#!/usr/bin/env python3
"""DOT COUNTER (explain): a row of dots pops in over the chest, one per item, when the speaker says how many things
are coming ("3 things", "5 steps"). Filled dots are done, rings are still to come, so a later slot can show the
progress (two of three filled on step two).

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds; CAPTIONS=0 accepted and
                                               ignored: the effect draws no words)
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
COUNT = None        # how many dots (2 to 8). None = the number the speaker says in the slot (a digit or one to eight)
FILLED = None       # how many of them are filled. None = all of them (the "here come N things" beat).
                    # Fewer = progress: step two of three is COUNT = 3, FILLED = 2
T_IN = None         # when the first dot pops (slot seconds). None = when the number is said
STEP = 0.08         # seconds between dots
T_OUT = None        # when the row cuts out (slot seconds). None = 0.6 s after the counted word ends, or the slot end
Y = None            # centre of the row, screen px. None = the chest band from layout.json
DOT = 46            # dot size, px
SOUND = 0.15        # volume of the soft click on each dot. 0 = silent
# ==== END CLIP ====

WORDS = {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8}


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    print(s.where())
    said = next((w for w in s.words if re.fullmatch(r'[2-8]', V.bare(w['text'])) or V.bare(w['text']).lower() in WORDS), None)
    count = COUNT
    if count is None:
        if said is None:
            V.die('nobody says how many things are coming in this slot (2 to 8), so Dot Counter has nothing to count')
        t = V.bare(said['text']).lower()
        count = int(t) if t.isdigit() else WORDS[t]
    count = max(2, min(8, int(count)))
    filled = count if FILLED is None else max(0, min(count, int(FILLED)))
    t_in = T_IN if T_IN is not None else (said['start'] if said else .1)
    if T_OUT is not None:
        t_out = T_OUT
    else:
        k = s.words.index(said) if said in s.words else None
        end = s.words[k + 1]['end'] if k is not None and k + 1 < len(s.words) else t_in + .4
        t_out = min(s.dur, end + .6)
    y = s.band(DOT + 20, Y)
    if y is None:
        V.die('there is no room under or above the face on this clip for the dots')
    p = V.Page(s)
    ink = STYLE['ink']
    p.css.append(f'''
.dc{{position:absolute;left:0;right:0;display:flex;justify-content:center;gap:{int(DOT * .35)}px;transform:translateY(-50%)}}
.dc span{{width:{DOT}px;height:{DOT}px;border-radius:50%;box-shadow:0 2px 14px rgba(0,0,0,.3)}}
.dc .f{{background:{ink}}}
.dc .o{{border:{max(3, DOT // 14)}px solid {ink}}}''')
    i = p.nid('dc')
    p.html.append(f'<div id="{i}" class="dc" style="top:{y}px">' +
                  ''.join(f'<span id="{i}d{k}" class="{"f" if k < filled else "o"}"></span>' for k in range(count)) + '</div>')
    p.show(f'#{i}', t_in, t_out)
    for k in range(count):
        at = t_in + k * STEP
        p.enter(f'#{i}d{k}', at, {'scale': .2}, {'scale': 1}, .16, 'back.out(3)')
        if SOUND:
            p.sound('click-soft', at, SOUND)
    print(f'  {count} dots ({filled} filled) from {t_in:.2f}s, centre y {y}, out at {t_out:.2f}s')
    p.write()
    print(f'snapshot at: {t_in + .03:.2f},{t_in + count * STEP + .2:.2f},{max(0, t_out - .05):.2f}')
    s.hide_hint([(t_in, t_out)])


if __name__ == '__main__':
    main()
