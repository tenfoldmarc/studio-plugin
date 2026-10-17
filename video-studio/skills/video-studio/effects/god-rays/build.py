#!/usr/bin/env python3
"""god-rays, step 1: measure the clip, choose how the light sits, write work/plan.json, work/track.npz, the sounds,
index.html.

On one word the room drops (at most a stop, colour kept), a warm white source blooms behind the speaker's head and
beams fan out around the silhouette, cut by the moving outline. Rim light, a little bloom, sparse dust. Two small
lines of type pull into focus under the face. It falls away and the rest of the slot is the untouched a-roll.

  PY build.py            measure + choose + plan + index.html (prints what it chose and why)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no words (the reel's own captions carry the line)
  SFX=0                  no air / thump / hum
  GRADE=1                the dimmed room leans warm while the light is up (default off: the reel grades)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

import rays as R
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_IN = 'auto'        # the word the light opens on: a word from words.json ('changed', or 'changed#2' for its 2nd
                     # time), seconds, or 'auto' (first word of 4+ letters after 0.35 s). The onset is re-measured on the audio.
T_OUT = 'auto'       # when the light starts to fall: a word (its END is used), seconds, or 'auto' (end of the phrase
                     # 1 to 2.4 s after T_IN). Everything is gone at least 3 frames before the slot ends.
TEXT = 'auto'        # 'auto' = the T_IN word in small caps + the next words up to T_OUT in the serif line.
                     # Or a list of (text, style, when): style 'caps' / 'serif', when None (auto), a word or seconds.
                     # Only the speaker's own words. [] = no words at all.
FONT = 'Instrument Serif'      # serif line family: any family in assets/fonts/fonts.css (the buyer's caption font)
ITALIC = True                  # serif line in the italic of FONT when the slot has one
WEIGHT = 400                   # serif line weight (variable fonts follow it; a static file stays what it is)
CASE = 'as typed'              # serif line: 'as typed', 'lower', 'title', 'upper'
CAPS_FONT = 'Montserrat'       # small tracked caps line family
CAPS_WEIGHT = 500
INK = 'auto'                   # caps colour: 'auto' (cream, near-black over a bright chest band) or (r, g, b)
ACCENT = (250, 230, 122)       # serif line colour (butter yellow); the buyer's highlight colour
TEXT_Y = 'auto'                # centre y of the caps line (serif sits 76 px below): 'auto' = under the face
STRENGTH = 1.0                 # master gain on the added light (0.7 subtler, 1.2 stronger)
DIM = 'auto'                   # stops the room drops at full light: 'auto' (from the room's brightness) or 0.3 to 1.0
BEAMS = 'auto'                 # beam gain: 'auto' (from the room) or a multiplier (0.6 to 1.2)
SOURCE = 'auto'                # (dx, dy) px nudge of the light source from where build.py puts it, or 'auto'
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
GRADE = os.environ.get('GRADE', '0') not in ('0', '')
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = R.W, R.H, R.FPS
Q = 2                                                    # head measurement runs at half size

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
if not os.path.exists('assets/subject.webm'):
    sys.exit('god-rays needs the cutout (assets/subject.webm): make the slot without --no-cutout')
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg)


def decline(reason):
    sys.exit('GOD RAYS DECLINES: ' + reason)


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160                                            # 10 ms
    n = len(a) // hop
    return np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: take the rise of the loudness after the dip before the word."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    i0, i1 = max(0, int((s - 0.15) * 100)), min(len(ENVL) - 1, int((s + 0.25) * 100))
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(ENVL[i0:i1 + 1]))
    pk = ENVL[im:min(len(ENVL), int((e + 0.1) * 100)) + 1].max()
    thr = ENVL[im] + 0.35 * (pk - ENVL[im])
    for i in range(im, min(len(ENVL), int((e + 0.1) * 100))):
        if ENVL[i] >= thr:
            return i / 100.0
    return s


def find(v):
    key, nth = (v.split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    return hits[int(nth) - 1]


auto_in = next((w for w in words if w['start'] >= 0.35 and len(norm(w['text'])) >= 4), None)
if T_IN == 'auto':
    w_in = auto_in
    t_word = onset(w_in) if w_in else 0.6
    how_in = f'auto: "{w_in["text"]}" whisper {w_in["start"]:.2f}s, audio onset {t_word:.2f}s' if w_in else 'auto: 0.6s'
elif isinstance(T_IN, (int, float)):
    w_in, t_word, how_in = None, float(T_IN), 'seconds'
else:
    w_in = find(T_IN)
    t_word = onset(w_in)
    how_in = f'"{w_in["text"]}" whisper {w_in["start"]:.2f}s, audio onset {t_word:.2f}s'
t_light = t_word - 0.12                                  # the light starts just before the word lands
if t_light < 0.2:
    say(f'!! the word lands at {t_word:.2f}s: no plain frames before the light. Moved to 0.32s; start the slot earlier.')
    t_word, t_light = 0.32, 0.20
latest_out = DUR - R.FALL - 4 / FPS                      # light fully gone 4 frames before the end
if isinstance(T_OUT, (int, float)):
    t_out, how_out = float(T_OUT), 'seconds'
elif T_OUT != 'auto':
    w = find(T_OUT)
    t_out, how_out = w['end'], f'end of "{w["text"]}" {w["end"]:.2f}s'
else:
    # end of the phrase: the last word ending 1.0 to 2.4 s after the light word, preferring one followed by a pause
    cand = [(i, w) for i, w in enumerate(words) if t_word + 1.0 <= w['end'] <= min(t_word + 2.4, latest_out)]
    paused = [(i, w) for i, w in cand if i + 1 >= len(words) or words[i + 1]['start'] - w['end'] >= 0.12]
    pick = (paused or cand)
    if pick:
        w = pick[0][1] if paused else pick[-1][1]
        t_out, how_out = w['end'], f'auto: end of "{w["text"]}" {w["end"]:.2f}s'
    else:
        t_out, how_out = min(t_word + 1.6, latest_out), 'auto: 1.6s after the word'
if t_out > latest_out:
    say(f'!! T_OUT {t_out:.2f}s leaves no plain frames at the end: moved to {latest_out:.2f}s')
    t_out = latest_out
if t_out < t_light + R.RISE + 0.25:
    say(f'!! the light is up only {t_out - t_light:.2f}s (about 1.2 s reads well): start the slot earlier or make it longer')
    t_out = max(t_out, min(latest_out, t_light + R.RISE + 0.25))
t_text_out = min(t_out + 0.18, DUR - R.TEXT_FADE_OUT - 4 / FPS)
plan = dict(n=N, t_word=t_word, t_light=t_light, t_out=t_out, t_text_out=t_text_out, strength=float(STRENGTH),
            grade=GRADE)
a_on, b_on = R.light_span(plan)
b_on = min(N - 1, b_on)

# ---------------------------------------------------------------------------------------------------- measure the cutout
f0, f1 = max(0, a_on - 4), min(N - 1, b_on + 4)
alphas = list(reader('assets/subject.webm', W, H, alpha=True, first=f0, last=f1, scale=(W // Q, H // Q)))
plains = list(reader('assets/aroll.mp4', W, H, first=f0, last=f1, scale=(W // Q, H // Q)))
n_tr = min(len(alphas), len(plains))
if n_tr < f1 - f0 + 1:
    say(f'!! the cutout has fewer frames than the slot ({f0 + n_tr} of {N}): remake it (fx_new.py)')
    alphas += [alphas[-1]] * (f1 - f0 + 1 - len(alphas))
    plains += [plains[-1]] * (f1 - f0 + 1 - len(plains))


def head_of(a):
    """half-size alpha -> (top, cx, width) of the head in full-size px, or None when nobody is in the frame.
    Width is measured half a head below the top (fixed point), so shoulders and raised hands lower down do not count."""
    m = a > 128
    rows = np.where(m.sum(axis=1) >= 5)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 80.0
    cx = np.where(m[top:top + 8].any(axis=0))[0].mean()
    for _ in range(8):
        band = m[top:int(top + 0.45 * hw) + 1]
        xs = np.where(band.any(axis=0))[0]
        if len(xs) and len(xs) < 0.9 * m.shape[1]:
            cx = xs.mean()
        r = min(m.shape[0] - 1, int(top + 0.6 * hw))
        lo = int(max(0, cx - 1.3 * hw))
        xs = np.where(m[r, lo:int(cx + 1.3 * hw) + 1])[0]
        if not len(xs):
            break
        hw = max(10.0, float(xs[-1] - xs[0] + 1))
        cx = lo + (xs[0] + xs[-1]) / 2.0
    return top * Q, cx * Q, hw * Q


raw = []
for a in alphas:
    h = head_of(a)
    raw.append(h)
found = [h for h in raw if h]
if len(found) < 0.6 * len(raw):
    decline('the cutout finds nobody in most of the frames. God Rays needs a person in the shot.')
head = np.zeros((len(raw), 3))
prev = None
held = 0
for i, h in enumerate(raw):
    if h is None:
        h = prev or found[0]
    top, cx, hw = h
    r = hw / 2
    if prev is not None and not (0.82 * prev[2] / 2 < r < 1.18 * prev[2] / 2):
        r, held = prev[2] / 2, held + 1                  # a jump over 18% is a mis-read (a hand, a tilt): hold
        hw = 2 * r
    head[i] = (cx, top + 1.18 * r, r)
    prev = (top, cx, hw)
if held:
    say(f'head size held on {held} frame(s) where it jumped (a hand near the head, a tilt)')


def gsmooth(x, sig):
    k = int(sig * 3)
    w = np.exp(-0.5 * (np.arange(-k, k + 1) / sig) ** 2)
    w /= w.sum()
    return np.convolve(np.pad(x, k, mode='edge'), w, mode='valid')


for c, sig in ((0, 2.0), (1, 2.0), (2, 4.0)):
    head[:, c] = gsmooth(head[:, c], sig)

# background drift (LK flow on room pixels) for the dust
drift = np.zeros((len(raw), 2))
prev_g = prev_a = None
for i in range(len(raw)):
    g = cv2.cvtColor(plains[i], cv2.COLOR_RGB2GRAY)
    a2 = alphas[i]
    if prev_g is not None:
        mask = (cv2.dilate(prev_a, np.ones((31, 31), np.uint8)) < 8).astype(np.uint8) * 255
        pts = cv2.goodFeaturesToTrack(prev_g, 300, 0.004, 9, mask=mask)
        step = np.zeros(2)
        if pts is not None and len(pts) >= 6:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_g, g, pts, None, winSize=(41, 41), maxLevel=4)
            ok = st.ravel() == 1
            if ok.sum() >= 6:
                q = nxt[ok].reshape(-1, 2)
                p0 = pts[ok].reshape(-1, 2)
                qi = np.clip(q.round().astype(int), 0, [W // Q - 1, H // Q - 1])
                bg = a2[qi[:, 1], qi[:, 0]] < 8
                if bg.sum() >= 6:
                    step = np.median((q - p0)[bg], axis=0) * Q
        drift[i] = drift[i - 1] + step
    prev_g, prev_a = g, a2
hoff = head[:, :2] - head[0, :2]
cam = float(np.abs(np.diff(drift, axis=0)).sum(1).mean()) if len(drift) > 1 else 0.0
os.makedirs('work', exist_ok=True)
np.savez('work/track.npz', f0=f0, head=head, off=drift, hoff=hoff)

# ---------------------------------------------------------------------------------------------------- choose the variant
k_full = min(len(raw) - 1, max(0, int(round((t_light + R.RISE) * FPS)) - f0))
cx, cy, rh = (float(v) for v in head[k_full])
hw_med = float(np.median(head[:, 2])) * 2
tops = np.array([h[0] for h in found])
top5 = float(np.percentile(tops, 5))
shot = 'tight selfie' if hw_med > 330 else ('medium' if hw_med > 150 else 'wide')
if hw_med < 46:
    decline(f'the head is only {hw_med:.0f} px wide: the light would be a speck. Use a closer shot (medium or selfie).')
src_shift = [0.0, 0.0]
src_note = 'source just above the head centre (the demo)'
light_min, light_max = 60.0, 140.0
if shot == 'tight selfie':
    # a big head hides a demo-sized source completely: the source grows to 0.8 head radii (it still peeks round the
    # head) and rises to the crown, so the light shows above and beside the head instead of flooding the face
    light_max = 0.8 * hw_med / 2
    src_shift = [0.0, -0.30 * hw_med / 2]
    src_note = 'tight shot: source raised to the crown and sized to peek round the head'
if top5 < 40:
    src_shift = [0.0, 0.18 * hw_med / 2]
    src_note = 'head touches the top of the frame: source moved down to the head centre so it stays in the picture'
if SOURCE != 'auto':
    src_shift = [src_shift[0] + SOURCE[0], src_shift[1] + SOURCE[1]]
    src_note += f', nudged {SOURCE}'
rl = float(np.clip(hw_med / 2, light_min, light_max))
sx, sy = cx + R.SOURCE_OFFSET[0] * rh + src_shift[0], cy + R.SOURCE_OFFSET[1] * rh + src_shift[1]

fk = f0 + k_full
plain_full = next(reader('assets/aroll.mp4', W, H, first=fk, last=fk))
al_full = next(reader('assets/subject.webm', W, H, alpha=True, first=fk, last=fk))
luma = plain_full.astype(np.float32) @ np.float32([0.2126, 0.7152, 0.0722])
person = cv2.dilate((al_full > 20).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
dist = np.hypot(R.XF - sx, R.YF - sy)
room = (dist < 3.6 * max(rh, 90)) & ~person
L = float(np.median(luma[room])) if room.sum() > 2000 else 120.0
hot = float((luma[room] > 235).mean()) if room.sum() > 2000 else 0.0
busy = float(np.abs(luma - cv2.GaussianBlur(luma, (0, 0), 6))[room].mean()) if room.sum() > 2000 else 0.0
ring = (dist > 1.0 * rh) & (dist < 2.3 * max(rh, rl))
ring_all = np.pi * ((2.3 * max(rh, rl)) ** 2 - rh ** 2)
visible = float((ring & ~person).sum() / ring_all)
if visible < 0.12:
    decline(f'only {visible * 100:.0f}% of the space around the head is room (the speaker fills it): there is nowhere '
            'for the beams to show. Use a shot with some wall around the head.')

if L >= 120:
    dim, beams, core_k, room_kind = 1.0, 1.0, 1.0, 'bright wall'
elif L >= 75:
    dim, beams, core_k, room_kind = 0.85, 0.92, 1.0, 'mid-tone room'
else:
    dim, beams, core_k, room_kind = 0.55, 0.72, 0.85, 'dark room'
notes = []
if busy > 9 and dim < 1.0:
    dim = min(1.0, dim + 0.15)
    notes.append('busy background: the room drops a little more so the beams read over it')
if hot > 0.04:
    notes.append(f'a window or lamp near the head ({hot * 100:.0f}% of the room clips): it dims with the room, the beams '
                 'win over it')
if DIM != 'auto':
    dim = float(DIM)
if shot == 'tight selfie':
    beams, core_k = beams * 0.8, core_k * 0.7
    notes.append('tight shot: beams x0.8 and a smaller glow so the top of the frame does not go milky')
if BEAMS != 'auto':
    beams = float(BEAMS)
off_c = abs(cx - W / 2) > 140
say(f'measured: {shot} shot, head {hw_med:.0f} px wide, top y {top5:.0f}, centre x {cx:.0f}'
    f'{" (off-centre: the light follows the head)" if off_c else ""}; camera {"still" if cam < 1.5 else "drifting"} '
    f'({cam:.1f} px/frame); {visible * 100:.0f}% of the ring round the head is room')
say(f'room: {room_kind} (median {L:.0f}, texture {busy:.1f}) -> room drops {dim:.2f} stop, beams x{beams:.2f}'
    + ''.join('; ' + n for n in notes))
say(f'light: {src_note}; light scale {rl:.0f} px (the demo was 105; at least 60 so a wide shot still gets reach, '
    f'at most {light_max:.0f})')

plan.update(light_min=light_min, light_max=light_max, dim_stops=dim, ray_k=beams, core_k=core_k,
            source_shift=src_shift, shot=shot, room=room_kind)

# ---------------------------------------------------------------------------------------------------- words
FONTS_DIR = os.path.join('assets', 'fonts')
table = R.font_table(FONTS_DIR)
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
f_serif = R.pick_font(table, FONT, WEIGHT, ITALIC)
f_caps = R.pick_font(table, CAPS_FONT, CAPS_WEIGHT)


def clean(s):
    return re.sub(r'[.,!?;:"]+$', '', s.strip()).strip('"')


def cased(s):
    return {'upper': s.upper(), 'lower': s.lower(), 'title': s.title()}.get(CASE, s)


def when(v, default):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    return onset(find(v)) + 0.04


lines = []
if ENV['CAPTIONS'] and TEXT:
    if TEXT == 'auto':
        spec = []
        if w_in:
            i_in = words.index(w_in)
            spec.append((clean(w_in['text']), 'caps', None))
            rest = [w for w in words[i_in + 1:] if w['start'] < t_out + 0.05][:5]
            if rest:
                spec.append((' '.join(clean(w['text']) for w in rest), 'serif', onset(rest[0]) + 0.04))
    else:
        spec = TEXT
    t_caps = t_word + 0.02
    for text, style, wn in spec:
        if style == 'caps':
            lines.append(dict(text=text.upper(), style='caps', font=f_caps, size=31, track=0.56, t_in=when(wn, t_caps)))
        else:
            lines.append(dict(text=cased(text), style='serif', font=f_serif, size=88, track=0.0,
                              t_in=when(wn, t_caps + 0.22)))
    for ln in lines:                                     # fit the width (35 px safe sides + air)
        while R.line_mask(ln['text'], ln['font'], ln['size'], ln['track'])[1] > W - 2 * 80 and ln['size'] > 20:
            ln['size'] = int(ln['size'] * 0.92)
    chin = float(np.percentile(head[:, 1] + 1.3 * head[:, 2], 95))
    cap_y = 1198.0 if TEXT_Y == 'auto' else float(TEXT_Y)
    has_caps = any(ln['style'] == 'caps' for ln in lines)
    has_serif = any(ln['style'] == 'serif' for ln in lines)
    gap = 76 if has_caps and has_serif else 0
    if TEXT_Y == 'auto' and cap_y - 30 < chin + 50:
        cap_y = chin + 80
    if cap_y + gap + 50 > 1470:
        if has_caps and has_serif and chin + 80 + 50 <= 1470:
            lines = [ln for ln in lines if ln['style'] == 'serif']
            cap_y, gap = chin + 80, 0
            say('words: the face sits low, only the serif line fits under it (caps line left out)')
        else:
            lines = []
            say('words: left out, there is no room under the face above y 1470 (the reel captions carry the line)')
    for ln in lines:
        ln['cy'] = cap_y + (gap if ln['style'] == 'serif' else 0)
    # ink from the chest band, as it will look with the room down
    if lines:
        band = luma[int(cap_y - 30):int(cap_y + gap + 40), 140:W - 140]
        bl = float(np.percentile(band, 75)) * 2 ** (-R.SUBJ_STOPS)
        dark = INK == 'auto' and bl > 190
        ink = [26, 23, 21] if dark else ([255, 248, 239] if INK == 'auto' else list(INK))
        acc = [122, 30, 48] if dark else list(ACCENT)
        for ln in lines:
            ln['colour'] = ink if ln['style'] == 'caps' else acc
            ln['shadow'] = 0.0 if dark else 0.5
        say(f'words: {" / ".join(ln["text"] for ln in lines)}  at y {cap_y:.0f}'
            f'{" +76" if gap else ""} (chin at {chin:.0f}); '
            f'{"near-black over a bright band" if dark else "cream caps, accent serif"}; fonts '
            f'{os.path.basename(f_caps[0])}, {os.path.basename(f_serif[0])}')
        if any(ln['t_in'] > t_out for ln in lines):
            say('!! a line arrives after the light starts to fall: give it an earlier word, or a later T_OUT')
plan['text'] = lines
say(f'timing: light opens {t_light:.2f}s on {how_in}; full {t_light + R.RISE:.2f}s; falls from {t_out:.2f}s '
    f'({how_out}), gone {t_out + R.FALL:.2f}s; plain footage on frames 0 to {a_on - 1} and {b_on + 1} to {N - 1}')
json.dump(plan, open('work/plan.json', 'w'), indent=1)

# ---------------------------------------------------------------------------------------------------- sounds + index.html
cues = []
if ENV['SFX']:
    for key, (path, t, length) in R.make_sfx('assets_fx', plan).items():
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(length - skip, DUR - t)
        if d > 0.05:
            cues.append(f'  <audio id="sfx_{key}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cues)}" data-volume="1"></audio>')

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)">'
              '</div></div>')
nl = '\n'
html = f'''<!doctype html>
<html lang="en" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#000}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:#000}}
#bgv{{position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover}}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR:.3f}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="2" data-volume="1"></audio>
{nl.join(cues)}
  <video id="bgv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.set({{}}, {{}}, {DUR:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open('index.html', 'w', encoding='utf-8', newline='\n').write(html)

fl, ff = int(round(t_light * FPS)), int(round((t_light + R.RISE) * FPS))
fo = int(round(t_out * FPS))
ft = int(round(max([ln['t_in'] for ln in lines] or [t_word]) * FPS)) + 12
marks = sorted({0, fl + 4, ff, ft, fo, fo + 10, b_on + 1, N - 1} & set(range(N)))
stills = [min(N - 1, ff + 4), min(N - 1, ft), max(0, fo - 2)]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + work/track.npz + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} GRADE={int(GRADE)} SAFE={int(SAFE)}')
print(f'next: bake.py --frames {ff},{ft},{fo} -g  (preview), then bake.py')
