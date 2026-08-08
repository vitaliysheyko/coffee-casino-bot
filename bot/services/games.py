import random
import string
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import Game, GamePlayer, Lot, User


def generate_game_code(length: int = 4) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


async def create_game(session: AsyncSession, host_id: int) -> Game:
    while True:
        code = generate_game_code()
        exists = await session.execute(select(Game).where(Game.code == code, Game.status != "finished"))
        if not exists.scalar_one_or_none():
            break

    game = Game(code=code, host_id=host_id, status="waiting")
    session.add(game)
    await session.commit()
    await session.refresh(game)
    return game


async def get_game_by_code(session: AsyncSession, code: str) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.code == code.upper(), Game.status != "finished")
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
    )
    return result.scalar_one_or_none()


async def get_game_by_id(session: AsyncSession, game_id: int) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.players).selectinload(GamePlayer.user),
            selectinload(Game.current_lot),
        )
    )
    return result.scalar_one_or_none()


async def get_active_game_for_host(session: AsyncSession, host_id: int) -> Optional[Game]:
    result = await session.execute(
        select(Game)
        .where(Game.host_id == host_id, Game.status != "finished")
        .options(selectinload(Game.players).selectinload(GamePlayer.user))
    )
    return result.scalar_one_or_none()


async def add_player_to_game(session: AsyncSession, game: Game, user: User) -> GamePlayer:
    for p in game.players:
        if p.user_id == user.id:
            return p

    player = GamePlayer(game_id=game.id, user_id=user.id)
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    result = await session.execute(select(User).where(User.id == tg_user.id))
    user = result.scalar_one_or_none()
    if user:
        user.full_name = tg_user.full_name
        user.username = tg_user.username
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


def format_players_list(game: Game) -> str:
    if not game.players:
        return "Пока никого нет"
    
    lines = []
    for p in game.players:
        name = p.user.full_name if p.user else "Игрок"
        mark = " \u2713" if p.has_bet else ""
        lines.append(f"\u2022 {name}{mark}")
    return "\n".join(lines)
