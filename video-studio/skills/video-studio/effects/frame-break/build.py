#!/usr/bin/env python3
"""frame-break (hook): the whole video shrinks into a floating card that looks like a phone post, over a blurred
copy of the room. The picture is clipped to the card, the speaker's cutout is not, and both sit in the same moving
rig, so the head rises over the card's top edge and reaching hands pass its sides while staying locked to the body.

Run from the slot folder, after prep.py (see effect.md for the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no text on the card, SFX=0 no sounds)
Where the card sits, how big it is and what comes out of it are measured by prep.py (work/measure.json).
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
F_IN = 45          # frame the card has LANDED: onset of the word it lands on ("onset" column of onsets.py). 23 or later
F_OUT = None       # frame the picture is full frame again: onset of a later word, 45+ frames after F_IN, 2+ before the
                   # last frame. None = the card stays to the last frame and the reel must CUT there
HEAD_OUT = 'auto'  # how much of the head stands above the card's top edge, in head heights: 0.3 = hair and forehead,
                   # 1.0 = whole head, 1.5 = head and shoulders. 'auto' = 0.3 on a medium shot, up to 1.0 on a wide one
CARD = None        # None = measured: a 9:16 card under the head, down to the bottom of the frame. Or (x, y, w, h) in
                   # a-roll px, read off work/check.jpg (it is drawn at 1/3 size, so multiply by 3)
SCALE = 'auto'     # card size on screen. 'auto' = as big as the safe zone allows. A number (0.5 to 1.1) makes it smaller
HEAD = None        # None = head measured from the cutout. (top_y, chin_y) in a-roll px when the green box on
                   # work/check.jpg is not on the head
SIDE_POP = True    # True = hands that pass the card's side edges come out too. False = only what is above the top edge
ICONS = True       # like / comment / share icons down the card's right edge. Icons only: the card never shows counts
NAME = ''          # the user's OWN handle, bottom left of the card. '' = no name row. Ask for it, never make one up
CARD_LINE = ''     # one short line under the name, in the user's own words. '' = none
FOLLOW_AT = None   # frame of the word "follow": a Follow button beside NAME gets tapped then. Needs NAME. None = off
COMMENT = None     # ('WORD', frame): the keyword the speaker asks people to comment pops out of the comment icon on that frame
LIKE_AT = None     # frame the heart fills in (a word worth a like). None = off
TILT = 1.0         # 3D tilt and drift of the floating card. 0 = flat and still, 1 = as designed
GRADE = ''         # '' = off, the slot hands back plain footage. A css filter only if the whole reel carries the same one
SOUNDS = True      # whoosh on the shrink and on the way back, soft click on the follow tap, pop on the comment
# ==== END CLIP ====

SHRINK, GROW = 21, 16      # frames the shrink and the grow-back take (prep.py uses the same numbers)
PUSH = 1.03                # slow push-in while the card floats (prep.py uses the same number)
SFX_GAIN = 0.75
SFX_LEN = {'whoosh-short': .57, 'pop': .72, 'click-soft': .37}

clip = json.load(open('clip.json'))
N = clip['frames']
DUR = N / 30
if not os.path.exists('work/measure.json'):
    sys.exit('no work/measure.json: run prep.py first')
m = json.load(open('work/measure.json'))
if (m['f_in'], m['f_out'], m['N']) != (F_IN, F_OUT, N):
    sys.exit('F_IN / F_OUT changed since prep.py ran: run prep.py again (it re-measures what leaves the card)')
for need in ('assets/subject_fade.webm', 'assets/backdrop.mp4'):
    if not os.path.exists(need):
        sys.exit(f'no {need}: run prep.py without "measure"')
RX, RY, RW, RH = m['card']
S, SCR_TOP = m['scale'], m['scr_top']
UK = RW / 800                               # card dressing is drawn for an 800 px wide card and scaled to this one
UH = RH / UK
RAD = 60 * UK
OX, OY = RX + RW / 2, RY + RH / 2           # rig transform origin = card centre
TX, TY = 540 - OX, SCR_TOP + RH * S / 2 - OY
A = (F_IN - SHRINK) / 30                    # shrink starts
L = F_IN / 30                               # card has landed
O = (F_OUT - GROW) / 30 if F_OUT is not None else DUR      # grow-back starts
E = F_OUT / 30 if F_OUT is not None else DUR
CAPS = os.environ.get('CAPTIONS') != '0'
NAME = NAME.strip().lstrip('@')
LINE = CARD_LINE.strip() if CAPS else ''
WORD = (COMMENT[0].strip(), COMMENT[1] / 30) if COMMENT and CAPS else None
TAP = FOLLOW_AT / 30 if FOLLOW_AT is not None and NAME else None
LIKE = LIKE_AT / 30 if LIKE_AT is not None and ICONS else None
if FOLLOW_AT is not None and not NAME:
    print('  (FOLLOW_AT is set but NAME is empty: no Follow button drawn)')

ICON = {
    'heart': '<path d="M12 20.6s-7.3-4.4-9.3-8.9C1.2 8.3 3.1 4.6 6.7 4.2c2.1-.2 3.9.9 5.3 2.8 1.4-1.9 3.2-3 5.3-2.8 3.6.4 5.5 4.1 4 7.5-2 4.5-9.3 8.9-9.3 8.9z"/>',
    'comment': '<path d="M20.66 17.01a9.99 9.99 0 1 0-3.59 3.62L22 22z"/>',
    'send': '<path d="M22 3 9.22 10.08"/><path d="M11.7 20.33 22 3H2l7.22 7.08z"/>',
}


def svg(name):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round" '
            f'stroke-linecap="round">{ICON[name]}</svg>')


def ui_html():
    parts = []
    if ICONS:
        dots = '<svg viewBox="0 0 24 24" fill="#fff"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>'
        fill = '<svg viewBox="0 0 24 24" fill="#ff3040" stroke="#ff3040" stroke-width="2" stroke-linejoin="round">' + ICON['heart'] + '</svg>'
        bub = f'<div id="cbub"><div class="bword">{html.escape(WORD[0])}</div></div>' if WORD else ''
        parts.append(f'''<div id="col">
        <div class="ic"><div class="glyph">{svg('heart')}<div id="hfill">{fill}</div></div></div>
        <div class="ic"><div class="glyph" id="cglyph">{svg('comment')}</div>{bub}</div>
        <div class="ic"><div class="glyph">{svg('send')}</div></div>
        <div class="ic"><div class="glyph dots">{dots}</div></div>
      </div>''')
    if NAME:
        pill = ('<div id="pill"><span id="pf">Follow</span><span id="pg">Following</span><div id="ring"></div>'
                '<div id="tap"></div></div>') if TAP is not None else ''
        parts.append(f'<div id="who"><div id="av">{html.escape(NAME[0].upper())}</div>'
                     f'<div id="handle">{html.escape(NAME)}</div>{pill}</div>')
    if LINE:
        parts.append(f'<div id="cap">{html.escape(LINE)}</div>')
    parts.append('<div id="bar"><div id="barfill"></div></div>')
    return '<div id="ui">\n      ' + '\n      '.join(parts) + '\n    </div>'


def tweens():
    tw = []
    clip0 = 'inset(0px 0px 0px 0px round 0px)'
    clip1 = f'inset({RY}px {1080 - RX - RW}px {1920 - RY - RH}px {RX}px round {RAD:.1f}px)'
    full = f'scaleX:{1080 / RW:.4f},scaleY:{1920 / RH:.4f},x:{540 - OX:.1f},y:{960 - OY:.1f},borderRadius:0'
    ind = L - A
    tw += [f"gsap.set('#rig',{{transformOrigin:'{OX}px {OY}px',transformPerspective:2200,x:0,y:0,scale:1,rotationX:0,rotationY:0}});",
           f"gsap.set('#plate',{{clipPath:'{clip0}'}});",
           # shadow + rim live at the card rect; at full frame they are scaled up to cover the whole video
           f"gsap.set(['#shad','#rim'],{{transformOrigin:'50% 50%',{full}}});",
           "gsap.set(['#shadw','#rimw','#cutw'],{autoAlpha:0});",
           f"tl.set('#cutw',{{autoAlpha:1}},{A:.3f});",
           # the shrink: the window closes to the card while the rig scales down; the cutout is never clipped
           f"tl.to('#plate',{{clipPath:'{clip1}',duration:{ind - .06:.3f},ease:'power3.inOut'}},{A:.3f});",
           f"tl.to(['#shad','#rim'],{{scaleX:1,scaleY:1,x:0,y:0,borderRadius:{RAD:.1f},duration:{ind - .06:.3f},ease:'power3.inOut'}},{A:.3f});",
           f"tl.to('#shadw',{{autoAlpha:1,duration:.4,ease:'power2.out'}},{A + .1:.3f});",
           f"tl.to('#rimw',{{autoAlpha:1,duration:.3,ease:'power2.out'}},{A + .35:.3f});",
           f"tl.to('#rig',{{scale:{S:.4f},x:{TX:.1f},y:{TY:.1f},duration:{ind - .02:.3f},ease:'expo.inOut'}},{A + .02:.3f});",
           f"tl.fromTo('#bdrop',{{scale:1.08}},{{scale:1.0,duration:{max(.1, O - A):.3f},ease:'sine.out',immediateRender:false}},{A:.3f});"]
    if TILT:
        tw += [f"tl.to('#rig',{{rotationY:{-9 * TILT:.2f},rotationX:{6 * TILT:.2f},duration:{ind + .25:.3f},ease:'power3.inOut'}},{A + .05:.3f});"]
        if O - (L + .3) > .15:      # slow drift while the card floats
            tw += [f"tl.to('#rig',{{rotationY:{7 * TILT:.2f},rotationX:{2.5 * TILT:.2f},duration:{O - L - .34:.3f},ease:'sine.inOut'}},{L + .32:.3f});"]
    if O - (L + .5) > .15:
        tw += [f"tl.to('#rig',{{scale:{S * PUSH:.4f},duration:{O - L - .52:.3f},ease:'sine.inOut'}},{L + .5:.3f});"]
    # card dressing staggers in as the card lands
    tw += ["gsap.set(['#col .ic','#who','#cap','#bar','#gradb'],{autoAlpha:0});",
           f"tl.fromTo('#gradb',{{autoAlpha:0}},{{autoAlpha:1,duration:.4,immediateRender:false}},{L - .3:.3f});",
           f"tl.fromTo('#bar',{{autoAlpha:0}},{{autoAlpha:1,duration:.3,immediateRender:false}},{L:.3f});",
           f"tl.fromTo('#barfill',{{scaleX:.18}},{{scaleX:.92,duration:{max(.1, O - L):.3f},ease:'none',immediateRender:false}},{L:.3f});"]
    if ICONS:
        tw += [f"tl.fromTo('#col .ic',{{autoAlpha:0,x:40,scale:.7}},{{autoAlpha:1,x:0,scale:1,duration:.42,ease:'back.out(2)',stagger:.06,immediateRender:false}},{L - .22:.3f});"]
    if NAME:
        tw += [f"tl.fromTo('#who',{{autoAlpha:0,y:30}},{{autoAlpha:1,y:0,duration:.42,ease:'power3.out',immediateRender:false}},{L - .12:.3f});"]
    if LINE:
        tw += [f"tl.fromTo('#cap',{{autoAlpha:0,y:24}},{{autoAlpha:1,y:0,duration:.42,ease:'power3.out',immediateRender:false}},{L - .04:.3f});"]
    if TAP is not None:
        tw += ["gsap.set('#tap',{autoAlpha:0,x:250,y:190,scale:1});", "gsap.set('#ring',{autoAlpha:0,scale:.4});",
               "gsap.set('#pg',{autoAlpha:0,y:16});",
               f"tl.to('#tap',{{autoAlpha:1,duration:.18}},{TAP - .5:.3f});",
               f"tl.to('#tap',{{x:0,y:0,duration:.44,ease:'power3.inOut'}},{TAP - .5:.3f});",
               f"tl.to('#tap',{{scale:.72,duration:.08,ease:'power2.in'}},{TAP - .06:.3f});",
               f"tl.to('#tap',{{scale:1,duration:.22,ease:'back.out(3)'}},{TAP + .03:.3f});",
               f"tl.to('#tap',{{autoAlpha:0,x:60,y:70,duration:.3,ease:'power2.in'}},{TAP + .32:.3f});",
               f"tl.fromTo('#ring',{{autoAlpha:.9,scale:.4}},{{autoAlpha:0,scale:2.4,duration:.5,ease:'power2.out',immediateRender:false}},{TAP:.3f});",
               f"tl.to('#pill',{{scale:.9,duration:.07,ease:'power2.in'}},{TAP - .04:.3f});",
               f"tl.to('#pill',{{scale:1,duration:.32,ease:'back.out(3)'}},{TAP + .03:.3f});",
               f"tl.to('#pill',{{backgroundColor:'rgba(255,255,255,.22)',borderColor:'rgba(255,255,255,0)',duration:.18}},{TAP:.3f});",
               f"tl.to('#pf',{{autoAlpha:0,y:-16,duration:.14,ease:'power2.in'}},{TAP:.3f});",
               f"tl.to('#pg',{{autoAlpha:1,y:0,duration:.22,ease:'power3.out'}},{TAP + .08:.3f});"]
    if WORD and ICONS:
        t = WORD[1]
        tw += ["gsap.set('#cbub',{autoAlpha:0,scale:0,x:70,y:30});",
               f"tl.to('#cglyph',{{scale:1.28,duration:.12,ease:'power2.out'}},{t - .26:.3f});",
               f"tl.to('#cglyph',{{scale:1,duration:.3,ease:'back.out(3)'}},{t - .14:.3f});",
               f"tl.to('#cbub',{{autoAlpha:1,scale:1,x:0,y:0,duration:.46,ease:'back.out(1.9)'}},{t - .04:.3f});"]
    tw += ["gsap.set('#hfill',{autoAlpha:0,scale:.2});"] if ICONS else []
    if LIKE is not None:
        tw += [f"tl.to('#hfill',{{autoAlpha:1,scale:1,duration:.34,ease:'back.out(3)'}},{LIKE - .04:.3f});"]
    if F_OUT is not None:
        g = E - O
        # the way back: dressing off, window opens, rig returns to exactly full frame one frame before F_OUT
        tw += [f"tl.to('#ui',{{autoAlpha:0,duration:.14,ease:'power1.in'}},{O - .08:.3f});",
               f"tl.to('#gradb',{{autoAlpha:0,duration:.2}},{O - .08:.3f});",
               f"tl.to('#plate',{{clipPath:'{clip0}',duration:{g - .05:.3f},ease:'power3.inOut'}},{O:.3f});",
               f"tl.to(['#shad','#rim'],{{{full},duration:{g - .05:.3f},ease:'power3.inOut'}},{O:.3f});",
               f"tl.to(['#shadw','#rimw'],{{autoAlpha:0,duration:.22,ease:'power2.in'}},{O + .04:.3f});",
               f"tl.to('#rig',{{scale:1,x:0,y:0,rotationX:0,rotationY:0,duration:{g - .04:.3f},ease:'expo.inOut'}},{O:.3f});",
               f"tl.set('#cutw',{{autoAlpha:0}},{E - .012:.3f});"]
    return tw


def audio():
    if os.environ.get('SFX') == '0' or not SOUNDS:
        return []
    sfx = [('whoosh-short', A - .04, .26)]
    if F_OUT is not None:
        sfx.append(('whoosh-short', O - .04, .2))
    if TAP is not None:
        sfx.append(('click-soft', TAP - .02, .6))
    if WORD and ICONS:
        sfx.append(('pop', WORD[1] - .03, .2))
    out, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        if not os.path.exists(f'assets/sfx/{name}.mp3'):
            print(f'  (sound {name} not in assets/sfx: skipped)')
            continue
        t = max(0.0, t)
        d = min(SFX_LEN[name], DUR - t)
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'  <audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


G = f'filter:{GRADE};' if GRADE else ''
BOTTOM = .58 if (NAME or LINE) else .30      # how dark the foot of the card gets (darker when text sits on it)
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#07080a}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#07080a}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;{G}}}
#bdropw{{position:absolute;inset:0;z-index:0}}
#bdrop{{transform-origin:50% 45%}}
#bshade{{position:absolute;inset:0;z-index:1;background:
  radial-gradient(75% 50% at 50% 44%,rgba(10,12,16,0) 0%,rgba(6,7,10,.38) 68%,rgba(4,5,7,.74) 100%),
  linear-gradient(180deg,rgba(18,28,40,.22),rgba(8,9,12,.30))}}
#rig{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:2}}
#shadw,#rimw,#plate,#cutw{{position:absolute;inset:0}}
#shad,#rim,#gradb{{position:absolute;left:{RX}px;top:{RY}px;width:{RW}px;height:{RH}px}}
#shad{{background:#0b0c0f;box-shadow:0 90px 160px rgba(0,0,0,.72),0 34px 60px rgba(0,0,0,.5),0 0 0 1px rgba(0,0,0,.4)}}
#gradb{{background:linear-gradient(180deg,rgba(0,0,0,0) 58%,rgba(0,0,0,{BOTTOM * .72:.2f}) 86%,rgba(0,0,0,{BOTTOM:.2f}) 100%)}}
#rim{{border:{max(2, round(3 * UK))}px solid rgba(255,255,255,.42);box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}}

/* card dressing: drawn for an 800 px wide card, scaled to the measured one */
#ui{{position:absolute;left:{RX}px;top:{RY}px;width:800px;height:{UH:.1f}px;transform:scale({UK:.4f});transform-origin:0 0;
  color:#fff;font-family:Inter;text-shadow:0 2px 10px rgba(0,0,0,.35)}}
#col{{position:absolute;left:700px;width:84px;bottom:{176 if (NAME or LINE) else 96}px;display:flex;flex-direction:column;align-items:center;gap:46px}}
.ic{{position:relative;display:flex;flex-direction:column;align-items:center}}
.glyph{{position:relative;width:62px;height:62px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.35))}}
.glyph svg{{width:62px;height:62px;display:block}}
.glyph.dots,.glyph.dots svg{{height:40px}}
#hfill{{position:absolute;inset:0}}
#cbub{{position:absolute;right:96px;top:-12px;padding:20px 34px;border-radius:44px;background:rgba(255,255,255,.97);color:#111;
  text-shadow:none;transform-origin:100% 50%;white-space:nowrap;box-shadow:0 26px 50px rgba(0,0,0,.45),0 6px 14px rgba(0,0,0,.25)}}
.bword{{font:900 46px 'Inter Tight';letter-spacing:-.02em;line-height:1}}
#who{{position:absolute;left:38px;bottom:{134 if LINE else 76}px;display:flex;align-items:center;gap:16px}}
#av{{width:62px;height:62px;border-radius:50%;background:rgba(255,255,255,.2);border:2px solid rgba(255,255,255,.9);
  display:flex;align-items:center;justify-content:center;font:600 28px Inter}}
#handle{{font:600 31px Inter;letter-spacing:-.2px}}
#pill{{position:relative;width:176px;height:52px;border-radius:14px;border:2px solid rgba(255,255,255,.92);display:flex;
  align-items:center;justify-content:center;font:600 26px Inter}}
#pill span{{position:absolute}}
#ring{{position:absolute;left:50%;top:50%;width:90px;height:90px;margin:-45px 0 0 -45px;border-radius:50%;border:4px solid rgba(255,255,255,.9)}}
#tap{{position:absolute;left:50%;top:50%;width:74px;height:74px;margin:-37px 0 0 -37px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.95) 0%,rgba(255,255,255,.75) 55%,rgba(255,255,255,.35) 100%);
  box-shadow:0 10px 28px rgba(0,0,0,.45),0 0 0 3px rgba(255,255,255,.35)}}
#cap{{position:absolute;left:38px;right:130px;bottom:76px;font:500 26px Inter;color:rgba(255,255,255,.92);white-space:nowrap;overflow:hidden}}
#bar{{position:absolute;left:26px;width:748px;bottom:35px;height:5px;border-radius:3px;background:rgba(255,255,255,.28);overflow:hidden}}
#barfill{{width:100%;height:100%;background:#fff;transform-origin:0 50%}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def build():
    nl = '\n'
    v = f'muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}"'
    return f'''<!doctype html>
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
{nl.join(audio())}
  <div id="bdropw"><video id="bdrop" class="full" src="assets/backdrop.mp4" {v} data-track-index="3"></video></div>
  <div id="bshade"></div>
  <div id="rig">
    <div id="shadw"><div id="shad"></div></div>
    <div id="plate"><video id="bgv" class="full" src="assets/aroll.mp4" {v} data-track-index="0"></video>
      <div id="gradb"></div></div>
    <div id="rimw"><div id="rim"></div></div>
    {ui_html()}
    <div id="cutw"><video id="cut" class="full" src="assets/subject_fade.webm" {v} data-track-index="1"></video></div>
  </div>
{SAFE_GUIDE if os.environ.get('SAFE') else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{nl.join(tweens())}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open('index.html', 'w').write(build())
slot = os.path.basename(HERE)
print(f'wrote index.html  {N} frames  shrink f{F_IN - SHRINK} to f{F_IN}, '
      + (f'back to full frame by f{F_OUT}' if F_OUT is not None else 'card stays to the last frame (END ON A CUT)'))
print(f'card on screen: top {SCR_TOP - RH * S * (PUSH - 1) / 2:.0f}, bottom {SCR_TOP + RH * S * (PUSH + 1) / 2:.0f} at its biggest (safe zone 220 to 1470), '
      f'x {540 - RW * S / 2:.0f} to {540 + RW * S / 2:.0f}; ' + ('hands come out' if m['hand_frames'] >= 3 else 'head pop-out only'))
print(f'render to renders/{slot}.mp4' + ('   (SAFE guide is ON: snapshots only)' if os.environ.get('SAFE') else ''))
