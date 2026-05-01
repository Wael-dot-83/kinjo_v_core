@echo off
REM KinJo Platform - Background Server Runner
REM This script runs the uvicorn server in the background

REM Check if .venv exists, otherwise use venv
if exist ".venv\Scripts\python.exe" (
    echo Starting server using .venv...
    start "KinJo Server" /B ".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
) else if exist "venv\Scripts\python.exe" (
    echo Starting server using venv...
    start "KinJo Server" /B "venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
) else (
    echo No virtual environment found. Using system Python...
    start "KinJo Server" /B python -m uvicorn main:app --host 127.0.0.1 --port 8000
)

echo.
echo KinJo server is starting in the background...
echo Access the application at: http://127.0.0.1:8000
echo Access API docs at: http://127.0.0.1:8000/docs
echo.
echo To stop the server, close the "KinJo Server" window or use Task Manager.
pause