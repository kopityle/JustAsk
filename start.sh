#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  JustAsk AI Tutor - bootstrap and start (Linux)"
echo "============================================================"

# === Golden config for 8 GB RAM: set BEFORE ollama starts ===
export OLLAMA_NUM_PARALLEL=2
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=60m

# === 1. Python ===
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Python3 не найден. Установите Python 3.10+:"
    echo "    Ubuntu: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi
echo "[OK] $(python3 --version)"

# === 2. venv: if unavailable, continue with system Python ===
if python3 -c "import venv" >/dev/null 2>&1; then
    if [ ! -f "venv/bin/activate" ]; then
        echo "[*] Creating virtual environment..."
        if ! python3 -m venv venv; then
            echo "[*] Не удалось создать venv, используется системный Python."
        fi
    fi
    if [ -f "venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source venv/bin/activate
        echo "[OK] venv активировано."
    fi
else
    echo "[*] Модуль venv не найден, используется системный Python."
fi

# === 3. Dependencies: install only when imports fail ===
if python3 -c "import fastapi, uvicorn, chromadb, fastembed, pymorphy3, docx" >/dev/null 2>&1; then
    echo "[OK] Зависимости установлены."
else
    echo "[*] Не хватает зависимостей, ставлю из requirements.txt (первый запуск - пару минут)..."
    python3 -m pip install -r requirements.txt || {
        echo "[!] Не удалось установить зависимости."
        echo "    Ubuntu: sudo apt install python3-pip python3-venv"
        exit 1
    }
    echo "[OK] Зависимости установлены."
fi

# === 4. .env creates itself on first import of app.core.config ===
echo "[*] Проверяю конфигурацию..."
python3 -c "import app.core.config" || {
    echo "[!] Не удалось подготовить .env. Скопируйте .env.example в .env вручную."
    exit 1
}

# === 5. Ollama binary ===
if ! command -v ollama >/dev/null 2>&1; then
    echo "[!] Ollama не найдена в PATH. Установите:"
    echo "    curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi
echo "[OK] Ollama найдена: $(command -v ollama)"

# If Ollama is a systemd service, register the golden pool settings.
if systemctl is-active --quiet ollama 2>/dev/null; then
    echo "[*] Найдена ollama.service, обновляю параметры пула..."
    if command -v sudo >/dev/null 2>&1; then
        sudo mkdir -p /etc/systemd/system/ollama.service.d
        cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null
[Service]
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=60m"
EOF
        sudo systemctl daemon-reload
        sudo systemctl restart ollama
    else
        echo "[*] sudo недоступен: задайте переменные в /etc/systemd/system/ollama.service.d/override.conf вручную."
    fi
fi

# === 6. Ollama service: start if needed, then wait up to 30 seconds ===
if ! curl -fsS --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
    if ! systemctl is-active --quiet ollama 2>/dev/null; then
        echo "[*] Ollama не отвечает, запускаю демон в фоне..."
        ollama serve >/tmp/ollama.log 2>&1 &
    fi
    for i in $(seq 1 30); do
        if curl -fsS --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
            break
        fi
        sleep 1
        if [ "$i" -eq 30 ]; then
            echo "[!] Ollama не ответила за 30 секунд. Смотрите /tmp/ollama.log"
            exit 1
        fi
    done
fi
echo "[OK] Ollama доступна на http://localhost:11434"

# === 7. Answer model. No separate embedder needed: FastEmbed runs in Python ===
if ! ollama list | grep -q "llama3.2:3b"; then
    echo "[*] Скачиваю llama3.2:3b - это ~2 ГБ..."
    ollama pull llama3.2:3b || {
        echo "[!] Не удалось скачать модель. Повторите: ollama pull llama3.2:3b"
        exit 1
    }
    echo "[OK] Модель загружена."
else
    echo "[OK] Модель llama3.2:3b уже есть."
fi
echo "[OK] Отдельный эмбеддер в Ollama качать НЕ нужно - FastEmbed работает в Python."

# === 8. Start the server ===
echo "[*] Server: http://localhost:8000  |  health: http://localhost:8000/health"
echo "[*] Для загрузки файлов без Moodle задайте ALLOW_GUEST_WRITES=true в .env"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
