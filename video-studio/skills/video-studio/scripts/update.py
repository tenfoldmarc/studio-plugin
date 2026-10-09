#!/usr/bin/env python3
"""Check for a newer version of the Studio, and install it.

Usage:  PY update.py --check     is there a newer version? (setup.py asks this once a day by itself)
        PY update.py             install the newest version: the buyer said yes, or said "update the Studio"

The Studio is a plugin: the newest version is whatever its source on GitHub holds. Installing it is done by
Claude's own plugin command, run here so the buyer never opens a terminal. Nothing of theirs is touched: picks,
their own style and the tools setup downloaded live in the state folder, which an update leaves alone.

Lines to watch for:
    STATUS update NONE (1.16.0 is the newest)
    STATUS update AVAILABLE 1.16.0 -> 1.17.0 ...          ask the buyer, then run this again without --check
    STATUS update DONE 1.16.0 -> 1.17.0 ...               tell the buyer to start a new chat
    STATUS update SKIPPED <why>                           offline, or this copy does not update this way: carry on
    STATUS update MANUAL <steps>                          pass the steps on word for word
Standard library only, so it also runs before setup has finished.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skillenv  # noqa: E402

PLUGIN = 'video-studio'
SOURCE = 'https://raw.githubusercontent.com/tenfoldmarc/studio-plugin/main/'
MANIFEST = SOURCE + 'video-studio/.claude-plugin/plugin.json'
NOTES = SOURCE + 'whats-new.json'


def say(line):
    print(line, flush=True)


def as_tuple(version):
    return tuple(int(x) for x in re.findall(r'\d+', version or '')[:3])


def installed(skill_dir=None):
    """-> (version or None, marketplace or None, kind). kind: 'marketplace' (installed from the plugin source,
    updates with Claude's plugin command), 'account' (arrives through the buyer's Claude account), or 'folder'
    (copied in by hand or uploaded as a file: no version to compare)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(skill_dir or skillenv.SKILL_DIR)))
    version = None
    try:
        with open(os.path.join(root, '.claude-plugin', 'plugin.json'), encoding='utf-8') as fh:
            version = json.load(fh).get('version')
    except (OSError, ValueError):
        pass
    parts = os.path.normpath(root).replace('\\', '/').split('/')
    for i in range(len(parts) - 2):
        if parts[i] == 'plugins' and parts[i + 1] == 'cache' and i + 3 < len(parts) and parts[i + 3] == PLUGIN:
            return version, parts[i + 2], 'marketplace'
        if parts[i] == 'plugins' and parts[i + 1] == 'synced':
            return version, None, 'account'
    return version, None, 'folder'


def fetch_json(url, timeout=5):
    req = urllib.request.Request(url, headers={'User-Agent': 'video-studio-update', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(200000).decode('utf-8', 'replace'))


def newest():
    """-> (version, one line on what is new or '')"""
    version = str(fetch_json(MANIFEST).get('version') or '')
    note = ''
    try:
        note = str((fetch_json(NOTES, timeout=4) or {}).get(version) or '')[:200]
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return version, note


def check(state=None, force=False):
    """One STATUS line, or None when there is nothing to say (a copy that does not update this way).
    Asks GitHub at most once a day unless forced; the answer is kept in <state>/update-check.json."""
    have, _, kind = installed()
    if kind != 'marketplace' or not have:
        return None
    cache = os.path.join(state, 'update-check.json') if state else None
    today = datetime.date.today().isoformat()
    latest = note = None
    if cache and not force:
        try:
            with open(cache, encoding='utf-8') as fh:
                seen = json.load(fh)
            if seen.get('checked') == today:
                latest, note = seen.get('latest'), seen.get('note', '')
        except (OSError, ValueError):
            pass
    if not latest:
        try:
            latest, note = newest()
        except (urllib.error.URLError, OSError, ValueError):
            return 'STATUS update SKIPPED (could not reach the update source: offline is fine, carry on)'
        if cache and latest:
            try:
                with open(cache, 'w', encoding='utf-8') as fh:
                    json.dump({'checked': today, 'latest': latest, 'note': note}, fh)
            except OSError:
                pass
    if not latest or as_tuple(latest) <= as_tuple(have):
        return f'STATUS update NONE ({have} is the newest)'
    what = f' What is new: {note}' if note else ''
    return (f'STATUS update AVAILABLE {have} -> {latest}.{what} Ask the buyer once: "There is an update for the Studio '
            f'with fixes. Want me to install it? It takes a minute." On yes: PY "{skillenv.shell_path(os.path.abspath(__file__))}"')


def claude_program():
    """The Claude Code program to run plugin commands with: the one running this chat when it says where it is
    (the desktop app does), else the one on the PATH, else the usual install places."""
    home = os.path.expanduser('~')
    spots = [os.environ.get('CLAUDE_CODE_EXECPATH'), shutil.which('claude'),
             os.path.join(home, '.claude', 'local', 'claude'), os.path.join(home, '.local', 'bin', 'claude'),
             '/usr/local/bin/claude', '/opt/homebrew/bin/claude',
             os.path.join(home, '.local', 'bin', 'claude.exe'),
             os.path.join(os.environ.get('APPDATA', ''), 'npm', 'claude.cmd') if os.environ.get('APPDATA') else None]
    return next((p for p in spots if p and os.path.isfile(p)), None)


def manual(marketplace):
    name = marketplace or 'creator-studio'
    return ('STATUS update MANUAL: I could not run the update from here. Tell the buyer: "Open Terminal (Mac) or '
            'PowerShell (Windows), not Claude, and paste these two lines one at a time, then start a new chat." '
            f'Line 1: claude plugin marketplace update {name}   Line 2: claude plugin update {PLUGIN}@{name}')


def run(cmd):
    try:
        r = subprocess.run(cmd, timeout=300, **skillenv.TEXT)
        return r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, type(e).__name__


def update():
    have, marketplace, kind = installed()
    if kind == 'account':
        say('STATUS update SKIPPED: this copy arrives through the buyer\'s Claude account and updates there by itself. '
            'Tell them to start a new chat to get the newest version.')
        return 0
    if kind != 'marketplace' or not have:
        say('STATUS update SKIPPED: this copy was put in by hand, so it does not update by itself. Tell the buyer '
            'the install steps in their portal get them the version that does.')
        return 0
    try:
        latest, _ = newest()
    except (urllib.error.URLError, OSError, ValueError):
        say('STATUS update SKIPPED (could not reach the update source: try again when online)')
        return 0
    if as_tuple(latest) <= as_tuple(have):
        say(f'STATUS update NONE ({have} is the newest)')
        return 0
    claude = claude_program()
    if not claude:
        say(manual(marketplace))
        return 2
    code, out = run([claude, 'plugin', 'marketplace', 'update', marketplace])
    if code == 0:
        code, out = run([claude, 'plugin', 'update', f'{PLUGIN}@{marketplace}'])
    versions = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(skillenv.SKILL_DIR))))
    got = sorted((d for d in os.listdir(versions) if os.path.isdir(os.path.join(versions, d))), key=as_tuple)[-1:] \
        if os.path.isdir(versions) else []
    if code != 0 or not got or as_tuple(got[0]) <= as_tuple(have):
        say(manual(marketplace) + '   (what the update said: ' + out[-160:].replace('\n', ' ') + ')')
        return 2
    say(f'STATUS update DONE {have} -> {got[0]}. Tell the buyer: "Updated. Start a new chat and you are on the new '
        'version. Your picks and your style are untouched."')
    return 0


def main():
    skillenv.utf8_stdio()
    if '--check' in sys.argv:
        line = check(skillenv.state_dir(), force='--force' in sys.argv)
        say(line or 'STATUS update SKIPPED (this copy does not update this way)')
        return 0
    return update()


if __name__ == '__main__':
    sys.exit(main())
