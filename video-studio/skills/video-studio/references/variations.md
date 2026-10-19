# Trial reel variations

Instagram trial reels show a reel to people who do not follow the buyer first, so they can test versions and keep
the winner. The buyer edits a reel as normal, then says "make 8 variations for my trial reels" (or "make 3
variations", "give me trial versions of this"). The Studio makes that many finished reels from the same raw clips,
each one different in ONE thing, so a winner tells them what worked.

`scripts/variations.py` does it in four steps: `plan`, `make`, `render`, `list`.

## What a variation can change

| change | what it means | how it is made |
| --- | --- | --- |
| hook | another opening: another take of the first line, another line first, a different opening cut, one more animation in the first seconds, a new opening headline | `edl` (any takes, any order), `punch` (the opening punched in close, cutting back to the usual framing in the first pause), `trim` (seconds cut off the start, e.g. a filler "So"), `opener` (an effect key for the first 3 seconds, or a short animation you write, references/motion.md), `plan` with a new `title` (a reel that opens on a pinned headline: write 2 or 3 options, the buyer picks) |
| captions | another caption style | `caption`: any of the 19 keys, or a custom spec |
| effects | another effect set | `effects`: the effect keys this trial keeps; `[]` = none |
| style | another saved style, or one of the 8 built-in overall looks | `myStyle`: a saved style name; `style`: an overall style key |

One change per variation is the clean test. Two in one ("new hook AND new captions") is allowed when the buyer asks
for it, but then a winner does not say which of the two did it: tell them so once.

## Every trial is its own video

Trial reels are posted next to each other from one account. A trial that only swaps the caption style keeps the
same voice track and the same frames as the reel and every other trial: as a file it is nearly a copy. So on top of
the one thing it tests, every trial gets its own light pass, `"unique"` in variations.json (plan and make fill it in):

| | what | how |
| --- | --- | --- |
| speed | 0.965 to 1.035, a different one per trial, never 1.0 | after the render, picture and voice together, voice pitch kept (`setpts` + `atempo`) |
| framing | 3.5 to 7% tighter, around the face, shifted a little to one side | `plan.json "reframe"`: the footage, the cutout and the effect slots move together; captions and layers do not, so text stays sharp and where it was placed |
| colour | a light grade on top of the reel's own | the same `"reframe"`, never black and white or a strong colour cast |
| mirror | OFF unless you turn it on | see "Mirror" below |

- The pass is small on purpose: a viewer only notices the one tested change, so a winner still says what worked.
- No two trials share a speed or a framing, and none is the reel itself (1.0x, unframed). The render stops a trial
  that would (`FAILED: it has the same speed as ...`): change its `"unique"`, make it again.
- A strict test with nothing else changed: `"unique": false` on that trial.
- Never tell the buyer the trials "won't get flagged": nobody outside Instagram knows how it compares videos. Say
  what was done: each one has its own speed, framing and colour, so none of them is a copy of another.

### Mirror

A mirrored trial differs the most, but it shows every word in the picture backwards. The plan never turns it on.
Turn it on for one trial (`"mirror": true` in its `"unique"`) only when ALL of these hold:
- you LOOKED at the footage (work/sheets.jpg and the reel's own frames) and found no readable text at all: no logo
  on clothes or a cap, no poster or framed print, no screen, sign or product label;
- the reel has no effect slots, no words or layers behind the head, and no overall style (make and the build stop
  a mirrored trial that has them: their words would read backwards);
- the buyer did not say anything about which side they are on ("on my left").
Then the layout is mirrored with the picture, so captions follow the face to the other side. Layers placed beside
the speaker stay where they were: LOOK at the self-check.

### Trials the buyer posted

The buyer posted trial 3: `PY "SK/scripts/variations.py" posted "<project>" 3`. That trial keeps its file and name,
is never made or rendered again (not even with `--redo`), and a fresh plan (`plan --fresh`) keeps it first, so every
new trial stays different from it. `--undo` takes the mark off. The edited reel itself is never touched by any of
this: it is the version most buyers post first.

### The face on punched-in shots

A punched-in part shows the face lower and bigger. A caption or card that clears the chin in the wide shots can
cover the mouth there, and a trial's framing moves the face a little more. The render runs the self-check with
`--punched` (the middle of every punched-in part is in the sheet): LOOK at those frames first. Something over the
mouth or chin: move it lower or make it smaller in that trial's folder, then render it again (`--only <n> --redo`).

## The workflow

```
1. the reel is edited and approved as normal (SKILL.md, "Workflow")
2. PY "SK/scripts/variations.py" plan "<project>" --count 8 [--change hook,captions,effects,style]
       proposes a mix -> <project>/variations.json and prints it
3. the buyer said what each one should change? Use that (--change, or edit variations.json).
   They did not? Show the proposed mix as a short numbered list and ask in ONE message, for example:
   "Here's the mix I'd test: 3 different hooks, 3 caption styles, one with no effects, one in your Hype style.
    Want that, or should they all test the hook?" Wait for the answer, then change variations.json to match.
4. PY "SK/scripts/variations.py" make "<project>"
       one working copy per variation in <project>/work/variations/<trial name>/. Read every CHECK line and do it
       in that trial's folder (fix new words, add an effect, write a new title) before rendering.
5. PY "SK/scripts/variations.py" render "<project>"        IN THE BACKGROUND
       one after another, never in parallel. Tell the buyer how long: the QUEUE line has the estimate.
       LOOK at each trial's self-check sheet (the "self-check: LOOK at" line) as it finishes.
6. deliver: the trial-reels folder and the short list (what-changed.txt, or `list`).
```

`plan` proposes, in this order of value: another take of the first line (found by reading every clip's transcript
for the same words outside the take in the reel), the opening without a filler word, a punched-in opening, one more
animation in the opening (an effect the buyer picked that may play there and is not in it yet), then
caption styles (the most different first; Bold only when the reel has a cutout), then no effects / one effect only
/ an effect the buyer picked that the reel does not have yet, then every other saved style. It takes one of each
kind in turn until it has the count. When it cannot reach the count on its own it says `SHORT` and the rest needs
your judgement, usually a hook: the strongest line of the reel as the opening (`edl` with that segment first, and
a new `title` under `"plan"`), a bolder first sentence from another take, or a new opening headline when the reel
opens on one (`IDEA` lines say which fit). It also prints each trial's own speed and framing (`UNIQUE`).

Writing a hook by hand: copy the reel's `edl.json` into the variation's `"edl"` and change it, exactly as in
`references/cutting.md`. Takes come from the raw clips (`transcript.txt`, `words_c1.json` ...), never invented.

## What make does for each change

- **hook**: cuts the trial again from the originals (`assemble.py`), then carries the reel over to the new times:
  every word the buyer already fixed and marked keeps its text and mark; only words that were never in the reel
  (another take) are transcribed, marked by the first-guess rule and listed in a CHECK line to fix by hand. Effect
  slots, timed layers, sound cues and timed reel motion move with their moment. An effect on a part the new
  opening changed is turned off (its render was made from the old frames): make it again in the trial's folder if
  it belongs. When the reel has a person cutout, the trial gets its own (`rvm_cut.py`, slow), so a look behind the
  speaker stays the same. Then `layout.py` finds the speaker in the new cut.
- **captions**: the trial's plan.json gets the caption key or spec. An overall style the reel is in is kept and only
  its captions are swapped.
- **effects**: slots not in the list are turned off. A key with no slot yet is a CHECK line with the exact
  `fx_new.py` / `fx_add.py` commands for the trial's folder (effects/INDEX.md, and the buyer's style still wins).
- **style**: the trial is built in that saved style; the reel's own look fields (caption, grade, css, motion
  patterns, layers) are taken out of its plan.json so the other style shows. CHECK lines: write this reel's graphic
  elements for that style, and turn off any effect whose words were restyled for the old style. A built-in overall
  style also needs its on-screen words in plan.json `"style"` (references/styles.md).

Every trial folder is a normal project: rebuild, snapshot and lint it with the usual commands when a CHECK needs it.

## Render: one after another

`render` builds, lints (0 errors), renders at high quality, runs `frames_check.py --punched`, gives the reel its
own speed and copies it into `<project>/trial-reels/` as `trial-01-<id>.mp4`, `trial-02-<id>.mp4` ... with
`what-changed.txt` beside them.
- Never two at once. A reel render takes the whole computer; two in parallel can run a Mac out of memory. Only one
  `make` or `render` runs per project (a second one says `STATUS variations BUSY` and stops).
- A trial that would come out the same as another one, or as the reel itself, fails before it renders: change
  something real.
- A trial already in trial-reels/ is kept; `--redo` renders it again, `--only 3` or `--only hook-take-2` picks one.
  `make` keeps a trial folder whose change is the same as before. A new plan (`plan --fresh`) moves the reels of
  the last one into `trial-reels/earlier-<date>/`, so the folder only ever holds the current set.
- A failed trial does not stop the queue: the last line says which failed (`STATUS variations INCOMPLETE`).

## What the buyer hears

- Asking: "Here's the mix I'd test: [the list]. Want that, or should they all test the hook?"
- Starting: "On it. I'm making 8 versions, then rendering them one at a time so your computer doesn't choke. That
  takes about 20 minutes. I'll tell you when they're ready."
- Delivery: "Your 8 trial reels are in the trial-reels folder. Same clips, one thing different in each, and each one
  has its own speed, framing and colour so none of them is a copy of another:" then the list, one line per file,
  for example:

```
trial-01-hook-take-2.mp4        Hook: opens on your other take of the first line
trial-02-captions-karaoke.mp4   Captions: Karaoke captions
trial-03-effects-none.mp4       Effects: no effects
trial-04-style-hype.mp4         Style: in your Hype style
```

  Then: "Post them as trial reels and keep the one that wins. Want me to post them for you? I can put them out a few
  minutes apart, on TikTok too." Yes: references/posting.md (`post.py new "<project>/posting.json"
  "<project>/trial-reels" --trial --every 5m`). Each one that goes to Instagram is marked posted by itself.
  Later: "Tell me which one won and I'll make it your default."
- They posted one: "Got it. Trial 3 stays exactly as you posted it, and anything new I make stays different from it."
  (`variations.py posted`).
- Never: "these won't get flagged". Say what was done instead (above).
- The buyer says which won: a hook is a lesson for the next scripts and edits (say it in one line); captions, effects
  or a style can become their default (`my_styles.py save` / `default`, references/my-styles.md).
