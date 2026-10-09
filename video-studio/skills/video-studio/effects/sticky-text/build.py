#!/usr/bin/env python3
"""sticky-text: a tag glued to their cap, beside their head, or on their chest. It moves, tilts and scales with the speaker.

  python build.py            writes index.html (run track.py first: it measures their head, chest and the word starts)
  SAFE=1      draws the Instagram unsafe area in red (snapshots only)
  CAPTIONS=0  tag text only: drops the `small` and `sub` lines
  SFX=0       no pop / whoosh
Layers: plate < tags with anchor 'head' < their cutout (their head hides the tucked end) < tags on 'cap' and 'chest'.
One tl.set per frame carries each tag (x, y, rotation, scale), so it sits on the exact pixel of every video frame.
"""
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ==== CLIP (edit this) ====
TAGS = [
    dict(
        text='YOUR TAG',     # the words on the tag, caps, 1 to 3 words the speaker actually says or that name the thing
        say='',              # spoken word it lands on, as track.py prints it ('' = lands at IN_F). Onset comes from the audio
        anchor='cap',        # 'cap' = on the speaker's cap / forehead, above the brows | 'head' = beside the speaker's head, tucked behind it | 'chest'
        # optional keys (leave them out for the defaults):
        # at=1.20,           # seconds, overrides `say` (only when the printed onset is wrong)
        # small='THE',       # small line above the word (default none)
        # sub='second line', # dark chip under the tag (default none); sub_say='word' = when it drops (default 0.5 s later)
        # side='auto',       # anchor 'head' only: 'left' / 'right' of the speaker's head on screen ('auto' = the side with more room)
        # offset=(0, 0),     # fine move in px (x right, y down) after looking at a snapshot
        # tilt=-4,           # degrees against the picture at the landing frame (after that it turns with the speaker)
        # size=1.0,          # 1.0 = auto (from the speaker's measured head size); 1.2 = 20% bigger. Shrinks by itself if it would not fit
        # out=3.2,           # seconds this tag leaves (default OUT)
    ),
]
IN_F = 4                     # first frame a tag may appear: frames before it are the untouched picture
OUT = None                   # seconds when every tag leaves. None = 9 frames before the slot ends (last frames stay plain)
BROW = 0.40                  # eyebrow line, as a fraction of head height under the cap top. check.py draws it: move it if it is off
HEAD_H = None                # head height / head width. None = measured (track.py prints it); set 1.3 to 1.5 if the chin line is off
TAG_COL, INK, CREAM = '#FAE67A', '#14161C', '#FFF8EF'   # tag, text, text on the dark sub chip
GRADE = 'none'               # CSS filter on the picture. 'none' = the reel grades (keep it, the slot must match the a-roll)
SFX_VOL = 0.75               # sounds at 0.75x the template volumes, always under the speaker's voice
# ==== END CLIP ====

FP = shutil.which('ffprobe') or 'ffprobe'
CLIP = json.load(open(os.path.join(HERE, 'clip.json')))
NF = int(CLIP['frames'])
DUR = NF / 30
if not os.path.exists(os.path.join(HERE, 'work/track.json')):
    sys.exit('run track.py first (it writes work/track.json)')
TR = json.load(open(os.path.join(HERE, 'work/track.json')))
FR = TR['frames']
if TR['n'] != NF:
    sys.exit(f"track has {TR['n']} frames, the slot has {NF}: the cutout and the a-roll do not match, remake the slot")
HH = TR['hh'] if HEAD_H is None else HEAD_H * TR['hw']
CAPTIONS, SFX_ON, SAFE = os.environ.get('CAPTIONS', '1') != '0', os.environ.get('SFX', '1') != '0', bool(os.environ.get('SAFE'))
WORD_PX, PADX, TUCK, TEXT_X, SUB_H = 92, 34, 46, 30, 60       # tag design at size 1.0
KMIN, KMAX = 0.42, 1.5                                        # readable floor (word 39 px) and ceiling


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / 30 - .002)


def rot(x, y, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c - y * s, x * s + y * c


def text_w(text, weight, px, spacing):
    """width of a line in px, measured from the template font (estimate if this Pillow cannot read woff2)"""
    try:
        from PIL import ImageFont
        w = ImageFont.truetype(os.path.join(HERE, f'assets/fonts/InterTight-{weight}-normal.woff2'), px).getlength(text)
    except Exception:
        w = sum(.27 if ch == ' ' else .64 for ch in text) * px
    return w + spacing * px * len(text)


def onset(word, what):
    key = word.strip().lower().strip('.,!?')
    for w in TR.get('words', []):
        if w['text'].lower().strip('.,!?') == key:
            return w['onset']
    sys.exit(f'{what}: "{word}" is not in words.json. track.py prints the words; or give seconds with at=')


def plan(i, tg):
    """everything about one tag: frames, size, where it sits, one key per frame"""
    anchor = tg.get('anchor', 'cap')
    if anchor not in ('cap', 'head', 'chest'):
        sys.exit(f"tag {i}: anchor must be 'cap', 'head' or 'chest'")
    if anchor == 'chest' and not TR['chest_ok']:
        sys.exit(f"tag {i}: their chest is under the frame edge on this clip. Use anchor 'cap' or 'head'")
    t = tg['at'] if tg.get('at') is not None else (onset(tg['say'], f'tag {i}') if tg.get('say') else IN_F / 30)
    fL = min(max(IN_F, round(t * 30)), NF - 20)
    t_out = tg.get('out', OUT)
    fO = NF - 9 if t_out is None else min(round(t_out * 30), NF - 6)
    fEnd = fO + 5
    if fO - fL < 45:
        print(f'!! tag {i} is on screen for {(fO - fL) / 30:.1f} s: under 1.5 s is hard to read (start the slot earlier or end it later)')
    A = [(r['cx'], r['cy'], r['crot'], r['s']) if anchor == 'chest' else (r['hx'], r['hy'], r['rot'], r['s']) for r in FR]
    sL, rL = A[fL][3], A[fL][2]
    hw, hh, capw = TR['hw'] * sL, HH * sL, TR['capw'] * sL
    small = tg.get('small', '') if CAPTIONS else ''
    sub = tg.get('sub') if CAPTIONS else None
    tw = text_w(tg['text'], 900, WORD_PX, -.022)
    Ht = 158 if small else 118
    side = 0
    if anchor == 'head':
        side = {'left': -1, 'right': 1}.get(tg.get('side', 'auto'), 0)
        if not side:
            side = 1 if min(1045 - (A[f][0] + TR['capw'] * A[f][3] / 2) for f in range(fL, fEnd)) >= min(A[f][0] - TR['capw'] * A[f][3] / 2 - 35 for f in range(fL, fEnd)) else -1
        Wt = TUCK + TEXT_X + tw + 30
        box = (-TUCK, -Ht / 2, Wt - TUCK, Ht / 2) if side > 0 else (TUCK - Wt, -Ht / 2, TUCK, Ht / 2)
        k0, base = .40 * hw / Ht, (side * capw / 2, -.26 * hh)
    else:
        Wt = tw + 2 * PADX
        box = (-Wt / 2, -Ht / 2, Wt / 2, Ht / 2)
        k0 = min(.92 * hw / Wt, (BROW - .07) * hh / Ht, .30 * hw / Ht) if anchor == 'cap' else min(1.05 * hw / Wt, .30 * hw / Ht)
        base = (0, -.31 * hh) if anchor == 'cap' else (0, 0)
    boxes = [box]
    if sub:
        sw = max(Wt - 24, text_w(sub, 800, 29, -.012) + 2 * 24 + (TUCK if anchor == 'head' else 0))
        sx = (box[0] + box[2] - sw) / 2 if anchor != 'head' else (box[0] + 12 if side > 0 else box[2] - 12 - sw)
        boxes.append((sx, box[3] + 10, sx + sw, box[3] + 10 + SUB_H))
    k_auto = k0
    k = max(KMIN, min(KMAX, k0 * tg.get('size', 1.0)))
    tilt = tg.get('tilt', -4 if anchor != 'cap' else -2)
    uo = tg.get('offset', (0, 0))
    chin = [FR[f]['top'] + HH * FR[f]['s'] for f in range(NF)]

    def keys(off):
        out = {}
        for f in range(max(fL - 1, 0), min(fEnd + 1, NF - 1) + 1):
            ax, ay, ar, a_s = A[f]
            ox, oy = rot(off[0] * a_s / sL, off[1] * a_s / sL, ar - rL)
            out[f] = (ax + ox, ay + oy, ar - rL, a_s / sL)
        return out

    def quads(off, kk):
        """screen corners of every box on every frame it is visible"""
        loc = [[rot(x * kk, y * kk, tilt) for x, y in ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))] for b in boxes]
        return {f: [[(px + rot(x * sc, y * sc, rr)[0], py + rot(x * sc, y * sc, rr)[1]) for x, y in q] for q in loc]
                for f, (px, py, rr, sc) in keys(off).items()}, loc

    while True:
        _, loc = quads((0, 0), k)
        ys = [p[1] for q in loc for p in q]
        off = [base[0] + uo[0], base[1] + uo[1]]
        if anchor == 'cap':                                    # the bottom edge never goes under the brow line
            off[1] = min(off[1], (BROW - .5 - .03) * hh - max(ys))
        ok = True
        for _ in range(3):                                     # push it into the safe zone by one constant shift (it stays glued)
            pts = [p for qs in quads(off, k)[0].values() for q in qs for p in q]
            lo, hi = max(35 - x for x, y in pts), max(x - (980 if y > 1155 else 1045) for x, y in pts)
            up, dn = max(220 - y for x, y in pts), max(y - 1470 for x, y in pts)
            if (lo > 0 and hi > 0) or (up > 0 and dn > 0) or (anchor == 'head' and max(lo, hi) > 0):
                ok = False
            off[0] += lo if lo > 0 else (-hi if hi > 0 else 0)
            off[1] += up if up > 0 else (-dn if dn > 0 else 0)
        Q = quads(off, k)[0]
        pts = [p for qs in Q.values() for q in qs for p in q]
        ok = ok and all(33 <= x <= (982 if y > 1155 else 1047) and 218 <= y <= 1472 for x, y in pts)
        if anchor == 'cap':
            ok = ok and off[1] + max(ys) <= (BROW - .5 - .01) * hh
        if anchor == 'chest':
            ok = ok and all(min(p[1] for q in qs for p in q) >= chin[f] + .05 * HH * FR[f]['s'] for f, qs in Q.items())
        if ok:
            break
        k *= .93
        if k < KMIN:
            why = {'cap': "their cap sits in the top 220 px (or at the frame edge) for this span, so a tag above their brows has no legal place. Use anchor 'head' or 'chest'",
                   'head': "no room beside their head inside the safe zone. On a close-up use anchor 'cap' (on the cap, sized from their head) or 'chest', or shorten the text",
                   'chest': "their chest is too low in the frame (the tag would sit under y 1470 or on their chin). Use anchor 'cap' or 'head'"}[anchor]
            sys.exit(f'tag {i} ("{tg["text"]}") does not fit: {why}')
    moved = (off[0] - base[0] - uo[0], off[1] - base[1] - uo[1])
    kk = keys(off)
    ks = sorted(kk)
    K = [None] * NF
    for f in ks:
        a, b = kk[max(f - 1, ks[0])], kk[min(f + 1, ks[-1])]
        blur = max(0.0, min(2.4, (math.hypot(b[0] - a[0], b[1] - a[1]) / 2 - 5) * .16))      # a little motion blur on fast moves
        K[f] = [round(kk[f][0], 1), round(kk[f][1], 1), round(kk[f][2], 2), round(kk[f][3], 4), round(blur, 2)]
    print(f'tag {i} "{tg["text"]}" on {anchor}' + (f' ({"right" if side > 0 else "left"} of their head)' if side else '') +
          f': lands frame {fL} ({fL / 30:.2f} s), leaves {fO} to {fEnd}. Size {k:.2f} (auto {k_auto:.2f}), word {WORD_PX * k:.0f} px, '
          f'box {Wt * k:.0f} x {Ht * k:.0f} px. x {min(p[0] for p in pts):.0f}..{max(p[0] for p in pts):.0f}  y {min(p[1] for p in pts):.0f}..{max(p[1] for p in pts):.0f}')
    if k < .98 * max(KMIN, min(KMAX, k0 * tg.get('size', 1.0))):
        print(f'!! tag {i} was shrunk to fit the safe zone / stay off their face')
    if math.hypot(*moved) > 4:
        print(f'!! tag {i} was moved {moved[0]:+.0f}, {moved[1]:+.0f} px to stay inside the safe zone' + (' and above their brows' if anchor == 'cap' else ''))
    if anchor == 'cap' and Wt * k > 1.05 * hw:
        print(f"!! tag {i} is wider than their head ({Wt * k:.0f} vs {hw:.0f} px): on a wide shot anchor 'head' or 'chest' reads better")
    if WORD_PX * k < 48:
        print(f'!! tag {i}: the word is only {WORD_PX * k:.0f} px tall on screen. Shorter text, or another anchor, for a bigger tag')
    t_sub = None
    if sub:
        t_sub = min(onset(tg['sub_say'], f'tag {i} sub') if tg.get('sub_say') else fL / 30 + .5, (fO - 12) / 30)
    return dict(i=i, anchor=anchor, side=side, text=tg['text'], small=small, sub=sub, t_sub=t_sub, fL=fL, fO=fO, fEnd=fEnd, k=k, tilt=tilt,
                box=box, boxes=boxes, Wt=Wt, Ht=Ht, K=K, quads={f: q[0] for f, q in Q.items()})


def sfx_len(name):
    return float(subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                 os.path.join(HERE, f'assets/sfx/{name}.mp3')], capture_output=True, text=True).stdout)


def audio(sfx):
    out, lanes = [], []
    for n, (name, t, vol) in enumerate(sorted(sfx, key=lambda x: x[1])):
        t = max(0.0, t)
        d = min(sfx_len(name), DUR - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{n}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{10 + lane}" data-volume="{vol * SFX_VOL:.3f}"></audio>')
    return out


CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
.full{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.g{{filter:{GRADE}}}
#plate{{position:absolute;inset:0;z-index:1}}
#behind{{position:absolute;inset:0;z-index:2;pointer-events:none}}
#cutw{{position:absolute;inset:0;z-index:3}}
#front{{position:absolute;inset:0;z-index:4;pointer-events:none}}
/* a stuck group: its own (0,0) is the tracked anchor; tl.set moves / rotates / scales it once per frame */
.stick{{position:absolute;left:0;top:0;width:0;height:0;transform-origin:0 0;will-change:transform}}
.piv,.mb{{position:absolute;left:0;top:0;width:0;height:0;transform-origin:0 0}}
.tag,.sub{{position:absolute}}
.tagbody{{position:absolute;inset:0;border-radius:28px;overflow:hidden;
  background:linear-gradient(176deg,rgba(255,255,255,.45) 0%,rgba(255,255,255,0) 34%,rgba(90,70,0,.07) 100%),{TAG_COL};
  box-shadow:0 22px 44px rgba(20,16,4,.34),0 4px 10px rgba(20,16,4,.3),inset 0 2px 0 rgba(255,255,255,.6),inset 0 -3px 0 rgba(90,70,0,.2)}}
.occ{{position:absolute;top:0;bottom:0;width:150px}}
.shine{{position:absolute;top:-20%;left:0;width:90px;height:140%;transform:skewX(-18deg);
  background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.75),rgba(255,255,255,0))}}
.eyebrow{{position:absolute;top:21px;font-family:'JetBrains Mono';font-weight:500;font-size:23px;line-height:26px;letter-spacing:.34em;color:{INK};opacity:.74;white-space:nowrap}}
.word{{position:absolute;font-family:'Inter Tight';font-weight:900;font-size:{WORD_PX}px;line-height:{WORD_PX}px;letter-spacing:-.022em;color:{INK};white-space:nowrap}}
.subbody{{position:absolute;inset:0;border-radius:20px;overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,0)),{INK};
  box-shadow:0 18px 36px rgba(10,10,14,.36),0 3px 8px rgba(10,10,14,.3),inset 0 1px 0 rgba(255,255,255,.14)}}
.subt{{position:absolute;left:0;right:0;top:0;text-align:center;font-family:'Inter Tight';font-weight:800;font-size:29px;line-height:{SUB_H - 2}px;letter-spacing:-.012em;color:{CREAM};white-space:nowrap}}
'''

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def tag_html(p):
    i, b, side = p['i'], p['box'], p['side']
    tx = (TUCK + TEXT_X if side > 0 else 30) if side else PADX            # text start inside the tag
    origin = f'{-b[0]:.0f}px 50%'                                          # the pivot, in tag space
    small = (f'<div id="te{i}" class="eyebrow" style="left:{tx + 4:.0f}px">{p["small"]}</div>') if p['small'] else ''
    occ = ''
    if side:        # the end tucked behind the speaker's head sits in the speaker's shadow
        d = 'left:0;background:linear-gradient(90deg' if side > 0 else 'right:0;background:linear-gradient(270deg'
        occ = f'<div class="occ" style="{d},rgba(20,22,28,.5) 0%,rgba(20,22,28,.22) 38%,rgba(20,22,28,0) 100%)"></div>'
    sub = ''
    if p['sub']:
        s = p['boxes'][1]
        sub = (f'<div id="sb{i}" class="sub" style="left:{s[0]:.0f}px;top:{s[1]:.0f}px;width:{s[2] - s[0]:.0f}px;height:{SUB_H}px">'
               f'<div class="subbody"><div class="subt">{p["sub"]}</div></div></div>')
    return (f'<div id="st{i}" class="stick"><div id="bl{i}" class="mb"><div class="piv" style="transform:rotate({p["tilt"]}deg) scale({p["k"]:.4f})">{sub}'
            f'<div id="tg{i}" class="tag" style="left:{b[0]:.0f}px;top:{b[1]:.0f}px;width:{p["Wt"]:.0f}px;height:{p["Ht"]}px;transform-origin:{origin}">'
            f'<div id="tb{i}" class="tagbody">{small}<div id="tw{i}" class="word" style="left:{tx:.0f}px;top:{49 if p["small"] else 11}px">{p["text"]}</div>'
            f'<div id="ts{i}" class="shine"></div>{occ}</div></div></div></div></div>')


def tag_js(p):
    i, side, T, TO = p['i'], p['side'], F(p['fL']), F(p['fO'])
    k0 = next(k for k in p['K'] if k)
    js = [f"const K{i}={json.dumps(p['K'], separators=(',', ':'))};",
          f"gsap.set('#st{i}',{{x:{k0[0]},y:{k0[1]},rotation:{k0[2]},scale:{k0[3]}}});",
          f"K{i}.forEach((k,n)=>{{if(k){{tl.set('#st{i}',{{x:k[0],y:k[1],rotation:k[2],scale:k[3]}},FT(n));tl.set('#bl{i}',{{filter:'blur('+k[4]+'px)'}},FT(n));}}}});",
          f"gsap.set(['#tg{i}','#ts{i}'],{{autoAlpha:0}});", f"gsap.set('#tw{i}',{{yPercent:128}});",
          f"tl.set('#tg{i}',{{autoAlpha:1}},{T:.3f});"]
    if side:        # slides out from BEHIND the speaker's head; the word rises inside it once the body is out (no half-read word)
        js += [f"tl.fromTo('#tg{i}',{{x:{-200 * side},scale:.66,rotation:{-12 * side}}},{{x:0,scale:1,rotation:0,duration:.32,ease:'back.out(1.45)',immediateRender:false}},{T:.3f});",
               f"tl.fromTo('#tb{i}',{{filter:'blur(7px)'}},{{filter:'blur(0px)',duration:.2,ease:'power2.out',immediateRender:false}},{T:.3f});",
               f"tl.to('#tg{i}',{{x:{-160 * side},scale:.7,autoAlpha:0,duration:.16,ease:'power2.in'}},{TO:.3f});"]
    else:           # pops onto the speaker
        js += [f"tl.fromTo('#tg{i}',{{scale:.45,rotation:-12,y:34}},{{scale:1,rotation:0,y:0,duration:.34,ease:'back.out(2)',immediateRender:false}},{T:.3f});",
               f"tl.fromTo('#tb{i}',{{filter:'blur(8px)'}},{{filter:'blur(0px)',duration:.16,ease:'power2.out',immediateRender:false}},{T:.3f});",
               f"tl.to('#tg{i}',{{scale:.5,autoAlpha:0,duration:.16,ease:'power2.in'}},{TO:.3f});"]
    js += [f"tl.to('#tw{i}',{{yPercent:0,duration:.3,ease:'expo.out'}},{T + .075:.3f});",
           f"tl.set('#ts{i}',{{autoAlpha:1}},{T + .26:.3f});",
           f"tl.fromTo('#ts{i}',{{x:-140}},{{x:{p['Wt'] + 60:.0f},duration:.5,ease:'power2.inOut',immediateRender:false}},{T + .26:.3f});",
           f"tl.set('#ts{i}',{{autoAlpha:0}},{T + .78:.3f});"]
    if p['small']:
        js += [f"gsap.set('#te{i}',{{x:-22,autoAlpha:0}});", f"tl.to('#te{i}',{{x:0,autoAlpha:.74,duration:.24,ease:'power3.out'}},{T + .12:.3f});"]
    if p['sub']:    # drops out from under the tag
        js += [f"gsap.set('#sb{i}',{{autoAlpha:0}});", f"tl.set('#sb{i}',{{autoAlpha:1}},{p['t_sub']:.3f});",
               f"tl.fromTo('#sb{i}',{{y:{-SUB_H - 6},scaleX:.9}},{{y:0,scaleX:1,duration:.38,ease:'back.out(1.5)',immediateRender:false}},{p['t_sub']:.3f});",
               f"tl.to('#sb{i}',{{y:{-SUB_H},autoAlpha:0,duration:.12,ease:'power2.in'}},{TO - .04:.3f});"]
    return js


def build():
    if not TAGS:
        sys.exit('TAGS is empty: nothing to stick')
    plans = [plan(i, tg) for i, tg in enumerate(TAGS)]
    layered = any(p['side'] for p in plans)           # only tags beside the speaker's head need the speaker's cutout as a layer
    if layered and not os.path.exists(os.path.join(HERE, 'assets/subject.webm')):
        sys.exit("anchor 'head' needs assets/subject.webm (the cutout)")
    sfx = []
    for p in plans:
        T = F(p['fL'])
        sfx += ([('whoosh-short', T - .03, .16), ('pop', T + .05, .22)] if p['side'] else [('pop', T + .04, .2)])
        sfx += [('click-soft', p['t_sub'] + .02, .22)] if p['sub'] else []
    f0, f1 = min(p['fL'] for p in plans) - 1, max(p['fEnd'] for p in plans) + 1
    js = ["const FT=n=>Math.max(0,n/30-0.002);"]
    if layered:     # the cutout is only laid over the picture while a tag is behind the speaker: first and last frames stay plain
        js += ["gsap.set('#cutw',{opacity:0});", f"tl.set('#cutw',{{opacity:1}},{F(f0):.3f});", f"tl.set('#cutw',{{opacity:0}},{F(f1):.3f});"]
    for p in plans:
        js += tag_js(p)
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump({'frames': NF, 'brow': BROW, 'hh': HH, 'layered': layered,
               'tags': [{k: p[k] for k in ('i', 'anchor', 'text', 'fL', 'fO', 'fEnd', 'k', 'quads')} for p in plans]},
              open(os.path.join(HERE, 'work/layout.json'), 'w'))
    g = '' if GRADE in ('none', '', None) else ' g'
    nl = '\n'
    behind = nl.join(tag_html(p) for p in plans if p['side'])
    front = nl.join(tag_html(p) for p in plans if not p['side'])
    cut = (f'<div id="cutw"><video id="cut" class="full{g}" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" '
           f'data-duration="{DUR:.3f}" data-track-index="1"></video></div>') if layered else ''
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
{nl.join(audio(sfx)) if SFX_ON else ''}
  <div id="plate"><video id="bgv" class="full{g}" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video></div>
  <div id="behind">{behind}</div>
  {cut}
  <div id="front">{front}</div>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(js)}
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''


open(os.path.join(HERE, 'index.html'), 'w').write(build())
print(f'wrote index.html: {NF} frames ({DUR:.2f} s), render name renders/{os.path.basename(HERE)}.mp4' + ('   [SAFE guide ON: snapshots only]' if SAFE else ''))
