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
if [ ! -d "venv" ]; then
    echo "[!] Создаём venv..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi
echo "[OK] Окружение Python готово!"

echo ""
echo "==================================================="
echo "🌐 [4/4] Запуск JustAsk на порту 8000..."
echo "==================================================="
# На сервере запускаем без --reload (он тратит ресурсы и нужен только при разработке)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000