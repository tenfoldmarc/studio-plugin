#!/usr/bin/env python3
"""ORBIT: the speaker's own reel covers circle around them in a ring. On the far side the cards pass BEHIND the
speaker (hidden by the cutout), on the near side they pass IN FRONT, at chest height, under the face.

  F_IN      the first cards are up on this frame (a spoken word); they start popping 4 frames earlier
  hold      the ring turns the whole time and follows the speaker if the shot drifts
  F_OUT     the plain picture is back on this frame (None = the ring stays to the end of the slot)

Layers: a-roll < far cards < the speaker's cutout (assets/subject.webm) < near cards < caption words.
The covers are YOURS: put the images in the COVERS folder. The effect ships none and prints no numbers unless you
type real ones into COUNTS. The ring's centre, size and height are MEASURED from the cutout by prep.py.

Run order (from the slot folder, see effect.md):
  python onsets.py      word onsets as frames  -> fill the CLIP block
  python prep.py        covers + ring measured from the cutout; look at work/ring.jpg
  python3 build.py      writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no caption words, SFX=0 no sounds)
"""
import json
import math
import os
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
COVERS = 'covers'    # folder (inside the slot, or an absolute path) holding YOUR reel covers: jpg / png / webp, at
                     # least 4. The first CARDS of them (file-name order) go on the ring.
COUNTS = {}          # OPTIONAL, real numbers only: {'cover-file.jpg': 15371, 'other.jpg': '1.07M'}. A number is
                     # shortened like a profile grid does (15.3K); a string is shown as written. Empty = no numbers
                     # and no play icons on any card. Read them off your own insights; never estimate.
CARDS = 6            # how many cards ride the ring (4 to 8). Fewer covers than this = one card per cover
F_IN = 30            # frame of the word the ring lands on (from `python onsets.py`). 5 or later
F_OUT = 120          # frame where the plain picture is back, every card gone. None = the ring stays to the last
                     # frame (only when the reel cuts away there). Needs F_OUT - F_IN >= 45 and F_OUT <= frames - 2
CAPS = []            # the effect's own caption words, in front of everything. A list of groups:
                     #   (first frame, last frame or None, [(frame, 'words', 'sm' | 'big'), ...])
                     # e.g. [(24, 70, [(24, 'all of', 'sm'), (30, 'these', 'big')])]. Each entry is one line and pops
                     # in on its frame. [] = none (the main reel captions the line). Only words that are spoken.
CAP_Y = None         # px: top of the caption block. None = measured (under the ring if it fits above y 1470, else
                     # above the head). prep.py draws the block in yellow on work/ring.jpg
CX = None            # px: ring centre x. None = measured (the middle of the speaker's chest)
CY = None            # px: ring centre y. None = measured: the highest ring whose near cards stay under the chin
RX = None            # px: half the ring's width. None = measured (just wider than the body, inside the safe zone)
TILT = .33           # ring height / ring width. Smaller = flatter ring, seen more from the side
CARD_W = 190         # px: width of a card at the front of the ring (9:16, so 338 tall). prep shrinks it by itself
                     # when the ring would not fit between chin and y 1470; it never makes it bigger
NEAR, FAR = 1.0, .6  # card size at the very front and at the very back of the ring (times CARD_W)
FACE_GAP = 30        # px kept clear between a near card and the face box (red on work/ring.jpg)
REV = 5.2            # seconds for one full turn
DIR = 1              # 1 = near cards travel right to left, -1 = left to right
PHASE = .35          # radians: where the first card starts on the ring (turn it if a card starts on a hand)
FOLLOW = True        # the ring follows the head when the speaker or the camera drifts more than 10 px
CROP_Y = .5          # which part of a cover survives when it is not 9:16: 0 = top / left, 0.5 = middle, 1 = bottom
FAR_DIM = .75        # brightness of the far cards (a depth cue). 1 = same as the near ones
GRADE = None         # None = off. (brightness, contrast, saturation), e.g. (1.03, .95, .9): a look on the whole
                     # picture that fades in with the ring and is gone again before F_OUT
VOICE = True         # False = silent slot (no a-roll audio in the render; also run with SFX=0)
REF = None           # frame drawn on work/ring.jpg. None = the middle of the ring's time on screen
# (sound, frame, base volume). Stock template sounds only; base volumes are the template's, played at 0.75x.
SOUNDS = [('whoosh-short', F_IN - 6, .25), ('pop', F_IN, .16)] + \
         ([('whoosh-short', F_OUT - 9, .16)] if F_OUT is not None else [])
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1080, 1920
LEAD = 4             # frames the first card starts before F_IN (four cards showing on the word)
STEP = 2             # frames between position keys
POP_DUR, POP_STAG = .42, .04
OUT_DUR, OUT_STAG = .2, .012
SFX_GAIN = 0.75
SAFE = dict(top=220, bottom=1470, side=35, right=100, right_from=1155)
CAP_LINE = {'sm': (64, 64), 'big': (132, 122)}       # class -> (font px, line pitch px)
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
PLAY = ('<svg class="pi" viewBox="0 0 24 24" width="19" height="19"><path d="M7.2 4.6c-.9-.55-2 .1-2 1.15v12.5c0 1.05 1.1 1.7 2 '
        '1.15l10.3-6.25c.86-.52.86-1.78 0-2.3z" fill="none" stroke="#fff" stroke-width="2.3" stroke-linejoin="round"/></svg>')


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


def span(nfr):
    """(first frame a card can show, frame the picture is plain again or the last frame)"""
    if F_IN - LEAD < 1:
        sys.exit(f'F_IN {F_IN} is too early: frame 0 must stay plain and the cards pop {LEAD} frames before the word')
    if F_OUT is not None and (F_OUT > nfr - 2 or F_OUT - F_IN < 45):
        sys.exit(f'F_OUT {F_OUT}: needs F_IN + 45 <= F_OUT <= frames - 2 (this slot has {nfr} frames, F_IN is {F_IN})')
    if F_OUT is None and nfr - F_IN < 45:
        sys.exit(f'only {nfr - F_IN} frames after F_IN: the ring needs 45 (1.5 s) or more')
    return F_IN - LEAD, (F_OUT if F_OUT is not None else nfr - 1)


def caption_height():
    return max([sum(CAP_LINE[c][1] for _, _, c in words) for _, _, words in CAPS] or [0])


def ring_pos(ring, i, n, f, f0):
    """card i of n on frame f: (centre x, centre y, scale, depth) with depth > 0 = in front of the speaker"""
    th = DIR * 2 * math.pi * ((f - f0) / FPS / REV) + i * 2 * math.pi / n + PHASE
    s = math.sin(th)
    k = min(max(f, 0), len(ring['dx']) - 1)
    return (ring['cx'] + ring['dx'][k] + ring['rx'] * math.cos(th), ring['cy'] + ring['dy'][k] + ring['ry'] * s,
            FAR + (NEAR - FAR) * (s + 1) / 2, s)


def probe(path, entries):
    ffp = shutil.which('ffprobe') or 'ffprobe'
    return subprocess.run([ffp, '-v', 'error', '-show_entries', entries, '-of', 'csv=p=0', path],
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
        t = F(max(0, frame))
        if t >= dur - .05:
            continue
        d = min(float(probe(path, 'format=duration')), dur - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def captions(cap_y, dur, nfr):
    html, tw = [], []
    if os.environ.get('CAPTIONS') == '0' or not CAPS:
        if os.environ.get('CAPTIONS') == '0' and cap_y is not None:
            # in a reel the buyer's own captions stay on: tell where they have room (the near cards pass at chest height)
            print(f"reel captions: this effect's own words are off. The room it leaves for the reel's captions starts at "
                  f"y {cap_y}: add the slot with fx_add.py --caption-y {max(236, min(1376, int(cap_y)))}, then check one reel "
                  'snapshot inside the slot')
        return html, tw
    if cap_y is None:
        print('WARNING: no room for the caption block inside the safe zone: captions left out (set CAP_Y to force)')
        return html, tw
    for g, (fa, fb, words) in enumerate(CAPS):
        a = F(fa)
        b = dur if fb is None or fb >= nfr - 1 else F(fb)
        top = cap_y
        for k, (frame, txt, cls) in enumerate(words):
            wid = f'c{g}-{k}'
            html.append(f'<div id="{wid}" class="cap {cls}" style="top:{top}px">{txt}</div>')
            top += CAP_LINE[cls][1]
            tw.append(f"gsap.set('#{wid}',{{autoAlpha:0}});")
            tw.append(f"tl.fromTo('#{wid}',{{autoAlpha:0,scale:1.22,filter:'blur(18px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',"
                      f"duration:.2,ease:'power3.out',immediateRender:false}},{max(a, F(frame) - .1):.3f});")
            if b < dur - .01:
                tw.append(f"tl.to('#{wid}',{{autoAlpha:0,scale:.96,filter:'blur(14px)',duration:.14,ease:'power2.in'}},{b - .14:.3f});")
                tw.append(f"tl.set('#{wid}',{{autoAlpha:0}},{b:.3f});")
    return html, tw


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the length UP to whole frames
    for need in ('work/ring.json', 'work/tiles.json'):
        if not os.path.exists(need):
            sys.exit(f'{need} is missing: run prep.py first (see effect.md)')
    ring = json.load(open('work/ring.json'))
    tiles = json.load(open('work/tiles.json'))
    n = len(tiles)
    if ring['frames'] != nfr or ring['span'] != list(span(nfr)) or ring['cards'] != n:
        sys.exit('work/ring.json was measured for other frames or cards: run prep.py again')
    f0, f1 = span(nfr)
    in_t = F(f0)
    out_end = F(F_OUT) if F_OUT is not None else dur
    tw_px, th_px = ring['tw'], ring['th']

    html = []
    tw = ["gsap.set('#cutwrap',{autoAlpha:0});",
          # the cutout layer only exists while the ring is up: before and after, the frame is the untouched a-roll
          f"tl.set('#cutwrap',{{autoAlpha:1}},{max(0.0, in_t - .034):.3f});"]
    if F_OUT is not None:
        tw.append(f"tl.set('#cutwrap',{{autoAlpha:0}},{out_end + .034:.3f});")
    keys = list(range(f0, f1 + 1, STEP))
    if keys[-1] != f1:
        keys.append(f1)
    for i, t in enumerate(tiles):
        cnt = f'<div class="cnt">{PLAY}<span>{t["label"]}</span></div>' if t.get('label') else ''
        pts = [ring_pos(ring, i, n, f, f0) for f in keys]
        for side in ('b', 'f'):
            sel = f'#{side}{i}'
            # two <img> may not share one file (the renderer warns), so prep wrote a copy per side
            html.append(f'<div id="{side}{i}" class="orb {side}"><div class="pop"><div class="tile">'
                        f'<img src="assets/tiles/{t["file"]}_{side}.jpg" alt="" />{cnt}</div></div></div>')
            vis = (lambda s: 1 if s > 0 else 0) if side == 'f' else (lambda s: 0 if s > 0 else 1)
            x0, y0, sc0, s0 = pts[0]
            tw.append(f"gsap.set('{sel}',{{xPercent:-50,yPercent:-50,x:{x0:.1f},y:{y0:.1f},scale:{sc0:.3f},autoAlpha:0}});")
            tw.append(f"tl.set('{sel}',{{autoAlpha:{vis(s0)}}},{in_t:.3f});")
            kf = ','.join(f"{{x:{x:.1f},y:{y:.1f},scale:{sc:.3f},autoAlpha:{vis(s)},duration:{(fb - fa) / FPS:.4f},ease:'none'}}"
                          for (x, y, sc, s), fa, fb in zip(pts[1:], keys, keys[1:]))
            tw.append(f"tl.to('{sel}',{{keyframes:[{kf}]}},{in_t:.3f});")
            tw.append(f"gsap.set('{sel} .pop',{{scale:0}});")
            tw.append(f"tl.to('{sel} .pop',{{scale:1,duration:{POP_DUR},ease:'back.out(1.8)'}},{in_t + i * POP_STAG:.3f});")
            if F_OUT is not None:
                o = out_end - OUT_DUR - (n - 1 - i) * OUT_STAG
                tw.append(f"tl.to('{sel} .pop',{{scale:0,duration:{OUT_DUR},ease:'power2.in'}},{o:.3f});")
                tw.append(f"tl.set('{sel}',{{autoAlpha:0}},{out_end:.3f});")
    if GRADE:
        g = 'brightness({}) contrast({}) saturate({})'
        g0, g1 = g.format(1, 1, 1), g.format(*GRADE)
        tw += [f"tl.set('#stage',{{filter:'{g0}'}},{in_t:.3f});",
               f"tl.to('#stage',{{filter:'{g1}',duration:.3,ease:'power1.inOut'}},{in_t:.3f});"]
        if F_OUT is not None:
            tw += [f"tl.to('#stage',{{filter:'{g0}',duration:.3,ease:'power1.inOut'}},{out_end - .32:.3f});",
                   f"tl.set('#stage',{{filter:'none'}},{out_end:.3f});"]
    cap_y = int(CAP_Y) if CAP_Y is not None else ring.get('cap_y')
    c_html, c_tw = captions(cap_y, dur, nfr)
    tw += c_tw

    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#000}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:0}}
#cutwrap{{position:absolute;inset:0;z-index:4}}
.orb{{position:absolute;left:0;top:0;width:{tw_px}px;height:{th_px}px}}
.orb.b{{z-index:3;filter:brightness({FAR_DIM})}}
.orb.f{{z-index:6}}
.pop{{width:100%;height:100%}}
.tile{{position:relative;width:100%;height:100%;border-radius:{round(tw_px * .147)}px;overflow:hidden;background:#111;
  border:{max(3, round(tw_px * .026))}px solid rgba(255,248,239,.92);box-shadow:0 26px 60px rgba(0,0,0,.45),0 6px 16px rgba(0,0,0,.25)}}
.tile img{{display:block;width:100%;height:100%;object-fit:cover}}
.cnt{{position:absolute;left:10px;bottom:9px;display:flex;align-items:center;gap:5px;color:#fff;font:600 {max(15, round(tw_px * .11))}px Inter;
  letter-spacing:-.2px;text-shadow:0 1px 4px rgba(0,0,0,.7),0 0 12px rgba(0,0,0,.4)}}
.cnt .pi{{filter:drop-shadow(0 1px 3px rgba(0,0,0,.6))}}
.cap{{position:absolute;left:0;right:0;z-index:8;text-align:center;color:#fff;font-family:'Inter Tight';font-weight:900;
  letter-spacing:-.05em;line-height:.9;white-space:nowrap;transform-origin:50% 60%;
  text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35)}}
.cap.sm{{font-size:{CAP_LINE['sm'][0]}px;font-weight:800;letter-spacing:-.04em}}
.cap.big{{font-size:{CAP_LINE['big'][0]}px}}
'''
    nl = '\n'
    voice = (f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="{W}" data-height="{H}">
  {voice}
{nl.join(audio(dur))}
  <div id="stage">
  <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
  <div id="cutwrap"><video id="cut" class="full" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div>
{nl.join(html)}
  </div>
{nl.join(c_html)}
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
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
    open('index.html', 'w').write(page)
    shown = sum(1 for t in tiles if t.get('label'))
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  {n} cards {tw_px}x{th_px}  counts on {shown}  ring centre '
          f'({ring["cx"]:.0f}, {ring["cy"]:.0f}) radius {ring["rx"]:.0f} x {ring["ry"]:.0f}  '
          f'{"follows the speaker" if ring["follows"] else "fixed"}  in f{f0}->{F_IN}  '
          f'out {"none" if F_OUT is None else f"f{F_OUT}"}  captions {"none" if not c_html else f"at y {cap_y}"}')
    for wmsg in ring.get('warnings', []):
        print('WARNING: ' + wmsg)
    print(f'render to renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    main()
