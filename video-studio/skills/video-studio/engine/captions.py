#!/usr/bin/env python3
"""Claude Creator Studio: the nineteen caption styles, one engine, all driven by the same word timings.

This file is a library. scripts/build_reel.py is what you run: it reads the buyer's picks, calls load(project) and
then page(<caption style key>) (or engine/styles.py for an overall style) and writes <project>/index.html.

Every style reads <project>/words.json: [{text, start, end, e?}] where e marks the words a style may treat differently:
  num  = a number worth showing big        key = a name / brand
  emph = the word the line leans on        cta = the comment keyword
Nothing below is specific to any clip. Where the speaker is comes from <project>/layout.json (scripts/layout.py:
head position measured on the footage, the three caption bands worked out from it). Pinned titles and any other
per-reel text come from <project>/plan.json, written by the editing Claude from the reel's hook.
"""
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
import skillenv  # noqa: E402

# ----------------------------------------------------------------------------------------------------------------------
# Per-clip values. Filled by load(project); the numbers here are only the fallback for footage with nobody in it.
# All coordinates are in the 1080x1920 frame.
# ----------------------------------------------------------------------------------------------------------------------
DEFAULT_BANDS = dict(HEAD_TOP=452, Y_ABOVE_HEAD=344, Y_CHEST=1170, Y_LOWER=1376,
                     WALL_LEFT=(70, 596, 300), WALL_RIGHT=(740, 640, 280))
HEAD_TOP = 452            # y of the top of the head, for words that sit BEHIND the head
Y_ABOVE_HEAD = 344        # top of a one-line caption that floats over the head (None: no room up there)
Y_CHEST = 1170            # top of a one-line caption over the chest / lap
Y_LOWER = 1376            # top of a lower-third subtitle line (must end above y 1470)
WALL_LEFT = (70, 596, 300)     # x, y, width of the open area left of the speaker (None: no room)
WALL_RIGHT = (740, 640, 280)   # same on the right
TITLE = ('', '')          # the reel's hook as two short lines, for a pinned title
SWASH = ('', '')          # the same hook, shorter, Title Case, for a swash title
VIDEO = 'assets/aroll.mp4'
CUTOUT = None             # assets/subject.webm when a person cutout exists
W, DUR = [], 0.0
PROJECT = None
LAYOUT, PLAN, SEGS = {}, {}, []
FACELESS = False          # nobody on camera (voice over b-roll)
LIFT, FILL = 0, '#0d0d10'  # close-up fallback: the picture is lifted LIFT px so captions get the collar band
HEAD = dict(top=452, chin=760, cx=540, width=250)


def _json(path, fallback):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def guess_title(words):
    """First guess at a pinned title: the opening line as two short lines. The editing Claude should write a better
    one into plan.json ("title"); this only keeps a build from having an empty pill."""
    line = []
    for w in words:
        line.append(w['text'])
        if w['text'][-1:] in ',.?!' and len(line) >= 3 or len(line) >= 9:
            break
    line = [t.strip(',.?!;:') for t in line]
    best = min(range(1, len(line)), key=lambda k: abs(len(' '.join(line[:k])) - len(' '.join(line[k:])))) if len(line) > 1 else 1
    return ' '.join(line[:best]), ' '.join(line[best:])


def load(project):
    """Point the engine at one reel project. Sets the module values every style reads."""
    global HEAD_TOP, Y_ABOVE_HEAD, Y_CHEST, Y_LOWER, WALL_LEFT, WALL_RIGHT, TITLE, SWASH, VIDEO, CUTOUT, W, DUR
    global PROJECT, LAYOUT, PLAN, SEGS, FACELESS, LIFT, FILL, HEAD
    PROJECT = os.path.abspath(project)
    W = _json(os.path.join(PROJECT, 'words.json'), None)
    if not W:
        sys.exit('words.json is missing or empty: run transcribe_cut.py first.')
    video = os.path.join(PROJECT, 'assets', 'aroll.mp4')
    DUR = float(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                'stream=duration', '-of', 'csv=p=0', video], **skillenv.TEXT).stdout.strip().split(',')[0])
    CUTOUT = 'assets/subject.webm' if os.path.isfile(os.path.join(PROJECT, 'assets', 'subject.webm')) else None
    LAYOUT = _json(os.path.join(PROJECT, 'layout.json'), {})
    PLAN = _json(os.path.join(PROJECT, 'plan.json'), {})
    bands = {**DEFAULT_BANDS, **(LAYOUT.get('bands') or {})}
    HEAD_TOP, Y_ABOVE_HEAD, Y_CHEST, Y_LOWER = bands['HEAD_TOP'], bands['Y_ABOVE_HEAD'], bands['Y_CHEST'], bands['Y_LOWER']
    WALL_LEFT = tuple(bands['WALL_LEFT']) if bands.get('WALL_LEFT') else None
    WALL_RIGHT = tuple(bands['WALL_RIGHT']) if bands.get('WALL_RIGHT') else None
    FACELESS = bool(LAYOUT.get('faceless'))
    LIFT, FILL = int(LAYOUT.get('lift') or 0), LAYOUT.get('fill') or '#0d0d10'
    HEAD = {**HEAD, **(LAYOUT.get('head') or {})}
    SEGS = [(s['frame'] / 30, (s['frame'] + s['frames']) / 30) for s in _json(os.path.join(PROJECT, 'segments.json'), [])]
    SEGS = SEGS or [(0.0, DUR)]
    title = [t for t in (PLAN.get('title') or []) if t] or list(guess_title(W))
    TITLE = tuple((title + [''])[:2]) if len(title) < 2 else tuple(title[:2])
    swash = [t for t in (PLAN.get('swash') or []) if t] or [' '.join(x[:1].upper() + x[1:] for x in t.split()) for t in TITLE]
    SWASH = tuple((swash + [''])[:2])
    return LAYOUT


def head_top_at(t):
    """Head top during the segment that is on screen at time t (punch-ins move the head)."""
    for s in LAYOUT.get('segments') or []:
        if s['t0'] - .02 <= t < s['t1'] and s.get('head_top') is not None:
            return s['head_top'] - LIFT
    return HEAD_TOP


WEAK ={'the', 'a', 'an', 'to', 'of', 'and', 'that', 'for', 'can', 'in', 'on', 'with', 'is', 'my', 'your', 'then'}
PRONOUNS = {'i', 'you', 'we', 'he', 'she', 'they', 'it'}


def counted(i):
    """end index of what a number counts: up to two more words ("21 video effects"), never past punctuation, a marked
    word, a weak word or a pronoun ("3 things" stops before "I")"""
    j = i + 1
    while (j < len(W) and j - i < 3 and W[j - 1]['text'][-1] not in ',.?!' and not W[j].get('e')
           and W[j]['text'].rstrip(',.;:').lower() not in WEAK | PRONOUNS):
        j += 1
    return j


def T(t):
    """snap to the frame grid, 2ms early so a tl.set lands ON that frame"""
    return max(0.0, round(t * 30) / 30 - .002)


def esc(s):
    return html.escape(s, quote=False).replace("'", '&rsquo;')


def bare(s):
    return s.rstrip(',.;:')


def low(w):
    """lowercase a word for the lowercase styles, but leave names and I / I'll alone"""
    t = bare(w['text'])
    return t if w.get('e') == 'key' or t.split("'")[0] == 'I' else t.lower()


def chunk(words, max_words, max_chars, solo=()):
    """greedy phrases: break on length, on punctuation, on a pause; never leave a weak word dangling at the end"""
    groups, cur = [], []

    def flush(carry=True):
        nonlocal cur
        if not cur:
            return
        tail = []
        if carry and len(cur) > 1 and bare(cur[-1]['text']).lower() in WEAK and cur[-1]['text'][-1] not in ',.?!':
            tail = [cur.pop()]
        groups.append(cur)
        cur = tail

    for w in words:
        if w.get('e') in solo:
            flush(carry=False)
            groups.append([w])
            continue
        if cur:
            text = ' '.join(x['text'] for x in cur + [w])
            punct = cur[-1]['text'][-1] in ',.?!' and len(cur) >= 2
            pause = w['start'] - cur[-1]['end'] > .3
            if len(cur) >= max_words or len(text) > max_chars or punct or pause:
                flush(carry=not (punct or pause))
        cur.append(w)
    flush(carry=False)
    return groups


def windows(groups, hold=.35, gap=.6):
    """(group, t_in, t_out): a phrase stays up until the next one, or drops after a pause"""
    out = []
    for i, g in enumerate(groups):
        t0, end = g[0]['start'], g[-1]['end']
        if i + 1 < len(groups):
            nxt = groups[i + 1][0]['start']
            t1 = nxt if nxt - end <= gap else end + hold
        else:
            t1 = end + hold
        out.append((g, t0, t1))
    return out


class Build:
    def __init__(self):
        self.css, self.html, self.js, self.n = [], [], [], 0
        self.back, self.cutout = [], False      # back = layer BEHIND the speaker (needs assets/subject.webm)

    def nid(self, p='c'):
        self.n += 1
        return f'{p}{self.n}'

    def cut(self, sel, t_in, t_out=None):
        """hard cut in at t_in, hard cut out at t_out"""
        if t_in > .02:
            self.js.append(f"gsap.set('{sel}',{{autoAlpha:0}});")
            self.js.append(f"tl.set('{sel}',{{autoAlpha:1}},{T(t_in):.3f});")
        if t_out is not None and t_out < DUR - .02:
            self.js.append(f"tl.set('{sel}',{{autoAlpha:0}},{T(t_out):.3f});")

    def tween_in(self, sel, t_in, frm, to, dur, ease='power2.out'):
        self.js.append(f"gsap.set('{sel}',{{autoAlpha:0}});")
        self.js.append(f"tl.fromTo('{sel}',{json.dumps({'autoAlpha': 0, **frm})},"
                       f"{json.dumps({'autoAlpha': 1, **to, 'duration': dur, 'ease': ease, 'immediateRender': False})},{T(t_in):.3f});")

    def out(self, sel, t_out, fade=0):
        if t_out >= DUR - .02:
            return
        if fade:
            self.js.append(f"tl.to('{sel}',{{autoAlpha:0,duration:{fade}}},{max(0, T(t_out) - fade):.3f});")
        self.js.append(f"tl.set('{sel}',{{autoAlpha:0}},{T(t_out):.3f});")


BASE_CSS = '''
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;background:#000;overflow:hidden}
#root{position:relative;width:1080px;height:1920px;overflow:hidden}
.full{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}
.cap{position:absolute;left:0;width:1080px;text-align:center;white-space:nowrap}
'''


# ----------------------------------------------------------------------------------------------------------------------
# 01 ARCADE: pixel type, short phrases, hard cuts, the comment keyword twice the size in quotes
# ----------------------------------------------------------------------------------------------------------------------
def arcade(b):
    b.css.append(f'''
.ar{{top:{Y_CHEST + 82}px;font-family:'Pixelify Sans';font-weight:600;font-size:68px;line-height:76px;color:#fff;
  text-shadow:0 4px 0 rgba(0,0,0,.3),0 0 22px rgba(0,0,0,.5)}}
.ar.big{{top:{Y_CHEST + 150}px;font-weight:700;font-size:140px;line-height:140px}}''')
    wins = windows(chunk(W, 3, 16, solo=('cta',)))
    for i, (g, t0, t1) in enumerate(wins):
        i_d = b.nid()
        if g[0].get('e') == 'cta':
            b.html.append(f'<div id="{i_d}" class="cap ar big">&ldquo;{esc(bare(g[0]["text"]).capitalize())}&rdquo;</div>')
            b.cut(f'#{i_d}', t0, t1)
            continue
        if i + 1 < len(wins) and wins[i + 1][0][0].get('e') == 'cta':
            t1 = wins[i + 1][2]                    # "comment" stays up while the keyword lands under it
        b.html.append(f'<div id="{i_d}" class="cap ar">{esc(" ".join(w["text"] for w in g))}</div>')
        b.cut(f'#{i_d}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 02 LOW KEY: tiny quiet captions that build one word at a time, under a pinned title pill
# ----------------------------------------------------------------------------------------------------------------------
def lowkey(b):
    b.css.append(f'''
.lk{{top:{Y_CHEST + 120}px;font-family:'Figtree';font-weight:600;font-size:42px;line-height:52px;color:#fff;
  text-shadow:0 2px 10px rgba(0,0,0,.6),0 0 2px rgba(0,0,0,.35)}}
.lkh{{position:absolute;left:0;width:1080px;top:246px;display:flex;flex-direction:column;align-items:center}}
.lkh span{{background:#fff;color:#141414;font-family:'Barlow Condensed';font-weight:500;font-size:52px;line-height:68px;
  padding:0 24px 2px;border-radius:17px;margin-top:-7px;letter-spacing:-.005em}}''')
    b.html.append('<div class="lkh">' + ''.join(f'<span>{esc(t)}</span>' for t in TITLE if t) + '</div>')
    for g, t0, t1 in windows(chunk(W, 3, 15)):
        gid = b.nid()
        parts = []
        for k, w in enumerate(g):
            wid = b.nid('w')
            parts.append(f'<span id="{wid}">{esc(w["text"])}</span>')
            if k:
                b.cut(f'#{wid}', w['start'])
        b.html.append(f'<div id="{gid}" class="cap lk">{" ".join(parts)}</div>')
        b.cut(f'#{gid}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 03 FIELD NOTES: a quiet book serif, whole phrases, soft fades, each one placed in a different open part of the frame
# ----------------------------------------------------------------------------------------------------------------------
def fieldnotes(b):
    b.css.append(f'''
.fn{{position:absolute;font-family:'Newsreader';font-weight:400;font-size:48px;line-height:58px;color:#fff;text-wrap:balance;
  text-shadow:0 1px 18px rgba(0,0,0,.7),0 0 6px rgba(0,0,0,.6),0 1px 2px rgba(0,0,0,.45)}}
.fn.b{{left:0;width:1080px;top:{Y_CHEST + 96}px;text-align:center}}''')
    # a wall spot is only used when the clip has open room on that side (layout.json); otherwise the phrase goes to the chest
    spots = ''
    for cls, wall in (('a', WALL_LEFT), ('b', True), ('c', WALL_RIGHT)):
        if wall:
            spots += cls
            if cls != 'b':
                b.css.append(f'\n.fn.{cls}{{left:{wall[0]}px;top:{wall[1]}px;width:{wall[2]}px;text-align:left}}')
    for i, (g, t0, t1) in enumerate(windows(chunk(W, 6, 28))):
        i_d = b.nid()
        b.html.append(f'<div id="{i_d}" class="fn {spots[i % len(spots)]}">{esc(" ".join(w["text"] for w in g))}</div>')
        b.tween_in(f'#{i_d}', t0, {'filter': 'blur(7px)'}, {'filter': 'blur(0px)'}, .34, 'power1.out')
        b.out(f'#{i_d}', t1 + .1, fade=.24)


# ----------------------------------------------------------------------------------------------------------------------
# 04 ANCHOR: bold clean sans pinned in one spot, hard cuts; the number and the key word take over the frame with a glow
# ----------------------------------------------------------------------------------------------------------------------
def anchor(b):
    b.css.append(f'''
.an{{top:{Y_CHEST + 40}px;font-family:'Inter Tight';font-weight:800;font-size:60px;line-height:68px;letter-spacing:-.012em;color:#fff;
  text-shadow:0 2px 14px rgba(0,0,0,.65),0 0 2px rgba(0,0,0,.4)}}
.an i{{display:block;font-weight:500;font-style:italic;font-size:44px;line-height:52px;letter-spacing:0}}
.an.num{{top:{Y_CHEST - 60}px;font-size:230px;line-height:230px;letter-spacing:-.04em;
  text-shadow:0 0 34px rgba(255,255,255,.7),0 0 6px rgba(255,255,255,.55)}}
.an.serif{{top:{Y_CHEST - 40}px;font-family:'Playfair Display';font-weight:500;font-style:italic;font-size:150px;line-height:190px;
  letter-spacing:-.03em;text-shadow:0 0 30px rgba(255,255,255,.75),0 0 6px rgba(255,255,255,.5)}}''')
    for g, t0, t1 in windows(chunk(W, 3, 16, solo=('num', 'emph'))):
        i_d = b.nid()
        kind = g[0].get('e') if len(g) == 1 else None
        if kind in ('num', 'emph'):
            cls = 'num' if kind == 'num' else 'serif'
            b.html.append(f'<div id="{i_d}" class="cap an {cls}">{esc(bare(g[0]["text"]))}</div>')
            b.tween_in(f'#{i_d}', t0, {'scale': 1.14, 'filter': 'blur(10px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .2)
            b.out(f'#{i_d}', t1)
            continue
        main = [w for w in g if w.get('e') != 'cta']
        cta = [w for w in g if w.get('e') == 'cta']
        sub = ''
        if cta:
            sid = b.nid('s')
            sub = f'<i id="{sid}">&ldquo;{esc(bare(cta[0]["text"]))}&rdquo;</i>'
            b.cut(f'#{sid}', cta[0]['start'])
        b.html.append(f'<div id="{i_d}" class="cap an">{esc(" ".join(w["text"] for w in main))}{sub}</div>')
        b.cut(f'#{i_d}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 05 LOUD LOWERCASE: huge tight lowercase, one word at a time; the number and what it counts park top-left as a title
# ----------------------------------------------------------------------------------------------------------------------
def loud(b):
    b.css.append(f'''
.ld{{font-family:'Arimo';font-weight:700;letter-spacing:-.085em;color:#fff;text-shadow:0 4px 26px rgba(0,0,0,.28)}}
.ld.w{{top:{Y_CHEST - 6}px;line-height:170px;height:170px}}
.ldt{{position:absolute;left:44px;top:214px;white-space:nowrap;display:flex;align-items:flex-start;gap:26px}}
#ldn{{font-size:290px;line-height:250px}}
.ldt .col{{padding-top:38px}}
.ldt .s{{font-size:104px;line-height:92px}}''')
    # the title: the number plus the next two words, held until the sentence ends
    ni = next((i for i, w in enumerate(W) if w.get('e') == 'num'), None)
    title, t_end = set(), 0
    if ni is not None:
        title = set(range(ni, counted(ni)))
        t_end = next((w['end'] for w in W[ni:] if w['text'][-1] in ',.?!'), W[-1]['end']) + .1
        rows = []
        for j in sorted(title - {ni}):
            i_d = b.nid('t')
            rows.append(f'<div id="{i_d}" class="s">{esc(bare(W[j]["text"]).lower())}</div>')
            b.cut(f'#{i_d}', W[j]['start'])
        b.html.append(f'<div id="ldw" class="ldt ld"><div id="ldn">{esc(W[ni]["text"])}</div><div class="col">{"".join(rows)}</div></div>')
        b.cut('#ldw', W[ni]['start'], t_end)
    for i, w in enumerate(W):
        if i in title:
            continue
        txt = bare(w['text'])
        txt = txt.upper() if w.get('e') == 'cta' else txt.lower()
        per = .66 if w.get('e') == 'cta' else .475
        size = min(190 if w.get('e') == 'cta' else 160, int(900 / (max(len(txt), 2) * per)))
        nxt = next((W[j]['start'] for j in range(i + 1, len(W)) if j not in title), None)
        t1 = nxt if nxt is not None and nxt - w['end'] <= .6 else w['end'] + .35
        i_d = b.nid()
        b.html.append(f'<div id="{i_d}" class="cap ld w" style="font-size:{size}px">{esc(txt)}</div>')
        b.cut(f'#{i_d}', w['start'], t1)


# ----------------------------------------------------------------------------------------------------------------------
# 06 VANITY: a tall display serif in butter cream, one word at a time, the words that matter flip to yellow italic,
#            a small icon rides along with the thing being named
# ----------------------------------------------------------------------------------------------------------------------
ICON_BURST = ('<svg class="vi" viewBox="-50 -50 100 100"><g stroke="#E9774F" stroke-width="13" stroke-linecap="round">'
              + ''.join(f'<line x1="0" y1="0" x2="0" y2="-42" transform="rotate({a})"/>' for a in range(0, 360, 45))
              + '</g></svg>')
ICON_BUBBLE = ('<svg class="vi" viewBox="0 0 100 100"><path d="M50 12c24 0 42 15 42 34S74 80 50 80c-5 0-10-.6-14-1.8L16 90l5-19C12 64 8 56 8 46 8 27 26 12 50 12z" '
               'fill="#fff"/><circle cx="33" cy="47" r="6" fill="#262626"/><circle cx="50" cy="47" r="6" fill="#262626"/>'
               '<circle cx="67" cy="47" r="6" fill="#262626"/></svg>')


def vanity(b):
    b.css.append(f'''
.vn{{top:{Y_CHEST + 30}px;font-family:'Instrument Serif';font-weight:400;font-size:104px;line-height:120px;color:#FFF4BE;
  -webkit-text-stroke:.7px #FFF4BE;text-shadow:0 3px 0 rgba(70,48,0,.32),0 0 26px rgba(0,0,0,.6)}}
.vn.em{{font-style:italic;font-size:122px;color:#FFE25F;-webkit-text-stroke:1.1px #FFE25F}}
.vi{{display:inline-block;width:84px;height:84px;vertical-align:-8px;margin-right:18px;filter:drop-shadow(0 4px 12px rgba(0,0,0,.45))}}''')
    for i, w in enumerate(W):
        t1 = W[i + 1]['start'] if i + 1 < len(W) and W[i + 1]['start'] - w['end'] <= .6 else w['end'] + .35
        em = w.get('e')
        txt = esc(w['text'])
        icon = ''
        if em == 'key':
            icon = ICON_BURST
        elif em == 'cta':
            txt = f'&ldquo;{esc(bare(w["text"]))}&rdquo;'
        elif bare(w['text']).lower() == 'comment':
            icon = ICON_BUBBLE
        i_d = b.nid()
        b.html.append(f'<div id="{i_d}" class="cap vn{" em" if em else ""}">{icon}{txt}</div>')
        b.cut(f'#{i_d}', w['start'], t1)


# ----------------------------------------------------------------------------------------------------------------------
# 07 BUBBLEGUM: one airy pink word at a time floating over the head, under a swashy pink title
# ----------------------------------------------------------------------------------------------------------------------
STAR = '<svg class="st" viewBox="0 0 100 100"><path d="M50 0C54 30 70 46 100 50 70 54 54 70 50 100 46 70 30 54 0 50 30 46 46 30 50 0z" fill="currentColor"/></svg>'


def bubblegum(b):
    # no room above the head (layout.json says so with Y_ABOVE_HEAD null): the word floats over the chest instead
    y_word = (Y_ABOVE_HEAD if Y_ABOVE_HEAD is not None else Y_CHEST) + 14
    b.css.append(f'''
.bg{{top:{y_word}px;font-family:'Arimo';font-weight:400;font-size:100px;line-height:104px;letter-spacing:-.065em;color:#FFE0EF;
  text-shadow:0 0 16px rgba(255,105,180,.85),0 0 3px rgba(240,80,160,.95),0 2px 12px rgba(120,20,70,.35)}}
#bgt{{position:absolute;left:0;width:1080px;top:228px;text-align:center;font-family:'Elsie Swash Caps';font-weight:900;
  font-size:66px;line-height:68px;letter-spacing:.01em;color:#F8BBD8;-webkit-text-stroke:2.4px #B4517F;paint-order:stroke fill;
  text-shadow:0 3px 0 rgba(120,40,85,.55),0 0 18px rgba(0,0,0,.3)}}
#bgt .st{{display:inline-block;width:38px;height:38px;margin:0 18px;vertical-align:0;color:#FFE9F4;filter:drop-shadow(0 0 6px rgba(255,105,180,.9))}}''')
    l1, l2 = SWASH
    b.html.append(f'<div id="bgt">{STAR}{esc(l1)}{STAR}{"<br>" + esc(l2) if l2 else ""}</div>')
    b.js.append("tl.fromTo('#bgt',{autoAlpha:0,filter:'blur(14px)',scale:1.06},{autoAlpha:1,filter:'blur(0px)',scale:1,duration:.4,ease:'power2.out',immediateRender:false},0);")
    gsap_hidden = "gsap.set('#bgt',{autoAlpha:0});"
    b.js.insert(len(b.js) - 1, gsap_hidden)
    for i, w in enumerate(W):
        t1 = W[i + 1]['start'] if i + 1 < len(W) and W[i + 1]['start'] - w['end'] <= .6 else w['end'] + .35
        i_d = b.nid()
        b.html.append(f'<div id="{i_d}" class="cap bg">{esc(low(w))}</div>')
        b.cut(f'#{i_d}', w['start'], t1)


# ----------------------------------------------------------------------------------------------------------------------
# 08 MOODBOARD: a bold rounded title line with a thin italic line typed out under it, little sparkles around the block
# ----------------------------------------------------------------------------------------------------------------------
def moodboard(b):
    b.css.append(f'''
.mb{{position:absolute;left:0;width:1080px;top:{Y_CHEST + 56}px;text-align:center;white-space:nowrap;color:#fff}}
.mb .t{{font-family:'Poppins';font-weight:700;font-size:56px;line-height:66px;letter-spacing:-.012em;text-shadow:0 2px 16px rgba(0,0,0,.5)}}
.mb .s{{font-family:'Instrument Serif';font-style:italic;font-size:62px;line-height:64px;letter-spacing:-.01em;text-shadow:0 2px 14px rgba(0,0,0,.6)}}
.mb .s u{{display:inline-block;width:0;text-decoration:none;overflow:visible}}
.mb .box{{display:inline-block;position:relative}}
.mb .st{{position:absolute;color:#fff;filter:drop-shadow(0 0 5px rgba(255,255,255,.55))}}''')
    # two phrases per card, never across a sentence: the first goes bold, the second is typed out in italic
    sents, cur = [], []
    for w in W:
        cur.append(w)
        if w['text'][-1] in '.?!':
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    pairs = []
    for s in sents:
        ph = chunk(s, 6, 28)
        if len(ph) > 1 and len(ph[0]) == 1:          # a lone lead-in word ("Okay,") rides with the next phrase
            ph = [ph[0] + ph[1]] + ph[2:]
        pairs += [(ph[p], ph[p + 1] if p + 1 < len(ph) else []) for p in range(0, len(ph), 2)]
    for n, (top, sub) in enumerate(pairs):
        card = b.nid('m')
        t0 = top[0]['start']
        last = (sub or top)[-1]['end']
        nxt = pairs[n + 1][0][0]['start'] if n + 1 < len(pairs) else None
        t1 = nxt if nxt is not None and nxt - last <= .6 else last + .4
        chars = []
        for w in sub:
            txt = (' ' if chars else '') + low(w)
            step = (w['end'] - w['start']) / max(len(txt), 1)
            for k, ch in enumerate(txt):
                chars.append((ch, w['start'] + k * step))
        spans = []
        for k, (ch, t) in enumerate(chars):
            cid, uid = b.nid('h'), b.nid('u')
            spans.append(f'<span id="{cid}">{esc(ch)}</span><u id="{uid}">_</u>')
            b.cut(f'#{cid}', max(t, .03))
            t_next = chars[k + 1][1] if k + 1 < len(chars) else t + .5
            b.cut(f'#{uid}', max(t, .03), t_next)
        title = ' '.join(low(w) for w in top)
        b.html.append(
            f'<div id="{card}" class="mb"><div class="box"><div class="t" style="font-size:{min(56, int(740 / (max(len(title), 1) * .6)))}px">{esc(title)}</div><div class="s">{"".join(spans)}</div>'
            f'<span class="st" style="right:-52px;top:-44px;width:44px;height:44px">{STAR}</span>'
            f'<span class="st" style="right:-84px;top:-8px;width:22px;height:22px">{STAR}</span>'
            f'<span class="st" style="left:-58px;top:40px;width:30px;height:30px">{STAR}</span></div></div>')
        b.tween_in(f'#{card}', t0, {'y': 10}, {'y': 0}, .18)
        b.out(f'#{card}', t1)


# ----------------------------------------------------------------------------------------------------------------------
# 09 GOLDEN HOUR: film subtitles. Gold italic serif, a hard little drop shadow, whole phrases low in the frame
# ----------------------------------------------------------------------------------------------------------------------
def golden(b):
    b.css.append(f'''
.gh{{top:{Y_LOWER}px;font-family:'Newsreader';font-weight:500;font-style:italic;font-size:62px;line-height:76px;letter-spacing:-.005em;
  color:#F8CB45;text-shadow:3px 3px 0 rgba(26,15,0,.68),0 0 18px rgba(0,0,0,.35)}}''')
    for g, t0, t1 in windows(chunk(W, 6, 28)):
        i_d = b.nid()
        txt = ' '.join(f'&ldquo;{esc(bare(w["text"]))}&rdquo;' if w.get('e') == 'cta' else esc(w['text']) for w in g)
        b.html.append(f'<div id="{i_d}" class="cap gh">{txt}</div>')
        b.cut(f'#{i_d}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 10 SPEC SHEET: small wide caps snapping in dead centre, plus big tilted yellow tags for the number and the keyword
# ----------------------------------------------------------------------------------------------------------------------
def specsheet(b):
    b.css.append(f'''
.ss{{top:{Y_CHEST - 30}px;font-family:'Archivo';font-stretch:125%;font-weight:900;font-size:46px;line-height:54px;letter-spacing:.012em;
  text-transform:uppercase;color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.6),0 0 2px rgba(0,0,0,.4)}}
.tag{{position:absolute;left:58px;top:244px;transform-origin:0 50%;transform:perspective(1100px) rotateY(24deg) rotateZ(-6deg);
  font-family:'Archivo';font-stretch:125%;font-weight:900;text-transform:uppercase;color:#FFEB00;white-space:nowrap;
  text-shadow:0 0 28px rgba(255,235,0,.5),0 4px 14px rgba(0,0,0,.35)}}
.tag .k{{font-size:34px;line-height:40px;letter-spacing:.02em}}
.tag .v{{font-size:150px;line-height:136px;letter-spacing:-.02em}}''')

    def tag(small, big, t0, t1):
        wrap, i_d = b.nid('g'), b.nid('g')
        b.html.append(f'<div id="{wrap}"><div id="{i_d}" class="tag"><div class="k">{esc(small)}</div><div class="v">{esc(big)}</div></div></div>')
        b.tween_in(f'#{wrap}', t0, {'x': -70, 'filter': 'blur(12px)'}, {'x': 0, 'filter': 'blur(0px)'}, .2, 'power3.out')
        b.out(f'#{wrap}', t1)

    ni = next((i for i, w in enumerate(W) if w.get('e') == 'num'), None)
    if ni is not None:
        t_end = next((w['end'] for w in W[ni:] if w['text'][-1] in ',.?!'), W[-1]['end']) + .1
        tag(' '.join(bare(w['text']) for w in W[ni + 1:counted(ni)]), W[ni]['text'], W[ni]['start'], t_end)
    ci = next((i for i, w in enumerate(W) if w.get('e') == 'cta'), None)
    if ci is not None:
        tag(bare(W[ci - 1]['text']) if ci else 'comment', bare(W[ci]['text']), W[ci]['start'], DUR)
    for g, t0, t1 in windows(chunk(W, 2, 14)):
        i_d = b.nid()
        b.html.append(f'<div id="{i_d}" class="cap ss">{esc(" ".join(bare(w["text"]) for w in g))}</div>')
        b.tween_in(f'#{i_d}', t0, {'x': -34, 'scaleX': 1.22, 'filter': 'blur(9px)'}, {'x': 0, 'scaleX': 1, 'filter': 'blur(0px)'}, .1, 'power2.out')
        b.out(f'#{i_d}', t1)


# ======================================================================================================================
# 11 to 16: the looks that came first, ported onto the same engine
# ======================================================================================================================
def spans(b, words, text=None, pop=None):
    """word spans that show on their spoken frame (the first one is up when its parent shows)"""
    out = []
    for k, w in enumerate(words):
        wid = b.nid('w')
        cls = ' class="y"' if w.get('e') else ''
        out.append(f'<span id="{wid}"{cls}>{esc((text or low)(w))}</span>')
        if pop:
            b.tween_in(f'#{wid}', w['start'], *pop)
        elif k:
            b.cut(f'#{wid}', w['start'])
    return ' '.join(out)


def cards(extend_num):
    """cards of (before, punch, after) built around each num / emph / cta word: one punch per line of thought"""
    idx = [i for i, w in enumerate(W) if w.get('e') in ('num', 'emph', 'cta')]
    if not idx:
        return [dict(before=g, punch=[], after=[]) for g in chunk(W, 6, 28)]
    out, start = [], 0
    for k, p in enumerate(idx):
        end = p + 1
        if extend_num and W[p].get('e') == 'num':        # a number takes what it counts with it: "21 video effects"
            end = counted(p)
            while end > p + 1 and len(' '.join(w['text'] for w in W[p:end])) > 16:
                end -= 1
        nxt = idx[k + 1] if k + 1 < len(idx) else len(W)
        stop = next((j + 1 for j in range(end - 1, len(W)) if W[j]['text'][-1] in ',.?!'), len(W))
        after_end = len(W) if k + 1 == len(idx) else (stop if stop <= nxt else end)
        out.append(dict(before=W[start:p], punch=W[p:end], after=W[end:after_end]))
        start = after_end
    return out


def card_times(cs):
    t0s = [(c['before'] or c['punch'])[0]['start'] for c in cs]
    for i, c in enumerate(cs):
        last = (c['after'] or c['punch'] or c['before'])[-1]['end']
        c['t0'] = t0s[i]
        c['t1'] = t0s[i + 1] if i + 1 < len(cs) and t0s[i + 1] - last <= .6 else last + .4
    return cs


# ----------------------------------------------------------------------------------------------------------------------
# 11 BOLD: heavy tight lowercase over the chest, and the words that matter go giant BEHIND the head
# ----------------------------------------------------------------------------------------------------------------------
def bold(b):
    b.cutout = bool(CUTOUT) and not FACELESS
    b.css.append(f'''
.dw{{position:absolute;left:0;width:1080px;text-align:center;color:#fff;font-family:'Inter Tight';font-weight:900;letter-spacing:-.05em;
  line-height:.9;text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35);white-space:nowrap;transform-origin:50% 60%}}
.dw span{{display:inline-block;margin:0 .1em;transform-origin:50% 60%}}
.dw.sm{{top:{Y_CHEST + 50}px;font-size:84px;font-weight:800;letter-spacing:-.04em}}
.dw.y{{color:#FAE67A}}''')
    for g, t0, t1 in windows(chunk(W, 3, 16, solo=('num', 'emph', 'cta'))):
        i_d = b.nid()
        if len(g) == 1 and g[0].get('e') in ('num', 'emph', 'cta'):
            txt = low(g[0])
            per = .6 if txt.isdigit() else .47
            size = min(300 if len(txt) <= 3 else 260, int(940 / (len(txt) * per)))
            cls = '' if g[0].get('e') == 'num' else ' y'
            head = head_top_at(t0)
            # the word has to fit between the safe line (y 226) and the head with only its bottom ~28% tucked behind
            # the head: top = head - .6084 * size. Less room means a smaller word; no room at all (or no cutout)
            # means the word lands big over the chest, in front, instead.
            size = min(size, int((head - 226) / .6084)) if b.cutout else 0
            if size < 110:
                front = min(150, int(900 / (len(txt) * per)))
                b.html.append(f'<div id="{i_d}" class="dw sm{cls}" style="top:{Y_CHEST + 20}px;font-size:{front}px;font-weight:900">{esc(txt)}</div>')
                b.tween_in(f'#{i_d}', t0, {'scale': 1.22, 'filter': 'blur(22px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .2, 'power3.out')
                b.out(f'#{i_d}', t1, fade=.12)
                continue
            glyph = .72 * size
            top = max(226, head + .28 * glyph - glyph - .09 * size)     # only the bottom ~28% tucks behind the head
            b.back.append(f'<div id="{i_d}" class="dw{cls}" style="top:{top:.0f}px;font-size:{size}px">{esc(txt)}</div>')
            b.tween_in(f'#{i_d}', t0, {'scale': 1.22, 'filter': 'blur(22px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .2, 'power3.out')
            b.out(f'#{i_d}', t1, fade=.12)
            continue
        body = spans(b, g, pop=({'scale': 1.22, 'filter': 'blur(14px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .18, 'power3.out'))
        b.html.append(f'<div id="{i_d}" class="dw sm">{body}</div>')
        b.cut(f'#{i_d}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 12 COOL GIRL: small calm lowercase, one big butter-yellow serif italic line per thought, sparkles
# ----------------------------------------------------------------------------------------------------------------------
def coolgirl(b):
    b.css.append(f'''
.gc{{position:absolute;left:110px;width:860px;top:{Y_CHEST - 40}px;text-align:center;color:#FFF8EF;text-shadow:0 2px 26px rgba(60,30,20,.55)}}
.gc .s{{font-family:'Inter';font-weight:500;font-size:60px;line-height:70px;letter-spacing:-1px;text-wrap:balance}}
.gc .e{{position:relative;display:inline-block;font-family:'Instrument Serif';font-style:italic;line-height:.92;color:#FAE67A;
  white-space:nowrap;margin:4px 0 10px;transform-origin:50% 60%}}
.gc .st{{position:absolute;color:#FAE67A;filter:drop-shadow(0 0 8px rgba(250,230,122,.6))}}''')
    for c in card_times(cards(extend_num=True)):
        card = b.nid('g')
        parts = []
        if c['before']:
            parts.append(f'<div class="s">{spans(b, c["before"])}</div>')
        if c['punch']:
            pid = b.nid('p')
            txt = ' '.join(f'&ldquo;{esc(low(w))}&rdquo;' if w.get('e') == 'cta' else esc(low(w)) for w in c['punch'])
            size = min(150, int(850 / (len(' '.join(w['text'] for w in c['punch'])) * .36)))
            parts.append(f'<div><div id="{pid}" class="e" style="font-size:{size}px">{txt}'
                         f'<span class="st" style="right:-44px;top:-6px;width:38px;height:38px">{STAR}</span>'
                         f'<span class="st" style="left:-58px;top:18px;width:28px;height:28px">{STAR}</span></div></div>')
            t = c['punch'][0]['start']
            if c['before']:
                b.tween_in(f'#{pid}', t, {'scale': .86, 'filter': 'blur(10px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .28, 'back.out(1.6)')
        if c['after']:
            aid = b.nid('a')
            parts.append(f'<div id="{aid}" class="s">{spans(b, c["after"])}</div>')
            b.cut(f'#{aid}', c['after'][0]['start'])
        b.html.append(f'<div id="{card}" class="gc">{"".join(parts)}</div>')
        b.cut(f'#{card}', c['t0'], c['t1'])


# ----------------------------------------------------------------------------------------------------------------------
# 13 COOL DUDE: tiny wide-tracked caps, heavy serif punch words whose letters rise out of a mask
# ----------------------------------------------------------------------------------------------------------------------
def cooldude(b):
    b.css.append(f'''
.cd{{position:absolute;left:100px;width:880px;top:{Y_CHEST - 70}px;text-align:center;color:#F7F4EE}}
.cd .t{{font-family:'Montserrat';font-weight:500;font-size:34px;line-height:50px;text-transform:uppercase;text-wrap:balance;
  text-shadow:0 2px 12px rgba(0,0,0,.6)}}
.cd .t span{{display:inline-block;letter-spacing:.32em;margin:0 .1em;transform-origin:50% 50%;color:#F7F4EE}}
.cd .p{{font-family:'DM Serif Display';line-height:1.12;letter-spacing:-.02em;white-space:nowrap;text-shadow:0 12px 40px rgba(0,0,0,.45)}}
.cd .mk{{display:inline-block;overflow:hidden;padding:0 .02em .14em;margin-bottom:-.14em;vertical-align:bottom}}
.cd .ch{{display:inline-block}}''')
    track = ({'scaleX': 1.45, 'filter': 'blur(6px)'}, {'scaleX': 1, 'filter': 'blur(0px)'}, .22, 'power2.out')
    cs = card_times(cards(extend_num=False))
    for n, c in enumerate(cs):
        card = b.nid('g')
        parts = []
        if c['before']:
            parts.append(f'<div class="t">{spans(b, c["before"], text=lambda w: bare(w["text"]), pop=track)}</div>')
        if c['punch']:
            txt = ' '.join(low(w) for w in c['punch'])
            size = min(230, int(860 / (len(txt) * .47)))
            ital = ';font-style:italic' if n == len(cs) - 1 else ''
            chars = ''.join('&nbsp;' if ch == ' ' else f'<span class="mk"><span class="ch">{esc(ch)}</span></span>' for ch in txt)
            parts.append(f'<div class="p" style="font-size:{size}px{ital}">{chars}</div>')
            b.js.append(f"gsap.set('#{card} .ch',{{yPercent:115}});")
            b.js.append(f"tl.to('#{card} .ch',{{yPercent:0,duration:.5,ease:'expo.out',stagger:.028}},{T(c['punch'][0]['start']):.3f});")
        if c['after']:
            parts.append(f'<div class="t">{spans(b, c["after"], text=lambda w: bare(w["text"]), pop=track)}</div>')
        b.html.append(f'<div id="{card}" class="cd">{"".join(parts)}</div>')
        b.cut(f'#{card}', c['t0'], c['t1'])


# ----------------------------------------------------------------------------------------------------------------------
# 14 KARAOKE: wide caps on a frosted dark plate, the word being said lights up and pops
# ----------------------------------------------------------------------------------------------------------------------
def karaoke(b):
    on, off = '#FAE67A', '#F4EDE0'
    b.css.append(f'''
.kk{{top:{Y_CHEST + 96}px}}
.kk .plate{{display:inline-flex;gap:0 26px;padding:20px 36px 22px;border-radius:26px;background:rgba(21,21,23,.62);
  backdrop-filter:blur(18px) saturate(140%);-webkit-backdrop-filter:blur(18px) saturate(140%);border:1px solid rgba(244,237,224,.12);
  box-shadow:0 18px 50px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.08)}}
.kk .w{{display:inline-block;font-family:'Archivo';font-stretch:125%;font-weight:900;font-size:66px;line-height:70px;letter-spacing:.01em;
  text-transform:uppercase;color:{off};text-shadow:0 3px 14px rgba(0,0,0,.5);transform-origin:50% 60%}}''')
    for g, t0, t1 in windows(chunk(W, 3, 13)):
        gid = b.nid()
        ws = []
        for k, w in enumerate(g):
            wid = b.nid('w')
            ws.append(f'<span id="{wid}" class="w"{f" style=&quot;color:{on}&quot;".replace("&quot;", chr(34)) if k == 0 else ""}>{esc(bare(w["text"]))}</span>')
            if k:
                b.js.append(f"tl.set('#{wid}',{{color:'{on}'}},{T(w['start']):.3f});")
                b.js.append(f"tl.fromTo('#{wid}',{{scale:1.2}},{{scale:1,duration:.22,ease:'back.out(2.2)',immediateRender:false}},{T(w['start']):.3f});")
            if k + 1 < len(g):
                b.js.append(f"tl.set('#{wid}',{{color:'{off}'}},{T(g[k + 1]['start']):.3f});")
        b.html.append(f'<div id="{gid}" class="cap kk"><div class="plate">{"".join(ws)}</div></div>')
        b.cut(f'#{gid}', t0, t1)


# ----------------------------------------------------------------------------------------------------------------------
# 15 SIGNATURE: clean wide white caps, and on the big moments a white marker script signs over heavy cream italic caps
# ----------------------------------------------------------------------------------------------------------------------
def signature(b):
    b.css.append(f'''
.sg{{top:{Y_CHEST + 70}px;font-family:'Archivo';font-stretch:125%;font-weight:900;font-size:48px;line-height:56px;letter-spacing:.03em;
  text-transform:uppercase;color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.6),0 0 2px rgba(0,0,0,.4)}}
.sa{{position:absolute;left:0;width:1080px;top:{Y_CHEST - 76}px;text-align:center;filter:drop-shadow(0 8px 22px rgba(0,0,0,.5))}}
.sa .scr{{position:relative;z-index:2;font-family:'Marck Script';font-size:128px;line-height:128px;color:#fff;-webkit-text-stroke:2px #fff;
  white-space:nowrap;transform:rotate(-5deg);margin-bottom:-34px}}
.sa .scr span{{display:inline-block}}
.sa .cps{{font-family:'Archivo';font-style:italic;font-stretch:125%;font-weight:900;line-height:.95;letter-spacing:-.02em;text-transform:uppercase;
  color:#F5D9BF;white-space:nowrap}}
.sa .cps span{{display:inline-block;transform-origin:50% 60%}}''')
    acc = []                                   # (first index, end index, script words, caps words)
    for i, w in enumerate(W):
        if i and w.get('e') == 'num':
            j = counted(i)
            acc.append((i - 1, j, W[i - 1:i + 1], W[i + 1:j]) if j > i + 1 else (i - 1, i + 1, W[i - 1:i], W[i:i + 1]))
        elif i and w.get('e') == 'cta':
            acc.append((i - 1, i + 1, W[i - 1:i], W[i:i + 1]))
    items, pos = [], 0
    for a in acc + [(len(W), len(W), [], [])]:
        items += [('cap', g) for g in chunk(W[pos:a[0]], 3, 16)]
        if a[2]:
            items.append(('acc', a))
        pos = a[1]
    first = [(it[1][0] if it[0] == 'cap' else it[1][2][0])['start'] for it in items]
    for n, (kind, it) in enumerate(items):
        last = (it[-1] if kind == 'cap' else it[3][-1])['end']
        t1 = first[n + 1] if n + 1 < len(items) and first[n + 1] - last <= .6 else last + .35
        i_d = b.nid()
        if kind == 'cap':
            b.html.append(f'<div id="{i_d}" class="cap sg">{esc(" ".join(bare(w["text"]) for w in it))}</div>')
            b.cut(f'#{i_d}', first[n], t1)
            continue
        caps = ' '.join(bare(w['text']) for w in it[3])
        size = min(150, int(900 / (len(caps) * .82)))
        pop = ({'scale': .8}, {'scale': 1}, .24, 'back.out(2)')
        b.html.append(f'<div id="{i_d}" class="sa"><div class="scr">{spans(b, it[2], pop=({"x": -26}, {"x": 0}, .22, "power3.out"))}</div>'
                      f'<div class="cps" style="font-size:{size}px">{spans(b, it[3], text=lambda w: bare(w["text"]), pop=pop)}</div></div>')
        b.cut(f'#{i_d}', first[n], t1)


# ----------------------------------------------------------------------------------------------------------------------
# 16 KEYWORD: one clean tight lowercase line, the word that matters in yellow; a key word alone goes bigger
# ----------------------------------------------------------------------------------------------------------------------
def keyword(b):
    b.css.append(f'''
.kw{{position:absolute;left:70px;right:70px;top:{Y_CHEST - 40}px;text-align:center;font-family:'Inter Tight';font-weight:800;font-size:76px;
  line-height:1;letter-spacing:-.045em;color:#fff;text-shadow:0 8px 30px rgba(0,0,0,.6),0 2px 6px rgba(0,0,0,.4);white-space:nowrap}}
.kw.big{{font-size:104px;top:{Y_CHEST - 56}px;font-weight:900}}
.kw span{{display:inline-block;margin:0 .1em;transform-origin:50% 60%}}
.kw .y{{color:#FAE67A}}''')
    pop = ({'scale': 1.16, 'filter': 'blur(10px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .16, 'power3.out')
    for g, t0, t1 in windows(chunk(W, 3, 16)):
        i_d = b.nid()
        big = ' big' if len(g) == 1 and g[0].get('e') else ''
        b.html.append(f'<div id="{i_d}" class="kw{big}">{spans(b, g, pop=pop)}</div>')
        b.cut(f'#{i_d}', t0, t1)


# ======================================================================================================================
# 17 to 19: the three looks that only existed as stills. All three are a stacked card: lead-in / punch / follow-on.
# ======================================================================================================================
def stacked(b, cls, small, punch_size, extend=True):
    for c in card_times(cards(extend_num=extend)):
        card = b.nid('g')
        parts = []
        if c['before']:
            parts.append(f'<div class="s">{spans(b, c["before"], text=small)}</div>')
        if c['punch']:
            pid = b.nid('p')
            txt = ' '.join(small(w) for w in c['punch'])
            parts.append(f'<div><div id="{pid}" class="e" style="font-size:{punch_size(txt)}px">{esc(txt)}</div></div>')
            if c['before']:
                b.tween_in(f'#{pid}', c['punch'][0]['start'], {'scale': .9, 'filter': 'blur(8px)'}, {'scale': 1, 'filter': 'blur(0px)'}, .2, 'power3.out')
        if c['after']:
            aid = b.nid('a')
            parts.append(f'<div id="{aid}" class="s">{spans(b, c["after"], text=small)}</div>')
            b.cut(f'#{aid}', c['after'][0]['start'])
        b.html.append(f'<div id="{card}" class="sk {cls}">{"".join(parts)}</div>')
        b.cut(f'#{card}', c['t0'], c['t1'])


SK_CSS = '''
.sk{{position:absolute;left:110px;width:860px;top:{top}px;text-align:center;color:#fff}}
.sk .s{{text-wrap:balance;text-shadow:0 2px 16px rgba(0,0,0,.6),0 0 2px rgba(0,0,0,.35)}}
.sk .s span{{color:#fff}}
.sk .e{{display:inline-block;white-space:nowrap;transform-origin:50% 60%}}'''


# 17 WEIGHT SHIFT: one typeface, thin for the lead-in and black for the word that matters
def weightshift(b):
    b.css.append(SK_CSS.format(top=Y_CHEST - 50) + '''
.ws .s{font-family:'Inter';font-weight:300;font-size:62px;line-height:74px;letter-spacing:-.02em}
.ws .e{font-family:'Inter Tight';font-weight:900;letter-spacing:-.045em;line-height:1.04;text-shadow:0 6px 26px rgba(0,0,0,.55)}''')
    stacked(b, 'ws', low, lambda t: min(132, int(840 / (len(t) * .5))))


# 18 TERMINAL: code-font lead-in, one big serif italic word
def terminal(b):
    b.css.append(SK_CSS.format(top=Y_CHEST - 40) + '''
.tm .s{font-family:'JetBrains Mono';font-weight:500;font-size:44px;line-height:62px;letter-spacing:.03em}
.tm .e{font-family:'Instrument Serif';font-style:italic;line-height:.98;margin:2px 0 8px;text-shadow:0 4px 24px rgba(0,0,0,.6)}''')
    stacked(b, 'tm', low, lambda t: min(156, int(850 / (len(t) * .36))))


# 19 OUTLINE: tall condensed caps, the word that matters drawn hollow
def outline(b):
    b.css.append(SK_CSS.format(top=Y_CHEST - 70) + '''
.ol .s{font-family:'Bebas Neue';font-size:80px;line-height:80px;letter-spacing:.012em;text-transform:uppercase}
.ol .e{font-family:'Bebas Neue';line-height:.98;letter-spacing:.02em;text-transform:uppercase;color:transparent;-webkit-text-stroke:3px #fff;
  filter:drop-shadow(0 4px 14px rgba(0,0,0,.55))}''')
    stacked(b, 'ol', lambda w: bare(w['text']), lambda t: min(170, int(850 / (len(t) * .4))))


# ----------------------------------------------------------------------------------------------------------------------
# CUSTOM: the buyer's own caption style, built from a spec (references/replicate.md). Same code path as the nineteen:
# the same words.json, marks, phrase windows, hide windows and caption_y. build_reel.py fills CUSTOM and EXTRA from
# <project>/plan.json and the buyer's my-style.json.
# ----------------------------------------------------------------------------------------------------------------------
CUSTOM = {}               # the caption spec (see custom() for every field and its default)
EXTRA = {}                # reel-wide extras: {'css': str, 'grade': css filter, 'layers': [...], 'sounds': [...], 'fonts': [...]}
NOTES = []                # things the build could not do as asked; build_reel.py prints them as NOTE lines
ENTRANCES = ('none', 'pop', 'fade', 'slide-up', 'type-on', 'word-by-word')
LIT = ('none', 'color', 'stay', 'plate', 'pop')
POSITIONS = {'top': 236, 'center': 860}


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def custom_top(s=None):
    """screen y of the top of the custom caption block, from its "position" (a band name or a y), kept inside the
    safe zone and off the face"""
    s = CUSTOM if s is None else s
    size, lines = _num(s.get('size'), 64), max(1, int(_num(s.get('lines'), 1)))
    plate = s.get('plate') if isinstance(s.get('plate'), dict) else {}
    pad_y = _num((plate.get('pad') or [0, 0])[0], 0) if plate else 0
    height = lines * size * _num(s.get('line_height'), 1.12) + 2 * pad_y
    pos = s.get('position', 'chest')
    if isinstance(pos, (int, float)):
        top = float(pos)
    elif pos == 'lower':
        top = Y_LOWER
    elif pos == 'above-head':
        top = Y_ABOVE_HEAD if Y_ABOVE_HEAD is not None else Y_CHEST
        if Y_ABOVE_HEAD is None and 'no room above the head' not in ' '.join(NOTES):
            NOTES.append('Custom captions: there is no room above the head in this clip, so they sit over the chest.')
    elif pos in POSITIONS:
        top = POSITIONS[pos]
    else:
        top = Y_CHEST
    top += _num(s.get('dy'), 0)
    top = max(236.0, min(top, 1470 - 14 - height))            # inside the Reels safe zone, top and bottom
    head = LAYOUT.get('head') or {}
    if head and not FACELESS:
        f0, f1 = head.get('top_min', head.get('top', 0)) - LIFT, (head.get('chin_max') or head.get('chin') or 0) - LIFT + 24
        if top < f1 and top + height > f0 + .25 * (f1 - f0):      # the block would sit on the face (brow to chin)
            moved = Y_CHEST if f1 + 100 <= Y_CHEST + 76 else max(f1, 236)
            note = (f'Custom captions: y {top:.0f} would put them on the face (it is at y {f0:.0f} to {f1 - 24:.0f}), '
                    f'so they were moved to y {moved:.0f}.')
            if note not in NOTES:
                NOTES.append(note)
            top = moved
    return int(top)


def custom(b):
    """One caption style from a spec. Every field is optional:
      font, weight, italic, stretch   css family (one from assets/fonts/fonts.css, or a "file" in assets/fonts), 100-900,
                                      true / false, font-stretch % (125 for a wide face)
      file                            a font file in <project>/assets/fonts for a family the skill does not ship
      case                            'as-typed' | 'upper' | 'lower' | 'title'
      size, tracking, line_height     px, em, multiple of size
      color, accent                   text colour; colour of marked and lit words
      shadow                          css text-shadow, or false
      stroke                          {"color": "#000", "width": 8}: an outline around the letters
      plate                           {"color": "rgba(...)", "radius": 24, "pad": [18, 32], "blur": 0, "per": "line" | "word"}
      lit, lit_text                   how the word being said shows: 'none' | 'color' (accent while said) | 'stay' (turns
                                      accent and stays) | 'plate' (an accent plate behind it, lit_text on top) | 'pop'
      mark, mark_scale                marked words (num / key / emph / cta in words.json): 'accent' (accent colour) |
                                      'highlight' (an accent box behind the word, lit_text on top) | 'none'; size factor
      words, chars, lines             most words and characters per line; 1 or 2 lines
      position, dy, align, margin     'chest' | 'lower' | 'above-head' | 'top' | 'center' or a y in px; nudge; 'center' |
                                      'left' | 'right'; side margin px
      entrance, exit                  'none' | 'pop' | 'fade' | 'slide-up' | 'type-on' | 'word-by-word'; 'none' | 'fade'
      css                             extra css for this style (classes: .cu block, .cu .ln line, .cu .w word, .cu .w.m
                                      marked word, .cu .pl plate)"""
    s = CUSTOM
    fam, weight = str(s.get('font') or 'Inter Tight'), int(_num(s.get('weight'), 800))
    size, lh = _num(s.get('size'), 64), _num(s.get('line_height'), 1.12)
    case = s.get('case', 'as-typed')
    color, accent = s.get('color', '#FFFFFF'), s.get('accent', '#FAE67A')
    lit = s.get('lit', 'none') if s.get('lit', 'none') in LIT else 'none'
    lit_text = s.get('lit_text', '#151517')
    entrance = s.get('entrance', 'none') if s.get('entrance', 'none') in ENTRANCES else 'none'
    if s.get('entrance') and s.get('entrance') not in ENTRANCES:
        NOTES.append(f'Custom captions: entrance "{s.get("entrance")}" is not one of {", ".join(ENTRANCES)}; used none.')
    if s.get('lit') and s.get('lit') not in LIT:
        NOTES.append(f'Custom captions: lit "{s.get("lit")}" is not one of {", ".join(LIT)}; used none.')
    lines_n = 2 if int(_num(s.get('lines'), 1)) >= 2 else 1
    margin = _num(s.get('margin'), 70)
    align = s.get('align', 'center') if s.get('align', 'center') in ('center', 'left', 'right') else 'center'
    plate = s.get('plate') if isinstance(s.get('plate'), dict) else None
    pad = (plate.get('pad') or [18, 32]) if plate else [0, 0]
    per_word = bool(plate) and plate.get('per') == 'word'
    # how many characters fit across the safe width at this size (wide capitals take more room)
    em = (.68 if case == 'upper' else .55) * (_num(s.get('stretch'), 100) / 100) + _num(s.get('tracking'), 0)
    fit = max(6, int((1080 - 2 * margin - 2 * pad[1]) / max(size * em, 1)))
    per_line_chars = min(int(_num(s.get('chars'), 18)), fit)
    per_line_words = max(1, int(_num(s.get('words'), 3)))
    if _num(s.get('chars'), 18) > fit:
        NOTES.append(f'Custom captions: at {size:.0f}px only about {fit} characters fit a line inside the safe zone, '
                     f'so lines break there instead of at {int(_num(s.get("chars"), 18))}.')
    top = custom_top(s)
    stroke = s.get('stroke') if isinstance(s.get('stroke'), dict) else None
    shadow = s.get('shadow', '0 3px 14px rgba(0,0,0,.5)')
    tt = {'upper': 'uppercase', 'lower': 'lowercase', 'title': 'capitalize'}.get(case, 'none')
    if s.get('file'):
        b.css.append(f"\n@font-face{{font-family:'{fam}';font-weight:{weight};font-style:{'italic' if s.get('italic') else 'normal'};"
                     f"font-display:block;src:url('assets/fonts/{s['file']}')}}")
    plate_css = ''
    if plate:
        blur = _num(plate.get('blur'), 0)
        plate_css = (f"background:{plate.get('color', 'rgba(21,21,23,.7)')};border-radius:{_num(plate.get('radius'), 20):.0f}px;"
                     f"padding:{pad[0]}px {pad[1]}px;"
                     + (f"backdrop-filter:blur({blur:.0f}px);-webkit-backdrop-filter:blur({blur:.0f}px);" if blur else ''))
    side = {'center': f'left:{margin:.0f}px;width:{1080 - 2 * margin:.0f}px;text-align:center',
            'left': f'left:{margin:.0f}px;width:{1080 - 2 * margin:.0f}px;text-align:left',
            'right': f'left:{margin:.0f}px;width:{1080 - 2 * margin:.0f}px;text-align:right'}[align]
    b.css.append(f'''
.cu{{position:absolute;{side};top:{top}px;white-space:nowrap;font-family:'{fam}',sans-serif;font-weight:{weight};
  font-style:{'italic' if s.get('italic') else 'normal'};font-stretch:{_num(s.get('stretch'), 100):.0f}%;font-size:{size:.0f}px;
  line-height:{size * lh:.0f}px;letter-spacing:{_num(s.get('tracking'), 0)}em;text-transform:{tt};color:{color};
  {f'text-shadow:{shadow};' if shadow else ''}{f"-webkit-text-stroke:{_num(stroke.get('width'), 6):.0f}px {stroke.get('color', '#000')};paint-order:stroke fill;" if stroke else ''}}}
.cu .ln{{display:block}}
.cu .pl{{display:inline-block;{'' if per_word else plate_css}}}
.cu .w{{display:inline-block;transform-origin:50% 60%;{'margin:0 .1em;' + plate_css if per_word else ''}}}
.cu .w.m{{{f'color:{accent};' if s.get('mark', 'accent') == 'accent' else ''}{f'background:{accent};color:{lit_text};border-radius:.2em;padding:0 .16em;margin:0 -.04em;text-shadow:none;' if s.get('mark') == 'highlight' else ''}{f"font-size:{_num(s.get('mark_scale'), 1):.2f}em;" if _num(s.get('mark_scale'), 1) != 1 else ''}}}
.cu .ch{{display:inline-block;white-space:pre}}
{s.get('css') or ''}''')

    def shown(w):
        t = bare(w['text'])
        return low(w) if case == 'lower' else t

    groups = chunk(W, per_line_words * lines_n, per_line_chars * lines_n)
    for g, t0, t1 in windows(groups):
        gid = b.nid()
        rows = [g]
        if lines_n == 2 and len(g) > 1 and (len(g) > per_line_words or len(' '.join(x['text'] for x in g)) > per_line_chars):
            cut = min(range(1, len(g)), key=lambda k: abs(len(' '.join(x['text'] for x in g[:k])) - len(' '.join(x['text'] for x in g[k:]))))
            rows = [g[:cut], g[cut:]]
        n_chars = sum(len(shown(w)) for w in g)
        said, ci, parts = max(.12, g[-1]['end'] - g[0]['start']), 0, []
        for row in rows:
            ws = []
            for w in row:
                wid = b.nid('w')
                txt = shown(w)
                cls = 'w m' if w.get('e') else 'w'
                if entrance == 'type-on':
                    inner = ''
                    for ch in txt:
                        cid = b.nid('h')
                        inner += f'<span id="{cid}" class="ch">{esc(ch)}</span>'
                        b.js.append(f"gsap.set('#{cid}',{{opacity:0}});")
                        b.js.append(f"tl.set('#{cid}',{{opacity:1}},{T(g[0]['start'] + .85 * said * ci / max(n_chars, 1)):.3f});")
                        ci += 1
                else:
                    inner = esc(txt)
                ws.append(f'<span id="{wid}" class="{cls}">{inner}</span>')
                ts = T(w['start'])
                if entrance == 'word-by-word' and w is not g[0]:
                    b.js.append(f"gsap.set('#{wid}',{{opacity:0}});")
                    b.js.append(f"tl.fromTo('#{wid}',{{opacity:0,scale:1.18}},{{opacity:1,scale:1,duration:.16,ease:'back.out(2)',immediateRender:false}},{ts:.3f});")
                nxt = g[g.index(w) + 1]['start'] if w is not g[-1] else None
                if lit in ('color', 'stay'):
                    b.js.append(f"tl.set('#{wid}',{{color:'{accent}'}},{ts:.3f});")
                    if lit == 'color' and nxt is not None and not w.get('e'):
                        b.js.append(f"tl.set('#{wid}',{{color:'{color}'}},{T(nxt):.3f});")
                elif lit == 'plate':
                    b.js.append(f"tl.set('#{wid}',{{backgroundColor:'{accent}',color:'{lit_text}',borderRadius:'{.18 * size:.0f}px',"
                                f"boxShadow:'0 0 0 {.12 * size:.0f}px {accent}'}},{ts:.3f});")
                    if nxt is not None:
                        b.js.append(f"tl.set('#{wid}',{{backgroundColor:'transparent',color:'{accent if w.get('e') and s.get('mark', 'accent') != 'none' else color}',"
                                    f"boxShadow:'none'}},{T(nxt):.3f});")
                if lit == 'pop' or (lit in ('color', 'plate') and entrance != 'word-by-word'):
                    if w is not g[0] or lit == 'pop':
                        b.js.append(f"tl.fromTo('#{wid}',{{scale:1.16}},{{scale:1,duration:.2,ease:'back.out(2.2)',immediateRender:false}},{ts:.3f});")
            line = ' '.join(ws)
            parts.append(f'<span class="ln">{line if per_word or not plate else f"<span class=&quot;pl&quot;>{line}</span>".replace("&quot;", chr(34))}</span>')
        b.html.append(f'<div id="{gid}" class="cap cu">{"".join(parts)}</div>')
        sel = f'#{gid}'
        if entrance == 'pop':
            b.tween_in(sel, t0, {'scale': .82}, {'scale': 1}, .18, 'back.out(2)')
        elif entrance == 'fade':
            b.tween_in(sel, t0, {}, {}, .18, 'power1.out')
        elif entrance == 'slide-up':
            b.tween_in(sel, t0, {'y': 34}, {'y': 0}, .22, 'power3.out')
        else:
            b.cut(sel, t0)
        b.out(sel, t1, fade=.12 if s.get('exit') == 'fade' else 0)


STYLES = {
    'arcade': ('01', 'Arcade', arcade),
    'low-key': ('02', 'Low Key', lowkey),
    'field-notes': ('03', 'Field Notes', fieldnotes),
    'anchor': ('04', 'Anchor', anchor),
    'loud-lowercase': ('05', 'Loud Lowercase', loud),
    'vanity': ('06', 'Vanity', vanity),
    'bubblegum': ('07', 'Bubblegum', bubblegum),
    'moodboard': ('08', 'Moodboard', moodboard),
    'golden-hour': ('09', 'Golden Hour', golden),
    'spec-sheet': ('10', 'Spec Sheet', specsheet),
    'bold': ('11', 'Bold', bold),
    'cool-girl': ('12', 'Cool Girl', coolgirl),
    'cool-dude': ('13', 'Cool Dude', cooldude),
    'karaoke': ('14', 'Karaoke', karaoke),
    'signature': ('15', 'Signature', signature),
    'keyword': ('16', 'Keyword', keyword),
    'weight-shift': ('17', 'Weight Shift', weightshift),
    'terminal': ('18', 'Terminal', terminal),
    'outline': ('19', 'Outline', outline),
}

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def lifted(inner):
    """Close-up fallback (layout.json "lift"): when the face fills the frame there is no band under the chin, so the
    picture is lifted and the gap at the bottom is filled with the colour of the frame's bottom edge. That gap sits
    under Instagram's own caption area anyway. Returns inner unchanged for every normal shot."""
    if not LIFT:
        return inner
    return (f'<div class="full" style="background:{FILL}"></div><div class="full" style="top:{-LIFT}px">{inner}</div>'
            f'<div class="full" style="top:{1920 - LIFT - 190}px;height:{LIFT + 190}px;'
            f'background:linear-gradient(180deg,transparent 0%,{FILL} {190 / (LIFT + 190) * 100:.0f}%)"></div>')


# Where the TOP of each style's ordinary caption line sits, as px below the chest band (Y_CHEST). Read from the
# style functions above: keep this in step when a style's `top:` changes. Golden Hour sits on the lower third and
# Bubblegum above the head, so those two are worked out in cap_top().
CAP_OFFSET = {'arcade': 82, 'low-key': 120, 'field-notes': 96, 'anchor': 40, 'loud-lowercase': -6, 'vanity': 30,
              'moodboard': 56, 'spec-sheet': -30, 'bold': 50, 'cool-girl': -40, 'cool-dude': -70, 'karaoke': 96,
              'signature': 70, 'keyword': -40, 'weight-shift': -50, 'terminal': -40, 'outline': -70}


def cap_top(key):
    """screen y of the top of this caption style's ordinary line (what a slot's caption_y moves)"""
    if key == 'custom':
        return custom_top()
    if key == 'golden-hour':
        return Y_LOWER
    if key == 'bubblegum':
        return (Y_ABOVE_HEAD if Y_ABOVE_HEAD is not None else Y_CHEST) + 14
    return Y_CHEST + CAP_OFFSET.get(key, 0)


def caption_changes(b):
    """The moments one caption gives way to the next: every time a caption element is taken off screen (plus the
    start of the reel). A slot that moves the caption layer moves it on one of these, never in mid caption."""
    import re
    ts = {0.0}
    for line in b.js:
        if "'#caps'" in line or "'#fx" in line or "'#ly" in line:
            continue
        m = re.search(r"\{autoAlpha:0[^}]*\},(\d+(?:\.\d+)?)\);\s*$", line)
        if m:
            ts.add(float(m.group(1)))
    return sorted(ts)


def slots(b):
    """Effect slots from plan.json: a finished effect render laid over the reel for exactly its frames.
    scripts/fx_add.py writes the entries; by hand the short form still works:
      {"slots": [{"src": "assets/fx/odometer.mp4", "from": 3.2, "to": 5.9, "captions": "keep"}]}
    Fields: src, from, to (reel seconds, on the frame grid); media (seconds to skip at the head of the render);
      captions   "hide" / false = the reel's own captions are off while the slot plays (the effect carries the words
                 or sits where they go), "keep" / true = they stay on
      hide_captions  [[t0, t1], ...] reel seconds: hide the captions only for these windows (wins over "captions")
      caption_y  screen y the TOP of the reel's caption line moves to while the slot plays (the reel's captions stay
                 on, in the buyer's style, at the place the effect leaves for them; the same number is right for
                 every caption style). fx_add.py --caption-y writes it
      gain       brightness lift for the slot picture (a slot render passes through the renderer twice and comes
                 back a touch darker than the footage around it)
      sfx        [{"src", "at", "media", "dur", "vol"}] the effect's own sounds, replayed over the reel's voice track
      off        true = leave this slot out of the build
    Returns (picture layers, audio elements). The voice always comes from the reel's own a-roll, so there is no
    audio seam at the slot edges."""
    out, audio, track = [], [], 20
    changes = caption_changes(b)        # read before this function adds its own caption-layer lines
    moved = [o for o in PLAN.get('slots') or [] if not o.get('off') and o.get('caption_y') is not None]
    for n, s in enumerate(PLAN.get('slots') or []):
        if s.get('off'):
            continue
        t0, t1 = float(s['from']), min(float(s['to']), DUR)
        if t1 - t0 < .03:
            continue
        g = float(s.get('gain') or 1)
        lift = f' style="filter:brightness({g:.4f})"' if abs(g - 1) > .003 else ''
        # class gr: an overall style grades its footage with .gr, so the slot gets the same grade as its neighbours
        out.append(f'<div id="fx{n}w"{lift}><video id="fx{n}" class="full gr" src="{s["src"]}" muted playsinline '
                   f'data-start="{T(t0):.3f}" data-media-start="{float(s.get("media", 0)):.3f}" '
                   f'data-duration="{t1 - T(t0):.3f}" data-track-index="{5 + n % 2}"></video></div>')
        b.cut(f'#fx{n}w', t0, t1)
        keep = s.get('captions') in (True, 'keep')
        windows = s.get('hide_captions')
        if windows is None:
            windows = [] if keep else [[t0, t1]]
        for h0, h1 in windows:
            h0, h1 = max(0.0, float(h0)), min(float(h1), DUR)
            if h1 - h0 < .03:
                continue
            b.js.append(f"tl.set('#caps',{{autoAlpha:0}},{T(h0):.3f});")
            if h1 < DUR - .02:
                b.js.append(f"tl.set('#caps',{{autoAlpha:1}},{T(h1):.3f});")
        if s.get('caption_y') is not None:
            # The buyer's captions stay on over an effect that needs the chest band for itself: the whole caption
            # layer moves so the TOP of the caption line sits at caption_y, whatever the style (each style starts a
            # different distance from its band: b.cap_top), then goes back.
            # It never moves in the middle of a caption: it moves in on the last caption change at or before the
            # slot, and back on the first one at or after it (within 1.5 s, and never over the face or into the
            # neighbouring slot's own move).
            dy = float(s['caption_y']) - getattr(b, 'cap_top', Y_CHEST)
            a, z = T(t0), T(t1)
            lo = max([float(o['to']) for o in moved if float(o['to']) <= t0 + .02] or [0.0])
            hi = min([float(o['from']) for o in moved if float(o['from']) >= t1 - .02] or [DUR])
            head = LAYOUT.get('head') or {}
            chin = (head.get('chin_max') or head.get('chin') or 0) - LIFT
            on_face = bool(head) and float(s['caption_y']) < chin + 24 and float(s['caption_y']) + 200 > head_top_at(t0)
            if not on_face:
                before = [c for c in changes if lo - .02 <= c <= a + .02 and a - c <= 1.5]
                after = [c for c in changes if z - .02 <= c <= hi + .02 and c - z <= 1.5]
                a = max(before) if before else a
                z = min(after) if after else z
            b.js.append(f"tl.set('#caps',{{y:{dy:.0f}}},{a:.3f});")
            if z < DUR - .02:
                b.js.append(f"tl.set('#caps',{{y:0}},{z:.3f});")
        for k, c in enumerate(s.get('sfx') or []):
            at = max(0.0, float(c['at']))
            dur = min(float(c.get('dur') or .5), DUR - at - .01)
            if dur < .03:
                continue
            audio.append(f'<audio id="fx{n}a{k}" src="{c["src"]}" data-start="{at:.3f}" '
                         f'data-media-start="{float(c.get("media") or 0):.3f}" data-duration="{dur:.3f}" '
                         f'data-track-index="{track}" data-volume="{float(c.get("vol") or .3):.3f}"></audio>')
            track += 1
    return out, audio


ANCHORS = ('full', 'behind', 'top', 'above-head', 'center', 'chest', 'lower-third')


def layers(b, behind=False):
    """The buyer's own on-screen elements from plan.json / my-style.json ("layers"): html + css with a time range and
    a named anchor. This is how a look is rebuilt that no built-in effect covers (a title card, a progress bar, a
    border, a lower third, a sticker). Each layer:
      {"id": "title", "anchor": "top", "from": 0.0, "to": 2.4, "html": "<div class='tt'>...</div>", "css": ".tt{...}",
       "in": "fade", "out": "fade", "dx": 0, "dy": 0}
      anchor   'full' (the whole frame, your html places itself), 'behind' (the whole frame, BEHIND the speaker: needs a
               person cutout), or a band the engine places for this clip: 'top' (y 236), 'above-head', 'center',
               'chest', 'lower-third'. A band layer is a 1080 px wide centred box whose top sits on the band.
      from/to  reel seconds. Leave both out for a layer that stays the whole reel (a border, a corner tag).
      in/out   'none' | 'fade' | 'pop' | 'slide-up'
    Returns the html of the layers of one kind (behind the speaker, or in front). Layers never count as caption
    changes and never move with a slot's caption_y."""
    out = []
    for n, l in enumerate(EXTRA.get('layers') or []):
        anchor = l.get('anchor', 'full')
        if anchor not in ANCHORS:
            if not behind:
                NOTES.append(f'Layer {l.get("id", n)}: anchor "{anchor}" is not one of {", ".join(ANCHORS)}; left out.')
            continue
        back = anchor == 'behind'
        if back and not CUTOUT:
            # never drawn in front instead: a layer made to sit behind the speaker would cover the face
            if behind:
                NOTES.append(f'Layer {l.get("id", n)} is meant to sit behind the speaker, which needs a person cutout '
                             '(rvm_cut.py). There is none yet, so it was left out of this build.')
            continue
        if back != behind:
            continue
        if back:
            b.cutout = True
        t0, t1 = _num(l.get('from'), 0), min(_num(l.get('to'), DUR), DUR)
        if t1 - t0 < .03:
            continue
        y = {'top': 236, 'above-head': Y_ABOVE_HEAD if Y_ABOVE_HEAD is not None else 236, 'center': 860, 'chest': Y_CHEST,
             'lower-third': Y_LOWER}.get(anchor)
        if anchor == 'above-head' and Y_ABOVE_HEAD is None and not behind:
            NOTES.append(f'Layer {l.get("id", n)}: no room above the head in this clip, so it sits at the top of the safe zone.')
        box = ('left:0;top:0;width:1080px;height:1920px' if y is None
               else f'left:{_num(l.get("dx"), 0):.0f}px;top:{y + _num(l.get("dy"), 0):.0f}px;width:1080px;text-align:center')
        lid = f'ly{n}'
        if l.get('css'):
            b.css.append('\n' + str(l['css']))
        # "media": a moving picture in the layer (a GIF the buyer asked for, made into a clip by gif_add.py). It is a
        # video element with its own track, so the renderer keeps it in step with the reel. {"src", "w", "x", "y", "radius"}
        media, m = '', l.get('media')
        if isinstance(m, dict) and m.get('src'):
            if PROJECT and not os.path.isfile(os.path.join(PROJECT, *str(m['src']).split('/'))):
                NOTES.append(f'Layer {l.get("id", n)}: {m["src"]} is not in the project, so it was left out.')
                continue
            at = (f'position:absolute;left:{_num(m.get("x"), 0):.0f}px;top:{_num(m.get("y"), 0):.0f}px;'
                  if m.get('x') is not None and m.get('y') is not None else '')
            media = (f'<video id="{lid}v" src="{m["src"]}" muted playsinline data-start="{T(t0):.3f}" data-media-start="0" '
                     f'data-duration="{t1 - T(t0):.3f}" data-track-index="{100 + n}" style="{at}width:{_num(m.get("w"), 420):.0f}px;'
                     f'height:auto;border-radius:{_num(m.get("radius"), 0):.0f}px"></video>')
        out.append(f'<div id="{lid}" class="layer" data-name="{esc(str(l.get("id", n)))}" style="position:absolute;{box}">{media}{l.get("html", "")}</div>')
        sel, how_in, how_out = f'#{lid}', l.get('in', 'none'), l.get('out', 'none')
        if t0 > .02 or how_in != 'none':
            b.js.append(f"gsap.set('{sel}',{{autoAlpha:0}});")
            frm = {'pop': "scale:.85,", 'slide-up': "y:40,"}.get(how_in, '')
            to = {'pop': "scale:1,ease:'back.out(2)',", 'slide-up': "y:0,ease:'power3.out',"}.get(how_in, '')
            dur = 0 if how_in == 'none' else .22
            b.js.append(f"tl.fromTo('{sel}',{{{frm}autoAlpha:0}},{{{to}autoAlpha:1,duration:{dur},immediateRender:false}},{T(t0):.3f});")
        if t1 < DUR - .02:
            if how_out == 'fade':
                b.js.append(f"tl.to('{sel}',{{autoAlpha:0,duration:.18}},{max(0, T(t1) - .18):.3f});")
            b.js.append(f"tl.set('{sel}',{{autoAlpha:0}},{T(t1):.3f});")
    return out


def sounds():
    """The reel's own sound cues from plan.json / my-style.json ("sounds"): [{"src": "assets/sfx/pop.mp3", "at": 1.2,
    "vol": 0.25, "dur": 0.5}]. Stock names live in <project>/assets/sfx. Returns audio elements."""
    out = []
    for k, c in enumerate(EXTRA.get('sounds') or []):
        at = max(0.0, _num(c.get('at'), 0))
        dur = min(_num(c.get('dur'), .6), DUR - at - .01)
        src = str(c.get('src', ''))
        if dur < .03 or not src:
            continue
        if PROJECT and not os.path.isfile(os.path.join(PROJECT, *src.split('/'))):
            NOTES.append(f'Sound {src} is not in the project, so that cue was left out.')
            continue
        out.append(f'<audio id="snd{k}" src="{src}" data-start="{at:.3f}" data-media-start="{_num(c.get("media"), 0):.3f}" '
                   f'data-duration="{dur:.3f}" data-track-index="{60 + k}" data-volume="{_num(c.get("vol"), .25):.3f}"></audio>')
    return out


def page(key, safe=False):
    """A caption style (or 'none', or 'custom': the buyer's own spec) over the footage."""
    b = Build()
    if key == 'custom':
        custom(b)
        b.cap_top = cap_top(key)
    elif key != 'none':
        STYLES[key][2](b)
        b.cap_top = cap_top(key)
    behind = layers(b, behind=True)       # the buyer's own layers that sit behind the speaker (they need the cutout)
    if EXTRA.get('grade'):                # one colour grade for the footage, the cutout and every effect slot (.gr)
        b.css.append(f"\n#plate,#cutw,.gr{{filter:{EXTRA['grade']}}}")
    nl = '\n'
    up = f' class="full" style="top:{-LIFT}px"' if LIFT else ''
    footage = [lifted(f'<div id="plate"><video id="bgv" class="full" src="{VIDEO}" muted playsinline data-start="0" '
                      f'data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video></div>'),
               '<div id="back">' + ''.join(b.back) + ''.join(behind) + '</div>']
    if b.cutout:
        footage.append(f'<div id="cutw"{up}><video id="cut" class="full" src="{CUTOUT}" muted playsinline data-start="0" '
                       f'data-media-start="0" data-duration="{DUR:.3f}" data-track-index="1"></video></div>')
    return document(b, footage, safe=safe, audio_track=2)


def document(b, footage, safe=False, audio_track=9):
    """The whole composition: footage layers, effect slots, captions, timeline. Used by page() and by styles.py."""
    nl = '\n'
    fx, fx_audio = slots(b)
    front = layers(b)                     # the buyer's own layers, over the slots and under the captions
    fx_audio = fx_audio + sounds()
    if EXTRA.get('css'):                  # the escape hatch: plain css from plan.json / my-style.json, last so it wins
        b.css.append('\n' + str(EXTRA['css']))
    return f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{BASE_CSS}{''.join(b.css)}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="{VIDEO}" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="{audio_track}" data-volume="1"></audio>
{nl.join('  ' + h for h in fx_audio)}
  <div id="footage">
{nl.join('    ' + h for h in footage)}
  </div>
  <div id="slots">
{nl.join('    ' + h for h in fx)}
  </div>
  <div id="layers">
{nl.join('    ' + h for h in front)}
  </div>
  <div id="caps">
{nl.join('    ' + h for h in b.html)}
  </div>
{SAFE_GUIDE if safe else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(b.js)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


if __name__ == '__main__':
    print('\n'.join(f'{v[0]}  {k:16} {v[1]}' for k, v in STYLES.items()))
    print('\nThis is the engine. Build a reel with scripts/build_reel.py <project>.')
