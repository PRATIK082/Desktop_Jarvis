@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   JARVIS Desktop - Setup and Run
echo ============================================
echo.

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do echo Node.js: %%v

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found. Install from https://python.org/
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)
for /f "tokens=*" %%v in ('%PYTHON% --version') do echo Python: %%v

:: Check Rust/Cargo
where cargo >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Rust/Cargo not found. Install from https://rustup.rs/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('cargo --version') do echo Cargo: %%v

:: Check Ollama (optional)
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not found. AI features will be unavailable.
    echo        Install from https://ollama.com/
) else (
    for /f "tokens=*" %%v in ('ollama --version') do echo Ollama: %%v
)

echo.
echo [1/3] Installing npm dependencies...
call npm run bootstrap
if %errorlevel% neq 0 (
    echo [ERROR] npm bootstrap failed.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing Python sidecar dependencies...
%PYTHON% -m pip install -r services/assistant/requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] Some Python packages may not have installed.
)

echo.
echo [3/3] Cleaning up stale processes, then starting JARVIS Desktop...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='jarvis-desktop.exe'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*services*assistant*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "$owner = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1; if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }"
echo       This will launch the desktop app with the Python sidecar.
echo       Press Ctrl+C to stop.
echo.
call npm run dev:tauri

pause