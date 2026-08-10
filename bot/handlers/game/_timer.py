import asyncio
import logging

from aiogram.exceptions import TelegramAPIError, TelegramNetworkError

from bot.constants import GameStatus
from bot.database import async_session
from bot.services.games import get_game_by_id

logger = logging.getLogger(__name__)

_active_timers: dict[int, dict] = {}


def cancel_timer(bot, game_id: int):
    data = _active_timers.pop(game_id, None)
    if not data:
        return
    task = data.get("task")
    if task and not task.done():
        task.cancel()
    if bot:
        asyncio.create_task(_delete_timer_message(bot, data.get("chat_id"), data.get("message_id")))


async def _delete_timer_message(bot, chat_id, message_id):
    if chat_id and message_id:
        try:
            await bot.delete_message(chat_id, message_id)
        except (TelegramAPIError, TelegramNetworkError) as e:
            logger.warning("Failed to delete timer message: %s", e)


async def _run_timer(bot, chat_id: int, message_id: int, game_id: int, total_seconds: int):
    try:
        remaining = total_seconds
        while remaining > 0:
            await asyncio.sleep(5)
            remaining -= 5
            mins = remaining // 60
            secs = remaining % 60
            text = f"⏱ <b>{mins}:{secs:02d}</b>"

            async with async_session() as session:
                game = await get_game_by_id(session, game_id)
                if not game or game.status != GameStatus.ROUND_ACTIVE:
                    break

            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
            except (TelegramAPIError, TelegramNetworkError) as e:
                logger.warning("Timer update failed: %s", e)

        try:
            await bot.edit_message_text("⏰ <b>Время вышло!</b>", chat_id=chat_id, message_id=message_id)
            await asyncio.sleep(3)
            await bot.delete_message(chat_id, message_id)
        except (TelegramAPIError, TelegramNetworkError) as e:
            logger.warning("Timer cleanup failed: %s", e)
            return

        async with async_session() as session:
            game = await get_game_by_id(session, game_id)
            if game and game.status == GameStatus.ROUND_ACTIVE and game.current_lot:
                game.status = GameStatus.REVEAL
                await session.commit()

        try:
            lot = game.current_lot if game else None
            await bot.send_message(
                chat_id,
                f"⏰ <b>Время вышло!</b>\n\n"
                f"Ставки сделаны, пора ревелить лот «{lot.title if lot else '?'}».\n\n"
                f"Используйте кнопку «Отметить кто угадал» на панели ниже.",
            )
        except (TelegramAPIError, TelegramNetworkError) as e:
            logger.warning("Auto-reveal notification failed: %s", e)

    except asyncio.CancelledError:
        raise


def register_timer(game_id: int, task: asyncio.Task, chat_id: int, message_id: int):
    _active_timers[game_id] = {
        "task": task,
        "chat_id": chat_id,
        "message_id": message_id,
    }
