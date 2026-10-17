#!/usr/bin/env python3
"""The buyer's saved editing styles: make, list, name, pick the default, and choose one for a reel.

A saved style is a folder in the state folder: styles/<slug>/style.json (what build_reel.py reads) and style.md (the
same in plain words, where each part came from, their standing notes). references/my-styles.md has the format.

Usage:
  PY my_styles.py list                                   every saved style, the default first
  PY my_styles.py show "<name>"                          one style: what it holds, where its files are
  PY my_styles.py save "<name>" --from-project "<project>" [--with-picks]
        make the style (or update it) from a reel the buyer just approved: its plan.json "caption", always-on
        "layers", "grade", "css", "motion" and "sounds_note" go into the style. --with-picks also stores the Studio
        Picker picks (caption key, overall style, effects) in it, so the style carries its effects.
  PY my_styles.py save "<name>" --from-picks             a style made of Picker picks only (no custom spec)
  PY my_styles.py new "<name>"                           an empty style to fill in by hand
  PY my_styles.py use "<project>" "<name>" | none        build this reel in that style (writes plan.json "myStyle")
  PY my_styles.py default "<name>" | none                the style "edit it" uses when the buyer names none
  PY my_styles.py rename "<name>" "<new name>"
  PY my_styles.py duplicate "<name>" "<new name>"        a copy to change without touching the original
  PY my_styles.py retire "<name>"                        moves it to styles/_retired/ (never deleted)

Names are what the buyer calls them ("Cozy Talk"); a unique part of a name is enough ("cozy"). Standard library only.
"""
import datetime
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

FROM_PLAN = ('caption', 'grade', 'css', 'motion', 'style_key')
NOTES_MD = """# {name}

Made: {date}. Edit this file in plain words; style.json is what the build reads. Keep both in step.

## Made from
<!-- one line per example: the file or link, and what was taken from it ("captions from A, motion from B") -->

## Type

## Colour

## Captions

## Caption motion

## Pace

## Framing

## Graphic elements

## Sound

## Effects
<!-- which of the Studio's effects this style uses, where (hook / middle / end), and how they are restyled -->

## Standing notes
<!-- "always" and "never" notes the buyer gave: every reel in this style follows them -->

## Could not be matched
"""


def read(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(data, fh, indent=1)
        fh.write('\n')


def today():
    return datetime.date.today().isoformat()


def need(name):
    s, many = skillenv.find_style(name)
    if s:
        return s
    have = skillenv.saved_styles()
    if many:
        sys.exit(f'"{name}" could be more than one style: ' + ', '.join(m['name'] for m in many) + '. Use the full name.')
    sys.exit(f'No saved style called "{name}". Saved styles: ' + (', '.join(h['name'] for h in have) or 'none yet'))


def summary(spec):
    """one plain line: what a style holds"""
    bits = []
    c = spec.get('caption')
    if isinstance(c, dict):
        bits.append('custom captions' + (f' ({c.get("font")})' if c.get('font') else ''))
    elif c:
        bits.append(f'{c} captions')
    p = spec.get('picks') or {}
    if p.get('mode') == 'preset' and p.get('style'):
        bits.append(f'overall style {p["style"]}')
    if p.get('captionStyle') and not c:
        bits.append(f'{p["captionStyle"]} captions')
    if p.get('effects'):
        bits.append('effects: ' + ', '.join(p['effects']))
    if spec.get('layers'):
        bits.append(f'{len(spec["layers"])} always-on layer(s)')
    if spec.get('motion'):
        bits.append('custom motion')
    if spec.get('grade'):
        bits.append('a grade')
    if spec.get('sources'):
        bits.append(f'made from {len(spec["sources"])} example(s)')
    return ', '.join(bits) or 'empty so far'


def folder_for(name):
    return os.path.join(skillenv.styles_dir(), skillenv.style_slug(name))


def start(name):
    """the folder and spec for a new style (refuses a name that is taken)"""
    s, _ = skillenv.find_style(name)
    if s and s['name'].lower() == str(name).strip().lower():
        return s['path'], read(s['path'], {}) or {}, False
    folder = folder_for(name)
    if os.path.exists(folder):
        sys.exit(f'A style folder {os.path.basename(folder)} already exists. Pick another name.')
    spec = {'name': str(name).strip(), 'slug': os.path.basename(folder), 'created': today()}
    return os.path.join(folder, 'style.json'), spec, True


def finish(path, spec, fresh):
    spec['updated'] = today()
    write(path, spec)
    md = os.path.join(os.path.dirname(path), 'style.md')
    if not os.path.isfile(md):
        with open(md, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(NOTES_MD.format(name=spec['name'], date=today()))
    if not skillenv.default_style():
        cfg = read(skillenv.config_file(), {}) or {}
        cfg['defaultStyle'] = spec['slug']
        write(skillenv.config_file(), cfg)
        print(f'DEFAULT "{spec["name"]}" is the default style now (the only one saved)')
    print(f'{"SAVED" if fresh else "UPDATED"} "{spec["name"]}": {summary(spec)}')
    print(f'  {path}')
    print(f'  {md}   write the plain-words notes here (references/my-styles.md)')


def cmd_save(args):
    if not args:
        sys.exit('save "<name>" --from-project "<project>" [--with-picks]   or   save "<name>" --from-picks')
    name = args[0]
    path, spec, fresh = start(name)
    took = []
    if '--from-project' in args:
        proj = skillenv.path_arg(args[args.index('--from-project') + 1])
        plan = read(os.path.join(proj, 'plan.json'))
        if not isinstance(plan, dict):
            sys.exit(f'No plan.json in {proj}.')
        for k in FROM_PLAN:
            if k == 'motion':
                # only patterns carry over ("on": marks / words / cuts); motion at fixed seconds belongs to that reel
                pat = [m for m in (plan.get('motion') or []) if isinstance(m, dict) and m.get('on')]
                fixed = len(plan.get('motion') or []) - len(pat)
                if pat:
                    spec['motion'] = pat
                    took.append(f'{len(pat)} motion pattern(s)')
                if fixed:
                    print(f'note: {fixed} motion entr(ies) at fixed seconds stay with that reel only. If they are part '
                          'of the style, rewrite them with "on" (references/motion.md).')
            elif plan.get(k) not in (None, '', [], {}):
                spec[k] = plan[k]
                took.append(k)
        always = [l for l in (plan.get('layers') or []) if isinstance(l, dict) and l.get('from') is None and l.get('to') is None]
        if always:
            spec['layers'] = always
            took.append(f'{len(always)} always-on layer(s)')
        timed = len(plan.get('layers') or []) - len(always)
        if timed:
            print(f'note: {timed} timed layer(s) stay with that reel only (they were written from its words). Describe '
                  'them in style.md under "Graphic elements" so the next reel gets its own.')
        spec.setdefault('builtFrom', []).append(os.path.basename(os.path.normpath(proj)))
    if '--from-picks' in args or '--with-picks' in args:
        picks = read(skillenv.picks_file())
        if not isinstance(picks, dict):
            sys.exit('No Studio Picker picks are saved yet: open the picker first, or save without --with-picks.')
        spec['picks'] = picks
        took.append('the Picker picks')
    if not took and fresh:
        print('note: nothing to take yet, so the style starts empty. Fill style.json (references/my-styles.md).')
    elif took:
        print('took: ' + ', '.join(took))
    finish(path, spec, fresh)


def cmd_new(args):
    if not args:
        sys.exit('new "<name>"')
    path, spec, fresh = start(args[0])
    if not fresh:
        sys.exit(f'"{spec["name"]}" is already saved. Use save to update it, or pick another name.')
    finish(path, spec, fresh)


def cmd_list(_):
    have = skillenv.saved_styles()
    if not have:
        print('No saved styles yet. Make one from an example (references/replicate.md) or from the Picker picks '
              '(my_styles.py save "<name>" --from-picks).')
        return
    for s in have:
        spec = read(s['path'], {}) or {}
        print(f'{"* " if s["default"] else "  "}{s["name"]}   {summary(spec)}')
    print('(* = the default: "edit it" uses it when the buyer names no style)')


def cmd_show(args):
    s = need(args[0] if args else '')
    spec = read(s['path'], {}) or {}
    print(f'{s["name"]}{" (default)" if s["default"] else ""}: {summary(spec)}')
    print(f'  style.json  {s["path"]}')
    md = os.path.join(os.path.dirname(s['path']), 'style.md')
    print(f'  style.md    {md}' + ('' if os.path.isfile(md) else '   (missing: write it)'))
    for src in spec.get('sources') or []:
        print(f'  from        {src.get("took", "?")}: {src.get("example") or src.get("link") or "?"}')


def cmd_use(args):
    if len(args) < 2:
        sys.exit('use "<project>" "<name>" | none')
    proj = skillenv.path_arg(args[0])
    plan_path = os.path.join(proj, 'plan.json')
    plan = read(plan_path, {}) or {}
    if args[1] == 'none':
        plan['myStyle'] = 'none'
        write(plan_path, plan)
        print('this reel is built from the Studio Picker picks, no saved style')
        return
    s = need(args[1])
    plan['myStyle'] = s['slug']
    write(plan_path, plan)
    print(f'this reel is built in "{s["name"]}": {summary(read(s["path"], {}) or {})}')


def cmd_default(args):
    cfg = read(skillenv.config_file(), {}) or {}
    if not args or args[0] == 'none':
        cfg.pop('defaultStyle', None)
        write(skillenv.config_file(), cfg)
        print('no default style: "edit it" uses the Studio Picker picks unless the buyer names a style')
        return
    s = need(args[0])
    cfg['defaultStyle'] = s['slug']
    write(skillenv.config_file(), cfg)
    print(f'DEFAULT "{s["name"]}": "edit it" uses it when the buyer names no style')


def cmd_rename(args):
    if len(args) < 2:
        sys.exit('rename "<name>" "<new name>"')
    s = need(args[0])
    dst = folder_for(args[1])
    old = os.path.dirname(s['path'])
    if os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(old):
        sys.exit(f'A style called "{args[1]}" is already saved.')
    if os.path.normcase(dst) != os.path.normcase(old):
        os.replace(old, dst)
    spec = read(os.path.join(dst, 'style.json'), {}) or {}
    spec['name'], spec['slug'], spec['updated'] = args[1].strip(), os.path.basename(dst), today()
    write(os.path.join(dst, 'style.json'), spec)
    if s['default']:
        cfg = read(skillenv.config_file(), {}) or {}
        cfg['defaultStyle'] = spec['slug']
        write(skillenv.config_file(), cfg)
    print(f'RENAMED "{s["name"]}" -> "{spec["name"]}"')


def cmd_duplicate(args):
    if len(args) < 2:
        sys.exit('duplicate "<name>" "<new name>"')
    s = need(args[0])
    dst = folder_for(args[1])
    if os.path.exists(dst):
        sys.exit(f'A style called "{args[1]}" is already saved.')
    shutil.copytree(os.path.dirname(s['path']), dst)
    spec = read(os.path.join(dst, 'style.json'), {}) or {}
    spec.update(name=args[1].strip(), slug=os.path.basename(dst), created=today(), copiedFrom=s['name'])
    write(os.path.join(dst, 'style.json'), spec)
    print(f'COPIED "{s["name"]}" -> "{spec["name"]}"')


def cmd_retire(args):
    s = need(args[0] if args else '')
    old = os.path.dirname(s['path'])
    dst = os.path.join(skillenv.styles_dir(), '_retired', f'{s["slug"]}-{today()}')
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(skillenv.styles_dir(), '_retired', f'{s["slug"]}-{today()}-{n}')
        n += 1
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(old, dst)
    if s['default']:
        cfg = read(skillenv.config_file(), {}) or {}
        cfg.pop('defaultStyle', None)
        write(skillenv.config_file(), cfg)
    print(f'RETIRED "{s["name"]}" (kept in {dst})' + ('; there is no default style now' if s['default'] else ''))


def main():
    skillenv.utf8_stdio()
    cmds = {'list': cmd_list, 'show': cmd_show, 'save': cmd_save, 'new': cmd_new, 'use': cmd_use,
            'default': cmd_default, 'rename': cmd_rename, 'duplicate': cmd_duplicate, 'retire': cmd_retire}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
