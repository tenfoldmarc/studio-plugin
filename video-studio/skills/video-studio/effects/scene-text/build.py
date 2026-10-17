#!/usr/bin/env python3
"""scene-text: a small word prints across the speaker's real wall like wallpaper, behind him and behind the things on
the wall, then 1 to 3 big painted words land on it, lit like the wall. The print lifts off, the big words follow, and
the slot ends on the plain picture.

This file holds the CLIP block (the only thing you edit) and writes index.html, which plays assets/fx.mp4 (baked by
`scene.py bake`) with his audio and the effect's sounds. Run from the slot folder:
    python build.py            index.html
    SAFE=1 python build.py     also draws the safe zone (snapshots only, never in the render)
    SFX=0 python build.py      no sounds (the main reel has its own)
    CAPTIONS=0 / GRADE=0       change nothing here: the big words are the caption for those words, and there is no grade
"""
import json
import os
import sys

# ==== CLIP (edit this) ====
PRINT_TEXT = 'YAPPING'        # the small word printed across his wall, over and over: the line's loudest idea, 1 or 2 short words
PRINT_FRAME = 20              # frame the print starts spreading out from behind his head: the frame he says that word (onsets.py, column "swap")
HERO = [(69, 'STAND'), (77, 'OUT')]   # the 1 to 3 big painted words, each (frame it lands, 'WORD'). Frames from onsets.py; a frame late beats a frame early. [] = print only
CLEAR_FRAME = None            # frame the print lifts off again. None = 32 frames after the last big word
OUT_FRAME = None              # frame the big words are gone and the plain picture is back. None = CLEAR_FRAME + 14 (always 12 frames before the slot ends)
HOLD_TO_END = False           # True only when this slot ends the reel or ends on a cut: the big words then stay to the last frame
# ---- the look (defaults = Marc's approved demo; take the buyer's caption style when the reel has one)
FONT, WEIGHT = 'Bebas Neue', 400      # big words: a family from assets/fonts/fonts.css and its weight (stand-in for Futura Condensed ExtraBold)
BOLDEN = 0.035                # extra stroke on the big words, as a share of the letter size (Bebas is thinner than the demo's poster face). 0 for an already heavy font
CASE = 'upper'                # 'upper', 'lower' or 'as is' (the print and the big words)
ACCENT = '#FAE67A'            # big-word paint colour (6-digit hex)
INK = '#14161C'               # colour of the block shade under the big words
PRINT_FONT, PRINT_WEIGHT = 'Inter Tight', 900   # the small print's font and weight
PRINT_INK = '#6F8263'         # print colour, sage (Marc's pick). On a light wall it is multiplied in, so it can only darken the plaster
PRINT_SIZE = None             # print letter size in px. None = from his head size (about 40 on a wide shot, up to 64 on a selfie)
# ---- placement (None / 'auto' = measured by `scene.py measure`; read its printout and work/measure.jpg)
HERO_BOX = None               # (x, y, w): left, top and width in px of the big-word block. None = the biggest open wall near his head
HERO_LAYOUT = 'auto'          # 'stack' (one word per line, all the same width), 'line' (side by side), 'auto' = whichever reads bigger
KEYSTONE = 'auto'             # wall perspective: 'auto' = from the room's vertical lines, None = flat on, (x, y) = point where the wall's verticals meet (px, may be far off frame)
PRINT_MODE = 'auto'           # 'multiply' (light wall), 'lift' (dark wall), 'auto' = by the wall's brightness
BUMP = 0.012                  # tiny camera punch as each big word lands (0 = off)
VOL_PRINT, VOL_HIT = 0.20, 0.05       # whoosh as the print spreads, low hit on each big word (template volumes, x0.75 applied). 0 = off
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SLOT = os.path.basename(HERE)
N = json.load(open('clip.json'))['frames']
DUR = N / 30
DUR_S = f'{DUR - .001:.3f}'           # 1 ms short so the render is exactly N frames
SAFE = os.environ.get('SAFE', '0') == '1'
SFX_ON = os.environ.get('SFX', '1') != '0'
SFX_GAIN = 0.75
FPS = 30

# ---- check the CLIP block
words = [PRINT_TEXT] + [w for _, w in HERO]
for w in words:
    if chr(8212) in w or chr(8211) in w:
        sys.exit(f'"{w}": no long dashes on screen')
    if w.upper().strip('.,!?\'"') in ('FR' + 'EE', 'COUR' + 'SE'):
        sys.exit(f'"{w}" is on the never-on-screen list')
if not 0 <= len(HERO) <= 3:
    sys.exit('HERO takes 0 to 3 big words')
for f, w in HERO:
    if not PRINT_FRAME < f < N:
        sys.exit(f'big word "{w}" at frame {f}: it must land after PRINT_FRAME ({PRINT_FRAME}) and inside the slot ({N} frames)')
if PRINT_FRAME < 2:
    print('note: PRINT_FRAME under 2: the print starts on frame 2 so the slot opens on the plain picture')
if not os.path.exists('assets/fx.mp4'):
    print('!! assets/fx.mp4 is missing: run `scene.py bake` before rendering')


def audio():
    if not SFX_ON:
        return []
    out = []
    cues = [('whoosh-short', PRINT_FRAME / FPS - 0.10, VOL_PRINT, 0.9)]
    for i, (f, _) in enumerate(HERO):
        cues.append(('impact-bass-1', f / FPS - 0.02, VOL_HIT * (1.0 if i == 0 else 1.3), 0.9))
    for i, (name, t, vol, d) in enumerate(cues):
        if vol <= 0 or not os.path.exists(f'assets/sfx/{name}.mp3'):
            continue
        t = max(t, 0.0)
        d = min(d, DUR - t - 0.01)
        if d <= 0.05:
            continue
        out.append(f'  <audio id="sfx{i}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-media-start="0" '
                   f'data-duration="{d:.3f}" data-track-index="{10 + i}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
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
{nl.join(audio())}
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
print(f'wrote index.html: slot "{SLOT}", {N} frames, {len(audio())} sound cues' + (', SAFE guide ON (snapshots only)' if SAFE else ''))
