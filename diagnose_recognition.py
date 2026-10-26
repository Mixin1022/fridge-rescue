"""Inspect a short real-video interval; no recipe generation or silent correction."""
import argparse
import json
import math
from pathlib import Path
import re


def chinese_boxes(results):
    return [{'text': text, 'confidence': float(conf), 'box': [[float(x), float(y)] for x, y in box]}
            for box, text, conf in results if re.search(r'[\u4e00-\u9fff]', text)
            and len(re.findall(r'[A-Za-z]', text)) <= len(re.findall(r'[\u4e00-\u9fff]', text))]


def diagnose(video, output, start=15, duration=20, interval=5, speech=True):
    import cv2
    from ocr_engine import ChineseOCR
    from video_recipe import decode_speech_audio
    if not all(math.isfinite(v) for v in (start, duration, interval)) or start < 0 or duration <= 0 or interval <= 0:
        raise ValueError('Invalid time range')
    if output.exists():
        raise ValueError('Use a new output directory')
    if not video.is_file():
        raise ValueError('Video does not exist')
    model_root = Path(__file__).parent / 'work' / 'models'
    reader = ChineseOCR()
    output.mkdir(parents=True)
    cap = cv2.VideoCapture(str(video))
    samples = []
    try:
        if not cap.isOpened():
            raise ValueError('Cannot open video')
        timestamp = start
        while timestamp < start + duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            actual = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            stem = f'{timestamp:07.2f}'
            cv2.imencode('.jpg', frame)[1].tofile(str(output / f'{stem}-full.jpg'))
            height, width = frame.shape[:2]
            # Full-frame boxes preserve ingredient cards outside the subtitle region.
            scaled = cv2.resize(frame, (int(width * min(1, 960 / width)), int(height * min(1, 960 / width))))
            full_boxes = chinese_boxes(reader.readtext(frame))
            crop = frame[int(height * .68):int(height * .80), :]
            cv2.imencode('.jpg', crop)[1].tofile(str(output / f'{stem}-subtitle.jpg'))
            subtitle_boxes = chinese_boxes(reader.readtext(crop, decoder='beamsearch', beamWidth=5))
            samples.append({'requested_seconds': timestamp, 'actual_seconds': actual,
                            'full_frame': f'{stem}-full.jpg', 'subtitle_crop': f'{stem}-subtitle.jpg',
                            'full_frame_chinese_boxes': full_boxes, 'subtitle_chinese_boxes': subtitle_boxes})
            (output / 'ocr.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'OCR checked {timestamp:.1f}s ({len(samples)} frames)', flush=True)
            timestamp += interval
    finally:
        cap.release()
    if not samples:
        raise ValueError('No frames sampled in requested range')
    segments_out = []
    if speech:
        from faster_whisper import WhisperModel
        audio = decode_speech_audio(video)[int(start * 16000):int((start + duration) * 16000)]
        if not len(audio):
            raise ValueError('No audio in requested range')
        model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=4,
                             download_root=str(model_root / 'speech'), local_files_only=True)
        segments, info = model.transcribe(audio, language='zh', beam_size=5, temperature=0,
                                          condition_on_previous_text=False, vad_filter=True)
        for segment in segments:
            segments_out.append({'start': start + segment.start, 'end': start + segment.end, 'text': segment.text})
        (output / 'speech.json').write_text(json.dumps(segments_out, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 识别诊断：原文待核对', '', '没有生成食谱；全画面用于检查配料卡，字幕裁剪仅是初始区域，应对照完整画面确认。', '']
    for sample in samples:
        lines += [f"## {sample['actual_seconds']:.2f} 秒", '', f"![完整画面]({sample['full_frame']})", '',
                  '全画面中文字：' + ' / '.join(b['text'] for b in sample['full_frame_chinese_boxes']), '',
                  '字幕区域中文字：' + ' / '.join(b['text'] for b in sample['subtitle_chinese_boxes']), '']
    lines += ['## 独立语音转写', ''] + [f"- {s['start']:.2f}–{s['end']:.2f} 秒：{s['text']}" for s in segments_out]
    (output / 'diagnosis.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', type=float, default=15)
    parser.add_argument('--duration', type=float, default=20)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--no-speech', action='store_true')
    args = parser.parse_args()
    diagnose(args.video, args.output, args.start, args.duration, args.interval, not args.no_speech)
