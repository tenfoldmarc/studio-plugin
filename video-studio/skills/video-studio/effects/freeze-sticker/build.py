#!/usr/bin/env python3
"""sticker (CTA): on one word the picture freezes and the speaker becomes a die-cut sticker (white border around
their outline, soft shadow, slight tilt) slapped onto a page, with handwritten notes written on around it. The voice
runs on under the freeze. Frames before F_FREEZE are plain live footage.

Run from the slot folder, after bake.py (see effect.md for the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no notes or doodles, SFX=0 no sounds)
The outline, the sticker's size and place and where each note goes are measured by bake.py (assets/sticker/sticker.json).
"""
import hashlib
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
F_FREEZE = 45      # frame the picture freezes: onset of the word it lands on ("onset" column of onsets.py). This one
                   # still IS the effect: run bake.py with the argument "frames" and look (eyes open, sharp, good face)
F_OUT = None       # None = the sticker stays to the last frame: the reel ends or CUTS there (the CTA default). Or a
                   # frame, 24+ after F_FREEZE and 2+ before the last: the sticker is flung off, live picture from there
NOTES = [          # the user's OWN words, as (text, frame, side). frame = onset of the word the note is written on,
                   # None = right after the freeze. side = 'auto', 'top', 'left' or 'right'. *stars* = accent + underline
    ('your *note* here', None, 'auto'),          # placeholder: ask the user. Never a number, result, handle or keyword
    ('a second one', None, 'auto'),              # the speaker does not say. [] = sticker only
]
STAMP = ''         # one short word of the user's in a boxed stamp above the first note. '' = off
ARROW = True       # hand-drawn arrow from the first note to the speaker's body (left out when it has no clear path)
TICKS = True       # three small emphasis lines by the head
BACKDROP = 'page'  # what is behind the sticker: 'page' = plain colour page (PAGE). 'footage' = the frozen picture,
                   # blurred and dimmed (frozen, not live, so the speaker does not move behind their own sticker)
PAGE = '#3A5BE6'   # page colour: pick one that sets the clothes and skin off. Never orange, never a grey
INK = '#FFFFFF'    # handwriting colour
ACCENT = '#FAE67A'  # colour of *starred* words, the stamp and the ticks (butter yellow; never orange)
SIZE = 'auto'      # 'auto' = measured from the head and the frame edges. A number = scale of the speaker (0.6 to 1.3)
PLACE = (0, 0)     # nudge the sticker (x, y) in screen px after the automatic placing. Look at work/check.jpg
TILT = 'auto'      # degrees. 'auto' = 4, leaning away from a side where the frame cuts the speaker. 0 = straight
BORDER = 20        # white border, px on screen
CUT_Y = None       # None = the body runs off the bottom of the screen. A y in a-roll px = straight die-cut across the
                   # body there (below the chest, above where the legs part): the sticker then floats whole
CHOKE = 2          # px shaved off the cutout edge. 3 or 4 if a rim of the room shows around the speaker
HEAD = None        # (top_y, chin_y) in a-roll px, only when the green box on work/check.jpg is not on the head
GRADE = ''         # '' = off: the live frames are handed back untouched. A css filter only if the whole reel has it
SOUNDS = True      # shutter click on the freeze, a pop as it lands, soft clicks on the notes, a whoosh on the way out
# ==== END CLIP ====

PEEL = .2                  # seconds the sticker takes to fly off before F_OUT
SFX_GAIN = 0.75
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'click': .36, 'click-soft': .36}

src = open(os.path.join(HERE, 'build.py')).read()
block = src.split('# ==== CLIP (edit this) ====')[1].split('# ==== END CLIP ====')[0]
N = json.load(open('clip.json'))['frames']
DUR = N / 30
if not os.path.exists('assets/sticker/sticker.json'):
    sys.exit('no assets/sticker/sticker.json: run bake.py first')
M = json.load(open('assets/sticker/sticker.json'))
if M['sig'] != hashlib.sha1((block + str(N)).encode()).hexdigest():
    sys.exit('the CLIP block changed since bake.py ran: run bake.py again (it re-measures the sticker and the notes)')
CAPS = os.environ.get('CAPTIONS') != '0'
TF = F_FREEZE / 30 - .002
TU = F_OUT / 30 - .002 if F_OUT is not None else None
END = TU - PEEL if TU is not None else DUR
S, TILT_, (AX, AY), (TX, TY), (PX, PY) = M['S'], M['tilt'], M['A'], M['T'], M['pivot']
st, sh = M['sticker'], M['shadow']
notes = M['notes'] if CAPS else []


def shade(hexs, k):
    h = hexs.lstrip('#')
    return '#' + ''.join(f'{max(0, min(255, round(int(h[i:i + 2], 16) * k))):02x}' for i in (0, 2, 4))


def sticker():
    h = [f'''<div id="stkbase" class="frame"><div id="drift" class="frame"><div id="slap" class="frame">
      <img id="shadow" src="assets/sticker/shadow.png" style="left:{sh['left']}px;top:{sh['top']}px;width:{sh['w']}px;height:{sh['h']}px" />
      <img id="stk" src="assets/sticker/sticker.png" style="left:{st['left']}px;top:{st['top']}px;width:{st['w']}px;height:{st['h']}px" />
    </div></div></div>''']
    tw = [f"gsap.set('#stkbase',{{transformOrigin:'{AX}px {AY}px',rotation:{TILT_},scale:{S},x:{TX},y:{TY}}});",
          f"gsap.set(['#slap','#drift'],{{transformOrigin:'{PX}px {PY}px'}});",
          "gsap.set('#fz',{autoAlpha:0});",
          f"tl.set('#fz',{{autoAlpha:1}},{TF:.3f});",
          # slap: lifted big -> overshoot small -> settle
          f"tl.fromTo('#slap',{{scale:1.12,rotation:{-TILT_}}},{{keyframes:[{{scale:.96,rotation:-1,duration:.13,ease:'power3.in'}},"
          f"{{scale:1.012,rotation:.4,duration:.12,ease:'power2.out'}},{{scale:1,rotation:0,duration:.14,ease:'sine.inOut'}}],immediateRender:false}},{TF:.3f});",
          # shadow: far + soft while lifted, tight on impact
          f"tl.fromTo('#shadow',{{x:26,y:70,opacity:.35}},{{keyframes:[{{x:6,y:16,opacity:.62,duration:.13,ease:'power3.in'}},"
          f"{{x:10,y:24,opacity:.55,duration:.2,ease:'power2.out'}}],immediateRender:false}},{TF:.3f});",
          # the freeze still breathes: a very slow push on the sticker, the page turns behind it
          f"tl.fromTo('#drift',{{scale:1}},{{scale:1.02,duration:{max(.1, END - TF - .4):.3f},ease:'none',immediateRender:false}},{TF + .4:.3f});",
          f"tl.fromTo('#turn',{{rotation:0,scale:1.06}},{{rotation:{7 if BACKDROP == 'page' else 0},scale:{1.06 if BACKDROP == 'page' else 1.0},duration:{max(.1, (TU or DUR) - TF):.3f},ease:'none',immediateRender:false}},{TF:.3f});",
          # camera shake on impact, shutter flash on the freeze
          f"tl.to('#cam',{{keyframes:[{{x:-11,y:7,rotation:-.5,duration:.035}},{{x:9,y:-6,rotation:.4,duration:.035}},"
          f"{{x:-6,y:4,rotation:-.25,duration:.035}},{{x:3,y:-2,rotation:.1,duration:.035}},{{x:0,y:0,rotation:0,duration:.05}}],ease:'none'}},{TF + .13:.3f});",
          "gsap.set('#flash',{autoAlpha:0});",
          f"tl.fromTo('#flash',{{autoAlpha:.55}},{{autoAlpha:0,duration:.16,ease:'power2.out',immediateRender:false}},{TF:.3f});",
          f"tl.set('#flash',{{autoAlpha:0}},{TF + .17:.3f});"]
    if TU is not None:
        # way out, over the page (the sticker never doubles the live shot): ink off, sticker lifts and is flung off the
        # top, then a hard cut to the live picture exactly on F_OUT
        tw += [f"tl.to('.ann',{{autoAlpha:0,duration:.08,ease:'power1.in'}},{TU - PEEL:.3f});",
               f"tl.to('#stkbase',{{keyframes:[{{scale:{S + .08:.4f},y:{TY - 110},rotation:{TILT_ - 3},duration:.07,ease:'power2.out'}},"
               f"{{x:{TX + 560},y:{TY - 2100},rotation:{TILT_ + 26},scale:{S - .06:.4f},filter:'blur(6px)',duration:{PEEL - .07:.3f},ease:'power1.in'}}]}},{TU - PEEL:.3f});",
               f"tl.to('#shadow',{{x:34,y:90,opacity:.28,duration:.07,ease:'power2.out'}},{TU - PEEL:.3f});",
               f"tl.set('#fz',{{autoAlpha:0}},{TU:.3f});"]
    return h, tw


def note_time(n, k):
    t = n['frame'] / 30 - .002 if n['frame'] is not None else TF + .12 + .38 * k
    return min(max(t, TF + .08), END - .3)


def ink():
    h, tw, paths = [], [], []
    for k, n in enumerate(notes):
        t, nid, size = note_time(n, k), f"n{n['i']}", n['size']
        top = .03 * n['w']
        if n['stamp']:
            h.append(f'<div class="ann" style="left:{n["x"] + 10}px;top:{n["y"] + top:.0f}px;transform:rotate({n["rot"] - 4}deg);transform-origin:0 50%">'
                     f'<div id="stamp" style="font-size:{size * .40:.0f}px;border-width:{max(4, size * .045):.0f}px"><span>{html.escape(n["stamp"])}</span></div></div>')
            tw += ["gsap.set('#stamp',{autoAlpha:0});",
                   f"tl.fromTo('#stamp',{{autoAlpha:0,scale:1.4,filter:'blur(6px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',duration:.2,ease:'expo.out',immediateRender:false}},{max(TF + .05, t - .06):.3f});",
                   f"tl.fromTo('#stamp',{{rotation:6}},{{rotation:0,duration:.35,ease:'back.out(3)',immediateRender:false}},{max(TF + .05, t - .06):.3f});"]
            top += .62 * size
        rows = []
        for j, ln in enumerate(n['lines']):
            out, run = [], []
            for w, em in ln + [[None, False]]:
                if em:
                    run.append(html.escape(w))
                    continue
                if run:
                    out.append('<span class="em">' + ' '.join(run) + '<svg class="ul" viewBox="0 0 100 12" preserveAspectRatio="none">'
                               '<path d="M2 5 C 24 1, 52 9, 98 3 C 70 8, 40 10, 14 11" fill="none" stroke-width="2.6" stroke-linecap="round"/></svg></span>')
                    run = []
                if w is not None:
                    out.append(html.escape(w))
            rows.append(f'<div id="{nid}l{j}" class="ln">{" ".join(out)}</div>')
            d = .22 + .012 * sum(len(w) for w, _ in ln)
            tw += [f"gsap.set('#{nid}l{j}',{{autoAlpha:0,clipPath:'inset(-30% 106% -30% -6%)'}});",      # hidden outright until its word:
                   f"tl.set('#{nid}l{j}',{{autoAlpha:1}},{t + j * .2:.3f});",                             # an empty clip still leaks a speck
                   f"tl.fromTo('#{nid}l{j}',{{clipPath:'inset(-30% 106% -30% -6%)'}},{{clipPath:'inset(-30% -6% -30% -6%)',duration:{d:.2f},ease:'power1.inOut',immediateRender:false}},{t + j * .2:.3f});",
                   f"tl.fromTo('#{nid}l{j}',{{y:10}},{{y:0,duration:{d + .1:.2f},ease:'power2.out',immediateRender:false}},{t + j * .2:.3f});"]
        h.append(f'<div class="ann note" style="left:{n["x"] + 14}px;top:{n["y"] + top:.0f}px;font-size:{size}px;'
                 f'transform:rotate({n["rot"]}deg)">{"".join(rows)}</div>')
    t0 = note_time(notes[0], 0) if notes else TF
    if CAPS and M['arrow'] and notes:
        paths += [('ar', M['arrow']['d'], INK, t0 + .34, .22), ('ah', M['arrow']['head'], INK, t0 + .54, .08)]
    if CAPS:
        paths += [(f'k{i}', d, ACCENT, TF + .26 + .03 * i, .07) for i, d in enumerate(M['ticks'])]
    if paths:
        svg = ''.join(f'<path id="{i}" d="{d}" pathLength="1" fill="none" stroke="{c}" stroke-width="9" stroke-linecap="round" '
                      f'stroke-linejoin="round" stroke-dasharray="1" stroke-dashoffset="1"/>' for i, d, c, _, _ in paths)
        h.append(f'<svg id="ink" class="ann" width="1080" height="1920" viewBox="0 0 1080 1920" xmlns="http://www.w3.org/2000/svg">{svg}</svg>')
        tw += [f"tl.fromTo('#{i}',{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:{dur},ease:'power2.inOut',immediateRender:false}},{min(t, END - .1):.3f});"
               for i, _, _, t, dur in paths]
    return h, tw


def audio():
    if os.environ.get('SFX') == '0' or not SOUNDS:
        return []
    sfx = [('click', TF - .01, .55), ('pop', TF + .1, .22)]
    sfx += [('click-soft', note_time(n, k) - .02, .4) for k, n in enumerate(notes[:3])]
    if TU is not None:
        sfx.append(('whoosh-short', TU - PEEL - .03, .24))
    out, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        if not os.path.exists(f'assets/sfx/{name}.mp3'):
            print(f'  (sound {name} not in assets/sfx: skipped)')
            continue
        t = max(0.0, t)
        d = min(SFX_LEN[name], DUR - t)
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'  <audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


if BACKDROP == 'page':
    BACK = (f'<div id="bd" style="background:radial-gradient(70% 50% at 50% 46%,{PAGE} 0%,{shade(PAGE, .82)} 45%,{shade(PAGE, .52)} 100%)">'
            '<div id="turn" class="rays"></div>'
            f'<div id="bdvig" style="background:radial-gradient(85% 60% at 50% 48%,{shade(PAGE, .2)}00 50%,{shade(PAGE, .2)}73 100%)"></div></div>')
else:
    BACK = '<div id="bd" style="background:#101114"><img id="turn" class="bk" src="assets/sticker/back.jpg" /></div>'
G_ = f'filter:{GRADE};' if GRADE else ''
SHAD = shade(PAGE, .18) if BACKDROP == 'page' else '#000000'
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#cam{{position:absolute;inset:-30px}}
#cam > .in{{position:absolute;left:30px;top:30px;width:1080px;height:1920px}}
#live{{position:absolute;inset:0}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;{G_}}}
.frame{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
#fz{{position:absolute;inset:0;z-index:3}}
#bd{{position:absolute;left:-60px;top:-60px;width:1200px;height:2040px;overflow:hidden}}
.rays{{position:absolute;left:-640px;top:-440px;width:2480px;height:2480px;transform-origin:50% 50%;
  background:repeating-conic-gradient(from 0deg at 50% 50%,rgba(255,255,255,.055) 0deg 7deg,rgba(255,255,255,0) 7deg 15deg)}}
.bk{{position:absolute;left:0;top:0;width:1200px;height:2040px;object-fit:cover;transform-origin:50% 45%}}
#bdvig{{position:absolute;inset:0}}
#stk,#shadow{{position:absolute;display:block;max-width:none}}
.ann{{position:absolute;z-index:6}}
#ink{{left:0;top:0;overflow:visible;filter:drop-shadow(0 4px 10px {SHAD}59)}}
.note{{font-family:'Caveat';font-weight:600;line-height:.92;white-space:nowrap;letter-spacing:-.01em;color:{INK};
  transform-origin:0 50%;text-shadow:0 4px 14px {SHAD}59}}
.ln{{display:block;width:max-content}}
.em{{position:relative;color:{ACCENT}}}
.ul{{position:absolute;left:-3%;bottom:-.1em;width:106%;height:.2em;overflow:visible;stroke:{ACCENT}}}
#stamp{{display:inline-block;padding:.16em .42em .13em;border:6px solid {ACCENT};border-radius:.26em;color:{ACCENT};
  font-family:'Inter Tight';font-weight:900;line-height:1;transform-origin:50% 50%;box-shadow:0 6px 18px {SHAD}40;white-space:nowrap}}
#stamp span{{display:inline-block;letter-spacing:.02em;text-transform:uppercase}}
#flash{{position:absolute;inset:0;z-index:9;background:#fff}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    s_html, s_tw = sticker()
    i_html, i_tw = ink()
    nl = '\n'
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
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
  <div id="cam"><div class="in">
    <div id="live"><video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video></div>
    <div id="fz">
      {BACK}
{nl.join(s_html)}
{nl.join(i_html)}
    </div>
  </div></div>
  <div id="flash"></div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(s_tw + i_tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open('index.html', 'w').write(build())
slot = os.path.basename(HERE)
print(f'wrote index.html  {N} frames  live to f{F_FREEZE - 1}, sticker from f{F_FREEZE}, '
      + (f'flung off and live again from f{F_OUT}' if F_OUT is not None else 'stays to the last frame (ENDS ON THE STICKER: the reel ends or cuts there)'))
print(f'sticker size {S}, tilt {TILT_}, {len(notes)} note(s)' + ('' if CAPS else ' (CAPTIONS=0: no notes, no doodles)')
      + (f'; {len(M["warnings"])} warning(s) from bake.py, read them' if M['warnings'] else ''))
print(f'render to renders/{slot}.mp4' + ('   (SAFE guide is ON: snapshots only)' if os.environ.get('SAFE') else ''))
