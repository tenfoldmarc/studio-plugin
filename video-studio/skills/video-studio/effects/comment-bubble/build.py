#!/usr/bin/env python3
"""comment-bubble (CTA): a comment field slides up under their chin, the keyword types itself on the spoken word, the
send arrow is tapped, the comment posts as a bubble with a creator heart, then a reply bubble lands with a link chip.

Run from the slot folder (see effect.md for the full run order):
    PY measure.py        chin + onsets -> work/measure.json
    PY build.py          writes index.html (SAFE=1 draws the safe zone)
Switches: SAFE=1 safe-zone guide (snapshots only), SFX=0 no sounds, CAPTIONS=0 accepted (this effect has no captions).
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
# -- on-screen text (no em dashes, never "free" / "course", nothing the speaker does not say or imply in the clip)
KEYWORD = 'ADS'                    # the word the speaker asks people to comment, in caps
REPLY_TEXT = 'Sent you the link'   # creator reply; keep it under ~20 characters
CHIP_TEXT = 'Open link'            # label on the yellow link chip; under ~14 characters
USER_NAME = 'you'                  # generic commenter name, never a real person
# -- times in seconds from the slot start. Run measure.py: it prints Whisper's start and the audio onset for every
#    word. Use the audio onset minus one frame (0.03) so the visual leads the voice by a frame.
T_IN = 0.50       # field slides up: about 0.4s before "comment" (on the words leading into it)
T_FOCUS = 0.93    # onset of "comment": field focuses, caret appears
T_TYPE = 1.26     # onset of the keyword minus 0.03: first letter
KEY_GAP = 0.09    # seconds per letter. (keyword end - T_TYPE - 0.1) / (letters - 1), between 0.05 and 0.11
T_SEND = 1.57     # send tap: the end of the keyword (first breath after it)
T_DOTS = 1.88     # onset of the next phrase ("I'll"): creator typing dots. At least 0.15s before T_REPLY
T_REPLY = 2.05    # onset of "send" (the s, not the vowel): reply bubble lands
T_LINK = 2.39     # onset of the thing the speaker sends ("link", "guide"...) minus 0.03: chip resolves
T_OUT = None      # None = thread holds to the last frame (slot ends on a cut). A time = thread leaves and the plate
                  # settles back so the slot's last frame matches the a-roll again (use when the reel keeps the shot)
# -- size and place. Everything is placed from the measured chin (work/measure.json), nothing is a fixed y.
SCALE = 1.3       # thread size, 1.0 = the original demo. Shrinks by itself if the band under the chin is too small
CHIN_Y = None     # None = measured from the cutout (95th percentile while the thread is up). Or a y in frame px:
                  # the lowest the speaker's chin gets in the slot, read off work/measure_check.jpg
CHIN_GAP = 20     # clear px between chin and thread, never less
DROP = 'auto'     # 'auto' = as low as the safe zone allows (bottom edge 1456): on wide shots the speaker's torso and hands stay
                  # visible, on close-ups this equals hugging the chin. A number = px from chin to the thread top
X_CENTER = None   # None = centred under the speaker's head (measured), clamped to the safe zone. Or an x in frame px
PUSH = 'auto'     # 'auto' = lift the plate (scale from the bottom edge) only as much as the thread needs, up to
PUSH_MAX = 1.12   # PUSH_MAX; 1 = never touch the plate (the thread shrinks instead). Close-ups need the lift.
# -- look
AVATAR_FRAME = None   # frame for the creator avatar crop: pick one from work/avatar_check.jpg (eyes open). None = last frame
AVATAR_BOX = None     # (x, y, size) square crop in frame px if the automatic head crop is off. None = measured
GRADE = 'none'        # css filter on the plate. Set it to the reel's own grade so the slot matches its neighbours
SEAT = 1.0            # strength of the soft dark gradient that seats the thread on the footage (0 = off)
# -- style. The buyer's style wins: in a reel, set these from the reel's caption style (SKILL.md "The buyer's style
#    wins", effects/INDEX.md "Restyling an effect's own words"). Each font is (css family, weight, file in
#    assets/fonts): the slot holds every font the caption styles use, assets/fonts/fonts.css lists them.
#    Karaoke, for example: WORD_FONT = TEXT_FONT = ('Archivo', 900, 'Archivo-900-normal.woff2'), UPPER = True.
#    A wider typeface makes the thread wider: build.py shrinks it to the safe zone, lower SCALE if it gets small.
WORD_FONT = ('Inter Tight', 800, 'InterTight-800-normal.woff2')   # the keyword (typed and posted) and the chip label
TEXT_FONT = ('Inter', 600, 'Inter-600-normal.woff2')              # the reply line and the commenter name
UPPER = False         # True = reply line, chip label and name in capitals (the keyword is in capitals already)
ACCENT_COL, LIGHT_COL, DARK_COL = '#FAE67A', '#FFF8EF', '#14161C'   # accent (ring, caret, chip), light (bubble, words), dark (words on light)
# ==== END CLIP ====

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SLOT = os.path.basename(os.getcwd())
CLIPJ = json.load(open('clip.json')) if os.path.exists('clip.json') else {}
if CLIPJ.get('frames'):
    NFRAMES = int(CLIPJ['frames'])
else:
    NFRAMES = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                                  'stream=nb_read_frames', '-of', 'csv=p=0', 'assets/aroll.mp4'], capture_output=True, text=True).stdout.strip())
DUR = NFRAMES / 30
# the renderer makes ceil(duration * 30) frames: 212 frames written as 7.067 came out as 213. Stay a hair under.
DUR_ATTR = f'{NFRAMES / 30 - 0.0004:.4f}'
YEL, CREAM, INK = ACCENT_COL, LIGHT_COL, DARK_COL
WF, WW, TF, TW = WORD_FONT[0], WORD_FONT[1], TEXT_FONT[0], TEXT_FONT[1]
RESTYLED = (WORD_FONT[2], TEXT_FONT[2]) != ('InterTight-800-normal.woff2', 'Inter-600-normal.woff2')


def U(s):
    """the reply, chip and name text as it is shown (capitals when the style asks for them)"""
    return s.upper() if UPPER else s
SAFE_T, SAFE_B, SAFE_L, SAFE_R, SAFE_R_LOW, LOW_Y = 220, 1470, 35, 1045, 980, 1155   # Instagram safe zone
BOTTOM = SAFE_B - 14                     # thread bottom edge when DROP is 'auto'
MARGIN_L = 48
SFX_ON = os.environ.get('SFX', '1') != '0'

# ------------------------------------------------------------------ text widths (exact with PIL, estimated without)
try:
    from PIL import ImageFont
except ImportError:
    ImageFont = None
    print("note: PIL not found, text widths are estimated. Run build.py with the skill's Python (PY) for exact fits.")
FONT_FILES = {('Inter', 500): 'Inter-500-normal.woff2', ('Inter', 600): 'Inter-600-normal.woff2',
              ('Inter Tight', 800): 'InterTight-800-normal.woff2'}
FONT_FILES[(WF, WW)] = WORD_FONT[2]
FONT_FILES[(TF, TW)] = TEXT_FONT[2]
_fonts = {}


def _font(path, px, weight):
    f = ImageFont.truetype(path, px)
    if RESTYLED:               # a font from the buyer's style: measure it at its real weight (the files are variable)
        try:
            f.set_variation_by_axes([weight])
        except (OSError, AttributeError, ValueError):
            pass
    return f


def text_w(txt, family, weight, px, ls=0.0):
    """advance width of txt in design px (ls = css letter-spacing in px)"""
    path = os.path.join('assets', 'fonts', FONT_FILES[(family, weight)])
    if ImageFont and os.path.exists(path):
        try:
            if (path, px) not in _fonts:
                _fonts[(path, px)] = _font(path, px, weight)
            return _fonts[(path, px)].getlength(txt) + ls * len(txt)
        except OSError:
            pass
    em = .66 if txt.isupper() else .52
    return len(txt) * em * px + ls * len(txt)


# ------------------------------------------------------------------ design units (1.0 = the approved demo)
TYPE_PX, KW_PX, WHO_PX, RTXT_PX, CHIP_PX = 62, 70, 33, 42, 37
AV1, AVGAP, R1 = 86, 16, 114            # comment avatar, gap to the bubble, comment row height
BUB_PL, BUB_GAP, BUB_PR = 34, 18, 46    # comment bubble padding / gap between name and keyword
HEART_OUT = 24                          # heart badge overhang right of the bubble
ROW_GAP = 12                            # between comment row and reply row
INDENT, RAV, RB_X = 94, 78, 94          # reply row indent, creator avatar, reply bubble x inside the row
RB_PL, RB_GAP, RB_PR = 38, 24, 20       # reply bubble padding (inline: text + chip on one line)
CHIP_H, CHIP_PL, CHIP_ICON, CHIP_GAP, CHIP_PR = 80, 22, 36, 10, 30
R2_INLINE = 120
ST_PT, ST_LINE, ST_GAP, ST_PB, ST_PR = 20, 52, 12, 22, 38     # stacked reply: text above the chip
R2_STACK = ST_PT + ST_LINE + ST_GAP + CHIP_H + ST_PB
FIELD_H, FIELD_W, FIELD_TEXT_X, SEND = 116, 876, 120, 84


def key_w(ch):
    return round(text_w(ch, WF, WW, TYPE_PX)) + 5      # fixed boxes: the caret position is known without the browser


def widths():
    kw = text_w(KEYWORD, WF, WW, KW_PX, .01 * KW_PX)
    who = text_w(U(USER_NAME), TF, TW, WHO_PX, -.5)
    bub = BUB_PL + who + BUB_GAP + kw + BUB_PR
    rtxt = text_w(U(REPLY_TEXT), TF, TW, RTXT_PX, -.7)
    chip = CHIP_PL + CHIP_ICON + CHIP_GAP + text_w(U(CHIP_TEXT), WF, WW, CHIP_PX, -.2) + CHIP_PR
    typed = sum(key_w(c) for c in KEYWORD)
    return {'bub': bub, 'row1': AV1 + AVGAP + bub + HEART_OUT, 'chip': chip,
            'rb_inline': RB_PL + rtxt + RB_GAP + chip + RB_PR, 'rb_stack': RB_PL + max(rtxt + 8, chip) + ST_PR,
            'field_min': FIELD_TEXT_X + typed + 46 + SEND + 16}


# ------------------------------------------------------------------ measured head / chin
def measured():
    """(chin_y, head_cx, head_w, per-frame list or None) for the frames the thread is on screen"""
    per = None
    if os.path.exists('work/measure.json'):
        per = json.load(open('work/measure.json')).get('frames')
    if per:
        a = max(0, min(len(per) - 1, round(T_IN * 30)))
        win = [p for p in per[a:] if p.get('head_w', 0) > 0] or per
        chins = sorted(p['chin'] for p in win)
        chin = chins[min(len(chins) - 1, int(.95 * len(chins)))]
        cx = sorted(p['cx'] for p in win)[len(win) // 2]
        hw = sorted(p['head_w'] for p in win)[len(win) // 2]
    else:
        chin, cx, hw = None, 540, 0
    if CHIN_Y is not None:
        chin = CHIN_Y
    if chin is None:
        sys.exit('no chin position: run measure.py first (needs assets/subject.webm) or set CHIN_Y in the CLIP block')
    return chin, (X_CENTER if X_CENTER is not None else cx), hw, per


def layout():
    """pick the biggest scale <= SCALE (and inline before stacked reply) that fits between chin and safe line"""
    W = widths()
    chin, cx, head_w, per = measured()
    pmax = PUSH_MAX if PUSH == 'auto' else float(PUSH)
    s = SCALE
    while s >= .6:
        for mode in ('inline', 'stack'):
            r2 = R2_INLINE if mode == 'inline' else R2_STACK
            row2 = INDENT + RB_X + (W['rb_inline'] if mode == 'inline' else W['rb_stack'])
            tw, th = max(W['row1'], row2) * s, (R1 + ROW_GAP + r2) * s
            # where the top goes, and whether the plate has to lift for it
            if DROP == 'auto':          # bottom-anchored: the chin has to be at or above `need`, lift the plate if not
                top = BOTTOM - th
                need = top - CHIN_GAP
                push = 1.0 if chin <= need else (1920 - need) / (1920 - chin)
            else:                       # hung a fixed distance under the chin, plate untouched
                top = chin + max(float(DROP), CHIN_GAP)
                push = 1.0
            chin_eff = 1920 - (1920 - chin) * push
            bottom = top + th
            right = SAFE_R_LOW if bottom > LOW_Y else SAFE_R
            ok = (tw <= right - MARGIN_L and push <= pmax + 1e-6 and top >= chin_eff + CHIN_GAP - .5
                  and bottom <= BOTTOM + .5 and W['field_min'] * s <= right - MARGIN_L)
            if ok:
                x0 = min(max(cx - tw / 2, MARGIN_L), right - tw)
                fw = min(max(tw, W['field_min'] * s, min(FIELD_W * s, 640 * s)), right - MARGIN_L)
                fx = min(max(x0 + tw / 2 - fw / 2, MARGIN_L), right - fw)
                return dict(s=s, mode=mode, r2=r2, x0=x0, y0=top, tw=tw, th=th, push=push, chin=chin, chin_eff=chin_eff,
                            cx=cx, head_w=head_w, right=right, fx=fx, fw=fw, fy=bottom - FIELD_H * s, W=W, per=per)
        s = round(s - .02, 2)
    sys.exit('the thread does not fit under their chin even at 0.6 scale: raise PUSH_MAX, shorten the texts or pick another shot')


# ------------------------------------------------------------------ icons (generic, no platform marks)
def person(size, uid):
    """grey placeholder avatar: head + shoulders (unique ids: a hidden twin would blank the other one)"""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 80 80"><defs><linearGradient id="g{uid}" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#D5D8DF"/><stop offset="1" stop-color="#9097A6"/></linearGradient>'
            f'<clipPath id="c{uid}"><circle cx="40" cy="40" r="40"/></clipPath></defs>'
            f'<g clip-path="url(#c{uid})"><rect width="80" height="80" fill="url(#g{uid})"/>'
            '<circle cx="40" cy="31" r="14" fill="#fff" fill-opacity=".94"/>'
            '<ellipse cx="40" cy="76" rx="27" ry="23" fill="#fff" fill-opacity=".94"/></g></svg>')


def arrow_up(color, size):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M12 19.2V5.2M5.6 11.4L12 5l6.4 6.4"/></svg>')


def heart(size):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24"><path fill="#FF4A6E" d="M12 21.2s-7.6-4.6-9.6-9.5C1 8.1 3 4.6 6.6 4.6c2 0 '
            '3.6 1 5.4 3.1 1.8-2.1 3.4-3.1 5.4-3.1 3.6 0 5.6 3.5 4.2 7.1-2 4.9-9.6 9.5-9.6 9.5z"/></svg>')


def link(size):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{INK}" stroke-width="2.7" stroke-linecap="round" '
            'stroke-linejoin="round" style="flex:none"><path d="M10.2 13.8a4.3 4.3 0 006.1 0l3-3a4.3 4.3 0 00-6.1-6.1l-1.3 1.3"/>'
            '<path d="M13.8 10.2a4.3 4.3 0 00-6.1 0l-3 3a4.3 4.3 0 006.1 6.1l1.3-1.3"/></svg>')


def reply_avatar(L):
    """square crop of their head from the clip -> assets/reply_avatar.jpg. Returns the img html, or a grey avatar."""
    f = AVATAR_FRAME if AVATAR_FRAME is not None else NFRAMES - 1
    f = max(0, min(NFRAMES - 1, int(f)))
    box = AVATAR_BOX
    if box is None and L['per']:
        p = L['per'][min(f, len(L['per']) - 1)]
        if p.get('head_w', 0) > 40:
            side = 1.5 * p['head_w']
            box = (p['cx'] - side / 2, p['top'] - .06 * side, side)
    if box is None:
        return person(round(RAV * L['s']), 'r')
    x, y, side = box
    side = int(min(side, 1080, 1920))
    x, y = int(min(max(0, x), 1080 - side)), int(min(max(0, y), 1920 - side))
    subprocess.run([FF, '-v', 'error', '-y', '-i', 'assets/aroll.mp4', '-vf',
                    f'select=eq(n\\,{f}),crop={side}:{side}:{x}:{y},eq=saturation=0.86:contrast=1.04,scale=240:240:flags=lanczos',
                    '-frames:v', '1', '-q:v', '2', 'assets/reply_avatar.jpg'], check=True)
    return '<img src="assets/reply_avatar.jpg" alt="" />'


# ------------------------------------------------------------------ the effect
def comment_bubble(L):
    """returns (html, tweens, sfx) for the layout L. html sits above the footage, tweens go into the timeline `tl`."""
    s, mode = L['s'], L['mode']
    P = lambda v: round(v * s, 2)                  # design px -> frame px
    J, sfx = [], []
    T = J.append
    x0, y0 = L['x0'], L['y0']
    row2_y = y0 + P(R1 + ROW_GAP)
    rise = L['fy'] - y0                            # the posted bubble starts where the field was
    stack = mode == 'stack'
    rav_top = 20 if stack else (R2_INLINE - RAV) / 2
    dots_top = 24
    av1x = x0 + P(AV1 / 2)                         # comment avatar centre x
    mid2 = row2_y + P(rav_top + RAV / 2)           # creator avatar centre y
    y_a = y0 + P(R1 / 2 + AV1 / 2 + 10)
    rad = P(28)
    elbow = f'M{av1x:.1f} {y_a:.1f} V{mid2 - rad:.1f} Q{av1x:.1f} {mid2:.1f} {av1x + rad:.1f} {mid2:.1f} H{x0 + P(INDENT - 8):.1f}'
    elbow_len = round((mid2 - rad - y_a) + rad * 1.6 + (P(INDENT - 8) - P(AV1 / 2) - rad) + 12)

    keys = ''.join(f'<span id="k{i}" class="k" style="width:{P(key_w(c))}px">{c}</span>' for i, c in enumerate(KEYWORD))
    burst = ''.join(f'<i id="hp{i}" class="hp"></i>' for i in range(6))
    send_cx = L['fw'] - P(16 + SEND / 2)           # send button centre, field-relative
    html = f'''
  <div id="seat"></div>
  <div id="cbui">
    <div id="field" style="left:{L['fx']:.1f}px;top:{L['fy']:.1f}px;width:{L['fw']:.1f}px;height:{P(FIELD_H)}px">
      <div id="fring"></div>
      <div id="fav">{person(P(76), 'f')}</div>
      <div id="ph" style="left:{P(FIELD_TEXT_X + 14)}px">Add a comment...</div>
      <div id="typed" style="left:{P(FIELD_TEXT_X)}px">{keys}</div>
      <div id="caret" style="left:{P(FIELD_TEXT_X - 1)}px"></div>
      <div id="send"><div id="sendoff">{arrow_up('rgba(255,255,255,.55)', P(42))}</div><div id="sendon">{arrow_up(INK, P(42))}</div></div>
      <div id="tapring" style="left:{send_cx:.1f}px;top:{P(FIELD_H / 2)}px"></div>
      <div id="tap" style="left:{send_cx:.1f}px;top:{P(FIELD_H / 2)}px"></div>
    </div>

    <svg id="elbow" width="1080" height="1920" viewBox="0 0 1080 1920"><path id="elbowp" d="{elbow}" fill="none"
      stroke="rgba(255,248,239,.62)" stroke-width="{P(4)}" stroke-linecap="round" stroke-dasharray="{elbow_len}" stroke-dashoffset="{elbow_len}"/></svg>

    <div id="crow" style="left:{x0:.1f}px;top:{y0:.1f}px;height:{P(R1)}px">
      <div id="cav">{person(P(AV1), 'c')}</div>
      <div id="cbub"><span class="who">{USER_NAME}</span><span class="kw">{KEYWORD}</span>
        <div id="heart"><div id="heartin">{heart(P(34))}</div>{burst}</div>
      </div>
    </div>

    <div id="rrow" style="left:{x0 + P(INDENT):.1f}px;top:{row2_y:.1f}px;height:{P(L['r2'])}px">
      <div id="rav" style="top:{P(rav_top)}px">{reply_avatar(L)}</div>
      <div id="dots" style="top:{P(dots_top)}px"><i id="d0"></i><i id="d1"></i><i id="d2"></i></div>
      <div id="rbub" class="{mode}"><span id="rtxt">{REPLY_TEXT}</span>
        <div id="chipwrap"><div id="skel"></div><div id="chipring"></div>
          <div id="chip">{link(P(CHIP_ICON))}<span>{CHIP_TEXT}</span><div id="shine"></div></div></div>
      </div>
    </div>
  </div>'''

    # ---- initial states
    T("gsap.set('#seat',{autoAlpha:0});")
    T(f"gsap.set('#field',{{autoAlpha:0,y:{P(84)},scale:.94,filter:'blur(10px)',transformOrigin:'50% 50%'}});")
    T("gsap.set(['#fav','#send'],{scale:.5,autoAlpha:0});")
    T("gsap.set(['#ph','#fring','#caret','#sendon','#tap','#tapring','#crow','#dots','#rbub','#rtxt','#chip','#chipring','.hp'],{autoAlpha:0});")
    T(f"gsap.set('.k',{{autoAlpha:0,scale:.4,y:{P(14)}}});")
    T(f"gsap.set('#tap',{{xPercent:-50,yPercent:-50,scale:1.25,x:{P(10)},y:{P(18)}}});gsap.set('#tapring',{{xPercent:-50,yPercent:-50}});")
    T(f"gsap.set('#crow',{{y:{rise * .72:.1f},scale:.84,transformOrigin:'12% 50%'}});")
    T("gsap.set('#heart',{scale:0});gsap.set('#heartin',{scale:1.6});")
    T("gsap.set('#rav',{scale:0});gsap.set('#dots',{scale:.4,transformOrigin:'0% 70%'});")
    T(f"gsap.set('#rbub',{{scale:.45,transformOrigin:'0% {'30%' if stack else '62%'}'}});gsap.set('#rtxt',{{x:{P(-16)}}});")
    T("gsap.set('#chip',{scale:.6});gsap.set('#shine',{xPercent:-110});")

    # ---- 1. field slides up
    T(f"tl.to('#seat',{{autoAlpha:1,duration:.6,ease:'power1.out'}},{T_IN:.3f});")
    T(f"tl.to('#field',{{autoAlpha:1,duration:.14,ease:'power1.out'}},{T_IN:.3f});")
    T(f"tl.to('#field',{{y:0,scale:1,filter:'blur(0px)',duration:.56,ease:'expo.out'}},{T_IN:.3f});")
    T(f"tl.to('#fav',{{scale:1,autoAlpha:1,duration:.34,ease:'back.out(2)'}},{T_IN + .10:.3f});")
    T(f"tl.to('#ph',{{autoAlpha:1,duration:.2,ease:'power1.out'}},{T_IN + .14:.3f});")
    T(f"tl.to('#send',{{scale:1,autoAlpha:1,duration:.34,ease:'back.out(2)'}},{T_IN + .17:.3f});")

    # ---- 2. "comment": focus ring + caret
    T(f"tl.to('#fring',{{autoAlpha:1,duration:.2,ease:'power2.out'}},{T_FOCUS:.3f});")
    T(f"tl.to('#ph',{{autoAlpha:.55,duration:.2}},{T_FOCUS:.3f});")
    T(f"tl.set('#caret',{{autoAlpha:1}},{T_FOCUS:.3f});")
    if T_TYPE - T_FOCUS > .32:   # one blink while the speaker finishes the word
        T(f"tl.set('#caret',{{autoAlpha:0}},{T_FOCUS + .15:.3f});tl.set('#caret',{{autoAlpha:1}},{T_FOCUS + .25:.3f});")

    # ---- 3. keyword types itself, one key per tick
    cum = 0
    for i, c in enumerate(KEYWORD):
        t = T_TYPE + i * KEY_GAP
        cum += key_w(c)
        if i == 0:
            T(f"tl.set('#ph',{{autoAlpha:0}},{t:.3f});")
            T(f"tl.to('#sendon',{{autoAlpha:1,duration:.12}},{t:.3f});")
            T(f"tl.to('#send',{{scale:1.16,duration:.09,ease:'power2.out'}},{t:.3f});")
            T(f"tl.to('#send',{{scale:1,duration:{max(.05, min(.22, T_SEND - t - .1)):.3f},ease:'back.out(2.4)'}},{t + .093:.3f});")
        T(f"tl.to('#k{i}',{{autoAlpha:1,scale:1,y:0,duration:.16,ease:'back.out(2.6)'}},{t:.3f});")
        T(f"tl.set('#caret',{{x:{P(cum + 4)}}},{t:.3f});")
        bump = min(.034, KEY_GAP * .38)
        if t >= T_IN + .57:      # the field's own entrance still owns its scale before that
            T(f"tl.to('#field',{{scale:1.014,duration:{bump:.3f},ease:'power1.out'}},{t:.3f});")
            T(f"tl.to('#field',{{scale:1,duration:{bump * 1.3:.3f},ease:'power1.inOut'}},{t + bump + .001:.3f});")
        sfx.append(('click-soft', t, .60))

    # ---- 4. send arrow tapped (back-to-back tweens of one property leave a 6 ms gap: lint flags float-equal ends)
    T(f"tl.to('#tap',{{autoAlpha:1,scale:1,x:0,y:0,duration:.12,ease:'power3.out'}},{T_SEND - .13:.3f});")
    T(f"tl.to('#tap',{{scale:.8,duration:.044,ease:'power2.in'}},{T_SEND:.3f});")
    T(f"tl.to('#tap',{{autoAlpha:0,scale:1.2,duration:.16,ease:'power2.out'}},{T_SEND + .05:.3f});")
    T(f"tl.to('#send',{{scale:.82,duration:.044,ease:'power2.in'}},{T_SEND:.3f});")
    T(f"tl.to('#send',{{scale:1,duration:.16,ease:'back.out(3)'}},{T_SEND + .05:.3f});")
    T(f"tl.set('#tapring',{{autoAlpha:.9,scale:1}},{T_SEND + .03:.3f});")
    T(f"tl.to('#tapring',{{autoAlpha:0,scale:1.7,duration:.3,ease:'power2.out'}},{T_SEND + .03:.3f});")
    T(f"tl.set('#caret',{{autoAlpha:0}},{T_SEND:.3f});")
    sfx.append(('click', T_SEND, .70))

    # ---- 5. the comment posts: the dark field lets go, the cream bubble jumps up out of it
    tp = T_SEND + .07
    # (field is gone before the bubble is solid, otherwise the keyword reads twice for a frame)
    T(f"tl.to('#field',{{y:{P(16)},scale:.96,autoAlpha:0,filter:'blur(8px)',duration:.12,ease:'power2.in'}},{tp:.3f});")
    T(f"tl.set('#field',{{autoAlpha:0}},{tp + .125:.3f});")
    T(f"tl.set(['#typed','#fav'],{{autoAlpha:0}},{tp + .07:.3f});")
    T(f"tl.to('#crow',{{autoAlpha:1,duration:.07,ease:'none'}},{tp + .07:.3f});")
    T(f"tl.to('#crow',{{y:0,scale:1,duration:.46,ease:'back.out(1.6)'}},{tp + .07:.3f});")
    sfx.append(('pop', tp + .06, .20))
    th = tp + .19                                   # creator heart on the bubble
    T(f"tl.to('#heart',{{scale:1,duration:.34,ease:'back.out(3.2)'}},{th:.3f});")
    T(f"tl.to('#heartin',{{scale:1,duration:.4,ease:'back.out(2.2)'}},{th + .02:.3f});")
    for i in range(6):
        a = math.radians(i * 60 - 80)
        T(f"tl.fromTo('#hp{i}',{{x:0,y:0,scale:1,autoAlpha:1}},{{x:{P(46) * math.cos(a):.1f},y:{P(46) * math.sin(a):.1f},scale:.2,"
          f"autoAlpha:0,duration:.44,ease:'power2.out',immediateRender:false}},{th + .05:.3f});")

    # ---- 6. next phrase: creator is typing
    # (the thread line is drawn in frame space: wait until the comment row has finished rising or it floats above it)
    T(f"tl.to('#elbowp',{{strokeDashoffset:0,duration:.22,ease:'power2.out'}},{max(T_DOTS - .08, tp + .07 + .17):.3f});")
    T(f"tl.to('#rav',{{scale:1,duration:.32,ease:'back.out(2.2)'}},{T_DOTS:.3f});")
    # (the intro must END before the hide below: a running tl.to(autoAlpha:1) beats a tl.set(autoAlpha:0))
    T(f"tl.to('#dots',{{autoAlpha:1,scale:1,duration:{max(.04, min(.2, T_REPLY - T_DOTS - .05)):.3f},ease:'back.out(2)'}},{T_DOTS + .03:.3f});")
    for j in range(3):
        for rep in range(max(1, int((T_REPLY - T_DOTS - .1) / .42) + 1)):
            T(f"tl.to('#d{j}',{{y:{P(-10)},duration:.09,ease:'power2.out',yoyo:true,repeat:1}},{T_DOTS + .07 + j * .05 + rep * .42:.3f});")

    # ---- 7. "send": reply bubble lands
    T(f"tl.set('#dots',{{autoAlpha:0}},{T_REPLY:.3f});")
    T(f"tl.to('#rbub',{{autoAlpha:1,duration:.04,ease:'none'}},{T_REPLY:.3f});")
    T(f"tl.to('#rbub',{{scale:1,duration:.4,ease:'back.out(1.7)'}},{T_REPLY:.3f});")
    T(f"tl.to('#rtxt',{{autoAlpha:1,duration:.1,ease:'none'}},{T_REPLY + .03:.3f});")
    T(f"tl.to('#rtxt',{{x:0,duration:.3,ease:'power3.out'}},{T_REPLY + .03:.3f});")
    for rep in range(max(1, int((T_LINK - T_REPLY - .1) / .34))):     # the empty chip breathes until the link lands
        T(f"tl.to('#skel',{{backgroundColor:'rgba(255,255,255,.24)',duration:.14,ease:'sine.inOut',yoyo:true,repeat:1}},{T_REPLY + .1 + rep * .34:.3f});")
    sfx.append(('whoosh-short', T_REPLY + .04, .20))

    # ---- 8. the thing the speaker sends: the chip resolves
    T(f"tl.to('#chip',{{autoAlpha:1,duration:.06,ease:'none'}},{T_LINK:.3f});")
    T(f"tl.to('#chip',{{scale:1,duration:.4,ease:'back.out(2.4)'}},{T_LINK:.3f});")
    T(f"tl.set('#skel',{{visibility:'hidden'}},{T_LINK + .1:.3f});")
    end = T_OUT if T_OUT is not None else DUR
    shine = min(.55, end - (T_LINK + .14) - .08)     # the sweep must be over before the thread ends: a slot that stops
    if shine >= .2:                                  # soon after the chip would freeze a white band on its last frame
        T(f"tl.to('#shine',{{xPercent:110,duration:{shine:.3f},ease:'power2.inOut'}},{T_LINK + .14:.3f});")
    tpulse = T_LINK + .5
    k = 0
    while tpulse + .62 < end and k < 3:              # a "tap me" pulse, repeated while the thread holds
        T(f"tl.set('#chipring',{{autoAlpha:.85,scaleX:1,scaleY:1}},{tpulse:.3f});")
        T(f"tl.to('#chipring',{{autoAlpha:0,scaleX:1.14,scaleY:1.42,duration:.6,ease:'power2.out'}},{tpulse:.3f});")
        T(f"tl.to('#chip',{{scale:1.05,duration:.14,ease:'power2.out'}},{tpulse:.3f});")
        T(f"tl.to('#chip',{{scale:1,duration:.36,ease:'back.out(2)'}},{tpulse + .145:.3f});")
        tpulse += 1.1
        k += 1

    # ---- 9. optional exit, so the slot hands back to the a-roll cleanly
    if T_OUT is not None:
        T(f"tl.to(['#crow','#rrow','#elbow'],{{autoAlpha:0,y:{P(18)},filter:'blur(6px)',duration:.22,ease:'power2.in'}},{T_OUT:.3f});")
        T(f"tl.to('#seat',{{autoAlpha:0,duration:.3,ease:'power1.in'}},{T_OUT:.3f});")
    return html, J, sfx


def plate(L):
    """the footage lifts as the field opens (scale from the bottom edge) only when the thread needs the room"""
    tw = [f"gsap.set('#bgv',{{filter:'{GRADE}'}});"] if GRADE and GRADE != 'none' else []
    p = L['push']
    if p <= 1.001:
        return tw
    a = max(0, T_IN - .08)
    tw.append(f"tl.to('#stage',{{scale:{p:.4f},duration:.9,ease:'power3.inOut'}},{a:.3f});")
    if T_OUT is None:
        tw.append(f"tl.to('#stage',{{scale:{p + .022:.4f},duration:{max(.1, DUR - a - .9):.3f},ease:'sine.out'}},{a + .9:.3f});")
    else:
        d = max(.2, min(.6, DUR - T_OUT - .02))
        tw.append(f"tl.to('#stage',{{scale:1,duration:{d:.3f},ease:'power3.inOut'}},{max(a + .92, T_OUT + .04):.3f});")
    return tw


SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'sparkle': 1.8, 'click': .3, 'click-soft': .36}
SFX_LEAD = {'whoosh-short': .118, 'pop': .117, 'sparkle': 0, 'click': .048, 'click-soft': .048}   # silence before the transient
SFX_GAIN = 0.75   # house level: all sounds 25% under the template base


def audio(sfx):
    out, lanes = [], []
    timed = sorted(((name, max(0, t - SFX_LEAD[name]), vol) for name, t, vol in sfx), key=lambda x: x[1])   # transient ON the beat
    for k, (name, t, vol) in enumerate(timed):
        d = min(SFX_LEN[name], DUR - t)
        if d <= .03:
            continue
        lane = next((i for i, e in enumerate(lanes) if e <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


BASE_CSS = '''
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:#000}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}
#stage{position:absolute;inset:0;transform-origin:50% 100%}
.full{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
#cbui{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:10}
#elbow{position:absolute;left:0;top:0}
'''

# design px: every px value below is multiplied by the layout scale (see scale_css)
UI_CSS = '''
/* ---- comment field */
#field{position:absolute;border-radius:58px;background:rgba(22,24,31,.96);
  box-shadow:0 30px 70px rgba(0,0,0,.52),0 6px 18px rgba(0,0,0,.32),inset 0 0 0 2px rgba(255,255,255,.15),inset 0 3px 0 rgba(255,255,255,.07)}
#fring{position:absolute;left:-3px;top:-3px;right:-3px;bottom:-3px;border-radius:61px;border:3px solid __YEL__;box-shadow:0 0 36px rgba(250,230,122,.30),inset 0 0 18px rgba(250,230,122,.10)}
#fav{position:absolute;left:20px;top:20px;width:76px;height:76px;border-radius:50%;overflow:hidden}
#fav svg,#cav svg,#rav svg{display:block}
#ph{position:absolute;top:0;height:116px;font:__PW__ 40px '__TF__';line-height:116px;color:rgba(255,248,239,.5);letter-spacing:-.6px;white-space:nowrap__UP__}
#typed{position:absolute;top:0;height:116px;display:flex;align-items:center}
.k{display:inline-block;text-align:center;font:__WW__ 62px '__WF__';line-height:116px;color:__CREAM__;transform-origin:50% 70%}
#caret{position:absolute;top:30px;width:5px;height:56px;border-radius:3px;background:__YEL__;box-shadow:0 0 14px rgba(250,230,122,.55)}
#send{position:absolute;right:16px;top:16px;width:84px;height:84px}
#sendoff,#sendon{position:absolute;left:0;top:0;width:84px;height:84px;border-radius:50%;display:flex;align-items:center;justify-content:center}
#sendoff{background:rgba(255,255,255,.11)}
#sendon{background:__YEL__;box-shadow:0 8px 26px rgba(250,230,122,.38)}
#tap{position:absolute;width:118px;height:118px;border-radius:50%;background:rgba(255,255,255,.46);border:3px solid rgba(255,255,255,.92);
  box-shadow:0 10px 28px rgba(0,0,0,.38),inset 0 0 22px rgba(255,255,255,.35)}
#tapring{position:absolute;width:84px;height:84px;border-radius:50%;border:4px solid __YEL__}

/* ---- posted comment */
#crow{position:absolute;display:flex;align-items:center;gap:16px}
#cav{width:86px;height:86px;border-radius:50%;overflow:hidden;flex:none;box-shadow:0 10px 26px rgba(0,0,0,.35)}
#cbub{position:relative;height:114px;padding:0 46px 0 34px;display:flex;align-items:center;gap:18px;background:__CREAM__;white-space:nowrap;
  border-radius:57px 57px 57px 16px;box-shadow:0 30px 70px rgba(0,0,0,.46),0 6px 18px rgba(0,0,0,.26),inset 0 -3px 0 rgba(20,22,28,.05)}
.who{font:__TW__ 33px '__TF__';color:rgba(20,22,28,.46);letter-spacing:-.5px;padding-top:6px__UP__}
.kw{font:__WW__ 70px '__WF__';color:__INK__;letter-spacing:.7px;line-height:114px}
#heart{position:absolute;right:-24px;top:-22px;width:60px;height:60px;border-radius:50%;background:#fff;display:flex;align-items:center;
  justify-content:center;box-shadow:0 10px 24px rgba(0,0,0,.30),0 2px 6px rgba(0,0,0,.18)}
#heartin{display:flex;padding-top:2px}
.hp{position:absolute;left:25px;top:25px;width:10px;height:10px;border-radius:50%;background:#FF4A6E}
.hp:nth-of-type(even){background:__YEL__;width:8px;height:8px}

/* ---- creator reply */
#rrow{position:absolute}
#rav{position:absolute;left:0;width:78px;height:78px;border-radius:50%;overflow:hidden;border:3px solid __YEL__;background:#222;
  box-shadow:0 10px 26px rgba(0,0,0,.4)}
#rav img{width:100%;height:100%;object-fit:cover;display:block}
#dots{position:absolute;left:94px;width:130px;height:72px;border-radius:36px 36px 36px 12px;background:rgba(20,22,28,.95);
  display:flex;align-items:center;justify-content:center;gap:11px;box-shadow:0 18px 44px rgba(0,0,0,.45),inset 0 0 0 2px rgba(255,255,255,.16)}
#dots i{width:14px;height:14px;border-radius:50%;background:rgba(255,248,239,.85)}
#rbub{position:absolute;left:94px;top:0;display:flex;white-space:nowrap;background:rgba(24,27,34,.97);
  box-shadow:0 30px 70px rgba(0,0,0,.55),0 6px 18px rgba(0,0,0,.34),inset 0 0 0 2px rgba(255,255,255,.16),inset 0 3px 0 rgba(255,255,255,.08)}
#rbub.inline{height:120px;padding:0 20px 0 38px;align-items:center;gap:24px;border-radius:60px 60px 60px 16px}
#rbub.stack{height:186px;padding:20px 38px 22px 38px;flex-direction:column;align-items:flex-start;gap:12px;border-radius:52px 52px 52px 16px}
#rtxt{font:__TW__ 42px '__TF__';color:__CREAM__;letter-spacing:-.7px;line-height:52px__UP__}
#rbub.stack #rtxt{padding-left:8px}
#chipwrap{position:relative;height:80px;flex:none}
#skel{position:absolute;left:0;top:0;width:100%;height:80px;border-radius:40px;background:rgba(255,255,255,.10);box-shadow:inset 0 0 0 2px rgba(255,255,255,.08)}
#chipring{position:absolute;left:0;top:0;width:100%;height:80px;border-radius:40px;border:3px solid __YEL__}
#chip{position:relative;height:80px;padding:0 30px 0 22px;border-radius:40px;background:__YEL__;display:flex;align-items:center;gap:10px;
  overflow:hidden;box-shadow:0 10px 30px rgba(250,230,122,.30)}
#chip span{font:__WW__ 37px '__WF__';color:__INK__;letter-spacing:-.2px__UP__}
#shine{position:absolute;left:0;top:0;width:100%;height:100%;background:linear-gradient(105deg,rgba(255,255,255,0) 36%,rgba(255,255,255,.85) 50%,rgba(255,255,255,0) 64%)}
'''.replace('__YEL__', YEL).replace('__CREAM__', CREAM).replace('__INK__', INK)
# typeface, weight and case come from the style lines of the CLIP block (the placeholder keeps its light weight in
# the default look and takes the text weight when the fonts were changed)
UI_CSS = (UI_CSS.replace('__WF__', WF).replace('__WW__', str(WW)).replace('__TF__', TF).replace('__TW__', str(TW))
          .replace('__PW__', str(TW if RESTYLED else 500)).replace('__UP__', ';text-transform:uppercase' if UPPER else ''))


def scale_css(css, s):
    """multiply every px length in the UI css by the layout scale (fonts, radii, paddings, shadows)"""
    return re.sub(r'(-?\d*\.?\d+)px', lambda m: f'{float(m.group(1)) * s:.2f}px', css)


def seat_css(L):
    a = max(0, L['y0'] - 230)
    k = max(0.0, min(1.5, SEAT))
    return ('#seat{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:5;pointer-events:none;'
            f'background:linear-gradient(180deg,rgba(8,9,12,0) {a:.0f}px,rgba(8,9,12,{.30 * k:.3f}) {L["y0"] + 60:.0f}px,'
            f'rgba(8,9,12,{.44 * k:.3f}) {min(1900, L["y0"] + L["th"] + 60):.0f}px,rgba(8,9,12,{.50 * k:.3f}) 1920px)}}')


# SAFE=1: Instagram safe zone in red + the chin line the layout used in cyan (snapshots only, never render this)
def safe_guide(L):
    return ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
            '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
            '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
            '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
            '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
            '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div>'
            f'<div style="position:absolute;left:0;right:0;top:{L["chin_eff"]:.0f}px;height:3px;background:rgba(0,255,255,.9)"></div></div>')


def sanity(L):
    last_key = T_TYPE + (len(KEYWORD) - 1) * KEY_GAP
    msgs = []
    if not (T_IN < T_FOCUS <= T_TYPE < T_SEND < T_DOTS < T_REPLY < T_LINK < DUR):
        msgs.append('times must run T_IN < T_FOCUS <= T_TYPE < T_SEND < T_DOTS < T_REPLY < T_LINK < slot end')
    if last_key > T_SEND - .06:
        msgs.append(f'the last letter lands at {last_key:.2f}, after the send tap ({T_SEND}): lower KEY_GAP or move T_SEND')
    if T_OUT is not None and not (T_LINK + .6 <= T_OUT <= DUR - .25):
        msgs.append('T_OUT must leave 0.6s after T_LINK and 0.25s before the slot ends')
    if DUR - T_LINK < 1.0:
        msgs.append(f'only {DUR - T_LINK:.2f}s of footage after the chip lands: give the slot at least 1.5s after T_LINK')
    if L['s'] < SCALE - .001:
        msgs.append(f'scale reduced to {L["s"]:.2f} (asked {SCALE}): the band under their chin is {BOTTOM - L["chin_eff"]:.0f}px even after the lift')
    if L['push'] > 1.001 and T_OUT is None:
        msgs.append(f'plate is lifted x{L["push"]:.3f} and stays lifted on the last frame: end the slot on a cut, or set T_OUT')
    for m in msgs:
        print('  ! ' + m)


def build():
    L = layout()
    html, tweens, sfx = comment_bubble(L)
    tweens = plate(L) + tweens
    nl = '\n'
    css = BASE_CSS + seat_css(L) + scale_css(UI_CSS, L['s'])
    doc = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR_ATTR}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR_ATTR}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio(sfx)) if SFX_ON else ''}
  <div id="stage">
    <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR_ATTR}" data-track-index="0"></video>
  </div>
{html}
{safe_guide(L) if os.environ.get('SAFE') else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(tweens)}
tl.set({{}}, {{}}, {DUR_ATTR});
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(doc)
    os.makedirs('work', exist_ok=True)
    json.dump({'frames': NFRAMES, 'scale': L['s'], 'mode': L['mode'], 'push': round(L['push'], 4), 'chin': L['chin'],
               'chin_eff': round(L['chin_eff'], 1), 'x0': round(L['x0'], 1), 'y0': round(L['y0'], 1), 'tw': round(L['tw'], 1),
               'th': round(L['th'], 1), 'field': [round(L['fx'], 1), round(L['fy'], 1), round(L['fw'], 1)],
               'beats': {'T_IN': T_IN, 'T_FOCUS': T_FOCUS, 'T_TYPE': T_TYPE, 'last_key': T_TYPE + (len(KEYWORD) - 1) * KEY_GAP,
                         'T_SEND': T_SEND, 'T_DOTS': T_DOTS, 'T_REPLY': T_REPLY, 'T_LINK': T_LINK, 'T_OUT': T_OUT}},
              open('work/layout.json', 'w'), indent=1)      # check.py reads this
    print(f'wrote index.html  {NFRAMES} frames ({DUR:.2f}s)  safe guide {"ON (do not render)" if os.environ.get("SAFE") else "off"}  sfx {"on" if SFX_ON else "off"}')
    print(f'layout: scale {L["s"]:.2f}  reply {L["mode"]}  thread x {L["x0"]:.0f}..{L["x0"] + L["tw"]:.0f}  y {L["y0"]:.0f}..{L["y0"] + L["th"]:.0f}'
          f'  chin {L["chin"]:.0f}' + (f' -> {L["chin_eff"]:.0f} after x{L["push"]:.3f} lift' if L['push'] > 1.001 else '  (plate untouched)'))
    sanity(L)
    print(f'render: npx --yes hyperframes@0.8.34 render -o renders/{SLOT}.mp4 --quality high')


build()
