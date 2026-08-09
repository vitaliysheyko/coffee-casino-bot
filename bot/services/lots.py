from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import LOT_FIELDS
from bot.models import Lot


def sanitize_lot_data(data: dict) -> dict:
    return {k: v for k, v in data.items() if k in LOT_FIELDS}


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
    clean = sanitize_lot_data(data)
    lot = Lot(owner_id=owner_id, **clean)
    session.add(lot)
    await session.commit()
    await session.refresh(lot)
    return lot


async def update_lot(session: AsyncSession, lot: Lot, data: dict) -> Lot:
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


PRESET_LOTS = [
    {
        "title": "Эфиопия Иргачеффе",
        "country": "Эфиопия",
        "region": "Иргачеффе",
        "altitude": "1900–2200 м",
        "process": "мытая",
        "variety": "Heirloom",
        "score": "88",
        "roast_level": "светлая",
        "roast_date": "2026-06",
        "fact": "Эфиопия — родина кофе. Иргачеффе известен яркими цветочными и цитрусовыми нотами.",
        "notes": "Жасмин, бергамот, лимон. Лёгкое тело.",
    },
    {
        "title": "Колумбия Уила",
        "country": "Колумбия",
        "region": "Уила",
        "altitude": "1600–1800 м",
        "process": "мытая",
        "variety": "Caturra",
        "score": "86",
        "roast_level": "средняя",
        "roast_date": "2026-05",
        "fact": "Колумбия — третий по величине производитель кофе в мире.",
        "notes": "Карамель, красное яблоко, молочный шоколад.",
    },
    {
        "title": "Бразилия Серрадо",
        "country": "Бразилия",
        "region": "Серрадо",
        "altitude": "1000–1200 м",
        "process": "натуральная",
        "variety": "Bourbon",
        "score": "84",
        "roast_level": "средняя",
        "roast_date": "2026-06",
        "fact": "Бразилия — крупнейший производитель кофе, более трети мирового объёма.",
        "notes": "Орехи, тёмный шоколад, низкая кислотность.",
    },
    {
        "title": "Кения Ньери",
        "country": "Кения",
        "region": "Ньери",
        "altitude": "1700–2000 м",
        "process": "мытая",
        "variety": "SL28, SL34",
        "score": "90",
        "roast_level": "светлая",
        "roast_date": "2026-04",
        "fact": "Кенийский кофе славится яркой кислотностью чёрной смородины и красных ягод.",
        "notes": "Чёрная смородина, грейпфрут, комплексная кислотность, сочное тело.",
    },
    {
        "title": "Гватемала Антигуа",
        "country": "Гватемала",
        "region": "Антигуа",
        "altitude": "1500–1700 м",
        "process": "мытая",
        "variety": "Typica, Caturra",
        "score": "87",
        "roast_level": "средняя",
        "roast_date": "2026-05",
        "fact": "Вулканическая почва Антигуа придаёт кофе особую глубину и минеральность.",
        "notes": "Какао, ириска, лёгкий дымок. Округлое тело.",
    },
    {
        "title": "Коста-Рика Тарразу",
        "country": "Коста-Рика",
        "region": "Тарразу",
        "altitude": "1400–1700 м",
        "process": "хани",
        "variety": "Caturra, Catuai",
        "score": "86",
        "roast_level": "светлая",
        "roast_date": "2026-06",
        "fact": "Коста-Рика запретила выращивание робусты — только арабика. Хани-процессинг популяризован именно здесь.",
        "notes": "Тропические фрукты, мёд, среднее тело. Хани даёт дополнительную сладость.",
    },
]


async def create_preset_lots(session: AsyncSession, owner_id: int) -> list[Lot]:
    lots = []
    for data in PRESET_LOTS:
        lot = Lot(owner_id=owner_id, **sanitize_lot_data(data))
        session.add(lot)
        lots.append(lot)
    await session.commit()
    for lot in lots:
        await session.refresh(lot)
    return lots
