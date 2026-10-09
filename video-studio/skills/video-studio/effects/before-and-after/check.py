#!/usr/bin/env python3
"""before-after / check: prove the render before anyone watches it.

  1. frame count of renders/<slot>.mp4 == the a-roll's
  2. plain edges: the first frames and (unless OUT = None) the last frames are the untouched a-roll
  3. while the line waits: the BEFORE side still is the a-roll, the AFTER side is not, the line is off their head
  4. work/check/sheet.jpg (9 moments), renders/stills/<slot>-1..3.jpg, the 720p phone copy renders/<slot>-phone.mp4

    PY check.py
LOOK at work/check/sheet.jpg afterwards: this script cannot judge taste.
"""
import json
import os
import subprocess
import sys

import numpy as np

import measure as M

HERE = M.HERE
SLOT = os.path.basename(HERE)
R = os.path.join(HERE, 'renders', f'{SLOT}.mp4')
if not os.path.exists(R):
    sys.exit(f'no render yet: renders/{SLOT}.mp4')
L = json.load(open(os.path.join(HERE, 'work', 'layout.json')))
N = L['frames']
W, H = 270, 480
ok = True


def load(path):
    raw = subprocess.run([M.FF, '-v', 'error', '-i', path, '-vf', f'scale={W}:{H}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.float32)


n = M.count_frames(R)
print(f'frames: render {n}, a-roll {N}  ' + ('OK' if n == N else '!! MISMATCH'))
ok &= n == N
a, r = load(os.path.join(HERE, 'assets/aroll.mp4')), load(R)
k = min(len(a), len(r))
e = np.abs(r[:k] - a[:k]).mean(axis=3)
d = e.reshape(k, H // 15, 15, W // 15, 15).mean(axis=(2, 4)).max(axis=(1, 2))      # worst 60x60 px block per frame
noise = max(8.0, 2.5 * float(np.median(np.sort(d)[:max(3, k // 10)])))              # re-encode noise; a tag or a grade is far above it
if '--v' in sys.argv:
    print('worst block per frame: ' + ' '.join(f'{x:.0f}' for x in d))
head = next((f for f in range(k) if d[f] > noise), k)
tail = next((f for f in range(k - 1, -1, -1) if d[f] > noise), -1)
print(f'plain edges: frame 0 differs from the a-roll by {d[0]:.2f}, first touched frame {head} ' + ('OK' if head >= 2 else '!! the effect is on at frame 0'))
ok &= head >= 2
if L['t_out'] is None:
    print(f'             OUT = None: the slot ENDS ON A CUT with the after look on (last frame differs by {d[k - 1]:.2f})')
else:
    good = tail < k - 2
    print(f'             last touched frame {tail} of {k - 1}, last frame differs by {d[k - 1]:.2f} ' + ('OK' if good else '!! the after look is still on at the end'))
    ok &= good
if L['peek']:
    f = int(round((L['rest'][0] + L['rest'][1]) / 2 * 30))
    x = int(L['rest_x'] / 4)
    y0 = 320 // 4                                     # below the tags
    left = float(np.abs(r[f, y0:, :max(1, x - 8)] - a[f, y0:, :max(1, x - 8)]).mean())
    right = float(np.abs(r[f, y0:, x + 8:] - a[f, y0:, x + 8:]).mean())
    noise = 2.6                                       # whole-side averages: plain re-encode sits near 2
    hw = L['head_wipe']
    gap = min(abs(L['rest_x'] - hw[0]), abs(L['rest_x'] - hw[2])) if hw else None
    print(f"line waiting (frame {f}, x {L['rest_x']:.0f}): before side differs by {left:.2f}, after side by {right:.2f} "
          + ('OK' if left < noise < right else '!! the sides are not what they should be'))
    ok &= left < noise < right
    if gap is not None:
        print(f'             line is {gap:.0f} px from their head (x {hw[0]:.0f}-{hw[2]:.0f}) ' + ('OK' if gap >= 60 else '!! too close'))
        ok &= gap >= 60
for w in L['warnings']:
    print('build.py warned: ' + w)

t = lambda s: int(max(0, min(N - 1, round(s * 30))))
mid = t((L['c0'] + L['c1']) / 2)
frames = [0, t(L['label_in'] + .4), t(L['t_in'] + .32), t((L['rest'][0] + L['rest'][1]) / 2) if L['peek'] else t(L['c0'] + .1), mid,
          t(L['c1']) + 2, t(L['c1'] + .7), t(L['t_out'] + .22) if L['t_out'] is not None else N - 8, N - 1]
out = os.path.join(HERE, 'work', 'check')
os.makedirs(out, exist_ok=True)
os.makedirs(os.path.join(HERE, 'renders', 'stills'), exist_ok=True)
for i, f in enumerate(frames):
    subprocess.run([M.FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n\\,{f})',scale=216:-1", '-frames:v', '1', '-q:v', '3',
                    os.path.join(out, f's{i}.jpg')], check=True)
ins = [x for i in range(len(frames)) for x in ('-i', os.path.join(out, f's{i}.jpg'))]
subprocess.run([M.FF, '-v', 'error', '-y', *ins, '-filter_complex', f'hstack=inputs={len(frames)}', '-q:v', '3', os.path.join(out, 'sheet.jpg')], check=True)
for i, f in enumerate([frames[3], mid, frames[6]]):
    subprocess.run([M.FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n\\,{f})'", '-frames:v', '1', '-q:v', '2',
                    os.path.join(HERE, 'renders', 'stills', f'{SLOT}-{i + 1}.jpg')], check=True)
subprocess.run([M.FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27', '-preset', 'slow',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                os.path.join(HERE, 'renders', f'{SLOT}-phone.mp4')], check=True)
print(f'sheet: work/check/sheet.jpg (frames {frames}: start, tag in, peek, waiting, mid sweep, swept, after look, easing off, end)')
print(f'stills: renders/stills/   phone copy: renders/{SLOT}-phone.mp4')
print('RESULT: ' + ('numbers check out, now LOOK at the sheet' if ok else '!! something above needs fixing'))
