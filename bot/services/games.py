from __future__ import annotations

import random
import string
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.constants import GameStatus
from bot.models import Game, GamePlayer, User


def generate_game_code(length: int = 4) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


async def create_game(
    session: AsyncSession,
    host_id: int,
    total_rounds: int = 6,
    starting_chips: int = 5,
    lot_ids: Optional[list] = None,
) -> Game:
    while True:
        code = generate_game_code()
        exists = await session.execute(
            select(Game).where(Game.code == code, Game.status != GameStatus.FINISHED)
        )
        if not exists.scalar_one_or_none():
            break

    game = Game(
        code=code,
        host_id=host_id,
        status=GameStatus.WAITING,
        total_rounds=total_rounds,
        starting_chips=starting_chips,
        lot_ids=lot_ids,
    )
    session.add(game)
    await session.commit()
    await session.refresh(game)
    return game


async def get_game_by_code(session: AsyncSession, code: str) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.code == code.upper(), Game.status != GameStatus.FINISHED)
        .options(
            selectinload(Game.players).selectinload(GamePlayer.user),
            selectinload(Game.current_lot),
            selectinload(Game.host),
        )
    )
    return result.scalar_one_or_none()


async def get_game_by_id(session: AsyncSession, game_id: int) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.players).selectinload(GamePlayer.user),
            selectinload(Game.current_lot),
            selectinload(Game.host),
        )
    )
    return result.scalar_one_or_none()


async def get_active_game_for_host(session: AsyncSession, host_id: int) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.host_id == host_id, Game.status != GameStatus.FINISHED)
        .options(
            selectinload(Game.players).selectinload(GamePlayer.user),
            selectinload(Game.current_lot),
            selectinload(Game.host),
        )
    )
    return result.scalar_one_or_none()


async def add_player_to_game(
    session: AsyncSession,
    game: Game,
    user: User,
    display_name: Optional[str] = None,
) -> GamePlayer:
    result = await session.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game.id, GamePlayer.user_id == user.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    name = display_name or user.full_name or f"Игрок {user.id}"
    player = GamePlayer(
        game_id=game.id,
        user_id=user.id,
        display_name=name,
        total_score=game.starting_chips,
    )
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    result = await session.execute(select(User).where(User.id == tg_user.id))
    user = result.scalar_one_or_none()
    if user:
        changed = False
        if user.full_name != tg_user.full_name:
            user.full_name = tg_user.full_name
            changed = True
        if user.username != tg_user.username:
            user.username = tg_user.username
            changed = True
        if changed:
            await session.commit()
        return user

    user = User(
        id=tg_user.id,
        username=tg_user.username,
        full_name=tg_user.full_name or "Без имени",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def format_players_list(players: list[GamePlayer]) -> str:
    if not players:
        return "Пока никого нет"
    lines = []
    for p in players:
        name = p.display_name
        lines.append(f"• {name} ({p.total_score} фишек)")
    return "\n".join(lines)


async def get_finished_games_for_host(session: AsyncSession, host_id: int, limit: int = 10) -> list[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.host_id == host_id, Game.status == GameStatus.FINISHED)
        .order_by(Game.finished_at.desc())
        .limit(limit)
        .options(
            selectinload(Game.players),
            selectinload(Game.round_results),
        )
    )
    return list(result.scalars().all())


def get_timer_minutes(game: Game) -> int:
    return game.timer_minutes if game.timer_minutes is not None else 5
