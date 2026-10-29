@echo off
REM JARVIS Desktop — local setup (Windows)
REM Runs the Python setup script to check prerequisites and install dependencies.
REM Local files (.env, logs/) are created and never committed to git.

setlocal enabledelayedexpansion

echo ========================================
echo JARVIS Desktop — local setup
echo ========================================
echo.

:: Ensure Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found on PATH. Install Python 3.11+ first.
    exit /b 1
)

python "%~dp0setup.py" %*
exit /b %errorlevel%
