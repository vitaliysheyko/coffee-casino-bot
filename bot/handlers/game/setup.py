import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.constants import GameStatus
from bot.database import async_session
from bot.keyboards.game import game_setup_kb, select_game_lots_kb
from bot.keyboards.common import main_menu_kb, cancel_fsm_kb
from bot.services.games import (
    create_game,
    get_active_game_for_host,
    get_game_by_id,
    get_or_create_user,
)
from bot.services.lots import get_lot_by_id, get_user_lots
from bot.services.script import format_game_setup_prompt
from bot.states.game import GameForm

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "fsm:cancel")
async def cb_fsm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=main_menu_kb())
    await callback.answer()


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
        f"Таймер: {minutes} мин\n\nСколько стартовых фишек у каждого игрока? (1–1000)",
        reply_markup=cancel_fsm_kb(),
    )


@router.message(GameForm.setup_chips)
async def process_chips_setup(message: Message, state: FSMContext):
    try:
        chips = int(message.text.strip())
        if not 1 <= chips <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 1000:")
        return

    data = await state.get_data()
    config = data["game_config"]
    config["starting_chips"] = chips

    async with async_session() as session:
        user = await get_or_create_user(session, message.from_user)
        lots = await get_user_lots(session, user.id)

    if not lots:
        await message.answer(
            "У вас нет лотов. Создайте лоты через «Мои лоты» или быструю игру.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    await state.update_data(game_config=config, sel_lots=[], all_lot_ids=[l.id for l in lots])
    await state.set_state(GameForm.setup_lots)
    total = config['total_rounds']
    await message.answer(
        f"☕ <b>Выберите лоты для игры</b>\n"
        f"Раундов: {total} | Фишек: {chips}\n\n"
        f"Выберите <b>ровно {total} лотов</b> — по одному на раунд.\n"
        f"Порядок выбора = порядок раундов.",
        reply_markup=select_game_lots_kb(lots),
    )


@router.callback_query(GameForm.setup_lots, F.data.startswith("game:sel_lot:"))
async def cb_sel_lot(callback: CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    sel = list(data.get("sel_lots", []))
    config = data["game_config"]
    total = config["total_rounds"]

    if lot_id in sel:
        sel.remove(lot_id)
    elif len(sel) >= total:
        await callback.answer(f"Уже выбрано {total} лотов — максимум для {total} раундов", show_alert=True)
        return
    else:
        sel.append(lot_id)

    await state.update_data(sel_lots=sel)
    selected_set = set(sel)

    async with async_session() as session:
        lots = await get_user_lots(session, callback.from_user.id)

    rounds_text = _format_round_assignments(sel, {l.id: l for l in lots})

    await callback.message.edit_text(
        f"☕ <b>Выберите лоты для игры</b>\n"
        f"Выбрано: {len(sel)}\n\n{rounds_text}",
        reply_markup=select_game_lots_kb(lots, selected_set),
    )
    await callback.answer()


@router.callback_query(GameForm.setup_lots, F.data == "game:sel_lots_clear")
async def cb_sel_lots_clear(callback: CallbackQuery, state: FSMContext):
    await state.update_data(sel_lots=[])
    async with async_session() as session:
        lots = await get_user_lots(session, callback.from_user.id)
    await callback.message.edit_text(
        f"☕ <b>Выберите лоты для игры</b>\nВыбрано: 0",
        reply_markup=select_game_lots_kb(lots),
    )
    await callback.answer()


def _format_round_assignments(sel: list, lot_map: dict) -> str:
    if not sel:
        return ""
    lines = []
    for i, lid in enumerate(sel, 1):
        lot = lot_map.get(lid)
        name = lot.title if lot else f"#{lid}"
        lines.append(f"  <b>Раунд {i}:</b> {name}")
    return "\n".join(lines)


@router.callback_query(GameForm.setup_lots, F.data == "game:sel_lots_done")
async def cb_sel_lots_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sel = data.get("sel_lots", [])
    config = data["game_config"]

    if len(sel) != config["total_rounds"]:
        await callback.answer(
            f"Выберите ровно {config['total_rounds']} лотов (сейчас {len(sel)})",
            show_alert=True,
        )
        return

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user)
        game = await create_game(
            session,
            user.id,
            total_rounds=config["total_rounds"],
            starting_chips=config["starting_chips"],
            lot_ids=sel,
        )
        game.timer_minutes = config["timer_minutes"]
        await session.commit()
        game = await get_game_by_id(session, game.id)

    await state.clear()
    code = game.code

    lot_titles = []
    if game.lot_ids:
        async with async_session() as session:
            for lid in game.lot_ids:
                lot = await get_lot_by_id(session, lid, callback.from_user.id)
                lot_titles.append(lot.title if lot else f"#{lid}")

    await callback.message.edit_text(
        format_game_setup_prompt(code, config["timer_minutes"], config["total_rounds"], 0, settings.web_url, lot_titles),
        reply_markup=game_setup_kb(),
    )
    await callback.answer(f"Создана игра {code} с {len(sel)} лотами")
