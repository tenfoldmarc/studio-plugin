#!/usr/bin/env python3
"""Shared machine helpers for video-studio (macOS, Linux, WSL, Windows). Standard library only: setup.py imports
this before the venv exists. Nothing here talks to the network; detection is local.

What lives here:
  detect()            which OS / CPU this is
  venv_python()       where the skill's Python lives (.venv/bin on macOS / Linux, .venv\\Scripts on Windows)
  find_tool()         ffmpeg / ffprobe / node, on PATH or in the usual install folders
  npx_command()       how to start npx without a shell (on Windows `npx` is npx.cmd, so a bare name fails)
  run_hyperframes()   npx --yes hyperframes@<pinned> ... with the right Node first on PATH
  state_dir()         the one writable folder (.venv, .platform.json, config.json, studio-picks.json, sound effects,
                      matting model): always a per-user data folder OUTSIDE the skill, so an update of the skill
                      never wipes the buyer's picks
  load()              reads <state>/.platform.json, written by setup.py, so nothing is detected twice
  saved_styles(), find_style(), project_style(), effective_picks()   the buyer's named editing styles
  path_arg(), utf8_stdio(), concat_entry(), safe_name()   small things every script needs on Windows
"""
import glob
import json
import ntpath
import os
import platform
import posixpath
import re
import shutil
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = 'video-studio'
HYPERFRAMES = 'hyperframes@0.8.34'
MIN_NODE = 22
# The skill's own Node, only when the computer has no Node 22+: setup.py fetches this exact version from nodejs.org
# into <state>/node and checks the download against the SHA-256 nodejs.org publishes for it (SHASUMS256.txt of that
# version). Windows always gets the x64 build (it also runs on Windows on ARM, like the x64 Python the skill asks for).
OWN_NODE = 'v22.23.2'
OWN_NODE_SHA256 = {
    'darwin-arm64.tar.gz': '61130f394c1630d211dd50aecc4353d379480f36d3ac913cd85dbba1aed585c6',
    'darwin-x64.tar.gz': '58e99022c2ff89395576cc7fd4d98cea24bb68081475d5f88b801ee8729fb026',
    'linux-arm64.tar.gz': '013b59cfd2819703a6f4a14ab891fc46fc2a4e3f5bcd92de3fb4929b43e35b30',
    'linux-x64.tar.gz': 'b294a556e639d64338823920e5866c21c02741742d2e1529ee1a225c1ec9252a',
    'win-x64.zip': '1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97',
}
MIN_PY = (3, 10)      # what the README asks for
OLDEST_PY = (3, 9)    # what the pinned packages still install on (the system Python of many Macs); never refused
# The newest Python the pinned packages install on everywhere. Checked 2026-10-15 with pip dry runs per system:
# 3.14 has no onnxruntime for Intel Macs, 3.15 has no ctranslate2 for anything. A newer Python on the computer is
# skipped and the Studio uses its own pinned 3.12 (start.sh / start.ps1). Raise this only after the same check.
NEWEST_PY = (3, 13)
OWN_PY_MAC_PKG = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg'   # Apple Silicon + Intel
SCHEMA = 1
# subprocess.run(..., **TEXT): capture output as UTF-8 text. Plain text mode decodes with the Windows code page
# (cp1252) and crashes on ffmpeg printing a file name like "Angel" with an accented A.
TEXT = {'capture_output': True, 'encoding': 'utf-8', 'errors': 'replace'}


# ------------------------------------------------------------------ what machine is this
def os_name(system=None, release=None, environ=None):
    """-> ('macos' | 'linux' | 'windows', is_wsl). Arguments exist so tests can simulate other machines."""
    system = platform.system() if system is None else system
    release = platform.release() if release is None else release
    environ = os.environ if environ is None else environ
    s = system.lower()
    if s == 'darwin':
        return 'macos', False
    if s == 'windows' or s.startswith(('msys', 'mingw', 'cygwin')):
        return 'windows', False
    wsl = 'microsoft' in release.lower() or bool(environ.get('WSL_DISTRO_NAME') or environ.get('WSL_INTEROP'))
    return 'linux', wsl


def norm_arch(machine):
    m = (machine or '').lower()
    if m in ('arm64', 'aarch64', 'armv8', 'armv8l'):
        return 'arm64'
    if m in ('x86_64', 'amd64', 'x64'):
        return 'x64'
    if m in ('i386', 'i686', 'x86'):
        return 'x86'
    return m or 'unknown'


def machine_arch(osn, python_arch, environ=None, sysctl=None):
    """CPU of the machine, which can differ from the Python build (Rosetta, x64 Python on Windows ARM)."""
    environ = os.environ if environ is None else environ
    if osn == 'windows':
        ident = (environ.get('PROCESSOR_ARCHITEW6432') or '') + ' ' + (environ.get('PROCESSOR_IDENTIFIER') or '')
        if 'arm' in ident.lower():
            return 'arm64'
    if osn == 'macos' and python_arch != 'arm64':
        if sysctl is None:
            try:
                sysctl = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], **TEXT).stdout
            except OSError:
                sysctl = ''
        if sysctl.strip() == '1':
            return 'arm64'
    return python_arch


def detect():
    osn, wsl = os_name()
    py_arch = norm_arch(platform.machine())
    return {'os': osn, 'wsl': wsl, 'arch': machine_arch(osn, py_arch), 'python_arch': py_arch}


def os_label(info):
    name = {'macos': 'macOS', 'linux': 'Linux', 'windows': 'Windows'}[info['os']]
    if info.get('wsl'):
        name = 'Linux (WSL on Windows)'
    chip = {('macos', 'arm64'): ' (Apple Silicon)', ('macos', 'x64'): ' (Intel)'}.get((info['os'], info['arch']), '')
    return f"{name} {info['arch']}{chip}"


def cutout_provider(info):
    """What `hyperframes remove-background` runs on. HyperFrames 0.8.34 only uses CoreML on Apple Silicon; CUDA is
    opt-in (HYPERFRAMES_CUDA=1 plus a CUDA build of onnxruntime); everything else, Windows included, is CPU."""
    return 'CoreML' if (info['os'], info['arch']) == ('macos', 'arm64') else 'CPU'


# ------------------------------------------------------------------ paths
def _pm(osn):
    return ntpath if osn == 'windows' else posixpath


# ------------------------------------------------------------------ the state folder
# Everything the skill writes for itself lives in ONE folder: .venv, .platform.json, config.json, sound effects.
#   clone install (git clone into a skills folder): the skill folder itself, exactly as before
#   plugin install: the code sits in a versioned cache folder that Claude Code replaces on every update, so the
#                   state goes to a per-user data folder outside it and survives updates
_explicit_state = None


def set_state(path):
    """setup.py --state <dir>. Returns False (and changes nothing) for an empty or unsubstituted value."""
    global _explicit_state
    if not real_path_value(path):
        return False
    _explicit_state = os.path.abspath(os.path.expanduser(path))
    return True


def real_path_value(v, isabs=None):
    """True for a usable absolute path. False for nothing, and for a placeholder nobody filled in, such as a
    literal ${CLAUDE_PLUGIN_DATA} that reached the command line unsubstituted."""
    if not v or not str(v).strip() or re.search(r'\$\{|%\w+%|^\s*\$', v):
        return False
    isabs = isabs or (lambda p: os.path.isabs(os.path.expanduser(p)))
    return bool(isabs(v.strip()))


def own_plugin_data(v, isabs=None):
    """True only for THIS plugin's data folder: the last folder name is `video-studio` or starts with `video-studio-`
    (.../plugins/data/video-studio-<marketplace>). The variable can be present in a session with another plugin's
    folder in it (seen in practice: a different plugin's hook had exported it), and writing our files into someone
    else's data folder must never happen. setup.py prints a STATUS line when it is set but not ours."""
    if not real_path_value(v, isabs):
        return False
    name = [p for p in re.split(r'[\\/]+', v.strip()) if p][-1]
    return name == APP or name.startswith(APP + '-')


def in_plugin_cache(path):
    """Is this folder inside Claude Code's plugin cache (<config>/plugins/cache/<marketplace>/<plugin>/<version>)?"""
    parts = [p for p in re.split(r'[\\/]+', path) if p]
    return any(a == 'plugins' and b == 'cache' for a, b in zip(parts, parts[1:]))


def user_data_dir(osn=None, environ=None, home=None):
    """Per-user data folder for a plugin install, outside ~/.claude."""
    osn = osn or os_name()[0]
    environ = os.environ if environ is None else environ
    home = home or os.path.expanduser('~')
    pm = _pm(osn)
    if osn == 'macos':
        return pm.join(home, 'Library', 'Application Support', APP)
    if osn == 'windows':
        return pm.join(environ.get('LOCALAPPDATA') or pm.join(home, 'AppData', 'Local'), APP)
    xdg = environ.get('XDG_DATA_HOME') or ''
    return pm.join(xdg if xdg.startswith('/') else pm.join(home, '.local', 'share'), APP)


def _venv_state(prefix=None, base_prefix=None, isfile=os.path.isfile):
    """The folder holding the .venv this interpreter runs from, when that folder is a state folder. Scripts are
    started with the state's own Python, so they land on the state setup.py chose without being told."""
    prefix = sys.prefix if prefix is None else prefix
    base_prefix = getattr(sys, 'base_prefix', sys.prefix) if base_prefix is None else base_prefix
    if prefix == base_prefix or os.path.basename(prefix) != '.venv':
        return None
    parent = os.path.dirname(prefix)
    return parent if isfile(os.path.join(parent, '.platform.json')) else None


def resolve_state(explicit=None, environ=None, skill_dir=SKILL_DIR, osn=None, home=None, venv_state=None):
    """-> (state folder, why). The only place this is decided. Order:
      1. --state <dir> given to setup.py
      2. CLAUDE_PLUGIN_DATA, when it is set to a real path that is this plugin's own data folder
      3. the folder of the .venv this interpreter runs from (scripts started with the state's Python)
      4. the per-user data folder (macOS: ~/Library/Application Support/video-studio, Windows:
         %LOCALAPPDATA%/video-studio, Linux: ~/.local/share/video-studio). Never the skill folder: the skill is
         replaced on every update and the buyer's picks must survive that."""
    environ = os.environ if environ is None else environ
    if explicit:
        return explicit, '--state'
    env = environ.get('CLAUDE_PLUGIN_DATA')
    if own_plugin_data(env):
        return os.path.abspath(os.path.expanduser(env.strip())), 'CLAUDE_PLUGIN_DATA'
    if venv_state:
        return venv_state, 'this Python environment'
    return user_data_dir(osn, environ, home), 'your Creator Studio folder, kept outside the skill so updates do not erase it'


def state_dir():
    return resolve_state(_explicit_state, venv_state=None if _explicit_state else _venv_state())[0]


def platform_file(state=None):
    return os.path.join(state or state_dir(), '.platform.json')


def config_file(state=None):
    return os.path.join(state or state_dir(), 'config.json')


def picks_file(state=None):
    """What the buyer chose in the Studio Picker (caption style, effects, or one overall style)."""
    return os.path.join(state or state_dir(), 'studio-picks.json')


def my_style_file(state=None):
    """The buyer's own style as a spec the build reads (custom captions, always-on layers, grade, css). Written once
    from an example or a description (references/replicate.md); my-style.md beside it says the same in plain words."""
    return os.path.join(state or state_dir(), 'my-style.json')


def styles_dir(state=None):
    """The buyer's saved editing styles, one folder each: styles/<slug>/style.json (what the build reads) and
    style.md (the same in plain words, plus their standing notes). references/my-styles.md has the whole format."""
    return os.path.join(state or state_dir(), 'styles')


def style_slug(name):
    """'Cozy Talk!' -> 'cozy-talk'. The folder name of a saved style."""
    s = re.sub(r'[^a-z0-9]+', '-', str(name).strip().lower()).strip('-')
    return s or 'style'


def _read_json(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def migrate_my_style(state=None):
    """The one-style days: a my-style.json in the state folder becomes the saved style "My style" (and the default),
    once. The old file is renamed to my-style.json.migrated, never deleted."""
    state = state or state_dir()
    old = my_style_file(state)
    if not os.path.isfile(old):
        return None
    spec = _read_json(old, None)
    if not isinstance(spec, dict):
        return None
    name = str(spec.get('name') or 'My style')
    slug = style_slug(name)
    folder = os.path.join(styles_dir(state), slug)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
        spec['name'], spec['slug'] = name, slug
        with open(os.path.join(folder, 'style.json'), 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(spec, fh, indent=1)
            fh.write('\n')
        md = os.path.join(state, 'my-style.md')
        if os.path.isfile(md):
            shutil.copyfile(md, os.path.join(folder, 'style.md'))
    cfg_path = config_file(state)
    cfg = _read_json(cfg_path, {}) or {}
    if not cfg.get('defaultStyle'):
        cfg['defaultStyle'] = slug
        with open(cfg_path, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(cfg, fh, indent=1)
            fh.write('\n')
    os.replace(old, old + '.migrated')
    return slug


def saved_styles(state=None):
    """-> [{'slug', 'name', 'path', 'default'}] for every saved style, default first, then by name."""
    state = state or state_dir()
    migrate_my_style(state)
    root = styles_dir(state)
    default = (_read_json(config_file(state), {}) or {}).get('defaultStyle')
    out = []
    if os.path.isdir(root):
        for slug in sorted(os.listdir(root)):
            path = os.path.join(root, slug, 'style.json')
            if slug.startswith(('_', '.')) or not os.path.isfile(path):
                continue
            spec = _read_json(path, {}) or {}
            out.append({'slug': slug, 'name': str(spec.get('name') or slug), 'path': path, 'default': slug == default})
    out.sort(key=lambda s: (not s['default'], s['name'].lower()))
    return out


def find_style(name, state=None):
    """A saved style by what the buyer calls it: its folder name, its name in any case, or one unique partial
    match ("cozy" finds "Cozy Talk"). -> (style or None, [candidates when the name matched more than one])."""
    if not name:
        return None, []
    have = saved_styles(state)
    want, slug = str(name).strip().lower(), style_slug(name)
    for s in have:
        if s['slug'] == slug or s['name'].lower() == want:
            return s, []
    part = [s for s in have if want in s['name'].lower() or slug in s['slug']]
    return (part[0], []) if len(part) == 1 else (None, part)


def default_style(state=None):
    """The style "edit it" uses when the buyer names none (config.json "defaultStyle"), or None."""
    have = saved_styles(state)
    return next((s for s in have if s['default']), None)


def project_style(project, state=None):
    """The saved style a reel is built in: <project>/plan.json "myStyle" (a style's name, or "none" for the plain
    picks), else the default style. -> (style or None, why)."""
    plan = _read_json(os.path.join(project, 'plan.json'), {}) or {}
    asked = plan.get('myStyle')
    if asked == 'none':
        return None, 'plan.json says "myStyle": "none"'
    if asked:
        s, many = find_style(asked, state)
        if s:
            return s, f'plan.json "myStyle": "{asked}"'
        return None, (f'plan.json asks for the style "{asked}", which is not saved'
                      + (' (it could be: ' + ', '.join(m['name'] for m in many) + ')' if many else ''))
    s = default_style(state)
    return (s, 'the default style') if s else (None, 'no saved style')


def effective_picks(project=None, picks_path=None, state=None):
    """The picks that count for this reel: an explicit --picks file, else the "picks" a saved style carries (a
    style made from presets and effects), else what the Studio Picker saved. -> (picks dict, where from)."""
    if picks_path:
        return _read_json(picks_path, {}) or {}, picks_path
    if project:
        s, _ = project_style(project, state)
        if s:
            spec = _read_json(s['path'], {}) or {}
            if isinstance(spec.get('picks'), dict):
                return spec['picks'], f'the style "{s["name"]}"'
    path = picks_file(state)
    return _read_json(path, {}) or {}, path


def my_fonts_dir(state=None):
    """Font files fetched for the buyer's own style (get_font.py). build_reel.py copies them into every project."""
    return os.path.join(state or state_dir(), 'fonts')


def examples_dir(state=None):
    """Where study.py keeps what it pulled out of an example the buyer showed (frames, cut times, levels)."""
    return os.path.join(state or state_dir(), 'examples')


def sfx_dir(state=None, skill_dir=SKILL_DIR):
    """Where the downloaded sound effects live: always the state folder (they are never shipped in the skill)."""
    return os.path.join(state or state_dir(), 'sfx')


def models_dir(state=None):
    """Where the optional clean-cutout model is downloaded (setup.py --matting)."""
    return os.path.join(state or state_dir(), 'models')


def node_dir(state=None):
    """Where the skill's own Node lives, when setup.py had to fetch one."""
    return os.path.join(state or state_dir(), 'node')


def own_node_build(osn, arch):
    """-> the nodejs.org build for this system ('darwin-arm64.tar.gz'), or None when the skill has no pin for it."""
    if osn == 'windows':
        return 'win-x64.zip'
    system = {'macos': 'darwin', 'linux': 'linux'}.get(osn)
    name = f'{system}-{arch}.tar.gz'
    return name if name in OWN_NODE_SHA256 else None


def own_node(state=None, osn=None):
    """-> the node program of the skill's own copy, or None when there is none."""
    osn = osn or os_name()[0]
    for d in sorted(glob.glob(os.path.join(node_dir(state), 'node-v*')), reverse=True):
        cand = os.path.join(d, 'node.exe') if osn == 'windows' else os.path.join(d, 'bin', 'node')
        if os.path.isfile(cand):
            return cand
    return None


def venv_python(base, osn):
    pm = _pm(osn)
    if osn == 'windows':
        return pm.join(base, '.venv', 'Scripts', 'python.exe')
    return pm.join(base, '.venv', 'bin', 'python')


def find_venv_python(base=None, osn=None):
    """The venv interpreter that actually exists (a few Windows Pythons use bin/ instead of Scripts/)."""
    base = base or state_dir()
    osn = osn or os_name()[0]
    cands = [venv_python(base, osn),
             os.path.join(base, '.venv', 'Scripts', 'python.exe'),
             os.path.join(base, '.venv', 'bin', 'python'),
             os.path.join(base, '.venv', 'bin', 'python.exe')]
    return next((c for c in cands if os.path.isfile(c)), None)


def shell_path(p):
    """A path that can be pasted, in double quotes, into bash, zsh, Git Bash and PowerShell alike: forward slashes
    (Windows accepts them; backslashes are escape characters in bash)."""
    return p.replace('\\', '/') if p else p


def path_arg(p):
    """A path typed on a command line. PowerShell does not expand ~ for programs, so do it here."""
    return os.path.normpath(os.path.expanduser(p))


def project_file(project, p):
    """A file of a project named on a command line. A full path is taken as it is. A short one ("renders/x.mp4") is
    looked up inside the project folder first, so the command works from any working folder, then where it stands."""
    p = path_arg(p)
    if os.path.isabs(p):
        return p
    inside = os.path.join(project, p)
    return inside if os.path.exists(inside) or not os.path.exists(p) else p


def safe_name(s):
    """File-name-safe version of an id (Windows forbids : ? * " < > | in names)."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(s))


def concat_entry(name):
    """One line of an ffmpeg concat list. Forward slashes only (a backslash is an escape character in that file)
    and a quote inside the name closed, escaped and reopened."""
    return "file '" + name.replace('\\', '/').replace("'", "'\\''") + "'\n"


def utf8_stdio():
    """Windows pipes default to cp1252: printing a transcript with a curly quote or a music note would crash."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


# ------------------------------------------------------------------ tools
def _exe(name, osn):
    return name + '.exe' if osn == 'windows' else name


def fallback_dirs(name, osn, environ=None, home=None):
    """Usual install folders, for a tool that is installed but not on this session's PATH (typical right after an
    install on Windows: the running app keeps the old PATH until it is restarted)."""
    environ = os.environ if environ is None else environ
    home = home or os.path.expanduser('~')
    pm = _pm(osn)
    if osn == 'windows':
        local = environ.get('LOCALAPPDATA') or pm.join(home, 'AppData', 'Local')
        pf = environ.get('ProgramFiles') or 'C:\\Program Files'
        dirs = [pm.join(local, 'Microsoft', 'WinGet', 'Links')]
        if name in ('ffmpeg', 'ffprobe'):
            dirs += [pm.join(local, 'Microsoft', 'WinGet', 'Packages', 'Gyan.FFmpeg*', '*', 'bin'),
                     'C:\\ffmpeg\\bin', pm.join(pf, 'ffmpeg', 'bin')]
        if name in ('node', 'npx'):
            dirs += [pm.join(pf, 'nodejs')]
            if environ.get('NVM_SYMLINK'):
                dirs.append(environ['NVM_SYMLINK'])
        dirs += [pm.join(home, 'scoop', 'shims'), 'C:\\ProgramData\\chocolatey\\bin']
        return dirs
    dirs = ['/opt/homebrew/bin', '/usr/local/bin'] if osn == 'macos' else ['/usr/local/bin', '/usr/bin', '/snap/bin']
    if name in ('node', 'npx'):
        dirs = [pm.join(home, '.nvm', 'versions', 'node', 'v*', 'bin'), '/opt/homebrew/opt/node@22/bin',
                '/usr/local/opt/node@22/bin', pm.join(home, '.volta', 'bin'),
                pm.join(home, '.local', 'share', 'fnm', 'node-versions', 'v*', 'installation', 'bin'),
                pm.join(home, 'Library', 'Application Support', 'fnm', 'node-versions', 'v*', 'installation', 'bin')] + dirs
    return dirs


def find_tool(name, osn=None):
    """-> (absolute path or None, on_path). PATH first, then the usual install folders."""
    osn = osn or os_name()[0]
    p = shutil.which(name)
    if p:
        return os.path.abspath(p), True
    for pat in fallback_dirs(name, osn):
        for d in sorted(glob.glob(pat), reverse=True):
            cand = os.path.join(d, _exe(name, osn))
            if os.path.isfile(cand):
                return cand, False
    return None, False


def node_major(version_text):
    m = re.match(r'\s*v?(\d+)\.', version_text or '')
    return int(m.group(1)) if m else 0


def _node_version(node):
    try:
        return subprocess.run([node, '-v'], timeout=20, **TEXT).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def nvm_node22(environ=None, home=None):
    """-> (node path, version text) of the newest Node 22 installed with nvm, or (None, ''). This is exactly what the
    old zsh scripts selected with `nvm use 22`, whatever the default Node was."""
    environ = os.environ if environ is None else environ
    home = home or os.path.expanduser('~')
    found = []
    for root in dict.fromkeys([environ.get('NVM_DIR') or '', os.path.join(home, '.nvm')]):
        for cand in glob.glob(os.path.join(root, 'versions', 'node', 'v22.*', 'bin', 'node')) if root else []:
            v = _node_version(cand)
            if node_major(v) == 22:
                found.append((tuple(int(x) for x in re.findall(r'\d+', v)[:3]), cand, v))
    if not found:
        return None, ''
    _, cand, v = max(found)
    return cand, v


def find_node(osn=None, environ=None, home=None, state=None):
    """-> (node path or None, version text, on_path).
    macOS / Linux with nvm: nvm's Node 22 first, as `nvm use 22` did before (same Node as the zsh scripts used).
    Otherwise the node on PATH when it is new enough. Otherwise look in Homebrew / the Windows installer folder /
    other version managers and take Node 22 if it is there, else the newest. Last, the skill's own copy in the
    state folder (setup.py fetches it when the computer has none)."""
    osn = osn or os_name()[0]
    best = (None, '', False)
    p = shutil.which('node')
    if osn != 'windows':
        cand, v = nvm_node22(environ, home)
        if cand:
            return cand, v, bool(p) and os.path.realpath(p) == os.path.realpath(cand)
    if p:
        v = _node_version(p)
        if node_major(v) >= MIN_NODE:
            return os.path.abspath(p), v, True
        best = (os.path.abspath(p), v, True)
    found = []
    for pat in fallback_dirs('node', osn):
        for d in glob.glob(pat):
            cand = os.path.join(d, _exe('node', osn))
            if os.path.isfile(cand):
                v = _node_version(cand)
                if node_major(v) >= MIN_NODE:
                    found.append((node_major(v) == MIN_NODE, tuple(int(x) for x in re.findall(r'\d+', v)[:3]), cand, v))
    if found:
        _, _, cand, v = max(found)
        return cand, v, False
    own = own_node(state, osn)
    if own:
        v = _node_version(own)
        if node_major(v) >= MIN_NODE:
            return own, v, False
    return best


def npx_command(node, osn=None, exists=os.path.isfile):
    """argv prefix that starts npx without a shell.
    Windows: `npx` is npx.cmd (a batch file), which subprocess cannot start by bare name. Prefer node.exe + npm's
    npx-cli.js (no cmd.exe in between, so no batch quoting surprises); fall back to the full path of npx.cmd.
    macOS / Linux: the npx script next to node (its `#!/usr/bin/env node` needs that folder first on PATH, which
    hyperframes_env() takes care of)."""
    osn = osn or os_name()[0]
    if not node:
        return None
    pm = _pm(osn)
    d = pm.dirname(node)
    if osn == 'windows':
        cli = pm.join(d, 'node_modules', 'npm', 'bin', 'npx-cli.js')
        if exists(cli):
            return [node, cli]
        cmd = pm.join(d, 'npx.cmd')
        if exists(cmd):
            return [cmd]
        w = shutil.which('npx')
        return [w] if w else None
    npx = pm.join(d, 'npx')
    if exists(npx):
        return [npx]
    w = shutil.which('npx')
    return [w] if w else None


# ------------------------------------------------------------------ .platform.json
def load():
    """The machine record written by setup.py, or {} when it is missing, unreadable or from another machine
    (a skill folder copied from a Mac to a PC must not reuse the Mac's paths)."""
    try:
        with open(platform_file(), encoding='utf-8') as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(rec, dict) or rec.get('schema') != SCHEMA or rec.get('os') != os_name()[0]:
        return {}
    return rec


def tool(name):
    """Absolute path of ffmpeg / ffprobe: the one setup.py recorded if it still exists, else found again, else the
    bare name (so the error names the missing program)."""
    rec = load().get(name)
    if rec and os.path.isfile(rec):
        return os.path.normpath(rec)
    return find_tool(name)[0] or name


def hyperframes_env(node=None, ffmpeg=None, environ=None, pathsep=os.pathsep, dirname=os.path.dirname):
    """Environment for a HyperFrames run: the chosen Node and ffmpeg folders first on PATH, anonymous usage
    telemetry off unless the user set it themselves."""
    env = dict(os.environ if environ is None else environ)
    key = next((k for k in env if k.upper() == 'PATH'), 'PATH')
    parts = [p for p in env.get(key, '').split(pathsep) if p]
    for exe in (ffmpeg, node):
        d = dirname(exe) if exe else ''
        if d:   # move to the front even when it is already further down (an older nvm Node may sit before it)
            parts = [d] + [p for p in parts if p != d]
    env[key] = pathsep.join(parts)
    env.setdefault('HYPERFRAMES_NO_TELEMETRY', '1')
    return env


def hyperframes_command(args):
    """-> (argv, env) for `npx --yes hyperframes@<pinned> <args>`."""
    rec = load()
    if rec.get('node') and rec.get('npx') and all(os.path.isfile(p) for p in [rec['node']] + rec['npx']):
        node, npx = os.path.normpath(rec['node']), [os.path.normpath(p) for p in rec['npx']]   # .json keeps / on Windows
    else:
        node = find_node()[0]
        npx = npx_command(node)
    if not npx:
        raise SystemExit(f'Node.js {MIN_NODE}+ (npx) not found. Run setup.py in the skill folder and follow its fix.')
    ffmpeg = tool('ffmpeg')
    return npx + ['--yes', HYPERFRAMES] + list(args), hyperframes_env(node, ffmpeg if os.path.isabs(ffmpeg) else None)


def split_project_arg(args):
    """`hf.py "<project>" lint` -> ('<project>', ['lint']). The first argument is taken as the folder to run in when
    it is an existing folder (no HyperFrames command is one); also `--project <folder>` anywhere. Else (None, args)."""
    args = list(args)
    if '--project' in args:
        i = args.index('--project')
        if i + 1 < len(args):
            folder = path_arg(args[i + 1])
            return folder, args[:i] + args[i + 2:]
    if args and os.path.isdir(path_arg(args[0])) and (os.sep in args[0] or '/' in args[0] or args[0].startswith('~')):
        return path_arg(args[0]), args[1:]
    return None, args


def run_hyperframes(args, cwd=None):
    argv, env = hyperframes_command(args)
    return subprocess.run(argv, cwd=cwd, env=env).returncode
