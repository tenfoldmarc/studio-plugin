#!/usr/bin/env python3
"""spotlight: on a key word the room goes dark and out of focus, the speaker stays lit, the key words land big,
then the lights come back up. Runs from the slot folder (made by fx_new.py, with a cutout).

  onsets.py   word onsets as frames                      -> fill the CLIP block below
  prep.py     measures the speaker, bakes assets/room_dark.mp4 + assets/subject_spot.webm, writes check pictures
  build.py    (this file) places the key words from the measured speaker, writes index.html
  check.py    after the render: plain frames at both ends, sheet + full-size edge crops from the final mp4

Switches: SAFE=1 safe-zone guide, CAPTIONS=0 no key words (lights only), SFX=0 no sounds.
"""
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FP = shutil.which('ffprobe') or 'ffprobe'

# ==== CLIP (edit this) ====
F_IN = 60            # first frame the lights move. Onset of the first key word minus 1 (onsets.py, "onset" column). 3 or later.
F_OUT = 108          # first frame the lights come back: onset of the first word said in the normal room, 14+ frames
                     # before the slot's last frame. None = stay dark to the last frame (the slot must END ON A CUT).
# key words, only words the speaker says: (text, frame it appears = its onset, place, size, colour)
#   place: 'auto' (first word 'above', the rest 'chest'), 'above' (behind the head, feet of the letters tucked
#          behind it), 'left' / 'right' (in the dark room beside the head), 'chest' (in front, under the chin),
#          or by hand ('back' | 'front', centre x, baseline y) in a-roll px, read off work/check_sheet.jpg
#   size:  'auto' (as big as the place and the safe zone allow) or a font size in px
KEYWORDS = [
    ('first', 61, 'auto', 'auto', '#FFF8EF'),
    ('second', 74, 'auto', 'auto', '#FAE67A'),
]
DARK = 0.16          # how dark the room gets outside the pool of light (0.10 = nearly night, 0.30 = dim). Keeps its colour.
BLUR = 11            # px the room goes out of focus
POOL = 1.0           # size of the pool of light behind the speaker (1 = measured from the head; 0.8 tighter, darker room)
EDGE_CHOKE = 1.5     # px the cutout edge is pulled in. Bright halo around the speaker on work/check_edge.jpg: 2.5. Thin hair eaten: 0.8
EDGE_SPILL = 4       # px of the speaker's outer edge recoloured from inside (kills the pale wall-coloured line). 0 = off
PUSH = 1.045         # slow push-in while the lights are down (1 = none). Back to 1:1 when the lights are up.
GAP = None           # still camera only: polygon [(x, y), ...] of background the cutout kept (between the legs). None = off
FLECKS = []          # bright background showing through a hole in the speaker: [(first frame, last frame, (x0, y0, x1, y1))]. [] = off
GRADE = ''           # css filter on the whole slot. '' = off (the slot hands back plain footage at both ends)
SOUNDS = True        # one low hit as the lights fall, a quiet whoosh as they come back (stock sounds, 0.75x)
# ==== END CLIP ====

FPS = 30
EASE_IN_FR, EASE_OUT_FR = 11, 8          # frames the lights take to fall / come back
# the lit state (baked by prep.py: change one, run prep.py again)
ROOM_SAT = .72                           # the dark room keeps this much of its colour (never grey)
ROOM_TINT, POOL_TINT = (.86, .96, 1.14), (1.05, 1.0, .91)      # the dark cools, the lit wall stays a touch warm
ROOM_LIT = .88                           # exposure in the middle of the pool
NAVY, NAVY_LIFT = (9, 13, 30), .9        # what the shadows fall to (a colour, never neutral black)
POOL_EDGE = (.68, 1.07)                  # penumbra: fully lit inside the first radius fraction, dark past the second
CONE_ON_WALL, BEAM_HAZE = .45, .17       # beam from above: lift on the wall over the pool, opacity of the warm haze
FALLOFF = .58                            # how far the frame edges and the speaker's lower body drop off
SUBJ_LIFT = (1.25, 1.03, .92)            # the speaker: brightness, contrast, saturation (saturation down or skin turns red)
RIM_GAIN = .31                           # warm top light screened onto the speaker's own up-facing edge pixels
SUBJ_SHADOW = (26, 44, .55)              # the shadow the speaker throws on the word / room behind: y offset, blur, opacity
WARM, FALL_RGB = (255, 240, 212), (5, 7, 16)
SFX_GAIN = 0.75
SAFE_BOX = (35, 220, 1045, 1470, 1155, 980)      # left, top, right, bottom, and from y 1155 down the right limit is 980
FONT = 'InterTight-900-normal.woff2'
BASE, TRACK = .815, -.05                 # Inter Tight 900 at line-height .9: baseline = top + .815 * size; letter-spacing em

ON = {k: os.environ.get(k, '1') != '0' for k in ('CAPTIONS', 'SFX')}
SAFE = bool(os.environ.get('SAFE'))


def stamp():
    """everything prep.py bakes in: build.py refuses to run when this no longer matches work/measure.json"""
    return json.loads(json.dumps([F_IN, F_OUT, DARK, BLUR, POOL, EDGE_CHOKE, EDGE_SPILL, GAP, FLECKS]))


def ramp(n):
    """0 = plain picture, 1 = lights fully down, for frame n"""
    if n < F_IN:
        return 0.0
    r = 1 - (1 - min(1.0, (n - F_IN + 1) / EASE_IN_FR)) ** 3
    if F_OUT is not None and n >= F_OUT:
        r *= (1 - min(1.0, (n - F_OUT + 1) / EASE_OUT_FR)) ** 2
    return r


def end_frame(n_frames):
    """first plain frame after the release (or the frame count when the lights stay down)"""
    return n_frames if F_OUT is None else F_OUT + EASE_OUT_FR - 1


def F(n):
    """time of frame n, 2 ms early so a tl.set lands ON that frame. A tween that starts on frame n is still at its
    start value on frame n: the first visible change is n + 1, so tweens start at F(n - 1)."""
    return max(0.0, n / FPS - .002)


def probe(path, entry, stream=None):
    args = [FP, '-v', 'error'] + (['-select_streams', stream] if stream else [])
    return float(subprocess.run(args + ['-show_entries', entry, '-of', 'csv=p=0', os.path.join(HERE, path)],
                                capture_output=True, text=True).stdout.strip())


_font = []


def ink(text, size):
    """(css width, ink above the baseline, ink below it) of the word at this font size"""
    n = len(text)
    try:
        if not _font:
            from PIL import ImageFont
            _font.append(ImageFont.truetype(os.path.join(HERE, 'assets/fonts', FONT), 1000))
        f = _font[0]
        w = sum(f.getlength(c) for c in text)
        _, t, _, b = f.getbbox(text, anchor='ls')
        up, down = -t, max(0, b)
    except Exception:                                # no Pillow or it cannot read woff2: table values for this font
        w = n * 575
        up = 745 if any(c in 'bdfhklt' or c.isupper() or c.isdigit() for c in text) else 560
        down = 200 if any(c in 'gjpqy' for c in text) else 12
    k = size / 1000
    return (w + TRACK * 1000 * n) * k, up * k, down * k


def allowed(origin, bottom_y=None):
    """safe zone pulled in so the word is still inside it at the end of the push-in"""
    ox, oy = origin
    l, t, r, b, y2, r2 = SAFE_BOX
    inv = lambda v, o: o + (v - o) / PUSH
    box = [inv(l + 6, ox), inv(t + 8, oy), inv(r - 6, ox), inv(b - 8, oy)]
    if bottom_y is not None and oy + (bottom_y - oy) * PUSH > y2:
        box[2] = inv(r2 - 6, ox)
    return box


def place_words(M):
    """KEYWORDS -> [(text, frame, layer, left, top, size, colour, ink box)], placed from the measured speaker"""
    S = M['summary']
    hx, top, neck, hw, hh = S['head_x'], S['head_top'], S['neck_y_max'], S['head_w'], S['head_h']
    origin = (S['head_x'], S['neck_y'])
    left_edge, right_edge = M['left_edge'], M['right_edge']          # per 2 px row: leftmost / rightmost speaker px
    face = (hx - hw / 2 - 6, S['head_top_min'] - 6, hx + hw / 2 + 6, neck)
    out, chest_y = [], neck + max(30, .12 * hh)

    def fit(text, size, width_max, cap):
        w1, up1, dn1 = ink(text, 1000)
        s = min(cap, width_max / w1 * 1000)
        return s if size == 'auto' else float(size)

    for i, (text, frame, place, size, colour) in enumerate(KEYWORDS):
        if place == 'auto':
            place = 'above' if i == 0 else 'chest'
        tried = []
        while True:
            tried.append(place)
            w1, up1, dn1 = (v / 1000 for v in ink(text, 1000))       # per px of font size
            box = allowed(origin)
            if isinstance(place, (tuple, list)):
                layer, cx, base = place
                s = fit(text, size, box[2] - box[0], 340)
                break
            if place == 'above':
                layer = 'back'
                s = fit(text, size, box[2] - box[0], 340)
                tuck = .16 if (hw < .25 * w1 * s and S['head_top_range'] < .1 * s) else .05
                if size == 'auto':                                    # ink top must stay under the safe top
                    s = min(s, (top - box[1]) / (up1 - tuck))
                base, cx = top + tuck * s, hx
                if s >= 130 or size != 'auto':
                    break
                place = 'left' if (S['free_left'] >= S['free_right']) else 'right'
                continue
            if place in ('left', 'right'):
                layer = 'back'
                y0, y1 = int(max(0, top - .2 * hh) / 2), int(min(1918, neck) / 2)
                if place == 'left':
                    x0, x1 = box[0], min(left_edge[y0:y1 + 1]) - 26
                else:
                    x0, x1 = max(right_edge[y0:y1 + 1]) + 26, box[2]
                s = fit(text, size, max(1, x1 - x0), 300)
                cx, base = (x0 + x1) / 2, top + .45 * hh + .5 * up1 * s
                if s >= 90 or size != 'auto' or 'chest' in tried:
                    break
                place = 'chest'
                continue
            layer = 'front'                                          # chest: in front of the speaker, under the chin
            box = allowed(origin, 1300)
            s = fit(text, size, box[2] - box[0], 320)
            if size == 'auto':
                s = min(s, (box[3] - chest_y) / (up1 + dn1))
            low = box[3] - (up1 + dn1) * s                             # lowest the word can sit in the safe zone
            if not any(k[2] == 'front' for k in out):                  # first chest word; later ones stack under it
                # wide shot: over the lap, well under the face. Closer shot: a third of the way down the chest.
                chest_y = min(chest_y + 1.68 * hh, low) if hh < 300 else chest_y + .35 * max(0, low - chest_y)
            base, cx = chest_y + up1 * s, hx
            chest_y = base + dn1 * s + .12 * s                        # the next chest word goes on the line below
            break
        w, up, dn = ink(text, s)
        box = allowed(origin, base + dn)
        cx = min(max(cx, box[0] + w / 2), box[2] - w / 2)             # slide sideways into the safe zone
        ib = (cx - w / 2, base - up, cx + w / 2, base + dn)
        msg = []
        if ib[0] < box[0] - 1 or ib[2] > box[2] + 1 or ib[1] < box[1] - 1 or ib[3] > box[3] + 1:
            msg.append('OUTSIDE THE SAFE ZONE (smaller size or another place)')
        if layer == 'front' and not (ib[2] < face[0] or ib[0] > face[2] or ib[1] > face[3] or ib[3] < face[1]):
            msg.append('ON THE FACE (move it under the chin or use a back place)')
        if s < 90:
            msg.append('very small: no room for it here, try another place')
        print(f'  "{text}" f{frame} {place if isinstance(place, str) else "by hand"} ({layer}) size {s:.0f}  ink box '
              f'x {ib[0]:.0f}..{ib[2]:.0f}  y {ib[1]:.0f}..{ib[3]:.0f}' + ''.join('  !! ' + m for m in msg))
        if any('SAFE' in m or 'FACE' in m for m in msg):
            sys.exit('fix the key word above (CLIP block: place / size)')
        out.append((text, frame, layer, cx - w / 2, base - BASE * s, s, colour, ib))
    return out


def tweens(words, n_frames, dur):
    sy, sb, so = SUBJ_SHADOW
    sh0, sh1 = 'drop-shadow(0px 0px 0px rgba(2,4,10,0))', f'drop-shadow(0px {sy}px {sb}px rgba(2,4,10,{so}))'
    d_in, d_out, end = EASE_IN_FR / FPS, EASE_OUT_FR / FPS, end_frame(n_frames)
    tw = [
        "gsap.set(['#dark','#subjw'],{autoAlpha:0});",
        f"gsap.set('#subjw',{{filter:'{sh0}'}});",
        # the baked layers carry the whole fall of the lights frame by frame; they switch on hard on the first frame
        # that moves (a fade-in pumps the speaker's brightness)
        f"tl.set(['#dark','#subjw'],{{autoAlpha:1}},{F(F_IN):.3f});",
        f"tl.to('#subjw',{{filter:'{sh1}',duration:{d_in:.3f},ease:'power3.out'}},{F(F_IN - 1):.3f});",
    ]
    hold = (F(F_OUT - 1) if F_OUT is not None else dur) - F(F_IN - 1)
    if PUSH != 1:
        tw.append(f"tl.fromTo('#stage',{{scale:1}},{{scale:{PUSH},duration:{hold:.3f},ease:'power1.out',immediateRender:false}},{F(F_IN - 1):.3f});")
    if F_OUT is not None:
        tw += [
            f"tl.to('#subjw',{{filter:'{sh0}',duration:{d_out:.3f},ease:'power2.out'}},{F(F_OUT - 1):.3f});",
            f"tl.to('#stage',{{scale:1,duration:{d_out + .06:.3f},ease:'power3.out'}},{F(F_OUT - 1):.3f});",
            # hand back to the live picture: by now the baked frames are almost the plain picture, so the two layers
            # dissolve over 3 frames instead of popping off (a hard switch shows as a 1-frame edge / colour tick)
            f"tl.to(['#dark','#subjw'],{{autoAlpha:0,duration:.1,ease:'none'}},{F(end - 3):.3f});",
            f"tl.set(['#dark','#subjw'],{{autoAlpha:0}},{F(end):.3f});",
        ]
    back, front = [], []
    for k, (text, frame, layer, left, top, size, colour, _) in enumerate(words):
        kid, t = f'kw{k}', F(frame - 1)
        chars = ''.join(f'<span class="ch">{c}</span>' for c in text)
        html = (f'<div id="{kid}" class="kw {layer}" style="left:{left:.1f}px;top:{top:.1f}px;font-size:{size:.1f}px;'
                f'color:{colour}"><div id="{kid}b" class="kwb">{chars}</div></div>')
        (back if layer == 'back' else front).append(html)
        tw.append(f"gsap.set('#{kid}',{{autoAlpha:0}});")
        if layer == 'back':       # resolves out of the dark: big, soft, letters settling up a few px
            tw += [
                f"tl.fromTo('#{kid}',{{autoAlpha:0,scale:1.14}},{{autoAlpha:1,scale:1,duration:.3,ease:'expo.out',immediateRender:false}},{t:.3f});",
                f"tl.fromTo('#{kid}b',{{filter:'blur(26px)'}},{{filter:'blur(0px)',duration:.26,ease:'power3.out',immediateRender:false}},{t:.3f});",
                f"tl.fromTo('#{kid} .ch',{{y:28}},{{y:0,duration:.36,ease:'expo.out',stagger:.014,immediateRender:false}},{t:.3f});",
            ]
        else:                     # pops forward off the speaker: small and soft, overshoots, settles
            tw += [
                f"tl.fromTo('#{kid}',{{autoAlpha:0,scale:.6}},{{autoAlpha:1,scale:1,duration:.26,ease:'back.out(2)',immediateRender:false}},{t:.3f});",
                f"tl.fromTo('#{kid}b',{{filter:'blur(18px)'}},{{filter:'blur(0px)',duration:.2,ease:'power3.out',immediateRender:false}},{t:.3f});",
            ]
        if F_OUT is not None:     # words clear with the first frames of the release
            t2, sc = F(F_OUT - 1), (1.05 if layer == 'back' else .88)
            tw += [f"tl.to('#{kid}',{{autoAlpha:0,scale:{sc},duration:.12,ease:'power1.in'}},{t2:.3f});",
                   f"tl.to('#{kid}b',{{filter:'blur(18px)',duration:.12,ease:'power1.in'}},{t2:.3f});",
                   f"tl.set('#{kid}',{{autoAlpha:0}},{t2 + .122:.3f});"]
    return back, front, tw


def audio(dur):
    if not (SOUNDS and ON['SFX']):
        return []
    hit = 'assets_fx/impact-bass-short.mp3'
    if not os.path.exists(os.path.join(HERE, hit)):
        hit = 'assets/sfx/impact-bass-1.mp3'
    cues = [(hit, (F_IN - 1) / FPS, .10)]
    if F_OUT is not None:
        cues.append(('assets/sfx/whoosh-short.mp3', (F_OUT - 3) / FPS, .13))
    out = []
    for k, (src, t, vol) in enumerate(cues):
        if not os.path.exists(os.path.join(HERE, src)):
            print(f'  sound {src} is not in the slot: left out')
            continue
        d = math.floor(min(probe(src, 'format=duration'), dur - t) * 1000) / 1000
        out.append(f'<audio id="sfx{k}" src="{src}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + k}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    n = json.load(open(os.path.join(HERE, 'clip.json')))['frames']
    mpath = os.path.join(HERE, 'work/measure.json')
    if not os.path.exists(mpath):
        sys.exit('no work/measure.json: run prep.py first')
    M = json.load(open(mpath))
    if M['stamp'] != stamp() or M['frames'] != n or not M.get('baked'):
        sys.exit('the CLIP block changed since prep.py ran (or it only measured): run prep.py again')
    if F_IN < 3:
        sys.exit('F_IN must be 3 or later: the slot starts on plain footage')
    end = end_frame(n)
    if F_OUT is not None and (F_OUT < F_IN + EASE_IN_FR + 6 or end + 5 > n - 1):
        sys.exit(f'F_OUT {F_OUT}: needs to be {F_IN + EASE_IN_FR + 6} or later and {n - EASE_OUT_FR - 5} or earlier '
                 f'(the lights are back up {EASE_OUT_FR + 4} frames after it). Or None = end on a cut.')
    for text, frame, *_ in KEYWORDS:
        if not (F_IN <= frame <= (F_OUT if F_OUT is not None else n) - 6):
            sys.exit(f'key word "{text}" at f{frame}: has to land while the lights are down ({F_IN} to {(F_OUT or n) - 6})')
    dur = math.floor(n / FPS * 1000) / 1000          # rounded up it renders one frame too many
    words = place_words(M) if ON['CAPTIONS'] else []
    back, front, tw = tweens(words, n, dur)
    S = M['summary']
    nl = '\n'
    v = f'muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}"'
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#06080F}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#06080F}}
#stage{{position:absolute;inset:0;transform-origin:{S['head_x']:.0f}px {S['neck_y']:.0f}px;{f'filter:{GRADE};' if GRADE else ''}}}
.lay{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.lay video{{position:absolute;left:0;top:0;width:1080px;height:1920px;display:block}}
#room{{z-index:0}}
#dark{{z-index:1}}
.kw{{position:absolute;white-space:nowrap;font-family:'Inter Tight';font-weight:900;line-height:.9;
  letter-spacing:{TRACK}em;transform-origin:50% 62%}}
.kw .kwb{{display:inline-block}}
.kw .ch{{display:inline-block}}
.kw.back{{z-index:3;filter:drop-shadow(0 12px 36px rgba(4,6,14,.5))}}
#subjw{{z-index:4}}
.kw.front{{z-index:7;filter:drop-shadow(0 20px 40px rgba(3,5,12,.62)) drop-shadow(0 3px 8px rgba(3,5,12,.4))}}
'''
    html = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(dur))}
  <div id="stage">
    <div id="room" class="lay"><video id="bgv" src="assets/aroll.mp4" {v} data-track-index="0"></video></div>
    <div id="dark" class="lay"><video id="darkv" src="assets/room_dark.mp4" {v} data-track-index="1"></video></div>
{nl.join(back)}
    <div id="subjw" class="lay"><video id="subj" src="assets/subject_spot.webm" {v} data-track-index="3"></video></div>
{nl.join(front)}
  </div>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open(os.path.join(HERE, 'index.html'), 'w').write(html)
    print(f'wrote index.html  {n} frames ({dur:.3f}s)  lights fall f{F_IN}, down by f{F_IN + EASE_IN_FR - 1}, '
          + (f'come back f{F_OUT}, plain picture again from f{end}' if F_OUT is not None else 'stay down to the last frame (END ON A CUT)')
          + f'  words {"on" if ON["CAPTIONS"] else "OFF"}  sounds {"on" if SOUNDS and ON["SFX"] else "OFF"}  safe guide {"ON" if SAFE else "off"}')
    print(f'render to: renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    build()
