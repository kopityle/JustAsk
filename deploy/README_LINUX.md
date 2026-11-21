# JustAsk на Linux без Docker (Ubuntu 22.04 / 24.04)

Короткий чеклист для администратора вуза. Пути зафиксированы в юните: `/opt/justask`.
Сервер слушает только `127.0.0.1:8000`, наружу его публикует Nginx по HTTPS.

## 1. Системные зависимости

```bash
sqlite3 --version          # нужно >= 3.35.0 (ChromaDB использует RETURNING в upsert)
sudo apt update
sudo apt install -y python3-venv python3-pip sqlite3 curl nginx
```

Если `sqlite3` старше 3.35 — обновите пакет из актуального репозитория до установки зависимостей, иначе ChromaDB упадёт на первой индексации.

## 2. Swap (при 8 ГБ ОЗУ)

```bash
sudo swapon --show         # если уже есть >= 4 ГБ — пропустите шаг
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Пользователь и каталоги

```bash
sudo useradd --system --create-home --home-dir /opt/justask --shell /bin/bash justask
sudo mkdir -p /opt/justask/data/chroma /opt/justask/data/docs
sudo cp -r . /opt/justask
sudo chown -R justask:justask /opt/justask
cd /opt/justask
sudo -u justask python3 -m venv venv
sudo -u justask venv/bin/pip install --upgrade pip
sudo -u justask venv/bin/pip install -r requirements.txt
```

## 4. Конфигурация `.env`

```bash
sudo -u justask cp /opt/justask/.env.example /opt/justask/.env
sudo -u justask nano /opt/justask/.env
sudo chmod 600 /opt/justask/.env
```

Обязательно заполните `LTI_CONSUMER_KEY`, `LTI_SHARED_SECRET`, `JWT_SECRET` (без них приложение не стартует). Для 8 ГБ рекомендуется `ALLOW_GUEST_WRITES=false`, `MAX_CONCURRENT_REQUESTS=2`, `DISTANCE_THRESHOLD=0.50`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`.

## 5. Ollama и «золотой» конфиг

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama
```

Добавьте в оверрайд:

```ini
[Service]
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=60m"
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
ollama pull llama3.2:3b
```

Эмбеддинги считаются FastEmbed внутри Python — отдельная модель Ollama не нужна.

## 6. Прогрев кэша FastEmbed от имени пользователя службы

Иначе при первом запросе модель скачивается уже от `justask` и может не иметь прав на каталог кэша:

```bash
cd /opt/justask
sudo -u justask -H env HF_HOME=/opt/justask/.cache/huggingface \
  venv/bin/python -c "from app.services.vector_store import vector_store; vector_store.embed_fn._get_model(); print('FastEmbed OK')"
sudo chown -R justask:justask /opt/justask/.cache
```

## 7. systemd

```bash
sudo cp /opt/justask/deploy/justask.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justask
sudo journalctl -u justask -f
```

Юнит привязан к `EnvironmentFile=/opt/justask/.env` и запускает **один** воркер (`--workers 1`) — семафор инференса и BM25-кэш живут в памяти процесса, поэтому несколько воркеров нельзя.

## 8. Nginx

```bash
sudo cp /opt/justask/deploy/nginx.conf /etc/nginx/sites-available/justask
sudo ln -s /etc/nginx/sites-available/justask /etc/nginx/sites-enabled/
sudo nano /etc/nginx/sites-available/justask    # server_name и пути к сертификатам
sudo nginx -t && sudo systemctl reload nginx
```

В шаблоне уже есть `client_max_body_size 55m;`, `X-Forwarded-Proto $scheme` для подписи LTI и отдельный `location /api/chat/stream` с `proxy_buffering off; proxy_read_timeout 120s;`.

## 9. Проверка

```bash
curl -i https://justask.example.edu/health
# 200: {"status":"ok","chunks":N,"ollama":"ok"}
# 503: {"status":"degraded", ...} — смотрите errors в ответе
```

Если `/health` отдаёт 503: проверьте `journalctl -u justask -n 100`, `curl http://127.0.0.1:11434/api/tags` и права `justask` на `/opt/justask/data/chroma`.
