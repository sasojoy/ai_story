"""玩家傳第一批：行狀（tianxia/annals.py）、存進資料庫第 5 版的 biographies、見聞的「行狀」頁。"""
from __future__ import annotations

import json
import random
import sqlite3

import pytest

import webharness
from conftest import next_season
from tianxia import annals, battle_instance
from tianxia.database import SCHEMA, SCHEMA_V5_TABLES, SCHEMA_V6_TABLES, SCHEMA_V7_TABLES, SCHEMA_VERSION, open_database
from tianxia.engine import Game
from tianxia.state import AnnalEntry


@pytest.fixture
def on(content):
    content.config.biography.enabled = True
    return content


def _game(content, world, name="沈浪"):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    return game


def test_the_switch_is_on_in_the_real_config_and_off_in_the_test_content(content):
    from conftest import real_content

    assert real_content().config.biography.enabled is True
    assert content.config.biography.enabled is False


def test_nothing_is_written_while_the_switch_is_off(content, world):
    game = _game(content, world)
    annals.note(game.state, content, annals.DEED, "不該記。", 5)
    game.state.player.sect = "cloud"
    game.sync(1.0)
    assert game.state.player.annals == [] and game.state.player.annals_mark is None


def test_the_first_look_only_remembers_and_later_changes_are_written(on, world):
    game = _game(on, world)
    p = game.state.player
    assert p.annals == [] and p.annals_mark is not None  # 第一次只記下來，不補以前的事
    p.sect = "cloud"
    p.member.level = 10
    p.affinities["mate"] = 45
    game.sync(1.0)
    texts = [e.text for e in p.annals]
    assert "拜入流雲派門下。" in texts
    assert "武藝精進，到了第 5 級。" in texts and "武藝精進，到了第 10 級。" in texts
    assert [e.text for e in p.annals if e.figure == "mate"] == [f"跟{on.characters['mate'].name}的情誼到了 40。"]
    game.sync(2.0)
    assert len(p.annals) == len(texts)  # 沒變就不再記


def test_a_big_drop_and_a_new_companion_are_written_under_the_figure(on, world):
    game = _game(on, world)
    p = game.state.player
    p.affinities["mate"] = 30
    game.sync(1.0)
    p.affinities["mate"] = 15
    p.team = ["pupil"]
    game.sync(2.0)
    name = on.characters["mate"].name
    assert any(e.text == f"跟{name}的情誼一下子冷了 15。" and e.weight == 3 for e in p.annals)
    assert any(e.figure == "pupil" and "願意跟你同行" in e.text and e.weight == 4 for e in p.annals)


def test_the_cap_drops_the_lightest_and_oldest_first(on, state):
    on.config.biography.cap = 10
    for i in range(12):
        state.world.time = float(i)
        annals.note(state, on, annals.DEED, f"第{i}件", 1 if i < 6 else 3)
    texts = [e.text for e in state.player.annals]
    assert len(texts) == 10 and "第0件" not in texts and "第1件" not in texts and "第2件" in texts


def test_note_clips_long_text_and_stamps_place_and_time(on, state):
    annals.note(state, on, annals.FIGURE, "長" * 120, 9, quote="說" * 50, figure="mate")
    e = state.player.annals[0]
    assert len(e.text) == annals.TEXT_MAX and e.text.endswith("…") and len(e.quote) == annals.QUOTE_MAX
    assert e.weight == 5 and e.place == on.locations[state.player.location].name and e.when


def test_saying_your_own_words_is_written_with_the_reply(on, world):
    game = _game(on, world)
    p = game.state.player
    p.dialogue_history["mate"] = [{"role": "user", "content": "久仰大名"}, {"role": "assistant", "content": "韓某不敢當。你從哪裡來？"}]
    game._annal_talk("mate", 6, "久仰大名")
    e = p.annals[-1]
    assert (e.figure, e.quote, e.reply, e.weight) == ("mate", "久仰大名", "韓某不敢當。你從哪裡來？", 3)
    game._annal_talk("mate", 1, None)  # 挑選項、情誼動得少：不記
    assert len(p.annals) == 1
    game._annal_talk("mate", -7, None)
    assert p.annals[-1].text.endswith("話不投機，情誼 -7。") and p.annals[-1].quote == "久仰大名"


def test_a_showdown_writes_the_side_the_role_the_merit_and_each_gamble(on, world):
    game = _game(on, world)
    me = battle_instance.BattleParticipant(name="沈浪", faction="guan", neili=10, neili_cap=10, acted_rounds=4, led_rounds=2)
    me.gambles.append(battle_instance.GambleMoment(
        name="沈浪", faction="guan", text="點火燒糧", story="沈浪一把火燒了糧車", rate=20, won=True, target="張三"))
    battle = battle_instance.BattleInstance(battle_id="xx", participants={"沈浪": me}, outcome_title="官軍大勝", outcome_side="guan")
    game._annal_showdown(battle, me, "長社火攻", "官軍", "先鋒", 1, 1, None, 5.0)
    main, gamble = game.state.player.annals[-2:]
    assert main.text == "長社火攻，你站在官軍以先鋒出陣，出手 4 回合，帶頭佔了 2 回合上風，是這一邊的首功，結果官軍大勝。"
    assert main.weight == 5 and main.kind == annals.SHOWDOWN
    assert (gamble.quote, gamble.reply, gamble.weight) == ("點火燒糧", "沈浪一把火燒了糧車", 4)
    assert gamble.text == "在長社火攻陣上放手一搏，成了，點名張三。"


def test_gambles_are_kept_on_the_participant_when_a_round_resolves(content):
    instance = battle_instance.BattleInstance(battle_id="b")
    me = battle_instance.BattleParticipant(name="甲", faction="a", neili=100, neili_cap=100)
    assert me.gambles == [] and battle_instance.GAMBLES_KEPT >= 3
    me.gambles.append(battle_instance.GambleMoment(name="甲", faction="a", text="x", rate=1, won=False))
    instance.participants["甲"] = me
    again = battle_instance.BattleInstance.model_validate(json.loads(instance.model_dump_json()))
    assert again.participants["甲"].gambles[0].target == ""


def test_a_new_season_saves_the_old_annals_and_starts_empty(on, world):
    game = _game(on, world)
    annals.note(game.state, on, annals.DEED, "上一季的事。", 4)
    next_season(on, world, game)
    assert game.state.player.annals == []
    saved = world.biography(1, "沈浪")
    assert [e["text"] for e in saved["annals"]] == ["上一季的事。"] and saved["text"] is None and saved["public"] is False
    assert saved["profile"]["name"] == "沈浪" and saved["profile"]["level"] >= 1
    world.add_saved_annal(1, "沈浪", AnnalEntry(kind="showdown", time=1, when="第1天", text="補上的決戰。").model_dump())
    assert [e["text"] for e in world.biography(1, "沈浪")["annals"]][-1] == "補上的決戰。"
    assert [b["season"] for b in world.biographies_of("沈浪")] == [1]
    world.add_saved_annal(9, "沈浪", {"text": "沒有那一季"})  # 那一季沒存過：不記
    assert world.biography(9, "沈浪") is None


def test_saving_again_replaces_the_annals_until_the_biography_is_written(world):
    world.save_annals(1, "沈浪", [{"text": "甲"}], {})
    world.save_annals(1, "沈浪", [{"text": "乙"}], {})
    assert world.biography(1, "沈浪")["annals"] == [{"text": "乙"}]
    with world.db.transaction() as conn:
        conn.execute("UPDATE biographies SET text = '寫好了' WHERE season = 1")
    world.save_annals(1, "沈浪", [{"text": "丙"}], {})
    assert world.biography(1, "沈浪")["annals"] == [{"text": "乙"}]


def test_a_version_four_file_upgrades_to_five_with_an_empty_biographies_table(tmp_path):
    path = tmp_path / "v4.db"
    conn = sqlite3.connect(path)
    for sql in SCHEMA[: len(SCHEMA) - len(SCHEMA_V5_TABLES) - len(SCHEMA_V6_TABLES) - len(SCHEMA_V7_TABLES)]:  # 第 6 版（商城）、第 7 版（真人量表）接在第 5 版後面
        conn.execute(sql)
    conn.execute("PRAGMA user_version = 4")
    conn.execute("INSERT INTO chronicle (season, time, location, text) VALUES (1, 0, NULL, '舊的江湖史')")
    conn.commit()
    conn.close()
    db = open_database(path)
    with db.snapshot() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 7  # 一路升到第 7 版（商城 6、真人量表 7）
        assert c.execute("SELECT COUNT(*) FROM biographies").fetchone()[0] == 0
        assert c.execute("SELECT text FROM chronicle").fetchone()[0] == "舊的江湖史"


def test_the_view_lists_rows_in_time_order_with_figure_names(on, world):
    game = _game(on, world)
    s = game.state
    s.world.time = 9.0
    annals.note(s, on, annals.FIGURE, "後來的事。", 2, figure="mate", quote="你好", reply="好")
    s.world.time = 3.0
    annals.note(s, on, annals.DEED, "先前的事。", 4)
    view = game.annals_view()
    assert view["on"] is True and view["name"] == "沈浪"
    assert [r["text"] for r in view["rows"]] == ["先前的事。", "後來的事。"]
    assert view["rows"][1]["figure"] == on.characters["mate"].name and view["rows"][1]["kind"] == "人物"


# ── 見聞的「行狀」頁（web/app.js 的 annalsHtml）──

DRIVER = r"""
const parts = [konst("esc"), fn("annalsHtml"), "return { annalsHtml };"];
const H = new Function(parts.join("\n"))();
finish(H.annalsHtml(input.a));
"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_annals_page_lists_newest_first_and_escapes_everything():
    rows = [
        {"kind": "行事", "when": "第1天 08:00", "place": "潁川", "figure": "", "text": "先", "quote": "", "reply": "", "weight": 4},
        {"kind": "人物", "when": "第2天 09:00", "place": "", "figure": "韓<鐵>", "text": "後", "quote": "<b>", "reply": "好", "weight": 2},
    ]
    html = webharness.run(DRIVER, {"a": {"on": True, "name": "沈浪", "rows": rows}})
    assert html.index(">後<") < html.index(">先<")  # 新的在上
    assert "&lt;b&gt;" in html and "韓&lt;鐵&gt;" in html and "<b>" not in html.replace("<b>韓", "")
    assert html.count('class="annal heavy"') == 1 and "《沈浪傳》" in html
    empty = webharness.run(DRIVER, {"a": {"on": True, "name": "沈浪", "rows": []}})
    assert "還沒有記下什麼" in empty
    off = webharness.run(DRIVER, {"a": {"on": False, "name": "沈浪", "rows": []}})
    assert "不記行狀" in off


def test_the_news_tabs_include_the_annals_and_the_server_serves_them():
    from pathlib import Path

    src = webharness.app_source()
    assert '{ id: "annals", name: "行狀" }' in src and 'api("/api/annals")' in src
    server = (Path(__file__).parents[2] / "server.py").read_text(encoding="utf-8")
    assert '@app.get("/api/annals")' in server
