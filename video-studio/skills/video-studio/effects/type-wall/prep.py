#!/usr/bin/env python3
"""type-wall / prep.py: measure the speaker from the cutout so build.py can place the wall without typed pixels.

Run from the slot folder with the skill's Python (PY) (numpy, scipy, Pillow):
    PY prep.py

Reads  assets/subject.webm (alpha), assets/aroll.mp4, clip.json
Writes work/measure.json  head top / head centre, where the speaker is on every 4th line (union over the whole slot),
                          how much wall is left, camera drift, stray cutout blobs, plain-language warnings
       work/measure.jpg   half-size frame with a 100 px grid (labels are full-size px), the head-top line in yellow
                          and everything the speaker ever covers tinted. Read KEEP polygon points off this image.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

FF = shutil.which('ffmpeg') or 'ffmpeg'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
W, H, S = 1080, 1920, 4                     # measure at quarter size
SW, SH = W // S, H // S
if not os.path.exists('assets/subject.webm'):
    sys.exit('assets/subject.webm is missing: this effect needs the cutout. Make the slot without --no-cutout, or run '
             '_shared/rvm_cut.py on the slot folder.')
N = json.load(open('clip.json'))['frames']


def gray(path, vf, w, h, vp9=False):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if vp9 else []) + ['-i', path, '-vf', vf, '-f', 'rawvideo',
                                                                            '-pix_fmt', 'gray', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw[:len(raw) // (w * h) * (w * h)], np.uint8).reshape(-1, h, w)


alpha = gray('assets/subject.webm', f'alphaextract,scale={SW}:{SH}:flags=area', SW, SH, vp9=True)
n = len(alpha)
warn = []
if n != N:
    warn.append(f'cutout has {n} frames, the a-roll has {N}: the cutout will drift. Re-cut it.')

tops, cxs, hws, areas, strays = [], [], [], [], []
union = np.zeros((SH, SW), bool)
for k in range(n):
    m = alpha[k] > 96
    lab, cnt = ndimage.label(m)
    if cnt == 0:
        continue
    sizes = np.bincount(lab.ravel())[1:]
    main = int(np.argmax(sizes)) + 1
    for j, a in enumerate(sizes):           # anything else of real size is not the speaker (a face in a picture, a lamp)
        if j + 1 != main and a > sizes[main - 1] * .02:
            cy, cx = ndimage.center_of_mass(lab == j + 1)
            strays.append((k, int(cx * S), int(cy * S), int(a * S * S)))
    p = lab == main
    union |= m
    rows = np.where(p.sum(1) >= 3)[0]
    top = int(rows[0])
    band = p[top:top + 40]                  # the first 160 px under the top of the speaker's head
    xs = np.where(band.any(0))[0]
    tops.append(top * S)
    cxs.append(float(np.median(np.where(band)[1])) * S)
    hws.append(int(xs[-1] - xs[0] + 1) * S)
    areas.append(p.mean())
if not tops:
    sys.exit('the cutout is empty: nobody was found in this clip.')

head_top_min, head_top_med = int(min(tops)), int(np.median(tops))
head_x = int(np.median(cxs))
cover = float(np.median(areas))
union = ndimage.binary_dilation(union, iterations=2)
spans = {}
for y in range(SH):
    xs = np.where(union[y])[0]
    if len(xs) == 0:
        continue
    cuts = np.where(np.diff(xs) > 1)[0]
    starts = [xs[0]] + [xs[c + 1] for c in cuts]
    ends = [xs[c] for c in cuts] + [xs[-1]]
    spans[str(y * S)] = [[int(a * S), int((b + 1) * S)] for a, b in zip(starts, ends)]
shoulder = min(SH, (head_top_med + 2 * int(np.median(hws))) // S)       # roughly down to the speaker's chest
clear_top = float(1 - union[:shoulder].mean())

# camera drift: background of the first, middle and last frame, best whole-pixel shift at half size
HW, HH = W // 2, H // 2
pick = sorted({0, n // 2, n - 1})
sel = '+'.join(f'eq(n\\,{i})' for i in pick)
fr = gray('assets/aroll.mp4', f"select='{sel}',scale={HW}:{HH}:flags=area", HW, HH).astype(np.float32)
bg = ~ndimage.binary_dilation(np.kron(union, np.ones((2, 2), bool)), iterations=12)
bg[:40] = bg[-40:] = False
bg[:, :40] = bg[:, -40:] = False
drift = 0.0


def best_shift(a, b, ok, around, reach, R):
    """whole-pixel shift of b against a (background pixels only), searched `reach` px around a first guess"""
    core = ok[R:-R, R:-R].astype(np.float32)
    a0 = a[R:-R, R:-R]
    hh, ww = a.shape
    best = (1e9, 0, 0)
    for dy in range(around[1] - reach, around[1] + reach + 1):
        for dx in range(around[0] - reach, around[0] + reach + 1):
            d = float((np.abs(b[R + dy:hh - R + dy, R + dx:ww - R + dx] - a0) * core).sum())
            if d < best[0]:
                best = (d, dx, dy)
    return best[1], best[2]


if bg.mean() > .04 and len(fr) > 1:
    for f in fr[1:]:                             # coarse to fine: 80 px reach at 1/8 size, then 1/4, then 2 px steps
        cx, cy = best_shift(fr[0][::4, ::4], f[::4, ::4], bg[::4, ::4], (0, 0), 10, 11)
        cx, cy = best_shift(fr[0][::2, ::2], f[::2, ::2], bg[::2, ::2], (2 * cx, 2 * cy), 2, 24)
        dx, dy = best_shift(fr[0], f, bg, (2 * cx, 2 * cy), 2, 48)
        drift = max(drift, 2 * float(np.hypot(dx, dy)))
else:
    warn.append('almost no background visible: camera drift could not be measured.')

if head_top_min < 190:
    warn.append(f'their head top reaches y {head_top_min}: there is no room for a row of words above the speaker. '
                'This framing is too tight for a type wall (try FS 150, or pick another effect).')
if clear_top < .40:
    warn.append(f'only {clear_top:.0%} of the picture around their head is open wall: the words will mostly hide behind the speaker.')
if drift > 8:
    warn.append(f'the camera moves about {drift:.0f} px during the slot. A KEEP shape needs a locked camera: it would '
                'come unstuck from the furniture by that much. With KEEP = [] one slow drift is fine, but handheld '
                'shake makes the speaker wobble on the locked wall like a sticker: use a still shot or another effect.')
if strays:
    ks = sorted({s[0] for s in strays})
    _, sx, sy, sa = max(strays, key=lambda s: s[3])
    warn.append(f'the cutout holds a second shape on {len(ks)} frame(s), frames {ks[0]} to {ks[-1]} (biggest near x {sx}, '
                f'y {sy}, about {sa} px): a hand coming into frame, or a face in a picture or poster. It will float on '
                'the wall. Look at those frames in the render.')

os.makedirs('work', exist_ok=True)
json.dump({'frames': n, 'head_top_min': head_top_min, 'head_top_med': head_top_med, 'head_x': head_x,
           'head_w': int(np.median(hws)), 'cover': round(cover, 3), 'clear_top': round(clear_top, 3),
           'drift_px': round(drift, 1), 'strays': strays[:20], 'warnings': warn, 'spans': spans},
          open('work/measure.json', 'w'))

# picture to read coordinates from: the frame where the speaker's head is highest
k = int(np.argmin(tops))
raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n\\,{k})',scale={HW}:{HH}",
                      '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
img = np.frombuffer(raw, np.uint8).reshape(HH, HW, 3).astype(np.float32)
u2 = np.kron(union, np.ones((2, 2), bool))
img[u2] = img[u2] * .7 + np.array([40, 110, 160], np.float32) * .3
im = Image.fromarray(img.astype(np.uint8))
d = ImageDraw.Draw(im)
for v in range(100, H, 100):
    d.line([(0, v // 2), (HW, v // 2)], fill=(255, 255, 255) if v % 500 == 0 else (150, 150, 150), width=1)
    d.text((4, v // 2 + 2), str(v), fill=(255, 255, 255))
for v in range(100, W, 100):
    d.line([(v // 2, 0), (v // 2, HH)], fill=(255, 255, 255) if v % 500 == 0 else (150, 150, 150), width=1)
    d.text((v // 2 + 3, 4), str(v), fill=(255, 255, 255))
d.line([(0, head_top_min // 2), (HW, head_top_min // 2)], fill=(250, 230, 122), width=3)
im.save('work/measure.jpg', quality=88)

print(f'{n} frames. Head top y {head_top_min} (highest) / {head_top_med} (usual), head centre x {head_x}. '
      f'The speaker covers {cover:.0%} of the frame; {clear_top:.0%} of the picture around their head is open wall. '
      f'Camera drift {drift:.0f} px.')
for w in warn:
    print('  !! ' + w)
print('wrote work/measure.json and work/measure.jpg' + ('' if warn else '  (footage looks right for a type wall)'))
