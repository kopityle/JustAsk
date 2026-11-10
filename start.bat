@echo off
title JustAsk AI Tutor

REM 1) Parallel inference slots in Ollama
set OLLAMA_NUM_PARALLEL=2

REM 2) Number of models kept loaded at once
set OLLAMA_MAX_LOADED_MODELS=1

REM 3) Never unload models while idle
set OLLAMA_KEEP_ALIVE=60m

REM 4) Allow guest writes for debugging uploads
set ALLOW_GUEST_WRITES=true

echo ===================================================
echo [1/3] Checking Ollama...
echo ===================================================
curl -s http://localhost:11434 > nul
if %errorlevel% neq 0 (
    echo [!] Starting Ollama in a separate window...
    start "Ollama" cmd /k ollama serve
    timeout /t 3 /nobreak > nul
) else (
    echo [OK] Ollama is already running in background.
)

echo.
echo ===================================================
echo [2/3] Activating Python venv...
echo ===================================================
if exist venv\Scripts\activate (
    call venv\Scripts\activate
) else (
    echo [!] venv folder not found, using system Python.
)

echo.
echo ===================================================
echo [3/3] Starting FastAPI...
echo ===================================================
start http://localhost:8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
