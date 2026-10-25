"""打開領地爭奪（企劃者 2026-10-22「領地爭奪……要打開」；計畫 docs/superpowers/plans/2026-10-22-打開領地爭奪.md）：正式內容的開關打開之後，
哪幾種季新開時蓋得上章、正在跑的季不變、要開新季才有；設定頁管理者工具的「領地爭奪」救場一組（Game.admin_conquest_choices 與網頁）。"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest
from conquest_kit import _new, conquest_rules, go, join, plain_game
from test_seal_web import DRIVER

import server
import webharness
from conftest import no_conquest, real_content
from tianxia import conquest
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 載正式內容、開資料庫

NOW = 1_793_088_000.0  # 2026-10-27（週二）16:00 台灣
ADMIN = "管事"


def _world():
    return open_world(Path(tempfile.mkdtemp(prefix="conqon-")) / "t.db")


@pytest.mark.parametrize(("profile", "stamped"), [("week7", True), ("season21", True), ("week7", True), (None, False)])
def test_a_newly_opened_season_is_stamped_on_for_three_kinds(profile, stamped):
    """週末、21 天、7 天（線上那一種）新開的季蓋上章；14 天（不帶設定）沒有第一季規則的章，蓋不上。籌備中種季、管理者開季兩步都走 stamp_season。"""
    c = real_content(profile)
    assert c.config.conquest.enabled is True
    w = _world()
    w.seed_first_season(c)
    assert w.open_season(c, NOW)
    season = w.get_season()
    assert season.conquest_on is stamped and conquest.on(c, season) is stamped


def test_a_season_opened_before_the_switch_stays_off_until_the_next_season():
    """部署那一刻正在跑的季（舊程式開的、章上沒有領地爭奪）：換上打開的程式照舊關著；管理者收季、開下一季，新的一季才有。"""
    w = _world()
    old = no_conquest(real_content("week7"))
    w.seed_first_season(old)
    assert w.open_season(old, NOW)
    new = real_content("week7")
    new.config.admins = [ADMIN]
    game = Game.new(new, ADMIN, rng=random.Random(0), world=w)
    game.client = None
    game.sync(NOW + 3600)
    assert game.state.world.conquest_on is False and not conquest.on(new, game.state.world)
    assert game.conquest_view() is None and game.admin_conquest_choices() is None
    game.admin_end_season(NOW + 7200)
    game.admin_next_season(NOW + 7300)
    season = w.get_season()
    assert w.get_season_number() == 2 and season.conquest_on is True and conquest.on(new, season)


def test_the_host_switch_still_turns_a_stamped_season_off():
    """主機的緊急開關：蓋了章的季，設定關掉就照關著（conquest.on 也看設定）。"""
    game = _admin_game()
    assert conquest.on(game.content, game.state.world)
    game.content.config.conquest.enabled = False
    assert not conquest.on(game.content, game.state.world) and game.admin_conquest_choices() is None


# ── 設定頁「領地爭奪」救場一組 ──


def _admin_game(profile: str = "week7"):
    c = conquest_rules(real_content(profile))
    c.config.admins = [ADMIN]
    return _new(c, ADMIN)


def test_admin_choices_list_capturable_blocks_two_sides_and_open_sieges():
    """下拉選單：搶得下來的區塊（大本營、廣宗不列；字寫此刻歸誰、進度、冷卻、戰書凍結）、交戰兩軍、還沒打完的攻城。關著的季是 None。"""
    game = _admin_game()
    c, w = game.content, game.state.world
    q = game.admin_conquest_choices()
    ids = [b["id"] for b in q["blocks"]]
    assert ids and all(conquest.capturable(c, loc) for loc in ids)
    assert set(ids) == {loc for loc in conquest.blocks(c) if conquest.capturable(c, loc)}
    assert "changshe" not in ids and "guangzong" not in ids  # 官軍的大本營、廣宗搶不下來
    assert [s["id"] for s in q["sides"]] == ["guan", "huang"] and q["sieges"] == []
    label = next(b["label"] for b in q["blocks"] if b["id"] == "hilltop_wilds")
    assert label == "荒丘（沒人佔）"
    assert {b["id"]: b["name"] for b in q["blocks"]}["yingchuan"] == "潁川郡（陽翟）"  # 問句寫的地名另給（label 不能拿來切）
    game.admin_conquest_progress("hilltop_wilds", "guan", 46)
    assert next(b["label"] for b in game.admin_conquest_choices()["blocks"] if b["id"] == "hilltop_wilds") == "荒丘（沒人佔・官軍 46）"
    game.admin_conquest_progress("hilltop_wilds", "guan", 100)  # 推滿易手：冷卻
    label = next(b["label"] for b in game.admin_conquest_choices()["blocks"] if b["id"] == "hilltop_wilds")
    assert label.startswith("荒丘（官軍・冷卻 ") and label.endswith(" 分）")
    game.admin_conquest_letter("runan_wilds", "guan")
    q = game.admin_conquest_choices()
    [siege] = q["sieges"]
    assert siege["id"] == w.conquest.schedule[-1].id and siege["label"].startswith("汝南荒野：官軍攻・")
    assert "戰書凍結" in next(b["label"] for b in q["blocks"] if b["id"] == "runan_wilds")
    game.admin_conquest_cancel(siege["id"])
    assert game.admin_conquest_choices()["sieges"] == []
    assert plain_game("week7").admin_conquest_choices() is None


def test_server_admin_choices_carry_the_conquest_group(monkeypatch):
    game = _admin_game()
    monkeypatch.setattr(server, "CONTENT", game.content)
    assert server.admin_choices(game)["conquest"] == game.admin_conquest_choices()
    off = plain_game("week7")
    monkeypatch.setattr(server, "CONTENT", off.content)
    assert server.admin_choices(off)["conquest"] is None


def test_the_four_routes_are_admin_actions_named_after_the_engine():
    """網頁的四顆鈕送的路由都在 ADMIN_ACTIONS，跟 Game.admin_* 同名或照舊名（FB-609：不跟玩家的下戰書撞名）。"""
    for op in ("conquest_set", "conquest_progress", "admin_conquest_letter", "conquest_cancel"):
        assert op in server.ADMIN_ACTIONS, op
    assert "conquest_letter" not in server.ADMIN_ACTIONS


def test_a_non_admin_gets_refused_and_the_map_stays():
    """開著領地爭奪、但不是管理者：四條路由都回拒絕話、地圖不動（路由本身不另擋，引擎的 _admin_refusal 擋）。"""
    game = join(go(_new(conquest_rules(real_content("week7")), "路人"), "hilltop_wilds"), "guan")
    before = conquest.holder(game.state.world, game.content, "hilltop_wilds")
    assert game.admin_conquest_set("hilltop_wilds", "guan") == ["（只有管理者能定一塊歸誰。）"]
    assert game.admin_conquest_progress("hilltop_wilds", "guan", 100) == ["（只有管理者能定一塊的進度。）"]
    assert game.admin_conquest_letter("hilltop_wilds", "guan") == ["（只有管理者能立刻下戰書。）"]
    assert conquest.holder(game.state.world, game.content, "hilltop_wilds") == before
    assert conquest.frozen(game.state.world, "hilltop_wilds") is None


# ── 網頁：設定頁畫那一組、四顆鈕先問一次再送 ──


def _admin_view(q):
    return {"battles": [], "events": [], "trends": [], "season_one": False, "showdowns": [], "timetable": [], "results": [],
            "locks": [], "seal": None, "conquest": q}


def _q():
    return {
        "blocks": [{"id": "hilltop_wilds", "name": "荒丘", "label": "荒丘（沒人佔・官軍 46）"},
                   {"id": "yingchuan", "name": "潁川郡（陽翟）", "label": "潁川郡（陽翟）（官軍）"}],
        "sides": [{"id": "guan", "label": "官軍"}, {"id": "huang", "label": "黃巾軍"}],
        "sieges": [{"id": "s-1", "label": "汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30"}],
    }


@pytest.fixture
def m():
    game = _admin_game()
    return server.main_view(game)


def _sheet(m, admin):
    return webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": "return H.sheetHtml();", "S": {"admin": admin},
                                   "menxia": None, "stored": {}, "responses": {}})


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_admin_sheet_draws_the_conquest_group_only_when_on(m):
    sheet = _sheet(m, _admin_view(_q()))
    assert "領地爭奪（救場" in sheet and "荒丘（沒人佔・官軍 46）" in sheet and "汝南荒野：官軍攻" in sheet
    assert "潁川郡（陽翟）（官軍）" in sheet
    for op in ("conquest_set", "conquest_progress", "admin_conquest_letter", "conquest_cancel"):
        assert f'data-op="{op}"' in sheet, op
    assert 'data-op="conquest_set" data-neutral="1"' in sheet
    no_siege = _sheet(m, _admin_view({**_q(), "sieges": []}))
    assert 'data-op="conquest_cancel"' not in no_siege and 'data-op="conquest_set"' in no_siege
    off = _sheet(m, _admin_view(None))
    assert "領地爭奪（救場" not in off and "conquest_" not in off


# 假瀏覽器的 getElementById 只認 app、page 那幾個：換成也認這一組的四個欄位（下拉選單照 selectedIndex 讀字）
FIELDS = """
  const sel = (opts, i) => ({ value: opts[i][0], selectedIndex: i, options: opts.map(([value, text]) => ({ value, text })) });
  const fields = {
    "ad-cq-block": sel([["hilltop_wilds", "荒丘（沒人佔・官軍 46）"], ["yingchuan", "潁川郡（陽翟）（官軍）"]], input.block),
    "ad-cq-side": sel([["guan", "官軍"], ["huang", "黃巾軍"]], input.side),
    "ad-cq-value": { value: input.value },
    "ad-cq-siege": sel([["s-1", "汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30"]], 0),
  };
  const real = T.ctx.document.getElementById;
  T.ctx.document.getElementById = (id) => fields[id] || real(id);
"""


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_the_conquest_buttons_ask_then_post_their_bodies(m):
    from test_admin_triggers_web import CLICK

    clicks = [{"act": "admin", "op": "conquest_set"}, {"act": "admin", "op": "conquest_set", "neutral": "1"},
              {"act": "admin", "op": "conquest_progress"}, {"act": "admin", "op": "admin_conquest_letter"},
              {"act": "admin", "op": "conquest_cancel"}]
    script = CLICK.replace("return (async () => {", "return (async () => {" + FIELDS, 1).replace("input.clicks", json.dumps(clicks))
    out = webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": script, "S": {"admin": _admin_view(_q()), "sheet": True},
                                  "menxia": None, "stored": {}, "responses": {"/api/do/": {"main": m, "message": "好了"}},
                                  "block": 1, "side": 1, "value": "130"})
    asked = out["asked"]
    # 地名照伺服器給的 name（潁川郡（陽翟）自己有括號，不從選單的字切）
    assert "把「潁川郡（陽翟）」定給黃巾軍" in asked[0] and "不分紅、不起冷卻" in asked[0]
    assert "把「潁川郡（陽翟）」放回中立" in asked[1]
    assert "黃巾軍那一條進度定成 100" in asked[2] and "推滿當場易手" in asked[2]  # 欄位寫 130：夾在 100
    assert "替黃巾軍立刻對「潁川郡（陽翟）」下一張戰書" in asked[3]
    assert "取消「汝南荒野：官軍攻・集結・交戰中・第 1 天 16:30」這一場攻城" in asked[4]
    posts = [(c[0], c[1]) for c in out["calls"] if c[0].startswith("/api/do/")]
    assert [p[0] for p in posts] == ["/api/do/conquest_set", "/api/do/conquest_set", "/api/do/conquest_progress",
                                     "/api/do/admin_conquest_letter", "/api/do/conquest_cancel"]
    bodies = [p[1] for p in posts]
    assert (bodies[0]["id"], bodies[0]["side"]) == ("yingchuan", "huang")
    assert (bodies[1]["id"], bodies[1]["side"]) == ("yingchuan", "")
    assert (bodies[2]["id"], bodies[2]["side"], bodies[2]["value"]) == ("yingchuan", "huang", 100)
    assert (bodies[3]["id"], bodies[3]["side"]) == ("yingchuan", "huang")
    assert bodies[4]["id"] == "s-1"


def test_get_sieges_reads_the_same_as_the_whole_state():
    """SqliteWorldStore.get_sieges 只讀流水號與那幾列戰鬥（不整份解析共用狀態與季；計畫 4.4 量到整份讀佔假人一個動作的兩成多）：
    跟 read().sieges 一模一樣——沒有攻城、兩場同時集結、其中一場有人加入之後都一樣。"""
    from conquest_kit import announce, conquest_game
    from tianxia import siege

    game = join(go(conquest_game("season21"), "hilltop_wilds"), "guan")
    same = lambda: [b.model_dump() for b in game.world.get_sieges()] == [b.model_dump() for b in game.world.read().sieges]  # noqa: E731
    assert game.world.get_sieges() == [] and same()
    game.now = NOW
    w = game.state.world
    for slot in (announce(game, "hilltop_wilds", "guan", minute=20 * 60), announce(game, "runan_wilds", "huang", minute=20 * 60)):
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    assert [b.siege.loc for b in game.world.get_sieges()] == ["hilltop_wilds", "runan_wilds"] and same()
    join_id = next(o.id for o in game.options() if o.id.startswith("battle:join:guan"))
    game.choose(join_id)
    assert game.state.player.name in game.world.get_sieges()[0].participants and same()


def test_the_routes_do_what_the_questions_say():
    """問句說的事跟引擎做的對得上：定歸誰發天下大事、不起冷卻；放回中立不發；定進度到 100 易手、起冷卻；下戰書凍結；取消解凍。"""
    game = _admin_game()
    c, w = game.content, game.state.world
    before = len(w.rumors)
    server.ADMIN_ACTIONS["conquest_set"](game, {"id": "hilltop_wilds", "side": "guan"})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and not conquest.cooling(w, c, "hilltop_wilds")
    assert len(w.rumors) == before + 1
    server.ADMIN_ACTIONS["conquest_set"](game, {"id": "hilltop_wilds", "side": ""})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") is None and len(w.rumors) == before + 1
    server.ADMIN_ACTIONS["conquest_progress"](game, {"id": "hilltop_wilds", "side": "huang", "value": 100})
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "huang" and conquest.cooling(w, c, "hilltop_wilds")
    server.ADMIN_ACTIONS["admin_conquest_letter"](game, {"id": "runan_wilds", "side": "guan"})
    w = game.state.world
    slot = conquest.frozen(w, "runan_wilds")
    assert slot is not None
    server.ADMIN_ACTIONS["conquest_cancel"](game, {"id": slot.id})
    assert conquest.frozen(game.state.world, "runan_wilds") is None
