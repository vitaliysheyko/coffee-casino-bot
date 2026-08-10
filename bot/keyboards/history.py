from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Game


def history_list_kb(games: list[Game]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for g in games:
        finished = g.finished_at.strftime("%d.%m.%Y") if g.finished_at else "—"
        builder.row(InlineKeyboardButton(
            text=f"{g.code} — {finished}",
            callback_data=f"history:view:{g.id}",
        ))
    builder.row(InlineKeyboardButton(text="« В главное меню", callback_data="main_menu"))
    return builder.as_markup()
