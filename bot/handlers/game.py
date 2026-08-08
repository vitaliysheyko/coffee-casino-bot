from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.database import async_session
from bot.keyboards.game import (
    game_waiting_kb,
    select_lot_kb,
    empty_fields_warning_kb,
    round_active_host_kb,
    reveal_host_kb,
    player_bet_kb,
    cancel_timer_kb,
)
from bot.keyboards.common import main_menu_kb, confirm_kb
from bot.models import Game, GamePlayer
from bot.services.games import (
    create_game,
    get_active_game_for_host,
    get_game_by_id,
    get_or_create_user,
    format_players_list,
)
from bot.services.lots import (
    get_user_lots,
    get_lot_by_id,
    get_empty_game_fields,
    format_lot_for_host,
    format_lot_for_players,
)
from bot.states.game import GameForm

router = Router()


def _host_waiting_text(game) -> str:
    players_count = len(game.players)
    text = (
        f"\u0418\u0433\u0440\u0430 <b>{game.code}</b>\n\n"
        f"\u0418\u0433\u0440\u043e\u043a\u043e\u0432: {players_count}\n"
        f"{format_players_list(game)}\n\n"
    )
    if players_count < 4:
        text += f"\u041d\u0443\u0436\u043d\u043e \u0435\u0449\u0451 \u043c\u0438\u043d\u0438\u043c\u0443\u043c {4 - players_count} \u0438\u0433\u0440\u043e\u043a\u0430(\u043e\u0432) \u0434\u043b\u044f \u0441\u0442\u0430\u0440\u0442\u0430."
    else:
        text += "\u041c\u043e\u0436\u043d\u043e \u043d\u0430\u0447\u0438\u043d\u0430\u0442\u044c \u0440\u0430\u0443\u043d\u0434!"
    return text
