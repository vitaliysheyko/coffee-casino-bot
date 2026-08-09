BET_CATEGORIES = ["country", "region", "process", "variety", "roast_level"]

CATEGORY_LABELS = {
    "country": "Страна",
    "region": "Регион",
    "process": "Обработка",
    "variety": "Разновидность",
    "roast_level": "Обжарка",
}

LOT_FIELD_NAMES = {
    "title": "Название",
    "country": "Страна",
    "region": "Регион",
    "altitude": "Высота",
    "process": "Обработка",
    "variety": "Разновидность",
    "score": "Оценка",
    "roast_level": "Обжарка",
    "roast_date": "Дата обжарки",
    "fact": "Факт",
    "notes": "Заметки",
}

LOT_FIELDS = list(LOT_FIELD_NAMES.keys())


class GameStatus:
    WAITING = "waiting"
    ROUND_ACTIVE = "round_active"
    REVEAL = "reveal"
    FINISHED = "finished"


class CallbackPrefix:
    GAME = "game"
    LOT = "lots"
    SCORING = "scoring"
    HISTORY = "history"
    MAIN_MENU = "main_menu"
    HELP = "help"
    QUICK_GAME = "quick_game"
