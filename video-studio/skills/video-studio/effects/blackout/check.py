#!/usr/bin/env python3
"""blackout check, after the render (numpy and Pillow), from the slot folder:
    python check.py
1. frame count of the render against clip.json
2. the frames that must be plain footage (first frame, the frame before the room dims, a frame after the snap, the
   last frame) compared with the a-roll. Frame 0 is the reference (nothing can be on screen yet): the others must
   differ from the a-roll by the same small amount and the same colour offset as frame 0 does
3. the room on the frame before the punch and on the last dim frame (how dim, and that it kept its colour), and the
   first plain frame after the snap
4. work/final_sheet.jpg: twelve frames of the final mp4 around the dim, the punch and the snap.
   work/final_edge.jpg: FULL SIZE crop of the head from the final mp4 while the room is dim. LOOK at both.
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
C = json.load(open('clip.json'))
N = C['frames']
M = json.load(open('work/measure.json'))
mp4 = f'renders/{os.path.basename(HERE)}.mp4'
if not os.path.exists(mp4):
    sys.exit(f'no {mp4}: render first')
SNAP = B.snap_frame(C)
END = B.end_frame(N, SNAP)


def grab(path, frames, w, h):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={w}:{h}", '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8)[:len(frames) * w * h * 3].reshape(len(frames), h, w, 3)


got = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', mp4], capture_output=True, text=True).stdout.strip() or 0)
bad = got != N
print(f'frames: {got} (clip.json {N})  ' + ('ok' if got == N else '!! WRONG FRAME COUNT'))
plain = sorted({0, B.F_DIM - 1} | ({END, min(N - 1, END + 2), N - 1} if SNAP is not None else set()))
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
if SNAP is None:
    print('F_SNAP is None: the room is still dim on the last frame, the reel has to cut there')

# the room = the top corners of the picture (never the speaker). Level against the a-roll, and its colour spread
last_dim = (SNAP if SNAP is not None else N) - 1
look = sorted({B.F_DIM, B.F_PUNCH - 1, last_dim})
dk, pl = grab(mp4, look, 270, 480).astype(float), grab('assets/aroll.mp4', look, 270, 480).astype(float)
corner = lambda x: np.r_[x[:120, :40].reshape(-1, 3), x[:120, -40:].reshape(-1, 3)]
for i, f in enumerate(look):
    c, c0 = corner(dk[i]), corner(pl[i])
    level, chroma = c.mean() / max(1, c0.mean()) * 100, float((c.max(1) - c.min(1)).mean())
    note = ''
    if f == B.F_DIM:
        note = 'first frame of the dim: ' + ('ok (barely moved)' if level > 90 else '!! already dark: the dim must start slowly')
        bad |= level <= 90
    elif chroma < 3 and float((c0.max(1) - c0.min(1)).mean()) >= 6:
        note = '!! reads as grey: raise DIM or lower COOL'
    elif f == last_dim:
        note = 'last dim frame: ' + ('ok (still dim, the lights come back on the next frame)' if level < 80 else '!! not dim')
        bad |= level >= 80
    print(f'room f{f:4d}: top corners at {level:3.0f}% of the plain picture, colour spread {chroma:.1f}  {note}')

pick = sorted({B.F_DIM - 1, B.F_DIM + B.DIM_FRAMES // 2, B.F_PUNCH - 1, B.F_PUNCH, B.F_PUNCH + 1, B.F_PUNCH + 3, B.F_PUNCH + 8,
               last_dim, min(N - 1, last_dim + 1), min(N - 1, last_dim + 3), min(N - 1, END), N - 1})
t = grab(mp4, pick, 180, 320)
cols = 6
sheet = Image.new('RGB', (180 * cols, 320 * -(-len(pick) // cols)))
for i, f in enumerate(pick):
    im = Image.fromarray(t[i])
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 40, 16), fill=(0, 0, 0))
    d.text((4, 3), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, (180 * (i % cols), 320 * (i // cols)))
sheet.save('work/final_sheet.jpg', quality=88)
f, (x0, y0), (cw, ch) = M['check']['frame'], M['check']['box'], M['check']['crop']
full = Image.fromarray(grab(mp4, [f], 1080, 1920)[0])
edge = full.crop((x0, y0, x0 + cw, y0 + ch))
ImageDraw.Draw(edge).text((6, 6), f'head / hair  f{f}  final mp4 1:1', fill=(255, 255, 0))
edge.save('work/final_edge.jpg', quality=95)
print('look at: work/final_sheet.jpg, work/final_edge.jpg')
sys.exit(1 if bad else 0)
