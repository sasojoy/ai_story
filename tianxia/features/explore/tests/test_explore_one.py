"""減法季探索一顆的引擎接線（減法季整合設計 4.1；主機側計畫 Task 2-3）：開著時選單只剩一顆「探索」（act:explore，出門一趟），
不畫三選一、尋敵、城裡操練；按一下扣 explore_stamina（6）、抽一件事結算，回一段話與一則「出門一趟」的江湖紀錄。
城類地點自己沒有對手時遭遇換成地痞（不推線、不算討伐、戰利打 town_loot_scale），自家營寨的遭遇是跟同袍比劃（不掉東西）；
事件端出 pending_event。用正式內容（season21）開局（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。

2d（企劃者 2026-10-26「只抽一件事情，然後體力先維持不動」，同天體力改 15）：以前連抽三拍，這個檔斷言三拍與體力 18 的測試照新規則改；
一趟只有一件事的整體行為在 tests/test_explore_one_single.py。"""
from __future__ import annotations

from unittest import mock

import pytest
from conftest import real_content
from jianfa_kit import _new, jianfa_game, jianfa_rules, plain_game, ready

from tianxia import explore_one, journal, team
from tianxia.battlelog import OUTING_LABEL
from tianxia.encounter import EncounterResult
from tianxia.engine import FREE_TEXT_OPTION


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _beat(beat: str):
    """這一趟抽到的那一件事照給的（不擲骰）。"""
    return mock.patch.object(explore_one, "draw", return_value=beat)


def _ids(game) -> list[str]:
    return [o.id for o in game.options(odds=False)]


def _reset(game) -> None:
    """下一趟：體力補滿、沒有待選的事件與感悟。"""
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def test_the_menu_has_one_explore_button_and_no_modes_drill_or_practice():
    game = ready(jianfa_game(), side="guan", loc="yingchuan")  # 城裡：以前有操練
    ids = _ids(game)
    assert ids.count("act:explore") == 1
    assert not [i for i in ids if i.startswith("explore:")] and "act:drill" not in ids
    option = next(o for o in game.options(odds=False) if o.id == "act:explore")
    assert option.label == "探索（體力 6・城裡多事）" and option.enabled
    ready(game, loc="yingshui")  # 城外：以前有練功（尋敵）
    ids = _ids(game)
    assert "explore:practice" not in ids and not [i for i in ids if i.startswith("explore:")]
    assert game.action_notes(ids)["act:explore"].startswith("出門一趟只碰上一件事")


def test_closed_season_keeps_the_old_menu():
    game = ready(plain_game(), side="guan", loc="yingchuan")
    ids = _ids(game)
    assert "explore:gather" in ids and "act:drill" in ids
    assert next(o for o in game.options(odds=False) if o.id == "act:explore").label == "探索"


def test_one_press_costs_six_and_writes_one_outing_entry():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    stamina, seq = p.stamina, p.explore_seq
    with _beat("material"):
        msgs = game.choose("act:explore")
    assert p.stamina == stamina - 6 and p.explore_seq == seq + 1
    entry = game.state.journal[0]
    assert entry.title == f"{journal.OUTING}・潁水河畔" and entry.tag == "得料"
    assert msgs[0].startswith("你") and "潁水河畔" in msgs[0]  # 一段話：出門那一句接這一件事
    assert msgs[1].startswith("得：")  # 得失那一行
    assert any(line.startswith("獲得 ") for line in msgs)
    assert not game.state.battles  # 這一趟沒有打仗


def test_an_encounter_trip_writes_one_battle_record_labelled_as_the_outing():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    with _beat("encounter"), _fight("大勝"):
        game.choose("act:explore")
    record = game.state.battles[0]  # 新的在前
    assert len(game.state.battles) == 1 and record.label == OUTING_LABEL and record.kind == "wild"
    assert game.state.journal[0].tag == "遇敵"


def test_the_event_trip_leaves_a_pending_event():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    with _beat("event"):
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
    with _beat("encounter"), _fight("大勝"):
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
    with _beat("encounter"):
        game.choose("act:explore")
    assert len(game.state.battles) == battles  # 比劃不是一場仗、沒有戰報
    assert p.materials == bag and game.state.pending_event is None  # 這一趟就是比劃，不掉東西、不遇事
    assert p.stats.get("xinde", 0) > xinde


def test_nothing_gained_fills_one_tier_one_material():
    """這一件沒收穫補一個一階素材（2d 以前是三拍都沒收穫）：遭遇打輸、素材找不到料。"""
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    p = game.state.player
    bag = sum(p.materials.values())
    with _beat("encounter"), _fight("落敗"):
        msgs = game.choose("act:explore")
    assert sum(p.materials.values()) == bag + 1
    assert any(line.startswith("獲得 ") for line in msgs)
    bag = sum(p.materials.values())
    _reset(game)
    with _beat("material"), mock.patch("tianxia.explore_modes.gather_finds", return_value=[]):
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


def test_a_strike_bounty_here_makes_the_trip_that_bounty():
    """2d：接了這裡的討伐懸賞，這一趟就是遭遇（打懸賞那一路）；以前是「至少一拍是遭遇」。"""
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    foe = game._wild_foes(game.content.locations["yingshui"])[0]
    bounty = mock.Mock(kind="strike", location="yingshui", squad=foe.id)
    with mock.patch("tianxia.bounties.mine", return_value=[bounty]):
        plan = game.outing_plan()
        assert plan.how == "bounty" and plan.foe.id == foe.id and plan.hint == "渡口有賞" and plan.boss is None
        assert game.mostly_here() == "渡口有賞"  # 四格那一格的小字跟鈕同一個字（/api/main 的 mostly）
        assert plan.weights == explore_one.encounter_only()
        for n in range(20):
            assert explore_one.draw(explore_one.rng_for(1, "沈浪", n, "拍"), plan.weights) == explore_one.ENCOUNTER


def test_a_boss_on_the_encounter_ends_the_outing_in_the_duel(monkeypatch):
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    boss = next(iter(game.content.duels.values()))
    real = game._outing_plan

    def with_boss(loc):
        plan = real(loc)
        return type(plan)(kind=plan.kind, weights=plan.weights, how=None, foe=None, boss=boss, hint=plan.hint)

    monkeypatch.setattr(game, "_outing_plan", with_boss)
    with _beat("encounter"):
        game.choose("act:explore")
    assert game.state.player.duel is not None and game.state.pending_event is None
    assert game.state.journal[0].tag == "遇敵"


def test_an_outing_rolls_the_pill_and_the_seal_shard_like_the_old_explore():
    """收尾照舊擲回體丹（簽到開著的季）與玉璽碎片（藏碎片的那一塊，領地爭奪的季）：出門一趟一次。"""
    got = []
    for chance in (0.0, 1.0):  # 新手目標（投靠一方）也送一顆：拿一定不掉的那一趟對照
        game = jianfa_game()
        game.content.config.checkin.pill_drop = chance
        ready(game, side="guan", loc="yingshui")
        pills = game.state.player.stamina_pills
        with _beat("material"):
            msgs = game.choose("act:explore")
        got.append((game.state.player.stamina_pills - pills, "回體丹 +1" in msgs))
    assert got[1] == (got[0][0] + 1, True) and not got[0][1]
    c = jianfa_rules(real_content("season21"))
    c.config.seal.cache.hide_chance = c.config.seal.cache.find_chance = 1.0  # 一定藏、一定撿到
    game = _new(c, "沈浪")
    cache = game.world.seal_state().registry.cache
    assert cache is not None
    ready(game, side="guan", loc=cache.loc)
    with _beat("material"):
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


def test_the_explore_cell_reads_the_same_hint_as_the_button():
    """雲端批 5 的 /api/main 的 mostly（四格探索那一格的小字，網頁 m.mostly）：探索一顆開著時照出門一趟那一張表，跟鈕上括號那一段同一個字；
    自家營寨寫「同袍比劃」。輿圖第一層名字旁的兩個字也照表（樓桑里照小圖是野、照表是城）；關著照小圖（雲端原本的）。"""
    import server

    from tianxia import mapdata

    game = ready(jianfa_game(), side="guan", loc="yingchuan")
    view = server.main_view(game)
    label = next(o for o in game.options(odds=False) if o.id == "act:explore").label
    assert view["mostly"] == "城裡多事" and label.endswith("・城裡多事）")
    ready(game, loc="guan_camp")
    assert server.main_view(game)["mostly"] == "同袍比劃"
    ready(game, loc="guangzong")
    assert mapdata.mostly_here(game.state, game.content) == "營裡多敵"  # 小圖是城，表是營（兩張都對得上的營優先）
    places = {p["id"]: p["mostly"] for p in game.map_base()["places"]}
    assert places["loushang_village"] == "多事" and places["guangzong"] == "多敵"
    off = ready(plain_game(), side="guan", loc="guangzong")
    assert mapdata.mostly_here(off.state, off.content) == "城裡多事"
    off_places = {p["id"]: p["mostly"] for p in off.map_base()["places"]}
    assert off_places["loushang_village"] == "多敵"
    assert mapdata.base_key(off.state, off.content) != mapdata.base_key(game.state, game.content)


def test_the_howto_explains_the_outing_the_gates_and_the_milestones():
    # 自己把屬性五段打開：正式設定 2026-10-28 起把 stat_milestones 關掉了（線上玩家沒點可配），
    # 這一條驗的是「開著時玩法說明寫了沒」，不跟著設定的取捨跑
    on = ready(jianfa_game(stat_milestones=True), side="guan", loc="yingshui").howto_text()
    off = ready(plain_game(), side="guan", loc="yingshui").howto_text()
    assert "出門一趟" in on and "收穫漸少" in on and "境界與配點" in on and "找素材" not in on.split("**探索**")[1].split("\n")[0]
    assert "出門一趟" not in off and "境界與配點" not in off
    off_gates = ready(jianfa_game(explore_one=False), side="guan", loc="yingshui").howto_text()
    assert "出門一趟" not in off_gates and "收穫漸少" in off_gates  # 子開關各管各的


def test_is_idle_follows_the_explore_button():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    assert game.is_idle()
    with _beat("event"):
        game.choose("act:explore")
    assert not game.is_idle()  # 事件擋著
