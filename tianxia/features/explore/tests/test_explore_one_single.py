"""減法季 2d：探索一趟只抽一件事（企劃者 2026-10-26：「探索雖然都變成隨機了，但是卻會一次同時觸發打怪＋事件或者意境，這是不是怪怪的」
→「只抽一件事情，然後體力先維持不動」；同一天又改口：體力 18 → 15）。

以前：按一次探索連抽三拍（同一類最多兩拍、要選的拍放最後、三拍都沒收穫補一個一階素材、接了討伐懸賞至少一拍是遭遇）。
現在：一趟只抽一拍、只發生一件事——遭遇、事件、素材、感悟其中一件；體力 6。
- 接了這裡的討伐懸賞：每一趟都是遭遇（打懸賞那一路），交了差回原表；
- 這一拍沒收穫（抽到素材卻沒料、遭遇打輸）照舊補一個一階素材；
- 頭目、三道閘照舊掛在遭遇那一拍；同一處連兩趟不抽同一則感悟（outing_last）照舊。
用正式內容（season21）（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import explore_one, team
from tianxia.encounter import EncounterResult
from tianxia.state import Bounty

ONE_WORDS = set(explore_one.BEAT_WORDS.values())  # 遇事、遇敵、得料、有悟
CONNECTIVES = ("接著", "最後", "然後", "隨後", "之後", "接下來", "後來", "末了", "於是")  # 三拍接成一段才會用到的接續字


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _reset(game) -> None:
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def _trip(game, tier: str = "大勝"):
    """出一趟：回（訊息, 這一趟多的戰報筆數）。"""
    _reset(game)
    battles = len(game.state.battles)
    with _fight(tier):
        msgs = game.choose("act:explore")
    return msgs, len(game.state.battles) - battles


def _strike_bounty(game, loc_id: str) -> Bounty:
    foe = next(f for f in game._wild_foes(game.content.locations[loc_id]) if f.faction == "huang")  # 官軍的討伐要打贏黃巾的隊伍
    b = Bounty(id="s1", kind="strike", faction="guan", week=1, expires=1e12, silver=10, deeds=1, location=loc_id, squad=foe.id,
               takers=[game.state.player.name])
    game.state.world.bounties.append(b)
    return b


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_a_real_trip_brings_one_thing_only():
    """渡口（事件、遭遇、素材、感悟都抽得到）連出六十趟：每一趟的結果標記只有一個字詞，不會同時打一仗又遇事或有所感。"""
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    seen: set[str] = set()
    for i in range(60):
        _, fights = _trip(game)
        tag = game.state.journal[0].tag
        assert tag in ONE_WORDS, (i, tag)
        things = (fights > 0) + (game.state.pending_event is not None) + (p.sensing is not None)
        assert things <= 1, (i, tag, fights, game.state.pending_event, p.sensing)
        assert fights == (1 if tag == "遇敵" else 0), (i, tag, fights)
        seen.add(tag)
    assert len(seen) >= 3, seen  # 不是每一趟都抽到同一件


def test_one_press_costs_six_stamina():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    assert game.content.config.jianfa.explore_stamina == 6
    option = next(o for o in game.options(odds=False) if o.id == "act:explore")
    assert option.label.startswith("探索（體力 6・")
    stamina = p.stamina
    with _fight():
        game.choose("act:explore")
    assert p.stamina == stamina - 6


def test_a_strike_bounty_here_makes_every_trip_that_bounty_fight_and_handing_it_in_goes_back_to_the_table():
    game = ready(jianfa_game(), side="guan", loc="yingchuan_wilds")  # 潁川郊野：黃巾的山賊站在這裡，打贏才算官軍的討伐
    cfg, loc = game.content.config.jianfa, game.content.locations["yingchuan_wilds"]
    table = explore_one.weights(cfg, loc, has_foes=True)
    assert game.outing_plan().how == "foe" and game.outing_plan().weights == table
    b = _strike_bounty(game, "yingchuan_wilds")
    plan = game.outing_plan()
    assert plan.how == "bounty" and plan.hint == "野外有賞" and plan.boss is None
    assert plan.weights == {explore_one.EVENT: 0, explore_one.ENCOUNTER: 100, explore_one.MATERIAL: 0, explore_one.INSIGHT: 0}
    # 2e（FB-880，企劃者 2026-10-26）：對懸賞那一路必敗就不強制。打輸的幾趟會掉氣血、掉到必敗就放開，這條要看的是「打得過卻沒交差，
    # 下一趟還是那一路」，所以勝算釘在難分勝負（必敗放開的規則在 tests/test_explore_one_2e.py）
    with mock.patch.object(game, "odds", return_value="難分勝負"):
        for i in range(8):  # 打輸了沒交差：下一趟還是那一路
            _, fights = _trip(game, "落敗")
            assert fights == 1 and game.state.journal[0].tag == "遇敵", i
            assert game.state.pending_event is None and game.state.player.sensing is None
            assert game.outing_plan().how == "bounty"
        _, fights = _trip(game, "大勝")  # 打贏就交差
        assert fights == 1 and game.state.journal[0].tag == "遇敵"
    b = next(x for x in game.state.world.bounties if x.id == b.id)  # 動作結束存季之後換了一份
    assert b.takers == [] and game.state.player.name in b.done_by
    plan = game.outing_plan()
    assert plan.how == "foe" and plan.weights == table  # 交了差回原表


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_the_paragraph_of_one_trip_has_no_three_beat_connectives():
    """正式內容的句子庫與真的出門回來的那一段，都不出現接著、最後這類三拍才有的接續字。"""
    lines = json.loads((Path(__file__).resolve().parents[4] / "content" / "outing_lines.json").read_text(encoding="utf-8"))
    sentences = [s for group in lines.values() for pool in group.values() for s in pool]
    assert sentences and not [s for s in sentences if any(word in s for word in CONNECTIVES)]
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    for _ in range(30):
        msgs, _ = _trip(game)
        assert not any(word in msgs[0] for word in CONNECTIVES), msgs[0]


def test_the_howto_and_the_action_note_talk_about_one_thing_not_beats():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    note = game.action_notes([o.id for o in game.options(odds=False)])["act:explore"]
    assert note.startswith("出門一趟只碰上一件事") and "拍" not in note
    text = game.howto_text().split("**探索**")[1].split("\n")[0]
    assert "體力 6" in text and "一件事" in text and "拍" not in text and "放在最後" not in text
    ready(game, loc="yingchuan_wilds")
    _strike_bounty(game, "yingchuan_wilds")
    bounty_note = game.action_notes([o.id for o in game.options(odds=False)])["act:explore"]
    assert "拍" not in bounty_note and "討伐" in bounty_note and "每一趟" in bounty_note
    assert "多半" not in bounty_note  # 一定是遭遇，不寫機率
