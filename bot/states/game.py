from aiogram.fsm.state import State, StatesGroup


class GameForm(StatesGroup):
    waiting_timer = State()
