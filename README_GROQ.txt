Заменить в репозитории chatgpttgbot:
- bot.py
- config.py

На VPS после замены:
cd /root/bots/chatgpttgbot && /root/bots/chatgpttgbot/venv/bin/pip install --upgrade pip openai python-telegram-bot
cd /root/bots/chatgpttgbot && nohup /root/bots/chatgpttgbot/venv/bin/python bot.py > chatgpt.log 2>&1 &
