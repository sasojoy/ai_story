"""本週卡「你這一步」的批 3c 那一半（減法季整合設計 6.1；計畫 Task 3c-3；tianxia/step.py）。

畫面只有一份「你這一步」：批 1 的 main.week_card.steps（weekcard._steps 排：託付 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠）。
四勝利開著的季，step.finish 替每一件補 target（地點、名字、走過去的現實分鐘）與 id，並照「換一件事」（step:next）今天按了幾次從那一件
排起、隔天從頭；step:next 不在選單上（假人碰不到）、不花體力、不寫江湖紀錄。關著的季 steps 一個字都不變。正式內容、建 Game（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

import json
import random
from types import SimpleNamespace
from unittest import mock


import server
from wins_kit import wins_content, wins_game
from tianxia import bot, newbie, orders, step, weekcard
from tianxia.state import Bounty, Order

DAY = 86400


def _order(game, template="escort", **fields) -> Order:
    s, c = game.state, game.content
    o = Order(id=f"o-{template}", template=template, faction=fields.pop("faction", "guan"), week=orders.period_of(s, c), quota=3,
              text="（軍令）", **fields)
    s.world.orders.append(o)
    return o


def _bounty(game, kind="scout", location="wan_city", **fields) -> Bounty:
    w = game.state.world
    b = Bounty(id=f"b-{kind}", kind=kind, faction=fields.pop("faction", "guan"), week=1, expires=w.time + 10 * DAY, silver=10,
               deeds=1, location=location, takers=[game.state.player.name], **fields)
    w.bounties.append(b)
    return b


def _quiet_newbie(game):
    game.state.player.newbie_done = {g.key for g in newbie.GOALS}  # 新手目標都拿過了：不排進來


def _steps(game) -> list[dict]:
    return server.main_view(game)["week_card"]["steps"]


def test_off_steps_stay_as_batch_one_wrote_them():
    """four_wins 關著（總開關或子開關）：steps 只有批 1 的 kind、text、reward（新手目標多 i），沒有 target、id、_ref；step:next 照舊不在選單上。"""
    master_off = wins_content()
    master_off.config.jianfa.enabled = False
    for content in (wins_content(off=True), master_off):
        game = wins_game(content, faction="guan", at="changshe")
        _order(game, start="changshe", end="wan_city")
        rows = _steps(game)
        assert rows and all(set(row) <= {"kind", "text", "who", "i", "reward"} for row in rows)
        stamina = game.state.player.stamina
        assert game.choose(step.NEXT) == ["（此刻無法這麼做。）"]
        p = game.state.player
        assert (p.step_day, p.step_skip, p.stamina) == (0, 0, stamina)


def test_one_weekly_step_in_the_view():
    game = wins_game(faction="guan", at="changshe")
    view = server.main_view(game)
    assert "step" not in view and "sides" not in view and view["week_card"]["steps"]  # 只有批 1 那一份


def test_order_step_gets_its_place():
    game = wins_game(faction="guan", at="changshe")
    o = _order(game, start="changshe", end="wan_city")
    row = next(r for r in _steps(game) if r["kind"] == "order")
    assert row["id"] == o.id
    assert row["target"] == {"location": "changshe", "name": "長社", "minutes": 0}  # 護糧：還沒接糧車，去起點
    assert row["then"] == {"location": "wan_city", "name": game.content.locations["wan_city"].name}  # 輿圖兩點都框進來
    assert "_ref" not in row


def test_bounty_newbie_and_join_get_their_places():
    game = wins_game(at="changshe")  # 散人
    b = _bounty(game, kind="strike", location="wan_city")
    rows = _steps(game)
    kinds = [r["kind"] for r in rows]
    assert kinds.index("bounty") < kinds.index("newbie") < kinds.index("join")
    bounty = next(r for r in rows if r["kind"] == "bounty")
    assert bounty["id"] == b.id and bounty["target"]["location"] == "wan_city" and bounty["target"]["minutes"] > 0
    join = next(r for r in rows if r["kind"] == "join")
    assert join["id"] == "guan" and join["target"] == {"location": "changshe", "name": "長社", "minutes": 0}  # 長社就是官軍的投靠點
    newbie_rows = [r for r in rows if r["kind"] == "newbie"]
    assert newbie_rows and all("target" in r and "id" in r for r in newbie_rows)
    level5 = next(r for r in newbie_rows if r["id"] == "level5")
    assert level5["target"] is not None and level5["target"]["minutes"] > 0  # 「去做」帶去最近的練功點


def test_errand_and_foreshadow_get_their_places():
    game = wins_game(faction="guan", at="changshe")
    b = _bounty(game, kind="scout", location="wan_city")
    status = game.status_data()
    status["bounties"] = [{"title": "託付", "how": "送信", "commission": True, "issuer": "某人", "id": b.id}]
    trip = SimpleNamespace(label="束苣乘城", location="changshe")
    with mock.patch("tianxia.foreshadow.next_trip", return_value=(SimpleNamespace(id="fs1"), trip)):
        rows = weekcard.week_card(game, status, [])["steps"]
    assert rows[0]["kind"] == "errand" and rows[0]["id"] == b.id and rows[0]["target"]["location"] == "wan_city"
    fs = next(r for r in rows if r["kind"] == "foreshadow")
    assert fs["text"] == "到長社：束苣乘城" and fs["id"] == "fs1" and fs["target"]["minutes"] == 0


def test_step_next_rotates_and_resets_the_next_day():
    game = wins_game(faction="guan", at="changshe")
    _quiet_newbie(game)
    first = _order(game, start="changshe", end="wan_city")
    second = _bounty(game)
    game.now = 1_800_000_000.0
    assert [r.get("id") for r in _steps(game)] == [first.id, second.id]
    journal, stamina = len(game.state.journal), game.state.player.stamina
    assert game.choose(step.NEXT) == []
    assert [r.get("id") for r in _steps(game)] == [second.id, first.id]  # 從下一件排起
    assert (len(game.state.journal), game.state.player.stamina) == (journal, stamina)  # 不寫紀錄、不花體力
    game.choose(step.NEXT)
    assert [r.get("id") for r in _steps(game)] == [first.id, second.id]  # 轉一圈回來
    game.now += DAY  # 隔天（台灣 00:00 換日）：從頭
    assert _steps(game)[0]["id"] == first.id
    game.choose(step.NEXT)
    p = game.state.player
    assert p.step_skip == 1 and p.step_day == game._pill_day()


def test_step_next_is_not_on_the_menu():
    game = wins_game(faction="guan", at="changshe")
    _order(game, start="changshe", end="wan_city")
    _bounty(game)
    menu = game.options()
    assert step.NEXT not in [o.id for o in menu]
    for seed in range(20):
        assert bot.pick(game, menu, random.Random(seed)) != step.NEXT


def test_new_fields_add_no_keys_until_used():
    game = wins_game(faction="guan", at="changshe")
    data = json.loads(game.state.model_dump_json())["player"]
    assert not {"step_day", "step_skip", "season_title"} & set(data)
    p = game.state.player
    p.step_day, p.step_skip, p.season_title = 20000, 2, "隨軍"
    data = json.loads(game.state.model_dump_json())["player"]
    assert (data["step_day"], data["step_skip"], data["season_title"]) == (20000, 2, "隨軍")


def test_ended_season_turns_it_off():
    game = wins_game(faction="guan", at="changshe")
    game.state.world.ended = True
    assert not step.on(game)
    assert step.finish(game, [{"kind": "join", "text": "x", step.REF: ("join",)}]) == [{"kind": "join", "text": "x"}]
