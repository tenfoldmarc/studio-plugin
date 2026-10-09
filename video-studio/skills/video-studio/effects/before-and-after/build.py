#!/usr/bin/env python3
"""before-after: a comparison line sweeps across the raw clip and leaves the edited version of the same frames.

One composition, one render. The raw a-roll plays underneath. The AFTER side sits on top in a box that is clipped at
the line: either the same a-roll with a look made here (grade, shade, captions, optional word behind the head, slow
push-in), or your own finished version of the same frames (AFTER = 'after/<file>', run prep_after.py first).

    python build.py            writes index.html and work/layout.json, prints what it measured and any warning (!!)
    SAFE=1 python build.py     same, with the safe zone drawn in red (snapshots only, never for a render)
    CAPTIONS=0                 no caption words, accent or punch word from this effect (the reel captions it)
    SFX=0                      no whooshes / pop
"""
import json
import math
import os
import shutil
import sys

import measure as M

# ==== CLIP (edit this) ====
COMMIT = 'edited'            # payoff word: the line sweeps across on it. A word/phrase from words.json, ('word', 2) = 2nd time the speaker says it, or seconds
PEEK = 'into'                # lead-in word: the line peeks in, eases back and waits beside the head. Same forms. None = one straight sweep
REST = 'auto'                # x where the line waits between peek and commit. 'auto' = measured (clear of head, captions, labels), a number, or None = no peek
SWEEP = 0.5                  # seconds the commit sweep takes. 0.4 when the next word comes fast, 0.6 for a slow line
LABELS = ('before', 'after')  # the two tags that ride the line. Your own two words, or None. No claims or numbers unless the speaker says them
LABEL_IN = 'auto'            # seconds the first tag pops in. 'auto' = half a second before the line (never in the first 4 frames)
LABEL_Y = 232                # top of the tags (220 is the top of the safe zone). Move only if build.py says a tag sits on the head
AFTER = None                 # None = the look below is made here. 'after/mine.mp4' = your finished version of the SAME frames (see effect.md)
AFTER_SHIFT = 0              # own file only: frames to skip at its start so it lines up (prep_after.py prints the number)
AFTER_GRADE = 'contrast(1.07) saturate(.9) brightness(.97)'   # CSS filter of the after side. Stronger: contrast(1.12) saturate(1.08). 'none' = off
AFTER_SHADE = True           # soft vignette + cool tone on the after side. False = grade only
PUSH = 1.045                 # slow push-in on the after side, starts when the sweep is done. 1 = off
CAPS = 'auto'                # captions on the after side. 'auto' = from words.json; a list of lines (one entry per spoken word, in order, fix spellings); None = off
CAP_Y = 'auto'               # top of the caption line. 'auto' = under the chin (1200 to 1340), or a number
ACCENT = None                # one caption word that turns yellow with an underline and two sparkles: a word the speaker says, ('word', 2) = 2nd time. None = off
PUNCH = None                 # a word the speaker says, shown big BEHIND the speaker's head from its spoken moment (needs the cutout). None = off
HANDLE_Y = 'auto'            # centre of the round handle on the line. 'auto' = below the chin and off the caption row
OUT = 'auto'                 # when the after look eases off so the slot ends on plain footage. 'auto' = last 0.6 s, seconds, or None = ends on a cut
# ==== END CLIP ====

FPS = 30
YEL, CREAM, INK = '#FAE67A', '#FFF8EF', '#14161C'
OFF_R, OFF_L = 1140, -80                     # line parked off-screen (handle fully out)
SFX_LEN = {'whoosh-short': .57, 'pop': .72}
SFX_GAIN = 0.75
TAG_GAP, TAG_H, DRIFT = 20, 58, 18
CAP_FS = 84
HERE = os.path.dirname(os.path.abspath(__file__))
WARN = []


def warn(msg):
    WARN.append(msg)
    print('!! ' + msg)


EASE = {
    None: lambda u: u,
    'sine.inOut': lambda u: .5 - .5 * math.cos(math.pi * u),
    'power3.out': lambda u: 1 - (1 - u) ** 3,
    'power3.inOut': lambda u: 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2,
}
_fonts = {}


def text_w(s, font, fs, track=0.0):
    """px width of s (PIL reads the woff2; rough table if it cannot)"""
    try:
        from PIL import ImageFont
        key = (font, round(fs))
        if key not in _fonts:
            _fonts[key] = ImageFont.truetype(os.path.join(HERE, 'assets/fonts', font), round(fs))
        return _fonts[key].getlength(s) + track * fs * len(s)
    except Exception:
        return (.53 + track) * fs * len(s)


def line_w(words):
    return sum(text_w(w, 'InterTight-800-normal.woff2', CAP_FS, -.04) + .2 * CAP_FS for w in words)


def path_x(path, t):
    if t <= path[0][0]:
        return path[0][1]
    for (t0, x0, _), (t1, x1, ease) in zip(path, path[1:]):
        if t <= t1:
            return x0 + (x1 - x0) * EASE[ease]((t - t0) / (t1 - t0))
    return path[-1][1]


def track(sel, rows):
    """rows = one dict of gsap props per frame. A set for frame 0 and linear keyframes over the frames that change,
    so the value ON every rendered frame is exactly the sampled one (separate eased tweens tear the edge)."""
    def same(a, b):
        return all(abs(a[k] - b[k]) < 1e-4 for k in a)
    def num(v):
        return '0' if abs(v) < 5e-4 else f'{v:.3f}'.rstrip('0').rstrip('.')
    fmt = lambda r: ','.join(f'{k}:{num(v)}' for k, v in r.items())
    out = [f"gsap.set('{sel}',{{{fmt(rows[0])}}});"]
    first = next((i for i in range(1, len(rows)) if not same(rows[i], rows[0])), None)
    if first is None:
        return out
    last = max(i for i in range(1, len(rows)) if not same(rows[i], rows[i - 1]))
    kf = ','.join(f"{{{fmt(rows[i])},duration:{1 / FPS:.5f},ease:'none'}}" for i in range(first, last + 1))
    out.append(f"tl.to('{sel}',{{keyframes:[{kf}]}},{(first - 1) / FPS:.5f});")
    return out


def clean(w):
    s = w.strip().strip('.,!?;:"()[]')
    return s if s == 'I' or s.startswith("I'") else s.lower()


def solve_rest(hb, spans, wb, wa, labels):
    """x where the line can wait: never on the head, never through a caption, both tags readable and off the head.
    Right of the head first (their face is raw again while it waits), else left of it, else None."""
    def ok(x):
        for q in (x, x + DRIFT):
            if hb[0] - 70 < q < hb[2] + 70:
                return False
            if any(l - 65 < q < r + 65 for l, r in spans):
                return False
            if labels:
                tb, ta = (q - TAG_GAP - wb, q - TAG_GAP), (q + TAG_GAP, q + TAG_GAP + wa)
                if tb[0] < 45 or ta[1] > 1045:
                    return False
                if LABEL_Y + TAG_H + 12 > hb[1] and any(a < hb[2] + 12 and b > hb[0] - 12 for a, b in (tb, ta)):
                    return False
            elif not 120 < q < 960:
                return False
        return True
    right = [x for x in range(int(hb[2]) + 70, 1000) if ok(x)]
    if right:
        return min(right, key=lambda x: abs(x - (hb[2] + 130))), 'R'
    left = [x for x in range(100, max(100, int(hb[0]) - 70)) if ok(x)]
    if left:
        return min(left, key=lambda x: abs(x - (hb[0] - 150))), 'L'
    return None, None


def main():
    NF = M.clip()['frames']
    DUR = math.floor(NF / FPS * 1000) / 1000        # floored to the ms: 5.167 would render one frame too many
    ws = M.words()
    times = M.timeline(ws, M.envelope()) if ws else []
    captions_on = os.environ.get('CAPTIONS', '1') != '0'
    byo = AFTER is not None

    def when(spec, name):
        if spec is None:
            return None, None
        if isinstance(spec, (int, float)):
            return float(spec), None
        phrase, nth = spec if isinstance(spec, tuple) else (spec, 1)
        i = M.find_say(ws, phrase, nth)
        if i is None:
            sys.exit(f"{name} = {spec!r} is not in words.json. The speaker says: {' '.join(w['text'] for w in ws)}")
        return times[i][0], i

    # ---------------------------------------------------------------------------------------------- timing
    t_commit, _ = when(COMMIT, 'COMMIT')
    if t_commit is None:
        sys.exit('COMMIT is empty: name the payoff word')
    t_peek, _ = when(PEEK, 'PEEK')
    c0, c1 = t_commit - .08, t_commit - .08 + SWEEP
    if c0 < 4 / FPS:
        sys.exit(f'COMMIT lands at {t_commit:.2f}s: the slot must start at least 0.3 s before the payoff word')
    if byo:
        t_out = None if OUT is None else (DUR - .5 if OUT == 'auto' else float(OUT))
        out_len = .34
    else:
        t_out = None if OUT is None else (DUR - .6 if OUT == 'auto' else float(OUT))
        out_len = .45
    if t_out is not None:
        if t_out + out_len > DUR - 2 / FPS:
            t_out = DUR - 2 / FPS - out_len
            warn(f'OUT moved to {t_out:.2f}s so the last frames are plain')
        if t_out < c1 + .8:
            warn(f'the after look shows for only {t_out - c1:.2f}s between the sweep ({c1:.2f}s) and OUT ({t_out:.2f}s): '
                 'make the slot longer, or OUT = None and end it on a cut')
    elif c1 > DUR - .5:
        warn(f'the sweep ends at {c1:.2f}s of {DUR:.2f}s: under half a second of the after look')
    hold_end = t_out if t_out is not None else DUR
    peek = t_peek is not None and REST is not None
    if peek and (c0 - (t_peek + .26) < .30 or t_peek - .06 < 3 / FPS):
        warn(f'PEEK at {t_peek:.2f}s leaves no room to ease back before COMMIT at {t_commit:.2f}s (needs 0.65 s, and '
             '0.2 s of slot before it): one straight sweep instead')
        peek = False
    t_in = t_peek - .06 if peek else c0

    # ---------------------------------------------------------------------------------------------- head
    m = M.alpha()
    hs = M.heads(m) if m is not None else None
    fr = lambda t: int(max(0, min(NF - 1, round(t * FPS))))
    hb_wipe = M.head_box(hs, fr(t_in), fr(c1)) if hs is not None else None
    hb_all = M.head_box(hs, 0, NF - 1) if hs is not None else None
    hb_after = M.head_box(hs, fr(c1), fr(hold_end)) if hs is not None else None

    # ---------------------------------------------------------------------------------------------- punch word
    punch = None
    if PUNCH and captions_on and not byo:
        t_p, i_p = when(PUNCH, 'PUNCH')
        if hs is None:
            warn('PUNCH needs the cutout (assets/subject.webm): left out')
        else:
            seg = hs[fr(t_p):fr(hold_end) + 1]
            top_head = float(sorted(seg[:, 1])[len(seg) // 2])
            txt = clean(ws[i_p]['text']) if i_p is not None else str(PUNCH)
            size = 240
            while size >= 120 and (text_w(txt, 'InterTight-900-normal.woff2', size, -.05) > 990 or top_head - .57 * size < 240):
                size -= 8
            if size < 120:
                warn(f'PUNCH "{txt}": no room above their head (top {top_head:.0f}) inside the safe zone: left out')
            else:
                punch = dict(text=txt, t=max(t_p - .05, 2 / FPS), size=size, top=round(top_head - .57 * size), skip=i_p)

    # ---------------------------------------------------------------------------------------------- captions
    lines = []                                             # [a, b, [(t, text, acc)]]
    if CAPS and captions_on and not byo and ws:
        skip = punch['skip'] if punch else None
        if CAPS == 'auto':
            toks, cur, groups = [(clean(w['text']), times[i][0], times[i][1], w['text'], i) for i, w in enumerate(ws)], [], []
            for k, tok in enumerate(toks):
                if tok[4] == skip or not tok[0]:
                    continue
                tight = t_in - .3 < tok[1] < c1 + .05           # short lines while the line is on screen
                if cur:
                    prev = cur[-1]
                    full = line_w([c[0] for c in cur] + [tok[0]]) > (380 if tight else 640) or len(cur) >= 3
                    gap = tok[1] - prev[1]                     # start to start: Whisper's word ENDS are not to be trusted
                    stop = prev[3].strip()[-1:]
                    if full or gap > .65 or stop in ('.', '?', '!') or (stop == ',' and gap > .4) or (prev[1] < c1 - .02 <= tok[1]):
                        groups.append(cur)
                        cur = []
                cur.append(tok)
            if cur:
                groups.append(cur)
            groups = [[(t, txt, i) for txt, t, _, _, i in g] for g in groups]
        else:
            flat = [w for line in CAPS for w in line.split()]
            if len(flat) > len(ws):
                sys.exit(f'CAPS has {len(flat)} words, words.json has {len(ws)}: one entry per spoken word, in order')
            groups, k = [], 0
            for line in CAPS:
                groups.append([(times[k + j][0], w, k + j) for j, w in enumerate(line.split()) if k + j != skip])
                k += len(line.split())
            groups = [g for g in groups if g]
        acc = when(ACCENT, 'ACCENT')[1] if ACCENT else None      # index of that one spoken word
        for gi, g in enumerate(groups):
            a = max(g[0][0] - .04, 3 / FPS)
            b = max(groups[gi + 1][0][0] - .04, a + .1) if gi + 1 < len(groups) else None
            last_t = g[-1][0]
            if b is not None and b - last_t > 1.6:
                b = last_t + 1.2                           # long pause: the line leaves, it does not hang around
            if t_out is not None:
                if g[-1][0] > t_out - .3:
                    continue                               # a line that could not finish before the look eases off is left out
                b = min(b, t_out) if b is not None else t_out
            lines.append([a, b, [(max(a, t - .02), txt, 'acc' if i == acc else '') for t, txt, i in g
                                 if t_out is None or t < t_out - .15]])
        lines = [l for l in lines if l[2]]
    fb = float(sorted(hs[:, 3])[int(len(hs) * .8)]) if hs is not None else 1000     # 80th percentile: a raised hand does not count
    cap_y = round(min(1340, max(1200, fb + 90))) if CAP_Y == 'auto' else int(CAP_Y)
    for a, b, wl in lines:
        if hs is not None:
            seg = hs[fr(a):fr(b if b is not None else DUR) + 1]
            h = [seg[:, 0].min(), 0, seg[:, 2].max(), float(sorted(seg[:, 3])[int(len(seg) * .8)])]
            w = line_w([x[1] for x in wl])
            if cap_y < h[3] + 10 and 540 - w / 2 < h[2] and 540 + w / 2 > h[0]:
                warn(f'caption "{" ".join(x[1] for x in wl)}" at y {cap_y} is over their chin (about {h[3]:.0f}) at {a:.2f}s: '
                     'set CAP_Y lower, or CAPS = None')

    # ---------------------------------------------------------------------------------------------- labels, rest, handle
    wb = wa = 0
    if LABELS:
        wb, wa = (2 * round((text_w(s, 'Inter-600-normal.woff2', 31, -.01) + 64) / 2) for s in LABELS)
    rest_x, side = None, None
    if peek:
        spans = []
        for a, b, wl in lines:
            if a < c0 + .1 and (b is None or b > t_peek + .2):
                w = line_w([x[1] for x in wl])
                spans.append((540 - w / 2, 540 + w / 2))
        if REST == 'auto':
            if hb_wipe is None:
                warn('REST = auto needs the cutout to find their head: one straight sweep. Give REST an x to get the peek')
                peek = False
            else:
                rest_x, side = solve_rest(hb_wipe, spans, wb, wa, LABELS)
                if rest_x is None:
                    warn(f'no place for the line to wait (head x {hb_wipe[0]:.0f}-{hb_wipe[2]:.0f}, captions {spans}): one '
                         'straight sweep. Shorter caption lines (CAPS list) or REST = x to force it')
                    peek = False
        else:
            rest_x = float(REST)
            side = 'L' if hb_wipe and rest_x < (hb_wipe[0] + hb_wipe[2]) / 2 else 'R'
            if hb_wipe and hb_wipe[0] - 40 < rest_x < hb_wipe[2] + 40:
                warn(f'REST = {rest_x:.0f} is on their head (x {hb_wipe[0]:.0f}-{hb_wipe[2]:.0f})')
    if not peek:
        t_in = c0
    if peek and side == 'R':
        peek_x = max(160, min((hb_wipe[0] - 70) if hb_wipe else rest_x - 380, rest_x - 200))
        back = min(t_peek + .56, c0 - .12)
        path = [(t_in, OFF_R, None), (t_peek + .26, peek_x, 'power3.out'), (back, rest_x + DRIFT, 'sine.inOut'),
                (c0, rest_x, 'sine.inOut'), (c1, OFF_L, 'power3.inOut')]
    elif peek:
        path = [(t_in, OFF_R, None), (t_peek + .32, rest_x + DRIFT, 'power3.out'), (c0, rest_x, 'sine.inOut'),
                (c1, OFF_L, 'power3.inOut')]
    else:
        path = [(t_in, OFF_R, None), (c1, OFF_L, 'power3.inOut')]
    chin = hb_wipe[3] if hb_wipe else 1000
    if HANDLE_Y != 'auto':
        handle_y = int(HANDLE_Y)
    elif not lines:
        handle_y = round(min(1380, max(1000, chin + 200)))
    elif cap_y <= 1245:
        handle_y = cap_y + 160
    elif cap_y - 105 >= chin + 100:
        handle_y = cap_y - 105
    else:
        handle_y = 1400
    label_in = max(4 / FPS, t_in - .5) if LABEL_IN == 'auto' else float(LABEL_IN)
    park_b, park_a = 1080 - 48 - wb, 48
    if LABELS and hs is not None:
        hb0 = M.head_box(hs, fr(label_in), fr(t_in + .2))
        if LABEL_Y + TAG_H + 8 > hb0[1] and park_b < hb0[2] + 8:
            warn(f'the "{LABELS[0]}" tag waits top right over their head (head x to {hb0[2]:.0f}, top {hb0[1]:.0f}): later LABEL_IN, or LABELS = None')
        if LABEL_Y + TAG_H + 8 > hb_after[1] and park_a + wa > hb_after[0] - 8:
            warn(f'the "{LABELS[1]}" tag ends top left over their head (head x from {hb_after[0]:.0f}, top {hb_after[1]:.0f}): LABELS = None, or OUT earlier')

    # ---------------------------------------------------------------------------------------------- wipe layers
    xs = [path_x(path, f / FPS) for f in range(NF)]
    vs = [0.0] + [(xs[f] - xs[f - 1]) * FPS for f in range(1, NF)]
    clip, inner, line, handle, trail, tag_b, tag_a = [], [], [], [], [], [], []
    bx, ax = park_b, max(xs[0] + TAG_GAP, park_a)
    pbx, pax, rb, ra = bx, ax, 0.0, 0.0
    for f in range(NF):
        x, v = xs[f], vs[f]
        sp = min(1.0, abs(v) / 4200)
        cx = max(x, 0.0)            # the box stops at the left edge (a box at x<0 would uncover the right edge)
        clip.append({'x': cx}); inner.append({'x': -cx}); line.append({'x': x})
        handle.append({'x': x, 'scaleX': 1 + .16 * sp, 'scaleY': 1 - .07 * sp})
        trail.append({'x': x, 'scaleX': -v / 4200, 'opacity': .6 * sp})
        tb, ta = min(x - TAG_GAP - wb, park_b), max(x + TAG_GAP, park_a)
        bx = min(bx + (tb - bx) * .42, tb)     # leading tag is pushed by the line, trailing one follows on a spring
        ax = max(ax + (ta - ax) * .42, ta)
        rb += (max(-1, min(1, (bx - pbx) * FPS / 3200)) * 5 - rb) * .5
        ra += (max(-1, min(1, (ax - pax) * FPS / 3200)) * 5 - ra) * .5
        pbx, pax = bx, ax
        tag_b.append({'x': bx, 'rotation': rb, 'opacity': max(0, min(1, (bx - 5) / 40))})
        tag_a.append({'x': ax, 'rotation': ra, 'opacity': max(0, min(1, (1085 - (ax + wa)) / 40))})
    tw = (track('#aclip', clip) + track('#ainner', inner) + track('#wline', line) + track('#whandle', handle)
          + track('#wtrail', trail))
    tags_html = ''
    if LABELS:
        tw += track('#tagB', tag_b) + track('#tagA', tag_a) + [
            "gsap.set('#tagB .pill',{scale:.5,autoAlpha:0});",
            f"tl.to('#tagB .pill',{{scale:1,autoAlpha:1,duration:.38,ease:'back.out(2.2)'}},{label_in:.3f});",
            f"tl.to('#tagA .pill',{{scale:1.16,duration:.14,ease:'power2.out'}},{c1 - .02:.3f});",
            f"tl.to('#tagA .pill',{{scale:1,duration:.4,ease:'back.out(2.4)'}},{c1 + .12:.3f});"]
        if t_out is not None:
            tw += [f"tl.to('#tagA .pill',{{scale:.6,autoAlpha:0,duration:.2,ease:'power2.in'}},{t_out:.3f});"]
        tags_html = (f'\n  <div id="tagB" class="tag" style="top:{LABEL_Y}px;width:{wb}px"><div class="pill b">{LABELS[0]}</div></div>'
                     f'\n  <div id="tagA" class="tag" style="top:{LABEL_Y}px;width:{wa}px"><div class="pill a">{LABELS[1]}</div></div>')

    # ---------------------------------------------------------------------------------------------- after side
    vid = lambda i, cls, src, ti: (f'<video id="{i}" class="full{cls}" src="{src}" muted playsinline data-start="0" '
                                   f'data-media-start="0" data-duration="{DUR:.3f}" data-track-index="{ti}"></video>')
    if byo:
        ap = os.path.join(HERE, 'assets/after.mp4')
        if not os.path.exists(ap) or M.count_frames(ap) != NF:
            sys.exit(f'AFTER = {AFTER!r}: run prep_after.py first (it makes assets/after.mp4 with exactly {NF} frames)')
        after_html = '    ' + vid('afterv', '', 'assets/after.mp4', 1)
    else:
        cap_html = []
        for g, (a, b, wl) in enumerate(lines):
            spans = []
            for k, (t, txt, cls) in enumerate(wl):
                wid = f'c{g}-{k}'
                if cls == 'acc':
                    chars = ''.join(f'<span class="ch">{c}</span>' for c in txt)
                    stars = ''.join(f'<span id="{wid}s{j}" class="spk" style="right:{r}px;top:{y}px"><svg width="2" height="2">'
                                    f'<path d="{STAR}" fill="{YEL}"/></svg></span>' for j, (r, y, _, _) in enumerate(SPARKS))
                    spans.append(f'<span id="{wid}" class="lw acc">{chars}<svg class="ul" viewBox="0 0 400 34" preserveAspectRatio="none">'
                                 f'<path id="{wid}u" d="M6 20 C 70 6, 150 26, 214 14 S 340 8, 394 18" pathLength="1" fill="none" stroke="{YEL}" '
                                 f'stroke-width="9" stroke-linecap="round" stroke-dasharray="1" stroke-dashoffset="1" vector-effect="non-scaling-stroke"/></svg>{stars}</span>')
                    tw += [f"gsap.set('#{wid} .ch',{{autoAlpha:0}});",
                           f"tl.fromTo('#{wid} .ch',{{autoAlpha:0,y:46,scale:.7,rotation:-8}},{{autoAlpha:1,y:0,scale:1,rotation:0,duration:.34,"
                           f"ease:'back.out(2.6)',stagger:.028,immediateRender:false}},{t:.3f});",
                           f"tl.to('#{wid}u',{{strokeDashoffset:0,duration:.34,ease:'power2.inOut'}},{t + .2:.3f});"]
                    for j, (_, _, sc, dt) in enumerate(SPARKS):
                        tw += [f"gsap.set('#{wid}s{j}',{{autoAlpha:0,scale:0,rotation:-40}});",
                               f"tl.to('#{wid}s{j}',{{autoAlpha:1,scale:{sc},rotation:0,duration:.3,ease:'back.out(3)'}},{t + dt:.3f});",
                               f"tl.to('#{wid}s{j}',{{scale:{sc * .62:.3f},rotation:22,duration:.3,yoyo:true,repeat:5,ease:'sine.inOut'}},{t + dt + .3:.3f});"]
                else:
                    spans.append(f'<span id="{wid}" class="lw">{txt}</span>')
                    tw += [f"gsap.set('#{wid}',{{autoAlpha:0}});",
                           f"tl.fromTo('#{wid}',{{autoAlpha:0,scale:1.22,filter:'blur(22px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',"
                           f"duration:.2,ease:'power3.out',immediateRender:false}},{t:.3f});"]
            cap_html.append(f'    <div id="cl{g}" class="cl" style="top:{cap_y}px">{"".join(spans)}</div>')
            if b is not None:
                tw += [f"tl.to('#cl{g}',{{autoAlpha:0,scale:.96,filter:'blur(16px)',duration:.12,ease:'power2.in'}},{b - .12:.3f});",
                       f"tl.set('#cl{g}',{{autoAlpha:0}},{b:.3f});"]
        # the after side plays its own copy of the a-roll: two <video> tags on ONE file are merged by the renderer
        # (lint: duplicate_media_discovery_risk) and everything layered in the after box goes missing
        src_a, src_b = os.path.join(HERE, 'assets/aroll.mp4'), os.path.join(HERE, 'assets/aroll_b.mp4')
        if not os.path.exists(src_b) or os.path.getmtime(src_b) < os.path.getmtime(src_a):
            shutil.copy2(src_a, src_b)
        stage = '      ' + vid('bgv', ' g', 'assets/aroll_b.mp4', 1)
        if punch:
            stage += (f'\n      <div id="pw" style="font-size:{punch["size"]}px;top:{punch["top"]}px">{punch["text"]}</div>'
                      f'\n      <div id="cutwrap">{vid("cut", " g", "assets/subject.webm", 3)}</div>')
            tw += ["gsap.set('#pw',{autoAlpha:0});", "gsap.set('#cutwrap',{autoAlpha:0});",
                   f"tl.set('#cutwrap',{{autoAlpha:1}},{math.floor(punch['t'] * FPS) / FPS - .002:.4f});",
                   f"tl.fromTo('#pw',{{autoAlpha:0,scale:1.22,filter:'blur(22px)'}},{{autoAlpha:1,scale:1,filter:'blur(0px)',duration:.22,"
                   f"ease:'power3.out',immediateRender:false}},{punch['t']:.3f});"]
            if t_out is not None:
                tw += [f"tl.to('#pw',{{autoAlpha:0,filter:'blur(16px)',duration:.14,ease:'power2.in'}},{t_out:.3f});",
                       f"tl.set('#cutwrap',{{autoAlpha:0}},{t_out + .15:.3f});"]
        if AFTER_GRADE and AFTER_GRADE != 'none':
            tw.append(f"gsap.set('.g',{{filter:'{AFTER_GRADE}'}});")
        if PUSH and PUSH != 1:
            # the picture must not move while the line is on screen: the push-in starts when the sweep is done
            tw.append(f"tl.fromTo('#stage',{{scale:1}},{{scale:{PUSH},duration:{hold_end - c1:.3f},ease:'none',immediateRender:false}},{c1:.3f});")
            if t_out is not None:
                tw.append(f"tl.to('#stage',{{scale:1,duration:.4,ease:'power2.inOut'}},{t_out:.3f});")
        shade = '\n    <div id="dtone" class="fx"></div><div id="dvig" class="fx"></div><div id="dgrad" class="fx"></div>' if AFTER_SHADE else ''
        nl = '\n'
        after_html = f'    <div id="stage">\n{stage}\n    </div>{shade}\n{nl.join(cap_html)}'
    if t_out is not None:
        # fade a wrapper INSIDE the box: an opacity tween on #aclip itself (which carries the keyframed x) hides the
        # whole after side from frame 0 in the renderer
        tw += [f"tl.to('#afade',{{autoAlpha:0,duration:{out_len - .16:.3f},ease:'power1.inOut'}},{t_out + .14:.3f});"]

    # ---------------------------------------------------------------------------------------------- sound
    sfx = []
    if os.environ.get('SFX', '1') != '0':
        sfx = ([('whoosh-short', t_in - .02, .20)] if peek else []) + [('whoosh-short', t_commit - .12, .26)]
        acc_t = [t for _, _, wl in lines for t, _, c in wl if c == 'acc']
        if acc_t:
            sfx.append(('pop', acc_t[0], .16))
    audio, lanes = [], []
    for k, (name, t, vol) in enumerate(sorted(sfx, key=lambda s: s[1])):
        t = max(0.0, t)
        d = min(SFX_LEN[name], DUR - t)
        lane = next((i for i, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0); lane = len(lanes) - 1
        lanes[lane] = t + d
        audio.append(f'  <audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                     f'data-track-index="{10 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')

    # ---------------------------------------------------------------------------------------------- page
    origin = '540px 700px'
    if hs is not None:
        seg = sorted(hs[fr(c1):fr(hold_end) + 1], key=lambda h: h[1])
        mid = seg[len(seg) // 2]                           # the speaker's face in the typical frame of the after look
        origin = f'{(mid[0] + mid[2]) / 2:.0f}px {(mid[1] + mid[3]) / 2:.0f}px'
    safe = SAFE_GUIDE if os.environ.get('SAFE') else ''
    nl = '\n'
    html = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS.replace('ORIGIN', origin)}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(audio)}
  {vid('beforev', '', 'assets/aroll.mp4', 0)}
  <div id="aclip"><div id="ainner">
  <div id="afade">
{after_html}
  </div>
  </div></div>
  <div id="wtrail"></div>
  <div id="wline"></div>
  <div id="whandle" style="top:{handle_y - 48}px"><div class="knob"><svg viewBox="0 0 96 96" width="96" height="96">
    <path d="M40 34 L27 48 L40 62" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M56 34 L69 48 L56 62" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg></div></div>{tags_html}
{safe}
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
    open(os.path.join(HERE, 'index.html'), 'w').write(html)
    lay = dict(frames=NF, dur=DUR, mode='own file' if byo else 'made here', t_in=round(t_in, 3), peek=peek, side=side,
               rest_x=rest_x, rest=[round(path[2][0] if peek and side == 'R' else path[1][0], 3), round(c0, 3)] if peek else None,
               c0=round(c0, 3), c1=round(c1, 3), t_commit=round(t_commit, 3), t_out=None if t_out is None else round(t_out, 3),
               plain_from=None if t_out is None else round(t_out + out_len, 3), handle_y=handle_y, cap_y=cap_y, label_in=round(label_in, 3),
               head_wipe=hb_wipe, punch=punch, captions=[[round(a, 3), None if b is None else round(b, 3), ' '.join(x[1] for x in wl)] for a, b, wl in lines],
               warnings=WARN)
    os.makedirs(os.path.join(HERE, 'work'), exist_ok=True)
    json.dump(lay, open(os.path.join(HERE, 'work', 'layout.json'), 'w'), indent=1)
    # The after side only carries words from the moment the line comes in until the look eases off. fx_add.py reads
    # this and hides the reel's own captions for just that window, so every spoken word has a caption (slot seconds).
    cap_from = t_in if peek else c0
    cap_to = DUR if t_out is None else t_out
    json.dump({'hide': [[round(cap_from, 3), round(cap_to, 3)]] if lines else []},
              open(os.path.join(HERE, 'work', 'reel_captions.json'), 'w'))
    print(f"{NF} frames {DUR:.3f}s, after side: {lay['mode']}" + ('  [SAFE GUIDE ON: not for a render]' if safe else ''))
    if peek:
        print(f"line: in {t_in:.2f}s, waits at x {rest_x:.0f} ({'right' if side == 'R' else 'left'} of their head"
              + (f", head x {hb_wipe[0]:.0f}-{hb_wipe[2]:.0f}" if hb_wipe else '') + f") from {lay['rest'][0]:.2f}s, sweeps {c0:.2f}-{c1:.2f}s")
    else:
        print(f'line: one sweep {c0:.2f}-{c1:.2f}s (no peek)')
    print(f"COMMIT {t_commit:.2f}s (frame {fr(t_commit)}), handle y {handle_y}, labels {LABELS} in at {label_in:.2f}s, "
          + (f"after look eases off {t_out:.2f}s, plain from {t_out + out_len:.2f}s (frame {math.ceil((t_out + out_len) * FPS)})" if t_out is not None else 'ENDS ON A CUT (OUT = None)'))
    if lines:
        print(f'captions at y {cap_y}: ' + ' / '.join(f'{x[2]} @{x[0]:.2f}' for x in lay['captions']))
        print(f"in a reel: the reel's own captions are hidden only from {cap_from:.2f}s to {cap_to:.2f}s of the slot "
              '(fx_add.py does it by itself) and carry the words before and after that')
    else:
        print("in a reel: no caption words on the after side, so the reel's own captions stay on for the whole slot")
    if punch:
        print(f"punch word \"{punch['text']}\" {punch['size']}px, top {punch['top']}, at {punch['t']:.2f}s")
    print(f'{len(WARN)} warning(s)' if WARN else 'no warnings')


SPARKS = [(-6, -30, 1.3, .26), (-50, -78, .68, .36)]   # (right, top) off the accent word, scale, delay
STAR = 'M0 -24 C 2 -8, 8 -2, 24 0 C 8 2, 2 8, 0 24 C -2 8, -8 2, -24 0 C -8 -2, -2 -8, 0 -24 Z'
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
CSS = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
.full{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}}
#beforev,#bgv,#afterv{{z-index:0}}
#aclip{{position:absolute;left:0;top:0;width:1080px;height:1920px;overflow:hidden;z-index:1}}
#ainner,#afade{{position:absolute;left:0;top:0;width:1080px;height:1920px}}
#stage{{position:absolute;left:0;top:0;width:1080px;height:1920px;transform-origin:ORIGIN}}
#cutwrap{{position:absolute;left:0;top:0;width:1080px;height:1920px;z-index:4}}
.fx{{position:absolute;left:0;top:0;width:1080px;height:1920px;pointer-events:none;z-index:7}}
#dtone{{background:linear-gradient(180deg,rgba(20,55,75,.20),rgba(60,40,20,.10));mix-blend-mode:soft-light}}
#dvig{{background:radial-gradient(95% 62% at 50% 46%,rgba(0,0,0,0) 55%,rgba(0,0,0,.42) 100%)}}
#dgrad{{background:linear-gradient(180deg,rgba(0,0,0,.36) 0%,rgba(0,0,0,0) 24%,rgba(0,0,0,0) 56%,rgba(0,0,0,.32) 100%)}}
#pw{{position:absolute;z-index:3;left:0;right:0;text-align:center;color:#fff;font-family:'Inter Tight';font-weight:900;
  letter-spacing:-.05em;line-height:.9;white-space:nowrap;transform-origin:50% 60%;
  text-shadow:0 14px 50px rgba(0,0,0,.5),0 3px 10px rgba(0,0,0,.3)}}
.cl{{position:absolute;left:0;right:0;z-index:8;text-align:center;white-space:nowrap;
  font:800 {CAP_FS}px/.9 'Inter Tight';letter-spacing:-.04em;color:#fff;text-shadow:0 10px 40px rgba(0,0,0,.55),0 2px 8px rgba(0,0,0,.35)}}
.cl .lw{{display:inline-block;position:relative;margin:0 .1em;transform-origin:50% 60%}}
.cl .acc{{color:{YEL}}}
.cl .ch{{display:inline-block}}
.ul{{position:absolute;left:-2%;top:78px;width:104%;height:34px;overflow:visible}}
.spk{{position:absolute;width:0;height:0}}
.spk svg{{position:absolute;left:0;top:0;overflow:visible;filter:drop-shadow(0 0 12px rgba(250,230,122,.55)) drop-shadow(0 4px 10px rgba(0,0,0,.3))}}
#wtrail{{position:absolute;left:0;top:0;width:230px;height:1920px;z-index:2;transform-origin:0 50%;
  background:linear-gradient(90deg,rgba(255,248,239,.5) 0%,rgba(255,248,239,.16) 38%,rgba(255,248,239,0) 100%)}}
#wline{{position:absolute;left:-3px;top:0;width:6px;height:1920px;z-index:3;background:{CREAM};
  box-shadow:0 0 22px rgba(0,0,0,.38),-14px 0 34px rgba(0,0,0,.16)}}
#whandle{{position:absolute;left:-48px;width:96px;height:96px;z-index:4}}
.knob{{width:96px;height:96px;border-radius:50%;background:{CREAM};
  box-shadow:0 16px 40px rgba(0,0,0,.45),0 3px 10px rgba(0,0,0,.3),0 0 0 7px rgba(255,248,239,.28)}}
.knob svg{{display:block}}
.tag{{position:absolute;left:0;height:{TAG_H}px;z-index:5;transform-origin:50% 50%}}
.pill{{width:100%;height:{TAG_H}px;border-radius:29px;font:600 31px/56px Inter;letter-spacing:-.3px;text-align:center;white-space:nowrap}}
.pill.b{{background:rgba(20,22,28,.8);color:{CREAM};border:1.5px solid rgba(255,248,239,.24);box-shadow:0 12px 30px rgba(0,0,0,.35)}}
.pill.a{{background:{YEL};color:{INK};line-height:{TAG_H}px;box-shadow:0 12px 30px rgba(0,0,0,.35),0 0 30px rgba(250,230,122,.25)}}
'''

if __name__ == '__main__':
    main()
