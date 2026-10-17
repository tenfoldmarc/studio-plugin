#!/usr/bin/env python3
"""Take a picture off the speaker's head: a painting, poster or framed photo with a face (or a skull) hanging behind
the speaker can be read by the cutout as part of the person. It then rides above their head as a half-transparent
grey "ghost" and shows over anything placed behind them (Bold captions, Orbit, Couch Wall, Headline Wall, Spotlight,
a new backdrop). rvm_cut.py runs this on every cutout it makes; a clean cutout is left exactly as it is.

Usage:  PY head_clean.py <project_dir> [--src assets/aroll.mp4] [--cut assets/subject.webm] [--look F F ...] [--basic]
        PY head_clean.py <project_dir> --prepare [--src ...]      (only find the face and hands; rvm_cut.py starts this
                                                                    in the background while it mattes)
How: Apple Vision finds the face, the hands and the arms on every frame of the footage (a small helper, built once on
the first run with Apple's free command line tools, about a minute). Above eye level nothing of the speaker can
exist except the head (an ellipse from the face, grown over whatever solid hair or hat joins it) and raised hands and
arms. Half-transparent cutout there, on enough frames, is the ghost; when it is found, the cutout outside those parts
and above eye level is removed on every frame. The cutout as it was is kept in work/<name>_before_head_clean.webm.
Without Apple Vision (Windows, Linux, a Mac without the command line tools) a simpler check runs: half-transparent
cutout far from anything solid at the top of the person is removed. It catches the faint ghost but can leave a
solid part of the picture; the printed line says which one ran.

--look F F ...  write work/head_clean_<F>.jpg (footage | cutout before | cutout after, on green) and change nothing
--basic         use the simpler check even on a Mac with Apple Vision (for testing)
Exit 0 when nothing needed doing or the cutout was cleaned; 2 when something went wrong (the cutout is unchanged).
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

skillenv.utf8_stdio()
if len(sys.argv) < 2:
    sys.exit(__doc__)
import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

W, H = 1080, 1920
SWIFT = os.path.join(HERE, 'vision', 'track.swift')
# The head, in face-box units (Apple Vision's box runs about brow to chin). The ellipse is the least of a head: a cap
# or bare scalp fits inside it. Hair or a hat that sticks out further is kept when it is SOLID cutout joined to it,
# out to the larger ellipse (GROW times the size); the ghost is half-transparent, so it does not join.
EX, EY, RX, RY = .5, .10, .74, .56
GROW = 1.7
SOLID = .85
# Hair and hats sit on the head in nearly every frame; a picture on the wall stays put while the head moves, so on
# the face-relative grid (CELL face units) it lands on any one cell only now and then. Joined solid cutout is kept
# as hair only on cells where it shows on at least HAIR_SHARE of the frames with a face.
CELL, HAIR_SHARE = .02, .5
GU, GV0, GV1 = GROW * RX, GROW * RY, .2
GRID = (int(round((GV0 + GV1) / CELL)) + 1, int(round(2 * GU / CELL)) + 1)
EDGE = .07                     # soft edge kept around solid hair, in face widths
EYE = .25                      # the zone ends at eye level: y + EYE * h (long hair and the neck below stay untouched)
SIDE = 2.1                     # the zone's half-width, in face widths
HAND_R, ARM_R, WRIST_R = .22, .35, .6    # capsule radii in face widths: finger bones, upper/fore arm, wrist blob
# The ghost test: half-transparent pixels (between LO and HI) in the zone outside the speaker's parts.
LO, HI = .1, .9
FRAME_AREA = .08               # a ghost frame has more than this many face areas of it
SHARE, MIN_FRAMES = .10, 5     # the cutout is cleaned when at least this share of frames (and this many) have one
# The simpler check (no Apple Vision): half-transparent cutout more than FAR px from solid cutout, above the top of
# the solid person + TOP_BAND px, more than BASIC_AREA px on a frame.
FAR, TOP_BAND, BASIC_AREA = 24, 30, 6000      # a lower band reaches motion-blurred hands beside the face
BONES = [('WRI', 'TCMC'), ('TCMC', 'TMP'), ('TMP', 'TIP'), ('TIP', 'TTIP')] + \
        [(a, b) for f in 'IMRP' for a, b in (('WRI', f + 'MCP'), (f + 'MCP', f + 'PIP'), (f + 'PIP', f + 'DIP'), (f + 'DIP', f + 'TIP'))]
ARM_BONES = [('ls', 'le'), ('le', 'lw'), ('rs', 're'), ('re', 'rw')]


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def say(line):
    print(line, flush=True)


# ------------------------------------------------------------------ the Apple Vision helper
def swift_compiler():
    """True when Apple's command line tools (or Xcode) are installed. Checked without xcrun: on a Mac without them,
    xcrun pops up an install dialog in the buyer's face."""
    if platform.system() != 'Darwin':
        return False
    try:
        dev = subprocess.run(['xcode-select', '-p'], **skillenv.TEXT, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(dev) and any(os.path.isfile(os.path.join(dev, p)) for p in
                             ('usr/bin/swiftc', 'Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'))


def helper_tag():
    with open(SWIFT, 'rb') as fh:
        return hashlib.sha256(fh.read() + platform.machine().encode()).hexdigest()[:10]


def helper():
    """-> (path of the built helper or None, why not). Built once per version of track.swift, into the state folder
    (it survives skill updates; a changed track.swift builds a new one)."""
    if platform.system() != 'Darwin':
        return None, 'Apple Vision is only on a Mac'
    bdir = os.path.join(skillenv.state_dir(), 'bin')
    exe = os.path.join(bdir, f'vision-track-{helper_tag()}')
    if os.path.isfile(exe) and os.access(exe, os.X_OK):
        return exe, ''
    if not swift_compiler():
        return None, "Apple's command line tools are not installed"
    os.makedirs(bdir, exist_ok=True)
    say('head check: building the face finder, one time (about a minute) ...')
    tmp = exe + '.part'
    try:
        r = subprocess.run(['xcrun', 'swiftc', '-O', '-swift-version', '5', '-o', tmp, SWIFT], **skillenv.TEXT, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f'the face finder did not build ({e})'
    if r.returncode != 0 or not os.path.isfile(tmp):
        err = [ln for ln in (r.stderr or '').splitlines() if 'error' in ln.lower()][:3]
        return None, 'the face finder did not build (' + ('; '.join(err) or 'no output') + ')'
    os.replace(tmp, exe)
    return exe, ''


def track(src, cache):
    """-> (rows or None, why not). Cached next to the project's other work files; redone when the footage changes."""
    stamp = f'{os.path.getsize(src)}:{int(os.path.getmtime(src))}:{os.path.basename(src)}:{helper_tag()}'
    if os.path.isfile(cache):
        try:
            with open(cache, encoding='utf-8') as fh:
                d = json.load(fh)
            if d.get('stamp') == stamp:
                return d['rows'], ''
        except (OSError, ValueError, KeyError):
            pass
    exe, why = helper()
    if not exe:
        return None, why
    raw = cache + '.raw'
    try:
        r = subprocess.run([exe, src, raw], **skillenv.TEXT, timeout=3600)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f'the face finder did not run ({e})'
    if r.returncode != 0 or not os.path.isfile(raw):
        return None, 'the face finder did not run (' + (r.stderr or '').strip()[-300:] + ')'
    with open(raw, encoding='utf-8') as fh:
        rows = json.load(fh)
    os.remove(raw)
    with open(cache, 'w', encoding='utf-8') as fh:
        json.dump({'stamp': stamp, 'rows': rows}, fh)
    return rows, ''


def align(rows, src, n):
    """Apple's reader and ffmpeg can disagree by a frame at the start of a file (AVFoundation shows an extra first
    frame where ffmpeg's video starts a frame late). Line the rows up with ffmpeg's frames by time (30 fps, as every
    cutout is). -> n rows (frames the face finder did not see get no face), or None when they cannot line up."""
    if len(rows) == n and all('t' not in r for r in rows):
        return rows
    try:
        start = float(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                      'stream=start_time', '-of', 'csv=p=0', src], **skillenv.TEXT).stdout.strip().split(',')[0])
    except ValueError:
        start = 0.0
    out = [None] * n
    for r in rows:
        if 't' not in r:
            return rows if len(rows) == n else None
        i = int(round((r['t'] - start) * 30))
        if 0 <= i < n and out[i] is None:
            out[i] = dict(r, f=i)
    if sum(o is not None for o in out) < .9 * n:
        return None
    return [o if o is not None else {'f': i, 'face': [], 'hands': [], 'arms': []} for i, o in enumerate(out)]


# ------------------------------------------------------------------ what the speaker is, per frame
class Parts:
    def __init__(self, rows, n):
        self.n = n
        faces = [r['face'] if len(r.get('face') or []) == 4 else None for r in rows[:n]] + [None] * max(0, n - len(rows))
        idx = [i for i, b in enumerate(faces) if b]
        self.box = [None] * n
        if idx:
            arr = np.array([faces[i] for i in idx], np.float32)
            full = np.stack([np.interp(np.arange(n), idx, arr[:, k]) for k in range(4)], 1)
            full = np.stack([ndimage.median_filter(full[:, k], 5, mode='nearest') for k in range(4)], 1)
            known = np.zeros(n, bool)
            known[idx] = True
            near = ndimage.binary_dilation(known, iterations=8)     # bridge short gaps (a blink of the detector), not long ones
            for i in range(n):
                if near[i]:
                    self.box[i] = full[i]
        self.hands = {r['f']: r.get('hands') or [] for r in rows}
        self.arms = {r['f']: r.get('arms') or [] for r in rows}
        self.faces_seen = len(idx)

    def kill(self, f, a, hairmap=None):
        """-> (kill mask for frame f: the zone above eye level minus the speaker's parts, or None without a face;
        this frame's solid cutout joined to the head outside the ellipse, on the face-relative grid, or None).
        hairmap: the face-relative cells where that joined cutout shows on most frames (hair, a hat). Without it, all
        of it is kept (measuring); with it, only what lies on those cells (cleaning)."""
        b = self.box[f]
        if b is None:
            return None, None
        x, y, w, h = (float(v) for v in b)
        cx, cy = x + EX * w, y + EY * h
        y1 = int(max(0, min(H, y + EYE * h)))
        x0, x1 = int(max(0, cx - SIDE * w)), int(min(W, cx + SIDE * w))
        kill = np.zeros((H, W), bool)
        if y1 == 0 or x1 <= x0:
            return kill, None
        yy, xx = np.mgrid[0:y1, x0:x1].astype(np.float32)
        u, v = (xx - cx) / w, (yy - cy) / h
        e = (u / RX) ** 2 + (v / RY) ** 2
        head = e <= 1
        # solid hair / hat joined to the head, inside the larger ellipse
        ac = a[:y1, x0:x1]
        solid = (ac >= SOLID) & (e <= GROW * GROW)
        lab, _ = ndimage.label(solid | head)
        ids = np.unique(lab[head & (lab > 0)])
        joined = np.isin(lab, ids[ids > 0]) & solid & ~head
        gi = np.clip(np.rint((u + GU) / CELL).astype(int), 0, GRID[1] - 1)
        gj = np.clip(np.rint((v + GV0) / CELL).astype(int), 0, GRID[0] - 1)
        inside = (np.abs(u) <= GU) & (v >= -GV0) & (v <= GV1)
        cells = np.zeros(GRID, bool)
        cells[gj[joined & inside], gi[joined & inside]] = True
        hair = joined if hairmap is None else joined & inside & hairmap[gj, gi]
        if hair.any():
            hair = ndimage.binary_dilation(hair, iterations=max(1, int(EDGE * w)))
        keep = head | hair | self.limbs(f, w)[:y1, x0:x1]
        kill[:y1, x0:x1] = ~keep
        return kill, cells

    def limbs(self, f, w):
        m = np.zeros((H, W), bool)
        for f2 in (f - 1, f, f + 1):                       # a frame either side: fast hands
            for hand in self.hands.get(f2, []):
                pts = {k.replace('VNHLK', ''): v for k, v in hand.items()}
                for p, q in BONES:
                    if p in pts and q in pts:
                        capsule(m, pts[p], pts[q], HAND_R * w)
            for arm in self.arms.get(f2, []):
                for p, q in ARM_BONES:
                    if p in arm and q in arm:
                        capsule(m, arm[p], arm[q], ARM_R * w)
                for k in ('lw', 'rw'):
                    if k in arm:
                        capsule(m, arm[k], arm[k], WRIST_R * w)
        return m


def capsule(m, p, q, r):
    p, q = np.array(p, np.float32), np.array(q, np.float32)
    x0, x1 = int(max(min(p[0], q[0]) - r, 0)), int(min(max(p[0], q[0]) + r + 1, W))
    y0, y1 = int(max(min(p[1], q[1]) - r, 0)), int(min(max(p[1], q[1]) + r + 1, H))
    if x1 <= x0 or y1 <= y0:
        return
    sy, sx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = q - p
    t = np.clip(((sx - p[0]) * d[0] + (sy - p[1]) * d[1]) / max(float(d @ d), 1e-3), 0, 1)
    m[y0:y1, x0:x1] |= np.hypot(sx - p[0] - t * d[0], sy - p[1] - t * d[1]) < r


def basic_kill(a):
    """The simpler check: half-transparent cutout far from solid cutout, near the top of the person. -> mask or None."""
    solid = a >= HI
    if not solid.any():
        return None
    lab, cnt = ndimage.label(solid[::2, ::2])
    if cnt == 0:
        return None
    big = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    top = int(np.argmax(big.any(axis=1))) * 2
    far = ndimage.distance_transform_edt(~solid[::2, ::2]) * 2 > FAR
    far = np.repeat(np.repeat(far, 2, axis=0), 2, axis=1)[:H, :W]
    kill = far & (a > 0)
    kill[min(H, top + TOP_BAND):] = False
    return kill


# ------------------------------------------------------------------ reading and writing the cutout
def alpha_frames(path):
    p = subprocess.Popen([FF, '-loglevel', 'error', '-c:v', 'libvpx-vp9', '-i', path, '-vf', f'scale={W}:{H}', '-f', 'rawvideo',
                          '-pix_fmt', 'rgba', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            buf = p.stdout.read(W * H * 4)
            if len(buf) < W * H * 4:
                break
            yield np.frombuffer(buf, np.uint8).reshape(H, W, 4)
    finally:                                   # also when the caller stops early (--look)
        p.kill()
        p.stdout.close()
        p.wait()


def frame_of(path, f):
    r = subprocess.run([FF, '-loglevel', 'error', '-i', path, '-vf', f"select=eq(n\\,{f}),scale={W}:{H}", '-frames:v', '1',
                        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(H, W, 3) if len(r.stdout) == W * H * 3 else np.zeros((H, W, 3), np.uint8)


def kill_mask(mode, parts, f, a, hairmap=None):
    """-> (kill mask or None, measured ghost pixels, scale for the ghost-frame test, hair cells or None)."""
    if mode == 'basic':
        k = basic_kill(a)
        if k is None:
            return None, 0, BASIC_AREA, None
        return k, int(((a > LO) & (a < HI) & k).sum()), BASIC_AREA, None
    kill, cells = parts.kill(f, a, hairmap)
    if kill is None:
        return None, 0, 1, None
    w, h = parts.box[f][2], parts.box[f][3]
    return kill, int(((a > LO) & (a < HI) & kill).sum()), FRAME_AREA * w * h, cells


def main():
    global FF
    FF = skillenv.tool('ffmpeg')
    proj = skillenv.path_arg(sys.argv[1])
    os.chdir(proj)
    src = arg('--src', 'assets/aroll.mp4')
    cut = arg('--cut', 'assets/subject.webm')
    look = None
    if '--look' in sys.argv:
        look = []
        for v in sys.argv[sys.argv.index('--look') + 1:]:
            if not v.lstrip('-').isdigit():
                break
            look.append(int(v))
    os.makedirs('work', exist_ok=True)
    cache = os.path.join('work', 'head_track_' + os.path.splitext(os.path.basename(src))[0] + '.json')
    rows, why = (None, 'asked for the simpler check') if '--basic' in sys.argv else track(src, cache)
    if '--prepare' in sys.argv:
        say('head check: face finder ready' if rows is not None else f'head check: no face finder ({why})')
        return 0
    name = os.path.splitext(os.path.basename(cut))[0]
    before = os.path.join('work', f'{name}_before_head_clean.webm')
    if '--redo' in sys.argv and os.path.isfile(before):
        shutil.copyfile(before, cut)                 # start again from the cutout as it was matted
        say('head check: starting again from the cutout as it was matted')
    if not os.path.isfile(cut):
        say(f'head check: skipped, there is no cutout at {cut}')
        return 2
    mode = 'vision' if rows is not None else 'basic'
    parts = None
    if mode == 'vision':
        n = int(subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries',
                                'stream=nb_read_packets', '-of', 'csv=p=0', cut], **skillenv.TEXT).stdout.strip().split(',')[0] or 0)
        rows = align(rows, src, n)
        if rows is None:
            why = 'the face finder and the cutout do not line up frame for frame'
            mode = 'basic'
        else:
            parts = Parts(rows, n)
            if parts.faces_seen == 0:
                say('head check: no face in the footage, nothing to check')
                return 0

    # 1. measure (and learn where the hair or hat sits)
    ghost_frames = checked = 0
    hair_count = np.zeros(GRID, np.int32)
    for f, fr in enumerate(alpha_frames(cut)):
        a = fr[..., 3].astype(np.float32) / 255
        kill, ghost, limit, cells = kill_mask(mode, parts, f, a)
        if kill is None:
            continue
        checked += 1
        ghost_frames += ghost > limit
        if cells is not None:
            hair_count += cells
    hairmap = hair_count >= HAIR_SHARE * max(checked, 1)
    need = max(MIN_FRAMES, SHARE * checked)
    how = 'Apple Vision' if mode == 'vision' else 'the simpler check' + (f': {why}' if why else '')

    if look is not None:
        from PIL import Image
        g = np.array([24, 177, 76], np.float32)
        say(f'head check (look only): {ghost_frames} of {checked} frames over the line, {int(need)} needed to clean')
        for f, fr in enumerate(alpha_frames(cut)):
            if f > max(look, default=-1):
                break
            if f not in look:
                continue
            a = fr[..., 3].astype(np.float32) / 255
            kill, ghost, _, _ = kill_mask(mode, parts, f, a, hairmap)
            k = 1 - ndimage.gaussian_filter(kill.astype(np.float32), 3) if kill is not None else np.ones((H, W), np.float32)

            def over(al):
                return (fr[..., :3] * al[..., None] + g * (1 - al[..., None])).astype(np.uint8)
            Image.fromarray(np.hstack([frame_of(src, f), over(a), over(a * k)])).resize((W * 3 // 2, H // 2)).save(
                f'work/head_clean_{f}.jpg', quality=85)
            say(f'wrote work/head_clean_{f}.jpg (ghost pixels {ghost})')
        return 0

    if ghost_frames < need:
        say(f'head check: clean, nothing behind the head kept in the cutout ({ghost_frames} of {checked} frames, {how}); '
            'cutout unchanged')
        return 0

    # 2. clean every frame (only some frames over the line would make the ghost flicker in and out)
    tmp = cut + '.part'
    enc = subprocess.Popen([FF, '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', '30',
                            '-i', '-', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '20', '-g', '30',
                            '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4', '-metadata:s:v:0', 'alpha_mode=1',
                            '-f', 'webm', tmp], stdin=subprocess.PIPE)
    n = 0
    for f, fr in enumerate(alpha_frames(cut)):
        a = fr[..., 3].astype(np.float32) / 255
        kill = kill_mask(mode, parts, f, a, hairmap)[0]
        out = fr.copy()
        if kill is not None and kill.any():
            k = 1 - ndimage.gaussian_filter(kill.astype(np.float32), 3)
            out[..., 3] = (fr[..., 3] * k).astype(np.uint8)
        enc.stdin.write(out.tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    if enc.returncode != 0 or not os.path.isfile(tmp):
        say('head check: found a picture behind the head in the cutout but could not write the cleaned one; cutout unchanged')
        return 2
    os.replace(cut, before)
    os.replace(tmp, cut)
    if mode == 'vision':
        say(f'head check: CLEANED. A picture behind the head was kept in the cutout on {ghost_frames} of {checked} frames; '
            f'removed it on all {n} frames ({how}). The cutout as it was: {before}')
    else:
        fix = ("on this Mac, install Apple's free command line tools (xcode-select --install), then run "
               'head_clean.py <project> --redo' if platform.system() == 'Darwin' else
               'on a Mac the full clean runs by itself; here, look at the head in the checks')
        say(f'head check: PARTLY CLEANED. A picture behind the head was kept in the cutout on {ghost_frames} of {checked} '
            f'frames; the faint part of it is removed ({how}), a solid part of it can still show. For the full clean: {fix}. '
            f'The cutout as it was: {before}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
