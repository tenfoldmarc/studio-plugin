# checklist

**What it does:** a dark checklist card builds on screen; each row's text lands as the speaker starts the phrase, its check draws and pops on the word that finishes it, then the card completes (counter pill "3 of 3", full bar, sheen, glow).
**Job:** explain. Turns "it's only N steps / it asks you N things" into something the viewer watches get done.
**Trigger phrases:** "put a checklist on screen for these steps", "tick these off as I say them", "list the three things on a card".

## Footage it needs, and where it fails
- A spoken list of 2 to 5 short items (1 to 4 words each on screen), at least ~8 frames between ticks, and ~0.5s after the last one for the completion beat.
- Best: a wide or medium shot with clear wall above or beside the speaker. The card sits BEHIND the speaker (between room and cutout) and the speaker's cap overlaps its bottom edge.
- Close-up selfie: works, but free room is a narrow column beside the speaker's face, so the card comes out at ~0.5 to 0.7 scale (row text 30 to 43 px). build.py prints the scale and warns under 0.6. Shorter rows give a bigger card.
- Moving camera (handheld): the glass is one blurred still of the room, so it switches to an OPAQUE card by itself when prep.py measures more than 24 px of background drift. The card is screen-fixed, it does not track the wall.
- Fails: no free room at all (the speaker fills the frame edge to edge), lists of 6+, items spoken faster than ~0.3s apart, a hand held high next to the speaker's head for the whole clip (taken for the head top).

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout: needed for LAYER behind and for auto placement), `words.json`, `clip.json`. No aroll_hi. Fonts + stock sounds from the template. No extra Python packages (prep.py uses numpy from the skill's Python; build.py, onsets.py, check.py are plain python3).

## CLIP block (top of build.py)
| Field | What it is | How to get it |
|---|---|---|
| `TITLE` | eyebrow line (shown in caps) | words the speaker says; under ~22 characters |
| `ROWS` | `(text, f_say, f_tick)` x 2 to 5; `*word*` = yellow accent; `a|b` = two-line row (also in `TITLE`), switches to tighter padding for a narrow column | `onsets.py`: `say` of the word that starts the phrase, `tick` of the word that finishes it |
| `F_IN` | card starts building | first frame of speech, or ~20 frames before the first f_say |
| `F_DONE` | completion beat | a stressed word 8+ frames after the last tick, or `None` (= last tick + 10) |
| `F_OUT` | card whips off, or `None` = stays | onset of the next sentence; use it when the slot runs on past the list |
| `CARD_BOX` | `'auto'` or `(x, y, w, h)` the card must fit inside | auto reads work/prep.json; override after looking at the snapshots |
| `LAYER` | `'behind'` / `'front'` / `'auto'` | behind whenever there is room; front only over chest or legs, never the face |
| `OVERLAP` | px the card tucks behind the top of the speaker's head | 40; 0 to keep it clear |
| `GLASS` | `'auto'` / `'glass'` / `'opaque'` | leave auto |
| `ACCENT` | tick colour | butter yellow `#FAE67A` |
| `GRADE`, `VIGNETTE`, `PUSH` | look of the footage in the slot | `''`, `0`, `1.0` when the slot is cut into a reel that grades itself; demo values for a standalone clip |
| `KEEP_OUT` | rects the main reel uses (label pill, caption band) | from the reel brief; auto placement stays out, a hand-placed box gets a warning |

**Silent / fast version (b-roll):** give every row an early `f_say` (all text up front) and ticks ~9 frames apart; the focus bar then follows the ticks. Frames before `F_IN` and after `F_OUT + 8` are the untouched a-roll (cutout layer off).
**Switches:** `SAFE=1` red safe-zone guide (snapshots only), `SFX=0` no sounds, `GRADE=0` no grade or vignette whatever the CLIP block says, `CAPTIONS=0` accepted and ignored (the card text is the caption; the effect draws no captions).

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # add -v for the loudness strip; frames for ROWS, F_IN, F_DONE
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # camera drift, head box, free room -> work/prep.json
# edit: the CLIP block in build.py (Edit tool)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 GRADE=0      # read what it prints: layer, glass/opaque, scale, WARNING lines
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <8+ times: build, each say+0.1s, each tick+0.1s, done+0.15s, end>
PY "SK/scripts/fx_run.py" "<slot>" build.py GRADE=0      # without SAFE
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, phone copy, work/final/sheet.jpg + ticks.jpg + edge.jpg
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A new clip takes about 15 minutes end to end (the matte in fx_new.py is most of it: ~1.3s per frame).

## What to look at in the final frames
- `ticks.jpg`: on tick-1 the ring is empty, on tick+1 the disc is yellow, on tick+3 the check is drawn. Play the phone copy with sound: the pop must sit on the word.
- `sheet.jpg`: frame 0 has no card; every row's text is readable 8+ frames before its tick; last frame shows all rows bright, pill yellow.
- `edge.jpg`: where the speaker overlaps the card there is no light fringe and no double edge; the speaker's face is never under the card.
- Safe zone: no WARNING from build.py, and the card clear of the red guide in every snapshot (largest at the completion pop).

## Traps (each one cost a render)
- Whisper word starts run 1 to 4 frames early. Use onsets.py, and check a soft word after a loud one on the `-v` strip.
- `pop.mp3` has 118 ms of air before its transient: build.py starts each sound early (`SFX_LEAD`), so SFX times mean "when it is heard".
- The counter pill swaps colour with a hard set on the frame. A cross-fade hides the digits for a frame.
- No `backdrop-filter`, no `mask-image` in the renderer: the glass is a baked blurred still (`assets/glass.jpg`).
- A "static" tripod shot can still drift: the approved demo drifts 17 px in its first second. That is inside the glass limit; trust prep.py, not the shot description.
- ffmpeg: `-c:v libvpx-vp9` before `-i` and `alphaextract` before `scale`, or the cutout alpha is lost.
- The card pops to 1.02 and the stage may push in: placement is checked at its largest moment, not at rest. Do not hand-place closer than 36 px to the top safe line.
- A front card over a close-up almost always crosses the speaker's face: build.py warns, believe it.
- `LAYER = 'auto'` takes a big FRONT card over the speaker's body when that is much larger. If the speaker's hands matter (the speaker counts on the speaker's fingers) set `LAYER = 'behind'`.
- Never add `overwrite:'auto'` to a tween: the renderer seeks, the overwrite kills the earlier tween for good (the counter read "2 of 3" from frame 0). Durations shrink to the gap instead.
- Centred medium shot (sofa): the only free room is a ~340 px column beside the speaker's head. Break rows with `|`; expect scale ~0.6 (row text 37 to 39 px).
