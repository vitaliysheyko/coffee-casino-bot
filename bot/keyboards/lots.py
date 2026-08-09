from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Lot


def lots_list_kb(lots: list[Lot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        builder.row(InlineKeyboardButton(text=lot.title, callback_data=f"lots:view:{lot.id}"))
    builder.row(InlineKeyboardButton(text="Создать лот", callback_data="lots:create"))
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="main_menu"))
    return builder.as_markup()


def lot_view_kb(lot_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Редактировать", callback_data=f"lots:edit:{lot_id}"),
        InlineKeyboardButton(text="Удалить", callback_data=f"lots:delete:{lot_id}"),
    )
    builder.row(InlineKeyboardButton(text="« К списку лотов", callback_data="lots:list"))
    return builder.as_markup()


def lot_delete_confirm_kb(lot_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да, удалить", callback_data=f"lots:delete_confirm:{lot_id}"),
        InlineKeyboardButton(text="Отмена", callback_data=f"lots:view:{lot_id}"),
    )
    return builder.as_markup()


def skip_cancel_kb(with_back: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if with_back:
        builder.row(InlineKeyboardButton(text="← Назад", callback_data="lots:back"))
    builder.row(
        InlineKeyboardButton(text="Пропустить", callback_data="lots:skip"),
        InlineKeyboardButton(text="Отменить", callback_data="lots:cancel"),
    )
    return builder.as_markup()


def title_edit_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="lots:skip"))
    builder.row(InlineKeyboardButton(text="Отменить", callback_data="lots:cancel"))
    return builder.as_markup()


def lot_preview_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Сохранить лот", callback_data="lots:save"))
    builder.row(InlineKeyboardButton(text="Изменить данные", callback_data="lots:restart"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="lots:cancel"))
    return builder.as_markup()
