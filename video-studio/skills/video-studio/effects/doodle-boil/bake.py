#!/usr/bin/env python3
"""doodle-boil, step 2 of 3: bake the chalk. work/plan.json + assets/aroll.mp4 + assets/subject.webm -> assets/fx.mp4
(1080x1920, 30 fps, exactly the slot's frames, no audio: index.html plays his audio and the chalk sound).

Usage (from the slot folder, with the Python that has opencv; put the slot runner in front on a shared machine):
  PY bake.py                          full bake, all cores but one (WORKERS=4 to use fewer)
  PY bake.py --frames 20,45,90,140    those frames only -> work/test/f###.jpg + work/test/sheet.jpg (a quick look)
  PY bake.py --frames ... --guide     same, with the safe zone, his face box and the doodle boxes drawn in
Deterministic: every random draw is seeded, so a re-bake gives the same frames.
"""
import argparse
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chalk  # noqa: E402
from chalk import W, H, FPS  # noqa: E402

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
SWS = 'flags=accurate_rnd+full_chroma_int+full_chroma_inp'     # no luma drift through the RGB round trip
G = {}


def in_colour():
    """The a-roll's matrix and range as tagged (phone clips are often full range): read it right or the picture shifts."""
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=color_space,color_range',
                          '-of', 'default=nw=1', os.path.join(HERE, 'assets/aroll.mp4')], capture_output=True, text=True).stdout
    tags = dict(line.split('=', 1) for line in out.split() if '=' in line)
    mat = 'bt601' if tags.get('color_space') in ('smpte170m', 'bt470bg') else 'bt709'
    return mat, ('pc' if tags.get('color_range') in ('pc', 'jpeg') else 'tv')


def init():
    plan = json.load(open(os.path.join(HERE, 'work/plan.json')))
    G['plan'] = plan
    G['chalk'] = chalk.Chalk({k: tuple(v) for k, v in plan['palette'].items()})
    G['docs'] = []
    for d in plan['doodles']:
        G['docs'].append((d, chalk.schedule(dict(d)), np.array(d['centres'])))
    G['body'] = np.array(plan['body_centres'])
    G['mat'], G['range'] = in_colour()
    G['has_alpha'] = os.path.exists(os.path.join(HERE, 'assets/subject.webm'))


def readers(a, b):
    sel = f"select='between(n\\,{a}\\,{b})'"
    v = subprocess.Popen([FF, '-v', 'error', '-i', os.path.join(HERE, 'assets/aroll.mp4'), '-vf',
                          f'{sel},scale={SWS}:in_color_matrix={G["mat"]}:in_range={G["range"]}:out_range=pc,format=bgr24',
                          '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE, bufsize=W * H * 3)
    al = None
    if G['has_alpha']:
        al = subprocess.Popen([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', os.path.join(HERE, 'assets/subject.webm'),
                               '-vf', f'{sel},alphaextract,format=gray', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'],
                              stdout=subprocess.PIPE, bufsize=W * H)
    return v, al


def read_exact(p, n):
    buf = p.stdout.read(n)
    return buf if len(buf) == n else None


def render(f, bgr, alpha, guide=False):
    plan = G['plan']
    t = f / FPS
    img = bgr.astype(np.float32)
    s = chalk.keyed(plan['dim_keys'], t)
    if s > 0.002:
        a = np.clip((alpha.astype(np.float32) / 255 - 0.42) / 0.42, 0, 1)
        a = cv2.erode(a, np.ones((3, 3), np.uint8))
        a = cv2.GaussianBlur(a, (0, 0), 1.4)
        mult = np.array((0.52, 0.47, 0.44), np.float32)           # BGR: slightly cool, never black and white
        img *= 1 - (s * (1 - a))[..., None] * (1 - mult)
    outs = plan['outlines']
    rays = plan['rays']
    live_o = [o for o in outs if o['t_in'] <= t and (o['t_out'] is None or t < o['t_out'] + max(o['undraw'], 1e-3))]
    need_sil = plan['person'] and (live_o or (rays and t >= rays['t_in']))
    masks = chalk.Chalk.new_masks()
    sil = chalk.Sil(alpha) if need_sil else None
    lw = plan['line_width']
    k = lw / 10.5
    outer = 12 * k
    for oi, o in enumerate(outs):
        if o not in live_o or sil is None:
            continue
        vis = chalk.outline_vis(o, t)
        boil = f // chalk.BOIL_OUTLINE
        if o['style'] == 'single':
            C, on = sil.contour(11 * k)
            if C is not None:
                chalk.draw_outline(masks['cream'], C, on, [401, oi, boil], lw, 0.97, vis)
        else:
            flare = 1 + 0.35 * (1 - chalk.ease_out((t - o['t_in']) / 0.5))     # the line lands heavy, then settles
            C1, on1 = sil.contour(11 * k)
            C2, on2 = sil.contour(33 * k, smooth=16.0)
            outer = 33 * k
            if C2 is not None:
                lag = dict(o, t_in=o['t_in'] + 0.07)
                chalk.draw_outline(masks['yellow'], C2, on2, [402, oi, boil], lw * 1.1 * flare, 0.97, chalk.outline_vis(lag, t), 2.2)
            if C1 is not None:
                if o.get('keep_inner'):        # the single line was already up: it stays whole, only the rub-out runs
                    vis = chalk.outline_vis(dict(o, t_in=o['t_in'] - 1.0), t)
                chalk.draw_outline(masks['cream'], C1, on1, [401, oi, boil], lw * flare, 0.97, vis)
    if rays and sil is not None:
        chalk.draw_rays(masks, 900, rays, sil, G['body'][min(f, len(G['body']) - 1)], f, t, outer, plan['ray_angles'],
                        rays['scale'])
    for di, (d, strokes, cen) in enumerate(G['docs']):
        chalk.draw_doodle(masks, di, d, strokes, cen[min(f, len(cen) - 1)], f, t)
    img = G['chalk'].composite(img, masks, f // chalk.BOIL_OUTLINE)
    out = np.clip(img + 0.5, 0, 255).astype(np.uint8)
    if guide:
        S, g = chalk.SAFE, (0, 0, 255)
        cv2.rectangle(out, (S['side'], S['top']), (W - S['side'], S['bottom']), g, 2)
        cv2.line(out, (W - S['right'], S['right_from']), (W - S['right'], S['bottom']), g, 2)
        for d, _, cen in G['docs']:
            if d['t_in'] <= t <= (d['t_out'] or 99) + 0.16:
                c, h = cen[min(f, len(cen) - 1)], 0.58 * d['size'] + 4
                cv2.rectangle(out, (int(c[0] - h), int(c[1] - h)), (int(c[0] + h), int(c[1] + h)), (0, 255, 255), 2)
        cv2.putText(out, f'f{f}', (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.6, g, 4)
    return out


def chunk(ab):
    a, b = ab
    v, al = readers(a, b)
    res = []
    for f in range(a, b + 1):
        fb = read_exact(v, W * H * 3)
        if fb is None:
            break
        ab_ = read_exact(al, W * H) if al else None
        alpha = np.frombuffer(ab_, np.uint8).reshape(H, W) if ab_ else np.zeros((H, W), np.uint8)
        res.append(render(f, np.frombuffer(fb, np.uint8).reshape(H, W, 3), alpha).tobytes())
    v.kill()
    if al:
        al.kill()
    return a, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default='')
    ap.add_argument('--guide', action='store_true')
    ap.add_argument('--out', default='assets/fx.mp4')
    args = ap.parse_args()
    if not os.path.exists(os.path.join(HERE, 'work/plan.json')):
        sys.exit('work/plan.json is missing: run build.py first')
    init()
    n = G['plan']['frames']
    if args.frames:
        want = sorted({min(n - 1, int(x)) for x in args.frames.split(',') if x.strip()})
        os.makedirs(os.path.join(HERE, 'work/test'), exist_ok=True)
        tiles = []
        for f in want:
            v, al = readers(f, f)
            fb = read_exact(v, W * H * 3)
            ab_ = read_exact(al, W * H) if al else None
            v.kill()
            if al:
                al.kill()
            alpha = np.frombuffer(ab_, np.uint8).reshape(H, W) if ab_ else np.zeros((H, W), np.uint8)
            out = render(f, np.frombuffer(fb, np.uint8).reshape(H, W, 3), alpha, args.guide)
            cv2.imwrite(os.path.join(HERE, f'work/test/f{f:03d}.jpg'), out, [cv2.IMWRITE_JPEG_QUALITY, 90])
            tw = max(180, 1080 // max(len(want), 1))
            tiles.append(cv2.resize(out, (tw, tw * 16 // 9), interpolation=cv2.INTER_AREA))
        cv2.imwrite(os.path.join(HERE, 'work/test/sheet.jpg'), np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print('wrote work/test/f###.jpg and work/test/sheet.jpg for frames', want)
        return
    workers = int(os.environ.get('WORKERS', '0')) or max(1, (os.cpu_count() or 2) - 1)
    size = max(6, -(-n // (workers * 2)))
    jobs = [(a, min(n - 1, a + size - 1)) for a in range(0, n, size)]
    out = os.path.join(HERE, args.out)
    tmp = out + '.part.mp4'
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS),
                            '-i', '-', '-vf', f'scale={SWS}:in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p,'
                            'setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709', '-c:v', 'libx264',
                            '-preset', 'medium', '-crf', '12', '-g', '15', '-bf', '0', '-color_primaries', 'bt709',
                            '-color_trc', 'bt709', '-colorspace', 'bt709', '-color_range', 'tv', '-an', tmp],
                           stdin=subprocess.PIPE)
    t0 = time.time()
    done = 0
    ctx = mp.get_context('spawn')
    with ctx.Pool(workers, initializer=init) as pool:
        for a, frames in pool.imap(chunk, jobs):
            for fbytes in frames:
                enc.stdin.write(fbytes)
            done += len(frames)
            print(f'  baked {done}/{n} frames', flush=True)
    enc.stdin.close()
    enc.wait()
    if done != n:
        sys.exit(f'only {done} of {n} frames baked: check assets/aroll.mp4 and assets/subject.webm')
    os.replace(tmp, out)
    dt = time.time() - t0
    print(f'wrote {args.out}: {n} frames in {dt:.0f}s with {workers} workers ({dt / (n / FPS):.1f}s per second of slot)')


if __name__ == '__main__':
    main()
