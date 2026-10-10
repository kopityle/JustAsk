# Спецификация API‑контрактов для justask (локальный RAG‑тьютор)

## 1. Документы (`/api/documents`)

### GET /`/api/documents`  (Info about corpus)
- **Headers**  
  - `Authorization: Bearer <jwt>` (jwt содержит `role`, `course_id`)  
  - *(опционально)* пустой токен для гостя.
- **Response (200 OK)**  
  ```json
  {
    "documents": [           // список объектов с метаданными
      {"filename": "lecture1.pdf", "chunks": 25, "pages": 10},
      {"filename": "tutorial.txt", "chunks": 15, "pages": 5}
    ],
    "total_chunks": 342,    // общее количество чанков в Chroma (materials_v2)
    "can_manage": true,     // true, если роль teacher/guest‑write
    "dev_write_access": false
  }
  ```
- **Error 401** – отсутствует/некорректный токен.  
- **Error 403** – роль не имеет права на управление документами.

### POST /`/api/documents/upload`
- **Payload** – `multipart/form-data` с полем `file` (UploadFile).
- **Headers** – тот же `Authorization`.
- **Body fields**  
  - `file` – загружаемый PDF или TXT.
- **Response (200 OK)**  
  ```json
  {"status":"ok","filename":"lecture1.pdf","indexed_chunks":57}
  ```
- **HTTP 400** – неверное расширение, пустое имя, файл > MAX_UPLOAD_SIZE (по умолчанию 50 MB, настройка в `config.py`).
- **HTTP 409** – файл с таким именем уже существует.
- **HTTP 413** – файл слишком большой (проверяется в `save_file`).

### DELETE /`/api/documents/{filename}`
- **URL param** – `filename` (имя файла без пути).
- **Headers** – `Authorization`.
- **Response (200 OK)**  
  ```json
  {"status":"deleted","filename":"lecture1.pdf","removed_chunks":57}
  ```
- **HTTP 403** – insufficient rights.  
- **HTTP 404** – файл не найден в хранилище (и Chroma, и папка `docs`).

---

## 2. Чат / стриминг (`/api/chat/stream`)

### POST /`/api/chat/stream`
- **Request body** (`ChatRequest` pydantic‑модель):
  ```json
  {
    "question": "Какие требования описаны в материалах курса?"
  }
  ```
- **Headers** – `Authorization: Bearer <jwt>` (опционально; пустой токен = guest).
- **Streaming response** – `media_type="text/event-stream"`.  
  Каждое событие имеет формат `data: <JSON>\n\n`. Содержимое событий:

  1. **Meta‑событие (первое)**  
     ```json
     {
       "type": "meta",
       "sources": [                      // может быть пустым, если вопрос не найден
         {
           "document": "lecture1.pdf",
           "page": 42,
           "text": "Модель данных — это совокупность правил порождения данных."
         }
       ],
       "is_found": true|false
     }
     ```

  2. **Token‑события** (последовательные фрагменты ответа LLM)  
     ```json
     {"type":"token","token":"Модель данных — это …"}
     ```

  3. **Финальное событие**  
     ```
     data: [DONE]\n\n
     ```

- **Логика отказоустойчивости** (первые ~15 мс): если после вектора поиска `chunks` пусто, сразу отдаёт `meta` с `is_found:false` и токен «В материалах курса ответ на этот вопрос не найден.».
- **Ограничение инференса** — семафор `inference_semaphore` (макс‑тайм‑аут 25 с). При таймауте возвращается `⚠️ Сервер сейчас перегружен…`.
- **Отключение клиента** — если клиент закрыл вкладку, стриминг прерывается (`request.is_disconnected()`), а семафор освобождается.
- **Ошибки**  
  - **400** – `question` пустой.
  - **401** – нет токена или он некорректен.
  - **500** – внутренняя ошибка LLM (перехвачена и возвращена как токен с префиксом `⚠️`).

---

## 3. Обратная связь (`/api/feedback`)

### POST /`/api/feedback`
- **Body** (`FeedbackRequest` pydantic‑модель):
  ```json
  {
    "question": "Какие требования описаны в материалах курса?",
    "answer": "Ответ с цитатой",
    "is_positive": true
  }
  ```
- **Headers** – `Authorization: Bearer <jwt>` (опционально).
- **Response (200 OK)**  
  ```json
  {"status":"recorded"}
  ```
- **Бочная сторона** — запись добавляется в `settings.FEEDBACK_FILE` (по умолчанию `./data/feedback.jsonl`). Используется `threading.Lock` для потокобезопасного доступа.

---

## 4. LTI‑запуск из Moodle (`/api/lti/launch`)

### POST /`/api/lti/launch`
- **Body** – сырой OAuth‑1 форма‑data (Moodle отправляет подписанный запрос).
- **Headers** – `Content-Type: application/x-www-form-urlencoded`.
- **Response (302 Redirect)**  
  ```http
  Location: /?token=<jwt>
  ```
  Где `<jwt>` encodes `{name, role, course_id}` с использованием `JWT_SECRET`.
- **Обработка ошибок**  
  - **401** – подпись не пройдена (`validate_request` вернул `false`).  
  - В логах пишется отладочное сообщение: `"Подпись не сошлась. Ожидаемый URI: …"`.
- **Роль** (`_role_from_lti`)  
  - Инструктор/учитель → `"teacher"`  
  - Во всех остальных случаях → `"student"`.

---

## 5. Общие заголовки и настройки
- **JWT_SECRET** — задается в `app/core/config` (случайная строка, хранящаяся в `.env`).
- **ALLOWED_EXTENSIONS** — `{".pdf", ".txt"}` (все endpoints, проверяющие расширение).
- **MAX_UPLOAD_SIZE** — лимит размера файла (по умолчанию 50 МБ, настраивается в `settings`).
- **CORS** — не нужен, так как фронтенд и бэкенд развернуты на одном хосте (или настроены через FastAPI `CORSMiddleware` в `main.py`).