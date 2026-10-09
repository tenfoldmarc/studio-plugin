#!/usr/bin/env python3
"""freeze-label: check the final render. Run from the slot folder after the render:

    PY check.py

Prints the numbers (frame count, plain edges, frozen really frozen, the cut back to live) and writes
work/check/sheet.jpg (6 frames with the head box and the safe zone drawn), 3 stills and renders/<slot>-phone.mp4.
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
FP = shutil.which('ffprobe') or 'ffprobe'
SLOT = os.path.basename(HERE)
OUT = f'renders/{SLOT}.mp4'
if not os.path.exists(OUT) or not os.path.exists('work/layout.json'):
    print(f'!! {OUT} or work/layout.json is missing: run build.py and the render first')
    sys.exit(1)
P = json.load(open('work/layout.json'))
N, FRZ, REL = P['frames'], P['freeze'], P['release']
os.makedirs('work/check', exist_ok=True)


def frames(path, want, w=540, h=960):
    """the wanted frame numbers of a video, small, as float arrays"""
    sel = '+'.join(f'eq(n,{f})' for f in sorted(set(want)))
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={w}:{h}", '-fps_mode', 'passthrough',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32)
    return dict(zip(sorted(set(want)), arr))


n = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', OUT], capture_output=True, text=True).stdout.strip() or 0)
bad = []
print(f"frames: {n} of {N}  {'ok' if n == N else '!! MISMATCH'}")
if n != N:
    bad.append('frame count')
last_lab = max(L['f_dot'] for L in P['labels']) + 14
end_hold = (REL if REL is not None else N) - 1
want = [0, FRZ - 1, FRZ, FRZ + 16, FRZ + 17, last_lab, end_hold - 8, end_hold, N - 1] + ([REL, REL + 12] if REL is not None else [])
want = [min(N - 1, max(0, f)) for f in want]
R, A = frames(OUT, want), frames('assets/aroll.mp4', want)
diff = lambda f: float(np.abs(R[f] - A[f]).mean())
edges = [0, FRZ - 1] + ([REL + 12, N - 1] if REL is not None else [])
for f in edges:
    d = diff(min(N - 1, f))
    print(f"frame {min(N - 1, f)}: differs from the plain a-roll by {d:.2f} levels (the renderer alone shifts colour by about 2)  {'plain' if d < 4 else '!! NOT PLAIN'}")
    if d >= 4:
        bad.append(f'frame {f} not plain')
if REL is None:
    print(f'no release: the last frame is the frozen picture with its labels (differs from live by {diff(N - 1):.1f}). The slot ends on a cut.')
# frozen really frozen: two neighbouring frames deep in the hold are the same picture (live footage is not)
hx0, hy0, hx1, hy1 = (int(v / 2) for v in P['head'])
fa = min(N - 2, FRZ + 16)
head = lambda S, f: S[f][hy0:hy1, hx0:hx1]
d_r, d_a = float(np.abs(head(R, fa) - head(R, fa + 1)).mean()), float(np.abs(head(A, fa) - head(A, fa + 1)).mean())
frozen = d_r < max(.8, .5 * d_a)
print(f"hold: head region changes {d_r:.2f} levels from frame {fa} to {fa + 1} (live footage: {d_a:.2f})  "
      f"{'frozen' if frozen else '!! MOVING: is the plate showing?'}")
if not frozen:
    bad.append('hold is not frozen')
if REL is not None:
    jump = float(np.abs(R[REL] - R[end_hold]).mean())
    print(f"release: frame {REL - 1} -> {REL} changes {jump:.1f} levels (the hard cut, with its flash and punch)")

# sheet: before, hit, labels up, end of hold, cut, last
show = [FRZ - 1, FRZ + 16, last_lab, end_hold - 8] + ([REL, N - 1] if REL is not None else [end_hold, N - 1])
show = [min(N - 1, max(0, f)) for f in show]
tw, th = 270, 480
sheet = Image.new('RGB', (tw * len(show), th + 24), (20, 22, 28))
dr = ImageDraw.Draw(sheet)
for i, f in enumerate(show):
    im = Image.fromarray(R[f].astype(np.uint8))
    d = ImageDraw.Draw(im)
    if FRZ <= f <= end_hold:
        d.rectangle([v / 2 for v in P['head']], outline=(80, 150, 255), width=2)
    d.rectangle((17, 110, 522, 735), outline=(255, 60, 60), width=1)
    d.line((490, 577, 522, 577), fill=(255, 60, 60), width=1)
    d.line((490, 577, 490, 735), fill=(255, 60, 60), width=1)
    sheet.paste(im.resize((tw, th), Image.LANCZOS), (i * tw, 24))
    dr.text((i * tw + 6, 6), f'frame {f}', fill=(230, 230, 230))
sheet.save('work/check/sheet.jpg', quality=88)

for name, f in (('1-freeze', FRZ + 16), ('2-labels', last_lab), ('3-release' if REL is not None else '3-end', REL + 2 if REL is not None else N - 1)):
    subprocess.run([FF, '-v', 'error', '-y', '-i', OUT, '-vf', f"select='eq(n,{min(N - 1, f)})'", '-frames:v', '1', '-q:v', '3',
                    f'work/check/{name}.jpg'], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', OUT, '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27', '-preset', 'medium',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', f'renders/{SLOT}-phone.mp4'], check=True)
print(f'wrote work/check/sheet.jpg, 3 stills, renders/{SLOT}-phone.mp4')
print('RESULT: ' + ('ok' if not bad else '!! ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
