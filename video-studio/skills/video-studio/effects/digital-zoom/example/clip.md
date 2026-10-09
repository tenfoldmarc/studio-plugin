# Demo clip

**Source:** the demo clip, 138 frames (4.6s). Wide shot, the speaker lounges on the floor by the green sofa, still camera, 1728x3072 master (`aroll_hi.mp4`, lossless to 1.6x).
**Line:** "and you don't need to be techy or know anything about video editing in order to use it."

## Onsets read off the audio (onsets.py), not Whisper
| word | Whisper | real frame |
|---|---|---|
| "and" (first word) | 0.05s | f1 |
| "techy" | 0.99s (f30) | t-burst f32.5, stressed vowel f35.5 |
| "video" | 2.77s (f83) | "v" f83.5, stressed vowel f86 |
| "editing" | 3.11s (f93) | f95 |
| "in" (order to use it) | 3.47s (f104) | f108.5 |

## CLIP block values (they are still the defaults in build.py)
```python
ZOOMS = [
    zoom(F(1), F(37), 1.62, 'creep'),       # starts on "and", motion dies on the vowel of "TECH-y" (f35 + 2)
    zoom(F(83), F(86), 2.26, 'snap'),       # leaves on the "v", peak lands on the vowel of "VI-deo"
    zoom(F(108), F(117), 1.0, 'pull'),      # leaves on "in", wide again before "order" ends
]
EYE = (540, 640)
FOLLOW = 5
AIM = None
MAX_UPSCALE = 1.5
CAPS = [
    (54, [(1000, 'sm', [(8, 'you', ''), (13, 'don’t', ''), (18, 'need', ''), (23, 'to', ''), (26, 'be', '')]),
          (1082, 'big', [(33, 'techy', 'y')])]),
    (83, [(1000, 'sm', [(56, 'or', ''), (59, 'know', ''), (65, 'anything', ''), (78, 'about', '')])]),
    (108, [(1062, 'lg', [(86, 'video', '')]), (1228, 'lg', [(95, 'editing', 'y')])]),
    (None, [(1000, 'sm', [(110, 'in', ''), (113, 'order', ''), (120, 'to', '')]),
            (1082, 'big', [(123, 'use', ''), (130, 'it.', '')])]),
]
WHOOSH = 0.26
GRADE = 'contrast(1.06) saturate(.93) brightness(.98)'
```

## What the camera does with them
- f1 to f37: creep 1.0x to 1.62x, eyes drift from where they were to (540, 640), crisp all the way.
- f83 to f86: snap to a 2.35x peak (2.26 + 4% overshoot), frames 84 and 85 carry up to 136px of zoom blur at the corners, f86 is sharp, recoil to 2.26 by f90, then a slow push.
- f108 to f117: pull back, wide and sharp by f114, exactly 1.0x on the last frames.
- 2.35x on a 1.6x-lossless master is a 1.47x upscale: inside `MAX_UPSCALE`, nothing was capped.
- Stills: 1 = the creep landed ("techy"), 2 = the travelling frame of the snap (f85), 3 = the snap held ("video editing").
