"""FB-643：起用碎片的那一筆行狀（份量 4）被酒肆讀到——打聽交情列出「近來的事：起用了『X』…」、近況（tavern.fresh）讓查人在哪與
買兇找人變準、行狀份量 4 的三件以上算名氣（person_fame），起用的人被認出來；七片同一條路（第 2 批就有）。PM 定：碎片起用的行狀不給酒肆與
買兇找人讀（annals.SEAL 這一類，tavern.ties_player_lines、fresh、person_fame、hit_reach 一律跳過），行狀本身留著（傳、本人的行狀頁照舊）。

守門照「兩個只差誰起用的世界」：甲客或乙客懷著那一片（同一陣營、同一處、同樣的目標），旁觀客跟他們同陣營、站在同一間酒肆（地頭熟），
兩人名望都到第一段（打聽度 4 以上才列近來的事）、份量 4 的舊事各兩件而且都在兩天前（再一件就多一點名氣、近況只看這一件）。
旁觀客在酒肆打聽交情、查人在哪，加上名氣、近況、打聽度、買兇找人的打聽度與酒肆那一頁，兩個世界要一字不差。正式內容（21 天季＋領地爭奪打開）。"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

from conftest import real_content
from conquest_kit import conquest_rules
from tianxia import annals, biography, conquest, renown, seal, tavern
from tianxia.calendar import DAY
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = pytest.mark.slow  # 每一條都載正式內容、開資料庫

AT = "runan"  # 汝南：黃巾的、有酒肆
VIEWER = "旁觀客"
TARGETS = {  # 片 → 指定的目標（甲客、乙客是黃巾、站在汝南）
    "xuanniu": "bocai",  # 引將
    "yunzhuan": "",  # 頒詔
    "chenglu": "",  # 承露：潁川汝南
    "chizhang": "yingru",  # 傳檄
    "guixin": "caocao",  # 收心
    "chishou": "runan",  # 鎮地
    "jinjiao": "runan_academy",  # 補缺：官軍先翻走汝南書院
}
OLD = -2 * DAY  # 舊事的時刻：兩天前，近況（24 小時）不算它


def _person(c, w, name, side, *, known=False):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, AT, len(c.tutorial.steps)
    p.visited.add(AT)
    p.stats["silver"] = 5000
    if known:
        p.stats["fame"] = renown.fame_bars(c, g.state.world)[0]  # 名望第一段：打聽度 4 以上，打聽交情列得出近來的事
    g.sync(0.0)
    if known:
        for a in p.annals:  # 開局記下的（投靠）挪到兩天前
            a.time = OLD
        while sum(1 for a in p.annals if a.weight >= 4) < 2:
            annals.note(g.state, c, annals.DEED, f"舊事{len(p.annals)}。", 4, time=OLD)
        assert renown.fame_tier(g.state, c) == 1
    g._save_season()
    CharacterStore(w.db).save(g.state)
    return g


def _do(c, w, name, fn, now):
    game = Game(c, CharacterStore(w.db).load(name), random.Random(0), w)
    game.client = None
    game.sync(now)
    out = fn(game)
    game._save_season()
    CharacterStore(w.db).save(game.state)
    return out


def _world(shard: str, user: str, side: str | None):
    """甲客、乙客（side；None 是散人）與旁觀客（黃巾）都在汝南；user 懷著 shard、在 10 秒起用（散人替黃巾）。回旁觀客在酒肆問到的一切。"""
    c = conquest_rules(real_content("season21"))
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = True
    c.config.newbie_days, c.config.newbie_real_hours = -1, 0
    w = open_world(Path(tempfile.mkdtemp(prefix="seal643-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards[shard]
        s.state, s.holder, s.since_season = "held", user, 0

    w.mutate(_give)
    for name in ("甲客", "乙客"):
        _person(c, w, name, side, known=True)
    _person(c, w, VIEWER, "huang")
    if shard == "jinjiao":
        _do(c, w, VIEWER, lambda g: conquest.push(g.state.world, c, "runan_academy", "guan", "官甲", 100, "attack"), now=5.0)
    for name in ("甲客", "乙客"):
        _do(c, w, name, (lambda g: g.seal_use(TARGETS[shard], "huang")) if name == user else (lambda g: None), now=10.0)
    assert [e.holder for e in w.seal_state().registry.history if e.kind == "use"] == [user]  # 真的起用了
    store = CharacterStore(w.db)

    def look(viewer: Game) -> dict:
        assert viewer._tavern_enter() and viewer._tavern_open()
        now = viewer.state.world.time
        out = {}
        for name in ("甲客", "乙客"):
            other = store.load(name)
            other.world = viewer.state.world
            out[f"ties:{name}"] = viewer.tavern_do("ties", name)
            out[f"seek:{name}"] = viewer.tavern_do("seek", name)
            out[f"fame:{name}"] = tavern.person_fame(other, c)
            out[f"fresh:{name}"] = tavern.fresh(other, now)
            out[f"reach:{name}"] = tavern.person_reach(viewer.state, c, other, set())
            out[f"hit:{name}"] = tavern.hit_reach(c, AT, other)
        out["page"] = json.dumps(viewer.tavern_view(), ensure_ascii=False, sort_keys=True, default=str)
        return out

    return _do(c, w, VIEWER, look, now=20.0)


CASES = [(shard, "huang") for shard in TARGETS] + [("chizhang", None), ("chishou", None)]


@pytest.mark.parametrize(("shard", "side"), CASES, ids=[f"{s}-{side or 'ranger'}" for s, side in CASES])
def test_the_tavern_cannot_tell_who_used_a_shard(shard, side):
    a, b = _world(shard, "甲客", side), _world(shard, "乙客", side)
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == b[key], key
    if side is not None:  # 打聽度到 4：近來的事真的列得出來（列得出舊事，就列得出起用那一筆）
        assert any("近來的事" in line for line in a["ties:甲客"])


def test_the_seal_annal_stays_for_its_owner():
    """行狀本身留著：本人的行狀頁照舊寫「行事」、季末的傳照舊歸在出身與行事那一段（跟改之前一樣）。"""
    c = conquest_rules(real_content("season21"))
    c.config.auto_open_first_season = True
    c.config.seal.revamp.enabled = True
    w = open_world(Path(tempfile.mkdtemp(prefix="seal643o-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards["yunzhuan"]
        s.state, s.holder, s.since_season = "held", "懷璽", 0

    w.mutate(_give)
    _person(c, w, "懷璽", "huang")
    _do(c, w, "懷璽", lambda g: g.seal_use(""), now=10.0)
    me = CharacterStore(w.db).load("懷璽")
    [entry] = [a for a in me.player.annals if a.text.startswith("起用了『雲篆』")]
    assert (entry.kind, entry.weight) == (annals.SEAL, 4) and not annals.heard(entry)
    [row] = [r for r in annals.rows(me, c) if r["text"] == entry.text]
    assert row["kind"] == annals.KINDS[annals.DEED]
    req = biography.BiographyRequest(season=1, name="懷璽", scenario="黃巾之亂", era_note="", annals=(entry.model_dump(),))
    assert entry.text in biography.outline(req).split("【出身與行事】")[1].split("【大戰】")[0]
    assert biography._strip(entry.text, "懷璽") in biography.rule_text(req)
