#!/usr/bin/env python3
"""pull-back-reveal / check: run after the render, from the slot folder (python with numpy and Pillow).

  python check.py      reads renders/<slot folder>.mp4 and prints / writes:
    - size and frame count against clip.json
    - plain edges: first frame, the frame before the shrink, the frame the picture is back, last frame, each
      compared with the clip (they must be the same picture)
    - work/check/sheet.jpg: the beats, to LOOK at (red lines = y 220 and y 1470, the safe zone's top and bottom)
    - renders/<slot folder>-phone.mp4 (720 x 1280 preview)
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.dont_write_bytecode = True
import build as B  # noqa: E402

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
    if 'rgba(255,0,0,.28)' in open('index.html').read():
        print('!! index.html still has the red safe-zone guide: run build.py without SAFE=1 and render again')
    nfr = int(json.load(open('clip.json'))['frames'])
    S = B.schedule(nfr)
    info = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                           'stream=width,height,nb_read_frames', '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.strip()
    ok = info == f'1080,1920,{nfr}'
    print(f'render: {info}  (want 1080,1920,{nfr})  {"OK" if ok else "!! WRONG"}')

    edges = sorted({0, S['f_in'] - 1} | ({S['f_out'], nfr - 1} if S['f_out'] is not None else set()))
    beats = [('before', S['f_in'] - 1), ('shrinking', S['f_in'] + 4), ('landed', S['land'] + 1), ('tick 1', S['ticks'][0]),
             ('ticking', S['ticks'][len(S['ticks']) // 2]), ('before done', S['done'] - 1), ('DONE', S['done']),
             ('after done', S['done'] + 6)]
    if S['label']:
        beats.append(('label', S['label'][-1] + 6))
    if S['name'] is not None:
        beats.append(('name', S['name'] + 8))
    if S['f_out'] is not None:
        beats += [('holding', S['out0'] - 2), ('growing', S['out0'] + 6), ('back', S['f_out']), ('last', nfr - 1)]
    else:
        beats.append(('last (cut here)', nfr - 1))
    want = sorted(set(edges) | {f for _, f in beats})
    R, A = grab(out, want), grab('assets/aroll.mp4', want)
    # A render shifts tone and colour a little on every pass (fx_add.py measures that and takes it back out), so the
    # test is made after fitting one gain and offset per colour channel: what is left is a difference in the PICTURE.
    print('plain edges (difference from the clip, 0 to 255, once the render\'s overall tone shift is taken out; '
          'under 2.5 = the same picture):')
    for f in edges:
        raw = float(np.abs(R[f] - A[f]).mean())
        res = []
        for c in range(3):
            g, o = np.polyfit(A[f][..., c].ravel(), R[f][..., c].ravel(), 1)
            res.append(float(np.abs(R[f][..., c] - (g * A[f][..., c] + o)).mean()))
        d = sum(res) / 3
        ok &= d < 2.5
        print(f'  f{f:4d}  {d:5.2f}  (before the tone fit {raw:5.2f})  {"OK" if d < 2.5 else "!! NOT PLAIN"}')
    if S['f_out'] is None:
        print("F_OUT = 'cut': the window is still on screen on the last frame, the reel has to cut there")

    os.makedirs('work/check', exist_ok=True)
    cols = 7
    rows = (len(beats) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * W, rows * (H + 18)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (label, f) in enumerate(beats):
        x, y = (i % cols) * W, (i // cols) * (H + 18)
        sheet.paste(Image.fromarray(R[f].astype(np.uint8)), (x, y + 18))
        d.line([(x, y + 18 + 55), (x + W, y + 18 + 55)], fill=(255, 60, 60))                # y 220
        d.line([(x, y + 18 + 367), (x + W, y + 18 + 367)], fill=(255, 60, 60))              # y 1470
        d.text((x + 4, y + 3), f'f{f}  {label}', fill=(255, 255, 255))
    sheet.save('work/check/sheet.jpg', quality=88)
    print(f'work/check/sheet.jpg: {len(beats)} frames. LOOK: the face is clear of the panel, the title bar and the strip; '
          'every step is ticked and the counter shows its number on the DONE frame, not one frame later; nothing sits '
          'outside the red lines; "back" and "last" are the plain picture')
    subprocess.run([FF, '-v', 'error', '-y', '-i', out, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-crf', '27', '-preset',
                    'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', f'renders/{name}-phone.mp4'], check=True)
    print(f'renders/{name}-phone.mp4 written')
    print('CHECK ' + ('PASSED (now look at the sheet)' if ok else 'FAILED: see the lines marked !!'))


if __name__ == '__main__':
    main()
