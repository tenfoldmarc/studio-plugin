#!/usr/bin/env python3
"""cover-story, step 2: measure the clip, lay out the cover, write work/plan.json, the two sounds, index.html.

The live shot becomes a magazine cover and the speaker keeps talking on it: hairline border, slow push-in, a tall
serif masthead behind (or above) the head, small tracked-caps labels, one italic cover line landing on a word.

  PY build.py            measure + layout + plan + index.html (prints which framing it chose and why)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no kicker and no cover line (the reel's own captions carry the words)
  SFX=0                  no swell / thump
  GRADE=1                a slightly richer print while the cover is up (default off: the reel grades)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np

import cover as C
from fxio import FF, count_frames, probe_size, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_IN = 'auto'        # the cover arrives on this word: a word from words.json ('video', or 'video#2' for its 2nd time),
                     # seconds, or 'auto' (first word that starts after 0.4 s). The onset is re-measured on the audio.
T_LAND = 'auto'      # the cover line lands on this word (same forms). 'auto' = longest word that leaves 1.5 s to read.
OUT = 'auto'         # when the cover leaves: 'auto' (gone 3 frames before the slot ends), seconds, or 'cut' (holds
                     # to the last frame; only when the reel cuts away right after the slot)
MASTHEAD = 'EDIT'    # an invented title, never a real magazine's logotype. 3 to 6 letters. Letters that end in a stem
                     # or bowl sit best over the head (build.py prints which letters are over it)
LINES = [            # (text, style, when). '\n' splits lines, *word* takes the accent. when: None = auto, a word, or s
    ('THE NEW\nISSUE', 'label-left', None),      # tracked caps beside the head, left (invented label, no names)
    ('IN THEIR\nOWN WORDS', 'label-right', None),  # tracked caps beside the head, right
    ('COVER STORY', 'kicker', None),              # small caps above the cover line
    ('Your words\ngo *here*', 'main', None),      # THE cover line: the speaker's own words, lands on T_LAND
]
FONT = 'Playfair Display'      # cover line family: any family in assets/fonts/fonts.css (the buyer's caption font)
ITALIC = True                  # cover line in the italic of FONT when the slot has one
WEIGHT = 400                   # cover line weight (variable fonts follow it; a static file stays what it is)
CASE = 'as typed'              # cover line + kicker: 'as typed', 'upper', 'lower', 'title'
MAST_FONT = 'DM Serif Display'  # masthead family (a high-contrast serif reads as a magazine)
LABEL_FONT = 'Figtree'         # tracked caps of the labels and kicker
INK = 'auto'                   # type colour: 'auto' (cream, near-black over a bright wall) or (r, g, b)
ACCENT = (250, 230, 122)       # the *word* colour (butter yellow); used once
FRAMING = 'auto'               # 'auto', or force 'behind' / 'above' / 'clear' (see effect.md "Adapting")
HEAD_TOP = 'auto'              # highest row the head reaches (1080x1920 px) if the measured one is off, else 'auto'
ZOOM_CENTRE = 'auto'           # (x, y) the push-in grows from; 'auto' = the measured face
PUSH = 0.03                    # push-in on T_IN (0.03 = 3 percent), then a slow drift
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
GRADE = os.environ.get('GRADE', '0') not in ('0', '')
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = C.W, C.H, C.FPS
Q = 4                                                    # measurement runs at a quarter of the size

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
if not os.path.exists('assets/subject.webm'):
    sys.exit('cover-story needs the cutout (assets/subject.webm): make the slot without --no-cutout')
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg)


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160                                            # 10 ms
    n = len(a) // hop
    return np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: take the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    # look for the dip only BEFORE the word's loudest moment, or a short word can jump to the next word's onset
    j0, j1 = int(s * 100), min(len(ENVL) - 1, int(e * 100) + 1)
    pk_i = j0 + int(np.argmax(ENVL[j0:j1 + 1])) if j1 > j0 else j0
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


def when(v, default):
    """CLIP time -> (seconds, how it was found)."""
    if v is None or v == 'auto':
        v = default
    if isinstance(v, (int, float)):
        return float(v), 'seconds'
    key, nth = (v.split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    w = hits[int(nth) - 1]
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


auto_in = next((w['text'] for w in words if w['start'] >= 0.4), 0.6)
t_in, how_in = when(T_IN, auto_in)
# 'auto' landing: the longest word (most likely the content word) that still leaves about 1.5 s to read
late = [w for w in words if t_in + 0.9 <= w['start'] <= DUR - 2.1]
auto_land = DUR - 2.1
if late:
    best = max(late, key=lambda w: len(norm(w['text'])))
    hits = [w for w in words if norm(w['text']) == norm(best['text'])]
    auto_land = f"{best['text']}#{hits.index(best) + 1}"
t_land, how_land = when(T_LAND, auto_land)
if t_in < 0.27:
    say(f'!! T_IN at {t_in:.2f}s leaves no plain frames at the start of the slot: moved to 0.27s. Start the slot earlier.')
    t_in = 0.27
if t_land < t_in + 0.9:
    say(f'!! T_LAND {t_land:.2f}s is only {t_land - t_in:.2f}s after T_IN: the page needs about 0.9s to set. Moved.')
    t_land = t_in + 0.9
OUT_DUR = 0.5
if OUT == 'cut':
    t_out = None
elif isinstance(OUT, (int, float)):
    t_out = float(OUT)
else:
    t_out = DUR - OUT_DUR - 3 / FPS
if t_out is not None and t_out < t_land + 1.2:
    say(f'!! the cover line is up for only {t_out - t_land:.2f}s before the cover leaves (1.5s reads well): '
        'start the slot earlier, make it longer, or land earlier')

# ---------------------------------------------------------------------------------------------------- measure the cutout
first_on = max(0, int((t_in - 0.2) * FPS))
last_on = N - 1 if t_out is None else min(N - 1, int((t_out + OUT_DUR) * FPS) + 1)
qa = np.stack(list(reader('assets/subject.webm', W, H, alpha=True, scale=(W // Q, H // Q))))
if len(qa) != N:
    say(f'!! the cutout has {len(qa)} frames, the slot {N}: remake it (fx_new.py)')
    qa = qa[:N] if len(qa) > N else np.concatenate([qa, np.repeat(qa[-1:], N - len(qa), 0)])
span = qa[first_on:last_on + 1] > 128


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head, or None when nobody is in the frame."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 40.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    for _ in range(6):                    # fixed point: width of the head half a head below its top
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
    sys.exit('the cutout finds nobody in most of the frames: Cover Story needs the speaker in the shot')
tops = np.array([h[0] for h in heads], float)
ht = float(np.percentile(tops, 5)) if HEAD_TOP == 'auto' else float(HEAD_TOP)
hcx = float(np.median([h[1] for h in heads]))
hw = float(np.median([h[2] for h in heads]))
face_cy = ht + 0.7 * hw
zc = (float(np.clip(hcx, 200, 880)), float(np.clip(face_cy, 300, 1300))) if ZOOM_CENTRE == 'auto' else tuple(ZOOM_CENTRE)

pl = dict(n=N, fps=FPS, t_in=t_in, t_land=t_land, t_out=t_out, out_dur=OUT_DUR, push=PUSH, push_dur=1.15, drift=0.007,
          zoom_centre=list(zc))
zmax = C.zoom_max(pl)


def pushed(y, cy=zc[1]):
    return cy + (y - cy) * zmax


HT = pushed(ht)                                          # the head top after the push-in (it rises a little)
HW = hw * zmax
face = (hcx - 0.62 * HW, HT, hcx + 0.62 * HW, HT + 1.4 * HW)        # x0, y0, x1, y1 (chin about 1.4 head widths down)
tight = HW > 330
drift = float(np.percentile(tops, 95) - np.percentile(tops, 5))
shot = 'tight' if tight else ('medium' if HW > 150 else 'wide')
say(f'measured: {shot} shot, head top {ht:.0f} (pushed {HT:.0f}), head width {HW:.0f}, face centre x {hcx:.0f}, '
    f'head moves {drift:.0f}px up/down over the cover')

# ---------------------------------------------------------------------------------------------------- fonts
FONTS_DIR = os.path.join('assets', 'fonts')
table = C.font_table(FONTS_DIR)
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
fonts = {'mast': C.pick_font(table, MAST_FONT, 400), 'line': C.pick_font(table, FONT, WEIGHT, ITALIC),
         'label': C.pick_font(table, LABEL_FONT, 500)}
say('fonts: ' + ', '.join(f'{k} {os.path.basename(v[0])}' for k, v in fonts.items()))

# ---------------------------------------------------------------------------------------------------- the masthead
MAST_TOP, LEFT, RIGHT = 232, 78, 1002
CAP_MAX = 240


def behind_cap(f):
    """masthead cap height when the head hides the bottom f of it (cap line fixed at MAST_TOP)."""
    base = (HT - f * MAST_TOP) / (1 - f)
    return base - MAST_TOP


room_above = HT - 28 - MAST_TOP
choice, why = None, ''
cand = []
if FRAMING != 'auto':
    cand = [FRAMING]
elif tight:
    cand = ['above', 'behind']
else:
    cand = ['behind', 'above']
for c in cand:
    if c == 'above' and (room_above >= (110 if tight else 96) or FRAMING == 'above'):
        cap = min(room_above, 160)
        if cap < 70:
            continue
        choice, mast_cap, mast_base = 'above', cap, MAST_TOP + cap
        why = f'{"tight shot: " if tight else ""}{room_above:.0f}px open above the head, smaller masthead over it'
        break
    if c in ('behind', 'clear'):
        cap20 = behind_cap(0.2)
        if cap20 >= CAP_MAX or c == 'clear':
            mast_cap, mast_base = CAP_MAX if c != 'clear' else min(CAP_MAX, max(120, HT - 40 - MAST_TOP)), None
            mast_base = MAST_TOP + mast_cap
            hidden = max(0.0, (mast_base - HT) / mast_cap)
            choice = 'behind' if hidden > 0.03 else 'clear'
            why = (f'head top {HT:.0f}: the head hides {hidden * 100:.0f}% of the caps' if choice == 'behind'
                   else f'head top {HT:.0f} is below the masthead: it stands clear above the speaker')
            break
        for f, lo in ((0.2, 150), (0.25, 140), (0.3, 130)):
            cap = behind_cap(f)
            if cap >= lo:
                choice, mast_cap, mast_base = 'behind', cap, MAST_TOP + cap
                why = f'head top {HT:.0f}: masthead behind the head, bottom {f * 100:.0f}% of the caps hidden'
                break
        if choice:
            break
if not choice:
    sys.exit(f'COVER STORY DECLINES: the head reaches y {HT:.0f} (the top safe line is 220), so there is no room for a '
             'masthead above or behind it. Use a moment with more headroom, a wider take, or another effect.')
size, track, mw = C.masthead_fit(MASTHEAD, fonts['mast'], mast_cap, RIGHT - LEFT)
say(f'framing: {choice.upper()} ({why}). Masthead "{MASTHEAD}" cap {mast_cap:.0f}px, size {size}, tracking {track:.2f}')
masthead = dict(text=MASTHEAD, size=size, track=track, left=LEFT, measure=RIGHT - LEFT, base=int(round(mast_base)),
                cap_top=MAST_TOP)

# ---------------------------------------------------------------------------------------------------- occupancy
zq = (zc[0] / Q, zc[1] / Q)
occ_frames = []
for m in span.astype(np.float32):                         # where the speaker is at the strongest push, per frame
    M = np.float32([[1 / zmax, 0, zq[0] - zq[0] / zmax], [0, 1 / zmax, zq[1] - zq[1] / zmax]])
    occ_frames.append(np.maximum(m, cv2.warpAffine(m, M, (m.shape[1], m.shape[0]), flags=cv2.WARP_INVERSE_MAP)))
occ_frames = np.stack(occ_frames) > 0.5


def covered(x, y, w, h, pad=12):
    """per-frame share of a box (full-size px) that the speaker covers -> (90th percentile, max)."""
    x0, y0 = max(0, (x - pad) // Q), max(0, (y - pad) // Q)
    x1, y1 = min(W // Q, (x + w + pad) // Q + 1), min(H // Q, (y + h + pad) // Q + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0, 0.0
    f = occ_frames[:, y0:y1, x0:x1].mean(axis=(1, 2))
    return float(np.percentile(f, 90)), float(f.max())


def overlaps_face(x, y, w, h, pad=24):
    return not (x + w < face[0] - pad or x > face[2] + pad or y + h < face[1] - pad or y > face[3] + pad)


# ---------------------------------------------------------------------------------------------------- lines
LABEL_STYLE = dict(size=21, track=0.26, lead=33, rule_len=44, rule_gap=37)
MAIN_SIZE, MAIN_LEAD, MAIN_BASE = 106, 108, 1442


def cased(s):
    if CASE == 'upper':
        return s.upper()
    if CASE == 'lower':
        return s.lower()
    if CASE == 'title':
        return re.sub(r"(^|[\s*])([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


style_of = {st: (tx, wh) for tx, st, wh in LINES}
gap = t_land - t_in
auto_t = {'label-left': t_in + 0.28 * gap, 'label-right': t_in + 0.45 * gap, 'kicker': t_land - 0.38 * gap,
          'main': t_land - 0.30}


def t_of(st):
    v = style_of[st][1]
    if v is None:
        return auto_t[st]
    return when(v, None)[0] if not isinstance(v, (int, float)) else float(v)


main = kicker = None
notes = []
if 'main' in style_of and ENV['CAPTIONS']:
    lines = [cased(s) for s in style_of['main'][0].split('\n')]
    msize = MAIN_SIZE
    widest = max(C.line_width(s, fonts['line'], msize) for s in lines)
    if widest > RIGHT - 100 - LEFT + 24:                   # measure is 902 (the right column below y 1155 stays clear)
        msize = int(msize * (RIGHT - 100 - LEFT + 24) / widest)
        if msize < 70:
            sys.exit('the cover line is too long for the page: split it with "\\n" or shorten it (2 to 6 words)')
        say(f'cover line set at {msize}px to fit the measure')
    lead = int(round(msize * MAIN_LEAD / MAIN_SIZE))
    asc = C.ascent(fonts['line'], msize)
    n = len(lines)
    bottom_first = MAIN_BASE - (n - 1) * lead
    block_w = max(C.line_width(s, fonts['line'], msize) for s in lines)
    if overlaps_face(LEFT, bottom_first - asc, block_w, (n - 1) * lead + asc + int(0.3 * msize)):
        notes.append('cover line moved up: the face sits low in the frame')
        # under the masthead / labels instead, if the face leaves room there
        first_base = int(mast_base + 110 + asc)
        if overlaps_face(LEFT, first_base - asc, block_w, (n - 1) * lead + asc + int(0.3 * msize)):
            sys.exit('COVER STORY DECLINES: the face sits where the cover line goes, top and bottom. Use a shot where '
                     'the face is in the upper half of the frame.')
        pos = 'top'
    else:
        first_base, pos = bottom_first, 'bottom'
    main = dict(lines=lines, size=msize, lead=lead, first_base=int(first_base), x=LEFT, t=t_of('main'), pos=pos)
    main_top = first_base - asc

labels = []
lab_bottom = mast_base
for st, align, x_edge in (('label-left', 'left', LEFT), ('label-right', 'right', RIGHT)):
    if st not in style_of:
        continue
    text = style_of[st][0]
    tl = text.split('\n')
    lw = max(C.set_line(s, fonts['label'], LABEL_STYLE['size'], LABEL_STYLE['track'])[1] for s in tl)
    lh = LABEL_STYLE['rule_gap'] + (len(tl) - 1) * LABEL_STYLE['lead'] + 8
    y_lo = int(mast_base + 86)
    y_hi = min(1000, int((main_top if main and main['pos'] == 'bottom' else H) - 140 - lh))
    placed = None
    for y in range(y_lo, max(y_lo, y_hi) + 1, 30):
        x = x_edge if align == 'left' else x_edge - lw
        p90, mx = covered(x, y, lw, lh)
        if p90 < 0.03 and mx < 0.25 and not (main and main['pos'] == 'top' and y + lh > main_top - 30):
            placed = y
            break
    if placed is None:
        notes.append(f'{st} left out: no open wall beside the head for it')
        continue
    if placed != y_lo:
        notes.append(f'{st} moved down to y {placed} to clear the speaker')
    labels.append(dict(text=text, x_edge=x_edge, y_rule=placed, align=align, layer='back', t=t_of(st)))
    lab_bottom = max(lab_bottom, placed + lh)

if 'kicker' in style_of and main and ENV['CAPTIONS']:
    ktext = cased(style_of['kicker'][0]).upper()
    kl = ktext.split('\n')
    kw = max(C.set_line(s, fonts['label'], LABEL_STYLE['size'], LABEL_STYLE['track'])[1] for s in kl)
    y_rule = int(main['first_base'] - C.ascent(fonts['line'], main['size']) - 34 - LABEL_STYLE['rule_gap']
                 - (len(kl) - 1) * LABEL_STYLE['lead'])
    if tight or overlaps_face(LEFT, y_rule, kw, main['first_base'] - y_rule):
        notes.append('kicker left out: ' + ('tight shot, one cover line only' if tight else 'it would touch the face'))
    else:
        kicker = dict(text=ktext, x_edge=LEFT, y_rule=y_rule, align='left', layer='front', t=t_of('kicker'))
        labels.append(kicker)

# ---------------------------------------------------------------------------------------------------- the wall: ink, busy
fl = min(N - 1, int(t_land * FPS) + 6)
plain = next(reader('assets/aroll.mp4', W, H, first=fl, last=fl))
luma = (plain.astype(np.float32) @ np.float32([0.2126, 0.7152, 0.0722]))
occ_full = cv2.resize(occ_frames.max(axis=0).astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
mx0 = LEFT + (RIGHT - LEFT - mw) // 2
band = np.zeros((H, W), bool)
band[MAST_TOP:int(mast_base), mx0:mx0 + mw] = True
wall = band & ~occ_full
hp = np.abs(luma - cv2.GaussianBlur(luma, (0, 0), 6))
wall_l = float(np.percentile(luma[wall], 75)) if wall.sum() > 500 else 120.0
busy = float(hp[wall].mean()) if wall.sum() > 500 else 0.0
fb = np.zeros((H, W), bool)
if main:
    fb[int(main_top):int(main['first_base'] + (len(main['lines']) - 1) * main['lead'] + 20), LEFT:LEFT + 700] = True
front_l = float(np.percentile(luma[fb], 75)) if fb.sum() > 500 else 100.0
CREAM, DARK, ACC_DARK = [255, 248, 239], [26, 23, 21], [122, 30, 48]
if INK == 'auto':
    ink_back = DARK if wall_l > 185 else CREAM
    ink_front = DARK if front_l > 200 else CREAM
else:
    ink_back = ink_front = list(INK)
accent = list(ACCENT) if ink_front == CREAM or INK != 'auto' else ACC_DARK
dim_top = 0.11
shadow_back = [0.26, 13.0, 7]
if ink_back == DARK:
    dim_top, shadow_back = 0.0, [0.0, 13.0, 7]
elif busy > 9:
    dim_top, shadow_back = 0.18, [0.36, 13.0, 7]
say(f'wall behind the masthead: brightness {wall_l:.0f}, texture {busy:.1f} -> '
    f'{"near-black type" if ink_back == DARK else "cream type"}{", busy wall: deeper shade behind the type" if busy > 9 and ink_back != DARK else ""}'
    f'; under the cover line {front_l:.0f} -> {"near-black" if ink_front == DARK else "cream"}')

# ---------------------------------------------------------------------------------------------------- source + sharpness match
src = 'assets/aroll_hi.mp4' if os.path.exists('assets/aroll_hi.mp4') else 'assets/aroll.mp4'
pre_blur = 0.0
if src.endswith('_hi.mp4'):
    sw, sh = probe_size(src)
    f0 = max(0, first_on)
    hi = next(reader(src, sw, sh, first=f0, last=f0))
    ref = next(reader('assets/aroll.mp4', W, H, first=f0, last=f0)).astype(np.float32)
    best = None
    tmp = dict(zoom_centre=list(zc), pre_blur=0.0)
    for s in (0.0, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.2):
        tmp['pre_blur'] = s
        p = C.plate_at(tmp, hi, 1.0)
        err = float(((p[300:1600, 150:930] - ref[300:1600, 150:930]) ** 2).mean())
        if best is None or err < best[1]:
            best = (s, err)
    pre_blur = best[0]
    say(f'source {src} ({sw}x{sh}); pre-blur {pre_blur} px matches aroll.mp4 sharpness (rms {best[1] ** .5:.2f})')
else:
    say('source assets/aroll.mp4 (no aroll_hi: the 3 percent push-in is an upscale; make the slot with --hi if the '
        'original is bigger than 1080 wide)')

pl.update(fonts=fonts, masthead=masthead, labels=labels, main=main, label_style=LABEL_STYLE, border=36,
          ink=dict(back=ink_back, front=ink_front, accent=accent, border=ink_back),
          dim_centre=[float(np.clip(hcx, 200, 880)), float(min(face_cy + 280, 960))], dim_edge=0.20, dim_top=dim_top,
          dim_top_to=float(max(700, mast_base + 240)), shadow_back=shadow_back,
          shadow_front=[0.30, 9.0, 4] if ink_front == CREAM else [0.0, 9.0, 4],
          matte_levels=[0.18, 0.52], pre_blur=pre_blur, src=src, grade=GRADE, active=[first_on, last_on],
          framing=choice, shot=shot)

cv = C.Cover(pl)
bad = cv.safe_problems()
if bad:
    sys.exit('outside the safe zone: ' + '; '.join(bad) + '. Shorten the text or split it with "\\n".')
if choice == 'behind':
    over = [ch for ch, a, b in cv.letter_x if b > face[0] and a < face[2]]
    say(f'letters over the head: {" ".join(over) or "none"} (E, L, Z, F there leave a horn over the head: pick another '
        'title if one is)')
for nte in notes:
    say(nte)
say(f'timing: cover in {t_in:.2f}s ({how_in}); cover line lands {t_land:.2f}s ({how_land}); '
    + ('holds to the last frame (OUT = cut)' if t_out is None else f'leaves {t_out:.2f}s to {t_out + OUT_DUR:.2f}s'))
say(f'layers: masthead, {len([lb for lb in labels if lb["layer"] == "back"])} label(s), '
    f'{"kicker, " if kicker else ""}{"cover line (" + main["pos"] + ")" if main else "no cover line (CAPTIONS=0)"}')
os.makedirs('work', exist_ok=True)
json.dump(pl, open('work/plan.json', 'w'), indent=1)

# ---------------------------------------------------------------------------------------------------- sounds + index.html
cues = []
if ENV['SFX']:
    files = C.make_sfx('assets_fx')
    for key, t in (('swell', t_in - 0.62), ('thump', t_land - 0.005)):
        path, length = files[key]
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(length - skip, DUR - t)
        if d > 0.05:
            cues.append(f'  <audio id="sfx_{key}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cues)}" data-volume="1"></audio>')

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

fi, fland = int(round(t_in * FPS)), int(round(t_land * FPS))
marks = sorted({0, first_on, fi + 12, fland - 3, fland + 2, min(N - 1, fland + 20), last_on - 8 if t_out else N - 2,
                N - 1} & set(range(N)))
stills = [min(N - 1, fland + 14), min(N - 1, fland + 40), fi + 20]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} GRADE={int(GRADE)} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(f) for f in (fi + 20, fland + 14, N - 1)) + '  (preview), then bake.py')
