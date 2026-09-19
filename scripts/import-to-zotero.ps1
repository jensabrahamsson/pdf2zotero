# import-to-zotero.ps1 — Convert PDFs with pdf2zotero and open the .bib in Zotero (Windows).
#
# Usage:
#   .\scripts\import-to-zotero.ps1 file.pdf [file2.pdf ...]
#   .\scripts\import-to-zotero.ps1 -Install     # SendTo shortcut "Import to Zotero"
#
# Does the same conversion as pdf2zotero.py, then opens each .bib with Zotero
# (the same File → Import path as the official docs). Still verify the PDF child.
#
# If execution policy blocks the script:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-to-zotero.ps1 paper.pdf
#
# Requires: Docker Desktop, GROBID, Zotero desktop, Python 3.9+.
# Copyright (c) 2026 Jens Abrahamsson. MIT License.

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList = @(),

    [switch]$Install,
    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Die {
    param([string]$Message)
    [Console]::Error.WriteLine("Error: $Message")
    exit 1
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Write-WarnMsg {
    param([string]$Message)
    [Console]::Error.WriteLine("[WARNING] $Message")
}

function Show-Usage {
    param([int]$ExitCode = 0)
    $lines = @(
        "import-to-zotero.ps1 — Convert PDFs and open the .bib in Zotero (Windows).",
        "",
        "Usage:",
        "  .\scripts\import-to-zotero.ps1 file.pdf [file2.pdf ...]",
        "  .\scripts\import-to-zotero.ps1 -Install",
        "",
        "Starts Docker Desktop and GROBID if needed, runs pdf2zotero.py, then opens",
        "each .bib with Zotero (File → Import). Verify the PDF child attachment.",
        "",
        "If execution policy blocks the script:",
        "  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\import-to-zotero.ps1 paper.pdf"
    )
    $lines | ForEach-Object { Write-Host $_ }
    exit $ExitCode
}

# --- parse positional / bash-style args ---
$Pdfs = New-Object System.Collections.Generic.List[string]
$i = 0
while ($i -lt $ArgsList.Count) {
    $a = $ArgsList[$i]
    if ($a -match '^(?i)(-h|--help|/h)$') {
        $Help = $true; $i++
    } elseif ($a -match '^(?i)(--install|-Install)$') {
        $Install = $true; $i++
    } elseif ($a.StartsWith("-")) {
        Die "unknown argument: $a (try -Help)"
    } else {
        $Pdfs.Add($a)
        $i++
    }
}

if ($Help) { Show-Usage 0 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Pdf2ZoteroPy = Join-Path $RepoRoot "pdf2zotero.py"
$SetupGrobid = Join-Path $ScriptDir "setup-grobid.ps1"
$ThisScript = $MyInvocation.MyCommand.Path

function Install-SendToShortcut {
    $sendTo = [Environment]::GetFolderPath("SendTo")
    if (-not $sendTo) {
        Die "Could not resolve the SendTo folder."
    }
    if (-not (Test-Path $sendTo)) {
        New-Item -ItemType Directory -Path $sendTo -Force | Out-Null
    }
    $lnkPath = Join-Path $sendTo "Import to Zotero.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($lnkPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ThisScript`""
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.WindowStyle = 1
    $shortcut.Description = "Convert PDF with pdf2zotero and open the .bib in Zotero"
    $shortcut.Save()
    Write-Step "Installed SendTo shortcut: $lnkPath"
    Write-Host "Right-click a PDF → Show more options → Send to → Import to Zotero."
}

if ($Install) {
    Install-SendToShortcut
    exit 0
}

if (-not (Test-Path $Pdf2ZoteroPy)) {
    Die "Could not find pdf2zotero.py in $RepoRoot"
}

if ($Pdfs.Count -eq 0) {
    [Console]::Error.WriteLine("Error: no PDF file given.")
    Write-Host "Usage: .\scripts\import-to-zotero.ps1 <file1.pdf> [file2.pdf ...] or -Install"
    exit 1
}

function Test-DockerDaemon {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) { return $false }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & docker info 2>&1
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    return $ok
}

function Start-DockerDesktopIfNeeded {
    Write-Step "Step 1/4: Checking Docker..."
    if (Test-DockerDaemon) {
        Write-Info "Docker is already running."
        return
    }
    Write-Info "Docker daemon not reachable. Starting Docker Desktop..."
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    )
    $desktop = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($desktop) {
        Start-Process -FilePath $desktop | Out-Null
    } else {
        Die "Docker Desktop not found. Install it, start it, then retry. See PREREQUISITES.md."
    }
    $waited = 0
    $maxWait = 90
    while (-not (Test-DockerDaemon)) {
        Start-Sleep -Seconds 2
        $waited += 2
        Write-Info "Waiting for Docker daemon... (${waited}s / ${maxWait}s)"
        if ($waited -ge $maxWait) {
            Die "Docker did not start within ${maxWait}s. Start Docker Desktop manually and retry."
        }
    }
    Write-Info "Docker Desktop is running."
}

function Test-GrobidAlive {
    $url = "http://127.0.0.1:8070/api/isalive"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $out = & curl.exe -sf --max-time 3 $url 2>$null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prev
        if ($ok -and $null -ne $out) {
            $body = ($out | Out-String).Trim()
            if ($body -match '(?i)true') { return $true }
        }
    }
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($resp.Content -match '(?i)true')
    } catch {
        return $false
    }
}

function Start-GrobidIfNeeded {
    Write-Step "Step 2/4: Checking GROBID..."
    if (Test-GrobidAlive) {
        Write-Info "GROBID is already running."
        return
    }
    Write-Info "GROBID is not answering on port 8070. Starting the container..."
    if (-not (Test-Path $SetupGrobid)) {
        Die "Missing $SetupGrobid"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupGrobid up
    if ($LASTEXITCODE -ne 0) {
        Die "setup-grobid.ps1 up failed."
    }
    if (-not (Test-GrobidAlive)) {
        Die "GROBID did not become ready at http://127.0.0.1:8070."
    }
    Write-Info "GROBID is up."
}

function Get-ZoteroExe {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Zotero\zotero.exe"),
        (Join-Path $env:ProgramFiles "Zotero\zotero.exe")
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} "Zotero\zotero.exe")
    }
    foreach ($p in $candidates) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    $cmd = Get-Command zotero.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Open-Zotero {
    param([string]$BibPath)
    $zotero = Get-ZoteroExe
    if ($zotero) {
        if ($BibPath) {
            Start-Process -FilePath $zotero -ArgumentList $BibPath | Out-Null
        } else {
            Start-Process -FilePath $zotero | Out-Null
        }
        return $true
    }
    if ($BibPath) {
        Write-WarnMsg "Zotero.exe not found; opening the .bib with the default app. Prefer File → Import… in Zotero."
        Start-Process -FilePath $BibPath | Out-Null
        return $false
    }
    Write-WarnMsg "Zotero.exe not found. Open Zotero yourself, then File → Import… the .bib."
    return $false
}

function Resolve-PythonInvocation {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prev
        if ($ok) { return @{ Exe = "py"; Prefix = @("-3") } }
    }
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $name -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prev
        if ($ok) { return @{ Exe = $name; Prefix = @() } }
    }
    Die "Python 3.9+ not found. Install from python.org and enable 'Add python.exe to PATH'."
}

function Invoke-Pdf2Zotero {
    param([string]$PdfPath)
    $py = Resolve-PythonInvocation
    $argv = @()
    if ($py.Prefix.Count -gt 0) { $argv += $py.Prefix }
    $argv += @($Pdf2ZoteroPy, $PdfPath)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $py.Exe @argv
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return $code
}

# --- main flow ---
Start-DockerDesktopIfNeeded
Start-GrobidIfNeeded

Write-Step "Step 3/4: Opening Zotero..."
Open-Zotero | Out-Null

Write-Step "Step 4/4: Converting and importing files..."
$failed = 0
foreach ($raw in $Pdfs) {
    if (-not (Test-Path -LiteralPath $raw -PathType Leaf)) {
        Write-WarnMsg "File not found: $raw"
        $failed++
        continue
    }
    $pdfAbs = (Resolve-Path -LiteralPath $raw).Path
    $ext = [System.IO.Path]::GetExtension($pdfAbs)
    if ($ext.ToLowerInvariant() -ne ".pdf") {
        Write-WarnMsg "Not a PDF: $pdfAbs"
        $failed++
        continue
    }
    $baseName = [System.IO.Path]::GetFileName($pdfAbs)
    Write-Info "Processing: $baseName"
    $code = Invoke-Pdf2Zotero -PdfPath $pdfAbs
    $bibFile = [System.IO.Path]::ChangeExtension($pdfAbs, ".bib")
    if ($code -ne 0) {
        Write-WarnMsg "pdf2zotero failed for $baseName"
        $failed++
        continue
    }
    if (-not (Test-Path -LiteralPath $bibFile)) {
        Write-WarnMsg "Could not find generated BibTeX for $baseName"
        $failed++
        continue
    }
    Write-Info "Opening $bibFile in Zotero..."
    Open-Zotero -BibPath $bibFile | Out-Null
    Write-Step "Done. Import '$baseName' and confirm the PDF child attachment."
}

if ($failed -gt 0) {
    exit 1
}
exit 0
