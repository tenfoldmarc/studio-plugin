#!/usr/bin/env python3
"""code-scan, step 1: measure the clip, time the code beat, place the terminal card, write work/plan.json, the two
order fields, the four sounds and index.html.

The picture resolves into readable code (the room in dim slate glyphs, the speaker as a brighter figure of tokens),
a small terminal card types two short lines, and the picture resolves back.

  PY build.py            measure + plan + sounds + index.html (prints what it measured and what it chose)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             no terminal card (the reel's captions carry the words); the code look stays
  SFX=0                  no sounds
  GRADE=1                a deeper vignette inside the code beat (default off; outside the beat nothing is graded)
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

import scan as S
from fxio import FF, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_IN = 'auto'        # the print front starts on this word ('drop', or 'drop#2' for its 2nd time), seconds, or 'auto'
                     # (the first word after 0.5 s). Re-measured on the audio; the code has landed IN_DUR later.
T_OUT = 'auto'       # the picture is fully back by this word's onset (a word or seconds), or 'auto' (HOLD after landing)
HOLD = 1.7           # seconds the full code look holds when T_OUT is 'auto' (1.4 to 2.0 lets the card type and read)
IN_DUR = 0.55        # seconds the print front takes to cover the frame (0.45 to 0.6 reads deliberate, not jumpy)
OUT_DUR = 0.50       # seconds back to the plain picture
PROMPT = '> '        # what the card's first line starts with
LINE1 = 'edit it'    # the card's typed line: a few of the speaker's own words, lower case reads as a command. Never a
                     # product, app or person's name unless the buyer asks for it.
LINE2 = 'done'       # the line that pops in with a check mark when the typing ends ('' for none)
FONT = 'JetBrains Mono'   # card font: any family in assets/fonts/fonts.css (the buyer's caption font works)
WEIGHT = 500         # card font weight (variable fonts follow it; a static file stays what it is)
CASE = 'as typed'    # card lines: 'as typed', 'upper', 'lower', 'title'
CODE_FONT = 'JetBrains Mono'  # the glyphs the picture is drawn in (a monospace face keeps the code readable)
CODE_WEIGHT = 500
INK = (255, 248, 239)         # the speaker's tokens and the card text (cream); the buyer's text colour works
ACCENT = (250, 230, 122)      # accent tokens, his outline, the prompt and check mark (butter); the buyer's highlight
ROOM_INK = (124, 135, 158)    # the room's glyphs (slate)
BACKDROP = (20, 22, 28)       # the code world's background (near black slate)
TOKENS = ['cut', 'trim', 'caption', 'zoom', 'render', 'clip', 'edit', 'pace', 'export', 'sound', 'hook', 'frame']
                     # the words the code is written in: the topic of the line works best (lower case, 3 to 8 letters)
ACCENT_WORDS = ['render', 'edit']   # tokens always drawn in ACCENT inside the speaker
TERM_CENTRE = 'auto' # (x, y) of the card in 1080x1920 px; 'auto' = below the chin, else beside or above the head
TERM_SCALE = 'auto'  # card size factor; 'auto' = 1.0, smaller only when the lines are long
SHOT = 'auto'        # 'auto' (from the head width), or force 'close' / 'medium' / 'wide' / 'none' (no person)
FACE_BLEND = 0.26    # how much of the real face shows through the head glyphs (0.15 to 0.35)
GLINT = 1.0          # light on the print front and the one breath as the code lands (0 = off)
FRONT = 0.35         # softness of the print front (0.25 crisper, 0.5 more of a dissolve)
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
GRADE = os.environ.get('GRADE', '0') not in ('0', '')
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS = S.W, S.H, S.FPS
Q = 4

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg)


def decline(msg):
    sys.exit('CODE SCAN DECLINES: ' + msg)


# ---------------------------------------------------------------------------------------------------- timing
def norm(s):
    return re.sub(r'[^a-z0-9%]', '', s.lower())


def audio_env():
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(a) // hop
    return np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)


ENVL = audio_env()


def onset(w):
    """Whisper's start can be 0.1 to 0.4 s off: the rise of the loudness after the dip before the word's loudest moment."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    j0, j1 = int(s * 100), min(len(ENVL) - 1, int(e * 100) + 1)
    pk_i = j0 + int(np.argmax(ENVL[j0:j1 + 1])) if j1 > j0 else j0
    i0, i1 = max(0, int((s - 0.12) * 100)), min(len(ENVL) - 1, int((s + 0.12) * 100), pk_i)
    if i1 <= i0:
        return s
    im = i0 + int(np.argmin(ENVL[i0:i1 + 1]))
    pk = ENVL[im:min(len(ENVL), int((e + 0.1) * 100)) + 1].max()
    thr = ENVL[im] + 0.35 * (pk - ENVL[im])
    for i in range(im, min(len(ENVL), int((e + 0.1) * 100))):
        if ENVL[i] >= thr:
            return i / 100.0
    return s


def when(v, default):
    if v is None or v == 'auto':
        v = default
    if isinstance(v, (int, float)):
        return float(v), 'seconds'
    key, nth = (str(v).split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    w = hits[int(nth) - 1]
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


if words:
    say('words: ' + ' '.join(f"{w['text']}@{w['start']:.2f}" for w in words))
auto_in = next((w for w in words if w['start'] >= 0.5), None)
if auto_in is not None:
    auto_in = f"{auto_in['text']}#{[norm(w['text']) for w in words if w['start'] < 0.5].count(norm(auto_in['text'])) + 1}"
else:
    auto_in = 0.6
t_on, how_in = when(T_IN, auto_in)
t_in0 = t_on - 0.06
if t_in0 < 0.15:
    say(f'!! the code would start at {t_in0:.2f}s: moved to 0.15s so the slot starts on plain footage. Start the slot earlier.')
    t_in0 = 0.15
t_in1 = t_in0 + IN_DUR
if T_OUT == 'auto':
    t_out0, how_out = t_in1 + HOLD, f'{HOLD:.1f}s after it lands'
    t_out1 = t_out0 + OUT_DUR
else:
    t_out1, how_out = when(T_OUT, T_OUT)
    t_out0 = t_out1 - OUT_DUR
last_ok = DUR - 6 / FPS
if t_out1 > last_ok:
    say(f'!! the picture would come back at {t_out1:.2f}s, too close to the slot end: moved to {last_ok:.2f}s '
        '(plain footage on the last frames).')
    t_out1, t_out0 = last_ok, last_ok - OUT_DUR
hold = t_out0 - t_in1
if hold < 0.6:
    decline(f'the full code look would hold only {max(0.0, hold):.2f}s (it needs 0.6 s or more, 1.5 s with the card). '
            f'Make the slot about {0.9 - hold:.1f}s longer after the word, or start on an earlier word.')
say(f'timing: starts on {how_in}; code in {t_in0:.2f} to {t_in1:.2f}s, holds {hold:.2f}s ({how_out}), '
    f'picture back {t_out0:.2f} to {t_out1:.2f}s of {DUR:.2f}s')
f_first, f_last = int(np.floor(t_in0 * FPS)), min(N - 1, int(np.ceil(t_out1 * FPS)))

# ---------------------------------------------------------------------------------------------------- measure
have_cut = os.path.exists('assets/subject.webm')
qw, qh = W // Q, H // Q
if have_cut:
    qa = np.stack(list(reader('assets/subject.webm', W, H, alpha=True, scale=(qw, qh))))
    if len(qa) != N:
        say(f'!! the cutout has {len(qa)} frames, the slot {N}: remake it (fx_new.py)')
        qa = qa[:N] if len(qa) > N else np.concatenate([qa, np.repeat(qa[-1:], N - len(qa), 0)])
else:
    say('no cutout (assets/subject.webm): the whole picture is drawn as the room, no figure')
    qa = np.zeros((N, qh, qw), np.uint8)


def main_body(m):
    m = m.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 2:
        m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    return m > 0


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head in full-size px, or None when nobody is in the frame."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 40.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    for _ in range(6):
        band = m[top:int(top + 0.45 * hw) + 1]
        xs = np.where(band.any(axis=0))[0]
        if len(xs):
            cx = xs.mean() if len(xs) < 0.9 * m.shape[1] else cx
        r = min(m.shape[0] - 1, int(top + 0.6 * hw))
        xs = np.where(m[r, int(max(0, cx - 1.3 * hw)):int(cx + 1.3 * hw) + 1])[0]
        if not len(xs):
            break
        hw = max(8.0, float(xs[-1] - xs[0] + 1))
    return top * Q, cx * Q, hw * Q


raw_heads = [head_of(main_body(m > 128)) if m.any() else None for m in qa]
span = range(f_first, f_last + 1)
found = [raw_heads[i] for i in span if raw_heads[i]]
if SHOT != 'auto':
    shot = SHOT
elif len(found) < 0.5 * len(span):
    shot = 'none'
else:
    hw_med = float(np.median([h[2] for h in found]))
    shot = 'close' if hw_med > 300 else ('medium' if hw_med > 150 else 'wide')
heads = [None] * N
face = None
if shot != 'none' and found:
    hws = np.array([h[2] for h in found])
    tops = np.array([h[0] for h in found])
    grow = float(np.percentile(hws, 95) / max(np.percentile(hws, 5), 1))
    moved = float(np.percentile(tops, 95) - np.percentile(tops, 5))
    if grow > 1.45 or moved > 380:
        decline(f'the shot zooms or the camera moves inside the effect (head size changes x{grow:.2f}, head top moves '
                f'{moved:.0f} px). Keep the code beat inside one steady shot.')
    hw_cap = 1.25 * float(np.median(hws))
    idx = [i for i in range(N) if raw_heads[i]]
    pts = []
    for i in range(N):
        j = min(idx, key=lambda k: abs(k - i))       # frames where the cutout lost him borrow the nearest head
        top, cx, hw = raw_heads[j]
        hw = min(hw, hw_cap)
        pts.append((cx, top + 0.62 * hw, 0.50 * hw, 0.66 * hw))
    pts = np.array(pts, np.float32)
    padm = np.pad(pts, ((3, 3), (0, 0)), mode='edge')
    pts = np.stack([np.median(padm[i:i + 7], axis=0) for i in range(N)])
    k = np.array([1, 2, 3, 2, 1], np.float32) / 9.0
    pad = np.pad(pts, ((2, 2), (0, 0)), mode='edge')
    pts = np.stack([np.convolve(pad[:, c], k, mode='valid') for c in range(4)], 1)
    heads = [[round(float(v), 1) for v in p] for p in pts]
    fb = np.array([(h[1] - 0.62 * min(h[2], hw_cap), h[0] - 0.08 * min(h[2], hw_cap), h[1] + 0.62 * min(h[2], hw_cap),
                    h[0] + 1.45 * min(h[2], hw_cap)) for h in found])
    face = (np.percentile(fb[:, 0], 3), np.percentile(fb[:, 1], 3), np.percentile(fb[:, 2], 97), np.percentile(fb[:, 3], 97))
    touch = float(np.mean([(qa[i][:, :2] > 128).sum() + (qa[i][:, -2:] > 128).sum() >= 12 for i in span]))
    say(f'measured: {shot} shot, head {np.median(hws):.0f}px wide, top {np.percentile(tops, 5):.0f}, face x '
        f'{(face[0] + face[2]) / 2:.0f}, chin down to {face[3]:.0f}' + (', speaker meets both frame sides' if touch > 0.5 else ''))
else:
    say(f'measured: no speaker in the cutout ({shot}): the picture becomes room code only, card in the lower middle')

# levels (so a dark room or dark clothes still read as code) and the two order fields, from the first frame of each
# transition
f_out0 = min(N - 1, int(np.ceil(t_out0 * FPS - 1e-6)))
grab = {}
for i, fr in enumerate(reader('assets/aroll.mp4', W, H, scale=(qw, qh))):
    if i in (f_first, f_out0):
        grab[i] = fr.astype(np.float32) / 255.0
    if i >= max(f_first, f_out0):
        break
rgb0 = grab[f_first]
A0 = qa[f_first].astype(np.float32) / 255.0
L0 = rgb0 @ S.LUMA
room_px, body_px = L0[A0 < 0.1], L0[A0 > 0.6]
lo = min(float(np.percentile(room_px, 3)) if room_px.size > 100 else 0.0, 0.12)
hi = max(float(np.percentile(room_px, 97)) if room_px.size > 100 else 1.0, lo + 0.35)
blo = min(float(np.percentile(body_px, 3)) if body_px.size > 100 else 0.02, 0.04)
bhi = float(np.clip(np.percentile(body_px, 97) if body_px.size > 100 else 0.6, blo + 0.30, 0.75))
say(f'levels: room {lo:.2f} to {hi:.2f}' + (' (dark room: stretched so it still reads as code)' if hi < 0.6 else '')
    + f', speaker {blo:.2f} to {bhi:.2f}')


def order_field(rgb, A, seed):
    """0..1 per pixel (quarter size): when that spot prints. Speaker's core first, then outward through the room,
    bright areas a touch earlier, plus a slow organic wobble. Smooth everywhere (no cells, no blocks) and
    rank-equalised so the front covers the same share of the frame per unit of progress."""
    m = (A > 0.5).astype(np.uint8)
    if m.sum() > 200:
        sd = cv2.distanceTransform(1 - m, cv2.DIST_L2, 5) - cv2.distanceTransform(m, cv2.DIST_L2, 5)
    else:
        yy, xx = np.mgrid[0:qh, 0:qw].astype(np.float32)
        sd = np.hypot(xx - qw / 2, (yy - qh * 0.45) * 0.8)
    sd = (sd - sd.min()) / max(float(sd.max() - sd.min()), 1e-6)
    lum = cv2.GaussianBlur(rgb @ S.LUMA, (0, 0), 6)
    rng = np.random.RandomState(seed)
    noise = cv2.resize(rng.rand(qh // 24 + 2, qw // 24 + 2).astype(np.float32), (qw, qh), interpolation=cv2.INTER_CUBIC)
    s = 0.58 * sd + 0.30 * (1.0 - lum) + 0.12 * noise
    s = cv2.GaussianBlur(s.astype(np.float32), (0, 0), 3.0)
    rank = np.empty(s.size, np.float32)
    rank[np.argsort(s, axis=None, kind='stable')] = np.linspace(0.0, 1.0, s.size, dtype=np.float32)
    return cv2.GaussianBlur(rank.reshape(s.shape), (0, 0), 1.5)


os.makedirs('work', exist_ok=True)
np.save('work/order_in.npy', order_field(rgb0, A0, 53))
np.save('work/order_out.npy', order_field(grab[f_out0], qa[f_out0].astype(np.float32) / 255.0, 71))

# ---------------------------------------------------------------------------------------------------- the card
table = S.font_table(os.path.join('assets', 'fonts'))
if not table:
    sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
S.pick_font(table, CODE_FONT, CODE_WEIGHT)
tspec = S.pick_font(table, FONT, WEIGHT)
term = None
if not ENV['CAPTIONS']:
    say('CAPTIONS=0: no terminal card, the code look alone')
elif not LINE1.strip():
    say('LINE1 is empty: no terminal card')
else:
    term = dict(prompt=PROMPT, line1=S.cased(LINE1, CASE), line2=S.cased(LINE2, CASE), font=FONT, weight=WEIGHT,
                font_px=46, cps=24.0, in_dur=0.42, out_dur=0.16)
    term['t_in'] = t_in1 - 0.10
    term['t_out'] = t_out0 - 0.16
    room = term['t_out'] - term['t_in']
    for cps in (24.0, 30.0, 36.0):
        term['cps'] = cps
        term['t_type'] = term['t_in'] + 0.24
        t_end = term['t_type'] + len(term['line1']) / cps
        term['t_done'] = t_end + 0.22
        need = (term['t_done'] + 0.32) if term['line2'] else (t_end + 0.32)
        if need <= term['t_out']:
            break
    else:
        if term['t_type'] + len(term['line1']) / term['cps'] + 0.4 <= term['t_out']:
            say(f'!! the hold ({hold:.2f}s) is too short for the second line: card types LINE1 only')
            term['line2'] = ''
        else:
            say(f'!! the hold ({hold:.2f}s) is too short for the card to type and be read: no card. HOLD 1.5 or more '
                'brings it back.')
            term = None
    if term is not None and not term['line2']:
        term['t_done'] = 1e9
if term is not None:
    lay = S.term_layout(term, tspec)
    sc = 1.0 if TERM_SCALE == 'auto' else float(TERM_SCALE)
    if lay['pw'] * sc > W - 2 * S.SAFE['side'] - 40:
        sc = (W - 2 * S.SAFE['side'] - 40) / lay['pw']
    term['scale'] = sc
    bw, bh = lay['pw'] * sc, lay['ph'] * sc

    def fits(cx, cy):
        x0, y0, x1, y1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2 + 14
        if x0 < S.SAFE['side'] + 10 or x1 > W - S.SAFE['side'] - 10 or y0 < S.SAFE['top'] + 10 or y1 > S.SAFE['bottom'] - 8:
            return False
        if y1 > S.SAFE['right_low'][0] and x1 > W - S.SAFE['right_low'][1] - 8:
            return False
        if face is not None:
            m = 26
            if x0 < face[2] + m and x1 > face[0] - m and y0 < face[3] + m and y1 > face[1] - m:
                return False
        return True

    if TERM_CENTRE != 'auto':
        centre, where = tuple(float(v) for v in TERM_CENTRE), 'from CLIP'
        if not fits(*centre):
            say('!! TERM_CENTRE touches the face or leaves the safe zone')
    else:
        if face is not None:
            fcx = (face[0] + face[2]) / 2
            pref = (fcx, face[3] + 40 + bh / 2)
        else:
            pref = (W / 2, 1180.0)
        cands = []
        for cy in np.arange(S.SAFE['top'] + bh / 2, S.SAFE['bottom'] - bh / 2, 10):
            for cx in np.arange(S.SAFE['side'] + bw / 2, W - S.SAFE['side'] - bw / 2 + 1, 10):
                if fits(cx, cy):
                    c = np.hypot(cx - pref[0], (cy - pref[1]) * 0.7)
                    if face is not None and cy < face[1]:
                        c += 260                       # above the head only when nothing else fits
                    cands.append((c, float(cx), float(cy)))
        if cands:
            _, cx, cy = min(cands)
            centre = (cx, cy)
            where = ('no speaker: lower middle' if face is None else 'below the chin' if cy - bh / 2 > face[3]
                     else 'above the head' if cy + bh / 2 < face[1] else 'beside the head')
        else:
            centre, where = None, ''
            say('!! no spot for the terminal card off the face inside the safe zone: the code beat runs without it')
            term = None
    if term is not None:
        term['cx'], term['cy'] = round(centre[0], 1), round(centre[1], 1)
        say(f'card: "{term["prompt"]}{term["line1"]}" / "{term["line2"]}" in {os.path.basename(tspec[0])}, '
            f'{bw:.0f}x{bh:.0f}px at ({centre[0]:.0f}, {centre[1]:.0f}), {where}; types at {term["cps"]:.0f} chars/s')

# ---------------------------------------------------------------------------------------------------- plan
pal = dict(bg=list(BACKDROP), room=list(ROOM_INK), body=list(INK), accent=list(ACCENT))
toks = [t for t in (str(x).strip() for x in TOKENS) if t] or ['code']
pl = dict(n=N, fps=FPS, t_in0=t_in0, t_in1=t_in1, t_out0=t_out0, t_out1=t_out1, f_first=f_first, f_last=f_last,
          heads=heads if shot != 'none' else [None] * N, shot=shot, cutout=have_cut, palette=pal, tokens=toks,
          accent_words=[a for a in ACCENT_WORDS if a in toks], code_font=CODE_FONT, code_weight=CODE_WEIGHT,
          room_levels=[lo, hi], body_levels=[blo, bhi], face_blend=FACE_BLEND, glint=GLINT, front=FRONT,
          grade=GRADE, term=term)
json.dump(pl, open('work/plan.json', 'w'), indent=1)

# ---------------------------------------------------------------------------------------------------- sounds + index.html
cues = []
if ENV['SFX']:
    files = S.make_sfx('assets_fx', IN_DUR, OUT_DUR, len(term['line1']) if term else 0, term['cps'] if term else 24.0)
    plan_cues = [('in', t_in0 - 0.20), ('out', t_out0 - 0.04)]
    if term:
        plan_cues.append(('type', term['t_type']))
        if term['line2']:
            plan_cues.append(('done', term['t_done']))
    for key, t in plan_cues:
        path, length = files[key]
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(length - skip, DUR - t)
        if d > 0.05 and length > 0.0:
            cues.append(f'  <audio id="sfx_{key}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cues)}" data-volume="1"></audio>')

SAFE_GUIDE = ('<div style="position:absolute;inset:0;z-index:99;pointer-events:none">'
              '<div style="position:absolute;left:0;right:0;top:0;height:220px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;right:0;top:1470px;bottom:0;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;left:0;width:35px;top:220px;height:1250px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:35px;top:220px;height:935px;background:rgba(255,0,0,.28)"></div>'
              '<div style="position:absolute;right:0;width:100px;top:1155px;height:315px;background:rgba(255,0,0,.28)">'
              '</div></div>')
nl = "\n"
DUR_S = f"{int(DUR * 1000 + 1e-6) / 1000:.3f}"   # truncated, never rounded up: a rounded-up duration renders one extra frame
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
<div id="root" data-composition-id="main" data-start="0" data-duration="{DUR_S}" data-width="1080" data-height="1920">
  <audio id="bga" src="assets/aroll.mp4" data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="2" data-volume="1"></audio>
{nl.join(cues)}
  <video id="bgv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR_S}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE else ''}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.set({{}}, {{}}, {DUR_S});
window.__timelines["main"] = tl;
</script>
</body>
</html>
'''
open('index.html', 'w', encoding='utf-8', newline='\n').write(html)

fi0, fi1, fo0, fo1 = (int(round(v * FPS)) for v in (t_in0, t_in1, t_out0, t_out1))
fin = [fi0 + int(round(k * (fi1 - fi0))) for k in (0.25, 0.5, 0.75)]
fout = [fo0 + int(round(k * (fo1 - fo0))) for k in (0.3, 0.6)]
typ = int(round((term['t_type'] + 0.15) * FPS)) if term else fi1 + 8
don = int(round((term['t_done'] + 0.3) * FPS)) if term and term['line2'] else fo0 - 4
marks = sorted({0, *fin, fi1 + 2, typ, don, *fout, fo1 + 1, N - 1} & set(range(N)))
stills = [fin[1], min(N - 1, don), fout[0]]
json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} GRADE={int(GRADE)} SAFE={int(SAFE)}')
print('next: bake.py --sheet ' + ','.join(str(f) for f in (*fin, fi1 + 2, don, fout[0], fout[1])) + '  (preview), then bake.py')
