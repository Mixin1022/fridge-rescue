"""Create a deterministic six-second MP4 with three distinct scenes."""
from pathlib import Path
import argparse
import cv2
import numpy as np


def generate(path):
    path = Path(path)
    if path.exists():
        raise ValueError('Refusing to overwrite an existing video')
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 240))
    if not writer.isOpened():
        raise RuntimeError('MP4 encoder unavailable')
    try:
        for i in range(60):
            frame = np.full((240, 320, 3), [30, 130, 230][i // 20], np.uint8)
            cv2.putText(frame, f'Scene {i // 20 + 1} / {i:02d}', (20, 120), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
            writer.write(frame)
    finally:
        writer.release()
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
