"""季末四階的接線（減法季整合設計 3.3、3.4；計畫 Task 3c-2、5.1 接線清單第 5 條）：開季 → 幾個人做事 → 管理者收季 →
WorldState.final_tiers、一二階寫江湖史、結局卡（欄位表 main.ending）→ 開下一季 → 起手資源與稱號（狀態列、玩家卡接在後面）。
關著（減法季的總開關關掉）的季什麼都不寫、下一季也不發。正式內容（season21）、整季的流程，整個檔標 slow。"""
from __future__ import annotations

import json
import random

import pytest

from wins_kit import save, wins_content, wins_game
from tianxia import social, wins
from tianxia.characters import CharacterStore
from tianxia.engine import Game

pytestmark = pytest.mark.slow

NOW = 1_800_000_000.0
ADMIN = "論功官"


def _season(off: bool = False):
    """一季：管理者＋官軍三人、黃巾兩人、豪強兩人（各幫一軍）、散人一人，貢獻直接寫好（其中兩人照引擎真的推一次）。"""
    content = wins_content()
    if off:
        content.config.jianfa.enabled = False
    content.config.admins = [ADMIN]
    admin = wins_game(content, name=ADMIN)
    w = admin.world
    people = {
        "官甲": ("guan", None, 200), "官乙": ("guan", None, 90), "官丙": ("guan", None, 10),
        "巾甲": ("huang", None, 150), "巾乙": ("huang", None, 70),
        "豪甲": ("haoqiang", "guan", 0), "豪乙": ("haoqiang", "huang", 0), "散人": (None, None, 0),
    }
    games = {}
    for name, (faction, ally, contrib) in people.items():
        game = wins_game(content, name=name, faction=faction, ally=ally, at="changshe", world=w)
        game.state.player.contrib = contrib
        games[name] = game
    games["豪甲"].state.player.contrib, games["豪甲"].state.player.ledgers = 120, {"guan": 100, "huang": 20}
    games["豪乙"].state.player.contrib, games["豪乙"].state.player.ledgers = 80, {"huang": 80}
    games["官丙"].push_trend("yingru", -2, source="event")  # 照引擎記的貢獻（wins.credit）
    games["豪甲"].push_trend("yingru", -2, source="event")
    for game in games.values():
        save(game)
    return content, admin, games


def _reload(content, world, name: str) -> Game:
    return Game(content, CharacterStore(world.db).load(name), random.Random(0), world)


def test_season_end_settles_tiers_and_the_next_season_pays():
    content, admin, games = _season()
    w = admin.world
    assert "賽季" in "".join(admin.admin_end_season(NOW))
    season = w.get_season()
    assert season.ended and wins.winner_of(season, content) == "guan"  # 官軍 55：黃巾敗退（官軍贏）
    tiers = {name: (r.tier, r.title, r.ledger_used) for name, r in season.final_tiers.items()}
    assert tiers["官甲"] == (1, "漢室忠良", "guan")
    assert tiers["官乙"] == (3, "有功之臣", "guan")  # 第三階至少 1 人（PM 2026-10-25 第 1 件）
    assert tiers["官丙"][0] == 0  # 不到門檻 40
    assert tiers["巾甲"] == (3, "有功之臣", "huang") and tiers["巾乙"] == (4, "隨軍", "huang")
    assert tiers["豪甲"] == (2, "一方之雄", "guan")  # 替官軍那一本（引擎那一推也記在這一本）
    assert tiers["豪乙"] == (3, "鄉里之望", "huang")  # 替官軍那一本是 0：照替黃巾那一本
    assert "散人" not in tiers and ADMIN not in tiers
    assert season.final_tiers["豪甲"].points > 100
    chronicle = [r.text for r in season.chronicle]
    assert "季末論功，官軍第一階「漢室忠良」：官甲。" in chronicle
    assert "季末論功，地方豪強第二階「一方之雄」：豪甲。" in chronicle

    card = _reload(content, w, "豪乙").ending_card()
    assert card == {"winner": "guan", "condition": "地方豪強（黃巾軍）", "my_tier": 3, "title": "鄉里之望",
                    "reward": "下一季開局銀兩 150、心得 100", "ledger_used": "huang"}
    loser = _reload(content, w, "官丙")
    assert loser.ending_card() == {"winner": "guan", "condition": "官軍", "my_tier": 0, "title": "", "reward": "", "ledger_used": None}
    assert loser.season_result()["ending"] == loser.ending_card()  # 休季結算卡也帶著（main_view 搬到 main.ending）
    drifter = _reload(content, w, "散人")
    assert drifter.ending_card()["condition"] is None and drifter.ending_card()["my_tier"] == 0

    admin.admin_next_season(NOW + 60)
    top = _reload(content, w, "官甲")
    p = top.state.player
    assert p.season_number == 2 and p.season_title == "漢室忠良"
    assert p.stats["silver"] >= 300 and p.stats["xinde"] >= 200
    entry = next(e for e in top.state.journal if e.title == wins.GRANT_TITLE)
    assert "銀兩 +300" in entry.changes and "心得 +200" in entry.changes
    assert social.affiliation(top.state, content).endswith("・漢室忠良")
    fresh = Game.new(content, "新人", rng=random.Random(0), world=w)
    gap = {k: top.state.player.stats.get(k, 0) - fresh.state.player.stats.get(k, 0) for k in ("silver", "xinde")}
    assert gap == {"silver": 300, "xinde": 200}
    fourth = _reload(content, w, "巾乙")
    assert {k: fourth.state.player.stats.get(k, 0) - fresh.state.player.stats.get(k, 0) for k in ("silver", "xinde")} == {"silver": 90, "xinde": 60}
    nothing = _reload(content, w, "官丙").state.player
    assert nothing.season_title == "" and not any(e.title == wins.GRANT_TITLE for e in _reload(content, w, "官丙").state.journal)
    assert "season_title" not in json.loads(nothing.model_dump_json())  # 沒有稱號不寫進存檔


def test_off_season_writes_no_tiers_and_pays_nothing():
    content, admin, games = _season(off=True)
    w = admin.world
    admin.admin_end_season(NOW)
    season = w.get_season()
    assert season.final_tiers == {}
    assert "final_tiers" not in json.loads(season.model_dump_json())  # 關著的季存檔一個鍵都不多
    assert not [r for r in season.chronicle if r.text.startswith("季末論功")]
    top = _reload(content, w, "官甲")
    assert top.ending_card() is None and "ending" not in top.season_result()
    admin.admin_next_season(NOW + 60)
    p = _reload(content, w, "官甲").state.player
    assert p.season_title == "" and not any(e.title == wins.GRANT_TITLE for e in _reload(content, w, "官甲").state.journal)
