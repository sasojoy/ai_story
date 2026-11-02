"""收場補送裡另外四步：行狀、貢獻、風聞、絕學的契機（view.file_showdown、showdown_pay）。

搬包的審查（dev/battle-1，回歸鏡頭的 should）：這四步一處一處拿掉，相關的 58 個測試檔全綠——test_annals 直接叫 _annal_showdown、
test_cultivation 直接叫 cultivation.seize，沒有一條驗「收場那一下真的寫了行狀、記了貢獻、傳了風聞、給了契機」（搬之前就是這樣）。
這裡照正式內容（week7）造一場收場的長社火攻（官軍大勝），替官軍出手滿回合、戰功排第一的人補那一下（Game._file_showdown，這一季打的），
四樣各驗一次；出手不到 Breakthrough.showdown_rounds 回合的人不擲契機（對照組）。file_showdown 另外兩支（上一季打的、季終收兵的）
各一條：前後對照（scripts/same_behavior.py）原本一次都沒走到。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import annals, battle_instance, calendar, cultivation
from tianxia.engine import Game
from tianxia.rules import season_one
from tianxia.sqlite_world import open_world

BATTLE = "changshe_fire"  # 長社火攻：時刻表決戰，大區是潁川汝南（yingru）
SEIZED = "（測試：契機擲過了）"


def _game():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "甲客", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "changshe"
    p.tutorial_step = len(c.tutorial.steps)  # 序章裡的人不發軍餉（FB-113）：走完序章
    return game


def _won(name, rounds):
    """官軍大勝收場的長社火攻，name 替官軍出手 rounds 回合（場上只有他：戰功排第一、是首功）。"""
    battle = battle_instance.BattleInstance(battle_id=BATTLE, record_id=7, phase="ended", outcome_side="guan", outcome_margin="大勝",
                                            outcome_title="官軍大勝")
    me = battle_instance.BattleParticipant(name=name, faction="guan", neili=1, neili_cap=1, acted_rounds=rounds)
    battle.participants[name] = me
    return battle, me


@pytest.fixture
def seizes(monkeypatch):
    """cultivation.seize 換成記下難度比、回一句固定的話（真的擲要身上有一門到了門檻；這裡只驗收場那一下有沒有擲、照什麼擲）。"""
    calls = []

    def spy(state, content, world, ratio, rng):
        calls.append(ratio)
        return [SEIZED]

    monkeypatch.setattr(cultivation, "seize", spy)
    return calls


def test_a_won_showdown_writes_the_annal_credits_spreads_the_word_and_rolls_the_chance(seizes):
    game = _game()
    c, p = game.content, game.state.player
    assert season_one(c, game.state.world)  # 貢獻只在第一季規則的季記
    rounds = c.config.breakthrough.showdown_rounds
    battle, me = _won(p.name, max(rounds, c.config.showdown_pay.full_rounds))
    definition = c.battles[BATTLE]
    week = calendar.point(game.state.world.time, c, game.state.world).week

    game._file_showdown(battle, me, None)
    entry = game.state.journal[0]
    record = game.state.battles[0]
    assert entry.title == f"{definition.name}・官軍大勝" and record.battle_ref == battle.record_id

    # 行狀（annal_showdown）：一則決戰，站哪邊、出手幾回合、首功、結果
    (annal,) = [a for a in p.annals if a.kind == annals.SHOWDOWN]
    assert annal.text.startswith(f"{definition.name}，你站在官軍") and "是這一邊的首功" in annal.text and annal.text.endswith("結果官軍大勝。")

    # 貢獻（showdown_pay 的 wins.credit）：本季總數與這一週的帳都記了，跟得失那一行同一個數
    (credit,) = [x for x in entry.changes if x.startswith("貢獻 +")]
    points = int(credit.removeprefix("貢獻 +"))
    assert points > 0 and p.contrib == points and p.contrib_weeks == {week: points}

    # 風聞（figure_life.spread）：打贏的那一邊戰功前三，那一區官軍的人物聽說了（同一場一季只傳一次）
    assert f"merit|{battle.record_id}" in p.hearsay_keys
    heard = [cid for cid, notes in p.hearsay.items() if f"在{definition.name}立了戰功" in notes]
    assert heard, "潁川汝南的官軍人物該聽說這一仗"

    # 絕學的契機（cultivation.seize）：出手滿 showdown_rounds 回合，照決戰的難度比擲一次，那一句接在紀錄與戰報裡
    assert seizes == [c.config.breakthrough.showdown_ratio]
    assert SEIZED in entry.lines and SEIZED in record.notes


def test_too_few_rounds_in_a_showdown_rolls_no_chance(seizes):
    game = _game()
    c = game.content
    rounds = c.config.breakthrough.showdown_rounds
    battle, me = _won(game.state.player.name, rounds - 1)
    game._file_showdown(battle, me, None)
    assert seizes == [] and SEIZED not in game.state.journal[0].lines
    assert any(a.kind == annals.SHOWDOWN for a in game.state.player.annals)  # 行狀照寫（對照：只有契機看回合數）


# ── 另外兩支：上一季打的、季終收兵的（審查 nit：前後對照一次都沒走到，只有混合檔 tests/core/test_engine.py 守著） ──


def test_last_seasons_showdown_is_marked_with_its_season_and_pays_nothing(seizes):
    """上一季收場、這一季才回來補的（earlier 是那一季）：紀錄與戰報標「第 N 季・」，不發軍餉、不算這一季參戰、不記貢獻、不傳風聞、
    不擲契機；行狀接在存起來的那一季後面，不進這一季的行狀。"""
    game = _game()
    c, p = game.content, game.state.player
    game.world.save_annals(1, p.name, [], {})  # 換季時存起來的那一季（Game._reset_player_for_new_season）
    silver = p.stats.get("silver", 0)
    battle, me = _won(p.name, c.config.showdown_pay.full_rounds)
    name = c.battles[BATTLE].name
    game._file_showdown(battle, me, 1)
    entry, record = game.state.journal[0], game.state.battles[0]
    assert entry.title == f"第 1 季・{name}・官軍大勝" and record.location.startswith("第 1 季・")
    assert entry.changes == [] and record.changes == [] and not any("軍餉" in line for line in entry.lines)
    assert p.stats.get("silver", 0) == silver and p.showdowns == 0 and p.top_merits == 0 and p.contrib == 0
    assert f"merit|{battle.record_id}" not in p.hearsay_keys and seizes == []
    assert not any(a.kind == annals.SHOWDOWN for a in p.annals)
    saved = game.world.biography(1, p.name)["annals"]
    assert [a["kind"] for a in saved] == [annals.SHOWDOWN] and saved[0]["text"].startswith(name)


def test_a_showdown_shelved_at_season_end_leaves_only_a_journal_line(seizes):
    """季終沒打完就收兵的（unfinished，FB-035）：只寫一則「不算勝負」的江湖紀錄（出手過幾回合照寫），不加戰報、不放「剛剛」的卡片、
    不發軍餉、不寫行狀、不擲契機。"""
    game = _game()
    c, p = game.content, game.state.player
    silver = p.stats.get("silver", 0)
    battle = battle_instance.BattleInstance(battle_id=BATTLE, record_id=8, phase="ended", unfinished=True,
                                            outcome_title=battle_instance.UNFINISHED_TITLE)
    me = battle_instance.BattleParticipant(name=p.name, faction="guan", neili=1, neili_cap=1, acted_rounds=4)
    battle.participants[p.name] = me
    game._file_showdown(battle, me, None)
    entry = game.state.journal[0]
    assert entry.title == f"{c.battles[BATTLE].name}・{battle_instance.UNFINISHED_TITLE}" and entry.tag == "你站在官軍"
    assert entry.lines == [battle_instance.UNFINISHED_TEXT, "你出手 4 回合"] and entry.changes == []
    assert game.state.battles == [] and game.state.battle_card is None and p.stats.get("silver", 0) == silver
    assert not any(a.kind == annals.SHOWDOWN for a in p.annals) and seizes == [] and p.showdowns == 0
