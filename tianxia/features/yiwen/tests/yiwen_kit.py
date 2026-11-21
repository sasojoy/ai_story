"""異聞測試的小工具（檔名全 repo 不重複）：換測試內容的十八句、擺一則撞見、開一份 season21 的世界。"""
from __future__ import annotations

import random
from pathlib import Path

from tianxia.features.yiwen import actions, rules
from tianxia.state import YiwenClaim, YiwenWalk, YiwenWorld

DATA = Path(__file__).resolve().parent / "data" / "yiwen_openings.json"


def use_test_lines(monkeypatch) -> None:
    """開場換成測試內容的十八句（rules.FILES 那一格），清快取；測完 monkeypatch 換回來時再清一次由 clear_after 負責。"""
    monkeypatch.setitem(rules.FILES, "openings", DATA)
    rules.cache_clear()


def turn_on(game) -> None:
    """測試內容的 game：開關打開、這一季補蓋章（開季時開關還關著），寫回共用賽季。"""
    game.content.config.yiwen.enabled = True
    game.state.world.yiwen_on = True
    game._save_season()


def claim(game, opening: str, place: str | None = None) -> YiwenWalk:
    """擺一則剛撞見、一幕都還沒寫的（發掘者）：全服名額記他、眼前那一則是它。"""
    s, p = game.state, game.state.player
    place = place or p.location
    yw = s.world.yiwen = s.world.yiwen or YiwenWorld()
    yw.taken[opening] = YiwenClaim(by=game._mall_owner(), at=rules.season_clock(s.world, game.content))
    w = p.yiwen = p.yiwen or YiwenWalk()
    actions._clear(w)
    w.opening, w.place, w.role, w.own_from = opening, place, rules.FIND, 0
    game._save_season()
    return w


def walk_all(game, picks=(0, 0, 0)) -> list[list[str]]:
    """照 picks 按三步（每一步照當下的 card 送 yiwen_step 的 body）。"""
    out = []
    for i in picks:
        c = actions.card(game)
        out.append(actions.step(game, {"tale": c["tale"], "opening": c["opening"], "node": c["node"], "pick": i}))
    return out


def season21_game(name: str = "陸三刀", world=None, kind: str = "wild", content=None, **tuning):
    """正式內容 season21、開關打開（開季時就蓋章）、季自己開、出了序章、站在第一個 kind 的地點；tuning 蓋過 Config.yiwen 的數字。
    world 給了就跟那一局同一個世界（兩個人撞同一則）；沒給每一局自己一個資料庫檔。content 給了就用那一份（同一個世界的兩局要同一份）。"""
    import tempfile

    from conftest import real_content
    from jianfa_kit import ready
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = content
    if c is None:
        c = real_content("season21")
        c.config.auto_open_first_season = True
        c.config.train_event_chance = 0.0
        c.config.yiwen.enabled = True
        c.config.guard.enabled = False  # 親衛隊長在 season21 開著、二十級探索第一段就撞見那個孩子（接管選單）：要測接管的自己打開
        for k, v in tuning.items():
            setattr(c.config.yiwen, k, v)
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="yiwen-")) / "tianxia.db")
    game = Game.new(c, name, rng=random.Random(0), world=world)
    game.client = None
    return ready(game, loc=place_of_kind(c, kind), level=20)


def place_of_kind(content, kind: str) -> str:
    """正式內容裡第一個是這一種的地點（照 core/explore_base 的分法）。"""
    from tianxia.core import explore_base

    for lid, loc in content.locations.items():
        if explore_base.kind_of(content.config.jianfa, loc).kind == kind:
            return lid
    raise AssertionError(f"沒有 {kind} 的地點")
