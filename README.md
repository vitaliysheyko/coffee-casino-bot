# Coffee Casino Bot

Telegram-бот помощник для игры «Кофейное казино».  
Гибридный формат: физическое поле + фишки + бот-ассистент.

## Стек

- Python 3.12
- aiogram 3.x
- SQLite + SQLAlchemy (async)

## Деплой на Railway

1. Зайди на [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Выбери репозиторий `vitaliysheyko/coffee-casino-bot`
3. В Variables добавь:
   ```
   BOT_TOKEN=твой_токен_от_BotFather
   ```
4. Deploy

Бот запустится командой `python main.py`.

### Важно про базу

Сейчас используется SQLite. На Railway данные могут сброситься при редеплое.  
Для продакшена позже можно подключить PostgreSQL (Railway даёт его в 1 клик).

## Локальный запуск

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN
python main.py
```

## Возможности MVP

**Ведущий:** лоты, создание игры, раунды, факт, ревейл  
**Игрок:** join по ссылке, ставки, просмотр ответов
