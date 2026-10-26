"""Local subtitle/voice recipe draft. Every candidate retains its evidence."""
import argparse
import importlib.util
import json
import math
import re
import sys
import tempfile
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from link_recipe import extract_url
from content_classifier import classify_content
from link_recipe import SafeRedirect, validate_url
from urllib.request import Request, build_opener

ACTION = re.compile(r'切|剁|刨|撒|放入|加入|倒入|下锅|锅里下|煎|炒|炖|煮|盖|翻|拌|捞|盛|装盘|回锅|收汁|补水|温水|小火|分钟|小时|搅打|打湿|稀释|铺上|准备|先取|油温|调味|配料|糖盐|做.*(?:酱|油|浇头)')
FOOD = re.compile(r'番茄|黄瓜|青椒|红椒|面包|大蒜|洋葱|葱姜|皮蛋|肉末|猪肉|牛肉|鸡肉|章鱼|橄榄油|辣椒|花椒|酱油|蚝油|豆瓣酱|白醋|雪梨醋|盐|白糖')


def clean_caption(text):
    # Preserve Chinese recipe text; discard appended OCR English subtitle noise.
    text = text.strip()
    if re.search(r'[\u4e00-\u9fff]', text):
        text = re.split(r'\s+[A-Za-z@][A-Za-z\s@;]*', text, maxsplit=1)[0].strip()
    return text


def normalized_text(text):
    return re.sub(r'[^\u4e00-\u9fff0-9]', '', clean_caption(text))


def matches_evidence(a, b):
    gap = max(a['start'], b['start']) - min(a['end'], b['end'])
    if gap > 2:
        return False
    left, right = normalized_text(a['text']), normalized_text(b['text'])
    if not left or not right:
        return False
    if gap <= 0 and a['source'] != b['source'] and min(len(left), len(right)) >= 2 and (left in right or right in left):
        return True
    if min(len(left), len(right)) >= 6 and (left in right or right in left):
        return True
    if a['source'] != b['source'] and min(len(left), len(right)) >= 8:
        short, long = sorted((left, right), key=len)
        if any(SequenceMatcher(None, short, long[i:i + len(short)]).ratio() >= .8
               for i in range(len(long) - len(short) + 1)):
            return True
    return SequenceMatcher(None, left, right).ratio() >= .68


def validate_evidence(records):
    if not isinstance(records, list):
        raise ValueError('Evidence must be a JSON list')
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str):
            raise ValueError('Each evidence record needs text/start/end/source')
        start, end = item.get('start'), item.get('end')
        if not isinstance(start, (float, int)) or not isinstance(end, (float, int)) or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end:
            raise ValueError('Evidence timestamps must be finite, nonnegative and ordered')
        if item.get('source') not in {'ocr', 'speech', 'manual_fixture'}:
            raise ValueError('Unrecognized evidence source')
    return records


def build_recipe(records, source_url=None):
    validate_evidence(records)
    steps = []
    ingredients = []
    title_candidates = []
    classifications = []
    for item in records:
        category, reason = classify_content(item, records)
        classifications.append(dict(item, category=category, classification_reason=reason))
    categories = {id(item): classified['category'] for item, classified in zip(records, classifications)}
    for item in records:
        if categories[id(item)] == 'ingredient':
            if not any(normalized_text(x['text']) == normalized_text(item['text']) for x in ingredients):
                ingredients.append({'text': item['text'], 'time': item['start'], 'confidence': item.get('confidence'), 'evidence': item})
        if item['source'] == 'ocr' and item['start'] <= 10 and re.search(r'(?:皮蛋面|牛肉|牛肋条|[\u4e00-\u9fff]{2,}(?:面|饭|汤|饼))', item['text']) and not re.search(r'屏幕|这碗|细节|配料|面包', item['text']):
            if not any(t['text'] == item['text'] for t in title_candidates):
                title_candidates.append({'text': item['text'], 'time': item['start'], 'evidence': item})
    for item in sorted(records, key=lambda r: (r['start'], r['end'])):
        text = clean_caption(item['text'])
        if item.get('kind') == 'ingredient_card':
            continue
        if categories[id(item)] not in {'operation', 'state'}:
            continue
        normalized = normalized_text(text)
        match = next((s for s in reversed(steps) if any(matches_evidence(e, item) for e in s['evidence'])), None)
        if match is not None:
            match['start'] = min(match['start'], item['start'])
            match['end'] = max(match['end'], item['end'])
            match['evidence'].append(item)
            # Longer source retains compound instructions; never invent corrections.
            reliable_ocr = item['source'] == 'ocr' and item.get('confidence', 0) >= .9
            existing_ocr = any(e['source'] == 'ocr' and e.get('confidence', 0) >= .9 for e in match['evidence'][:-1])
            if reliable_ocr and len(normalized) >= len(normalized_text(match['instruction'])) * .65 or not existing_ocr and len(normalized) > len(normalized_text(match['instruction'])):
                match['instruction'] = text
            continue
        # Only merge adjacent, identical captions. Repeated later actions are retained.
        if steps and steps[-1]['normalized'] == normalized and item['start'] - steps[-1]['end'] <= 3:
            steps[-1]['end'] = max(steps[-1]['end'], item['end'])
            steps[-1]['evidence'].append(item)
        else:
            steps.append({'start': item['start'], 'end': item['end'], 'instruction': text,
                          'normalized': normalized, 'evidence': [item]})
    for step in steps:
        del step['normalized']
        captions = []
        for e in step['evidence']:
            if e['source'] == 'ocr' and e.get('confidence', 0) >= .95:
                caption = clean_caption(e['text'])
                norm = normalized_text(caption)
                if not any(norm in normalized_text(c) for c in captions):
                    captions = [c for c in captions if normalized_text(c) not in norm]
                    captions.append(caption)
        if captions:
            caption_text = '；'.join(captions)
            # A subtitle can cover only the verb in a longer spoken sentence.
            # Keep that sentence when the subtitle omits substantial context.
            complete_speech = [e['text'] for e in step['evidence'] if e['source'] == 'speech'
                               and len(normalized_text(e['text'])) > len(normalized_text(caption_text)) * 1.3]
            step['instruction'] = max(complete_speech, key=len) if complete_speech else caption_text
        notes = []
        instruction = step['instruction']
        if re.search(r'屏幕|配料表|配到|肥膜|鲜鲜|汤汤|五流|中筋质', instruction):
            notes.append('识别文字含可疑词或引用画面配料，需要回看对应画面，不能据此确定食材或用量。')
        variants = {normalized_text(e['text']) for e in step['evidence']}
        if len(variants) > 1:
            notes.append('字幕与语音文字存在差异，原文证据已保留。')
        step['review_notes'] = notes
    fixture = any(r['source'] == 'manual_fixture' for r in records)
    return {'source_url': source_url, 'status': 'fixture_draft' if fixture else ('needs_review' if steps else 'no_steps_detected'),
            'method': 'Timestamp-aligned OCR/ASR candidate merging; no visual action model',
            'steps': steps, 'evidence': records,
            'content_classification': classifications,
            'narration': [r for r in classifications if r['category'] == 'narration'],
            'context': [r for r in classifications if r['category'] == 'uncertain'],
            'ingredients': ingredients, 'dish_name_candidates': title_candidates,
            'limitations': ['Candidates need human review; incomplete captions may split one action across several candidates.',
                            'Silent visual actions are not recognized; unspoken quantities and cooking times are not invented.']}


def ocr_video(video, model_dir, interval, crop_top, download):
    import cv2
    from ocr_engine import ChineseOCR
    reader = ChineseOCR()
    cap = cv2.VideoCapture(str(video))
    records = []
    try:
        if not cap.isOpened():
            raise ValueError('Cannot decode input video')
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('No usable video FPS')
        next_time, index = 0.0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if not math.isfinite(timestamp) or (timestamp <= 0 and index > 0):
                timestamp = index / fps
            if timestamp >= next_time:
                results = reader.readtext(frame)
                results.sort(key=lambda r: (min(p[1] for p in r[0]), min(p[0] for p in r[0])))
                for box, text, conf in results:
                    if conf < .7:
                        continue
                    # Quantity-bearing cards outside the subtitle band are stored independently.
                    top = min(p[1] for p in box) / frame.shape[0]
                    kind = 'ingredient_card' if top < crop_top and re.search(r'\d+(?:\.\d+)?\s*(?:毫升|克|根|片|个|颗|勺|ml|g)', text) else 'caption'
                    records.append({'start': round(timestamp, 3), 'end': round(timestamp, 3), 'source': 'ocr',
                                    'text': text, 'confidence': float(conf), 'kind': kind,
                                    'box': [[float(x), float(y)] for x, y in box]})
                if int(timestamp) % 10 == 0:
                    print(f'画面识别进度：{timestamp:.0f} 秒，已保存 {len(records)} 条文字', flush=True)
                next_time = timestamp + interval
            index += 1
        if index == 0:
            raise ValueError('No video frames decoded')
    finally:
        cap.release()
    return records


def decode_speech_audio(video):
    """Decode locally without faster-whisper's removed PyAV metadata_errors argument."""
    import av
    import numpy as np
    chunks = []
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    with av.open(str(video), mode='r') as container:
        if not container.streams.audio:
            raise ValueError('视频没有音轨，请选择仅字幕模式。')
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                chunks.append(converted.to_ndarray().reshape(-1).copy())
        for converted in resampler.resample(None):
            chunks.append(converted.to_ndarray().reshape(-1).copy())
    if not chunks:
        raise ValueError('未解码到音频，请选择仅字幕模式。')
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def transcribe(video, model, model_dir, download):
    from faster_whisper import WhisperModel
    recognizer = WhisperModel(model, device='cpu', compute_type='int8', download_root=str(model_dir), local_files_only=not download)
    audio = decode_speech_audio(video)
    print(f'音频解码完成：{len(audio) / 16000:.1f} 秒，开始转写……', flush=True)
    segments, info = recognizer.transcribe(audio, language='zh', vad_filter=True)
    return [{'start': s.start, 'end': s.end, 'text': s.text.strip(), 'source': 'speech',
             'avg_logprob': s.avg_logprob, 'no_speech_probability': s.no_speech_prob} for s in segments]


def resolve_share_url(url):
    validate_url(url)
    from urllib.parse import urlparse
    if urlparse(url).hostname in {'xhslink.cn', 'xhslink.com', 'v.douyin.com'}:
        with build_opener(SafeRedirect()).open(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20) as response:
            url = response.url
        validate_url(url)
    return url


def download_video(url, root, cookies=None, max_bytes=None):
    """Attempt public video extraction, without browser cookies or login bypass."""
    from yt_dlp import YoutubeDL
    url = resolve_share_url(url)
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='download-', dir=root))
    last_progress = [0.0]
    def progress(event):
        import time
        if max_bytes is not None and event.get('downloaded_bytes', 0) > max_bytes:
            raise ValueError('视频超过允许的下载大小')
        now = time.monotonic()
        if event.get('status') == 'finished':
            print('视频下载完成，正在检查文件……', flush=True)
        elif now - last_progress[0] >= 3:
            downloaded = event.get('downloaded_bytes', 0) / (1024 * 1024)
            print(f'正在下载视频：已接收 {downloaded:.1f} MB', flush=True)
            last_progress[0] = now
    options = {'outtmpl': str(folder / 'video.%(ext)s'), 'format': 'best[ext=mp4][vcodec!=none][acodec!=none]',
               'noplaylist': True, 'socket_timeout': 15, 'retries': 1,
               'progress_hooks': [progress],
               'quiet': True, 'no_warnings': True, 'overwrites': False}
    if max_bytes is not None:
        options['max_filesize'] = max_bytes
    with YoutubeDL(options) as downloader:
        if cookies is not None:
            for cookie in cookies:
                downloader.cookiejar.set_cookie(cookie)
        info = downloader.extract_info(url, download=True)
        if not info:
            raise ValueError('未获取到视频信息')
        path = Path(downloader.prepare_filename(info)).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file() or path.suffix.lower() != '.mp4':
        raise ValueError('未下载到可用的 MP4')
    return path


def prompt_local_video():
    while True:
        value = input('请输入本地 MP4 路径（可拖入终端；输入 q 退出）：').strip().strip('\"').strip("'")
        if value.lower() in {'q', 'quit', '退出'}:
            raise KeyboardInterrupt
        path = Path(value).expanduser()
        if path.is_file() and path.suffix.lower() == '.mp4':
            return path
        print('文件不存在或不是 MP4，请重新输入。')


def dependency_hint():
    executable = f'"{sys.executable}"'
    prefix = '& ' if sys.platform == 'win32' else ''
    print(f'当前运行 Python：{sys.executable}')
    print('请在终端使用同一 Python 安装依赖：')
    print(f'{prefix}{executable} -m pip install -r "{Path(__file__).parent / "requirements-recognition.txt"}"')
    print(f'{prefix}{executable} -m playwright install chromium')


def report_fetch_error(error, stage):
    if isinstance(error, ModuleNotFoundError):
        print(f'{stage}缺少模块：{error.name or "未知"}。尚未开始访问小红书。')
        dependency_hint()
        return
    message = str(error)
    if '缺少 Playwright' in message:
        print('浏览器组件 Playwright 未安装，尚未打开浏览器。')
        dependency_hint()
    elif "Executable doesn't exist" in message:
        print('Playwright 已安装，但 Chromium 浏览器未安装。')
        dependency_hint()
    else:
        # Redact URLs and likely authentication material from third-party errors.
        message = re.sub(r'https?://\S+', '[链接已隐藏]', message)
        message = re.sub(r'(?i)(cookie|token|authorization|password)\s*[:=]\s*\S+', r'\1=[已隐藏]', message)
        print(f'{stage}失败（{type(error).__name__}）：{message[:400]}')


def prepare_input(args, interactive):
    if interactive:
        print('Fridge Rescue：输入链接 → 获取视频 → 本地识别 → 步骤草稿')
        while True:
            share = input('请粘贴小红书或抖音链接或完整分享文本（回车使用本地视频；q 退出）：').strip()
            if share.lower() in {'q', 'quit', '退出'}:
                raise KeyboardInterrupt
            if not share:
                break
            try:
                args.share = extract_url(share)
                break
            except ValueError:
                print('没有找到有效的小红书 HTTPS 链接，请重新输入。')
    url = extract_url(args.share) if args.share else None
    if not args.video and not args.evidence:
        if url:
            print('正在尝试获取公开视频……')
            try:
                args.video = download_video(url, Path(__file__).parent / 'work' / 'downloads')
                print(f'已获取视频：{args.video}')
            except Exception as error:
                # Do not print extractor errors that may contain signed URLs or cookies.
                report_fetch_error(error, '自动获取')
                if not getattr(args, 'no_browser', False) and 'douyin.com' not in url:
                    print('尝试使用专用浏览器及保存的登录状态……')
                    try:
                        from browser_video import fetch_with_browser
                        args.video = fetch_with_browser(url, Path(__file__).parent / 'work' / 'downloads',
                                                       getattr(args, 'browser_profile', Path(__file__).parent / 'work' / 'browser-profile'),
                                                       allow_login=interactive, timeout=getattr(args, 'login_timeout', 180))
                        print(f'已获取视频：{args.video}')
                    except Exception as browser_error:
                        report_fetch_error(browser_error, '浏览器获取')
                if not interactive and not args.video:
                    raise ValueError('无法自动获取视频。请直接运行进入交互模式，或使用 --video 指定本地 MP4。') from error
        if interactive and not args.video:
            args.video = prompt_local_video()
        elif not args.video:
            raise ValueError('请提供 --share、--video 或 --evidence，或直接运行进入交互模式。')
    if interactive:
        print('识别方式：字幕＋语音' if args.mode == 'both' else f'识别方式：{args.mode}', flush=True)
        if not args.download_models:
            args.download_models = input('首次使用需要下载模型，允许下载吗？[y/N]：').strip().lower() in {'y', 'yes', '是'}
    if args.output is None:
        args.output = Path(__file__).parent / 'local-videos' / ('run-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    return url


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--share', help='Xiaohongshu URL or full share text; attempt public video download')
    p.add_argument('--video', type=Path, help='Local authorized MP4')
    p.add_argument('--evidence', type=Path, help='Replay timestamped OCR/ASR JSON; fixture provenance preserved')
    p.add_argument('--output', type=Path, help='New directory; defaults to a unique project local-videos folder')
    p.add_argument('--interactive', action='store_true', help='Prompt for link and fallback video')
    p.add_argument('--diagnose', action='store_true', help='Save short-interval OCR/ASR evidence instead of generating a recipe')
    p.add_argument('--no-browser', action='store_true', help='Disable browser-assisted download')
    p.add_argument('--browser-profile', type=Path, default=Path(__file__).parent / 'work' / 'browser-profile')
    p.add_argument('--login-timeout', type=int, default=180, help='Seconds to wait for visible login')
    p.add_argument('--mode', choices=['ocr', 'speech', 'both'], default='both')
    p.add_argument('--interval', type=float, default=1)
    p.add_argument('--crop-top', type=float, default=.55)
    p.add_argument('--model', default='small')
    p.add_argument('--model-dir', type=Path, default=Path(__file__).parent / 'work' / 'models')
    p.add_argument('--download-models', action='store_true', help='Allow first-run public model downloads')
    p.add_argument('--check', action='store_true')
    p.add_argument('--analysis', choices=['auto', 'deepseek', 'local'], default='auto', help='Use configured DeepSeek, or local rules')
    argv = sys.argv[1:] if argv is None else argv
    a = p.parse_args(argv)
    try:
        if a.check:
            print(f'当前 Python：{sys.executable}')
            print(json.dumps({m: importlib.util.find_spec(m) is not None for m in ['cv2', 'yt_dlp', 'playwright', 'rapidocr', 'faster_whisper']}, indent=2))
            return
        url = prepare_input(a, a.interactive or not argv)
        if a.output.exists():
            raise ValueError('Output exists; choose a new directory')
        if bool(a.video) == bool(a.evidence):
            raise ValueError('Choose exactly one: --video or --evidence.')
        if a.diagnose:
            if not a.video:
                raise ValueError('诊断需要实际 MP4，不能使用文字样例。')
            from diagnose_recognition import diagnose
            print('进入短片段诊断：分别保存完整画面、中文字幕和语音，暂不生成食谱。', flush=True)
            diagnose(a.video, a.output)
            print(f'诊断完成，请打开：{a.output / "diagnosis.md"}', flush=True)
            return
        if not math.isfinite(a.interval) or a.interval <= 0 or not 0 <= a.crop_top < 1:
            raise ValueError('interval must be positive; crop-top must be in [0, 1)')
        if a.evidence:
            loaded = json.loads(a.evidence.read_text(encoding='utf-8'))
            records = validate_evidence(loaded['evidence'] if isinstance(loaded, dict) else loaded)
        else:
            if not a.video.is_file() or a.video.suffix.lower() != '.mp4':
                raise ValueError('Provide an existing authorized MP4')
            required = (['rapidocr'] if a.mode == 'ocr' else ['faster_whisper'] if a.mode == 'speech' else ['rapidocr', 'faster_whisper'])
            missing = [m for m in required if importlib.util.find_spec(m) is None]
            if missing:
                raise ValueError('缺少识别依赖：' + ', '.join(missing) + '。请在当前 Python 环境执行：python -m pip install -r requirements-recognition.txt')
            records = []
            a.output.mkdir(parents=True)
            if a.mode in {'ocr', 'both'}:
                print('开始字幕识别（首次加载模型可能较慢）……', flush=True)
                records.extend(ocr_video(a.video, a.model_dir / 'ocr', a.interval, a.crop_top, a.download_models))
                (a.output / 'ocr-evidence.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            if a.mode in {'speech', 'both'}:
                print('开始语音转写（CPU 处理可能需要数分钟）……', flush=True)
                speech_records = transcribe(a.video, a.model, a.model_dir / 'speech', a.download_models)
                records.extend(speech_records)
                (a.output / 'speech-evidence.json').write_text(json.dumps(speech_records, ensure_ascii=False, indent=2), encoding='utf-8')
        result = build_recipe(records, url)
        result['input_video'] = str(a.video.resolve()) if a.video else (loaded.get('input_video') if isinstance(loaded, dict) else None)
        a.output.mkdir(parents=True, exist_ok=True)
        (a.output / 'recipe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# 视频步骤候选（需核对）', '', f"状态：{result['status']}", '']
        lines += ['## 菜名原文候选', ''] + [f"- [{t['time']:.1f}秒] {t['text']}" for t in result['dish_name_candidates']]
        lines += ['', '## 配料与用量原文候选（字幕／语音）', ''] + [f"- [{t['time']:.1f}秒] {t['text']}" for t in sorted(result['ingredients'], key=lambda t: t['time'])]
        lines += ['', '## 操作步骤', '']
        lines += [f"{i}. [{s['start']:.1f}–{s['end']:.1f}秒] {s['instruction']}" +
                  (f" **待核对：{' '.join(s['review_notes'])}**" if s['review_notes'] else '') for i, s in enumerate(result['steps'], 1)]
        lines += ['', '## 用途不明确的原文（需核对）', '']
        seen_context = set()
        for item in sorted(result['context'], key=lambda r: r['start']):
            norm = normalized_text(item['text'])
            if norm and norm not in seen_context:
                lines.append(f"- [{item['start']:.1f}秒，{item['source']}] {item['text']}")
                seen_context.add(norm)
        lines += ['', '## 开场与闲聊评价（不计入操作步骤，保留供核对）', '']
        seen_narration = set()
        for item in sorted(result['narration'], key=lambda r: r['start']):
            norm = normalized_text(item['text'])
            if norm and norm not in seen_narration:
                lines.append(f"- [{item['start']:.1f}秒] {item['text']}")
                seen_narration.add(norm)
        lines += ['', *result['limitations']]
        (a.output / 'recipe.md').write_text('\n'.join(lines), encoding='utf-8')
        from deepseek_recipe import load_config, analyze, render
        if a.analysis == 'deepseek' or (a.analysis == 'auto' and load_config()[0]):
            print('正在调用 DeepSeek 分析完整字幕和语音（发送文字，不发送视频）……', flush=True)
            try:
                ai_result = analyze(records)
                (a.output / 'deepseek-recipe.json').write_text(json.dumps(ai_result, ensure_ascii=False, indent=2), encoding='utf-8')
                (a.output / 'local-rule-recipe.md').write_text('\n'.join(lines), encoding='utf-8')
                (a.output / 'recipe.md').write_text(render(ai_result, records), encoding='utf-8')
                result['deepseek'] = ai_result
                (a.output / 'recipe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                print('DeepSeek 分析完成，原文编号与材料／操作覆盖检查通过。', flush=True)
            except Exception as error:
                print(f'DeepSeek 未完成：{error}。已保留本地规则结果。', flush=True)
                if a.analysis == 'deepseek':
                    p.exit(1, 'DeepSeek 分析失败；本地识别结果已保存。\n')
        from render_recipe import render_recipe
        render_recipe(result, a.output / 'recipe.html')
        from build_library import add_recipe
        add_recipe(result)
        print(f'食谱页面已保存：{a.output / "recipe.html"}', flush=True)
        print(json.dumps({'status': result['status'], 'step_candidates': len(result['steps']), 'output': str(a.output.resolve())}, ensure_ascii=False))
    except (KeyboardInterrupt, EOFError):
        print('\n已退出，没有生成食谱。')
    except Exception as error:
        p.exit(1, f'Recognition failed: {error}\n')


if __name__ == '__main__':
    main()
