#!/usr/bin/env python3
"""COUCH WALL: the wall behind the speaker turns into a grid of their own reel covers. The columns flick up from
behind the speaker (and behind the sofa, chair or floor if there is one), keep scrolling like a feed, then sink back and the
real room returns.

  F_IN      the grid has landed on this frame (a spoken word); the columns start rising 8 frames earlier
  hold      the grid scrolls slowly upward the whole time
  F_OUT     the real room is fully back on this frame (None = the grid stays to the end of the slot)

Layers: a-roll < GRID < fg.webm (the speaker + furniture + floor, baked by prep.py) < caption words.
The covers are YOURS: put the images in the COVERS folder. The effect ships none and prints no numbers unless you
type real ones into COUNTS.

Run order (from the slot folder, see effect.md):
  python onsets.py      word onsets as frames  -> fill the CLIP block
  python prep.py        covers + track + wall matte + fg.webm; look at work/wall.jpg
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
                     # least 4, 9 or more looks best. Shown in file-name order, repeated if the wall needs more.
COUNTS = {}          # OPTIONAL, real numbers only: {'cover-file.jpg': 15371, 'other.jpg': '1.07M'}. A number is
                     # shortened like a profile grid does (15.3K); a string is shown as written. Empty = no numbers
                     # and no play icons on any tile. Read them off your own insights; never estimate.
TOP_BY_COUNT = True  # with COUNTS: the best-performing covers take the top row. False = plain file-name order
F_IN = 32            # frame of the word the grid lands on (from `python onsets.py`)
F_OUT = 113          # frame of the word where the real room is back. None = the grid stays to the last frame.
                     # Needs F_OUT - F_IN >= 45 (1.5 s to read the grid) and F_OUT <= frames - 2
CAPS = []            # the effect's own caption words, in front of everything. A list of groups:
                     #   (first frame, last frame or None, [(frame, 'words', 'sm' | 'big'), ...])
                     # e.g. [(18, 57, [(18, 'all of', 'sm'), (32, 'these', 'big')])]. Each entry is one line and pops
                     # in on its frame. [] = none (the main reel captions the line). Only words the speaker really says.
CAP_Y = None         # px: top of the caption block. None = measured (below the speaker's chin, around the chest, above 1470).
                     # prep.py draws the block in yellow on work/wall.jpg: move it if it sits on the speaker's face or hands
WALL = None          # (x0, y0, x1, y1) px: the grid is only allowed inside this rectangle. None = the whole frame.
                     # Use it to stop the grid above a desk or beside a window when 'auto' gets it wrong
FURNITURE = 'auto'   # 'auto' = sofa / chair / floor in front of the wall are found by colour and stay in front.
                     # 'off' = nothing but the speaker is in front: then give a WALL rectangle that ends above them
IN_FRONT = []        # extra shapes that must stay in front of the grid: [[(x, y), (x, y), ...], ...] in px on the
                     # reference frame (work/wall.jpg, left half, is that frame at half size). For furniture that
                     # is the same colour as the wall (a white pillow on a white wall)
BEHIND = []          # shapes the grid must cover even though 'auto' kept them in front (same format)
WALL_TOL = 1.0       # how far from the wall colour still counts as wall. Raise to 1.3 if bare wall is left
                     # uncovered (shadows, a lamp glow), lower to 0.7 if the grid leaks onto furniture
EDGE_CHOKE = 1       # px the furniture edge is pulled in, so no light rim of wall glows over the dark tiles
COLS = 3             # tiles across. 3 looks like a profile grid; 4 on a very wide wall
SCROLL = 190         # px per second the grid drifts upward while it is on the wall (0 = it stands still)
CROP_Y = 0.42        # which part of a tall 9:16 cover survives the 3:4 crop: 0 = top, 0.5 = middle, 1 = bottom
LOOK = (.80, .95, .86)   # tile brightness, contrast, saturation: dimmed so the grid sits in the room, not on top
SHADOW = .45         # strength of the soft shadow the speaker and furniture throw on the grid (0 = none)
VOICE = True         # False = silent slot (no a-roll audio in the render; also run with SFX=0)
TRACK_YMAX = None    # px: only wall above this line is used for the camera track. None = 1100. Lower it to just
                     # above the furniture if the grid slides against the room on a moving camera
REF = None           # reference frame the wall is measured on. None = the middle frame of the slot
# (sound, frame, base volume). Base volumes are the template's; everything is played at 0.75x.
SOUNDS = [('whoosh-short', F_IN - 9, .25)] + \
         ([('whoosh-short', F_OUT - 13, .16), ('pop', F_OUT, .18)] if F_OUT is not None else [])
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1080, 1920
GAP = 3              # px between tiles
GRID_TOP = -70       # the first row starts a little above the frame, like a feed caught mid-scroll
LEAD = 8             # frames the columns start before F_IN (expo.out: first column 90% up on the word, last one 80%)
IN_DUR, IN_STAG = .80, .04
OUT_DUR, OUT_STAG = .34, .05
SFX_GAIN = 0.75
CAP_LINE = {'sm': (76, 72), 'big': (178, 164)}       # class -> (font px, line pitch px)
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
PLAY = ('<svg class="pi" viewBox="0 0 24 24" width="25" height="25"><path d="M7.2 4.6c-.9-.55-2 .1-2 1.15v12.5c0 1.05 1.1 1.7 2 '
        '1.15l10.3-6.25c.86-.52.86-1.78 0-2.3z" fill="none" stroke="#fff" stroke-width="2.3" stroke-linejoin="round"/></svg>')


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


def tile_size():
    tw = (W - (COLS - 1) * GAP) // COLS
    return tw, round(tw * 4 / 3)


def caption_height():
    """height of the tallest caption group, for the measured placement"""
    return max([sum(CAP_LINE[c][1] for _, _, c in words) for _, _, words in CAPS] or [CAP_LINE['sm'][1] + CAP_LINE['big'][1]])


def grid_order(tiles, need):
    """file-name order (best counts first if asked), cycled until the wall is full"""
    order = list(tiles)
    if TOP_BY_COUNT and any(t.get('plays') for t in tiles):
        top = sorted([t for t in tiles if t.get('plays')], key=lambda t: -t['plays'])[:COLS]
        order = top + [t for t in tiles if t not in top]
    return [order[i % len(order)] for i in range(need)]


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
        k = min(max(1 - (speed[n] - .3) / .7, 0), 1)
        h11, h12, h13, h21, h22, h23, h31, h32, h33 = [a * (1 - k) + b * k for a, b in zip(fast[n], slow[n])]
        mats.append(f'matrix3d({h11:.6f},{h21:.6f},0,{h31:.9f},{h12:.6f},{h22:.6f},0,{h32:.9f},0,0,1,0,{h13:.3f},{h23:.3f},0,{h33:.6f})')
    return mats


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
    if os.environ.get('CAPTIONS') == '0':
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
                      f"duration:.2,ease:'power3.out',immediateRender:false}},{max(a, F(frame) - .1):.3f});")   # ~90% sharp ON the word
            if b < dur - .01:
                tw.append(f"tl.to('#{wid}',{{autoAlpha:0,scale:.96,filter:'blur(14px)',duration:.14,ease:'power2.in'}},{b - .14:.3f});")
                tw.append(f"tl.set('#{wid}',{{autoAlpha:0}},{b:.3f});")
    return html, tw


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the length UP to whole frames
    for need in ('work/prep.json', 'work/tiles.json', 'assets/fg.webm'):
        if not os.path.exists(need):
            sys.exit(f'{need} is missing: run prep.py first (see effect.md)')
    prep = json.load(open('work/prep.json'))
    if prep['frames'] != nfr:
        sys.exit('work/prep.json belongs to another clip: run prep.py --force')
    tiles = json.load(open('work/tiles.json'))
    track = json.load(open('work/track.json')) if os.path.exists('work/track.json') else None
    out_len = OUT_DUR + OUT_STAG * (COLS - 1)
    if F_IN - LEAD < 0:
        sys.exit(f'F_IN {F_IN} is too early: the columns need {LEAD} frames to rise before the word')
    if F_OUT is not None and (F_OUT > nfr - 2 or F_OUT - F_IN < 45):
        sys.exit(f'F_OUT {F_OUT}: needs F_IN + 45 <= F_OUT <= frames - 2 (frames = {nfr})')
    if F_OUT is None and nfr - F_IN < 45:
        print(f'WARNING: only {nfr - F_IN} frames after the grid lands; 45 (1.5 s) or more reads better')
    in_t = F(F_IN - LEAD)
    out_end = F(F_OUT) if F_OUT is not None else None
    out_t = out_end - out_len if F_OUT is not None else None
    tw_px, th_px = tile_size()
    pitch = th_px + GAP
    hold = (out_end if F_OUT is not None else dur) - in_t
    scroll = SCROLL * hold
    mats = camera(track, nfr)
    over = 1.0
    if mats:                    # moving camera: the grid is glued to the wall, so it is drawn a little larger
        over = 1 + 2 * (float(track.get('max_shift_px', 0)) + 6) / W
    rows = math.ceil((H * over + 120 - GRID_TOP + scroll) / pitch) + 1
    seq = grid_order(tiles, COLS * rows)
    # the columns wait just below the lowest visible bit of wall (hidden behind furniture / floor), so the rise is
    # short and the grid is up ON the word; they sink back to the same place, plus what the grid has scrolled by then
    shift = float(track.get('max_shift_px', 0)) if mats else 0
    rise = int(min(H * over + 140, prep.get('grid_bottom', H) - GRID_TOP + 70 + shift))
    sink = rise + int(scroll) + 50

    cols, used = [], {}
    for c in range(COLS):
        cells = []
        for r in range(rows):
            t = seq[r * COLS + c]
            cnt = f'<div class="cnt">{PLAY}<span>{t["label"]}</span></div>' if t.get('label') else ''
            # a cover that repeats gets its own copy of the file: the renderer warns on two <img> with one source
            k = used[t['file']] = used.get(t['file'], -1) + 1
            src = f'assets/tiles/{t["file"]}'
            if k:
                src = f'assets/tiles/{os.path.splitext(t["file"])[0]}_r{k}.jpg'
                shutil.copyfile(f'assets/tiles/{t["file"]}', src)
            cells.append(f'<div class="tile"><img src="{src}" alt="" />{cnt}</div>')
        cols.append(f'<div id="col{c}" class="col" style="left:{c * (tw_px + GAP)}px">{"".join(cells)}</div>')

    sh = f'drop-shadow(0px -6px 24px rgba(0,0,0,{SHADOW}))'
    sh0 = 'drop-shadow(0px -6px 24px rgba(0,0,0,0))'
    tw = ["gsap.set('#gridwrap',{autoAlpha:0});", "gsap.set('#fgwrap',{autoAlpha:0});", "gsap.set('#gfx',{autoAlpha:0});",
          f"gsap.set('#scroll',{{y:{GRID_TOP}}});",
          f"tl.set('#gridwrap',{{autoAlpha:1}},{in_t:.3f});",
          # the foreground layer only exists while the grid is up: before and after, the frame is the untouched a-roll
          f"tl.set('#fgwrap',{{autoAlpha:1}},{max(0.0, in_t - .034):.3f});",
          f"tl.to('#gfx',{{autoAlpha:1,duration:.35,ease:'power1.out'}},{in_t + .4:.3f});",
          f"tl.to('#fgwrap',{{filter:'{sh}',duration:.3,ease:'power1.inOut'}},{in_t + .3:.3f});",
          # one continuous upward drift from the reveal on (linear, like a feed being scrolled)
          f"tl.fromTo('#scroll',{{y:{GRID_TOP}}},{{y:{GRID_TOP - scroll:.1f},duration:{hold:.3f},ease:'none',immediateRender:false}},{in_t:.3f});",
          f"tl.fromTo('#gridin',{{filter:'blur(9px)'}},{{filter:'blur(0px)',duration:.5,ease:'power2.out',immediateRender:false}},{in_t:.3f});",
          f"tl.set('#gridin',{{filter:'none'}},{in_t + .52:.3f});"]
    if F_OUT is not None:
        tw += [f"tl.to('#gfx',{{autoAlpha:0,duration:.14,ease:'power1.in'}},{out_t - .04:.3f});",
               f"tl.to('#fgwrap',{{filter:'{sh0}',duration:.14,ease:'power1.in'}},{out_t - .04:.3f});",
               f"tl.fromTo('#gridin',{{filter:'blur(0px)'}},{{filter:'blur(8px)',duration:{OUT_DUR + .1:.2f},ease:'power2.in',immediateRender:false}},{out_t + .04:.3f});",
               f"tl.set('#gridwrap',{{autoAlpha:0}},{out_end:.3f});",
               f"tl.set('#fgwrap',{{autoAlpha:0}},{out_end + .034:.3f});"]
    for c in range(COLS):
        tw.append(f"gsap.set('#col{c}',{{y:{rise}}});")
        tw.append(f"tl.fromTo('#col{c}',{{y:{rise}}},{{y:0,duration:{IN_DUR},ease:'expo.out',immediateRender:false}},{in_t + c * IN_STAG:.3f});")
        if F_OUT is not None:       # out: reverse order, back down behind the furniture
            tw.append(f"tl.to('#col{c}',{{y:{sink},duration:{OUT_DUR},ease:'power3.in'}},{out_t + (COLS - 1 - c) * OUT_STAG:.3f});")
    cap_y = int(CAP_Y) if CAP_Y is not None else int(prep['cap_y_auto'])
    c_html, c_tw = captions(cap_y, dur, nfr)
    tw += c_tw

    cam_js = ''
    if mats:
        # function-based property: GSAP calls cam.frame(v) on every render (seek-safe, no callbacks involved)
        cam_js = (f"const MATS = {json.dumps(mats)};\n"
                  "const camEl = document.getElementById('gridcam');\n"
                  "const cam = { f: 0, frame(v) { if (v === undefined) return this.f; this.f = v;\n"
                  "  const n = Math.max(0, Math.min(MATS.length - 1, Math.round(v))); camEl.style.transform = MATS[n]; } };\n"
                  "cam.frame(0);\n"
                  f"tl.to(cam, {{ frame: {nfr - 1}, duration: {(nfr - 1) / FPS:.5f}, ease: 'none' }}, 0);")
    b_, c_, s_ = LOOK
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#000}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#000}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#bgv{{z-index:0}}
#gridwrap{{position:absolute;inset:0;z-index:2}}
#gridcam{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;transform-origin:0 0}}
#gridin{{position:absolute;inset:0;transform:scale({over:.4f});transform-origin:50% 50%}}
#scroll{{position:absolute;left:0;top:0;width:{W}px}}
.col{{position:absolute;top:0;width:{tw_px + GAP}px;padding-right:{GAP}px;background:#0b0b0b}}
.tile{{position:relative;width:{tw_px}px;height:{th_px}px;border-bottom:{GAP}px solid #0b0b0b;box-sizing:content-box;overflow:hidden;background:#222}}
.tile img{{display:block;width:{tw_px}px;height:{th_px}px;filter:brightness({b_}) contrast({c_}) saturate({s_})}}
.cnt{{position:absolute;left:14px;bottom:12px;display:flex;align-items:center;gap:7px;color:#fff;font:600 27px Inter;
  letter-spacing:-.2px;text-shadow:0 1px 4px rgba(0,0,0,.65),0 0 14px rgba(0,0,0,.35)}}
.cnt .pi{{filter:drop-shadow(0 1px 3px rgba(0,0,0,.6))}}
/* room-matching light: a warm wash and a falloff so the grid sits in the room instead of glowing in front of it */
#gfx{{position:absolute;inset:-60px}}
#gtone{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,214,170,.10),rgba(120,80,40,.10));mix-blend-mode:soft-light}}
#gvig{{position:absolute;inset:0;background:radial-gradient(90% 60% at 52% 38%,rgba(0,0,0,0) 45%,rgba(16,10,6,.42) 100%)}}
#fgwrap{{position:absolute;inset:0;z-index:4;filter:{sh0}}}
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
  <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
  <div id="gridwrap"><div id="gridcam"><div id="gridin"><div id="scroll">
{nl.join(cols)}
  </div><div id="gfx"><div id="gtone"></div><div id="gvig"></div></div></div></div></div>
  <div id="fgwrap"><video id="fg" class="full" src="assets/fg.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div>
{nl.join(c_html)}
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
    shown = sum(1 for t in seq if t.get('label'))
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  grid {COLS}x{rows} from {len(tiles)} covers'
          f'{"" if len(tiles) >= 9 else " (few covers: they repeat)"}  counts on {shown} tiles  '
          f'camera {"tracked" if mats else "still"}  in f{F_IN - LEAD}->{F_IN}  out {"none" if F_OUT is None else f"f{F_OUT}"}  captions at y {cap_y}')
    print(f'render to renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    main()
