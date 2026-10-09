#!/usr/bin/env python3
"""Small shared helpers for the effect slot scripts (fx_new.py, fx_run.py, fx_add.py) and build_reel.py.
Standard library only.

An effect in effects/index.json is one of two kinds ("status"):
  ready    packaged: effects/<key>/ holds the finished machinery plus slot.json (what it needs, how it runs in a
           reel). Make a slot with fx_new.py, fill the CLIP block, run the listed commands, add it with fx_add.py.
  recipe   the finished build of one real reel: the editing Claude adapts it by hand (see effects/INDEX.md).
"""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

EFFECTS = os.path.join(skillenv.SKILL_DIR, 'effects')
SAFE_MARK = 'rgba(255,0,0,.28)'        # the red safe-zone guide every build draws with SAFE=1
PARTS = ('hook', 'middle', 'end')


def read(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def write(path, data):
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, indent=1)
        fh.write('\n')


def index():
    """-> {key: entry} from effects/index.json"""
    return {e['key']: e for e in (read(os.path.join(EFFECTS, 'index.json'), {}) or {}).get('effects', [])}


def slot_meta(key):
    """effects/<key>/slot.json of a ready effect, or None for a recipe."""
    return read(os.path.join(EFFECTS, key, 'slot.json'))


def ready_keys():
    return sorted(k for k, e in index().items() if e.get('status') == 'ready' and slot_meta(k))


def probe_frames(path):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                          '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout
    try:
        return int(out.strip().split(',')[0])
    except ValueError:
        return 0


def probe_size(path):
    out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height', '-of', 'csv=p=0', path], **skillenv.TEXT).stdout.strip().split(',')
    try:
        return int(out[0]), int(out[1])
    except (ValueError, IndexError):
        return 0, 0


def luma(path, frame):
    """Mean brightness (0 to 255) of one frame, measured on a small grey copy."""
    raw = subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', '-i', path, '-vf',
                          f"select='eq(n\\,{int(frame)})',scale=108:192,format=gray", '-frames:v', '1', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    return sum(raw) / len(raw) if raw else 0.0


# ------------------------------------------------------------------ making a slot match the footage around it
# Every pass through the renderer shifts the picture a little (shadows a touch darker, reds a touch weaker). The
# reel's own footage goes through it once, a slot goes through it twice (its own render, then the reel's), so an
# untreated slot shows as a small step in tone and colour at both of its edges. The slot's first frame is still the
# plain footage, so that one pass can be measured there, pixel against pixel, and taken back out of the slot file.
# accurate_rnd matters: the fast conversion paths round down and would darken the slot by a level or two on their own
_TO_RGB = 'scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int+bitexact,format=rgb24'
_TO_YUV = 'scale=out_color_matrix=bt709:in_range=pc:out_range=tv:flags=accurate_rnd+full_chroma_int+bitexact,format=yuv420p'


def _rgb_frame(path, frame, w=270, h=480):
    import numpy as np
    raw = subprocess.run([skillenv.tool('ffmpeg'), '-v', 'error', '-i', path, '-vf',
                          f"select='eq(n\\,{int(frame)})',scale={w}:{h}:flags=area,{_TO_RGB}", '-frames:v', '1',
                          '-f', 'rawvideo', '-'], capture_output=True).stdout
    if len(raw) != w * h * 3:
        return None
    return np.frombuffer(raw, np.uint8).astype(np.float64).reshape(-1, 3)


def pass_fit(aroll, frame, render):
    """What one renderer pass did to the footage: render frame 0 = M * (a-roll frame) + t, fitted on the pixels the
    effect has not touched. -> {'M', 't', 'rms', 'share'} or None (numpy missing, frames unreadable)."""
    try:
        import numpy as np
    except ImportError:
        return None
    a, s = _rgb_frame(aroll, frame), _rgb_frame(render, 0)
    if a is None or s is None:
        return None
    X = np.hstack([a, np.ones((len(a), 1))])
    keep = np.ones(len(a), bool)
    for _ in range(3):                         # refit without the pixels an effect already covers on frame 0
        B = np.linalg.lstsq(X[keep], s[keep], rcond=None)[0]
        err = np.abs(s - X @ B).max(axis=1)
        keep = err < 8
        if keep.sum() < 2000:
            return None
    rms = float(np.sqrt(((s[keep] - X[keep] @ B) ** 2).mean()))
    return {'M': B[:3].T, 't': B[3], 'rms': rms, 'share': float(keep.mean())}


def undo_pass(render, out, fit, frames):
    """Write `out` = the slot render with that one pass taken back out (same frames, same audio). -> frames written."""
    import numpy as np
    ff = skillenv.tool('ffmpeg')
    inv = np.linalg.inv(fit['M']).T.astype(np.float32)
    t = fit['t'].astype(np.float32)
    w, h = 1080, 1920
    dec = subprocess.Popen([ff, '-v', 'error', '-i', render, '-vf', _TO_RGB, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([ff, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}', '-r', '30',
                            '-i', '-', '-i', render, '-map', '0:v:0', '-map', '1:a:0?', '-vf', _TO_YUV, '-frames:v', str(frames),
                            '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-g', '30', '-pix_fmt', 'yuv420p',
                            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                            '-c:a', 'copy', out], stdin=subprocess.PIPE)
    size, n = w * h * 3, 0
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        x = np.frombuffer(buf, np.uint8).astype(np.float32).reshape(-1, 3)
        try:
            enc.stdin.write(np.clip((x - t) @ inv + .5, 0, 255).astype(np.uint8).tobytes())
        except (BrokenPipeError, OSError):      # the encoder stopped early: the caller sees the short frame count
            break
        n += 1
    dec.stdout.close()
    try:
        enc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    enc.wait()
    dec.wait()
    return n


# ------------------------------------------------------------------ the parts of a reel the buyer allowed
def reel_parts(project):
    """-> ({'hook': (t0, t1), 'middle': (t0, t1) | None, 'end': (t0, t1) | None}, duration). Same rule as the
    footage check: hook = the opening line, end = the call to action, middle = everything between."""
    from footage_check import parts
    words = read(os.path.join(project, 'words.json'), []) or []
    segs = read(os.path.join(project, 'segments.json'), []) or []
    plan = read(os.path.join(project, 'plan.json'), {}) or {}
    dur = (segs[-1]['frame'] + segs[-1]['frames']) / 30 if segs else (words[-1]['end'] if words else 0.0)
    return parts(words, dur, plan), dur


def part_verdict(picks, key, where, t0, t1):
    """May effect `key` play from t0 to t1? -> (ok, one plain line).
    No "effectSections" in the picks: anywhere. Otherwise at least 60% of the slot has to sit inside the parts the
    buyer ticked for this effect (a slot may spill a little over the end of the opening line)."""
    sections = (picks or {}).get('effectSections')
    if not sections:
        return True, 'the buyer set no parts: it may go anywhere in the reel'
    allowed = [p for p in PARTS if key in (sections.get(p) or [])]
    if not allowed:
        return False, 'the buyer did not allow it in any part of the reel'
    inside = 0.0
    for p in allowed:
        span = where.get(p)
        if span:
            inside += max(0.0, min(t1, span[1]) - max(t0, span[0]))
    share = inside / max(t1 - t0, 1e-6)
    spans = ', '.join(f'{p} {where[p][0]:.2f} to {where[p][1]:.2f}s' if where.get(p) else f'{p} (this reel has none)'
                      for p in allowed)
    if share >= .6:
        return True, f'allowed in: {spans}'
    return False, (f'the buyer only allowed it in: {spans}. {t0:.2f} to {t1:.2f}s is outside that '
                   f'({share * 100:.0f}% inside, it needs 60%)')


# ------------------------------------------------------------------ does the slot's cutout agree with layout.json?
def head_check(project, slot, t0, limit=60):
    """Reads the head off the slot's own clean cutout (three frames of assets/subject.webm) and compares it with what
    layout.py wrote for that part of the reel. -> a warning line when head top or chin differ by more than `limit`
    px, else None. None too when there is nothing to compare (no cutout, no layout, nobody on camera)."""
    subject = os.path.join(slot, 'assets', 'subject.webm')
    lay = read(os.path.join(project, 'layout.json'), {}) or {}
    if not os.path.isfile(subject) or not lay.get('head'):
        return None
    try:
        import statistics
        from PIL import Image
        import layout
    except ImportError:
        return None
    work = os.path.join(slot, 'work')
    os.makedirs(work, exist_ok=True)
    found = []
    frames = probe_frames(subject)
    for i, f in enumerate(sorted({0, frames // 2, max(frames - 1, 0)})):
        png = os.path.join(work, f'headcheck_{i}.png')
        r = subprocess.run([skillenv.tool('ffmpeg'), '-loglevel', 'error', '-y', '-c:v', 'libvpx-vp9', '-i', subject, '-vf',
                            f"select='eq(n\\,{f})',alphaextract,scale={layout.SW}:{layout.SH}", '-frames:v', '1', png])
        if r.returncode != 0 or not os.path.isfile(png):
            continue
        rows, area = layout.main_blob(Image.open(png).convert('L'))
        h = layout.read_head(rows) if area >= .03 * layout.SW * layout.SH else None
        if h:
            found.append(h)
    if not found:
        return None
    top = int(statistics.median(h['top'] for h in found))
    chin = int(statistics.median(h['chin'] for h in found))
    seg = next((s for s in lay.get('segments') or [] if s.get('head_top') is not None
                and s['t0'] - .01 <= t0 < s['t1']), None)
    l_top = seg['head_top'] if seg else lay['head']['top']
    l_chin = seg['chin'] if seg and seg.get('chin') is not None else lay['head']['chin']
    if abs(top - l_top) <= limit and abs(chin - l_chin) <= limit:
        return None
    return (f'CHECK layout.json: this slot\'s clean cutout puts the head at top {top}, chin {chin}, but layout.json says top '
            f'{l_top}, chin {l_chin} for this part of the reel. The cutout is usually the one that is right (a picture or '
            'poster behind the head can fool the quick measurement). Look at work/layout/check.jpg, then run layout.py '
            'again (it uses the clean cutout now that it is installed) or correct "head" and "bands" in layout.json, '
            'and rebuild the reel: captions and the self-check both read those numbers.')
