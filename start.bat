@echo off
setlocal

echo Starting JARVIS Desktop...
echo.

:: Check if dependencies are installed
if not exist "node_modules" (
    echo Dependencies not installed. Run run.bat first.
    pause
    exit /b 1
)

:: Auto-cleanup stale processes from previous runs.
:: - Kills hidden previous jarvis-desktop.exe windows (old binary kept running).
:: - Kills orphan sidecar pythons (matched by script path, other apps untouched).
:: - Frees port 5173 if a dead dev server still holds it.
echo Cleaning up processes left over from previous runs...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='jarvis-desktop.exe'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*services*assistant*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "$owner = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1; if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }"
echo Cleanup done.
echo.

call npm run dev:tauri
