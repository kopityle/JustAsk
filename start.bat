@echo off
chcp 65001 >nul
title JustAsk AI Tutor
cd /d "%~dp0"

echo ============================================================
echo   JustAsk AI Tutor - bootstrap and start (Windows)
echo ============================================================

REM === Golden config for 8 GB RAM: set BEFORE ollama starts ===
set "OLLAMA_NUM_PARALLEL=2"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_KEEP_ALIVE=60m"

REM === 1. Ollama: explicit locations + PATH lookup ===
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%ProgramFiles%\Ollama;%PATH%"
where ollama >nul 2>&1
if errorlevel 1 (
    echo [!] Ollama не найдена в PATH и по стандартным путям.
    echo     Скачайте и установите: https://ollama.com/download/windows
    echo     После установки откройте НОВОЕ окно терминала и запустите скрипт снова.
    pause
    exit /b 1
)
echo [OK] Ollama найдена.

REM === 2. Python ===
where python >nul 2>&1
if errorlevel 1 (
    echo [!] Python не найден. Установите Python 3.10+ с галочкой "Add python.exe to PATH":
    echo     https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python найден.

REM === 3. venv: if unavailable, continue with system Python ===
python -c "import venv" >nul 2>&1
if errorlevel 1 (
    echo [*] Модуль venv не найден, используется системный Python.
    goto :deps
)
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [*] Не удалось создать venv, используется системный Python.
        goto :deps
    )
)
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [*] Не удалось активировать venv, используется системный Python.
    goto :deps
)
echo [OK] venv активировано.

:deps
python -c "import fastapi, uvicorn, chromadb, fastembed, pymorphy3, docx" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Зависимости установлены.
    goto :envcheck
)
echo [*] Не хватает зависимостей, ставлю из requirements.txt - первый запуск может занять пару минут...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Не удалось установить зависимости. Проверьте интернет и права пользователя.
    pause
    exit /b 1
)
echo [OK] Зависимости установлены.

:envcheck
REM === 4. .env creates itself on first import of app.core.config ===
echo [*] Проверяю конфигурацию...
python -c "import app.core.config"
if errorlevel 1 (
    echo [!] Не удалось подготовить .env. Скопируйте .env.example в .env вручную.
    pause
    exit /b 1
)

REM === 5. Ollama service ===
curl.exe -s --max-time 1 http://localhost:11434/api/tags >nul 2>&1
if not errorlevel 1 goto :ollama_ready
echo [*] Ollama не отвечает, запускаю демон в фоне...
start "" ollama serve
set /a OLLAMA_TRIES=0

:ollama_wait
curl.exe -s --max-time 1 http://localhost:11434/api/tags >nul 2>&1
if not errorlevel 1 goto :ollama_ready
set /a OLLAMA_TRIES+=1
if %OLLAMA_TRIES% GEQ 30 goto :ollama_failed
timeout /t 1 /nobreak >nul
goto :ollama_wait

:ollama_failed
echo [!] Ollama не ответила за 30 секунд. Проверьте вручную: ollama serve
pause
exit /b 1

:ollama_ready
echo [OK] Ollama доступна на http://localhost:11434

REM === 6. Answer model. No separate embedder needed: FastEmbed runs in Python ===
ollama list | findstr /i /c:"llama3.2:3b" >nul 2>&1
if errorlevel 1 (
    echo [*] Скачиваю llama3.2:3b - это ~2 ГБ...
    ollama pull llama3.2:3b
    if errorlevel 1 (
        echo [!] Не удалось скачать модель. Повторите вручную: ollama pull llama3.2:3b
        pause
        exit /b 1
    )
    echo [OK] Модель загружена.
) else (
    echo [OK] Модель llama3.2:3b уже есть.
)
echo [OK] Отдельный эмбеддер в Ollama качать НЕ нужно - FastEmbed работает в Python.

REM === 7. Start the server ===
echo [*] Server: http://localhost:8000  ^|  health: http://localhost:8000/health
echo [*] Для загрузки файлов без Moodle задайте ALLOW_GUEST_WRITES=true в .env
start "" http://localhost:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
