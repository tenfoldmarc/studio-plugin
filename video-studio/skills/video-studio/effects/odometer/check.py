#!/usr/bin/env python3
"""odometer / check: prove the render before anyone watches it.

  1. frame count of renders/<slot>.mp4 == the a-roll's
  2. per frame: is any digit or label word behind their cutout? (work/layout.json from build.py + the matte)
  3. where the ticks landed in the audio (render minus a-roll) and how far under their voice they are
  4. contact sheet work/check/sheet.jpg (first frame, each roll, each lock, +0.5 s, last frame) and one full-size
     frame per lock in work/check/, renders/stills/<slot>-1..3.jpg, and the 720p phone copy renders/<slot>-phone.mp4

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

# 1 frames
n = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                        '-of', 'csv=p=0', R], capture_output=True, text=True).stdout.strip() or 0)
print(f'frames: render {n}, a-roll {N}  ' + ('OK' if n == N else '!! MISMATCH'))
ok &= n == N

# 2 readable rects vs the speaker's cutout
m = M.alpha()
c8 = M.CELL


def covered(rect, f0, f1):
    x0, y0, x1, y1 = rect
    seg = m[max(0, f0):min(N, f1 + 1), int(y0 // c8):int(-(-y1 // c8)), int(x0 // c8):int(-(-x1 // c8))]
    per = seg.reshape(len(seg), -1).mean(axis=1) if seg.size else np.zeros(1)
    return float(per.max()), int((per > .02).sum())


for c in L['counters']:
    f0, f1 = round(c['t_start'] * 30), round(c['t_end'] * 30)
    worst = max((covered(r, f0, f1) for r in c['readable']), default=(0, 0))
    flag = '' if worst[0] <= .02 else '   !! look at those frames'
    print(f"{c['id']} \"{c['text']}\" digits/label behind the speaker: worst frame {worst[0] * 100:.0f}% of a text box, {worst[1]} frames over 2%{flag}")
    ok &= worst[0] <= .10
    if 'chip' in c:
        worst = max((covered(r, round(c['chip']['t'] * 30), N - 1) for r in c['chip']['readable']), default=(0, 0))
        print(f"   chip: worst frame {worst[0] * 100:.0f}%, {worst[1]} frames over 2%")
        ok &= worst[0] <= .10
    x0, y0, x1, y1 = c['rect']
    safe = x0 >= 35 and x1 <= 1045 and y0 >= 220 and y1 <= 1470 and (y1 <= 1155 or x1 <= 980)
    print(f"   panel rect {c['rect']}  inside the safe zone: {'yes' if safe else '!! NO'}")
    ok &= safe


# 3 audio: where the sounds landed
def pcm(path):
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


a, b = pcm(os.path.join(HERE, 'assets/aroll.mp4')), pcm(R)
k = min(len(a), len(b))
if k > 4800:
    g = float(np.dot(a[:k], b[:k]) / max(np.dot(a[:k], a[:k]), 1e-9))
    d = b[:k] - g * a[:k]
    win = 480
    env = np.array([np.sqrt((d[i:i + win] ** 2).mean()) for i in range(0, k - win, win)])
    voice = np.array([np.sqrt((a[i:i + win] ** 2).mean()) for i in range(0, k - win, win)])
    vdb = 20 * np.log10(max(np.percentile(voice, 90), 1e-6))
    print(f'audio: their voice passes at gain {g:.2f}; loud speech {vdb:.0f} dB')
    for c in L['counters']:
        i = int(c['t_lock'] * 100)
        pk = env[max(0, i - 3):i + 8].max() if len(env) > i else 0
        db = 20 * np.log10(max(pk, 1e-6))
        print(f"   tick at lock {c['t_lock']:.2f}s: {db:.0f} dB ({vdb - db:.0f} dB under their voice)" + ('' if db < vdb - 6 else '  !! too loud'))

# 4 pictures
out = os.path.join(HERE, 'work', 'check')
os.makedirs(out, exist_ok=True)
os.makedirs(os.path.join(HERE, 'renders', 'stills'), exist_ok=True)
frames = [0]
for c in L['counters']:
    fl = round(c['t_lock'] * 30)
    frames += [round(c['t_start'] * 30) + 4, fl - 2, fl, fl + 2, fl + 15]
    if 'chip' in c:
        frames += [round(c['chip']['t'] * 30) - 5, round(c['chip']['t'] * 30) + 3]
frames = sorted({min(N - 1, max(0, f)) for f in frames + [N - 1]})
sel = '+'.join(f'eq(n\\,{f})' for f in frames)
cols = min(6, len(frames))
rows = -(-len(frames) // cols)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='{sel}',scale=360:-1,tile={cols}x{rows}", '-frames:v', '1', '-q:v', '2',
                os.path.join(out, 'sheet.jpg')], check=True)
stills = []
for c in L['counters']:
    stills += [round(c['t_lock'] * 30) + 12]
stills = (stills + [N - 1, round(L['counters'][0]['t_lock'] * 30)])[:3]
for i, f in enumerate(stills):
    f = min(N - 1, max(0, f))
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n\\,{f})'", '-frames:v', '1', '-q:v', '2',
                    os.path.join(HERE, 'renders', 'stills', f'{SLOT}-{i + 1}.jpg')], check=True)
for c in L['counters']:
    f = min(N - 1, round(c['t_lock'] * 30) + 1)
    subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', f"select='eq(n\\,{f})'", '-frames:v', '1', '-q:v', '2',
                    os.path.join(out, f"lock_{c['id']}_f{f}.jpg")], check=True)
subprocess.run([FF, '-v', 'error', '-y', '-i', R, '-vf', 'scale=720:1280', '-c:v', 'libx264', '-crf', '27', '-preset', 'slow',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                os.path.join(HERE, 'renders', f'{SLOT}-phone.mp4')], check=True)
print(f'sheet: work/check/sheet.jpg  (frames {frames})   stills: renders/stills/   phone copy: renders/{SLOT}-phone.mp4')
print('RESULT: ' + ('numbers check out, now LOOK at the sheet' if ok else '!! something above needs fixing'))
