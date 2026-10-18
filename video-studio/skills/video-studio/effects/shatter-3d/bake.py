#!/usr/bin/env python3
"""shatter-3d, step 2: bake the effect into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the break and after the glass has gone (or the tiles have healed) are the a-roll itself, so the slot
starts and ends on plain footage. The effect frames are split into work units (one per 12 fps fracture step, the
crack frames, the glass frames in fours) over up to 4 worker processes. Every random choice is seeded: two bakes of
the same plan match frame for frame.

  PY bake.py                          full bake -> assets/fx.mp4
  PY bake.py --frames 105,130,142 -g  those frames as jpg -> work/t/ (-g: red safe-zone lines, face and eye boxes)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import cv2
import numpy as np

import shcore as S
from fxio import count_frames, frames, probe_size, stream, writer

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
W, H, FPS = S.W, S.H, S.FPS
_fx = _glass = _pl = None


def _init(pl):
    global _fx, _glass, _pl
    _pl = pl
    _fx, _glass = S.make(pl)


def _held():
    last = _fx.steps2[-1]
    return last, _fx.pose(None, (last - _fx.fh) / FPS + S.LEAD, last)


def _unit(u):
    """u = list of output frame numbers -> [(n, BGR bytes)]."""
    hw, hh = probe_size(_pl['src_hi'])
    plans = {n: _fx.plan(n) for n in u}
    need_hi = {p[3].get('pane_src', p[1]) for p in plans.values() if p[0] in ('frac', 'glass', 'plate')}
    need_lo = {p[1] for p in plans.values() if p[0] in ('glass', 'clean')}
    hi = frames(_pl['src_hi'], need_hi, hw, hh)
    lo = frames('assets/aroll.mp4', need_lo, W, H)
    out, cache = [], {}
    for n in u:
        mode, src, P, extra = plans[n]
        if mode == 'clean':
            img = lo[src]
        elif mode == 'plate':
            img = S.plate(hi[src], P['scale'])
        else:
            fsrc = extra.get('pane_src', src)
            key = (fsrc, round(P['A'], 5))
            if key not in cache:
                cache[key] = _fx.render(hi[fsrc], P)
            img = cache[key]
            if 'crack' in extra:
                img = _glass.cracks(img, extra['crack'])
            elif mode == 'glass':
                img = _glass.render(img, lo[src], extra['t'])
        out.append((n, np.ascontiguousarray(img).tobytes()))
    return out


def units(fx, n):
    """contiguous groups of effect frames that share their expensive part."""
    out, cur, key = [], [], None
    for f in range(n):
        mode, src, P, extra = fx.plan(f)
        if mode == 'clean':
            continue
        k = ('frac', src, round(P['A'], 5)) if mode == 'frac' and 'crack' not in extra else \
            ('crack',) if 'crack' in extra else ('glass', (f - fx.fr) // 4) if mode == 'glass' else ('plate', f)
        if k != key and cur:
            out.append(cur)
            cur = []
        key = k
        cur.append(f)
    if cur:
        out.append(cur)
    return out


def guide(img, pl):
    img = img.copy()
    red = (40, 40, 230)
    for y in (220, 1470):
        cv2.line(img, (0, y), (W, y), red, 2)
    cv2.line(img, (35, 220), (35, 1470), red, 2)
    cv2.line(img, (W - 35, 220), (W - 35, 1155), red, 2)
    cv2.line(img, (W - 100, 1155), (W - 100, 1470), red, 2)
    if pl.get('face'):
        x0, y0, x1, y1 = (int(v) for v in pl['face'])
        cv2.rectangle(img, (x0, y0), (x1, y1), (60, 220, 60), 2)
    if pl.get('eyes'):
        x0, y0, x1, y1 = pl['eyes']
        cv2.rectangle(img, (x0, y0), (x1, y1), (230, 200, 40), 2)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('-g', action='store_true', help='draw the safe zone, the measured face (green) and eyes (blue)')
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
        for f in sorted({min(max(0, int(v)), n - 1) for v in args.frames.split(',')}):
            mode = _fx.plan(f)[0]
            got = _unit([f])[0][1]
            img = np.frombuffer(got, np.uint8).reshape(H, W, 3)
            if args.g:
                img = guide(img, pl)
            p = f'work/t/f_{f:03d}.jpg'
            cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            print(f'wrote {p} ({mode})')
        return
    fx = S.Shatter(pl)
    us = units(fx, n)
    workers = args.workers or max(1, min(4, cpu_count() - 2))
    w = writer('assets/fx.mp4', W, H, FPS)
    lo = stream('assets/aroll.mp4', W, H)
    done = {}
    with Pool(workers, initializer=_init, initargs=(pl,)) as pool:
        it = pool.imap(_unit, us)
        for f in range(n):
            frame = next(lo, None)
            if fx.plan(f)[0] == 'clean':
                if frame is None:
                    sys.exit(f'assets/aroll.mp4 ran out at frame {f}')
                w.stdin.write(np.ascontiguousarray(frame).tobytes())
                continue
            while f not in done:
                for k, b in next(it):
                    done[k] = b
                print(f'  effect frames up to {max(done)}', flush=True)
            w.stdin.write(done.pop(f))
    w.stdin.close()
    w.wait()
    got = count_frames('assets/fx.mp4')
    secs = time.time() - t0
    print(f'wrote assets/fx.mp4: {got} frames ({"ok" if got == n else "!! expected " + str(n)}), {secs:.0f}s, '
          f'{secs / (n / FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
