# glass-type: the demo clip (maker-side only)

`demo.mp4` and `stills/` show Marc in his own room. They are for the maker and the main session only: they never ship
to buyers and never go on a sales page.

- Source: `reel-edit/aesthetics-reel/src/c4.mp4` from 33.28 s, 108 frames (3.6 s), medium shot, armchair, window and
  wall lamp behind, tripod (4 px of drift, read as handheld and tracked).
- Line: "And the funniest thing is I suck at DESIGN and I'm not a tech bro at all."
- This is the round-3 package run on the lab demo clip (`pack/tests/glass-type/demo`), not the lab render: the word
  is now level (the lab version sloped with the wall) and reads over the window (dark glass rim, rim light, backing
  shade; the lab version lost I, G and N against the window).

CLIP block values used (everything else default):
```
TEXT = 'DESIGN'
T_IN = 'auto'        # found "design" in words.json, audio onset 1.61 s -> starts frame 47
```
What measure chose: medium shot, box x 64..958, y 596..795 (199 px tall) above his head and across the window, level
(the crown moulding leans 17 deg but the lines at the word's height do not agree enough to follow), plain-wall light
values (backing 0.17, dark rim 0.39, rim light 0.92, shadow 0.24).
