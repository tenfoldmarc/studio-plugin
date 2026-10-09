#!/usr/bin/env python3
"""green-screen / check: prove the render before anyone watches it.

  1. renders/<slot>.mp4 has exactly the clip's frames at 1080x1920
  2. the frames outside the effect are the untouched clip (the reel lays this slot over the a-roll); with HARD_IN /
     HARD_OUT that edge is skipped and said so
  3. every background cut lands on its frame (big change INTO the frame, small change after it)
  4. the face stays above y 1470 and the body's cut-off row is below the canvas bottom (from work/layout.json)
  5. work/check/sheet.jpg (two rows: edges, the shrink, every cut, the grow back; red line = y 1470),
     renders/stills/<slot>-1..3.jpg and the 720p copy renders/<slot>-phone.mp4

    python check.py          (numpy + Pillow)
LOOK at work/check/sheet.jpg afterwards: this script cannot judge taste.
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
SLOT = os.path.basename(HERE)
R = f'renders/{SLOT}.mp4'
if not os.path.exists(R):
    sys.exit(f'no render yet: {R}')
L = json.load(open('work/layout.json'))
N, f_in, f_out, items = L['frames'], L['f_in'], L['f_out'], L['items']
TW, TH = 180, 320
ok = True


def frames(path, wanted):
    """{frame number: TH x TW x 3 array} in one decode"""
    sel = '+'.join(f'eq(n,{f})' for f in sorted(set(wanted)))
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={TW}:{TH}:flags=area", '-fps_mode',
                          'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, TH, TW, 3)
    return dict(zip(sorted(set(wanted)), a))


info = B.probe(R, 'stream=width,height,nb_frames').split('\n')[0].split(',')
good = info[:2] == [str(B.W), str(B.H)] and info[2] == str(N)
print(f'render: {info[0]}x{info[1]}, {info[2]} frames (clip: {N})  ' + ('OK' if good else '!! WRONG SIZE OR FRAME COUNT'))
ok &= good

plain = [0, N - 1] + ([] if B.HARD_IN else [f_in - 1]) + ([] if B.HARD_OUT else [f_out])
cuts = [it['a'] for it in items[1:]]
sheet_f = sorted({0, max(0, f_in - 1), f_in, f_in + 2, f_in + B.TRANS, min(N - 1, f_out - B.TRANS), f_out - 2, f_out - 1,
                  min(N - 1, f_out), N - 1} | {c - 1 for c in cuts} | set(cuts) | {(it['a'] + it['b']) // 2 for it in items})
want = sorted(set(plain + sheet_f + [c + 1 for c in cuts]))
want = [f for f in want if 0 <= f < N]
rend = frames(R, want)
src = frames('assets/aroll.mp4', [f for f in plain if 0 <= f < N])

for f in sorted(set(plain)):
    if (f == 0 and B.HARD_IN) or (f == N - 1 and B.HARD_OUT):
        print(f'frame {f}: the green screen is up on purpose (HARD_{"IN" if f == 0 else "OUT"}): the reel must cut here')
        continue
    d = np.abs(rend[f].astype(np.float32) - src[f].astype(np.float32))
    worst = float(d.mean(axis=2).max())
    good = d.mean() < 6.0 and worst < 24       # anything the effect draws leaves a spot far above 24
    print(f'frame {f} vs the plain clip: mean difference {d.mean():.2f}, worst spot {worst:.0f} (of 255)  '
          + ('OK, untouched' if good else '!! something of the effect is on this frame')
          + (' (the even difference is the encode\'s colour shift on this source, not the effect)' if good and d.mean() >= 2 else ''))
    ok &= good

for c in cuts:
    into = float(np.abs(rend[c].astype(np.float32) - rend[c - 1]).mean())
    after = float(np.abs(rend[c + 1].astype(np.float32) - rend[c]).mean())
    good = into > 3 * after + 2
    print(f'background cut on frame {c}: change into it {into:.1f}, change after it {after:.1f}  '
          + ('OK, lands on the frame' if good else '!! the cut is not clean on this frame'))
    ok &= good

m = L['measure']
for k, it in enumerate(items):
    p = it['pose']
    edge = p['y'] + p['s'] * m['base']
    good = p['face'][3] <= 1470 and edge >= B.H and p['cap_bottom'] < p['face'][1]
    print(f'item {k}: chin at y {p["face"][3]} (limit 1470), body cut-off row lands at y {edge:.0f} (canvas ends at {B.H}), '
          f'caption line ends {p["face"][1] - p["cap_bottom"]} px above the head  ' + ('OK' if good else '!! CHECK'))
    ok &= good

os.makedirs('work/check', exist_ok=True)
os.makedirs('renders/stills', exist_ok=True)
tiles = [f for f in sheet_f if f in rend]
per = 6
sheet = Image.new('RGB', (TW * per, TH * -(-len(tiles) // per)), (30, 30, 30))
for i, f in enumerate(tiles):
    im = Image.fromarray(rend[f])
    d = ImageDraw.Draw(im)
    y = 1470 * TH // B.H
    d.line([(0, y), (TW, y)], fill=(255, 0, 0), width=1)
    d.rectangle([0, 0, 44, 13], fill=(0, 0, 0))
    d.text((3, 1), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, ((i % per) * TW, (i // per) * TH))
sheet.save('work/check/sheet.jpg', quality=85)
stills = [f_in + B.TRANS + 6] + [(it['a'] + it['b']) // 2 for it in items][-2:]
stills = (stills + [f_out - B.TRANS - 6])[:3]
for i, f in enumerate(stills):
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n,{f})',scale=720:1280:flags=lanczos,format=yuvj420p",
                    '-frames:v', '1', '-q:v', '3', f'renders/stills/{SLOT}-{i + 1}.jpg'], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27',
                '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                f'renders/{SLOT}-phone.mp4'], check=True)
print(f'wrote work/check/sheet.jpg ({len(tiles)} frames), renders/stills/{SLOT}-1..3.jpg, renders/{SLOT}-phone.mp4')
print('ALL CHECKS PASSED: now look at the sheet' if ok else '!! at least one check failed (see above)')
sys.exit(0 if ok else 1)
