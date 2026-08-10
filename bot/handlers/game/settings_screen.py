import logging
from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.database import async_session
from bot.models import User
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)


def _quick_defaults() -> dict:
    return {"rounds": 6, "timer": 3, "chips": 10}


async def _get_user(callback: CallbackQuery) -> Optional[User]:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        return result.scalar_one_or_none()


def settings_kb(user: User, total_rounds: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    mod = "✅" if user.modifiers_enabled else "⏸"
    b.button(text=f"{mod} Модификатор ×{user.modifier_multiplier}", callback_data="sett:toggle_mod")
    b.button(text=f"🌍 Континент ×{user.sector_continent}", callback_data="sett:continent")
    b.button(text=f"🏳 Страна ×{user.sector_country}", callback_data="sett:country")
    b.button(text=f"⚙️ Обработка ×{user.sector_process}", callback_data="sett:process")
    b.button(text=f"📐 Прочее ×{user.sector_other}", callback_data="sett:other")
    b.button(text="📏 Лимит ставок по раундам", callback_data="sett:bet_limits")
    qcfg = user.quick_config or _quick_defaults()
    b.button(text=f"⚡ Быстрая: {qcfg['rounds']} раундов / {qcfg['timer']} мин / {qcfg['chips']}♟", callback_data="sett:quick")
    b.button(text="« К игре" if total_rounds else "« Меню", callback_data="game:refresh" if total_rounds else "main_menu")
    b.adjust(1)
    return b.as_markup()


def _cycle(value, options):
    try:
        idx = options.index(value)
    except ValueError:
        idx = 0
    return options[(idx + 1) % len(options)]


@router.callback_query(F.data == "game:settings")
async def cb_settings(callback: CallbackQuery):
    user = await _get_user(callback)
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return

    qcfg = user.quick_config or _quick_defaults()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"Модификатор: {'вкл' if user.modifiers_enabled else 'выкл'} ×{user.modifier_multiplier}\n"
        f"Континент ×{user.sector_continent}\n"
        f"Страна ×{user.sector_country}\n"
        f"Обработка ×{user.sector_process}\n"
        f"Прочее ×{user.sector_other}\n\n"
        f"⚡ <b>Быстрая игра</b>\n"
        f"Раундов: {qcfg['rounds']} | Таймер: {qcfg['timer']} мин | Фишек: {qcfg['chips']}",
        reply_markup=settings_kb(user),
    )
    await callback.answer()


@router.callback_query(F.data == "sett:toggle_mod")
async def cb_toggle_mod(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user: return
        user.modifiers_enabled = not user.modifiers_enabled
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\nМодификатор: {'вкл' if user.modifiers_enabled else 'выкл'} ×{user.modifier_multiplier}",
        reply_markup=settings_kb(user),
    )
    await callback.answer(f"Мод {'вкл' if user.modifiers_enabled else 'выкл'}")


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
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user: return
        current = getattr(user, field)
        setattr(user, field, _cycle(current, [2, 3, 4, 5]))
        await session.commit()
    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n{field}: ×{getattr(user, field)}",
        reply_markup=settings_kb(user),
    )
    await callback.answer(f"×{getattr(user, field)}")


@router.callback_query(F.data == "sett:bet_limits")
async def cb_bet_limits(callback: CallbackQuery):
    user = await _get_user(callback)
    if not user: return

    qcfg = user.quick_config or _quick_defaults()
    tr = qcfg["rounds"]

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
        if not user: return
        qcfg = user.quick_config or _quick_defaults()
        tr = qcfg["rounds"]
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
        if not user: return
        qcfg = user.quick_config or _quick_defaults()
        tr = qcfg["rounds"]
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


@router.callback_query(F.data == "sett:quick")
async def cb_quick_config(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return
        qcfg = user.quick_config or _quick_defaults()
        rounds_opts = [4, 6, 8, 10, 12]
        idx = rounds_opts.index(qcfg["rounds"]) if qcfg["rounds"] in rounds_opts else -1
        qcfg["rounds"] = rounds_opts[(idx + 1) % len(rounds_opts)]
        user.quick_config = qcfg
        await session.commit()

    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"⚡ Быстрая игра: {qcfg['rounds']} раундов / {qcfg['timer']} мин / {qcfg['chips']}♟",
        reply_markup=settings_kb(user),
    )
    await callback.answer(f"Раундов: {qcfg['rounds']}")
