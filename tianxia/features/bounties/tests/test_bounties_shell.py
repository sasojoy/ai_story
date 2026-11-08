"""bounties 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
import server
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _journal_titles, _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_a_bounty_option_that_is_no_longer_on_the_menu_tells_the_page_why_and_is_not_journaled(client, monkeypatch):
    """FB-162：兩個分頁搶同一張，慢的那一頁按下去的選項已經不在選單上——跟決戰選項一樣回一句 message（網頁跳提示），
    原因是引擎的拒絕（bounties.give_problem：裝備庫裡沒有這一件）；不寫江湖紀錄。不是懸賞的、也不在選單上的選項照舊什麼都不回。"""
    from tianxia.features.bounties import rules as bounties
    from tianxia.state import Bounty

    monkeypatch.setattr(server.CONTENT.config.weapons, "enabled", True)  # 兵器關著時求兵一律回「此刻無法這麼做」，看不出原因
    _player(client)
    # 開季時已經掛了第 1 週的那一批（b1…），這一張另取名字，免得 give_problem 找到的是別張
    open_world().mutate_season(lambda s: s.bounties.append(Bounty(
        id="b-race", kind="arms", faction="guan", silver=0, deeds=2, quota=3, attribute="柔", weapon_kind="劍", week=1, expires=1e12)))
    before = _journal_titles()
    out = client.post("/api/choose", json={"id": "bounty:give:b-race:兵:9"}).json()
    assert bounties.NO_WEAPON in out["message"]  # 伺服器把話轉成 HTML，網頁跳提示時再去掉標籤
    assert bounties.GONE in client.post("/api/choose", json={"id": "bounty:pick:b99"}).json()["message"]
    assert bounties.STALE in client.post("/api/choose", json={"id": "bounty:unpick"}).json()["message"]  # 榜根本沒開著
    assert _journal_titles() == before
    assert "message" not in client.post("/api/choose", json={"id": "act:nonsense"}).json()
