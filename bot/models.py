from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram ID
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
    
    # Игровые поля (опциональные)
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    altitude: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    process: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    variety: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    score: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    
    # Дополнительные
    roast_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    roast_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Только для ведущего
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
    
    status: Mapped[str] = mapped_column(String(32), default="waiting")  # waiting | round_active | reveal | finished
    
    current_lot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("lots.id"), nullable=True)
    current_lot_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timer_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    round_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    host: Mapped["User"] = relationship(back_populates="games_as_host")
    current_lot: Mapped[Optional["Lot"]] = relationship()
    players: Mapped[list["GamePlayer"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class GamePlayer(Base):
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    
    has_bet: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="players")
    user: Mapped["User"] = relationship()
