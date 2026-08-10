from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import (
    game_waiting_kb,
    round_active_host_kb,
    leaderboard_kb,
)
from bot.keyboards.common import main_menu_kb, confirm_kb
from bot.services.games import get_active_game_for_host, get_game_by_id, format_players_list, get_timer_minutes
from bot.services.lots import format_lot_for_host
from bot.services.scoring import build_leaderboard, format_leaderboard
from bot.services.script import format_host_card, format_lot_cheatsheet, category_hint, format_finish_summary
from bot.handlers.game._timer import cancel_timer

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:end_round_early")
async def cb_end_round_early(callback: CallbackQuery):
    await callback.message.edit_text(
        "Досрочно завершить раунд?",
        reply_markup=confirm_kb("game:reveal", "game:refresh", "Да", "Вернуться"),
    )
    await callback.answer()


@router.callback_query(F.data == "game:finish_game")
async def cb_finish_game(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return

        game = await get_game_by_id(session, game.id)
        board = build_leaderboard(game.players)
        winner_name = board[0]["name"] if board else "Никто"
        leaderboard_text = format_leaderboard(game.players)

        game.status = GameStatus.FINISHED
        game.finished_at = datetime.now(timezone.utc)
        await session.commit()

    cancel_timer(callback.bot, game.id)

    await callback.message.edit_text(
        format_finish_summary(leaderboard_text, winner_name),
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "game:cancel")
async def cb_game_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        "Отменить текущую игру? Все данные будут потеряны.",
        reply_markup=confirm_kb("game:cancel_confirm", "game:refresh", "Да, отменить", "Вернуться"),
    )
    await callback.answer()


@router.callback_query(F.data == "game:cancel_confirm")
async def cb_game_cancel_confirm(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game.status = GameStatus.FINISHED
            game.finished_at = datetime.now(timezone.utc)
            await session.commit()

    cancel_timer(callback.bot, game.id)

    await callback.message.edit_text("Игра отменена.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "game:leaderboard")
async def cb_leaderboard(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)

    leaderboard = format_leaderboard(game.players)
    await callback.message.edit_text(leaderboard, reply_markup=leaderboard_kb())
    await callback.answer()


@router.callback_query(F.data == "game:refresh")
async def cb_game_refresh(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.message.edit_text(
                "Активной игры нет.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()
            return
        game = await get_game_by_id(session, game.id)

    if game.status == GameStatus.WAITING:
        await callback.message.edit_text(
            format_players_list(game.players),
            reply_markup=game_waiting_kb(len(game.players) > 0),
        )
    elif game.status == GameStatus.ROUND_ACTIVE:
        lot = game.current_lot
        await callback.message.edit_text(
            format_host_card(
                game.current_round,
                game.total_rounds,
                lot.title if lot else "?",
                get_timer_minutes(game),
                len(game.players),
            ),
            reply_markup=round_active_host_kb(),
        )
        if lot:
            await callback.message.answer(category_hint(lot))
            await callback.message.answer(format_lot_cheatsheet(lot))
    elif game.status == GameStatus.REVEAL:
        lot = game.current_lot
        is_last = game.current_round >= game.total_rounds
        await callback.message.edit_text(
            f"🔍 <b>Ревел — Раунд {game.current_round}</b>\n\n"
            f"{format_lot_for_host(lot) if lot else 'Лот не найден'}",
            reply_markup=reveal_kb(is_last),
        )
    elif game.status == GameStatus.FINISHED:
        leaderboard = format_leaderboard(game.players)
        board = build_leaderboard(game.players)
        winner = board[0]["name"] if board else "Никто"
        await callback.message.edit_text(
            format_finish_summary(leaderboard, winner),
            reply_markup=main_menu_kb(),
        )
    else:
        await callback.message.edit_text(
            f"Статус игры: {game.status}",
            reply_markup=main_menu_kb(),
        )
    await callback.answer()


def reveal_kb(is_last: bool):
    from bot.keyboards.game import reveal_kb as _reveal_kb
    return _reveal_kb(is_last)
