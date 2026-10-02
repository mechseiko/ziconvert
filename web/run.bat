@echo off
REM ─────────────────────────────────────────────────────────────────────
REM  zicengine web — launch backend + frontend together
REM  Usage:  web\run.bat
REM ─────────────────────────────────────────────────────────────────────

setlocal

REM Detect repo root (parent of this script's directory)
set "SCRIPT_DIR=%~dp0"
set "REPO=%SCRIPT_DIR%.."
set "BACKEND=%SCRIPT_DIR%backend"
set "FRONTEND=%SCRIPT_DIR%frontend"

echo.
echo  ███████╗██╗ ██████╗███████╗███╗   ██╗ ██████╗ ██╗███╗   ██╗███████╗
echo  ╚══███╔╝██║██╔════╝██╔════╝████╗  ██║██╔════╝ ██║████╗  ██║██╔════╝
echo    ███╔╝ ██║██║     █████╗  ██╔██╗ ██║██║  ███╗██║██╔██╗ ██║█████╗
echo   ███╔╝  ██║██║     ██╔══╝  ██║╚██╗██║██║   ██║██║██║╚██╗██║██╔══╝
echo  ███████╗██║╚██████╗███████╗██║ ╚████║╚██████╔╝██║██║ ╚████║███████╗
echo  ╚══════╝╚═╝ ╚═════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝╚═╝  ╚═══╝╚══════╝
echo.
echo  Image to DXF — web UI
echo  Backend : http://localhost:8000
echo  Frontend: http://localhost:5173
echo  Docs    : http://localhost:8000/docs
echo.

REM ── Check Python ─────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found on PATH.
    echo         Install Python 3.11+ and try again.
    pause
    exit /b 1
)

REM ── Check Node ───────────────────────────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] node not found on PATH.
    echo         Install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

REM ── Install Python deps if needed ─────────────────────────────────────
if not exist "%BACKEND%\.deps_ok" (
    echo [1/4] Installing Python backend dependencies...
    pip install -r "%BACKEND%\requirements.txt" --quiet
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check internet connection or venv.
        pause
        exit /b 1
    )
    echo. > "%BACKEND%\.deps_ok"
    echo       Done.
) else (
    echo [1/4] Python deps already installed ^(delete backend\.deps_ok to reinstall^).
)

REM ── Install Node deps if needed ──────────────────────────────────────
if not exist "%FRONTEND%\node_modules" (
    echo [2/4] Installing Node frontend dependencies ^(this may take a minute^)...
    pushd "%FRONTEND%"
    npm install --silent
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause
        exit /b 1
    )
    popd
    echo       Done.
) else (
    echo [2/4] Node modules already present.
)

REM ── Launch backend ────────────────────────────────────────────────────
echo [3/4] Starting FastAPI backend on port 8000...
start "zicengine-backend" cmd /k "cd /d "%BACKEND%" && uvicorn main:app --reload --port 8000"

REM Give the backend a moment to start before the browser opens.
timeout /t 2 /nobreak >nul

REM ── Launch frontend ───────────────────────────────────────────────────
echo [4/4] Starting Vite frontend on port 5173...
start "zicengine-frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

echo.
echo  ✓ Both services are starting in separate windows.
echo  ✓ Open http://localhost:5173 in your browser.
echo.
echo  Press any key to exit this launcher (services keep running).
pause >nul
