from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.common import main_menu_kb
from bot.keyboards.history import history_list_kb
from bot.services.games import get_finished_games_for_host, get_or_create_user
from bot.services.history import format_game_details, format_game_history_list

router = Router()


@router.message(Command("history"))
async def cmd_history(message: Message):
    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)
        games = await get_finished_games_for_host(session, user.id)

    await message.answer(
        format_game_history_list(games),
        reply_markup=history_list_kb(games),
    )


@router.callback_query(F.data == "history:list")
async def cb_history_list(callback: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        games = await get_finished_games_for_host(session, user.id)

    await callback.message.edit_text(
        format_game_history_list(games),
        reply_markup=history_list_kb(games),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:view:"))
async def cb_history_view(callback: CallbackQuery):
    game_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        from bot.services.games import get_game_by_id
        game = await get_game_by_id(session, game_id)
        if not game or game.host_id != callback.from_user.id:
            await callback.answer("Игра не найдена", show_alert=True)
            return

    await callback.message.edit_text(
        format_game_details(game),
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
