#!/usr/bin/env python3
"""Start an effect slot for a READY effect: a small self-contained project that turns N frames of the reel into the
same N frames with one effect applied (1080x1920, 30fps, same audio). build_reel.py then lays the slot's render over
the reel for exactly those frames.

Inside a reel project (the normal way):
  PY fx_new.py <effect key> --project <project> --from <sec> --to <sec>
      slot folder   <project>/fx/<effect key>/         (--name <folder> for a second slot of the same effect)
      footage       the frames of <project>/assets/aroll.mp4 between --from and --to (reel seconds)
      words         the reel's own cleaned words.json, cut to the slot, times counted from the slot start
      cutout        cut from <project>/assets/subject.webm when the reel has one, else only the slot's frames are
                    matted with the clean cutout (rvm_cut.py: about 1.2 s per frame, say so before starting)

Any clip (same inputs and outputs as the effects were packaged with):
  PY fx_new.py <effect key> <slot_dir> --src <video> (--frame F | --in SEC) --frames N

Options:
An effect that lives on a cut (Zoom-Through Cut): give a span ACROSS one cut of the reel, about 0.5s each side.
The slot then holds both shots, clip.json records the cut frame, and the cutout is reset on the cut.

  --hi                    also write assets/aroll_hi.mp4 at the source's own size (deep zooms stay sharp)
  --cutout-from <webm>    cut the cutout out of a full-length one (same frame numbering as --src)
  --no-cutout             skip the cutout (effects that do not layer the speaker)
  --no-transcribe         skip words.json      --prompt "Claude, skill"   names for the transcription
  --picks <file>          read this picks file instead of the saved one (for the parts the buyer allowed)
  --buyer-files <folder>  for an effect that shows the buyer's own material (Couch Wall: their reel covers): copy the
                          files of that folder into the slot. The skill ships none; no material = no effect
  --force                 overwrite effect files that already exist in the slot (a CLIP block you filled is lost)

What ends up in the slot: the effect's scripts and effect.md, hyperframes.json, package.json, assets/fonts,
assets/sfx (the sound effects setup fetched), assets/aroll.mp4 (exactly N frames), words.json, clip.json,
assets/subject.webm. Then: read <slot>/effect.md, fill the CLIP block at the top of build.py, and run the commands
this script prints (they are saved in <slot>/RUN.txt).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402
import fxlib  # noqa: E402

SK = skillenv.SKILL_DIR
ENGINE = os.path.join(SK, 'engine')
# The effects ask for these weights by file name. The skill ships one variable font file per family, so the slot
# gets a copy under the second name plus its @font-face line: (family, weight, the file it is a copy of).
FONT_ALIASES = {
    'Inter-600-normal.woff2': ('Inter', 600, 'Inter-500-normal.woff2'),
    'Montserrat-600-normal.woff2': ('Montserrat', 600, 'Montserrat-500-normal.woff2'),
}
SHIM = '''#!/usr/bin/env python3
"""Forwards to the skill's clean cutout (written by fx_new.py; effects call _shared/rvm_cut.py from the slot)."""
import subprocess
import sys

sys.exit(subprocess.call([sys.executable, {script!r}] + sys.argv[1:]))
'''


def parse():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('effect', nargs='?')
    ap.add_argument('slot', nargs='?')
    ap.add_argument('--project')
    ap.add_argument('--from', dest='t_from', type=float)
    ap.add_argument('--to', dest='t_to', type=float)
    ap.add_argument('--name')
    ap.add_argument('--src')
    ap.add_argument('--frame', type=int)
    ap.add_argument('--in', dest='t_in', type=float)
    ap.add_argument('--frames', type=int)
    ap.add_argument('--hi', action='store_true')
    ap.add_argument('--cutout-from')
    ap.add_argument('--no-cutout', action='store_true')
    ap.add_argument('--prompt', default='Claude, Claude Code, skill.')
    ap.add_argument('--no-transcribe', action='store_true')
    ap.add_argument('--picks')
    ap.add_argument('--buyer-files')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('-h', '--help', action='store_true')
    return ap.parse_args()


def copy_tree(src, dst, force, skip=()):
    for name in sorted(os.listdir(src)):
        if name in skip or name.startswith('.') or name == '__pycache__':
            continue
        sp, dp = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(sp):
            os.makedirs(dp, exist_ok=True)
            copy_tree(sp, dp, force)
        elif force or not os.path.exists(dp):
            shutil.copyfile(sp, dp)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def fps_of(path, fp):
    out = subprocess.run([fp, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of',
                          'csv=p=0', path], **skillenv.TEXT).stdout.strip().split(',')[0] or '30/1'
    num, den = (float(x) for x in (out.split('/') + ['1'])[:2])
    return num / den if den else 30.0


def main():
    skillenv.utf8_stdio()
    a = parse()
    ready = fxlib.ready_keys()
    if a.help or not a.effect:
        sys.exit(__doc__ + '\nReady effects: ' + ', '.join(ready))
    FF, FP = skillenv.tool('ffmpeg'), skillenv.tool('ffprobe')
    key = a.effect
    meta = fxlib.slot_meta(key)
    entry = fxlib.index().get(key)
    if not entry:
        sys.exit(f'"{key}" is not one of the effects. Ready ones: ' + ', '.join(ready))
    if entry.get('status') != 'ready' or not meta:
        sys.exit(f'{entry["name"]} is a recipe, not a ready effect: there is no slot to make. Adapt effects/{key}/build.py '
                 f'by hand as effects/INDEX.md describes. Ready ones: ' + ', '.join(ready))
    src_dir = os.path.join(fxlib.EFFECTS, key)

    # ---------------------------------------------------------------- where the frames come from
    proj = skillenv.path_arg(a.project) if a.project else None
    segs, cut_frames = [], []
    if proj:
        if a.t_from is None or a.t_to is None:
            sys.exit('with --project pass --from <sec> and --to <sec> (reel seconds)')
        src = os.path.join(proj, 'assets', 'aroll.mp4')
        if not os.path.isfile(src):
            sys.exit(f'{src} is missing: run assemble.py first.')
        frame0 = max(0, round(a.t_from * 30))
        total = fxlib.probe_frames(src)
        n = min(round(a.t_to * 30), total) - frame0
        if n < 15:
            sys.exit(f'that span is {n} frames: a slot needs at least half a second inside the reel ({total} frames long)')
        slot = os.path.join(proj, 'fx', skillenv.safe_name(a.name or key))
        segs = fxlib.read(os.path.join(proj, 'segments.json'), []) or []
        cut_frames = [s['frame'] - frame0 for s in segs if frame0 < s['frame'] < frame0 + n]
        two_shot = int(entry.get('segments') or 1) >= 2
        if cut_frames and not two_shot:
            sys.exit(f'{entry["name"]} needs one continuous shot and this span crosses a cut at reel frame '
                     f'{cut_frames[0] + frame0} ({(cut_frames[0] + frame0) / 30:.2f}s). Move --from / --to to one side of it.')
        if two_shot:
            # an effect that lives ON a cut: the span has to hold exactly one cut of the reel, with room on both sides
            cuts = ', '.join(f'{s["frame"] / 30:.2f}s' for s in segs[1:]) or 'none: this reel is one continuous take'
            if len(cut_frames) != 1:
                sys.exit(f'{entry["name"]} needs exactly one cut of the reel inside the span, and {frame0 / 30:.2f} to '
                         f'{(frame0 + n) / 30:.2f}s holds {len(cut_frames)}. Cuts in this reel: {cuts}. '
                         'Use --from about 0.5s before one cut and --to about 0.5s after it.')
            k = cut_frames[0]
            if k < 11 or n - k < 11:
                sys.exit(f'{entry["name"]} needs at least 11 frames on each side of the cut; this span has {k} before and '
                         f'{n - k} after. Widen --from / --to (the cut is at {(frame0 + k) / 30:.2f}s).')
            print(f'two shots: cut on slot frame {k} (reel {(frame0 + k) / 30:.3f}s), {k} frames before, {n - k} after. '
                  'clip.json carries the cut, so the effect\'s own two-shot step is not needed.')
        picks = fxlib.read(skillenv.path_arg(a.picks) if a.picks else skillenv.picks_file(), {}) or {}
        where, _ = fxlib.reel_parts(proj)
        ok, why = fxlib.part_verdict(picks, key, where, frame0 / 30, (frame0 + n) / 30)
        if not ok:
            sys.exit(f'NOT ALLOWED HERE  {entry["name"]}: {why}. Pick another moment, or leave it out and tell the buyer.')
        print(f'parts: {why}')
        if key not in (picks.get('effects') or []):
            print(f'note: {entry["name"]} is not in the saved picks. Fine for a one-off the buyer asked for; otherwise leave it out.')
        rate, t0 = 30.0, frame0 / 30
    else:
        if not a.slot or not a.src or a.frames is None or (a.frame is None) == (a.t_in is None):
            sys.exit('pass --project <project> --from S --to S, or: <slot_dir> --src <video> (--frame F | --in SEC) --frames N')
        slot, src, n = skillenv.path_arg(a.slot), skillenv.path_arg(a.src), a.frames
        rate = fps_of(src, FP)
        t0 = a.t_in if a.t_in is not None else a.frame / rate
        frame0 = a.frame if a.frame is not None else round(a.t_in * rate)
    slot = os.path.abspath(slot)
    for d in ('assets', 'work', 'renders'):
        os.makedirs(os.path.join(slot, d), exist_ok=True)
    dur = n / 30

    # ---------------------------------------------------------------- 1 + 2: effect files, fonts, sounds, template
    copy_tree(src_dir, slot, a.force, skip=('example', 'slot.json'))
    shutil.copyfile(os.path.join(src_dir, 'slot.json'), os.path.join(slot, 'slot.json'))
    buyer = meta.get('buyer_folder')        # material only the buyer has (their own reel covers, ...): never shipped
    buyer_note = ''
    if buyer:
        bdir = os.path.join(slot, buyer['name'])
        os.makedirs(bdir, exist_ok=True)
        if a.buyer_files:
            given = skillenv.path_arg(a.buyer_files)
            if not os.path.isdir(given):
                sys.exit(f'--buyer-files: {given} is not a folder')
            for f in sorted(os.listdir(given)):
                if not f.startswith('.') and os.path.isfile(os.path.join(given, f)):
                    shutil.copyfile(os.path.join(given, f), os.path.join(bdir, f))
        have = len([f for f in os.listdir(bdir) if not f.startswith('.')])
        need = 1 if buyer.get('min') is None else int(buyer['min'])
        if need == 0:                       # an optional folder (Phone Mockup: their own screen, or the packaged card)
            if not have:
                buyer_note = (f'FROM THE BUYER, if they have it: {buyer["what"]}. Files go into '
                              f'"{skillenv.shell_path(bdir)}" (or run this command again with --buyer-files <their folder>).')
            else:
                print(f'{buyer["name"]}: {have} file(s) from the buyer')
        elif have < need:
            buyer_note = (f'FROM THE BUYER, before anything else: {buyer["what"]}. At least {need} files, into '
                          f'"{skillenv.shell_path(bdir)}" (or run this command again with --buyer-files <their folder>). '
                          f'The skill ships none. If the buyer has none, leave {entry["name"]} out and say so.')
        else:
            print(f'{buyer["name"]}: {have} file(s) from the buyer')
    os.makedirs(os.path.join(slot, '_shared'), exist_ok=True)
    with open(os.path.join(slot, '_shared', 'rvm_cut.py'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(SHIM.format(script=os.path.join(HERE, 'rvm_cut.py')))
    for f in ('hyperframes.json', 'package.json'):
        if not os.path.exists(os.path.join(slot, f)):
            shutil.copyfile(os.path.join(ENGINE, 'template', f), os.path.join(slot, f))
    fonts = os.path.join(slot, 'assets', 'fonts')
    os.makedirs(fonts, exist_ok=True)
    copy_tree(os.path.join(ENGINE, 'fonts'), fonts, force=False)
    css_path = os.path.join(fonts, 'fonts.css')
    with open(css_path, encoding='utf-8') as fh:
        css = fh.read()
    extra = ''
    for name, (family, weight, same_as) in FONT_ALIASES.items():
        if os.path.isfile(os.path.join(fonts, same_as)) and not os.path.exists(os.path.join(fonts, name)):
            shutil.copyfile(os.path.join(fonts, same_as), os.path.join(fonts, name))
        if f"url('{name}')" not in css:
            extra += (f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;"
                      f"src:url('{name}') format('woff2');}}\n")
    if extra:
        with open(css_path, 'a', encoding='utf-8', newline='\n') as fh:
            fh.write('\n' + extra)
    sfx_src, sfx_dst = skillenv.sfx_dir(), os.path.join(slot, 'assets', 'sfx')
    os.makedirs(sfx_dst, exist_ok=True)
    sounds = sorted(f for f in os.listdir(sfx_src) if f.lower().endswith('.mp3')) if os.path.isdir(sfx_src) else []
    for f in sounds:
        if not os.path.exists(os.path.join(sfx_dst, f)):
            shutil.copyfile(os.path.join(sfx_src, f), os.path.join(sfx_dst, f))
    # sounds an effect makes out of a stock one (a shorter hit, a single tick): built here, never shipped
    for rel, how in (meta.get('sounds') or {}).items():
        out, base = os.path.join(slot, *rel.split('/')), os.path.join(sfx_src, how['from'] + '.mp3')
        if os.path.exists(out) or not os.path.isfile(base):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        af = [f"afade=t=out:st={how['fade_out'][0]}:d={how['fade_out'][1]}"] if how.get('fade_out') else []
        r = subprocess.run([FF, '-v', 'error', '-y', '-i', base, '-t', str(how.get('duration', 1))]
                           + (['-af', ','.join(af)] if af else []) + [out], **skillenv.TEXT)
        if r.returncode != 0:
            print(f'note: could not make {rel} ({(r.stderr or "").strip()[-120:]}): build this effect with SFX=0')
    if not sounds:
        print('note: no sound effects on this machine (setup.py reported them MISSING): fx_run.py builds this slot with SFX=0')

    # ---------------------------------------------------------------- 3: the slot's a-roll
    seek = max(0.0, t0 - 0.001)          # 1 ms early so rounding can never skip the first frame
    fit = 'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1'
    enc = ['-frames:v', str(n), '-fps_mode', 'cfr', '-r', '30', '-c:v', 'libx264', '-crf', '14', '-preset', 'medium',
           '-pix_fmt', 'yuv420p']
    aud = ['-af', f'apad,atrim=0:{dur:.4f}', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '192k']
    aroll = os.path.join(slot, 'assets', 'aroll.mp4')
    run([FF, '-v', 'error', '-y', '-ss', f'{seek:.4f}', '-i', src, '-t', f'{dur + 0.2:.4f}', '-vf', f'fps=30,{fit}']
        + enc + aud + [aroll])
    got = fxlib.probe_frames(aroll)
    if got != n:
        sys.exit(f'the slot a-roll has {got} frames, expected {n}: the source is shorter than the span you asked for')
    hi_note = ''
    if a.hi:
        hi = os.path.join(slot, 'assets', 'aroll_hi.mp4')
        native = "crop='min(iw,floor(ih*9/32)*2)':'min(ih,floor(iw*16/18)*2)',setsar=1"   # 9:16 at the source's own size
        seg = next((s for s in segs if s['frame'] <= frame0 and frame0 + n <= s['frame'] + s['frames']), None) if proj else None
        sources = fxlib.read(os.path.join(proj, 'sources.json'), {}) if proj else {}
        raw = sources.get(seg['clip']) if seg else None
        if proj and not (raw and os.path.isfile(raw)):
            hi_note = 'aroll_hi: the original clip of this span was not found, so the slot works from the 1080 a-roll (HI=0)'
        elif proj and float(seg.get('zoom') or 1) > 1.001:
            hi_note = 'aroll_hi: this part of the reel is already a punch-in, so the slot works from the 1080 a-roll (HI=0)'
        elif proj:
            # the same decode as assemble.py (seek to the segment start, 30fps), then keep exactly this slot's frames
            j = frame0 - seg['frame']
            vf = f"fps=30,select='between(n\\,{j}\\,{j + n - 1})',setpts=N/30/TB,{native}"
            run([FF, '-v', 'error', '-y', '-ss', f"{seg['src_in']:.3f}", '-i', raw, '-an', '-vf', vf] + enc + [hi])
            hi_note = f'aroll_hi: {fxlib.probe_frames(hi)} frames at {"x".join(str(v) for v in fxlib.probe_size(hi))} from the original clip'
        else:
            run([FF, '-v', 'error', '-y', '-ss', f'{seek:.4f}', '-i', src, '-t', f'{dur + 0.2:.4f}', '-an', '-vf',
                 f'fps=30,{native}'] + enc + [hi])
            hi_note = f'aroll_hi: {fxlib.probe_frames(hi)} frames at {"x".join(str(v) for v in fxlib.probe_size(hi))}'
    clip = {'effect': meta.get('pack') or key, 'key': key, 'src': os.path.abspath(src), 'src_fps': round(rate, 4),
            'in': round(t0, 4), 'frame': frame0, 'frames': n, 'duration': round(dur, 4), 'cut_frames': cut_frames,
            'hi_res': bool(a.hi and os.path.isfile(os.path.join(slot, 'assets', 'aroll_hi.mp4')))}
    if proj:
        clip['project'] = os.path.abspath(proj)
    fxlib.write(os.path.join(slot, 'clip.json'), clip)
    print(f'a-roll: {n} frames ({dur:.2f}s) from {os.path.basename(src)} @ {t0:.3f}s (frame {frame0})')
    if hi_note:
        print(hi_note)

    # ---------------------------------------------------------------- 4: words
    words_path = os.path.join(slot, 'words.json')
    reel_words = fxlib.read(os.path.join(proj, 'words.json')) if proj else None
    if a.no_transcribe or (os.path.exists(words_path) and not a.force):
        pass
    elif reel_words:
        t1 = t0 + dur
        ws = [{'text': w['text'], 'start': round(max(0.0, w['start'] - t0), 3), 'end': round(min(dur, w['end'] - t0), 3)}
              for w in reel_words if w['end'] > t0 + .02 and w['start'] < t1 - .02]
        fxlib.write(words_path, ws)
        print('words (from the reel, already cleaned): ' + ' '.join(f"{w['text']}@{w['start']:.2f}" for w in ws))
        print('  (word starts can be 0.1 to 0.3s off: confirm onsets with the effect\'s own measuring script)')
    else:
        try:
            from faster_whisper import WhisperModel
            wav = os.path.join(slot, 'work', 'aroll.wav')
            run([FF, '-v', 'error', '-y', '-i', aroll, '-vn', '-ac', '1', '-ar', '16000', wav])
            model = WhisperModel('medium.en', compute_type='int8')
            segments, _ = model.transcribe(wav, word_timestamps=True, vad_filter=False, initial_prompt=a.prompt)
            ws = [{'text': w.word.strip(), 'start': round(w.start, 3), 'end': round(w.end, 3)} for s in segments for w in s.words]
            fxlib.write(words_path, ws)
            print('words: ' + ' '.join(f"{w['text']}@{w['start']:.2f}" for w in ws))
            print('  (names get misheard and word starts can be 0.1 to 0.3s off: fix the spelling, confirm onsets on the audio)')
        except ImportError:
            print('words: the transcription package is missing in this Python. Run the script with the skill\'s own Python (PY).')

    # ---------------------------------------------------------------- 5: cutout
    sub = os.path.join(slot, 'assets', 'subject.webm')
    need = meta.get('cutout', 'layer')
    full = a.cutout_from or (os.path.join(proj, 'assets', 'subject.webm') if proj else None)
    status = 0
    if a.no_cutout or need == 'none':
        print('cutout: skipped (' + ('--no-cutout' if a.no_cutout else 'this effect does not use one') + ')')
    elif os.path.isfile(sub) and os.path.isfile(os.path.join(slot, 'assets', '.cutout_done')) and not a.force \
            and fxlib.probe_frames(sub) == n:
        print(f'cutout: kept the one already in the slot ({n} frames)')
    elif full and os.path.isfile(full):
        run([FF, '-v', 'error', '-y', '-c:v', 'libvpx-vp9', '-i', full, '-vf',
             f"select='between(n\\,{frame0}\\,{frame0 + n - 1})',setpts=N/30/TB", '-fps_mode', 'cfr', '-r', '30',
             '-an', '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '20', '-g', '30',
             '-auto-alt-ref', '0', '-row-mt', '1', '-cpu-used', '4', '-metadata:s:v:0', 'alpha_mode=1', sub])
        c = fxlib.probe_frames(sub)
        print(f'cutout: cut {c} frames out of {os.path.basename(full)}' + ('' if c == n else '  !! FRAME MISMATCH'))
        status = 0 if c == n else 2
    else:
        print(f'cutout: matting {n} frames with the clean cutout, about {n * 1.2 / 60:.1f} min on an Apple Silicon Mac ...', flush=True)
        r = subprocess.run([sys.executable, os.path.join(HERE, 'rvm_cut.py'), slot])
        c = fxlib.probe_frames(sub) if r.returncode == 0 and os.path.isfile(sub) else 0
        if c == n:
            print(f'cutout: {c} frames')
        else:
            status = 2
            print('cutout: NOT MADE. If the line above says the clean cutout is not set up, run  setup.py --matting  once '
                  '(about 105 MB), then run this same command again (what is already in the slot is kept).')
    if os.path.isfile(sub) and status == 0:
        open(os.path.join(slot, 'assets', '.cutout_done'), 'w').close()
        warn = fxlib.head_check(proj, slot, t0) if proj else None
        if warn:
            print(warn)

    def fit_snapshot(rest):
        """Example snapshot times in a step come from the demo clip. When they run past the end of THIS slot, spread
        the same number of moments over the slot instead, so the command works as printed."""
        m = re.match(r'(snapshot --at )([\d.]+(?:,[\d.]+)*)(.*)$', rest)
        if not m:
            return rest
        times = [float(x) for x in m.group(2).split(',')]
        if max(times) <= dur - .05:
            return rest
        even = ','.join(f'{dur * (i + 1) / (len(times) + 1):.2f}' for i in range(len(times)))
        tail = m.group(3) if m.group(3).strip() else '      # spread over this slot: use your own moments'
        return f'{m.group(1)}{even}{tail}'

    # ---------------------------------------------------------------- what to do next
    py, sk = skillenv.shell_path(sys.executable), skillenv.shell_path(SK)
    sl = skillenv.shell_path(slot)
    runner = f'"{py}" "{sk}/scripts/fx_run.py" "{sl}"'
    lines = [f'# {entry["name"]} slot: {n} frames, reel {frame0 / 30:.3f}s to {(frame0 + n) / 30:.3f}s' if proj else f'# {entry["name"]} slot: {n} frames',
             f'# 1. read "{sl}/effect.md"   2. fill the CLIP block at the top of "{sl}/build.py"   3. run, in this order:']
    if buyer_note:
        lines.append('# ' + buyer_note)
    for step in meta.get('steps') or []:
        kind, _, rest = step.partition(' ')
        if kind == 'run':
            lines.append(f'{runner} {rest}')
        elif kind == 'hf':
            lines.append(f'{runner} hf {fit_snapshot(rest)}')
        else:
            lines.append(f'#    {step}')
    for note in meta.get('in_a_reel') or []:
        lines.append(f'# note: {note}')
    if proj:
        lines.append(f'"{py}" "{sk}/scripts/fx_add.py" "{skillenv.shell_path(proj)}" "{sl}"      # lays the finished render into plan.json')
        lines.append(f'# then build_reel.py again, render, and check the slot\'s moments with frames_check.py --at')
    with open(os.path.join(slot, 'RUN.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    print(f'\nslot ready: {slot}' if status == 0 else f'\nslot started, cutout still missing: {slot}')
    print('\n'.join(lines))
    sys.exit(status)


if __name__ == '__main__':
    main()
