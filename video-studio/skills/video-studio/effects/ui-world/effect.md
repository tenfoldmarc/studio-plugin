# ui-world

**What it does:** an app screen drops in over the top of the frame and the speaker stands in front of it: the speaker's cutout sits over the screen, the join runs across the speaker's mid-chest, the real room shows in the band below, and the screen plays along with the speaker's words (things land in a message box, a line types and sends, a reply and a step card tick, a result card pops in beside the speaker's head).
**Job:** explain ("all you do is X, then Y"). Works anywhere in a video: as an opener, mid-video on a how-it-works line, or on the payoff. Set `F_OUT` and the screen lifts away again inside the take.
**Trigger phrases:** "put me in front of the app screen", "put me in front of the Claude screen", "show the chat behind me while I explain it", "UI world".

## Footage it needs, and where it fails
- ONE continuous shot, 3 to 6 s, the speaker facing camera, head and shoulders in frame. Wide and medium shots both work: a small head is punched in up to 1.25x and the whole shot slides down so the speaker's head sits under the screen.
- Best when the speaker's head is 150 to 320 px tall in the 1080x1920 slot. Leave 1.5 s after the last thing lands.
- **Fails on:** a tight selfie (head over ~360 px tall: the screen is left with a strip and there is no room band for captions); a speaker who moves a lot up and down or walks (the screen is laid out for the speaker's highest position, nothing is tracked); hands raised above the head (they cut into the message box); a shot that cuts; two people in frame (only the biggest outline is measured); a head already near the bottom of the frame.
- **Cutout quality decides this effect.** A light screen shows every flaw of the speaker's outline. Clothes the same colour as the chair or sofa behind the speaker are the classic miss (shoulder eaten, or a piece of chair kept). Look at the shoulder line before you render.

**Slot inputs:** cutout yes (`assets/subject.webm`), `aroll_hi` no. Python: numpy, scipy, Pillow (the skill's Python has them). No extra packages, no model of its own.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `SCREEN` | `'chat'` (packaged chat-style screen with your text) or the path of your own picture / screen recording | your own app or page only; portrait, 1080 px wide or more; put it in `assets/` |
| `APP_NAME`, `APP_MARK` | chat: name in the header, optional small logo file | your own; `None` = no logo |
| `GREETING`, `PLACEHOLDER` | chat: line on the empty screen, grey text in the box | `None` = none |
| `ATTACH` | `(frame, [1 to 5 labels or picture paths])` things that fly into the box | frame of the word ("drop") from `onsets.py` |
| `TYPE`, `SEND` | `(frame, text)` typed into the box; frame it sends | text max ~30 characters |
| `REPLY` | `(frame, text)` the answer, streams in word by word | needs `SEND`; max ~34 characters |
| `STEPS` | `(title, [(frame, row), ...])` 1 to 4 rows that appear and tick | needs `SEND`; rows max ~30 characters |
| `RESULT` | `(frame, title, picture or None, badge)` card beside the speaker's head | the payoff word; a 9:16 picture works best |
| `LABELS` | `(frame, TEXT, where)` yellow highlighter tags | where = `'attach'`, `'text'` or `(x, y)` off a `SAFE=1` snapshot |
| `F_IN`, `F_OUT` | frame the screen drops in; frame it lifts away | `F_OUT = None` stays to the end |
| `EDGE` | y of the screen's bottom edge (the speaker's chest line) | `None` = measured; set by eye if the pink line in `work/measure.jpg` is off |
| `HEAD_Y`, `ZOOM` | y the top of the speaker's head is moved down to; punch-in | 860 and `None` (measured). Lower `HEAD_Y` number = more room band, less screen |
| `RESULT_SIDE` | `'L'` / `'R'` side for the result card | `None` = the side with more room above the speaker's shoulder |
| `ACCENT`, `HILITE` | button / progress colour; tag colour | your brand colour; butter yellow |
| `CAPTION_FIX`, `CAP_Y` | fix misheard caption words (`''` drops one); caption line y | read the words printed by `onsets.py` |
| `SCREEN_ZOOM`, `SCREEN_X`, `SCREEN_Y`, `SCREEN_SCROLL` | media: size, position, slow scroll of your picture | start at 1, 0, 0, 0 and nudge on a snapshot |
| `SHADOW`, `FIX_EDGE`, `VOICE`, `SOUNDS` | the speaker's shadow on the screen, cleaned cutout, the speaker's audio, sound list | defaults |

Any chat part set to `None` is left out. In media mode the chat fields are ignored; `LABELS` with `(x, y)` and captions still work.
**Switches:** `SAFE=1` draws the safe-zone guide (snapshots only). `CAPTIONS=0` drops the caption words in the room band (the main reel captions it instead). `SFX=0` drops the effect's sounds.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. word onsets as frames -> fill the CLIP block in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measure the speaker + bake the clean cutout (1 to 2 min). LOOK at work/measure.jpg: cyan = head top, yellow = neck, pink = chest line. Pink off the speaker's chest -> set EDGE
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # 3. page with the safe guide; read the WARNING lines it prints
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.2,1.0,2.0,3.0,4.0      # (pick the times so one lands just after each of your frames: frame / 30)
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.

## What to look at in the final frames
- The speaker's outline against the screen at full size: both shoulders complete, no piece of chair or wall kept, no dark or light fringe around hair, cap and hands.
- The join: the screen edge crosses the speaker's chest, and there is no seam or colour step on the speaker's body just below it.
- Each thing lands on its word (pull the word frame and the one before): attachments in the box, the send click, the result card.
- Nothing on the screen hidden behind the speaker's head that has to be read; the result card clear of the speaker's face; the speaker's face never covered (everything on the screen is behind the speaker).
- Safe zone: header under y 220, tags and cards inside the sides, captions above y 1470. First and last frame: with `F_IN` > 0 or `F_OUT` set they must be untouched a-roll. Frame count equals `frames` in `clip.json` (ffprobe it).

## Traps
- The slot's cutout comes from `_shared/rvm_cut.py`. If a shoulder is eaten or furniture is kept, a better matte beats any tweak here: remake the cutout and pass it with `fx_new.py --cutout-from`, then run `prep.py` again. A lower `EDGE` number (join higher on the speaker's chest) hides a bad shoulder line.
- `prep.py` measures the neck from the speaker's outline. A hand by the face, a hood or long hair gives a wrong neck: it prints a warning, set `EDGE` yourself. After changing only `EDGE`, `HEAD_Y` or `ZOOM` there is no need to run prep again.
- The reframe moves and scales the plate and the cutout together, down only. `ZOOM` over 1.25 goes soft on a 1080 slot.
- The screen needs about 12 frames to arrive: start the slot (or set `F_IN`) at least 12 frames before the first thing lands, and drop `GREETING` when the first thing lands inside the first second.
- Whisper word starts are 1 to 3 frames off: use the onset column. Captions use `words.json` as is: fix names in `CAPTION_FIX`. A slot that starts mid-sentence can lose its first word in `words.json`.
- `build.py` stops with a clear message when text does not fit (too many rows, no room for the box). Widths of typed text are estimated, so check a tag placed with `'text'` on a snapshot.
- A screen recording must cover the whole slot and is played from its start at `F_IN`. Do not show a screen, post or page that is not yours. The demo in `example/` was built by hand (other fonts and accent): see `example/clip.md`.
