<#
.SYNOPSIS
    KinJo - First-time local setup (Windows PowerShell)

.DESCRIPTION
    Run once from the project root:
        .\reqMd\scripts\setup-local.ps1

    What it does:
        1. Checks prerequisites (Python, Docker)
        2. Creates .venv and installs dependencies
        3. Generates .env.local with a real SECRET_KEY
        4. Creates required data/ and logs/ directories
        5. Copies docker-compose.local.yml to the project root
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ReqMdDir    = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ReqMdDir

# Fallback when running directly from reqMd/scripts
if (-not (Test-Path "$ProjectRoot\main.py")) {
    $ProjectRoot = (Get-Location).Path
}

Push-Location $ProjectRoot

function Write-Step { param($n, $m) Write-Host "`n--- $n  $m" -ForegroundColor Cyan }
function Write-Info { param($m) Write-Host "   [ok]  $m" -ForegroundColor Green  }
function Write-Warn { param($m) Write-Host "   [!]   $m" -ForegroundColor Yellow }

# --- 1. Prerequisites --------------------------------------------------------
Write-Step "1/6" "Check prerequisites"

foreach ($cmd in @('python','docker')) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { Write-Info "$cmd found: $($found.Source)" }
    else         { Write-Warn "$cmd NOT found (required)" }
}

# --- 2. Virtual environment --------------------------------------------------
Write-Step "2/6" "Create virtual environment"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Info ".venv created"
} else {
    Write-Info ".venv already exists"
}
& ".venv\Scripts\Activate.ps1"

# --- 3. Dependencies ---------------------------------------------------------
Write-Step "3/6" "Install dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
Write-Info "Dependencies installed"

# --- 4. .env.local -----------------------------------------------------------
Write-Step "4/6" "Create .env.local"
if (-not (Test-Path ".env.local")) {
    $exampleSrc = Join-Path $ReqMdDir ".env.local.example"
    if (Test-Path $exampleSrc) {
        Copy-Item $exampleSrc ".env.local"
    } else {
        Copy-Item ".env.local.example" ".env.local"
    }
    # Generate a real SECRET_KEY
    $sk = python -c "import secrets; print(secrets.token_hex(32))"
    (Get-Content ".env.local") -replace 'local-dev-secret-key-change-before-any-public-deployment', $sk |
        Set-Content ".env.local"
    Write-Info ".env.local created with a fresh SECRET_KEY"
} else {
    Write-Info ".env.local already exists - skipping"
}

# --- 5. Data directories -----------------------------------------------------
Write-Step "5/6" "Create required directories"
foreach ($dir in @('data\attachments','data\uploads','logs')) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
}
Write-Info "data/ and logs/ directories ready"

# --- 6. Copy docker-compose override -----------------------------------------
Write-Step "6/6" "Copy docker-compose.local.yml to project root"
$srcCompose = Join-Path $ReqMdDir "docker-compose.local.yml"
if (-not (Test-Path "docker-compose.local.yml")) {
    if (Test-Path $srcCompose) {
        Copy-Item $srcCompose "."
        Write-Info "docker-compose.local.yml copied"
    } else {
        Write-Warn "docker-compose.local.yml not found in reqMd - skipping"
    }
} else {
    Write-Info "docker-compose.local.yml already in project root - skipping"
}

Write-Host ""
Write-Info "Setup complete. Next steps:"
Write-Host "   1. Review .env.local"
Write-Host "   2. .\reqMd\run-local.ps1"
Write-Host "      or: docker compose -f docker-compose.yml -f docker-compose.local.yml up"

Pop-Location