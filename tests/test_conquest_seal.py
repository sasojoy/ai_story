"""領地爭奪第三批 B（計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md Task 14，設計 3.9、4.8）：玉璽碎片藏在開季中立的區塊、
探索撿到。只動「碎片從哪裡來」：效果、傳承那一格、璽動、單挑、天命之季都照舊（test_seal*.py）。"""
from __future__ import annotations

import json

import pytest
from conquest_kit import _new, conquest_rules, go, join
from conftest import next_season, no_conquest, real_content
from jianfa_kit import no_jianfa

import server
from tianxia import atlas, conquest, explore_modes, library, seal
from tianxia import world as world_rules
from tianxia.world_state import SealCache, SealRegistry

pytestmark = pytest.mark.slow

NAME = "沈浪"


def _content(hide: float = 1.0, find: float = 1.0, profile: str = "season21"):
    """正式內容（21 天季）、領地爭奪打開；hide／find 是這一批的兩個機率（1.0＝一定藏、一定撿到，好測）。"""
    c = no_jianfa(conquest_rules(real_content(profile)))  # 這一份測探索三選一撿碎片（explore:*）；出門一趟撿碎片在 tests/test_explore_one.py
    c.config.seal.cache.hide_chance, c.config.seal.cache.find_chance = hide, find
    return c


def _game(hide: float = 1.0, find: float = 1.0, name: str = NAME, world=None, content=None):
    return _new(content or _content(hide, find), name, world)


def _cache(game) -> SealCache | None:
    return game.world.seal_state().registry.cache


def _reg(game) -> SealRegistry:
    return game.world.seal_state().registry


def _neutral(content) -> list[str]:
    return [loc for loc, block in conquest.blocks(content).items() if block.kind == "neutral"]


def _stand(game, loc_id: str, faction: str | None = None):
    join(game, faction)
    go(game, loc_id)
    return game


def _mode_for(game, mode: str) -> str:
    """explore_modes 的四種：找素材有分支層時要指一條分支（不然只回 GATHER_PICK、不花體力）。"""
    if mode != "gather":
        return mode
    loc = game.content.locations[game.state.player.location]
    layers = explore_modes.layered(game.content, game.state.world, loc)
    return f"gather:{layers[0].id}" if layers else "gather"


def _move_cache(game, loc_id: str) -> None:
    game.world.mutate(lambda st: setattr(st.seal.cache, "loc", loc_id))


# ── 藏 ──────────────────────────────────────────────


def test_hide_is_deterministic_with_salt_and_only_neutral_spots():
    """開季那一刻：同一份密鹽＋天機＋季數藏在同一個地方；只藏在開季中立的區塊；不同的密鹽藏在不同的地方（不只一處）。"""
    c = _content()
    g1, g2 = _game(content=_content()), _game(content=_content())
    a, b = _cache(g1), _cache(g2)
    assert a is not None and a == b  # 測試沒有密鹽：同樣的種子同樣的結果
    neutral = set(_neutral(c))
    assert a.loc in neutral and a.shard in c.seal and a.season == 1
    spots = seal.hide_spots(c, g1.state.world)
    assert {loc for loc, _ in spots} == neutral
    seen = set()
    for i in range(80):
        reg = seal.filled(SealRegistry(salt=f"鹽{i}"), c)
        cache = seal.hide(reg, c, 1, 0, spots)
        assert cache is not None and cache.loc in neutral
        assert cache == seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, spots)
        seen.add(cache.loc)
    assert len(seen) >= 4  # 十處左右的中立地都有可能


def test_hide_chance_gates_the_whole_season():
    """開季先擲 hide_chance：0 一片都不藏、1 一定藏；0.4 時大約四成的季有一片藏著。"""
    c = _content()
    spots = seal.hide_spots(c, _game(content=_content()).state.world)

    def hidden(chance: float, n: int = 400) -> int:
        c.config.seal.cache.hide_chance = chance
        return sum(seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, spots) is not None for i in range(n))

    assert hidden(0.0) == 0 and hidden(1.0) == 400
    assert 0.32 < hidden(0.4) / 400 < 0.48
    assert _cache(_game(hide=0.0)) is None


def test_hide_skips_when_nothing_is_left_to_hide():
    """這一輪七片都現世過、不在「未現世」了：沒有可藏的；這一季已經現世過一片也不再藏。"""
    c = _content()
    spots = seal.hide_spots(c, _game(content=_content()).state.world)
    reg = seal.filled(SealRegistry(), c)
    for shard in reg.shards.values():
        shard.state = "sunk"
    assert seal.hide(reg, c, 1, 0, spots) is None
    reg = seal.filled(SealRegistry(emerge_season=1), c)
    assert seal.hide(reg, c, 1, 0, spots) is None


def test_core_regions_weigh_more_and_the_default_names_the_core_region():
    """核心加權（輿圖簡化設計 3.1，企劃者定「核心的機率最高」）：地點落在 core_regions 的大區，權重是 core_weight，其餘 1。
    預設的大區 id 是 "core"（新地理的核心自成一區）；今天的地圖沒有這一區，所以全是 1。"""
    c = _content()
    cfg = c.config.seal.cache
    assert cfg.core_regions == ["core"] and cfg.core_weight > 1
    world = _game(content=_content()).state.world
    assert {w for _, w in seal.hide_spots(c, world)} == {1.0}  # 今天的地圖沒有 core 這一區
    loc = _neutral(c)[0]
    cfg.core_regions, cfg.core_weight = [atlas.region_of(c, loc).id], 9.0
    weights = dict(seal.hide_spots(c, world))
    heavy = {l for l in weights if atlas.region_of(c, l).id == cfg.core_regions[0]}
    assert heavy and all(weights[l] == 9.0 for l in heavy) and all(w == 1.0 for l, w in weights.items() if l not in heavy)
    picked = [seal.hide(seal.filled(SealRegistry(salt=f"鹽{i}"), c), c, 1, 0, list(weights.items())).loc for i in range(600)]
    share = sum(p in heavy for p in picked) / 600
    want = 9.0 * len(heavy) / (9.0 * len(heavy) + len(weights) - len(heavy))
    assert abs(share - want) < 0.07


def test_no_cache_when_the_switch_is_off_or_the_season_is_not_conquest():
    """領地爭奪沒開（沒有蓋章）：什麼都不藏，宛城照舊擲現世。"""
    c = no_conquest(real_content("weekend"))  # PM 2026-10-22 起正式內容打開，沒蓋章的季要明講關掉
    c.config.seal.cache.hide_chance = 1.0
    game = _new(c, NAME)
    assert _cache(game) is None
    off = _content()
    off.config.seal.enabled = False  # 主機關掉碎片
    assert _cache(_game(content=off)) is None


def test_a_new_season_clears_the_old_cache_and_hides_again():
    """上一季沒撿到的清掉；新的一季照 hide_chance 重擲（季數記在藏處上）。"""
    c = _content(find=0.0)
    game = _game(content=c)
    assert _cache(game).season == 1
    next_season(c, game.world)
    assert _cache(game).season == 2 and _reg(game).emerge_season is None
    c.config.seal.cache.hide_chance = 0.0
    next_season(c, game.world)
    assert _cache(game) is None


def test_the_mandate_season_hides_nothing_and_the_one_after_hides_again():
    """天命之季（七片都現世過）不藏；再下一季七片散去，照常藏。"""
    c = _content(find=0.0)
    game = _game(content=c)

    def _all_emerged(st):
        reg = seal.filled(st.seal, c)
        for shard in reg.shards.values():
            shard.state, shard.emerged_round = "sunk", reg.round
        reg.shards["chishou"].state = "hidden"  # 現世過卻回到未現世（管理者收回）：還有一片可藏，不藏是因為天命之季，不是因為沒東西可藏

    game.world.mutate(_all_emerged)
    next_season(c, game.world)
    assert game.world.get_season().mandate and _cache(game) is None
    next_season(c, game.world)
    assert not game.world.get_season().mandate and _cache(game) is not None and _cache(game).season == 3


# ── 撿 ──────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["gather", "seek", "sense", "practice"])
def test_find_only_at_the_cache_and_all_four_explore_modes_roll(mode):
    """只在藏碎片的那一塊擲；探索的四種（找素材、找事件、靜心感悟、練功，計畫第八章裁決 13）都擲。別處探索一百次也撿不到。"""
    game = _game()
    cache = _cache(game)
    away = next(loc for loc in _neutral(game.content) if loc != cache.loc)
    _stand(game, away)
    for _ in range(6):
        game._explore_mode(_mode_for(game, mode))
        game.state.player.stamina = 250.0
    assert seal.shard_of(_reg(game), NAME) is None and _cache(game) == cache  # 沒藏碎片的塊：不擲、藏處紋風不動
    go(game, cache.loc)
    game._explore_mode(_mode_for(game, mode))
    reg = _reg(game)
    shard = seal.shard_of(reg, NAME)
    assert shard is not None and shard.id == cache.shard and shard.since_season == 1 and shard.emerged_round == reg.round
    assert reg.cache is None and reg.emerge_season == 1
    event = reg.history[-1]
    assert (event.kind, event.shard, event.holder, event.record, event.where) == ("emerge", cache.shard, NAME, None, "")


def test_the_finder_gets_the_heirloom_and_learns_the_emerge_skill():
    """撿到的人：傳承那一格、同一季補送時學會混元一氣（Config.seal.emerge_skill，原本跟宛城現世的得主一起送）、紀錄一則、行狀一筆。"""
    game = _game()
    _stand(game, _cache(game).loc)
    assert "hunyuan" not in library.owned_arts(game.state)
    game.choose(f"explore:{_mode_for(game, 'seek')}")
    p = game.state.player
    assert p.heirloom is not None and p.heirloom.template == seal.shard_of(_reg(game), NAME).id
    assert "hunyuan" in library.owned_arts(game.state)
    titles = [e.title for e in game.state.journal]
    assert seal.SEAL_TITLE in titles


def test_one_shard_per_season_and_nobody_else_finds_it():
    """撿走了就沒了：同一塊再探索一百次也不會有第二片；這一季不會再藏。"""
    game = _game()
    loc = _cache(game).loc
    _stand(game, loc)
    game._explore_mode(_mode_for(game, "seek"))
    other = _new(game.content, "旁人", game.world)
    _stand(other, loc)
    for _ in range(5):
        other._explore_mode(_mode_for(other, "seek"))
        other.state.player.stamina = 250.0
    assert seal.shard_of(_reg(other), "旁人") is None
    assert len(seal.holders(_reg(other))) == 1 and _cache(other) is None


def test_someone_who_already_holds_a_shard_does_not_find_a_second():
    """一人一片：手上有碎片的人在藏處探索不擲，藏處留給別人。"""
    game = _game()
    cache = _cache(game)
    held = next(s for s in game.content.seal if s != cache.shard)

    def _hold(st):
        shard = st.seal.shards[held]
        shard.state, shard.holder = "held", NAME

    game.world.mutate(_hold)
    _stand(game, cache.loc)
    game._explore_mode(_mode_for(game, "seek"))
    assert _cache(game) == cache and seal.shard_of(_reg(game), NAME).id == held


def test_no_find_while_the_block_is_cooling():
    """翻地與爭搶（輿圖簡化設計 4.1；翻地計畫第一節第 9 條）：剛易手、還在冷卻的那一塊加成暫停，碎片也不擲（藏處紋風不動）；冷卻過了照擲。"""
    game = _game()
    cache = _cache(game)
    _stand(game, cache.loc, "guan")
    w, c = game.state.world, game.content
    conquest.flip(w, c, cache.loc, "guan")  # 官軍剛拿下：冷卻 cooldown_minutes
    game._save_season()
    assert conquest.cooling(game.state.world, c, cache.loc)
    for _ in range(3):
        game._explore_mode(_mode_for(game, "seek"))
        game.state.player.stamina = 250.0
    assert conquest.cooling(game.state.world, c, cache.loc)
    assert seal.shard_of(_reg(game), NAME) is None and _cache(game) == cache  # 修前冷卻期照擲（find_chance 1.0：一定撿到）
    fight = game.state.world.conquest.fights[cache.loc]
    fight.flipped_at -= conquest._seconds(c, c.config.conquest.cooldown_minutes) + 1  # 冷卻過了
    game._save_season()
    game._explore_mode(_mode_for(game, "seek"))
    assert seal.shard_of(_reg(game), NAME) is not None


def test_find_is_not_rolled_when_the_season_is_not_conquest():
    """領地爭奪沒開的季：探索照舊，不碰登記（也沒有藏處可言）。"""
    c = no_conquest(real_content("weekend"))  # PM 2026-10-22 起正式內容打開，沒蓋章的季要明講關掉
    c.config.seal.cache.hide_chance = c.config.seal.cache.find_chance = 1.0
    game = _new(c, NAME)
    cache = SealCache(season=1, shard="chishou", loc=_neutral(_content())[0])  # 硬塞一個：不算數
    game.world.mutate(lambda st: setattr(st.seal, "cache", cache))
    _stand(game, cache.loc)
    game._explore_mode(_mode_for(game, "seek"))
    assert seal.shard_of(_reg(game), NAME) is None


def test_the_find_roll_scales_for_the_holding_side(monkeypatch):
    """那一塊此刻歸你的陣營，機率再高一點（設計 3.9）：own_scale。純機率驗一次、再驗 Game 傳給 seal.find 的 own 旗標。"""
    cfg = _content().config.seal
    cfg.cache.find_chance, cfg.cache.own_scale = 0.4, 2.0
    reg = SealRegistry(salt="鹽")
    plain = sum(seal.find(reg, 0, "甲", n, False, cfg) for n in range(2000)) / 2000
    own = sum(seal.find(reg, 0, "甲", n, True, cfg) for n in range(2000)) / 2000
    assert 0.35 < plain < 0.45 and 0.75 < own < 0.85
    assert seal.find(reg, 0, "甲", 1, True, _content(find=0.9).config.seal) in (True, False)  # 上限夾在 1：不會炸

    game = _game(find=0.0)
    loc = _cache(game).loc
    calls = []
    monkeypatch.setattr(seal, "find", lambda reg_, tianji, name, seq, own_, cfg_: calls.append(own_) or False)
    _stand(game, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔的中立地：不算自家
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 官軍佔下了：官軍的人算自家
    game.state.player.faction = "huang"
    game._explore_mode(_mode_for(game, "seek"))  # 黃巾的人在官軍佔的地方：不算
    assert calls == [False, True, False]


def test_a_gentry_follower_gets_the_scale_on_the_side_he_follows_and_a_ranger_never_does(monkeypatch):
    """FB-571（PM 裁決）：豪強依附一軍，那一軍佔著的藏處算他的自家（照 rules.side_of，同療傷、打造、買馬的地盤折扣）；散人沒有自家、不乘
    ——沒人佔的藏處控制方是 None、散人的 side 也是 None，不能被 None == None 騙成「自家」。"""
    game = _game(find=0.0)
    loc = _cache(game).loc
    calls = []
    monkeypatch.setattr(seal, "find", lambda reg_, tianji, name, seq, own_, cfg_: calls.append(own_) or False)
    _stand(game, loc, "haoqiang")
    p = game.state.player
    assert game.state.world.haoqiang_allied
    p.ally = "guan"
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔：不算
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))  # 他依附的官軍佔下了：算自家
    conquest.set_control(game.state.world, game.content, loc, "huang")
    game._explore_mode(_mode_for(game, "seek"))  # 另一軍佔著：不算
    p.ally = "huang"
    game._explore_mode(_mode_for(game, "seek"))  # 改依附黃巾：算
    assert calls == [False, True, False, True]
    calls.clear()
    p.faction, p.ally = None, None  # 散人
    conquest.set_control(game.state.world, game.content, loc, None)
    game._explore_mode(_mode_for(game, "seek"))  # 沒人佔（控制方 None）：散人也不算
    conquest.set_control(game.state.world, game.content, loc, "guan")
    game._explore_mode(_mode_for(game, "seek"))
    assert calls == [False, False]


def test_the_find_dice_never_touch_game_rng():
    """擲骰用密鹽的亂數，不碰 Game.rng：整季測試與量表的序列不位移。"""
    game = _game(find=0.0)
    _stand(game, _cache(game).loc)
    before = game.rng.getstate()
    game._seal_find(game.state.player.location)
    assert game.rng.getstate() == before


def _admin_game(hide: float = 1.0, find: float = 1.0):
    c = _content(hide, find)
    c.config.admins = [NAME]
    return _game(content=c)


def test_stamping_the_mandate_mid_season_clears_the_cache():
    """FB-570：管理者在這一季「立刻蓋天命之季的章」，藏著的那一片當場清掉（跟自然換季那條路一樣：天命之季不藏），天命之季裡探索撿不到；
    登記上那一片還是未現世。"""
    game = _admin_game()
    cache = _cache(game)
    assert cache is not None
    out = game.admin_seal_mandate("now")
    assert game.world.get_season().mandate and any("天命之季" in line for line in out)
    assert _cache(game) is None
    _stand(game, cache.loc)
    game._explore_mode(_mode_for(game, "seek"))
    reg = _reg(game)
    assert seal.shard_of(reg, NAME) is None and reg.shards[cache.shard].state == "hidden" and reg.emerge_season is None


def test_a_cache_left_in_a_mandate_season_is_not_live():
    """FB-570：就算登記上留著一個藏處（舊資料、別的路徑蓋章），天命之季也當它不存在。"""
    c = _content()
    reg = seal.filled(SealRegistry(), c)
    reg.cache = SealCache(season=3, shard="chishou", loc=_neutral(c)[0])
    assert seal.live_cache(reg, 3) is reg.cache
    reg.mandate_season = 3
    assert seal.live_cache(reg, 3) is None
    spots = seal.hide_spots(c, _game(content=_content()).state.world)
    assert seal.hide(reg, c, 3, 0, spots, force=True) is None


def test_hide_now_says_no_in_a_mandate_season():
    """FB-570：天命之季裡按「現在藏一片」回一句不藏的話，不登記藏處（自然換季天命之季本來就不藏）。"""
    game = _admin_game(hide=0.0, find=1.0)
    assert _cache(game) is None
    game.admin_seal_mandate("now")
    out = game.admin_seal_emerge("guixin")
    assert _cache(game) is None and any(seal.HIDE_MANDATE in line for line in out)
    assert "天命之季" in seal.HIDE_MANDATE


# ── 不漏 ────────────────────────────────────────────


def _snapshot(game) -> dict:
    """玩家與其他人從任何地方看得到的東西：江湖頁／狀態列（/api/main）、江湖史、傳聞、管理者的玉璽那一組。"""
    season = game.world.get_season()
    return {
        "main": json.dumps(server.main_view(game), ensure_ascii=False, sort_keys=True, default=str),
        "chronicle": game.chronicle_text(),
        "rumors": [(r.layer, r.text) for r in season.rumors],
        "history": [(r.text) for r in season.chronicle],
        "admin": json.dumps(game.admin_seal_choices(), ensure_ascii=False, sort_keys=True, default=str),
    }


def test_the_hiding_place_is_not_observable_from_outside():
    """藏在哪裡不公開（計畫 Task 14）：兩個世界一模一樣、只有碎片藏的地方不同，畫面、API、江湖史、傳聞、管理者的玉璽那一組都一個字
    不差；在藏處探索沒擲中的那一下，玩家的狀態也一個字不差（江湖紀錄、亂數）。"""
    a, b = _game(find=0.0), _game(find=0.0)
    spots = _neutral(a.content)
    here, there = spots[0], spots[-1]
    _move_cache(a, here)
    _move_cache(b, there)
    assert _snapshot(a) == _snapshot(b)
    for game in (a, b):
        _stand(game, here)
        game.choose(f"explore:{_mode_for(game, 'seek')}")
    assert _snapshot(a) == _snapshot(b)
    assert a.state.player.model_dump_json() == b.state.player.model_dump_json()
    assert a.rng.getstate() == b.rng.getstate()


def test_the_find_is_announced_without_naming_the_place():
    """撿到的那一句天下大事與江湖史、補送的紀錄都不寫是在哪一塊撿到的。"""
    game = _game()
    loc = _cache(game).loc
    place = game.content.locations[loc].name
    _stand(game, loc)
    game._explore_mode(_mode_for(game, "seek"))
    season = game.world.get_season()
    said = [r.text for r in season.rumors if r.layer == "world"] + [r.text for r in season.chronicle] + [game.chronicle_text()]
    assert any(NAME in line and "傳國玉璽" in line for line in said)
    assert not any(place in line or loc in line for line in said)
    assert not any(place in line for e in game.state.journal if e.title == seal.SEAL_TITLE for line in e.lines)


# ── 宛城、管理者 ────────────────────────────────────


def _muster_wancheng(content):
    game = _new(content, NAME)
    game.world.mutate(lambda st: setattr(seal.filled(st.seal, content), "force_emerge", "yunzhuan"))
    world_rules.open_showdown(game.world, content, "wancheng", 0.0)
    return game, game.world.get_battle()


def test_wancheng_does_not_emerge_under_conquest_but_still_does_without_it():
    """領地爭奪的季不擲宛城現世（碎片只從探索來）；璽動照舊。沒蓋章的季宛城照舊擲，一個字不變。"""
    c = _content(hide=0.0)
    c.config.seal.emerge_chance = 1.0
    game, battle = _muster_wancheng(c)
    assert battle is not None and battle.seal_emerge is None
    assert seal.EMERGE_OMEN.format(battle="宛城之戰") not in [r.text for r in game.world.get_season().rumors]
    assert _reg(game).force_emerge == "yunzhuan"  # 管理者的記號留著，不吃掉
    plain = no_conquest(real_content("season21"))  # PM 2026-10-22 起正式內容打開，沒蓋章的季要明講關掉
    plain.config.seal.emerge_chance = 1.0
    _, battle = _muster_wancheng(plain)
    assert battle is not None and battle.seal_emerge == "yunzhuan"


def test_the_admin_hides_one_now_under_conquest_and_still_forces_emergence_otherwise():
    """管理者「強制現世」在領地爭奪的季改成「現在藏一片」：略過 hide_chance，可指定哪一片；回話不寫藏在哪；已經藏著、這一季已經現世過
    都不再藏。沒蓋章的季照舊設 force_emerge。"""
    c = _content(hide=0.0, find=0.0)
    c.config.admins = [NAME]
    game = _game(content=c)
    assert _cache(game) is None and game.admin_seal_choices()["hide"] is True
    out = game.admin_seal_emerge("guixin")
    cache = _cache(game)
    assert cache is not None and cache.shard == "guixin" and cache.season == 1 and cache.loc in _neutral(c)
    assert not any(cache.loc in line or c.locations[cache.loc].name in line for line in out)
    assert any("已經藏著" in line for line in game.admin_seal_emerge())  # 再按一次：不換地方
    assert _cache(game) == cache and _reg(game).force_emerge is None
    assert any("沒有這一片" in line for line in game.admin_seal_emerge("沒有"))
    game.world.mutate(lambda st: setattr(st.seal, "cache", None))
    game.world.mutate(lambda st: setattr(st.seal, "emerge_season", 1))
    assert any("這一季" in line for line in game.admin_seal_emerge())
    assert _cache(game) is None

    old = no_conquest(real_content("weekend"))  # PM 2026-10-22 起正式內容打開，沒蓋章的季要明講關掉
    old.config.admins = [NAME]
    legacy = _new(old, NAME)
    assert legacy.admin_seal_choices()["hide"] is False
    legacy.admin_seal_emerge("guixin")
    assert _reg(legacy).force_emerge == "guixin" and _cache(legacy) is None


def test_the_howto_says_where_shards_come_from_without_saying_where():
    """玩法說明「地盤」：碎片只在開季中立的地方、探索才撿得到（設計 3.9，玩家看得出為什麼要搶這一塊）；不寫是哪一塊。碎片關著不寫。"""
    from tianxia import howto

    c = _content()
    lines = [line for line in howto.conquest_lines(c) if "碎片" in line]
    assert len(lines) == 1 and "探索" in lines[0] and "沒人知道" in lines[0]
    assert not any(c.locations[loc].name in lines[0] for loc in _neutral(c))
    c.config.seal.enabled = False
    assert not any("碎片" in line for line in howto.conquest_lines(c))
