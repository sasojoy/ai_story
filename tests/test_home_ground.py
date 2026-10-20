"""主場（輿圖重製 1c，企劃者 2026-10-20「長社火攻照長社此刻歸誰定難易」；tianxia/home_ground.py、BattleDef.home）。

領地爭奪開著的季，長社火攻開集結那一刻看長社這一塊此刻歸誰：
- 黃巾佔著：波才坐鎮長社，龍頭上陣全額；戰局起點往黃巾偏 N。
- 官軍佔著：起點往官軍偏 N；波才遠道而來，上陣份量 × S。
- 還是中立：起點不偏，波才照常上陣。
三種都在開集結那一刻把波才調到長社（他開季站在黃巾的外圈）；被打退、退場的照舊不上陣。領地爭奪關著時三種季一個字都不變。"""
from __future__ import annotations

import pytest

from conftest import real_content
from conquest_kit import conquest_game, plain_game
from tianxia import battle_instance as bi
from tianxia import conquest, figures, generals, home_ground
from tianxia import world as world_mod
from tianxia.content import ContentError, validate
from tianxia.models import HomeGround

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

BATTLE = "changshe_fire"
START = 50


def _muster(game, holder: str | None = None, start: int = START, setup=None):
    """長社火攻開集結（同時刻表與管理者「立刻開這一場」走的 world._open_claimed），起點照 start；開之前把長社改成 holder 的（None 照舊）。"""
    c, world = game.content, game.world
    if holder is not None:
        world.mutate_season(lambda s: conquest.set_control(s, c, "changshe", holder))
    if setup is not None:
        world.mutate_season(setup)
    d = c.battles[BATTLE]
    msgs = world_mod._open_claimed(world, c, 0.0, lambda vehicle: (d, start))  # noqa: SLF001
    return d, msgs, world.get_battle(), world.get_season()


def _bocai(battle):
    return next((x for x in battle.commanders if x.fid == "bocai"), None)


def _where(game, season, fid="bocai"):
    return figures.state_of(world_mod._season_vehicle(game.content, season), game.content, fid).location  # noqa: SLF001


def test_changshe_fire_names_its_home_ground():
    d = real_content("season21").battles[BATTLE]
    assert d.home == HomeGround(block="changshe", figure="bocai")


def test_huang_holds_changshe_bocai_waits_inside():
    game = conquest_game("season21")
    n = game.content.config.conquest.home_shift
    d, msgs, battle, season = _muster(game, "huang")
    assert battle.trend_start == battle.trend == START - n  # 往黃巾（factions[1]）偏：戰局以官軍為正向
    assert battle.home == bi.HomeNote(holder="huang", shift=-n, figure="bocai")
    assert _where(game, season) == "changshe"
    neutral = conquest_game("season21")
    _, _, even, _ = _muster(neutral)
    assert _bocai(battle).score == _bocai(even).score  # 全額
    line = "長社火攻開集結：黃巾軍早已據長社，波才閉城以待。"
    assert any(line in m for m in msgs) and any(r.text == line for r in season.rumors)


def test_guan_holds_changshe_bocai_comes_from_afar():
    game = conquest_game("season21")
    cfg = game.content.config.conquest
    d, msgs, battle, season = _muster(game, "guan")
    assert battle.trend_start == battle.trend == START + cfg.home_shift
    assert battle.home == bi.HomeNote(holder="guan", shift=cfg.home_shift, figure="bocai")
    assert _where(game, season) == "changshe"
    neutral = conquest_game("season21")
    _, _, even, _ = _muster(neutral)
    assert _bocai(battle).score == pytest.approx(_bocai(even).score * cfg.home_away_share, abs=0.1)
    assert [x.score for x in battle.commanders if x.fid != "bocai"] == [x.score for x in even.commanders if x.fid != "bocai"]
    assert any("官軍早已據長社，波才遠道而來" in m for m in msgs)


def test_changshe_still_neutral_no_lean_bocai_comes_as_usual():
    game = conquest_game("season21")
    assert conquest.holder(game.state.world, game.content, "changshe") is None
    before = _where(game, game.world.get_season())
    assert before != "changshe"  # 他開季站在黃巾的外圈（1c 搬家）
    d, msgs, battle, season = _muster(game)
    assert battle.trend_start == battle.trend == START
    assert battle.home == bi.HomeNote(holder=conquest.NEUTRAL, shift=0, figure="bocai")
    assert _where(game, season) == "changshe"
    assert _bocai(battle) is not None and _bocai(battle).rank == 0
    assert any("長社還沒有人佔下，波才引兵趕到" in m for m in msgs)


def test_a_fallen_bocai_is_not_moved_and_does_not_fight():
    """被打退、退場的照現在的規則不上陣；起點照長社歸誰偏。"""
    game = conquest_game("season21")
    n = game.content.config.conquest.home_shift

    def retire(season):
        vehicle = world_mod._season_vehicle(game.content, season)  # noqa: SLF001
        figures._ensure(vehicle, game.content, "bocai").status = "retired"  # noqa: SLF001

    d, msgs, battle, season = _muster(game, "huang", setup=retire)
    assert battle.trend_start == START - n
    assert battle.home == bi.HomeNote(holder="huang", shift=-n, figure=None)
    assert _where(game, season) != "changshe" and _bocai(battle) is None
    assert any("長社火攻開集結：黃巾軍早已據長社。" in m for m in msgs)


def test_the_shift_never_pushes_the_start_into_a_decisive_finish():
    """夾在合理範圍：主場的偏移不把起點推進「一開打就壓倒性收場」那一帶（50±decisive_margin），已經在帶外的也不拉回來。"""
    game = conquest_game("season21")
    d = game.content.battles[BATTLE]
    _, _, battle, _ = _muster(game, "guan", start=88)
    assert battle.trend_start == 50 + d.decisive_margin - 1
    low = conquest_game("season21")
    _, _, battle, _ = _muster(low, "huang", start=12)
    assert battle.trend_start == 50 - d.decisive_margin + 1


def _stockpiled(holder, supply):
    game = conquest_game("season21")
    game.content.config.stockpile.enabled = True
    return _muster(game, holder, setup=lambda s: s.supply.update(supply))


def test_home_ground_and_stockpile_stack_within_eight():
    """企劃者 2026-10-20：主場優勢要「錦上添花」，不能幾乎決定勝負——PM 定主場與屯糧練兵的偏移合計夾在 ±8（home_stack_cap）以內：
    同方向疊加時才撞得到（主場 6 ＋ 屯糧最多 6）；反方向照加。天命之爭的偏移不在長社火攻。"""
    d, msgs, battle, season = _stockpiled("guan", {"guan": 20})  # 主場 +6、屯糧本來 +3（同 test_stamina_plays 的那一筆）
    assert battle.supply_lean == {"guan": 20, "huang": 0}
    assert battle.trend_start == battle.trend == START + 8
    assert any("早已據長社" in m for m in msgs) and any("起手往官軍偏了 2 點" in m for m in msgs)  # 屯糧那一句照夾過的寫
    _, _, most, _ = _stockpiled("guan", {"guan": 1000})  # +6 ＋ +6
    assert most.trend_start == START + 8
    _, _, other, _ = _stockpiled("huang", {"huang": 1000})  # 往黃巾：−6 ＋ −6
    assert other.trend_start == START - 8
    _, _, against, _ = _stockpiled("guan", {"huang": 1000})  # 反方向：+6 −6
    assert against.trend_start == START
    _, _, open_, _ = _stockpiled(None, {"guan": 1000})  # 長社中立：主場不偏，屯糧照舊 +6
    assert open_.trend_start == START + 6


def test_stack_only_trims_the_stockpile_part():
    c = real_content("season21")
    assert c.config.conquest.home_stack_cap == 8
    assert home_ground.stack(c, None, 6) == 6  # 沒有主場：一個字都不變
    assert home_ground.stack(c, bi.HomeNote(holder="guan", shift=6), 6) == 2
    assert home_ground.stack(c, bi.HomeNote(holder="guan", shift=6), -6) == -6
    assert home_ground.stack(c, bi.HomeNote(holder="huang", shift=-6), -3) == -2
    assert home_ground.stack(c, bi.HomeNote(holder="neutral", shift=0), 6) == 6
    assert home_ground.stack(c, bi.HomeNote(holder="guan", shift=10), 3) == 0  # 主場自己就超過（N 調大了）：不往回拉，只是不再加
    assert home_ground.stack(c, bi.HomeNote(holder="guan", shift=10), -3) == -3


def test_the_battle_screen_says_why():
    game = conquest_game("season21")
    n = game.content.config.conquest.home_shift
    d, _, battle, _ = _muster(game, "guan")
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert f"主場：長社此刻在官軍手裡，波才遠道而來，上陣的份量打了折；戰局起點往官軍偏了 {n} 點。" in scene
    held = conquest_game("season21")
    d, _, battle, _ = _muster(held, "huang")
    assert f"主場：長社此刻在黃巾軍手裡，波才坐鎮城中；戰局起點往黃巾軍偏了 {n} 點。" in held._battle_scene_text(battle, d)  # noqa: SLF001
    open_ = conquest_game("season21")
    d, _, battle, _ = _muster(open_)
    assert "主場：長社還沒有人佔下，波才引兵趕到；戰局起點不偏。" in open_._battle_scene_text(battle, d)  # noqa: SLF001


@pytest.mark.parametrize("profile", ["weekend", "season21", None])
def test_conquest_off_not_a_word_changes(profile):
    """領地爭奪關著（正式內容的預設）：三種季開長社火攻，跟長社火攻沒寫主場時一模一樣（起點、陣容、波才在哪、傳聞、訊息）。"""
    def run(with_home: bool):
        game = plain_game(profile)
        c = game.content
        if not with_home:
            c.battles[BATTLE] = c.battles[BATTLE].model_copy(update={"home": None})
        _, msgs, battle, season = _muster(game)
        return msgs, battle.model_dump(exclude={"muster_deadline_real"}), _where(game, season), [r.text for r in season.rumors]

    assert run(True) == run(False)
    msgs, battle, where, _ = run(True)
    assert battle["home"] is None and where != "changshe"


def test_weight_is_one_when_conquest_is_off_or_no_home():
    game = plain_game("season21")
    s = world_mod._season_vehicle(game.content, game.world.get_season())  # noqa: SLF001
    assert home_ground.weight(s, game.content, game.content.battles[BATTLE], "bocai") == 1.0
    on = conquest_game("season21")
    on.world.mutate_season(lambda w: conquest.set_control(w, on.content, "changshe", "guan"))
    s = world_mod._season_vehicle(on.content, on.world.get_season())  # noqa: SLF001
    assert home_ground.weight(s, on.content, on.content.battles[BATTLE], "bocai") == on.content.config.conquest.home_away_share
    assert home_ground.weight(s, on.content, on.content.battles[BATTLE], "huangfusong") == 1.0
    assert home_ground.weight(s, on.content, on.content.battles["guangzong"], "bocai") == 1.0
    rows = generals.pick(s, on.content, on.content.battles[BATTLE])
    assert any(r.fid == "bocai" for r in rows)


def test_content_checks_the_home_ground():
    c = real_content("season21")
    c.battles[BATTLE] = c.battles[BATTLE].model_copy(update={"home": HomeGround(block="mentor_hut", figure="bocai")})
    with pytest.raises(ContentError, match="主場"):
        validate(c)
    c = real_content("season21")
    c.battles[BATTLE] = c.battles[BATTLE].model_copy(update={"home": HomeGround(block="changshe", figure="nobody")})
    with pytest.raises(ContentError, match="主場"):
        validate(c)
    c = real_content("season21")
    c.figures["bocai"] = c.figures["bocai"].model_copy(update={"faction": "haoqiang"})
    c.battles[BATTLE] = c.battles[BATTLE].model_copy(update={"home": HomeGround(block="changshe", figure="bocai")})
    with pytest.raises(ContentError, match="主場"):
        validate(c)
