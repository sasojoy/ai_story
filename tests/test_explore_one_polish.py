"""減法季主機側批 2 的小修（PM 2026-10-26；試玩回饋 FB-830～832、hints.json 的「尋敵」）：只改顯示的字，實際入帳不動。
1. FB-830：自家營寨比劃那一趟，段落最後「得：」那一行心得照實際入帳寫一次（以前寫兩倍），後面不再多一則單獨的「心得 +N」；
2. FB-831：撞到破境丹、回體丹時，「得：」那一行只列「破境丹 +1」「回體丹 +1」，不把整句說明當成一樣東西列進去（說明那一句照舊留在訊息裡）；
3. FB-832：鈕上與四格那一格的小字照這一處此刻實際的比重寫（取比重最高的那一類），不是照地點種類；
4. hints.json 的 h_drill_done 在探索一顆開著時不再說「尋敵」。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

import re
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, plain_game, ready

from tianxia import explore_one, hints, journal, team
from tianxia.encounter import EncounterResult

pytestmark = pytest.mark.slow

NUMERIC = re.compile(r"^\S+ [+-]\d+(\.\d+)?")  # 例如「銀兩 +5」「經驗 +10（每人）」


def _beats(*beats: str):
    return mock.patch.object(explore_one, "draw", return_value=list(beats))


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _reset(game) -> None:
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def _ledger_parts(msgs: list[str]) -> tuple[list[str], list[str]]:
    """段落後面那一行「得：…　失：…」拆成（得的幾項, 失的幾項）；沒有那一行是（[], []）。"""
    line = msgs[1] if len(msgs) > 1 and msgs[1][:2] in ("得：", "失：") else ""
    gains, losses = [], []
    for part in line.split("　") if line else []:
        (gains if part.startswith("得：") else losses).extend(part[2:].split("、"))
    return gains, losses


# ── 1. FB-830：營寨比劃的帳 ──


@pytest.mark.parametrize("side, loc", [("guan", "guan_camp"), ("huang", "huangjin_camp")])
def test_the_camp_spar_ledger_writes_the_xinde_once(side, loc):
    game = ready(jianfa_game(), side=side, loc=loc, level=20)
    p = game.state.player
    xinde0, exp0 = p.stats.get("xinde", 0), p.member.exp
    with _beats("encounter", "material", "material"):
        msgs = game.choose("act:explore")
    xinde, exp = p.stats.get("xinde", 0) - xinde0, p.member.exp - exp0
    assert xinde > 0 and exp > 0  # 實際入帳不動（兩倍的只是字）
    gains, losses = _ledger_parts(msgs)
    assert [g for g in gains if g.startswith("心得")] == [f"心得 +{xinde}"], gains
    assert f"經驗 +{exp}（每人）" in gains and not losses
    assert not [m for m in msgs if m.startswith("心得 ")], msgs  # 後面不再多一則單獨的「心得 +N」
    assert game.state.journal[0].changes.count(f"心得 +{xinde}") == 1  # 江湖紀錄的標籤本來就只有一顆


def test_the_camp_spar_ledger_keeps_the_materials_of_the_other_beats():
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    with _beats("encounter", "material", "material"):
        msgs = game.choose("act:explore")
    gains, _ = _ledger_parts(msgs)
    assert any(" ×" in g for g in gains) and any(m.startswith("獲得 ") for m in msgs)  # 素材拍的「得：」照舊


def test_the_camp_spar_called_without_a_journal_draft_still_reports_the_xinde():
    """沒有江湖紀錄草稿（直接叫引擎函式，例如別的測試、腳本）時，心得那一行照樣在回傳的訊息裡，不會悄悄不見。"""
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    plan = game.outing_plan()
    assert game._draft is None and plan.how == "spar"
    msgs = game._outing_fight(game.content.locations["guan_camp"], plan)[0]
    assert any(m.startswith("心得 +") for m in msgs)


@pytest.mark.parametrize("loc", ["guan_camp", "yingchuan_wilds", "yingchuan", "yingshui"])  # 比劃、野外的仗、城裡的地痞、只有素材
def test_the_ledger_numbers_are_the_numbers_the_journal_chips_show(loc):
    """「得：」「失：」那一行的數值跟江湖紀錄的標籤同一份（實際入帳寫一次）：每一種拍都一樣。"""
    game = ready(jianfa_game(), side="guan", loc=loc, level=20)
    game.content.config.training.goals = False  # 新手目標的獎勵會在這一則多記一顆標籤，跟這一行的帳無關
    beats = ("material",) * 3 if loc == "yingshui" else ("encounter", "material", "material")
    with _beats(*beats), _fight("大勝"):
        msgs = game.choose("act:explore")
    gains, losses = _ledger_parts(msgs)
    shown = sorted(x for x in gains + losses if NUMERIC.match(x))
    assert shown == sorted(game.state.journal[0].changes), (shown, game.state.journal[0].changes)


def test_the_other_drills_still_report_the_xinde_line_and_hide_it_from_the_journal_text():
    """操練、出陣的守與攪局共用的 _drill_gains：訊息照舊有「心得 +N」、草稿另記一筆標籤、敘事裡不重複（只有出門一趟的比劃不回那一行）。"""
    game = ready(jianfa_game(explore_one=False), side="guan", loc="guan_camp", level=20)
    foe = game.content.squads["liangzhou_cavalry"]
    game._draft = journal.Draft("操練")
    msgs = game._drill_gains(foe, 0.3)
    xinde = [m for m in msgs if m.startswith("心得 +")]
    assert len(xinde) == 1 and game._draft.changes[0] == xinde[0] and (xinde[0], None) in game._draft.rewrites
    assert not [line for line in game._draft.entry(0.0, msgs).lines if line.startswith("心得 ")]
    game._draft = None
