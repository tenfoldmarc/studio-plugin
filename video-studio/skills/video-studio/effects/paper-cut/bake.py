#!/usr/bin/env python3
"""paper-cut, step 2: bake the collage into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the paper arrives and after the tear are the a-roll itself, so the slot starts and ends on plain
footage. One worker process per core (up to 6), frames in chunks; every frame is seeded, so the result is the same
on every machine and every run.

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 40,90,140   those frames as jpg -> work/t/ (red safe-zone lines with -g)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

import collage as C
from fxio import count_frames, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
_scene = None


class Src:
    """the a-roll and the cleaned cutout alpha for a run of frames; single frames outside it are decoded on demand."""

    def __init__(self, lo, hi, pl, plate):
        self.lo, self.pl, self.plate = lo, pl, plate
        self.rgb = list(reader(os.path.join(HERE, 'assets/aroll.mp4'), C.W, C.H, first=lo, last=hi))
        self.al = list(reader(os.path.join(HERE, 'assets/subject.webm'), C.W, C.H, alpha=True, first=lo, last=hi))
        self.clean = {}

    def _raw(self, i):
        k = i - self.lo
        if 0 <= k < len(self.rgb) and k < len(self.al):
            return self.rgb[k], self.al[k]
        r = next(reader(os.path.join(HERE, 'assets/aroll.mp4'), C.W, C.H, first=i, last=i))
        a = next(reader(os.path.join(HERE, 'assets/subject.webm'), C.W, C.H, alpha=True, first=i, last=i))
        return r, a

    def room(self, i):
        return self._raw(i)[0]

    def get(self, i):
        if i not in self.clean:
            r, a = self._raw(i)
            self.clean[i] = (r, C.clean_matte(a, r, self.pl['matte'], self.plate))
        return self.clean[i]


def _plate():
    p = os.path.join(HERE, 'work/plate.npz')
    if not os.path.exists(p):
        return None
    z = np.load(p)
    return z['col'], z['bg']


def _init(plan):
    global _scene
    _scene = C.Scene(plan, _plate())


def _chunk(span):
    a, b = span
    pl = _scene.pl
    lo = min(a, C.held_frame(a, pl['f_in'], pl['step_fps']))
    src = Src(lo, b, pl, _scene.plate)
    return a, [_scene.frame(f, src).tobytes() for f in range(a, b + 1)]


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
            img = np.frombuffer(frames[0], np.uint8).reshape(C.H, C.W, 3)
            if args.g:
                img = C.safe_guide(img)
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            print('wrote', os.path.relpath(p, HERE))
        return
    workers = args.workers or max(1, min(6, cpu_count() - 2))
    size = 10
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, C.W, C.H, C.FPS)
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
          f'{secs / (n / C.FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
