#!/usr/bin/env python3
"""Studio Picker for Claude Creator Studio.

Opens a local page where you pick a caption style and the effects you like (or one overall style),
then saves the picks to a JSON file the skill reads. Python 3 standard library only. Mac, Linux, Windows.

    python3 serve.py                      open the picker
    python3 serve.py --tab captions       open straight on the captions (also: effects, styles)
    python3 serve.py --config <path>      where the picks are saved (default: studio-picks.json beside this file)
    python3 serve.py --captions <path>    the caption styles list (default: ../captions/styles.json)
    python3 serve.py --styles <path>      the overall styles list (default: data/styles.json)
    python3 serve.py --port 4750         use this port (default: 4747, or any open port if that one is taken)
    python3 serve.py --no-open            do not open the browser
    python3 serve.py --keep-alive         keep running after the page is closed

Lines it prints (one per event, easy to read from another program):

    STATUS picker READY http://127.0.0.1:4747/
    STATUS picks SAVED <path> mode=custom style=none captions=vanity effects=digital-zoom,checklist parts=off
    STATUS picker CLOSED

parts= is "off" when effects can land anywhere, else hook:<keys>;middle:<keys>;end:<keys>.

It listens on 127.0.0.1 only, answers only requests addressed to localhost, and serves only the picker's own
files and the caption preview clips. It stops about 25 seconds after the page is closed (a reload does not
count), on Ctrl+C, or on POST /api/done (send it as JSON, for example with the body {}).

Picks file:
    {"mode": "preset" | "custom", "style": "<key>" | null, "captionStyle": "<key>" | "none",
     "effects": ["<key>", ...],
     "effectSections": null | {"hook": ["<key>", ...], "middle": [...], "end": [...]},
     "updated": "<ISO time>"}

captionStyle "none" means no caption style: titles and effects only.
mode "preset" keeps the overall style the buyer picked; captionStyle and effects start as that style's own
and may have been changed. effectSections is null when effects can land anywhere in the reel; otherwise every
picked effect is listed under each part it is allowed in.
"""
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, 'studio-picks.json')
DEFAULT_CAPTIONS = os.path.normpath(os.path.join(HERE, '..', 'captions', 'styles.json'))
DEFAULT_STYLES = os.path.join(HERE, 'data', 'styles.json')
DEFAULT_PORT = 4747
PRODUCT = 'Claude Creator Studio'
PARTS = (('hook', 'Hook'), ('middle', 'Middle'), ('end', 'End'))      # the parts of a reel an effect can be kept to
PART_KEYS = tuple(k for k, _ in PARTS)
# captionStyle "none": no caption style at all. Some overall styles carry their words inside the look itself.
NO_CAPTIONS = {'key': 'none', 'name': 'No captions', 'label': '', 'line': 'Titles and effects only.',
               'preview': None, 'poster': None, 'none': True}

KEY_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
LOCAL_HOSTS = ('localhost', '127.0.0.1')
STATIC_DIRS = ('assets', 'data', 'previews')          # the only folders of the picker that are ever served
CAPTIONS_URL = '/captions/previews/'                  # mapped to <captions folder>/previews
MAX_BODY = 64 * 1024
OPEN_FOR = 300.0                                      # seconds without a sign of life from the page before stopping
CLOSE_AFTER = 25.0                                    # seconds to stop after the page says it is closing

TYPES = {
    '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8', '.mp4': 'video/mp4', '.webm': 'video/webm', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2', '.ico': 'image/x-icon',
}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' "
       "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
       "media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def say(line):
    print(line, flush=True)


def warn(line):
    print('picker: ' + line, file=sys.stderr, flush=True)


def read_json(path, fallback):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except (OSError, ValueError) as e:
        warn('could not read %s (%s)' % (path, e))
        return fallback


def inside(root, path):
    """True when path is a real file inside root (symlinks resolved)."""
    try:
        root_r = os.path.realpath(root)
        path_r = os.path.realpath(path)
        return os.path.isfile(path_r) and os.path.commonpath([root_r, path_r]) == root_r
    except (OSError, ValueError):
        return False


def text(value, limit=200):
    return value.strip()[:limit] if isinstance(value, str) else ''


# ---------------------------------------------------------------------------------------------------------
# Catalog: caption styles (from the captions folder), effects and overall styles (from data/).
# mode 'server' gives URLs this server answers; mode 'file' gives paths relative to index.html, for the
# snapshot the page uses when it is opened as a plain file.
# ---------------------------------------------------------------------------------------------------------
def build_catalog(captions_json=DEFAULT_CAPTIONS, mode='server', styles_json=None):
    styles_json = styles_json or DEFAULT_STYLES
    cap_dir = os.path.dirname(os.path.abspath(captions_json))
    cap_prev = os.path.join(cap_dir, 'previews')

    def picker_url(rel):
        """A file of the picker (rel uses forward slashes), or None when it is missing or not allowed."""
        if not isinstance(rel, str) or not rel or rel.startswith('/') or '\\' in rel:
            return None
        parts = rel.split('/')
        if parts[0] not in STATIC_DIRS or any(p in ('', '.', '..') for p in parts):
            return None
        if not inside(os.path.join(HERE, parts[0]), os.path.join(HERE, *parts)):
            return None
        return ('/' + rel) if mode == 'server' else rel

    def caption_url(rel):
        if not isinstance(rel, str) or not rel:
            return None
        name = rel.replace('\\', '/').split('/')[-1]
        full = os.path.join(cap_prev, name)
        if not inside(cap_prev, full):
            return None
        if mode == 'server':
            return CAPTIONS_URL + urllib.parse.quote(name)
        return os.path.relpath(full, HERE).replace(os.sep, '/')

    captions = []
    seen = set()
    for s in (read_json(captions_json, {}) or {}).get('styles', []):
        if not isinstance(s, dict):
            continue
        key = s.get('key')
        if not isinstance(key, str) or not KEY_RE.match(key) or key in seen or key == NO_CAPTIONS['key']:
            continue
        seen.add(key)
        best = text(s.get('bestFor'))
        captions.append({
            'key': key, 'name': text(s.get('name'), 60) or key,
            'label': 'Best for' if best else '',
            'line': best or text(s.get('look')),
            'preview': caption_url(s.get('preview') or ('previews/%s.mp4' % key)),
            'poster': picker_url('previews/posters/captions/%s.jpg' % key),
        })
    captions.append(dict(NO_CAPTIONS))                     # always the last card: captionStyle "none"
    caption_keys = {c['key'] for c in captions}

    fx_data = read_json(os.path.join(HERE, 'data', 'effects.json'), {}) or {}
    effects = []
    seen = set()
    for e in fx_data.get('effects', []):
        if not isinstance(e, dict):
            continue
        key = e.get('key')
        if not isinstance(key, str) or not KEY_RE.match(key) or key in seen:
            continue
        seen.add(key)
        effects.append({                                   # "job" stays in the data file; the page never shows it
            'n': e.get('n'), 'key': key, 'name': text(e.get('name'), 60) or key,
            'line': text(e.get('line')),
            'preview': picker_url(e.get('preview', 'previews/effects/%s.mp4' % key)),    # null = plain card on purpose
            'poster': picker_url(e.get('poster') or ('previews/posters/effects/%s.jpg' % key)),
        })
    effect_keys = {e['key'] for e in effects}

    st_data = read_json(styles_json, {}) or {}
    group_labels = {g.get('key'): text(g.get('label'), 40) for g in st_data.get('groups', []) if isinstance(g, dict)}
    styles = []
    seen = set()
    for s in st_data.get('styles', []):
        if not isinstance(s, dict):
            continue
        key = s.get('key')
        if not isinstance(key, str) or not KEY_RE.match(key) or key in seen:
            continue
        seen.add(key)
        cap = s.get('captionStyle') if s.get('captionStyle') in caption_keys else None
        fx = [k for k in (s.get('effects') or []) if k in effect_keys]
        ready = bool(s.get('ready')) and cap is not None        # a style cannot be picked until its captions exist
        if s.get('ready') and not ready:
            warn('style "%s" is marked ready but its caption style is missing; keeping it hidden' % key)
        styles.append({
            'n': s.get('n'), 'key': key, 'name': text(s.get('name'), 60) or key, 'group': text(s.get('group'), 30),
            'label': group_labels.get(s.get('group')) or '',
            'line': text(s.get('line')), 'captionStyle': cap, 'effects': fx, 'ready': ready,
            'preview': picker_url(s.get('preview', 'previews/styles/%s.mp4' % key)),
            'poster': picker_url(s.get('poster') or ('previews/posters/styles/%s.jpg' % key)),
        })

    return {'product': PRODUCT, 'captions': captions, 'effects': effects, 'styles': styles,
            'parts': [{'key': k, 'label': label} for k, label in PARTS]}


# ---------------------------------------------------------------------------------------------------------
# Picks
# ---------------------------------------------------------------------------------------------------------
def empty_picks():
    return {'mode': 'custom', 'style': None, 'captionStyle': None, 'effects': [], 'effectSections': None,
            'updated': None}


def clean_sections(raw, effects, strict):
    """effectSections: None (effects can land anywhere) or {"hook": [...], "middle": [...], "end": [...]}.
    Every key in it must be a picked effect, and every picked effect needs at least one part.
    strict=True (a save) reports what is wrong; strict=False (reading an old file) repairs it instead."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return (None, 'effectSections must be null or an object.') if strict else (None, None)
    extra = sorted(str(k) for k in raw if k not in PART_KEYS)
    if extra and strict:
        return None, 'Unknown part: ' + ', '.join(extra[:5])
    out = {}
    for part in PART_KEYS:
        keys = raw.get(part, [])
        if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
            if strict:
                return None, 'effectSections.%s must be a list of effect keys.' % part
            keys = []
        stray = sorted(set(keys) - set(effects))
        if stray and strict:
            return None, 'In effectSections but not picked: ' + ', '.join(stray[:5])
        chosen = set(keys)
        out[part] = [k for k in effects if k in chosen]
    homeless = [k for k in effects if not any(k in out[p] for p in PART_KEYS)]
    if homeless:
        if strict:
            return None, 'Picked but not in any part: ' + ', '.join(homeless[:5])
        for part in PART_KEYS:                             # an effect with no part can land anywhere
            out[part] = [k for k in effects if k in out[part] or k in homeless]
    return out, None


def check_picks(raw, catalog):
    """Validate picks sent by the page against the catalog. Returns (picks, None) or (None, 'what is wrong')."""
    if not isinstance(raw, dict):
        return None, 'Picks must be a JSON object.'
    captions = {c['key'] for c in catalog['captions']}
    effects_order = [e['key'] for e in catalog['effects']]
    styles = {s['key']: s for s in catalog['styles']}

    mode = raw.get('mode')
    if mode not in ('preset', 'custom'):
        return None, 'mode must be "preset" or "custom".'
    style = raw.get('style')
    if mode == 'preset':
        if not isinstance(style, str) or style not in styles:
            return None, 'Unknown overall style.'
        if not styles[style]['ready']:
            return None, 'That overall style is not ready yet.'
    else:
        style = None
    cap = raw.get('captionStyle')
    if not isinstance(cap, str) or cap not in captions:
        return None, 'Unknown caption style.'
    fx = raw.get('effects')
    if not isinstance(fx, list) or len(fx) > 200 or any(not isinstance(k, str) for k in fx):
        return None, 'effects must be a list of effect keys.'
    unknown = sorted(set(fx) - set(effects_order))
    if unknown:
        return None, 'Unknown effect: ' + ', '.join(unknown[:5])
    chosen = set(fx)
    effects = [k for k in effects_order if k in chosen]
    sections, error = clean_sections(raw.get('effectSections'), effects, strict=True)
    if error:
        return None, error
    return {'mode': mode, 'style': style, 'captionStyle': cap, 'effects': effects, 'effectSections': sections,
            'updated': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()}, None


def load_picks(path, catalog):
    """The saved picks, with anything the catalog no longer has dropped. Defaults when nothing is saved."""
    raw = read_json(path, None)
    picks = empty_picks()
    if not isinstance(raw, dict):
        return picks
    captions = {c['key'] for c in catalog['captions']}
    effects_order = [e['key'] for e in catalog['effects']]
    styles = {s['key']: s for s in catalog['styles']}
    if raw.get('captionStyle') in captions:
        picks['captionStyle'] = raw['captionStyle']
    if isinstance(raw.get('effects'), list):
        chosen = {k for k in raw['effects'] if isinstance(k, str)}
        picks['effects'] = [k for k in effects_order if k in chosen]
    picks['effectSections'] = clean_sections(raw.get('effectSections'), picks['effects'], strict=False)[0]
    if raw.get('mode') == 'preset' and raw.get('style') in styles and styles[raw['style']]['ready']:
        picks['mode'], picks['style'] = 'preset', raw['style']
    if isinstance(raw.get('updated'), str):
        picks['updated'] = raw['updated'][:40]
    return picks


def write_picks(path, picks):
    """Write to a temp file in the same folder, then swap it in, so the skill never reads a half-written file."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='.studio-picks-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(picks, f, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------------------------------------
class Picker(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'      # on Windows this flag would let two programs share the port

    def __init__(self, addr, config, captions_json, verbose=False, keep_alive=False, styles_json=None):
        super().__init__(addr, Handler)
        self.config = config
        self.captions_json = captions_json
        self.styles_json = styles_json or DEFAULT_STYLES
        self.captions_previews = os.path.join(os.path.dirname(os.path.abspath(captions_json)), 'previews')
        self.verbose = verbose
        self.keep_alive = keep_alive
        self.deadline = None                   # set once a page has loaded; None = wait for as long as it takes
        self.page = None                       # id of the page that checked in last
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()

    def catalog(self):
        return build_catalog(self.captions_json, 'server', self.styles_json)

    def seen(self, seconds=OPEN_FOR, page=None):
        with self.lock:
            self.deadline = time.monotonic() + seconds
            if page:
                self.page = page

    def closing(self, page):
        """A page says it is closing. Ignored when a newer page (a reload, a second tab) has checked in since."""
        with self.lock:
            if self.page in (None, page):
                self.deadline = time.monotonic() + CLOSE_AFTER

    def stop_soon(self):
        threading.Thread(target=self.shutdown, daemon=True).start()

    def watch(self):
        """Stop when the page has gone quiet (closed tab). A laptop waking from sleep gets a fresh window."""
        last = time.monotonic()
        while True:
            time.sleep(2)
            now = time.monotonic()
            with self.lock:
                if self.deadline is None:
                    last = now
                    continue
                if now - last > 15:
                    self.deadline = now + OPEN_FOR
                elif now > self.deadline:
                    break
            last = now
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    server_version = 'StudioPicker/1'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write('picker: %s %s\n' % (self.address_string(), fmt % args))

    # ---- guards ----
    def host_ok(self):
        host = (self.headers.get('Host') or '').strip().lower()
        if host.startswith('['):
            return False
        return host.rsplit(':', 1)[0] in LOCAL_HOSTS if ':' in host else host in LOCAL_HOSTS

    def origin_ok(self):
        origin = self.headers.get('Origin')
        if origin is None:
            return True
        try:
            parts = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        return parts.scheme == 'http' and (parts.hostname or '') in LOCAL_HOSTS

    # ---- replies ----
    def reply(self, status, body=b'', ctype='application/json; charset=utf-8', extra=None, head=False):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body and not head:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, status, obj):
        self.reply(status, json.dumps(obj).encode('utf-8'))

    def fail(self, status, message):
        self.close_connection = True
        self.send_json(status, {'ok': False, 'error': message})

    def send_file(self, path, head=False):
        ext = os.path.splitext(path)[1].lower()
        if ext not in TYPES:
            return self.fail(404, 'Not found.')
        try:
            size = os.path.getsize(path)
            f = open(path, 'rb')
        except OSError:
            return self.fail(404, 'Not found.')
        with f:
            start, end, status = 0, size - 1, 200
            rng = self.headers.get('Range')
            if rng:
                m = re.match(r'^\s*bytes=(\d*)-(\d*)\s*$', rng)
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                    if start >= size or start > end:
                        return self.reply(416, extra={'Content-Range': 'bytes */%d' % size}, head=head)
                    status = 206
            length = max(0, end - start + 1)
            self.send_response(status)
            self.send_header('Content-Type', TYPES[ext])
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if status == 206:
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
            if ext == '.html':
                self.send_header('Content-Security-Policy', CSP)
                self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            if head:
                return
            f.seek(start)
            left = length
            try:
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True      # the browser dropped a clip it no longer needs

    # ---- routes ----
    def route_get(self, head=False):
        if not self.host_ok():
            return self.fail(403, 'This picker only answers on localhost.')
        try:
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path, errors='strict')
        except (ValueError, UnicodeDecodeError):
            return self.fail(400, 'Bad request.')
        if '\x00' in path or '\\' in path:
            return self.fail(400, 'Bad request.')

        if path in ('/', '/index.html'):
            self.server.seen()
            return self.send_file(os.path.join(HERE, 'index.html'), head)
        if path == '/api/catalog':
            return self.send_json(200, self.server.catalog())
        if path == '/api/picks':
            return self.send_json(200, load_picks(self.server.config, self.server.catalog()))
        if path == '/api/ping':
            page = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('p', [''])[0][:40]
            self.server.seen(page=page)
            return self.send_json(200, {'ok': True})

        parts = path.split('/')
        if any(p in ('.', '..') for p in parts):
            return self.fail(404, 'Not found.')
        if path.startswith(CAPTIONS_URL):
            root, rel = self.server.captions_previews, path[len(CAPTIONS_URL):]
        elif len(parts) > 2 and parts[1] in STATIC_DIRS:
            root, rel = os.path.join(HERE, parts[1]), '/'.join(parts[2:])
        else:
            return self.fail(404, 'Not found.')
        full = os.path.join(root, *[p for p in rel.split('/') if p])
        if not rel or not inside(root, full):
            return self.fail(404, 'Not found.')
        return self.send_file(full, head)

    def do_GET(self):
        self.route_get()

    def do_HEAD(self):
        self.route_get(head=True)

    def do_POST(self):
        if not self.host_ok():
            return self.fail(403, 'This picker only answers on localhost.')
        if not self.origin_ok():
            return self.fail(403, 'This picker only takes requests from its own page.')
        if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
            return self.fail(415, 'Send JSON.')
        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            return self.fail(400, 'Bad request.')
        if length < 0 or length > MAX_BODY:
            return self.fail(413, 'Too large.')
        body = self.rfile.read(length) if length else b''
        path = urllib.parse.urlsplit(self.path).path

        if path == '/api/save':
            try:
                raw = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return self.fail(400, 'That was not valid JSON.')
            picks, error = check_picks(raw, self.server.catalog())
            if error:
                return self.fail(400, error)
            try:
                with self.server.write_lock:
                    write_picks(self.server.config, picks)
            except OSError as e:
                warn('could not write %s (%s)' % (self.server.config, e))
                return self.fail(500, 'Could not write the picks file.')
            self.server.seen()
            parts = picks['effectSections']
            say('STATUS picks SAVED %s mode=%s style=%s captions=%s effects=%s parts=%s' % (
                self.server.config, picks['mode'], picks['style'] or 'none', picks['captionStyle'],
                ','.join(picks['effects']) or 'none',
                ';'.join('%s:%s' % (p, ','.join(parts[p]) or 'none') for p in PART_KEYS) if parts else 'off'))
            return self.send_json(200, {'ok': True, 'picks': picks})
        if path == '/api/bye':
            try:
                page = str(json.loads(body.decode('utf-8')).get('p', ''))[:40]
            except (ValueError, UnicodeDecodeError, AttributeError):
                page = ''
            self.server.closing(page)
            return self.send_json(200, {'ok': True})
        if path == '/api/done':
            self.close_connection = True
            self.send_json(200, {'ok': True})
            return self.server.stop_soon()
        return self.fail(404, 'Not found.')

    def do_OPTIONS(self):
        self.fail(405, 'Not allowed.')

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS


def bind(port, config, captions_json, verbose, keep_alive, styles_json=None):
    """The asked port, or 4747, or any open port if 4747 is taken."""
    tries = [port] if port else [DEFAULT_PORT, 0]
    last = None
    for p in tries:
        try:
            return Picker(('127.0.0.1', p), config, captions_json, verbose, keep_alive, styles_json)
        except OSError as e:
            last = e
    raise last


def main(argv=None):
    ap = argparse.ArgumentParser(description='Studio Picker for Claude Creator Studio.')
    ap.add_argument('--config', default=DEFAULT_CONFIG, help='the picks file (default: studio-picks.json beside serve.py)')
    ap.add_argument('--captions', default=DEFAULT_CAPTIONS, help='the caption styles list (default: ../captions/styles.json)')
    ap.add_argument('--styles', default=DEFAULT_STYLES, help='the overall styles list (default: data/styles.json)')
    ap.add_argument('--tab', choices=('captions', 'effects', 'styles'), help='open straight on one section')
    ap.add_argument('--port', type=int, default=0, help='port to use (default: %d, or any open port)' % DEFAULT_PORT)
    ap.add_argument('--no-open', action='store_true', help='do not open the browser')
    ap.add_argument('--keep-alive', action='store_true', help='keep running after the page is closed')
    ap.add_argument('--verbose', action='store_true', help='log every request')
    args = ap.parse_args(argv)

    config = os.path.abspath(os.path.expanduser(args.config))
    captions_json = os.path.abspath(os.path.expanduser(args.captions))
    if not os.path.isfile(os.path.join(HERE, 'index.html')):
        warn('index.html is missing beside serve.py')
        return 2
    if not os.path.isfile(captions_json):
        warn('caption styles not found at %s (the page will open with no caption styles)' % captions_json)
    try:
        server = bind(args.port, config, captions_json, args.verbose, args.keep_alive,
                      os.path.abspath(os.path.expanduser(args.styles)))
    except OSError as e:
        warn('could not start on port %s (%s)' % (args.port or DEFAULT_PORT, e))
        return 2

    url = 'http://127.0.0.1:%d/' % server.server_address[1]
    if args.tab:
        url += '?tab=' + args.tab
    say('STATUS picker READY ' + url)
    say('STATUS picks FILE %s (%s)' % (config, 'found' if os.path.isfile(config) else 'not saved yet'))
    if not args.keep_alive:
        threading.Thread(target=server.watch, daemon=True).start()
    if not args.no_open:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        say('STATUS picker CLOSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
