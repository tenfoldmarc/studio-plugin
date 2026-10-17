#!/usr/bin/env python3
"""paper-cut, step 1: measure the clip, choose the layout, write work/plan.json, the sounds and index.html.

The room rips away to torn paper; the speaker stays live as a white-edged hand-cut cutout (moving at 12 fps), the
phrase lands in ransom-note letters word by word, crayon and pen marks boil, then the collage tears back to the room.

  PY build.py            measure + layout + plan + index.html (prints which layout it chose and why)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no letters (the reel's own captions carry the words): collage and cutout only
  SFX=0                  no rips, whooshes, clicks
  GRADE                  this effect has no grade of its own; the switch is accepted and does nothing
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import math
import os
import re
import subprocess
import sys
import wave

import cv2
import numpy as np

import collage as C
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_IN = 'auto'         # the paper rips in on this word: a word from words.json ('look', or 'look#2' for its 2nd time),
                      # seconds, or 'auto' (the first word that starts after 0.4 s). Re-measured on the audio.
T_OUT = 'auto'        # the collage tears away: 'auto' (room back 4 frames before the slot ends), seconds, or 'cut'
                      # (holds to the last frame; only when the reel cuts away right after the slot)
ROWS = [              # the ransom-note phrase, one string per row (1 to 4 rows, 1 to 12 letters each). Each word lands
    'YOUR WORDS',     # on its own spoken word (matched in words.json in order, from T_IN on). For exact control a row
    'GO HERE',        # can be a list of (text, when) groups: [('1', '100'), ('00', 1.92), ('%', '%')], when = a word
]                     # or seconds. Use the speaker's own words; no names, numbers or outlets they did not say.
LAYOUT = 'auto'       # 'auto', 'above' (letters above the head, cutout shrinks toward its corner) or 'below' (letters
                      # across the chest, under the chin). Leave 'auto' unless the printout's choice looks wrong.
FONT = 'mix'          # 'mix' = the ransom mix of the shipped faces, or ONE family from assets/fonts/fonts.css (the
                      # buyer's caption font: every letter in it, still on mixed papers), or a list of families
WEIGHT = 800          # weight for a named FONT (variable faces follow it; static faces stay what they are)
CASE = 'upper'        # 'upper', 'as typed', 'lower', 'title'
INK = (20, 22, 28)            # the dark ink and dark scraps (r, g, b): the buyer's text colour if it is dark
ACCENT = (200, 34, 47)        # the red scraps, the pen ellipse and underline: the buyer's highlight colour
ACCENT2 = (43, 73, 194)       # the blue scraps and the crayon: a second brand colour
HIGHLIGHT = (250, 230, 122)   # the yellow paper and yellow scraps
ELLIPSE = 'auto'      # which row gets the pen ellipse: a row number (0 = top), 'auto' (the shortest row that is not
                      # the last), or None
TAPE = True           # a strip of tape slaps on the first letter of the last row
MATTE_KILL_POLYS = []  # matte repairs, off by default: polygons [(x, y), ...] in 1080x1920 px where the cutout grabbed
                       # room (a picture frame, a cabinet edge). Look at a preview first; add only what you see.
MATTE_PLATE = None     # still camera only: dict(roi=(x0, y0, x1, y1), frames=[...], thr=20, min_area=2200): a clean
                       # plate of a region, from frames where the speaker is out of it, drops pixels that match the room
SEED = 7               # change for a different scatter of papers, fonts and tilts
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = C.W, C.H, C.FPS
Q = 4
DEFAULT_MIX = [('Bebas Neue', 400, False), ('DM Serif Display', 400, False), ('Archivo', 900, False),
               ('Newsreader', 600, True), ('JetBrains Mono', 500, False), ('Playfair Display', 600, True),
               ('Inter Tight', 900, False), ('Instrument Serif', 400, False), ('Poppins', 700, False),
               ('Barlow Condensed', 600, False), ('Figtree', 600, False), ('DM Serif Display', 400, True),
               ('Montserrat', 500, False), ('Newsreader', 500, False)]

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
if not os.path.exists('assets/subject.webm'):
    sys.exit('paper-cut needs the cutout (assets/subject.webm): make the slot without --no-cutout')
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg)


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9%]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(a) // hop
    return np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: take the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    j0, j1 = int(s * 100), min(len(ENVL) - 1, int(e * 100) + 1)
    pk_i = j0 + int(np.argmax(ENVL[j0:j1 + 1])) if j1 > j0 else j0          # the loudest moment of the word
    i0, i1 = max(0, int((s - 0.12) * 100)), min(len(ENVL) - 1, int((s + 0.12) * 100), pk_i)
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(ENVL[i0:i1 + 1]))
    pk = ENVL[im:min(len(ENVL), int((e + 0.1) * 100)) + 1].max()
    thr = ENVL[im] + 0.35 * (pk - ENVL[im])
    for i in range(im, min(len(ENVL), int((e + 0.1) * 100))):
        if ENVL[i] >= thr:
            return i / 100.0
    return s


def find_word(v):
    key, nth = (str(v).split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    return hits[int(nth) - 1]


def when(v, default):
    if v is None or v == 'auto':
        v = default
    if isinstance(v, (int, float)):
        return float(v), 'seconds'
    w = find_word(v)
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


auto_in = next((w['text'] for w in words if w['start'] >= 0.4), 0.5)
if isinstance(auto_in, str):
    auto_in = f"{auto_in}#{[norm(w['text']) for w in words if w['start'] < 0.4].count(norm(auto_in)) + 1}"
t_in, how_in = when(T_IN, auto_in)
f_in = int(round(t_in * FPS)) - 1
if f_in < 8:
    say(f'!! the paper would arrive at frame {f_in}: moved to frame 8 so the slot starts on plain footage. '
        'Start the slot earlier.')
    f_in = 8
if T_OUT == 'cut':
    f_out = N
elif isinstance(T_OUT, (int, float)):
    f_out = int(round(float(T_OUT) * FPS))
else:
    f_out = N - 10                                     # the tear takes 6 frames, then 4 plain frames
f_out = min(f_out, N)
if T_OUT != 'cut' and f_out > N - 7:
    say(f'!! T_OUT frame {f_out} leaves no room for the tear and plain frames: moved to {N - 7}')
    f_out = N - 7
LAND = f_in + 10                                       # the sheets have landed


def cased(s):
    if CASE == 'upper':
        return s.upper()
    if CASE == 'lower':
        return s.lower()
    if CASE == 'title':
        return re.sub(r"(^|\s)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s.lower())
    return s


# rows -> groups (text, frame, stagger)
row_groups = []
notes = []
if ENV['CAPTIONS']:
    cursor = next((i for i, w in enumerate(words) if w['end'] > t_in - 0.05), len(words))
    pending = []
    for row in ROWS:
        gs = []
        if isinstance(row, str):
            for tok in row.split():
                hit = None
                for j in range(cursor, min(len(words), cursor + 8)):
                    a, b = norm(words[j]['text']), norm(tok)
                    if a and b and (a.startswith(b) or b.startswith(a) or a in b):
                        hit = j
                        break
                if hit is None:
                    gs.append([(" " if gs else "") + tok, None, 1])
                    pending.append(tok)
                    continue
                w = words[hit]
                cursor = hit + 1
                t = onset(w)
                dur = max(1, int(round((w['end'] - w['start']) * FPS)))
                stag = 0 if len(tok) == 1 else int(np.clip(round(0.7 * dur / len(tok)), 1, 2))
                gs.append([(" " if gs else "") + tok, int(round(t * FPS)), stag])
        else:
            for text, wv in row:
                t = when(wv, None)[0]
                gs.append([text, int(round(t * FPS)), 0 if len(text.strip()) == 1 else 1])
        row_groups.append(gs)
    if pending:
        notes.append('!! not matched in words.json, spread evenly instead: ' + ' '.join(pending)
                     + '  (give these as (text, word or seconds) groups)')
        known = [g[1] for gs in row_groups for g in gs if g[1] is not None]
        lo = max([LAND + 2] + known)
        hi = max(lo + 4, f_out - 36)
        miss = [g for gs in row_groups for g in gs if g[1] is None]
        for k, g in enumerate(miss):
            g[1] = int(lo + (hi - lo) * (k + 1) / (len(miss) + 1))
    for gs in row_groups:
        for g in gs:
            if g[1] < LAND:
                notes.append(f'!! "{g[0]}" lands at frame {g[1]}, before the paper has settled (frame {LAND}): '
                             f'moved to {LAND}. Bring T_IN earlier for a cleaner build.')
                g[1] = LAND
    last_land = max((g[1] + g[2] * (len(g[0].strip()) - 1) for gs in row_groups for g in gs), default=LAND)
    if T_OUT != 'cut' and f_out - last_land < 30:
        notes.append(f'!! the last letter lands {(f_out - last_land) / FPS:.2f}s before the tear (1 s or more reads '
                     'well): make the slot longer or the phrase earlier')
else:
    last_land = LAND

# ---------------------------------------------------------------------------------------------------- measure
qa = np.stack(list(reader('assets/subject.webm', W, H, alpha=True, scale=(W // Q, H // Q))))
if len(qa) != N:
    say(f'!! the cutout has {len(qa)} frames, the slot {N}: remake it (fx_new.py)')
    qa = qa[:N] if len(qa) > N else np.concatenate([qa, np.repeat(qa[-1:], N - len(qa), 0)])
span = qa[f_in:max(f_in + 1, min(N, f_out))] > 128


def main_body(m):
    """what the cutout will show: the kill polygons removed, then only the largest piece (the speaker)."""
    m = m.astype(np.uint8)
    for p in MATTE_KILL_POLYS:
        cv2.fillPoly(m, [(np.array(p, np.float32) / Q).astype(np.int32)], 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 2:
        m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    return m > 0


span = np.stack([main_body(m) for m in span])


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head, or None when nobody is in the frame."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 40.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    for _ in range(6):
        band = m[top:int(top + 0.45 * hw) + 1]
        xs = np.where(band.any(axis=0))[0]
        if len(xs):
            cx = xs.mean() if len(xs) < 0.9 * m.shape[1] else cx
        r = min(m.shape[0] - 1, int(top + 0.6 * hw))
        xs = np.where(m[r, int(max(0, cx - 1.3 * hw)):int(cx + 1.3 * hw) + 1])[0]
        if not len(xs):
            break
        hw = max(8.0, float(xs[-1] - xs[0] + 1))
    return top * Q, cx * Q, hw * Q


heads = [h for h in (head_of(m) for m in span) if h]
if len(heads) < 0.5 * len(span):
    sys.exit('PAPER CUT DECLINES: the cutout finds nobody in most of the frames. It needs the speaker in the shot.')
tops = np.array([h[0] for h in heads], float)
hws = np.array([h[2] for h in heads], float)
jump = np.where(np.abs(np.diff(hws)) > 0.3 * np.minimum(hws[1:], hws[:-1]) + 24)[0]
moved = float(np.percentile(tops, 95) - np.percentile(tops, 5))
if moved > 350:
    say(f'!! the head top moves {moved:.0f} px during the effect (a zoom, punch-in or camera move): the layout must '
        'clear its highest point. Keep the slot inside one steady shot for a bigger layout.')
elif len(jump) and LAYOUT == 'auto':
    say(f'!! the head size jumps near slot frame {f_in + int(jump[0]) + 1}: a cut or punch-in inside the slot. The '
        'layout is measured over the whole effect, so keep the slot inside one shot (or end the effect before it).')
top_hi = float(np.percentile(tops, 3))                 # highest the head (or a raised hand) gets
hcx = float(np.median([h[1] for h in heads]))
hw = float(np.median(hws))
chin_low = float(np.percentile(tops + 1.35 * hws, 95))  # lowest the chin gets
touch = {k: float(np.mean(v)) for k, v in (('left', span[:, :, :2].sum(axis=(1, 2)) >= 6),
                                          ('right', span[:, :, -2:].sum(axis=(1, 2)) >= 6),
                                          ('top', span[:, :2, :].sum(axis=(1, 2)) >= 3))}
shot = 'tight' if hw > 330 else ('medium' if hw > 150 else 'wide')
say(f'measured: {shot} shot, head top {top_hi:.0f} (highest), head width {hw:.0f}, face centre x {hcx:.0f}, '
    f'chin down to {chin_low:.0f}; speaker meets the frame edge: '
    + ', '.join(f'{k} {v * 100:.0f}%' for k, v in touch.items()))
can_shrink = not (touch['left'] > 0.2 and touch['right'] > 0.2) and touch['top'] < 0.2
side = 'left' if touch['left'] > 0.2 else ('right' if touch['right'] > 0.2 else ('left' if hcx < W / 2 else 'right'))

# ---------------------------------------------------------------------------------------------------- fonts
css =os.path.join('assets', 'fonts', 'fonts.css')
if not os.path.exists(css):
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
faces = []
for block in re.findall(r'@font-face\s*\{([^}]*)\}', open(css, encoding='utf-8').read()):
    fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", block)
    sty = re.search(r'font-style:\s*(\w+)', block)
    wt = re.search(r'font-weight:\s*(\d+)', block)
    src = re.search(r"url\(['\"]?([^'\")]+)", block)
    if fam and src and os.path.exists(os.path.join('assets', 'fonts', src.group(1))):
        faces.append((fam.group(1).strip(), sty.group(1) if sty else 'normal', int(wt.group(1)) if wt else 400,
                      os.path.join('assets', 'fonts', src.group(1)).replace(os.sep, '/')))


def pick(family, weight, italic, strict=True):
    fs = [f for f in faces if f[0].lower() == family.lower()]
    if not fs:
        if strict:
            sys.exit(f'font "{family}" is not in assets/fonts/fonts.css. Families there: '
                     + ', '.join(sorted({f[0] for f in faces})))
        return None
    same = [f for f in fs if f[1] == ('italic' if italic else 'normal')] or fs
    best = min(same, key=lambda f: abs(f[2] - weight))
    return [best[3], weight]


if FONT == 'mix':
    fonts = [p for p in (pick(f, w, i, strict=False) for f, w, i in DEFAULT_MIX) if p]
    if len(fonts) < 4:
        fonts += [[f[3], f[2]] for f in faces][:8]
elif isinstance(FONT, (list, tuple)):
    fonts = [pick(f, WEIGHT, False) for f in FONT]
else:
    fonts = [pick(FONT, WEIGHT, False)]
fonts = [list(f) for f in dict((tuple(f), 1) for f in fonts)]
if not fonts:
    sys.exit('no usable font in assets/fonts/fonts.css')
say(f'letters: {len(fonts)} face(s): ' + ', '.join(os.path.basename(f[0]).split('-')[0] for f in fonts[:8])
    + (' ...' if len(fonts) > 8 else ''))
C.set_colours(dict(black=list(INK), crimson=list(ACCENT), cobalt=list(ACCENT2), yellow=list(HIGHLIGHT)))

# ---------------------------------------------------------------------------------------------------- layout
GAP = 16
X0, X1_HI, X1_LO = 58, 1022, 962


def nat_h(gs, width):
    chars = sum(len(g[0].replace(" ", "")) for g in gs)
    spaces = sum(g[0].count(" ") for g in gs)
    return min(190.0, width / (0.80 * chars + 0.30 * spaces))


def stack(hs):
    return sum(hs) + GAP * (len(hs) - 1) + 24          # + tilt and jitter allowance


def dy_of(s):
    return 300 * (1 - s)                                # the shrunk cutout also drops a little


def top_after(s):
    return H - s * (H - top_hi) + dy_of(s)


MIN_H = 96
layout, why, scale, rows_h, block_top = None, '', 1.0, [], 0
if row_groups:
    hs = [nat_h(gs, X1_HI - X0) for gs in row_groups]
    Y0 = 250
    cand = [LAYOUT] if LAYOUT != 'auto' else ['above', 'below']
    for c in cand:
        if c == 'above':
            for shrink_h in (1.0, 0.85, 0.72):
                hh = [h * shrink_h for h in hs]
                if min(hh) < MIN_H and shrink_h < 1:
                    break
                need = Y0 + stack(hh) + 36
                s_need = (H + 300 - need) / (H - top_hi + 300)
                if can_shrink:
                    s = min(0.96, s_need)
                    if s >= 0.70:
                        layout, scale, rows_h = 'above', s, hh
                        break
                elif top_hi >= need:
                    layout, scale, rows_h = 'above', 1.0, hh
                    break
            if layout:
                why = (f'{"shrinks to " + format(scale, ".2f") + " toward the " + side + " corner" if scale < 1 else "no shrink (the speaker meets both sides or the top)"}'
                       f', head top {top_after(scale):.0f} after it, letters {min(rows_h):.0f} to {max(rows_h):.0f} px tall')
                break
            if LAYOUT == 'above':
                sys.exit(f'PAPER CUT DECLINES (LAYOUT above): the head reaches y {top_hi:.0f}; there is no room for the '
                         'letters above it. Try LAYOUT = "below" or "auto".')
        if c == 'below':
            zone = 1462 - (chin_low + 55)
            hs2 = [nat_h(gs, X1_LO - X0) for gs in row_groups]
            k = min(1.0, (zone - 24 - GAP * (len(hs2) - 1)) / (sum(hs2) + 0.2 * hs2[-1])) if zone > 0 else 0
            hh = [h * k for h in hs2]
            if k > 0 and min(hh) >= MIN_H:
                layout, scale, rows_h = 'below', 1.0, hh
                why = f'tight framing: the letters go across the chest under the chin (chin down to y {chin_low:.0f})'
                break
            if LAYOUT == 'below':
                sys.exit(f'PAPER CUT DECLINES (LAYOUT below): the chin reaches y {chin_low:.0f}; no room for the letters '
                         'between it and the bottom safe line (y 1470).')
    if not layout:
        sys.exit(f'PAPER CUT DECLINES: the face fills the frame (head top y {top_hi:.0f}, chin down to y '
                 f'{chin_low:.0f}): no room for the letters above the head or under the chin. Use a wider take, '
                 'shorten the phrase, or build with CAPTIONS=0 (the collage and cutout without letters).')
else:
    layout = 'above' if can_shrink else 'none'
    scale = 0.9 if can_shrink else 1.0
    why = 'no letters (CAPTIONS=0): collage and cutout only'
say(f'layout: {layout.upper()} ({why})')

# row geometry
ALIGNS = {1: ['center'], 2: ['left', 'right'], 3: ['left', 'right', 'center'], 4: ['left', 'right', 'left', 'center']}
rows = []
if row_groups:
    if layout == 'above':
        spare = (top_after(scale) - 36) - (250 + stack(rows_h))
        y = 250 + max(0.0, spare * 0.45) + 12
        x1 = X1_HI
    else:
        y = 1462 - 0.2 * rows_h[-1] - stack(rows_h) + 12
        x1 = X1_LO
    al = ALIGNS[min(4, len(rows_h))] + ['center'] * max(0, len(rows_h) - 4)
    ell_row = ELLIPSE
    if ell_row == "auto" and layout == "below":   # under the chin the ellipse would reach up to the face
        ell_row = None
    if ell_row == "auto":                         # the shortest row that is not the last
        ell_row = min(range(len(row_groups) - 1), key=lambda r: sum(len(g[0]) for g in row_groups[r]), default=None)
    for i, (gs, h) in enumerate(zip(row_groups, rows_h)):
        items = []
        for text, fr, stag in gs:                  # string rows carry a space before each word; groups join as typed
            j = 0
            for ch in cased(text):
                items.append([ch, int(fr + j * stag)] if ch.strip() else None)
                j += 1 if ch.strip() else 0
        inset = 54 if i == ell_row else 0           # the pen ellipse needs room round its row
        rows.append(dict(cy=round(y + h / 2, 1), h=round(h, 1), x0=X0 + inset, x1=x1 - inset, align=al[i], items=items))
        y += h + GAP

letters = C.build_letters(rows, fonts, SEED) if rows else []
face_line = top_after(scale) - 30 if layout == 'above' else chin_low + 30
bad = []
for L in letters:
    x0, y0, x1, y1 = C.letter_box(L)
    if y0 < C.SAFE['top'] or y1 > C.SAFE['bottom'] or x0 < C.SAFE['side'] or x1 > W - C.SAFE['side'] or (
            y1 > C.SAFE['right_low'][0] and x1 > W - C.SAFE['right_low'][1]):
        bad.append(f'{L["ch"]} ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})')
    if (layout == 'above' and y1 > face_line) or (layout == 'below' and y0 < face_line):
        bad.append(f'{L["ch"]} touches the face line y {face_line:.0f}')
if bad:
    say('!! check: ' + '; '.join(bad[:6]))

# ---------------------------------------------------------------------------------------------------- collage
if letters:
    y_band = max(C.letter_box(L)[3] for L in letters) if layout == 'above' else float(np.clip(chin_low - 300, 560, 900))
else:
    y_band = float(np.clip(top_after(scale) - 60, 560, 900))
shift = float(np.clip(y_band - 758, -260, 420))
mir = side == 'right'


def P(x, y, shift_y=True):
    return [round(W - x if mir else x, 1), round(min(1880, y + shift) if shift_y else y, 1)]


def poly(pts, keep_bottom=False):
    return [P(x, y, not (keep_bottom and y >= 2000)) for x, y in pts]


def frm(x, y):
    return [-x if mir else x, y]


rot = -1 if mir else 1
layers = [
    dict(kind='kraft', poly=[[-220, -220], [1300, -220], [1300, 2140], [-220, 2140]], frm=frm(-1300, 0),
         rot=-3.0 * rot, f=f_in),
    dict(kind='cream', poly=[P(-90, -90, False), P(1170, -90, False)]
         + poly([(1185, 905), (835, 872), (455, 948), (-90, 868)]), frm=frm(0, -1150), rot=2.5 * rot, f=f_in + 2),
    dict(kind='yellow', poly=poly([(455, 792), (1150, 742), (1165, 1335), (712, 1408), (418, 1296)]),
         frm=frm(820, -60), rot=-7.0 * rot, f=f_in + 4),
    dict(kind='graph', poly=poly([(548, 1302), (1150, 1236), (1170, 2010), (372, 2010), (410, 1512)], True),
         frm=frm(420, 760), rot=6.0 * rot, f=f_in + 6),
]
layers[3]['poly'] = [[x, min(y, 1750) if y < 2000 else y] for x, y in layers[3]['poly']]


def zig(x0, y0, x1, y1, w, n):
    a, b = P(x0, y0), P(x1, y1)
    return ['zigzag', a[0], a[1], b[0], b[1], w, n]


marks = [
    dict(kind='crayon', col='cobalt_soft', w=30, f=f_in + 5, dur=9, path=zig(120, 478, 1000, 520, 235, 13), amp=3.0, op=0.50),
    dict(kind='crayon', col='cobalt', w=20, f=f_in + 9, dur=7, path=zig(660, 880, 1010, 1100, 120, 9), amp=2.5, op=0.85),
    dict(kind='crayon', col='crimson', w=16, f=f_in + 13, dur=6, path=zig(800, 1300, 950, 1440, 70, 7), amp=2.2, op=0.85),
    dict(kind='pen', col='ink', w=5, f=f_in + 12, dur=3, path=['cross'] + P(968, 1196) + [26], amp=1.6),
    dict(kind='pen', col='ink', w=5, f=f_in + 15, dur=3, path=['cross'] + P(905, 1236) + [20], amp=1.6),
    dict(kind='pen', col='crimson', w=5, f=f_in + 17, dur=3, path=['cross'] + P(78, 792) + [22], amp=1.6),
    dict(kind='pen', col='ink', w=4, f=f_in + 16, dur=10, path=['loops'] + P(600, 1560) + P(990, 1530) + [26, 7], amp=1.8),
    dict(kind='pen', col='crimson', w=5, f=f_in + 20, dur=8, path=['stitch'] + P(712, 888) + P(1052, 902) + [9], amp=1.5),
    dict(kind='pen', col='ink', w=4, f=f_in + 24, dur=6, path=['star'] + P(150, 820) + [24], amp=1.4),
]
tape = None
if letters:
    by_row = {}
    for L in letters:
        by_row.setdefault(L['row'], []).append(L)
    boxes = {r: (min(C.letter_box(L)[0] for L in ls), max(C.letter_box(L)[2] for L in ls),
                 max(L['f'] for L in ls), min(L['f'] for L in ls)) for r, ls in by_row.items()}
    last = max(by_row)
    er = ell_row
    if er is not None and er in by_row:
        x0, x1, lf, _ = boxes[er]
        cy, hh = rows[er]['cy'], rows[er]['h']
        rx = min((x1 - x0) / 2 + 46, (x0 + x1) / 2 - 40, W - 40 - (x0 + x1) / 2)
        ry = min(hh * 0.64, cy - 226)
        if rx > (x1 - x0) / 2 + 8 and ry > hh * 0.52:
            marks.append(dict(kind='pen', col='crimson', w=6, f=lf + 3, dur=8, over=True, amp=2.2,
                              path=['ellipse', (x0 + x1) / 2, cy, rx, ry, -3.0]))
    x0, x1, lf, ff = boxes[last]
    uy = rows[last]['cy'] + 0.57 * rows[last]['h']
    if uy + 18 < C.SAFE['bottom']:
        marks.append(dict(kind='pen', col='crimson', w=6, f=lf + 6, dur=5, over=True, amp=1.8,
                          path=['underline', x0 + 0.52 * (x1 - x0), uy + 8, x1 - 6, uy]))
    if TAPE:
        first = min(by_row[last], key=lambda L: L['cx'])
        k = rows[last]['h'] / 184
        tape = dict(f=lf + 10, cx=round(first['cx'] - first['w'] / 2 + 10 * k, 1),
                    cy=round(rows[last]['cy'] - 0.35 * rows[last]['h'], 1), rot=-38.0, w=200 * k, h=58 * k)
tear = dict(x_top=W - 735 if mir else 735, x_bot=W - 585 if mir else 585)
cut = dict(scale=round(scale, 4), ax=0.0 if side == 'left' else float(W), dx=(-8 if side == 'left' else 8) * (scale < 1),
           dy=round(dy_of(scale), 1), border=24, jitter=True)

# optional matte plate (still camera)
mt = dict(kill_polys=MATTE_KILL_POLYS, plate=MATTE_PLATE, open_roi=None)
os.makedirs('work', exist_ok=True)
if MATTE_PLATE:
    x0, y0, x1, y1 = MATTE_PLATE['roi']
    fr = sorted(set(min(N - 1, max(0, f)) for f in MATTE_PLATE['frames']))
    cols, alps = [], []
    for f in fr:
        cols.append(next(reader('assets/aroll.mp4', W, H, first=f, last=f))[y0:y1, x0:x1])
        alps.append(next(reader('assets/subject.webm', W, H, alpha=True, first=f, last=f))[y0:y1, x0:x1])
    cols = [cv2.blur(c, (3, 3)) for c in cols]
    np.savez_compressed('work/plate.npz', col=np.median(np.stack(cols), 0).astype(np.int16),
                        bg=np.median(np.stack(alps), 0) < 100)
    say(f'matte plate from {len(fr)} frames of region {MATTE_PLATE["roi"]}')

pl = dict(n=N, fps=FPS, seed=SEED, f_in=f_in, f_out=f_out, step_fps=12, layout=layout, side=side, shot=shot,
          colours=dict(black=list(INK), crimson=list(ACCENT), cobalt=list(ACCENT2), yellow=list(HIGHLIGHT)),
          fonts=fonts, rows=rows, layers=layers, marks=marks, tape=tape, tear=tear, cut=cut, matte=mt)
json.dump(pl, open('work/plan.json', 'w'), indent=1)
for nte in notes:
    say(nte)
say(f'timing: paper in at frame {f_in} ({how_in}); letters land frames '
    + ' | '.join(' '.join(f'{g[0]}@{g[1]}' for g in gs) for gs in row_groups)
    + ('; holds to the last frame (T_OUT = cut)' if f_out >= N else f'; tears away frames {f_out} to {f_out + 5}'))

# ---------------------------------------------------------------------------------------------------- sounds
SR = 48000


def wav(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def band_noise(n, lo, hi, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = 1 / (1 + (lo / np.maximum(fr, 1)) ** 2) / (1 + (fr / hi) ** 2)
    x = np.fft.irfft(spec * shape, n)
    return x / np.abs(x).max()


def s_rip(seed, peak):
    r = np.random.default_rng(seed)
    n = int(SR * 0.30)
    x = r.standard_normal(n)
    x = np.concatenate([[0], x[1:] - 0.86 * x[:-1]])          # tilt up: papery, no rumble
    x = np.convolve(x, np.ones(3) / 3, 'same')
    env = np.zeros(n)
    for t0 in np.sort(r.uniform(0, 0.30 * 0.82, 90)):
        i = int(t0 * SR)
        ln = int(SR * r.uniform(0.002, 0.007))
        env[i:i + ln] += r.uniform(0.3, 1.0) * np.exp(-np.arange(min(ln, n - i)) / (ln / 3))
    t = np.arange(n) / SR
    env = (0.25 + env) * np.minimum(1, t / 0.006) * np.exp(-np.maximum(0, t - 0.16) / 0.045)
    y = x * env
    return y / np.abs(y).max() * peak


def s_whoosh(seed, peak):
    r = np.random.default_rng(seed)
    n = int(SR * 0.42)
    t = np.arange(n) / SR
    lo, hi = band_noise(n, 250, 900, r), band_noise(n, 900, 4200, r)
    mixk = np.clip(t / 0.12, 0, 1)                             # brightens toward the peak, then darkens
    mixk = np.where(t < 0.12, mixk, np.exp(-(t - 0.12) / 0.10))
    x = lo * (1 - 0.6 * mixk) + hi * 0.6 * mixk
    env = np.where(t < 0.10, (t / 0.10) ** 2, np.exp(-(t - 0.10) / 0.09))
    y = x * env
    return y / np.abs(y).max() * peak


def s_click(seed, peak):
    r = np.random.default_rng(seed)
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    y = band_noise(n, 1500, 7000, r) * np.exp(-t / 0.004) + 0.5 * np.sin(2 * np.pi * 1900 * t) * np.exp(-t / 0.007)
    return y / np.abs(y).max() * peak


def s_pop(seed, peak):
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    f0 = 260 + 420 * np.exp(-t / 0.018)
    y = np.sin(2 * np.pi * np.cumsum(f0) / SR) * np.exp(-t / 0.035) * np.clip(t / 0.002, 0, 1)
    y += 0.25 * band_noise(n, 2000, 8000, np.random.default_rng(seed)) * np.exp(-t / 0.003)
    return y / np.abs(y).max() * peak


cues = []
if ENV['SFX']:
    os.makedirs('assets_fx', exist_ok=True)
    plan_sfx = [('whoosh_in', s_whoosh(SEED, 0.15), f_in / FPS - 0.10), ('rip_in', s_rip(SEED + 1, 0.10), f_in / FPS - 0.02)]
    if row_groups:
        firsts = [gs[0][1] for gs in row_groups]
        for i, fr in enumerate(firsts[:-1]):
            plan_sfx.append((f'click{i}', s_click(SEED + 10 + i, 0.13), fr / FPS - 0.01))
        plan_sfx.append(('pop', s_pop(SEED + 20, 0.12), firsts[-1] / FPS - 0.01))
    if f_out < N:
        plan_sfx += [('rip_out', s_rip(SEED + 2, 0.11), f_out / FPS - 0.02),
                     ('whoosh_out', s_whoosh(SEED + 3, 0.11), f_out / FPS - 0.07)]
    for key, x, t in plan_sfx:
        path = f'assets_fx/paper-{key}.wav'
        wav(path, x)
        length = len(x) / SR
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(length - skip, DUR - t)
        if d > 0.03:
            cues.append(f'  <audio id="sfx_{key}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cues)}" data-volume="1"></audio>')

# ---------------------------------------------------------------------------------------------------- index.html
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

firsts = [gs[0][1] for gs in row_groups] or [LAND]
mk = sorted({0, f_in + 3, LAND + 2, firsts[0] + 1, last_land + 3, min(N - 1, last_land + 14), f_out - 1,
             min(N - 1, f_out + 2), N - 1} & set(range(N)))
stills = [min(N - 1, last_land + 12), min(N - 1, (firsts[0] + last_land) // 2 + 1), LAND + 4]
json.dump({'name': NAME, 'frames': N, 'marks': mk, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(f) for f in (LAND + 2, min(N - 1, last_land + 12), min(N - 1, f_out + 2)))
      + ' -g  (preview), then bake.py')
