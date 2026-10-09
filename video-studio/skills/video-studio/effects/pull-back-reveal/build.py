#!/usr/bin/env python3
"""PULL-BACK REVEAL (proof): the live video shrinks into a card inside a plain app window on a light page. Beside it a
checklist of the real edit ticks off, the window's timeline strip plays the reel's own shots, and a counter rolls up
to its number as everything turns "done". Then the card grows back to full frame (or the reel cuts away).

The window is drawn in the page from the settings below and the slot's own clip: nothing pre-rendered, no logo, no
real product's interface. No cutout is used.

Run from the slot folder (see effect.md for the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no caption words on the card,
                                               SFX=0 no sounds; GRADE=0 is accepted and changes nothing)
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys

# ==== STYLE (the reel's look wins: when the reel has a caption or overall style, match this block to it) ====
# Every word this effect draws takes its typeface, case, weight, colours and placement from here. The defaults are a
# light, neutral window. Fonts must be families that assets/fonts/fonts.css provides.
STYLE = dict(
    ui_font='Inter',               # checklist rows, panel title, window title
    ui_weight=500,                 # its weight (use one the font file has; the window title is drawn at 600)
    ui_case='as-typed',            # 'as-typed', 'upper' or 'lower'
    mono_font='JetBrains Mono',    # small technical text: tag pill, status line, frame counter, file name
    mono_weight=500,
    num_font='DM Serif Display',   # the big counter digits, the unit badge and the highlighted name
    num_weight=400,
    label_font='Instrument Serif',  # the line under the counter
    label_weight=400,
    label_italic=True,
    label_case='as-typed',         # 'as-typed', 'upper' or 'lower' (also used for the highlighted name)
    cap_font='Inter Tight',        # caption words on the card: set these six to the reel's caption style
    cap_weight=800,
    cap_case='as-typed',           # 'as-typed', 'upper' or 'lower'
    cap_size=62,                   # px on screen
    cap_tracking=-0.04,            # letter spacing, em
    cap_color='#FFFFFF',
    cap_mark='#FAE67A',            # colour of the words listed in CAP_MARK (the reel's accent; never orange)
    cap_words=3,                   # most words shown at once
    cap_y=None,                    # y of the top of the caption line. None = just above the timeline strip
    width_factor=1.0,              # raise to 1.1 when another typeface runs wider and a text touches its edge
    page='#F1EEE6',                # the page behind the window
    window='#FAF9F5',              # title bar and timeline strip
    panel='#FFFFFF',               # checklist panel
    line='#E4DFD4',                # hairlines
    ink='#1F1E1D',                 # main text and the digits
    muted='#6F6C66',               # secondary text
    faint='#A7A195',               # steps that have not started yet
    accent='#3D6FE0',              # "working" colour: progress, playhead, tag pill, unit badge (never orange)
    accent_text='#FFFFFF',         # text on the accent colour
    done='#3F8F5A',                # "done" colour: ticks, the finished timeline
    highlight='#FAE67A',           # slab behind the highlighted name
    track='#DDD4C3',               # timeline blocks before they fill
    dots='#D8D3C8',                # the three window buttons (plain on purpose)
    radius=36,                     # window corner radius, px
    window_x=310,                  # placement: left edge of the window (205 to 375). 310 keeps the whole window
                                   # inside the safe zone. 375 = bigger left column, but the window's lower right
                                   # corner (no text in it) then sits under the app's buttons
    panel_y=None,                  # placement: top of the checklist panel. None = under the counter, off the FACE
)
# ==== END STYLE ====

# ==== CLIP (edit this) ====
# Everything on screen must be TRUE of this reel. Read the steps and the shot lengths from the reel's own edit list
# (edl.json / plan.json: clips used, shots, frames). Never invent a step, a count or a number.
STEPS = [               # the checklist, in the order the work was done. 2 to 7 short lines, about 22 characters each.
    'Step one',         # placeholder: replace with a real step of this edit, e.g. how many clips were transcribed
    'Step two',         # placeholder
    'Step three',       # placeholder. A line can also be ('text', frame) to pin the frame it ticks on
]
SHOTS = []              # length of every shot of the finished reel, in frames (seconds x 30), in order. The timeline
                        # strip draws one block per shot and counts frames up to their sum (computed, never typed).
                        # [] = one plain bar with no frame count
WINDOW_TITLE = 'Assistant'   # text at the right of the title bar. Plain text only: no logo, no product interface
WINDOW_FILE = ''        # small file name in the middle of the title bar, e.g. the reel's own file name. '' = none
PANEL_TITLE = 'Working on'   # small grey line at the top of the checklist
PANEL_TAG = ''          # pill beside it: what is doing the work, in the user's words. '' = no pill
STATUS_RUN = 'rendering'     # status word in the timeline strip while it plays
STATUS_DONE = 'done'    # and once it has finished
COUNT_TO = None         # the number the counter rolls up to (0 to 9999). ONLY a number the speaker says in this
                        # clip, e.g. 100 for "one hundred percent". None = no counter
COUNT_UNIT = '%'        # one or two characters in the round badge beside the number. '' = no badge
COUNT_LABEL = ''        # short line under the number, the speaker's own words. '' = none
COUNT_NAME = ''         # one highlighted name or word under that, as the speaker says it. '' = none
F_IN = 3                # frame the shrink starts (2 or later). The card has landed 12 frames after it
TICK_FROM = None        # frame the first step ticks. None = 14 frames after F_IN
DONE_AT = None          # frame the last step ticks, the timeline finishes and the counter lands on COUNT_TO: the
                        # onset of the word that says it is finished (onsets.py). None = 50 frames after F_IN
COUNT_AT = None         # frame the digits appear and start rolling. None = 14 frames before DONE_AT
LABEL_AT = None         # frame COUNT_LABEL writes on, or a list with one frame per word. None = 15 after DONE_AT
NAME_AT = None          # frame COUNT_NAME wipes in. None = 12 frames after the label
F_OUT = 'auto'          # frame the picture is full frame again. 'auto' = 3 frames before the end of the slot.
                        # 'cut' = the window stays to the last frame and the reel must CUT to another shot there
FACE = None             # (x0, y0, x1, y1) box around the speaker's face in the slot's picture, px (read it off a
                        # frame of assets/aroll.mp4). The checklist panel is then kept off it. None = not checked
CAP_FIX = {}            # caption words Whisper misheard: {'heard': 'meant'} ('' drops the word)
CAP_MARK = []           # caption words drawn in STYLE['cap_mark'], e.g. the one word that carries the line
SOUNDS = 'auto'         # 'auto' = short whoosh on the shrink and on the way back, a soft click per tick, a low hit on
                        # DONE_AT, a pop on the name. Or a list of (name, frame, volume) with stock names; [] = none
SEED = 7                # shuffles the little bars drawn inside the timeline blocks
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
SHRINK, GROW = 12, 12            # frames the shrink and the grow-back take
CY, CW, CH = 250, 670, 1190      # the card (the live picture) on screen: top, width, height. Its left is window_x
WIN_TOP, BAR_H, STRIP_H = 222, 70, 148
SFX_GAIN = 0.75
PLACEHOLDERS = ('Step one', 'Step two', 'Step three')
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def F(n):
    """time of frame n, nudged 2 ms early so a hit lands ON that frame"""
    return max(0.0, n / FPS - .002)


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def cased(s, key):
    mode = STYLE[key]
    return s.upper() if mode == 'upper' else s.lower() if mode == 'lower' else s


def rgba(hexcol, a):
    h = hexcol.lstrip('#')
    return f'rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})'


def text_w(s, fs, mono=False, tight=0.0):
    """estimated width in px (build time has no browser): generous on purpose, tune with STYLE['width_factor']"""
    if mono:
        return len(s) * .6 * fs
    w = 0.0
    for ch in s:
        w += (.28 if ch == ' ' else .29 if ch in "il.,:;!'|" else .38 if ch in 'ftjrI-' else .90 if ch in 'mwMW@%'
              else .70 if ch.isupper() else .64 if ch.isdigit() else .58)
    return (w + tight * len(s)) * fs * STYLE['width_factor']


def stop(msg):
    sys.exit('pull-back-reveal: ' + msg)


# ------------------------------------------------------------------ when things happen (frames)
def schedule(n_frames):
    f_in = int(F_IN)
    if f_in < 2:
        stop('F_IN must be 2 or later, so the first frames of the slot stay the plain picture')
    land = f_in + SHRINK
    if F_OUT == 'cut':
        f_out, out0 = None, n_frames
    else:
        f_out = n_frames - 3 if F_OUT == 'auto' else int(F_OUT)
        if f_out > n_frames - 2:
            stop(f'F_OUT {f_out} is too late: at most {n_frames - 2} so the last frame is the plain picture')
        out0 = f_out - GROW
    steps = [(s, None) if isinstance(s, str) else (s[0], int(s[1])) for s in STEPS]
    if not 2 <= len(steps) <= 7:
        stop(f'STEPS has {len(steps)} lines: use 2 to 7')
    done = int(DONE_AT) if DONE_AT is not None else f_in + 50
    first = int(TICK_FROM) if TICK_FROM is not None else f_in + 14
    if first < land + 1:
        stop(f'TICK_FROM {first} is before the card has landed: {land + 1} or later')
    if done < first + 4 * (len(steps) - 1):
        stop(f'DONE_AT {done} leaves no time for {len(steps)} ticks after f{first}: {first + 4 * (len(steps) - 1)} or later')
    ticks = [round(first + (done - first) * k / (len(steps) - 1)) for k in range(len(steps))]
    for k, (_, pin) in enumerate(steps):
        if pin is not None:
            ticks[k] = pin
    if any(b - a < 4 for a, b in zip(ticks, ticks[1:])) or ticks[0] < land + 1:
        stop(f'step frames must be 4 or more apart and start after f{land}: got {ticks}')
    done = max(done, ticks[-1])
    last = done
    count_at = None
    if COUNT_TO is not None:
        count_at = int(COUNT_AT) if COUNT_AT is not None else max(land + 2, done - 14)
        if not land < count_at <= done - 6:
            stop(f'COUNT_AT {count_at} must be after f{land} and 6 frames or more before DONE_AT {done}')
    label = []
    if COUNT_LABEL:
        nw = len(COUNT_LABEL.split())
        if isinstance(LABEL_AT, (list, tuple)):
            label = [int(v) for v in LABEL_AT]
            if len(label) != nw:
                stop(f'LABEL_AT lists {len(label)} frames but COUNT_LABEL has {nw} words')
        else:
            l0 = int(LABEL_AT) if LABEL_AT is not None else done + 15
            label = [l0 + 6 * k for k in range(nw)]
        last = max(last, label[-1] + 6)
    name = None
    if COUNT_NAME:
        name = int(NAME_AT) if NAME_AT is not None else (label[-1] if label else done) + 12
        last = max(last, name + 10)
    need = last + 8 + (GROW + 3 if f_out is not None else 1)
    if last + 8 > out0:
        stop(f'the slot is too short: the last beat is on f{last} and the way out starts on f{out0}. Make the slot '
             f'{need} frames or longer, or move the beats earlier')
    return dict(f_in=f_in, land=land, f_out=f_out, out0=out0, ticks=ticks, done=done, count_at=count_at, label=label,
                name=name, last=last, steps=[s for s, _ in steps], n=n_frames)


# ------------------------------------------------------------------ where things sit (px on the 1080 x 1920 screen)
def columns():
    """the digit columns of the counter: (cells, kind, width in em)"""
    s = str(int(COUNT_TO))
    cols = []
    for i, ch in enumerate(s):
        k, d = len(s) - 1 - i, int(ch)
        if k == 0:
            cols.append((['0'] + [str((d - 19 + j) % 10) for j in range(20)], 'roll', .53))
        elif i == 0 and len(s) >= 3:
            cols.append((['', ch], 'late', .417 if ch == '1' else .53))
        else:
            cols.append(([''] + [str((d - 9 + j) % 10) for j in range(10)], 'roll', .53))
    return cols


def layout(S):
    cx = int(STYLE['window_x'])
    if not 205 <= cx <= 375:
        stop("STYLE['window_x'] must be between 205 and 375")
    L = dict(cx=cx, k=CW / 1080, warn=[])
    col_w = cx - 35
    y = 226
    # counter
    if COUNT_TO is not None:
        if not 0 <= int(COUNT_TO) <= 9999:
            stop('COUNT_TO must be a whole number from 0 to 9999')
        if len(COUNT_UNIT) > 2:
            stop('COUNT_UNIT is one or two characters (it sits in a small round badge)')
        cols = columns()
        em = sum(c[2] for c in cols)
        nf = min(230.0, col_w / em)
        if nf < 110:
            stop("no room for the counter beside the window: raise STYLE['window_x'] or use a shorter number")
        k = nf / 230
        L.update(cols=cols, nf=nf, cell=round(196 * k), dig_w=round(em * nf), dig_x=cx - round(em * nf), dig_y=y,
                 badge=round(108 * k), badge_x=cx - round(13 * k), badge_y=y + round(78 * k))
        y += round(191 * k)
    if COUNT_LABEL:
        txt = cased(COUNT_LABEL, 'label_case')
        fs = 58
        while fs > 38 and text_w(txt, fs) * .82 > col_w - 10:
            fs -= 2
        if text_w(txt, fs) * .82 > col_w + 40:
            stop(f'COUNT_LABEL "{COUNT_LABEL}" is too long for the column beside the window: about '
                 f'{int((col_w + 40) / (38 * .5))} characters')
        L.update(lab_fs=fs, lab_y=y, lab_txt=txt)
        y += round(fs * 1.19)
    if COUNT_NAME:
        txt = cased(COUNT_NAME, 'label_case')
        fs = 70
        while fs > 44 and text_w(txt, fs) + 32 > col_w - 6:
            fs -= 2
        if text_w(txt, fs) + 32 > col_w + 60:
            stop(f'COUNT_NAME "{COUNT_NAME}" is too long for the column beside the window: one short word or name')
        L.update(name_fs=fs, name_y=y + 9, name_h=round(fs * 1.14), name_txt=txt)
        y += 9 + round(fs * 1.14)
    readout_bottom = y if y > 226 else None
    # checklist panel
    rows = [cased(s, 'ui_case') for s in S['steps']]
    widest = max(text_w(r, 30) for r in rows)
    rf = 30
    if widest > 347:
        rf = max(26, int(30 * 347 / widest))
        if text_w(max(rows, key=len), rf) > 360:
            stop(f'a step is too long ("{max(S["steps"], key=len)}"): about 24 characters at most')
    title = cased(PANEL_TITLE, 'ui_case')
    head_w = 26 + text_w(title, 27) + ((text_w(PANEL_TAG, 24, True) + 44) if PANEL_TAG else 0)
    pw = int(min(443, max(300, widest * rf / 30 + 100, head_w + 52)))
    if head_w + 48 > 443:
        stop('PANEL_TITLE and PANEL_TAG together are too long: about 24 characters in all')
    ph = 118 + 64 * len(rows)
    top_min = (readout_bottom + 20) if readout_bottom else 250
    top_max = WIN_TOP + (CH + 28) - STRIP_H - 22 - ph        # stays above the timeline strip
    if top_max < top_min:
        stop(f'no room for {len(rows)} steps under the counter lines: drop a step, COUNT_LABEL or COUNT_NAME')
    py = (readout_bottom + 24) if readout_bottom else (top_min + top_max) // 2
    py = min(py, top_max)
    px = 37
    face = None
    if FACE is not None:
        fx0, fy0, fx1, fy1 = [float(v) for v in FACE]
        face = (cx + fx0 * L['k'], CY + fy0 * L['k'], cx + fx1 * L['k'], CY + fy1 * L['k'])
        def hit():
            return px + pw > face[0] - 12 and py < face[3] + 12 and py + ph > face[1] - 12
        if hit():
            below = int(face[3] + 16)
            above = int(face[1] - 16 - ph)
            if below <= top_max:
                py = max(py, below)
            elif above >= top_min:
                py = above
            while hit() and rf > 26 and pw > 300:        # no room above or below: smaller rows = a narrower panel
                rf -= 1
                pw = int(min(443, max(300, widest * rf / 30 + 100, head_w + 52)))
            if hit():
                L['warn'].append('the checklist panel crosses the FACE box: shorten the steps (a narrower panel), '
                                 "use fewer steps, or raise STYLE['window_x']")
        if face[1] < WIN_TOP + BAR_H + 6:
            L['warn'].append('the title bar covers the top of the FACE box (the head is at the very top of the picture)')
        if face[3] > WIN_TOP + CH + 28 - STRIP_H - 6:
            L['warn'].append('the timeline strip covers the bottom of the FACE box')
    if STYLE['panel_y'] is not None:
        py = int(STYLE['panel_y'])
    L.update(px=px, py=py, pw=pw, ph=ph, rf=rf, rows=rows, title=title, face=face)
    # timeline strip inside the window: its text and track stay left of x 975 (clear of the app's buttons)
    L['tw'] = int(min(CW - 48, 975 - cx - 24))
    L['strip_y'] = WIN_TOP + CH + 28 - STRIP_H
    cap = STYLE['cap_y'] if STYLE['cap_y'] is not None else L['strip_y'] - 52 - STYLE['cap_size']
    L['cap_y'] = int(cap)
    if face and face[3] > L['cap_y'] - 8:
        L['warn'].append("the caption line sits on the FACE box: lower STYLE['cap_size'] or build with CAPTIONS=0")
    # title bar text
    tw_title = text_w(cased(WINDOW_TITLE, 'ui_case'), 26)
    if tw_title > 430:
        stop('WINDOW_TITLE is too long for the title bar: about 28 characters')
    fw = text_w(WINDOW_FILE, 25, True) + 30 if WINDOW_FILE else 0
    L['show_file'] = bool(WINDOW_FILE) and (CW / 2 + fw / 2 + 18 < CW - 24 - tw_title) and (CW / 2 - fw / 2 > 110)
    if WINDOW_FILE and not L['show_file']:
        L['warn'].append('WINDOW_FILE does not fit beside WINDOW_TITLE in the title bar: it is left out')
    return L


# ------------------------------------------------------------------ caption words on the card
def caption_lines(S):
    if os.environ.get('CAPTIONS') == '0' or not os.path.exists('words.json'):
        return []
    a, b = S['f_in'] + 6, (S['out0'] - 1 if S['f_out'] is not None else S['n'])     # while the card is small
    fix = {k.lower(): v for k, v in CAP_FIX.items()}
    mark = {m.lower() for m in CAP_MARK}
    words = []
    for w in json.load(open('words.json')):
        raw = w['text'].strip()
        core = re.sub(r"^[^\w']+|[^\w']+$", '', raw)
        core = fix.get(core.lower(), core)
        if core:
            words.append(dict(t=core, s=w['start'], e=w['end'], brk=bool(re.search(r'[.,!?;:]$', raw))))
    lines, cur = [], []
    for w in words:
        chars = sum(len(x['t']) + 1 for x in cur) + len(w['t'])
        if cur and (len(cur) >= STYLE['cap_words'] or chars > 16 or cur[-1]['brk'] or w['s'] - cur[-1]['e'] > .4):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines):
        f0 = round(ln[0]['s'] * FPS)
        f1 = round(lines[i + 1][0]['s'] * FPS) if i + 1 < len(lines) else round(ln[-1]['e'] * FPS) + 8
        f1 = min(f1, round(ln[-1]['e'] * FPS) + 14)
        f0, f1 = max(f0, a), min(f1, b)
        if f1 - f0 < 3:
            continue
        txt = ' '.join(cased(x['t'], 'cap_case') for x in ln)
        fs = STYLE['cap_size']
        while fs > 34 and text_w(txt, fs, tight=STYLE['cap_tracking']) > CW - 60:
            fs -= 2
        html = ' '.join((f'<b>{esc(cased(x["t"], "cap_case"))}</b>' if x['t'].lower() in mark else esc(cased(x['t'], 'cap_case')))
                        for x in ln)
        out.append(dict(f0=f0, f1=f1, html=html, fs=fs, txt=txt))
    return out


# ------------------------------------------------------------------ sounds (stock names only)
def sound_len(name):
    fp = shutil.which('ffprobe')
    if fp:
        r = subprocess.run([fp, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f'assets/sfx/{name}.mp3'],
                           capture_output=True, text=True).stdout.strip()
        try:
            return float(r)
        except ValueError:
            pass
    return {'whoosh-short': .57, 'pop': .72, 'click-soft': .37}.get(name, .5)


def audio(S, dur):
    if os.environ.get('SFX') == '0' or SOUNDS == []:
        return []
    if SOUNDS == 'auto':
        sfx = [('whoosh-short', S['f_in'] - 1, .2)] + [('click-soft', t, .16) for t in S['ticks'][:-1]]
        sfx.append(('impact-bass-1', S['done'] - 1, .14))
        if S['name'] is not None:
            sfx.append(('pop', S['name'] - 1, .14))
        if S['f_out'] is not None:
            sfx.append(('whoosh-short', S['out0'] - 1, .16))
    else:
        sfx = [(n, int(f), float(v)) for n, f, v in SOUNDS]
    out, lanes = [], []
    for k, (name, f, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        if not os.path.exists(f'assets/sfx/{name}.mp3'):
            print(f'  (sound {name} is not in assets/sfx: skipped)')
            continue
        t = max(0.0, f / FPS)
        d = min(sound_len(name), dur - t)
        if d < .05:
            continue
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d + .01
        out.append(f'  <audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


# ------------------------------------------------------------------ the page
def blocks(tw):
    """timeline blocks: (x, w, frames, frames before it). One plain block when SHOTS is empty."""
    shots = [int(s) for s in SHOTS] or [1]
    if any(s <= 0 for s in shots):
        stop('SHOTS holds a length that is not above 0')
    gap = 4
    usable = tw - gap * (len(shots) - 1)
    tot, out, x, cum = sum(shots), [], 0.0, 0
    for s in shots:
        w = s / tot * usable
        out.append((x, w, s, cum))
        x += w + gap
        cum += s
    if len(shots) > 1 and min(b[1] for b in out) < 9:
        print('  NOTE: a shot is so short that its block is under 9 px wide. That is how long it really is; leave it')
    return out, tot


def css(L):
    st = STYLE
    cx, r = L['cx'], st['radius']
    ui = f"'{st['ui_font']}'"
    mono = f"font-family:'{st['mono_font']}';font-weight:{st['mono_weight']}"
    num = f"font-family:'{st['num_font']}';font-weight:{st['num_weight']}"
    lab = f"font-family:'{st['label_font']}';font-weight:{st['label_weight']};font-style:{'italic' if st['label_italic'] else 'normal'}"
    wh = CH + 28
    c = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000;font-family:{ui};font-weight:{st['ui_weight']};color:{st['ink']}}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#page{{position:absolute;inset:0;background:{st['page']}}}
#under,#over{{position:absolute;inset:0}}
#cardwrap{{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;background:#000}}
.track{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0}}
.winbox{{position:absolute;left:{cx}px;top:{WIN_TOP}px;width:{CW}px;height:{wh}px;border-radius:{r}px}}
#ringshadow{{box-shadow:0 34px 80px -12px rgba(40,30,15,.34),0 10px 26px rgba(40,30,15,.14)}}
#win{{overflow:hidden}}
#ring{{border:3px solid {st['window']};box-shadow:0 0 0 1.5px {rgba(st['ink'], .14)}}}
#ringdone{{border:4px solid {st['done']};box-shadow:0 0 36px 2px {rgba(st['done'], .45)}}}
#tbar{{position:absolute;left:0;top:0;width:{CW}px;height:{BAR_H}px;background:{st['window']};border-bottom:1.5px solid {st['line']}}}
#dots{{position:absolute;left:27px;top:27px;display:flex;gap:10px}}
#dots i{{display:block;width:16px;height:16px;border-radius:50%;background:{st['dots']}}}
#fname{{position:absolute;left:0;top:0;width:{CW}px;height:68px;display:flex;align-items:center;justify-content:center;gap:10px;
  font-size:25px;color:{st['ink']};letter-spacing:-.01em;{mono}}}
#fname .fic{{width:20px;height:20px;border-radius:5px;border:2px solid {st['muted']};position:relative;display:block}}
#fname .fic:after{{content:"";position:absolute;left:5px;top:3px;border-left:7px solid {st['muted']};border-top:5px solid transparent;border-bottom:5px solid transparent}}
#wtitle{{position:absolute;right:24px;top:0;height:68px;display:flex;align-items:center;font-weight:600;font-size:26px;letter-spacing:-.015em;white-space:nowrap}}
#strip{{position:absolute;left:0;top:{wh - STRIP_H}px;width:{CW}px;height:{STRIP_H}px;background:{rgba(st['window'], .91)};
  border-top:1.5px solid rgba(255,255,255,.95);box-shadow:0 -1px 0 {rgba(st['ink'], .10)}}}
#stripflash{{position:absolute;inset:0;background:{st['done']}}}
#srow{{position:absolute;left:24px;top:14px;width:{L['tw']}px;height:36px;display:flex;align-items:center;justify-content:space-between;font-size:23px;{mono}}}
#status{{display:flex;align-items:center;gap:9px;color:{st['muted']}}}
#strun{{display:flex;align-items:center;gap:9px}}
#stdot{{width:11px;height:11px;border-radius:50%;background:{st['accent']};display:block}}
#stdone{{display:none;align-items:center;gap:8px;color:{st['done']}}}
#counter{{color:{st['muted']}}}
#cnum{{color:{st['ink']}}}
#cnum span{{display:none}}
#tlbar{{position:absolute;left:24px;top:62px;width:{L['tw']}px;height:58px}}
.blk{{position:absolute;top:0;height:58px;border-radius:8px;background:{st['track']};overflow:hidden;box-shadow:inset 0 0 0 1.5px {rgba(st['ink'], .10)}}}
.blk .fill{{position:absolute;inset:0;background:{st['accent']};transform-origin:0 50%}}
.blk .bar{{position:absolute;width:3px;border-radius:2px;background:{rgba(st['window'], .62)}}}
.cutm{{position:absolute;top:-8px;width:2px;height:66px;background:{st['faint']};border-radius:1px;transform-origin:50% 0%}}
#ph{{position:absolute;left:-2px;top:-14px;width:4px;height:86px;transform-origin:50% 100%}}
#phline{{position:absolute;left:0;top:10px;width:4px;height:76px;background:{st['ink']};border-radius:2px}}
#phcap{{position:absolute;left:-8px;top:0;width:20px;height:18px;border-radius:6px 6px 9px 9px;background:{st['accent']};box-shadow:0 2px 6px {rgba(st['ink'], .3)}}}
.cc{{position:absolute;left:{cx}px;width:{CW}px;top:{L['cap_y']}px;text-align:center;color:{st['cap_color']};font-family:'{st['cap_font']}';
  font-weight:{st['cap_weight']};letter-spacing:{st['cap_tracking']}em;line-height:1;white-space:nowrap;
  text-shadow:0 6px 26px rgba(0,0,0,.7),0 2px 6px rgba(0,0,0,.5);transform-origin:50% 50%}}
.cc b{{font-weight:{st['cap_weight']};color:{st['cap_mark']}}}
#paneldrift{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:{L['px'] + L['pw'] // 2}px {L['py'] + L['ph'] // 2}px}}
#panel{{position:absolute;left:{L['px']}px;top:{L['py']}px;width:{L['pw']}px;height:{L['ph']}px;background:{st['panel']};border-radius:24px;
  border:1.5px solid {st['line']};box-shadow:0 30px 60px -14px rgba(40,30,15,.30),0 6px 14px rgba(40,30,15,.10);
  padding:24px 24px 0 24px;transform-origin:0 50%}}
#phead{{display:flex;align-items:center;gap:10px;height:46px}}
#phead .pd{{width:16px;height:16px;border-radius:50%;background:{st['accent']};display:block;flex:0 0 16px}}
#phead .lbl{{font-size:27px;color:{st['muted']};letter-spacing:-.012em;white-space:nowrap}}
#pill{{margin-left:4px;font-size:24px;line-height:1;background:{st['accent']};color:{st['accent_text']};border-radius:999px;padding:8px 15px 9px;white-space:nowrap;{mono}}}
#prog{{position:relative;margin-top:16px;height:5px;border-radius:3px;background:{st['line']};overflow:hidden}}
#progfill{{position:absolute;inset:0;background:{st['accent']};border-radius:3px;transform-origin:0 50%}}
#rows{{margin-top:10px}}
.row{{position:relative;height:64px;display:flex;align-items:center;gap:14px}}
.row .flash{{position:absolute;left:-12px;right:-12px;top:5px;bottom:5px;border-radius:14px;background:{rgba(st['done'], .16)}}}
.ck{{position:relative;width:34px;height:34px;flex:0 0 34px}}
.ck .e{{position:absolute;inset:0;border-radius:50%;border:2.5px solid {st['line']}}}
.ck .s{{position:absolute;inset:0}}
.ck .g{{position:absolute;inset:0;border-radius:50%;background:{st['done']};box-shadow:0 4px 10px -2px {rgba(st['done'], .55)}}}
.ck .m{{position:absolute;inset:0}}
.row .rt{{position:relative;font-size:{L['rf']}px;line-height:1;letter-spacing:-.014em;color:{st['faint']};white-space:nowrap}}
#readdrift,#digdrift{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
'''
    if 'cols' in L:
        cell, b = L['cell'], L['badge']
        c += f'''#digpos{{position:absolute;left:{L['dig_x']}px;top:{L['dig_y']}px;width:{L['dig_w']}px;height:{cell}px}}
#digitswrap{{position:absolute;left:0;top:0;transform-origin:72% 80%}}
.band{{position:absolute;left:0;width:100%;height:{round(cell * .13)}px;z-index:2}}
#bandt{{top:-1px;background:linear-gradient({st['page']},{rgba(st['page'], 0)})}}
#bandb{{bottom:-1px;background:linear-gradient({rgba(st['page'], 0)},{st['page']})}}
#digits{{position:relative;display:flex;height:{cell}px;transform-origin:0 100%;{num};font-size:{L['nf']:.1f}px;line-height:{cell}px;color:{st['ink']}}}
.col{{position:relative;height:{cell}px;overflow:hidden}}
.col .st{{position:absolute;left:0;top:0;width:100%}}
.col .st div{{height:{cell}px;text-align:center}}
#pct{{position:absolute;left:{L['badge_x']}px;top:{L['badge_y']}px;width:{b}px;height:{b}px;border-radius:50%;background:{st['accent']};
  box-shadow:0 12px 26px -8px {rgba(st['ink'], .5)},inset 0 -4px 0 rgba(0,0,0,.08);display:flex;align-items:center;justify-content:center;
  {num};font-size:{round(b * (.61 if len(COUNT_UNIT) < 2 else .42))}px;line-height:1;color:{st['accent_text']}}}
#pct span{{display:block;margin-top:-4px}}
#pctring{{position:absolute;left:{L['badge_x']}px;top:{L['badge_y']}px;width:{b}px;height:{b}px;border-radius:50%;border:4px solid {st['accent']}}}
'''
    if 'lab_y' in L:
        c += (f"#lab1{{position:absolute;left:40px;top:{L['lab_y']}px;height:{L['lab_fs'] + 2}px;white-space:nowrap;{lab};"
              f"font-size:{L['lab_fs']}px;line-height:{L['lab_fs'] + 2}px;color:{st['ink']}}}\n#lab1 span{{display:inline-block}}\n")
    if 'name_y' in L:
        h = L['name_h']
        c += f'''#slabwrap{{position:absolute;left:40px;top:{L['name_y']}px;height:{h}px;transform-origin:0 60%}}
#slab{{position:absolute;inset:0;background:{st['highlight']};border-radius:10px;transform-origin:0 50%;box-shadow:0 8px 18px -8px rgba(60,50,0,.45)}}
#nclip{{position:relative;height:{h}px;padding:0 16px}}
#nword{{display:block;{num};font-size:{L['name_fs']}px;line-height:{round(h * .95)}px;color:{st['ink']};letter-spacing:-.005em;white-space:nowrap}}
'''
    return c


def page(S, L, dur):
    st = STYLE
    cx, k = L['cx'], L['k']
    n = len(L['rows'])
    blks, tot = blocks(L['tw'])
    rnd = random.Random(SEED)
    tw = []                                   # timeline lines
    T0 = F(S['f_in'])
    TD = F(S['done'])
    OUT = F(S['out0']) if S['f_out'] is not None else dur
    sx, sy = 1080 / CW, 1920 / CH
    home = f'x:{-cx * sx:.2f},y:{-CY * sy:.2f},scaleX:{sx:.5f},scaleY:{sy:.5f}'

    # ---- markup
    bl = []
    for i, (x, w, s, cum) in enumerate(blks):
        bars = ''
        nb = int((w - 6) // 6) if w >= 12 else 0
        pad = (w - (nb * 6 - 3)) / 2 if nb else 0
        for j in range(nb):
            bh = 10 + round(rnd.random() * 30 * (.55 + .45 * (abs(((j + i * 3) * .7) % 2 - 1))))
            bars += f'<i class="bar" style="left:{pad + j * 6:.1f}px;top:{29 - bh / 2:.1f}px;height:{bh}px"></i>'
        bl.append(f'<div class="blk" id="blk{i}" style="left:{x:.2f}px;width:{w:.2f}px"><div class="fill" id="fill{i}"></div>{bars}</div>')
        if i > 0:
            bl.append(f'<div class="cutm" id="cut{i}" style="left:{x - 3:.2f}px"></div>')
    count_frames = list(range(S['land'] + 2, S['done'] + 1)) if SHOTS else []
    PH0, PH1 = F(S['land'] + 2), TD
    spans = ''
    if SHOTS:
        pad = len(str(tot))
        for f in count_frames:
            x = (F(f) - PH0) / (PH1 - PH0) * L['tw']
            val = tot
            if f < S['done']:
                for (bx, bw, bs, cum) in blks:
                    if x <= bx + bw:
                        val = round(cum + max(0.0, (x - bx) / bw) * bs)
                        break
            spans += f'<span id="cn{f}">{str(min(val, tot)).zfill(pad)}</span>'
    counter = f'<div id="counter"><span id="cnum">{spans}</span><span> / {tot}</span></div>' if SHOTS else ''
    rows = ''
    for i, t in enumerate(L['rows']):
        rows += (f'<div class="row" id="row{i}"><div class="flash" id="flash{i}"></div><div class="ck"><div class="e" id="cke{i}"></div>'
                 f'<svg class="s" id="cks{i}" width="34" height="34" viewBox="0 0 34 34"><circle cx="17" cy="17" r="15.75" fill="none" '
                 f'stroke="{st["accent"]}" stroke-width="2.8" stroke-linecap="round" stroke-dasharray="34 99"/></svg>'
                 f'<div class="g" id="ckg{i}"></div><svg class="m" width="34" height="34" viewBox="0 0 34 34"><path id="ckm{i}" '
                 f'd="M10 17.6 L15.2 22.6 L24.4 12.2" fill="none" stroke="#FFFFFF" stroke-width="3.6" stroke-linecap="round" '
                 f'stroke-linejoin="round" stroke-dasharray="22" stroke-dashoffset="22"/></svg></div>'
                 f'<span class="rt" id="rt{i}">{esc(t)}</span></div>\n')
    pill = f'<span id="pill">{esc(PANEL_TAG)}</span>' if PANEL_TAG else ''
    fname = (f'<div id="fname"><i class="fic"></i><span>{esc(WINDOW_FILE)}</span></div>' if L['show_file'] else '')
    digits = readout = ''
    if 'cols' in L:
        cols = ''.join(f'<div class="col" style="width:{round(w * L["nf"])}px"><div class="st" id="col{i}">'
                       + ''.join(f'<div>{d}</div>' for d in cells) + '</div></div>' for i, (cells, kind, w) in enumerate(L['cols']))
        digits = (f'<div id="digdrift"><div id="digpos"><div id="digitswrap"><div id="digits">{cols}'
                  '<div class="band" id="bandt"></div><div class="band" id="bandb"></div></div></div></div></div>')
        if COUNT_UNIT:
            readout += f'<div id="pctring"></div><div id="pct"><span>{esc(COUNT_UNIT)}</span></div>'
    if 'lab_y' in L:
        ws = L['lab_txt'].split()
        readout += '<div id="lab1">' + '<span style="width:14px"></span>'.join(
            ''.join(f'<span class="lc lw{wi}">{esc(ch)}</span>' for ch in w) for wi, w in enumerate(ws)) + '</div>'
    if 'name_y' in L:
        readout += f'<div id="slabwrap"><div id="slab"></div><div id="nclip"><span id="nword">{esc(L["name_txt"])}</span></div></div>'
    caps = caption_lines(S)
    cap_html = '\n'.join(f'<div id="cc{i}" class="cc" style="font-size:{c["fs"]}px">{c["html"]}</div>' for i, c in enumerate(caps))

    # ---- start states
    tw += ["gsap.set(['#page','#under','#over'],{autoAlpha:0});",
           "gsap.set('#cardwrap',{transformOrigin:'0 0',x:0,y:0,scale:1,borderRadius:0});",
           f"gsap.set('.track',{{{home}}});",
           "gsap.set(['#ring','#ringshadow','#ringdone','#stripflash'],{opacity:0});",
           "gsap.set('#tbar',{opacity:0,y:-16});", "gsap.set('#dots i',{scale:0});",
           "gsap.set('#wtitle',{opacity:0,y:8});", "gsap.set('#strip',{opacity:0,y:40});",
           "gsap.set('.blk',{opacity:0,scaleY:.2});", "gsap.set('.blk .fill',{scaleX:0});",
           "gsap.set('#ph',{opacity:0,scaleY:0});",
           "gsap.set('#panel',{opacity:0,x:-70,scale:.94});", "gsap.set('.row',{opacity:0,x:-14});",
           "gsap.set('.ck .s',{opacity:0,transformOrigin:'50% 50%'});", "gsap.set('.ck .g',{scale:0});",
           "gsap.set('.row .flash',{opacity:0});", "gsap.set('#progfill',{scaleX:0});"]
    if L['show_file']:
        tw.append("gsap.set('#fname',{opacity:0,y:8});")
    if len(blks) > 1:
        tw.append("gsap.set('.cutm',{scaleY:0,opacity:0});")
    if caps:
        tw.append("gsap.set('.cc',{autoAlpha:0});")

    # ---- the shrink: the picture becomes the card, the window chrome rides in with it
    tw += [f"tl.set(['#page','#under','#over'],{{autoAlpha:1}},{T0:.3f});",
           f"tl.to('#cardwrap',{{x:{cx},y:{CY},scale:{k:.5f},borderRadius:{st['radius'] / k:.1f},duration:{SHRINK / FPS:.3f},ease:'expo.out'}},{T0:.3f});",
           f"tl.to('.track',{{x:0,y:0,scaleX:1,scaleY:1,duration:{SHRINK / FPS:.3f},ease:'expo.out'}},{T0:.3f});",
           f"tl.to(['#ring','#ringshadow'],{{opacity:1,duration:.16,ease:'power2.out'}},{T0 + .05:.3f});",
           f"tl.to('#tbar',{{opacity:1,y:0,duration:.22,ease:'power3.out'}},{T0 + .11:.3f});",
           f"tl.to('#dots i',{{scale:1,duration:.22,ease:'back.out(2.6)',stagger:.035}},{T0 + .17:.3f});",
           f"tl.to('#wtitle',{{opacity:1,y:0,duration:.2,ease:'power2.out'}},{T0 + .25:.3f});",
           f"tl.to('#strip',{{opacity:1,y:0,duration:.24,ease:'expo.out'}},{T0 + .13:.3f});"]
    if L['show_file']:
        tw.append(f"tl.to('#fname',{{opacity:1,y:0,duration:.2,ease:'power2.out'}},{T0 + .21:.3f});")
    step = min(.04, .2 / len(blks))
    for i in range(len(blks)):
        t = T0 + .17 + i * step
        tw += [f"tl.to('#blk{i}',{{opacity:1,duration:.08,ease:'none'}},{t:.3f});",
               f"tl.to('#blk{i}',{{scaleY:1,duration:.26,ease:'back.out(2.4)'}},{t + .001:.3f});"]
        if i > 0:
            tw.append(f"tl.to('#cut{i}',{{opacity:1,scaleY:1,duration:.2,ease:'back.out(2)'}},{t + .02:.3f});")
    tw.append(f"tl.to('#ph',{{opacity:1,scaleY:1,duration:.12,ease:'back.out(2)'}},{T0 + .31:.3f});")

    # ---- the playhead runs over the whole reel and reaches the end on DONE_AT
    PD = PH1 - PH0
    tw.append(f"tl.to('#ph',{{x:{L['tw']},duration:{PD:.3f},ease:'none'}},{PH0:.3f});")
    for i, (x, w, s, cum) in enumerate(blks):
        tw.append(f"tl.to('#fill{i}',{{scaleX:1,duration:{max(.02, w / L['tw'] * PD):.3f},ease:'none'}},{PH0 + x / L['tw'] * PD:.3f});")
    if count_frames:
        tw.append(f"gsap.set('#cn{count_frames[0]}',{{display:'inline'}});")
        tw.append(' '.join(f"tl.set('#cn{f - 1}',{{display:'none'}},{F(f):.3f}); tl.set('#cn{f}',{{display:'inline'}},{F(f):.3f});"
                           for f in count_frames[1:]))       # one line: the lint warns about very long pages
    blink = max(1, round(PD / .34))
    tw.append(f"tl.to('#stdot',{{opacity:.25,duration:{PD / (2 * blink):.3f},ease:'sine.inOut',repeat:{2 * blink - 1},yoyo:true}},{PH0:.3f});")

    # ---- checklist
    tw += [f"tl.to('#panel',{{opacity:1,duration:.14,ease:'power1.out'}},{T0 + .17:.3f});",
           f"tl.to('#panel',{{x:0,scale:1,duration:.30,ease:'expo.out'}},{T0 + .171:.3f});",
           f"tl.to('.row',{{opacity:1,x:0,duration:.18,ease:'power2.out',stagger:.022}},{T0 + .24:.3f});"]
    for i, tf in enumerate(S['ticks']):
        s = F(tf) - 2 / FPS                    # starts two frames early so the tick is fully ON at its frame
        a = (T0 + .29) if i == 0 else F(S['ticks'][i - 1])
        gap = min(.2, (S['ticks'][i + 1] - tf) / FPS - .02) if i + 1 < n else .06
        tw.append(' '.join([
               f"tl.set('#cks{i}',{{opacity:1}},{a:.3f});",
               f"tl.to('#cks{i}',{{rotation:{360 * max(1, round((s - a) / .3))},duration:{s - a + .02:.3f},ease:'none'}},{a:.3f});",
               f"tl.to('#rt{i}',{{color:'{st['muted']}',duration:.05,ease:'none'}},{a:.3f});",
               f"tl.set('#cks{i}',{{opacity:0}},{s + .021:.3f});",
               f"tl.to('#cke{i}',{{opacity:0,duration:.05,ease:'none'}},{s:.3f});",
               f"tl.to('#ckg{i}',{{scale:1,duration:.2,ease:'back.out(3.2)'}},{s:.3f});",
               f"tl.to('#ckm{i}',{{strokeDashoffset:0,duration:.1,ease:'power2.out'}},{s + .01:.3f});",
               f"tl.to('#rt{i}',{{color:'{st['ink']}',duration:.06,ease:'none'}},{s:.3f});",
               f"tl.to('#flash{i}',{{opacity:1,duration:.05,ease:'none'}},{s:.3f});",
               f"tl.to('#flash{i}',{{opacity:0,duration:.42,ease:'power2.out'}},{s + .07:.3f});",
               f"tl.to('#progfill',{{scaleX:{(i + 1) / n:.4f},duration:{gap:.3f},ease:'power3.out'}},{s:.3f});"]))
    tw.append(f"tl.to('#progfill',{{backgroundColor:'{st['done']}',duration:.06,ease:'none'}},{TD - 2 / FPS:.3f});")

    # ---- counter
    if 'cols' in L:
        O0 = F(S['count_at'])
        cell = L['cell']
        tw += ["gsap.set('#digits',{opacity:0,y:34,scale:.9});",
               f"tl.to('#digits',{{opacity:1,duration:.07,ease:'none'}},{O0 - 1 / FPS:.3f});",
               f"tl.to('#digits',{{y:0,scale:1,duration:.3,ease:'back.out(1.7)'}},{O0 - 1 / FPS + .001:.3f});"]
        for i, (cells, kind, w) in enumerate(L['cols']):
            if kind == 'late':
                tw.append(f"tl.to('#col{i}',{{y:{-cell},duration:.15,ease:'power2.out'}},{TD - .15:.3f});")
            else:
                tw.append(f"tl.to('#col{i}',{{y:{-(len(cells) - 1) * cell},duration:{TD - O0:.3f},ease:'power1.out'}},{O0:.3f});")
        tw += [f"tl.set('.band',{{opacity:0}},{TD:.3f});",
               f"tl.fromTo('#digitswrap',{{scale:1.05}},{{scale:1,duration:.6,ease:'elastic.out(1, 0.42)',immediateRender:false}},{TD:.3f});"]
        if COUNT_UNIT:
            tw += ["gsap.set('#pct',{scale:0,rotation:-50});", "gsap.set('#pctring',{opacity:0,scale:1});",
                   f"tl.to('#pct',{{scale:1,rotation:-8,duration:.32,ease:'back.out(2.6)'}},{TD - 2 / FPS:.3f});",
                   f"tl.fromTo('#pctring',{{opacity:.8,scale:1}},{{opacity:0,scale:1.75,duration:.5,ease:'power2.out',immediateRender:false}},{TD:.3f});"]

    # ---- done: the timeline turns to the done colour on DONE_AT
    tw += [f"tl.set('.blk .fill',{{backgroundColor:'{st['done']}'}},{TD:.3f});",
           f"tl.set('#phcap',{{backgroundColor:'{st['done']}'}},{TD:.3f});",
           f"tl.set('#strun',{{display:'none'}},{TD:.3f});", f"tl.set('#stdone',{{display:'flex'}},{TD:.3f});",
           f"tl.set('#stripflash',{{opacity:.5}},{TD:.3f});",
           f"tl.to('#stripflash',{{opacity:.07,duration:.6,ease:'power2.out'}},{TD + .07:.3f});",
           f"tl.set('#ringdone',{{opacity:.9}},{TD:.3f});",
           f"tl.to('#ringdone',{{opacity:0,duration:.7,ease:'power2.out'}},{TD + .08:.3f});",
           f"tl.to('.blk',{{scaleY:1.14,duration:.07,ease:'power2.out',stagger:.015}},{TD:.3f});",
           f"tl.to('.blk',{{scaleY:1,duration:.3,ease:'back.out(2.5)',stagger:.015}},{TD + .075:.3f});"]
    if SHOTS:
        tw.append(f"tl.set('#cnum',{{color:'{st['done']}'}},{TD:.3f});")

    # ---- the line under the counter, the highlighted name
    if 'lab_y' in L:
        tw.append("gsap.set('.lc',{opacity:0,y:20});")
        for wi, f in enumerate(S['label']):
            tw.append(f"tl.to('.lw{wi}',{{opacity:1,y:0,duration:.18,ease:'back.out(1.8)',stagger:.016}},{F(f):.3f});")
    if 'name_y' in L:
        C0 = F(S['name'])
        tw += ["gsap.set('#slabwrap',{rotation:-2});", "gsap.set('#slab',{scaleX:0});",
               "gsap.set('#nclip',{clipPath:'inset(-10% 100% -10% 0%)'});",
               f"tl.to('#slab',{{scaleX:1,duration:.22,ease:'expo.out'}},{C0:.3f});",
               f"tl.to('#nclip',{{clipPath:'inset(-10% 0% -10% 0%)',duration:.22,ease:'expo.out'}},{C0:.3f});",
               f"tl.fromTo('#slabwrap',{{scale:1.11,rotation:-5}},{{scale:1,rotation:-2,duration:.55,ease:'elastic.out(1, 0.45)',immediateRender:false}},{C0 + 2 / FPS:.3f});"]

    # ---- caption words on the card
    for i, c in enumerate(caps):
        tw += [f"tl.fromTo('#cc{i}',{{autoAlpha:0,scale:1.14}},{{autoAlpha:1,scale:1,duration:.13,ease:'power3.out',immediateRender:false}},{max(0, F(c['f0']) - .03):.3f});",
               f"tl.set('#cc{i}',{{autoAlpha:0}},{F(c['f1']):.3f});"]

    # ---- slow drift while it holds, then the way back to the plain picture
    hold = OUT - (T0 + .55)
    side = "['#readdrift','#digdrift']" if digits else "'#readdrift'"
    if hold > .4:
        tw.append(f"tl.to('#paneldrift',{{y:-9,rotation:-.35,duration:{hold - .06:.3f},ease:'sine.inOut'}},{T0 + .55:.3f});")
        if (readout or digits) and OUT - TD > .6:
            tw.append(f"tl.to({side},{{y:-7,duration:{OUT - TD - .3:.3f},ease:'sine.inOut'}},{TD + .2:.3f});")
    if S['f_out'] is not None:
        g = (GROW - 1) / FPS
        E = F(S['f_out'])
        tw += [f"tl.to(['#tbar','#strip','#ring','#ringshadow'],{{opacity:0,duration:.1,ease:'power1.in'}},{OUT:.3f});",
               f"tl.to('#panel',{{opacity:0,x:-50,duration:.13,ease:'power2.in'}},{OUT - .03:.3f});",
               f"tl.to({side},{{opacity:0,duration:.12,ease:'power1.in'}},{OUT - .03:.3f});",
               f"tl.to('#cardwrap',{{x:0,y:0,scale:1,borderRadius:0,duration:{g:.3f},ease:'expo.inOut'}},{OUT:.3f});",
               f"tl.to('.track',{{{home},duration:{g:.3f},ease:'expo.inOut'}},{OUT:.3f});",
               f"tl.set('#cardwrap',{{x:0,y:0,scale:1,borderRadius:0}},{E:.3f});",
               f"tl.set(['#page','#under','#over'],{{autoAlpha:0}},{E:.3f});"]

    nl = '\n'
    v = f'muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}"'
    doc = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css(L)}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(S, dur))}
  <div id="page"></div>
  <div id="under">
    {digits}
    <div class="track"><div id="ringshadow" class="winbox"></div></div>
  </div>
  <div id="cardwrap"><video id="bgv" class="full" src="assets/aroll.mp4" {v} data-track-index="0"></video></div>
  <div id="over">
    <div class="track">
      <div id="win" class="winbox">
        <div id="tbar"><div id="dots"><i></i><i></i><i></i></div>{fname}<div id="wtitle"><span>{esc(cased(WINDOW_TITLE, 'ui_case'))}</span></div></div>
        <div id="strip"><div id="stripflash"></div>
          <div id="srow"><div id="status"><span id="strun"><i id="stdot"></i><span>{esc(STATUS_RUN)}</span></span>
            <span id="stdone"><svg width="22" height="22" viewBox="0 0 22 22"><path d="M4 11.5 L9 16.5 L18.5 6" fill="none" stroke="{st['done']}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg><span>{esc(STATUS_DONE)}</span></span></div>
            {counter}</div>
          <div id="tlbar">{''.join(bl)}<div id="ph"><div id="phline"></div><div id="phcap"></div></div></div>
        </div>
      </div>
      <div id="ring" class="winbox"></div>
      <div id="ringdone" class="winbox"></div>
    </div>
{cap_html}
    <div id="paneldrift"><div id="panel">
      <div id="phead"><i class="pd"></i><span class="lbl">{esc(L['title'])}</span>{pill}</div>
      <div id="prog"><div id="progfill"></div></div>
      <div id="rows">
{rows}      </div>
    </div></div>
    <div id="readdrift">{readout}</div>
  </div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    return doc, caps


def main():
    os.chdir(HERE)
    if not os.path.exists('clip.json'):
        stop('no clip.json here: run this from a slot folder')
    n = int(json.load(open('clip.json'))['frames'])
    dur = n / FPS
    S = schedule(n)
    L = layout(S)
    doc, caps = page(S, L, dur)
    open('index.html', 'w').write(doc)
    slot = os.path.basename(HERE)
    cx = L['cx']
    print(f'wrote index.html  {n} frames')
    print(f'  shrink f{S["f_in"]} to f{S["land"]}   ticks {", ".join("f%d" % t for t in S["ticks"])}   DONE f{S["done"]}'
          + (f'   counter from f{S["count_at"]} lands on {COUNT_TO}{COUNT_UNIT} at f{S["done"]}' if S['count_at'] is not None else '')
          + (f'   label {", ".join("f%d" % t for t in S["label"])}' if S['label'] else '')
          + (f'   name f{S["name"]}' if S['name'] is not None else ''))
    print('  ' + (f'grows back f{S["out0"]} to f{S["f_out"]}: plain picture from f{S["f_out"]} to the last frame'
                  if S['f_out'] is not None else "F_OUT = 'cut': the window stays to the last frame, the reel must CUT there"))
    print(f'  window x {cx} to {cx + CW}, y {WIN_TOP} to {WIN_TOP + CH + 28}; checklist x {L["px"]} to {L["px"] + L["pw"]}, y {L["py"]} to '
          f'{L["py"] + L["ph"]} (covers {max(0, L["px"] + L["pw"] - cx)} px of the card\'s left edge); caption line y {L["cap_y"]}')
    if caps:
        print('  caption words on the card (reel captions: hide them for this slot): '
              + ' | '.join(f'f{c["f0"]} {c["txt"]}' for c in caps))
    elif os.environ.get('CAPTIONS') == '0':
        print('  CAPTIONS=0: no caption words drawn. The reel\'s own captions are centred on the frame, not on the card')
    if cx + CW > 980:
        print(f'  NOTE: the window reaches x {cx + CW}: below y 1155 its right edge sits under the app\'s buttons (no text there)')
    if any(s in PLACEHOLDERS for s in S['steps']):
        print('  WARNING: STEPS still holds placeholders ("Step one" ...). Replace them with real steps of this edit')
    if not SHOTS:
        print('  NOTE: SHOTS is empty: the timeline is one plain bar with no frame count. Fill it from the reel\'s edit list')
    if COUNT_TO is None:
        print('  NOTE: COUNT_TO is None: no counter. Set it only to a number the speaker says')
    for w in L['warn']:
        print('  WARNING: ' + w)
    if FACE is None:
        print('  NOTE: FACE is not set: look at a SAFE=1 snapshot and make sure the checklist panel is not on the face')
    snaps = sorted({S['f_in'] + 6, S['land'] + 1, S['ticks'][0], S['ticks'][len(S['ticks']) // 2], S['done'] - 3, S['done'],
                    S['last'] + 4} | ({S['out0'] + 6} if S['f_out'] is not None else set()))
    print('  snapshot times: ' + ','.join(f'{f / FPS + .017:.3f}' for f in snaps))
    print(f'render to renders/{slot}.mp4' + ('   (SAFE guide is ON: snapshots only)' if os.environ.get('SAFE') else ''))


if __name__ == '__main__':
    main()
