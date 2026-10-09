# pull-back-reveal

**What it does:** the live video shrinks into a card inside a plain app window on a light page. Beside it a checklist of the real edit ticks off, the window's timeline strip plays the reel's own shots, and a counter rolls up to its number as everything turns "done". Then the card grows back to full frame.
**Job:** proof ("this video was edited by ...", "here is what it just did", "it took N steps"). Works as a hook line or mid-reel.
**Trigger phrases:** "pull back and show this video being edited", "shrink me into the app window and tick off what it did", "show the edit happening around me".

## First step: only what is true of this reel
Everything the window shows is a claim about the buyer's own edit. Write `STEPS` and `SHOTS` from the reel's own edit list (`edl.json` / `plan.json`: how many clips were transcribed, how many shots were cut, each shot's length in frames, whether captions and sound were added). `COUNT_TO`, `COUNT_LABEL` and `COUNT_NAME` are only what the speaker says in this clip. Never invent a step, a count, a number or a name. The frame total is the sum of `SHOTS`, computed, never typed. The window is plain on purpose: a text title, no logo, no real product's interface. The defaults ("Step one", no shots, no counter) are placeholders and `build.py` warns while they are still there. Nothing true to show = leave this effect out.

## Footage it needs
- **Shot:** wide, medium or close. The whole picture goes into the card (62% size), so the speaker is never cropped.
- **Camera:** still, drifting or moving. Nothing is tracked.
- **Wall:** none.
- **Cutout:** not needed (make the slot with `--no-cutout`).
- **Breaks it:** a face in the left quarter of the picture at mid height (the checklist covers about 170 px of the card's left edge: set `FACE` and the panel moves off it, or the build warns); a head at the very top of the picture (the title bar covers the top 68 px of the clip); anything that matters in the bottom 240 px of the clip (the timeline strip); a slot under about 3.5 s; a slot that cuts to another shot.
- **Edges:** frame 0 and the last frame are the untouched clip. The shrink starts on `F_IN`, the picture is back on `F_OUT`. No grade, dim or push-in of its own (`GRADE=0` is accepted and changes nothing). Exception: `F_OUT = 'cut'` keeps the window to the last frame and the reel must cut to another shot there.

**Slot inputs:** cutout no, `aroll_hi` no. Python: numpy for `onsets.py`, numpy and Pillow for `check.py`; `build.py` needs nothing. No art, stock sounds only.

## The words are the effect itself: STYLE block (top of build.py)
The checklist, window title, status line, counter, label and name are the effect, not captions. When the reel has a caption or overall style, set the `STYLE` block to it BEFORE building: `ui_font`, `ui_weight`, `ui_case` (rows, titles), `mono_font` (tag, status, frame count), `num_font` (digits, badge, name), `label_font`, `label_italic`, `label_case`, the colours (`page`, `window`, `panel`, `ink`, `muted`, `accent`, `done`, `highlight` ...), `radius`, and the placement entries `window_x` and `panel_y`. Fonts must be in `assets/fonts/fonts.css`; `width_factor` widens the fit checks for a wider typeface.
**Captions:** the reel's own captions sit in the middle of the full frame, half off the small card, so they are hidden while the slot plays (`fx_add.py --captions hide`). The effect draws the spoken words on the card instead, from `words.json`, only while the card is small. Set `cap_font`, `cap_weight`, `cap_case`, `cap_size`, `cap_tracking`, `cap_color`, `cap_mark`, `cap_words` to the reel's caption style so the reel keeps one caption look. Limit: the words on the card take typeface, case, size and colour, not a plate behind them and not a word that lights up as it is said: tell the buyer when their style has one of those. Switch: `CAPTIONS=0` draws no caption words (the card then carries no captions unless the reel's own are kept on; those are centred on the frame, not on the card). Keep `F_IN` and the tail after `F_OUT` short: words said while the picture is full frame have no caption.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `STEPS` | 2 to 7 checklist lines, about 22 characters each; `('text', frame)` pins a tick | the reel's edit list; true steps only |
| `SHOTS` | each shot's length in frames, in order (`[]` = one plain bar, no frame count) | `edl.json`: seconds x 30 |
| `WINDOW_TITLE`, `WINDOW_FILE` | text at the right of the title bar; small file name in its middle (`''` = none) | the user's words; plain text |
| `PANEL_TITLE`, `PANEL_TAG` | grey line above the list; pill beside it (`''` = none) | what is doing the work |
| `STATUS_RUN`, `STATUS_DONE` | status word in the strip, before and after `DONE_AT` | defaults |
| `COUNT_TO`, `COUNT_UNIT` | number the counter lands on (`None` = no counter); 1 or 2 characters in the badge | a number the speaker says |
| `COUNT_LABEL`, `COUNT_NAME` | short line under the number; one highlighted word under that (`''` = none) | the speaker's own words |
| `F_IN` | frame the shrink starts (2 or later); landed 12 frames on | just before the line |
| `TICK_FROM`, `DONE_AT` | first tick; last tick = timeline finished = counter lands | `onsets.py`: the word that says it is done |
| `COUNT_AT`, `LABEL_AT`, `NAME_AT` | digits start rolling; label writes on (one frame, or one per word); name wipes in | onsets of those words; `None` = spaced after `DONE_AT` |
| `F_OUT` | `'auto'` (3 frames before the end), a frame, or `'cut'` | leave 12 frames for the way back |
| `FACE` | `(x0, y0, x1, y1)` around the face in the clip, px; the panel is kept off it | a frame of `assets/aroll.mp4` |
| `CAP_FIX`, `CAP_MARK` | misheard caption words `{'heard': 'meant'}`; words in the accent colour | the caption lines `build.py` prints |
| `SOUNDS`, `SEED` | `'auto'`, `[]`, or `(name, frame, volume)` with stock names; bar shuffle | defaults |

**Switches:** `SAFE=1` safe-zone guide (snapshots only), `CAPTIONS=0` no caption words on the card, `SFX=0` no sounds, `GRADE=0` accepted (no grade to drop).

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: read the reel's own edit list (edl.json / plan.json) and write STEPS and SHOTS from it: only steps that were really done and the real length of every shot in frames. COUNT_TO, COUNT_LABEL and COUNT_NAME are only what the speaker says in this clip. Never invent a step, a count, a number or a name, never draw a logo. Nothing true to show = leave Pull-Back Reveal out and say so
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. every word with its frame
# edit: the STYLE block and the CLIP block in build.py (true steps and shot lengths from the reel's edit list)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 2. page with the guide; prints every beat, the caption lines, the snapshot times
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 3. guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 4. frame count, plain edges, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at (work/check/sheet.jpg)
- The whole clip sits in the card; the face is clear of the checklist panel, the title bar and the strip.
- On the DONE frame (not one later): every step ticked, the timeline in the done colour, the frame count at its total, the counter on `COUNT_TO`. The frame before, the last tick is still popping in and the digits are still rolling. Each tick starts two frames before its frame, so it is fully on ON its frame.
- Every text fits its box (rows inside the panel, title inside the bar, label and name left of the window).
- With `SAFE=1`: nothing in the red bands. `build.py` prints the window and panel boxes.
- "before", "back" and "last" are the plain picture (`check.py` prints the difference with the render's overall tone shift taken out); frame count matches `clip.json`.

## Traps
- The slot needs about 105 frames with a counter, label and name, plus 15 for the way back: `build.py` says how many when it is short. Ticks are 4 frames or more apart.
- Text widths are estimated at build time. Another typeface can run wider: look at a snapshot, raise `width_factor`.
- `window_x = 375` gives a wider left column and bigger digits, but the window's lower right corner then sits under the app's buttons (no text is there).
- Whisper word starts are 1 to 3 frames off and it mishears names: use the onset column, fix spellings in `CAP_FIX`.
- Sounds are stock only at 0.75x template volume (`whoosh-short`, `click-soft`, `impact-bass-1`, `pop`). Colours: never orange. `F_OUT = 'cut'` only where the reel really cuts on the slot's last frame; otherwise the window pops off. A 5 s slot takes about 5 minutes (no cutout to wait for).
