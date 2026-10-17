"""Frame IO helpers for rack-focus: ffmpeg pipes in and out (colour-accurate). Used by build.py and bake.py."""
import shutil
import subprocess

import numpy as np

FF = shutil.which('ffmpeg') or 'ffmpeg'
FP = shutil.which('ffprobe') or 'ffprobe'


def probe_size(path):
    out = subprocess.run([FP, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of',
                          'csv=p=0', path], capture_output=True, text=True).stdout.strip()
    w, h = (int(v) for v in out.split(',')[:2])
    return w, h


def count_frames(path):
    out = subprocess.run([FP, '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                          'stream=nb_read_frames', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout
    return int(out.strip() or 0)


def reader(path, w, h, alpha=False, first=None, last=None, scale=None):
    """Yield frames of a video as numpy arrays (rgb24, or the VP9 alpha plane as gray when alpha=True).
    first/last (inclusive frame numbers) decode only that run. scale=(w, h) resizes on decode (measurement)."""
    cmd = [FF, '-v', 'error']
    if alpha:
        cmd += ['-c:v', 'libvpx-vp9']          # must come BEFORE -i or the alpha plane is dropped
    if first:                                  # seek half a frame early (exact on the slots' 30 fps CFR files)
        cmd += ['-ss', f'{(first - 0.5) / 30:.5f}']
    cmd += ['-i', path]
    filt = []
    if alpha:
        filt.append('alphaextract')
    if first is not None:
        filt.append(f"select='between(n,0,{last - first})'")
    if scale:
        filt.append(f'scale={scale[0]}:{scale[1]}:flags=area')
        w, h = scale
    if filt:
        cmd += ['-vf', ','.join(filt)]
    pix = 'gray' if alpha else 'rgb24'
    # accurate_rnd: swscale's default fast YUV->RGB path comes out about 2 levels dark
    cmd += ['-fps_mode', 'passthrough', '-sws_flags', 'accurate_rnd+full_chroma_int+bicubic', '-f', 'rawvideo',
            '-pix_fmt', pix, '-']
    ch = 1 if alpha else 3
    n = w * h * ch
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=n)
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            a = np.frombuffer(buf, np.uint8)
            yield a.reshape(h, w) if ch == 1 else a.reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


VF_OUT = ('scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,'
          'setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709')


def writer(path, w, h, fps=30, crf=12):
    cmd = [FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', str(fps),
           '-i', '-', '-an', '-vf', VF_OUT,
           '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-g', '15', '-bf', '0', '-colorspace', 'bt709',
           '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', '-movflags', '+faststart', path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)
