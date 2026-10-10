# Архитектура данных: ChromaDB, папка docs и обратная связь (feedback.jsonl)

## 1. ChromaDB (векторное хранилище)
- **Название коллекции** (по умолчанию): `materials_v2` (задается в `vector_store.py:44`).
- **Схема документа (чанка)** (один запись в коллекции):
  - `id` – уникальный идентификатор чанка (генераруется при `add_chunks`).
  - `document` – **имя файла** (без пути), например `lecture1.pdf`.
  - `page` – номер страницы (целое число), извлеченный при парсинге PDF.
  - `text` – текстовый фрагмент (чанк) длиной до ~1000 символов.
  - `metadata` – объект с полями:
    - `course_id` – идентификатор курса (строка, по умолчанию `"default_course"`).
    - `filename` – то же, что и `document`.
    - `chunk_index` – порядковый номер чанка внутри файла.
- **Функции доступа** (из `app/services/vector_store.py`):
  - `add_chunks(chunks: List[dict], course_id: str)` – последовательно вставляет записи в Chroma.
  - `delete_document(filename: str, course_id: str)` – удаляет все чанки, где `metadata.document == filename` и `metadata.course_id == course_id`.
  - `search(query: str, top_k: int, course_id: str) → List[dict]` – векторный поиск, возвращает словари с полями `document`, `page`, `text`, `metadata`.
  - `get_document_stats(course_id: str) → dict` – возвращает `{ "total_chunks": N, "unique_documents": M }` (используется в `GET /api/documents`).
- **Типы хранилища** – на данный момент используется встроенная база Chroma (файловая версия, путь по умолчанию `./data/chroma`). При необходимости можно заменить на удаленный сервер, но код пока ориентирован на локальное развертывание.

## 2. Папка `docs/` (файлы, загруженные преподавателями)
- **Путь** — `settings.DOCS_DIR` (по умолчанию `./data/docs/`).
- **Разрешенные расширения** — `.pdf` и `.txt` (проверяется на этапе загрузки через `validate_filename` в `documents.py`).
- **Содержимое** – исходные учебные материалы. После загрузки файл передается в `load_and_chunk_file` (из `pdf_loader`), который:
  - Для PDF: использует `pymupdf` (PyMuPDF) для извлечения текста и разделения его на страницы/чанки.
  - Для TXT: читает файл целиком и разбивает на чанки заданного размера.
- **После индексации** исходный файл сохраняется на диск, а только его чанки попадают в ChromaDB. При повторной загрузке того же имени файл отклоняется с HTTP 409 (already exists).

## 3. Файл обратной связи `feedback.jsonl`
- **Путь** — `settings.FEEDBACK_FILE` (по умолчанию `./data/feedback.jsonl`).
- **Формат каждой записи** — одна строка JSON, например:
  ```json
  {"question":"Какие требования описаны в материалах курса?", "answer":"Ответ с цитатой", "is_positive": true}
  ```
- **Запись** — происходит в эндпоинте `POST /api/feedback` (`chat.py:93‑98`). Используется глобальный `file_lock` (threading), чтобы избежать перезаписей при одновременных запросах.
- **Чтение** — в текущем фронтенде файлы не читаются автоматически; их можно обрабатывать отдельными дашбордами или скриптами аналитики.

## 4. Итоговая схема данных (граф)
```
[ChromaDB collection "materials_v2"]
   ├─ each record: {id, document, page, text, metadata{course_id, filename, chunk_index}}
   └─ indexes: vector embedding (для semantic search)

[Folder ./data/docs/]
   └─ uploaded .pdf / .txt files (raw source material)

[File ./data/feedback.jsonl]
   └─ append‑only JSON lines {question, answer, is_positive}
```