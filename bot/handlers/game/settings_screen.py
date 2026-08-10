import logging
from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import MODIFIER_LABELS, MODIFIER_TYPES
from bot.database import async_session
from bot.models import User
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)


async def _get_user(callback: CallbackQuery) -> Optional[User]:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        return result.scalar_one_or_none()


def _mod_enabled(user: User, mod_type: str) -> bool:
    if mod_type == "spoon":
        return user.mod_spoon_enabled
    if mod_type == "deer":
        return user.mod_deer_enabled
    if mod_type == "sniffer":
        return user.mod_sniffer_enabled
    return False


def _toggle_mod(user: User, mod_type: str):
    if mod_type == "spoon":
        user.mod_spoon_enabled = not user.mod_spoon_enabled
    elif mod_type == "deer":
        user.mod_deer_enabled = not user.mod_deer_enabled
    elif mod_type == "sniffer":
        user.mod_sniffer_enabled = not user.mod_sniffer_enabled


def _clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(min_val if max_val < min_val else max_val, value))


def _add_value_row(
    builder: InlineKeyboardBuilder,
    label: str,
    value: int,
    minus_cb: str,
    plus_cb: str,
):
    builder.row(
        InlineKeyboardButton(text=f"{label}: {value}", callback_data="sett:nop"),
        InlineKeyboardButton(text="−", callback_data=minus_cb),
        InlineKeyboardButton(text="+", callback_data=plus_cb),
    )


def settings_kb(user: User, total_rounds: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    b.button(text="⚙️ <b>Параметры быстрой игры</b>", callback_data="sett:nop")
    _add_value_row(b, "Раундов", user.default_rounds, "sett:dec:rounds", "sett:inc:rounds")
    _add_value_row(b, "Таймер, мин", user.default_timer, "sett:dec:timer", "sett:inc:timer")
    _add_value_row(b, "Фишек", user.default_chips, "sett:dec:chips", "sett:inc:chips")

    b.button(text="🧪 Множители", callback_data="sett:nop")
    _add_value_row(b, "Модификатор", user.modifier_multiplier, "sett:dec:mod_mult", "sett:inc:mod_mult")
    _add_value_row(b, "Континент", user.sector_continent, "sett:dec:continent", "sett:inc:continent")
    _add_value_row(b, "Страна", user.sector_country, "sett:dec:country", "sett:inc:country")
    _add_value_row(b, "Обработка", user.sector_process, "sett:dec:process", "sett:inc:process")
    _add_value_row(b, "Прочее", user.sector_other, "sett:dec:other", "sett:inc:other")

    for mod_type in MODIFIER_TYPES:
        enabled = _mod_enabled(user, mod_type)
        icon = "✅" if enabled else "⏸"
        label = MODIFIER_LABELS.get(mod_type, mod_type)
        b.button(text=f"{icon} {label}", callback_data=f"sett:toggle_mod:{mod_type}")

    b.button(text="📏 Лимит ставок по раундам", callback_data="sett:bet_limits")
    b.button(text="« К игре" if total_rounds else "« Меню", callback_data="game:refresh" if total_rounds else "main_menu")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "sett:nop")
async def cb_nop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "game:settings")
async def cb_settings(callback: CallbackQuery):
    user = await _get_user(callback)
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return

    mod_status = []
    for mod_type in MODIFIER_TYPES:
        enabled = _mod_enabled(user, mod_type)
        label = MODIFIER_LABELS.get(mod_type, mod_type)
        mod_status.append(f"{'вкл' if enabled else 'выкл'} {label}")
    mod_status_text = "\n  ".join(mod_status)

    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"<b>Параметры быстрой игры:</b>\n"
        f"  Раундов: {user.default_rounds}\n"
        f"  Таймер: {user.default_timer} мин\n"
        f"  Фишек: {user.default_chips}\n\n"
        f"<b>Множители:</b>\n"
        f"  Модификатор: ×{user.modifier_multiplier}\n"
        f"  Континент: ×{user.sector_continent}\n"
        f"  Страна: ×{user.sector_country}\n"
        f"  Обработка: ×{user.sector_process}\n"
        f"  Прочее: ×{user.sector_other}\n\n"
        f"<b>Модификаторы:</b>\n"
        f"  {mod_status_text}\n\n"
        f"Используйте кнопки ниже, чтобы изменить значения.",
        reply_markup=settings_kb(user),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sett:inc:") | F.data.startswith("sett:dec:"))
async def cb_adjust_value(callback: CallbackQuery):
    parts = callback.data.split(":")
    direction = parts[1]
    field = parts[2]

    field_limits = {
        "rounds": (1, 12, 1),
        "timer": (0, 30, 1),
        "chips": (1, 1000, 5),
        "mod_mult": (2, 5, 1),
        "continent": (2, 5, 1),
        "country": (2, 5, 1),
        "process": (2, 5, 1),
        "other": (2, 5, 1),
    }

    model_field_map = {
        "rounds": "default_rounds",
        "timer": "default_timer",
        "chips": "default_chips",
        "mod_mult": "modifier_multiplier",
        "continent": "sector_continent",
        "country": "sector_country",
        "process": "sector_process",
        "other": "sector_other",
    }

    model_field = model_field_map.get(field)
    limits = field_limits.get(field)
    if not model_field or not limits:
        await callback.answer("Ошибка", show_alert=True)
        return

    min_val, max_val, step = limits
    delta = step if direction == "inc" else -step

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        current = getattr(user, model_field)
        new_value = _clamp(current + delta, min_val, max_val)
        setattr(user, model_field, new_value)
        await session.commit()

    await cb_settings(callback)


@router.callback_query(F.data.startswith("sett:toggle_mod:"))
async def cb_toggle_mod(callback: CallbackQuery):
    mod_type = callback.data.split(":")[2]
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user or mod_type not in MODIFIER_TYPES:
            await callback.answer("Ошибка", show_alert=True)
            return
        _toggle_mod(user, mod_type)
        await session.commit()
    await cb_settings(callback)


@router.callback_query(F.data == "sett:bet_limits")
async def cb_bet_limits(callback: CallbackQuery):
    user = await _get_user(callback)
    if not user:
        return

    tr = user.default_rounds
    limits = user.bet_limits_json or []
    while len(limits) < tr:
        limits.append(None)

    b = InlineKeyboardBuilder()
    for r in range(tr):
        val = limits[r]
        label = f"Раунд {r+1}: {val if val else 'без лимита'}"
        b.button(text=label, callback_data=f"sett:bl_round:{r}")
    b.button(text="📐 Применить ко всем", callback_data="sett:bl_all")
    b.button(text="« Настройки", callback_data="game:settings")
    b.adjust(1)

    await callback.message.edit_text(
        f"📏 <b>Лимит ставок — {tr} раундов</b>\n\nВыберите раунд чтобы изменить лимит",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sett:bl_round:"))
async def cb_bl_round(callback: CallbackQuery):
    round_idx = int(callback.data.split(":")[2])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            return
        tr = user.default_rounds
        limits = list(user.bet_limits_json or [])
        while len(limits) < tr:
            limits.append(None)
        limits[round_idx] = _cycle(limits[round_idx] or 0, [None, 1, 2, 3, 4, 5])
        user.bet_limits_json = limits
        await session.commit()

    b = InlineKeyboardBuilder()
    for r in range(tr):
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
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            return
        tr = user.default_rounds
        limits = list(user.bet_limits_json or [])
        while len(limits) < tr:
            limits.append(None)
        values = [l for l in limits if l is not None]
        current = max(set(values), key=values.count) if values else 3
        new_val = _cycle(current, [1, 2, 3, 4, 5, None])
        limits = [new_val] * tr
        user.bet_limits_json = limits
        await session.commit()

    await callback.answer(f"Все раунды: {new_val or 'без лимита'}")
    await cb_bet_limits(callback)


def _cycle(value, options):
    try:
        idx = options.index(value)
    except ValueError:
        idx = 0
    return options[(idx + 1) % len(options)]
