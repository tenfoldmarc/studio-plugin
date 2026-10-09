#!/usr/bin/env python3
"""chart-grow: a line chart draws on the wall BEHIND the speaker (between the plate and the cutout) and kicks up on
one spoken word. Shape only by default: no numbers, no labels, no title. See effect.md for the run order.

    python build.py        writes index.html     (SAFE=1 safe-zone guide, CAPTIONS=0 no tag word, SFX=0 no sounds)
Needs work/measure.json + work/measure.npz from measure.py.
"""
import colorsys
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
KICK = 'scale'            # the spoken word the line takes off on, as measure.py prints it. ('scale', 2) = the 2nd time. Or a frame number
KICK_LEAD = 2             # frames the kick starts BEFORE that word's measured start, so the line is already moving on the word
SHAPE = [.04, .09, .055, .12, .16, .56, 1.0]   # height of each point, 0 = floor, 1 = top. A shape, not data: flat with small wobbles, then the kick
KICK_FROM = 4             # index of the point the line kicks from; the points after it rise on the word (measure nothing, count in SHAPE)
FIGURES = None            # OFF. The speaker's OWN real numbers, one per point, e.g. [1200, 1310, 1280, 1400, 1520, 3900, 6100]: the line is then drawn to scale from zero. Never invent, estimate or round up
FIGURE_FMT = '{:,.0f}'    # how a figure reads on screen ('${:,.0f}', '{:.0f}%'); only used with FIGURES. Ask the speaker for the unit
FIGURE_AT = (0, -1)       # which points carry their figure (default: the first and the last, "from this to this"). Only with FIGURES
X_LABELS = None           # OFF. Real period names, one per point (['MON', 'TUE', ...]); only what the speaker says the points are
TAG = None                # OFF. One word the speaker SAYS, in a pill over the turn ('SCALE'). Never a result ("3X", "+200%"). CAPTIONS=0 drops it
SIT = 'auto'              # 'auto' (measured), 'behind' (full width, flat part runs behind the speaker), 'beside' (small chart on open wall), or (x0, y_top, x1, y_floor) in px
IN_FRAME = 3              # first frame anything shows. Frames before it are the untouched picture
OUT_FRAME = 'auto'        # frame by which everything is gone again ('auto' = 4 before the end). None = the slot ends on a cut and the chart holds
DRAW_START = 'auto'       # when the flat part starts drawing: 'auto' (0.4 s after IN_FRAME), a spoken word, or a frame number
ACCENT = '#FAE67A'        # colour of the kick. Any brand colour that is not orange and not grey
LINE = '#FFF8EF'          # colour of the flat part, grid and labels (a warm or cool off-white)
DIM = 'auto'              # how far the room falls back behind the chart, 0 to 0.7. 'auto' = from the measured wall brightness
LOCK = 'auto'             # 'auto' = glued to the wall when measure.py found camera movement, pinned on a still camera. 0 / 1 to force
PUNCH = 1.0               # push-in on the kick (1.04 = 4%). Off by default; it eases back out before OUT_FRAME
GRADE = 'none'            # CSS filter on plate + cutout ('saturate(.94) contrast(1.03)'). Off: the main reel grades
SFX_LEVEL = 1.0           # multiplies the effect's sounds (already 0.75x template volume). SFX=0 drops them
# ==== END CLIP ====

FPS = 30
FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
SLOT = os.path.basename(HERE)
INK = '#14161C'
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 35, 1045, 220, 1470      # right edge is 980 from y 1155 down
if not os.path.exists('work/measure.json'):
    sys.exit('run measure.py first (work/measure.json is missing)')
M = json.load(open('work/measure.json'))
NPZ = np.load('work/measure.npz')
MASKS = NPZ['masks']
NF = json.load(open('clip.json'))['frames']
assert NF == M['frames'] == len(MASKS), 'measure.py was run on a different cut: run it again'
DUR = NF / FPS
WARN = []
if os.environ.get('CAPTIONS') == '0':
    TAG = None
if FIGURES is not None:
    assert len(FIGURES) >= 3 and min(FIGURES) >= 0, 'FIGURES: at least 3 real numbers, none below zero'
    SHAPE = [v / max(FIGURES) for v in FIGURES]
N = len(SHAPE)
assert 1 <= KICK_FROM <= N - 2, 'KICK_FROM needs at least one point before it and one after it'
assert X_LABELS is None or len(X_LABELS) == N, 'X_LABELS: one per point'


def warn(s):
    WARN.append(s)


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def word_frame(spec, what):
    """a frame number, a spoken word, or (word, nth)"""
    if isinstance(spec, (int, float)):
        return int(spec)
    word, nth = (spec, 1) if isinstance(spec, str) else spec
    hits = [w for w in M['words'] if norm(w['text']) == norm(word)]
    if len(hits) < nth:
        sys.exit(f'{what}: "{word}" is not in words.json ({" ".join(w["text"] for w in M["words"])}). Use a frame number.')
    return hits[nth - 1]['frame']


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h, a):
    return 'rgba(%d,%d,%d,%s)' % (*rgb(h), a)


hh, ss, _ = colorsys.rgb_to_hsv(*[v / 255 for v in rgb(ACCENT)])
if 12 / 360 <= hh <= 45 / 360 and ss > .5:
    warn('ACCENT reads as orange: pick another colour')
if ss < .15:
    warn('ACCENT is grey / white: the kick will not stand out, and the look goes black and white')

WORD_F = word_frame(KICK, 'KICK')
KICK_F = max(IN_FRAME + 12, WORD_F - KICK_LEAD)
TK, KD = KICK_F / FPS, .44
T_IN = IN_FRAME / FPS
OUT_F = (NF - 4) if OUT_FRAME == 'auto' else OUT_FRAME
T_OUT = OUT_F / FPS if OUT_F is not None else None        # everything is at zero from this time on
T_FADE = (T_OUT - .30) if T_OUT else None
LAST_VIS = OUT_F if OUT_F is not None else NF
T_DRAW = T_IN + .40 if DRAW_START == 'auto' else word_frame(DRAW_START, 'DRAW_START') / FPS
T_DRAW_END = TK - .05
if T_DRAW_END - T_DRAW < .6:
    warn(f'only {T_DRAW_END - T_DRAW:.2f}s of flat line before the kick: start the slot earlier or the growth has nothing to grow from')
    T_DRAW = max(T_IN + .1, T_DRAW_END - .6)
if T_FADE is not None and T_FADE - (TK + KD) < 1.0:
    warn(f'the chart is only up {T_FADE - TK - KD:.2f}s after it lands: make the slot longer (1.5 s after the kick word)')

# ---------------------------------------------------------------------------------------- camera (ref = kick frame)
_tr = np.array(M['track'])
_c = _tr[:, 0] + 1j * _tr[:, 1]
_t = _tr[:, 2] + 1j * _tr[:, 3]
LOCKED = (not M['still']) if LOCK == 'auto' else bool(LOCK)
_cr = _c / _c[KICK_F] if LOCKED else np.ones(NF, complex)
_trl = (_t - _cr * _t[KICK_F]) if LOCKED else np.zeros(NF, complex)
CAM = [[float(_trl[f].real), float(_trl[f].imag), float(abs(_cr[f])), float(math.degrees(math.atan2(_cr[f].imag, _cr[f].real)))]
       for f in range(NF)]
VIS = range(IN_FRAME, LAST_VIS)
DRIFT = max(abs(_cr[f] * (540 + 700j) + _trl[f] - (540 + 700j)) for f in VIS)      # how far the wall moves on screen while the chart is up


def stage_scale(t):
    if PUNCH == 1 or t <= TK:
        return 1.0
    z = 1 + (PUNCH - 1) * (1 - 2 ** (-10 * min(1.0, (t - TK) / .55)))
    if T_FADE is not None and t > T_FADE:
        u = min(1.0, (t - T_FADE) / .28)
        z = 1 + (z - 1) * (1 - u * u * (3 - 2 * u))
    return z


def to_screen(px, py, f):
    """chart point (px of the kick frame) -> where it is on screen in frame f"""
    q = _cr[f] * complex(px, py) + _trl[f]
    z = stage_scale(f / FPS)
    return 540 + (q.real - 540) * z, 700 + (q.imag - 700) * z


# ---------------------------------------------------------------------------------------- where the chart goes
_DIST = {}


def dist_map(f):
    if f not in _DIST:
        _DIST[f] = ndimage.distance_transform_edt(~MASKS[f]) * 8
    return _DIST[f]


def clearance(pts, frames):
    """smallest distance in px between the speaker and any of the chart points, over the given frames"""
    worst = 1e9
    for f in frames:
        d = dist_map(f)
        for x, y in pts:
            sx, sy = to_screen(x, y, f)
            worst = min(worst, d[min(239, max(0, int(sy / 8))), min(134, max(0, int(sx / 8)))])
    return worst


def points_for(x0, y_top, x1, y_floor):
    return [(x0 + (x1 - x0) * i / (N - 1), y_floor - SHAPE[i] * (y_floor - y_top)) for i in range(N)]


def dense(pts, step=14):
    out = []
    for a, b in zip(pts, pts[1:]):
        k = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
        out += [(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k) for i in range(k)]
    return out + [pts[-1]]


HEAD_ROOM = (64 if X_LABELS else 0) + (70 if FIGURES else 0)       # labels sit above the top of the line
PAD = 58 + min(120, DRIFT)                                         # room for the end dot + how far the wall drifts
KWIN = list(range(KICK_F, LAST_VIS, 2))                            # frames the kick is on screen


def sit_behind():
    x0, x1, y_top = SAFE_L + PAD, SAFE_R - PAD - 6, SAFE_T + PAD + HEAD_ROOM
    hi = min(y_top + .55 * (x1 - x0), SAFE_B - 60)
    for turn, line, low in ((62, 40, 300), (34, 26, 220)):          # first try to keep the turn's ring whole, then settle for tight
        y = hi
        while y >= y_top + low:
            p = points_for(x0, y_top, x1, y)
            if clearance([p[-1]], KWIN) >= 70 and clearance([p[KICK_FROM]], KWIN) >= turn and clearance(dense(p[KICK_FROM:]), KWIN) >= line:
                return (x0, y_top, x1, y)
            y -= 8
    return None


def sit_beside():
    """biggest patch of wall the speaker never enters, inside the safe zone"""
    union = MASKS[IN_FRAME:LAST_VIS].any(axis=0)
    free = ndimage.distance_transform_edt(~union) * 8 >= 30 + min(120, DRIFT)
    yy, xx = np.mgrid[0:240, 0:135] * 8 + 4
    free &= (xx >= SAFE_L) & (yy >= SAFE_T) & (yy <= SAFE_B) & (xx <= np.where(yy >= 1155, 980, SAFE_R))
    best, hts = (0, None), np.zeros(135, int)
    for i in range(240):
        hts = np.where(free[i], hts + 1, 0)
        stack = []
        for j in range(136):
            h = hts[j] if j < 135 else 0
            start = j
            while stack and stack[-1][1] >= h:
                start, sh = stack.pop()
                w_px, h_px = (j - start) * 8, sh * 8
                score = min(w_px, 1.9 * h_px) * min(h_px, .9 * w_px)
                if score > best[0]:
                    best = (score, (start * 8, (i - sh + 1) * 8, j * 8, (i + 1) * 8))
            stack.append((start, h))
    if best[1] is None:
        return None, (0, 0)
    L, T, R_, B = best[1]
    w, h = min(R_ - L, 1.9 * (B - T)), min(B - T, .9 * (R_ - L))
    cx = (L + R_) / 2
    box = (cx - w / 2 + 44, T + 52 + HEAD_ROOM, cx + w / 2 - 52, T + h - 26)
    return (box if box[2] - box[0] >= 240 and box[3] - box[1] >= 200 else None), (R_ - L, B - T)


if isinstance(SIT, (tuple, list)):
    BOX, MODE = tuple(SIT), 'by hand'
else:
    BOX = sit_behind() if SIT in ('auto', 'behind') else None
    MODE = 'behind'
    if BOX is None and SIT in ('auto', 'beside'):
        BOX, patch = sit_beside()
        MODE = 'beside'
        if BOX is None:
            sys.exit(f'NO OPEN WALL: the biggest patch the speaker never enters is {patch[0]:.0f} x {patch[1]:.0f} px (need about '
                     '330 x 280). Chart Grow needs a medium or wide shot with wall beside or above the head. Leave the effect '
                     'out of this clip, or give SIT = (x0, y_top, x1, y_floor) by hand and accept that the speaker hides part of the line.')
    if BOX is None:
        sys.exit("SIT = 'behind' does not fit: the end of the line would land on the speaker. Use 'auto' or 'beside'.")
X0, Y_TOP, X1, Y_FLOOR = BOX
POINTS = points_for(*BOX)
flat = [SHAPE[i] for i in range(KICK_FROM + 1)]
if 1 - SHAPE[KICK_FROM] < 2.5 * (max(flat) - min(flat)):
    warn('the kick is under 2.5x the wobble before it: it will read as "flat" on a phone. Flatten the start of SHAPE'
         + (' (FIGURES decide the shape: if the real numbers do not kick, this is the wrong effect for them)' if FIGURES else ''))
if SHAPE[-1] < max(SHAPE):
    warn('the last point is not the highest: the chart ends on a dip')
BEHIND = MODE != 'beside'
GRID_TOP = Y_TOP - 34 - (70 if FIGURES else 0)        # with figures the grid opens above the end point's number
GRID_BOT = Y_FLOOR if (FIGURES or not BEHIND) else min(Y_FLOOR + .8 * (Y_FLOOR - Y_TOP), SAFE_B - 20)
_u = MASKS[IN_FRAME:LAST_VIS].any(axis=0)
_box = np.zeros_like(_u)
_box[int(GRID_TOP / 8):int(GRID_BOT / 8), int(SAFE_L / 8):int(SAFE_R / 8)] = True
WALL = float(NPZ['luma'][_box & ~_u].mean()) / 255 if (_box & ~_u).any() else .5
DIM_V = round(min(.68, max(.38, .30 + .45 * WALL)), 2) if DIM == 'auto' else float(DIM)
sc_k = min(1.0, (X1 - X0) / 800)                       # small charts get thinner strokes and smaller dots
LINE_W, KICK_W = round(10 * max(.7, sc_k), 1), round(11 * max(.7, sc_k), 1)
TICK_PX, TAG_PX, FIG_PX = 38, 52, 46


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


# ---------------------------------------------------------------------------------------- line geometry
def seg(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def rounded(pts, r=16, steps=7):
    """polyline with rounded corners as a dense point list, + running length, + the length at every original point"""
    out, vidx = [pts[0]], []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ra, rc = min(r, seg(a, b) / 2.2), min(r, seg(b, c) / 2.2)
        p0 = (b[0] + (a[0] - b[0]) * ra / seg(a, b), b[1] + (a[1] - b[1]) * ra / seg(a, b))
        p2 = (b[0] + (c[0] - b[0]) * rc / seg(b, c), b[1] + (c[1] - b[1]) * rc / seg(b, c))
        out.append(p0)
        for k in range(1, steps + 1):
            u = k / steps
            out.append(((1 - u) ** 2 * p0[0] + 2 * u * (1 - u) * b[0] + u * u * p2[0],
                        (1 - u) ** 2 * p0[1] + 2 * u * (1 - u) * b[1] + u * u * p2[1]))
            if k == (steps + 1) // 2:
                vidx.append(len(out) - 1)
    out.append(pts[-1])
    cum = [0.0]
    for i in range(1, len(out)):
        cum.append(cum[-1] + seg(out[i - 1], out[i]))
    return out, cum, [0.0] + [cum[i] for i in vidx] + [cum[-1]]


def at_len(dn, cum, L):
    L = max(0.0, min(cum[-1], L))
    for i in range(1, len(cum)):
        if cum[i] >= L:
            u = 0 if cum[i] == cum[i - 1] else (L - cum[i - 1]) / (cum[i] - cum[i - 1])
            return dn[i - 1][0] + (dn[i][0] - dn[i - 1][0]) * u, dn[i - 1][1] + (dn[i][1] - dn[i - 1][1]) * u
    return dn[-1]


def path_d(dn):
    return 'M' + ' L'.join(f'{x:.1f} {y:.1f}' for x, y in dn)


def chart():
    """html + tweens for the chart, in px of the kick frame. Motion is worked out per frame here and played back as
    linear keyframes (perFrame), so the line head is exact on every frame."""
    pts, mi = POINTS, KICK_FROM
    base, bcum, bvl = rounded(pts[:mi + 1])
    kick, kcum, kvl = rounded(pts[mi:])
    LB, LK = bcum[-1], kcum[-1]
    arrive = [T_DRAW + (T_DRAW_END - T_DRAW) * i / mi for i in range(mi + 1)]
    for j in range(1, N - mi):                         # when the kick passes each later point (ease inverted)
        arrive.append(TK + KD * (1 - (1 - min(.97, kvl[j] / LK)) ** .25))

    def base_len(t):
        if t <= arrive[0]:
            return 0.0
        for i in range(1, mi + 1):
            if t <= arrive[i]:
                u = (t - arrive[i - 1]) / (arrive[i] - arrive[i - 1])
                return bvl[i - 1] + (bvl[i] - bvl[i - 1]) * (.4 * u + .6 * u * u * (3 - 2 * u))
        return LB

    rows = []                                          # per frame: flat dash offset, kick dash offset, head x, head y, fill clip
    for f in range(NF):
        t = f / FPS
        lb, lk = base_len(t), LK * (1 - (1 - max(0.0, min(1.0, (t - TK) / KD))) ** 4)
        hx, hy = at_len(kick, kcum, lk) if lk > 0 else at_len(base, bcum, lb)
        rows.append([round(LB + 4 - lb, 2), round(LK + 4 - lk, 2), round(hx, 2), round(hy, 2), round(1080 - hx, 2)])

    xs = [p[0] for p in pts]
    step = xs[1] - xs[0]
    top, bot = GRID_TOP, GRID_BOT
    h, tw, texts = [], [], []
    t_grid = T_IN + .03
    for k in range(5):                                 # grid: horizontals, then a column per point
        y = top + (bot - top) * k / 4
        left, width = (-400, 1900) if BEHIND else (X0 - 40, X1 - X0 + 80)
        h.append(f'<div class="gh{" base" if k == 4 else ""}" id="gh{k}" style="top:{y - 1:.1f}px;left:{left:.0f}px;width:{width:.0f}px"></div>')
        tw += [f"gsap.set('#gh{k}',{{scaleX:0,autoAlpha:0}});",
               f"tl.to('#gh{k}',{{scaleX:1,autoAlpha:1,duration:.6,ease:'expo.out'}},{t_grid + k * .04:.3f});"]
    cols = list(enumerate(xs)) + ([(-1, xs[0] - step), (N, xs[-1] + step)] if BEHIND else [])
    for i, x in cols:
        cid = f'gv{i}'.replace('-', 'm')
        tcol = T_IN + .10 + .30 * min(max(i, 0), N - 1) / (N - 1)
        out = i < 0 or i >= N
        h.append(f'<div class="gv{" out" if out else ""}" id="{cid}" style="left:{x - 1:.1f}px;top:{top}px;height:{bot - top}px"></div>')
        tw += [f"gsap.set('#{cid}',{{scaleY:0,autoAlpha:0}});",
               f"tl.to('#{cid}',{{scaleY:1,autoAlpha:1,duration:.55,ease:'expo.out'}},{tcol:.3f});"]
        if out or not X_LABELS:
            continue
        ly = top - 36
        h.append(f'<div class="lab" id="lab{i}" style="left:{x - 80:.1f}px;top:{ly - 30:.1f}px">{X_LABELS[i]}</div>')
        tw += [f"gsap.set('#lab{i}',{{autoAlpha:0,y:14,scale:.7}});",
               f"tl.to('#lab{i}',{{autoAlpha:.7,y:0,scale:1,duration:.3,ease:'back.out(2.2)'}},{tcol:.3f});"]
        texts.append((f'lab{i}', x, ly, TICK_PX * .7 * len(str(X_LABELS[i])), TICK_PX * 1.1, tcol))

    def curtain(dn, colour, peak, depth, bands=48):
        """fill = a light curtain hanging from the line: stacked see-through copies, so the fade follows the line"""
        o = []
        for b in range(bands):
            d = depth * ((b + 1) / bands) ** 1.5
            p_ = ' '.join(f'{x:.1f},{y:.1f}' for x, y in dn) + ' ' + ' '.join(f'{x:.1f},{min(bot, y + d):.1f}' for x, y in reversed(dn))
            o.append(f'<polygon points="{p_}" fill="{colour}" fill-opacity="{peak / bands * 1.9 * (1 - b / bands):.4f}"/>')
        return ''.join(o)

    rise = Y_FLOOR - Y_TOP
    # playhead: a cursor riding the head of the line, so the sweep still reads while the line is behind the speaker
    h.append(f'<div id="cursor" style="top:{top}px;height:{bot - top}px"><div id="cursorl"></div><div id="cursord"></div></div>')
    tw += ["gsap.set('#cursor',{autoAlpha:0});",
           f"tl.to('#cursor',{{autoAlpha:1,duration:.3,ease:'power2.out'}},{T_DRAW:.3f});",
           f"tl.to('#cursor',{{autoAlpha:.45,duration:.5,ease:'power2.out'}},{TK + KD:.3f});",
           "perFrame('#cursor',r=>({x:r[2]}));"]
    h.append(f'<div id="areaw"><svg class="sv soft" viewBox="0 0 1080 1920">{curtain(base, LINE, .6, rise * 1.2)}'
             f'{curtain(kick, ACCENT, 1.15, rise * 1.8)}</svg></div>')
    h.append(f'<svg class="sv glow" viewBox="0 0 1080 1920"><path class="lb" d="{path_d(base)}" stroke="{LINE}" stroke-width="{LINE_W * 2}"/>'
             f'<path class="lk" d="{path_d(kick)}" stroke="{ACCENT}" stroke-width="{KICK_W * 2.6:.0f}"/></svg>')
    h.append(f'<svg class="sv" viewBox="0 0 1080 1920"><path class="lb" d="{path_d(base)}" stroke="{LINE}" stroke-width="{LINE_W}"/>'
             f'<path class="lk" d="{path_d(kick)}" stroke="{ACCENT}" stroke-width="{KICK_W}"/></svg>')
    tw += [f"gsap.set('.lb',{{strokeDasharray:{LB + 4:.2f},strokeDashoffset:{LB + 4:.2f},autoAlpha:0}});",
           f"gsap.set('.lk',{{strokeDasharray:{LK + 4:.2f},strokeDashoffset:{LK + 4:.2f},autoAlpha:0}});",
           f"tl.set('.lb',{{autoAlpha:1}},{F(round(T_DRAW * FPS) + 1):.3f});",
           f"tl.set('.lk',{{autoAlpha:1}},{F(KICK_F + 1):.3f});",
           "perFrame('.lb',r=>({strokeDashoffset:r[0]}));", "perFrame('.lk',r=>({strokeDashoffset:r[1]}));",
           "perFrame('#areaw',r=>({clipPath:'inset(0px '+r[4]+'px 0px 0px)'}));", "perFrame('#head',r=>({x:r[2],y:r[3]}));",
           f"tl.fromTo('.glow .lk',{{strokeWidth:{KICK_W * 5:.0f}}},{{strokeWidth:{KICK_W * 2.6:.0f},duration:.7,ease:'power2.out',immediateRender:false}},{TK:.3f});"]

    mx, my = pts[mi]
    h.append(f'<div id="mring" class="ring y" style="left:{mx:.1f}px;top:{my:.1f}px"></div>')
    tw += ["gsap.set('#mring',{autoAlpha:0,scale:2.2});",
           f"tl.to('#mring',{{autoAlpha:1,scale:1,duration:.3,ease:'power3.out'}},{TK:.3f});"]
    if TAG:                                            # the word the speaker says, in a pill over the turn, on a dashed marker
        tag_w, tag_h = round(TAG_PX * (.68 * len(TAG) + 1.9)), round(TAG_PX * 1.62)
        tx = min(max(mx - 40, SAFE_L + PAD + tag_w / 2), SAFE_R - PAD - tag_w / 2)
        ty = top + tag_h / 2 + 6
        m_top = ty + tag_h / 2 + 8
        h.append(f'<div id="mline" style="left:{mx - 2:.1f}px;top:{m_top:.1f}px;height:{max(0, my - m_top - 30):.1f}px"></div>')
        h.append(f'<div id="tagw" style="left:{tx:.1f}px;top:{ty:.1f}px"><div id="tag" style="left:{-tag_w / 2:.0f}px;top:{-tag_h / 2:.0f}px;'
                 f'width:{tag_w}px;height:{tag_h}px;border-radius:{tag_h / 2:.0f}px;font-size:{TAG_PX}px;line-height:{tag_h}px">'
                 f'<span>{TAG}</span><svg viewBox="0 0 24 24" width="{TAG_PX * .8:.0f}" height="{TAG_PX * .8:.0f}">'
                 f'<path d="M6 18 L18 6 M9 6 H18 V15" fill="none" stroke="{INK}" stroke-width="3.4" stroke-linecap="round" '
                 'stroke-linejoin="round"/></svg></div></div>')
        tw += ["gsap.set('#mline',{scaleY:0,autoAlpha:0});", "gsap.set('#tagw',{autoAlpha:0,scale:.5,y:14});",
               f"tl.to('#mline',{{scaleY:1,autoAlpha:1,duration:.22,ease:'power3.out'}},{TK:.3f});",
               f"tl.to('#tagw',{{autoAlpha:1,scale:1,y:0,duration:.4,ease:'back.out(2.4)'}},{TK + .02:.3f});"]
        texts.append(('tag', tx, ty, tag_w, tag_h, TK))
    if FIGURES:                                        # the speaker's own numbers, over the points that carry them
        for i in sorted({k % N for k in FIGURE_AT}):
            txt = FIGURE_FMT.format(FIGURES[i])
            w_ = FIG_PX * .62 * len(txt) + 10
            fx = min(max(pts[i][0], SAFE_L + PAD - 30 + w_ / 2), SAFE_R - PAD + 30 - w_ / 2)
            fy = pts[i][1] - 58
            h.append(f'<div class="fig{" y" if i >= mi else ""}" id="fig{i}" style="left:{fx - 200:.1f}px;top:{fy - 30:.1f}px">{txt}</div>')
            tw += [f"gsap.set('#fig{i}',{{autoAlpha:0,y:16,scale:.7}});",
                   f"tl.to('#fig{i}',{{autoAlpha:1,y:0,scale:1,duration:.34,ease:'back.out(2.2)'}},{arrive[i] + .04:.3f});"]
            texts.append((f'fig{i}', fx, fy, w_, FIG_PX * 1.15, arrive[i]))

    for i in range(N):                                 # a dot and one ring on every point as the line reaches it
        kc = i >= mi
        px, py = at_len(kick, kcum, kvl[i - mi]) if i > mi else at_len(base, bcum, bvl[i])
        if i < N - 1:
            h.append(f'<div class="vdot{" y" if kc else ""}" id="vd{i}" style="left:{px:.1f}px;top:{py:.1f}px"></div>')
            tw += [f"gsap.set('#vd{i}',{{scale:0,autoAlpha:0}});",
                   f"tl.to('#vd{i}',{{scale:1,autoAlpha:1,duration:.3,ease:'back.out(3)'}},{arrive[i]:.3f});"]
        big = 3.4 if i in (mi, N - 1) else 2.3
        h.append(f'<div class="ring{" y" if kc else ""}" id="vr{i}" style="left:{px:.1f}px;top:{py:.1f}px"></div>')
        tw += [f"gsap.set('#vr{i}',{{scale:.3,autoAlpha:0}});",
               f"tl.fromTo('#vr{i}',{{scale:.3,autoAlpha:.95}},{{scale:{big},autoAlpha:0,duration:{.75 if big > 3 else .6},ease:'power2.out',immediateRender:false}},{arrive[i]:.3f});"]
        if X_LABELS:
            tw += [f"tl.to('#lab{i}',{{autoAlpha:1,color:'{ACCENT if kc else LINE}',duration:.2,ease:'power2.out'}},{arrive[i]:.3f});"]

    # head of the line: glow + core + a dashed tracker running off to the right until the kick
    h.append('<div id="head"><div id="hpop"><div class="hglow"></div><div class="htrk"></div><div class="hcore"></div></div></div>')
    tw += ["gsap.set('#hpop',{scale:0,autoAlpha:0});",
           f"tl.to('#hpop',{{scale:1,autoAlpha:1,duration:.34,ease:'back.out(2.6)'}},{T_DRAW - .03:.3f});",
           f"tl.set('#head',{{'--c':'{ACCENT}'}},{F(KICK_F):.3f});",
           f"tl.to('#hpop',{{scale:1.9,duration:.12,ease:'power2.out'}},{TK:.3f});",
           f"tl.to('#hpop',{{scale:1.3,duration:.5,ease:'power3.out'}},{TK + .12:.3f});",
           f"tl.to('.htrk',{{autoAlpha:0,duration:.3}},{TK + .1:.3f});"]
    k, tp = 0, arrive[-1] + .42                        # the peak keeps breathing while the chart holds
    while tp < (T_FADE - .45 if T_FADE else DUR - .25):
        h.append(f'<div class="ring y" id="pr{k}" style="left:{pts[-1][0]:.1f}px;top:{pts[-1][1]:.1f}px"></div>')
        tw += [f"gsap.set('#pr{k}',{{scale:.3,autoAlpha:0}});",
               f"tl.fromTo('#pr{k}',{{scale:.3,autoAlpha:.8}},{{scale:1.9,autoAlpha:0,duration:.7,ease:'power2.out',immediateRender:false}},{tp:.3f});"]
        tp += .46
        k += 1
    texts.append(('end dot', pts[-1][0], pts[-1][1], 46, 46, TK))
    return h, tw, rows, texts, arrive


SOUNDS, GAP = [], []
UNDER_DB = 8             # the loudest effect sound sits this far under the speaker's loudest 0.1 s


def audio(t_land):
    if os.environ.get('SFX') == '0' or SFX_LEVEL <= 0:
        return []
    sfx = [('whoosh-short', T_IN, .20), ('pop', T_DRAW - .02, .13), ('impact-bass-1', TK - .02, .20),
           ('whoosh-short', TK - .06, .24), ('sparkle', t_land + .02, .13)]
    out, lanes, ln, lv = [], [], {}, {}
    for name in sorted({s[0] for s in sfx}):
        p = f'assets/sfx/{name}.mp3'
        if not os.path.exists(p):
            warn(f'stock sound {name}.mp3 is not in assets/sfx: left out')
            continue
        ln[name] = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                        capture_output=True, text=True).stdout)
        raw = subprocess.run([FF, '-v', 'error', '-i', p, '-ac', '1', '-ar', '48000', '-f', 's16le', '-'], capture_output=True).stdout
        x = np.frombuffer(raw[:len(raw) // 9600 * 9600], np.int16).astype(np.float32).reshape(-1, 4800) / 32768
        lv[name] = 10 * math.log10(float((x ** 2).mean(axis=1).max()) + 1e-12)                     # its loudest 0.1 s
    # the sounds follow the measured voice: the loudest one sits UNDER_DB under the speaker's loudest 0.1 s, never above its stock level
    top = max((lv[n_] + 20 * math.log10(v * .75) for n_, _, v in sfx if n_ in lv), default=-90)
    gain = min(1.0, 10 ** ((M.get('voice_db', -18) - UNDER_DB - top) / 20)) * SFX_LEVEL
    GAP.append(round(M.get('voice_db', -18) - top - 20 * math.log10(max(gain, 1e-6)), 1))
    print(f'sounds: their loudest word {M.get("voice_db", -18):.1f} dB, loudest effect sound {GAP[0]:.0f} dB under it (x{gain:.2f} of stock level)')
    for k, (name, t, vol) in enumerate(sorted((s for s in sfx if s[0] in ln), key=lambda s: s[1])):
        vol = vol * gain / SFX_LEVEL
        t = max(0.0, t)
        d = min(ln[name], DUR - t - .02)
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        SOUNDS.append([name, round(t, 3), round(vol * .75 * SFX_LEVEL, 3)])
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * .75 * SFX_LEVEL:.3f}"></audio>')
    return out


def css():
    grade = '' if GRADE in (None, '', 'none') else f'#bgv,#cut{{filter:{GRADE}}}'
    return f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0;transform-origin:50% 700px}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:0}}
#fx{{position:absolute;inset:0;z-index:2}}
#dim{{position:absolute;inset:0;background:radial-gradient(120% 80% at 50% 38%,rgba(16,18,26,{DIM_V * .86:.3f}) 0%,rgba(12,13,20,{min(.9, DIM_V * 1.22):.3f}) 100%)}}
#dim2{{position:absolute;inset:0;background:rgba(12,13,20,.16)}}
#world{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0}}
#cutwrap{{position:absolute;inset:0;z-index:4}}
{grade}
.sv{{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:visible}}
.sv path{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
.sv.glow{{filter:blur(13px);opacity:.7}}
#areaw{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.sv.soft{{filter:blur(5px)}}
#cursor{{position:absolute;left:0;width:0}}
#cursorl{{position:absolute;left:-1.5px;top:0;width:3px;height:100%;background:linear-gradient(180deg,{rgba(LINE, .85)} 0%,{rgba(LINE, .4)} 30%,{rgba(LINE, .08)} 100%)}}
#cursord{{position:absolute;left:-8px;top:-8px;width:16px;height:16px;background:{LINE};transform:rotate(45deg);box-shadow:0 0 14px {rgba(LINE, .7)}}}
.gh{{position:absolute;height:2px;background:{rgba(LINE, .15)};transform-origin:0 50%}}
.gh.base{{background:{rgba(LINE, .34)}}}
.gv{{position:absolute;width:2px;background:{rgba(LINE, .2)};transform-origin:50% 0}}
.gv.out{{background:{rgba(LINE, .1)}}}
.lab{{position:absolute;width:160px;height:60px;text-align:center;color:{LINE};font:600 {TICK_PX}px/60px Montserrat;text-shadow:0 2px 14px rgba(0,0,0,.6)}}
.fig{{position:absolute;width:400px;height:60px;text-align:center;color:{LINE};font:800 {FIG_PX}px/60px 'Inter Tight';text-shadow:0 2px 16px rgba(0,0,0,.7)}}
.fig.y{{color:{ACCENT}}}
.vdot{{position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;background:{INK};border:6px solid {LINE};box-shadow:0 0 16px {rgba(LINE, .5)}}}
.vdot.y{{border-color:{ACCENT};box-shadow:0 0 18px {rgba(ACCENT, .6)}}}
.ring{{position:absolute;width:60px;height:60px;margin:-30px 0 0 -30px;border-radius:50%;border:4px solid {LINE}}}
.ring.y{{border-color:{ACCENT}}}
#head{{position:absolute;left:0;top:0;width:0;height:0;--c:{LINE}}}
#hpop{{position:absolute;left:0;top:0;width:0;height:0}}
.hglow{{position:absolute;left:-100px;top:-100px;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle,var(--c) 0%,{rgba(ACCENT, .34)} 22%,{rgba(ACCENT, 0)} 68%);opacity:.8}}
.hcore{{position:absolute;left:-19px;top:-19px;width:38px;height:38px;border-radius:50%;background:#fff;border:7px solid var(--c);box-shadow:0 0 28px var(--c)}}
.htrk{{position:absolute;left:36px;top:-1.5px;width:{'1500' if BEHIND else f'{X1 - X0:.0f}'}px;height:3px;opacity:.5;background:repeating-linear-gradient(90deg,{LINE} 0 12px,rgba(0,0,0,0) 12px 26px)}}
#mline{{position:absolute;width:4px;transform-origin:50% 100%;background:repeating-linear-gradient(180deg,{ACCENT} 0 11px,rgba(0,0,0,0) 11px 22px)}}
#tagw{{position:absolute;width:0;height:0}}
#tag{{position:absolute;background:{ACCENT};color:{INK};display:flex;align-items:center;justify-content:center;gap:8px;font-family:'Inter Tight';font-weight:900;letter-spacing:.02em;box-shadow:0 12px 40px rgba(0,0,0,.42),0 0 54px {rgba(ACCENT, .45)}}}
#tag span{{display:block;padding-top:1px}}
'''


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def safe_report(texts):
    """every readable thing, every frame it is up: inside the safe zone once the camera track moves it?"""
    for name, cx, cy, w, hgt, ta in texts:
        lo, hi = [1e9, 1e9], [-1e9, -1e9]
        for f in range(int(ta * FPS), LAST_VIS):
            for dx, dy in ((-w / 2, -hgt / 2), (w / 2, -hgt / 2), (-w / 2, hgt / 2), (w / 2, hgt / 2)):
                sx, sy = to_screen(cx + dx, cy + dy, f)
                lo, hi = [min(lo[0], sx), min(lo[1], sy)], [max(hi[0], sx), max(hi[1], sy)]
        ok = lo[0] >= SAFE_L and hi[0] <= (980 if hi[1] >= 1155 else SAFE_R) and lo[1] >= SAFE_T and hi[1] <= SAFE_B
        gap = clearance([(cx - w / 2, cy), (cx + w / 2, cy), (cx, cy - hgt / 2), (cx, cy + hgt / 2)], range(int(ta * FPS), LAST_VIS, 2))
        print(f'  {name:8s} x {lo[0]:6.1f}..{hi[0]:6.1f}  y {lo[1]:6.1f}..{hi[1]:6.1f}  {"ok" if ok else "OUTSIDE SAFE ZONE"}'
              f'  {gap:4.0f} px from the speaker')
        if not ok:
            warn(f'{name} leaves the safe zone: set SIT by hand, further in')
        if gap < 20:
            warn(f'{name} goes behind the speaker (clear by {gap:.0f} px): move it with SIT or drop it')


def build():
    c_html, c_tw, rows, texts, arrive = chart()
    print(f'slot {SLOT}: {NF} frames. kick word starts frame {WORD_F}, kick starts frame {KICK_F} ({TK:.2f}s), lands {arrive[-1]:.2f}s; '
          f'in {IN_FRAME}, out {OUT_F if OUT_F is not None else "none (ends on a cut)"}')
    print(f'chart {MODE}: x {X0:.0f}..{X1:.0f}, top {Y_TOP:.0f}, floor {Y_FLOOR:.0f} (rise {Y_FLOOR - Y_TOP:.0f} px); kick clear of the '
          f'speaker by {clearance(dense(POINTS[KICK_FROM:]), KWIN):.0f} px; wall brightness {WALL:.2f} -> dim {DIM_V}; '
          f'{"glued to the wall (drift %.0f px)" % DRIFT if LOCKED else "pinned (still camera)"}')
    safe_report(texts)
    tw = ["gsap.set('#dim',{autoAlpha:0});", "gsap.set('#dim2',{autoAlpha:0});", "gsap.set('#cutwrap',{autoAlpha:0});",
          f"tl.set('#cutwrap',{{autoAlpha:1}},{F(IN_FRAME):.3f});",
          f"tl.to('#dim',{{autoAlpha:1,duration:.5,ease:'power2.out'}},{T_IN:.3f});",
          f"tl.to('#dim2',{{autoAlpha:1,duration:.3,ease:'power2.out'}},{TK:.3f});"]      # the room drops a touch more on the kick
    if LOCKED:
        tw.append("perFrameOf('#world',CAM,r=>({x:r[0],y:r[1],scale:r[2],rotation:r[3]}));")
    if PUNCH != 1:
        tw.append("perFrameOf('#stage',ZOOM,r=>({scale:r[0]}));")
    tw += c_tw
    if T_OUT is not None:
        tw += [f"tl.to('#fx',{{autoAlpha:0,duration:.27,ease:'power2.in'}},{T_FADE:.3f});",
               f"tl.set('#cutwrap',{{autoAlpha:0}},{F(OUT_F):.3f});"]
    zoom = [[round(stage_scale(f / FPS), 5)] for f in range(NF)]
    nl = '\n'
    html = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css()}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(arrive[-1]))}
  <div id="stage">
    <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
    <div id="fx">
      <div id="dim"></div>
      <div id="dim2"></div>
      <div id="world">
{nl.join(c_html)}
      </div>
    </div>
    <div id="cutwrap"><video id="cut" class="full" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="1"></video></div>
  </div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
const FR = 1 / {FPS};
const ROWS = {json.dumps(rows, separators=(',', ':'))};
const CAM = {json.dumps([[round(v, 4) for v in r] for r in CAM], separators=(',', ':')) if LOCKED else '[]'};
const ZOOM = {json.dumps(zoom, separators=(',', ':')) if PUNCH != 1 else '[]'};
// one linear keyframe per video frame: the motion is worked out in build.py, GSAP only plays it back
function perFrameOf(sel, rows, fn) {{
  gsap.set(sel, fn(rows[0]));
  tl.to(sel, {{ keyframes: rows.slice(1).map(r => Object.assign(fn(r), {{ duration: FR, ease: 'none' }})) }}, 0);
}}
function perFrame(sel, fn) {{ perFrameOf(sel, ROWS, fn); }}
{nl.join(tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(html)
    json.dump(dict(slot=SLOT, frames=NF, word_frame=WORD_F, kick_frame=KICK_F, land=round(arrive[-1], 3), in_frame=IN_FRAME,
                   out_frame=OUT_F, mode=MODE, box=[round(v, 1) for v in BOX], points=[[round(x, 1), round(y, 1)] for x, y in POINTS],
                   accent=ACCENT, locked=LOCKED, dim=DIM_V, sounds=SOUNDS, sound_gap_db=(GAP[0] if GAP else None), shape_only=not (FIGURES or X_LABELS or TAG), warnings=WARN),
              open('work/build.json', 'w'), indent=1)
    for w in WARN:
        print('!! ' + w)
    print(f'wrote index.html ({"SAFE GUIDE ON, not for the render" if os.environ.get("SAFE") else "clean"}); '
          f'on screen: {"shape only" if not (FIGURES or X_LABELS or TAG) else "shape + " + ", ".join(n for n, v in (("figures", FIGURES), ("x labels", X_LABELS), ("tag", TAG)) if v)}')


build()
