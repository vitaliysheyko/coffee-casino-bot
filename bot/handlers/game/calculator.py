import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.services.games import get_active_game_for_host, get_game_by_id
from bot.models import GameSettings

router = Router()
logger = logging.getLogger(__name__)

CHIPS = [5, 10, 25, 50, 100]


async def _get_game_multipliers(callback: CallbackQuery) -> tuple[list[int], int, bool]:
    """Returns (sector multipliers, modifier multiplier, modifiers enabled)"""
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game = await get_game_by_id(session, game.id)
            s = game.settings if game.settings else GameSettings(game_id=game.id)
            mults = list(dict.fromkeys([s.sector_continent, s.sector_country, s.sector_process, s.sector_other]))
            return sorted(mults), s.modifier_multiplier, s.modifiers_enabled
    return [2, 3], 2, True  # defaults


def _player_calc_kb(player_id: int, modifier_on: bool, has_bets: bool, mults: list[int], mod_mult: int,
                     prev_id: int = 0, next_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    for val in CHIPS:
        b.button(text=str(val), callback_data=f"calc:chip:{player_id}:{val}")
    b.adjust(len(CHIPS))

    b.button(text="❌", callback_data=f"calc:mult:{player_id}:0")
    for m in mults:
        b.button(text=f"×{m}", callback_data=f"calc:mult:{player_id}:{m}")
    b.adjust(1 + len(mults))

    mod_text = f"🧪 Мод ×{mod_mult}: ON" if modifier_on else f"🧪 Мод ×{mod_mult}: OFF"
    b.button(text=mod_text, callback_data=f"calc:mod:{player_id}")

    if has_bets:
        b.button(text="↩ Отменить", callback_data=f"calc:undo:{player_id}")
        b.button(text="💾 Сохранить", callback_data=f"calc:save:{player_id}")

    nav = []
    if prev_id:
        nav.append(InlineKeyboardButton(text="◀ Пред", callback_data=f"calc:open:{prev_id}"))
    b.button(text="« Список", callback_data="game:calculator")
    if next_id:
        nav.append(InlineKeyboardButton(text="След ▶", callback_data=f"calc:open:{next_id}"))
    if nav:
        b.row(*nav)

    return b.as_markup()


def _round_total(bets: list, mod: bool, mod_mult: int = 2) -> int:
    won = sum(b["amount"] * b["mult"] for b in bets if b["mult"])
    lost = sum(b["amount"] for b in bets if not b["mult"])
    if mod:
        won *= mod_mult
    return won - lost


def _format_bets(bets: list) -> str:
    if not bets:
        return "—"
    lines = []
    for i, bet in enumerate(bets, 1):
        amt = bet["amount"]
        m = bet["mult"]
        if m == 0:
            lines.append(f"{i}. {amt}♟ ❌ = −{amt}")
        else:
            lines.append(f"{i}. {amt}♟ ×{m} = +{amt * m}")
    return "\n".join(lines)


async def _get_calc_state(state: FSMContext):
    d = await state.get_data()
    return d.get("calc_bets", []), d.get("calc_mod", False)


@router.callback_query(F.data == "game:calculator")
async def cb_calculator(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет активной игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        players = list(game.players)

    if not players:
        await callback.answer("Нет игроков", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for p in players:
        b.button(text=f"{p.display_name} ({p.total_score}♟)", callback_data=f"calc:open:{p.id}")
    b.adjust(1)
    b.button(text="« Назад к игре", callback_data="game:refresh")

    await callback.message.edit_text("🧮 <b>Калькулятор</b>\n\nВыберите игрока:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("calc:open:"))
async def cb_calc_open(callback: CallbackQuery, state: FSMContext):
    player_id = int(callback.data.split(":")[2])
    await state.update_data(calc_player_id=player_id, calc_bets=[], calc_mod=False)
    await _render(callback, state)
    await callback.answer()


async def _render(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    player_id = d.get("calc_player_id")
    if not player_id:
        return
    bets = d.get("calc_bets", [])
    mod = d.get("calc_mod", False)

    mults, mod_mult, _ = await _get_game_multipliers(callback)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.message.edit_text("Нет игры.", reply_markup=InlineKeyboardBuilder().as_markup())
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)

    if not player:
        await callback.message.edit_text("Игрок не найден.")
        return

    ids = [p.id for p in game.players]
    idx = ids.index(player_id)
    prev_id = ids[idx - 1] if idx > 0 else 0
    next_id = ids[idx + 1] if idx < len(ids) - 1 else 0

    rt = _round_total(bets, mod, mod_mult)
    won = sum(b["amount"] * b["mult"] for b in bets if b["mult"])
    lost = sum(b["amount"] for b in bets if not b["mult"])

    text = (
        f"🧮 <b>{player.display_name}</b>\n"
        f"Баланс: {player.total_score}♟\n\n"
        f"<b>Ставки:</b>\n{_format_bets(bets)}\n"
    )
    if won:
        text += f"\n<b>Выигрыш: +{won}♟</b>"
        if mod:
            text += f" → ×{mod_mult}🧪 = <b>+{won * mod_mult}♟</b>"
    if lost:
        text += f"\n<b>Проигрыш: −{lost}♟</b>"
    text += f"\n\n<b>Итого раунд: {rt:+d}♟</b>\n"
    text += f"После раунда: <b>{player.total_score + rt}♟</b>"

    await callback.message.edit_text(text, reply_markup=_player_calc_kb(player_id, mod, len(bets) > 0, mults, mod_mult, prev_id, next_id))


@router.callback_query(F.data.startswith("calc:mod:"))
async def cb_calc_mod(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    mod = not d.get("calc_mod", False)
    await state.update_data(calc_mod=mod)
    await _render(callback, state)
    await callback.answer(f"Модификатор {'ON' if mod else 'OFF'}")


@router.callback_query(F.data.startswith("calc:chip:"))
async def cb_calc_chip(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    amount = int(parts[3])
    await state.update_data(calc_pending=amount)
    d = await state.get_data()
    bets = d.get("calc_bets", [])
    mod = d.get("calc_mod", False)
    player_id = d.get("calc_player_id")

    mults, mod_mult, _ = await _get_game_multipliers(callback)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if game:
            game = await get_game_by_id(session, game.id)
            ids = [p.id for p in game.players]
            idx = ids.index(player_id) if player_id in ids else -1
            prv = ids[idx - 1] if idx > 0 else 0
            nxt = ids[idx + 1] if 0 <= idx < len(ids) - 1 else 0
        else:
            prv = nxt = 0

    await callback.message.edit_text(
        callback.message.html_text + f"\n\n▸ <b>{amount}♟</b> — [❌] [{'/'.join(f'×{m}' for m in mults)}]",
        reply_markup=_player_calc_kb(player_id, mod, len(bets) > 0, mults, mod_mult, prv, nxt),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("calc:mult:"))
async def cb_calc_mult(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    mult = int(parts[3])
    d = await state.get_data()
    amount = d.get("calc_pending", 0)
    bets = list(d.get("calc_bets", []))
    bets.append({"amount": amount, "mult": mult})
    await state.update_data(calc_bets=bets, calc_pending=0)
    await _render(callback, state)

    label = "❌" if mult == 0 else f"×{mult}"
    await callback.answer(f"{amount}♟ {label}")


@router.callback_query(F.data.startswith("calc:undo:"))
async def cb_calc_undo(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    bets = list(d.get("calc_bets", []))
    if bets:
        bets.pop()
        await state.update_data(calc_bets=bets)
    await _render(callback, state)
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("calc:save:"))
async def cb_calc_save(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    player_id = d.get("calc_player_id")
    bets = d.get("calc_bets", [])
    mod = d.get("calc_mod", False)

    if not bets:
        await callback.answer("Нет ставок для сохранения", show_alert=True)
        return

    _, mod_mult, _ = await _get_game_multipliers(callback)
    rt = _round_total(bets, mod, mod_mult)

    async with async_session() as session:
        game = await get_active_game_for_host(session, callback.from_user.id)
        if not game:
            await callback.answer("Нет игры", show_alert=True)
            return
        game = await get_game_by_id(session, game.id)
        player = next((p for p in game.players if p.id == player_id), None)
        if not player:
            await callback.answer("Игрок не найден", show_alert=True)
            return

        player.total_score += rt
        await session.commit()
        name = player.display_name
        new_balance = player.total_score

    await state.update_data(calc_bets=[], calc_mod=False)
    await _render(callback, state)
    await callback.answer(f"{name}: {rt:+d}♟ → {new_balance}♟")
