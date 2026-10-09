#!/usr/bin/env python3
"""blackout prep. Run from the slot folder after the CLIP block in build.py is filled (numpy, scipy, Pillow):

    python prep.py            measure + clean the cutout edge (about 1 min)
    python prep.py measure    measure only (10 s): work/measure.json, for a first look at the numbers

Reads   assets/aroll.mp4, assets/subject.webm (the cutout made by fx_new.py), clip.json, the CLIP block of build.py
Writes  work/measure.json          head / neck / open room, measured on every frame the room is dim (build.py places
                                   the punch word, the push-in and the edge darkness from it)
        assets/subject_lit.webm    the cutout for a dim room: edge pulled in (EDGE_CHOKE) and its outer pixels
                                   recoloured from inside (EDGE_SPILL), so no wall-coloured rim stays lit around the
                                   speaker. Not written when both are 0 (the cutout is used as it is).
        work/check_sheet.jpg       4 frames of the dim room with the measured head box and neck line (a preview)
        work/check_edge.jpg        FULL SIZE crop of the head in the dim room: cutout as it came | cutout cleaned
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import build as B

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
C = json.load(open('clip.json'))
N = C['frames']
SNAP = B.snap_frame(C)
B.validate(N, SNAP)
SPAN = (B.F_DIM, (SNAP if SNAP is not None else N) - 1)      # frames on which the cutout is on screen
CLEAN = (B.EDGE_CHOKE > 0 or B.EDGE_SPILL > 0)
MEASURE_ONLY = sys.argv[1:] == ['measure']
if not os.path.exists('assets/subject.webm'):
    sys.exit('no assets/subject.webm: this effect needs the cutout (make the slot without --no-cutout)')


def reader(src, pix, alpha=False, select=None):
    vf = ['-vf', "select='" + '+'.join(f'eq(n\\,{f})' for f in select) + "'", '-fps_mode', 'passthrough'] if select else []
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + ['-i', src] + vf + ['-f', 'rawvideo', '-pix_fmt', pix, '-']
    ch = {'rgb24': 3, 'rgba': 4}[pix]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    while True:
        buf = p.stdout.read(W * H * ch)
        if len(buf) < W * H * ch:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, ch)
    p.wait()


def head_of(m):
    """m: half-size boolean matte. Returns head top, centre x, width, neck row (half-size px), neck found."""
    rows = m.sum(1)
    ok = (rows > 5) & (np.roll(rows, -1) > 5) & (np.roll(rows, -2) > 5)
    ys = np.where(ok[:-2])[0]
    if not len(ys):
        return None
    top = int(ys[0])
    xs = np.where(m[top + 1])[0]
    cx = float(xs.mean())
    rw, mid = [], []
    for y in range(top, m.shape[0]):
        xs = np.where(m[y])[0]
        if not len(xs):
            break
        cuts = np.where(np.diff(xs) > 3)[0]
        starts, ends = np.r_[xs[0], xs[cuts + 1]], np.r_[xs[cuts], xs[-1]]
        k = int(np.argmin(np.where((starts <= cx) & (ends >= cx), 0, np.minimum(abs(starts - cx), abs(ends - cx)))))
        rw.append(ends[k] - starts[k] + 1)
        mid.append((starts[k] + ends[k]) / 2)
        cx = .7 * cx + .3 * mid[-1]
    rw = ndimage.median_filter(np.array(rw, np.float32), 5)
    # head = widest run before the outline narrows (neck) and then grows clearly wider than the head (shoulders)
    wmax, ymax, sh, dip = 0.0, 0, None, 0
    for i, w in enumerate(rw):
        if dip >= 3:
            if w > 1.2 * wmax:
                sh = i
                break
        elif w > wmax:
            wmax, ymax, dip = float(w), i, 0
        elif w < .9 * wmax and i > 8:
            dip += 1
    if sh is None:                                   # no shoulders found (hood, long hair, head only): a guess
        return top, mid[ymax], wmax, min(m.shape[0] - 1, top + ymax + int(.6 * wmax)), False
    neck = ymax + int(np.argmin(rw[ymax:sh]))
    return top, mid[ymax], wmax, top + neck, True


def clean(fr):
    """one rgba frame of the cutout -> the same frame with its edge pulled in and recoloured from inside"""
    a = fr[..., 3].astype(np.float32) / 255
    ys, xs = np.where(a > .02)
    out = np.zeros_like(fr)
    if not len(ys):
        return out
    y0, y1, x0, x1 = max(0, ys.min() - 16), min(H, ys.max() + 17), max(0, xs.min() - 16), min(W, xs.max() + 17)
    a, rgb = a[y0:y1, x0:x1], fr[y0:y1, x0:x1, :3].astype(np.float32)
    a2 = a
    if B.EDGE_CHOKE > 0:                             # the half-way line of the edge becomes its outside
        a2 = np.minimum(a, np.clip((ndimage.gaussian_filter(a, B.EDGE_CHOKE) - .5) * 2, 0, 1))
    if B.EDGE_SPILL > 0:                             # outer pixels take the colour of the pixels further in
        s = float(B.EDGE_SPILL)
        core = np.clip((ndimage.gaussian_filter(a, s) - .5) * 2.4, 0, 1)
        den = ndimage.gaussian_filter(core, s)
        num = np.dstack([ndimage.gaussian_filter(rgb[..., c] * core, s) for c in range(3)])
        w = ((1 - core) * (den > .03))[..., None]
        rgb = rgb * (1 - w) + num / np.maximum(den, 1e-3)[..., None] * w
    out[y0:y1, x0:x1, :3] = np.clip(rgb + .5, 0, 255).astype(np.uint8)
    out[y0:y1, x0:x1, 3] = np.clip(a2 * 255 + .5, 0, 255).astype(np.uint8)
    return out


def dim_room(rgb):
    """numpy stand-in for the css filter on the room (preview pictures only)"""
    x = rgb.astype(np.float32) / 255 * B.DIM
    x = (x - .5) * (1 + .1 * B.COOL) + .5
    l = (x * np.array([.2126, .7152, .0722], np.float32)).sum(-1, keepdims=True)
    return np.clip(l + (x - l) * (1 - .38 * B.COOL), 0, 1) * 255


def over(room, cut):
    a = cut[..., 3:].astype(np.float32) / 255
    return (room * (1 - a) + cut[..., :3].astype(np.float32) * a).astype(np.uint8)


f0, f1 = SPAN
picks = sorted({f0 + 2, (f0 + B.F_PUNCH) // 2, min(f1, B.F_PUNCH + 6), f1})
enc = None
if CLEAN and not MEASURE_ONLY:
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30', '-i', '-',
                            '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '20', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4', '-metadata:s:v:0', 'alpha_mode=1',
                            'assets/subject_lit.webm'], stdin=subprocess.PIPE)
track, keep = {}, {}
lo, hi = np.full(H // 2, W, np.float32), np.zeros(H // 2, np.float32)
blank = np.zeros((H, W, 4), np.uint8).tobytes()
count = 0
for n, fr in enumerate(reader('assets/subject.webm', 'rgba', True)):
    count += 1
    if not (f0 <= n <= f1):
        if enc:
            enc.stdin.write(blank)
        continue
    m = fr[::2, ::2, 3] > 127
    h = head_of(m)
    if h is None:
        sys.exit(f'frame {n}: the cutout is empty. This effect needs the speaker cut out on every frame the room is dim.')
    track[n] = h
    if n >= B.F_PUNCH:                               # the speaker's outline while the punch word is on screen
        any_row = m.any(1)
        lo = np.where(any_row, np.minimum(lo, m.argmax(1) * 2), lo)
        hi = np.where(any_row, np.maximum(hi, (m.shape[1] - 1 - m[:, ::-1].argmax(1)) * 2), hi)
    out = clean(fr) if (enc or (CLEAN and n in picks)) else fr
    if enc:
        enc.stdin.write(out.tobytes())
    if n in picks:
        keep[n] = (fr.copy(), out)
if enc:
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit('ffmpeg could not write assets/subject_lit.webm')
if count != N or len(track) != f1 - f0 + 1:
    sys.exit(f'assets/subject.webm has {count} frames, the a-roll has {N}: cutout and a-roll do not match')

ids = sorted(track)
t_all = np.array([track[n][:4] for n in ids], np.float32) * 2    # full-size px
r_top, r_hx, _, r_neck = (float(v) for v in np.median(t_all, axis=0))        # the whole dim: lights, push-in
t = t_all[[i for i, n in enumerate(ids) if n >= B.F_PUNCH]]                  # while the word is on screen: the word
top, hx, hw, neck = (float(v) for v in np.median(t, axis=0))
hh = max(40.0, neck - top)
y0, y1 = int(max(0, top - .2 * hh) / 2), int(min(H - 2, neck) / 2)
S = {'head_x': round(hx, 1), 'head_top': round(top, 1), 'head_top_min': float(t[:, 0].min()),
     'head_top_range': float(t[:, 0].max() - t[:, 0].min()), 'head_w': round(hw, 1), 'head_h': round(hh, 1),
     'neck_y': round(neck, 1), 'neck_y_max': float(t[:, 3].max()),
     'free_left': float(lo[y0:y1 + 1].min() - 26 - 41), 'free_right': float(1039 - hi[y0:y1 + 1].max() - 26),
     'neck_found': bool(all(track[n][4] for n in ids))}
cw, ch = 540, 480
box = [int(min(max(hx - cw // 2, 0), W - cw)), int(min(max(top - 110, 0), H - ch))]
M = {'frames': N, 'stamp': B.stamp(SNAP), 'baked': not MEASURE_ONLY, 'cutout': 'cleaned' if CLEAN else 'as it came',
     'span': list(SPAN), 'summary': S, 'origin': [round(r_hx, 1), round((r_top + r_neck) / 2, 1)],
     'room': {'head_x': round(r_hx, 1), 'head_top': round(r_top, 1), 'neck_y': round(r_neck, 1),
              'head_h': round(max(40.0, r_neck - r_top), 1)},
     'left_edge': [float(v) for v in lo], 'right_edge': [float(v) for v in hi],
     'check': {'frame': picks[2], 'box': box, 'crop': [cw, ch]}}
json.dump(M, open('work/measure.json', 'w'))
print(f"measured f{f0}..f{f1}, the word from f{B.F_PUNCH}: head top y {S['head_top']:.0f} (moves {S['head_top_range']:.0f} px "
      f"while the word is up), centre x {S['head_x']:.0f}, "
      f"head {S['head_w']:.0f} x {S['head_h']:.0f}, neck y {S['neck_y']:.0f}, open room beside the head: left "
      f"{S['free_left']:.0f} px, right {S['free_right']:.0f} px, room above the head inside the safe zone: {top - 220:.0f} px")
if not S['neck_found']:
    print('  !! no clear neck / shoulders on some frames (hood, long hair, hands at the head): check the green box')
if MEASURE_ONLY:
    sys.exit(0)

# check pictures: the dim room as numpy sees it (the real one is the css filter; this is close enough to judge edges)
rooms = dict(zip(picks, (dim_room(f) for f in reader('assets/aroll.mp4', 'rgb24', select=picks))))
sheet = Image.new('RGB', (270 * len(picks), 480))
for i, n in enumerate(picks):
    im = Image.fromarray(over(rooms[n], keep[n][1])).resize((270, 480), Image.BILINEAR)
    d = ImageDraw.Draw(im)
    tt, cx, ww, nk = (v * 2 / 4 for v in track[n][:4])
    d.rectangle((cx - ww / 2, tt, cx + ww / 2, nk), outline=(0, 255, 0))
    d.text((5, 5), f'f{n}', fill=(255, 255, 0))
    sheet.paste(im, (270 * i, 0))
sheet.save('work/check_sheet.jpg', quality=88)
n = picks[2]
edge = Image.new('RGB', (cw * 2 + 8, ch + 30), (20, 20, 20))
d = ImageDraw.Draw(edge)
for i, (name, cut) in enumerate((('cutout as it came', keep[n][0]), ('cutout cleaned (what renders)' if CLEAN else 'no cleaning asked', keep[n][1]))):
    full = Image.fromarray(over(rooms[n], cut))
    edge.paste(full.crop((box[0], box[1], box[0] + cw, box[1] + ch)), (i * (cw + 8), 30))
    d.text((i * (cw + 8) + 6, 9), f'{name}  f{n}  1:1', fill=(255, 255, 0))
edge.save('work/check_edge.jpg', quality=95)
print(('wrote assets/subject_lit.webm, ' if CLEAN else 'cutout used as it came, ') + 'look at: work/check_sheet.jpg, work/check_edge.jpg (full size)')
