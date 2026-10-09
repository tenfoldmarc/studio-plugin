#!/usr/bin/env python3
"""knockout-tiles / prep: measures the clip so build.py never needs pixel numbers typed in by hand.

  python prep.py words    every spoken word with its frame (Whisper's start next to the frame the voice really starts)
  python prep.py          1. turns every 'at' of the CLIP block (word or frame) into a frame
                          2. reads the speaker's cutout: where the head is on every frame of the effect, and which
                             parts of the wall stay clear while each piece is up
                          3. puts each tile, each receipt pile and the total on clear wall inside the safe zone
                          -> work/layout.json (build.py reads it) and work/layout.jpg (LOOK at it)

Run from the slot folder with a python that has numpy and Pillow. Takes a few seconds. Run it again after ANY change
to the CLIP block; build.py refuses a layout made for other values.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys

import numpy as np

import build as B

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
FF = shutil.which('ffmpeg') or 'ffmpeg'
GW, GH, G = 270, 480, 4          # measuring grid: the 1080 x 1920 frame at quarter size
S = B.SAFE


def words_table():
    """[(text, whisper frame, onset frame)]: onset = first frame within 5 of Whisper's guess where the level rises out of a dip"""
    if not os.path.exists('words.json'):
        return [], None
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 1600
    db = np.array([20 * np.log10(np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(len(a) // hop)])
    thr = np.percentile(db, 10) + .45 * (np.percentile(db, 90) - np.percentile(db, 10))
    out = []
    for w in json.load(open('words.json')):
        f = round(w['start'] * 30)
        best = None
        for n in range(max(1, f - 5), min(len(db), f + 6)):
            if db[n] >= thr and (db[n - 1] < thr or db[n] - db[n - 1] > 6) and (best is None or abs(n - f) < abs(best - f)):
                best = n
        out.append((w['text'], f, best if best is not None else f))
    return out, db


def norm(s):
    return ''.join(c for c in s.lower() if c.isalnum())


def resolve(at, table, nfr):
    if isinstance(at, (int, float)):
        f = int(at)
    else:
        word, _, nth = str(at).partition('#')
        hits = [on for text, _, on in table if norm(text) == norm(word)]
        n = int(nth) if nth else 1
        if len(hits) < n:
            said = ' '.join(t for t, _, _ in table)
            sys.exit(f'"{at}": the word is not said {"that often " if hits else ""}in this slot. Words heard: {said}\n'
                     'Whisper mishears names: use the word it wrote, or the frame number (prep.py words).')
        f = hits[n - 1]
    if not 0 <= f < nfr:
        sys.exit(f'"{at}" = frame {f}, outside the slot (0 to {nfr - 1})')
    return f


def masks(nfr):
    src = 'assets/subject.webm'
    if not os.path.exists(src):
        sys.exit('assets/subject.webm is missing: this effect needs the speaker cut out (make the slot with the cutout)')
    raw = subprocess.run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', src, '-vf', f'alphaextract,scale={GW}:{GH}:flags=area',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    m = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW) > 127
    if len(m) != nfr:
        sys.exit(f'the cutout has {len(m)} frames, the clip {nfr}: remake the cutout, it would drift')
    return m


def head_of(m, hint=None):
    """(centre x, top, width, bottom, sure) of the head on one frame, grid units: walks down from the top of the
    silhouette, following the body's own run of pixels, until the run narrows into the neck. hint = head width of the
    last frame that had a clear neck"""
    rows = np.where(m.sum(1) >= 2)[0]
    if not len(rows):
        return None
    top = int(rows[0])
    xs = np.where(m[top])[0]
    lo, hi, runs = int(xs[0]), int(xs[-1]), []
    for y in range(top, GH):
        a = max(0, lo - 3)
        seg = np.where(m[y, a:hi + 4])[0]
        if not len(seg):
            break
        lo, hi = a + int(seg[0]), a + int(seg[-1])
        while lo > 0 and m[y, lo - 1]:
            lo -= 1
        while hi < GW - 1 and m[y, hi + 1]:
            hi += 1
        runs.append((lo, hi))
    # the head ends where the run narrows into the neck and widens again, or (no visible neck) where the
    # silhouette is 1.25 times as deep as it is wide
    mx, neck, end = 0, None, None
    for k, (l, h) in enumerate(runs):
        w = h - l + 1
        if neck is None:
            if mx and k >= .5 * mx and w < .8 * mx:
                neck = k
            elif mx and k >= 1.25 * mx:
                end = k
                break
            else:
                mx = max(mx, w)
        elif w > 1.05 * mx or k >= 1.45 * mx:
            end = k
            break
    sure = end is not None and not (hint and mx > 1.5 * hint)
    if not sure and hint:        # no neck on this frame (leaning in, a hand at the chin): keep the last sure head size
        mx, end = int(hint), min(len(runs), int(1.45 * hint))
    elif not sure:               # never seen a neck (a hood, long hair): take the row where it is as deep as wide
        end = next((k for k, (l, h) in enumerate(runs) if k >= h - l + 1), len(runs))
        mx = max(6, int(.8 * end))
    if mx < 6:
        return None
    wide = [(l + h) / 2 for l, h in runs[:end] if .8 * mx <= h - l + 1 <= 1.3 * mx] or [sum(runs[min(len(runs) - 1, int(.45 * mx))]) / 2]
    return float(np.median(wide)), top, mx, top + end, sure


class Wall:
    """how much of a rectangle the speaker covers while a piece is up (0 = clear wall, 1 = always behind them)"""

    def __init__(self, m, a, b):
        p = m[max(0, a):b + 1].mean(0)
        self.ii = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def cover(self, x0, y0, x1, y1):
        x0, y0, x1, y1 = [int(round(v / G)) for v in (x0, y0, x1, y1)]
        x0, x1, y0, y1 = max(0, x0), min(GW, x1), max(0, y0), min(GH, y1)
        if x1 <= x0 or y1 <= y0:
            return 1.0
        ii = self.ii
        return float(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]) / ((x1 - x0) * (y1 - y0))


def bbox(W, H, rot, pad=0):
    r = math.radians(abs(rot))
    return W * math.cos(r) + H * math.sin(r) + 2 * pad, W * math.sin(r) + H * math.cos(r) + 2 * pad


def find(wall, W, H, bw, bh, pref, region):
    """centre of the W x H piece (bounding box bw x bh) inside region that is clearest of the speaker and nearest pref"""
    x0, y0, x1, y1 = region
    best = None
    for y in range(int(math.ceil(y0 + bh / 2)), int(y1 - bh / 2) + 1, 8):
        for x in range(int(math.ceil(x0 + bw / 2)), int(x1 - bw / 2) + 1, 8):
            if y + bh / 2 > S['low_y'] and x + bw / 2 > S['right_low']:
                continue
            ov = wall.cover(x - W / 2, y - H / 2, x + W / 2, y + H / 2)
            cost = 4000 * max(0, ov - .015) + abs(x - pref[0]) + .9 * abs(y - pref[1])
            if best is None or cost < best[0]:
                best = (cost, x, y, ov)
    return best and best[1:]


def region_for(spot, hd, wallbox, low):
    if spot == 'above':
        r = [S['left'], S['top'], S['right'], hd['top'] - 14]
    elif spot == 'left':
        r = [S['left'], S['top'], hd['cx'], low]
    else:
        r = [hd['cx'], S['top'], S['right'], low]
    if wallbox:
        r = [max(r[0], wallbox[0]), max(r[1], wallbox[1]), min(r[2], wallbox[2]), min(r[3], wallbox[3])]
    return r


def pref_for(spot, hd, W, H):
    hh = hd['bottom'] - hd['top']
    if spot == 'above':
        return hd['cx'], hd['top'] - 24 - H / 2
    y = hd['top'] + .45 * hh
    return (hd['x0'] - 26 - W / 2, y) if spot == 'left' else (hd['x1'] + 26 + W / 2, y)


def main():
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    table, db = words_table()
    if len(sys.argv) > 1 and sys.argv[1] == 'words':
        print(f'slot: {nfr} frames ({nfr / 30:.2f}s)\nword            whisper  onset   (use the onset frame, or the word itself, as "at")')
        seen = {}
        for text, f, on in table:
            seen[norm(text)] = seen.get(norm(text), 0) + 1
            tag = f'#{seen[norm(text)]}' if seen[norm(text)] > 1 else ''
            print(f'{(text + tag)[:14]:14s}  f{f:4d}    f{on:4d}')
        return
    warn = []
    at = {str(a): resolve(a, table, nfr) for a in B.ats()}
    sch = B.schedule(at, nfr)
    m = masks(nfr)
    rng = random.Random(B.SEED)

    # the head while the effect is up
    per, hint = {}, None
    for f in range(nfr):
        h = head_of(m[f], hint)
        if h:
            per[f] = h
            hint = h[2] if h[4] else hint

    def head_in(a, b):
        """the head while one piece is up (frames a to b): it may sit differently from the rest of the slot"""
        hs = [per[f] for f in range(max(0, a), min(nfr - 1, b) + 1) if f in per]
        if len(hs) < 3:
            sys.exit(f'could not find the speaker in the cutout on frames {a} to {b}: check assets/subject.webm')
        w = float(np.median([h[2] for h in hs])) * G
        return dict(cx=float(np.median([h[0] for h in hs])) * G, top=min(h[1] for h in hs) * G, w=w,
                    bottom=float(np.median([h[3] for h in hs])) * G,
                    x0=min(h[0] for h in hs) * G - w / 2, x1=max(h[0] for h in hs) * G + w / 2)

    hd = head_in(sch['f_in'], sch['f_out'])
    hh = hd['bottom'] - hd['top']
    if hd['top'] < S['top'] - 30:
        warn.append(f'the head reaches y {hd["top"]:.0f}, inside the top 220 px: nothing fits above it and side tiles sit low')
    if hd['x1'] - hd['x0'] > 2.2 * hd['w'] or max(per[f][1] for f in per if sch['f_in'] <= f <= sch['f_out']) * G - hd['top'] > .5 * hh:
        warn.append('the speaker moves a lot while the effect is up: each piece is placed for its own frames, check work/layout.jpg')

    # ---- tiles
    tiles, prev = [], None
    order = [s for s in B.STYLE['order'] if s in ('left', 'right', 'above')] or ['left', 'right']
    for k, t in enumerate(B.TILES):
        wall = Wall(m, sch['land'][k] - 4, sch['knock'][k] + 6)
        hk = head_in(sch['land'][k] - 4, sch['knock'][k] + 6)
        want = t.get('spot') or order[k % len(order)]
        tries = [want] if t.get('spot') else [want] + [s for s in order[k % len(order) + 1:] + order[:k % len(order)]]
        if not t.get('spot') and prev in tries and len(tries) > 1:      # not twice in a row on the same spot if another fits
            tries = [s for s in tries if s != prev] + [prev]
        got = None
        for spot in tries:
            rot = B.ROT[spot] + rng.uniform(-.8, .8)
            for sc in (1, .92, .85, .78, .7):
                W, H, fs = B.tile_size(t['text'], spot, sc)
                bw, bh = bbox(W, H, rot, 6)
                bw += 44                                   # the strike-through overhangs the tile on both sides
                if spot in B.SPOTS:
                    x, y = B.SPOTS[spot]
                    inside = (S['left'] <= x - bw / 2 and x + bw / 2 <= S['right'] and S['top'] <= y - bh / 2 and y + bh / 2 <= S['bottom'])
                    hit = (x, y, wall.cover(x - W / 2, y - H / 2, x + W / 2, y + H / 2)) if inside else None
                    lim = .5
                else:
                    hit = find(wall, W, H, bw, bh, pref_for(spot, hk, W, H),
                               region_for(spot, hk, B.WALL, hk['bottom'] + .7 * (hk['bottom'] - hk['top'])))
                    lim = .06
                if hit and hit[2] <= lim and (got is None or sc > got['scale']):
                    got = dict(spot=spot, x=int(hit[0]), y=int(hit[1]), w=W, h=H, fs=fs, rot=round(rot, 2), scale=sc, cover=round(hit[2], 3))
                    break
            if got:
                break
        if not got:
            sys.exit(f'tile "{t["text"]}" has no clear wall inside the safe zone on {" / ".join(tries)}. Use a wider shot, a '
                     'shorter name, set SPOTS by hand from the frame, or leave this effect out for this clip.')
        if got['spot'] != want:
            warn.append(f'tile "{t["text"]}": no room on "{want}", placed on "{got["spot"]}"')
        if got['scale'] < 1:
            warn.append(f'tile "{t["text"]}" shrunk to {got["scale"]:.2f} to fit: check it still reads on a phone')
        tiles.append(got)
        prev = got['spot']
    sch = B.schedule(at, nfr, [g['spot'] for g in tiles])

    # ---- receipts and total
    recs, total = [], None
    rc = B.receipts()
    if rc:
        sides = [(B.RECEIPT_FIRST_SIDE, 'right' if B.RECEIPT_FIRST_SIDE == 'left' else 'left')[i % 2] for i in range(len(rc))]
        col = {}
        for side in set(sides):
            idx = [i for i, s in enumerate(sides) if s == side]
            wall = Wall(m, sch['rec'][idx[0]] - 4, sch['wipe'] + 8)
            hk = head_in(sch['rec'][idx[0]] - 4, sch['wipe'] + 8)
            for sc in (1, .9, .8, .72):
                W, H = B.RW * B.SIZE * sc, (B.RH + B.RSTEP * (len(idx) - 1)) * B.SIZE * sc
                bw, bh = W + 40, H + 26
                if side in B.PILES:
                    hit = (*B.PILES[side], 0)
                else:
                    px, py = pref_for(side, hk, W, H)
                    hit = find(wall, W, H, bw, bh, (px, hk['top'] + .5 * (hk['bottom'] - hk['top'])),
                               region_for(side, hk, B.WALL, hk['bottom'] + 1.3 * (hk['bottom'] - hk['top'])))
                if hit and hit[2] <= .08:
                    col[side] = (hit[0], hit[1], H, sc)
                    break
            if side not in col:
                sys.exit(f'no clear wall for the {side} receipt pile ({len(idx)} receipts). Use fewer receipts, set PILES by hand, '
                         'or RECEIPTS_ON = False.')
            if col[side][3] < 1:
                warn.append(f'{side} receipt pile shrunk to {col[side][3]:.2f}: check the amounts still read on a phone')
        tilt = {'left': [-3, 3.5, -3, 3], 'right': [2.5, -3.5, 3, -3]}
        nudge = [-8, 10, -10, 6]
        count = {'left': 0, 'right': 0}
        for i, side in enumerate(sides):
            j = count[side]
            count[side] += 1
            px, py, H, sc = col[side]
            recs.append(dict(side=side, slot=j, x=int(px + nudge[j] * sc), y=int(py + H / 2 - B.RH * B.SIZE * sc / 2 - B.RSTEP * B.SIZE * sc * j),
                             rot=tilt[side][j], scale=sc))
        if sch['total'] is not None:
            final = B.money(sum(r['amount'] for r in rc))
            wall = Wall(m, sch['total'] - 4, sch['wipe'] + 8)
            hk = head_in(sch['total'] - 4, sch['wipe'] + 8)
            for sc in (1, .9, .8, .7):
                k = B.SIZE * sc
                W, H = round((52 + sum((30 if c == ',' else 72) + 6 for c in final)) * k), round(118 * k)
                tag_w = round((len(B.TOTAL_TAG) * 18 + 40) * k) if B.TOTAL_TAG else 0
                ext = 41 * k if B.TOTAL_TAG else 0
                bw, bh = max(W, tag_w) + 70, H + ext + 16
                if B.TOTAL_POS:
                    total = dict(x=int(B.TOTAL_POS[0]), y=int(B.TOTAL_POS[1]), w=W, h=H, scale=sc, tag_w=tag_w)
                    break
                reg = region_for('above', hk, B.WALL, 0)
                hit = find(wall, max(W, tag_w), H + ext, bw, bh, (hk['cx'], hk['top'] - 24 - (H + ext) / 2), reg)
                if hit and hit[2] <= .08:
                    total = dict(x=int(hit[0]), y=int(hit[1] - ext / 2), w=W, h=H, scale=sc, tag_w=tag_w)
                    break
            if not total:
                sys.exit(f'no room above the head for the running total (the head tops out at y {hk["top"]:.0f} while it is up, the plate needs '
                         f'about {round(118 * B.SIZE * .7 + 60)} px under the 220 px line). Set TOTAL_POS = (x, y) by hand from the frame, or '
                         'TOTAL_AT = None for receipts without a total.')
            if total['scale'] < 1:
                warn.append(f'total shrunk to {total["scale"]:.2f} to fit above the head')

    os.makedirs('work', exist_ok=True)
    lay = dict(sig=B.signature(), frames=nfr, at=at, head={k: round(v, 1) for k, v in hd.items()}, tiles=tiles, receipts=recs,
               total=total, warnings=warn)
    json.dump(lay, open('work/layout.json', 'w'), indent=1)
    picture(lay, sch, nfr)
    print(f'head: centre x {hd["cx"]:.0f}, y {hd["top"]:.0f} to {hd["bottom"]:.0f}, width {hd["w"]:.0f} (moves x {hd["x0"]:.0f} to {hd["x1"]:.0f})')
    for t, g in zip(B.TILES, tiles):
        print(f'  tile "{t["text"]}": {g["spot"]} at ({g["x"]}, {g["y"]}) {g["w"]} x {g["h"]}, size {g["scale"]:.2f}, behind the speaker {g["cover"] * 100:.0f}%')
    for i, g in enumerate(recs):
        print(f'  receipt {i + 1}: {g["side"]} at ({g["x"]}, {g["y"]}), size {g["scale"]:.2f}')
    if total:
        print(f'  total: ({total["x"]}, {total["y"]}) {total["w"]} x {total["h"]}, size {total["scale"]:.2f}')
    for x in warn:
        print('WARNING:', x)
    print('wrote work/layout.json and work/layout.jpg: LOOK at the picture, then build.py')


def picture(lay, sch, nfr):
    """work/layout.jpg: a frame from the middle of the effect with every piece drawn where it will sit"""
    from PIL import Image, ImageDraw
    f = min(nfr - 1, (sch['f_in'] + sch['f_out']) // 2)
    raw = subprocess.run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-vf', f"select='eq(n,{f})',scale=540:960", '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    im = Image.frombytes('RGB', (540, 960), raw) if len(raw) == 540 * 960 * 3 else Image.new('RGB', (540, 960), (40, 40, 40))
    d = ImageDraw.Draw(im)
    q = lambda *v: [x / 2 for x in v]
    for box in ((0, 0, 1080, S['top']), (0, S['bottom'], 1080, 1920), (0, S['top'], S['left'], S['bottom']),
                (S['right'], S['top'], 1080, S['low_y']), (S['right_low'], S['low_y'], 1080, S['bottom'])):
        d.rectangle(q(*box), outline=(255, 60, 60))
    h = lay['head']
    d.rectangle(q(h['x0'], h['top'], h['x1'], h['bottom']), outline=(0, 220, 255), width=2)
    for k, g in enumerate(lay['tiles']):
        d.rectangle(q(g['x'] - g['w'] / 2, g['y'] - g['h'] / 2, g['x'] + g['w'] / 2, g['y'] + g['h'] / 2), outline=(250, 230, 120), width=2)
        d.text(q(g['x'] - g['w'] / 2 + 12, g['y'] - 12), f'tile {k + 1}', fill=(250, 230, 120))
    for i, g in enumerate(lay['receipts']):
        W, H = B.RW * B.SIZE * g['scale'], B.RH * B.SIZE * g['scale']
        d.rectangle(q(g['x'] - W / 2, g['y'] - H / 2, g['x'] + W / 2, g['y'] + H / 2), outline=(255, 255, 255), width=2)
        d.text(q(g['x'] - W / 2 + 12, g['y'] - 12), f'receipt {i + 1}', fill=(255, 255, 255))
    t = lay['total']
    if t:
        d.rectangle(q(t['x'] - t['w'] / 2, t['y'] - t['h'] / 2, t['x'] + t['w'] / 2, t['y'] + t['h'] / 2), outline=(229, 72, 77), width=2)
        d.text(q(t['x'] - t['w'] / 2 + 12, t['y'] - 12), 'total', fill=(229, 72, 77))
    im.save('work/layout.jpg', quality=88)


if __name__ == '__main__':
    main()
