from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database import async_session
from bot.keyboards.lots import (
    lots_list_kb,
    lot_view_kb,
    lot_delete_confirm_kb,
    skip_cancel_kb,
    lot_preview_kb,
)
from bot.keyboards.common import main_menu_kb
from bot.services.lots import (
    get_user_lots,
    get_lot_by_id,
    create_lot,
    delete_lot,
    format_lot_for_host,
)
from bot.services.games import get_or_create_user
from bot.states.lot import LotForm

router = Router()

LOT_FIELDS = [
    ("title", "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430:", True),
    ("country", "\u0421\u0442\u0440\u0430\u043d\u0430 (\u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c\u00bb):", False),
    ("region", "\u0420\u0435\u0433\u0438\u043e\u043d / \u0421\u0442\u0430\u043d\u0446\u0438\u044f:", False),
    ("altitude", "\u0412\u044b\u0441\u043e\u0442\u0430 (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 2100\u20132300 \u043c):", False),
    ("process", "\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 (\u043c\u044b\u0442\u0430\u044f, \u043d\u0430\u0442\u0443\u0440\u0430\u043b\u044c\u043d\u0430\u044f, \u0445\u0430\u043d\u0438...):", False),
    ("variety", "\u0420\u0430\u0437\u043d\u043e\u0432\u0438\u0434\u043d\u043e\u0441\u0442\u044c (\u0441\u043e\u0440\u0442):", False),
    ("score", "\u041e\u0446\u0435\u043d\u043a\u0430:", False),
    ("roast_level", "\u0423\u0440\u043e\u0432\u0435\u043d\u044c \u043e\u0431\u0436\u0430\u0440\u043a\u0438:", False),
    ("roast_date", "\u0414\u0430\u0442\u0430 \u043e\u0431\u0436\u0430\u0440\u043a\u0438:", False),
    ("fact", "\u0418\u043d\u0442\u0435\u0440\u0435\u0441\u043d\u044b\u0439 \u0444\u0430\u043a\u0442 (\u0432\u0438\u0434\u0438\u0442\u0435 \u0442\u043e\u043b\u044c\u043a\u043e \u0432\u044b, \u043c\u043e\u0436\u043d\u043e \u043f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0438\u0433\u0440\u043e\u043a\u0430\u043c):", False),
    ("notes", "\u0417\u0430\u043c\u0435\u0442\u043a\u0438 \u0432\u0435\u0434\u0443\u0449\u0435\u0433\u043e (\u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0432\u0430\u0441):", False),
]


@router.callback_query(F.data == "lots:list")
async def cb_lots_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await get_or_create_user(session, callback.from_user)
        lots = await get_user_lots(session, callback.from_user.id)

    if not lots:
        text = "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u043b\u043e\u0442\u043e\u0432.\n\u0421\u043e\u0437\u0434\u0430\u0439\u0442\u0435 \u043f\u0435\u0440\u0432\u044b\u0439!"
    else:
        text = f"\u0412\u0430\u0448\u0438 \u043b\u043e\u0442\u044b ({len(lots)}):"

    await callback.message.edit_text(text, reply_markup=lots_list_kb(lots))
    await callback.answer()


@router.callback_query(F.data.startswith("lots:view:"))
async def cb_lot_view(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)

    if not lot:
        await callback.answer("\u041b\u043e\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", show_alert=True)
        return

    text = format_lot_for_host(lot)
    await callback.message.edit_text(text, reply_markup=lot_view_kb(lot.id))
    await callback.answer()


@router.callback_query(F.data.startswith("lots:delete:"))
async def cb_lot_delete(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "\u0412\u044b \u0443\u0432\u0435\u0440\u0435\u043d\u044b, \u0447\u0442\u043e \u0445\u043e\u0442\u0438\u0442\u0435 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u044d\u0442\u043e\u0442 \u043b\u043e\u0442?",
        reply_markup=lot_delete_confirm_kb(lot_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lots:delete_confirm:"))
async def cb_lot_delete_confirm(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
        if lot:
            await delete_lot(session, lot)

    async with async_session() as session:
        lots = await get_user_lots(session, callback.from_user.id)
    await callback.message.edit_text(
        f"\u0412\u0430\u0448\u0438 \u043b\u043e\u0442\u044b ({len(lots)}):" if lots else "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u043b\u043e\u0442\u043e\u0432.",
        reply_markup=lots_list_kb(lots),
    )
    await callback.answer()


@router.callback_query(F.data == "lots:create")
async def cb_lot_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(LotForm.title)
    await state.update_data(lot_data={})
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="\u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c", callback_data="lots:cancel"))
    await callback.message.edit_text(
        "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430\n\n\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "lots:cancel")
async def cb_lot_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        lots = await get_user_lots(session, callback.from_user.id)
    await callback.message.edit_text(
        f"\u0412\u0430\u0448\u0438 \u043b\u043e\u0442\u044b ({len(lots)}):" if lots else "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u043b\u043e\u0442\u043e\u0432.",
        reply_markup=lots_list_kb(lots),
    )
    await callback.answer()


@router.callback_query(F.data == "lots:skip")
async def cb_lot_skip(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if not current:
        await callback.answer()
        return

    data = await state.get_data()
    lot_data = data.get("lot_data", {})

    field_names = [f[0] for f in LOT_FIELDS]
    try:
        idx = field_names.index(current.split(":")[-1])
    except ValueError:
        await callback.answer()
        return

    await _go_to_next_field(callback.message, state, lot_data, idx + 1)
    await callback.answer()


@router.message(LotForm.title)
@router.message(LotForm.country)
@router.message(LotForm.region)
@router.message(LotForm.altitude)
@router.message(LotForm.process)
@router.message(LotForm.variety)
@router.message(LotForm.score)
@router.message(LotForm.roast_level)
@router.message(LotForm.roast_date)
@router.message(LotForm.fact)
@router.message(LotForm.notes)
async def process_lot_field(message: Message, state: FSMContext):
    current = await state.get_state()
    field_name = current.split(":")[-1]
    value = message.text.strip()

    data = await state.get_data()
    lot_data = data.get("lot_data", {})

    if field_name == "title" and not value:
        await message.answer("\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e. \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430:")
        return

    lot_data[field_name] = value if value != "-" else None
    await state.update_data(lot_data=lot_data)

    field_names = [f[0] for f in LOT_FIELDS]
    idx = field_names.index(field_name)
    await _go_to_next_field(message, state, lot_data, idx + 1)


def _is_bot_message(msg) -> bool:
    return msg.from_user is not None and msg.from_user.is_bot


async def _go_to_next_field(message_or_msg, state: FSMContext, lot_data: dict, next_idx: int):
    if next_idx >= len(LOT_FIELDS):
        await state.set_state(LotForm.preview)
        text = _build_preview(lot_data)
        if _is_bot_message(message_or_msg):
            await message_or_msg.edit_text(text, reply_markup=lot_preview_kb())
        else:
            await message_or_msg.answer(text, reply_markup=lot_preview_kb())
        return

    field_name, prompt, required = LOT_FIELDS[next_idx]
    await state.set_state(getattr(LotForm, field_name))

    if field_name == "title":
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="\u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c", callback_data="lots:cancel"))
        kb = builder.as_markup()
    else:
        kb = skip_cancel_kb()

    if _is_bot_message(message_or_msg):
        await message_or_msg.edit_text(prompt, reply_markup=kb)
    else:
        await message_or_msg.answer(prompt, reply_markup=kb)


def _build_preview(data: dict) -> str:
    lines = ["<b>\u041f\u0440\u0435\u0432\u044c\u044e \u043b\u043e\u0442\u0430:</b>", ""]
    labels = {
        "title": "\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435",
        "country": "\u0421\u0442\u0440\u0430\u043d\u0430",
        "region": "\u0420\u0435\u0433\u0438\u043e\u043d",
        "altitude": "\u0412\u044b\u0441\u043e\u0442\u0430",
        "process": "\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430",
        "variety": "\u0420\u0430\u0437\u043d\u043e\u0432\u0438\u0434\u043d\u043e\u0441\u0442\u044c",
        "score": "\u041e\u0446\u0435\u043d\u043a\u0430",
        "roast_level": "\u041e\u0431\u0436\u0430\u0440\u043a\u0430",
        "roast_date": "\u0414\u0430\u0442\u0430 \u043e\u0431\u0436\u0430\u0440\u043a\u0438",
        "fact": "\u0424\u0430\u043a\u0442",
        "notes": "\u0417\u0430\u043c\u0435\u0442\u043a\u0438",
    }
    for key, label in labels.items():
        val = data.get(key)
        lines.append(f"{label}: {val or '\u2014'}")

    empty = [labels[k] for k in ["country", "region", "altitude", "process", "variety", "score"] if not data.get(k)]
    if empty:
        lines.append(f"\n\u26a0\ufe0f \u041f\u0443\u0441\u0442\u044b\u0435 \u0438\u0433\u0440\u043e\u0432\u044b\u0435 \u043f\u043e\u043b\u044f: {', '.join(empty)}")

    return "\n".join(lines)


@router.callback_query(F.data == "lots:save")
async def cb_lot_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lot_data = data.get("lot_data", {})

    if not lot_data.get("title"):
        await callback.answer("\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e", show_alert=True)
        return

    async with async_session() as session:
        await get_or_create_user(session, callback.from_user)
        lot = await create_lot(session, callback.from_user.id, lot_data)

    await state.clear()
    await callback.message.edit_text(
        f"\u041b\u043e\u0442 \u00ab{lot.title}\u00bb \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d!",
        reply_markup=lot_view_kb(lot.id),
    )
    await callback.answer()


@router.callback_query(F.data == "lots:restart")
async def cb_lot_restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(LotForm.title)
    await state.update_data(lot_data={})
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="\u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c", callback_data="lots:cancel"))
    await callback.message.edit_text(
        "\u0421\u043e\u0437\u0434\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430\n\n\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043b\u043e\u0442\u0430:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
