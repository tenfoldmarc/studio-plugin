#!/usr/bin/env python3
"""word-pile (Word Pile), step 1: measure the speaker, pick the variant, search the drops, run the physics, write
work/plan.json + work/sim.npz, the sounds in assets_fx/ and index.html. Then bake.py draws the frames.

Things the speaker names drop as solid slabs (real rigid-body physics, seeded, no physics package), glance off the
speaker's head, land on a drawn floor line with a thud and stack, then one gust blows the pile out of frame and the
line leaves. Run from the slot folder:  PY build.py      (PY = the python that has requirements.txt)
"""
import json
import math
import os
import pickle
import re
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool, cpu_count

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import pile_search as PS                                 # noqa: E402
import pile_sim as S                                     # noqa: E402
import slabs as L                                        # noqa: E402
from fxio import reader                                  # noqa: E402

# ==== CLIP (edit this) ====
SLABS = [            # (text, word, weight) in drop order. text: what the slab says ('\n' = two lines); word: when it
    #                  drops: a word from words.json ('budget', 'budget#2' = its 2nd time), seconds, or 'auto'
    #                  (spread from 0.6 s); weight: 1 = normal, over 1.5 = the heavy accent slab (use one, last)
    ('FIRST THING', 'auto', 1.0),
    ('SECOND THING', 'auto', 1.0),
    ('THE\nBIG ONE', 'auto', 2.6),
]
T_SWEEP = 'auto'     # the word the gust blows the pile away on (same forms); 'auto' = 1.7 s after the last drop
SWEEP_DIR = 'auto'   # 'auto' (out on the side the pile is nearest), 'left' or 'right'
FONT = 'Inter Tight'  # slab type: any family in assets/fonts/fonts.css (the buyer's caption font)
WEIGHT = 900         # slab type weight (variable fonts follow it; a static file stays what it is)
CASE = 'upper'       # 'upper', 'lower', 'title' or 'as typed'
TRACK = 0.0          # letter spacing in em (0.02 opens caps up a little)
INK = (255, 248, 239)        # type on the dark slabs (cream)
SLAB = (30, 33, 42)          # dark slab colour (it gets a top-to-bottom shade and an underside)
ACCENT = (250, 230, 122)     # the heavy slab (butter yellow): the buyer's highlight colour
ACCENT_INK = (20, 22, 28)    # type on the heavy slab
LINE = (255, 248, 239)       # the drawn floor line
TYPE_PX = 'auto'     # cap size of the type: 'auto' (66 px, smaller when the pile has little room) or a number
FLOOR_Y = 'auto'     # y of the floor line: 'auto' = 1420 (the safe zone ends at 1470)
SPAWN = 'auto'       # 'auto', 'top' (drop past the head), 'side' (tossed in under the chin, for very tight shots)
CHIN_Y = 'auto'      # lowest chin y over the slot if the printed one is wrong (the pile stays below it)
DROPS = None         # None = search; or a list per slab of dict(x=, ang=, spin=) from a previous printout to pin them
# ==== END CLIP ====

ENV_SFX = os.environ.get('SFX', '1') != '0'
SAFE_ON = os.environ.get('SAFE', '0') not in ('0', '')
W, H, FPS = L.W, L.H, L.FPS
SUB = 4                                                  # physics steps per frame (120 Hz)
Q = 4                                                    # measurement at a quarter of the size
SF = L.SAFE
NAME = os.path.basename(HERE)


def main():
    clip = json.load(open('clip.json'))
    N = int(clip['frames'])
    DUR = N / FPS
    words = json.load(open('words.json')) if os.path.exists('words.json') else []


    def say(msg):
        print('  ' + msg, flush=True)


    # ---------------------------------------------------------------------------------------------------- timing
    def norm(s):
        return re.sub(r'[^a-z0-9]', '', s.lower())


    def audio_env():
        ff = shutil.which('ffmpeg') or 'ffmpeg'
        raw = subprocess.run([ff, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                             capture_output=True).stdout
        a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
        n = len(a) // 160
        return np.sqrt((a[:n * 160].reshape(n, 160) ** 2).mean(axis=1) + 1e-12)


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


    def when(v, default):
        if v is None or v == 'auto':
            v = default
        if isinstance(v, (int, float)):
            return float(v), 'seconds'
        key, nth = (v.split('#') + ['1'])[:2]
        hits = [w for w in words if norm(w['text']) == norm(key)]
        if len(hits) < int(nth):
            sys.exit(f'"{v}" is not in words.json. Words: ' + ' '.join(w['text'] for w in words))
        w = hits[int(nth) - 1]
        t = onset(w)
        return t, f'"{w["text"]}" whisper {w["start"]:.2f}s, audio {t:.2f}s'


    drops = []
    for k, (text, wd, wt) in enumerate(SLABS):
        t, how = when(wd, 0.6 + 0.7 * k)
        drops.append(dict(text=text, t=t, weight=float(wt), heavy=float(wt) > 1.5, how=how))
    for a, b in zip(drops, drops[1:]):
        if b['t'] < a['t'] + 0.3:
            say(f'!! "{b["text"]}" drops only {b["t"] - a["t"]:.2f}s after "{a["text"]}": moved to +0.30 s')
            b['t'] = a['t'] + 0.3
    if drops[0]['t'] < 0.45:
        say(f'!! the first slab drops at {drops[0]["t"]:.2f}s: the line needs ~0.4 s before it. Start the slot earlier.')
    t_sweep, how_sw = when(T_SWEEP, drops[-1]['t'] + 1.7)
    if t_sweep < drops[-1]['t'] + 1.1:
        say(f'!! the gust at {t_sweep:.2f}s leaves the last slab {t_sweep - drops[-1]["t"]:.2f}s to land: moved to +1.1 s')
        t_sweep = drops[-1]['t'] + 1.1
    if t_sweep > DUR - 1.0:
        say(f'!! the gust at {t_sweep:.2f}s leaves no time for the pile and line to leave before the slot ends '
            f'({DUR:.2f}s): moved to {DUR - 1.0:.2f}s. Make the slot longer for a later gust.')
        t_sweep = DUR - 1.0

    # ---------------------------------------------------------------------------------------------------- measure
    t0 = time.time()
    if not os.path.exists('assets/subject.webm'):
        sys.exit('word-pile needs the cutout (assets/subject.webm) to find the head: make the slot without --no-cutout')
    qw, qh = W // Q, H // Q
    al = np.stack(list(reader('assets/subject.webm', W, H, alpha=True, scale=(qw, qh))))
    if len(al) != N:
        say(f'!! the cutout has {len(al)} frames, the slot {N}')
        al = al[:N] if len(al) > N else np.concatenate([al, np.repeat(al[-1:], N - len(al), 0)])


    def head_of(m):
        """quarter-size mask -> (top, cx, width) of the head in quarter px, or None."""
        rows = np.where(m.sum(axis=1) >= 3)[0]
        if not len(rows):
            return None
        top, hw = rows[0], 40.0
        cx = np.where(m[top:top + 6].any(axis=0))[0].mean()
        for _ in range(6):
            xs = np.where(m[top:int(top + 0.45 * hw) + 1].any(axis=0))[0]
            if len(xs):
                cx = xs.mean() if len(xs) < 0.9 * m.shape[1] else cx
            r = min(m.shape[0] - 1, int(top + 0.6 * hw))
            xs = np.where(m[r, int(max(0, cx - 1.3 * hw)):int(cx + 1.3 * hw) + 1])[0]
            if not len(xs):
                break
            hw = max(8.0, float(xs[-1] - xs[0] + 1))
        return float(top), float(cx), float(hw)


    masks = [cv2.morphologyEx((a > 128).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) for a in al]
    heads = [head_of(m) for m in masks]
    found = [h for h in heads if h]
    person = len(found) >= 0.5 * N
    if person:
        for i in range(N):                                   # fill gaps, then a short median against flicker
            if heads[i] is None:
                heads[i] = min(found, key=lambda h: 0)
        arr = np.array(heads, np.float32)
        arr = np.stack([np.median(arr[max(0, i - 2):i + 3], axis=0) for i in range(N)])
        top_, cx_, hw_ = arr[:, 0] * Q, arr[:, 1] * Q, arr[:, 2] * Q
        chin_ = top_ + 1.35 * hw_
        HW = float(np.median(hw_))
        shot = 'tight' if HW > 330 else ('medium' if HW > 150 else 'wide')
        chin_max = float(np.percentile(chin_, 95)) if CHIN_Y == 'auto' else float(CHIN_Y)
        hcx = float(np.median(cx_))
        say(f'measured: {shot} shot, head width {HW:.0f}, head top {np.percentile(top_, 5):.0f}, face centre x {hcx:.0f}, '
            f'chin down to y {chin_max:.0f}, head moves {np.percentile(cx_, 95) - np.percentile(cx_, 5):.0f}px sideways')
    else:
        say('no speaker found in the cutout (voice-over or empty shot): the slabs just drop onto the line')
        shot, HW, hcx, chin_max = 'none', 0.0, W / 2, 600.0
        top_ = cx_ = hw_ = chin_ = np.zeros(N, np.float32)

    head_sdf = np.full((N, qh, qw), 1e4, np.float16)
    him_sdf = np.full((N, qh, qw), 1e4, np.float16)


    def sdf(m):
        if not m.any():
            return np.full(m.shape, 1e4, np.float32)
        out = cv2.distanceTransform((m == 0).astype(np.uint8), cv2.DIST_L2, 5)
        ins = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
        return cv2.GaussianBlur((out - ins) * Q, (0, 0), 0.8)


    face_box = np.zeros((N, 4), np.float32)
    if person:
        for i, m in enumerate(masks):
            t_, c_, w_ = top_[i] / Q, cx_[i] / Q, hw_[i] / Q
            y1 = int(min(qh - 1, (chin_[i]) / Q))
            x0, x1 = int(max(0, c_ - 0.75 * w_)), int(min(qw, c_ + 0.75 * w_ + 1))
            hm = np.zeros_like(m)
            hm[int(t_):y1, x0:x1] = m[int(t_):y1, x0:x1]
            pts = cv2.findNonZero(hm)
            if pts is not None:                              # the deflector: the convex hull of the head (face included)
                hull = cv2.convexHull(pts)
                hm2 = np.zeros_like(m)
                cv2.fillConvexPoly(hm2, hull, 1)
                head_sdf[i] = sdf(hm2)
            him_sdf[i] = sdf(m)
            face_box[i] = (cx_[i] - 0.45 * hw_[i], top_[i] + 0.2 * hw_[i], cx_[i] + 0.45 * hw_[i], chin_[i])
    os.makedirs('work', exist_ok=True)
    np.savez_compressed('work/geom.npz', head=head_sdf, him=him_sdf, scale=Q, person=person)

    # ---------------------------------------------------------------------------------------------------- adapt
    floor_y = 1420.0 if FLOOR_Y == 'auto' else float(FLOOR_Y)
    pile_top = chin_max + 30 if person else 700.0
    avail = floor_y - pile_top
    x_l, x_r = SF['left'] + 9, SF['right_low'] - 8        # the line inside the safe zone (right 100 px clear low down)
    line_w = x_r - x_l
    table = L.font_table(os.path.join('assets', 'fonts'))
    if not table:
        sys.exit('assets/fonts/fonts.css is missing: the slot is incomplete (make it with fx_new.py)')
    look = dict(font=L.pick_font(table, FONT, WEIGHT), case=CASE, track=TRACK, ink=list(INK), slab=list(SLAB), accent=list(ACCENT),
                accent_ink=list(ACCENT_INK), line=list(LINE), rim=0.2, heavy_scale=0.94)
    say(f'font: {os.path.basename(look["font"][0])} at weight {WEIGHT}, case {CASE}')
    heavy_i = [k for k, d in enumerate(drops) if d['heavy']]
    gap_l = (hcx - 0.62 * HW) - SF['left'] if person else W
    gap_r = SF['right'] - (hcx + 0.62 * HW) if person else W
    strip_side = -1 if gap_l >= gap_r else 1


    def sizes_at(px):
        pl = dict(type_px=px, look=look)
        return [L.make_sprite(pl, d['text'], d['heavy'], size_only=True) for d in drops]


    px = 66 if TYPE_PX == 'auto' else float(TYPE_PX)
    while True:
        sz = sizes_at(px)
        h1 = max([s['h'] for k, s in enumerate(sz) if k not in heavy_i] or [s['h'] for s in sz])
        rows = max(0, int((avail - 6) // h1))      # whole rows of slabs between the chin and the line
        hv_w = sum(sz[k]['w'] for k in heavy_i) + 30 * len(heavy_i)
        rest_w = sum(s['w'] for k, s in enumerate(sz) if k not in heavy_i)
        fits = (rows >= 1 and max(s['h'] for s in sz) <= avail - 6 and max(s['w'] for s in sz) <= line_w - 20
                and rest_w + 8 * len(sz) <= (line_w - hv_w) * rows * 0.95 and (not heavy_i or sz[heavy_i[0]]['h'] <= avail - 6))
        if fits or TYPE_PX != 'auto' or px <= 40:
            break
        px -= 4
    if not fits:
        sys.exit(f'WORD PILE DECLINES: the chin sits at y {chin_max:.0f}, which leaves {avail:.0f} px above the floor line '
                 f'(y {floor_y:.0f}) for the pile; it needs about {max(s["h"] for s in sz) + 10:.0f} px and room for '
                 f'{len(drops)} slabs. Use a wider shot, fewer or shorter words.' if person else
                 'WORD PILE DECLINES: the words do not fit on the line even at 40 px: fewer or shorter words.')
    say(f'type {px:.0f} px: slabs ' + ', '.join(f'{s["w"]}x{s["h"]}' for s in sz) + f'; pile room {avail:.0f} px '
        f'(about {rows} row{"s" if rows != 1 else ""}) between the chin and the line at y {floor_y:.0f}')
    h_min = min(s['h'] for s in sz)
    if SPAWN == 'auto':
        spawn = 'top' if (not person or max(gap_l, gap_r) > h_min + 30) else 'side'
        say(f'spawn: {spawn} (open beside the head: left {gap_l:.0f} px, right {gap_r:.0f} px; a slab on end needs '
            f'{h_min + 30:.0f})' + ('' if spawn == 'top' else ': slabs are tossed in from the frame edge under the chin'))
    else:
        spawn = SPAWN
    if heavy_i:
        hw0 = sz[heavy_i[0]]['w'] + 30
        strip = (x_l, x_l + hw0) if strip_side < 0 else (x_r - hw0, x_r)
        say(f'heavy slab lands on the {"left" if strip_side < 0 else "right"} end of the line (the wider side of the head)')
    else:
        strip = None
    # the layout the search aims for: the other slabs pack from the far end of the line, row on row; the heavy one
    # gets its own strip of the line so it lands ON the line (a greedy search without a plan fills the line first)
    a_, b_ = (strip[1] + 10, x_r) if strip and strip_side < 0 else (x_l, strip[0] - 10) if strip else (x_l, x_r)
    from_right = not strip or strip_side < 0
    targets, cur, base, row_h = [], None, floor_y, 0.0
    for k, (d, s) in enumerate(zip(drops, sz)):
        if d['heavy']:
            targets.append(((strip[0] + strip[1]) / 2 if strip else (a_ + b_) / 2, floor_y - s['h'] / 2 - 2, 50))
            continue
        if s['w'] > b_ - a_:
            base, row_h = base - row_h if cur is not None else base, s['h']
            targets.append(((a_ + b_) / 2, base - s['h'] / 2 - 2, 60))
            cur = b_ if from_right else a_
            base -= s['h']
            row_h = 0.0
            continue
        if cur is None or (from_right and cur - s['w'] < a_) or (not from_right and cur + s['w'] > b_):
            if cur is not None:
                base -= row_h
            cur, row_h = (b_ if from_right else a_), 0.0
        cx = cur - s['w'] / 2 - 4 if from_right else cur + s['w'] / 2 + 4
        cur = cx - s['w'] / 2 - 4 if from_right else cx + s['w'] / 2 + 4
        row_h = max(row_h, s['h'])
        targets.append((cx, base - s['h'] / 2 - 2, 55))
    say('plan: ' + ', '.join(f'"{d["text"].split(chr(10))[0]}" at ({t[0]:.0f}, {t[1]:.0f})' for d, t in zip(drops, targets)))

    # ---------------------------------------------------------------------------------------------------- physics + search
    cfg = dict(fps=FPS, sub=SUB, n=N, floor_y=floor_y - 2.0, wall_l=x_l - 6, wall_r=x_r + 6, wall_top=pile_top + 40,
               t_sweep=t_sweep, mid_x=W / 2, sweep_dir={'left': -1, 'right': 1}.get(SWEEP_DIR))
    slab_cfg = []
    for d, s in zip(drops, sz):
        slab_cfg.append(dict(w=s['w'], h=s['h'], weight=d['weight'], t_spawn=1e9, t_word=d['t'], x=W / 2, y=-0.7 * s['h'],
                             ang=0.0, spin=0.0, vx=0.0, vy=1500.0))
    CTX = dict(face=face_box.tolist(), chin=chin_.tolist(), pile_top=pile_top, person=person, strip=strip, heavy=[d['heavy'] for d in drops],
               sizes=sz, words=[d['t'] for d in drops], targets=targets, spawn=spawn, floor_y=floor_y, sweep_f=int(t_sweep * FPS))
    def spawn_params(k, x=None, ang=0.0, spin=0.0, side=None, y=None, vx=None):
        c = slab_cfg[k]
        if spawn == 'side':
            return dict(t_spawn=c['t_word'] - 0.08, x=-0.6 * c['w'] if side < 0 else W + 0.6 * c['w'], y=y,
                        vx=-side * vx, vy=-380.0, ang=ang, spin=spin)
        return dict(t_spawn=c['t_word'] - 0.05, x=x, y=-0.7 * c['h'], vx=0.0, vy=1500.0, ang=ang, spin=spin)


    def candidates(k):
        c = slab_cfg[k]
        out = []
        if spawn == 'side':
            y0 = pile_top + 20
            for side in (-1, 1):
                for y in (y0, y0 + 90, y0 + 180):
                    for vx in (650.0, 950.0, 1250.0):
                        for ang in (-12.0, 0.0, 12.0):
                            out.append(spawn_params(k, side=side, y=min(y, floor_y - c['h']), vx=vx, ang=ang,
                                                    spin=1.2 if side < 0 else -1.2))
            return out
        lo, hi = int(SF['left'] + 30 + c['w'] * 0.25), int(SF['right'] - 30 - c['w'] * 0.25)
        for x in range(lo, hi + 1, 50):
            # long slabs only get past the head nearly on end, then topple onto the line or the stack
            for ang in (-72.0, -54.0, -36.0, -18.0, 0.0, 18.0, 36.0, 54.0, 72.0):
                for spin in (-1.6, 0.0, 1.6):
                    out.append(spawn_params(k, x=float(x), ang=ang, spin=spin))
        return out


    G = PS.load_fields()
    world = S.World(cfg, [dict(c) for c in slab_cfg], G['head'], G['him'])
    workers = max(1, min(4, cpu_count() - 1))
    chosen = []
    pool = Pool(workers, initializer=PS.init, initargs=(CTX,)) if DROPS is None else None
    for k in range(len(drops)):
        f_spawn = int(math.floor((drops[k]['t'] - 0.1) * FPS))
        world.run(max(0, f_spawn))
        if DROPS is not None:
            best = spawn_params(k, **DROPS[k]) if spawn == 'top' else dict(DROPS[k])
            say(f'slab {k} "{drops[k]["text"]}": pinned {best}')
        else:
            fe = min(CTX['sweep_f'] - 1, int((drops[k]['t'] + 1.6) * FPS), N - 1)
            if k + 1 < len(drops):
                fe = min(fe, max(f_spawn + 20, int((drops[k + 1]['t'] + 0.9) * FPS)))
            head, him = world.head, world.him
            world.head = world.him = None
            blob = pickle.dumps(world)
            world.head, world.him = head, him
            jobs = [(blob, k, p, fe) for p in candidates(k)]
            res = pool.map(PS.job, jobs, chunksize=2)
            order = sorted(range(len(res)), key=lambda i: (res[i][0], i))
            best = res[order[0]][1]
            say(f'slab {k} "{drops[k]["text"]}": {len(jobs)} drops tried, best score {res[order[0]][0]:.0f} '
                f'{res[order[0]][2]}  (x {best["x"]:.0f}, lean {best["ang"]:.0f}, spin {best["spin"]})')
            if res[order[0]][0] > 300 or os.environ.get('DEBUG'):
                for i in order[1:5]:
                    say(f'     also {res[i][0]:.0f} x {res[i][1]["x"]:.0f} lean {res[i][1]["ang"]:.0f} spin {res[i][1]["spin"]} {res[i][2]}')
            if res[order[0]][0] > 900:
                say(f'   !! no clean drop for "{drops[k]["text"]}": check the preview, try a shorter text or TYPE_PX smaller')
        world.bodies[k].cfg.update(best)
        chosen.append({kk: best[kk] for kk in ('x', 'ang', 'spin')} if spawn == 'top' else best)
    if pool:
        pool.close()
    world.run(N)
    ev = world.events()
    track = world.track
    np.save('work/track.npy', track)
    say('drops: ' + json.dumps([{kk: round(v, 1) if isinstance(v, float) else v for kk, v in c.items()} for c in chosen]))
    # line timing: draws before the first drop, leaves once the last slab has left the frame
    fr = track[:, ::SUB]
    f_sw = int(t_sweep * FPS)
    gone = N - 1
    for f in range(f_sw, N):
        if all(np.isnan(fr[i, f, 0]) or not (-math.hypot(s['w'], s['h']) / 2 - 30 < fr[i, f, 0] < W + math.hypot(s['w'], s['h']) / 2 + 30
                                            and fr[i, f, 1] < H + 200) for i, s in enumerate(sz)):
            gone = f
            break
    sweep_dir = world.sweep_dir or 1
    line = dict(y=floor_y, x0=x_l, x1=x_r, px=4, t_draw=max(3 / FPS, drops[0]['t'] - 0.42), draw_s=0.30, draw_dir=1,
                undraw_s=0.30, t_undraw=gone / FPS + 0.03, undraw_dir=-1 if sweep_dir < 0 else 1, dip_px=3.5)
    t_clear = line['t_undraw'] + line['undraw_s']
    if t_clear > DUR - 3 / FPS:
        say(f'!! the line is still leaving at {t_clear:.2f}s, the slot ends at {DUR:.2f}s: make the slot longer or the gust earlier')
    pl = dict(n=N, sub=SUB, type_px=px, look=look, slabs=[dict(text=d['text'], heavy=d['heavy']) for d in drops], sizes=sz,
              heavy=[d['heavy'] for d in drops], events=ev, line=line, thick=11, shot=shot, spawn=spawn, safe=SAFE_ON)
    json.dump(pl, open('work/plan.json', 'w'), indent=1)
    for k, (d, e) in enumerate(zip(drops, ev)):
        say(f'"{d["text"]}" drops {d["t"]:.2f}s ({d["how"]}); ' + (f'hits him {e["hit_t"]:.2f}s{" (head)" if e["head"] else ""}; ' if e['hit_t'] else 'misses him; ')
            + (f'line {e["floor_t"]:.2f}s' if e['floor_t'] else 'rests on the stack') + f'; rests at x {track[k, f_sw * SUB - 1, 0]:.0f} '
            f'y {track[k, f_sw * SUB - 1, 1]:.0f} lean {math.degrees(track[k, f_sw * SUB - 1, 2]):.0f}')
    say(f'gust {t_sweep:.2f}s ({how_sw}) to the {"left" if sweep_dir < 0 else "right"}; pile gone {gone / FPS:.2f}s; '
        f'line leaves {line["t_undraw"]:.2f} to {t_clear:.2f}s; slot ends {DUR:.2f}s')

    # ------------------------------------------------------------------------------------------------ sounds + html
    cues = []
    if ENV_SFX:
        os.makedirs('assets_fx', exist_ok=True)
        for k, (d, e) in enumerate(zip(drops, ev)):
            if e['floor_t'] is not None and e['floor_t'] < t_sweep:
                p = f'assets_fx/thud_{k}.wav'
                L.floor_thud(p, 64 if d['heavy'] else 88 + 5 * (k % 3), 0.36 if d['heavy'] else 0.24, 0.9, seed=3 + k)
                cues.append((p, e['floor_t'], 0.30 * (1.6 if d['heavy'] else 1.0) * 0.75, 0.36))
            ts = e['slab_t']
            if ts is not None and ts < t_sweep and (e['floor_t'] is None or abs(ts - e['floor_t']) > 0.09):
                p = f'assets_fx/knock_{k}.wav'
                L.floor_thud(p, 150 if d['heavy'] else 190, 0.12, 0.9, seed=11 + k)
                cues.append((p, ts, 0.21 * (1.2 if d['heavy'] else 1.0) * 0.75, 0.12))
        L.gust('assets_fx/gust.wav')
        cues.append(('assets_fx/gust.wav', max(0.0, t_sweep - 0.06), 0.42 * 0.75, 0.75))
    tags = []
    for i, (p, t, vol, ln) in enumerate(cues):
        d = min(ln, DUR - t)
        if d > 0.03:
            tags.append(f'  <audio id="sfx_{i}" src="{p}" data-start="{t:.3f}" data-media-start="0" data-duration="{d:.3f}" '
                        f'data-track-index="{10 + i}" data-volume="{min(1.0, vol):.3f}"></audio>')
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
{nl.join(tags)}
  <video id="bgv" src="assets/fx.mp4" muted playsinline data-start="0" data-media-start="0" data-duration="{DUR:.3f}" data-track-index="0"></video>
{SAFE_GUIDE if SAFE_ON else ''}
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
    lands = [int(round((e['floor_t'] or d['t'] + 0.5) * FPS)) for d, e in zip(drops, ev)]
    marks = sorted({0, int(drops[0]['t'] * FPS) + 4, *[min(N - 1, f + 3) for f in lands], f_sw - 2, min(N - 1, f_sw + 6),
                    min(N - 1, int(line['t_undraw'] * FPS) + 4), N - 1} & set(range(N)))
    stills = [min(N - 1, lands[0] + 3), f_sw - 2, min(N - 1, f_sw + 5)]
    json.dump({'name': NAME, 'frames': N, 'marks': marks, 'stills': stills}, open('work/marks.json', 'w'))
    secs = time.time() - t0
    print(f'wrote work/plan.json, work/track.npy, index.html  slot "{NAME}" {N} frames, {len(tags)} sounds, {secs:.0f}s '
          f'({secs / DUR:.1f}s per second of slot)  switches SFX={int(ENV_SFX)} SAFE={int(SAFE_ON)}')
    print('next: bake.py --frames ' + ','.join(str(f) for f in (stills[0], f_sw - 2, min(N - 1, f_sw + 5))) + ' -g  (preview), then bake.py')



if __name__ == '__main__':
    main()
