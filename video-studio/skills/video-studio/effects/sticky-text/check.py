#!/usr/bin/env python3
"""sticky-text / check.py: run after the render. Prints the numbers, writes the pictures to look at.

  work/check/sheet.jpg   4 frames from the final mp4 (landing, biggest head movement, middle, just before it leaves)
                         with the safe zone (red) and the measured brow / chin lines (blue) drawn on
  work/check/lock.jpg    6 crops re-centred on what the tag is glued to: the tag must sit at the same spot in each
  work/check/still_*.jpg full-size frames;  renders/<slot>-phone.mp4  720x1280 copy
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
SLOT = os.path.basename(HERE)
MP4 = os.path.join(HERE, 'renders', f'{SLOT}.mp4')
if not os.path.exists(MP4):
    sys.exit(f'no render at renders/{SLOT}.mp4')
LAY = json.load(open(os.path.join(HERE, 'work/layout.json')))
TR = json.load(open(os.path.join(HERE, 'work/track.json')))
FR, NF, HH, BROW = TR['frames'], LAY['frames'], LAY['hh'], LAY['brow']
OUT = os.path.join(HERE, 'work/check')
os.makedirs(OUT, exist_ok=True)


def read(path, w, h, pix='gray', pick=None):
    vf = (f"select='{'+'.join(f'eq(n\\,{f})' for f in pick)}'," if pick else '') + f'scale={w}:{h}'
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', vf, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', pix, '-'],
                         capture_output=True).stdout
    c = 1 if pix == 'gray' else 3
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, c).astype(np.int16)


# 1. frame count, and where the picture differs from the a-roll (the edges of the slot must be the plain picture)
a, b = read(MP4, 270, 480), read(os.path.join(HERE, 'assets/aroll.mp4'), 270, 480)
print(f'render: {len(a)} frames (slot {NF})' + ('' if len(a) == NF else '   !! FRAME COUNT MISMATCH'))
n = min(len(a), len(b))
d = np.abs(a[:n] - b[:n])[:, :, :, 0]
blk = d[:, :480, :256].reshape(n, 30, 16, 16, 16).mean((2, 4)).max((1, 2))        # worst 16 px block per frame
on = np.flatnonzero(blk > 12)
f_in = min(t['fL'] for t in LAY['tags'])
f_out = max(t['fEnd'] for t in LAY['tags'])
if on.size:
    print(f'picture differs from the a-roll on frames {on[0]}..{on[-1]} (tags planned {f_in}..{f_out}); '
          f'frame 0 diff {blk[0]:.1f}, last frame diff {blk[n - 1]:.1f} (under 12 = plain)')
    if on[0] < f_in - 1 or on[-1] > f_out + 1 or blk[0] > 12 or blk[n - 1] > 12:
        print('!! the slot does not hand back plain footage at an edge')
else:
    print('!! no tag visible anywhere in the render')

# 2. numbers from the layout: safe zone, face
for t in LAY['tags']:
    q = {int(f): np.array(v) for f, v in t['quads'].items()}
    xs, ys = np.concatenate([v[:, 0] for v in q.values()]), np.concatenate([v[:, 1] for v in q.values()])
    line = f'tag {t["i"]} "{t["text"]}" ({t["anchor"]}): x {xs.min():.0f}..{xs.max():.0f}  y {ys.min():.0f}..{ys.max():.0f}  (safe: x 35..1045, y 220..1470)'
    if t['anchor'] == 'cap':
        m = min(FR[f]['top'] + BROW * HH * FR[f]['s'] - v[:, 1].max() for f, v in q.items())
        line += f'   bottom edge stays {m:.0f} px above the brow line (worst frame)'
    if t['anchor'] == 'chest':
        m = min(v[:, 1].min() - FR[f]['top'] - HH * FR[f]['s'] for f, v in q.items())
        line += f'   top edge stays {m:.0f} px under the chin line (worst frame)'
    print(line)

# 3. pictures
t0 = LAY['tags'][0]
mv = min(max(TR['move_frame'], f_in + 3), f_out - 7)
pick = sorted({min(t0['fL'] + 5, NF - 1), mv, (t0['fL'] + t0['fO']) // 2, t0['fO'] - 2})
lockf = sorted({int(round(x)) for x in np.linspace(t0['fL'] + 8, t0['fO'] - 2, 6)})
allf = sorted(set(pick) | set(lockf))
rgb = dict(zip(allf, read(MP4, 1080, 1920, 'rgb24', allf).astype(np.uint8)))
tiles = []
for f in pick:
    im = Image.fromarray(rgb[f])
    dr = ImageDraw.Draw(im)
    for xy in ((0, 220, 1080, 220), (0, 1470, 1080, 1470), (35, 220, 35, 1470), (1045, 220, 1045, 1155), (980, 1155, 980, 1470), (980, 1155, 1045, 1155)):
        dr.line(xy, fill=(255, 40, 40), width=4)
    r = FR[f]
    for frac in (BROW, 1.0):
        y = r['top'] + frac * HH * r['s']
        dr.line((r['hx'] - .7 * TR['hw'] * r['s'], y, r['hx'] + .7 * TR['hw'] * r['s'], y), fill=(40, 160, 255), width=5)
    im.save(os.path.join(OUT, f'still_{f:03d}.jpg'), quality=90)
    tiles.append(im.resize((270, 480), Image.LANCZOS))
sheet = Image.new('RGB', (270 * len(tiles), 480))
for i, im in enumerate(tiles):
    sheet.paste(im, (270 * i, 0))
sheet.save(os.path.join(OUT, 'sheet.jpg'), quality=88)
lock = Image.new('RGB', (180 * len(lockf), 180))
for i, f in enumerate(lockf):
    r = FR[f]
    cx, cy = (r['cx'], r['cy']) if t0['anchor'] == 'chest' else (r['hx'], r['hy'])
    h = 1.25 * TR['hw'] * r['s']
    lock.paste(Image.fromarray(rgb[f]).transform((180, 180), Image.EXTENT, (cx - h, cy - h, cx + h, cy + h), Image.BILINEAR), (180 * i, 0))
lock.save(os.path.join(OUT, 'lock.jpg'), quality=88)
print(f'sheet.jpg frames {pick} (biggest head movement = {mv});  lock.jpg frames {lockf}')

# 4. phone copy
ph = os.path.join(HERE, 'renders', f'{SLOT}-phone.mp4')
subprocess.run([FF, '-v', 'error', '-y', '-i', MP4, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27', '-preset', 'medium',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', ph], check=True)
print(f'phone copy: renders/{SLOT}-phone.mp4')
