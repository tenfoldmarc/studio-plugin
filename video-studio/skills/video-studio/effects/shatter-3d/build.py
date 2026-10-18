#!/usr/bin/env python3
"""shatter-3d, step 1: measure the clip, choose the variant, plan the fracture, make the sounds, write index.html.

On the break word the picture fractures into rectangular tiles at different depths and a virtual camera drifts
through them (12 fps stepping, soft shadows, a dark ground in the gaps). Up to two punched-in close-ups (the eyes,
the hands) fly out with an accent edge. A hard jolt lands on the hit word. Then the way out:
  ENDING 'glass' (default): the held picture cracks from an impact point and breaks into falling glass shards,
                            revealing the clean live frame, with a synthesised glass sound.
  ENDING 'heal':            the tiles snap back into one clean frame.
The tile holding the face is laid out from the measured head (cutout alpha), stays whole and nearest the camera.

Run from the slot folder:  PY build.py      (then bake.py, HF render, post.py; see effect.md)
Writes work/plan.json, work/marks.json, assets_fx/*.wav, index.html. Prints every choice it made and why.
"""
import json
import math
import os
import re
import subprocess
import sys
import wave

import cv2
import numpy as np

import shcore as S
from fxio import FF, alpha, frames, probe_size

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
T_BREAK = 'auto'      # the picture fractures on this word: a word from words.json ('absolutely', or 'so#2' for its 2nd
                      # time), seconds (3.29), or 'auto' (a word 0.5 to 1.6 s before T_HIT). Re-measured on the audio
T_HIT = 'auto'        # the hard jolt lands on this word (the punch word): word, seconds, or 'auto' (the last long word
                      # that leaves 1.5 s of slot after it). Read the printout and set both words for a real edit
ENDING = 'glass'      # 'glass' = v2, cracks and breaks like glass (the default look); 'heal' = v1, the tiles snap back
HOLD = 11             # frames the fractured picture holds after the hit before it cracks (glass) or heals; 6 to 16
SHOT = 'auto'         # 'auto' (measured from the cutout), or 'wide' / 'medium' / 'tight' / 'none' (no speaker: plain grid)
FACE_BOX = None       # override the measured face (x0, y0, x1, y1) in 1080x1920 px, only if the printout is wrong
CLOSEUPS = 'auto'     # how many close-ups fly out: 'auto' (eyes and hands where there is room), 0, 1 (eyes) or 2
IMPACT = 'auto'       # where the glass is hit (x, y) in 1080x1920 px; 'auto' = the hands, else under the chin, never
                      # on the face
ACCENT = (250, 230, 122)   # edge colour of the close-up shards (r, g, b): butter yellow; use the buyer's accent colour
GROUND = (20, 22, 28)      # the dark ground seen in the gaps between tiles (r, g, b); keep it near black
SEED = 11             # tile split, depths and tilts. Change it for another arrangement
GLASS_SEED = 4        # crack pattern and how each glass shard flies
# ==== END CLIP ====

SFX = os.environ.get('SFX', '1') != '0'
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
# CAPTIONS and GRADE are accepted for the slot contract: this effect draws no words and has no grade of its own.
NAME = os.path.basename(HERE)
W, H, FPS = S.W, S.H, S.FPS
Q = 4                                     # measurement scale (quarter size)
SAFE_BOX = dict(top=220, bottom=1470, left=35, right=35, right_low=100, low_from=1155)


def say(msg):
    print('  ' + msg, flush=True)


def decline(msg):
    print(f'SHATTER 3D DECLINES: {msg}')
    sys.exit(2)


clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = math.floor(N / FPS * 1000) / 1000          # rounded DOWN: a duration rounded up renders one frame too many
words = json.load(open('words.json')) if os.path.exists('words.json') else []
os.makedirs('work', exist_ok=True)


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
    """Whisper's start can be 0.1 to 0.45 s off (it pads a word with the silence or the tail before it). First choice:
    the end of a real pause (90 ms or more of near silence; the stop of a 'p' or 'k' inside a word is shorter) from
    0.15 s before to 0.5 s after Whisper's start, the first one from the start on. Without a pause (joined-up
    speech): the rise of the loudness after the dip before the word (the dip is looked for only before the word's
    loudest moment, so it cannot jump to the next word)."""
    s, e = w['start'], max(w['end'], w['start'] + 0.1)
    loc = float(ENVL[max(0, int((s - 0.5) * 100)):int((e + 0.5) * 100) + 1].max())
    sil = ENVL < 0.08 * loc
    cands = []
    for i in range(max(9, int((s - 0.15) * 100)), min(len(ENVL) - 1, int(min(s + 0.5, e) * 100)) + 1):
        if sil[i - 9:i].all() and not sil[i]:
            j = i
            while j < min(len(ENVL) - 1, i + 10) and ENVL[j] < 0.12 * loc:
                j += 1
            cands.append(j / 100.0)
    if cands:                             # Whisper usually starts a word early: the first pause end from its start on
        after = [c for c in cands if c >= s - 0.04]
        return min(after) if after else max(cands)
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


def find_word(v):
    key, nth = (str(v).split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    return hits[int(nth) - 1]


def when(v):
    if isinstance(v, (int, float)):
        return float(v), f'{float(v):.2f}s (given)'
    w = find_word(v)
    t = onset(w)
    return t, f'"{w["text"]}" (whisper {w["start"]:.2f}s, audio onset {t:.2f}s)'


STOP = set('the a an and but or so to of in on at for with is are was were be been it its this that these those you '
           'your i me my we our they them he she his her if then than just like do does did have has had not no can '
           'will would could should what when how why who all also very really'.split())
TAIL_GLASS = 3 + 20 + 4                   # crack frames + glass fall + plain frames, after HOLD
TAIL_HEAL = 24 - HOLD + 3 + 4
tail = HOLD + (TAIL_GLASS if ENDING == 'glass' else TAIL_HEAL)
if T_HIT == 'auto':
    cands = [w for w in words if len(norm(w['text'])) >= 4 and norm(w['text']) not in STOP]
    good = [w for w in cands if 17 <= onset(w) * FPS <= N - max(45, tail)]
    ok = [w for w in cands if 17 <= onset(w) * FPS <= N - tail]
    pick_hit = (good or ok or [None])[-1]
    if pick_hit is None:
        decline('no word in this slot leaves room for the effect: the hit word needs about 1.2 s of slot after it '
                'and 0.6 s before it. Make the slot longer or set T_HIT in seconds.')
    t_hit, how_hit = onset(pick_hit), f'auto: "{pick_hit["text"]}" (the last long word with room after it)'
    if not good:
        how_hit += ', less than 1.5 s of slot after it'
else:
    t_hit, how_hit = when(T_HIT)
f_hit = int(round(t_hit * FPS))
if T_BREAK == 'auto':
    best = None
    for w in words:
        g = (f_hit - onset(w) * FPS) / FPS
        if 0.5 <= g <= 1.6 and onset(w) * FPS >= 8:
            score = abs(g - 1.0) - (0.25 if len(norm(w['text'])) >= 4 and norm(w['text']) not in STOP else 0)
            if best is None or score < best[0]:
                best = (score, w)
    if best:
        t_break = onset(best[1])
        how_break = f'auto: "{best[1]["text"]}" ({f_hit / FPS - t_break:.2f}s before the hit)'
    else:
        t_break, how_break = max(8 / FPS, t_hit - 1.0), 'auto: 1 s before the hit (no word fits)'
else:
    t_break, how_break = when(T_BREAK)
f_break = int(round(t_break * FPS))
if f_break < 8:
    say(f'!! the break would be at frame {f_break}: moved to frame 8 so the slot starts on plain footage '
        '(start the slot earlier for a cleaner build)')
    f_break = 8
if f_hit - f_break < 9:
    say(f'!! break and hit are {f_hit - f_break} frames apart (9 or more reads well): the break moves to {f_hit - 9}')
    f_break = f_hit - 9
    if f_break < 8:
        decline('the hit word comes too early in the slot for a fracture before it. Start the slot earlier.')
if f_hit - f_break > 75:
    say(f'!! {(f_hit - f_break) / FPS:.1f}s between break and hit: the drift gets long; 0.6 to 1.5 s is the sweet spot')
hold = int(HOLD)
glass_fall = 20
if ENDING == 'glass':
    while f_hit + hold + 3 + glass_fall + 4 > N and hold > 5:
        hold -= 1
    while f_hit + hold + 3 + glass_fall + 4 > N and glass_fall > 15:
        glass_fall -= 1
    if f_hit + hold + 3 + glass_fall + 4 > N:
        decline(f'the slot ends {(N - f_hit) / FPS:.2f}s after the hit word: the glass needs about 1 s. Give the slot '
                'about 1.2 s more after the hit (or more footage), or pick an earlier hit word.')
    f_crack = f_hit + hold
    f_gone = f_crack + 3 + glass_fall
    f_heal = f_crack
    f_clean = f_gone
else:
    f_heal = f_hit + 24 - (HOLD - hold)
    while f_heal + 3 + 4 > N and f_heal > f_hit + 8:
        f_heal -= 1
    if f_heal + 3 + 4 > N:
        decline('the slot ends right after the hit word: the tiles need 0.5 s to snap back. Make the slot longer.')
    f_clean = f_heal + 3
if hold != HOLD and ENDING == 'glass':
    say(f'!! the slot is short after the hit: HOLD {HOLD} -> {hold} frames, glass falls in {glass_fall} frames')
say(f'timing: break frame {f_break} on {how_break}; hit frame {f_hit} on {how_hit}')
say(f'        ' + (f'cracks frames {f_crack} to {f_crack + 2}, glass falls {f_crack + 3} to {f_gone - 1}, clean from {f_gone}'
                   if ENDING == 'glass' else f'heals frames {f_heal} to {f_heal + 2}, clean from {f_heal + 3}')
    + f'; slot has {N} frames ({(N - f_clean) / FPS:.2f}s plain at the end, {(N - f_hit) / FPS:.2f}s after the hit)')

# ---------------------------------------------------------------------------------------------------- measure
span_lo, span_hi = f_break, (f_crack if ENDING == 'glass' else f_heal) + 1


def snap(v):
    return int(round(v / 5.0)) * 5


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head, or None when nobody is in the frame."""
    rows = np.where(m.sum(axis=1) >= 3)[0]
    if not len(rows):
        return None
    top = rows[0]
    hw = 40.0
    cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
    def run(r, c):
        """width and centre of the solid run of the mask row r that holds column c (or the nearest set pixel)."""
        xs = np.where(m[r])[0]
        if not len(xs):
            return None
        c = int(xs[np.argmin(np.abs(xs - c))])
        x0, x1 = c, c
        while x0 > 0 and m[r, x0 - 1]:
            x0 -= 1
        while x1 < m.shape[1] - 1 and m[r, x1 + 1]:
            x1 += 1
        return x1 - x0 + 1, (x0 + x1) / 2

    for _ in range(6):
        # the temples: median of three rows high on the head, each the run around the head's centre, so a raised
        # hand, an arm on the sofa or the shoulders cannot widen it
        got = [run(min(m.shape[0] - 1, int(top + k * hw)), cx) for k in (0.30, 0.40, 0.50)]
        got = [g for g in got if g]
        if not got:
            break
        new = float(np.median([g[0] for g in got]))
        cx = float(np.median([g[1] for g in got]))
        new = min(new, 1.6 * hw)
        if abs(new - hw) < 1:
            break
        hw = max(8.0, new)
    return top * Q, cx * Q, hw * Q


def main_body(m):
    m = m.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 2:
        m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    return m > 0


shot, heads, qa = SHOT, [], None
if SHOT != 'none' and FACE_BOX is None:
    if os.path.exists('assets/subject.webm'):
        qa = alpha('assets/subject.webm', (W // Q, H // Q))
        if len(qa) != N:
            say(f'!! the cutout has {len(qa)} frames, the slot {N}')
            qa = qa[:N] if len(qa) > N else np.concatenate([qa, np.repeat(qa[-1:], N - len(qa), 0)])
        body = [main_body(m > 128) for m in qa[span_lo:span_hi]]
        heads = [h for h in (head_of(m) for m in body) if h]
        if len(heads) < 0.5 * max(1, len(body)):
            say('no speaker found in the cutout for most of the effect: plain fracture (SHOT none)')
            shot = 'none'
    else:
        say('no cutout (assets/subject.webm): the face cannot be measured, plain fracture (SHOT none). '
            'Make the slot without --no-cutout to keep the face whole.')
        shot = 'none'

face = eyes = None
if FACE_BOX is not None:
    fx0_, fy0_, fx1_, fy1_ = FACE_BOX
    hw = (fx1_ - fx0_)
    face = (float(fx0_), float(fy0_), float(fx1_), float(fy1_))
    top_hi, chin_low, hcx = fy0_, fy1_, (fx0_ + fx1_) / 2
    if shot == 'auto':
        shot = 'tight' if hw > 330 else ('medium' if hw > 150 else 'wide')
    say(f'face box given: {FACE_BOX}, {shot} shot')
elif shot != 'none':
    tops = np.array([h[0] for h in heads])
    cxs = np.array([h[1] for h in heads])
    hws = np.array([h[2] for h in heads])
    sm = np.convolve(hws, np.ones(5) / 5, 'valid') if len(hws) >= 5 else hws
    zoom = float(sm.max() / max(sm.min(), 1))
    if zoom > 1.30:
        decline(f'the shot zooms in or out while the frame is fractured (the head grows x{zoom:.2f}): the face tile '
                'cannot hold it. Start the slot after the zoom, or end it before.')
    hw = float(np.median(hws))
    top_hi = float(np.percentile(tops, 3))
    chin_low = float(np.percentile(tops + 1.35 * hws, 97))
    hcx = float(np.median(cxs))
    face = (float(np.percentile(cxs - hws / 2, 3)), top_hi, float(np.percentile(cxs + hws / 2, 97)), chin_low)
    moved = float(np.percentile(cxs, 97) - np.percentile(cxs, 3)) + float(np.percentile(tops, 97) - top_hi)
    if shot == 'auto':
        shot = 'tight' if hw > 330 else ('medium' if hw > 150 else 'wide')
    say(f'measured: {shot} shot, head {hw:.0f} px wide, top y {top_hi:.0f}, chin y {chin_low:.0f}, face centre x '
        f'{hcx:.0f}, moves {moved:.0f} px during the effect (the face tile covers all of it)')
if face is not None:
    # eye line: about 0.75 of the head width below the top of the head (hair or a cap included in the cutout)
    ey = top_hi + 0.75 * hw if FACE_BOX is None else fy0_ + 0.42 * (fy1_ - fy0_)
    eyes = (snap(max(0, hcx - 0.48 * hw)), snap(max(0, ey - 0.22 * hw)), snap(min(W, hcx + 0.48 * hw)),
            snap(min(H, ey + 0.22 * hw)))

# ---------------------------------------------------------------------------------------------------- tiles
rng = np.random.RandomState(SEED + 1)
if face is not None:
    # margins around the face (in head widths): generous on a medium or wide shot, snug on a close-up where the
    # face already fills the frame (the tile must still hold every place the face goes during the effect)
    mx, mt, mb = (0.12, 0.25, 0.22) if shot == "tight" else (0.30, 0.45, 0.55)
    fx0, fx1 = face[0] - mx * hw, face[2] + mx * hw
    fy0, fy1 = face[1] - mt * hw, face[3] + mb * hw
    minw, minh = (300, 420)
    if fx1 - fx0 < minw:
        c = (fx0 + fx1) / 2
        fx0, fx1 = c - minw / 2, c + minw / 2
    if fy1 - fy0 < minh:
        c = (fy0 + fy1) / 2
        fy0, fy1 = c - minh / 2, c + minh / 2
else:
    fx0, fx1, fy0, fy1 = W * 0.30, W * 0.68, H * 0.24, H * 0.50
fx0, fx1 = snap(max(0, fx0)), snap(min(W, fx1))
fy0, fy1 = snap(max(0, fy0)), snap(min(H, fy1))
fx0 = 0 if fx0 < 110 else fx0
fx1 = W if W - fx1 < 110 else fx1
fy0 = 0 if fy0 < 130 else fy0
fy1 = H if H - fy1 < 160 else fy1
hero = (fx0, fy0, fx1, fy1)


def split(r, max_area, min_side=120):
    x0, y0, x1, y1 = r
    w, h = x1 - x0, y1 - y0
    if w * h <= max_area or (w < 2 * min_side and h < 2 * min_side):
        return [r]
    if (h >= w * 0.9 and h >= 2 * min_side) or w < 2 * min_side:
        c = snap(y0 + h * rng.uniform(0.38, 0.62))
        return split((x0, y0, x1, c), max_area, min_side) + split((x0, c, x1, y1), max_area, min_side)
    c = snap(x0 + w * rng.uniform(0.38, 0.62))
    return split((x0, y0, c, y1), max_area, min_side) + split((c, y0, x1, y1), max_area, min_side)


AREA = W * H / (14 if shot == "tight" else 9)         # largest other tile: smaller pieces around a big face
shards = [dict(id='face', rect=hero, hero=True, z=round(-300 * float(np.clip(330 / (fx1 - fx0), 0.45, 1.0))),
               tilt=(0, 3.0, 0))]
rects = []
if fy0 > 0:
    rects += split((0, 0, W, fy0), AREA)
open_right = (W - fx1) >= fx0                     # the side of the face with more room
if fx0 > 0:
    lw = fx0
    if not open_right and lw >= 300:
        sl = snap(rng.uniform(120, 160))
        rects.append((fx0 - sl, fy0, fx0, fy1))
        lw -= sl
    rects += split((0, fy0, lw, fy1), AREA)
if fx1 < W:
    rx = fx1
    if open_right and W - fx1 >= 300:
        sl = snap(rng.uniform(120, 160))
        rects.append((fx1, fy0, fx1 + sl, fy1))
        rx += sl
    rects += split((rx, fy0, W, fy1), AREA)
if fy1 < H:
    cols = [0, fx0, fx1, W]
    cols = [c for i, c in enumerate(cols) if i in (0, 3) or 120 <= c <= W - 120]
    cols = sorted(set(cols))
    for a, b in zip(cols[:-1], cols[1:]):
        parts = split((a, fy1, b, H), AREA)
        parts.sort(key=lambda r: r[1])
        if a == fx0 and b == fx1 and shot != 'none':
            shards.append(dict(id='body', rect=parts[0], z=-110, tilt=(-2.0, -4.0, 0.5)))
            parts = parts[1:]
        rects += parts
for k, r in enumerate(rects):
    shards.append(dict(id=f't{k}', rect=r))
for s in shards:
    s['rect'] = tuple(int(v) for v in s['rect'])
cover = np.zeros((H, W), np.uint8)
for s in shards:
    x0, y0, x1, y1 = s['rect']
    cover[y0:y1, x0:x1] += 1
assert cover.min() == 1 and cover.max() == 1, 'tile layout does not cover the frame exactly once'
say(f'tiles: {len(shards)}, face tile {hero} ({hero[2] - hero[0]}x{hero[3] - hero[1]}, depth {shards[0]["z"]}), '
    f'open side {"right" if open_right else "left"}')

# ---------------------------------------------------------------------------------------------------- close-ups
def plan_dict(sh, impact=(W / 2, H / 2)):
    return dict(f_break=f_break, f_hit=f_hit, f_heal=f_heal, ending=ENDING, seed=SEED, eyes=eyes, shards=sh,
                accent=list(ACCENT), ground=list(GROUND),
                glass=dict(f_crack=f_heal, crack_frames=3, f_gone=f_clean, impact=list(impact), seed=GLASS_SEED))


def in_safe(q):
    x0, y0 = q.min(0)
    x1, y1 = q.max(0)
    right = W - (SAFE_BOX['right_low'] if y1 > SAFE_BOX['low_from'] else SAFE_BOX['right'])
    return x0 >= SAFE_BOX['left'] and x1 <= right and y0 >= SAFE_BOX['top'] and y1 <= SAFE_BOX['bottom']


def overlap(q, box):
    x0, y0 = q.min(0)
    x1, y1 = q.max(0)
    ix = max(0.0, min(x1, box[2]) - max(x0, box[0]))
    iy = max(0.0, min(y1, box[3]) - max(y0, box[1]))
    return ix * iy / max(1.0, (box[2] - box[0]) * (box[3] - box[1]))


def try_dupe(base, d, avoid):
    """does close-up d stay inside the safe zone, off the face and off `avoid` boxes, with the eyes seen?"""
    fx = S.Shatter(plan_dict(base + [d]))
    s = fx.shards[-1]
    worst = 1.0
    for n, P in fx.frac_poses():
        if P['D'] < 0.02:
            continue
        q, _ = fx.quad(s, P)
        if not in_safe(q):
            return False, 'leaves the safe zone'
        if face is not None and overlap(q, face) > 0.06:
            return False, 'covers the face'
        if any(overlap(q, b) > 0.15 for b in avoid):
            return False, 'covers the other close-up'
        worst = min(worst, fx.eye_vis(P))
    return (worst >= 0.97), f'eyes {worst:.0%} seen'


def final_box(base, d):
    fx = S.Shatter(plan_dict(base + [d]))
    qs = [fx.quad(fx.shards[-1], P)[0] for n, P in fx.frac_poses() if P['D'] >= 0.02]
    q = np.concatenate(qs)
    return (float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()), float(q[:, 1].max()))


want = 2 if CLOSEUPS == 'auto' else int(CLOSEUPS)
dupes, boxes, hands = [], [], None
if face is not None and want > 0 and shot != 'none':
    # eyes close-up: the eye band, punched in, flies to the open side (or above / below the head)
    ew = eyes[2] - eyes[0]
    er = (snap(max(0, (eyes[0] + eyes[2]) / 2 - 0.62 * hw)), snap(max(0, (eyes[1] + eyes[3]) / 2 - 0.30 * hw)),
          snap(min(W, (eyes[0] + eyes[2]) / 2 + 0.62 * hw)), snap(min(H, (eyes[1] + eyes[3]) / 2 + 0.30 * hw)))
    grow = float(np.clip(250 / max(1, er[2] - er[0]), 1.08, 1.7))
    dw, dh = (er[2] - er[0]) * grow * 1.3, (er[3] - er[1]) * grow * 1.3
    gap = 40
    sgn = 1 if open_right else -1
    xo = (face[2] + gap + dw / 2) if open_right else (face[0] - gap - dw / 2)
    xc = (face[0] - gap - dw / 2) if open_right else (face[2] + gap + dw / 2)
    cands = [('beside the face', (xo, face[1] + 0.25 * hw)), ('beside the face, lower', (xo, face[3])),
             ('on the other side', (xc, face[1] + 0.25 * hw)), ('above the head', ((face[0] + face[2]) / 2, face[1] - gap - dh / 2)),
             ('under the chin', ((face[0] + face[2]) / 2, face[3] + gap + dh / 2))]
    why = []
    for label, to in cands:
        for pull in (0, 60, 120):
            t2 = (to[0] - sgn * pull if 'other' not in label else to[0] + sgn * pull, to[1])
            d = dict(id='eyes', kind='dupe', rect=er, z=-400, to=(round(t2[0]), round(t2[1])), grow=round(grow, 3),
                     tilt=(0, -7 * sgn, 1.2 * sgn), eyes=True, accent=True)
            ok, msg = try_dupe(shards, d, [])
            if ok:
                dupes.append(d)
                boxes.append(final_box(shards, d))
                say(f'close-up 1: the eyes, flies {label} to {d["to"]} (x{grow:.2f})')
                break
            why.append(f'{label}: {msg}')
        if dupes:
            break
    if not dupes:
        say('close-ups: none (no room beside, above or below the face inside the safe zone). The face tile carries it.')
    # hands close-up: skin below the chin inside the speaker's cutout, measured on the frames the fracture shows
    if want >= 2 and dupes and qa is not None:
        fx_tmp = S.Shatter(plan_dict(shards))
        srcs = sorted({fx_tmp.plan(n)[1] for n in range(f_break, span_hi) if fx_tmp.plan(n)[0] == 'frac'})
        fr = frames('assets/aroll.mp4', srcs, W, H)
        acc = np.zeros((H // Q, W // Q), np.float32)
        for i in srcs:
            small = cv2.resize(fr[i], (W // Q, H // Q), interpolation=cv2.INTER_AREA)
            ycc = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb)
            skin = cv2.inRange(ycc, (50, 136, 80), (245, 175, 128)) > 0
            acc += skin & main_body(qa[i] > 128)
        acc /= max(1, len(srcs))
        lim = int((face[3] + 0.15 * hw) / Q)
        acc[:max(0, lim)] = 0
        mk = cv2.morphologyEx((acc > 0.4).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, lab, st, cen = cv2.connectedComponentsWithStats(mk, 8)
        if n > 1:
            k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            if st[k, cv2.CC_STAT_AREA] * Q * Q >= (0.35 * hw) ** 2:
                hands = (float(cen[k][0] * Q), float(cen[k][1] * Q))
        if hands is None:
            say('close-up 2: none (no hands found under the chin)')
        else:
            hr = (snap(max(0, hands[0] - 0.75 * hw)), snap(max(0, hands[1] - 0.80 * hw)),
                  snap(min(W, hands[0] + 0.75 * hw)), snap(min(H, hands[1] + 0.80 * hw)))
            if overlap(np.array([[hr[0], hr[1]], [hr[2], hr[3]]], float), face) > 0.10:
                say('close-up 2: none (the hands are up at the face)')
                hands = None                      # and the glass is not hit there either (too near the face)
            else:
                g2 = float(np.clip(300 / max(1, hr[2] - hr[0]), 1.05, 1.6))
                dw2 = (hr[2] - hr[0]) * g2 * 1.3
                tx = (face[0] - gap - dw2 / 2) if open_right else (face[2] + gap + dw2 / 2)
                c2 = [('on the other side, low', (tx, hands[1] + 0.9 * hw)), ('on the other side', (tx, hands[1])),
                      ('below the hands', (hands[0], hands[1] + 1.6 * hw)), ('on the open side, low', (xo, hands[1] + 0.9 * hw))]
                for label, to in c2:
                    for pull in (0, 60, 120, 180):
                        yy = min(to[1], SAFE_BOX['bottom'] - (hr[3] - hr[1]) * g2 * 0.75) - pull * 0.5
                        d = dict(id='hands', kind='dupe', rect=hr, z=-380, to=(round(to[0] + sgn * pull * (1 if 'other' in label else -1)), round(yy)),
                                 grow=round(g2, 3), tilt=(2, 8 * sgn, -1.5 * sgn), accent=True)
                        ok, msg = try_dupe(shards + dupes, d, boxes)
                        if ok:
                            dupes.append(d)
                            say(f'close-up 2: the hands at ({hands[0]:.0f}, {hands[1]:.0f}), fly {label} to {d["to"]}')
                            break
                    if len(dupes) == 2:
                        break
                if len(dupes) < 2:
                    say('close-up 2: none (no room for the hands close-up inside the safe zone)')
shards += dupes[:want]

# ---------------------------------------------------------------------------------------------------- impact
if IMPACT != 'auto':
    impact = tuple(float(v) for v in IMPACT)
    how_imp = 'given'
elif hands is not None:
    impact, how_imp = hands, 'on the hands'
elif face is not None and face[3] + 0.6 * hw < 1500:
    impact, how_imp = ((face[0] + face[2]) / 2, face[3] + 0.6 * hw), 'under the chin'
elif face is not None:
    xo2 = (face[2] + W) / 2 if open_right else face[0] / 2
    impact, how_imp = (xo2, face[1] + 0.9 * hw), 'beside the face on the open side'
else:
    impact, how_imp = (W * 0.55, H * 0.47), 'centre'
impact = (float(np.clip(impact[0], 60, W - 60)), float(np.clip(impact[1], 260, 1600)))
if ENDING == 'glass':
    say(f'glass: hit at ({impact[0]:.0f}, {impact[1]:.0f}) ({how_imp}), seed {GLASS_SEED}')

# ---------------------------------------------------------------------------------------------------- checks
pl = plan_dict(shards, impact)
fx = S.Shatter(pl)
worst = min((fx.eye_vis(P) for n, P in fx.frac_poses()), default=1.0)
for s in fx.shards:
    if s['kind'] == 'dupe':
        q = np.concatenate([fx.quad(s, P)[0] for n, P in fx.frac_poses() if P['D'] >= 0.02])
        say(f"close-up '{s['id']}' travels x {q[:, 0].min():.0f}..{q[:, 0].max():.0f}, "
            f"y {q[:, 1].min():.0f}..{q[:, 1].max():.0f} (safe zone x 35..980/1045, y 220..1470)")
if eyes:
    say(f'eyes {eyes} seen in every fractured frame: worst {worst:.0%}' + ('' if worst >= 0.97 else '  !! check it'))
hi_path = 'assets/aroll_hi.mp4'
use_hi = False
if os.path.exists(hi_path):
    hw_, hh_ = probe_size(hi_path)
    use_hi = abs(hw_ / hh_ - W / H) < 0.01 and hw_ > W
    say(f'tiles cut from {"assets/aroll_hi.mp4 (" + str(hw_) + "x" + str(hh_) + ")" if use_hi else "assets/aroll.mp4"}'
        + ('' if use_hi else f' (aroll_hi is {hw_}x{hh_}, not a sharper 9:16 copy)'))
else:
    say('tiles cut from assets/aroll.mp4 (fine for 1080 footage; from a 4K source make the slot with --hi for sharper tiles)')
pl.update(n=N, name=NAME, src_hi=hi_path if use_hi else 'assets/aroll.mp4', shot=shot, face=face, hands=hands)
json.dump(pl, open('work/plan.json', 'w'), indent=1)

# ---------------------------------------------------------------------------------------------------- sounds
SR = 48000


def wav(path, x):
    x = np.clip(x, -1, 1)
    st = x if x.ndim == 2 else np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def band_noise(n, lo, hi, r):
    spec = np.fft.rfft(r.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = 1 / (1 + (lo / np.maximum(fr, 1)) ** 2) / (1 + (fr / hi) ** 2)
    x = np.fft.irfft(spec * shape, n)
    return x / np.abs(x).max()


def s_whoosh(seed, peak):
    r = np.random.default_rng(seed)
    n = int(SR * 0.42)
    t = np.arange(n) / SR
    lo, hi = band_noise(n, 250, 900, r), band_noise(n, 900, 4200, r)
    k = np.where(t < 0.12, np.clip(t / 0.12, 0, 1), np.exp(-(t - 0.12) / 0.10))
    x = lo * (1 - 0.6 * k) + hi * 0.6 * k
    env = np.where(t < 0.10, (t / 0.10) ** 2, np.exp(-(t - 0.10) / 0.09))
    y = x * env
    return y / np.abs(y).max() * peak


def s_bass(seed, peak):
    """a deep hit: a falling sine thump plus a short low click on top."""
    r = np.random.default_rng(seed)
    n = int(SR * 0.7)
    t = np.arange(n) / SR
    f0 = 44 + 80 * np.exp(-t / 0.035)
    y = np.sin(2 * np.pi * np.cumsum(f0) / SR) * np.exp(-t / 0.24) * np.clip(t / 0.003, 0, 1)
    y += 0.35 * band_noise(n, 80, 1800, r) * np.exp(-t / 0.012)
    y = np.tanh(1.6 * y)
    return y / np.abs(y).max() * peak


def s_click(seed, peak):
    r = np.random.default_rng(seed)
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    y = band_noise(n, 1500, 7000, r) * np.exp(-t / 0.004) + 0.5 * np.sin(2 * np.pi * 1900 * t) * np.exp(-t / 0.007)
    return y / np.abs(y).max() * peak


def s_glass(seed, pre, peak):
    """glass shatter, synthesised: crackle while the cracks race (`pre` s), a sharp break, a dense spray of short high
    pings thinning out over about 0.6 s, a few late tinkles."""
    n = int(SR * 0.98)
    rng2 = np.random.RandomState(seed)
    out = np.zeros((n, 2))

    def band(x, lo, hi):
        f = np.fft.rfftfreq(len(x), 1 / SR)
        g = 1 / (1 + (lo / np.maximum(f, 1)) ** 6) / (1 + (f / hi) ** 6)
        return np.fft.irfft(np.fft.rfft(x) * g, len(x))

    def put(sig, t0, pan):
        i = int(t0 * SR)
        m = min(len(sig), n - i)
        if m > 0:
            out[i:i + m, 0] += sig[:m] * math.cos((pan + 1) * math.pi / 4)
            out[i:i + m, 1] += sig[:m] * math.sin((pan + 1) * math.pi / 4)

    def ping(f, tau, amp, parts=3):
        m = int(SR * min(tau * 7, 0.6))
        t = np.arange(m) / SR
        s = np.zeros(m)
        ratios = [1.0, rng2.uniform(1.42, 1.71), rng2.uniform(2.2, 2.95)]
        for k in range(parts):
            if f * ratios[k] < 19000:
                s += (1, 0.5, 0.28)[k] * np.sin(2 * np.pi * f * ratios[k] * t + rng2.uniform(0, 6.28)) \
                     * np.exp(-t / (tau / (1 + 0.6 * k)))
        att = max(2, int(SR * 0.0004))
        s[:att] *= np.linspace(0, 1, att)
        return s * amp

    for _ in range(16):
        m = int(SR * rng2.uniform(0.001, 0.003))
        click = np.pad(rng2.randn(m) * np.exp(-np.arange(m) / (m / 3)), (0, 256))
        put(band(click, 2500, 15000) * rng2.uniform(0.10, 0.28), pre * rng2.uniform(0, 1) ** 0.6, rng2.uniform(-0.6, 0.6))
    for _ in range(5):
        put(ping(rng2.uniform(5000, 11000), rng2.uniform(0.006, 0.014), rng2.uniform(0.04, 0.08), 2),
            pre * rng2.uniform(0.1, 0.95), rng2.uniform(-0.6, 0.6))
    m = int(SR * 0.12)
    t = np.arange(m) / SR
    put(band(rng2.randn(m), 1800, 16000) * np.exp(-t / 0.011) * 0.95, pre, 0)
    put(np.sin(2 * np.pi * 150 * t * (1 - 1.5 * t)) * np.exp(-t / 0.028) * 0.30, pre, 0)
    m = int(SR * 0.7)
    t = np.arange(m) / SR
    env = np.exp(-t / 0.11) * 0.30 + np.exp(-t / 0.35) * 0.05
    for pan in (-0.45, 0.45):
        grain = np.interp(t, np.linspace(0, 0.7, 180), rng2.uniform(0.3, 1.0, 180))
        put(band(rng2.randn(m), 2800, 13000) * env * grain, pre, pan)
    for _ in range(190):
        dt = rng2.exponential(0.13)
        if dt < 0.62:
            f = math.exp(rng2.uniform(math.log(1900), math.log(10500)))
            put(ping(f, rng2.uniform(0.010, 0.050) * (4000 / f) ** 0.35, rng2.uniform(0.06, 0.26) * math.exp(-dt / 0.30)),
                pre + 0.004 + dt, rng2.uniform(-0.8, 0.8))
    for _ in range(8):
        dt, f, tau = rng2.uniform(0.33, 0.80), rng2.uniform(3600, 9500), rng2.uniform(0.06, 0.14)
        amp, pan = rng2.uniform(0.06, 0.13), rng2.uniform(-0.8, 0.8)
        put(ping(f, tau, amp, 2), pre + dt, pan)
        put(ping(f * rng2.uniform(0.97, 1.04), tau * 0.7, amp * 0.55, 2), pre + dt + rng2.uniform(0.035, 0.075), pan)
    out *= peak / np.abs(out).max()
    fade = int(SR * 0.03)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return out


cues = []
if SFX:
    os.makedirs('assets_fx', exist_ok=True)
    plan_sfx = [('whoosh', s_whoosh(SEED, 0.15), f_break / FPS - 0.10), ('hit', s_bass(SEED + 1, 0.20), f_hit / FPS - 0.02)]
    if ENDING == 'glass':
        plan_sfx.append(('glass', s_glass(GLASS_SEED, 3 / FPS, 0.17), f_crack / FPS))
    else:
        plan_sfx += [('whoosh_out', s_whoosh(SEED + 2, 0.08), f_heal / FPS - 0.10), ('click', s_click(SEED + 3, 0.16), (f_heal + 1) / FPS)]
    for key, x, t in plan_sfx:
        path = f'assets_fx/shatter-{key}.wav'
        wav(path, x)
        length = len(x) / SR
        skip = max(0.0, -t)
        t = max(0.0, t)
        d = min(length - skip, DUR - t)
        if d > 0.03:
            cues.append(f'  <audio id="sfx_{key}" src="{path}" data-start="{t:.3f}" data-media-start="{skip:.3f}" '
                        f'data-duration="{d:.3f}" data-track-index="{10 + len(cues)}" data-volume="1"></audio>')

# ---------------------------------------------------------------------------------------------------- index.html
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

if ENDING == 'glass':
    mk = [0, f_break - 1, f_break + 2, f_hit + 1, f_hit + 6, f_crack + 1, f_crack + 4, f_crack + 9, f_gone, N - 1]
    stills = [f_hit + 5, f_crack + 5, f_break + 7]
    preview = [f_break + 7, f_hit + 2, f_crack + 2, f_crack + 6]
else:
    mk = [0, f_break - 1, f_break + 2, f_hit + 1, f_hit + 6, f_heal, f_heal + 1, f_heal + 3, N - 1]
    stills = [f_hit + 5, f_break + 7, f_heal - 2]
    preview = [f_break + 7, f_hit + 2, f_heal]
mk = sorted({min(N - 1, max(0, f)) for f in mk})
json.dump({'name': NAME, 'frames': N, 'marks': mk, 'stills': [min(N - 1, f) for f in stills]}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  ending {ENDING}  sounds {len(cues)}  '
      f'switches SFX={int(SFX)} SAFE={int(SAFE)}')
print('next: bake.py --frames ' + ','.join(str(min(N - 1, f)) for f in preview) + ' -g  (preview), then bake.py')
