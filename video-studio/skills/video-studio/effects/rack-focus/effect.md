# rack-focus (Rack Focus)

**What it does:** a two-line title hangs close to the lens as soft points of light (real lens bokeh: the lens's own nine-blade shape, lit rim, faint rings and dust, cat's eye toward the edges). On the key word focus pulls to it: the speaker and the room fall into true lens blur, the discs shrink into crisp type. It holds, racks back to the speaker, and the title drifts out of frame before the slot ends.
**Job:** emphasis / explain: name the one thing the sentence is about. Also a soft hook on a key claim.
**Trigger phrases:** "rack focus to the word X", "pull focus to a title on X, then back to me", "focus pull title".

## Footage it needs
- Shot: close (selfie), medium or wide. Camera: still or handheld drift (the title is glued to the lens, so drift is right). A walking or panning camera is untested.
- Wall: none needed. The title sits on the darkest, calmest spot off the face (usually the chest or legs); a bright room behind it gets a soft shade.
- Cutout: measured and layered (`assets/subject.webm`: the speaker and the room blur apart, face and hands are measured). Without a cutout the whole frame blurs as one layer.
- Breaks: the face filling every spot in the safe zone (declines); a slot where the title could be sharp for under 0.55 s (declines); two people (one cutout for both, fine but untested).

## Adapting to the footage (build.py picks and prints)
- Close selfie (head wider than 300 px): room blur 30 px, speaker 0.62 of it, discs 0.31 x the word size, block up to 640 px.
- Medium (150 to 300 px): room 26 px, speaker 0.78, smaller discs (0.26), block up to 700 px. Wide (under 150 px): room 22 px, speaker 0.88 (he is nearly as far as the wall).
- No person found (voice-over, b-roll): one-layer blur, title in the lower middle.
- Still or drifting camera: same; the face box is the 3rd to 97th percentile over the whole title span (a raised hand does not count as the head).
- Room: point lights (lamp, bulb, LED) bloom into real discs when the room blurs; big clipped areas (window, white wall) get a gentle lift only. Disc colour follows the room's lights, kept off orange; cool daylight gives near-white discs, never blue. A bright room behind the title gets a soft shade that comes and goes with the focus.
- Speaker off-centre or two-thirds of the frame: the title goes to the darkest spot off the face, where hands move least (measured from the picture, not the cutout: hands in front of the body do not change it). The word shrinks to fit (236 px down to 120), caps tracking tightens next.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (recommended), `words.json`, `clip.json`, `assets/fonts/fonts.css` + woff2 files. No aroll_hi. Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_LAND` | the word the title is sharp on | a word ('skill', 'skill#2'), seconds, or 'auto'. build.py prints Whisper and audio onset; if they differ by over 0.15 s check with onsets.py and give seconds |
| `T_BACK`, `HOLD` | when focus returns | 'auto' = HOLD (1.0 s) after sharp, or a word / seconds. Shortened so the title is gone before the slot ends |
| `SMALL`, `BIG` | tracked caps line, the one big word | the speaker's own words; `SMALL` '' for none |
| `FONT`, `ITALIC`, `WEIGHT`, `CASE` | big word family / italic / weight / case | the buyer's caption font from fonts.css; default Instrument Serif italic 400 |
| `SMALL_FONT`, `SMALL_WEIGHT`, `SMALL_CASE` | caps line | default Inter Tight 700 upper (thin caps vanish over the blur) |
| `INK`, `ACCENT` | caps colour, big word colour | default cream; ACCENT 'ink' or the buyer's highlight colour |
| `ALIGN` | 'left' (demo look) or 'centre' | |
| `BOKEH` | disc colour | 'auto' (room lights) or (r, g, b) |
| `TITLE_CENTRE`, `SHOT` | overrides | 'auto' unless the printout's choice looks wrong in the preview |
| `MAX_RADIUS`, `SUBJECT_RATIO`, `REST_RADIUS`, `BREATHING` | lens overrides | 'auto', 'auto', 'auto', 0.026 |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no words: the pull goes to the points of light alone (the reel captions it). `SFX=0` no swells or thump. `GRADE=1` a touch richer colour while the title is sharp (default off). Frame 0 and the last frame are always the plain a-roll.

## Python
Needs OpenCV: in the Studio run `setup.py --fx rack-focus` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, place, time, plan, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 40,62,95 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 9 to 15 s per second of slot (6 cores)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, edge colour, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. The title sharp on its word, discs (not a grey smear) at rest.
- The face never under the title or its discs; hands not waving through the letters while they are sharp.
- The sharp title inside y 220 to 1470 and the right column; it reads against what is behind it.

## Traps
- Whisper invents words on quiet audio ("Thank you for watching"): check words.json before trusting 'auto'.
- A long BIG word shrinks the serif; past about 11 letters use a shorter word.
- HyperFrames can shift colour about 2 levels against the a-roll: post.py prints the edge difference. That is the render pipeline, not the effect (the effect hands back the a-roll bytes at both ends).
- Inside a reel: the title IS the caption for its span. Hide the reel's captions there, or build with CAPTIONS=0.
