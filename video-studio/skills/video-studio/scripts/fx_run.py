#!/usr/bin/env python3
"""Run one step of an effect slot. One command style for zsh, bash, Git Bash and PowerShell: the switches an effect
takes as environment variables are written as plain NAME=value words, so there is no `SAFE=1 python build.py`
(which PowerShell cannot run) and no `cd`.

  PY fx_run.py <slot_dir> <script.py> [arguments] [NAME=value ...]     one of the effect's own scripts
  PY fx_run.py <slot_dir> hf lint
  PY fx_run.py <slot_dir> hf snapshot --at 0.2,1.0,2.0                 -> <slot>/work/snap/ (contact-sheet.jpg)
  PY fx_run.py <slot_dir> hf render                                    -> <slot>/renders/<slot folder>.mp4

Examples:
  PY fx_run.py "<project>/fx/odometer" measure.py
  PY fx_run.py "<project>/fx/odometer" build.py SAFE=1          red safe-zone guide, for snapshots only
  PY fx_run.py "<project>/fx/odometer" build.py                 guide off: always the last build before a render

What it takes care of:
  - the script runs inside the slot with the skill's own Python, UTF-8 output, and the ffmpeg and Node that setup
    found first on PATH (the effects look tools up on PATH)
  - `hf` is the pinned HyperFrames. snapshot gets `--no-end --describe false -o work/snap` unless you pass your own.
    render gets `-o renders/<slot folder>.mp4 --quality high`, REFUSES to run while the red safe-zone guide is still
    in index.html, and afterwards checks that the render has exactly the slot's frame count.
  - no sound effects on this machine: every script gets SFX=0 so the build does not point at missing files.
"""
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skillenv  # noqa: E402
import fxlib  # noqa: E402

ENV_WORD = re.compile(r'^[A-Z][A-Z0-9_]*=')


def main():
    skillenv.utf8_stdio()
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    slot = os.path.abspath(skillenv.path_arg(sys.argv[1]))
    if not os.path.isfile(os.path.join(slot, 'clip.json')):
        sys.exit(f'{slot} is not an effect slot (no clip.json). Make one with fx_new.py.')
    words = sys.argv[2:]
    switches = dict(w.split('=', 1) for w in words if ENV_WORD.match(w))
    args = [w for w in words if not ENV_WORD.match(w)]
    if not args:
        sys.exit('nothing to run: pass a script name (build.py) or hf lint / snapshot / render')
    name = os.path.basename(slot)
    clip = fxlib.read(os.path.join(slot, 'clip.json'), {}) or {}
    index = os.path.join(slot, 'index.html')

    if args[0] == 'hf':
        hf = args[1:]
        if not hf:
            sys.exit('hf what? lint, snapshot --at <times>, or render')
        if hf[0] == 'snapshot':
            if '--no-end' not in hf:
                hf.append('--no-end')
            if '--describe' not in hf:
                hf += ['--describe', 'false']
            if '-o' not in hf and '--output' not in hf:
                hf += ['-o', 'work/snap']
        if hf[0] == 'render':
            try:
                with open(index, encoding='utf-8') as fh:
                    page = fh.read()
            except OSError:
                sys.exit('index.html is missing: run build.py first.')
            if fxlib.SAFE_MARK in page:
                sys.exit('NOT RENDERED: the red safe-zone guide is still in index.html. Run build.py again WITHOUT SAFE=1 '
                         '(with the same other switches), then render.')
            if '-o' not in hf and '--output' not in hf:
                hf += ['-o', f'renders/{name}.mp4']
            if '--quality' not in hf:
                hf += ['--quality', 'high']
        code = skillenv.run_hyperframes(hf, cwd=slot)
        if hf[0] == 'render' and code == 0:
            out = os.path.join(slot, hf[hf.index('-o') + 1]) if '-o' in hf else None
            if out and os.path.isfile(out):
                got, want = fxlib.probe_frames(out), int(clip.get('frames') or 0)
                size = fxlib.probe_size(out)
                ok = got == want and size == (1080, 1920)
                print(f'render: {out}  {got} frames (slot has {want})  {size[0]}x{size[1]}  ' + ('OK' if ok else
                      '!! NOT A CLEAN SLOT: the frame count and 1080x1920 must match exactly, fix it before fx_add.py'))
                if not ok:
                    code = 3
        sys.exit(code)

    buyer = (fxlib.read(os.path.join(slot, 'slot.json'), {}) or {}).get('buyer_folder')
    if buyer:      # an effect that shows the buyer's own material does not run on nothing, and never on stand-ins
        bdir = os.path.join(slot, buyer['name'])
        have = len([f for f in os.listdir(bdir) if not f.startswith('.')]) if os.path.isdir(bdir) else 0
        if have < (1 if buyer.get('min') is None else int(buyer['min'])):      # min 0 = an optional folder
            label = fxlib.index().get(clip.get('key'), {}).get('name', name)
            plain = re.sub(r'\s*\([^)]*\)\s*$', '', buyer['what']).replace("the buyer's", 'your')
            sys.exit(f'SKIP  {label}: it needs {buyer["what"]}, at least {buyer.get("min", 1)}, in "{skillenv.shell_path(bdir)}" '
                     f'and there are {have}. Ask the buyer for them, or leave the effect out.\n'
                     f'      tell the buyer: "I left {label} out of this one: it needs {plain} and I do not have them yet."')
    script = os.path.join(slot, args[0])
    if not os.path.isfile(script):
        have = sorted(f for f in os.listdir(slot) if f.endswith('.py'))
        sys.exit(f'{args[0]} is not in this slot. Scripts here: ' + ', '.join(have))
    env = skillenv.hyperframes_env(skillenv.load().get('node'), skillenv.tool('ffmpeg') if os.path.isabs(skillenv.tool('ffmpeg')) else None)
    env.update({'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'})
    sfx = os.path.join(slot, 'assets', 'sfx')
    if 'SFX' not in switches and not (os.path.isdir(sfx) and any(f.lower().endswith('.mp3') for f in os.listdir(sfx))):
        switches['SFX'] = '0'
        print('note: no sound effects in this slot, running with SFX=0')
    env.update(switches)
    shown = ' '.join(f'{k}={v}' for k, v in switches.items())
    print(f'[{name}] {" ".join(args)}' + (f'   ({shown})' if shown else ''), flush=True)
    sys.exit(subprocess.run([sys.executable, script] + args[1:], cwd=slot, env=env).returncode)


if __name__ == '__main__':
    main()
