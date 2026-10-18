# code-scan (Code Scan)

**What it does:** the picture resolves into readable code (the room in dim slate glyphs, the speaker as a brighter figure of tokens), a small terminal card types two short lines, and the picture resolves back.
**Job:** hook / explain: the beat where the speaker says the work gets done by the machine ("trigger the skill", "it writes the code").
**Trigger phrases:** "turn the shot into code when I say X", "code scan on X", "make me turn into code".

## Footage it needs
- Shot: close (selfie), medium or wide. Camera: still or handheld drift (every frame is re-drawn, so drift is fine). A zoom, punch-in or big camera move inside the beat: declines.
- Wall: none needed. Any room works; a dark room is levelled so it still reads as code.
- Cutout: layered and measured (`assets/subject.webm`: the speaker becomes the bright figure, the head gets finer glyphs). Without a cutout the whole picture becomes room code (fine for voice-over or b-roll).
- Breaks: a hold under 0.6 s (declines), the shot zooming inside the beat (declines), two people (one figure for both, untested).

## Adapting to the footage (build.py picks and prints)
- Close selfie (head over 300 px, shoulders edge to edge): head ellipse from the measured head, card below the chin if it fits, else beside or above the head, else no card (printed).
- Medium (150 to 300 px) and wide (under 150 px): same machinery; the finer head cells keep a small face readable.
- No speaker in the cutout (voice-over, b-roll): room code only, card in the lower middle.
- Still or drifting camera: the head is tracked per frame (median smoothed); the two transition orders are frozen per transition so cells never flicker.
- Room: open wall, busy shelf, window or lamp: glyph density follows the picture (bright = dense); a plain dark room is stretched (levels printed) so it still reads. Dark clothes keep a floor of brightness so the figure never turns into a hole; the glow eases off when the figure fills the frame.
- Speaker off-centre or two-thirds of the frame: the print front starts at the speaker's core wherever it is; the card follows the face.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (recommended), `words.json`, `clip.json`, `assets/fonts/fonts.css` + woff2 files. No aroll_hi. Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_IN` | the word the print front starts on | a word ('trigger', 'trigger#2'), seconds, or 'auto'. Printed with Whisper and audio onset; if they differ by over 0.15 s check with onsets.py |
| `T_OUT`, `HOLD` | when the picture is back | 'auto' = HOLD (1.7 s) after landing, or the word the picture must be back by |
| `IN_DUR`, `OUT_DUR` | transition lengths | 0.55 / 0.50 s; shorter than 0.4 s starts to look jumpy |
| `PROMPT`, `LINE1`, `LINE2` | the card | the speaker's own words, short and neutral; never a product, app or person's name unless the buyer asks |
| `FONT`, `WEIGHT`, `CASE` | card type | any family in fonts.css (the buyer's caption font); default JetBrains Mono 500 |
| `CODE_FONT`, `CODE_WEIGHT` | the glyphs | keep a monospace face (JetBrains Mono) |
| `INK`, `ACCENT`, `ROOM_INK`, `BACKDROP` | colours | INK = buyer's text colour, ACCENT = buyer's highlight; no orange |
| `TOKENS`, `ACCENT_WORDS` | the words the code is written in | the topic of the line, lower case, 3 to 8 letters |
| `TERM_CENTRE`, `TERM_SCALE`, `SHOT` | overrides | 'auto' unless the printout's choice looks wrong |
| `FACE_BLEND`, `GLINT`, `FRONT` | look | 0.26 real face under the glyphs; 1.0 light on the front; 0.35 front softness |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no card (the reel captions the words; the code look stays). `SFX=0` no sounds. `GRADE=1` a deeper vignette inside the code beat (default off). Frame 0 and the last frame are always the plain a-roll.

## Python
Needs OpenCV: in the Studio run `setup.py --fx code-scan` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, time, place the card, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --sheet <frames it prints>      # 2. quick look -> work/t/sheet.jpg (--frames ... -g for full size + safe lines)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 7 to 20 s per second of slot (4 workers)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, edge colour, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. The front reads as glyphs printing in the picture's own colours, then the lights go down evenly: no dark patch, no blocks.
- The face never under the card; the card inside y 220 to 1470 and out of the right column.
- The figure reads as the speaker (hands, head); the room has texture, not a black void.

## Traps
- Whisper invents or repeats words on quiet audio: check words.json before trusting 'auto'.
- Long LINE1 (over ~18 letters) widens the card and it may not fit beside a close face: keep it short.
- HyperFrames can shift colour about 2 levels against the a-roll: post.py prints the edge difference (render pipeline, not the effect).
- Inside a reel: the card is the only on-screen text of the beat. Keep the reel's captions off the card's spot, or build with CAPTIONS=0.
