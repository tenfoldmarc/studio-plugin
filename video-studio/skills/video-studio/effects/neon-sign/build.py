#!/usr/bin/env python3
"""neon-sign, step 1: measure the clip, choose where the sign hangs, trace the lettering, build the glass and the
light maps, write work/plan.json + work/static.npz, the sounds (assets_fx/) and index.html.

The speaker's phrase as a glass-tube neon sign on their wall: it fades on unlit, strikes on the word with an
irregular flicker, the room drops most of a stop, the sign lights the wall and the side of the speaker facing it,
then it switches off and the slot ends on plain footage.

  PY build.py            measure + choose the placement (prints which one and why) + prep + index.html
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             accepted for the contract; the sign IS the effect, so it stays (the reel captions as usual)
  SFX=0                  no buzz / thump
  GRADE=1                not used (the room dim is the effect and is gone before the slot ends)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import os
import re
import subprocess
import sys
import wave

import cv2
import numpy as np

import neon
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
LINES = [                 # the sign, one glass tube per line, top to bottom: (text, strike). Use the speaker's own
    ('your', 'auto'),     # words, 1 to 3 short lines. strike: a word from words.json ('this', 'this#2' = its 2nd time),
    ('words.', 'auto'),   # seconds, or 'auto' (the line's first word in words.json). *text* = the line in ACCENT
]
UNDERLINE = 'auto'        # a swash tube under the last line: 'auto' (strikes 0.4 s after the last line), a word,
                          # seconds, or None
STEP_ON = None            # a word where the whole sign steps brighter with a low thump ('like THAT'), or None
OUT = 'auto'              # 'auto' (switches off, plain footage 3 frames before the end), seconds (switch-off time),
                          # or 'cut' (stays lit to the last frame; only when the reel cuts away right after)
FONT = 'Marck Script'     # any family in assets/fonts/fonts.css. A script face reads as hand-bent neon (the demo);
                          # a sans (Figtree, Montserrat) gives a clean monoline sign. The glyphs are thinned to one tube
WEIGHT = 400              # weight (variable fonts follow it; a static file stays what it is)
CASE = 'as typed'         # 'as typed', 'upper', 'lower', 'title'
INK = (250, 230, 122)     # tube colour (butter yellow FAE67A, the demo). Pale colours glow best; never orange
ACCENT = 'ink'            # underline and *line* colour: 'ink' (same as INK) or (r, g, b), e.g. the buyer's highlight
ALIGN = 'stagger'         # 'stagger' (each line steps right, sign-painter look), 'left', 'centre'
TILT = 4.0                # degrees the lines climb to the right (0 = level; 4 = the demo)
PLACE = 'auto'            # 'auto' or force 'beside' / 'above' / 'corner'; or (x, y, size): left end of the first
                          # baseline in 1080x1920 px of frame 0 and the letter size in px (read off a preview still)
SIDE = 'auto'             # beside the head: 'auto' (the side with more open wall), 'left', 'right'
SIZE_MAX = 200            # largest letter size in px (the demo: 196)
FLICKER = 'classic'       # 'classic' (irregular strike, the demo) or 'soft' (two quick pulses, then steady)
ROOM_DIM = 'auto'         # room exposure while lit (0.56 = most of a stop); 'auto' sets it from how bright the room is
SPILL = 1.0               # wall glow strength multiplier
CABLE = None              # optional visible flex: list of (x, y) frame-0 px from a tube end to where it hides behind
                          # something (the couch, the speaker). None = wired through the wall (nothing shows)
OCCLUDERS = []            # optional shadows: [([(x, y), ...] polygon in frame-0 px, depth px), ...] for things that
                          # stand proud of the wall right next to the sign (a frame: 18, a wall light: 110). [] = none
BUZZ_DB, THUMP_DB = -33.0, -27.0   # sound peaks (dBFS); the voice peaks around -5
# ==== END CLIP ====

ENV_SFX = os.environ.get('SFX', '1') != '0'
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = 1080, 1920, 30
Q = 2                                       # measurement runs at half size
HW_, HH_ = W // Q, H // Q
REF = 196.0                                 # the demo's letter size: every length below scales from it
YELLOW = (250, 230, 122)

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
if not os.path.exists('assets/subject.webm'):
    sys.exit('neon-sign needs the cutout (assets/subject.webm): make the slot without --no-cutout')
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg, flush=True)


def ell(k):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = len(a) // 160                                   # 10 ms
    return np.sqrt((a[:n * 160].reshape(n, 160) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    # the dip before the word: from just before Whisper's start to a little into the word (never into the next one)
    i0, i1 = max(0, int((s - 0.15) * 100)), min(len(ENVL) - 1, int((s + min(0.25, 0.5 * (e - s))) * 100))
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(ENVL[i0:i1 + 1]))
    i_end = min(len(ENVL), max(int((e + 0.1) * 100), im + 12))
    pk = ENVL[im:i_end + 1].max()
    thr = ENVL[im] + 0.35 * (pk - ENVL[im])
    for i in range(im, i_end):
        if ENVL[i] >= thr:
            return i / 100.0
    return s


def when(v, after=0.0):
    """CLIP time -> (seconds, how it was found). A word: its first match at or after `after` unless '#n' is given."""
    if isinstance(v, (int, float)):
        return float(v), 'seconds'
    key, nth = (v.split('#') + [''])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if nth:
        if len(hits) < int(nth):
            sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
        w = hits[int(nth) - 1]
    else:
        later = [w for w in hits if w['start'] >= after - 0.05]
        if not later:
            sys.exit(f'"{key}" is not in words.json (after {after:.2f}s). Words: ' + ' '.join(
                f"{w['text']}@{w['start']:.2f}" for w in words))
        w = later[0]
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


def cased(s):
    if CASE == 'upper':
        return s.upper()
    if CASE == 'lower':
        return s.lower()
    if CASE == 'title':
        return re.sub(r"(^|\s)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


if not LINES or len(LINES) > 3:
    sys.exit('LINES needs 1 to 3 lines of text')
ink = tuple(INK)
acc = ink if ACCENT == 'ink' else tuple(ACCENT)
lines = []
t_prev = 0.0
for i, (text, strike) in enumerate(LINES):
    accent = text.startswith('*') and text.endswith('*')
    txt = cased(text.strip('*'))
    if strike == 'auto' or strike is None:
        first = norm(txt.split()[0]) if txt.split() else ''
        if any(norm(w['text']) == first and w['start'] >= t_prev - 0.05 for w in words):
            t, how = when(first, t_prev)
        else:
            t, how = 0.6 + 0.45 * i, 'no matching word: placeholder time (set it in the CLIP block)'
    else:
        t, how = when(strike, t_prev)
    if lines and t < lines[-1]['t'] + 4 / FPS:      # two tubes on one beat read as one: keep them 4 frames apart
        t = lines[-1]['t'] + 4 / FPS
    t_prev = t + 0.05
    lines.append(dict(text=txt, t=t, how=how, colour=acc if accent else ink))
FIRST_OK = 8                                     # frames of plain picture + the unlit fade before the first strike
for ln in lines:
    ln['f'] = int(round(ln['t'] * FPS))
if lines[0]['f'] < FIRST_OK:
    say(f'!! the first strike is at frame {lines[0]["f"]}: moved to {FIRST_OK} (start the slot a little earlier)')
    d = FIRST_OK - lines[0]['f']
    for ln in lines:
        ln['f'] += d
und = None
if UNDERLINE is not None:
    if UNDERLINE == 'auto':
        uf, uhow = lines[-1]['f'] + 12, '0.4 s after the last line'
    else:
        ut, uhow = when(UNDERLINE, lines[-1]['t'])
        uf = int(round(ut * FPS))
    und = dict(f=max(uf, lines[-1]['f'] + 4), how=uhow)
TAIL = len([0.85, 0.20, 0.55, 0.0]) + 3 + 9 + 3   # off flicker, unlit hold, fade, plain frames
if OUT == 'cut':
    f_off = None
elif isinstance(OUT, (int, float)):
    f_off = int(round(OUT * FPS))
else:
    f_off = N - TAIL
last_on = max([ln['f'] for ln in lines] + ([und['f']] if und else []))
if f_off is not None and f_off < last_on + 24:
    say(f'!! the sign is fully lit for only {(f_off - last_on) / FPS:.2f}s before it switches off (about 1.5 s reads '
        'well): start the slot earlier or make it longer')
step = None
if STEP_ON:
    st, _ = when(STEP_ON, lines[0]['t'])
    step = dict(frame=int(round(st * FPS)), peak=1.5, settle=1.15, tau=8.0)

f_first = lines[0]['f']
appear = [max(2, f_first - 20), max(2, f_first - 20) + 9]
if appear[1] > f_first:
    appear = [2, max(3, f_first)]
gone = [f_off + 7, f_off + 16] if f_off is not None else None
active = [appear[0], (gone[1] if gone else N - 1)]
if gone and gone[1] > N - 3:
    say(f'!! the sign is still fading at frame {gone[1]} of {N}: the last frame may not be plain')

# ---------------------------------------------------------------------------------------------------- read the clip (half size)
grays, alphas = [], []
for p, m in zip(reader('assets/aroll.mp4', W, H, scale=(HW_, HH_)),
                reader('assets/subject.webm', W, H, alpha=True, scale=(HW_, HH_))):
    grays.append(cv2.cvtColor(p, cv2.COLOR_RGB2GRAY))
    alphas.append(m)
if len(alphas) != N:
    say(f'!! the cutout has {len(alphas)} frames, the slot {N}: remake it (fx_new.py)')
    n = min(len(alphas), len(grays))
    grays, alphas = grays[:n], alphas[:n]
    grays += [grays[-1]] * (N - n)
    alphas += [alphas[-1]] * (N - n)


# ---------------------------------------------------------------------------------------------------- camera track
def track():
    """Camera motion of the room, frame to frame: corners on the background (speaker masked out), Lucas-Kanade, a
    RANSAC similarity (shift + roll + scale: a selfie phone moves in and out), chained from frame 0. Matrices map
    frame-0 px to frame-f px at full size. A still camera comes out as identity (no jitter)."""
    acc, fails = np.eye(3), 0
    par = [(0.0, 0.0, 0.0, 0.0)]
    for f in range(1, N):
        bg = (cv2.dilate((alphas[f - 1] > 10).astype(np.uint8), ell(21)) == 0).astype(np.uint8) * 255
        bg[:8], bg[-8:], bg[:, :8], bg[:, -8:] = 0, 0, 0, 0
        pts = cv2.goodFeaturesToTrack(grays[f - 1], 500, 0.01, 7, mask=bg)
        T = None
        if pts is not None and len(pts) >= 12:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(grays[f - 1], grays[f], pts, None, winSize=(21, 21), maxLevel=3)
            ok = st[:, 0] == 1
            if ok.sum() >= 10:
                m, inl = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=1.0)
                if m is not None and inl is not None and inl.sum() >= 8:
                    T = np.vstack([m, [0, 0, 1]]).astype(np.float64)
        if T is None:
            fails += 1
            T = np.eye(3)
        acc = T @ acc
        a_, b_ = acc[0, 0], acc[1, 0]
        par.append((float(acc[0, 2]), float(acc[1, 2]), float(np.arctan2(b_, a_)), float(np.log(np.hypot(a_, b_)))))
    par = np.array(par)
    move = float(np.abs(par[:, :2]).max() * Q + np.abs(np.expm1(par[:, 3])).max() * 960)
    if move < 1.5:                              # tracker noise on a locked-off camera: keep it perfectly still
        par[:] = 0.0
    else:
        k = np.exp(-0.5 * (np.arange(-3, 4) / 1.2) ** 2)
        k /= k.sum()
        pad = np.pad(par, ((3, 3), (0, 0)), mode='edge')
        par = np.stack([np.convolve(pad[:, i], k, mode='valid') for i in range(4)], 1)
    S = np.float64([[Q, 0, 0.5 * (Q - 1)], [0, Q, 0.5 * (Q - 1)], [0, 0, 1]])
    out = []
    for tx, ty, th, ls in par:
        s = np.exp(ls)
        Mh = np.float64([[s * np.cos(th), -s * np.sin(th), tx], [s * np.sin(th), s * np.cos(th), ty], [0, 0, 1]])
        out.append(S @ Mh @ np.linalg.inv(S))
    return out, move, fails


TRACK, move, fails = track()
cam = 'still' if move < 1.5 else ('drifting' if move < 60 else 'moving')
say(f'camera: {cam} (room moves up to {move:.1f}px{", " + str(fails) + " frames held" if fails else ""})')
if cam == 'moving':
    say('!! the camera moves a lot: the sign rides the track of the room, check it stays stuck to the wall')

# ---------------------------------------------------------------------------------------------------- where the speaker is
occ = np.zeros((HH_, HW_), np.float32)          # anywhere the speaker reaches (max over the sign's span)
frac = np.zeros((HH_, HW_), np.float32)         # share of the span the speaker covers each pixel
headm = np.zeros((HH_, HW_), np.uint8)          # where the head goes
heads = []
Sh = np.float64([[1 / Q, 0, 0], [0, 1 / Q, 0], [0, 0, 1]])


def head_of(m):
    """half-size mask -> (top, cx, width) in full px, or None when nobody is in the frame."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 60.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    for _ in range(6):                    # fixed point: width of the head half a head below its top
        r = min(m.shape[0] - 1, int(top + 0.6 * hw))
        xs = np.where(m[r, int(max(0, cx - 1.3 * hw)):int(cx + 1.3 * hw) + 1])[0]
        if not len(xs):
            break
        x0 = int(max(0, cx - 1.3 * hw))
        cx = x0 + (xs[0] + xs[-1]) / 2.0
        hw = max(12.0, float(xs[-1] - xs[0] + 1))
    return top * Q, cx * Q, hw * Q


for f in range(active[0], active[1] + 1):
    Mh = Sh @ TRACK[f] @ np.linalg.inv(Sh)
    a0 = cv2.warpAffine(alphas[f], Mh[:2], (HW_, HH_), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
    occ = np.maximum(occ, a0.astype(np.float32) / 255.0)
    frac += (a0 > 128)
    h = head_of(alphas[f] > 128)
    if h:
        heads.append(h + (f,))
frac /= max(1, active[1] - active[0] + 1)
if len(heads) < 0.5 * (active[1] - active[0] + 1):
    sys.exit('NEON SIGN DECLINES: the cutout finds nobody in most of the frames (it needs the speaker in the shot)')
wmed = float(np.median([h[2] for h in heads]))
for top_, cx_, w_, f in heads:                  # every head position, in frame-0 space (an arm beside the head can
    w_ = min(w_, 1.3 * wmed)                    # make one frame's width read wide: capped at 1.3 x the median)
    Mi = np.linalg.inv(Sh @ TRACK[f] @ np.linalg.inv(Sh))
    sc = float(np.sqrt(abs(np.linalg.det(Mi[:2, :2]))))
    c0 = cv2.perspectiveTransform(np.float64([[(cx_ / Q, top_ / Q)]]), Mi)[0, 0]
    w0 = w_ / Q * sc
    cv2.rectangle(headm, (int(c0[0] - 0.7 * w0), int(c0[1] - 4)), (int(c0[0] + 0.7 * w0), int(c0[1] + 1.5 * w0)), 1, -1)
# hands may cross a sign on the wall now and then (it is behind the speaker); the head and the body may not
occ_b = cv2.dilate(((frac > 0.25) | (headm > 0)).astype(np.uint8), ell(2 * int(18 / Q) + 1)) > 0
ht = float(np.percentile([h[0] for h in heads], 5))
hcx = float(np.median([h[1] for h in heads]))
hw = float(np.median([h[2] for h in heads]))
face = (hcx - 0.62 * hw, ht, hcx + 0.62 * hw, ht + 1.4 * hw)
shot = 'tight' if hw > 330 else ('medium' if hw > 150 else 'wide')
say(f'speaker: {shot} shot, head top {ht:.0f}, head width {hw:.0f}, face centre x {hcx:.0f} '
    f'({"off-centre " + ("left" if hcx < 400 else "right") if abs(hcx - 540) > 140 else "centred"})')

# ---------------------------------------------------------------------------------------------------- the wall
f_ref = 0                                       # everything static lives in frame-0 coordinates (the track's origin)
plate_ref = next(reader('assets/aroll.mp4', W, H, first=f_ref, last=f_ref))
plate_h = cv2.resize(plate_ref, (HW_, HH_), interpolation=cv2.INTER_AREA)


def wall_map(plate_h, holes):
    """Where the plain wall is (0..1, half size): smooth and close to the room's main wall colour. Shelves, frames,
    windows, lamps, furniture and the floor come out as 'not wall'."""
    lab = cv2.cvtColor(plate_h, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255.0
    lab[..., 1:] -= 128
    L = cv2.GaussianBlur(lab[..., 0], (0, 0), 1.5)
    g = np.hypot(cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3))
    tex = cv2.GaussianBlur(g, (0, 0), 4.0)
    usable = ~holes
    if usable.sum() < 2000:
        return np.zeros((HH_, HW_), np.float32), tex
    t_tex = max(4.0, 2.2 * float(np.percentile(tex[usable], 25)))
    cand = (tex < t_tex) & usable
    yy, xx = np.mgrid[0:HH_, 0:HW_].astype(np.float32)
    xn, yn = xx / HW_ - .5, yy / HH_ - .5
    basis = np.stack([np.ones_like(xn), xn, yn, xn * xn, xn * yn, yn * yn], -1)
    idx = np.flatnonzero(cand.ravel())
    if len(idx) < 500:
        return np.zeros((HH_, HW_), np.float32), tex
    idx = idx[::max(1, len(idx) // 40000)]
    B = basis.reshape(-1, 6)[idx]
    Y = lab.reshape(-1, 3)[idx]
    keep = np.ones(len(idx), bool)
    med = 3.0
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(B[keep], Y[keep], rcond=None)
        r = np.sqrt(((B @ coef - Y) ** 2).sum(1))
        med = float(np.median(r[keep]))
        keep = r < max(3.5, 2.5 * med)
    model = (basis.reshape(-1, 6) @ coef).reshape(HH_, HW_, 3)
    dE = np.sqrt(((lab - model) ** 2).sum(-1))
    tol = max(8.0, 3.5 * med)
    wall = neon.sstep((tol - dE) / (tol * 0.5)) * neon.sstep((t_tex * 2.0 - tex) / t_tex)
    b = (wall > 0.5).astype(np.uint8)
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, ell(5))
    nl, lab_cc, stats, _ = cv2.connectedComponentsWithStats(b, 8)
    small = np.zeros(nl, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < 0.003 * HW_ * HH_
    small[1:] |= stats[1:, cv2.CC_STAT_TOP] > 0.62 * HH_        # a plain patch that starts low is floor, not wall
    b[small[lab_cc]] = 0
    b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, ell(7))
    return cv2.GaussianBlur(b.astype(np.float32), (0, 0), 0.8), tex


wallm, tex = wall_map(plate_h, occ_b)
luma_h = plate_h.astype(np.float32) @ np.float32([0.2126, 0.7152, 0.0722])
bright = cv2.morphologyEx((luma_h > 228).astype(np.uint8), cv2.MORPH_OPEN, ell(13))   # windows, lamps, blown
bright = cv2.dilate(bright, ell(9)) > 0                                                  # walls (not a white trim)
yy, xx = np.mgrid[0:HH_, 0:HW_] * Q
safe = (xx >= 35 + 14) & (xx <= 1045 - 14) & (yy >= 220 + 14) & (yy <= 1470 - 14) & ~((yy >= 1155 - 14) & (xx > 980 - 14))
if cam != 'still':                              # the sign rides the room: it must stay inside on every frame it shows
    s0 = safe.astype(np.uint8)
    for f in range(active[0], active[1] + 1, 3):
        Mh = Sh @ TRACK[f] @ np.linalg.inv(Sh)
        safe &= cv2.warpAffine(s0, Mh[:2], (HW_, HH_), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_NEAREST) > 0
usable = (wallm > 0.5) & ~bright
# thin things on the wall (a trim line, a switch, a cable) may sit behind the sign: close them over
usable = (cv2.morphologyEx(usable.astype(np.uint8), cv2.MORPH_CLOSE, ell(2 * int(30 / Q) + 1)) > 0)
usable &= ~occ_b & ~bright & safe
bg = ~(occ > 0.15)
room_l = float(np.median(luma_h[bg])) if bg.any() else 110.0
busy = float(np.mean(tex[bg] > 6.0)) if bg.any() else 0.0
say(f'room: brightness {room_l:.0f}, {"busy" if busy > 0.45 else "calm"} ({busy * 100:.0f}% textured), '
    f'{int(bright[bg].mean() * 100)}% window or lamp, open wall {usable.mean() * 100:.0f}% of the frame')

# ---------------------------------------------------------------------------------------------------- fonts + sign geometry
table = neon.font_table(os.path.join('assets', 'fonts'))
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
font = neon.pick_font(table, FONT, WEIGHT)
say(f'font: {FONT} {WEIGHT} ({os.path.basename(font[0])})')
F100 = neon.load_font(font, 400)


def ink_box(text):
    """ink bbox of a line at size 1 (x0, y0, x1, y1), baseline at y 0, left of the advance at x 0."""
    l, t, r, b = F100.getbbox(text, anchor='ls')
    return np.float64([l, t, r, b]) / 400.0


LAYOUT = dict(oneline=False, underline=True)     # the stacked sign first; one line (for a low strip of wall) after


def geometry(size, origin):
    """-> per line baseline origins, the underline points, and the glass bbox (frame px) for the sign at `size`."""
    boxes = [ink_box(ln['text']) for ln in lines]
    ox, oy = origin
    pos, y = [], oy
    widths = [b[2] - b[0] for b in boxes]
    xr = ox
    for i, b in enumerate(boxes):
        if LAYOUT['oneline']:                                   # every tube on one baseline, a word space apart
            pos.append((xr - b[0] * size, oy))
            xr += (b[2] - b[0] + 0.30) * size
            continue
        if i:
            pitch = max(0.68, -b[1] + 0.10) * size              # script ascenders interleave the line above's tails
            y += pitch
        if ALIGN == 'stagger':
            x = ox + 0.21 * size * i
        elif ALIGN == 'centre':
            x = ox + (max(widths) - widths[i]) / 2 * size
        else:
            x = ox
        pos.append((x - b[0] * size, y))
    th = np.radians(TILT)
    pts = []
    for (x, y), b in zip(pos, boxes):
        for cx, cy in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])):
            dx, dy = cx * size, cy * size
            pts.append((x + dx * np.cos(th) + dy * np.sin(th), y - dx * np.sin(th) + dy * np.cos(th)))
    ul = None
    if und and LAYOUT['underline']:
        x, y = pos[-1]
        b = boxes[-1]
        if LAYOUT['oneline']:                                   # under the whole line
            x, b = pos[0][0], np.float64([boxes[0][0], 0, (xr - 0.30 * size - pos[0][0]) / size, boxes[-1][3]])
        x0, x1 = x + (b[0] + 0.02) * size, x + b[2] * 0.98 * size
        y0 = y + 0.12 * size + max(b[3], 0) * size * 0.55
        rise = (x1 - x0) * np.tan(th) + 0.05 * size
        ul = [(x0 + (x1 - x0) * t, y0 - rise * t ** 1.6) for t in (0.0, 0.27, 0.62, 1.0)]
        pts += ul
    pts = np.float64(pts)
    r = max(4.5, 8.0 * size / REF) / 2 + 3
    return pos, ul, (pts[:, 0].min() - r, pts[:, 1].min() - r, pts[:, 0].max() + r, pts[:, 1].max() + r)


g0 = geometry(100.0, (0.0, 0.0))[2]
gw, gh = (g0[2] - g0[0]) / 100.0, (g0[3] - g0[1]) / 100.0           # glass size per px of letter size
gx, gy = g0[0] / 100.0, g0[1] / 100.0                                 # glass box offset from the origin, per px

# ---------------------------------------------------------------------------------------------------- placement
bad = (~usable).astype(np.int32)
ii = np.pad(bad.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
ifr = np.pad(frac.astype(np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def fits(size, pad):
    """all positions (half-size top-left of the glass box + pad) where the box is open wall that hands cross only
    briefly. -> box w, box h (full px), ok mask."""
    bw = int(np.ceil((gw * size + 2 * pad) / Q))
    bh = int(np.ceil((gh * size + 2 * pad) / Q))
    if bw >= HW_ or bh >= HH_:
        return None

    def win(t):
        return t[bh:, bw:] - t[:-bh, bw:] - t[bh:, :-bw] + t[:-bh, :-bw]
    ok = (win(ii) <= 0.004 * bw * bh) & (win(ifr) <= 0.04 * bw * bh)
    return bw * Q, bh * Q, ok


def best_place(kind, side=None, smin=56):
    pad = 18.0
    for size in np.arange(SIZE_MAX, smin - 1, -6.0):
        r = fits(size, pad)
        if r is None:
            continue
        bw, bh, ok = r
        ys, xs = np.nonzero(ok)
        if not len(xs):
            continue
        x0, y0 = xs * Q + pad, ys * Q + pad                              # glass box top-left, full px
        x1, y1 = x0 + gw * size, y0 + gh * size
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if kind == 'beside':
            sel_l = x1 <= face[0] - 30
            sel_r = x0 >= face[2] + 30
            sel = (sel_l if side == 'left' else sel_r if side == 'right' else sel_l | sel_r)
            sel &= (cy >= ht - 0.3 * hw) & (cy <= ht + 2.6 * hw)
            score = -np.abs(cy - (ht + 0.8 * hw)) - 0.6 * np.minimum(np.abs(x1 - face[0]), np.abs(x0 - face[2]))
        elif kind == 'above':
            sel = (y1 <= ht - 26) & (np.abs(cx - hcx) <= max(220.0, 0.35 * gw * size))
            score = -np.abs(cx - hcx) - 1.5 * np.abs(y1 - (ht - 40))
        else:                                                              # corner: any open patch high in the frame
            sel = y1 <= ht + 1.1 * hw
            score = -cy - 0.3 * np.minimum(np.abs(x1 - face[0]), np.abs(x0 - face[2]))
        if not sel.any():
            continue
        k = int(np.argmax(np.where(sel, score, -1e9)))
        return dict(size=float(size), box=(float(x0[k]), float(y0[k]), float(x1[k]), float(y1[k])),
                    side='left' if cx[k] < hcx else 'right')
    return None


def placement_sheet(box=None):
    """work/placement.jpg: open wall green, where the speaker goes red, too bright blue, the chosen glass box white."""
    os.makedirs('work', exist_ok=True)
    v = plate_h.astype(np.float32) * 0.55
    v[usable] = v[usable] * 0.6 + np.float32([0, 255, 90]) * 0.4
    v[occ_b] = v[occ_b] * 0.6 + np.float32([255, 40, 40]) * 0.4
    v[bright & ~occ_b] = v[bright & ~occ_b] * 0.6 + np.float32([60, 120, 255]) * 0.4
    v = np.clip(v, 0, 255).astype(np.uint8)
    cv2.rectangle(v, (35 // Q, 220 // Q), (1045 // Q, 1470 // Q), (255, 0, 255), 1)
    if box is not None:
        cv2.rectangle(v, (int(box[0] / Q), int(box[1] / Q)), (int(box[2] / Q), int(box[3] / Q)), (255, 255, 255), 2)
    cv2.imwrite('work/placement.jpg', v[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 85])


REL = float(np.clip(0.55 * hw, 64, 110))       # smallest letters that still read as a sign next to this head
MIN = dict(beside=REL, above=max(64.0, REL - 16), corner=60.0)
if isinstance(PLACE, (tuple, list)):
    x, y, s = PLACE
    choice = dict(kind='manual', size=float(s), origin=(float(x), float(y)))
    why = 'PLACE set in the CLIP block'
else:
    layouts = [dict(oneline=False, underline=True)]
    if len(lines) > 1:
        layouts.append(dict(oneline=True, underline=True))
    if und:
        layouts.append(dict(oneline=len(lines) > 1, underline=False))
    choice, need = None, None
    for lay in layouts:
        LAYOUT.update(lay)
        g0 = geometry(100.0, (0.0, 0.0))[2]
        gw, gh = (g0[2] - g0[0]) / 100.0, (g0[3] - g0[1]) / 100.0
        gx, gy = g0[0] / 100.0, g0[1] / 100.0
        need = (gw * MIN['corner'] + 36, gh * MIN['corner'] + 36)          # the smallest layout tried, at 64 px
        name = ('one line' if lay['oneline'] else 'stacked') + ('' if lay['underline'] or not und else ', no underline')
        cands = {k: best_place(k, SIDE if k == 'beside' and SIDE != 'auto' else None,
                               smin=56 if PLACE == k else MIN[k])
                 for k in (['beside', 'above', 'corner'] if PLACE == 'auto' else [PLACE])}
        for k, c in cands.items():
            say(f'  {name} {k:6s}: ' + (f'letters up to {c["size"]:.0f}px at x {c["box"][0]:.0f}..{c["box"][2]:.0f}, '
                                        f'y {c["box"][1]:.0f}..{c["box"][3]:.0f}' if c else 'no room'))
        b, a, c = cands.get('beside'), cands.get('above'), cands.get('corner')
        if PLACE != 'auto':
            if cands[PLACE]:
                choice, why = dict(cands[PLACE], kind=PLACE), 'forced by PLACE'
        elif b and (not a or b['size'] >= 0.75 * a['size']):
            choice, why = dict(b, kind='beside'), f'open wall {b["side"]} of the head'
        elif a:
            choice, why = dict(a, kind='above'), ('no open wall beside the head' if not b else
                                                  'more room above the head than beside it')
        elif c and (shot == 'tight' or not b):
            over = abs((c['box'][0] + c['box'][2]) / 2 - hcx) < 0.6 * hw
            choice, why = dict(c, kind='corner'), (f'{shot} shot: the only open wall is a '
                                                   f'{"strip above the head" if over else "top corner"}, smaller sign')
        if choice:
            if lay != layouts[0]:
                why += f'; set on {name} to fit the wall'
            break
    if not choice:
        placement_sheet()
        cause = []
        if shot == 'tight':
            cause.append('your head fills the top of the frame')
        if cam == 'moving':
            cause.append('the phone moves, so the wall slides past the safe area')
        if busy > 0.45:
            cause.append('the room behind you is busy (shelves, things on the wall)')
        sys.exit(f'NEON SIGN DECLINES: there is no open wall beside or above you for the sign'
                 + (f' ({"; ".join(cause)})' if cause else '')
                 + f'. Even a small one-line sign needs a patch of plain wall about {need[0]:.0f} x {need[1]:.0f} px '
                   'that your head never crosses. Use a wider or steadier take, shorter text, or another effect.')
    choice['origin'] = (choice['box'][0] - gx * choice['size'], choice['box'][1] - gy * choice['size'])
size = choice['size']
pos, ul, gbox = geometry(size, choice['origin'])
placement_sheet(gbox)
kk = size / REF
say(f'placement: {choice["kind"].upper()} ({why}). Letters {size:.0f}px, glass x {gbox[0]:.0f}..{gbox[2]:.0f}, '
    f'y {gbox[1]:.0f}..{gbox[3]:.0f}')
if gbox[0] < 35 or gbox[2] > 1045 or gbox[1] < 220 or gbox[3] > 1470:
    say('!! the glass reaches outside the safe zone: set PLACE by hand or shorten the text')

# ---------------------------------------------------------------------------------------------------- room light settings
if ROOM_DIM == 'auto':
    room_dim = 0.62 if room_l < 70 else (0.50 if room_l > 165 else 0.56)
else:
    room_dim = float(ROOM_DIM)
THROW_SAT = 1.5


def throw(rgb):
    """Same hue, more saturated: the colour of the light a tube of colour `rgb` puts on a white wall."""
    c = np.float64(rgb)
    hi, lo = c.max(), c.min()
    lo2 = hi * (1 - min((hi - lo) / max(hi, 1e-6) * THROW_SAT, 1.0))
    return [float(v) for v in (lo2 + (c - lo) / max(hi - lo, 1e-6) * (hi - lo2))]


PATTERNS = {'classic': [[0.55, 0.06, 0.0, 0.85, 0.28], [0.45, 0.0, 0.75, 0.12], [0.5, 0.0, 0.22, 0.9],
                        [0.4, 0.05, 0.7, 0.0, 0.5]],
            'soft': [[0.5, 0.15, 0.8], [0.45, 0.1, 0.85], [0.5, 0.2, 0.9], [0.5, 0.1, 0.8]]}
pats = PATTERNS.get(FLICKER, PATTERNS['classic'])
groups = []
for i, ln in enumerate(lines):
    groups.append(dict(kind='text', text=ln['text'], pos=list(pos[i]), f_strike=ln['f'], flicker=pats[i % len(pats)],
                       colour=list(ln['colour']), throw=throw(ln['colour'])))
if ul:
    groups.append(dict(kind='stroke', points=[list(p) for p in ul], f_strike=und['f'], flicker=pats[2],
                       colour=list(acc), throw=throw(acc)))

# ---------------------------------------------------------------------------------------------------- prep: glass + light maps
ART_RS = 3
diam = max(4.5, 8.0 * kk)
for g in groups:
    if g['kind'] == 'text':
        g['chains'] = neon.lettering(g['text'], font, size, tuple(g['pos']), TILT)
    else:
        g['chains'] = neon.stroke(g['points'])
allp = np.vstack([c['pts'] for g in groups for c in g['chains']] + ([np.float64(CABLE)] if CABLE else []))
m_art = 30 + diam
ART_EXTENT = (float(np.floor(allp[:, 0].min() - m_art)), float(np.floor(allp[:, 1].min() - m_art)),
              float(np.ceil(allp[:, 0].max() + m_art)), float(np.ceil(allp[:, 1].max() + m_art)))
tube = neon.Tube(groups, ART_EXTENT, ART_RS, diam, max(3.0, 5.0 * kk), max(50.0, 88.0 * kk), CABLE)
art_a, art_e = tube.layers()
SPILL_EXTENT, SPILL_RES = (-160.0, -160.0, 1240.0, 2080.0), 4.0
x0, y0, x1, y1 = SPILL_EXTENT
cw, ch = int((x1 - x0) / SPILL_RES), int((y1 - y0) / SPILL_RES)
to_canvas = np.float64([[1 / SPILL_RES, 0, -x0 / SPILL_RES - 0.5], [0, 1 / SPILL_RES, -y0 / SPILL_RES - 0.5], [0, 0, 1]])
occl = []
for poly_pts, depth in OCCLUDERS:
    om = np.zeros((ch, cw), np.float32)
    q = cv2.perspectiveTransform(np.float64([poly_pts]), to_canvas)
    cv2.fillPoly(om, [np.round(q[0] * 8).astype(np.int32)], 1.0, cv2.LINE_AA, shift=3)
    occl.append((om, float(depth)))
to_img = np.linalg.inv(to_canvas)


def img(m):
    return cv2.warpPerspective(m, to_img, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


wall_full = cv2.GaussianBlur(cv2.resize(wallm, (W, H), interpolation=cv2.INTER_LINEAR), (0, 0), 3.0)
G = len(groups)
SG = np.zeros((H, W, G), np.float32)
far_tot = np.zeros((H, W), np.float32)
cents = []
standoff = 26.0 * kk
for gi, g in enumerate(groups):
    pts = neon.sample_points(g['chains'], 9.0 * kk)
    S, S0 = neon.spill(pts, SPILL_EXTENT, SPILL_RES, max(standoff, 2.0 * SPILL_RES), occl, fill=0.06,
                       fill_radius=max(200.0, 320.0 * kk), wide=(125.0 * kk, 0.42))
    _, Sfar = neon.spill(pts, SPILL_EXTENT, SPILL_RES, 120.0 * kk, (), fill=0.04, fill_radius=max(200.0, 320.0 * kk))
    n = len(pts) / 110.0
    S, Sfar = img(S) * n, img(Sfar) * n
    cents.append(pts.mean(0).tolist())
    SG[..., gi] = (wall_full * S + (1 - wall_full) * 0.55 * Sfar) * SPILL
    far_tot += Sfar
foot = cv2.warpPerspective(tube.cover, tube.to_units(), (W, H), flags=cv2.INTER_LINEAR)
foot = cv2.GaussianBlur(foot, (0, 0), 20 * max(kk, 0.5))
foot /= max(float(foot.max()), 1e-6)
MS = np.dstack([np.zeros((H, W), np.float32), np.clip(far_tot / 2.0, 0, 1), foot]).astype(np.float32)
# the wall's colour where the sign hangs: unlit coated glass is opaque and takes the same light
bx0, by0, bx1, by1 = [int(round(v)) for v in gbox]
bx0, by0, bx1, by1 = max(0, bx0), max(0, by0), min(W, bx1), min(H, by1)
LUT = (np.arange(256, dtype=np.float32) / 255.0) ** 2.2
sel = cv2.resize(usable.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)[by0:by1, bx0:bx1] > 0
patch = LUT[plate_ref[by0:by1, bx0:bx1]]
wallcol = np.median(patch[sel], axis=0) if sel.sum() > 50 else np.median(patch.reshape(-1, 3), axis=0)
say(f'wall colour under the sign (linear) {np.round(wallcol, 3).tolist()}, room dim {room_dim:.2f}, '
    f'tube {diam:.1f}px')

os.makedirs('work', exist_ok=True)
np.savez('work/static.npz', art_a=art_a.astype(np.float16), art_e=art_e.astype(np.float16),
         SG=SG.astype(np.float16), MS=MS.astype(np.float16), wallcol=np.float32(wallcol))
dim_in = [f_first - 1, f_first + 25]
plan = dict(n=N, fps=FPS, groups=[{k: v for k, v in g.items() if k != 'chains'} for g in groups], cents=cents,
            art_to_img=tube.to_units().tolist(), track=[m.tolist() for m in TRACK], f_off=f_off, step=step,
            appear=appear, gone=gone, active=active, dim_in=dim_in,
            dim_out=[f_off, f_off + 12] if f_off is not None else None, room_dim=room_dim, spill_gain=3.0,
            rim=dict(tight=0.6, wide=1.9, reach=300.0 * max(kk, 0.6)), matte_pull=7,
            bloom=[(2.2 * max(kk, 0.6), 0.50), (7.0 * max(kk, 0.6), 0.42), (22.0 * max(kk, 0.6), 0.30),
                   (70.0 * max(kk, 0.6), 0.18)],
            placement=choice['kind'], size=size, glass_box=list(gbox), shot=shot, camera=cam)
json.dump(plan, open('work/plan.json', 'w'))
cv2.imwrite('work/art_gain.png', (np.clip(art_a[..., 0], 0, 1.2) / 1.2 * 255).astype(np.uint8))
for g in groups:
    say(f'tube "{g.get("text", "underline")}" strikes frame {g["f_strike"]} ({g["f_strike"] / FPS:.2f}s)')
for ln in lines:
    say(f'   "{ln["text"]}": {ln["how"]}')
if und:
    say(f'   underline: {und["how"]}')
say(f'timeline: unlit sign fades on {appear[0]}..{appear[1]}, room dims {dim_in[0]}..{dim_in[1]}, '
    + ('stays lit to the last frame (OUT = cut)' if f_off is None else
       f'switches off at {f_off}, gone by {gone[1]} (slot ends {N - 1})'))


# ---------------------------------------------------------------------------------------------------- sounds (synthesised, seeded)
def write_wav(path, x, sr):
    pcm = (np.clip(x, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.repeat(pcm, 2).tobytes())


def make_sfx():
    """A quiet electrical buzz on each strike and the switch-off, the transformer settling, one low thump on the
    step. Deterministic (seeded); written into assets_fx/. Returns [(path, start s, duration s)]."""
    sr = 48000
    os.makedirs('assets_fx', exist_ok=True)
    n = int(DUR * sr)
    t = np.arange(n) / sr
    env = np.zeros(n)
    for g in groups:
        for k, v in enumerate(g['flicker'] + [1.0]):
            a0 = int((g['f_strike'] + k) / FPS * sr)
            if a0 >= n:
                break
            if k < len(g['flicker']):
                env[a0:a0 + sr // FPS] = np.maximum(env[a0:a0 + sr // FPS], v)
            else:
                m = min(int(0.22 * sr), n - a0)
                env[a0:a0 + m] = np.maximum(env[a0:a0 + m], 0.75 * np.exp(-np.arange(m) / (0.06 * sr)))
    if f_off is not None:
        for k, v in enumerate([0.85, 0.20, 0.55, 0.0]):
            a0 = int((f_off + k) / FPS * sr)
            if a0 < n:
                env[a0:a0 + sr // FPS] = np.maximum(env[a0:a0 + sr // FPS], v * 0.8)
    ker = np.hanning(int(0.006 * sr))
    env = np.convolve(env, ker / ker.sum(), mode='same')
    buzz = sum(np.sin(2 * np.pi * 120 * h * t + h) / h ** 0.9 for h in range(1, 18))
    buzz *= 0.75 + 0.25 * np.sin(2 * np.pi * 60 * t)
    rng = np.random.default_rng(3)
    crack = np.convolve(rng.standard_normal(n), np.ones(12) / 12, mode='same') * 2.0     # dull hiss, nothing bright
    sig = (buzz / np.abs(buzz).max() + 0.25 * crack / np.abs(crack).max()) * env
    sig = sig / (np.abs(sig).max() + 1e-9) * 10 ** (BUZZ_DB / 20)
    out = []
    nz = np.flatnonzero(np.abs(sig) > 1e-5)
    if len(nz):
        a, b = max(0, nz[0] - 240), min(n, nz[-1] + 2400)
        write_wav('assets_fx/neon-buzz.wav', sig[a:b], sr)
        out.append(('assets_fx/neon-buzz.wav', a / sr, (b - a) / sr))
    if step:
        m = int(0.9 * sr)
        tt = np.arange(m) / sr
        th = np.sin(2 * np.pi * (48 + 22 * np.exp(-tt / 0.05)) * tt) * np.exp(-tt / 0.16) * np.minimum(tt / 0.012, 1)
        write_wav('assets_fx/neon-thump.wav', th * 10 ** (THUMP_DB / 20), sr)
        out.append(('assets_fx/neon-thump.wav', step['frame'] / FPS, min(0.9, DUR - step['frame'] / FPS)))
    return out


cues = []
if ENV_SFX:
    for k, (path, t0, d) in enumerate(make_sfx()):
        if d > 0.05:
            cues.append(f'  <audio id="sfx_{k}" src="{path}" data-start="{t0:.3f}" data-media-start="0" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + k}" data-volume="1"></audio>')

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
{nl.join(cues)}
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

fl = [g['f_strike'] for g in groups]
marks = sorted({0, appear[1], fl[0] + 2, max(fl) + 8, (step['frame'] + 4) if step else max(fl) + 30,
                (f_off + 2) if f_off is not None else N - 2, N - 1} & set(range(N)))
stills = [min(N - 1, max(fl) + 14), min(N - 1, max(fl) + 40), min(N - 1, fl[0] + 3)]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json, work/static.npz, index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches SFX={int(ENV_SFX)} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(f) for f in (appear[1], max(fl) + 10, (f_off or N - 2) + 1)) +
      ' -g  (preview), then bake.py')
