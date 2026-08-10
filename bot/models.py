from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bot.constants import BET_CATEGORIES, CATEGORY_LABELS, GameStatus


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lots: Mapped[list["Lot"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    games_as_host: Mapped[list["Game"]] = relationship(back_populates="host")


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))

    title: Mapped[str] = mapped_column(String(128))

    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    altitude: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    process: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    variety: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    score: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    roast_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    roast_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    fact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="lots")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    host_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    status: Mapped[str] = mapped_column(String(32), default=GameStatus.WAITING)

    current_lot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("lots.id"), nullable=True)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=6)
    starting_chips: Mapped[int] = mapped_column(Integer, default=5)

    lot_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    current_lot_index: Mapped[int] = mapped_column(Integer, default=-1)

    timer_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    round_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    host: Mapped["User"] = relationship(back_populates="games_as_host")
    current_lot: Mapped[Optional["Lot"]] = relationship(foreign_keys=[current_lot_id])
    players: Mapped[list["GamePlayer"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    round_results: Mapped[list["RoundResult"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class GamePlayer(Base):
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    display_name: Mapped[str] = mapped_column(String(64))
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="players")
    user: Mapped["User"] = relationship()
    results: Mapped[list["RoundResult"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class RoundResult(Base):
    __tablename__ = "round_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_players.id", ondelete="CASCADE"))
    lot_id: Mapped[int] = mapped_column(Integer, ForeignKey("lots.id"))
    round_number: Mapped[int] = mapped_column(Integer)

    country_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    region_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    process_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    variety_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    roast_level_correct: Mapped[bool] = mapped_column(Boolean, default=False)

    chips_won: Mapped[int] = mapped_column(Integer, default=0)

    game: Mapped["Game"] = relationship(back_populates="round_results")
    player: Mapped["GamePlayer"] = relationship(back_populates="results")
    lot: Mapped["Lot"] = relationship()
