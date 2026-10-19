# Looks: the 3 base looks and building the buyer's own

A look is a folder. The 3 base looks ship with the skill (`CS/looks/`, read-only). The buyer's own looks live in
`<state>/carousels/looks/<name>/` and are made with `carousel.py look new`:

```
look.json    name, about, the look it builds on ("extends"), fonts, vars (colours, type, spacing), and for choosing
             it: "kind" ("photo" = built around photos, "type" = needs none), "for" (her / him / everyone),
             "niches", "imageStyle" (the kind of picture that suits it, used when generating images)
sample.json  3 slides that show the look at its best (setup preview); {photo1..3}, {face1..3}, {handle} are filled in
look.css     the CSS (on top of the base look's CSS when it extends one)
decor.html   optional: shapes drawn behind every slide (a sun, a frame, a grid, a glow)
look.md      what the look is, in plain lines, and its "Standing notes" (the buyer's "always" rules)
assets/      pictures the look uses (a texture, a logo the buyer owns), referenced in look.css as url(assets/x.png)
```

## Three ways to a look of their own

1. **A base look, tuned.** "Paper but blue", "Horizon with my brand colours": `look new "<name>" --from paper`,
   then only the changes: `"vars": {"--accent": "#2F6BFF"}` in look.json, a few rules in look.css. Fastest.
2. **From carousels they love** (screenshots, files or links). Study them, then build it (below). This is the
   main road and it is replication: the look of THEIR example, not the nearest base look.
3. **From words.** "Black and white, very minimal, big serif, lots of space." Build it, show the 3 sample slides,
   adjust.

Every look gets tried on the same 3 sample slides first (hook, a content slide, the CTA) before it is saved and
used on a real carousel: write a 3-slide carousel.json in a scratch carousel folder and render it.

## Studying an example (screenshots or files)

Links: `PY "SK/scripts/get_example.py" "<link>"` fetches a post (for an Instagram carousel it may only get the
first picture or fail without a login: then ask for screenshots, they are better anyway). Files and screenshots:
look at every one of them. Write down, one line each, before any CSS:

- **Ground:** colour, texture, gradient, pattern, photo. Light or dark.
- **Colour:** the ink, the one or two accent colours and where they appear.
- **Type:** headline face feel (heavy grotesk, condensed, serif, rounded, handwritten), weight, caps or not,
  tight or loose spacing, line height. Body face. Labels (mono? caps? tracked?).
- **Hierarchy:** what is loud, what is quiet, how big the jump is, how lines are mixed (big/small, two colours).
- **Layout:** where the headline sits (top, centre, bottom), alignment, margins, how full the slide is.
- **Recurring parts:** handle, avatar, counter, swipe arrow, progress bar, frame, logo spot, page numbers.
- **Content blocks:** how lists, numbers, quotes, screenshots, prompts and CTAs are drawn.
- **Copy feel:** words per slide, caps, tone, emoji or not. This goes in look.md, it guides the copy too.

Then map it: colours and fonts into `vars`, everything else into look.css on the classes below. Fonts: the
nearest face the skill has (`PY "SK/scripts/get_font.py" --list`) or an open one fetched with
`PY "SK/scripts/get_font.py" "<Family>" --weight 800` (saves `<Family>-<weight>-<normal|italic>.woff2`; put that
file name in look.json `fonts`). Never a paid font file. Say which face stands in for theirs.

What is copied and what never is: the LOOK (type feel, colour, layout, rhythm, how blocks are drawn). Never the
example's words, handle, name, logo, photos or mascot, and never a claim that the result is by or with whoever
made it.

## The slide, as HTML (what look.css styles)

```
.slide.L-<layout>.s<N>[.is-first][.is-last][.has-zt .has-zm .has-zb .has-image .has-items .has-payload ...]
  .decor            (decor.html)           .bleed (a full-slide picture)        .ghost (big faint number)
  .chrome.top       .tag (i dot + text)  .count (b = this slide)  .top-who (avatar + handle, hidden by most looks)
  main.body
    section.zt      .label (i + text)  .kicker  h1.hl > span.ln[.ac|.q]  .rule  p.sub
    section.zm      .big (.num .bs)  blockquote.quote (p, cite)  .media-label  figure.media.<fit> (img, figcaption; fit "frame" is .framed)
                    .items.<style> (li > i.dot | span.n, .tx > b.t + span.d) | .chip | .card | .pair (s.old i.ar .new)
                    | .col (b.t, ul li)
    section.zb      .payload (.pl-label i, .pl-text)  .callout  .cta-word (.cw-pre .kw .cw-post .follow)  .note
  .chrome.bottom    .who (img.av | .av.initial, .hn, .tick)  .foot  .swipe (.st text, .sa arrow svg)
  .progress > i     (width = how far through the carousel)
inline: em.ac  span.q  strong  s  code
```

- Empty parts are not in the page at all, so `.has-zb`, `.has-image` etc. let a look change a slide by what is on it.
- The base CSS (`CS/engine/base.css`) only sets structure. Every colour, face, size and every visible piece of
  chrome is the look's. Hide what the look does not use (`.chrome .tag { display: none }`).
- `.zb` is pushed to the bottom (`--zb-push: 0` keeps it under the middle instead).

## Vars the engine reads (set them in look.json `vars`)

| var | does |
|---|---|
| `--bg`, `--ink`, `--accent`, any of your own | colours (use them in look.css) |
| `--font-head`, `--font-body`, `--font-serif`, `--font-mono` | faces (names from `fonts`) |
| `--pad-x`, `--pad-top`, `--pad-bottom` | the body box between the chrome |
| `--chrome-top`, `--chrome-bottom` | where the top and bottom chrome sit |
| `--gap`, `--zt-gap`, `--zm-gap`, `--zb-gap`, `--items-gap` | spacing |
| `--zm-justify` | the middle: `flex-start`, `center`, `space-between` |
| `--zm-grow` | how much the middle may grow to fill empty room (1 = never, 1.35 = up to 35% bigger) |
| `--min-text` | the smallest reading text the check accepts (default 26px) |
| `--fit: lines` on `.hl` | every loud headline line sized to fill the width (poster hooks), between `--fit-min` and `--fit-max`; with `--fit-wide`/`--fit-narrow` (font-stretch values, variable faces only) short lines go wide and long ones narrow |

Set on every slide by the engine after layout, for decoration that follows the content: `--zb-top` (top of the
bottom zone, or near the bottom when there is none), `--zb-h`, `--zt-bottom`, `--zm-top`, `--zm-bottom`, plus `--i`
(slide number), `--n` (count), `--progress`.

## Saving and using looks

- `carousel.py look default "<name>"`: plain "make a carousel" uses it.
- A note the buyer gives with "always" ("always put my logo top left", "never use caps") goes into the look:
  a setting into look.css / look.json, a copy rule into look.md "Standing notes". Read look.md before every
  carousel in that look.
- "Make a copy of Paper with my colours" = `look new "<name>" --from paper`. "Rename", "get rid of" =
  `look rename` / `look retire` (kept on disk, hidden).
- The base looks are never edited. To change one, make a look of their own from it.
