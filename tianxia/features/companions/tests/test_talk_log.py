"""往來紀錄（介面重整 2026-11-05，tianxia/features/companions/talk_log.py）：跟大勢人物說過的話一句一列記在資料庫旁邊的小檔，不進角色存檔；
打開才分頁讀；兩季以前的搬去封存檔。伺服器在每個動作前後數一次多談了幾輪（不改引擎）。"""

from random import Random

from tianxia import companion_agent, talk_log
from tianxia.companion_agent import CompanionTurn
from tianxia.core import features as features_core


def _turn(narrative="他點了點頭。"):
    return CompanionTurn(narrative=narrative, options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "雪中送炭"])


def test_new_lines_finds_the_turns_taken_since_the_snapshot(content, state, world):
    before = talk_log.snapshot(state)
    companion_agent.start_dialogue(None, state, content, world, "mate", Random(0), turn=_turn("「你來了。」"))
    lines = talk_log.new_lines(state, before)
    assert lines and lines[-1] == ("mate", "assistant", "「你來了。」")
    assert [role for _, role, _ in lines] == ["user", "assistant"]
    assert talk_log.new_lines(state, talk_log.snapshot(state)) == []  # 沒再談：沒有新的


def test_the_store_pages_newest_first_and_archives_old_seasons(tmp_path):
    store = talk_log.TalkLogStore(tmp_path / "x-talk.sqlite")
    row = lambda i, role="assistant": {"figure": "mate", "at": float(i), "stamp": f"第 1 週・週一 0{i % 10}:00", "place": "宛城",
                                       "role": role, "text": f"第{i}句", "affinity": i}
    store.add("甲", 1, [row(i) for i in range(5)])
    rows, more = store.page("甲", "mate", 1, limit=3)
    assert [r["text"] for r in rows] == ["第4句", "第3句", "第2句"] and more
    rows2, more2 = store.page("甲", "mate", 1, before=rows[-1]["id"], limit=3)
    assert [r["text"] for r in rows2] == ["第1句", "第0句"] and not more2
    assert store.page("乙", "mate", 1)[0] == []  # 別人的看不到
    store.add("甲", 3, [row(9)])  # 換到第 3 季：第 1 季（兩季以前）整批搬去封存檔
    assert store.archive_path.is_file()
    rows3, _ = store.page("甲", "mate", 1)
    assert len(rows3) == 5  # 主檔沒有了，從封存檔讀
    assert store.meets("甲", "mate") == 1


def test_the_endpoint_reads_this_seasons_log_with_affinity_gains(monkeypatch, tmp_path):
    import server

    monkeypatch.setattr(server, "TALK_LOG", talk_log.TalkLogStore(tmp_path / "t-talk.sqlite"))
    monkeypatch.setattr(server, "talk_store", lambda: server.TALK_LOG)

    class P:
        name, season_number, affinities = "甲", 1, {"huangfusong": 10}

    class St:
        player = P()

    class G:
        state, content = St(), server.CONTENT

    monkeypatch.setattr(server, "_game", lambda request: G())
    # 主幹合回 D 段：路由搬進人物情誼包（找法同 tests/web/test_craft_web.py 的 /api/forge_line：這一版 FastAPI 的 app.routes 不攤開 include_router 的路由）
    api_talk_log = next(r.endpoint for rt in features_core.routers(server) for r in rt.routes if r.path == "/api/talk_log")
    server.TALK_LOG.add("甲", 1, [
        {"figure": "huangfusong", "at": 1.0, "stamp": "第 1 週・週一 08:00", "place": "長社", "role": "user", "text": "「將軍。」", "affinity": 4},
        {"figure": "huangfusong", "at": 1.0, "stamp": "第 1 週・週一 08:00", "place": "長社", "role": "assistant", "text": "「坐。」", "affinity": 10},
    ])
    out = api_talk_log(None, id="huangfusong")
    assert [x["text"] for x in out["lines"]] == ["「坐。」", "「將軍。」"]
    assert out["lines"][0]["gain"] == 6 and out["lines"][1]["gain"] == 0
    assert out["meets"] == 1 and out["affinity"] == 10
    assert api_talk_log(None, id="huangfusong", season="prev")["lines"] == []
    assert api_talk_log(None, id="nobody") == {"lines": [], "more": False}
