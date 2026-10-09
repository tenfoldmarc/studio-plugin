#!/usr/bin/env python3
"""HyperFrames launcher: one command that works the same in zsh, bash, Git Bash and PowerShell.

Usage:   PY hf.py "<project folder>" <hyperframes arguments>
  PY hf.py "<project>" lint
  PY hf.py "<project>" snapshot --at 1.2,3.4,5.6 --no-end --describe false
  PY hf.py "<project>" render -o renders/<slug>-v1.mp4 --quality high

The project folder comes first (a full path) and the command runs inside it, so there is no `cd` and the paths
after it ("renders/...") are the project's own. `--project "<folder>"` anywhere does the same. Without a folder it
runs where the shell stands, as before.

Runs `npx --yes hyperframes@0.8.34 <arguments>` (the pinned version) with the Node 22+ that setup.py found first
on PATH, so there is no `nvm use`, and without a shell, so Windows' npx.cmd is not a problem. Standard library only.
The very first run downloads HyperFrames itself (one time, it can take a minute or two): say so once.
"""
import os
import sys

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts (a plugin's folder is not ours to write in)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder, args = skillenv.split_project_arg(sys.argv[1:])
    if folder is not None and not os.path.isdir(folder):
        sys.exit(f'project folder not found: {folder}')
    if not args:
        sys.exit(__doc__)
    sys.exit(skillenv.run_hyperframes(args, cwd=folder))
