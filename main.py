import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from urllib.parse import parse_qs, urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database import init_db, async_session
from bot.handlers import start, lots, game, history, errors
from bot.models import Game
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 10000))
WEB_PORT = int(os.environ.get("WEB_PORT", settings.web_port))

TIMER_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Кофейное казино — Таймер</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1b0f; color: #e8d5a3;
    font-family: 'Georgia', serif;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100vh; text-align: center;
  }
  .timer-container {
    background: #1a2f1d;
    border: 4px solid #c9a84c;
    border-radius: 24px;
    padding: 60px 80px;
    box-shadow: 0 0 60px rgba(201,168,76,0.3);
  }
  .label { font-size: 28px; color: #c9a84c; margin-bottom: 20px; }
  .round { font-size: 22px; color: #8b9a6b; margin-bottom: 10px; }
  .timer { font-size: 140px; font-weight: bold; color: #f0e6c8; line-height: 1; }
  .status { font-size: 32px; color: #c9a84c; margin-top: 20px; }
  .warning { color: #d4845a; }
  .flash { animation: flash 1s infinite; }
  @keyframes flash { 50% { opacity: 0.3; } }
</style>
</head>
<body>
<div class="timer-container">
  <div class="label">☕ КОФЕЙНОЕ КАЗИНО</div>
  <div class="round" id="round_info"></div>
  <div class="timer" id="timer">--:--</div>
  <div class="status" id="status">Ожидание...</div>
</div>
<script>
  let timerData = null;
  async function fetchTimer() {
    try {
      const res = await fetch('/timer/' + window.location.pathname.split('/').pop());
      if (res.ok) {
        timerData = await res.json();
        updateDisplay();
      }
    } catch(e) {}
  }
  function updateDisplay() {
    if (!timerData) { document.getElementById('status').textContent = 'Игра не найдена'; return; }
    const t = timerData;
    if (t.status === 'waiting') {
      document.getElementById('status').textContent = 'Скоро начнём...';
      document.getElementById('timer').textContent = '--:--';
      document.getElementById('round_info').textContent = t.lot_title ? t.lot_title : '';
    } else if (t.status === 'finished') {
      document.getElementById('status').textContent = 'Игра завершена';
      document.getElementById('timer').textContent = '00:00';
      document.getElementById('round_info').textContent = '';
    } else if (t.status === 'reveal') {
      document.getElementById('status').textContent = 'РЕВЕЙЛ';
      document.getElementById('timer').textContent = '00:00';
      document.getElementById('timer').classList.add('flash');
      document.getElementById('round_info').textContent = 'Раунд ' + t.round + (t.lot_title ? ' — ' + t.lot_title : '');
    } else {
      document.getElementById('timer').classList.remove('flash');
      const min = Math.floor(t.remaining / 60);
      const sec = t.remaining % 60;
      document.getElementById('timer').textContent = String(min).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
      document.getElementById('round_info').textContent = 'Раунд ' + t.round + (t.lot_title ? ' — ' + t.lot_title : '');
      if (t.remaining <= 30) {
        document.getElementById('timer').classList.add('warning');
        document.getElementById('status').textContent = 'Финальный отсчёт!';
      } else {
        document.getElementById('timer').classList.remove('warning');
        document.getElementById('status').textContent = 'Ставки принимаются';
      }
    }
  }
  fetchTimer();
  setInterval(fetchTimer, 2000);
</script>
</body>
</html>"""


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_html(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health" or path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return

        if path.startswith("/timer/"):
            code = path.split("/")[-1].upper()
            if self.path.endswith("/json") or "json" in parsed.query:
                self._handle_timer_api(code)
            else:
                self._send_html(200, TIMER_HTML)
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not found")

    def _handle_timer_api(self, code: str):
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self._get_timer_data(code))
        finally:
            loop.close()

        if result is None:
            self._send_json(404, {"error": "game not found"})
            return

        self._send_json(200, result)

    async def _get_timer_data(self, code: str):
        async with async_session() as session:
            result = await session.execute(
                select(Game).where(Game.code == code, Game.status != "finished")
            )
            game = result.scalar_one_or_none()
            if not game:
                result = await session.execute(
                    select(Game).where(Game.code == code)
                )
                game = result.scalar_one_or_none()

            if not game:
                return None

            remaining = 0
            if game.status == "round_active" and game.round_started_at:
                elapsed = (datetime.now(timezone.utc) - game.round_started_at).total_seconds()
                total = (game.timer_minutes or 5) * 60
                remaining = max(0, total - elapsed)

            lot_title = game.current_lot.title if game.current_lot else None
            return {
                "code": game.code,
                "status": game.status,
                "round": game.current_round,
                "total_rounds": game.total_rounds,
                "remaining": int(remaining),
                "lot_title": lot_title,
            }


def run_web_server():
    server = HTTPServer(("0.0.0.0", WEB_PORT), WebHandler)
    logger.info("Web server started on port %s", WEB_PORT)
    server.serve_forever()


async def main():
    await init_db()
    logger.info("Database initialized")

    Thread(target=run_web_server, daemon=True).start()
    logger.info("Web server started on port %s", WEB_PORT)

    from aiogram.client.session.aiohttp import AiohttpSession
    session = AiohttpSession(timeout=60)
    
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(lots.router)
    dp.include_router(game.router)
    dp.include_router(history.router)
    dp.include_router(errors.router)

    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
