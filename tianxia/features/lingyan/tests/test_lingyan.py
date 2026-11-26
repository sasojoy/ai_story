"""凌煙閣：從已經跨季存著的紀錄排出每一季上閣的人（hall）、整頁的樣子（hall_html）、路由（關著 404、開著沒登入也看得到）。"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from tianxia.core import battle_base
from tianxia.features.lingyan import hall, hall_html
from tianxia.state import ArenaEntry, Rumor, TierResult


def _end(store, number: int, *, champ: str = "", tier_top: str = "", lines=(), ending: str = "官軍平亂") -> None:
    def fn(s):
        if champ:
            s.arena[champ.casefold()] = ArenaEntry(name=champ, power=10, hp_cap=10, rank=1, wins=7, place=1)
        if tier_top:
            s.final_tiers[tier_top] = TierResult(tier=1, title="平亂元勛", ledger_used="guan", points=900, rank=1, of=5)
            s.final_tiers["別人"] = TierResult(tier=2, title="", ledger_used="guan", points=10, rank=2, of=5)
        for i, text in enumerate(lines):
            s.chronicle.append(Rumor(time=float(i), text=text))
        s.ended = True
        s.ending_title = ending

    store.mutate_season(fn)


def test_an_ended_season_puts_its_people_on_the_hall_one_cell_each(game):
    store = game.world
    _end(store, 1, champ="沈浪", tier_top="沈浪", lines=(
        "第 1 季名人榜：李尋歡（名望 320）、沈浪（名望 200）",
        "第 1 季天下武學榜：沈浪【沈家劍】（神品，評 98，威力 12.0）、王憐花【折梅手】（上品，評 70，威力 9.0）",
        "李尋歡把【飛刀】練成絕學，為之定名【小李飛刀】。",
        "王憐花把【折梅手】練成絕學，為之定名【折梅】。",
    ))
    scrolls, live = hall.hall(store, game.content)
    assert not live
    [s] = scrolls
    assert s.number == 1 and s.ending == "官軍平亂"
    names = [c.name for c in s.cells]
    assert names == ["沈浪", "李尋歡"]  # 擂台天下第一排最前；同一個人一格，事蹟疊在一起
    shen = s.cells[0]
    assert [h.label for h in shen.honors] == ["天下第一", "論功第一", hall.BOARD_HONOR["武學"]]
    assert shen.honors[2].deed == "【沈家劍】"
    li = s.cells[1]
    assert [(h.label, h.deed) for h in li.honors] == [(hall.BOARD_HONOR["名人"], ""), ("絕學首成", "【小李飛刀】")]
    assert "別人" not in names  # 論功只掛第一名


def test_a_running_season_is_not_hung_yet(game):
    scrolls, live = hall.hall(game.world, game.content)
    assert scrolls == [] and live in (True, False)
    assert "閣裡還空著" in hall_html.page(scrolls, live)


def test_second_time_on_the_hall_and_old_seasons_still_read_after_next_season(game):
    store, c = game.world, game.content
    _end(store, 1, champ="沈浪")
    assert store.next_season(c, game.now + 100)
    _end(store, 2, champ="沈浪", lines=("第 2 季善人榜：花滿樓（善名 99）",))
    scrolls, _ = hall.hall(store, c)
    assert [s.number for s in scrolls] == [2, 1]
    assert scrolls[0].cells[0].name == "沈浪" and scrolls[0].cells[0].times == 2
    assert scrolls[1].cells[0].times == 1
    html = hall_html.page(scrolls, False)
    assert "二入凌煙" in html and "第二季" in html and "第一季" in html


def test_a_public_biography_hangs_its_verdict_and_links_the_page(game):
    store = game.world
    _end(store, 1, champ="沈浪")
    store.save_annals(1, "沈浪", [], {})
    store.store_biography(1, "沈浪", "沈浪，江湖人。\n\n評曰：劍出無悔，一生不負。", "史官", 0.0, False)
    scrolls, _ = hall.hall(store, game.content)
    assert scrolls[0].cells[0].verdict == "" and scrolls[0].cells[0].code == ""  # 沒公開不掛
    store.share_biography(1, "沈浪", True, "abc123")
    cell = hall.hall(store, game.content)[0][0].cells[0]
    assert cell.verdict == "劍出無悔，一生不負。" and cell.code == "abc123"
    assert 'href="/zhuan/abc123"' in hall_html.cell_html(cell)


def test_top_merit_takes_the_best_who_acted(monkeypatch):
    ps = {
        "a": SimpleNamespace(name="甲", faction="guan", acted_rounds=3, m=50),
        "b": SimpleNamespace(name="乙", faction="guan", acted_rounds=0, m=90),  # 全程掛機不拿首功
        "c": SimpleNamespace(name="丙", faction="huang", acted_rounds=1, m=0),  # 0 分不算
    }
    monkeypatch.setattr(battle_base, "merit", lambda tuning, p: p.m)
    assert hall.top_merit(SimpleNamespace(participants=ps), None) == {"guan": "甲"}


def test_cn_number_and_html_escapes_names():
    assert [hall_html.cn_number(n) for n in (1, 10, 11, 20, 23)] == ["一", "十", "十一", "二十", "二十三"]
    cell = hall.Cell(name="<b>", honors=[hall.Honor(hall.ARENA, "天下第一", "x")])
    assert "&lt;b&gt;" in hall_html.cell_html(cell) and "<b><b>" not in hall_html.cell_html(cell)


def test_the_page_is_public_and_404_while_off(monkeypatch):
    import server

    client = TestClient(server.app, raise_server_exceptions=False)
    assert client.get("/lingyan").status_code == 404
    monkeypatch.setattr(server.CONTENT.config.lingyan, "enabled", True)
    got = client.get("/lingyan")  # 沒登入（Joy 2026-11-26 選「沒登入也看得到」）
    assert got.status_code == 200 and "凌煙閣" in got.text and "也去江湖走一遭" in got.text
    monkeypatch.setattr(server, "_account", lambda request: "k")
    got = client.get("/lingyan")
    assert got.status_code == 200 and "回江湖" in got.text
