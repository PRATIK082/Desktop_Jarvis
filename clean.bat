@echo off
setlocal

echo ============================================
echo   JARVIS Desktop - Deep Clean
echo ============================================
echo.
echo This frees disk space used by build output.
echo Run it when builds feel slow or disk is low.
echo A normal rebuild afterwards takes longer once.
echo.

:: Kill stale processes first (same sweep as start.bat).
echo [1/4] Stopping stale app and sidecar processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='jarvis-desktop.exe'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*services*assistant*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

:: Rust build output (~2.4 GB, recreated on next build).
echo [2/4] Removing Rust build output...
if exist "apps\desktop\src-tauri\target" (
    rmdir /s /q "apps\desktop\src-tauri\target"
    echo         target/ removed.
) else (
    echo         target/ already absent.
)

:: Frontend build output and Vite cache.
echo [3/4] Removing frontend build output and cache...
if exist "apps\desktop\dist" (
    rmdir /s /q "apps\desktop\dist"
    echo         dist/ removed.
) else (
    echo         dist/ already absent.
)
if exist "apps\desktop\node_modules\.vite" (
    rmdir /s /q "apps\desktop\node_modules\.vite"
    echo         node_modules/.vite removed.
) else (
    echo         node_modules/.vite already absent.
)

:: Sidecar logs.
echo [4/4] Removing sidecar logs...
if exist "services\assistant\logs\*.log" (
    del /q "services\assistant\logs\*.log"
    echo         logs cleared.
) else (
    echo         no logs to clear.
)

echo.
echo Clean complete.
pause
