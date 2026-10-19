"""Shared machinery for the six text-graphic effects from the Viral Guy look (Depth Scatter, Stat Stack, Dot Counter,
Chip Row, Prompt Box, Serif Flow). Each effect folder ships its own copy of this file, so a slot needs nothing else.

What it gives a build.py:
  Slot          the slot's facts: frames, seconds, words (slot seconds), where the face is and where graphics may go
  Page          collects html / css / timeline lines / sounds and writes index.html (the slot's own footage under it)
  style_css()   the STYLE block as css rules (.vg-word, .vg-big, .vg-small, .vg-serif)
  T(sec)        a time snapped onto the 30 fps frame grid, 2 ms early so a hard set lands ON that frame

No cutout, no extra Python packages. Placement comes from the reel's layout.json (scripts/layout.py) when the slot
was made inside a reel project; on a loose clip it falls back to the chest band and says so.
"""
import html
import json
import os
import re
import sys

FPS = 30
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE, SAFE_RIGHT, SAFE_RIGHT_FROM = 220, 1470, 35, 100, 1155
SAFE_MARK = 'rgba(255,0,0,.28)'
SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)"></div></div>')
# stock sounds the slot gets from setup: how long each one is worth playing, and how early its hit sits in the file
SFX_LEN = {'click-soft': .25, 'pop': .4, 'key-press': .2, 'whoosh-short': .8, 'typing': 1.6}
SFX_LEAD = {'click-soft': .01, 'pop': .118, 'key-press': .01, 'whoosh-short': .12, 'typing': 0}


def env(name, default='1'):
    return os.environ.get(name, default)


SAFE = env('SAFE', '0') == '1'
SFX_ON = env('SFX', '1') != '0'
# The final build is transparent graphics only: the reel lays it over its own footage (slot.json "layer": "overlay").
# SAFE=1 or PREVIEW=1 puts the slot's footage under it, to judge the snapshots.
PREVIEW = SAFE or env('PREVIEW', '0') == '1'


def T(t):
    return max(0.0, round(t * FPS) / FPS - .002)


def esc(s):
    return html.escape(str(s), quote=False).replace("'", '&rsquo;')


def cased(text, case):
    if case == 'lower':
        return text.lower()
    if case == 'upper':
        return text.upper()
    return text


def bare(s):
    return s.strip().rstrip(',.;:!?')


def die(msg):
    """a plain one-line reason the editing Claude can pass on to the buyer, then stop"""
    print('DECLINED: ' + msg)
    sys.exit(2)


class Slot:
    """Everything this slot knows: run from the slot folder."""

    def __init__(self):
        here = os.getcwd()
        self.clip = _json(os.path.join(here, 'clip.json'), {})
        n = int(self.clip.get('frames') or 0)
        if not n:
            die('clip.json is missing or has no frame count: make the slot with fx_new.py first')
        self.frames, self.dur = n, n / FPS
        ws = _json(os.path.join(here, 'words.json'), [])
        ws = ws.get('words', ws) if isinstance(ws, dict) else ws
        self.words = [dict(w, text=w.get('text', w.get('word', '')).strip()) for w in ws if w.get('text', w.get('word', '')).strip()]
        self.layout, self.layout_from = self._layout()
        head = (self.layout or {}).get('head') or {}
        bands = (self.layout or {}).get('bands') or {}
        self.chin = int(head.get('chin_max') or head.get('chin') or 760)
        self.head_top = int(head.get('top_min') or head.get('top') or 452)
        self.cx = int(head.get('cx') or 540)
        self.chest = int(bands.get('Y_CHEST') or 1170)       # top of a one-line caption over the chest
        self.shot = (self.layout or {}).get('shot') or 'unknown'
        self.t0 = float(self.clip.get('in') or 0)          # reel seconds of the slot's first frame
        # the face in THIS slot's shots: layout.json measures every segment of the reel (punch-ins move the head)
        segs = [g for g in (self.layout or {}).get('segments') or []
                if g.get('t1', 0) > self.t0 + .02 and g.get('t0', 0) < self.t0 + self.dur - .02 and g.get('chin')]
        if segs:
            self.chin = max(int(g['chin']) for g in segs)
            self.head_top = min(int(g.get('head_top') or self.head_top) for g in segs)
            self.cx = int(sum(int(g.get('cx') or self.cx) for g in segs) / len(segs))

    def hide_hint(self, wins):
        """The reel's captions are hidden only while this effect's own words are up: written to
        work/reel_captions.json (slot seconds), which fx_add.py reads by itself."""
        wins = [[round(max(0.0, a), 3), round(min(b, self.dur), 3)] for a, b in wins if b > a]
        os.makedirs('work', exist_ok=True)
        with open(os.path.join('work', 'reel_captions.json'), 'w', encoding='utf-8') as fh:
            json.dump({'hide': wins}, fh)
        print('in a reel: the reel\'s captions are hidden for ' + ', '.join(f'{self.t0 + a:.2f} to {self.t0 + b:.2f}s' for a, b in wins)
              + ' (work/reel_captions.json, fx_add.py applies it)')

    def _layout(self):
        proj = self.clip.get('project')
        for p in ([os.path.join(proj, 'layout.json')] if proj else []) + ['layout.json']:
            if os.path.isfile(p):
                return _json(p, None), p
        return None, None

    def where(self):
        if self.layout_from:
            return f'placement: from {os.path.relpath(self.layout_from)} ({self.shot} shot, chin at y {self.chin}, chest band y {self.chest})'
        return 'placement: no layout.json found, so the chest band default (y 1170) is used: check a SAFE=1 snapshot'

    def band(self, height, prefer=None):
        """centre y for a graphic `height` px tall: on the chest band, never over the chin, never past y 1470.
        A close-up with no room under the chin gets the space above the head instead; None = no room anywhere."""
        if prefer is not None:
            return int(prefer)
        y = max(self.chest + 40, self.chin + 60 + height / 2)
        if y + height / 2 > SAFE_BOTTOM - 6:
            y = SAFE_BOTTOM - 6 - height / 2
        if y - height / 2 >= self.chin + 20:
            return int(y)
        up = self.head_top - 50 - height / 2              # above the head, clear of the top of the safe zone
        if up - height / 2 >= SAFE_TOP + 10:
            print(f'placement: no room under the chin on this clip, so it sits above the head (y {int(up)})')
            return int(up)
        return None

    def word_list(self):
        return ' '.join(f"{w['text']}@{w['start']:.2f}" for w in self.words)

    def find(self, pattern, after=0.0):
        """first word (from `after` seconds on) whose text matches the regex"""
        rx = re.compile(pattern, re.I)
        return next((w for w in self.words if w['start'] >= after - .01 and rx.search(bare(w['text']))), None)


def _json(path, fallback):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def style_css(S):
    """the STYLE block as css: one place where the buyer's look goes in"""
    shadow = 'text-shadow:0 2px 18px rgba(0,0,0,.38);' if S.get('shadow', True) else ''
    ital = 'italic' if S.get('serif_italic', True) else 'normal'
    return f'''
.vg-word{{font-family:'{S["font"]}';font-weight:{S["weight"]};letter-spacing:{S["tracking"]}em;color:{S["ink"]};{shadow}line-height:1;white-space:nowrap}}
.vg-big{{font-family:'{S["font"]}';font-weight:{S["big_weight"]};letter-spacing:{S["big_tracking"]}em;color:{S.get("accent") or S["ink"]};{shadow}line-height:.86;white-space:nowrap}}
.vg-small{{font-family:'{S["small_font"]}';font-weight:{S["small_weight"]};color:{S["ink"]};{shadow}line-height:1.1;white-space:nowrap}}
.vg-serif{{font-family:'{S["serif_font"]}';font-style:{ital};font-weight:400;color:{S["ink"]};{shadow}line-height:1;white-space:pre}}'''


class Page:
    def __init__(self, slot):
        self.s = slot
        self.css, self.html, self.js, self.hidden, self.sfx = [], [], [], [], []
        self.n = 0

    def nid(self, p='e'):
        self.n += 1
        return f'{p}{self.n}'

    # hard cuts, the way the look does it
    def show(self, sel, t_in, t_out=None):
        self.hidden.append(sel)
        self.js.append(f"tl.set('{sel}',{{autoAlpha:1}},{T(t_in):.3f});")
        if t_out is not None and t_out < self.s.dur - .02:
            self.js.append(f"tl.set('{sel}',{{autoAlpha:0}},{T(t_out):.3f});")

    def enter(self, sel, t_in, frm, to, dur, ease='power2.out', t_out=None):
        self.hidden.append(sel)
        self.js.append(f"tl.fromTo('{sel}',{json.dumps(dict(autoAlpha=0, **frm))},"
                       f"{json.dumps(dict(autoAlpha=1, duration=dur, ease=ease, immediateRender=False, **to))},{T(t_in):.3f});")
        if t_out is not None and t_out < self.s.dur - .02:
            self.js.append(f"tl.set('{sel}',{{autoAlpha:0}},{T(t_out):.3f});")

    def sound(self, name, at, vol=.35):
        if SFX_ON and os.path.exists(f'assets/sfx/{name}.mp3'):
            self.sfx.append((name, at, vol))

    def write(self, gain=1.0):
        dur = self.s.dur
        audio, lanes = [], []
        for k, (name, hit, vol) in enumerate(sorted(self.sfx, key=lambda x: x[1])):
            t = max(0.0, hit - SFX_LEAD.get(name, 0))
            d = min(SFX_LEN.get(name, .5), dur - t)
            if d < .08:
                continue
            lane = next((i for i, end in enumerate(lanes) if end <= t), None)
            if lane is None:
                lanes.append(0)
                lane = len(lanes) - 1
            lanes[lane] = t + d
            audio.append(f'<audio id="sfx{k}" src="assets/sfx/{name}.mp3" data-start="{t:.3f}" data-duration="{d:.3f}" '
                         f'data-track-index="{10 + lane}" data-volume="{vol * gain:.3f}"></audio>')
        footage = ('' if not PREVIEW else
                   f'<audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{dur:.4f}" data-track-index="2" data-volume="1"></audio>\n'
                   f'  <video id="bgv" class="full" src="assets/aroll.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{dur:.4f}" data-track-index="0"></video>')
        hide = f"gsap.set({json.dumps(sorted(set(self.hidden)))}.join(','),{{autoAlpha:0}});" if self.hidden else ''
        page = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<link rel="stylesheet" href="assets/fonts/fonts.css" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:{'#000' if PREVIEW else 'transparent'}}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden}}
.full{{position:absolute;left:0;top:0;width:1080px;height:1920px;object-fit:cover}}
#fx{{position:absolute;inset:0;z-index:5;pointer-events:none}}
{''.join(self.css)}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur:.4f}" data-width="1080" data-height="1920">
  {footage}
  {chr(10).join(audio)}
  <div id="fx">
  {chr(10).join(self.html)}
  </div>
  {SAFE_GUIDE if SAFE else ''}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{hide}
{chr(10).join(self.js)}
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
        with open('index.html', 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(page)
        print(f'index.html written: {self.s.frames} frames ({dur:.2f}s), {len(audio)} sound(s), '
              + ('footage under it, SAFE guide ON (snapshots only)' if SAFE else 'footage under it (PREVIEW=1, snapshots only)' if PREVIEW
                 else 'transparent graphics only (the final build: hf render makes a .webm the reel lays over its own footage)'))
