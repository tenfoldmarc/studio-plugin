#!/usr/bin/env python3
"""STAT STACK (proof): a number the speaker says lands huge over the chest, and a tiny caps line under it swaps on
the words that follow ("14,000" / FOLLOWERS / IN 7 DAYS). Hard cuts, no bounce: the size does the work.

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted:
                                               the number IS the effect, so it always draws)
"""
import re

import vgfx as V

# ==== STYLE (the reel's look wins: match this block to the reel's caption style before building) ====
# Fonts must be families that assets/fonts/fonts.css provides. The defaults are the Viral Guy look: cream Inter
# Tight with tight tracking, Inter for small labels, Instrument Serif italic as the second voice, deep ink cards.
STYLE = dict(
    font='Inter Tight',            # main words
    weight=700,
    tracking=-0.035,               # letter spacing of the main words, em
    big_weight=800,                # the huge words (numbers, the word that matters)
    big_tracking=-0.055,
    case='as-said',                # 'as-said', 'lower' or 'upper'
    small_font='Inter',            # small labels, chips, sub lines
    small_weight=500,
    serif_font='Instrument Serif', # the second voice (Serif Flow nodes)
    serif_italic=True,
    ink='#E9DAC8',                 # text colour (cream). White reels: '#FFFFFF'
    accent=None,                   # colour of the huge words; None = same as ink. Never orange
    card='#101B1B',                # full-frame card / dark fills (deep ink)
    shadow=True,                   # soft shadow under words that sit on footage
)
# ==== END STYLE ====

# ==== CLIP (edit this) ====
NUMBER = None       # the big text, exactly as said ("14,000", "$3,000", "100%", "7 days"). None = the first spoken
                    # word with a digit in it. Never a number the speaker did not say
T_IN = None         # when it lands (slot seconds). None = when that word starts
SUBS = None         # the small caps lines under it: [(text, seconds), ...], each replaces the one before at its
                    # seconds. Words the speaker says, shortened ("FOLLOWERS", "IN 7 DAYS"). None = the one or two
                    # words said right after the number. [] = no line
T_OUT = None        # when it cuts out (slot seconds). None = the end of the slot
Y = None            # centre of the number, screen px. None = the chest band from layout.json, clear of the chin
SIZE = 176          # px of the number; long numbers shrink to fit the width by themselves
# ==== END CLIP ====


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    print(s.where())
    num_word = None
    number = NUMBER
    if number is None:
        num_word = next((w for w in s.words if re.search(r'\d', w['text'])), None)
        if num_word is None:
            V.die('nobody says a number in this slot, so there is nothing for Stat Stack to show')
        number = V.bare(num_word['text'])
    else:
        digits = re.search(r'\d+', number)
        num_word = s.find(re.escape(digits.group() if digits else number.split()[0]))
    t_in = T_IN if T_IN is not None else (num_word['start'] if num_word else .1)
    subs = SUBS
    if subs is None:
        subs = []
        if num_word:
            k = s.words.index(num_word)
            # what the number counts: up to two words said right after it, stopping at punctuation or a small word
            weak = {'the', 'a', 'an', 'to', 'of', 'and', 'that', 'for', 'can', 'in', 'on', 'with', 'is', 'i', 'you', 'it'}
            took = []
            for w in s.words[k + 1:k + 3]:
                if w['start'] - s.words[k]['end'] > 1.2 or V.bare(w['text']).lower() in weak:
                    break
                took.append(w)
                if w['text'][-1:] in ',.?!':
                    break
            if took:
                subs.append((' '.join(V.bare(w['text']) for w in took).upper(), took[0]['start']))
    t_out = T_OUT if T_OUT is not None else s.dur
    size = int(min(SIZE, 880 / max(len(number) * .56, 1)))
    y = s.band(size + 60, Y)
    if y is None:
        V.die('there is no room under or above the face on this clip for the number')
    p = V.Page(s)
    p.css.append(V.style_css(STYLE) + '''
.st{position:absolute;left:0;right:0;text-align:center;transform:translateY(-50%)}
.st .sub{position:absolute;left:0;right:0;font-size:30px;letter-spacing:.01em}''')
    i = p.nid('st')
    sub_html = ''
    for k, (text, at) in enumerate(subs):
        sub_html += f'<div id="{i}s{k}" class="sub vg-word" style="font-weight:{STYLE["big_weight"]}">{V.esc(text)}</div>'
    p.html.append(f'<div id="{i}" class="st" style="top:{y}px"><div class="vg-big" style="font-size:{size}px">'
                  f'{V.esc(V.cased(number, STYLE["case"]))}</div><div style="position:relative;height:40px;margin-top:14px">{sub_html}</div></div>')
    p.show(f'#{i}', t_in, t_out)
    for k, (text, at) in enumerate(subs):
        end = subs[k + 1][1] if k + 1 < len(subs) else t_out
        p.show(f'#{i}s{k}', max(at, t_in), end)
        print(f'  sub line {text!r} at {at:.2f}s')
    print(f'  number {number!r} at {t_in:.2f}s, {size}px, centre y {y}; out at {t_out:.2f}s')
    p.write()
    print(f'snapshot at: {t_in + .1:.2f},' + ','.join(f'{at + .1:.2f}' for _, at in subs) + f',{max(0, t_out - .05):.2f}')
    s.hide_hint([(t_in, t_out)])


if __name__ == '__main__':
    main()
