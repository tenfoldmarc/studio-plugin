#!/usr/bin/env python3
"""pointer-callout / check.py: numbers and pictures from the FINAL render. numpy + Pillow only.

Reads  renders/<slot folder>.mp4, assets/aroll.mp4, clip.json, work/track.json, work/layout.json
Prints frame count, which frames differ from the a-roll (frame 0 and the last frame must be plain), pixels changed
       outside the safe zone and inside the face (both must be 0), the frame each card is first seen on.
Writes work/check/sheet.jpg  6 frames side by side: safe zone in red, head box in blue
       work/check/lock.jpg   one row per card: crops centred on the point its line is tied to. The dot sits on the
                             same spot of the speaker in every crop; a dot that wanders = weak track
       work/check/stills/1.jpg 2.jpg 3.jpg, renders/<slot folder>-phone.mp4 (720 x 1280)
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
NAME = os.path.basename(HERE)
OUTV = os.path.join(HERE, 'renders', NAME + '.mp4')
W, H = 1080, 1920


def stream(path, w, h, fmt):
    ch = 3 if fmt == 'rgb24' else 1
    p = subprocess.Popen([FF, '-v', 'error', '-i', path, '-vf', f'scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', fmt, '-'],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(w * h * ch)
        if len(b) < w * h * ch:
            break
        a = np.frombuffer(b, np.uint8)
        yield a.reshape(h, w, 3) if ch == 3 else a.reshape(h, w)


if not os.path.exists(OUTV):
    sys.exit(f'check.py: {OUTV} is missing. Render first.')
clip = json.load(open(os.path.join(HERE, 'clip.json')))
track = json.load(open(os.path.join(HERE, 'work/track.json')))
lay = json.load(open(os.path.join(HERE, 'work/layout.json')))
box = np.array(track['box'])
yy, xx = np.mgrid[0:H // 2, 0:W // 2] * 2
unsafe = (yy < 220) | (yy >= 1470) | (xx < 35) | (xx >= 1045) | ((yy >= 1155) & (xx >= 980))

changed, out_px, face_px, seen = [], 0, 0, {c['id']: None for c in lay['cards']}
for f, (r, a) in enumerate(zip(stream(OUTV, W // 2, H // 2, 'gray'), stream(os.path.join(HERE, 'assets/aroll.mp4'), W // 2, H // 2, 'gray'))):
    d = np.abs(r.astype(np.int16) - a.astype(np.int16)) > 28
    changed.append(int(d.sum()))
    out_px = max(out_px, int((d & unsafe).sum()))
    b = box[min(f, len(box) - 1)]
    bw, bh = b[2] - b[0], b[3] - b[1]
    face = (xx > b[0] + .1 * bw) & (xx < b[2] - .1 * bw) & (yy > b[1] + .36 * bh) & (yy < b[3])       # brows to chin
    face_px = max(face_px, int((d & face).sum()))
    for c in lay['cards']:
        x, y, w, h = c['rect']
        if seen[c['id']] is None and d[y // 2:(y + h) // 2, x // 2:(x + w) // 2].mean() > .3:
            seen[c['id']] = f
n = len(changed)
on = [f for f, v in enumerate(changed) if v >= 12]
print(f"frames: {n} (clip.json says {clip['frames']})" + ('' if n == clip['frames'] else '   !! FRAME COUNT MISMATCH'))
if on:
    print(f'differs from the a-roll on frames {on[0]}..{on[-1]}; plain on 0..{on[0] - 1} and {on[-1] + 1}..{n - 1}'
          + ('' if on[0] > 0 and on[-1] < n - 1 else '   !! THE FIRST OR LAST FRAME IS NOT PLAIN'))
else:
    print('!! the render never differs from the a-roll: no card came on')
print(f'changed pixels outside the safe zone (worst frame): {out_px}' + ('' if out_px == 0 else '   !! look at sheet.jpg'))
print(f'changed pixels inside the face (worst frame): {face_px}' + ('' if face_px == 0 else '   !! a card, line or shadow touches the face'))
for c in lay['cards']:
    s = seen[c['id']]
    late = '' if s is not None and abs(s - c['f_word']) <= 3 else '   !! not on its word'
    print(f"  '{c['text']}': first seen frame {s}, word at frame {c['f_word']}{late}")

# pictures
lands = [c['f_in'] + 9 for c in lay['cards']]
tracks = np.array([np.array(c['track'])[:n] for c in lay['cards']])
speed = np.r_[0, np.hypot(np.diff(tracks[..., 0], axis=1), np.diff(tracks[..., 1], axis=1)).max(0)]
speed[:max(lands) + 4] = 0
speed[lay['out'] - 6:] = 0
sheet_f = set([min(n - 1, v + 8) for v in lands] + [int(np.argmax(speed)), lay['out'] - 8])   # landings, fastest move, end
for v in np.linspace(max(lands) + 14, lay['out'] - 14, 6):
    if len(sheet_f) < 6:
        sheet_f.add(int(v))
sheet_f = sorted(sheet_f)[:6]
lock_f = {c['id']: [int(v) for v in np.linspace(c['f_in'] + 12, lay['out'] - 8, 6)] for c in lay['cards']}
still_f = [min(n - 1, lands[0] + 8), min(n - 1, lands[-1] + 10), lay['out'] - 10]
want = set(sheet_f) | set(still_f) | {v for vs in lock_f.values() for v in vs}
frames = {f: Image.fromarray(fr) for f, fr in enumerate(stream(OUTV, W, H, 'rgb24')) if f in want}
os.makedirs(os.path.join(HERE, 'work/check/stills'), exist_ok=True)
sheet = Image.new('RGB', (180 * len(sheet_f), 320))
for j, f in enumerate(sheet_f):
    im = frames[f].copy()
    dr = ImageDraw.Draw(im)
    dr.line([(35, 1470), (35, 220), (1045, 220), (1045, 1155), (980, 1155), (980, 1470), (35, 1470)], fill=(255, 40, 40), width=5)
    dr.rectangle([float(v) for v in box[min(f, len(box) - 1)]], outline=(60, 140, 255), width=5)
    try:
        dr.text((50, 1500), f'f{f}', fill=(255, 255, 255), font_size=90)
    except TypeError:                               # older Pillow: small default font
        dr.text((50, 1500), f'f{f}', fill=(255, 255, 255))
    sheet.paste(im.resize((180, 320), Image.LANCZOS), (180 * j, 0))
sheet.save(os.path.join(HERE, 'work/check/sheet.jpg'), quality=88)
lock = Image.new('RGB', (180 * 6, 180 * len(lay['cards'])))
R = int(max(90, .6 * track['hw']))
for i, c in enumerate(lay['cards']):
    t = np.array(c['track'])
    for j, f in enumerate(lock_f[c['id']]):
        x, y = t[min(f, len(t) - 1)]
        lock.paste(frames[f].crop((int(x - R), int(y - R), int(x + R), int(y + R))).resize((180, 180), Image.LANCZOS), (180 * j, 180 * i))
lock.save(os.path.join(HERE, 'work/check/lock.jpg'), quality=88)
for j, f in enumerate(still_f):
    frames[f].save(os.path.join(HERE, f'work/check/stills/{j + 1}.jpg'), quality=90)
phone = os.path.join(HERE, 'renders', NAME + '-phone.mp4')
subprocess.run([FF, '-v', 'error', '-y', '-i', OUTV, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27',
                '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', phone], check=True)
print(f'sheet frames {sheet_f}; lock crops ({2 * R} px wide) per card at {list(lock_f.values())[0]} ...; wrote work/check/sheet.jpg, lock.jpg, stills/, {os.path.basename(phone)}')
