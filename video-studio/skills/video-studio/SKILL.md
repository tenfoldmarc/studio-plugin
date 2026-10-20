---
name: video-studio
description: "Creator Studio. Setup runs once, at the first use or when the buyer asks for it ('set up the Studio', /video-studio setup). Turns raw 9:16 talking-head or voice-over clips into a finished Instagram reel in the creator's own named editing style: rebuilt from links or files of reels they love (captions, animation, overlays, pace, mixed from several examples), or one of 20 caption styles or 9 overall styles from the Studio Picker, plus the effects they like. Picks the cleanest take of every line, cuts dead air, transcribes with word timings, places captions from where the speaker actually is in the frame, and checks every result inside the Reels safe zone. Use when the user says 'edit it', 'edit these clips', 'I dropped clips in my downloads', 'cut this into a reel', 'switch my captions', 'change my effects', 'change my style', 'edit these in <style name>', 'replicate the editing style of this reel', 'copy this editing style', 'save this style', 'what styles do I have', 'make 8 variations for my trial reels', 'make N variations', 'trial reel versions', 'post it', 'post this to Instagram / TikTok / YouTube', 'post these as trial reels', 'schedule this for tomorrow', 'set up posting', 'connect my Instagram', 'open the picker', 'update the Studio', or runs /video-studio."
---

# Creator Studio (video-studio)

Raw clips in, finished reel out, in the buyer's own editing style. They show you reels whose editing they love (links
or files, mixing captions from one and motion from another), or describe it, or pick from the Studio's built-in
looks. You rebuild that look on their clips and save it under a name they choose. They can keep several styles
("Cozy Talk", "Hype") and from then on drop clips in and say "edit these in Cozy Talk", or just "edit it" for their
default. They never open an editor: they watch a phone copy and give notes.

Read before the first edit: `references/cutting.md` (takes, dead air, fixing the transcript),
`references/captions.md` (the 20 caption styles, how to mark words, where captions go),
`references/checks.md` (footage check, self-check, safe zone), `references/my-styles.md` (the saved styles).
Read `references/replicate.md` and `references/motion.md` the moment the buyer shows an example or describes a look
of their own: you can rebuild nearly any talking-head or voice-over edit, animation included. Read
`references/styles.md` when the picks hold an overall style, `effects/INDEX.md` when they hold effects,
`references/gotchas.md` when a build or render misbehaves, `references/gifs.md` when the buyer asks for GIFs (you
can find them yourself and place them on the right lines), `references/variations.md` when they ask for variations
or trial reel versions of a reel, `references/posting.md` when they ask you to post, schedule or connect an account.

## The buyer's style wins. Read this first.

This is the most important rule in the skill. Everything the skill ships with is a starting point. The buyer's
style beats all of it.

Order of precedence, highest first:
1. What the buyer asks for on this reel.
2. The saved style this reel is in: the one they named ("edit it in Cozy Talk"), else their default style
   (`references/my-styles.md`). A style built from their examples or words is REPLICATED, not mapped onto the
   nearest built-in look (see "Building a style"). The built-in caption styles and effects are only used where the
   style or the buyer asks for them.
3. The Studio Picker picks in `ST/studio-picks.json`, when they have no saved style.
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
  they say "always", write it into the style the reel is in (style.json when it is a setting, its style.md
  "Standing notes" when it is a rule for you) so every later reel in that style follows it.

Read the style's `style.md` at the start of every edit (`my_styles.py show` prints where it is). Check the finished
reel against this rule before you deliver: one caption look from the first frame to the last, in the buyer's style.

## Step 0: the quiet check (every run) and the setup (first run only)

Two different things, never mixed up:
- **The setup** (the welcome, the two folder questions, building their first style) happens ONCE, the first time,
  when `STATUS config MISSING` shows. After that it never comes back by itself. It runs again only when the buyer
  asks: "set up the Studio again", "redo the setup", `/video-studio setup` ("First run only" below says how).
- **The quiet check** below runs at the start of every chat that uses the Studio. It takes a few seconds and the
  buyer does not see it: do not announce it, do not repeat setup questions, do not list what it found. Speak only
  when it needs them (an update to offer, something missing to fix).

`SK` is this skill's folder (the one holding this file): `${CLAUDE_SKILL_DIR}`, or the base directory Claude Code
gave you when it loaded the skill. `SK` is read-only: never write into it.

Run the setup check. The buyer does not need Python, Node or ffmpeg on the computer: the Studio gets its own copy
of whatever is missing, into `ST`, with no password and nothing installed system-wide.
- Mac and Linux: `sh "SK/scripts/start.sh"`. Always this one. Never run a bare `python3` on a Mac: without Apple's
  developer tools it opens an "install developer tools" window.
- Windows: try in order until one prints STATUS lines: `python3 "SK/scripts/setup.py"`, then
  `python "SK/scripts/setup.py"`, then `py -3 "SK/scripts/setup.py"`. (`python3` is often a Store stub that prints
  "Python was not found": try the next one.) None of them runs: there is no Python, so run
  `powershell -NoProfile -ExecutionPolicy Bypass -File "SK/scripts/start.ps1"`. It gets the Studio its own Python
  and then runs the setup.

It takes a few seconds, a few minutes the very first time while it downloads what is missing and builds its own
Python environment (say so that first time only). Only when it prints `STATUS python MISSING`, or `start.ps1` fails in any other way:
give the fix and stop (Windows: paste `winget install --id Python.Python.3.12 -e` into PowerShell, then quit
Claude Code completely and reopen it. Mac: download Python 3.12 from
https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg and open it. Linux:
`sudo apt install python3 python3-venv`).

Never install a Python yourself to get past setup, and never the newest one: the transcription engine only
installs on Python 3.9 to 3.13. A newer Python on the computer is fine to leave there, the Studio skips it.

Read the STATUS lines:
- `STATUS state <folder>` is `ST`, the buyer's own Studio folder. Everything this skill keeps lives there (its
  Python, `.platform.json`, `config.json`, `studio-picks.json`, sound effects). It is outside the skill on purpose,
  so an update never wipes their picks.
- node, python or ffmpeg `MISSING` (only when the Studio could not fetch its own copy: no internet, or a system
  there is no build for): the line ends with the steps for THIS machine, written for someone who has never used a
  terminal. Pass them on word for word and stop until the script prints `READY`. On Windows they paste the winget
  line into their own PowerShell window, then quit Claude Code completely and reopen it.
- `STATUS python TOO NEW`: the Python that ran the setup is newer than the transcription engine supports. Run the
  command at the end of the line (the starter script). It gets the Studio its own Python 3.12. Nothing to install.
- `the download did not finish, trying again (attempt 2 of 3)`: a download got stuck and the Studio started it
  again by itself. Nothing to do. Only the `OK` or `MISSING` line that follows counts.
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

What a new buyer downloads, all of it at setup, one time (how long depends on their connection, so say the size,
not a time):
- the setup check: the skill's Python environment, about 0.25 GB. On a computer that has none of its own, also
  Python (about 25 MB on a Mac, 46 MB on Windows), Node (about 50 MB) and ffmpeg (about 45 to 75 MB).
- then `PY "SK/scripts/prefetch.py"`, started IN THE BACKGROUND right after the first setup check, so it downloads
  while they answer the questions and build their style: the two speech models (about 0.5 and 1.4 GB), HyperFrames
  (the renderer, about 0.4 GB) and its browser, the quick cutout model (about 170 MB) and the clean cutout (about
  105 MB). Say it once: "I'm downloading the editing tools in the background now (about 3 GB, one time), so your
  first edit is quick. We can keep going while it runs."
- Before step 1 of an edit, while `prefetch.py` has not reported `STATUS prefetch DONE`: `PY "SK/scripts/prefetch.py"
  --status`. RUNNING: tell them it is still finishing the download and wait for it. INCOMPLETE or STOPPED: carry on,
  the edit downloads what is missing by itself (and `prefetch.py` can be run again).

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

`/video-studio setup` (or "set up the Studio") is how a new buyer starts. Run Step 0, then the three steps below.
Do not ask for clips until they have a style.

When a buyer who is already set up asks for the setup again ("set up the video studio", "redo my setup",
`/video-studio setup`): run Step 0, then show what they have in two plain lines (the clips folder and the projects
folder, their saved styles and which is the default) and ask what they want to change: the folders, a new style,
or their default. Change only that. Never wipe their styles, picks or folders.

`STATUS config MISSING`:
0. Start `PY "SK/scripts/prefetch.py"` in the background now (see Step 0: the downloads), then go on.
1. Say: "Welcome to Creator Studio. Two quick questions, then we build your editing style. This only
   happens once."
2. Ask in one message: where their raw clips usually land (default `~/Downloads`; you check there for new clips
   every time they say "edit it") and where finished reel projects should live (default `~/reel-edits`).
3. Save `ST/config.json`: `{"clipsDir": "~/Downloads", "projectsDir": "~/reel-edits", "setupDate": "YYYY-MM-DD"}`
   (keep any other keys already in it).

No saved style yet (`my_styles.py list` says so) and no picks: build their first style. Ask in ONE message:

> "Now your editing style. The best way: send me links to 1 to 3 reels whose editing you love (Instagram, TikTok,
> YouTube Shorts all work), or drop the video files in. You can mix: captions from one, the animations from another,
> overlays from a third, just tell me what you like in each. No examples handy? Describe the look in your own words,
> or I can open the Studio's built-in looks and you pick one."

- Links, files or a description: "Building a style" below.
- Built-in looks: the Studio Picker below; when they save, `my_styles.py save "<a name they like>" --from-picks`.
- Either way, ask what to call it ("Cozy Talk", "Hype", their brand name). Propose one if they do not care.

Then set expectations once, in these words or close: "Your first edit takes a bit longer and we'll go back and forth
once or twice to dial the style in. After that, you drop clips in and say: edit them in <name>." Then ask for clips.

## The Studio Picker

A local page where the buyer picks one overall style, or their own caption style and effects, with a preview clip
on every card. It runs on their computer only. It is also how a buyer with a style built from examples adds the
Studio's effects to it: open the effects tab, then `my_styles.py save "<style>" --with-picks` keeps their own
captions and adds the picked effects.

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

## Building a style (from examples, links or words)

The picker is for buyers who do not know what they want yet. A buyer who sends a link to a reel they like, a file,
a pin, a screenshot, or says what they want in their own words, has given you the brief. Replicate it. The built-in
caption styles and effects step aside: you do not map their example onto the nearest one, you rebuild the look
itself, animation included. This works at setup and any time later ("make me a new style like this reel").
`references/replicate.md` has every field and command, `references/motion.md` every kind of movement. The procedure:

1. **Get and study every example.** `PY "SK/scripts/get_example.py" "<link or file>" ["<link 2>" ...]`, then
   `PY "SK/scripts/study.py" "<file>"` on each file it prints. Look at every sheet AND every motion strip
   (`motion_01.jpg` ...): the sheets show what is on screen, the strips show how it moves. A still shows type,
   colour and layout but not motion or sound: ask one question, or pick calm defaults and say so. Several
   examples: ask in ONE message what they want from each (replicate.md, "Several examples: mix and match").
2. **Name it and write it down.** `PY "SK/scripts/my_styles.py" new "<name>"`, then its `style.md`: one plain line
   per area (type, colour, captions, caption motion, pace, framing, graphic elements, sound, effects) and where each
   came from.
3. **Rebuild it on THEIR clips.** Their words, their takes, their length. Copy the rhythm, not the timing. Start the
   project in that style (`init_project.py "<project>" --my-style "<name>"`) and write the look into its plan.json:
   a custom caption spec with its motion, your own layers, the grade, reel motion, sounds.
4. **Check it side by side.** `PY "SK/scripts/side_by_side.py" "<example file>" "<project>" "renders/<slug>-v1.mp4"`
   puts example frames over frames of the final render. Also take snapshots in the MIDDLE of an entrance and compare
   them with the motion strip. Fix what is off, once. Then give the buyer the sheet and a plain list: what matches,
   and what could not be matched.
5. **Dial it in, then save it.** Their notes go into the reel; when they are happy:
   `PY "SK/scripts/my_styles.py" save "<name>" --from-project "<project>"`. Say: "Saved as <name>. Next time, drop
   clips in and say: edit them in <name>." The first saved style is the default (plain "edit it").

What is copied and what never is: the LOOK and the STRUCTURE are replicated (type feel, colours, layout, rhythm,
motion). Never the example's footage, music, voice, logo, handle, name or words, and never a claim that the result
is by or with whoever made it. Typeface: the nearest face the skill ships or an openly licensed one it can fetch;
never a paid font file, and you say which face stands in.

Be straight about the limits (`references/replicate.md` lists them): no music is added, the speaker is not moved
into a panel or onto a page outside the overall styles and effects that do that, no speed ramps or 3D. Say what
could not be matched. Never fake it.

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
Style = the saved style they name ("edit these in Hype": `my_styles.py list` shows the names, a part of one is
enough), else their default. No saved style and no picks: "First run only" above. Several styles, none named, and
the clips could suit more than one: ask which, in one line. Read the style's `style.md` before step 2: its pace,
framing and standing notes decide the cut.

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
6. PY "SK/scripts/init_project.py" "<project>" [--my-style "<name>"]   fonts, project files, starter plan.json
       (leave --my-style out for the default style). Write the pinned title, any on-screen text an overall style
       needs, and the reel's own parts of the style ("Graphic elements" in style.md, from THIS reel's words) into plan.json
7. effects picked?  PY "SK/scripts/footage_check.py" "<project>"   then, for each one that passes AND fits a line:
       it says "ready":   PY "SK/scripts/fx_new.py" <key> --project "<project>" --from <sec> --to <sec>
                          fill the CLIP block in the slot, run the commands it prints, then
                          PY "SK/scripts/fx_add.py" "<project>" "<slot>"      (writes the slot into plan.json)
       step by step: effects/INDEX.md
8. PY "SK/scripts/build_reel.py" "<project>" --safe     reads the reel's style -> index.html, unsafe area in red
                                                        (its "style" line says which style: check it)
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
    Once per chat, after a reel they are happy with, you may offer: "Want a carousel from this reel too?" A yes is
    the carousel-studio skill, with this project as the source.
```

`build_reel.py` prints `NOTE` lines when something could not be done
as picked (no room above the head, a look that needs a cutout, a caption swap that cannot ride on a style): pass
each one on to the buyer in plain words, and fix what can be fixed.

A look that goes behind the speaker or lifts them out of the room (Bold captions, Chalk Talk, Show and Tell) needs
a person cutout of the whole reel first. Use the clean one, `rvm_cut.py`, and tell the buyer how long it takes
before you start (`references/checks.md`). Almost every effect needs the clean cutout too (`effects/INDEX.md` says which do not), but only of its own frames:
`fx_new.py` does that (about 1.2 to 1.8 seconds per frame on an Apple Silicon Mac, so about 2 minutes for a 3
second effect). Both need `setup.py --matting` once. Every clean cutout ends with a `head check:` line (a picture
behind the head taken off the cutout, or not): pass it on as `references/checks.md` says.

Look at one reel snapshot inside every slot: one caption look, nothing doubled, no spoken word without a
caption unless the effect's own words carry it.

Notes round: change `edl.json` / `words.json` / `plan.json`, rebuild from the step that changed, render `-v2`. Keep
every version in `renders/`. A note meant for every reel ("always", "from now on") goes into the style too: after
they approve, `my_styles.py save "<style>" --from-project "<project>"`, plus a line in its style.md.

## Trial reel variations ("make 8 variations for my trial reels")

After a reel is edited, the buyer can ask for N versions of it to post as Instagram trial reels. Each version is a
finished reel from the same raw clips that differs in ONE thing: the hook (another take, another line first,
another opening cut, one more animation in the first seconds, a new opening headline), the caption style, the
effect set, or the saved style. `references/variations.md` has every detail. No reel edited yet: edit it first, then
make the variations.

Every trial is also its own video, never a near copy: on top of the one thing it tests it gets its own speed (0.965
to 1.035x, voice pitch kept), a reframe around the face (3.5 to 7% tighter) and a light grade, and no two trials
share them. Mirror stays off unless you LOOKED at the footage and found no readable text (logos on clothes or caps,
posters, screens, signs) and the reel has no effect slots, words behind the head or overall style. A trial the buyer
posted is marked (`variations.py posted`) and never touched again. Never promise a trial "won't get flagged".

```
1. PY "SK/scripts/variations.py" plan "<project>" --count <N> [--change hook,captions,effects,style]
       they said what each should change ("all different hooks"): pass --change or edit <project>/variations.json.
       They did not: show the proposed mix as a short list and ask in ONE message before building. Wait.
2. PY "SK/scripts/variations.py" make "<project>"     do every CHECK line in that trial's own folder
3. PY "SK/scripts/variations.py" render "<project>"   IN THE BACKGROUND. One render after another, never in
       parallel (two at once can run the computer out of memory). LOOK at each self-check sheet as it lands,
       the punched-in frames first: nothing may cover the mouth or chin there.
4. deliver <project>/trial-reels/ and the list (PY "SK/scripts/variations.py" list "<project>")
5. they posted one: PY "SK/scripts/variations.py" posted "<project>" <n>
```

## Posting ("post it")

The buyer can have you post a finished reel or their trial reels for them: Instagram (normal reels or trial reels),
TikTok, YouTube Shorts, Facebook Reels and more, now, at a set time, or a few minutes apart. It goes through their own
Zernio account (free for their first 2 connected accounts). `references/posting.md` has the setup, every step and
the words.

```
PY "SK/scripts/post.py" check                      key saved? accounts connected? (setup steps when not)
PY "SK/scripts/post.py" new "<project>/posting.json" "<file or folder>" --platforms instagram,tiktok [--trial] [--every 5m]
   write every caption in posting.json, then:
PY "SK/scripts/post.py" plan "<project>/posting.json"          show the buyer the plan, get a clear yes
PY "SK/scripts/post.py" run "<project>/posting.json" --yes     only after that yes
PY "SK/scripts/post.py" status "<project>/posting.json" --wait the links, or what failed and the fix
```

Never post, schedule or cancel without a clear yes to that exact plan, and only to the platforms they named. Trial
reels are an Instagram thing: other platforms in the same post get a normal post.

Styles on request: "save this as a new style called X" (`my_styles.py save "X" --from-project`), "what styles do I
have" (`list`), "make Hype my default" (`default`), "rename", "make a copy of Cozy with yellow captions"
(`duplicate`, then change the copy), "get rid of X" (`retire`: kept, never deleted). `references/my-styles.md`.

## What the buyer hears

- Start of an edit: "On it. I'm picking your best takes and cutting the dead air."
- A skipped effect: "I left Clone out of this one: it needs a wide shot with a still camera and this clip is a close-up."
- A fallback: "Your face fills the frame in this clip, so I kept the captions to one line under your chin."
- A slow step: "This look needs a clean cutout of you. That takes about 12 minutes for this reel. I'll keep going
  and tell you when it's done."
- Delivery: "Here's your reel in Cozy Talk. Effects: Digital Zoom on the hook. Tell me what to change."
- The first reel in a new style: "This is the first one in this style, so tell me everything you'd change. Once
  it's dialed in I'll save it and the next ones come out like this from the start."
- An effect made of words: "I matched the Checklist to your Karaoke captions: same typeface, same caps, same
  yellow."
- An example they showed you, before you start: "On it. I'm studying your example from start to finish, then I'll
  rebuild that look on your clip."
- After replicating it: "Here is what I matched, and what I could not. Tell me what to change, then I'll save it
  as <name>."
- Saved: "Saved as <name>. Next time, drop your clips in and say: edit them in <name>."
- A quiet recording: "Your voice is recorded a little quiet in this clip. Want a louder copy?"
- Variations, before building: "Here's the mix I'd test: 3 different hooks, 3 caption styles, one with no effects,
  one in your Hype style. Want that, or should they all test the hook?"
- Variations, while rendering: "On it. I'm rendering them one at a time so your computer doesn't choke. That takes
  about 20 minutes. I'll tell you when they're ready."
- Variations, delivered: "Your 8 trial reels are in the trial-reels folder. Same clips, one thing different in
  each, and each one has its own speed, framing and colour so none of them is a copy of another:" then one line per
  file ("trial-01-hook-take-2.mp4: opens on your other take of the first line"). "Post them as trial reels and keep
  the one that wins. Want me to post them for you?"

The styles for her (Soft Hours, Glam Cam, Color Block, Camera Shy) work faceless or on camera. Say it that way.
