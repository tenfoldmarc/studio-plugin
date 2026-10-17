# Replicating an example: study it, rebuild it, make it theirs

When the buyer shows an example (a link to a reel they like, a file, a pin, a screenshot) or describes a look, that
IS the brief. The built-in caption styles and effects step aside. You study the example from top to bottom and
rebuild its look on the buyer's own clips, so it fits THEIR words and footage. Then you save it as one of their named
styles (`references/my-styles.md`), and every later "edit it in <name>" uses it.

You can rebuild almost any talking-head or voice-over edit: type, colour, plates, layout, caption rhythm, every kind
of caption and graphic animation (`references/motion.md`), pace, punch-ins, overlays, the grade, sound cues, and
the Studio's effects where the example has something like them. Work it out like an editor would. Do not settle for
the nearest built-in look.

## What is copied and what never is

Copied: the LOOK and the STRUCTURE. Type feel, case, colours, plates, layout, where things sit, caption rhythm,
motion, pace, the kind of graphic elements, the sound character.

Never copied: the example's footage, music, voice, logo, handle, name or words. Never a claim that the result is
by, with or approved by whoever made the example. On screen there are only the buyer's own words, the buyer's own
footage and material, and generic placeholders.

Typeface: the nearest face the skill ships, or an openly licensed one fetched with `get_font.py`. Never download,
embed or ask for a paid font file. When the example's face is not available, say which face stands in.

The skill's own text never names or imitates a specific creator. A buyer's reference is their business.

## 1. Study it (the whole thing, not three stills)

```
PY "SK/scripts/get_example.py" "<link or file>" ["<another link>" ...]     links to posts, or files they dropped in
PY "SK/scripts/study.py" "<the file it printed>"                            once per example
```
`get_example.py` takes Instagram, TikTok, YouTube, Pinterest, X and most other post links, and files. Each lands in
`ST/examples/downloads/` with a `STATUS example READY <file>` line. The first link installs the downloader into the
Studio's own Python (about 3 MB), once.
- `STATUS example FAILED LOGIN`: the post only shows to a logged-in visitor (Instagram does this sometimes). Ask
  the buyer, in these words or close: "Instagram wants a login for that one. Can I use your browser's login to fetch
  it? Nothing is saved." Only on a yes: run it again with `--browser chrome` (or safari, firefox, edge: the browser
  they are logged in with). On a no: they download the video themselves and drop the file in.
- Any other `FAILED`: ask for another link or the file. With an Apify tool connected you may also get the video's
  direct address with it and run `get_example.py --direct "<address>"` right away (those addresses expire in minutes).

`study.py` writes `ST/examples/<name>/`: every sampled frame on contact sheets (`sheet_01.jpg` ...), `cuts.jpg`
(the frame before and after each cut), `motion_01.jpg ...` (frame-by-frame strips around every moment something
appears or moves: how captions and graphics ANIMATE), full-size frames in `frames/`, and `study.json` (cut times,
shot lengths, loudness over time, where the sound jumps, the words with their times). It prints the measured half:
length, cuts, pace, speech rate, motion moments, sound jumps.

Then LOOK at every sheet, in order, every motion strip, and two or three full-size frames for type and colour.
Captions, graphics and framing change from beat to beat: a look read off three stills is a guess. The sheets show
WHAT is on screen; the motion strips show HOW it moves. You cannot hear the example: the loudness line and the sound
jumps are your ears, so check each jump against the frame at that time (a pop on a word, a whoosh on a cut, music).

## Several examples: mix and match

Buyers often like the captions of one reel, the motion of another and the overlays of a third. Study each one.
Then ask ONE message of questions, only what decides the look:
"I studied all three. Here is what stands out in each: (one line per example). What do you want from each one?
For example: captions from the first, the way things pop in from the second, the grade from the third."
Write the answer into `style.md` "Made from" and `style.json` "sources" (`references/my-styles.md`), then rebuild:
each area from its example. When two areas fight (a busy caption style and busy overlays), say so in one line and
pick the calmer one unless they asked for both.

A still (a pin, a screenshot) shows type, colour, plate, placement and graphics. It cannot show rhythm, animation,
pace or sound: ask the buyer in one question, or choose calm defaults and say so.

A description only ("white bold captions with a yellow highlight, fast cuts, no sounds"): skip the script, write
the same notes from their words, and ask one question about whatever decides the look and is missing.

## 2. Write it down

Make the style first (`PY "SK/scripts/my_styles.py" new "<name>"`: the buyer's name for it, or one you propose,
short and plain, such as "Cozy Talk"), then write these into its `style.md`, in plain words, one short line each.
Leave nothing as "like the example".

| Area | What to note |
|---|---|
| Type | feel (serif, clean sans, condensed, wide capitals, mono, handwriting), weight, case, size against the frame width, tracking, the face you will use and why |
| Colour | text, the accent, plate, outline or shadow, background or page colour, the grade (warm, cool, flat, contrasty, faded) |
| Captions | where they sit (chest, lower third, above the head, top, centre), how many words and lines at once, plate or none, what the word being said does, what a key word does |
| Caption motion | how a line arrives and leaves, what each word does as it is said, what a key word does: read it off the motion strips (from where, how many frames, overshoot or not) |
| Pace | cuts per 10 seconds, typical shot length, punch-ins (how often, how hard), pauses kept or cut |
| Framing | how big the speaker is, where in the frame, anything behind or around them (a page, a border, a card) |
| Graphic elements | titles, bars, borders, lower thirds, stickers, cards, inserts: what, where, when they come and go |
| Sound | cues on cuts or words or none, how loud against the voice, music or none |

## 3. Rebuild it on the buyer's clips

Edit the buyer's clips as always (`references/cutting.md`): their best takes, their words. The example's timing
is not copied. Its RHYTHM is: if it cuts every 2 seconds and marks one word per line, do that on their words.

Build the first reel with everything in its `<project>/plan.json` (start the project with `init_project.py
"<project>" --my-style "<name>"`). When the buyer approves it, `my_styles.py save "<name>" --from-project
"<project>"` moves the parts that belong to every reel into the style (`references/my-styles.md`). `build_reel.py`
reads the style, then the reel's plan.json on top. No built-in caption style or effect is used unless the buyer asks
for one (then it goes in the style's `picks`).

### The custom caption style: `"caption": { ... }`

One spec, rendered by the same engine as the built-in styles: same words, same marks, same safe zone and face
logic, and effect slots (`--caption-y`, hide windows) work with it. Every field is optional.

| Field | Values | Default |
|---|---|---|
| `font` | a family from `assets/fonts/fonts.css` (`PY "SK/scripts/get_font.py" --list`), or one fetched with `get_font.py` | Inter Tight |
| `file` | the fetched font's file name (in `ST/fonts/`), only for a family the skill does not ship | |
| `weight`, `italic`, `stretch` | 100 to 900; true / false; font-stretch in % (125 for the wide Archivo) | 800, false, 100 |
| `case` | `as-typed`, `upper`, `lower`, `title` | as-typed |
| `size`, `tracking`, `line_height` | px on the 1080 wide frame; em; multiple of the size | 64, 0, 1.12 |
| `color`, `accent` | text colour; the colour of marked and lit words | white, #FAE67A |
| `shadow` | a css text-shadow, or false | a soft dark shadow |
| `stroke` | `{"color": "#000", "width": 8}` an outline around the letters | none |
| `plate` | `{"color": "rgba(...)", "radius": 24, "pad": [18, 32], "blur": 0, "per": "line"}`; `"per": "word"` puts one behind each word | none |
| `lit`, `lit_text` | what the word being said does: `none`, `color` (accent while said), `stay` (turns accent and stays), `plate` (an accent plate behind it, text in `lit_text`), `pop` | none |
| `mark`, `mark_scale` | marked words (num, key, emph, cta in `words.json`): `accent` (accent colour), `highlight` (an accent box behind the word, text in `lit_text`) or `none`; a size factor such as 1.25 | accent, 1 |
| `words`, `chars`, `lines` | most words and characters per line; 1 or 2 lines | 3, 18, 1 |
| `position`, `dy` | `chest`, `lower`, `above-head`, `top`, `center`, or a y in px; a nudge in px | chest |
| `align`, `margin` | `center`, `left`, `right`; side margin px | center, 70 |
| `entrance`, `exit` | `none`, `pop`, `fade`, `slide-up`, `type-on`, `word-by-word`; `none` or `fade` (shortcuts: anything else is `motion`) | none |
| `motion`, `word_motion`, `mark_motion` | your own animation for each line, each word as it is said, each marked word: `references/motion.md` | |
| `css` | extra css for this style. Classes: `.cu` the block, `.cu .ln` a line, `.cu .pl` the plate, `.cu .w` a word, `.cu .w.m` a marked word | |

The engine keeps the block inside the safe zone, breaks lines where the width runs out, and moves a block that
would sit on the face (it prints a `NOTE` when it does). `"caption": "karaoke"` (a key instead of a spec) simply
makes a built-in style the buyer's own.

### Your own layers: `"layers": [ ... ]`

For what the example has and no built-in effect covers: a title card, a progress bar, a border, a lower third, a
corner tag, a sticker, a page behind the speaker. Plain html and css that you write, with a time range and an anchor.

```json
{"id": "title", "anchor": "top", "from": 0.0, "to": 2.4, "in": "slide-up", "out": "fade",
 "html": "<div class='tt'>3 things I wish I knew</div>",
 "css": ".tt{display:inline-block;font:800 64px 'Inter Tight';color:#111;background:#fff;padding:14px 30px;border-radius:18px}"}
```
- `anchor`: a band the engine places for this clip, `top` (y 236), `above-head`, `center`, `chest`, `lower-third`
  (a 1080 wide centred box whose top sits on the band; `dx` / `dy` nudge it). Or `full`: the whole frame, your css
  places everything. Or `behind`: the whole frame, BEHIND the speaker, which needs a person cutout (`rvm_cut.py`).
- `from` / `to` in reel seconds. Leave both out for a layer that stays the whole reel. In a saved style only
  those always-on layers are used; timed layers belong in a reel's `plan.json`, written from that reel's words.
- `in` / `out`: `none`, `fade`, `pop`, `slide-up` as shortcuts. Any other movement (a spring, a wiggle, letters
  one by one, a slide from the side, a blur-in, a progress bar filling) is the layer's `"motion"`
  (`references/motion.md`). css `@keyframes` will NOT play in the renderer.
- `from` / `to` work for reel-specific layers in plan.json; a style keeps only always-on layers. For a graphic
  that every reel in the style has at its own moments (a title on the hook, a lower third on the name), write it
  down in `style.md` "Graphic elements" and add it to each reel's plan.json from that reel's words.
- A GIF or a short clip as a layer: `gif_add.py` makes it and writes the layer for you (`references/gifs.md`).
- Text in a layer is the buyer's own words or a generic placeholder. Never a logo, a handle or a claim.
- Layers go through the same checks as everything else: `HF lint`, snapshots with the red safe guide, and
  `frames_check.py` on the final render (its numbers flag anything drawn in the unsafe area or on the face).
  Keep text inside x 35 to 1045 (980 from y 1155 down) and y 220 to 1470. A plain page, band or border may run
  into the unsafe area (the app's buttons sit on top of it); `frames_check.py` then flags every frame it is on:
  look once that nothing to READ is out there, and move on.

### The whole reel

| What | How | Limit |
|---|---|---|
| Colour grade | `"grade": "contrast(1.08) saturate(.9) brightness(.98)"` (a css filter on the footage, the cutout and every effect slot) | css filters only: no LUTs, no film grain, no selective colour |
| Punch-in rhythm | `edl.json`: split a take into segments and alternate `zoom` (1.0, 1.25, 1.0 ...) with `cx` / `cy` on the face, as often as the example punches in | hard cuts between zoom levels; a smooth zoom is the Digital Zoom effect; soft above about 1.4 on a 1080 source |
| Cut pace | `edl.json`: tighter or looser out points, pauses kept or cut, to the example's typical shot length | the buyer's takes decide what can be cut |
| Sound | `"sounds": [{"src": "assets/sfx/pop.mp3", "at": 1.2, "vol": 0.2}]` in `plan.json` (the stock names are in `<project>/assets/sfx`); none for a quiet example. Effects: `SFX=0`, `--no-sfx`, `SFX_GAIN` | the stock cue set only; no music is added |
| Reel motion | `"motion"`: punch-ins on key words, a flash, shake or zoom on every cut, a slow push over the hook (`references/motion.md`, `"on": "marks"` / `"cuts"`) | GSAP tweens only, no random values |
| Anything else | `"css": "..."` plain css appended last, in `plan.json` or the style | it restyles; movement is `motion` |

What cannot be matched today, so say it plainly when the example has it: music (none is added), a layout that
moves the speaker into a panel or onto a page (use the Show and Tell or Chalk Talk overall style when that is the
look, or Green Screen for a background), speed ramps, 3D, and b-roll the buyer did not supply.

## 4. Check it side by side

```
PY "SK/scripts/side_by_side.py" "<example file>" "<project>" "renders/<slug>-v1.mp4" --example-at 1.2,3.0,6.5 --at 0.8,2.4,5.0
```
Example frames on top, the buyer's reel below, in `work/compare/`. Pick pairs that show the same KIND of moment
(a caption line, a marked word, a title, a graphic). Look at it and fix what is off: size against the frame,
colour, position, weight. One polish pass.

Then tell the buyer, in plain words: "I studied your example. Here is what I matched: ... And the two things I
could not: ..." One line each. Send the sheet with the reel.

## 5. It becomes theirs, under a name

- After their notes are in and they are happy: `PY "SK/scripts/my_styles.py" save "<name>" --from-project
  "<project>"` (add `--with-picks` when the style uses the Studio's effects or a built-in caption style).
- `style.md`: the notes from step 2, where each part came from, the face that stands in for theirs, what could
  not be matched, their standing notes ("always", "never").
- Tell them: "Saved as <name>. Next time, drop your clips in and say: edit them in <name>." The first style they
  save becomes the default, so plain "edit it" uses it too. They can make as many styles as they like, change the
  default (`my_styles.py default`), rename, copy or retire them (`references/my-styles.md`).
- An effect added to a reel in their style is restyled to it (`effects/INDEX.md`, "Restyling an effect's own words").
- "Go back to the Picker picks": `build_reel.py --no-my-style` for one reel, or `my_styles.py default none`.
