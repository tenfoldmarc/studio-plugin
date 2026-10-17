#!/usr/bin/env python3
"""Step 4. Bake the picture: work/curve.json + plate + track + cutout -> assets/fx.mp4 (1080x1920, same frame count).

Per frame: the room without the speaker (this frame's room, the clean plate where the speaker stands), warped by
the vertigo scale with a real zoom blur across the open shutter, a soft vignette and contact shadow that grow with
the push, then the speaker comped back on top untouched (with the old room colour un-mixed from the soft edge).
At scale 1.0 a frame is the untouched a-roll, so the slot starts and ends on plain footage.
Uses every core but one (FX_PROCS=n to change). Deterministic: no randomness anywhere.
Usage (from the slot folder):  PY bake.py               full bake -> assets/fx.mp4
                               PY bake.py --frames 40-48   JPG previews of those frames -> work/bake/
"""
import math
import os
import warnings
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np

from vcore import FF, FPS, H, W, Warp, count_frames, here, load_json, mirror_fill, smoothstep, vertigo

G = {}
warnings.filterwarnings('ignore', message='All-NaN slice')     # pixels nobody saw: filled by mirror_fill


def init():
    cv2.setNumThreads(1)
    c = load_json(here('work', 'curve.json'))
    G['c'] = c
    G['fr'] = np.load(here('work', 'frames.npy'), mmap_mode='r')
    G['al'] = np.load(here('work', 'alpha.npy'), mmap_mode='r')
    G['cam'] = np.load(here('work', 'cam.npy'))
    G['plate'] = cv2.imread(here('assets', 'plate.png'))
    G['warp'] = Warp(c['origin'], c['shoulder_y'], c['seat_y'], c['squeeze'], c['lens_k'])


def warp_avg(img, s0, s1):
    wp = G['warp']
    n = int(np.clip(math.ceil(abs(s1 - s0) * wp.reach / 5.0), 1, 40))
    acc = np.zeros(img.shape, np.float32)
    for i in range(n):
        s = (s0 + s1) / 2 if n == 1 else s0 + (s1 - s0) * (i + 0.5) / n
        mx, my = wp.maps(s)
        acc += cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    return acc / n


def live_room(i, orig, hole):
    """Moving camera: one plate cannot line up, but frames a few tenths of a second away barely differ in angle.
    Re-align the neighbours (+-10 frames) to this frame, take the median of the room they show where the speaker
    has moved out of the way, and mirror-fill only what none of them saw."""
    ys, xs = np.where(hole)
    if len(ys) == 0:
        return orig.astype(np.float32)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    to_i = np.vstack([cv2.invertAffineTransform(G['cam'][i]), [0, 0, 1]])
    k = np.ones((25, 25), np.uint8)
    ones = np.full((H, W), 255, np.uint8)
    stack, valid = [], []
    n = len(G['fr'])
    for j in range(max(0, i - 10), min(n, i + 11), 2):
        if j == i:
            continue
        m = (to_i @ np.vstack([G['cam'][j], [0, 0, 1]]))[:2].astype(np.float32)        # frame j -> frame i
        img = cv2.warpAffine(np.asarray(G['fr'][j]), m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        a = cv2.warpAffine(cv2.dilate(np.asarray(G['al'][j]), k), m, (W, H), borderValue=255)
        inside = cv2.warpAffine(ones, m, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
        stack.append(img[y0:y1, x0:x1].astype(np.float32))
        valid.append((a[y0:y1, x0:x1] < 8) & (inside[y0:y1, x0:x1] > 250))
    out = orig.astype(np.float32).copy()
    left = hole.copy()
    if stack:
        s, v = np.stack(stack), np.stack(valid)
        s[~v] = np.nan
        with np.errstate(all='ignore'):
            med = np.nanmedian(s, axis=0)
        got = (v.sum(0) >= 2) & hole[y0:y1, x0:x1]
        out[y0:y1, x0:x1][got] = med[got]
        left[y0:y1, x0:x1] &= ~got
    return mirror_fill(np.clip(out + 0.5, 0, 255).astype(np.uint8), left)


def frame(i):
    c, wp = G['c'], G['warp']
    tm = (i + 0.5) / FPS
    s = vertigo(tm, c)
    s0, s1 = vertigo(tm - c['shutter'] / 2 / FPS, c), vertigo(tm + c['shutter'] / 2 / FPS, c)
    orig = np.asarray(G['fr'][i])
    if abs(s - 1) < 1e-5 and abs(s1 - s0) < 1e-5:
        return orig.tobytes()
    inv = cv2.invertAffineTransform(G['cam'][i])                 # REF -> this frame
    person = np.asarray(G['al'][i])
    a = person.astype(np.float32)[..., None] / 255
    hole = cv2.dilate((person > 4).astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    hole = cv2.GaussianBlur(hole, (0, 0), 1.6).astype(np.float32)[..., None] / 255
    if c.get('fill') == 'live':                                   # moving camera: fill from this frame's neighbours
        plate = live_room(i, orig, hole[..., 0] > 0.02)
    else:
        plate = cv2.warpAffine(G['plate'], inv, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    room = orig * (1 - hole) + plate * hole                       # this frame's room without the speaker
    room8 = np.clip(room + 0.5, 0, 255).astype(np.uint8)
    bg = warp_avg(room8, s0, s1)
    k = float(np.clip((s - 1) / (c['scale'] - 1), 0, 1.15))      # 0..1 strength of the push
    if k > 0.02 and c['edge_blur'] > 0:
        e = c['edge_blur'] * k / 2
        if abs(s1 - s0) < 2 * e:
            blur = warp_avg(room8, s - e, s + e)
            bg = bg * (1 - wp.edge_m) + blur * wp.edge_m
    if k > 0:
        vig = 1 - c['vignette'] * k * smoothstep(0.35, 1.2, wp.rho)[..., None]
        sh = cv2.GaussianBlur(person, (0, 0), 30).astype(np.float32) / 255
        sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 10]]), (W, H))
        sh2 = cv2.GaussianBlur(person, (0, 0), 9).astype(np.float32) / 255
        shadow = 1 - c['shadow'] * k * (0.75 * sh + 0.25 * sh2)[..., None]
        bg = bg * vig * shadow
    unmix = smoothstep(0.06, 0.45, a)
    fix = np.clip(unmix * (1 - a) * (orig - room), -14, 14)       # clamped: the plate is a guess back there
    out = a * orig + (1 - a) * bg + fix
    mix = float(smoothstep(0.0, 0.012, abs(s - 1) + abs(s1 - s0)))  # exact original picture at rest
    out = orig * (1 - mix) + out * mix
    return np.clip(out + 0.5, 0, 255).astype(np.uint8).tobytes()


def main():
    for p in ('work/curve.json', 'work/frames.npy', 'work/cam.npy', 'assets/plate.png'):
        if not os.path.exists(here(*p.split('/'))):
            sys.exit(f'{p} is missing: run prep.py, then build.py')
    c = load_json(here('work', 'curve.json'))
    n = c['frames']
    procs = int(os.environ.get('FX_PROCS', max(1, (os.cpu_count() or 2) - 1)))
    if '--frames' in sys.argv:
        a, b = (int(v) for v in sys.argv[sys.argv.index('--frames') + 1].split('-'))
        os.makedirs(here('work', 'bake'), exist_ok=True)
        with Pool(min(procs, b - a + 1), initializer=init) as pool:
            for i, buf in zip(range(a, b + 1), pool.imap(frame, range(a, b + 1))):
                img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
                cv2.imwrite(here('work', 'bake', f'f{i:03d}.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f'wrote work/bake/f{a:03d}..f{b:03d}.jpg')
        return
    out = here('assets', 'fx.mp4')
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS),
                            '-i', '-', '-vf', 'scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,'
                            'format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '12', '-g', '15', '-bf', '0',
                            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                            '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    with Pool(procs, initializer=init) as pool:
        for i, buf in enumerate(pool.imap(frame, range(n), chunksize=2)):
            enc.stdin.write(buf)
            if i % 30 == 0:
                print(f'bake {i}/{n}', flush=True)
    enc.stdin.close()
    enc.wait()
    got = count_frames(out)
    print(f'wrote assets/fx.mp4: {got} frames' + ('' if got == n else f'   !! expected {n}'))
    if got != n:
        sys.exit(1)


if __name__ == '__main__':
    main()
