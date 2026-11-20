# justask — локальный ИИ-тьютор по методичкам

Отвечает на вопросы студентов строго по загруженным материалам курса и показывает цитаты с номером страницы. Всё работает локально: **FastAPI + ChromaDB + FastEmbed + Ollama `llama3.2:3b`**. Поддерживаются PDF, TXT и DOCX; поиск гибридный (BM25 + вектора, склейка RRF).

## Локальный запуск

1. **Установите Ollama и скачайте модель ответов:**

   ```bash
   ollama pull llama3.2:3b
   ```

   Отдельный эмбеддер в Ollama качать **не нужно** — эмбеддинги считает FastEmbed прямо в Python (модель `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, скачивается один раз в локальный кэш).

2. **Создайте виртуальное окружение и установите зависимости:**

   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Запустите сервер:**

   ```bash
   uvicorn app.main:app --reload
   ```

   Файл `.env` создастся автоматически при первом старте: в нём будет сгенерированный `JWT_SECRET` и шаблон остальных настроек. Для локальной проверки загрузки файлов без Moodle задайте `ALLOW_GUEST_WRITES=true` в `.env` (или в переменных окружения) — в production этот флаг должен оставаться `false`.

## Быстрый тест в Moodle через Cloudflare Tunnel

1. В соседней консоли поднимите туннель до локального сервера:

   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

2. В Moodle создайте элемент курса **«Внешний инструмент»** (LTI 1.1):
   - **URL инструмента:** `https://<ссылка-из-туннеля>/api/lti/launch`
   - **Consumer Key** и **Shared Secret:** значения `LTI_CONSUMER_KEY` и `LTI_SHARED_SECRET` из вашего `.env` (замените шаблонные заглушки на свои).

## Развёртывание на сервере вуза

Готовые шаблоны systemd-юнита, Nginx и пошаговый чеклист для Ubuntu 22.04/24.04 (без Docker): [deploy/README_LINUX.md](deploy/README_LINUX.md).

## Проверки

```bash
pytest                          # 76+ тестов
python benchmarks/run_40_eval.py # eval по 40 вопросам
```

Готовность зависимостей можно проверить через `GET /health`: ответ `200 {"status":"ok", ...}` или `503 {"status":"degraded", ...}` с подробностями в поле `errors`.
