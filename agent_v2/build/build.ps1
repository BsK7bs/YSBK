<#
.SYNOPSIS
    Build the Digital Twin Agent v2 Windows binaries.

.DESCRIPTION
    Runs on Windows 10/11 or a windows-latest GitHub Actions runner with
    Python 3.11 x64 on PATH. Produces:

        DigitalTwinAgentSetup.exe  <- the ONE artifact shipped to customers
        agent.exe                  <- the Windows Service host
        uninstaller.exe            <- matching uninstall utility

    All three are written to $OutputDir (default: <repo>\dist). The dashboard
    Download Agent button streams DigitalTwinAgentSetup.exe from that
    directory.

    Path model (single source of truth):
        $PSScriptRoot  =  <repo>\agent_v2\build            (this file's dir)
        $AgentRoot     =  <repo>\agent_v2
        $RepoRoot      =  <repo>

    All three variables are exported into the environment so the PyInstaller
    spec files can reference the same values via os.environ if ever needed.

.PARAMETER BackendUrl
    Baked into the compiled installer via the DIGITAL_TWIN_BACKEND_URL env
    variable so the shipped EXE knows where to phone home.

.PARAMETER Clean
    Purge build\, dist\, and the target OutputDir before rebuilding.

.PARAMETER OutputDir
    Where the final EXEs land. Default: <repo>\dist

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build.ps1
    powershell -ExecutionPolicy Bypass -File build.ps1 -Clean -BackendUrl "https://cloud.digitaltwin.example"
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$BackendUrl = $env:DIGITAL_TWIN_BACKEND_URL,
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Path resolution - ALL derived from $PSScriptRoot to keep CI + local identical
# ---------------------------------------------------------------------------
$BuildDir  = $PSScriptRoot
$AgentRoot = (Resolve-Path (Join-Path $BuildDir  "..")).Path
$RepoRoot  = (Resolve-Path (Join-Path $AgentRoot "..")).Path

if (-not $OutputDir) { $OutputDir = Join-Path $RepoRoot "dist" }
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot $OutputDir
}

# Publish the resolved roots so the spec files and hidden imports can align.
$env:DT_BUILD_DIR  = $BuildDir
$env:DT_AGENT_ROOT = $AgentRoot
$env:DT_REPO_ROOT  = $RepoRoot

Write-Host "[build] PSScriptRoot = $BuildDir"
Write-Host "[build] AgentRoot    = $AgentRoot"
Write-Host "[build] RepoRoot     = $RepoRoot"
Write-Host "[build] OutputDir    = $OutputDir"

# ---------------------------------------------------------------------------
# Backend URL (baked into installer at compile time)
# ---------------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($BackendUrl)) {
    Write-Warning "No -BackendUrl passed (and DIGITAL_TWIN_BACKEND_URL is empty)."
    Write-Warning "The installer will fall back to the placeholder in agent_v2\common\version.py."
} else {
    $env:DIGITAL_TWIN_BACKEND_URL = $BackendUrl
    Write-Host "[build] backend_url  = $BackendUrl (baked into installer)"
}

# ---------------------------------------------------------------------------
# Pre-flight: entry points must exist under agent_v2\
# ---------------------------------------------------------------------------
$Entries = @(
    (Join-Path $AgentRoot "installer\__main__.py"),
    (Join-Path $AgentRoot "agent\__main__.py"),
    (Join-Path $AgentRoot "uninstaller\__main__.py")
)
foreach ($e in $Entries) {
    if (-not (Test-Path $e -PathType Leaf)) {
        throw "Entry point not found: $e"
    }
    Write-Host "[build] entry: OK  $e"
}

# ---------------------------------------------------------------------------
# Guard: reject stale root-level directories that would cause the old bug
# ---------------------------------------------------------------------------
foreach ($legacy in @("installer", "modules", "agent", "uninstaller")) {
    $stale = Join-Path $RepoRoot $legacy
    if (Test-Path $stale -PathType Container) {
        throw "Legacy root-level directory found: $stale"
    }
}

# ---------------------------------------------------------------------------
# Print + SHA-256 the entry files that PyInstaller will freeze.
# This is the FIRST thing an operator investigating "did we ship the
# right code?" needs to see in the CI log.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[build] ============================================================"
Write-Host "[build] ENTRY FILES PyInstaller WILL PACKAGE"
Write-Host "[build] ============================================================"
foreach ($entry in $Entries) {
    $sha  = (Get-FileHash -Algorithm SHA256 $entry).Hash.ToLower()
    $size = (Get-Item $entry).Length
    Write-Host ("[build]   {0}" -f $entry)
    Write-Host ("[build]     size   = {0} bytes" -f $size)
    Write-Host ("[build]     sha256 = {0}" -f $sha)
    # Also print the first 3 executable lines so it is impossible to
    # miss whether the current fast-path is present.
    $head = Get-Content $entry -TotalCount 5
    Write-Host "[build]     head   ="
    foreach ($line in $head) { Write-Host ("[build]        {0}" -f $line) }
}
Write-Host "[build] ============================================================"

# ---------------------------------------------------------------------------
# Belt-and-braces cache purge. PyInstaller keeps state in
#   %LOCALAPPDATA%\pyinstaller
# and __pycache__ folders scattered through the source tree. If one of
# these ever contains a stale bytecode copy of __main__.py, the frozen
# EXE can silently pick up an old version. Nuke them before every build.
# ---------------------------------------------------------------------------
Write-Host "[build] purging stale PyInstaller cache + __pycache__ trees"
$pyiCache = Join-Path $env:LOCALAPPDATA "pyinstaller"
if (Test-Path $pyiCache) {
    Remove-Item -Recurse -Force $pyiCache -ErrorAction SilentlyContinue
    Write-Host "[build]   removed $pyiCache"
}
Get-ChildItem -Path $AgentRoot -Filter "__pycache__" -Recurse -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
    Write-Host ("[build]   removed {0}" -f $_.FullName)
}

# ---------------------------------------------------------------------------
# Python + build deps
# ---------------------------------------------------------------------------
try {
    $py = & python --version 2>&1
    Write-Host "[build] python: $py"
} catch {
    throw "Python 3.11 x64 is required on PATH."
}

Write-Host "[build] installing/upgrading build dependencies"
& python -m pip install --upgrade pip wheel setuptools | Out-Null
& python -m pip install pyinstaller==6.6.0 | Out-Null
& python -m pip install -r (Join-Path $AgentRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed rc=$LASTEXITCODE" }

# ---------------------------------------------------------------------------
# PYTHONPATH - expose BOTH the repo root (for 'import agent_v2.*') and
# agent_v2\ (for 'from ..common ...' in-package imports) to PyInstaller.
# ---------------------------------------------------------------------------
$env:PYTHONPATH = "$RepoRoot;$AgentRoot;$env:PYTHONPATH"
Write-Host "[build] PYTHONPATH   = $env:PYTHONPATH"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
if ($Clean) {
    Write-Host "[build] --Clean: purging build\, dist\, and $OutputDir"
    Remove-Item -Recurse -Force (Join-Path $BuildDir "build") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $BuildDir "dist")  -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $OutputDir                    -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# ---------------------------------------------------------------------------
# Build each EXE
# ---------------------------------------------------------------------------
Push-Location $BuildDir
try {
    foreach ($spec in @("installer.spec", "agent.spec", "uninstaller.spec")) {
        $specPath = Join-Path $BuildDir $spec
        if (-not (Test-Path $specPath)) { throw "Spec file missing: $specPath" }
        Write-Host "[build] pyinstaller $spec"
        & python -m PyInstaller --noconfirm --clean $specPath
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed on $spec rc=$LASTEXITCODE" }
    }

    $srcInstaller   = Join-Path $BuildDir "dist\installer.exe"
    $srcAgent       = Join-Path $BuildDir "dist\agent.exe"
    $srcUninstaller = Join-Path $BuildDir "dist\uninstaller.exe"
    foreach ($p in @($srcInstaller, $srcAgent, $srcUninstaller)) {
        if (-not (Test-Path $p -PathType Leaf)) { throw "Missing build output: $p" }
    }

    Copy-Item -Force $srcInstaller   (Join-Path $OutputDir "DigitalTwinAgentSetup.exe")
    Copy-Item -Force $srcAgent       (Join-Path $OutputDir "agent.exe")
    Copy-Item -Force $srcUninstaller (Join-Path $OutputDir "uninstaller.exe")

    # -----------------------------------------------------------------
    # Post-build content assertion: run --self-test on the produced
    # installer.exe and demand that it emits the current fast-path
    # breadcrumb prefix. This catches the class of bug where PyInstaller
    # bundled a stale __main__.py (wrong pathex, dirty checkout,
    # __pycache__ pollution, case-mismatch on Windows) and shipped a
    # binary that hangs on --self-test.
    # -----------------------------------------------------------------
    Write-Host ""
    Write-Host "[build] --------------------------------------------------------"
    Write-Host "[build] Post-build content assertion: installer.exe --self-test"
    Write-Host "[build] --------------------------------------------------------"
    $shippedInstaller = Join-Path $OutputDir "DigitalTwinAgentSetup.exe"
    $outFile = New-TemporaryFile
    $errFile = New-TemporaryFile
    $proc = Start-Process -FilePath $shippedInstaller -ArgumentList "--self-test" -PassThru `
                          -NoNewWindow -RedirectStandardOutput $outFile -RedirectStandardError $errFile

    # NOTE on why we don't trust $proc.ExitCode blindly:
    # Start-Process -PassThru returns a System.Diagnostics.Process handle whose
    # ExitCode property is populated only when the internal Exited callback
    # has fired *before* the handle is disposed. When combined with
    # -RedirectStandardOutput / -RedirectStandardError (no -Wait), it is
    # observably common on GitHub Actions windows-latest for the timed
    # WaitForExit(ms) overload to return $true while $proc.ExitCode is still
    # $null. Throwing on `-ne 0` in that state produces the misleading
    # "returned  ." error (empty ExitCode) even though the child printed
    # exit=0 in its own breadcrumbs. The mitigation below:
    #   1. record the WaitForExit(ms) result explicitly
    #   2. call the parameterless WaitForExit() to force ExitCode caching
    #   3. fall back to Process.GetProcessById($id).ExitCode
    #   4. only fail on a *known* non-zero exit code
    $procId          = $proc.Id
    $waitedInTime    = $proc.WaitForExit(30000)
    if (-not $waitedInTime) {
        try { $proc.Kill() } catch { }
        Write-Host "[build]   diag: WaitForExit(30000)=False (still running)"
        Write-Host ("[build]   diag: HasExited      = {0}" -f $proc.HasExited)
        Write-Host ("[build]   diag: LASTEXITCODE   = {0}" -f $LASTEXITCODE)
        throw "POST-BUILD FAIL: DigitalTwinAgentSetup.exe --self-test did not exit within 30s. The frozen EXE is hung; a stale __main__.py was almost certainly packaged. Check the '[installer.spec] RESOLVED PATHS' block above."
    }

    # Force the runtime to cache ExitCode by calling the non-timeout overload.
    # This is a documented .NET workaround for Process.ExitCode returning null
    # after a timed WaitForExit succeeded.
    try { [void]$proc.WaitForExit() } catch { }

    $exitCode = $null
    try { $exitCode = $proc.ExitCode } catch { $exitCode = $null }
    if ($null -eq $exitCode) {
        try {
            $reattached = [System.Diagnostics.Process]::GetProcessById($procId)
            $exitCode   = $reattached.ExitCode
        } catch {
            # Process already reaped and gone from the table. Fall back to
            # $LASTEXITCODE if it happens to hold a value from the child.
            if ($null -ne $LASTEXITCODE) { $exitCode = $LASTEXITCODE }
        }
    }

    $stdout = Get-Content $outFile -Raw
    $stderr = Get-Content $errFile -Raw
    Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue

    Write-Host ("[build]   diag: WaitForExit(30000) = {0}" -f $waitedInTime)
    Write-Host ("[build]   diag: HasExited          = {0}" -f $proc.HasExited)
    Write-Host ("[build]   diag: proc.ExitCode raw  = '{0}'" -f $proc.ExitCode)
    Write-Host ("[build]   diag: resolved exitCode  = '{0}'" -f $exitCode)
    Write-Host ("[build]   diag: LASTEXITCODE       = '{0}'" -f $LASTEXITCODE)
    Write-Host ("[build]   --self-test exit code    = {0}" -f $exitCode)
    if ($stderr) {
        Write-Host "[build]   ----- stderr breadcrumbs -----"
        foreach ($line in ($stderr -split "`r?`n") | Where-Object { $_ }) {
            Write-Host ("[build]   {0}" -f $line)
        }
    }
    if ($stdout) {
        Write-Host "[build]   ----- stdout -----"
        foreach ($line in ($stdout -split "`r?`n") | Where-Object { $_ }) {
            Write-Host ("[build]   {0}" -f $line)
        }
    }

    # Only fail on a KNOWN non-zero exit. A null/unresolved ExitCode after a
    # successful WaitForExit is a PowerShell/Windows plumbing artifact - the
    # child already told us in its own '[installer.boot] exit=0' breadcrumb
    # whether it succeeded, so we trust the breadcrumb + exit-code combination
    # rather than punishing the build for the harness's inability to read a
    # Win32 exit status.
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        throw "POST-BUILD FAIL: --self-test returned $exitCode. See stderr above."
    }
    if ($null -eq $exitCode) {
        Write-Host "[build]   WARN: could not read ExitCode from the process handle;"
        Write-Host "[build]         relying on breadcrumb '[installer.boot] exit=0' from stderr instead."
        if (-not ($stderr -match '\[installer\.boot\][^\r\n]*exit=0')) {
            throw "POST-BUILD FAIL: --self-test ExitCode was unreadable AND stderr did not carry an '[installer.boot] exit=0' confirmation. Refusing to ship."
        }
    }
    if (-not ($stderr -match '\[installer\.boot\]')) {
        throw "POST-BUILD FAIL: --self-test did NOT emit any '[installer.boot]' breadcrumbs. The frozen EXE was built from a STALE __main__.py. Aborting."
    }
    Write-Host "[build]   OK - fast-path breadcrumbs present, self-test succeeded."
    Write-Host "[build] --------------------------------------------------------"

    Write-Host ""
    Write-Host "[build] SUCCESS."
    Write-Host "[build] Shipping artifact: $(Join-Path $OutputDir 'DigitalTwinAgentSetup.exe')"
    Get-ChildItem $OutputDir | Select-Object Name, Length | Format-Table -AutoSize
}
finally {
    Pop-Location
}
