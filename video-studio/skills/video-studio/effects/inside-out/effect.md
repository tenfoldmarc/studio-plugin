# inside-out (Inside Out)

**What it does:** a thin cream line runs down the speaker, their body below the neck opens into a window onto ONE calm b-roll clip (face stays live), the picture slowly pushes in, then one soft iris from the chest flips it: the speaker is solid again and the same clip is the room around them. Near the end the real room eases back.
**Job:** hook (first 3 seconds), or the moment a line introduces a place, a product or a screen ("this is where I work", "here's the app").
**Trigger phrases:** "inside out on this line", "turn my body into a window onto this clip, then flip it into the room", "put my b-roll inside me".

## First step: the fill comes from the buyer
Ask for ONE short b-roll clip (3 s or more; a still image also works): a place, a product, a screen. **Never a person** (not even the speaker), no captions or big titles, calm movement. Copy it into `fill/` in the slot. Nothing ships with the effect: **no fill = the effect is left out** (build.py stops with "INSIDE OUT DECLINES: there is no fill clip ...").

## Footage it needs
- Shot: wide, medium or close (selfie that shows the shoulders and chest). Camera: still or handheld drift. No zoom or punch-in inside the slot (declines).
- Wall: not needed (the room is replaced after the flip). Cutout: layered (required, `assets/subject.webm`). `aroll_hi` not used.
- Breaks: the face filling the frame with no chest in shot (declines: no window); a zoom inside the slot (declines); two people (only the largest cutout gets the window); a matte that grabs a chair arm (it shows inside the line: add `MATTE_KILL_POLYS`).

## Adapting to the footage (build.py measures the cutout, prints the variant and why)
- Wide (head under 150 px): the window is the whole body below the neck. FIT frames the whole picture inside the small body (so it reads as a window, not a flat colour), then the picture grows into the room with the same iris.
- Medium (the demo look): window from the collar down, iris from the chest, a floor shadow when the body ends inside the frame.
- Tight selfie close-up (shoulders edge to edge): the keep zone and shadows scale with the big head; the window is the chest under the chin; iris from the upper chest. Face filling the frame: declines.
- Still camera or handheld drift: the same (the matte is followed per frame, head top and centre smoothed). A zoom or punch-in: declines.
- Room behind: open wall, busy shelf, window or lamp, plain dark: only the line's soft outer shadow changes (stronger on pale rooms); it warns when the line colour is close to the room.
- Speaker off-centre or two-thirds of the frame: keep zone and iris follow the measured head; nothing is placed by hand.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `words.json`, `clip.json`, `fill/` (the buyer's clip). Sounds (an air swell, a low thump, soft air on the way back) are synthesised into `assets_fx/` (seeded, nothing ships). No fonts: the effect draws no words.

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `FILL` | the fill file | 'auto' (first video in fill/, else first image) or 'fill/name.mp4' |
| `FILL_START`, `FILL_FOCUS`, `FILL_PUSH` | where the fill starts, which part of it stays in the 9:16 crop, the slow push | look at `work/qa/fill.jpg`; focus (x, y) 0 to 1 |
| `FIT` | frame the whole picture inside a small body, grow it into the room on the flip | 'auto' (wide shots only), True, False |
| `T_IN` | the word the line and window start on | a word ('edit', 'edit#2'), seconds, or 'auto'. Re-measured on the audio |
| `T_FLIP` | the word it flips on | the payoff word; 'auto' = the word nearest 1 s after T_IN |
| `T_OUT` | the real room eases back | 'auto' (last 14 frames), seconds, or 'cut' (holds; only if the reel cuts right after) |
| `ACCENT`, `LINE_PX` | line colour (the buyer's accent), px inside / outside the edge | light colours read best on most shirts |
| `KEEP` | live head-and-neck zone | 'auto'; dict(cy, rx, ry) only if the window eats the chin |
| `MATTE_KILL_POLYS` | matte repairs, off | only after you see room inside the line in a preview |
| `SEED` | sound synthesis | leave |
FONT / WEIGHT / CASE / INK: not used (no words on screen); the buyer's look reaches the effect through `ACCENT`.

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `SFX=0` no sounds. `CAPTIONS=0` and `GRADE`: accepted, change nothing (no words, no grade). The reel's captions stay on over this effect.

## Python
Needs OpenCV: in the Studio run `setup.py --fx inside-out` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, choose, prep the fill, plan, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 40,80,110 -g      # 2. preview the frames it suggests -> work/t/ ; look at work/qa/fill.jpg
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4 (4 workers)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage; the line starts on T_IN, the iris on T_FLIP.
- The face and chin are live video, never inside the window; no person anywhere in the fill.
- The line hugs the speaker (no room fringe, no chair arm inside it).

## Traps
- Whisper starts can be 2 to 4 frames off and it can invent words on quiet audio: check words.json; `PY onsets.py first last` shows the audio, then give T_IN / T_FLIP in seconds.
- A fill with a person or big text fights the face. Use plain b-roll; if a person walks in, move FILL_START.
- Keep it calm: one fill, no cuts inside it. A busy, fast fill makes the effect look cheap.
