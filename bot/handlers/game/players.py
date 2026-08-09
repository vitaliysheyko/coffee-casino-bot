import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import game_setup_kb, game_waiting_kb
from bot.models import GamePlayer
from bot.services.games import (
    get_active_game_for_host,
    get_game_by_id,
    format_players_list,
)
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "game:add_player")
async def cb_add_player(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameForm.add_player)
    await callback.message.edit_text(
        "Введите имя игрока (как его называть за столом):",
        reply_markup=None,
    )
    await callback.answer()


@router.message(GameForm.add_player)
async def process_add_player(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 64:
        await message.answer("Имя должно быть от 1 до 64 символов:")
        return

    async with async_session() as session:
        game = await get_active_game_for_host(session, message.from_user.id)
        if not game:
            await message.answer("Нет активной игры.")
            await state.clear()
            return

        player = GamePlayer(
            game_id=game.id,
            user_id=None,
            display_name=name,
            total_score=game.starting_chips,
        )
        session.add(player)
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()
    await message.answer(
        f"<b>{name}</b> добавлен за стол!\n\n"
        f"Игроков: {len(game.players)}\n"
        f"{format_players_list(game.players)}",
        reply_markup=game_setup_kb(),
    )


@router.callback_query(F.data == "game:remove_player")
async def cb_remove_player(callback: CallbackQuery):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game or not game.players:
            await callback.answer("Нет игроков", show_alert=True)
            return

        from bot.keyboards.game import remove_player_kb
        await callback.message.edit_text(
            "Кого убрать?",
            reply_markup=remove_player_kb(game.players),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("game:remove_player_id:"))
async def cb_remove_player_id(callback: CallbackQuery):
    player_id = int(callback.data.split(":")[3])
    async with async_session() as session:
        result = await session.execute(select(GamePlayer).where(GamePlayer.id == player_id))
        player = result.scalar_one_or_none()
        if player:
            await session.delete(player)
            await session.commit()
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game = await get_game_by_id(session, game.id)

    await callback.message.edit_text(
        f"Игрок удалён.\n\n"
        f"Игроков: {len(game.players)}\n"
        f"{format_players_list(game.players)}",
        reply_markup=game_waiting_kb(len(game.players) > 0),
    )
    await callback.answer()
