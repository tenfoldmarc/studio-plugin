# type-wall demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Source:** the demo clip, 92 frames (3.07 s). Medium shot, the speaker sitting on the floor leaning on a wooden chest, clear wall above the speaker's head (head top y 328 to 340). The camera is not locked: it settles over the first 1.5 s (prep.py measures about 97 px of background movement across the slot).

**Spoken line:** "Everybody's talking about how Claude can edit your videos."

**CLIP block for this clip** (these are the values the packaged `build.py` ships with):

```python
PHRASES = [
    {'words': [(3, 'EVERY'), (11, 'BODY’S'), (21, 'TALKING')]},     # speech starts f3; "body's" is the dip at f11; "talking" f21
    {'words': [(42, 'CLAUDE')], 'hit': True},                       # the hard "Cl" at f42: wall punch, yellow row, low hit
    {'words': [(56, 'EDIT'), (65, 'YOUR'), (71, 'VIDEOS')]},        # the wall ends reading EDIT / YOUR / VIDEOS top to bottom
]
IN_FRAME = 0        # the clip opens on the wall
OUT_FRAME = None
KEEP = []
FS = 205
ACCENT_Y = None     # measured: yellow row letters y 165 to 314 (the hand-placed demo had them at 167 to 317)
HEAD_GAP = 14
XC = {}             # measured: rows 0 to 4 centred at x 470, 536, 200, 940, 1016
GROUND = ('#22261A', '#14160F', '#0B0C09')
INK = '#EEEADF'
ACCENT = '#FAE67A'
VOL_IN, VOL_HIT, VOL_SWAP = .28, .08, .16
```

**Beats:** rows whip in from alternating sides on the first frame; the wall builds EVERY / BODY'S / TALKING as the speaker says it; on "Claude" every row snaps to CLAUDE spreading out from the row above the speaker's head, the wall punches in and that row turns yellow; then EDIT, YOUR, VIDEOS build down the wall.

**How `demo.mp4` differs from what the package builds on the same clip** (the demo render was made before packaging):
- The chest and rug stay in front of the wall in the demo. That was a hand-drawn shape tracked to the moving camera frame by frame. The package does not ship that tracker: its `KEEP` shapes are fixed, for a still camera. On this clip the package would be run with `KEEP = []` (wall all the way down) or on a locked-off retake.
- In the demo the rows that will say TALKING are empty until the speaker says it. The package starts every row on the first word and turns rows to the 2nd and 3rd word as the speaker says them (the same way the demo builds EDIT / YOUR / VIDEOS).
- Row heights and word positions were typed by hand in the demo and are measured from the cutout in the package. The numbers land within 3 px for the yellow row.
- Word frames: the demo used 56 / 65 / 71 for edit / your / videos. `onsets.py` hears those words start at 53 / 62 / 67. Both read as on the word; the later ones are the ones the demo uses.

**Files:** `demo.mp4` (720x1280 preview with sound), `stills/type-wall-1.jpg` to `-3.jpg` (three beats from the demo in order; `-2.jpg` is the CLAUDE hit).
