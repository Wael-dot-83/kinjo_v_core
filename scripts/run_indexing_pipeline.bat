@echo off
REM ============================================================
REM Kindergarten Indexing Pipeline — Batch Runner
REM ============================================================
REM Runs the indexing pipeline, then the database migration.
REM ============================================================

title Kindergarten Indexing Pipeline

echo ============================================================
echo STEP 1/2: Kindergarten Indexing Pipeline
echo ============================================================
echo.
python kindergarten_indexing_pipeline.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Indexing pipeline failed with code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo STEP 2/2: Database Migration (Add Index Column)
echo ============================================================
echo.
python add_index_column_migration.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Database migration failed with code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo ALL STEPS COMPLETED SUCCESSFULLY
echo ============================================================
echo.
pause