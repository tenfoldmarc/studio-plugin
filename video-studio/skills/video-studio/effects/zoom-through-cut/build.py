#!/usr/bin/env python3
"""zoom-through: a hard cut between two shots becomes one continuous camera move through a point on the speaker.

Run from the slot folder (full run order in effect.md):
  two_shot.py  -> a-roll with both shots + clip.json "cut_frames" + cutout
  prep.py      -> work/measure.json (dive points, caption tops) + work/measure.jpg to look at
  bake.py      -> assets/plate.mp4 (the a-roll with the camera move and motion blur baked in)
  build.py     -> index.html (plate + captions + their voice + whoosh)     SAFE=1 CAPTIONS=0 SFX=0 switches

cam() below is the one camera. bake.py uses it for the pixels and the captions use it as GSAP keyframes, so the type
rides exactly the same move as the picture. Standard library only, Python 3.9+.
"""
import json
import math
import os
import sys

# ==== CLIP (edit this) ====
CUT = None            # first frame of shot B. None = clip.json "cut_frames"[0] (two_shot.py writes it)
HALF = 9              # transition frames on EACH side of the cut (9 = 18 in total). Shorter shots: lower it
POINT_A = None        # (x, y) px the camera dives into, on the LAST frame of shot A. None = measured by prep.py
                      #   (darkest flat patch on the speaker's torso or lap, clear of the speaker's hands). Check work/measure.jpg
POINT_B = None        # (x, y) px shot B opens out from, on the FIRST frame of shot B. None = measured by prep.py
DEPTH = 80.0          # total zoom travelled. A reaches ~sqrt(DEPTH)x on the cut. 40 = gentler, 150 = harder
SHARP = 2.4           # ease steepness: higher = longer creep at both ends, faster through the cut
ROLL = 5.0            # degrees of camera roll through the move (0 = none, negative = the other way)
CREEP_A = 1.03        # slow push-in on shot A before the dive (scale reached when the dive starts). 1 = off
CREEP_B = 1.04        # slow push-in on shot B after landing (scale reached on the last frame). 1 = off
GRADE_A = None        # optional light look baked into shot A: None, 'girl' (warm, soft) or 'dude' (dark, cool)
GRADE_B = None        # same for shot B. None when the main reel grades the footage itself
# Captions: one block per shot, or None. Times are seconds in THIS slot (words.json; confirm onsets on the audio).
#   style  'girl' (small Inter + yellow serif italic), 'dude' (tracked caps + DM Serif), 'plain' (Inter Tight)
#   top    y of the block top. None = measured by prep.py (just under the speaker's chin); the block is dropped if no room
#   lead / punch / tail   [(time, 'word'), ...]: small line above, the big word(s), small line below
CAP_A = {'style': 'girl', 'top': None,
         'lead': [(0.42, 'you'), (0.52, 'can'), (0.64, 'get'), (0.80, 'the')],
         'punch': [(0.92, 'cool'), (1.10, 'girl')],
         'tail': [(1.32, 'aesthetic')]}
CAP_B = {'style': 'dude', 'top': None,
         'lead': [(2.29, 'or'), (2.55, 'you'), (2.67, 'can'), (2.79, 'get'), (2.95, 'the')],
         'lead_rides': True,      # True = the whole lead line arrives with the picture, spreading out of the point
         'punch': [(3.11, 'cool'), (3.31, 'dude')],
         'tail': [(3.53, 'aesthetic')]}
WHOOSH_VOL = 0.30     # template volume of the one whoosh (x0.75 is applied below). Its peak lands on the cut
# ==== END CLIP ====

# ---- look of the move (not clip-specific; change only to restyle the effect) ---------------------------------------
SHUTTER = 1.0                 # motion-blur shutter in frames (1.0 = 360 degrees, creamy streaks)
PORT_IN, PORT_OUT, PORT_G = 1820.0, 5200.0, 1.25  # portal radius (px) = PORT * (B scale) ** PORT_G, soft between
PORT_GATE = (3.0, 6.0)        # the portal only starts to open once shot A is this deep (A scale from, to)
FOG_FROM, FOG_TO = 9.0, 24.0  # shot A melts into the colour at POINT_A between these zoom factors (the pass-through)
FILL_BLUR = 28.0              # px softness of the border colours that are stretched outward around shot B
EDGE_DARK = 0.88              # how far that stretched fill falls off into the dark away from the picture (0..1)
FEATHER = 150.0               # px (source) the picture edge melts into the fill; shrinks to 0 as B lands
CHROMA = 0.020                # chromatic fringe at peak speed (fraction of radius per ln-scale/frame), 0 = off
CAP_DEPTH = 1.35              # captions sit nearer the camera than the room: they leave / arrive this much faster
YEL, CREAM = '#FAE67A', '#FFF8EF'
FPS = 30
W, H = 1080, 1920
SFX_GAIN = 0.75
WHOOSH = ('whoosh-short', 0.16, 0.57)     # file, seconds to its peak, length

# ---- measured inputs -----------------------------------------------------------------------------------------------
CLIPJ = json.load(open('clip.json'))
MEAS = json.load(open('work/measure.json')) if os.path.exists('work/measure.json') else {}
NFRAMES = int(CLIPJ['frames'])
if CUT is None:
    CUT = (CLIPJ.get('cut_frames') or [None])[0]
if CUT is None:
    sys.exit('no cut frame: run two_shot.py first (it writes clip.json "cut_frames"), or set CUT in the CLIP block')
if POINT_A is None:
    POINT_A = MEAS.get('point_a')
if POINT_B is None:
    POINT_B = MEAS.get('point_b')
if POINT_A is None or POINT_B is None:
    sys.exit('no dive points: run prep.py (needs assets/subject.webm), or set POINT_A / POINT_B in the CLIP block')
POINT_A, POINT_B = tuple(POINT_A), tuple(POINT_B)
_room = min(CUT - 2, NFRAMES - CUT - 2)
if HALF > _room:
    print('HALF %d does not fit (cut %d of %d frames): using %d' % (HALF, CUT, NFRAMES, _room))
    HALF = _room
if HALF < 4:
    sys.exit('the cut is too close to the start or end of the slot: need at least 6 frames on both sides')
DUR = NFRAMES / float(FPS)
F0 = CUT - HALF - 1           # last untouched frame of shot A
F1 = CUT + HALF               # first untouched frame of shot B
Z = math.log(DEPTH)
SLOT = os.path.basename(os.getcwd())


def ease(u):
    u = min(1.0, max(0.0, u))
    a, b = u ** SHARP, (1.0 - u) ** SHARP
    return a / (a + b)


def cam(f):
    """Camera state at (fractional) frame f. Screen = c + s * R(rot) * (src - point)."""
    e = ease((f - F0) / float(F1 - F0))
    ln_a = math.log(CREEP_A) * f / float(F0)
    ln_b = math.log(CREEP_B) * (f - F1) / float(max(1, NFRAMES - 1 - F1))
    return {
        'e': e,
        'sA': math.exp(ln_a + Z * e), 'sB': math.exp(ln_b + Z * (e - 1.0)),
        'rotA': ROLL * e, 'rotB': ROLL * (e - 1.0),
        'cx': POINT_A[0] + (POINT_B[0] - POINT_A[0]) * e, 'cy': POINT_A[1] + (POINT_B[1] - POINT_A[1]) * e,
    }


def speed(f):
    """Zoom speed in ln-scale units per frame."""
    return Z * (ease((f + .5 - F0) / float(F1 - F0)) - ease((f - .5 - F0) / float(F1 - F0)))


def smooth(a, b, x):
    t = min(1.0, max(0.0, (x - a) / float(b - a)))
    return t * t * (3 - 2 * t)


def zoom_through_keys(shot):
    """Per-frame GSAP keyframes that make a caption layer ride the camera. Shot 'A' leaves, 'B' arrives."""
    keys = []
    if shot == 'A':
        base = cam(F0)['sA']
        for f in range(F0 + 1, CUT + 1):
            c = cam(f)
            k = (c['sA'] / base) ** CAP_DEPTH
            keys.append((f, min(k, 9.0), c['rotA'], 1.0 - smooth(1.12, 2.3, k), min(30.0, 20.0 * (k - 1.0))))
    else:
        for f in range(CUT, F1 + 1):
            c = cam(f)
            k = c['sB'] ** CAP_DEPTH if f < F1 else 1.0
            keys.append((f, max(k, .02), c['rotB'] if f < F1 else 0.0, smooth(.34, .86, k), 26.0 * (1.0 - k)))
    return keys


# ---- captions ------------------------------------------------------------------------------------------------------
STYLE = {  # punch font-size cap, average glyph width as a fraction of the size (for auto-fit), block height
    'girl': (156, .40, 262), 'dude': (156, .50, 268), 'plain': (150, .52, 290),
}
PUNCH_MAX_W = 860


def cap_block(shot, spec, top, cx):
    """One caption block (html, tweens). shot 'A' or 'B'; ids are prefixed a / b."""
    p = shot.lower()
    style = spec.get('style', 'plain')
    size_cap, glyph, _ = STYLE[style]
    lead, punch, tail = spec.get('lead') or [], spec.get('punch') or [], spec.get('tail') or []
    ptext = ' '.join(w for _, w in punch)
    size = int(min(size_cap, PUNCH_MAX_W / max(1.0, len(ptext) * glyph)))
    rides = shot == 'B' and spec.get('lead_rides')
    up = (lambda s: s.upper()) if style == 'dude' else (lambda s: s)
    html, tw = [], []

    def small(words, grp, cls):
        if not words:
            return ''
        spans = (' ' if style != 'dude' else '').join(
            '<span class="w" id="%s%s%d">%s</span>' % (p, grp, k, up(w)) for k, (_, w) in enumerate(words))
        return '<div class="%s">%s</div>' % (cls, spans)

    if style == 'dude':
        chars = ''.join('<span class="mk"><span class="ch">%s</span></span>' % ('&nbsp;' if ch == ' ' else ch) for ch in ptext)
        big = '<div class="e" id="%sp" style="font-size:%dpx">%s</div>' % (p, size, chars) if punch else ''
        lead_cls = 's spread' if len(lead) > 2 else 's'
    else:
        words = ' '.join('<span class="w" id="%sp%d">%s</span>' % (p, k, w) for k, (_, w) in enumerate(punch))
        sparks = ('<span class="spark" id="%ssp0" style="left:-58px;top:10%%;font-size:40px">&#10022;</span>'
                  '<span class="spark" id="%ssp1" style="right:-48px;top:64%%;font-size:26px">&#10022;</span>' % (p, p)
                  ) if style == 'girl' else ''
        big = '<div class="e" style="font-size:%dpx"><span class="pw">%s%s</span></div>' % (size, words, sparks) if punch else ''
        lead_cls = 's'
    html.append('<div id="cap%s" class="rig"><div class="cap %s" style="top:%dpx;left:%dpx">%s%s%s</div></div>'
                % (shot, style, top, cx - 450, small(lead, 'l', lead_cls), big, small(tail, 't', 's')))

    for grp, words in (('l', lead), ('t', tail)):
        if grp == 'l' and rides:
            continue
        for k, (t, _) in enumerate(words):
            sel, at = '#%s%s%d' % (p, grp, k), max(0.0, t - .04)
            tw.append("gsap.set('%s',{autoAlpha:0});" % sel)
            if style == 'dude':   # "tracking in" with scaleX (lint rejects letterSpacing tweens)
                tw.append("tl.fromTo('%s',{autoAlpha:0,scaleX:1.45,filter:'blur(8px)'},{autoAlpha:1,scaleX:1,filter:'blur(0px)',"
                          "duration:.45,ease:'power3.out',immediateRender:false},%.3f);" % (sel, at))
            else:
                tw.append("tl.fromTo('%s',{autoAlpha:0,y:16,filter:'blur(6px)'},{autoAlpha:1,y:0,filter:'blur(0px)',"
                          "duration:.32,ease:'power3.out',immediateRender:false},%.3f);" % (sel, at))
    if punch and style == 'dude':
        at = max(0.0, punch[0][0] - .04)
        # letters are parked under the mask with a set: a staggered fromTo leaves the late letters visible
        tw += ["gsap.set('#%sp',{autoAlpha:0});" % p, "tl.set('#%sp',{autoAlpha:1},%.3f);" % (p, at),
               "gsap.set('#%sp .ch',{yPercent:118});" % p,
               "tl.to('#%sp .ch',{yPercent:0,duration:.6,ease:'expo.out',stagger:.03},%.3f);" % (p, at),
               "tl.fromTo('#%sp',{scale:1.06,filter:'blur(6px)'},{scale:1,filter:'blur(0px)',duration:.42,ease:'power3.out',"
               "immediateRender:false},%.3f);" % (p, at)]
    elif punch:
        for k, (t, _) in enumerate(punch):
            sel = '#%sp%d' % (p, k)
            tw += ["gsap.set('%s',{autoAlpha:0});" % sel,
                   "tl.fromTo('%s',{autoAlpha:0,scale:1.2,y:10,filter:'blur(16px)'},{autoAlpha:1,scale:1,y:0,"
                   "filter:'blur(0px)',duration:.36,ease:'power3.out',immediateRender:false},%.3f);" % (sel, max(0.0, t - .04))]
        if style == 'girl':
            t_sp = punch[-1][0] + .1
            for k in range(2):
                sel = '#%ssp%d' % (p, k)
                tw += ["gsap.set('%s',{autoAlpha:0,scale:.2,rotation:-40});" % sel,
                       "tl.to('%s',{autoAlpha:1,scale:1,rotation:0,duration:.34,ease:'back.out(2.4)'},%.3f);" % (sel, t_sp + k * .16),
                       "tl.to('%s',{scale:.72,autoAlpha:.7,duration:.3,ease:'sine.inOut',yoyo:true,repeat:1},%.3f);"
                       % (sel, t_sp + k * .16 + .36)]
    return html, tw


def captions():
    html, tw = [], []
    if os.environ.get('CAPTIONS') == '0':
        return html, tw
    cx = int(min(530, max(485, MEAS.get('cap_x', 520))))     # block is 900 wide: stays inside 35..980
    for shot, spec in (('A', CAP_A), ('B', CAP_B)):
        if not spec:
            continue
        limit = 1462 - STYLE[spec.get('style', 'plain')][2]      # lowest top that keeps the block above y 1470
        top = spec.get('top')
        if top is None:
            top = MEAS.get('cap_top_' + shot.lower())
            if top is None or top > limit + 4:
                print('caption %s dropped: no room under their chin (measured top %s, limit %d). Set its "top" by hand '
                      'or leave that shot to the main reel captions' % (shot, top, limit))
                continue
        top = int(min(top, limit))
        h, t = cap_block(shot, spec, top, cx)
        html += h
        tw += t
        c = cam(F0 if shot == 'A' else F1)
        keys = zoom_through_keys(shot)
        kf = ','.join("{scale:%.4f,rotation:%.3f,autoAlpha:%.3f,filter:'blur(%.2fpx)',duration:%.5f,ease:'none'}"
                      % (k, r, a, b, 1.0 / FPS) for _, k, r, a, b in keys)
        if shot == 'A':
            tw += ["gsap.set('#capA',{transformOrigin:'%.1fpx %.1fpx',scale:1,rotation:0,autoAlpha:1});" % (c['cx'], c['cy']),
                   "tl.to('#capA',{keyframes:[%s]},%.5f);" % (kf, (keys[0][0] - 1) / float(FPS)),
                   "tl.set('#capA',{autoAlpha:0},%.4f);" % (CUT / float(FPS) - .002)]
        else:
            tw += ["gsap.set('#capB',{transformOrigin:'%.1fpx %.1fpx',scale:.02,rotation:0,autoAlpha:0});" % (c['cx'], c['cy']),
                   "tl.to('#capB',{keyframes:[%s]},%.5f);" % (kf, (keys[0][0] - 1) / float(FPS))]
    return html, tw


def audio():
    if os.environ.get('SFX') == '0':
        return []
    name, peak, length = WHOOSH
    t = max(0.0, CUT / float(FPS) - peak)
    return ['<audio id="sfx0" src="assets/sfx/%s.mp3" data-start="%.3f" data-duration="%.3f" data-track-index="10" '
            'data-volume="%.3f"></audio>' % (name, t, min(length, DUR - t), WHOOSH_VOL * SFX_GAIN)]


CSS = '''
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#0b0c0f}
.full{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.rig{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:8}
.cap{position:absolute;width:900px;text-align:center}
.cap .w{display:inline-block;transform-origin:50% 60%}
.cap .e{white-space:nowrap}
.cap .pw{position:relative;display:inline-block}
/* girl: small Inter + butter-yellow serif italic */
.girl{color:CREAM;text-shadow:0 2px 22px rgba(40,22,14,.62),0 1px 3px rgba(40,22,14,.35)}
.girl .s{font:500 46px Inter;letter-spacing:-.6px;line-height:1.1}
.girl .e{font-family:'Instrument Serif';font-style:italic;font-weight:400;line-height:.9;color:YEL;margin:0 0 6px;
  text-shadow:0 4px 30px rgba(40,22,14,.6),0 1px 4px rgba(40,22,14,.3)}
.spark{position:absolute;color:YEL;line-height:1;font-style:normal;text-shadow:0 0 18px rgba(250,230,122,.55)}
/* dude: tracked caps + heavy serif */
.dude .s{color:#F2EFE9;font:600 33px Montserrat;text-shadow:0 2px 12px rgba(0,0,0,.65);white-space:nowrap;line-height:1.2}
.dude .s.spread{display:flex;justify-content:space-between;width:652px;margin:0 auto}
.dude .s{padding-left:.32em}
.dude .s .w{letter-spacing:.32em;margin:0 .14em;transform-origin:50% 50%}
.dude .s.spread{padding-left:0}
.dude .s.spread .w{margin:0 -.32em 0 0}
.dude .e{color:#F7F4EE;font-family:'DM Serif Display';font-weight:400;line-height:1.1;letter-spacing:-.02em;
  text-shadow:0 12px 40px rgba(0,0,0,.5);margin:-6px 0 2px}
.dude .mk{display:inline-block;overflow:hidden;padding:0 .02em .14em;margin-bottom:-.14em;vertical-align:bottom}
.dude .ch{display:inline-block}
/* plain: the base caption look */
.plain{color:#fff;font-family:'Inter Tight';text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35)}
.plain .s{font-weight:800;font-size:56px;letter-spacing:-.04em;line-height:1.12}
.plain .e{font-weight:900;letter-spacing:-.05em;line-height:.98;color:YEL}
'''.replace('YEL', YEL).replace('CREAM', CREAM)

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    nl = '\n'
    html, tw = captions()
    return '''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>%(css)s</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="%(dur).3f" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="%(dur).3f" data-track-index="2" data-volume="1"></audio>
%(sfx)s
  <video id="bgv" class="full" src="assets/plate.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="%(dur).3f" data-track-index="0"></video>
%(html)s
%(safe)s
</div>
<script>
const tl = gsap.timeline({ paused: true });
%(tw)s
tl.set({}, {}, %(dur).3f);
window.__timelines["main"] = tl;
</script>
</body>
</html>
''' % {'css': CSS, 'dur': DUR, 'sfx': nl.join(audio()), 'html': nl.join(html), 'tw': nl.join(tw),
       'safe': SAFE_GUIDE if os.environ.get('SAFE') else ''}


if __name__ == '__main__':
    if not os.path.exists('assets/plate.mp4'):
        print('note: assets/plate.mp4 is missing, run bake.py before lint / render')
    open('index.html', 'w').write(build())
    print('wrote index.html  %s  %d frames (%.3fs)  cut %d  transition %d..%d  A %s  B %s  -> renders/%s.mp4'
          % (SLOT, NFRAMES, DUR, CUT, F0 + 1, F1 - 1, POINT_A, POINT_B, SLOT))
