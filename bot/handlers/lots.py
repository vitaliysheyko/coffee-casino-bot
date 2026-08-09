import csv
import io
import json
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import LOT_FIELDS, LOT_FIELD_NAMES
from bot.database import async_session
from bot.keyboards.lots import (
    lots_list_kb,
    lot_view_kb,
    lot_delete_confirm_kb,
    skip_cancel_kb,
    title_edit_kb,
    lot_preview_kb,
)
from bot.keyboards.common import back_to_main_kb
from bot.services.lots import (
    get_user_lots,
    get_lot_by_id,
    create_lot,
    update_lot,
    delete_lot,
    format_lot_for_host,
    sanitize_lot_data,
)
from bot.services.games import get_or_create_user
from bot.states.lot import LotForm

router = Router()
logger = logging.getLogger(__name__)

LOT_FIELDS_META = [
    ("title", "Введите название лота:", True),
    ("country", "Страна (или нажмите «Пропустить»):", False),
    ("region", "Регион / Станция:", False),
    ("altitude", "Высота (например 2100–2300 м):", False),
    ("process", "Обработка (мытая, натуральная, хани...):", False),
    ("variety", "Разновидность (сорт):", False),
    ("score", "Оценка:", False),
    ("roast_level", "Уровень обжарки:", False),
    ("roast_date", "Дата обжарки:", False),
    ("fact", "Интересный факт (видите только вы, можно показать игрокам):", False),
    ("notes", "Заметки ведущего (только для вас):", False),
]

DASH = "\u2014"
FIELD_NAMES = [f[0] for f in LOT_FIELDS_META]


def _is_bot_message(msg) -> bool:
    return msg.from_user is not None and msg.from_user.is_bot


def _title_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отменить", callback_data="lots:cancel"))
    return builder.as_markup()


def _title_prompt() -> str:
    return "Создание лота\n\nВведите название лота:"


def _edit_title_prompt(title: str) -> str:
    t = f"«{title}»" if title else ""
    return f"Редактирование лота {t}\n\nВведите новое название или нажмите «Пропустить»:"


async def _show_lots_list(session, callback_or_msg, user_id, *, edit: bool = True):
    lots = await get_user_lots(session, user_id)
    if lots:
        text = f"Ваши лоты ({len(lots)}):"
    else:
        text = "У вас пока нет лотов.\nСоздайте первый!"
    kb = lots_list_kb(lots)
    if edit and hasattr(callback_or_msg, "edit_text"):
        await callback_or_msg.edit_text(text, reply_markup=kb)
    else:
        await callback_or_msg.answer(text, reply_markup=kb)


async def _go_to_next_field(target, state: FSMContext, lot_data: dict, next_idx: int):
    if next_idx >= len(LOT_FIELDS_META):
        await state.set_state(LotForm.preview)
        text = _build_preview(lot_data)
        if _is_bot_message(target):
            await target.edit_text(text, reply_markup=lot_preview_kb())
        else:
            await target.answer(text, reply_markup=lot_preview_kb())
        return

    field_name, prompt, _ = LOT_FIELDS_META[next_idx]
    await state.set_state(getattr(LotForm, field_name))

    if field_name == "title":
        editing = (await state.get_data()).get("editing_lot_id")
        kb = title_edit_kb() if editing else _title_cancel_kb()
    else:
        kb = skip_cancel_kb(with_back=True)

    if _is_bot_message(target):
        await target.edit_text(prompt, reply_markup=kb)
    else:
        await target.answer(prompt, reply_markup=kb)


def _build_preview(data: dict) -> str:
    lines = ["<b>Превью лота:</b>", ""]
    for key, label in LOT_FIELD_NAMES.items():
        val = data.get(key)
        lines.append(f"{label}: {val or DASH}")

    empty = [LOT_FIELD_NAMES[k] for k in ["country", "region", "altitude", "process", "variety", "score"] if not data.get(k)]
    if empty:
        lines.append(f"\n⚠️ Пустые игровые поля: {', '.join(empty)}")
    return "\n".join(lines)


def _lot_data_from_model(lot) -> dict:
    return {
        "title": lot.title,
        "country": lot.country,
        "region": lot.region,
        "altitude": lot.altitude,
        "process": lot.process,
        "variety": lot.variety,
        "score": lot.score,
        "roast_level": lot.roast_level,
        "roast_date": lot.roast_date,
        "fact": lot.fact,
        "notes": lot.notes,
    }


# --- List ---

@router.callback_query(F.data == "lots:list")
async def cb_lots_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await get_or_create_user(session, callback.from_user)
        await _show_lots_list(session, callback.message, callback.from_user.id)
    await callback.answer()


# --- View ---

@router.callback_query(F.data.startswith("lots:view:"))
async def cb_lot_view(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return
    text = format_lot_for_host(lot)
    await callback.message.edit_text(text, reply_markup=lot_view_kb(lot.id))
    await callback.answer()


# --- Create ---

@router.callback_query(F.data == "lots:create")
async def cb_lot_create(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(LotForm.title)
    await state.update_data(lot_data={}, editing_lot_id=None)
    await callback.message.edit_text(_title_prompt(), reply_markup=_title_cancel_kb())
    await callback.answer()


# --- Edit ---

@router.callback_query(F.data.startswith("lots:edit:"))
async def cb_lot_edit(callback: CallbackQuery, state: FSMContext):
    lot_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        lot = await get_lot_by_id(session, lot_id, callback.from_user.id)
    if not lot:
        await callback.answer("Лот не найден", show_alert=True)
        return
    lot_data = _lot_data_from_model(lot)
    await state.clear()
    await state.set_state(LotForm.title)
    await state.update_data(lot_data=lot_data, editing_lot_id=lot_id)
    await callback.message.edit_text(
        _edit_title_prompt(lot.title),
        reply_markup=title_edit_kb(),
    )
    await callback.answer()


# --- Cancel ---

@router.callback_query(F.data == "lots:cancel")
async def cb_lot_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session() as session:
        await _show_lots_list(session, callback.message, callback.from_user.id)
    await callback.answer()


# --- Skip ---

@router.callback_query(F.data == "lots:skip")
async def cb_lot_skip(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if not current:
        await callback.answer()
        return

    data = await state.get_data()
    lot_data = data.get("lot_data", {})

    field_name = current.split(":")[-1]
    if field_name not in FIELD_NAMES:
        await callback.answer()
        return

    idx = FIELD_NAMES.index(field_name)
    await _go_to_next_field(callback.message, state, lot_data, idx + 1)
    await callback.answer()


# --- Field input ---

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
    editing_lot_id = data.get("editing_lot_id")

    if field_name == "title" and not value and not editing_lot_id:
        await message.answer("Название обязательно. Введите название лота:")
        return

    lot_data[field_name] = value if value != "-" else None
    await state.update_data(lot_data=lot_data)

    idx = FIELD_NAMES.index(field_name)
    await _go_to_next_field(message, state, lot_data, idx + 1)


# --- Save ---

@router.callback_query(F.data == "lots:save")
async def cb_lot_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lot_data = data.get("lot_data", {})
    editing_lot_id = data.get("editing_lot_id")

    if not lot_data.get("title"):
        await callback.answer("Название обязательно", show_alert=True)
        return

    async with async_session() as session:
        await get_or_create_user(session, callback.from_user)
        if editing_lot_id:
            lot = await get_lot_by_id(session, editing_lot_id, callback.from_user.id)
            if not lot:
                await callback.answer("Лот не найден", show_alert=True)
                return
            lot = await update_lot(session, lot, lot_data)
            verb = "обновлён"
        else:
            lot = await create_lot(session, callback.from_user.id, lot_data)
            verb = "сохранён"

    await state.clear()
    await callback.message.edit_text(
        f"Лот «{lot.title}» {verb}!", reply_markup=lot_view_kb(lot.id)
    )
    await callback.answer()


# --- Restart ---

@router.callback_query(F.data == "lots:restart")
async def cb_lot_restart(callback: CallbackQuery, state: FSMContext):
    editing_lot_id = (await state.get_data()).get("editing_lot_id")
    await state.clear()
    await state.set_state(LotForm.title)
    await state.update_data(lot_data={}, editing_lot_id=editing_lot_id)
    if editing_lot_id:
        prompt = _edit_title_prompt("")
        kb = title_edit_kb()
    else:
        prompt = _title_prompt()
        kb = _title_cancel_kb()
    await callback.message.edit_text(prompt, reply_markup=kb)
    await callback.answer()


# --- Back ---

@router.callback_query(F.data == "lots:back")
async def cb_lot_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if not current:
        await callback.answer()
        return

    data = await state.get_data()
    lot_data = data.get("lot_data", {})

    field_name = current.split(":")[-1]
    if field_name not in FIELD_NAMES:
        await callback.answer()
        return

    idx = FIELD_NAMES.index(field_name)
    if idx <= 0:
        await callback.answer()
        return

    await _go_to_next_field(callback.message, state, lot_data, idx - 1)
    await callback.answer()


# --- Delete ---

@router.callback_query(F.data.startswith("lots:delete:"))
async def cb_lot_delete(callback: CallbackQuery):
    lot_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "Вы уверены, что хотите удалить этот лот?",
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
        await _show_lots_list(session, callback.message, callback.from_user.id)
    await callback.answer()


# --- Import ---

IMPORT_EXAMPLE = (
    "<b>Импорт лотов</b>\n\n"
    "Отправьте CSV (заголовки: title,country,region,altitude,process,variety,score,roast_level,roast_date,fact,notes)\n\n"
    "Или JSON: список объектов с теми же полями.\n\n"
    "Пример CSV:\n"
    "<code>title,country,region,process\n"
    "Эфиопия Гуджи,Эфиопия,Гуджи,мытая\n"
    "Колумбия Уила,Колумбия,Уила,мытая</code>\n\n"
    "Пример JSON:\n"
    '<code>[{"title":"Эфиопия","country":"Эфиопия"}]</code>'
)


@router.callback_query(F.data == "lots:import")
async def cb_lots_import(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LotForm.import_data)
    await callback.message.edit_text(IMPORT_EXAMPLE, reply_markup=back_to_main_kb())
    await callback.answer()


@router.message(LotForm.import_data)
async def process_import(message: Message, state: FSMContext):
    document = message.document

    if document:
        file = await message.bot.get_file(document.file_id)
        content = await message.bot.download_file(file.file_path)
        text = content.read().decode("utf-8-sig")
    elif message.text:
        text = message.text
    else:
        await message.answer("Отправьте CSV/JSON файл или вставьте текст.")
        return

    async with async_session() as session:
        await get_or_create_user(session, message.from_user)
        lots_data = _parse_import(text)
        if not lots_data:
            await message.answer(
                "Не удалось распознать данные. Проверьте формат.",
                reply_markup=back_to_main_kb(),
            )
            await state.clear()
            return

        created = 0
        for data in lots_data:
            clean = sanitize_lot_data(data)
            if not clean.get("title"):
                continue
            await create_lot(session, message.from_user.id, clean)
            created += 1

    await state.clear()
    await message.answer(
        f"Импортировано лотов: {created}",
        reply_markup=back_to_main_kb(),
    )


def _parse_import(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(row) for row in reader]
        if rows:
            return rows
    except Exception:
        logger.warning("Failed to parse import as CSV", exc_info=True)

    return []
