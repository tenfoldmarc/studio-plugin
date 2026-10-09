# the-stack ("The Stack")

**What it does:** the picture snaps down into a rounded window at the bottom of a light dotted page and data cards stack above the speaker: each card drops in on a word and pushes the speaker's window down, its bars race with counting numbers, the winning bar arrives on the word you pick. Then the window grows back to the full frame.
**Job:** explain (compare a few figures while the speaker talks: costs, hours, results, before and after).
**Trigger phrases:** "do the stacked data card layout on this line", "stack the numbers above me", "the stack".

## First step: the figures are the user's own
Every title, label, value and unit in `CARDS` comes from what is said in the clip or from figures the user gives you. Ask for them if the line does not hold them. Never invent, estimate or round up a number, a name, a tool or a ranking: the winning row is the one the user's numbers make the winner. No figures from the user = leave this effect out. The package ships a placeholder and `build.py` stops until it is replaced.

## Footage it needs, and where it fails
- Shot: wide, medium or close. Camera: still, drifting or handheld. Wall: none needed. One speaker with head and shoulders in frame, one continuous take, 3 to 6 s, at least 1.5 s between `F_IN` and `F_OUT`.
- Cutout: only measured, never layered. `measure.py` reads the alpha of `assets/subject.webm` to find the speaker's head, so the window crop centres the speaker's face with a little room above it. With `HEAD` typed by hand the slot needs no cutout (`fx_new.py --no-cutout`). `aroll_hi`: no. Python: numpy, Pillow.
- What breaks it: a very tight selfie (the picture cannot shrink below the window width, so the head stays large and the stack holds about 5 rows in all: `build.py` stops and says how many px to drop); a far-away wide shot (enlarged over 2x, soft); hands above the head, a hood or two people (the head box is wrong: check `work/head.jpg`, type `HEAD`); a speaker who leaves the frame; a shot with a cut in it. A handheld or swaying speaker is fine: the window follows the speaker's head (`FOLLOW`).
- Captions: the layout replaces the whole frame, so the effect draws its own caption words (`CAPS`) on the speaker's chest inside the window. With `CAPTIONS=0` that band stays empty and `build.py` prints it (`caption band: y .. to ..`): the reel's caption for these frames goes there, anywhere else it lands on the cards.
- Edges: every frame before `F_IN - 8` and from `F_OUT` on is the untouched picture. `F_OUT = None` keeps the layout up to the last frame: the reel has to cut on that frame.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `TITLE` | bold line above the cards | the user's words, under 30 characters; `''` = none |
| `CARDS[].title`, `sub` | card heading, small grey line under it | what is compared; the source or the unit in words |
| `CARDS[].rows` | `(label, value)`, 1 to 5 per card, 1 to 3 cards | the user's figures; a string is shown as typed (`'12,400'`) |
| `unit`, `full` | text before / after every value; the value of a full bar | `('$', '')`, `('', '%')`; `full=100` for percentages |
| `win` | row that takes the accent and arrives last | what the numbers say; `None` = all bars accent, no winner |
| `at`, `race`, `win_at` | frames: card landed, bars start, winner arrives | `onsets.py`; the first card always lands on `F_IN` |
| `F_IN`, `F_OUT` | frames: layout landed, plain picture back | `onsets.py`; `F_IN` 8 or more; `F_OUT` up to frames - 1, or `None` |
| `CAPS` | caption words `(frame, 'WORDS')` or `(frame, 'WORD', 'acc')` | words the speaker says, 22 characters or fewer, frames from `onsets.py` |
| `ACCENT` | the one colour (winner bar, number, tick, glow, punch word) | the user's brand hex; not orange |
| `HEAD`, `FOLLOW` | typed head box `(top, centre_x, width)`; window follows the speaker's head | `None` = measured; read px off `work/head.jpg` (half size). `FOLLOW = False` = one fixed crop |
| `ZOOM`, `HEADROOM` | the speaker's size in the window, px of picture above the speaker's head | 1.0 and 40 |
| `CAP_Y`, `SOUNDS` | top of the caption band; sounds | `None` = just under the speaker's chin; `'auto'` or a list of stock sounds |

**Switches:** `SAFE=1` draws the safe-zone guide and the caption band (snapshots only). `CAPTIONS=0` drops the effect's caption words. `SFX=0` drops its sounds. `GRADE=1` puts a light grade on the picture for the whole slot, edges included: only when the reel carries the same grade (default off).

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: get the figures from the buyer: every title, label, value and unit in CARDS comes from what is said in the clip or from figures the buyer gives. Never invent, estimate or round up a number, a name, a tool or a ranking. No figures from the buyer = no Stack: leave it out and say so
PY "SK/scripts/fx_run.py" "<slot>" onsets.py      # 1. word onsets as frames -> F_IN, F_OUT, at, win_at, CAPS in build.py
PY "SK/scripts/fx_run.py" "<slot>" measure.py      # 2. head from the cutout alpha -> work/head.json; LOOK at work/head.jpg
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1 CAPTIONS=0      # 3. page with the safe guide; read what it prints
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.5,1.0,1.5,2.0,3.0,4.0
PY "SK/scripts/fx_run.py" "<slot>" build.py CAPTIONS=0      # 4. clean page (no guide), then render
PY "SK/scripts/fx_run.py" "<slot>" hf render
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
Pick the snapshot times from your own frames (frame / 30): just after `F_IN`, after each card's `at`, each `win_at`, just before `F_OUT - 8`. `build.py` needs no packages; any python with numpy and Pillow runs the other two.

## What to look at in the final frames
- Frame `F_IN - 8` and frame `F_OUT`: the plain picture, no page, no card, no shade. Frame `F_IN`: title and first card landed, the speaker's head whole inside the window.
- Each `at`: the card sits in its place and the window has moved down under it, nothing overlapping. Each `win_at` + 2: the winning number shows the exact figure typed, tick on, the other rows already stopped.
- Every figure on screen against the user's own: same digits, same unit, same label. No row that the user did not give.
- The speaker's face: centred in the window, hair or cap not cut by the window top, chin above the caption words, caption inside the dashed band of the `SAFE=1` snapshot.
- Safe zone: title and cards between y 220 and the window, inside x 90 to 990; caption words above y 1470. The window itself is picture and runs to the bottom of the frame.
- The render has exactly the `frames` of `clip.json` (ffprobe it).

## Traps
- Every card heading costs about 100 px and every row 48: three cards only fit with 2 rows each. `build.py` stops with the number of px to drop.
- The window follows a smoothed track of the top of the speaker's head, so the room behind the speaker moves a little while the speaker stays put. With a typed `HEAD` or `FOLLOW = False` the crop is fixed and uses the highest point the speaker's head reaches.
- The chin is taken as 1.5 head widths under the top of the head (a collar often hides the neck). If the caption sits on a long beard or a raised hand, set `CAP_Y` by hand from the dashed band in the `SAFE=1` snapshot.
- Bars are drawn to scale against the biggest value (or `full`). A value under 3% of it is a stub: that is honest, do not stretch it.
- `win_at` after the layout has left (later than `F_OUT - 8`) leaves the winner still racing at the collapse: `build.py` warns.
- Long labels are cut with an ellipsis at about 25 characters; long values shrink the bars. Shorten the label, never the figure.
- Sounds are stock template sounds at 0.75x volume: a whoosh in, a pop per card, a sparkle on the last winner, a whoosh back.
