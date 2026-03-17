# Mail.tm Telegram Bot for Render

## Что это
Webhook-версия Telegram-бота для Render.

## Что нужно
- GitHub аккаунт
- Render аккаунт
- токен Telegram-бота от BotFather

## Файлы
- `web_bot.py` — основной файл для Render
- `db.py` — локальная SQLite база
- `mailtm.py` — клиент mail.tm
- `requirements.txt`
- `render.yaml`

## Важно
Render free web services засыпают после 15 минут без входящего HTTP-трафика, а просыпаются при следующем запросе. Это не полноценный 24/7 для production, но для хобби и тестов подходит.

## Быстрый деплой
1. Залей эти файлы в новый GitHub-репозиторий.
2. На Render создай новый Web Service из этого репозитория.
3. Укажи переменную `BOT_TOKEN`.
4. После первого деплоя в переменную `RENDER_EXTERNAL_URL` вставь URL вида `https://имя-сервиса.onrender.com`
5. Redeploy.

## Start command
`python web_bot.py`
