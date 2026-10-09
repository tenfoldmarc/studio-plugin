#!/usr/bin/env python3
"""sticker check, after the render (any python with numpy and Pillow), from the slot folder:
    python check.py
1. the frames that must be plain footage (frame 0, the frame before F_FREEZE, and with F_OUT: F_OUT and the last frame)
   are compared with the a-roll: mean difference per frame after taking out any uniform level shift (0 to 255;
   under 3 is encoder noise, more = something is on)
2. writes work/final_sheet.jpg (six frames of the final mp4: before, freeze, landed, notes on, late, last) and
   work/final_edge.jpg (the landed sticker's head and shoulders at full size: judge the border around hair and hands)
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
C = {}
exec(open('build.py').read().split('# ==== CLIP (edit this) ====')[1].split('# ==== END CLIP ====')[0], C)
N = json.load(open('clip.json'))['frames']
F, F_OUT = C['F_FREEZE'], C['F_OUT']
mp4 = f'renders/{os.path.basename(HERE)}.mp4'
if not os.path.exists(mp4):
    sys.exit(f'no {mp4}: render first')


def grab(path, frames, w, h, fmt):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={w}:{h}", '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', fmt, '-'], capture_output=True).stdout
    c = 3 if fmt == 'rgb24' else 1
    return np.frombuffer(raw, np.uint8)[:len(frames) * w * h * c].reshape(len(frames), h, w, c)


plain = sorted({0, F - 1} | ({F_OUT, N - 1} if F_OUT is not None else set()))
a, b = grab(mp4, plain, 270, 480, 'gray').astype(float), grab('assets/aroll.mp4', plain, 270, 480, 'gray').astype(float)
bad = False
for i, f in enumerate(plain):
    lvl = float((a[i] - b[i]).mean())          # a uniform level shift is the renderer's colour handling, not the effect
    d = float(np.abs(a[i] - b[i] - lvl).mean())
    bad |= d >= 3
    print(f'plain frame f{f:4d}: mean difference {d:5.2f}  ' + ('ok' if d < 3 else '!! NOT plain footage')
          + (f'   (whole frame {lvl:+.1f} levels: full-range phone footage through the renderer, same on every slot)' if abs(lvl) > 1.5 else ''))
if F_OUT is None:
    print('F_OUT is None: the sticker is still on screen on the last frame, the reel has to end or cut there')
end = F_OUT - 8 if F_OUT is not None else N - 1
pick = sorted({F - 1, F, min(F + 6, end), min(F + 16, end), (F + 16 + end) // 2, end})
t = grab(mp4, pick, 180, 320, 'rgb24')
sheet = Image.new('RGB', (180 * len(pick), 320))
for i, f in enumerate(pick):
    im = Image.fromarray(t[i])
    ImageDraw.Draw(im).text((5, 5), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, (180 * i, 0))
sheet.save('work/final_sheet.jpg', quality=88)
M = json.load(open('assets/sticker/sticker.json'))
x0, y0, x1, y1 = M['head_screen']
hw, hh = x1 - x0, y1 - y0
box = (max(0, int(x0 - .9 * hw)), max(0, int(y0 - .25 * hh)), min(1080, int(x1 + .9 * hw)), min(1920, int(y1 + .8 * hh)))
Image.fromarray(grab(mp4, [min(F + 16, end)], 1080, 1920, 'rgb24')[0]).crop(box).save('work/final_edge.jpg', quality=92)
print('sheet: work/final_sheet.jpg   border at full size: work/final_edge.jpg')
sys.exit(1 if bad else 0)
