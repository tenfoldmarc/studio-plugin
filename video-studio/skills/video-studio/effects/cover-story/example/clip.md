# Cover Story: the approved demo (maker side only)

`demo.mp4` and `stills/` show Marc. They are for the maker and the importer, never shipped to buyers, never shown as
the buyer's result.

Demo clip: 4K DJI, medium shot on the green sofa, still camera, 169 frames (5.63 s). Spoken line:
"I'm terribly sorry to say, but video editors are absolutely cooked."

The demo was built in the lab with Didot / Futura on Marc's Mac. The package uses the shipped stand-ins
(DM Serif Display for the masthead, Playfair Display italic for the cover line, Figtree for the tracked caps), so a
package render of the same clip has a slightly heavier masthead; layout, timing and motion are the same.

CLIP block values for this clip (package build.py):
```
T_IN = 'video'          # measured onset 1.83 s (Whisper said 1.66)
T_LAND = 4.26           # the "k" of "cooked" (Whisper put the word 0.44 s early, so seconds here)
OUT = 'cut'             # the demo holds the finished cover to the last frame
MASTHEAD = 'EDIT'
LINES = [
    ('THE AI\nISSUE', 'label-left', None),
    ('TERRIBLY SORRY\nTO SAY', 'label-right', None),
    ('COVER STORY', 'kicker', None),
    ('Video editors\nare *cooked*', 'main', None),
]
```
Everything else default. build.py chose BEHIND: head top 406 after the push, bottom 20% of the caps hidden, letters
D and I over the head, cream type (wall brightness 130).
