#!/usr/bin/env python3
"""rack-focus, step 2: bake the focus pull into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the title arrives and after it has left are the a-roll itself, so the slot starts and ends on plain
footage. One worker process per core (up to 6), frames in chunks, everything seeded (same input, same output).

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 30,52,80    those frames as jpg -> work/t/ (red safe-zone lines with -g)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

import rack as R
from fxio import count_frames, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
_scene = None


def _init(plan):
    global _scene
    _scene = R.Scene(plan)


def _chunk(span):
    a, b = span
    pl = _scene.pl
    plain = reader(os.path.join(HERE, 'assets/aroll.mp4'), R.W, R.H, first=a, last=b)
    al = reader(os.path.join(HERE, 'assets/subject.webm'), R.W, R.H, alpha=True, first=a, last=b) if pl['cutout'] else None
    out = []
    for k in range(b - a + 1):
        p = next(plain)
        m = next(al, None) if al is not None else None
        out.append(_scene.frame(a + k, p, m).tobytes())
    return a, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('-g', action='store_true', help='draw the safe-zone lines on preview frames')
    ap.add_argument('--workers', type=int, default=0)
    args = ap.parse_args()
    plan_path = os.path.join(HERE, 'work/plan.json')
    if not os.path.exists(plan_path):
        sys.exit('work/plan.json is missing: run build.py first')
    pl = json.load(open(plan_path))
    n = pl['n']
    t0 = time.time()
    if args.frames:
        _init(pl)
        os.makedirs(os.path.join(HERE, 'work/t'), exist_ok=True)
        for f in sorted(int(v) for v in args.frames.split(',')):
            f = min(max(0, f), n - 1)
            _, frames = _chunk((f, f))
            img = np.frombuffer(frames[0], np.uint8).reshape(R.H, R.W, 3)
            if args.g:
                img = R.safe_guide(img)
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            st = _scene.title_state(f / R.FPS)
            print(f'wrote {os.path.relpath(p, HERE)}  focus on title {st[0]:.2f}, title blur {st[4]:.0f}px')
        return
    workers = args.workers or max(1, min(6, cpu_count() - 2))
    size = 10
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, R.W, R.H, R.FPS)
    with Pool(workers, initializer=_init, initargs=(pl,)) as pool:
        for a, frames in pool.imap(_chunk, spans):
            for fr in frames:
                w.stdin.write(fr)
            print(f'  frames {a}..{a + len(frames) - 1}', flush=True)
    w.stdin.close()
    w.wait()
    got = count_frames(out_path)
    secs = time.time() - t0
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f}s, '
          f'{secs / (n / R.FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
