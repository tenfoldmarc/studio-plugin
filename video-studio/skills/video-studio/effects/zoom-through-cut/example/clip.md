# zoom-through demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Sources (two shots, 1080x1920):** shot A, 67 frames (wide, sitting on the floor by the armchair). Shot B, 74 frames (wide, in the armchair). 141 frames in total, cut on frame 67.

**Spoken line:** "And you can get the cool girl aesthetic like this. / Or you can get the cool dude aesthetic ..."

**CLIP block that made `demo.mp4`:**

```python
CUT = 67                  # clip.json cut_frames
HALF = 9                  # 18 transition frames, 58 to 75
POINT_A = (480, 1212)     # hand-picked on the speaker's black tee, last frame of shot A
POINT_B = (516, 1200)     # hand-picked on the speaker's tee, first frame of shot B
DEPTH = 80.0
SHARP = 2.4
ROLL = 5.0
CREEP_A = 1.03
CREEP_B = 1.04
GRADE_A = 'girl'          # warm, soft
GRADE_B = 'dude'          # dark, cool
CAP_A = {'style': 'girl', 'top': 1126,
         'lead': [(0.42, 'you'), (0.52, 'can'), (0.64, 'get'), (0.80, 'the')],
         'punch': [(0.92, 'cool'), (1.10, 'girl')],
         'tail': [(1.32, 'aesthetic')]}
CAP_B = {'style': 'dude', 'top': 1150,
         'lead': [(2.29, 'or'), (2.55, 'you'), (2.67, 'can'), (2.79, 'get'), (2.95, 'the')],
         'lead_rides': True,
         'punch': [(3.11, 'cool'), (3.31, 'dude')],
         'tail': [(3.53, 'aesthetic')]}
WHOOSH_VOL = 0.30
```

The packaged `build.py` ships with the same caption words and timings, but with `POINT_A`, `POINT_B`, both `top` values and both grades set to `None` (measured by prep.py, footage left ungraded), which are the right defaults for a new clip.

**Beats:** the "cool girl" block builds word by word over shot A; on frame 58 the camera starts to dive into the speaker's tee and the block rushes past the lens; frame 67 (the cut) is dark with shot B as a small bright burst at the point; shot B opens out and brakes into place by frame 76 with "or you can get the" riding in with the picture; "cool dude" rises on its words.

**What differs from the packaged effect:** `demo.mp4` is the render from before packaging. Around shot B, while it was smaller than the frame, that build used mirrored copies of the room, darkened. The packaged `bake.py` replaces them with the picture's own border colours stretched outward along the zoom rays and fading to dark, so a fresh run of this clip will show soft rays there instead. Everything else (camera curve, blur, portal, captions, whoosh) is the same code path.

**Stills:** `stills/zoom-through-1.jpg` shot A with its caption, `-2.jpg` the pass-through, `-3.jpg` shot B landed.
