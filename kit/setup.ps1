# Job search workspace: one-time setup. Safe to run again; it only installs what is missing.
# Installs (current user only, no admin): Python 3.12 and Git through winget if missing, then four small Python
# packages (typst, python-docx, pypdf, keyring). Registers the morning sweep (asks first). Then checks everything
# with engine\doctor.py.
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

function Say($tag, $msg) {
    $color = @{ "OK" = "Green"; "INSTALLED" = "Cyan"; "ACTION NEEDED" = "Yellow"; "..." = "Gray" }[$tag]
    Write-Host ("{0,-14} {1}" -f $tag, $msg) -ForegroundColor $color
}
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
}
function Find-Python {
    $candidates = @()
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*") { $candidates += $cmd.Source }
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { return $c }
        }
    }
    return $null
}

Write-Host ""
Write-Host "Setting up the job search workspace in: $Here"
Write-Host ""

# 1. winget
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Say "ACTION NEEDED" "winget is missing. Install 'App Installer' from the Microsoft Store, then run setup.cmd again."
    exit 1
}
Say "OK" "winget"

# 2. Python
$py = Find-Python
if (-not $py) {
    Say "..." "installing Python 3.12 (about 30 MB)"
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements `
        --override "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0"
    Refresh-Path
    $py = Find-Python
    if (-not $py) { Say "ACTION NEEDED" "Python didn't install. Restart the computer and run setup.cmd again."; exit 1 }
    Say "INSTALLED" "Python ($py)"
} else { Say "OK" "Python ($py)" }

# 3. Git (keeps the history of your profile; Claude's Code tab uses it too)
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Say "..." "installing Git"
    winget install -e --id Git.Git --scope user --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Say "ACTION NEEDED" "Git didn't install. Restart the computer and run setup.cmd again."; exit 1 }
    Say "INSTALLED" "Git"
} else { Say "OK" "Git" }

# 4. Python packages
& $py -c "import typst, docx, pypdf, keyring" 2>$null
if ($LASTEXITCODE -ne 0) {
    Say "..." "installing Python packages: typst, python-docx, pypdf, keyring (about 25 MB)"
    & $py -m pip install --user --disable-pip-version-check -q -r (Join-Path $Here "engine\requirements.txt")
    if ($LASTEXITCODE -ne 0) { Say "ACTION NEEDED" "the Python packages didn't install. Check the internet connection and run setup.cmd again."; exit 1 }
    Say "INSTALLED" "Python packages"
} else { Say "OK" "Python packages" }

# 5. Folders, history, and a full check
foreach ($d in "profile", "data", "inbox", "archive", "Resumes") { New-Item -ItemType Directory -Force (Join-Path $Here $d) | Out-Null }
$env:FOUNDRY_HOME = $Here
& $py (Join-Path $Here "engine\backup.py") init
& $py (Join-Path $Here "engine\upgrade.py")

# 6. The morning sweep (Task Scheduler, this user only)
& $py (Join-Path $Here "engine\schedule.py") status *> $null
if ($LASTEXITCODE -eq 0) {
    & $py (Join-Path $Here "engine\schedule.py") on | Out-Null
    Say "OK" "morning sweep (every day at 08:30)"
} else {
    $answer = Read-Host "Read the careers sites and job alerts every morning at 08:30 by itself? [Y/n]"
    if ($answer -notmatch '^(n|no)$') {
        & $py (Join-Path $Here "engine\schedule.py") on
        if ($LASTEXITCODE -eq 0) { Say "INSTALLED" "morning sweep (every day at 08:30)" } else { Say "ACTION NEEDED" "the morning sweep didn't register; /sweep still works by hand" }
    } else { Say "OK" "morning sweep off (turn it on later: run setup.cmd again)" }
}
# 7. OpenCode (the app to use until Claude Pro): install, the OpenRouter key, a desktop shortcut
$useOc = Read-Host "Use OpenCode with an OpenRouter key (answer n for Claude Code only)? [Y/n]"
if ($useOc -notmatch '^(n|no)$') {
    $oc = Get-Command opencode -ErrorAction SilentlyContinue
    if (-not $oc -and -not (Test-Path (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\opencode.exe"))) {
        Say "..." "installing OpenCode"
        winget install -e --id SST.opencode --scope user --silent --accept-source-agreements --accept-package-agreements
        Refresh-Path
    }
    if ((Get-Command opencode -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\opencode.exe"))) { Say "OK" "OpenCode" }
    else { Say "ACTION NEEDED" "OpenCode didn't install. Restart the computer and run setup.cmd again." }
    & $py (Join-Path $Here "engine\opencode_app.py") status *> $null
    if ($LASTEXITCODE -ne 0) { & $py (Join-Path $Here "engine\opencode_app.py") key }
    if ($LASTEXITCODE -eq 0) { Say "OK" "OpenRouter key (kept in Windows Credential Manager)" } else { Say "ACTION NEEDED" "the OpenRouter key isn't set: run setup.cmd again and paste it" }
    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop "Job search (OpenCode).lnk"))
    $lnk.TargetPath = Join-Path $Here "OpenCode.cmd"
    $lnk.WorkingDirectory = $Here
    $lnk.Description = "Open the job search folder in OpenCode"
    $lnk.Save()
    Say "OK" "desktop shortcut: Job search (OpenCode)"
}

Write-Host ""
& $py (Join-Path $Here "engine\doctor.py")
$ok = $LASTEXITCODE -eq 0
Write-Host ""
if ($ok) {
    Write-Host "Done. Double-click 'Job search (OpenCode)' on the desktop (or open this folder in Claude, Code tab) and type /start" -ForegroundColor Green
    Write-Host "Optional, any time: Gmail setup.cmd (read the Job Alerts label) and API keys.cmd (job-search APIs)."
} else {
    Write-Host "Almost done: fix the ACTION NEEDED lines above, then run setup.cmd again." -ForegroundColor Yellow
}
