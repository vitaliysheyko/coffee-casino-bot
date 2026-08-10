from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.constants import CATEGORY_LABELS
from bot.models import GamePlayer, Lot
from bot.services.scoring import active_categories


def game_setup_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить игрока", callback_data="game:add_player"))
    builder.row(InlineKeyboardButton(text="➖ Убрать игрока", callback_data="game:remove_player"))
    builder.row(InlineKeyboardButton(text="🧮 Калькулятор", callback_data="game:calculator"))
    builder.row(InlineKeyboardButton(text="⚙️ Множители", callback_data="game:settings"))
    builder.row(InlineKeyboardButton(text="▶️ Начать игру", callback_data="game:start_game"))
    builder.row(InlineKeyboardButton(text="❌ Отменить игру", callback_data="game:cancel"))
    return builder.as_markup()


def game_waiting_kb(can_start: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить игрока", callback_data="game:add_player"))
    builder.row(InlineKeyboardButton(text="➖ Убрать игрока", callback_data="game:remove_player"))
    builder.row(InlineKeyboardButton(text="🧮 Калькулятор", callback_data="game:calculator"))
    builder.row(InlineKeyboardButton(text="⚙️ Множители", callback_data="game:settings"))
    if can_start:
        builder.row(InlineKeyboardButton(text="🎯 Начать раунд", callback_data="game:start_round"))
    builder.row(InlineKeyboardButton(text="❌ Отменить игру", callback_data="game:cancel"))
    return builder.as_markup()


def remove_player_kb(players: list[GamePlayer]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in players:
        builder.row(InlineKeyboardButton(
            text=p.display_name,
            callback_data=f"game:remove_player_id:{p.id}",
        ))
    builder.row(InlineKeyboardButton(text="« Назад", callback_data="game:refresh"))
    return builder.as_markup()


def select_lot_kb(lots: list[Lot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        has_cats = bool(active_categories(lot))
        prefix = "☕ " if has_cats else "⚠️ "
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{lot.title}",
            callback_data=f"game:select_lot:{lot.id}",
        ))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="game:refresh"))
    return builder.as_markup()


def round_active_host_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 Сделать ревел", callback_data="game:reveal"))
    builder.row(InlineKeyboardButton(text="⏹ Досрочно завершить раунд", callback_data="game:end_round_early"))
    builder.row(InlineKeyboardButton(text="🔄 Заменить лот", callback_data="game:swap_lot"))
    return builder.as_markup()


def reveal_kb(is_last: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Отметить кто угадал", callback_data="game:score_round"))
    skip_cb = "game:finish_game" if is_last else "game:start_round"
    skip_text = "💤 Завершить игру" if is_last else "💤 Пропустить подсчёт"
    builder.row(InlineKeyboardButton(text=skip_text, callback_data=skip_cb))
    return builder.as_markup()


def build_round_result_kb(
    player_id: int,
    categories: list[str],
    current_results: Optional[dict[str, bool]] = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    current = current_results or {}
    for cat in categories:
        checked = "✅ " if current.get(cat) else "⬜ "
        builder.row(InlineKeyboardButton(
            text=f"{checked}{CATEGORY_LABELS.get(cat, cat)}",
            callback_data=f"scoring:cat:{player_id}:{cat}",
        ))
    builder.row(InlineKeyboardButton(
        text="✔️ Готово",
        callback_data=f"scoring:done:{player_id}",
    ))
    builder.row(InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="scoring:cancel",
    ))
    return builder.as_markup()


def scoring_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Подсчитать очки", callback_data="game:score_round"))
    return builder.as_markup()


def post_round_kb(is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_last:
        builder.row(InlineKeyboardButton(text="🎯 Следующий раунд", callback_data="game:start_round"))
    builder.row(InlineKeyboardButton(text="➕ Добавить раунд", callback_data="game:add_round"))
    builder.row(InlineKeyboardButton(text="📊 Турнирная таблица", callback_data="game:leaderboard"))
    builder.row(InlineKeyboardButton(text="🏁 Завершить игру", callback_data="game:finish_game"))
    return builder.as_markup()


def leaderboard_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 Следующий раунд", callback_data="game:start_round"))
    builder.row(InlineKeyboardButton(text="➕ Добавить раунд", callback_data="game:add_round"))
    builder.row(InlineKeyboardButton(text="🏁 Завершить игру", callback_data="game:finish_game"))
    return builder.as_markup()


def select_game_lots_kb(lots: list[Lot], selected_ids: Optional[set] = None) -> InlineKeyboardMarkup:
    selected = selected_ids or set()
    builder = InlineKeyboardBuilder()
    for lot in lots:
        prefix = "✅ " if lot.id in selected else "⬜ "
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{lot.title}",
            callback_data=f"game:sel_lot:{lot.id}",
        ))
    builder.row(InlineKeyboardButton(text="🔄 Очистить", callback_data="game:sel_lots_clear"))
    builder.row(
        InlineKeyboardButton(text=f"✔️ Готово ({len(selected)} выбрано)", callback_data="game:sel_lots_done"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="game:cancel"),
    )
    return builder.as_markup()


def swap_lot_kb(lots: list[Lot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        has_cats = bool(active_categories(lot))
        prefix = "☕ " if has_cats else "⚠️ "
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{lot.title}",
            callback_data=f"game:swap_to:{lot.id}",
        ))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="game:swap_cancel"))
    return builder.as_markup()
