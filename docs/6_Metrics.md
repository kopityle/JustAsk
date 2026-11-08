# Определения метрик — cheat‑sheet justask KPI

| Метрика | Формула / Источник | Единица измерения | Комментарий |
|---------|--------------------|-------------------|-------------|
| **Onboarding completion rate** | `100 % – (dismissedUsers / totalUsers)` | % | Отслеживает, сколько пользователей сохраняет руководство вместо того, чтобы его скрыть. |
| **Document uptake rate** | `uploaders / totalUsers` | % | Процент пользователей, которые добавили хотя бы один PDF/TXT. |
| **Question‑answer acceptance** | `answersWithFeedback / totalAnswers` | % | Ответы, получившие хотя бы один голос 👍/👎. |
| **Positive feedback ratio** | `positiveVotes / (positiveVotes + negativeVotes)` | % | Чем выше значение, тем более полезные ответы в целом. |
| **Most‑selected sample prompt** | `max(count(sample_prompt_selected[promptIndex]))` | Индекс / текст | Помогает подтвердить, что используются нейтральные архетипы. |
| **Average session length** | `(exitTime – loadTime) / 60` | минуты | Из `conversation_cleared` или закрытия страницы. |
| **First‑answer time** | `timeToFirstToken` (мс) | мс | Сколько времени проходит после нажатия Send, прежде чем AI начнет возвращать токены. |
| **Source‑reuse rate** | `answersWithSources / totalAnswers` | % | Показывает, насколько часто система находит материал для цитаты. |

*Все метрики вычисляются на основе полезных нагрузок событий, определенных в `5_Analytics_Plan.md`.*