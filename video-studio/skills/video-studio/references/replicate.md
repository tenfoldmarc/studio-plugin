# Replicating an example: study it, rebuild it, make it theirs

When the buyer shows an example (a reel they like, a pin, a screenshot) or describes a look, that IS the brief.
The built-in caption styles and effects step aside. You study the example from top to bottom and rebuild its look
on the buyer's own clips, so it fits THEIR words and footage. Then you save it, and every later "edit it" uses it.

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
PY "SK/scripts/study.py" "<example file>"            a video or a picture the buyer dropped in
```
A link to a post (a reel, a short, a pin) goes through Apify: use your Apify tool to get the direct address of
the video for that link, then `PY "SK/scripts/get_example.py" --direct "<address>"` right away (such addresses
expire within minutes) and run `study.py` on the file it prints. It lands in `ST/examples/downloads/`. If you
have no Apify tool, tell the buyer in one sentence that links need Apify connected (the walkthrough in their
portal shows how), or they can drop the video file in instead.

It writes `ST/examples/<name>/`: every sampled frame on contact sheets (`sheet_01.jpg` ...), `cuts.jpg` (the frame
before and after each cut), full-size frames in `frames/`, and `study.json` (cut times, shot lengths, loudness over
time, where the sound jumps, the words with their times). It prints the measured half: length, cuts, pace, speech
rate, sound jumps.

Then LOOK at every sheet, in order, and at two or three full-size frames for type and colour. Captions, graphics
and framing change from beat to beat: a look read off three stills is a guess.

A still (a pin, a screenshot) shows type, colour, plate, placement and graphics. It cannot show rhythm, animation,
pace or sound: ask the buyer in one question, or choose calm defaults and say so.

A description only ("white bold captions with a yellow highlight, fast cuts, no sounds"): skip the script, write
the same notes from their words, and ask one question about whatever decides the look and is missing.

## 2. Write it down

Write these into `ST/my-style.md`, in plain words, one short line each. Leave nothing as "like the example".

| Area | What to note |
|---|---|
| Type | feel (serif, clean sans, condensed, wide capitals, mono, handwriting), weight, case, size against the frame width, tracking, the face you will use and why |
| Colour | text, the accent, plate, outline or shadow, background or page colour, the grade (warm, cool, flat, contrasty, faded) |
| Captions | where they sit (chest, lower third, above the head, top, centre), how many words and lines at once, plate or none, what the word being said does, what a key word does |
| Caption motion | how a line arrives (cut, pop, fade, slide up, typed, word by word) and leaves |
| Pace | cuts per 10 seconds, typical shot length, punch-ins (how often, how hard), pauses kept or cut |
| Framing | how big the speaker is, where in the frame, anything behind or around them (a page, a border, a card) |
| Graphic elements | titles, bars, borders, lower thirds, stickers, cards, inserts: what, where, when they come and go |
| Sound | cues on cuts or words or none, how loud against the voice, music or none |

## 3. Rebuild it on the buyer's clips

Edit the buyer's clips as always (`references/cutting.md`): their best takes, their words. The example's timing
is not copied. Its RHYTHM is: if it cuts every 2 seconds and marks one word per line, do that on their words.

Everything below goes into `ST/my-style.json` (the style, used by every reel) or `<project>/plan.json` (this reel
only, wins over my-style). `build_reel.py` reads both. No built-in caption style or effect is used unless the
buyer asks for one.

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
| `entrance`, `exit` | `none`, `pop`, `fade`, `slide-up`, `type-on`, `word-by-word`; `none` or `fade` | none |
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
- `from` / `to` in reel seconds. Leave both out for a layer that stays the whole reel. In `my-style.json` only
  those always-on layers are used; timed layers belong in a reel's `plan.json`, written from that reel's words.
- `in` / `out`: `none`, `fade`, `pop`, `slide-up`. That is all the motion a layer has: css `@keyframes` in a
  layer's css will NOT play in the renderer. When the example moves a graphic in another way, use the nearest of
  these four and say so.
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
| Anything else | `"css": "..."` plain css appended last, in `plan.json` or `my-style.json` | it can restyle what is on the page; it cannot add motion |

What cannot be matched today, so say it plainly when the example has it: music, a layout that moves the speaker
into a panel or onto a page (use the Show and Tell or Chalk Talk overall style when that is the look, or Green
Screen for a background), speed ramps, transitions between shots other than a cut or the Zoom-Through Cut effect,
animated graphics beyond the four entrances, caption motion beyond the six entrances, 3D, and b-roll the buyer
did not supply.

## 4. Check it side by side

```
PY "SK/scripts/side_by_side.py" "<example file>" "<project>" "renders/<slug>-v1.mp4" --example-at 1.2,3.0,6.5 --at 0.8,2.4,5.0
```
Example frames on top, the buyer's reel below, in `work/compare/`. Pick pairs that show the same KIND of moment
(a caption line, a marked word, a title, a graphic). Look at it and fix what is off: size against the frame,
colour, position, weight. One polish pass.

Then tell the buyer, in plain words: "I studied your example. Here is what I matched: ... And the two things I
could not: ..." One line each. Send the sheet with the reel.

## 5. It becomes theirs

- `ST/my-style.md`: the notes from step 2, the face that stands in for theirs, what could not be matched, their
  standing notes ("always", "never"), and where the example's study is.
- `ST/my-style.json`: `{"name": "...", "caption": {...}, "layers": [always-on ones], "grade": "...", "css": "...",
  "pace": "...", "sound": "..."}`. `build_reel.py` reads `caption`, always-on `layers`, `grade` and `css` on every
  build; `pace` and `sound` are notes for you when you write `edl.json` and `plan.json`.
- From then on "edit it" uses their style without asking. It sits above the saved picks. A built-in caption style
  or an effect is only used when the buyer asks for it, and an effect is then restyled to their style
  (`effects/INDEX.md`, "Restyling an effect's own words").
- "Go back to my picks": `build_reel.py --no-my-style` for one reel, or put `my-style.json` aside (rename it,
  never delete it) for good.
