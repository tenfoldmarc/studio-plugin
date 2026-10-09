#!/usr/bin/env python3
"""type-wall: the room behind the speaker becomes a wall of giant moving words (Inter Tight 900).

Rows of one repeated word march sideways in alternating directions, solid and outlined rows taking turns. Every row
hard-swaps to the next word on the frame the speaker says it, and the row right above their head says every word as the speaker says it.
On the word that matters the whole wall snaps to it, punches in, and the row over their head turns yellow.
The speaker stays in front of the wall the whole time (assets/subject.webm, the cutout).

Run from the slot folder, after prep.py (see effect.md for the full run order):
    python3 build.py           writes index.html
    SAFE=1 python3 build.py    also draws the safe zone, the head-top line and the KEEP shapes, for snapshot checks
    SFX=0 python3 build.py     no sounds (the main video has its own)
    CAPTIONS=0                 changes nothing here: the wall is the caption, so tell the main video to skip its own
"""
import json
import math
import os
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
# PHRASES: what the wall says, in the order the speaker says it. 1 to 3 words per phrase, UPPER CASE.
#   (frame, 'WORD') = the frame that word starts on. Get it from `python3 onsets.py` (column "swap").
#   The first word of the first phrase rides in with the wall at IN_FRAME, whatever its own frame says.
#   A 2 or 3 word phrase builds down the wall: every row says word 1, then every 2nd (or 3rd) row turns to word 2...
#   'hit': True marks the word that matters: all rows snap to it, the wall punches, the row over the speaker's head turns yellow.
#   Skip the small words. Split a word that is wider than the frame (EVERY / BODY'S); build.py tells you which.
PHRASES = [
    {'words': [(3, 'EVERY'), (11, 'BODY’S'), (21, 'TALKING')]},
    {'words': [(42, 'CLAUDE')], 'hit': True},
    {'words': [(56, 'EDIT'), (65, 'YOUR'), (71, 'VIDEOS')]},
]
IN_FRAME = 0        # frame the wall arrives (hard cut from the room, rows whip in). 0 = it is up from the first frame. Normally the frame of the first wall word
OUT_FRAME = None    # frame the wall is gone and the room is back. None = it stays up to the end of the slot
KEEP = []           # real picture kept in front of the wall (the sofa or desk the speaker sits at). Still camera only. A list of shapes that do not overlap, each a list of (x, y) px read off work/measure.jpg. [] = the wall fills the whole frame
FS = 205            # letter size in px. 205 suits a shot with clear wall above the speaker's head; go down (150 to 180) when prep.py says there is no room above the speaker or build.py says a word is wider than the frame
ACCENT_Y = None     # y px where the letters of the yellow row end. None = measured: just above the highest point the speaker's head reaches
HEAD_GAP = 14       # px between the yellow row and the top of the speaker's head (only used when ACCENT_Y is None)
XC = {}             # {row number: x px} to move the spot where a row's word is centred when it swaps. {} = measured: the widest gap the speaker leaves in that row. Row numbers are printed by build.py
GROUND = ('#22261A', '#14160F', '#0B0C09')    # wall colours: glow behind the speaker's head, middle, corners. Keep it dark and quiet so the letters carry
INK = '#EEEADF'     # letter colour (outlined rows use the same colour at 60%)
ACCENT = '#FAE67A'  # colour of the row over the speaker's head from the hit word on (from the start when no phrase has 'hit')
VOL_IN, VOL_HIT, VOL_SWAP = .28, .08, .16     # sound levels: whoosh as the wall arrives, low hit on the hit word, soft whoosh on each new phrase. 0 = that sound off
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SLOT = os.path.basename(HERE)
FP = shutil.which('ffprobe') or 'ffprobe'
W, H = 1080, 1920
if not os.path.exists('work/measure.json'):
    sys.exit('work/measure.json is missing: run prep.py first (see effect.md).')
N = json.load(open('clip.json'))['frames']
DUR = N / 30
DUR_S = f'{DUR - .001:.3f}'          # 1 ms short, so the render is exactly N frames
MS = json.load(open('work/measure.json'))
MET = json.load(open('assets_fx/widths.json'))
notes = list(MS.get('warnings', []))

LS = -0.025                          # tracking (em)
PITCH = round(FS * 172 / 205)        # row height
GAP = .42 * FS                       # space between the repeated words
KICK = 150                           # px a row lurches in its own direction on every swap
SPEEDS = [150, 205, 170, 230, 160, 215, 180, 200, 165]      # px per second, row by row
ENTRY_D = .55
SFX_GAIN = .75

# ---- check the CLIP block before building anything
last = -1
for ph in PHRASES:
    if not 1 <= len(ph['words']) <= 3:
        sys.exit(f'a phrase needs 1 to 3 words, this one has {len(ph["words"])}: {ph["words"]}')
    for f, w in ph['words']:
        if w != w.upper():
            sys.exit(f'"{w}": wall words are UPPER CASE')
        if chr(8212) in w or chr(8211) in w:
            sys.exit(f'"{w}": no long dashes on screen')
        if w.strip('.,!?’\'"') in ('FR' + 'EE', 'COUR' + 'SE'):
            sys.exit(f'"{w}" is on the never-on-screen list')
        bad = [c for c in w if c not in MET['w']]
        if bad:
            sys.exit(f'"{w}": no width on file for {bad}. Use letters, digits and simple punctuation.')
        if f <= last and last >= 0:
            sys.exit(f'word frames must go up: "{w}" at {f} comes after a word at {last}')
        if f >= N:
            sys.exit(f'"{w}" at frame {f} is past the end of the slot ({N} frames)')
        last = f
IN = max(0, IN_FRAME or 0)
OUT = N if OUT_FRAME is None else OUT_FRAME
first = [f for ph in PHRASES for f, _ in ph['words']][1:2]
if first and first[0] <= IN:
    sys.exit(f'IN_FRAME {IN} is at or after the second wall word (frame {first[0]}): the wall has to be up before it')
if not last < OUT <= N:
    sys.exit(f'OUT_FRAME {OUT} has to come after the last word (frame {last}) and inside the slot ({N} frames)')
tail = OUT - last
if tail < 30:
    notes.append(f'only {tail} frames between the last word and the wall leaving: it needs about a second to be read.')


def F(n):
    """time of frame n, 2 ms early so a set lands ON that frame"""
    return max(0.0, n / 30 - .002)


T_IN = F(IN)


def wwidth(w):
    return (sum(MET['w'][c] for c in w) + LS * len(w)) * FS


for ph in PHRASES:
    for _, w in ph['words']:
        if wwidth(w) > W - 70:
            notes.append(f'{w} is {wwidth(w):.0f} px wide at FS {FS}: it never fits the frame whole. Split it, drop it or lower FS.')

# ---- rows: one row ends just above the speaker's head (the accent row), the grid runs up and down from there
BASE = (PITCH - (MET['asc'] + MET['desc']) * FS) / 2 + MET['asc'] * FS      # baseline, below the top of a row
CAPT = BASE - MET['cap'] * FS                                               # top of the capitals, below the top of a row
acc_bottom = ACCENT_Y if ACCENT_Y is not None else MS['head_top_min'] - HEAD_GAP
t_acc = acc_bottom - BASE
if t_acc + CAPT < 24:
    notes.append('no room for a row above their head at this letter size: the yellow row sits at the top of the frame '
                 'and the speaker covers part of it. Lower FS, or this framing is too tight for a type wall.')
    t_acc = 24 - CAPT
elif t_acc + CAPT < 220:
    notes.append(f'the yellow row starts at y {t_acc + CAPT:.0f}, above the top safe line (220): app buttons can sit on it.')
ACC = max(0, math.ceil(t_acc / PITCH))          # number of the accent row
Y0 = t_acc - ACC * PITCH
NROWS = math.ceil((H - Y0) / PITCH)
DIRS = [1 if i % 2 == 0 else -1 for i in range(NROWS)]
SPEED = [SPEEDS[i % len(SPEEDS)] for i in range(NROWS)]


def keep_spans(y):
    out = []
    for poly in KEEP:
        xs = []
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if (ya <= y) != (yb <= y):
                xs.append(xa + (y - ya) * (xb - xa) / (yb - ya))
        xs.sort()
        out += [[xs[k], xs[k + 1]] for k in range(0, len(xs) - 1, 2)]
    return out


COLS = 135                                       # 8 px columns


def row_room(i):
    """(share of the row's letters that stays visible, centre x of the widest gap, gap width)"""
    y0, y1 = Y0 + i * PITCH + CAPT, Y0 + i * PITCH + BASE
    cov, lines = [0] * COLS, 0
    for y in range(max(0, int(y0) // 4 * 4), min(H, int(y1)) + 1, 4):
        lines += 1
        hit = [False] * COLS
        for a, b in MS['spans'].get(str(y), []) + keep_spans(y):
            for c in range(max(0, int(a) // 8), min(COLS, int(b) // 8 + 1)):
                hit[c] = True
        cov = [v + h for v, h in zip(cov, hit)]
    if not lines:
        return 0.0, W / 2, 0
    clear = [v / lines < .5 for v in cov]
    best, run = (0, 0), 0
    for c in range(COLS + 1):
        if c < COLS and clear[c]:
            run += 1
        else:
            if run > best[0]:
                best = (run, c - run)
            run = 0
    return 1 - sum(cov) / lines / COLS, (best[1] + best[0] / 2) * 8, best[0] * 8


ROOM = [row_room(i) for i in range(NROWS)]
SHOWN = [i for i in range(NROWS) if i == ACC or ROOM[i][0] >= .1]          # rows nobody would ever see are not built

# ---- what every row says and when
hits = [F(ph['words'][0][0]) if pi else T_IN for pi, ph in enumerate(PHRASES) if ph.get('hit')]
T_YEL = hits[0] if hits else T_IN
STATES = {}
for i in SHOWN:
    st = []                                      # (time, word, time of the word itself)
    for pi, ph in enumerate(PHRASES):
        ws = ph['words']
        m = len(ws)
        j = (i - ACC - 1) % m                    # rows under the accent row read word 1, 2, 3 top-down
        for q, (f, w) in enumerate(ws):
            if i != ACC and q > j:
                break
            t0 = T_IN if (pi == 0 and q == 0) else F(f)
            if (pi == 0 and q == 0) or i == ACC:
                t = t0                           # the accent row is the speaker: it says every word on its frame
            elif q == 0:
                t = t0 + min(6, abs(i - ACC)) * (1 if ph.get('hit') else .5) / 30     # a new phrase spreads out from the speaker's head
            else:
                t = t0 + (i // m) * .5 / 30
            st.append((t, w, t0))
    for k in range(len(st) - 2, -1, -1):         # fast speech: a late row never swaps after its next word is due
        if st[k][0] > st[k + 1][0] - .034:
            st[k] = (st[k + 1][0] - .034, st[k][1], st[k][2])
    st = [s for k, s in enumerate(st) if k == 0 or s[0] >= s[2] - 1e-6]     # no time left for that word: the row skips it
    STATES[i] = [(max(T_IN, t), w) for t, w, _ in st]

wmax = max(wwidth(w) for _, w in STATES[ACC])
XCEN = {}
for i in SHOWN:
    vis, cx, gap = ROOM[i]
    if i in XC:
        XCEN[i] = XC[i]
    elif i == ACC:                               # over the speaker's head, but never so far that the word leaves the frame
        lo, hi = 35 + wmax / 2, W - 35 - wmax / 2
        XCEN[i] = min(max(MS['head_x'], lo), hi) if lo <= hi else W / 2
    elif vis > .97:
        XCEN[i] = W / 2 + (90 if i % 2 else -70)
    else:
        XCEN[i] = cx


def row(i):
    tw = []
    d, v = DIRS[i], SPEED[i] * DIRS[i]
    cls = 'solid' if (i - ACC) % 2 == 0 else 'outl'
    states = STATES[i]
    strips = []
    for k, (ts, word) in enumerate(states):
        w = wwidth(word)
        pitch = w + GAP
        base = XCEN[i] - w / 2 - v * ts - max(0, k - 1) * KICK * d    # where the row has marched and kicked to by then
        n = int(2600 / pitch) + 3
        spans = ''.join(f'<span class="wd" style="left:{base + j * pitch:.1f}px">{word}</span>' for j in range(-n, n + 1))
        sid = f'r{i}s{k}'
        acc = ' acc' if (i == ACC and ts >= T_YEL - .01) else ''
        strips.append(f'<div id="{sid}" class="strip{acc}">{spans}</div>')
        if k == 0:
            continue
        nxt = states[k + 1][0] if k + 1 < len(states) else DUR
        kd = max(.03, min(.5, nxt - ts - .005))               # the kick ends before the next swap starts
        tw += [f"tl.set('#r{i}s{k - 1}',{{autoAlpha:0}},{ts:.3f});",
               f"tl.set('#{sid}',{{autoAlpha:1}},{ts:.3f});",
               # slam: vertical squash + quick focus pull on the new word
               f"tl.fromTo('#{sid}',{{scaleY:1.5,scaleX:1.04,filter:'blur(6px)'}},{{scaleY:1,scaleX:1,filter:'blur(0px)',"
               f"duration:{min(.32, kd):.3f},ease:'expo.out',immediateRender:false}},{ts:.3f});",
               f"tl.fromTo('#k{i}',{{x:{(k - 1) * KICK * d}}},{{x:{k * KICK * d},duration:{kd:.3f},ease:'expo.out',"
               f"immediateRender:false}},{ts:.3f});"]
    tw.insert(0, f"gsap.set('#r{i} .strip',{{autoAlpha:0}}); gsap.set('#r{i}s0',{{autoAlpha:1}});")
    tw.append(f"tl.fromTo('#m{i}',{{x:0}},{{x:{v * DUR:.1f},duration:{DUR:.3f},ease:'none',immediateRender:false}},0);")
    e0 = T_IN + SHOWN.index(i) * .028            # rows whip in one after another from the side they travel from
    tw += [f"gsap.set('#e{i}',{{x:{-d * 1100},autoAlpha:0,filter:'blur(18px)'}});",
           f"tl.to('#e{i}',{{autoAlpha:1,duration:.06,ease:'none'}},{e0:.3f});",
           f"tl.to('#e{i}',{{x:0,duration:{ENTRY_D},ease:'expo.out'}},{e0:.3f});",
           f"tl.to('#e{i}',{{filter:'blur(0px)',duration:.3,ease:'power2.out'}},{e0:.3f});"]
    html = (f'<div id="r{i}" class="row {cls}" style="top:{Y0 + i * PITCH:.1f}px"><div id="e{i}" class="lay">'
            f'<div id="k{i}" class="lay"><div id="m{i}" class="lay">{"".join(strips)}</div></div></div></div>')
    return html, tw


def sfx_len(path):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True).stdout)


def audio():
    if os.environ.get('SFX') == '0':
        return []
    cues = [('whoosh-short', max(0.0, T_IN - .03), VOL_IN)]
    for pi, ph in enumerate(PHRASES):
        t = F(ph['words'][0][0]) if pi else T_IN
        if ph.get('hit'):
            cues.append(('impact-bass-short', t, VOL_HIT))
        elif pi:
            cues.append(('whoosh-short', max(0.0, t - .04), VOL_SWAP))
    out, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(cues, key=lambda x: x[1])):
        path = next((p for p in (f'assets/sfx/{name}.mp3', f'assets_fx/{name}.mp3') if os.path.exists(p)), None)
        if path is None or vol <= 0:
            if path is None:
                print(f'  (sound {name} not found in assets/sfx or assets_fx: skipped)')
            continue
        d = min(sfx_len(path), DUR - t - .002)
        if d < .08:
            continue
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


OX = 100 * MS['head_x'] / W                                             # the wall glows and punches from the speaker's head
OY = 100 * (MS['head_top_med'] + .6 * MS['head_w']) / H
GRADE = 'contrast(1.04) saturate(.94) brightness(.97)'
KEEP_PATH = ' '.join('M' + ' L'.join(f'{x:.0f} {y:.0f}' for x, y in poly) + ' Z' for poly in KEEP)
# the wall is cut away where a KEEP shape is, so the real room (one video underneath) shows through there
CLIP_CSS = f"clip-path:path(evenodd,'M0 0 L{W} 0 L{W} {H} L0 {H} Z {KEEP_PATH}')" if KEEP else ''

CSS = f'''
@font-face{{font-family:'Inter Tight Wall';font-style:normal;font-weight:900;font-display:block;src:url('assets_fx/InterTightWall-900.woff2') format('woff2');}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{GROUND[2]}}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:{GROUND[2]}}}
#base{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}}
#fx{{position:absolute;inset:0;z-index:1}}
#wallclip{{position:absolute;inset:0;z-index:1;overflow:hidden;background:{GROUND[2]};{CLIP_CSS}}}
#wall{{position:absolute;inset:0;z-index:1;transform-origin:{OX:.1f}% {OY:.1f}%;
  background:radial-gradient(70% 42% at {OX:.1f}% {OY + 5:.1f}%,{GROUND[0]} 0%,{GROUND[1]} 55%,{GROUND[2]} 100%)}}
.row{{position:absolute;left:0;width:{W}px;height:{PITCH}px}}
.lay{{position:absolute;left:0;top:0;width:{W}px;height:{PITCH}px}}
.strip{{position:absolute;left:0;top:0;width:{W}px;height:{PITCH}px;transform-origin:50% 50%}}
.wd{{position:absolute;top:0;white-space:nowrap;font-family:'Inter Tight Wall';font-weight:900;font-size:{FS}px;line-height:{PITCH}px;
  letter-spacing:{LS}em}}
.solid .wd{{color:{INK};opacity:.9}}
.outl .wd{{color:transparent;-webkit-text-stroke:{3.5 * FS / 205:.1f}px {INK}99}}
.acc .wd{{color:{ACCENT};opacity:1;-webkit-text-stroke:0}}
#wvig{{position:absolute;inset:0;z-index:2;pointer-events:none;
  background:radial-gradient(85% 60% at {OX:.1f}% {OY + 10:.1f}%,rgba(10,11,8,0) 45%,rgba(10,11,8,.55) 100%),
  linear-gradient(180deg,rgba(10,11,8,.35) 0%,rgba(10,11,8,0) 14%)}}
#flash{{position:absolute;inset:0;z-index:2;background:{ACCENT};mix-blend-mode:soft-light;pointer-events:none}}
#fgwrap{{position:absolute;inset:0;z-index:5;filter:drop-shadow(0 26px 60px rgba(0,0,0,.72)) drop-shadow(0 4px 14px rgba(0,0,0,.45))}}
#fg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:{GRADE}}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div>'
              f'<div style="position:absolute;left:0;right:0;top:{MS["head_top_min"]}px;height:2px;background:#39f"></div>'
              f'<svg width="{W}" height="{H}" style="position:absolute;inset:0"><path d="{KEEP_PATH}" fill="none" '
              'stroke="#3f6" stroke-width="3"/></svg></div>')


def build():
    rows_html, tw = [], []
    for i in SHOWN:
        h, t = row(i)
        rows_html.append(h)
        tw += t
    # the wall as a whole: a punch + a faint flash on a hit word, a small settle on every other new phrase
    moves = [(F(ph['words'][0][0]), bool(ph.get('hit'))) for pi, ph in enumerate(PHRASES) if pi]
    tw.append("gsap.set('#flash',{autoAlpha:0});")
    for k, (t, hit) in enumerate(moves):
        nxt = moves[k + 1][0] if k + 1 < len(moves) else DUR
        d = max(.05, min(.6 if hit else .4, nxt - t - .005))
        tw.append(f"tl.fromTo('#wall',{{scale:{1.08 if hit else 1.03}}},{{scale:1,duration:{d:.3f},ease:'expo.out',"
                  f"immediateRender:false}},{t:.3f});")
        if hit:
            tw += [f"tl.set('#flash',{{autoAlpha:.3}},{t:.3f});",
                   f"tl.to('#flash',{{autoAlpha:0,duration:.35,ease:'power2.out'}},{t + .001:.3f});"]
    nl = '\n'
    base = ''
    if KEEP or IN > 0 or OUT < N:                # the real room: under the KEEP shapes, before the wall arrives, after it leaves
        base = (f'  <video id="base" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" '
                f'data-duration="{DUR_S}" data-track-index="0"></video>')
        if IN > 0:                               # the room takes the speaker's grade only while the wall is up, so the seams match
            tw += ["gsap.set('#fx',{autoAlpha:0});", f"tl.set('#fx',{{autoAlpha:1}},{T_IN:.3f});",
                   f"tl.set('#base',{{filter:'{GRADE}'}},{T_IN:.3f});"]
        else:
            tw.append(f"gsap.set('#base',{{filter:'{GRADE}'}});")
        if OUT < N:
            tw += [f"tl.set('#fx',{{autoAlpha:0}},{F(OUT):.3f});", f"tl.set('#base',{{filter:'none'}},{F(OUT):.3f});"]
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR_S}" data-width="{W}" data-height="{H}">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio())}
{base}
  <div id="fx">
  <div id="wallclip">
  <div id="wall">
{nl.join(rows_html)}
  </div>
  <div id="wvig"></div>
  <div id="flash"></div>
  </div>
  <div id="fgwrap"><video id="fg" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="1"></video></div>
  </div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {DUR_S});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open('index.html', 'w').write(build())
print(f'wrote index.html for renders/{SLOT}.mp4: {N} frames, wall up from frame {IN} to {OUT}, '
      f'{len(SHOWN)} of {NROWS} rows built, letters {FS} px, '
      f'yellow row = row {ACC} (letters y {Y0 + ACC * PITCH + CAPT:.0f} to {Y0 + ACC * PITCH + BASE:.0f})')
for i in SHOWN:
    print(f'  row {i}{"*" if i == ACC else " "} y {Y0 + i * PITCH + CAPT:5.0f}  {ROOM[i][0]:4.0%} visible  word centred at x {XCEN[i]:4.0f}  '
          + '  '.join(f'{w}@{round(t * 30):d}' for t, w in STATES[i]))
for s in notes:
    print('  !! ' + s)
