#!/usr/bin/env python3
"""Vertigo, step 3: the dolly zoom from one locked-off shot. The speaker stays still while the room behind them
stretches away, holds, then springs back through neutral and settles on the untouched picture.

build.py reads work/measure.json (prep.py), words.json and clip.json, picks the variant for this footage (prints
which and why, or stops with a plain reason), and writes:
  work/curve.json     the move, for bake.py
  index.html          plays assets/fx.mp4 (the baked picture) + the effect's own words + its two sounds
  assets_fx/*.wav     the riser and the soft air on the snap, generated here (seeded, identical every run)
  work/marks.json     the frames post.py pulls into the contact sheet
Run from the slot folder: PY build.py   (switches: SAFE=1 CAPTIONS=0 SFX=0 GRADE=1)
"""
import json
import math
import os
import re
import sys
import wave

import cv2
import numpy as np

from vcore import FPS, H, W, Warp, here, load_json, smoothstep, vertigo

# ==== CLIP (edit this) ====
PUSH_WORD = None      # word where the room starts to stretch (as spelled in words.json; 'word#2' = its 2nd time). None = auto
PEAK_WORD = None      # the push lands at the END of this word. None = auto (about 0.6 s after the push starts)
RELEASE_WORD = None   # the room snaps back on this word. None = auto (first word about 0.6 s after the peak)
T_START = None        # seconds, overrides PUSH_WORD (find it with onsets.py: a frame or two before the stressed vowel)
T_PEAK = None         # seconds, overrides PEAK_WORD
T_RELEASE = None      # seconds, overrides RELEASE_WORD
SCALE = None          # room size at the peak. None = chosen from the footage (1.12 to 1.33, printed with the reason)
ORIGIN = None         # (x, y) vanishing point. None = measured head centre. Only move it if work/plate_check.jpg is off
SEAT_Y = None         # row from which the room stays pinned (chair, sofa, desk, floor). None = measured (chin + 3 heads)
FORCE = False         # True = render even when the footage check declines (only after you looked and it holds up)
CAPTIONS = 'auto'     # 'auto' = the slot's words from the push on, max 3 per line; [] = none; or by hand:
                      #   [(t_out, [(word, t_in, accent True/False), ...]), ...]   times in seconds from words.json
ACCENT_WORDS = None   # 'auto' captions: words drawn in ACCENT. None = the peak word and the very last word
CAP_Y = None          # caption centre line (px). None = measured: chest band under the chin, inside the safe zone
CAP_SIZE = 92         # caption size px; shrinks itself until the line fits 820 px
FONT = 'Inter Tight'  # caption family from assets/fonts/fonts.css: use the buyer's saved caption font
WEIGHT = 900          # its weight (must exist in fonts.css for that family)
CASE = 'upper'        # 'upper' / 'lower' / 'as-is'
INK = '#FFFFFF'       # word colour
ACCENT = '#FAE67A'    # accent word colour (the buyer's highlight colour)
SFX_GAIN = 1.0        # 1.0 = low riser into the push + soft air on the snap at 0.75x template level; 0 = silent
GRADE = ''            # CSS filter on the picture (e.g. 'contrast(1.03) saturate(1.04)'); applied only with GRADE=1
# ==== END CLIP ====

ON = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
ON['GRADE'] = os.environ.get('GRADE', '0') == '1'
SAFE = os.environ.get('SAFE', '0') == '1'
NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

# the look of the move (approved demo values; not per clip)
CREEP, SPRING_ZETA, SPRING_T_MIN, SETTLE = 0.035, 0.37, 0.235, [0.55, 0.85]
SHUTTER, EDGE_BLUR, VIGNETTE, SHADOW, SQUEEZE, LENS_K = 0.70, 0.012, 0.16, 0.30, 0.10, 0.10

if not os.path.exists(here('work', 'measure.json')):
    sys.exit('work/measure.json is missing: run prep.py first')
M = load_json(here('work', 'measure.json'))
NFR = M['frames']
DUR = NFR / FPS
hw, chin = M['head']['w'], M['head']['chin']
words = load_json(here('words.json')) if os.path.exists(here('words.json')) else []
words = [dict(w, key=re.sub(r"[^a-z0-9']", '', w['text'].lower())) for w in words]


def decline(msg):
    print(f'DECLINE: {msg}')
    if not FORCE:
        sys.exit(1)
    print('  (FORCE = True: rendering anyway)')


def find_word(spec):
    name, _, nth = spec.lower().partition('#')
    name = re.sub(r"[^a-z0-9']", '', name)
    hits = [w for w in words if w['key'] == name]
    if len(hits) < int(nth or 1):
        sys.exit(f'word "{spec}" is not in words.json (words: {" ".join(w["text"] for w in words)})')
    return hits[int(nth or 1) - 1]


# ------------------------------------------------------------------------------------------------ timing
why = []
if T_START is None and PUSH_WORD:
    T_START = find_word(PUSH_WORD)['start'] - 0.10
if T_START is None:                       # auto: first real word after 0.35 s, leaving room for the rest
    cand = [w for w in words if 0.35 <= w['start'] <= DUR - 2.2]
    pick = next((w for w in cand if len(w['key']) >= 4), cand[0] if cand else None)
    T_START = (pick['start'] - 0.10) if pick else max(0.4, DUR * 0.22)
    why.append(f'push auto on "{pick["text"]}"' if pick else 'push auto at 22% of the slot')
T_START = max(0.17, T_START)
if T_PEAK is None and PEAK_WORD:
    w = find_word(PEAK_WORD)
    T_PEAK = w['start'] + 0.6 * (w['end'] - w['start'])
if T_PEAK is None:
    ends = [w for w in words if T_START + 0.45 <= w['start'] + 0.6 * (w['end'] - w['start']) <= T_START + 0.9
            and w['start'] > T_START + 0.15]                     # a later word than the one the push starts on
    w = min(ends, key=lambda w: abs(w['start'] + 0.6 * (w['end'] - w['start']) - (T_START + 0.62))) if ends else None
    T_PEAK = (w['start'] + 0.6 * (w['end'] - w['start'])) if w else T_START + 0.62
    PEAK_WORD = w['text'] if w else None
    why.append(f'peak auto on "{w["text"]}"' if w else 'peak auto 0.62 s after the push')
T_PEAK = max(T_PEAK, T_START + 0.40)
if T_RELEASE is None and RELEASE_WORD:
    T_RELEASE = find_word(RELEASE_WORD)['start'] - 0.04
if T_RELEASE is None:
    rel = [w for w in words if T_PEAK + 0.55 <= w['start'] <= DUR - 1.0]
    T_RELEASE = (rel[0]['start'] - 0.04) if rel else T_PEAK + 0.75
    why.append(f'release auto on "{rel[0]["text"]}"' if rel else 'release auto 0.75 s after the peak')
T_RELEASE = max(T_RELEASE, T_PEAK + 0.25)
room = DUR - 2 / FPS - T_RELEASE
if room < SETTLE[1]:
    if room < 0.5:
        decline(f'the line ends {room:.2f} s after the snap back: the slot needs about 0.9 s of footage after the '
                'release word (make the slot longer, or release earlier)')
    SETTLE = [0.65 * room, room]
    why.append(f'settle squeezed to {room:.2f} s to hand back plain footage on the last frame')

# ------------------------------------------------------------------------------------------------ footage check + scale
origin = tuple(ORIGIN) if ORIGIN else tuple(M['origin'])
seat_y = float(SEAT_Y) if SEAT_Y else M['seat_y']
shoulder_y = min(M['shoulder_y'], seat_y - 120)
variant = [M['shot'], M['drift']]
if M['room_frac'] < 0.10:
    decline('you fill almost the whole frame, so there is too little room behind you to stretch '
            '(it needs at least a strip of room beside or above your head)')
if M['room_texture'] < 0.012:
    decline('the wall behind you is plain, so the stretch has nothing to show: it needs some lines or things '
            'behind you (a door, a shelf, a picture, a window)')
base = {'wide': 1.33, 'medium': 1.30, 'close': 1.22}[M['shot']]
if M['drift'] == 'moving':
    base = 1 + (base - 1) * 0.85
    why.append('handheld: a little gentler, the plate only lines up to a few px')
hole = cv2.imread(here('work', 'hole.png'), 0) > 0
amed = cv2.imread(here('work', 'alpha_med.png'), 0)
FILL = M.get('fill', 'plate')
if FILL == 'live':                     # no plate lines up: everything behind the speaker is filled frame by frame
    hole = cv2.dilate((amed > 4).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    base = min(base, 1.20)
    why.append(f'the camera moves through the room (plate misses by {M["plate_err"]:.0f} levels), so each frame '
               'fills the room behind the speaker from itself and the stretch stays at 1.20 or less')
warp = Warp(origin, shoulder_y, seat_y, SQUEEZE, LENS_K)


def fake_area(s):
    """Share of a head-sized area that shows painted-in room (never seen) at scale s, plus what it is weighed by."""
    mx, my = warp.maps(s)
    src_hole = cv2.remap(hole.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT_101) > 0
    shown = src_hole & (amed < 30)
    return float(shown.sum()) / (hw * hw)


busy = 0.5 + 8.0 * M['ring_busy']                  # a busy background right behind the speaker shows fill more
if SCALE is None:
    s, chosen = base, None
    while s >= 1.119:
        f = fake_area(s) * busy
        if f <= 0.9:
            chosen = s
            break
        s = round(s - 0.03, 3)
    if chosen is None:
        decline(f'the room right behind you is never seen in this clip and the fill would show even at a gentle '
                f'stretch (fake {fake_area(1.12) * busy:.2f}). Use a take where you lean or move a little, or run '
                f'more.py so the plate sees more of the room')
        chosen = 1.12
    if chosen < base:
        why.append(f'gentler stretch {chosen:.2f} instead of {base:.2f}: the never-seen room behind you would show '
                   f'(fake {fake_area(base) * busy:.2f} > 0.9)')
    SCALE = chosen
print(f'variant: {"/".join(variant)} shot, scale {SCALE:.2f}, origin ({origin[0]:.0f}, {origin[1]:.0f}), '
      f'pinned from y {seat_y:.0f}, fake {fake_area(SCALE) * busy:.2f} (limit 0.9), room texture '
      f'{M["room_texture"]:.3f}, ring busy {M["ring_busy"]:.3f}, extra plate frames {M["extra_frames"]}')
for w_ in why:
    print('  ' + w_)
print(f'move: push {T_START:.2f}s -> peak {T_PEAK:.2f}s -> release {T_RELEASE:.2f}s -> plain from '
      f'{T_RELEASE + SETTLE[1]:.2f}s (slot {DUR:.2f}s)')

curve = dict(t_start=T_START, t_peak=T_PEAK, t_release=T_RELEASE, scale=SCALE, creep=CREEP, spring_zeta=SPRING_ZETA,
             spring_t_min=SPRING_T_MIN, settle=SETTLE, origin=list(origin), shoulder_y=shoulder_y, seat_y=seat_y,
             shutter=SHUTTER, edge_blur=EDGE_BLUR, vignette=VIGNETTE, shadow=SHADOW, squeeze=SQUEEZE, lens_k=LENS_K,
             frames=NFR, ref=M['ref'], fill=FILL)
json.dump(curve, open(here('work', 'curve.json'), 'w'), indent=1)
print('scale per 3 frames: ' + ' '.join(f'{vertigo((i + .5) / FPS, curve):.3f}' for i in range(0, NFR, 3)))

# ------------------------------------------------------------------------------------------------ captions
fonts_css = open(here('assets', 'fonts', 'fonts.css')).read() if os.path.exists(here('assets', 'fonts', 'fonts.css')) else ''
if f"'{FONT}'" not in fonts_css:
    print(f'!! font "{FONT}" is not in assets/fonts/fonts.css: the words fall back to sans-serif')
if CAPTIONS == 'auto':
    acc = {re.sub(r"[^a-z0-9']", '', a.lower()) for a in (ACCENT_WORDS or [])}
    span = [w for w in words if T_START - 0.05 <= w['start'] < min(DUR - 0.3, T_RELEASE + 0.3)]
    stop = next((k for k, w in enumerate(span) if w['start'] >= T_RELEASE - 0.1 and re.search(r'[.,!?]$', w['text'])), None)
    span = span[:stop + 1] if stop is not None else span      # end on the sentence the snap lands in
    if ACCENT_WORDS is None and span:
        acc = {span[-1]['key']} | ({re.sub(r"[^a-z0-9']", '', PEAK_WORD.lower().split('#')[0])} if PEAK_WORD else set())
    lines, cur = [], []
    wide = lambda ws: sum(len(x['key']) for x in ws) * 0.64 * CAP_SIZE + 0.26 * CAP_SIZE * (len(ws) - 1)
    for k, w in enumerate(span):
        cur.append(w)
        gap = span[k + 1]['start'] - w['end'] if k + 1 < len(span) else 9
        nxt = cur + [span[k + 1]] if k + 1 < len(span) else cur
        if len(cur) == 3 or re.search(r'[.,!?]$', w['text']) or gap > 0.35 or wide(nxt) > 820:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    CAPTIONS = []
    for j, ln in enumerate(lines):
        t_out = lines[j + 1][0]['start'] if j + 1 < len(lines) else DUR - 3 / FPS
        CAPTIONS.append((t_out, [(re.sub(r'[.,!?;:]+$', '', w['text']), w['start'], w['key'] in acc) for w in ln]))
size = CAP_SIZE
for _, ws in CAPTIONS:
    est = sum(len(t) for t, _, _ in ws) * 0.64 * size + 0.26 * size * (len(ws) - 1)
    if est > 820:
        size = min(size, int(size * 820 / est))
if CAP_Y is None:
    CAP_Y = chin + 0.75 * hw + size * 0.5
    floor_y = 1470 - size * 0.62 - 10
    if CAP_Y > floor_y:
        CAP_Y = floor_y if floor_y - size * 0.55 > chin + 0.2 * hw else M['head']['top'] - 0.35 * hw - size * 0.5
    if CAP_Y - size * 0.6 < 220:
        print('!! no room for the effect\'s words outside the face: captions off (let the reel caption this slot)')
        CAPTIONS = []
cap_x = float(np.clip(M['head']['cx'], 35 + 430, 980 - 430))
if CAPTIONS:
    print(f'captions: {len(CAPTIONS)} lines, size {size}px, centre y {CAP_Y:.0f}, x {cap_x:.0f}: '
          + ' / '.join(' '.join(t + ('*' if a else '') for t, _, a in ws) for _, ws in CAPTIONS))


def captions_html():
    if not (ON['CAPTIONS'] and CAPTIONS):
        return [], []
    html, tw = [], []
    for j, (t_out, ws) in enumerate(CAPTIONS):
        spans = ''.join(f'<span class="w{" a" if a else ""}" id="c{j}_{k}">{t}</span>' for k, (t, _, a) in enumerate(ws))
        html.append(f'<div class="line" id="l{j}" style="top:{CAP_Y - size * 0.55:.0f}px;font-size:{size}px">{spans}</div>')
        for k, (t, t_in, _) in enumerate(ws):
            t0 = max(0.0, t_in - 1.4 / FPS)
            tw.append(f"tl.fromTo('#c{j}_{k}',{{opacity:0,scale:.78,y:16}},{{opacity:1,scale:1,y:0,duration:.2,"
                      f"ease:'back.out(1.9)'}},{t0:.4f});")
        t_gone = t_out - 1.4 / FPS                 # gone before the next line's first word starts to pop
        tw.append(f"tl.to('#l{j}',{{opacity:0,scale:.95,duration:.067,ease:'none'}},{max(0, t_gone - .067):.4f});")
    return html, tw


# ------------------------------------------------------------------------------------------------ sounds (generated)
SR = 48000


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    pcm = (np.stack([x, x], 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def one_pole(x, fc):
    """Time-varying one-pole low-pass (fc in Hz per sample)."""
    a = 1 - np.exp(-2 * np.pi * np.asarray(fc, np.float64) / SR) * np.ones(len(x))
    y = np.zeros(len(x))
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def riser(d):
    rng = np.random.default_rng(32)
    n = int(d * SR)
    t = np.arange(n) / SR
    u = t / d
    noise = one_pole(one_pole(rng.standard_normal(n), 160 + 520 * u ** 1.5), 200 + 560 * u ** 1.5)
    f = 62 + 40 * u ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    x = noise / (np.abs(noise).max() + 1e-9) * 0.8 + tone * 0.35
    env = smoothstep(0, 0.35, t) * (0.25 + 0.75 * u ** 1.6) * (1 - smoothstep(d - 0.22, d, t))
    x = x * env
    return x / (np.abs(x).max() + 1e-9) * 0.075 * SFX_GAIN


def air(d=0.5):
    rng = np.random.default_rng(33)
    n = int(d * SR)
    t = np.arange(n) / SR
    w = rng.standard_normal(n)
    band = one_pole(w, 2600 - 1800 * t / d) - one_pole(w, 380)
    env = smoothstep(0, 0.07, t) * np.exp(-t / 0.16) * (1 - smoothstep(d - 0.1, d, t))
    x = band * env
    return x / (np.abs(x).max() + 1e-9) * 0.11 * SFX_GAIN


def audio_html():
    if not (ON['SFX'] and SFX_GAIN > 0):
        return []
    os.makedirs(here('assets_fx'), exist_ok=True)
    r0 = max(0.0, T_START - 0.45)
    rd = T_PEAK + 0.12 - r0
    write_wav(here('assets_fx', 'vertigo-riser.wav'), riser(rd))
    write_wav(here('assets_fx', 'vertigo-air.wav'), air(0.5))
    a0 = max(0.0, T_RELEASE - 0.05)
    ad = min(0.5, DUR - a0)
    return [f'<audio id="sfx0" src="assets_fx/vertigo-riser.wav" data-start="{r0:.3f}" data-media-start="0" '
            f'data-duration="{rd:.3f}" data-track-index="10" data-volume="1"></audio>',
            f'<audio id="sfx1" src="assets_fx/vertigo-air.wav" data-start="{a0:.3f}" data-media-start="0" '
            f'data-duration="{ad:.3f}" data-track-index="11" data-volume="1"></audio>']


# ------------------------------------------------------------------------------------------------ index.html
TRANSFORM = {'upper': 'uppercase', 'lower': 'lowercase'}.get(CASE, 'none')
GRADE_CSS = f';filter:{GRADE}' if ON['GRADE'] and GRADE else ''
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#fxv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover;z-index:0{GRADE_CSS}}}
.line{{position:absolute;left:{cap_x - 540:.0f}px;width:1080px;text-align:center;white-space:nowrap;color:{INK};z-index:8;
  font-family:'{FONT}',sans-serif;font-weight:{WEIGHT};text-transform:{TRANSFORM};letter-spacing:-.03em;line-height:1.1;
  text-shadow:0 8px 36px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35)}}
.w{{display:inline-block;margin:0 .13em;transform-origin:50% 62%;opacity:0}}
.a{{color:{ACCENT}}}
'''
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
c_html, c_tw = captions_html()
nl = '\n'
html = f'''<!doctype html>
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
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio_html())}
  <video id="fxv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
{nl.join(c_html)}
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(c_tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open(here('index.html'), 'w').write(html)

f = lambda t: int(min(NFR - 1, max(0, round(t * FPS))))
mid = (T_START + T_PEAK) / 2
marks = sorted({0, f(T_START), f(mid), f(T_PEAK), f((T_PEAK + T_RELEASE) / 2), f(T_RELEASE + SPRING_T_MIN),
                f(T_RELEASE + SETTLE[1]), NFR - 1})
json.dump({'name': NAME, 'frames': NFR, 'marks': marks, 'stills': [f(mid) + 2, f((T_PEAK + T_RELEASE) / 2),
                                                                   f(T_RELEASE + SPRING_T_MIN)]},
          open(here('work', 'marks.json'), 'w'))
print(f'wrote index.html + work/curve.json   slot "{NAME}"  {NFR} frames   next: bake.py')
