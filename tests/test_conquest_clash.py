"""翻地與爭搶：混戰（輿圖簡化設計 4.3【企劃者選 b】、第九章第 14 條；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）。
出陣時對面 10 分鐘內在這一塊推過、人還在這裡，照截殺的規則打一場：贏的那一下推得多、輸的白跑、平手照推；保護照截殺（新手期、同一對的冷卻、
被截過的護身、截殺開關），帳跟截殺共用；城鎮也打；沒有戰利品；兩邊各一份戰報。

兩個角色開在同一個資料庫：每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去。

合進區塊表 v3（輿圖第三版第 2 批，feature/territory-conquest b9ee3c9c）之後黃巾開季碰不到荒丘：兩邊撞上的地方從荒丘換成汝南荒野（v3 起是兩邊都碰得到的中立地），斷言不動。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import _new, conquest_rules, fight
from conftest import real_content
from tianxia import conquest, encounter, team
from tianxia.characters import CharacterStore
from tianxia.engine import Game

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
LOC = "runan_wilds"  # 兩邊開季都碰得到的中立地（區塊表 v3 之前用荒丘）


def _world():
    c = conquest_rules(real_content("season21"))
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0  # 不等新手期（新手期另外測）
    first = _new(c, "甲")
    CharacterStore(first.world.db).save(first.state)
    return c, first.world


def _seat(c, world, name, side, loc):
    state = CharacterStore(world.db).load(name)
    if state is None:
        state = _new(c, name, world).state
    p = state.player
    p.faction, p.location, p.journey = side, loc, None
    p.tutorial_step = len(c.tutorial.steps)
    p.stamina = float(c.config.stamina_max)
    p.visited.add(loc)
    CharacterStore(world.db).save(state)


def _do(c, world, name, act):
    state = CharacterStore(world.db).load(name)
    game = Game(c, state, random.Random(0), world)
    game.client = None
    game.now = NOW
    game.state.world = world.get_season()
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _sortie(c, world, name, tier="大勝"):
    with fight(tier):
        return _do(c, world, name, lambda g: g.choose("act:train"))


def _melee(monkeypatch, tier):
    real = encounter.resolve_encounter
    monkeypatch.setattr(encounter, "resolve_encounter",
                        lambda ours, theirs, rng, *a, **k: real(ours, theirs, rng).model_copy(update={"tier": tier}))


def _pair(loc=LOC):
    c, world = _world()
    _seat(c, world, "甲", "guan", loc)
    _seat(c, world, "乙", "huang", loc)
    return c, world


def _base(c, loc):
    """一個人推、沒有集火：名目量 × progress_scale。"""
    return conquest.sortie_nominal(c, loc, "attack") * c.config.conquest.progress_scale


def test_a_win_pushes_more_and_both_sides_get_a_report(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")  # 黃巾先在這裡推了一下
    _melee(monkeypatch, "大勝")
    purse = CharacterStore(world.db).load("乙").player.stats.get("silver", 0)
    msgs, game = _sortie(c, world, "甲")
    w = game.state.world
    assert conquest.bar(w, LOC, "guan") == pytest.approx(_base(c, LOC) * c.config.conquest.clash_scale)
    assert any("乙正在汝南荒野替黃巾軍出力" in m for m in msgs) and any("混戰得勝" in m for m in msgs)
    mine = [r for r in game.state.battles if r.kind == "melee"]
    assert len(mine) == 1 and mine[0].silver in (None, 0)  # 沒有戰利品
    theirs = CharacterStore(world.db).load("乙")
    assert any(r.kind == "melee" for r in theirs.battles)
    assert any(e.title == "遭甲撞上" for e in theirs.journal)
    assert w.raids["甲>乙"] == w.raids["乙>甲"] == w.time and w.raided["乙"] == w.time  # 跟截殺共用一本帳
    assert theirs.player.stats.get("silver", 0) == purse  # 輸的不失銀兩


def test_a_loss_wastes_the_push_but_spends_the_sortie(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "落敗")
    before = CharacterStore(world.db).load("甲").player
    msgs, game = _sortie(c, world, "甲")
    w = game.state.world
    assert conquest.bar(w, LOC, "guan") == 0
    assert any("這一趟白跑了" in m for m in msgs)
    p = game.state.player
    assert p.sorties_today == before.sorties_today + 1 and p.stamina < before.stamina
    assert [r.kind for r in game.state.battles] == ["melee"]  # 沒有打守軍
    assert any(row["name"] == "甲" and row["moved"] == 0 for row in conquest.pushers(w, c, LOC))


def test_a_draw_pushes_as_usual(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "僵持")
    _, game = _sortie(c, world, "甲")
    assert conquest.bar(game.state.world, LOC, "guan") == pytest.approx(_base(c, LOC))


@pytest.mark.parametrize("guard", ["stale", "moved", "cooldown", "shield", "switch", "newbie"])
def test_protections_keep_a_clash_from_happening(monkeypatch, guard):
    c, world = _pair()
    _sortie(c, world, "乙")
    if guard == "stale":  # 11 分鐘前推的：不是「正在推」
        world.mutate_season(lambda s: setattr(s, "time", s.time + 11 * 60))
    elif guard == "moved":
        _seat(c, world, "乙", "huang", "nanyang_road")
    elif guard == "cooldown":
        world.mutate_season(lambda s: s.raids.__setitem__("乙>甲", s.time))  # 他剛截殺過你：這一對三小時內不撞
    elif guard == "shield":
        world.mutate_season(lambda s: s.raided.__setitem__("乙", s.time))
    elif guard == "switch":
        c.config.raid.enabled = False
    elif guard == "newbie":
        c.config.newbie_days = 3
    _melee(monkeypatch, "落敗")
    msgs, game = _sortie(c, world, "甲")
    assert not any(r.kind == "melee" for r in game.state.battles)
    assert conquest.bar(game.state.world, LOC, "guan") > 0  # 照常推


def test_a_clash_happens_in_a_town_on_a_hold(monkeypatch):
    c, world = _world()
    world.mutate_season(lambda s: conquest.set_control(s, c, "runan_wilds", "guan"))  # 汝南荒野歸官軍：汝南（黃巾的城）碰得到
    _seat(c, world, "甲", "huang", "runan")
    _seat(c, world, "乙", "guan", "runan")
    _sortie(c, world, "乙")  # 官軍攻汝南
    _, game = _do(c, world, "甲", lambda g: None)
    pushed = conquest.bar(game.state.world, "runan", "guan")
    assert pushed > 0
    _melee(monkeypatch, "大勝")
    msgs, game = _sortie(c, world, "甲")  # 黃巾在自家的城守：撞上就打（城鎮也打）
    w = game.state.world
    assert any(r.kind == "melee" for r in game.state.battles)
    pull = conquest.sortie_nominal(c, "runan", "hold") * c.config.conquest.progress_scale * c.config.conquest.clash_scale
    assert conquest.bar(w, "runan", "guan") == pytest.approx(max(0.0, pushed - pull))


def test_no_clash_where_the_sortie_cannot_push(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    world.mutate_season(lambda s: s.conquest.fights[LOC].__setattr__("flipped_at", s.time))  # 剛易手：兩邊都推不動
    _melee(monkeypatch, "落敗")
    _, game = _sortie(c, world, "甲")
    assert not any(r.kind == "melee" for r in game.state.battles)


@pytest.mark.parametrize(("tier", "hit_won"), [("大勝", False), ("落敗", True), ("險勝", False)])
def test_the_hit_side_story_follows_its_own_result(monkeypatch, tier, hit_won):
    """FB-606（QA 驗輿圖第三版第 1 批）：被撞的那一方，那一則紀錄「遭某某撞上」與行狀照**自己的**勝負寫，跟他那一份戰報對得上
    （修前照出陣那一方的結果挑句子：出陣的大勝，被撞的戰報「落敗」，紀錄卻寫「你逼退了他」）。"""
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, tier)
    _sortie(c, world, "甲")
    theirs = CharacterStore(world.db).load("乙")
    (record,) = [r for r in theirs.battles if r.kind == "melee"]
    assert (record.tier in team.WIN_TIERS) is hit_won
    entry = next(e for e in theirs.journal if e.title == "遭甲撞上")
    story = next(line for line in entry.lines if "撞上了你" in line)
    annal = next(a.text for a in theirs.player.annals if "撞上了你" in a.text)
    for text in (story, annal):
        if hit_won:
            assert "你逼退了" in text and "你不敵" not in text, text
        else:
            assert "你不敵" in text and "逼退" not in text, text


def test_a_draw_story_is_a_draw_on_the_hit_side(monkeypatch):
    c, world = _pair()
    _sortie(c, world, "乙")
    _melee(monkeypatch, "僵持")
    _sortie(c, world, "甲")
    theirs = CharacterStore(world.db).load("乙")
    assert any("撞上了你" in a.text and "不分高下" in a.text for a in theirs.player.annals)
