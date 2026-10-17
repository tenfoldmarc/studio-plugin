# vertigo (Vertigo, effect 32)

**What it does:** a dolly zoom from one locked-off shot: the speaker stays perfectly still while the room behind them stretches away, holds, then springs back through neutral and settles on the untouched picture. Subtle on purpose.
**Job:** hook / emphasis: a confession, a twist, "here is the catch".
**Trigger phrases:** "do the vertigo zoom on this line", "make the room stretch away behind me when I say X", "dolly zoom on X".

## Footage it needs
- Shot: wide, medium or close. Camera: still is best; drifting is fine (tracked); moving handheld works at a gentler stretch.
- Wall: some room must show beside or above the head, with lines or things in it (door, shelf, picture, window). Cutout: layered (the speaker is comped back on top of the stretched room) and measured (head, chin, seat line).
- What breaks it: a plain wall (nothing to see stretch), the speaker filling the frame, a busy background right behind a speaker who never moves (the never-seen room is painted in), under 0.9 s of footage after the release word, a cut inside the slot. A camera that travels through the room still works but reads weaker (the stretch competes with the camera move).
- How the room behind the speaker is rebuilt: every frame where they lean or gesture uncovers some of it (plus `more.py`: the same take before and after the slot). What is never seen is filled: right at the outline the neighbouring room is mirrored in (edges continue at the right height), deeper in a column smear with the wall's own texture laid over it.

## Adapting to the footage (build.py chooses and prints it; CLIP entries override)
- Wide: full stretch 1.33; floor and furniture from the seat down stay pinned. Medium: 1.30, sofa or desk pinned. Close selfie (head near the top, shoulders edge to edge): 1.22 around the head, captions on the chest band, or above the head when the chin is too low.
- Still camera: one clean plate. Handheld drift: tracked, plate re-aligned per frame. Moving handheld: stretch 15% gentler. Camera moving through the room (prep's plate check misses by more than 8 levels): "live" fill, each frame rebuilt from its neighbours +-10 frames re-aligned, stretch capped at 1.20.
- Open wall: full stretch. Busy shelf right behind the speaker: the stretch drops in 0.03 steps until the painted-in part is small (`fake` under 0.9), declines below 1.12. Window or lamp: fine, bright areas just stretch. Plain dark or plain paint: declines ("the wall behind you is plain...").
- Speaker off-centre or two-thirds of the frame: the vanishing point follows the head; captions centre on the head, kept inside the safe zone.
- Declines (exit 1, one plain line to pass on): too little room visible, plain wall, never-seen busy room, line ends too soon after the snap. `FORCE = True` renders anyway.

## Slot inputs
cutout `assets/subject.webm`: yes. aroll_hi: no. `words.json`: timing and the effect's own words. Extra Python: `requirements.txt` (opencv-python-headless, numpy, scipy, Pillow): in the Studio `setup.py --fx vertigo`, else `python3 -m venv work/venv && work/venv/bin/pip install -r requirements.txt`.

## CLIP block (top of build.py)
| Field | What it is | How to find it |
|---|---|---|
| `PUSH_WORD` / `PEAK_WORD` / `RELEASE_WORD` | push starts on, lands at the end of, snaps back on these words | words.json; `None` = auto (printed). `'word#2'` = second time |
| `T_START` / `T_PEAK` / `T_RELEASE` | the same in seconds, override the words | `onsets.py`: frame / 30 |
| `SCALE` | room size at the peak | `None` = chosen from the footage; 1.12 to 1.35 |
| `ORIGIN` / `SEAT_Y` | vanishing point; row from which the room is pinned | `None` = measured; check `work/plate_check.jpg` |
| `FORCE` | render even when the check declines | only after you looked at the frames |
| `CAPTIONS` / `ACCENT_WORDS` | the effect's own words (`'auto'`, `[]`, or by hand) and which are accented | auto = 3 words per line from the push on |
| `CAP_Y` / `CAP_SIZE` | caption centre line and size | `None` = chest band under the chin, inside the safe zone |
| `FONT` `WEIGHT` `CASE` `INK` `ACCENT` | the buyer's caption look | a family + weight from `assets/fonts/fonts.css`, their colours |
| `SFX_GAIN` | riser + soft air level (generated in code) | 1.0 sits under the voice; 0 = silent |
| `GRADE` | CSS filter on the picture | used only with `GRADE=1` |

## Switches
`SAFE=1` safe-zone guide (snapshots only). `CAPTIONS=0` no words (the reel captions the slot). `SFX=0` no sounds. `GRADE=1` applies `GRADE`. On prep: `MORE=0` ignore work/more.*, `FILL=plate|live` override the plate check, `MIRROR_BAND=px` (110) mirrored room inside the outline. `FX_PROCS=n` bake processes.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 0. optional: frame-exact word onsets, if you time by hand
PY "SK/scripts/fx_run.py" "<slot>" more.py      # 1. optional, more plate
PY "SK/scripts/rvm_cut.py" "<slot>" --src work/more.mp4 --out work/more.webm      # 1b. only after more.py: its clean cutout
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. track, measure, clean plate. LOOK at work/plate_check.jpg
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 3. variant, timing, index.html. Read the printout (or the DECLINE line)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 4. assets/fx.mp4 (PY bake.py --frames 40-48 previews a few frames)
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <mid push>
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 5. guide off again (with the switches you want, e.g. CAPTIONS=0 SFX=0)
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 6. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Re-run prep after a new cutout; build + bake after any CLIP change to timing, SCALE, ORIGIN or SEAT_Y; captions, font and sound need only build + render. Bake time: see example/test.md.

## What to look at (work/qa/sheet_*.jpg)
- Speaker pixel-still in every frame; only the room moves. First and last frame equal to the a-roll.
- The ring the push uncovers around the head and shoulders: no smear, no copy of a hand, no hard seam.
- The chair or sofa under them stays put (if it slides, lower `SEAT_Y`). Words: never on the face, inside the safe zone.

## Traps
- The cutout must not include the chair; the seat line pins it instead. A seat higher than the measured one: set `SEAT_Y`.
- Fast hands near the edge: the old room colour is un-mixed from the soft edge, clamped at 14 levels.
- The undershoot below 1.0 mirrors a few px past the frame edge: keep it near 0.9 (it is, by the spring).
- whisper word starts are 0.1 to 0.3 s off: auto timing pads for it; for frame-exact timing use `onsets.py`.
