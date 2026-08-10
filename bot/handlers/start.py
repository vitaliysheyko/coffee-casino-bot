from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database import async_session
from bot.keyboards.common import main_menu_kb, back_to_main_kb
from bot.keyboards.game import game_setup_kb
from bot.services.games import (
    get_game_by_id,
    get_or_create_user,
    create_game,
    get_active_game_for_host,
)
from bot.services.lots import create_preset_lots, get_user_lots
from bot.services.script import format_game_setup_prompt
from bot.states.game import GameForm
from sqlalchemy import select
from bot.models import User

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await get_or_create_user(session, message.from_user)

    await message.answer(
        "<b>Кофейное казино</b> — помощник ведущего\n\n"
        "Бот помогает проводить дегустационную игру:\n"
        "• Сценарий каждого раунда\n"
        "• Таймер на проектор\n"
        "• Подсчёт фишек\n"
        "• Турнирная таблица\n"
        "• PDF игрового поля\n\n"
        "Игроки не трогают телефоны — только ведущий управляет ботом.",
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
        "<b>📖 Правила Кофейного казино</b>\n\n"
        "<b>Игровое поле</b>\n"
        "Каждый игрок получает лист с категориями:\n"
        "• 🌍 Континент — ×2\n"
        "• 🏳 Страна — ×3\n"
        "• ⚙️ Обработка — ×2\n"
        "• 🌱 Разновидность — ×3\n"
        "• 🔥 Обжарка — ×2\n"
        "• ⛰ Высота — ×3\n"
        "• ⭐ Оценка Q — ×3\n\n"
        "<b>Модификаторы (×2 к угаданному)</b>\n"
        "• 🥄 Ложка — дегустация вслепую с перемешиванием\n"
        "• 🦌 Дичь — нестандартный метод заваривания\n"
        "• 👃 Нюхлер — определение только по аромату\n"
        "Лимит: 2 использования каждого за игру\n\n"
        "<b>Ставки</b>\n"
        "Фишки: 5 / 10 / 25 / 50 / 100\n"
        "Ставка на категорию × множитель сектора = выигрыш\n"
        "Ошибка — ставка теряется\n\n"
        "<b>Ход игры</b>\n"
        "1. Раунд: ведущий заваривает лот, запускает таймер\n"
        "2. Игроки пробуют, делают ставки на поле\n"
        "3. Ревел: ведущий объявляет правильные ответы\n"
        "4. Подсчёт: ведущий вносит ставки в калькулятор\n"
        "5. Турнирная таблица обновляется\n\n"
        "<b>Множители можно менять</b> в ⚙️ Настройки"
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(F.data == "quick_game")
async def cb_quick_game(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        existing = await get_active_game_for_host(session, user.id)
        if existing:
            await callback.message.edit_text(
                f"У вас уже есть игра: <b>{existing.code}</b>\nЗавершите её.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()
            return

        lots = await get_user_lots(session, user.id)
        if len(lots) < 4:
            lots = await create_preset_lots(session, user.id)

        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one_or_none()
        qcfg = db_user.quick_config if db_user and db_user.quick_config else {"rounds": 6, "timer": 3, "chips": 10}
        
        lot_ids = [l.id for l in lots]
        game = await create_game(session, user.id, total_rounds=qcfg["rounds"], starting_chips=qcfg["chips"], lot_ids=lot_ids)
        game.timer_minutes = qcfg["timer"]
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()

    lot_titles = [l.title for l in lots]
    await callback.message.edit_text(
        format_game_setup_prompt(game.code, qcfg["timer"], qcfg["rounds"], 0, settings.web_url, lot_titles),
        reply_markup=game_setup_kb(),
    )
    await callback.answer()


@router.message(Command("timer"))
async def cmd_timer(message: Message):
    args = message.text.split(maxsplit=1)
    code = args[1].strip() if len(args) > 1 else None

    if not code:
        await message.answer("Укажите код игры: /timer X7K2")
        return

    web_url = settings.web_url
    if not web_url:
        web_port = settings.web_port
        await message.answer(
            f"<b>Таймер для проектора</b>\n\n"
            f"Веб-сервер запущен на порту {web_port}.\n"
            f"Откройте в браузере:\n"
            f"<code>http://ВАШ_IP:{web_port}/timer/{code.upper()}</code>\n\n"
            f"Добавьте WEB_URL в .env для автоматической ссылки.",
        )
        return

    url = f"{web_url.rstrip('/')}/timer/{code.upper()}"
    await message.answer(
        f"<b>Таймер для проектора</b>\n\n"
        f"Откройте на проекторе/телевизоре:\n"
        f"<a href=\"{url}\">{url}</a>",
        disable_web_page_preview=False,
    )
