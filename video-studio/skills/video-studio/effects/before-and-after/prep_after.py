#!/usr/bin/env python3
"""before-after / prep_after: only when AFTER in build.py names YOUR finished version of the same moment.

Makes assets/after.mp4 from it (1080x1920, 30 fps, exactly the slot's frame count, every frame a keyframe, no audio:
the voice always comes from the a-roll), then checks that it really is the same frames:
  - timing : which frame offset matches the a-roll best (0 = locked). Not 0 -> it prints the AFTER_SHIFT to set.
  - framing: how well the outlines line up. Low = other crop, a punch-in, or another take: the wipe will jump at the line.

    PY prep_after.py
"""
import os
import subprocess
import sys

import numpy as np

import build as B
import measure as M

HERE = M.HERE
W, H = 180, 320


def load(path):
    raw = subprocess.run([M.FF, '-v', 'error', '-i', path, '-vf', f'scale={W}:{H}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
    return np.abs(np.diff(f, axis=2))[:, :-1, :] + np.abs(np.diff(f, axis=1))[:, :, :-1]      # outlines: grade-proof


if B.AFTER is None:
    sys.exit('AFTER = None in build.py: the after look is made by build.py itself, there is nothing to prepare.')
src = os.path.join(HERE, B.AFTER)
if not os.path.exists(src):
    sys.exit(f'{B.AFTER} is not in the slot. Copy your finished clip to that path first.')
N = M.clip()['frames']
info = subprocess.run([M.FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of',
                       'csv=p=0', src], capture_output=True, text=True).stdout.strip().split(',')
w, h = int(info[0]), int(info[1])
print(f'{B.AFTER}: {w}x{h} at {info[2]} fps')
if abs(w / h - 9 / 16) > .01:
    print('!! not 9:16: it is cropped to fill 1080x1920, so the framing will not match the a-roll')
out = os.path.join(HERE, 'assets/after.mp4')
shift = int(B.AFTER_SHIFT)
subprocess.run([M.FF, '-v', 'error', '-y', '-i', src, '-an', '-vf',
                f"fps=30,select='gte(n\\,{shift})',setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1",
                '-frames:v', str(N), '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-g', '1',
                '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], check=True)
n = M.count_frames(out)
if n != N:
    sys.exit(f'!! your file gives {n} frames at 30 fps (after skipping {shift}), the slot needs {N}. It must cover the whole '
             'slot: export a longer piece, or make the slot shorter.')
a, b = load(os.path.join(HERE, 'assets/aroll.mp4')), load(out)
move = float(np.abs(a[1:] - a[:-1]).mean() / max(a.mean(), 1e-6))
scores = {}
for k in range(-45, 46):
    lo, hi = max(0, -k), min(N, N - k)
    if hi - lo < N // 2:
        continue
    scores[k] = float(np.abs(b[lo:hi:2] - a[lo + k:hi + k:2]).mean())
best = min(scores, key=scores.get)
x, y = a[max(0, best):N + min(0, best)].ravel(), b[max(0, -best):N - max(0, best)].ravel()
corr = float(np.corrcoef(x, y)[0, 1])
print(f'timing : best match at offset {best:+d} frames (score {scores[best]:.2f}, at 0: {scores[0]:.2f})')
if move < .04:
    print('         (very still picture: the timing check has little to hold on to, look at a mid-sweep frame yourself)')
if best == 0:
    print('         locked: frame N of your file is frame N of the a-roll')
elif best < 0:
    print(f'!! your file is {-best} frames late: set AFTER_SHIFT = {shift - best} in build.py and run this again')
elif shift - best >= 0:
    print(f'!! your file is {best} frames early: set AFTER_SHIFT = {shift - best} in build.py and run this again')
else:
    print(f'!! your file starts {best} frames after the slot does: export it from an earlier point, or re-make the slot {best} frames later')
print(f'framing: outline match {corr:.2f} ' + ('(lines up)' if corr >= .33 else
      '!! does not line up: different crop, a punch-in or another take. The picture will jump at the line; use AFTER = None instead'))
print('wrote assets/after.mp4' + ('' if best == 0 and corr >= .33 else '   (fix the !! lines before you render)'))
