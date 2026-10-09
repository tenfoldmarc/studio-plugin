# Gotchas (each one cost a render)

## Timing / sync
- ffmpeg concat leaves a 0.033s start offset and uneven frame gaps, and a cutout made from that drifts.
  `assemble.py` re-encodes to clean 30fps; `cutout.py` and `rvm_cut.py` stop when the frame counts differ.
- `tl.set` at a rounded time fires one frame late: use `frame/30 - 0.002` (the engine's `T()` does this).
- `HF snapshot` seeks roughly at cuts and can show the next shot a frame early. Only frames from the final render
  prove a cut (`check_cuts.py`, `frames_check.py`).
- Whisper word starts can be 0.1 to 0.3s off and it can invent a word at a cut. Confirm pauses with silencedetect.
- Whisper splits "GPT-6" and "5.1" into two tokens and hears "Claude" as "cloud". Fix `words.json` by hand.

## HyperFrames (pinned: hyperframes@0.8.34, Node 22+, always started through `HF`)
- Lint: states hidden at the start use `gsap.set` outside the timeline; every exit needs a hard `tl.set` kill; every
  `<video>` and `<audio>` needs an `id` (a video without one renders frozen); clips that touch in time go on
  different `data-track-index` values; one composition per `index.html`.
- Never tween autoAlpha or opacity on an element that has `data-start`: wrap it in a plain div and animate that.
- `fromTo` shows its from-state at once: pass `immediateRender:false` for anything hidden until its time.
- `autoAlpha:1` sets opacity to 1 and overrides a CSS opacity on the same element.
- Lint rejects tweening letterSpacing: fake tracking with scaleX.
- Element ids cannot contain apostrophes.
- CSS masks do not survive the renderer. Bake alpha into a VP9 webm instead.
- Reading an alpha webm with ffmpeg: `-c:v libvpx-vp9` BEFORE `-i`, and `alphaextract` before `scale`.
- Heavy backdrop-filter or blur on many elements can turn captures black. Keep it to a few.
- HyperFrames shifts video colours slightly against stills and CSS colours: a frozen frame next to live video
  needs a colour match (see `effects/freeze-and-label/effect.md`).

## Tools
- Python scripts run in the skill's own environment: read `python` from `ST/.platform.json` (`PY`). Its path
  differs per OS.
- Transcription dies with `unexpected keyword argument 'metadata_errors'`: run `setup.py` again, it repairs it.
- The skill writes only in its state folder `ST` and in the project folder. Never into `SK`.
- A shell safety hook can block a command that runs a program held in a variable, or a long inline `python -c`:
  put such steps in a small script file in the project's `work/` folder and run that.
- Large uploads to chat can fail: deliver the 720p phone copy and keep the full render on disk.
- Effects that track the room or the face need extra packages (`effects/INDEX.md` lists them per effect). Install
  them into the skill's own Python: `PY -m pip install opencv-python-headless`. mediapipe has no build for every
  Python version: if it will not install, skip that effect and say so.

## Windows (same skill, different shell)
- Claude Code runs commands in Git Bash when Git for Windows is installed, otherwise PowerShell. Write commands
  that work in both: full paths in double quotes with forward slashes, one command per call, no `&&`, no
  `VAR=1 cmd`, no `~` in arguments. In PowerShell start a quoted program with `&`.
- `python3` is usually a Store stub. Use `PY` for everything; before the environment exists try `python`, then `py -3`.
- A program installed while Claude Code is open is not found until Claude Code is fully quit and reopened.
- The quick cutout has no GPU path on Windows: it runs on the processor. Run it in the background.
- Windows opens text files as cp1252 unless told otherwise: every `open()` you write needs `encoding='utf-8'`.
- Never put a file path inside an ffmpeg filter (drive colons break it). Pass files with `-i`.
- Smart App Control or antivirus can block the image library HyperFrames loads, or make ffmpeg fail once with
  `spawn EBUSY`. Retry once, then tell the buyer what Windows blocked.
- Windows on ARM: the transcription engine has no ARM build; `setup.py` asks for the x64 Python.
- Helper files ending in `.sh` inside `effects/` are notes from the Mac builds. Do not run them: run the ffmpeg and
  HyperFrames commands they contain directly.
