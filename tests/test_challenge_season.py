"""挑戰大勢人物每季都有（docs/superpowers/specs/2026-10-11-挑戰大勢人物每季都有-design.md）。正式內容、預設設定（14 天、第一季規則關著）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import real_content
from tianxia import figures, team
from tianxia.content import ContentError, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


def _player(content, store, name, faction, at, *, now=1000.0) -> Game:
    game = Game.new(content, name, rng=random.Random(0), world=store)
    p = game.state.player
    p.faction, p.location = faction, at
    p.tutorial_step = len(content.tutorial.steps)
    p.visited.add(at)
    game.now = now
    return game


def _ids(game):
    return [o.id for o in game.options()]


def _won(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=120))


def test_challenge_on_needs_figures_factions_and_the_switch(real, world):
    w = world.get_season()
    assert figures.challenge_on(real, w) and figures.untimed(real, w)
    real.config.figure_challenge_every_season = False
    assert not figures.challenge_on(real, w)
    real.config.season_one = True  # 第一季一定開（打擊軍令靠它交差），就算開關關著
    w.season_one = True
    assert figures.challenge_on(real, w) and not figures.untimed(real, w)


def test_a_fourteen_day_season_draws_the_challenge_buttons(real, world):
    cost = real.config.action_cost["train"]
    guan = _player(real, world, "官甲", "guan", "huangjin_camp")
    bocai = next(o for o in guan.options() if o.id == "act:challenge:bocai")
    assert bocai.enabled and bocai.label.startswith(f"挑戰波才（體力 {cost}・")
    assert figures.difficulty(guan.state, real, "bocai") == 120
    for name, faction, at in (("黃乙", "huang", "huangjin_camp"), ("散丙", None, "huangjin_camp"), ("官丁", "guan", "changshe")):
        assert not any(i.startswith("act:challenge:") for i in _ids(_player(real, world, name, faction, at))), name
    assert {"act:challenge:huangfusong", "act:challenge:zhujun"} <= set(_ids(_player(real, world, "豪戊", "haoqiang", "changshe")))
    assert "act:challenge:dongzhuo" not in _ids(_player(real, world, "黃己", "huang", "mengjin_ford"))  # 戰線空著：沒有時刻表的季不畫
    assert "act:challenge:zhaohong" not in _ids(_player(real, world, "官庚", "guan", "nanyang_huangjin_camp"))
    assert "act:challenge:hejin" in _ids(_player(real, world, "黃辛", "huang", "dajiangjun_fu"))  # challenge_off_front


def test_a_fourteen_day_win_takes_five_prestige_snubs_and_records_no_contribution(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    before = game.state.player.affinities.get("bocai", 0) + 10
    game.state.player.affinities["bocai"] = before
    with _won():
        game.choose("act:challenge:bocai")
    s = game.state
    assert figures.state_of(s, real, "bocai").prestige == 55
    assert s.player.affinities["bocai"] == before - real.config.figure_defeat_affinity
    assert s.player.figure_wins == {"bocai": 1} and not s.player.contrib
    assert set(world.get_season().figures) == {"bocai"}  # 第一次打贏才寫進存檔，其他人照人物表讀
    snubbed = next(o for o in game.options() if o.id == "act:challenge:bocai")
    assert not snubbed.enabled
    game.now += real.config.snub_hours * 3600
    assert next(o for o in game.options() if o.id == "act:challenge:bocai").enabled


def test_people_stand_at_their_talk_at_until_someone_retires(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    placed = figures.placed_characters(game.state, real)
    for fid, fig in real.figures.items():
        if fig.character is not None and fig.start_status == "active":
            assert placed[fig.character] == real.characters[fig.character].talk_at, fid
    real.config.figure_challenge_every_season = False
    assert figures.placed_characters(game.state, real) == {}


def test_a_retired_figure_leaves_the_audience_list(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    figures.defeat(game.state, real, "bocai", 60)
    assert figures.is_out(game.state, "bocai") and "bocai" not in game._figures_here()
    assert figures.state_of(game.state, real, "pengtuo").status == "active"  # 彭脫接手


def test_a_running_fourteen_day_season_gets_the_buttons_at_once(real, world):
    """上線那一刻（設計第六節情形一）：14 天的季已經走到第 8 週、存檔裡沒有人物，一同步就看得到挑戰鈕，人物照開季值。"""
    from tianxia import calendar
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    world.mutate_season(lambda s: setattr(s, "time", calendar.week_start(8, real, s)))
    game.sync(game.now)
    assert world.get_season().figures == {}
    assert next(o for o in game.options() if o.id == "act:challenge:bocai").enabled
    assert figures.state_of(game.state, real, "bocai").prestige == real.figures["bocai"].start_prestige


def test_figures_on_stage_must_start_where_they_are_met(real):
    real.figures["bocai"] = real.figures["bocai"].model_copy(update={"location": "changshe"})
    with pytest.raises(ContentError, match="talk_at"):
        validate(real)


def test_a_figure_loses_at_most_fifteen_a_game_day_but_the_win_still_pays(real, world):
    """甲 (d)：沒有時刻表的季每位人物每個遊戲日最多被打掉 figure_daily_loss_cap 點；額度用完之後打贏照拿獎勵、情誼照扣、照樣閉門不見，
    只是聲威不動，回話寫「部眾死守不退」；隔天額度回來，舊日子的 lost: 鍵清掉。"""
    s = _player(real, world, "官甲", "guan", "huangjin_camp").state
    for _ in range(3):
        figures.defeat(s, real, "bocai", 5, cap=15)
    assert figures.state_of(s, real, "bocai").prestige == 45
    assert figures.defeat(s, real, "bocai", 5, cap=15) == [figures.HELD_LINE.format(name="波才")]
    assert figures.state_of(s, real, "bocai").prestige == 45
    s.world.time += 86400
    figures.defeat(s, real, "bocai", 5, cap=15)
    assert figures.state_of(s, real, "bocai").prestige == 40
    assert [k for k in s.world.trend_accum if k.startswith("lost:bocai:")] == [f"lost:bocai:{int(s.world.time // 86400)}"]


def test_the_engine_passes_the_cap_only_without_a_timetable(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    real.config.snub_hours = 0
    with _won():
        for _ in range(4):
            game.choose("act:challenge:bocai")
    assert figures.state_of(game.state, real, "bocai").prestige == 45
    assert any(figures.HELD_LINE.format(name="波才") in line for e in game.state.journal for line in e.lines)


def test_prestige_creeps_back_one_point_a_calendar_day_up_to_the_start(real, world):
    """甲 (b)：沒有時刻表的季，被打下來的聲威每個季曆天回 figure_prestige_regen 點，回到開季值為止；退場的不回、
    沒被打過的不寫存檔、人物表沒有的 id 跳過；第一季不回。"""
    s = _player(real, world, "官甲", "guan", "huangjin_camp").state
    figures.defeat(s, real, "bocai", 10)
    s.world.figures["ghost"] = figures.FigureState(prestige=1, status="active")
    figures.recover(s, real, 12)
    assert figures.state_of(s, real, "bocai").prestige == 50
    figures.recover(s, real, 12)
    assert figures.state_of(s, real, "bocai").prestige == 51
    figures.recover(s, real, 24 * 30)
    assert figures.state_of(s, real, "bocai").prestige == real.figures["bocai"].start_prestige
    assert set(s.world.figures) == {"bocai", "ghost"} and s.world.figures["ghost"].prestige == 1
    figures.defeat(s, real, "zhangliang", 60)
    figures.recover(s, real, 24 * 30)
    assert figures.state_of(s, real, "zhangliang").prestige == 0


def test_recovery_over_one_long_step_matches_many_short_ones(real, world):
    a = _player(real, world, "官甲", "guan", "huangjin_camp").state
    b = a.model_copy(deep=True)
    for s in (a, b):
        figures.defeat(s, real, "bocai", 20)
    figures.recover(a, real, 24 * 5)
    for _ in range(24 * 5):
        figures.recover(b, real, 1)
    assert figures.state_of(a, real, "bocai").prestige == figures.state_of(b, real, "bocai").prestige == 45


def test_the_world_clock_drives_the_recovery_without_touching_the_game_dice(real, world):
    from tianxia.world import advance_world_state
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    figures.defeat(game.state, real, "bocai", 10)
    world.mutate_season(lambda w: w.figures.update(game.state.world.figures))
    before = game.rng.getstate()
    season = world.get_season()
    advance_world_state(season, real, 4 * 3600, random.Random(1), world)  # 14 天的季：一個季曆天是現實 4 小時
    assert season.figures["bocai"].prestige == 51 and game.rng.getstate() == before


def test_season_one_keeps_no_cap_and_no_recovery(real, world):
    real.config.season_one = True
    s = _player(real, world, "官甲", "guan", "huangjin_camp").state
    s.world.season_one = True
    figures.defeat(s, real, "bocai", 10)
    figures.recover(s, real, 24 * 30)
    assert figures.state_of(s, real, "bocai").prestige == 50


def _retire(game, fid):
    figures.defeat(game.state, game.content, fid, 100)
    game.world.mutate_season(lambda w: w.figures.update(game.state.world.figures))


def test_beating_bocai_out_marks_him_defeated_and_stops_his_sim_player(real, world):
    """丙 (c)：波才退場（14 天的季）記 bocai_defeated，kou_boss 不再是候選，波才虛擬玩家不再推黃巾聲勢；第一季打到退場不記。"""
    from tianxia.world import sim_active
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    real.config.figure_daily_loss_cap = 0
    real.config.snub_hours = 0
    with _won():
        for _ in range(12):
            game.choose("act:challenge:bocai")
    s = game.state
    assert figures.is_out(s, "bocai") and "bocai_defeated" in s.world.flags
    bocai = next(sim for sim in real.scenario.sim_players if sim.name == "波才")
    assert not sim_active(bocai, s, real)


def test_huangfusong_out_stops_his_pushes_and_leaves_the_map(real, world):
    from tianxia import atlas
    from tianxia.world import sim_active
    game = _player(real, world, "黃甲", "huang", "changshe")
    figures.defeat(game.state, real, "huangfusong", 100)
    s = game.state
    hfs = next(sim for sim in real.scenario.sim_players if sim.name == "皇甫嵩")
    assert not sim_active(hfs, s, real) and sim_active(hfs, s)  # 不給 content 的舊呼叫照舊
    assert "皇甫嵩" not in atlas.haunters(s, real, "changshe") and "皇甫嵩" not in atlas.haunters(s, real, "yingchuan")
    assert "act:challenge:zhujun" in _ids(_player(real, world, "黃乙", "huang", "changshe"))


def test_the_switch_off_brings_back_the_leaders_even_after_a_retirement(real, world):
    from tianxia import atlas
    from tianxia.world import sim_active
    game = _player(real, world, "黃甲", "huang", "changshe")
    figures.defeat(game.state, real, "huangfusong", 100)
    real.config.figure_challenge_every_season = False
    s = game.state
    hfs = next(sim for sim in real.scenario.sim_players if sim.name == "皇甫嵩")
    assert sim_active(hfs, s, real) and "皇甫嵩" in atlas.haunters(s, real, "changshe")
    assert figures.placed_characters(s, real) == {}


def test_season_one_records_no_out_flag(real, world):
    real.config.season_one = True
    world.mutate_season(lambda w: setattr(w, "season_one", True))  # 這一季蓋第一季的章
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    real.config.snub_hours = 0
    with _won():
        for _ in range(40):
            if figures.is_out(game.state, "bocai"):
                break
            game.choose("act:challenge:bocai")
    assert "bocai_defeated" not in game.state.world.flags


def test_a_new_season_brings_the_retired_back(real, world):
    from conftest import next_season
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    real.config.figure_daily_loss_cap = 0
    real.config.snub_hours = 0
    with _won():
        for _ in range(12):
            game.choose("act:challenge:bocai")
    next_season(real, world)
    w = world.get_season()
    assert w.figures == {} and "bocai_defeated" not in w.flags


def test_an_out_flag_nobody_reads_is_refused(real):
    real.figures["bocai"] = real.figures["bocai"].model_copy(update={"out_flag": "no_such_flag"})
    with pytest.raises(ContentError, match="out_flag"):
        validate(real)


def _tier3_count(state, content):
    return sum(n for mid, n in state.player.materials.items() if mid in content.materials and content.materials[mid].tier == 3)


def test_only_the_first_win_over_a_figure_gives_tier_three(real, world):
    """丁 (c)：這一季第一次打贏某位人物，保證一個三階（打造第二批的 _figure_tier3）＋預設表照擲；之後再打贏，預設表的三階那一擲
    照擲、擲中不給（Game.rng 的序列跟以前一樣），保證那一個也不給。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    real.config.snub_hours = 0
    real.config.figure_daily_loss_cap = 0
    with _won():
        game.choose("act:challenge:bocai")
    first = _tier3_count(game.state, real)
    assert first >= 1 and game.state.player.figure_rare_drops == first
    with _won(), mock.patch("tianxia.materials._default_rolls", return_value=[(3, 1.0)]):
        game.choose("act:challenge:bocai")
    assert _tier3_count(game.state, real) == first


def test_the_capped_tier_three_roll_still_uses_the_game_dice(real):
    from tianxia import materials
    squad = real.squads[real.figures["bocai"].squad]
    a, b = random.Random(5), random.Random(5)
    materials.roll_squad_drops(squad, real, a)
    materials.roll_squad_drops(squad, real, b, max_tier=2)
    assert a.getstate() == b.getstate()


def test_the_rare_cap_counts_across_a_defection(real, world):
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    game.state.player.figure_rare_drops = real.config.figure_rare_cap
    with _won():
        game.choose("act:challenge:bocai")
    assert _tier3_count(game.state, real) == 0  # 到上限：第一次打贏也不給
    game.state.player.faction = "huang"  # 叛投不清
    game.state.player.location = "changshe"
    with _won():
        game.choose("act:challenge:huangfusong")
    assert _tier3_count(game.state, real) == 0


def test_a_weakened_figure_pays_less_xinde_and_exp(real, world):
    """戊 (b)：心得、經驗乘「此刻難度 ÷ 開季難度」（夾在 1 以下）：波才聲威 0 時難度 75，80 × 75 ÷ 120 四捨五入是 50。"""
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    s = game.state
    figures._ensure(s, real, "bocai").prestige = 0
    xinde = s.player.stats.get("xinde", 0)
    with _won(), mock.patch.object(figures, "defeat", return_value=[]):
        game.choose("act:challenge:bocai")
    assert s.player.stats["xinde"] - xinde == 50
    assert figures.start_difficulty(real, "bocai") == 120


def test_challenge_treasures_stop_at_two_a_season(real, world):
    from tianxia import treasures
    real.config.treasures.enabled = True
    real.config.treasures.challenge_chance = 1.0
    s = _player(real, world, "官甲", "guan", "huangjin_camp").state
    s.player.treasure_drops = {"zhangjiao", "zhangbao"}
    assert treasures.challenge_drop(s, real, "bocai", 1, 99) == (None, [])


def _detail(game, loc):
    from tianxia import atlas
    game.state.player.visited.add(loc)
    return atlas.detail_text(game.state, game.content, loc, lambda squad_id: "")


def test_the_map_lists_the_figures_here_in_a_fourteen_day_season(real, world):
    """設計 3.8：沒有時刻表的季，龍頭人物那一段只有人物此刻就站在這裡才寫聲威、情誼；其餘站在這裡的大勢人物列在
    「此地的大勢人物」，戰線空著的寫「按兵不動」，聲威會回時寫「沒人去打……慢慢回來」。緊急開關關著時一個字都不變。"""
    from tianxia import atlas
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    camp = _detail(game, "huangjin_camp")
    assert "聲威 60" in camp and atlas.REGEN_NOTE in camp and atlas.HERE_TITLE not in camp  # 波才併在龍頭人物那一段
    nanyang = _detail(game, "nanyang_huangjin_camp")
    assert atlas.HERE_TITLE in nanyang and "張曼成" in nanyang and "趙弘" in nanyang and atlas.IDLE_NOTE in nanyang
    assert "沒有龍頭人物在此出沒" not in nanyang
    ford = _detail(game, "mengjin_ford")
    assert "董卓" in ford and atlas.IDLE_NOTE in ford and "沒有龍頭人物在此出沒" not in ford
    assert "聲威" not in atlas.leader_text(game.state, real, "皇甫嵩", "yingchuan")  # 人物站在長社，潁川那一段不寫聲威
    assert "聲威" in atlas.leader_text(game.state, real, "皇甫嵩", "changshe")
    real.config.figure_challenge_every_season = False
    off = _detail(game, "nanyang_huangjin_camp")
    assert atlas.HERE_TITLE not in off and "聲威" not in _detail(game, "huangjin_camp")


def test_the_howto_explains_challenges_in_a_fourteen_day_season(real, world):
    from tianxia import howto
    cfg = real.config
    page = howto.page(real, world.get_season(), recruitable=True)
    assert f"打贏大勢人物本人，他對你的情誼會掉 {cfg.figure_defeat_affinity}" in page
    assert howto.CHALLENGE_UNTIMED[0].format(n=cfg.figure_defeat_prestige) in page
    assert howto.CHALLENGE_UNTIMED[1].format(cap=cfg.figure_daily_loss_cap) in page
    assert "波才、皇甫嵩、董卓" in page
    cfg.figure_challenge_every_season = False
    assert "打贏大勢人物本人" not in howto.page(real, world.get_season(), recruitable=True)


def test_season_bots_pick_a_challenge_by_its_odds(real, world):
    """第九節：整季機器人隨機挑選時，挑戰鈕只在勝算「穩勝」「有把握」時留著（同假人）；火候滿了等契機時五五波以上也打。"""
    from tianxia import bot
    game = _player(real, world, "官甲", "guan", "huangjin_camp")
    options = [o for o in game.options(odds=False) if o.enabled]
    assert "act:challenge:bocai" in [o.id for o in options]
    with mock.patch.object(Game, "challenge_odds", return_value="五五波"):
        assert "act:challenge:bocai" not in [bot.pick(game, options, random.Random(i)) for i in range(80)]
        with mock.patch.object(bot, "awaits_chance", return_value=True):
            assert bot.pick(game, options, random.Random(0)) == "act:challenge:bocai"
    with mock.patch.object(Game, "challenge_odds", return_value="有把握"):
        assert "act:challenge:bocai" in [bot.pick(game, options, random.Random(i)) for i in range(80)]
    assert bot.CHALLENGE_ODDS == ("穩勝", "有把握")
