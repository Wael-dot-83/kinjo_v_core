@echo off
echo Starting KinJo Platform Server...
echo ================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not found in PATH.
    echo Please install Python 3.9+ and add it to your PATH.
    pause
    exit /b
)

:: Check if virtual environment exists
if not exist "venv" (
    echo Virtual environment not found. Creating 'venv'...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b
    )
    echo Virtual environment created.
)

:: Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Error: venv created but activate.bat not found.
    pause
    exit /b
)

:: Check if dependencies are installed (check for uvicorn)
python -m pip show uvicorn >nul 2>&1
if errorlevel 1 (
    echo Dependencies not found. Installing from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b
    )
    echo Dependencies installed successfully.
)

:: Run the server
echo.
echo Launching Uvicorn...
echo Access the API at http://127.0.0.1:8000/docs
echo Access the KPI Dashboard at http://127.0.0.1:8000/kpi/dashboard
echo.
uvicorn main:app --reload --host 127.0.0.1 --port 8000
pause
