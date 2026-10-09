#!/usr/bin/env python3
"""Claude Creator Studio: the eight overall styles. An overall style = a footage treatment (grade, layout, cuts,
push-ins) plus a caption treatment, driven by the same word timings as the caption styles.

This file is a library, like captions.py. scripts/build_reel.py calls page(<style key>, caption) after
captions.load(project).

  caption = None      the style's own captions (what the picker preview shows)
  caption = '<key>'   the buyer swapped the captions: the footage treatment stays, that caption style goes on top
  caption = 'none'    footage treatment only

Nothing here is typed in for a clip:
  where the speaker is      <project>/layout.json  (scripts/layout.py)
  any words on screen       <project>/plan.json    "style": {"<style key>": {...}}  written by the editing Claude
                            (shapes are documented in references/styles.md). Every style still builds with an empty
                            plan: it falls back to the hook title, the first marked number and the comment keyword.
  extra footage (b-roll)    plan.json "style": {"<key>": {"broll": [{"src", "from", "to", "media", "zoom"}]}}
"""
import captions as cap
from captions import Build, T, esc, bare, low, chunk, windows, STAR

NAMES = {'soft-hours': 'Soft Hours', 'glam-cam': 'Glam Cam', 'color-block': 'Color Block', 'camera-shy': 'Camera Shy',
         'chalk-talk': 'Chalk Talk', 'fireside': 'Fireside', 'raw-tape': 'Raw Tape', 'show-and-tell': 'Show and Tell'}
NEEDS_CUTOUT = ('chalk-talk', 'show-and-tell')      # these two lift the speaker off the room: they need assets/subject.webm
NO_SWAP = {'show-and-tell': 'Show and Tell carries the words on its light canvas, and caption styles are built for video, '
                            'so they would not read there.'}
NOTES = []                                           # things the editing Claude should tell the buyer; build_reel prints them


def plan(key):
    return (cap.PLAN.get('style') or {}).get(key) or {}


def face_origin():
    """transform-origin on the speaker's face, as percentages of the frame"""
    h = cap.HEAD
    return f"{h['cx'] / 1080 * 100:.1f}% {(h['top'] + .75 * h['width']) / 1920 * 100:.1f}%"


def shot(b, i_d, src, t0, t1, media=0.0, zoom=1.0, push=.05, origin='50% 45%', track=0):
    """one video shot on screen from t0 to t1, with a slow push-in; returns its html"""
    b.cut(f'#{i_d}w', t0, t1)
    b.js.append(f"tl.fromTo('#{i_d}p',{{scale:{zoom}}},{{scale:{zoom + push},duration:{t1 - t0:.3f},ease:'none',immediateRender:false}},{T(t0):.3f});")
    return (f'<div id="{i_d}w" class="shot"><div id="{i_d}p" class="full" style="transform-origin:{origin};transform:scale({zoom})">'
            f'<video id="{i_d}" class="full gr" src="{src}" muted playsinline data-start="{T(t0):.3f}" data-media-start="{media:.3f}" '
            f'data-duration="{t1 - T(t0):.3f}" data-track-index="{track}"></video></div></div>')


def typed(b, text, t0, t1):
    """text typed out letter by letter between t0 and t1"""
    out = []
    for k, ch in enumerate(text):
        cid = b.nid('h')
        out.append(f'<span id="{cid}">{esc(ch)}</span>')
        b.cut(f'#{cid}', max(.03, t0 + (t1 - t0) * k / max(len(text), 1)))
    return ''.join(out)


def first(mark):
    """index of the first word with that mark, or None"""
    return next((i for i, w in enumerate(cap.W) if w.get('e') == mark), None)


def sentence_starts():
    """start time of every sentence (the word after a . ? or !)"""
    out, new = [], True
    for w in cap.W:
        if new:
            out.append(w['start'])
        new = w['text'][-1:] in '.?!'
    return out


def phrase_starts(min_gap=0.0):
    """start time of every phrase (same phrasing the captions use), at least min_gap apart"""
    out = []
    for g in chunk(cap.W, 6, 28):
        if not out or g[0]['start'] - out[-1] >= min_gap:
            out.append(g[0]['start'])
    return out


def footage_shots(b, key, push, auto_cuts=None, zooms=(1.0,)):
    """The pictures under the voice. With "broll" in the plan those clips are the shots (gaps show whatever is under
    them). Without it the reel's own cut is used: one shot per segment, or per auto cut, zoomed in turn."""
    broll = plan(key).get('broll')
    if broll:
        return [shot(b, f's{n}', s['src'], float(s['from']), min(float(s['to']), cap.DUR), media=float(s.get('media', 0)),
                     zoom=float(s.get('zoom', 1)), push=push, track=n % 2) for n, s in enumerate(broll)]
    cuts = sorted(set([t0 for t0, _ in cap.SEGS] + list(auto_cuts or [])))
    cuts = [t for i, t in enumerate(cuts) if i == 0 or t - cuts[i - 1] > .5]
    ends = cuts[1:] + [cap.DUR]
    origin = '50% 45%' if cap.FACELESS else face_origin()
    return [shot(b, f's{n}', cap.VIDEO, t0, t1, media=t0, zoom=zooms[n % len(zooms)], push=push, origin=origin, track=n % 2)
            for n, (t0, t1) in enumerate(zip(cuts, ends))]


def captions(b, caption, own):
    """the style's own captions (own is a function) unless the buyer swapped them"""
    if caption is None:
        own(b)
    elif caption == 'custom':                 # the buyer's own caption spec rides on the overall style
        cap.custom(b)
        b.cap_top = cap.cap_top('custom')
    elif caption != 'none':
        cap.STYLES[caption][2](b)
        b.cap_top = cap.cap_top(caption)      # a slot's caption_y moves the top of this style's line


VIGNETTE = '<div class="full" style="background:radial-gradient(120% 75% at 50% 45%,rgba(0,0,0,0) 50%,rgba(20,10,5,.42) 100%)"></div>'


# ======================================================================================================================
# FOR HER (all four work faceless or on camera)
# ======================================================================================================================
def soft_hours(b, caption):
    """cozy how-to: dim warm room, slow cuts, the bold + typed italic captions (upper third when nobody is on camera)"""
    b.css.append('.gr{filter:brightness(.9) saturate(.86) sepia(.16) contrast(.96)}')
    body = footage_shots(b, 'soft-hours', push=.06)
    body.append(VIGNETTE)
    if cap.FACELESS:
        cap.Y_CHEST = 470
    captions(b, caption, cap.moodboard)
    return body


def camera_shy(b, caption):
    """tips list: quick cuts, a pinned title, the points typed onto the frame as a small numbered list"""
    p = plan('camera-shy')
    top = 470 if cap.FACELESS else cap.Y_CHEST - 60          # upper third with nobody on camera, else under the chin
    b.css.append(f'''.gr{{filter:brightness(.88) saturate(.84) sepia(.14) contrast(.97)}}
.cs{{position:absolute;left:96px;top:{top}px;width:880px;color:#fff;text-shadow:0 2px 16px rgba(0,0,0,.6)}}
.cs .t{{font-family:'Poppins';font-weight:700;font-size:58px;line-height:68px;letter-spacing:-.012em}}
.cs .i{{font-family:'Instrument Serif';font-style:italic;font-size:56px;line-height:60px;margin-bottom:14px}}
.cs .r{{font-family:'Poppins';font-weight:600;font-size:36px;line-height:54px}}
.cs .st{{position:absolute;color:#fff;filter:drop-shadow(0 0 5px rgba(255,255,255,.55))}}''')
    body = footage_shots(b, 'camera-shy', push=.04, auto_cuts=phrase_starts(1.4), zooms=(1.0, 1.3, 1.0, 1.25))
    body.append(VIGNETTE)
    lst = p.get('list')
    if caption is None and lst:
        rows = lst.get('rows') or []
        if not cap.FACELESS and len(rows) > 3:
            NOTES.append('Camera Shy: only the first 3 list rows fit under the speaker; the rest were left off.')
            rows = rows[:3]
        t_in = float(lst.get('at', cap.W[0]['start']))
        sub = lst.get('sub')
        html = f'<div class="t">{esc(lst.get("title", cap.TITLE[0]))}</div>'
        if sub:
            t_sub = float(lst.get('subAt', t_in + .4))
            html += f'<div class="i">{typed(b, sub, t_sub, t_sub + max(.6, len(sub) * .05))}</div>'
        for r in rows:
            html += f'<div class="r">{typed(b, r["text"], float(r["at"]), float(r["at"]) + max(.6, len(r["text"]) * .045))}</div>'
        body.append(f'<div id="cs" class="cs">{html}'
                    f'<span class="st" style="left:-50px;top:14px;width:34px;height:34px">{STAR}</span>'
                    f'<span class="st" style="left:640px;top:-30px;width:24px;height:24px">{STAR}</span></div>')
        b.tween_in('#cs', t_in, {'y': 12}, {'y': 0}, .2)
    else:
        if caption is None:
            NOTES.append('Camera Shy: plan.json has no typed list for this reel, so Moodboard captions were used instead.')
        if cap.FACELESS:
            cap.Y_CHEST = 470
        captions(b, caption, cap.moodboard)
    return body


def color_block(b, caption):
    """a day in the life in pieces: shots broken up by flat colour cards, huge tight lowercase on top"""
    p = plan('color-block')
    color = p.get('color', '#B5C77A')
    b.css.append('.gr{filter:saturate(1.06) contrast(1.03)}')
    body = [f'<div class="full" style="background:{color}"></div>']        # the colour card is simply what is under the shots
    if p.get('broll'):
        body += footage_shots(b, 'color-block', push=.03)
    else:
        cards = p.get('cards')
        if cards is None:                                                   # a card on the first beat of every new sentence
            starts = sentence_starts()[1:]
            cards = [[t, min(t + 1.15, cap.DUR)] for t in starts if cap.DUR - t > 1.6]
        edges, t = [], 0.0
        for c0, c1 in cards:
            if c0 - t > .3:
                edges.append((t, float(c0)))
            t = float(c1)
        if cap.DUR - t > .1:
            edges.append((t, cap.DUR))
        origin = '50% 45%' if cap.FACELESS else face_origin()
        body += [shot(b, f's{n}', cap.VIDEO, t0, t1, media=t0, push=.03, origin=origin, track=n % 2) for n, (t0, t1) in enumerate(edges)]
    captions(b, caption, cap.loud)
    return body


def glam_cam(b, caption):
    """studio beauty tutorial: tight face shot, a jump zoom on every new thought, one-word serif captions"""
    p = plan('glam-cam')
    b.css.append('.gr{filter:contrast(1.04) saturate(1.05)}')
    beats = p.get('zooms')
    if beats is None:
        levels = (1.16, 1.0, 1.22, 1.1, 1.26, 1.0)
        beats = [[t, levels[n % len(levels)]] for n, t in enumerate(phrase_starts(.7)[1:])]
    chin = cap.HEAD['chin'] - cap.LIFT            # jump zooms pivot on the chin so it never moves into the captions
    video = (f'<video id="gv" class="full gr" src="{cap.VIDEO}" muted playsinline data-start="0" data-media-start="0" '
             f'data-duration="{cap.DUR:.3f}" data-track-index="0"></video>')
    if cap.LIFT:                                  # the face fills the frame: lifted picture, dark fill under it
        body = [f'<div class="full" style="background:{cap.FILL}"></div>'
                f'<div id="gz" class="full" style="transform-origin:50% {chin}px"><div class="full" style="top:{-cap.LIFT}px">{video}</div></div>',
                f'<div class="full" style="top:{1920 - cap.LIFT - 190}px;height:{cap.LIFT + 190}px;'
                f'background:linear-gradient(180deg,transparent 0%,{cap.FILL} {190 / (cap.LIFT + 190) * 100:.0f}%)"></div>']
    else:
        body = [f'<div id="gz" class="full" style="transform-origin:{cap.HEAD["cx"]}px {chin}px">{video}</div>']
    for t, z in beats:
        b.js.append(f"tl.set('#gz',{{scale:{float(z)}}},{T(float(t)):.3f});")
    captions(b, caption, cap.vanity)
    return body


# ======================================================================================================================
# FOR HIM
# ======================================================================================================================
def fireside(b, caption):
    """one locked-off shot, warm lamp light, no added cuts: a slow push-in and small gold captions over the chest"""
    h = cap.HEAD
    cx, fy = h['cx'] / 1080 * 100, (h['top'] - cap.LIFT + .75 * h['width']) / 1920 * 100      # the face, in % of the frame
    b.css.append(f'''.gr{{filter:sepia(.5) saturate(1.7) contrast(1.1) brightness(.9) hue-rotate(-14deg)}}
.fs{{top:{cap.Y_CHEST + 70}px;font-family:'Newsreader';font-weight:500;font-size:46px;line-height:56px;color:#F4AE52;
  text-shadow:0 2px 14px rgba(20,8,0,.75),0 0 3px rgba(20,8,0,.6)}}''')
    video = (f'<video id="bgv" class="full gr" src="{cap.VIDEO}" muted playsinline data-start="0" data-media-start="0" '
             f'data-duration="{cap.DUR:.3f}" data-track-index="0"></video>')
    body = [f'<div id="pl" class="full" style="transform-origin:{cx:.1f}% {fy:.1f}%">{cap.lifted(video)}</div>',
            f'<div class="full" style="background:radial-gradient(70% 45% at {cx:.1f}% {fy + 2:.1f}%,rgba(255,150,50,.34),rgba(255,110,20,.16));mix-blend-mode:overlay"></div>',
            f'<div class="full" style="background:radial-gradient(95% 62% at {cx:.1f}% {fy + 6:.1f}%,rgba(0,0,0,0) 38%,rgba(12,5,0,.62) 100%)"></div>']
    b.js.append(f"tl.fromTo('#pl',{{scale:1}},{{scale:1.08,duration:{cap.DUR:.3f},ease:'none',immediateRender:false}},0);")

    def gold(b):
        for g, t0, t1 in windows(chunk(cap.W, 2, 14)):
            i_d = b.nid()
            b.html.append(f'<div id="{i_d}" class="cap fs">{esc(" ".join(low(w) for w in g))}</div>')
            b.cut(f'#{i_d}', t0, t1)
    captions(b, caption, gold)
    return body


def raw_tape(b, caption):
    """a sit-down left alone: 4:3 picture inside the reel, faded green film grade, small plain yellow subtitles"""
    WIN_TOP, WIN_H = 555, 810
    h = cap.HEAD
    # the head sits 158px under the top of the window; a face that is too tall for that slides up until the chin
    # clears the subtitle line
    up = max(h['top'] - 158, h['chin'] - (WIN_H - 150))
    up = int(min(max(up, 0), 1920 - WIN_H))
    b.css.append(f'''.gr{{filter:contrast(.92) saturate(.82) brightness(1.04) sepia(.12) hue-rotate(14deg)}}
#win{{position:absolute;left:0;top:{WIN_TOP}px;width:1080px;height:{WIN_H}px;overflow:hidden;background:#111}}
#win .in{{position:absolute;left:0;top:{-up}px;width:1080px;height:1920px;transform-origin:{h['cx']}px {h['top'] + 118}px}}
.rt{{top:{WIN_TOP + WIN_H - 96}px;font-family:'Arimo';font-weight:400;font-size:36px;line-height:44px;color:#F4E455;
  text-shadow:0 2px 3px rgba(0,0,0,.75),0 0 8px rgba(0,0,0,.4)}}''')
    body = ['<div class="full" style="background:#000"></div>',
            f'<div id="win"><div id="rin" class="in"><video id="bgv" class="full gr" src="{cap.VIDEO}" muted playsinline data-start="0" '
            f'data-media-start="0" data-duration="{cap.DUR:.3f}" data-track-index="0"></video></div>'
            '<div class="full" style="background:rgba(60,120,90,.16);mix-blend-mode:soft-light"></div>'
            '<div class="full" style="background:rgba(210,225,205,.07)"></div></div>']
    b.js.append(f"tl.fromTo('#rin',{{scale:1}},{{scale:1.06,duration:{cap.DUR:.3f},ease:'none',immediateRender:false}},0);")

    def subs(b):
        for g, t0, t1 in windows(chunk(cap.W, 6, 28)):
            i_d = b.nid()
            b.html.append(f'<div id="{i_d}" class="cap rt">{esc(" ".join(w["text"] for w in g))}</div>')
            b.cut(f'#{i_d}', t0, t1)
    if caption not in (None, 'none'):
        cap.Y_CHEST = min(cap.Y_CHEST, WIN_TOP + WIN_H - 260)      # a swapped caption style stays inside the picture
    captions(b, caption, subs)
    return body


def auto_beats():
    """Fallback script for Chalk Talk and Show and Tell when plan.json gives none: the hook title until the first
    marked number, then the number with what it counts until its sentence ends."""
    beats, W = [], cap.W
    ni = first('num')
    t_num = W[ni]['start'] if ni is not None else None
    hook_end = t_num if t_num is not None else next((w['end'] for w in W if w['text'][-1:] in ',.?!'), W[-1]['end']) + .2
    if hook_end - W[0]['start'] > .5:
        beats.append({'from': W[0]['start'], 'to': hook_end, 'title': ' '.join(t for t in cap.TITLE if t)})
    if ni is not None:
        j = cap.counted(ni)
        t_end = next((w['end'] for w in W[ni:] if w['text'][-1:] in ',.?!'), W[-1]['end']) + .1
        ci = first('cta')
        if ci is not None and ci > ni:
            t_end = min(t_end, W[max(ci - 1, ni)]['start'])
        beats.append({'from': t_num, 'to': t_end, 'big': bare(W[ni]['text']),
                      'lines': [bare(w['text']) for w in W[ni + 1:j]], 'lineAt': [w['start'] for w in W[ni + 1:j]]})
    return beats


def cta_times():
    """(time "comment" is said, time the keyword is said, the keyword) or None"""
    ci = first('cta')
    if ci is None:
        return None
    t_cta = cap.W[ci]['start']
    t_say = next((w['start'] for w in reversed(cap.W[:ci]) if bare(w['text']).lower() == 'comment'), t_cta)
    return t_say, t_cta, bare(cap.W[ci]['text']).strip('"“”\'')


def chalk_talk(b, caption):
    """presenter on a dark studio gradient, hand-drawn marker titles and doodles, cutting out to a rounded b-roll card"""
    p = plan('chalk-talk')
    h = cap.HEAD
    oy = h['top'] + 122                                  # the speaker is scaled 1.5 around a point just under the top of the speaker's head
    ty = 547 - (oy - 183)                                # so the top of the speaker's head lands at y 547, under the titles
    b.css.append(f'''#stg{{position:absolute;inset:0;background:radial-gradient(90% 60% at 50% 38%,#17515c 0%,#0c2c36 46%,#051318 100%)}}
#man{{position:absolute;inset:0;transform-origin:{h['cx']}px {oy}px;transform:translate({540 - h['cx']}px,{ty}px) scale(1.5)}}
#floor{{position:absolute;left:0;right:0;top:1180px;bottom:0;background:linear-gradient(180deg,rgba(5,19,24,0) 0%,#051318 34%)}}
.mk{{position:absolute;font-family:'Covered By Your Grace';color:#fff;white-space:nowrap;transform:rotate(-4deg);transform-origin:0 50%;
  text-shadow:0 3px 14px rgba(0,0,0,.45)}}
.mk span{{display:inline-block}}
.dd{{position:absolute;overflow:visible}}
.dd path{{fill:none;stroke:#fff;stroke-width:8;stroke-linecap:round;stroke-linejoin:round}}
#card{{position:absolute;left:180px;top:330px;width:720px;height:1140px;border-radius:54px;overflow:hidden;
  box-shadow:0 40px 90px rgba(0,0,0,.6);background:#000}}
#card video{{position:absolute;left:0;top:-70px;width:720px;height:1280px;object-fit:cover}}''')
    body = ['<div id="stg"></div>',
            f'<div id="manw"><div id="man"><video id="cut" class="full" src="{cap.CUTOUT}" muted playsinline data-start="0" '
            f'data-media-start="0" data-duration="{cap.DUR:.3f}" data-track-index="0"></video></div><div id="floor"></div></div>']
    cta = cta_times()
    t_stop = cta[0] if cta else cap.DUR

    def underline(i_d, y, width, t):
        b.html.append(f'<svg id="{i_d}" class="dd" style="left:70px;top:{y}px" width="{width}" height="40" viewBox="0 0 {width} 40">'
                      f'<path id="{i_d}p" d="M6 22 C {width * .19:.0f} 4, {width * .39:.0f} 34, {width * .59:.0f} 14 S {width * .87:.0f} 8, {width - 6} 20"/></svg>')
        b.js.append(f"gsap.set('#{i_d}p',{{strokeDasharray:{width + 20},strokeDashoffset:{width + 20}}});")
        b.js.append(f"tl.to('#{i_d}p',{{strokeDashoffset:0,duration:.3,ease:'power2.out'}},{T(t):.3f});")

    for n, bt in enumerate(p.get('beats') or auto_beats()):
        t0, t1 = float(bt['from']), min(float(bt['to']), t_stop)
        if t1 - t0 < .2:
            continue
        if bt.get('big'):                                 # a number with the two words it counts, and a drawn underline
            lines = [str(x).upper() for x in (bt.get('lines') or [])][:2]
            at = list(bt.get('lineAt') or []) + [t0, t0]
            big = str(bt['big']).upper()
            bw = int(len(big) * 118)                      # width of the big number at 250px
            size = min(104, int((1010 - 64 - bw - 30) / (max([len(x) for x in lines] + [1]) * .42)))
            rows = '<br>'.join(f'<span id="k{n}l{k}">{esc(x)}</span>' for k, x in enumerate(lines))
            b.html.append(f'<div id="k{n}a" class="mk" style="left:64px;top:236px;font-size:250px;line-height:210px">{esc(big)}</div>'
                          f'<div id="k{n}b" class="mk" style="left:{64 + bw + 30}px;top:262px;font-size:{size}px;line-height:{size * .92:.0f}px">{rows}</div>')
            b.cut(f'#k{n}a', t0, t1)
            b.cut(f'#k{n}b', float(at[0]), t1)
            if len(lines) > 1:
                b.cut(f'#k{n}l1', float(at[1]))
            t_line = float(at[min(1, len(lines) - 1)]) + .1 if lines else t0 + .1
            underline(f'k{n}d', 486, 640, t_line)
            b.cut(f'#k{n}d', t_line, t1)
        else:                                             # one marker line (two when it is long)
            text = str(bt.get('title', '')).upper()
            words, rows = text.split(), [text]
            if len(text) > 18 and len(words) > 1:
                k = min(range(1, len(words)), key=lambda k: abs(len(' '.join(words[:k])) - len(' '.join(words[k:]))))
                rows = [' '.join(words[:k]), ' '.join(words[k:])]
            size = min(92, int(900 / (max(len(r) for r in rows) * .42)))
            b.html.append(f'<div id="k{n}" class="mk" style="left:70px;top:{262 if len(rows) == 1 else 240}px;font-size:{size}px;'
                          f'line-height:{size}px">{"<br>".join(esc(r) for r in rows)}</div>')
            b.cut(f'#k{n}', t0, t1)
    br = p.get('broll')                                   # cut away to a rounded b-roll card with a marker label
    if br:
        t0, t1 = float(br['from']), float(br['to'])
        body.append(f'<div id="cardw"><div id="card"><video id="brv" src="{br["src"]}" muted playsinline data-start="{T(t0):.3f}" '
                    f'data-media-start="{float(br.get("media", 0)):.3f}" data-duration="{t1 - T(t0):.3f}" data-track-index="1"></video></div></div>')
        b.cut('#cardw', t0, t1)
        b.cut('#manw', 0, t0)
        b.js.append(f"tl.set('#manw',{{autoAlpha:1}},{T(t1):.3f});")
        b.js.append(f"tl.fromTo('#card',{{scale:.9}},{{scale:1,duration:.3,ease:'back.out(1.6)',immediateRender:false}},{T(t0):.3f});")
        if br.get('label'):
            label = str(br['label']).upper()
            b.html.append(f'<div id="kbl" class="mk" style="left:196px;top:232px;font-size:{min(78, int(700 / (len(label) * .42)))}px;line-height:80px">{esc(label)}</div>')
            b.cut('#kbl', t0 + .1, t1)
    if cta:                                               # back on the speaker for the call to action
        t_say, t_cta, kw = cta
        size = min(214, int(900 / (max(len(kw), 2) * .46)))
        b.html.append('<div id="kc1" class="mk" style="left:70px;top:250px;font-size:96px;line-height:92px">COMMENT</div>'
                      f'<div id="kc2" class="mk" style="left:70px;top:336px;font-size:{size}px;line-height:190px">{esc(kw.upper())}</div>')
        b.cut('#kc1', t_say)
        b.cut('#kc2', t_cta)
        underline('kcd', 522, 520, t_cta + .15)
        b.cut('#kcd', t_cta + .15)
    captions(b, caption, lambda b: None)
    return body


def show_and_tell(b, caption):
    """speaker in a rounded window at the bottom, a clean light canvas above for labels, cards and proof"""
    p = plan('show-and-tell')
    b.css.append('''#cv{position:absolute;inset:0;background:#F1F1F3}
#spk{position:absolute;left:SPK_Xpx;top:SPK_Ypx;width:SPK_Wpx;height:SPK_Hpx;border-radius:58px 58px 0 0;overflow:hidden;background:#E7E1D4;
  box-shadow:0 -10px 50px rgba(20,20,30,.2)}
#pop{position:absolute;left:SPK_Xpx;top:POP_Ypx;width:SPK_Wpx;height:POP_Hpx;overflow:hidden}
#spk .in,#pop .in{position:absolute;width:1080px;height:1920px;transform-origin:0 0;transform:scale(SPK_S)}
.lb{position:absolute;left:0;width:1080px;text-align:center;font-family:'Inter Tight';font-weight:800;font-size:64px;line-height:72px;
  letter-spacing:-.02em;color:#111}
.ar{position:absolute;left:510px;width:60px;height:60px}
.cd{position:absolute;background:#fff;border-radius:30px;box-shadow:0 18px 40px rgba(20,20,30,.14),0 2px 6px rgba(20,20,30,.08)}
.th{position:absolute;top:500px;width:226px;height:402px;border-radius:26px;overflow:hidden;box-shadow:0 18px 40px rgba(20,20,30,.2)}
.th img{width:100%;height:100%;object-fit:cover;display:block}
.pill{position:absolute;left:0;width:1080px;top:950px;text-align:center}
.pill span{display:inline-block;background:#fff;border-radius:22px;padding:14px 30px;font-family:'Inter';font-weight:500;font-size:36px;color:#111;
  box-shadow:0 0 0 4px #3B5BFF,0 0 34px rgba(59,91,255,.55)}
#big{position:absolute;left:0;width:1080px;top:500px;text-align:center;font-family:'Inter Tight';font-weight:800;color:#111;letter-spacing:-.03em}''')
    # The speaker card sits flush with the BOTTOM of the video on purpose (the one exception to the bottom safe zone).
    # The room is clipped to the card; the cutout uses the same transform but is only clipped at the sides, so the head
    # pops out above the card's top edge. Framed wider than a face crop: head, shoulders and upper chest.
    SPK_X, SPK_W, SPK_Y, SPK_S = 190, 700, 1400, 1.15         # card left, width, top edge, footage scale
    HEAD_Y = SPK_Y - 112                                       # where the top of the head lands (pops ~110px above the card)
    POP_Y = SPK_Y - 320
    ox = 540 - cap.HEAD['cx'] * SPK_S                          # footage offset so the head top lands at (540, HEAD_Y)
    oy = HEAD_Y - cap.HEAD['top'] * SPK_S
    for token, val in (('SPK_X', SPK_X), ('SPK_Y', SPK_Y), ('SPK_W', SPK_W), ('SPK_H', 1920 - SPK_Y), ('POP_Y', POP_Y),
                       ('POP_H', 1920 - POP_Y), ('SPK_S', SPK_S)):
        b.css[-1] = b.css[-1].replace(token, str(val))
    body = ['<div id="cv"></div>',
            f'<div id="spk"><div class="in" style="left:{ox - SPK_X:.0f}px;top:{oy - SPK_Y:.0f}px"><video id="bgv" class="full" src="{cap.VIDEO}" muted '
            f'playsinline data-start="0" data-media-start="0" data-duration="{cap.DUR:.3f}" data-track-index="0"></video></div></div>',
            f'<div id="pop"><div class="in" style="left:{ox - SPK_X:.0f}px;top:{oy - POP_Y:.0f}px"><video id="cut" class="full" '
            f'src="{cap.CUTOUT}" muted playsinline data-start="0" data-media-start="0" data-duration="{cap.DUR:.3f}" '
            f'data-track-index="1"></video></div></div>']
    arrow = '<svg class="ar" style="top:{y}px" viewBox="0 0 60 60"><path d="M30 4v40M12 30l18 20 18-20" fill="none" stroke="#111" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    link = ('<svg viewBox="0 0 64 64" width="92" height="92"><g fill="none" stroke="#111" stroke-width="6" stroke-linecap="round">'
            '<path d="M27 37a11 11 0 0 0 15.6 0l8-8a11 11 0 0 0-15.6-15.6l-3 3"/><path d="M37 27a11 11 0 0 0-15.6 0l-8 8a11 11 0 0 0 15.6 15.6l3-3"/></g></svg>')
    cta = cta_times()
    t_stop = cta[0] if cta else cap.DUR
    beats = p.get('beats')
    if beats is None:
        beats = [{'from': x['from'], 'to': x['to'],
                  'label': x.get('title') or ' '.join([x['big']] + x.get('lines', []))} for x in auto_beats()]
    for n, bt in enumerate(beats):
        t0, t1 = float(bt['from']), min(float(bt['to']), t_stop)
        if t1 - t0 < .2:
            continue
        label = str(bt.get('label', ''))
        lsize = min(64, int(980 / (max(len(label), 1) * .5)))
        thumbs = (bt.get('thumbs') or [])[:4]
        if bt.get('card'):                                # a label, an arrow and one white card
            icon = link if bt.get('icon') == 'link' else ''
            b.html.append(f'<div id="sb{n}"><div class="lb" style="top:400px;font-size:{lsize}px">{esc(label)}</div>{arrow.format(y=492)}'
                          f'<div class="cd" style="left:300px;top:586px;width:480px;height:270px;display:flex;align-items:center;justify-content:center;gap:26px">'
                          f'{icon}<div style="font-family:\'Inter Tight\';font-weight:800;font-size:{min(60, int(330 / (max(len(str(bt["card"])), 1) * .5)))}px;color:#111">{esc(str(bt["card"]))}</div></div></div>')
            b.cut(f'#sb{n}', t0, t1)
        else:                                             # a label, then up to four proof thumbnails pop in
            b.html.append(f'<div id="sb{n}" class="lb" style="top:{376 if thumbs else 620}px;font-size:{lsize}px">{esc(label)}</div>')
            b.cut(f'#sb{n}', t0, t1)
            x0 = 540 - (len(thumbs) * 246 - 20) / 2
            for k, src in enumerate(thumbs):
                i_d = f'sb{n}t{k}'
                b.html.append(f'<div id="{i_d}w"><div id="{i_d}" class="th" style="left:{x0 + k * 246:.0f}px"><img src="{src}" alt=""></div></div>')
                b.tween_in(f'#{i_d}', t0 + .1 + k * .13, {'y': 40, 'scale': .86}, {'y': 0, 'scale': 1}, .28, 'back.out(1.5)')
                b.out(f'#{i_d}w', t1)
        if bt.get('note'):                                # a highlighted note under the block
            b.html.append(f'<div id="sb{n}n" class="pill"><span>{esc(str(bt["note"]))}</span></div>')
            b.tween_in(f'#sb{n}n', float(bt.get('noteAt', t0 + .6)), {'scale': .8}, {'scale': 1}, .24, 'back.out(2)')
            b.out(f'#sb{n}n', t1)
    if cta:                                               # the call to action, big on the canvas
        t_say, t_cta, kw = cta
        b.html.append(f'<div id="big"><div id="bg1" style="font-size:118px;line-height:120px">Comment</div>'
                      f'<div id="bg2" style="font-size:{min(210, int(900 / (max(len(kw), 2) * .62)))}px;line-height:200px">&ldquo;{esc(kw.upper())}&rdquo;</div></div>')
        b.cut('#bg1', t_say)
        b.tween_in('#bg2', t_cta, {'scale': .8}, {'scale': 1}, .22, 'back.out(2)')
    return body                                           # no caption swap on this style: see NO_SWAP


PRESETS = {'soft-hours': soft_hours, 'camera-shy': camera_shy, 'color-block': color_block, 'glam-cam': glam_cam,
           'fireside': fireside, 'raw-tape': raw_tape, 'chalk-talk': chalk_talk, 'show-and-tell': show_and_tell}


def page(key, caption=None, safe=False):
    """One overall style. caption: None = the style's own, a caption style key = the buyer's swap, 'none' = no captions."""
    del NOTES[:]
    if key in NEEDS_CUTOUT and not cap.CUTOUT:
        raise SystemExit(f'{NAMES[key]} lifts the speaker off the room, so it needs a person cutout first: run '
                         f'scripts/rvm_cut.py <project> (clean edge) or scripts/cutout.py <project> (quick).')
    if caption not in (None, 'none') and key in NO_SWAP:
        NOTES.append(NO_SWAP[key] + ' The caption swap was skipped.')
        caption = None
    if caption == 'bold':
        NOTES.append('Bold puts words behind the head of the untouched footage, so it cannot ride on an overall style. '
                     "The style's own captions were used.")
        caption = None
    b = Build()
    b.css.append('.shot{position:absolute;inset:0;overflow:hidden}')
    body = PRESETS[key](b, caption)
    return cap.document(b, body, safe=safe, audio_track=9)
