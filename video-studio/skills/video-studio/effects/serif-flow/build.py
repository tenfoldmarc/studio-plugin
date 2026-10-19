#!/usr/bin/env python3
"""SERIF FLOW (explain): the picture cuts to a flat deep-ink card. A small [BRACKET CAPS] title sits on top, and a
process builds down the card one node at a time: serif italic nodes whose letters surface out of order, bold sans
nodes that cut on as they are said, thin lines drawing down between them. Then it cuts back to the speaker.

Run from the slot folder (effect.md has the full run order):
    python3 build.py      writes index.html   (SAFE=1 safe-zone guide, SFX=0 no sounds, CAPTIONS=0 accepted:
                                               the card's words ARE the effect, so they always draw)
"""
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
TITLE = ''          # small caps line on top, in brackets ("[ONE VIDEO]"). The speaker's own subject. '' = none
NODES = []          # top to bottom, 2 to 4 nodes, each a dict:
                    #   {'kind': 'serif', 'text': 'five variations', 'at': 0.4}        letters surface from `at`
                    #   {'kind': 'sans', 'parts': [('edits', 2.2), (' + posts', 2.9)]}  each part cuts on at its time
                    # The speaker's own words, shortened. A line draws down just before each node after the first.
                    # Serif nodes alternate with sans nodes in the look. Required
T_IN = 0.0          # when the card cuts in (slot seconds). The slot should start on a cut of the reel or a word
T_OUT = None        # when it cuts back to the speaker. None = the end of the slot
SERIF = 118         # serif node size, px
SANS = 82           # sans node size, px
SOUND = 0.22        # volume of the soft whoosh as the card cuts in. 0 = silent
# ==== END CLIP ====

ORDER = [3, 0, 5, 1, 7, 2, 6, 4, 9, 8, 11, 10, 13, 12, 15, 14, 17, 16, 19, 18]   # fixed letter order: no random


def main():
    s = V.Slot()
    print('words: ' + s.word_list())
    if not NODES or len(NODES) < 2:
        V.die('write NODES in the CLIP block: 2 to 4 steps of the process the speaker describes, with their times')
    t_out = T_OUT if T_OUT is not None else s.dur
    # fit the stack between the safe lines: title 56 + nodes + lines 124 each
    def height(k):
        return (56 if TITLE else 0) + sum((SERIF if n.get('kind') == 'serif' else SANS) * k for n in NODES) + 124 * (len(NODES) - 1)
    k = min(1.0, (V.SAFE_BOTTOM - V.SAFE_TOP - 80) / height(1))
    top = int(960 - height(k) / 2)
    widest = max(len(n.get('text', '') or ''.join(t for t, _ in n.get('parts', []))) * (SERIF * .42 if n.get('kind') == 'serif' else SANS * .55) for n in NODES)
    k = min(k, (1080 - 2 * V.SAFE_RIGHT) / max(widest, 1))
    p = V.Page(s)
    ink = STYLE['ink']
    p.css.append(V.style_css(STYLE) + f'''
.sfcard{{position:absolute;inset:0;background:{STYLE["card"]}}}
.sf{{position:absolute;left:0;right:0;top:{top}px;display:flex;flex-direction:column;align-items:center}}
.sf .vg-word,.sf .vg-serif,.sf .vg-small{{text-shadow:none}}
.sf .ttl{{font-size:{int(34 * k)}px;letter-spacing:.01em;margin-bottom:{int(22 * k)}px;font-weight:{STYLE["big_weight"]}}}
.sf .ln{{width:2px;height:{int(84 * k)}px;background:{ink}BF;margin:{int(20 * k)}px 0;transform-origin:50% 0}}''')
    card = p.nid('cd')
    p.html.append(f'<div id="{card}" class="sfcard"></div>')
    p.show(f'#{card}', T_IN, t_out)
    if SOUND:
        p.sound('whoosh-short', T_IN, SOUND)
    parts = []
    if TITLE:
        tid = p.nid('t')
        parts.append(f'<div id="{tid}" class="ttl vg-word">{V.esc(TITLE.upper())}</div>')
        p.enter(f'#{tid}', T_IN, {'y': 10}, {'y': 0}, .2, t_out=t_out)
    snaps = []
    for n, node in enumerate(NODES):
        first_at = node['at'] if node.get('kind') == 'serif' else node['parts'][0][1]
        if n:
            lid = p.nid('l')
            parts.append(f'<div id="{lid}" class="ln"></div>')
            p.hidden.append(f'#{lid}')
            p.js.append(f"tl.fromTo('#{lid}',{{autoAlpha:1,scaleY:0}},{{autoAlpha:1,scaleY:1,duration:.22,ease:'power2.out',immediateRender:false}},{V.T(max(T_IN, first_at - .24)):.3f});")
            if t_out < s.dur - .02:
                p.js.append(f"tl.set('#{lid}',{{autoAlpha:0}},{V.T(t_out):.3f});")
        if node.get('kind') == 'serif':
            text = V.cased(node['text'], STYLE['case'])
            nid = p.nid('n')
            spans = ''.join(f'<span id="{nid}l{c}">{V.esc(ch)}</span>' for c, ch in enumerate(text))
            parts.append(f'<div class="vg-serif" style="font-size:{int(SERIF * k)}px">{spans}</div>')
            order = [c for c in ORDER if c < len(text)] + [c for c in range(len(text)) if c not in ORDER]
            reveal = max(.12, min(.7, .05 * len(text), t_out - node['at'] - .25))   # always finished on screen
            for r, c in enumerate(order):
                p.enter(f'#{nid}l{c}', node['at'] + r * reveal / len(text), {'filter': 'blur(6px)'}, {'filter': 'blur(0px)'}, .18, 'none', t_out=t_out)
            snaps.append(node['at'] + reveal + .1)
        else:
            inner = ''
            for m, (piece, at) in enumerate(node['parts']):
                pid = p.nid('p')
                inner += f'<span id="{pid}">{V.esc(V.cased(piece, STYLE["case"]))}</span>'
                p.show(f'#{pid}', at, t_out)
            parts.append(f'<div class="vg-word" style="font-size:{int(SANS * k)}px;font-weight:{STYLE["big_weight"]};letter-spacing:-.04em;white-space:pre">{inner}</div>')
            snaps.append(node['parts'][-1][1] + .1)
        print(f'  node {n + 1}: {node.get("text") or "".join(t for t, _ in node["parts"])!r} from {first_at:.2f}s')
    p.html.append(f'<div class="sf">{"".join(parts)}</div>')
    print(f'  card {T_IN:.2f}s to {t_out:.2f}s, scale {k:.2f}, top y {top}')
    p.write()
    print('snapshot at: ' + ','.join(f'{t:.2f}' for t in [T_IN + .1] + snaps + [max(0, t_out - .05)]))
    s.hide_hint([(T_IN, t_out)])


if __name__ == '__main__':
    main()
