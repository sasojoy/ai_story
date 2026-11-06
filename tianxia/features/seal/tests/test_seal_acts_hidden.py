"""玉璽碎片改版第 2 批：獨門行動不具名（設計第一章第 3、8 條、第三章「兩個只差誰持有／誰起用的世界，別人看得到的一切一字不差」；
計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-2.md Task 7）。五個行動各建兩個只差「誰起用」的世界：甲客或乙客懷著那一片、
兩人同一陣營、站在同一處、指定同樣的目標，起用的那一個用、另一個只同步；旁觀客看到的江湖頁（/api/main）、江湖史、天下大事與傳聞、
輿圖上那一處、酒肆查兩人、兩人的玩家卡、榜單一個字不差。還原漏洞（天下大事那一句帶上起用的人）證明這條測試抓得到。"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path

import pytest

import server
from conftest import real_content
from tianxia import leaderboard, seal, seal_acts, social, tavern
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

AT = "yingchuan_wilds"  # 甲客、乙客站的地方（潁川汝南；不是城鎮）
VIEWER, VIEWER_AT = "旁觀客", "yingchuan"  # 同一區、另一處（城鎮）
CASES = {  # 片 → 指定的目標
    "xuanniu": "bocai",  # 引將：把波才引到潁川郊野
    "yunzhuan": "",  # 頒詔
    "chenglu": "",  # 承露：潁川汝南
    "chizhang": "yingru",  # 傳檄：兩人都是黃巾，不挑邊
    "guixin": "caocao",  # 收心
}


def _person(c, w, name, side, at):
    g = Game.new(c, name, rng=random.Random(0), world=w)
    g.client = None
    p = g.state.player
    p.faction, p.location, p.tutorial_step = side, at, len(c.tutorial.steps)
    p.visited.add(at)
    g.sync(0.0)
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


def _world(shard: str, user: str):
    """正式內容（21 天季）：甲客、乙客（黃巾、同一處）與旁觀客（黃巾、同一區另一處）；user 懷著 shard、在 10 秒起用（另一個同一刻只同步）。
    回旁觀客看得到的一切。"""
    c = real_content("season21")
    c.config.auto_open_first_season = True
    w = open_world(Path(tempfile.mkdtemp(prefix="seal2h-")) / "t.db")

    def _give(st):
        s = seal.filled(st.seal, c).shards[shard]
        s.state, s.holder, s.since_season = "held", user, 0

    w.mutate(_give)
    for name in ("甲客", "乙客"):
        _person(c, w, name, "huang", AT)
    _person(c, w, VIEWER, "huang", VIEWER_AT)
    for name in ("甲客", "乙客"):
        _do(c, w, name, (lambda g: g.seal_use(CASES[shard])) if name == user else (lambda g: None), now=10.0)
    assert [e.holder for e in w.seal_state().registry.uses] == [user]  # 真的起用了
    return _seen(c, w)


def _seen(c, w) -> dict:
    store = CharacterStore(w.db)

    def look(viewer: Game) -> dict:
        season = w.get_season()
        out = {
            "main": json.dumps(server.main_view(viewer), ensure_ascii=False, sort_keys=True, default=str),
            "chronicle": viewer.chronicle_text(),
            "rumors": [(r.layer, r.text, r.location, r.region, r.character) for r in season.rumors],
            "history": [r.text for r in season.chronicle],
            "map": json.dumps(server.map_view(viewer, server.DEFAULT_LAYER, AT), ensure_ascii=False, sort_keys=True, default=str),
            "boards": json.dumps(leaderboard.compute_boards(c, w, store), ensure_ascii=False, sort_keys=True, default=str),
        }
        for name in ("甲客", "乙客"):
            other = store.load(name)
            other.world = viewer.state.world
            out[f"seek:{name}"] = tavern.seek_lines(viewer.state, c, other, 100.0, set())
            # FB-643：打聽交情、名氣、近況、買兇找人也一樣（打聽度夠高、看得到近來的事的那一種在 test_seal_acts.py 的 FB-643 那一段）
            out[f"ties:{name}"] = tavern.ties_player_lines(viewer.state, c, other, [], set())
            out[f"tavern:{name}"] = (tavern.person_fame(other, c), tavern.fresh(other, viewer.state.world.time),
                                     tavern.hit_reach(c, VIEWER_AT, other))
            out[f"card:{name}"] = json.dumps(social.card(viewer, viewer._kin(other)), ensure_ascii=False, sort_keys=True, default=str)
        return out

    return _do(c, w, VIEWER, look, now=20.0)


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
@pytest.mark.parametrize("shard", list(CASES))
def test_two_worlds_that_differ_only_in_who_used_it_look_the_same(shard):
    a, b = _world(shard, "甲客"), _world(shard, "乙客")
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == b[key], key
    public = [text for _, text, *_ in a["rumors"] if "有人起用了" in text]
    assert len(public) == 1 and "甲客" not in public[0] and "乙客" not in public[0]


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_the_guard_has_teeth(monkeypatch):
    """還原漏洞：天下大事那一句帶上起用的人，兩個世界就看得出差別（天下大事、江湖史、江湖頁都在裡面）。"""
    acting: list[str] = []
    use = Game.seal_use

    def leaky_use(self, *args, **kwargs):
        acting[:] = [self.state.player.name]
        return use(self, *args, **kwargs)

    public = seal_acts.public_text
    monkeypatch.setattr(Game, "seal_use", leaky_use)
    monkeypatch.setattr(seal_acts, "public_text", lambda content, act: public(content, act) + "".join(acting))
    a, b = _world("yunzhuan", "甲客"), _world("yunzhuan", "乙客")
    differs = {key for key in a if a[key] != b[key]}
    assert {"rumors", "history", "chronicle"} <= differs, differs
