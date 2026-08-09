from aiogram.fsm.state import State, StatesGroup


class LotForm(StatesGroup):
    title = State()
    country = State()
    region = State()
    altitude = State()
    process = State()
    variety = State()
    score = State()
    roast_level = State()
    roast_date = State()
    fact = State()
    notes = State()
    preview = State()
    import_data = State()
