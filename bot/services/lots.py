from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Lot


async def get_user_lots(session: AsyncSession, user_id: int) -> list[Lot]:
    result = await session.execute(
        select(Lot).where(Lot.owner_id == user_id).order_by(Lot.created_at.desc())
    )
    return list(result.scalars().all())


async def get_lot_by_id(session: AsyncSession, lot_id: int, owner_id: int) -> Optional[Lot]:
    result = await session.execute(
        select(Lot).where(Lot.id == lot_id, Lot.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def create_lot(session: AsyncSession, owner_id: int, data: dict) -> Lot:
    from bot.services.games import sanitize_lot_data
    clean = sanitize_lot_data(data)
    lot = Lot(owner_id=owner_id, **clean)
    session.add(lot)
    await session.commit()
    await session.refresh(lot)
    return lot


async def update_lot(session: AsyncSession, lot: Lot, data: dict) -> Lot:
    from bot.services.games import sanitize_lot_data
    for key, value in sanitize_lot_data(data).items():
        setattr(lot, key, value)
    await session.commit()
    await session.refresh(lot)
    return lot


async def delete_lot(session: AsyncSession, lot: Lot) -> None:
    await session.delete(lot)
    await session.commit()


_EM_DASH = "\u2014"


def format_lot_for_host(lot: Lot) -> str:
    lines = [f"<b>{lot.title}</b>", ""]
    
    fields = [
        ("Страна", lot.country),
        ("Регион", lot.region),
        ("Высота", lot.altitude),
        ("Обработка", lot.process),
        ("Разновидность", lot.variety),
        ("Оценка", lot.score),
        ("Обжарка", lot.roast_level),
        ("Дата обжарки", lot.roast_date),
    ]
    
    for name, value in fields:
        lines.append(f"{name}: {value or _EM_DASH}")
    
    if lot.fact:
        lines.append(f"\n📌 Факт: {lot.fact}")
    if lot.notes:
        lines.append(f"📝 Заметки: {lot.notes}")
    
    empty = [name for name, value in fields[:6] if not value]
    if empty:
        lines.append(f"\n⚠️ Пустые игровые поля: {', '.join(empty)}")
    
    return "\n".join(lines)


def format_lot_for_players(lot: Lot) -> str:
    lines = [f"<b>{lot.title}</b>", ""]
    
    fields = [
        ("Страна", lot.country),
        ("Регион", lot.region),
        ("Высота", lot.altitude),
        ("Обработка", lot.process),
        ("Разновидность", lot.variety),
        ("Оценка", lot.score),
    ]
    
    for name, value in fields:
        if value:
            lines.append(f"{name}: {value}")
    
    return "\n".join(lines)


def get_empty_game_fields(lot: Lot) -> list[str]:
    mapping = {
        "Страна": lot.country,
        "Регион": lot.region,
        "Высота": lot.altitude,
        "Обработка": lot.process,
        "Разновидность": lot.variety,
        "Оценка": lot.score,
    }
    return [name for name, value in mapping.items() if not value]
