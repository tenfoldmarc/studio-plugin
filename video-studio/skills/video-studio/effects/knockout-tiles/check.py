#!/usr/bin/env python3
"""knockout-tiles / check: run after the render, from the slot folder (python with numpy and Pillow).

  python check.py      reads renders/<slot folder>.mp4 and prints / writes:
    - size, frame count against clip.json
    - plain edges: first frame, the frame before the effect, the frame it is over, last frame, each against the clip
    - face: how much the middle of the face differs from the clip while pieces are up (it must stay the clip)
    - work/check/sheet.jpg: every landing frame, the frame before it, and the knock / wipe frames, to LOOK at
    - renders/<slot folder>-phone.mp4 (720 x 1280 preview)
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
FP = shutil.which('ffprobe') or 'ffprobe'
W, H = 270, 480


def grab(path, frames):
    sel = '+'.join(f'eq(n\\,{f})' for f in frames)
    raw = subprocess.run([FF, '-v', 'error', '-i', path, '-vf', f"select='{sel}',scale={W}:{H}:flags=area", '-fps_mode', 'vfr',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.float32)
    return dict(zip(frames, a))


def main():
    name = os.path.basename(HERE)
    out = f'renders/{name}.mp4'
    if not os.path.exists(out):
        sys.exit(f'{out} is missing: render first')
    nfr = int(json.load(open('clip.json'))['frames'])
    lay = json.load(open('work/layout.json'))
    S = B.schedule(lay['at'], nfr, [g['spot'] for g in lay['tiles']])
    info = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                           'stream=width,height,nb_read_frames', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.strip()
    ok = info == f'1080,1920,{nfr}'
    print(f'render: {info}  (want 1080,1920,{nfr})  {"OK" if ok else "!! WRONG"}')

    edges = sorted({0, S['f_in'] - 1, S['f_out'], nfr - 1})
    beats = sorted({f for k in range(len(S['land'])) for f in (S['land'][k] - 1, S['land'][k], S['knock'][k] - 2, S['knock'][k] + 2)}
                   | {f for r in S['rec'] for f in (r - 1, r)}
                   | ({S['total'], S['wipe'] - 3, S['wipe'] + 4} if S['total'] is not None else set())
                   | ({S['wipe'] - 3, S['wipe'] + 4} if S['wipe'] is not None else set()))
    during = list(range(S['f_in'], S['f_out'], 3))
    want = sorted(set(edges + beats + during))
    R, A = grab(out, want), grab('assets/aroll.mp4', want)
    print('plain edges (mean difference from the clip, 0 to 255; under 2.5 = the same picture):')
    for f in edges:
        d = float(np.abs(R[f] - A[f]).mean())
        ok &= d < 2.5
        print(f'  f{f:4d}  {d:5.2f}  {"OK" if d < 2.5 else "!! NOT PLAIN"}')
    h = lay['head']
    hh = h['bottom'] - h['top']
    x0, x1 = int((h['cx'] - .25 * h['w']) / 4), int((h['cx'] + .25 * h['w']) / 4)
    y0, y1 = int((h['top'] + .4 * hh) / 4), int((h['top'] + .8 * hh) / 4)
    worst = max((float(np.abs(R[f][y0:y1, x0:x1] - A[f][y0:y1, x0:x1]).mean()), f) for f in during)
    face_ok = worst[0] < 6
    ok &= face_ok
    print(f'face: largest difference from the clip {worst[0]:.2f} on f{worst[1]}  {"OK (never covered)" if face_ok else "!! something is over the face"}')

    os.makedirs('work/check', exist_ok=True)
    cols = 6
    rows = (len(beats) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * W, rows * (H + 18)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    lands = set(S['land']) | set(S['rec']) | ({S['total']} if S['total'] is not None else set())
    for i, f in enumerate(beats):
        x, y = (i % cols) * W, (i // cols) * (H + 18)
        sheet.paste(Image.fromarray(R[f].astype(np.uint8)), (x, y + 18))
        d.line([(x, y + 18 + 55), (x + W, y + 18 + 55)], fill=(255, 60, 60))                # y 220
        d.line([(x, y + 18 + 367), (x + W, y + 18 + 367)], fill=(255, 60, 60))              # y 1470
        d.text((x + 4, y + 3), f'f{f}' + ('  LANDS' if f in lands else ''), fill=(255, 255, 255))
    sheet.save('work/check/sheet.jpg', quality=88)
    print(f'work/check/sheet.jpg: {len(beats)} frames (red lines = y 220 and y 1470). LOOK: on its LANDS frame each piece is flat on '
          'the wall at its resting size (the frame before, it is still flying in, bigger); pieces pass behind the speaker; '
          'nothing rests above or below the red lines')
    subprocess.run([FF, '-v', 'error', '-y', '-i', out, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27', '-preset',
                    'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', f'renders/{name}-phone.mp4'], check=True)
    print(f'renders/{name}-phone.mp4 written')
    print('CHECK ' + ('PASSED (now look at the sheet)' if ok else 'FAILED: see the lines marked !!'))


if __name__ == '__main__':
    main()
