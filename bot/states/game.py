from aiogram.fsm.state import State, StatesGroup


class GameForm(StatesGroup):
    setup_rounds = State()
    setup_timer = State()
    setup_chips = State()
    add_player = State()
    scoring = State()
