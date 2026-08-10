from __future__ import annotations

from datetime import datetime
from typing import Optional

from bot.models import Game
from bot.services.scoring import build_leaderboard


def format_game_history_list(games: list[Game]) -> str:
    if not games:
        return "<b>История игр</b>\n\nУ вас пока нет завершённых игр."

    lines = ["<b>История игр</b>", ""]
    for g in games:
        finished = g.finished_at.strftime("%d.%m.%Y %H:%M") if g.finished_at else "—"
        winner = build_leaderboard(g.players)[0]["name"] if g.players else "—"
        lines.append(f"• <b>{g.code}</b> — {finished}\n  Победитель: {winner}")
    return "\n".join(lines)


def format_game_details(game: Game) -> str:
    if not game:
        return "Игра не найдена."

    lines = [
        f"<b>Игра {game.code}</b>",
        f"Раундов: {game.total_rounds}",
        f"Игроков: {len(game.players)}",
    ]
    if game.finished_at:
        lines.append(f"Завершена: {game.finished_at.strftime('%d.%m.%Y %H:%M')}")

    lines.append("")
    lines.append("<b>Турнирная таблица</b>")
    for entry in build_leaderboard(game.players):
        lines.append(f"{entry['rank']}. {entry['name']}: {entry['score']} фишек")

    if game.round_results:
        lines.append("")
        lines.append("<b>Раунды</b>")
        by_round = {}
        for rr in game.round_results:
            by_round.setdefault(rr.round_number, []).append(rr)
        for round_num in sorted(by_round.keys()):
            results = by_round[round_num]
            lot_title = results[0].lot.title if results[0].lot else "?"
            lines.append(f"\nРаунд {round_num} — {lot_title}")
            for rr in results:
                sign = "+" if rr.chips_won >= 0 else ""
                lines.append(f"  {rr.player.display_name}: {sign}{rr.chips_won}")

    return "\n".join(lines)
