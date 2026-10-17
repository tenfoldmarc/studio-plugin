# paper-cut (Paper Cut)

**What it does:** the room rips away to torn paper sheets; the speaker stays live as a white-edged, hand-cut paper cutout moving at 12 fps; the phrase slams down in ransom-note letters word by word while crayon and pen marks boil; then the collage tears in two and the real room is back.
**Job:** hook or explain. One short claim (1 to 4 rows, 2 to 6 words) said with punch.
**Trigger phrases:** "make this line a paper collage", "ransom-note letters for X", "cut me out on torn paper", "paper cut on this line".

## Footage it needs
- Shot: wide, medium or close (selfie). Camera: still or handheld drift (the paper covers the room; the cutout is live). A big zoom or punch-in inside the slot shrinks the layout (build.py warns).
- Wall: not needed. The room is replaced by paper, so wall, shelf, window or lamp do not matter.
- Cutout: layered (required, `assets/subject.webm`). `aroll_hi` not used.
- Breaks: the face filling the frame with no room above the head or under the chin (declines); two people (only the largest cutout is kept); a matte that grabs room (a picture frame, a chair) shows up loudly inside the white border.

## Adapting to the footage (build.py picks the layout and prints why)
- Wide shot (head top low): ABOVE. Letters stacked over the head, the cutout barely shrinks (0.96).
- Medium shot: ABOVE. The cutout shrinks (down to 0.70) toward the bottom corner on its side, freeing the top half for the letters (the demo look).
- Tight selfie close-up (shoulders edge to edge): BELOW. No shrink (it would show the cut shoulders); letters go across the chest under the chin, no ellipse near the face.
- Face fills the frame both ways: stops with "PAPER CUT DECLINES: ..." (pass that on; or CAPTIONS=0 for the collage alone).
- Still camera or handheld drift: the same; the highest head point and lowest chin over the effect set the room.
- Open wall, busy shelf, window or lamp, plain dark: no change (all of it is under paper).
- Speaker off-centre or on one side: the cutout anchors to the frame edge it touches (or the side its face is on); the yellow and graph sheets and the marks mirror to the open side.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `words.json`, `clip.json`, `assets/fonts/fonts.css` and its woff2 files. Sounds (rips, whooshes, clicks, a pop) are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_IN` | the word the paper rips in on | a word ('look', 'look#2'), seconds, or 'auto'. Re-measured on the audio |
| `T_OUT` | when it tears away | 'auto' (room back 4 frames before the end), seconds, or 'cut' (holds; only if the reel cuts right after) |
| `ROWS` | the phrase, one string per row | the speaker's own words; each word lands on its spoken word. A row can be `[(text, word or seconds), ...]` groups for exact landings (e.g. syllables of '100%') |
| `LAYOUT` | 'auto', 'above', 'below' | leave 'auto' unless the printed choice looks wrong in the preview |
| `FONT`, `WEIGHT`, `CASE` | letter faces | 'mix' (the ransom mix of shipped faces) or the buyer's caption family from fonts.css (or a list); CASE 'upper' |
| `INK`, `ACCENT`, `ACCENT2`, `HIGHLIGHT` | dark ink, red, blue, yellow of the scraps and marks | the buyer's colours; light ones get dark ink automatically |
| `ELLIPSE`, `TAPE` | pen ellipse row, tape strip | 'auto' / row number / None; True / False |
| `MATTE_KILL_POLYS`, `MATTE_PLATE` | matte repairs, off | only after you see room inside the white border in a preview |
| `SEED` | the scatter of papers, faces, tilts | change for another arrangement |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no letters, ellipse, underline or tape (the reel captions it). `SFX=0` no sounds. `GRADE`: this effect has no grade of its own; accepted, does nothing.

## Python
Needs OpenCV: in the Studio run `setup.py --fx paper-cut` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, choose the layout, plan, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 30,90,140 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 11 to 20 s per second of slot (6 cores)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. Each word's letters land on the word (the printout lists the landing frames).
- No letter, ellipse or tape over the face; nothing readable above y 220 or below y 1470.
- Inside the white border: only the speaker (no slice of chair, frame or lamp). If there is, add a MATTE_KILL_POLYS entry.

## Traps
- Whisper word starts can be off by a lot after a pause ("drop" heard 0.6 s early in a test). build.py lands on the loudness rise; if a landing still looks wrong, run `PY onsets.py first last` and give that word in seconds.
- On quiet audio Whisper can invent words ("Thank you for watching"): check words.json before matching ROWS.
- A long row (over about 12 letters) gets small letters: split it into two rows.
- Inside a reel the letters ARE the caption: hide the reel's captions for the slot's span, or build with CAPTIONS=0.
