#!/usr/bin/env python3
"""doodle-boil, step 3 of 3 (after the render): frame count, plain footage on the first and last frame, phone copy,
stills, and contact sheets of the frames that matter.

Reads work/marks.json (written by build.py: each doodle mid-draw, drawn, crossed, rubbed out, plus the first and last
frame) and pulls those frames from the FINAL mp4 into work/qa/sheet_*.jpg (6 frames, 1080 px wide) with frame numbers,
so you can check: each doodle draws on its word, nothing covers his face, doodles inside the safe zone, edges plain.

Usage (from the slot folder):  PY post.py [extra frame numbers ...]
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
FP = shutil.which('ffprobe') or 'ffprobe'
NAME = os.path.basename(HERE)
R = os.path.join(HERE, f'renders/{NAME}.mp4')
if not os.path.exists(R):
    sys.exit(f'renders/{NAME}.mp4 is missing: render first')


def count(path):
    return int(subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries', 'stream=nb_read_frames',
                               '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip() or 0)


a, r = count(os.path.join(HERE, 'assets/aroll.mp4')), count(R)
print(f'frames: aroll {a}, render {r}' + ('' if a == r else '   !! FRAME COUNT MISMATCH'))
if a != r:
    sys.exit(1)


def frame(path, f):
    """One frame as RGB, decoded with its own tagged range (phone clips are often full range)."""
    rng = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=color_range', '-of', 'csv=p=0',
                          path], capture_output=True, text=True).stdout.strip()
    rng = 'pc' if rng in ('pc', 'jpeg') else 'tv'
    vf = (f'select=eq(n\\,{f}),scale=270:480:flags=area+accurate_rnd+full_chroma_int:in_color_matrix=bt709:in_range={rng}'
          ':out_range=pc,format=rgb24')
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', vf, '-frames:v', '1', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).astype(np.float32)


AR, FX = os.path.join(HERE, 'assets/aroll.mp4'), os.path.join(HERE, 'assets/fx.mp4')
for f in (0, a - 1):
    ref = frame(AR, f)
    d = float(np.abs(frame(FX, f) - ref).mean())          # what the effect controls: the bake against the a-roll
    dr = float(np.abs(frame(R, f) - ref).mean())          # plus the HyperFrames render's own colour path
    print(f'edge frame {f}: bake differs from the a-roll by {d:.2f} levels' + ('  (plain)' if d < 1.5 else '   !! NOT PLAIN')
          + f'; the render by {dr:.2f}')
phone = os.path.join(HERE, f'renders/{NAME}-phone.mp4')
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-preset', 'slow', '-crf', '27',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', phone], check=True)

marks = json.load(open(os.path.join(HERE, 'work/marks.json')))
frames = sorted(set(marks['marks']) | {int(v) for v in sys.argv[1:]})
os.makedirs(os.path.join(HERE, 'renders/stills'), exist_ok=True)
os.makedirs(os.path.join(HERE, 'work/qa'), exist_ok=True)
for k, f in enumerate(marks['stills'][:3]):
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f'select=eq(n\\,{f})', '-frames:v', '1', '-q:v', '2',
                    os.path.join(HERE, f'renders/stills/{NAME}-{k + 1}.jpg')], check=True)

TW, TH, PER = 180, 320, 6
sel = '+'.join(f'eq(n\\,{f})' for f in frames)
raw = subprocess.run([FF, '-v', 'error', '-i', R, '-vf', f"select='{sel}',scale={TW}:{TH}", '-fps_mode', 'passthrough', '-f', 'rawvideo',
                      '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
sheets = []
for s in range(0, len(frames), PER):
    part = frames[s:s + PER]
    sheet = Image.new('RGB', (TW * len(part), TH), '#111')
    for k, f in enumerate(part):
        i = s + k
        im = Image.frombytes('RGB', (TW, TH), raw[i * TW * TH * 3:(i + 1) * TW * TH * 3])
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 64, 22], fill=(0, 0, 0))
        d.text((6, 5), f'f{f}', fill=(255, 255, 255))
        sheet.paste(im, (TW * k, 0))
    p = os.path.join(HERE, f'work/qa/sheet_{s // PER + 1}.jpg')
    sheet.save(p, quality=88)
    sheets.append(os.path.relpath(p, HERE))
print(f'phone copy: renders/{NAME}-phone.mp4\nstills: frames {marks["stills"][:3]} -> renders/stills/\nlook at: ' + ', '.join(sheets))
