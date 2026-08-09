import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.keyboards.game import game_setup_kb
from bot.services.games import get_active_game_for_host, get_game_by_id, format_players_list

router = Router()
logger = logging.getLogger(__name__)

CHIP_DELTAS = [(-5, "−5"), (-3, "−3"), (-1, "−1"), (1, "+1"), (3, "+3"), (5, "+5")]


def calc_kb(player_id: int, player_name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = []
    for delta, label in CHIP_DELTAS:
        buttons.append(InlineKeyboardButton(
            text=label,
            callback_data=f"calc:{player_id}:{delta}",
        ))
    builder.row(*buttons[:3])
    builder.row(*buttons[3:])
    builder.row(InlineKeyboardButton(text="« Назад к игре", callback_data="game:refresh"))
    return builder.as_markup()


@router.callback_query(F.data == "game:calculator")
async def cb_calculator(callback: CallbackQuery):
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

    lines = ["🧮 <b>Калькулятор фишек</b>\n", format_players_list(players), "", "Выберите игрока:"]
    await callback.message.edit_text("\n".join(lines), reply_markup=_players_kb(players))
    await callback.answer()


def _players_kb(players):
    builder = InlineKeyboardBuilder()
    for p in players:
        builder.row(InlineKeyboardButton(
            text=f"{p.display_name} ({p.total_score})",
            callback_data=f"calc:select:{p.id}",
        ))
    builder.row(InlineKeyboardButton(text="« Назад к игре", callback_data="game:refresh"))
    return builder.as_markup()


@router.callback_query(F.data.startswith("calc:select:"))
async def cb_calc_select(callback: CallbackQuery):
    player_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)

    if not player:
        await callback.answer("Игрок не найден", show_alert=True)
        return

    await callback.message.edit_text(
        f"🧮 <b>{player.display_name}</b>\nФишек: {player.total_score}\n\nВыберите действие:",
        reply_markup=calc_kb(player.id, player.display_name),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("calc:"))
async def cb_calc_action(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        return

    player_id = int(parts[1])
    delta = int(parts[2])

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)
        if not player:
            await callback.answer("Игрок не найден", show_alert=True)
            return

        player.total_score += delta
        await session.commit()
        new_score = player.total_score

    sign = "+" if delta > 0 else ""
    await callback.message.edit_text(
        f"🧮 <b>{player.display_name}</b>\n"
        f"Действие: {sign}{delta}\n"
        f"Фишек: <b>{new_score}</b>\n\nВыберите действие:",
        reply_markup=calc_kb(player.id, player.display_name),
    )
    await callback.answer(f"{sign}{delta} → {new_score}")
