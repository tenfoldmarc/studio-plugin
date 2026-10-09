#!/usr/bin/env python3
"""green-screen / prep: everything build.py needs that has to be measured or cut.

  python prep.py words    every spoken word with the frame its sound starts on (for IN_FRAME, OUT_FRAME, at=, CAPS)
  python prep.py          1. measures the cutout (assets/subject.webm): highest point of the head, chin, head width,
                             the row the body is cut off at (desk edge, table, frame bottom)
                          2. works out the pose for every background item (scale, position, caption line)
                          3. cuts the background files into the slot: videos 1080x1920 cover, 30 fps constant,
                             a keyframe every 30 frames, muted, exactly the frames needed; pictures resized
                          4. writes work/layout.json and the check picture work/layout.jpg  <- LOOK at it

Needs numpy, scipy, Pillow and ffmpeg. Run it again after any change to the CLIP block (it takes seconds; videos that
did not change are not cut again).
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import build as B

HERE = os.path.dirname(os.path.abspath(__file__))
FF = shutil.which('ffmpeg') or 'ffmpeg'
W, H, FPS = B.W, B.H, B.FPS
CELL = 4
GW, GH = W // CELL, H // CELL


def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        sys.exit('ffmpeg failed:\n' + r.stderr.decode(errors='replace')[-600:])
    return r.stdout


def word_frames(nfr):
    """words.json with the frame each word really starts on: the first frame within 5 of Whisper's guess where the
    voice rises out of a dip (Whisper alone is often 0.1 to 0.3 s early)"""
    if not os.path.exists('words.json'):
        return []
    words = json.load(open('words.json'))
    raw = run([FF, '-v', 'error', '-i', 'assets/aroll.mp4', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 48000 // FPS
    db = np.array([20 * np.log10(np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) + 1e-9) for i in range(len(a) // hop)])
    if not len(db):
        return [dict(text=w['text'], frame=round(w['start'] * FPS), whisper=round(w['start'] * FPS)) for w in words]
    floor, loud = np.percentile(db, 10), np.percentile(db, 90)
    thr = floor + .45 * (loud - floor)
    out = []
    for w in words:
        f = round(w['start'] * FPS)
        best = None
        for n in range(max(1, f - 5), min(len(db), f + 6)):
            if db[n] >= thr and (db[n - 1] < thr or db[n] - db[n - 1] > 6):
                if best is None or abs(n - f) < abs(best - f):
                    best = n
        out.append(dict(text=w['text'], frame=min(nfr - 1, best if best is not None else f), whisper=f))
    for i in range(1, len(out)):           # two words never share a frame, and never run backwards
        out[i]['frame'] = min(nfr - 1, max(out[i]['frame'], out[i - 1]['frame'] + 1))
    return out


def alpha(nfr):
    # -c:v libvpx-vp9 BEFORE -i, or ffmpeg's own decoder drops the alpha plane
    raw = run([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', 'assets/subject.webm', '-vf',
               f'alphaextract,scale={GW}:{GH}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    a = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW)
    if len(a) != nfr:
        sys.exit(f'the cutout has {len(a)} frames, the clip has {nfr}: it would drift. Re-make the slot.')
    return a


def measure(a, f0, f1):
    """the speaker on the source frame (px), over the frames the green screen is up"""
    seg = a[f0:f1] > 127
    keep = np.zeros_like(seg)
    for i, m in enumerate(seg):            # the biggest blob only: lamps and picture frames the matte caught are dropped
        lab, n = ndimage.label(m)
        if n:
            keep[i] = lab == 1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    rows = keep.any(axis=2)
    has = rows.any(axis=1)
    if has.mean() < .9:
        sys.exit('The cutout is empty on many frames of this slot: there is nobody to put in front of the background. '
                 'Check assets/subject.webm (re-make the slot without --no-cutout).')
    tops = np.array([int(np.argmax(r)) for r in rows[has]])
    top_min, top_hi = int(np.percentile(tops, 1)), int(np.percentile(tops, 98))
    M = keep.mean(axis=0) >= .5            # where the speaker is at least half of the time
    wd = ndimage.uniform_filter1d(M.sum(axis=1).astype(float), 5)
    top = int(np.argmax(M.any(axis=1)))
    note = ''
    if B.FACE:
        fx0, fy0, fx1, fy1 = B.FACE
        head_w, head_cx, chin = (fx1 - fx0) / CELL, (fx0 + fx1) / 2 / CELL, fy1 / CELL
    else:
        # the head ends where the outline narrows to the neck; the shoulders start where it widens past the head again
        peak, y_peak, neck = 0.0, top, None
        for y in range(top, GH):
            if wd[y] > peak:
                if neck is not None and wd[y] > peak * 1.12:
                    break
                if neck is None:
                    peak, y_peak = wd[y], y
            elif wd[y] < .88 * peak and y - top > 5 and (neck is None or wd[y] < wd[neck]):
                neck = y
        shoulders = float(wd[top:min(GH, top + int(4 * peak))].max()) if peak else 0
        if neck is None or shoulders < 1.3 * peak:
            # no neck in the outline (hood, long hair, a hand at the face): guess from the shoulders
            peak = .38 * float(wd[top:top + max(8, (GH - top) // 2)].max())
            neck = top + int(1.25 * peak)
            note = 'no neck found in the outline: head size is a guess from the shoulders. Check the red box, set FACE if it is off'
        head_w, chin = peak, neck
        band = M[top:neck + 1]
        xs = np.where(band.any(axis=0))[0]
        head_cx = (xs[0] + xs[-1] + 1) / 2
    chin_max = chin + (top_hi - top)
    # where the body is cut off: per column the lowest row the speaker reaches; the highest of those under the shoulders
    below = M[int(chin):]
    cols = np.where(below.any(axis=0))[0]
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    core = cols[(cols >= x0 + .1 * (x1 - x0)) & (cols <= x1 - 1 - .1 * (x1 - x0))]
    bottoms = np.array([int(chin) + int(np.where(below[:, x])[0][-1]) for x in core])
    cut = float(np.percentile(bottoms, 5))
    runs_off = cut >= GH - 3
    base = H if runs_off else cut * CELL - 8
    if B.BODY_BOTTOM is not None:
        base = float(B.BODY_BOTTOM)
    rows_up = slice(top_min, max(top_min + 1, int(min(base, H) / CELL)))
    ever = keep.any(axis=0)[rows_up]
    ex = np.where(ever.any(axis=0))[0]
    return dict(top=top_min * CELL, chin=round(chin_max * CELL), head_w=round(head_w * CELL), head_cx=round(head_cx * CELL),
                base=round(base), runs_off=bool(runs_off), x0=int(ex[0]) * CELL, x1=(int(ex[-1]) + 1) * CELL,
                edge_l=bool(M[rows_up, 0].any()), edge_r=bool(M[rows_up, -1].any()), note=note)


def media_size(path, kind):
    if kind == 'image':
        with Image.open(path) as im:
            return im.size
    out = B.probe(path, 'stream=width,height:stream_side_data=rotation').replace('\n', ',').split(',')
    nums = [x for x in out if x.strip().lstrip('-').replace('.', '').isdigit()]
    w, h = int(nums[0]), int(nums[1])
    return (h, w) if len(nums) > 2 and abs(int(float(nums[2]))) in (90, 270) else (w, h)


def cover(sw, sh, tw, th, focus):
    """scale + crop numbers that fill tw x th from sw x sh, keeping the part of the picture named by focus"""
    f = max(tw / sw, th / sh)
    w, h = max(tw, round(sw * f / 2) * 2), max(th, round(sh * f / 2) * 2)
    return w, h, round((w - tw) * focus[0]), round((h - th) * focus[1])


def cut_media(k, it, cache):
    """the item's file, cut into assets/bgm/ at the size and length the page needs"""
    src = os.path.join(B.bg_folder(), it['file'])
    n = it['b'] - it['a']
    tw, th = (W, H) if it['mode'] == 'fill' else (it['card'][2] // 2 * 2, it['card'][3] // 2 * 2)
    if it['kind'] == 'image' or (it['mode'] == 'fill' and it.get('reframe')):
        over = 1.12 if it['kind'] == 'image' else min(1.5, float(it['reframe'][0]))    # room for the push / reframe
        tw, th = round(tw * over / 2) * 2, round(th * over / 2) * 2
    st = os.stat(src)
    key = json.dumps([it['file'], st.st_size, int(st.st_mtime), n, it['start'], tw, th, list(it['focus'])])
    out = f'assets/bgm/bg{k}' + ('.mp4' if it['kind'] == 'video' else '.jpg')
    if cache.get(out) == key and os.path.exists(out):
        return out
    sw, sh = media_size(src, it['kind'])
    w, h, cx, cy = cover(sw, sh, tw, th, it['focus'])
    if it['kind'] == 'image':
        im = Image.open(src)
        if im.mode in ('RGBA', 'LA', 'P'):
            im = im.convert('RGBA')
            flat = Image.new('RGB', im.size, (255, 255, 255))
            flat.paste(im, mask=im.split()[3])
            im = flat
        im = im.convert('RGB').resize((w, h), Image.LANCZOS).crop((cx, cy, cx + tw, cy + th))
        im.save(out, quality=93)
    else:
        vf = (f'fps={FPS},scale={w}:{h}:flags=lanczos,crop={tw}:{th}:{cx}:{cy},setsar=1,'
              f'tpad=stop_mode=clone:stop_duration={n / FPS + 1:.2f}')
        run([FF, '-v', 'error', '-y', '-ss', f'{max(0.0, float(it["start"])):.3f}', '-i', src, '-vf', vf, '-frames:v', str(n),
             '-fps_mode', 'cfr', '-r', str(FPS), '-an', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium', '-g', '30',
             '-keyint_min', '30', '-sc_threshold', '0', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out])
        got = int(B.probe(out, 'stream=nb_frames').split('\n')[0] or 0)
        if got != n:
            sys.exit(f'{out} has {got} frames, needed {n}')
        length = float(B.probe(src, 'format=duration') or 0)
        if length and length - float(it['start']) < n / FPS - .05:
            print(f'  !! {it["file"]} is {length:.1f}s long: it runs out {n / FPS - (length - float(it["start"])):.1f}s '
                  f'early and holds its last frame. Give a longer file or an earlier start')
    cache[out] = key
    return out


def grab(path, f, size, rgba=False):
    pre = ['-c:v', 'libvpx-vp9'] if rgba else []
    raw = run([FF, '-v', 'error'] + pre + ['-i', path, '-vf', f"select='eq(n,{f})',scale={size[0]}:{size[1]}", '-frames:v', '1',
                                           '-f', 'rawvideo', '-pix_fmt', 'rgba' if rgba else 'rgb24', '-'])
    return Image.frombytes('RGBA' if rgba else 'RGB', size, raw)


def cap_luma(it):
    """how bright the background is under the caption line (0..255), so white words can get a dark plate"""
    p, rf = it['pose'], it.get('reframe') or (1, 0, 0)
    n, q = it['b'] - it['a'], 4
    ims = ([grab(it['src'], f, (W // q, H // q)) for f in (0, n // 2, n - 1)] if it['kind'] == 'video'
           else [Image.open(it['src']).resize((W // q, H // q))])
    cx = (p['cap_box'][0] + p['cap_box'][1]) / 2
    x0, x1 = [int(min(W, max(0, (v - rf[1]) / rf[0])) / q) for v in (cx - 300, cx + 300)]
    y0, y1 = [int(min(H, max(0, (v - rf[2]) / rf[0])) / q) for v in (p['cap_top'], p['cap_bottom'])]
    return float(np.mean([np.asarray(im.convert('L'))[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)].mean() for im in ims]))


def check_picture(L, m):
    """work/layout.jpg at half size: the source frame with what was measured, then every item as it will look"""
    S = 2
    tiles = []
    mid = (L['f_in'] + L['f_out']) // 2
    src = grab('assets/aroll.mp4', mid, (W // S, H // S))
    d = ImageDraw.Draw(src)
    d.rectangle([(m['head_cx'] - m['head_w'] / 2) / S, m['top'] / S, (m['head_cx'] + m['head_w'] / 2) / S, m['chin'] / S],
                outline=(255, 40, 40), width=3)
    d.line([(0, min(m['base'], H - 4) / S), (W / S, min(m['base'], H - 4) / S)], fill=(0, 230, 255), width=3)
    d.text((10, 10), 'SOURCE  red = head, cyan = body cut-off row', fill=(255, 255, 0))
    tiles.append(src)
    for k, it in enumerate(L['items']):
        f = (it['a'] + it['b']) // 2
        p = it['pose']
        if it['mode'] == 'card':
            can = Image.new('RGB', (W, H), (22, 24, 29))
            l, t, w, h = it['card']
            pic = (grab(it['src'], f - it['a'], (w, h)) if it['kind'] == 'video' else Image.open(it['src']).resize((w, h)))
            mask = Image.new('L', (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], B.CARD_R, fill=255)
            can.paste(pic, (l, t), mask)
        else:
            can = (grab(it['src'], f - it['a'], (W, H)) if it['kind'] == 'video' else Image.open(it['src']).resize((W, H)))
            rf = it.get('reframe')
            if rf:
                big = can.resize((round(W * rf[0]), round(H * rf[0])))
                can = Image.new('RGB', (W, H))
                can.paste(big, (round(rf[1]), round(rf[2])))
        cut = grab('assets/subject.webm', f, (W, H), rgba=True)
        cut = cut.resize((round(W * p['s']), round(H * p['s'])), Image.LANCZOS)
        can.paste(cut, (round(p['x']), round(p['y'])), cut)
        can = can.resize((W // S, H // S), Image.LANCZOS)
        d = ImageDraw.Draw(can, 'RGBA')
        for box in ([0, 0, W, 220], [0, 1470, W, H], [0, 220, 35, 1470], [W - 35, 220, W, 1155], [W - 100, 1155, W, 1470]):
            d.rectangle([v / S for v in box], fill=(255, 0, 0, 60))
        d.rectangle([v / S for v in p['face']], outline=(255, 40, 40, 255), width=3)
        d.rectangle([p['cap_box'][0] / S, p['cap_top'] / S, p['cap_box'][1] / S, p['cap_bottom'] / S], outline=(255, 230, 0, 255), width=3)
        d.text((10, 10), f'ITEM {k}  f{it["a"]}..{it["b"]}  {it["mode"]}  yellow = caption line', fill=(255, 255, 0, 255))
        tiles.append(can)
    sheet = Image.new('RGB', (W // S * len(tiles), H // S))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * W // S, 0))
    sheet.save('work/layout.jpg', quality=85)


def main():
    os.chdir(HERE)
    clip = json.load(open('clip.json'))
    nfr = int(clip['frames'])
    words = word_frames(nfr)
    if sys.argv[1:2] == ['words']:
        print('word            frame  (whisper)')
        for w in words:
            print(f"{w['text'][:14]:14s}  f{w['frame']:4d}  (f{w['whisper']})")
        print(f'\n{nfr} frames in this slot. Whisper mishears names: trust the order of the words, not the spelling.')
        return
    if not os.path.exists('assets/subject.webm'):
        sys.exit('assets/subject.webm is missing: Green Screen needs the cutout. Re-make the slot without --no-cutout.')
    f_in, f_out, items = B.resolve(nfr, words)
    os.makedirs('assets/bgm', exist_ok=True)
    os.makedirs('work', exist_ok=True)
    m = measure(alpha(nfr), f_in, f_out)
    print(f'speaker: head top y {m["top"]}, chin y {m["chin"]}, head {m["head_w"]} px wide at x {m["head_cx"]}, body '
          + ('runs off the bottom of the frame' if m['runs_off'] and B.BODY_BOTTOM is None else f'is cut off at y {m["base"]}')
          + (' (BODY_BOTTOM)' if B.BODY_BOTTOM is not None else '') + (f'\n  !! {m["note"]}' if m['note'] else ''))
    cache = json.load(open('work/media.json')) if os.path.exists('work/media.json') else {}
    for k, it in enumerate(items):
        it['pose'] = B.pose(m, it['side'], it['size'])
        sw, sh = media_size(os.path.join(B.bg_folder(), it['file']), it['kind'])
        if it['mode'] == 'auto':
            it['mode'] = 'fill' if sw / sh <= .8 else 'card'
        if it['mode'] not in ('fill', 'card'):
            sys.exit(f'BG item {k}: mode must be "auto", "fill" or "card"')
        it['card'] = B.card_rect(sw / sh, it['pose']['cap_top'], it['credit']) if it['mode'] == 'card' else None
        rf = it.get('reframe')
        if rf and it['mode'] == 'fill' and (rf[1] > 0 or rf[2] > 0 or rf[1] + W * rf[0] < W or rf[2] + H * rf[0] < H):
            print(f'  !! item {k}: reframe {tuple(rf)} leaves part of the frame empty (needs x <= 0, y <= 0, '
                  f'x + {W} * scale >= {W}, y + {H} * scale >= {H})')
        it['src'] = cut_media(k, it, cache)
        it['plate'] = bool(B.CAP_PLATE) if B.CAP_PLATE != 'auto' else (it['mode'] == 'fill' and cap_luma(it) > 140)
        p = it['pose']
        print(f'  item {k}  f{it["a"]}..f{it["b"]}  {it["file"]} ({sw}x{sh}, {it["kind"]}) -> {it["mode"]}  speaker scale '
              f'{p["s"]:.2f}, head line y {p["head_line"]}, caption line y {p["cap_top"]}'
              + (f', card {it["card"][2]}x{it["card"][3]} at {it["card"][0]},{it["card"][1]}' if it['card'] else '')
              + (', bright under the caption line: dark plate behind the words' if it['plate'] else '')
              + ''.join(f'\n     !! {n}' for n in p['notes']))
    json.dump(cache, open('work/media.json', 'w'), indent=1)
    L = dict(frames=nfr, sig=B.signature(), f_in=f_in, f_out=f_out, trans=B.TRANS, measure=m, items=items,
             words=[dict(text=w['text'], frame=w['frame']) for w in words],
             note='boxes are canvas px. With CAPTIONS=0 the reel captions this slot: keep its words inside cap_box, '
                  'between cap_top and cap_bottom of the item on screen, never lower (the speaker\'s face is at "face").')
    json.dump(L, open('work/layout.json', 'w'), indent=1)
    check_picture(L, m)
    print('wrote work/layout.json and work/layout.jpg: LOOK at the picture (red box on the head, no cut body edge above '
          'the bottom, face above the red bar, subject of the background not behind the speaker)')


if __name__ == '__main__':
    main()
