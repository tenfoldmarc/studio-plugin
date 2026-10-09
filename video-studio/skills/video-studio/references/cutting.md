# Cutting: best takes, dead air, a clean transcript

## 1. Ingest
`PY "SK/scripts/ingest.py" "<project>" <clips or one folder> [--newest N]` writes:
- `sources.json` (c1, c2 ... oldest to newest), `work/sheets.jpg` (8 frames across each clip: look at it for
  setups and angles), `words_cN.json`, and `transcript.txt` (per clip: lines with times, every word with its time,
  and a speech map where `S12.40` = silence starts and `E13.10` = silence ends).
Originals are read in place. Nothing is copied or changed. The first transcription downloads the speech model:
about 0.5 GB here, then 1.4 GB more at step 4 for the final pass (one time each). Tell the buyer before you start,
once: "The first edit downloads the speech model, about 2 GB. That happens once."

## 2. Pick takes -> `<project>/edl.json`
People repeat a line until it lands. Rebuild what they meant to say from the takes:
- Use the LAST complete clean take of each line, unless the buyer says otherwise ("the good one starts at 0:47"
  means one continuous take from there).
- In point: 0.05 to 0.07s before the first word. Out point: where the silence starts after the last word (speech map).
- Cut dead air between lines. Before trimming a short pause inside a line, confirm it with silencedetect
  (`ffmpeg -i <clip> -af silencedetect=n=-40dB:d=0.08 -f null -`): Whisper word times can be 0.1 to 0.3s off and it
  can invent a word at a cut.
- Two segments in a row from the same angle: punch one in (zoom 1.3 to 1.9, `cx` / `cy` on the chest). Sharp when
  the source is 4K, soft above about 1.4 on a 1080 source.
- Not sure about a name or the comment keyword: transcribe just that snippet again with the names in the prompt.

```json
[{"id": "hook", "clip": "c1", "in": 12.66, "out": 15.72, "zoom": 1.0, "cx": 0.5, "cy": 0.5, "line": "Everybody's talking about..."},
 {"id": "cta",  "clip": "c2", "in": 4.10,  "out": 7.02,  "zoom": 1.4, "cx": 0.5, "cy": 0.42, "line": "Comment EDIT and..."}]
```
`id` is a short name with letters only. Tell the buyer the plan in two lines and keep going. Do not wait for a yes.

## 3. Assemble
`PY "SK/scripts/assemble.py" "<project>"` cuts straight from the originals into `assets/aroll.mp4` (1080x1920,
clean 30fps from t=0) and writes `segments.json` (first frame and frame count of every segment, source size).
The last line must say the frame totals match.

## 4. Words
`PY "SK/scripts/transcribe_cut.py" "<project>" "Claude, Claude Code, <other names said>"` writes `words.json`:
`[{"text": "Everybody's", "start": 0.08, "end": 0.52}, ...]`. These times drive every caption, so clean them:
- Fix mishearings by hand from what was actually said. Usual ones: "Claude" -> "cloud" / "claws" / "Claud",
  "skill" -> "scale", product names split in two ("GPT" "-6", "5" ".1": the script joins the common cases, check).
- Keep Whisper's punctuation honest: a comma or full stop ends a caption phrase, so remove a comma that is not a
  pause and add a full stop where a sentence really ends.
- Keep numbers the way they should READ on screen ("7", not "seven", when a style shows the number big).
- Never change the times unless a word is clearly late or early against the audio.
`work/words_raw.json` keeps Whisper's untouched output.

Then mark the words: `PY "SK/scripts/marks.py" "<project>"` and the rule in `references/captions.md`.

## 5. Check the cuts (after the render)
`PY "SK/scripts/check_cuts.py" "<project>" "renders/<file>.mp4" --phone` writes `work/cut_check.jpg` (the frame before
and after every cut, side by side) and a 720p phone copy. Every "after" frame must show the new shot cleanly.
The render may be written the short way (`renders/<file>.mp4`): both check scripts look inside the project.

The last line it prints is the audio level (peak and average). The reel keeps the level the clip was recorded at:
nothing in the edit raises or lowers the voice. A peak of -6 dB or higher is fine. A lower peak is a quiet
recording: say so in the delivery note and offer a louder copy. To make one, raise it by the missing amount (peak
-8.6 dB -> `volume=5dB` brings it to about -3.6) with the ffmpeg from `.platform.json`, picture untouched:
`"<ffmpeg>" -i "<project>/renders/<file>.mp4" -af volume=5dB -c:v copy -c:a aac -b:a 192k "<project>/renders/<file>-louder.mp4"`
Never raise it so far that the peak goes above -1 dB.
