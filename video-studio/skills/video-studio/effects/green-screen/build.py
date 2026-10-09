#!/usr/bin/env python3
"""GREEN SCREEN: the speaker is cut out, shrunk to the bottom of the frame (left, right or centre) and the whole
frame behind them becomes the thing they are talking about: a video, a picture, or a screenshot shown as a rounded
card on a plain wallpaper. The viewer sees the subject full screen while the speaker keeps talking over it.

  IN_FRAME   the room drops away on this frame and the speaker shrinks into the pose (8 frames)
  hold       the background items play; each later item hard-cuts in on its own frame
  OUT_FRAME  the plain picture is back on this frame (the speaker grows back over the 8 frames before it)

Layers: a-roll < backgrounds (video / picture / card on wallpaper) < the cutout in its pose < credit pill < captions.
The background is YOURS: put the files in the BG_DIR folder. The effect ships no media and draws no handle unless you
type one into `credit`.

Run order (from the slot folder, see effect.md):
  python prep.py words   every spoken word with its frame            -> fill the CLIP block
  python prep.py         measures the cutout, cuts the background files, writes work/layout.json + work/layout.jpg
  python3 build.py       writes index.html   (SAFE=1 safe-zone guide, CAPTIONS=0 no caption words, SFX=0 no sounds)
  python check.py        after the render: frame count, plain edges, cut frames, contact sheet, phone copy
"""
import json
import os
import shutil
import subprocess
import sys

# ==== CLIP (edit this) ====
BG_DIR = 'bg'        # folder (inside the slot, or an absolute path) with the background material: mp4 / mov / webm
                     # video or png / jpg picture, at least one file. No file = no Green Screen.
BG = []              # one dict per background item, in the order they appear. [] = every file of BG_DIR in file-name
                     # order, evenly spaced, all with the defaults below. Keys (all optional except file):
                     #   file='name.mp4'   file inside BG_DIR
                     #   at=None           frame, or spoken word ('this', 'this#2' = second time), where this item
                     #                     cuts in. The first item always starts on IN_FRAME. None = evenly spaced
                     #   start=0.0         videos: second of the file that plays first
                     #   mode='auto'       'fill' = covers the whole frame, 'card' = rounded card on the wallpaper
                     #                     (screenshots). 'auto' = tall material fills, wide material becomes a card
                     #   side=SIDE         where the speaker stands for this item
                     #   size=SIZE         how big the speaker is for this item
                     #   reframe=None      (scale, x, y) px: slide a 'fill' item so its subject is not behind the
                     #                     speaker, e.g. (1.2, -70, -380) = 20% bigger, moved left and up
                     #   focus=(.5, .5)    which part survives the crop to 9:16: (0, 0) top left, (1, 1) bottom right
                     #   credit=CREDIT     '@handle' pill for this item
IN_FRAME = 2         # frame (or spoken word) the effect starts on. Frames before it are the untouched clip
OUT_FRAME = None     # frame (or word) the plain picture is back on. None = 2 frames before the end of the slot
HARD_IN = False      # True = the slot OPENS on the green screen (no shrink): only when the reel cuts into this slot
HARD_OUT = False     # True = the green screen stays to the last frame: only when the reel cuts away after it
SIDE = 'left'        # 'left', 'center', 'right', 'far-left', 'far-right', or the x (px) the head is centred on.
                     # Pick the side the background's subject is NOT on. work/layout.jpg shows the result
SIZE = 'normal'      # 'normal', 'small' (the background's subject needs room) or 'big'
CREDIT = ''          # '' = no pill. When the background is someone else's footage, their handle: '@name'
WALLPAPER = 'linear-gradient(160deg,#262a31 0%,#16181d 55%,#0d0e11 100%)'   # behind a card. Any CSS background
CAPS = 'auto'        # the effect's own caption words. 'auto' = lines built from words.json (what the speaker says, lowercase).
                     # [] = none. Or your own lines: [(frame or word, 'text with a *key word*'), ...]
CAP_KEY = []         # 'auto' only: words or phrases shown in yellow, e.g. ['half a million']. Only words the speaker says
CAP_FIX = {}         # 'auto' only: fix what Whisper misheard, {'heard': 'said'}; {'heard': ''} drops the word;
                     # {'in#1': 'an'} fixes only the first time that word is said in the slot
CAP_WORDS = 3        # 'auto' only: most words on one caption line
CAP_PLATE = 'auto'   # dark plate behind the caption words: 'auto' = only where the background is bright under them
                     # (measured by prep.py), True = always, False = never
BODY_BOTTOM = None   # px on the source frame: the row where the body is cut off (desk edge, table, frame bottom).
                     # None = measured from the cutout. Set it when work/layout.jpg shows a cut edge above the bottom
FACE = None          # (x0, y0, x1, y1) px on the source frame around the speaker's head (top of hair / cap to chin).
                     # None = measured. Set it when the red box in work/layout.jpg is not on the speaker's head
TRANS = 8            # frames the shrink in / grow back takes (6 to 8 reads best)
PUSH = 1.07          # slow push-in on each background over its time on screen (1.0 = none)
SHADOW = .35         # soft shadow the speaker throws on the background (0 = none)
GRADE = 'none'       # CSS filter on the cutout only, e.g. 'brightness(.94) saturate(1.05)' over a dark background
VOICE = True         # False = silent slot (no a-roll audio in the render)
SOUNDS = 'auto'      # 'auto' = a soft whoosh on the way in, on every cut and on the way out. [] = none.
                     # Or your own: [('whoosh-short', frame, base volume), ...] (stock template sounds only)
# ==== END CLIP ====

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
W, H = 1080, 1920
SIDES = {'far-left': 235, 'left': 345, 'center': 540, 'right': 735, 'far-right': 845}   # canvas x of the head centre
SIZES = {'small': (.917, 1100), 'normal': (1.0, 1065), 'big': (1.056, 1045)}   # (scale factor, head line y)
HEAD_W = 232         # px: width of the head on the canvas at SIZE 'normal' (the approved look)
HEAD_MIN = 780       # the head line may rise to here to keep the face above the bottom bar; higher = stop
FACE_MAX = 1450      # the chin stays above this (Instagram's bottom bar starts at 1470)
PAD = 8              # px the body's cut-off edge is pushed below the canvas bottom
CAP_PX, CAP_GAP = 76, 118      # caption size; distance from the caption's top to the head line below it
CARD_TOP, CARD_SIDE, CARD_R = 240, 60, 30
VIDEO_EXT = ('.mp4', '.mov', '.webm', '.m4v')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp')
ITEM_DEFAULTS = dict(file='', at=None, start=0.0, mode='auto', side=None, size=None, reframe=None, focus=(.5, .5),
                     credit=None)
SFX_GAIN = 0.75
YEL = '#FAE67A'
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')


def F(n):
    """time of frame n, nudged 2 ms early so a tl.set lands ON that frame"""
    return max(0.0, n / FPS - .002)


def clean(t):
    """a word the way captions show it: lowercase, no punctuation around it"""
    return t.lower().strip(' .,!?;:"()[]')


def signature():
    """everything prep.py's output depends on: build.py refuses to run on a layout made from other values"""
    return json.dumps([BG_DIR, BG, IN_FRAME, OUT_FRAME, HARD_IN, HARD_OUT, SIDE, SIZE, CREDIT, BODY_BOTTOM, FACE, TRANS, CAP_PLATE],
                      sort_keys=True, default=str)


def bg_folder():
    return BG_DIR if os.path.isabs(BG_DIR) else os.path.join(HERE, BG_DIR)


def bg_files():
    d = bg_folder()
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if not f.startswith('.') and f.lower().endswith(VIDEO_EXT + IMAGE_EXT))


def word_frame(ref, words, what):
    if isinstance(ref, (int, float)):
        return int(ref)
    name, _, k = str(ref).partition('#')
    hits = [w['frame'] for w in words if clean(w['text']) == clean(name)]
    k = int(k or 1)
    if len(hits) < k:
        sys.exit(f'{what}: the word "{name}" is said {len(hits)} time(s) in this slot (python prep.py words lists them). '
                 'Use a frame number instead.')
    return hits[k - 1]


def resolve(nfr, words):
    """CLIP -> (f_in, f_out, items with their frames). No media is touched here."""
    files = bg_files()
    if not files:
        sys.exit(f'No background material: put at least one video (mp4 / mov / webm) or picture (png / jpg) in '
                 f'{BG_DIR}/ inside the slot. Without material from the user there is no Green Screen: leave it out.')
    f_in = 0 if HARD_IN else word_frame(IN_FRAME, words, 'IN_FRAME')
    f_out = nfr if HARD_OUT else (nfr - 2 if OUT_FRAME is None else word_frame(OUT_FRAME, words, 'OUT_FRAME'))
    if not HARD_IN and f_in < 1:
        sys.exit('IN_FRAME must be 1 or later so frame 0 is the untouched clip (or set HARD_IN = True)')
    if not HARD_OUT and f_out > nfr - 1:
        sys.exit(f'OUT_FRAME must be {nfr - 1} or earlier so the last frame is the untouched clip (or set HARD_OUT = True)')
    if f_out - f_in < 2 * TRANS + 20:
        sys.exit(f'only {f_out - f_in} frames between IN_FRAME and OUT_FRAME: the green screen needs {2 * TRANS + 20} or more')
    items = []
    for k, spec in enumerate(BG or [dict(file=f) for f in files]):
        unknown = set(spec) - set(ITEM_DEFAULTS)
        if unknown:
            sys.exit(f'BG item {k}: unknown key(s) {sorted(unknown)}')
        it = dict(ITEM_DEFAULTS, **spec)
        if it['file'] not in files:
            sys.exit(f'BG item {k}: "{it["file"]}" is not in {BG_DIR}/ (found: {", ".join(files)})')
        it['side'] = SIDE if it['side'] is None else it['side']
        it['size'] = SIZE if it['size'] is None else it['size']
        it['credit'] = CREDIT if it['credit'] is None else it['credit']
        if it['size'] not in SIZES or not (it['side'] in SIDES or isinstance(it['side'], (int, float))):
            sys.exit(f'BG item {k}: side must be one of {list(SIDES)} or a number, size one of {list(SIZES)}')
        it['kind'] = 'video' if it['file'].lower().endswith(VIDEO_EXT) else 'image'
        it['a'] = f_in if k == 0 else (None if it['at'] is None else word_frame(it['at'], words, f'BG item {k} at'))
        items.append(it)
    # items without a frame are spread evenly between their neighbours
    known = [(i, it['a']) for i, it in enumerate(items) if it['a'] is not None] + [(len(items), f_out)]
    for (i0, a0), (i1, a1) in zip(known, known[1:]):
        for i in range(i0 + 1, i1):
            items[i]['a'] = round(a0 + (a1 - a0) * (i - i0) / (i1 - i0))
    for k, it in enumerate(items):
        it['b'] = items[k + 1]['a'] if k + 1 < len(items) else f_out
        if it['b'] - it['a'] < 12:
            sys.exit(f'BG item {k} ("{it["file"]}") is on screen for {it["b"] - it["a"]} frames (frames {it["a"]} to '
                     f'{it["b"]}): give it 12 or more, or drop it')
    return f_in, f_out, items


def pose(m, side, size):
    """where the cutout goes for one item. m = prep.py's measurement of the cutout (source px):
    top (highest point of the head over the effect), chin (lowest the chin gets), head_w, head_cx, base (the row
    the body is cut off at). Returns the transform (x, y, scale, transform-origin 0 0) and what follows from it."""
    factor, line = SIZES[size]
    s_look = factor * HEAD_W / m['head_w']
    # the cut-off edge has to be at or below the canvas bottom AND the chin above the bottom bar: that needs at least
    s_need = (H + PAD - FACE_MAX) / max(1.0, m['base'] - m['chin'])
    s = max(s_look, s_need)
    y_lo = H + PAD - s * m['base']            # lower y would show the cut-off edge
    y_hi = FACE_MAX - s * m['chin']           # higher y would put the chin in the bottom bar
    y = min(max(line - s * m['top'], y_lo), y_hi)
    head_line = y + s * m['top']
    if head_line < HEAD_MIN:
        sys.exit(f'This shot is too tight for Green Screen: only {m["base"] - m["chin"]:.0f} px of body show below the '
                 f'chin, so keeping the face above y 1470 and the cut-off body edge off screen would put the head at '
                 f'y {head_line:.0f} and hide the background. Use a wider take, or leave the effect out.')
    cx = SIDES.get(side, side)
    x = cx - s * m['head_cx']
    box = [max(0, round(x + s * m['x0'])), round(head_line), min(W, round(x + s * m['x1'])), H]
    face = [round(cx - s * m['head_w'] / 2), round(head_line), round(cx + s * m['head_w'] / 2), round(y + s * m['chin'])]
    cap_top = round(head_line - CAP_GAP)
    far = side in ('far-left', 'far-right') or (isinstance(side, (int, float)) and not 300 <= side <= 780)
    cap_box = [35, W - 35] if not far else ([35, 600] if cx < W / 2 else [W - 600, W - 35])
    notes = []
    if s > s_look * 1.02:
        notes.append(f'speaker {s / s_look:.2f}x bigger than the look so the cut-off body edge stays off screen')
    if s > 1.3:
        notes.append(f'the cutout is enlarged {s:.2f}x and will look soft: a closer take is better')
    if (m['edge_l'] and x > 2) or (m['edge_r'] and x + s * W < W - 2):
        notes.append('the speaker\'s body touches the side of the source frame and that straight edge shows: use side '
                     + ("'left' / 'far-left'" if m['edge_l'] else "'right' / 'far-right'"))
    return dict(x=round(x, 1), y=round(y, 1), s=round(s, 4), cx=cx, head_line=round(head_line), box=box, face=face,
                cap_top=cap_top, cap_bottom=cap_top + CAP_PX, cap_box=cap_box, notes=notes)


def card_rect(aspect, cap_top, credit):
    """a card (w / h = aspect) in the top zone: under the safe top (and the credit pill), above the caption line"""
    top = CARD_TOP + (72 if credit else 0)
    zone_w, zone_h = W - 2 * CARD_SIDE, cap_top - 34 - top
    if zone_h < 240:
        sys.exit('no room for a card above the caption line: use mode="fill" for this item')
    w = min(zone_w, zone_h * aspect)
    h = w / aspect
    return [round((W - w) / 2), round(top + (zone_h - h) / 2), round(w), round(h)]


def probe(path, entries):
    ffp = shutil.which('ffprobe') or 'ffprobe'
    return subprocess.run([ffp, '-v', 'error', '-show_entries', entries, '-of', 'csv=p=0', path],
                          capture_output=True, text=True).stdout.strip()


def sounds(L):
    if SOUNDS != 'auto':
        return list(SOUNDS)
    out = [] if HARD_IN else [('whoosh-short', L['f_in'] - 2, .20)]
    out += [('whoosh-short', it['a'] - 2, .16) for it in L['items'][1:]]
    return out + ([] if HARD_OUT else [('whoosh-short', L['f_out'] - TRANS - 1, .14)])


def audio(L, dur):
    if os.environ.get('SFX') == '0':
        return []
    out, lanes = [], []
    for k, (name, frame, vol) in enumerate(sorted(sounds(L), key=lambda x: x[1])):
        path = next((p for p in (f'assets/sfx/{name}.mp3', f'assets_fx/{name}.mp3') if os.path.exists(p)), None)
        if not path:
            print(f'  (sound {name} not found in assets/sfx: skipped)')
            continue
        t = F(max(0, frame))
        if t >= dur - .05:
            continue
        d = min(float(probe(path, 'format=duration')), dur - t)
        lane = next((j for j, end in enumerate(lanes) if end <= t), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = t + d
        out.append(f'<audio id="sfx{k}" src="{path}" data-start="{t:.3f}" data-duration="{d:.3f}" '
                   f'data-track-index="{20 + lane}" data-volume="{vol * SFX_GAIN:.3f}"></audio>')
    return out


def caption_lines(L):
    """-> [(item index, [(frame, word, is key), ...]), ...] one entry per caption line"""
    words = [w for w in L['words'] if L['f_in'] <= w['frame'] < L['f_out'] - 4]
    item_of = lambda f: max(k for k, it in enumerate(L['items']) if it['a'] <= f)
    lines = []
    if CAPS == 'auto':
        toks, seen = [], {}
        for w in L['words']:
            c = clean(w['text'])
            seen[c] = seen.get(c, 0) + 1
            t = CAP_FIX.get(f'{c}#{seen[c]}', CAP_FIX.get(c, c))
            if t and w in words:
                toks.append(dict(frame=w['frame'], text=t, end=w['text'].rstrip()[-1:] in '.,!?', item=item_of(w['frame'])))
        keys = set()
        joined = [t['text'] for t in toks]
        for phrase in CAP_KEY:
            p = [clean(x) for x in phrase.split()]
            keys.update(i + j for i in range(len(joined) - len(p) + 1) if joined[i:i + len(p)] == p for j in range(len(p)))
        cur = []
        for i, t in enumerate(toks):
            box = L['items'][t['item']]['pose']['cap_box']
            room = int((box[1] - box[0]) / (CAP_PX * .47))
            prev = toks[i - 1] if cur else None
            if prev and (len(cur) >= CAP_WORDS or prev['end'] or prev['item'] != t['item'] or t['frame'] - prev['frame'] > 20
                         or len(' '.join(x[1] for x in cur)) + 1 + len(t['text']) > room):
                lines.append((prev['item'], cur))
                cur = []
            cur.append((t['frame'], t['text'], i in keys))
        if cur:
            lines.append((toks[-1]['item'], cur))
    else:
        marks = [word_frame(at, L['words'], 'CAPS') for at, _ in CAPS] + [L['f_out']]
        for (at, text), f0, f1 in zip(CAPS, marks, marks[1:]):
            said = [w['frame'] for w in words if f0 <= w['frame'] < f1] or [f0]
            toks, key = [], False
            for raw in text.split(' '):
                key = key or raw.startswith('*')
                toks.append((raw.strip('*'), key))
                key = key and not raw.endswith('*')
            line = [(max(f0, said[min(len(said) - 1, i * len(said) // len(toks))]), t, k) for i, (t, k) in enumerate(toks)]
            lines.append((item_of(f0), line))
    return lines


def captions(L, dur):
    html, pre, tw = [], [], []
    if os.environ.get('CAPTIONS') == '0' or not CAPS:
        return html, pre, tw
    lines = caption_lines(L)
    for g, (k, line) in enumerate(lines):
        p = L['items'][k]['pose']
        x0, x1 = p['cap_box']
        size = min(CAP_PX, int((x1 - x0) / (len(' '.join(t for _, t, _ in line)) * .47)))
        t0 = max(F(line[0][0]) - .032, F(L['items'][k]['a']))     # never before its own background is up
        end = min(F(line[-1][0]) + 1.0, F(L['items'][k]['b']), F(L['f_out'] - (0 if HARD_OUT else TRANS - 2)))
        if g + 1 < len(lines):
            end = min(end, max(F(lines[g + 1][1][0][0]) - .032, t0 + .1))
        spans = ' '.join(f'<span class="cw{" y" if key else ""}" id="c{g}_{i}">{t}</span>' for i, (_, t, key) in enumerate(line))
        plate = ' plate' if L['items'][k].get('plate') else ''
        html.append(f'<div class="cap{plate}" id="cg{g}" style="left:{x0}px;width:{x1 - x0}px;top:{p["cap_top"]}px;'
                    f'font-size:{size}px"><span class="ln">{spans}</span></div>')
        pre.append(f"gsap.set('#cg{g}',{{autoAlpha:0}});")
        tw.append(f"tl.set('#cg{g}',{{autoAlpha:1}},{t0:.3f});")
        last = t0
        for i, (frame, _, _) in enumerate(line):
            last = max(F(frame) - .032, last + (.04 if i else 0))
            pre.append(f"gsap.set('#c{g}_{i}',{{autoAlpha:0}});")
            tw.append(f"tl.fromTo('#c{g}_{i}',{{autoAlpha:0,scale:1.22,filter:'blur(12px)'}},{{autoAlpha:1,scale:1,"
                      f"filter:'blur(0px)',duration:.17,ease:'power3.out',immediateRender:false}},{last:.3f});")
        if end < dur - .01:
            tw.append(f"tl.set('#cg{g}',{{autoAlpha:0}},{end:.3f});")
    return html, pre, tw


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    dur = nfr / FPS - .001      # 1 ms short on purpose: the renderer rounds the length UP to whole frames
    if not bg_files():
        resolve(nfr, [])        # stops with the "no material" message
    if not os.path.exists('work/layout.json'):
        sys.exit('work/layout.json is missing: run prep.py first (see effect.md)')
    L = json.load(open('work/layout.json'))
    if L['frames'] != nfr or L['sig'] != signature():
        sys.exit('the CLIP block (or the clip) changed since prep.py ran: run prep.py again, then build.py')
    f_in, f_out, items, T = L['f_in'], L['f_out'], L['items'], TRANS
    pre, tw, bgs, over = [], [], [], []

    def show(sel, f0, f1):
        pre.append(f"gsap.set('{sel}',{{autoAlpha:{1 if f0 <= 0 else 0}}});")
        if f0 > 0:
            tw.append(f"tl.set('{sel}',{{autoAlpha:1}},{F(f0):.3f});")
        if f1 < nfr:
            tw.append(f"tl.set('{sel}',{{autoAlpha:0}},{F(f1):.3f});")

    for k, it in enumerate(items):
        a, b = it['a'], it['b']
        start = int(a / FPS * 1000) / 1000                      # floored to the millisecond
        d = min((b - a) / FPS, dur - start)
        vid = (f'muted playsinline data-start="{start:.3f}" data-media-start="0" data-duration="{d:.3f}" '
               f'data-track-index="{3 + k}"')
        if it['mode'] == 'card':
            l, t, w, h = it['card']
            media = (f'<video id="bgv{k}" src="{it["src"]}" {vid}></video>' if it['kind'] == 'video'
                     else f'<img id="bgi{k}" src="{it["src"]}" alt="" />')
            inner = (f'<div class="wall"></div><div class="push" id="p{k}"><div class="card" id="card{k}" '
                     f'style="left:{l}px;top:{t}px;width:{w}px;height:{h}px">{media}</div></div>')
            tw.append(f"tl.fromTo('#card{k}',{{y:46,scale:.95}},{{y:0,scale:1,duration:.36,ease:'power3.out',immediateRender:false}},{F(a):.3f});")
            grow = 1 + (PUSH - 1) * .45
        else:
            media = (f'<video id="bgv{k}" class="full" src="{it["src"]}" {vid}></video>' if it['kind'] == 'video'
                     else f'<img id="bgi{k}" class="full" src="{it["src"]}" alt="" />')
            rf = it.get('reframe')
            if rf:
                media = f'<div class="rf" style="transform:translate({rf[1]}px,{rf[2]}px) scale({rf[0]})">{media}</div>'
            inner = f'<div class="push" id="p{k}">{media}</div>'
            grow = PUSH
        bgs.append(f'<div class="bgw" id="w{k}">{inner}</div>')
        if k:       # a later item simply covers the ones before it; #stage shows and hides the whole stack
            show(f'#w{k}', a, nfr)
        if grow != 1:
            tw.append(f"tl.fromTo('#p{k}',{{scale:1}},{{scale:{grow:.4f},duration:{(b - a) / FPS:.3f},ease:'none',immediateRender:false}},{F(a):.3f});")
        if it['credit']:
            over.append(f'<div class="pill" id="pill{k}">{it["credit"]}</div>')
            show(f'#pill{k}', a + (0 if k or HARD_IN else T // 2), b - (0 if k + 1 < len(items) or HARD_OUT else T))
        p = it['pose']
        here = f"{{x:{p['x']},y:{p['y']},scale:{p['s']}}}"
        if k == 0 and HARD_IN:
            pre.append(f"gsap.set('#pose',{here});")
        elif k == 0:
            # one frame of lead: on IN_FRAME itself the speaker is already a third of the way into the pose
            t0 = max(0.0, (a - 1) / FPS)
            pre.append("gsap.set('#pose',{x:0,y:0,scale:1});")
            tw.append(f"tl.fromTo('#pose',{{x:0,y:0,scale:1}},{{x:{p['x']},y:{p['y']},scale:{p['s']},duration:{T / FPS:.4f},"
                      f"ease:'power3.out',immediateRender:false}},{t0:.4f});")
            tw.append(f"tl.fromTo('#bgall',{{scale:1.12,filter:'blur(14px)'}},{{scale:1,filter:'blur(0px)',duration:{T / FPS:.4f},"
                      f"ease:'power2.out',immediateRender:false}},{t0:.4f});")
            tw.append(f"tl.set('#bgall',{{filter:'none'}},{t0 + T / FPS + .01:.4f});")
        else:
            tw.append(f"tl.set('#pose',{here},{F(a):.3f});")
            tw.append(f"tl.fromTo('#stage',{{scale:1.045}},{{scale:1,duration:.3,ease:'power2.out',immediateRender:false}},{F(a):.3f});")
    if not HARD_OUT:
        p = items[-1]['pose']
        t1 = F(f_out) - T / FPS
        tw.append(f"tl.fromTo('#pose',{{x:{p['x']},y:{p['y']},scale:{p['s']}}},{{x:0,y:0,scale:1,duration:{T / FPS:.4f},"
                  f"ease:'power3.in',immediateRender:false}},{t1:.4f});")
        tw.append(f"tl.fromTo('#bgall',{{scale:1,filter:'blur(0px)'}},{{scale:1.12,filter:'blur(14px)',duration:{T / FPS:.4f},"
                  f"ease:'power2.in',immediateRender:false}},{t1:.4f});")
    show('#stage', f_in, f_out)
    c_html, c_pre, c_tw = captions(L, dur)
    shadow = f'filter:drop-shadow(0 10px 34px rgba(0,0,0,{SHADOW}));' if SHADOW else ''
    grade = '' if GRADE in ('', 'none', None) else f'filter:{GRADE};'
    css = f'''
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:#000}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#000}}
.full{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;object-fit:cover}}
#stage{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;z-index:2;overflow:hidden;transform-origin:50% 45%}}
#bgall{{position:absolute;inset:0;transform-origin:50% 45%;background:#000}}
.bgw{{position:absolute;inset:0;overflow:hidden;background:#000}}
.push{{position:absolute;inset:0;transform-origin:50% 40%}}
.rf{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;transform-origin:0 0}}
.wall{{position:absolute;inset:0;background:{WALLPAPER}}}
.card{{position:absolute;border-radius:{CARD_R}px;overflow:hidden;background:#15171b;transform-origin:50% 40%;
  box-shadow:0 40px 90px rgba(0,0,0,.55),0 6px 22px rgba(0,0,0,.35)}}
.card img,.card video{{display:block;width:100%;height:100%;object-fit:cover}}
#cutw{{position:absolute;inset:0;{shadow}}}
#pose{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;transform-origin:0 0;{grade}}}
.pill{{position:absolute;left:60px;top:250px;z-index:6;padding:11px 22px 12px;border-radius:99px;background:rgba(10,10,12,.72);
  color:#fff;font:600 30px Inter;letter-spacing:-.3px;white-space:nowrap}}
.cap{{position:absolute;z-index:7;text-align:center;font-family:'Inter Tight';font-weight:800;letter-spacing:-.04em;line-height:1;
  color:#fff;white-space:nowrap;text-shadow:0 4px 22px rgba(0,0,0,.8),0 1px 4px rgba(0,0,0,.7)}}
.cap .ln{{display:inline-block}}
.cap.plate{{text-shadow:none;margin-top:-10px}}
.cap.plate .cw{{background:#0d0d10;padding:10px 16px 16px;margin:0 -16px;border-radius:20px}}
.cap .cw{{display:inline-block;transform-origin:50% 60%}}
.cap .y{{color:{YEL}}}
'''
    nl = '\n'
    voice = (f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.3f}" '
             f'data-track-index="2" data-volume="1"></audio>') if VOICE else ''
    page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.3f}" data-width="{W}" data-height="{H}">
  {voice}
{nl.join(audio(L, dur))}
  <video id="aroll" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
  <div id="stage">
    <div id="bgall">
{nl.join(bgs)}
    </div>
    <div id="cutw"><div id="pose"><video id="cut" class="full" src="assets/subject.webm" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.3f}" data-track-index="1"></video></div></div>
  </div>
{nl.join(over)}
{nl.join(c_html)}
{SAFE_GUIDE if os.environ.get('SAFE') == '1' else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{nl.join(pre + c_pre)}
{nl.join(tw + c_tw)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
    open('index.html', 'w').write(page)
    own = bool(c_html)
    print(f'wrote index.html  {nfr} frames ({dur:.3f}s)  green screen f{f_in}..f{f_out}'
          f'{"  HARD IN" if HARD_IN else ""}{"  HARD OUT" if HARD_OUT else ""}  captions: '
          + ('the effect\'s own' if own else 'none drawn (the reel captions this slot: use the caption line below)'))
    for k, it in enumerate(items):
        p = it['pose']
        print(f'  item {k}  f{it["a"]}..f{it["b"]}  {it["file"]}  {it["mode"]}  speaker box x {p["box"][0]}..{p["box"][2]} '
              f'y {p["box"][1]}..{H}  face y {p["face"][1]}..{p["face"][3]}  caption line y {p["cap_top"]}..{p["cap_bottom"]} '
              f'x {p["cap_box"][0]}..{p["cap_box"][1]}' + ''.join(f'\n     !! {n}' for n in p['notes']))
    if not own:
        # In a reel the buyer's own captions stay on, in their style. The speaker is shrunk to the bottom, so the
        # captions move up to the line this layout keeps free above the head (36 px higher than the effect's own
        # line, so a caption with a plate behind it still clears the head).
        cy = max(236, min(int(it['pose']['cap_top']) for it in items) - 36)
        print(f"  reel captions: this effect's own words are off. Add the slot with fx_add.py --caption-y {cy} "
              "(the reel's captions move to the line above the speaker's head), then check one reel snapshot inside the slot")
    snaps = sorted({f_in + 1, f_in + TRANS + 4, f_out - TRANS - 4, f_out - 2} | {it['a'] + 6 for it in items[1:]}
                   | {(it['a'] + it['b']) // 2 for it in items})
    print('snapshot times: ' + ','.join(f'{(n + .5) / FPS:.3f}' for n in snaps if 0 <= n < nfr))
    print(f'render to renders/{os.path.basename(HERE)}.mp4')


if __name__ == '__main__':
    main()
