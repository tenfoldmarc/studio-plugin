# word-pile (Word Pile)

**What it does:** each thing the speaker names drops in as a solid slab with real physics, glances off their head, lands on a drawn floor line with a thud and stacks; on the payoff word one gust blows the pile out of frame and the line leaves.
**Job:** explain / proof. A list of things the viewer no longer needs ("you don't need X, Y, or Z"), then "gone".
**Trigger phrases:** "drop these words on me and pile them up", "word pile on X, Y, Z, blow them away on W".

## Footage it needs
- Shot: wide, medium or close (selfie). Camera: still or handheld drift (the head is re-measured every frame). A moving camera is untested.
- Wall: none needed. The pile sits on the line low in the frame (y 1000 to 1420), drawn over the speaker's body.
- Cutout: measured only (head and outline become the colliders; nothing is layered). Needs `assets/subject.webm`.
- Breaks: the chin so low that no slab fits between it and the line (declines with the reason); a second person (the outline takes both, the head finder the top one); hands above the head for long (they count as the head).

## Adapting to the footage (build.py picks and prints why)
- Medium shot: slabs drop past the head, glance off it, stack at one end of the line; the heavy slab gets the other end to itself (the side with more room beside the head) and slams the line.
- Wide shot: same, the head is a small target so most slabs glance off the shoulders; plenty of room, full-size type.
- Tight selfie: the pile room is the chin to the line. Type shrinks (66 down to 40 px) until the slabs fit in the rows that fit; if a slab on end cannot pass beside the head, SPAWN 'side' tosses them in from the frame edge under the chin (untested on footage: check the preview). No room at all: stops with "WORD PILE DECLINES: the chin sits at y ...".
- Still camera / drift: the head and outline are measured per frame; the line and the pile are fixed to the screen.
- Room (open wall, shelf, window, dark): no change needed: dark slabs carry a faint cream rim and a soft contact shadow, so they read on dark clothes and bright walls.
- Speaker off-centre or two-thirds of the frame: the heavy slab's strip goes to the wider side; drops are searched across the whole safe width.
- No speaker in the cutout (voice-over): the slabs just drop onto the line, nothing to glance off.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (required), `words.json`, `clip.json`, `assets/fonts/fonts.css` + its woff2 files, `assets/sfx/` not used. Sounds (thuds, knocks, gust) are synthesised into `assets_fx/` by build.py (seeded, nothing ships).

## CLIP block (top of build.py)
| field | what it is | how to set it |
|---|---|---|
| `SLABS` | `(text, word, weight)` per slab, in drop order | text = what the speaker names (2 to 5 slabs, short; `\n` = two lines); word = the word it drops on ('budget', 'budget#2', seconds, 'auto'); weight over 1.5 = the heavy accent slab: one, the last |
| `T_SWEEP` | the payoff word the gust comes on | a word, seconds or 'auto' (1.7 s after the last drop). Needs ~1 s after it before the slot ends |
| `SWEEP_DIR` | 'auto', 'left', 'right' | auto = out on the side the pile is nearest |
| `FONT`, `WEIGHT`, `CASE`, `TRACK` | slab type | the buyer's caption font from assets/fonts/fonts.css; defaults Inter Tight 900 caps |
| `INK`, `SLAB`, `ACCENT`, `ACCENT_INK`, `LINE` | colours (r, g, b) | defaults cream on charcoal, butter yellow heavy slab, cream line. ACCENT = the buyer's highlight colour |
| `TYPE_PX`, `FLOOR_Y`, `SPAWN`, `CHIN_Y` | overrides | 'auto' unless the printout is wrong |
| `DROPS` | pin the drops | None = search; paste the printed `drops:` list to keep a pile you liked while changing colours |

## Switches
`SAFE=1` red safe-zone guide in index.html. `SFX=0` no thuds, knocks or gust. `CAPTIONS` and `GRADE` do nothing here: the slabs are the effect and there is no grade. Inside a reel, hide the reel's captions for this slot's span: they sit where the pile is.

## Python
Needs OpenCV: in the Studio run `setup.py --fx word-pile` once (installs requirements.txt). Outside it, in the slot:
`python -m venv work/venv` then `work/venv/bin/pip install -r requirements.txt` (Windows: `work\venv\Scripts\pip`), and use that python as PY.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 1. measure, adapt, search the drops, physics, sounds, index.html. READ the printout
PY "SK/scripts/fx_run.py" "<slot>" bake.py --frames 60,140,175 -g      # 2. preview the frames it suggests -> work/t/ (red lines = safe zone)
PY "SK/scripts/fx_run.py" "<slot>" bake.py      # 3. assets/fx.mp4 (4 workers)
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # 4. 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf render --video-frame-format png
PY "SK/scripts/fx_run.py" "<slot>" post.py      # 5. frame count, phone copy, stills, work/qa/sheet_*.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
HF = `npx --yes hyperframes@0.8.34`. build.py takes 20 s to 2.5 min (about 450 drops tried per slab, 4 workers); bake 6 to 10 s per second of slot (4 workers). Re-run build.py after any CLIP change, then bake and render.

## What to look at (work/qa/sheet_*.jpg)
- Frame 0 and the last frame plain footage. Each slab is in frame on its word and lands within about a second.
- No slab ever over the face; the resting pile below the chin, readable (type up, not buried), inside the safe zone.
- The heavy slab on the line itself; the line dips when it lands; the pile and the line gone before the end.

## Traps
- A slab longer than the gap beside the head only gets past on end, then topples: keep texts short (one or two words; two lines for the heavy one).
- build.py prints "!! no clean drop" when the best try still leans on a wall or floats: shorten that text, drop a slab, or TYPE_PX smaller.
- Whisper can be 0.2 s off: build.py prints Whisper's and the audio's time per slab; give seconds if a slab is early or late (check with onsets.py).
- Two drops closer than 0.3 s are spread to 0.3 s; slabs then arrive a little after their word.
- Same CLIP + same slot = the same pile every run (seeded, fixed-step physics).
