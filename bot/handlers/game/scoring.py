from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.constants import GameStatus, MODIFIER_LABELS, MODIFIER_TYPES
from bot.database import async_session
from bot.keyboards.game import (
    build_modifier_kb,
    build_round_result_kb,
    reveal_kb,
)
from bot.keyboards.common import main_menu_kb
from bot.services.games import get_active_game_for_host, get_game_by_id
from bot.services.lots import get_lot_by_id, format_lot_for_host
from bot.services.scoring import (
    active_categories,
    apply_round_result,
    count_modifier_usage,
    format_round_summary,
)
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:score_round")
async def cb_score_round(callback: CallbackQuery, state: FSMContext):
    logger.info("cb_score_round called by user %s", callback.from_user.id)
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.REVEAL:
            logger.warning("No active game in REVEAL status for user %s", callback.from_user.id)
            await callback.answer("Нет раунда для подсчёта", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        players = list(game.players)
        lot = game.current_lot
        host = game.host

    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return

    cats = active_categories(lot)
    if not cats:
        await callback.answer("Нет категорий для ставок", show_alert=True)
        return

    enabled_mods = []
    if host:
        for mod_type in MODIFIER_TYPES:
            if getattr(host, f"mod_{mod_type}_enabled", False):
                enabled_mods.append(mod_type)

    player_data = {p.id: p.display_name for p in players}
    await state.update_data(
        scoring_round=game.current_round,
        scoring_lot_id=lot.id,
        scoring_players=player_data,
        scoring_cats=cats,
        scoring_idx=0,
        scoring_results={},
        scoring_modifiers={},
        scoring_host_id=callback.from_user.id,
        scoring_modifiers_enabled=enabled_mods,
        modifier_multiplier=host.modifier_multiplier if host else 2,
    )
    await state.set_state(GameForm.scoring)
    logger.info("FSM state set to GameForm.scoring, players: %s", list(player_data.keys()))
    await _show_scoring_for_player(callback.message, state, 0, cats, player_data)
    await callback.answer()


async def _show_scoring_for_player(
    target: Message, state: FSMContext, idx: int, cats: list[str], player_data: dict[int, str]
):
    ids = list(player_data.keys())
    if idx >= len(ids):
        await _finish_scoring(target, state)
        return

    player_id = ids[idx]
    name = player_data[player_id]
    await target.edit_text(
        f"Кто угадал?\n\nИгрок: <b>{name}</b>\nВыберите угаданные категории:",
        reply_markup=build_round_result_kb(player_id, cats),
    )


@router.callback_query(GameForm.scoring, F.data == "scoring:cancel")
async def cb_scoring_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.message.edit_text("Игра не найдена.", reply_markup=main_menu_kb())
            await callback.answer()
            return
        game = await get_game_by_id(session, game.id)
        lot = game.current_lot
        is_last = game.current_round >= game.total_rounds

    await callback.message.edit_text(
        f"🔍 <b>Ревел — Раунд {game.current_round}</b>\n\n"
        f"{format_lot_for_host(lot) if lot else 'Лот не найден'}",
        reply_markup=reveal_kb(is_last),
    )
    await callback.answer()


@router.callback_query(GameForm.scoring, F.data.startswith("scoring:cat:"))
async def cb_scoring_toggle(callback: CallbackQuery, state: FSMContext):
    logger.info("cb_scoring_toggle called: %s", callback.data)
    _, _, player_id_str, cat = callback.data.split(":")
    player_id = int(player_id_str)

    data = await state.get_data()
    results = data.get("scoring_results", {})
    player_key = str(player_id)
    if player_key not in results:
        results[player_key] = {}
    results[player_key][cat] = not results[player_key].get(cat, False)
    await state.update_data(scoring_results=results)

    cats = data["scoring_cats"]
    player_data = data["scoring_players"]
    await callback.message.edit_text(
        f"Кто угадал?\n\nИгрок: <b>{player_data[player_id]}</b>\nВыберите угаданные категории:",
        reply_markup=build_round_result_kb(player_id, cats, results[player_key]),
    )
    await callback.answer()


@router.callback_query(GameForm.scoring, F.data.startswith("scoring:done:"))
async def cb_scoring_done(callback: CallbackQuery, state: FSMContext):
    logger.info("cb_scoring_done called: %s", callback.data)
    _, _, player_id_str = callback.data.split(":")
    player_id = int(player_id_str)

    data = await state.get_data()
    enabled_mods = data.get("scoring_modifiers_enabled", [])

    if enabled_mods:
        await state.set_state(GameForm.scoring_modifier)
        await _show_modifier_for_player(callback.message, state, player_id)
    else:
        idx = data["scoring_idx"] + 1
        await state.update_data(scoring_idx=idx)

        cats = data["scoring_cats"]
        player_data = data["scoring_players"]
        await _show_scoring_for_player(callback.message, state, idx, cats, player_data)

    await callback.answer()


async def _show_modifier_for_player(target: Message, state: FSMContext, player_id: int):
    data = await state.get_data()
    player_data = data["scoring_players"]
    player_name = player_data.get(player_id, "Игрок")
    current_modifier = data.get("scoring_modifiers", {}).get(str(player_id))

    game_id = None
    async with async_session() as session:
        game = await get_active_game_for_host(session, data["scoring_host_id"])
        if game:
            game_id = game.id

    usage_counts = {}
    if game_id:
        async with async_session() as session:
            for mod_type in MODIFIER_TYPES:
                usage_counts[mod_type] = await count_modifier_usage(session, game_id, player_id, mod_type)

    host_id = data["scoring_host_id"]
    user = None
    async with async_session() as session:
        from bot.models import User
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.id == host_id))
        user = result.scalar_one_or_none()

    await target.edit_text(
        f"🧪 <b>Модификатор</b>\n\nИгрок: <b>{player_name}</b>\nВыберите модификатор (лимит 2 раза за игру):",
        reply_markup=build_modifier_kb(player_id, user, usage_counts, current_modifier),
    )


@router.callback_query(GameForm.scoring_modifier, F.data == "scoring:mod_limit")
async def cb_scoring_mod_limit(callback: CallbackQuery):
    await callback.answer("Лимит использования этого модификатора исчерпан", show_alert=True)


@router.callback_query(GameForm.scoring_modifier, F.data.startswith("scoring:mod:"))
async def cb_scoring_mod(callback: CallbackQuery, state: FSMContext):
    logger.info("cb_scoring_mod called: %s", callback.data)
    _, _, player_id_str, mod_type = callback.data.split(":")
    player_id = int(player_id_str)

    data = await state.get_data()
    modifiers = data.get("scoring_modifiers", {})
    player_key = str(player_id)

    if mod_type == "none":
        modifiers[player_key] = None
    else:
        modifiers[player_key] = mod_type

    await state.update_data(scoring_modifiers=modifiers)
    await _show_modifier_for_player(callback.message, state, player_id)
    await callback.answer()


@router.callback_query(GameForm.scoring_modifier, F.data.startswith("scoring:mod_done:"))
async def cb_scoring_mod_done(callback: CallbackQuery, state: FSMContext):
    logger.info("cb_scoring_mod_done called: %s", callback.data)
    data = await state.get_data()
    idx = data["scoring_idx"] + 1
    await state.update_data(scoring_idx=idx)
    await state.set_state(GameForm.scoring)

    cats = data["scoring_cats"]
    player_data = data["scoring_players"]
    await _show_scoring_for_player(callback.message, state, idx, cats, player_data)
    await callback.answer()


async def _finish_scoring(target: Message, state: FSMContext):
    data = await state.get_data()
    results = data["scoring_results"]
    modifiers = data.get("scoring_modifiers", {})
    round_num = data["scoring_round"]
    lot_id = data["scoring_lot_id"]
    host_id = data.get("scoring_host_id")
    modifier_multiplier = data.get("modifier_multiplier", 2)
    if not host_id:
        await target.answer("Ошибка: не удалось определить ведущего.")
        await state.clear()
        return

    async with async_session() as session:
        game = await get_active_game_for_host(session, host_id)
        if not game:
            await target.answer("Нет активной игры.")
            await state.clear()
            return

        game = await get_game_by_id(session, game.id)
        lot = await get_lot_by_id(session, lot_id, game.host_id)

        round_results = []
        for p in game.players:
            cat_results = results.get(str(p.id), {})
            mod_type = modifiers.get(str(p.id))
            rr = apply_round_result(
                p,
                lot,
                round_num,
                cat_results,
                modifier_type=mod_type,
                modifier_multiplier=modifier_multiplier,
            )
            session.add(rr)
            round_results.append(rr)

        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()

    summary = format_round_summary(round_num, lot, round_results)
    leaderboard = format_leaderboard(game.players)

    await target.answer(summary)
    await target.answer(leaderboard)

    is_last = game.current_round >= game.total_rounds
    from bot.keyboards.game import post_round_kb
    await target.answer(
        "Что дальше?" if not is_last else "Это был последний раунд.",
        reply_markup=post_round_kb(is_last),
    )


def format_leaderboard(players):
    from bot.services.scoring import format_leaderboard as _format_leaderboard
    return _format_leaderboard(players)
