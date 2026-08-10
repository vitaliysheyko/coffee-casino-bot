from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import BET_CATEGORIES, CATEGORY_LABELS, MODIFIER_LABELS, MODIFIER_TYPES
from bot.models import Game, GamePlayer, Lot, RoundResult


def active_categories(lot: Lot) -> list[str]:
    return [cat for cat in BET_CATEGORIES if getattr(lot, cat, None)]


def calculate_round_score(
    results: dict[str, bool],
    active_cats: list[str],
    bet_per_category: int = 1,
    modifier_applied: bool = False,
    modifier_multiplier: int = 2,
) -> tuple[int, int, int]:
    correct = sum(1 for cat in active_cats if results.get(cat, False))
    wrong = len(active_cats) - correct
    won = correct * bet_per_category * 2
    if modifier_applied and won > 0:
        won *= modifier_multiplier
    lost = wrong * bet_per_category
    return correct, won - lost, lost


def apply_round_result(
    player: GamePlayer,
    lot: Lot,
    round_number: int,
    category_results: dict[str, bool],
    modifier_type: Optional[str] = None,
    modifier_multiplier: int = 2,
    bet_per_category: int = 1,
) -> RoundResult:
    cats = active_categories(lot)
    modifier_applied = modifier_type in MODIFIER_TYPES
    correct_count, score_delta, chips_lost = calculate_round_score(
        category_results,
        cats,
        bet_per_category,
        modifier_applied,
        modifier_multiplier,
    )

    result = RoundResult(
        game_id=player.game_id,
        player_id=player.id,
        lot_id=lot.id,
        round_number=round_number,
        country_correct=category_results.get("country", False),
        region_correct=category_results.get("region", False),
        process_correct=category_results.get("process", False),
        variety_correct=category_results.get("variety", False),
        roast_level_correct=category_results.get("roast_level", False),
        modifier_type=modifier_type,
        modifier_applied=modifier_applied,
        chips_won=score_delta,
    )

    player.total_score += score_delta
    return result


async def count_modifier_usage(
    session: AsyncSession,
    game_id: int,
    player_id: int,
    modifier_type: str,
) -> int:
    result = await session.execute(
        select(func.count(RoundResult.id)).where(
            RoundResult.game_id == game_id,
            RoundResult.player_id == player_id,
            RoundResult.modifier_type == modifier_type,
            RoundResult.modifier_applied == True,
        )
    )
    return result.scalar_one() or 0


def build_leaderboard(players: list[GamePlayer]) -> list[dict]:
    sorted_players = sorted(players, key=lambda p: p.total_score, reverse=True)
    return [
        {
            "rank": i + 1,
            "name": p.display_name,
            "score": p.total_score,
        }
        for i, p in enumerate(sorted_players)
    ]


def format_leaderboard(players: list[GamePlayer], title: str = "Турнирная таблица") -> str:
    board = build_leaderboard(players)
    lines = [f"<b>{title}</b>", ""]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for entry in board:
        medal = medals.get(entry["rank"], f"{entry['rank']}.")
        lines.append(f"{medal} {entry['name']}: {entry['score']} фишек")
    return "\n".join(lines)


def format_round_summary(round_number: int, lot: Lot, results: list[RoundResult]) -> str:
    lines = [f"<b>Раунд {round_number} — итоги</b>", f"Лот: {lot.title}", ""]
    cats = active_categories(lot)
    cat_labels = CATEGORY_LABELS
    lines.append("Правильные ответы:")
    for cat in cats:
        val = getattr(lot, cat, None)
        lines.append(f"  {cat_labels.get(cat, cat)}: {val}")

    if results:
        lines.append("")
        lines.append("Результаты игроков:")
        for r in results:
            player = r.player
            correct_cats = [cat_labels[c] for c in cats if getattr(r, f"{c}_correct", False)]
            mod_text = ""
            if r.modifier_applied and r.modifier_type:
                mod_text = f" [{MODIFIER_LABELS.get(r.modifier_type, r.modifier_type)}]"
            if correct_cats:
                sign = "+" if r.chips_won >= 0 else ""
                lines.append(f"  {player.display_name}: {sign}{r.chips_won}{mod_text} ({' + '.join(correct_cats)})")
            else:
                lines.append(f"  {player.display_name}: {r.chips_won}{mod_text} (не угадал ни одной категории)")
    return "\n".join(lines)
