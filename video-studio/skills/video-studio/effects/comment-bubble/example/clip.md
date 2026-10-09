# Demo clip

> The demo render and stills this note mentions (`demo.mp4`, `stills/`) are not part of the skill. What carries over to a new clip is the CLIP block and the numbers.

**Source:** handheld close-up selfie, 3.5s, 105 frames (last 0.7s is a freeze of the final frame).
**Line:** "So if you want it, just comment ads and I'll send you the link."
**Files:** `demo.mp4` (720x1280 phone copy of the render), `stills/` (typed keyword, posted comment + typing dots, final thread).

## CLIP values
These are the defaults that ship in `build.py`, so a fresh slot of this clip rebuilds the demo without edits.

```
KEYWORD = 'ADS'        REPLY_TEXT = 'Sent you the link'   CHIP_TEXT = 'Open link'   USER_NAME = 'you'
T_IN = 0.50    T_FOCUS = 0.93   T_TYPE = 1.26   KEY_GAP = 0.09   T_SEND = 1.57
T_DOTS = 1.88  T_REPLY = 2.05   T_LINK = 2.39   T_OUT = None
SCALE = 1.3    CHIN_Y = None    CHIN_GAP = 20   DROP = 'auto'    X_CENTER = None   PUSH = 'auto'   PUSH_MAX = 1.12
AVATAR_FRAME = None    AVATAR_BOX = None    GRADE = 'none'    SEAT = 1.0
```

## What the packaged build does with it
`layout: scale 0.98  reply inline  thread x 48..863  y 1215..1456  chin 1270 -> 1195 after x1.116 lift`

- The close-up leaves 186px under the speaker's chin, so the 1.3x request shrinks to 0.98 and the plate lifts 11.6%. The demo was hand-set to 1.0 and a 12% lift: same picture.
- measure.py's suggested times for this clip came out within 0.06s of the hand-tuned ones above (T_TYPE, T_SEND and T_LINK identical).

## Differences from the demo render
- The thread is centred under the speaker's head (x 48..863); the demo was hand-placed at x 96..949.
- `GRADE` is `'none'`; the demo used `contrast(1.05) saturate(.9) brightness(.98)`.
- Keyword letters in the field are tracked 2px wider.
- The demo's avatar was a hand-picked frame (90); the default is the last frame.
