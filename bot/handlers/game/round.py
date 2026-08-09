import asyncio
import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import (
    game_waiting_kb,
    select_lot_kb,
    round_active_host_kb,
    reveal_kb,
)
from bot.services.games import get_active_game_for_host, get_game_by_id, format_players_list
from bot.services.lots import get_user_lots, get_lot_by_id, format_lot_for_host
from bot.services.scoring import active_categories
from bot.services.script import format_host_card, format_lot_cheatsheet, category_hint
from bot.handlers.game._timer import cancel_timer, _run_timer, register_timer

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:start_game")
async def cb_start_game(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.WAITING:
            await callback.answer("Сейчас нельзя начать игру", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        if not game.players:
            await callback.answer("Добавьте хотя бы одного игрока", show_alert=True)
            return

    await state.clear()
    await callback.message.edit_text(
        format_players_list(game.players),
        reply_markup=game_waiting_kb(len(game.players) > 0),
    )
    await callback.answer()


@router.callback_query(F.data == "game:start_round")
async def cb_start_round(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status not in (GameStatus.WAITING, GameStatus.REVEAL):
            await callback.answer("Сейчас нельзя начать раунд", show_alert=True)
            return

        cancel_timer(callback.bot, game.id)
        lots = await get_user_lots(session, callback.from_user.id)

    if not lots:
        await callback.answer("Сначала создайте хотя бы один лот", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите лот для раунда:",
        reply_markup=select_lot_kb(lots),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("game:select_lot:"))
async def cb_select_lot(callback: CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
        if not lot:
            await callback.answer("Лот не найден", show_alert=True)
            return

        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return

        cats = active_categories(lot)
        if not cats:
            await callback.answer(
                "В этом лоте нет заполненных категорий (страна, регион, обработка, разновидность, обжарка). "
                "Заполните хотя бы одну.",
                show_alert=True,
            )
            return

        round_num = game.current_round + 1
        game.status = GameStatus.ROUND_ACTIVE
        game.current_lot_id = lot.id
        game.current_round = round_num
        game.round_started_at = datetime.now(timezone.utc)
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()
    await state.update_data(current_round_cats=active_categories(lot))

    timer = game.timer_minutes or 5
    host_text = format_host_card(round_num, game.total_rounds, lot.title, timer, len(game.players))
    cat_text = category_hint(lot)

    timer_msg = await callback.bot.send_message(
        callback.message.chat.id,
        f"⏱ <b>{timer}:00</b>",
    )

    await callback.message.edit_text(host_text, reply_markup=round_active_host_kb())
    await callback.message.answer(cat_text)
    await callback.message.answer(format_lot_cheatsheet(lot))

    task = asyncio.create_task(
        _run_timer(callback.bot, timer_msg.chat.id, timer_msg.message_id, game.id, timer * 60)
    )
    register_timer(game.id, task, timer_msg.chat.id, timer_msg.message_id)

    await callback.answer(f"Раунд {round_num} запущен!")


@router.callback_query(F.data == "game:reveal")
async def cb_reveal(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.ROUND_ACTIVE:
            await callback.answer("Сейчас нельзя сделать ревел", show_alert=True)
            return

        game = await get_game_by_id(session, game.id)
        lot = game.current_lot
        game.status = GameStatus.REVEAL
        await session.commit()
        game = await get_game_by_id(session, game.id)

    cancel_timer(callback.bot, game.id)
    is_last = game.current_round >= game.total_rounds

    if lot:
        await callback.message.edit_text(
            f"🔍 <b>Ревел — Раунд {game.current_round}</b>\n\n"
            f"{format_lot_for_host(lot)}",
            reply_markup=reveal_kb(is_last),
        )
    else:
        await callback.message.edit_text(
            f"🔍 <b>Ревел — Раунд {game.current_round}</b>\n\nЛот не найден.",
            reply_markup=reveal_kb(is_last),
        )
    await callback.answer()
