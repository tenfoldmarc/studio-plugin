# couch-wall

**What it does:** the wall behind the speaker turns into a grid of the speaker's own reel covers. The columns flick up from behind the speaker (and behind the sofa, chair or floor), drift upward like a feed, then sink back and the real room returns.
**Job:** explain / proof ("look at everything I posted", "they all do the same thing", "my last 20 videos"). Works anywhere in a video: set `F_IN` and `F_OUT` and the frames before and after are untouched a-roll.
**Trigger phrases:** "put my reels as a grid on the wall behind me", "turn the wall into my profile grid", "couch wall".

## The covers are the user's own
Ask for a folder of their reel cover images (jpg / png / webp, at least 4, 9 or more looks best; 9:16 covers are cropped to 3:4 tiles). Copy them into `covers/` in the slot. The effect ships no covers. Tiles carry no numbers unless the user gives real view counts for `COUNTS`: never estimate or round up a count.

## Footage it needs, and where it fails
- ONE continuous shot (no internal cuts), 3 to 6 s, wide or medium, with a plain wall filling a good part of the upper frame. Camera still or gently moving (it is tracked).
- At least 1.5 s between `F_IN` and `F_OUT` so the grid can be read.
- Fails on: a tight selfie (no wall to cover); furniture, floor or clothes close to the wall colour (white pillow on a white wall, beige sofa on a beige wall: the grid leaks onto them until you draw them in `IN_FRONT`); patterned wallpaper, brick, bookshelves or a window as the "wall" (it is not one colour, so `auto` finds little: use `FURNITURE = 'off'` with a `WALL` rectangle); a shot that cuts; hair or fast hands that the cutout loses.
- Things hanging on the wall (pictures, lamps, a clock) are covered by the grid on purpose. Anything that reaches the bottom of the frame (sofa, chair, floor, door frame, a floor lamp) stays in front.

**Slot inputs:** cutout yes (`assets/subject.webm`, made by `fx_new.py` with `_shared/rvm_cut.py`), `aroll_hi` no. Python: numpy, scipy, Pillow. No OpenCV, no extra packages.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `COVERS` | folder with the user's cover images | default `covers` inside the slot; file-name order is grid order |
| `COUNTS` | optional real view counts per file | from the user's own insights; `{}` = no numbers, no play icons |
| `TOP_BY_COUNT` | best covers take the top row | only matters with `COUNTS` |
| `F_IN` | frame the grid has landed on | `onsets.py`: onset of the word |
| `F_OUT` | frame the room is fully back, or `None` | onset of a later word; `None` = grid stays to the end |
| `CAPS`, `CAP_Y` | the effect's own caption words and their height | words the speaker says, frames from `onsets.py`; `None` = measured, check the yellow box |
| `WALL` | rectangle the grid may use | `None` = whole frame; read px off `work/wall.jpg` (shown at half size) |
| `FURNITURE` | `'auto'` or `'off'` | `auto` first; `off` + `WALL` when the wall is not one plain colour |
| `IN_FRONT`, `BEHIND` | hand-drawn shapes kept in front of / forced behind the grid | default `[]`; points in px on the reference frame |
| `WALL_TOL`, `EDGE_CHOKE` | colour tolerance of the wall; px the furniture edge is pulled in | 1.0 and 1; see traps |
| `COLS`, `SCROLL`, `CROP_Y` | tiles across, drift px per second, which part of a tall cover is kept | 3, 190, 0.42 |
| `LOOK`, `SHADOW` | tile dimming, shadow of speaker and furniture on the grid | lower `LOOK[0]` in a dark room |
| `VOICE`, `TRACK_YMAX`, `REF`, `SOUNDS` | the speaker's audio on/off, track region, measuring frame, sounds | defaults |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the effect's caption words. `SFX=0` drops its sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: ask the buyer for a folder of their own reel cover images (their saved covers, or covers exported from their profile) and copy them into <slot>/covers/ (fx_new.py --buyer-files <folder> does the copy). No covers from the buyer = no Couch Wall: leave it out and say so
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # copy the user's reel covers into ./covers  (create the folder; 4 or more images); 1. word onsets as frames -> F_IN, F_OUT, CAPS in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. covers, camera track, wall matte, fg.webm (about 3 min). LOOK at work/wall.jpg. If the cyan area is wrong, edit WALL / IN_FRONT / BEHIND / WALL_TOL, then
PY "SK/scripts/fx_run.py" "<slot>" prep.py wall      # re-measure only (20 s); repeat until right, then run. prep.py once more WITHOUT "wall" so fg.webm is baked from the final matte
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # 3. page with the safe guide
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.5,1.0,1.5,2.0,2.5,3.0
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Any python with numpy, scipy and Pillow works in place of the venv path. `build.py` itself needs no packages.

## What to look at in the final frames
- The frame of `F_IN` and the one before: the columns are up and almost still on the word. The frame of `F_OUT`: plain room, no tile left.
- Furniture edge at full size: no tile on the sofa, chair or floor, no strip of real wall left between furniture and grid, no bright rim.
- The speaker's outline: no wall colour showing through hair, fingers or a fast sleeve; no tile inside the speaker's body.
- Caption words on the speaker's chest, never on the speaker's face or hands, inside the safe zone (top 220, bottom 1470, sides 35). The grid itself is background and may run under those zones.
- Tile numbers appear only if `COUNTS` was filled. The render has exactly the `frames` of `clip.json` (ffprobe it).

## Traps
- `auto` reads the wall colour from the upper half of the frame, with the speaker averaged out. It needs the speaker to leave most of the upper wall visible at some point in the slot.
- Bare wall left uncovered next to furniture (a dark shadow band): raise `WALL_TOL` to 1.3. Grid on a pale sofa or the floor: lower it to 0.7, or draw the piece in `IN_FRONT`. prep prints a warning when the grid reaches the bottom of the frame.
- A doorway into another room is not wall: if the grid should stop at the door frame and does not, close it with `WALL` or `IN_FRONT`.
- After any change to the matte fields run `prep.py` (not just `prep.py wall`) before `build.py`, or the render uses the old `fg.webm`.
- Fewer covers than the wall needs are repeated in order; under 9 the repeats are easy to spot. `F_IN` must be 8 or later (the columns rise for 8 frames before the word); `F_OUT` needs 45 frames after `F_IN` and 2 frames after itself. With `F_OUT = None` the main reel has to cut away on the last frame.
- Moving camera: the grid is glued to the wall with a per-frame `matrix3d` set by a function-based GSAP property (seek-safe). If it slides, lower `TRACK_YMAX` to just above the furniture and run `prep.py --force`.
- Sounds play at 0.75x template volume: one whoosh in, one out, a soft pop when the room is back.
