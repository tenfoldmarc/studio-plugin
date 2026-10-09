#!/usr/bin/env python3
"""Find GIFs for a line in the reel, so you can LOOK at them and pick one. No account and no key.

Usage:  PY gif_find.py <project_dir> "<what the GIF should show, 1 to 4 words>" [--count 12] [--stickers]

  --stickers   only when the buyer asks for a sticker: cut-out shapes with no box around them, instead of GIFs.
It searches Giphy and Tenor, saves a small preview of each GIF to <project>/work/gifs/ and lays them out on one
numbered sheet. Look at the sheet, pick a number, then:
  PY gif_add.py <project_dir> "<the link printed for that number>" --from <sec> --to <sec>
Prints  STATUS gifs FOUND <n> ...  or  STATUS gifs NONE <why>  (then ask the buyer for a GIF file or a link).
"""
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'


def say(line):
    print(line, flush=True)


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def get(url, limit=4_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'}), timeout=40) as r:
        return r.read(limit)


def giphy_ids(slug):
    page = get(f'https://giphy.com/search/{slug}').decode('utf-8', 'replace')
    ids = []
    for m in re.finditer(r'media\d*\.giphy\.com/media/(?:v1\.[A-Za-z0-9_\-]+/)?([A-Za-z0-9]{8,})/', page):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def giphy(words, stickers):
    ids = giphy_ids(urllib.parse.quote('-'.join(words.lower().split()) + ('-stickers' if stickers else '')))
    # The site puts a graphic of its own on every page. A search for nothing shows which ones those are.
    try:
        own = set(giphy_ids('zxqvjkwpplmno')) if ids else set()
    except (urllib.error.URLError, OSError, ValueError):
        own = set()
    return [{'link': f'https://giphy.com/gifs/{i}', 'preview': f'https://media.giphy.com/media/{i}/200w.gif'}
            for i in ids if i not in own]


def tenor(words):
    slug = urllib.parse.quote('-'.join(words.lower().split()) + '-gifs')
    page = get(f'https://tenor.com/search/{slug}').decode('utf-8', 'replace')
    seen, out = set(), []
    for m in re.finditer(r'https://media\d*\.tenor\.com/(?:m/)?([A-Za-z0-9_\-]{10,})/([^"\\ ]+\.gif)', page):
        key = m.group(1)[:11]          # the same GIF is listed in several sizes: the start of the id is shared
        if key not in seen:
            seen.add(key)
            # ids end in a size code: ...AAAAC is the full GIF, ...AAAAM a small one (enough for the sheet)
            small = f'https://media.tenor.com/{m.group(1)[:-1]}M/{m.group(2)}' if m.group(1).endswith('AAAAC') else m.group(0)
            out.append({'link': m.group(0), 'preview': small})
    return out


def sheet(tiles, path, cols=4, cell=260):
    """Numbered sheet: the middle frame of every preview, on a checker so see-through parts show."""
    from PIL import Image, ImageDraw
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new('RGB', (cols * cell, rows * cell), (24, 24, 26))
    d = ImageDraw.Draw(out)
    for k, (n, file) in enumerate(tiles):
        x0, y0 = (k % cols) * cell, (k // cols) * cell
        for cy in range(0, cell, 20):
            for cx in range(0, cell, 20):
                if (cx // 20 + cy // 20) % 2:
                    d.rectangle([x0 + cx, y0 + cy, x0 + cx + 19, y0 + cy + 19], fill=(46, 46, 50))
        try:
            im = Image.open(file)
            im.seek(getattr(im, 'n_frames', 1) // 2)
            im = im.convert('RGBA')
            im.thumbnail((cell - 16, cell - 16))
            out.paste(im, (x0 + (cell - im.width) // 2, y0 + (cell - im.height) // 2), im)
        except (OSError, EOFError, ValueError):
            pass
        d.rectangle([x0, y0, x0 + 44, y0 + 34], fill=(255, 91, 31))
        d.text((x0 + 14, y0 + 10), str(n), fill=(0, 0, 0))
    out.save(path, quality=88)


def main():
    skillenv.utf8_stdio()
    args = [a for a in sys.argv[1:] if not a.startswith('--') and a != opt('--count')]
    if len(args) < 2:
        sys.exit(__doc__)
    proj, words = os.path.abspath(skillenv.path_arg(args[0])), ' '.join(args[1:]).strip()
    stickers = '--stickers' in sys.argv
    try:
        count = max(1, min(int(opt('--count', '12')), 16))
    except ValueError:
        count = 12
    # Both libraries, half the sheet each (all of it from one when the other gives nothing). Stickers: Giphy only.
    from_giphy, from_tenor = [], []
    try:
        from_giphy = giphy(words, stickers)
    except (urllib.error.URLError, OSError, ValueError):
        pass
    if not stickers:
        try:
            from_tenor = tenor(words)
        except (urllib.error.URLError, OSError, ValueError):
            pass
    half = (count + 1) // 2
    take_g = min(len(from_giphy), max(half, count - len(from_tenor)))
    found = from_giphy[:take_g] + from_tenor[:count - take_g]
    where = ' and '.join(n for n, got in (('Giphy', take_g), ('Tenor', len(found) - take_g)) if got)
    if not found:
        say(f'STATUS gifs NONE: nothing came back for "{words}". Try other words, or ask the buyer for a GIF file or a link.')
        sys.exit(2)

    folder = os.path.join(proj, 'work', 'gifs', skillenv.safe_name(words)[:40] + ('-stickers' if stickers else ''))
    os.makedirs(folder, exist_ok=True)
    tiles, lines = [], []
    for item in found:
        if len(tiles) >= count:
            break
        n = len(tiles) + 1
        file = os.path.join(folder, f'{n:02d}.gif')
        data = b''
        for address in dict.fromkeys((item['preview'], item['link'])):
            try:
                data = get(address)
            except (urllib.error.URLError, OSError, ValueError):
                data = b''
            if len(data) >= 200 and data[:3] == b'GIF':
                break
        if len(data) < 200 or data[:3] != b'GIF':
            continue
        with open(file, 'wb') as fh:
            fh.write(data)
        tiles.append((n, file))
        lines.append(f'  {n}  {item["link"]}')
    if not tiles:
        say(f'STATUS gifs NONE: the previews for "{words}" did not load. Ask the buyer for a GIF file or a link.')
        sys.exit(2)
    path = os.path.join(folder, 'sheet.jpg')
    sheet(tiles, path)
    say(f'STATUS gifs FOUND {len(tiles)} on {where} for "{words}". LOOK at the sheet before you pick: {skillenv.shell_path(path)}')
    say('\n'.join(lines))
    say('next: PY gif_add.py "<project>" "<the link of the one you picked>" --from <sec> --to <sec>')


if __name__ == '__main__':
    main()
