from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.common import main_menu_kb, back_to_main_kb
from bot.keyboards.game import game_waiting_kb, cancel_timer_kb
from bot.services.games import get_game_by_code, add_player_to_game, get_or_create_user, create_game, get_active_game_for_host
from bot.services.lots import create_preset_lots, get_user_lots
from bot.states.game import GameForm

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
        "3. Когда собралось ≥ 2 человека — запускает раунд\n"
        "4. Игроки делают ставки на физическом поле\n"
        "5. Ведущий делает ревейл — все видят правильные ответы\n\n"
        "Бот не считает фишки и не заменяет живую игру."
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data == "quick_game")
async def cb_quick_game(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)

        existing = await get_active_game_for_host(session, user.id)
        if existing:
            game = await get_game_by_code(session, existing.code)
            await callback.message.edit_text(
                f"У вас уже есть активная игра: <b>{existing.code}</b>\n\n"
                f"Завершите её перед созданием новой.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()
            return

        lots = await get_user_lots(session, user.id)
        if len(lots) < 4:
            await callback.message.edit_text(
                "🎲 Создаю 6 готовых лотов для быстрой игры...",
                reply_markup=None,
            )
            await create_preset_lots(session, user.id)
        else:
            await callback.message.edit_text(
                "🎲 Создаю новую игру...",
                reply_markup=None,
            )

        game = await create_game(session, user.id)

    await state.update_data(new_game_id=game.id)
    await state.set_state(GameForm.waiting_timer)
    await callback.message.edit_text(
        f"🎲 Быстрая игра <b>{game.code}</b>\n"
        f"6 лотов готовы!\n\n"
        f"Укажите длительность раунда в минутах (целое число от 1 до 30):",
        reply_markup=cancel_timer_kb(),
    )
    await callback.answer()
