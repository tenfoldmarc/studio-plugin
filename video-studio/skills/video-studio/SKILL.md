---
name: video-studio
description: "Claude Creator Studio. Turns raw 9:16 talking-head clips into a finished Instagram reel in the look the creator saved in the Studio Picker: one of 19 caption styles, or one of 8 overall styles, plus the effects they like. Picks the cleanest take of every line, cuts dead air, transcribes with word timings, places captions from where the speaker actually is in the frame, and checks every result inside the Reels safe zone. Use when the user says 'edit it', 'edit these clips', 'I dropped clips in my downloads', 'cut this into a reel', 'switch my captions', 'change my effects', 'change my style', 'open the picker', 'update the Studio', or runs /video-studio."
---

# Claude Creator Studio (video-studio)

Raw clips in, finished reel out, in the look the buyer picked. They set up once, pick in the Studio Picker, and
from then on drop clips in and say "edit it". They never open an editor: they watch a phone copy and give notes. They can change their editing style at any point if they tell you to.

Read before the first edit: `references/cutting.md` (takes, dead air, fixing the transcript),
`references/captions.md` (the 19 caption styles, how to mark words, where captions go),
`references/checks.md` (footage check, self-check, safe zone). Read `references/styles.md` when the picks hold an
overall style, `effects/INDEX.md` when they hold effects, `references/gotchas.md` when a build or render misbehaves.
Read `references/replicate.md` the moment the buyer shows an example or describes a look of their own.
Read `references/gifs.md` when the buyer asks for GIFs (you can find them yourself and place them on the right lines).

## The buyer's style wins. Read this first.

This is the most important rule in the skill. Everything the skill ships with is a starting point. The buyer's
style beats all of it.

Order of precedence, highest first:
1. What the buyer asks for on this reel.
2. An example they gave or a style they described. You study it and REPLICATE it, and it becomes their own style
   (`ST/my-style.md` + `ST/my-style.json`, see "When the buyer shows an example or describes a style"). Once it
   exists, every "edit it" uses it without asking until told otherwise, and the built-in caption styles and effects are only used
   where the buyer asks for them.
3. Their saved picks: the overall style or the caption style in `ST/studio-picks.json`.
4. An effect's own default look. Always last.

What that means on every edit:
- An effect never brings its own caption look into a reel that already has a caption style.
  - `effects/INDEX.md`, "Restyling an effect's own words", says what to do for each effect: turn its words off, or
    restyle them to the buyer's style before you build.
  - This holds for every effect, also one added after this was written. No effect is exempt.
- **Everything in an effect is open to change.** Colours, fonts, sound level, motion strength, timing. Change them
  to fit the style or the buyer's notes. An effect's defaults are one demo's taste, not a rule.
- **Effects are suggestions.** They are a base for buyers who do not know what they want yet. Use a picked one only where it fits the clip and the line. Drop one rather than force it
  against the style, and say why in one line. Tweak the look of the effects to make sense with the clip you are editing. Meaning the words being spoken, the person saying the words, etc.
- **A note from the buyer is an instruction.** "Make it white", "less zoom", "no sounds": do it on this reel. If
  they say "always", write it into `ST/my-style.md` so every later reel follows it.

Read `ST/my-style.md` at the start of every edit when it exists. Check the finished reel against this rule before
you deliver: one caption look from the first frame to the last, in the buyer's style.

## Step 0: setup check (every run)

`SK` is this skill's folder (the one holding this file): `${CLAUDE_SKILL_DIR}`, or the base directory Claude Code
gave you when it loaded the skill. `SK` is read-only: never write into it.

Run the setup script with whichever Python the machine has. Try in order until one prints STATUS lines:
`python3 "SK/scripts/setup.py"`, then `python "SK/scripts/setup.py"`, then `py -3 "SK/scripts/setup.py"`.
(On Windows `python3` is often a Store stub that prints "Python was not found": try the next one.) It takes a few
seconds, a minute or two the very first time while it builds its own Python environment (say so). None of them
runs: Python is missing. Give the fix and stop (Windows: paste `winget install --id Python.Python.3.12 -e` into
PowerShell, then quit Claude Code completely and reopen it. Mac: download the installer from
https://www.python.org/downloads/ and run it. Linux: `sudo apt install python3 python3-venv`).

Read the STATUS lines:
- `STATUS state <folder>` is `ST`, the buyer's own Studio folder. Everything this skill keeps lives there (its
  Python, `.platform.json`, `config.json`, `studio-picks.json`, sound effects). It is outside the skill on purpose,
  so an update never wipes their picks.
- node / python `MISSING`, or ffmpeg `MISSING` (only when its own copy could not be fetched): the line ends with
  the steps for THIS machine, written for someone who has never used a terminal. Pass them on word for word and
  stop until the script prints `READY`. On Windows they paste the winget line into their own PowerShell window,
  then quit Claude Code completely and reopen it.
- Sound effects `MISSING` (offline) is fine: the reel just has no sound effects until they are there.
- `STATUS update AVAILABLE`: a newer version of the Studio is out. This comes first, before the setup questions,
  the picker or any edit. Ask it on its own: "There's an update for the Studio with fixes. Want me to install it?
  It takes a minute."
  - Yes, or any time they say "update the Studio": run `PY "SK/scripts/update.py"` right away, pass on what it
    prints, tell them to start a new chat, and stop. Nothing else in this chat: the new chat carries on from
    where they were, on the new version.
  - No: carry on, and do not ask again in this chat.
- `clean cutout NOT SET UP` is fine for captions on their own. Almost every effect needs it, and so do the looks that
  go behind the speaker (Bold captions, Chalk Talk, Show and Tell). Get it the first time the picks hold an
  effect or one of those looks: `setup.py --matting`, one time, about 105 MB.
- The other opt-in extra, only when a script asks for it: `setup.py --fx <effect key>` (extra Python packages
  for that effect, into the skill's own Python).

What a new buyer downloads, and when (one time each; how long depends on their connection, so say the size, not
a time):
- at setup: the skill's Python environment, about 0.25 GB.
- at the first edit: the speech model, about 0.5 GB at step 1 and 1.4 GB more at step 4. HyperFrames (the
  renderer), about 0.4 GB, the first time `HF` or `layout.py` runs, then its browser (about 0.2 GB) at the first
  snapshot or render and its quick-cutout model (about 0.2 GB) at step 5.
- with the first effect: the clean cutout, about 105 MB.
Say it once before the first edit: "The first edit downloads about 3 GB of tools, one time. After that it is quick."

Then read `ST/.platform.json` (rewritten on every run). It holds the commands for this computer:
- `PY` = its `python` value. Run EVERY script of this skill with it, never a bare `python3`.
- `HF` = `PY "SK/scripts/hf.py" "<project>"`: the pinned HyperFrames with the right Node on any OS. The project
  folder is its first argument and it runs inside it, so there is no `cd` and `renders/...` means the project's.
- `cutout`: `CoreML` (Apple Silicon, fast) or `CPU` (everything else: slower, run it in the background).

One command style for zsh, bash, Git Bash and PowerShell: full paths in double quotes with forward slashes, one
command per call, no `&&`, no `cd`, no `VAR=1 cmd`, no `~` inside arguments. In PowerShell put `&` in front of a
quoted program: `& "PY" "SK/scripts/ingest.py" "<project>"`. The one short path that is allowed is a render named
after the project folder (`"renders/<slug>-v1.mp4"`): `HF` and both check scripts look it up inside the project.

### First run only

`/video-studio setup` (or "set up the Studio") is how a new buyer starts: run Step 0, do the first-run steps below, then
open the Studio Picker. Do not ask for clips yet. When the picks are saved, say they are ready and that the next step
is to drop clips in and say "edit it". Run again later, it only repeats what is still missing. The person can skip picking options from the studio picker and send you an example or multiple examples of video editing styles. You should study the videos or pictures provided so you can replicate the style.

`STATUS config MISSING`:
1. Say: "Welcome to Claude Creator Studio. Two quick questions, then you pick your look. This only happens once."
2. Ask in one message: where their raw clips usually land (default `~/Downloads`) and where reel projects should
   live (default `~/reel-edits`).
3. Save `ST/config.json`: `{"clipsDir": "~/Downloads", "projectsDir": "~/reel-edits", "setupDate": "YYYY-MM-DD"}`.

`STATUS picks MISSING` (or the buyer asks for the picker): open it, see the next section.

## The Studio Picker

A local page where the buyer picks one overall style, or their own caption style and effects, with a preview clip
on every card. It runs on their computer only.

```
PY "SK/scripts/picker.py" --until-saved                  first run, "open the picker", "change my style"
PY "SK/scripts/picker.py" --tab captions --until-saved   "switch my captions"
PY "SK/scripts/picker.py" --tab effects --until-saved    "change my effects"
```
Run it in the background and tell the buyer: "I opened the Studio Picker in your browser. Pick one overall style,
or pick your own captions and effects, then press Save." Wait for the line `STATUS picks SAVED ...`. Then read
`ST/studio-picks.json` and confirm in ONE plain sentence, for example: "Saved. You are on Keyword captions with
Digital Zoom and Checklist. Drop your clips in and say edit it."

The picks: `{"mode": "preset"|"custom", "style": key|null, "captionStyle": key|"none", "effects": [keys],
"effectSections": null | {"hook": [...], "middle": [...], "end": [...]}}`. `mode: preset` = an overall style, with
its own captions unless `captionStyle` differs from the one that style comes with (the buyer swapped them).
`effectSections` set = each effect may only be used in the parts listed for it.

A one-off ("try Karaoke on this one") does not touch the saved picks: `build_reel.py --caption karaoke` or
`--style fireside`.

## When the buyer shows an example or describes a style

The picker is for buyers who do not know what they want yet. A buyer who hands you a reel they like, a pin, a
screenshot, or says what they want in their own words, has given you the brief. Replicate it. The built-in
caption styles and effects step aside: you do not map their example onto the nearest one, you rebuild the look
itself. `references/replicate.md` has every field and command. The procedure:

1. **Study the whole thing.** `PY "SK/scripts/study.py" "<example file>"` on the file they dropped in. It lays
   EVERY beat out on contact sheets and measures the cuts, the pace, the speech rate and where the sound jumps.
   Look at every sheet, top to bottom, not three stills. A still shows type, colour and layout but not rhythm or
   sound: ask one question, or pick calm defaults and say so.
   A link to a post (a reel, a short, a pin): get the video's direct address with your Apify tool, run
   `PY "SK/scripts/get_example.py" --direct "<address>"`, and study the file it prints. No Apify tool: tell the
   buyer "Links need Apify connected. The walkthrough in your portal shows how. Or drop the video file in here."
2. **Write it down** in `ST/my-style.md`, one plain line per area: type, colour, captions (place, words at once,
   plate, what the spoken word and the key word do), caption motion, pace, framing, graphic elements, sound.
3. **Rebuild it on THEIR clips.** Their words, their takes, their length. Copy the rhythm, not the timing.
   - Rebuild it with a custom caption spec, your own layers and the whole-reel settings
     (`references/replicate.md` has every field).
4. **Check it side by side.** `PY "SK/scripts/side_by_side.py" "<example file>" "<project>" "renders/<slug>-v1.mp4"`
   puts example frames over frames of the final render. Fix what is off, once. Then give the buyer the sheet and
   a plain list: what matches, and what could not be matched.
5. **It becomes theirs.** Save the spec in `ST/my-style.json` (captions, always-on layers, grade, css) and the
   notes in `ST/my-style.md`. `build_reel.py` reads it on every build from then on, above the saved picks.

What is copied and what never is: the LOOK and the STRUCTURE are replicated (type feel, colours, layout, rhythm,
motion). Never the example's footage, music, voice, logo, handle, name or words, and never a claim that the result
is by or with whoever made it. Typeface: the nearest face the skill ships or an openly licensed one it can fetch;
never a paid font file, and you say which face stands in.

Be straight about the limits (`references/replicate.md` lists them): no music is added, the speaker is not moved
into a panel or onto a page outside the overall styles and effects that do that, caption and layer motion is the
set of entrances the engine has. Say what could not be matched. Never fake it.

## Hard rules

1. Reels safe zone (1080x1920): top 220, bottom 450 (nothing below y 1470), sides 35, right 100 from y 1155 down.
   One exception: the Show and Tell speaker card sits flush with the bottom of the video on purpose. Or unless told to disregard safe zones.
2. Captions and effects never cover the face (eyes to chin).
3. Captions say what was actually said. Fix Whisper's mishearings ("Claude" comes out as "cloud"). No em dashes
   in on-screen text.
4. Everything on screen is real or a clearly generic placeholder. Never a real person who is not the buyer, never
   invented numbers, comments or results.
5. Effects only where the footage qualifies (footage check) and only in the parts the buyer allowed. A skipped
   effect is normal: tell the buyer why in one line.
6. Proof comes from frames of the FINAL render, not from snapshots.
7. Never delete or change the buyer's files. Originals are only read.
8. Talk to the buyer in plain words. Never show them file names of this skill, STATUS lines or stack traces.

## Workflow ("edit it")

`<project>` = `<projectsDir>/<short-slug>/`. Clips = the files the buyer names, else the newest videos in `clipsDir`.

```
1. PY "SK/scripts/ingest.py" "<project>" <clips or folder> [--newest 5]
       look at work/sheets.jpg, read transcript.txt
2. write <project>/edl.json                      best take of every line, dead air out (references/cutting.md)
3. PY "SK/scripts/assemble.py" "<project>"       -> assets/aroll.mp4 (clean 30fps) + segments.json
4. PY "SK/scripts/transcribe_cut.py" "<project>" "<names and keywords said in the reel>"
       fix mishearings in words.json by hand, then:
   PY "SK/scripts/marks.py" "<project>"          first guess at the word marks; then apply the marking rule yourself
5. PY "SK/scripts/layout.py" "<project>"         where the speaker is -> layout.json. LOOK at work/layout/check.jpg:
       the green box must run from the top of the head to the chin. A line "CHECK THE HEAD BOX" means it is a guess
       (a picture or poster behind the head can pull it up): fix it before going on (references/captions.md)
6. PY "SK/scripts/init_project.py" "<project>"   fonts, project files, starter plan.json
       write the pinned title (and any on-screen text an overall style needs) into plan.json
7. effects picked?  PY "SK/scripts/footage_check.py" "<project>"   then, for each one that passes AND fits a line:
       it says "ready":   PY "SK/scripts/fx_new.py" <key> --project "<project>" --from <sec> --to <sec>
                          fill the CLIP block in the slot, run the commands it prints, then
                          PY "SK/scripts/fx_add.py" "<project>" "<slot>"      (writes the slot into plan.json)
       step by step: effects/INDEX.md
8. PY "SK/scripts/build_reel.py" "<project>" --safe     reads the saved picks -> index.html, unsafe area in red
   PY "SK/scripts/hf.py" "<project>" lint               0 errors
   PY "SK/scripts/hf.py" "<project>" snapshot --at <5 to 10 moments> --no-end --describe false
                                                        read <project>/snapshots/contact-sheet.jpg, fix
9. PY "SK/scripts/build_reel.py" "<project>"            same build WITHOUT the red guide
   PY "SK/scripts/hf.py" "<project>" render -o renders/<slug>-v1.mp4 --quality high
                                                        about 20 to 45s per 10s of reel on Apple Silicon, up to
                                                        about 80s per 10s when the reel has effect slots
   PY "SK/scripts/frames_check.py" "<project>" "renders/<slug>-v1.mp4"     the self-check: LOOK at the sheet
   PY "SK/scripts/check_cuts.py" "<project>" "renders/<slug>-v1.mp4" --phone   cuts strip + 720p phone copy
                                                        its last line is the audio level (references/cutting.md)
10. deliver the phone copy and the full render. Say what was done and what was skipped, in plain words.
```

`build_reel.py` prints `NOTE` lines when something could not be done
as picked (no room above the head, a look that needs a cutout, a caption swap that cannot ride on a style): pass
each one on to the buyer in plain words, and fix what can be fixed.

A look that goes behind the speaker or lifts them out of the room (Bold captions, Chalk Talk, Show and Tell) needs
a person cutout of the whole reel first. Use the clean one, `rvm_cut.py`, and tell the buyer how long it takes
before you start (`references/checks.md`). Almost every effect needs the clean cutout too (`effects/INDEX.md` says which do not), but only of its own frames:
`fx_new.py` does that (about 1.2 to 1.8 seconds per frame on an Apple Silicon Mac, so about 2 minutes for a 3
second effect). Both need `setup.py --matting` once.

Look at one reel snapshot inside every slot: one caption look, nothing doubled, no spoken word without a
caption unless the effect's own words carry it.

Notes round: change `edl.json` / `words.json` / `plan.json`, rebuild from the step that changed, render `-v2`. Keep
every version in `renders/`.

## What the buyer hears

- Start of an edit: "On it. I'm picking your best takes and cutting the dead air."
- A skipped effect: "I left Clone out of this one: it needs a wide shot with a still camera and this clip is a close-up."
- A fallback: "Your face fills the frame in this clip, so I kept the captions to one line under your chin."
- A slow step: "This look needs a clean cutout of you. That takes about 12 minutes for this reel. I'll keep going
  and tell you when it's done."
- Delivery: "Here's your reel. Captions: Keyword. Effects: Digital Zoom on the hook. Tell me what to change."
- An effect made of words: "I matched the Checklist to your Karaoke captions: same typeface, same caps, same
  yellow."
- An example they showed you, before you start: "On it. I'm studying your example from start to finish, then I'll
  rebuild that look on your clip."
- After replicating it: "Here is what I matched, and what I could not. Every reel uses this style from now on."
- A quiet recording: "Your voice is recorded a little quiet in this clip. Want a louder copy?"

The styles for her (Soft Hours, Glam Cam, Color Block, Camera Shy) work faceless or on camera. Say it that way.
