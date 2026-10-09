#!/usr/bin/env python3
"""Put what a reel project needs to render into it: hyperframes.json, package.json, assets/fonts, the sound effects
(assets/sfx) and a starter plan.json. One command for every OS and shell, instead of cp / Copy-Item.

Usage:  PY init_project.py <project_dir>

Files that already exist in the project are KEPT, never overwritten, so running this twice is harmless.
plan.json is the per-reel plan the editing Claude fills in (see references/styles.md): the pinned title from the
reel's hook, any words an overall style shows on screen, and the effect slots. Standard library only.
"""
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402


def copy_new(src, dst):
    """Copy one file unless the project already has it. -> True when copied."""
    if os.path.exists(dst):
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def guess_title(words):
    """the opening line as two short lines (the same first guess the caption engine falls back to)"""
    line = []
    for w in words:
        line.append(w['text'])
        if w['text'][-1:] in ',.?!' and len(line) >= 3 or len(line) >= 9:
            break
    line = [t.strip(',.?!;:') for t in line]
    if len(line) < 2:
        return [' '.join(line), '']
    k = min(range(1, len(line)), key=lambda k: abs(len(' '.join(line[:k])) - len(' '.join(line[k:]))))
    return [' '.join(line[:k]), ' '.join(line[k:])]


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    engine = os.path.join(skillenv.SKILL_DIR, 'engine')
    sfx = skillenv.sfx_dir()
    jobs = [(os.path.join(engine, 'template', n), os.path.join(proj, n)) for n in ('hyperframes.json', 'package.json')]
    fonts = os.path.join(engine, 'fonts')
    jobs += [(os.path.join(fonts, n), os.path.join(proj, 'assets', 'fonts', n)) for n in sorted(os.listdir(fonts))]
    sounds = sorted(n for n in os.listdir(sfx) if n.lower().endswith('.mp3')) if os.path.isdir(sfx) else []
    jobs += [(os.path.join(sfx, n), os.path.join(proj, 'assets', 'sfx', n)) for n in sounds]
    copied = [dst for src, dst in jobs if copy_new(src, dst)]
    for d in ('renders', 'work'):
        os.makedirs(os.path.join(proj, d), exist_ok=True)
    print(f'project files -> {proj}: {len(copied)} copied, {len(jobs) - len(copied)} already there and kept')
    if not sounds:
        print('no sound effects found (setup.py reported them MISSING): the reel renders without them until they are added')

    plan = os.path.join(proj, 'plan.json')
    if os.path.exists(plan):
        print('plan.json was already in the project and was left as it is')
        return
    title = ['', '']
    try:
        with open(os.path.join(proj, 'words.json'), encoding='utf-8') as fh:
            title = guess_title(json.load(fh))
    except (OSError, ValueError):
        pass
    starter = {
        'title': title,                       # pinned title: the hook as two short lines (first guess, rewrite it)
        'swash': [' '.join(x[:1].upper() + x[1:] for x in t.split()) for t in title],   # shorter, Title Case (Bubblegum)
        'style': {},                          # words an overall style shows on screen: {"<style key>": {...}}
        'slots': [],                          # finished effect renders laid over the reel
    }
    with open(plan, 'w', encoding='utf-8') as fh:
        json.dump(starter, fh, indent=1)
        fh.write('\n')
    print(f'plan.json started with a first-guess title {title}: rewrite it from the hook '
          '(references/captions.md, "Titles come from the hook"; words for an overall style: references/styles.md)')


if __name__ == '__main__':
    main()
