"""本週卡第三行「你這一步」（減法季整合設計 6.1；計畫 Task 3c-3，欄位表 main.step；tianxia/step.py）。

來源照順序：託付（批 6，現在空的）→ 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠；一天換一次、「換一件事」（step:next）往下挑、
隔天從頭；step:next 不在選單上（假人碰不到）、不花體力、不寫江湖紀錄。減法季的規則關著沒有。正式內容、建 Game，整個檔標 slow。"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock

import pytest

from wins_kit import wins_content, wins_game
from tianxia import atlas, bot, newbie, orders, step, wins
from tianxia.state import Bounty, Order

pytestmark = pytest.mark.slow

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


def test_off_has_no_step():
    content = wins_content()
    content.config.jianfa.enabled = False
    game = wins_game(content, faction="guan", at="changshe")
    _order(game, start="changshe", end="wan_city")
    assert game.step_view() is None
    stamina = game.state.player.stamina
    assert game.choose(step.NEXT) == ["（此刻無法這麼做。）"]  # 關著的季照舊當成不在選單上
    p = game.state.player
    assert (p.step_day, p.step_skip, p.stamina) == (0, 0, stamina)
    off = wins_game(wins_content(off=True), name="乙客", faction="guan", at="changshe")  # 只關這一批的子開關也一樣
    _order(off, start="changshe", end="wan_city")
    assert off.step_view() is None and off.choose(step.NEXT) == ["（此刻無法這麼做。）"]


def test_order_comes_first_with_its_place():
    game = wins_game(faction="guan", at="changshe")
    o = _order(game, start="changshe", end="wan_city")
    _bounty(game)
    row = game.step_view()
    assert row["source"] == "order" and row["id"] == o.id
    assert row["text"] == step.ORDER_TEXT.format(title=orders.title(game.content, o))
    assert row["why"] == atlas.order_how(game.state, game.content, o)
    assert row["target"] == {"location": "changshe", "name": "長社", "minutes": 0}  # 護糧：還沒接糧車，去起點


def test_orders_not_yet_helped_come_first():
    game = wins_game(faction="guan", at="changshe")
    helped = _order(game, template="escort", start="changshe", end="wan_city")
    helped.progress[game.state.player.name] = 1
    fresh = _order(game, template="intercept", location="wan_city")
    assert [r["id"] for r in step.candidates(game) if r["source"] == "order"] == [fresh.id, helped.id]


def test_bounty_then_newbie_then_join():
    game = wins_game(at="changshe")  # 散人
    b = _bounty(game, kind="strike", location="wan_city")
    sources = [r["source"] for r in step.candidates(game)]
    assert sources[0] == "bounty" and step.candidates(game)[0]["id"] == b.id
    assert step.candidates(game)[0]["target"]["location"] == "wan_city" and step.candidates(game)[0]["target"]["minutes"] > 0
    assert sources.index("bounty") < sources.index("newbie") < sources.index("join")
    _quiet_newbie(game)
    game.state.world.bounties.clear()
    row = game.step_view()
    assert row["source"] == "join" and row["target"]["minutes"] == 0  # 長社本身就是官軍的投靠點
    assert row["text"] == step.JOIN_TEXT.format(place="長社", faction="官軍")
    game.state.player.newbie_marks.add(newbie.DRIFTER)  # 選了「就當散人」：不再催投靠
    assert game.step_view() is None


def test_errand_slot_is_first_and_foreshadow_sits_after_bounties():
    game = wins_game(faction="guan", at="changshe")
    _bounty(game)
    errand = {"text": "替盧植送信", "why": "託付", "source": "errand", "target": None}
    trip = SimpleNamespace(label="束苣乘城", location="changshe")
    chain = SimpleNamespace(id="fs1")
    with mock.patch.dict(step.FINDERS, {"errand": lambda g: [errand]}), \
            mock.patch("tianxia.foreshadow.next_trips", return_value=[(chain, trip)]):
        rows = step.candidates(game)
    assert rows[0] == errand
    assert [r["source"] for r in rows][:3] == ["errand", "bounty", "foreshadow"]
    assert rows[2]["text"] == "束苣乘城" and rows[2]["target"]["location"] == "changshe"


def test_step_next_cycles_and_resets_the_next_day():
    game = wins_game(faction="guan", at="changshe")
    _quiet_newbie(game)
    first = _order(game, start="changshe", end="wan_city")
    second = _bounty(game)
    game.now = 1_800_000_000.0
    assert game.step_view()["id"] == first.id and game.step_view()["left"] == 1
    journal, stamina = len(game.state.journal), game.state.player.stamina
    assert game.choose(step.NEXT) == []
    assert game.step_view()["id"] == second.id
    assert (len(game.state.journal), game.state.player.stamina) == (journal, stamina)  # 不寫紀錄、不花體力
    game.choose(step.NEXT)
    assert game.step_view()["id"] == first.id  # 排到底從頭
    game.now += DAY  # 隔天（台灣 00:00 換日）：從頭
    assert game.step_view()["id"] == first.id
    game.choose(step.NEXT)
    p = game.state.player
    assert p.step_skip == 1 and p.step_day == game._pill_day()


def test_step_next_with_nothing_to_switch_records_nothing():
    game = wins_game(faction="guan", at="changshe")
    _quiet_newbie(game)
    _order(game, start="changshe", end="wan_city")
    game.choose(step.NEXT)
    assert (game.state.player.step_day, game.state.player.step_skip) == (0, 0)


def test_step_next_is_not_on_the_menu():
    game = wins_game(faction="guan", at="changshe")
    _order(game, start="changshe", end="wan_city")
    _bounty(game)
    menu = game.options()
    assert step.NEXT not in [o.id for o in menu]
    for seed in range(20):
        import random

        assert bot.pick(game, menu, random.Random(seed)) != step.NEXT


def test_new_fields_add_no_keys_until_used():
    game = wins_game(faction="guan", at="changshe")
    data = json.loads(game.state.model_dump_json())["player"]
    assert not {"step_day", "step_skip", "season_title"} & set(data)
    p = game.state.player
    p.step_day, p.step_skip, p.season_title = 20000, 2, "隨軍"
    data = json.loads(game.state.model_dump_json())["player"]
    assert (data["step_day"], data["step_skip"], data["season_title"]) == (20000, 2, "隨軍")


def test_ended_season_has_no_step():
    game = wins_game(faction="guan", at="changshe")
    _order(game, start="changshe", end="wan_city")
    game.state.world.ended = True
    assert game.step_view() is None and wins.on(game.content, game.state.world)
