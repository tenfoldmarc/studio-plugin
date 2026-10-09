#!/usr/bin/env python3
"""Put a GIF the buyer asked for into the reel: a GIF file, or a link to one (a direct address, or a Giphy or
Tenor page). It becomes a small clip that plays in step with the reel, kept see-through where the GIF is, and
one entry in <project>/plan.json ("layers"). Run build_reel.py afterwards.

Usage:  PY gif_add.py <project_dir> "<gif file or link>" --from <sec> --to <sec>
                      [--place auto|above|left|right|top|chest] [--at X,Y] [--width 380] [--id name]
                      [--in pop|fade|slide-up|none] [--out fade|none] [--radius 18]
        PY gif_add.py <project_dir> --remove <id>

  --from / --to   reel seconds: the line the GIF reacts to. It loops for as long as it is on.
  --place         where it sits. auto (default): above the head when there is room, else on the open wall beside
                  the speaker, else at the top of the safe zone. --at X,Y puts its top left corner exactly there.
  --width         its width on the 1080 wide frame. It is made smaller on its own when the spot is tight.
It never sits on the face and stays inside the Reels safe zone. Also takes a short .mp4, .mov, .webm or a still
.png / .jpg. Prints  STATUS gif READY ...  or  STATUS gif FAILED <why>.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
TYPES = {'image/gif': '.gif', 'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov', 'image/png': '.png',
         'image/jpeg': '.jpg'}
STILL = ('.png', '.jpg', '.jpeg')
MAX_BYTES = 80 * 1024 * 1024
SAFE = dict(top=228, bottom=1470, left=35, right=1045, right_low=980, low_from=1155)   # the Reels safe zone
GAP = 26   # px kept clear between the GIF and the head


def say(line):
    print(line, flush=True)


def fail(why):
    say(f'STATUS gif FAILED: {why}')
    sys.exit(2)


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def num(name, default=None):
    v = opt(name)
    try:
        return float(v) if v is not None else default
    except ValueError:
        fail(f'{name} needs a number, got "{v}".')


def get(url, limit=MAX_BYTES):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        data = r.read(limit + 1)
    return ctype, data


def media_address(page_html):
    """The GIF or clip a Giphy / Tenor / other page points at (its og: tags), or None."""
    found = {}
    for prop, val in re.findall(r'<meta[^>]+(?:property|name)=["\'](og:video(?::url|:secure_url)?|og:image(?::url)?)["\'][^>]+content=["\']([^"\']+)["\']', page_html, re.I):
        found.setdefault(prop.lower().split(':')[1], val.replace('&amp;', '&'))
    for prop, val in re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](og:video(?::url|:secure_url)?|og:image(?::url)?)["\']', page_html, re.I):
        found.setdefault(val.lower().split(':')[1], prop.replace('&amp;', '&'))
    img, vid = found.get('image', ''), found.get('video', '')
    if '.gif' in img.lower():
        return img          # the GIF itself keeps its see-through parts; the page's mp4 does not
    return vid or img or None


def fetch(src, folder):
    """A file on this computer or a link -> a local file. Returns its path."""
    src = src.strip().strip('"\'')
    if not src.lower().startswith(('http://', 'https://')):
        path = os.path.abspath(skillenv.path_arg(src))
        if not os.path.isfile(path):
            fail(f'{path} is not a file on this computer.')
        return path
    try:
        g = re.search(r'giphy\.com/(?:gifs|stickers|clips)/(?:[^/?#]*-)?([A-Za-z0-9]{8,})', src)
        url = f'https://media.giphy.com/media/{g.group(1)}/giphy.gif' if g else src
        # Tenor lists a small copy (id ends ...AAAAM). The full one ends ...AAAAC: try it first, keep the small one if not.
        t = re.match(r'(https://media\d*\.tenor\.com/)(?:m/)?([A-Za-z0-9_\-]+AAAA)M(/.+\.gif)$', url)
        ctype, data = '', b''
        if t:
            try:
                ctype, data = get(f'{t.group(1)}{t.group(2)}C{t.group(3)}')
            except (urllib.error.URLError, OSError, ValueError):
                ctype, data = '', b''
            if data[:3] == b'GIF':
                url = f'{t.group(1)}{t.group(2)}C{t.group(3)}'
        if data[:3] != b'GIF':
            ctype, data = get(url)
        if ctype.startswith('text/html'):
            inner = media_address(data.decode('utf-8', 'replace'))
            if not inner:
                fail('that link is a page with no GIF on it. Ask for the GIF file, or a link that ends in .gif.')
            url = urllib.parse.urljoin(url, inner)
            ctype, data = get(url)
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        ext = ext if ext in tuple(TYPES.values()) + ('.jpeg', '.m4v') else TYPES.get(ctype, '')
        if not ext or len(data) < 200:
            fail('that link did not give a GIF, a short clip or a picture.')
        if len(data) > MAX_BYTES:
            fail('that file is far too large for a GIF.')
        dest = os.path.join(folder, 'src-' + hashlib.sha1(src.encode('utf-8', 'replace')).hexdigest()[:8] + ext)
        with open(dest, 'wb') as fh:
            fh.write(data)
        return dest
    except (urllib.error.URLError, OSError, ValueError) as e:
        fail(f'the link did not answer ({type(e).__name__}). Ask the buyer for the GIF file instead.')


def probe(path):
    try:
        out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                              'stream=width,height', '-of', 'csv=p=0:s=x', path], timeout=60, **skillenv.TEXT).stdout.strip()
        w, h = out.splitlines()[0].split('x')[:2]
        return int(w), int(h)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        fail('that file is not a GIF, a short clip or a picture this can read.')


def spot(layout, place, at, w, ratio):
    """Top left corner and width of the GIF on the 1080x1920 frame: never on the face, inside the safe zone."""
    head = layout.get('head') or {}
    bands = layout.get('bands') or {}
    top, chin, cx = head.get('top', 452), head.get('chin', 660), head.get('cx', 540)

    def above(width):
        room = top - GAP - SAFE['top']
        if room < 150:
            return None
        width = min(width, room / ratio)
        return cx - width / 2, top - GAP - width * ratio, width

    def wall(side, width):
        spot_ = bands.get('WALL_LEFT' if side == 'left' else 'WALL_RIGHT')
        if not spot_:
            return None
        x, y, free = spot_[:3]
        width = min(width, free)
        return (x + (free - width) / 2, y - width * ratio / 2, width) if width >= 150 else None

    if at:
        x, y, width = at[0], at[1], w
    else:
        order = {'above': [above], 'left': [lambda n: wall('left', n)], 'right': [lambda n: wall('right', n)],
                 'top': [], 'chest': [],
                 'auto': [above] + sorted([lambda n: wall('left', n), lambda n: wall('right', n)],
                                          key=lambda f: -(f(w) or (0, 0, 0))[2])}.get(place)
        if order is None:
            fail(f'--place "{place}" is not one of auto, above, left, right, top, chest.')
        got = next((r for r in (f(w) for f in order) if r), None)
        if place == 'chest':
            got = (540 - w / 2, max(chin + 60, bands.get('Y_CHEST', 1170) - w * ratio), w)
        if not got:
            if place not in ('auto', 'top'):
                say(f'NOTE: no room for the GIF {place} the speaker in this clip, so it sits at the top of the safe zone.')
            got = (540 - w / 2, SAFE['top'], w)
        x, y, width = got
    h = width * ratio
    y = min(max(y, SAFE['top']), SAFE['bottom'] - h)
    right = SAFE['right_low'] if y + h > SAFE['low_from'] else SAFE['right']
    x = min(max(x, SAFE['left']), right - width)
    # the face (top of the head to the chin, head width) must stay clear
    hl, hr = head.get('left', cx - 110), head.get('right', cx + 110)
    if not at and x < hr and x + width > hl and y < chin and y + h > top:
        y = max(SAFE['top'], top - GAP - h)
        if y + h > top:
            fail('there is no spot for a GIF in this clip that keeps the face clear. Try a smaller --width, or --at X,Y.')
    return round(x), round(y), round(width)


def main():
    skillenv.utf8_stdio()
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    proj = os.path.abspath(skillenv.path_arg(args[0]))
    plan_path = os.path.join(proj, 'plan.json')
    if not os.path.isfile(plan_path):
        fail(f'{plan_path} is missing. Run init_project.py first (step 6).')
    with open(plan_path, encoding='utf-8') as fh:
        plan = json.load(fh)
    layers = [l for l in (plan.get('layers') or []) if isinstance(l, dict)]

    gone = opt('--remove')
    if gone:
        keep = [l for l in layers if l.get('id') != gone]
        if len(keep) == len(layers):
            fail(f'there is no layer called "{gone}" in this reel.')
        plan['layers'] = keep
        with open(plan_path, 'w', encoding='utf-8') as fh:
            json.dump(plan, fh, indent=1, ensure_ascii=False)
        say(f'STATUS gif REMOVED {gone}')
        return

    values = {opt(n) for n in ('--from', '--to', '--place', '--at', '--width', '--id', '--in', '--out', '--radius')}
    src = next((a for a in args[1:] if a not in values), None)
    t0, t1 = num('--from'), num('--to')
    if not src or t0 is None or t1 is None or t1 - t0 < .3:
        fail('give the GIF (a file or a link) and --from / --to in reel seconds, at least 0.3 s apart.')

    folder = os.path.join(proj, 'assets', 'gifs')
    os.makedirs(folder, exist_ok=True)
    path = fetch(src, folder)
    sw, sh = probe(path)
    ratio = sh / sw

    layout = {}
    if os.path.isfile(os.path.join(proj, 'layout.json')):
        with open(os.path.join(proj, 'layout.json'), encoding='utf-8') as fh:
            layout = json.load(fh)
    at = None
    if opt('--at'):
        try:
            at = [float(v) for v in opt('--at').split(',')[:2]]
        except ValueError:
            fail('--at needs X,Y in pixels on the 1080x1920 frame.')
    x, y, w = spot(layout, opt('--place', 'auto'), at, min(max(num('--width', 380), 120), 1010), ratio)
    w -= w % 2
    h = max(2, round(w * ratio / 2) * 2)

    gid = skillenv.safe_name(opt('--id') or 'gif-' + hashlib.sha1(f'{src}{t0}'.encode('utf-8', 'replace')).hexdigest()[:6])[:40]
    out = os.path.join(folder, gid + '.webm')
    dur = t1 - t0
    ext = os.path.splitext(path)[1].lower()
    loop = ['-loop', '1'] if ext in STILL else ['-ignore_loop', '0'] if ext == '.gif' else ['-stream_loop', '-1']
    cmd = [skillenv.tool('ffmpeg'), '-v', 'error', '-y', *loop, '-i', path, '-t', f'{dur:.3f}', '-an',
           '-vf', f'fps=30,scale={w}:{h}:flags=lanczos,format=yuva420p', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p',
           '-b:v', '0', '-crf', '30', '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4',
           '-metadata:s:v:0', 'alpha_mode=1', out]
    try:
        done = subprocess.run(cmd, timeout=600, **skillenv.TEXT)
    except (OSError, subprocess.SubprocessError) as e:
        fail(f'the GIF could not be turned into a clip ({type(e).__name__}).')
    if done.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) < 200:
        fail('the GIF could not be turned into a clip: ' + (done.stderr or '').strip()[-200:])

    layer = {'id': gid, 'anchor': 'full', 'from': round(t0, 3), 'to': round(t1, 3), 'in': opt('--in', 'pop'),
             'out': opt('--out', 'fade'),
             'media': {'src': 'assets/gifs/' + gid + '.webm', 'x': x, 'y': y, 'w': w, 'radius': round(num('--radius', 18))}}
    plan['layers'] = [l for l in layers if l.get('id') != gid] + [layer]
    with open(plan_path, 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    say(f'STATUS gif READY {gid}: {w}x{h} at x {x}, y {y}, from {t0:.2f}s to {t1:.2f}s ({os.path.getsize(out) / 1e6:.1f} MB)')
    say(f'next: PY build_reel.py "{skillenv.shell_path(proj)}" --safe, then look at a snapshot inside {t0:.1f} to {t1:.1f}s: '
        'the GIF must not sit on the face or on a caption. Move it with --place or --at and run this again (same --id).')


if __name__ == '__main__':
    main()
