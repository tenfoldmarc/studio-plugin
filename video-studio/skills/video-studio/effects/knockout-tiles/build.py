#!/usr/bin/env python3
"""KNOCKOUT TILES: name tiles slam onto the wall behind the speaker, one per spoken word. Each one is struck out and
knocked away (dropped, flicked or shattered) as the next lands. Optional second half: receipts stack up beside the
head while a running total counts them, then the whole pile is struck and falls.

Layers: the clip < tiles / receipts / total (flat on the wall) < the speaker's cutout. The cutout layer only exists
between F_IN and F_OUT, so the first and last frame of the slot are the untouched clip.

Run order (from the slot folder, see effect.md):
  python prep.py words     every spoken word with its frame      -> fill the CLIP block below
  python prep.py           measures the cutout, places everything -> work/layout.json, work/layout.jpg (look at it)
  python3 build.py         writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds; CAPTIONS=0 / GRADE=0 no-ops)
"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys

# ==== STYLE (the reel's look wins: when the reel has a caption or overall style, match this block to it) ====
# Every word this effect draws takes its typeface, case, weight, colours and placement from here. The defaults are
# a neutral dark tile with cream type. Fonts must be families that assets/fonts/fonts.css provides.
STYLE = dict(
    name_font='Inter Tight',       # typeface of the tile names, receipt titles and the total
    name_weight=900,               # its weight (use one the font file has)
    name_case='as-typed',          # 'as-typed', 'upper' or 'lower'
    name_tracking=-0.022,          # letter spacing of the names, in em
    small_font='JetBrains Mono',   # typeface of the small label, the receipt lines and the total tag
    small_weight=500,
    small_case='as-typed',         # 'as-typed', 'upper' or 'lower'
    width_factor=1.0,              # raise to 1.1 if a name touches the edge of its tile with another typeface
    tile_bg='#0E0F12',             # tile and total plate
    tile_text='#F7F4EE',           # name on the tile
    label_color='#FAE67A',         # small label under the name (the reel's accent colour; never orange)
    strike='#E5484D',              # the strike-through, the counted amounts and the total digits
    paper='#F7F4EE',               # receipt paper
    paper_ink='#0E0F12',           # receipt text
    radius=28,                     # tile corner radius, px
    order=['left', 'right', 'above'],   # placement: wall spots around the head, used in turn. Drop one to keep it clear
)
# ==== END STYLE ====

# ==== CLIP (edit this) ====
# The tiles, in spoken order. 'text' = the name on the tile: ONLY a name the speaker says in this clip or the user
# gave you. Plain text, no logos. 'at' = the spoken word it lands on ('word', or 'word#2' for the second time it is
# said) or a frame number; list them with `prep.py words`. Optional keys per tile: 'exit' ('drop', 'flick',
# 'shatter'; default by spot), 'spot' ('left', 'right', 'above'; default STYLE order), 'knock' (frame or word it is
# knocked away on; default = when the next tile lands, the last one 21 frames after it lands).
TILES = [
    {'text': 'Tool one', 'at': 12},        # placeholder: replace with the first name the speaker says
    {'text': 'Tool two', 'at': 36},        # placeholder
    {'text': 'Tool three', 'at': 60},      # placeholder
]
TILE_LABEL = ''      # small line under every name saying what these things are ('' = none). The speaker's own words
RECEIPTS_ON = False  # the switch for the second half. False = tiles only (the fields below are ignored)
# One entry per receipt, in spoken order: a frame or word (uses the three defaults below), or a dict with 'at' and
# any of 'title', 'item', 'amount' for a receipt that differs. Up to 8; they alternate sides of the head.
RECEIPTS = []
RECEIPT_TITLE = 'Receipt'   # placeholder: bold first line (what is being paid for, in the speaker's words)
RECEIPT_ITEM = '1 item'     # placeholder: the line item
RECEIPT_AMOUNT = 0          # whole number per receipt. ONLY an amount the speaker says or the user gave you
CURRENCY = ''        # printed before every amount, e.g. '$' ('' = bare numbers)
RECEIPT_FIRST_SIDE = 'left'   # side of the head the first receipt lands on
TOTAL_AT = None      # frame or word the running total slams in above the head. None = receipts without a total.
                     # The total is always the sum of the receipts on the wall: it is computed, never typed in
TOTAL_TAG = ''       # small tag that drops out under the total ('' = none), in the speaker's words
TOTAL_TAG_AT = None  # frame or word the tag drops on. None = 8 frames after the total lands
TOTAL_POS = None     # (x, y) centre of the total plate, px. None = centred above the head (prep.py says if no room)
WIPE_AT = None       # frame or word the pile is struck and falls. None = 24 frames after the last thing lands
F_IN = None          # frame the effect switches on. None = 5 frames before the first tile lands (never frame 0)
F_OUT = None         # frame the plain picture is back. None = as soon as the last piece is gone. Max: frames - 2
WALL = None          # (x0, y0, x1, y1) px the pieces may use. None = the whole safe zone. Set it when work/layout.jpg
                     # shows a piece on a window, a shelf or furniture
SPOTS = {}           # hand placement, e.g. {'left': (230, 540), 'right': (860, 540), 'above': (540, 310)}: the centre
                     # of that wall spot, px. Only the spots you name are fixed; the rest stay measured
PILES = {}           # same for the receipt piles: {'left': (x, y), 'right': (x, y)} = centre of the pile
SIZE = 1.0           # overall size of tiles and receipts (0.8 to 1.15). prep.py shrinks a piece that has no room
VOICE = True         # False = silent slot (no clip audio in the render)
SOUNDS = 'auto'      # 'auto' = a pop per landing, a short whoosh per knock, one low hit on the total. Or a list of
                     # (name, frame, volume) with the stock names; [] = none. Played at 0.75x, under the voice
SEED = 3             # change it to vary tilts
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
SFX_GAIN = 0.75
SAFE = dict(top=220, bottom=1470, left=35, right=1045, right_low=980, low_y=1155)
ROT = {'left': -5.0, 'right': 4.0, 'above': -2.5}
EXIT = {'left': 'drop', 'right': 'flick', 'above': 'shatter'}
RW, RH, RSTEP = 300, 136, 70          # receipt size and how far the next one on a side lands above the last
PLACEHOLDERS = ('Tool one', 'Tool two', 'Tool three', 'Receipt', '1 item')
NEAR = '0px 16px 30px 0px rgba(0,0,0,0.5), 0px 3px 7px 0px rgba(0,0,0,0.4)'
FAR = '0px 80px 90px 0px rgba(0,0,0,0.2), 0px 34px 44px 0px rgba(0,0,0,0.1)'
PNEAR = '0px 14px 26px 0px rgba(0,0,0,0.44), 0px 2px 6px 0px rgba(0,0,0,0.34)'
PFAR = '0px 70px 80px 0px rgba(0,0,0,0.18), 0px 30px 40px 0px rgba(0,0,0,0.1)'
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def F(n):
    """time of frame n, nudged 2 ms early so a hit lands ON that frame"""
    return max(0.0, n / FPS - .002)


def r1(v):
    return round(v * 10) / 10


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def cased(s, which):
    mode = STYLE[which]
    return s.upper() if mode == 'upper' else s.lower() if mode == 'lower' else s


def text_w(s, fs, mono=False):
    """estimated width in px (build time has no browser): generous on purpose, tune with STYLE['width_factor']"""
    if mono:
        return len(s) * .6 * fs
    w = 0.0
    for ch in s:
        w += (.26 if ch == ' ' else .30 if ch in "il.,:;!'|" else .40 if ch in 'ftjrI-' else .90 if ch in 'mwMW@%'
              else .70 if ch.isupper() else .62 if ch.isdigit() else .58)
    return (w + STYLE['name_tracking'] * len(s)) * fs * STYLE['width_factor']


def tile_size(text, spot, scale=1.0):
    """(W, H, font size) of a tile on a wall spot"""
    fs = (76 if spot == 'above' else 78) * SIZE * scale
    lab = bool(TILE_LABEL)
    W = text_w(cased(text, 'name_case'), fs) + 2 * (46 if spot == 'above' else 38) * SIZE * scale
    if lab:
        W = max(W, text_w(cased(TILE_LABEL, 'small_case'), 26 * SIZE * scale, True) + 60 * SIZE * scale)
    H = fs * .96 + ((39 if lab else 0) + 2 * (18 if spot == 'above' else 34)) * SIZE * scale
    return round(W), round(H), round(fs)


def money(v):
    return f'{CURRENCY}{int(v):,}'


def receipts():
    """the receipt list with the defaults filled in"""
    out = []
    for r in (RECEIPTS if RECEIPTS_ON else []):
        d = dict(r) if isinstance(r, dict) else {'at': r}
        d.setdefault('title', RECEIPT_TITLE)
        d.setdefault('item', RECEIPT_ITEM)
        d.setdefault('amount', RECEIPT_AMOUNT)
        if int(d['amount']) != d['amount'] or d['amount'] < 0:
            sys.exit(f'receipt amount {d["amount"]!r}: whole numbers only')
        out.append(d)
    if len(out) > 8:
        sys.exit('more than 8 receipts: the piles would cover the speaker. Use 8 or fewer')
    return out


def ats():
    """every 'at' value of the CLIP block (words or frames) that prep.py has to turn into a frame"""
    v = [t['at'] for t in TILES] + [t['knock'] for t in TILES if t.get('knock') is not None]
    v += [r['at'] for r in receipts()]
    if RECEIPTS_ON:
        v += [x for x in (TOTAL_AT, TOTAL_TAG_AT, WIPE_AT) if x is not None]
    return v


def signature():
    """changes whenever something prep.py depends on changes: build.py refuses a layout made for other values"""
    blob = json.dumps([TILES, TILE_LABEL, RECEIPTS_ON, receipts(), CURRENCY, RECEIPT_FIRST_SIDE, TOTAL_AT, TOTAL_TAG,
                       TOTAL_TAG_AT, TOTAL_POS, WIPE_AT, F_IN, F_OUT, WALL, SPOTS, PILES, SIZE, SEED,
                       STYLE['order'], STYLE['name_case'], STYLE['small_case'], STYLE['width_factor'],
                       STYLE['name_tracking']], sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()[:12]


def schedule(at, nfr, spots=None):
    """frames of every beat. at = {str(word or frame): frame} from prep.py; spots = the wall spot of each tile once
    prep.py has placed them (a tile that reuses the spot of the one before is knocked 6 frames early)"""
    fr = lambda x: at[str(x)]
    rc = receipts()
    R = [fr(r['at']) for r in rc]
    L = [fr(t['at']) for t in TILES]
    if L != sorted(L) or len(set(L)) != len(L):
        sys.exit(f'tiles must land in spoken order on different frames (got {L})')
    K = []
    for i, t in enumerate(TILES):
        if t.get('knock') is not None:
            k = fr(t['knock'])
        elif i + 1 < len(L):
            k = L[i + 1] - (6 if spots and spots[i] == spots[i + 1] else 0)
        else:
            k = L[i] + 21
            if R:
                k = min(k, R[0] - 7)
        if k - L[i] < 9:
            sys.exit(f'tile "{t["text"]}" would be up for {k - L[i]} frames (lands f{L[i]}, knocked f{k}): it needs 9 '
                     'or more to be read. Drop a tile or move its "knock"')
        K.append(k)
    f_in = F_IN if F_IN is not None else L[0] - 5
    if f_in < 1 or L[0] - f_in < 5:
        sys.exit(f'the first tile lands on f{L[0]}: the slot must start at least 6 frames (0.2 s) before that word, '
                 'so its first frame is the plain clip')
    s = dict(land=L, knock=K, f_in=f_in, rec=R, total=None, tag=None, wipe=None)
    last = K[-1] + 9                               # the knocked tile is gone 6 to 7 frames after its knock
    if R:
        if R != sorted(R) or len(set(R)) != len(R) or R[0] < K[-1] + 5:
            sys.exit(f'receipts must land in order, after the last tile is knocked away (f{K[-1]}) plus 5 frames; got {R}')
        ev = R[-1]
        if TOTAL_AT is not None:
            s['total'] = fr(TOTAL_AT)
            ev = max(ev, s['total'] + 4 * sum(1 for x in R if x <= s['total']))
            if TOTAL_TAG:
                s['tag'] = fr(TOTAL_TAG_AT) if TOTAL_TAG_AT is not None else s['total'] + 8
                ev = max(ev, s['tag'] + 6)
        s['wipe'] = fr(WIPE_AT) if WIPE_AT is not None else ev + 24
        if s['wipe'] < ev + 8:
            sys.exit(f'WIPE_AT f{s["wipe"]} is too early: the last piece lands on f{ev}, give it 8 frames')
        last = s['wipe'] + 10
    s['f_out'] = F_OUT if F_OUT is not None else last
    if s['f_out'] < last:
        sys.exit(f'F_OUT {s["f_out"]} is too early: the last piece is gone on f{last}')
    if s['f_out'] > nfr - 2:
        sys.exit(f'the effect ends on f{s["f_out"]} but the slot has {nfr} frames: it needs {s["f_out"] + 2} or more '
                 '(the last frames must be the plain clip). Make the slot longer or move the beats earlier')
    return s


# ---------------------------------------------------------------- page pieces
def in_safe(x, y):
    return SAFE['left'] <= x <= (SAFE['right'] if y < SAFE['low_y'] else SAFE['right_low']) and SAFE['top'] <= y <= SAFE['bottom']


def burst_svg(W, H, color, cx, cy, rot):
    """impact ticks around a piece; ticks that would leave the safe zone are left out"""
    Ls, pad, s = [30, 18, 26, 16, 32, 20, 28, 16, 30, 18, 26, 20], 22, ''
    rx, ry, ca, sa = W / 2 + pad, H / 2 + pad, math.cos(math.radians(rot)), math.sin(math.radians(rot))
    for k in range(12):
        a = k / 12 * math.pi * 2 + .26
        c, sn = math.cos(a), math.sin(a)
        sc = 1 / (abs(c / rx) ** 4 + abs(sn / ry) ** 4) ** .25
        x1, y1, x2, y2 = c * sc, sn * sc, c * (sc + Ls[k]), sn * (sc + Ls[k])
        ex, ey = x2 * 1.16, y2 * 1.16
        if not in_safe(cx + ex * ca - ey * sa, cy + ex * sa + ey * ca):
            continue
        s += f'<line x1="{r1(x1)}" y1="{r1(y1)}" x2="{r1(x2)}" y2="{r1(y2)}"/>'
    w, h = W + 180, H + 180
    return (f'<svg width="{w}" height="{h}" viewBox="{-w / 2} {-h / 2} {w} {h}" style="position:absolute;left:{-w / 2}px;'
            f'top:{-h / 2}px;overflow:visible"><g stroke="{color}" stroke-width="5" stroke-linecap="round">{s}</g></svg>')


def strike_paths(kind, W, H):
    p = lambda a: ' '.join(str(r1(v)) if isinstance(v, float) else str(v) for v in a)
    if kind == 0:      # rising slash
        return (p(['M', -22, H * .82, 'C', W * .22, H * .72, ',', W * .4, H * .36, ',', W * .58, H * .44, 'S', W * .86, H * .15, ',', W + 22, H * .12]),
                p(['M', -12, H * .86, 'C', W * .25, H * .7, ',', W * .42, H * .42, ',', W * .6, H * .46, 'S', W * .84, H * .2, ',', W + 12, H * .16]))
    if kind == 1:      # falling slash
        return (p(['M', -22, H * .16, 'C', W * .24, H * .2, ',', W * .4, H * .64, ',', W * .6, H * .56, 'S', W * .88, H * .86, ',', W + 22, H * .88]),
                p(['M', -12, H * .12, 'C', W * .27, H * .24, ',', W * .42, H * .58, ',', W * .62, H * .54, 'S', W * .86, H * .8, ',', W + 12, H * .84]))
    return (p(['M', -24, H * .62, 'C', W * .2, H * .38, ',', W * .36, H * .68, ',', W * .55, H * .48, 'S', W * .86, H * .3, ',', W + 24, H * .4]),
            p(['M', -12, H * .66, 'C', W * .22, H * .44, ',', W * .38, H * .64, ',', W * .56, H * .52, 'S', W * .84, H * .36, ',', W + 12, H * .44]))


def strike_svg(k, W, H, d, d2, sw, outline, ids):
    i = (lambda s: f' id="sk-{k}-{s}"') if ids else (lambda s: '')
    red = STYLE['strike']
    under = (f'<path{i("u")} d="{d}" pathLength="1000" fill="none" stroke="rgba(14,15,18,.95)" stroke-width="{sw + 12}" stroke-linecap="round" stroke-linejoin="round"/>'
             if outline else
             f'<path{i("u")} d="{d}" pathLength="1000" fill="none" stroke="rgba(0,0,0,.42)" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" transform="translate(3 6)"/>')
    return (f'<svg class="strike{"" if ids else " done"}"' + (f' id="sk-{k}"' if ids else '') + f' width="{W}" height="{H}" viewBox="0 0 {W} {H}">{under}'
            f'<path{i("a")} d="{d}" pathLength="1000" fill="none" stroke="{red}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path{i("b")} d="{d2}" pathLength="1000" fill="none" stroke="{red}" stroke-opacity=".55" stroke-width="{round(sw * .3)}" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def tile_body(k, name, fs, sc, ident):
    lab = f'<div class="tlabel" style="font-size:{r1(26 * sc)}px;line-height:{r1(30 * sc)}px;margin-top:{r1(9 * sc)}px">{esc(cased(TILE_LABEL, "small_case"))}</div>' if TILE_LABEL else ''
    return (f'<div class="tbody"' + (f' id="tb-{k}"' if ident else '') + '><div class="sheen"></div><div class="edge"></div>'
            f'<div class="tname" style="font-size:{fs}px">{esc(cased(name, "name_case"))}</div>{lab}</div>')


def teeth(W):
    n, step, s = 12, W / 12, '0,0'
    for i in range(n):
        s += f' {r1(i * step + step / 2)},10 {r1((i + 1) * step)},0'
    return f'<svg class="teeth" width="{W}" height="10" viewBox="0 0 {W} 10"><polygon points="{s}" fill="{STYLE["paper"]}"/></svg>'


class Page:
    """html + GSAP lines. ft() is an explicit from/to tween that refuses to overlap another tween on the same
    property, so every frame can be seeked safely."""

    def __init__(self):
        self.html, self.sets, self.tw, self.busy = [], [], [], {}

    def add(self, s):
        self.html.append(s)

    def set(self, i, v):
        self.sets.append(f"gsap.set(E('{i}'),{json.dumps(v)});")

    def idle(self, i, props, t):
        return all(self.busy.get(f'{i}|{p}', -1) <= t + 1e-6 for p in props)

    def ft(self, i, t, d, a, b, ease='none'):
        if t < 0:
            sys.exit(f'internal: tween on {i} starts before the slot ({t:.3f})')
        for p in b:
            key = f'{i}|{p}'
            if self.busy.get(key, -1) > t + 1e-6:
                sys.exit(f'two moves overlap on {key} at {t:.3f}s: beats are too close together, space them out')
            self.busy[key] = t + d
        v = dict(b, duration=round(d, 3), ease=ease, immediateRender=False)
        self.tw.append(f"tl.fromTo(E('{i}'),{json.dumps(a)},{json.dumps(v)},{t:.3f});")

    def slam(self, sp, sh, t, rot, S=1.0, s0=1.5, d=.13, kick=9.0, far=FAR, near=NEAR, settle=.34):
        """flies in from the camera (big, soft far shadow), hits the wall at t, squashes, springs back"""
        self.ft(sp, t - d, .06, {'opacity': 0}, {'opacity': 1})
        self.ft(sp, t - d, d, {'scale': S * s0, 'rotation': rot + kick}, {'scale': S * .94, 'rotation': rot - kick * .22}, 'power3.in')
        self.ft(sp, t, settle, {'scale': S * .94, 'rotation': rot - kick * .22}, {'scale': S, 'rotation': rot}, 'elastic.out(1.15,0.42)')
        self.ft(sh, t - d, d, {'boxShadow': far}, {'boxShadow': near}, 'power3.in')

    def burst(self, i, t, rot, ln=.26):
        self.set(i, {'rotation': rot, 'opacity': 0})
        self.ft(i, t, ln, {'scale': .9}, {'scale': 1.16}, 'power3.out')
        self.ft(i, t, .03, {'opacity': 0}, {'opacity': 1})
        self.ft(i, t + .07, ln - .07, {'opacity': 1}, {'opacity': 0}, 'power1.in')

    def strike(self, k, t, d=.12):
        self.set(f'sk-{k}', {'opacity': 0})
        self.ft(f'sk-{k}', t, .001, {'opacity': 0}, {'opacity': 1})
        for s, off in (('u', 0), ('a', 0), ('b', .02)):
            self.ft(f'sk-{k}-{s}', t + off, d - off, {'strokeDashoffset': 1000}, {'strokeDashoffset': 0})


def fall(bottom, want):
    """how far a piece may fall before it would cross the bottom safe line (it has faded out by then)"""
    return max(120, min(want, SAFE['bottom'] - bottom - 6))


def build_tiles(P, lay, S):
    cx_head = lay['head']['cx']
    for k, (t, g) in enumerate(zip(TILES, lay['tiles'])):
        W, H, fs, cx, cy, rot, sc = g['w'], g['h'], g['fs'], g['x'], g['y'], g['rot'], g['scale'] * SIZE
        d, d2 = strike_paths(k % 3, W, H)
        ox = 0 if cx - W / 2 < SAFE['left'] + W * .27 else 100 if cx + W / 2 > SAFE['right'] - W * .27 else 50
        oy = 0 if cy - H / 2 < SAFE['top'] + H * .27 else 50
        box = f'width:{W}px;height:{H}px;margin:{-H / 2}px 0 0 {-W / 2}px;transform-origin:{ox}% {oy}%'
        ex = t.get('exit') or EXIT[g['spot']]
        away = -1 if cx < cx_head else 1
        streak = ''
        if ex == 'drop':
            streak = (f'<div class="streak" id="st-{k}" style="left:{-W * .42}px;top:{-H / 2 - 270}px;width:{W * .84}px;height:{270 + H / 2}px;'
                      'background:linear-gradient(to top,rgba(14,15,18,.6),rgba(14,15,18,0));transform-origin:50% 100%"></div>')
        elif ex == 'flick':
            # the trail sits on the side the tile comes from and is darkest at the tile
            streak = (f'<div class="streak" id="st-{k}" style="left:{-W / 2 - 300 if away > 0 else 0}px;top:{-H * .4}px;width:{300 + W / 2}px;height:{H * .8}px;'
                      f'background:linear-gradient(to {"left" if away > 0 else "right"},rgba(14,15,18,.6),rgba(14,15,18,0));'
                      f'transform-origin:{100 if away > 0 else 0}% 50%"></div>')
        P.add(f'<div class="burst" id="bu-{k}" style="left:{cx}px;top:{cy}px">{burst_svg(W, H, STYLE["tile_text"], cx, cy, rot)}</div>'
              f'<div class="mover" id="mv-{k}" style="left:{cx}px;top:{cy}px">{streak}'
              f'<div class="spin" id="sp-{k}" style="{box}">{tile_body(k, t["text"], fs, sc, True)}{strike_svg(k, W, H, d, d2, 16, False, True)}'
              + (f'<svg class="cracks" id="cr-{k}" width="{W}" height="{H}" viewBox="0 0 {W} {H}"></svg>' if ex == 'shatter' else '') + '</div></div>')
        tL, tK = F(S['land'][k]), F(S['knock'][k]) - .01
        P.set(f'sp-{k}', {'opacity': 0, 'rotation': rot})
        kick = (9, -9, 6)[k % 3]
        P.slam(f'sp-{k}', f'tb-{k}', tL, rot, s0=1.45 if g['spot'] == 'above' else 1.5, kick=kick, settle=max(.12, min(.34, tK - .13 - tL)))
        P.burst(f'bu-{k}', tL, rot)
        P.strike(k, tK - .12)
        tilt = rot + (4 if rot >= 0 else -4)
        if ex == 'shatter':
            build_shards(P, k, t, g, d, d2, box, tK)
            continue
        P.ft(f'sp-{k}', tK - .08, .08, {'rotation': rot}, {'rotation': tilt}, 'power2.out')
        if ex == 'drop':
            P.set(f'st-{k}', {'opacity': 0, 'scaleY': 0})
            P.ft(f'mv-{k}', tK, .18, {'y': 0}, {'y': fall(cy + H / 2, 900)}, 'power2.in')
            P.ft(f'mv-{k}', tK, .18, {'x': 0}, {'x': 46 * away}, 'power1.in')
            P.ft(f'sp-{k}', tK, .18, {'rotation': tilt}, {'rotation': tilt + 37 * away}, 'power1.in')
            P.ft(f'st-{k}', tK + .02, .10, {'scaleY': 0}, {'scaleY': 1}, 'power1.in')
            P.ft(f'st-{k}', tK + .02, .05, {'opacity': 0}, {'opacity': 1})
            P.ft(f'st-{k}', tK + .09, .08, {'opacity': 1}, {'opacity': 0})
            P.ft(f'sp-{k}', tK + .09, .08, {'opacity': 1}, {'opacity': 0})
        else:
            P.set(f'st-{k}', {'opacity': 0, 'scaleX': 0})
            P.ft(f'mv-{k}', tK, .16, {'x': 0}, {'x': 760 * away}, 'power1.in')
            P.ft(f'mv-{k}', tK, .16, {'y': 0}, {'y': -90 if cy - H > SAFE['top'] + 90 else 60}, 'power1.out')
            P.ft(f'sp-{k}', tK, .16, {'rotation': tilt}, {'rotation': tilt + 110 * away}, 'power1.in')
            P.ft(f'st-{k}', tK + .01, .08, {'scaleX': 0}, {'scaleX': 1}, 'power1.in')
            P.ft(f'st-{k}', tK + .01, .04, {'opacity': 0}, {'opacity': 1})
            P.ft(f'st-{k}', tK + .07, .06, {'opacity': 1}, {'opacity': 0})
            P.ft(f'sp-{k}', tK + .07, .06, {'opacity': 1}, {'opacity': 0})


def build_shards(P, k, t, g, d, d2, box, tK):
    W, H, fs, cx, cy, rot, sc = g['w'], g['h'], g['fs'], g['x'], g['y'], g['rot'], g['scale'] * SIZE
    C = (W * .47, H * .51)
    pts = [(W * .27, 0), (W * .66, 0), (W, H * .42), (W * .77, H), (W * .35, H), (0, H * .65)]
    polys = [[C, pts[0], pts[1]], [C, pts[1], (W, 0), pts[2]], [C, pts[2], (W, H), pts[3]],
             [C, pts[3], pts[4]], [C, pts[4], (0, H), pts[5]], [C, pts[5], (0, 0), pts[0]]]
    cracks = ''
    for i, p in enumerate(pts):
        mx, my = (C[0] + p[0]) / 2 + (9 if i % 2 else -8), (C[1] + p[1]) / 2 + (-6 if i % 3 else 7)
        cracks += f'<polyline points="{r1(C[0])},{r1(C[1])} {r1(mx)},{r1(my)} {r1(p[0])},{r1(p[1])}"/>'
    # the crack lines go into the tile's own (empty) svg by string replace: no runtime DOM work
    P.html[-1] = P.html[-1].replace(f'viewBox="0 0 {W} {H}"></svg>', f'viewBox="0 0 {W} {H}"><g fill="none" stroke="{STYLE["tile_text"]}" '
                                    f'stroke-opacity=".8" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">{cracks}</g></svg>')
    html = f'<div class="mover" id="mv-sh{k}" style="left:{cx}px;top:{cy}px"><div class="spin" id="sp-sh{k}" style="{box}">'
    geo = []
    for j, poly in enumerate(polys):
        gx, gy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
        dx, dy = gx - C[0], gy - C[1]
        ln = math.hypot(dx, dy) or 1
        geo.append((dx / ln, dy / ln))
        clip = ','.join(f'{r1(p[0])}px {r1(p[1])}px' for p in poly)
        html += (f'<div class="shard" id="sh-{k}-{j}" style="width:{W}px;height:{H}px;clip-path:polygon({clip});transform-origin:{r1(gx)}px {r1(gy)}px">'
                 f'{tile_body(k, t["text"], fs, sc, False)}{strike_svg(k, W, H, d, d2, 16, False, False)}</div>')
    P.add(f'<div class="burst" id="bu-sh{k}" style="left:{cx}px;top:{cy}px">{burst_svg(W + 30, H + 30, STYLE["strike"], cx, cy, rot)}</div>')
    P.add(html + '</div></div>')
    P.set(f'cr-{k}', {'opacity': 0})
    P.set(f'sp-sh{k}', {'opacity': 0, 'rotation': rot})
    P.ft(f'cr-{k}', tK - 1 / FPS, .001, {'opacity': 0}, {'opacity': 1})
    P.ft(f'sp-{k}', tK, .001, {'opacity': 1}, {'opacity': 0})
    P.ft(f'sp-sh{k}', tK, .001, {'opacity': 0}, {'opacity': 1})
    P.burst(f'bu-sh{k}', tK, rot, .18)
    room = fall(cy + H / 2, 272)
    for j, (ux, uy) in enumerate(geo):
        sgn = 1 if j % 2 else -1
        P.ft(f'sh-{k}-{j}', tK, .21, {'x': 0}, {'x': r1(ux * (250 + 34 * ((j * 3) % 4)))}, 'power2.out')
        P.ft(f'sh-{k}-{j}', tK, .21, {'y': 0}, {'y': r1(min(room, uy * 150 + 250 + 22 * (j % 3)))}, 'power1.in')
        P.ft(f'sh-{k}-{j}', tK, .21, {'rotation': 0}, {'rotation': sgn * (48 + 19 * j)}, 'power1.out')
        P.ft(f'sh-{k}-{j}', tK, .21, {'scale': 1}, {'scale': .82}, 'power1.in')
    P.ft(f'sp-sh{k}', tK + .12, .08, {'opacity': 1}, {'opacity': 0}, 'power1.in')


def build_receipts(P, lay, S):
    rc, ink, red = receipts(), STYLE['paper_ink'], STYLE['strike']
    G = lay['receipts']
    tot = lay.get('total')
    t_tot = F(S['total']) if S['total'] is not None else None
    # running total: which receipt is counted when
    counted, steps = {}, []
    if t_tot is not None:
        on_wall = [i for i, f in enumerate(S['rec']) if f <= S['total']]
        for n, i in enumerate(on_wall):
            counted[i] = t_tot + (.12 + .14 * (n - 1) if n else 0)
        for i, f in enumerate(S['rec']):         # later receipts are counted as they land, never faster than the catch-up
            if i not in counted:
                counted[i] = max([F(f)] + [v + .14 for v in counted.values()])
        run = 0
        if not on_wall:                          # the total lands on an empty wall: it starts at zero
            steps.append((t_tot, 0, -1))
        for i in sorted(counted, key=lambda i: counted[i]):
            run += rc[i]['amount']
            steps.append((counted[i], run, i))
    for i, (r, g) in enumerate(zip(rc, G)):
        sc = g['scale'] * SIZE
        W, H = round(RW * sc), round(RH * sc)
        title, item, amt = cased(str(r['title']), 'name_case'), cased(str(r['item']), 'small_case'), money(r['amount'])
        inner = W - 44 * sc
        tfs = min(38 * sc, 38 * sc * inner / max(1, text_w(title, 38 * sc)))
        rfs = min(30 * sc, inner / (.6 * (len(item) + len(amt) + 2)))
        late = t_tot is not None and S['rec'][i] > S['total']
        P.add(f'<div class="mover" id="mv-r{i}" style="left:{g["x"]}px;top:{g["y"]}px">'
              f'<div class="spin" id="sp-r{i}" style="width:{W}px;height:{H}px;margin:{-H / 2}px 0 0 {-W / 2}px">'
              f'<div class="paper" id="pp-r{i}" style="padding:{r1(14 * sc)}px {r1(22 * sc)}px 0 {r1(22 * sc)}px">'
              f'<div class="rhead" id="hd-r{i}" style="font-size:{r1(tfs)}px;line-height:{r1(40 * sc)}px;height:{r1(40 * sc)}px">{esc(title)}</div>'
              f'<div class="rrule" id="ru-r{i}" style="margin:{r1(9 * sc)}px 0 {r1(8 * sc)}px 0"></div>'
              f'<div class="rrow" style="font-size:{r1(rfs)}px;line-height:{r1(36 * sc)}px"><span class="ritem">{esc(item)}</span><span class="rdots"></span>'
              f'<span class="ramt" id="am-r{i}" style="color:{red if late else ink}">{esc(amt)}</span></div></div>{teeth(W)}</div></div>')
        P.set(f'sp-r{i}', {'opacity': 0, 'rotation': g['rot']})
        t = F(S['rec'][i])
        nxt = min([F(f) for f in S['rec'][i + 1:]] + [F(S['wipe'])])
        P.slam(f'sp-r{i}', f'pp-r{i}', t, g['rot'], s0=1.42, d=.12, kick=8 if g['side'] == 'left' else -8, far=PFAR, near=PNEAR,
               settle=max(.1, min(.34, nxt - t - .01)))
        for j in range(i):                       # the pile reacts: the one underneath loses its header, the rest wobble
            if G[j]['side'] != g['side']:
                continue
            if G[j]['slot'] == g['slot'] - 1:
                P.ft(f'hd-r{j}', t, .05, {'opacity': 1}, {'opacity': 0})
                P.ft(f'ru-r{j}', t, .05, {'opacity': 1}, {'opacity': 0})
            if P.idle(f'sp-r{j}', ['rotation'], t) and nxt - t > .23:
                amp = (1.2, -1.0, .8)[(i + j) % 3]
                P.ft(f'sp-r{j}', t, .22, {'rotation': G[j]['rot'] + amp}, {'rotation': G[j]['rot']}, 'elastic.out(1,0.4)')
    for i, tc in counted.items():
        if not (t_tot is not None and S['rec'][i] > S['total']):
            P.ft(f'am-r{i}', tc, .06, {'color': ink}, {'color': red})
        P.ft(f'am-r{i}', tc, .2, {'scale': 1.5}, {'scale': 1}, 'back.out(2)')
    tW = F(S['wipe'])
    if tot:
        build_total(P, tot, steps, t_tot, S, tW)
    dl, dxs, drs = [0, .02, .01, .03, .015, .025, .005, .02], [-150, 170, -90, 110, -210, 230, -60, 80], [-38, 44, 26, -30, -52, 58, 20, -24]
    for i, g in enumerate(G):
        t0, H, hw = tW + dl[i], RH * g['scale'] * SIZE, RW * g['scale'] * SIZE / 2
        dx = max(SAFE['left'] - (g['x'] - hw), min(dxs[i], SAFE['right'] - (g['x'] + hw)))     # it drifts, but stays in frame
        P.ft(f'mv-r{i}', t0, .25, {'y': 0}, {'y': fall(g['y'] + H / 2, 780)}, 'power2.in')
        P.ft(f'mv-r{i}', t0, .25, {'x': 0}, {'x': r1(dx)}, 'power1.out')
        if P.idle(f'sp-r{i}', ['rotation'], t0):
            P.ft(f'sp-r{i}', t0, .25, {'rotation': g['rot']}, {'rotation': g['rot'] + drs[i]}, 'power1.in')
        P.ft(f'sp-r{i}', tW + .19, .09, {'opacity': 1}, {'opacity': 0})


def build_total(P, tot, steps, t, S, tW):
    red, sc = STYLE['strike'], tot['scale'] * SIZE
    W, H, cx, cy = tot['w'], tot['h'], tot['x'], tot['y']
    vals = [money(v) for _, v, _ in steps]
    wid = max(len(v) for v in vals)
    vals = [v.rjust(wid) for v in vals]
    cell = r1(98 * sc)
    cols = ''
    for j in range(wid):
        chars = [v[j] for v in vals]
        narrow = all(c in ', ' for c in chars)
        text = all(not c.isdigit() for c in chars)
        w = r1((30 if narrow else 72) * sc)
        cells = ''.join(f'<div class="dg" style="height:{cell}px;line-height:{cell}px;font-size:{r1((86 if text else 100) * sc)}px">{esc(c) if c != " " else ""}</div>' for c in chars)
        cols += (f'<div class="slot{" bare" if text else ""}" style="width:{w}px;height:{cell}px;margin:0 {r1(3 * sc)}px">'
                 f'<div class="col" id="col-{j}" style="width:{w}px">{cells}</div></div>')
    d = ' '.join(str(v) for v in ['M', -30, r1(H * .88), 'C', r1(W * .2), r1(H * .78), ',', r1(W * .42), r1(H * .34), ',', r1(W * .6), r1(H * .44), 'S', r1(W * .88), r1(H * .2), ',', W + 30, r1(H * .16)])
    d2 = ' '.join(str(v) for v in ['M', -18, r1(H * .92), 'C', r1(W * .23), r1(H * .76), ',', r1(W * .44), r1(H * .4), ',', r1(W * .62), r1(H * .46), 'S', r1(W * .86), r1(H * .24), ',', W + 18, r1(H * .2)])
    tag = ''
    if TOTAL_TAG:
        tw_, th = tot['tag_w'], round(46 * sc)
        tag = (f'<div id="tagclip" style="left:{-tw_ / 2 - 14}px;top:{r1(H / 2 - 5 * sc)}px;width:{tw_ + 28}px;height:{th + 32}px"><div id="tag" style="left:14px;width:{tw_}px;'
               f'height:{th}px;font-size:{r1(30 * sc)}px;line-height:{th + 2}px">{esc(cased(TOTAL_TAG, "small_case"))}</div></div>')
    P.add(f'<div class="burst" id="bu-tot" style="left:{cx}px;top:{cy}px">{burst_svg(W, H, red, cx, cy, -1.5)}</div>'
          f'<div class="mover" id="mv-tot" style="left:{cx}px;top:{cy}px">{tag}'
          f'<div class="spin" id="sp-tot" style="width:{W}px;height:{H}px;margin:{-H / 2}px 0 0 {-W / 2}px;transform-origin:50% 0">'
          f'<div class="plate" id="pl-tot"><div class="sheen"></div><div class="edge"></div><div id="digits">{cols}</div></div>'
          f'{strike_svg("tot", W, H, d, d2, 20, True, True)}</div></div>')
    P.set('sp-tot', {'opacity': 0, 'rotation': -1.5})
    P.slam('sp-tot', 'pl-tot', t, -1.5, kick=6, s0=1.5)
    P.burst('bu-tot', t, -1.5)
    for n in range(1, len(steps)):
        ts = steps[n][0]
        gap = (steps[n + 1][0] if n + 1 < len(steps) else tW - .13) - ts
        dur = max(.08, min(.24, gap - .01))
        for j in range(wid):
            if vals[n][j] != vals[n - 1][j]:
                P.ft(f'col-{j}', ts, dur, {'y': r1(-cell * (n - 1))}, {'y': r1(-cell * n)}, 'back.out(1.6)' if dur > .13 else 'power2.out')
        P.ft('digits', ts, min(dur, .2), {'scale': 1.1 if n == len(steps) - 1 else 1.08}, {'scale': 1}, 'power2.out')
    if TOTAL_TAG:
        tt = F(S['tag'])
        P.set('tag', {'y': -62 * sc - 8, 'rotation': -1.5})
        P.set('tagclip', {'opacity': 0})      # its drop shadow would otherwise leak under the clip edge
        P.ft('tagclip', tt - .01, .001, {'opacity': 0}, {'opacity': 1})
        P.ft('tag', tt, .24, {'y': -62 * sc - 8}, {'y': 0}, 'back.out(2.1)')
        P.ft('tagclip', tW, .27, {'rotation': 0, 'x': 0}, {'rotation': -22, 'x': -40}, 'power1.in')
        P.ft('tagclip', tW + .19, .09, {'opacity': 1}, {'opacity': 0})
    P.strike('tot', tW - .12)
    P.ft('sp-tot', tW - .07, .07, {'rotation': -1.5}, {'rotation': -5}, 'power2.out')
    P.ft('mv-tot', tW, .27, {'y': 0}, {'y': fall(cy + H / 2, 560)}, 'power2.in')
    P.ft('sp-tot', tW, .27, {'rotation': -5}, {'rotation': 16}, 'power1.in')
    P.ft('sp-tot', tW + .19, .09, {'opacity': 1}, {'opacity': 0})


def probe(path, entries):
    ffp = shutil.which('ffprobe') or 'ffprobe'
    return subprocess.run([ffp, '-v', 'error', '-show_entries', entries, '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip()


def audio(S, lay, dur):
    if os.environ.get('SFX') == '0':
        return []
    snd = SOUNDS
    if snd == 'auto':
        snd = [('pop', f - 1, .15) for f in S['land']] + [('whoosh-short', f - 4, .10) for f in S['knock']]
        snd += [('pop', f - 1, .08) for f in S['rec']]
        if S['total'] is not None and lay.get('total'):
            snd.append(('impact-bass-1', S['total'] - 1, .15))
        if S['wipe'] is not None:
            snd.append(('whoosh-short', S['wipe'] - 1, .12))
    out, lanes = [], []
    for k, (name, frame, vol) in enumerate(sorted(snd, key=lambda x: x[1])):
        path = next((p for p in (f'assets/sfx/{name}.mp3', f'assets_fx/{name}.mp3') if os.path.exists(p)), None)
        if not path:
            print(f'  (sound {name} not found in assets/sfx: skipped)')
            continue
        t = F(frame)
        if t >= dur - .05:
            continue
        d = min(float(probe(path, 'format=duration')), dur - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def css():
    s = STYLE
    return f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000;color:{s['paper_ink']}}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:1}}
#wallfx{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:3}}
#fgwrap{{position:absolute;inset:0;z-index:5}}
.mover{{position:absolute;width:0;height:0}}
.spin{{position:absolute;left:0;top:0;transform-origin:50% 50%}}
.burst{{position:absolute;width:0;height:0}}
.streak{{position:absolute;border-radius:26px;filter:blur(5px)}}
.tbody{{position:absolute;left:0;top:0;right:0;bottom:0;border-radius:{s['radius']}px;background:{s['tile_bg']};
  border:1.5px solid rgba(247,244,238,.34);overflow:hidden;box-shadow:{NEAR};
  display:flex;flex-direction:column;align-items:center;justify-content:center}}
.sheen{{position:absolute;left:0;top:0;right:0;bottom:0;
  background:linear-gradient(152deg,rgba(255,255,255,.17) 0%,rgba(255,255,255,.05) 36%,rgba(255,255,255,0) 36.4%,rgba(255,255,255,0) 100%)}}
.edge{{position:absolute;left:0;top:0;right:0;height:2px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.5),rgba(255,255,255,0))}}
.tname{{position:relative;font-family:'{s['name_font']}',sans-serif;font-weight:{s['name_weight']};color:{s['tile_text']};letter-spacing:{s['name_tracking']}em;line-height:.96;white-space:nowrap}}
.tlabel{{position:relative;font-family:'{s['small_font']}',monospace;font-weight:{s['small_weight']};color:{s['label_color']};white-space:nowrap}}
.strike,.cracks{{position:absolute;left:0;top:0;overflow:visible}}
.strike path{{stroke-dasharray:1000;stroke-dashoffset:1000}}
.strike.done path{{stroke-dashoffset:0}}
.shard{{position:absolute;left:0;top:0}}
.paper{{position:absolute;left:0;top:0;right:0;bottom:10px;background:{s['paper']};border-radius:9px 9px 0 0;box-shadow:{PNEAR};overflow:hidden}}
.paper:after{{content:"";position:absolute;left:0;right:0;bottom:0;height:46px;background:linear-gradient(180deg,rgba(14,15,18,0),rgba(14,15,18,.055))}}
.teeth{{position:absolute;left:0;bottom:0;display:block}}
.rhead{{font-family:'{s['name_font']}',sans-serif;font-weight:{s['name_weight']};letter-spacing:-.015em;color:{s['paper_ink']};white-space:nowrap}}
.rrule{{height:0;border-top:2.5px dashed rgba(14,15,18,.32)}}
.rrow{{position:relative;display:flex;align-items:center;font-family:'{s['small_font']}',monospace;font-weight:{s['small_weight']};color:{s['paper_ink']};white-space:nowrap}}
.ritem{{display:inline-block}}
.rdots{{display:block;flex:1;height:0;margin:8px 9px 0 9px;border-top:3px dotted rgba(14,15,18,.4)}}
.ramt{{display:inline-block;-webkit-text-stroke:.9px currentColor;transform-origin:100% 55%}}
.plate{{position:absolute;left:0;top:0;right:0;bottom:0;border-radius:{max(0, s['radius'] - 2)}px;background:{s['tile_bg']};
  border:1.5px solid rgba(247,244,238,.34);overflow:hidden;box-shadow:{NEAR}}}
#digits{{position:absolute;left:0;top:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;transform-origin:50% 50%}}
.slot{{position:relative;overflow:hidden;border-radius:13px;background:rgba(247,244,238,.07)}}
.slot.bare{{background:none}}
.slot:after{{content:"";position:absolute;left:0;top:0;right:0;bottom:0;
  background:linear-gradient(180deg,rgba(0,0,0,.62) 0%,rgba(0,0,0,0) 24%,rgba(0,0,0,0) 76%,rgba(0,0,0,.62) 100%)}}
.slot.bare:after{{display:none}}
.col{{position:absolute;left:0;top:0}}
.dg{{text-align:center;font-family:'{s['name_font']}',sans-serif;font-weight:{s['name_weight']};color:{s['strike']}}}
#tagclip{{position:absolute;overflow:hidden;transform-origin:50% 0}}
#tag{{position:absolute;top:0;background:{s['paper']};border-radius:0 0 9px 9px;box-shadow:0px 8px 16px 0px rgba(0,0,0,0.4);
  font-family:'{s['small_font']}',monospace;font-weight:{s['small_weight']};text-align:center;color:{s['paper_ink']};white-space:nowrap;transform-origin:50% 0}}
'''


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the duration UP to whole frames
    if not os.path.exists('work/layout.json'):
        sys.exit('work/layout.json is missing: run prep.py first (see effect.md)')
    lay = json.load(open('work/layout.json'))
    if lay.get('sig') != signature() or lay.get('frames') != nfr:
        sys.exit('the CLIP block (or the clip) changed since prep.py ran: run prep.py again, look at work/layout.jpg, then build')
    S = schedule(lay['at'], nfr, [g['spot'] for g in lay['tiles']])
    P = Page()
    build_tiles(P, lay, S)
    if lay.get('receipts'):
        build_receipts(P, lay, S)
    t_in, t_out = F(S['f_in']), F(S['f_out'])
    late = max(P.busy.values())
    if late > t_out + 1e-6:
        sys.exit(f'internal: a move runs to {late:.3f}s, past F_OUT ({t_out:.3f}s)')
    # the wall layer and the cutout layer only exist between F_IN and F_OUT: outside, the frame is the untouched clip
    P.sets += ["gsap.set(['#wallfx','#fgwrap'],{autoAlpha:0});",
               f"tl.set(['#wallfx','#fgwrap'],{{autoAlpha:1}},{t_in:.3f});",
               f"tl.set(['#wallfx','#fgwrap'],{{autoAlpha:0}},{t_out:.3f});"]
    nl = '\n'
    voice = (f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css()}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1080" data-height="1920">
  {voice}
{nl.join(audio(S, lay, dur))}
  <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
  <div id="wallfx">
{nl.join(P.html)}
  </div>
  <div id="fgwrap"><video id="fg" class="full" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div>
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
function E(id) {{ const el = document.getElementById(id); if (!el) throw new Error('missing #' + id); return el; }}
{nl.join(P.sets)}
{nl.join(P.tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    name = os.path.basename(HERE)
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  effect on f{S["f_in"]} to f{S["f_out"]}  (plain clip before and after)')
    for k, (t, g) in enumerate(zip(TILES, lay['tiles'])):
        print(f'  tile {k + 1} "{t["text"]}"  lands f{S["land"][k]}  knocked f{S["knock"][k]}  {g["spot"]:5s} {t.get("exit") or EXIT[g["spot"]]:7s} size {g["scale"]:.2f}')
    for i, f in enumerate(S['rec']):
        print(f'  receipt {i + 1} lands f{f}  {lay["receipts"][i]["side"]}')
    if S['total'] is not None and lay.get('total'):
        print(f'  total lands f{S["total"]}' + (f', tag f{S["tag"]}' if S['tag'] is not None else '') + f', final {money(sum(r["amount"] for r in receipts()))}')
    if S['wipe'] is not None:
        print(f'  pile struck and falls f{S["wipe"]}')
    snaps = sorted({S['f_in'] - 1, *[f + 3 for f in S['land']], *[f - 2 for f in S['knock']], *[f + 3 for f in S['rec'][-1:]],
                    *([S['wipe'] - 6] if S['wipe'] is not None else []), S['f_out']})
    print('snapshot times: ' + ','.join(f'{(f + .5) / FPS:.3f}' for f in snaps if 0 <= f < nfr))
    used = [t['text'] for t in TILES] + ([RECEIPT_TITLE, RECEIPT_ITEM] if RECEIPTS_ON else [])
    if any(u in PLACEHOLDERS for u in used):
        print('WARNING: placeholder text is still in the CLIP block. Use the names (and amounts) the speaker says.')
    for w in lay.get('warnings', []):
        print('WARNING (layout):', w)
    print(f'render to renders/{name}.mp4')


if __name__ == '__main__':
    main()
