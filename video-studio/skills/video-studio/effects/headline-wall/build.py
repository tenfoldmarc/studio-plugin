#!/usr/bin/env python3
"""HEADLINE WALL: the wall behind the speaker fills with headline / post / search cards that all say the same thing
in different words, glued to the room behind the speaker, and one phrase gets swiped in highlighter on every card at once.

  F_START   first card slides onto the wall, then they pile up faster and faster until F_PEAK
  F_ACCENT  the key word: highlighter swipe on every card, small camera bump, one low hit
  HEROES    big readable cards that each land ON a spoken word, alternating sides of their head
  all clip  slow push-in on their face, the room dims a touch as the wall fills

Layers: plate < dim < WALL (cards; ride a per-frame room homography if the camera moves) < their cutout < vignette.

Run order (from the slot folder, see effect.md):
  python onsets.py                 word onsets as frames  -> fill the CLIP block
  python prep.py                   track + matte + layout -> work/layout.json, work/layout.jpg (look at it)
  python3 build.py                 writes index.html      (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 no-op)
"""
import json
import math
import os
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
# The headlines: a plain list, one string per card, every one a version of the SAME message in different words.
# Put the phrase to highlight in [brackets] (one per headline). Keep them under ~40 characters; the list is cycled
# if the wall needs more cards than you wrote. No real outlets, people, numbers or results the speaker did not say.
HEADLINES = [
    '[Claude] cut my whole reel.',
    '[Claude] edits everyone’s videos now',
    '[Claude] is the new video editor',
    '[Claude] edits video now',
    'POV: [Claude] edits your reel',
    'Dropped my clips in. [Claude] did the edit.',
    '[Claude] just edited my video',
    'Editors are talking about [Claude]',
    'wait, [Claude] edits videos??',
    '[Claude] video editing',
    'So [Claude] edits videos now',
    'Edited by [Claude].',
    'Your next video editor is [Claude]',
    'I had [Claude] edit this',
    'ok [Claude] can edit video',
    'Re: [Claude] edits videos?',
    '[Claude] edits. You post.',
    'Video editing, by [Claude]',
    'did [Claude] edit this??',
    '[Claude] can cut your reel',
]
# Hero cards: (headline, frame of the spoken word it lands on). 2 to 4 of them, in spoken order. They alternate
# sides of the speaker's head, so each needs clear wall beside the speaker. Frames come from `python onsets.py`.
HEROES = [
    ('[Claude] can edit your videos now', 42),                        # "Claude"
    ('I let AI edit my reel. [Claude] did the whole thing.', 56),     # "edit"
    ('[Claude] edits video now?', 65),                                # "your"
    ('[Claude] edited this entire reel', 71),                         # "videos"
]
SEARCH = 'can [claude] edit videos'   # a search-bar pill opposite the first hero, lowercase like a real query. None = no pill
F_START = 2          # frame of the speaker's first syllable: the first card starts here
F_PEAK = 28          # frame where the opening phrase ends ("everybody's talking"): the last pile card starts here
F_ACCENT = 42        # frame of the key word (the [bracketed] one): highlighter + bump + hit. Usually = HEROES[0] frame
DENSITY = 1.8        # 1 = cards arrive evenly, higher = slow start and a faster and faster pile-up
LEAD = 4             # frames a hero starts before its word so it is ~90% landed ON the word (do not go under 3)
F_OUT = None         # frame the cards whip off the wall again (a slot inside one continuous take, e.g. b-roll).
                     # None = the wall stays to the last frame. With F_OUT set PUSH and BUMP must be 1 and the first
                     # frames before F_START and the last 2 frames come out as untouched a-roll. Needs F_OUT <= frames - 12
KEEP_OUT = []        # screen rectangles (x0, y0, x1, y1) no card may enter on any frame, e.g. the main reel's label
                     # pill [(140, 222, 940, 322)]
VOICE = True         # False = silent slot (no a-roll audio in the render; also run with SFX=0)

WALL = None          # (x0, y0, x1, y1) px: the bare wall the cards may cover. None = full width, down to the speaker's elbows.
                     # SET IT when furniture, a window or a door sits beside the speaker: look at work/layout.jpg (cyan box)
FACE = None          # (x, y) px the push-in aims at. None = measured from the speaker's cutout
HERO_FIRST_SIDE = 'L'  # side of the speaker's head the first hero lands on ('L' or 'R'): pick the side with more clear wall
N_MID = None         # mid-depth cards (readable, inside the safe zone, heroes land on top). None = by wall area (5 to 10)
N_FAR = None         # far cards (small, soft, dim). None = as many as the wall area holds (6 to 15)
FAR_BLEED_SIDES = True  # far cards may run off the left / right frame edge as texture (never into the top 220px)
PUSH = 1.06          # slow push-in over the whole slot (1 = none; keep under 1.08 on 1080p footage)
BUMP = 1.032         # camera bump on the accent word (1 = none)
DIM = 1.0            # how much the room dims as the wall fills (0 = not at all; raise to 1.3 on a white wall)
ACCENT = '#FAE67A'   # highlighter colour (butter yellow; never orange)
OUTLETS = ['Tech newsletter', 'Creator briefing', 'Trade magazine', 'Weekly roundup', 'Local paper', 'Marketing blog',
           'Business desk', 'Industry memo']                     # placeholder source labels, must stay generic
PEOPLE = ['A founder', 'Agency owner', 'A creator', 'Video editor', 'Founder']   # placeholder "who posted it" labels
CHAT_REPLIES = ['since when', 'no way', 'wait what']             # second bubble on chat cards
DARK_LABEL = 'Group chat'                                        # small label on the dark cards
FOREGROUND = []      # polygons [(x, y), ...] in reference-frame px of furniture that stands IN FRONT of the wall (a
                     # pillow, a sofa back): cards then pass behind it. Only needed when a card has to cross it;
                     # after editing run `prep.py matte`
FIX_MATTE = True     # bake assets/fg.webm with motion-blurred sleeves / hands made solid. False = use subject.webm as is
TRACK_YMAX = None    # px: only wall above this line is used for the camera track. None = 1100. Lower it to the top
                     # of a sofa / desk if the track wobbles (layout.jpg cards slide off the wall on early frames)
REF = None           # reference frame the layout is drawn in. None = 4 frames before the end (a settled frame)
SEED = 7             # change it to reshuffle tilts and far-card positions
# (sound, frame, base volume). Base volumes are the template's; everything is played at 0.75x. click-soft is a very
# quiet file, hence .36. Files: assets/sfx/<name>.mp3 or assets_fx/<name>.mp3
SOUNDS = [('whoosh-short', F_START - 1, .22), ('impact-bass-short', F_ACCENT, .10)] + \
         [('click-soft', f - 1, .34) for _, f in HEROES[1:]]
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
PARALLAX = {'far': 1.000, 'mid': 1.012, 'near': 1.026}     # extra push per depth layer by the end of the slot
FLIGHT_BLUR = {'far': 0, 'mid': 8, 'near': 10}
SFX_GAIN = 0.75
INK = '#14161C'
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def F(n):
    """time of frame n, nudged 2ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


def camera(track, nfr):
    """per-frame CSS matrix3d strings (reference px -> frame px), smoothed harder where the camera is at rest"""
    if not track or track.get('static'):
        return None
    Hm = [[v / h[8] for v in h] for h in track['hom']]
    assert len(Hm) == nfr, (len(Hm), nfr)

    def at(h, x, y):
        d = h[6] * x + h[7] * y + h[8]
        return (h[0] * x + h[1] * y + h[2]) / d, (h[3] * x + h[4] * y + h[5]) / d

    def smooth(sig):
        out = []
        for n in range(nfr):
            acc, wsum = [0.0] * 9, 0.0
            for k in range(-8, 9):
                m = min(max(n + k, 0), nfr - 1)
                wgt = math.exp(-.5 * (k / sig) ** 2)
                wsum += wgt
                acc = [a + wgt * v for a, v in zip(acc, Hm[m])]
            out.append([a / wsum for a in acc])
        return out
    speed = [0.0] * nfr
    for n in range(1, nfr):
        speed[n] = max(math.hypot(at(Hm[n], x, y)[0] - at(Hm[n - 1], x, y)[0], at(Hm[n], x, y)[1] - at(Hm[n - 1], x, y)[1])
                       for x, y in ((150, 300), (930, 300), (150, 900), (930, 900)))
    speed[0] = speed[1] if nfr > 1 else 0
    speed = [max(speed[max(0, n - 3):n + 4]) for n in range(nfr)]
    fast, slow = smooth(.8), smooth(3.0)
    mats = []
    for n in range(nfr):
        k = min(max(1 - (speed[n] - .3) / .7, 0), 1)      # at rest -> heavy smoothing, so the cards do not shimmer
        h = [a * (1 - k) + b * k for a, b in zip(fast[n], slow[n])]
        h11, h12, h13, h21, h22, h23, h31, h32, h33 = h
        mats.append(f'matrix3d({h11:.6f},{h21:.6f},0,{h31:.9f},{h12:.6f},{h22:.6f},0,{h32:.9f},0,0,1,0,{h13:.3f},{h23:.3f},0,{h33:.6f})')
    return mats


def probe(path, entries, stream='v:0'):
    ffp = shutil.which('ffprobe') or 'ffprobe'
    sel = ['-select_streams', stream] if stream else []
    return subprocess.run([ffp, '-v', 'error'] + sel + ['-show_entries', entries, '-of', 'csv=p=0', path],
                          capture_output=True, text=True).stdout.strip()


def audio(dur):
    if os.environ.get('SFX') == '0':
        return []
    out, lanes = [], []
    for k, (name, frame, vol) in enumerate(sorted(SOUNDS, key=lambda x: x[1])):
        path = next((p for p in (f'assets/sfx/{name}.mp3', f'assets_fx/{name}.mp3') if os.path.exists(p)), None)
        if not path:
            print(f'  (sound {name} not found in assets/sfx or assets_fx: skipped)')
            continue
        t = F(frame)
        if t >= dur - .05:
            continue
        d = min(float(probe(path, 'format=duration', None)), dur - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def main():
    os.chdir(HERE)
    sys.path.insert(0, HERE)
    import cards as C
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the duration UP to whole frames, and
    #                             101 / 30 written as 3.367 would render 102 frames instead of the slot's 101
    if not os.path.exists('work/layout.json'):
        sys.exit('work/layout.json is missing: run prep.py first (see effect.md)')
    lay = json.load(open('work/layout.json'))
    if lay['frames'] != nfr:
        sys.exit('work/layout.json belongs to another clip: run prep.py --force')
    track = json.load(open('work/track.json')) if os.path.exists('work/track.json') else None
    cutout = 'assets/fg.webm' if (FIX_MATTE and os.path.exists('assets/fg.webm')) else 'assets/subject.webm'
    face, head = lay['face'], lay['head']
    cards = lay['cards']

    # schedule: pile cards arrive faster and faster between F_START and F_PEAK, heroes LEAD frames before their word
    pile = sorted([c for c in cards if not c['hero']], key=lambda c: c['order'])
    t0, t1 = F(F_START), F(F_PEAK)
    for i, c in enumerate(pile):
        c['t'] = t0 + (t1 - t0) * (i / max(1, len(pile) - 1)) ** (1 / DENSITY)
    for c in cards:
        if c['hero']:
            c['t'] = F(c['frame'] - LEAD)
    t_acc = F(F_ACCENT)
    heroes = [c for c in cards if c['hero']]
    ax = heroes[0]['x'] if heroes else head['cx']

    html = {'far': [], 'mid': [], 'near': []}
    tw = []
    for z, c in enumerate(sorted(cards, key=lambda c: c['t'])):          # later cards sit on top inside a layer
        cid, L = c['id'], c['layer']
        s = C.LAYER_SCALE[L] * c.get('shrink', 1)
        html[L].append(f'<div id="{cid}" class="c {L}" style="left:{c["x"]}px;top:{c["y"]}px;width:{c["w"]}px;z-index:{z + 1}">'
                       f'<div id="{cid}i" class="ci">{C.body(c["kind"], c["lines"], c["src"])}</div></div>')
        tw.append(f"gsap.set('#{cid}',{{xPercent:-50,yPercent:-50,rotation:{c['rot']},scale:{s:.3f}}});"
                  f"gsap.set('#{cid}i',{{autoAlpha:0}});gsap.set('#{cid} .mk',{{scaleX:0,skewX:-9,rotation:-1.2}});")
        # flight: slides along the wall from the nearest frame edge (never across the speaker's face), bigger + blurred, tilt settles
        t = c['t']
        if not KEEP_OUT and c['y'] < head['top'] - 40 and abs(c['x'] - head['cx']) < 340:
            ox, oy = (c['x'] - head['cx']) * .5, -640
        else:
            ox, oy = (-700 if c['x'] < head['cx'] else 700), (c['y'] - face[1]) * .55
        ox, oy = ox / s, oy / s
        dr = (14 if (z % 2) else -14) + c['rot'] * .6
        d = .38 if c['hero'] else .40
        tw.append(f"tl.set('#{cid}i',{{autoAlpha:1}},{t:.3f});"
                  f"tl.fromTo('#{cid}i',{{opacity:0}},{{opacity:1,duration:.07,ease:'none',immediateRender:false}},{t:.3f});"
                  f"tl.fromTo('#{cid}i',{{x:{ox:.0f},y:{oy:.0f},scale:{1.34 if c['hero'] else 1.24}}},{{x:0,y:0,scale:1,duration:{d},"
                  f"ease:'expo.out',immediateRender:false}},{t:.3f});"
                  f"tl.fromTo('#{cid}i',{{rotation:{dr:.1f}}},{{rotation:0,duration:{d + .16:.2f},ease:'back.out(2.4)',"
                  f"immediateRender:false}},{t:.3f});")
        if FLIGHT_BLUR[L]:
            tw.append(f"tl.fromTo('#{cid}i',{{filter:'blur({FLIGHT_BLUR[L]}px)'}},{{filter:'blur(0px)',duration:.2,ease:'power2.out',"
                      f"immediateRender:false}},{t:.3f});")
        # highlighter: everything already on the wall is swiped on the accent word (sweeping out from the first hero),
        # later cards a beat after they land
        th = max(t_acc + abs(c['x'] - ax) / 1000 * .17, t + .14)
        tw.append(f"tl.to('#{cid} .mk',{{scaleX:1,duration:.24,ease:'power3.out'}},{th:.3f});")
        if C.base(c['kind']) == 'dark':
            tw.append(f"tl.to('#{cid} .tx',{{color:'{INK}',duration:.1,ease:'none'}},{th + .03:.3f});")
        if F_OUT is not None:
            # whip-out: back the way it came, staggered over 3 frames, gone in 6
            to = F(F_OUT) + (z % 4) * (.1 / 3)
            tw.append(f"tl.to('#{cid}i',{{x:{ox * .8:.0f},y:{oy * .8:.0f},scale:1.18,rotation:{-dr * .5:.1f},duration:.2,ease:'power3.in'}},{to:.3f});"
                      f"tl.to('#{cid}i',{{opacity:0,duration:.07,ease:'none'}},{to + .13:.3f});"
                      f"tl.set('#{cid}i',{{autoAlpha:0}},{to + .21:.3f});")
            if FLIGHT_BLUR[L]:
                tw.append(f"tl.to('#{cid}i',{{filter:'blur({FLIGHT_BLUR[L]}px)',duration:.16,ease:'power2.in'}},{to + .04:.3f});")

    mats = camera(track, nfr)
    cam_js = ''
    if mats:
        # function-based property: GSAP calls cam.frame(v) on every render (seek-safe, no callbacks involved)
        cam_js = (f"const MATS = {json.dumps(mats)};\n"
                  "const wallEl = document.getElementById('wall');\n"
                  "const cam = { f: 0, frame(v) { if (v === undefined) return this.f; this.f = v;\n"
                  "  const n = Math.max(0, Math.min(MATS.length - 1, Math.round(v))); wallEl.style.transform = MATS[n]; } };\n"
                  "cam.frame(0);\n"
                  f"tl.to(cam, {{ frame: {nfr - 1}, duration: {(nfr - 1) / FPS:.5f}, ease: 'none' }}, 0);")
    fill = max(.2, t1 + .15 - t0)
    if F_OUT is not None:
        if PUSH != 1 or BUMP != 1:
            sys.exit('F_OUT is set: PUSH and BUMP must be 1 so the first and last frames stay untouched a-roll')
        if F_OUT > nfr - 12:
            sys.exit(f'F_OUT {F_OUT} is too late: the whip-out needs 10 frames + 2 untouched ones (max {nfr - 12})')
        fill = min(fill, max(.15, F(F_OUT) - t0))
    else:
        tw += [f"tl.fromTo('#stage',{{scale:1}},{{scale:{PUSH},duration:{dur:.3f},ease:'sine.inOut',immediateRender:false}},0);",
               *([f"tl.fromTo('#bump',{{scale:{BUMP}}},{{scale:1,duration:.5,ease:'expo.out',immediateRender:false}},{t_acc:.3f});"]
                 if BUMP != 1 else []),
               *[f"tl.fromTo('#L{k}',{{scale:1}},{{scale:{v},duration:{dur:.3f},ease:'sine.inOut',immediateRender:false}},0);"
                 for k, v in PARALLAX.items() if v != 1]]
    tw += [
        # the cutout layer only exists while cards are up: before / after, the frame is the untouched plate
        "gsap.set('#fgwrap',{autoAlpha:0});",
        f"tl.set('#fgwrap',{{autoAlpha:1}},{max(0.0, t0 - .004):.3f});",
        "gsap.set('#dim',{opacity:0});",
        f"tl.to('#dim',{{opacity:1,duration:{fill:.3f},ease:'power1.inOut'}},{t0:.3f});",
        f"tl.to('#fgwrap',{{filter:'drop-shadow(0px 22px 46px rgba(0,0,0,0.5))',duration:{fill:.3f},ease:'power1.inOut'}},{t0:.3f});",
    ]
    if F_OUT is not None:
        to = F(F_OUT)
        tw += [f"tl.to('#dim',{{opacity:0,duration:.26,ease:'power1.inOut'}},{to + .04:.3f});",
               f"tl.to('#fgwrap',{{filter:'drop-shadow(0px 22px 46px rgba(0,0,0,0))',duration:.26,ease:'power1.inOut'}},{to + .04:.3f});",
               f"tl.set('#fgwrap',{{autoAlpha:0}},{to + .32:.3f});"]
    d0, d1 = min(.9, .30 * DIM), min(.95, .52 * DIM)
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage,#bump{{position:absolute;inset:0;transform-origin:{face[0]}px {face[1]}px}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:1}}
#dim{{position:absolute;inset:-40px;z-index:2;background:radial-gradient(70% 55% at {face[0] / 10.8:.1f}% {max(10, (face[1] - 250) / 19.2):.1f}%,rgba(13,15,22,{d0:.2f}) 0%,rgba(13,15,22,{d1:.2f}) 100%)}}
#wall{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:3;transform-origin:0 0}}
.lay{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:{face[0]}px {face[1] - 60}px}}
#Lfar{{filter:blur(1.7px) brightness(.7) saturate(.9)}}
#Lmid{{filter:brightness(.9)}}
#fgwrap{{position:absolute;inset:0;z-index:5;filter:drop-shadow(0px 22px 46px rgba(0,0,0,0))}}
#vig{{position:absolute;inset:0;z-index:6;pointer-events:none;
  background:radial-gradient(120% 85% at 50% 38%,rgba(0,0,0,0) 58%,rgba(0,0,0,.30) 100%)}}
{C.css(ACCENT)}'''
    nl = '\n'
    # GRADE=0: the main reel grades everything once, so the effect's own vignette is left out (the room dim stays:
    # it is part of the effect, not a grade)
    vig = '' if os.environ.get('GRADE') == '0' else '<div id="vig"></div>'
    voice = (f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''
    page = f'''<!doctype html>
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
  {voice}
{nl.join(audio(dur))}
  <div id="stage"><div id="bump">
    <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
    <div id="dim"></div>
    <div id="wall">
      <div id="Lfar" class="lay">{nl.join(html['far'])}</div>
      <div id="Lmid" class="lay">{nl.join(html['mid'])}</div>
      <div id="Lnear" class="lay">{nl.join(html['near'])}</div>
    </div>
    <div id="fgwrap"><video id="fg" class="full" src="{cutout}" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div>
    {vig}
  </div></div>
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{cam_js}
{nl.join(tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    name = os.path.basename(HERE)
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  cards {len(cards)}  camera {"tracked" if mats else "still"}  cutout {cutout}')
    for c in sorted(cards, key=lambda c: c['t']):
        print(f"  f{c['t'] * 30:5.1f} {'HERO' if c['hero'] else '    '} {c['layer']:4s} {c['kind']:8s} {' / '.join(c['lines'])}")
    for w in lay.get('warnings', []):
        print('WARNING (layout):', w)
    print(f'render to renders/{name}.mp4')


if __name__ == '__main__':
    main()
