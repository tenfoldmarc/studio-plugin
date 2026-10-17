#!/usr/bin/env python3
"""doodle-boil, step 1 of 3: plan. A chalk line boils round the speaker and chalk doodles draw on, on his words.

build.py   CLIP block + words.json + the cutout + the audio -> work/plan.json (where and when every stroke goes),
           assets_fx/chalk.wav (chalk scratch, synthesised here), index.html (plays assets/fx.mp4 + his audio + chalk)
bake.py    work/plan.json + assets/aroll.mp4 + assets/subject.webm -> assets/fx.mp4 (the chalk, baked frame by frame)
post.py    after the render: frame count, edge frames plain, phone copy, stills, contact sheets

Measures everything it can: the framing (head size and position from the cutout), the open space beside / above him
for each doodle, the room (how bright and busy it is, for the dim), the word onsets (Whisper snapped to the audio).
It prints what it chose and why. Switches: SAFE=1 safe-zone guide (snapshots only), SFX=0 no chalk sound,
DIM=0 no room dim, CAPTIONS / GRADE accepted and ignored (the effect draws no words and has no grade).
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chalk  # noqa: E402
import doodles  # noqa: E402

FF = shutil.which('ffmpeg') or 'ffmpeg'
FPS = 30


def F(n):
    """A time given as a frame number of the slot."""
    return n / FPS


def cue(word, doodle, cross=None, hold=None, where='auto', size=None, colour=None, fill=None, accent=None, rot=None,
        finale=False):
    return dict(word=word, shape=doodle, cross=cross, hold=hold, where=where, size=size, colour=colour, fill=fill,
                accent=accent, rot=rot, finale=finale)


# ==== CLIP (edit this) ====
# The doodles, one per idea, in the order they are said. cue(word, doodle, ...):
#   word    the spoken word it draws on: first match in words.json after the previous cue ('word#2' = 2nd time),
#           or a time in seconds, or F(frame). build.py snaps Whisper's start to the audio onset and prints it.
#   doodle  a name from the library table in effect.md (heart, clapper, chip, bulb, clock, dollar, check ...)
#   cross='word'   crosses / scribbles it out on that word ("I'm NOT techy"). hold='word' or seconds: when it rubs out
#           (default: HOLD_MAX after it lands, sooner if the next doodle needs its spot or the finale starts).
#   where   'auto' (most open space near his head) | 'left' | 'right' | 'above' | 'body' (on his torso, under the chin)
#   size    px, None = auto (from his head size, shrunk to fit the space). colour / fill / accent: 'cream' | 'yellow'
#           | 'pink' slot for the main line / scribble fill / other strokes. rot: tilt in degrees.
#   finale=True  the payoff: the outline goes double, rays burst round him, a few small stars sprinkle in (SPARKLE).
DOODLES = [
    cue('girlfriend', 'heart'),
    cue('suck', 'clapper', cross='video'),
    cue('not', 'chip', cross='techy'),
    cue('results', 'crown', finale=True),
]
OUTLINE = 'auto'      # 'auto' = single chalk line from the first doodle, double for the finale | 'single' | 'double' | 'off'
PALETTE = 'classic'   # 'classic' (cream, butter, pink) or 'blush' (cream, lilac, pink)
INK = None            # the buyer's colour for the main line (the cream slot), hex like '#FFF4E8'; None = palette
ACCENT = None         # the buyer's second colour (butter / lilac slot), hex; None = palette
ACCENT2 = None        # the third colour (pink slot), hex; None = palette. Never orange (Marc's rule for his reels).
DIM = 'auto'          # room dim behind him while chalk is up: 'auto' (from how bright and busy the room is) or 0 to 1
HOLD_MAX = 2.8        # seconds a doodle stays up when nothing else asks for its space
SPARKLE = 'auto'      # small stars that sprinkle in on the finale: 'auto' (as many as fit, up to 5) or 0 to 6
IN_FRAME = 3          # nothing appears before this frame (frame 0 must stay plain footage)
OUT_FRAME = -4        # everything is rubbed out by this frame (negative = from the end). None = hold to the last frame:
                      # only when the slot ends the reel or ends on a hard cut
SFX_PEAK_DB = -27.0   # chalk scratch peak (his voice peaks near -6 dBFS): -27 sits under him
# ==== END CLIP ====

W, H = chalk.W, chalk.H
ON = {k: os.environ.get(k, '1') != '0' for k in ('SFX', 'DIM')}
SAFE_ON = os.environ.get('SAFE', '0') not in ('', '0')
NAME = os.path.basename(HERE)
QW, QH, Q = 270, 480, 4          # quarter-res analysis grid
RAY_ANGLES = [-112, -96, -80, -64, -48, -33, 33, 48, 64, 80, 96, 112]   # degrees from straight up, torso centre


def say(*a):
    print(*a, flush=True)


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout


def smooth(v, sigma):
    if sigma <= 0 or len(v) < 3:
        return v
    r = int(3 * sigma)
    ker = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    ker /= ker.sum()
    ext = np.concatenate([np.repeat(v[:1], r), v, np.repeat(v[-1:], r)])
    return np.convolve(ext, ker, 'valid')


def hex_rgb(h):
    h = h.strip().lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------------------------------------------ slot inputs
clip = json.load(open(os.path.join(HERE, 'clip.json')))
N = int(clip['frames'])
DUR = N / FPS
f_in = max(1, int(IN_FRAME))
f_out = None if OUT_FRAME is None else (N + int(OUT_FRAME) if OUT_FRAME < 0 else int(OUT_FRAME))
T_IN = f_in / FPS
T_OUT = None if f_out is None else f_out / FPS
words = json.load(open(os.path.join(HERE, 'words.json'))) if os.path.exists(os.path.join(HERE, 'words.json')) else []

# --- audio onsets (Whisper word starts are 1 to 4 frames off; the chalk should touch the board on the syllable)
pcm = np.frombuffer(run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-ac', '1', '-ar', '16000',
                         '-f', 's16le', '-']), np.int16).astype(np.float32) / 32768
HOP = 160                                                   # 10 ms
env = np.sqrt(np.convolve(pcm ** 2, np.ones(HOP) / HOP, 'same')[::HOP] + 1e-12)


def onset(ws, we):
    """The word's real start: the quietest point just around Whisper's start (the gap before the word), then the
    first rise out of it."""
    i0, i1 = max(0, int((ws - 0.15) * 100)), min(len(env), max(int(we * 100), int((ws + 0.15) * 100)) + 1)
    if i1 - i0 < 4:
        return ws
    j1 = min(i1, int((ws + 0.08) * 100) + 1)
    v = i0 + int(np.argmin(env[i0:j1]))                  # the valley before the word
    peak = env[v:i1].max()
    k = np.nonzero(env[v:i1] > env[v] + 0.3 * (peak - env[v]))[0]
    return (v + int(k[0])) / 100 if len(k) else ws


def norm(s):
    return re.sub(r"[^a-z0-9']", '', s.lower().replace('’', "'"))


def when(spec, after=0.0, label=''):
    """A cue time: seconds, or a word (first match at or after `after`, 'word#2' = second time it is said)."""
    if spec is None:
        return None
    if isinstance(spec, (int, float)):
        return float(spec)
    w, _, nth = str(spec).partition('#')
    hits = [x for x in words if norm(x['text']) == norm(w)]
    if nth:
        hits = hits[int(nth) - 1:int(nth)]
    else:
        hits = [x for x in hits if x['start'] >= after - 0.05] or hits
    if not hits:
        sys.exit(f'cue word "{spec}" is not in words.json. Words: ' + ' '.join(x['text'] for x in words))
    x = hits[0]
    t = onset(x['start'], x['end'])
    say(f'  word "{w}"{label}: Whisper {x["start"]:.2f}s -> audio onset {t:.2f}s (f{t * FPS:.0f})')
    return t


# --- the speaker, from the cutout (quarter resolution)
sub_path = os.path.join(HERE, 'assets/subject.webm')
if os.path.exists(sub_path):
    al = np.frombuffer(run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', sub_path, '-vf',
                            f'alphaextract,scale={QW}:{QH}:flags=area,format=gray', '-f', 'rawvideo', '-']), np.uint8)
    al = al.reshape(-1, QH, QW)[:N]
    if len(al) < N:
        al = np.concatenate([al, np.repeat(al[-1:], N - len(al), 0)])
else:
    al = np.zeros((N, QH, QW), np.uint8)

present = np.zeros(N, bool)
hx, yt, hwq = np.zeros(N), np.zeros(N), np.zeros(N)
body = np.zeros((N, QH, QW), bool)
for i in range(N):
    m = (al[i] > 140).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2 or st[1:, cv2.CC_STAT_AREA].max() < 0.01 * QW * QH:
        continue
    m = lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    body[i] = m
    rows = np.nonzero(m.sum(1) >= 3)[0]
    y0 = int(rows[0])
    top = np.nonzero(m[y0:y0 + 8].any(0))[0]
    cx = int(round((top[0] + top[-1]) / 2))
    wmax = 0
    for k, y in enumerate(range(y0, QH)):
        xs = np.nonzero(m[y])[0]
        if not len(xs):
            break
        j = xs[np.argmin(np.abs(xs - cx))]                  # the run of the row that holds the head's centre line
        l, r = j, j
        while l > 0 and m[y, l - 1]:
            l -= 1
        while r < QW - 1 and m[y, r + 1]:
            r += 1
        w = r - l + 1
        if wmax and k > 0.7 * wmax and w > 1.5 * wmax:      # shoulders start
            break
        if wmax and k > 1.35 * wmax:                        # a head is about 1.35 widths tall
            break
        wmax = max(wmax, w)
        if k < 0.6 * max(wmax, 1):
            cx = (l + r) // 2
    present[i], hx[i], yt[i], hwq[i] = True, cx, y0, wmax

PERSON = present.mean() > 0.6
if PERSON:
    idx = np.nonzero(present)[0]
    for v in (hx, yt, hwq):                                  # fill gaps where the matte lost him, then smooth
        v[:] = np.interp(np.arange(N), idx, v[idx])
    HX, YT = smooth(hx * Q + 2, 3.5), smooth(yt * Q, 3.5)
    HW = smooth(hwq * Q, 8.0)
else:
    HX, YT, HW = np.full(N, 540.0), np.full(N, 560.0), np.full(N, 260.0)
HCY = YT + 0.62 * HW                                         # head centre
hw_med = float(np.median(HW))
FACE = np.stack([HX - 0.58 * HW, YT - 12, HX + 0.58 * HW, YT + 1.42 * HW], 1)    # never covered
area = body.reshape(N, -1).mean(1) if PERSON else np.zeros(N)
if not PERSON:
    framing = 'none'
elif hw_med > 0.30 * W:
    framing = 'close'
elif hw_med > 0.19 * W:
    framing = 'medium'
else:
    framing = 'wide'
say(f'slot "{NAME}": {N} frames, effect from f{f_in} to ' + (f'f{f_out}' if f_out is not None else 'the last frame (held)'))
if PERSON:
    off = (np.median(HX) - W / 2) / W
    say(f'framing: {framing} (head {hw_med:.0f}px wide = {hw_med / W:.0%} of the frame, top of head at y{np.median(YT):.0f}, '
        f'{"centred" if abs(off) < 0.08 else ("left" if off < 0 else "right") + f" of centre by {abs(off):.0%}"}, '
        f'body {np.median(area):.0%} of the frame, head moves {np.ptp(HX):.0f}px x / {np.ptp(YT):.0f}px y)')
else:
    say('framing: no person in the cutout (voice-over or b-roll): doodles only, round the upper middle; outline, '
        'rays and the person-shaped dim are off')
    say('  !! placement cannot see a face without a cutout: if someone IS on screen, make the slot with a cutout')

# integral images of the body (dilated 12 px) for fast "how much of this box is on him" checks
kern = np.ones((7, 7), np.uint8)
INTG = np.zeros((N, QH + 1, QW + 1), np.int32)
for i in range(N):
    b = cv2.dilate(body[i].astype(np.uint8), kern) if PERSON else body[i].astype(np.uint8)
    INTG[i, 1:, 1:] = b.cumsum(0).cumsum(1)

# --- the room (for the dim): how bright and how busy the wall behind him is
mid = N // 2
fr = np.frombuffer(run([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vf',
                        f"select=eq(n\\,{mid}),scale={QW}:{QH}", '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']),
                   np.uint8).reshape(QH, QW).astype(np.float32)
bg = cv2.erode((~body[mid]).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0 if PERSON else np.ones((QH, QW), bool)
lum = float(fr[bg].mean()) if bg.any() else 100.0
busy = float(np.abs(cv2.Laplacian(fr, cv2.CV_32F))[bg].mean()) if bg.any() else 4.0
hot = float((fr[bg] > 235).mean()) if bg.any() else 0.0
if DIM == 'auto':
    dim_base = float(np.clip(0.62 + (lum - 90) / 170 + (busy - 5) * 0.03 + hot * 1.5, 0.35, 0.85))
    if not PERSON:
        dim_base = min(dim_base, 0.45)
    why = f'room luma {lum:.0f}, texture {busy:.1f}, blown-out {hot:.0%}'
else:
    dim_base, why = float(DIM), 'set in the CLIP block'
dim_base = dim_base if ON['DIM'] else 0.0
dim_fin = min(1.0, dim_base + 0.22) if dim_base > 0 else 0.0
room = 'plain dark' if lum < 60 else 'window / lamp' if hot > 0.03 else 'busy' if busy > 7 else 'open wall'
say(f'room: {room} ({why}) -> dim {dim_base:.2f}, finale {dim_fin:.2f}' + ('' if ON['DIM'] else '  (DIM=0)'))

# ----------------------------------------------------------------------------------------------------- timeline
say('cues:')
cues, t_prev = [], 0.0
for i, c in enumerate(DOODLES):
    if c['shape'] not in doodles.SHAPES:
        sys.exit(f'unknown doodle "{c["shape"]}". Library: {", ".join(sorted(doodles.SHAPES))}')
    t = when(c['word'], t_prev, f' ({c["shape"]})')
    d = dict(c, t_in=max(T_IN, t - 0.03))
    if c['cross'] is not None:
        d['cross'] = when(c['cross'], t, ' (cross)')
    d['t_hold'] = when(c['hold'], t, ' (hold)') if isinstance(c['hold'], str) else (
        None if c['hold'] is None else d['t_in'] + float(c['hold']))
    cues.append(d)
    t_prev = t
cues.sort(key=lambda d: d['t_in'])
fin = next((d for d in cues if d['finale']), None)
T_FIN = fin['t_in'] if fin else None
T_END = (T_OUT - 0.22) if T_OUT is not None else None        # doodles start rubbing out here (gone by T_OUT)

for i, d in enumerate(cues):
    if d['rot'] is None:
        d['rot'] = -5 if d['shape'] == 'crown' else [8, -5, 6, -7, 4][i % 5]
    st = chalk.schedule(dict(d, size=1))
    d['drawn'] = max(s['t0'] + s['dur'] for s in st)          # when its last stroke lands
    if d['finale']:
        d['t_out'] = T_END
    else:
        out = d['t_hold'] if d['t_hold'] is not None else max(d['drawn'], d['cross'] or 0) + HOLD_MAX
        out = max(out, d['drawn'] + 0.5, (d['cross'] or 0) + 0.6)
        if T_FIN is not None and T_FIN > d['t_in']:      # make way for the finale, unless it has only just landed
            out = min(out, max(T_FIN - 0.10, d['drawn'] + 0.9, (d['cross'] or 0) + 0.6))
        if T_END is not None:
            out = min(out, T_END)
        d['t_out'] = out

# ----------------------------------------------------------------------------------------------------- placement
SZ_BASE = float(np.clip(1.35 * hw_med, 130, 280)) if PERSON else 230.0
SZ_MIN = 96.0


def frames_of(a, b):
    f0 = max(0, int(a * FPS))
    f1 = N - 1 if b is None else min(N - 1, int(math.ceil((b + 0.16) * FPS)))
    return np.arange(f0, f1 + 1, 2) if f1 > f0 else np.array([f0])


def box_ok(cxy, half, fs, allow_body, live, avoid_face=True):
    """cxy: (len(fs), 2) centres. True when the box is inside the safe zone, off his face, mostly off his body and
    clear of the doodles that are up at the same time."""
    x0, y0, x1, y1 = cxy[:, 0] - half, cxy[:, 1] - half, cxy[:, 0] + half, cxy[:, 1] + half
    S = chalk.SAFE
    right = np.where(y1 > S['right_from'], W - S['right'], W - S['side'])
    if (x0 < S['side'] + 6).any() or (x1 > right - 6).any() or (y0 < S['top'] + 6).any() or (y1 > S['bottom'] - 6).any():
        return False
    if avoid_face and PERSON:
        fb = FACE[fs]
        if ((x0 < fb[:, 2]) & (x1 > fb[:, 0]) & (y0 < fb[:, 3]) & (y1 > fb[:, 1])).any():
            return False
    if PERSON and allow_body < 1:
        qx0 = np.clip((x0 / Q).astype(int), 0, QW)
        qx1 = np.clip((x1 / Q).astype(int), 0, QW)
        qy0 = np.clip((y0 / Q).astype(int), 0, QH)
        qy1 = np.clip((y1 / Q).astype(int), 0, QH)
        I = INTG[fs]
        r = np.arange(len(fs))
        on = I[r, qy1, qx1] - I[r, qy0, qx1] - I[r, qy1, qx0] + I[r, qy0, qx0]
        if (on / np.maximum((qx1 - qx0) * (qy1 - qy0), 1)).max() > allow_body:
            return False
    for o in live:
        g = o['half'] + half + 14
        oc = o['centres'][fs]
        alive = (fs / FPS >= o['t_in'] - 0.05) & (fs / FPS <= o['t_out'] + 0.16)
        hit = (np.abs(oc[:, 0] - cxy[:, 0]) < g) & (np.abs(oc[:, 1] - cxy[:, 1]) < g) & alive
        if hit.any():
            return False
    return True


def place(d, live, prev_side, sizes, prefer, want_dr=None):
    """Best (size, offset from the head anchor) for one doodle, or None."""
    fs = frames_of(d['t_in'], d['t_out'])
    A = np.stack([HX, YT], 1)
    HC = np.stack([HX, HCY], 1)
    best = None
    where = d['where']
    allow_body = 1.0 if where == 'body' else 0.05
    for s in sizes:
        half = 0.58 * s + 4
        if where == 'body':
            cands = [(dx * hw_med, dy) for dx in (0, -0.45, 0.45, -0.8, 0.8) for dy in (0, 60, 130, 210)]
            base_pts = [(HC[fs, 0] + dx, FACE[fs, 3] + half + 18 + dy) for dx, dy in cands]
        else:
            r0 = 0.5 * hw_med + half * 0.9 + 8
            base_pts, cands = [], []
            for th in range(-135, 136, 15):
                if where == 'left' and th > -20 or where == 'right' and th < 20 or where == 'above' and abs(th) > 40:
                    continue
                for dr in (0, 30, 70, 120, 180, 250, 330):
                    a = math.radians(th)
                    r = r0 + dr
                    base_pts.append((HC[fs, 0] + r * math.sin(a), HC[fs, 1] - r * math.cos(a)))
                    cands.append((th, dr))
        for (cx, cy), cnd in zip(base_pts, cands):
            cxy = np.stack([np.broadcast_to(cx, fs.shape), np.broadcast_to(cy, fs.shape)], 1).astype(np.float64)
            if not box_ok(cxy, half, fs, allow_body, live):
                continue
            if where == 'body':
                cost = abs(cnd[0]) * 0.3 + cnd[1] * 0.5
                side = 0
            else:
                th, dr = cnd
                side = -1 if th < -10 else 1 if th > 10 else 0
                want = prefer if prefer is not None else 70
                cost = (dr if want_dr is None else abs(dr - want_dr)) * 0.9 + abs(abs(th) - want) * 1.3
                cost += max(0.0, float(np.median(cy - HC[fs, 1]))) * 0.25        # below the eyes reads less well
                if prev_side and side == prev_side:
                    cost += 70                                                  # alternate sides like a hand would
            cost += (sizes[0] - s) * 1.6
            if best is None or cost < best[0]:
                off = np.median(np.stack([np.broadcast_to(cx, fs.shape), np.broadcast_to(cy, fs.shape)], 1) - A[fs], 0)
                best = (cost, s, off, side)
    return best


placed, prev_side = [], 0
say('placement (head anchor follows him; boxes kept off his face, inside the safe zone):')
for i, d in enumerate(cues):
    base = d['size'] or (SZ_BASE * (1.0 if d['shape'] not in ('crown',) else 0.85))
    sizes = [base] if d['size'] else [base * k for k in (1.0, 0.88, 0.77, 0.67, 0.58, 0.5) if base * k >= SZ_MIN] or [SZ_MIN]
    prefer = 0 if d['shape'] == 'crown' or d['where'] == 'above' else None
    live = [p for p in placed if p['t_out'] > d['t_in']]
    res = place(d, live, prev_side, sizes, prefer)
    if res is None and live:
        for p in live:                                           # make room: the older doodles rub out as this one lands
            p['t_out'] = max(p['drawn'] + 0.25, d['t_in'] + 0.08)
        res = place(d, [p for p in live if p['t_out'] > d['t_in'] + 0.1], prev_side, sizes, prefer)
        if res:
            say(f'  ({d["shape"]}: no room beside the doodles still up, so they rub out as it lands)')
    if res is None and d['where'] == 'auto' and PERSON:
        res = place(dict(d, where='body'), live, 0, sizes, None)
        if res:
            say(f'  ({d["shape"]}: no open space near his head, drawn on his torso under the chin)')
    if res is None:
        say(f'  SKIPPED {d["shape"]} on "{d["word"]}": no space for it even at {SZ_MIN:.0f}px')
        continue
    cost, s, off, side = res
    d['size'], d['offset'] = float(s), off
    d['half'] = 0.58 * s + 4
    d['centres'] = np.stack([HX, YT], 1) + off
    prev_side = side or prev_side
    placed.append(d)
    c = d['centres'][min(N - 1, int(d['t_in'] * FPS))]
    say(f'  {d["shape"]:12s} f{d["t_in"] * FPS:5.1f} to f{d["t_out"] * FPS:5.1f}  size {s:4.0f}px  at ({c[0]:4.0f},{c[1]:5.0f})'
        f'  {"left of" if c[0] < HX[0] - 30 else "right of" if c[0] > HX[0] + 30 else "above / below"} his head'
        + (f'  cross f{d["cross"] * FPS:.0f}' if d['cross'] else ''))

if not placed:
    sys.exit('Doodle Boil cannot run on this clip: there is no open space beside, above or under the speaker\'s face '
             'for even a small doodle inside the safe zone (the head fills the frame). Use a wider take.')

# finale extras: small stars sprinkled into whatever open space is left
sprinkles = []
if fin is not None and fin in placed:
    n_sp = 5 if SPARKLE == 'auto' else int(SPARKLE)
    kinds = [('star', dict(fill='yellow')), ('star', dict(fill='pink')), ('pentagram', {}), ('pentagram', dict(colour='yellow')),
             ('spiral', {}), ('star', dict(colour='yellow'))]
    sp_side = 1
    for k in range(n_sp):
        shp, kw = kinds[k % len(kinds)]
        d = dict(cue(None, shp, where='auto', rot=[-10, 14, 8, -12, 0, -6][k]), **kw)
        d.update(t_in=fin['t_in'] + 0.20 + 0.12 * k, t_out=T_END, cross=None, finale=False, drawn=fin['t_in'] + 0.6)
        if T_END is not None and d['t_in'] > T_END - 0.5:          # no time left to see it before the rub-out
            break
        base = max(SZ_MIN * 0.62, min(0.5 * SZ_BASE, 130.0))
        res = place(d, placed + sprinkles, sp_side, [base, base * 0.82, base * 0.68], [80, 45, 100, 20, 60, 90][k],
                    [40, 160, 90, 230, 10, 120][k])
        if res is None:
            continue
        cost, s, off, side = res
        d['size'], d['offset'], d['half'] = float(s), off, 0.58 * s + 4
        d['centres'] = np.stack([HX, YT], 1) + off
        sp_side = -side if side else -sp_side
        sprinkles.append(d)
    say(f'finale on "{fin["word"]}" f{fin["t_in"] * FPS:.0f}: ' + ('double outline, rays, ' if PERSON else '')
        + f'{len(sprinkles)} sprinkles')

say('timeline: ' + ', '.join(f'{d["shape"]} f{d["t_in"] * FPS:.0f}-' + (f'f{d["t_out"] * FPS:.0f}' if d['t_out'] else 'end')
                             for d in sorted(placed + sprinkles, key=lambda x: x['t_in'])))

# outlines
outlines = []
style = OUTLINE if PERSON else 'off'
first = min(d['t_in'] for d in placed)
lw = 10.5 * float(np.clip((hw_med / 165) ** 0.5, 0.9, 1.35)) if PERSON else 10.5
o_end = (T_OUT - 0.40) if T_OUT is not None else None
if style == 'auto':
    o_in = max(T_IN, first - 0.46)
    regular = [d for d in placed if not d['finale']]
    gap = (T_FIN - max(d['t_out'] for d in regular)) if (T_FIN is not None and regular) else 0
    keep = False
    if T_FIN is not None and T_FIN - o_in > 1.0:
        if gap >= 0.6:      # the words leave a breath before the payoff: the line rubs out, then comes back double
            outlines.append(dict(t_in=o_in, t_out=max(o_in + 0.8, T_FIN - 0.75), style='single', draw=0.46, undraw=0.36))
        else:               # no breath: the single line stays and the finale adds the second line round it
            outlines.append(dict(t_in=o_in, t_out=T_FIN - 0.06, style='single', draw=0.46, undraw=0.0))
            keep = True
    if T_FIN is not None:
        outlines.append(dict(t_in=max(T_IN, T_FIN - 0.06), t_out=o_end, style='double', draw=0.30, undraw=0.36,
                             keep_inner=keep))
    else:
        outlines.append(dict(t_in=o_in, t_out=o_end, style='single', draw=0.46, undraw=0.36))
elif style in ('single', 'double'):
    outlines.append(dict(t_in=max(T_IN, first - 0.46), t_out=o_end, style=style, draw=0.46 if style == 'single' else 0.30,
                         undraw=0.36))

# room dim keys: arrives with the chalk, hands back in a long gap, deeper for the finale, gone by OUT
spans = sorted([(o['t_in'], (o['t_out'] or DUR) + o['undraw']) for o in outlines] +
               [(d['t_in'], (d['t_out'] or DUR) + 0.16) for d in placed])
merged = []
for a, b in spans:
    if merged and a <= merged[-1][1] + 0.6:
        merged[-1][1] = max(merged[-1][1], b)
    else:
        merged.append([a, b])
keys = [(0.0, 0.0)]
for a, b in merged:
    lvl_a = dim_fin if (T_FIN is not None and a >= T_FIN - 0.1) else dim_base
    keys += [(max(a - 0.05, keys[-1][0] + 0.01), 0.0), (a + 0.5, lvl_a)]
    if T_FIN is not None and a < T_FIN - 0.1 < b:
        keys += [(T_FIN - 0.06, dim_base), (T_FIN + 0.28, dim_fin)]
    end = min(b, T_OUT) if T_OUT is not None else b
    if end < DUR - 0.01:
        keys += [(max(end - 0.34, keys[-1][0] + 0.01), keys[-1][1]), (end, 0.0)]
if T_OUT is not None:
    keys = [(t, v) for t, v in keys if t <= T_OUT] + [(T_OUT, 0.0)]
if not PERSON:
    keys = [(t, v * 0.6) for t, v in keys]

# rays (finale)
rays = None
if fin is not None and fin in placed and PERSON:
    rays = dict(t_in=fin['t_in'] + 0.10, t_out=T_END, scale=float(np.clip(hw_med / 165, 0.75, 1.4)))
BODYC = np.stack([HX, np.minimum(YT + 2.6 * HW, H - 260)], 1)

pal = dict(doodles.PALETTES[PALETTE])
for slot, v in (('cream', INK), ('yellow', ACCENT), ('pink', ACCENT2)):
    if v:
        pal[slot] = hex_rgb(v)

os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
plan = dict(name=NAME, frames=N, fps=FPS, palette=pal, dim_keys=keys, person=bool(PERSON), line_width=lw,
            outlines=outlines, rays=rays, body_centres=BODYC.round(1).tolist(), ray_angles=RAY_ANGLES,
            doodles=[dict(shape=d['shape'], t_in=d['t_in'], t_out=d['t_out'], size=d['size'], rot=d['rot'],
                          colour=d.get('colour'), fill=d.get('fill'), accent=d.get('accent'), cross=d.get('cross'),
                          centres=d['centres'].round(1).tolist()) for d in placed + sprinkles],
            framing=framing, room=room)
json.dump(plan, open(os.path.join(HERE, 'work/plan.json'), 'w'))


# ----------------------------------------------------------------------------------------------------------- sound
def sfx_events():
    ev = []
    for o in outlines:
        ev.append((o['t_in'], o['draw'], 0.9 if o['style'] == 'single' else 1.0, 0))
        if o['style'] == 'double':
            ev.append((o['t_in'] + 0.07, o['draw'], 0.8, 0))
    if rays:
        for k in range(len(RAY_ANGLES)):
            ev.append((rays['t_in'] + k * 0.016, 0.07, 0.45, 0))
    for d in plan['doodles']:
        for s in chalk.schedule(dict(d)):
            g = 0.55 if s['kind'] == 'fill' else 1.0 if s['kind'] == 'zig' or s['color'] == 'pink' else 0.7
            zig = s.get('zig', 6 if s['kind'] == 'fill' else 0)
            if d['t_out'] is None or s['t0'] < d['t_out']:
                ev.append((s['t0'], max(s['dur'], 0.035), g, zig))
    return ev


def synth_sfx(path, dur, sr=48000):
    n = int(round(dur * sr))
    out = np.zeros(n)
    rng = np.random.default_rng(77)
    for (t0, d, gain, zig) in sfx_events():
        m = int(d * sr)
        i0 = int(t0 * sr)
        if i0 >= n or m < 32:
            continue
        tt = np.arange(m) / sr
        e = np.minimum(1, tt / 0.006) * np.minimum(1, (d - tt) / min(0.03, d / 2))
        e *= 0.6 + 0.4 * np.clip(chalk.snoise(rng, m, sr / 28.0), -1.5, 1.5) / 1.5
        if zig:
            e *= 0.45 + 0.55 * np.abs(np.sin(math.pi * zig * tt / d)) ** 0.7
        rasp = 0.35 + 0.65 * np.abs(chalk.snoise(rng, m, sr / 330.0))
        x = rng.standard_normal(m) * e * rasp * gain
        j = min(n, i0 + m)
        out[i0:j] += x[:j - i0]
    spec = np.fft.rfft(out)
    fr_ = np.fft.rfftfreq(n, 1 / sr)
    band = 1 / (1 + (1900 / np.maximum(fr_, 1)) ** 6) * 1 / (1 + (fr_ / 7500) ** 6)
    band *= 1 + 1.4 * np.exp(-0.5 * ((fr_ - 3300) / 500) ** 2)       # the dry squeak of chalk
    out = np.fft.irfft(spec * band, n)
    pk = np.abs(out).max()
    if pk > 0:
        out *= 10 ** (SFX_PEAK_DB / 20) / pk
    pcm16 = (np.clip(out, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.repeat(pcm16, 2).tobytes())


audio = ''
if ON['SFX']:
    os.makedirs(os.path.join(HERE, 'assets_fx'), exist_ok=True)
    synth_sfx(os.path.join(HERE, 'assets_fx/chalk.wav'), DUR)
    audio = (f'  <audio id="chalk" src="assets_fx/chalk.wav" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" '
             f'data-track-index="3" data-volume="1"></audio>')

# ------------------------------------------------------------------------------------------------------- index.html
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#fxv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{audio}
  <video id="fxv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE_ON else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open(os.path.join(HERE, 'index.html'), 'w').write(page)

# ------------------------------------------------------------------------------------------------- frames to check
marks, stills = {0, N - 1}, []
for d in plan['doodles']:
    st = chalk.schedule(dict(d))
    done = max(s['t0'] + s['dur'] for s in st if not s['ev'])
    marks |= {min(N - 1, int(d['t_in'] * FPS) + 4), min(N - 1, int(done * FPS) + 2)}
    if d['cross']:
        marks.add(min(N - 1, int((max(s['t0'] + s['dur'] for s in st)) * FPS) + 2))
    if d['t_out'] is not None:
        marks.add(min(N - 1, int((d['t_out'] + 0.2) * FPS)))
for d in placed:
    st = chalk.schedule(dict(d, size=1))
    stills.append(min(N - 1, int(max(s['t0'] + s['dur'] for s in st) * FPS) + 3))
if fin is not None:
    stills = stills[:2] + [min(N - 1, int((fin['t_in'] + 1.0) * FPS))]
json.dump({'name': NAME, 'frames': N, 'marks': sorted(marks), 'stills': stills[:3]},
          open(os.path.join(HERE, 'work/marks.json'), 'w'))
o_txt = ', '.join('%s from %.2fs' % (o['style'], o['t_in']) for o in outlines) or 'off'
say(f'outline: {o_txt}   line {lw:.1f}px')
say(f'dim keys: ' + ' '.join(f'{t:.2f}:{v:.2f}' for t, v in keys))
say(f'wrote work/plan.json, index.html' + (', assets_fx/chalk.wav' if ON['SFX'] else ' (SFX=0: no chalk sound)')
    + ('   SAFE guide ON: snapshots only, run build.py again without SAFE before the render' if SAFE_ON else ''))
say(f'check frames (work/marks.json): {sorted(marks)}')
say('next: bake.py (writes assets/fx.mp4)')
