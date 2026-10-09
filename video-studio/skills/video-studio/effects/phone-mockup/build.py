#!/usr/bin/env python3
"""phone-mockup: a drawn 3D phone flies in beside the speaker, plays a screen, and taps land on their words.

  IN_FRAME        phone flies in from its side (3D tilt settles, glass sheen), frames before it are untouched picture
  CARD_AT         packaged card only: the card rises on the glass
  TAPS            touch dot glides in and presses on the word: ripple, rings, the button flips / the row ticks
  TURN            optional: the phone turns to face the viewer
  OUT_FRAME       phone leaves the way it came; the last frames are untouched picture again

python3 build.py            -> index.html + work/layout.json (prints where the phone went and every tap frame)
SAFE=1    safe-zone guide in red (snapshots only)      GRID=1  fractions drawn on the glass (to find tap positions)
CAPTIONS=0  no caption words from the effect           SFX=0   no sounds from the effect
"""
import html as _html
import json
import math
import os
import sys

import numpy as np

import measure as M

# ==== CLIP (edit this) ====
# What plays on the phone. None = the packaged card below, written with the speaker's own words. Or a file the BUYER
# put in the slot's screen/ folder: 'screen/recording.mp4' (mp4 / mov / webm) or 'screen/picture.png' (png / jpg).
# Only their own screen. Ask for it first; with no file and no words for the card, leave the effect out.
SCREEN = None
SCREEN_START = 0.0        # recordings: second of the recording that plays at slot time 0 (find it by scrubbing the file)
SCREEN_POS = 'center'     # which part survives the crop to the tall glass: 'center', 'top' or 'bottom'
# The packaged card (used when SCREEN is None). Type what the speaker says or means; '' or [] hides that part.
CARD = dict(
    app='Your app',                                      # name in the top bar: the thing the speaker is talking about
    intro='',                                            # small message bubble above the card
    label='STEP',                                        # small caps line on the card
    title='Your title here',                             # the big line: the thing being approved / shown
    rows=['First line', 'Second line', 'Third line'],    # up to 4 short lines; a tap on 'row1', 'row2'.. ticks one
    button='Approve', button_done='Approved',            # main button, and what it says after it is tapped
    button_alt='',                                       # quiet second button beside it
    done='',                                             # message bubble after the button is tapped
)
CARD_AT = None            # when the card rises: a spoken word, a frame number, or None (half a second after the phone)
ROWS_FOLLOW_BUTTON = True # after 'button' is tapped, rows nobody tapped tick themselves one by one
# Taps, in order: (when, where).
#   when  = a spoken word exactly as words.json has it ('send#2' = the second time), or a frame number.
#           A word lands on its stressed syllable; measure.py prints the frame for every word.
#   where = 'button' / 'row1' / 'row2'.. on the packaged card, or (x, y) as FRACTIONS of the glass for a recording or
#           picture: (0, 0) top left, (1, 1) bottom right. GRID=1 draws the fractions on the glass in a snapshot.
TAPS = [('approve', 'button')]
TURN = None               # optional: word / frame where the phone turns to face the viewer (at least 1 s after it lands)
IN_FRAME = 3              # frame the phone starts flying in. Keep it 2 or more: frame 0 must be the plain clip
OUT_FRAME = None          # frame the phone starts leaving. None = 16 frames before the end (it needs 12 to be gone)
SIDE = 'auto'             # 'auto' = the side with more room beside the speaker, measured on the speaker's cutout. Or 'left' / 'right'
PHONE_W = 'auto'          # 'auto' = the biggest that fits (250 to 430 px wide). Or a width in px
PHONE_TOP = 'auto'        # 'auto' = level with the speaker's head. Or the y of the phone's top edge in px
LAYER = 'behind'          # 'behind' = between background and speaker, the speaker's head and hands pass in front (needs the cutout)
                          # 'front'  = on top of the picture; it then keeps fully clear of the speaker (works with --no-cutout)
ROOM = 'auto'             # tight shot with no room: 'auto' slides the picture over while the phone is up and back before
                          # it leaves, 'off' never moves it, or type it: dict(scale=1.12, x=-130, y=-60)
COVER_MAX = 0.12          # LAYER='behind': the most of the glass the speaker may hide, averaged over the slot
HAND_FRAMES = ()          # optional, default off: frames where a fast hand crosses the phone and its edge looks blocky
MATTE_FIX = {}            # optional, default off: {frame: px} shave the cutout inside the phone on that frame (a blurred
                          # fingertip dragging a block of background across the glass). Re-run prep.py after changing
CAPS = 'auto'             # the effect's own caption words: 'auto' (from words.json) or [] for none
CAP_PUNCH = []            # spoken words shown big in the accent colour on their own line, e.g. the tapped word
CAP_FIX = {}              # respell what Whisper misheard: {'heard': 'Meant'}
CAP_Y = 1300              # top of the caption line (stay between 1260 and 1340)
ACCENT = '#FAE67A'        # accent colour: tapped button, ticks, rings, punch word. Never orange
GRADE = 'none'            # CSS filter on the footage for the WHOLE slot. Leave 'none': the reel grades, and a grade here
                          # would show on the first and last frame
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
SLOT = os.path.basename(HERE)
ENV = os.environ.get
N = M.clip()['frames']
DUR = N / 30
CREAM, INK, YEL = '#FFF8EF', '#14161C', ACCENT
RGB = ','.join(str(int(ACCENT.lstrip('#')[i:i + 2], 16)) for i in (0, 2, 4))
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'sparkle': 1.8, 'click': .3, 'click-soft': .37}
SFX_GAIN = 0.75

# phone, drawn at one design size (412 px wide) and scaled as a whole to the measured width
DW = 412
DH = round(DW * 2.06)
PH_R = round(DW * .158)
BEZ = 13
SW, SH = DW - 2 * BEZ, DH - 2 * BEZ
SR = PH_R - BEZ + 1
PERSP = 1500
TILT_Y, TILT_Z = 15, 2.5                  # resting pose (deg): screen turned toward the speaker
W_MIN, W_MAX, ROOM_WANT = 250, 430, 340
BOTTOM_MAX = 1240                         # the phone never reaches lower: caption words live below it
IS_VIDEO = bool(SCREEN) and SCREEN.lower().endswith(('.mp4', '.mov', '.webm', '.m4v'))
IS_PIC = bool(SCREEN) and not IS_VIDEO


def project(px, py, ry, rz, sc=1.0):
    """design px relative to the phone centre -> the same after tilt + perspective (GSAP order rotateZ * rotateY * scale)"""
    cy_, sy_ = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz_, sz_ = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    x, y = px * sc, py * sc
    x1, z1 = x * cy_, -x * sy_
    f = PERSP / (PERSP - z1)
    return (x1 * cz_ - y * sz_) * f, (x1 * sz_ + y * cz_) * f


def extents(d):
    """how far the tilted, floating phone reaches past its own box (design px): left, top, right, bottom. d = +1 right side"""
    xs, ys = [], []
    r = PH_R * .45
    pts = [(sx * (DW / 2 - a), sy * (DH / 2 - b)) for sx in (-1, 1) for sy in (-1, 1) for a, b in ((r, 0), (0, r))]
    poses = [(-TILT_Y * d + fy, TILT_Z * d + fz, 1.0, dy) for fy in (0, 2.4 * d) for fz in (0, -.6 * d) for dy in (0, -9)]
    if TURN is not None:
        poses.append((-TILT_Y * d * .53 + 2.4 * d, TILT_Z * d, 1.025, -9))
    for ry, rz, sc, dy in poses:
        for px, py in pts:
            x, y = project(px, py, ry, rz, sc)
            xs.append(x)
            ys.append(y + dy)
    return min(xs) + DW / 2, min(ys) + DH / 2, max(xs) - DW / 2, max(ys) - DH / 2


def _integral(g):
    return np.pad(g, ((1, 0), (1, 0))).cumsum(0).cumsum(1)


def _boxmean(ii, x0, y0, x1, y1):
    """mean of the grid over frame-px boxes (arrays allowed)"""
    c = M.CELL
    a, b = np.clip(np.floor(x0 / c).astype(int), 0, M.GW), np.clip(np.floor(y0 / c).astype(int), 0, M.GH)
    e, f = np.clip(np.ceil(x1 / c).astype(int), 0, M.GW), np.clip(np.ceil(y1 / c).astype(int), 0, M.GH)
    area = np.maximum(1, (e - a) * (f - b))
    return (ii[f, e] - ii[b, e] - ii[f, a] + ii[b, a]) / area


def _warp(g, room):
    """the matte grid as it sits in the frame once the picture is reframed (frame = native * scale + offset)"""
    if not room:
        return g
    c = M.CELL
    xs = np.clip(((np.arange(M.GW) * c + c / 2 - room['x']) / room['scale'] // c).astype(int), 0, M.GW - 1)
    ys = np.clip(((np.arange(M.GH) * c + c / 2 - room['y']) / room['scale'] // c).astype(int), 0, M.GH - 1)
    return g[np.ix_(ys, xs)]


def _place(mean, anyf, head_y, sides, widths):
    """biggest phone that fits beside the speaker: dict(side, w, x0, y0, cover) or None"""
    im, iu = _integral(mean), _integral(anyf)
    col = mean.sum(axis=0)
    him_x = float((col * (np.arange(M.GW) * M.CELL + M.CELL / 2)).sum() / col.sum()) if col.sum() > 0 else 540.0
    found = {}
    for tier, lim in ((0, .02), (1, COVER_MAX)):
        if LAYER == 'front' and tier:
            break
        for w in widths:
            k = w / DW
            best = None
            for side in sides:
                d = 1 if side == 'right' else -1
                el, et, er, eb = (v * k for v in extents(d))
                y_lo, y_hi = 226 - et, BOTTOM_MAX - k * DH - eb
                if y_hi < y_lo:
                    continue
                ys = np.arange(y_lo, y_hi + 1, 8) if PHONE_TOP == 'auto' else np.array([float(PHONE_TOP)])
                target = min(max(head_y - .12 * k * DH, y_lo), y_hi)
                for y0 in ys:
                    right_lim = 1039 if y0 + k * DH + eb <= 1155 else 974     # the right side is tighter low down
                    x_lo, x_hi = 41 - el, right_lim - k * DW - er
                    if x_hi < x_lo:
                        continue
                    xs = np.arange(x_lo, x_hi + 1, 8)
                    if LAYER == 'front':
                        cov = _boxmean(iu, xs + el - 16, y0 + et - 16, xs + k * DW + er + 16, y0 + k * DH + eb + 16)
                        ok = cov <= .002
                    else:
                        cov = _boxmean(im, xs + k * BEZ, y0 + k * BEZ, xs + k * (BEZ + SW), y0 + k * (BEZ + SH))
                        ok = cov <= lim
                    ok &= (xs + w / 2 > him_x) if d == 1 else (xs + w / 2 < him_x)      # on its own side of the speaker
                    if not ok.any():
                        continue
                    away = xs if d == 1 else 1080 - xs - w                     # smaller = closer to the speaker
                    cost = np.where(ok, abs(y0 - target) + .5 * away + (cov * 1500 if tier else 0), 1e9)
                    j = int(np.argmin(cost))
                    if best is None or cost[j] < best[0]:
                        best = (float(cost[j]), dict(side=side, w=int(w), x0=float(xs[j]), y0=float(y0), cover=float(cov[j])))
            if best:
                found[tier] = best[1]
                break
    if 0 in found and 1 in found:
        return found[1] if found[1]['w'] >= found[0]['w'] + 60 else found[0]
    return found.get(0) or found.get(1)


def layout():
    """Where the phone goes. Measured on the cutout: side with more room, biggest width that keeps the glass readable,
    never over the speaker. Tight shot: slides the picture over (ROOM), then goes smaller, then stops with a message."""
    f_in = max(2, int(IN_FRAME))
    f_out = N - 16 if OUT_FRAME is None else int(OUT_FRAME)
    if f_out > N - 14:
        print(f'!! OUT_FRAME {f_out} leaves no time to get out before the last frame: using {N - 14}')
        f_out = N - 14
    if f_out - f_in < 40:
        sys.exit(f'slot too short for a phone: {f_out - f_in} frames between in and out (needs 40, better 75 or more)')
    L = dict(f_in=f_in, f_out=f_out, f_end=f_out + 12, layer=LAYER, room=None)
    sides = ['right', 'left'] if SIDE == 'auto' else [SIDE]
    widths = list(range(W_MAX, W_MIN - 1, -10)) if PHONE_W == 'auto' else [int(PHONE_W)]
    if not M.has_cutout():
        if LAYER != 'front' or 'auto' in (SIDE, PHONE_W, PHONE_TOP):
            sys.exit('no cutout in this slot (assets/subject.webm). Either re-make the slot without --no-cutout, or set '
                     'LAYER = "front" and type SIDE, PHONE_W and PHONE_TOP in the CLIP block.')
        d = 1 if SIDE == 'right' else -1
        k = PHONE_W / DW
        el, et, er, eb = (v * k for v in extents(d))
        x0 = (1039 if PHONE_TOP + k * DH + eb <= 1155 else 974) - k * DW - er if d == 1 else 41 - el
        L.update(side=SIDE, w=int(PHONE_W), x0=float(x0), y0=float(PHONE_TOP), cover=0.0, head=None)
        return _finish(L)
    a = M.alpha()[f_in:f_out + 13]
    mean, anyf = a.mean(axis=0), (a.max(axis=0) > .35).astype(np.float32)
    hx, hy = M.head(a)
    best = _place(mean, anyf, hy, sides, widths)
    rooms = [ROOM] if isinstance(ROOM, dict) else []
    if ROOM == 'auto' and (best is None or best['w'] < min(ROOM_WANT, widths[0])):
        for s in (1.06, 1.10, 1.14, 1.18):
            for side in sides:
                rooms.append(dict(scale=s, x=round(-(s - 1) * 1080) if side == 'right' else 0,
                                  y=round(max(-(s - 1) * 1920, min(0, -(s - 1) * (hy + 200)))), side=side))
    for room in rooms:
        b = _place(_warp(mean, room), _warp(anyf, room), hy * room['scale'] + room['y'],
                   [room['side']] if 'side' in room else sides, widths)
        if b and (isinstance(ROOM, dict) or best is None or b['w'] > best['w']):
            best = dict(b, room={k: room[k] for k in ('scale', 'x', 'y')})
            if isinstance(ROOM, dict) or b['w'] >= ROOM_WANT:
                break
    if best is None:
        why = 'touching the speaker' if LAYER == 'front' else f'the speaker hiding more than {COVER_MAX:.0%} of the glass'
        sys.exit(f'no room for a phone beside the speaker: even {W_MIN} px wide does not fit inside the safe zone without {why}.\n'
                 'This shot is too tight for the effect. Use a wider take, or leave the effect out. (To force it: raise '
                 'COVER_MAX, or type ROOM = dict(scale=1.2, x=-216, y=-100) to push the speaker further over.)')
    L.update(best)
    L.setdefault('room', None)
    L['head'] = [round(hx), round(hy)]
    return _finish(L)


def _finish(L):
    d = 1 if L['side'] == 'right' else -1
    k = L['w'] / DW
    el, et, er, eb = (v * k for v in extents(d))
    L.update(d=d, k=k, h=round(k * DH),
             bounds=[round(L['x0'] + el), round(L['y0'] + et), round(L['x0'] + k * DW + er), round(L['y0'] + k * DH + eb)],
             glass=[round(L['x0'] + k * BEZ), round(L['y0'] + k * BEZ), round(L['x0'] + k * (BEZ + SW)), round(L['y0'] + k * (BEZ + SH))])
    return L


# ------------------------------------------------------------------ text
_fonts = {}


def text_w(text, font, fs):
    key = (font, round(fs))
    if key not in _fonts:
        try:
            from PIL import ImageFont
            _fonts[key] = ImageFont.truetype(os.path.join(HERE, 'assets/fonts', font), round(fs))
        except Exception:
            _fonts[key] = None
    f = _fonts[key]
    return f.getlength(text) if f else len(text) * fs * .56


def wrap(text, font, fs, maxw):
    lines, cur = [], ''
    for word in str(text).split():
        if cur and text_w(cur + ' ' + word, font, fs) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + ' ' + word).strip()
    return lines + ([cur] if cur else [])


def esc(s):
    return _html.escape(str(s))


# ------------------------------------------------------------------ icons (drawn, no product marks)
SPARK = ('<svg width="{s}" height="{s}" viewBox="0 0 24 24" style="flex:none"><path fill="{c}" d="M12 1.5c.7 5.6 2.9 8.3 10.5 10.5'
         '-7.6 2.2-9.8 4.9-10.5 10.5C11.3 16.9 9.1 14.2 1.5 12 9.1 9.8 11.3 7.1 12 1.5z"/></svg>')
BACK = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="rgba(255,248,239,.6)" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>')


def check_svg(i, size=24, sw=3.2):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" style="flex:none"><path id="{i}" d="M4.5 12.6l5 5L19.8 6.8" '
            f'fill="none" stroke="{INK}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" '
            'stroke-dasharray="24" stroke-dashoffset="24"/></svg>')


# ------------------------------------------------------------------ the packaged card (screen px, 386 wide)
CARD_L, PAD = 16, 19
CARD_W = SW - 2 * CARD_L
INNER = CARD_W - 2 * PAD
ROW_H, BTN_H = 42, 56


def card_layout():
    """every box of the card, laid out here (not by the browser) so tap targets are known before the render"""
    c = dict(CARD)
    rows = [r for r in (c.get('rows') or []) if str(r).strip()][:4]
    fs = 31
    title = wrap(c.get('title') or '', 'InterTight-800-normal.woff2', fs, INNER)
    if len(title) > 3:
        fs = 25
        title = wrap(c['title'], 'InterTight-800-normal.woff2', fs, INNER)
    lh = round(fs * 1.16)
    top = 208 if c.get('intro') else 150
    y = 20
    G = dict(c=c, rows=rows, title=title, fs=fs, lh=lh, top=top, y_label=y)
    y += 32 if c.get('label') else 2
    G['y_title'] = y
    y += lh * len(title) + (16 if title else 0)
    G['y_rows'] = y
    y += ROW_H * len(rows) + (10 if rows else 0)
    G['y_btn'] = y
    G['btn_w'] = 204 if c.get('button_alt') else INNER
    y += (BTN_H + PAD) if c.get('button') else PAD - 8
    G['h'] = y
    G['row_fs'] = [min(19.0, 19.0 * (INNER - 38) / max(1.0, text_w(r, 'Inter-500-normal.woff2', 19))) for r in rows]
    G['done_top'] = top + y + 16
    T = {}
    if c.get('button'):
        T['button'] = (CARD_L + PAD + G['btn_w'] / 2 + 6, top + G['y_btn'] + BTN_H / 2 + 2)
    for i in range(len(rows)):
        T[f'row{i + 1}'] = (CARD_L + PAD + 70, top + G['y_rows'] + i * ROW_H + ROW_H / 2)
    G['targets'] = T
    if top + y > SH - 34:
        print(f'!! the card is taller than the glass by {top + y - SH + 34:.0f} px: shorten the title or drop a row')
    return G


def card_html(G):
    c, h = G['c'], []
    A = h.append
    A('<div id="app">')
    A(f'<div id="hdr">{BACK}<div id="ava">{SPARK.format(s=24, c=INK)}</div><b>{esc(c.get("app") or "")}</b></div>')
    if c.get('intro'):
        A(f'<div class="bub" id="msg1">{esc(c["intro"])}</div>')
    A(f'<div class="bub" id="typing" style="top:{G["top"] + 4}px"><i id="td0"></i><i id="td1"></i><i id="td2"></i></div>')
    A(f'<div id="card" style="top:{G["top"]}px;height:{G["h"]}px">')
    if c.get('label'):
        A(f'<div id="clabel" style="top:{G["y_label"]}px">{SPARK.format(s=17, c=YEL)}<span>{esc(c["label"])}</span></div>')
    A(f'<div id="ctitle" style="top:{G["y_title"]}px;font-size:{G["fs"]}px;line-height:{G["lh"]}px">'
      + '<br>'.join(esc(t) for t in G['title']) + '</div>')
    for i, r in enumerate(G['rows']):
        A(f'<div class="row" id="row{i}" style="top:{G["y_rows"] + i * ROW_H}px"><div class="rc" id="rc{i}">{check_svg(f"rk{i}", 16, 3.6)}</div>'
          f'<span id="rt{i}" style="font-size:{G["row_fs"][i]:.1f}px">{esc(r)}</span></div>')
    if c.get('button'):
        A(f'<div id="btn" style="top:{G["y_btn"]}px;width:{G["btn_w"]}px;transform-origin:{G["btn_w"] / 2}px 50%">'
          f'<div id="bfront"><span>{esc(c["button"])}</span></div>'
          f'<div id="bback">{check_svg("ckpath")}<span>{esc(c.get("button_done") or c["button"])}</span></div></div>')
        if c.get('button_alt'):
            A(f'<div id="balt" style="top:{G["y_btn"]}px;left:{PAD + G["btn_w"] + 10}px;width:{INNER - G["btn_w"] - 10}px">{esc(c["button_alt"])}</div>')
    A('</div>')
    if c.get('done'):
        A(f'<div class="bub" id="msg2" style="top:{G["done_top"]}px">{esc(c["done"])}</div>')
    A('<div id="homebar"></div></div>')
    return '\n'.join(h)


def card_tweens(G, T_IN, T_CARD, taps):
    c, J = G['c'], []
    T = J.append
    T("gsap.set('#card',{autoAlpha:0});" + ("gsap.set('#msg2',{autoAlpha:0});" if c.get('done') else ''))
    if c.get('button'):
        T("gsap.set('#bback',{autoAlpha:0,rotationX:90,transformPerspective:420});gsap.set('#bfront',{transformPerspective:420});")
    if T_CARD - T_IN > .45:
        reps = max(1, int((T_CARD - T_IN - .26) / .32) * 2 - 1)
        for k in range(3):
            T(f"tl.to('#td{k}',{{y:-6,opacity:1,duration:.16,ease:'sine.inOut',yoyo:true,repeat:{reps}}},{T_IN + .2 + k * .09:.3f});")
    T(f"tl.to('#typing',{{autoAlpha:0,scale:.8,duration:.1,ease:'power2.in'}},{T_CARD - .1:.3f});")
    T(f"tl.fromTo('#card',{{autoAlpha:0,y:44,scale:.94}},{{autoAlpha:1,y:0,scale:1,duration:.42,ease:'back.out(1.5)',"
      f"immediateRender:false}},{T_CARD:.3f});")
    parts = (('#clabel', .06, c.get('label')), ('#ctitle', .1, True), ('.row', .15, G['rows']), ('#btn', .21, c.get('button')),
             ('#balt', .21, c.get('button') and c.get('button_alt')))
    for sel, dl, have in parts:
        if have:
            T(f"tl.fromTo('{sel}',{{autoAlpha:0,y:14}},{{autoAlpha:1,y:0,duration:.28,ease:'power3.out',immediateRender:false}},{T_CARD + dl:.3f});")
    ticked, last, t_btn = {}, T_CARD, None
    for t, where, _ in taps:
        if where == 'button':
            t_btn = t
        elif isinstance(where, str) and where.startswith('row'):
            ticked[int(where[3:]) - 1] = t
    if t_btn is not None:
        T(f"tl.fromTo('#btn',{{scale:1}},{{scale:1.045,duration:.16,ease:'sine.inOut',yoyo:true,repeat:1,immediateRender:false}},{t_btn - .5:.3f});")
        T(f"tl.to('#btn',{{scale:.93,duration:.05,ease:'power2.in'}},{t_btn - .04:.3f});")
        T(f"tl.to('#btn',{{scale:1,duration:.34,ease:'back.out(3.2)'}},{t_btn + .02:.3f});")
        T(f"tl.to('#bfront',{{rotationX:-90,duration:.04,ease:'power2.in'}},{t_btn:.3f});")      # accent is on screen 2 frames after the touch
        T(f"tl.set('#bfront',{{autoAlpha:0}},{t_btn + .038:.3f});tl.set('#bback',{{autoAlpha:1}},{t_btn + .038:.3f});")
        T(f"tl.to('#bback',{{rotationX:0,duration:.24,ease:'back.out(2.4)'}},{t_btn + .038:.3f});")
        T(f"tl.to('#ckpath',{{strokeDashoffset:0,duration:.16,ease:'power2.out'}},{t_btn + .1:.3f});")
        if c.get('button_alt'):
            T(f"tl.to('#balt',{{autoAlpha:0,x:16,duration:.12,ease:'power2.in'}},{t_btn + .03:.3f});")
            T(f"tl.to('#btn',{{width:{INNER},duration:.4,ease:'power3.out'}},{t_btn + .13:.3f});")
        last = t_btn + .3
        if ROWS_FOLLOW_BUTTON:
            k = 0
            for i in range(len(G['rows'])):
                if i not in ticked:
                    ticked[i] = t_btn + .34 + .2 * k
                    k += 1
    for i, t in ticked.items():
        if i >= len(G['rows']):
            sys.exit(f'TAPS names row{i + 1} but CARD has {len(G["rows"])} rows')
        T(f"tl.to('#rc{i}',{{backgroundColor:'{YEL}',borderColor:'{YEL}',duration:.1,ease:'power2.out'}},{t:.3f});")
        T(f"tl.fromTo('#rc{i}',{{scale:.6}},{{scale:1,duration:.3,ease:'back.out(3)',immediateRender:false}},{t:.3f});")
        T(f"tl.to('#rk{i}',{{strokeDashoffset:0,duration:.14,ease:'power2.out'}},{t + .04:.3f});")
        T(f"tl.to('#rt{i}',{{color:'{CREAM}',duration:.15}},{t:.3f});")
        last = max(last, t + .2)
    if c.get('done'):
        T(f"tl.fromTo('#msg2',{{autoAlpha:0,y:26,scale:.94}},{{autoAlpha:1,y:0,scale:1,duration:.36,ease:'back.out(1.6)',"
          f"immediateRender:false}},{last + .25:.3f});")
    return J


# ------------------------------------------------------------------ the phone
def media_html():
    pos = {'top': '50% 0%', 'bottom': '50% 100%'}.get(SCREEN_POS, '50% 50%')
    st = f'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:{pos}'
    if IS_VIDEO:
        return (f'<video id="scrv" src="assets/screen.mp4" muted playsinline data-start="0" data-media-start="0" '
                f'data-duration="{DUR:.3f}" data-track-index="5" style="{st}"></video>')
    return f'<img id="scri" src="assets/screen{os.path.splitext(SCREEN)[1].lower()}" style="{st}" />'


GRID = ''.join(f'<i style="left:{p}%;top:0;width:1px;height:100%"></i><i style="top:{p}%;left:0;height:1px;width:100%"></i>'
               f'<b style="left:{p}%;top:2px">.{p // 10}</b><b style="top:{p}%;left:2px">.{p // 10}</b>' for p in range(10, 100, 10))


def phone_html(L, screen, taps):
    d = L['d']
    depth = ''.join(f'<div class="phd{" phd-last" if k == 6 else ""}" style="transform:translateZ({-3 * k}px)"></div>' for k in range(6, 0, -1))
    dots = ''.join(f'<div class="ripple" id="rp{i}" style="left:{x - 150:.1f}px;top:{y - 150:.1f}px"></div><div class="touch" id="tc{i}"></div>'
                   for i, (_, _, (x, y)) in enumerate(taps))
    rings = ''.join(f'<div class="ring" id="rg{i}{j}" style="left:{BEZ + x - 250:.1f}px;top:{BEZ + y - 250:.1f}px;border-width:{3 - j}px"></div>'
                    for i, (_, _, (x, y)) in enumerate(taps) for j in (0, 1))
    grid = f'<div id="grid">{GRID}</div>' if ENV('GRID') else ''
    return f'''<div id="phouter"><div id="phwrap" style="left:{L['x0']:.1f}px;top:{L['y0']:.1f}px;transform:scale({L['k']:.4f})">
  <div id="phfloat"><div id="phtap"><div id="ph">
    <div id="phglow"></div>
    {depth}
    <div id="phkey" style="{'right' if d == 1 else 'left'}:-3px"></div>
    <div id="phbody"><div id="phbez"></div>
      <div id="phscreen">
        {screen}
        {grid}{dots}
        <div id="island"><i></i></div>
        <div id="glass"></div>
        <div id="sheen"></div>
      </div>
      <div id="rim"></div>
    </div>
    {rings}
  </div></div></div>
</div></div>'''


def phone_tweens(L, T_IN, T_OUT, T_TURN, taps):
    J, d, k = [], L['d'], L['k']
    T = J.append
    off = ((1080 - L['x0']) / k + 80) if d == 1 else -((L['x0'] + L['w']) / k + 80)
    T("gsap.set('#phouter',{opacity:0,filter:'blur(12px)'});gsap.set('#dim',{opacity:0});")
    T(f"gsap.set('#ph',{{x:{off:.0f},y:150,rotationY:{-64 * d},rotation:{15 * d},rotationX:9,scale:.8}});")
    T(f"tl.set('#phouter',{{opacity:1}},{T_IN:.3f});")
    T(f"tl.to('#ph',{{x:0,y:0,duration:.74,ease:'expo.out'}},{T_IN:.3f});")
    T(f"tl.to('#ph',{{rotationY:{-TILT_Y * d},rotation:{TILT_Z * d},rotationX:0,scale:1,duration:.98,ease:'back.out(1.3)'}},{T_IN:.3f});")
    T(f"tl.to('#phouter',{{filter:'blur(0px)',duration:.34,ease:'power2.out'}},{T_IN + .06:.3f});")
    T(f"tl.set('#phouter',{{filter:'none'}},{T_IN + .42:.3f});")
    T(f"tl.to('#dim',{{opacity:1,duration:.6,ease:'power2.out'}},{T_IN + .1:.3f});")
    t0 = T_IN + .8                                              # slow float: a bob and a breath of rotation on another period
    if T_OUT - t0 > .6:
        T(f"tl.to('#phfloat',{{y:-9,duration:1.7,ease:'sine.inOut',yoyo:true,repeat:{max(0, math.ceil((T_OUT - t0) / 1.7) - 1)}}},{t0:.3f});")
        T(f"tl.to('#phfloat',{{rotationY:{2.4 * d},rotation:{-.6 * d},duration:2.2,ease:'sine.inOut',yoyo:true,"
          f"repeat:{max(0, math.ceil((T_OUT - t0) / 2.2) - 1)}}},{t0:.3f});")
    T(f"gsap.set('#sheen',{{x:{-SW - 80}}});")
    T(f"tl.to('#sheen',{{x:{SW + 120},duration:.8,ease:'power2.inOut'}},{T_IN + .32:.3f});")
    if T_TURN is not None:                                      # the phone turns to the viewer
        T(f"tl.set('#sheen',{{x:{-SW - 80}}},{T_TURN - .05:.3f});")
        T(f"tl.to('#sheen',{{x:{SW + 120},duration:.85,ease:'power2.inOut'}},{T_TURN:.3f});")
        T(f"tl.to('#ph',{{rotationY:{-TILT_Y * d * .53:.2f},scale:1.025,duration:.8,ease:'power3.out'}},{T_TURN:.3f});")
    T("gsap.set('#phglow',{opacity:0});gsap.set('.ripple',{scale:.1,autoAlpha:0});gsap.set('.ring',{scale:.12,autoAlpha:0});"
      "gsap.set('.touch',{autoAlpha:0,scale:1.25});")
    prev = T_IN + .45
    for i, (t, _, (x, y)) in enumerate(taps):
        glide = min(.5, t - .06 - prev)                         # the dot glides in from below, presses on t, lifts
        if glide >= .12:
            sx, sy = min(SW - 30, x + 90), min(SH - 30, y + 150)
            T(f"gsap.set('#tc{i}',{{x:{sx:.0f},y:{sy:.0f}}});")
            T(f"tl.to('#tc{i}',{{autoAlpha:1,scale:1,duration:.14,ease:'power2.out'}},{t - .06 - glide:.3f});")
            T(f"tl.to('#tc{i}',{{x:{x:.1f},duration:{glide:.3f},ease:'power3.inOut'}},{t - .06 - glide:.3f});")
            T(f"tl.to('#tc{i}',{{y:{y:.1f},duration:{glide:.3f},ease:'power2.inOut'}},{t - .06 - glide:.3f});")
        else:
            T(f"gsap.set('#tc{i}',{{x:{x:.1f},y:{y:.1f}}});")
            T(f"tl.to('#tc{i}',{{autoAlpha:1,scale:1,duration:.06,ease:'power2.out'}},{t - .1:.3f});")
        T(f"tl.to('#tc{i}',{{scale:.72,duration:.05,ease:'power2.in'}},{t - .05:.3f});")
        T(f"tl.to('#tc{i}',{{scale:1.2,autoAlpha:0,duration:.26,ease:'power2.out'}},{t + .08:.3f});")
        T(f"tl.set('#rp{i}',{{autoAlpha:.55}},{t - .002:.3f});")
        T(f"tl.to('#rp{i}',{{scale:1,duration:.5,ease:'expo.out'}},{t:.3f});")
        T(f"tl.to('#rp{i}',{{autoAlpha:0,duration:.26,ease:'power1.out'}},{t + .1:.3f});")
        T(f"tl.to('#phtap',{{scale:.972,rotationX:2.6,duration:.05,ease:'power2.in'}},{t - .04:.3f});")     # the whole phone takes the tap
        gap = (taps[i + 1][0] if i + 1 < len(taps) else T_OUT - .1) - t        # tails end before the next tap starts
        T(f"tl.to('#phtap',{{scale:1,rotationX:0,duration:{max(.2, min(.7, gap - .06)):.3f},ease:'elastic.out(1,.42)'}},{t + .01:.3f});")
        for j, (dl, al) in enumerate(((.05, .85), (.17, .45))):
            T(f"tl.set('#rg{i}{j}',{{autoAlpha:{al}}},{t + dl:.3f});")
            T(f"tl.to('#rg{i}{j}',{{scale:1,duration:.8,ease:'expo.out'}},{t + dl:.3f});")
            T(f"tl.to('#rg{i}{j}',{{autoAlpha:0,duration:.55,ease:'power1.out'}},{t + dl + .1:.3f});")
        T(f"tl.to('#phglow',{{opacity:1,duration:.12,ease:'power2.out'}},{t + .04:.3f});")
        T(f"tl.to('#phglow',{{opacity:.18,duration:{max(.1, min(.8, gap - .24)):.3f},ease:'power2.out'}},{t + .17:.3f});")
        prev = t + .12
    # out: the way it came, then nothing of the effect is left on the picture
    T(f"tl.to('#phglow',{{opacity:0,duration:.2}},{T_OUT - .1:.3f});")
    T(f"tl.to('#ph',{{x:{off:.0f},y:120,rotationY:{-52 * d},rotation:{12 * d},scale:.84,duration:.36,ease:'power3.in'}},{T_OUT:.3f});")
    T(f"tl.to('#dim',{{opacity:0,duration:.34,ease:'power1.in'}},{T_OUT:.3f});")
    T(f"tl.set('#phouter',{{opacity:0}},{T_OUT + .37:.3f});")
    if L['layer'] == 'behind':
        T(f"gsap.set('#camB',{{opacity:0}});tl.set('#camB',{{opacity:1}},{T_IN:.3f});tl.set('#camB',{{opacity:0}},{T_OUT + .385:.3f});")
    if L['room']:
        r = L['room']
        T(f"tl.to('.cam',{{scale:{r['scale']},x:{r['x']},y:{r['y']},duration:.7,ease:'power3.out'}},{T_IN:.3f});")
        T(f"tl.to('.cam',{{scale:1,x:0,y:0,duration:.46,ease:'power2.inOut'}},{T_OUT - .1:.3f});")
    return J


# ------------------------------------------------------------------ captions (the effect's own; the reel usually captions instead)
def caps(T_IN, T_OUT):
    if not CAPS or ENV('CAPTIONS') == '0':
        return '', []
    env, fix, punch = M.envelope(), {M.norm(a): b for a, b in CAP_FIX.items()}, {M.norm(p) for p in CAP_PUNCH}
    groups = []
    for w in M.words():
        st = M.stress(env, w['start'], w['end'])
        is_p = M.norm(w['text']) in punch
        t = st if is_p else max(w['start'], min(st, w['end'] - .05))
        if not (T_IN <= t <= T_OUT - .15):
            continue
        raw = fix.get(M.norm(w['text']), w['text'])
        text, closed = raw.rstrip(',.'), raw[-1:] in ',.?!'
        g = groups[-1] if groups else None
        fits = g and not g['closed'] and t - g['end'] < .45
        if is_p:
            groups.append(dict(kind='y', words=[(t, text, 'y')], chars=0, closed=closed, end=w['end']))
            continue
        if fits and g['kind'] == 'y' and g['chars'] + len(text) <= 18:
            g['words'].append((t, text, 's'))
        elif fits and g['kind'] == '' and len(g['words']) < 4 and g['chars'] + len(text) < 15:
            g['words'].append((t, text, ''))
        else:
            groups.append(dict(kind='', words=[(t, text, '')], chars=0, closed=False, end=0))
            g = groups[-1]
        g = groups[-1]
        g.update(chars=g['chars'] + len(text) + 1, closed=closed, end=w['end'])
    out, tw = [], []
    for gi, g in enumerate(groups):
        a = g['words'][0][0] - .03
        b = min(groups[gi + 1]['words'][0][0] - .03 if gi + 1 < len(groups) else 1e9, g['end'] + .45, T_OUT + .12)
        spans = ''
        for k, (t, text, c) in enumerate(g['words']):
            st = f' style="font-size:{min(104, round(104 * 11 / max(11, len(text))))}px"' if c == 'y' else ''
            spans += f'<span id="cp{gi}-{k}"{(" class=" + chr(34) + c + chr(34)) if c else ""}{st}>{esc(text)}</span>'
            t0 = max(a, t - .03)
            tw.append(f"gsap.set('#cp{gi}-{k}',{{autoAlpha:0}});")
            if c == 'y':     # punch word: sharp within 3 frames, the scale keeps settling
                tw.append(f"tl.fromTo('#cp{gi}-{k}',{{autoAlpha:0,filter:'blur(10px)'}},{{autoAlpha:1,filter:'blur(0px)',duration:.1,"
                          f"ease:'power2.out',immediateRender:false}},{t0:.3f});")
                tw.append(f"tl.fromTo('#cp{gi}-{k}',{{scale:1.38,y:10}},{{scale:1,y:0,duration:.32,ease:'back.out(2.6)',immediateRender:false}},{t0:.3f});")
            else:
                tw.append(f"tl.fromTo('#cp{gi}-{k}',{{autoAlpha:0,scale:1.22,y:8,filter:'blur(12px)'}},{{autoAlpha:1,scale:1,y:0,"
                          f"filter:'blur(0px)',duration:.18,ease:'power3.out',immediateRender:false}},{t0:.3f});")
        out.append(f'<div class="cap" id="cap{gi}" style="top:{CAP_Y - (22 if g["kind"] == "y" else 0)}px">{spans}</div>')
        tw.append(f"tl.to('#cap{gi}',{{autoAlpha:0,duration:.08,ease:'power1.in'}},{b - .08:.3f});tl.set('#cap{gi}',{{autoAlpha:0}},{b:.3f});")
    return '\n'.join(out), tw


def audio(events):
    if ENV('SFX') == '0':
        return []
    out, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(events, key=lambda x: x[1])):
        t = max(0.0, t)
        dd = min(SFX_LEN[name], DUR - t)
        if dd <= .05:
            continue
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + dd
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{dd:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def css(L):
    d = L['d']
    cx, cy = (L['bounds'][0] + L['bounds'][2]) / 2, (L['bounds'][1] + L['bounds'][3]) / 2
    edge = ('linear-gradient(90deg,#24262c 0%,#3a3c44 40%,#7c7f8a 88%,#c5c8d2 97%,#8d909b 100%)' if d == 1 else
            'linear-gradient(270deg,#24262c 0%,#3a3c44 40%,#7c7f8a 88%,#c5c8d2 97%,#8d909b 100%)')
    grade = '' if GRADE in ('none', '', None) else f'filter:{GRADE};'
    return f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
.cam{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:0 0}}
.g{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;{grade}}}
#camA{{z-index:0}}
#camB{{z-index:4}}
#dim{{position:absolute;inset:0;z-index:1;pointer-events:none;
  background:radial-gradient(52% 44% at {cx / 10.8:.1f}% {cy / 19.2:.1f}%,rgba(10,9,8,.5) 0%,rgba(10,9,8,.26) 45%,rgba(10,9,8,0) 100%)}}
#phouter{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:3}}
#phwrap{{position:absolute;width:{DW}px;height:{DH}px;perspective:{PERSP}px;transform-origin:0 0}}
#phfloat,#phtap,#ph{{position:absolute;inset:0;transform-style:preserve-3d}}
#phglow{{position:absolute;inset:26px;border-radius:{PH_R}px;transform:translateZ(-21px);
  box-shadow:0 0 110px 46px rgba({RGB},.62),0 0 34px 18px rgba({RGB},.5)}}
.phd{{position:absolute;inset:0;border-radius:{PH_R}px;background:{edge}}}
.phd-last{{box-shadow:0 60px 100px rgba(6,5,4,.5),0 22px 36px rgba(6,5,4,.34),0 4px 10px rgba(6,5,4,.3)}}
#phkey{{position:absolute;top:{DH * .27:.0f}px;width:5px;height:{DH * .11:.0f}px;border-radius:3px;
  background:linear-gradient(90deg,#6d707b,#b9bcc6);transform:translateZ(-9px)}}
#phbody{{position:absolute;inset:0;border-radius:{PH_R}px;
  background:linear-gradient(128deg,#8f929d 0%,#4a4c55 9%,#202127 30%,#16171b 62%,#3d3f47 88%,#9da0ab 100%)}}
#phbez{{position:absolute;inset:3px;border-radius:{PH_R - 3}px;background:#050506}}
#phscreen{{position:absolute;left:{BEZ}px;top:{BEZ}px;width:{SW}px;height:{SH}px;border-radius:{SR}px;overflow:hidden;background:{INK}}}
#rim{{position:absolute;left:{BEZ}px;top:{BEZ}px;width:{SW}px;height:{SH}px;border-radius:{SR}px;
  box-shadow:inset 0 0 0 1.5px rgba(255,255,255,.07),inset 0 0 26px rgba(0,0,0,.3)}}
#island{{position:absolute;left:{SW / 2 - 58:.0f}px;top:13px;width:116px;height:34px;border-radius:17px;background:#000}}
#island i{{position:absolute;right:11px;top:11px;width:12px;height:12px;border-radius:50%;
  background:radial-gradient(circle at 35% 35%,#2b3350,#0a0c14 60%)}}
#glass{{position:absolute;inset:0;
  background:linear-gradient(116deg,rgba(255,255,255,.15) 0%,rgba(255,255,255,.06) 21%,rgba(255,255,255,0) 36%,rgba(255,255,255,0) 78%,rgba(255,255,255,.05) 100%)}}
#sheen{{position:absolute;left:0;top:-140px;width:150px;height:{SH + 280}px;
  background:linear-gradient(90deg,rgba(255,255,255,0) 0%,rgba(255,255,255,.2) 50%,rgba(255,255,255,0) 100%);transform:rotate(17deg)}}
.touch{{position:absolute;left:-26px;top:-26px;width:52px;height:52px;border-radius:50%;background:rgba(255,255,255,.36);
  border:2px solid rgba(255,255,255,.82);box-shadow:0 6px 16px rgba(0,0,0,.38)}}
.ripple{{position:absolute;width:300px;height:300px;border-radius:50%;
  background:radial-gradient(closest-side,rgba({RGB},0) 62%,rgba({RGB},.42) 88%,rgba({RGB},0) 100%)}}
.ring{{position:absolute;width:500px;height:500px;border-radius:50%;border:3px solid {YEL};transform:translateZ(2px)}}
#grid{{position:absolute;inset:0}}
#grid i{{position:absolute;background:rgba(255,60,60,.8)}}
#grid b{{position:absolute;font:600 15px 'Inter',sans-serif;color:#fff;background:rgba(0,0,0,.6);padding:0 3px}}
#app{{position:absolute;inset:0;font-family:'Inter',sans-serif;font-weight:500;color:{CREAM};
  background:radial-gradient(120% 60% at 50% 0%,#1D2029 0%,{INK} 60%)}}
#hdr{{position:absolute;left:0;right:0;top:62px;height:68px;display:flex;align-items:center;gap:10px;padding:0 14px;
  border-bottom:1px solid rgba(255,248,239,.07)}}
#hdr b{{font-weight:600;font-size:20px;letter-spacing:-.01em;white-space:nowrap}}
#ava{{width:44px;height:44px;border-radius:50%;background:{YEL};display:flex;align-items:center;justify-content:center;flex:none}}
.bub{{position:absolute;left:{CARD_L}px;padding:13px 17px;border-radius:22px 22px 22px 8px;background:#242731;
  font-size:19px;line-height:26px;white-space:nowrap;transform-origin:0 100%}}
#msg1{{top:146px}}
#typing{{display:flex;gap:7px;padding:19px 18px}}
#typing i{{width:10px;height:10px;border-radius:50%;background:{CREAM};opacity:.4}}
#card{{position:absolute;left:{CARD_L}px;width:{CARD_W}px;border-radius:26px;transform-origin:20% 100%;
  background:linear-gradient(180deg,#282B37 0%,#1E2029 100%);border:1px solid rgba(255,248,239,.09);
  box-shadow:0 18px 40px rgba(0,0,0,.4)}}
#clabel{{position:absolute;left:{PAD}px;height:20px;display:flex;align-items:center;gap:7px;white-space:nowrap;
  font-weight:600;font-size:13.5px;letter-spacing:.15em;color:{YEL}}}
#ctitle{{position:absolute;left:{PAD}px;width:{INNER}px;font-family:'Inter Tight',sans-serif;font-weight:800;
  letter-spacing:-.012em;color:{CREAM};white-space:nowrap}}
.row{{position:absolute;left:{PAD}px;width:{INNER}px;height:{ROW_H}px;display:flex;align-items:center;gap:12px;white-space:nowrap}}
.row span{{color:rgba(255,248,239,.66)}}
.rc{{width:26px;height:26px;border-radius:50%;border:2px solid rgba(255,248,239,.3);flex:none;display:flex;align-items:center;
  justify-content:center;background-color:rgba(255,248,239,0)}}
#btn{{position:absolute;left:{PAD}px;height:{BTN_H}px}}
#bfront,#bback{{position:absolute;inset:0;border-radius:{BTN_H / 2}px;display:flex;align-items:center;justify-content:center;gap:9px;
  font-weight:600;font-size:22px;letter-spacing:-.01em;color:{INK};overflow:hidden;white-space:nowrap}}
#bfront{{background:{CREAM};box-shadow:0 8px 20px rgba(0,0,0,.3)}}
#bback{{background:{YEL};box-shadow:0 8px 26px rgba({RGB},.32)}}
#balt{{position:absolute;height:{BTN_H}px;border-radius:{BTN_H / 2}px;border:1.5px solid rgba(255,248,239,.16);display:flex;
  align-items:center;justify-content:center;font-size:17px;color:rgba(255,248,239,.6);white-space:nowrap}}
#homebar{{position:absolute;left:{SW / 2 - 66:.0f}px;bottom:9px;width:132px;height:5px;border-radius:3px;background:rgba(255,248,239,.5)}}
.cap{{position:absolute;left:30px;width:960px;z-index:6;text-align:center;color:#fff;
  font-family:'Inter Tight',sans-serif;font-weight:900;font-size:80px;line-height:1;letter-spacing:-.045em;white-space:nowrap;
  text-shadow:0 8px 34px rgba(0,0,0,.6),0 2px 8px rgba(0,0,0,.45)}}
.cap span{{display:inline-block;margin:0 .13em;transform-origin:50% 70%}}
.cap .y{{display:block;margin:0 0 10px;color:{YEL};line-height:.92}}
.cap .s{{font-size:58px;letter-spacing:-.035em}}
"""


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def main():
    L = layout()
    T_IN, T_OUT = L['f_in'] / 30, L['f_out'] / 30
    T_CARD = M.when(CARD_AT, T_IN + .5)
    T_TURN = M.when(TURN)
    G = None if SCREEN else card_layout()
    taps = []                                                   # (seconds, where, (x, y) in screen px)
    for wh, where in TAPS:
        t = M.when(wh)
        if isinstance(where, str):
            if G is None:
                sys.exit(f'tap "{where}": named targets only exist on the packaged card. With a recording or picture give (x, y) fractions.')
            if where not in G['targets']:
                sys.exit(f'tap "{where}": the card has {", ".join(G["targets"]) or "no targets"}')
            xy = G['targets'][where]
        else:
            xy = (float(where[0]) * SW, float(where[1]) * SH)
        if not (T_IN + .5 <= t <= T_OUT - .1):
            print(f'!! tap at frame {round(t * 30)} is outside the time the phone is up and settled '
                  f'(frames {L["f_in"] + 15} to {L["f_out"] - 3}): move IN_FRAME / OUT_FRAME or start the slot earlier')
        if G is not None and t < T_CARD + .35:
            print(f'!! tap at frame {round(t * 30)} lands before the card is up (CARD_AT frame {round(T_CARD * 30)}): set CARD_AT earlier')
        taps.append((t, where, xy))
    if T_TURN is not None and not (T_IN + 1.0 <= T_TURN <= T_OUT - .8):
        print(f'!! TURN at frame {round(T_TURN * 30)} overlaps the fly-in or the exit')
    if SCREEN and not os.path.exists(os.path.join(HERE, SCREEN)):
        sys.exit(f'SCREEN = "{SCREEN}" is not in the slot. Copy the buyer\'s own recording or picture into screen/ and run prep.py.')
    screen = media_html() if SCREEN else card_html(G)
    tweens = phone_tweens(L, T_IN, T_OUT, T_TURN, taps) + ([] if SCREEN else card_tweens(G, T_IN, T_CARD, taps))
    cap_html, cap_tw = caps(T_IN, T_OUT)
    events = [('whoosh-short', T_IN - .03, .25), ('whoosh-short', T_OUT, .16)]
    events += [('click', t - .015, .6) for t, _, _ in taps]
    if G is not None:
        events += [('pop', T_CARD - .02, .12)] + [('sparkle', t + .06, .10) for t, w, _ in taps if w == 'button']
    subject = 'assets/subject_soft.webm'
    if L['layer'] == 'behind' and not os.path.exists(os.path.join(HERE, subject)):
        sys.exit('assets/subject_soft.webm is missing: run prep.py first (it softens the cutout edge for the dark phone).')
    cut = (f'<div class="cam" id="camB"><video id="cut" class="g" src="{subject}" muted playsinline data-start="0" data-media-start="0" '
           f'data-duration="{DUR:.3f}" data-track-index="1"></video></div>') if L['layer'] == 'behind' else ''
    nl = '\n'
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css(L)}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(events))}
  <div class="cam" id="camA"><video id="bgv" class="g" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video></div>
  <div id="dim"></div>
  {phone_html(L, screen, taps)}
  {cut}
{cap_html}
{SAFE_GUIDE if ENV('SAFE') else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tweens + cap_tw)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open(os.path.join(HERE, 'index.html'), 'w').write(page)
    # tap points in frame px (resting pose) for check.py
    cxp, cyp = L['x0'] + L['k'] * DW / 2, L['y0'] + L['k'] * DH / 2
    pts = []
    for t, where, (x, y) in taps:
        px, py = project(BEZ + x - DW / 2, BEZ + y - DH / 2, -TILT_Y * L['d'], TILT_Z * L['d'])
        pts.append(dict(frame=round(t * 30), where=where if isinstance(where, str) else list(where),
                        x=round(cxp + L['k'] * px), y=round(cyp + L['k'] * py)))
    L.update(taps=pts, frames=N, slot=SLOT, screen=SCREEN or 'card')
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump(L, open(os.path.join(HERE, 'work', 'layout.json'), 'w'), indent=1)
    b = L['bounds']
    print(f'wrote index.html  {N} frames  screen: {SCREEN or "packaged card"}  layer: {L["layer"]}')
    print(f'  phone: {L["side"]} side, {L["w"]} x {L["h"]} px, tilted bounds x {b[0]}..{b[2]}  y {b[1]}..{b[3]}  '
          f'(safe: x 35..1045, y 220..1470, x <= 980 below y 1155)')
    if L.get('head'):
        print(f'  speaker: head top around x {L["head"][0]}, y {L["head"][1]}; the speaker hides {L["cover"]:.1%} of the glass on average')
    if L['room']:
        print(f'  ROOM: the picture slides to scale {L["room"]["scale"]}, x {L["room"]["x"]}, y {L["room"]["y"]} while the phone is up')
    if L['k'] < .7:
        print(f'!! the phone is small ({L["w"]} px): keep the words on the glass few and short, or use a wider shot')
    print(f'  in frame {L["f_in"]}, out frame {L["f_out"]}, gone by frame {L["f_end"]}'
          + (f', card frame {round(T_CARD * 30)}' if G is not None else '') + (f', turn frame {round(T_TURN * 30)}' if T_TURN is not None else ''))
    for p in pts:
        print(f'  tap frame {p["frame"]:4d}  {p["where"]}  at frame px ({p["x"]}, {p["y"]})')
    print(f'  snapshot times worth looking at: {",".join(f"{v:.2f}" for v in sorted({round(T_IN + .5, 2), *[round(p["frame"] / 30 + .1, 2) for p in pts], round(T_OUT - .1, 2)}))}')


if __name__ == '__main__':
    main()
