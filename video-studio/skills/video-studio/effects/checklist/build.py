#!/usr/bin/env python3
"""checklist: a checklist card builds on screen and every row ticks on the word the speaker says.

  card      dark glass (steady camera) or opaque (moving camera), 2 to 5 rows, sized and placed from measurements
  rows      start as an empty ring + a skeleton bar; the row's text lands when the speaker starts the phrase, the check
            draws + pops on the word that finishes it, a focus bar glides from row to row
  progress  segmented bar + a rolling "N of N" counter in the header
  finish    counter pill fills yellow, a sheen crosses the card, a soft yellow edge glow stays on; optional exit

Run order (from the slot folder, see effect.md):
  python3 onsets.py                                         word onsets from the audio -> frames for the CLIP block
  PY prep.py       measures camera drift + where the speaker is -> work/prep.json
  SAFE=1 python3 build.py                                   index.html with the red safe-zone guide (snapshots only)
  python3 build.py                                          index.html for the render
Switches: SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted (this effect has no captions of its own).
"""
import html as html_mod
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
NAME = os.path.basename(HERE)

# ==== CLIP (edit this) ====
# Frames are 30 fps frames of assets/aroll.mp4 (frame 0 = first frame of the slot). Get them from `python3 onsets.py`.
TITLE = 'All you need to do'       # eyebrow line, shown in caps. Use words the speaker says in the clip. Keep it under ~22 characters.
ROWS = [                           # 2 to 5 rows: (text, f_say, f_tick). *word* = yellow accent word.
    # f_say  = frame the speaker STARTS the phrase (the row's text lands): onsets.py column "say"
    # f_tick = frame the check starts drawing, one frame before the stressed vowel of the word that
    #          finishes the phrase: onsets.py column "tick"
    ('Drop your clips',        28, 39),
    ('Trigger the skill',      55, 69),
    ('*Claude* does the rest', 83, 97),
]
F_IN = 2            # frame the card starts building. First frame of speech, or ~20 frames before the first f_say.
F_DONE = 108        # frame the card completes (pill, sheen, glow). A stressed word 8+ frames after the last tick, or None = last tick + 10.
F_OUT = None        # frame the card leaves (whips off in ~7 frames), or None = it stays to the end of the slot.
CARD_BOX = 'auto'   # 'auto' = largest room the speaker leaves free while the card is up (work/prep.json), or (x, y, w, h) px the card must fit inside.
LAYER = 'auto'      # 'behind' = between the room and the speaker's cutout (the speaker overlaps it), 'front' = over the speaker, 'auto' = behind unless front is clearly larger.
OVERLAP = 40        # px the card may tuck behind the top of the speaker's head when it sits above the speaker ('behind' only). 0 = keep clear.
GLASS = 'auto'      # 'auto' = glass when prep.py says the camera is steady, else opaque. Or force 'glass' / 'opaque'.
ACCENT = '#FAE67A'  # tick, bar and accent-word colour (the house butter yellow). Never orange.
GRADE = ''          # CSS filter on the footage. '' = leave it (the main reel grades the slot). Standalone clip: 'contrast(1.05) saturate(.95) brightness(.99)'
VIGNETTE = 0        # 0 to .4 edge darkening. 0 inside a reel that has its own vignette. Standalone clip: .30
PUSH = 1.0          # slow push-in across the slot (1.0 = none). Only above 1.0 (demo: 1.03) on a locked-off shot that does not cut back to plain a-roll.
KEEP_OUT = []       # [(x0, y0, x1, y1), ...] px rects the main reel uses (its label pill, its caption band): the card never enters them.
# ==== END CLIP ====

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
CREAM, INK = '#FFF8EF', '#14161C'
SAFE_ON = bool(os.environ.get('SAFE')) and os.environ.get('SAFE') != '0'
SFX_ON = os.environ.get('SFX', '1') != '0'
if os.environ.get('GRADE') == '0':             # GRADE=0: the main reel grades the slot, whatever the CLIP block says
    GRADE, VIGNETTE = '', 0
WARN = []


def warn(msg):
    WARN.append(msg)


# ---------------------------------------------------------------- the slot
if os.path.exists('clip.json'):
    N = int(json.load(open('clip.json'))['frames'])
else:
    N = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                            'stream=nb_read_frames', '-of', 'csv=p=0', 'assets/aroll.mp4'], capture_output=True, text=True).stdout)
DUR = N / 30 - .001      # 1 ms short on purpose: the renderer rounds the duration UP to whole frames (179/30 written
#                          as 5.9667 rendered 180 frames). check.py verifies the count.
HAS_CUT = os.path.exists('assets/subject.webm')
PREP = json.load(open('work/prep.json')) if os.path.exists('work/prep.json') else None
if PREP is None and (CARD_BOX == 'auto' or LAYER == 'auto' or GLASS == 'auto'):
    sys.exit('work/prep.json is missing: run  PY prep.py  first '
             '(or set CARD_BOX, LAYER and GLASS by hand in the CLIP block)')
HEAD = PREP.get('head') if PREP else None


def F(n):
    """time of frame n, nudged 2ms early so a tl.set lands ON that frame"""
    return max(0.0, n / 30 - .002)


# ---------------------------------------------------------------- checks on the CLIP block
n_rows = len(ROWS)
if not 2 <= n_rows <= 5:
    sys.exit(f'ROWS has {n_rows} rows: the card takes 2 to 5')
if F_DONE is None:
    F_DONE = ROWS[-1][2] + 10
prev_say, prev_tick = F_IN, F_IN
for text, f_say, f_tick in ROWS:
    # f_say may come before the previous tick (silent b-roll: all the text up front, then the ticks in a run);
    # the focus bar then follows the ticks instead of the says
    if prev_tick != F_IN and f_tick - prev_tick < 6:
        sys.exit(f'row "{text}": ticks need 6+ frames between them (f_tick {f_tick} after {prev_tick})')
    if not (prev_say <= f_say < f_tick and prev_tick < f_tick):
        sys.exit(f'row "{text}": frames must rise: f_say {f_say} >= previous f_say {prev_say}, f_tick {f_tick} > f_say '
                 f'and > previous f_tick {prev_tick}')
    prev_say, prev_tick = f_say, f_tick
if F_DONE < ROWS[-1][2] + 5 or F_DONE >= N:
    sys.exit(f'F_DONE {F_DONE} must sit 5+ frames after the last tick ({ROWS[-1][2]}) and inside the slot ({N} frames). '
             'The CLIP block still holds another clip\'s frames? Run onsets.py and fill it in.')
if F_OUT is not None and not (F_DONE + 8 <= F_OUT <= N - 4):
    sys.exit(f'F_OUT {F_OUT} must be 8+ frames after F_DONE ({F_DONE}) and 4+ frames before the end ({N}); the exit takes 7 frames')
if F_OUT is None and N - F_DONE < 12:
    warn(f'only {N - F_DONE} frames after F_DONE: the completion beat needs about 15 to read')
for s in [TITLE] + [r[0] for r in ROWS]:
    if '\u2014' in s or '–' in s:
        sys.exit(f'"{s}": no dashes in on-screen text (a rule of this skill)')
    if any(w.strip('*.,!?').lower() in ('free', 'course') for w in s.split()):
        sys.exit(f'"{s}": the words "free" and "course" never go on screen (a rule of this skill)')

# ---------------------------------------------------------------- card geometry in card units (scaled by K to the screen)
NARROW = any('|' in s for s in [TITLE] + [r[0] for r in ROWS])   # a '|' line break says: this card lives in a narrow column
PADX = 34 if NARROW else 46                    # narrow cards trade padding for text size
TITLE_LINES = TITLE.split('|')                 # 'To use|these effects' = two eyebrow lines (narrow cards)
EB_LH = 34
HEAD_X = EB_LH * (len(TITLE_LINES) - 1)        # extra header height for a second eyebrow line
HEAD_H = 152 + HEAD_X                          # eyebrow + counter pill + segmented bar
PITCH = {2: 150, 3: 144, 4: 128, 5: 118}[n_rows]
BOX = min(64 if NARROW else 76, PITCH - 50)    # check circle
FS = 62 if PITCH >= 128 else 58                # row font size
RAD = 46
TEXT_L = PADX + BOX + (22 if NARROW else 30)
W_PREF = 880
# glyph advances in em (PIL on the bundled woff2). Inter Tight 800 renders 11% wider in Chrome than the table
# (measured on the demo render), Montserrat 600 matches.
IT = {' ': .234, '!': .25, '"': .415, '#': .584, '$': .591, '%': .766, '&': .592, "'": .249, '(': .313, ')': .313, '*': .453,
      '+': .613, ',': .251, '-': .412, '.': .238, '/': .31, '0': .578, '1': .355, '2': .559, '3': .59, '4': .595, '5': .556,
      '6': .568, '7': .515, '8': .566, '9': .568, ':': .238, ';': .251, '?': .46, '@': .889, 'A': .629, 'B': .603, 'C': .681,
      'D': .671, 'E': .55, 'F': .54, 'G': .696, 'H': .692, 'I': .216, 'J': .495, 'K': .605, 'L': .515, 'M': .845, 'N': .706,
      'O': .715, 'P': .587, 'Q': .715, 'R': .592, 'S': .591, 'T': .594, 'U': .693, 'V': .629, 'W': .909, 'X': .595, 'Y': .619,
      'Z': .578, 'a': .518, 'b': .561, 'c': .514, 'd': .561, 'e': .532, 'f': .314, 'g': .562, 'h': .546, 'i': .19, 'j': .19,
      'k': .497, 'l': .191, 'm': .824, 'n': .54, 'o': .549, 'p': .561, 'q': .561, 'r': .325, 's': .475, 't': .316, 'u': .535,
      'v': .51, 'w': .766, 'x': .493, 'y': .51, 'z': .494}
IT_CAL = 1.11
MO = {' ': .25, '!': .242, '&': .634, "'": .184, ',': .182, '-': .38, '.': .182, '/': .3, '0': .652, '1': .342, '2': .555,
      '3': .548, '4': .644, '5': .548, '6': .592, '7': .57, '8': .624, '9': .592, ':': .182, '?': .554, 'A': .688, 'B': .748,
      'C': .701, 'D': .826, 'E': .668, 'F': .629, 'G': .774, 'H': .816, 'I': .286, 'J': .477, 'K': .693, 'L': .58, 'M': .956,
      'N': .816, 'O': .836, 'P': .71, 'Q': .836, 'R': .716, 'S': .601, 'T': .548, 'U': .794, 'V': .67, 'W': 1.08, 'X': .621,
      'Y': .61, 'Z': .639}


def row_width(text):
    """px width of a row at FS (words are flex items with a .24em gap, tracking -.028em)"""
    words = [w.strip('*') for w in text.split(' ')]
    em = sum(sum(IT.get(c, .6) for c in w) * IT_CAL - .028 * len(w) for w in words) + .24 * (len(words) - 1)
    return em * FS


def eyebrow_width(text):
    return sum(MO.get(c, .75) + .17 for c in text.upper()) * 26


LH = round(FS * 1.06)                          # line height of a row line
ROW_LINES = [r[0].split('|') for r in ROWS]    # 'Drop the clips|into *Claude*' = a two-line row (narrow cards)
ROW_W = [max(row_width(l) for l in lines) for lines in ROW_LINES]
ROW_H = [PITCH if len(lines) == 1 else PITCH + (len(lines) - 1) * LH - 28 for lines in ROW_LINES]
ROW_TOP = [HEAD_H + sum(ROW_H[:k]) for k in range(n_rows)]
HEADER_NEED = PADX + 13 + 16 + max(eyebrow_width(l) for l in TITLE_LINES) + 28 + 140 + (PADX - 6)
W0 = max(TEXT_L + max(ROW_W) + PADX + 4, HEADER_NEED, 520)      # narrowest the card can be, in card units


def h0(pad_b):
    return HEAD_H + sum(ROW_H) + pad_b


PAD_PLAIN = 36
PAD_CAP = 25 + OVERLAP                         # empty band at the bottom where the speaker's cap pokes in

# ---------------------------------------------------------------- where the card goes
SAFE_T, SAFE_B, SAFE_L, SAFE_R, SAFE_R_LOW, SAFE_LOW_Y = 220, 1470, 35, 1045, 980, 1155
OCC_T = 15                                     # a cell the speaker covers in more than 15% of the frames is taken
OX, OY = 540, 1920 * .49                       # stage transform origin (the push-in scales about it)
P_POP = 1 + (PUSH - 1) * min(1, (F_DONE + 4) / N)      # how far the push-in has got when the card pops at F_DONE
# the rect a card may occupy at rest so that it is still inside the safe zone at its largest (pop + tilt + float, pushed in)
IN_T = max(OY - (OY - SAFE_T) / P_POP + 18, OY - (OY - SAFE_T) / PUSH + 10)
IN_B = min(OY + (SAFE_B - OY) / P_POP - 12, OY + (SAFE_B - OY) / PUSH - 3)
IN_L = OX - (OX - SAFE_L) / PUSH + 18
IN_R = OX + (SAFE_R - OX) / PUSH - 18
IN_R_LOW = OX + (SAFE_R_LOW - OX) / PUSH - 18
IN_LOW_Y = OY + (SAFE_LOW_Y - OY) / PUSH - 12


# ---- where the speaker is WHILE THE CARD IS UP (frames F_IN..F_OUT), and on the beats that must read (says, ticks, done)
F_END = F_OUT if F_OUT is not None else N - 1
VIS = range(F_IN, F_END + 1)
KEYS = set(range(F_DONE, F_DONE + 13))
for _r in ROWS:
    KEYS.update(range(_r[1], _r[1] + 9))
    KEYS.update(range(_r[2] - 2, _r[2] + 13))
KEYS = [f for f in sorted(KEYS) if F_IN <= f <= F_END]
GRID = PREP['grid'] if PREP else None
OCC = KEY_ANY = MASKS = None
if GRID:
    CELL, GW, GH = GRID['cell'], GRID['w'], GRID['h']
    OCC = GRID['occ']
    KEY_ANY = [[0] * GW for _ in range(GH)]
    _mp = os.path.join('work', GRID.get('masks', ''))
    if GRID.get('masks') and os.path.exists(_mp) and os.path.getsize(_mp) == N * GW * GH:
        MASKS = open(_mp, 'rb').read()
        _sz = GW * GH
        _cnt, _any = [0] * _sz, bytearray(_sz)
        for f in VIS:
            fr = MASKS[f * _sz:(f + 1) * _sz]
            for i in range(_sz):
                if fr[i]:
                    _cnt[i] += 1
        for f in KEYS:
            fr = MASKS[f * _sz:(f + 1) * _sz]
            for i in range(_sz):
                if fr[i]:
                    _any[i] = 1
        OCC = [[round(100 * _cnt[cy * GW + cx] / len(VIS)) for cx in range(GW)] for cy in range(GH)]
        KEY_ANY = [[_any[cy * GW + cx] for cx in range(GW)] for cy in range(GH)]
HV = None                                      # the speaker's head over the visible frames only
if HEAD:
    tops = [HEAD['tops'][f] for f in VIS] if HEAD.get('tops') else [HEAD['top_min'], HEAD['top_max']]
    cxs = [HEAD['cxs'][f] for f in VIS] if HEAD.get('cxs') else [HEAD['cx_min'], HEAD['cx_max']]
    hw = HEAD['w']
    HV = dict(top_min=min(tops), top_max=max(tops), cx_min=min(cxs), cx_max=max(cxs), w=hw, chin_max=max(tops) + 1.38 * hw,
              face_box=[max(0, min(cxs) - .55 * hw - 16), max(0, min(tops) - 16), min(1080, max(cxs) + .55 * hw + 16),
                        min(1920, max(tops) + 1.38 * hw + 16)])


def covered(x, y, w, h, frames):
    """largest share of the rect the speaker covers in any of the given frames (0..1), from the per-frame grid"""
    if not MASKS or w <= 0 or h <= 0:
        return 0.0
    cx0, cx1 = max(0, int(x // CELL)), min(GW, int(-(-(x + w) // CELL)))
    cy0, cy1 = max(0, int(y // CELL)), min(GH, int(-(-(y + h) // CELL)))
    area = max(1, (cx1 - cx0) * (cy1 - cy0))
    worst = 0
    for f in frames:
        base = f * GW * GH
        c = sum(sum(MASKS[base + cy * GW + cx0:base + cy * GW + cx1]) for cy in range(cy0, cy1))
        worst = max(worst, c)
    return worst / area


def above_head(x0, x1, y1):
    if not (HV and OVERLAP > 0):
        return False
    hx0, hx1 = HV['cx_min'] - HV['w'] / 2, HV['cx_max'] + HV['w'] / 2
    return x0 < hx1 and x1 > hx0 and HV['top_min'] - 14 <= y1 <= HV['top_min'] + OVERLAP + 26


def fit(x0, y0, x1, y1, layer):
    """Fit the card into a free rect (px). Returns dict(K, kraw, x, y, w, h, pad_b, wn)."""
    rw, rh = x1 - x0, y1 - y0
    cap = layer == 'behind' and above_head(x0, x1, y1)
    pad_b = PAD_CAP if cap else PAD_PLAIN
    H0 = h0(pad_b)
    kraw = min(rw / W0, rh / H0)
    K = min(1.0, kraw)
    wn = min(max(W0, W_PREF), rw / K)
    w, h = wn * K, H0 * K
    x = x0 + (rw - w) / 2
    if cap:
        y = y1 - h                                            # sit on the speaker's head
    elif HV and y0 >= HV['chin_max'] - 10:
        y = y0                                                # under the speaker's chin: hug the top
    elif HV and y1 > HV['top_min'] and y0 < HV['chin_max']:
        fc = (HV['top_min'] + HV['chin_max']) / 2             # beside the speaker's face: centre on it
        y = min(max(fc - h / 2, y0), y1 - h)
    else:
        y = y0 + (rh - h) / 2
    return dict(K=K, kraw=kraw, x=x, y=y, w=w, h=h, pad_b=pad_b, wn=wn, cap=cap, layer=layer)


def search(layer, tuck=False):
    """largest free room for the card on the 10 px occupancy grid of prep.py.
    tuck=True looks only for the spot above their head, where the card may slide OVERLAP px behind their cap."""
    cell, occ, key_any = CELL, OCC, KEY_ANY
    fb = HV['face_box'] if HV else None
    ov = OVERLAP // cell if (layer == 'behind' and tuck) else 0
    if tuck and not (ov and fb):
        return None
    blocked = [[False] * GW for _ in range(GH)]
    for cy in range(GH):
        ya, yb = cy * cell, cy * cell + cell
        for cx in range(GW):
            xa, xb = cx * cell, cx * cell + cell
            if layer == 'front':
                taken = bool(fb) and xa < fb[2] and xb > fb[0] and ya < fb[3] and yb > fb[1]
            else:
                o, kk = occ[cy][cx], key_any[cy][cx]
                if ov and fb and xa < fb[2] and xb > fb[0] and cy - ov >= 0:
                    o = min(o, occ[cy - ov][cx])              # let the card tuck OVERLAP px behind the top of the speaker's head
                    kk = min(kk, key_any[cy - ov][cx])
                taken = o >= OCC_T or bool(kk)                # never behind the speaker on a tick, whatever the average says
            # zones of the main reel, grown by the room the card needs when it pops (18 px up/down, 14 px sideways)
            blocked[cy][cx] = taken or any(xa < z[2] + 14 and xb > z[0] - 14 and ya < z[3] + 18 and yb > z[1] - 14
                                           for z in KEEP_OUT)

    def clipped(r):
        """the free rect cut down to the safe zone; where it crosses the right-hand icon column, both ways of avoiding it"""
        x0, y0, x1, y1 = max(r[0], IN_L), max(r[1], IN_T), min(r[2], IN_R), min(r[3], IN_B)
        if y1 > IN_LOW_Y and x1 > IN_R_LOW:
            return [(x0, y0, IN_R_LOW, y1), (x0, y0, x1, IN_LOW_Y)]
        return [(x0, y0, x1, y1)]

    best, heights = None, [0] * GW
    for cy in range(GH):
        for cx in range(GW):
            heights[cx] = 0 if blocked[cy][cx] else heights[cx] + 1
        stack = []
        for cx in range(GW + 1):
            hh = heights[cx] if cx < GW else 0
            start = cx
            while stack and stack[-1][1] >= hh:
                sx, sh = stack.pop()
                if sh > 0:
                    for r in clipped((sx * cell, (cy - sh + 1) * cell, cx * cell, (cy + 1) * cell)):
                        if r[2] - r[0] >= 300 and r[3] - r[1] >= 240:
                            f = fit(*r, layer)
                            if tuck != f['cap']:
                                continue
                            key = (round(f['K'], 2), round(min(f['kraw'], 1.3), 1), (r[2] - r[0]) * (r[3] - r[1]))
                            if best is None or key > best[0]:
                                best = (key, f)
                start = sx
            stack.append((start, hh))
    return best[1] if best else None


if CARD_BOX == 'auto':
    layers = ['behind', 'front'] if LAYER == 'auto' else [LAYER]
    cands = ([search('behind', True), search('behind', False)] if 'behind' in layers and HAS_CUT else []) + \
            ([search('front')] if 'front' in layers else [])
    cands = [c for c in cands if c]
    if not cands:
        sys.exit('no free room found for the card: set CARD_BOX = (x, y, w, h) by hand')
    CARD = max(cands, key=lambda c: (c['K'] + (.08 if c['layer'] == 'behind' else 0), c['kraw']))   # prefer depth
else:
    bx, by, bw, bh = CARD_BOX
    layer = LAYER if LAYER != 'auto' else ('behind' if HAS_CUT else 'front')
    CARD = fit(bx, by, bx + bw, by + bh, layer)
if CARD['layer'] == 'behind' and not HAS_CUT:
    sys.exit('LAYER "behind" needs assets/subject.webm (their cutout). Use LAYER = "front" or make the cutout.')
K, CX, CY, CW, CH = CARD['K'], round(CARD['x']), round(CARD['y']), round(CARD['w']), round(CARD['h'])
WN, PAD_B, H0 = CARD['wn'], CARD['pad_b'], h0(CARD['pad_b'])
if K < .6:
    warn(f'card scale {K:.2f}: row text is only {FS * K:.0f} px tall on screen. Shorten the rows, use fewer rows, or pick another shot')
for z in KEEP_OUT:
    if CX < z[2] and CX + CW > z[0] and CY - 12 < z[3] and CY + CH + 8 > z[1]:
        warn(f'card {CX},{CY} {CW}x{CH} (plus its pop) enters the keep-out zone {z}. Move CARD_BOX')
COVER_KEY = COVER_VIS = 0.0
if CARD['layer'] == 'front' and HV:
    fb = [round(v) for v in HV['face_box']]
    if min(CX + CW, fb[2]) > max(CX, fb[0]) and min(CY + CH, fb[3]) > max(CY, fb[1]):
        warn(f'card {CX},{CY} {CW}x{CH} crosses their face box {fb} while it is up: a front card may never cover their face. Move CARD_BOX')
elif CARD['layer'] == 'behind':
    body_h = CH - (PAD_B * K if CARD['cap'] else 0)       # the cap band at the bottom is meant to be overlapped
    COVER_KEY = covered(CX, CY, CW, body_h, KEYS)
    COVER_VIS = covered(CX, CY, CW, body_h, VIS)
    if COVER_KEY > .03:
        warn(f'the speaker hides {COVER_KEY * 100:.0f}% of the card on a say/tick/done beat: the row may not read. Move CARD_BOX or use CARD_BOX = "auto"')
    elif COVER_VIS > .35:
        warn(f'the speaker hides up to {COVER_VIS * 100:.0f}% of the card between beats (a hand or their head passes in front). Check the snapshots')
# largest screen rect of the card body: (a) at the completion pop (scale 1.02, tilt still on, float up 7 px, push-in
# as far as it has got by F_DONE) and (b) at rest on the last frame (full push-in). Calibrated on the demo render.
states = [(CW * .016 + 4, CH * .015 + 7, CH * .015, P_POP), (4, 10, 3, PUSH)]
wx0 = min(OX + (CX - ex - OX) * p for ex, et, eb, p in states)
wx1 = max(OX + (CX + CW + ex - OX) * p for ex, et, eb, p in states)
wy0 = min(OY + (CY - et - OY) * p for ex, et, eb, p in states)
wy1 = max(OY + (CY + CH + eb - OY) * p for ex, et, eb, p in states)
if wy0 < SAFE_T or wy1 > SAFE_B or wx0 < SAFE_L or wx1 > SAFE_R or (wy1 > SAFE_LOW_Y and wx1 > SAFE_R_LOW):
    warn(f'card reaches x {wx0:.0f}..{wx1:.0f}, y {wy0:.0f}..{wy1:.0f} at its largest: outside the safe zone '
         f'(x {SAFE_L}..{SAFE_R}, y {SAFE_T}..{SAFE_B}, right {SAFE_R_LOW} below y {SAFE_LOW_Y}). Shrink or move CARD_BOX')

# glass or opaque
if GLASS == 'auto':
    GLASS_MODE = 'glass' if PREP['camera']['still'] else 'opaque'
else:
    GLASS_MODE = GLASS
    if GLASS == 'glass' and PREP and not PREP['camera']['still']:
        warn(f'GLASS forced on a moving camera (drift {PREP["camera"]["drift_px"]} px): the room behind the glass will not move with the shot')
if GLASS_MODE == 'glass':
    gf = PREP['camera']['glass_frame'] if PREP else N // 2
    # the room seen through the glass: one blurred still of the plate, cropped to the card rect, contrast flattened
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf',
                    f"select=eq(n\\,{gf}),gblur=sigma=40,crop={CW}:{CH}:{max(0, CX)}:{max(0, CY)},"
                    "eq=contrast=0.62:brightness=0.02:saturation=1.3", '-frames:v', '1', '-q:v', '3', 'assets/glass.jpg'], check=True)
    CARD_BG = f'{INK} url(assets/glass.jpg) 0 0/{WN:.1f}px {H0}px no-repeat'
    TINT = 'linear-gradient(158deg,rgba(36,39,50,.66) 0%,rgba(21,23,30,.78) 46%,rgba(14,15,20,.86) 100%)'
else:
    CARD_BG = 'linear-gradient(158deg,#2B2E3A 0%,#1A1C24 46%,#101116 100%)'
    TINT = 'radial-gradient(120% 90% at 18% 0%,rgba(255,248,239,.07) 0%,rgba(255,248,239,0) 60%)'


def hexrgb(h):
    h = h.lstrip('#')
    return ','.join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


AR = hexrgb(ACCENT)
Z = 6 if CARD['layer'] == 'front' else 2
TILT_Y = -4.5 if CX + CW / 2 >= 540 else 4.5
CNT_H = 38


def words_html(text, k):
    out, j = [], 0
    for line in text.split('|'):
        ws = []
        for w in line.split(' '):
            acc = w.startswith('*') and w.endswith('*') and len(w) > 2
            ws.append(f'<span class="w{" acc" if acc else ""}" id="w{k}-{j}">{html_mod.escape(w.strip("*") if acc else w)}</span>')
            j += 1
        out.append(f'<div class="ln">{" ".join(ws)}</div>')
    return ''.join(out)


def checklist():
    """Returns (css, html, tweens) for the card. All sizes are card units inside #cls, which is scaled by K."""
    n = n_rows
    seg_w = (WN - 2 * PADX - (n - 1) * 10) / n
    css = f'''
#clw{{position:absolute;left:{CX}px;top:{CY}px;width:{CW}px;height:{CH}px;z-index:{Z}}}
#clf,#cl3,#cln{{position:absolute;inset:0}}
#cl3{{transform-origin:50% 62%}}
#cls{{position:absolute;left:0;top:0;width:{WN:.1f}px;height:{H0}px;transform:scale({K:.4f});transform-origin:0 0}}
#clsh{{position:absolute;left:40px;right:40px;top:70px;bottom:-26px;border-radius:{RAD}px;background:rgba(24,16,8,.55);filter:blur(46px)}}
.card{{position:absolute;inset:0;border-radius:{RAD}px;overflow:hidden;background:{CARD_BG};box-shadow:0 10px 26px rgba(16,10,6,.30)}}
.tint{{position:absolute;inset:0;background:{TINT}}}
.edge{{position:absolute;inset:0;border-radius:{RAD}px;border:1.5px solid rgba(255,248,239,.15);
  box-shadow:inset 0 1.5px 0 rgba(255,255,255,.20),inset 0 -1px 0 rgba(0,0,0,.35)}}
#glow{{position:absolute;inset:-3px;border-radius:{RAD + 3}px;border:3px solid rgba({AR},.9);
  box-shadow:0 0 54px rgba({AR},.38),inset 0 0 44px rgba({AR},.10)}}
#sheen{{position:absolute;top:-20%;left:0;width:26%;height:140%;transform:skewX(-18deg);
  background:linear-gradient(90deg,rgba(255,248,239,0) 0%,rgba(255,248,239,.13) 50%,rgba(255,248,239,0) 100%)}}
.eyebrow{{position:absolute;left:{PADX}px;top:50px;display:flex;align-items:flex-start;gap:16px;white-space:nowrap;
  font:600 26px/{EB_LH}px Montserrat;letter-spacing:.17em;color:rgba(255,248,239,.74)}}
.eyebrow i{{display:block;width:13px;height:13px;margin-top:10.5px;border-radius:50%;background:{ACCENT};box-shadow:0 0 14px rgba({AR},.7)}}
#pill{{position:absolute;right:{PADX - 6}px;top:38px;height:58px;padding:0 24px;border-radius:29px;display:flex;align-items:center;gap:10px;
  background:rgba(255,248,239,.09);border:1.5px solid rgba(255,248,239,.16);color:{CREAM};font:800 31px 'Inter Tight';
  letter-spacing:-.01em;white-space:nowrap}}
#cntb{{height:{CNT_H}px;overflow:hidden}}
#cnt{{display:flex;flex-direction:column}}
#cnt span{{height:{CNT_H}px;line-height:{CNT_H}px;display:block;text-align:center}}
.segs{{position:absolute;left:{PADX}px;top:{118 + HEAD_X}px;width:{WN - 2 * PADX:.1f}px;height:10px;display:flex;gap:10px}}
.seg{{width:{seg_w:.1f}px;height:10px;border-radius:5px;background:rgba(255,248,239,.13);overflow:hidden}}
.segf{{width:100%;height:100%;border-radius:5px;background:{ACCENT};transform-origin:0 50%;box-shadow:0 0 12px rgba({AR},.5)}}
#hl{{position:absolute;left:16px;right:16px;top:{HEAD_H + 9}px;height:{ROW_H[0] - 18}px;border-radius:32px;
  background:linear-gradient(90deg,rgba(255,248,239,.115),rgba(255,248,239,.05));border:1.5px solid rgba(255,248,239,.11)}}
.row{{position:absolute;left:0;right:0}}
.box{{position:absolute;left:{PADX}px;width:{BOX}px;height:{BOX}px}}
.ring{{position:absolute;inset:0;border-radius:50%;border:3.5px solid rgba(255,248,239,.34)}}
.disc{{position:absolute;inset:0;border-radius:50%;background:{ACCENT};box-shadow:0 6px 22px rgba({AR},.34)}}
.rip{{position:absolute;inset:0;border-radius:50%;border:4px solid {ACCENT}}}
.ck{{position:absolute;inset:0;width:{BOX}px;height:{BOX}px}}
.spk{{position:absolute;left:{BOX / 2}px;top:{BOX / 2}px;width:0;height:0}}
.spk i{{position:absolute;left:0;top:-3px;width:18px;height:6px;border-radius:3px;background:{ACCENT}}}
.sk{{position:absolute;left:{TEXT_L}px;top:0;display:flex;flex-direction:column;justify-content:center;transform-origin:0 50%}}
.skb{{height:22px;margin:{(LH - 22) / 2:.0f}px 0;border-radius:11px;background:linear-gradient(90deg,rgba(255,248,239,.15),rgba(255,248,239,.07))}}
.tx{{position:absolute;left:{TEXT_L}px;top:0;display:flex;flex-direction:column;justify-content:center;white-space:nowrap;
  font:800 {FS}px 'Inter Tight';letter-spacing:-.028em;color:{CREAM}}}
.tx .ln{{display:flex;align-items:center;gap:.24em;height:{LH}px}}
.tx .w{{display:inline-block}}
.tx .acc{{color:{ACCENT}}}
.star{{position:absolute;z-index:{Z};color:{ACCENT};line-height:1;text-shadow:0 0 18px rgba({AR},.55)}}
'''
    row_html = []
    for k, (text, _, _) in enumerate(ROWS):
        sparks = ''.join(f'<div class="spk" style="transform:rotate({a}deg)"><i id="spk{k}-{j}"></i></div>'
                         for j, a in enumerate((-158, -112, -68, -22, 28, 74, 118, 164)))
        row_html.append(f'''
        <div class="row" id="row{k}" style="top:{ROW_TOP[k]}px;height:{ROW_H[k]}px">
          <div class="box" id="box{k}" style="top:{(ROW_H[k] - BOX) / 2:.0f}px">
            <div class="rip" id="rip{k}"></div>{sparks}
            <div class="ring"></div><div class="disc" id="disc{k}"></div>
            <svg class="ck" viewBox="0 0 76 76"><path id="ck{k}" d="M22.5 39.5 L33.5 50.5 L54.5 27.5" fill="none" stroke="{INK}" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="50" stroke-dashoffset="50"/></svg>
          </div>
          <div class="sk" id="sk{k}" style="height:{ROW_H[k]}px">{''.join(f'<div class="skb" style="width:{row_width(l) * .78:.0f}px"></div>' for l in ROW_LINES[k])}</div>
          <div class="tx" id="tx{k}" style="height:{ROW_H[k]}px">{words_html(text, k)}</div>
        </div>''')
    star1_x = max(SAFE_L + 2, CX - 22 * K)
    html = f'''
    <div id="clw"><div id="clf"><div id="cl3"><div id="cln"><div id="cls">
      <div id="clsh"></div>
      <div class="card">
        <div class="tint"></div>
        <div id="hl"></div>
        <div class="eyebrow" id="eyebrow"><i></i><span>{'<br>'.join(html_mod.escape(l.upper()) for l in TITLE_LINES)}</span></div>
        <div id="pill"><div id="cntb"><div id="cnt">{''.join(f'<span>{i}</span>' for i in range(n + 1))}</div></div><span>of {n}</span></div>
        <div class="segs">{''.join(f'<div class="seg" id="seg{k}"><div class="segf" id="segf{k}"></div></div>' for k in range(n))}</div>
        {''.join(row_html)}
        <div id="sheen"></div>
        <div class="edge"></div>
      </div>
      <div id="glow"></div>
    </div></div></div></div></div>
    <div class="star" id="star0" style="left:{CX + CW - 36 * K:.0f}px;top:{CY - 4 * K:.0f}px;font-size:{44 * K:.0f}px">&#10022;</div>
    <div class="star" id="star1" style="left:{star1_x:.0f}px;top:{CY + 96 * K:.0f}px;font-size:{30 * K:.0f}px">&#10022;</div>'''

    t0 = F(F_IN)
    # the build takes ~0.72s at full length; squeeze it when the first row is said sooner than that
    e = min(1.0, max(.35, (F(ROWS[0][1]) - t0) / .72))
    tw = [
        # ---- build ----
        "gsap.set('#clw',{autoAlpha:0});",
        f"gsap.set('#cl3',{{transformPerspective:1500,rotationX:17,rotationY:{TILT_Y * 2},y:86,scale:.88,filter:'blur(10px)'}});",
        "gsap.set(['#eyebrow','#pill','.seg','.box','.sk'],{autoAlpha:0});",
        "gsap.set(['.disc','.rip','.spk i','.ck','#hl','#glow','.star','.tx .w'],{autoAlpha:0});",
        "gsap.set('.segf',{scaleX:0});gsap.set('#sheen',{xPercent:-140});gsap.set('.star',{scale:0});",
        f"tl.to('#clw',{{autoAlpha:1,duration:.1,ease:'power2.out'}},{t0:.3f});",
        f"tl.to('#cl3',{{rotationX:2.5,rotationY:{TILT_Y},y:0,scale:1,filter:'blur(0px)',duration:{.6 * max(e, .6):.3f},ease:'expo.out'}},{t0:.3f});",
        f"tl.set('#cl3',{{filter:'none'}},{t0 + .6 * max(e, .6) + .02:.3f});",
        f"tl.fromTo('#eyebrow',{{autoAlpha:0,x:-22}},{{autoAlpha:1,x:0,duration:{.34 * e:.3f},ease:'power3.out',immediateRender:false}},{t0 + .14 * e:.3f});",
        f"tl.fromTo('#pill',{{autoAlpha:0,scale:.6}},{{autoAlpha:1,scale:1,duration:{.36 * e:.3f},ease:'back.out(2.2)',immediateRender:false}},{t0 + .20 * e:.3f});",
        f"tl.fromTo('.seg',{{autoAlpha:0,scaleX:.2,transformOrigin:'0 50%'}},{{autoAlpha:1,scaleX:1,duration:{.4 * e:.3f},ease:'power3.out',stagger:{.06 * e:.3f},immediateRender:false}},{t0 + .20 * e:.3f});",
        f"tl.fromTo('.box',{{autoAlpha:0,scale:.3}},{{autoAlpha:1,scale:1,duration:{.4 * e:.3f},ease:'back.out(2)',stagger:{.225 * e / n:.3f},immediateRender:false}},{t0 + .28 * e:.3f});",
        f"tl.fromTo('.sk',{{autoAlpha:0,scaleX:.15}},{{autoAlpha:1,scaleX:1,duration:{.45 * e:.3f},ease:'power3.out',stagger:{.225 * e / n:.3f},immediateRender:false}},{t0 + .32 * e:.3f});",
        # slow float so the card never sits dead still
        f"tl.to('#clf',{{y:-7,duration:{DUR * .5:.3f},ease:'sine.inOut',yoyo:true,repeat:1}},0);",
    ]
    # NO overwrite:'auto' anywhere: the renderer seeks, and an overwrite kills the earlier tween for good (the counter
    # stuck on "2 of 3" from frame 0). Tweens on one property never overlap instead: durations shrink to the gap.
    td = F(F_DONE)
    to = F(F_OUT) if F_OUT is not None else None
    # focus arrives with the text, unless the text came up front (before the previous tick): then 3 frames after that tick
    TF = [F(r[1]) if k == 0 or r[1] >= ROWS[k - 1][2] else F(ROWS[k - 1][2] + 3) for k, r in enumerate(ROWS)]
    for k, (text, f_say, f_tick) in enumerate(ROWS):
        ts, tt, tf = F(f_say), F(f_tick), TF[k]
        nw = len(text.replace('|', ' ').split(' '))
        gap = (F(ROWS[k + 1][2]) if k < n - 1 else td) - tt            # time until the next tick (or the finish)
        fgap = (TF[k + 1] if k < n - 1 else td) - tf                   # time until the focus bar moves again
        # ---- the speaker starts the phrase: focus bar glides to the row, skeleton resolves into the words ----
        if k == 0:
            tw += [f"tl.fromTo('#hl',{{autoAlpha:0,scaleX:.9}},{{autoAlpha:1,scaleX:1,duration:.26,ease:'power3.out',immediateRender:false}},{tf:.3f});"]
        else:
            tw += [f"tl.to('#hl',{{y:{ROW_TOP[k] - HEAD_H},height:{ROW_H[k] - 18},duration:{max(.12, min(.38, fgap - .02)):.3f},ease:'expo.out'}},{tf:.3f});",
                   f"tl.to('#tx{k - 1}',{{opacity:.62,duration:.3,ease:'power2.out'}},{tf:.3f});",
                   f"tl.to('#box{k - 1}',{{opacity:.8,duration:.3,ease:'power2.out'}},{tf:.3f});"]
        tw += [f"tl.to('#sk{k}',{{autoAlpha:0,scaleX:.5,duration:.1,ease:'power2.in'}},{ts:.3f});",
               f"tl.fromTo('#tx{k} .w',{{autoAlpha:0,y:26,filter:'blur(10px)'}},{{autoAlpha:1,y:0,filter:'blur(0px)',duration:.22,"
               f"ease:'power3.out',stagger:.045,immediateRender:false}},{ts:.3f});",
               f"tl.set('#tx{k} .w',{{filter:'none'}},{ts + .045 * nw + .26:.3f});",
               f"tl.to('#box{k} .ring',{{borderColor:'rgba(255,248,239,.8)',duration:.25}},{ts:.3f});"]
        # ---- the tick: anticipation, disc pops, check draws, ripple + sparks, text flashes in the accent colour ----
        tw += [f"tl.to('#box{k}',{{scale:.84,duration:.062,ease:'power2.in'}},{tt - .066:.3f});",
               f"tl.to('#box{k}',{{scale:1.22,duration:.1,ease:'power3.out'}},{tt:.3f});",
               f"tl.to('#box{k}',{{scale:1,duration:.4,ease:'back.out(2.8)'}},{tt + .102:.3f});",
               f"tl.fromTo('#disc{k}',{{autoAlpha:1,scale:.25}},{{autoAlpha:1,scale:1,duration:.2,ease:'back.out(1.8)',immediateRender:false}},{tt:.3f});",
               f"tl.set('#box{k} .ck',{{autoAlpha:1}},{tt:.3f});",
               f"tl.to('#ck{k}',{{strokeDashoffset:0,duration:.2,ease:'power2.out'}},{tt + .033:.3f});",
               f"tl.fromTo('#rip{k}',{{autoAlpha:.9,scale:.8}},{{autoAlpha:0,scale:2.05,duration:.5,ease:'power2.out',immediateRender:false}},{tt + .02:.3f});",
               f"tl.fromTo('#box{k} .spk i',{{autoAlpha:1,x:34,scaleX:1}},{{autoAlpha:0,x:70,scaleX:.25,duration:.42,ease:'power3.out',immediateRender:false}},{tt + .03:.3f});",
               f"tl.fromTo('#tx{k} .w:not(.acc)',{{color:'{ACCENT}'}},{{color:'{CREAM}',duration:.55,ease:'power2.inOut',immediateRender:false}},{tt:.3f});",
               f"tl.fromTo('#tx{k}',{{x:12}},{{x:0,duration:.5,ease:'elastic.out(1,.55)',immediateRender:false}},{tt:.3f});",
               f"tl.to('#segf{k}',{{scaleX:1,duration:.42,ease:'power3.out'}},{tt + .03:.3f});",
               f"tl.to('#cnt',{{y:{-(k + 1) * CNT_H},duration:{max(.12, min(.4, gap - .05)):.3f},ease:'back.out(1.7)'}},{tt + .03:.3f});",
               f"tl.to('#cln',{{scale:1.014,y:3,duration:.08,ease:'power2.out'}},{tt:.3f});",
               f"tl.to('#cln',{{scale:1,y:0,duration:{max(.05, min(.2, gap - .1)):.3f},ease:'power2.out'}},{tt + .082:.3f});"]
    # ---- finish: counter pill fills (hard swap on the frame, a fade hides the digits), sheen, edge glow, settle ----
    tw += [f"tl.to('#hl',{{autoAlpha:0,duration:.3,ease:'power2.out'}},{td:.3f});",
           f"tl.to(['.tx','.box'],{{opacity:1,duration:.26,ease:'power2.out'}},{td:.3f});",
           f"tl.set('#pill',{{backgroundColor:'{ACCENT}',borderColor:'{ACCENT}',color:'{INK}'}},{td:.3f});",
           f"tl.to('#pill',{{scale:1.17,duration:.1,ease:'power3.out'}},{td:.3f});",
           f"tl.to('#pill',{{scale:1,duration:.5,ease:'back.out(2.6)'}},{td + .1:.3f});",
           f"tl.to('#glow',{{autoAlpha:1,duration:.16,ease:'power2.out'}},{td:.3f});",
           f"tl.to('#glow',{{autoAlpha:.42,duration:.7,ease:'power2.inOut'}},{td + .2:.3f});",
           f"tl.to('#sheen',{{xPercent:420,duration:.8,ease:'power2.inOut'}},{td + .02:.3f});",
           f"tl.to('#cln',{{scale:1.02,duration:.12,ease:'power2.out'}},{td:.3f});",
           f"tl.to('#cln',{{scale:1,duration:.6,ease:'back.out(2.2)'}},{td + .122:.3f});",
           f"tl.to('#cl3',{{rotationX:0,rotationY:0,duration:{.7 if to is None else max(.15, min(.7, to - td - .02)):.3f},ease:'power3.out'}},{td:.3f});"]
    for j, dt in enumerate((.06, .16)):
        if to is None or td + dt + .34 <= to - .01:                    # a sparkle that cannot finish before the exit is left out
            tw += [f"tl.to('#star{j}',{{autoAlpha:1,scale:1,rotation:90,duration:.34,ease:'back.out(2.4)'}},{td + dt:.3f});"]
        if to is None or td + dt + .95 <= to - .01:
            tw += [f"tl.to('#star{j}',{{scale:.72,duration:.3,ease:'sine.inOut',yoyo:true,repeat:1}},{td + dt + .345:.3f});"]
    # ---- optional exit ----
    if F_OUT is not None:
        tw += [f"tl.to('.star',{{autoAlpha:0,scale:0,duration:.12,ease:'power2.in'}},{to:.3f});",
               f"tl.to('#cl3',{{y:54,scale:.93,rotationX:12,filter:'blur(9px)',duration:.22,ease:'power2.in'}},{to:.3f});",
               f"tl.to('#clw',{{autoAlpha:0,duration:.16,ease:'power2.in'}},{to + .06:.3f});",
               f"tl.set('#clw',{{autoAlpha:0}},{to + .24:.3f});"]
    # ---- outside the effect the frame is the untouched a-roll: the speaker's cutout layer is only up while the card is ----
    if HAS_CUT and CARD['layer'] == 'behind':
        tw += ["gsap.set('#cutwrap',{autoAlpha:0});", f"tl.set('#cutwrap',{{autoAlpha:1}},{F(F_IN):.3f});"]
        if F_OUT is not None:
            tw += [f"tl.set('#cutwrap',{{autoAlpha:0}},{F(F_OUT + 8):.3f});"]
    return css, html, tw


# ---------------------------------------------------------------- sound
# (file, time the HIT should be heard, base volume). Each stock file has air before its transient (pop.mp3: 118 ms),
# so audio() starts it early by SFX_LEAD. Volumes are the template's base volumes x SFX_GAIN.
SFX = [('whoosh-short', F_IN / 30 + .12, .20)] + [('pop', r[2] / 30 + .033, .18) for r in ROWS] + \
      [('sparkle', F_DONE / 30 + .03, .16)] + ([('whoosh-short', F_OUT / 30 + .10, .14)] if F_OUT is not None else [])
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'sparkle': 1.8, 'click': .36, 'click-soft': .36}
SFX_LEAD = {'whoosh-short': .14, 'pop': .118, 'sparkle': .025, 'click': .05, 'click-soft': .05}
SFX_GAIN = 0.75   # house level: all sounds 25% under the template's base volumes


def audio():
    out, lanes = [], []
    if not SFX_ON:
        return out
    for k, (name, hit, vol) in enumerate(sorted(SFX, key=lambda s: s[1])):
        t = max(0.0, hit - SFX_LEAD[name])
        d = min(SFX_LEN[name], DUR - t)
        if d < .08 or not os.path.exists(f'assets/sfx/{name}.mp3'):
            continue
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    c_css, c_html, c_tw = checklist()
    front = CARD['layer'] == 'front'
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0;transform-origin:50% 49%}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
{f'.g{{filter:{GRADE}}}' if GRADE else ''}
#bgv{{z-index:0}}
#cutwrap{{position:absolute;inset:0;z-index:4}}
#vig{{position:absolute;inset:0;z-index:7;pointer-events:none;
  background:radial-gradient(105% 70% at 50% 46%,rgba(0,0,0,0) 58%,rgba(0,0,0,{VIGNETTE}) 100%)}}
{c_css}'''
    tw = list(c_tw)
    if PUSH != 1:
        tw.append(f"tl.fromTo('#stage',{{scale:1}},{{scale:{PUSH},duration:{DUR:.3f},ease:'none',immediateRender:false}},0);")
    cut = (f'<div id="cutwrap"><video id="cut" class="full g" src="assets/subject.webm" muted playsinline data-start="0" '
           f'data-media-start="0" data-duration="{DUR:.4f}" data-track-index="1"></video></div>') if HAS_CUT and not front else ''
    nl = '\n'
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.4f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.4f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
  <div id="stage">
    <video id="bgv" class="full g" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.4f}" data-track-index="0"></video>
{c_html}
    {cut}
  </div>
  {'<div id="vig"></div>' if VIGNETTE else ''}
{SAFE_GUIDE if SAFE_ON else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {DUR:.4f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    os.makedirs('work', exist_ok=True)
    json.dump({'name': NAME, 'frames': N, 'f_in': F_IN, 'rows': [[r[0], r[1], r[2]] for r in ROWS], 'f_done': F_DONE,
               'f_out': F_OUT, 'card': [CX, CY, CW, CH], 'layer': CARD['layer'], 'glass': GLASS_MODE, 'scale': round(K, 3),
               'safe_guide': SAFE_ON, 'warnings': WARN}, open('work/build.json', 'w'), indent=1)
    print(f'[{NAME}] wrote index.html  {N} frames ({DUR:.3f}s)  {n_rows} rows{"  SAFE GUIDE ON (do not render)" if SAFE_ON else ""}')
    print(f'  card   {CARD["layer"]}, {GLASS_MODE}, x {CX} y {CY} {CW}x{CH}, scale {K:.2f} (row text {FS * K:.0f} px)'
          f'{", cap overlap band " + str(PAD_B) + " px" if CARD["cap"] else ""}{"  [auto]" if CARD_BOX == "auto" else ""}')
    if CARD['layer'] == 'behind' and MASKS:
        print(f'  depth  the speaker passes in front of up to {COVER_VIS * 100:.0f}% of the card while it is up, {COVER_KEY * 100:.0f}% on a beat')
    if PREP:
        c = PREP['camera']
        print(f'  camera {"steady" if c["still"] else "moving"}: background drift {c["drift_px"]} px (glass up to {c.get("glass_max_drift_px", 24)} px)')
    print(f'  beats  in f{F_IN}  ' + '  '.join(f'row{k + 1} say f{r[1]} tick f{r[2]}' for k, r in enumerate(ROWS)) +
          f'  done f{F_DONE}' + (f'  out f{F_OUT}' if F_OUT is not None else '') + f'   sounds {"on" if SFX_ON else "off"}')
    print(f'  render to renders/{NAME}.mp4')
    for w in WARN:
        print('  WARNING: ' + w)


build()
