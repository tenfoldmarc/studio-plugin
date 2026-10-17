# god-rays (God Rays)

**What it does:** on one word the room drops (at most a stop, colour kept), a warm white light blooms behind the speaker's head and beams fan out around the silhouette, cut by the moving outline. Rim light on the edges, a little dust in the beams, two small lines of type under the face. It falls away in 0.64 s; the rest of the slot is the untouched a-roll.
**Job:** hook or reveal. **Trigger phrases:** "god rays when I say X", "backlight me on this line", "make this the hero moment".

## Footage it needs
- **Context (use it for this, once per reel):** a reveal or a turning point said to camera. "So I built ...", "this changed everything", "all you need is ...", the name of the thing. One short line, 1 to 2.4 s. Not for a running explanation, a list, or a CTA: on an ordinary line it reads as cheese.
- Shot: tight selfie, medium or wide (head at least about 50 px wide). Camera: still or handheld drift (the light is locked to the head every frame). Fast pans untested.
- Wall: around the head (the beams live in the room behind and beside the head; above is best, beside is enough).
- Cutout: layered (the light comes from behind the speaker and the outline cuts the beams). Needs `assets/subject.webm`; `aroll_hi` not used.
- Breaks: nobody in the shot or a head under ~46 px wide (declines); the speaker filling the frame so under 12% of the ring around the head is room (declines); two people (the light goes behind the higher head); a soft cutout (hair on a same-tone wall) gives a softer rim.

## Adapting to the footage (build.py chooses and prints why)
- Tight selfie (head over 330 px wide): the source rises to the crown and is sized at 0.8 head radii, beams x0.8 and a smaller glow, so the light peeks over and round the head and the beams fan up and out without turning the top of the frame milky. Head touching the top of the frame: the source moves down to the head centre so it stays in the picture.
- Medium (150 to 330 px): the demo look. Wide (46 to 150 px): the light scale is at least 60 px, so the beams still reach across the room.
- Still camera / handheld drift: the head is tracked from the cutout every frame (smoothed, jumps over 18% held); the dust follows the room drift (LK track) so it sits in the air.
- Room behind: bright wall (median 120+): one stop down, full beams (demo). Mid-tone: 0.85 stop. Dark room (under 75): 0.55 stop and beams at 72%, so it does not fill with fog. Busy shelf: 0.15 stop more so the beams read over it. Window or lamp: dims with the room, the beams win over it.
- Speaker off-centre or two-thirds of the frame: the source follows the head; the words stay centred on the frame.
- Words: under the chin (default y 1198); a low face pushes them down, then only the serif line fits, then none (the reel captions carry it). Near-black ink if the chest band is bright.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `words.json`, `clip.json`, `assets/fonts/fonts.css` + its woff2 files (the Studio puts them in every slot). Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_IN` | the word the light opens on | a word ('built', 'built#2' for its 2nd time), seconds, or 'auto'. build.py measures the onset on the audio and prints both |
| `T_OUT` | when the light starts to fall | a word (its end), seconds, or 'auto' (end of the phrase 1 to 2.4 s later) |
| `TEXT` | the two lines | 'auto' (T_IN word in caps + the next words in serif), a list of (text, 'caps' or 'serif', when), or [] for none. Speaker's own words only |
| `FONT`, `ITALIC`, `WEIGHT`, `CASE` | serif line | the buyer's caption font from assets/fonts/fonts.css; default Instrument Serif italic 400 |
| `CAPS_FONT`, `CAPS_WEIGHT` | tracked caps line | default Montserrat 500 |
| `INK`, `ACCENT` | caps colour, serif colour | 'auto' / (r,g,b); ACCENT = the buyer's highlight colour (default butter) |
| `TEXT_Y` | caps line centre y | 'auto' or px (serif sits 76 px lower; keep it above 1430) |
| `STRENGTH`, `DIM`, `BEAMS`, `SOURCE` | overrides | 1.0, 'auto', 'auto', 'auto' or (dx, dy) px nudge of the source |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no words. `SFX=0` no air swell, thump or hum. `GRADE=1` the dimmed room leans warm while the light is up (default off).

## Python
Needs OpenCV: in the Studio run `setup.py --fx god-rays` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, choose, plan, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 40,52,70 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 15 to 20 s per second of slot (6 cores)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage. The light opens on the word; the beams come from behind the head, not from the face.
- The face keeps its exposure and is never under type; the words sit under the chin inside y 220 to 1470.
- No bright fringe of undimmed wall round the outline; no fog over the whole frame (lower BEAMS if so).

## Traps
- Whisper is often 0.1 to 0.4 s off: the printed audio onset is what the light uses. If it picked the wrong word, give seconds (check with onsets.py).
- Fonts come from the slot's assets/fonts/fonts.css; a family that is not there stops build.py with the list.
- Used on every other line it stops meaning anything. One per reel, on the reveal.
- Inside a reel: the two lines ARE the caption for that beat. Hide the reel captions for the span, or build with CAPTIONS=0.
