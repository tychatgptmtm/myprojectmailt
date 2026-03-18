Это версия почтового бота для обычного VPS.

Что изменено:
1. Убран webhook и Render
2. Бот работает через long polling
3. База переведена с Postgres на локальную SQLite
4. Запуск теперь обычный: python3 bot.py

Что должно быть на VPS:
- Python 3
- pip
- токен Telegram бота

Команды установки:
apt update && apt install -y python3 python3-pip python3-venv git

Команды запуска:
cd /root/myprojectmailt
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
nohup env BOT_TOKEN=ТВОЙ_ТОКЕН /root/myprojectmailt/venv/bin/python bot.py > mail.log 2>&1 &

Проверка логов:
tail -f /root/myprojectmailt/mail.log
