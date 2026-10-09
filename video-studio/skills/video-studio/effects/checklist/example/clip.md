# checklist demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Source:** the demo clip, 128 frames (4.25 s). Wide shot, the speaker sitting on the floor, wall free above the speaker's head. Described as a static camera; prep.py measures 15 px of background drift (it sways for the first second), still inside the glass limit of 24 px.

**Spoken line:** "All you need to do is drop your clips, trigger the skill, and Claude takes care of it all for you."

**CLIP block that made `demo.mp4`** (the packaged `build.py` ships with these TITLE / ROWS / frames but with `CARD_BOX = 'auto'`, `LAYER = 'auto'`, `GRADE = ''`, `VIGNETTE = 0`, `PUSH = 1.0` as the new-clip defaults; with the block below it rebuilds the demo timeline line for line, checked against the index.html):

```python
TITLE = 'All you need to do'
ROWS = [
    ('Drop your clips',        28, 39),    # "drop" vowel f30 -> say 28; "clips" vowel f40 -> tick 39
    ('Trigger the skill',      55, 69),    # "trigger" vowel f58 (said 55, onsets.py suggests 56); "skill" vowel f70 -> tick 69
    ('*Claude* does the rest', 83, 97),    # "Claude" vowel f84 (onsets.py suggests 82); "care" vowel f98 -> tick 97
]
F_IN = 2            # speech starts at frame 2
F_DONE = 108        # "(takes care of it) ALL"
F_OUT = None        # the clip ends on the finished card
CARD_BOX = (100, 256, 880, 649)    # hand-placed; CARD_BOX = 'auto' gives (104, 256, 873, 644), scale 0.99
LAYER = 'behind'
OVERLAP = 40        # the speaker's cap top is y 855 to 870, the card bottom is y 905
GLASS = 'auto'      # -> glass
ACCENT = '#FAE67A'
GRADE = 'contrast(1.05) saturate(.95) brightness(.99)'
VIGNETTE = .30
PUSH = 1.03
```

**Beats:** card tilts in on "All" (f2), header + three empty rings by f22; row text lands on "drop" / "trigger" / "Claude"; checks pop on "clips" / "skill" / "care"; on "all" the pill snaps to yellow "3 of 3", sheen, edge glow, card settles flat.

**Files:** `demo.mp4` (720x1280 preview with sound), `stills/checklist-1.jpg` (first tick mid-pop), `-2.jpg` (third tick), `-3.jpg` (finished card).
