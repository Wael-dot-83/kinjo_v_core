@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title KinJo - Local Production Launcher
color 0A

echo ============================================================
echo    KinJo - Local Production Bootstrap ^& Run
echo    %date% %time%
echo ============================================================
echo.

rem ---------------------------------------------------------------------------
rem Resolve project directory dynamically from this script location.
rem Run1.bat lives under: PROJECT\Runmyself\Run1.bat
rem ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo [FAIL] Cannot navigate to project directory: %PROJECT_DIR%
    pause
    exit /b 1
)
echo [OK] Working directory: %PROJECT_DIR%
echo.

rem ---------------------------------------------------------------------------
rem Configuration
rem ---------------------------------------------------------------------------
set "HOST=0.0.0.0"
set "PORT="
set "PORT_CANDIDATES=8000 8001 8010 8080"
set "WORKERS=2"
set "VENV_DIR=%PROJECT_DIR%\.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" if exist "%PROJECT_DIR%\venv\Scripts\python.exe" set "VENV_DIR=%PROJECT_DIR%\venv"

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"

set "DEFAULT_DOCKER_DB_URL=postgresql+psycopg2://kinjo:kinjo_password@localhost:5432/kinjo_db"
set "DEFAULT_SQLITE_URL=sqlite:///./data/kinjo.db"
set "RUNTIME_DB_URL="
set "NEEDS_DOCKER=0"
set "COMPOSE_CMD="

rem ---------------------------------------------------------------------------
rem Resolve an available app port to avoid conflicts with other local projects
rem ---------------------------------------------------------------------------
for %%P in (%PORT_CANDIDATES%) do (
    netstat -ano | findstr /C:":%%P" | findstr /C:"LISTENING" >nul
    if errorlevel 1 if not defined PORT set "PORT=%%P"
)

if not defined PORT (
    set "PORT=8000"
    echo [WARN] Could not auto-detect free port; falling back to %PORT%.
) else (
    echo [OK] Selected available app port: %PORT%
)
echo.

rem ---------------------------------------------------------------------------
rem [1/9] Check Python and virtual environment
rem ---------------------------------------------------------------------------
echo [1/9] Checking Python and virtual environment...
where python >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Python is not installed or not available in PATH.
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment at "%VENV_DIR%"...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [FAIL] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

if not exist "%PYTHON_EXE%" (
    echo [FAIL] Virtual environment Python executable not found: %PYTHON_EXE%
    pause
    exit /b 1
)
echo [OK] Virtual environment ready: %VENV_DIR%
echo.

rem ---------------------------------------------------------------------------
rem [2/9] Install runtime dependencies
rem ---------------------------------------------------------------------------
echo [2/9] Installing Python dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [FAIL] Failed to bootstrap pip tooling.
    pause
    exit /b 1
)

if exist "requirements.txt" (
    "%PIP_EXE%" install -r requirements.txt
    if errorlevel 1 (
        echo [FAIL] Failed to install requirements.txt
        pause
        exit /b 1
    )
    echo [OK] Runtime dependencies installed.
) else (
    echo [FAIL] requirements.txt not found.
    pause
    exit /b 1
)
echo.

rem ---------------------------------------------------------------------------
rem [3/9] Ensure .env exists
rem ---------------------------------------------------------------------------
echo [3/9] Checking .env...
if exist ".env" goto :env_exists
if exist ".env.example" goto :env_copy
> ".env" echo DATABASE_URL=%DEFAULT_SQLITE_URL%
>> ".env" echo SECRET_KEY=local-dev-secret-change-me
>> ".env" echo ENVIRONMENT=production
>> ".env" echo DEBUG=False
>> ".env" echo REDIS_URL=redis://localhost:6379/0
echo [WARN] Created minimal .env (SQLite local fallback).
goto :env_done

:env_copy
copy ".env.example" ".env" >nul
echo [WARN] Created .env from .env.example.
goto :env_done

:env_exists
echo [OK] .env already exists.

:env_done
echo.

rem ---------------------------------------------------------------------------
rem [4/9] Ensure data folders
rem ---------------------------------------------------------------------------
echo [4/9] Ensuring data folders...
if not exist "data" mkdir "data"
if not exist "data\attachments" mkdir "data\attachments"
if not exist "data\uploads" mkdir "data\uploads"
if not exist "data\backups" mkdir "data\backups"
echo [OK] Data folders ready.
echo.

rem ---------------------------------------------------------------------------
rem [5/9] Decide DB mode (SQLite vs PostgreSQL + Docker)
rem ---------------------------------------------------------------------------
echo [5/9] Resolving database mode...
for /f "tokens=1,* delims==" %%A in ('findstr /R /B /C:"DATABASE_URL=" ".env"') do set "ENV_DB_URL=%%B"

if defined ENV_DB_URL (
    set "RUNTIME_DB_URL=!ENV_DB_URL!"
) else (
    set "RUNTIME_DB_URL=%DEFAULT_DOCKER_DB_URL%"
)

echo !RUNTIME_DB_URL! | findstr /I "sqlite" >nul
if errorlevel 1 (
    set "NEEDS_DOCKER=1"
    set "RUNTIME_DB_URL=%DEFAULT_DOCKER_DB_URL%"
) else (
    set "NEEDS_DOCKER=0"
)

if "!NEEDS_DOCKER!"=="1" (
    echo [INFO] PostgreSQL mode detected. Docker services will be started.
) else (
    echo [INFO] SQLite mode detected. Docker services are not required.
)
echo.

rem ---------------------------------------------------------------------------
rem [6/9] Start Docker services if needed
rem ---------------------------------------------------------------------------
if "!NEEDS_DOCKER!" NEQ "1" goto :docker_skip
echo [6/9] Starting Docker services (db, redis)...

docker compose version >nul 2>nul
if not errorlevel 1 set "COMPOSE_CMD=docker compose"
if defined COMPOSE_CMD goto :docker_cmd_ready

where docker-compose >nul 2>nul
if not errorlevel 1 set "COMPOSE_CMD=docker-compose"

:docker_cmd_ready
if not defined COMPOSE_CMD (
    echo [FAIL] Docker Compose not found. Install Docker Desktop or switch DATABASE_URL to SQLite.
    pause
    exit /b 1
)

call %COMPOSE_CMD% up -d db redis
if errorlevel 1 (
    echo [FAIL] Failed to start Docker services.
    pause
    exit /b 1
)
echo [OK] Docker services started.
goto :docker_done

:docker_skip
echo [6/9] Skipping Docker services (SQLite mode).

:docker_done
echo.

rem ---------------------------------------------------------------------------
rem [7/9] Export runtime environment
rem ---------------------------------------------------------------------------
echo [7/9] Applying runtime environment...
set "DATABASE_URL=%RUNTIME_DB_URL%"
set "REDIS_URL=redis://localhost:6379/0"
set "CELERY_BROKER_URL=redis://localhost:6379/0"
set "CELERY_RESULT_BACKEND=redis://localhost:6379/0"
set "ENVIRONMENT=production"
set "DEBUG=False"
if not defined SECRET_KEY set "SECRET_KEY=local-production-secret-change-me"
echo [OK] Runtime environment configured.
echo.

rem ---------------------------------------------------------------------------
rem [8/9] Wait for DB + run Alembic migrations
rem ---------------------------------------------------------------------------
echo [8/9] Waiting for database readiness...
set "DB_READY=0"
for /L %%I in (1,1,30) do (
    "%PYTHON_EXE%" -c "import os; from sqlalchemy import create_engine,text; e=create_engine(os.environ['DATABASE_URL']); c=e.connect(); c.execute(text('SELECT 1')); c.close()" >nul 2>nul
    if not errorlevel 1 (
        set "DB_READY=1"
        goto :db_ready
    )
    timeout /t 2 /nobreak >nul
)

:db_ready
if "!DB_READY!"=="0" (
    echo [FAIL] Database is not reachable after waiting.
    pause
    exit /b 1
)
echo [OK] Database connection verified.

echo [INFO] Running Alembic migrations...
"%PYTHON_EXE%" -m alembic upgrade head
if not errorlevel 1 goto :migrations_ok

echo [WARN] Alembic upgrade failed.
echo !RUNTIME_DB_URL! | findstr /I "sqlite" >nul
if errorlevel 1 goto :migrations_fail

echo [WARN] Attempting SQLite migration recovery with "alembic stamp head"...
"%PYTHON_EXE%" -m alembic stamp head
if errorlevel 1 goto :migrations_fail

echo [OK] SQLite migration state stamped to head.
goto :migrations_ok

:migrations_fail
echo [FAIL] Alembic migration failed and recovery did not succeed.
pause
exit /b 1

:migrations_ok
echo [OK] Database schema is up to date.
echo.

rem ---------------------------------------------------------------------------
rem [9/9] Start application (local production mode)
rem ---------------------------------------------------------------------------
echo [9/9] Starting KinJo application...
echo.
echo ============================================================
echo    KinJo is starting in LOCAL PRODUCTION MODE
echo ============================================================
echo    URL:        http://127.0.0.1:%PORT%/
echo    API Docs:   http://127.0.0.1:%PORT%/docs
echo    Admin:      http://127.0.0.1:%PORT%/admin/dashboard
echo    Health:     http://127.0.0.1:%PORT%/health
echo    Workers:    %WORKERS%
echo.
echo    Press Ctrl+C to stop
echo ============================================================
echo.

"%PYTHON_EXE%" -m uvicorn main:app --host %HOST% --port %PORT% --workers %WORKERS% --proxy-headers --forwarded-allow-ips=127.0.0.1,::1

echo.
echo ============================================================
echo    KinJo server stopped.
echo ============================================================
pause
