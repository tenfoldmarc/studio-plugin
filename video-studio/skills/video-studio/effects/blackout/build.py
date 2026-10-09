#!/usr/bin/env python3
"""blackout: the clip starts in its normal look, the room dims on a line while the speaker stays lit, the punch word
slams in behind the head with a flash and a small camera kick, and the lights snap back on at the next cut (or the
next line). Runs from the slot folder (made by fx_new.py, with a cutout).

  onsets.py   word onsets as frames                       -> fill the CLIP block below
  prep.py     measures the speaker, cleans the cutout edge (assets/subject_lit.webm), writes check pictures
  build.py    (this file) places the punch word from the measured speaker, writes index.html
  check.py    after the render: plain frames at both ends, how dim the room got, sheet + edge crop from the final mp4

Switches: SAFE=1 safe-zone guide, CAPTIONS=0 no punch word (lights, flash and kick only), SFX=0 no sounds.
"""
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FP = shutil.which('ffprobe') or 'ffprobe'

# ==== CLIP (edit this) ====
F_DIM = 40           # first frame the room starts to dim: onset of the first word of the line that builds to the punch
                     # (onsets.py, "onset" column). 3 or later, so the slot opens on the plain picture.
DIM_FRAMES = 24      # frames the dim takes (24 = 0.8 s). Shorter when the line is short: it should be down by F_PUNCH.
F_PUNCH = 70         # frame the punch word is said (its onset): word, flash and camera kick all land on this frame
PUNCH = 'word'       # the punch word, typed the way the speaker says it (a full stop after it is fine). One word,
                     # two at most, and only what the speaker really says. '' = no word.
F_SNAP = 'auto'      # frame the lights snap back on. 'auto' = the first cut after F_PUNCH (clip.json "cut_frames").
                     # No cut in the slot: the onset of the first word of the next line. 12+ frames after F_PUNCH and
                     # 14+ before the slot's last frame. None = stay dim to the last frame (the slot must END ON A CUT).
DIM = 0.46           # room brightness while dim (0.46 = about half; 0.30 darker, 0.60 lighter). Never near black.
COOL = 1.0           # how much the dim room cools and loses colour (1 = full, 0 = brightness only)
EDGE_DARK = 1.0      # darkness closing in from the frame edges and the floor (1 = full, 0 = none)
PUSH = 1.055         # slow push-in on the face from F_DIM to the punch (1 = none). Back to 1:1 after the snap.
KICK = 1.0           # camera kick on the punch: 1 = a 5 % bump and a 6 px shake over 4 frames. 0.5 softer, 0 = none
FLASH = 0.28         # strength of the flash on the punch (0 = none)
FLASH_COLOUR = '#FFE7BE'       # colour of that flash (a warm white)
SNAP_FLASH = 0.5     # strength of the flash when the lights come back (0 = none)
SNAP_COLOUR = '#FFFFFF'        # colour of that flash
EDGE_CHOKE = 1.5     # px the cutout edge is pulled in. Pale line around the speaker on work/check_edge.jpg: 2.5.
                     # Thin hair eaten: 0.8. 0 with EDGE_SPILL 0 = use the cutout as it is
EDGE_SPILL = 3       # px of the speaker's outer edge recoloured from inside (kills the wall-coloured rim). 0 = off
GRADE = ''           # css filter on the whole slot. '' = off (the slot hands back plain footage at both ends)
SOUNDS = True        # one low hit on the punch, a light-switch click and a quiet whoosh on the snap (stock sounds)
# ==== END CLIP ====

# ==== WORD STYLE (the reel's caption or overall style wins: copy its typeface, case, weight and colour here) ====
# These defaults are only for a reel with no style of its own. To let the reel's captions say the word instead,
# build with CAPTIONS=0: the room still dims, flashes, kicks and snaps back.
WORD_FONT = 'Inter Tight'                        # css font-family: a face from assets/fonts/fonts.css
WORD_FONT_FILE = 'InterTight-900-normal.woff2'   # the same face as a file in assets/fonts (used to measure the word)
WORD_WEIGHT = 900                                # css font-weight of that face
WORD_ITALIC = False                              # True for an italic face
WORD_CASE = 'lower'                              # 'lower', 'upper', 'title' or 'as-typed'
WORD_TRACK = -0.05                               # letter-spacing in em
WORD_COLOUR = '#FAE67A'                          # colour of the letters
WORD_GLOW = 'auto'                               # soft glow behind the letters: 'auto' = the word's own colour,
                                                 # a colour, or '' = none
WORD_PLACE = 'auto'  # 'auto' = 'behind', then 'left' / 'right', then 'chest' when there is no room.
                     # 'behind' (above the head, feet of the letters tucked behind it), 'left' / 'right' (in the
                     # room beside the head), 'chest' (in front, under the chin), or by hand:
                     # ('back' | 'front', centre x, baseline y) in a-roll px, read off work/check_sheet.jpg
WORD_SIZE = 'auto'   # 'auto' (as big as the place and the safe zone allow) or a font size in px
# ==== END WORD STYLE ====

FPS = 30
SETTLE_FR = 11                                   # frames after the snap until the picture is plain again
RAW = 'brightness(1) contrast(1) saturate(1) hue-rotate(0deg)'


def num(x):
    """a number for a css filter string WITHOUT trailing zeros and never '-0': the animation library reads the '0' of
    '0.460' or '1.100' as a unit and the room turns flat grey for the whole dim"""
    return '%g' % (round(x, 4) + 0.0)


ROOM = (f'brightness({num(DIM)}) contrast({num(1 + .1 * COOL)}) saturate({num(1 - .38 * COOL)}) '
        f'hue-rotate({num(-8 * COOL)}deg)')     # the room: down, a touch cooler, less colour (never grey)
SUBJ = 'brightness(1) contrast(1.05) saturate(.92) hue-rotate(0deg)'      # the speaker stays lit, skin natural
SFX_GAIN = 0.75
SAFE_BOX = (35, 220, 1045, 1470, 1155, 980)      # left, top, right, bottom, and from y 1155 down the right limit is 980
PEAK = PUSH + .05 * KICK                         # largest scale the stage reaches (first frame of the kick)

ON = {k: os.environ.get(k, '1') != '0' for k in ('CAPTIONS', 'SFX')}
SAFE = bool(os.environ.get('SAFE'))


def clip():
    return json.load(open(os.path.join(HERE, 'clip.json')))


def snap_frame(c=None):
    """F_SNAP as a frame number (or None = the room stays dim to the last frame)"""
    if F_SNAP != 'auto':
        return F_SNAP
    cuts = [f for f in (c or clip()).get('cut_frames', []) if f > F_PUNCH]
    if not cuts:
        sys.exit("F_SNAP = 'auto' but clip.json has no cut after F_PUNCH: give F_SNAP as a frame (the onset of the "
                 "next line) or None (the slot ends on a cut)")
    return min(cuts)


def end_frame(n_frames, snap):
    """first plain frame after the snap (or the frame count when the room stays dim)"""
    return n_frames if snap is None else snap + SETTLE_FR


def stamp(snap):
    """everything prep.py bakes in: build.py refuses to run when this no longer matches work/measure.json"""
    return json.loads(json.dumps([F_DIM, F_PUNCH, snap, EDGE_CHOKE, EDGE_SPILL]))


def validate(n, snap):
    if F_DIM < 3:
        sys.exit('F_DIM must be 3 or later: the slot starts on plain footage')
    if F_PUNCH < F_DIM + 6:
        sys.exit(f'F_PUNCH {F_PUNCH}: the room needs at least 6 frames to dim first (F_DIM is {F_DIM})')
    last = n if snap is None else snap
    if last < F_PUNCH + 12:
        sys.exit(f'the lights come back on f{last}: the punch word needs 12+ frames on screen (F_PUNCH is {F_PUNCH})')
    if snap is not None and snap + SETTLE_FR + 2 > n - 1:
        sys.exit(f'F_SNAP {snap} is too late for {n} frames: {n - SETTLE_FR - 3} or earlier (the picture is plain '
                 f'{SETTLE_FR} frames after it), or None = end on a cut')


def F(n):
    """time of frame n, 2 ms early so a tl.set lands ON that frame. A tween that starts at F(n) still shows its start
    value on frame n (wanted for the punch and the snap: the word, the flashes and the kick are strongest on their
    frame). The dim starts at F(F_DIM - 1), so F_DIM is the first frame that moves."""
    return max(0.0, n / FPS - .002)


def probe(path, entry):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', entry, '-of', 'csv=p=0', os.path.join(HERE, path)],
                                capture_output=True, text=True).stdout.strip())


def cased(text):
    return {'lower': text.lower(), 'upper': text.upper(), 'title': text.title()}.get(WORD_CASE, text)


_font = []


def ink(text, size):
    """(width, ink above the baseline, ink below it) of the word at this font size"""
    n = len(text)
    try:
        if not _font:
            from PIL import ImageFont
            f = ImageFont.truetype(os.path.join(HERE, 'assets/fonts', WORD_FONT_FILE), 1000)
            try:                                     # a variable font opens at its default weight: set the real one
                f.set_variation_by_axes([min(a['maximum'], max(a['minimum'], WORD_WEIGHT))
                                         if a.get('name') in (b'Weight', 'Weight') else a['default']
                                         for a in f.get_variation_axes()])
            except OSError:
                pass                                 # a static font
            _font.append(f)
        f = _font[0]
        w = sum(f.getlength(c) for c in text)
        _, t, _, b = f.getbbox(text, anchor='ls')
        up, down = -t * 1.05, max(0, b)              # 5 % headroom: dots and accents can sit above the measured top
    except Exception:                                # no Pillow, or it cannot read this font file: rough table values
        if not _font:
            print('  !! word measured from rough table values: this Python has no Pillow or cannot read the font file. '
                  'Run build.py with the same Python as prep.py, and check the yellow ink box on a SAFE=1 snapshot')
            _font.append(None)
        w = n * (640 if text.isupper() else 575)
        up = 745 if any(c in 'bdfhklt' or c.isupper() or c.isdigit() for c in text) else 560
        down = 200 if any(c in 'gjpqy' for c in text) else 12
    k = size / 1000
    return (w + WORD_TRACK * 1000 * (n - 1)) * k, up * k, down * k


def allowed(origin, bottom_y=None):
    """safe zone pulled in so the word is still inside it at the largest scale of the push-in and the kick"""
    ox, oy = origin
    l, t, r, b, y2, r2 = SAFE_BOX
    inv = lambda v, o: o + (v - o) / PEAK
    box = [inv(l + 6, ox), inv(t + 8, oy), inv(r - 6, ox), inv(b - 8, oy)]
    if bottom_y is not None and oy + (bottom_y - oy) * PEAK > y2:
        box[2] = inv(r2 - 6, ox)
    return box


def place_word(M, text):
    """the punch word placed from the measured speaker -> dict(text, layer, cx, base, size, ink box)"""
    S = M['summary']
    hx, top, neck, hw, hh = S['head_x'], S['head_top'], S['neck_y_max'], S['head_w'], S['head_h']
    origin = tuple(M['origin'])
    left_edge, right_edge = M['left_edge'], M['right_edge']          # per 2 px row: leftmost / rightmost speaker px
    face = (hx - hw / 2 - 6, S['head_top_min'] - 6, hx + hw / 2 + 6, neck)
    w1, up1, dn1 = (v / 1000 for v in ink(text, 1000))               # per px of font size
    # / 1.035: the word creeps 3.5 % larger while it is up
    fit = lambda width_max, cap: min(cap, width_max / 1.035 / w1) if WORD_SIZE == 'auto' else float(WORD_SIZE)
    place, tried = ('behind' if WORD_PLACE == 'auto' else WORD_PLACE), []
    while True:
        tried.append(place)
        box = allowed(origin)
        if isinstance(place, (tuple, list)):
            layer, cx, base = place
            s = fit(box[2] - box[0], 320)
            break
        if place == 'behind':
            layer = 'back'
            s = fit(box[2] - box[0], 320)
            # tucked a fifth of its height behind the head when the head is narrow against the word and steady
            tuck = .2 if (hw < .3 * w1 * s and S['head_top_range'] < .1 * s) else .06
            if WORD_SIZE == 'auto':                                   # ink top must stay under the safe top
                s = min(s, (top - box[1]) / (up1 - tuck))
            base, cx = top + tuck * s, hx
            if s >= 130 or WORD_PLACE != 'auto':
                break
            place = 'left' if S['free_left'] >= S['free_right'] else 'right'
            continue
        if place in ('left', 'right'):
            layer = 'back'
            y0, y1 = int(max(0, top - .2 * hh) / 2), int(min(1918, neck) / 2)
            if place == 'left':
                x0, x1 = box[0], min(left_edge[y0:y1 + 1]) - 26
            else:
                x0, x1 = max(right_edge[y0:y1 + 1]) + 26, box[2]
            s = fit(max(1, x1 - x0), 300)
            cx, base = (x0 + x1) / 2, top + .45 * hh + .5 * up1 * s
            if s >= 90 or WORD_PLACE != 'auto' or 'chest' in tried:
                break
            place = 'chest'
            continue
        layer = 'front'                                              # chest: in front of the speaker, under the chin
        box = allowed(origin, 1300)
        s = fit(box[2] - box[0], 300)
        chest_y = neck + max(30, .12 * hh)
        if WORD_SIZE == 'auto':
            s = min(s, (box[3] - chest_y) / (up1 + dn1))
        low = box[3] - (up1 + dn1) * s                                # lowest the word can sit in the safe zone
        # wide shot: over the lap, well under the face. Closer shot: a third of the way down the chest.
        chest_y = min(chest_y + 1.68 * hh, low) if hh < 300 else chest_y + .35 * max(0, low - chest_y)
        base, cx = chest_y + up1 * s, hx
        break
    if s <= 0:
        sys.exit('no room for the punch word here: another WORD_PLACE, or CAPTIONS=0')
    w, up, dn = ink(text, s)
    box = allowed(origin, base + dn)
    cx = min(max(cx, box[0] + w / 2), box[2] - w / 2)                 # slide sideways into the safe zone
    ib = (cx - w / 2, base - up, cx + w / 2, base + dn)
    msg = []
    if ib[0] < box[0] - 1 or ib[2] > box[2] + 1 or ib[1] < box[1] - 1 or ib[3] > box[3] + 1:
        msg.append('OUTSIDE THE SAFE ZONE (smaller WORD_SIZE or another WORD_PLACE)')
    if layer == 'front' and not (ib[2] < face[0] or ib[0] > face[2] or ib[1] > face[3] or ib[3] < face[1]):
        msg.append('ON THE FACE (move it under the chin or use a back place)')
    if s < 90:
        msg.append('very small: no room for it here, try another place')
    print(f'  "{text}" f{F_PUNCH} {place if isinstance(place, str) else "by hand"} ({layer}) size {s:.0f}  ink box '
          f'x {ib[0]:.0f}..{ib[2]:.0f}  y {ib[1]:.0f}..{ib[3]:.0f}' + ''.join('  !! ' + m for m in msg))
    if any('SAFE' in m or 'FACE' in m for m in msg):
        sys.exit('fix the punch word (WORD STYLE block: WORD_PLACE / WORD_SIZE), or build with CAPTIONS=0')
    return {'text': text, 'layer': layer, 'cx': cx, 'base': base, 'size': s, 'ink': ib}


def word_html(wd):
    """the word as svg text: x / y are its centre and its BASELINE whatever the typeface"""
    s, cx, base = wd['size'], wd['cx'], wd['base']
    glow = WORD_COLOUR if WORD_GLOW == 'auto' else WORD_GLOW
    fx = ((f'drop-shadow(0 0 {.1 * s:.0f}px {glow}73) ' if glow and len(glow) == 7 else
           f'drop-shadow(0 0 {.1 * s:.0f}px {glow}) ' if glow else '') + 'drop-shadow(0 8px 28px rgba(0,0,0,.55))')
    esc = wd['text'].replace('&', '&amp;').replace('<', '&lt;')
    return (f'<div id="pw" class="pw {wd["layer"]}" style="transform-origin:{cx:.1f}px {base - .36 * s:.1f}px">'
            f'<div id="pwb" class="lay"><svg class="lay" width="1080" height="1920" viewBox="0 0 1080 1920" '
            f'style="overflow:visible;filter:{fx}"><text x="{cx:.1f}" y="{base:.1f}" '
            f'text-anchor="middle" font-family="{WORD_FONT}" font-weight="{WORD_WEIGHT}" '
            f'font-style="{"italic" if WORD_ITALIC else "normal"}" font-size="{s:.1f}" '
            # letter-spacing as a css property with a unit: as a bare svg attribute the browser ignores it
            f'style="letter-spacing:{WORD_TRACK * s:.2f}px" fill="{WORD_COLOUR}">{esc}</text></svg></div></div>')


def tweens(wd, n, dur, snap):
    td, dd, tp = F(F_DIM - 1), DIM_FRAMES / FPS, F(F_PUNCH)
    te = F(snap) if snap is not None else dur                         # the hold ends here
    p1, p2 = PUSH + .05 * KICK, PUSH + .015 * KICK                    # kick peak, where it settles
    p3 = p2 + (.01 if PUSH != 1 else 0)                               # slow drift after the kick
    e = "ease:'power2.inOut'"
    tw = [
        f"gsap.set(['#bgv','#subj'],{{filter:'{RAW}'}});",
        "gsap.set(['#subjw','.dimfx','#flash'],{autoAlpha:0});",
        # the cutout comes on over the first 4 frames of the dim, while the room has barely moved (no tick, no pump)
        f"tl.to('#subjw',{{autoAlpha:1,duration:{4 / FPS:.3f},ease:'none'}},{td:.3f});",
        f"tl.to('#bgv',{{filter:'{ROOM}',duration:{dd:.3f},{e}}},{td:.3f});",
        f"tl.to('#subj',{{filter:'{SUBJ}',duration:{dd:.3f},{e}}},{td:.3f});",
        f"tl.to('.dimfx',{{autoAlpha:1,duration:{dd:.3f},{e}}},{td:.3f});",
    ]
    if PUSH != 1:
        tw.append(f"tl.fromTo('#stage',{{scale:1}},{{scale:{PUSH},duration:{tp - td:.3f},ease:'power1.in',immediateRender:false}},{td:.3f});")
    if KICK > 0:
        k = KICK
        tw += [
            f"tl.fromTo('#stage',{{scale:{p1:.4f}}},{{scale:{p2:.4f},duration:.34,ease:'power3.out',immediateRender:false}},{tp:.3f});",
            f"tl.fromTo('#stage',{{x:0,y:0}},{{keyframes:[{{x:{-6 * k:.1f},y:{4 * k:.1f},duration:.033}},{{x:{5 * k:.1f},y:{-4 * k:.1f},duration:.033}},"
            f"{{x:{-3 * k:.1f},y:{2 * k:.1f},duration:.033}},{{x:0,y:0,duration:.033}}],immediateRender:false}},{tp:.3f});",
        ]
    if p3 != p2 and te - tp > .4:
        tw.append(f"tl.to('#stage',{{scale:{p3:.4f},duration:{te - tp - .36:.3f},ease:'none'}},{tp + .35:.3f});")
    if FLASH > 0:
        tw += [f"tl.set('#flash',{{background:'{FLASH_COLOUR}'}},{max(0, tp - .01):.3f});",
               f"tl.fromTo('#flash',{{autoAlpha:{FLASH}}},{{autoAlpha:0,duration:.26,ease:'power2.out',immediateRender:false}},{tp:.3f});"]
    if wd:
        big = 1.9 if wd['layer'] == 'back' else 1.3                   # a word in front must not swell over the face
        tw += ["gsap.set('#pw',{autoAlpha:0});", f"tl.set('#pw',{{autoAlpha:1}},{tp:.3f});",
               # the slam: on screen ON the punch frame, big and soft, exact 6 frames later
               f"tl.fromTo('#pw',{{scale:{big}}},{{scale:1,duration:.2,ease:'expo.out',immediateRender:false}},{tp:.3f});",
               f"tl.fromTo('#pwb',{{filter:'blur(14px)'}},{{filter:'blur(0px)',duration:.2,ease:'expo.out',immediateRender:false}},{tp:.3f});",
               f"tl.to('#pw',{{scale:1.035,duration:{te - tp - .22:.3f},ease:'none'}},{tp + .21:.3f});"]
    if snap is not None:
        end = end_frame(n, snap)
        off = json.dumps(['.dimfx', '#subjw'] + (['#pw'] if wd else []))
        tw += [                                                       # lights on, hard, on the snap frame
            f"tl.set(['#bgv','#subj'],{{filter:'{RAW}'}},{te:.3f});",
            f"tl.set({off},{{autoAlpha:0}},{te:.3f});",
            f"tl.set('#stage',{{x:0,y:0}},{te:.3f});",
        ]
        if SNAP_FLASH > 0:
            tw += [f"tl.set('#flash',{{background:'{SNAP_COLOUR}'}},{te - .01:.3f});",
                   f"tl.fromTo('#flash',{{autoAlpha:{SNAP_FLASH}}},{{autoAlpha:0,duration:.3,ease:'power2.out',immediateRender:false}},{te:.3f});"]
        if p3 != 1:
            tw.append(f"tl.fromTo('#stage',{{scale:{p3:.4f}}},{{scale:1,duration:.34,ease:'power2.out',immediateRender:false}},{te:.3f});")
        tw += [f"tl.set('#stage',{{scale:1,x:0,y:0}},{F(end):.3f});", f"tl.set('#flash',{{autoAlpha:0}},{F(end):.3f});"]
    return tw


def audio(dur, snap):
    if not (SOUNDS and ON['SFX']):
        return []
    hit = 'assets_fx/impact-bass-short.mp3'
    if not os.path.exists(os.path.join(HERE, hit)):
        hit = 'assets/sfx/impact-bass-1.mp3'
    cues = [(hit, F_PUNCH / FPS - .02, .36)]
    if snap is not None:
        cues += [('assets/sfx/click.mp3', snap / FPS - .03, .42), ('assets/sfx/whoosh-short.mp3', snap / FPS, .14)]
    out = []
    for k, (src, t, vol) in enumerate(cues):
        if not os.path.exists(os.path.join(HERE, src)):
            print(f'  sound {src} is not in the slot: left out')
            continue
        d = math.floor(min(probe(src, 'format=duration'), dur - t) * 1000) / 1000
        out.append(f'<audio id="sfx{k}" src="{src}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + k}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    c = clip()
    n = c['frames']
    snap = snap_frame(c)
    validate(n, snap)
    mpath = os.path.join(HERE, 'work/measure.json')
    if not os.path.exists(mpath):
        sys.exit('no work/measure.json: run prep.py first')
    M = json.load(open(mpath))
    if M['stamp'] != stamp(snap) or M['frames'] != n or not M.get('baked'):
        sys.exit('the CLIP block changed since prep.py ran (or it only measured): run prep.py again')
    if F_DIM + DIM_FRAMES > F_PUNCH:
        print(f'  note: the room is still dimming when the punch lands (F_DIM {F_DIM} + {DIM_FRAMES} frames is past '
              f'F_PUNCH {F_PUNCH}): start earlier or shorten DIM_FRAMES')
    dur = math.floor(n / FPS * 1000) / 1000          # rounded up it renders one frame too many
    text = cased(PUNCH.strip())
    wd = place_word(M, text) if (ON['CAPTIONS'] and text) else None
    tw = tweens(wd, n, dur, snap)
    R = M['room']                                    # the speaker over the whole dim (the word has its own numbers)
    hx, top, neck, hh = R['head_x'], R['head_top'], R['neck_y'], R['head_h']
    ox, oy = M['origin']
    k = min(1.7, max(1.0, hh / 210))                 # a closer shot gets a wider clear zone around the speaker
    d = max(0.0, EDGE_DARK)
    floor0 = min(1700.0, neck + 1.9 * hh)            # where the floor darkness starts (under the speaker's body)
    f1 = floor0 + .42 * (1920 - floor0)
    sub = 'assets/subject_lit.webm' if M.get('cutout') == 'cleaned' else 'assets/subject.webm'
    nl = '\n'
    v = f'muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}"'
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#04060C}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#04060C}}
#stage{{position:absolute;inset:0;transform-origin:{ox:.0f}px {oy:.0f}px;{f'filter:{GRADE};' if GRADE else ''}}}
.lay{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.lay video,video.lay{{position:absolute;left:0;top:0;width:1080px;height:1920px;display:block}}
.fx{{position:absolute;inset:0;pointer-events:none}}
#bgv{{z-index:0}}
#hpool{{z-index:1;mix-blend-mode:screen;background:radial-gradient({2.25 * hh:.0f}px {2.25 * hh:.0f}px at {hx:.0f}px {top + .45 * hh:.0f}px,
  rgba(255,222,190,{.18 * min(1, d):.3f}) 0%,rgba(255,214,180,{.06 * min(1, d):.3f}) 45%,rgba(255,214,180,0) 72%)}}
.pw{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
.pw.back{{z-index:3}}
#subjw{{z-index:4}}
.pw.front{{z-index:6}}
#inkbox{{position:absolute;z-index:8;border:2px solid #FFE600}}
/* the speaker is the only thing lit: darkness closes in from the edges and takes the floor */
#hvig{{z-index:7;background:radial-gradient({800 * k:.0f}px {960 * k:.0f}px at {hx:.0f}px {neck:.0f}px,rgba(2,4,10,0) 48%,
  rgba(2,4,10,{min(.9, .24 * d):.3f}) 78%,rgba(2,4,10,{min(.9, .52 * d):.3f}) 100%)}}
#hfloor{{z-index:7;background:linear-gradient(180deg,rgba(2,4,10,0) {floor0:.0f}px,rgba(2,4,10,{min(.9, .22 * d):.3f}) {f1:.0f}px,
  rgba(2,4,10,{min(.9, .5 * d):.3f}) 1920px)}}
#htone{{z-index:7;mix-blend-mode:soft-light;background:linear-gradient(180deg,rgba(40,80,140,{.14 * COOL:.3f}),rgba(10,20,50,{.18 * COOL:.3f}))}}
#flash{{z-index:60}}
'''
    ib = wd['ink'] if wd else None
    inkbox = (f'<div id="inkbox" style="left:{ib[0]:.0f}px;top:{ib[1]:.0f}px;width:{ib[2] - ib[0]:.0f}px;'
              f'height:{ib[3] - ib[1]:.0f}px"></div>') if (SAFE and ib) else ''
    html = f'''<!doctype html>
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
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(dur, snap))}
  <div id="stage">
    <video id="bgv" class="lay" src="assets/aroll.mp4" {v} data-track-index="0"></video>
    <div id="hpool" class="fx dimfx"></div>
{word_html(wd) if wd and wd['layer'] == 'back' else ''}
    <div id="subjw" class="lay"><video id="subj" src="{sub}" {v} data-track-index="1"></video></div>
{word_html(wd) if wd and wd['layer'] == 'front' else ''}
{inkbox}
  </div>
  <div id="hvig" class="fx dimfx"></div><div id="hfloor" class="fx dimfx"></div><div id="htone" class="fx dimfx"></div>
  <div id="flash" class="fx"></div>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open(os.path.join(HERE, 'index.html'), 'w').write(html)
    print(f'wrote index.html  {n} frames ({dur:.3f}s)  room dims f{F_DIM} to f{F_DIM + DIM_FRAMES - 1}, punch f{F_PUNCH}, '
          + (f'lights snap back f{snap}, plain picture again from f{end_frame(n, snap)}' if snap is not None
             else 'stays dim to the last frame (END ON A CUT)')
          + f'  word {"on" if wd else "OFF"}  sounds {"on" if SOUNDS and ON["SFX"] else "OFF"}  safe guide {"ON" if SAFE else "off"}')
    print(f'render to: renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    build()
