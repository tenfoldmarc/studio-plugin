#!/usr/bin/env python3
"""clone / check: QA on the FINAL render (never on snapshots) + the phone copy.

    PY check.py              checks renders/<slot folder>.mp4
    PY check.py other.mp4

Prints  frame count vs clip.json, and per frame how much of the picture differs from the a-roll: it must be ~0 before
        the first pop and after the exit, step up once per clone, and spike only on the payoff frame.
Writes  work/check/sheet_*.jpg   contact sheets: every pop frame by frame, the payoff, the exit, the last frame
        work/check/crop_*.jpg    1:1 crops of every clone at rest (edges, shadow, furniture line)
        renders/<slot>-phone.mp4 720x1280 crf 27 preview
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import build as C

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
SLOT = os.path.basename(HERE)
MP4 = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'renders', f'{SLOT}.mp4')
OUT = os.path.join(HERE, 'work/check')
os.makedirs(OUT, exist_ok=True)
N = C.N


def gray(p):
    raw = subprocess.run([FF, '-v', 'error', '-i', p, '-vf', 'scale=270:480:flags=area', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 480, 270).astype(np.float32)


def frames(p, fl):
    fl = sorted(set(int(min(max(f, 0), N - 1)) for f in fl))
    sel = '+'.join(f'eq(n\\,{f})' for f in fl)
    raw = subprocess.run([FF, '-v', 'error', '-i', p, '-vf', f'select={sel}', '-vsync', '0', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return fl, np.frombuffer(raw, np.uint8).reshape(-1, 1920, 1080, 3)


def sheet(name, fl, crop=None, cols=6):
    fl, A = frames(MP4, fl)
    tiles = []
    for f, a in zip(fl, A):
        im = Image.fromarray(a)
        im = im.crop(crop) if crop else im.resize((360, 640), Image.LANCZOS)
        ImageDraw.Draw(im).text((6, 4), f'f{f} {f / 30:.2f}s', fill=(255, 60, 60))
        tiles.append(im)
    cols = min(cols, len(tiles))
    tw, th = tiles[0].size
    sh = Image.new('RGB', (cols * tw, ((len(tiles) + cols - 1) // cols) * th), (20, 20, 20))
    for k, t in enumerate(tiles):
        sh.paste(t, ((k % cols) * tw, (k // cols) * th))
    p = os.path.join(OUT, name)
    sh.save(p, quality=90)
    print('  ', p, sh.size)


R, A = gray(MP4), gray(os.path.join(HERE, 'assets/aroll.mp4'))
print(f'frames: render {len(R)}, a-roll {len(A)}, clip.json {N}' + ('  OK' if len(R) == len(A) == N else '   !! MISMATCH'))
pops = {C.f_in(c): c['id'] for c in C.CLONES}
first = min(pops)
changed = [float((np.abs(R[f] - A[f]) > 14).mean()) for f in range(min(len(R), len(A)))]
luma = [float(R[f].mean() - A[f].mean()) for f in range(min(len(R), len(A)))]
caps = os.path.exists(os.path.join(HERE, 'index.html')) and 'class="cap' in open(os.path.join(HERE, 'index.html')).read()
print('changed share of the picture vs a-roll (captions count too):')
for f in range(len(changed)):
    note = ''
    if f in pops:
        note = f'  <- clone {pops[f]} pop starts'
    if C.SYNC_F is not None and f == C.SYNC_F:
        note = '  <- payoff (flash + punch expected)'
    if C.EXIT_F is not None and f == C.EXIT_F:
        note = '  <- exit starts'
    step = changed[f] - changed[f - 1] if f else 0
    odd = abs(step) > .05 and not (C.SYNC_F is not None and C.SYNC_F <= f <= C.SYNC_F + 6)
    if note or odd or f % 10 == 0 or f == len(changed) - 1:
        print(f'  f{f:3d}  changed {changed[f]:.3f}  luma {luma[f]:+5.1f}{note}' + ('   !! unexplained jump, look at this frame' if odd else ''))
if not caps:
    pre = max(changed[:max(first - 1, 1)])
    print(f'before the first pop: max changed {pre:.4f}' + ('  OK (plate untouched)' if pre < .004 else '   !! something shows before the pop'))
    if C.EXIT_F is not None:
        post = max(changed[min(C.EXIT_F + 12, N - 1):])
        print(f'after the exit: max changed {post:.4f}' + ('  OK (hands back to the a-roll)' if post < .004 else '   !! clones or flash still visible at the end'))

print('contact sheets:')
for c in C.CLONES:
    f0 = C.f_in(c)
    sheet(f"sheet_pop_{c['id']}.jpg", range(f0 - 1, f0 + 11))
    x0, y0, w, h = C.canvas(c)
    rest = [f0 + 14, (f0 + (C.SYNC_F or N - 1)) // 2, min(N - 1, (C.EXIT_F or N) - 3)]
    cw = min(w, 600)
    cx = int(min(max(c['x'] - cw // 2, 0), 1080 - cw))
    sheet(f"crop_{c['id']}.jpg", rest, crop=(cx, y0, cx + cw, y0 + h), cols=3)
if C.SYNC_F is not None:
    sheet('sheet_payoff.jpg', range(C.SYNC_F - 3, C.SYNC_F + 9))
if C.EXIT_F is not None:
    sheet('sheet_exit.jpg', range(C.EXIT_F - 2, C.EXIT_F + 16))
sheet('sheet_overview.jpg', [round(k * (N - 1) / 11) for k in range(12)])

phone = os.path.join(os.path.dirname(MP4), os.path.splitext(os.path.basename(MP4))[0] + '-phone.mp4')
subprocess.run([FF, '-v', 'error', '-y', '-i', MP4, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27', '-preset', 'slow',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', phone], check=True)
print('phone copy:', phone)
print('now LOOK at the sheets: pop lands on the word, their face never covered, clone edges clean, nothing cut by the frame edge')
