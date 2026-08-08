# setup-grobid.ps1 — start or remove the GROBID Docker service for pdf2zotero (Windows).
#
# Default image matches PREREQUISITES.md / GROBID Docker guide:
#   grobid/grobid:0.9.0-crf  (use -Full for 0.9.0-full)
#
# Usage:
#   .\scripts\setup-grobid.ps1              # start (pull + run + wait until alive)
#   .\scripts\setup-grobid.ps1 up
#   .\scripts\setup-grobid.ps1 up -Full
#   .\scripts\setup-grobid.ps1 status
#   .\scripts\setup-grobid.ps1 down         # stop/remove container only
#   .\scripts\setup-grobid.ps1 purge        # stop container + delete GROBID images
#
# If execution policy blocks the script, run via:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-grobid.ps1 up
# Explicit -Image / --image wins over -Full / -Crf when both are set.
#
# Requires: Docker Desktop (daemon running). Does not auto-start Colima.
# Copyright (c) 2026 Jens Abrahamsson. MIT License.

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList = @(),

    [switch]$Full,
    [switch]$Crf,

    [string]$Port,
    [string]$Name,
    [string]$Image,

    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Die {
    param([string]$Message)
    [Console]::Error.WriteLine("Error: $Message")
    exit 1
}

function Show-Usage {
    param([int]$ExitCode = 0)
    $lines = @(
        "setup-grobid.ps1 — start or remove the GROBID Docker service for pdf2zotero (Windows).",
        "",
        "Default image matches PREREQUISITES.md / GROBID Docker guide:",
        "  grobid/grobid:0.9.0-crf  (use -Full for 0.9.0-full)",
        "",
        "Usage:",
        "  .\scripts\setup-grobid.ps1              # start (pull + run + wait until alive)",
        "  .\scripts\setup-grobid.ps1 up",
        "  .\scripts\setup-grobid.ps1 up -Full",
        "  .\scripts\setup-grobid.ps1 status",
        "  .\scripts\setup-grobid.ps1 down         # stop/remove container only",
        "  .\scripts\setup-grobid.ps1 purge        # stop container + delete GROBID images",
        "",
        "Aliases: start/setup → up; stop → down; remove/clean → purge",
        "Flags:   -Full / --full, -Crf / --crf; -Port / --port N; -Name / --name; -Image / --image",
        "Note:    Explicit -Image / --image wins over -Full / -Crf when both are set.",
        "",
        "If execution policy blocks the script:",
        "  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-grobid.ps1 up",
        "",
        "Requires: Docker Desktop (daemon running). Does not auto-start Colima."
    )
    $lines | ForEach-Object { Write-Host $_ }
    exit $ExitCode
}

# --- parse positional / bash-style args (up --full, --port 8070, etc.) ---
# Note: do not use break/continue inside switch-in-while (break would exit the loop).
$Command = "up"
$i = 0
while ($i -lt $ArgsList.Count) {
    $a = $ArgsList[$i]
    if ($a -match '^(?i)(-h|--help|/h)$') {
        $Help = $true; $i++
    } elseif ($a -match '^(?i)(up|start|setup)$') {
        $Command = "up"; $i++
    } elseif ($a -match '^(?i)(down|stop)$') {
        $Command = "down"; $i++
    } elseif ($a -match '^(?i)(purge|remove|clean)$') {
        $Command = "purge"; $i++
    } elseif ($a -match '^(?i)status$') {
        $Command = "status"; $i++
    } elseif ($a -match '^(?i)(--full|-Full)$') {
        $Full = $true; $i++
    } elseif ($a -match '^(?i)(--crf|-Crf)$') {
        $Crf = $true; $i++
    } elseif ($a -match '^(?i)(--port|-Port)$') {
        if ($i + 1 -ge $ArgsList.Count) { Die "missing value for $a" }
        $Port = $ArgsList[$i + 1]; $i += 2
    } elseif ($a -match '^(?i)(--name|-Name)$') {
        if ($i + 1 -ge $ArgsList.Count) { Die "missing value for $a" }
        $Name = $ArgsList[$i + 1]; $i += 2
    } elseif ($a -match '^(?i)(--image|-Image)$') {
        if ($i + 1 -ge $ArgsList.Count) { Die "missing value for $a" }
        $Image = $ArgsList[$i + 1]; $i += 2
    } else {
        Die "unknown argument: $a (try -Help)"
    }
}

if ($Help) { Show-Usage 0 }

# --- defaults (env overrides, then param / flag overrides) ---
if (-not $Name) {
    if ($env:GROBID_NAME) { $Name = $env:GROBID_NAME } else { $Name = "grobid" }
}
if (-not $Port) {
    if ($env:GROBID_PORT) { $Port = $env:GROBID_PORT } else { $Port = "8070" }
}

$ImageCrf = "grobid/grobid:0.9.0-crf"
$ImageFull = "grobid/grobid:0.9.0-full"
# Explicit -Image / --image wins over -Full / -Crf (resolved only when Image unset).
if (-not $Image) {
    if ($Full) { $Image = $ImageFull }
    elseif ($Crf) { $Image = $ImageCrf }
    else { $Image = $ImageCrf }
}

$WaitAttempts = 36
if ($env:GROBID_WAIT_ATTEMPTS) {
    $parsedWait = 0
    if (-not [int]::TryParse($env:GROBID_WAIT_ATTEMPTS, [ref]$parsedWait)) {
        Die "GROBID_WAIT_ATTEMPTS must be an integer (got: $($env:GROBID_WAIT_ATTEMPTS))"
    }
    $WaitAttempts = $parsedWait
}
$WaitSleep = 5

function Test-DockerAvailable {
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        Die "docker not found on PATH. Install Docker Desktop and ensure docker is on PATH."
    }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & docker info 2>&1
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $ok) {
        Die "Docker daemon not reachable. Start Docker Desktop, wait until it is running, then retry."
    }
}

function Test-GrobidAlive {
    $url = "http://127.0.0.1:${Port}/api/isalive"
    $body = $null

    # Prefer curl.exe when available (matches bash behaviour more closely)
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $out = & curl.exe -sf --max-time 3 $url 2>$null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prev
        if ($ok -and $null -ne $out) {
            $body = ($out | Out-String).Trim()
        }
    }

    if ($null -eq $body) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            $body = $resp.Content
        } catch {
            return $false
        }
    }

    if (-not $body) { return $false }
    return ($body -match '(?i)true')
}

function Get-HttpText {
    param([string]$Url)
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $out = & curl.exe -s --max-time 5 $Url 2>$null
        $ErrorActionPreference = $prev
        if ($LASTEXITCODE -eq 0 -and $null -ne $out) {
            return ($out | Out-String).Trim()
        }
    }
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $resp.Content
    } catch {
        return $null
    }
}

function Test-ContainerExists {
    param([string]$ContainerName)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $names = & docker ps -a --format '{{.Names}}' 2>$null
    $ErrorActionPreference = $prev
    if (-not $names) { return $false }
    foreach ($n in ($names | ForEach-Object { "$_".Trim() })) {
        if ($n -eq $ContainerName) { return $true }
    }
    return $false
}

function Invoke-Status {
    Test-DockerAvailable
    Write-Host "Container '${Name}':"
    if (Test-ContainerExists -ContainerName $Name) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker ps -a --filter "name=^/${Name}$" --format '  {{.Status}}  image={{.Image}}  ports={{.Ports}}'
        $ErrorActionPreference = $prev
    } else {
        Write-Host "  (not present)"
    }

    Write-Host -NoNewline "HTTP :${Port}/api/isalive → "
    if (Test-GrobidAlive) {
        $alive = Get-HttpText -Url "http://127.0.0.1:${Port}/api/isalive"
        Write-Host $alive
        Write-Host -NoNewline "version → "
        $ver = Get-HttpText -Url "http://127.0.0.1:${Port}/api/version"
        if ($ver) { Write-Host $ver } else { Write-Host "" }
    } else {
        Write-Host "not reachable"
    }

    Write-Host "GROBID-related images:"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $imgs = & docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' 2>$null
    $ErrorActionPreference = $prev
    $matched = @()
    if ($imgs) {
        $matched = @($imgs | Where-Object { $_ -match '(?i)grobid|lfoppiano' })
    }
    if ($matched.Count -eq 0) {
        Write-Host "  (none)"
    } else {
        $matched | ForEach-Object { Write-Host "  $_" }
    }
}

function Invoke-Up {
    Test-DockerAvailable
    Write-Host "Using image: $Image"
    Write-Host "Pulling (first time can be large)…"
    & docker pull $Image
    if ($LASTEXITCODE -ne 0) { Die "docker pull failed for $Image" }

    if (Test-ContainerExists -ContainerName $Name) {
        Write-Host "Removing existing container '${Name}'…"
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $null = & docker rm -f $Name
        $ErrorActionPreference = $prev
    }

    Write-Host "Starting named container '${Name}' on port ${Port}…"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $null = & docker run -d --name $Name --init --ulimit core=0 -p "${Port}:8070" $Image
    $runOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    if (-not $runOk) { Die "docker run failed for container '${Name}'" }

    $maxSec = $WaitAttempts * $WaitSleep
    Write-Host "Waiting for GROBID to become alive (up to ~${maxSec}s)…"
    for ($j = 1; $j -le $WaitAttempts; $j++) {
        if (Test-GrobidAlive) {
            Write-Host "GROBID is up: http://127.0.0.1:${Port}/api/isalive"
            $ver = Get-HttpText -Url "http://127.0.0.1:${Port}/api/version"
            if ($ver) { Write-Host $ver }
            return
        }
        Write-Host ("  attempt {0}/{1}…" -f $j, $WaitAttempts)
        Start-Sleep -Seconds $WaitSleep
    }

    Write-Host "Timed out waiting for GROBID. Recent logs:"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker logs --tail 40 $Name 2>&1 | ForEach-Object { [Console]::Error.WriteLine("$_") }
    $ErrorActionPreference = $prev
    Die "GROBID did not become ready"
}

function Invoke-Down {
    Test-DockerAvailable
    if (Test-ContainerExists -ContainerName $Name) {
        & docker rm -f $Name
        Write-Host "Removed container '${Name}'."
    } else {
        Write-Host "Container '${Name}' not present."
    }
}

function Invoke-Purge {
    Invoke-Down
    Write-Host "Removing GROBID Docker images…"

    $known = @(
        $ImageCrf
        $ImageFull
        "grobid/grobid-crf:0.8.0"
        "grobid/grobid:0.8.2"
        "lfoppiano/grobid:0.8.1"
    )

    foreach ($id in $known) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $null = & docker image inspect $id 2>&1
        $exists = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prev
        if ($exists) {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & docker rmi $id
            $removed = ($LASTEXITCODE -eq 0)
            $ErrorActionPreference = $prev
            if ($removed) {
                Write-Host "  removed $id"
            } else {
                Write-Host "  could not remove $id (in use?)"
            }
        }
    }

    # Any other grobid-related tags (including leftovers not in the known list)
    # Force array: a single docker output line is a [string]; foreach would iterate chars.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $all = @(& docker images --format '{{.Repository}} {{.Tag}}' 2>$null)
    $ErrorActionPreference = $prev
    if ($all.Count -gt 0) {
        foreach ($line in $all) {
            $parts = ($line -split '\s+', 2)
            if ($parts.Count -lt 2) { continue }
            $repo = $parts[0]
            $tag = $parts[1]
            if ($repo -notmatch '(?i)grobid|lfoppiano') { continue }
            $ref = "${repo}:${tag}"
            if ($tag -eq "<none>") {
                $prev = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                $qid = (& docker images -q $repo | Select-Object -First 1)
                $ErrorActionPreference = $prev
                if (-not $qid) { continue }
                $ref = "$qid"
            }
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $null = & docker rmi $ref 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  removed $ref"
            }
            $ErrorActionPreference = $prev
        }
    }

    Write-Host "Done. Disk (docker system df):"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker system df 2>$null
    $ErrorActionPreference = $prev
    Write-Host ""
    Write-Host "To start GROBID again later:"
    Write-Host "  .\scripts\setup-grobid.ps1 up"
}

# --- dispatch ---
# Command already normalized to up|down|purge|status (aliases mapped above)
switch ($Command.ToLowerInvariant()) {
    "up" { Invoke-Up }
    "down" { Invoke-Down }
    "purge" { Invoke-Purge }
    "status" { Invoke-Status }
    default { Die "unknown argument: $Command (try -Help)" }
}
