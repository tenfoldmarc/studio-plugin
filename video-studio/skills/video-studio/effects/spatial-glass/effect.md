# spatial-glass (Spatial Glass)

**What it does:** three panes of frosted glass float in the room at three depths while the speaker names three steps: a grid of soft tiles (step 1, high on the wall), a bar that types the step (step 2, in front of the speaker), a ring that runs and resolves to a check (step 3, tucked behind the shoulder). Each pane blurs the live room behind it; a slow camera drift slides them against the room. They leave before the slot ends.
**Job:** explain. A three-step "how it works" line ("drop your clips, trigger the skill, it takes care of it").
**Trigger phrases:** "float three glass panes for these three steps", "spatial glass on drop, trigger, done", "glass UI windows in the room".

## Footage it needs
- Shot: wide or medium (three full panes); tight selfie works with smaller panes or two panes. Camera: still or handheld drift (the room is tracked and the panes ride it). Walking or panning is untested.
- Wall: beside the head (one side is enough) and some chest or lap below the chin for the bar.
- Cutout: layered (the ring pane goes behind the speaker; `assets/subject.webm` needed for that and for the measuring). Without a cutout the panes float in the open frame and none goes behind. `aroll_hi` not used.
- Breaks: the face filling the frame with no wall on either side (declines); two people (the cutout counts both as the speaker); steps said faster than 0.28 s apart (the panes wait their turn).

## Adapting to the footage (build.py chooses and prints why; CLIP entries override)
- Wide / medium: three panes at full size (scaled down in steps until they fit): grid high on the side with more wall, ring beside the head on the other side, bar across the chest or lap below the chin.
- Tight selfie (head wider than 290 px or its top above y 300): panes from 0.8x down beside the head. Three panes while they stay 0.62x or bigger, else TWO bigger panes (the bar types steps 1 and 2 in turn, the ring takes step 3), and only then smaller ones down to 0.5x. No room for two: stops with "SPATIAL GLASS DECLINES: there is no open wall ..." (pass that on; pick a moment with room beside the speaker).
- Still camera: the panes hold still on the wall (only their slow float). Handheld drift: the room is tracked (features; a plain wall that cannot be followed counts as still) and the panes ride it, world-locked.
- Big handheld sweep (the face crosses a few hundred px of room, e.g. a walking or waving selfie): declines with "the face moves about N px across the room ..." because a world-locked pane would be crossed by the face. Suggest a steadier moment or a stand.
- Room: bright or mid room = light frosted glass with dark type; dark room (median below 85) = smoked glass with cream type. A lamp in shot is found and the pane edges near it catch its light. A busy shelf or window just shows through the frost (that is the point).
- Speaker off-centre or two-thirds of the frame: every pane takes the open side; the grid only goes where the speaker never is, the ring may hide up to 40 percent behind them, nothing ever touches the face.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (recommended), `words.json`, `clip.json`, `assets/fonts/fonts.css` + its woff2 files. Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `STEPS` | three (cue, text): cue = the word each pane lands on, text = what the pane shows | cue: a word ('clips', 'clips#2') or seconds; build.py prints Whisper and audio onset. Text: the speaker's own 1 to 3 words, never a product, app or name |
| `DONE`, `DONE_LABEL` | when the ring turns into a check; its label after | 'auto' (about 1 s after step 3) or a word / seconds; label 'Done', or '' to keep step 3's text |
| `OUT` | when the panes leave | 'auto' (plain footage 3 frames before the end), seconds, or 'cut' (holds; only if the reel cuts right after) |
| `PANES`, `LAYOUT`, `REF` | pane count, positions, measuring frame | leave 'auto'; LAYOUT = {'grid': (cx, cy, k), 'ring': (cx, cy, k), 'bar': (cx, cy, k, width)} from the printout to nudge one |
| `GLASS` | 'light' / 'smoke' | 'auto' picks by the room brightness |
| `FONT`, `WEIGHT`, `FONT2`, `ITALIC2`, `CASE` | bar + grid header sans, ring label serif, casing | families from assets/fonts/fonts.css (the buyer's caption font); defaults Inter 500, Instrument Serif italic |
| `INK`, `ACCENT` | type colour, send button + check colour | 'auto' / (r, g, b); ACCENT = the buyer's highlight colour (default butter yellow) |
| `PUSH`, `TRUCK`, `LAMP` | camera push-in, sideways slide, light in shot | 0.03, 'auto', 'auto'; 0 turns a move off; LAMP None turns the glint off |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no words on the panes (the bar types a quiet line, ring and grid unlabelled). `SFX=0` no air swells or thump. `GRADE=1` a touch more contrast while the panes are up (default off).

## Python
Needs OpenCV: in the Studio run `setup.py --fx spatial-glass` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. track, measure, choose the layout, plan, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames <the 4 it suggests> -g      # 2. preview -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 7 to 13 s per second of slot (4 workers; WORKERS=n)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. Each pane settles on its word; the check lands after step 3.
- The face never under glass; the ring's edge behind the speaker is clean (no halo, no ghost of a hand).
- Panes sit on the wall when the camera moves (no sliding); nothing above y 220 or below y 1470.

## Traps
- Whisper is often 0.1 to 0.3 s off: build.py prints Whisper and the audio onset; if they disagree by more than 0.15 s check with `PY onsets.py`, then give seconds.
- On quiet audio Whisper can invent words ("thank you for watching"): read words.json before trusting a cue.
- A pane's text is the speaker's words. Never a real app, product, person or handle on the glass.
- Light glass over a white wall reads as a white card: if the printout says light glass on a near-white wall, try GLASS = 'smoke'.
- Inside a reel: the pane words are not captions. Keep the reel captions on; build with CAPTIONS=0 if they say the same thing twice.
