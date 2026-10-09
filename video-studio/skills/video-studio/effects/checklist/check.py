#!/usr/bin/env python3
"""checklist / check.py: after the render. Checks the frame count, writes the phone copy and the sheets to look at.

Run from the slot folder (plain python3):   python3 check.py
Reads   work/build.json (written by build.py), renders/<slot folder>.mp4
Writes  renders/<slot folder>-phone.mp4        720x1280 crf 27 preview
        work/final/sheet.jpg                   whole frame at every beat: before, build, each say, each tick, done, (out), last
        work/final/ticks.jpg                   the card at full size on tick-1, tick+1, tick+3 of every row (does it land?)
        work/final/edge.jpg                    full-size crop where the card meets the speaker (halo / double image / cutout drift)
Exit code 1 if the render does not have exactly the slot's frame count or was built with the safe guide on.
"""
import json
import os
import shutil
import subprocess
import sys

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
B = json.load(open('work/build.json'))
name = os.path.basename(os.getcwd())
mp4 = f'renders/{name}.mp4'
if not os.path.exists(mp4):
    sys.exit(f'{mp4} is missing: render first')
info = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                       'stream=nb_read_frames,width,height,r_frame_rate', '-of', 'csv=p=0', mp4], capture_output=True, text=True).stdout.strip()
w, h, rate, n = info.split(',')
ok = int(n) == B['frames'] and (w, h, rate) == ('1080', '1920', '30/1')
print(f'{mp4}: {w}x{h} {rate} fps, {n} frames (slot has {B["frames"]})  ' + ('OK' if ok else '!! MISMATCH'))
if B.get('safe_guide') or 'rgba(255,0,0,.28)' in open('index.html').read():
    print('!! index.html was built with SAFE=1: rebuild with `python3 build.py` and render again')
    ok = False
os.makedirs('work/final', exist_ok=True)
N = B['frames']
last = N - 1


def sel(frames):
    return '+'.join(f'eq(n\\,{min(max(f, 0), last)})' for f in frames)


beats = [0, B['f_in'] + 4, B['f_in'] + 12]
for _, say, tick in B['rows']:
    beats += [say + 2, tick + 3]
beats += [B['f_done'] + 4] + ([B['f_out'] - 1, B['f_out'] + 4] if B['f_out'] is not None else []) + [last]
cols = min(len(beats), 7)
rows = -(-len(beats) // cols)
subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vf', f"select='{sel(beats)}',scale=360:-1,tile={cols}x{rows}",
                '-frames:v', '1', '-q:v', '3', 'work/final/sheet.jpg'], check=True)
x, y, cw, ch = B['card']
px, py = max(0, x - 40), max(0, y - 40)
pw, ph = min(1080 - px, cw + 80), min(1920 - py, ch + 120)
ticks = [f for _, _, t in B['rows'] for f in (t - 1, t + 1, t + 3)]
subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vf', f"select='{sel(ticks)}',crop={pw}:{ph}:{px}:{py},scale=480:-1,"
                f"tile=3x{len(B['rows'])}", '-frames:v', '1', '-q:v', '3', 'work/final/ticks.jpg'], check=True)
edge = [B['rows'][0][1] + 2, B['rows'][-1][2] + 3, B['f_done'] + 10 if B['f_done'] + 10 < N else last]
subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vf', f"select='{sel(edge)}',crop={pw}:{ph}:{px}:{py},tile=3x1",
                '-frames:v', '1', '-q:v', '2', 'work/final/edge.jpg'], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', mp4, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27',
                '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                f'renders/{name}-phone.mp4'], check=True)
print(f'beats on work/final/sheet.jpg (left to right): {beats}')
print(f'wrote renders/{name}-phone.mp4, work/final/sheet.jpg, ticks.jpg, edge.jpg  -> LOOK at all three before reporting')
for wmsg in B.get('warnings', []):
    print('build warning still open: ' + wmsg)
sys.exit(0 if ok else 1)
