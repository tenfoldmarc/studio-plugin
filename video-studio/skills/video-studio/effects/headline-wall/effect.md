# headline-wall

**What it does:** the wall behind the speaker fills with headline, post, search and video cards that all say the same thing in different words, stuck to the room behind the speaker; on the key word a yellow highlighter swipes one phrase on every card and big hero cards land on the next spoken words.
**Job:** proof / explain ("everybody is talking about X", "everyone says X"). Works as an opener and just as well mid-video or under b-roll: set `F_OUT` and the wall whips off again inside the take.
**Trigger phrases:** "fill the wall behind me with headlines about X", "everybody's talking about X, show the clippings", "headline wall".

## Footage it needs, and where it fails
- ONE continuous shot (no internal cuts), 3 to 6 s, with visible wall beside or above the speaker's head. Works wide (sofa, chair, floor) and medium. Camera may be still or moving: a moving camera is tracked.
- Each hero card needs about 280 x 220 px of clear wall beside the speaker's head inside the safe zone. A tight selfie that fills the frame has no room: use 1 or 2 heroes, or another effect.
- Fails on: a wall that is really a window / mirror / open doorway (the track slides), big arm swings across the wall after the heroes land (they get hidden), a shot that cuts.
- Leave 1.5 s after the last hero so the wall can be read.

**Slot inputs:** cutout yes (`assets/subject.webm`), `aroll_hi` no. Python: numpy, scipy, Pillow (the skill's Python has them). No OpenCV, no extra packages.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `HEADLINES` | plain list of strings, one per card, `[phrase]` = highlighted | write 12 to 20 versions of the speaker's message, under ~40 characters; no real outlets, people, numbers |
| `HEROES` | `(headline, frame)` big cards that land on a word, 2 to 4 | frames from `onsets.py`; in spoken order |
| `SEARCH` | text of the search-bar pill, or `None` | lowercase, like a typed query |
| `F_START`, `F_PEAK` | first card, last pile card | first syllable; end of the opening phrase |
| `F_ACCENT` | highlighter + bump + low hit | onset of the key word (usually the first hero's frame) |
| `F_OUT` | frame the wall whips off again, `None` = stays to the end | mid-take use; needs `PUSH = BUMP = 1` and `F_OUT <= frames - 12` |
| `DENSITY`, `LEAD` | pile-up acceleration; hero head start | leave at 1.8 and 4 |
| `WALL` | `(x0, y0, x1, y1)` wall the cards may cover | `None` first, then read it off `work/layout.jpg`: stop above sofas, desks, windows |
| `KEEP_OUT`, `FOREGROUND` | screen boxes no card may enter; furniture polygons cards pass behind | default `[]`; the main reel's label pill; a pillow or sofa back in front of the wall |
| `FACE`, `HERO_FIRST_SIDE` | push-in target; side of the first hero | `None` = measured; the side with more clear wall |
| `N_MID`, `N_FAR`, `FAR_BLEED_SIDES` | card counts per depth, side bleed | `None` = by wall area |
| `PUSH`, `BUMP`, `DIM`, `ACCENT` | push-in, bump, room dim, highlighter colour | raise `DIM` to ~1.3 on a white wall |
| `OUTLETS`, `PEOPLE`, `CHAT_REPLIES`, `DARK_LABEL` | placeholder source labels | keep them generic |
| `VOICE`, `FIX_MATTE`, `TRACK_YMAX`, `REF`, `SEED`, `SOUNDS` | the speaker's audio on/off, matte fix, track region, layout frame, shuffle, sounds | defaults; see traps |

**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `SFX=0` drops the effect's sounds. `GRADE=0` drops the effect's vignette (the main reel grades once). `CAPTIONS=0` is accepted and does nothing: this effect has no caption words.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. word onsets as frames -> fill HEADLINES, HEROES, F_* in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. track + matte + layout (about 1 to 2 min). LOOK at work/layout.jpg (and work/trackcheck.jpg if the camera moves). Set WALL / HERO_FIRST_SIDE if needed, then
PY "SK/scripts/fx_run.py" "<slot>" prep.py layout      # re-layout only (seconds). Repeat until the picture is right
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 GRADE=0      # 3. page with the safe guide
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.5,1.0,1.5,2.0,2.5,3.0
PY "SK/scripts/fx_run.py" "<slot>" build.py GRADE=0      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Nudging one card by hand: edit `x`, `y`, `rot` in `work/layout.json`, run `python3 build.py` (a later `prep.py layout` overwrites it).

## What to look at in the final frames
- The first hero is fully landed on the frame of its word and the highlighter starts on that frame (pull the word frame and the one before).
- Cards stay glued to the wall while the camera moves (compare a wall detail next to a card on two frames 10 apart).
- Every hero line is fully readable, none tucked behind the speaker's head or shoulder; nothing covers the speaker's face (cards are behind the speaker).
- Nothing in the top 220 px; hero and mid cards inside the safe zone on the last frame. Far cards may run off the sides.
- The speaker's outline: no cream showing through a fast hand or sleeve, no light fringe around the cap or hair. The render has exactly the `frames` of `clip.json` (ffprobe it).

## Traps
- `WALL = None` runs down to elbow height: fine on a bare wall, wrong when a sofa back or desk is in that band. Always check the cyan box in `work/layout.jpg`.
- prep prints `shrunk to 0.xx` / `dropped` when a hero has no room: shorten the headline, switch `HERO_FIRST_SIDE`, or use fewer heroes. Under 0.8 the text gets small on a phone.
- Put the `[phrase]` early in a headline: line breaks are balanced, the first line is the one that survives a card tucked behind the speaker.
- Word onsets: Whisper is 1 to 3 frames off and mishears names. `onsets.py` shows the level per frame; a hero with `LEAD` 4 lands on the word, less than 3 reads late.
- A hero only has to clear where the speaker is from its own landing frame on, mid and far cards where the speaker is from the accent on: if the speaker leans into a card later in the slot, cut the slot shorter or lower that card.
- The track is fitted on wall pixels above `TRACK_YMAX` (1100). If `work/trackcheck.jpg` shows a doubled wall, lower it to just above the furniture and run `prep.py --force`. After editing `FOREGROUND` run `prep.py matte`.
- `matrix3d` is not handed to GSAP: a function-based property (`cam.frame`) sets it per frame. Keep it that way, it is seek-safe.
- `click-soft` is a very quiet file (needs ~.34 base volume); `impact-bass-short` ships in `assets_fx/`. Far cards never enter the top 220 px (checked on every frame); side bleed is on by default, `FAR_BLEED_SIDES = False` keeps them fully in frame.
