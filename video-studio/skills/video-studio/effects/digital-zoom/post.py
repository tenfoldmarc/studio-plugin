#!/usr/bin/env python3
"""Step 5. After the render: frame-count check, phone copy, stills, and contact sheets of the frames that matter.

Reads work/marks.json (written by build.py: every zoom's start, travelling frames, landing, plus caption frames) and
pulls those frames from the FINAL mp4 into work/qa/sheet_*.jpg with frame numbers, so you can check: the move lands
on the word, their eyes sit on the target, no caption touches their face, nothing readable outside the safe zone.

Usage (from the slot folder):  PY post.py [extra frame numbers ...]
"""
import json
import os
import shutil
import subprocess
import sys

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

TW, TH, PER = 360, 640, 6
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
