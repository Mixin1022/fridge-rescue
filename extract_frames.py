"""Local representative-frame extraction; never uploads video."""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def extract(source, output, interval=2.0, scene_threshold=0.25, max_frames=100):
    source, output = Path(source), Path(output)
    if not source.is_file():
        raise ValueError(f"Input file not found: {source}")
    if source.suffix.lower() != '.mp4':
        raise ValueError('Input must be an MP4 file')
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('interval must be finite and positive')
    if not math.isfinite(scene_threshold) or not 0 < scene_threshold <= 1:
        raise ValueError('scene_threshold must be in (0, 1]')
    if max_frames < 1:
        raise ValueError('max_frames must be positive')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty to prevent overwriting')
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise ValueError('Video cannot be opened by the installed decoder')
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('Video has no usable frame rate')
        backend = cap.getBackendName()
        reported_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        output.mkdir(parents=True, exist_ok=True)
        frames, previous, index, last_saved = [], None, 0, -float('inf')
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            # Presentation timestamp from decoder; frame/FPS fallback is approximate.
            pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            timestamp = pts if math.isfinite(pts) and (index == 0 or pts > 0) else index / fps
            small = cv2.resize(frame, (64, 64)).astype(np.float32)
            score = 0.0 if previous is None else float(np.mean(np.abs(small - previous)) / 255)
            reason = 'first' if index == 0 else ('scene_change' if score >= scene_threshold else 'interval')
            if len(frames) < max_frames and (index == 0 or score >= scene_threshold or timestamp - last_saved >= interval):
                name = f'frame_{index:06d}.jpg'
                success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if not success:
                    raise RuntimeError('JPEG encoding failed')
                (output / name).write_bytes(encoded.tobytes())
                frames.append({'file': name, 'frame_index': index, 'timestamp_seconds': round(timestamp, 6),
                               'reason': reason, 'scene_score': round(score, 6),
                               'width': frame.shape[1], 'height': frame.shape[0]})
                last_saved = timestamp
            previous = small
            index += 1
        if index == 0:
            raise ValueError('No decodable frames found')
        metadata = {'source': str(source.resolve()), 'opencv_version': cv2.__version__, 'backend': backend,
                    'fps': fps, 'reported_frame_count': reported_count, 'decoded_frame_count': index,
                    'possible_incomplete_decode': reported_count > 0 and index < reported_count,
                    'selection': 'representative frames, not codec I-frames',
                    'timestamp_note': 'decoder PTS with frame/FPS fallback; not validated for all variable-frame-rate inputs',
                    'parameters': {'interval_seconds': interval, 'scene_threshold': scene_threshold, 'max_frames': max_frames},
                    'saved_frame_count': len(frames), 'frames': frames}
        (output / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
        return metadata
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=2.0)
    parser.add_argument('--scene-threshold', type=float, default=0.25)
    parser.add_argument('--max-frames', type=int, default=100)
    args = parser.parse_args()
    try:
        data = extract(args.input, args.output, args.interval, args.scene_threshold, args.max_frames)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')
    print(json.dumps({'decoded': data['decoded_frame_count'], 'saved': data['saved_frame_count'], 'output': str(args.output.resolve())}))


if __name__ == '__main__':
    main()
