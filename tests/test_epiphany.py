"""特殊頓悟（tianxia/epiphany.py；企劃者 2026-10-26 設計稿）：擲中感悟時再擲、機率與保底；中了開一條頓悟的線，
拷問→小試→心魔（打自己的影子、輸了隔一日再打、次數不限）→挑模板→取名（三個候選或自己寫，全服不重複）→收進意境（神品）；
神品不能揣摩、合成、熔，身上只准裝一個；關著時不擲、存檔不多鍵。用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import arts, epiphany, fusion, insight_fx, library, storyline, team
from tianxia.encounter import EncounterResult
from tianxia.rules import day_seconds
from tianxia.state import InsightFx

pytestmark = pytest.mark.slow

HERE = "yingshui"


def _game(**rules):
    game = ready(jianfa_game(), side="guan", loc=HERE)
    game.content.config.epiphany.enabled = True
    for key, value in rules.items():
        setattr(game.content.config.epiphany, key, value)
    return game


def _win():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40))


def _loss():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="落敗", margin=-50, our_power=40, difficulty=200))


def _begin(game, trial: str = "wait"):
    with mock.patch.object(epiphany, "_trial", return_value=(trial, epiphany.TRIALS[trial][0], -1)):
        return game._epiphany_begin("剛", "潁水河畔")


def _answer_all(game, pick: int = 0) -> None:
    line = next(iter(game.state.player.storylines))
    for _ in range(epiphany.ASKED + 1):
        game.choose(f"{storyline.OPTION}:{line}:a{pick}")


def _through_demon(game) -> str:
    """拷問全選第一個（型都是攻）、靜候一日、打贏心魔：回線的 id。"""
    s = game.state
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(game.content, s.world)
    game._story_tick()
    assert s.player.storylines[line].stage == "demon"
    with _win():
        game.choose(f"{storyline.OPTION}:{line}")
    game._story_tick()
    return line


def _think(game) -> None:
    game.choose(f"{epiphany.OPTION}:{epiphany.THINK}")


def test_chances_halve_scale_with_wit_and_stop_at_the_season_cap():
    game = _game()
    s, c = game.state, game.content
    s.player.stats["wis"] = 5
    assert epiphany.chance(s, c) == pytest.approx(0.03)
    s.player.stats["wis"] = 7
    assert epiphany.chance(s, c) == pytest.approx(0.03 * 1.05 ** 2)
    s.player.stats["wis"] = 15
    assert epiphany.chance(s, c) == pytest.approx(0.03 * 1.5)  # 最多乘 1.5
    s.player.stats["wis"] = 5
    s.player.epiphanies = 1
    assert epiphany.chance(s, c) == pytest.approx(0.015)
    s.player.epiphanies = 3
    assert epiphany.chance(s, c) == 0


def test_roll_counts_dry_hits_and_the_first_one_has_a_pity():
    game = _game(pity=2)
    s, c = game.state, game.content
    never = mock.Mock(random=mock.Mock(return_value=0.99))
    assert not epiphany.roll(s, c, never) and not epiphany.roll(s, c, never)
    assert s.player.epiphany_dry == 2
    assert epiphany.roll(s, c, never)  # 保底
    s.player.epiphanies, s.player.epiphany_dry = 1, 5
    assert not epiphany.roll(s, c, never)  # 保底只管第一次


def test_the_season_profiles_turn_it_on():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    assert game.content.config.epiphany.enabled and epiphany.on(game.content, game.state)


def test_off_means_no_roll_and_no_new_save_keys():
    game = ready(jianfa_game(), side="guan", loc=HERE)
    game.content.config.epiphany.enabled = False
    rng = mock.Mock(random=mock.Mock(return_value=0.0))
    assert not epiphany.roll(game.state, game.content, rng)
    rng.random.assert_not_called()
    dumped = game.state.player.model_dump()
    assert not {"epiphanies", "epiphany_dry", "god_naming"} & set(dumped)


def test_a_hit_on_sensing_opens_the_line_and_asks_the_first_question():
    game = _game()
    s = game.state
    msgs = _begin(game)
    assert any(epiphany.TITLE in m for m in msgs)
    assert s.player.epiphanies == 1 and s.player.sensing is None
    line = next(iter(s.player.storylines))
    assert s.player.story_open == line
    assert len(game.options()) == 5  # 四個答案＋先擱著
    assert epiphany.busy(s, game.content)


def test_the_whole_way_through_names_and_grants_a_god_insight():
    game = _game()
    s, c = game.state, game.content
    line = _through_demon(game)
    assert s.player.storylines[line].ending == "done"
    naming = s.player.god_naming
    assert naming is not None and not naming.candidates and not naming.asked
    assert [o.id for o in game.options()] == [f"{epiphany.OPTION}:{epiphany.THINK}", f"{epiphany.OPTION}:{epiphany.OWN}"]
    assert game.choose(f"{epiphany.OPTION}:0") == ["（此刻無法這麼做。）"]  # 還沒想過名字，沒有候選可挑
    _think(game)
    assert naming.asked and len(naming.candidates) == 3
    god = next(g for g in c.traits.god if g.id == naming.god)
    assert god.form == "攻"  # 三題都選了攻（+6），小試是心（+1），心魔贏了再加一型（+2）：攻還是最多
    options = [o.id for o in game.options()]
    assert options == [f"{epiphany.OPTION}:0", f"{epiphany.OPTION}:1", f"{epiphany.OPTION}:2", f"{epiphany.OPTION}:{epiphany.OWN}"]
    name = naming.candidates[1]
    msgs = game.choose(f"{epiphany.OPTION}:1")
    assert any(name in m for m in msgs)
    own = next(i for i in s.player.own_insights.values() if i.name == name)
    fx = s.player.insight_fx[own.id]
    assert fx.grand == god.id and fx.general == {god.general: 3}
    assert insight_fx.look(fx) == "神" and insight_fx.is_god(s, own.id)
    assert s.player.god_naming is None and not epiphany.busy(s, c)
    assert game.world.get_season().god_names[name] == s.player.name
    assert game.world.get_season().god_firsts[god.id] == f"{name}|{s.player.name}"


def test_own_name_is_checked_and_unique_across_the_server():
    game = _game()
    s = game.state
    _through_demon(game)
    assert game.choose(f"{epiphany.OPTION}:{epiphany.OWN}") == [epiphany.NAME_OWN_ASK]
    game.world.mutate_season(lambda w: w.god_names.update({"斷水流雲": "別人"}))
    assert game.choose(f"{epiphany.OPTION}:{epiphany.OWN}", text="斷水流雲") == [epiphany.NAME_TAKEN]
    game.choose(f"{epiphany.OPTION}:{epiphany.OWN}", text="寒江獨照")
    assert any(i.name == "寒江獨照" for i in s.player.own_insights.values())


def test_losing_to_the_demon_waits_a_day_and_never_ends_the_line():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(c, s.world)
    game._story_tick()
    for _ in range(4):
        with _loss():
            game.choose(f"{storyline.OPTION}:{line}")
        progress = s.player.storylines[line]
        assert progress.ending is None and progress.stage == "demon"
        assert not next(o for o in game.options() if o.id == f"{storyline.OPTION}:{line}").enabled
        s.world.time = progress.retry_at
    with _win():
        game.choose(f"{storyline.OPTION}:{line}")
    game._story_tick()
    assert s.player.god_naming is not None


def test_the_demon_is_your_own_shadow():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    stage = epiphany.storyline.definition(c, s.player.storylines[line]).stage("demon")
    squad = game._mirror_squad(s.player.storylines[line], stage)
    power = team.power_vs(s, c, game.world, squad.model_copy(update={"difficulty": 1.0}), fresh=True, terrain=False, seal=False)
    assert squad.name == "心魔" and squad.difficulty == pytest.approx(round(power * c.config.epiphany.demon_scale, 1), abs=0.11)


def test_path_follows_method_and_shape_and_the_righteous_road_needs_good_name():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    progress = next(iter(s.player.storylines.values()))
    progress.marks.update({"形快": 1})  # 剛＋快 → 陽
    assert epiphany.path_of(s, c, progress) == ("陽", "無")
    progress.marks["正"] = 2
    assert epiphany.path_of(s, c, progress) == ("陽", "無")  # 善名不夠
    s.player.stats["good"] = c.insights["haoran"].grant.at
    assert epiphany.path_of(s, c, progress) == ("陽", "正")


def test_pick_skips_a_template_you_already_hold():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    progress = next(iter(s.player.storylines.values()))
    progress.marks.update({"形剛": 1, "攻": 6, "守": 2})
    first = epiphany.pick(s, c, progress)
    assert (first.attribute, first.form) == ("剛", "攻")
    s.player.insight_fx["悟:99"] = InsightFx(quality="上品", grand=first.id)
    assert epiphany.pick(s, c, progress).form == "守"


def test_god_insights_cannot_be_merged_melted_or_stacked_in_slots():
    game = _game()
    s, c, w = game.state, game.content, game.world
    _through_demon(game)
    _think(game)
    game.choose(f"{epiphany.OPTION}:0")
    god_id = next(i for i in s.player.insights if insight_fx.is_god(s, i))
    other = next(i for i in s.player.insights if i != god_id) if len(s.player.insights) > 1 else None
    if other is not None:
        assert fusion.merge_problem(s, c, w, god_id, other) == fusion._refuse(fusion.GOD_KEPT, "神品")
    assert library.melt_insight_problem(s, c, w, god_id) == library.GOD_KEPT
    s.player.insight_fx["悟:98"] = InsightFx(quality="上品", grand=s.player.insight_fx[god_id].grand)
    s.player.insights.append("悟:98")
    art = s.player.member.wugong_id
    s.player.art_slots[art] = ["悟:98"]
    assert arts.slot_problem(s, c, w, s.player.member.neigong_id, god_id) == arts.refuse(arts.GOD_ONE, "只裝一個")


def test_season_cap_and_one_at_a_time():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    assert not epiphany.roll(s, c, mock.Mock(random=mock.Mock(return_value=0.0)))  # 還有一條沒收


def test_the_demon_fight_runs_for_real_and_leaves_no_squad_behind():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(c, s.world)
    game._story_tick()
    before = set(c.squads)
    game.choose(f"{storyline.OPTION}:{line}")  # 不 mock：真的打一場（打輸也只是等一日再打）
    assert s.battles and s.battles[0].kind == "event"
    assert set(c.squads) == before
    assert game.state.player.storylines[line].ending in (None, "done")


class _Model:
    """假的模型：chat_structured 回固定的三個名字（或丟錯）。"""

    timeout = 30

    def __init__(self, names=None, fail=False):
        self.names, self.fail, self.messages = names or [], fail, None

    def chat_structured(self, messages, model, **_):
        self.messages = messages
        if self.fail:
            raise ConnectionError("down")
        return model(names=self.names)


def test_three_stage_naming_takes_the_model_names_and_tops_up_from_the_word_list():
    game = _game()
    s, c = game.state, game.content
    _through_demon(game)
    ask = game.epiphany_request()
    assert ask is not None and ask.god == s.player.god_naming.god
    assert s.player.god_naming.place in ask.messages[-1]["content"]  # 在哪裡悟的、拷問問了什麼都給模型當線索
    model = _Model(["「寒潭映月」", "寒潭映月", "張角", "孤燈照雪"])  # 包裝、重複、人物的名字都不收
    names = epiphany.propose_names(model, c, ask, budget=20.0, person=game.world.is_character_name)
    assert names == ["寒潭映月", "孤燈照雪"]
    game.world.mutate_season(lambda w: w.god_names.update({"孤燈照雪": "別人"}))  # 等名字的時候被別人用掉了
    game.epiphany_names(ask, names)
    got = s.player.god_naming.candidates
    assert got[0] == "寒潭映月" and "孤燈照雪" not in got and len(got) == 3
    assert game.epiphany_request() is None  # 想過了不再開單
    assert game.epiphany_names(ask, ["別的名字"]) == [] and s.player.god_naming.candidates == got  # 舊單子交回來不動


def test_model_down_means_word_list_names():
    game = _game()
    s, c = game.state, game.content
    _through_demon(game)
    ask = game.epiphany_request()
    assert epiphany.propose_names(_Model(fail=True), c, ask) == []
    assert epiphany.propose_names(None, c, ask) == []
    game.epiphany_names(ask, [])
    assert len(s.player.god_naming.candidates) == 3


def test_bots_wait_for_a_model_slot_and_never_take_word_list_names():
    from tianxia import bot_policy

    game = _game()
    s = game.state
    _through_demon(game)
    rng = mock.Mock(randrange=mock.Mock(return_value=1))
    closed = bot_policy.NamingSlot(open=False)
    assert bot_policy._god_name(game, rng, closed) == [] and closed.skipped == 1 and not s.player.god_naming.asked
    slot = bot_policy.NamingSlot(open=True)
    bot_policy._god_name(game, rng, slot)
    assert isinstance(slot.job, bot_policy.EpiphanyJob)
    assert bot_policy.apply_job(game, slot.job, []) == [] and not s.player.god_naming.asked  # 模型沒給名字：不交回
    bot_policy.apply_job(game, slot.job, ["寒潭映月"])
    assert s.player.god_naming.candidates[0] == "寒潭映月"
    name = s.player.god_naming.candidates[1]
    bot_policy._god_name(game, rng, bot_policy.NamingSlot(open=True))
    assert any(i.name == name for i in s.player.own_insights.values())


def test_a_bot_runner_without_a_model_falls_back_to_the_word_list():
    from tianxia import bot_policy

    game = _game()
    _through_demon(game)
    bot_policy._god_name(game, mock.Mock(), bot_policy.NamingSlot(open=False, model=False))
    assert game.state.player.god_naming.asked and len(game.state.player.god_naming.candidates) == 3
