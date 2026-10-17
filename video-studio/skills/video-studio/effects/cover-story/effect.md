# cover-story (Cover Story)

**What it does:** the live shot becomes a magazine cover while the speaker keeps talking: a hairline border draws itself, the picture pushes in 3 percent, a tall serif masthead rises behind (or above) the head, small tracked-caps labels set themselves beside it, and one italic cover line lands on the punch word. It holds as a finished cover, then leaves before the slot ends.
**Job:** hook. A bold one-line claim said to camera.
**Trigger phrases:** "turn this into a magazine cover", "put me on the cover", "cover story when I say X, headline lands on Y".

## Footage it needs
- Shot: wide, medium or close (selfie). Camera: still or handheld drift (the page is fixed to the screen, the cutout follows the speaker). A moving camera (walking, panning) is untested.
- Wall: above the head. It needs about 100 px of picture between the top safe line (y 220) and the top of the head.
- Cutout: layered (masthead and labels go behind the speaker). Needs `assets/subject.webm`; `aroll_hi` optional, preferred.
- Breaks: the head touching the top of the frame (declines); the face so low that both cover-line spots touch it (declines); two people (the cutout layers both); a hand above the head for most of the span (it counts as the head).

## Adapting to the footage (build.py picks the variant and prints why)
- Medium shot, head top around y 350 to 480: BEHIND. Big masthead, the head hides the bottom fifth of the caps (the demo look).
- Wide shot, head well below y 480: CLEAR. Full-size masthead stands above the speaker; labels on the open wall.
- Tight selfie (head wider than 330 px): ABOVE. Smaller masthead between the top line and the head, no kicker, one cover line.
- Head too high for either: stops with "COVER STORY DECLINES: the head reaches y ..." (pass that on; pick a moment with headroom).
- Still camera / handheld drift: same page; the highest head position (5th percentile over the cover) sets the masthead.
- Open wall: cream type with a soft shadow. Busy shelf: deeper shade and shadow behind the type. Window, lamp or white wall (bright): near-black type, no top shade. Plain dark: cream, as the demo.
- Speaker off-centre or two-thirds of the frame: the push-in and the light fall-off centre on the measured face; labels that would land on the speaker move down or are left out; the cover line moves above the face if the face sits low.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `assets/aroll_hi.mp4` (optional), `words.json`, `clip.json`, `assets/fonts/fonts.css` + its woff2 files (the Studio puts them in every slot). Sounds are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `T_IN` | the word the cover arrives on | a word ('video', 'video#2'), seconds, or 'auto'. build.py re-measures the onset on the audio and prints both |
| `T_LAND` | the word the cover line lands on | same ('auto' = the longest word that leaves 1.5 s to read); give seconds when the printed Whisper and audio times differ by over 0.15 s (check with onsets.py) |
| `OUT` | when the cover leaves | 'auto' (plain footage again 3 frames before the end), seconds, or 'cut' (holds; only if the reel cuts right after) |
| `MASTHEAD` | the title | invented, 3 to 6 letters, never a real magazine; build.py prints the letters over the head |
| `LINES` | `(text, style, when)`: 'label-left', 'label-right', 'kicker', 'main' | main = the speaker's own words, `\n` splits, `*word*` takes the accent; labels short invented caps (no names, numbers or outlets); when None = auto |
| `FONT`, `ITALIC`, `WEIGHT`, `CASE` | cover line family / italic / weight / 'upper' 'lower' 'title' 'as typed' | the buyer's caption font from assets/fonts/fonts.css; defaults Playfair Display italic 400 |
| `MAST_FONT`, `LABEL_FONT` | masthead serif, tracked caps | defaults DM Serif Display, Figtree |
| `INK`, `ACCENT` | type colour ('auto' or (r,g,b)), accent word colour | 'auto' picks cream or near-black from the wall; ACCENT = the buyer's highlight colour |
| `FRAMING` | 'auto', 'behind', 'above', 'clear' | leave 'auto' unless the printout's choice looks wrong in the preview |
| `HEAD_TOP`, `ZOOM_CENTRE`, `PUSH` | overrides | 'auto', 'auto', 0.03 |

## Switches
`SAFE=1` red safe-zone guide in index.html (snapshots only). `CAPTIONS=0` no kicker and no cover line (the reel captions it). `SFX=0` no swell or thump. `GRADE=1` a slightly richer print while the cover is up (default off).

## Python
Needs OpenCV: in the Studio run `setup.py --fx cover-story` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, choose the framing, plan, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 75,142,168 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4, 10 to 15 s per second of slot (6 cores)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. Re-run build.py and bake.py after any CLIP change; the render after every bake.

## What to look at (work/qa/sheet_*.jpg)
- First and last frame plain footage (unless OUT = 'cut'). The cover line is up on its word.
- The face never under type; the masthead letters over the head still read (bake.py prints the hidden share: keep it under 30%).
- No white sliver of a letter poking over the hair; nothing readable above y 220 or below y 1470.

## Traps
- Whisper is often 0.2 to 0.4 s off on the landing word. The audio onset build.py prints is the loudness rise after the dip before the word (searched only before the word's loudest moment, so it cannot jump to the next word): the line rises from 0.3 s before it and is up about 8 frames later. If it picked the wrong word, give seconds.
- Fonts come from the slot's assets/fonts/fonts.css. A family that is not there stops build.py with the list of families that are.
- A soft cutout (dark hair on a dark wall) lets the masthead show through the head: check the junction at full size on one frame.
- Letters with a beak at the bottom right (E, L, Z, F) right over the head leave a horn: pick a title whose middle letters end in stems or bowls.
- Inside a reel: the cover line IS the caption. Add the slot with the reel's captions hidden for its span, or build with CAPTIONS=0.
