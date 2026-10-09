#!/usr/bin/env python3
"""The footage check: does THIS clip qualify for an effect, and in which part of the reel may it go?
Run it before building any effect. An effect that fails is skipped, and the buyer is told why in one plain line.

Usage:  PY footage_check.py <project_dir> [effect keys ...] [--all] [--picks <file>]

  no keys   checks the effects the buyer picked (studio-picks.json)        --all   checks every effect

It compares effects/index.json (what each effect needs) with what layout.py measured on the clip (layout.json):
framing (wide / medium / close), camera (still / drifting / moving), open wall, how many shots the cut has, and
whether anybody is on camera. It also lists what has to be in place first (a clean cutout, extra Python packages,
material from the buyer).

Parts of the reel (only matter when the buyer limited effects to parts, "effectSections" in the picks):
  hook = the opening line     end = the call to action     middle = everything between
Worked out from words.json (first sentence; the sentence with the comment keyword, else nothing). Override with
plan.json: {"parts": {"hook": [0, 2.9], "end": [21.4, 25.0]}}.

The measurements are first guesses. A verdict of CHECK means: look at work/sheets.jpg and work/layout/check.jpg
yourself before deciding. A person judging the frames always beats this script.
"""
import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402

MODULES = {'opencv-python-headless': 'cv2', 'mediapipe': 'mediapipe', 'scipy': 'scipy'}


def read(path, fallback):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def parts(words, dur, plan):
    """-> {'hook': (t0, t1), 'middle': (t0, t1) or None, 'end': (t0, t1) or None}"""
    over = (plan or {}).get('parts') or {}
    sentences, cur = [], []
    for w in words:
        cur.append(w)
        if w['text'][-1:] in '.?!':
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    hook = (0.0, sentences[0][-1]['end'] if sentences else dur)
    end = None
    for s in sentences[1:]:
        if any(w.get('e') == 'cta' or w['text'].strip('.,!?').lower() == 'comment' for w in s):
            end = (s[0]['start'], dur)
            break
    if over.get('hook'):
        hook = tuple(float(v) for v in over['hook'])
    if over.get('end'):
        end = tuple(float(v) for v in over['end'])
    mid = (hook[1], end[0] if end else dur)
    return {'hook': hook, 'middle': mid if mid[1] - mid[0] > .3 else None, 'end': end}


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2 or sys.argv[1].startswith('--'):
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    args = sys.argv[2:]
    picks_path = skillenv.picks_file()
    if '--picks' in args:
        i = args.index('--picks')
        picks_path = skillenv.path_arg(args[i + 1])
        args = args[:i] + args[i + 2:]
    index = read(os.path.join(skillenv.SKILL_DIR, 'effects', 'index.json'), {}).get('effects', [])
    by_key = {e['key']: e for e in index}
    picks = read(picks_path, {}) or {}
    layout = read(os.path.join(proj, 'layout.json'), None)
    if layout is None:
        sys.exit('layout.json is missing: run layout.py first.')
    words = read(os.path.join(proj, 'words.json'), [])
    segs = read(os.path.join(proj, 'segments.json'), [])
    plan = read(os.path.join(proj, 'plan.json'), {})
    record = skillenv.load()
    dur = (segs[-1]['frame'] + segs[-1]['frames']) / 30 if segs else (words[-1]['end'] if words else 0)
    keys = [a for a in args if not a.startswith('--')]
    if '--all' in args:
        keys = [e['key'] for e in index]
    keys = keys or list(picks.get('effects') or [])
    if not keys:
        print('No effects picked. Nothing to check.')
        return
    where = parts(words, dur, plan)
    sections = picks.get('effectSections')
    fits, shot, cam = layout.get('fits') or {}, layout.get('shot'), (layout.get('camera') or {}).get('verdict', 'unknown')
    head = layout.get('head') or {}
    src_w = max([s.get('src_w') or 0 for s in segs] + [0])
    frames = int(dur * 30)

    print(f"clip: {shot} shot, camera {cam}, {len(segs) or 1} segment(s), {dur:.1f}s"
          + (f", source {src_w}px wide" if src_w else '') + (', nobody on camera' if layout.get('faceless') else ''))
    print('parts: ' + '  '.join(f'{k} {v[0]:.2f}-{v[1]:.2f}s' if v else f'{k} (none in this reel)' for k, v in where.items()))
    for key in keys:
        e = by_key.get(key)
        if not e:
            print(f'SKIP  {key}: not one of the effects')
            continue
        no, todo, look = [], [], []
        if layout.get('faceless') and (e['cutout'] != 'none' or e['tracking'] != 'none'):
            no.append('it needs the speaker on camera and this reel has nobody on camera')
        else:
            if shot not in e['shot']:
                no.append(f"it needs a {' or '.join(e['shot'])} shot and this clip is a {shot} shot (the head is {head.get('width', '?')}px wide)")
            if cam == 'unknown':
                look.append('camera movement could not be measured')
            elif cam not in e['camera']:
                no.append(f"it needs a {' or '.join(e['camera'])} camera and this one is {cam}")
            if e['wall'] == 'beside' and not (fits.get('wall_left') or fits.get('wall_right')):
                no.append('it needs open wall beside the speaker and there is none in this framing')
            if e['wall'] == 'both' and not (fits.get('wall_left') and fits.get('wall_right')):
                no.append('it needs open room on both sides of the speaker and this framing does not have it')
            if e['wall'] == 'above' and not fits.get('behind_head'):
                no.append('it needs clear wall above the head and the head is too close to the top of the frame')
            if e['segments'] > len(segs or [1]):
                no.append('it needs two different shots back to back and this reel is one continuous take')
        allowed = None
        if sections:
            allowed = [p for p in ('hook', 'middle', 'end') if key in (sections.get(p) or [])]
            usable = [p for p in allowed if where.get(p)]
            if not allowed:
                no.append('the buyer did not allow it in any part of the reel')
            elif not usable:
                no.append(f"the buyer only allowed it in the {' / '.join(allowed)} and this reel has no such part")
        if no:
            print(f"SKIP  {e['name']}: " + '; '.join(no) + '.')
            print(f"      tell the buyer: \"I left {e['name']} out of this one: " + no[0] + '."')
            continue
        ready = e.get('status') == 'ready' and os.path.isfile(os.path.join(skillenv.SKILL_DIR, 'effects', key, 'slot.json'))
        have_cut = os.path.isfile(os.path.join(proj, 'assets', 'subject.webm'))
        if e['cutout'] == 'clean':
            if not record.get('rvm_model'):
                todo.append('one-time setup of the clean cutout: setup.py --matting (about 105 MB)')
            if not have_cut and ready:
                todo.append('a clean cutout of the effect\'s own frames: fx_new.py makes it, about 1.2 s per frame on an '
                            'Apple Silicon Mac (a 3 second slot is about 2 minutes). Tell the buyer before starting')
            elif not have_cut:
                todo.append(f'a clean cutout (rvm_cut.py): about {frames * 1.2 / 60:.0f} min for the whole reel on an Apple '
                            'Silicon Mac, less if you only matte the frames of the effect (--src)')
        elif e['cutout'] == 'quick' and not have_cut:
            todo.append('a cutout (cutout.py is enough)')
        missing = [p for p in e['extra'] if importlib.util.find_spec(MODULES.get(p, p)) is None]
        if missing:
            todo.append(f"extra packages ({' '.join(missing)}), into the skill's own Python: setup.py --fx {key}")
        if (e.get('material') or 'none').strip().lower() not in ('none', 'nothing', ''):
            todo.append('from the buyer: ' + e['material'])
        if key == 'digital-zoom' and src_w:
            sharp = src_w / 1080
            if sharp < 1.3:
                look.append(f'the source is {src_w}px wide, so every zoom is an upscale: keep a creep near 1.15x and a snap near 1.35x')
            elif ready:
                todo.append(f'make the slot with --hi: the source is {src_w}px wide, so zooms stay sharp up to {sharp:.2f}x')
            elif src_w < 2160:
                look.append(f'the source is {src_w}px wide, not 4K: keep the zoom under 1.4x')
        span = 'anywhere in the reel'
        if allowed is not None:
            span = 'only in: ' + ', '.join(f'{p} {where[p][0]:.2f}-{where[p][1]:.2f}s' for p in allowed if where.get(p))
        print(f"{'CHECK' if look else 'OK   '} {e['name']}: fits this clip. Use it {span}.")
        for t in todo:
            print('      first: ' + t)
        for t in look:
            print('      look: ' + t)
        if e['notes']:
            print('      note: ' + e['notes'])
        if ready and e['segments'] > 1:
            cuts = ', '.join(f"{s['frame'] / 30:.2f}s" for s in segs[1:])
            print(f'      ready: fx_new.py {key} --project "<project>" --from <sec> --to <sec>   (a span ACROSS one cut, about '
                  f'0.5 s each side. Cuts in this reel: {cuts}; then effects/INDEX.md "A ready effect")')
        elif ready:
            print(f'      ready: fx_new.py {key} --project "<project>" --from <sec> --to <sec>   (the line it lands on, plus '
                  'about 1.5 s after; then effects/INDEX.md "A ready effect")')
        else:
            print(f"      recipe: effects/{key}/" + ('effect.md, ' if os.path.isfile(os.path.join(skillenv.SKILL_DIR, 'effects', key, 'effect.md')) else '')
                  + 'build.py   (adapt by hand: effects/INDEX.md "A recipe")')


if __name__ == '__main__':
    main()
