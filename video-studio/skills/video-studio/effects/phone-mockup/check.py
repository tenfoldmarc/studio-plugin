#!/usr/bin/env python3
"""phone-mockup / check: prove the render before anyone watches it.

  1. frame count of renders/<slot>.mp4 == the a-roll's
  2. first and last frame are the untouched picture (the reel lays this slot over the a-roll, both edges must match)
  3. the phone's bounds sit inside the safe zone; no tap point is hidden behind the speaker when it lands
  4. work/check/sheet.jpg (first frame, landed, each tap before / after, leaving, last frame), one full-size frame per
     tap, renders/stills/<slot>-1..3.jpg and the 720p copy renders/<slot>-phone.mp4

    PY check.py
LOOK at work/check/sheet.jpg afterwards: this script cannot judge taste.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
SLOT = os.path.basename(HERE)
R = os.path.join(HERE, 'renders', f'{SLOT}.mp4')
if not os.path.exists(R):
    sys.exit(f'no render yet: renders/{SLOT}.mp4')
L = json.load(open(os.path.join(HERE, 'work', 'layout.json')))
N = M.clip()['frames']
ok = True

n = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', R], capture_output=True, text=True).stdout.strip() or 0)
print(f'frames: render {n}, a-roll {N}  ' + ('OK' if n == N else '!! MISMATCH'))
ok &= n == N


def grab(path, f):
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='eq(n,{f})',scale=270:480:flags=area", '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).astype(np.float32).reshape(480, 270, 3)


for name, f in (('first', 0), ('last', N - 1)):
    d = np.abs(grab(R, f) - grab(os.path.join(HERE, 'assets/aroll.mp4'), f))
    worst = float(d.mean(axis=2).max())
    good = d.mean() < 2.0 and worst < 24
    print(f'{name} frame vs the plain clip: mean difference {d.mean():.2f}, worst spot {worst:.0f} (of 255)  '
          + ('OK, untouched' if good else '!! something of the effect is still on this frame'))
    ok &= good

b = L['bounds']
safe = b[0] >= 35 and b[1] >= 220 and b[3] <= 1470 and b[2] <= (1045 if b[3] <= 1155 else 980)
print(f'phone bounds x {b[0]}..{b[2]}, y {b[1]}..{b[3]}  ' + ('inside the safe zone' if safe else '!! outside the safe zone'))
ok &= safe
if M.has_cutout() and L['layer'] == 'behind':
    a = M.alpha()
    r = L['room'] or dict(scale=1, x=0, y=0)
    for t in L['taps']:
        gx, gy = int((t['x'] - r['x']) / r['scale'] // M.CELL), int((t['y'] - r['y']) / r['scale'] // M.CELL)
        seg = a[max(0, t['frame'] - 3):t['frame'] + 5, max(0, gy - 4):gy + 5, max(0, gx - 4):gx + 5]
        hid = float(seg.max()) if seg.size else 0.0
        print(f"tap frame {t['frame']} ({t['where']}): " + ('clear of the speaker' if hid < .3 else '!! the speaker is in front of the tap point: move the tap, the side, or the slot'))
        ok &= hid < .3

out = os.path.join(HERE, 'work', 'check')
os.makedirs(out, exist_ok=True)
os.makedirs(os.path.join(HERE, 'renders', 'stills'), exist_ok=True)
taps = [t['frame'] for t in L['taps']]
fr = [0, L['f_in'] + 6, L['f_in'] + 24] + [f for t in taps[:3] for f in (t - 2, t + 4)] + [L['f_out'] + 5, N - 1]
fr = sorted({min(N - 1, max(0, f)) for f in fr})
tw = 1080 // min(6, len(fr))
sel = '+'.join(f'eq(n,{f})' for f in fr)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='{sel}',scale={tw}:-2,tile={min(6, len(fr))}x{-(-len(fr) // 6)}",
                '-frames:v', '1', '-q:v', '3', os.path.join(out, 'sheet.jpg')], check=True)
print(f'sheet: work/check/sheet.jpg  frames {fr}')
for t in taps[:2]:
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n,{t + 4})'", '-frames:v', '1', '-q:v', '2',
                    os.path.join(out, f'tap_{t:04d}.jpg')], check=True)
mid = taps[0] + 6 if taps else N // 2
for i, f in enumerate((L['f_in'] + 12, min(N - 1, mid), min(N - 1, max(mid + 20, L['f_out'] - 6))), 1):
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n,{f})'", '-frames:v', '1', '-q:v', '2',
                    os.path.join(HERE, 'renders', 'stills', f'{SLOT}-{i}.jpg')], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27', '-preset',
                'medium', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                os.path.join(HERE, 'renders', f'{SLOT}-phone.mp4')], check=True)
print(f'stills: renders/stills/{SLOT}-1..3.jpg   phone copy: renders/{SLOT}-phone.mp4')
print('\nRESULT: ' + ('numbers OK, now look at the sheet' if ok else '!! fix the lines marked !! first'))
