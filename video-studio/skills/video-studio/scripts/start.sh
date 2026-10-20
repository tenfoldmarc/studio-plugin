#!/bin/sh
# video-studio (Creator Studio): the setup check for macOS and Linux, for a computer that may have no Python.
#
# Usage:   sh start.sh [the same options as setup.py]
#
# setup.py is a Python script, so it cannot be what puts Python on the computer. This file can: it needs nothing
# but the tools every Mac and Linux ships (sh, curl, tar, shasum or sha256sum). It finds a Python in this order
# and then runs setup.py with it:
#   1. the skill's own environment in the state folder (every run after the first one ends here)
#   2. the skill's own Python in the state folder (fetched by an earlier run of this file)
#   3. a Python 3.9 to 3.13 already on the computer (a newer one is skipped: the transcription engine has no
#      build for it, see NEWEST_PY in skillenv.py)
#   4. none: it fetches the skill its own Python into <state>/python (python-build-standalone, pinned, about
#      25 MB on a Mac, checked against its SHA-256). Nothing is installed system-wide and no password is asked.
# It prints the same STATUS lines as setup.py. When no Python can be had it prints STATUS python MISSING with the
# steps for this computer and exits 1.
#
# On a Mac /usr/bin/python3 is only a placeholder until Apple's developer tools are installed, and running the
# placeholder opens an "install developer tools" window. So it is never run: the developer tools' own Python is
# used by its real path, and only when it is there.

PY_VERSION='3.12.15'
PY_RELEASE='20261009'
PY_SOURCE='https://github.com/astral-sh/python-build-standalone/releases/download'
SHA_aarch64_apple_darwin='83dcb04777c798bd95f3687acf9ae84b09860272ee6bdfb05be8bcf9447f75b8'
SHA_x86_64_apple_darwin='4c84ef5abe4bc145646175fce9b881936d60126b9a3f9a24c6308e2d035ca5c6'
SHA_x86_64_unknown_linux_gnu='5864001bf969db329fadc2b654c4878c6027d170c6bd77e28f88666260bcaf63'
SHA_aarch64_unknown_linux_gnu='b342ccfb577fda349d0237c98b24848234ca767c10f034628a5ff9fc858d662f'
CLT="${VIDEO_STUDIO_CLT:-/Library/Developer/CommandLineTools}"   # Apple's developer tools (the variable is for tests)

HERE=$(cd "$(dirname "$0")" && pwd)
OS=$(uname -s)
ARCH=$(uname -m)

# ---- the state folder: the same answer skillenv.resolve_state() gives
case "$OS" in
  Darwin) STATE="$HOME/Library/Application Support/video-studio" ;;
  *)      case "${XDG_DATA_HOME:-}" in
            /*) STATE="$XDG_DATA_HOME/video-studio" ;;
            *)  STATE="$HOME/.local/share/video-studio" ;;
          esac ;;
esac
case "${CLAUDE_PLUGIN_DATA:-}" in
  /*/video-studio|/*/video-studio-*) STATE="$CLAUDE_PLUGIN_DATA" ;;
esac
prev=''
for a in "$@"; do
  case "$a" in --state=/*) STATE="${a#--state=}" ;; esac
  case "$prev" in --state) case "$a" in /*) STATE="$a" ;; esac ;; esac
  prev="$a"
done

runs() {      # is this a working Python 3.9 to 3.13, one the pinned packages install on? (NEWEST_PY in skillenv.py)
  # also for the Studio's own environment: one built on a newer Python is left to setup.py, which keeps it when it
  # works and rebuilds it when it does not, but setup.py itself must run on a Python it can build with
  [ -n "$1" ] && [ -x "$1" ] && "$1" -c 'import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1
}

PY=''
for cand in "$STATE/.venv/bin/python" "$STATE/python/bin/python3"; do
  if runs "$cand"; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
  for name in python3 python; do
    cand=$(command -v "$name" 2>/dev/null) || continue
    if [ "$OS" = Darwin ] && [ "$cand" = /usr/bin/python3 ]; then
      cand="$CLT/usr/bin/python3"                    # never the placeholder itself
    fi
    if runs "$cand"; then PY="$cand"; break; fi
  done
fi

missing() {   # $1 = why
  case "$OS" in
    Darwin) steps='step 1, download Python 3.12 from https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg and open it to install. Step 2, run the skill again' ;;
    *)      steps='sudo apt install python3 python3-venv' ;;
  esac
  echo "STATUS python MISSING ($1) -> $steps"
  echo 'NOT READY'
  exit 1
}

if [ -z "$PY" ]; then
  if [ "$OS" = Darwin ]; then
    if [ "$ARCH" = arm64 ] || [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then
      build='aarch64-apple-darwin'; sum="$SHA_aarch64_apple_darwin"
    else
      build='x86_64-apple-darwin'; sum="$SHA_x86_64_apple_darwin"
    fi
  else
    case "$ARCH" in
      x86_64|amd64)  build='x86_64-unknown-linux-gnu'; sum="$SHA_x86_64_unknown_linux_gnu" ;;
      aarch64|arm64) build='aarch64-unknown-linux-gnu'; sum="$SHA_aarch64_unknown_linux_gnu" ;;
      *) missing "the skill has no Python of its own for this system ($ARCH)" ;;
    esac
  fi
  echo 'STATUS python: none on this computer it can use (it needs 3.9 to 3.13), getting the skill its own copy (about 25 MB on a Mac, 60 MB on Linux, one time)'
  mkdir -p "$STATE" || missing "could not create $STATE"
  part="$STATE/python.tar.gz.part"
  new="$STATE/python.unpack"
  # %2B is the + in the file name
  url="$PY_SOURCE/$PY_RELEASE/cpython-$PY_VERSION%2B$PY_RELEASE-$build-install_only.tar.gz"
  rm -rf "$new" "$part"                              # our own leftovers from a run that was cut off
  # a connection that stops arriving for 45 seconds is given up (not waited on for ever) and the download is
  # started again, 3 tries in all, with a line each time so nobody is staring at silence
  try=1
  until curl -fsSL --connect-timeout 20 --speed-limit 1024 --speed-time 45 -o "$part" "$url"; do
    rm -f "$part"
    [ "$try" -lt 3 ] || missing 'the skill could not get its own copy: no internet'
    try=$((try + 1))
    echo "STATUS python: the download did not finish, trying again (attempt $try of 3)"
    sleep 3
  done
  if command -v shasum >/dev/null 2>&1; then
    got=$(shasum -a 256 "$part" | cut -d ' ' -f 1)
  else
    got=$(sha256sum "$part" | cut -d ' ' -f 1)
  fi
  if [ "$got" != "$sum" ]; then
    rm -f "$part"
    missing 'the download did not pass its check, so it was not used'
  fi
  mkdir -p "$new" && tar -xzf "$part" -C "$new"
  rm -f "$part"
  if ! runs "$new/python/bin/python3"; then
    rm -rf "$new"
    missing 'the skill could not get its own copy: the download does not run on this system'
  fi
  rm -rf "$STATE/python"
  mv "$new/python" "$STATE/python" && rm -rf "$new"
  PY="$STATE/python/bin/python3"
  runs "$PY" || missing 'the skill could not get its own copy'
  echo "STATUS python OK ($PY_VERSION, the skill's own copy)"
fi

exec "$PY" "$HERE/setup.py" "$@"
