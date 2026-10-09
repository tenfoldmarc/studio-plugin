#!/usr/bin/env python3
"""pointer-callout / build.py: callout cards that stay put, each tied to a tracked point on the speaker by a thin
line that stretches and swings with them on every frame (dot + ring pulse on the speaker, spring lag in the line).

  python build.py            writes index.html (run track.py first: it writes work/track.json and work/occ.png)
  SAFE=1 python build.py     same, with the Instagram unsafe area drawn in red (snapshot checks only)
  SFX=0                      no sounds.   CAPTIONS=0 is accepted and changes nothing (the effect has no caption words).

Card positions and size are measured: the open space around the speaker inside the safe zone, never over the head,
never over another card. No room for every card = it stops and says how many fit.
"""
import html
import itertools
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30

# ==== CLIP (edit this) ====
# One entry per card, in the order they are spoken (2 to 4 cards).
#   text    what the card says: the speaker's own name for the thing, 1 to 3 words. No number or claim they do not say.
#   say     the spoken word the card lands on, as track.py prints it ('skill', or 'this#2' for the second "this").
#           '' = no word: the cards come on one after the other from IN_F.
#   anchor  what on the speaker the line is tied to: 'head', 'head_left', 'head_right' (on the cap / hairline), 'chest',
#           'shoulder_left', 'shoulder_right', 'hand_left', 'hand_right' (left / right as seen on screen).
#           track.py prints which exist on this clip, how far each one moves and whether it stays in the safe zone.
#   side    where the card sits: 'left', 'right' or 'auto' (the clearest spot near its anchor).
#   icon    'check', 'image', 'script', 'launch', 'spark' or 'none'.
#   sub     small detail under the text: 'lines', 'thumbs', 'progress' or 'none'.
#   optional: at=seconds (overrides say when the printed onset is wrong), pos=(left, top) to place one card by hand.
CARDS = [
    dict(text='First thing', say='', anchor='head_left', side='auto', icon='check', sub='lines'),
    dict(text='Second thing', say='', anchor='head_right', side='auto', icon='check', sub='lines'),
    dict(text='Third thing', say='', anchor='chest', side='auto', icon='check', sub='lines'),
]
IN_F = 4          # first frame a card may appear: the slot starts on the plain picture. Keep 4 or more
OUT_F = None      # frame by which everything is gone. None = 6 frames before the slot ends (it ends on the plain picture)
DONE_SAY = ''     # optional spoken word on which every dot pulses once and 'progress' bars complete. '' = off
SIZE = 'auto'     # 'auto' = as large as the measured open space allows, or a number (1.0 = 44 px text)
FLOOR = 0.82      # smallest size that still reads on a phone (36 px text). Under it the build stops instead of shrinking
ACCENT, CREAM, INK = '#FAE67A', '#FFF8EF', '#14161C'   # line / dots / icon tile, card text, card. Brand colours, never orange
GRADE = 'none'    # CSS filter on the picture. Leave 'none': the reel grades, and anything else also changes frame 0
# ==== END CLIP ====

FP = shutil.which('ffprobe') or 'ffprobe'
SL, ST, SR, SB, SY2, SR2 = 35, 220, 1045, 1470, 1155, 980       # safe zone; the right side tightens to 980 from y 1155
LEAD = 2                             # frames a card starts before its word, so it is readable ON the word
LINE_DELAY, LINE_DUR = 3, 6          # frames after the card pops: the line leaves the card, then travels
SPRING_W, SPRING_Z, SPRING_K = 15.0, 0.34, 1.8   # rad/s, damping ratio, how much of the lag reaches the line belly
KICK = 520                           # px/s sideways impulse when the line lands
BOW = 0.07                           # resting curve of the line (fraction of its length)
SFX_LEAD = {'pop': .117, 'click-soft': .048}
SFX_GAIN = 0.75
C = 8                                # layout grid cell in px (work/occ.png is 135 x 240)


def on(name, default):
    v = os.environ.get(name)
    return default if v is None else v not in ('0', '')


def stop(msg):
    sys.exit('!! ' + msg)


try:
    CLIP = json.load(open(os.path.join(HERE, 'clip.json')))
    TRACK = json.load(open(os.path.join(HERE, 'work/track.json')))
    OCC = np.asarray(Image.open(os.path.join(HERE, 'work/occ.png')).convert('L'), np.float64) / 255
except FileNotFoundError as e:
    stop(f'{e.filename} is missing. The slot needs clip.json (fx_new.py) and work/track.json + work/occ.png (run track.py first).')
N = int(CLIP['frames'])
DUR = N / FPS
OUT = min(N - 2, OUT_F if OUT_F is not None else N - 6)
HW, HH = TRACK['hw'], TRACK['hh']
WORDS = TRACK.get('words', [])


def padded(rows):
    a = np.array(rows, float)
    return a if len(a) >= N else np.r_[a, np.repeat(a[-1:], N - len(a), 0)]


BOX = padded(TRACK['box'])
ANCH = {k: padded(v) for k, v in TRACK['anchors'].items()}
HXM = float(np.median((BOX[:, 0] + BOX[:, 2]) / 2))


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


def word_frame(say, at=None):
    if at is not None:
        return int(round(at * FPS))
    if not say:
        return None
    name, _, nth = say.partition('#')
    norm = lambda t: ''.join(ch for ch in t.lower() if ch.isalnum())
    hits = [w for w in WORDS if norm(w['text']) == norm(name)]
    if len(hits) < int(nth or 1):
        stop(f"say='{say}' is not in the slot's words: " + ' '.join(w['text'] for w in WORDS))
    w = hits[int(nth or 1) - 1]
    return int(round(w.get('onset', w['start']) * FPS))


# ---- cards: timing and the point each one is tied to ----------------------------------------------------------
if not 1 <= len(CARDS) <= 4:
    stop('CARDS needs 1 to 4 entries.')
ANY_SUB = any(c.get('sub', 'none') != 'none' for c in CARDS)
for i, c in enumerate(CARDS):
    c['id'] = f'c{i + 1}'
    if chr(8212) in c['text']:
        stop(f"card {i + 1}: no em dashes on screen.")
    fw = word_frame(c.get('say', ''), c.get('at'))
    c['f_word'] = fw if fw is not None else IN_F + LEAD + 12 * i
    c['f_in'] = max(IN_F, c['f_word'] - LEAD)
    if c['f_in'] + 30 > OUT:
        stop(f"card {i + 1} ('{c['text']}') comes on at frame {c['f_in']} and everything leaves at frame {OUT}: it needs 1 s "
             f"on screen. Cut the slot longer or land it on an earlier word.")
    if c['anchor'] not in ANCH:
        stop(f"card {i + 1}: anchor '{c['anchor']}' is not available on this clip. Usable: {', '.join(ANCH)}.")


def safe_gap(p, m):
    """how far a point is outside the safe zone -> (dx, dy) needed to bring it back in (0, 0 = inside)"""
    x, y = p
    right = (SR2 if y >= SY2 - m else SR) - m
    return (max(0, SL + m - x) - max(0, x - right), max(0, ST + m - y) - max(0, y - (SB - m)))


for c in CARDS:                      # a point that leaves the safe zone: one constant nudge, or a clear stop
    tr = ANCH[c['anchor']][c['f_in']:OUT + 1]
    gaps = np.array([safe_gap(p, 26) for p in tr])
    dx = gaps[:, 0].max() if gaps[:, 0].max() > 0 else gaps[:, 0].min()
    dy = gaps[:, 1].max() if gaps[:, 1].max() > 0 else gaps[:, 1].min()
    lim = .12 * HH if c['anchor'].startswith('head') else .35 * HW
    moved = tr + (dx, dy)
    if (dx or dy) and (math.hypot(dx, dy) > lim or any(safe_gap(p, 22) != (0, 0) for p in moved)):
        okay = [k for k, v in ANCH.items() if all(safe_gap(p, 26) == (0, 0) for p in v[c['f_in']:OUT + 1])]
        stop(f"card '{c['text']}': the point '{c['anchor']}' is outside the safe zone on this clip "
             f"(x {tr[:, 0].min():.0f}..{tr[:, 0].max():.0f}, y {tr[:, 1].min():.0f}..{tr[:, 1].max():.0f}). "
             f"Inside it for this card: {', '.join(okay) or 'none (cut the slot shorter or pick another line)'}.")
    c['track'] = ANCH[c['anchor']] + (dx, dy)
    if dx or dy:
        print(f"  note: '{c['anchor']}' nudged by ({dx:+.0f}, {dy:+.0f}) px to stay inside the safe zone")

# ---- layout: measured open space ---------------------------------------------------------------------------------
_FONT = []


def text_w(t, px):
    if not _FONT:
        try:
            _FONT.append(ImageFont.truetype(os.path.join(HERE, 'assets/fonts/InterTight-800-normal.woff2'), 200))
        except Exception:
            _FONT.append(None)
    if _FONT[0] is not None:
        w = _FONT[0].getlength(t) / 200
    else:                             # no woff2 support in this Pillow: estimate from character classes
        w = sum(.85 if ch in 'mwMW@' else .25 if ch in "iljtfI.,:;'!| " else .62 if ch.isupper() else .5 for ch in t) * 1.04
    return (w - .02 * len(t)) * px + 4


def dims(c, k):
    icon = 0 if c.get('icon', 'check') == 'none' else 100
    return math.ceil((22 + icon + 26 + (6 if not icon else 0)) * k + text_w(c['text'], 44 * k)), round((124 if ANY_SUB else 104) * k)


def integral(m):
    return np.pad(np.asarray(m, np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def rsum(I, X, Y, w, h):
    c0, c1 = np.clip(X // C, 0, 135).astype(int), np.clip(-(-(X + w) // C), 0, 135).astype(int)
    r0, r1 = np.clip(Y // C, 0, 240).astype(int), np.clip(-(-(Y + h) // C), 0, 240).astype(int)
    return I[r1, c1] - I[r0, c1] - I[r1, c0] + I[r0, c0], np.maximum((r1 - r0) * (c1 - c0), 1)


def mark(m, x0, y0, x1, y1):
    m[max(0, int(y0 // C)):max(0, int(-(-y1 // C))), max(0, int(x0 // C)):max(0, int(-(-x1 // C)))] = True


dotm = np.zeros((240, 135), bool)
MH = max(16.0, .12 * HW)
for c in CARDS:
    headm = np.zeros((240, 135), bool)
    for f in range(c['f_in'], OUT + 1):   # the head on every frame this card is up, with a margin (more above: card shadow)
        x0, y0, x1, y1 = BOX[f]
        mark(headm, x0 - MH, y0 - MH - 14, x1 + MH, y1 + MH)
    c['IH'] = integral(headm)
    for p in c['track'][c['f_in']:OUT + 1:2]:      # no card may sit on a dot
        mark(dotm, p[0] - 30, p[1] - 30, p[0] + 30, p[1] + 30)
ID, IO = integral(dotm), integral(OCC)
# what a line may never cross: the head box from the brow line down, with a margin at the sides and under the chin
FACE = np.c_[BOX[:, 0] - .5 * MH, BOX[:, 1] + .24 * (BOX[:, 3] - BOX[:, 1]) - 6, BOX[:, 2] + .5 * MH, BOX[:, 3] + MH]
LMIN = max(70.0, .45 * HW)
TARGET = float(np.clip(1.5 * HW, 170, 380))
TT = np.linspace(0, 1, 25)


def ports_of(X, Y, w, h, a, k):
    """for every spot: the point on the card's edge nearest to its anchor (kept off the round corners)"""
    ins = min(44 * k, w / 2, h / 2)
    cx, cy = np.clip(a[0], X + ins, X + w - ins), np.clip(a[1], Y + ins, Y + h - ins)
    px, py = np.stack([cx, cx, X + 0.0, X + w + 0.0]), np.stack([Y + 0.0, Y + h + 0.0, cy, cy])
    j = np.argmin(np.hypot(px - a[0], py - a[1]), 0)[None]
    return np.take_along_axis(px, j, 0)[0], np.take_along_axis(py, j, 0)[0]


def lines_ok(c, X, Y, w, h, PX, PY, placed):
    """for every spot at once: its line never crosses the face, another card or another line, and never gets too short"""
    fs = np.arange(c['f_in'], OUT + 1, 3)
    A, fb = c['track'][fs], FACE[fs]
    px, py = PX[:, None], PY[:, None]
    dx, dy = A[None, :, 0] - px, A[None, :, 1] - py                        # (spots, frames)
    ok = (np.hypot(dx, dy) >= LMIN).all(1)
    sx, sy = px[:, :, None] + dx[:, :, None] * TT, py[:, :, None] + dy[:, :, None] * TT     # points along the line
    inside = lambda qx, qy, x0, y0, x1, y1: ((qx > x0) & (qx < x1) & (qy > y0) & (qy < y1)).any((1, 2))
    ok &= ~inside(sx, sy, fb[None, :, 0, None], fb[None, :, 1, None], fb[None, :, 2, None], fb[None, :, 3, None])
    x0, y0 = X[:, None, None], Y[:, None, None]
    ok &= ~inside(sx, sy, x0 + 6, y0 + 6, x0 + w - 6, y0 + h - 6)          # nor its own card
    turn = lambda ax, ay, bx, by, qx, qy: (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
    for o, (ox, oy, ow, oh), op in placed:
        OA = o['track'][fs]
        ok &= ~inside(sx, sy, ox - 8, oy - 8, ox + ow + 8, oy + oh + 8)
        qx, qy = op[0] + (OA[:, 0, None] - op[0]) * TT, op[1] + (OA[:, 1, None] - op[1]) * TT      # the other card's line
        ok &= ~inside(qx[None], qy[None], x0 - 8, y0 - 8, x0 + w + 8, y0 + h + 8)
        ax, ay, bx, by = A[None, :, 0], A[None, :, 1], OA[None, :, 0], OA[None, :, 1]
        ok &= ~((turn(px, py, ax, ay, op[0], op[1]) * turn(px, py, ax, ay, bx, by) < 0) &
                (turn(op[0], op[1], bx, by, px, py) * turn(op[0], op[1], bx, by, ax, ay) < 0)).any(1)
    return ok


def place(k, tier, order):
    placed = []
    for i in order:
        c = CARDS[i]
        w, h = dims(c, k)
        am = c['track'][c['f_in']:OUT + 1].mean(0)
        cands = []
        if c.get('pos'):
            x, y = int(c['pos'][0]), int(c['pos'][1])
            px, py = ports_of(np.array([x]), np.array([y]), w, h, am, k)
            cands = [(x, y, float(px[0]), float(py[0]))]
        else:
            xs, ys = np.arange(SL + 18, SR - 18 - w + 1, 12), np.arange(ST + 24, SB - 24 - h + 1, 12)
            if not len(xs) or not len(ys):
                return None
            X, Y = np.meshgrid(xs, ys)
            occ = rsum(IO, X, Y, w, h)
            occ = occ[0] / occ[1]
            valid = ~((Y + h > SY2 - 18) & (X + w > SR2 - 18)) & (rsum(c['IH'], X, Y, w, h)[0] == 0) & (rsum(ID, X, Y, w, h)[0] == 0)
            valid &= occ <= (.10 if tier == 1 else 1.0)
            g = 22 * k
            for _, (ox, oy, ow, oh), _ in placed:
                valid &= ~((X < ox + ow + g) & (X + w > ox - g) & (Y < oy + oh + g) & (Y + h > oy - g))
            cx = X + w / 2
            if c.get('side', 'auto') in ('left', 'right'):
                valid &= (cx < HXM) == (c['side'] == 'left')
            dist = np.hypot(np.maximum(np.maximum(X - am[0], am[0] - (X + w)), 0), np.maximum(np.maximum(Y - am[1], am[1] - (Y + h)), 0))
            valid &= dist >= LMIN
            nl = sum(1 for _, r, _ in placed if r[0] + r[2] / 2 < HXM)
            cost = 900 * occ + .6 * np.abs(dist - TARGET) + 60 * np.where(cx < HXM, nl, len(placed) - nl) + .12 * np.maximum(0, Y + h / 2 - am[1])
            idx = np.flatnonzero(valid)
            idx = idx[np.argsort(cost.ravel()[idx], kind='stable')]
            Xr, Yr = X.ravel(), Y.ravel()
            # where the line may leave the card: the edge point nearest the anchor first, then the corners and edge middles
            ins = min(44 * k, w / 2, h / 2)
            opts = [ports_of(Xr, Yr, w, h, am, k)] + [(Xr + ins + fx * (w - 2 * ins), Yr + fy * h + 0.0) for fx, fy in
                                                       ((0, 1), (1, 1), (0, 0), (1, 0), (.5, 1), (.5, 0))]
            for s0 in range(0, len(idx), 600):       # cheapest spots first, 600 at a time
                part = idx[s0:s0 + 600]
                first = [(int(np.argmax(g)), oi) for oi, g in enumerate(
                    lines_ok(c, Xr[part], Yr[part], w, h, PX[part], PY[part], placed) for PX, PY in opts) if g.any()]
                if first:
                    r, oi = first[0] if first[0][1] == 0 else min(first)
                    j = part[r]
                    cands = [(int(Xr[j]), int(Yr[j]), float(opts[oi][0][j]), float(opts[oi][1][j]))]
                    break
        if not cands:
            if on('DEBUG', False):
                print(f"    size {k} tier {tier} order {order}: no spot for '{c['text']}' ({w} x {h} px): "
                      + ('placed by hand' if c.get('pos') else f'{len(idx)} spots clear of head / cards / dots, none with a clean line'))
            return None
        x, y, px, py = cands[0]
        placed.append((c, (x, y, w, h), (px, py)))
    return placed


def layout(cards_idx):
    w1 = max(dims(CARDS[i], 1.0)[0] for i in cards_idx)
    top = min(1.3, 540 / w1)                                    # no card wider than half the frame
    ks = [SIZE] if SIZE != 'auto' else sorted({round(max(FLOOR, min(top, v)), 2) for v in (1.3, 1.2, 1.1, 1.0, .9, FLOOR)}, reverse=True)
    orders = list(itertools.permutations(cards_idx))
    for tier in (1, 2):                                         # 1 = on clear background, 2 = may sit over the body (never the head)
        for k in ks:
            if tier == 2 and SIZE == 'auto' and k > 1.0:
                continue
            for order in orders:
                got = place(k, tier, order)
                if got:
                    return k, tier, got
    return None


res = layout(list(range(len(CARDS))))
if res is None:
    fit = next((m for m in range(len(CARDS) - 1, 0, -1) if layout(list(range(m)))), 0)
    stop(f"no room for {len(CARDS)} cards on this clip at a readable size: {fit} fit{'s' if fit == 1 else ''} "
         f"(the head box, the safe zone and the other cards leave too little space; head {HW:.0f} px wide = {TRACK.get('shot', '?')} shot). "
         f"Keep {'the one that matters' if fit == 1 else f'the {fit} that matter'} most, shorten the text, tie the lines to head_left / head_right, "
         f"or use a wider shot." if fit else
         f"no room for a single card on this clip at a readable size (head {HW:.0f} px wide fills the safe zone). Use another effect here.")
K, TIER, PLACED = res
for c, rect, port in PLACED:
    c['rect'], c['port'] = rect, port
print(f"layout: size {K:.2f} (text {44 * K:.0f} px), {'on clear background' if TIER == 1 else '!! over the body: no clear background on this clip, look at the snapshot'}")


def spring_lag(track, f0, f_land, kick):
    """Damped spring follower of the anchor. Returns {frame: (lx, ly)} = follower minus anchor (0 when it is still)."""
    sub = 8
    dt = 1 / (FPS * sub)
    q, v, out = list(track[f0]), [0.0, 0.0], {}
    for f in range(f0, N):
        out[f] = (q[0] - track[f][0], q[1] - track[f][1])
        if f == f_land:
            v[0] += kick[0]
            v[1] += kick[1]
        nxt = track[min(f + 1, N - 1)]
        for j in range(sub):
            u = j / sub
            for ax in (0, 1):
                tgt = track[f][ax] * (1 - u) + nxt[ax] * u
                v[ax] += (SPRING_W ** 2 * (tgt - q[ax]) - 2 * SPRING_Z * SPRING_W * v[ax]) * dt
                q[ax] += v[ax] * dt
    return out


ICONS = {
    'check': '<path d="M9 25 L20 36 L39 13"/>',
    'spark': '<path d="M24 5 L28.5 19.5 L43 24 L28.5 28.5 L24 43 L19.5 28.5 L5 24 L19.5 19.5 Z"/>',
    'image': '<rect x="6" y="9" width="36" height="30" rx="7"/><circle cx="17" cy="20" r="3.4"/>'
             '<path d="M8.5 34.5 L19 25 L26 31 L31.5 26 L40 33.5"/>',
    'script': f'<rect x="6" y="6" width="36" height="23" rx="6.5"/><path d="M21 12.5 L29 17.5 L21 22.5 Z" fill="{INK}"/>'
              '<path d="M8 36.5 H40 M8 43 H27"/>',
    'launch': '<path d="M42 6 L5 21 L20 27 Z M42 6 L27 43 L20 27"/>',
}
F_DONE = word_frame(DONE_SAY) if DONE_SAY else None


def sub_html(c):
    i, s = c['id'], c.get('sub', 'none')
    room = text_w(c['text'], 44 * K) - 6             # the detail never runs wider than the text above it
    if s == 'thumbs':
        return ''.join(f'<i id="{i}s{j}" class="th{" on" if j == 0 else ""}"></i>' for j in range(3))
    if s == 'lines':
        f = min(1.0, (room - 16 * K) / (268 * K))
        return ''.join(f'<i id="{i}s{j}" class="bar" style="width:{w * K * f:.0f}px"></i>' for j, w in enumerate((132, 84, 52)))
    return f'<i class="trk" style="width:{min(138 * K, room):.0f}px"><i id="{i}fill" class="fill"></i></i>' if s == 'progress' else ''


def sub_tweens(c):
    i, s, t = c['id'], c.get('sub', 'none'), F(c['f_in'] + 10)
    if s == 'thumbs':
        return [f"gsap.set('#{i}s{j}',{{scale:0}});" for j in range(3)] + \
               [f"tl.to('#{i}s{j}',{{scale:1,duration:.34,ease:'back.out(2.6)'}},{t + j * .1:.3f});" for j in range(3)]
    if s == 'lines':
        return [f"gsap.set('#{i}s{j}',{{scaleX:0}});" for j in range(3)] + \
               [f"tl.to('#{i}s{j}',{{scaleX:1,duration:.3,ease:'power3.out'}},{t + j * .12:.3f});" for j in range(3)]
    if s != 'progress':
        return []
    end = F(F_DONE) if F_DONE and F(F_DONE) > t + .3 else min(t + 1.3, F(OUT) - .3)
    return [f"gsap.set('#{i}fill',{{scaleX:0}});",
            f"tl.to('#{i}fill',{{scaleX:.86,duration:{end - t - .08:.3f},ease:'power1.inOut'}},{t:.3f});",
            f"tl.to('#{i}fill',{{scaleX:1,duration:.12,ease:'power3.out'}},{end:.3f});",
            f"tl.to('#{i}ic',{{keyframes:{{scale:[1,1.2,1]}},duration:.36,ease:'power2.out'}},{end:.3f});"]


def callout(c):
    """One callout: card (fixed) + line whose end follows the track + dot. -> card html, svg, dots, tweens, frame data"""
    i, track, f_in = c['id'], c['track'], c['f_in']
    left, top, w, h = c['rect']
    px, py = c['port']
    f_line, f_land = f_in + LINE_DELAY, f_in + LINE_DELAY + LINE_DUR
    ax, ay = track[f_land]
    ln = math.hypot(ax - px, ay - py) or 1
    nx, ny = -(ay - py) / ln, (ax - px) / ln
    hx, hy = (BOX[f_land][0] + BOX[f_land][2]) / 2, (BOX[f_land][1] + BOX[f_land][3]) / 2
    mx, my = (px + ax) / 2, (py + ay) / 2          # the line bows away from the head
    bow = BOW if math.hypot(mx + nx - hx, my + ny - hy) > math.hypot(mx - nx - hx, my - ny - hy) else -BOW
    lag = spring_lag(track, f_line, f_land, (nx * KICK * K, ny * KICK * K))
    frames, lens = [], []
    for f in range(f_line, OUT + 1):
        ax, ay = track[f]
        dx, dy = ax - px, ay - py
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        lx, ly = lag[f]
        cx = (px + ax) / 2 + nx * ln * bow + SPRING_K * lx
        cy = (py + ay) / 2 + ny * ln * bow + SPRING_K * ly
        if f < f_land:
            # travel: only the first part of the curve (quadratic split at u), computed here per frame because a
            # stroke-dashoffset tween on a pathLength-normalised path snaps from hidden to full in the renderer
            u = 1 - (1 - (f - f_line + 1) / (LINE_DUR + 1)) ** 2.4
            q0x, q0y = px + (cx - px) * u, py + (cy - py) * u
            q1x, q1y = cx + (ax - cx) * u, cy + (ay - cy) * u
            d = f'M{px:.1f} {py:.1f}Q{q0x:.1f} {q0y:.1f} {q0x + (q1x - q0x) * u:.1f} {q0y + (q1y - q0y) * u:.1f}'
        else:
            d = f'M{px:.1f} {py:.1f}Q{cx:.1f} {cy:.1f} {ax:.1f} {ay:.1f}'
            lens.append(ln)
        frames.append((d, round(float(ax), 1), round(float(ay), 1)))
    occ = rsum(IO, np.array(left), np.array(top), w, h)
    print(f"  {i} '{c['text']}' -> {c['anchor']}: card x {left}..{left + w} y {top}..{top + h}, on at frame {f_in} "
          f"(word at {c['f_word']}), line lands {f_land}, length {min(lens):.0f}..{max(lens):.0f} px, "
          f"{100 * float(occ[0] / occ[1]):.0f}% of the card over the speaker")
    icon = c.get('icon', 'check')
    ic = f'<div id="{i}ic" class="ic"><svg viewBox="0 0 48 48">{ICONS[icon]}</svg></div>' if icon != 'none' else f'<div id="{i}ic"></div>'
    sub = f'<div class="sub">{sub_html(c)}</div>' if c.get('sub', 'none') != 'none' else ''
    card = (f'<div id="{i}" class="card{"" if icon != "none" else " noic"}" style="left:{left}px;top:{top}px;width:{w}px;'
            f'transform-origin:{px - left:.1f}px {py - top:.1f}px">{ic}'
            f'<div class="tx"><div class="lbm"><div id="{i}lb" class="lb">{html.escape(c["text"])}</div></div>{sub}</div></div>')
    d0 = frames[0][0]
    svg = f'<g id="{i}g"><path class="lc ln-{i}" d="{d0}"/><path class="ll ln-{i}" d="{d0}"/></g>'
    dots = (f'<div id="{i}port" class="port" style="left:{px:.1f}px;top:{py:.1f}px"></div>'
            f'<div id="{i}dot" class="dot"><div id="{i}ring" class="ring"></div><div id="{i}halo" class="halo"></div>'
            f'<div id="{i}core" class="core"></div></div>')
    t0, tl_, td = F(f_in), F(f_line), F(f_land)
    tw = [
        f"gsap.set(['#{i}','#{i}g','#{i}port'],{{autoAlpha:0}});",
        f"gsap.set(['#{i}core','#{i}halo'],{{scale:0}});",
        f"gsap.set('#{i}ring',{{autoAlpha:0,scale:.25}});",
        f"gsap.set('#{i}dot',{{x:{frames[0][1]},y:{frames[0][2]}}});",
        # card: grows out of its port with a quick focus pull. Width eases in with NO overshoot, the height overshoots
        f"tl.set('#{i}',{{autoAlpha:1}},{t0:.3f});",
        f"tl.fromTo('#{i}',{{scaleX:.6}},{{scaleX:1,duration:.4,ease:'expo.out',immediateRender:false}},{t0:.3f});",
        f"tl.fromTo('#{i}',{{scaleY:.45}},{{scaleY:1,duration:.5,ease:'back.out(2.6)',immediateRender:false}},{t0:.3f});",
        f"tl.fromTo('#{i}',{{rotation:{2.5 if px < left + w / 2 else -2.5}}},{{rotation:0,duration:.45,ease:'power3.out',immediateRender:false}},{t0:.3f});",
        f"tl.fromTo('#{i}',{{filter:'blur(14px)'}},{{filter:'blur(0px)',duration:.2,ease:'power2.out',immediateRender:false}},{t0:.3f});",
        # icon and label start hidden (gsap.set), so nothing shows at rest scale before its own tween begins
        f"gsap.set('#{i}ic',{{scale:.3,rotation:-28}});",
        f"gsap.set('#{i}lb',{{yPercent:112}});",
        f"tl.to('#{i}ic',{{scale:1,rotation:0,duration:.5,ease:'back.out(2.2)'}},{t0 + .02:.3f});",
        f"tl.to('#{i}lb',{{yPercent:0,duration:.3,ease:'expo.out'}},{t0:.3f});",
        f"tl.set(['#{i}port','#{i}g'],{{autoAlpha:1}},{tl_:.3f});",
        f"tl.fromTo('#{i}port',{{scale:0}},{{scale:1,duration:.24,ease:'back.out(3)',immediateRender:false}},{tl_:.3f});",
        # landing: dot pops, ring pulse
        f"tl.to('#{i}core',{{scale:1,duration:.3,ease:'back.out(3.2)'}},{td - .034:.3f});",
        f"tl.to('#{i}halo',{{scale:1,duration:.42,ease:'back.out(2)'}},{td:.3f});",
    ]
    # ring pulses: one on landing, a soft idle one every 1.25 s, one more on DONE_SAY
    t_end, t_done = F(OUT) - .25, (F(F_DONE) if F_DONE else None)
    pulses = [(td, .95, 1.0)] + [(td + 1.25 * j, .5, .8) for j in range(1, 12) if not t_done or abs(td + 1.25 * j - t_done) > .5]
    if t_done and t_done > td + .3:
        pulses.append((t_done, .9, 1.0))
    cap = min(1.0, .18 * HH / (44 * K)) if c['anchor'].startswith('head') else 1.0     # a ring on the cap stays above the brows
    pulses = sorted((tp, op, round(sc * cap, 3)) for tp, op, sc in pulses if tp < t_end - .2)
    for j, (tp, op, sc) in enumerate(pulses):
        nxt = pulses[j + 1][0] if j + 1 < len(pulses) else t_end
        dd = min(.75, nxt - tp - .01)
        if dd >= .2:
            tw.append(f"tl.fromTo('#{i}ring',{{autoAlpha:{op},scale:.25}},{{autoAlpha:0,scale:{sc},duration:{dd:.3f},ease:'power2.out',immediateRender:false}},{tp:.3f});")
    tw += sub_tweens(c)
    return card, svg, dots, tw, {'f0': f_line, 'd': [fr[0] for fr in frames], 'x': [fr[1] for fr in frames], 'y': [fr[2] for fr in frames]}


def audio():
    if not on('SFX', True):
        return []
    hitsfx = [('pop', c['f_word'] / FPS, .24) for c in CARDS] + ([('click-soft', F_DONE / FPS, .36)] if F_DONE else [])
    out, lanes = [], []
    for j, (name, t, vol) in enumerate(sorted(((n, max(0.0, t - SFX_LEAD.get(n, 0)), v) for n, t, v in hitsfx), key=lambda x: x[1])):
        ln = float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                   os.path.join(HERE, f'assets/sfx/{name}.mp3')], capture_output=True, text=True).stdout or 0)
        d = min(ln, DUR - t)
        if d <= 0.05:
            continue
        lane = next((q for q, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{j}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def px(v):
    return f'{v * K:.1f}px'


CARD_H = PLACED[0][1][3]
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#plate{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1{'' if GRADE == 'none' else ';filter:' + GRADE}}}
#cards{{position:absolute;inset:0;z-index:3}}
.card{{position:absolute;height:{CARD_H}px;border-radius:{px(32)};padding:0 {px(26)} 0 {px(22)};display:flex;align-items:center;gap:{px(20)};
  background:linear-gradient(180deg,#23262F 0%,{INK} 100%);border:1.5px solid rgba(255,248,239,.16);
  box-shadow:0 14px 34px rgba(0,0,0,.38),0 4px 12px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.07)}}
.card.noic{{padding:0 {px(26)} 0 {px(28)};gap:0}}
.ic{{flex:none;width:{px(80)};height:{px(80)};border-radius:{px(23)};background:{ACCENT};display:flex;align-items:center;justify-content:center;
  box-shadow:inset 0 -4px 0 rgba(20,22,28,.10),0 6px 18px rgba(0,0,0,.18)}}
.ic svg{{width:{px(46)};height:{px(46)};fill:none;stroke:{INK};stroke-width:4.2;stroke-linecap:round;stroke-linejoin:round}}
.tx{{display:flex;flex-direction:column;justify-content:center}}
.lbm{{height:{px(52)};overflow:hidden}}
.lb{{font-family:'Inter Tight';font-weight:800;font-size:{px(44)};line-height:{px(52)};letter-spacing:-.02em;color:{CREAM};white-space:nowrap}}
.sub{{display:flex;align-items:center;gap:{px(8)};height:{px(16)};margin-top:{px(7)}}}
.sub i{{display:block;flex:none}}
.th{{width:{px(26)};height:{px(16)};border-radius:{px(5)};background:rgba(255,248,239,.24)}}
.th.on{{background:{ACCENT}}}
.bar{{height:{px(9)};border-radius:{px(5)};background:rgba(255,248,239,.26);transform-origin:0 50%}}
.trk{{position:relative;width:{px(138)};height:{px(9)};border-radius:{px(5)};background:rgba(255,248,239,.18);overflow:hidden}}
.fill{{position:absolute;inset:0;border-radius:{px(5)};background:{ACCENT};transform-origin:0 50%}}
#lines{{position:absolute;inset:0;width:1080px;height:1920px;z-index:5;overflow:visible}}
#lines path{{fill:none;stroke-linecap:round}}
.lc{{stroke:rgba(16,17,22,.50);stroke-width:{9 * K:.1f}}}
.ll{{stroke:{ACCENT};stroke-width:{4 * K:.1f}}}
#dots{{position:absolute;inset:0;z-index:6}}
.port{{position:absolute;width:{px(18)};height:{px(18)};margin:{px(-9)} 0 0 {px(-9)};border-radius:50%;background:{ACCENT};border:{px(3.5)} solid {INK}}}
.dot{{position:absolute;left:0;top:0;width:0;height:0}}
.dot>div{{position:absolute;border-radius:50%}}
.core{{width:{px(22)};height:{px(22)};left:{px(-11)};top:{px(-11)};background:{ACCENT};border:{px(3.5)} solid {INK};box-shadow:0 2px 10px rgba(0,0,0,.45)}}
.halo{{width:{px(40)};height:{px(40)};left:{px(-20)};top:{px(-20)};border:2.5px solid {ACCENT};opacity:.75;box-shadow:0 0 0 1.5px rgba(16,17,22,.28)}}
.ring{{width:{px(88)};height:{px(88)};left:{px(-44)};top:{px(-44)};border:3px solid {ACCENT}}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    cards, svgs, dots, tw, data = [], [], [], [], {}
    for c in CARDS:
        card, svg, dot, t, d = callout(c)
        cards.append(card)
        svgs.append(svg)
        dots.append(dot)
        tw += t
        data[c['id']] = d
    # everything leaves before the slot ends: the last frames are the plain picture
    tw += [f"tl.to(['#cards','#lines','#dots'],{{autoAlpha:0,duration:.166,ease:'power2.in'}},{F(OUT) - .166:.3f});",
           f"tl.set(['#cards','#lines','#dots'],{{autoAlpha:0}},{F(OUT):.3f});"]
    nl = '\n'
    # per-frame driver: ONE linear proxy tween, onUpdate writes the path + dot position of the current frame
    driver = f'''const TR = {json.dumps(data, separators=(',', ':'))};
const LN = {{}}, DT = {{}};
for (const id in TR) {{ LN[id] = document.querySelectorAll('.ln-' + id); DT[id] = document.getElementById(id + 'dot'); }}
function drawFrame(f) {{
  for (const id in TR) {{
    const tr = TR[id];
    const k = Math.max(0, Math.min(tr.d.length - 1, f - tr.f0));
    LN[id].forEach(p => p.setAttribute('d', tr.d[k]));
    gsap.set(DT[id], {{ x: tr.x[k], y: tr.y[k] }});
  }}
}}
drawFrame(0);
(function () {{ const o = {{ f: 0 }}; tl.to(o, {{ f: {N}, duration: {N / FPS:.4f}, ease: 'none', onUpdate: function () {{ drawFrame(Math.floor(o.f + 0.07)); }} }}, 0); }})();'''
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <video id="plate" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
  <audio id="voice" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
  <div id="cards">
{nl.join(cards)}
  </div>
  <svg id="lines" viewBox="0 0 1080 1920">{''.join(svgs)}</svg>
  <div id="dots">
{nl.join(dots)}
  </div>
{SAFE_GUIDE if on('SAFE', False) else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
{driver}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open(os.path.join(HERE, 'index.html'), 'w').write(build())
json.dump({'size': K, 'tier': TIER, 'out': OUT, 'cards': [
    {'id': c['id'], 'text': c['text'], 'anchor': c['anchor'], 'rect': list(c['rect']), 'port': list(c['port']), 'f_in': c['f_in'],
     'f_word': c['f_word'], 'track': np.round(c['track'], 1).tolist()} for c in CARDS]}, open(os.path.join(HERE, 'work/layout.json'), 'w'))
if GRADE != 'none':
    print('!! GRADE is on: the first and last frame are no longer the plain picture')
print(f'wrote index.html: {N} frames ({DUR:.2f} s), cards on from frame {min(c["f_in"] for c in CARDS)}, everything gone by frame {OUT}'
      + ('   [SAFE guide ON: do not render this one]' if on('SAFE', False) else ''))
