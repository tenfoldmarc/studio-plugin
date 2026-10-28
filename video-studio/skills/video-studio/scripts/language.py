#!/usr/bin/env python3
"""The language the buyer speaks in their reels (config.json "language"), asked ONCE, before their first edit.

Usage:
  PY language.py                       STATUS language NOT ASKED  -> ask the question (SKILL.md), then set it
                                       STATUS language <code> (<name>)
  PY language.py set en                English (the speech model never checks for another language)
  PY language.py set ar                Arabic for every reel (also: set Arabic / set es / set French)
  PY language.py set auto              it changes from video to video: English first, and clips the English model
                                       cannot read are checked and re-read in their own language
  PY language.py "<project>" ar        this one reel only (<project>/language.json), the default stays as it is

What it changes: the speech model reads the clips in that language and the captions are written in it, never
translated. Arabic, Persian, Urdu and Hebrew captions read right to left, with Arabic letters in every caption style.
Any language other than English uses the multilingual models (about 2 GB, downloaded once, at the next edit).
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402


def write(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write('\n')


def say_set(code, where):
    print(f'STATUS language SET {code} ({skillenv.lang_name(code)}) for {where}')
    if code == 'auto':
        print('  English first; clips in another language are found and read in it (a one-time 0.5 GB download '
              'the first time that happens)')
    elif code != 'en':
        print(f'  speech models: {skillenv.asr_model("fast", code)} for the takes, {skillenv.asr_model("best", code)} '
              'for the caption words (about 2 GB, downloaded once, at the next edit)')
    if skillenv.is_rtl(code):
        print('  captions read right to left, with Arabic letters in every caption style')


def main():
    skillenv.utf8_stdio()
    args = sys.argv[1:]
    if not args:
        code = skillenv.language_setting()
        print('STATUS language NOT ASKED' if code is None else f'STATUS language {code} ({skillenv.lang_name(code)})')
        return
    if args[0] == 'set' and len(args) >= 2:
        code = skillenv.lang_code(' '.join(args[1:]))
        cfg = skillenv._read_json(skillenv.config_file(), {}) or {}
        cfg['language'] = code
        write(skillenv.config_file(), cfg)
        say_set(code, 'every reel')
        return
    if len(args) == 2 and os.path.isdir(skillenv.path_arg(args[0])):
        proj, code = skillenv.path_arg(args[0]), skillenv.lang_code(args[1])
        write(os.path.join(proj, 'language.json'), {'language': code, 'how': 'set by hand'})
        plan_path = os.path.join(proj, 'plan.json')
        if os.path.isfile(plan_path):                 # plan.json "language" wins over language.json: keep them equal
            plan = skillenv._read_json(plan_path, {}) or {}
            plan.pop('language', None)
            write(plan_path, plan)
        say_set(code, 'this reel')
        print('  then run ingest.py and transcribe_cut.py again: the words were read in the old language')
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
