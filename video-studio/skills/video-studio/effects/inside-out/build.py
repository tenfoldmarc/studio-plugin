#!/usr/bin/env python3
"""inside-out, step 1: measure the clip, prepare the buyer's fill clip, write work/plan.json, the sounds, index.html.

Inside Out: a thin line runs down the speaker, their body below the neck opens into a window onto ONE calm b-roll
clip (a place, a product, a screen), the picture slowly pushes in, then one soft iris from the chest flips it: the
speaker is solid again and the same clip is now the room around them. Near the end the real room eases back.

  PY build.py            measure + choose + plan + sounds + index.html (prints what it chose and why)
  SAFE=1 PY build.py     same, with the red safe-zone guide in index.html (snapshots only, never for the render)
  CAPTIONS=0             this effect draws no words; accepted, changes nothing
  SFX=0                  no sounds (air swell, low thump, soft air on the way back)
  GRADE                  this effect has no grade of its own; accepted, does nothing
Then bake.py (the frames), hf render, post.py. Run order: effect.md.
"""
import glob
import json
import os
import re
import subprocess
import sys
import wave

import cv2
import numpy as np

from fxio import FF, FP, reader

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ==== CLIP (edit this) ====
FILL = 'auto'           # the buyer's fill: a file in fill/ ('fill/shop.mp4') or 'auto' (the first video in fill/, else
                        # the first image). B-roll of a place, a product or a screen. NEVER a person, no big text.
FILL_START = 0.0        # seconds into the fill clip to start from (skip a shaky start, a title or a person walking in)
FILL_FOCUS = (0.5, 0.5)  # which part of a landscape fill stays in the 9:16 crop: (x, y) from 0 to 1, 0.5 = centre.
                        # Look at work/qa/fill.jpg and move it toward the interesting part.
FILL_PUSH = (1.03, 1.10)  # slow push on the fill: zoom on its first and last frame (1.0 = no push)
FIT = 'auto'            # 'auto' (wide shots only: the whole picture is framed inside the small body, then grows into
                        # the room with the flip), True (always), False (never: the picture is room-sized throughout)
T_IN = 'auto'           # the window opens on this word: a word from words.json ('edit', 'edit#2' for its 2nd time),
                        # seconds, or 'auto' (the first word that starts after 0.4 s). Re-measured on the audio.
T_FLIP = 'auto'         # the flip (the clip becomes the room): a word, seconds, or 'auto' (the word that starts
                        # nearest 1 s after T_IN and still leaves a 1 s hold). Best on the payoff word of the line.
T_OUT = 'auto'          # the real room eases back: 'auto' (over 10 frames, plain for the last 4), seconds, or 'cut'
                        # (holds to the last frame; only when the reel cuts away right after the slot)
ACCENT = (255, 248, 239)  # the thin cut line (r, g, b): cream. The buyer's accent works if it reads on their shirt
LINE_PX = (2.0, 3.0)    # line thickness: px inside / outside the matte edge (thicker reads bolder, calmer is thinner)
KEEP = 'auto'           # the live head-and-neck zone: 'auto' (from the measured head) or dict(cy=, rx=, ry=) in px:
                        # ellipse centre below the head top, half width, half height. Only if the window eats the chin.
MATTE_KILL_POLYS = []   # matte repairs, off: polygons [(x, y), ...] in 1080x1920 px where the cutout grabbed room
                        # (a chair arm, a frame). Look at a preview first; add only what you see.
SEED = 7                # the sounds are synthesised from this seed
# ==== END CLIP ====

ENV = {k: os.environ.get(k, d) != '0' for k, d in (('CAPTIONS', '1'), ('SFX', '1'))}
SAFE = os.environ.get('SAFE', '0') not in ('0', '')
NAME = os.path.basename(HERE)
W, H, FPS, Q = 1080, 1920, 30, 4
LINE_FRAMES, OPEN_FRAMES, FLIP_FRAMES, BACK_FRAMES = 10, 16, 18, 10
VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.webm', '.mkv')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp')

clip = json.load(open('clip.json'))
N = int(clip['frames'])
DUR = N / FPS
os.makedirs('work/qa', exist_ok=True)
if not os.path.exists('assets/subject.webm'):
    sys.exit('inside-out needs the cutout (assets/subject.webm): make the slot without --no-cutout')
words = json.load(open('words.json')) if os.path.exists('words.json') else []


def say(msg):
    print('  ' + msg)


def decline(reason):
    sys.exit('INSIDE OUT DECLINES: ' + reason)


# ---------------------------------------------------------------------------------------------------- the fill
def find_fill():
    if FILL != 'auto':
        if not os.path.exists(FILL):
            decline(f'the fill "{FILL}" is not there. Put the buyer\'s b-roll clip in fill/ and name it in FILL.')
        return FILL
    files = sorted(glob.glob(os.path.join('fill', '*')))
    vids = [f for f in files if f.lower().endswith(VIDEO_EXT)]
    imgs = [f for f in files if f.lower().endswith(IMAGE_EXT)]
    if not vids and not imgs:
        decline('there is no fill clip. It needs one short b-roll clip from the buyer (a place, a product or a '
                'screen; no people, no big text) in fill/ inside the slot.')
    return (vids or imgs)[0]


fill_src = find_fill()
is_img = fill_src.lower().endswith(IMAGE_EXT)


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
    """Whisper's start can be 0.1 to 0.4 s off: take the rise of the loudness after the dip before the word
    (the dip is searched only before the word's loudest moment, so it can never jump to the next word)."""
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


def find_word(v):
    key, nth = (str(v).split('#') + ['1'])[:2]
    hits = [w for w in words if norm(w['text']) == norm(key)]
    if len(hits) < int(nth):
        sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
    return hits[int(nth) - 1]


def when(v):
    if isinstance(v, (int, float)):
        return float(v), f'{float(v):.2f}s as given'
    w = find_word(v)
    t = onset(w)
    return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio onset {t:.2f}s'


if T_OUT == 'cut':
    f_out = N
elif isinstance(T_OUT, (int, float)):
    f_out = min(N - BACK_FRAMES - 2, int(round(float(T_OUT) * FPS)))
else:
    f_out = N - BACK_FRAMES - 4
f_end = min(N, f_out + BACK_FRAMES)                     # first frame that is plain footage again

if T_IN == 'auto':
    w0 = next((w for w in words if w['start'] >= 0.4), None)
    t_in, how_in = (when(f"{w0['text']}#{[norm(x['text']) for x in words[:words.index(w0) + 1]].count(norm(w0['text']))}")
                    if w0 else (0.5, 'no words: 0.50 s'))
else:
    t_in, how_in = when(T_IN)
f_in = int(round(t_in * FPS))
if f_in < 6:
    say(f'!! the line would start at frame {f_in}: moved to frame 6 so the slot starts on plain footage.')
    f_in = 6

latest_flip = f_out - FLIP_FRAMES - 12                    # the flip settles and holds before the room comes back
if T_FLIP == 'auto':
    cands = []
    for w in words:
        if w['start'] < t_in + 0.5:
            continue
        t = onset(w)
        fr = int(round(t * FPS))
        if f_in + OPEN_FRAMES + 4 <= fr <= latest_flip:
            cands.append((abs(t - (t_in + 1.0)), fr, w))
    if cands:
        _, f_flip, wf = min(cands, key=lambda c: c[0])
        how_flip = f'"{wf["text"]}" (auto: nearest 1 s after T_IN), audio onset {f_flip / FPS:.2f}s'
    else:
        f_flip = min(f_in + 30, latest_flip)
        how_flip = 'no word fits: 1 s after T_IN'
else:
    t_fl, how_flip = when(T_FLIP)
    f_flip = int(round(t_fl * FPS))
if f_flip < f_in + OPEN_FRAMES + 4:
    say(f'!! the flip at frame {f_flip} comes before the window has opened: moved to {f_in + OPEN_FRAMES + 4}')
    f_flip = f_in + OPEN_FRAMES + 4
if f_flip > latest_flip:
    if f_flip + FLIP_FRAMES + 4 > N:
        decline(f'the slot is too short after the flip (frame {f_flip} of {N}). Make the slot longer: the room '
                'needs about 1 s after the flip word.')
    say(f'!! the flip at frame {f_flip} leaves little hold before the room comes back (frame {f_out}): make the '
        'slot longer or set T_OUT = "cut" if the reel cuts right after.')

# ---------------------------------------------------------------------------------------------------- measure
qa = np.stack(list(reader('assets/subject.webm', W, H, alpha=True, scale=(W // Q, H // Q))))
if len(qa) != N:
    say(f'!! the cutout has {len(qa)} frames, the slot {N}: remake it (fx_new.py)')
    qa = qa[:N] if len(qa) > N else np.concatenate([qa, np.repeat(qa[-1:], N - len(qa), 0)])


def main_body(m):
    """the speaker: the kill polygons removed, then only the largest piece."""
    m = m.astype(np.uint8)
    for p in MATTE_KILL_POLYS:
        cv2.fillPoly(m, [(np.array(p, np.float32) / Q).astype(np.int32)], 0)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 2:
        m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    return m > 0


def head_of(m):
    """quarter-size mask -> (top, cx, width) of the head, or None when nobody is in the frame."""
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


bodies = [main_body(m > 128) for m in qa]
heads = [head_of(m) for m in bodies]
span = range(f_in, f_end)
found = [heads[f] for f in span if heads[f]]
if len(found) < 0.8 * len(span):
    decline('the cutout finds nobody in many frames of the effect. It needs the speaker in the shot the whole time.')
tops = np.array([h[0] for h in found], float)
hws = np.array([h[2] for h in found], float)
hw = float(np.median(hws))
# a zoom is a steady change of scale: compare the first and last third (medians, so a hand near the head or a
# lean does not count)
thirds = max(1, len(hws) // 3)
a_hw, b_hw = float(np.median(hws[:thirds])), float(np.median(hws[-thirds:]))
hw_ratio = max(a_hw, b_hw) / max(min(a_hw, b_hw), 1)
top_move = abs(float(np.median(tops[:thirds]) - np.median(tops[-thirds:])))
if hw_ratio > 1.25 or top_move > max(300.0, 1.2 * hw):
    decline(f'the picture zooms or punches in during the effect (head size changes {hw_ratio:.2f}x, head top moves '
            f'{top_move:.0f} px). Put the slot inside one steady shot without a zoom.')


def fill_gaps(v):
    v = np.array(v, float)
    ok = ~np.isnan(v)
    idx = np.arange(len(v))
    return np.interp(idx, idx[ok], v[ok])


def smooth(v):
    pad = np.pad(v, 3, mode='edge')
    med = np.array([np.median(pad[i:i + 7]) for i in range(len(v))])
    k = np.array([1, 3, 5, 3, 1], np.float64)
    k /= k.sum()
    return np.convolve(np.pad(med, 2, mode='edge'), k, mode='valid')


head_top = smooth(fill_gaps([h[0] if h else np.nan for h in heads]))
head_cx = smooth(fill_gaps([h[1] if h else np.nan for h in heads]))
touch = {k: float(np.mean([v(bodies[f]) for f in span])) for k, v in (
    ('left', lambda m: m[:, :2].sum() >= 6), ('right', lambda m: m[:, -2:].sum() >= 6),
    ('top', lambda m: m[:2, :].sum() >= 3), ('bottom', lambda m: m[-2:, :].sum() >= 6))}
top_med = float(np.median(tops))
shot = 'tight' if hw > 330 else ('medium' if hw > 150 else 'wide')
hcx = float(np.median(head_cx[f_in:f_end]))
if touch['top'] > 0.5:
    say('!! the head is cut by the top of the frame: the head size is a guess. If the window eats the chin, set KEEP.')

# keep zone (live head and neck), in px; proportions measured on the approved demo (head 300 px wide)
if isinstance(KEEP, dict):
    keep = dict(cy=float(KEEP['cy']), rx=float(KEEP['rx']), ry=float(KEEP['ry']))
else:
    keep = dict(cy=0.77 * hw, rx=0.72 * hw, ry=0.78 * hw)
k_scale = float(np.clip(hw / 300.0, 0.6, 1.6))          # shadow and line-shade sizes follow the speaker's size

# how much window shows: body below the keep zone, inside the safe height, at the flip
yy, xx = np.mgrid[0:H // Q, 0:W // Q].astype(np.float32) * Q
win_frac = []
for f in range(f_in + OPEN_FRAMES, min(f_flip + 1, N)):
    ex = (xx - head_cx[f]) / keep['rx']
    ey = np.maximum(yy - (head_top[f] + keep['cy']), 0) / keep['ry']
    open_ = (np.sqrt(ex * ex + ey * ey) > 1.0) & (yy > head_top[f] + keep['cy']) & (yy < 1470)
    win_frac.append(float((bodies[f] & open_).mean() * H / 1470))
win_frac = float(np.median(win_frac)) if win_frac else 0.0
# where the window is (union over the open window), for FIT: frame the whole picture inside a small body
union = np.zeros((H // Q, W // Q), bool)
for f in range(f_in + OPEN_FRAMES, min(f_flip + 1, N)):
    union |= bodies[f] & (yy > head_top[f] + keep['cy'])
if union.any():
    ys_, xs_ = np.where(union)
    wb = (xs_.min() * Q, ys_.min() * Q, xs_.max() * Q + Q, ys_.max() * Q + Q)
else:
    wb = (0, 0, W, H)
fit_scale = float(np.clip(max((wb[2] - wb[0] + 120) / W, (wb[3] - wb[1] + 120) / H), 0.55, 1.0))
use_fit = (FIT is True) or (FIT == 'auto' and shot == 'wide' and fit_scale < 0.9)
fit = dict(scale=fit_scale, cx=(wb[0] + wb[2]) / 2, cy=(wb[1] + wb[3]) / 2) if use_fit and fit_scale < 0.99 else None
if win_frac < 0.035:
    decline(f'the speaker\'s body below the chin is barely in the shot ({win_frac * 100:.1f}% of the frame), so '
            'there is no window to open. It needs the shoulders and chest in frame (a selfie that shows the chest '
            'works; a face filling the frame does not).')

# where the body ends (does it run off the bottom, or sit on a floor in the frame)
bottoms = []
for f in span:
    rows = np.where(bodies[f].any(axis=1))[0]
    bottoms.append(rows[-1] * Q if len(rows) else H)
body_bottom = float(np.median(bottoms))
on_floor = body_bottom < H - 60
iris_below = float(np.clip(1.9 * hw, 1.2 * hw, max(1.2 * hw, body_bottom - top_med - 0.4 * hw)))

# the room right outside the outline: pale rooms get a faint shadow outside the line so it reads
plate = next(reader('assets/aroll.mp4', W, H, first=f_in, last=f_in, scale=(W // Q, H // Q)))
bm = bodies[f_in].astype(np.uint8)
ring = (cv2.dilate(bm, np.ones((9, 9), np.uint8)) > 0) & (bm == 0)
room_l = float((plate[ring].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722])).mean()) if ring.any() else 128.0
line_shadow = 0.22 if room_l > 150 else (0.14 if room_l > 90 else 0.08)
acc_l = float(np.dot(ACCENT, (0.2126, 0.7152, 0.0722)))
if abs(acc_l - room_l) < 40:
    say(f'!! the line colour (lightness {acc_l:.0f}) is close to the room around the speaker ({room_l:.0f}): it may '
        'not read before the flip. A darker or lighter ACCENT would.')

side = 'centre' if abs(hcx - W / 2) < 0.12 * W else ('left' if hcx < W / 2 else 'right')
say(f'measured: {shot} shot (head {hw:.0f} px wide, top y {top_med:.0f}, face x {hcx:.0f}, {side}); body ends '
    f'{"in frame at y %.0f (floor shadow on)" % body_bottom if on_floor else "off the bottom edge (no floor shadow)"}; '
    f'frame edges touched: ' + ', '.join(f'{k} {v * 100:.0f}%' for k, v in touch.items()))
say({'tight': 'variant TIGHT: window = chest and shoulders under the chin; keep zone sized to the big head; '
              'iris from the upper chest',
     'medium': 'variant MEDIUM: the demo look; window from the collar down; iris from the chest',
     'wide': 'variant WIDE: small speaker, the window is the whole body below the neck; the flip turns almost the '
             'whole frame into the fill'}[shot]
    + f'. Window at the flip: {win_frac * 100:.0f}% of the safe frame.'
    + (f' FIT on: the picture is framed at {fit["scale"]:.2f}x inside the body, grows to full with the flip.'
       if fit else ' FIT off: the picture is room-sized throughout.'))
say(f'room beside the outline: lightness {room_l:.0f} -> line shadow {line_shadow:.2f}; '
    f'camera: head top moves {top_move:.0f} px, size {hw_ratio:.2f}x (steady enough)')
say(f'timing: line + window from frame {f_in} ({how_in}); flip at frame {f_flip} ({how_flip}); '
    + ('holds to the last frame (T_OUT = cut)' if f_out >= N else f'room back frames {f_out} to {f_end - 1}, plain '
       f'from {f_end}'))

# ---------------------------------------------------------------------------------------------------- fill prep
need = f_end - f_in
fill_out = 'work/fill.mp4'
fx_, fy_ = (float(np.clip(v, 0, 1)) for v in FILL_FOCUS)
cover = (f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,'
         f'crop={W}:{H}:(iw-{W})*{fx_:.3f}:(ih-{H})*{fy_:.3f},setsar=1')
if is_img:
    cmd = [FF, '-v', 'error', '-y', '-loop', '1', '-i', fill_src, '-vf', f'{cover},fps={FPS},format=yuv420p',
           '-frames:v', str(need)]
    how_fill = 'a still image (the push is the only movement)'
else:
    d = subprocess.run([FP, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', fill_src],
                       capture_output=True, text=True).stdout.strip()
    avail = (float(d or 0) - FILL_START) * FPS
    if avail < 6:
        decline(f'the fill clip {fill_src} is too short after FILL_START (it needs about {need / FPS:.1f} s).')
    if avail >= need:
        tempo, how_fill = 1.0, f'{fill_src} plays at normal speed from {FILL_START:.1f}s'
        chain = f'{cover},fps={FPS}'
        cmd = [FF, '-v', 'error', '-y', '-ss', f'{FILL_START:.3f}', '-i', fill_src, '-an', '-vf',
               f'{chain},format=yuv420p', '-frames:v', str(need)]
    elif avail >= 0.5 * need:
        tempo = avail / need
        how_fill = f'{fill_src} is short: slowed to {tempo:.2f}x'
        cmd = [FF, '-v', 'error', '-y', '-ss', f'{FILL_START:.3f}', '-i', fill_src, '-an', '-vf',
               f'setpts=PTS/{tempo:.4f},{cover},fps={FPS},format=yuv420p', '-frames:v', str(need)]
    else:
        how_fill = f'{fill_src} is very short: slowed to 0.5x and played forward then back'
        cmd = [FF, '-v', 'error', '-y', '-ss', f'{FILL_START:.3f}', '-i', fill_src, '-an', '-filter_complex',
               f'[0:v]setpts=2*PTS,{cover},fps={FPS},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,'
               f'loop=-1:size=32767,format=yuv420p[v]', '-map', '[v]', '-frames:v', str(need)]
cmd += ['-c:v', 'libx264', '-crf', '14', '-preset', 'medium', '-g', '15', '-bf', '0', fill_out]
subprocess.run(cmd, check=True)
got = int(subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', fill_out], capture_output=True, text=True)
          .stdout.strip() or 0)
if got < need:
    decline(f'the fill could not be prepared ({got} of {need} frames from {fill_src}).')
say(f'fill: {how_fill}; focus {FILL_FOCUS}, push {FILL_PUSH[0]:.2f} to {FILL_PUSH[1]:.2f} -> work/fill.mp4 ({need} frames)')
# a look at the fill: it must hold no person and no big text (Claude cannot skip this look)
pick = [0, need // 3, 2 * need // 3, need - 1]
frames = []
for i in pick:
    frames.append(next(reader(fill_out, W, H, first=i, last=i, scale=(270, 480))) if i else
                  next(reader(fill_out, W, H, scale=(270, 480))))
cv2.imwrite('work/qa/fill.jpg', cv2.cvtColor(np.concatenate(frames, axis=1), cv2.COLOR_RGB2BGR))
say('LOOK at work/qa/fill.jpg: no person, no big text, nothing the speaker would cover badly.')

# ---------------------------------------------------------------------------------------------------- plan
plan = dict(n=N, f_in=f_in, f_flip=f_flip, f_out=f_out, f_end=f_end, need=need,
            head_top=[round(float(v), 1) for v in head_top], head_cx=[round(float(v), 1) for v in head_cx],
            hw=hw, keep=keep, k_scale=k_scale, iris_below=iris_below, on_floor=on_floor,
            line_shadow=line_shadow, accent=list(ACCENT), line_px=list(LINE_PX), push=list(FILL_PUSH), fit=fit,
            kill=MATTE_KILL_POLYS, frames=dict(line=LINE_FRAMES, open=OPEN_FRAMES, flip=FLIP_FRAMES,
                                               back=BACK_FRAMES))
json.dump(plan, open('work/plan.json', 'w'))

# ---------------------------------------------------------------------------------------------------- sounds
SR = 48000


def wav(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1)
    with wave.open(path, 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((st * 32767).astype('<i2').tobytes())


def band_noise(n, lo, hi, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    fr = np.fft.rfftfreq(n, 1.0 / SR)
    shape = 1 / np.sqrt(np.maximum(fr, 1)) / (1 + (lo / np.maximum(fr, 1)) ** 2) / (1 + (fr / hi) ** 2)   # pinkish
    x = np.fft.irfft(spec * shape, n)
    return x / np.abs(x).max()


def s_air(seed, peak, length=1.2):
    """a soft air swell: pink noise 180 to 1000 Hz, slow in, long out."""
    n = int(SR * length)
    t = np.arange(n) / SR
    x = band_noise(n, 180, 1000, np.random.default_rng(seed))
    env = np.clip(t / 0.45, 0, 1) ** 1.5 * np.where(t < 0.5, 1.0, np.clip(1 - (t - 0.5) / (length - 0.5), 0, 1))
    y = x * env
    return y / np.abs(y).max() * peak


def s_thump(peak):
    """a low thump: a 60 to 20 Hz sweep, fast decay."""
    n = int(SR * 0.7)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * (60 - 20 * t) * t) * np.exp(-7 * t) * np.clip(t / 0.015, 0, 1)
    y *= np.clip((0.7 - t) / 0.3, 0, 1)
    return y / np.abs(y).max() * peak


cues = []
if ENV['SFX']:
    os.makedirs('assets_fx', exist_ok=True)
    plan_sfx = [('air_in', s_air(SEED, 0.10), (f_in - 4) / FPS), ('thump', s_thump(0.16), f_flip / FPS)]
    if f_out < N:
        plan_sfx.append(('air_out', s_air(SEED + 1, 0.06, 0.9), (f_out - 3) / FPS))
    for key, x, t in plan_sfx:
        path = f'assets_fx/insideout-{key}.wav'
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

hold = min(N - 1, (f_flip + FLIP_FRAMES + f_out) // 2)
mk = sorted({0, f_in + 3, f_in + OPEN_FRAMES, f_flip - 1, f_flip + 6, f_flip + FLIP_FRAMES, hold, f_out + 4,
             N - 1} & set(range(N)))
stills = [min(N - 1, f_in + OPEN_FRAMES + 2), min(N - 1, f_flip + 7), hold]
json.dump({'name': NAME, 'frames': N, 'marks': mk, 'stills': stills}, open('work/marks.json', 'w'))
print(f'wrote work/plan.json + index.html  slot "{NAME}"  {N} frames  sounds {len(cues)}  '
      f'switches CAPTIONS={int(ENV["CAPTIONS"])} SFX={int(ENV["SFX"])} SAFE={int(SAFE)}')
print(f'next: bake.py --frames {f_in + OPEN_FRAMES + 2},{f_flip + 7},{hold} -g  (preview), then bake.py')
