#!/usr/bin/env python3
"""neon-sign, step 2: bake the sign into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the sign fades on and after it is gone are the a-roll itself, so the slot starts and ends on plain
footage. Worker processes (up to 4) take the frames in chunks; every random number is seeded, so a re-bake is
identical.

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 30,60,120   those frames as jpg -> work/t/ (red safe-zone lines with -g)
  PY bake.8 GB)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

import scene as S
from fxio import count_frames, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN, STATIC = os.path.join(HERE, 'work/plan.json'), os.path.join(HERE, 'work/static.npz')
_scene = None


def _init():
    global _scene
    _scene = S.Scene(PLAN, STATIC)


def _chunk(span):
    a, b = span
    plain = reader(os.path.join(HERE, 'assets/aroll.mp4'), S.W, S.H, first=a, last=b)
    al = reader(os.path.join(HERE, 'assets/subject.webm'), S.W, S.H, alpha=True, first=a, last=b)
    out = []
    for k in range(b - a + 1):
        p = next(plain)
        m = next(al)
        out.append(np.ascontiguousarray(_scene.frame(a + k, p, m)).tobytes())
    return a, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('-g', action='store_true', help='draw the safe-zone lines on preview frames')
    ap.add_argument('--workers', type=int, default=0)
    args = ap.parse_args()
    if not (os.path.exists(PLAN) and os.path.exists(STATIC)):
        sys.exit('work/plan.json or work/static.npz is missing: run build.py first')
    n = json.load(open(PLAN))['n']
    t0 = time.time()
    if args.frames:
        _init()
        os.makedirs(os.path.join(HERE, 'work/t'), exist_ok=True)
        for f in sorted(int(v) for v in args.frames.split(',')):
            f = min(max(0, f), n - 1)
            _, frames = _chunk((f, f))
            img = np.frombuffer(frames[0], np.uint8).reshape(S.H, S.W, 3)
            if args.g:
                img = S.safe_guide(img)
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            print('wrote', os.path.relpath(p, HERE))
        return
    workers = args.workers or max(1, min(4, cpu_count() - 2))
    size = 8
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, S.W, S.H, S.FPS)
    with Pool(workers, initializer=_init) as pool:
        for a, frames in pool.imap(_chunk, spans):
            for fr in frames:
                w.stdin.write(fr)
            print(f'  frames {a}..{a + len(frames) - 1}', flush=True)
    w.stdin.close()
    w.wait()
    got = count_frames(out_path)
    secs = time.time() - t0
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f}s, '
          f'{secs / (n / S.FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
