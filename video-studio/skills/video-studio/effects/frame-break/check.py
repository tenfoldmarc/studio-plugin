#!/usr/bin/env python3
"""frame-break check, after the render (any python with numpy and Pillow), from the slot folder:
    python check.py
1. the frames that must be plain footage (first frame, last frame before the shrink, F_OUT, last frame) are compared
   with the a-roll: prints the mean difference per frame (0 to 255; under 3 is encoder noise, more = something is left on)
2. writes work/final_sheet.jpg: six frames of the final mp4 side by side (before, mid-shrink, landed, floating,
   growing back, after). LOOK at it, then at one frame at full size for the outline of the head and hands.
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
F_IN, F_OUT = C['F_IN'], C['F_OUT']
A0 = F_IN - 21
mp4 = f'renders/{os.path.basename(HERE)}.mp4'
if not os.path.exists(mp4):
    sys.exit(f'no {mp4}: render first')


def grab(path, frames, w, h, fmt):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={w}:{h}", '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', fmt, '-'], capture_output=True).stdout
    c = 3 if fmt == 'rgb24' else 1
    return np.frombuffer(raw, np.uint8)[:len(frames) * w * h * c].reshape(len(frames), h, w, c)


plain = sorted({0, A0 - 1} | ({F_OUT, N - 1} if F_OUT is not None else set()))
a, b = grab(mp4, plain, 270, 480, 'gray').astype(float), grab('assets/aroll.mp4', plain, 270, 480, 'gray').astype(float)
bad = False
for i, f in enumerate(plain):
    d = float(np.abs(a[i] - b[i]).mean())
    bad |= d >= 3
    print(f'plain frame f{f:4d}: mean difference {d:5.2f}  ' + ('ok' if d < 3 else '!! NOT plain footage'))
if F_OUT is None:
    print('F_OUT is None: the card is still on screen on the last frame, the reel has to cut there')
end = F_OUT if F_OUT is not None else N - 1
pick = sorted({A0 - 1, A0 + 12, F_IN, (F_IN + end) // 2, max(F_IN, end - 6), end})
t = grab(mp4, pick, 180, 320, 'rgb24')
sheet = Image.new('RGB', (180 * len(pick), 320))
for i, f in enumerate(pick):
    im = Image.fromarray(t[i])
    ImageDraw.Draw(im).text((5, 5), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, (180 * i, 0))
sheet.save('work/final_sheet.jpg', quality=88)
print('sheet: work/final_sheet.jpg')
sys.exit(1 if bad else 0)
