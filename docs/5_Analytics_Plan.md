# План аналитики — метрики взаимодействия justask

## Цели
- Измерить вовлеченность студентов в Onboarding‑флод.
- Отслеживать принятие загрузки документов и их влияние на качество ответов на вопросы.
- Захватывать чувство обратной связи (👍/👎) и коррелировать с полезностью ответов.
- Идентифицировать популярные темы вопросов через выбор sample‑пromptов.

## События, которые нужно захватить (клиент‑side → `localStorage` / eventual backend send)

| Название события | Полезная нагрузка (JSON) | Триггер |
|------------------|--------------------------|---------|
| `onboarding_shown` | `{timestamp, version:"v1.4", promptCount:4}` | Первый рендер `showOnboarding()` |
| `onboarding_dismissed` | `{timestamp, key:"justask_onboarding_dismissed"}` | Клик по кнопке.dismiss `dismissOnboarding()` |
| `onboarding_replayed` | `{timestamp}` | Нажатие кнопки «Показать подсказку» при скрытом Onboarding |
| `documents_loaded` | `{documentCount, canManage}` | `applyOnboardingAvailability()` после ответа API |
| `question_sent` | `{questionId, sourceCount, hasSources}` | `sendQuestion()` после запуска SSE |
| `answer_shown` | `{cardId, sourcesCount, answerLength}` | AI‑карточка `.ai-card` добавлена в `#messagesContainer` |
| `feedback_submitted` | `{cardId, isPositive:true|false, ratingTime}` | `rateAnswer()` успешный POST |
| `sample_prompt_selected` | `{promptIndex:0‑3, promptText}` | Клик по любой кнопке `[data-sample-question]` |
| `conversation_cleared` | `{timestamp}` | `clearConversation()` после подтверждения |

## Ключевые метрики (вычисляются из журналов событий)

| Метрика | Определение | Желаемый начальный таргет |
|---------|-------------|---------------------------|
| **Onboarding completion rate** | `% пользователей, которыеDismiss Onboarding в течение 2 сессий` | < 30 % (то есть большинство сохраняет руководство) |
| **Документо‑загрузка** | `% пользователей, которые загрузили хотя бы один файл после Onboarding` | > 20 % |
| **Принятие ответа** | `% Streaming‑ответов, получивших хотя бы один голос обратной связи` | > 40 % |
| **Отношение положительных отзывов** | `% «Да» голосов среди всех отправленных обратной связи` | > 65 % |
| **Наиболее выбранный sample‑prompt** | Индекс и текст с максимальным количеством `sample_prompt_selected` | Должен быть одним из нейро‑архетипов (например, «Объясни ключевые понятия из первой темы») |
| **Длина сессии** | Время от загрузки страницы до `conversation_cleared` или выхода из страницы | < 15 мин в среднем |

## Подход к хранению данных
1. **Временный `localStorage`** — каждое событие добавляет минимальный JSON‑объект; массив сохраняется под ключом `justask_analytics`.
2. **Периодическая выгрузка** — каждые 5 минут или при разгрузке страницы сериализуется массив и отправляется silent `fetch("/api/analytics", {method:"POST", body:JSON.stringify(events)})`.
3. **Серверный endpoint (планируется)** — простой маршрут логирования, который дописывает в файл или питрует легкий дашборд; PII не сохраняется.

## Приватность и соответствие
- В хранящиеся данные не включаются идентифицирующие сведения (имёна, email); используются анонимные ID сессий (генерируются при первом визите, хранятся в `localStorage` под ключом `justask_sessionId`).
- Кнопка отключения (планируется) может устанавливать `localStorage.setItem("justask_analyticsOptOut","1")`; при наличии этого флага события не отправляются.
- GDPR‑friendly retention: автоматическая purge через 30  дней на сервере.

## Чеклист реализации
- [ ] Добавить helpers для событий в `app/static/index.html` (например, `window.analytics = {log(eventName,payload)=>…}`).
- [ ] Создать маршрут `/api/analytics` (POST), если нужна бэкенд‑логирование.
- [ ] Интегрировать тумблер отключения в шапке/настройках.
- [ ] Настроить периодическую выгрузку (`setInterval` или `beforeunload`).
- [ ] спроектировать простой дашборд (React/Flask) для отображения перечисленных метрик.

*Все фрагменты кода должны уважать существующие паттерны `ONBOARDING_KEY` и `hasCourseDocuments`, presentes in the project.*