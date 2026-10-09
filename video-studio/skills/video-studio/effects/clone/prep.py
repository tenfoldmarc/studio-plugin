#!/usr/bin/env python3
"""clone / prep: measure a new clip so the CLIP block in build.py can be filled from numbers, not by eye.

Run from the slot folder with the skill's Python (PY) (numpy, PIL, scipy):
    PY prep.py

Reads   assets/aroll.mp4, assets/subject.webm, clip.json, words.json
Writes  work/measure.json     their head anchor, head size and the widest their cutout gets (used by build.py + bake.py)
        work/alpha_half.npy   half-res alpha of every frame (bake.py reuses it for the camera track)
        work/onsets.txt       per-frame audio level with the Whisper words next to it + a suggested "hit" frame per word
        work/prep/grid_*.jpg  frames with a 100 px grid, their outline and the free wall space: read x / y for
                              CLONES and OCCLUDER_LINE from these
"""
import json
import os
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
HW, HH = W // 2, H // 2
N = json.load(open(os.path.join(HERE, 'clip.json')))['frames']
os.makedirs(os.path.join(HERE, 'work/prep'), exist_ok=True)


def alpha_half():
    raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', os.path.join(HERE, 'assets/subject.webm'), '-vf',
                          f'alphaextract,scale={HW}:{HH}:flags=area', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, HH, HW)
    if len(a) != N:
        raise SystemExit(f'subject.webm has {len(a)} frames, clip.json says {N}: the cutout would drift. Re-make the slot.')
    np.save(os.path.join(HERE, 'work/alpha_half.npy'), a)
    return a


def measure(A):
    rows = []
    for f, a in enumerate(A):
        m = a > 128
        ys, xs = np.where(m)
        if not len(ys):
            raise SystemExit(f'frame {f}: empty cutout')
        top = ys.min()
        # head: the widest run of mask in the rows just under the top (hands held above the head are narrower)
        band = m[top + 8:top + 60]
        cols = np.where(band.mean(axis=0) > .5)[0]
        if not len(cols):
            cols = np.where(band.any(axis=0))[0]
        runs = np.split(cols, np.where(np.diff(cols) > 3)[0] + 1)
        run = max(runs, key=len)
        rows.append(dict(f=f, x0=int(xs.min() * 2), x1=int(xs.max() * 2), y0=int(top * 2), y1=int(ys.max() * 2),
                         hx0=int(run.min() * 2), hx1=int(run.max() * 2)))
    hw = float(np.median([r['hx1'] - r['hx0'] for r in rows]))
    ok = [r for r in rows if abs((r['hx1'] - r['hx0']) - hw) < .25 * hw]        # frames where that run really is the head
    ax = float(np.median([(r['hx0'] + r['hx1']) / 2 for r in ok]))
    ay = float(np.median([r['y0'] for r in ok]))
    # head height: from the top down to where the mask gets clearly wider than the head (shoulders)
    union_w = (A[::3] > 128).mean(axis=0)
    width_at = (union_w > .5).sum(axis=1) * 2
    y = int(ay / 2) + 20
    while y < HH - 1 and width_at[y] < 1.45 * hw:
        y += 1
    hh = float(np.clip(y * 2 - ay, 1.3 * hw, 1.9 * hw))        # a raised arm can fool the walk: keep it head-shaped
    M = dict(frames=N, anchor=[round(ax, 1), round(ay, 1)], head_w=round(hw, 1), head_h=round(hh, 1),
             src_x=[min(r['x0'] for r in rows), max(r['x1'] for r in rows)],
             src_y=[min(r['y0'] for r in rows), max(r['y1'] for r in rows)],
             widest_frame=int(max(rows, key=lambda r: r['x1'] - r['x0'])['f']), per_frame=rows)
    json.dump(M, open(os.path.join(HERE, 'work/measure.json'), 'w'))
    print(f"head anchor (centre x, top y): {M['anchor']}   head {M['head_w']:.0f} x {M['head_h']:.0f} px")
    print(f"cutout extents over the clip: x {M['src_x']}  y {M['src_y']}   widest at frame {M['widest_frame']}")
    return M


def onsets():
    raw = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-ac', '1', '-ar', '48000', '-f',
                          's16le', '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = 1600
    db = np.array([20 * np.log10(np.sqrt((a[f * n:(f + 1) * n] ** 2).mean()) + 1e-6) for f in range(len(a) // n)])
    words = json.load(open(os.path.join(HERE, 'words.json'))) if os.path.exists(os.path.join(HERE, 'words.json')) else []
    hits = []
    for w in words:
        # "hit" = first frame of the word's vowel: find the loudest frame inside the word (skipping its first frame,
        # which is often the tail of the word before), then walk back while the level stays within 6 dB of it
        f0, f1 = min(len(db) - 1, int(w['start'] * 30) + 1), min(len(db) - 1, int(w['end'] * 30) + 1)
        f1 = max(f1, f0)
        hit = f0 + int(np.argmax(db[f0:f1 + 1]))
        peak = db[hit]
        while hit > 0 and db[hit - 1] >= peak - 6:
            hit -= 1
        hits.append((w['text'], round(w['start'] * 30), hit))
    lines = ['frame  time   dB    level                                    whisper word (start frame) -> hit frame']
    for f, v in enumerate(db):
        tag = '   '.join(f'{t} (whisper f{s}) -> HIT' for t, s, h in hits if h == f)
        lines.append(f'{f:4d} {f / 30:6.2f} {v:6.1f}  ' + ('#' * max(0, int((v + 60) / 1.5))).ljust(40) + ' ' + tag)
    open(os.path.join(HERE, 'work/onsets.txt'), 'w').write('\n'.join(lines) + '\n')
    print('word hits (frame the vowel lands on):  ' + '  '.join(f'{t}={h}' for t, s, h in hits))
    print('   full envelope in work/onsets.txt: check each hit you use, Whisper can be 0.1 to 0.3s off')


def grid(A, M):
    """frames with a 100px grid, their outline (yellow) and everywhere the speaker ever is (red tint): free wall = no tint"""
    ever = (A > 128).any(axis=0)
    for f in sorted({0, N // 2, M['widest_frame'], N - 1}):
        raw = subprocess.run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vf', f'select=eq(n\\,{f})', '-vframes',
                              '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True).stdout
        im = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32)
        ev = np.repeat(np.repeat(ever, 2, axis=0), 2, axis=1)
        im[..., 0] = np.where(ev, im[..., 0] * .7 + 255 * .3, im[..., 0])
        m = np.repeat(np.repeat(A[f] > 128, 2, axis=0), 2, axis=1)
        edge = m ^ ndimage.binary_erosion(m, iterations=3)
        im[edge] = (250, 230, 122)
        pic = Image.fromarray(im.astype(np.uint8))
        d = ImageDraw.Draw(pic)
        for x in range(0, W, 100):
            d.line([(x, 0), (x, H)], fill=(255, 255, 255) if x % 500 == 0 else (150, 220, 255), width=1)
            d.text((x + 3, 3), str(x), fill=(255, 255, 255))
        for y in range(0, H, 100):
            d.line([(0, y), (W, y)], fill=(255, 255, 255) if y % 500 == 0 else (150, 220, 255), width=1)
            d.text((3, y + 3), str(y), fill=(255, 255, 255))
        ax, ay = M['anchor']
        d.line([(ax - 30, ay), (ax + 30, ay)], fill=(255, 60, 60), width=3)
        d.line([(ax, ay - 30), (ax, ay + 30)], fill=(255, 60, 60), width=3)
        p = os.path.join(HERE, f'work/prep/grid_{f:03d}.jpg')
        pic.save(p, quality=88)
        print('grid frame', p)


if __name__ == '__main__':
    A = alpha_half()
    M = measure(A)
    onsets()
    grid(A, M)
    print('\nnext: fill the CLIP block in build.py (CLONES x/top/scale, OCCLUDER_LINE from the grid frames), then bake.py')
