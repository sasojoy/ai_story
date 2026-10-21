"""玉璽碎片改版第 1 批：持有者平時藏起來（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第一章第 8 條、第三章；
計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-1.md Task 5）。江湖史七格只寫「已現世」、璽動不點名、沒開成單挑那一句不點名、
隱沒不點名、「戰功居前」兩軍都給、酒肆的名氣不算碎片；奪璽單挑那一場照舊露面。假人持璽跟真人一樣藏。
守門：(1) 掃過旁人看得到的各處，持有者的名號不跟碎片一起出現；(2) 兩個只差「誰持有」的世界，旁人看到的一個字不差。"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

import server
from conftest import real_content
from test_seal import _ended, _registry, sealed  # noqa: F401  sealed 是夾具
from test_seal_revamp import revamp
from tianxia import battle_instance, leaderboard, seal, seal_duel, social, tavern
from tianxia import world as world_rules
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile

pytestmark = pytest.mark.slow  # 每一條都載正式內容、開資料庫

VIEWER = "旁觀客"
BOTS = {"甲客": ("guan", "changshe"), "乙客": ("huang", "huangjin_camp")}  # 兩個伺服器假人：陣營、所在地
SHARD = "螭首"


def _world(holder: str, *, on: bool = True):
    """正式內容（21 天季）、一個資料庫：兩個伺服器假人甲客（官軍）、乙客（黃巾）與一個真人旁觀客（黃巾，在別處）；holder 懷著螭首。
    長社火攻開集結、必定牽動螭首（管理者的強制璽動）。回（內容, 資料庫, 旁觀客的 Game）。"""
    c = real_content("season21")
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = on
    w = open_world(Path(tempfile.mkdtemp(prefix="seal1-")) / "t.db")

    def _give(st):
        reg = seal.filled(st.seal, c)
        shard = reg.shards["chishou"]
        shard.state, shard.holder, shard.since_season, shard.emerged_round = "held", holder, 0, reg.round
        reg.force_stir = "chishou"

    w.mutate(_give)
    for name, (side, at) in BOTS.items():
        g = _character(c, w, name, side, at)
        g.state.player.bot = BotProfile(personality="普通", seed=1, faction=side, season_number=1)
        CharacterStore(w.db).save(g.state)
    viewer = _character(c, w, VIEWER, "huang", "yingchuan")
    world_rules.open_showdown(w, c, "changshe_fire", 0.0)
    viewer.sync(1.0)
    return c, w, viewer


def _character(c, w, name, side, at):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, at, len(c.tutorial.steps)
    p.visited.add(at)
    g.sync(0.0)  # 投靠的記進名冊（璽動那一刻照名冊快照持有者的陣營）
    CharacterStore(w.db).save(g.state)
    return g


def _active(viewer):
    """被璽動的那一場打到一半（第 3 回合）：三個人都上陣、各出手 3 回合（戰功一樣）。只拿來問畫面那幾句，不寫回去。"""
    battle = viewer.world.get_battle().model_copy(deep=True)
    battle.phase, battle.round_number = "active", 3
    for name, side in ((VIEWER, "huang"), ("甲客", "guan"), ("乙客", "huang")):
        battle.participants[name] = battle_instance.BattleParticipant(name=name, faction=side, neili=100.0, neili_cap=100.0,
                                                                      acted_rounds=3)
    return battle


def _seen(viewer) -> dict:
    """旁觀客看得到的一切：江湖頁與狀態列（/api/main）、江湖史、天下大事與傳聞、決戰畫面、打到一半的「戰功居前」、酒肆查兩個假人
    （名氣與回話）、兩個假人的玩家卡（不含卡上的鈕：截殺的勝算照實力算，見計畫第三節第 1 條）、榜單。"""
    c, w = viewer.content, viewer.world
    season = w.get_season()
    battle, definition = w.get_battle(), c.battles["changshe_fire"]
    active = _active(viewer)
    store = CharacterStore(w.db)
    out = {
        "main": json.dumps(server.main_view(viewer), ensure_ascii=False, sort_keys=True, default=str),
        "chronicle": viewer.chronicle_text(),
        "rumors": [(r.layer, r.text) for r in season.rumors],
        "history": [r.text for r in season.chronicle],
        "scene": viewer._battle_scene_text(battle, definition),
        "spotlight": viewer._battle_spotlight(active, definition, active.participants[VIEWER]),
        "boards": json.dumps(leaderboard.compute_boards(c, w, store), ensure_ascii=False, sort_keys=True, default=str),
    }
    for name in BOTS:
        other = store.load(name)
        out[f"fame:{name}"] = tavern.person_fame(other, c)
        out[f"seek:{name}"] = tavern.seek_lines(viewer.state, c, other, 100.0, set())
        card = social.card(viewer, viewer._kin(other))
        card.pop("actions")
        out[f"card:{name}"] = json.dumps(card, ensure_ascii=False, sort_keys=True, default=str)
    return out


def _with_shard(lines, name: str) -> list[str]:
    """提到碎片的那幾行裡、寫了 name 的。"""
    return [line for line in lines if name in line and ("璽" in line or SHARD in line)]


def test_the_holder_stays_hidden_from_everyone_else():
    """守門（企劃者「平時藏起來」）：假人甲客懷著螭首、長社火攻牽動了它——旁觀客看得到的狀態列、江湖史、天下大事、決戰畫面、
    「戰功居前」、戰報都不寫甲客跟碎片；收場時甲客那一方大勝、沒開成單挑，那一句也不點名。關著時同一個世界照舊點名（測試抓得到）。"""
    for on in (True, False):
        c, w, viewer = _world("甲客", on=on)
        seen = _seen(viewer)
        texts = [seen["main"], seen["chronicle"], seen["scene"], *seen["spotlight"], *(t for _, t in seen["rumors"]), *seen["history"]]
        leaked = _with_shard(texts, "甲客")
        assert (leaked == []) == on, leaked
        assert ("甲客懷中" in seen["chronicle"]) != on and (f"{SHARD}：已現世" in seen["chronicle"]) == on
        battle = w.get_battle()
        viewer._seal_settle(battle, c.battles["changshe_fire"], {"side": "guan", "margin": "大勝"})  # 懷璽的那一方大勝：不打
        assert w.seal_state().duels == []
        rumors = [r.text for r in w.get_season().rumors]
        assert (_with_shard(rumors, "甲客") == []) == on
        if on:
            assert seal.NO_DUEL_HIDDEN.format(shard=SHARD) in rumors
            assert seal.STIR_HIDDEN.format(shard=SHARD) in rumors


def test_the_seal_duel_itself_still_shows_both_names():
    """奪璽單挑那一場照舊露面：下戰書那一句天下大事、江湖頁的奪璽卡寫兩邊的名號。"""
    c, w, viewer = _world("甲客")
    rows = [("甲客", "guan", 3, 0), (VIEWER, "huang", 3, 3)]
    battle = _ended("changshe_fire", rows, rounds=3, seal_shard="chishou", seal_holder="甲客", seal_holder_faction="guan",
                    seal_holder_side="guan")
    viewer._seal_settle(battle, c.battles["changshe_fire"], {"side": "huang", "margin": "大勝"})
    duel = w.seal_state().duels[0]
    assert (duel.holder.name, duel.challenger.name) == ("甲客", VIEWER)
    assert any("甲客" in r.text and "下了戰書" in r.text for r in w.get_season().rumors)
    card = json.dumps(viewer.seal_duel_card(), ensure_ascii=False)
    assert "甲客" in card and VIEWER in card


def test_two_worlds_that_differ_only_in_the_holder_look_the_same():
    """差異測試（設計第三章「兩個只差誰持有的世界，別人看得到的一切一字不差」）：甲客（官軍）或乙客（黃巾）懷著螭首，其餘一模一樣；
    旁觀客（黃巾）看到的一個字不差——包括「戰功居前」（以前只給持有者對面那一軍，看得出持有者站哪一軍）與酒肆查人（以前名氣多一點）。
    關著時兩個世界看得出差別（這條測試抓得到）。"""
    a, b = _seen(_world("甲客")[2]), _seen(_world("乙客")[2])
    for key in a:
        assert a[key] == b[key], key
    old_a, old_b = _seen(_world("甲客", on=False)[2]), _seen(_world("乙客", on=False)[2])
    differs = {key for key in old_a if old_a[key] != old_b[key]}
    assert {"main", "chronicle", "rumors", "scene", "spotlight", "fame:甲客", "fame:乙客", "seek:甲客"} <= differs, differs


# ── 一處一條：純規則 ──

def test_the_chronicle_cells_say_emerged_and_a_sinking_names_nobody(sealed):
    revamp(sealed)
    reg = _registry(sealed, chishou="懷璽")
    seal.log(reg, 1, "sink", shard="xuanniu", other="失主")
    text = seal.chronicle_block(sealed, reg)
    assert "- 螭首：已現世" in text and "懷璽" not in text
    assert "『玄紐』不知所蹤。" in text and "失主" not in text
    sealed.config.seal.revamp.enabled = False
    text = seal.chronicle_block(sealed, reg)
    assert "- 螭首：懷璽懷中" in text and "失主懷中的『玄紐』不知所蹤。" in text


def test_next_season_writes_a_sinking_without_the_name(sealed, world):
    """換季那一刻判隱沒、寫進江湖史的那一句不點名（改版）。"""
    from conftest import next_season

    revamp(sealed)
    world.seed_first_season(sealed)
    if world.season_phase() == "preparing":
        world.open_season(sealed, 0.0)
    reg = _registry(sealed, chishou="不見人")
    reg.opened_real = 0.0
    reg.shards["chishou"].absent = 2
    world.mutate(lambda st: setattr(st, "seal", reg))
    game = Game.new(sealed, "路人", rng=random.Random(0), world=world)
    next_season(sealed, world, game)
    lines = [r.text for _, entries in world.chronicle_before(world.seal_state().season) for r in entries]
    assert "『螭首』不知所蹤。" in lines and not any("不見人" in line for line in lines)


def test_both_armies_hear_the_merit_hint_and_the_pick_still_hears_it(sealed):
    """「戰功居前」兩軍都給（改版）：持有者那一軍的前幾名也收到，字是有條件的那一句；持有者本人不收。實際被挑上的人一定收到過
    （FB-177：挑人照 challenger_ok，收到的只多不少）。"""
    revamp(sealed)
    battle = _ended("changshe_fire", [("甲", "guan", 3, 2), ("乙", "guan", 3, 0), ("懷璽", "guan", 3, 3), ("丙", "huang", 3, 0)],
                    rounds=3, seal_shard="chishou", seal_holder="懷璽", seal_holder_faction="guan", seal_holder_side="guan")
    battle.phase = "active"
    assert seal.hint_names(battle, sealed, {"懷璽"}) == {"甲", "乙", "丙"}
    assert seal.merit_hint(sealed) == seal.MERIT_HINT_BOTH
    sealed.config.seal.revamp.enabled = False
    assert seal.hint_names(battle, sealed, {"懷璽"}) == {"丙"} and seal.merit_hint(sealed) == seal.MERIT_HINT


def test_the_tavern_no_longer_counts_the_shard_as_fame(sealed, world):
    """酒肆的名氣（查人查得多準）不算碎片那一項（改版）；關著照舊 +1。"""
    from test_seal_revamp import holding

    revamp(sealed)
    game = holding(sealed, world, "chishou")
    with_shard = tavern.person_fame(game.state, sealed)
    copy = game.state.model_copy(deep=True)
    copy.player.heirloom = None
    assert with_shard == tavern.person_fame(copy, sealed)
    sealed.config.seal.revamp.enabled = False
    assert tavern.person_fame(game.state, sealed) == tavern.person_fame(copy, sealed) + 1


def test_the_stir_lines_name_nobody(sealed):
    revamp(sealed)
    who = "持璽客"
    assert seal.stir_text(sealed, who, SHARD) == "此役牽動『螭首』之主。"
    assert who not in seal.stir_text(sealed, who, SHARD, scene=True)
    assert seal.no_duel_text(sealed, who, SHARD) == "『螭首』之主安然無恙，懷璽不失。"
    sealed.config.seal.revamp.enabled = False
    assert seal.stir_text(sealed, who, SHARD) == seal.STIR.format(holder=who, shard=SHARD)
    assert seal.stir_text(sealed, who, SHARD, scene=True) == seal.STIR_SCENE.format(holder=who, shard=SHARD)
    assert seal.no_duel_text(sealed, who, SHARD) == seal.NO_DUEL.format(holder=who, shard=SHARD)


def test_seal_duel_module_is_untouched_by_the_hiding():
    """奪璽單挑那一場的字照舊寫兩邊的名號（設計：那是公開的一場仗）。"""
    assert "{holder}" in seal_duel.CALL and "{challenger}" in seal_duel.CALL and "{holder}" in seal.DUEL_NOTE
