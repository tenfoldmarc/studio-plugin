#!/usr/bin/env python3
"""cover-story, step 3: bake the cover into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames outside the cover are the a-roll itself, so the slot starts and ends on plain footage. The push-in is
resampled from assets/aroll_hi.mp4 when the slot has one. One worker process per core (up to 6), frames in chunks.

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 60,110,168  those frames as jpg -> work/t/ (red safe-zone lines with -g)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

import cover as C
from fxio import count_frames, probe_size, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
_scene = None


def _init(plan):
    global _scene
    _scene = C.Scene(plan)


def _chunk(span):
    a, b = span
    pl = _scene.pl
    src = os.path.join(HERE, pl['src'])
    sw, sh = probe_size(src)
    plain = reader(os.path.join(HERE, 'assets/aroll.mp4'), C.W, C.H, first=a, last=b)
    hi = reader(src, sw, sh, first=a, last=b) if src.endswith('_hi.mp4') else None
    al = reader(os.path.join(HERE, 'assets/subject.webm'), C.W, C.H, alpha=True, first=a, last=b)
    out = []
    for k in range(b - a + 1):
        p = next(plain)
        s = next(hi) if hi is not None else p
        m = next(al)
        out.append(_scene.frame(a + k, p, s, m).tobytes())
    return a, out, _scene.stats[:]


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
            _, frames, _ = _chunk((f, f))
            img = np.frombuffer(frames[0], np.uint8).reshape(C.H, C.W, 3)
            if args.g:
                img = C.safe_guide(img)
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            print('wrote', os.path.relpath(p, HERE))
        return
    workers = args.workers or max(1, min(6, cpu_count() - 2))
    size = 12
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, C.W, C.H, C.FPS)
    stats, done = [], 0
    with Pool(workers, initializer=_init, initargs=(pl,)) as pool:
        for a, frames, st in pool.imap(_chunk, spans):
            for fr in frames:
                w.stdin.write(fr)
            done += len(frames)
            stats += st
            print(f'  frames {a}..{a + len(frames) - 1}', flush=True)
    w.stdin.close()
    w.wait()
    got = count_frames(out_path)
    secs = time.time() - t0
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f}s, '
          f'{secs / (n / C.FPS):.1f}s per second of slot, {workers} workers')
    if stats:
        st = np.array(sorted(set(map(tuple, stats))))
        print(f'  masthead hidden behind the speaker: up to {st[:, 1].max() * 100:.0f}% of the cap height '
              f'(frame {int(st[st[:, 1].argmax(), 0])}), ink area up to {st[:, 2].max() * 100:.0f}%'
              + ('   !! over 30%: the title may not read. Use a shorter or lower FRAMING' if st[:, 1].max() > 0.3 else ''))
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
