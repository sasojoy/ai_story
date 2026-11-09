"""結義能幹嘛（設計稿 https://claude.ai/artifact/8xg7rEersma24d6uikMi76；Joy 2026-11-09「贈素材不要 其他按照建議」「第二批也繼續做」）：
第一批義不相殘、替兄出頭（追回銀兩）、名分（卡、名帖、江湖史、列傳）；第二批義聚、並肩作戰。不加屬性、不加勝算。"""
from __future__ import annotations

import random

import pytest
from test_raid import NOW, _do, _load, _seat

from tianxia import encounter, rules as game_rules
from tianxia.characters import CharacterStore
from tianxia.core import annal_base, battle_base, jieyi_base
from tianxia.core.combat import battle_marks
from tianxia.engine import Game
from tianxia.features.bounties import rules as bounty_rules
from tianxia.features.jieyi import actions, rules
from tianxia.models import BattleTuning
from tianxia.state import Bounty
from tianxia.world_state import JieyiBond


@pytest.fixture
def trio(content, world):
    """甲（官軍）、乙（黃巾）、丙（黃巾）都在湖畔；甲與丙結義（不同陣營）。"""
    content.config.jieyi.enabled = True
    _seat(content, world)
    game = Game.new(content, "丙", rng=random.Random(0), world=world)
    game.client = None
    game_rules.learn_skill(game.state, content, "fist")
    game.state.player.faction = "huang"
    game.state.player.location = "lake"
    game.state.player.stamina = 100.0
    game.state.player.stats["silver"] = 200
    game.sync(NOW)
    CharacterStore(world.db).save(game.state)
    _bond(world, "甲", "丙")
    return content, world


def _bond(world, *names):
    def _apply(shared):
        shared.jieyi.seq += 1
        b = JieyiBond(id=str(shared.jieyi.seq), place="lake", season=1, members=list(names))
        shared.jieyi.bonds[b.id] = b
    world.mutate(_apply)


def _book(world):
    return world.read().jieyi


def _win(monkeypatch, tier="大勝"):
    real = encounter.resolve_encounter
    monkeypatch.setattr(encounter, "resolve_encounter", lambda ours, theirs, rng, *a, **k: real(ours, theirs, rng).model_copy(update={"tier": tier}))


def _buttons(content, world, me, other):
    return _do(content, world, me, lambda g: g.peer_card(other))[0]


def test_brothers_cannot_raid_each_other_even_across_factions(trio):
    content, world = trio
    card = _buttons(content, world, "甲", "丙")
    assert not [b for b in card["actions"] if b["action"] == "raid"]  # 官軍與黃巾，結了義就不畫
    assert _do(content, world, "甲", lambda g: g.peer_act("丙", "raid"))[0] == [jieyi_base.SWORN_NO]
    content.config.jieyi.enabled = False  # 開關關著：照舊敵對陣營截殺得了
    assert [b for b in _buttons(content, world, "甲", "丙")["actions"] if b["action"] == "raid"]


def test_a_wanted_poster_on_a_brother_cannot_be_taken(trio):
    content, world = trio
    state = _load(world, "甲")
    b = Bounty(id="w1", kind="wanted", faction="guan", week=1, expires=1e9, silver=50, deeds=1, poster="某", target="丙")
    assert bounty_rules.take_problem(state, content, b, world) == jieyi_base.SWORN_BOUNTY
    assert bounty_rules.take_problem(state, content, b) != jieyi_base.SWORN_BOUNTY  # 沒給 world（舊呼叫端）照舊


def test_a_brother_avenges_a_raid_and_the_silver_goes_back(trio, monkeypatch):
    content, world = trio
    _win(monkeypatch)
    state = _load(world, "乙")
    state.player.faction = "guan"  # 乙改投官軍：跟黃巾的丙敵對、跟官軍的甲同陣營（平常甲截不了乙）
    CharacterStore(world.db).save(state)
    _do(content, world, "乙", lambda g: g.peer_act("丙", "raid"))
    lost = 200 - _load(world, "丙").player.stats["silver"]
    assert lost > 0
    [feud] = _book(world).feuds
    assert feud.victim == "丙" and feud.raider == "乙"
    # 甲同步：收到消息；甲與乙同是官軍，平常截不了，卡上是「替兄出頭」，也不看乙剛被截過的護身
    s = world.get_season()
    s.raided["乙"] = s.time  # 乙剛被截過：平常有護身
    world.save_season(s)
    msgs, g = _do(content, world, "甲", lambda g: g.peer_card("乙"))
    assert any("被乙截殺" in line for e in g.state.journal for line in e.lines)
    [btn] = [b for b in msgs["actions"] if b["action"] == "raid"]
    assert btn["label"] == jieyi_base.AVENGE_LABEL and btn["enabled"], btn
    before = _load(world, "甲").player.stats["silver"]
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))
    assert any("替丙出了這口氣" in m for m in msgs)
    assert _load(world, "甲").player.stats["silver"] == before  # 贏到的那一份轉給兄弟，自己不多拿
    [feud] = _book(world).feuds
    assert feud.avenged_by == "甲" and feud.owed > 0
    owed = feud.owed
    v_before = _load(world, "丙").player.stats["silver"]
    _, g = _do(content, world, "丙", lambda g: [])
    assert g.state.player.stats["silver"] == v_before + owed
    assert not _book(world).feuds  # 交完就清
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_card("乙"))  # 一筆仇只報一次
    assert not [b for b in msgs["actions"] if b["action"] == "raid" and b["label"] == jieyi_base.AVENGE_LABEL]


def test_the_feud_expires(trio, monkeypatch):
    content, world = trio
    state = _load(world, "乙")
    state.player.faction = "guan"
    CharacterStore(world.db).save(state)
    _win(monkeypatch)
    _do(content, world, "乙", lambda g: g.peer_act("丙", "raid"))
    g = Game(content, _load(world, "甲"), random.Random(0), world)
    g.sync(NOW)
    assert jieyi_base.feud_against(content, world, "甲", "乙", NOW + 10) is not None
    assert jieyi_base.feud_against(content, world, "甲", "乙", NOW + content.config.jieyi.feud_seconds + 1) is None


def test_name_tag_on_card_and_mingtie(trio):
    content, world = trio
    card = _buttons(content, world, "乙", "甲")
    assert card["jieyi"].endswith("二義・行一")
    assert jieyi_base.card_tag(content, world, "丙").endswith("・行二")
    assert jieyi_base.card_tag(content, world, "乙") == ""
    content.config.jieyi.enabled = False
    assert "jieyi" not in _buttons(content, world, "乙", "甲")


def test_forming_and_leaving_go_into_chronicle_and_annals(trio):
    content, world = trio
    chron: list[str] = []

    def _leave(shared):
        rules.leave(shared.jieyi, content, "丙", 1, NOW, chron)
    world.mutate(_leave)
    assert chron[0].startswith("丙割袍斷義") and "散了" in chron[1]
    assert _book(world).notes["甲"][-1].endswith("就此散了。")
    _, g = _do(content, world, "甲", lambda g: [])
    if annal_base.on(content):
        assert any("散了" in a.text for a in g.state.player.annals)
    assert "甲" not in _book(world).notes


def test_leave_writes_the_season_chronicle(trio):
    content, world = trio
    _do(content, world, "丙", actions.leave)
    texts = [r.text for r in world.get_season().chronicle]
    assert any("丙割袍斷義" in t for t in texts)


def test_gathering_gives_stamina_once_a_day(trio):
    content, world = trio
    def tired(g):
        g.state.player.stamina = 50.0
        return [o.id for o in g.options()]
    ids, _ = _do(content, world, "甲", tired)
    assert "jieyi:gather" in ids
    msgs, g = _do(content, world, "甲", lambda g: g.choose("jieyi:gather"))
    assert any("義聚" in m and "+15" in m for m in msgs), msgs
    assert g.state.player.stamina >= 50.0 + 15 - 1
    ids, _ = _do(content, world, "甲", lambda g: [o.id for o in g.options()])
    assert "jieyi:gather" not in ids
    assert _do(content, world, "甲", lambda g: actions.gather(g))[0] == [rules.GATHER_AGAIN]
    _do(content, world, "丙", lambda g: g.choose("jieyi:gather"))
    log = [line for b in _book(world).bonds.values() for line in b.log]
    assert sum("義聚" in line for line in log) == 1  # 同一天一組只寫一行
    view = _do(content, world, "甲", lambda g: g.feature_status()["jieyi"])[0]
    assert view["gather"]["ready"] is False


def test_gathering_needs_a_brother_here(trio):
    content, world = trio
    state = _load(world, "丙")
    state.player.location = "town"
    CharacterStore(world.db).save(state)
    ids, _ = _do(content, world, "甲", lambda g: [o.id for o in g.options()])
    assert "jieyi:gather" not in ids
    assert _do(content, world, "甲", actions.gather)[0] == [rules.GATHER_ALONE]


def test_gather_amount_steps():
    from tianxia.core.tuning.jieyi import JieyiTuning
    cfg = JieyiTuning()
    assert [rules.gather_amount(cfg, n) for n in (1, 2, 3, 4, 5, 6)] == [0, 15, 20, 25, 30, 30]


def test_status_without_a_bond_is_an_empty_paper(trio):
    content, world = trio
    view = _do(content, world, "乙", lambda g: g.feature_status()["jieyi"])[0]
    assert view == {"empty": actions.EMPTY}


def test_fighting_side_by_side_adds_merit_only(trio):
    content, world = trio
    g = Game(content, _load(world, "甲"), random.Random(0), world)
    g.sync(NOW)
    marks = battle_marks(g)
    assert marks["sworn"] == ["丙"] and marks["sworn_step"] == 5 and marks["sworn_max"] == 10
    tuning = BattleTuning()
    a = battle_base.BattleParticipant(name="甲", faction="guan", neili=10, neili_cap=10, acted_rounds=4, sworn=["丙", "丁"], sworn_step=5, sworn_max=10)
    c = battle_base.BattleParticipant(name="丙", faction="guan", neili=10, neili_cap=10, acted_rounds=1)
    d = battle_base.BattleParticipant(name="丁", faction="huang", neili=10, neili_cap=10, acted_rounds=3)
    base = battle_base.merit(tuning, a)

    class _Inst:
        participants = {"甲": a, "丙": c, "丁": d}
    battle_base.note_sworn(_Inst)
    assert a.sworn_mates == ["丙"]  # 丁站另一方，不算
    assert battle_base.sworn_pct(a) == 5 and battle_base.merit(tuning, a) == base + base * 5 // 100
    d.faction = "guan"
    battle_base.note_sworn(_Inst)
    assert battle_base.sworn_pct(a) == 10
    a.sworn_max = 10
    a.sworn_mates = ["丙", "丁", "戊"]
    assert battle_base.sworn_pct(a) == 10  # 最多一成
    content.config.jieyi.enabled = False
    assert "sworn" not in battle_marks(g)
