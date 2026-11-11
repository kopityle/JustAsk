#!/bin/bash
set -e

echo "==================================================="
echo "🚀 [1/4] Настройка и запуск Ollama для многопоточности..."
echo "==================================================="

# Экспортируем переменные окружения для инференса (золотой конфиг под 8 ГБ)
export OLLAMA_NUM_PARALLEL=2
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=60m

# 1. Если Ollama не установлена — ставим
if ! command -v ollama &> /dev/null; then
    echo "[!] Ollama не найдена. Устанавливаем автоматически..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# 2. Если Ollama работает как systemd-сервис, прописываем переменные в systemd
if systemctl is-active --quiet ollama 2>/dev/null; then
    echo "[*] Найдена системная служба ollama.service, обновляем параметры пула..."
    sudo mkdir -p /etc/systemd/system/ollama.service.d
    cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null
[Service]
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=60m"
EOF
    sudo systemctl daemon-reload
    sudo systemctl restart ollama
    sleep 2
elif ! curl -s http://localhost:11434 > /dev/null; then
    # Если systemd нет (например, внутри Docker), стартуем руками в фоне
    echo "[!] Запускаем фоновый процесс Ollama (2 слота инференса)..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

echo "[OK] Ollama запущена с поддержкой параллельных запросов!"

echo ""
echo "==================================================="
echo "📦 [2/4] Проверяем модели ИИ..."
echo "==================================================="
if ! ollama list | grep -q "llama3.2:3b"; then
    echo "[!] Скачиваем llama3.2:3b..."
    ollama pull llama3.2:3b
fi
# Эмбеддинги считаются FastEmbed в Python — отдельная Ollama-модель не нужна
echo "[OK] Модели готовы!"

echo ""
echo "==================================================="
echo "🐍 [3/4] Проверяем Python и зависимости..."
echo "==================================================="
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    if [ ! -f "venv/.installed" ]; then
        echo "[*] Ставим зависимости - первый запуск, пару минут..."
        pip install -r requirements.txt || { echo "[!] Ошибка установки зависимостей."; exit 1; }
        touch venv/.installed
    fi
    echo "[OK] Использую venv."
elif python3 -c "import fastapi, uvicorn, chromadb" 2>/dev/null; then
    echo "[OK] Зависимости уже в системном Python, venv не нужен."
else
    echo "[*] Зависимостей нет. Пробую создать venv..."
    if ! python3 -m venv venv; then
        echo "[!] Не удалось создать venv."
        echo "    На Debian/Ubuntu: sudo apt install python3-venv python3-pip"
        echo "    Или установите зависимости вручную: python3 -m pip install -r requirements.txt"
        exit 1
    fi
    source venv/bin/activate
    pip install -r requirements.txt || { echo "[!] Ошибка установки зависимостей."; exit 1; }
    touch venv/.installed
fi
echo "[OK] Окружение Python готово!"

echo ""
echo "==================================================="
echo "🌐 [4/4] Запуск JustAsk на порту 8000..."
echo "==================================================="
# На сервере запускаем без --reload (он тратит ресурсы и нужен только при разработке)
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000