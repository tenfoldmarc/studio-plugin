#!/usr/bin/env python3
"""Freeze and Label. The picture freezes on a word while the voice runs on, the room softens and dims behind the
speaker, and label chips with leader lines point at spots on the frozen speaker. Then a hard cut back to live.

  0 -> freeze word      plain live picture
  freeze word           one frame is held: shutter flash, punch-in with a small overshoot, the room softens and dims
  each label            dot pops on its point -> line draws out of it -> chip unfolds from the line end -> words rise
  release word          chips whip off sideways, a short inhale, HARD CUT to live on the word with a cut punch + flash
  ... -> end            plain live picture again (or RELEASE = None: the slot ends on a cut, still frozen)

Run from the slot folder:  python build.py   (SAFE=1 guide, SFX=0 no sounds, GRADE=0 no freeze look, COLTEST=1 colour QA)
It measures the held frame (head, tie points, open space), bakes the frozen plates, lays the chips out and writes
index.html, work/freeze_pick.jpg (is the held frame a good one?) and work/layout.jpg (the label plan).
"""
import itertools
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import bake_freeze as bf
from bake_freeze import FPS, H, W, stop

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
FREEZE = ''          # spoken word the picture freezes on: 'word', 'word#2' (second time it is said) or a frame number. bake_freeze.py prints the words with their frames
HOLD = 'auto'        # the frame that is held: 'auto' = sharpest of the 6 frames from the freeze word on, or frames after it (0 to 5). Check the eyes in work/freeze_pick.jpg
RELEASE = ''         # word the live picture comes back on (hard cut + punch), or a frame number. None = stay frozen to the last frame: the slot then ENDS on a cut
LABELS = [           # (text, word it lands on, what it points at) + optional 'left' / 'right' to force the chip's side
    ('First label', '', 'head'),     # text = the speaker's own words, 1 to 3 words. word '' = one after the other from the freeze
    ('Second label', '', 'chest'),   # points at: head, cap, chest, shoulder, hand (or head_left, hand_right ... as seen on screen), or (fx, fy) = a spot as a fraction of the speaker's box
]
ZOOM = 1.12          # punch-in of the frozen picture, 1.0 = none. Wide shot: up to 1.2. Close shot: 1.0 to 1.06 (build.py prints the shot)
DRIFT = 0.03         # slow extra push during the hold so the still breathes. 0 = dead still
LOOK = 'subtle'      # the frozen room behind the speaker: 'subtle' (soft blur, light dim), 'strong', 'off'. Always in full colour
NUMBERS = True       # the small 01 / 02 tab on each chip. False = text only
ACCENT = '#FAE67A'   # dot centre and number tab: a brand colour, never orange
CHIP = '#FFF8EF'     # chip and line colour (light)
INK = '#14161C'      # text colour (dark)
HEAD = None          # only if build.py says it cannot find the head: (x0, y0, x1, y1) of the head, cap to chin, in px of work/hold.jpg
# ==== END CLIP ====


def on(name, default):
    v = os.environ.get(name)
    return default if v is None else v.lower() not in ('0', '', 'false', 'off', 'no')


SAFE, SFX_ON, COLTEST = on('SAFE', False), on('SFX', True), on('COLTEST', False)
on('CAPTIONS', True)                 # accepted, changes nothing: the effect has no caption words of its own
if not on('GRADE', True):
    LOOK = 'off'
if COLTEST:                          # QA build: the held frame at 1:1, untreated, no labels: compare its colour with live
    ZOOM, DRIFT, LOOK = 1.0, 0.0, 'off'
SL, SR, ST, SB, SR2, SY2 = 35, 1045, 220, 1470, 980, 1155      # Instagram safe zone (right edge is 980 below y 1155)
FLOOR = 0.70                         # smallest chip size that still reads on a phone (39 px text)
LEAD = 7                             # frames the dot starts before its word, so the chip is open and readable ON the word
WHIP_F = 5                           # frames each chip takes to fly off
PUNCH_F = 11                         # frames the cut punch on the live picture lasts after the release
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'click': .36}
SFX_GAIN = 0.75
C = 8                                # layout grid cell in px


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


# ---- the clip ----------------------------------------------------------------------------------------------------
CLIPJ = json.load(open('clip.json'))
N = int(CLIPJ['frames'])
DUR = N / FPS
SLOT = os.path.basename(HERE)
os.makedirs('work', exist_ok=True)
if not os.path.exists('assets/.cutout_done'):
    stop('the cutout is not finished (no assets/.cutout_done). This effect needs assets/subject.webm: wait for it, or run '
         '_shared/rvm_cut.py on the slot.')
if LOOK not in bf.LOOKS:
    stop(f"LOOK = '{LOOK}' is not one of: {', '.join(bf.LOOKS)}")
if not 1 <= len(LABELS) <= 4:
    stop('LABELS needs 1 to 4 entries.')
WORDS = bf.onsets()
word_list = ' '.join(f"{w['text']}({round(w['onset'] * FPS)})" for w in WORDS)
if FREEZE == '' or RELEASE == '':
    stop(f"fill FREEZE and RELEASE in the CLIP block (RELEASE = None to end frozen). Words (frame): {word_list}")
F_FRZ = bf.word_frame(FREEZE, WORDS, 'FREEZE')
F_REL = None if RELEASE is None else bf.word_frame(RELEASE, WORDS, 'RELEASE')
if F_FRZ < 3:
    stop(f'the freeze lands on frame {F_FRZ}: the slot has to start on at least 3 frames of plain live picture. Cut the slot earlier.')
if F_REL is not None and F_REL + PUNCH_F > N - 2:
    stop(f'the release lands on frame {F_REL} and the slot has {N} frames: the cut punch needs {PUNCH_F} frames and the slot must end '
         f'on plain live picture. Release on an earlier word (frame {N - 2 - PUNCH_F} or before), cut the slot longer, or RELEASE = None.')
F_END = N if F_REL is None else F_REL
TF, TU = F(F_FRZ), (None if F_REL is None else F(F_REL))

# ---- the held frame: which one, and where the speaker is on it ---------------------------------------------------
a0 = bf.alpha_of(F_FRZ)
m0 = bf.measure(a0, head=HEAD)
if m0['head'] is None:
    stop('cannot find the head outline on the freeze frame (hood, long hair over the neck, a hand on the head, or the head is not '
         'the top of the cutout). Type it in: HEAD = (x0, y0, x1, y1), cap to chin, read off work/hold.jpg.')
HOLD_F, WARN = bf.pick_hold(F_FRZ, F_END, m0['head'], HOLD)
ALPHA = a0 if HOLD_F == F_FRZ else bf.alpha_of(HOLD_F)
YUV = np.frombuffer(bf.grab(bf.AROLL, HOLD_F, HOLD_F, 'yuv444p')[0], np.uint8).reshape(3, H, W).astype(np.float32)
M = bf.measure(ALPHA, YUV, HEAD)
if M['head'] is None:
    stop(f'cannot find the head outline on held frame {HOLD_F}. Set HOLD to another frame or type HEAD = (x0, y0, x1, y1).')
hx0, hy0, hx1, hy1 = M['head']
HWP = M['hw']

# punch-in: scale about the upper chest; shifted down only if the head would leave the top of the safe zone
OX, OY = float(np.clip((hx0 + hx1) / 2, 0, W)), float(min(H, hy1 + .6 * HWP))
top_s = OY + (hy0 - OY) * ZOOM
DY = float(min(max(0.0, ST + 42 - top_s), OY * (ZOOM - 1)))
CX, CY = OX * (1 - ZOOM), OY * (1 - ZOOM) + DY
SO = (OX, OY + DY)                   # the zoom origin on screen: the drift scales about it
KD = 1 + DRIFT


def scr(p):
    """picture px -> screen px once the punch-in has settled"""
    return (p[0] * ZOOM + CX, p[1] * ZOOM + CY)


def drifted(p):
    return (SO[0] + (p[0] - SO[0]) * KD, SO[1] + (p[1] - SO[1]) * KD)


def in_safe(p, m=22):
    return all(SL + m <= q[0] <= (SR2 if q[1] > SY2 - m else SR) - m and ST + m <= q[1] <= SB - m for q in (p, drifted(p)))


HB = scr((hx0, hy0)) + scr((hx1, hy1))                # head box on screen
HWS, HHS, HCX = HB[2] - HB[0], HB[3] - HB[1], (HB[0] + HB[2]) / 2
SHOT = 'wide' if HWS < 230 else 'medium' if HWS < 400 else 'close'
MH = max(16.0, .12 * HWS)
HEADPAD = (HB[0] - MH, HB[1] - MH - 14, HB[2] + MH, HB[3] + MH)          # no chip here
FACE = (HB[0] - .3 * MH, HB[1] + .24 * HHS, HB[2] + .3 * MH, HB[3] + .5 * MH)   # no line through here (brows to chin)
ANCH = {k: scr(v) for k, v in M['anchors'].items()}
AFF = (1 / ZOOM, 0, -CX / ZOOM, 0, 1 / ZOOM, -CY / ZOOM)
OCC = np.asarray(Image.fromarray((M['mask'] * 255).astype(np.uint8)).transform((W, H), Image.AFFINE, AFF, Image.BILINEAR)
                 .resize((W // C, H // C), Image.BOX)) > 40

# ---- labels: timing and what each one points at ------------------------------------------------------------------
SIDED = {'head': ('head_left', 'head_right'), 'shoulder': ('shoulder_left', 'shoulder_right'), 'hand': ('hand_left', 'hand_right')}
free_l = int((~OCC)[ST // C:SB // C, SL // C:int(HCX) // C].sum())
free_r = int((~OCC)[ST // C:SB // C, int(HCX) // C:SR // C].sum())
LAB = []
gap = max(12, min(30, (F_END - F_FRZ - 34) // max(1, len(LABELS))))
for i, row in enumerate(LABELS):
    text, say, spec = row[0], row[1], row[2]
    side = row[3] if len(row) > 3 else 'auto'
    if chr(8212) in text:
        stop(f'label {i + 1}: no em dashes on screen.')
    if isinstance(spec, (tuple, list)):
        bx = M['box']
        p = scr((bx[0] + spec[0] * (bx[2] - bx[0]), bx[1] + spec[1] * (bx[3] - bx[1])))
        if FACE[0] < p[0] < FACE[2] and FACE[1] < p[1] < FACE[3]:
            stop(f"label '{text}': the point {tuple(spec)} is on the face. Move it (the face is never covered).")
        cands = [('point', p)]
    else:
        names = [n for n in SIDED.get(spec, (spec,)) if n in ANCH]
        if spec in SIDED and side in ('left', 'right'):          # a forced side takes the point on that side
            names = [n for n in names if n.endswith('_' + side)] or names
        elif spec in SIDED and free_r > free_l:
            names = names[::-1]
        cands = [(n, ANCH[n]) for n in names]
        if not cands:
            stop(f"label '{text}': '{spec}' was not found on the held frame. Found: {', '.join(sorted(ANCH))} (or use (fx, fy)).")
    ok = [c for c in cands if in_safe(c[1])]
    if not ok:
        usable = ', '.join(sorted(k for k, v in ANCH.items() if in_safe(v)))
        stop(f"label '{text}': '{spec}' is outside the safe zone on the held frame. Inside it: {usable or 'none (lower ZOOM)'}.")
    f_word = bf.word_frame(say, WORDS, f"label '{text}'") if say != '' else F_FRZ + LEAD + 1 + gap * i
    f_dot = max(F_FRZ + 1, f_word - LEAD)
    f_out = F_END - 1 - WHIP_F - (len(LABELS) - 1 - i)             # first label leaves first
    if F_REL is not None and f_dot + 20 > f_out:
        stop(f"label '{text}' starts at frame {f_dot} and has to leave at frame {f_out} (release at {F_REL}): it needs 20 frames to open "
             f"and be read. Land it on an earlier word or release later.")
    if f_dot + 10 > N:
        stop(f"label '{text}' starts at frame {f_dot}, the slot has {N} frames. Land it earlier.")
    LAB.append(dict(i=i, text=text, side=side, cands=ok, f_word=f_word, f_dot=f_dot, f_out=f_out))

# ---- layout: measured open space (the picture is frozen, so one frame is the whole story) ------------------------
_FONT = []


def text_w(t, px):
    if not _FONT:
        try:
            _FONT.append(ImageFont.truetype('assets/fonts/InterTight-800-normal.woff2', 200))
        except Exception:
            _FONT.append(None)
    if _FONT[0] is not None:
        w = _FONT[0].getlength(t) / 200
    else:                             # no woff2 support in this Pillow: estimate from character classes
        w = sum(.85 if ch in 'mwMW@' else .25 if ch in "iljtfI.,:;'!| " else .62 if ch.isupper() else .5 for ch in t) * 1.04
    return (w - .03 * len(t)) * px


def dims(L, k):
    """chip size at scale k. The width is an upper estimate (+5%): the real chip hugs its text and is pinned by the
    side its line meets, so the line end is exact whatever the browser makes of the font."""
    return math.ceil(((17 + 62 + 18 if NUMBERS else 30) + 30) * k + 1.05 * text_w(L['text'], 56 * k) + 6), round(96 * k)


def integral(m):
    return np.pad(np.asarray(m, np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def rsum(I, X, Y, w, h):
    c0, c1 = np.clip(X // C, 0, W // C).astype(int), np.clip(-(-(X + w) // C), 0, W // C).astype(int)
    r0, r1 = np.clip(Y // C, 0, H // C).astype(int), np.clip(-(-(Y + h) // C), 0, H // C).astype(int)
    return I[r1, c1] - I[r0, c1] - I[r1, c0] + I[r0, c0], np.maximum((r1 - r0) * (c1 - c0), 1)


def mark(m, x0, y0, x1, y1):
    m[max(0, int(y0 // C)):max(0, int(-(-y1 // C))), max(0, int(x0 // C)):max(0, int(-(-x1 // C)))] = True


headm, dotm = np.zeros((H // C, W // C), bool), np.zeros((H // C, W // C), bool)
mark(headm, *HEADPAD)
for L in LAB:
    for _, p in L['cands']:
        mark(dotm, p[0] - 30, p[1] - 30, p[0] + 30, p[1] + 30)
IH, ID, IO = integral(headm), integral(dotm), integral(OCC)
LMIN = max(70.0, .45 * HWS)
TARGET = float(np.clip(1.5 * HWS, 170, 380))
TT = np.linspace(0, 1, 25)


def in_box(xs, ys, b):
    return bool(((xs > b[0]) & (xs < b[2]) & (ys > b[1]) & (ys < b[3])).any())


def crosses(p1, p2, p3, p4):
    turn = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return turn(p1, p2, p3) * turn(p1, p2, p4) < 0 and turn(p3, p4, p1) * turn(p3, p4, p2) < 0


def line_ok(a, p, rect, placed):
    """the straight line dot -> chip never crosses the face, a chip or another line, and is not too short"""
    if math.hypot(p[0] - a[0], p[1] - a[1]) < LMIN:
        return False
    xs, ys = a[0] + (p[0] - a[0]) * TT, a[1] + (p[1] - a[1]) * TT
    x, y, w, h = rect
    if in_box(xs, ys, FACE) or in_box(xs, ys, (x + 6, y + 6, x + w - 6, y + h - 6)):
        return False
    for q in placed:
        ox, oy, ow, oh = q['rect']
        qx, qy = q['a'][0] + (q['port'][0] - q['a'][0]) * TT, q['a'][1] + (q['port'][1] - q['a'][1]) * TT
        if in_box(xs, ys, (ox - 8, oy - 8, ox + ow + 8, oy + oh + 8)) or in_box(qx, qy, (x - 8, y - 8, x + w + 8, y + h + 8)) \
                or crosses(a, p, q['a'], q['port']):
            return False
    return True


def ports(x, y, w, h, a, k):
    """where the line may meet the chip: the edge point nearest the dot first, then the corners and edge middles"""
    ins = min(40 * k, w / 2, h / 2)
    cx, cy = float(np.clip(a[0], x + ins, x + w - ins)), float(np.clip(a[1], y + ins, y + h - ins))
    near = min(((cx, y), (cx, y + h), (x, cy), (x + w, cy)), key=lambda q: math.hypot(q[0] - a[0], q[1] - a[1]))
    return [near] + [(x + ins + fx * (w - 2 * ins), y + fy * h) for fx, fy in ((0, 1), (1, 1), (0, 0), (1, 0), (.5, 1), (.5, 0))]


def place(k, tier, order):
    placed = []
    for i in order:
        L = LAB[i]
        w, h = dims(L, k)
        xs, ys = np.arange(SL + 10, SR - 10 - w + 1, 12), np.arange(ST + 14, SB - 14 - h + 1, 12)
        if not len(xs) or not len(ys):
            return None
        X, Y = np.meshgrid(xs, ys)
        x0d, x1d = SO[0] + (X - SO[0]) * KD, SO[0] + (X + w - SO[0]) * KD        # the chip rides the drift: check its end too
        y0d, y1d = SO[1] + (Y - SO[1]) * KD, SO[1] + (Y + h - SO[1]) * KD
        valid = (x0d >= SL) & (y0d >= ST) & (y1d <= SB) & (x1d <= np.where(y1d > SY2, SR2, SR)) & ~((Y + h > SY2) & (X + w > SR2))
        occ = rsum(IO, X, Y, w, h)
        occ = occ[0] / occ[1]
        valid &= (rsum(IH, X, Y, w, h)[0] == 0) & (rsum(ID, X, Y, w, h)[0] == 0) & (occ <= (.10 if tier == 1 else 1.0))
        g = 22 * k
        for q in placed:
            ox, oy, ow, oh = q['rect']
            valid &= ~((X < ox + ow + g) & (X + w > ox - g) & (Y < oy + oh + g) & (Y + h > oy - g))
        cx = X + w / 2
        if L['side'] in ('left', 'right'):
            valid &= (cx < HCX) == (L['side'] == 'left')
        nl = sum(1 for q in placed if q['rect'][0] + q['rect'][2] / 2 < HCX)
        Xr, Yr, got = X.ravel(), Y.ravel(), None
        for name, a in L['cands']:                               # best spot per tie point, then the cheaper of them
            v = valid
            if L['side'] == 'auto' and name.endswith(('_left', '_right')):
                v = v & ((cx < HCX) == name.endswith('_left'))   # a left point gets a chip on the left: no line over the head
            dist = np.hypot(np.maximum(np.maximum(X - a[0], a[0] - (X + w)), 0), np.maximum(np.maximum(Y - a[1], a[1] - (Y + h)), 0))
            cost = 900 * occ + .6 * np.abs(dist - TARGET) + 60 * np.where(cx < HCX, nl, len(placed) - nl) + .12 * np.maximum(0, Y + h / 2 - a[1])
            idx = np.flatnonzero(v & (dist >= LMIN))
            for j in idx[np.argsort(cost.ravel()[idx], kind='stable')][:1500]:
                rect = (int(Xr[j]), int(Yr[j]), w, h)
                port = next((p for p in ports(rect[0], rect[1], w, h, a, k) if line_ok(a, p, rect, placed)), None)
                if port:
                    if got is None or cost.ravel()[j] < got['cost']:
                        got = dict(L=L, rect=rect, port=port, a=a, name=name, cost=float(cost.ravel()[j]))
                    break
        if not got:
            return None
        placed.append(got)
    return placed


def layout(idx):
    w1 = max(dims(LAB[i], 1.0)[0] for i in idx)
    top = min(1.0, 600 / w1)                                    # no chip much wider than half the frame
    ks = sorted({round(max(FLOOR, min(top, v)), 2) for v in (1.0, .92, .84, .76, FLOOR)}, reverse=True)
    for tier in (1, 2):                                         # 1 = on clear background, 2 = may sit over the body (never the head)
        for k in ks:
            got = [g for g in (place(k, tier, order) for order in itertools.permutations(idx)) if g]
            if got:                                             # every order that fits: keep the cheapest plan
                return k, tier, min(got, key=lambda g: sum(q['cost'] for q in g))
    return None


res = layout(list(range(len(LAB))))
if res is None:
    fit = next((m for m in range(len(LAB) - 1, 0, -1) if layout(list(range(m)))), 0)
    stop(f"no room for {len(LAB)} labels on this frame at a readable size ({SHOT} shot, head {HWS:.0f} px wide after the punch-in): "
         + (f"{fit} fit. Drop a label, shorten the text, lower ZOOM or point at other spots." if fit else
            "not even one fits. Lower ZOOM to 1.0, or use another effect on this shot."))
K, TIER, PLACED = res
PLACED.sort(key=lambda q: q['L']['i'])

# ---- the frozen plates ---------------------------------------------------------------------------------------------
baked = bf.bake(HOLD_F, N, LOOK, ALPHA, ((hx0 + hx1) / 2, hy1 + .5 * HWP))
HAS_TREAT = LOOK != 'off'


def px(v):
    return f'{v:.1f}px'


def labels():
    """dot -> line -> chip for each label, in a layer that shares the picture's transform (so it rides the punch-in)"""
    svg, html, tw = [], [], []
    for q in PLACED:
        L, (x, y, w, h), (qx, qy), (ax, ay) = q['L'], q['rect'], q['port'], q['a']
        k, t = f"l{L['i']}", F(L['f_dot'])
        left = (qx - x) <= (x + w - qx)                          # pinned by the side the line meets
        side = f'left:{x}px' if left else f'right:{W - (x + w)}px'
        org_x = px(qx - x) if left else f'calc(100% - {px(x + w - qx)})'
        org_y = px(qy - y)
        ln = math.hypot(qx - ax, qy - ay)
        sx, sy = ax + (qx - ax) * 17 / ln, ay + (qy - ay) * 17 / ln      # the line starts outside the dot's ring
        svg.append(f'<path id="{k}ln" d="M{sx:.1f} {sy:.1f} L{qx:.1f} {qy:.1f}" pathLength="1" fill="none" stroke="{CHIP}" '
                   f'stroke-width="3.5" stroke-linecap="round" stroke-dasharray="1" stroke-dashoffset="1"/>')
        words = ' '.join(f'<span class="wm"><span class="w {k}w">{wd}</span></span>' for wd in L['text'].split())
        idx = f'<span id="{k}ix" class="idx">{L["i"] + 1:02d}</span>' if NUMBERS else ''
        html.append(
            f'<div id="{k}dw" class="dotw" style="left:{ax:.1f}px;top:{ay:.1f}px">'
            f'<div id="{k}rg" class="ripple"></div><div id="{k}dt" class="dot"><i></i></div></div>'
            f'<div id="{k}cw" class="chipw" style="{side};top:{y}px;transform-origin:{org_x} {org_y}">'
            f'<div id="{k}pt" class="portdot" style="left:{org_x};top:{org_y}"></div>'
            f'<div class="chip">{idx}<span class="txt">{words}</span></div></div>')
        t_line, t_chip = t + .03, t + .14
        stagger = .04 if L['f_dot'] > L['f_word'] - LEAD else .07
        tw += [
            f"gsap.set('#{k}dt',{{scale:0}});gsap.set('#{k}rg',{{scale:.3,opacity:0}});gsap.set('#{k}ln',{{autoAlpha:0}});",
            f"gsap.set('#{k}cw',{{autoAlpha:0}});gsap.set('.{k}w',{{yPercent:118}});",
            f"tl.fromTo('#{k}dt',{{scale:0}},{{scale:1,duration:.26,ease:'back.out(2.6)',immediateRender:false}},{t:.3f});",
            f"tl.fromTo('#{k}rg',{{scale:.3,opacity:.95}},{{scale:3.4,opacity:0,duration:.6,ease:'power2.out',immediateRender:false}},{t:.3f});",
            f"tl.set('#{k}ln',{{autoAlpha:1}},{t_line:.3f});",
            f"tl.fromTo('#{k}ln',{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:.16,ease:'power2.inOut',immediateRender:false}},{t_line:.3f});",
            f"tl.fromTo('#{k}cw',{{autoAlpha:0,scale:.7,filter:'blur(9px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',duration:.32,ease:'back.out(1.9)',immediateRender:false}},{t_chip:.3f});",
            f"tl.fromTo('.{k}w',{{yPercent:118}},{{yPercent:0,duration:.36,ease:'expo.out',stagger:{stagger},immediateRender:false}},{t_chip + .04:.3f});",
        ]
        if NUMBERS:
            tw += [f"gsap.set('#{k}ix',{{scale:0}});",
                   f"tl.fromTo('#{k}ix',{{scale:0,rotation:-40}},{{scale:1,rotation:0,duration:.3,ease:'back.out(2.2)',immediateRender:false}},{t_chip + .05:.3f});"]
        if F_REL is not None:        # whip off: the chip flies out sideways with a smear, the line retracts, the dot blinks out
            to_left = x + w / 2 < W / 2
            out_x = -(x + w + 160) if to_left else (W - x + 160)
            t_out, d = F(L['f_out']), WHIP_F / FPS
            tw += [
                f"tl.to('#{k}cw',{{x:{out_x:.0f},skewX:{14 if to_left else -14},filter:'blur(7px)',duration:{d:.3f},ease:'power3.in'}},{t_out:.3f});",
                f"tl.set('#{k}cw',{{autoAlpha:0}},{t_out + d:.3f});",
                f"tl.to('#{k}ln',{{strokeDashoffset:1,duration:.1,ease:'power2.in'}},{t_out + .03:.3f});",
                f"tl.to('#{k}dt',{{scale:0,duration:.09,ease:'power2.in'}},{t_out + .08:.3f});",
            ]
    return ('<svg id="lines" width="1080" height="1920" viewBox="0 0 1080 1920" xmlns="http://www.w3.org/2000/svg">'
            + ''.join(svg) + '</svg>'), html, tw


def freeze():
    """the hold itself: plates over the live video, flash, punch-in, room look, and the way out"""
    t_end = DUR if F_REL is None else TU
    tw = [
        "gsap.set('#fz',{autoAlpha:0});gsap.set('#flash',{autoAlpha:0});gsap.set('#treat',{opacity:0});",
        f"gsap.set('#zoom',{{transformOrigin:'{OX:.1f}px {OY:.1f}px',scale:1,y:0}});",
        f"gsap.set('#drift',{{transformOrigin:'{SO[0]:.1f}px {SO[1]:.1f}px',scale:1}});",
        f"tl.set('#fz',{{autoAlpha:1}},{TF:.3f});",
        f"tl.fromTo('#flash',{{autoAlpha:.66}},{{autoAlpha:0,duration:.26,ease:'power2.out',immediateRender:false}},{TF:.3f});",
        f"tl.fromTo('#zoom',{{scale:1,y:0}},{{scale:{ZOOM},y:{DY:.1f},duration:.5,ease:'back.out(1.5)',immediateRender:false}},{TF:.3f});",
        f"tl.fromTo('#treat',{{opacity:0}},{{opacity:1,duration:.42,ease:'power2.out',immediateRender:false}},{TF + .02:.3f});",
    ]
    if F_REL is None:                # no way out: the slot ends on a cut, still frozen
        return tw + [f"tl.fromTo('#drift',{{scale:1}},{{scale:{KD},duration:{t_end - TF:.3f},ease:'none',immediateRender:false}},{TF:.3f});"]
    tw_in = TU - .2                  # the last 0.2 s of the hold: a short inhale while the chips leave
    return tw + [
        f"tl.fromTo('#drift',{{scale:1}},{{scale:{KD},duration:{tw_in - TF:.3f},ease:'none',immediateRender:false}},{TF:.3f});",
        f"tl.to('#drift',{{scale:{KD + .022},duration:.2,ease:'power2.in'}},{tw_in:.3f});",
        # the jump back to live is made on purpose: hard cut ON the release word, cut punch on the live picture, a lighter flash
        f"tl.set('#fz',{{autoAlpha:0}},{TU:.3f});",
        f"tl.fromTo('#live',{{scale:1.07}},{{scale:1,duration:{(PUNCH_F - 1) / FPS:.3f},ease:'power3.out',immediateRender:false}},{TU:.3f});",
        f"tl.set('#live',{{scale:1}},{F(F_REL + PUNCH_F):.3f});",
        f"tl.fromTo('#flash',{{autoAlpha:.34}},{{autoAlpha:0,duration:.18,ease:'power2.out',immediateRender:false}},{TU:.3f});",
        f"tl.set('#flash',{{autoAlpha:0}},{TU + .19:.3f});",
    ]


def audio():
    """shutter click on the freeze, one soft pop per chip, one whoosh on the release (stock template sounds)"""
    if not SFX_ON or COLTEST:
        return []
    sfx = [('click', TF - .01, .5)] + [('pop', F(q['L']['f_dot']) + .13, .2) for q in PLACED]
    if F_REL is not None:
        sfx.append(('whoosh-short', TU - .25, .24))
    out, lanes = [], []
    for n, (name, t, vol) in enumerate(sorted(sfx, key=lambda s: s[1])):
        d = min(SFX_LEN[name], DUR - t)
        if d <= .05 or not os.path.exists(f'assets/sfx/{name}.mp3'):
            continue
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'  <audio id="sfx{n}" src="assets/sfx/{name}.mp3" data-start="{max(0, t):.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#live{{position:absolute;inset:0;transform-origin:50% 46%}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#fz,#drift,#zoom{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
#fz{{z-index:3;overflow:hidden}}
.pic{{position:absolute;left:0;top:0;width:1080px;height:1920px;display:block}}
#treat{{position:absolute;inset:0}}
#lab{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0;
  transform:translate({-CX / ZOOM:.3f}px,{-CY / ZOOM:.3f}px) scale({1 / ZOOM:.6f})}}
#lines{{position:absolute;left:0;top:0;overflow:visible;filter:drop-shadow(0 2px 5px rgba(8,10,16,.55))}}
.dotw{{position:absolute;width:0;height:0}}
.dot{{position:absolute;left:-17px;top:-17px;width:34px;height:34px;border-radius:50%;border:3px solid {CHIP};
  box-shadow:0 2px 8px rgba(8,10,16,.55),inset 0 1px 4px rgba(8,10,16,.35);transform-origin:50% 50%}}
.dot i{{position:absolute;left:50%;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:{ACCENT};
  box-shadow:0 0 14px {ACCENT}bb}}
.ripple{{position:absolute;left:-17px;top:-17px;width:34px;height:34px;border-radius:50%;border:2.5px solid {ACCENT};transform-origin:50% 50%}}
.chipw{{position:absolute;height:{px(96 * K)};width:max-content}}
.portdot{{position:absolute;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;background:{CHIP};
  box-shadow:0 2px 6px rgba(8,10,16,.5)}}
.chip{{position:relative;height:100%;display:flex;align-items:center;gap:{px(18 * K)};padding:0 {px(30 * K)} 0 {px((17 if NUMBERS else 30) * K)};
  border-radius:{px(28 * K)};background:{CHIP};
  box-shadow:0 26px 54px rgba(8,10,16,.40),0 4px 12px rgba(8,10,16,.28),inset 0 -2px 0 rgba(20,22,28,.07)}}
.idx{{flex:none;display:flex;align-items:center;justify-content:center;width:{px(62 * K)};height:{px(62 * K)};border-radius:{px(18 * K)};
  background:{ACCENT};color:{INK};font:500 {px(25 * K)} 'JetBrains Mono';letter-spacing:-.02em;transform-origin:50% 50%}}
.txt{{font:800 {px(56 * K)} 'Inter Tight';letter-spacing:-.03em;line-height:1;color:{INK};white-space:nowrap}}
.wm{{display:inline-block;overflow:hidden;padding:.08em .03em .2em 0;margin:-.08em 0 -.2em 0;vertical-align:bottom}}
.w{{display:inline-block}}
#flash{{position:absolute;inset:0;z-index:9;background:#fff}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def video(vid, src, track, cls):
    return (f'<video id="{vid}" class="{cls}" src="{src}" muted playsinline data-start="0" data-media-start="0" '
            f'data-duration="{DUR:.3f}" data-track-index="{track}"></video>')


def build():
    svg, l_html, l_tw = labels()
    f_tw = freeze()
    nl = '\n'
    treat = f'<div id="treat">{video("fzt", "assets/freeze/treat.mp4", 3, "pic")}</div>' if HAS_TREAT else '<div id="treat"></div>'
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}{'#treat,#lab,#flash{display:none}' if COLTEST else ''}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
  <div id="live">{video("bgv", "assets/aroll.mp4", 0, "full")}</div>
  <div id="fz"><div id="drift"><div id="zoom">
    {video("fzp", "assets/freeze/plain.mp4", 1, "pic")}
    {treat}
    <div id="lab">
      {svg}
{nl.join(l_html)}
    </div>
  </div></div></div>
  <div id="flash"></div>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(f_tw + l_tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


def plan():
    """work/layout.jpg: the held frame as it sits after the punch-in, with the plan drawn on it"""
    im = Image.open('work/hold.jpg').convert('RGB').resize((W, H)).transform((W, H), Image.AFFINE, AFF, Image.BILINEAR)
    d = ImageDraw.Draw(im)
    for box, col in (((SL, ST, SR, SB), (255, 60, 60)), (HB, (80, 150, 255)), (FACE, (80, 150, 255))):
        d.rectangle([round(v) for v in box], outline=col, width=3)
    d.rectangle((SR2, SY2, SR, SB), outline=(255, 60, 60), width=3)
    for q in PLACED:
        x, y, w, h = q['rect']
        d.line([q['a'], q['port']], fill=(255, 248, 239), width=4)
        d.ellipse((q['a'][0] - 17, q['a'][1] - 17, q['a'][0] + 17, q['a'][1] + 17), outline=(255, 248, 239), width=4)
        d.rounded_rectangle((x, y, x + w, y + h), radius=int(28 * K), fill=(255, 248, 239))
        d.text((x + 20, y + h / 2 - 8), f"{q['L']['i'] + 1:02d} {q['L']['text']}", fill=(20, 22, 28))
    im.resize((540, 960), Image.LANCZOS).save('work/layout.jpg', quality=88)


open('index.html', 'w').write(build())
plan()
json.dump(dict(slot=SLOT, frames=N, freeze=F_FRZ, hold=HOLD_F, release=F_REL, head=[round(v, 1) for v in HB],
               labels=[dict(text=q['L']['text'], f_dot=q['L']['f_dot'], f_word=q['L']['f_word'], f_out=q['L']['f_out'],
                            rect=list(q['rect']), point=[round(v, 1) for v in q['a']], at=q['name']) for q in PLACED]),
          open('work/layout.json', 'w'), indent=1)

print(f"freeze-label: {N} frames. Freeze on frame {F_FRZ}, held frame {HOLD_F}, "
      + (f"release on frame {F_REL} (hold {(F_REL - F_FRZ) / FPS:.2f} s), plain again from frame {F_REL + PUNCH_F}" if F_REL is not None
         else 'no release: the slot ENDS frozen, on a cut'))
print(f"shot: {SHOT} (head {HWS:.0f} px wide after the {ZOOM}x punch-in)   look: {LOOK}   plates: {'baked' if baked else 'reused'}")
print(f"tie points found: {', '.join(sorted(ANCH))}")
for q in PLACED:
    x, y, w, h = q['rect']
    print(f"  {q['L']['i'] + 1:02d} '{q['L']['text']}' -> {q['name']}: dot frame {q['L']['f_dot']}, chip readable from frame {q['L']['f_dot'] + 8} "
          f"(word at {q['L']['f_word']}), chip x {x}..{x + w} y {y}..{y + h}")
print(f"layout: size {K:.2f} (text {56 * K:.0f} px), " + ('on clear background' if TIER == 1 else '!! over the body: no clear background on this frame, look at work/layout.jpg'))
for w_ in WARN:
    print('!! ' + w_)
print('look at work/freeze_pick.jpg (eyes open, sharp?) and work/layout.jpg (labels where you want them?) before rendering')
print('wrote index.html' + ('  (SAFE guide ON: do not render this one)' if SAFE else '') + ('  (COLTEST build)' if COLTEST else ''))
