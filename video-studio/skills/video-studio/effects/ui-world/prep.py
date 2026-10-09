#!/usr/bin/env python3
"""UI WORLD prep: measure the speaker from the cutout alpha and bake a clean-edged cutout for the bright screen.

  assets/subject.webm  ->  work/measure.json   per frame: head top, head width, shoulder line, head centre, and the
                                               top of their outline per column (so cards can sit beside their head)
                           work/measure.jpg    the middle frame with those lines drawn on it (LOOK at it)
                           assets/fg.webm      the cutout with its edge tightened and recoloured (no dark room fringe
                                               against the light screen)

Run from the slot folder:   python prep.py            (about 1 to 2 min for a 5 s slot)
                            python prep.py measure    measure only, no bake (seconds)
Needs numpy, scipy, Pillow.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H, Q = 1080, 1920, 4                 # frame size, measuring step (quarter size)
ALPHA_LO, ALPHA_HI = .10, .94           # alpha levels: below LO becomes clear, above HI solid (tightens a soft edge)
CHEST = 2.15                            # chest line = head top + CHEST x head width
only_measure = 'measure' in sys.argv[1:]

clip = json.load(open('clip.json'))
nfr = int(clip['frames'])
src = 'assets/subject.webm'
if not os.path.exists(src):
    sys.exit('assets/subject.webm is missing: this effect needs the cutout (make the slot without --no-cutout)')
os.makedirs('work', exist_ok=True)


def trace(m):
    """follow their head down from its top to where the shoulders open up. m = quarter-size mask of their outline.
    Returns (top row, head width, shoulder row, head centre x) in quarter px, or None when no head shape is found."""
    cols = ndimage.uniform_filter1d(m.sum(axis=0).astype(np.float32), 9)
    if cols.max() < 6:
        return None
    c = int(np.argmax(cols))                            # the column with the most of the speaker in it: head over torso
    ys = np.flatnonzero(m[:, max(0, c - 2):c + 3].any(axis=1))
    if not len(ys):
        return None
    top = int(ys[0])
    widths, centres = [], []
    lo = hi = c
    for y in range(top, m.shape[0]):
        row = m[y]
        if not row[c]:
            near = np.flatnonzero(row[lo:hi + 1])
            if not len(near):
                break
            c = lo + int(near[len(near) // 2])
        lo = hi = c
        while lo > 0 and row[lo - 1]:
            lo -= 1
        while hi < len(row) - 1 and row[hi + 1]:
            hi += 1
        widths.append(hi - lo + 1)
        centres.append((lo + hi) / 2)
        c = (lo + hi) // 2
        k = len(widths)
        if k > 4:
            head_w = max(widths[:k - 2])
            if k - 1 >= .6 * head_w and widths[-1] >= 1.35 * head_w:
                if 8 <= head_w <= 130 and .7 * head_w <= k - 1 <= 2.3 * head_w:
                    return top, head_w, y, float(np.mean(centres[:max(1, int(head_w))]))
                return None
    return None


dec = subprocess.Popen([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', src, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'],
                       stdout=subprocess.PIPE)
enc = None
if not only_measure:
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                            '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '18', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4', '-metadata:s:v:0', 'alpha_mode=1',
                            'assets/fg.webm'], stdin=subprocess.PIPE)

size = W * H * 4
col_tops, heads, blob_tops = [], [], []
n = 0
while True:
    buf = dec.stdout.read(size)
    if len(buf) < size:
        break
    fr = np.frombuffer(buf, np.uint8).reshape(H, W, 4)
    a = fr[..., 3].astype(np.float32) / 255
    m = a[::Q, ::Q] > .5
    lab, cnt = ndimage.label(m)
    if cnt > 1:                                         # the speaker = the biggest blob (drops a stray lamp or plant)
        m = lab == (1 + int(np.argmax(np.bincount(lab.ravel())[1:])))
    any_col = m.any(axis=0)
    col_tops.append(np.where(any_col, m.argmax(axis=0), H // Q).astype(int).tolist())
    rows = np.flatnonzero(m.sum(axis=1) >= 3)
    blob_tops.append(int(rows[0]) if len(rows) else H // Q)
    heads.append(trace(m))
    if enc is not None:
        a2 = np.clip((a - ALPHA_LO) / (ALPHA_HI - ALPHA_LO), 0, 1)
        ys = np.flatnonzero(a2.max(axis=1) > 0)
        xs = np.flatnonzero(a2.max(axis=0) > 0)
        out = fr.copy()
        if len(ys) and len(xs):
            y0, y1, x0, x1 = max(0, ys[0] - 8), min(H, ys[-1] + 9), max(0, xs[0] - 8), min(W, xs[-1] + 9)
            ab = a2[y0:y1, x0:x1]
            rgb = fr[y0:y1, x0:x1, :3].astype(np.float32)
            solid = (ab > .97).astype(np.float32)       # edge pixels take the colour of the solid body next to them
            den = ndimage.gaussian_filter(solid, 2.5)
            w = np.clip((.97 - ab) / .5, 0, 1) * (den > .03)
            for ch in range(3):
                near = ndimage.gaussian_filter(rgb[..., ch] * solid, 2.5) / np.maximum(den, 1e-4)
                rgb[..., ch] = rgb[..., ch] * (1 - w) + near * w
            out[y0:y1, x0:x1, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        out[..., 3] = (a2 * 255).astype(np.uint8)
        enc.stdin.write(out.tobytes())
    n += 1
    if n % 30 == 0:
        print(f'  frame {n}/{nfr}', flush=True)
dec.wait()
if enc is not None:
    enc.stdin.close()
    enc.wait()
if n != nfr:
    sys.exit(f'the cutout has {n} frames, clip.json says {nfr}: remake the slot (the cutout would drift)')
if min(blob_tops) >= H // Q:
    sys.exit('the cutout is empty: check assets/subject.webm')

warn = []
ok = [h for h in heads if h is not None]
if len(ok) >= max(3, .3 * n):
    head_w = float(np.median([h[1] for h in ok]))
    ok = [h for h in ok if .7 * head_w <= h[1] <= 1.4 * head_w]       # drop frames where a hand joined the head
    tops = np.array([h[0] for h in ok], np.float32)
    top_min, top_med = float(np.percentile(tops, 3)), float(np.median(tops))
    shoulder = float(np.median([h[2] for h in ok]))
    head_cx = float(np.median([h[3] for h in ok]))
    drift = float(tops.max() - tops.min())
else:
    tops = np.array(blob_tops, np.float32)
    top_min, top_med = float(np.percentile(tops, 3)), float(np.median(tops))
    head_w, shoulder, head_cx, drift = 37.0, top_med + 55, W / Q / 2, float(tops.max() - tops.min())
    warn.append('no clear head-and-shoulders shape in the outline (hand by the face, hood, long hair, lying down?): '
                'head size and chest line are guesses. Set EDGE, ZOOM and HEAD_Y by eye from work/measure.jpg')
edge = top_med + CHEST * head_w
if drift > 1.0 * head_w:
    warn.append(f'their head moves {drift * Q:.0f}px up and down in this slot: the screen is laid out for the highest '
                'position, so there is a gap above their head when the speaker sits lower')
if head_w * Q > 250:
    warn.append(f'tight shot (head {head_w * Q:.0f}px wide): the screen only gets the strip above their head and there '
                'is no room band for captions. A wider shot reads better')
meas = {'frames': n, 'q': Q, 'head_top_min': round(top_min * Q), 'head_top': round(top_med * Q),
        'head_w': round(head_w * Q), 'shoulder': round(shoulder * Q), 'head_cx': round(head_cx * Q),
        'edge': round(edge * Q), 'drift': round(drift * Q), 'head_found': f'{len(ok)}/{n}', 'warnings': warn,
        'col_tops': col_tops}
json.dump(meas, open('work/measure.json', 'w'))

# ---- picture to look at
mid = n // 2
subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n\\,{mid})',scale=540:960",
                '-frames:v', '1', 'work/measure_src.jpg'], check=True)
im = Image.open('work/measure_src.jpg').convert('RGB')
d = ImageDraw.Draw(im)
for name, yy, c in (('head top (highest)', meas['head_top_min'], (0, 220, 255)), ('shoulders', meas['shoulder'], (250, 230, 60)),
                    ('chest line (EDGE)', meas['edge'], (255, 60, 200))):
    d.line([(0, yy // 2), (540, yy // 2)], fill=c, width=2)
    d.text((8, yy // 2 + 3), f'{name}  y={yy}', fill=c)
hx, hw = meas['head_cx'] // 2, meas['head_w'] // 4
d.line([(hx - hw, meas['head_top'] // 2), (hx + hw, meas['head_top'] // 2)], fill=(0, 220, 255), width=4)
env = np.percentile(np.array(col_tops), 3, axis=0)
pts = [(i * Q // 2, int(v) * Q // 2) for i, v in enumerate(env) if v < H // Q]
if len(pts) > 1:
    d.line(pts, fill=(60, 255, 120), width=2)
im.save('work/measure.jpg', quality=88)
print(f"measured {n} frames (head found on {meas['head_found']}): head top y={meas['head_top_min']} to "
      f"{meas['head_top_min'] + meas['drift']}  head {meas['head_w']}px wide at x={meas['head_cx']}  "
      f"shoulders y={meas['shoulder']}  chest line y={meas['edge']}  (slot px, before the reframe)")
for w_ in warn:
    print('WARNING:', w_)
print('look at work/measure.jpg: cyan = head top and width, yellow = shoulders, pink = chest line, green = the '
      'highest their outline gets' + ('' if only_measure else '   |   baked assets/fg.webm'))
