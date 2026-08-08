from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.common import main_menu_kb, back_to_main_kb
from bot.services.games import get_game_by_code, add_player_to_game, get_or_create_user

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split(maxsplit=1)
    deep_link = args[1] if len(args) > 1 else None

    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)

        if deep_link:
            game = await get_game_by_code(session, deep_link)
            if not game:
                await message.answer(
                    "Игра с таким кодом не найдена или уже завершена.",
                    reply_markup=main_menu_kb(),
                )
                return

            if game.host_id == user.id:
                await message.answer(
                    f"Вы ведущий этой игры.\nКод: <b>{game.code}</b>",
                    reply_markup=main_menu_kb(),
                )
                return

            await add_player_to_game(session, game, user)
            await message.answer(
                f"Вы присоединились к игре!\n\n"
                f"Код игры: <b>{game.code}</b>\n"
                f"Игроков сейчас: {len(game.players) + 1}\n\n"
                f"Ожидаем начала раунда...",
            )
            return

    await message.answer(
        "Добро пожаловать в <b>Кофейное казино</b>!\n\n"
        "Бот-помощник для проведения дегустационной игры.\n"
        "Физическое поле и фишки остаются главными — бот только помогает.",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Кофейное казино\n\nВыберите действие:",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    text = (
        "<b>Как играть</b>\n\n"
        "1. Ведущий создаёт лоты заранее\n"
        "2. Создаёт игру и скидывает код/ссылку игрокам\n"
        "3. Когда собралось ≥ 4 человека — запускает раунд\n"
        "4. Игроки делают ставки на физическом поле\n"
        "5. Ведущий делает ревейл — все видят правильные ответы\n\n"
        "Бот не считает фишки и не заменяет живую игру."
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()
