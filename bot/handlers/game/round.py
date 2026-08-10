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
    swap_lot_kb,
    post_round_kb,
)
from bot.keyboards.common import main_menu_kb
from bot.services.games import get_active_game_for_host, get_game_by_id, format_players_list
from bot.services.lots import get_user_lots, get_lot_by_id, format_lot_for_host
from bot.services.scoring import active_categories
from bot.services.script import format_host_card, format_lot_cheatsheet, category_hint, modifiers_reference, sectors_reference
from bot.handlers.game._timer import cancel_timer, _run_timer, register_timer
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:start_game")
async def cb_start_game(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        if game.status != GameStatus.WAITING:
            await callback.answer("Игра уже началась или завершена", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        if not game.players:
            await callback.answer("Добавьте хотя бы одного игрока перед стартом", show_alert=True)
            return
        if not game.lot_ids:
            await callback.answer("Выберите лоты для раундов перед стартом", show_alert=True)
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

        if game.lot_ids and len(game.lot_ids) > 0:
            next_idx = game.current_lot_index + 1
            if next_idx >= len(game.lot_ids):
                await callback.answer("Все лоты из меню использованы", show_alert=True)
                return

            lot_id = game.lot_ids[next_idx]
            lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
            if not lot:
                game.current_lot_index = next_idx
                await session.commit()
                await callback.answer("Лот не найден, пробую следующий", show_alert=True)
                return await cb_start_round(callback, state)

            round_num = game.current_round + 1
            game.status = GameStatus.ROUND_ACTIVE
            game.current_lot_id = lot.id
            game.current_round = round_num
            game.current_lot_index = next_idx
            game.round_started_at = datetime.now(timezone.utc)
            await session.commit()
            game = await get_game_by_id(session, game.id)

            await _send_round_messages(callback, game, lot)
            await callback.answer(f"Раунд {round_num} — {lot.title}")
            return

        lots = await get_user_lots(session, callback.from_user.id)

    if not lots:
        await callback.answer("Сначала создайте хотя бы один лот", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите лот для раунда:",
        reply_markup=select_lot_kb(lots),
    )
    await callback.answer()


async def _send_round_messages(callback: CallbackQuery, game, lot):
    timer = game.timer_minutes or 5
    host_text = format_host_card(game.current_round, game.total_rounds, lot.title, timer, len(game.players), game.settings)
    cat_text = category_hint(lot)

    timer_msg = await callback.bot.send_message(
        callback.message.chat.id,
        f"⏱ <b>{timer}:00</b>",
    )

    await callback.message.edit_text(host_text, reply_markup=round_active_host_kb())
    await callback.message.answer(cat_text)
    await callback.message.answer(format_lot_cheatsheet(lot))

    if game.settings:
        if game.settings.modifiers_enabled:
            await callback.message.answer(modifiers_reference(game.settings))
        await callback.message.answer(sectors_reference(game.settings))

    task = asyncio.create_task(
        _run_timer(callback.bot, timer_msg.chat.id, timer_msg.message_id, game.id, timer * 60)
    )
    register_timer(game.id, task, timer_msg.chat.id, timer_msg.message_id)


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


@router.callback_query(F.data == "game:swap_lot")
async def cb_swap_lot(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.ROUND_ACTIVE:
            await callback.answer("Сейчас нельзя заменить лот", show_alert=True)
            return

        current_lot_id = game.current_lot_id

        if game.lot_ids:
            lot_ids = [lid for lid in game.lot_ids if lid != current_lot_id]
            lots = []
            for lid in lot_ids:
                lot = await get_lot_by_id(session, lid, callback.from_user.id)
                if lot:
                    lots.append(lot)
        else:
            user_lots = await get_user_lots(session, callback.from_user.id)
            lots = [l for l in user_lots if l.id != current_lot_id]

    if not lots:
        await callback.answer("Нет доступных лотов для замены", show_alert=True)
        return

    current_name = game.current_lot.title if game.current_lot else "?"
    await callback.message.edit_text(
        f"🔄 <b>Замена лота</b>\n\nТекущий: {current_name}\n\nВыберите новый лот:",
        reply_markup=swap_lot_kb(lots),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("game:swap_to:"))
async def cb_swap_to(callback: CallbackQuery, state: FSMContext):
    new_lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        new_lot = await get_lot_by_id(session, new_lot_id, callback.from_user.id)
        if not new_lot:
            await callback.answer("Лот не найден", show_alert=True)
            return

        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.ROUND_ACTIVE:
            await callback.answer("Сейчас нельзя заменить лот", show_alert=True)
            return

        cats = active_categories(new_lot)
        if not cats:
            await callback.answer("В этом лоте нет категорий для ставок", show_alert=True)
            return

        game.current_lot_id = new_lot.id
        game.round_started_at = datetime.now(timezone.utc)
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()
    await state.update_data(current_round_cats=active_categories(new_lot))

    cancel_timer(callback.bot, game.id)

    timer = game.timer_minutes or 5
    host_text = format_host_card(game.current_round, game.total_rounds, new_lot.title, timer, len(game.players), game.settings)

    timer_msg = await callback.bot.send_message(
        callback.message.chat.id,
        f"⏱ <b>{timer}:00</b>",
    )

    await callback.message.edit_text(host_text, reply_markup=round_active_host_kb())
    await callback.message.answer(f"🔄 Лот заменён на: <b>{new_lot.title}</b>")
    await callback.message.answer(category_hint(new_lot))
    await callback.message.answer(format_lot_cheatsheet(new_lot))

    task = asyncio.create_task(
        _run_timer(callback.bot, timer_msg.chat.id, timer_msg.message_id, game.id, timer * 60)
    )
    register_timer(game.id, task, timer_msg.chat.id, timer_msg.message_id)

    await callback.answer(f"Лот заменён — {new_lot.title}")


@router.callback_query(F.data == "game:swap_cancel")
async def cb_swap_cancel(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != GameStatus.ROUND_ACTIVE:
            await callback.message.edit_text("Раунд не активен.", reply_markup=main_menu_kb())
            await callback.answer()
            return
        game = await get_game_by_id(session, game.id)
        lot = game.current_lot

    timer = game.timer_minutes or 5
    host_text = format_host_card(game.current_round, game.total_rounds, lot.title if lot else "?", timer, len(game.players), game.settings)
    await callback.message.edit_text(host_text, reply_markup=round_active_host_kb())
    await callback.answer()


@router.callback_query(F.data == "game:add_round")
async def cb_add_round(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return

        game.total_rounds += 1
        await session.commit()

        if game.lot_ids:
            lot_ids = game.lot_ids.copy()
            used_ids = set(lot_ids)
            all_lots = await get_user_lots(session, callback.from_user.id)
            available = [l for l in all_lots if l.id not in used_ids]
            if not available:
                available = all_lots  # если все использованы, показать все
        else:
            available = await get_user_lots(session, callback.from_user.id)

    await state.set_state(GameForm.add_extra_round)
    await state.update_data(extra_round_game_id=game.id)

    await callback.message.edit_text(
        f"➕ <b>Добавить раунд {game.total_rounds}</b>\n\n"
        f"Выберите лот для нового раунда:",
        reply_markup=select_lot_kb(available),
    )
    await callback.answer()


@router.callback_query(GameForm.add_extra_round, F.data.startswith("game:select_lot:"))
async def cb_add_round_select_lot(callback: CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    game_id = data["extra_round_game_id"]

    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
        game = await get_game_by_id(session, game_id)
        if not game:
            await state.clear()
            await callback.message.edit_text("Игра не найдена.", reply_markup=main_menu_kb())
            await callback.answer()
            return

        if game.lot_ids is None:
            game.lot_ids = []
        game.lot_ids.append(lot.id)
        await session.commit()

    await state.clear()
    new_total = game.total_rounds
    lot_name = lot.title if lot else f"#{lot_id}"
    is_last = game.current_round >= new_total

    await callback.message.edit_text(
        f"✅ Добавлен раунд {new_total}: <b>{lot_name}</b>\n"
        f"Всего раундов: {new_total}\n\n"
        f"Текущий раунд: {game.current_round}/{new_total}",
        reply_markup=post_round_kb(is_last),
    )
    await callback.answer(f"Добавлен раунд {new_total}")


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
