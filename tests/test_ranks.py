"""第一季濃縮版 T5：頭銜、召見、第 2 階晉升奇遇、部下（計畫 2026-10-05-T5-晉升）。

用真實內容（content/）：要驗的就是真實的晉升定義、奇遇、部下與大勢人物。每個測試自己載一份，開關在測試裡才打開。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import calendar, figures, ranks, team
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Config, Effect, FigureChange
from tianxia.state import PlayerState, Summons, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def _win():
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_new_fields_have_defaults_so_old_saves_load():
    assert Config().rank2_contrib == 300
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.rank, p.summons, p.followers) == (0, None, [])
    assert WorldState().promoted_today == {}
    assert (Effect().promote, Effect().followers, Effect().affinity) == (None, [], {})


def test_real_promotions_valid(real):
    by_side = {p.faction: p for p in real.promotions}
    assert set(by_side) == {"guan", "huang", "haoqiang"} and all(p.rank == 2 for p in real.promotions)
    guan, huang, gentry = by_side["guan"], by_side["huang"], by_side["haoqiang"]
    assert (guan.figure, guan.successor, guan.location) == ("huangfusong", "zhujun", "changshe")
    assert (huang.figure, huang.successor, huang.location) == ("bocai", "pengtuo", "huangjin_camp")
    assert (gentry.figure, gentry.successor, gentry.location, gentry.event_handoff) == (None, None, "nearest_base", None)
    assert guan.summons_text == "皇甫嵩召你到長社營中。" and guan.summons_handoff == "朱儁召你到長社營中。"
    assert gentry.summons_text == "中山的馬商張世平、蘇雙到了{據點}，指名要見你。"
    for p in real.promotions:
        for event_id in filter(None, (p.event_main, p.event_handoff)):
            event = real.events[event_id]
            assert event.actions == [] and len(event.choices) == 3
            assert all(ch.effect.promote == 2 and len(ch.effect.followers) == 2 for ch in event.choices)
    first = real.events["promo_guan_2"].choices[1]
    assert first.effect.affinity == {"huangfusong": 10} and first.effect.text == "皇甫嵩微微一笑。"
    assert real.events["promo_haoqiang_2"].choices[1].effect.materials == {"kuai_1": 2}


def test_real_followers_valid(real):
    assert set(real.followers) == {
        "follower_guan_spear", "follower_guan_crossbow", "follower_huang_believer",
        "follower_huang_strongman", "follower_haoqiang_retainer", "follower_haoqiang_buqu",
    }
    spear = real.followers["follower_guan_spear"]
    assert (spear.name, spear.faction, spear.wugong, spear.wugong_level) == ("持矛鄉勇", "guan", "xingwu_qiang", 3)
    assert all(f.wugong in real.skills for f in real.followers.values())
    assert real.skills["qiangnu"].name == "強弩射法"


# ── Task 2：頭銜 ─────────────────────────────────


def test_join_shows_rank_one_title(on):
    """投靠之後狀態列寫「陣營・頭銜」（第一季設計 5.2，第 1 階）；有門派時「門派・陣營・頭銜」；散人照舊；第 2 階換頭銜。"""
    assert ranks.TITLES == {
        "guan": ["", "鄉勇", "屯長", "軍司馬", "校尉"],
        "huang": ["", "信眾", "小帥", "小方渠帥", "大方渠帥"],
        "haoqiang": ["", "鄉里子弟", "宗族頭人", "地方豪強", "一方之主"],
    }
    game = _game(on, at="changshe")
    assert (ranks.rank_of(game.state), ranks.title(on, game.state), game.status_data()["affiliation"]) == (0, None, "散人")
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.faction == "guan"
    assert (ranks.rank_of(game.state), game.status_data()["affiliation"]) == (1, "官軍・鄉勇")
    for name, faction, shown in (("乙", "huang", "黃巾軍・信眾"), ("丙", "haoqiang", "地方豪強・鄉里子弟")):
        assert _game(on, name=name, faction=faction).status_data()["affiliation"] == shown
    game.state.player.sect = "yingchuan_academy"
    assert game.status_data()["affiliation"] == "潁川書院・官軍・鄉勇"
    game.state.player.rank = 2
    assert game.status_data()["affiliation"] == "潁川書院・官軍・屯長"
    assert "潁川書院・官軍・屯長" in game.status_text().splitlines()[0]


def test_switch_off_affiliation_unchanged(real):
    """開關關著（beta 那一季）：沒有頭銜，狀態列照舊「陣營」「門派・陣營」。"""
    game = _game(real, faction="guan")
    assert ranks.title(real, game.state) is None and game.status_data()["affiliation"] == "官軍"
    game.state.player.sect = "yingchuan_academy"
    game.state.player.rank = 2  # 就算存檔裡有階，beta 也不顯示
    assert game.status_data()["affiliation"] == "潁川書院・官軍"


def test_new_season_resets_rank_summons_and_followers(on):
    """RF5：換季是新角色——頭銜、召見、部下都重來（散人、第 0 階、沒有召見、沒有部下）；做完的引導照 T6 的規則不重來。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    player = _game(on, "甲", faction="guan")
    p = player.state.player
    p.rank, p.followers = 2, ["follower_guan_spear", "follower_guan_crossbow"]
    p.summons = Summons(rank=3, figure="huangfusong", location="changshe")
    done = p.tutorial_step = len(on.tutorial.steps)
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    p = player.state.player
    assert (p.faction, p.rank, p.summons, p.followers, p.tutorial_step) == (None, 0, None, [], done)
    assert player.status_data()["affiliation"] == "散人"


# ── Task 3：召見、晉升奇遇、每日彙整 ─────────────────────────────────


def _logged(game, text: str) -> bool:
    """江湖紀錄裡寫了這一句（敘事或數值變化）。"""
    return any(text in line for e in game.state.journal for line in (*e.lines, *e.changes, e.tag))


def _summoned(game, figure="huangfusong", at="changshe"):
    game.state.player.summons = Summons(rank=2, figure=figure, location=at)
    return game


def _ids(game):
    return [o.id for o in game.options()]


def test_summons_when_contribution_crosses_threshold(on):
    """貢獻 290 不發召見；巡哨推一次（+10）過 300 → 「皇甫嵩召你到長社營中。」寫進江湖紀錄、記下召見；再推不重發。"""
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.contrib = 290
    game.choose("act:rest")
    game.choose("act:stand")
    assert p.summons is None
    p.contrib = 295
    msgs = game.choose("act:duty")
    assert p.contrib >= 300 and "皇甫嵩召你到長社營中。" in msgs and _logged(game, "皇甫嵩召你到長社營中。")
    assert (p.summons.rank, p.summons.figure, p.summons.location) == (2, "huangfusong", "changshe")
    since = p.summons.since
    assert "皇甫嵩召你到長社營中。" not in game.choose("act:duty") and p.summons.since == since


def test_summons_after_a_challenge_win(on):
    """RF2：貢獻不是從推大勢來的——貢獻 260、挑戰波才打贏（+50）→ 召見。"""
    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.contrib = 260
    with _win():
        msgs = game.choose("act:challenge:bocai")
    assert game.state.player.contrib == 310 and "皇甫嵩召你到長社營中。" in msgs


def test_summons_on_sync_when_contribution_came_outside_an_action(on):
    """貢獻在行動之外跨過門檻（例：路上抵達、別處記帳）：下一次同步就發召見，寫一則江湖紀錄。"""
    game = _game(on, faction="guan", at="changshe")
    game.state.player.contrib = 300
    game.sync(game.now + 1)
    assert game.state.player.summons is not None and _logged(game, "皇甫嵩召你到長社營中。")


def test_summons_goes_to_successor_when_figure_gone(on):
    """RF1：皇甫嵩重挫轉去冀州、朱儁守長社：召見寫朱儁，到了長社演接手版。"""
    game = _game(on, faction="guan", at="changshe")
    figures.apply(game.state, on, "huangfusong", FigureChange(fate="重挫", front="jizhou", location="luzhi_camp"))
    game.state.player.contrib = 300
    assert "朱儁召你到長社營中。" in game.choose("act:rest")
    assert game.state.player.summons.figure == "zhujun"
    game.choose("act:stand")
    game.choose("act:summons")
    assert game.state.pending_event == "promo_guan_2_handoff"


def test_handoff_version_when_figure_left_after_summons(on):
    """RF1：召見發出時皇甫嵩還在，之後才重挫離開：到了現場照當下挑人，演接手版；主線與目標裡的召見也改寫朱儁。"""
    game = _summoned(_game(on, faction="guan", at="changshe"))
    assert "**召見**：皇甫嵩召你到長社營中。" in game.quest_text()
    figures.apply(game.state, on, "huangfusong", FigureChange(fate="重挫", front="jizhou", location="luzhi_camp"))
    assert "**召見**：朱儁召你到長社營中。" in game.quest_text()
    game.choose("act:summons")
    assert game.state.pending_event == "promo_guan_2_handoff"
    assert on.events["promo_guan_2_handoff"].text.startswith("長社營中。朱儁")


def test_haoqiang_summons_nearest_base(on):
    """豪強的召見地點照路網挑最近的豪強據點：在譙縣 → 曹氏莊院；在涿縣 → 鄉里結社。{據點} 換成地名。"""
    for name, at, base, base_name in (("甲", "qiao_county", "cao_manor", "曹氏莊院"),
                                      ("乙", "zhuo_county", "zhuo_militia_hall", "鄉里結社")):
        game = _game(on, name=name, faction="haoqiang", at=at)
        game.state.player.contrib = 300
        assert f"中山的馬商張世平、蘇雙到了{base_name}，指名要見你。" in game.choose("act:rest"), at
        assert (game.state.player.summons.location, game.state.player.summons.figure) == (base, None)


def test_summons_option_only_when_idle_at_the_place(on):
    """RF3：有召見、人在召見的地點、閒著時才有「應召」（不花體力）；不在那裡、在打坐、在路上都沒有；
    演到一半季結束，晉升不發生。"""
    game = _summoned(_game(on, faction="guan", at="luzhi_camp"))
    assert "act:summons" not in _ids(game)
    game.state.player.location = "changshe"
    summons = next(o for o in game.options() if o.id == "act:summons")
    assert summons.enabled and summons.label == "應召"
    game.choose("act:rest")
    assert _ids(game) == ["act:stand"]
    game.choose("act:stand")
    road = next(o.id for o in game.options() if o.id.startswith("move:"))
    game.choose(road)
    assert game.state.player.journey is not None and "act:summons" not in _ids(game)
    other = _summoned(_game(on, name="乙", faction="guan", at="changshe"))
    stamina = other.state.player.stamina
    other.choose("act:summons")
    assert other.state.pending_event == "promo_guan_2" and other.state.player.stamina == stamina
    other.state.world.ended = True
    assert other.choose("choice:1") == ["（此刻無法這麼做。）"] and ranks.rank_of(other.state) == 1


@pytest.mark.parametrize(("pick", "reaction", "affinity"), [
    (0, "「軍法是要守的，但為一隻雞斬一個兵，下一仗誰替你衝？」", 23),
    (1, "皇甫嵩微微一笑。", 30),
    (2, "「營規鬆一寸，賊就近一丈。」", 17),
])
def test_every_choice_promotes_and_gives_two_followers(on, pick, reaction, affinity):
    """三個選項都晉升：第 2 階、頭銜「官軍・屯長」、兩名部下、情誼照表（從 20 起）；接著是結尾那一句；召見清掉、記進當天的彙整。"""
    game = _summoned(_game(on, faction="guan", at="changshe"))
    p = game.state.player
    p.affinities["huangfusong"] = 20
    game.choose("act:summons")
    msgs = game.choose(f"choice:{pick}")
    assert msgs[1:3] == [reaction, f"皇甫嵩情誼 {affinity - 20:+d}"]  # msgs[0] 是「▸ 選項」那一行
    assert "兩個鄉勇被叫到你面前：「從今天起，他們跟你。」" in msgs and "你升為屯長。" in msgs
    assert "獲得部下：持矛鄉勇、弩手鄉勇" in msgs
    assert (p.rank, p.summons, p.followers, p.affinities["huangfusong"]) == (
        2, None, ["follower_guan_spear", "follower_guan_crossbow"], affinity)
    assert game.status_data()["affiliation"] == "官軍・屯長"
    assert list(game.state.world.promoted_today.values()) == [["甲"]]
    assert ranks.check_summons(game.state, on) == []  # 第 3 階這一版沒有定義：不再發


def test_affinity_clamps_and_needs_a_character(on):
    """情誼夾在 0～100：從 1 扣 3 是 0、訊息寫實際的 -1；效果裡的情誼要是對話人物。"""
    game = _summoned(_game(on, faction="guan", at="changshe"))
    game.state.player.affinities["huangfusong"] = 1
    game.choose("act:summons")
    assert "皇甫嵩情誼 -1" in game.choose("choice:2") and game.state.player.affinities["huangfusong"] == 0
    bad = load_content(CONTENT_DIR)
    bad.events["promo_guan_2"].choices[0].effect.affinity = {"ghost": 3}
    with pytest.raises(ContentError, match="ghost"):
        validate(bad)


def test_explore_at_the_place_opens_the_promotion(on):
    """人在召見的地點探索、交友：直接端出晉升奇遇（照扣體力），不擲其他東西。"""
    game = _summoned(_game(on, faction="guan", at="changshe"))
    stamina = game.state.player.stamina
    game.choose("act:explore")
    assert game.state.pending_event == "promo_guan_2"
    assert game.state.player.stamina == stamina - on.config.action_cost["explore"]
    huang = _summoned(_game(on, name="乙", faction="huang", at="huangjin_camp"), figure="bocai", at="huangjin_camp")
    huang.choose("act:socialize")
    assert huang.state.pending_event == "promo_huang_2"


def test_rank_two_news_is_one_line_per_day(on):
    """兩人同一天升屯長 → 過了那一天，一則陣營軍情「昨日升為屯長的有：甲、乙。」只給官軍；當天還沒發。
    收季時當天的照發（寫「今日」）。"""
    games = []
    for name in ("甲", "乙"):
        game = _summoned(_game(on, name=name, faction="guan", at="changshe"))
        game.choose("act:summons")
        game.choose("choice:1")
        games.append(game)
    news = lambda g: [r for r in g.world.get_season().rumors if "升為屯長" in r.text]  # noqa: E731
    assert news(games[1]) == []
    games[1].advance(calendar.cal_hour_seconds(on, games[1].state.world) * 25)
    [rumor] = news(games[1])
    assert (rumor.text, rumor.layer, rumor.faction) == ("昨日升為屯長的有：甲、乙。", "faction", "guan")
    on.config.admins = ["管"]
    late = _summoned(_game(on, name="丙", faction="guan", at="changshe"))
    late.choose("act:summons")
    late.choose("choice:0")
    _game(on, "管").admin_end_season(now=late.now)
    assert "今日升為屯長的有：丙。" in [r.text for r in news(late)]


def test_switch_off_no_summons(real):
    """開關關著：貢獻再多也不發召見，沒有「應召」，召見地點也端不出奇遇。"""
    game = _game(real, faction="guan", at="changshe")
    game.state.player.contrib = 900
    game.choose("act:rest")
    assert game.state.player.summons is None
    game.choose("act:stand")
    _summoned(game)
    assert "act:summons" not in _ids(game) and ranks.summons_event(game.state, real) is None
