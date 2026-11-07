"""socialize 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
from unittest import mock
import pytest
from tianxia import companion_agent, rules
from tianxia.engine import Game
from tianxia.models import FigureDef, PromotionDef
from engine_kit import (  # noqa: F401
    FAKE_TURN, NEXT_TURN, _figure, _hall, _labels, _no_model, _prepared, _stand_by_one_figure, _training_factions, ids,
)

pytestmark = pytest.mark.whole_content


def _lone_figure_at_the_cave(content, fame=10):
    """寶洞沒有交友事件：這裡只站著韓鐵一位大勢人物。"""
    ch = _figure(content, fame=fame)
    ch.kind, ch.recruit_at, ch.talk_at = "locked", None, "cave"
    return ch


def test_a_lone_figure_you_cannot_meet_leaves_only_the_free_audience_button(content, game):
    """沒有交友事件、唯一的大勢人物又見不到：交友按下去只是花 5 點體力換同一句打發，所以不給交友，
    這條路只剩不花體力的求見（設計 9.1：求見一直都在）。"""
    game.state.player.location = "cave"
    assert "act:socialize" not in ids(game)  # 沒有大勢人物也沒有事件
    _lone_figure_at_the_cave(content, fame=10)
    assert game.state.player.stats.get("fame", 0) < 10
    assert "act:socialize" not in ids(game)
    option = next(o for o in game.options() if o.id == "call:mate")
    assert (option.label, option.enabled) == ("求見韓鐵（名望還差 10）", True)
    stamina = game.state.player.stamina
    assert game.choose("call:mate")[0].startswith("韓鐵連見都不見你")
    assert game.state.player.stamina == stamina


def test_socialize_stays_wherever_it_is_not_futile(content, game):
    """交友照給：地點有交友事件、見得到那位人物、福緣到期、或在召見的地點（交友端出晉升奇遇）。"""
    game.state.player.location = "cave"
    _lone_figure_at_the_cave(content, fame=10)
    assert "act:socialize" not in ids(game)
    game.state.player.stats["fame"] = 10  # 見得到他
    assert "act:socialize" in ids(game)
    game.state.player.stats["fame"] = 0
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min  # 福緣到期：交友最先發福緣
    assert "act:socialize" in ids(game)
    game.state.player.fortune = True
    assert "act:socialize" not in ids(game)
    with mock.patch("tianxia.engine.ranks.summons_event", return_value="join"):  # 召見的地點
        assert "act:socialize" in ids(game)
    game.state.player.location = "town"  # 小鎮有交友事件（拜師）
    assert "act:socialize" in ids(game)


def test_socializing_where_two_figures_stand_never_opens_a_dialogue(content, game):
    _hall(content, game)
    assert not game.socialize_starts_dialogue()
    assert game.dialogue_request("act:socialize") is None
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("交友不該開口對話")):
        game.choose("act:socialize")
    assert game.state.pending_event == "join"  # 小鎮的交友事件（拜師）照常發生
    assert game.state.player.pending_companion is None
    game.state.pending_event = None
    with mock.patch("tianxia.features.socialize.actions.pick_event", return_value=None):
        msgs = game.choose("act:socialize")
    assert msgs == ["你四處結交了一番，沒遇上什麼事；想拜會此地的人物，請按「求見」指名。"]


def test_the_audience_list_names_each_figure_and_why_some_cannot_be_seen(content, game):
    _hall(content, game, mate_fame=10)
    game.choose("act:call")
    assert game.state.player.picking_audience
    assert [(o.id, o.label, o.enabled) for o in game.options()] == [
        ("call:mate", "韓鐵（名望還差 10）", True),  # 求見一直都在（武學與成長設計 9.1）；被打發是一定的，寫真正的差距
        ("call:scholar", "書生（體力 5・還能談 3/3 輪）", True),
        ("call:back", "返回", True),
    ]
    scene = game.scene_text()
    moment = rules.day_ends_text(content, game.state.world)  # 遊戲日跟著季長縮：寫換日的那一刻，不寫「每天」（企劃者 2026-10-08）
    assert scene.startswith("**求見**") and f"每位人物各算各的，最多談 3 輪，到 {moment} 重新算起" in scene
    assert game.state.journal[0].title == "求見・小鎮"
    assert game.state.player.stamina == content.config.stamina_max  # 打開名單不花體力


def test_a_prior_meeting_opens_the_door_in_the_audience_list(content, game):
    _hall(content, game, mate_fame=10)
    game.state.player.flags.add("結識:mate")
    game.choose("act:call")
    assert _labels(game)["call:mate"] == ("韓鐵（體力 5・還能談 3/3 輪）", True)


def test_the_daily_limit_counts_per_figure(content, game):
    """每位人物一個遊戲日最多談 3 輪，各算各的：跟書生談滿了，韓鐵照樣見得到。"""
    _hall(content, game)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:call")
        game.choose("call:scholar")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
    moment = rules.day_ends_text(content, game.state.world)
    assert msgs[-1] == f"書生起身送客，改日再敘：要到 {moment} 之後才能再來拜會。"
    game.choose("act:call")
    labels = _labels(game)
    assert labels["call:scholar"] == (f"書生（已經談滿 3 輪，{moment} 之後再來）", False)
    assert labels["call:mate"] == ("韓鐵（體力 5・還能談 3/3 輪）", True)
    assert game.choose("call:scholar") == ["（此刻無法這麼做。）"]
    game.state.world.time = rules.day_ends(content, game.state.world)  # 換日重算（遊戲日跟著季長縮）
    assert _labels(game)["call:scholar"][1]


def test_going_back_always_works_and_closes_the_list(content, game):
    _hall(content, game)
    game.choose("act:call")
    game.state.player.stamina = 0
    labels = _labels(game)
    assert labels["call:scholar"] == ("書生（體力 5・還能談 3/3 輪）", False)  # 體力不夠
    assert labels["call:back"] == ("返回", True)  # 永遠有路可退，不會卡死
    assert game.choose("call:back") == ["你收回名帖，暫且不求見了。"]
    assert not game.state.player.picking_audience
    assert "act:call" in ids(game)
    assert game.state.journal[0].title == "收回名帖"


def test_dialogue_request_for_a_call_is_the_generic_opening(content, game):
    _hall(content, game, mate_fame=10)
    game.choose("act:call")
    req = game.dialogue_request("call:scholar")
    assert (req.option_id, req.companion_id, req.player_action) == (
        "call:scholar", "scholar", companion_agent.GENERIC_OPENING,
    )
    assert game.dialogue_request("call:mate") is None  # 見不到：被打發，不叫模型
    assert game.dialogue_request("call:back") is None


def test_a_prepared_failure_for_an_audience_refunds_the_cost(content, game):
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=None)
    with _no_model():
        msgs = game.choose("call:scholar", prepared=prepared)
    assert msgs == ["書生似乎無心多談，你只好先行告辭。"]
    assert game.state.player.stamina == content.config.stamina_max
    assert not game.state.player.picking_audience


def test_calling_on_a_figure_never_delivers_the_fortune(content, game):
    """福緣到期也一樣：求見是指名拜會，直接開口對話，福緣留給交友或之後自己到。"""
    _hall(content, game)
    game.state.player.fortune = False
    game.state.world.time += 86400 * content.config.fortune_day_min
    game.choose("act:call")
    assert game.dialogue_request("call:scholar") is not None
    with mock.patch.object(companion_agent, "generate_turn", return_value=NEXT_TURN):
        game.choose("call:scholar")
    assert game.state.player.pending_companion == "scholar"
    assert not game.state.player.fortune


def test_a_prepared_audience_is_refused_once_the_list_is_closed(content, game):
    """生成的那段時間另一個分頁按了「返回」：call:<人物> 已經不在選單上，鎖外生成好的這輪不套用、也不扣體力。"""
    _hall(content, game)
    game.choose("act:call")
    prepared = _prepared(game, "call:scholar", turn=NEXT_TURN)
    game.choose("call:back")
    before = game.state.player.stamina
    with _no_model():
        assert game.choose("call:scholar", prepared=prepared) == ["（此刻無法這麼做。）"]
    assert game.state.player.pending_companion is None
    assert game.state.player.stamina == before


def _guan_figure(content, character_id="mate"):
    """把這位人物掛成官軍的大勢人物（階級抵門檻只認人物表上的陣營）。"""
    _training_factions(content)
    content.figures["f_test"] = FigureDef(
        id="f_test", character=character_id, name=content.characters[character_id].name, faction="guan",
        location="town", squad=next(iter(content.squads)),
    )


def _season_one_on(content, game):
    """第一季的規則開著（開關開、這一季開季時也蓋了章）：晉升只有這時候才有，「再升一階」的提示才算數。"""
    content.config.season_one = True
    game.state.world.season_one = True


def _promotion(content, faction="guan", rank=2):
    """這個陣營升到第 rank 階的晉升定義（hint 只在真的有下一階可升時才提「再升一階」）。"""
    content.promotions.append(PromotionDef(
        faction=faction, rank=rank, location="town", event_main="x", summons_text="x", closing="x",
    ))


def test_the_audience_button_is_always_there_and_brushes_off_for_free(content, game):
    cid = _stand_by_one_figure(content, game)
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    assert option.enabled and option.label == "求見韓鐵（名望還差 30）"
    game.state.player.stats["fame"] = 12
    assert next(o for o in game.options() if o.id == f"call:{cid}").label == "求見韓鐵（名望還差 18）"
    game.state.player.stats["fame"] = 0
    stamina, affinity = game.state.player.stamina, game.state.player.affinities.get(cid, 0)
    msgs = game.choose(f"call:{cid}")
    assert any("閒雜人等退下。" in m and "名望還差 30" in m for m in msgs)
    assert game.state.player.stamina == stamina and game.state.player.affinities.get(cid, 0) == affinity
    assert game.state.player.pending_companion is None
    assert game.state.journal[0].title == "求見・韓鐵"  # 吃閉門羹也寫進江湖紀錄


def test_a_brush_off_does_not_ask_the_model(content, game):
    cid = _stand_by_one_figure(content, game)
    assert game.dialogue_request(f"call:{cid}") is None
    with mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("被打發的不該叫模型")):
        game.choose(f"call:{cid}")


def test_a_brush_off_without_written_lines_uses_the_general_one(content, game):
    cid = _stand_by_one_figure(content, game)
    content.characters[cid].brush_off = []
    assert game.choose(f"call:{cid}") == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 30）"]


def test_a_brush_off_picks_one_of_the_written_lines(content, game):
    cid = _stand_by_one_figure(content, game)
    content.characters[cid].brush_off = ["一", "二", "三"]
    seen = set()
    for _ in range(40):
        seen.add(game.choose(f"call:{cid}")[0].partition("（")[0])
    assert seen == {"一", "二", "三"}


def test_the_brush_off_says_how_far_short_you_are(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    game.state.player.stats["fame"] = 12
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18）"]  # 散人只看名望
    game.state.player.faction = "huang"  # 敵對陣營：階級不抵，也不指望在他那邊升階
    game.state.player.rank = 2
    _promotion(content, "huang", 3)
    assert game.choose(f"call:{cid}") == ["閒雜人等退下。（名望還差 18）"]


@pytest.mark.parametrize(("season_one", "promotions", "rank", "fame", "discount", "hint"), [
    # 投靠了官軍、還沒晉升：門檻 30，升一階抵 5；官軍有第 2 階可升。差 5：剛好一階補得上
    pytest.param(True, [2], 0, 25, None, "（名望還差 5，或在官軍再升一階）", id="one-step-closes-a-gap-of-5"),
    pytest.param(True, [2], 0, 26, None, "（名望還差 4，或在官軍再升一階）", id="one-step-closes-a-gap-of-4"),
    pytest.param(True, [], 0, 26, None, "（名望還差 4）", id="no-next-promotion-written"),  # 官軍的晉升表上沒有第 2 階
    # 已經升過第 2 階，下一階（3）沒寫；門檻 30 - 5 = 25，差 3
    pytest.param(True, [2], 2, 22, None, "（名望還差 3）", id="past-the-last-written-promotion"),
    pytest.param(True, [2], 0, 12, None, "（名望還差 18）", id="one-step-cannot-close-the-gap"),  # 差 18，一階只抵 5
    pytest.param(True, [2], 0, 12, 18, "（名望還差 18，或在官軍再升一階）", id="a-big-enough-step-can"),  # 抵得夠大就補得上
    # 規則沒開（beta 那一季）沒有晉升這回事，「再升一階」不能寫：其他條件都成立也一樣
    pytest.param(False, [2], 0, 26, None, "（名望還差 4）", id="season-one-rules-off"),
])
def test_the_brush_off_names_the_faction_way_up_only_when_one_more_step_would_close_the_gap(
    content, game, season_one, promotions, rank, fame, discount, hint,
):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    if season_one:
        _season_one_on(content, game)
    for promoted_to in promotions:
        _promotion(content, "guan", promoted_to)
    if discount is not None:
        content.config.audience_rank_discount = discount
    p = game.state.player
    p.faction, p.rank = "guan", rank
    p.stats["fame"] = fame
    assert game.choose(f"call:{cid}") == [f"閒雜人等退下。{hint}"]


def test_enough_fame_turns_the_audience_button_into_a_real_audience(content, game):
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    assert (option.label, option.enabled) == ("求見韓鐵（體力 5）", True)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose(f"call:{cid}")
    p = game.state.player
    assert p.pending_companion == cid
    assert p.stamina == content.config.stamina_max - content.config.action_cost["socialize"]


def test_rank_in_the_figures_faction_opens_the_door(content, game):
    cid = _stand_by_one_figure(content, game)
    _guan_figure(content, cid)
    game.state.player.stats["fame"] = 24
    game.state.player.faction, game.state.player.rank = "guan", 2  # 晉升過一次：30 - 5 = 25
    assert not game.can_meet_figure(cid)
    game.state.player.stats["fame"] = 25  # 剛好到
    assert game.can_meet_figure(cid)
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose(f"call:{cid}")
    assert game.state.player.pending_companion == cid
    game.choose("talk:leave")
    game.state.player.stats["fame"], game.state.player.rank = 20, 3  # 兩次：30 - 10 = 20
    assert game.can_meet_figure(cid)
    game.state.player.rank = 0  # 投靠了還沒晉升：一點都不抵
    assert not game.can_meet_figure(cid)


def test_can_meet_figure_follows_fame_or_a_prior_meeting(content, game):
    cid = _stand_by_one_figure(content, game)
    assert not game.can_meet_figure(cid)
    game.state.player.flags.add(f"結識:{cid}")
    assert game.can_meet_figure(cid)
    game.state.player.flags.discard(f"結識:{cid}")
    game.state.player.stats["fame"] = 30
    assert game.can_meet_figure(cid)


def test_a_figure_who_turned_you_away_after_a_defeat_stays_shut(content, game):
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    with mock.patch.object(Game, "_snubbed_character", return_value=True):
        option = next(o for o in game.options() if o.id == f"call:{cid}")
        assert option.label == "求見韓鐵（剛吃了敗仗，閉門不見）" and not option.enabled


def test_the_audience_button_stays_but_greys_out_once_the_day_is_used_up(content, game):
    """一個遊戲日 3 輪談滿後，單人地點的求見不消失：灰掉、寫跟求見名單同一句（設計 9.1：求見一直都在）。"""
    cid = _stand_by_one_figure(content, game)
    game.state.player.stats["fame"] = 30
    game.state.player.talks_today[cid] = [rules.game_day(content, game.state.world), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == f"call:{cid}")
    moment = rules.day_ends_text(content, game.state.world)
    assert (option.label, option.enabled) == (f"求見韓鐵（已經談滿 3 輪，{moment} 之後再來）", False)
    assert game.choose(f"call:{cid}") == ["（此刻無法這麼做。）"]
    game.state.world.time = rules.day_ends(content, game.state.world)  # 換日重算（遊戲日跟著季長縮）
    assert next(o for o in game.options() if o.id == f"call:{cid}").enabled


def test_two_figures_still_share_one_audience_option_and_a_brush_off_closes_the_list(content, game):
    _hall(content, game, mate_fame=10)
    assert "call:mate" not in ids(game) and "act:call" in ids(game)  # 兩位以上：求見先打開名單，不直接列人
    game.choose("act:call")
    stamina = game.state.player.stamina
    msgs = game.choose("call:mate")
    assert msgs == ["韓鐵連見都不見你，門口的人把你請了出去。（名望還差 10）"]
    assert game.state.player.stamina == stamina and not game.state.player.picking_audience
    assert game.state.player.pending_companion is None
