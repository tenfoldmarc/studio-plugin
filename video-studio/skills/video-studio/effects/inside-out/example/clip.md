# Inside Out: the approved demo (maker side only)

`demo.mp4` and `stills/` show Marc, and the demo's fill is a clip of Marc too (the lab used another of his takes).
They are for the maker and the importer, never shipped to buyers, never shown as the buyer's result. The package
never uses a person as the fill: the buyer gives b-roll of a place, a product or a screen.

Demo clip: aesthetics-reel c1 (1080x1920), medium-wide shot on the floor by the sofa, still camera, 92 frames
(3.07 s), lab version v2 (one clip, no cuts; v1, the fast montage, was "too much happening at the same time").
Spoken line: "Everybody's talking about how Claude can edit your videos."

The lab ended the demo on the flipped room (no hand-back). The package eases the real room back over the last 14
frames by default (`T_OUT = 'auto'`); `T_OUT = 'cut'` gives the demo's ending when the reel cuts away right after.

CLIP block values for this clip (package build.py):
```
FILL = 'fill/<buyer b-roll>.mp4'   # the lab used a take of Marc here; the package needs person-free b-roll
T_IN = 'Claude'          # the /k/ burst, frame 43 (Whisper put it 2 to 3 frames early)
T_FLIP = 'videos'        # frame 73
T_OUT = 'cut'            # the demo holds the flipped room to the last frame
```
Everything else default (cream line 2 px in / 3 px out, keep zone and iris measured from the head).
