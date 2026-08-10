import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.database import async_session
from bot.models import GameSettings
from bot.services.games import get_active_game_for_host, get_game_by_id

router = Router()
logger = logging.getLogger(__name__)


def _get_or_create_settings(game) -> GameSettings:
    if game.settings is None:
        game.settings = GameSettings(game_id=game.id)
    return game.settings


def settings_kb(s: GameSettings) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mod = "🟢" if s.modifiers_enabled else "⬜"
    b.button(text=f"{mod} Модификатор ×{s.modifier_multiplier}", callback_data="sett:toggle_mod")
    b.button(text=f"🌍 Континент ×{s.sector_continent}", callback_data="sett:continent")
    b.button(text=f"🏳 Страна ×{s.sector_country}", callback_data="sett:country")
    b.button(text=f"⚙️ Обработка ×{s.sector_process}", callback_data="sett:process")
    b.button(text=f"📐 Прочее ×{s.sector_other}", callback_data="sett:other")
    bl = s.bet_limit if s.bet_limit else "нет"
    b.button(text=f"📏 Лимит ставок: {bl}", callback_data="sett:bet_limit")
    b.button(text="« К игре", callback_data="game:refresh")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "game:settings")
async def cb_settings(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Множители игры</b>\n\n"
        f"Модификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}\n"
        f"Континент ×{s.sector_continent}\n"
        f"Страна ×{s.sector_country}\n"
        f"Обработка ×{s.sector_process}\n"
        f"Прочее ×{s.sector_other}\n"
        f"Лимит ставок: {s.bet_limit or 'нет'}",
        reply_markup=settings_kb(s),
    )
    await callback.answer()


def _cycle(value: int, options: list[int]) -> int:
    try:
        idx = options.index(value)
    except ValueError:
        idx = 0
    return options[(idx + 1) % len(options)]


@router.callback_query(F.data == "sett:toggle_mod")
async def cb_toggle_mod(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        s.modifiers_enabled = not s.modifiers_enabled
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Множители игры</b>\n\n"
        f"Модификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}",
        reply_markup=settings_kb(s),
    )
    await callback.answer(f"Мод {'вкл' if s.modifiers_enabled else 'выкл'}")


@router.callback_query(F.data == "sett:continent")
async def cb_continent(callback: CallbackQuery):
    await _cycle_field(callback, "sector_continent")

@router.callback_query(F.data == "sett:country")
async def cb_country(callback: CallbackQuery):
    await _cycle_field(callback, "sector_country")

@router.callback_query(F.data == "sett:process")
async def cb_process(callback: CallbackQuery):
    await _cycle_field(callback, "sector_process")

@router.callback_query(F.data == "sett:other")
async def cb_other(callback: CallbackQuery):
    await _cycle_field(callback, "sector_other")


async def _cycle_field(callback: CallbackQuery, field: str):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        current = getattr(s, field)
        setattr(s, field, _cycle(current, [2, 3, 4, 5]))
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Множители игры</b>\n\n{field}: ×{getattr(s, field)}",
        reply_markup=settings_kb(s),
    )
    await callback.answer(f"×{getattr(s, field)}")


@router.callback_query(F.data == "sett:bet_limit")
async def cb_bet_limit(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        limits = [None, 1, 2, 3, 4, 5]
        current = limits.index(s.bet_limit) if s.bet_limit in limits else 0
        s.bet_limit = limits[(current + 1) % len(limits)]
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Множители игры</b>\n\nЛимит ставок: {s.bet_limit or 'нет'}",
        reply_markup=settings_kb(s),
    )
    await callback.answer(f"Лимит: {s.bet_limit or 'снят'}")
