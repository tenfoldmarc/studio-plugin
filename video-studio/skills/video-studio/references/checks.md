# Checks: the footage check, the cutout, the self-check

Nothing in this product was tuned for the buyer's clip. These checks are the safety net. Do not skip them.

## Reels safe zone (1080 x 1920)
- top 220 clear, bottom 450 clear (nothing below **y 1470**), 35 clear on each side,
- the right 100 clear from **y 1155** down (like / comment / share).
- One exception: the Show and Tell speaker card sits flush with the bottom of the video.
`build_reel.py --safe` paints the unsafe area red for snapshots. Never render with it on:
`build_reel.py` without `--safe` right before every render.

## 1. Footage check (before any effect)
`PY "SK/scripts/footage_check.py" "<project>"` checks each picked effect against what `layout.py` measured:
framing, camera movement, open wall, number of shots, and the parts of the reel the buyer allowed.
- `OK`: it fits. The lines under it say what has to be in place first (a cutout, a package, something from the buyer).
- `SKIP`: leave it out. Say the printed line to the buyer. Do not argue the footage into qualifying.
- `CHECK`: the script could not tell. Look at `work/sheets.jpg` and `work/layout/check.jpg` and decide.
The measurements are first guesses (the framing comes from the head width, the camera from how much the room
changes between samples). When your eyes and the script disagree, your eyes win. Say so in the delivery note.

An effect that passes still has to fit the WORDS: no number said means no Odometer, no list means no Checklist.

The last line under an `OK` says which kind the effect is. `ready`: make a slot with `fx_new.py`, fill the CLIP
block, run the commands it prints, add it with `fx_add.py`. `recipe`: adapt the demo build by hand. Both are laid
out step by step in `effects/INDEX.md`. The parts the buyer allowed are enforced three times (`fx_new.py` refuses to
make the slot, `fx_add.py` refuses to add it, `build_reel.py` leaves it out): never work around a refusal, tell the
buyer the one line it prints.

## 2. The cutout: quick or clean
| | Quick: `cutout.py` | Clean: `rvm_cut.py` |
|---|---|---|
| Time | about 7s per second of footage on Apple Silicon, a few times that on other machines | about 1.2s per FRAME: a 20s reel is about 12 minutes |
| Good for | measuring (layout.py does its own small one), Sticky Text | anything BEHIND the speaker or popping out of a card: Bold, Chalk Talk (`--hard`), Show and Tell, most effects. Every ready effect uses this one |
| Weak spot | can take a face in a painting or poster for the speaker; rough hands | slow; needs `setup.py --matting` once (about 105 MB) |

Prefer the clean one whenever an edge will be seen. Tell the buyer the time BEFORE starting, run it in the
background, keep working. One cutout at a time. Only an effect's own frames need matting: `fx_new.py` does that
for a ready effect (a 3 second slot is about 2 minutes), `rvm_cut.py --src` for a recipe.
Both write `assets/subject.webm` and stop with FRAME MISMATCH if it is not frame-for-frame with the cut: then
re-run `assemble.py` and cut again.

## 3. Self-check (after building anything)
Before the render, from snapshots with the red guide (`build_reel.py --safe`, `HF snapshot --at ...`): layout,
readability, safe zone. Pick 5 to 10 moments: one per caption look change, every title, every effect, the last line.

After the render, from the FINAL file:
`PY "SK/scripts/frames_check.py" "<project>" "renders/<file>.mp4" [--at 1.2,3.4]`
writes one picture, `work/check/<file>.jpg` (six frames a row), with the safe zone in red and the face in green.
The green box comes from `layout.json`: if it is not on the face, fix the layout first. Confirm all four:

| Check | Fails when | Fix, or drop |
|---|---|---|
| Nothing covers the face | any caption, card or title touches eyes to chin | rerun `layout.py`, correct `bands` in `layout.json`, or use a one-line style |
| Nothing leaves the safe zone | anything drawn in the red area (except the Show and Tell card) | shorten the text, lower the size in the plan, or drop the element |
| The cutout is clean | halo, missing hand, a poster cut out as a second person, the edge crawling | make the clean cutout; if it is still wrong, switch to a look that needs none |
| Text is readable | pale text on a pale wall, text behind the head hiding more than a third of a letter | a style with a plate or a shadow (Karaoke, Golden Hour), or move the band |

An effect slot adds a fifth check: **its two edges**. Pass `--at` the times `fx_add.py` printed (just inside the
slot at both ends, the middle, just after it). The picture must not jump in brightness or colour going in or coming
out, the captions must not double the effect's own words, no spoken word inside the slot may be left without any
caption (the effect's or the reel's), and the effect has to be gone before the slot ends unless
the slot ends on a cut. `fx_add.py` says whether it could match the slot to the reel; when it says NOT matched,
look twice. If an edge shows, take the slot out (`fx_add.py ... --remove`) and say so.

For a caption style with no overall style the script also prints how much of the unsafe area and of the face box
changed against the raw cut. Above about 1.5% means something is drawn there. It skips those numbers when the look
regrades or moves the picture, and for every frame inside an effect slot (the effect changes the picture on
purpose): then the picture is the only proof.

`check_cuts.py` covers the cuts (frame before / after each cut) and writes the phone copy.

One polish pass, then deliver. If something still fails after one fix, drop that element and tell the buyer what
was dropped and why. A clean reel without the effect beats a broken reel with it.
