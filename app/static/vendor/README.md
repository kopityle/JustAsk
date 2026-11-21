# Локальные ассеты фронтенда

Все зависимости страницы лежат здесь, обращения к CDN не выполняются.

| Файл | Источник |
| --- | --- |
| `tailwind.css` | Tailwind CLI **3.4.17**, только классы из `../index.html`, минифицирован |
| `marked.min.js` | `marked@12.0.1` (jsDelivr) |
| `purify.min.js` | `dompurify@3.0.9` (jsDelivr) |
| `highlight.min.js`, `github-dark.min.css` | `highlight.js@11.9.0` (cdnjs) |
| `fonts/*.woff2` | Google Fonts: Moderustic и JetBrains Mono, подмножества `latin` и `cyrillic`; `@font-face` прописаны в `../index.html` |

## Пересборка `tailwind.css`

Статический CSS нужно пересобирать после любого изменения классов в `../index.html`.
Конфиг повторяет бывший инлайн-конфиг Play CDN (`darkMode: 'class'`, цвета
`brand`/`canvas`/`alert`, шрифт `Moderustic`, плагины не подключены — `prose`
намеренно инертен, как и раньше).

```bash
npm i --no-save tailwindcss@3.4.17
npx tailwindcss \
  -c tailwind.config.js \
  -i input.css \
  -o app/static/vendor/tailwind.css \
  --minify
```

где `tailwind.config.js`:

```js
module.exports = {
  content: ['app/static/index.html'],
  darkMode: 'class',
  theme: { extend: {
    fontFamily: { sans: ['Moderustic', 'sans-serif'] },
    colors: {
      brand: { 500: '#0C36CD', 600: '#0C36CD', 700: '#0A005A' },
      canvas: { light: '#F7F7F5', dark: '#18181B' },
      alert: { notfound: '#FF5500', error: '#C5161D' },
    },
  } },
  plugins: [],
};
```

а `input.css` содержит только `@tailwind base; @tailwind components; @tailwind utilities;`.

Размер `vendor/` без README: **≈275 КБ** (из них `highlight.min.js` 119 КБ,
`tailwind.css` 18 КБ, шрифты 81 КБ).
