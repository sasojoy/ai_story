"""三陣營四勝利的接線（減法季整合設計 3.2；計畫第五節 5.1 接線清單第 1～4 條；PM 2026-10-25 第 4、5 件）。

開著（season21：豪強分屬兩軍、減法季開著）：貢獻呼叫點改走 wins.credit（豪強另記此刻幫的那一軍那一本）、投靠豪強照投靠點直接給傾向、
拜入曹氏莊院照門派所在地給、「改幫…」隨時換（不算叛投、不發傳聞、帳不清、名冊與活躍名單搬邊、舊那一軍的懸賞作廢）、叛投不列
同陣營換一軍的槽、叛投清掉兩本帳。正式內容、建 Game，整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest

from wins_kit import ids, wins_content, wins_game
from tianxia import bounties, defection, team, wins
from tianxia.content import ContentError, validate
from tianxia.encounter import EncounterResult
from tianxia.state import Bounty

pytestmark = pytest.mark.slow

DAY = 86400


def _win():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40))


# ── 開關與載入檢查 ─────────────────────────────


def test_validate_checks_the_lean_defaults():
    content = wins_content()
    validate(content)
    content.config.jianfa.lean_default_by_join = {"cao_manor": "haoqiang"}
    with pytest.raises(ContentError, match="lean_default_by_join"):
        validate(content)


# ── 投靠那一下 ─────────────────────────────


@pytest.mark.parametrize(("place", "side"), [("zhuo_militia_hall", "guan"), ("cao_manor", "guan"), ("haozu_fort", "huang")])
def test_join_gentry_takes_the_join_point_lean(place, side):
    game = wins_game(at=place)
    game.choose("faction:haoqiang")
    assert ids(game) == ["faction:confirm", "faction:cancel"]  # 不出選邊鈕
    game.choose("faction:confirm")
    p = game.state.player
    assert (p.faction, p.ally, p.lean_changed) == ("haoqiang", side, 0)
    assert game.world.roll_of(p.name) == f"haoqiang@{side}"


def test_sect_join_takes_the_manor_lean():
    """拜入曹氏莊院而投靠（PM 2026-10-25 第 5 件）：照門派所在地，預設幫官軍；不出選邊鈕。"""
    game = wins_game(at="cao_manor")
    game.state.pending_event = "cao_manor_join"
    with _win():
        msgs = game.choose("choice:0")
    p = game.state.player
    assert (p.faction, p.sect, p.ally) == ("haoqiang", "cao_manor", "guan")
    assert msgs[-1] == "你依附了官軍。"
    assert not [i for i in ids(game) if i.startswith("faction:ally:")]
    assert game.world.roll_of(p.name) == "haoqiang@guan"


# ── 兩本帳 ─────────────────────────────


def test_gentry_credit_goes_to_the_lean_book():
    game = wins_game(faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    p = game.state.player
    game.push_trend("yingru", -2, source="event")
    first = p.contrib
    assert first > 0 and p.ledgers == {"guan": first}
    game.choose("faction:lean:huang")
    game.push_trend("yingru", 2, source="event")
    assert p.ledgers["guan"] == first and p.ledgers["huang"] == p.contrib - first > 0


def test_army_credit_keeps_no_books():
    game = wins_game(faction="guan", at="changshe")
    game.push_trend("yingru", -2, source="event")
    assert game.state.player.contrib > 0 and game.state.player.ledgers == {}


def test_showdown_credits_the_side_it_joined():
    """決戰的戰功記參戰那一刻那一邊那一本（計畫 5.0 第 12 條）：中途改幫另一軍，這一場照舊記原來那一軍。"""
    from tianxia.battle_instance import BattleParticipant

    game = wins_game(faction="haoqiang", ally="huang", at="zhuo_militia_hall")
    me = BattleParticipant(name=game.state.player.name, faction="guan", neili=100, neili_cap=100)
    assert game._showdown_credits(me)
    army = wins_game(name="丙客", faction="huang", at="julu_altar")
    assert army._showdown_credits(BattleParticipant(name="丙客", faction="huang", neili=100, neili_cap=100))
    assert not army._showdown_credits(BattleParticipant(name="丙客", faction="guan", neili=100, neili_cap=100))


# ── 改幫另一軍 ─────────────────────────────


def _held_bounty(game, faction: str) -> Bounty:
    w = game.state.world
    b = Bounty(id=f"b-{faction}", kind="scout", faction=faction, week=1, expires=w.time + 10 * DAY, silver=10, deeds=1,
               location="changshe", takers=[game.state.player.name])
    w.bounties.append(b)
    return b


def test_lean_switch_is_not_a_defection():
    game = wins_game(faction="haoqiang", ally="guan", at="changshe")
    game._record_faction()
    s, p = game.state, game.state.player
    w = s.world
    p.contrib, p.ledgers = 30, {"guan": 30}
    w.active_pushers["guan"] = {p.name: w.time - 5}
    held = _held_bounty(game, "guan")
    rumors = len(w.rumors)
    assert "faction:lean:huang" in ids(game) and "faction:lean:guan" not in ids(game)
    msgs = game.choose("faction:lean:huang")
    assert msgs[0] == wins.LEAN_DONE.format(side="黃巾軍", old="官軍")
    lapsed = bounties.LAPSED_LEAN.format(faction="黃巾軍", poster="官軍", title=bounties.title(game.content, held))
    assert msgs[1] == lapsed  # 舊那一軍的懸賞作廢、寫一句（PM 2026-10-25 第 4 件；FB-811：改幫另寫一句，不帶「改投」的口氣）
    assert p.name not in held.takers
    assert (p.ally, p.lean_changed, p.defected, p.contrib, p.ledgers) == ("huang", 1, False, 30, {"guan": 30})
    assert len(w.rumors) == rumors  # 不發傳聞
    assert game.world.roll_of(p.name) == "haoqiang@huang"
    assert p.name not in w.active_pushers.get("guan", {}) and w.active_pushers["huang"][p.name] == w.time - 5
    assert s.journal[0].title == "改幫黃巾軍"
    assert "faction:lean:guan" in ids(game)  # 隨時再換回來


def test_lean_lapse_line_does_not_sound_like_a_defection():
    """FB-811：改幫時舊那一軍的懸賞作廢，那一句不能寫「改投」（上一行才說不算叛投）；叛投照舊用 LAPSED_SIDE。"""
    game = wins_game(faction="haoqiang", ally="guan", at="changshe")
    held = _held_bounty(game, "guan")
    other = _held_bounty(game, "guan")
    other.id = "b-guan-2"
    lines = game.choose("faction:lean:huang")
    lapsed = [line for line in lines if line.startswith("【懸賞】")]
    assert len(lapsed) == 2  # 每張一句
    assert all("改投" not in line and "改幫黃巾軍" in line and "官軍掛的" in line for line in lapsed)
    assert lapsed[0] == bounties.LAPSED_LEAN.format(faction="黃巾軍", poster="官軍", title=bounties.title(game.content, held))
    assert game.state.journal[0].title == "改幫黃巾軍"
    assert all("改投" not in line for line in game.state.journal[0].lines)  # 江湖紀錄那一則也是這兩行
    # 叛投（換陣營）照舊那一句
    defector = wins_game(name="乙客", faction="haoqiang", ally="huang", at="changshe")
    theirs = _held_bounty(defector, "huang")
    defector.choose("defect:guan")
    msgs = defector.choose("defect:confirm")
    assert bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(defector.content, theirs)) in msgs


def test_lean_options_only_for_gentry_when_on():
    assert not [i for i in ids(wins_game(faction="guan", at="changshe")) if i.startswith(wins.LEAN_PREFIX)]
    assert not [i for i in ids(wins_game(name="乙客", at="changshe")) if i.startswith(wins.LEAN_PREFIX)]


def test_lean_switch_follows_a_mustering_battle():
    game = wins_game(faction="haoqiang", ally="guan", at="changshe")
    with mock.patch.object(type(game), "_ally_follows_battle", return_value=["（換到另一邊）"]) as follows:
        msgs = game.choose("faction:lean:huang")
    assert follows.called and msgs[-1] == "（換到另一邊）"


# ── 叛投 ─────────────────────────────


def test_defect_has_no_same_faction_slot_when_on():
    game = wins_game(faction="haoqiang", ally="guan", at="zhuo_militia_hall")
    slots = [(f.id, ally) for f, ally in defection.slots_here(game.state, game.content)]
    assert ("haoqiang", "huang") not in slots
    target = game.content.scenario.faction("haoqiang")
    assert defection.refusal(game.state, game.content, target, None, "huang") == wins.LEAN_NOT_DEFECT
    army = wins_game(name="乙客", faction="guan", at="zhuo_militia_hall")
    assert {(f.id, ally) for f, ally in defection.slots_here(army.state, army.content)} == {("haoqiang", "guan"), ("haoqiang", "huang")}


def test_defect_clears_the_books():
    game = wins_game(faction="haoqiang", ally="guan", at="changshe")
    p = game.state.player
    p.contrib, p.ledgers, p.lean_changed = 30, {"guan": 20, "huang": 10}, 2
    game.choose("defect:guan")
    game.choose("defect:confirm")
    assert (p.faction, p.contrib, p.ledgers, p.lean_changed, p.defected) == ("guan", 0, {}, 0, True)


def test_stranded_helper_matches_the_switch():
    """bounties.stranded 是「改幫」作廢的那一份：舊那一軍掛的單、新的那一邊接不了。"""
    game = wins_game(faction="haoqiang", ally="guan", at="changshe")
    held = _held_bounty(game, "guan")
    assert bounties.stranded(game.state, game.content, "huang") == [held]
    assert bounties.stranded(game.state, game.content, "guan") == []
