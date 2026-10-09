#!/usr/bin/env python3
"""spotlight check, after the render (numpy and Pillow), from the slot folder:
    python check.py
1. frame count of the render against clip.json
2. the frames that must be plain footage (first frame, the frame before the lights move, a frame after the release,
   the last frame) compared with the a-roll. Frame 0 is the reference (nothing can be on screen yet): the others
   must differ from the a-roll by the same small amount and the same colour offset as frame 0 does
3. how dark the room got and how much colour it kept (it must never read as grey)
4. work/final_sheet.jpg: six frames of the final mp4.  work/final_edge.jpg: FULL SIZE crops from the final mp4 in
   the darkest moment, on the head / hair and on the fastest moving edge (the hand). LOOK at both.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import build as B

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
N = json.load(open('clip.json'))['frames']
M = json.load(open('work/measure.json'))
mp4 = f'renders/{os.path.basename(HERE)}.mp4'
if not os.path.exists(mp4):
    sys.exit(f'no {mp4}: render first')
END = B.end_frame(N)


def grab(path, frames, w, h, fmt='rgb24'):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={w}:{h}", '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', fmt, '-'], capture_output=True).stdout
    c = 3 if fmt == 'rgb24' else 1
    return np.frombuffer(raw, np.uint8)[:len(frames) * w * h * c].reshape(len(frames), h, w, c)


got = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', mp4], capture_output=True, text=True).stdout.strip() or 0)
bad = got != N
print(f'frames: {got} (clip.json {N})  ' + ('ok' if got == N else '!! WRONG FRAME COUNT'))
plain = sorted({0, B.F_IN - 1} | ({END + 3, N - 1} if B.F_OUT is not None else set()))
a, b = grab(mp4, plain, 270, 480).astype(float), grab('assets/aroll.mp4', plain, 270, 480).astype(float)
base = None
for i, f in enumerate(plain):
    off = (a[i] - b[i]).mean((0, 1))                 # a constant colour offset is the render pipeline, not the effect
    d = float(np.abs(a[i] - b[i] - off).mean())
    if base is None:
        base, ok = (off, d), d < 6
    else:
        ok = d < base[1] + 1.0 and float(np.abs(off - base[0]).max()) < 1.5
    bad |= not ok
    print(f'plain frame f{f:4d}: difference {d:5.2f}, colour offset {np.round(off, 1)}  ' + ('ok' if ok else '!! NOT plain footage'))
if B.F_OUT is None:
    print('F_OUT is None: the room is still dark on the last frame, the reel has to cut there')

hair_f, hand_f = M['check']['hair'][0], M['check']['hand'][0]
dk = grab(mp4, [hair_f], 270, 480)[0].astype(float)
pl = grab('assets/aroll.mp4', [hair_f], 270, 480)[0].astype(float)
corner = np.r_[dk[:120, :40].reshape(-1, 3), dk[:120, -40:].reshape(-1, 3)]
corner0 = np.r_[pl[:120, :40].reshape(-1, 3), pl[:120, -40:].reshape(-1, 3)]
chroma = float((corner.max(1) - corner.min(1)).mean())
print(f'darkest frame f{hair_f}: top corners at {corner.mean() / max(1, corner0.mean()) * 100:.0f}% of the plain picture, '
      f'colour spread {chroma:.1f} ' + ('ok (keeps colour)' if chroma >= 4 else '!! reads as grey / black: raise DARK'))

end = B.F_OUT if B.F_OUT is not None else N - 1
pick = sorted({B.F_IN - 1, B.F_IN + 2, hair_f, hand_f, min(N - 1, end + 2), N - 1})
t = grab(mp4, pick, 180, 320)
sheet = Image.new('RGB', (180 * len(pick), 320))
for i, f in enumerate(pick):
    im = Image.fromarray(t[i])
    ImageDraw.Draw(im).text((5, 5), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, (180 * i, 0))
sheet.save('work/final_sheet.jpg', quality=88)
cw, ch = M['check']['crop']
edge = Image.new('RGB', (cw * 2 + 8, ch + 30), (20, 20, 20))
d = ImageDraw.Draw(edge)
for i, key in enumerate(('hair', 'hand')):
    f, x0, y0 = M['check'][key]
    full = Image.fromarray(grab(mp4, [f], 1080, 1920)[0])
    edge.paste(full.crop((x0, y0, x0 + cw, y0 + ch)), (i * (cw + 8), 30))
    d.text((i * (cw + 8) + 6, 9), f'{"head / hair" if key == "hair" else "fastest moving edge (hand)"}  f{f}  final mp4 1:1', fill=(255, 255, 0))
edge.save('work/final_edge.jpg', quality=95)
print('look at: work/final_sheet.jpg, work/final_edge.jpg')
sys.exit(1 if bad else 0)
