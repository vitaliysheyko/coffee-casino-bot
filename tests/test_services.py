import pytest
from bot.services.games import (
    sanitize_lot_data,
    get_or_create_user,
    format_players_list,
    generate_game_code,
    create_game,
    add_player_to_game,
    get_active_game_for_host,
)
from bot.services.lots import (
    create_lot,
    update_lot,
    get_user_lots,
    get_lot_by_id,
    delete_lot,
)
from bot.models import User, Game


class TestSanitizeLotData:
    def test_allows_known_fields(self):
        data = {
            "title": "Эфиопия Гуджи",
            "country": "Эфиопия",
            "region": "Гуджи",
            "altitude": "2100-2300",
            "process": "мытая",
            "variety": "Heirloom",
            "score": "88",
            "roast_level": "светлая",
            "roast_date": "2024-01-15",
            "fact": "Интересный факт",
            "notes": "Заметки",
        }
        result = sanitize_lot_data(data)
        assert result == data

    def test_filters_unknown_keys(self):
        data = {
            "title": "Тест",
            "country": "Колумбия",
            "owner_id": 99999,
            "id": 123,
            "malicious": "DROP TABLE users",
            "__class__": "hack",
        }
        result = sanitize_lot_data(data)
        assert result == {"title": "Тест", "country": "Колумбия"}
        assert "owner_id" not in result
        assert "id" not in result
        assert "malicious" not in result

    def test_empty_dict(self):
        assert sanitize_lot_data({}) == {}


class TestFormatPlayersList:
    def test_empty_players(self):
        game = Game()
        game.players = []
        assert format_players_list(game) == "Пока никого нет"

    def test_players_without_bets(self):
        user = User(id=1, full_name="Alice", username="alice")
        from bot.models import GamePlayer
        game = Game()
        game.players = [GamePlayer(user=user, has_bet=False)]
        result = format_players_list(game)
        assert "Alice" in result
        assert "✓" not in result

    def test_players_with_bets(self):
        user = User(id=2, full_name="Bob", username="bob")
        from bot.models import GamePlayer
        game = Game()
        game.players = [GamePlayer(user=user, has_bet=True)]
        result = format_players_list(game)
        assert "Bob" in result
        assert "✓" in result


class TestGenerateGameCode:
    def test_default_length(self):
        code = generate_game_code()
        assert len(code) == 4
        assert code.isalnum()
        assert code == code.upper()

    def test_custom_length(self):
        code = generate_game_code(6)
        assert len(code) == 6

    def test_randomness(self):
        codes = {generate_game_code() for _ in range(100)}
        assert len(codes) > 50  # very unlikely to have 50 duplicates out of 36^4 possibilities


@pytest.mark.asyncio
class TestGetOrCreateUser:
    async def test_creates_new_user(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        assert user is not None
        assert user.id == tg_user.id
        assert user.full_name == tg_user.full_name
        assert user.username == tg_user.username

    async def test_returns_existing_user(self, session, tg_user):
        user1 = await get_or_create_user(session, tg_user)
        user2 = await get_or_create_user(session, tg_user)
        assert user1.id == user2.id

    async def test_updates_name_on_change(self, session, tg_user):
        user1 = await get_or_create_user(session, tg_user)
        tg_user.full_name = "New Name"
        user2 = await get_or_create_user(session, tg_user)
        assert user2.full_name == "New Name"
        assert user1.id == user2.id

    async def test_handles_none_full_name(self, session):
        class NoNameUser:
            id = 999
            full_name = None
            username = "noname"
        user = await get_or_create_user(session, NoNameUser())
        assert user.full_name == "Без имени"


@pytest.mark.asyncio
class TestLotCRUD:
    async def test_create_and_get_lot(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "Тестовый лот", "country": "Бразилия"})
        assert lot.id is not None
        assert lot.title == "Тестовый лот"
        assert lot.country == "Бразилия"

        found = await get_lot_by_id(session, lot.id, 1)
        assert found is not None
        assert found.title == "Тестовый лот"

    async def test_get_lot_wrong_owner(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "Мой лот"})
        found = await get_lot_by_id(session, lot.id, 2)
        assert found is None

    async def test_get_user_lots(self, session):
        await create_lot(session, owner_id=1, data={"title": "Лот 1"})
        await create_lot(session, owner_id=1, data={"title": "Лот 2"})
        await create_lot(session, owner_id=2, data={"title": "Лот 3"})

        lots = await get_user_lots(session, 1)
        assert len(lots) == 2

    async def test_update_lot(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "До обновления"})
        updated = await update_lot(session, lot, {"title": "После обновления", "country": "Кения"})
        assert updated.title == "После обновления"
        assert updated.country == "Кения"

    async def test_update_lot_filters_unknown(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "Оригинал"})
        updated = await update_lot(session, lot, {"title": "Новое", "owner_id": 99999, "id": 12345})
        assert updated.title == "Новое"
        assert updated.owner_id == 1

    async def test_delete_lot(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "Удаляемый"})
        await delete_lot(session, lot)
        found = await get_lot_by_id(session, lot.id, 1)
        assert found is None


@pytest.mark.asyncio
class TestGameCRUD:
    async def test_create_game(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        assert game.id is not None
        assert game.code is not None
        assert len(game.code) == 4
        assert game.status == "waiting"

    async def test_add_player(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        player = await add_player_to_game(session, game, user)
        assert player.game_id == game.id
        assert player.user_id == user.id

    async def test_add_player_twice_no_duplicate(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        p1 = await add_player_to_game(session, game, user)
        p2 = await add_player_to_game(session, game, user)
        assert p1.id == p2.id

    async def test_get_active_game(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        active = await get_active_game_for_host(session, user.id)
        assert active is not None
        assert active.id == game.id
