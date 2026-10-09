#!/usr/bin/env python3
"""Fetch one openly licensed typeface for the buyer's own style, when the example uses a face the skill does not ship.

Usage:  PY get_font.py "<Family Name>" [--weight 700] [--italic] [--list]

  It asks Google Fonts for the family (every family there is under an open licence: OFL, Apache or UFL) and saves one
  .woff2 file into <state folder>/fonts/ as <Family>-<weight>-<normal|italic>.woff2. build_reel.py copies that folder
  into every project, and a custom caption spec uses the file with  "font": "<Family Name>", "file": "<that name>".
  --list   only show the fonts the skill already has (shipped + fetched), then stop

Never a paid font: if the family is not on Google Fonts this stops and says so. Pick the nearest face that is
(or one the skill ships: engine/fonts), and tell the buyer which face stands in for the one in their example.
Needs the internet once per face. Standard library only.
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


def opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def have():
    shipped = os.path.join(skillenv.SKILL_DIR, 'engine', 'fonts')
    mine = skillenv.my_fonts_dir()
    out = []
    for label, d in (('shipped', shipped), ('fetched', mine)):
        if os.path.isdir(d):
            out += [(label, f) for f in sorted(os.listdir(d)) if f.lower().endswith(('.woff2', '.woff', '.ttf', '.otf'))]
    return out


def main():
    skillenv.utf8_stdio()
    args = [a for a in sys.argv[1:] if not a.startswith('--') and a != opt('--weight')]
    if '--list' in sys.argv:
        for label, f in have():
            print(f'{label:8} {f}')
        return
    if not args:
        sys.exit(__doc__)
    family = ' '.join(args[0].split())
    weight = int(opt('--weight', '400'))
    italic = '--italic' in sys.argv
    spec = f'{urllib.parse.quote_plus(family)}:ital,wght@{1 if italic else 0},{weight}'
    url = f'https://fonts.googleapis.com/css2?family={spec}&display=block'
    try:
        css = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        sys.exit(f'"{family}" at weight {weight}{" italic" if italic else ""} is not on Google Fonts (HTTP {e.code}). The skill only '
                 'fetches openly licensed faces and never a paid one: pick the nearest open face, or one it ships '
                 '(PY get_font.py --list), and tell the buyer which face stands in.')
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f'could not reach Google Fonts ({e}). Check the connection, or use a face the skill ships (--list).')
    # the css lists one block per script; the plain Latin one is marked /* latin */ (take the last block otherwise)
    blocks = re.findall(r'/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{[^}]*?src:\s*url\(([^)]+)\)', css)
    pick = next((u for name, u in blocks if name == 'latin'), None) or (blocks[-1][1] if blocks else None)
    if not pick:
        m = re.search(r'src:\s*url\(([^)]+)\)', css)
        pick = m.group(1) if m else None
    if not pick:
        sys.exit(f'Google Fonts answered, but with no font file for "{family}" {weight}. Try another weight.')
    dest_dir = skillenv.my_fonts_dir()
    os.makedirs(dest_dir, exist_ok=True)
    name = f'{re.sub(r"[^A-Za-z0-9]", "", family)}-{weight}-{"italic" if italic else "normal"}.woff2'
    dest = os.path.join(dest_dir, name)
    data = urllib.request.urlopen(urllib.request.Request(pick.strip('\'"'), headers={'User-Agent': UA}), timeout=60).read()
    if len(data) < 2000:
        sys.exit('the font file came back empty. Try again, or use a face the skill ships (--list).')
    with open(dest, 'wb') as fh:
        fh.write(data)
    print(f'fetched {family} {weight}{" italic" if italic else ""} ({len(data) // 1024} KB, open licence, from Google Fonts)')
    print(f'file    {skillenv.shell_path(dest)}')
    print(f'use it  "font": "{family}", "weight": {weight}, "file": "{name}"' + (', "italic": true' if italic else '')
          + '   in the caption spec, or in a layer\'s css with @font-face and url(\'assets/fonts/' + name + '\')')


if __name__ == '__main__':
    main()
