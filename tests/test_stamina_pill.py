"""回體丹（企劃者 2026-10-07「新增物品回體丹可以回體力100點，新手進來都送20顆，現在是內測期間，讓大家初期可以盡情遊玩體驗」）。"""
import random

from fastapi.testclient import TestClient

import server
from conftest import next_season
from tianxia import bot, skillview
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def test_a_new_character_gets_the_beta_gift(game):
    assert game.state.player.stamina_pills == game.content.config.beta_gift_stamina_pills == 20


def test_the_gift_can_be_switched_off(content):
    content.config.beta_gift = False
    assert Game.new(content, "沈浪", rng=random.Random(0)).state.player.stamina_pills == 0


def test_bots_get_the_same_gift_as_people(content):
    """假人與整季機器人走 graduated：跟真人一樣拿到（不能從丹看出誰是假人）。"""
    assert Game.new(content, "假人", rng=random.Random(0), graduated=True).state.player.stamina_pills == 20


def test_a_pill_restores_a_hundred_and_never_overflows(game):
    p, cap = game.state.player, game.content.config.stamina_max
    p.stamina = 10.0
    msgs = game.take_stamina_pill()
    assert p.stamina == 110 and p.stamina_pills == 19
    assert msgs[-1] == "體力 +100（回體丹還剩 19 顆）"
    entry = game.state.journal[0]
    assert entry.title == "服下回體丹" and entry.changes == ["體力 +100", "回體丹 -1"]
    msgs = game.take_stamina_pill()  # 110 → 150：夾在上限
    assert p.stamina == cap and p.stamina_pills == 18 and msgs[-1].startswith(f"體力 +{cap - 110}")


def test_refusals_cost_nothing(game):
    p = game.state.player
    p.stamina = float(game.content.config.stamina_max)
    assert game.take_stamina_pill() == ["體力是滿的，這時候服丹是糟蹋。"] and p.stamina_pills == 20
    p.stamina, p.stamina_pills = 0.0, 0
    assert game.take_stamina_pill() == ["你身上沒有回體丹了。"] and p.stamina == 0


def test_the_hut_keeps_its_own_stamina_plan(prologue_content):
    """草廬序章的體力是照步驟算好的（探索、合成、修練剛好用完，接著教打坐）：序章裡不能吃，狀態列也不畫鈕。"""
    game = Game.new(prologue_content, "沈浪", rng=random.Random(0), prologue=True)
    p = game.state.player
    assert p.stamina_pills == 20
    p.stamina = 0.0
    assert "出了草廬再吃" in game.take_stamina_pill()[0] and p.stamina == 0 and p.stamina_pills == 20
    assert game.status_data()["pills"] is None


def test_the_status_bar_offers_the_pill(game):
    p = game.state.player
    p.stamina = 40.0
    assert game.status_data()["pills"] == {"name": "回體丹", "count": 20, "restore": 100, "full": False}
    p.stamina = float(game.content.config.stamina_max)
    assert game.status_data()["pills"]["full"] is True
    p.stamina_pills = 0
    assert game.status_data()["pills"] is None


def test_the_bag_lists_the_pills(game):
    text = skillview.bag_text(game.state, game.content)
    assert "回體丹 ×20" in text and "服丹" in text


def test_pills_carry_into_the_next_season_without_a_second_gift(content):
    world = open_world()
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0), world=world)
    game.state.player.stamina_pills = 7
    next_season(content, world, game)
    assert game.state.player.stamina_pills == 7


def test_the_bot_takes_a_pill_only_when_stamina_runs_out(game):
    p = game.state.player
    p.stamina = float(bot.PILL_BELOW)
    bot.take_pill(game)
    assert p.stamina_pills == 20
    p.stamina = 0.0
    bot.take_pill(game)
    assert p.stamina_pills == 19 and p.stamina == 100


def test_the_web_button_takes_a_pill(monkeypatch):
    from tianxia.characters import open_characters  # noqa: PLC0415

    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    client = TestClient(server.app)
    client.post("/api/register", json={"login": "pill_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": "服丹人"})
    client.post("/api/do/skip_tutorial", json={})
    game = server.game_for("服丹人")
    game.state.player.stamina = 5.0
    open_characters().save(game.state)
    left = server.CONTENT.config.beta_gift_stamina_pills - 1
    r = client.post("/api/do/pill", json={}).json()
    assert r["main"]["status"]["pills"]["count"] == left, r["message"]
    saved = open_characters().load("服丹人").player
    assert saved.stamina_pills == left and saved.stamina >= 105


# ── 拿掉一鍵補滿之後補回體丹（企劃者 2026-10-12；PlayerState.pills_topped_to）──

def _reload(game):
    return Game(game.content, game.state, random.Random(0), game.world)


def test_an_old_character_short_of_pills_is_topped_up_once(game):
    p = game.state.player
    p.stamina_pills, p.pills_topped_to = 5, 0  # 拿掉之前的舊角色：吃掉了大半
    again = _reload(game)
    n = game.content.config.beta_gift_stamina_pills
    assert again.state.player.stamina_pills == n and again.state.player.pills_topped_to == n
    entry = again.state.journal[0]
    assert entry.title == "回體丹" and entry.lines == [
        f"體力條上的「補滿」收起來了；補給你回體丹 {n - 5} 顆，手上一共 {n} 顆，一顆回 {game.content.config.stamina_pill_restore} 點體力，"
        "按體力條右端的「丹」服下。"]
    again.state.player.stamina_pills = 1
    assert _reload(again).state.player.stamina_pills == 1  # 一個數只補一次


def test_a_character_holding_enough_is_left_alone_but_marked(game):
    p = game.state.player
    p.stamina_pills, p.pills_topped_to = 50, 0
    entries = len(game.state.journal)
    again = _reload(game)
    assert again.state.player.stamina_pills == 50 and again.state.player.pills_topped_to == 20
    assert len(again.state.journal) == entries


def test_new_characters_are_not_topped_up_on_top_of_the_gift(game):
    assert game.state.player.pills_topped_to == 20 and game.state.player.stamina_pills == 20
    assert all(e.title != "回體丹" for e in game.state.journal)


def test_raising_the_gift_tops_up_again(game):
    game.state.player.stamina_pills = 3
    game.content.config.beta_gift_stamina_pills = 30
    assert _reload(game).state.player.stamina_pills == 30


def test_the_weekend_profile_no_longer_refills_for_free():
    from pathlib import Path

    from tianxia.content import load_content
    real = load_content(Path(__file__).parent.parent / "content", profile="weekend")
    assert real.config.beta_free_refill is False
