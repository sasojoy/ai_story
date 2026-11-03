"""特殊頓悟（tianxia/epiphany.py；企劃者 2026-10-26 設計稿）：擲中感悟時再擲、機率與保底；中了開一條頓悟的線，
拷問→小試→心魔（打自己的影子、輸了隔一日再打、次數不限）→挑模板→取名（三個候選或自己寫，全服不重複）→收進意境（神品）；
神品不能揣摩、合成、熔，身上只准裝一個；關著時不擲、存檔不多鍵。用正式內容（season21）（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import arts, epiphany, fusion, insight_fx, library, storyline, team
from tianxia.encounter import EncounterResult
from tianxia.rules import day_seconds
from tianxia.state import InsightFx

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


def test_the_waiting_trial_shows_a_row_and_counts_down():
    """FB-902：小試抽到「靜候」時 task 段在選單上一行都不畫（doable 排除 task），玩家什麼都看不到——
    上班想下班就這樣「卡住」一整天。現在灰著列一行、後面寫還要多久。"""
    game = _game(trial_wait_days=0.25)  # 四分之一個遊戲日
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    progress = s.player.storylines[line]
    assert progress.stage == "trial"

    def row():
        return next((o for o in game.options() if o.id == f"{storyline.OPTION}:{line}"), None)

    got = row()
    assert got is not None and not got.enabled  # 有這一行，但按不下去（要去等／去做那件事）
    assert epiphany.TRIALS["wait"][0] in got.label and "還要 6 小時" in got.label
    assert "一日" not in got.label  # 以前寫死「靜候一日」，等多久變成設定之後那句話會騙人
    assert game.choose(f"{storyline.OPTION}:{line}") == ["（此刻無法這麼做。）"]  # 灰的按下去引擎本來就擋

    s.world.time += day_seconds(c, s.world) * 0.25 - 30  # 剩不到一分鐘
    assert storyline.WAIT_SOON in row().label
    s.world.time += 60  # 到了：這一段過去了，換心魔那一行
    game._story_tick()
    assert s.player.storylines[line].stage == "demon"
    assert row().enabled


def test_how_long_the_waiting_trial_takes_follows_the_setting():
    """「靜候一日」在 7 天的季裡是真實 24 小時（整季的 1/7）：改成設定、正式設定寫一個時辰（FB-902）。"""
    game = _game(trial_wait_days=1.0)
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(c, s.world) * 0.5
    game._story_tick()
    assert s.player.storylines[line].stage == "trial"  # 半日還不夠
    # 這一刻把設定調短（線已經在走）：每次檢定都照此刻的設定讀，所以當場就過
    c.config.epiphany.trial_wait_days = 1 / 12
    game._story_tick()
    assert s.player.storylines[line].stage == "demon"


def test_the_old_wait_hint_in_a_running_line_is_rewritten():
    """進行中的線 hint 是存檔裡那一份：舊存檔寫著「靜候一日，什麼都別急」，讀出來要換成新的那一句
    （REFRESH_HOOKS；還要多久由倒數寫）。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    progress = next(iter(s.player.storylines.values()))
    stale = [st.model_copy(update={"hint": "靜候一日，什麼都別急"}) if st.id == "trial" else st
             for st in progress.custom.stages]
    progress.custom = progress.custom.model_copy(update={"stages": stale})
    _, stage = storyline.current(c, s.player.storylines[progress.line])
    assert stage.id == "ask"
    _answer_all(game)
    _, stage = storyline.current(c, s.player.storylines[progress.line])
    assert stage.id == "trial" and stage.hint == epiphany.TRIALS["wait"][0] and "一日" not in stage.hint


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


def test_losing_to_the_demon_pops_a_card_with_the_fail_art_and_writes_it_down():
    """Joy 2026-10-28「心魔挑戰失敗沒有明顯提示，我們不是有做圖片嗎」：打輸了（還能再打）跳一張「心魔未破」的卡，圖是 dunwu_fail，
    寫幾天後能再打、前面的關都還算數；江湖紀錄與行狀各一行。打贏不跳。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(c, s.world)
    game._story_tick()
    s.player.story_cards = []
    with _loss():
        msgs = game.choose(f"{storyline.OPTION}:{line}")
    (card,) = [x for x in s.player.story_cards if x.kind == "retry"]
    days = storyline.wait_text(c.config.epiphany.retry_days)
    assert card.title == epiphany.FAIL_TITLE and card.image == epiphany.IMAGE["fail"] and card.failed
    assert f"過 {days}，可以再去面對它" in card.text and "前面問過的心、試過的手都還算數" in card.text
    assert epiphany.FAIL_LOG.replace("{days}", days) in "\n".join(msgs)
    assert s.player.annals[-1].text == epiphany.FAIL_ANNAL.replace("{name}", s.player.name)
    (view,) = [v for v in game.story_card_view() if v["kind"] == "retry"]
    assert view["title"] == epiphany.FAIL_TITLE and view["image"] == "stories/dunwu_fail"
    s.player.story_cards = []
    s.world.time = s.player.storylines[line].retry_at
    with _win():
        game.choose(f"{storyline.OPTION}:{line}")
    assert not [x for x in s.player.story_cards if x.kind == "retry"]


def test_the_demon_is_your_own_shadow():
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    stage = epiphany.storyline.definition(c, s.player.storylines[line]).stage("demon")
    squad = game._mirror_squad(s.player.storylines[line], stage)
    power = team.power_vs(s, c, game.world, squad.model_copy(update={"difficulty": 1.0}), fresh=True, terrain=False, seal=False)
    assert squad.name == "心魔" and squad.difficulty == pytest.approx(round(power * c.config.epiphany.demon_scale, 1), abs=0.11)


def test_config_changes_reach_a_line_that_is_already_running():
    """程式組的線把整份定義存進 progress.custom，所以改了設定本來只對之後新開的線有效
    （線上踩到：心魔的 retry_days 從一天改成一個時辰、削弱也加了，正在走的人完全沒吃到）。
    storyline.REFRESH_HOOKS 讓每次讀出來的那一份照此刻的設定重算。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    progress = next(iter(s.player.storylines.values()))
    frozen = progress.custom.stage("demon")          # 存檔裡凍著的那一份
    assert frozen is not None

    c.config.epiphany.retry_days = 0.5               # 開線之後才改設定
    c.config.epiphany.demon_weaken = 0.2
    c.config.epiphany.demon_floor = 0.5
    live = storyline.definition(c, progress).stage("demon")
    assert live.retry_days == 0.5 and live.mirror_weaken == 0.2 and live.mirror_floor == 0.5
    assert progress.custom.stage("demon") is frozen   # 存檔沒被改，只有讀出來的那一份


def test_the_retry_note_counts_down_from_retry_at():
    """FB-900：那句話以前寫死「再等一個時辰」（照 StoryStage.retry_days 的預設 1/12），
    心魔那一關卻用 Config.epiphany.retry_days 覆蓋它，字就騙人。現在照 retry_at 算。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    _answer_all(game)
    s.world.time += day_seconds(c, s.world)
    game._story_tick()
    with _loss():
        game.choose(f"{storyline.OPTION}:{line}")
    progress = s.player.storylines[line]
    assert progress.retry_at is not None

    def note() -> str:
        return next(o for o in game.options() if o.id == f"{storyline.OPTION}:{line}").label

    s.world.time = progress.retry_at - 7200          # 兩小時
    assert "再等 2 小時才能再試" in note()
    s.world.time = progress.retry_at - 900           # 十五分鐘
    assert "再等 15 分鐘才能再試" in note()
    s.world.time = progress.retry_at - 30            # 剩不到一分鐘
    assert storyline.RETRY_SOON in note()
    s.world.time = progress.retry_at                 # 到了：不再有那一段，而且按得下去
    label = note()
    assert "才能再試" not in label and storyline.RETRY_SOON not in label
    assert next(o for o in game.options() if o.id == f"{storyline.OPTION}:{line}").enabled


def test_the_demon_gets_weaker_every_time_you_fail_down_to_a_floor():
    """企劃者 2026-10-28「心魔重複打的時候削弱他好了」（「僵持也算過關」被否了：太簡單）：
    每輸一次（含僵持）難度的倍數降 demon_weaken，降到 demon_floor 為止，所以不會永遠卡在那裡。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    line = next(iter(s.player.storylines))
    progress = s.player.storylines[line]
    stage = epiphany.storyline.definition(c, progress).stage("demon")
    r = c.config.epiphany
    assert r.demon_weaken > 0 and 0 < r.demon_floor < r.demon_scale   # 設定真的開著
    base = game._mirror_squad(progress, stage).difficulty

    seen = [base]
    for tries in range(1, 9):
        progress.tries = tries
        seen.append(game._mirror_squad(progress, stage).difficulty)
    assert seen[1] < seen[0]                                         # 輸一次就弱一點
    assert all(b <= a for a, b in zip(seen, seen[1:]))               # 一路不回頭
    floor_at = int(round((r.demon_scale - r.demon_floor) / r.demon_weaken))
    assert seen[floor_at] == seen[floor_at + 1] == seen[-1]          # 到底就不再削
    assert seen[-1] == pytest.approx(base * r.demon_floor / r.demon_scale, rel=0.02)


def test_other_mirror_fights_are_not_weakened():
    """削弱只掛在帶了 mirror_weaken 的那一關；沒帶的（預設 0）一個字都不變。"""
    game = _game()
    s, c = game.state, game.content
    _begin(game)
    progress = next(iter(s.player.storylines.values()))
    stage = epiphany.storyline.definition(c, progress).stage("demon")
    plain = stage.model_copy(update={"mirror_weaken": 0.0, "mirror_floor": 0.0})
    progress.tries = 0
    first = game._mirror_squad(progress, plain).difficulty
    progress.tries = 5
    assert game._mirror_squad(progress, plain).difficulty == first


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
