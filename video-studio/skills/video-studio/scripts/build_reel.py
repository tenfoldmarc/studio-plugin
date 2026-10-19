#!/usr/bin/env python3
"""Turn the buyer's saved picks into the reel's composition: <project>/index.html.

Usage:  PY build_reel.py <project_dir> [--safe] [--picks <file>] [--caption <key>] [--style <key>]
                                       [--my-style "<saved style>"] [--no-my-style]

  --safe            draw the Reels unsafe area in red (for snapshots only; never render with it)
  --picks <file>    read this picks file instead of the saved one (studio-picks.json in the state folder)
  --caption <key>   one-off: use this caption style for this build without changing the saved picks
  --style <key>     one-off: use this BUILT-IN overall style for this build ("none" = no overall style)
  --my-style <name> one-off: build in this one of the buyer's saved styles
  --no-my-style     one-off: ignore the buyer's saved styles and build from the Studio Picker picks

The buyer's own style wins over the Picker picks: one of their saved styles (styles/<slug>/style.json in the state
folder; plan.json "myStyle" names it, else the default style), then this reel's plan.json on top of it ("caption",
"layers", "grade", "css", "sounds", "motion"). A saved style that carries "picks" (a caption key, an overall style,
effects) uses those instead of studio-picks.json. Every field: references/replicate.md and references/my-styles.md.
A trial reel's plan.json may also hold "reframe" (variations.py writes it: its own zoom, sideways shift, mirror and
light grade on the footage, the cutout and the effect slots; captions and layers stay as placed).

What it reads:
  the picks        {"mode": "preset"|"custom", "style": key|null, "captionStyle": key|"none", "effects": [...],
                    "effectSections": null|{...}}   saved by the Studio Picker
  <project>/words.json    cleaned and marked word timings        <project>/layout.json   where the speaker is
  <project>/plan.json     pinned title, per-style text, effect slots (optional: every look builds without it)

mode "custom": the caption style goes over the untouched footage ("none" = no captions).
mode "preset": the overall style's footage treatment, with its own captions, or with the buyer's caption swap when
               captionStyle differs from the one the style comes with.
Effects are never added here on their own: an effect only shows up as a slot in plan.json ("slots", written by
scripts/fx_add.py), after the footage check (scripts/footage_check.py). A slot's finished render is laid over the
reel for exactly its frames; the reel's own captions are hidden or kept for those frames as the slot entry says; a
slot outside the parts of the reel the buyer allowed for that effect ("effectSections") is left out with a NOTE.
"""
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SK = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SK, 'engine'))
import skillenv  # noqa: E402
import fxlib  # noqa: E402
import captions as cap  # noqa: E402
import styles  # noqa: E402


def opt(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    return None


def read(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def motion_entries(mine, plan):
    """Reel-wide motion: the style's patterns ("on": marks / words / cuts), then this reel's own entries. An entry in
    both (the reel the style was saved from) counts once."""
    out, seen = [], set()
    for m in [m for m in (mine.get('motion') or []) if isinstance(m, dict) and m.get('on')] + \
             [m for m in (plan.get('motion') or []) if isinstance(m, dict)]:
        key = json.dumps(m, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2 or sys.argv[1].startswith('--'):
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    safe = '--safe' in sys.argv

    # Which of the buyer's saved styles this reel is built in (references/my-styles.md): --my-style for a one-off,
    # else plan.json "myStyle", else their default style. --no-my-style builds from the Studio Picker picks alone.
    saved, saved_why = None, 'no saved style'
    if '--no-my-style' in sys.argv:
        saved_why = '--no-my-style'
    elif opt('--my-style'):
        saved, many = skillenv.find_style(opt('--my-style'))
        if not saved:
            sys.exit(f'No saved style called "{opt("--my-style")}".' + (
                ' It could be: ' + ', '.join(m['name'] for m in many) if many else
                ' Saved styles: ' + (', '.join(s['name'] for s in skillenv.saved_styles()) or 'none yet')))
        saved_why = '--my-style'
    else:
        saved, saved_why = skillenv.project_style(proj)
    if saved:
        mine = read(saved['path'], {}) or {}
    elif '--no-my-style' not in sys.argv and os.path.isfile(skillenv.my_style_file()):
        mine = read(skillenv.my_style_file(), {}) or {}          # an old single my-style.json nobody migrated yet
    else:
        mine = {}

    if opt('--picks'):
        picks, picks_path = read(skillenv.path_arg(opt('--picks'))), opt('--picks')
    elif isinstance(mine.get('picks'), dict):
        picks, picks_path = mine['picks'], f'the style "{mine.get("name") or saved["name"]}"'
    else:
        picks_path = skillenv.picks_file()
        picks = read(picks_path)
    if not isinstance(picks, dict):
        if not mine:
            sys.exit(f'No picks saved yet ({picks_path}) and no saved style. Open the Studio Picker '
                     '(PY scripts/picker.py) or build a style from an example (references/replicate.md).')
        picks, picks_path = {'mode': 'custom', 'style': None, 'captionStyle': 'none', 'effects': []}, 'nowhere (the style alone)'
    style = picks.get('style') if picks.get('mode') == 'preset' else None
    caption = picks.get('captionStyle') or 'none'

    layout_file = os.path.join(proj, 'layout.json')
    if not os.path.isfile(layout_file):
        print('WARNING layout.json is missing: run layout.py first. Building with the standard bands, which may cover the face.')
    cap.load(proj)
    del cap.NOTES[:]

    # The buyer's own style beats the saved picks (SKILL.md, "The buyer's style wins"). It is one of their saved
    # styles (picked above); this reel's plan.json can override any part of it. A one-off --caption / --style on the
    # command line beats both.
    plan = cap.PLAN
    own_look = None
    spec = plan.get('caption', mine.get('caption'))
    if isinstance(spec, dict):
        caption, cap.CUSTOM, own_look = 'custom', spec, 'a custom caption style'
    elif isinstance(spec, str) and spec:
        caption, own_look = spec, f'caption style {spec}'
    if own_look and not opt('--style'):
        style = plan.get('style_key', mine.get('style_key'))     # an overall style only when their style names one
    always = [l for l in (mine.get('layers') or []) if isinstance(l, dict) and l.get('from') is None and l.get('to') is None]
    cap.EXTRA = {'layers': always + [l for l in (plan.get('layers') or []) if isinstance(l, dict)],
                 'grade': plan.get('grade', mine.get('grade')),
                 'css': '\n'.join(str(c) for c in (mine.get('css'), plan.get('css')) if c),
                 'sounds': plan.get('sounds') or [],
                 # reel-wide motion: the style's patterns ("on": marks / words / cuts) plus this reel's own entries
                 'motion': motion_entries(mine, plan)}
    # a trial reel's own framing and colour (variations.py): scaled around the face, so the captions placed under it
    # still fit. The point is the face on screen (the layout's head, after any lift) unless the plan gives one.
    reframe = plan.get('reframe')
    if isinstance(reframe, dict) and reframe:
        reframe = dict(reframe)
        h = cap.HEAD or {}
        reframe.setdefault('ox', round(float(h.get('cx', 540)), 1))
        reframe.setdefault('oy', round((float(h.get('top', 700)) + float(h.get('chin', 900))) / 2 - (cap.LIFT or 0), 1))
        cap.EXTRA['reframe'] = reframe
        reframe = cap.reframe_values(reframe)                 # as applied: frames_check.py moves its face box the same way
    else:
        reframe = None
    fonts_src = skillenv.my_fonts_dir()
    if os.path.isdir(fonts_src):                 # fonts fetched for the buyer's style (get_font.py) go with every reel
        os.makedirs(os.path.join(proj, 'assets', 'fonts'), exist_ok=True)
        for f in os.listdir(fonts_src):
            dst = os.path.join(proj, 'assets', 'fonts', f)
            if f.lower().endswith(('.woff2', '.woff', '.ttf', '.otf')) and not os.path.exists(dst):
                import shutil
                shutil.copyfile(os.path.join(fonts_src, f), dst)
    if isinstance(spec, dict) and spec.get('file') and not os.path.isfile(os.path.join(proj, 'assets', 'fonts', spec['file'])):
        cap.NOTES.append(f'The custom caption font file {spec["file"]} is not in the project (assets/fonts) or in the '
                         f'state folder (fonts/): the browser falls back to a plain sans. Fetch it with get_font.py.')

    if opt('--style'):
        style = None if opt('--style') == 'none' else opt('--style')
    if opt('--caption'):
        caption = opt('--caption')
    if style and style not in styles.PRESETS:
        sys.exit(f'Unknown overall style "{style}". The built-in ones: ' + ', '.join(styles.PRESETS))
    if caption not in ('none', 'custom') and caption not in cap.STYLES:
        sys.exit(f'Unknown caption style "{caption}". The built-in ones: ' + ', '.join(cap.STYLES)
                 + ' (or none, or a custom spec under "caption" in plan.json / my-style.json)')
    if caption == 'custom' and not cap.CUSTOM:
        sys.exit('--caption custom needs a caption spec: "caption": {...} in plan.json or my-style.json (references/replicate.md)')
    # layout notes that are about one caption style only matter when that style is the one being built
    only = {'Field Notes': 'field-notes', 'Bubblegum': 'bubblegum', 'Bold': 'bold'}
    notes = [n for n in (cap.LAYOUT.get('notes') or [])
             if not any(name in n and caption != key for name, key in only.items())]

    # effect slots (plan.json, written by fx_add.py): a slot only plays when its render is there and it sits in the
    # parts of the reel the buyer allowed for that effect. A slot that fails is left out of this build, with a NOTE.
    names = {k: e.get('name', k) for k, e in fxlib.index().items()}
    where, _ = fxlib.reel_parts(proj)
    live = []
    for s in cap.PLAN.get('slots') or []:
        if s.get('off'):
            continue
        label = names.get(s.get('key'), s.get('key') or s.get('src'))
        if not os.path.isfile(os.path.join(proj, *str(s.get('src', '')).split('/'))):
            s['off'] = True
            notes.append(f'Effect slot {label}: {s.get("src")} is missing, so the slot was left out. Render it and run fx_add.py.')
            continue
        if s.get('key'):
            ok, why = fxlib.part_verdict(picks, s['key'], where, float(s['from']), float(s['to']))
            if not ok:
                s['off'] = True
                notes.append(f'{label} was left out of this build: {why}.')
                continue
        live.append(s)
    if style and any(not s.get('overlay') for s in live):     # overlay slots keep the style's own footage under them
        notes.append('An effect slot is laid over an overall style: the slot gets the style\'s colour grade, but not its '
                     'push-ins or reframing. Look at both edges of every slot in the final render.')

    if style:
        # the caption style each overall style comes with is the one the picker lists for it
        listed = {s.get('key'): s.get('captionStyle') for s in
                  (read(os.path.join(SK, 'picker', 'data', 'styles.json'), {}) or {}).get('styles', [])}
        own = listed.get(style)
        swap = None if (caption == own or (opt('--style') and not opt('--caption'))) else caption
        html = styles.page(style, swap, safe=safe)
        notes += styles.NOTES
        what = f'style={style} captions=' + ('own' if swap is None else swap)
        if cap.EXTRA.get('grade'):
            notes.append('The grade in plan.json / my-style.json is not applied on top of an overall style, which has its own.')
    else:
        if caption == 'bold' and not cap.CUTOUT:
            notes.append('Bold puts its big words BEHIND the head, which needs a person cutout (rvm_cut.py for a clean '
                         'edge, cutout.py for a quick one). There is none yet, so the big words sit over the chest.')
        html = cap.page(caption, safe=safe)
        what = f'style=none captions={caption}'
    notes += cap.NOTES
    if reframe and reframe['mirror']:
        # a mirrored picture shows any text in it backwards: the words behind the head, an effect's own words, an
        # overall style's on-screen text. Those reels never mirror (references/variations.md, "Mirror").
        why = ('an overall style' if style else 'words or layers behind the head' if cap.BEHIND
               else 'effect slots' if live else None)
        if why:
            sys.exit(f'This trial is mirrored, but the reel has {why}: their words would read backwards. Set "mirror": '
                     f'false in its "unique" (variations.json) and make it again.')
    n_layers = len(cap.EXTRA.get('layers') or [])
    if reframe:
        what += (f"  [trial framing: {float(reframe.get('zoom', 1)):.3f}x" + (' mirrored' if reframe.get('mirror') else '')
                 + (f", {float(reframe.get('x', 0)):+.0f}px" if reframe.get('x') else '') + (', own grade' if reframe.get('grade') else '') + ']')
    if own_look or n_layers or cap.EXTRA.get('grade') or cap.EXTRA.get('css') or cap.EXTRA.get('sounds') or cap.EXTRA.get('motion'):
        what += ('  [the buyer\'s own style: ' + ', '.join(x for x in (
            own_look if caption == 'custom' or own_look and not opt('--caption') else None,
            f'{n_layers} layer(s)' if n_layers else None, 'grade' if cap.EXTRA.get('grade') and not style else None,
            'css' if cap.EXTRA.get('css') else None,
            f"{len(cap.EXTRA['motion'])} motion entr(ies)" if cap.EXTRA.get('motion') else None,
            f"{len(cap.EXTRA['sounds'])} sound cue(s)" if cap.EXTRA.get('sounds') else None) if x) + ']')
    with open(os.path.join(proj, 'index.html'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(html)
    # what was built, for frames_check.py: the automatic checks only make sense when the picture was not regraded or moved
    os.makedirs(os.path.join(proj, 'work'), exist_ok=True)
    # reel motion that moves or filters the picture itself (a punch-in on key words, a flash on cuts) means the
    # frames no longer match the footage, so the automatic before / after comparison would flag every such frame
    moved = any(str(m.get('target', '')).strip() in ('footage', 'speaker', '#plate', '#cutw', '#bgv', '#footage', '#root')
                or any(t in str(m.get('target', '')) for t in ('#plate', '#cutw', '#bgv', '#footage', '#root'))
                for m in (cap.EXTRA.get('motion') or []) if isinstance(m, dict))
    if moved:
        notes.append('Reel motion moves the picture (footage, speaker or #root), so the self-check cannot compare '
                     'frames with the footage: LOOK at its sheet yourself, and at a frame where the picture is moved most.')
    with open(os.path.join(proj, 'work', 'build.json'), 'w', encoding='utf-8') as fh:
        # a reframed trial: the picture no longer matches the raw cut (no before / after numbers), and the face moved a
        # little, so frames_check.py moves its face box the same way ("reframe")
        json.dump({'style': style, 'caption': caption, 'safe': safe,
                   'untouched_footage': not style and not cap.LIFT and not cap.EXTRA.get('grade') and not moved and not reframe,
                   'face_in_place': ((not style) or style == 'fireside') and not moved,
                   'reframe': reframe}, fh, indent=1)
    marks = sum(1 for w in cap.W if w.get('e'))
    print(f'built index.html  {what}  words={len(cap.W)} marked={marks}  dur={cap.DUR:.3f}s  '
          f'slots={len(live)}  safe guide={"ON (snapshots only)" if safe else "off"}')
    print(f'style  ' + (f'saved style "{saved["name"]}" ({saved_why})' if saved else f'none ({saved_why})')
          + f'   picks from {picks_path}')
    for s in live:
        hid = s.get('hide_captions')
        caps = ('captions hidden ' + ', '.join(f'{h[0]:.2f}-{h[1]:.2f}s' for h in hid) if hid
                else 'captions kept' if s.get('captions') in (True, 'keep') else 'captions hidden')
        print(f'slot   {names.get(s.get("key"), s.get("key") or s.get("src"))}  {float(s["from"]):.2f}-{float(s["to"]):.2f}s  '
              f'{caps}  sounds={len(s.get("sfx") or [])}')
    if not (cap.PLAN.get('title')):
        print(f'NOTE   plan.json has no "title": a pinned title would read "{cap.TITLE[0]} / {cap.TITLE[1]}" (a guess).')
    for n in notes:
        print('NOTE   ' + n)
    picked = picks.get('effects') or []
    if picked:
        used = {s.get('key') for s in live}
        print('effects picked: ' + ', '.join(k + (' (in the reel)' if k in used else '') for k in picked)
              + '   (footage_check.py first; an effect only shows up as a slot, see effects/INDEX.md)')


if __name__ == '__main__':
    main()
