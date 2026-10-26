"""Run RapidOCR against saved real frames. Do not generate a recipe."""
import argparse
import json
from pathlib import Path
from datetime import datetime


def run(frames, output):
    from rapidocr import RapidOCR
    images = sorted(frames.glob('*-full.jpg'))
    if not images:
        raise ValueError('No saved diagnostic frames found')
    if output.exists():
        raise ValueError('Choose a new output directory')
    engine = RapidOCR()
    output.mkdir(parents=True)
    records = []
    baseline_path = frames / 'ocr.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf-8')) if baseline_path.exists() else []
    lines = ['# 同一画面的 OCR 对照', '', '请逐行对照原始图片检查食材名称、数字和单位。两种识别结果都未经人工纠正。', '']
    for path in images:
        result = engine(str(path))
        txts = result.txts if result.txts is not None else []
        scores = result.scores if result.scores is not None else []
        boxes = result.boxes if result.boxes is not None else []
        rows = [{'text': str(text), 'confidence': float(score), 'box': box.tolist() if hasattr(box, 'tolist') else box}
                for text, score, box in zip(txts, scores, boxes)]
        old = next((s['full_frame_chinese_boxes'] for s in baseline if s['full_frame'] == path.name), [])
        records.append({'image': str(path.resolve()), 'rapidocr': rows, 'easyocr': old})
        lines += [f'## {path.name}', '', f'![原始画面]({path.resolve().as_posix()})', '', '### RapidOCR', '']
        lines += [f"- {r['text']}（置信度 {r['confidence']:.2f}）" for r in rows] or ['未识别到文字。']
        lines += ['', '### 旧 EasyOCR', ''] + [f"- {r['text']}" for r in old] + ['']
        (output / 'comparison.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Completed: {path.name}', flush=True)
    (output / 'comparison.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Compare results: {output.resolve() / "comparison.md"}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=Path, default=Path(__file__).parent / 'local-videos' / 'diagnostic-v1')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    destination = args.output or Path(__file__).parent / 'local-videos' / ('ocr-comparison-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    try:
        run(args.frames, destination)
    except ModuleNotFoundError:
        parser.exit(1, '缺少 RapidOCR，请运行项目内 test_new_ocr.cmd 安装并测试。\n')
    except Exception as error:
        parser.exit(1, f'OCR comparison failed: {error}\n')
