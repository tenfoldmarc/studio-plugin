#!/usr/bin/env python3
"""odometer: the number the speaker says rolls up digit by digit like a mechanical mileage counter (job: proof).

Each digit is a drum that spins up from 0 with a vertical motion blur, overshoots a hair and locks with a soft tick
exactly as the speaker finishes saying the number. The drums live in a dark instrument panel that sits BEHIND the speaker (between
the plate and their cutout), placed automatically in the free wall next to their head. A label writes itself on their
words. With two counters, the first one shrinks into a small chip in a corner when the second arrives.

Run from the slot folder (the skill's Python (PY): it needs numpy and PIL):
    PY build.py            writes index.html + work/layout.json
    SAFE=1 ... build.py      draws the Instagram safe zone (snapshots only, never the render)
    CAPTIONS=0 ... build.py  number panels only, no label words
    SFX=0 ... build.py       no ticks / whoosh
Full run order: effect.md.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np

import measure as M

# ==== CLIP (edit this) ====
COUNTERS = [    # one dict per number the speaker says, in the order the speaker says them. One or two (three works, it gets busy).
    dict(
        text='10',                    # what locks on screen: digits with an optional prefix / suffix ("10", "$200K", "87%", "100s", "1,250"). Only a number the speaker SAYS.
        say='10',                     # the spoken words for that number exactly as words.json has them; the last drum locks as the last word ends (measured on the audio)
        lock=None,                    # override in seconds if `say` cannot find it or measure.py shows the end is wrong (the END of the spoken number)
        label=[('YEARS', 'years'), ('RUNNING', 'running'), ('ADS', 'ads')],   # words under the drums: (WORD, when). when = a spoken word from words.json, seconds, or None (right after the lock). Wraps to a second line by itself. [] = no label
        label2=None,                  # OPTIONAL extra line, off by default: [[('FUNNELS', 'funnels')], [('FUNNELS', 5.8), ('+', 5.8), ('BUDGETS', 5.8)]]  each inner list replaces the one before with a roll
        sit='auto',                   # where the panel sits: 'auto' (free wall nearest the speaker's head), 'right', 'left', 'above', or (x, y) px of its top-left corner
        size='auto',                  # 'auto' = as big as fits (max 1.5), or a scale number (1.0 = 150 px wide drums)
        then='dock',                  # when the NEXT counter arrives: 'dock' (shrink into a corner chip), 'stay' (both full size), 'out' (leave). Ignored for the last one
    ),
    dict(                             # second counter: same fields. Delete this dict for a single number
        text='100s',
        say='hundreds',
        lock=None,
        label=[('OF', 'of'), ('OFFERS', 'offers')],
        label2=None,
        sit='auto',
        size='auto',
        then='dock',
    ),
]
ROLL = 0.44        # seconds the drums spin before the lock (0.35 to 0.5; shorter for a number the speaker says fast)
OUT = None         # seconds: every panel leaves by this time. None = they hold to the last frame (end the slot on a cut, or set this ~0.25 s before the slot ends)
DOCK_CORNER = 'auto'   # where a docked chip goes: 'auto' (top corner away from the next panel), 'top-left', 'top-right', or (x, y)
GRADE = 'contrast(1.05) saturate(.92) brightness(.99)'    # light grade on the footage (plate + cutout). 'none' when the main reel grades it
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FP = shutil.which('ffprobe') or 'ffprobe'
SLOT = os.path.basename(HERE)
FPS = 30
YEL, CREAM, INK = '#FAE67A', '#FFF8EF', '#14161C'
SAFE = (35, 220, 1045, 1470)          # Instagram: top 220, nothing below 1470, 35 px sides (+ right 100 from y 1155)
EDGE = 10                             # breathing room inside the safe zone
CAPTIONS = os.environ.get('CAPTIONS', '1') != '0'
SFX_ON = os.environ.get('SFX', '1') != '0'

# geometry at scale 1 (px)
DW, DH, DGAP, DFS = 150, 200, 8, 178  # drum width / height / gap, digit font size
PAD = 20
CHIP = 0.64                           # drum scale once docked
L1_FS, L1_H, L1_TR = 40, 46, .13      # label line 1: font size, line height, tracking (em)
L2_FS, L2_H, L2_TR = 26, 36, .17      # label line 2
C1_FS, C1_H, C1_TR, C2_FS, C2_H, C2_TR = 30, 36, .12, 22, 29, .15      # chip label lines
RULE_GAP = 16
WORD_GAP = .34                        # em between label words
MAX_W = 640                           # a panel never gets wider than this (px on screen)
SFX_GAIN = 0.75                       # house level: every sound 25% under the template's base volume
TICK, TICK_PRE, WHOOSH = 0.50, 0.20, 0.12
VOICE_REF = -13.5                     # loud-speech level (dB, measure.voice_db) of the clip these volumes were tuned on
SFX_LEAD = {'click-soft': 0.048}      # silence before the transient inside the file: start that much early
SFX_TRIM = {'click-soft': 0.125}      # the file is a double click (down + up): keep the first tick only
FIX_EM = {'%': .77, 'K': .61, 'k': .56, 'M': .82, 'B': .62, 's': .48, '$': .59, '+': .58, 'x': .54, '#': .62}

CLIP = M.clip()
N = CLIP['frames']
DUR = N / FPS


# ------------------------------------------------------------------ text widths (PIL reads the woff2; table fallback)
_fonts = {}


def text_w(txt, font, fs, track=0.0):
    try:
        from PIL import ImageFont
        key = (font, round(fs))
        if key not in _fonts:
            _fonts[key] = ImageFont.truetype(os.path.join(HERE, 'assets/fonts', font), round(fs))
        return _fonts[key].getlength(txt) * fs / round(fs) + len(txt) * track * fs
    except Exception:
        if font.startswith('InterTight'):
            return sum(FIX_EM.get(c, .6) for c in txt) * fs
        return len(txt) * (.72 + track) * fs


def line_w(words, fs, track):
    return sum(text_w(w, 'Montserrat-600-normal.woff2', fs, track) for w in words) + max(0, len(words) - 1) * WORD_GAP * fs - track * fs


# ------------------------------------------------------------------ small helpers
def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return n / FPS - .002


def js(v):
    return f"'{v}'" if isinstance(v, str) else f'{v:.3f}'.rstrip('0').rstrip('.')


def frame_sets(sel, f0, f1, fn):
    """one tl.set per frame f0..f1 with the props fn(frame) returns: deterministic, exactly what the renderer samples"""
    out = []
    for f in range(max(0, f0), min(N - 1, f1) + 1):
        props = fn(f)
        body = ','.join(f"{k}:{js(v) if not isinstance(v, dict) else '{' + ','.join(f'{a}:{js(b)}' for a, b in v.items()) + '}'}"
                        for k, v in props.items())
        out.append(f"tl.set('{sel}',{{{body}}},{max(0, F(f)):.4f});")
    return out


def ease_io(u):
    u = min(1.0, max(0.0, u))
    return 16 * u ** 5 if u < .5 else 1 - (-2 * u + 2) ** 5 / 2      # quint in-out


def split(text):
    m = re.match(r'^(\D*)(\d[\d.,]*?)(\D*)$', text)
    if not m:
        sys.exit(f'counter text "{text}" needs at least one digit (prefix + digits + suffix, e.g. "$200K")')
    return m.group(1), m.group(2), m.group(3)


# ------------------------------------------------------------------ the reusable part: one counter
def roll_curve(K, T, overshoot=0.13):
    """Underdamped spring from rest: position (in digits) that first reaches K at time T, runs `overshoot` of a digit
    past it and settles back. Returns p(tau) and the settle time."""
    ab = math.log(K / overshoot) / math.pi          # a/b so the first overshoot is exactly `overshoot` digits
    b = (math.pi - math.atan(1 / ab)) / T            # first crossing of K at tau = T
    a = ab * b

    def p(tau):
        if tau <= 0:
            return 0.0
        return K * (1 - math.exp(-a * tau) * (math.cos(b * tau) + ab * math.sin(b * tau)))
    return p, math.pi / b * 1.9


def odo_width(text, w=DW, gap=DGAP, fs=DFS):
    """laid-out width of the counter row (drums + separators + prefix / suffix), same maths as the CSS flex row"""
    pre, body, suf = split(text)
    parts = []
    if pre:
        parts.append(text_w(pre, 'InterTight-900-normal.woff2', fs * .74) + 2)
    for c in body:
        parts.append(w if c.isdigit() else text_w(c, 'InterTight-900-normal.woff2', fs * .8) - 4)
    if suf:
        parts.append(text_w(suf, 'InterTight-900-normal.woff2', fs * .74, -.03) + 2)
    return sum(parts) + gap * (len(parts) - 1)


def odometer(oid, text, t_start, t_lock, w=DW, h=DH, fs=DFS, gap=DGAP, stagger=0.07, blur_cap=38.0, shutter=0.34):
    """A mechanical counter for any string of digits with an optional prefix / suffix ("$200K", "87%", "100s", "1,250").

    Every digit is its own drum: a column of numbers that rolls UP from 0, with a vertical motion blur proportional
    to its speed (SVG feGaussianBlur, y only), a small spring overshoot when it locks, and a yellow flash that cools
    to cream. Drums lock left to right, `stagger` apart; the LAST one locks at t_lock.
    Returns (html, svg filter defs, tweens, [lock times])."""
    pre, body, suf = split(text)
    ndig = sum(c.isdigit() for c in body)
    html, defs, tw, locks = [], [], [], []
    if pre:
        html.append(f'<span class="ofix opre">{pre}</span>')
    i = 0
    for c in body:
        if not c.isdigit():
            html.append(f'<span class="osep">{c}</span>')
            continue
        d = int(c)
        K = d + 10 * (1 if i == 0 else 2)            # steps: the first drum does one turn, the rest two (they spin faster)
        seq = [k % 10 for k in range(K + 1)] + [(d + 1) % 10]      # one extra number below, seen during the overshoot
        cid = f'{oid}-c{i}'
        lock = t_lock - (ndig - 1 - i) * stagger
        locks.append(lock)
        p, settle = roll_curve(K, max(.12, lock - t_start))
        cells = ''.join(f'<b>{n}</b>' for n in seq)
        html.append(f'<span class="drum"><span id="{cid}" class="strip" style="filter:url(#{cid}-f)">{cells}</span>'
                    f'<i class="shade"></i><i id="{cid}-s" class="sheen"></i></span>')
        defs.append(f'<filter id="{cid}-f" x="-10%" y="-1%" width="120%" height="102%" color-interpolation-filters="sRGB">'
                    f'<feGaussianBlur id="{cid}-b" in="SourceGraphic" stdDeviation="0 0"/></filter>')
        f0, f1 = int(t_start * FPS), int(math.ceil((t_start + settle) * FPS)) + 1

        def pos(f, p=p, f1=f1, K=K):
            return float(K) if f >= f1 else p(f / FPS - t_start)

        def blur(f, pos=pos):
            v = abs(pos(f + .5) - pos(f - .5)) * h          # px per frame
            return min(blur_cap, shutter * v) if v > 1.5 else 0.0
        tw.append(f"gsap.set('#{cid}',{{y:0}});")
        tw += frame_sets(f'#{cid}', f0, f1, lambda f: {'y': -pos(f) * h})
        tw += frame_sets(f'#{cid}-b', f0, f1, lambda f: {'attr': {'stdDeviation': f'0 {blur(f):.2f}'}})
        if f1 > N - 1:                                # slot ends mid-roll: never leave a drum between two numbers
            tw.append(f"tl.set('#{cid}',{{y:{-K * h}}},{F(N - 1):.4f});")
        # lock: a glass sheen crosses the drum, digits flash yellow and cool to cream
        tw += [f"gsap.set('#{cid}-s',{{xPercent:-260,skewX:-16}});",
               f"tl.to('#{cid}-s',{{xPercent:320,duration:.7,ease:'power2.inOut'}},{t_lock + .10 + i * .07:.3f});",
               f"tl.fromTo('#{cid}',{{color:'{YEL}'}},{{color:'{CREAM}',duration:.55,ease:'power2.out',immediateRender:false}},{lock:.3f});"]
        i += 1
    if suf:
        sid = f'{oid}-suf'
        html.append(f'<span id="{sid}" class="ofix osuf">{suf}</span>')
        tw += [f"gsap.set('#{sid}',{{autoAlpha:0,scale:.4,x:-18}});",
               f"tl.to('#{sid}',{{autoAlpha:1,scale:1,x:0,duration:.34,ease:'back.out(2.4)'}},{t_lock - .02:.3f});"]
    return (f'<div id="{oid}" class="odo" style="--w:{w}px;--h:{h}px;--fs:{fs}px;--gap:{gap}px">{"".join(html)}</div>',
            defs, tw, locks)


# ------------------------------------------------------------------ timing: read the lock and the label words off the audio
def resolve_times(counters):
    ws = M.words()
    tline = M.timeline(ws, M.envelope())          # measured (start, end) per word: Whisper's times snapped to the audio
    for k, c in enumerate(counters):
        c['id'] = f'p{k + 1}'
        if c.get('lock') is not None:
            c['t_lock'] = float(c['lock'])
        else:
            hit = M.find_say(ws, c.get('say') or '', after=counters[k - 1]['t_lock'] if k else 0.0)
            if not hit:
                sys.exit(f"counter {k + 1}: cannot find say='{c.get('say')}' in words.json ({' '.join(w['text'] for w in ws)}). "
                         f"Fix `say` or set lock=<seconds> (python measure.py prints the measured word ends).")
            c['t_lock'] = tline[hit[1]][1]
        c['t_lock'] = min(c['t_lock'], DUR - .12)
        c['t_start'] = max(.06, c['t_lock'] - ROLL)
        c['t_in'] = max(.02, c['t_start'] - .10)       # frame 0 stays a clean plate
        if c['t_lock'] - c['t_start'] < .2:
            print(f"!! counter {k + 1} locks {c['t_lock']:.2f}s into the slot: too early for a roll. Start the slot earlier.")

        def when(w, t_prev, c=c):
            if isinstance(w, (int, float)):
                t = float(w)
            elif w is None:
                t = t_prev + .09
            else:
                hit = M.find_say(ws, w, after=c['t_in'])
                if not hit:
                    print(f"   label word time '{w}' not in words.json: it appears right after the lock")
                    t = t_prev + .09
                else:
                    t = tline[hit[0]][0]
            return max(t, t_prev + .06)
        t_prev = c['t_lock'] - .02
        l1 = []
        for word, w in (c.get('label') or []) if CAPTIONS else []:
            t_prev = when(w, t_prev)
            l1.append((t_prev, word))
        rows = []
        for row in (c.get('label2') or []) if (CAPTIONS and l1) else []:
            r = []
            if not rows:                     # first row: every word on its own time
                for word, w in row:
                    t_prev = when(w, t_prev)
                    r.append((t_prev, word))
            else:                            # later rows roll in as one line, on the first word's time
                t_prev = when(row[0][1], t_prev + .25)
                r = [(t_prev, word) for word, _ in row]
            rows.append(r)
        c['l1'], c['l2'] = l1, rows
    for k, c in enumerate(counters):
        nxt = counters[k + 1] if k + 1 < len(counters) else None
        c['t_end'] = DUR if OUT is None else min(DUR, OUT)
        c['mode'] = c.get('then', 'dock') if nxt else 'hold'
        if nxt and c['mode'] == 'dock':
            c['t_dock'] = max(c['t_lock'] + .25, nxt['t_in'] - .04)
            c['dock_dur'] = .34
            late = [w for t, w in c['l1'] + [x for r in c['l2'] for x in r] if t > c['t_dock'] - .05]
            if late:
                print(f"!! counter {k + 1}: label words {late} arrive after it docks at {c['t_dock']:.2f}s. Give them earlier times.")
        elif nxt and c['mode'] == 'out':
            c['t_end'] = nxt['t_in'] + .06
    return counters


# ------------------------------------------------------------------ geometry of one panel at scale 1
def geometry(c):
    c['inner'] = inner = odo_width(c['text'])
    wrapped = []
    while len(c['l1']) > 1 and line_w([w for _, w in c['l1']], L1_FS, L1_TR) > inner:
        wrapped.insert(0, c['l1'].pop())                # the label is wider than the drums: the tail drops to line 2
    if wrapped:
        c['l2'] = [wrapped] + c['l2']
    l1w = line_w([w for _, w in c['l1']], L1_FS, L1_TR) if c['l1'] else 0
    l2w = max((line_w([w for _, w in r], L2_FS, L2_TR) for r in c['l2']), default=0)
    c['cw'] = cw = max(inner, l1w, l2w)                 # content width: a long label widens the panel
    c['l1w'], c['l2w'] = l1w, l2w
    c['W'] = cw + 2 * PAD
    c['y_rule'] = PAD + DH + RULE_GAP
    c['y_l1'] = c['y_rule'] + 14
    c['H0'] = 2 * PAD + DH
    c['H1'] = c['y_l1'] + L1_H + PAD - 4
    c['H2'] = c['H1'] + L2_H
    c['H'] = c['H2'] if c['l2'] else c['H1'] if c['l1'] else c['H0']
    # the chip it becomes when it docks
    c['chip_w'] = inner * CHIP + 32
    lines, cur = [], []
    words = [w for _, w in c['l1']] + ([w for _, w in c['l2'][-1]] if c['l2'] else [])
    for w in words:                                      # greedy wrap to the chip's width; first line is the yellow one
        fs, tr = (C1_FS, C1_TR) if not lines else (C2_FS, C2_TR)
        if cur and line_w(cur + [w], fs, tr) > inner * CHIP:
            lines.append(cur); cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    c['chip_lines'] = [' '.join(x) for x in lines]
    c['chip_rule'] = 16 + DH * CHIP + 12
    c['chip_h'] = c['chip_rule'] + 12 + C1_H + C2_H * (len(lines) - 1) + 14 if lines else 32 + DH * CHIP


def readable(c, align):
    """rects (local px, scale 1) that must never be behind the speaker: the digits and the label text"""
    ox = PAD if align == 'left' else PAD + c['cw'] - c['inner']
    r = [(ox + 8, PAD + 16, ox + c['inner'] - 2, PAD + DH - 16)]
    for y, h, w in ((c['y_l1'], L1_H, c['l1w']), (c['y_l1'] + L1_H, L2_H, c['l2w'])):
        if w:
            x0 = PAD if align == 'left' else PAD + c['cw'] - w
            r.append((x0, y + 4, x0 + w, y + h - 4))
    return r


def chip_readable(c, align):
    r = [(16 + 4, 16 + 8, 16 + c['inner'] * CHIP, 16 + DH * CHIP - 8)]
    y = c['chip_rule'] + 12
    for j, ln in enumerate(c['chip_lines']):
        fs, tr, h = (C1_FS, C1_TR, C1_H) if j == 0 else (C2_FS, C2_TR, C2_H)
        w = min(c['inner'] * CHIP, line_w(ln.split(' '), fs, tr))
        x0 = 16 if align == 'left' else 16 + c['inner'] * CHIP - w
        r.append((x0, y + 3, x0 + w, y + h - 3))
        y += h
    return r


# ------------------------------------------------------------------ placement: measured on the speaker's cutout, never typed in
class Field:
    """their cutout over a span of frames, as integral images on the 8 px matte grid"""

    def __init__(self, m, t0, t1):
        f0, f1 = max(0, int(t0 * FPS) - 1), min(len(m), int(math.ceil(t1 * FPS)) + 1)
        seg = m[f0:max(f0 + 1, f1)]
        self.any = self._integral(seg.any(axis=0).astype(np.float64))      # covered in ANY frame
        self.mean = self._integral(seg.mean(axis=0))                        # share of frames covered

    @staticmethod
    def _integral(a):
        out = np.zeros((a.shape[0] + 1, a.shape[1] + 1))
        out[1:, 1:] = a.cumsum(0).cumsum(1)
        return out

    @staticmethod
    def _sum(I, x0, y0, x1, y1):
        """sum over px rects; x0.. may be arrays (same shape)"""
        c = M.CELL
        i0 = np.clip(np.floor(np.asarray(x0) / c).astype(int), 0, M.GW)
        j0 = np.clip(np.floor(np.asarray(y0) / c).astype(int), 0, M.GH)
        i1 = np.clip(np.ceil(np.asarray(x1) / c).astype(int), 0, M.GW)
        j1 = np.clip(np.ceil(np.asarray(y1) / c).astype(int), 0, M.GH)
        return I[j1, i1] - I[j0, i1] - I[j1, i0] + I[j0, i0]

    def hits(self, x0, y0, x1, y1):
        return self._sum(self.any, x0, y0, x1, y1)

    def cover(self, x0, y0, x1, y1):
        area = (np.asarray(x1) - np.asarray(x0)) * (np.asarray(y1) - np.asarray(y0)) / M.CELL ** 2
        return self._sum(self.mean, x0, y0, x1, y1) / np.maximum(area, 1)


def in_safe(x, y, w, h):
    ok = (x >= SAFE[0] + EDGE - 1) & (x + w <= SAFE[2] + .5) & (y >= SAFE[1] + EDGE + 5) & (y + h <= SAFE[3])
    return ok & ((y + h <= 1155) | (x + w <= 980))            # right 100 px column is taken from y 1155 down


def place(c, field, subj, avoid):
    """Biggest panel whose digits and label are never behind the speaker, as close to their head as it gets, tucked so their
    head overlaps an empty corner of it (that overlap is the depth). Returns x, y, scale, label align, cover."""
    sit, size = c.get('sit', 'auto'), c.get('size', 'auto')
    smax = min(1.5, MAX_W / c['W']) if size == 'auto' else float(size)
    scales = [smax - .05 * i for i in range(40) if smax - .05 * i >= .55] if size == 'auto' else [smax]
    ax, ay = subj['ax'], subj['ay']
    sh = subj['box'][3] - subj['box'][1]
    if isinstance(sit, (tuple, list)):
        x, y = float(sit[0]), float(sit[1])
        s = scales[0]
        best = None
        for align in ('right', 'left') if x + c['W'] * s / 2 >= ax else ('left', 'right'):
            h = sum(field.hits(x + r[0] * s, y + r[1] * s, x + r[2] * s, y + r[3] * s) for r in readable(c, align))
            if best is None or h < best[0]:
                best = (h, align)
        return dict(x=x, y=y, s=s, align=best[1], clear=best[0] == 0,
                    cover=float(field.cover(x, y, x + c['W'] * s, y + c['H'] * s)))
    gx, gy = np.meshgrid(np.arange(SAFE[0], SAFE[2], 4.0), np.arange(SAFE[1], SAFE[3], 4.0))
    best = None
    for s in scales:
        w, h = c['W'] * s, c['H'] * s
        ok0 = in_safe(gx, gy, w, h)
        for (a0, a1, a2, a3) in avoid:
            ok0 &= (gx + w + 16 <= a0) | (gx >= a2 + 16) | (gy + h + 16 <= a1) | (gy >= a3 + 16)
        cx, cy = gx + w / 2, gy + h / 2
        if sit == 'right':
            ok0 &= cx >= ax
        elif sit == 'left':
            ok0 &= cx <= ax
        elif sit == 'above':
            ok0 &= (gy + h <= ay + .3 * h) & (np.abs(cx - ax) <= .3 * w)
        if not ok0.any():
            continue
        cover = field.cover(gx, gy, gx + w, gy + h)
        dist = np.hypot(np.maximum(0, np.maximum(gx - ax, ax - (gx + w))), np.maximum(0, np.maximum(gy - ay, ay - (gy + h))))
        low = np.maximum(0, cy - (ay + .35 * sh))             # keep it by the speaker's head, not down by the speaker's legs
        for align in ('right', 'left'):
            ok = ok0 & (cover <= .22)
            for r in readable(c, align):
                ok &= field.hits(gx + r[0] * s, gy + r[1] * s, gx + r[2] * s, gy + r[3] * s) == 0
            if not ok.any():
                continue
            away = (align == 'right') == (cx >= ax)           # label hugs the edge away from the speaker's head
            score = (s / scales[0] - dist / 500 - low / 300 + .15 * ((cover > .004) & (cover < .15)) + .04 * away
                     - gy / 6000)
            score = np.where(ok, score, -1e9)
            j, i = np.unravel_index(int(np.argmax(score)), score.shape)
            if best is None or score[j, i] > best[0]:
                best = (float(score[j, i]), dict(x=float(gx[j, i]), y=float(gy[j, i]), s=round(s, 3), align=align, clear=True,
                                                 cover=float(cover[j, i])))
    if best is None:
        sys.exit(f"counter {c['id']} ({c['text']}): no free spot for the panel at any size with sit={sit!r}. The speaker fills the "
                 f"frame for the whole span: try sit='auto', a shorter label, or give sit=(x, y) and size by hand.")
    return best[1]


def place_chip(c, field, avoid, prefer_left):
    corner = DOCK_CORNER
    w, h = c['chip_w'], c['chip_h']
    if isinstance(corner, (tuple, list)):
        return dict(x=float(corner[0]), y=float(corner[1]), align='left' if corner[0] < 540 else 'right')
    if corner in ('top-left', 'top-right'):
        prefer_left = corner == 'top-left'
    gx, gy = np.meshgrid(np.arange(SAFE[0], SAFE[2], 4.0), np.arange(SAFE[1], SAFE[3], 4.0))
    ok0 = in_safe(gx, gy, w, h)
    for (a0, a1, a2, a3) in avoid:
        ok0 &= (gx + w + 20 <= a0) | (gx >= a2 + 20) | (gy + h + 20 <= a1) | (gy >= a3 + 20)
    best = None
    for left in (prefer_left, not prefer_left):
        align = 'left' if left else 'right'
        ok = ok0.copy()
        for r in chip_readable(c, align):
            ok &= field.hits(gx + r[0], gy + r[1], gx + r[2], gy + r[3]) == 0
        if not ok.any():
            continue
        tx = SAFE[0] + EDGE if left else SAFE[2] - w
        d = np.where(ok, np.hypot(gx - tx, gy - (SAFE[1] + EDGE + 6)), 1e9)
        j, i = np.unravel_index(int(np.argmin(d)), d.shape)
        if best is None or d[j, i] < best[0] - 200:           # only change sides when the preferred one is far worse
            best = (float(d[j, i]), dict(x=float(gx[j, i]), y=float(gy[j, i]), align=align))
    if best is None:
        sys.exit(f"counter {c['id']}: nowhere to dock the chip. Use then='out' for it, or DOCK_CORNER=(x, y).")
    return best[1]


def layout(counters):
    m = M.alpha()
    subj = M.subject(m)
    if subj is None:
        sys.exit('the cutout is empty: is the speaker in this slot?')
    prev = None
    for c in counters:
        geometry(c)
        t1 = c.get('t_dock', c['t_end']) + (c.get('dock_dur', 0))
        avoid = [prev['rect']] if prev and prev['mode'] == 'stay' else []
        if prev and prev['mode'] == 'dock':
            pass                                              # the chip is placed after this panel, away from it
        p = place(c, Field(m, c['t_in'], t1), subj, avoid)
        c.update(x=p['x'], y=p['y'], scale=p['s'], align=p['align'], cover=p['cover'], clear=p['clear'])
        c['rect'] = (c['x'], c['y'], c['x'] + c['W'] * c['scale'], c['y'] + c['H'] * c['scale'])
        if prev and prev['mode'] == 'dock':
            ch = place_chip(prev, Field(m, prev['t_dock'], prev['t_end']), [c['rect']], prefer_left=c['x'] + c['W'] * c['scale'] / 2 >= 540)
            prev['dock'] = ch
            prev['chip_rect'] = (ch['x'], ch['y'], ch['x'] + prev['chip_w'], ch['y'] + prev['chip_h'])
        c['from_x'] = 0 if prev is None else (110 if c['x'] + c['W'] * c['scale'] / 2 >= 540 else -110)
        prev = c
    return subj


# ------------------------------------------------------------------ panels
def words_line(pid, k, words, cls, fs_scale=1.0):
    spans = ''.join(f'<span class="mk"><span id="{pid}-{k}-{j}" class="ch">{w}</span></span>' for j, (_, w) in enumerate(words))
    st = f' style="font-size:{fs_scale:.3f}em"' if fs_scale < .999 else ''
    return f'<div class="{cls}"{st}>{spans}</div>'


def panel(c):
    pid, S, al = c['id'], c['scale'], c['align']
    odo, defs, tw, locks = odometer(pid + 'o', c['text'], c['t_start'], c['t_lock'])
    W, cw, inner = c['W'], c['cw'], c['inner']
    Hel = c['H']                                              # the background element is built at its final height
    Hnow = c['H1'] if c['l2'] else Hel                        # ... and starts one line shorter when a second line comes later
    ox = PAD if al == 'left' else PAD + cw - inner
    html = [f'<div id="{pid}" class="panel" style="left:0;top:0"><div id="{pid}-in" class="pin" style="width:{W:.1f}px;height:{Hel:.1f}px">',
            f'<div id="{pid}-bg" class="pbg" style="width:{W:.1f}px;height:{Hel:.1f}px"></div>',
            f'<div id="{pid}-dr" class="pdr" style="left:{ox:.1f}px;top:{PAD}px">{odo}</div>']
    if c['l1']:
        l1 = words_line(pid, 'a', c['l1'], 'l1')
        l2 = ''.join(f'<div id="{pid}-r{k}" class="l2row">{words_line(pid, f"b{k}", ws, "l2")}</div>' for k, ws in enumerate(c['l2']))
        html.append(f'<div id="{pid}-lab" class="plab {al}" style="left:{PAD}px;top:{c["y_rule"]}px;width:{cw:.1f}px">'
                    f'<div id="{pid}-rule" class="rule"></div>{l1}' + (f'<div class="l2slot">{l2}</div>' if l2 else '') + '</div>')
    # entry: pops onto the wall (frame 0 is always a clean plate)
    cx = c['x']
    tw += [f"gsap.set('#{pid}',{{x:{cx + c['from_x']:.1f},y:{c['y']:.1f},scale:{S}}});",
           f"gsap.set('#{pid}-in',{{autoAlpha:0,scale:.9,filter:'blur(14px)'}});",
           f"gsap.set('#{pid}-bg',{{scaleY:{Hnow / Hel:.4f}}});",
           f"tl.to('#{pid}-in',{{autoAlpha:1,duration:.12,ease:'none'}},{c['t_in']:.3f});",
           f"tl.to('#{pid}-in',{{scale:1,filter:'blur(0px)',duration:.34,ease:'expo.out'}},{c['t_in']:.3f});"]
    if c['from_x']:
        tw.append(f"tl.to('#{pid}',{{x:{cx:.1f},duration:.42,ease:'expo.out'}},{c['t_in']:.3f});")
    # lock: tiny punch on the drums, the rule draws, then the label writes itself on the speaker's words
    tw.append(f"tl.fromTo('#{pid}-dr',{{scale:1.045}},{{scale:1,duration:.4,ease:'expo.out',immediateRender:false}},{c['t_lock']:.3f});")
    if c['l1']:
        tw += [f"gsap.set('#{pid}-rule',{{scaleX:0}});",
               f"tl.to('#{pid}-rule',{{scaleX:1,duration:.5,ease:'expo.out'}},{c['t_lock']:.3f});"]
    for j, (t, _) in enumerate(c['l1']):
        tw += [f"gsap.set('#{pid}-a-{j}',{{yPercent:112}});",
               f"tl.to('#{pid}-a-{j}',{{yPercent:0,duration:.42,ease:'expo.out'}},{t - .03:.3f});"]
    grown_at = None
    for k, ws in enumerate(c['l2']):
        t0 = min(t for t, _ in ws)
        if k == 0:       # the panel grows a line (scaleY on the background only: never tween height)
            grown_at = t0 - .08
            tw.append(f"tl.to('#{pid}-bg',{{scaleY:1,duration:.42,ease:'expo.out'}},{grown_at:.3f});")
            for j, (t, _) in enumerate(ws):
                tw += [f"gsap.set('#{pid}-b{k}-{j}',{{yPercent:112}});",
                       f"tl.to('#{pid}-b{k}-{j}',{{yPercent:0,duration:.42,ease:'expo.out'}},{t - .03:.3f});"]
        else:            # the line rolls: old row up and out, new row up from below
            tw += [f"gsap.set('#{pid}-r{k}',{{yPercent:118}});",
                   f"tl.to('#{pid}-r{k - 1}',{{yPercent:-118,duration:.38,ease:'expo.inOut'}},{t0 - .10:.3f});",
                   f"tl.to('#{pid}-r{k}',{{yPercent:0,duration:.38,ease:'expo.inOut'}},{t0 - .10:.3f});"]
    sfx = [('click-soft', t, TICK if j == len(locks) - 1 else TICK_PRE) for j, t in enumerate(locks)]
    for k, ws in enumerate(c['l2'][1:]):
        sfx.append(('click-soft', min(t for t, _ in ws) + .08, TICK_PRE))

    if c['mode'] == 'dock':
        # FLIP to a chip: one move (quint in-out) with a horizontal motion blur from its speed; the drums scale down,
        # the panel shrinks around them, the hero label hands over to a stacked one.
        d, t0, dur = c['dock'], c['t_dock'], c['dock_dur']
        if c['chip_lines']:
            ch = ''.join(f'<div class="{"c1" if j == 0 else "c2"}">{w}</div>' for j, w in enumerate(c['chip_lines']))
            html.append(f'<div id="{pid}-clab" class="clab {d["align"]}" style="left:16px;top:{c["chip_rule"]:.1f}px;'
                        f'width:{inner * CHIP:.1f}px"><div class="rule"></div>{ch}</div>')
            tw.append(f"gsap.set('#{pid}-clab',{{autoAlpha:0}});")
        defs.append(f'<filter id="{pid}-mf" x="-30%" y="-30%" width="160%" height="160%" color-interpolation-filters="sRGB">'
                    f'<feGaussianBlur id="{pid}-mb" in="SourceGraphic" stdDeviation="0 0"/></filter>')
        f0, f1 = int(t0 * FPS), int(math.ceil((t0 + dur) * FPS))
        sy0 = 1.0 if (grown_at is not None and grown_at < t0) or not c['l2'] else Hnow / Hel

        def e(f):
            return ease_io((f / FPS - t0) / dur)

        def mix(a, b, f):
            return a + (b - a) * e(f)

        def speed(f):
            return math.hypot(mix(c['x'], d['x'], f + .5) - mix(c['x'], d['x'], f - .5),
                              mix(c['y'], d['y'], f + .5) - mix(c['y'], d['y'], f - .5))
        horiz = abs(d['x'] - c['x']) >= abs(d['y'] - c['y'])
        tw += frame_sets(f'#{pid}', f0, f1, lambda f: {'x': mix(c['x'], d['x'], f), 'y': mix(c['y'], d['y'], f), 'scale': mix(S, 1, f)})
        tw += frame_sets(f'#{pid}-bg', f0, f1, lambda f: {'scaleX': mix(1, c['chip_w'] / W, f), 'scaleY': mix(sy0, c['chip_h'] / Hel, f)})
        tw += frame_sets(f'#{pid}-dr', f0, f1, lambda f: {'scale': mix(1, CHIP, f), 'x': mix(0, 16 - ox, f), 'y': mix(0, 16 - PAD, f)})
        tw += frame_sets(f'#{pid}-mb', f0, f1, lambda f: {'attr': {'stdDeviation':
                         (f'{min(34.0, .30 * speed(f)):.2f} 0' if horiz else f'0 {min(34.0, .30 * speed(f)):.2f}')}})
        tw += [f"tl.set('#{pid}',{{filter:'url(#{pid}-mf)'}},{max(0, F(f0)):.4f});",
               f"tl.set('#{pid}',{{filter:'none'}},{F(f1):.4f});"]
        if c['l1']:
            tw.append(f"tl.to('#{pid}-lab',{{autoAlpha:0,duration:.1,ease:'none'}},{t0:.3f});")
        if c['chip_lines']:
            tw.append(f"tl.to('#{pid}-clab',{{autoAlpha:1,duration:.14,ease:'none'}},{t0 + dur * .55:.3f});")
        sfx.append(('whoosh-short', t0 - .06, WHOOSH))
    if c['t_end'] < DUR - .01:      # leave: blur out before the slot hands back to the plain a-roll
        tw += [f"tl.to('#{pid}-in',{{autoAlpha:0,scale:.94,filter:'blur(10px)',duration:.2,ease:'power2.in'}},{c['t_end'] - .2:.3f});",
               f"tl.set('#{pid}-in',{{autoAlpha:0}},{c['t_end']:.3f});"]
    html.append('</div></div>')
    return html, defs, tw, sfx


def sfx_len(name):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                 os.path.join(HERE, f'assets/sfx/{name}.mp3')], capture_output=True, text=True).stdout)


def audio(sfx):
    if not SFX_ON:
        return []
    out, lanes = [], []
    # the volumes were tuned on a clip whose loud speech sat at VOICE_REF dB: a quieter voice gets quieter ticks
    k = min(1.0, max(.3, 10 ** ((M.voice_db() - VOICE_REF) / 20)))
    sfx = [(name, max(0.0, t - SFX_LEAD.get(name, 0)), vol * k) for name, t, vol in sfx if t < DUR - .05]
    for k, (name, t, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        d = min(SFX_TRIM.get(name, sfx_len(name)), DUR - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0); lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.g{{filter:{GRADE}}}
#bgv{{z-index:0}}
#wall{{position:absolute;inset:0;z-index:2}}
#cutwrap{{position:absolute;inset:0;z-index:4}}
svg.defs{{position:absolute;width:0;height:0}}

.panel{{position:absolute;transform-origin:0 0}}
.pin{{position:relative;transform-origin:50% 45%}}
.pbg{{position:absolute;left:0;top:0;transform-origin:0 0;border-radius:32px;background:linear-gradient(180deg,{INK} 0%,#1A1D25 55%,#262B36 100%);
  box-shadow:0 30px 70px rgba(20,22,28,.42),0 6px 18px rgba(20,22,28,.34),inset 0 1.5px 0 rgba(255,255,255,.10),
  inset 0 0 0 1.5px rgba(255,248,239,.07)}}
.pdr{{position:absolute;transform-origin:0 0}}

/* ---- odometer (reusable) ---- */
.odo{{display:flex;align-items:flex-end;gap:var(--gap);height:var(--h);transform-origin:50% 50%}}
.drum{{position:relative;display:block;flex:none;width:var(--w);height:var(--h);overflow:hidden;border-radius:18px;
  background:linear-gradient(180deg,#07080A 0%,#20232B 20%,#2C303A 50%,#20232B 80%,#07080A 100%);
  box-shadow:inset 0 0 0 1.5px rgba(0,0,0,.65),0 1.5px 0 rgba(255,255,255,.07)}}
.strip{{position:absolute;left:0;top:0;width:100%;display:block;color:{CREAM};will-change:transform}}
.strip b{{display:block;height:var(--h);line-height:var(--h);text-align:center;font-family:'Inter Tight';font-weight:900;
  font-size:var(--fs);letter-spacing:-.02em;font-variant-numeric:tabular-nums}}
.shade{{position:absolute;inset:0;pointer-events:none;border-radius:18px;
  background:linear-gradient(180deg,rgba(6,7,9,.92) 0%,rgba(6,7,9,.35) 14%,rgba(6,7,9,0) 30%,rgba(255,255,255,.035) 50%,
  rgba(6,7,9,0) 70%,rgba(6,7,9,.35) 86%,rgba(6,7,9,.92) 100%)}}
.sheen{{position:absolute;top:0;bottom:0;left:0;width:46%;pointer-events:none;
  background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.17),rgba(255,255,255,0))}}
.ofix{{display:block;flex:none;font-family:'Inter Tight';font-weight:900;color:{YEL};line-height:1;transform-origin:0% 80%}}
.osuf{{font-size:calc(var(--fs) * .74);margin:0 0 calc(var(--h) * .065) 2px;letter-spacing:-.03em}}
.opre{{font-size:calc(var(--fs) * .74);margin:0 2px calc(var(--h) * .065) 0}}
.osep{{display:block;flex:none;font-family:'Inter Tight';font-weight:900;color:{CREAM};font-size:calc(var(--fs) * .8);line-height:1;
  margin:0 -2px calc(var(--h) * .1)}}

/* ---- labels ---- */
.plab{{position:absolute;white-space:nowrap}}
.plab.right{{text-align:right}}
.plab.left{{text-align:left}}
.rule{{height:3px;border-radius:2px;background:{YEL};margin-bottom:11px}}
.right .rule{{transform-origin:100% 50%}}
.left .rule{{transform-origin:0 50%}}
.mk{{display:inline-block;overflow:hidden;vertical-align:top;margin-left:{WORD_GAP}em}}
.mk:first-child{{margin-left:0}}
.ch{{display:inline-block}}
.l1{{height:{L1_H}px;font:600 {L1_FS}px/{L1_H}px Montserrat;letter-spacing:{L1_TR}em;color:{YEL}}}
.l2slot{{position:relative;height:{L2_H}px;overflow:hidden}}
.l2row{{position:absolute;top:0;height:{L2_H}px}}
.right .l2row{{right:0}}
.left .l2row{{left:0}}
.l2{{height:{L2_H}px;font:600 {L2_FS}px/{L2_H}px Montserrat;letter-spacing:{L2_TR}em;color:rgba(255,248,239,.86)}}
.right .l1{{margin-right:-{L1_TR}em}}
.right .l2{{margin-right:-{L2_TR}em}}
.clab{{position:absolute;white-space:nowrap}}
.clab.left{{text-align:left}}
.clab.right{{text-align:right}}
.clab .rule{{height:2.5px;margin-bottom:9px}}
.c1{{font:600 {C1_FS}px/{C1_H}px Montserrat;letter-spacing:{C1_TR}em;color:{YEL}}}
.c2{{font:600 {C2_FS}px/{C2_H}px Montserrat;letter-spacing:{C2_TR}em;color:rgba(255,248,239,.86)}}
.clab.right .c1{{margin-right:-{C1_TR}em}}
.clab.right .c2{{margin-right:-{C2_TR}em}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    counters = resolve_times([dict(c) for c in COUNTERS])
    subj = layout(counters)
    html, defs, tw, sfx = [], [], [], []
    for c in reversed(counters):          # earlier counters paint on top (the docking panel flies over the next one)
        h, d, t, s = panel(c)
        html += h; defs += d; tw += t; sfx += s
    nl = '\n'
    page = f'''<!doctype html>
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
{nl.join(audio(sfx))}
  <svg class="defs" aria-hidden="true"><defs>
{nl.join(defs)}
  </defs></svg>
  <video id="bgv" class="full g" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
  <div id="wall">
{nl.join(html)}
  </div>
  <div id="cutwrap"><video id="cut" class="full g" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="1"></video></div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open(os.path.join(HERE, 'index.html'), 'w').write(page)
    # what check.py and the next person need: where everything ended up and when
    out = {'slot': SLOT, 'frames': N, 'subject': subj, 'counters': []}
    print(f'wrote index.html  {N} frames ({DUR:.2f}s)   the speaker: head top around ({subj["ax"]:.0f}, {subj["ay"]:.0f})')
    for c in counters:
        S = c['scale']
        rd = [[c['x'] + r[0] * S, c['y'] + r[1] * S, c['x'] + r[2] * S, c['y'] + r[3] * S] for r in readable(c, c['align'])]
        o = {'id': c['id'], 'text': c['text'], 't_in': round(c['t_in'], 3), 't_start': round(c['t_start'], 3), 't_lock': round(c['t_lock'], 3),
             't_end': round(c.get('t_dock', c['t_end']), 3), 'rect': [round(v, 1) for v in c['rect']], 'scale': S, 'align': c['align'],
             'readable': [[round(v, 1) for v in r] for r in rd], 'label': [[round(t, 3), w] for t, w in c['l1']],
             'label2': [[[round(t, 3), w] for t, w in r] for r in c['l2']], 'mode': c['mode']}
        if c['mode'] == 'dock':
            d = c['dock']
            o['chip'] = {'t': round(c['t_dock'] + c['dock_dur'], 3), 'rect': [round(v, 1) for v in c['chip_rect']],
                         'readable': [[round(d['x'] + r[0], 1), round(d['y'] + r[1], 1), round(d['x'] + r[2], 1), round(d['y'] + r[3], 1)]
                                      for r in chip_readable(c, d['align'])], 'lines': c['chip_lines']}
        out['counters'].append(o)
        print(f"  {c['id']} \"{c['text']}\"  in {c['t_in']:.2f}  spin {c['t_start']:.2f}  LOCK {c['t_lock']:.2f}s (frame {round(c['t_lock'] * FPS)})"
              f"  panel {c['W'] * S:.0f}x{c['H'] * S:.0f} at ({c['x']:.0f},{c['y']:.0f}) scale {S}  label {c['align']}  "
              f"their cutout covers {c['cover'] * 100:.0f}% of it" + ('' if c['clear'] else '   !! DIGITS OR LABEL GO BEHIND HIM'))
        if c['l1']:
            print('     label: ' + '  '.join(f'{w}@{t:.2f}' for t, w in c['l1'])
                  + ''.join('  |  ' + ' '.join(f'{w}@{t:.2f}' for t, w in r) for r in c['l2']))
        if c['mode'] == 'dock':
            print(f"     docks {c['t_dock']:.2f}s -> chip {c['chip_w']:.0f}x{c['chip_h']:.0f} at ({c['dock']['x']:.0f},{c['dock']['y']:.0f})  {c['chip_lines']}")
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, 'work', 'layout.json'), 'w'), indent=1)
    if os.environ.get('SAFE'):
        print('SAFE guide is ON: snapshots only. Run build.py again without SAFE=1 before the render.')
    else:
        print(f'render:  npx --yes hyperframes@0.8.34 render -o renders/{SLOT}.mp4 --quality high')


build()
