from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Мои лоты", callback_data="lots:list"))
    builder.row(InlineKeyboardButton(text="Создать игру", callback_data="game:create"))
    builder.row(InlineKeyboardButton(text="🎲 Быстрая игра", callback_data="quick_game"))
    builder.row(InlineKeyboardButton(text="Помощь", callback_data="help"))
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="main_menu"))
    return builder.as_markup()


def confirm_kb(yes_data: str, no_data: str, yes_text: str = "Да", no_text: str = "Отмена") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=yes_text, callback_data=yes_data),
        InlineKeyboardButton(text=no_text, callback_data=no_data),
    )
    return builder.as_markup()
