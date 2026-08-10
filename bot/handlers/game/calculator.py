from __future__ import annotations

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import MODIFIER_LABELS, MODIFIER_TYPES, GameStatus
from bot.database import async_session
from bot.models import RoundResult, User
from bot.services.games import get_active_game_for_host, get_game_by_id
from bot.services.scoring import count_modifier_usage
from sqlalchemy import select

router = Router()
logger = logging.getLogger(__name__)

CHIPS = [5, 10, 25, 50, 100]


async def _get_game_settings(callback: CallbackQuery) -> tuple[list[int], int, list[str]]:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            mults = list(dict.fromkeys([user.sector_continent, user.sector_country, user.sector_process, user.sector_other]))
            enabled_mods = []
            for mod_type in MODIFIER_TYPES:
                if getattr(user, f"mod_{mod_type}_enabled", False):
                    enabled_mods.append(mod_type)
            return sorted(mults), user.modifier_multiplier, enabled_mods
    return [2, 3], 2, []


def _player_calc_kb(
    player_id: int,
    modifier_type: Optional[str],
    has_bets: bool,
    mults: list[int],
    mod_mult: int,
    enabled_mods: list[str],
    prev_id: int = 0,
    next_id: int = 0,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    for val in CHIPS:
        b.button(text=str(val), callback_data=f"calc:chip:{player_id}:{val}")
    b.adjust(len(CHIPS))

    b.button(text="❌", callback_data=f"calc:mult:{player_id}:0")
    for m in mults:
        b.button(text=f"×{m}", callback_data=f"calc:mult:{player_id}:{m}")
    b.adjust(1 + len(mults))

    if enabled_mods:
        for mod_type in enabled_mods:
            label = MODIFIER_LABELS.get(mod_type, mod_type)
            prefix = "✅ " if modifier_type == mod_type else "⬜ "
            b.button(text=f"{prefix}{label} ×{mod_mult}", callback_data=f"calc:mod:{player_id}:{mod_type}")
        none_text = "✅ Без модификатора" if not modifier_type else "⬜ Без модификатора"
        b.button(text=none_text, callback_data=f"calc:mod:{player_id}:none")
    else:
        b.button(text="🚫 Модификаторы отключены", callback_data="calc:no_mods")

    if has_bets:
        b.button(text="↩ Отменить", callback_data=f"calc:undo:{player_id}")
        b.button(text="💾 Сохранить", callback_data=f"calc:save:{player_id}")

    nav = []
    if prev_id:
        nav.append(InlineKeyboardButton(text="◀ Пред", callback_data=f"calc:open:{prev_id}"))
    b.button(text="« Список", callback_data="game:calculator")
    if next_id:
        nav.append(InlineKeyboardButton(text="След ▶", callback_data=f"calc:open:{next_id}"))
    if nav:
        b.row(*nav)

    return b.as_markup()


def _round_total(bets: list, mod_type: Optional[str], mod_mult: int = 2) -> int:
    won = sum(b["amount"] * b["mult"] for b in bets if b["mult"])
    lost = sum(b["amount"] for b in bets if not b["mult"])
    if mod_type and won > 0:
        won *= mod_mult
    return won - lost


def _format_bets(bets: list) -> str:
    if not bets:
        return "—"
    lines = []
    for i, bet in enumerate(bets, 1):
        amt = bet["amount"]
        m = bet["mult"]
        if m == 0:
            lines.append(f"{i}. {amt}♟ ❌ = −{amt}")
        else:
            lines.append(f"{i}. {amt}♟ ×{m} = +{amt * m}")
    return "\n".join(lines)


async def _get_calc_state(state: FSMContext):
    d = await state.get_data()
    return d.get("calc_bets", []), d.get("calc_mod_type")


@router.callback_query(F.data == "game:calculator")
async def cb_calculator(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        players = list(game.players)

    if not players:
        await callback.answer("Нет игроков", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for p in players:
        b.button(text=f"{p.display_name} ({p.total_score}♟)", callback_data=f"calc:open:{p.id}")
    b.adjust(1)
    b.button(text="« Назад к игре", callback_data="game:refresh")

    await callback.message.edit_text("🧮 <b>Калькулятор</b>\n\nВыберите игрока:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("calc:open:"))
async def cb_calc_open(callback: CallbackQuery, state: FSMContext):
    player_id = int(callback.data.split(":")[2])
    await state.update_data(calc_player_id=player_id, calc_bets=[], calc_mod_type=None)
    await _render(callback, state)
    await callback.answer()


async def _render(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    player_id = d.get("calc_player_id")
    if not player_id:
        return
    bets = d.get("calc_bets", [])
    mod_type = d.get("calc_mod_type")

    mults, mod_mult, enabled_mods = await _get_game_settings(callback)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.message.edit_text("Нет игры.", reply_markup=InlineKeyboardBuilder().as_markup())
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)

    if not player:
        await callback.message.edit_text("Игрок не найден.")
        return

    ids = [p.id for p in game.players]
    idx = ids.index(player_id)
    prev_id = ids[idx - 1] if idx > 0 else 0
    next_id = ids[idx + 1] if idx < len(ids) - 1 else 0

    rt = _round_total(bets, mod_type, mod_mult)
    won = sum(b["amount"] * b["mult"] for b in bets if b["mult"])
    lost = sum(b["amount"] for b in bets if not b["mult"])

    mod_label = ""
    if mod_type:
        mod_label = f"\n🧪 Модификатор: {MODIFIER_LABELS.get(mod_type, mod_type)} ×{mod_mult}"

    text = (
        f"🧮 <b>{player.display_name}</b>\n"
        f"Баланс: {player.total_score}♟\n\n"
        f"<b>Ставки:</b>\n{_format_bets(bets)}\n"
    )
    if won:
        text += f"\n<b>Выигрыш: +{won}♟</b>"
        if mod_type:
            text += f" → ×{mod_mult}🧪 = <b>+{won * mod_mult}♟</b>"
    if lost:
        text += f"\n<b>Проигрыш: −{lost}♟</b>"
    text += f"\n\n<b>Итого раунд: {rt:+d}♟</b>\n"
    text += f"После раунда: <b>{player.total_score + rt}♟</b>{mod_label}"

    await callback.message.edit_text(
        text,
        reply_markup=_player_calc_kb(player_id, mod_type, len(bets) > 0, mults, mod_mult, enabled_mods, prev_id, next_id),
    )


@router.callback_query(F.data == "calc:no_mods")
async def cb_calc_no_mods(callback: CallbackQuery):
    await callback.answer("Модификаторы отключены в настройках", show_alert=True)


@router.callback_query(F.data.startswith("calc:mod:"))
async def cb_calc_mod(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    player_id = int(parts[2])
    mod_type = parts[3]

    if mod_type == "none":
        await state.update_data(calc_mod_type=None)
        await _render(callback, state)
        await callback.answer("Без модификатора")
        return

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет игры", show_alert=True)
            return
        usage = await count_modifier_usage(session, game.id, player_id, mod_type)

    if usage >= 2:
        await callback.answer(f"Лимит {MODIFIER_LABELS.get(mod_type, mod_type)} исчерпан", show_alert=True)
        return

    await state.update_data(calc_mod_type=mod_type)
    await _render(callback, state)
    await callback.answer(f"{MODIFIER_LABELS.get(mod_type, mod_type)} ON")


@router.callback_query(F.data.startswith("calc:chip:"))
async def cb_calc_chip(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    amount = int(parts[3])
    await state.update_data(calc_pending=amount)
    d = await state.get_data()
    bets = d.get("calc_bets", [])
    mod_type = d.get("calc_mod_type")
    player_id = d.get("calc_player_id")

    mults, mod_mult, enabled_mods = await _get_game_settings(callback)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game = await get_game_by_id(session, game.id)
            ids = [p.id for p in game.players]
            idx = ids.index(player_id) if player_id in ids else -1
            prv = ids[idx - 1] if idx > 0 else 0
            nxt = ids[idx + 1] if 0 <= idx < len(ids) - 1 else 0
        else:
            prv = nxt = 0

    await callback.message.edit_text(
        callback.message.html_text + f"\n\n▸ <b>{amount}♟</b> — [❌] [{'/'.join(f'×{m}' for m in mults)}]",
        reply_markup=_player_calc_kb(player_id, mod_type, len(bets) > 0, mults, mod_mult, enabled_mods, prv, nxt),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("calc:mult:"))
async def cb_calc_mult(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    mult = int(parts[3])
    d = await state.get_data()
    amount = d.get("calc_pending", 0)
    bets = list(d.get("calc_bets", []))
    bets.append({"amount": amount, "mult": mult})
    await state.update_data(calc_bets=bets, calc_pending=0)
    await _render(callback, state)

    label = "❌" if mult == 0 else f"×{mult}"
    await callback.answer(f"{amount}♟ {label}")


@router.callback_query(F.data.startswith("calc:undo:"))
async def cb_calc_undo(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    bets = list(d.get("calc_bets", []))
    if bets:
        bets.pop()
        await state.update_data(calc_bets=bets)
    await _render(callback, state)
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("calc:save:"))
async def cb_calc_save(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    player_id = d.get("calc_player_id")
    bets = d.get("calc_bets", [])
    mod_type = d.get("calc_mod_type")

    if not bets:
        await callback.answer("Нет ставок для сохранения", show_alert=True)
        return

    _, mod_mult, _ = await _get_game_settings(callback)
    rt = _round_total(bets, mod_type, mod_mult)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)
        if not player:
            await callback.answer("Игрок не найден", show_alert=True)
            return

        player.total_score += rt

        round_recorded = False
        if game.current_round > 0 and game.current_lot_id:
            result = await session.execute(
                select(RoundResult).where(
                    RoundResult.game_id == game.id,
                    RoundResult.player_id == player.id,
                    RoundResult.round_number == game.current_round,
                    RoundResult.source == "calculator",
                )
            )
            rr = result.scalar_one_or_none()
            if rr:
                rr.chips_won = rt
                rr.modifier_type = mod_type
                rr.modifier_applied = bool(mod_type)
            else:
                rr = RoundResult(
                    game_id=game.id,
                    player_id=player.id,
                    lot_id=game.current_lot_id,
                    round_number=game.current_round,
                    modifier_type=mod_type,
                    modifier_applied=bool(mod_type),
                    source="calculator",
                    chips_won=rt,
                )
                session.add(rr)
            round_recorded = True

        await session.commit()
        name = player.display_name
        new_balance = player.total_score

    await state.update_data(calc_bets=[], calc_mod_type=None)
    await _render(callback, state)
    msg = f"{name}: {rt:+d}♟ → {new_balance}♟"
    if not round_recorded:
        msg += " (баланс обновлён, история раунда недоступна)"
    await callback.answer(msg)
