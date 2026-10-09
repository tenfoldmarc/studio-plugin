#!/usr/bin/env python3
"""Step 1. Where their eyes are in every frame -> work/headtrack.json + work/track_check.jpg   (1080x1920 coordinates)

Two passes, numpy + PIL only:
  A. cutout alpha (assets/subject.webm): the head is the topmost blob of the matte. Head width is found scale-free
     (works on a wide shot and on a close-up), then per frame the cap top and head centre inside a column window that
     follows the head, so a raised hand is never the "head". Eye estimate = (centre, top + EYE_K * head width).
  B. plate (assets/aroll.mp4): the top of the head alone drifts 20-30 px against the eyes when the speaker tips their head, and
     the matte edge breathes. So the forehead-eyes-nose patch of one upright reference frame is template-matched
     (zero-mean NCC, coarse then fine, sub-pixel) forwards and backwards through the clip. The alpha estimate stays as
     the guard rail: a weak match, or one that walks more than GUARD head widths from it, falls back to alpha.
The smoothing (how tightly the camera follows) is a camera choice and happens in build.py.

AIM in build.py's CLIP block overrides the automatic eye estimate: AIM = (frame, x, y), the point between their eyes.
ALWAYS open work/track_check.jpg: the cross must sit between their eyes in every tile.

Usage (from the slot folder):  PY track.py
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image, ImageDraw

import clipblock

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
AW, AH = 540, 960        # alpha analysis size
KA = 1080 / AW
EYE_K = 0.78             # eye line below the top of the head, in head widths (front-facing head, cap or hair)
GUARD = 0.35             # max distance (head widths) the plate match may sit from the alpha estimate
MIN_SCORE = 0.5
FINE_HEAD = 110          # the plate is analysed at the size where the speaker's head is this many px wide ...
COARSE = 3               # ... and first at 1/3 of that, with a search as wide as half a head (handheld, fast moves)

AIM = clipblock.load().get('AIM')
sub, plate_src = os.path.join(HERE, 'assets/subject.webm'), os.path.join(HERE, 'assets/aroll.mp4')
if not os.path.exists(sub):
    sys.exit('assets/subject.webm is missing: this effect needs the cutout (make the slot without --no-cutout)')


def decode(args, w, h, pix='gray'):
    raw = subprocess.run([FF, '-loglevel', 'error', *args, '-f', 'rawvideo', '-pix_fmt', pix, '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w) if pix == 'gray' else np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


# ---------------------------------------------------------------- pass A: alpha
alpha = decode(['-c:v', 'libvpx-vp9', '-i', sub, '-vf', f'alphaextract,scale={AW}:{AH}', '-fps_mode', 'passthrough'], AW, AH) > 128
n = len(alpha)
MINROW = max(3, int(.008 * AW))


def measure(a, cx, w):
    """cap top, head centre and head width inside a window of +-0.8 w around cx. None if there is no matte there."""
    lo, hi = max(0, int(cx - .8 * w)), min(AW, int(cx + .8 * w))
    rows = np.where(a[:, lo:hi].sum(axis=1) >= MINROW)[0]
    if not len(rows):
        return None
    top = int(rows[0])
    band = a[top + int(.25 * w):top + int(.72 * w) + 1, lo:hi]       # ears / cap sides: the widest part of the head
    if band.shape[0] < 2:
        return None
    cols = np.where(band.sum(axis=0) > band.shape[0] * .5)[0]
    if len(cols) < 4:
        return None
    return top, lo + (cols[0] + cols[-1]) / 2, float(band.sum(axis=1).max())


# head width, scale-free: start small and let the window grow until the width stops changing
centres, widths = [], []
for a in alpha[::max(1, n // 40)]:
    rows = np.where(a.sum(axis=1) >= MINROW)[0]
    if not len(rows):
        continue
    xs = np.where(a[rows[0]:rows[0] + 6].any(axis=0))[0]
    cx, w, m = (xs[0] + xs[-1]) / 2, .08 * AW, None
    for _ in range(12):
        m = measure(a, cx, w)
        if m is None:
            break
        done = abs(m[2] - w) < .02 * w
        cx, w = m[1], m[2]
        if done:
            break
    if m is not None:
        widths.append(w); centres.append(cx)
if not widths:
    sys.exit('no person found in the cutout alpha')
wmed = float(np.median(widths))
cx_prev = float(np.median(centres))
A, clipped = [], 0
for a in alpha:
    m = measure(a, cx_prev, wmed)
    if m is None:
        A.append(dict(A[-1]) if A else {'top': 0.0, 'cx': cx_prev})
        continue
    top, cx, _ = m
    clipped += top <= 1
    cx_prev = .5 * cx_prev + .5 * cx
    A.append({'top': float(top), 'cx': float(cx)})
for o in A:
    o['ex'], o['ey'] = o['cx'] * KA, (o['top'] + EYE_K * wmed) * KA      # full-res px from here on
HEAD_W = wmed * KA

# ---------------------------------------------------------------- pass B: plate template match (coarse -> fine)
sf = min(1.0, FINE_HEAD / HEAD_W)
FW, FH = int(round(1080 * sf / (2 * COARSE))) * 2 * COARSE, int(round(1920 * sf / (2 * COARSE))) * 2 * COARSE
kx, ky = FW / 1080, FH / 1920
fine = decode(['-i', plate_src, '-vf', f'scale={FW}:{FH}:flags=area'], FW, FH).astype(np.float32)
assert len(fine) == n, f'{len(fine)} plate frames, {n} matte frames: the cutout is not frame-exact with aroll.mp4'
coarse = fine.reshape(n, FH // COARSE, COARSE, FW // COARSE, COARSE).mean(axis=(2, 4))
hw = HEAD_W * kx                                   # head width at the fine size
PW, PH = int(round(1.2 * hw)), int(round(1.12 * hw))            # patch: cap strap / forehead, eyes, nose (rigid parts)
OX, OY = PW / 2, .70 * hw                          # eye point inside the patch
PWc, PHc = PW // COARSE, PH // COARSE
RC = int(np.ceil(.5 * hw / COARSE)) + 1            # coarse search radius: half a head per frame
RF = COARSE + 1                                    # fine search radius around the coarse hit
PAD = PW + PH + RC * COARSE                        # edge padding so a face near the border still matches
fine_p = np.pad(fine, ((0, 0), (PAD, PAD), (PAD, PAD)), mode='edge')
PADc = PAD // COARSE + 1
coarse_p = np.pad(coarse, ((0, 0), (PADc, PADc), (PADc, PADc)), mode='edge')


def ncc(win, tpl):
    v = sliding_window_view(win, tpl.shape)
    t = tpl - tpl.mean()
    vm = v - v.mean(axis=(2, 3), keepdims=True)
    return (vm * t).sum(axis=(2, 3)) / (np.sqrt((vm ** 2).sum(axis=(2, 3)) * (t ** 2).sum()) + 1e-6)


def peak(c):
    ly, lx = np.unravel_index(np.argmax(c), c.shape)
    dx = dy = 0.0
    if 0 < lx < c.shape[1] - 1 and 0 < ly < c.shape[0] - 1:          # parabolic sub-pixel peak
        a, b, d = c[ly, lx - 1], c[ly, lx], c[ly, lx + 1]
        dx = float(np.clip(.5 * (a - d) / (a - 2 * b + d - 1e-9), -.5, .5))
        a, b, d = c[ly - 1, lx], c[ly, lx], c[ly + 1, lx]
        dy = float(np.clip(.5 * (a - d) / (a - 2 * b + d - 1e-9), -.5, .5))
    return lx, ly, dx, dy, float(c[ly, lx])


def cut(img_p, pad, x, y, w, h):
    return img_p[pad + y:pad + y + h, pad + x:pad + x + w]


def match(i, tpl_f, tpl_c, px, py):
    """patch top-left (fine px) in frame i, searched around (px, py)"""
    cx0, cy0 = px // COARSE - RC, py // COARSE - RC
    lx, ly, _, _, _ = peak(ncc(cut(coarse_p[i], PADc, cx0, cy0, PWc + 2 * RC, PHc + 2 * RC), tpl_c))
    gx, gy = (cx0 + lx) * COARSE, (cy0 + ly) * COARSE
    fx0, fy0 = gx - RF, gy - RF
    lx, ly, dx, dy, sc = peak(ncc(cut(fine_p[i], PAD, fx0, fy0, PW + 2 * RF, PH + 2 * RF), tpl_f))
    return fx0 + lx + dx, fy0 + ly + dy, sc


if AIM:
    ref, ex0, ey0 = int(AIM[0]), float(AIM[1]), float(AIM[2])
else:
    tops = np.array([o['top'] for o in A])
    ref = int(np.argmin(np.abs(tops - np.median(tops)) + 1e-3 * np.arange(n)))      # an upright frame (median head height)
    ex0, ey0 = A[ref]['ex'], A[ref]['ey']
bias = (ex0 - A[ref]['ex'], ey0 - A[ref]['ey'])    # AIM vs alpha estimate: keeps the guard rail consistent
bx, by = int(round(ex0 * kx - OX)), int(round(ey0 * ky - OY))
offx, offy = ex0 * kx - bx, ey0 * ky - by
out, fallbacks = [None] * n, 0
for order in (range(ref, n), range(ref - 1, -1, -1)):
    tpl_f = cut(fine_p[ref], PAD, bx, by, PW, PH).copy()
    px, py = bx, by
    for i in order:
        tpl_c = tpl_f[:PHc * COARSE, :PWc * COARSE].reshape(PHc, COARSE, PWc, COARSE).mean(axis=(1, 3))
        fx, fy, sc = match(i, tpl_f, tpl_c, px, py)
        ex, ey = (fx + offx) / kx, (fy + offy) / ky
        gx, gy = A[i]['ex'] + bias[0], A[i]['ey'] + bias[1]
        if sc < MIN_SCORE or np.hypot(ex - gx, ey - gy) > GUARD * HEAD_W:
            ex, ey = gx, gy
            fallbacks += 1
        else:
            px, py = int(round(fx)), int(round(fy))
            tpl_f = .92 * tpl_f + .08 * cut(fine_p[i], PAD, px, py, PW, PH)       # follow slow changes of expression / light
        out[i] = {'eye_x': round(float(ex), 2), 'eye_y': round(float(ey), 2), 'score': round(sc, 3),
                  'alpha_eye_x': round(gx, 1), 'alpha_eye_y': round(gy, 1)}

os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
json.dump({'frames': n, 'head_w': round(HEAD_W, 1), 'eye_k': EYE_K, 'ref_frame': ref, 'aim': list(AIM) if AIM else None,
           'fallbacks': fallbacks, 'track': out}, open(os.path.join(HERE, 'work/headtrack.json'), 'w'))

# ---------------------------------------------------------------- check sheet: look at it
picks = sorted(set([ref] + [round(k * (n - 1) / 7) for k in range(8)]))
sel = '+'.join(f'eq(n\\,{p})' for p in picks)
tiles = decode(['-i', plate_src, '-vf', f"select='{sel}'", '-fps_mode', 'passthrough'], 1080, 1920, 'rgb24')
TS, COLS = 420, 5                                   # every tile is a crop of 3 head widths around the tracked point
sheet = Image.new('RGB', (TS * COLS, TS * -(-len(picks) // COLS)), '#111')
for k, p in enumerate(picks):
    x, y, half = out[p]['eye_x'], out[p]['eye_y'], 1.5 * HEAD_W
    im = Image.fromarray(tiles[k]).crop((int(x - half), int(y - half), int(x + half), int(y + half))).resize((TS, TS), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    c, r = TS / 2, TS / 6
    d.line([(c - r, c), (c + r, c)], fill=(0, 255, 255), width=2)
    d.line([(c, c - r * .6), (c, c + r * .6)], fill=(0, 255, 255), width=2)
    d.ellipse([c - 5, c - 5, c + 5, c + 5], outline=(255, 255, 0), width=2)
    d.rectangle([0, 0, 170, 24], fill=(0, 0, 0))
    d.text((6, 6), f'f{p}{" (ref)" if p == ref else ""}  score {out[p]["score"]:.2f}', fill=(255, 255, 255))
    sheet.paste(im, (TS * (k % COLS), TS * (k // COLS)))
sheet.save(os.path.join(HERE, 'work/track_check.jpg'), quality=88)

ex = np.array([o['eye_x'] for o in out]); ey = np.array([o['eye_y'] for o in out])
print(f'{n} frames  head width {HEAD_W:.0f}px  ref frame {ref}{" (AIM)" if AIM else ""}  eye x {ex.min():.0f}-{ex.max():.0f}  '
      f'y {ey.min():.0f}-{ey.max():.0f}  min score {min(o["score"] for o in out):.2f}  alpha fallbacks {fallbacks}/{n}')
if clipped > n * .2 and not AIM:
    print('!! the top of their head touches the frame edge in many frames: the automatic eye estimate is unreliable here.\n'
          '   Set AIM = (frame, x, y) in the CLIP block of build.py (the point between their eyes) and run track.py again.')
if fallbacks > n * .25:
    print('!! more than a quarter of the frames fell back to the alpha estimate: look at work/track_check.jpg, set AIM if the\n'
          '   cross is off, or expect a looser lock (raise FOLLOW in the CLIP block).')
print('look at work/track_check.jpg: the cross must sit between their eyes in every tile')
