#!/usr/bin/env python3
"""Posting: the buyer's finished reels go out to Instagram (as normal reels or trial reels), TikTok, YouTube Shorts,
Facebook Reels and the other platforms Zernio supports, now or at set times, through the buyer's own Zernio account.
references/posting.md has the why and what the buyer hears. Standard library only.

Usage:
  PY post.py check                          is a key saved, which accounts are connected and can post. STATUS lines
  PY post.py key [--clipboard]              saves the buyer's Zernio key: piped in on stdin, typed at the hidden prompt,
                                            or (--clipboard) taken from what the buyer just copied. Never an argument
  PY post.py connect <platform> [--wait] [--no-open]
                                            opens the page where the buyer connects Instagram / TikTok / YouTube /
                                            Facebook ... to their Zernio account. --wait: until it shows up (10 min)
  PY post.py use <platform> <@handle|account id>
                                            which account to post to when several of one platform are connected
  PY post.py notes "<how they write captions>"
                                            the buyer's caption style, saved for every later post (check prints it)
  PY post.py new <plan.json> <video, picture or folder> ... [--platforms instagram,tiktok] [--trial]
                 [--every 5m] [--start now|"2026-10-21 18:00"]
                                            writes a posting plan, one post per file, captions left for you to write.
                                            A trial-reels folder skips the trials already posted
  PY post.py plan <plan.json>               checks the plan (files, accounts, captions, lengths, times, Zernio's own
                                            check) and prints what will go where and when. Nothing is sent
  PY post.py run <plan.json> --yes [--draft]
                                            uploads and posts or schedules every post not sent yet. Only after the buyer
                                            said yes to the plan. --draft: saved in Zernio as drafts, nothing goes out
  PY post.py status <plan.json> [--wait]    what happened to each post: live links, scheduled, or what failed and the fix
  PY post.py retry <plan.json> [--item N]   sends the failed platforms of a post again
  PY post.py cancel <plan.json> --yes [--item N]
                                            cancels posts that are still scheduled (one that is live stays live)

The plan (JSON, paths relative to the plan file):
  {"defaults": {"platforms": ["instagram", "tiktok"], "trial": true, "graduation": "manual"},
   "posts": [
     {"file": "trial-reels/trial-01-hook-take-2.mp4", "caption": "...", "when": "now"},
     {"file": "trial-reels/trial-02-captions-karaoke.mp4", "caption": "...", "when": "+5m"},
     {"file": "renders/reel-v3.mp4", "caption": "...", "when": "2026-10-21 18:00", "trial": false,
      "platforms": ["instagram", "tiktok", "youtube"], "title": "YouTube title",
      "captions": {"tiktok": "a different caption for TikTok"}}]}
  file        a video, or "files": [pictures] for a photo post / carousel
  caption     the text under the post (required; "" only on purpose). "captions": {platform: text} per platform
  platforms   instagram, tiktok, youtube, facebook, threads, linkedin, twitter, bluesky, pinterest ...
  trial       true: Instagram trial reel (shown to non-followers first). Other platforms post it normally
  graduation  manual (default: the buyer shares the winner to followers in the Instagram app) or auto (Instagram
              shares it on its own when it does well)
  when        now | +5m / +2h / +1d (after the post before it; the first one: after now) | "2026-10-21 18:00" (the
              buyer's own time on this computer)
  title       YouTube title (default: the caption's first line, 100 characters at most)
  cover_ms    the frame shown as the cover, in milliseconds from the start (default 0 = the first frame)
  instagram / tiktok / youtube / facebook   {extra Zernio fields for that platform}, merged in last
  account     {"instagram": "@handle"} when several accounts of a platform are connected

Results go to <plan>.results.json beside the plan: run again and only what has not gone out yet is sent; a post is
never sent twice. The key lives in <Studio state>/posting/zernio.env (this computer only, permissions 600), or comes
from ZERNIO_API_KEY in the environment. No key is ever printed, logged or put on a command line.
"""
import datetime as dt
import json
import mimetypes
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

API = 'https://zernio.com/api/v1'
ENV_VARS = ('ZERNIO_API_KEY', 'LATE_API_KEY')
BRAND = 'Creator Studio'
NAMES = {'instagram': 'Instagram', 'tiktok': 'TikTok', 'youtube': 'YouTube', 'facebook': 'Facebook',
         'threads': 'Threads', 'linkedin': 'LinkedIn', 'twitter': 'X', 'bluesky': 'Bluesky', 'pinterest': 'Pinterest',
         'reddit': 'Reddit', 'googlebusiness': 'Google Business'}
ALIASES = {'ig': 'instagram', 'insta': 'instagram', 'tt': 'tiktok', 'yt': 'youtube', 'shorts': 'youtube',
           'youtube shorts': 'youtube', 'fb': 'facebook', 'x': 'twitter', 'gbp': 'googlebusiness'}
CAPTION_MAX = {'instagram': 2200, 'tiktok': 2200, 'youtube': 5000, 'facebook': 63206, 'threads': 500,
               'linkedin': 3000, 'twitter': 280, 'bluesky': 300, 'pinterest': 500}
VIDEO_EXT = ('.mp4', '.mov', '.m4v', '.webm')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp')
WRITE_ME = 'WRITE ME'
FIX = {   # Zernio's errorCategory -> what to do, in plain words
    'auth_expired': 'the connection to this account expired: reconnect it (post.py connect <platform>), then retry',
    'user_content': 'the platform refused the video or text as it is (format, length, size): fix it, then retry',
    'user_abuse': 'the platform says too many posts too fast: wait a few hours, then retry',
    'platform_rate_limit': 'the platform is busy: Zernio retries this by itself',
    'quota_exhausted': 'the platform\'s daily posting limit is used up: it goes out after the limit resets',
    'account_issue': 'the account is not set up for this (for Instagram: it must be a Professional account, '
                     'Creator or Business): change it in the app, reconnect, then retry',
    'platform_rejected': 'the platform rejected it under its rules: change the video or caption',
    'platform_error': 'the platform had a problem on its side: retry in a little while',
    'system_error': 'Zernio had a problem: retry in a little while',
}


class Fail(Exception):
    """kind: auth, billing, limit, transient, refused, other. The message is plain words for the buyer."""
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


def say(line):
    print(line, flush=True)


# ------------------------------------------------------------------ the key and the settings
def home():
    d = os.path.join(skillenv.state_dir(), 'posting')
    os.makedirs(d, exist_ok=True)
    return d


def key_file():
    return os.path.join(home(), 'zernio.env')


def settings_file():
    return os.path.join(home(), 'settings.json')


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def find_key():
    """-> (key, where) or (None, None). The saved key first, then the environment."""
    try:
        with open(key_file(), encoding='utf-8') as f:
            for line in f:
                m = re.match(r'\s*ZERNIO_API_KEY\s*=\s*(.*?)\s*$', line)
                if m and m.group(1):
                    return m.group(1).strip('\'"'), 'saved key'
    except OSError:
        pass
    for var in ENV_VARS:
        if os.environ.get(var, '').strip():
            return os.environ[var].strip(), f'key from {var}'
    return None, None


def scrub(text, key=None):
    """Text from a server, safe to show: no key, nothing key-shaped."""
    text = str(text or '')
    if key:
        text = text.replace(key, '[key]')
    text = re.sub(r'sk_[0-9A-Za-z]{16,}', '[key]', text)
    return re.sub(r'\s+', ' ', text).strip()[:400]


def read_secret(clipboard):
    if clipboard:
        cmd = (['pbpaste'] if sys.platform == 'darwin' else
               ['powershell', '-NoProfile', '-Command', 'Get-Clipboard'] if os.name == 'nt' else
               ['sh', '-c', 'wl-paste 2>/dev/null || xclip -o -selection clipboard 2>/dev/null || xsel -b'])
        try:
            return subprocess.run(cmd, timeout=15, **skillenv.TEXT).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            raise SystemExit('STATUS key FAILED: could not read the clipboard on this computer')
    if sys.stdin is not None and sys.stdin.isatty():
        import getpass
        return getpass.getpass('Paste your Zernio API key (it stays hidden) and press Enter: ').strip()
    return (sys.stdin.read() if sys.stdin else '').strip()


# ------------------------------------------------------------------ talking to Zernio
def ssl_context():
    ctx = ssl.create_default_context()
    try:   # a python.org Python on a Mac ships without certificates: the system ones work
        if sys.platform == 'darwin' and os.path.isfile('/etc/ssl/cert.pem'):
            ctx.load_verify_locations('/etc/ssl/cert.pem')
    except (OSError, ssl.SSLError):
        pass
    return ctx


def http(method, url, headers=None, data=None, timeout=120):
    """-> (status, bytes). Network trouble raises Fail('transient')."""
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=dict(headers or {}, **{'User-Agent': 'claude-creator-studio-posting'}))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, 'reason', e)
        if 'timed out' in str(reason).lower() or isinstance(e, TimeoutError):
            raise Fail('transient', 'Zernio took too long to answer')
        raise Fail('transient', f'could not reach Zernio ({scrub(reason)}). Is the internet on?')


class Zernio:
    def __init__(self, key):
        self.key = key

    def call(self, method, path, body=None, timeout=120, headers=None, ok=(200, 201, 207)):
        """-> (status, json). 401 / 402 / 429 / 5xx become Fail with plain words; other codes are returned."""
        h = {'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'}
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(4):
            status, raw = http(method, API + path, h, data, timeout)
            try:
                out = json.loads(raw or b'{}')
            except ValueError:
                out = {'error': scrub(raw[:300])}
            if status == 429 or status >= 500:
                if attempt < 3:
                    time.sleep(min(60, 5 * 2 ** attempt))
                    continue
                raise Fail('transient', f'Zernio is busy or down right now (HTTP {status}). Try again in a few minutes')
            if status == 401:
                raise Fail('auth', 'Zernio does not accept this key (it was deleted or mistyped). '
                                   'Make a new one at zernio.com/dashboard/api-keys and save it again')
            if status == 402:
                raise Fail('billing', 'Zernio wants a payment method for this: the first 2 connected accounts are '
                                      'free, every one after that is a few dollars a month. Add a card at '
                                      'zernio.com/dashboard/billing, then try again. ' + self.why(out))
            return status, out
        raise Fail('transient', 'Zernio did not answer')

    def why(self, out):
        if not isinstance(out, dict):
            return ''
        return scrub(out.get('message') or out.get('error') or out.get('details') or '', self.key)


def zernio_or_exit():
    key, _ = find_key()
    if not key:
        raise SystemExit('STATUS posting NO KEY: no Zernio key saved yet (references/posting.md, "Setup")')
    return Zernio(key)


def accounts(z):
    st, out = z.call('GET', '/accounts')
    if st != 200:
        raise Fail('other', f'could not list the connected accounts (HTTP {st}). {z.why(out)}')
    return [a for a in out.get('accounts', []) if a.get('enabled', True)]


def health(z):
    try:
        st, out = z.call('GET', '/accounts/health')
    except Fail:
        return {}
    return {a.get('accountId'): a for a in out.get('accounts', [])} if st == 200 else {}


def default_profile(z):
    st, out = z.call('GET', '/profiles')
    profs = out.get('profiles', []) if st == 200 else []
    if not profs:
        st, out = z.call('POST', '/profiles', {'name': 'My accounts', 'description': f'Posting from {BRAND}'})
        if st not in (200, 201):
            raise Fail('other', f'could not make a Zernio profile (HTTP {st}). {z.why(out)}')
        return out['profile']['_id']
    return next((p for p in profs if p.get('isDefault')), profs[0])['_id']


def handle(a):
    u = a.get('username') or a.get('displayName') or a.get('_id')
    return u if u.startswith('@') or ' ' in u else '@' + u


def platform_name(p):
    p = (p or '').strip().lower()
    return ALIASES.get(p, p)


def pick_account(accs, platform, wanted=None):
    """-> account dict. wanted: '@handle' or an id. Several and nothing chosen: Fail listing them."""
    mine = [a for a in accs if a.get('platform') == platform]
    if not mine:
        raise Fail('other', f'no {NAMES.get(platform, platform)} account is connected to Zernio yet '
                            f'(post.py connect {platform})')
    wanted = wanted or (read_json(settings_file(), {}) or {}).get('accounts', {}).get(platform)
    if wanted:
        w = wanted.lstrip('@').lower()
        hit = [a for a in mine if w in (a.get('_id', '').lower(), (a.get('username') or '').lower())]
        if hit:
            return hit[0]
        raise Fail('other', f'{wanted} is not a connected {NAMES.get(platform, platform)} account. Connected: '
                            + ', '.join(handle(a) for a in mine))
    if len(mine) > 1:
        raise Fail('other', f'{len(mine)} {NAMES.get(platform, platform)} accounts are connected: '
                            + ', '.join(handle(a) for a in mine) + f'. Ask which one, then post.py use {platform} @handle')
    return mine[0]


# ------------------------------------------------------------------ commands: setup
def cmd_check(args):
    key, where = find_key()
    if not key:
        say('STATUS posting NO KEY')
        return 1
    z = Zernio(key)
    try:
        accs = accounts(z)
    except Fail as e:
        say(f'STATUS posting KEY BAD: {e}' if e.kind == 'auth' else f'STATUS posting FAILED: {e}')
        return 1
    hl = health(z)
    ready = []
    for a in accs:
        h = hl.get(a['_id'], {})
        ok = h.get('canPost', a.get('isActive', True)) and not h.get('needsReconnect') and not a.get('needsReconnection')
        note = '' if ok else '  NEEDS RECONNECT (post.py connect ' + a['platform'] + ')'
        issues = '; '.join(scrub(i.get('message') if isinstance(i, dict) else i) for i in (h.get('issues') or []))
        say(f'ACCOUNT {a["platform"]:10} {handle(a):24} {"can post" if ok else "cannot post"}{note}'
            + (f'  ({issues})' if issues else ''))
        if ok:
            ready.append(a['platform'])
    if not accs:
        say(f'STATUS posting NO ACCOUNTS ({where} works; nothing is connected yet)')
        return 1
    notes = (read_json(settings_file(), {}) or {}).get('captionNotes')
    say(f'CAPTION NOTES {notes}' if notes else 'CAPTION NOTES none yet (ask how they like their captions, then post.py notes)')
    say(f'STATUS posting READY {",".join(sorted(set(ready)))}' if ready else 'STATUS posting NO ACCOUNT CAN POST')
    return 0 if ready else 1


def cmd_key(args):
    key = read_secret(args.clipboard)
    key = re.sub(r'^(export\s+)?[A-Z_]+=', '', key).strip().strip('\'"')   # a whole "ZERNIO_API_KEY=..." line is fine
    if not re.fullmatch(r'sk_[0-9A-Za-z]{20,}', key or ''):
        raise SystemExit('STATUS key FAILED: that does not look like a Zernio key (they start with sk_). '
                         'Nothing copied, or more than the key?')
    try:
        st, out = Zernio(key).call('GET', '/profiles')
    except Fail as e:
        raise SystemExit(f'STATUS key FAILED: {e}. Nothing saved')
    if st != 200:
        raise SystemExit(f'STATUS key FAILED: Zernio answered HTTP {st}. Nothing saved')
    path = key_file()
    fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Creator Studio: Zernio key for posting. Private, this computer only. Never share this file.\n')
        f.write(f'ZERNIO_API_KEY={key}\n')
    os.replace(path + '.tmp', path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    say('STATUS key SAVED (checked: it works)')
    return 0


def cmd_connect(args):
    z = zernio_or_exit()
    platform = platform_name(args.platform)
    try:
        before = {a['_id'] for a in accounts(z) if a.get('platform') == platform}
        q = {'profileId': default_profile(z), 'welcome': 'true', 'brandName': BRAND}
        st, out = z.call('GET', f'/connect/{urllib.parse.quote(platform)}?' + urllib.parse.urlencode(q))
    except Fail as e:
        raise SystemExit(f'STATUS connect FAILED: {e}')
    if st != 200 or not out.get('authUrl'):
        raise SystemExit(f'STATUS connect FAILED {platform}: HTTP {st}. {z.why(out)}')
    url = out['authUrl']
    opened = False if args.no_open else webbrowser.open(url)
    say(f'CONNECT {platform}: {"opened in the browser" if opened else "open this link"}: {url}')
    if not args.wait:
        return 0
    t0 = time.time()
    while time.time() - t0 < 600:
        time.sleep(5)
        try:
            new = [a for a in accounts(z) if a.get('platform') == platform and a['_id'] not in before]
        except Fail:
            continue
        if new:
            say(f'STATUS connect DONE {platform} {handle(new[0])}')
            return 0
    say(f'STATUS connect WAITING {platform}: nothing new after 10 minutes. Run post.py check once they say it is done')
    return 1


def cmd_use(args):
    z = zernio_or_exit()
    platform = platform_name(args.platform)
    try:
        a = pick_account(accounts(z), platform, args.account)
    except Fail as e:
        raise SystemExit(f'STATUS use FAILED: {e}')
    conf = read_json(settings_file(), {}) or {}
    conf.setdefault('accounts', {})[platform] = a['_id']
    write_json(settings_file(), conf)
    say(f'STATUS use SAVED {platform} {handle(a)}')
    return 0


def cmd_notes(args):
    conf = read_json(settings_file(), {}) or {}
    conf['captionNotes'] = ' '.join(args.text).strip()
    write_json(settings_file(), conf)
    say('STATUS notes SAVED')
    return 0


# ------------------------------------------------------------------ the plan
def parse_when(text, prev, now):
    """-> (aware datetime, 'now'|'at'). +5m / +2h / +1d count from the post before (the first one: from now)."""
    t = str(text or 'now').strip().lower()
    if t in ('now', 'right now', 'asap', ''):
        return now, 'now'
    m = re.fullmatch(r'(?:\+|in\s+)?\s*(\d+(?:\.\d+)?)\s*(m|min|mins|minutes?|h|hrs?|hours?|d|days?)(?:\s+later)?', t)
    if m:
        n, unit = float(m.group(1)), m.group(2)[0]
        delta = dt.timedelta(minutes=n) if unit == 'm' else dt.timedelta(hours=n) if unit == 'h' else dt.timedelta(days=n)
        return (prev or now) + delta, 'at'
    try:
        when = dt.datetime.fromisoformat(str(text).strip().replace('Z', '+00:00').replace(' ', 'T', 1))
    except ValueError:
        raise Fail('other', f'"{text}" is not a time I can read: now, +5m, +2h, +1d or "2026-10-21 18:00"')
    return (when.astimezone() if when.tzinfo is None else when), 'at'


def local(t):
    t = t.astimezone()
    return t.strftime('%a %b %d, %I:%M %p').replace(' 0', ' ')


def probe(path):
    """-> {'duration', 'width', 'height'} or {} when ffprobe is missing or cannot read it."""
    try:
        out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                              'stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration',
                              '-of', 'json', path], timeout=60, **skillenv.TEXT)
        d = json.loads(out.stdout or '{}')
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    s = (d.get('streams') or [{}])[0]
    w, h = s.get('width'), s.get('height')
    rot = str((s.get('tags') or {}).get('rotate') or next((x.get('rotation') for x in s.get('side_data_list') or []
                                                           if 'rotation' in x), 0) or 0)
    if rot.lstrip('-') in ('90', '270') and w and h:
        w, h = h, w
    try:
        dur = float((d.get('format') or {}).get('duration') or 0)
    except ValueError:
        dur = 0
    return {'duration': dur, 'width': w, 'height': h} if w and h else {}


def load_plan(path):
    plan = read_json(path)
    if not isinstance(plan, dict) or not isinstance(plan.get('posts'), list) or not plan['posts']:
        raise SystemExit(f'STATUS plan FAILED: {path} is not a posting plan ({{"posts": [...]}}, see post.py --help)')
    return plan


def results_path(plan_path):
    return re.sub(r'\.json$', '', plan_path) + '.results.json'


def item_files(item, base):
    files = item.get('files') or ([item['file']] if item.get('file') else [])
    return [f if os.path.isabs(f) else os.path.normpath(os.path.join(base, skillenv.path_arg(f))) for f in files]


def resolve(plan_path, plan, now=None, results=None):
    """Every post with its files, platforms, settings and time, plus problems (stop) and notes (say once)."""
    base = os.path.dirname(os.path.abspath(plan_path))
    d = plan.get('defaults') or {}
    now = now or dt.datetime.now().astimezone()
    done = (results or {}).get('posts', {})
    rows, prev = [], None
    for i, item in enumerate(plan['posts'], 1):
        r = {'n': i, 'item': item, 'problems': [], 'notes': []}
        rows.append(r)
        r['files'] = item_files(item, base)
        r['platforms'] = [platform_name(p) for p in (item.get('platforms') or d.get('platforms') or [])]
        r['trial'] = bool(item.get('trial', d.get('trial', False)))
        r['graduation'] = str(item.get('graduation', d.get('graduation', 'manual'))).lower()
        r['caption'] = item.get('caption', d.get('caption'))
        r['captions'] = {platform_name(k): v for k, v in (item.get('captions') or {}).items()}
        rec = done.get(str(i), {})
        r['sent'] = rec.get('postId') if not rec.get('draft') else None   # a draft still has to go out
        r['draft_id'] = rec.get('postId') if rec.get('draft') else None
        try:
            if r['sent'] and done[str(i)].get('scheduledFor'):
                r['when'], r['mode'] = dt.datetime.fromisoformat(done[str(i)]['scheduledFor']).astimezone(), 'at'
            else:
                r['when'], r['mode'] = parse_when(item.get('when', d.get('when', 'now')), prev, now)
        except Fail as e:
            r['when'], r['mode'] = now, 'now'
            r['problems'].append(str(e))
        prev = r['when']
        if not r['files']:
            r['problems'].append('no "file" (or "files") to post')
        for f in r['files']:
            if not os.path.isfile(f):
                r['problems'].append(f'file not found: {f}')
        kinds = {('video' if f.lower().endswith(VIDEO_EXT) else 'image' if f.lower().endswith(IMAGE_EXT) else '?')
                 for f in r['files']}
        if '?' in kinds:
            r['problems'].append('only videos (.mp4 .mov) and pictures (.jpg .png .webp) can be posted')
        r['kind'] = 'video' if kinds == {'video'} else 'image' if kinds == {'image'} else 'mixed'
        if r['kind'] == 'video' and len(r['files']) > 1:
            r['problems'].append('one video per post (a carousel is pictures)')
        if not r['platforms']:
            r['problems'].append('no platforms: say where it goes ("platforms": ["instagram", "tiktok"])')
        for p in r['platforms']:
            text = r['captions'].get(p, r['caption'])
            if text is None or WRITE_ME in str(text):
                r['problems'].append(f'write the {NAMES.get(p, p)} caption')
            elif len(str(text)) > CAPTION_MAX.get(p, 10 ** 6):
                r['problems'].append(f'{NAMES.get(p, p)} caption is {len(text)} characters, the limit is {CAPTION_MAX[p]}')
            elif p == 'instagram' and len(re.findall(r'#\w', str(text))) > 30:
                r['problems'].append('Instagram allows 30 hashtags at most')
        if r['graduation'] not in ('manual', 'auto'):
            r['problems'].append('graduation is manual or auto')
        if r['trial'] and 'instagram' not in r['platforms']:
            r['notes'].append('trial is an Instagram thing: no Instagram in this post, so it posts normally')
        if r['trial'] and r['kind'] != 'video':
            r['problems'].append('a trial reel is a video')
        if r['mode'] == 'at' and not r['sent'] and r['when'] < now - dt.timedelta(minutes=1):
            r['problems'].append(f'{local(r["when"])} is in the past')
        if r['kind'] == 'video' and r['files'] and os.path.isfile(r['files'][0]):
            r['media'] = probe(r['files'][0])
            m = r['media']
            if m:
                vertical, dur = m['height'] > m['width'], m['duration']
                if 'youtube' in r['platforms']:
                    if not vertical or dur > 180:
                        r['notes'].append('YouTube: not a Short (a Short is vertical and 3 minutes or less), '
                                          'it goes up as a normal video')
                    title = str(item.get('title') or first_line(r['captions'].get('youtube', r['caption'])))
                    if len(title) > 100:
                        r['problems'].append(f'YouTube title is {len(title)} characters, the limit is 100')
                if 'facebook' in r['platforms'] and not (vertical and 3 <= dur <= 90):
                    r['notes'].append('Facebook: a Reel is vertical and 3 to 90 seconds, this posts as a normal video')
                if 'instagram' in r['platforms'] and not 3 <= dur <= 900:
                    r['problems'].append(f'Instagram reels are 3 seconds to 15 minutes, this one is {dur:.0f} s')
                if not vertical and r['platforms'] != ['youtube']:
                    r['notes'].append(f'the video is {m["width"]}x{m["height"]}, not vertical: it will look small '
                                      'on Reels and TikTok')
    order = sorted(rows, key=lambda r: r['when'])
    if [r['n'] for r in order] != [r['n'] for r in rows]:
        rows[0]['notes'].append('the times are not in the order of the list: they go out by time, not by list order')
    return rows


def first_line(text):
    line = next((l.strip() for l in str(text or '').splitlines() if l.strip()), '')
    line = re.sub(r'\s*#\w+', '', line).strip()
    return line[:100] or 'New video'


def build_body(r, accs, tiktok_info):
    """-> the POST /v1/posts body for one row (no media urls yet: 'mediaItems' filled by the caller)."""
    item = r['item']
    want = item.get('account') or {}
    cover = int(item.get('cover_ms', 0) or 0)
    plats = []
    for p in r['platforms']:
        a = pick_account(accs, p, want.get(p))
        e = {'platform': p, 'accountId': a['_id'], 'platformSpecificData': {}}
        if p in r['captions']:
            e['customContent'] = r['captions'][p]
        psd = e['platformSpecificData']
        if p == 'instagram' and r['kind'] == 'video':
            psd['thumbOffset'] = cover
            if r['trial']:
                psd['trialParams'] = {'graduationStrategy': 'MANUAL' if r['graduation'] == 'manual' else 'SS_PERFORMANCE'}
        elif p == 'youtube':
            psd.update({'title': str(item.get('title') or first_line(r['captions'].get('youtube', r['caption'])))[:100],
                        'visibility': 'public', 'madeForKids': False, 'categoryId': '22'})
        elif p == 'facebook' and r['kind'] == 'video':
            m = r.get('media') or {}
            if m and m['height'] > m['width'] and 3 <= m['duration'] <= 90:
                psd['contentType'] = 'reel'
        elif p == 'tiktok':
            info = tiktok_info.get(a['_id']) or {}
            levels = [x.get('value') for x in info.get('privacyLevels') or []]
            inter = (info.get('postingLimits') or {}).get('interactionSettings') or {}
            tk = {'privacy_level': 'PUBLIC_TO_EVERYONE' if not levels or 'PUBLIC_TO_EVERYONE' in levels else levels[0],
                  'allow_comment': inter.get('allow_comment', {}).get('enabled', True),
                  'content_preview_confirmed': True, 'express_consent_given': True}
            if r['kind'] == 'video':
                tk.update({'allow_duet': inter.get('allow_duet', {}).get('enabled', True),
                           'allow_stitch': inter.get('allow_stitch', {}).get('enabled', True),
                           'video_cover_timestamp_ms': max(cover, 100)})
            tk.update(item.get('tiktok') or {})
            psd['tiktokSettings'] = tk
        if p != 'tiktok':
            psd.update(item.get(p) or {})
        if not psd:
            e.pop('platformSpecificData')
        plats.append(e)
    body = {'content': r['caption'] if r['caption'] is not None else '', 'platforms': plats}
    return body


def tiktok_infos(z, accs, rows):
    ids = set()
    for r in rows:
        if 'tiktok' in r['platforms']:
            try:
                ids.add(pick_account(accs, 'tiktok', (r['item'].get('account') or {}).get('tiktok'))['_id'])
            except Fail:
                pass
    out = {}
    for i in ids:
        try:
            st, info = z.call('GET', f'/accounts/{i}/tiktok/creator-info?mediaType=video')
            if st == 200:
                out[i] = info
        except Fail:
            pass
    return out


def check_plan(z, plan_path, plan, results=None, quiet=False):
    """-> (rows, accounts, tiktok info, ok). Prints the plan the buyer approves."""
    rows = resolve(plan_path, plan, results=results)
    try:
        accs = accounts(z)
    except Fail as e:
        raise SystemExit(f'STATUS plan FAILED: {e}')
    hl = health(z)
    tk = tiktok_infos(z, accs, rows)
    for r in rows:
        for p in r['platforms']:
            try:
                a = pick_account(accs, p, (r['item'].get('account') or {}).get(p))
            except Fail as e:
                r['problems'].append(str(e))
                continue
            h = hl.get(a['_id'], {})
            if h.get('needsReconnect') or a.get('needsReconnection') or h.get('canPost') is False:
                r['problems'].append(f'{NAMES.get(p, p)} {handle(a)} needs reconnecting (post.py connect {p})')
            if p == 'tiktok' and (tk.get(a['_id']) or {}).get('creator', {}).get('canPostMore') is False:
                r['problems'].append('TikTok says this account cannot post more right now (daily limit): '
                                     'try later or post fewer')
        if r['problems'] or r['sent']:
            continue
        body = build_body(r, accs, tk)
        body['mediaItems'] = [{'type': r['kind'] if r['kind'] != 'mixed' else 'video',
                               'url': 'https://media.zernio.com/temp/check' + os.path.splitext(f)[1].lower()}
                              for f in r['files']]
        try:
            st, out = z.call('POST', '/tools/validate/post', body)
        except Fail:
            continue   # the server check is a bonus; the post itself is checked again when it is sent
        if st == 200 and out.get('valid') is False:
            r['problems'] += [f'{NAMES.get(x.get("platform"), x.get("platform"))}: {scrub(x.get("error"))}'
                              for x in out.get('errors') or []]
        r['notes'] += [f'{NAMES.get(x.get("platform"), x.get("platform"))}: {scrub(x.get("warning"))}'
                       for x in out.get('warnings') or []]
    if not quiet:
        print_plan(rows, accs)
    ok = not any(r['problems'] for r in rows)
    return rows, accs, tk, ok


def print_plan(rows, accs):
    for r in rows:
        name = ', '.join(os.path.basename(f) for f in r['files']) or '(no file)'
        if r['sent']:
            say(f'POST {r["n"]}  {name}  ALREADY SENT (post.py status)')
            continue
        where = []
        for p in r['platforms']:
            try:
                h = handle(pick_account(accs, p, (r['item'].get('account') or {}).get(p)))
            except Fail:
                h = '?'
            extra = ''
            if p == 'instagram' and r['trial'] and r['kind'] == 'video':
                extra = ' trial reel, ' + ('you share the winner yourself' if r['graduation'] == 'manual'
                                           else 'Instagram shares it if it does well')
            elif p == 'youtube':
                extra = ' "' + str(r['item'].get('title') or first_line(r['captions'].get('youtube', r['caption'])))[:100] + '"'
            where.append(f'{NAMES.get(p, p)} {h}{extra}')
        when = 'right away' if r['mode'] == 'now' else local(r['when'])
        m = r.get('media') or {}
        size = f'{m["duration"]:.0f} s, {m["width"]}x{m["height"]}' if m else ''
        say(f'POST {r["n"]}  {name}{"  (" + size + ")" if size else ""}  {when}')
        say(f'   to: {"; ".join(where)}')
        cap = r['caption'] if r['caption'] is not None else ''
        say(f'   caption: {first_line(cap) if cap else "(none)"}' + ('  ...' if len(str(cap).splitlines()) > 1 else ''))
        for p, t in r['captions'].items():
            say(f'   {NAMES.get(p, p)} caption: {first_line(t)}')
        for n in r['notes']:
            say(f'   note: {n}')
        for pr in r['problems']:
            say(f'   PROBLEM: {pr}')
    if any('tiktok' in r['platforms'] for r in rows if not r['sent']):
        say('NOTE TikTok: posting means the buyer agrees to TikTok\'s Music Usage Confirmation and has seen the video '
            '(say it with the plan)')


def cmd_plan(args):
    z = zernio_or_exit()
    plan_path = os.path.abspath(skillenv.path_arg(args.plan))
    plan = load_plan(plan_path)
    rows, _, _, ok = check_plan(z, plan_path, plan, read_json(results_path(plan_path), {}))
    todo = [r for r in rows if not r['sent']]
    if ok:
        say(f'STATUS plan OK {len(todo)} to send' + (f', {len(rows) - len(todo)} already sent' if len(todo) < len(rows) else ''))
        return 0
    say(f'STATUS plan PROBLEMS in {sum(1 for r in rows if r["problems"])} post(s): fix them, then plan again')
    return 1


def cmd_new(args):
    plan_path = os.path.abspath(skillenv.path_arg(args.plan))
    if os.path.exists(plan_path) and not args.force:
        raise SystemExit(f'STATUS new FAILED: {plan_path} is already there (--force to replace it)')
    files = []
    for src in args.files:
        src = os.path.abspath(skillenv.path_arg(src))
        if os.path.isdir(src):
            posted = set()
            proj = os.path.dirname(src)
            if os.path.basename(src) == 'trial-reels':
                for v in (read_json(os.path.join(proj, 'variations.json'), {}) or {}).get('variations') or []:
                    if v.get('posted') and v.get('name'):
                        posted.add(v['name'] + '.mp4')
            for f in sorted(os.listdir(src)):
                if f.lower().endswith(VIDEO_EXT + IMAGE_EXT) and not f.startswith('.'):
                    if f in posted:
                        say(f'SKIPPED {f}: already posted')
                        continue
                    files.append(os.path.join(src, f))
        elif os.path.isfile(src):
            files.append(src)
        else:
            raise SystemExit(f'STATUS new FAILED: not found: {src}')
    if not files:
        raise SystemExit('STATUS new FAILED: no videos or pictures to post')
    base = os.path.dirname(plan_path)
    def rel(f):   # inside the plan's folder: a short path; anywhere else: the full one
        inside = os.path.splitdrive(f)[0] == os.path.splitdrive(base)[0] and not os.path.relpath(f, base).startswith('..')
        return os.path.relpath(f, base).replace('\\', '/') if inside else f
    posts = []
    pics = all(f.lower().endswith(IMAGE_EXT) for f in files)
    if pics and args.carousel:
        posts.append({'files': [rel(f) for f in files], 'caption': WRITE_ME, 'when': args.start})
    else:
        for i, f in enumerate(files):
            posts.append({'file': rel(f), 'caption': WRITE_ME, 'when': args.start if i == 0 else (args.every or args.start)})
    plan = {'defaults': {'platforms': [platform_name(p) for p in args.platforms.split(',') if p.strip()],
                         'trial': bool(args.trial), 'graduation': 'manual'}, 'posts': posts}
    os.makedirs(base, exist_ok=True)
    write_json(plan_path, plan)
    say(f'STATUS new WRITTEN {plan_path}: {len(posts)} post(s). Write every caption ("{WRITE_ME}"), then post.py plan')
    return 0


# ------------------------------------------------------------------ sending
def content_type(path):
    ext = os.path.splitext(path)[1].lower()
    return {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm',
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(
        ext, mimetypes.guess_type(path)[0] or 'application/octet-stream')


def upload(z, path, cache):
    """-> public url. The same unchanged file uploaded less than 6 days ago is not uploaded again."""
    st_ = os.stat(path)
    sig = f'{os.path.abspath(path)}|{st_.st_size}|{int(st_.st_mtime)}'
    hit = cache.get(sig)
    if hit and time.time() - hit['at'] < 6 * 86400:
        return hit['url']
    name = re.sub(r'[^A-Za-z0-9._-]', '-', os.path.basename(path))
    st, out = z.call('POST', '/media/presign', {'filename': name, 'contentType': content_type(path), 'size': st_.st_size})
    if st != 200 or not out.get('uploadUrl'):
        raise Fail('other', f'Zernio would not take the upload of {os.path.basename(path)} (HTTP {st}). {z.why(out)}')
    for attempt in range(3):
        with open(path, 'rb') as fh:
            try:
                code, raw = http('PUT', out['uploadUrl'], {'Content-Type': content_type(path),
                                                           'Content-Length': str(st_.st_size)}, fh, timeout=1800)
            except Fail:
                code, raw = 0, b''
        if code in (200, 201, 204):
            cache[sig] = {'url': out['publicUrl'], 'at': time.time()}
            return out['publicUrl']
        time.sleep(5 * (attempt + 1))
    raise Fail('transient', f'the upload of {os.path.basename(path)} did not go through (HTTP {code}). Try again')


def summarize(post):
    """-> [(platform, status, url, error, category)]"""
    return [(x.get('platform'), x.get('status'), x.get('platformPostUrl') or x.get('url'),
             scrub(x.get('errorMessage') or x.get('error')), x.get('errorCategory'))
            for x in post.get('platforms') or []]


def mark_posted(file):
    """A trial from the Studio's trial-reels folder that went out is marked posted, so it is never made again."""
    folder, name = os.path.split(os.path.abspath(file))
    if os.path.basename(folder) != 'trial-reels' or not re.match(r'trial-\d+', name):
        return
    proj = os.path.dirname(folder)
    if not os.path.isfile(os.path.join(proj, 'variations.json')):
        return
    out = subprocess.run([sys.executable, os.path.join(HERE, 'variations.py'), 'posted', proj, name], timeout=60,
                         **skillenv.TEXT)
    line = (out.stdout or out.stderr or '').strip().splitlines()
    if line:
        say('   ' + line[-1])


def cmd_run(args):
    z = zernio_or_exit()
    plan_path = os.path.abspath(skillenv.path_arg(args.plan))
    plan = load_plan(plan_path)
    rpath = results_path(plan_path)
    results = read_json(rpath, {}) or {}
    results.setdefault('posts', {})
    cache = results.setdefault('uploads', {})
    rows, accs, tk, ok = check_plan(z, plan_path, plan, results, quiet=args.yes)
    if not ok:
        if args.yes:
            print_plan(rows, accs)
        raise SystemExit('STATUS run STOPPED: the plan has problems (above). Nothing was sent')
    if not args.yes:
        raise SystemExit('STATUS run NOT SENT: show the buyer this plan and get a clear yes, then run it with --yes')
    t0 = dt.datetime.now().astimezone()
    sent = failed = 0
    for r in rows:
        if r['sent']:
            continue
        rec = results['posts'].setdefault(str(r['n']), {})
        if r.get('draft_id'):
            if args.draft:
                continue   # already a draft
            st, out = z.call('DELETE', f'/posts/{r["draft_id"]}')   # our own draft makes way for the real post
            if st not in (200, 204, 404):
                say(f'FAILED {r["n"]}: could not replace its Zernio draft (HTTP {st}). {z.why(out)}')
                failed += 1
                continue
            rec.clear()
        rec['idem'] = rec.get('idem') or str(uuid.uuid4())
        write_json(rpath, results)
        name = ', '.join(os.path.basename(f) for f in r['files'])
        try:
            urls = [upload(z, f, cache) for f in r['files']]
            write_json(rpath, results)
            body = build_body(r, accs, tk)
            body['mediaItems'] = [{'type': r['kind'], 'url': u} for u in urls]
            when = r['when']
            if args.draft:
                body['isDraft'] = True
            elif r['mode'] == 'now' or when <= dt.datetime.now().astimezone() + dt.timedelta(seconds=30):
                body['publishNow'] = True
            else:
                body['scheduledFor'] = when.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                body['timezone'] = 'UTC'
            st, out = z.call('POST', '/posts', body, timeout=900, headers={'Idempotency-Key': rec['idem']})
        except Fail as e:
            failed += 1
            say(f'FAILED {r["n"]} {name}: {e}')
            if e.kind in ('auth', 'billing'):
                break
            continue
        if st == 409:
            failed += 1
            say(f'FAILED {r["n"]} {name}: this exact video and caption already went to that account in the last '
                f'24 hours. Change the caption (or the video) to post it again')
            continue
        if st not in (200, 201, 207):
            failed += 1
            say(f'FAILED {r["n"]} {name}: Zernio said HTTP {st}. {z.why(out)}')
            continue
        post = out.get('post') or {}
        rec.update({'postId': post.get('_id'), 'status': post.get('status'), 'file': name,
                    'scheduledFor': None if body.get('publishNow') or args.draft else when.isoformat(),
                    'draft': bool(args.draft), 'sentAt': t0.isoformat(),
                    'platforms': [list(x) for x in summarize(post)]})
        write_json(rpath, results)
        try:
            with open(os.path.join(home(), 'history.jsonl'), 'a', encoding='utf-8') as f:
                f.write(json.dumps({'at': t0.isoformat(), 'plan': plan_path, 'n': r['n'], 'file': name,
                                    'postId': rec['postId'], 'status': rec['status'],
                                    'platforms': r['platforms'], 'trial': r['trial']}) + '\n')
        except OSError:
            pass
        sent += 1
        for w in out.get('warnings') or []:
            say(f'   note: {scrub(w)}')
        if args.draft:
            say(f'DRAFT {r["n"]} {name}: saved in Zernio, nothing went out')
            continue
        if body.get('publishNow'):
            parts = []
            for p, s, url, err, cat in summarize(post):
                parts.append(f'{NAMES.get(p, p)} {s}' + (f' {url}' if url else '') +
                             (f' ({err}. {FIX.get(cat, "")})' if s == 'failed' else ''))
            say(f'POSTED {r["n"]} {name}: ' + '; '.join(parts))
        else:
            say(f'SCHEDULED {r["n"]} {name}: {local(when)} to ' + ', '.join(NAMES.get(p, p) for p in r['platforms']))
        if 'instagram' in r['platforms'] and r['kind'] == 'video':
            mark_posted(r['files'][0])
    left = sum(1 for r in rows if not r['sent'] and not (args.draft and r.get('draft_id'))) - sent
    say(f'STATUS run {"DONE" if not failed else "INCOMPLETE"}: {sent} sent'
        + (f', {failed} failed (run it again after the fix: what went out is never sent twice)' if failed else '')
        + ('' if left <= failed else f', {left - failed} not tried'))
    return 0 if not failed else 1


def refresh(z, rec):
    st, out = z.call('GET', f'/posts/{rec["postId"]}')
    if st != 200:
        return None
    post = out.get('post') or out
    rec['status'] = post.get('status')
    rec['platforms'] = [list(x) for x in summarize(post)]
    return post


def cmd_status(args):
    z = zernio_or_exit()
    plan_path = os.path.abspath(skillenv.path_arg(args.plan))
    rpath = results_path(plan_path)
    results = read_json(rpath, {}) or {}
    recs = {k: v for k, v in (results.get('posts') or {}).items() if v.get('postId')}
    if not recs:
        raise SystemExit('STATUS status NOTHING SENT yet from this plan')
    t0, gone = time.time(), set()
    while True:   # --wait: until every post that is due has finished (20 minutes at most)
        busy = False
        for n, rec in recs.items():
            if n in gone or refresh(z, rec) is None:
                gone.add(n)
                continue
            due = not rec.get('scheduledFor') or dt.datetime.fromisoformat(rec['scheduledFor']) <= dt.datetime.now().astimezone()
            busy = busy or (due and rec['status'] in ('publishing', 'scheduled', 'pending'))
        write_json(rpath, results)
        if not args.wait or not busy or time.time() - t0 > 1200:
            break
        time.sleep(20)
    for n in sorted(recs, key=int):
        rec = recs[n]
        if n in gone:
            say(f'POST {n} {rec.get("file")}: Zernio does not know it any more (deleted in Zernio?)')
            continue
        head = f'POST {n} {rec.get("file")}: {rec["status"]}'
        if rec.get('scheduledFor') and rec['status'] == 'scheduled':
            head += ' for ' + local(dt.datetime.fromisoformat(rec['scheduledFor']))
        say(head)
        for p, s, url, err, cat in rec['platforms']:
            say(f'   {NAMES.get(p, p)}: {s}' + (f' {url}' if url else '')
                + (f'  {err}. Fix: {FIX.get(cat, "read the error above")}' if s == 'failed' else ''))
    states = [rec['status'] for n, rec in recs.items() if n not in gone]
    bad = sum(1 for s in states if s in ('failed', 'partial'))
    say(f'STATUS status {"PROBLEMS " + str(bad) if bad else "OK"}: ' +
        ', '.join(f'{states.count(s)} {s}' for s in dict.fromkeys(states)))
    return 1 if bad else 0


def selected(results, item):
    recs = {k: v for k, v in (results.get('posts') or {}).items() if v.get('postId')}
    return {k: v for k, v in recs.items() if item is None or k == str(item)}


def cmd_retry(args):
    z = zernio_or_exit()
    rpath = results_path(os.path.abspath(skillenv.path_arg(args.plan)))
    results = read_json(rpath, {}) or {}
    for n, rec in sorted(selected(results, args.item).items(), key=lambda kv: int(kv[0])):
        refresh(z, rec)
        if rec['status'] not in ('failed', 'partial'):
            continue
        st, out = z.call('POST', f'/posts/{rec["postId"]}/retry', timeout=900)
        post = out.get('post') or {}
        rec['status'] = post.get('status', rec['status'])
        if post:
            rec['platforms'] = [list(x) for x in summarize(post)]
        say(f'RETRIED {n} {rec.get("file")}: {rec["status"]}' + ('' if st in (200, 201, 207) else f' (HTTP {st}. {z.why(out)})'))
    write_json(rpath, results)
    say('STATUS retry DONE (post.py status for the links)')
    return 0


def cmd_cancel(args):
    if not args.yes:
        raise SystemExit('STATUS cancel NOT DONE: say which posts will be cancelled, get a yes, then --yes')
    z = zernio_or_exit()
    rpath = results_path(os.path.abspath(skillenv.path_arg(args.plan)))
    results = read_json(rpath, {}) or {}
    for n, rec in sorted(selected(results, args.item).items(), key=lambda kv: int(kv[0])):
        refresh(z, rec)
        if rec['status'] not in ('scheduled', 'draft'):
            say(f'KEPT {n} {rec.get("file")}: it is {rec["status"]}, not waiting (a live post is removed in the app)')
            continue
        st, out = z.call('DELETE', f'/posts/{rec["postId"]}')
        if st in (200, 204):
            say(f'CANCELLED {n} {rec.get("file")}')
            results['posts'].pop(n, None)
        else:
            say(f'FAILED {n}: HTTP {st}. {z.why(out)}')
    write_json(rpath, results)
    say('STATUS cancel DONE')
    return 0


def main():
    import argparse
    skillenv.utf8_stdio()
    ap = argparse.ArgumentParser(prog='post.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    p = sub.add_parser('key')
    p.add_argument('--clipboard', action='store_true')
    p = sub.add_parser('connect')
    p.add_argument('platform')
    p.add_argument('--wait', action='store_true')
    p.add_argument('--no-open', action='store_true')
    p = sub.add_parser('use')
    p.add_argument('platform')
    p.add_argument('account')
    p = sub.add_parser('notes')
    p.add_argument('text', nargs='+')
    p = sub.add_parser('new')
    p.add_argument('plan')
    p.add_argument('files', nargs='+')
    p.add_argument('--platforms', default='instagram')
    p.add_argument('--trial', action='store_true')
    p.add_argument('--every', default=None)
    p.add_argument('--start', default='now')
    p.add_argument('--carousel', action='store_true')
    p.add_argument('--force', action='store_true')
    for name in ('plan', 'run', 'status', 'retry', 'cancel'):
        p = sub.add_parser(name)
        p.add_argument('plan')
        if name in ('run', 'cancel'):
            p.add_argument('--yes', action='store_true')
        if name == 'run':
            p.add_argument('--draft', action='store_true')
        if name == 'status':
            p.add_argument('--wait', action='store_true')
        if name in ('retry', 'cancel'):
            p.add_argument('--item', type=int)
    args = ap.parse_args()
    cmds = {'check': cmd_check, 'key': cmd_key, 'connect': cmd_connect, 'use': cmd_use, 'notes': cmd_notes, 'new': cmd_new,
            'plan': cmd_plan, 'run': cmd_run, 'status': cmd_status, 'retry': cmd_retry, 'cancel': cmd_cancel}
    try:
        return cmds[args.cmd](args)
    except Fail as e:
        raise SystemExit(f'STATUS {args.cmd} FAILED: {e}')


if __name__ == '__main__':
    sys.exit(main())
