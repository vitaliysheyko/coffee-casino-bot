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


def settings_kb(s: GameSettings, qcfg: dict, total_rounds: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mod = "✅" if s.modifiers_enabled else "⏸"
    b.button(text=f"{mod} Модификатор ×{s.modifier_multiplier}", callback_data="sett:toggle_mod")
    b.button(text=f"🌍 Континент ×{s.sector_continent}", callback_data="sett:continent")
    b.button(text=f"🏳 Страна ×{s.sector_country}", callback_data="sett:country")
    b.button(text=f"⚙️ Обработка ×{s.sector_process}", callback_data="sett:process")
    b.button(text=f"📐 Прочее ×{s.sector_other}", callback_data="sett:other")

    limits = s.bet_limits_json or []
    while len(limits) < total_rounds:
        limits.append(None)
    limit_text = "📏 Лимит ставок: " + " · ".join(
        f"R{r+1}:{v if v else '—'}" for r, v in enumerate(limits[:total_rounds])
    )
    b.button(text=limit_text, callback_data="sett:bet_limits")

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

    limits = s.bet_limits_json or []
    while len(limits) < game.total_rounds:
        limits.append(None)
    limit_text = " · ".join(f"R{r+1}:{v if v else '—'}" for r, v in enumerate(limits[:game.total_rounds]))

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n"
        f"Модификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}\n"
        f"Континент ×{s.sector_continent}\n"
        f"Страна ×{s.sector_country}\n"
        f"Обработка ×{s.sector_process}\n"
        f"Прочее ×{s.sector_other}\n\n"
        f"📏 <b>Лимит ставок по раундам:</b>\n{limit_text}\n\n"
        f"⚡ <b>Быстрая игра</b>\n"
        f"Раундов: {qcfg['rounds']} | Таймер: {qcfg['timer']} мин | Фишек: {qcfg['chips']}",
        reply_markup=settings_kb(s, qcfg, game.total_rounds),
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
        tr = game.total_rounds
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\nМодификатор: {'вкл' if s.modifiers_enabled else 'выкл'} ×{s.modifier_multiplier}",
        reply_markup=settings_kb(s, qcfg, tr),
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
        tr = game.total_rounds
        current = getattr(s, field)
        setattr(s, field, _cycle(current, [2, 3, 4, 5]))
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки игры</b>\n\n{field}: ×{getattr(s, field)}",
        reply_markup=settings_kb(s, qcfg, tr),
    )
    await callback.answer(f"×{getattr(s, field)}")


@router.callback_query(F.data == "sett:bet_limit")
async def cb_bet_limit(callback: CallbackQuery):
    await cb_bet_limits(callback)


@router.callback_query(F.data == "sett:bet_limits")
async def cb_bet_limits(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        await session.commit()

    limits = list(s.bet_limits_json or [])
    while len(limits) < game.total_rounds:
        limits.append(None)

    b = InlineKeyboardBuilder()
    for r in range(game.total_rounds):
        val = limits[r]
        label = f"Раунд {r+1}: {val if val else 'без лимита'}"
        b.button(text=label, callback_data=f"sett:bl_round:{r}")
    b.button(text="📐 Применить ко всем", callback_data="sett:bl_all")
    b.button(text="« Настройки", callback_data="game:settings")
    b.adjust(1)

    await callback.message.edit_text(
        f"📏 <b>Лимит ставок — {game.total_rounds} раундов</b>\n\nВыберите раунд чтобы изменить лимит",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sett:bl_round:"))
async def cb_bl_round(callback: CallbackQuery):
    round_idx = int(callback.data.split(":")[2])

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        limits = list(s.bet_limits_json or [])
        while len(limits) < game.total_rounds:
            limits.append(None)
        limits[round_idx] = _cycle(limits[round_idx] or 0, [None, 1, 2, 3, 4, 5])
        s.bet_limits_json = limits
        await session.commit()

    b = InlineKeyboardBuilder()
    for r in range(game.total_rounds):
        val = limits[r]
        label = f"Раунд {r+1}: {val if val else 'без лимита'}"
        b.button(text=label, callback_data=f"sett:bl_round:{r}")
    b.button(text="📐 Применить ко всем", callback_data="sett:bl_all")
    b.button(text="« Настройки", callback_data="game:settings")
    b.adjust(1)

    await callback.message.edit_text(
        f"📏 <b>Лимит ставок</b>\n\nРаунд {round_idx+1}: {limits[round_idx] or 'без лимита'}",
        reply_markup=b.as_markup(),
    )
    await callback.answer(f"Раунд {round_idx+1}: {limits[round_idx] or 'без лимита'}")


@router.callback_query(F.data == "sett:bl_all")
async def cb_bl_all(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        limits = s.bet_limits_json or []
        while len(limits) < game.total_rounds:
            limits.append(None)
        values = [l for l in limits if l is not None]
        current = max(set(values), key=values.count) if values else 3
        new_val = _cycle(current, [1, 2, 3, 4, 5, None])
        limits = [new_val] * game.total_rounds
        s.bet_limits_json = limits
        await session.commit()

    await callback.answer(f"Все раунды: {new_val or 'без лимита'}")
    await cb_bet_limits(callback)


@router.callback_query(F.data == "sett:quick")
async def cb_quick_config(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game: return
        game = await get_game_by_id(session, game.id)
        s = _get_or_create_settings(game)
        tr = game.total_rounds

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
        reply_markup=settings_kb(s, qcfg, tr),
    )
    await callback.answer(f"Раундов: {qcfg['rounds']}")
