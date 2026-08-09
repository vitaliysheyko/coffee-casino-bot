import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from aiogram.types import Chat, Message, CallbackQuery, User
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from bot.database import async_session
from bot.handlers.game.setup import cb_game_create
from bot.handlers.game.round import cb_start_game, cb_start_round, cb_select_lot, cb_reveal
from bot.handlers.game.scoring import cb_score_round
from bot.handlers.game.controls import cb_finish_game
from bot.handlers.start import cmd_start, cb_quick_game
from bot.services.games import get_or_create_user, create_game
from bot.services.lots import create_lot


@asynccontextmanager
async def patch_session(session):
    with patch("bot.handlers.start.async_session") as mock_start:
        mock_start.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_start.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("bot.handlers.game.setup.async_session") as mock_setup, \
             patch("bot.handlers.game.round.async_session") as mock_round, \
             patch("bot.handlers.game.scoring.async_session") as mock_scoring, \
             patch("bot.handlers.game.controls.async_session") as mock_controls, \
             patch("bot.handlers.game.players.async_session") as mock_players:
            for m in [mock_setup, mock_round, mock_scoring, mock_controls, mock_players]:
                m.return_value.__aenter__ = AsyncMock(return_value=session)
                m.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("bot.handlers.lots.async_session") as mock_lots:
                mock_lots.return_value.__aenter__ = AsyncMock(return_value=session)
                mock_lots.return_value.__aexit__ = AsyncMock(return_value=False)
                yield


def make_user(user_id: int = 111, full_name: str = "Host", username: str = "host") -> User:
    return User(id=user_id, is_bot=False, first_name=full_name.split()[0], username=username)


def make_message(text: str = "", user_id: int = 111) -> Message:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = make_user(user_id)
    msg.chat = Chat(id=user_id, type="private")
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_message = AsyncMock()
    return msg


def make_callback(data: str = "", user_id: int = 111) -> CallbackQuery:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = make_user(user_id)
    cb.message = make_message(user_id=user_id)
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.bot = MagicMock()
    cb.message.bot.send_message = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = cb.message.bot
    return cb


def make_state() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key="test")


@pytest.mark.asyncio
async def test_cmd_start(session):
    async with patch_session(session):
        user = make_user()
        msg = make_message("/start", user.id)
        msg.from_user = user

        await cmd_start(msg, make_state())

        assert msg.answer.called
        text = msg.answer.call_args[0][0]
        assert "Кофейное казино" in text
        assert "помощник ведущего" in text


@pytest.mark.asyncio
async def test_quick_game_creates_game(session, tg_user):
    async with patch_session(session):
        cb = make_callback("quick_game", tg_user.id)
        state = make_state()

        await cb_quick_game(cb, state)

        assert cb.message.edit_text.called
        text = cb.message.edit_text.call_args[0][0]
        assert "Быстрая игра" in text or "настроена" in text


@pytest.mark.asyncio
async def test_game_create_flow(session, tg_user):
    user = await get_or_create_user(session, tg_user)
    await create_lot(session, user.id, {"title": "Test Lot", "country": "Ethiopia"})
    
    async with patch_session(session):
        cb = make_callback("game:create", tg_user.id)
        state = make_state()

        await cb_game_create(cb, state)

        assert cb.message.edit_text.called
        text = cb.message.edit_text.call_args[0][0]
        assert "Новая игра" in text
        assert "Сколько раундов" in text


@pytest.mark.asyncio
async def test_start_game_requires_players(session, tg_user):
    user = await get_or_create_user(session, tg_user)
    game = await create_game(session, user.id, total_rounds=2, starting_chips=5)

    async with patch_session(session):
        cb = make_callback("game:start_game", user.id)
        state = make_state()

        await cb_start_game(cb, state)

        assert cb.answer.called
        assert cb.answer.call_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_reveal_transitions_to_scoring(session, tg_user):
    user = await get_or_create_user(session, tg_user)
    lot = await create_lot(session, user.id, {
        "title": "Эфиопия",
        "country": "Эфиопия",
        "process": "мытая",
    })
    game = await create_game(session, user.id, total_rounds=1, starting_chips=5)
    game.status = "round_active"
    game.current_lot_id = lot.id
    game.current_round = 1
    from bot.models import GamePlayer
    player = GamePlayer(game_id=game.id, user_id=999, display_name="Алексей", total_score=5)
    session.add(player)
    await session.commit()

    async with patch_session(session):
        cb = make_callback("game:reveal", user.id)
        state = make_state()
        await cb_reveal(cb, state)

        assert cb.message.edit_text.called
        text = cb.message.edit_text.call_args[0][0]
        assert "Ревел" in text
        assert "Эфиопия" in text


@pytest.mark.asyncio
async def test_score_round_shows_player_categories(session, tg_user):
    user = await get_or_create_user(session, tg_user)
    lot = await create_lot(session, user.id, {
        "title": "Эфиопия",
        "country": "Эфиопия",
        "process": "мытая",
    })
    game = await create_game(session, user.id, total_rounds=1, starting_chips=5)
    game.status = "reveal"
    game.current_lot_id = lot.id
    game.current_round = 1
    from bot.models import GamePlayer
    player = GamePlayer(game_id=game.id, user_id=999, display_name="Алексей", total_score=5)
    session.add(player)
    await session.commit()

    async with patch_session(session):
        cb = make_callback("game:score_round", user.id)
        state = make_state()
        await cb_score_round(cb, state)

        assert cb.message.edit_text.called
        text = cb.message.edit_text.call_args[0][0]
        assert "Алексей" in text
        reply_markup = cb.message.edit_text.call_args[1].get("reply_markup")
        assert reply_markup is not None
        buttons = reply_markup.inline_keyboard
        texts = [btn.text for row in buttons for btn in row]
        assert any("Страна" in t for t in texts)
        assert any("Обработка" in t for t in texts)


@pytest.mark.asyncio
async def test_finish_game_shows_winner(session, tg_user):
    user = await get_or_create_user(session, tg_user)
    game = await create_game(session, user.id, total_rounds=1, starting_chips=5)
    from bot.models import GamePlayer
    player = GamePlayer(game_id=game.id, user_id=999, display_name="Алексей", total_score=12)
    session.add(player)
    await session.commit()
    game.status = "reveal"
    await session.commit()

    async with patch_session(session):
        cb = make_callback("game:finish_game", user.id)
        state = make_state()
        await cb_finish_game(cb)

        assert cb.message.edit_text.called
        text = cb.message.edit_text.call_args[0][0]
        assert "Победитель" in text
        assert "Алексей" in text
        assert "12 фишек" in text or "12" in text
