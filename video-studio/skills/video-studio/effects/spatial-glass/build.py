#!/usr/bin/env python3
"""spatial-glass, step 1: measure the clip, lay out the panes, write work/plan.json, the sounds and index.html.

Three panes of frosted glass float in the room at three depths, one for each step the speaker names: a grid of tiles
(step 1, high on the wall), a bar that types the step (step 2, in front of the speaker), a ring that runs and resolves
to a check (step 3, tucked behind the speaker's shoulder). Each pane shows the live room blurred behind it.

  PY build.py            track the room, measure the speaker, choose the layout, plan + index.html. READ the printout
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no words on the panes (the bar types a quiet line instead, the ring has no label)
  SFX=0                  no air swells / thump
  GRADE=1                a touch more contrast while the panes are up (default off: the reel grades)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

import glass as G
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
STEPS = [('drop', 'Clips'),          # (cue word, text on its pane) for the three steps the speaker names. Cue: a word
         ('trigger', 'edit it'),     # from words.json ('clips', or 'clips#2' for its 2nd time) or seconds. The text:
         ('takes', 'Editing')]       # the speaker's own short words (1 to 3 words). Pane 1 grid header, pane 2 typed, pane 3 ring
DONE = 'auto'          # when the ring resolves to a check: a word, seconds, or 'auto' (about 1 s after step 3)
DONE_LABEL = 'Done'    # the ring's label after the check ('' keeps the step-3 text)
OUT = 'auto'           # when the panes leave: 'auto' (plain footage 3 frames before the end), seconds, or 'cut'
PANES = 'auto'         # 'auto' (3, or 2 when the shot has no room), or force 3 / 2 (2 = the bar types steps 1 and 2)
LAYOUT = 'auto'        # 'auto', or {'grid': (cx, cy, k), 'ring': (cx, cy, k), 'bar': (cx, cy, k, width)} in frame REF px
REF = 'auto'           # the frame every position is measured in ('auto' = middle of the effect)
GLASS = 'auto'         # 'light' (frosted, dark type) or 'smoke' (darker glass, cream type); auto = smoke in a dark room
FONT = 'Inter'                 # the sans on the panes (bar text, grid header): a family in assets/fonts/fonts.css
WEIGHT = 500                   # its weight (nearest face)
FONT2 = 'Instrument Serif'     # the ring label
ITALIC2 = True                 # ring label in italic when the family has one
CASE = 'as typed'              # bar text + ring label: 'as typed', 'upper', 'lower', 'title' (grid header is always caps)
INK = 'auto'                   # type colour: 'auto' (near-black on light glass, cream on smoke) or (r, g, b)
ACCENT = (250, 230, 122)       # send button + check fill (butter yellow); the buyer's highlight colour
PUSH = 0.03                    # camera push-in while the panes are up (0.03 = 3 percent), 0 = none
TRUCK = 'auto'                 # sideways camera slide (parallax), 'auto' = 0.12 towards the grid side, 0 = none
LAMP = 'auto'                  # a practical light in shot (x, y) in frame REF, None, or 'auto' (brightest small blob)
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
GRADE = os.environ.get('GRADE', '0') not in ('0', '')
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = G.W, G.H, G.FPS
Q = 4                                                    # occupancy runs at a quarter of the size
clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
words = json.load(open('words.json')) if os.path.exists('words.json') else []
HAS_CUT = os.path.exists('assets/subject.webm')
os.makedirs('work', exist_ok=True)


def say(msg):
    print('  ' + msg, flush=True)


def decline(reason):
    print(f'SPATIAL GLASS DECLINES: {reason}', flush=True)
    sys.exit(2)


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = len(a) // 160
    return np.sqrt((a[:n * 160].reshape(n, 160) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    i0, i1 = max(0, int((s - 0.15) * 100)), min(len(ENVL) - 1, int((s + 0.25) * 100))
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(ENVL[i0:i1 + 1]))
    pk = ENVL[im:min(len(ENVL), int((e + 0.1) * 100)) + 1].max()
    thr = ENVL[im] + 0.35 * (pk - ENVL[im])
    for i in range(im, min(len(ENVL), int((e + 0.1) * 100))):
        if ENVL[i] >= thr:
            return float(np.clip(i / 100.0, s - 0.15, s + 0.15))    # a soft first consonant can read late
    return s


def when(v):
    if isinstance(v, (int, float)):
        return float(v), 'seconds'
    key, nth = (v.split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    w = hits[int(nth) - 1]
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio {t:.2f}s'


if len(STEPS) != 3:
    sys.exit('STEPS needs three (cue, text) entries, one per step the speaker names')
cues = []
for cue, txt in STEPS:
    t, how = when(cue)
    cues.append(t)
    say(f'step "{txt}": {t:.2f}s ({how})')
LEAD, GAP = 0.12, 0.28                                   # pane lands just ahead of its word; panes at least 0.28 s apart
arr = []
for k, c in enumerate(cues):
    a = c - LEAD
    if k and a < arr[-1] + GAP:
        say(f'!! step {k + 1} comes {c - cues[k - 1]:.2f}s after step {k}: its pane waits to {arr[-1] + GAP:.2f}s')
        a = arr[-1] + GAP
    arr.append(a)
if arr[0] < 0.30:
    say(f'!! the first pane at {arr[0]:.2f}s leaves no plain frames at the start: moved to 0.30s. Start the slot earlier.')
    shift = 0.30 - arr[0]
    arr = [a + shift for a in arr]
OUT_DUR, STAGGER = 0.45, 0.05
if OUT == 'cut':
    t_end = None
else:
    t_end = (float(OUT) + OUT_DUR) if isinstance(OUT, (int, float)) else DUR - 3 / FPS
    t_end = min(t_end, DUR - 2 / FPS)
t_last_out = (t_end - OUT_DUR) if t_end is not None else DUR
if DONE == 'auto':
    t_check = min(cues[2] + 1.0, t_last_out - 0.75)
else:
    t_check = when(DONE)[0]
t_check = max(t_check, arr[2] + 0.75)
if t_end is not None and t_last_out - t_check < 0.6:
    say(f'!! the check is up for only {t_last_out - t_check:.2f}s before the panes leave (1 s reads well): '
        'start the slot earlier or make it longer')
if t_end is not None and t_last_out - arr[2] < 1.4:
    say(f'!! step 3 lands only {t_last_out - arr[2]:.2f}s before the panes leave: give the slot 1.5 s after it')

# ---------------------------------------------------------------------------------------------------- room track
def track_room(ref, alphas):
    """Homography REF picture -> frame i for every frame, from SIFT features on the room (the speaker masked out).
    A still camera comes out as identity; a handheld one is followed, so the panes stay on the wall."""
    S = 2                                                # half size: plenty for a room track, 4x faster
    grays = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in reader('assets/aroll.mp4', W, H, scale=(W // S, H // S))]
    n = len(grays)
    ker = np.ones((25, 25), np.uint8)

    def bgmask(i):
        if alphas is None:
            return None
        a = cv2.resize(alphas[min(i, len(alphas) - 1)], (W // S, H // S), interpolation=cv2.INTER_LINEAR)
        return ((cv2.dilate(a, ker) < 10) * 255).astype(np.uint8)

    sift = cv2.SIFT_create(4000, contrastThreshold=0.012)
    k0, d0 = sift.detectAndCompute(grays[ref], bgmask(ref))
    bf = cv2.BFMatcher(cv2.NORM_L2)
    c = np.float32([[0, 0], [W / S, 0], [W / S, H / S], [0, H / S]])
    pos = np.zeros((n, 4, 2), np.float32)
    weak = []
    use_ecc = d0 is None or len(k0) < 60
    if use_ecc:
        say(f'track: plain room ({0 if d0 is None else len(k0)} features), following it by image alignment instead')
        tmpl = cv2.GaussianBlur(grays[ref], (0, 0), 1.5).astype(np.float32)
        m0 = bgmask(ref)
        if m0 is not None and (m0 > 0).mean() < 0.05:
            m0 = None
    warp = np.eye(2, 3, dtype=np.float32)
    for i in range(n):
        if i == ref:
            pos[i] = c
            continue
        hm = None
        if use_ecc:
            try:
                img = cv2.GaussianBlur(grays[i], (0, 0), 1.5).astype(np.float32)
                crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
                _, wnew = cv2.findTransformECC(tmpl, img, warp.copy(), cv2.MOTION_AFFINE, crit, m0, 5)
                det = float(np.linalg.det(wnew[:, :2]))
                if 0.85 < det < 1.18 and np.abs(wnew[:, 2]).max() < 0.2 * W / S:    # a sane small move only
                    warp = wnew
                    hm = np.vstack([warp, [0, 0, 1]]).astype(np.float64)
            except cv2.error:
                pass
            if hm is None:
                weak.append(i)
                pos[i] = pos[i - 1] if i else c
            else:
                pos[i] = cv2.perspectiveTransform(c[None], hm)[0]
            continue
        k1, d1 = sift.detectAndCompute(grays[i], bgmask(i))
        if d0 is not None and d1 is not None and len(k1) >= 8:
            good = [m[0] for m in bf.knnMatch(d1, d0, k=2) if len(m) == 2 and m[0].distance < 0.7 * m[1].distance]
            if len(good) >= 12:
                src = np.float32([k1[m.queryIdx].pt for m in good])
                dst = np.float32([k0[m.trainIdx].pt for m in good])
                hm, inl = cv2.findHomography(dst, src, cv2.RANSAC, 1.5)
                if hm is None or int(inl.sum()) < 25:
                    aff, inl2 = cv2.estimateAffinePartial2D(dst, src, method=cv2.RANSAC, ransacReprojThreshold=1.5)
                    hm = None if aff is None or int(inl2.sum()) < 10 else np.vstack([aff, [0, 0, 1]])
        if hm is None:
            weak.append(i)
            pos[i] = pos[i - 1] if i else c
        else:
            pos[i] = cv2.perspectiveTransform(c[None], hm)[0]
    if use_ecc and len(weak) > 0.2 * n:
        say(f'track: the room is too plain to follow ({len(weak)} of {n} frames lost): treated as a still camera')
        return np.repeat(np.eye(3)[None], n, 0), 0.0
    if weak:
        say(f'track: {len(weak)} frames with too little room to follow (kept the previous position): {weak[:12]}')
    pos *= S
    full = c * S
    move = room_move([cv2.getPerspectiveTransform(full, p) for p in pos])
    if move < 1.5:
        say(f'camera: still (room moves at most {move:.1f}px)')
        hs = np.repeat(np.eye(3)[None], n, 0)
    else:
        sm = smooth_track(pos)
        hs = np.array([cv2.getPerspectiveTransform(full, sm[i]) for i in range(n)])
        say(f'camera: {"handheld" if move > 12 else "nudged"} (room moves up to {move:.0f}px): '
            'the panes ride the room track')
    return hs, move


def room_move(hs):
    """How far the room moves (px) at points inside the picture (corners exaggerate tiny fit errors)."""
    gx, gy = np.meshgrid(np.linspace(0.2, 0.8, 3) * W, np.linspace(0.2, 0.8, 3) * H)
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    return float(max(np.abs(G.apply_h(h, pts) - pts).max() for h in hs))


def smooth_track(pos):
    """Corner paths cleaned: repeated source frames off the time axis, single-frame misfits replaced by the curve
    through their neighbours, Savitzky-Golay while the camera is at rest (5 taps)."""
    n = len(pos)
    dup = np.zeros(n, bool)
    dup[1:] = np.abs(np.diff(pos, axis=0)).max(axis=(1, 2)) < 0.02
    tau = np.cumsum(~dup) - 1
    pu = pos[~dup].reshape(-1, 8).astype(np.float64)
    m = len(pu)
    if m >= 6:
        for _ in range(24):
            pred = (-pu[:-4] + 4 * pu[1:-3] + 4 * pu[3:-1] - pu[4:]) / 6
            res = np.abs(pu[2:-2] - pred).max(axis=1)
            j = int(res.argmax())
            if res[j] < 0.45:
                break
            pu[j + 2] = pred[j]
        k = np.float64([-3, 12, 17, 12, -3]) / 35
        pad = np.concatenate([pu[:1]] * 2 + [pu] + [pu[-1:]] * 2)
        sg = sum(k[j] * pad[j:j + m] for j in range(5))
        step = np.abs(np.diff(pu, axis=0)).max(axis=1)
        step = np.concatenate([step[:1], step])
        busy = np.array([step[max(0, i - 2):i + 4].max() for i in range(m)])
        wraw = G.smoothstep(0.25, 0.60, busy)[:, None]
        pu = pu * wraw + sg * (1 - wraw)
    return pu[tau].reshape(n, 4, 2).astype(np.float32)


t_first, t_stop = arr[0], (t_end if t_end is not None else DUR)
f0, f1 = max(0, int((t_first - 0.2) * FPS)), min(N - 1, int(t_stop * FPS))
ref = int(REF) if REF != 'auto' else (f0 + f1) // 2
alphas = np.stack(list(reader('assets/subject.webm', W, H, alpha=True))) if HAS_CUT else None
if alphas is not None and len(alphas) != N:
    say(f'!! the cutout has {len(alphas)} frames, the slot {N}: remake it (fx_new.py)')
    alphas = alphas[:N] if len(alphas) > N else np.concatenate([alphas, np.repeat(alphas[-1:], N - len(alphas), 0)])
meta = dict(v=5, ref=ref, n=N, cut=HAS_CUT, src=clip.get('src'), at=clip.get('in'))
mp = 'work/track_meta.json'
if os.path.exists('work/track.npy') and os.path.exists(mp) and json.load(open(mp)).get('meta') == meta:
    track = np.load('work/track.npy')
    raw_move = json.load(open(mp))['move']
    say(f'track: reused work/track.npy (room moves up to {raw_move:.0f}px)')
else:
    track, raw_move = track_room(ref, alphas)
    np.save('work/track.npy', track)
    json.dump(dict(meta=meta, move=raw_move), open(mp, 'w'))

# ---------------------------------------------------------------------------------------------------- measure the speaker
ref_rgb = next(reader('assets/aroll.mp4', W, H, first=ref, last=ref))
qs = (W // Q, H // Q)
SQ = np.diag([1.0 / Q, 1.0 / Q, 1.0])
if alphas is not None:
    span = []
    for i in range(f0, f1 + 1):                          # each active frame's matte, carried into frame REF
        hm = SQ @ np.linalg.inv(track[i]) @ np.linalg.inv(SQ)
        a = cv2.resize(alphas[i], qs, interpolation=cv2.INTER_AREA)
        span.append(cv2.warpPerspective(a, hm, qs, flags=cv2.INTER_LINEAR) > 128)
    span = np.array(span)
    occ = span.mean(0).astype(np.float32)                # how often each spot is the speaker
    union = cv2.dilate(span.any(0).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
else:
    occ = np.zeros(qs[::-1], np.float32)
    union = occ.copy()


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head (full-size px), or None."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 40.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    for _ in range(6):
        xs = np.where(m[top:int(top + 0.45 * hw) + 1].any(axis=0))[0]
        if len(xs):
            cx = xs.mean() if len(xs) < 0.9 * m.shape[1] else cx
        r = min(m.shape[0] - 1, int(top + 0.6 * hw))
        xs = np.where(m[r, int(max(0, cx - 1.3 * hw)):int(cx + 1.3 * hw) + 1])[0]
        if not len(xs):
            break
        hw = max(8.0, float(xs[-1] - xs[0] + 1))
    return top * Q, cx * Q, hw * Q


heads = [h for h in (head_of(m) for m in span) if h] if alphas is not None else []
person = len(heads) >= 0.5 * max(1, (f1 - f0 + 1))
if person:                                               # a raised hand reads as a narrow 'head' off to one side: drop
    mw, mx = np.median([h[2] for h in heads]), np.median([h[1] for h in heads])
    heads = [h for h in heads if abs(h[2] - mw) < 0.35 * mw and abs(h[1] - mx) < 1.2 * mw] or heads
    tops = np.array([h[0] for h in heads])
    cxs = np.array([h[1] for h in heads])
    ht = float(np.percentile(tops, 5))
    hcx = float(np.median(cxs))
    hw = float(np.median([h[2] for h in heads]))
    padf = 28
    hlow = float(np.percentile(tops, 95))                # the head at its lowest (handheld, nodding)
    FACE = (float(np.percentile(cxs, 10)) - 0.56 * hw - padf, ht - padf,
            float(np.percentile(cxs, 90)) + 0.56 * hw + padf, hlow + 1.45 * hw + padf)
    chin = hlow + 1.45 * hw
    rows = np.where(occ[int(chin / Q):].sum(axis=1) > 0)[0]
    body_x = float((occ[int(chin / Q):] * np.arange(qs[0])[None]).sum() / max(occ[int(chin / Q):].sum(), 1)) * Q
    tight = hw > 290 or ht < 300
    shot = 'tight selfie' if tight else ('medium' if hw > 150 else 'wide')
    say(f'measured: {shot} shot, head top {ht:.0f}, head width {hw:.0f}, face centre x {hcx:.0f}, '
        f'chin {chin:.0f}, body centre x {body_x:.0f}')
else:
    FACE, ht, hcx, hw, chin, body_x, tight, shot = None, H * 0.4, W / 2, 0.0, H * 0.4, W / 2, False, 'no speaker'
    say('measured: nobody in the cutout (voice-over or no cutout): panes float in the open frame, none goes behind')

# ---------------------------------------------------------------------------------------------------- layout
SIZES = {'grid': (392, 378), 'ring': (300, 400), 'bar': (640, 92)}
M = 30                                                   # margin for the float, the push-in and the arrival
ii_occ = cv2.integral(occ)
ii_uni = cv2.integral(union)


def frac(ii, b):
    x0, y0, x1, y1 = [int(round(v / Q)) for v in b]
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, qs[0]), min(y1, qs[1])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    s = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    return float(s) / ((x1 - x0) * (y1 - y0))


def in_safe(b):
    g = 1.0 + 1.8 * float(PUSH)                         # nearer panes grow away from the centre on the push-in
    x0, y0, x1, y1 = W / 2 + (b[0] - W / 2) * g, H / 2 + (b[1] - H / 2) * g, W / 2 + (b[2] - W / 2) * g, \
        H / 2 + (b[3] - H / 2) * g
    right = W - G.SAFE['right_low'][1] if y1 > G.SAFE['right_low'][0] - M else W - G.SAFE['side']
    return x0 >= G.SAFE['side'] + M and y0 >= G.SAFE['top'] + M and x1 <= right - M and y1 <= G.SAFE['bottom'] - M


def hits(b, o, pad=0):
    return not (b[2] + pad <= o[0] or o[2] + pad <= b[0] or b[3] + pad <= o[1] or o[3] + pad <= b[1])


def box(cx, cy, w, h):
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def best_spot(role, k, side, placed, bw=None):
    """Lowest-cost centre for one pane: hard rules (safe zone, face, other panes, how much of the speaker it may
    cover) then distance to where that pane looks right next to this speaker."""
    w, h = SIZES[role]
    if role == 'bar':
        w = bw
    w, h = w * k, h * k
    if person:
        if role == 'grid':
            tx = hcx + side * (0.6 * hw + 0.5 * w + 40)
            ty = min(ht - 0.5 * h - 50, ht + 0.6 * hw)
        elif role == 'ring':                             # beside the head, its inner edge tucked behind the shoulder
            tx = hcx + side * (0.62 * hw + 0.30 * w)
            ty = max(ht + 0.5 * hw, FACE[3] + 0.5 * h - 0.25 * h)
        else:
            tx, ty = body_x, chin + 110 + h / 2
    else:
        tx, ty = {'grid': (W * 0.30, H * 0.33), 'ring': (W * 0.70, H * 0.45), 'bar': (W * 0.5, H * 0.62)}[role]
    best = None
    for cy in np.arange(G.SAFE['top'] + M + h / 2, G.SAFE['bottom'] - M - h / 2 + 1, 12.0):
        for cx in np.arange(G.SAFE['side'] + M + w / 2, W - G.SAFE['side'] - M - w / 2 + 1, 12.0):
            if side and person and role != 'bar' and (cx - hcx) * side < 0:
                continue
            b = box(cx, cy, w, h)
            if not in_safe(b) or (FACE and hits(b, FACE)) or any(hits(b, o, 30) for o in placed):
                continue
            if role == 'bar' and person and b[1] < chin + 0.15 * hw + 28 and b[0] < FACE[2] and b[2] > FACE[0]:
                continue                                 # the bar stays a clear gap below the chin
            if role == 'grid' and frac(ii_uni, b) > 0.06:
                continue                                 # on the wall, never over the speaker
            if role == 'ring':
                f = frac(ii_occ, b)
                if f > 0.40:
                    continue                             # at least 60 percent of it shows
            cost = abs(cx - tx) / 100 + abs(cy - ty) / 100
            if role == 'ring' and person:
                cost += 12.0 * max(0.0, 0.12 - frac(ii_occ, b))  # likes to tuck a little behind the shoulder
            if best is None or cost < best[0]:
                best = (cost, cx, cy, b)
    return best


def free_side():
    """+1 if there is more open wall right of the face, else -1."""
    left = occ[:, :int(hcx / Q)]
    right = occ[:, int(hcx / Q):]
    return 1 if (1 - right).sum() > (1 - left).sum() else -1


def plan_layout():
    ks = [0.80, 0.72, 0.64, 0.57, 0.50] if tight else [1.0, 0.92, 0.84, 0.76, 0.68]
    bars = [640, 580, 520, 460, 400]
    fs = free_side() if person else -1
    want = [3, 2] if PANES == 'auto' else [int(PANES)]
    # three panes while they can stay a readable size; below 0.62x two bigger panes look better than three specks
    tries = [(p, k) for k in ks if k >= 0.62 for p in want[:1]] + [(p, k) for k in ks if k >= 0.62 for p in want[1:]] \
        + [(p, k) for k in ks if k < 0.62 for p in want]
    for npanes, k in tries:
        if True:
            options = []
            combos = [(fs, -fs), (-fs, fs), (fs, fs), (-fs, -fs)] if person else [(-1, 1)]
            for gs, rs in combos:
                placed, got, cost = [], {}, 0.0
                order = (('grid', gs), ('ring', rs), ('bar', 0)) if npanes == 3 else (('ring', rs), ('bar', 0))
                for role, side in order:
                    spot = None
                    for bw in (bars if role == 'bar' else [None]):
                        spot = best_spot(role, k, side, placed, bw)
                        if spot:
                            if role == 'bar':
                                spot = spot + (bw,)
                            break
                    if spot is None:
                        break
                    placed.append(spot[3])
                    got[role] = spot
                    cost += spot[0]
                if len(got) == npanes:
                    if npanes == 3 and gs == rs:
                        cost += 2.5                      # one pane each side of the speaker reads calmer
                    options.append((cost, gs, got))
            if options:
                cost, gs, got = min(options, key=lambda o: o[0])
                return npanes, k, gs, got
    return None


if LAYOUT != 'auto':
    got = {}
    for role, v in LAYOUT.items():
        cx, cy, k = v[:3]
        w = v[3] if role == 'bar' and len(v) > 3 else SIZES[role][0]
        got[role] = (0.0, cx, cy, box(cx, cy, w * k, SIZES[role][1] * k)) + ((w,) if role == 'bar' else ())
    npanes, kk = len(got), min(v[2] for v in LAYOUT.values())
    gside = -1 if got.get('grid', (0, 0))[1] < W / 2 else 1
    say(f'layout: from the CLIP block ({npanes} panes)')
else:
    res = plan_layout()
    if res is None:
        kmin = 0.50 if tight else 0.68
        for role in ('grid', 'ring', 'bar'):
            ok = [s for s in (-1, 1) if best_spot(role, kmin, s, [], 400 if role == 'bar' else None)]
            say(f'  {role} at {kmin}x alone: ' + (', '.join('left' if s < 0 else 'right' for s in ok) or 'no spot'))
        sweep = (FACE[2] - FACE[0] - 1.12 * hw - 56) + (FACE[3] - FACE[1] - 1.45 * hw - 56) if person else 0
        if sweep > 0.5 * hw:
            decline(f'the face moves about {sweep:.0f}px across the room during the effect (handheld or a lot of '
                    'head movement), so no spot on the wall stays clear of it for even two small glass panes. '
                    'Pick a steadier moment, or film with the phone on a stand.')
        decline('there is no open wall beside or below the face for even two small glass panes in this shot '
                '(the speaker fills the frame). Pick a moment with some room beside the speaker.')
    npanes, kk, gside, got = res
    why = ('3 panes' if npanes == 3 else '2 panes (no room for the grid: the bar types steps 1 and 2)')
    say(f'layout: {why} at {kk:.2f}x size, grid on the {"left" if gside < 0 else "right"}'
        if npanes == 3 else f'layout: {why} at {kk:.2f}x size')

WALL, PERSON_Z = 4.0, 2.65
k_of = {r: (LAYOUT[r][2] if LAYOUT != 'auto' else kk) for r in got}
panes = []
lab = [G.cased(s, CASE) for _, s in STEPS]
for role in (['grid', 'bar', 'ring'] if npanes == 3 else ['bar', 'ring']):
    sp = got[role]
    cx, cy = float(sp[1]), float(sp[2])
    w, h = (int(sp[4]) if role == 'bar' else SIZES[role][0]), SIZES[role][1]
    b = sp[3]
    p = dict(role=role, cx=cx, cy=cy, w=w, h=h, k=float(k_of[role]), r=46)
    if role == 'grid':
        p.update(z=2.5, frost=17, trans=0.84, defocus=0.0, soft=0.7, behind=False, recv=WALL, shadow=0.22,
                 shadow_behind=person, float=(3.0, 5.4, 0.55), t_in=arr[0],
                 content=dict(label=STEPS[0][1], t0=arr[0] + 0.16))
    elif role == 'bar':
        texts = ([(max(arr[1] + 0.30, cues[1] + 0.05), lab[1])] if npanes == 3 else
                 [(max(arr[0] + 0.30, cues[0] + 0.05), lab[0]), (max(arr[1] + 0.10, cues[1] + 0.05), lab[1])])
        if len(texts) == 2 and texts[1][0] < texts[0][0] + 0.12 * 2 + len(texts[0][1]) * 0.03:
            texts[1] = (texts[0][0] + 0.24 + len(texts[0][1]) * 0.03, texts[1][1])
        step = min(2 / FPS, 0.6 / max(len(t[1]) for t in texts))
        t_send = texts[-1][0] + step * len(texts[-1][1]) + 0.12
        on_person = frac(ii_occ, b) > 0.3
        p.update(z=1.9, frost=22, trans=0.72, defocus=0.0, soft=0.45, behind=False,
                 recv=PERSON_Z if on_person else WALL, shadow=0.20, shadow_behind=False, float=(3.4, 4.8, 0.9),
                 t_in=arr[1] if npanes == 3 else arr[0],
                 content=dict(texts=texts, type_step=step, t_send=t_send, longest=max((t[1] for t in texts), key=len)))
    else:
        f = frac(ii_occ, b)
        p.update(z=3.2, frost=10, trans=0.84, defocus=1.9, behind=bool(person and f > 0.01), recv=WALL, shadow=0.26,
                 float=(2.4, 6.1, 0.15), t_in=arr[2],
                 content=dict(label=lab[2], done_label=G.cased(DONE_LABEL, CASE) if DONE_LABEL else '',
                              t_prog0=arr[2] + 0.30, t_prog1=t_check - 0.02, t_check=t_check))
        say(f'ring pane: {"behind the speaker, " + str(int(round(f * 100))) + "% hidden at most times" if p["behind"] else "on the open wall"}')
    panes.append(p)
order = sorted(panes, key=lambda p: p['t_in'])
for j, p in enumerate(order):
    p['t_out'] = None if t_end is None else t_end - OUT_DUR - STAGGER * (len(order) - 1 - j)
    say(f'{p["role"]:4s} pane: centre ({p["cx"]:.0f}, {p["cy"]:.0f}) size {p["w"] * p["k"]:.0f}x{p["h"] * p["k"]:.0f}, '
        f'in {p["t_in"]:.2f}s' + ('' if p['t_out'] is None else f', out {p["t_out"]:.2f}s'))

# ---------------------------------------------------------------------------------------------------- the look
bg = union < 0.5
lum_q = cv2.resize(cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY), qs, interpolation=cv2.INTER_AREA)
room_l = float(np.median(lum_q[bg])) if bg.sum() > 200 else float(np.median(lum_q))
material = GLASS if GLASS != 'auto' else ('smoke' if room_l < 85 else 'light')
ink = list(INK) if INK != 'auto' else list(G.CREAM if material == 'smoke' else G.INK_DARK)
say(f'room brightness {room_l:.0f} -> {material} glass, {"cream" if ink == list(G.CREAM) else "dark"} type')
table = G.font_table(os.path.join('assets', 'fonts'))
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
style = dict(material=material, ink=ink, accent=list(ACCENT), check_ink=list(G.INK_DARK),
             arc=ink if material == 'light' else list(ACCENT), captions=ENV['CAPTIONS'],
             font_ui=G.pick_font(table, FONT, WEIGHT), font_label=G.pick_font(table, FONT, 600),
             font_serif=G.pick_font(table, FONT2, 400, ITALIC2))
say('fonts: ' + ', '.join(f'{k[5:]} {os.path.basename(style[k][0])}' for k in ('font_ui', 'font_label', 'font_serif')))

lamp = None
if LAMP == 'auto':
    hot = ((cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY) >= 248) & (cv2.resize(union, (W, H)) < 0.5)).astype(np.uint8)
    nl, labs, st, cen = cv2.connectedComponentsWithStats(hot, connectivity=8)
    cand = [(st[j, cv2.CC_STAT_AREA], cen[j]) for j in range(1, nl) if 120 <= st[j, cv2.CC_STAT_AREA] <= 40000]
    if cand:
        lamp = [float(v) for v in max(cand, key=lambda c: c[0])[1]]
elif LAMP:
    lamp = [float(v) for v in LAMP]
say(f'lamp in shot: {"(%d, %d): pane edges near it catch its light" % tuple(lamp) if lamp else "none"}')

# ---------------------------------------------------------------------------------------------------- camera
truck = (0.12 * (gside if npanes == 3 else -1)) if TRUCK == 'auto' else float(TRUCK)
cam = dict(f=1300.0, wall=WALL, push=float(PUSH), truck=truck, ease=1.45, t0=max(2 / FPS, arr[0] - 0.45),
           t1=t_end if t_end is not None else DUR, base=1.0, shift=[0.0, 0.0])
env_t = [cam['t0'], arr[0] + 0.10, None if t_end is None else t_end - OUT_DUR, t_end]
pl = dict(n=N, fps=FPS, ref=ref, cam=cam, env=env_t, out_dur=OUT_DUR, panes=panes, light=[-0.20, -0.42, 0.55],
          style=style, lamp=lamp, grade=GRADE, shot=shot, npanes=npanes)


def fit_base():
    """Smallest zoom that keeps the moved camera covering the frame at every moment."""
    edge = np.float32([[0, 0], [W / 2, 0], [W - 1, 0], [W - 1, H / 2], [W - 1, H - 1], [W / 2, H - 1], [0, H - 1],
                       [0, H / 2]])
    for base in np.arange(1.0, 1.10, 0.002):
        cam['base'] = float(base)
        c = G.Camera(pl)
        ok = True
        for i in range(N):
            hm, e = c.env_h(i / FPS)
            if e <= 0:
                continue
            src = G.apply_h(np.linalg.inv(hm), edge)
            if src[:, 0].min() < -0.01 or src[:, 0].max() > W - 0.99 or src[:, 1].min() < -0.01 or src[:, 1].max() > H - 0.99:
                ok = False
                break
        if ok:
            return
    say('!! the camera move cannot keep the frame covered: TRUCK or PUSH too big')


fit_base()
cam['base'] = float(cam['base'] + 0.001)

# safe zone on every frame (the panes float, grow on the push and ride the room track): shrink what pokes out
os.makedirs('work', exist_ok=True)
json.dump(pl, open('work/plan.json', 'w'), indent=1)
for attempt in range(6):
    sc = G.Scene(pl, HERE)
    bad = []
    for p in panes:
        bx = [sc.bbox(p, i) for i in range(N)]
        bx = np.array([b for b in bx if b is not None])
        x0, y0, x1, y1 = bx[:, 0].min(), bx[:, 1].min(), bx[:, 2].max(), bx[:, 3].max()
        right = W - G.SAFE['right_low'][1] if y1 > G.SAFE['right_low'][0] else W - G.SAFE['side']
        ok = x0 >= G.SAFE['side'] and y0 >= G.SAFE['top'] and x1 <= right and y1 <= G.SAFE['bottom']
        fx = FACE and any(hits(b, (FACE[0] + 18, FACE[1] + 18, FACE[2] - 18, FACE[3] - 18)) for b in bx)
        if not ok or fx:                                 # move by the overflow, shrink a little
            bad.append(p['role'])
            p['k'] *= 0.96
            p['cx'] += 1.15 * (max(0, G.SAFE['side'] - x0) - max(0, x1 - right))
            p['cy'] += 1.15 * (max(0, G.SAFE['top'] - y0) - max(0, y1 - G.SAFE['bottom']))
            if fx and FACE:
                p['cx'] += 16 * (1 if p['cx'] > hcx else -1)
    if not bad:
        break
    say(f'safe zone / face: {", ".join(bad)} shrunk 6% and pulled in (pass {attempt + 1})')
    json.dump(pl, open('work/plan.json', 'w'), indent=1)
else:
    decline('the panes keep touching the face or leaving the safe zone on this shot')

# ---------------------------------------------------------------------------------------------------- clean plate
if any(p['behind'] for p in panes) and alphas is not None:
    bs = [box(p['cx'], p['cy'], p['w'] * p['k'], p['h'] * p['k']) for p in panes if p['behind']]
    m = 150
    roi = (max(int(min(b[0] for b in bs)) - m, 0), max(int(min(b[1] for b in bs)) - m, 0),
           min(int(max(b[2] for b in bs)) + m, W), min(int(max(b[3] for b in bs)) + m, H))
    pm = dict(roi=roi, track=meta)
    if os.path.exists('work/plate.npz') and os.path.exists('work/plate_meta.json') and \
            json.load(open('work/plate_meta.json')) == json.loads(json.dumps(pm)):
        say('clean plate: reused work/plate.npz')
    else:
        x0, y0, x1, y1 = roi
        hh, ww = y1 - y0, x1 - x0
        shift = np.float64([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]])
        stack, valid, loose = [], [], []
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        for i, rgb in enumerate(reader('assets/aroll.mp4', W, H)):
            mm = shift @ np.linalg.inv(track[i])
            stack.append(cv2.warpPerspective(rgb, mm, (ww, hh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
            a = cv2.warpPerspective(alphas[i], mm, (ww, hh), flags=cv2.INTER_LINEAR)
            valid.append(cv2.dilate((a > 10).astype(np.uint8), ker) == 0)
            loose.append(a < 200)
        stack, valid, loose = np.array(stack), np.array(valid), np.array(loose)
        cnt = valid.sum(0)
        med = np.zeros((hh, ww, 3), np.float32)
        med2 = np.zeros((hh, ww, 3), np.float32)
        mad = np.full((hh, ww), 255.0, np.float32)
        with np.errstate(all='ignore'):
            import warnings
            warnings.simplefilter('ignore')
            for r0 in range(0, hh, 80):
                s = stack[:, r0:r0 + 80].astype(np.float32)
                s1 = s.copy()
                s1[~valid[:, r0:r0 + 80]] = np.nan
                med[r0:r0 + 80] = np.nan_to_num(np.nanmedian(s1, axis=0))
                s[~loose[:, r0:r0 + 80]] = np.nan
                m2 = np.nanmedian(s, axis=0)
                med2[r0:r0 + 80] = np.nan_to_num(m2)
                mad[r0:r0 + 80] = np.nan_to_num(np.nanmedian(np.abs(s - m2).max(axis=-1), axis=0), nan=255.0)
        k1 = cnt >= 6
        k2 = (~k1) & (loose.sum(0) >= min(24, N // 4)) & (mad <= 4.0)
        k2 = cv2.morphologyEx(k2.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
        med[k2] = med2[k2]
        known = (k1 | k2).astype(np.uint8) * 255
        np.savez('work/plate.npz', plate=np.clip(med + 0.5, 0, 255).astype(np.uint8), known=known,
                 roi=np.int32([x0, y0, x1, y1]))
        json.dump(pm, open('work/plate_meta.json', 'w'))
        say(f'clean plate: {float((known > 0).mean()) * 100:.0f}% of the room behind the ring pane is known '
            '(the rest is filled from around the speaker)')

# ---------------------------------------------------------------------------------------------------- sounds + index.html
sfx = []
if ENV['SFX']:
    files = G.make_sfx('assets_fx')
    for p in order:
        sfx.append(('air', p['t_in'] + 0.08 - files['air'][2]))
    if any(p['role'] == 'ring' for p in panes):
        sfx.append(('thump', t_check + 0.10))
cue_html = []
for key, t in sfx:
    path, length, _ = files[key]
    skip = max(0.0, -t)
    t = max(0.0, t)
    d = min(length - skip, DUR - t)
    if d > 0.05:
        cue_html.append(f'  <audio id="sfx_{len(cue_html)}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cue_html)}" data-volume="1"></audio>')

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)">'
              '</div></div>')
nl = '\n'
html = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#bgv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(cue_html)}
  <video id="bgv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open('index.html', 'w', encoding='utf-8', newline='\n').write(html)

fr = lambda t: min(N - 1, max(0, int(round(t * FPS))))
ring_on = any(p['role'] == 'ring' for p in panes)
marks = sorted({0, fr(arr[0] + 0.35), fr(arr[1] + 0.5), fr(arr[2] + 0.4), fr(t_check + 0.5),
                fr((t_end or DUR) - OUT_DUR * 0.5), N - 1})
stills = [fr(arr[1] + 0.6), fr(t_check + 0.5), fr(arr[2] + 0.3)]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
say('timing: ' + ', '.join(f'{p["role"]} {p["t_in"]:.2f}s' for p in order) + f', check {t_check:.2f}s, '
    + ('holds to the last frame (OUT = cut)' if t_end is None else f'all gone by {t_end:.2f}s'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  {npanes} panes  sounds {len(cue_html)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} GRADE={int(GRADE)} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(f) for f in marks[1:-1][:4]) + ' -g  (preview), then bake.py')
