# The buyer's saved styles

A buyer can keep several editing styles under names they choose ("Cozy Talk", "Hype", "Client: Bella") and say
"edit the clips I dropped in Cozy Talk". One of them is the default: plain "edit it" uses it.

## Where they live

`ST/styles/<slug>/` for each one:
- `style.json`: what the build reads. Every field is optional.
- `style.md`: the same in plain words, where each part came from, the buyer's standing notes. Keep the two in step.

`ST/config.json` "defaultStyle" names the default. A buyer from before named styles had one `ST/my-style.json`: it
becomes the saved style "My style" (the default) the first time any style command runs, and the old file is kept
as `my-style.json.migrated`.

## style.json

```json
{"name": "Cozy Talk", "slug": "cozy-talk", "created": "2026-10-17",
 "caption": { ...custom caption spec, references/replicate.md, with "motion", "word_motion", "mark_motion"... } | "karaoke",
 "layers": [ ...always-on layers only (a border, a corner tag), each may have "motion"... ],
 "grade": "contrast(1.06) saturate(.92)",
 "css": "...",
 "motion": [ ...reel motion patterns with "on" only (references/motion.md)... ],
 "picks": {"mode": "custom", "style": null, "captionStyle": "karaoke", "effects": ["digital-zoom"], "effectSections": null},
 "pace": "cuts every 1.5 to 2 s, pauses cut tight, punch-in on every other cut",
 "sound": "a soft pop on each key word, no music",
 "sources": [{"took": "captions", "link": "https://...", "example": "examples/<name>"},
             {"took": "motion", "link": "https://..."}]}
```

- `picks` makes the Studio's own looks part of the style: a built-in caption style, an overall style, the effects
  and where they may go. A style can be picks only (built from the Picker), a spec only (built from examples), or
  both (their own captions plus some of the Studio's effects). Effects are always restyled to the style.
- `pace` and `sound` are notes for you when you write `edl.json` and the reel's sounds.
- `sources` records what came from which example, for mix and match.

## Commands

```
PY "SK/scripts/my_styles.py" list
PY "SK/scripts/my_styles.py" show "<name>"
PY "SK/scripts/my_styles.py" save "<name>" --from-project "<project>" [--with-picks]
PY "SK/scripts/my_styles.py" save "<name>" --from-picks
PY "SK/scripts/my_styles.py" new "<name>"
PY "SK/scripts/my_styles.py" use "<project>" "<name>" | none
PY "SK/scripts/my_styles.py" default "<name>" | none
PY "SK/scripts/my_styles.py" rename "<name>" "<new name>"
PY "SK/scripts/my_styles.py" duplicate "<name>" "<new name>"
PY "SK/scripts/my_styles.py" retire "<name>"
```
A unique part of a name is enough ("cozy"). Never delete a style: `retire` moves it to `ST/styles/_retired/`.

## Which style a reel uses

1. The one the buyer names for this reel: `init_project.py "<project>" --my-style "<name>"` (or `my_styles.py use`).
   It is written into `plan.json` as "myStyle".
2. Else the default style.
3. Else the Studio Picker picks.

`build_reel.py --my-style "<name>"` is a one-off build in another style; `--no-my-style` builds from the picks.
`build_reel.py` prints a `style` line saying which style it used: check it.

## Building and changing a style

- **New from examples:** `references/replicate.md`. Make it with `new "<name>"` first, so its notes have a home.
- **The first reel in a new style is the dial-in reel.** Tell the buyer it takes longer and there will be a round
  or two of notes. Put their notes into the reel's `plan.json`; when they are happy, `save "<name>" --from-project
  "<project>"` takes the caption spec, always-on layers, grade, css and motion patterns into the style. Timed
  layers and fixed-time motion stay with that reel: describe them in `style.md` ("Graphic elements") so the next
  reel gets its own, written from its own words.
- **A note with "always" or "never"** goes into the style the reel is in (style.json when it is a setting, style.md
  "Standing notes" when it is a rule for you), not into the others.
- **"Make a version with ..."**: `duplicate`, change the copy, so the original stays as it was.
- **From the Picker:** `save "<name>" --from-picks` after the Picker is saved.

## Talking about styles

Use their names, never file names. "Saved as Cozy Talk. It's your default now: drop clips in and say edit it." /
"You have three styles: Cozy Talk (default), Hype and Client Bella. Which one for these clips?" Ask only when the
buyer has several and the clips could suit more than one and they named none; otherwise use the default.
