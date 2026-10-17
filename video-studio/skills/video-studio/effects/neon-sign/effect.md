# neon-sign (Neon Sign)

**What it does:** the speaker's phrase becomes a glass-tube neon sign on their own wall: it fades on unlit, strikes on the word with an irregular flicker, the room drops most of a stop, and the sign lights the wall, whatever hangs near it and the side of the speaker that faces it. It switches off and fades away before the slot ends.
**Job:** hook or emphasis on a short phrase (1 to 3 short lines, the speaker's own words).
**Trigger phrases:** "put that phrase on my wall as a neon sign", "light up 'like this' in neon when I say it", "neon sign behind me".

## Footage it needs
- Shot: wide, medium or close. Camera: still or handheld drift (the sign rides a track of the room). A walking or panning camera is not supported.
- Wall: beside or above (a patch of plain wall the head never crosses; hands crossing it now and then is fine, the sign is behind them).
- Cutout: layered (the sign goes behind the speaker, the light lands on them). Needs `assets/subject.webm`; `aroll_hi` not used.
- Breaks: no plain wall anywhere near the head (declines); a wall seen at a steep angle (the sign is drawn flat to the camera and looks pasted on); two people (the cutout layers both).

## Adapting to the footage (build.py picks the variant and prints why; work/placement.jpg shows it)
- Wide or medium shot, open wall beside the head: BESIDE, on the side with more wall, centred near face height, letters up to SIZE_MAX, at least 0.55 x head width (64 to 110 px).
- No open wall beside (a shelf, a window, the speaker filling the width): ABOVE, centred over the head, between the top safe line and the hair.
- Tight selfie (head over 330 px wide) or a busy room, nothing beside or above: CORNER, a smaller sign (60 px letters or more) in the open top corner. A sign that does not fit stacked is set on one line, then without the underline.
- Nowhere (a selfie whose head fills the top while the phone moves; shelves everywhere): stops with "NEON SIGN DECLINES: there is no open wall ... (the reason)" (pass that on).
- Still camera: no track (identity, no jitter). Handheld drift: a similarity track of the room (shift, roll, scale); the sign stays on the wall and must stay inside the safe zone on every frame it shows.- Open wall: the demo look. Busy shelf: the sign never hangs over it (only plain wall counts), the shelf takes the glow. Window or lamp: excluded from placement; a bright room dims a little deeper (0.50). Plain dark room: dims less (0.62), the sign carries it.
- Speaker off-centre or two-thirds of the frame: BESIDE on the open side; thin things on the wall (trim, a switch) may sit behind the sign.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `words.json`, `clip.json`, `assets/fonts/fonts.css` + its woff2 files. Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `LINES` | `(text, strike)` per tube, top to bottom | the speaker's words, 1 to 3 short lines; strike = a word ('this', 'this#2'), seconds or 'auto' (the line's first word). `*text*` = ACCENT colour |
| `UNDERLINE` | swash tube under the last line | 'auto' (0.4 s after the last line), a word, seconds, or None |
| `STEP_ON` | the sign steps brighter with a low thump | a later word ('that'), or None |
| `OUT` | switch-off | 'auto' (plain footage 3 frames before the end), seconds, or 'cut' (stays lit; only if the reel cuts right after) |
| `FONT`, `WEIGHT`, `CASE` | lettering | a family in assets/fonts/fonts.css (the buyer's font); default Marck Script (hand-bent script). A sans gives a monoline sign |
| `INK`, `ACCENT` | tube colour, underline and `*line*` colour | (r, g, b); default butter yellow (250, 230, 122); ACCENT 'ink' = same. Pale colours glow best, never orange |
| `ALIGN`, `TILT` | 'stagger' / 'left' / 'centre', degrees the lines climb | defaults stagger, 4 |
| `PLACE`, `SIDE`, `SIZE_MAX` | placement override | 'auto' / 'beside' / 'above' / 'corner' / (x, y, size); SIDE 'auto' / 'left' / 'right'; 200 |
| `FLICKER`, `ROOM_DIM`, `SPILL` | strike style, room exposure while lit, glow strength | 'classic' or 'soft'; 'auto' or 0.4 to 0.8; 1.0 |
| `CABLE`, `OCCLUDERS` | optional visible flex, optional shadows of things proud of the wall | None, [] (default off; frame-0 px from work/placement.jpg) |
| `BUZZ_DB`, `THUMP_DB` | sound peaks | -33, -27 (far under the voice) |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `SFX=0` no buzz or thump. `CAPTIONS=0` changes nothing (the sign is the effect; the reel captions as usual, keep captions clear of the sign). `GRADE` not used (the dim is gone before the slot ends).

## Python
Needs OpenCV: in the Studio run `setup.py --fx neon-sign` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, place, trace, light maps, index.html (20 to 40 s). READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 14,79,115 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4 (4 workers)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage (unless OUT = 'cut'). Each tube catches on its word.
- The sign never behind the head; the glass inside the safe zone; the light on the speaker is soft, never orange on skin.
- With drift: the sign stays put on the wall across the sheet (compare it to a corner or a frame near it).

## Traps
- Whisper is often 0.1 to 0.4 s off: build.py prints Whisper's time and the audio onset per tube. If it picked the wrong word, give seconds (check with onsets.py).
- The matte runs a few px wide of the speaker; the light and glass behind are pulled in 7 px (`matte_pull`), so no grey line of unlit wall follows the outline.
- Short beads (i dots, full stops) skip the electrode sleeve or they render as dark dots that never light.
- A heavy display font thins to a busy skeleton: prefer scripts and plain sans; check the unlit preview frame.
- Long text shrinks the sign or makes it decline: 1 to 3 short words per line ('not a' / 'tech bro', not "I'm not a").
- A punch-in or jump cut inside the slot breaks the track (the room jumps): make the slot from one continuous take.
- If the placement looks wrong, open work/placement.jpg (green open wall, red speaker, white the sign) and use PLACE / SIDE.
