#!/usr/bin/env python3
"""First guess at the word marks in <project>/words.json. Run it AFTER fixing Whisper's mishearings by hand.

Usage:  PY marks.py <project_dir> [--dry]        (--dry prints the guess and changes nothing)

The marks (the "e" field of a word) tell every caption style which words to treat differently:
  num   a number worth showing big          digits ("21", "$500", "10x") and number words ("seven", "twenty")
  cta   the comment keyword                 the word right after "comment" (skipping "the word", "below" ...)
  key   a name or brand                     a capitalised word that does not start a sentence ("Claude", "Instagram")
  emph  the word the line leans on          never guessed: that one is a judgement call, add it by hand

This is only a first guess. The rule the editing Claude applies afterwards is in references/captions.md
("Marking the words"): at most one num / emph / cta per sentence, key on every name, nothing on filler words.
Words that already carry a mark are left alone. The file before marking is kept as work/words_premarks.json.
"""
import json
import os
import re
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

NUMBER_WORDS = {'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen',
                'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty', 'forty',
                'fifty', 'sixty', 'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'billion', 'zero',
                'double', 'triple', 'half'}                       # "one" is left out: it is usually not a number
SKIP_AFTER_COMMENT = {'the', 'word', 'a', 'below', 'down', 'this', 'just', 'me', 'with'}
NOT_NAMES = {'i', "i'm", "i'll", "i've", "i'd", 'ok', 'okay'}


def bare(text):
    return text.strip('.,;:!?"“”\'()')


def guess(words):
    """-> list of (index, mark, why). Does not change words."""
    out, new_sentence, punch_in_sentence = [], True, False
    for i, w in enumerate(words):
        t = bare(w['text'])
        low = t.lower()
        starts = new_sentence
        if new_sentence:
            punch_in_sentence = False
        new_sentence = w['text'][-1:] in '.?!'
        if w.get('e'):
            punch_in_sentence = punch_in_sentence or w['e'] in ('num', 'emph', 'cta')
            continue
        prev = [bare(x['text']).lower() for x in words[max(0, i - 3):i]]
        after_comment = 'comment' in prev and all(p in SKIP_AFTER_COMMENT or p == 'comment' for p in prev[prev.index('comment'):])
        if after_comment and low not in SKIP_AFTER_COMMENT and low != 'comment' and t:
            out.append((i, 'cta', 'the word after "comment"'))
            punch_in_sentence = True
        elif re.search(r'\d', t) or low in NUMBER_WORDS:
            if punch_in_sentence:
                continue                                           # one punch per sentence: the first number wins
            out.append((i, 'num', 'a number'))
            punch_in_sentence = True
        elif t[:1].isupper() and not starts and low not in NOT_NAMES and not t.isupper():
            out.append((i, 'key', 'capitalised, not at the start of a sentence'))
        elif t.isupper() and len(t) > 1 and not starts and low not in NOT_NAMES:
            out.append((i, 'key', 'all caps (an acronym or a brand)'))
    return out


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    proj = skillenv.path_arg(sys.argv[1])
    path = os.path.join(proj, 'words.json')
    with open(path, encoding='utf-8') as fh:
        words = json.load(fh)
    found = guess(words)
    for i, mark, why in found:
        print(f'{mark:5} {words[i]["text"]:18} @{words[i]["start"]:.2f}   ({why})')
    openers = [bare(w['text']) for i, w in enumerate(words)
               if (i == 0 or words[i - 1]['text'][-1:] in '.?!') and bare(w['text'])[:1].isupper()
               and bare(w['text']).lower() not in NOT_NAMES]
    if openers:
        print('check by hand (a name that starts a sentence cannot be told from a normal word): ' + ', '.join(dict.fromkeys(openers)))
    print('emph is never guessed: add it by hand where a sentence has no number and no comment keyword.')
    if '--dry' in sys.argv:
        print('dry run: words.json not changed')
        return
    os.makedirs(os.path.join(proj, 'work'), exist_ok=True)
    shutil.copyfile(path, os.path.join(proj, 'work', 'words_premarks.json'))
    for i, mark, _ in found:
        words[i]['e'] = mark
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(words, fh, indent=1)
    print(f'{len(found)} marks written to {path}')


if __name__ == '__main__':
    main()
