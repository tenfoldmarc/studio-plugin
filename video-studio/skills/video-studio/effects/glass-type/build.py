#!/usr/bin/env python3
"""glass-type: one word as thick clear glass letters standing on the speaker's wall, bending the room behind them.

This file holds the CLIP block (the only thing you edit) and writes index.html, which plays assets/fx.mp4 (baked by
`glass.py bake`) with the speaker's audio and the effect's sounds (synthesised here into assets_fx/, seeded). Run from
the slot folder, after `glass.py measure` (it reads work/plan.json for the timing):
    python build.py            index.html
    SAFE=1 python build.py     also draws the safe zone (snapshots only, never in the render)
    SFX=0 python build.py      no sounds (the main reel has its own)
    CAPTIONS=0 / GRADE=0       change nothing here: the glass word is the caption for that word, and there is no grade
"""
import json
import os
import sys
import wave

import numpy as np

# ==== CLIP (edit this) ====
TEXT = 'DESIGN'               # the ONE word in glass: the word the line turns on, as he says it (8 letters or fewer read biggest)
T_IN = 'auto'                 # when it arrives: 'auto' = the spoken word matching TEXT in words.json, or a word ('design#2' = its 2nd time), or seconds. Re-measured on the audio
T_OUT = 'auto'                # when it leaves: 'auto' = HOLD seconds after it lands (always gone 6 frames before the slot ends), a word, seconds, or 'cut' (stays to the last frame: only when the reel cuts right after)
HOLD = 1.3                    # seconds it stands after landing (with T_OUT 'auto')
PLACE = 'auto'                # 'auto' = the biggest open wall near his head (printed by measure), 'above', 'left', 'right', or (x, y, width) in px for the word's top-left and width
MAX_HIDDEN = 0.10             # share of the letters he may stand in front of (he occludes the glass; no single letter more than 30%)
LEVEL = 'auto'                # 'auto' = level unless the wall's lines really slope at that height (then follows at most 4 deg), True = always level, or degrees
# ---- the look (defaults = the approved demo; take the buyer's caption font and colours when the reel has a style)
FONT, WEIGHT = 'Inter Tight', 900     # a family from assets/fonts/fonts.css and its weight. Heavy faces only: thin strokes leave no glass to bend the room through
CASE = 'upper'                # 'upper', 'lower', 'title' or 'as is'
STRETCH, TRACKING = 1.10, 0.035       # vertical stretch of the letters and letter spacing (em): the demo's tall condensed look
INK = '#0B1016'               # the dark glass rim, the hairline round each letter and the soft backing shade (a deep near-black; the buyer's darkest colour works)
ACCENT = '#FFF6EA'            # the light on the glass: the travelling highlight and the rim light (warm white; a pale tint of the buyer's accent works)
TINT = '#F2F8F4'              # the glass body colour, very pale (white = perfectly clear, a pale green = real window glass)
BACKING = 'auto'              # soft dark shade behind the letters, 0..1: 'auto' = strong over a window or a lamp, light on a wall
RIM_DARK = 'auto'             # dark glass edge, 0..1: 'auto' = by the light behind (stronger over bright)
RIM_LIGHT = 'auto'            # thin bright rim on the bevels that face the light, 0..2: 'auto' = stronger on a plain or dark wall
SHADOW = 'auto'               # the glass's shadow + caustic on the wall, 0..0.4: 'auto' = off on a dark wall, stronger on a plain one
LIGHT_FROM = (-0.7, -0.7)     # where the room's key light comes from in the picture (x, y; -1 = left / top): sets the shadow side and the rim light
IOR, BEVEL, DEPTH = 1.52, 15.0, 62.0  # glass: refractive index, bevel radius and thickness (canvas px of a 400 px tall word)
DISPERSION = 0.035            # rainbow split at the rims
KEY_GAIN = 0.50               # brightness of the travelling highlight on the flat faces
DRIFT = 1.0                   # the slow slide and turn while it stands (0 = dead still)
VOL_AIR, VOL_LAND, VOL_RING = 0.16, 0.10, 0.05   # sounds: air swell into the landing, soft low thump, faint glass ring (x0.75 applied). 0 = off
SEED = 3                      # the sounds' noise (same seed, same sound)
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SLOT = os.path.basename(HERE)
N = json.load(open('clip.json'))['frames']
FPS = 30
DUR = N / FPS
DUR_S = f'{DUR - .001:.3f}'           # 1 ms short so the render is exactly N frames
SAFE = os.environ.get('SAFE', '0') == '1'
SFX_ON = os.environ.get('SFX', '1') != '0'
SFX_GAIN = 0.75
SR = 48000

if not os.path.exists('work/plan.json'):
    sys.exit('work/plan.json is missing: run `glass.py measure` first')
plan = json.load(open('work/plan.json'))
if plan['N'] != N:
    sys.exit('work/plan.json is from another slot length: run `glass.py measure` again')
if not os.path.exists('assets/fx.mp4'):
    print('!! assets/fx.mp4 is missing: run `glass.py bake` before rendering')


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


def s_air(rng):
    """a soft low air swell that crests on the landing (1.0 s, crest at 0.62 s)"""
    n = int(SR * 1.0)
    t = np.arange(n) / SR
    lo, hi = band_noise(n, 120, 520, rng), band_noise(n, 500, 1600, rng)
    k = np.clip(t / 0.62, 0, 1) ** 2
    x = lo * (1 - 0.35 * k) + hi * 0.35 * k
    env = np.where(t < 0.62, (t / 0.62) ** 2.2, np.exp(-(t - 0.62) / 0.12))
    y = x * env
    return y / np.abs(y).max()


def s_land(rng):
    """a soft, low thump as the slab takes its weight (0.5 s)"""
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    f0 = 58 + 50 * np.exp(-t / 0.03)
    y = np.sin(2 * np.pi * np.cumsum(f0) / SR) * np.exp(-t / 0.11) * np.clip(t / 0.004, 0, 1)
    y += 0.15 * band_noise(n, 200, 900, rng) * np.exp(-t / 0.02)
    return y / np.abs(y).max()


def s_ring(rng):
    """a faint glass ring: a few inharmonic partials that decay (0.9 s)"""
    n = int(SR * 0.9)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for fq, a, d in ((2340, 1.0, 0.34), (3712, 0.6, 0.22), (5180, 0.35, 0.15), (6930, 0.2, 0.10)):
        y += a * np.sin(2 * np.pi * fq * (1 + 0.0004 * rng.standard_normal()) * t + rng.uniform(0, 6.28)) * np.exp(-t / d)
    y *= np.clip(t / 0.003, 0, 1)
    return y / np.abs(y).max()


def audio():
    if not SFX_ON:
        return []
    rng = np.random.default_rng(SEED)
    os.makedirs('assets_fx', exist_ok=True)
    t_in = plan['t_in']
    t_land = t_in + 0.30                                  # where the slab reads as landed (its thickness is most of the way)
    cues = [('glass-air', s_air(rng), t_land - 0.62, VOL_AIR), ('glass-land', s_land(rng), t_land - 0.01, VOL_LAND),
            ('glass-ring', s_ring(rng), t_land, VOL_RING)]
    if plan['t_out'] is not None:
        cues.append(('glass-air-out', s_air(np.random.default_rng(SEED + 1))[::-1].copy(), plan['t_out'] - 0.05, VOL_AIR * 0.5))
    out = []
    for i, (name, x, t, vol) in enumerate(cues):
        if vol <= 0:
            continue
        path = f'assets_fx/{name}.wav'
        wav(path, x * 0.9)
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(len(x) / SR - skip, DUR - t - 0.01)
        if d <= 0.05:
            continue
        out.append(f'  <audio id="sfx{i}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                   f'data-duration="{d:.3f}" data-track-index="{10 + i}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
cues = audio()
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
#fxv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR_S}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="2" data-volume="1"></audio>
{nl.join(cues)}
  <video id="fxv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.set({{}}, {{}}, {DUR_S});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open('index.html', 'w', encoding='utf-8').write(html)
print(f'wrote index.html: slot "{SLOT}", {N} frames, {len(cues)} sound cues' + (', SAFE guide ON (snapshots only)' if SAFE else ''))
