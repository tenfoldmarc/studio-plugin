#!/usr/bin/env python3
"""phone-mockup / prep: the two files build.py needs beside the slot's own.

1. assets/subject_soft.webm (LAYER = 'behind'): the cutout with its matte pulled in 2 px and feathered, so a cap, an ear
   or a hand never carries a light fringe of wall against the dark phone. Colour is untouched. Optional, from the CLIP
   block: HAND_FRAMES (wider feather on a fast, blurred hand) and MATTE_FIX {frame: px} (shave the matte inside the phone).
2. assets/screen.mp4 / assets/screen.<png|jpg> (SCREEN set): the buyer's recording cut to the slot (from SCREEN_START,
   30 fps, no sound, last frame held if it is shorter) or their picture, sized for the glass.

Slot folder, the skill's Python (PY) (takes about a minute; on a shared machine run it through the slot runner):
    PY prep.py
"""
import os
import shutil
import subprocess
import sys

import numpy as np
from scipy import ndimage

import build as B
import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920


def soften():
    src, out = os.path.join(HERE, 'assets/subject.webm'), os.path.join(HERE, 'assets/subject_soft.webm')
    if not os.path.exists(src):
        sys.exit('no assets/subject.webm: re-make the slot without --no-cutout, or set LAYER = "front"')
    roi = None
    if B.MATTE_FIX:                                   # phone body in the clip's own coordinates (undo the ROOM reframe)
        L = B.layout()
        r = L['room'] or dict(scale=1, x=0, y=0)
        x0, y0, x1, y1 = [(v - (r['x'] if i % 2 == 0 else r['y'])) / r['scale'] for i, v in enumerate(L['bounds'])]
        roi = np.zeros((H, W), np.float32)
        roi[max(0, int(y0) + 6):int(y1) - 6, max(0, int(x0) + 6):int(x1) - 6] = 1
        roi = ndimage.gaussian_filter(roi, 5)
    dec = subprocess.Popen([FF, '-loglevel', 'error', '-c:v', 'libvpx-vp9', '-i', src, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([FF, '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                            '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '18', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '3', '-metadata:s:v:0', 'alpha_mode=1', out],
                           stdin=subprocess.PIPE)
    size, n = W * H * 4, 0
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        f = np.frombuffer(buf, np.uint8).reshape(H, W, 4).copy()
        a = f[..., 3].astype(np.float32) / 255
        soft = ndimage.gaussian_filter(ndimage.grey_erosion(a, size=(5, 5)), 6 if n in B.HAND_FRAMES else 1.3)
        if n in B.MATTE_FIX:
            px = int(B.MATTE_FIX[n])
            hard = ndimage.gaussian_filter(ndimage.grey_erosion(a, size=(px, px)), 6)
            soft = soft * (1 - roi) + hard * roi
        f[..., 3] = np.clip(soft * 255 + .5, 0, 255).astype(np.uint8)
        enc.stdin.write(f.tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    dec.wait()
    want = M.clip()['frames']
    print(f'subject_soft.webm: {n} frames' + ('' if n == want else f'  !! the a-roll has {want}: the cutout would drift'))


def screen():
    src = os.path.join(HERE, B.SCREEN)
    if not os.path.exists(src):
        sys.exit(f'SCREEN = "{B.SCREEN}" is not there. Copy the buyer\'s own recording or picture into the slot\'s screen/ folder.')
    if B.IS_VIDEO:
        out = os.path.join(HERE, 'assets/screen.mp4')
        subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{float(B.SCREEN_START):.3f}', '-i', src, '-an', '-vf',
                        f"fps=30,scale=-2:'min(1280,ih)':flags=lanczos,setsar=1,tpad=stop_mode=clone:stop_duration={B.DUR + 1:.2f}",
                        '-frames:v', str(B.N), '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-g', '15', out],
                       check=True)
        print(f'assets/screen.mp4: {B.N} frames of {B.SCREEN} from {float(B.SCREEN_START):.2f}s')
    else:
        from PIL import Image
        ext = os.path.splitext(B.SCREEN)[1].lower()
        im = Image.open(src)
        im.thumbnail((1400, 2800))
        if ext in ('.jpg', '.jpeg'):
            im = im.convert('RGB')
        im.save(os.path.join(HERE, 'assets', f'screen{ext}'))
        print(f'assets/screen{ext}: {im.size[0]} x {im.size[1]} from {B.SCREEN}')


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'assets'), exist_ok=True)
    if B.SCREEN:
        screen()
    if B.LAYER == 'behind':
        soften()
    else:
        print('LAYER = "front": no soft cutout needed')
