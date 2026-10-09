# knockout-tiles

**What it does:** name tiles slam onto the wall behind the speaker, one per spoken word; each is struck out and knocked away (dropped, flicked or shattered) as the next lands. Optional second half: receipts stack up beside the head while a running total counts them, then the pile is struck and falls.
**Job:** explain / proof ("you do not need X, Y or Z", "stop paying for A, B and C", any spoken list that gets crossed off).
**Trigger phrases:** "put these three names on the wall behind me and knock each one out as I say it", "cross them off behind me", "stack the receipts and show what it adds up to".

## First step: only the speaker's own names and amounts
Every tile is a name the speaker says in this clip or the user gave you. Every amount on a receipt is one they said or supplied; the total is added up by the build, never typed. Never invent a name, a price or a count, and never draw a logo: tiles are plain text. No list in the line = leave this effect out. The CLIP defaults ("Tool one", "Receipt", 0) are placeholders; `build.py` warns while they are still there.

## Footage it needs
- **Shot:** wide or medium, with wall around the head. Each tile needs about 400 x 150 px of clear wall beside or above the head, inside the safe zone. Close fails: `prep.py` stops with "no clear wall".
- **Camera:** still. A slow drift is fine (a tile is up for under a second). A moving camera breaks it: the pieces are not tracked to the room.
- **Wall:** beside the head for tiles and receipts, above it for the third tile and the total. No wall above = tiles alternate left / right and the total needs `TOTAL_POS` or stays off.
- **Cutout:** layered and measured. `assets/subject.webm` goes over the pieces, and head position, head movement and the clear wall are read from its alpha. `aroll_hi` is not used.
- **Breaks it:** a cutout that loses hair or keeps a patch of wall (the piece shows through, or is cut by a ghost edge), two people in the shot, big arm swings at head height while a tile is up, a slot that cuts to another shot.
- **Edges:** frame 0 and the last frame are the untouched clip. The effect switches on at `F_IN` (5 frames before the first tile) and is gone by `F_OUT`; it has no grade, dim or push-in.

**Slot inputs:** cutout yes, `aroll_hi` no. Python: numpy, Pillow. No extra packages, no art, stock sounds only.

## The words are the effect itself: STYLE block (top of build.py)
The tiles, receipts and total are not captions, so the reel's captions keep running through the slot (the pieces sit at head height and above, captions lower). `CAPTIONS=0` is accepted and changes nothing. When the reel has a caption or overall style, set the `STYLE` block to it before building: `name_font`, `name_weight`, `name_case`, `name_tracking` (names, receipt titles, total), `small_font`, `small_weight`, `small_case` (label, receipt lines, tag), the colours (`tile_bg`, `tile_text`, `label_color`, `strike`, `paper`, `paper_ink`), `radius`, and `order` (which wall spots are used, in turn). Fonts must be in `assets/fonts/fonts.css`. `width_factor` widens the tiles if another typeface touches the edge.

## CLIP block (top of build.py)
| field | what it is | how to find it |
|---|---|---|
| `TILES` | one dict per tile: `text`, `at` (spoken word, `'word#2'`, or frame); optional `exit`, `spot`, `knock` | `prep.py words`; spoken order; 2 to 5 tiles, each up 9 frames or more |
| `TILE_LABEL` | small line under every name (`''` = none) | what the things are, in the speaker's words |
| `RECEIPTS_ON` | switch for the second half | `False` = tiles only |
| `RECEIPTS` | one entry per receipt: a word / frame, or a dict with `at`, `title`, `item`, `amount` | after the last tile; up to 8 |
| `RECEIPT_TITLE`, `RECEIPT_ITEM`, `RECEIPT_AMOUNT`, `CURRENCY` | defaults for every receipt; text before each amount | whole numbers the speaker said |
| `TOTAL_AT`, `TOTAL_TAG`, `TOTAL_TAG_AT`, `TOTAL_POS` | when the total lands (`None` = no total), tag under it, hand position | the word where they add it up |
| `WIPE_AT`, `F_IN`, `F_OUT` | when the pile falls; first and last frame of the effect | `None` = measured; `F_OUT` at most frames - 2 |
| `WALL`, `SPOTS`, `PILES`, `SIZE` | usable wall box; hand positions; overall size | only when `work/layout.jpg` shows a piece on a window, shelf or furniture |
| `RECEIPT_FIRST_SIDE`, `VOICE`, `SOUNDS`, `SEED` | first pile side, clip audio, sounds, tilt shuffle | defaults |

**Switches:** `SAFE=1` safe-zone guide (snapshots only), `SFX=0` no sounds. `CAPTIONS=0` and `GRADE=0` are accepted and change nothing.

## Run order (PY and SK as in SKILL.md, <slot> = the slot folder; no cd, no shell variables)
```
# first: ask which names go on the tiles and, for receipts, which amounts: only names and amounts the speaker says in this clip or the buyer gave you. Never invent a name, a price or a count, never draw a logo. No spoken list = leave Knockout Tiles out and say so
PY "SK/scripts/fx_run.py" "<slot>" prep.py words      # 1. every word with its frame -> edit STYLE and CLIP in build.py
PY "SK/scripts/fx_run.py" "<slot>" prep.py      # 2. measures the cutout, places every piece -> work/layout.jpg (LOOK)
PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1      # 3. page with the guide; prints every beat and the snapshot times
PY "SK/scripts/fx_run.py" "<slot>" hf lint      # must be 0 errors
PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at <times build.py printed>
PY "SK/scripts/fx_run.py" "<slot>" build.py      # 4. guide off
PY "SK/scripts/fx_run.py" "<slot>" hf render
PY "SK/scripts/fx_run.py" "<slot>" check.py      # 5. frame count, plain edges, face, work/check/sheet.jpg, phone copy
```
`fx_new.py` prints these commands with the real paths filled in and saves them as `RUN.txt` in the slot. `hf render` names the file itself, refuses to run while the red guide is on, and checks the frame count. Last step in a reel: `PY "SK/scripts/fx_add.py" "<project>" "<slot>"`.
After ANY change to the CLIP block run `prep.py` again (`build.py` refuses a layout made for other values). A 6 s slot takes about 5 minutes after the cutout.

## What to look at (work/check/sheet.jpg)
- On its LANDS frame each tile is flat on the wall at resting size (the frame before, it is still flying in, bigger); the strike is drawn before it leaves.
- Pieces pass behind the speaker: hair, ears and hands stay in front, no piece crosses the face.
- Names fit inside their tiles; receipt amounts and the total read at phone size; the final total is the sum.
- Nothing rests above y 220 or below y 1470. First and last frame are the plain clip (`check.py` prints it).

## Traps
- Whisper is 1 to 3 frames off and mishears names: `prep.py words` shows the frame the voice really starts on. Use that word, or the frame.
- The slot must start 6 frames or more before the first name and run 12 frames past the last piece: `build.py` says how many frames it needs.
- A tile that is knocked through the side of the frame crosses the side margin for 3 to 4 frames while fading; resting pieces are always inside the safe zone.
- `prep.py` prints `shrunk to 0.xx`: shorten the name, drop `TILE_LABEL`, or change the spots in `STYLE['order']`. Under 0.8 the name gets small on a phone.
- A hand that waves through a tile's spot is fine (it passes in front). A speaker who leans across it for most of the tile's time moves the tile: look at `work/layout.jpg`.
- Sounds are stock only (`pop`, `whoosh-short`, `impact-bass-1`) at 0.75x template volume. Colours: never orange, never black and white.
