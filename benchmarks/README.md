# Бенчмарки justask

Все замеры и отчёты лежат здесь, а результаты прогонов сохраняются в `benchmarks/results/`.

## Состав

- `run_40_eval.py` — 40 учебных/оффтоп-вопросов через RAG + строгий промпт.
- `test_prompts.py` — сравнение двух конфигураций промпта.
- `load_test_sse.py` — Locust-сценарий SSE-чата.
- `run_stress.ps1` — запуск Locust с автоматическим сохранением HTML/CSV.
- `scripts/auto_screenshots.py` — скриншоты ответов на 40 вопросов.
- `benchmark.md` — исторический отчёт сравнения промптов.

## 40 вопросов

```powershell
python benchmarks/run_40_eval.py
```

Сохраняется:

- `benchmarks/results/40_questions_<timestamp>.md`
- `benchmarks/results/latest_40_questions.md`

## Сравнение промптов

```powershell
python benchmarks/test_prompts.py
```

Сохраняется в `benchmarks/results/prompt_comparison_<timestamp>.md`.

## Стресс-тест

Приложение должно быть запущено на `http://localhost:8000`.

```powershell
.\benchmarks\run_stress.ps1 -Users 3 -Rate 1 -Duration 1m
```

Или напрямую:

```powershell
locust -f benchmarks/load_test_sse.py --host http://localhost:8000 `
  --headless -u 3 -r 1 -t 1m `
  --html=benchmarks/results/locust_report.html
```

Результаты: `locust_<timestamp>.html` и `locust_<timestamp>_*.csv` в `benchmarks/results/`.

## Скриншоты

```powershell
python scripts/auto_screenshots.py
```

Скриншоты сохраняются в `benchmarks/screenshots/`.
