from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class GameForm(StatesGroup):
    setup_rounds = State()
    setup_timer = State()
    setup_chips = State()
    setup_lots = State()
    add_player = State()
    scoring = State()
    scoring_modifier = State()
    add_extra_round = State()
    bet_limit_input = State()
    bet_limit_all_input = State()
