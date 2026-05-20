[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$HostName = "127.0.0.1",
    [switch]$SkipInstall,
    [switch]$SkipChecks,
    [switch]$SkipSeed,
    [switch]$ResetDatabase,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Ensure-VirtualEnv {
    $pythonPath = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $pythonPath) {
        return $pythonPath
    }

    Write-Step "Creating Python virtual environment"
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv .venv
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    else {
        throw "Python 3.11 or newer is required, but Python was not found on PATH."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python virtual environment."
    }

    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Virtual environment was not created at .venv."
    }
    return $pythonPath
}

function Ensure-PythonVersion {
    param([string]$Python)
    & $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 or newer is required."
    }
    Write-Ok "Python version is 3.11 or newer"
}

function Test-PythonDependencies {
    param([string]$Python)
    & $Python -c "import fastapi, uvicorn, sqlalchemy, jinja2, pydantic_settings" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-Dependencies {
    param([string]$Python)
    if (Test-PythonDependencies -Python $Python) {
        Write-Ok "Python dependencies are installed"
        return
    }

    if ($SkipInstall) {
        throw "Python dependencies are missing. Re-run without -SkipInstall."
    }

    Write-Step "Installing Python dependencies"
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements.txt."
    }
    Write-Ok "Python dependencies installed"
}

function Ensure-LocalEnv {
    $envPath = Join-Path $Root ".env"
    if (Test-Path -LiteralPath $envPath) {
        Write-Ok ".env exists"
        return
    }

    Write-Step "Creating local .env"
    $secret = & $script:Python -c "import secrets; print(secrets.token_hex(32))"
    @"
DATABASE_URL=sqlite:///./data/kinjo_dev.db
SECRET_KEY=$secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER=10080
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_STORAGE_URI=memory://
APP_NAME=KinJo
ENVIRONMENT=development
DEBUG=True
TESTING=true
DEFAULT_LANGUAGE=ar
SUPPORTED_LANGUAGES=["ar","en"]
CORS_ALLOWED_ORIGINS=["http://localhost:$Port","http://127.0.0.1:$Port"]
TRUSTED_HOSTS=["127.0.0.1","localhost","testserver"]
API_DOCS_ENABLED=True
"@ | Set-Content -Path $envPath -Encoding UTF8
    Write-Ok "Created .env for local SQLite"
}

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch "^\s*([^#=]+?)\s*=\s*(.*)\s*$") {
            continue
        }

        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Get-SqlitePath {
    param([string]$DatabaseUrl)
    if (-not $DatabaseUrl -or $DatabaseUrl -notmatch "^sqlite:///") {
        return $null
    }

    $rawPath = $DatabaseUrl -replace "^sqlite:///", ""
    if ($rawPath -eq ":memory:") {
        return $null
    }

    if ([System.IO.Path]::IsPathRooted($rawPath)) {
        return [System.IO.Path]::GetFullPath($rawPath)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $Root $rawPath))
}

function Reset-LocalDatabaseIfRequested {
    if (-not $ResetDatabase) {
        return
    }

    $dbPath = Get-SqlitePath -DatabaseUrl $env:DATABASE_URL
    if (-not $dbPath) {
        throw "-ResetDatabase only supports local SQLite DATABASE_URL values."
    }

    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
    $rootPrefix = "$rootFull\"
    if (-not $dbPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete SQLite database outside the project folder: $dbPath"
    }

    Write-Step "Resetting local SQLite database"
    foreach ($path in @($dbPath, "$dbPath-wal", "$dbPath-shm", "$dbPath-journal")) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    Write-Ok "Local SQLite database reset"
}

function Initialize-Database {
    param([string]$Python)
    Write-Step "Initializing local database"
    & $Python -c "from database import init_db; init_db(); print('Database initialized')"
    if ($LASTEXITCODE -ne 0) {
        throw "Database initialization failed."
    }
}

function Seed-Database {
    param([string]$Python)
    if ($SkipSeed) {
        Write-Ok "Skipped demo data seed"
        return
    }

    Write-Step "Seeding demo data"
    & $Python seed_local.py
    if ($LASTEXITCODE -ne 0) {
        throw "Demo data seed failed. If this is an old local SQLite database, re-run with -ResetDatabase."
    }
}

function Run-ProjectChecks {
    param([string]$Python)
    if ($SkipChecks) {
        Write-Ok "Skipped project checks"
        return
    }

    Write-Step "Running backend/frontend smoke checks"
    & $Python -c "import main; print('FastAPI app import OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "FastAPI app import check failed."
    }
    & $Python -m pytest tests\test_frontend_integration.py -q
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend integration checks failed."
    }
}

function Test-PortInUse {
    param([int]$LocalPort)
    try {
        $connections = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
        return [bool]$connections
    }
    catch {
        return $false
    }
}

function Get-AvailablePort {
    param([int]$RequestedPort)
    for ($candidate = $RequestedPort; $candidate -le ($RequestedPort + 20); $candidate++) {
        if (-not (Test-PortInUse -LocalPort $candidate)) {
            if ($candidate -ne $RequestedPort) {
                Write-Host "Port $RequestedPort is in use; using $candidate instead." -ForegroundColor Yellow
            }
            return $candidate
        }
    }
    throw "No available port found from $RequestedPort to $($RequestedPort + 20)."
}

function Start-BrowserOpener {
    param([string]$BaseUrl)
    if ($NoBrowser) {
        return
    }

    Start-Job -ScriptBlock {
        param([string]$TargetUrl)
        $healthUrl = "$TargetUrl/health"
        for ($i = 0; $i -lt 60; $i++) {
            try {
                $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
                if ($response.StatusCode -eq 200) {
                    Start-Process $TargetUrl
                    return
                }
            }
            catch {
                Start-Sleep -Seconds 1
            }
        }
        Start-Process $TargetUrl
    } -ArgumentList $BaseUrl | Out-Null
}

Ensure-Directory (Join-Path $Root "data")
Ensure-Directory (Join-Path $Root "logs")
Ensure-Directory (Join-Path $Root "data\attachments")
Ensure-Directory (Join-Path $Root "data\uploads")

$script:Python = Ensure-VirtualEnv
Ensure-PythonVersion -Python $script:Python
Ensure-Dependencies -Python $script:Python
Ensure-LocalEnv
Import-DotEnv -Path (Join-Path $Root ".env")

if (-not $env:DATABASE_URL) {
    throw "DATABASE_URL is not configured."
}
if (-not $env:SECRET_KEY) {
    throw "SECRET_KEY is not configured."
}

Reset-LocalDatabaseIfRequested
Initialize-Database -Python $script:Python
Seed-Database -Python $script:Python
Run-ProjectChecks -Python $script:Python

$Port = Get-AvailablePort -RequestedPort $Port
$BaseUrl = "http://$HostName`:$Port"
Write-Step "Starting KinJo locally"
Write-Host "Frontend and backend: $BaseUrl"
Write-Host "Health check:         $BaseUrl/health"
Write-Host "API docs:             $BaseUrl/docs"
Write-Host ""
Write-Host "Demo users:"
Write-Host "  admin       / Admin@1234"
Write-Host "  manager1    / Manager@1234"
Write-Host "  supervisor1 / Super@1234"
Write-Host "  parent1     / Parent@1234"
Write-Host ""
Write-Host "Press Ctrl+C to stop the server."

Start-BrowserOpener -BaseUrl $BaseUrl
& $script:Python -m uvicorn main:app --host $HostName --port $Port --reload
