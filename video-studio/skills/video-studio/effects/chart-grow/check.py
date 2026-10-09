#!/usr/bin/env python3
"""chart-grow / check.py: facts about the finished render, a contact sheet, stills and the phone copy.

Run from the slot folder after the render. Prints: frame count and size, whether the first and last frame are the
untouched picture, the frame the kick colour first shows (against the kick word), how far the sounds sit under the
voice. Writes work/check/sheet.jpg (6 frames), renders/stills/<slot>-1..3.jpg, renders/<slot>-phone.mp4.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
SLOT = os.path.basename(HERE)
OUT = f'renders/{SLOT}.mp4'
W, H = 360, 640
if not os.path.exists(OUT) or not os.path.exists('work/build.json'):
    sys.exit(f'{OUT} or work/build.json is missing: build and render first')
B = json.load(open('work/build.json'))
NF = B['frames']


def video(path):
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f'scale={W}:{H}:flags=area', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3)


size = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', OUT],
                      capture_output=True, text=True).stdout.strip()
r, a = video(OUT), video('assets/aroll.mp4')
ok = len(r) == NF and size == '1080,1920'
print(f'{OUT}: {len(r)} frames (slot {NF}), {size.replace(",", "x")}  {"ok" if ok else "!! WRONG LENGTH OR SIZE"}')
n = min(len(r), len(a))
diff = np.abs(r[:n].astype(np.int16) - a[:n].astype(np.int16)).mean(axis=(1, 2, 3))
lim = float(diff.min()) + .4                 # the render re-encodes the picture: its quietest frame is the floor
touched = np.where(diff > lim)[0]
print(f'first frame differs from the plain picture by {diff[0]:.2f}, last by {diff[n - 1]:.2f} (re-encode floor {diff.min():.2f}, '
      f'under {lim:.2f} = untouched). Effect on frames {touched[0] if len(touched) else "-"}..{touched[-1] if len(touched) else "-"}; '
      f'CLIP says in {B["in_frame"]}, out {B["out_frame"]}')
if diff[0] > lim:
    print('!! the first frame is not the plain picture')
if B['out_frame'] is not None and diff[n - 1] > lim:
    print('!! the last frame is not the plain picture (OUT_FRAME is set, so it should be)')

acc = np.array([int(B['accent'].lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)], np.int16)
x_from = int(B['points'][-3][0] / 3) if len(B['points']) > 3 else 0
near = lambda v: (np.abs(v[:, :, x_from:].astype(np.int16) - acc).sum(axis=3) < 70)
count = (near(r[:n]) & ~near(a[:n])).sum(axis=(1, 2))
seen = np.where(count > 10)[0]
if len(seen):
    print(f'kick colour first shows on frame {seen[0]} (kick set to start on {B["kick_frame"]}, word starts on {B["word_frame"]}); '
          f'most on frame {int(count.argmax())}')
    if not B['kick_frame'] <= seen[0] <= B['word_frame'] + 2:
        print('!! the kick is not landing on the word: check KICK and measure.py -v')
else:
    print('!! the kick colour never shows: the line is hidden or ACCENT is too close to the wall colour')

if B.get('sounds'):      # worked out by build.py from the sound files and their volumes; the render itself is not measured
    print(f'sound: {len(B["sounds"])} effect sounds, the loudest sits {B["sound_gap_db"]:.0f} dB under their loudest word '
          '(8 or more is the aim; SFX_LEVEL lowers them). Nobody has listened: play it once.')
    has = subprocess.run([FP, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', OUT],
                         capture_output=True, text=True).stdout.strip()
    print(f'audio track in the render: {has or "!! NONE"}')
else:
    print('sound: no effect sounds (SFX=0 or SFX_LEVEL 0)')

os.makedirs('work/check', exist_ok=True)
os.makedirs('renders/stills', exist_ok=True)
land = int(B['land'] * 30)
last = (B['out_frame'] - 12) if B['out_frame'] is not None else NF - 2
frames = [0, (B['in_frame'] + B['kick_frame']) // 2, B['kick_frame'] - 1, B['kick_frame'] + 4, land + 8, min(n - 1, max(land + 9, last))]
sheet = Image.new('RGB', (W * 3, H * 2))
for k, f in enumerate(frames):
    sheet.paste(Image.fromarray(r[min(n - 1, f)]), ((k % 3) * W, (k // 3) * H))
sheet.save('work/check/sheet.jpg', quality=88)
for k, f in enumerate((frames[1], frames[3], frames[4])):
    subprocess.run([FF, '-v', 'error', '-y', '-i', OUT, '-vf', f"select='eq(n,{f})'", '-frames:v', '1', '-q:v', '3',
                    f'renders/stills/{SLOT}-{k + 1}.jpg'], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', OUT, '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27', '-preset', 'medium',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', f'renders/{SLOT}-phone.mp4'], check=True)
print(f'sheet: work/check/sheet.jpg (frames {frames})   stills: renders/stills/   phone copy: renders/{SLOT}-phone.mp4')
