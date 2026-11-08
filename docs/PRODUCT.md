# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Students of an UrFU course who study lecture and lab materials in Moodle and need quick, trustworthy answers while preparing for classes. Teachers are a secondary audience: they upload and maintain the course materials that ground the assistant's answers.

## Product Purpose

justask is a local AI tutor that answers student questions strictly from the course materials and backs each answer with a quotation and page number. It exists to reduce information overload and to make AI assistance trustworthy in an academic setting. Success means students can verify every answer against the source instead of guessing whether the model invented it.

## Positioning

The product combines retrieval over the course corpus with citation-level grounding and runs on a local LLM, so course content and student questions do not need to leave the institution's environment. Neighboring chat assistants cannot truthfully copy the combination of local inference, source-bound answers, and Moodle-native access.

## Operating Context

Students use justask inside the Moodle course at elearn.urfu.ru through an LTI 1.1 iframe, as well as through the standalone web interface during local development. Teachers upload PDF and TXT methodology files; the system indexes them and makes them available to the whole course. The interface and course materials are in Russian. Answers are expected to cite the document title, page, and quoted fragment.

## Capabilities and Constraints

- FastAPI backend with a server-rendered SPA frontend.
- Local Ollama inference: `llama3.2:3b` for answers and `nomic-embed-text` for embeddings.
- RAG pipeline with ChromaDB and /vector retrieval.
- PDF/TXT ingestion with chunking and page mapping.
- Streaming answers over SSE, source cards with expandable quotations, answer copying, and usefulness feedback.
- Role-aware JWT sessions: students consume answers; teachers can upload and delete materials.
- Must remain embeddable in Moodle via LTI 1.1, including iframe-friendly response headers.
- Product truth is the Q&A tutor implemented today. The adaptive test generator described in `docs/1_BRD_PRD.md` is a possible future extension, not current functionality.

## Brand Commitments

The product name is `justask`, written lowercase. The voice is direct, friendly, and academic: Russian-language, no decorative marketing claims, and no fabricated course facts.

## Evidence on Hand

- Working chat interface in `app/static/index.html`.
- API and RAG implementation in `app/api/` and `app/services/`.
- Real course material available at `data/docs/978-5-7996-2478-1_2018.pdf`.
- Product and API notes in `docs/1_BRD_PRD.md`, `docs/2_Database_Architecture.md`, and `docs/3_API_Contracts.md`.
- No customer testimonials, benchmarks, pricing, or press assets exist; future work must not invent them.

## Product Principles

1. Every answer is traceable to a specific course source; unverifiable answers are a product failure.
2. Keep the student's data and the course corpus inside the local environment.
3. Fit the study workflow: fast questions, clear citations, and no friction between Moodle and the assistant.
4. Respect the teacher's authority over course materials; students should not be able to alter the corpus.
5. Prefer honest uncertainty over a confident answer that is not grounded in the materials.
