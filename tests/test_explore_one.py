"""減法季探索一顆的引擎接線（減法季整合設計 4.1；主機側計畫 Task 2-3）：開著時選單只剩一顆「探索」（act:explore，出門一趟），
不畫三選一、尋敵、城裡操練；按一下扣 explore_stamina、抽三拍逐拍結算，回一段話與一則「出門一趟」的江湖紀錄。
城類地點自己沒有對手時遭遇換成地痞（不推線、不算討伐、戰利打 town_loot_scale），自家營寨的遭遇是跟同袍比劃（不掉東西）；
事件拍留在最後、端出 pending_event。用正式內容（season21）開局，整個檔標 slow。"""
from __future__ import annotations

from unittest import mock

import pytest
from conftest import real_content
from jianfa_kit import _new, jianfa_game, jianfa_rules, plain_game, ready

from tianxia import explore_one, journal, team
from tianxia.battlelog import OUTING_LABEL
from tianxia.encounter import EncounterResult
from tianxia.engine import FREE_TEXT_OPTION

pytestmark = pytest.mark.slow


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beats(*beats: str):
    """這一趟抽到的拍照給的（不擲骰；要選的拍照 draw 的規矩要放最後）。"""
    return mock.patch.object(explore_one, "draw", return_value=list(beats))


def _ids(game) -> list[str]:
    return [o.id for o in game.options(odds=False)]


def test_the_menu_has_one_explore_button_and_no_modes_drill_or_practice():
    game = ready(jianfa_game(), side="guan", loc="yingchuan")  # 城裡：以前有操練
    ids = _ids(game)
    assert ids.count("act:explore") == 1
    assert not [i for i in ids if i.startswith("explore:")] and "act:drill" not in ids
    option = next(o for o in game.options(odds=False) if o.id == "act:explore")
    assert option.label == "探索（體力 18・多半有事）" and option.enabled
    ready(game, loc="yingshui")  # 城外：以前有練功（尋敵）
    ids = _ids(game)
    assert "explore:practice" not in ids and not [i for i in ids if i.startswith("explore:")]
    assert game.action_notes(ids)["act:explore"].startswith("出門一趟走三拍")


def test_closed_season_keeps_the_old_menu():
    game = ready(plain_game(), side="guan", loc="yingchuan")
    ids = _ids(game)
    assert "explore:gather" in ids and "act:drill" in ids
    assert next(o for o in game.options(odds=False) if o.id == "act:explore").label == "探索"


def test_one_press_costs_eighteen_and_writes_one_outing_entry():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    stamina, seq = p.stamina, p.explore_seq
    with _beats("material", "material", "encounter"), _fight("大勝"):
        msgs = game.choose("act:explore")
    assert p.stamina == stamina - 18 and p.explore_seq == seq + 1
    entry = game.state.journal[0]
    assert entry.title == f"{journal.OUTING}・潁水河畔"
    assert msgs[0].startswith("你") and "潁水河畔" in msgs[0]  # 一段話：出門那一句接每一拍
    assert msgs[1].startswith("得：")  # 得失那一行
    record = game.state.battles[0]  # 新的在前
    assert record.label == OUTING_LABEL and record.kind == "wild"
    assert any(line.startswith("獲得 ") for line in msgs)


def test_the_event_beat_stays_last_and_leaves_a_pending_event():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    with _beats("material", "material", "event"):
        game.choose("act:explore")
    assert game.state.pending_event is not None
    assert game.state.player.outing_last == "yingshui:event"
    ids = _ids(game)
    assert ids and all(i.startswith("choice:") or i == FREE_TEXT_OPTION for i in ids)  # 選單是那一則事件的選項


def test_town_encounters_are_street_toughs_that_push_nothing_and_count_no_bounty():
    game = ready(jianfa_game(), side="guan", loc="yingchuan")
    c, p = game.content, game.state.player
    plan = game.outing_plan()
    assert plan.kind == explore_one.TOWN and plan.how == "town" and plan.foe.id == "dipi"
    trends = dict(game.state.world.trends)
    silver = p.stats["silver"]
    with _beats("encounter", "material", "material"), _fight("大勝"):
        game.choose("act:explore")
    record = game.state.battles[0]
    assert record.opponent == c.squads["dipi"].name and record.label == OUTING_LABEL
    assert dict(game.state.world.trends) == trends  # 不推線
    assert record.silver == round(c.squads["dipi"].reward_silver * c.config.jianfa.town_loot_scale)
    assert p.stats["silver"] >= silver + (record.silver or 0) - 1


def test_a_town_with_its_own_garrison_fights_that_garrison():
    """自己有隊伍的城（下曲陽）照原本的隊伍（PM 2026-10-25 第 3 件）。"""
    game = ready(jianfa_game(), side="huang", loc="xiaquyang")
    plan = game.outing_plan()
    if plan.how is None:
        pytest.skip("下曲陽此刻沒有對黃巾的隊伍")
    assert plan.how == "foe" and plan.foe.id != "dipi"


def test_own_camp_encounter_is_sparring_with_comrades_and_drops_nothing():
    game = ready(jianfa_game(), side="guan", loc="guan_camp")
    p = game.state.player
    plan = game.outing_plan()
    assert plan.kind == explore_one.CAMP and plan.how == "spar" and plan.hint == explore_one.SPAR_HINT
    bag, battles, xinde = dict(p.materials), len(game.state.battles), p.stats.get("xinde", 0)
    with _beats("encounter", "encounter", "event"):
        game.choose("act:explore")
    assert len(game.state.battles) == battles  # 比劃不是一場仗、沒有戰報
    assert p.materials == bag or game.state.pending_event is not None
    assert p.stats.get("xinde", 0) > xinde


def test_nothing_gained_fills_one_tier_one_material():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    bag = sum(p.materials.values())
    with _beats("encounter", "encounter", "material"), _fight("落敗"), mock.patch(
        "tianxia.explore_modes.gather_finds", return_value=[]
    ):
        msgs = game.choose("act:explore")
    assert sum(p.materials.values()) == bag + 1
    assert any(line.startswith("獲得 ") for line in msgs)


def test_insight_is_not_drawn_twice_in_a_row_at_the_same_place():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    p.outing_last = "yingshui:insight"
    with mock.patch.object(explore_one, "draw", wraps=explore_one.draw) as spy, _fight():
        game.choose("act:explore")
    assert spy.call_args.kwargs["last_choice"] == "insight"
    p.outing_last, p.stamina = "baima_temple:insight", 200.0
    game.state.pending_event = None
    p.sensing = None
    with mock.patch.object(explore_one, "draw", wraps=explore_one.draw) as spy, _fight():
        game.choose("act:explore")
    assert spy.call_args.kwargs["last_choice"] is None  # 換了地方不擋


def test_a_strike_bounty_here_makes_the_first_beat_that_bounty():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    foe = game._wild_foes(game.content.locations["yingshui"])[0]
    bounty = mock.Mock(kind="strike", location="yingshui", squad=foe.id)
    with mock.patch("tianxia.bounties.mine", return_value=[bounty]):
        plan = game.outing_plan()
        assert plan.how == "bounty" and plan.foe.id == foe.id and plan.hint == explore_one.BOUNTY_HINT and plan.boss is None
        rng = explore_one.rng_for(1, "沈浪", 1, "拍")
        beats = explore_one.draw(game.content.config.jianfa, rng, plan.weights, bounty_here=True)
    assert beats[0] == explore_one.ENCOUNTER


def test_a_boss_on_the_encounter_beat_ends_the_outing_in_the_duel(monkeypatch):
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    boss = next(iter(game.content.duels.values()))
    real = game._outing_plan

    def with_boss(loc):
        plan = real(loc)
        return type(plan)(kind=plan.kind, weights=plan.weights, how=None, foe=None, boss=boss, hint=plan.hint)

    monkeypatch.setattr(game, "_outing_plan", with_boss)
    with _beats("material", "encounter", "event"):
        game.choose("act:explore")
    assert game.state.player.duel is not None and game.state.pending_event is None


def test_an_outing_rolls_the_pill_and_the_seal_shard_like_the_old_explore():
    """收尾照舊擲回體丹（簽到開著的季）與玉璽碎片（藏碎片的那一塊，領地爭奪的季）：出門一趟一次。"""
    got = []
    for chance in (0.0, 1.0):  # 新手目標（投靠一方）也送一顆：拿一定不掉的那一趟對照
        game = jianfa_game()
        game.content.config.checkin.pill_drop = chance
        ready(game, side="guan", loc="yingshui")
        pills = game.state.player.stamina_pills
        with _beats("material", "material", "material"):
            msgs = game.choose("act:explore")
        got.append((game.state.player.stamina_pills - pills, "回體丹 +1" in msgs))
    assert got[1] == (got[0][0] + 1, True) and not got[0][1]
    c = jianfa_rules(real_content("season21"))
    c.config.seal.cache.hide_chance = c.config.seal.cache.find_chance = 1.0  # 一定藏、一定撿到
    game = _new(c, "沈浪")
    cache = game.world.seal_state().registry.cache
    assert cache is not None
    ready(game, side="guan", loc=cache.loc)
    with _beats("material", "material", "material"):
        game.choose("act:explore")
    assert game.state.player.heirloom is not None


def test_bots_score_the_one_explore_button():
    """假人：探索一顆是一顆會按的鈕（同以前的練功分數；接了討伐懸賞多加分）；整季機器人照舊在選單上看得到它。"""
    from tianxia import bot, bot_policy
    from tianxia.state import BotProfile

    game = ready(jianfa_game(), side="guan", loc="yingshui")
    option = next(o for o in game.options(odds=False) if o.id == "act:explore")
    value = bot_policy.score(game, option, BotProfile(personality="普通", seed=1, faction="guan", season_number=1))
    assert value in (bot_policy.OUTING_SCORE, bot_policy.OUTING_SCORE + bot_policy.NEED_MATERIAL_SCORE)  # 剛出師缺素材：潁水河畔素材不比遭遇少
    assert bot.explore_choice([o.id for o in game.options(odds=False)]) == "act:explore"
    off = ready(plain_game(), side="guan", loc="yingshui")
    assert bot_policy.score(off, next(o for o in off.options(odds=False) if o.id == "act:explore"), BotProfile(personality="普通", seed=1, faction="guan", season_number=1)) is None  # 三選一的入口


def test_outing_lines_are_checked_when_loaded():
    from tianxia.content import ContentError, validate

    c = jianfa_rules(real_content("season21"))
    assert set(c.outing_lines) == set(explore_one.LINE_KEYS)
    c.outing_lines["encounter"]["win"] = ["半路撞上{foe}，打了3回合。"]  # 不准寫數字
    with pytest.raises(ContentError, match="outing_lines.encounter.win"):
        validate(c)
    c.outing_lines["encounter"]["win"] = ["半路撞上{foe}。"]
    del c.outing_lines["close"]["tired"]
    with pytest.raises(ContentError, match="tired"):
        validate(c)


def test_is_idle_follows_the_explore_button():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    assert game.is_idle()
    with _beats("material", "material", "event"):
        game.choose("act:explore")
    assert not game.is_idle()  # 事件擋著
