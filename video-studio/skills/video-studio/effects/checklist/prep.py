#!/usr/bin/env python3
"""checklist / prep.py: measure the slot so build.py can place the card and pick glass vs opaque without guessing.

Run from the slot folder with the skill's Python (PY) (needs numpy):
    PY prep.py

Reads   assets/aroll.mp4, assets/subject.webm (their cutout; without it only the camera test runs)
Writes  work/prep.json:
  camera  still (bool: background drift small enough for the glass card), drift_px (largest background shift against
          the middle frame, phase correlation), edge_std (background edge flicker, info only), glass_frame
  head    top_min / top_max (cap top, px), w (head width, px), cx_min / cx_max, chin_max (estimate), tops / cxs per
          frame, face_box [x0, y0, x1, y1]: union of their head box over every frame, 16 px margin
  grid    10 px cells: occ[y][x] = % of frames in which the speaker covers the cell; work/prep_masks.bin holds the same grid
          per frame (1 byte per cell) so build.py can look only at the frames in which the card is on screen

Optional: prep.py <project_dir> [--out file.json] measures another project without writing into it.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

FF = shutil.which('ffmpeg') or 'ffmpeg'
args = [a for a in sys.argv[1:] if not a.startswith('--')]
OUT = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
if OUT:
    OUT = os.path.abspath(OUT)
    args = [a for a in args if os.path.abspath(a) != OUT]
os.chdir(args[0] if args else os.path.dirname(os.path.abspath(__file__)))
OUT = OUT or os.path.join('work', 'prep.json')
W, H, S = 216, 384, 5          # analysis size, px per analysis cell
# The glass backdrop is ONE frame blurred at sigma 40, so it hides a background that wanders up to about half a
# sigma. Measured: the approved demo (a "static" tripod shot that really drifts 17 px in its first second) looks
# locked; a handheld selfie measures 100+ px and needs the opaque card.
GLASS_MAX_DRIFT_PX = 24.0


def frames(path, vf, alpha=False):
    cmd = [FF, '-v', 'error'] + (['-c:v', 'libvpx-vp9'] if alpha else []) + \
          ['-i', path, '-vf', vf, '-pix_fmt', 'gray', '-f', 'rawvideo', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W)


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


gray = frames('assets/aroll.mp4', f'scale={W}:{H}:flags=area').astype(np.float32)
N = len(gray)
has_cut = os.path.exists('assets/subject.webm')
alpha = frames('assets/subject.webm', f'alphaextract,scale={W}:{H}:flags=area', alpha=True) if has_cut else None
if has_cut and len(alpha) != N:
    sys.exit(f'cutout has {len(alpha)} frames, a-roll has {N}: re-make the cutout, it will drift')
subj = (alpha > 100) if has_cut else np.zeros((N, H, W), bool)

# ---------------------------------------------------------------- camera: is the background still?
idx = list(range(0, N, 2))
ever = dilate(subj[idx].any(0), 3)
bg = ~ever
ref = N // 2
gy, gx = np.gradient(gray[ref])
grad = np.hypot(gx, gy)
edge_std = 0.0
if bg.sum() > 400:
    strong = bg & (grad >= np.percentile(grad[bg], 75))
    edge_std = float(np.median(gray[idx][:, strong].std(0)))
win = np.outer(np.hanning(H), np.hanning(W))


def feat(g):
    yy, xx = np.gradient(g)
    return np.fft.fft2(np.hypot(xx, yy) * bg * win)


F0 = feat(gray[ref])
drift = 0.0
for i in idx:
    R = F0 * np.conj(feat(gray[i]))
    c = np.abs(np.fft.ifft2(R / (np.abs(R) + 1e-6)))
    py, px = np.unravel_index(np.argmax(c), c.shape)
    py, px = (py - H if py > H // 2 else py), (px - W if px > W // 2 else px)
    drift = max(drift, float(np.hypot(py, px)) * S)
still = bool(drift <= GLASS_MAX_DRIFT_PX)
camera = {'still': still, 'drift_px': round(drift, 1), 'edge_std': round(edge_std, 2), 'glass_frame': ref,
          'glass_max_drift_px': GLASS_MAX_DRIFT_PX}

# ---------------------------------------------------------------- head: where is the speaker's face in every frame?
head = None
if has_cut and subj.any():
    def run_width(m, y, cx):
        """width (cells) and centre of the run of subject pixels in row y that holds column cx"""
        row = m[y]
        c = int(round(cx))
        if not row[min(max(c, 0), W - 1)]:
            near = np.where(row[max(0, c - 4):c + 5])[0]
            if not len(near):
                return 0, cx
            c = max(0, c - 4) + int(near[len(near) // 2])
        a = b = c
        while a > 0 and row[a - 1]:
            a -= 1
        while b < W - 1 and row[b + 1]:
            b += 1
        return b - a + 1, (a + b) / 2

    def head_of(m, lo=0, hi=W, wref=None):
        """(top, cx, width) of the head in mask m, looking only at columns lo..hi for its top.
        With wref (expected head width) a raised hand is rejected: half a head below its top, the thing found must
        still be at least 55% of a head wide and centred under that top. If not, those columns are skipped."""
        ok = np.zeros(W, bool)
        ok[lo:hi] = True
        top = cx = None
        for _ in range(4):
            rows = np.where((m & ok).any(1))[0]
            if not len(rows):
                return None
            top = int(rows[0])
            cols = np.where(m[top:top + 4].any(0) & ok)[0]
            groups = np.split(cols, np.where(np.diff(cols) > 1)[0] + 1)
            grp = max(groups, key=len)
            cx = float(grp.mean())
            if wref is None:
                break
            wchk, cchk = run_width(m, min(top + int(.5 * wref), H - 1), cx)
            if wchk >= .55 * wref and abs(cchk - cx) <= .4 * wref:
                break
            ok[max(0, int(grp[0]) - 6):int(grp[-1]) + 7] = False       # a hand or an arm: look elsewhere
        w, cx2 = run_width(m, min(top + 3, H - 1), cx)
        for _ in range(8):
            best = max((run_width(m, y, cx) for y in range(top, min(H, top + max(4, int(w))))), key=lambda t: t[0])
            if best[0] <= w * 1.03:
                break
            w, cx2 = best
        return top, cx2, w

    persistent = subj.mean(0) >= .5
    p = head_of(persistent) or head_of(subj.any(0))
    lo, hi = max(0, int(p[1] - .9 * p[2])), min(W, int(p[1] + .9 * p[2]) + 1)
    per = [head_of(subj[i], lo, hi, wref=p[2]) for i in range(N)]
    last = next(x for x in per if x)
    for i in range(N):                       # a frame with no head found keeps the last good one
        per[i] = last = per[i] or last
    w_med = float(np.median([x[2] for x in per]))
    tops = np.array([x[0] for x in per], float)
    cxs = np.array([x[1] for x in per], float)
    chin = tops + 1.38 * w_med
    m16 = 16
    head = {'top_min': int(tops.min() * S), 'top_max': int(tops.max() * S), 'w': int(w_med * S),
            'cx_min': int(cxs.min() * S), 'cx_max': int(cxs.max() * S), 'chin_max': int(chin.max() * S),
            'tops': [int(t * S) for t in tops], 'cxs': [int(c * S) for c in cxs],        # per frame
            'face_box': [max(0, int((cxs.min() - .55 * w_med) * S) - m16), max(0, int(tops.min() * S) - m16),
                         min(1080, int((cxs.max() + .55 * w_med) * S) + m16), min(1920, int(chin.max() * S) + m16)]}

# ---------------------------------------------------------------- occupancy grid (10 px cells)
cells = subj.reshape(N, H // 2, 2, W // 2, 2).any(4).any(2)
occ = cells.mean(0) * 100
MASKS = os.path.splitext(OUT)[0] + '_masks.bin'      # per-frame grid, 1 byte per cell: build.py reads it to see where
grid = {'cell': 10, 'w': W // 2, 'h': H // 2, 'occ': [[int(round(v)) for v in row] for row in occ],   # the speaker is while the card is up
        'masks': os.path.basename(MASKS)}

os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
open(MASKS, 'wb').write(cells.astype(np.uint8).tobytes())
json.dump({'frames': N, 'camera': camera, 'head': head, 'grid': grid}, open(OUT, 'w'))
print(f'[prep] {N} frames  camera: {"STEADY ENOUGH" if still else "MOVING"} (background drift {drift:.1f} px against the '
      f'middle frame, limit {GLASS_MAX_DRIFT_PX:.0f}; edge flicker {edge_std:.2f})'
      f'  -> card will be {"glass" if still else "opaque"} with GLASS = "auto"')
if head:
    print(f'[prep] head: top y {head["top_min"]}..{head["top_max"]}, width {head["w"]}, centre x {head["cx_min"]}..{head["cx_max"]}, '
          f'chin about y {head["chin_max"]}  face box (never cover) {head["face_box"]}')
else:
    print('[prep] no cutout: build.py needs an explicit CARD_BOX and LAYER = "front"')
print(f'[prep] wrote {OUT}')
