#!/usr/bin/env python3
"""The clean person cutout (RobustVideoMatting, resnet50, onnxruntime on the CPU):
<project>/assets/aroll.mp4 -> assets/subject.webm (VP9 + alpha, 1080x1920, frame-for-frame with aroll).

Usage:  PY rvm_cut.py <project_dir> [--src assets/x.mp4] [--out assets/y.webm] [--hard]

Use THIS cutout, not the quick one (cutout.py), whenever something sits behind the speaker or the speaker pops out
of a card: Bold captions, Chalk Talk, Show and Tell, and the effects that say "clean cutout" in effects/INDEX.md.
The quick cutout is fine for measuring (layout.py) but it can take a face in a painting or poster for the speaker
and it is rough around hands. This one is slow: about 1.2 seconds per FRAME on an Apple Silicon Mac, so roughly
36 seconds of work per second of footage (a 20 second reel is about 12 minutes; slower on older machines). Say so,
run it in the background and keep working.

First use needs the model and scipy, one time:   <any python> scripts/setup.py --matting   (about 105 MB download)

--hard   push soft, half-transparent edges solid (for a speaker placed on a new backdrop, as Chalk Talk does)
The recurrent state is warmed on the first frame and reset at every cut in <project>/segments.json (in an effect
slot: at the "cut_frames" of its clip.json). fx_new.py runs this on a slot's own frames when the reel has no cutout.
"""
import json
import os
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

skillenv.utf8_stdio()
if len(sys.argv) < 2:
    sys.exit(__doc__)
MODEL = os.path.join(skillenv.models_dir(), 'rvm_resnet50_fp32.onnx')
try:
    import numpy as np
    import onnxruntime as ort
    from scipy import ndimage
except ImportError as e:
    sys.exit(f'The clean cutout is not set up yet ({e.name} is missing). Run: setup.py --matting')
if not os.path.isfile(MODEL):
    sys.exit(f'The matting model is not downloaded yet ({MODEL}). Run: setup.py --matting')

FF = skillenv.tool('ffmpeg')
W, H = 1080, 1920
os.chdir(skillenv.path_arg(sys.argv[1]))
src = sys.argv[sys.argv.index('--src') + 1] if '--src' in sys.argv else 'assets/aroll.mp4'
out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else 'assets/subject.webm'
hard = '--hard' in sys.argv
cuts = set()
if os.path.exists('segments.json') and '--src' not in sys.argv:
    with open('segments.json', encoding='utf-8') as fh:
        cuts = {s['frame'] for s in json.load(fh)}
elif os.path.exists('clip.json') and '--src' not in sys.argv:      # an effect slot: its own cuts, if it spans two shots
    with open('clip.json', encoding='utf-8') as fh:
        cuts = set(json.load(fh).get('cut_frames') or [])
WARM = 12

so = ort.SessionOptions()
so.intra_op_num_threads = int(os.environ.get('RVM_THREADS', str(max(2, (os.cpu_count() or 4) - 2))))
sess = ort.InferenceSession(MODEL, so, providers=['CPUExecutionProvider'])
dec = subprocess.Popen([FF, '-loglevel', 'error', '-i', src, '-vf', f'scale={W}:{H}', '-fps_mode', 'passthrough', '-f', 'rawvideo',
                        '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
enc = subprocess.Popen([FF, '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                        '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '20', '-g', '30',
                        '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4', '-metadata:s:v:0', 'alpha_mode=1', out],
                       stdin=subprocess.PIPE)
ds = np.array([.375], np.float32)
size = W * H * 3
rec = None
n = 0
t0 = t_print = time.time()


def run(rgb, rec):
    x = rgb.astype(np.float32).transpose(2, 0, 1)[None] / 255.
    fgr, pha, *rec = sess.run(None, {'src': x, 'r1i': rec[0], 'r2i': rec[1], 'r3i': rec[2], 'r4i': rec[3],
                                     'downsample_ratio': ds})
    return fgr, pha, rec


while True:
    buf = dec.stdout.read(size)
    if len(buf) < size:
        break
    rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    if rec is None or n in cuts:                  # warm the recurrent state on the first frame of each shot
        rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
        for _ in range(WARM):
            _, _, rec = run(rgb, rec)
    fgr, pha, rec = run(rgb, rec)
    a = np.clip(pha[0, 0], 0, 1)
    small = a[::2, ::2] > .1                      # drop small floating islands
    lab, cnt = ndimage.label(small)
    if cnt > 1:
        areas = np.bincount(lab.ravel())[1:]
        drop = [i + 1 for i, ar in enumerate(areas) if ar < areas.max() * .015]
        if drop:
            m = ndimage.binary_dilation(np.isin(lab, drop), iterations=2)
            a = a.copy()
            a[np.repeat(np.repeat(m, 2, axis=0), 2, axis=1)[:H, :W]] = 0
    if hard:                                      # smoothstep: soft edges go solid, faint haze goes away
        s = np.clip((a - .25) / .5, 0, 1)
        a = s * s * (3 - 2 * s)
    f = np.clip(fgr[0].transpose(1, 2, 0), 0, 1)  # decontaminated foreground colour for edge pixels
    edge = (a > .02) & (a < .98)
    col = rgb.copy()
    col[edge] = (f[edge] * 255).astype(np.uint8)
    enc.stdin.write(np.dstack([col, (a * 255).astype(np.uint8)]).tobytes())
    n += 1
    if time.time() - t_print >= 30:
        t_print = time.time()
        print(f'{n} frames done, {(time.time() - t0) / n:.2f}s per frame', flush=True)
enc.stdin.close()
enc.wait()
dec.wait()
print(f'done {out}: {n} frames, {(time.time() - t0) / max(n, 1):.2f}s/frame', flush=True)
aroll = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                        'stream=nb_read_frames', '-of', 'csv=p=0', src], **skillenv.TEXT).stdout.strip().split(',')[0]
if aroll and aroll != str(n):
    sys.exit(f'FRAME MISMATCH: {src} has {aroll} frames, the cutout has {n}. Re-run assemble.py, then this script.')
