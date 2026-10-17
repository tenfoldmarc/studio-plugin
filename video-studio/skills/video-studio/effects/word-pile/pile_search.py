"""word-pile drop search: the worker side (scores one candidate drop). build.py runs a process pool over these."""
import math
import pickle

import cv2
import numpy as np

import pile_sim as S
from slabs import FPS, H, SAFE as SF, W

G = {}


def load_fields(path='work/geom.npz'):
    g = np.load(path)
    person = bool(g['person'])
    return dict(head=S.Field(g['head'], int(g['scale'])) if person else None,
                him=S.Field(g['him'], int(g['scale'])) if person else None)


def init(ctx):
    G.update(load_fields())
    G['ctx'] = ctx


def job(args):
    blob, k, params, fe = args
    wd = pickle.loads(blob)
    wd.head, wd.him = G['head'], G['him']
    wd.bodies[k].cfg.update(params)
    try:
        wd.run(fe)
        sc, notes = score(wd, k, G['ctx'], fe)
    except Exception as e:                               # a bad drop must not kill the pool
        sc, notes = 1e6, [repr(e)]
    return sc, params, notes


def score(wd, k, ctx, fe):
    """Lower is better: the slab lands readable on the line or the stack, stays off the face, leaves room."""
    SUB = wd.c['sub']
    tr = wd.track[:, :fe * SUB:SUB]
    ev = wd.events()
    pen, notes = 0.0, []
    polys = []
    for j in range(k + 1):
        s = ctx['sizes'][j]
        p, p0 = tr[j, fe - 1], tr[j, max(0, fe - 6)]
        if np.isnan(p[0]):
            return 1e6, ['not spawned']
        cs = np.array(S.corners(p[0], p[1], p[2], s['w'], s['h']))
        polys.append(cs)
        if cs[:, 1].min() > H or cs[:, 0].max() < 0 or cs[:, 0].min() > W:
            return 1e6, [f'{j} fell out']
        if abs(p[0] - p0[0]) + abs(p[1] - p0[1]) > 4 or abs(p[2] - p0[2]) > 0.03:
            pen += 150
            notes.append(f'{j} moving')
        if cs[:, 0].min() < SF['left'] - 10 or cs[:, 0].max() > SF['right'] + 10 or cs[:, 1].max() > SF['bottom'] or \
                any(c[1] > SF['right_low_y'] and c[0] > SF['right_low'] + 10 for c in cs):
            pen += 400
            notes.append(f'{j} unsafe')
        raw = abs((math.degrees(p[2]) + 180) % 360 - 180)
        if raw > 75:
            pen += 1500
            notes.append(f'{j} on end or flipped ({raw:.0f} deg)')
        heavy = ctx['heavy'][j]
        pen += max(0.0, raw - (8 if heavy else 26)) * (15 if heavy else 6)
        pen += max(0.0, ctx["floor_y"] - cs[:, 1].min() - s["h"] - 8) * 0.25     # prefer a low, wide pile
        if cs[:, 1].min() < ctx['pile_top']:
            pen += (ctx['pile_top'] - cs[:, 1].min()) * 2.5
            notes.append(f'{j} too high (top {cs[:, 1].min():.0f})')
        if ctx['strip'] and not heavy and any(ctx['heavy'][m] for m in range(j + 1, len(ctx['heavy']))):
            if cs[:, 1].max() > ctx['floor_y'] - 215:
                ov = min(cs[:, 0].max(), ctx['strip'][1]) - max(cs[:, 0].min(), ctx['strip'][0])
                if ov > 0:
                    pen += ov * 2.0
                    notes.append(f'{j} on the heavy strip')
    s = ctx['sizes'][k]
    f_drop = int(ctx['words'][k] * FPS)
    live = [f for f in range(f_drop, fe) if not np.isnan(tr[k, f, 0])]
    if ctx['person']:
        high = sum(1 for f in live if tr[k, f, 1] < ctx['chin'][f])
        if high > 24:
            pen += (high - 24) * 25
            notes.append(f'{k} hangs {high}f')
        for f in live:
            x0, y0, x1, y1 = ctx['face'][f]
            cs = np.array(S.corners(*tr[k, f], s['w'], s['h']), np.float32)
            box = np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], np.float32)
            inter, _ = cv2.intersectConvexConvex(cs, box)
            if inter > 60:
                pen += 2500
                notes.append(f'{k} over the face @{f}')
                break
        if ctx['spawn'] == 'top':
            if ev[k]['hit_t'] is None:
                pen += 250
                notes.append(f'{k} missed him')
            elif not ev[k]['head']:
                pen += 60
    if ev[k]['wall_lean'] > 0.12:
        pen += (ev[k]['wall_lean'] - 0.12) * 900
        notes.append(f'{k} leans on a wall')
    ref = tr[k, fe - 1]
    f_set = f_drop
    for f in range(fe - 1, f_drop, -1):
        pq = tr[k, f]
        if np.isnan(pq[0]) or abs(pq[0] - ref[0]) + abs(pq[1] - ref[1]) > 30 or abs(pq[2] - ref[2]) > 0.2:
            f_set = f
            break
    if (f_set - f_drop) / FPS > 1.35:
        pen += ((f_set - f_drop) / FPS - 1.35) * 700
        notes.append(f'{k} settles late')
    if ctx['heavy'][k]:
        if ev[k]['floor_t'] is None:
            pen += 600
            notes.append(f'{k} never touched the line')
        elif ev[k]['floor_t'] - ctx['words'][k] > 1.25:
            pen += 450
            notes.append(f'{k} reached the line late')
    tg = ctx['targets'][k]                               # the planned spot (soft): keeps the pile coherent
    pk = tr[k, fe - 1]
    dist = math.hypot(pk[0] - tg[0], pk[1] - tg[1])
    if dist > tg[2]:
        pen += (dist - tg[2]) * 3.0
        notes.append(f'{k} {dist:.0f}px off plan')
    q = 4.0
    sw_, sh_ = int(W / q), int(H / q)
    for j in range(k):                                   # how much of each earlier slab's type the later ones cover
        sj, pj = ctx['sizes'][j], tr[j, fe - 1]
        tm = np.zeros((sh_, sw_), np.uint8)
        cv2.fillPoly(tm, [np.round(np.array(S.corners(pj[0], pj[1], pj[2], sj['w'] * 0.84, sj['h'] * 0.58)) / q).astype(np.int32)], 1)
        cover = np.zeros_like(tm)
        for m in range(j + 1, k + 1):
            cv2.fillPoly(cover, [np.round(polys[m] / q).astype(np.int32)], 1)
        vis = 1.0 - float((tm & cover).sum()) / max(1.0, float(tm.sum()))
        if vis < 0.8:
            pen += (0.8 - vis) * 700
            notes.append(f'{j} vis {vis:.2f}')
    return pen, notes
