#!/usr/bin/env python3
"""clone: copies of the speaker spring up from behind the furniture, one per spoken beat, each running a few tenths
of a second behind the speaker (a canon, never in unison). Optional payoff: all of them snap into sync with the speaker on one word.
Optional exit: they drop back down before the slot ends.

Layers (bottom to top):  aroll plate  ->  clone_<id>.webm (baked)  ->  fg.webm (the speaker + the furniture)  ->  captions
bake.py does the pixel work; this file places the layers and animates them. Read effect.md for the run order.

    python3 build.py            writes index.html
    SAFE=1 python3 build.py     + Instagram safe-zone guide (snapshots only, never render with it)
    CAPTIONS=0                  no caption words (the main reel captions the slot)
    SFX=0                       no sounds from this effect
"""
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# ==== CLIP (edit this) ====
# Run prep.py first. It prints the speaker's head anchor, the widest pose and the word hits, and saves grid frames in
# work/prep/ to read pixel positions from. The values below are the demo's (example/clip.md): replace every one.

CLONES = [
    # One line per clone, in the order they appear.
    #   id      letter used in file and element names
    #   word_f  frame the VOWEL of the trigger word lands on ("hit" in work/onsets.txt). The pop starts 4 frames earlier.
    #   x       x of the clone's head centre, px. A spot where the wall above the furniture is free (no red tint in
    #           the grid frames). bake.py prints each clone's visible x range: keep it inside 6..1074.
    #   top     y of the clone's head top, px. Set it so the furniture edge (or the real speaker) crosses the clone
    #           between shoulders and hips: furniture edge y at that x, minus 1.5 to 2.5 clone head heights
    #           (clone head height = scale x prep.py "head ... x H"). Sitting upright: the speaker's own head top + 60 to 120.
    #   scale   size vs the real speaker, 0.5 to 0.7 = (camera to the speaker) / (camera to the spot behind the furniture).
    #   lag     frames the clone runs behind the speaker (6 = 0.2 s). Give each clone a different lag.
    dict(id='L', word_f=37, x=287, top=520, scale=.64, lag=6),
    dict(id='R', word_f=69, x=781, top=520, scale=.64, lag=9),
]

# Payoff frame: every lag snaps to 0, the clones flash-pop together, the stage punches in. The vowel of the payoff
# word (work/onsets.txt). None = no payoff, the clones just stay in canon.
SYNC_F = 115

# Frame the clones drop back behind the furniture. None = they stay to the last frame (fine for a stand-alone clip).
# In a reel slot set it ~14 frames before the end so the slot hands back to the plain a-roll.
EXIT_F = None

# Top edge of the furniture the clones stand behind, as rough points (x, y) left to right across the WHOLE frame
# width, read from work/prep/grid_000.jpg (within ~10 px is enough: bake.py snaps every column to the real edge).
# Where the speaker covers the edge, continue the line straight through the speaker.
OCCLUDER_LINE = [(0, 998), (42, 998), (52, 940), (240, 960), (880, 966), (1080, 968)]

# Side the key light comes from, 'left' or 'right' (the brighter side of the speaker's face). Shadows fall the other way.
LIGHT_FROM = 'right'

# Caption groups: (top y px, [(word, onset frame, 'y' = accent colour or '')], frame the group clears or None).
# Chest band, in front of the speaker, never over the speaker's face. Dropped with CAPTIONS=0.
CAP_X = 540                  # x the captions are centred on (the speaker's chest centre)
CAPS = [
    (1078, [('you', 1, ''), ('need', 3, ''), ('edits', 13, '')], 24),
    (1078, [('like', 25, ''), ('this', 36, 'y')], 54),
    (1078, [('like', 57, ''), ('this', 68, 'y')], 88),
    (1052, [('or', 91, ''), ('like', 104, '')], None),
]
# Big accent word on the payoff: (word, frame, top y px, frame it clears or None). None instead of the tuple = no word.
PUNCH = ('that', 115, 1118, None)

ACCENT = '#FAE67A'           # butter yellow (accent words, flash tint)
VIGNETTE = 0.0               # 0 for a reel slot (the slot must match the a-roll around it); 0.22 for a stand-alone clip
# ==== END CLIP ====

# ---- machinery ------------------------------------------------------------------------------------------------------
FPS = 30
POP_LEAD = 4                 # frames between the start of the pop and the vowel it lands on
SFX_GAIN = 0.75
FP = shutil.which('ffprobe') or 'ffprobe'
N = json.load(open(os.path.join(HERE, 'clip.json')))['frames']
_MP = os.path.join(HERE, 'work/measure.json')
M = json.load(open(_MP)) if os.path.exists(_MP) else None


def F(n):
    """time of frame n, nudged 2ms early so a tl.set lands ON that frame"""
    return n / FPS - .002


def f_in(c):
    return max(c['lag'] + 1, c['word_f'] - POP_LEAD)


def line_y(x):
    """the rough occluder line at column x"""
    pts = sorted(OCCLUDER_LINE)
    if x <= pts[0][0]:
        return pts[0][1]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if x <= xb:
            return ya + (yb - ya) * (x - xa) / max(xb - xa, 1e-6)
    return pts[-1][1]


def canvas(c):
    """comp-space rect (x0, y0, w, h) of a clone's baked video: their widest pose at this scale + room for the shadow"""
    if M is None:
        raise SystemExit('work/measure.json missing: run prep.py first')
    s, ax = c['scale'], M['anchor'][0]
    x0 = int(max(0, c['x'] + s * (M['src_x'][0] - ax) - 70))
    x1 = int(min(1080, c['x'] + s * (M['src_x'][1] - ax) + 70))
    y0 = int(max(0, c['top'] - s * 60 - 70))
    y1 = int(min(1920, max(line_y(x) for x in range(x0, x1 + 1, 8)) + 80))
    return x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2


def drop(c):
    """px a clone starts below its rest position: its head top ends under the lowest furniture edge in its columns"""
    x0, y0, w, h = canvas(c)
    return int(max(line_y(x) for x in range(x0, x0 + w + 1, 8)) - (c['top'] - c['scale'] * 60) + 24)


def lag_at(c, i):
    return 0 if (SYNC_F is not None and i >= SYNC_F) else c['lag']


def present(c, i):
    """is this clone on screen at frame i (bake.py skips the others)"""
    return f_in(c) - 1 <= i <= (N if EXIT_F is None else EXIT_F + 10)


def probe(path):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True).stdout)


def audio(dur):
    if os.environ.get('SFX') == '0':
        return []
    # whoosh-short is a stock template sound (assets/sfx); the soft low hit ships with the effect (assets_fx)
    sfx = [('assets/sfx/whoosh-short.mp3', f_in(c) / FPS - .09, .24) for c in CLONES]
    if SYNC_F is not None:
        sfx += [('assets/sfx/whoosh-short.mp3', SYNC_F / FPS - .16, .2), ('assets_fx/impact-bass-short.mp3', SYNC_F / FPS - .01, .09)]
    if EXIT_F is not None:
        sfx += [('assets/sfx/whoosh-short.mp3', EXIT_F / FPS - .1, .16)]
    out, lanes = [], []
    for k, (src, t, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        t = max(0, t)
        if not os.path.exists(os.path.join(HERE, src)):
            print(f'!! sound {src} missing, skipped')
            continue
        d = min(probe(os.path.join(HERE, src)), dur - t)
        if d <= .05:
            continue
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0); lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{src}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def clone(c, k, dur):
    """one clone layer: wrapper (pop motion) > inner (flash filter) > baked alpha video"""
    x0, y0, w, h = canvas(c)
    i, d = c['id'], drop(c)
    ox, oy = c['x'] - x0, line_y(c['x']) - y0          # transform origin: under the speaker's spine, on the furniture edge
    t = F(f_in(c))
    html = (f'<div id="cw{i}" class="cw" style="left:{x0}px;top:{y0}px;width:{w}px;height:{h}px;transform-origin:{ox:.0f}px {oy:.0f}px">'
            f'<div id="cf{i}" class="cf"><video id="cv{i}" src="assets/clone_{i}.webm" muted playsinline data-start="0" '
            f'data-media-start="0" data-duration="{dur:.3f}" data-track-index="{3 + k}" style="width:{w}px;height:{h}px"></video></div></div>')
    glow0 = "brightness(2.2) blur(4px) drop-shadow(0px 0px 16px rgba(255,244,200,0.55))"
    glow1 = "brightness(1) blur(0px) drop-shadow(0px 0px 0px rgba(255,244,200,0))"
    tw = [f"gsap.set('#cw{i}',{{autoAlpha:0,y:{d}}});",
          f"tl.set('#cw{i}',{{autoAlpha:1}},{t:.3f});",
          # spring up from behind the furniture: fast rise, small overshoot, a stretch that settles
          f"tl.fromTo('#cw{i}',{{y:{d}}},{{y:0,duration:.36,ease:'back.out(1.15)',immediateRender:false}},{t:.3f});",
          f"tl.fromTo('#cw{i}',{{scaleY:1.09,scaleX:.955}},{{scaleY:1,scaleX:1,duration:.5,ease:'power3.out',immediateRender:false}},{t:.3f});",
          f"tl.fromTo('#cf{i}',{{filter:'{glow0}'}},{{filter:'{glow1}',duration:.42,ease:'power2.out',immediateRender:false}},{t + .03:.3f});",
          f"tl.set('#cf{i}',{{filter:'none'}},{t + .47:.3f});"]
    if SYNC_F is not None:
        ts = F(SYNC_F)
        tw += [f"tl.fromTo('#cw{i}',{{scale:1.1}},{{scale:1,duration:.5,ease:'expo.out',immediateRender:false}},{ts:.3f});",
               f"tl.fromTo('#cf{i}',{{filter:'brightness(1.9) blur(2px) drop-shadow(0px 0px 14px rgba(255,244,200,0.5))'}},"
               f"{{filter:'{glow1}',duration:.4,ease:'power2.out',immediateRender:false}},{ts:.3f});",
               f"tl.set('#cf{i}',{{filter:'none'}},{ts + .42:.3f});"]
    if EXIT_F is not None:
        te = F(EXIT_F) + k * .05          # one after the other, 1.5 frames apart
        tw += [f"tl.to('#cw{i}',{{y:{d},scaleY:1.06,duration:.24,ease:'power3.in'}},{te:.3f});",
               f"tl.set('#cw{i}',{{autoAlpha:0}},{te + .25:.3f});"]
    return html, tw


def pop(sel, t):
    return [f"gsap.set('{sel}',{{autoAlpha:0}});",
            f"tl.set('{sel}',{{autoAlpha:1}},{t:.3f});",
            f"tl.fromTo('{sel}',{{scale:1.22,filter:'blur(22px)'}},{{scale:1,filter:'blur(0px)',duration:.2,ease:'power3.out',"
            f"immediateRender:false}},{t:.3f});"]


def clear(sel, f):
    return [f"tl.to('{sel}',{{autoAlpha:0,filter:'blur(14px)',duration:.12,ease:'power2.in'}},{F(f) - .12:.3f});",
            f"tl.set('{sel}',{{autoAlpha:0}},{F(f):.3f});"]


def captions():
    if os.environ.get('CAPTIONS') == '0':
        return [], []
    html, tw = [], []
    left = CAP_X - 540
    for g, (top, words, out) in enumerate(CAPS):
        gid = f'c{g}'
        spans = ''.join(f'<span id="{gid}w{j}" class="w {cls}">{w}</span>' for j, (w, _, cls) in enumerate(words))
        html.append(f'<div id="{gid}" class="cap" style="top:{top}px;left:{left}px">{spans}</div>')
        for j, (_, f, _) in enumerate(words):
            tw += pop(f'#{gid}w{j}', F(f))
        if out is not None:
            tw += clear(f'#{gid}', out)
    if PUNCH:
        word, f, top, out = PUNCH
        html.append(f'<div id="punch" class="cap big" style="top:{top}px;left:{left}px"><span id="punchw" class="w y">{word}</span></div>')
        t = F(f)
        tw += ["gsap.set('#punchw',{autoAlpha:0});",
               f"tl.set('#punchw',{{autoAlpha:1}},{t:.3f});",
               f"tl.fromTo('#punchw',{{scale:1.5,filter:'blur(26px)'}},{{scale:1,filter:'blur(0px)',duration:.32,ease:'expo.out',"
               f"immediateRender:false}},{t:.3f});"]
        if out is not None:
            tw += clear('#punch', out)
    return html, tw


CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0;transform-origin:50% 40%}}
.full{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}}
.cw{{position:absolute;z-index:2}}
.cf{{position:absolute;inset:0}}
.cf video{{position:absolute;left:0;top:0;display:block}}
#fgwrap{{position:absolute;inset:0;z-index:4}}
#vig{{position:absolute;inset:0;z-index:6;pointer-events:none;
  background:radial-gradient(90% 70% at 50% 42%,rgba(8,10,8,0) 55%,rgba(8,10,8,{VIGNETTE}) 100%)}}
#flash{{position:absolute;inset:0;z-index:6;pointer-events:none;background:#FFF6D8;mix-blend-mode:soft-light}}
.cap{{position:absolute;width:1080px;z-index:8;text-align:center;font-family:'Inter Tight';font-weight:800;font-size:84px;
  letter-spacing:-.05em;line-height:.9;color:#fff;text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.3);white-space:nowrap}}
.cap .w{{display:inline-block;margin:0 .1em;transform-origin:50% 60%}}
.cap .y{{color:{ACCENT}}}
.cap.big{{font-weight:900;font-size:190px;letter-spacing:-.055em}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    dur = round(N / FPS, 3)
    c_html, tw = [], []
    for k, c in enumerate(CLONES):
        h, t = clone(c, k, dur)
        c_html.append(h)
        tw += t
    cap_html, cap_tw = captions()
    tw += cap_tw
    tw.append("gsap.set('#flash',{autoAlpha:0});")
    if SYNC_F is not None:
        ts = F(SYNC_F)
        tw += [f"tl.fromTo('#stage',{{scale:1.04}},{{scale:1,duration:.5,ease:'expo.out',immediateRender:false}},{ts:.3f});",
               f"tl.set('#flash',{{autoAlpha:.3}},{ts:.3f});",
               f"tl.to('#flash',{{autoAlpha:0,duration:.4,ease:'power2.out'}},{ts + .001:.3f});"]
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
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(dur))}
  <div id="stage">
    <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
{nl.join(c_html)}
    <div id="fgwrap"><video id="fgv" class="full" src="assets/fg.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div>
  </div>
  {'<div id="vig"></div>' if VIGNETTE > 0 else ''}
  <div id="flash"></div>
{nl.join(cap_html)}
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
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


if __name__ == '__main__':
    for need in ('assets/fg.webm',) + tuple(f"assets/clone_{c['id']}.webm" for c in CLONES):
        if not os.path.exists(os.path.join(HERE, need)):
            print(f'!! {need} missing: run bake.py before rendering')
    open(os.path.join(HERE, 'index.html'), 'w').write(build())
    print(f'wrote index.html  {N} frames  ' + '  '.join(f"{c['id']}: pop f{f_in(c)} canvas {canvas(c)} drop {drop(c)}" for c in CLONES)
          + f'  sync {SYNC_F}  exit {EXIT_F}' + ('  [SAFE GUIDE ON]' if os.environ.get('SAFE') else ''))
