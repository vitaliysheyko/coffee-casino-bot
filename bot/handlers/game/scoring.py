import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import (
    build_round_result_kb,
    reveal_kb,
)
from bot.keyboards.common import main_menu_kb
from bot.services.games import get_active_game_for_host, get_game_by_id
from bot.services.lots import get_lot_by_id, format_lot_for_host
from bot.services.scoring import (
    active_categories,
    apply_round_result,
    format_round_summary,
)
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:score_round")
async def cb_score_round(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.REVEAL:
            await callback.answer("Нет раунда для подсчёта", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        players = list(game.players)
        lot = game.current_lot

    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return

    cats = active_categories(lot)
    if not cats:
        await callback.answer("Нет категорий для ставок", show_alert=True)
        return

    player_data = {p.id: p.display_name for p in players}
    await state.update_data(
        scoring_round=game.current_round,
        scoring_lot_id=lot.id,
        scoring_players=player_data,
        scoring_cats=cats,
        scoring_idx=0,
        scoring_results={},
        scoring_host_id=callback.from_user.id,
    )
    await state.set_state(GameForm.scoring)
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
    _, _, player_id_str = callback.data.split(":")
    player_id = int(player_id_str)

    data = await state.get_data()
    idx = data["scoring_idx"] + 1
    await state.update_data(scoring_idx=idx)

    cats = data["scoring_cats"]
    player_data = data["scoring_players"]
    await _show_scoring_for_player(callback.message, state, idx, cats, player_data)
    await callback.answer()


async def _finish_scoring(target: Message, state: FSMContext):
    data = await state.get_data()
    results = data["scoring_results"]
    round_num = data["scoring_round"]
    lot_id = data["scoring_lot_id"]
    host_id = data.get("scoring_host_id")
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
            rr = apply_round_result(p, lot, round_num, cat_results)
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
