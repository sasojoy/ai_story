"""奪璽的網頁那一半（玉璽碎片設計 5.5、5.10、第十節）：江湖頁的奪璽卡、送出放手一搏、背景輪詢與分頁標題、修練頁的傳承那一列。
餵真的引擎給的 /api/main 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

# test_prologue_web 的假瀏覽器只把它列的名字交給 H（wholeApp([...]) 寫成 `{ a, b, … }`：名單上的名字 app.js 裡一定要有，
# 不然整支載不起來）。這裡多交奪璽要直接叫的三個；碎片卡 sealHtml 只經過 pageJianghu，不必列
NAMES_START = 'wholeApp(["S", '  # 名單的開頭（結尾那幾個名字別的計畫會加，開頭比較穩）
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "sealDuelHtml", "sealWatched", "sealTitle", ')


def run(m, script):
    """同 test_prologue_web.run（m 是 /api/main 回的那份）；script 裡可用 H、m、T（T.ctx.document 是假瀏覽器的 document）。"""
    return webharness.run(DRIVER, {"m": m, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})


def _card(**over):
    return {"id": "7:chishou", "shard": "螭首", "challenger": "<b>黃甲</b>", "holder": "懷璽", "phase": "active", "round": 2,
            "rounds": 5, "edge": "黃甲略佔上風", "lines": ["奪璽第 1 回合：黃甲強攻，懷璽以固守相迎——兩邊僵持不下。"], "sent": 1,
            "left": 75, "note": "最後氣勢越偏向挑戰者，碎片越可能易主；璽有靈，未必跟著贏家走。", "mine": False, "tell": "",
            "late": False, "turn": False, "gambles_left": 0, **over}


@pytest.fixture
def m(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game)


def test_the_jianghu_page_draws_the_seal_card_escaped(m):
    m["status"]["seal_duel"] = _card()
    page = run(m, "return H.pageJianghu();")
    assert "奪璽" in page and "螭首" in page and "第 2／5 回合" in page and "已出招 1／2" in page and "1 分 15 秒" in page
    assert "<b>黃甲</b>" not in page and "&lt;b&gt;黃甲&lt;/b&gt;" in page
    assert "璽有靈" in page


def test_the_tell_is_drawn_only_when_the_server_sends_it(m):
    m["status"]["seal_duel"] = _card(mine=True, tell="他退了半步，門戶守得嚴嚴實實。", turn=True)
    page = run(m, "return H.pageJianghu();")
    assert "他退了半步" in page and "輪到你出招" in page
    m["status"]["seal_duel"] = _card(phase="muster", round=0, left=120)
    page = run(m, "return H.pageJianghu();")
    assert "2 分 0 秒後開打" in page and "已出招" not in page


def test_the_input_box_posts_to_seal_text(m):
    m["free_text"], m["free_op"] = "寫下你陣前的一手（20 字內）", "seal_text"
    page = run(m, "return H.pageJianghu();")
    assert 'data-op="seal_text"' in page


def test_a_watched_tab_flags_your_turn_in_the_tab_title(m):
    """5.5：seal_watch 為真時 sealWatched 為真（poll 讀它）；輪到你出招時分頁標題改成「【奪璽】輪到你出招」，之後改回原本的標題。"""
    m["status"]["seal_watch"] = True
    m["status"]["seal_duel"] = _card(mine=True, turn=True)
    out = run(m, "return [H.sealWatched(), H.sealTitle()].join('|');")
    assert out == "true|【奪璽】輪到你出招"
    m["status"]["seal_watch"] = False
    m["status"]["seal_duel"] = None
    out = run(m, "return [H.sealWatched(), H.sealTitle() === H.S.baseTitle].join('|');")
    assert out == "false|true"


def test_a_hidden_tab_polls_only_while_the_seal_is_watched():
    """5.5：背景分頁平常不輪詢；seal_watch 為真時照樣打 /api/main。用 test_push_page 的假頁面跑真的 poll（它切 poll、setMain 與推送那一段）。"""
    from test_push_page import page, start

    out = page(start(False) + """
    S.main.status = { seal_watch: true };
    document.hidden = true;
    await poll();
    const watched = at("/api/main").length;
    await poll();  // 上一次輪詢拿回來的畫面沒有 seal_watch：背景分頁照舊不打
    return [watched, at("/api/main").length, document.title === undefined];
    """)
    assert out == [1, 1, True]  # 假頁面的 S 沒有 baseTitle：setMain 照 sealTitle 改標題


def test_the_holder_card_is_drawn(m):
    m["status"]["seal"] = {"name": "雲篆", "effect_text": "練成的心得 ×0.9", "state": "新得之季，此季不動", "stir": "",
                           "dates": ["第 6 週・週四 20:00", "第 11 週・週四 20:00"]}
    page = run(m, "return H.pageJianghu();")
    assert "『雲篆』" in page and "練成的心得 ×0.9" in page and "新得之季" in page and "第 6 週・週四 20:00" in page


# ── Task 11：管理者「玉璽」一組 ──

def _seal_admin(hung=False, duel=False, qa=False):
    """admin_choices 的那一份（只放設定頁畫得到的幾樣；seal 是 Game.admin_seal_choices 的形狀）。"""
    shards = [{"id": "chishou", "name": "螭首", "state": "held", "holder": "懷璽"}] + [
        {"id": f"s{i}", "name": f"碎片{i}", "state": "hidden", "holder": ""} for i in range(6)
    ]
    return {"battles": [], "events": [], "trends": [], "season_one": False, "showdowns": [], "timetable": [], "results": [],
            "locks": [], "seal": {"shards": shards, "duel": duel, "hung": hung, "where": "長社火攻" if hung else "", "qa": qa}}


def _sheet(m, admin):
    return webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": "return H.sheetHtml();", "S": {"admin": admin},
                                   "menxia": None, "stored": {}, "responses": {}})


def test_the_admin_sheet_draws_the_seal_group(m):
    """第十二節：碎片開著時管理者區多一組「玉璽」：七片與各自的狀態、強制現世、強制璽動、指定持有者、強制開單挑、定結果、取消單挑、隱沒判斷。"""
    sheet = _sheet(m, _seal_admin())
    assert "玉璽" in sheet and "螭首（懷璽懷中）" in sheet and sheet.count("（未現世）") == 6
    for op in ("seal_emerge", "seal_stir", "seal_assign", "seal_cancel", "seal_sink_check"):
        assert f'data-op="{op}"' in sheet, op
    assert 'data-op="seal_duel" disabled' in sheet and "沒有剛收場的決戰可掛" in sheet  # 沒掛得上、也不是 QA
    assert 'data-op="seal_fix" data-take="1" disabled' in sheet  # 沒有單挑在打
    live = _sheet(m, _seal_admin(hung=True, duel=True))
    assert 'data-op="seal_duel" disabled' not in live and 'data-op="seal_fix" data-take="1" disabled' not in live
    assert "長社火攻" in live
    plain = _sheet(m, {**_seal_admin(), "seal": None})
    assert "seal_emerge" not in plain  # 碎片關著（admin_seal_choices 是 None）：不畫


def test_seal_admin_buttons_ask_then_post_to_their_routes(m):
    from test_admin_triggers_web import CLICK

    import json

    script = CLICK.replace("input.clicks", json.dumps([{"act": "admin", "op": "seal_cancel"}, {"act": "admin", "op": "seal_emerge"}]))
    out = webharness.run(DRIVER, {"m": {**m, "admin": True}, "script": script, "S": {"admin": _seal_admin(duel=True), "sheet": True},
                                  "menxia": None, "stored": {}, "responses": {"/api/do/": {"main": m, "message": "好了"}}})
    assert "取消" in out["asked"][0] and "現世" in out["asked"][1]
    assert [c[0] for c in out["calls"] if c[0].startswith("/api/do/")] == ["/api/do/seal_cancel", "/api/do/seal_emerge"]


def test_the_seal_moves_sit_above_the_action_bar_not_in_the_fold(m):
    """最終審查 I-1：閒著的時候（選單上有打坐）奪璽三招不掉進收起來的「此地還能做」，畫在行動列上面（5.5「選單最前面」）。"""
    assert any(o["id"] == "act:rest" for o in m["options"])
    base = next(o for o in m["options"] if o["id"] == "act:rest")
    moves = [{**base, "id": f"seal:{move}", "label": f"{move}（剋{beat}）", "enabled": True}
             for move, beat in (("強攻", "奇襲"), ("固守", "強攻"), ("奇襲", "固守"))]
    m["options"] = moves + m["options"]
    page = run(m, "return H.pageJianghu();")
    at = page.index('data-id="seal:強攻"')
    assert at < page.index('class="act-bar"')
    fold = page.find('class="fold here"')
    assert fold == -1 or at < fold or 'data-id="seal:' not in page[fold:]
