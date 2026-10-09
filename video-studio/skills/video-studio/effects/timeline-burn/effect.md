# timeline-burn

**What it does:** a video-editing timeline assembles in front of the speaker (lower third, under the chin), a cursor makes two slow edits, the timeline overheats, catches fire on a spoken word, burns right to left and crumbles into embers. Then the plain picture is back.
**Job:** hook (also a punchline mid-video: "you do not need X any more", "X is done").
**Trigger phrases:** "put an editing timeline on screen and burn it when I say X", "burn the timeline on X", "timeline burn".

## Footage it needs
- **Shot:** wide or medium. On the 1080x1920 slot the chin has to be above about y 980 for the timeline plus a caption line, above about y 1100 for the timeline alone. Close fails: with the face that low there is no room under it inside the safe zone and `build.py` stops with "No room for the timeline".
- **Camera:** still, drifting or moving. Nothing is tracked: the timeline is a screen overlay and does not stick to the room.
- **Wall:** none.
- **Cutout:** only measured (the head box is read from `assets/subject.webm` so nothing is ever drawn on the face). Not layered: the timeline is in front of the speaker and hands that drop that low go behind it. Type `FACE` and the slot can be made with `--no-cutout`. `aroll_hi` is not used.
- **Breaks it:** a slot with fewer than 30 frames before the burn word or fewer than 30 after it; a face that sinks below y 1100 during the slot; a hand at the face, a hood, long hair or a raised knee (the head box becomes a guess: `build.py` says so, type `FACE`); a bright busy picture with `DIM = 0` (the fire reads best on a dark or dimmed shot).
- **Edges:** frame 0 and the last frame are the untouched clip. The effect starts on `F_IN` and everything, dim included, is gone 28 frames after the burn. It cannot end on the fire: the slot has to run 30 frames past the burn word.
- Python: numpy, scipy, Pillow. No extra packages, no model of its own, no shipped media.

## Words, captions and the reel's style
- The words it draws (track labels, timecodes, optional clip names) **are the effect itself**, not speech. It draws no spoken words, so there is no caption switch to turn off: the reel's captions **keep running** through the slot.
- The timeline sits where chest captions go. `build.py` prints `fx_add.py --caption-y N`: the reel's captions move to the line above the timeline for the slot. When there is no room for that line it says so: add the slot with `--captions hide` instead (the one case where the captions pause).
- **`STYLE` block** (top of `build.py`, above the CLIP block): `FONT`, `WEIGHT`, `CASE`, `TEXT`, `LABEL_PX`, `NAME_PX`, `ACCENT`, `PANEL`, `PANEL_EDGE`, `PALETTE`. When the reel has a caption or overall style, set typeface, case, weight and colours here BEFORE the first build (`ACCENT` = the reel's accent colour). The fire stays fire coloured. Placement is `PANEL_W` / `PANEL_X` / `PANEL_Y` in the CLIP block.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `BURN_AT` | the spoken word it catches fire on (`'word'`, `'word#2'` = second time), or a frame | `build.py words`. Required: the build stops until it is set |
| `F_IN` | frame the timeline assembles | `None` = 72 frames before the burn. 30 at least; under 69 the cursor edits are left out |
| `TRACKS` | one dict per track, top to bottom (2 to 6): `label`, `kind` (`'video'`, `'title'`, `'audio'`), `color`, `clips`, `names` | `clips` = a count (laid out from `SEED`) or `(start, end[, 'name'])` from 0 to 1 |
| `TRACKS[..]['names']` | optional words on the clips | the speaker's own words, short; `[]` = none. Small by nature: they are dressing, not captions |
| `RULER` | timecodes over the tracks | `'auto'`, your own list of up to 8, or `None` for ticks only |
| `EDIT` | the cursor that trims one clip and drags another | `False` = no cursor |
| `DIM` | how much the picture darkens while the timeline is up | 0 = off, 0.4 default, 0.6 dark. Eases in and is back before the slot ends. 0 when the reel's look is already dark |
| `PANEL_W`, `PANEL_X`, `PANEL_Y` | width, centre x, top y of the timeline | 848 / 540 / `None` (measured: as low as the safe zone allows) |
| `CAPTION_ROOM` | px kept between chin and timeline for the reel's caption line | 130; 0 = none kept |
| `FACE` | `(x0, y0, x1, y1)` head box over the whole effect | `None` = measured; read it off `work/layout.jpg` when the red box is wrong |
| `SEED`, `VOICE`, `SOUNDS` | layout / cracks / embers; the speaker's audio; sound list | defaults |

**Switches:** `SAFE=1` safe-zone guide (snapshots only), `SFX=0` no sounds, `DIM=0` no dimming. `CAPTIONS=0` changes nothing (no caption words to drop). There is no grade of its own.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py words      # 1. every word with its frame -> BURN_AT in the CLIP block; reel style -> the STYLE block
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 2. measures the face, places the timeline, page with the guide. Read the !! lines, LOOK at work/layout.jpg
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors (a "file too large" warning is normal)
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 3. guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 4. frame count, plain edges, burn frame, face, safe zone, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 5 s slot takes about 5 minutes after the cutout.

## What to look at (work/check/sheet.jpg)
- First and last frame, the frame before `F_IN` and the frame 28 after the burn: the plain clip (`check.py` prints the difference).
- The flash is on the burn frame and the frame before it has none. Say the line out loud against the phone copy: the fire starts on the word.
- The timeline and every ember stay under the chin and inside the safe zone (red line = y 1470; nothing right of x 980 below y 1155).
- In the reel: one snapshot inside the slot. The reel's captions sit on the line above the timeline, in the reel's style, nothing doubled.

## Traps
- The word's frame: `build.py words` snaps each word to where the voice comes up out of a dip, and prints the transcript's guess beside it. In fast speech the two can differ by 5 frames. Confirm with `PY build.py level <from> <to>` (bars per frame) and type the frame into `BURN_AT` when the word is wrong. One frame early is better than one late.
- Under 72 frames before the burn the heat-up is squeezed, under 69 the cursor edits go. The full gag needs 2.4 s: start the slot early enough.
- Long labels are drawn small (the label column is 70 px): 4 characters or fewer. A name that does not fit its clip is left off and reported.
- Generic on purpose: no app name, logo or real interface. On-screen words are the speaker's own: no invented numbers, names or handles, no em dashes.
- Sounds: stock `whoosh-short`, `click`, `impact-bass-1` only, at 0.75x template volume. `SOUNDS = []` when the reel has its own hit on that word.
- After changing `BURN_AT`, `F_IN`, `TRACKS` or `FACE`, run `build.py` again and read the printed `--caption-y`: it moves with the layout.
