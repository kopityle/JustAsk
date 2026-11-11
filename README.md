# justask — Локальный ИИ-наставник по учебному курсу

Сервис на базе локальной LLM и RAG-конвейера, который отвечает на вопросы студентов строго по материалам курса с подтверждением ответа цитатой и номером страницы.

## Стек технологий
- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **AI & RAG:** Ollama (Llama 3.2 3B / Qwen 2.5), ChromaDB Hybrid Search, PyMuPDF
- **Frontend:** SPA (HTML5, TailwindCSS, Vanilla JS) с поддержкой встраивания через LTI 1.1 iframe
- **Интеграция:** LMS Moodle (elearn.urfu.ru) via LTI 1.1

## Быстрый запуск
1. Убедитесь, что запущен демон Ollama:
   ```bash
   ollama pull llama3.2:3b
   ollama pull nomic-embed-text
   ollama run llama3.2:3b
   pip install -r requirements.txt
   ```

## Режим разработки без LTI

По умолчанию гости могут только задавать вопросы. Чтобы локально загружать и удалять методички без токена преподавателя, включите флаг:

```powershell
$env:ALLOW_GUEST_WRITES="true"
uvicorn app.main:app --reload
```

В интерфейсе появится предупреждение `DEV: ...`. Не включайте этот флаг в production.
Максимальный размер файла задаётся через `MAX_UPLOAD_SIZE` (в байтах, по умолчанию 50 МБ).
