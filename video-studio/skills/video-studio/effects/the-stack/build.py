#!/usr/bin/env python3
"""THE STACK: a data-explainer layout. The full-frame picture snaps down into a rounded window at the bottom, a light
dotted page takes the rest, and data cards stack above the speaker: each card drops in on a spoken word and pushes
their window down, its bars race with counting numbers, and the winning bar lands on the word you choose. Then the
window grows back to the full frame.

  F_IN - 8   last untouched frame; the picture starts shrinking into the window
  F_IN       the layout has landed (title + first card), bars start racing 3 frames later
  card.at    a later card has landed and the window has moved down to make room
  win_at     the winning bar of that card arrives (number stops, tick pops, card glows)
  F_OUT      the plain full-frame picture is back (None = the layout stays to the last frame: end on a cut)

Layers: page < title + cards < the speaker video in its window < bottom shade < the effect's caption words.
The cutout is NOT drawn. measure.py only reads its alpha to find their head, so the window crop is measured.
THE NUMBERS ARE YOURS: every title, label and value in CARDS is something said in the clip or given by the user.
The effect ships a placeholder and refuses to build until you replace it. Never estimate or round up a figure.

Run order (from the slot folder, see effect.md):
  python onsets.py     word onsets as frames  -> F_IN, F_OUT, card `at` / `win_at`, CAPS
  python measure.py    head position from the cutout alpha -> work/head.json + work/head.jpg (look at it)
  python3 build.py     writes index.html   (SAFE=1 guide, CAPTIONS=0 no caption words, SFX=0 no sounds, GRADE=1)
"""
import html
import json
import os
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
TITLE = 'PLACEHOLDER TITLE'   # bold line above the cards (the question the cards answer). '' = no title line.
                              # Keep it under 30 characters; it is words the user says or gives, not a claim you add
CARDS = [                     # one dict per card, in the order they land. 1 to 3 cards, 1 to 5 rows each.
    dict(title='PLACEHOLDER CARD',      # card heading: what is being compared
         sub='your own numbers go here',  # small grey line under it (the source or the unit in words). '' = none
         rows=[('Label A', 0), ('Label B', 0), ('Label C', 0)],
                                        # (label, value): the user's OWN figures, as said in the clip or given in
                                        # chat. A number (12400, 2.5) or a string shown as typed ('12,400', '2.50')
         unit=('', ''),                 # (before, after) every value: ('$', ''), ('', '%'), ('', ' hrs')
         full=None,                     # value that fills the whole bar. None = the biggest value in this card.
                                        # Use 100 for percentages so 40% is 40% of the bar
         win=None,                      # index (0 = first row) of the row that wins the race: it gets the accent
                                        # colour and arrives last, on `win_at`. None = every bar in the accent,
                                        # no winner. The winner is what the numbers say, never a ranking you make up
         at=None,                       # frame this card has landed (onset of the word that introduces it, from
                                        # onsets.py). The FIRST card always lands with the layout on F_IN
         race=None,                     # frame its bars start to grow. None = 3 frames after it lands
         win_at=None),                  # frame the winning bar arrives (onset of the word that names the winner
                                        # or its number). None = 27 frames after `race`
]
F_IN = 12            # frame the layout has landed (onset of the first word of the line). 8 or more: the picture
                     # shrinks during the 8 frames before it, and every frame before that is untouched a-roll
F_OUT = None         # frame the plain full-frame picture is back (onset of a later word, at most frames - 1).
                     # None = the layout stays up to the last frame, so the reel must CUT on the slot's last frame
CAPS = []            # the effect's own caption words, drawn on the speaker's chest inside the window:
                     #   [(frame, 'WORDS'), (frame, 'PUNCH WORD', 'acc'), ...]  each stays until the next one;
                     # 'acc' = bigger, in the accent tint. Frames from onsets.py, F_IN - 8 or later. Only words the speaker
                     # says, 22 characters or fewer per entry. [] = none (the main reel captions the line: see CAP_Y)
ACCENT = '#22B65A'   # the one colour: winning bar, its number and tick, card glow, 'acc' caption words.
                     # The user's brand colour as hex. Not orange, not grey
HEAD = None          # None = measured by measure.py from the cutout alpha (work/head.json). Or type it:
                     # (top_y, centre_x, width) of the speaker's head in px on the 1080x1920 a-roll, read off work/head.jpg
                     # (shown at half size). Typed = the slot needs no cutout at all
FOLLOW = True        # True = the window follows the speaker's head (smoothed track from measure.py), so a handheld or
                     # swaying speaker stays put in the window. False = one fixed crop (also when HEAD is typed)
ZOOM = 1.0           # how big the speaker is in the window. 1.0 = head a quarter of the window width (head and shoulders).
                     # 1.2 = closer. It is capped by the room left under the stack and by the picture's own width
HEADROOM = 40        # px of picture kept above the top of the speaker's head inside the window
CAP_Y = None         # px: top of the caption band. None = measured (just under the speaker's chin, above 1470). build.py
                     # prints the band; with CAPTIONS=0 it stays empty for the main reel's own caption
SOUNDS = 'auto'      # 'auto' = whoosh as the picture shrinks, a pop per card, a sparkle on the last winner, a
                     # whoosh back. Or your own list of (stock sound name, frame, base volume). [] = none
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
NAME = os.path.basename(HERE)
FPS = 30
FP = shutil.which('ffprobe') or 'ffprobe'
SAFE, CAPTIONS, SFX, GRADE = (os.environ.get(k, d) not in ('', '0') for k, d in
                              (('SAFE', '0'), ('CAPTIONS', '1'), ('SFX', '1'), ('GRADE', '0')))

if os.path.exists('clip.json'):
    N = int(json.load(open('clip.json'))['frames'])
else:
    N = round(float(subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration',
                                    '-of', 'csv=p=0', 'assets/aroll.mp4'], capture_output=True, text=True).stdout) * FPS)
DUR = N / FPS

# ---------- fixed look ----------
LEAD, OUT_LEAD = 8, 8                 # frames the picture takes to shrink into the window / to grow back
CX, CW = 90, 900                      # card + window column
TOP = 226                             # first pixel row the layout uses (safe zone starts at 220)
TITLE_H = 66
ROW_PITCH, BAR_H = 48, 32
CARD_GAP, WIN_GAP = 14, 12            # between cards / between the last card and the speaker window
WIN_R, RAD = 80, 30                   # window top-corner radius, card radius
WIN_MAX = 1060                        # lowest the window top may sit (the head and a caption still fit above 1470)
PANEL_X = 18
HEAD_FRAC = 0.25                      # head width as a share of the window width at ZOOM 1
S_MIN, S_MAX = 0.86, 2.4              # the picture must still cover the 900 px window / stay sharp
CAP_H = 60
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'click-soft': .37, 'click': .3, 'sparkle': 1.2, 'impact-bass-1': 1.0}
SFX_GAIN = 0.75
GRADE_CSS = 'contrast(1.05) saturate(.94) brightness(.98)'


def die(msg):
    sys.exit(f'[{NAME}] {msg}')


def mix(c, to, k):
    a = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(to[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(x + (y - x) * k):02X}' for x, y in zip(a, b))


def num(v):
    """value as typed -> (number, decimals, uses commas, text)"""
    s = str(v).strip()
    try:
        x = float(s.replace(',', ''))
    except ValueError:
        die(f'row value {v!r} is not a number. Values are figures; put words in the label')
    return x, (len(s.split('.')[1]) if '.' in s else 0), ',' in s, s


# ---------- checks on the CLIP block ----------
words = ' '.join([TITLE] + [str(c.get('title', '')) + ' ' + str(c.get('sub', '')) for c in CARDS]).upper()
if 'PLACEHOLDER' in words or not CARDS:
    die('CARDS still holds the placeholder. This effect only shows the user\'s own figures: take the titles, labels '
        'and numbers from what is said in the clip or ask for them. No figures = leave the effect out.')
if len(ACCENT) != 7 or not ACCENT.startswith('#'):
    die('ACCENT must be a hex colour like #22B65A')
if F_IN < LEAD:
    die(f'F_IN is {F_IN}: it must be {LEAD} or more so the slot starts on the plain picture')
if F_OUT is not None and not (F_IN + 30 <= F_OUT <= N - 1):
    die(f'F_OUT {F_OUT} must lie between F_IN + 30 and frames - 1 ({N - 1}), or be None')
END = (F_OUT - OUT_LEAD) if F_OUT is not None else N        # last frame the layout is fully up
cards = []
for i, c in enumerate(CARDS):
    rows = [(str(l), ) + num(v) for l, v in c['rows']]
    if not 1 <= len(rows) <= 5:
        die(f'card {i + 1} has {len(rows)} rows: 1 to 5')
    at = F_IN if i == 0 else c.get('at')
    if at is None:
        die(f'card {i + 1} needs `at` (the frame it lands on)')
    if i and at < cards[-1]['at'] + 12:
        die(f'card {i + 1} lands on frame {at}: at least 12 frames after the card before it')
    race = c.get('race') if c.get('race') is not None else at + 3
    win_at = c.get('win_at') if c.get('win_at') is not None else race + 27
    if win_at < race + 9:
        die(f'card {i + 1}: win_at {win_at} is under 9 frames after the bars start ({race})')
    if win_at > END:
        print(f'!! card {i + 1}: the winning bar arrives on frame {win_at}, after the layout leaves ({END})')
    win = c.get('win')
    if win is not None and not 0 <= win < len(rows):
        die(f'card {i + 1}: win {win} is not a row index')
    full = float(c['full']) if c.get('full') else max(r[1] for r in rows)
    pre, suf = c.get('unit') or ('', '')
    cards.append(dict(id=chr(65 + i), title=str(c['title']), sub=str(c.get('sub') or ''), rows=rows, at=at, race=race,
                      win_at=win_at, win=win, full=full or 1.0, pre=pre, suf=suf))

# ---------- stack geometry ----------
y = TOP + (TITLE_H if TITLE else 6)
wins = []                                  # window top once card k has landed
for c in cards:
    c['head_h'] = 76 if c['sub'] else 60
    c['h'] = c['head_h'] + len(c['rows']) * ROW_PITCH + 34
    c['y'] = y
    y += c['h'] + CARD_GAP
    wins.append(y - CARD_GAP + WIN_GAP)
if wins[-1] > WIN_MAX:
    die(f'the stack is {wins[-1] - WIN_MAX} px too tall (each row is {ROW_PITCH} px, a card heading about 100): '
        'drop rows, a card, a sub line or the title')
label_w = min(300, max(110, max(len(r[0]) for c in cards for r in c['rows']) * 12 + 8))
val_w = max(len(c['pre'] + r[4] + c['suf']) for c in cards for r in c['rows']) * 15 + 44
BAR_X = PANEL_X + 4 + label_w + 14
BAR_W = CW - 2 * PANEL_X - (BAR_X - PANEL_X) - 14 - val_w
if BAR_W < 180:
    die('labels or values are too long for the row: shorten the labels (25 characters fit) or the unit')
STUB = 12

# ---------- the speaker window: crop from the measured head ----------
TRK = []                                   # per frame: [head centre x, head top] minus the reference, in a-roll px
if HEAD is not None:
    h_top, h_cx, h_w = (float(v) for v in HEAD)
    chin_ratio = 1.4
elif os.path.exists('work/head.json'):
    hd = json.load(open('work/head.json'))
    h_top, h_cx, h_w, chin_ratio = hd['top'], hd['cx'], hd['width'], hd['chin_ratio']
    if FOLLOW and len(hd.get('track_top', [])) >= N:
        tt, tc = sorted(hd['track_top'][:N]), sorted(hd['track_cx'][:N])
        h_top, h_cx = tt[N // 2], tc[N // 2]                  # reference = where the speaker's head usually is
        TRK = [[round(hd['track_cx'][i] - h_cx, 1), round(hd['track_top'][i] - h_top, 1)] for i in range(N)]
    else:
        low = hd['top_range'][1] - hd['top']                # fixed crop: the speaker may drop this far below the top
        chin_ratio += low / max(1.0, h_w)
else:
    die('no head measurement: run measure.py (needs the cutout), or type HEAD = (top, centre_x, width)')
room = 1470 - wins[-1] - HEADROOM - 24 - CAP_H - 6           # px for the speaker's head between window top and caption band
want = HEAD_FRAC * CW * ZOOM
S = min(want, room / chin_ratio) / h_w
if S < S_MIN:
    need = HEADROOM + chin_ratio * h_w * S_MIN + 24 + CAP_H + 6
    if 1470 - wins[-1] < need:
        die(f'close shot: their head is {h_w:.0f} px wide and cannot shrink further, so the stack must end '
            f'{need - (1470 - wins[-1]):.0f} px higher. Drop rows, a card, a sub line or the title')
    S = S_MIN
S = min(S, S_MAX)
TX = min(CX, max(CX + CW - 1080 * S, 540 - h_cx * S))
OFF = min(0.0, HEADROOM - h_top * S)                        # window top -> picture top (the picture never ends
off = lambda wy: max(OFF, 1920 * (1 - S) - wy)              # above the frame bottom: a shrunk picture sits lower)
chin = wins[-1] + off(wins[-1]) + (h_top + chin_ratio * h_w) * S   # screen y of the speaker's chin with the full stack up
cap_y = CAP_Y if CAP_Y is not None else min(1470 - CAP_H - 6, round(chin + 24))
if cap_y < chin + 10:
    print(f'!! the caption band (y {cap_y}) touches their chin (y {chin:.0f}): fewer rows, or CAPTIONS=0')

# ---------- timeline data ----------
t = lambda f: f / FPS
BARS, tw = [], []
for c in cards:
    wd = max(.3, t(c['win_at'] - c['race']))
    for k, (label, v, dec, comma, txt) in enumerate(c['rows']):
        share = min(1.0, max(0.0, v / c['full']))
        is_win = c['win'] == k
        d = wd if (is_win or c['win'] is None) else wd * (.55 + .30 * share)
        BARS.append(dict(id=f"{c['id']}{k}", t0=round(t(c['race']) + (0 if is_win else k * .04), 4), d=round(d, 4),
                         w=round(STUB + (BAR_W - STUB) * share, 1), v=v, dec=dec, comma=comma, pre=c['pre'],
                         suf=c['suf'], fin=c['pre'] + txt + c['suf']))
WINS = [dict(y=wins[0])] + [dict(y=wins[i], t0=round(t(cards[i]['at'] - 9), 4), d=round(t(7), 4))
                             for i in range(1, len(cards))]
T_IN0, T_IND = t(F_IN - LEAD), t(LEAD)
T_OUT0 = t(F_OUT - OUT_LEAD) if F_OUT is not None else None

tw += ["gsap.set('#titlew,.cardw,.glow,#fadew" + (",.chk" if any(c['win'] is not None for c in cards) else '') +
       "',{autoAlpha:0});"]
k0 = T_IN0 + T_IND * .2
if TITLE:
    tw += [f"tl.fromTo('#titlew',{{autoAlpha:0,y:-46}},{{autoAlpha:1,y:0,duration:{T_IND * .8:.3f},ease:'back.out(1.6)',immediateRender:false}},{k0:.3f});"]
tw += [f"tl.to('#fadew',{{autoAlpha:1,duration:{T_IND:.3f},ease:'power2.out'}},{T_IN0:.3f});"]
for i, c in enumerate(cards):
    t0 = (k0 + .02) if i == 0 else t(c['at'] - 5)
    dd = (t(c['at']) - t0)
    tw += [f"tl.fromTo('#cw{c['id']}',{{autoAlpha:0,y:{-36 if i == 0 else -26},scale:{1.04 if i == 0 else .96}}},{{autoAlpha:1,y:0,scale:1,duration:{dd:.3f},ease:'back.out(1.4)',immediateRender:false}},{t0:.3f});"]
    if c['win'] is not None and c['win_at'] <= END:
        rid = f"{c['id']}{c['win']}"
        tw += [f"tl.fromTo('#k{rid}',{{autoAlpha:0,scale:.2}},{{autoAlpha:1,scale:1,duration:.2,ease:'back.out(3)',immediateRender:false}},{t(c['win_at']) - .03:.3f});",
               f"tl.fromTo('#n{rid}',{{scale:1.14}},{{scale:1,duration:.26,ease:'power2.out',immediateRender:false}},{t(c['win_at']):.3f});",
               f"tl.fromTo('#glow{c['id']}',{{autoAlpha:0}},{{autoAlpha:1,duration:.14,ease:'power2.out',immediateRender:false}},{t(c['win_at']) - .03:.3f});",
               f"tl.to('#glow{c['id']}',{{autoAlpha:0,duration:.5,ease:'power2.in'}},{t(c['win_at']) + .22:.3f});"]
if T_OUT0 is not None:
    tw += [f"tl.to('#stack,#fadew',{{autoAlpha:0,duration:.13,ease:'power2.in'}},{T_OUT0:.3f});"]

caps = []
if CAPTIONS:
    cs = sorted(CAPS, key=lambda x: x[0])
    for k, e in enumerate(cs):
        f0, txt = e[0], str(e[1])
        acc = len(e) > 2 and e[2] == 'acc'
        f1 = cs[k + 1][0] if k + 1 < len(cs) else END
        if f0 < F_IN - LEAD or f0 >= END:
            die(f'caption {txt!r} on frame {f0}: caption frames run from F_IN - {LEAD} ({F_IN - LEAD}) to {END - 1}')
        if not txt:
            continue
        if len(txt) > 22:
            print(f'!! caption {txt!r} is {len(txt)} characters: it is shrunk to fit, split it in two')
        fs = min(62 if acc else 50, 860 / (.66 * len(txt)))
        caps.append(f'<div class="cap{" acc" if acc else ""}" id="cap{k}" style="font-size:{fs:.0f}px">{html.escape(txt.upper())}</div>')
        tw += [f"gsap.set('#cap{k}',{{autoAlpha:0}});",
               f"tl.fromTo('#cap{k}',{{autoAlpha:0,y:10,scaleX:1.08}},{{autoAlpha:1,y:0,scaleX:1,duration:.12,ease:'power3.out',immediateRender:false}},{max(0, t(f0) - .02):.3f});"]
        if f1 < N:
            tw += [f"tl.set('#cap{k}',{{autoAlpha:0}},{t(f1) - .002:.3f});"]

sounds = SOUNDS
if sounds == 'auto':
    sounds = [('whoosh-short', F_IN - LEAD, .22)] + [('pop', c['at'] - 2, .12) for c in cards]
    last = [c for c in cards if c['win'] is not None and c['win_at'] <= END]
    sounds += [('sparkle', last[-1]['win_at'], .14)] if last else []
    sounds += [('whoosh-short', F_OUT - OUT_LEAD - 1, .16)] if F_OUT is not None else []
audio, lanes = [], []
for k, (name, f, vol) in enumerate(sorted(sounds if SFX else [], key=lambda x: x[1])):
    if name not in SFX_LEN:
        die(f'unknown sound {name!r}: stock sounds are {", ".join(SFX_LEN)}')
    st = max(0.0, t(f))
    dd = min(SFX_LEN[name], DUR - st)
    if dd <= .05:
        continue
    lane = next((i for i, end in enumerate(lanes) if end <= st), None)
    if lane is None:
        lanes.append(0)
        lane = len(lanes) - 1
    lanes[lane] = st + dd
    audio.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{st:.3f}" data-duration="{dd:.3f}" '
                 f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')

# ---------- page ----------
A_DK, A_LT, A_NUM, A_CAP = mix(ACCENT, '#000000', .10), mix(ACCENT, '#FFFFFF', .28), mix(ACCENT, '#000000', .22), mix(ACCENT, '#FFFFFF', .45)
TICK = (f'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="{ACCENT}"/><path d="M7 12.5l3.2 3.2L17 9" '
        'fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def card_html(c):
    rows = []
    for k, (label, v, dec, comma, txt) in enumerate(c['rows']):
        rid = f"{c['id']}{k}"
        hot = c['win'] is None or c['win'] == k
        top = 10 + k * ROW_PITCH + (ROW_PITCH - BAR_H) / 2
        rows.append(f'''
      <div class="row" style="top:{top:.0f}px">
        <div class="lab">{html.escape(label)}</div>
        <div class="bar {'hot' if hot else 'cool'}" id="b{rid}"></div>
        <div class="val" id="v{rid}"><span class="num {'hot' if hot else 'cool'}" id="n{rid}">{html.escape(c['pre'])}0{html.escape(c['suf'])}</span>{f'<div class="chk" id="k{rid}">{TICK}</div>' if c['win'] == k else ''}</div>
      </div>''')
    sub = f'<div class="cs">{html.escape(c["sub"])}</div>' if c['sub'] else ''
    return f'''
  <div class="glow" id="glow{c['id']}" style="left:{CX - 6}px;top:{c['y'] - 6}px;width:{CW + 12}px;height:{c['h'] + 12}px"></div>
  <div class="cardw" id="cw{c['id']}" style="top:{c['y']}px;height:{c['h']}px"><div class="card">
    <div class="ch">{html.escape(c['title'])}</div>{sub}
    <div class="panel" style="top:{c['head_h']}px">{''.join(rows)}</div>
  </div></div>'''


title_fs = min(52, 880 / (.52 * max(1, len(TITLE))))
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#E4E4E4}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#E4E4E4}}
#ground{{position:absolute;inset:0;z-index:0;
  background:radial-gradient(rgba(0,0,0,.075) 1.4px,transparent 1.9px) 0 0/26px 26px,
  radial-gradient(120% 75% at 50% 28%,#F0F0F0 0%,#E5E5E5 55%,#D8D8D8 100%)}}
#stack{{position:absolute;inset:0;z-index:3}}
#titlew{{position:absolute;left:{CX}px;width:{CW}px;top:{TOP}px;text-align:center}}
#title{{font:800 {title_fs:.0f}px 'Inter Tight';letter-spacing:-1.2px;color:#15171A;line-height:60px;white-space:nowrap}}
.cardw{{position:absolute;left:{CX}px;width:{CW}px}}
.card{{position:absolute;inset:0;border-radius:{RAD}px;background:#FDFDFD;
  box-shadow:0 22px 48px rgba(20,24,30,.10),0 3px 10px rgba(20,24,30,.06)}}
.ch{{position:absolute;left:24px;right:24px;top:14px;text-align:center;font:800 34px 'Inter Tight';letter-spacing:-.5px;color:#1A1C20;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cs{{position:absolute;left:24px;right:24px;top:53px;text-align:center;font:500 17px Inter;color:#7C828C;letter-spacing:.2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.panel{{position:absolute;left:{PANEL_X}px;right:{PANEL_X}px;bottom:16px;border-radius:20px;background:#F1F2F5}}
.row{{position:absolute;left:0;right:0;height:{BAR_H}px}}
.lab{{position:absolute;left:18px;top:0;width:{label_w}px;height:{BAR_H}px;line-height:{BAR_H}px;font:600 21px/{BAR_H}px Inter;color:#22252A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bar{{position:absolute;left:{BAR_X - PANEL_X}px;top:0;width:{STUB}px;height:{BAR_H}px;border-radius:9px;box-shadow:inset 0 -2px 0 rgba(0,0,0,.08)}}
.bar.hot{{background:linear-gradient(90deg,{A_DK} 0%,{ACCENT} 55%,{A_LT} 100%)}}
.bar.cool{{background:linear-gradient(90deg,#8C95A3 0%,#A6AEBB 100%)}}
.val{{position:absolute;left:{BAR_X - PANEL_X + 12}px;top:0;height:{BAR_H}px;display:flex;align-items:center;gap:8px;white-space:nowrap}}
.num{{font:800 26px 'Inter Tight';letter-spacing:-.3px;display:inline-block;transform-origin:0 50%}}
.num.hot{{color:{A_NUM}}}
.num.cool{{color:#5B6472}}
.chk{{width:24px;height:24px}}
.chk svg{{width:24px;height:24px;display:block}}
.glow{{position:absolute;border-radius:{RAD + 6}px;box-shadow:0 0 0 3px {ACCENT}8C,0 0 40px {ACCENT}59}}
#rig{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:5;transform-origin:0 0}}
#plate{{position:absolute;inset:0}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
{f".g{{filter:{GRADE_CSS}}}" if GRADE else ''}
#fadew{{position:absolute;left:0;right:0;top:1500px;height:420px;z-index:6}}
#fade{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 0%,rgba(0,0,0,.38) 45%,rgba(0,0,0,.78) 100%)}}
.cap{{position:absolute;left:110px;width:860px;top:{cap_y}px;z-index:9;text-align:center;color:#FAFAF7;white-space:nowrap;
  font-family:'Inter Tight';font-weight:900;letter-spacing:.6px;line-height:{CAP_H}px;
  text-shadow:0 3px 18px rgba(0,0,0,.6),0 1px 3px rgba(0,0,0,.45)}}
.cap.acc{{color:{A_CAP}}}
'''
GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
         '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
         '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
         '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
         '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
         '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div>'
         f'<div style="position:absolute;left:110px;width:860px;top:{cap_y}px;height:{CAP_H}px;outline:2px dashed rgba(255,235,60,.9)"></div></div>')
JS = f'''
const tl = gsap.timeline({{ paused: true }});
const E3o=gsap.parseEase('power3.out'),E3io=gsap.parseEase('power3.inOut'),E2o=gsap.parseEase('power2.out');
const cl=x=>x<0?0:(x>1?1:x);
const S={S:.5f},TXW={540 - h_cx * S:.3f},OFF={OFF:.3f},CX={CX},CW={CW},WIN_R={WIN_R},STUB={STUB};
const TRK={json.dumps(TRK, separators=(',', ':'))};
const TIN0={T_IN0:.5f},TIND={T_IND:.5f},TOUT0={'null' if T_OUT0 is None else f'{T_OUT0:.5f}'},TOUTD={t(OUT_LEAD):.5f};
const WINS={json.dumps(WINS)};
const BARS={json.dumps(BARS)};
const rig=document.getElementById('rig'),plate=document.getElementById('plate');
for(const b of BARS){{b.eb=document.getElementById('b'+b.id);b.ev=document.getElementById('v'+b.id);b.en=document.getElementById('n'+b.id);}}
function fmt(v,dec,comma){{let s=v.toFixed(dec);if(comma){{const a=s.split('.');a[0]=a[0].replace(/\\B(?=(\\d{{3}})+(?!\\d))/g,',');s=a.join('.');}}return s;}}
// One function of time draws the window and the bars, so any seek lands on exactly the same picture.
function layout(t){{
  let p=E3o(cl((t-TIN0)/TIND+1e-6));
  if(TOUT0!==null&&t>=TOUT0)p=1-E3io(cl((t-TOUT0)/TOUTD+1e-6));
  let wy=WINS[0].y;
  for(let i=1;i<WINS.length;i++)wy+=(WINS[i].y-WINS[i-1].y)*E3o(cl((t-WINS[i].t0)/WINS[i].d+1e-6));   // the window moves first
  if(p<1e-4){{rig.style.transform='none';plate.style.clipPath='none';}}
  else{{
    let dx=0,dy=0;                       // FOLLOW: where their head is on this frame, relative to its usual place
    if(TRK.length){{const f=Math.min(TRK.length-1,Math.max(0,t*30)),i=Math.floor(f),j=Math.min(TRK.length-1,i+1),u=f-i;
      dx=TRK[i][0]+(TRK[j][0]-TRK[i][0])*u;dy=TRK[i][1]+(TRK[j][1]-TRK[i][1])*u;}}
    const txf=Math.min(CX,Math.max(CX+CW-1080*S,TXW-dx*S));          // the picture always covers the window
    const tyf=Math.min(wy,Math.max(1920*(1-S),wy+OFF-dy*S));
    const s=1+(S-1)*p,tx=txf*p,ty=tyf*p;
    rig.style.transform='translate('+tx.toFixed(3)+'px,'+ty.toFixed(3)+'px) scale('+s.toFixed(5)+')';
    const x0=(CX*p-tx)/s,x1=(1080-(1080-CX-CW)*p-tx)/s,y0=(wy*p-ty)/s,y1=(1920-ty)/s,r=WIN_R*p/s;
    plate.style.clipPath='inset('+y0.toFixed(2)+'px '+(1080-x1).toFixed(2)+'px '+Math.max(0,1920-y1).toFixed(2)+'px '+x0.toFixed(2)+'px round '+r.toFixed(2)+'px '+r.toFixed(2)+'px 0px 0px)';
  }}
  for(const b of BARS){{
    const q=E2o(cl((t-b.t0)/b.d+1e-6)),w=STUB+(b.w-STUB)*q;
    b.eb.style.width=w.toFixed(2)+'px';b.ev.style.transform='translateX('+w.toFixed(2)+'px)';
    b.en.textContent=q>=1?b.fin:b.pre+fmt(b.v*q,b.dec,b.comma)+b.suf;
  }}
}}
layout(0);
(function(){{const o={{t:0}};tl.to(o,{{t:{DUR:.5f},duration:{DUR:.5f},ease:'none',onUpdate:function(){{layout(o.t);}}}},0);}})();
{chr(10).join(tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
'''
PAGE = f'''<!doctype html>
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
{chr(10).join(audio)}
  <div id="ground"></div>
  <div id="stack">
  {f'<div id="titlew"><div id="title">{html.escape(TITLE)}</div></div>' if TITLE else '<div id="titlew"></div>'}
{''.join(card_html(c) for c in cards)}
  </div>
  <div id="rig"><div id="plate"><video id="bgv" class="full g" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video></div></div>
  <div id="fadew"><div id="fade"></div></div>
{chr(10).join(caps)}
{GUIDE if SAFE else ''}
</div>
<script>{JS}</script>
</body>
</html>
'''
open('index.html', 'w').write(PAGE)
print(f'[{NAME}] wrote index.html: {N} frames, {len(cards)} card(s), window top {" -> ".join(str(w) for w in wins)}, '
      f'picture scale {S:.2f}, head {h_w * S:.0f} px wide on screen, chin at y {chin:.0f}, '
      + ('window follows their head' if TRK else 'fixed crop'))
print(f'  plain picture up to frame {F_IN - LEAD}' + (f' and from frame {F_OUT}' if F_OUT is not None else
      '; the layout stays to the last frame (cut the reel there)'))
print(f'  caption band: y {cap_y} to {cap_y + CAP_H}, x 110 to 970' + ('' if CAPTIONS and caps else
      '  (empty: the main reel\'s caption for these frames goes here)'))
if not CAPTIONS:
    # in a reel the buyer's own captions stay on: tell where they have room (the layout replaces the whole frame)
    print(f"  reel captions: this effect's own words are off. Add the slot with fx_add.py --caption-y {max(236, min(1376, int(cap_y)))} "
          'so the reel\'s captions sit in that band, then check one reel snapshot inside the slot')
if S >= S_MAX:
    print('!! the speaker is small in the source: the picture is enlarged 2.4x and will look soft')
