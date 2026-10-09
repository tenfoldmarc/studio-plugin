# The effects

One flat list. An effect can go anywhere in a reel. Never present them to the buyer in groups.

Every effect is one of two kinds (the "Kind" column below, `status` in `index.json`):

- **ready**: packaged. `effects/<key>/` holds finished machinery that measures the clip itself, one block of
  settings to fill in (the CLIP block at the top of `build.py`), an `effect.md` with the exact run order, and
  `slot.json` (what it needs and how it behaves inside a reel). You make a slot, fill the CLIP block, run the listed
  commands, check, add it to the reel. You do not rewrite code.
- **recipe**: the finished build of one real reel. Its machinery is reusable, but the block marked CLIP-SPECIFIC at
  the top (frames, words, positions, paths) belongs to that demo and has to be rewritten for the buyer's clip.

The effect folders hold no demo footage, cutouts or sounds: an effect only ever runs on the buyer's own clip. The
only demo footage in the skill is the short preview clips of the Studio Picker (`picker/previews/`,
`captions/previews/`), which are there on purpose so the buyer can see each look before picking it. They are never
used in a reel. An `example/clip.md` in an effect folder is a worked example in words: the settings one demo clip
used, with no footage.

Almost every effect needs the clean cutout (`setup.py --matting`, one time, about 105 MB). Pull-Back Reveal needs
none, and Comment Bubble can run without it (`fx_new.py --no-cutout` and `CHIN_Y` typed in). The Cutout column
below says what each one needs.

## Before you use one (every time)

1. **Footage check.** `PY "SK/scripts/footage_check.py" "<project>"` checks the picked effects against what was
   measured on this clip. `SKIP` means leave it out and tell the buyer the one line it prints. `CHECK` means look at
   the frames yourself. Never force an effect onto footage that fails. The lines under an `OK` say what has to be in
   place first: `setup.py --matting` (the clean cutout, one time, about 105 MB), `setup.py --fx <key>` (extra
   Python packages for that effect, one time), or something from the buyer.
2. **Parts.** When the picks carry `effectSections`, an effect may only go in the parts the buyer allowed
   (hook = the opening line, end = the call to action, middle = the rest). The footage check prints the time window
   of each part. `fx_new.py`, `fx_add.py` and `build_reel.py` all enforce it: a slot outside its parts is refused
   or left out, with the reason.
3. **Only where it fits the words.** An effect lands on a line that calls for it (a number for Odometer, a list for
   Checklist, the comment keyword for Comment Bubble). No line that fits means no effect, even if it was picked.
   One or two effects in a short reel is plenty.

## A ready effect

An effect slot is a small project of its own: it takes N frames of the reel and hands back the same N frames with
the effect applied (1080x1920, 30fps). The reel build lays that render over the reel for exactly those frames.

```
1. PY "SK/scripts/fx_new.py" <key> --project "<project>" --from <sec> --to <sec> [--hi]
       Reel seconds. Start about 0.1s before the first word the effect reacts to, end about 1.5s after it lands
       (or on a cut). It makes <project>/fx/<key>/ with the effect's scripts, the slot's frames, the reel's own
       words cut to the slot, fonts, sounds, and the speaker cutout (cut from the reel's cutout when there is one,
       else it mattes only the slot's frames: about 1.2s per frame, tell the buyer first).
       It prints the commands for this effect with the real paths filled in, and saves them as RUN.txt in the slot.
       Example snapshot times that would run past the end of this slot are spread over the slot for you.
       A line starting with CHECK layout.json means the slot's clean cutout and layout.json disagree about where
       the head is by more than 60 px: look at work/layout/check.jpg and run layout.py again before going on.
2. Read <slot>/effect.md. Fill the CLIP block at the top of <slot>/build.py with the Edit tool. Follow the
   "in a reel" lines fx_new.py printed (no grade of its own, leave before the slot ends, and so on).
3. Run the printed commands in order. They all look like this:
       PY "SK/scripts/fx_run.py" "<slot>" measure.py              one of the effect's own scripts
       PY "SK/scripts/fx_run.py" "<slot>" build.py SAFE=1         switches are plain NAME=value words
       PY "SK/scripts/fx_run.py" "<slot>" hf lint
       PY "SK/scripts/fx_run.py" "<slot>" hf snapshot --at 0.4,1.2,2.0     LOOK at <slot>/work/snap/contact-sheet.jpg
       PY "SK/scripts/fx_run.py" "<slot>" build.py                guide off: always the last build before a render
       PY "SK/scripts/fx_run.py" "<slot>" hf render               -> <slot>/renders/<slot folder>.mp4
   The render refuses to start while the red guide is on, and checks the frame count afterwards.
4. PY "SK/scripts/fx_add.py" "<project>" "<slot>"
       Checks the render, copies it to <project>/assets/fx/, and writes the slot into plan.json: its frames, what
       happens to the reel's captions, a small brightness lift so the slot matches its neighbours, and the
       effect's own sounds.
5. PY "SK/scripts/build_reel.py" "<project>", lint, render, then the self-check on the slot's moments and both of
   its edges: PY "SK/scripts/frames_check.py" "<project>" "renders/<file>.mp4" --at <the times fx_add.py printed>.
   Nothing on the face, nothing in the red area, clean cutout edge, readable text, no jump in or out of the slot.
   Fix it (one pass) or take it out: fx_add.py "<project>" "<slot>" --remove, and tell the buyer why.
```

A second slot of the same effect: add `--name <folder>` to `fx_new.py`. `--hi` also cuts the slot from the original
clip at its own size (Digital Zoom stays sharp that way). Two slots can never share frames.

An effect that lives ON a cut (Zoom-Through Cut): give `fx_new.py` a span ACROSS one cut of the reel, about 0.5s on
each side (the footage check prints where the cuts are). The slot then holds both shots and knows the cut frame.
Every other effect needs one continuous shot: `fx_new.py` refuses a span that crosses a cut.

## A recipe

1. Copy `SK/effects/<key>/` (and `SK/engine/fonts` as `assets/fonts`, plus the two files in `SK/engine/template/`)
   to `<project>/fx/<key>/`. Cut the frames the effect covers into `fx/<key>/assets/aroll.mp4` with ffmpeg
   (exactly N frames, 1080x1920, 30fps, from `<project>/assets/aroll.mp4`), and its words into `words.json`
   (times counted from the start of the slot).
2. Rewrite the CLIP-SPECIFIC block from the buyer's footage. Where a build reads a tool by a fixed path, use `ffmpeg`
   / `ffprobe` from PATH and `PY` for Python. Paths that start with `FXLAB/`, `WORKSPACE/` or `HOME/` are the demo's
   own files: replace every one. Helper scripts ending in `.sh` are the demo's shell notes: run the same ffmpeg /
   HyperFrames commands directly (they work the same on Windows), do not run the `.sh` file.
3. Build, lint, snapshot, render the slot with `PY "SK/scripts/hf.py" "<project>/fx/<key>" <command>` (the folder
   comes first, it runs inside it): the slot is a full-frame 1080x1920
   render with exactly the same number of frames it was given.
4. Add it to `<project>/plan.json` by hand and run `build_reel.py` again:
   `"slots": [{"key": "<key>", "src": "fx/<key>/renders/slot.mp4", "from": 3.2, "to": 6.4, "captions": "hide"}]`
5. Self-check the slot from the final render, as for a ready effect.

## Captions, sound and parts around a slot

- **Captions.** Each ready effect says what the reel's own captions do while it plays (`reel_captions` in its
  `slot.json`): `hide` when the effect carries the words itself or sits where the captions go, `keep` when it stays
  out of their way. `fx_add.py --captions keep|hide` overrides it for one slot. When an effect's own words cover
  only part of the slot, hide the captions for just that window: `fx_add.py ... --hide-captions 3.9-4.9`.
  Before and After, when it is built with its own words on (a reel with no captions), works its own window out
  and `fx_add.py` applies it without a flag. `fx_add.py --caption-y N` keeps the reel's captions on but moves
  the top of their line to screen y N while the slot plays. An effect that needs the chest for itself prints the
  value in its build. The same value is right for every caption style, and the move happens on a caption change,
  never in the middle of a caption.
  Check in the slot snapshots that no spoken word is left without a caption.
- **The buyer's caption style wins.** See "Restyling an effect's own words" below. No effect brings its own
  caption look into a reel that has a style.
- **Sound.** The voice always comes from the reel's own cut, so there is no audio seam. The effect's own sounds are
  read from the slot and replayed in the reel. `--no-sfx` leaves them out.
- **An overall style.** A slot laid over an overall style gets the style's colour grade but not its push-ins or
  reframing. Look at both edges of the slot. If it jumps, drop the effect for that reel.
- **Cutouts.** "clean" means `rvm_cut.py` (about 1.2 seconds per frame; `fx_new.py` mattes only the slot's frames).
  "quick" means `cutout.py` is enough. The clean one needs `setup.py --matting` once.
- Everything shown on screen is real (the buyer's own numbers and reels) or a generic placeholder. Never a real
  person, never made-up proof, no like or view counts that were not given.

## Restyling an effect's own words (the buyer's style wins)

The rule is at the top of SKILL.md. The effects in the table below can put words on screen. In a reel that has a
caption style (or a style the buyer showed or described) they never keep their own caption look. An effect that
draws words and has no row here yet follows the same rule: read its `effect.md`, decide which of the two kinds
its words are, and add what you find to the slot.

- **Words that only repeat what is said: turn them off.** The reel's captions carry the words in the buyer's
  style. `fx_new.py` already prints the build commands with `CAPTIONS=0` for those effects.
- **Words that are the effect: restyle them** to the buyer's style before the first build. Typeface, case, weight,
  colours, plate or no plate. The slot is the buyer's own copy of the effect, so edit its `build.py` freely.
- Everything else in an effect is open too: sound level (`SFX_GAIN`, `SOUNDS`, `SFX=0`), motion strength (`PUSH`,
  the scales in `ZOOMS`), timing (the frame and second values in the CLIP block), colours (`ACCENT`, `GRADE`).

| Effect | Its words | Switch that turns them off | Where the look is set in the slot's `build.py` |
|---|---|---|---|
| Before and After | repeat speech (the after-side captions). The two tags are the effect | `CAPTIONS=0` (the default in a reel; the tags stay) | Tags: `LABELS`, `LABEL_Y`. Own captions, only for a reel with no captions: `CAPS`, `CAP_Y`, `CAP_FS`, `ACCENT`, `PUNCH`; typeface in the `font-family:'Inter Tight'` rules at the end of the page template |
| Orbit | repeat speech | `CAPTIONS=0` (the default in a reel), then `fx_add.py --caption-y <printed value>` | Own captions, only for a reel with no captions: `CAPS`, `CAP_Y`, `CAP_LINE` (sizes); typeface in the `.cap` css rules |
| The Stack | caption words repeat speech. The title and the cards are the effect | `CAPTIONS=0` for the caption words (the default in a reel), then `fx_add.py --caption-y <printed value>` | Title and cards: `TITLE`, `CARDS`, `ACCENT`, and the `font-family:'Inter Tight'` rules in `PAGE`. Caption band: `CAP_Y`, `CAP_H` |
| UI World | the caption line repeats speech. The screen and the tags are the effect | `CAPTIONS=0` for the caption line (the default in a reel), then `fx_add.py --caption-y <printed value>` | Tags: `LABELS`, `HILITE`. Screen: `ACCENT`, `INK`, and the font rules of the screen css. Caption line: the `.cap` css rule, `CAP_Y` |
| Checklist | the effect (a title and rows) | none | `TITLE` (drawn in caps by `.upper()` in the eyebrow line), `ROWS` (`*word*` = accent word), `ACCENT`, `GLASS`, row size `FS`, place `CARD_BOX`. Typeface: `font:600 26px ... Montserrat` (eyebrow) and the two `font:800 ... 'Inter Tight'` rules (rows, pill) |
| Comment Bubble | the effect (the typed keyword, the comment, the reply, the chip) | none | The style lines at the end of the CLIP block: `WORD_FONT`, `TEXT_FONT` (css family, weight, font file), `UPPER`, `ACCENT_COL`, `LIGHT_COL`, `DARK_COL`. Size and place: `SCALE`, `DROP`, `X_CENTER` |
| Freeze Sticker | the effect (handwritten notes, a stamp) | `CAPTIONS=0` = no notes or doodles | `NOTES`, `STAMP`, `INK`, `ACCENT`, `PAGE`, `SIZE`, `PLACE`. Typeface: `.note{font-family:'Caveat'}` and the stamp rule (`'Inter Tight'`, `text-transform:uppercase`) |
| Spotlight | the effect (the key words) | `CAPTIONS=0` = lights only: then add the slot with `--captions keep` and the reel's captions carry the words | `KEYWORDS` (each row has its own text and colour: type the text in the style's case), `FONT` (the file the words are measured with) together with the `.kw{font-family ...;font-weight ...}` css rule |
| Green Screen | repeat speech. The speaker is shrunk to the bottom, so the reel's normal caption line would land on the face | `CAPTIONS=0` (the default in a reel), then `fx_add.py --caption-y <printed value>`: the reel's captions move to the line above the head | Own captions, only for a reel with no captions: `CAPS`, `CAP_KEY`, `CAP_WORDS`, `CAP_PLATE`, `CAP_PX`, `CAP_GAP` (lowercase, typeface in the `.cap` css rule). More room above the head: `SIZE = 'small'` |
| Blackout | the effect: one punch word behind the head, a word the speaker says | `CAPTIONS=0` = no word (the dim, flash, kick and snap stay, the reel's captions say the word). With the word on, hide the reel's caption for that one word (`--hide-captions a-b`) | the `WORD STYLE` block under the CLIP block in `build.py`: `WORD_FONT`, `WORD_FONT_FILE`, `WORD_WEIGHT`, `WORD_ITALIC`, `WORD_CASE`, `WORD_TRACK`, `WORD_COLOUR`, `WORD_GLOW`, `WORD_PLACE`, `WORD_SIZE` |
| Knockout Tiles | the effect (name tiles, receipts, total). The reel's captions keep running | none needed: nothing covers the captions | the `STYLE` block at the top of `build.py`: `name_*` and `small_*` (typeface, weight, case, tracking), `tile_bg`, `tile_text`, `label_color`, `strike`, `paper`, `paper_ink`, `radius`, `order`. Another typeface may need `width_factor` |
| Pull-Back Reveal | the effect (window title, checklist, counter, label). It also draws the spoken words on the small card, because the reel's captions are hidden while the slot plays | `CAPTIONS=0` = no spoken words on the card | the `STYLE` block at the top of `build.py`: `ui_font`, `ui_weight`, `ui_case`, `label_font`, `label_case`, the colours (`page`, `window`, `panel`, `ink`, `accent`, `done`, `highlight`), and for the spoken words `cap_font`, `cap_weight`, `cap_case`, `cap_size`, `cap_color`, `cap_mark`: set those to the buyer's caption style. Limit: the words on the card take typeface, case, size and colour, not a plate behind them and not a word that lights up as it is said. Tell the buyer when their style has one of those |
| Timeline Burn | the effect (track labels, timecodes). The reel's captions keep running | none needed. The timeline sits in the chest band: add the slot with the `--caption-y` value `build.py` prints, or `--captions hide` when it says there is no room | the `STYLE` block at the top of `build.py`: `FONT`, `WEIGHT`, `CASE`, `TEXT`, `LABEL_PX`, `NAME_PX`, `ACCENT`, `PANEL`, `PANEL_EDGE`, `PALETTE`. Set `DIM = 0` when the buyer's style is already dark or they do not want the room dimmed |
| Type Wall | the effect (the wall of words) | none | `PHRASES`, `FS`, `INK`, `ACCENT`, `GROUND`, `ACCENT_Y`. Typeface: its own `@font-face` (`'Inter Tight Wall'`) and the `.wd` rule. The wall is drawn in capitals |

Comment Bubble is the one with a ready style block. In the other effects made of words the typeface sits in css
rules inside `build.py`: change the family and weight there, keep the size variables, and look at the slot
snapshot, because text widths were tuned for the default typeface (lower `FS` or the size value when a word no
longer fits). Every font the caption styles use is already in the slot: `<slot>/assets/fonts/`, named
`<Family>-<weight>-<normal or italic>.woff2`, declared in `assets/fonts/fonts.css`.

The type facts of the caption styles, for matching:

| Caption style | Main words | Second voice (marked words, titles) | Case | Colours | Plate |
|---|---|---|---|---|---|
| Arcade | Pixelify Sans 600 / 700 | | as spoken | white | none |
| Low Key | Figtree 500 / 600, small | title pill: Barlow Condensed 500 | as spoken | white; pill text #141414 on white | the title pill only |
| Field Notes | Newsreader 400 | | as spoken | white | none |
| Anchor | Inter Tight 800 | Playfair Display italic | as spoken | white | none |
| Loud Lowercase | Arimo 700 | | lowercase | white | none |
| Vanity | Instrument Serif 400 | the same, italic | as spoken | cream #FFF4BE, marked words yellow #FFE25F | none |
| Bubblegum | Arimo | title: Elsie Swash Caps 900 | lowercase | pinks #F8BBD8 / #FFE0EF | none |
| Moodboard | Poppins 700 | Instrument Serif italic | lowercase | white | none |
| Golden Hour | Newsreader 500 italic | | as spoken | gold #F8CB45 | none |
| Spec Sheet | Archivo 900, wide (stretch 125%) | tags, same face | capitals | white, tags yellow #FFEB00 | none |
| Bold | Inter Tight 800 / 900 | the same, giant | lowercase | white, big words yellow #FAE67A | none |
| Cool Girl | Inter 500 | Instrument Serif italic | lowercase | cream #FFF8EF, big line yellow #FAE67A | none |
| Cool Dude | Montserrat 500, small and wide | DM Serif Display | capitals over a serif word | off-white #F7F4EE | none |
| Karaoke | Archivo 900, wide (stretch 125%) | | capitals | cream #F4EDE0, the spoken word yellow #FAE67A | frosted dark plate, rounded (rgba(21,21,23,.62), radius 26) |
| Signature | Archivo 900, wide, italic | Marck Script | capitals | cream #F5D9BF, script white | none |
| Keyword | Inter Tight 800 / 900 | | lowercase | white, marked words yellow #FAE67A | none |
| Weight Shift | Inter 300 | Inter Tight 900 | as spoken | white | none |
| Terminal | JetBrains Mono 500 | Instrument Serif italic | as spoken | white | none |
| Outline | Bebas Neue | the same, drawn hollow | capitals | white | none |

When a detail matters and this table is not enough, read the style's own function in `SK/engine/captions.py`
(read only). A buyer's own style goes over this table. When they have one (`ST/my-style.json`, built from an
example or a description, `references/replicate.md`), the reel's captions are their own custom spec, not one of
these: restyle an effect's words to the values in that spec (`font`, `weight`, `case`, `color`, `accent`, `plate`).

## The list

<!-- LIST:START (generated from index.json, do not edit by hand) -->
26 ready, 0 recipe.

| # | Effect | Key | Kind | What it does | The buyer says | Framing | Camera | Wall | Cutout | Tracking | Extra packages |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Orbit | `orbit` | ready | Your own reels circle around you, passing behind and in front. | "put my reels in orbit around me" | wide or medium | still or drifting | no need | clean | none (prep.py measures the ring from the cutout; the ring follows the head) | none |
| 5 | Frame Break | `frame-break` | ready | The video shrinks into a card and your head and hands pop out of it. | "shrink the video into a card and let me break out of it" | wide or medium | any | no need | clean | none (prep.py measures head, body and hands from the cutout) | none |
| 6 | Type Wall | `type-wall` | ready | Giant words march behind you and swap on the word you say. | "put giant words behind me that change as I talk" | wide or medium | still | clear wall above the head | clean | none (prep.py measures the head; the wall is locked) | scipy |
| 8 | Digital Zoom | `digital-zoom` | ready | A slow creep onto your face, a hard snap on a key word, a whip back out. | "punch in on my face when I say X" | any | any | no need | clean | face (track.py) | none |
| 16 | Headline Wall | `headline-wall` | ready | The wall behind you fills with headline and post cards, the key word highlighted. | "fill the wall behind me with headlines about X" | wide or medium | any | open wall beside the speaker | clean | room track (prep.py) | scipy |
| 17 | Zoom-Through Cut | `zoom-through-cut` | ready | The camera dives through you and comes out in the next shot. | "make that cut a zoom-through" | any, two shots back to back | any | no need | clean | none (prep.py finds the dive points) | scipy |
| 18 | Clone | `clone` | ready | More of you pop up beside you on the words, then sync up for the payoff. | "clone me when I say like this, like this" | wide | still | open room on both sides | clean | room drift lock (bake.py) | scipy |
| 2 | Couch Wall | `couch-wall` | ready | Your reel covers become a grid on the wall behind you. | "put my reels as a grid on the wall behind me" | wide or medium | still or drifting | clear wall above the head | clean | room track, wall and furniture found by colour (prep.py) | scipy |
| 3 | UI World | `ui-world` | ready | An app screen fills the frame and you stand in front of it. | "put me in front of the Claude screen" | wide or medium | still or drifting | no need | clean | none (laid out for the speaker's highest position) | scipy |
| 7 | The Stack | `the-stack` | ready | Data cards with racing bars stack above you, you sit in a window below. | "do the stacked data card layout on this line" | any | any | no need | clean | none (measure.py finds the head from the cutout; the window follows it) | none |
| 9 | Sticky Text | `sticky-text` | ready | A tag glued to your cap or chest that moves, tilts and scales with you. | "stick a tag that says X to my cap" | any | any | no need | clean | head and chest followed frame by frame from the cutout (track.py) | scipy |
| 11 | Spotlight | `spotlight` | ready | The room goes dark and out of focus, you stay lit, the key words land big, the lights come back up. | "put a spotlight on me when I say X" | any | any | no need | clean | none (prep.py measures the head on every frame; the light follows it) | scipy |
| 13 | Freeze and Label | `freeze-and-label` | ready | The picture freezes while you keep talking, tagged lines point at you. | "freeze the frame on X and label me: A, B" | any | any | no need | clean | none (the picture is frozen: everything is measured once on the held frame) | scipy |
| 14 | Phone Mockup | `phone-mockup` | ready | A 3D phone flies in beside you playing a screen, taps land on your words. | "put a phone next to me showing the app" | any | still or drifting | no need | clean | none (build.py finds the side with more room from the cutout) | scipy |
| 15 | Checklist | `checklist` | ready | A card builds on the wall and each step ticks as you say it. | "put a checklist on screen for these three steps" | any | any | no need | clean | none (prep.py measures the clip) | none |
| 21 | Pointer Callout | `pointer-callout` | ready | Cards tied to you by lines that stretch and swing as you move. | "put callout cards on these three things and tie them to me" | any | any | no need | clean | head, chest, shoulders and hands followed frame by frame from the cutout (track.py) | scipy |
| 10 | Odometer | `odometer` | ready | Numbers roll up digit by digit like a mileage counter. | "roll the numbers up like an odometer when I say X" | any | any | no need | clean | none | none |
| 19 | Before and After | `before-and-after` | ready | A wipe line sweeps across your raw clip to reveal the edited version. | "do a before/after wipe on this line" | any | any | no need | clean | none (measure.py finds the head; both sides are the same frames) | none |
| 20 | Chart Grow | `chart-grow` | ready | A line chart draws on the wall behind you and kicks up on your word. | "draw a growth chart behind me that takes off when I say scale" | wide or medium | still or drifting | open room on both sides | clean | wall track for a drifting or handheld shot (measure.py); pinned on a still camera | scipy |
| 4 | Freeze Sticker | `freeze-sticker` | ready | Your freeze frame becomes a die-cut sticker with handwritten notes. | "turn me into a sticker on this line" | any | any | no need | clean | none (one frame is frozen; bake.py measures its outline) | scipy |
| 12 | Comment Bubble | `comment-bubble` | ready | The comment keyword types itself, posts, and your reply with the link lands. | "show the comment being typed and my reply when I say comment X" | any | any | no need | clean | none | none |
| 26 | Green Screen | `green-screen` | ready | You are cut out and shrunk to the bottom of the frame, and the whole screen behind you becomes the thing you are talking about. | "green screen me over this video" | wide or medium | any | no need | clean | none (prep.py reads head top, chin, head width and the body's cut-off row from the cutout) | scipy |
| 25 | Knockout Tiles | `knockout-tiles` | ready | Name tiles slam onto the wall behind you one per word, each gets struck out and knocked away; receipts can then stack up with a running total. | "put these names on the wall behind me and knock each one out as I say it" | wide or medium | still or drifting | open wall beside the speaker | clean | none (prep.py reads the head, its movement and the clear wall from the cutout) | none |
| 23 | Timeline Burn | `timeline-burn` | ready | A video-editing timeline assembles in front of you, overheats, catches fire on your word and crumbles into embers. | "put an editing timeline on screen and burn it when I say X" | wide or medium | any | no need | clean | none (build.py reads the head box from the cutout; the timeline is a screen overlay) | scipy |
| 22 | Blackout | `blackout` | ready | The room dims on your line while you stay lit, the punch word slams in behind your head, and the lights snap back on the next line. | "dim the room when I say X and bring the lights back on the next line" | any | any | no need | clean | none (prep.py measures the head while the room is dim; the word is fixed on screen) | scipy |
| 24 | Pull-Back Reveal | `pull-back-reveal` | ready | The live video shrinks into a card inside an app window: a checklist of the real edit ticks off, the shot timeline plays, a counter rolls up to the number you say. | "pull back and show this video being edited" | any | any | no need | none | none (the whole picture goes into the card; nothing is measured) | none |

## Per effect: what the buyer has to give you, and what to watch

- **Orbit** (READY, `effects/orbit/`: build.py, effect.md, onsets.py, prep.py, slot.json). Needs from the buyer: a folder of the buyer's own reel cover images (at least 4, 6 fills the default ring). Real view counts only if the buyer gives them. Speaker centred, wide or medium, chin above about y 1000 so a card fits under the face. Fails on a close-up selfie, a speaker who fills the frame width or sits far off centre, a hand held above the head, a weak cutout and a walking camera. Without the buyer's own covers the effect is left out.
- **Frame Break** (READY, `effects/frame-break/`: build.py, check.py, effect.md, onsets.py, prep.py, slot.json). Needs nothing from the buyer. One continuous shot, 3 to 6 s, head in the upper half with room above it. Best with a hand gesture that reaches sideways at chest height or higher; without one it still works as a head pop-out. Weak on a tight close-up and when the head touches the top of the frame. Needs a cutout that keeps hair and fingers. A hood or long hair over the shoulders needs HEAD typed in.
- **Type Wall** (READY, `effects/type-wall/`: assets_fx, build.py, effect.md, example, onsets.py, prep.py, slot.json). Needs nothing from the buyer. Locked camera only. Needs clear room above the head (head top at y 250 or lower in the frame). It replaces everything behind the speaker: furniture the speaker sits on has to be drawn in KEEP. Best on a short line with one word that matters; a word over about 7 letters does not fit.
- **Digital Zoom** (READY, `effects/digital-zoom/`: bake.py, build.py, clipblock.py, effect.md, example, onsets.py, post.py, slot.json, track.py). Needs nothing from the buyer. One continuous shot with the face visible the whole time. With --hi a 1728 px source stays sharp to 1.6x; from a 1080 source every zoom is an upscale (capped at 1.5x).
- **Headline Wall** (READY, `effects/headline-wall/`: build.py, cards.py, effect.md, example, onsets.py, prep.py, slot.json). Needs from the buyer: the topic. Card text is written for the reel: generic outlets and placeholder names, never a real publication, person, number or made-up proof. One continuous shot, 3 to 6 s, with visible wall beside or above the head. A moving camera is tracked. A window, mirror or open doorway behind the speaker breaks the track. A tight selfie has no room for the big cards.
- **Zoom-Through Cut** (READY, `effects/zoom-through-cut/`: bake.py, build.py, effect.md, example, prep.py, slot.json, two_shot.py). Needs nothing from the buyer. Needs two different shots back to back (a real cut in the edit, not one continuous take), the speaker in both, and something dark and plain on the speaker to dive into. A cut in the middle of a word fights the move.
- **Clone** (READY, `effects/clone/`: bake.py, build.py, check.py, effect.md, example, prep.py, slot.json). Needs nothing from the buyer. Needs room on both sides and a furniture edge (sofa back, desk, counter) with wall above it for the clones to stand behind. No close-ups, no moving camera.
- **Couch Wall** (READY, `effects/couch-wall/`: build.py, effect.md, onsets.py, prep.py, slot.json). Needs from the buyer: a folder of the buyer's own reel cover images (at least 4, 9 or more looks best). Real view counts only if the buyer gives them. Needs a plain one-colour wall in the upper frame. Fails on a tight selfie, a patterned wall (wallpaper, brick, shelves, a window) and furniture or floor the same colour as the wall (draw those in IN_FRONT). Without the buyer's own covers the effect is left out.
- **UI World** (READY, `effects/ui-world/`: build.py, effect.md, example, onsets.py, prep.py, slot.json). Needs from the buyer: what the screen shows: the buyer's words for the packaged chat screen, or the buyer's own picture or screen recording. Any names on it are generic placeholders. Still or near-still speaker facing the camera, head and shoulders in frame, one continuous shot. Nothing is tracked: a speaker who moves up and down a lot, walks, or raises hands above the head breaks it. Needs a clean cutout with both shoulders intact. A tight selfie leaves no room.
- **The Stack** (READY, `effects/the-stack/`: build.py, effect.md, measure.py, onsets.py, slot.json). Needs from the buyer: the buyer's own figures: titles, labels, values and units for one to three small cards. One speaker, head and shoulders in frame, one continuous take of 3 to 6 s. A very tight selfie holds about 5 rows in all (build.py stops and says how much to drop). A far-away wide shot is enlarged and goes soft. Hands above the head, a hood or two people give a wrong head box: type HEAD. Without the buyer's own figures the effect is left out.
- **Sticky Text** (READY, `effects/sticky-text/`: build.py, check.py, effect.md, slot.json, track.py). Needs nothing from the buyer. Works on handheld. 'cap' and 'chest' want a medium or close shot, 'head' (beside the head) wants room beside it. Breaks on a hand on or above the head, a hood or long hair hiding the neck, a second person, a head turn past about 40 degrees. When the cap is inside the top 220 px, 'cap' and 'head' are refused: use 'chest'.
- **Spotlight** (READY, `effects/spotlight/`: build.py, check.py, effect.md, onsets.py, prep.py, slot.json). Needs nothing from the buyer. One continuous shot of one person, 3 to 6 s. Best wide or medium with wall above and beside the head; on a close shot the light tightens to a glow. Needs a clean cutout: lost hair or fingers go dark with the room. Breaks on a hand above the head, two people, a hood or long hair over the shoulders, and a head that fills the frame (no room for the words).
- **Freeze and Label** (READY, `effects/freeze-and-label/`: bake_freeze.py, build.py, check.py, effect.md, slot.json). Needs from the buyer: the labels. Best wide or medium with room beside or above the speaker. The hold needs about 1 s per label. A tight selfie fits 1 or 2 short labels (build.py stops and says how many fit). Breaks on a blink or motion blur on the freeze word, a hood or long hair over the neck, a hand on the head, a second person. Hand points are found by skin colour and can miss a hand in front of the chest.
- **Phone Mockup** (READY, `effects/phone-mockup/`: build.py, check.py, effect.md, measure.py, prep.py, slot.json). Needs from the buyer: the buyer's own screen recording or picture for the phone, or the words for the packaged card. Medium or wide is best; close works with 300 px or more of background beside the head, and a close-up that fills the frame stops with 'no room for a phone'. Needs a slot of 2 s or more, the tap word not in the first 0.6 s or last 0.5 s, and no hand parked over the tap point. Not for a speaker walking across the frame.
- **Checklist** (READY, `effects/checklist/`: build.py, check.py, effect.md, example, onsets.py, prep.py, slot.json). Needs from the buyer: 2 to 4 steps, in the speaker's own words. Needs open room above or beside the speaker. A close-up gives a small card. On a moving camera it switches to an opaque card by itself.
- **Pointer Callout** (READY, `effects/pointer-callout/`: build.py, check.py, effect.md, slot.json, track.py). Needs from the buyer: the card texts. Best wide or medium with clear background beside or above the speaker, and a speaker who moves or points. A tight selfie fits 1 or 2 short cards (build.py stops and says how many fit). Breaks on a hood or long hair hiding the neck, a hand on the head, a second person. Hand anchors fail with gloves, bare arms or skin-coloured clothes: tie those cards to head, chest or shoulder.
- **Odometer** (READY, `effects/odometer/`: build.py, check.py, effect.md, example, measure.py, slot.json). Needs from the buyer: the real number, from the buyer. The panel sits behind the speaker, in open background beside or above the head. It stops with a clear message when the speaker fills the frame. Only a number the speaker actually says.
- **Before and After** (READY, `effects/before-and-after/`: build.py, check.py, effect.md, measure.py, prep_after.py, slot.json). Needs from the buyer: nothing needed. Optional: the buyer's own finished version of the same frames. Any shot, any camera. Needs a line that is about a change. Weak when the payoff word comes in the first 0.3 s or less than 1.5 s of slot follows the sweep. On footage that is already dark the default grade may be too quiet: raise AFTER_GRADE. The buyer's own after file must be the same take with no punch-in, reframe or speed change.
- **Chart Grow** (READY, `effects/chart-grow/`: build.py, check.py, effect.md, measure.py, slot.json). Needs from the buyer: nothing needed. Optional: the buyer's own real figures and labels for the chart. Needs open wall beside or above the head, best up and to the right where the line ends. A tight selfie stops with NO OPEN WALL. Breaks on a walking or panning camera, a wall with no texture on a handheld shot, hands flying through the top right during the kick, and a kick word in the first second of the slot.
- **Freeze Sticker** (READY, `effects/freeze-sticker/`: bake.py, build.py, check.py, effect.md, onsets.py, slot.json). Needs from the buyer: the notes. Medium or wide is best (head and chest with air around them); a close-up gives a large sticker with room for one or two short notes. Breaks on a freeze frame with motion blur, closed eyes or a hand across the face, a cutout that lost hair or fingers on that frame, a speaker cut by both sides of the frame, and a head cut by the top of the frame.
- **Comment Bubble** (READY, `effects/comment-bubble/`: build.py, check.py, effect.md, example, measure.py, slot.json). Needs from the buyer: the comment keyword (the cta mark in words.json). The commenter is a generic placeholder, never a real person. The cutout is only used to measure the chin and the avatar crop (fx_new.py --no-cutout and CHIN_Y by hand skips it). Needs the top of the head in frame and about 1.5 s of the same shot after the line.
- **Green Screen** (READY, `effects/green-screen/`: build.py, check.py, effect.md, prep.py, slot.json). Needs from the buyer: the buyer's own video or picture of the thing they are talking about (at least one file in bg/). Medium is best (head, shoulders and chest). Wide works but the speaker is enlarged and turns soft above 1.3x. A close-up with less than about one head height of body under the chin stops with 'too tight'. Needs a clean cutout (the new background shows every matte fault), one speaker, a slot of 36 frames or more. Only a still camera was tested.
- **Knockout Tiles** (READY, `effects/knockout-tiles/`: build.py, check.py, effect.md, prep.py, slot.json). Needs from the buyer: the names the speaker lists; for receipts, the amounts they say. Wide or medium shot with about 400 x 150 px of clear wall beside the head, inside the safe zone. Still camera: the pieces are not tracked to the room. Needs the clean cutout. The running total needs about 150 px of wall above the head. A close-up stops with 'no clear wall'. Only a still wide shot was tested.
- **Timeline Burn** (READY, `effects/timeline-burn/`: build.py, check.py, effect.md, slot.json). Needs nothing from the buyer. Wide or medium shot with the chin above about y 980 (y 1100 without a caption line): the timeline sits under the chin in the lower third. A tight selfie stops with 'No room for the timeline'. Needs 1 s or more of the slot before the burn word and 1 s after it. Reads best on a dark or dimmed picture (DIM). Only a wide shot on a still camera was tested.
- **Blackout** (READY, `effects/blackout/`: build.py, check.py, effect.md, onsets.py, prep.py, slot.json). Needs nothing from the buyer. One person, a line of 1 to 3 s that ends on one punch word, then a cut or the next line. Best wide or medium with room above the head; on a close shot the word sits just above the head. Needs a clean cutout: background the cutout keeps stays lit, lost hair or fingers dim with the room. Breaks on a hand above the head, two people, a head that reaches the top of the safe zone (no room for the word: move it or turn it off) and a room that is already dark.
- **Pull-Back Reveal** (READY, `effects/pull-back-reveal/`: build.py, check.py, effect.md, onsets.py, slot.json). Needs from the buyer: the reel's own edit list (steps really done, each shot's length in frames) and, for the counter, a number the speaker says. Any shot, any camera, no cutout. The checklist covers up to 170 px of the card's left edge: a face in the left quarter of the picture at mid height needs FACE set or shorter steps. The title bar covers the top 68 px of the clip, the timeline strip the bottom 240 px. Needs a slot of about 3.5 s or more. Only a handheld close-up was tested.
<!-- LIST:END -->
