# Demo clip (the approved lab render: demo.mp4, stills/)

Maker side only: `demo.mp4` and `stills/` show Marc. Do not ship them to buyers or show them as the buyer's result.
`doodle-library.jpg` (the lab's 24-doodle sheet on a chalkboard, no person) is safe to show; clock, dollar and bulb
were added in the package and are not on it.

**Source:** DJI 4K wide, `dji_mimo_20261007_170446...video.MP4` from 11.96s, 180 frames (6.0s). Full body on the green
sofa, low still camera, grey wall behind. Lab render made by the old one-file frame loop (not re-rendered with the
packaged code; the packaged defaults below are its cues).
**Line:** "Just ask my girlfriend, I suck at video editing and I'm not techy at all, yet you can get results like this."

## What it did
heart on "girlfriend" right of his head; clapper on "suck", scribbled out on "video"; chip on "not", crossed on
"techy"; the outline rubbed out and the room came back before "yet"; finale on "results": double line (cream + butter),
rays round his body, a crown above the cap, five small stars. Held to the last frame (the demo ended the reel).

## CLIP block values (the shipped defaults in build.py)
```python
DOODLES = [
    cue('girlfriend', 'heart'),
    cue('suck', 'clapper', cross='video'),
    cue('not', 'chip', cross='techy'),
    cue('results', 'crown', finale=True),
]
OUTLINE = 'auto'; PALETTE = 'classic'; INK = ACCENT = ACCENT2 = None; DIM = 'auto'
HOLD_MAX = 2.8; SPARKLE = 'auto'; IN_FRAME = 3; OUT_FRAME = -4     # the demo itself held to the end (OUT_FRAME=None)
```
Lab timings for reference (seconds on the clip): girlfriend 0.56, suck 1.16, video 1.82, not 2.66, techy 3.06,
results 4.88. The lab placed every doodle by hand (offsets from the head); the package places them automatically.
