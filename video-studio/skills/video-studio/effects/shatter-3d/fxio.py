"""Frame IO for shatter-3d: colour-accurate ffmpeg pipes (BGR frames, numpy). Used by build.py, bake.py, post.py.

Without the accurate_rnd / full_chroma flags a yuv -> bgr -> yuv round trip darkens the picture by about 2 levels,
which shows as a pop where the plain footage hands over to the effect.
"""
import shutil
import subprocess

import numpy as np

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'
SWS = 'accurate_rnd+full_chroma_int+full_chroma_inp+bicubic'


def probe_size(path):
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of',
                          'csv=p=0', path], capture_output=True, text=True).stdout.strip()
    w, h = (int(v) for v in out.split(',')[:2])
    return w, h


def count_frames(path):
    out = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout
    return int(out.strip() or 0)


def frames(path, idxs, w, h):
    """{frame number: BGR array} for the frames asked for (one decode pass from just before the first one)."""
    idxs = sorted(set(int(i) for i in idxs))
    if not idxs:
        return {}
    first = idxs[0]
    sel = '+'.join(f'eq(n\\,{i - first})' for i in idxs)
    cmd = [FF, '-v', 'error']
    if first:                                  # seek half a frame early (exact on the slots' 30 fps CFR files)
        cmd += ['-ss', f'{(first - 0.5) / 30:.5f}']
    cmd += ['-i', path, '-an', '-vf',
            f"select='{sel}',scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags={SWS},format=bgr24",
            '-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = w * h * 3
    got = len(raw) // n
    assert got == len(idxs), f'{path}: asked for {len(idxs)} frames from {first}, got {got}'
    return {i: np.frombuffer(raw[k * n:(k + 1) * n], np.uint8).reshape(h, w, 3) for k, i in enumerate(idxs)}


def stream(path, w, h):
    """every frame of a video in order (BGR)."""
    p = subprocess.Popen([FF, '-v', 'error', '-i', path, '-an', '-vf',
                          f'scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags={SWS},format=bgr24',
                          '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


def alpha(path, scale):
    """the cutout's alpha plane, every frame, at scale=(w, h) (measurement)."""
    w, h = scale
    p = subprocess.Popen([FF, '-v', 'error', '-c:v', 'libvpx-vp9', '-i', path, '-vf',
                          f'alphaextract,scale={w}:{h}:flags=area', '-fps_mode', 'passthrough', '-f', 'rawvideo',
                          '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
    out = []
    try:
        while True:
            buf = p.stdout.read(w * h)
            if len(buf) < w * h:
                break
            out.append(np.frombuffer(buf, np.uint8).reshape(h, w))
    finally:
        p.stdout.close()
        p.wait()
    return np.stack(out) if out else np.zeros((0, h, w), np.uint8)


def writer(path, w, h, fps=30, crf=12):
    cmd = [FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps),
           '-i', '-', '-an', '-vf', f'scale=in_range=pc:out_color_matrix=bt709:out_range=tv:flags={SWS},format=yuv420p',
           '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-g', '15', '-bf', '0', '-colorspace', 'bt709',
           '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', '-movflags', '+faststart', path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
