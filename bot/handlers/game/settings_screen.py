import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.keyboards.game import game_setup_kb, game_waiting_kb
from bot.models import Game, GameSettings
from bot.services.games import get_active_game_for_host, get_game_by_id

router = Router()
logger = logging.getLogger(__name__)


def _get_or_create_settings(game: Game) -> GameSettings:
    if game.settings is None:
        game.settings = GameSettings(game_id=game.id)
    return game.settings


def settings_kb(settings: GameSettings) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mod = "✅" if settings.modifiers_enabled else "⏸"
    b.row(InlineKeyboardButton(
        text=f"{mod} Модификаторы (ложка/дичь/нюхлер)",
        callback_data="sett:toggle_modifiers",
    ))
    bl = settings.bet_limit if settings.bet_limit else "нет"
    b.row(InlineKeyboardButton(
        text=f"📏 Лимит ставок: {bl}",
        callback_data="sett:bet_limit",
    ))
    b.row(InlineKeyboardButton(text="« Назад к игре", callback_data="game:refresh"))
    return b.as_markup()


@router.callback_query(F.data == "game:settings")
async def cb_settings(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"Модификаторы: {'вкл' if s.modifiers_enabled else 'выкл'} (×{s.modifier_multiplier})\n"
        f"Лимит на игрока: {s.modifier_limit}\n"
        f"Лимит ставок в раунде: {s.bet_limit or 'нет'}\n\n"
        f"Множители секторов:\n"
        f"• Континент ×{s.sector_continent}\n"
        f"• Страна ×{s.sector_country}\n"
        f"• Обработка ×{s.sector_process}\n"
        f"• Прочее ×{s.sector_other}",
        reply_markup=settings_kb(s),
    )
    await callback.answer()


@router.callback_query(F.data == "sett:toggle_modifiers")
async def cb_toggle_modifiers(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        s.modifiers_enabled = not s.modifiers_enabled
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"Модификаторы: {'вкл ✅' if s.modifiers_enabled else 'выкл ⏸'} (×{s.modifier_multiplier})\n"
        f"Лимит на игрока: {s.modifier_limit}\n"
        f"Лимит ставок в раунде: {s.bet_limit or 'нет'}",
        reply_markup=settings_kb(s),
    )
    await callback.answer(f"Модификаторы {'вкл' if s.modifiers_enabled else 'выкл'}")


@router.callback_query(F.data == "sett:bet_limit")
async def cb_bet_limit(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        limits = [None, 1, 2, 3, 4, 5]
        current = limits.index(s.bet_limit) if s.bet_limit in limits else 0
        next_idx = (current + 1) % len(limits)
        s.bet_limit = limits[next_idx]
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"Лимит ставок в раунде: <b>{s.bet_limit or 'нет'}</b>",
        reply_markup=settings_kb(s),
    )
    await callback.answer(f"Лимит ставок: {s.bet_limit or 'снят'}")
