import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.database import async_session
from bot.models import GameSettings, User
from bot.services.games import get_active_game_for_host, get_game_by_id
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)


def _get_or_create_settings(game) -> GameSettings:
    if game.settings is None:
        game.settings = GameSettings(game_id=game.id)
    return game.settings


def settings_kb(s: GameSettings, qcfg: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mod = "✅" if s.modifiers_enabled else "⏸"
    b.button(text=f"{mod} Модификатор ×{s.modifier_multiplier}", callback_data="sett:toggle_mod")
    b.button(text=f"🌍 Континент ×{s.sector_continent}", callback_data="sett:continent")
    b.button(text=f"🏳 Страна ×{s.sector_country}", callback_data="sett:country")
    b.button(text=f"⚙️ Обработка ×{s.sector_process}", callback_data="sett:process")
    b.button(text=f"📐 Прочее ×{s.sector_other}", callback_data="sett:other")
    bl = s.bet_limit if s.bet_limit else "нет"
    b.button(text=f"📏 Лимит ставок: {bl}", callback_data="sett:bet_limit")
    b.button(text=f"⚡ Быстрая: {qcfg['rounds']} раундов / {qcfg['timer']} мин / {qcfg['chips']}♟", callback_data="sett:quick")
    b.button(text="« К игре", callback_data="game:refresh")
    b.adjust(1)
    return b.as_markup()


def _quick_defaults() -> dict:
    return {"rounds": 6, "timer": 3, "chips": 10}


async def _get_quick_config(session, user_id: int) -> dict:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return user.quick_config if user and user.quick_config else _quick_defaults()


@router.callback_query(F.data == "game:settings")
async def cb_settings(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        qcfg = await _get_quick_config(session, callback.from_user.id)
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"Модификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}\n"
        f"Континент ×{s.sector_continent}\n"
        f"Страна ×{s.sector_country}\n"
        f"Обработка ×{s.sector_process}\n"
        f"Прочее ×{s.sector_other}\n"
        f"Лимит ставок: {s.bet_limit or 'нет'}\n\n"
        f"⚡ <b>Быстрая игра</b>\n"
        f"Раундов: {qcfg['rounds']} | Таймер: {qcfg['timer']} мин | Фишек: {qcfg['chips']}",
        reply_markup=settings_kb(s, qcfg),
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
        qcfg = await _get_quick_config(session, callback.from_user.id)
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\nМодификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}",
        reply_markup=settings_kb(s, qcfg),
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
        qcfg = await _get_quick_config(session, callback.from_user.id)
        current = getattr(s, field)
        setattr(s, field, _cycle(current, [2, 3, 4, 5]))
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n{field}: ×{getattr(s, field)}",
        reply_markup=settings_kb(s, qcfg),
    )
    await callback.answer(f"×{getattr(s, field)}")


@router.callback_query(F.data == "sett:bet_limit")
async def cb_bet_limit(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        qcfg = await _get_quick_config(session, callback.from_user.id)
        limits = [None, 1, 2, 3, 4, 5]
        current = limits.index(s.bet_limit) if s.bet_limit in limits else 0
        s.bet_limit = limits[(current + 1) % len(limits)]
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\nЛимит ставок: {s.bet_limit or 'нет'}",
        reply_markup=settings_kb(s, qcfg),
    )
    await callback.answer(f"Лимит: {s.bet_limit or 'снят'}")


@router.callback_query(F.data == "sett:quick")
async def cb_quick_config(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)

        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            qcfg = user.quick_config or _quick_defaults()
            rounds_opts = [4, 6, 8, 10, 12]
            idx = rounds_opts.index(qcfg["rounds"]) if qcfg["rounds"] in rounds_opts else -1
            qcfg["rounds"] = rounds_opts[(idx + 1) % len(rounds_opts)]
            user.quick_config = qcfg
        else:
            qcfg = _quick_defaults()
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"⚡ Быстрая игра: {qcfg['rounds']} раундов / {qcfg['timer']} мин / {qcfg['chips']}♟",
        reply_markup=settings_kb(s, qcfg),
    )
    await callback.answer(f"Раундов: {qcfg['rounds']}")
