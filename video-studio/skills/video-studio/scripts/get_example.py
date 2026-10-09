#!/usr/bin/env python3
"""Put the example the buyer showed into the state folder so it can be studied: a file on this computer, or a
direct media address (the address of the video or picture itself, not of the page it sits on).

Usage:  PY get_example.py "<file>" [--name <short label>]
        PY get_example.py --direct "<direct video or picture address>" [--name <short label>]

It lands in <state folder>/examples/downloads/ and prints  STATUS example READY <file>  (then: study.py on that
file), or  STATUS example FAILED <why>.  Plain Python, nothing to install.

A link to a post (a reel, a short, a pin) is not handled here. The editing Claude gets the video's direct address
with its Apify tool and passes it with --direct. See references/replicate.md.
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
                say('STATUS example FAILED: that address is a page, not the video or picture itself. A link to a post needs '
                    'the Apify tool to find its direct address (references/replicate.md).')
                return None
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


def main():
    skillenv.utf8_stdio()
    src = opt('--direct') or next((a for a in sys.argv[1:] if not a.startswith('--') and a != opt('--name')), None)
    if not src:
        sys.exit(__doc__)
    sys.exit(0 if fetch(src, opt('--name')) else 2)


if __name__ == '__main__':
    main()
