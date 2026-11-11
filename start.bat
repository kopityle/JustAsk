@echo off
chcp 65001 >nul
title JustAsk AI Tutor

REM === Golden config for 8GB RAM (must be set BEFORE ollama starts) ===
set OLLAMA_NUM_PARALLEL=2
set OLLAMA_MAX_LOADED_MODELS=1
set OLLAMA_KEEP_ALIVE=60m
set ALLOW_GUEST_WRITES=true

echo ============================================================
echo  [1/5] Проверяем Python...
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [!] Установите Python 3.10+ с галочкой "Add to PATH"
    echo  Открываю python.org...
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python найден.

echo.
echo ============================================================
echo  [2/5] Проверяем Python-окружение...
echo ============================================================
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    if not exist venv\.installed (
        echo [*] Ставим зависимости - первый запуск, пару минут...
        python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [!] Ошибка установки зависимостей.
            pause
            exit /b 1
        )
        type nul > venv\.installed
    )
    echo [OK] Использую venv.
) else (
    python -c "import fastapi, uvicorn, chromadb" >nul 2>nul
    if not errorlevel 1 (
        echo [OK] Зависимости уже в системном Python, venv не нужен.
    ) else (
        echo [*] Зависимостей нет. Пробую создать venv...
        python -m venv venv 2>nul
        if errorlevel 1 (
            echo.
            echo  [!] Установите зависимости вручную:
            echo      python -m pip install -r requirements.txt
            echo  (или установите полный Python 3.10+ с python.org
            echo   с галочкой "Add to PATH" и снова запустите start.bat)
            start https://www.python.org/downloads/
            pause
            exit /b 1
        )
        call venv\Scripts\activate.bat
        python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [!] Ошибка установки зависимостей.
            pause
            exit /b 1
        )
        type nul > venv\.installed
    )
)
echo [OK] Окружение готово.

echo.
echo ============================================================
echo  [3/5] Проверяем Ollama...
echo ============================================================
where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo  [!] Не установлена Ollama. Скачайте её: https://ollama.com
    echo  Открываю сайт...
    start https://ollama.com
    pause
    exit /b 1
)
curl -s http://localhost:11434 >nul 2>nul
if errorlevel 1 (
    echo [*] Стартую Ollama в отдельном окне...
    start "Ollama" cmd /k ollama serve
) else (
    echo [OK] Ollama уже работает.
)

set /a TRIES=0
:wait_ollama
ollama list >nul 2>nul
if not errorlevel 1 goto ollama_ok
set /a TRIES+=1
if %TRIES% geq 15 (
    echo [!] Ollama не отвечает. Проверьте окно Ollama.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_ollama
:ollama_ok
echo [OK] Ollama отвечает.

echo.
echo ============================================================
echo  [4/5] Проверяем модель llama3.2:3b...
echo ============================================================
ollama list 2>nul | findstr /c:"llama3.2:3b" >nul
if errorlevel 1 (
    echo [!] Модель llama3.2:3b не найдена. Начинаем загрузку ~2 ГБ...
    ollama pull llama3.2:3b
    if errorlevel 1 (
        echo [!] Ошибка загрузки модели.
        pause
        exit /b 1
    )
)
echo [OK] Модель на месте.

echo.
echo ============================================================
echo  [5/5] Запуск JustAsk на http://localhost:8000
echo ============================================================
start http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
