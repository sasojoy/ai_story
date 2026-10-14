"""出陣（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第二節）。正式內容、週末設定。
開季：潁川汝南 40；黃巾別部營寨是黃巾的大本營（站黃巾別部、黃巾渠帥，train_trend 潁川汝南 −2）；汝南荒野此刻歸黃巾。"""
from __future__ import annotations

import random
from unittest import mock

from conftest import classic_rules, real_content
from test_real_content import _walk_the_hut

import server
from tianxia import sortie, team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game, drill_share
from tianxia.sqlite_world import open_world
from tianxia.state import Order

TW_MIDNIGHT = 16 * 3600  # UTC 16:00＝台灣 00:00（1970-01-02）


def _game(faction="huang", at="huangjin_camp", profile="weekend", name="沈浪"):
    c = real_content(profile)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location, p.stamina = faction, at, float(c.config.stamina_max)
    p.tutorial_step = len(c.tutorial.steps)  # 引導走完：完成步驟的獎勵不混進心得、經驗的帳
    p.visited.add(at)
    return game


def _sortie(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _fight(tier="大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def test_rangers_and_places_off_the_fronts_have_no_sortie():
    assert _sortie(_game(faction=None, at="changshe")) is None
    assert _sortie(_game(at="wan_city")) is None  # 投靠點，不在戰線上
    assert _sortie(_game(at="luoyang_road")) is None  # 寫的是 front，洛陽沒有戰線


def test_holding_your_own_camp():
    game = _game()
    p, w = game.state.player, game.state.world
    option = _sortie(game)
    assert option.enabled and option.label == "出陣・守（體力 6・今日還能 5 次・零風險）"
    xinde = p.stats.get("xinde", 0)
    msgs = game.choose("act:train")
    assert sortie.HOLD_LINE.format(place="黃巾別部營寨") in msgs
    assert p.stats["xinde"] - xinde == drill_share(35, 0.3)  # 自家經驗最高的一路：黃巾渠帥（心得 35）
    assert w.trends["yingru"] == 41  # 攻的一半：2 × 0.5
    assert game.sorties_left() == 4 and game.state.battles == []
    assert p.stamina == game.content.config.stamina_max - 6


def test_attacking_an_enemy_camp_gives_a_third_and_no_loot():
    game = _game(faction="guan")
    p, w = game.state.player, game.state.world
    assert _sortie(game).label.startswith("出陣・攻（體力 6・今日還能 5 次・")
    silver = p.stats["silver"]
    with _fight():
        game.choose("act:train")
    record = game.state.battles[-1]
    squad = next(q for q in game.content.squads.values() if q.name == record.opponent)
    assert record.kind == "sortie" and record.silver == 0 and record.materials == []
    assert record.xinde == drill_share(squad.reward_xinde, 0.3) and record.exp == drill_share(squad.exp, 0.3)
    assert p.stats["silver"] == silver and w.trends["yingru"] == 38  # 打贏推地點寫的量（2），往官軍那頭
    assert game.state.pending_event is None  # 不接戰後事件（搬到找素材）


def test_losing_an_attack_costs_silver_and_pushes_nothing():
    game = _game(faction="guan")
    game.state.player.stats["silver"] = 100
    with _fight("落敗"):
        game.choose("act:train")
    assert game.state.player.stats["silver"] == 90 and game.state.world.trends["yingru"] == 40


def test_five_a_day_then_grey_until_taiwan_midnight():
    """Review Focus 1：UTC 15:59:59（台灣 23:59:59）用滿五次，下一秒台灣 00:00 又有五次。"""
    game = _game()
    game.now = TW_MIDNIGHT - 1
    for _ in range(5):
        game.choose("act:train")
    option = _sortie(game)
    assert not option.enabled and sortie.USED_UP.format(n=5) in option.label
    assert game.choose("act:train") == ["（此刻無法這麼做。）"]
    game.now = TW_MIDNIGHT
    assert _sortie(game).enabled and game.sorties_left() == 5


def test_advancing_rolls_the_sortie_day():
    """整季機器人只 advance、不 sync：次數照 advanced_real 換日（同回體丹）。now 0＝台灣 08:00。"""
    game = _game()
    for _ in range(5):
        game.choose("act:train")
    assert game.sorties_left() == 0
    game.advance(TW_MIDNIGHT)
    assert game.sorties_left() == 5


def test_the_gentry_stirs_toward_the_middle():
    game = _game(faction="haoqiang", at="runan_wilds")
    w = game.state.world
    assert _sortie(game).label == "出陣・攪局（體力 6・今日還能 5 次・零風險）"
    msgs = game.choose("act:train")
    assert sortie.STIR_LINE.format(place="汝南荒野") in msgs and w.trends["yingru"] == 40  # 0.5：零頭記著
    game.choose("act:train")
    assert w.trends["yingru"] == 41  # 往 50 拉
    w.trends["yingru"] = 50
    game.choose("act:train")
    assert w.trends["yingru"] == 50  # 在 50 什麼都不推


def test_holding_counts_for_the_defend_order_and_attacking_for_the_siege():
    huang = _game()
    huang.state.world.orders.append(Order(id="1:huang:defend:yingru", template="defend", faction="huang", week=1,
                                          front="yingru", quota=99, text=""))
    huang.choose("act:train")
    assert huang.state.world.orders[-1].progress == {"沈浪": 1}
    guan = _game(faction="guan", name="燕青")
    guan.state.world.orders.append(Order(id="1:guan:siege:yingru", template="siege", faction="guan", week=1,
                                         front="yingru", quota=99, text=""))
    with _fight():
        guan.choose("act:train")
    assert guan.state.world.orders[-1].progress == {"燕青": 1}


def test_a_hold_never_asks_the_model():
    game = _game()
    game.client = mock.Mock()
    assert server.may_judge_fight("act:train") and game.fight_request("act:train") is None


def test_the_old_train_and_drill_come_back_with_the_switch_off():
    game = _game()
    classic_rules(game.content)
    assert _sortie(game).label == "操練（體力 6・零風險）"
    assert any("操軍擺陣" in m for m in game.choose("act:train"))


def test_the_prologue_fight_is_named_and_not_counted(world):
    content = real_content()
    content.config.auto_open_first_season = True
    game = Game.new(content, "新人", rng=random.Random(0), world=world, prologue=True)
    _walk_the_hut(game)
    record = game.state.battles[0]
    assert (record.kind, record.tier) == ("train", "險勝") and game.state.player.sortie_day == -1
    assert any(e.title.startswith(sortie.PROLOGUE_FIGHT) for e in game.state.journal)
    step = next(s for s in content.tutorial.steps if s.id == "p8_revenge")
    assert sortie.PROLOGUE_FIGHT in step.text and sortie.PROLOGUE_FIGHT in step.line


def test_the_sortie_line_says_when_today_is_pushed_full_or_used_up():
    """行動列底下那一行（Game._sortie_line）：今天這條線推滿了（_push_room 是 0）就不說推動戰局；次數用完寫什麼時候再來。"""
    from tianxia import calendar, howto

    game = _game(faction="guan")
    line = lambda: game.action_notes([o.id for o in game.options(odds=False)])["act:train"]  # noqa: E731
    assert howto.SORTIE_PUSH in line() and howto.SORTIE_LEFT.format(n=5) in line()
    day = calendar.point(game.state.world.time, game.content, game.state.world).cal_day
    game.state.player.pushed[f"{day}:yingru"] = game.content.config.daily_push_cap
    assert howto.SORTIE_NO_PUSH in line() and howto.SORTIE_PUSH not in line()
    game.state.player.sortie_day, game.state.player.sorties_today = game._pill_day(), 5
    assert line() == sortie.USED_UP.format(n=5) + "。"


def test_the_siege_card_says_sortie():
    from tianxia import atlas

    game = _game()
    order = Order(id="1:huang:siege:yingru", template="siege", faction="huang", week=1, front="yingru", quota=9, text="")
    assert "出陣" in atlas.order_how(game.state, game.content, order) and "遊歷" not in atlas.order_how(game.state, game.content, order)


# ── 守勢行動（PM 2026-10-14 對計畫第 17 條的決定）──────────────────


def _duty(game):
    return next((o for o in game.options() if o.id == "act:duty"), None)


def test_a_duty_spends_a_sortie_and_still_counts_for_the_defend_order():
    """出陣開著時巡哨、傳道、保境安民每用一次扣一次出陣次數（跟攻、守、攪局共用），守城軍令照舊認它。"""
    game = _game()
    game.state.world.orders.append(Order(id="1:huang:defend:yingru", template="defend", faction="huang", week=1,
                                         front="yingru", quota=99, text=""))
    option = _duty(game)
    assert option.enabled and sortie.LEFT_NOTE.format(n=5) in option.label
    game.choose("act:duty")
    assert game.sorties_left() == 4 and game.state.world.orders[-1].progress == {"沈浪": 1}
    assert sortie.LEFT_NOTE.format(n=4) in _sortie(game).label


def test_duties_and_sorties_share_the_five_and_grey_out_with_the_same_line():
    game = _game()
    game.now = TW_MIDNIGHT - 1
    for _ in range(3):
        game.choose("act:train")
    for _ in range(2):
        game.choose("act:duty")
    used_up = sortie.USED_UP.format(n=5)
    assert not _duty(game).enabled and used_up in _duty(game).label
    assert not _sortie(game).enabled and used_up in _sortie(game).label
    assert game.choose("act:duty") == ["（此刻無法這麼做。）"]
    game.now = TW_MIDNIGHT
    assert _duty(game).enabled


def test_rank_actions_do_not_spend_sorties():
    """PM 2026-10-14：只有守勢行動跟出陣共用次數；第 2、3 階（第 4 階同一條路）的行動不扣。"""
    from tianxia import rules

    game = _game(at="julu_altar")
    p = game.state.player
    p.rank = 2
    before = p.stamina
    with mock.patch.object(rules, "check_chance", return_value=1.0):
        game.choose("act:rank2")
        p.rank, p.location = 3, "runan"
        game.choose("act:rank:incite")
    cfg = game.content.config
    assert p.stamina == before - cfg.rank2_stamina - 20  # 兩下都真的做了
    assert game.sorties_left() == 5 and p.sortie_day == -1


def test_a_duty_is_not_counted_with_the_sortie_off():
    game = _game()
    game.content.config.sortie.enabled = False
    game.choose("act:duty")
    assert game.state.player.sortie_day == -1 and "今日還能" not in _duty(game).label
