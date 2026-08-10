from __future__ import annotations

import pytest
from bot.services.games import (
    get_or_create_user,
    format_players_list,
    generate_game_code,
    create_game,
    add_player_to_game,
    get_active_game_for_host,
)
from bot.services.lots import (
    sanitize_lot_data,
    create_lot,
    update_lot,
    get_user_lots,
    get_lot_by_id,
    delete_lot,
)
from bot.services.scoring import (
    active_categories,
    calculate_round_score,
    build_leaderboard,
    apply_round_result,
    count_modifier_usage,
)
from bot.models import Lot, User, Game, GamePlayer, RoundResult


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
        }
        result = sanitize_lot_data(data)
        assert result == {"title": "Тест", "country": "Колумбия"}
        assert "owner_id" not in result

    def test_empty_dict(self):
        assert sanitize_lot_data({}) == {}


class TestFormatPlayersList:
    def test_empty_players(self):
        assert format_players_list([]) == "Пока никого нет"

    def test_players_with_scores(self):
        p = GamePlayer(display_name="Alice", total_score=3)
        result = format_players_list([p])
        assert "Alice" in result
        assert "3 фишек" in result


class TestGenerateGameCode:
    def test_default_length(self):
        code = generate_game_code()
        assert len(code) == 4
        assert code.isalnum()
        assert code == code.upper()

    def test_randomness(self):
        codes = {generate_game_code() for _ in range(100)}
        assert len(codes) > 50


@pytest.mark.asyncio
class TestGetOrCreateUser:
    async def test_creates_new_user(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        assert user.id == tg_user.id
        assert user.full_name == tg_user.full_name

    async def test_returns_existing_user(self, session, tg_user):
        user1 = await get_or_create_user(session, tg_user)
        user2 = await get_or_create_user(session, tg_user)
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
        lot = await create_lot(session, owner_id=1, data={"title": "Тест", "country": "Бразилия"})
        assert lot.title == "Тест"
        found = await get_lot_by_id(session, lot.id, 1)
        assert found is not None

    async def test_get_lot_wrong_owner(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "Мой лот"})
        found = await get_lot_by_id(session, lot.id, 2)
        assert found is None

    async def test_update_lot(self, session):
        lot = await create_lot(session, owner_id=1, data={"title": "До"})
        updated = await update_lot(session, lot, {"title": "После", "country": "Кения"})
        assert updated.title == "После"

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
        assert game.code is not None
        assert len(game.code) == 4
        assert game.status == "waiting"
        assert game.starting_chips == 5
        assert game.total_rounds == 6

    async def test_add_player(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        player = await add_player_to_game(session, game, user, "ТестИгрок")
        assert player.display_name == "ТестИгрок"
        assert player.total_score == game.starting_chips

    async def test_add_player_twice_no_duplicate(self, session, tg_user):
        user = await get_or_create_user(session, tg_user)
        game = await create_game(session, user.id)
        p1 = await add_player_to_game(session, game, user, "A")
        p2 = await add_player_to_game(session, game, user, "A")
        assert p1.id == p2.id


class TestScoring:
    def test_active_categories(self):
        lot = Lot(country="Бразилия", region=None, process="мытая", variety=None, roast_level=None, title="Тест")
        cats = active_categories(lot)
        assert cats == ["country", "process"]

    def test_no_categories(self):
        lot = Lot(country=None, region=None, process=None, variety=None, roast_level=None, title="Тест")
        assert active_categories(lot) == []

    def test_calculate_score_all_correct(self):
        results = {"country": True, "region": True, "process": True}
        cats = ["country", "region", "process"]
        correct, net, lost = calculate_round_score(results, cats)
        assert correct == 3
        assert net == 6  # 3 correct * 2 chips = 6 win
        assert lost == 0

    def test_calculate_score_mixed(self):
        results = {"country": True, "region": False, "process": True}
        cats = ["country", "region", "process"]
        correct, net, lost = calculate_round_score(results, cats)
        assert correct == 2
        assert net == 3  # (2*2) - 1 = 3
        assert lost == 1

    def test_calculate_score_all_wrong(self):
        results = {"country": False, "process": False}
        cats = ["country", "process"]
        correct, net, lost = calculate_round_score(results, cats)
        assert correct == 0
        assert net == -2
        assert lost == 2

    def test_build_leaderboard(self):
        p1 = GamePlayer(display_name="Alice", total_score=10)
        p2 = GamePlayer(display_name="Bob", total_score=5)
        p3 = GamePlayer(display_name="Charlie", total_score=15)
        board = build_leaderboard([p1, p2, p3])
        assert board[0]["name"] == "Charlie"
        assert board[0]["rank"] == 1
        assert board[2]["name"] == "Bob"
        assert board[2]["rank"] == 3


class TestModifierScoring:
    def test_calculate_score_with_modifier(self):
        results = {"country": True, "region": False, "process": True}
        cats = ["country", "region", "process"]
        correct, net, lost = calculate_round_score(results, cats, modifier_applied=True, modifier_multiplier=2)
        assert correct == 2
        assert net == 7  # (2 correct * 1 * 2 base) * 2 mod - 1 lost = 8 - 1 = 7
        assert lost == 1

    def test_apply_round_result_with_modifier(self):
        lot = Lot(title="Test", country="Brazil", process="natural")
        player = GamePlayer(display_name="Alice", total_score=10)
        rr = apply_round_result(
            player,
            lot,
            round_number=1,
            category_results={"country": True, "process": True},
            modifier_type="spoon",
            modifier_multiplier=2,
        )
        assert rr.modifier_applied is True
        assert rr.modifier_type == "spoon"
        # 2 correct * 1 * 2 base = 4, * 2 modifier = 8
        assert rr.chips_won == 8
        assert player.total_score == 18

    async def test_count_modifier_usage(self, session):
        user = User(id=1, full_name="Host")
        session.add(user)
        game = Game(code="TEST", host_id=1, status="finished")
        session.add(game)
        await session.commit()

        player = GamePlayer(game_id=game.id, display_name="Alice", total_score=10)
        session.add(player)
        lot = Lot(title="Test", owner_id=1)
        session.add(lot)
        await session.commit()

        rr1 = RoundResult(game_id=game.id, player_id=player.id, lot_id=lot.id, round_number=1, modifier_type="spoon", modifier_applied=True)
        rr2 = RoundResult(game_id=game.id, player_id=player.id, lot_id=lot.id, round_number=2, modifier_type="spoon", modifier_applied=True)
        rr3 = RoundResult(game_id=game.id, player_id=player.id, lot_id=lot.id, round_number=3, modifier_type="deer", modifier_applied=True)
        session.add_all([rr1, rr2, rr3])
        await session.commit()

        count = await count_modifier_usage(session, game.id, player.id, "spoon")
        assert count == 2

        deer_count = await count_modifier_usage(session, game.id, player.id, "deer")
        assert deer_count == 1

        sniffer_count = await count_modifier_usage(session, game.id, player.id, "sniffer")
        assert sniffer_count == 0
