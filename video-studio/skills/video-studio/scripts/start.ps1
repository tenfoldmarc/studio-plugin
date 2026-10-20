# video-studio (Creator Studio): the setup check for Windows, for a computer that may have no Python.
#
# Usage:   powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1 [the same options as setup.py]
#
# setup.py is a Python script, so it cannot be what puts Python on the computer. This file can: it needs nothing
# but what Windows 10 and 11 ship (PowerShell, tar). It finds a Python in this order and runs setup.py with it:
#   1. the skill's own environment in the state folder (every run after the first one ends here)
#   2. the skill's own Python in the state folder (fetched by an earlier run of this file)
#   3. a Python 3.9 to 3.13 already on the computer (python, then py -3; a newer one is skipped: the transcription
#      engine has no build for it, see NEWEST_PY in skillenv.py)
#   4. none: it fetches the skill its own Python into <state>\python (python-build-standalone, pinned, about
#      46 MB, checked against its SHA-256). Nothing is installed system-wide and no admin rights are asked.
#      Always the x64 build: the transcription engine has no Windows ARM build, and x64 runs on Windows on ARM.
# It prints the same STATUS lines as setup.py. When no Python can be had it prints STATUS python MISSING with the
# steps for this computer and exits 1.
#
# Run end to end on Windows Server 2025 (GitHub's windows-latest, Python and Node hidden from the PATH, started from
# PowerShell 7) on 2026-10-17 by ci/e2e.py: own Python fetched and checked, setup, one full edit. Not yet run on a
# home Windows 10 or 11 PC. SKILL.md treats a failure here as "Python is missing" and gives the install steps.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'      # a download is many times slower with the progress bar on

$PyVersion = '3.12.15'
$PyRelease = '20261009'
$PySha256  = '194c8f0d9e0de6f1c4576e5dfa67819a48c764be87608b74b8ad43387a57b93b'
$PyUrl     = "https://github.com/astral-sh/python-build-standalone/releases/download/$PyRelease/cpython-$PyVersion%2B$PyRelease-x86_64-pc-windows-msvc-install_only.tar.gz"
$Restart   = 'then quit Claude Code completely, reopen it and run the skill again'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---- the state folder: the same answer skillenv.resolve_state() gives
$Local = $env:LOCALAPPDATA
if (-not $Local) { $Local = Join-Path $HOME 'AppData\Local' }
$State = Join-Path $Local 'video-studio'
$Data = $env:CLAUDE_PLUGIN_DATA
if ($Data -and [IO.Path]::IsPathRooted($Data) -and ((Split-Path -Leaf $Data) -match '^video-studio(-.*)?$')) { $State = $Data }
for ($i = 0; $i -lt $args.Count; $i++) {
    $a = [string]$args[$i]
    if ($a -eq '--state' -and ($i + 1) -lt $args.Count -and [IO.Path]::IsPathRooted([string]$args[$i + 1])) { $State = [string]$args[$i + 1] }
    elseif ($a.StartsWith('--state=') -and [IO.Path]::IsPathRooted($a.Substring(8))) { $State = $a.Substring(8) }
}

function Test-Python([string]$Py) {
    # is this a working Python 3.9 to 3.13, one the pinned packages install on? (NEWEST_PY in skillenv.py; the Store
    # placeholder prints "Python was not found" and fails here). Also for the Studio's own environment: setup.py keeps
    # one built on a newer Python when it works, but setup.py itself must run on a Python it can build with.
    if (-not $Py -or -not (Test-Path -LiteralPath $Py -PathType Leaf)) { return $false }
    try {
        & $Py -c "import sys; sys.exit(0 if (3, 9) <= sys.version_info[:2] <= (3, 13) else 1)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Stop-Missing([string]$Why) {
    Write-Output "STATUS python MISSING ($Why) -> winget install --id Python.Python.3.12 -e   ($Restart)"
    Write-Output 'NOT READY'
    exit 1
}

$Py = $null
foreach ($cand in @((Join-Path $State '.venv\Scripts\python.exe'), (Join-Path $State 'python\python.exe'))) {
    if (Test-Python $cand) { $Py = $cand; break }
}

if (-not $Py) {
    $cmd = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and (Test-Python $cmd.Source)) { $Py = $cmd.Source }
}
if (-not $Py) {
    $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        try {
            $found = (& $launcher.Source -3 -c "import sys; print(sys.executable)" 2> $null | Select-Object -First 1)
            if ($found -and (Test-Python ([string]$found).Trim())) { $Py = ([string]$found).Trim() }
        } catch { }
    }
}

if (-not $Py) {
    Write-Output 'STATUS python: none on this computer it can use (it needs 3.9 to 3.13), getting the skill its own copy (about 46 MB, one time)'
    $tar = Get-Command tar -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $tar) { Stop-Missing 'the skill could not unpack its own copy: this Windows has no tar' }
    try { New-Item -ItemType Directory -Force -Path $State | Out-Null } catch { Stop-Missing "could not create $State" }
    $part = Join-Path $State 'python.tar.gz.part'
    $new  = Join-Path $State 'python.unpack'
    foreach ($left in @($part, $new)) {           # our own leftovers from a run that was cut off
        if (Test-Path -LiteralPath $left) { Remove-Item -LiteralPath $left -Recurse -Force -ErrorAction SilentlyContinue }
    }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # .NET first for the same reason as the checksum below; Invoke-WebRequest only if that is refused
        try { (New-Object Net.WebClient).DownloadFile($PyUrl, $part) }
        catch { Invoke-WebRequest -Uri $PyUrl -OutFile $part -UseBasicParsing }
    } catch {
        if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue }
        Stop-Missing 'the skill could not get its own copy: no internet'
    }
    # .NET, not Get-FileHash: started from PowerShell 7 (pwsh), Windows PowerShell 5.1 inherits pwsh's module path and
    # cannot load the module Get-FileHash lives in (seen on a fresh Windows machine). .NET is always there.
    $got = ''
    try {
        $stream = [IO.File]::OpenRead($part)
        try { $got = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($stream))).Replace('-', '').ToLower() }
        finally { $stream.Dispose() }
    } catch { $got = '' }
    if ($got -ne $PySha256) {
        Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
        Stop-Missing 'the download did not pass its check, so it was not used'
    }
    New-Item -ItemType Directory -Force -Path $new | Out-Null
    & $tar.Source -xzf $part -C $new
    Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
    if (-not (Test-Python (Join-Path $new 'python\python.exe'))) {
        Remove-Item -LiteralPath $new -Recurse -Force -ErrorAction SilentlyContinue
        Stop-Missing 'the skill could not get its own copy: the download does not run on this system'
    }
    $own = Join-Path $State 'python'
    if (Test-Path -LiteralPath $own) { Remove-Item -LiteralPath $own -Recurse -Force -ErrorAction SilentlyContinue }
    Move-Item -LiteralPath (Join-Path $new 'python') -Destination $own
    Remove-Item -LiteralPath $new -Recurse -Force -ErrorAction SilentlyContinue
    $Py = Join-Path $own 'python.exe'
    if (-not (Test-Python $Py)) { Stop-Missing 'the skill could not get its own copy' }
    Write-Output "STATUS python OK ($PyVersion, the skill's own copy)"
}

& $Py (Join-Path $Here 'setup.py') @args
exit $LASTEXITCODE
