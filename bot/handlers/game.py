from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.database import async_session
from bot.keyboards.game import (
    game_waiting_kb,
    select_lot_kb,
    empty_fields_warning_kb,
    round_active_host_kb,
    reveal_host_kb,
    player_bet_kb,
    cancel_timer_kb,
)
from bot.keyboards.common import main_menu_kb, confirm_kb
from bot.models import Game, GamePlayer
from bot.services.games import (
    create_game,
    get_active_game_for_host,
    get_game_by_id,
    get_or_create_user,
    format_players_list,
)
from bot.services.lots import (
    get_user_lots,
    get_lot_by_id,
    get_empty_game_fields,
    format_lot_for_host,
    format_lot_for_players,
)
import logging

from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


def _host_waiting_text(game) -> str:
    players_count = len(game.players)
    text = (
        f"Игра <b>{game.code}</b>\n\n"
        f"Игроков: {players_count}\n"
        f"{format_players_list(game)}\n\n"
    )
    if players_count < 4:
        text += f"Нужно ещё минимум {4 - players_count} игрока(ов) для старта."
    else:
        text += "Можно начинать раунд!"
    return text


@router.callback_query(F.data == "game:create")
async def cb_game_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        existing = await get_active_game_for_host(session, user.id)
        if existing:
            existing = await get_game_by_id(session, existing.id)
            await callback.message.edit_text(
                f"У вас уже есть активная игра: <b>{existing.code}</b>\n\n"
                f"{_host_waiting_text(existing)}",
                reply_markup=game_waiting_kb(len(existing.players) >= 4),
            )
            await callback.answer()
            return

        game = await create_game(session, user.id)

    link = f"https://t.me/coffee_casino_bot?start={game.code}"
    text = (
        f"Игра создана!\n\n"
        f"Код для игроков: <b>{game.code}</b>\n"
        f"Ссылка: {link}\n\n"
        f"Игроков: 0\n\n"
        f"Ожидаем участников...\n(минимум 4 игрока)"
    )
    await callback.message.edit_text(text, reply_markup=game_waiting_kb(False))
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

    if game.status == "waiting":
        text = _host_waiting_text(game)
        await callback.message.edit_text(
            text, reply_markup=game_waiting_kb(len(game.players) >= 4)
        )
    elif game.status == "round_active":
        await _show_round_active(callback, game)
    elif game.status == "reveal":
        await _show_reveal(callback, game)
    else:
        await callback.message.edit_text("Игра завершена.", reply_markup=main_menu_kb())

    await callback.answer()


@router.callback_query(F.data == "game:cancel")
async def cb_game_cancel(callback: CallbackQuery):
    await callback.message.edit_text(
        "Отменить текущую игру?",
        reply_markup=confirm_kb(
            "game:cancel_confirm", "game:refresh", "Да, отменить игру", "Вернуться"
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "game:cancel_confirm")
async def cb_game_cancel_confirm(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game.status = "finished"
            await session.commit()
            game = await get_game_by_id(session, game.id)

            for p in game.players:
                try:
                    await callback.bot.send_message(
                        p.user_id, "Ведущий отменил игру."
                    )
                except Exception:
                    logger.warning("Failed to send cancel notification to player %s", p.user_id, exc_info=True)

    await callback.message.edit_text("Игра отменена.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "game:start_round")
async def cb_start_round(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status not in ("waiting", "reveal"):
            await callback.answer("Сейчас нельзя начать раунд", show_alert=True)
            return

        game = await get_game_by_id(session, game.id)
        if len(game.players) < 4 and game.status == "waiting":
            await callback.answer("Нужно минимум 4 игрока", show_alert=True)
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


@router.callback_query(F.data.startswith("game:select_lot:"))
async def cb_select_lot(callback: CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
        if not lot:
            await callback.answer("Лот не найден", show_alert=True)
            return

    await state.update_data(selected_lot_id=lot_id)
    await state.set_state(GameForm.waiting_timer)
    await callback.message.edit_text(
        f"Лот: <b>{lot.title}</b>\n\n"
        f"Укажите длительность раунда в минутах (целое число от 1 до 30):",
        reply_markup=cancel_timer_kb(),
    )
    await callback.answer()


@router.message(GameForm.waiting_timer)
async def process_timer(message: Message, state: FSMContext):
    try:
        minutes = int(message.text.strip())
        if not 1 <= minutes <= 30:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от 1 до 30:")
        return

    data = await state.get_data()
    lot_id = data.get("selected_lot_id")
    await state.update_data(timer_minutes=minutes)

    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, message.from_user.id)
        empty = get_empty_game_fields(lot)

    if empty:
        text = (
            f"Внимание!\n\n"
            f"В этом лоте нет данных по полям:\n"
            f"\u2022 " + "\n\u2022 ".join(empty) + "\n\n"
            f"Сообщите игрокам, что на эти категории в данном раунде ставки не принимаются."
        )
        await message.answer(text, reply_markup=empty_fields_warning_kb())
    else:
        await _launch_round(message, state, message.from_user.id, lot_id, minutes)


@router.callback_query(F.data == "game:confirm_start")
async def cb_confirm_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lot_id = data.get("selected_lot_id")
    minutes = data.get("timer_minutes")
    await _launch_round(
        callback.message, state, callback.from_user.id, lot_id, minutes, edit=True
    )
    await callback.answer()


async def _launch_round(
    message_or_msg, state: FSMContext, user_id: int, lot_id: int, minutes: int, edit: bool = False
):
    bot = message_or_msg.bot

    async with async_session() as session:
        game = await get_active_game_for_host(session, user_id)
        if not game:
            logger.error("No active game for host %s at round launch", user_id)
            await message_or_msg.answer("Не удалось найти активную игру.")
            return

        lot = await get_lot_by_id(session, lot_id, user_id)
        if not lot:
            logger.error("Lot %s not found for user %s at round launch", lot_id, user_id)
            await message_or_msg.answer("Лот не найден.")
            return

        lot_number = (game.current_lot_number or 0) + 1

        game.status = "round_active"
        game.current_lot_id = lot.id
        game.current_lot_number = lot_number
        game.timer_minutes = minutes
        game.round_started_at = datetime.now(timezone.utc)

        game = await get_game_by_id(session, game.id)
        for p in game.players:
            p.has_bet = False

        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()

    host_text = (
        f"Раунд идёт\n\n"
        f"<b>Лот {lot_number} — {lot.title}</b>\n"
        f"Таймер: {minutes}:00\n\n"
        f"Уже поставили: 0 из {len(game.players)}\n"
        f"{format_players_list(game)}"
    )

    if edit:
        await message_or_msg.edit_text(host_text, reply_markup=round_active_host_kb())
    else:
        await message_or_msg.answer(host_text, reply_markup=round_active_host_kb())

    player_text = (
        f"Раунд начался!\n\n"
        f"<b>Лот {lot_number}</b>\n"
        f"Таймер: {minutes}:00\n\n"
        f"Сделайте ставки на физическом поле."
    )
    for p in game.players:
        try:
            await bot.send_message(p.user_id, player_text, reply_markup=player_bet_kb())
        except Exception:
            logger.warning("Failed to send round start to player %s", p.user_id, exc_info=True)


async def _show_round_active(callback: CallbackQuery, game):
    lot = game.current_lot
    bet_count = sum(1 for p in game.players if p.has_bet)
    title = lot.title if lot else "?"
    text = (
        f"Раунд идёт\n\n"
        f"<b>Лот {game.current_lot_number} — {title}</b>\n"
        f"Таймер: {game.timer_minutes} мин\n\n"
        f"Уже поставили: {bet_count} из {len(game.players)}\n"
        f"{format_players_list(game)}"
    )
    await callback.message.edit_text(text, reply_markup=round_active_host_kb())


@router.callback_query(F.data == "game:place_bet")
async def cb_place_bet(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(GamePlayer)
            .join(Game)
            .where(
                GamePlayer.user_id == callback.from_user.id,
                Game.status == "round_active",
            )
        )
        player = result.scalar_one_or_none()
        if not player:
            await callback.answer("Сейчас нет активного раунда", show_alert=True)
            return

        if player.has_bet:
            await callback.answer("Вы уже сделали ставки", show_alert=True)
            return

        player.has_bet = True
        await session.commit()
        game = await get_game_by_id(session, player.game_id)

        await callback.message.edit_text(
            f"Раунд идёт\n\n"
            f"<b>Лот {game.current_lot_number}</b>\n\n"
            f"Вы сделали ставки ✓\n"
            f"Ожидаем остальных и ревейл от ведущего."
    )
    await callback.answer("Ставки приняты!")

    bet_count = sum(1 for p in game.players if p.has_bet)
    total = len(game.players)
    try:
        host_text = (
            f"Раунд идёт\n\n"
            f"<b>Лот {game.current_lot_number} — {game.current_lot.title if game.current_lot else '?'}</b>\n"
            f"Таймер: {game.timer_minutes} мин\n\n"
            f"Уже поставили: {bet_count} из {total}\n"
            f"{format_players_list(game)}"
        )
        if bet_count == total and total > 0:
            host_text += "\n\n✅ Все игроки сделали ставки!"
        await callback.bot.send_message(
            game.host_id,
            host_text,
            reply_markup=round_active_host_kb(),
        )
    except Exception:
        logger.warning("Failed to update host message", exc_info=True)


@router.callback_query(F.data == "game:show_fact")
async def cb_show_fact(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return

        game = await get_game_by_id(session, game.id)
        if not game.current_lot or not game.current_lot.fact:
            await callback.answer("У этого лота нет факта", show_alert=True)
            return

        fact = game.current_lot.fact

    for p in game.players:
        try:
            await callback.bot.send_message(
                p.user_id, f"📌 Интересный факт:\n\n{fact}"
            )
        except Exception:
            logger.warning("Failed to send fact to player %s", p.user_id, exc_info=True)

    await callback.answer("Факт отправлен игрокам!")


@router.callback_query(F.data == "game:reveal")
async def cb_reveal(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or game.status != "round_active":
            await callback.answer("Сейчас нельзя сделать ревейл", show_alert=True)
            return

        game = await get_game_by_id(session, game.id)
        lot = game.current_lot
        game.status = "reveal"
        await session.commit()
        game = await get_game_by_id(session, game.id)

    host_text = (
        f"Ревейл — Лот {game.current_lot_number}\n\n"
        f"{format_lot_for_host(lot) if lot else 'Лот не найден'}"
    )
    await callback.message.edit_text(host_text, reply_markup=reveal_host_kb())

    player_text = (
        f"Ревейл — Лот {game.current_lot_number}\n\n"
        f"{format_lot_for_players(lot) if lot else 'Лот не найден'}"
    )
    for p in game.players:
        try:
            await callback.bot.send_message(p.user_id, player_text)
        except Exception:
            logger.warning("Failed to send reveal to player %s", p.user_id, exc_info=True)

    await callback.answer()


async def _show_reveal(callback: CallbackQuery, game):
    lot = game.current_lot
    text = (
        f"Ревейл — Лот {game.current_lot_number}\n\n"
        f"{format_lot_for_host(lot) if lot else 'Лот не найден'}"
    )
    await callback.message.edit_text(text, reply_markup=reveal_host_kb())


@router.callback_query(F.data == "game:end_round_early")
async def cb_end_round_early(callback: CallbackQuery):
    await callback.message.edit_text(
        "Досрочно завершить раунд и сделать ревейл?",
        reply_markup=confirm_kb(
            "game:reveal", "game:refresh", "Да, завершить раунд", "Вернуться"
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "game:finish")
async def cb_finish_game(callback: CallbackQuery):
    await callback.message.edit_text(
        "Завершить игру полностью?",
        reply_markup=confirm_kb(
            "game:finish_confirm", "game:refresh", "Да, завершить игру", "Вернуться"
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "game:finish_confirm")
async def cb_finish_confirm(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game.status = "finished"
            await session.commit()
            game = await get_game_by_id(session, game.id)

            for p in game.players:
                try:
                    await callback.bot.send_message(
                        p.user_id, "Игра завершена.\n\nСпасибо за участие!"
                    )
                except Exception:
                    logger.warning("Failed to send finish to player %s", p.user_id, exc_info=True)

    await callback.message.edit_text(
        "Игра завершена.\n\nСпасибо за игру!",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
