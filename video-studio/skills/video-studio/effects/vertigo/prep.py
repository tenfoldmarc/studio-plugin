#!/usr/bin/env python3
"""Step 2. Measure the clip and build the clean plate (the room without the speaker).

  - decodes assets/aroll.mp4 + assets/subject.webm once into work/frames.npy + work/alpha.npy (bake.py reuses them)
  - camera track: background feature match of every frame to the middle frame (a "still" phone still slides a few px)
  - measures head box, chin, shoulder / seat line, how much room is visible, how busy it is, camera drift
  - clean plate: per-pixel median of the room over every frame where the speaker is not covering it, plus the extra
    frames from more.py when work/more.npz exists. What is never seen is filled: walls smeared down their columns
    (crisp where there are vertical edges, soft on plain paint), below the seat an inpaint, and on top of both the
    fine texture of the wall right next to the hole (mirrored), so the fill is not a soft smudge.
Writes work/cam.npy, work/measure.json, assets/plate.png, work/hole.png, work/alpha_med.png, work/plate_check.jpg.
Usage (from the slot folder):  PY prep.py      (30 s to 2 min; behind the slot runner on a shared machine)
"""
import os
import sys
import warnings

import cv2
import numpy as np

from vcore import FPS, H, W, count_frames, decode_alpha, decode_video, here, smoothstep
import json

cv2.setNumThreads(max(1, (os.cpu_count() or 2) - 1))
warnings.filterwarnings('ignore', message='All-NaN slice')     # never-seen pixels: filled below
WORK = here('work')
os.makedirs(WORK, exist_ok=True)
AROLL, CUT = here('assets', 'aroll.mp4'), here('assets', 'subject.webm')
if not os.path.exists(CUT):
    sys.exit('assets/subject.webm is missing: Vertigo needs the cutout (make the slot without --no-cutout)')

N = count_frames(AROLL)
fr = decode_video(AROLL, os.path.join(WORK, 'frames.npy'), N)
al, got = decode_alpha(CUT, os.path.join(WORK, 'alpha.npy'), N)
if got != N:
    print(f'!! cutout has {got} frames, a-roll {N}: the last cutout frame is held')
REF = N // 2
MIRROR_BAND = float(os.environ.get('MIRROR_BAND', '110'))   # px of mirrored room inside the outline (0 = smear only)
PLATE_ERR_MAX = 8.0      # levels (75th pct, room near the speaker) the plate may miss by before bake fills each frame
                         # from itself. Measured: still sofa 3, handheld selfie 5, camera moving through a room 13


# ------------------------------------------------------------------------------------------------ measure the head
def head_of(m):
    """m: bool mask of the speaker. -> (cx, top, width, chin) or None."""
    rows = np.where(m.sum(1) > 6)[0]
    if len(rows) == 0:
        return None
    top = int(rows[0])
    w = np.convolve(m.sum(1).astype(np.float32), np.ones(9) / 9, mode='same')
    hw = float(w[top:top + 40].max())
    for _ in range(4):                         # head width = widest row within about one head of the crown
        hw = float(w[top:top + max(20, int(1.05 * hw))].max())
    band = m[top:top + int(hw)]
    xs = np.where(band)[1]
    cx = float(xs.mean()) if len(xs) else W / 2
    return cx, top, hw, top + 1.3 * hw


heads = [head_of(al[i] > 128) for i in range(0, N, 3)]
heads = [h for h in heads if h]
if not heads:
    sys.exit('the cutout is empty: no speaker found in this clip')
cx, top, hw, chin = (float(np.median([h[k] for h in heads])) for k in range(4))
origin = (cx, top + 0.6 * hw)
shoulder_y, seat_y = chin + 0.35 * hw, chin + 3.0 * hw

# ------------------------------------------------------------------------------------------------ camera track
union = (al[::2] > 8).any(0).astype(np.uint8) * 255
bgmask = (cv2.dilate(union, np.ones((41, 41), np.uint8)) < 10).astype(np.uint8) * 255
sift = cv2.SIFT_create(3000)
small = lambda img: cv2.cvtColor(cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
bg_small = cv2.resize(bgmask, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST)
k0, d0 = sift.detectAndCompute(small(fr[REF]), bg_small)
bf = cv2.BFMatcher(cv2.NORM_L2)
EYE = np.float32([[1, 0, 0], [0, 1, 0]])


def track(img, mask_small=bg_small):
    """-> (2x3 affine: this frame -> REF, inlier count)."""
    if d0 is None or len(k0) < 12:
        return EYE.copy(), 0
    k1, d1 = sift.detectAndCompute(small(img), mask_small)
    if d1 is None or len(k1) < 12:
        return EYE.copy(), 0
    good = [a for a, b in (p for p in bf.knnMatch(d1, d0, k=2) if len(p) == 2) if a.distance < 0.7 * b.distance]
    if len(good) < 12:
        return EYE.copy(), len(good)
    src = np.float32([k1[a.queryIdx].pt for a in good]) * 2
    dst = np.float32([k0[a.trainIdx].pt for a in good]) * 2
    m, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if m is None:
        return EYE.copy(), 0
    return m.astype(np.float32), int(inl.sum())


cam, inls = [], []
for i in range(N):
    m, n_in = track(fr[i])
    cam.append(m)
    inls.append(n_in)
cam = np.array(cam, np.float32)
cam_s = cam.copy()                              # a little temporal smoothing kills RANSAC jitter on still shots
for i in range(N):
    a, b = max(0, i - 2), min(N, i + 3)
    cam_s[i] = cam[a:b].mean(0)
cam = cam_s
np.save(os.path.join(WORK, 'cam.npy'), cam)
shift = np.hypot(cam[:, 0, 2], cam[:, 1, 2])
drift = float(shift.max())
drift_kind = 'still' if drift < 8 else ('drifting' if drift < 45 else 'moving')
print(f'track: {N} frames, median inliers {int(np.median(inls))}, drift up to {drift:.1f}px -> {drift_kind}')

# ------------------------------------------------------------------------------------------------ plate stack
K_SLOT = min(N, 90)
idx = np.linspace(0, N - 1, K_SLOT).round().astype(int)
extra = []
mp, mw = os.path.join(WORK, 'more.mp4'), os.path.join(WORK, 'more.webm')
if os.path.exists(mp) and os.path.exists(mw) and os.environ.get('MORE', '1') != '0':
    mfr = decode_video(mp, os.path.join(WORK, 'more_frames.npy'))
    mal, _ = decode_alpha(mw, os.path.join(WORK, 'more_alpha.npy'), len(mfr))
    for j in range(len(mfr)):
        mb = (cv2.dilate((mal[j] > 8).astype(np.uint8) * 255, np.ones((41, 41), np.uint8)) < 10).astype(np.uint8) * 255
        m, n_in = track(mfr[j], cv2.resize(mb, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST))
        sc = float(np.hypot(m[0, 0], m[0, 1]))
        if n_in >= 25 and abs(sc - 1) < 0.04 and np.hypot(m[0, 2], m[1, 2]) < 160:
            extra.append((mfr[j], mal[j], m))
    print(f'more: {len(extra)} of {len(mfr)} extra frames from the same take line up and are used for the plate')
K = len(idx) + len(extra)
stack = np.lib.format.open_memmap(os.path.join(WORK, 'stack.npy'), mode='w+', dtype=np.uint8, shape=(K, H, W, 3))
valid = np.zeros((K, H, W), bool)
k25 = np.ones((25, 25), np.uint8)
ones = np.full((H, W), 255, np.uint8)
items = [(fr[i], al[i], cam[i]) for i in idx] + extra
for j, (img, a, m) in enumerate(items):
    stack[j] = cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    aw = cv2.warpAffine(cv2.dilate(a, k25), m, (W, H), flags=cv2.INTER_LINEAR, borderValue=255)
    inside = cv2.warpAffine(ones, m, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
    valid[j] = (aw < 8) & (inside > 250)
cnt = valid.sum(0)
med = np.zeros((H, W, 3), np.float32)
for y0 in range(0, H, 64):
    s = stack[:, y0:y0 + 64].astype(np.float32)
    s[~valid[:, y0:y0 + 64]] = np.nan
    with np.errstate(all='ignore'):
        med[y0:y0 + 64] = np.nan_to_num(np.nanmedian(s, axis=0))
del stack
hole = cnt < (2 if K < 20 else 3)


# ------------------------------------------------------------------------------------------------ fill the hole
def fill_plate(med, hole):
    hole_u8 = hole.astype(np.uint8) * 255
    seen = (~hole).astype(np.float32)
    gray = cv2.cvtColor(np.clip(med, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    gxs = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)) * seen
    # 1. vertical smear of every hole run in every column, from the median of the seen rows just above it
    vert = med.copy()
    crisp = np.zeros(W, np.float32)
    for x in range(W):
        col = hole[:, x]
        if not col.any():
            continue
        d = np.diff(np.r_[0, col.astype(np.int8), 0])
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        for y0, y1 in zip(starts, ends):
            if y0 > 6:
                src = med[max(0, y0 - 34):y0 - 2, x]
                crisp[x] = max(crisp[x], float(gxs[max(0, y0 - 34):y0 - 2, x].mean()))
            elif y1 < H - 6:
                src = med[y1 + 2:min(H, y1 + 34), x]
            else:
                continue
            vert[y0:y1, x] = np.median(src, axis=0)
    # plain paint: blur the smear sideways among filled pixels (no streaks); vertical edges (frames, panels) stay crisp
    hm = hole.astype(np.float32)[..., None]
    num = cv2.GaussianBlur(vert * hm, (0, 0), sigmaX=16, sigmaY=1)
    den = cv2.GaussianBlur(hm, (0, 0), sigmaX=16, sigmaY=1)[..., None]
    soft = num / np.maximum(den, 1e-3)
    crisp = cv2.GaussianBlur(crisp[None, :], (0, 0), sigmaX=12)[0]
    wsoft = (1.0 - smoothstep(10.0, 28.0, crisp))[None, :, None]
    vert = cv2.blur(vert, (3, 1)) * (1 - wsoft) + soft * wsoft
    # 2. below the seat the floor and furniture run sideways: inpaint there (it is pinned, so barely ever revealed)
    half = cv2.resize(np.clip(med, 0, 255).astype(np.uint8), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    hh = cv2.resize(hole_u8, (W // 2, H // 2), interpolation=cv2.INTER_NEAREST)
    inp = cv2.resize(cv2.inpaint(half, hh, 6, cv2.INPAINT_TELEA), (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None, None]
    wfloor = smoothstep(seat_y - 60, seat_y + 60, yy)
    low = vert * (1 - wfloor) + inp * wfloor
    # 3. fine texture: the high-pass of the wall right beside the hole, mirrored into it, fading with depth
    blur = cv2.GaussianBlur(med * seen[..., None], (0, 0), 3) / np.maximum(cv2.GaussianBlur(seen, (0, 0), 3), 1e-3)[..., None]
    hp = (med - blur) * seen[..., None]
    dist, lab = cv2.distanceTransformWithLabels(hole_u8, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(~hole)
    lut_y = np.zeros(lab.max() + 1, np.int32)
    lut_x = np.zeros(lab.max() + 1, np.int32)
    lut_y[lab[ys, xs]], lut_x[lab[ys, xs]] = ys, xs
    py, px = np.where(hole)
    by, bx = lut_y[lab[py, px]], lut_x[lab[py, px]]
    qy, qx = np.clip(2 * by - py, 0, H - 1), np.clip(2 * bx - px, 0, W - 1)
    bad = hole[qy, qx]
    qy[bad], qx[bad] = by[bad], bx[bad]
    detail = np.zeros_like(med)
    fade = 0.25 + 0.75 * (1 - smoothstep(30, 200, dist[py, px]))
    detail[py, px] = hp[qy, qx] * fade[:, None]
    # 4. the band the push actually uncovers (about 0 to 90 px around the outline) gets the room right outside the
    #    outline, mirrored: a picture edge or a sofa top beside the head continues at the right height, a door frame
    #    above it continues straight down. Deeper in, the smear + texture take over.
    mirror = med.copy()                            # real room outside the hole, so the blur does not darken the seam
    mirror[py, px] = med[qy, qx]
    mirror = cv2.GaussianBlur(mirror, (0, 0), 1.2)
    m = (1 - smoothstep(MIRROR_BAND * 0.55, MIRROR_BAND, dist))[..., None]
    out = np.where(hole[..., None], mirror * m + (low + detail) * (1 - m), med)
    # melt the seam between seen and filled pixels
    sm = cv2.GaussianBlur(out, (0, 0), 1.6)
    edge = cv2.GaussianBlur(hole_u8, (0, 0), 3.0).astype(np.float32) / 255
    edge = ((1 - np.abs(edge * 2 - 1)) ** 2)[..., None]
    return out * (1 - edge) + sm * edge


plate = np.clip(fill_plate(med, hole) + 0.5, 0, 255).astype(np.uint8)
cv2.imwrite(here('assets', 'plate.png'), plate)
cv2.imwrite(os.path.join(WORK, 'hole.png'), hole.astype(np.uint8) * 255)
alpha_med = np.median(np.stack([cv2.warpAffine(al[i], cam[i], (W, H)) for i in idx[::3]]), axis=0).astype(np.uint8)
cv2.imwrite(os.path.join(WORK, 'alpha_med.png'), alpha_med)

# ------------------------------------------------------------------------------------------------ does the plate hold?
# Put the plate back into a few frames and compare it with the room they really show. A still or gently drifting
# camera lines up within a few levels; a camera that moves through the room (parallax) does not, and then one plate
# cannot serve every frame: bake fills each frame from itself instead ("live" fill).
errs = []
k41 = np.ones((41, 41), np.uint8)
for i in idx[::6]:
    inv = cv2.invertAffineTransform(cam[i])
    pw = cv2.warpAffine(plate, inv, (W, H), borderMode=cv2.BORDER_REPLICATE).astype(np.int16)
    inside = cv2.warpAffine(ones, inv, (W, H), flags=cv2.INTER_NEAREST, borderValue=0) > 250
    a = np.asarray(al[i])                  # only the room near the speaker counts: that is what the push uncovers
    near = (cv2.dilate(a, np.ones((161, 161), np.uint8)) > 10) & (cv2.dilate(a, np.ones((21, 21), np.uint8)) < 10)
    m = near & inside & ~cv2.warpAffine(hole.astype(np.uint8), inv, (W, H)).astype(bool)
    if m.sum() > 1000:
        errs.append(float(np.percentile(np.abs(pw - fr[i].astype(np.int16)).mean(2)[m], 75)))
plate_err = float(np.median(errs)) if errs else 99.0
fill = os.environ.get('FILL') or ('plate' if plate_err <= PLATE_ERR_MAX else 'live')
print(f'plate check: misses the room near the speaker by {plate_err:.1f} levels (limit {PLATE_ERR_MAX}) -> {fill} fill')

# ------------------------------------------------------------------------------------------------ room numbers
g = cv2.cvtColor(fr[REF], cv2.COLOR_BGR2GRAY).astype(np.float32)
mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
bgv = (bgmask > 0) & (np.arange(H)[:, None] < seat_y)          # the part of the room that stretches
edges = mag > 40
room_texture = float(edges[bgv].mean()) if bgv.any() else 0.0  # share of the stretching room that is a real edge
ring = (cv2.dilate(union, np.ones((121, 121), np.uint8)) > 0) & (union == 0) & (np.arange(H)[:, None] < seat_y)
ring_busy = float(edges[ring].mean()) if ring.any() else 0.0
meas = dict(frames=N, ref=REF, shot=('close' if hw >= 0.27 * W else 'wide' if hw < 0.12 * W else 'medium'),
            head=dict(cx=round(cx, 1), top=round(top, 1), w=round(hw, 1), chin=round(chin, 1)),
            origin=[round(origin[0], 1), round(origin[1], 1)], shoulder_y=round(shoulder_y, 1), seat_y=round(seat_y, 1),
            person_frac=round(float((union > 0).mean()), 3), room_frac=round(float(bgv.mean()), 3),
            room_texture=round(room_texture, 4), ring_busy=round(ring_busy, 4), drift_px=round(drift, 1),
            drift=drift_kind, hole_frac=round(float(hole.mean()), 4), extra_frames=len(extra),
            plate_err=round(plate_err, 2), fill=fill,
            centre_offset=round((cx - W / 2) / W, 3))
json.dump(meas, open(os.path.join(WORK, 'measure.json'), 'w'), indent=1)

chk = np.hstack([cv2.resize(fr[REF], (W // 2, H // 2)), cv2.resize(plate, (W // 2, H // 2))])
cnts, _ = cv2.findContours(cv2.resize(hole.astype(np.uint8) * 255, (W // 2, H // 2)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(chk[:, W // 2:], cnts, -1, (255, 0, 255), 1)
cv2.line(chk, (0, int(seat_y / 2)), (W - 1, int(seat_y / 2)), (0, 255, 0), 1)
cv2.line(chk, (0, int(shoulder_y / 2)), (W - 1, int(shoulder_y / 2)), (255, 255, 0), 1)
cv2.circle(chk, (int(origin[0] / 2), int(origin[1] / 2)), 6, (0, 255, 255), 2)
cv2.imwrite(os.path.join(WORK, 'plate_check.jpg'), chk, [cv2.IMWRITE_JPEG_QUALITY, 85])
print('measure: ' + json.dumps(meas))
print('look at work/plate_check.jpg: left the middle frame, right the plate (magenta = never seen, filled),'
      ' cyan line = shoulders (stretch fades out), green = seat (pinned from here down), yellow ring = vanishing point')
