from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Lot


def game_waiting_kb(can_start: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Обновить список", callback_data="game:refresh"))
    if can_start:
        builder.row(InlineKeyboardButton(text="Начать раунд", callback_data="game:start_round"))
    builder.row(InlineKeyboardButton(text="Отменить игру", callback_data="game:cancel"))
    return builder.as_markup()


def select_lot_kb(lots: list[Lot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        builder.row(InlineKeyboardButton(text=lot.title, callback_data=f"game:select_lot:{lot.id}"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="game:refresh"))
    return builder.as_markup()


def empty_fields_warning_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Всё равно запустить", callback_data="game:confirm_start"))
    builder.row(InlineKeyboardButton(text="Выбрать другой лот", callback_data="game:start_round"))
    return builder.as_markup()


def round_active_host_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Показать факт", callback_data="game:show_fact"),
        InlineKeyboardButton(text="Сделать ревейл", callback_data="game:reveal"),
    )
    builder.row(InlineKeyboardButton(text="Завершить раунд досрочно", callback_data="game:end_round_early"))
    return builder.as_markup()


def reveal_host_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Начать следующий раунд", callback_data="game:start_round"))
    builder.row(InlineKeyboardButton(text="Завершить игру", callback_data="game:finish"))
    return builder.as_markup()


def player_bet_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Я сделал ставки", callback_data="game:place_bet"))
    return builder.as_markup()


def cancel_timer_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="game:refresh"))
    return builder.as_markup()
