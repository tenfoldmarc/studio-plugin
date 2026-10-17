#!/usr/bin/env python3
"""word-pile, step 2: draw the slabs and the floor line over the a-roll -> assets/fx.mp4 (1080x1920, exactly the
slot's frame count). Frames before the line draws and after it leaves are the a-roll itself (plain at both ends).
Frames are drawn in a process pool (up to 4 workers), in chunks, deterministic.

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 40,95,130   those frames as jpg -> work/t/ (red safe-zone lines with -g)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import slabs as L                                        # noqa: E402
from fxio import count_frames, reader, writer            # noqa: E402

_scene = None


def _init(plan):
    global _scene
    _scene = L.Scene(plan, np.load('work/track.npy'))


def _chunk(span):
    a, b = span
    plain = reader('assets/aroll.mp4', L.W, L.H, first=a, last=b)
    return a, [_scene.frame(a + k, next(plain)).tobytes() for k in range(b - a + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('-g', action='store_true', help='draw the safe-zone lines on preview frames')
    ap.add_argument('--workers', type=int, default=0)
    args = ap.parse_args()
    if not os.path.exists('work/plan.json'):
        sys.exit('work/plan.json is missing: run build.py first')
    pl = json.load(open('work/plan.json'))
    n = pl['n']
    t0 = time.time()
    if args.frames:
        _init(pl)
        os.makedirs('work/t', exist_ok=True)
        for f in sorted(int(v) for v in args.frames.split(',')):
            f = min(max(0, f), n - 1)
            _, frames = _chunk((f, f))
            img = np.frombuffer(frames[0], np.uint8).reshape(L.H, L.W, 3)
            if args.g:
                img = L.safe_guide(img)
            Image.fromarray(img).save(f'work/t/f_{f:03d}.jpg', quality=92)
            print(f'wrote work/t/f_{f:03d}.jpg')
        return
    workers = args.workers or max(1, min(4, cpu_count() - 1))
    size = 10
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    w = writer('assets/fx.mp4', L.W, L.H, L.FPS)
    with Pool(workers, initializer=_init, initargs=(pl,)) as pool:
        for a, frames in pool.imap(_chunk, spans):
            for fr in frames:
                w.stdin.write(fr)
    w.stdin.close()
    w.wait()
    got = count_frames('assets/fx.mp4')
    secs = time.time() - t0
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f}s, '
          f'{secs / (n / L.FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
