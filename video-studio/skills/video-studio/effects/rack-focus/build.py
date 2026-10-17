#!/usr/bin/env python3
"""rack-focus, step 1: measure the clip, place and size the title, time the pull, write work/plan.json, the three
sounds and index.html.

A cinema focus pull: a two-line title hangs close to the lens as soft bokeh discs, focus pulls to it on the key word
(the speaker and the room fall into true lens blur, the discs shrink into crisp type), then racks back to the speaker
and the title drifts out of the frame.

  PY build.py            measure + layout + plan + index.html (prints what it measured and what it chose)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no words: the pull goes to the points of light alone (the reel's captions carry the words)
  SFX=0                  no swells / thump
  GRADE=1                a touch richer colour while the title is sharp (default off: the reel grades)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import colorsys
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

import rack as R
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_LAND = 'auto'      # the word the focus lands on (title sharp): a word from words.json ('skill', or 'skill#2' for its
                     # 2nd time), seconds, or 'auto' (the longest word that leaves 1.6 s after it). Audio onset re-measured.
T_BACK = 'auto'      # when focus starts back to the speaker: 'auto' (HOLD seconds after the title is sharp), a word, or s
HOLD = 1.0           # seconds the title stays sharp when T_BACK is 'auto' (shortened if the slot ends too soon)
SMALL = 'THE ONE'    # the tracked caps line above the word: a few of the speaker's own words, '' for none
BIG = 'Word'         # the one word in the big serif: the key word of the sentence (the speaker's own word)
FONT = 'Instrument Serif'   # big word family: any family in assets/fonts/fonts.css (the buyer's caption font works)
ITALIC = True        # big word in the italic of FONT when the slot has one
WEIGHT = 400         # big word weight (variable fonts follow it; a static file stays what it is)
CASE = 'as typed'    # big word: 'as typed', 'upper', 'lower', 'title'
SMALL_FONT = 'Inter Tight'  # tracked caps family (keep it bold: thin caps vanish over the blurred picture)
SMALL_WEIGHT = 700   # tracked caps weight
SMALL_CASE = 'upper'  # tracked caps case
INK = (255, 248, 239)  # colour of the caps line (cream); (r, g, b)
ACCENT = 'ink'       # colour of the big word: 'ink' (same as INK) or (r, g, b), e.g. the buyer's highlight colour
ALIGN = 'left'       # 'left' (caps start over the word, the demo look) or 'centre'
BOKEH = 'auto'       # disc colour: 'auto' (from the lights in the room, kept off orange) or (r, g, b)
TITLE_CENTRE = 'auto'  # (x, y) of the sharp title block in 1080x1920 px; 'auto' = best spot off the face (printed)
SHOT = 'auto'        # 'auto' (from the head width), or force 'close' / 'medium' / 'wide' / 'none' (no person)
MAX_RADIUS = 'auto'  # room blur in px at full focus on the title; auto: close 30, medium 26, wide 22
SUBJECT_RATIO = 'auto'  # speaker's blur as a share of the room's; auto: close 0.62, medium 0.78, wide 0.88
REST_RADIUS = 'auto'  # disc size while the title is out of focus; auto: 0.31 (close) or 0.26 x the big word's size
BREATHING = 0.026    # the picture grows this much as the focus comes forward (a real lens breathes)
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
GRADE = os.environ.get('GRADE', '0') not in ('0', '')
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = R.W, R.H, R.FPS
Q = 4                                                    # measurement runs at a quarter of the size
RACK_IN, RACK_OUT, EXIT_DUR = 0.54, 0.58, 1.0

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
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
    i0, i1 = max(0, int((s - 0.15) * 100)), min(len(ENVL) - 1, int((s + 0.25) * 100))
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


late = [w for w in words if 0.75 <= w['start'] <= DUR - 1.9]
auto_land = DUR * 0.35
if late:
    best = max(late, key=lambda w: len(norm(w['text'])))
    hits = [w for w in words if norm(w['text']) == norm(best['text'])]
    auto_land = f"{best['text']}#{hits.index(best) + 1}"
t_on, how_land = when(T_LAND, auto_land)
t_to_title = t_on + 0.08 - RACK_IN / 2                  # the middle of the pull sits on the word's vowel
if t_to_title < 0.30:
    say(f'!! the landing word is at {t_on:.2f}s: too early for plain frames and the discs first. Pull moved to 0.30s; '
        'start the slot earlier for a better match.')
    t_to_title = 0.30
t_sharp = t_to_title + RACK_IN
if T_BACK == 'auto':
    t_back, how_back = t_sharp + HOLD, f'{HOLD:.1f}s after the title is sharp'
else:
    t_back, how_back = when(T_BACK, T_BACK)
    t_back -= 0.10                                        # start leaving just before the word
t_back_max = DUR - 0.14 - max(RACK_OUT, 0.10 + 0.94 * EXIT_DUR)
if t_back > t_back_max:
    say(f'!! focus back at {t_back:.2f}s would leave the title on screen at the end of the slot: moved to '
        f'{t_back_max:.2f}s (plain footage on the last frames).')
    t_back = t_back_max
if t_back - t_sharp < 0.55:
    sys.exit(f'RACK FOCUS DECLINES: the title would be sharp for only {max(0, t_back - t_sharp):.2f}s. Make the slot '
             f'about {0.6 - (t_back - t_sharp) + 0.2:.1f}s longer after the landing word, or land on an earlier word.')
t_show = max(0.12, t_to_title - 0.9)
fade_in = max(0.15, min(0.35, t_to_title - t_show))
t_gone = t_back + 0.10 + 0.94 * EXIT_DUR
say(f'timing: lands on {how_land}; pull {t_to_title:.2f} to {t_sharp:.2f}s, sharp until {t_back:.2f}s ({how_back}), '
    f'back by {t_back + RACK_OUT:.2f}s, title gone by {t_gone:.2f}s of {DUR:.2f}s')

# ---------------------------------------------------------------------------------------------------- measure
f_show, f_gone = int(t_show * FPS), min(N - 1, int(np.ceil(t_gone * FPS)))
qw, qh = W // Q, H // Q
have_cut = os.path.exists('assets/subject.webm')
mats = list(reader('assets/subject.webm', W, H, alpha=True, scale=(qw, qh))) if have_cut else []
if have_cut and len(mats) != N:
    say(f'!! the cutout has {len(mats)} frames, the a-roll {N}: it will drift. Re-make the slot.')
mats = [m.astype(np.float32) / 255.0 for m in mats] or [np.zeros((qh, qw), np.float32)] * N
span = mats[f_show:f_gone + 1] or mats


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head in full-size px, or None when nobody is in the frame."""
    m = m > 0.5
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


heads = [head_of(m) for m in span]
found = [h for h in heads if h]
if SHOT != 'auto':
    shot = SHOT
elif len(found) < 0.5 * len(span):
    shot = 'none'
else:
    hw_med = float(np.median([h[2] for h in found]))
    shot = 'close' if hw_med > 300 else ('medium' if hw_med > 150 else 'wide')
faces = []                                # per-frame face box (x0, y0, x1, y1), full-size px
if found and shot != 'none':
    hw_cap = 1.25 * float(np.median([h[2] for h in found]))   # a hand raised to the head must not inflate the face
    for top, cx, hw in found:
        hw = min(hw, hw_cap)
        faces.append((cx - 0.62 * hw, top - 0.08 * hw, cx + 0.62 * hw, top + 1.45 * hw))
    fa = np.array(faces)                  # one box over the span, robust to a few odd frames (3rd to 97th percentile)
    faces = [(np.percentile(fa[:, 0], 3), np.percentile(fa[:, 1], 3), np.percentile(fa[:, 2], 97),
              np.percentile(fa[:, 3], 97))]
# where the speaker comes and goes (hands waving, leaning): a blurred moving hand behind the type hurts reading
motion = cv2.GaussianBlur(np.std(np.stack(span), axis=0).astype(np.float32), (0, 0), 3)

# the room: brightness under the title, the colour of its lights, how much of it the camera clipped
samples = sorted(set(np.linspace(0, N - 1, 6).astype(int)))
lum, light_cols, clipped = [], [], []
prev, moving = None, np.zeros((qh, qw), np.float32)
for i, fr in enumerate(reader('assets/aroll.mp4', W, H, scale=(qw, qh))):
    if f_show <= i <= f_gone:             # hands moving in front of the body do not change the cutout: use the picture
        g = cv2.GaussianBlur(fr.astype(np.float32) @ np.float32([0.3, 0.59, 0.11]) / 255.0, (0, 0), 1.5)
        if prev is not None:
            moving += np.abs(g - prev)
        prev = g
    if i not in samples:
        continue
    lin = R.SRGB2LIN[fr]
    lm = lin @ R.LUMA
    lum.append(lm)
    room = mats[min(i, len(mats) - 1)] < 0.1
    if room.sum() > 50:
        rl = lm[room]
        clipped.append(float((rl > 0.80).mean()))
        lo, hi = np.percentile(rl, 99.0), np.percentile(rl, 99.85)
        sel = room & (lm >= lo) & (lm <= hi)
        if sel.sum() > 3:
            light_cols.append(fr[sel].reshape(-1, 3).mean(axis=0))
lum = cv2.GaussianBlur(np.mean(lum, axis=0), (0, 0), 8)
moving = cv2.GaussianBlur(moving / max(1, f_gone - f_show), (0, 0), 3)
motion = np.maximum(motion, 8.0 * moving)
clip_share = float(np.mean(clipped)) if clipped else 0.0
hdr_g = float(np.interp(clip_share, [0.004, 0.04], [11.0, 2.5]))
say(f'measured: shot {shot}' + (f' (head {np.median([h[2] for h in found]):.0f}px wide, top {np.percentile([h[0] for h in found], 5):.0f})' if found and shot != 'none' else '')
    + f', room clipped {clip_share * 100:.1f}% -> highlight lift x{1 + hdr_g:.1f} '
    + ('(point lights bloom into discs)' if hdr_g > 8 else '(big bright areas: kept gentle)'))

if BOKEH == 'auto':
    if light_cols:
        r_, g_, b_ = np.mean(light_cols, axis=0) / 255.0
        hh, ss, _ = colorsys.rgb_to_hsv(r_, g_, b_)
        hue = hh * 360
        if ss < 0.08:
            hue, sat, why = 48.0, 0.18, 'neutral room: warm white'
        elif not (8 <= hue <= 75):
            hue, sat, why = 48.0, 0.12, f'cool light (hue {hue:.0f}, a window or daylight): near white, never tinted blue'
        else:
            if 8 <= hue < 44:
                hue = 46.0                                  # never orange: lamp warmth reads as butter
            sat = float(np.clip(ss * 1.3, 0.14, 0.50))
            why = f'room lights hue {hh * 360:.0f}'
        bok = tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(hue / 360, sat, 1.0))
    else:
        bok, why = (255, 226, 160), 'no room measured: butter'
    say(f'bokeh colour {bok} ({why})')
else:
    bok = tuple(BOKEH)

# ---------------------------------------------------------------------------------------------------- the title
table = R.font_table(os.path.join('assets', 'fonts'))
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
big_font = R.pick_font(table, FONT, WEIGHT, ITALIC)
small_font = R.pick_font(table, SMALL_FONT, SMALL_WEIGHT)
ink = tuple(INK)
acc = ink if ACCENT == 'ink' else tuple(ACCENT)
title = dict(small=R.cased(SMALL, SMALL_CASE), big=R.cased(BIG, CASE), big_font=big_font, small_font=small_font,
             italic=bool(ITALIC) and 'italic' in os.path.basename(big_font[0]).lower(), big_px=236, small_px=31,
             track_em=0.44, line_gap=30, ink=list(ink), accent=list(acc), align='left' if ALIGN == 'left' else 'centre',
             bokeh=list(bok), glints=7, seed=5)
MAX_BLOCK_W = 700 if shot in ('medium', 'wide', 'none') else 640
for _ in range(12):                       # fit: big word down from 236 px until the block fits; caps tracking after
    mt = R.title_metrics(title)
    if mt['bw'] - 2 * mt['pad'] <= MAX_BLOCK_W:
        break
    if mt['big_w'] > MAX_BLOCK_W and title['big_px'] > 120:
        title['big_px'] = max(120, int(title['big_px'] * MAX_BLOCK_W / mt['big_w']) - 1)
    elif title['track_em'] > 0.18:
        title['track_em'] = round(title['track_em'] - 0.06, 2)
    else:
        break
mt = R.title_metrics(title)
if mt['bw'] - 2 * mt['pad'] > MAX_BLOCK_W + 40:
    sys.exit(f'RACK FOCUS DECLINES: the title is {mt["bw"] - 2 * mt["pad"]}px wide even at the smallest size. '
             'Use a shorter word (BIG) or fewer caps (SMALL).')
bw, bh = mt['bw'] * 1.03, mt['bh'] * 1.03                 # it drifts a little toward the lens while it is up
ink_w, ink_h = bw - 2 * mt['pad'], bh - 2 * mt['pad']
r_share = 0.31 if shot == 'close' else 0.26             # smaller discs where the speaker is small in the frame
r_rest = float(np.clip(r_share * title['big_px'], 40, 80)) if REST_RADIUS == 'auto' else float(REST_RADIUS)
title['glints'] = int(np.clip(round(ink_w / 68), 6, 13))
say(f'title: "{title["small"]}" / "{title["big"]}" in {os.path.basename(big_font[0])} {title["big_px"]}px + '
    f'{os.path.basename(small_font[0])} {title["small_px"]}px, block {ink_w:.0f}x{ink_h:.0f}, '
    f'{title["glints"]} discs of {r_rest:.0f}px at rest')

# ---------------------------------------------------------------------------------------------------- placement
clear = 0.25 * r_rest + 12                # the discs spread a little past the letters: keep that much off the face
if faces:
    fb = np.array(faces)
    face_cx = float(np.median((fb[:, 0] + fb[:, 2]) / 2))
    face_bot = float(np.percentile(fb[:, 3], 90))
    pref = (face_cx, face_bot + 30 + bh / 2)
else:
    fb = np.zeros((0, 4))
    pref = (W / 2, 1180.0)


def fits_safe(cx, cy):
    x0, y0, x1, y1 = cx - ink_w / 2, cy - ink_h / 2, cx + ink_w / 2, cy + ink_h / 2
    # the sharp letters stay inside; the resting discs may spill a little past the bottom line (out of focus light)
    if x0 < R.SAFE['side'] or x1 > W - R.SAFE['side'] or y0 < R.SAFE['top'] + 10 or y1 > R.SAFE['bottom'] - max(6, 0.2 * r_rest):
        return False
    if y1 > R.SAFE['right_low'][0] and x1 > W - R.SAFE['right_low'][1]:
        return False
    return True


def hits_face(cx, cy):
    if not len(fb):
        return False
    x0, y0, x1, y1 = cx - ink_w / 2 - clear, cy - ink_h / 2 - clear, cx + ink_w / 2 + clear, cy + ink_h / 2 + clear
    return bool(((fb[:, 0] < x1) & (fb[:, 2] > x0) & (fb[:, 1] < y1) & (fb[:, 3] > y0)).any())


def region(mp, cx, cy):
    x0, y0 = int(max(0, (cx - ink_w / 2) / Q)), int(max(0, (cy - ink_h / 2) / Q))
    x1, y1 = int(min(qw, (cx + ink_w / 2) / Q)), int(min(qh, (cy + ink_h / 2) / Q))
    return float(mp[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 1.0


def cost(cx, cy):
    l_ = region(lum, cx, cy)
    mo = region(motion, cx, cy)
    d = np.hypot(cx - pref[0], (cy - pref[1]) * 0.8) / 1000
    return 1.2 * l_ + 2.5 * mo + 0.6 * d, l_, mo


if TITLE_CENTRE != 'auto':
    centre = tuple(float(v) for v in TITLE_CENTRE)
    best = (cost(*centre)[0], centre[0], centre[1], *cost(*centre)[1:])
    say(f'title centre {centre} (from CLIP)' + ('  !! it touches the face' if hits_face(*centre) else '')
        + ('  !! outside the safe zone' if not fits_safe(*centre) else ''))
else:
    cands = []
    for cy in np.arange(R.SAFE['top'] + ink_h / 2 + 10, R.SAFE['bottom'] - ink_h / 2 - 5, 12):
        for cx in np.arange(R.SAFE['side'] + ink_w / 2, W - R.SAFE['side'] - ink_w / 2 + 1, 12):
            if fits_safe(cx, cy) and not hits_face(cx, cy):
                c, l_, mo = cost(cx, cy)
                cands.append((c, float(cx), float(cy), l_, mo))
    if not cands:
        sys.exit('RACK FOCUS DECLINES: the face fills every spot where the title could sit inside the safe zone. '
                 'Pick a moment with room below the chin or beside the head, or a wider shot.')
    best = min(cands)
    centre = (best[1], best[2])
    if os.environ.get('DEBUG'):
        for c in sorted(cands)[:3] + sorted(c for c in cands if faces and c[2] > face_bot)[:3]:
            say(f'   candidate ({c[1]:.0f}, {c[2]:.0f}) cost {c[0]:.3f} room {c[3]:.2f} moving {c[4]:.3f}')
    say(f'title centre ({centre[0]:.0f}, {centre[1]:.0f}): room under it {best[3]:.2f} (0 dark, 1 white), '
        f'hand movement {best[4]:.3f}, ' + ('below the chin' if faces and centre[1] > face_bot else
                                            'beside the speaker' if faces else 'no speaker found: lower middle'))
lum_under = best[3]
backing = float(np.clip((lum_under - 0.20) * 1.1, 0, 0.42))
if backing > 0:
    say(f'bright room behind the title: a soft shade of {backing:.2f} comes in with the focus so cream type reads')

# shot settings (CLIP overrides)
AUTO = {'close': (30.0, 0.62), 'medium': (26.0, 0.78), 'wide': (22.0, 0.88), 'none': (26.0, 1.0)}
max_r = AUTO[shot][0] if MAX_RADIUS == 'auto' else float(MAX_RADIUS)
s_ratio = AUTO[shot][1] if SUBJECT_RATIO == 'auto' else float(SUBJECT_RATIO)
say(f'lens: room blur {max_r:.0f}px, speaker {s_ratio:.2f} of that ({shot} shot)')

# exit: fall away under the lens if the title sits below the face, else slide off the side away from the face
if faces and centre[1] < face_bot:
    sgn = -1 if centre[0] < face_cx else 1
    exit_vec = (sgn * 760.0, 120.0)
else:
    exit_vec = (-110.0 if centre[0] > W / 2 else 110.0, 640.0)

pl = dict(n=N, fps=FPS, t_to_title=t_to_title, t_back=t_back, rack_in=RACK_IN, rack_out=RACK_OUT, t_show=t_show,
          fade_in=fade_in, exit_dur=EXIT_DUR, exit_vec=list(exit_vec), centre=list(centre), block=[bw, bh],
          rest_radius=r_rest, glint_level=0.50, max_radius=max_r, subject_ratio=s_ratio, breathing=BREATHING,
          hdr_t=0.80, hdr_g=hdr_g, backing=backing, title=title, captions=ENV['CAPTIONS'], grade=GRADE,
          cutout=have_cut, shot=shot)
os.makedirs('work', exist_ok=True)
json.dump(pl, open('work/plan.json', 'w'), indent=1)

# ---------------------------------------------------------------------------------------------------- sounds + index.html
cues = []
if ENV['SFX']:
    files = R.make_sfx('assets_fx')
    for key, t in (('pull', t_to_title - 0.12), ('land', t_sharp - 0.06), ('back', t_back - 0.04)):
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

fi, fs, fb_ = int(round(t_to_title * FPS)), int(round(t_sharp * FPS)), int(round(t_back * FPS))
marks = sorted({0, max(0, int(t_show * FPS) + 8), fi + 8, fs + 2, (fs + fb_) // 2, fb_ + 10,
                min(N - 1, int(t_gone * FPS) - 4), N - 1} & set(range(N)))
stills = [max(0, fi - 4), min(N - 1, fs + 6), min(N - 1, fb_ + 9)]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} GRADE={int(GRADE)} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(f) for f in (max(0, fi - 4), fs + 6, fb_ + 9)) + ' -g  (preview), then bake.py')
