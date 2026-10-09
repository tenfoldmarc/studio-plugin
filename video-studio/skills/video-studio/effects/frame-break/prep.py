#!/usr/bin/env python3
"""frame-break prep: measures the speaker from the cutout, places the card, bakes the two layers the page needs.

Run from the slot folder (any python with numpy and Pillow):
    python prep.py            measure + bake      -> work/measure.json, work/check.jpg,
                                                     assets/subject_fade.webm, assets/backdrop.mp4
    python prep.py measure    measure only (5 s): use it while you tune HEAD_OUT / CARD / HEAD, then run it plain

What is measured (nothing is typed in):
  head      top, width and chin line per frame, by walking down the cutout's silhouette from the top (no face model)
  card      a 9:16 window under the head: its top edge sits HEAD_OUT head heights below the top of the head, it is
            centred on the head and reaches the bottom of the frame
  pop zone  the cutout is kept from the top of the frame down to Y0 and faded out by Y1. Y1 stops where the resting
            body outline (median over the slot) leaves the card's sides, so only moving hands come out sideways
  reach     how far head and hands rise above the card (sets the size of the card on screen) and whether the hands
            pass the card's sides at all. If they never do, the effect is a head pop-out and prep says so
LOOK at work/check.jpg: cyan = card, green = head box, yellow lines = Y0 / Y1, pink = what comes out of the card.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H = 1080, 1920
K = 4
AW, AH = W // K, H // K
NECK_RATIO = 0.8           # the neck is found where the silhouette gets this much narrower than the head
CHIN_K = 1.5               # chin = head top + CHIN_K * head width (lands on the chin or a little under it)
ASPECT = 9 / 16            # card width / height
SHRINK, GROW = 21, 16      # frames the shrink and the grow-back take (build.py uses the same numbers)
ZONE = (245, 1435)         # screen band the card and what rises out of it must fit in (safe zone 220 to 1470)
PUSH = 1.03                # slow push-in while the card floats (build.py uses the same number)

src = open('build.py').read()
C = {}
exec(src.split('# ==== CLIP (edit this) ====')[1].split('# ==== END CLIP ====')[0], C)
clip = json.load(open('clip.json'))
N = clip['frames']
F_IN, F_OUT = C['F_IN'], C['F_OUT']
a0 = F_IN - SHRINK
if a0 < 2:
    sys.exit(f'F_IN = {F_IN}: the shrink takes {SHRINK} frames and the slot must open on plain footage. F_IN must be {SHRINK + 2} or later')
if F_OUT is not None and not (F_IN + 45 <= F_OUT <= N - 2):
    sys.exit(f'F_OUT = {F_OUT}: it must be at least 45 frames after F_IN ({F_IN + 45}) and at most {N - 2} (2 plain frames close the slot)')
z1 = F_OUT if F_OUT is not None else N - 1
if not os.path.exists('assets/subject.webm'):
    sys.exit('no assets/subject.webm: this effect needs the cutout (make the slot without --no-cutout)')


# ------------------------------------------------------------------------------------------------- read the cutout
p = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
                    f'alphaextract,scale={AW}:{AH}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True)
A = np.frombuffer(p.stdout, dtype=np.uint8)
A = A[:len(A) // (AW * AH) * AW * AH].reshape(-1, AH, AW)
if len(A) != N:
    print(f'!! cutout has {len(A)} frames, the slot has {N}: the pop-out will drift. Re-make the cutout')
z1 = min(z1, len(A) - 1)
win = list(range(a0, z1 + 1))


def runs(row):
    d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def head_of(mask):
    """walk down the head's own run of pixels from the top of the silhouette -> (top, width, centre x) or None"""
    rows = np.flatnonzero(mask.sum(1) >= 3)
    if len(rows) == 0:
        return None
    prof, x0, x1 = [], None, None
    for y in range(rows[0], AH):
        rs = [r for r in runs(mask[y]) if r[1] - r[0] >= 2]
        if not rs:
            if prof:
                break
            continue
        if x0 is None:
            r = max(rs, key=lambda r: r[1] - r[0])
        else:
            best = max(((min(r[1], x1) - max(r[0], x0), r) for r in rs), key=lambda o: o[0])
            if best[0] <= 0:
                break
            r = best[1]
        x0, x1 = r
        prof.append((y, x0, x1))
    if len(prof) < 12:
        return None
    w = np.array([q[2] - q[1] for q in prof], dtype=float)
    ws = np.array([np.median(w[max(0, i - 2):i + 3]) for i in range(len(w))])
    m, i_w = 0.0, 0
    for i, v in enumerate(ws):
        if v > m:
            m, i_w = v, i
        elif i - i_w > 2 and v < NECK_RATIO * m and i > 0.6 * m:
            return prof[0][0] * K, m * K, (prof[i_w][1] + prof[i_w][2]) / 2 * K
    return None


notes = []
if C['HEAD']:
    top, chin = C['HEAD']
    head_h = chin - top
    cols = np.flatnonzero((A[win] > 128)[:, int(top) // K:int(chin) // K].any(axis=(0, 1)))
    cx = float(cols.mean() * K) if len(cols) else W / 2
    head_w = head_h / CHIN_K
    notes.append('head taken from HEAD (typed in)')
else:
    hs = [h for h in (head_of(A[f] > 128) for f in win) if h]
    if not hs:
        sys.exit('could not find a head in the cutout (no neck under it: hood, hair over the shoulders, hands at the '
                 'face). Set HEAD = (top_y, chin_y) in build.py, read off a frame of assets/aroll.mp4')
    wmed = float(np.median([h[1] for h in hs]))
    hs = [h for h in hs if .72 * wmed <= h[1] <= 1.3 * wmed] or hs       # a width jump = a hand merged into the head
    top, head_w, cx = (float(np.median([h[i] for h in hs])) for i in range(3))
    head_h = CHIN_K * head_w
    chin = top + head_h
    if len(hs) < .5 * len(win):
        notes.append(f'head found on only {len(hs)} of {len(win)} frames: check the green box')

# ------------------------------------------------------------------------------------------------------- the card
ho = C['HEAD_OUT']
if ho == 'auto':           # a big head (medium shot): hair and forehead. A small head (wide shot): the whole head
    ho = .30 + .70 * min(max((420 - head_h) / 120, 0.0), 1.0)
pop = float(ho) * head_h
if C['CARD']:
    RX, RY, RW, RH = (float(v) for v in C['CARD'])
    if RX < 0 or RY < 0 or RX + RW > W or RY + RH > H:
        sys.exit('CARD must lie inside the 1080x1920 frame')
else:
    RY = min(max(top + pop, 0.0), H - 500.0)
    RH = H - RY
    RW = min(RH * ASPECT, 1000.0)
    RX = min(max(cx - RW / 2, 0.0), W - RW)
RX, RY, RW, RH = (round(v) for v in (RX, RY, RW, RH))

# resting body: what the cutout covers on 85% of the card's frames (torso and shoulders; moving hands are not in it)
M = A[win] > 128
rest = M.mean(axis=0) >= .85
y_out = None
for y in range(RY // K + 1, min(AH, (RY + RH) // K)):
    xs = np.flatnonzero(rest[y]) * K
    if len(xs) and (xs.min() < RX - 8 or xs.max() + K > RX + RW + 8):
        y_out = y * K
        break
ramp = max(60.0, .28 * head_h)
Y1 = RY + .38 * RH                       # never lower than the chest of a card-sized body
if y_out is not None:
    Y1 = min(Y1, y_out + ramp)           # the fade starts where the resting body leaves the card's sides
Y0 = Y1 - ramp
if Y0 < RY + 8:
    Y0, Y1 = RY + 8, RY + 8 + ramp
if not C['SIDE_POP']:
    Y0, Y1 = RY + 8, RY + 48
Y0, Y1 = round(Y0), round(Y1)

# what comes out of the card: cutout x pop zone, outside the card rect
yy = (np.arange(AH) * K + K / 2)[:, None]
xx = (np.arange(AW) * K + K / 2)[None, :]
zone = np.clip((Y1 - yy) / (Y1 - Y0), 0, 1) * np.clip(xx / 70, 0, 1) * np.clip((W - 1 - xx) / 70, 0, 1)
out = M & (zone > .5) & ~((xx >= RX) & (xx < RX + RW) & (yy >= RY))
tops = [np.flatnonzero(o.any(axis=1))[0] * K for o in out if o.any()]
reach_top = float(np.percentile(tops, 3)) if tops else RY - pop
EXT = max(RY - reach_top, 0.0)
side = out & (yy >= RY)
hand_frames = int((side.sum(axis=(1, 2)) * K * K > 1500).sum())
sx = np.flatnonzero(side.any(axis=(0, 1))) * K
reach_l = int(max(0, RX - sx.min())) if len(sx) else 0
reach_r = int(max(0, sx.max() - (RX + RW))) if len(sx) else 0
if hand_frames >= 3:
    hands = f'hands pass the card sides on {hand_frames} of {len(win)} frames (up to {reach_l} px left, {reach_r} px right)'
else:
    hands = ('HEAD POP-OUT ONLY: the hands never pass the card sides on this clip. It still works; for hands too, pick a '
             'line with a wide gesture or a narrower CARD')
ax = np.flatnonzero(rest[:max(RY // K - 2, 1)].any(axis=0)) * K
if len(ax) and (ax.min() < RX - 20 or ax.max() > RX + RW + 20):
    notes.append('the resting shoulders stand above the card and are wider than it: lower HEAD_OUT if it looks odd')

# ------------------------------------------------------------------------------------------- size on screen
sc = C['SCALE']
fit = (ZONE[1] - ZONE[0]) / ((EXT + RH) * PUSH)
S = min(1.1, fit) if sc == 'auto' else min(float(sc), fit)
total = (EXT + RH) * S
scr_top = ZONE[0] + (ZONE[1] - ZONE[0] - total) / 2 + EXT * S
meas = {'N': N, 'card': [RX, RY, RW, RH], 'Y0': Y0, 'Y1': Y1, 'head': [round(top), round(chin), round(cx), round(head_w)],
        'pop': round(pop), 'reach_top': round(reach_top), 'scale': round(S, 4), 'scr_top': round(scr_top, 1),
        'hand_frames': hand_frames, 'window': [a0, z1], 'f_in': F_IN, 'f_out': F_OUT, 'notes': notes}
os.makedirs('work', exist_ok=True)
json.dump(meas, open('work/measure.json', 'w'), indent=1)
print(f'head   top {top:.0f}  chin {chin:.0f}  centre x {cx:.0f}  ({head_h:.0f} px tall)')
print(f'card   x {RX} y {RY}  {RW}x{RH} in the a-roll   on screen: {RW * S:.0f}x{RH * S:.0f}, top {scr_top:.0f}, '
      f'bottom {scr_top + RH * S:.0f}, scale {S:.3f}')
print(f'pop    {RY - top:.0f} px of head above the card edge; highest reach y {reach_top:.0f}; kept to y {Y0}, gone by y {Y1}')
print(f'       {hands}')
for n in notes:
    print(f'note   {n}')

# ------------------------------------------------------------------------------------------------- check sheet
pick = sorted({a0, F_IN, (F_IN + z1) // 2, max(F_IN, z1 - GROW - 2)})
sel = '+'.join(f'eq(n\\,{f})' for f in pick)
raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='{sel}',scale=360:640", '-fps_mode',
                      'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
sheet = Image.new('RGB', (360 * len(pick), 640), (0, 0, 0))
for i, f in enumerate(pick):
    if len(raw) < (i + 1) * 360 * 640 * 3:
        break
    im = np.frombuffer(raw[i * 360 * 640 * 3:(i + 1) * 360 * 640 * 3], np.uint8).reshape(640, 360, 3).astype(float)
    o = np.asarray(Image.fromarray((out[f - a0] * 255).astype(np.uint8)).resize((360, 640))) > 128
    im[o] = im[o] * .45 + np.array([255, 60, 200]) * .55
    t = Image.fromarray(im.astype(np.uint8))
    d = ImageDraw.Draw(t)
    d.rectangle([RX / 3, RY / 3, (RX + RW) / 3, (RY + RH) / 3 - 1], outline=(0, 255, 255), width=2)
    d.rectangle([(cx - head_w / 2) / 3, top / 3, (cx + head_w / 2) / 3, chin / 3], outline=(60, 255, 90), width=2)
    for y in (Y0, Y1):
        d.line([(0, y / 3), (360, y / 3)], fill=(255, 230, 0), width=1)
    d.text((6, 6), f'f{f}', fill=(255, 255, 255))
    sheet.paste(t, (360 * i, 0))
sheet.save('work/check.jpg', quality=88)
print('check  work/check.jpg (a-roll at 1/3 size: cyan card, green head, yellow Y0 / Y1, pink = comes out of the card)')

if len(sys.argv) > 1 and sys.argv[1] == 'measure':
    sys.exit(0)

# --------------------------------------------------------------------------------------------------------- bake
key = {'Y0': Y0, 'Y1': Y1, 'N': N, 'src': os.path.getmtime('assets/subject.webm')}
old = json.load(open('work/bake.json')) if os.path.exists('work/bake.json') else None
if old != key or not os.path.exists('assets/subject_fade.webm'):
    yf = np.arange(H)[:, None] + .5
    xf = np.arange(W)[None, :] + .5
    m = np.clip((Y1 - yf) / (Y1 - Y0), 0, 1) * np.clip(xf / 70, 0, 1) * np.clip((W - xf) / 70, 0, 1)
    Image.fromarray((m * 255).astype(np.uint8)).save('work/ramp.png')
    subprocess.run([FF, '-v', 'error', '-y', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-loop', '1', '-framerate',
                    '30', '-i', 'work/ramp.png', '-filter_complex',
                    '[0:v]format=yuva420p,split[c][c2];[c2]alphaextract,gblur=sigma=1.2,format=gray[a];[1:v]format=gray[r];'
                    '[a][r]blend=all_mode=multiply:shortest=1[am];[c][am]alphamerge,setpts=N/30/TB[o]', '-map', '[o]',
                    '-frames:v', str(N), '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0', '-b:v',
                    '0', '-crf', '22', '-g', '30', '-deadline', 'good', '-cpu-used', '4', '-row-mt', '1',
                    '-metadata:s:v:0', 'alpha_mode=1', 'assets/subject_fade.webm'], check=True)
    json.dump(key, open('work/bake.json', 'w'))
    print('baked  assets/subject_fade.webm (cutout kept only where it may leave the card)')
else:
    print('baked  assets/subject_fade.webm is up to date')
if not os.path.exists('assets/backdrop.mp4') or os.path.getmtime('assets/backdrop.mp4') < os.path.getmtime('assets/aroll.mp4'):
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf',
                    'scale=216:384,gblur=sigma=9,scale=1080:1920:flags=bicubic,setsar=1', '-frames:v', str(N), '-an',
                    '-c:v', 'libx264', '-crf', '22', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-g', '30',
                    'assets/backdrop.mp4'], check=True)
    print('baked  assets/backdrop.mp4 (the blurred room behind the card)')
print('next   python3 build.py')
