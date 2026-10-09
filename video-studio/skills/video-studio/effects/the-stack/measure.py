#!/usr/bin/env python3
"""Measure the speaker's head from the cutout alpha, so build.py can crop the speaker window around it.

  python measure.py        (any python with numpy and Pillow; run from the slot folder)

Reads assets/subject.webm (only its alpha: the cutout is never drawn by this effect) and assets/aroll.mp4.
Writes work/head.json  {top, cx, width, chin_ratio, track_top, track_cx, ...} in 1080x1920 px (the track is the
smoothed position of their head on every frame, used when FOLLOW is on), and the check picture work/head.jpg: the
middle frame at half size with the measured head box in cyan and the chin line in yellow. LOOK at it. If the
box is not on their head (raised hands, a hood, two people), type HEAD = (top, centre_x, width) in build.py instead.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
SW, SH, K = 270, 480, 4          # alpha is read at quarter size
STEP = 2                         # every 2nd frame

if not os.path.exists('assets/subject.webm'):
    sys.exit('assets/subject.webm is missing: make the slot without --no-cutout (or run _shared/rvm_cut.py on it), '
             'or type HEAD = (top, centre_x, width) in build.py and skip this script')
raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                      f"select='not(mod(n\\,{STEP}))',alphaextract,scale={SW}:{SH}:flags=area", '-fps_mode',
                      'passthrough', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
frames = np.frombuffer(raw, np.uint8).reshape(-1, SH, SW) > 128
if not len(frames):
    sys.exit('could not read the alpha of assets/subject.webm')


def head_of(mask):
    """(top, centre x, width, chin y, neck found) of the head in one quarter-size alpha frame, or None."""
    rw = mask.sum(1)
    ys = np.where((rw >= 4) & (np.roll(rw, -1) >= 4) & (np.roll(rw, -2) >= 4))[0]
    if not len(ys):
        return None
    y0 = int(ys[0])
    xs = np.where(mask[y0])[0]
    cx = float(np.median(xs))
    widest, centres, first = 0, [], None
    for y in range(y0, SH):
        row = mask[y]
        xs = np.where(row)[0]
        if not len(xs):
            break
        # the run of cutout pixels that holds (or is nearest to) the head centre: raised hands are other runs
        cuts = np.where(np.diff(xs) > 2)[0]
        runs = np.split(xs, cuts + 1)
        run = min(runs, key=lambda r: 0 if r[0] <= cx <= r[-1] else min(abs(r[0] - cx), abs(r[-1] - cx)))
        w = len(run)
        if first is None:
            widest = max(widest, w)
            if y - y0 >= 0.7 * widest and w <= 0.80 * widest:
                first, neck_w, neck_y = y, w, y             # the face has narrowed to 80% of the widest row
            cx = 0.7 * cx + 0.3 * (run[0] + run[-1]) / 2
            centres.append((run[0] + run[-1]) / 2)
            if y - y0 > 0.5 * SH:
                break
        else:
            if w < neck_w:
                neck_w, neck_y = w, y                       # narrowest row so far: the neck
            if w >= 1.1 * widest or y - first > 1.2 * widest:
                break                                       # shoulders
    if first is not None:                                   # the chin sits about two thirds of the way to the neck
        return y0, float(np.mean(centres)), widest, first + 0.65 * (neck_y - first), True
    # no neck (hood, long hair, very tight framing): head width from the rows just under the top
    band = [int(mask[y].sum()) for y in range(y0 + 6, min(SH, y0 + int(0.12 * SH)))] or [widest]
    hw = float(np.median(band))
    return y0, float(np.mean(centres[:max(1, int(hw))])) if centres else cx, hw, y0 + 1.4 * hw, False


per = [head_of(m) for m in frames]
idx = [i for i, h in enumerate(per) if h and h[2] >= 6]
got = [per[i] for i in idx]
if len(got) < max(2, len(frames) // 4):
    sys.exit('the cutout is empty on most frames: check assets/subject.webm, or type HEAD in build.py')
tops = np.array([g[0] for g in got], float)
cxs = np.array([g[1] for g in got], float)
hws = np.array([g[2] for g in got], float)
chins = np.array([(g[3] - g[0]) / g[2] for g in got], float)
necks = sum(1 for g in got if g[4])
top = float(np.percentile(tops, 5)) * K          # the highest the speaker gets (so the window never cuts the speaker's head)
cx = float(np.median(cxs)) * K
hw = float(np.median(hws)) * K
# Chin: the silhouette narrows at the jaw, but a collar or hunched shoulders often hide the neck, so the measured
# value is only trusted when it is LOWER than a normal head (1.5 x its width). Too low is the safe side: the
# caption band sits under it.
ratio = float(np.clip(np.median(chins), 1.5, 1.9))
n = json.load(open('clip.json'))['frames'] if os.path.exists('clip.json') else len(frames) * STEP


def path(vals):
    """per-frame smooth path (1080 px) through the measured frames: holes filled, 0.4 s gaussian"""
    full = np.interp(np.arange(n), np.array(idx) * STEP, vals * K)
    k = np.exp(-0.5 * (np.arange(-15, 16) / 5.0) ** 2)
    return np.convolve(np.pad(full, 15, mode='edge'), k / k.sum(), mode='valid')


p_top, p_cx = path(tops), path(cxs)
out = {'top': round(top), 'cx': round(cx), 'width': round(hw), 'chin_ratio': round(ratio, 2),
       'neck_found': round(necks / len(got), 2), 'frames_measured': len(got),
       'top_range': [round(float(tops.min()) * K), round(float(tops.max()) * K)],
       'cx_range': [round(float(cxs.min()) * K), round(float(cxs.max()) * K)],
       # FOLLOW: where the top of the speaker's head and its centre are on every frame, smoothed
       'track_top': [round(float(v), 1) for v in p_top], 'track_cx': [round(float(v), 1) for v in p_cx]}
os.makedirs('work', exist_ok=True)
json.dump(out, open('work/head.json', 'w'))

mid = n // 2
png = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n\\,{mid})',scale=540:960",
                      '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'png', '-'], capture_output=True).stdout
if png:
    import io
    im = Image.open(io.BytesIO(png)).convert('RGB')
    d = ImageDraw.Draw(im)
    mx, my = float(p_cx[mid]), float(p_top[mid])            # where the smoothed path puts the speaker's head on this frame
    x0, x1, y0, y1 = (mx - hw / 2) / 2, (mx + hw / 2) / 2, my / 2, (my + ratio * hw) / 2
    cx_line = mx
    d.rectangle([x0, y0, x1, y1], outline=(0, 230, 255), width=3)
    d.line([x0 - 30, y1, x1 + 30, y1], fill=(255, 235, 60), width=3)
    d.line([cx_line / 2, y0 - 16, cx_line / 2, y1 + 16], fill=(0, 230, 255), width=1)
    im.save('work/head.jpg', quality=88)
print(f"head: top {out['top']}  centre x {out['cx']}  width {out['width']}  chin at top + {out['chin_ratio']} x width"
      f"  (neck found on {necks}/{len(got)} frames)")
print(f"moves: top {out['top_range'][0]} to {out['top_range'][1]}, centre x {out['cx_range'][0]} to {out['cx_range'][1]}")
if necks < len(got) * 0.5:
    print('!! no clear neck on most frames: the width is a guess. Check work/head.jpg, or type HEAD in build.py')
if out['cx_range'][1] - out['cx_range'][0] > 1.2 * hw:
    print('!! the speaker moves sideways by more than a head: the window crop is fixed, so the speaker will wander inside it')
print('wrote work/head.json and work/head.jpg (cyan box = head, yellow line = chin). Look at the picture.')
