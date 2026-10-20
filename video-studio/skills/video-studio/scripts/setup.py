#!/usr/bin/env python3
"""video-studio (Creator Studio) setup check, for macOS, Linux (and WSL) and Windows. Safe to re-run: it only
reports and fills in what is missing. Standard library only, because it runs before the skill's own Python
environment exists.

Run it with whichever Python the machine has:   python3 setup.py   |   python setup.py   |   py -3 setup.py
Optional:   --state <dir>   keep the skill's working files in that folder (default: decided by skillenv.resolve_state)
            --matting       also get the clean-cutout model (RobustVideoMatting, about 105 MB) and scipy. Almost every effect
                            needs it, and so do the looks that put things behind the speaker or pop them out of a card.
            --fx <effect key> [<key> ...]   also add the extra Python packages those effects need (the "Extra packages"
                            column in effects/INDEX.md; `--fx all` for every effect). Only needed when
                            footage_check.py prints "first: extra packages" for an effect the buyer picked.

  0. The state folder: the one place this skill writes (.venv, .platform.json, config.json, studio-picks.json,
     sound effects, the matting model). Always a per-user data folder outside the skill folder.
  1. ffmpeg + ffprobe: the ones on PATH, else the ones in the usual install folders (used by their full path), else
     the skill gets its own copy into its Python environment (static-ffmpeg, pinned; 42 to 142 MB by system)
  2. Node 22+ (HyperFrames renders with it; an nvm / Homebrew / installer copy is picked up even when an older
     Node is the default; with none the skill gets its own copy into the state folder, pinned and checksum-checked)
  3. Python 3.10 to 3.13 and a venv in the state folder with faster-whisper + Pillow (transcription, head tracking).
     A computer with no Python at all starts through start.sh / start.ps1, which fetch the skill its own Python
     first and then run this script with it.
  4. Sound effects (not bundled: the Pixabay license forbids redistributing the files)
  5. The picks file (what the buyer chose in the Studio Picker): found, or not saved yet

Prints a STATUS line per item, each with the fix for THIS machine, then READY or NOT READY. Exit code 0 only when
everything is ready. Writes <state>/.platform.json (os, arch, the venv Python, how to start npx) so the other
scripts and SKILL.md read the right commands instead of detecting again. Nothing is sent anywhere.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

sys.dont_write_bytecode = True   # no __pycache__ next to the scripts: a plugin's folder is not ours to write in
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

SFX_NAMES = ['whoosh-short', 'pop', 'sparkle', 'click', 'click-soft', 'impact-bass-1',
             'whoosh', 'whoosh-cinematic', 'impact-bass-2', 'riser', 'chime', 'notification', 'ping',
             'key-press', 'typing', 'error', 'glitch-1', 'glitch-2', 'glitch-3']
SFX_URL = 'https://raw.githubusercontent.com/heygen-com/hyperframes/main/skills/media-use/audio/assets/sfx'
RESTART = 'then quit Claude Code completely, reopen it and run the skill again'


def fix(what, osn):
    """How to install `what` on this OS, in steps a person who has never used a terminal can follow. Every command
    here was checked against its own source (formulae.brew.sh, the winget-pkgs manifests, nodejs.org, python.org)."""
    brew = ('if you have Homebrew, paste this into the Terminal app: {cmd} . No Homebrew: step 1, open https://brew.sh '
            'and paste the one line at the top of that page into the Terminal app (it installs Homebrew). '
            'Step 2, paste: {cmd} . Then run the skill again')
    table = {
        'ffmpeg': {'macos': brew.format(cmd='brew install ffmpeg'),
                   'linux': 'sudo apt install ffmpeg',
                   'windows': 'step 1, open PowerShell from the Start menu and paste: winget install --id Gyan.FFmpeg -e . '
                              f'Step 2, {RESTART}'},
        'node': {'macos': 'step 1, download the macOS installer from https://nodejs.org (the LTS button) and run it. '
                          'Step 2, run the skill again. (With Homebrew instead: brew install node)',
                 'linux': 'install Node 22 LTS from https://nodejs.org (or: nvm install 22). apt\'s own nodejs is often too old',
                 'windows': 'step 1, open PowerShell from the Start menu and paste: winget install --id OpenJS.NodeJS.LTS -e . '
                            f'Step 2, {RESTART}'},
        'python': {'macos': f'step 1, download Python 3.12 from {skillenv.OWN_PY_MAC_PKG} and open it to install. '
                            'Step 2, run the skill again. (With Homebrew instead: brew install python@3.12)',
                   'linux': 'sudo apt install python3 python3-venv',
                   'windows': f'winget install --id Python.Python.3.12 -e   ({RESTART})'},
        'venv': {'macos': 'brew install python@3.12',
                 'linux': 'sudo apt install python3-venv',
                 'windows': f'winget install --id Python.Python.3.12 -e   ({RESTART})'},
    }
    return table[what][osn]


def say(line):
    print(line, flush=True)


# ------------------------------------------------------------------ 1. ffmpeg
def ffmpeg_facts(ff):
    """-> (version text, [encoders this build lacks]). The reel is H.264, the cutout is VP9 with alpha."""
    try:
        ver = subprocess.run([ff, '-version'], **skillenv.TEXT, timeout=30).stdout.split()[2]
        enc = subprocess.run([ff, '-hide_banner', '-encoders'], **skillenv.TEXT, timeout=30).stdout
    except (OSError, IndexError, subprocess.SubprocessError):
        ver, enc = 'version unknown', 'libx264 libvpx-vp9'
    return ver, [e for e in ('libx264', 'libvpx-vp9') if e not in enc]


def check_ffmpeg(osn):
    """-> (ok, ffmpeg, ffprobe). ok is None when no usable ffmpeg is on this computer: main() then gives the skill
    its own copy (own_ffmpeg) once the Python environment is there.
    An ffmpeg that is installed but not on this session's PATH is used by its full path, the same way Node is: every
    script of the skill reads the path from .platform.json and HyperFrames gets that folder put first on its PATH."""
    found = {n: skillenv.find_tool(n, osn) for n in ('ffmpeg', 'ffprobe')}
    if all(p for p, _ in found.values()):
        ff = found['ffmpeg'][0]
        ver, lacking = ffmpeg_facts(ff)
        if lacking:   # a cut-down build
            say(f"STATUS ffmpeg: the one at {ff} ({ver}) has no {' / '.join(lacking)}, so the skill gets its own copy")
            return None, None, None
        on_path = all(on for _, on in found.values())
        say(f'STATUS ffmpeg OK ({ver})' if on_path else f'STATUS ffmpeg OK ({ver}, using {ff})')
        return True, ff, found['ffprobe'][0]
    return None, None, None


# The skill's own ffmpeg + ffprobe, only when the computer has none. static-ffmpeg is a small pip package that
# keeps one ready-made build for this system in the skill's Python environment (inside the state folder): about
# 42 MB on an Apple Silicon Mac, 53 MB on an Intel Mac, 72 MB on Windows, 142 MB on Linux. Pinned, and installed
# without its dependency list because that list names a publishing tool the download does not use.
# The package says where its build comes from and where it goes, and hands back the two paths. The download itself
# is done here with fetch(): the package's own download waits ten minutes on a connection that has stopped and
# never tries again (2026-10-11: one sat at 26 MB until setup gave up on ffmpeg after 15 silent minutes).
OWN_FFMPEG = ['static-ffmpeg==3.0']
OWN_FFMPEG_NEEDS = ['requests>=2,<3', 'filelock>=3', 'progress==1.6.1']
OWN_FFMPEG_WHERE = ('from static_ffmpeg import run\n'
                    'print("URL=" + run.get_platform_http_zip())\nprint("DIR=" + run.get_platform_dir())\n')
OWN_FFMPEG_FETCH = ('from static_ffmpeg import run\n'
                    'ff, fp = run.get_or_fetch_platform_executables_else_raise()\n'
                    'print("FFMPEG=" + ff)\nprint("FFPROBE=" + fp)\n')
OWN_FFMPEG_SIZE = {'macos': 'about 45 MB on an Apple Silicon Mac, 55 MB on an Intel Mac', 'windows': 'about 75 MB',
                   'linux': 'about 145 MB'}


def own_ffmpeg(py, osn):
    """-> (ok, ffmpeg, ffprobe): the skill's own copy, fetched once. Falls back to the install steps when it cannot
    be fetched (offline, a download that stops three times in a row, a system the package has no build for)."""
    def ask(code):
        """Run a few lines with the skill's Python -> {KEY: value} from the KEY=value lines they print."""
        try:
            r = subprocess.run([py, '-c', code], **skillenv.TEXT, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return {}
        if r.returncode != 0:
            return {}
        return dict(l.split('=', 1) for l in (r.stdout or '').splitlines()
                    if l.startswith(('URL=', 'DIR=', 'FFMPEG=', 'FFPROBE=')))

    def there(folder):
        """The build is unpacked in the package's folder: its own "all here" mark, and the program itself."""
        return bool(folder) and os.path.isfile(os.path.join(folder, 'installed.crumb')) and any(
            os.path.isfile(os.path.join(folder, n)) for n in ('ffmpeg', 'ffmpeg.exe'))

    def get(url, folder):
        """Download the build and unpack it the way the package does: the zip holds one folder named after the
        system, and the mark is written last so a run that was cut off starts over."""
        if not url or not folder:
            return False
        archive = folder + '.zip'
        try:
            os.makedirs(os.path.dirname(folder), exist_ok=True)
            if not fetch(url, archive, tries=3, what='ffmpeg'):
                return False
            shutil.rmtree(folder, ignore_errors=True)   # our own leftovers from a run that was cut off
            unpack(archive, os.path.dirname(folder))
            if any(os.path.isfile(os.path.join(folder, n)) for n in ('ffmpeg', 'ffmpeg.exe')):
                with open(os.path.join(folder, 'installed.crumb'), 'w', encoding='utf-8') as f:
                    f.write(f'installed from {url} by setup.py on {datetime.datetime.now()}')
        except (OSError, zipfile.BadZipFile):
            return False
        finally:
            if os.path.isfile(archive):
                os.remove(archive)   # our own download, nothing of the user's
        return there(folder)

    if not py:
        say(f"STATUS ffmpeg MISSING -> {fix('ffmpeg', osn)}")
        return False, None, None
    where = ask(OWN_FFMPEG_WHERE)           # {} until the package is in the skill's Python
    ready = there(where.get('DIR'))
    if not ready:
        say(f'STATUS ffmpeg: none found on this computer, getting the skill its own copy ({OWN_FFMPEG_SIZE[osn]}, one time)')
        if not where:
            subprocess.run([py, '-m', 'pip', 'install', '-q', '--no-deps'] + OWN_FFMPEG, **skillenv.TEXT)
            subprocess.run([py, '-m', 'pip', 'install', '-q'] + OWN_FFMPEG_NEEDS, **skillenv.TEXT)
            where = ask(OWN_FFMPEG_WHERE)
        ready = get(where.get('URL'), where.get('DIR'))
    if ready:                               # the package finds its mark, so it only hands back the paths
        got = ask(OWN_FFMPEG_FETCH)
        ff, fp = got.get('FFMPEG'), got.get('FFPROBE')
        if ff and fp and os.path.isfile(ff) and os.path.isfile(fp):
            ver, lacking = ffmpeg_facts(ff)
            if not lacking:
                say(f"STATUS ffmpeg OK ({ver}, the skill's own copy)")
                return True, ff, fp
    say(f"STATUS ffmpeg MISSING (the skill could not get its own copy: no internet, or no build for this system) -> {fix('ffmpeg', osn)}")
    return False, None, None


# ------------------------------------------------------------------ 2. node
OWN_NODE_SIZE = {'macos': 'about 50 MB', 'linux': 'about 55 MB', 'windows': 'about 36 MB'}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def unpack(archive, into):
    """Unpack a .tar.gz or .zip that has already passed its SHA-256 check."""
    if archive.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            z.extractall(into)
        return
    with tarfile.open(archive) as t:
        if hasattr(tarfile, 'data_filter'):
            t.extractall(into, filter='data')
        else:                                   # a Python from before the filters existed (3.9.6 on many Macs)
            t.extractall(into)


def own_node(osn, state, arch):
    """-> (node, version, npx) of the skill's own Node, fetched once into the state folder, or (None, '', None)
    when it cannot be fetched (offline, a system nodejs.org has no build for, a download that fails its check)."""
    build = skillenv.own_node_build(osn, arch)
    if not build:
        return None, '', None
    name = f'node-{skillenv.OWN_NODE}-{build}'
    root = skillenv.node_dir(state)
    folder = os.path.join(root, name[:-len('.zip' if build.endswith('.zip') else '.tar.gz')])
    archive, tmp = os.path.join(root, name), os.path.join(root, '.unpack')
    os.makedirs(root, exist_ok=True)
    try:
        if not fetch(f'https://nodejs.org/dist/{skillenv.OWN_NODE}/{name}', archive, tries=3, what='node'):
            return None, '', None
        if sha256_of(archive) != skillenv.OWN_NODE_SHA256[build]:
            say('STATUS node: the download did not pass its check, so it was not used')
            return None, '', None
        for d in (tmp, folder):                 # our own leftovers from a run that was cut off, nothing of the user's
            shutil.rmtree(d, ignore_errors=True)
        unpack(archive, tmp)
        os.replace(os.path.join(tmp, os.path.basename(folder)), folder)
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        return None, '', None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.isfile(archive):
            os.remove(archive)
    node = skillenv.own_node(state, osn)
    ver = skillenv._node_version(node) if node else ''
    npx = skillenv.npx_command(node, osn) if node else None
    if skillenv.node_major(ver) >= skillenv.MIN_NODE and npx:
        return node, ver, npx
    return None, '', None


def check_node(osn, state, arch):
    """-> (ok, node, version, npx). A Node 22+ already on the computer is used as it is. With none (or only an
    older one) the skill gets its own copy; the install steps are only printed when that cannot be fetched."""
    node, ver, on_path = skillenv.find_node(osn, state=state)
    if node and skillenv.node_major(ver) >= skillenv.MIN_NODE:
        npx = skillenv.npx_command(node, osn)
        if npx:
            if node == skillenv.own_node(state, osn):
                say(f"STATUS node OK ({ver}, the skill's own copy)")
            else:
                say(f'STATUS node OK ({ver})' if on_path else f'STATUS node OK ({ver}, using {node})')
            return True, node, ver, npx
    have = f'found {ver}, need {skillenv.MIN_NODE}+' if ver else 'none found on this computer'
    if node and skillenv.node_major(ver) >= skillenv.MIN_NODE:
        have = f'found {ver} but npx is missing next to it'
    say(f'STATUS node: {have}, getting the skill its own copy ({OWN_NODE_SIZE[osn]}, one time)')
    own, own_ver, npx = own_node(osn, state, arch)
    if own:
        say(f"STATUS node OK ({own_ver}, the skill's own copy)")
        return True, own, own_ver, npx
    say(f"STATUS node MISSING or < {skillenv.MIN_NODE} (the skill could not get its own copy: no internet, or no "
        f"build for this system) -> {fix('node', osn)}")
    return False, None, ver, None


# ------------------------------------------------------------------ 3. python + venv
def base_python():
    """The interpreter to build the venv with: this one when it is 3.10 to NEWEST_PY, otherwise one of those on PATH,
    otherwise this one anyway when it is 3.9 (the old setup.sh used whatever `python3` was, and 3.9 still works).
    A Python newer than NEWEST_PY is never used: the transcription engine has no build for it."""
    here = sys.version_info[:2]
    if skillenv.MIN_PY <= here <= skillenv.NEWEST_PY:
        return sys.executable, here
    for minor in range(skillenv.NEWEST_PY[1], skillenv.MIN_PY[1] - 1, -1):
        p = shutil.which(f'python3.{minor}')
        if p:
            return p, (3, minor)
    if skillenv.OLDEST_PY <= here < skillenv.MIN_PY:
        return sys.executable, here
    return None, here


def venv_version(venv):
    """(major, minor) the venv was built with, read from its pyvenv.cfg, or None."""
    try:
        with open(os.path.join(venv, 'pyvenv.cfg'), encoding='utf-8') as f:
            for line in f:
                key, _, value = line.partition('=')
                if key.strip() in ('version', 'version_info'):
                    major, minor = value.strip().split('.')[:2]
                    return int(major), int(minor)
    except (OSError, ValueError):
        pass
    return None


def starter_command(osn):
    """How to run the setup through start.sh / start.ps1, which get the Studio its own Python 3.12."""
    if osn == 'windows':
        return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{os.path.join(skillenv.SKILL_DIR, "scripts", "start.ps1")}"'
    return f'sh "{os.path.join(skillenv.SKILL_DIR, "scripts", "start.sh")}"'


# Versions are pinned so a new upstream release cannot break installs (same pins as the setup.sh hotfix). PyAV 19
# (2026-09-29) removed the `metadata_errors` argument that faster-whisper 1.2.1 still passes, so every transcription
# crashed on fresh installs. A venv that already has PyAV 19 fails the self-test below and is repaired in place.
REQUIREMENTS = ['faster-whisper==1.2.1', 'av>=11,<19', 'pillow']
# imports alone did not catch the PyAV break: decode a tenth of a second of silence the way a transcription does
VENV_SELFTEST = r'''
import os, tempfile, wave
import PIL
from faster_whisper.audio import decode_audio
d = tempfile.mkdtemp(); p = os.path.join(d, 't.wav')
w = wave.open(p, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0' * 1600); w.close()
try:
    decode_audio(p)
finally:
    os.remove(p); os.rmdir(d)
'''


def venv_ok(py):
    if not py or not os.path.isfile(py):
        return False
    try:
        return subprocess.run([py, '-c', VENV_SELFTEST], capture_output=True, timeout=300).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def tail(text, n=12):
    return '\n'.join('        ' + l for l in (text or '').strip().splitlines()[-n:])


def check_python(info, state):
    osn = info['os']
    py = skillenv.find_venv_python(state, osn)
    if venv_ok(py):
        say('STATUS python venv OK')
        return True, py
    base, ver = base_python()
    if not base and ver > skillenv.NEWEST_PY:
        newest = '.'.join(map(str, skillenv.NEWEST_PY))
        say(f'STATUS python TOO NEW (this is {ver[0]}.{ver[1]}, the transcription engine has no build past {newest} '
            f'yet) -> run the setup through the starter instead, it gets the Studio its own Python 3.12: '
            f'{starter_command(osn)}')
        return False, None
    if not base:
        say(f"STATUS python MISSING or too old (this is {ver[0]}.{ver[1]}, need 3.10+) -> {fix('python', osn)}")
        return False, None
    if osn == 'windows' and info['python_arch'] == 'arm64':
        say('STATUS python venv CANNOT BE BUILT with this ARM64 Python (the transcription engine has no Windows ARM '
            f'build) -> install the x64 Python: winget install --id Python.Python.3.12 -e --architecture x64   ({RESTART})')
        return False, None
    venv = os.path.join(state, '.venv')
    built_with = venv_version(venv) if py else None
    if py and not (built_with and skillenv.OLDEST_PY <= built_with <= skillenv.NEWEST_PY):
        py = None   # broken and made with a Python the packages do not install on: repairing it would fail every time
    if py:   # the venv is there but its packages are missing or broken: repair it in place
        say(f'STATUS python venv: repairing {venv} (faster-whisper + Pillow, ~1 min)')
    else:
        rebuild = os.path.isdir(venv)
        say(f"STATUS python venv: {'rebuilding' if rebuild else 'creating'} {venv} with Python {ver[0]}.{ver[1]} "
            '(faster-whisper + Pillow, ~1 min)')
        # --clear empties a broken old venv first, so nothing from the old Python is left behind
        r = subprocess.run([base, '-m', 'venv'] + (['--clear'] if rebuild else []) + [venv], **skillenv.TEXT)
        py = skillenv.find_venv_python(state, osn)
        if r.returncode != 0 or not py:
            say(f"STATUS python venv FAILED (could not create it) -> {fix('venv', osn)}")
            say(tail(r.stdout + r.stderr))
            return False, None
    # `python -m pip`, not the pip script: on Windows pip.exe cannot replace itself while it is running
    subprocess.run([py, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'], **skillenv.TEXT)
    r = subprocess.run([py, '-m', 'pip', 'install', '-q'] + REQUIREMENTS, **skillenv.TEXT)
    if r.returncode == 0 and venv_ok(py):
        say('STATUS python venv OK')
        return True, py
    say('STATUS python venv FAILED (pip output below). If it says no matching version / failed building a wheel, this '
        f"Python ({ver[0]}.{ver[1]}) is too new or too old for the packages -> {fix('python', osn)}")
    say(tail(r.stdout + r.stderr))
    return False, py


# ------------------------------------------------------------------ 4. sound effects
STALL = 45   # seconds with nothing arriving before a download counts as stuck (a connection can hang with no error)


def download(url, tmp):
    """One try at url -> tmp. True only when the whole file arrived."""
    got = 0
    try:
        with urllib.request.urlopen(url, timeout=STALL) as r, open(tmp, 'wb') as f:
            size = r.headers.get('Content-Length') or ''
            for block in iter(lambda: r.read(1 << 16), b''):
                f.write(block)
                got += len(block)
        return got > 0 and (not size.isdigit() or got == int(size))   # a connection closed early is not the file
    except Exception:   # no certificates in a python.org macOS install, offline, proxy, a stuck connection
        if got:
            return False                    # it was arriving and then stopped: curl would do no better
    curl = shutil.which('curl')             # nothing arrived at all: try the system curl
    if not curl:
        return False
    try:
        r = subprocess.run([curl, '-fsSL', '--connect-timeout', '20', '--speed-limit', '1024',
                            '--speed-time', str(STALL), url, '-o', tmp], capture_output=True)
    except OSError:
        return False
    return r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0


def fetch(url, dest, tries=1, what=None):
    """Download url to dest. A try that stops arriving for STALL seconds is given up, and with tries > 1 the
    download is started again, with a STATUS line under the name `what` so nobody is staring at silence."""
    tmp = dest + '.part'
    for attempt in range(1, tries + 1):
        if attempt > 1:
            if what:
                say(f'STATUS {what}: the download did not finish, trying again (attempt {attempt} of {tries})')
            time.sleep(3)
        if download(url, tmp):
            os.replace(tmp, dest)
            return True
    if os.path.isfile(tmp):
        os.remove(tmp)   # our own partial download, nothing of the user's
    return False


def check_sfx(sfx):
    os.makedirs(sfx, exist_ok=True)

    def have(n):
        p = os.path.join(sfx, n + '.mp3')
        return os.path.isfile(p) and os.path.getsize(p) > 0

    home = os.path.expanduser('~')
    for lib in (os.path.join(home, '.claude', 'skills', 'media-use', 'audio', 'assets', 'sfx'),
                os.path.join(home, '.agents', 'skills', 'media-use', 'audio', 'assets', 'sfx')):
        for n in SFX_NAMES:
            src = os.path.join(lib, n + '.mp3')
            if not have(n) and os.path.isfile(src):
                shutil.copyfile(src, os.path.join(sfx, n + '.mp3'))
    # not found locally: fetch them from the HyperFrames repo, which publishes this Pixabay-licensed pack
    for n in SFX_NAMES:
        if not have(n):
            fetch(f'{SFX_URL}/{n}.mp3', os.path.join(sfx, n + '.mp3'))
    missing = [n for n in SFX_NAMES if not have(n)]
    if not missing:
        say('STATUS sound effects OK')
    else:
        say(f"STATUS sound effects MISSING: {' '.join(missing)} -> optional. You can get similar sound effects at https://pixabay.com/sound-effects/")
        say(f'        and save them as {os.path.join(sfx, "<name>.mp3")}, then re-run this script.')
    return not missing


# ------------------------------------------------------------------ 4b. clean-cutout model (only with --matting)
RVM_MODEL = 'rvm_resnet50_fp32.onnx'
RVM_URL = 'https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/' + RVM_MODEL


def matting_ready(py, state):
    """-> (model path or None, scipy importable)."""
    model = os.path.join(skillenv.models_dir(state), RVM_MODEL)
    have_model = os.path.isfile(model) and os.path.getsize(model) > 50_000_000
    try:
        ok = bool(py) and subprocess.run([py, '-c', 'import scipy.ndimage, onnxruntime, numpy'],
                                         capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return (model if have_model else None), ok


def check_matting(py, state, install):
    model, libs = matting_ready(py, state)
    if install and py:
        if not libs:
            say('STATUS clean cutout: adding scipy to the Python environment')
            subprocess.run([py, '-m', 'pip', 'install', '-q', 'scipy'], **skillenv.TEXT)
        if not model:
            os.makedirs(skillenv.models_dir(state), exist_ok=True)
            say('STATUS clean cutout: downloading the matting model (about 105 MB, one time)')
            fetch(RVM_URL, os.path.join(skillenv.models_dir(state), RVM_MODEL), tries=3, what='clean cutout')
        model, libs = matting_ready(py, state)
    if model and libs:
        say('STATUS clean cutout OK')
    else:
        say('STATUS clean cutout NOT SET UP -> fine for captions on their own. Almost every effect needs it, and so do the looks '
            'that go behind the speaker (Bold captions, Chalk Talk, Show and Tell). One time, about 105 MB: setup.py --matting')
    return model if (model and libs) else None


# ------------------------------------------------------------------ 4c. extra packages for effects (only with --fx)
FX_MODULES = {'opencv-python-headless': 'cv2', 'mediapipe': 'mediapipe', 'scipy': 'scipy'}


def fx_keys(argv):
    """-> the effect keys after --fx (up to the next option), or None when --fx was not given."""
    if '--fx' not in argv:
        return None
    keys = []
    for a in argv[argv.index('--fx') + 1:]:
        if a.startswith('--'):
            break
        keys.append(a)
    return keys


def check_fx(py, keys):
    """Install what the named effects list under "extra" in effects/index.json, plus an effect's own
    requirements.txt when it has one, into the skill's own Python. Opt-in: nothing happens without --fx."""
    effects = os.path.join(skillenv.SKILL_DIR, 'effects')
    try:
        with open(os.path.join(effects, 'index.json'), encoding='utf-8') as fh:
            index = {e['key']: e for e in json.load(fh).get('effects', [])}
    except (OSError, ValueError):
        index = {}
    if not keys or 'all' in keys:
        keys = sorted(index)
    unknown = [k for k in keys if k not in index]
    if unknown:
        say(f"STATUS effect packages: unknown effect {' '.join(unknown)} (keys are listed in effects/INDEX.md)")
    wanted = []
    for k in keys:
        if k not in index:
            continue
        wanted += list(index[k].get('extra') or [])
        req = os.path.join(effects, k, 'requirements.txt')
        if os.path.isfile(req):
            with open(req, encoding='utf-8') as fh:
                wanted += [l.strip() for l in fh if l.strip() and not l.lstrip().startswith('#')]
    wanted = list(dict.fromkeys(wanted))
    if not wanted:
        say('STATUS effect packages OK (these effects need nothing extra)')
        return True
    if not py:
        say('STATUS effect packages SKIPPED (the Python environment is not ready yet)')
        return False

    def missing():
        out = []
        for p in wanted:
            mod = FX_MODULES.get(p)
            if not mod:
                out.append(p)       # a pinned requirement line: let pip decide
                continue
            try:
                if subprocess.run([py, '-c', f'import {mod}'], capture_output=True, timeout=120).returncode != 0:
                    out.append(p)
            except (OSError, subprocess.SubprocessError):
                out.append(p)
        return out

    need = missing()
    if need:
        say(f"STATUS effect packages: adding {' '.join(need)} (one time, can take a few minutes)")
        r = subprocess.run([py, '-m', 'pip', 'install', '-q'] + need, **skillenv.TEXT)
        if r.returncode != 0:
            say('STATUS effect packages FAILED (pip output below). The effects that need them are skipped until this works.')
            say(tail(r.stdout + r.stderr))
            return False
    say(f"STATUS effect packages OK ({' '.join(wanted)})")
    return True


# ------------------------------------------------------------------ 0. state folder
def state_arg(argv):
    """-> the value after --state (or --state=...), or None."""
    for i, a in enumerate(argv):
        if a == '--state':
            return argv[i + 1] if i + 1 < len(argv) else ''
        if a.startswith('--state='):
            return a.split('=', 1)[1]
    return None


def choose_state(argv):
    """-> (state folder, why). An empty or unsubstituted --state (a literal ${CLAUDE_PLUGIN_DATA}) is ignored."""
    given = state_arg(argv)
    if given is not None and not skillenv.set_state(given):
        say('STATUS state: ignoring --state (empty or an unfilled placeholder), using the default folder')
    env = os.environ.get('CLAUDE_PLUGIN_DATA')
    if env and not skillenv._explicit_state and not skillenv.own_plugin_data(env):
        # set, but not this skill's own data folder (another plugin exported it, or it was never filled in)
        say(f'STATUS state: ignoring CLAUDE_PLUGIN_DATA ({env}): its last folder name has to be "{skillenv.APP}" or start '
            f'with "{skillenv.APP}-" to count as this skill\'s folder. Using the default folder (or pass --state <folder>)')
    state, why = skillenv.resolve_state(skillenv._explicit_state,
                                        venv_state=None if skillenv._explicit_state else skillenv._venv_state())
    os.makedirs(state, exist_ok=True)
    if not skillenv._explicit_state and state != skillenv.SKILL_DIR:
        state = os.path.realpath(state)   # Microsoft Store Python quietly redirects AppData: record the real folder
    return state, why


# ------------------------------------------------------------------ main
def main():
    skillenv.utf8_stdio()
    info = skillenv.detect()
    osn = info['os']
    provider = skillenv.cutout_provider(info)
    how = 'Apple GPU / Neural Engine' if provider == 'CoreML' else 'no GPU acceleration, speed depends on the processor'
    say(f'STATUS system {skillenv.os_label(info)} | background cutout runs on {provider} ({how})')
    state, why = choose_state(sys.argv[1:])
    sfx = skillenv.sfx_dir(state)
    config = skillenv.config_file(state)
    say(f'STATUS state {state} ({why})')
    # A newer version of the Studio? Asked once a day and printed first, because the buyer is asked about it before
    # anything else. Never in the way: offline or anything odd says nothing.
    try:
        import update
        line = update.check(state)
        if line and 'AVAILABLE' in line:
            say(line)
    except (ImportError, OSError, ValueError):
        pass
    # a config.json that only holds the default style (written by my_styles.py before the setup questions) is not done
    asked = (skillenv._read_json(config, {}) or {}).get('clipsDir')
    say(f'STATUS config FOUND {config}' if asked else
        f'STATUS config MISSING -> first run: ask the two setup questions, then save {config} (keep any keys in it)')

    ff_ok, ffmpeg, ffprobe = check_ffmpeg(osn)
    node_ok, node, node_ver, npx = check_node(osn, state, info['arch'])
    py_ok, py = check_python(info, state)
    if ff_ok is None:                       # no usable ffmpeg on this computer: the skill gets its own copy
        ff_ok, ffmpeg, ffprobe = own_ffmpeg(py if py_ok else None, osn)
    sfx_ok = check_sfx(sfx)
    rvm_model = check_matting(py if py_ok else None, state, '--matting' in sys.argv[1:])
    if fx_keys(sys.argv[1:]) is not None:
        check_fx(py if py_ok else None, fx_keys(sys.argv[1:]))
    picks = skillenv.picks_file(state)
    say(f'STATUS picks FOUND {picks}' if os.path.isfile(picks) else
        'STATUS picks MISSING (fine when they have a saved style)')
    have = skillenv.saved_styles(state)
    if have:
        say('STATUS styles ' + ', '.join(s['name'] + (' (default)' if s['default'] else '') for s in have))
    else:
        say('STATUS styles NONE -> first run: build their first style (SKILL.md, "First run only")'
            if not os.path.isfile(picks) else 'STATUS styles NONE (the Picker picks are used)')
    ready = ff_ok and node_ok and py_ok

    sp = skillenv.shell_path
    record = {
        'schema': skillenv.SCHEMA,
        'ready': ready,
        'checked': datetime.date.today().isoformat(),
        'os': osn, 'wsl': info['wsl'], 'arch': info['arch'], 'python_arch': info['python_arch'],
        'skill_dir': sp(skillenv.SKILL_DIR),
        'state_dir': sp(state),                                    # ST in SKILL.md: everything the skill writes
        'config': sp(config),
        'picks': sp(picks),                                        # the Studio Picker saves here
        'sfx_dir': sp(sfx),
        'rvm_model': sp(rvm_model),                                # None until setup.py --matting has run
        'python': sp(py) if py_ok else None,                       # PY in SKILL.md
        'hf': [sp(py), sp(os.path.join(skillenv.SKILL_DIR, 'scripts', 'hf.py'))] if py_ok else None,   # HF in SKILL.md
        'ffmpeg': sp(ffmpeg), 'ffprobe': sp(ffprobe),
        'node': sp(node) if node_ok else None, 'node_version': node_ver or None,
        'npx': [sp(p) for p in npx] if npx else None,
        'hyperframes': skillenv.HYPERFRAMES,
        'cutout': provider,
        'sfx': sfx_ok,
    }
    with open(skillenv.platform_file(state), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=1)
        f.write('\n')
    say('READY' if ready else 'NOT READY')
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
