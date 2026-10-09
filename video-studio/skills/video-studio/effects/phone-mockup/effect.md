# phone-mockup

**What it does:** a drawn 3D phone (metal frame, glass sheen, edge thickness, soft shadow, slow float) flies in beside the speaker and plays a screen; a touch dot presses on the screen on the speaker's words (ripple, rings, the button flips, rows tick), then the phone leaves.
**Job:** explain (show the screen the speaker is talking about without cutting away from the speaker).
**Trigger phrases:** "put a phone next to me showing the app, tap Approve when I say approve", "show this screen recording on a phone beside me", "phone mockup of this screenshot while I talk".

## First step: what goes on the glass (ask before building)
- **Their own screen:** ask the buyer for the recording (mp4 / mov / webm) or picture (png / jpg) and copy it to `screen/` in the slot (`screen/recording.mp4`). Only a screen that is theirs to show. Set `SCREEN`.
- **No file:** the packaged card (`SCREEN = None`): app name, label, title, up to 4 rows, a button, all typed from what the speaker says in the clip. No numbers, names or claims the speaker does not say. The defaults are placeholders: replace every one.
- Neither a file nor words that fit a card: leave the effect out.

## Footage it needs
- **Shot:** medium or wide is best. Close works when there is 300 px or more of background beside the speaker's head; a close-up that fills the frame gets a smaller phone (down to 250 px), and if even that does not fit build.py stops with "no room for a phone" (use another take or leave it out).
- **Camera:** still or drifting. The phone is fixed to the screen, not to the wall, so a camera that moves a lot makes it read as an overlay (fine) but can swing the speaker across the glass (build.py prints how much the speaker hides).
- **Wall:** none needed. Any background; busy or bright ones get a soft dim behind the phone.
- **Cutout:** layered (`LAYER='behind'`: the phone sits between background and speaker, head and hands pass in front) and measured (side, size and height come from it). `LAYER='front'` needs it only for measuring; with `--no-cutout` type `SIDE`, `PHONE_W`, `PHONE_TOP` by hand.
- **Breaks it:** slots under 2 s (needs 40 frames between in and out, better 75), a tap word in the first 0.6 s or last 0.5 s, a hand that parks in front of the tap point, the speaker walks across the frame. No `aroll_hi`.
- **Edges:** frame 0 and the last frame are the untouched clip (phone in at `IN_FRAME`, gone 12 frames after `OUT_FRAME`), so the slot drops onto the a-roll anywhere.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `SCREEN` | `None` (packaged card) or `'screen/<file>'` | the buyer's file, see first step |
| `SCREEN_START`, `SCREEN_POS` | second of the recording at slot time 0; which part survives the crop to the tall glass | scrub the recording; `'top'` if the action is up there |
| `CARD` | `app, intro, label, title, rows, button, button_done, button_alt, done` | the speaker's words; `''` / `[]` hides a part |
| `CARD_AT` | when the card rises | a spoken word, a frame, or `None` (0.5 s after the phone) |
| `TAPS` | `[(when, where), ...]` | `when`: a word from words.json (`'send#2'` = second time) or a frame number; `where`: `'button'`, `'row1'`.. or `(x, y)` fractions of the glass (`GRID=1` snapshot shows them) |
| `ROWS_FOLLOW_BUTTON` | untapped rows tick themselves after the button | `False` to keep them empty |
| `TURN` | word / frame where the phone turns to the viewer | `None` = off |
| `IN_FRAME`, `OUT_FRAME` | fly-in start, exit start | 3 and `None` (16 frames before the end) |
| `SIDE`, `PHONE_W`, `PHONE_TOP` | `'auto'` or left/right, px, px | leave `'auto'`: side with more room, biggest that fits, level with the speaker's head |
| `LAYER` | `'behind'` or `'front'` | `'front'` when the speaker's cutout is rough or missing |
| `ROOM` | `'auto'`, `'off'` or `dict(scale, x, y)` | tight shots: slides the picture over while the phone is up, back before it leaves |
| `COVER_MAX` | most of the glass the speaker may hide on average | 0.12; lower if the screen must stay readable |
| `HAND_FRAMES`, `MATTE_FIX` | optional cutout repairs, default off | only after seeing a blocky hand edge or a dark block on the glass; re-run prep.py |
| `CAPS`, `CAP_PUNCH`, `CAP_FIX`, `CAP_Y` | the effect's own caption words | `[]` or `CAPTIONS=0` when the reel captions the slot (the usual case) |
| `ACCENT`, `GRADE` | accent colour; CSS filter on the footage | keep `GRADE='none'` or the edges stop matching |

**Switches:** `SAFE=1` safe-zone guide, `GRID=1` fractions on the glass (both snapshots only), `CAPTIONS=0`, `SFX=0`.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: ask the buyer what goes on the phone: their own screen recording or picture (copy it into <slot>/screen/ and set SCREEN), or the packaged card typed from what they say in the clip (SCREEN = None, replace every placeholder). Only a screen that is theirs to show. Neither a file nor words that fit a card = no Phone Mockup: leave it out and say so
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # every word with the frame a tap would land on, where the speaker is
# edit: copy the buyer's file into screen/ (if any), edit the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # soft cutout for the dark phone (+ the screen file cut to the slot), about 1 min
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # prints side, size, bounds, tap frames, warnings (!!) and snapshot times
PY "SK/scripts/fx_run.py" "<slot>" hf lint
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # frame count, plain first / last frame, safe zone, tap points, sheet, stills, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Uses numpy, scipy, Pillow only. A 4 s slot takes about 8 minutes end to end.

## What to look at (work/check/sheet.jpg, tap_*.jpg)
- The tap frame: dot pressed on the target, accent colour on screen within 2 frames, on the speaker's word (not before it).
- The speaker's face is never behind the phone; where the speaker's head or hand crosses it the edge is clean (no light rim, no dark block).
- Words on the glass are readable at phone size; the title does not run off the card.
- Phone inside the safe zone: nothing above y 220, right edge at x 1045 at most (980 below y 1155), bottom above the captions (y 1240).
- First and last frame identical to the clip (check.py prints the difference).

## Traps
- Whisper puts a word's start up to 0.3 s early, and "approve" starts on its weak syllable: taps use the loudest syllable start from the audio. If one looks off, give the frame number.
- Never put `filter` or `opacity` below 1 on the 3D phone nodes (it flattens the edge): blur and fades sit on `#phouter`.
- Background and cutout share the `.cam` class so `ROOM` moves both; a transform on one gives a double image.
- A double edge on the speaker over the phone = cutout frame count drift: re-make the slot.
- Tap fractions are of the visible glass after the crop, not of the original recording.
- On-screen words: the speaker's own, no em dashes, never "free" or "course", no orange accent, no invented numbers or names.
