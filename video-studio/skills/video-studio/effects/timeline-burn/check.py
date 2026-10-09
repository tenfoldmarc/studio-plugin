#!/usr/bin/env python3
"""timeline-burn / check: prove the render before anyone watches it.

  1. renders/<slot>.mp4 has exactly the clip's frames at 1080x1920
  2. frame 0, the frame before F_IN, the F_OUT frame and the last frame are the untouched clip
  3. the fire starts on the burn frame (the flash is a jump in brightness inside the timeline, not before it)
  4. nothing is drawn on the face: inside the face box the picture is only the clip, evenly dimmed
  5. nothing is drawn outside the safe zone (compared with the clip, evenly dimmed)
  6. work/check/sheet.jpg (red line = y 1470), renders/stills/<slot>-1..3.jpg and the 720p copy renders/<slot>-phone.mp4

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
N, f_in, f_burn, f_out = L['frames'], L['f_in'], L['f_burn'], L['f_out']
TW, TH = 270, 480
K = B.W / TW
ok = True


def frames(path, wanted):
    """{frame number: TH x TW x 3 float array} in one decode"""
    want = sorted(set(wanted))
    sel = '+'.join(f'eq(n,{f})' for f in want)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={TW}:{TH}:flags=area", '-fps_mode',
                          'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, TH, TW, 3).astype(np.float32)
    return dict(zip(want, a))


info = B.probe(R, 'stream=width,height,nb_read_packets').split('\n')[0].split(',')
good = info[:2] == [str(B.W), str(B.H)] and info[2] == str(N)
print(f'render: {info[0]}x{info[1]}, {info[2]} frames (clip: {N})  ' + ('OK' if good else '!! WRONG SIZE OR FRAME COUNT'))
ok &= good

plain = sorted({0, f_in - 1, f_out, N - 1})
during = sorted({f_in + 10, (f_in + f_burn) // 2, f_burn - 2, f_burn, f_burn + 2, f_burn + 4, f_burn + 7, f_burn + 10,
                 f_burn + 14, f_burn + 19, f_burn + 24})
sheet_f = sorted({0, f_in - 1, f_in + 4, f_in + 12, (f_in + f_burn) // 2, f_burn - 12, f_burn - 1, f_burn, f_burn + 2,
                  f_burn + 5, f_burn + 9, f_burn + 14, f_burn + 20, f_out - 1, f_out, N - 1})
want = [f for f in sorted(set(plain + during + sheet_f + [f_burn - 1])) if 0 <= f < N]
rend = frames(R, want)
src = frames('assets/aroll.mp4', want)

for f in plain:
    d = np.abs(rend[f] - src[f])
    worst = float(d.mean(axis=2).max())
    good = d.mean() < 6.0 and worst < 24       # anything the effect draws leaves a spot far above 24
    print(f'frame {f} vs the plain clip: mean difference {d.mean():.2f}, worst spot {worst:.0f} (of 255)  '
          + ('OK, untouched' if good else '!! something of the effect is on this frame'))
    ok &= good

x0, y0, x1, y1 = (int(v / K) for v in L['panel'])
lum = lambda f: float(rend[f][y0:y1, x0:x1].mean())
jump, before = lum(f_burn) - lum(f_burn - 1), abs(lum(f_burn - 1) - lum(f_burn - 2))
good = jump > 6 and jump > 2.5 * before
print(f'burn frame {f_burn} ({L["burn_word"]}): brightness inside the timeline jumps by {jump:.1f} on it (the frame before moved '
      f'{before:.1f})  ' + ('OK, the fire starts on the frame' if good else '!! the flash is not on this frame'))
ok &= good


def drawn(f, box):
    """strongest thing the effect drew inside box on frame f: what is left once the even dim is taken out"""
    bx0, by0, bx1, by1 = (max(0, int(v / K)) for v in box)
    r, s = rend[f][by0:by1, bx0:bx1].mean(axis=2), src[f][by0:by1, bx0:bx1].mean(axis=2)
    if r.size == 0:
        return 0.0
    k = float(np.median(r[s > 30] / s[s > 30])) if (s > 30).any() else 1.0
    return float(np.abs(r - k * s).max())


fx0, fy0, fx1, fy1 = L['face']
worst_face = max(drawn(f, (fx0, fy0, fx1, fy1)) for f in during)
good = worst_face < 30
print(f'face box x {fx0}..{fx1} y {fy0}..{fy1}: strongest mark over {len(during)} frames is {worst_face:.0f} (of 255)  '
      + ('OK, nothing drawn on the face' if good else '!! something crosses the face: look at the sheet'))
ok &= good
edges = [(0, 0, B.W, B.SAFE_T - 4), (0, B.SAFE_B + 4, B.W, B.H), (0, 0, B.SAFE_L - 3, B.H), (B.SAFE_R + 3, 0, B.W, B.H),
         (B.SAFE_R_LOW + 4, B.SAFE_R_Y, B.W, B.SAFE_B)]
worst_out = max(drawn(f, e) for f in during for e in edges)
good = worst_out < 30
print(f'outside the safe zone: strongest mark is {worst_out:.0f} (of 255)  ' + ('OK, nothing drawn there' if good else '!! CHECK the sheet'))
ok &= good

os.makedirs('work/check', exist_ok=True)
os.makedirs('renders/stills', exist_ok=True)
tiles = [f for f in sheet_f if f in rend]
per = 8
tw, th = 135, 240
sheet = Image.new('RGB', (tw * per, th * -(-len(tiles) // per)), (30, 30, 30))
for i, f in enumerate(tiles):
    im = Image.fromarray(rend[f].astype(np.uint8)).resize((tw, th))
    d = ImageDraw.Draw(im)
    y = B.SAFE_B * th // B.H
    d.line([(0, y), (tw, y)], fill=(255, 0, 0), width=1)
    d.rectangle([0, 0, 40, 12], fill=(0, 0, 0))
    d.text((3, 1), f'f{f}', fill=(255, 255, 0))
    sheet.paste(im, ((i % per) * tw, (i // per) * th))
sheet.save('work/check/sheet.jpg', quality=88)
for i, f in enumerate([(f_in + f_burn) // 2, f_burn + 3, f_burn + 9]):
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n,{f})',scale=720:1280:flags=lanczos,format=yuvj420p",
                    '-frames:v', '1', '-q:v', '3', f'renders/stills/{SLOT}-{i + 1}.jpg'], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27',
                '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                f'renders/{SLOT}-phone.mp4'], check=True)
print(f'wrote work/check/sheet.jpg ({len(tiles)} frames), renders/stills/{SLOT}-1..3.jpg, renders/{SLOT}-phone.mp4')
print('ALL CHECKS PASSED: now look at the sheet' if ok else '!! at least one check failed (see above)')
sys.exit(0 if ok else 1)
