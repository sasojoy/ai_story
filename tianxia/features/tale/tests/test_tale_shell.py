"""tale 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import re
import pytest
from fastapi.testclient import TestClient
import server
import webharness
from tianxia import tale
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _ended_showdown, _no_landing, _no_preset_recipes, _player, _tale_store, cheap_password_hashing, client,
    fresh_server_memory, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_the_tale_api_says_pending_until_it_is_written(client, tmp_path, monkeypatch):
    """收場了還沒寫好＝pending（網頁畫灰的「史官還在落筆」）、沒這一場＝none、寫好了＝整篇。
    這裡沒有 client（TALES_CLIENT 是 None），寫出來的是模板版——叫不動模型也不會一直卡在 pending。"""
    _player(client)
    _tale_store(tmp_path, monkeypatch)
    record_id = _ended_showdown(open_world())
    assert client.get(f"/api/tale/{record_id}").json() == {"status": "pending"}
    assert client.get("/api/tale/9999").json() == {"status": "none"}
    assert server.tale_round() == record_id
    page = client.get(f"/api/tale/{record_id}").json()
    assert page["status"] == "ready" and page["title"] == "黃巾決戰戰記" and page["result"] == "黃巾大勝"
    assert page["acts"] and all(scene["text"] for act in page["acts"] for scene in act["scenes"])
    assert server.tale_round() is None  # 寫過的不重寫


def test_a_written_tale_gets_a_share_page_anyone_can_open(client, tmp_path, monkeypatch):
    """戰記分享頁（Joy 2026-11-04）：寫好了 /api/tale 帶分享網址（/zhanji/<亂碼>，每次問都是同一個）與遊戲裡那一層的頁（?in=1）；
    沒登入也打得開、帶 Open Graph 與招攬；遊戲裡那一層換成「‹ 返回」、不招攬；認不得的代碼一律 404。"""
    _player(client)
    _tale_store(tmp_path, monkeypatch)
    record_id = _ended_showdown(open_world())
    server.tale_round()
    page = client.get(f"/api/tale/{record_id}").json()
    code = page["url"].rsplit("/", 1)[1]
    assert page["page"] == f"/zhanji/{code}?in=1" and len(code) >= 8 and str(record_id) != code
    assert client.get(f"/api/tale/{record_id}").json()["url"] == page["url"]  # 同一篇同一個代碼
    anyone = TestClient(server.app)  # 沒登入
    html = anyone.get(f"/zhanji/{code}")
    assert html.status_code == 200 and "黃巾決戰戰記・天下大勢" in html.text
    assert f'<meta property="og:url" content="{page["url"]}">' in html.text and 'property="og:image"' in html.text
    assert "zj-cta" in html.text and 'href="/"' in html.text and 'id="zj-back"' not in html.text
    assert "黃巾大勝" in html.text and "官軍" in html.text and "黃巾軍" in html.text
    inside = anyone.get(f"/zhanji/{code}?in=1").text
    assert 'id="zj-back"' in inside and '<section class="zj-cta">' not in inside
    assert anyone.get("/zhanji/nope").status_code == 404
    assert anyone.get(f"/zhanji/{record_id}").status_code == 404  # 流水號猜不到


def test_a_showdown_cut_short_by_the_season_gets_no_tale(client, tmp_path, monkeypatch):
    """季終沒打完收起來的那一場沒有結果（unfinished）：不寫、也不是 pending。"""
    _player(client)
    store = _tale_store(tmp_path, monkeypatch)
    record_id = _ended_showdown(open_world(), unfinished=True)
    assert client.get(f"/api/tale/{record_id}").json() == {"status": "none"}
    assert server.tale_round() is None and store.done(open_world().get_season_number()) == set()


def test_the_tale_needs_a_login_like_the_reports(client):
    assert client.get("/api/tale/1").status_code != 200


def test_a_trait_line_can_lead_the_folded_process_and_the_page_still_recognizes_it():
    """計畫六 Task 4（N1）：功效開打前的句子排在回合前面，收著的「過程」露出的第一行因此是〔先手〕之類的句子、不是「第1回合」。
    網頁認的 ROUNDS_MARK／TALE_MARK 照舊對得上（過程那一段的開頭沒變），第一個 <li> 就是功效的句子；
    大場面的一段話則是功效的句子與模型的話在同一個 <p> 裡、各佔一行（<br />）。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    js = webharness.app_source()
    rounds_mark = re.search(r'const ROUNDS_MARK = "([^"]*)";', js).group(1).replace("\\n", "\n")
    tale_mark = re.search(r'const TALE_MARK = "([^"]*)";', js).group(1).replace("\\n", "\n")
    base = dict(
        id=1, time=0, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10, rounds=["第1回合　甲，你氣血 -5；乙，對手氣勢 -34。", "第2回合　丙。"],
        trait_before=["〔先手〕沈浪搶得先機，【穿林腿】出手在前。"], trait_after=["〔乘勝〕沈浪越打越順，這一仗收穫格外多。"],
    )
    html = server.md(battlelog.card_text(BattleRecord(**base)))
    assert rounds_mark in html
    after_mark = html[html.index(rounds_mark) + len(rounds_mark):]
    assert after_mark.startswith("\n<li>〔先手〕沈浪搶得先機，【穿林腿】出手在前。</li>\n<li>第1回合") and "<li>〔乘勝〕" in after_mark
    tale = server.md(battlelog.card_text(BattleRecord(**base, narration="波才刀勢沉猛，你左支右絀。")))
    assert tale_mark in tale and "<ul" not in tale
    assert tale[tale.index(tale_mark):].startswith(tale_mark + "〔先手〕沈浪搶得先機，【穿林腿】出手在前。<br />\n波才刀勢沉猛，你左支右絀。<br />\n〔乘勝〕")
