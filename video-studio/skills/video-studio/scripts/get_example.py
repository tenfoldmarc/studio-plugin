#!/usr/bin/env python3
"""Put the examples the buyer showed into the state folder so they can be studied: a link to a post (an Instagram
reel, a TikTok, a YouTube short, ...), a file on this computer, or a direct media address.

Usage:  PY get_example.py "<link or file>" ["<another>" ...] [--name <short label>] [--browser chrome|safari|firefox|edge]
        PY get_example.py --direct "<direct video or picture address>" [--name <short label>]

  a link        fetched with yt-dlp, which the Studio installs into its own Python the first time (about 3 MB) and
                updates once by itself when a site has changed. One file per link (the first video of a carousel).
  --browser     ONLY after the buyer said yes: some posts (often Instagram) only show to a logged-in visitor, and this
                lets yt-dlp read that browser's login to fetch them. Nothing is stored. Without it such a post fails
                with a plain message, and the buyer can download the video themselves and drop the file in.
  --direct      the address of the video file itself (from an Apify tool, for example); such addresses expire in minutes

Each one lands in <state folder>/examples/downloads/ and prints  STATUS example READY <file>  (then: study.py on
that file), or  STATUS example FAILED <why>.  See references/replicate.md.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
MEDIA = ('.mp4', '.mov', '.webm', '.m4v', '.mkv', '.jpg', '.jpeg', '.png', '.webp', '.gif')
TYPES = {'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/webm': '.webm', 'image/jpeg': '.jpg',
         'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'}
MAX_BYTES = 600 * 1024 * 1024


def say(line):
    print(line, flush=True)


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def downloads():
    d = os.path.join(skillenv.examples_dir(), 'downloads')
    os.makedirs(d, exist_ok=True)
    return d


def is_media(path):
    try:
        out = subprocess.run([skillenv.tool('ffprobe'), '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', path],
                             timeout=60, **skillenv.TEXT).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return 'video' in out


def ready(path, how):
    if not is_media(path):
        say(f'STATUS example FAILED: what came from {how} is not a video or a picture.')
        return None
    say(f'STATUS example READY {skillenv.shell_path(path)}  ({os.path.getsize(path) / 1e6:.1f} MB, {how})')
    say(f'next: PY study.py "{skillenv.shell_path(path)}"')
    return path


def fetch(src, name=None):
    """A file or a direct media address -> a local file in the state folder, or None after one STATUS line."""
    try:
        src = src.strip().strip('"\'')
        if not src.lower().startswith(('http://', 'https://')):
            path = os.path.abspath(skillenv.path_arg(src))
            if not os.path.isfile(path):
                say(f'STATUS example FAILED: {path} is not a file on this computer.')
                return None
            dest = os.path.join(downloads(), os.path.basename(path))
            if os.path.abspath(dest) != path and not os.path.exists(dest):
                shutil.copyfile(path, dest)
            return ready(dest, 'the file the buyer gave')
        with urllib.request.urlopen(urllib.request.Request(src, headers={'User-Agent': UA, 'Accept': '*/*'}), timeout=60) as r:
            ctype = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            ext = os.path.splitext(urllib.parse.urlparse(src).path)[1].lower()
            ext = ext if ext in MEDIA else TYPES.get(ctype, '')
            if not ext:
                if opt('--direct'):
                    say('STATUS example FAILED: that address is a page, not the video or picture itself. Run it '
                        'without --direct: get_example.py "<link>" fetches posts.')
                    return None
                return from_link(src, name)
            label = skillenv.safe_name(name)[:60] if name else 'example-' + hashlib.sha1(src.encode('utf-8', 'replace')).hexdigest()[:8]
            dest = os.path.join(downloads(), label + ext)
            done = 0
            with open(dest + '.part', 'wb') as fh:
                while done <= MAX_BYTES:
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    done += len(buf)
                    fh.write(buf)
        if done > MAX_BYTES or done < 1000:
            os.replace(dest + '.part', dest + '.rejected')
            say('STATUS example FAILED: the file is empty or far too large for a short video.')
            return None
        os.replace(dest + '.part', dest)
        return ready(dest, 'a direct address')
    except (urllib.error.URLError, OSError, ValueError) as e:
        say(f'STATUS example FAILED: the address did not answer ({type(e).__name__}). A direct address expires within '
            'minutes: get a new one and run this again.')
        return None


POST_SITES = ('instagram.com', 'tiktok.com', 'youtube.com', 'youtu.be', 'facebook.com', 'fb.watch', 'x.com',
              'twitter.com', 'pinterest.', 'pin.it', 'threads.net', 'vimeo.com', 'linkedin.com', 'snapchat.com')
BROWSERS = ('chrome', 'safari', 'firefox', 'edge', 'brave', 'chromium', 'opera', 'vivaldi')


def is_post(src):
    host = urllib.parse.urlparse(src).netloc.lower()
    return any(s in host for s in POST_SITES)


def yt_dlp(*args):
    return subprocess.run([sys.executable, '-m', 'yt_dlp', *args], timeout=600, **skillenv.TEXT)


def have_yt_dlp(update=False):
    """yt-dlp in the Studio's own Python: installed the first time a link comes in, updated when asked (sites change
    often and an old yt-dlp is the usual reason a link stops working)."""
    try:
        ok = subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'], timeout=60, **skillenv.TEXT).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if ok and not update:
        return True
    say('getting the link downloader (yt-dlp, about 3 MB, one time)...' if not ok else 'updating the link downloader...')
    try:
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '--upgrade',
                            'yt-dlp'], timeout=600, **skillenv.TEXT)
    except (OSError, subprocess.SubprocessError):
        return ok
    return r.returncode == 0 or ok


def from_link(src, name=None):
    """A link to a post -> the video in the state folder, through yt-dlp."""
    if not have_yt_dlp():
        say('STATUS example FAILED: the link downloader could not be installed (no internet?). Download the video '
            'and drop the file in instead.')
        return None
    label = skillenv.safe_name(name)[:60] if name else 'example-' + hashlib.sha1(src.encode('utf-8', 'replace')).hexdigest()[:8]
    out = os.path.join(downloads(), label + '.%(ext)s')
    ff = os.path.dirname(skillenv.tool('ffmpeg') or '') or None
    args = ['--no-playlist', '--playlist-items', '1', '--no-progress', '--no-warnings', '--max-filesize', '600M',
            '-f', 'bv*[ext=mp4][height<=1920]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b', '--merge-output-format', 'mp4',
            '-o', out, '--print', 'after_move:filepath']
    if ff:
        args += ['--ffmpeg-location', ff]
    browser = (opt('--browser') or '').lower()
    if browser:
        if browser not in BROWSERS:
            say(f'STATUS example FAILED: --browser must be one of {", ".join(BROWSERS)}.')
            return None
        args += ['--cookies-from-browser', browser]
    for attempt in (1, 2):
        try:
            r = yt_dlp(*args, src)
        except subprocess.TimeoutExpired:
            say('STATUS example FAILED: the download took more than 10 minutes. Ask for the video file instead.')
            return None
        path = next((l.strip() for l in reversed(r.stdout.splitlines()) if l.strip() and os.path.isfile(l.strip())), None)
        if r.returncode == 0 and path:
            return ready(path, 'the link')
        err = (r.stderr or '').lower()
        gone = ('private', 'not available', 'unavailable', 'removed', 'does not exist', '404')
        if attempt == 1 and not any(x in err for x in ('login', 'log in', 'cookies') + gone):
            have_yt_dlp(update=True)        # most other failures are an out-of-date downloader: update once, try again
            continue
        break
    if browser and any(x in err for x in ('could not copy', 'decrypt', 'dpapi', 'app-bound', 'permission denied',
                                              'operation not permitted', 'unsupported browser')):
        say(f'STATUS example FAILED: {browser}\'s login could not be read on this computer (Chrome and Edge on '
            'Windows lock it, and Safari needs Full Disk Access on a Mac). Try Firefox if they use it, or ask the buyer '
            'to download the video and drop the file in.')
    elif any(x in err for x in ('login', 'log in', 'cookies', 'rate-limit', 'rate limit')):
        say('STATUS example FAILED LOGIN: this post only shows to someone logged in. Ask the buyer: "Can I use your '
            'browser\'s login to fetch it? Nothing is saved." On yes, run again with --browser <their browser> '
            '(on Windows, Firefox works best: Chrome and Edge lock their login there). Or they download the video '
            'themselves and drop the file in.')
    elif any(x in err for x in gone):
        say('STATUS example FAILED: that post is private or was taken down. Ask for another link, or the video file.')
    else:
        last = next((l for l in reversed((r.stderr or '').splitlines()) if l.strip()), 'no reason given')
        say(f'STATUS example FAILED: the link could not be fetched ({last.strip()[:160]}). Ask the buyer to download '
            'the video and drop the file in.')
    return None


def main():
    skillenv.utf8_stdio()
    if opt('--direct'):
        sys.exit(0 if fetch(opt('--direct'), opt('--name')) else 2)
    skip = {opt('--name'), opt('--browser')}
    srcs = [a for a in sys.argv[1:] if not a.startswith('--') and a not in skip]
    if not srcs:
        sys.exit(__doc__)
    got = 0
    for i, src in enumerate(srcs):
        name = opt('--name') if len(srcs) == 1 else (f'{opt("--name")}-{i + 1}' if opt('--name') else None)
        s = src.strip().strip('"\'')
        if s.lower().startswith(('http://', 'https://')) and is_post(s):
            got += bool(from_link(s, name))
        else:
            got += bool(fetch(s, name))
    sys.exit(0 if got == len(srcs) else 2)


if __name__ == '__main__':
    main()
