from typing import Optional

from bot.models import Lot


def category_hint(lot: Lot) -> str:
    cats = []
    if lot.country:
        cats.append("🌍 Страна")
    if lot.region:
        cats.append("📍 Регион")
    if lot.process:
        cats.append("⚙️ Обработка")
    if lot.variety:
        cats.append("🌱 Разновидность")
    if lot.roast_level:
        cats.append("🔥 Обжарка")
    if not cats:
        return "Нет категорий для ставок."
    return "\n".join(f"• {c}" for c in cats)


def format_host_card(
    round_number: int,
    total_rounds: int,
    lot_title: str,
    timer: int,
    players_count: int,
) -> str:
    return (
        f"🎯 <b>Раунд {round_number} из {total_rounds}</b>\n\n"
        f"☕ Лот: <b>{lot_title}</b>\n"
        f"⏱ Таймер: <b>{timer} мин</b>\n"
        f"👥 Игроков за столом: <b>{players_count}</b>\n\n"
        f"<i>Категории для ставок смотрите ниже ↓</i>"
    )


def modifiers_reference() -> str:
    return (
        f"<b>🧪 Модификаторы</b>\n"
        f"• Ложка 🥄 — перемешать, угадать сорт\n"
        f"• Дичь 🦌 — экзотический способ заварки\n"
        f"• Нюхлер 👃 — определить по аромату с завязанными глазами\n"
        f"Множитель: ×2 на все угаданные\n"
        f"Лимит: 2 раза каждого за игру"
    )


def sectors_reference() -> str:
    return (
        f"<b>📊 Множители секторов</b>\n"
        f"• Континент: ×2\n"
        f"• Страна: ×3\n"
        f"• Обработка: ×2\n"
        f"• Прочее (высота/Q/сорт): ×3"
    )


def format_lot_cheatsheet(lot: Lot) -> str:
    cats = []
    if lot.country:
        cats.append(f"🌍 Страна: {lot.country}")
    if lot.region:
        cats.append(f"📍 Регион: {lot.region}")
    if lot.process:
        cats.append(f"⚙️ Обработка: {lot.process}")
    if lot.variety:
        cats.append(f"🌱 Разновидность: {lot.variety}")
    if lot.roast_level:
        cats.append(f"🔥 Обжарка: {lot.roast_level}")
    if lot.altitude:
        cats.append(f"⛰ Высота: {lot.altitude}")
    if lot.score:
        cats.append(f"⭐ Оценка: {lot.score}")

    lines = [f"<b>📋 Шпаргалка: {lot.title}</b>", ""]
    if cats:
        lines.extend(cats)
    if lot.fact:
        lines.append(f"\n📌 Факт для рассказа:\n{lot.fact}")
    if lot.notes:
        lines.append(f"\n📝 Заметки:\n{lot.notes}")
    return "\n".join(lines)


def format_game_setup_prompt(code: str, timer: int, total_rounds: int, players: int, web_url: str = "", lot_titles: Optional[list] = None) -> str:
    if web_url:
        timer_url = f"{web_url.rstrip('/')}/timer/{code.upper()}"
        timer_line = f"📺 <a href=\"{timer_url}\">Таймер для проектора</a>"
    else:
        timer_line = f"📺 Отправьте /timer_{code}, чтобы получить ссылку на таймер"

    lines = [
        f"🎲 <b>Игра {code} настроена</b>\n",
        f"Раундов: {total_rounds}",
        f"Таймер раунда: {timer} мин",
        f"Игроков: {players}",
    ]

    if lot_titles:
        lines.append("")
        lines.append("<b>Меню дегустации:</b>")
        for i, title in enumerate(lot_titles, 1):
            lines.append(f"  Раунд {i}: {title}")

    lines.append("")
    lines.append(timer_line)
    lines.append("")
    lines.append("<i>Когда все готовы — нажмите «Начать игру»</i>")
    return "\n".join(lines)


def format_finish_summary(leaderboard: str, winner_name: str) -> str:
    return (
        f"🏆 <b>Игра завершена!</b>\n\n"
        f"Победитель: <b>{winner_name}</b>\n\n"
        f"{leaderboard}\n\n"
        f"Спасибо за игру!"
    )
