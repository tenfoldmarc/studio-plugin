# carousel.json: every field

The carousel folder holds `carousel.json`. `carousel.py new` writes the empty shell; you fill `slides` after the
buyer approved the copy. Every field is optional except `slides`. Leave out what a slide does not need: an empty
part takes no room.

```json
{
 "title": "8 design sites",            shown on the preview page
 "look": "Horizon",                    a base look or one of theirs (carousel.py looks)
 "size": "3:4",                        3:4 (1080x1440, the Instagram default), 4:5 (1080x1350) or 1:1
 "tag": "Design cheat codes",          the small tag at the top, on slides without a label of their own
 "footer": "Claude · 16 installs",     a small footer line (looks that show one)
 "caption": "...",                     the post caption, shown under the preview (optional)
 "css": "",                            extra CSS for this carousel only
 "slides": [ { ... }, ... ]
}
```

## A slide

| Field | What it is |
|---|---|
| `layout` | `hook`, `content` (default for the middle), `statement` (one big line, centred), `cta`, `custom`. Left out: the first slide is `hook`, the last `cta`, the rest `content`. |
| `label` | small label: `Tip 01`, `Step 2`, `The math`. Looks show it as a pill, an eyebrow or in the top bar. |
| `kicker` | a big name over the headline (a website, a price): `motionsites.ai`, `$999` |
| `headline` | the loud part. One line per line (`\n`). A line that is all `[[...]]` is an accent line, all `((...))` a quiet line. |
| `sub` | one or two sentences under the headline |
| `items` | a list, see below |
| `big` | `"$10K"` or `{"num": "$10K", "text": "per month"}` |
| `quote` | `"words"` or `{"text": "...", "by": "Name, role"}` (real words, credited) |
| `image` | `"assets/frame-12.30s.jpg"` or `{"src": ..., "fit": "frame", "place": "middle", "label": "...", "caption": "...", "height": 520, "dim": 0.5}` |
| `photos` | several photos as one block (a collage), see "photos" below |
| `stickers` | phone-screen, paper and hand-drawn pieces placed anywhere on the slide: `references/stickers.md` |
| `payload` | the thing to keep: `{"label": "Paste this", "text": "..."}` |
| `callout` | one punchline at the bottom |
| `keyword` | the comment word (CTA). With `keywordPre` (default "Comment the word"), `keywordPost` ("and I'll send you the full guide.") and `follow` (default "Follow @handle for more", `""` for none) |
| `note` | small print at the bottom: "Swipe for 8 copy-paste fixes" |
| `ghost` | a huge faint number behind the slide ("01"), in looks that use one |
| `swipe` | the swipe cue text for this slide (default "Swipe", "End" on the last) |
| `wrap` | `true`: let headline lines wrap instead of one line each |
| `rule` | `false`: no divider under the headline in looks that draw one |
| `html` | raw HTML placed in the middle (anything the fields cannot say: a mock window, a chart) |
| `class`, `css` | extra class names on the slide / extra CSS for this slide only |

## Text markup (headline, sub, items, payload, callout, note)

- `[[words]]` accent
- `((words))` quiet: in a headline a whole `((line))` becomes the small connecting line between loud ones
- `**words**` strong, `~~words~~` struck, `` `words` `` a code chip
- a new line is a line break
Write in normal case. The look decides caps.

## items

```json
"items": ["point one", "point **two**"]                                  bullets (the short form)
"items": {"style": "bullets" | "check" | "rows" | "steps" | "chips" | "grid" | "compare" | "versus",
          "list": [...]}
```

| style | list entries |
|---|---|
| `bullets`, `check` | `"text"` |
| `rows`, `steps` | `{"title": "impeccable", "text": "Design sense on every page."}` (`n` to set the number) |
| `chips` | `"$999"` |
| `grid` | `{"tag": "Best for most", "title": "Plan mode", "text": "...", "hot": true}` (2 columns) |
| `compare` | `{"before": "Dense", "after": "Plain"}` (2 columns; 2 pairs or fewer: one column) |
| `versus` | `"columns": [{"title": "The old way", "list": [...]}, {"title": "The new way", "list": [...]}]` |

## image fits

- `frame` (default): the picture in the middle, rounded, with a soft shadow
- `cover`: fills its box, cropped
- `circle`: round (a face)
- `cutout`: a transparent PNG with no frame (a person cut out with `carousel.py cutout`)
- `bleed`: fills the whole slide behind everything; the look decides how it is dimmed or faded so text reads on it
  (`dim` 0 to 1 overrides: 1 = the photo as it is)
- `half`: the photo takes one part of the slide edge to edge and the text the rest: `"side": "top" | "bottom" |
  "left" | "right"`, `"share": 0.55` (how much of the slide the photo takes)
- `focus`: which part of the photo to keep when it is cropped, like `"50% 25%"` (left, top): move a face into view
- `face`: where the face is in the photo, `"x,y,w,h"` in % of the photo (left, top, width, height), from
  `carousel.py faces` (never guessed by eye). Give it for every photo with text over or next to it: the render moves
  text that lands on it above or below the face, and says TEXT OVER THE FACE when there is no room
- `place`: `top` (above the headline), `middle` (default), `bottom` (in the bottom zone), `stage` (standing on the
  bottom edge of the slide behind the text: a person cut-out for a cover; `height` like `"60%"`, `align`
  left/center/right). The text never covers the face: the render shrinks the picture, or says TEXT OVER THE FACE.

## photos (a collage)

```json
"photos": {"layout": "pair", "frame": "polaroid",
           "list": ["assets/photos/p02.jpg", {"src": "assets/photos/p05.jpg", "caption": "day 1", "rotate": -4, "focus": "50% 30%"}],
           "height": 640, "place": "middle"}
```
- `layout`: `row` (one), `pair` (two side by side), `trio` (one big, two small), `grid` (four), `strip` (three or
  more in a row), `stack` (two or three overlapping, tilted), `scatter` (up to four tossed on the slide)
- `frame`: `plain`, `polaroid` (white border, handwritten caption), `tape` (a strip of tape on top), `card`
  (rounded with a shadow). The look may restyle all of them.
- `place: "bleed"`: the collage fills the whole slide behind the text (a photo dump cover)

Pictures: put them in the carousel's `assets/` folder and refer to them as `assets/name.jpg`. The buyer's photos go
in with `carousel.py photos` (as `assets/photos/pNN.jpg`). Frames from a video
land there by themselves (`carousel.py frames ... --out "<carousel folder>"`).

## The check lines (after every render)

- `OK`: nothing to fix.
- `shrunk to fit (...)`: it fit after making type smaller. Fine above about 85%; below that, cut words.
- `picture made smaller to keep the face clear`: fine; look at it.
- `ROOM TO FILL`: a big empty band in the middle. Usually worth fixing (a list, a picture, a number, or the
  bottom part moved up), unless the buyer's look is deliberately airy.
- `TOO MUCH`, `SMALL TEXT`, `PAST THE MARGIN`, `OFF THE SLIDE`, `RUNS INTO THE CHROME`, `TEXT OVER THE FACE`: fix before showing the
  buyer. Cut words, move a part to its own slide, or shorten the payload. The preview does not open by itself
  while any of these show.
- `FONT MISSING`: a face in the look is not on this computer: `PY "SK/scripts/get_font.py" "<Family>"`.
