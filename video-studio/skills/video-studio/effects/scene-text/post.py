#!/usr/bin/env python3
"""After the render: frame-count check, renders/<slot>-phone.mp4 (720x1280), three stills, and a six-frame contact
sheet of the frames that matter (print spreading, each big word landing, before the lift, after, the last frame) taken
from the FINAL mp4 -> work/qa/sheet.jpg.   Usage (slot folder): python post.py [extra frame numbers ...]
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
R = os.path.join(HERE, 'renders', f'{NAME}.mp4')
if not os.path.exists(R):
    sys.exit(f'renders/{NAME}.mp4 is missing: render first')


def count(path):
    return int(subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                               'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip() or 0)


n = json.load(open(os.path.join(HERE, 'clip.json')))['frames']
r = count(R)
print(f'frames: clip.json {n}, render {r}' + ('' if n == r else '   !! FRAME COUNT MISMATCH'))
if n != r:
    sys.exit(1)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-preset', 'slow',
                '-crf', '27', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                os.path.join(HERE, 'renders', f'{NAME}-phone.mp4')], check=True)
marks = json.load(open(os.path.join(HERE, 'work', 'marks.json')))['marks']
frames = sorted(set(marks) | {int(v) for v in sys.argv[1:]})[:6]
TW, TH = 180, 320
sel = '+'.join(f'eq(n\\,{f})' for f in frames)
raw = subprocess.run([FF, '-v', 'error', '-i', R, '-vf', f"select='{sel}',scale={TW * 2}:{TH * 2}", '-fps_mode', 'passthrough',
                      '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
os.makedirs(os.path.join(HERE, 'work', 'qa'), exist_ok=True)
os.makedirs(os.path.join(HERE, 'renders', 'stills'), exist_ok=True)
sheet = Image.new('RGB', (TW * 2 * len(frames) // 2, TH), '#111')
sz = TW * 2 * TH * 2 * 3
for k, f in enumerate(frames):
    im = Image.frombytes('RGB', (TW * 2, TH * 2), raw[k * sz:(k + 1) * sz])
    if 1 <= k <= 3:
        im.save(os.path.join(HERE, 'renders', 'stills', f'{NAME}-{k}.jpg'), quality=90)
    im = im.resize((TW, TH), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 46, 16], fill=(0, 0, 0))
    d.text((4, 3), f'f{f}', fill=(255, 255, 255))
    sheet.paste(im, (TW * k, 0))
sheet.save(os.path.join(HERE, 'work', 'qa', 'sheet.jpg'), quality=88)
print(f'phone copy: renders/{NAME}-phone.mp4\nlook at: work/qa/sheet.jpg (frames {frames})')
