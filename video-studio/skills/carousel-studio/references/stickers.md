# Stickers: every type

A slide's `"stickers": [ ... ]` puts small pieces anywhere on it: iPhone UI bits, paper and scrapbook bits,
hand-drawn marks. They take no room in the layout and the check does not look at them, so LOOK at the slide:
a sticker must never cover the words or a face by accident.

```json
"stickers": [
  {"type": "bubble", "side": "left", "x": 8, "y": 30, "text": "how do you post every day??"},
  {"type": "circle", "x": 50, "y": 22, "w": 380, "anchor": "center", "color": "red"}
]
```

## Fields every sticker takes

| field | what it does |
|---|---|
| `type` | one of the types below |
| `x`, `y` | where, in % of the slide width / height (`"120px"` works too). The sticker's top-left corner, unless `anchor` |
| `anchor` | `top-left` (default), `center`, `top`, `bottom`, `left`, `right`, `top-right`, `bottom-left`, `bottom-right` |
| `w` | width in px (the slide is 1080 wide). Each type has a good default |
| `size` | base type size in px: scales a text or UI sticker as a whole |
| `rotate`, `scale`, `flip` | degrees (-6 to 6 looks hand-placed), a multiplier, `true` to mirror |
| `color` | the main colour: a name (`yellow pink blue green red orange purple white black cream kraft mint lilac sage gold navy`...) or any CSS colour |
| `z` | `"front"` (default, over the text) or `"back"` (under the text, over the picture) |
| `opacity`, `class`, `style` | extra: 0 to 1, class names, inline CSS |

Slide space: 1080 x 1440. The look's handle/counter sit at the top (y under ~8%) and the swipe cue at the bottom
(y over ~90%). Text stickers read on a phone from about `size` 28 up.

## iPhone UI (real talk, DMs, "what my clients ask me", lifestyle, story-style carousels)

**bubble**: an iMessage bubble. `text`, `side` (`left` = grey, them; `right` = blue, you), `tone: "green"`,
`tail` (default true), `meta` (small line under: "Delivered", "Read 9:41"), `max` (max width, 720).
`variant: "typing"` the three dots. `variant: "reply"` the text field: `text` or `placeholder` ("Type your text here").
```json
{"type": "bubble", "side": "right", "x": 94, "y": 45, "anchor": "top-right", "text": "I batch it on Sundays", "meta": "Delivered"}
```
Stack a conversation top to bottom, left bubbles at x 6-8, right ones anchored `top-right` at x 92-94, ~7% apart.

**notification**: the lock-screen banner. `app`, `title`, `text`, `time` ("now"), `icon` (`message mail bell heart
cash bank camera music calendar star sparkle`, anything else = the app's first letter), `icon_color`, `icon_src`
(their own logo file), `day`/`date` (calendar icon), `dark`. `variant: "message"`: the white "New Message" card with
a blue dot (`app` = the header, `title` = sender). Default width 920.
```json
{"type": "notification", "x": 7, "y": 6, "app": "Messages", "title": "Sarah", "text": "ok wait, how did you get 40 new clients??", "icon": "message"}
```

**notes**: an iPhone Notes card ("< Notes" bar with share and more icons). `title`, `text`, `date`,
`checklist` (`["[x] 10 min walk", "film one reel"]`), `back`, `dark`, `color` (the yellow).
```json
{"type": "notes", "x": 6, "y": 8, "w": 620, "date": "14 May 2026 at 09:37", "title": "Morning routine", "checklist": ["[x] walk", "write 3 hooks"]}
```

**search**: a search bar. `text` (with a blinking-style caret; `cursor: false` to hide) or `placeholder`,
`variant` `ios` (grey field + mic, default) | `google` (white pill, round arrow button) | `glass` (on photos) | `dark`,
`button` (round arrow), `color` (the button). Default width 820.
```json
{"type": "search", "variant": "google", "x": 6, "y": 80, "text": "best pilates studio near me"}
```

**menu**: the long-press menu. `items`: `["Save", "Copy", "Share", "-", "Delete"]` (`-` = group gap; icons and red
come from the word: save, copy, share, more, delete, edit, reply, forward, pin, like, link, report) or
`{"text": "Book now", "icon": "calendar", "red": false}`. `dark`. Default width 540.

**camera**: `variant` `modes` (SLO-MO VIDEO PHOTO PORTRAIT SQUARE, `active` in yellow; `modes` to change),
`focus` (the yellow focus square, `w`, `sun: false` to drop the exposure sun), `zoom` (`levels` [".5","1×","3"],
`active`), `shutter` (the white button, `w`).

**toolbar**: `variant` `reactions` (the tapback pill: heart, thumbs up/down, haha, !!, ?; `active` 1-6 or "heart"),
`buttons` (round white buttons, `icons`: heart comment send bookmark share star...), `nav` (a bottom app bar: home,
search, add, video, profile with their avatar; `active` 1-5, `dark`; x 0, y ~92, w 1080), `actions` (post actions:
heart, comment, send, save; `counts` ["2.4k","118","56"], `liked`, `dark`).

**statusbar**: 9:41, signal, wifi, battery across the top. `time`, `battery` (%), `dark` (black ink for light pictures). x 0, y 0.

**player**: a now-playing card. `src` (cover picture), `title`, `artist`, `progress` (0-1), `time`, `left`, `light`.

**location**: a pin + place pill. `text`, `variant` `glass` (default, on photos) | `white` (accent gradient text) |
`dark` | `accent` | `plain` (no pill). Caps by itself.
```json
{"type": "location", "x": 6, "y": 6, "text": "Paris"}
```

**stamp**: a date/time line. `variant` `ui` (small iPhone-style text, white unless `color`; `bold`: "Today", `text`: "9:41 AM"),
`film` (orange LCD date of a film camera, digits: `"'26 05 14"`), `rubber` (inked rubber stamp: "Approved", "Sold out").

## Paper and scrapbook (journal, lifestyle, wellness, "my week", behind the scenes; best on Paper)

**polaroid**: a photo in a white instant-film frame. `src`, `caption` (hand font), `font`, `focus`, `ratio`
(`square` | `portrait` | `wide`), `tape: true` (+ `tape_color`, `tape_pattern`). Default width 440; rotate it 3-6°.
```json
{"type": "polaroid", "src": "assets/me.jpg", "x": 6, "y": 6, "w": 420, "rotate": -5, "caption": "day one", "tape": true}
```

**tape**: a strip of washi/masking tape with torn ends. `color` (`beige kraft pink mint blue yellow lilac white clear
black red sage` or any), `pattern` (`stripes dots grid check hearts`), `w` (length, 240), `h` (64). Put two across
the corners of a photo at ±35-45°.

**sticky**: a sticky note. `text` (hand font), `color` (`yellow pink blue green orange lilac mint white`), `font`,
`ink`, `align: "left"`, `tape`. Default 400 square; text size follows `w`.

**receipt**: a diner guest check. `title` ("Guest Check"), `number`, `date`, `table`, `guests`, `server`,
`lines` (`"text"` or `{"qty": "1", "text": "consistency", "price": "$0"}`), `rows` (blank rows to show), `total`,
`footer`, `paper`, `ink`. A playful "the bill for success" list.
```json
{"type": "receipt", "x": 56, "y": 5, "w": 420, "rotate": 3, "lines": [{"qty": "1", "text": "patience", "price": "∞"}], "total": "100%"}
```

**card**: a paper card with a title and words, for the "old money" feel. `variant` `simple` | `lace` (scalloped edge
with eyelets) | `invite` (double rule frame with corner scrolls, centred, caps title) | `torn` (torn top and bottom).
`title`, `text`, `sign` (a script signature), `paper`, `ink`. Default width 620.
```json
{"type": "card", "variant": "invite", "x": 52, "y": 12, "w": 460, "title": "You're invited", "text": "to stop playing small", "sign": "Marc"}
```

**clip**: a paperclip (`color` silver | gold | rosegold | pink | black), clipped on a photo or note edge.

**folder**: a desktop folder icon with its name under it. `color` (pink default, blue yellow green purple grey black
orange red beige), `label`, `selected` (blue name highlight), `cursor: true` (the arrow pointer). Default width 240.
Good for "my folders": `2026 goals`, `Clients`, `Content ideas`.

## Hand-drawn marks (point at things; work on every look)

**hand**: handwritten words. `text`, `font` (`hand` default, `pen` loose pen, `marker` bold marker, `script`
elegant signature, `serif`, `type` typewriter), `color` (the slide's ink if left out), `size` (64), `align`.
```json
{"type": "hand", "x": 8, "y": 88, "text": "my advice inside...", "color": "white", "size": 76}
```

**circle**: a scribbled loop around a word. `w`, `h` (0.42 × w), `stroke` (7), `brush` (`pen` tapered | `marker`),
`color` (the look's accent). Use `anchor: "center"` on the word's centre and make it ~1.3× the word's width.

**arrow**: a hand-drawn arrow. `w` (length, 260), `direction` (`right down-right down down-left left up-left up
up-right` or degrees), `curve` (-1 to 1, 0.45), `variant` `curve` | `loop` | `zigzag`, `head` (size, 1), `stroke`, `color`.

**underline**: `variant` `swoosh` (default) | `wave` | `double` | `scribble`, `w`, `stroke`, `color`.

**sparkle**, **star**, **heart**: small icons. `w` (84), `color`, `variant` `flat` (default) | `gloss` (shiny 3D) |
`outline` (drawn by hand). `count: 3` makes a little cluster (flat, gloss).

**highlight**: words on a highlighter swipe. `text`, `color` (yellow), `ink`, `font` (`ui` default, `serif`, `hand`...),
`size` (44), `w` (where it wraps). `variant: "strip"`: typed words on white paper strips, one per line
(`color` = the strip).
```json
{"type": "highlight", "x": 6, "y": 6, "w": 760, "text": "the one habit that changed my business", "size": 54}
```

**label**: a rounded chip: "SWIPE", "TIP OF THE DAY", "25% OFF BOOKINGS THIS WEEK". `text`, `variant` `solid`
(accent) | `white` | `dark` | `outline` | `glass` | `soft`, `icon` (`arrow sparkle heart star pin check link lock
bell music calendar flag dot`), `icon_side: "left"`, `shape: "square"`, `color`.

## Fit them to the look and the mood

- Paper, beige, serif, "old money": card (invite, lace), polaroid, tape in beige/kraft, receipt, hand in `script`, stamp rubber.
- Pastel, lifestyle, pilates, wellness: sticky (pink, blue, mint), tape with patterns, hearts and sparkles gloss, label soft, folder pink.
- Bold, Poster, hot takes: circle, arrow, underline in the accent, highlight, label solid, notification ("this DM made me...").
- Dark looks (Horizon) and photos: glass location / label / search, white hand text, white or yellow marks.
- Two to six stickers a slide. One hero piece (a bubble thread, a polaroid, a notes card) plus small marks. Tilt
  paper bits 2-6°, never UI pieces.
- Never a real brand's logo or a real person's message: everything in a bubble or notification is the buyer's own
  words or a clearly made-up example they approved.

## For looks

A look restyles every sticker in its look.css through these (all have defaults): `--st-ui-font`, `--st-hand-font`,
`--st-pen-font`, `--st-marker-font`, `--st-script-font`, `--st-type-font`, `--st-serif-font`, `--st-paper`,
`--st-ink`, `--st-accent` (defaults to the look's `--accent`), `--st-mark` (circles, arrows, underlines),
`--st-blue` (iMessage, links), `--st-radius` (1 = iOS rounding, 0.5 = sharper), `--st-glass`, `--st-glass-dark`,
`--st-shadow`. A rule on `.st-<type>` changes one type (`.st-sticky .s-pg { ... }`).
