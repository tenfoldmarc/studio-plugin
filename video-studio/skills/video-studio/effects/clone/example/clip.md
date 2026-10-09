# clone: the demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Source:** wide shot, the speaker sits on the front edge of the green sofa, camera on a gimbal on the table in front of the speaker (it crept 13 px sideways and 7 px up over the clip). 132 frames (4.4 s).
**Spoken line:** "you need edits like this, like this, or like that."
**What happens:** clone L springs up behind the sofa on the first "like THIS" (vowel at f37), clone R on the second (f69), both snap into sync with the speaker and flash-pop on "or like THAT" (f115). They stay to the last frame (stand-alone demo, no exit).

`demo.mp4` is the phone copy of the render, `stills/` are frames 48, 80 and 122 of it.

## CLIP block of the demo (this is also what ships at the top of `build.py`)
```python
CLONES = [
    dict(id='L', word_f=37, x=287, top=520, scale=.64, lag=6),
    dict(id='R', word_f=69, x=781, top=520, scale=.64, lag=9),
]
SYNC_F = 115
EXIT_F = None
OCCLUDER_LINE = [(0, 998), (42, 998), (52, 940), (240, 960), (880, 966), (1080, 968)]   # pillow, sofa corner, sofa back
LIGHT_FROM = 'right'
CAP_X = 540
CAPS = [
    (1078, [('you', 1, ''), ('need', 3, ''), ('edits', 13, '')], 24),
    (1078, [('like', 25, ''), ('this', 36, 'y')], 54),
    (1078, [('like', 57, ''), ('this', 68, 'y')], 88),
    (1052, [('or', 91, ''), ('like', 104, '')], None),
]
PUNCH = ('that', 115, 1118, None)
ACCENT = '#FAE67A'
VIGNETTE = 0.0      # the demo used 0.22 (stand-alone clip)
```

## Numbers the tools reported on this clip
- `prep.py`: head anchor (540, 442), head 172 x 294 px, cutout x 128 to 1000 (widest at frame 67, both hands out).
- Word hits: this=37, this=69, or=91, that=116 (Whisper had the first two 0.2 s early).
- `bake.py`: drift 13.2 px sideways / 6.9 px vertical, occluder snapped on 459 columns (the speaker covers the rest), clone L seen x 21 to 576, clone R 515 to 1069.

## Why the layout looks like this
The speaker is 750 px wide with the speaker's hands out, so there is no room for a same-size copy next to the speaker. The clones stand behind the sofa back at 0.64 (what a person about 70 cm further from this lens measures), heads beside and a little below the speaker's, and the sofa edge hides everything under their hips. On "or" the speaker's raised hands cover the clones' faces for about 10 frames: correct depth, left alone.

Re-running the packaged effect on this clip with the block above reproduces the demo (checked during packaging).
