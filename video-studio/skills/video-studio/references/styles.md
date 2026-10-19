# The 9 overall styles and the per-reel plan

An overall style = what happens to the footage (grade, layout, cuts, push-ins) + the captions it comes with.
`build_reel.py` builds it when the picks say `"mode": "preset"`. Engine: `SK/engine/styles.py`. You never edit the
engine for a reel. Anything a style writes on screen comes from `<project>/plan.json`, which YOU write from the
reel's own words.

The four for her work faceless or on camera. Never call them faceless-only.

| Key | Name | What it does to the footage | Its own captions | Needs |
|---|---|---|---|---|
| `soft-hours` | Soft Hours | Warm dim grade, a slow push-in on every shot, soft vignette | Moodboard (upper third when nobody is on camera, else under the chin) | |
| `glam-cam` | Glam Cam | Clean bright grade, a jump zoom on every new thought, pivoting on the chin | Vanity | works best on a medium or close shot |
| `color-block` | Color Block | The shots are broken up by flat colour cards on the first beat of each new sentence | Loud Lowercase | more than one sentence |
| `camera-shy` | Camera Shy | Quick cuts (a punch-in every phrase or so), warm dim grade | A typed list from the plan; without one, Moodboard | a list in the plan |
| `chalk-talk` | Chalk Talk | The speaker cut out onto a dark teal studio backdrop, hand-drawn marker titles, an optional rounded b-roll card | None: the marker titles carry the words | a clean cutout made with `rvm_cut.py --hard` |
| `fireside` | Fireside | One shot, warm lamp-light grade, vignette, one slow push-in on the face | Small gold serif, two words at a time | |
| `raw-tape` | Raw Tape | A 4:3 picture inside the reel on black, faded green film grade, slow push-in | Small plain yellow subtitles inside the picture | |
| `viral-guy` | Viral Guy | Slate-teal room grade, warm skin, a punch-in on every other shot (and one in the middle of any shot over 4.5 s), flat ink and paper word cards on the beats, a small step label over the words | Viral Guy (one quiet cream word at a time) | |
| `show-and-tell` | Show and Tell | The speaker in a rounded card flush with the BOTTOM of the video, head popping out above it, a light canvas above | None: the canvas carries the words | a clean cutout (`rvm_cut.py`) |

Caption swaps: when the picks' `captionStyle` is not the one the style comes with, the footage treatment stays and
that caption style goes on top. Two limits, both reported as a `NOTE` to pass on: Show and Tell takes no swap (white
captions do not read on its light canvas), and Bold cannot ride on any overall style (its words go behind the head
of untouched footage).

Every style builds with an EMPTY plan. It then falls back to the pinned title, the first `num` word with what it
counts, and the `cta` word. Write the plan when the fallback is not good enough, which for Chalk Talk, Show and
Tell and Camera Shy is most reels.

## plan.json

```json
{
  "title": ["7 video effects", "Claude made for me"],
  "swash": ["7 Video", "Effects"],
  "parts": {"hook": [0, 2.9], "end": [21.4, 25.0]},
  "style": { "<style key>": { ... } },
  "slots": [{"src": "fx/checklist/renders/slot.mp4", "from": 6.2, "to": 9.8}]
}
```
All times are seconds in the finished cut (read them from `words.json`). Text is what the speaker said, shortened.
Never add a claim, a number or a name they did not say.

### Extra footage, any of the four for her
```json
"soft-hours": {"broll": [{"src": "assets/broll/kitchen.mp4", "from": 0, "to": 3.4, "media": 0, "zoom": 1}]}
```
With `broll` the listed clips are the pictures and the reel's own cut is only heard (that is the faceless version).
Without it the reel's own shots are used. Put the files under `<project>/assets/broll/` (1080x1920).

### Camera Shy: the typed list
```json
"camera-shy": {"list": {"title": "3 things i wish i knew", "at": 0.4,
                        "sub": "before i started posting", "subAt": 1.3,
                        "rows": [{"text": "1. batch your hooks", "at": 3.1}, {"text": "2. film in one take", "at": 5.6}]}}
```
`title` shows at `at`, `sub` types itself from `subAt`, each row types itself when its point is said. With the
speaker on camera the list sits under the chin and holds 3 rows at most.

### Color Block
```json
"color-block": {"color": "#B5C77A", "cards": [[3.3, 4.45], [7.0, 8.35]]}
```
Both optional. `cards` = when the flat colour card replaces the picture (the words keep going on top).

### Glam Cam
```json
"glam-cam": {"zooms": [[1.2, 1.16], [2.4, 1.0], [3.1, 1.22]]}
```
Optional: time and zoom level of each jump. Default: a jump on every new phrase.

### Chalk Talk: the marker titles
```json
"chalk-talk": {
  "beats": [{"from": 0.0, "to": 2.1, "title": "WANT THE LINK?"},
            {"from": 2.1, "to": 4.6, "big": "21", "lines": ["VIDEO", "EFFECTS"], "lineAt": [2.4, 2.8]}],
  "broll": {"src": "assets/broll/demo.mp4", "from": 4.6, "to": 6.9, "media": 0.2, "label": "CLAUDE MAKES THEM"}
}
```
A beat is either one marker line (`title`, up to about 22 characters, longer ones break in two) or a big number
with the one or two words it counts, each appearing when it is said. `broll` cuts away to a rounded card with a
marker label. The call to action ("COMMENT" + the keyword, underlined) is added by itself from the `cta` mark.

### Show and Tell: the canvas
```json
"show-and-tell": {
  "beats": [{"from": 0.0, "to": 2.1, "label": "You will need", "card": "the link", "icon": "link"},
            {"from": 2.1, "to": 5.6, "label": "21 video effects",
             "thumbs": ["assets/thumbs/a.jpg", "assets/thumbs/b.jpg", "assets/thumbs/c.jpg", "assets/thumbs/d.jpg"],
             "note": "Claude builds them for you", "noteAt": 4.0}]
}
```
A beat is a label with one white card under it, or a label with up to four thumbnails (the buyer's own images,
226x402) and an optional highlighted note. The big "Comment" + keyword is added by itself from the `cta` mark.
The speaker card ignores the bottom safe zone on purpose. Everything else on the canvas stays inside it.

### Viral Guy: word cards and step labels
```json
"viral-guy": {"cards": [{"from": 5.5, "to": 6.7, "kind": "ink"}, {"from": 13.8, "to": 14.3, "kind": "paper"}],
              "steps": [{"from": 16.8, "to": 23.2, "label": "step one"}, {"from": 23.2, "to": 26.7, "label": "step two"}],
              "zooms": [1.0, 1.12]}
```
All optional. A card replaces the picture with a flat ink (`#101B1B`) or paper (`#F4F6FA`) colour while the words keep
running, centred on it: put cards on a punchline or a contrast ("campaigns" ink / "launches" paper), about 1 second,
starting and ending on a word. Paper flips the Viral Guy captions to deep green; with a swapped caption style paper
cards turn ink (a `NOTE` says so). Default with no `cards`: an ink or paper card on every other new sentence, at least 4 s
apart. A step is the small label ("step one") over the captions for a whole section; a chapter card is a card plus a
step that starts with it. Write the labels from the speaker's own structure ("step one", "number two"), never invented.
`zooms` = the framings the shots take in turn. The effects that come from this look (Stat Stack, Dot Counter,
Serif Flow, Chip Row, Prompt Box, Depth Scatter) are overlay effects: they lay over this style's own footage, so its
grade and punch-ins stay under them.

## Push-ins and punch-ins already in the cut
Styles add their own slow push-in on top of whatever `edl.json` did. Fireside and Raw Tape are meant for one
continuous take: on a reel with many cuts they still work, the push simply runs across the cuts.
