#!/usr/bin/env python3
"""inside-out, step 2: bake the effect into assets/fx.mp4 (1080x1920, exactly the slot's frame count).

Frames before the line starts and after the room is back are the a-roll itself, so the slot starts and ends on
plain footage. Up to 4 worker processes, frames in chunks; every frame is a pure function of its number, so the
result is the same on every machine and every run.

  PY bake.py                      full bake -> assets/fx.mp4
  PY bake.py --frames 40,70,110   those frames as jpg -> work/t/ (red safe-zone lines with -g)
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import cv2
import numpy as np
from PIL import Image

from fxio import count_frames, reader, writer

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
P = None
GRID = None


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def ease3(t):
    """power3 out: quick start, long settle."""
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def blur_half(img, sigma):
    """a wide gaussian blur done at half size (same look, a quarter of the work)."""
    s = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    s = cv2.GaussianBlur(s, (0, 0), sigma / 2)
    return cv2.resize(s, (W, H), interpolation=cv2.INTER_LINEAR)


def zoom(img, z, cx, cy):
    M = np.float32([[z, 0, cx - z * cx], [0, z, cy - z * cy]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def clean(a):
    """matte float 0..1 -> only the speaker (kill polygons, then the largest piece)."""
    b = (a > 0.5).astype(np.uint8)
    for p in P['kill']:
        poly = np.array(p, np.int32)
        cv2.fillPoly(b, [poly], 0)
        cv2.fillPoly(a, [poly], 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    if n > 2:
        big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        keep = cv2.dilate((lab == big).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(np.float32)
        a = a * keep
    return a


def geometry(a):
    lin, lout = P['line_px']
    s = cv2.GaussianBlur(a, (0, 0), 4.5)
    s = np.clip((s - 0.42) / 0.16, 0, 1)
    b = (s > 0.5).astype(np.uint8)
    d_out = cv2.distanceTransform(1 - b, cv2.DIST_L2, 5)
    d_in = cv2.distanceTransform(b, cv2.DIST_L2, 5)
    sd = d_out - d_in
    ol = np.clip(sd + lin + 0.5, 0, 1) * np.clip(lout + 0.5 - sd, 0, 1)
    ol = cv2.GaussianBlur(ol, (0, 0), 0.7)
    rows = np.where(b.max(1) > 0)[0]
    return s, ol, float(rows[-1]) if len(rows) else float(H)


def render(f, plate, a, fill):
    """plate, fill: rgb float32 0..255; a: matte float32 0..1 (already averaged over 5 frames)."""
    pl, fr = P, P['frames']
    k = f - pl['f_in']
    ks = pl['k_scale']
    xx, yy = GRID
    s, ol, bottom = geometry(clean(a))
    top, hx = pl['head_top'][f], pl['head_cx'][f]
    kp = pl['keep']
    ex = (xx - hx) / kp['rx']
    ey = np.maximum(yy - (top + kp['cy']), 0) / kp['ry']
    keep = 1 - sstep(0.84, 1.10, np.sqrt(ex * ex + ey * ey))          # head and neck stay live video

    # beat 1a: the line runs down the speaker
    yl = (top - 40) + ease3((k + 1) / fr['line']) * (bottom + 90 - (top - 40))
    line = ol * (1 - sstep(yl - 36, yl, yy))
    # beat 1b: the window opens from the collar down, then holds while the picture slowly pushes in
    y0 = top + kp['cy'] + 0.8 * kp['ry']
    yo = y0 + ease3((k + 1) / fr['open']) * (bottom + 150 - y0)
    win = (s * (1 - keep) * (1 - sstep(yo - 120, yo, yy)))[..., None]
    # the window is a hole cut in the picture: its edge shades the picture behind it (light from top left)
    ish = np.clip(1 - blur_half(shift(s, 6 * ks, 11 * ks), 12 * ks), 0, 1) * 0.55
    ish = ish + (1 - cv2.GaussianBlur(s, (0, 0), 4)) * 0.25
    s3 = s[..., None]
    out = plate * (1 - win) + fill * (1 - np.clip(ish, 0, 0.8))[..., None] * win          # state A
    shd = blur_half(shift(line, 0, 4), 6) * (1 - s)                  # faint shadow outside the line on pale rooms
    out = out * (1 - np.clip(shd * 2.0, 0, pl['line_shadow']))[..., None]

    if f >= pl['f_flip']:
        # beat 2: ONE soft iris from the chest. Inside it the speaker is solid again and the same picture is the room.
        e = ease3((f - pl['f_flip'] + 1) / fr['flip'])
        cx, cy = hx, top + pl['iris_below']
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        soft = 150 * ks
        r = e * (float(dist.max()) + soft)
        iris = sstep(r, r - soft, dist)[..., None]
        if pl['on_floor']:                                            # stronger where the body meets a floor
            floor = sstep(bottom - 300 * ks, bottom, yy)
        else:
            floor = 0.0
        sh = blur_half(shift(s, 0, 16 * ks), 26 * ks) * (0.20 + 0.34 * floor)
        flipped = fill * (1 - sh)[..., None] * (1 - s3) + plate * s3                     # state B
        out = out * (1 - iris) + flipped * iris
    acc = np.array(pl['accent'], np.float32)
    out = out * (1 - line[..., None]) + acc * line[..., None]
    if f >= pl['f_out']:                                              # the real room eases back, line fades with it
        b = sstep(0, 1, (f - pl['f_out'] + 1) / fr['back'])
        out = out * (1 - b) + plate * b
    return out


def _init(plan):
    global P, GRID
    P = plan
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    GRID = (xx, yy)


def _chunk(span):
    a, b = span
    pl = P
    n = pl['n']
    rgb = list(reader(os.path.join(HERE, 'assets/aroll.mp4'), W, H, first=a, last=b))
    lo, hi = max(0, a - 2), min(n - 1, b + 2)
    al = list(reader(os.path.join(HERE, 'assets/subject.webm'), W, H, alpha=True, first=lo, last=hi))
    fa, fb = max(a, pl['f_in']), min(b, pl['f_end'] - 1)
    fill = {}
    if fa <= fb:
        for i, fr in enumerate(reader(os.path.join(HERE, 'work/fill.mp4'), W, H, first=fa - pl['f_in'],
                                      last=fb - pl['f_in'])):
            fill[fa + i] = fr
    outs = []
    for f in range(a, b + 1):
        plate = rgb[min(f - a, len(rgb) - 1)]
        if not (pl['f_in'] <= f < pl['f_end']):
            outs.append(np.ascontiguousarray(plate).tobytes())
            continue
        m = sum(wt * al[min(max(f + o, lo), hi) - lo][...].astype(np.float32)
                for o, wt in zip((-2, -1, 0, 1, 2), (1, 2, 3, 2, 1))) / (9 * 255.0)   # calm the matte boil
        k = f - pl['f_in']
        z = pl['push'][0] + (pl['push'][1] - pl['push'][0]) * k / max(pl['need'] - 1, 1)
        fit = pl.get('fit')
        if fit:   # wide shots: the whole picture sits inside the body, then grows into the room with the flip
            e = ease3(min(1.0, 1.4 * (f - pl['f_flip'] + 1) / pl['frames']['flip'])) if f >= pl['f_flip'] else 0.0
            zz = z * (fit['scale'] + (1 - fit['scale']) * e)
            cx = fit['cx'] + (W / 2 - fit['cx']) * e
            cy = fit['cy'] + (H / 2 - fit['cy']) * e
            M = np.float32([[zz, 0, cx - zz * W / 2], [0, zz, cy - zz * H / 2]])
            fl = cv2.warpAffine(fill[f].astype(np.float32), M, (W, H), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REFLECT)
        else:
            fl = zoom(fill[f].astype(np.float32), z, W / 2, H / 2)
        img = render(f, plate.astype(np.float32), m, fl)
        outs.append(np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes())
    return a, outs


def safe_guide(img):
    g = img.copy()
    c = (255, 0, 0)
    cv2.rectangle(g, (35, 220), (W - 35, 1470), c, 3)
    cv2.line(g, (W - 100, 1155), (W - 100, 1470), c, 3)
    return g


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
            img = np.frombuffer(frames[0], np.uint8).reshape(H, W, 3)
            if args.g:
                img = safe_guide(img)
            p = os.path.join(HERE, f'work/t/f_{f:03d}.jpg')
            Image.fromarray(img).save(p, quality=92)
            print('wrote', os.path.relpath(p, HERE))
        return
    workers = args.workers or max(1, min(4, cpu_count() - 2))
    size = 10
    spans = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out_path = os.path.join(HERE, 'assets/fx.mp4')
    w = writer(out_path, W, H, FPS)
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
          f'{secs / (n / FPS):.1f}s per second of slot, {workers} workers')
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
