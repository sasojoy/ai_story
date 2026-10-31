"""收場補送裡另外四步：行狀、貢獻、風聞、絕學的契機（view.file_showdown、showdown_pay）。

搬包的審查（dev/battle-1，回歸鏡頭的 should）：這四步一處一處拿掉，相關的 58 個測試檔全綠——test_annals 直接叫 _annal_showdown、
test_cultivation 直接叫 cultivation.seize，沒有一條驗「收場那一下真的寫了行狀、記了貢獻、傳了風聞、給了契機」（搬之前就是這樣）。
這裡照正式內容（week7）造一場收場的長社火攻（官軍大勝），替官軍出手滿回合、戰功排第一的人補那一下（Game._file_showdown，這一季打的），
四樣各驗一次；出手不到 Breakthrough.showdown_rounds 回合的人不擲契機（對照組）。"""
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
