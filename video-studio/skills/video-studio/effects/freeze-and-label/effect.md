# freeze-label (Freeze and Label)

**What it does:** the picture freezes on a word while the voice runs on, the room softens and dims behind the speaker, and label chips with leader lines point at spots on the frozen speaker. Then a hard cut back to live.
**Job:** explain (also a hook: "here is who this is" in two labels).
**Trigger phrases:** "freeze the frame on X and label me: A, B", "freeze on that word and tag me", "pause the picture and point out A and B".

## Footage it needs
- **Shot:** wide or medium is best (room beside or above the speaker for the chips). Close works with 1 or 2 short labels and `ZOOM = 1.0`.
- **Camera:** still, drifting or moving: the picture is frozen, nothing is tracked. A moving camera only makes the jump back to live bigger, and the held frame more likely to be blurred.
- **Wall:** beside or above helps (chips go on clear background first). With none they sit over the body, never over the head.
- **Cutout:** layered and measured. The speaker stays sharp over the softened room (baked into the frozen plate), and the head, tie points and open space are measured ONCE on the held frame. `LOOK = 'off'`: only measured.
- **What breaks it:** a blink or motion blur on the freeze word (pick another frame or word), a hood / long hair over the neck / a hand on the head / a head that is not the top of the cutout (no head outline: type `HEAD`), a second person in the cutout, a tight selfie with 3 labels (build.py stops and says how many fit). Hands are found by skin colour sampled from the face: gloves, bare arms, skin-coloured clothes or a hand in front of the chest are missed or misplaced (use chest / shoulder / a fraction point).
- The hold needs about 1 s per label, and 13 frames of live picture after the release.

## Slot inputs
`assets/aroll.mp4`, `assets/subject.webm` (cutout: REQUIRED), `words.json`, `clip.json`. No `aroll_hi`. Fonts (Inter Tight 800, JetBrains Mono 500) and `click.mp3`, `pop.mp3`, `whoosh-short.mp3` come from the template. Python: numpy, scipy, Pillow. The effect ships no pictures or sounds and needs none from the buyer: only their own words for the labels.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `FREEZE` | spoken word the picture freezes on | as `bake_freeze.py` prints it (Whisper's spelling); `'this#2'` = the second "this"; or a frame number |
| `HOLD` | which frame is held | `'auto'` = sharpest of the 6 frames from the freeze word on; or 0 to 5 frames after it. ALWAYS check `work/freeze_pick.jpg` |
| `RELEASE` | word the live picture comes back on | a word or frame at least 13 frames before the slot ends. `None` = stay frozen to the last frame |
| `LABELS[i]` | `(text, word it lands on, what it points at)` plus optional `'left'` / `'right'` for the chip's side | text: the speaker's own words, 1 to 3 words, never a number, result or claim they do not say. word `''` = one after the other. points at: `head`, `cap`, `chest`, `shoulder`, `hand` (or `head_left`, `hand_right` ... as seen on screen), or `(fx, fy)` = a spot as a fraction of the speaker's box |
| `ZOOM`, `DRIFT` | punch-in of the frozen picture, slow push during the hold | 1.12 and 0.03. Wide: up to 1.2. Close: 1.0 to 1.06 |
| `LOOK` | the frozen room: `'subtle'`, `'strong'`, `'off'` | `'subtle'`. Blur and dim only: the frozen picture always stays in full colour |
| `NUMBERS` | the small 01 / 02 tab on each chip | `True`; `False` = text only |
| `ACCENT`, `CHIP`, `INK` | dot and tab, chip and line, text | brand colours, never orange |
| `HEAD` | head box typed by hand `(x0, y0, x1, y1)`, cap to chin | `None`. Only when build.py cannot find the head: read it off `work/hold.jpg` |

## Switches
`SAFE=1` safe-zone guide (snapshots only, never render it). `SFX=0` no sounds. `GRADE=0` no freeze look (same as `LOOK = 'off'`; the live picture is never graded). `CAPTIONS=0` is accepted and changes nothing (no caption words). `COLTEST=1` colour QA build: the held frame untreated at 1:1.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" bake_freeze.py      # print the words with their start frames and check the cutout is finished
# edit: fill the CLIP block in build.py, then build (about 12 s); a line starting with !! is a stop or a warning to act on
PY "SK/scripts/fx_run.py" "<slot>" build.py
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf render      # render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # numbers, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
A 5 s slot takes about 3 minutes end to end once the cutout exists (build 12 s, render 30 s, check 5 s).

## How it ends (the jump back to live)
The frozen frame and the live picture never match, so the jump is made on purpose: the chips whip off sideways, the still inhales for 0.2 s, then a HARD CUT lands on the `RELEASE` word with a cut punch (live picture 1.07 to 1.0 over 10 frames) and a short light flash. Frame 0 to the freeze word is plain live picture, and so is everything from 11 frames after the release. `RELEASE = None`: no way out, the labels stay and the slot ENDS frozen, on a cut. Use that only when the reel cuts to something else right after the slot.

## What to look at (work/check/)
- check.py numbers: frame count, first / last frames plain, the hold really frozen, RESULT: ok.
- `sheet.jpg`: no chip or line over the blue head box, nothing past the red lines, each chip up by its word, last frame plain.
- The first frozen frames against the last live ones: no colour jump (only the flash and the dim). Text reads at phone size (`renders/<slot>-phone.mp4`; build.py prints the text height, under 40 px is small).

## Traps
- `HOLD = 'auto'` takes the sharpest frame, and the sharpest frame is often a blink (it was on the test clip). Eyes cannot be measured here: open `work/freeze_pick.jpg` every time. "held frame is soft" = motion blur warning: try a neighbour or another word.
- The frozen plates are VIDEOS made from the a-roll's own YUV pixels, with its colour tags on ffmpeg's input side. A PNG or JPG still, or tags given as output options, shifts the colour by 3 to 4 levels at the freeze and the release. Do not swap them for stills.
- A label on the freeze word itself cannot start before the freeze: it is readable about 8 frames after the hit. Later labels open on their word.
- No room is a result, not a bug: drop a label, shorten the text or lower `ZOOM`. `!! over the body` = no clear background, look at the plan first.
- An unsided `head` / `shoulder` / `hand` takes the side with more room; a `_left` point always gets its chip on the left, so no line runs over the head.
- Chip widths in the plan are estimates (5% wide). The real chip hugs its text and is pinned by the side its line meets.
- Whisper word starts are snapped to the audio, good to about 3 frames. Freeze early or late in the render: pass a frame number.
- On screen: the speaker's words only, no made-up names or numbers, no em dashes, no orange. Sounds are the stock three at 0.75x.
