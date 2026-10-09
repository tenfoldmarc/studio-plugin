#!/usr/bin/env python3
"""UI WORLD: an app screen drops in over the top of the frame and the speaker stands in front of it. Their cutout sits
over the screen, the real room only shows in the band below their chest, and the screen plays along with their line.

  F_IN      the screen drops in from the top and the shot reframes so their head sits under it
  chat      (SCREEN = 'chat') things land in the message box, a line types, it sends, a reply streams in, a
            step card ticks, a result card pops in beside their head: each on the frame of a spoken word
  media     (SCREEN = an image or a screen recording you supply) your own app or page fills the screen instead
  F_OUT     optional: the screen lifts away again and the shot goes back to normal

Layers: room plate < screen < their shadow on the screen < their cutout (faded out below the chest line) < captions.

Run order (from the slot folder, see effect.md):
  python onsets.py        word onsets as frames  -> fill the CLIP block
  python prep.py          measure the speaker + clean cutout -> work/measure.json, work/measure.jpg (look at it)
  python3 build.py        writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no caption words, SFX=0 no sounds)
"""
import json
import os
import re
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
# What is on the screen. 'chat' = the packaged chat-style screen filled with YOUR text (fields below). Or the path of
# a picture / screen recording of your own app or page, e.g. 'assets/screen.png' or 'assets/screen.mp4' (portrait,
# at least 1080 wide; a recording must be at least as long as the slot). Only show screens you have the right to show.
SCREEN = 'chat'
APP_NAME = 'Claude'      # chat: the name in the header (your app, your tool, your page)
APP_MARK = None          # chat: small logo next to the name, an svg / png you supply in assets_fx/. None = no logo
GREETING = 'What are we making today?'   # chat: line in the empty screen before anything happens. None = none
PLACEHOLDER = 'How can I help you today?'  # chat: grey text in the empty message box
# Chat story. Every frame number is the frame of the spoken word the thing lands on (from `python onsets.py`).
# Any part can be None and is then left out. REPLY and STEPS need SEND.
ATTACH = (25, ['Clip 1', 'Clip 2', 'Clip 3', 'Clip 4', 'Clip 5'])   # (frame, 1 to 5 things that fly into the box).
#                          Each thing is a short label, or the path of a picture ('assets/screen/a.jpg') for a thumbnail
TYPE = (54, '/edit-my-reel')   # (frame, text typed into the box, max ~30 characters). A leading "/" gets a tinted pill
SEND = 74                # frame the message is sent (button click, the box drops away, the message moves up)
REPLY = (79, 'On it. Editing your reel.')   # (frame, the answer that streams in word by word, max ~34 characters)
STEPS = ('Editing your reel', [(87, 'Picked your best takes'), (93, 'Cut the dead air'),
                               (99, 'Cut you out of the background'), (105, 'Added captions and sound')])
#                          (card title, [(frame, row text), ...]) 1 to 4 rows: each row appears on its frame and
#                          ticks 5 frames later. Rows max ~30 characters
RESULT = (112, 'reel-final.mp4', None, 'Ready')   # (frame, title, picture path or None, badge text): the card that
#                          pops in beside the speaker's head on the payoff word. A 9:16 picture works best
LABELS = [(39, 'RAW CLIPS', 'attach'), (67, 'ONE COMMAND', 'text')]   # highlighter tags: (frame, TEXT, where).
#                          where = 'attach' (beside the attachments), 'text' (after the typed text) or (x, y) frame px
#                          read off a SAFE=1 snapshot. [] = none. Tags placed before SEND leave when it sends

F_IN = 0                 # frame the screen drops in (the frames before it are untouched a-roll)
F_OUT = None             # frame the screen lifts away again. None = it stays to the last frame
EDGE = None              # y (frame px) of the bottom edge of the screen = the speaker's chest line. None = measured from the speaker's
#                          cutout (neck + 0.45 head). Set it by eye if work/measure.jpg shows the pink line off
HEAD_Y = 860             # y the top of the speaker's head is moved down to, so the screen has room above it (the speaker is never
#                          moved up; if the speaker already sits lower the speaker stays where the speaker is). 760 to 900 works
ZOOM = None              # punch-in on the speaker. None = measured (up to 1.25 when the speaker's head is under 190px tall). 1 = none
RESULT_SIDE = None       # 'L' or 'R': side of the speaker's head the result card lands on. None = the side with more room
ACCENT = '#1F1E1D'       # button / progress colour: your app's brand colour
HILITE = '#FAE67A'       # highlighter tag colour (butter yellow)
CAPTION_FIX = {}         # captions come from words.json: fix what Whisper misheard, {'claw': 'Claude'}; '' drops a word
CAP_Y = None             # y of the caption line in the room band. None = 114px under the chest line
SCREEN_ZOOM = 1.0        # media: 1 = the picture fills the frame width; more = closer
SCREEN_X = 0             # media: px to slide the picture sideways (negative = left)
SCREEN_Y = 0             # media: px to slide the picture down (negative = up). The top 220px sits under app chrome
SCREEN_SCROLL = 0        # media: px the picture scrolls up over the slot (a long page). 0 = still
SHADOW = .26             # how dark the speaker's shadow on the screen is (0 = none)
FIX_EDGE = True          # use the cleaned cutout from prep.py (assets/fg.webm). False = assets/subject.webm as is
VOICE = True             # False = silent slot (no a-roll audio in the render)
SOUNDS = None            # None = whoosh on F_IN and ATTACH, pop on the first tag and on RESULT, click on SEND.
#                          Or your own list [(sound, frame, base volume)], played at 0.75x. [] = none
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
FP = shutil.which('ffprobe') or 'ffprobe'
SFX_GAIN = 0.75
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'sparkle': 1.8, 'click': .3, 'click-soft': .37, 'impact-bass-1': 1.0}
INK = '#1F1E1D'
JOINERS = {'AND', 'OR', 'BUT', 'SO', 'THE', 'A', 'AN', 'TO', 'OF', 'IN', 'ON', 'FOR', 'WITH', 'MY', 'YOUR', "I'LL", 'IS'}
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')

# chat geometry (frame px)
HEAD_BOT = 322                                   # bottom of the header strip
COMP_L, COMP_W = 50, 980
CHIP_W, CHIP_H, CHIP_GAP = 124, 220, 16
COMP_PAD = (26, 28, 22)                          # top, sides, bottom
TEXT_H, BAR_GAP, BAR_H = 60, 14, 64
UM_TOP, TH_W, TH_H = 332, 64, 114                # sent message row, its small thumbnails
CL_ROW, CARD_TOP, CARD_W, ROW_H = 476, 556, 650, 60
RES_W = 300


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def text_w(s, px, heavy=False):
    """rough width of a line of Inter at px (good to about 6%): only used to place things next to text"""
    w = 0.0
    for ch in s:
        if ch in "iljtfr.,:;'!|/ -":
            w += .34
        elif ch in 'mwMW@':
            w += .9
        elif ch.isupper():
            w += .70
        elif ch.isdigit():
            w += .63
        else:
            w += .57
    return w * px * (1.04 if heavy else 1.0)


def is_pic(s):
    return isinstance(s, str) and s.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))


def check(size):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 28 28"><circle cx="14" cy="14" r="14" fill="#3F8F5A"/>'
            '<path d="M8 14.5l4 4 8-9" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def play(size, bg='rgba(20,18,16,.42)'):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="{bg}"/>'
            '<path d="M9.6 7.4l7 4.6-7 4.6z" fill="#fff"/></svg>')


PLUS = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#5E5D59" stroke-width="2.2" stroke-linecap="round">'
        '<path d="M12 5v14M5 12h14"/></svg>')
SLIDERS = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#5E5D59" stroke-width="2" stroke-linecap="round">'
           '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/></svg>')
ARROW_UP = ('<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.8" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/></svg>')
DOC = ('<svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#8C8A83" stroke-width="1.6" stroke-linecap="round" '
       'stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>')


def mark(size, id_=''):
    idattr = f' id="{id_}"' if id_ else ''
    if APP_MARK:
        return f'<img{idattr} src="{APP_MARK}" alt="" style="width:{size}px;height:{size}px;object-fit:contain;flex:none">'
    return ''


def captions(words, nfr, t_hide):
    """caption groups from words.json: up to 3 words, a new group at every pause or punctuation mark"""
    groups, cur = [], []
    for w in words:
        key = re.sub(r"[^a-z0-9']", '', w['text'].lower())
        txt = CAPTION_FIX.get(key, w['text'])
        if txt == '':
            continue
        txt = re.sub(r'[,;:]+$', '', txt.strip()).upper()
        if cur and (len(cur) >= 3 or w['start'] - cur[-1]['e'] > .22 or cur[-1]['brk']
                    or sum(len(c['t']) for c in cur) + len(txt) > 15):
            carry = []
            if len(cur) > 1 and not cur[-1]['brk'] and cur[-1]['t'] in JOINERS:
                carry = [cur.pop()]                            # a line never ends on "and", "the", "to"...
            groups.append(cur)
            cur = carry
        cur.append({'t': txt, 's': w['start'], 'e': w['end'], 'brk': w['text'].strip()[-1:] in ',.?!;:'})
    if cur:
        groups.append(cur)
    html, tw = [], []
    for g, grp in enumerate(groups):
        a = max(0.0, grp[0]['s'] - .03)
        nxt = groups[g + 1][0]['s'] - .03 if g + 1 < len(groups) else None
        b = nxt if nxt is not None and nxt - grp[-1]['e'] < .6 else min(grp[-1]['e'] + .35, nfr / FPS)
        if nxt is None and nfr / FPS - grp[-1]['e'] < 1.2:
            b = None                                           # the last words stay to the end of the slot
        html.append(f'<div class="cap" id="cap{g}">' + ''.join(f'<span id="cp{g}-{k}">{esc(c["t"])}</span>' for k, c in enumerate(grp)) + '</div>')
        for k, c in enumerate(grp):
            tw.append(f"gsap.set('#cp{g}-{k}',{{autoAlpha:0}});")
            tw.append(f"tl.fromTo('#cp{g}-{k}',{{autoAlpha:0,scale:1.25,y:6,filter:'blur(10px)'}},{{autoAlpha:1,scale:1,y:0,"
                      f"filter:'blur(0px)',duration:.18,ease:'power3.out',immediateRender:false}},{max(a, c['s'] - .03):.3f});")
        if b is not None:
            tw.append(f"tl.to('#cap{g}',{{autoAlpha:0,duration:.08,ease:'power1.in'}},{max(a, b - .08):.3f});")
            tw.append(f"tl.set('#cap{g}',{{autoAlpha:0}},{b:.3f});")
    return html, tw


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the duration UP to whole frames
    if not os.path.exists('work/measure.json'):
        sys.exit('work/measure.json is missing: run prep.py first (see effect.md)')
    M = json.load(open('work/measure.json'))
    if M['frames'] != nfr:
        sys.exit('work/measure.json belongs to another clip: run prep.py again')
    cutout = 'assets/fg.webm' if (FIX_EDGE and os.path.exists('assets/fg.webm')) else 'assets/subject.webm'
    warn = list(M.get('warnings', []))
    chat = SCREEN == 'chat'
    t_in = F_IN / FPS
    t_out = F_OUT / FPS if F_OUT is not None else None
    if F_OUT is not None and not (F_IN + 20 <= F_OUT <= nfr - 14):
        sys.exit('F_OUT must be at least 20 frames after F_IN and at least 14 frames before the end of the slot')

    # ---- reframe: punch in a little on a small head, slide the shot down so the speaker's head sits under the screen
    s = float(ZOOM) if ZOOM else min(1.25, max(1.0, 150 / max(M['head_w'], 1)))
    s = max(1.0, s)
    ty = max(HEAD_Y - s * M['head_top_min'], 1920 * (1 - s))   # down only: the picture must still reach the bottom
    tx = min(0.0, max(1080 * (1 - s), M['head_cx'] * (1 - s)))
    edge = int(EDGE) if EDGE else int(round(ty + s * M['edge']))
    head_top = ty + s * M['head_top_min']
    q = M['q']

    def clear_y(x0, x1, f0=0, f1=None):
        """highest point of the speaker (frame px, after the reframe) between two frame x positions, from frame f0 to f1"""
        cols = [i for i in range(len(M['col_tops'][0])) if x0 <= tx + s * i * q <= x1]
        fr = M['col_tops'][max(0, min(int(f0), nfr - 1)):(nfr if f1 is None else max(int(f1), int(f0) + 1))]
        ys = sorted(ty + s * q * row[i] for row in fr for i in cols)
        return ys[min(len(ys) - 1, len(ys) // 200)] if ys else 1920.0     # 0.5% off the top: one stray pixel does not count

    if edge - head_top < 150:
        warn.append('the chest line is very close to their head: check EDGE')
    if edge > 1500:
        warn.append(f'the screen edge is at y {edge}, below the safe zone: tight shot, use a wider one or set EDGE')
    cap_y = CAP_Y if CAP_Y else edge + 114
    caps_on = os.environ.get('CAPTIONS') != '0'
    if caps_on and cap_y + 70 > 1470:
        if edge + 50 + 70 <= 1470 and not CAP_Y:
            cap_y = 1400
        else:
            caps_on = False
            warn.append('no room for captions between the screen edge and the safe-zone floor: captions dropped')

    J, body = [], []
    T, A = J.append, body.append
    sounds = [('whoosh-short', F_IN, .25)]

    # ---- screen drop-in / lift-out + reframe (the plate starts 1 frame late and returns early, so the screen
    #      always covers the strip the moving plate leaves at the top)
    travel = edge + 80
    T(f"gsap.set('#ui',{{y:{-travel}}});")
    T(f"tl.to('#ui',{{y:0,duration:.5,ease:'expo.out'}},{t_in:.3f});")
    T(f"tl.to(['#plate','#cutx'],{{x:{tx:.2f},y:{ty:.2f},scale:{s:.4f},duration:.5,ease:'expo.out'}},{t_in + .03:.3f});")
    T(f"tl.to('#cutsh',{{'--sh':{SHADOW},duration:.3,ease:'power1.out'}},{t_in + .3:.3f});")
    if t_out is not None:
        T(f"tl.to('#cutsh',{{'--sh':0,duration:.1,ease:'power1.in'}},{t_out:.3f});")
        T(f"tl.to('#ui',{{y:{-travel},duration:.4,ease:'power3.in'}},{t_out:.3f});")
        T(f"tl.to(['#plate','#cutx'],{{x:0,y:0,scale:1,duration:.34,ease:'power3.in'}},{t_out:.3f});")
        sounds.append(('whoosh-short', F_OUT, .2))

    label_spots = {}
    info = []
    if chat:
        # room above the speaker: for the message box while it is on screen, for the thread from the send on
        sky_bot = int(clear_y(COMP_L, COMP_L + COMP_W, F_IN, None if SEND is None else SEND + 10)) - 28
        items = list(ATTACH[1]) if ATTACH else []
        n_at = len(items)
        if n_at > 5:
            sys.exit('ATTACH takes at most 5 things')
        if (REPLY or STEPS) and SEND is None:
            sys.exit('REPLY and STEPS need SEND (the message has to be sent before the answer comes)')
        chips_row = CHIP_H + 18 if n_at else 0
        comp_h0 = COMP_PAD[0] + TEXT_H + BAR_GAP + BAR_H + COMP_PAD[2]
        comp_bot = sky_bot
        comp_top1 = comp_bot - comp_h0 - chips_row
        if comp_top1 < HEAD_BOT + 8:
            sys.exit(f'no room for the message box above their head (needs y {HEAD_BOT + 8}, has {comp_top1}): raise HEAD_Y')
        slot_y = comp_top1 + COMP_PAD[0]
        slots = [(COMP_L + COMP_PAD[1] + i * (CHIP_W + CHIP_GAP), slot_y) for i in range(n_at)]
        text_y = comp_bot - COMP_PAD[2] - BAR_H - BAR_GAP - TEXT_H
        typed = TYPE[1] if TYPE else ''
        token = typed.startswith('/')
        label_spots['attach'] = ((slots[-1][0] + CHIP_W + 26) if slots else COMP_L + 40, slot_y + 70)
        label_spots['text'] = (COMP_L + COMP_PAD[1] + 4 + text_w(typed, 42) + 44, text_y - 2)
        # sent message: bubble on the right, small thumbnails fanned to its left
        bub_w = text_w(typed, 42, True) + 76
        fan_r = 1080 - 50 - bub_w - 10
        th_x = [fan_r - TH_W - (n_at - 1 - i) * 44 for i in range(n_at)]
        th_rot = [(i - (n_at - 1) / 2) * 3.5 for i in range(n_at)]
        th_scale = TH_W / CHIP_W
        if n_at and th_x[0] < 40:
            warn.append('the typed text is too long to sit beside the attachments in the sent message: shorten TYPE')
        # step card + scroll
        rows = list(STEPS[1]) if STEPS else []
        if len(rows) > 4:
            sys.exit('STEPS takes at most 4 rows')
        card_h = 128 + ROW_H * len(rows)
        # result card: the side of the speaker's head with more room, bottom just above the speaker's shoulder there
        res = None
        if RESULT:
            has_pic = bool(RESULT[2])
            if has_pic and not os.path.exists(RESULT[2]):
                sys.exit(f'RESULT picture {RESULT[2]} not found')
            rh = (14 + 52 + 6 + 483 + 16) if has_pic else (14 + 52 + 6 + 170 + 16)
            opts = {}
            for side, x0 in (('R', 1080 - 68 - RES_W), ('L', 68)):
                bot = min(clear_y(x0 - 14, x0 + RES_W + 14, RESULT[0] - 3) - 18, edge - 70)
                opts[side] = (x0, bot)
            side = RESULT_SIDE or max(opts, key=lambda k_: opts[k_][1])
            x0, bot = opts[side]
            top_min = HEAD_BOT + 18
            k = min(1.0, (bot - top_min) / rh)
            if k < .62:
                warn.append(f'the result card only has {bot - top_min:.0f}px beside their head on side {side} '
                            f'(scaled to {max(k, .4):.2f}): try RESULT_SIDE, a higher HEAD_Y, or drop the picture')
                k = max(k, .4)
            rx = x0 if side == 'L' else x0 + RES_W * (1 - k)
            res = {'side': side, 'x': rx, 'y': bot - rh * k, 'k': k, 'pic': has_pic, 'h': rh}
        card_x = 50 if (res is None or res['side'] == 'R') else 1080 - 50 - CARD_W
        scroll = 0
        if rows:                        # the thread scrolls up so the step card ends just above the speaker
            room = int(clear_y(card_x, card_x + CARD_W, rows[0][0] - 6)) - 24
            scroll = max(0, CARD_TOP + card_h - room)
            if scroll > CL_ROW - (HEAD_BOT + 18):
                fit = int((room - 128 - (CARD_TOP - (CL_ROW - HEAD_BOT - 18))) // ROW_H)
                sys.exit(f'STEPS has {len(rows)} rows, only {max(fit, 0)} fit above the speaker: fewer rows or a higher HEAD_Y number')
        if res and rows and res['y'] < CARD_TOP - scroll + card_h + 10:
            # the result card would run up beside the step card: fine when they are side by side, not when it overlaps
            lo, hi = (card_x, card_x + CARD_W)
            if not (res['x'] >= hi + 8 or res['x'] + RES_W * res['k'] <= lo - 8):
                warn.append('result card overlaps the step card: set RESULT_SIDE to the other side or drop a row')

        # ---- chat html
        A(f'<div id="hstrip"></div><div id="brand">{mark(58, "bmark")}<span>{esc(APP_NAME)}</span></div>')
        if GREETING:
            g_y = (HEAD_BOT + (comp_bot - comp_h0)) // 2 - 40
            A(f'<div id="greet" style="top:{g_y}px">{esc(GREETING)}</div>')
        A('<div id="thread">')
        for i, it in enumerate(items):
            A(f'<div class="uth tile" id="uth{i}" style="left:{th_x[i]:.0f}px;transform:rotate({th_rot[i]}deg) scale({th_scale:.4f})">{tile(it)}</div>')
        if TYPE and SEND is not None:
            A(f'<div id="ububble" class="{"tok" if token else ""}">{esc(typed)}</div>')
        if REPLY:
            A(f'<div id="crow">{mark(52, "rmark") or "<div id=rmark class=dot></div>"}<div id="ctext">'
              + ''.join(f'<span class="cw" id="cw{k_}">{esc(w)}</span>' for k_, w in enumerate(REPLY[1].split())) + '</div></div>')
        if rows:
            A(f'<div id="card" style="left:{card_x}px"><div id="chead"><b>{esc(STEPS[0])}</b></div>'
              '<div id="ptrack"><div id="pfill"></div></div><div id="rows">')
            for i, (_, txt) in enumerate(rows):
                A(f'<div class="step" id="st{i}"><div class="ico"><div class="spin" id="sp{i}"></div>'
                  f'<div class="chk" id="ck{i}">{check(40)}</div></div><span>{esc(txt)}</span></div>')
            A('</div></div>')
        A('</div>')
        A('<div id="comp"><div id="chipsp"></div><div id="tline"><span id="tok">'
          + ''.join(f'<span class="ch" id="c{j}">{esc(c) if c != " " else "&nbsp;"}</span>' for j, c in enumerate(typed))
          + f'</span><span id="caret"></span><span id="ph">{esc(PLACEHOLDER or "")}</span></div>'
          f'<div id="tbar"><div class="tb">{PLUS}</div><div class="tb">{SLIDERS}</div><div id="send">{ARROW_UP}</div></div></div>')
        if res:
            thumb = (f'<div id="rthumb" style="height:483px"><img src="{RESULT[2]}" alt=""><div id="rplay">{play(96)}</div>'
                     if res['pic'] else f'<div id="rthumb" class="nopic" style="height:170px">{DOC}')
            A(f'<div id="reelpos" style="left:{res["x"]:.0f}px;top:{res["y"]:.0f}px;transform:scale({res["k"]:.3f})"><div id="reel">'
              f'<div id="rname">{esc(RESULT[1])}</div>{thumb}'
              f'<div id="rready">{check(34)}<span>{esc(RESULT[3])}</span></div></div></div></div>')
        for i, (x, y) in enumerate(slots):
            A(f'<div class="chip tile" id="chip{i}" style="left:{x}px;top:{y}px">{tile(items[i])}</div>')

        # ---- chat timeline
        for sel, d in (('#brand', .14), ('#greet', .2), ('#comp', .26)):
            if sel != '#greet' or GREETING:
                T(f"tl.fromTo('{sel}',{{autoAlpha:0,y:46}},{{autoAlpha:1,y:0,duration:.45,ease:'power3.out',immediateRender:false}},{t_in + d:.3f});")
        hide = [sel for sel, on in (('#reel', res), ('#ububble', TYPE and SEND is not None), ('#crow', REPLY), ('.cw', REPLY),
                                    ('#card', rows), ('.chk', rows), ('.step', rows), ('.uth', n_at)) if on]
        if hide:
            T(f"gsap.set({json.dumps(hide)},{{autoAlpha:0}});")
        T("gsap.set('#send',{opacity:.38});" + ("gsap.set('.ch',{display:'none'});" if typed else '')
          + ("gsap.set('#pfill',{scaleX:0});" if rows else ''))
        t_type = TYPE[0] / FPS if TYPE else None
        t_send = SEND / FPS if SEND is not None else None
        first_evt = min([v for v in (ATTACH[0] / FPS if ATTACH else None, t_type, t_send) if v is not None], default=dur)
        bt = t_in + .5
        while bt + .3 < (t_type if t_type is not None else first_evt):     # caret blinks while the box is empty
            T(f"tl.set('#caret',{{autoAlpha:0}},{bt:.2f});tl.set('#caret',{{autoAlpha:1}},{bt + .3:.2f});")
            bt += .6
        if GREETING:
            T(f"tl.to('#greet',{{autoAlpha:0,y:-24,duration:.2,ease:'power2.in',overwrite:'auto'}},{max(t_in + .5, first_evt - .04):.3f});")
        if ATTACH:
            ta = ATTACH[0] / FPS
            sounds.append(('whoosh-short', ATTACH[0] - 1, .22))
            T(f"tl.to('#chipsp',{{height:{chips_row},duration:.42,ease:'power3.out'}},{max(0, ta - .05):.3f});")
            fly = [(-330, -900, -24, 1.55), (-140, -1010, 14, 1.6), (60, -960, -9, 1.5), (250, -1030, 19, 1.6), (430, -930, -16, 1.55)]
            for i in range(n_at):
                dx, dy, rot, sc = fly[i]
                T(f"gsap.set('#chip{i}',{{x:{dx},y:{dy},rotation:{rot},scale:{sc},autoAlpha:0}});")
                T(f"tl.set('#chip{i}',{{autoAlpha:1}},{max(0, ta - .06 + i * .05):.3f});")
                T(f"tl.to('#chip{i}',{{x:0,y:0,rotation:0,scale:1,duration:.5,ease:'expo.out'}},{max(0, ta - .06 + i * .05):.3f});")
            T(f"tl.fromTo('#comp',{{scale:1}},{{scale:1.012,duration:.1,yoyo:true,repeat:1,ease:'sine.inOut',immediateRender:false}},{ta + .42:.3f});")
        if TYPE:
            step = min(.036, .4 / max(len(typed), 1))
            T(f"tl.set('#ph',{{display:'none'}},{t_type:.3f});tl.set('#caret',{{autoAlpha:1}},{t_type:.3f});")
            for j in range(len(typed)):
                T(f"tl.set('#c{j}',{{display:'inline'}},{t_type + j * step:.3f});")
            T(f"tl.to('#send',{{opacity:1,duration:.12}},{t_type + .02:.3f});")
            if token:
                rgb = tuple(int(ACCENT.lstrip('#')[k_:k_ + 2], 16) for k_ in (0, 2, 4))
                T(f"tl.to('#tok',{{backgroundColor:'rgba({rgb[0]},{rgb[1]},{rgb[2]},0.13)',duration:.16,ease:'power1.out'}},{t_type + len(typed) * step + .03:.3f});")
        if t_send is not None:
            sounds.append(('click', SEND - 1, .6))
            T(f"tl.to('#send',{{opacity:1,scale:.86,duration:.06,ease:'power2.in'}},{t_send - .06:.3f});")
            T(f"tl.to('#send',{{scale:1,duration:.16,ease:'back.out(3)'}},{t_send:.3f});")
            T(f"tl.to('#comp',{{y:110,scale:.95,duration:.26,ease:'power2.in',overwrite:'auto'}},{t_send + .01:.3f});")
            T(f"tl.to('#comp',{{autoAlpha:0,filter:'blur(6px)',duration:.16,ease:'power1.out'}},{t_send + .02:.3f});")
            for i, (x, y) in enumerate(slots):
                T(f"tl.to('#chip{i}',{{x:{th_x[i] - x:.1f},y:{UM_TOP - y},scale:{th_scale:.4f},rotation:{th_rot[i]},duration:.36,"
                  f"ease:'power3.inOut',overwrite:'auto'}},{t_send + .02 + i * .025:.3f});")
            if n_at:
                T(f"tl.set('.chip',{{autoAlpha:0}},{t_send + .49:.3f});tl.set('.uth',{{autoAlpha:1}},{t_send + .49:.3f});")
            if TYPE:
                T(f"tl.fromTo('#ububble',{{autoAlpha:0,y:40,scale:.94}},{{autoAlpha:1,y:0,scale:1,duration:.3,ease:'power3.out',immediateRender:false}},{t_send + .1:.3f});")
        if REPLY:
            tr = max(REPLY[0] / FPS, t_send + .12)
            T(f"tl.fromTo('#crow',{{autoAlpha:0,y:24}},{{autoAlpha:1,y:0,duration:.26,ease:'power3.out',immediateRender:false}},{tr - .06:.3f});")
            for k_ in range(len(REPLY[1].split())):
                T(f"tl.fromTo('#cw{k_}',{{autoAlpha:0,y:10}},{{autoAlpha:1,y:0,duration:.16,ease:'power2.out',immediateRender:false}},{tr + k_ * .06:.3f});")
        if rows:
            r0 = rows[0][0] / FPS
            tc = max(t_send + .2, r0 - .12)
            T(f"tl.fromTo('#card',{{autoAlpha:0,y:40}},{{autoAlpha:1,y:0,duration:.32,ease:'power3.out',immediateRender:false}},{tc:.3f});")
            if scroll:
                T(f"tl.to('#thread',{{y:{-scroll},duration:.42,ease:'power3.inOut'}},{tc + .12:.3f});")
                if UM_TOP - scroll < HEAD_BOT - 40:
                    T(f"tl.to(['.uth','#ububble'],{{autoAlpha:0,duration:.3,ease:'power1.in'}},{tc + .2:.3f});")
            for i, (f, _) in enumerate(rows):
                a_ = max(f / FPS, tc + .08)
                c_ = a_ + 5 / FPS
                T(f"tl.to('#rows',{{height:{ROW_H * (i + 1)},duration:.17,ease:'power3.out'}},{a_ - .02:.3f});")
                T(f"tl.fromTo('#st{i}',{{autoAlpha:0,x:-16}},{{autoAlpha:1,x:0,duration:.18,ease:'power2.out',immediateRender:false}},{a_:.3f});")
                T(f"tl.fromTo('#sp{i}',{{rotation:0}},{{rotation:120,duration:{c_ - a_:.3f},ease:'none',immediateRender:false}},{a_:.3f});")
                T(f"tl.set('#sp{i}',{{autoAlpha:0}},{c_:.3f});")
                T(f"tl.fromTo('#ck{i}',{{autoAlpha:0,scale:.3}},{{autoAlpha:1,scale:1,duration:.2,ease:'back.out(2.6)',immediateRender:false}},{c_:.3f});")
            last = max(rows[-1][0] / FPS, tc + .08) + 5 / FPS
            T(f"tl.to('#pfill',{{scaleX:1,duration:{max(.2, last - r0):.3f},ease:'power1.inOut'}},{max(tc, r0):.3f});")
        if res:
            trs = RESULT[0] / FPS
            sounds.append(('pop', RESULT[0], .18))
            T(f"tl.fromTo('#reel',{{autoAlpha:0,scale:.55,y:80,rotation:6}},{{autoAlpha:1,scale:1,y:0,rotation:0,duration:.5,"
              f"ease:'back.out(1.5)',immediateRender:false}},{max(0, trs - .03):.3f});")
            T(f"tl.fromTo('#rready',{{autoAlpha:0,scale:.4}},{{autoAlpha:1,scale:1,duration:.24,ease:'back.out(2.6)',immediateRender:false}},{trs + .22:.3f});")
            if res['pic']:
                T(f"tl.fromTo('#rplay',{{scale:.6}},{{scale:1,duration:.3,ease:'back.out(2.5)',immediateRender:false}},{trs + .12:.3f});")
        info.append(f'chat: message box y {comp_top1} to {comp_bot}, scroll {scroll}'
                    + (f", result card side {res['side']} at ({res['x']:.0f}, {res['y']:.0f}) x{res['k']:.2f}" if res else ''))
        css_extra = chat_css(edge, comp_bot, comp_top1, chips_row)
    else:
        # ---- your own picture or screen recording
        if not os.path.exists(SCREEN):
            sys.exit(f'SCREEN file {SCREEN} not found (put it in the slot, e.g. assets/screen.png)')
        video = SCREEN.lower().endswith(('.mp4', '.mov', '.webm', '.m4v'))
        pr = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                             '-of', 'json', SCREEN], capture_output=True, text=True)
        pj = json.loads(pr.stdout or '{}')
        st = (pj.get('streams') or [{}])[0]
        mw, mh = int(st.get('width', 1080)), int(st.get('height', 1920))
        dw = 1080 * SCREEN_ZOOM
        dh = mh * dw / mw
        need = edge + abs(SCREEN_SCROLL) - min(0, SCREEN_Y)
        if dh + min(0, SCREEN_Y) < edge + abs(SCREEN_SCROLL):
            k = need / dh
            dw, dh = dw * k, dh * k
            warn.append(f'the picture is too short for the screen: scaled up {k:.2f}x to cover it (a taller picture avoids this)')
        left = (1080 - dw) / 2 + SCREEN_X
        style = f'left:{left:.1f}px;top:{SCREEN_Y}px;width:{dw:.1f}px;height:{dh:.1f}px'
        if video:
            mdur = float((pj.get('format') or {}).get('duration', dur))
            vd = min(dur - t_in, mdur - .05)
            if mdur + .05 < dur - t_in:
                warn.append(f'the recording ({mdur:.1f}s) is shorter than the slot: it holds its last frame')
            A(f'<video id="shot" src="{SCREEN}" muted playsinline data-start="{t_in:.3f}" data-media-start="0" '
              f'data-duration="{vd:.3f}" data-track-index="5" style="{style}"></video>')
        else:
            A(f'<img id="shot" src="{SCREEN}" alt="" style="{style}">')
        if SCREEN_SCROLL:
            T(f"tl.to('#shot',{{y:{-abs(SCREEN_SCROLL)},duration:{max(.5, (t_out or dur) - t_in - .5):.3f},ease:'sine.inOut'}},{t_in + .4:.3f});")
        info.append(f'media: {SCREEN} shown {dw:.0f}x{dh:.0f} at ({left:.0f}, {SCREEN_Y})')
        css_extra = '#shot{position:absolute;display:block;max-width:none}'

    # ---- highlighter tags
    t_send_lbl = SEND / FPS if (chat and SEND is not None) else None
    for i, (f, txt, where) in enumerate(LABELS):
        if isinstance(where, str):
            if where not in label_spots:
                sys.exit(f'LABELS: "{where}" only exists on the chat screen: give (x, y) instead')
            x, y = label_spots[where]
        else:
            x, y = where
        lw = text_w(txt, 38, True) * 1.08 + 36
        x = max(40, min(x, 1045 - lw))
        t = f / FPS
        A(f'<div class="hl" id="hl{i}" style="left:{x:.0f}px;top:{y:.0f}px"><div class="bg"></div><div class="tx">{esc(txt)}</div></div>')
        T(f"gsap.set('#hl{i}',{{autoAlpha:0}});gsap.set('#hl{i} .bg',{{scaleX:0}});gsap.set('#hl{i} .tx',{{autoAlpha:0}});")
        T(f"tl.set('#hl{i}',{{autoAlpha:1}},{t:.3f});")
        T(f"tl.fromTo('#hl{i}',{{rotation:-9,scale:.8}},{{rotation:-3,scale:1,duration:.4,ease:'back.out(2.4)',immediateRender:false}},{t:.3f});")
        T(f"tl.to('#hl{i} .bg',{{scaleX:1,duration:.18,ease:'power3.out'}},{t:.3f});")
        T(f"tl.fromTo('#hl{i} .tx',{{autoAlpha:0,x:-10}},{{autoAlpha:1,x:0,duration:.16,ease:'power2.out',immediateRender:false}},{t + .08:.3f});")
        if t_send_lbl is not None and t < t_send_lbl:
            T(f"tl.to('#hl{i}',{{autoAlpha:0,scale:.85,duration:.14,ease:'power2.in',overwrite:'auto'}},{max(t + .42, t_send_lbl):.3f});")
        if i == 0:
            sounds.append(('pop', f, .14))
        info.append(f'tag "{txt}" at ({x:.0f}, {y:.0f})')

    # ---- captions in the room band
    cap_html, cap_tw = [], []
    if caps_on and os.path.exists('words.json'):
        cap_html, cap_tw = captions(json.load(open('words.json')), nfr, t_out)

    # ---- sounds
    aud = []
    if os.environ.get('SFX') != '0':
        lanes = []
        for k_, (name, f, vol) in enumerate(sorted(SOUNDS if SOUNDS is not None else sounds, key=lambda x_: x_[1])):
            path = next((p for p in (f'assets/sfx/{name}.mp3', f'assets_fx/{name}.mp3') if os.path.exists(p)), None)
            t = max(0.0, f / FPS)
            if path is None or t >= dur - .05:
                print(f'  (sound {name} skipped: file missing or past the end)')
                continue
            d = min(SFX_LEN.get(name, .6), dur - t)
            lane = next((i for i, end in enumerate(lanes) if end <= t), None)
            if lane is None:
                lanes.append(0)
                lane = len(lanes) - 1
            lanes[lane] = t + d
            aud.append(f'<audio id="sfx{k_}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                       f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    voice = (f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''

    panel_bg = ('radial-gradient(120% 60% at 50% 0%,#FBFAF6 0%,#F5F4EE 55%,#F0EEE6 100%)' if chat else '#111')
    css = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#stage{{position:absolute;inset:0}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
#plate,#cutx{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0}}
#plate{{z-index:0}}
/* the screen: runs 200px above the frame so the drop never shows a gap */
#ui{{position:absolute;left:0;top:-200px;width:1080px;height:{edge + 200}px;z-index:2;overflow:hidden;background:{panel_bg};
  box-shadow:0 26px 54px -8px rgba(28,16,8,.42),0 3px 0 rgba(255,255,255,.55) inset}}
#uiedge{{position:absolute;left:0;right:0;bottom:0;height:2px;background:rgba(40,30,20,.10)}}
#uic{{position:absolute;left:0;top:200px;width:1080px;height:{edge}px;font-family:'Inter',sans-serif;font-weight:500;color:{INK}}}
/* their cutout: shadow on the screen, faded out just below the screen edge where the plate already shows the speaker */
#cutmask{{position:absolute;inset:0;z-index:4;-webkit-mask-image:linear-gradient(to bottom,#000 0,#000 {edge + 14}px,transparent {edge + 54}px);
  mask-image:linear-gradient(to bottom,#000 0,#000 {edge + 14}px,transparent {edge + 54}px)}}
#cutsh{{position:absolute;inset:0;--sh:0;filter:drop-shadow(22px 14px 18px rgba(28,16,8,var(--sh)))}}
/* highlighter tags */
.hl{{position:absolute;z-index:40;height:62px;transform-origin:0 50%}}
.hl .bg{{position:absolute;inset:0;background:{HILITE};border-radius:6px;transform-origin:0 50%;box-shadow:0 8px 18px rgba(120,95,10,.18)}}
.hl .tx{{position:relative;padding:0 18px;font-family:'Inter Tight';font-weight:900;font-size:38px;line-height:62px;
  letter-spacing:.01em;color:#2A2412;white-space:nowrap}}
/* captions in the room band */
.cap{{position:absolute;left:0;right:0;top:{cap_y}px;z-index:9;text-align:center;color:#fff;font-family:'Inter Tight';font-weight:900;
  font-size:70px;line-height:1;letter-spacing:-.015em;white-space:nowrap;text-shadow:0 6px 28px rgba(0,0,0,.55),0 2px 6px rgba(0,0,0,.45)}}
.cap span{{display:inline-block;margin:0 .12em;transform-origin:50% 70%}}
{css_extra}"""
    nl = '\n'
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
{nl.join(aud)}
  <div id="stage">
    <div id="plate"><video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video></div>
    <div id="ui"><div id="uic">
{nl.join(body)}
    </div><div id="uiedge"></div></div>
    <div id="cutmask"><div id="cutsh"><div id="cutx"><video id="cut" class="full" src="{cutout}" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div></div></div>
{nl.join(cap_html)}
  </div>
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(J + cap_tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    name = os.path.basename(HERE)
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  screen {"chat" if chat else SCREEN}  cutout {cutout}')
    print(f'  reframe: zoom {s:.3f}, shift ({tx:.0f}, {ty:.0f})  head top y {head_top:.0f}  screen edge y {edge}  '
          f'captions {"y " + str(cap_y) if caps_on else "off"}')
    if os.environ.get('CAPTIONS') == '0':
        # in a reel the buyer's own captions stay on: tell where they have room (the reel's chest band would be on the face)
        print(f"  reel captions: this effect's own words are off. The room band for the reel's captions is at y {cap_y}: "
              f'add the slot with fx_add.py --caption-y {max(236, min(1376, int(cap_y)))}, then check one reel snapshot inside the slot')
    for line in info:
        print('  ' + line)
    for w in warn:
        print('WARNING:', w)
    print(f'render to renders/{name}.mp4')


def tile(item):
    """one attachment: a picture thumbnail, or a plain labelled tile"""
    if is_pic(item):
        if not os.path.exists(item):
            sys.exit(f'ATTACH picture {item} not found')
        return f'<img src="{item}" alt=""><div class="pl">{play(44)}</div>'
    return f'<div class="lab"><div class="pl2">{play(44, "rgba(20,18,16,.30)")}</div><span>{esc(item)}</span></div>'


def chat_css(edge, comp_bot, comp_top1, chips_row):
    return f"""
.a{{position:absolute}}
#hstrip{{position:absolute;left:0;right:0;top:-200px;height:{HEAD_BOT + 200}px;z-index:20;background:linear-gradient(180deg,#FAF9F5 0%,#F8F7F2 100%)}}
#hstrip:after{{content:'';position:absolute;left:0;right:0;bottom:-34px;height:34px;background:linear-gradient(#F8F7F2,rgba(248,247,242,0))}}
#brand{{position:absolute;left:0;right:0;top:236px;height:64px;display:flex;align-items:center;justify-content:center;gap:16px;z-index:21}}
#brand span{{font-family:'DM Serif Display',serif;font-weight:400;font-size:56px;letter-spacing:-.01em;color:{INK}}}
#greet{{position:absolute;left:0;right:0;text-align:center;font-family:'DM Serif Display',serif;font-weight:400;
  font-size:58px;letter-spacing:-.01em;color:#2B2A27;z-index:5;white-space:nowrap}}
#comp{{position:absolute;left:{COMP_L}px;width:{COMP_W}px;bottom:{edge - comp_bot}px;z-index:6;
  padding:{COMP_PAD[0]}px {COMP_PAD[1]}px {COMP_PAD[2]}px;border-radius:38px;background:#fff;border:1.5px solid #E3DFD5;
  box-shadow:0 24px 60px rgba(60,40,20,.12),0 3px 8px rgba(60,40,20,.06);transform-origin:50% 100%}}
#chipsp{{height:0}}
#tline{{position:relative;height:{TEXT_H}px;font-size:42px;line-height:{TEXT_H}px;white-space:nowrap;padding-left:4px}}
#tok{{display:inline-block;border-radius:12px;padding:0 4px;margin-left:-4px;line-height:56px}}
.ch{{display:inline}}
#caret{{display:inline-block;width:3px;height:44px;background:{INK};vertical-align:-8px;margin:0 2px}}
#ph{{color:#8C8A83}}
#tbar{{position:relative;height:{BAR_H}px;margin-top:{BAR_GAP}px;display:flex;align-items:center;gap:12px}}
.tb{{width:64px;height:64px;border-radius:18px;border:1.5px solid #E3DFD5;display:flex;align-items:center;justify-content:center}}
#send{{position:absolute;right:0;top:0;width:64px;height:64px;border-radius:18px;background:{ACCENT};display:flex;align-items:center;justify-content:center}}
.tile{{position:absolute;width:{CHIP_W}px;height:{CHIP_H}px;border-radius:18px;overflow:hidden;background:#E9E5DA;
  border:2px solid #fff;box-shadow:0 14px 34px rgba(40,25,15,.22),0 2px 6px rgba(40,25,15,.12);transform-origin:0 0}}
.tile img{{width:100%;height:100%;object-fit:cover;display:block}}
.tile .pl{{position:absolute;left:{CHIP_W // 2 - 22}px;top:{CHIP_H // 2 - 22}px}}
.tile .lab{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;
  background:linear-gradient(160deg,#EFEBE1,#DDD8CB)}}
.tile .lab span{{font-size:26px;font-weight:600;color:#3A3935;text-align:center;line-height:1.1;padding:0 6px}}
.chip{{z-index:30}}
#thread{{position:absolute;left:0;top:0;width:1080px;height:{edge}px;z-index:4}}
.uth{{top:{UM_TOP}px}}
#ububble{{position:absolute;right:50px;top:{UM_TOP + 9}px;height:96px;padding:0 38px;border-radius:30px;background:#EAE6DB;
  font-size:42px;line-height:96px;color:{INK};font-weight:600;white-space:nowrap}}
#crow{{position:absolute;left:52px;top:{CL_ROW}px;height:64px;display:flex;align-items:center;gap:20px}}
.dot{{width:44px;height:44px;border-radius:50%;background:{ACCENT};flex:none}}
#ctext{{font-weight:500;font-size:44px;letter-spacing:-.015em;color:{INK};white-space:nowrap}}
.cw{{display:inline-block;margin-right:.24em}}
#card{{position:absolute;top:{CARD_TOP}px;width:{CARD_W}px;padding:24px 28px 18px;border-radius:32px;background:#fff;
  border:1.5px solid #E6E2D8;box-shadow:0 22px 54px rgba(60,40,20,.10),0 2px 6px rgba(60,40,20,.05)}}
#chead{{display:flex;align-items:center;gap:12px;height:48px;font-size:34px;color:#5E5D59;white-space:nowrap}}
#chead b{{font-weight:600;color:{INK}}}
#rows{{height:0;overflow:hidden}}
#ptrack{{height:12px;border-radius:12px;background:#EFEAE0;overflow:hidden;margin:16px 0 10px}}
#pfill{{width:100%;height:100%;background:{ACCENT};border-radius:12px;transform-origin:0 50%}}
.step{{height:{ROW_H}px;display:flex;align-items:center;gap:18px;font-size:35px;color:{INK};white-space:nowrap}}
.ico{{position:relative;width:40px;height:40px;flex:none}}
.spin{{position:absolute;left:1px;top:1px;width:38px;height:38px;border-radius:50%;border:4px solid #E8E4DA;border-top-color:{ACCENT};border-right-color:{ACCENT}}}
.chk{{position:absolute;left:0;top:0}}
#reelpos{{position:absolute;width:{RES_W}px;z-index:8;transform-origin:0 0}}
#reel{{width:{RES_W}px;padding:14px 14px 16px;border-radius:32px;background:#fff;
  border:1.5px solid #E6E2D8;box-shadow:0 34px 80px rgba(60,40,20,.24),0 6px 16px rgba(60,40,20,.10);transform-origin:50% 60%}}
#rname{{height:52px;display:flex;align-items:center;padding-left:6px;font-size:32px;font-weight:600;letter-spacing:-.01em;white-space:nowrap;overflow:hidden}}
#rthumb{{position:relative;width:272px;border-radius:20px;overflow:hidden;margin-top:6px;background:#222}}
#rthumb.nopic{{background:linear-gradient(160deg,#EFEBE1,#DDD8CB);display:flex;align-items:flex-end;justify-content:center;padding-bottom:22px}}
#rthumb img{{width:100%;height:100%;object-fit:cover;display:block}}
#rplay{{position:absolute;left:88px;top:194px}}
#rready{{position:absolute;left:14px;top:14px;height:52px;padding:0 18px 0 10px;border-radius:26px;background:#fff;display:flex;
  align-items:center;gap:8px;font-size:32px;font-weight:600;color:#2F7A49;box-shadow:0 6px 16px rgba(0,0,0,.18);white-space:nowrap}}
"""


if __name__ == '__main__':
    main()
