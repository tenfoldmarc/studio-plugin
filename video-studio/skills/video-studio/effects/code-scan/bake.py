#!/usr/bin/env python3
"""code-scan, step 2: bake the code look into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the print front starts and after the picture is back are the a-roll itself, so the slot starts and
ends on plain footage. Worker processes (up to 4) take chunks of frames; everything is seeded (same input, same output).

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 30,52,80    those frames as jpg -> work/t/ (red safe-zone lines with -g)
  PY bake.py --sheet 30,52,80     the same frames tiled small into work/t/sheet.jpg (quick look)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np
from PIL import Image

import scan as S
from fxio import count_frames, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
_scene = None


def _init(plan):
    global _scene
    _scene = S.Scene(plan, HERE)


def _chunk(span):
    a, b = span
    pl = _scene.pl
    if b < pl['f_first'] or a > pl['f_last']:                 # nothing of the effect here: copy the a-roll
        plain = reader(os.path.join(HERE, 'assets/aroll.mp4'), S.W, S.H, first=a, last=b)
        return a, [next(plain).tobytes() for _ in range(b - a + 1)]
    plain = reader(os.path.join(HERE, 'assets/aroll.mp4'), S.W, S.H, first=a, last=b)
    al = reader(os.path.join(HERE, 'assets/subject.webm'), S.W, S.H, alpha=True, first=a, last=b) if pl['cutout'] else None
    out = []
    for k in range(b - a + 1):
        p = next(plain)
        m = next(al, None) if al is not None else None
        out.append(_scene.frame(a + k, p, m).tobytes())
    return a, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('--sheet', default='')
    ap.add_argument('-g', action='store_true', help='draw the safe-zone lines on preview frames')
    ap.add_argument('--workers', type=int, default=0)
    args = ap.parse_args()
    plan_path = os.path.join(HERE, 'work/plan.json')
    if not os.path.exists(plan_path):
        sys.exit('work/plan.json is missing: run build.py first')
    pl = json.load(open(plan_path))
    n = pl['n']
    t0 = time.time()
    if args.frames or args.sheet:
        _init(pl)
        os.makedirs(os.path.join(HERE, 'work/t'), exist_ok=True)
        tiles = []
        for f in sorted(int(v) for v in (args.frames or args.sheet).split(',')):
            f = min(max(0, f), n - 1)
            _, frames = _chunk((f, f))
            img = np.frombuffer(frames[0], np.uint8).reshape(S.H, S.W, 3)
            if args.g:
                img = S.safe_guide(img)
            if args.sheet:
                tiles.append(Image.fromarray(img).resize((216, 384), Image.LANCZOS))
                continue
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            print(f'wrote {os.path.relpath(p, HERE)}  ({_scene.state(f / S.FPS)[2] or "plain"})')
        if tiles:
            sheet = Image.new('RGB', (216 * len(tiles), 384))
            for k, im in enumerate(tiles):
                sheet.paste(im, (216 * k, 0))
            sheet.save(os.path.join(HERE, 'work/t/sheet.jpg'), quality=88)
            print('wrote work/t/sheet.jpg')
        return
    workers = args.workers or max(1, min(4, cpu_count() - 2))
    size = 8
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, S.W, S.H, S.FPS)
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
          f'{secs / (n / S.FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
