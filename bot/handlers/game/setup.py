import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import game_setup_kb
from bot.keyboards.common import main_menu_kb, cancel_fsm_kb
from bot.services.games import (
    create_game,
    get_active_game_for_host,
    get_game_by_id,
    get_or_create_user,
)
from bot.services.lots import create_preset_lots, get_user_lots
from bot.services.script import format_game_setup_prompt
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "fsm:cancel")
async def cb_fsm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "game:add_presets")
async def cb_add_presets(callback: CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        existing = await get_user_lots(session, user.id)
        if len(existing) >= 4:
            await callback.answer("У вас уже есть лоты", show_alert=True)
            return
        
        lots = await create_preset_lots(session, user.id)
        await callback.answer(f"Добавлено {len(lots)} пресетных лотов", show_alert=True)
        
        game = await get_active_game_for_host(session, user.id)
        if game:
            await callback.message.edit_text(
                f"✅ Добавлено {len(lots)} лотов!\n\n"
                f"Игроков: {len(game.players)}\n"
                f"Лотов: {len(existing) + len(lots)}",
                reply_markup=game_setup_kb(),
            )


@router.callback_query(F.data == "game:create")
async def cb_game_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        existing = await get_active_game_for_host(session, callback.from_user.id)
        if existing:
            await callback.message.edit_text(
                f"У вас уже есть игра <b>{existing.code}</b>. Завершите её.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()
            return
        
        lots = await get_user_lots(session, callback.from_user.id)
        if not lots:
            await callback.message.edit_text(
                "⚠️ <b>У вас нет лотов!</b>\n\n"
                "Для игры нужны лоты с кофе.\n\n"
                "Создайте лоты через «Мои лоты» или используйте «Быстрая игра» с пресетными лотами.",
                reply_markup=main_menu_kb(),
            )
            await callback.answer()
            return

    await state.set_state(GameForm.setup_rounds)
    await state.update_data(game_config={})
    await callback.message.edit_text(
        "🎲 <b>Новая игра</b>\n\nСколько раундов? (введите число от 1 до 12)",
        reply_markup=cancel_fsm_kb(),
    )
    await callback.answer()


@router.message(GameForm.setup_rounds)
async def process_rounds(message: Message, state: FSMContext):
    try:
        rounds = int(message.text.strip())
        if not 1 <= rounds <= 12:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 12:")
        return

    await state.update_data(game_config={"total_rounds": rounds})
    await state.set_state(GameForm.setup_timer)
    await message.answer(
        f"Раундов: {rounds}\n\nДлительность одного раунда в минутах? (1–30)",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(GameForm.setup_timer)
async def process_timer_setup(message: Message, state: FSMContext):
    try:
        minutes = int(message.text.strip())
        if not 1 <= minutes <= 30:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 30:")
        return

    data = await state.get_data()
    config = data["game_config"]
    config["timer_minutes"] = minutes
    await state.update_data(game_config=config)
    await state.set_state(GameForm.setup_chips)
    await message.answer(
        f"Таймер: {minutes} мин\n\nСколько стартовых фишек у каждого игрока? (1–50)",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(GameForm.setup_chips)
async def process_chips_setup(message: Message, state: FSMContext):
    try:
        chips = int(message.text.strip())
        if not 1 <= chips <= 50:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 50:")
        return

    data = await state.get_data()
    config = data["game_config"]

    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)
        game = await create_game(
            session,
            user.id,
            total_rounds=config["total_rounds"],
            starting_chips=chips,
        )
        game.timer_minutes = config["timer_minutes"]
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()
    code = game.code
    await message.answer(
        format_game_setup_prompt(code, config["timer_minutes"], config["total_rounds"], 0, settings.web_url),
        reply_markup=game_setup_kb(),
    )
