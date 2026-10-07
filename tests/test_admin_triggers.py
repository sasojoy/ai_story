"""管理者觸發鈕（企劃者 2026-10-07：「這些事件都要加到管理員按鈕觸發」；brief 2026-10-07-管理者觸發鈕 第 1～3 組）。

每一顆鈕都叫自然那條路用的同一個函式：測試照「雙胞胎」比——兩份一模一樣的世界，一份讓自然的路走（週一的掛鉤、時刻表、
同步時發的召見、行動之後聽到的線索），一份按鈕，比按完之後的世界與角色。拒絕的每一種都有一個測試。

用真實內容（content/）、週末設定的開關（季長 2.5 天）；人數上限 250（第 4 階兩席，跟 tests/test_seats.py 一樣）。
現實時間由測試給（game.now），time_scale 是 1；管理者是「管」。"""
from __future__ import annotations

import copy
import random

import pytest

from conftest import FixedRandom, real_content
from tianxia import calendar, foreshadow, opportunities, orders, ranks, rules, seats
from tianxia.characters import open_characters
from tianxia.engine import PAUSED_REFUSAL, Game
from tianxia.sqlite_world import open_world

NOW = 1000.0


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季）；季自己開、遊歷打完不接戰後事件；「管」是管理者。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.admins = ["管"]
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 250
    return real


def _game(content, name="管", world=None):
    """一個角色，同步過一次（之後的同步才會推賽季）；不叫模型。"""
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(NOW)
    return game


def _twins(content, tmp_path):
    """兩份一模一樣的世界（各自一個資料庫）與各自的管理者。"""
    return _game(content), _game(content, world=open_world(tmp_path / "twin.db"))


def _week_real(game, week, after=5.0):
    """第 week 週週一 00:00 之後 after 秒的現實時間（從 NOW 起算；time_scale 1）。"""
    return NOW + calendar.week_start(week, game.content, game.state.world) / game.content.config.time_scale + after


def _into_week(game, week, after=5.0):
    game.sync(_week_real(game, week, after))


def _faction_notes(season, since=0):
    return [r.text for r in season.rumors[since:] if r.layer == "faction"]


# ── 第 1 組：立刻發本週軍令 ─────────────────────────────────


def _week_orders(game, week):
    return [o.model_dump() for o in game.world.get_season().orders if o.week == week]


def _credit_defend(game, order, name):
    """照自然的路替這一道守城記功，記到額度（守勢行動一次記一次；達成那一刻套效果）。"""
    season = game.world.get_season()
    game.state.world = season
    for _ in range(order.quota):
        orders.credit(game.state, game.content, order.faction, name, kind="duty", front=order.front)
    game.world.save_season(season)
    game.state.world = game.world.get_season()


def test_issue_orders_redraws_the_unfinished_ones_like_the_monday_hook(on, tmp_path):
    """雙胞胎都自然走進第 2 週（週一的掛鉤發令）。B 這一週達成了一道守城（效果套上去）、另一道有進度，然後按「立刻發本週軍令」
    （審查 I-1）：沒達成的照週一的挑法重挑（跟 A 週一發的一樣、沒有進度），陣營軍情照週一那樣再發一輪，只是少了那一道已達成的；
    已達成的那一道原封不動（還是達成、進度與記下的效果都在），戰況不退回；不動 hooked_week，下週一照常發令。"""
    a, b = _twins(on, tmp_path)
    for game in (a, b):
        _into_week(game, 2)
    monday = calendar.week_start(2, on, a.state.world)
    issued_on_monday = [r.text for r in a.world.get_season().rumors if r.time >= monday - 1 and r.text.startswith(orders.ISSUED)]
    assert issued_on_monday and _week_orders(a, 2) == _week_orders(b, 2)

    week2 = [o for o in b.world.get_season().orders if o.week == 2]
    done = next(o for o in week2 if o.template == "defend")
    _credit_defend(b, done, "甲")
    season = b.world.get_season()
    done_record = next(o for o in season.orders if o.id == done.id).model_dump()
    assert done_record["done"]
    other = next(o for o in season.orders if o.week == 2 and o.id != done.id)
    other.progress = {"乙": 1}
    b.world.save_season(season)
    trends = dict(b.world.get_season().trends)
    hooked = b.world.get_season().hooked_week
    b.state.world = b.world.get_season()
    before = len(b.state.world.rumors)

    [msg] = b.admin_issue_orders()
    after = b.world.get_season()
    mine = _week_orders(b, 2)
    assert [o for o in mine if o["id"] == done.id] == [done_record]  # 已達成的那一道原封不動、只有一道
    assert [o for o in mine if o["id"] != done.id] == [o for o in _week_orders(a, 2) if o["id"] != done.id]  # 沒達成的照週一重挑
    assert [r.text for r in after.rumors[before:]] == [t for t in issued_on_monday if t != f"{orders.ISSUED}{done.text}"]
    assert after.trends == trends  # 達成過的效果留著
    assert after.hooked_week == hooked
    assert f"換掉沒達成的 {len(week2) - 1} 道" in msg and "已達成的 1 道照舊" in msg
    _into_week(b, 3)
    week3 = [o for o in b.world.get_season().orders if o.week == 3]
    assert week3 and b.world.get_season().hooked_week == 3  # 下週一照常發令


def test_a_reissue_cannot_complete_the_same_order_twice(on):
    """審查 I-1：重挑出來的軍令 id 是決定性的（{週}:{陣營}:{種類}:{戰線}），已達成的那一道不能再變成「沒達成」——
    重發之後再記滿一次，戰況不再動（效果不會套兩次）。"""
    admin = _game(on)
    _into_week(admin, 2)
    done = next(o for o in admin.world.get_season().orders if o.week == 2 and o.template == "defend")
    _credit_defend(admin, done, "甲")
    first = rules.trend_value(admin.state, on, done.front)
    admin.admin_issue_orders()
    assert [o.done for o in admin.world.get_season().orders if o.id == done.id] == [True]
    _credit_defend(admin, done, "乙")
    assert rules.trend_value(admin.state, on, done.front) == first


def test_next_monday_still_sees_a_siege_completed_before_the_reissue(on):
    """審查 I-1：下週一發令時，「敵方上週攻下過這條戰線」（or_enemy_siege）讀的是上週已達成的攻城：重發不能把它拿掉。"""
    from tianxia.state import Order

    admin = _game(on)
    _into_week(admin, 2)
    siege = Order(id="2:guan:siege:yingru", template="siege", faction="guan", week=2, front="yingru", quota=4, text="（測試）",
                  done=True, applied=3, progress={"甲": 4})
    admin.world.mutate_season(lambda s: s.orders.append(siege))
    admin.state.world = admin.world.get_season()
    admin.admin_issue_orders()
    season = admin.world.get_season()
    assert [o for o in season.orders if o.id == siege.id] == [siege]
    admin.state.world = season
    assert orders._enemy_sieged_last_week(admin.state, "huang", "yingru", 3)  # noqa: SLF001  _issuable 讀的就是它


def test_issue_orders_refusals(on):
    player = _game(on, "甲")
    assert player.admin_issue_orders() == ["（只有管理者能發本週軍令。）"]
    admin = _game(on)
    before = admin.world.get_season().orders
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_issue_orders() == [PAUSED_REFUSAL]
    assert admin.world.get_season().orders == before


def test_issue_orders_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_issue_orders() == ["（這一季沒有軍令。）"]


# ── 第 1 組：立刻輪替第 4 階席次 ─────────────────────────────


LEDGER = {"guan": {"乙": {1: 50}, "丙": {1: 40}, "甲": {1: 7}}}


def test_rotate_seats_matches_the_monday_rotation_and_leaves_monday_to_run(on, tmp_path):
    """A 的帳在週一之前就有上一週的貢獻：自然走進第 2 週時輪替（乙、丙上任、發一則名單）。B 週一時帳是空的（沒有輪替），
    帳補成跟 A 一樣之後按鈕：在任的人、發的那一則名單都跟 A 週一一樣；hooked_week 不動，第 3 週週一照常再排一次。"""
    a, b = _twins(on, tmp_path)
    a.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    monday_notes_from = len(a.world.get_season().rumors)
    for game in (a, b):
        _into_week(game, 2)
    sa = a.world.get_season()
    roster_a = [t for t in _faction_notes(sa, monday_notes_from) if t.startswith("本週在任的")]
    assert sa.seats["guan"] == ["乙", "丙"] and roster_a == ["本週在任的校尉：乙、丙。"]
    assert b.world.get_season().seats == {}

    b.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    b.state.world = b.world.get_season()
    before = len(b.state.world.rumors)
    [msg] = b.admin_rotate_seats()
    sb = b.world.get_season()
    assert sb.seats == sa.seats
    assert _faction_notes(sb, before) == roster_a
    assert sb.hooked_week == 2 and "下週一照常" in msg and "乙、丙" in msg
    _into_week(b, 3)
    assert _faction_notes(b.world.get_season()).count("本週在任的校尉：乙、丙。") == 2  # 第 3 週週一照常排


def test_rotate_seats_refusals(on):
    player = _game(on, "甲")
    assert player.admin_rotate_seats() == ["（只有管理者能輪替第 4 階席次。）"]
    admin = _game(on)
    admin.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    assert admin.admin_rotate_seats() == ["（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）"]
    _into_week(admin, 2)
    admin.world.mutate_season(lambda s: s.seats.clear())
    admin.state.world = admin.world.get_season()
    assert admin.world.pause_clock(_week_real(admin, 2, 10))  # 暫停中：跟自然的路一樣，不排、不補
    assert admin.admin_rotate_seats() == [PAUSED_REFUSAL]
    assert admin.world.get_season().seats == {}


def test_rotate_seats_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_rotate_seats() == ["（這一季沒有第 4 階席次。）"]
    assert seats.SEAT_RANK == 4


# ── 第 3 組：三場大戲 ─────────────────────────────────────


def _battle(game):
    battle = game.world.get_battle()
    return None if battle is None or battle.phase == "ended" else battle


def test_start_showdown_opens_exactly_as_the_timetable_would(on, tmp_path):
    """雙胞胎同一刻：A 讓時刻表自然開長社（排定的時間就是此刻，季的事把它記進等著開的、推進之後開集結——world 的同一串函式），
    B 按「立刻開這一場」。兩邊開出來的那一場（哪一筆、起點、集結截止……整份）、集結號角、開過的記號一模一樣。"""
    from tianxia import world as world_mod

    a, b = _twins(on, tmp_path)

    def due_now(season):
        season.schedule["changshe_fire"] = season.time
        world_mod._note_due_showdowns(world_mod._season_vehicle(on, season), on)  # noqa: SLF001  季的事那一步
    a.world.mutate_season(due_now)
    natural = world_mod.start_pending_battle(a.world, on, NOW)
    pressed = b.admin_start_showdown("changshe_fire", NOW)
    assert natural == pressed == ["🛡️ 【全服戰報】長社火攻的集結號角已經吹響！"]
    assert b.world.get_battle().model_dump() == a.world.get_battle().model_dump()
    assert b.world.get_season().showdowns_opened == a.world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}


def test_an_early_start_counts_as_happened_so_the_date_passes_quietly(on):
    """第 1 週就開了長社、取消掉（時間軸上沒有結果，只剩開過的記號）：排定的日子過了也不再開集結。"""
    admin = _game(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    first = admin.world.get_battle().record_id
    admin.admin_cancel_battle()
    season = admin.world.get_season()
    assert "changshe_fire" not in season.timeline and "changshe_fire" in season.showdowns_opened
    cal_hour = calendar.cal_hour_seconds(on, season)
    past = NOW + (season.schedule["changshe_fire"] + 3 * cal_hour - season.time)
    admin.sync(past)
    after = admin.world.get_season()
    assert after.time > season.schedule["changshe_fire"] and "changshe_fire" not in after.showdowns_waiting
    assert admin.world.get_battle() is None  # 沒有第二場
    assert [battle.record_id for _, battle in admin.world.ended_battles()] == [first]
    assert admin.admin_start_showdown("changshe_fire", past) == ["（長社火攻已經開打過了。）"]


def test_an_active_battle_blocks_the_buttons(on):
    admin = _game(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    battle = admin.world.get_battle().model_dump()
    assert admin.admin_start_showdown("guangzong", NOW) == ["（已經有一場戰鬥在進行。）"]
    assert admin.world.get_battle().model_dump() == battle and "guangzong" not in admin.world.get_season().showdowns_opened
    notes = {event.id: why for event, why in admin.admin_showdowns()}
    assert notes["guangzong"] == "（已經有一場戰鬥在進行。）" and notes["changshe_fire"] == "（長社火攻已經開打過了。）"


@pytest.mark.parametrize(("week3", "battle_id"), [("成", "wancheng_jia"), ("不成", "wancheng_yi")])
def test_wancheng_takes_the_version_the_rule_picks(on, week3, battle_id):
    """宛城看第 3 週（張曼成攻殺南陽太守）的結果：還沒結算時按不下去、說要等它；結算之後開的是那一版。"""
    admin = _game(on)
    assert admin.admin_start_showdown("wancheng", NOW) == ["（宛城之戰要等張曼成攻殺南陽太守結算了才知道是哪一版。）"]
    assert admin.world.get_battle() is None
    admin.admin_resolve_event("zhangmancheng_wan", week3)
    admin.admin_start_showdown("wancheng", NOW)
    assert _battle(admin).battle_id == battle_id
    assert admin.world.get_season().showdowns_opened == {"wancheng": battle_id}


def test_start_showdown_refusals(on):
    player = _game(on, "甲")
    assert player.admin_start_showdown("changshe_fire", NOW) == ["（只有管理者能開這一場決戰。）"]
    admin = _game(on)
    assert admin.admin_start_showdown("luzhi_siege", NOW) == ["（時刻表上沒有這一場決戰。）"]
    assert admin.admin_start_showdown("nope", NOW) == ["（時刻表上沒有這一場決戰。）"]
    admin.admin_resolve_event("changshe_fire", "guan:大勝")
    assert admin.admin_start_showdown("changshe_fire", NOW) == ["（長社火攻已經結算了。）"]
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_start_showdown("guangzong", NOW + 2) == [PAUSED_REFUSAL]
    assert admin.world.get_battle() is None


def test_start_showdown_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_start_showdown("changshe_fire", NOW) == ["（這一季沒有時刻表。）"]
    assert admin.admin_showdowns() == [] and admin.world.get_battle() is None


# ── 第 2 組：玩家個人劇情 ─────────────────────────────────────


def _member(content, name, faction="guan", *, rank=1, at=None, save=True):
    """一個陣營裡的玩家，同步過一次；save 為真時存進角色存檔（管理者照名號從存檔裡找他）。"""
    game = Game.new(content, name, rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    game.sync(NOW)
    if save:
        open_characters().save(game.state)
    return game


def _saved(admin, name):
    """存檔裡的那個人（接上共用賽季，才讀得到機緣、伏筆這些看賽季的東西）。"""
    state = open_characters().load(name)
    state.world = admin.world.get_season()
    return state


def _entry(state, title):
    [entry] = [e for e in state.journal if e.title == title]
    return entry


def _said(entry):
    return entry.lines + entry.changes


@pytest.mark.parametrize("rank", [1, 2])
def test_summon_issues_the_same_summons_as_reaching_the_threshold(on, rank):
    """雙胞胎：甲的貢獻（第 3 階另加一種機緣）到了、同步時自然收到召見；乙什麼都沒有，管理者替他發。召見（哪一階、誰出面、在哪、
    第幾段、演哪一則）、摸清的路、江湖紀錄那一句都一樣；乙的貢獻照舊是 0（門檻是略過，不是補上）。"""
    admin = _game(on)
    natural = _member(on, "甲", rank=rank, save=False)
    natural.state.player.contrib = ranks.threshold(on, rank + 1)
    if rank + 1 >= 3:
        natural.state.player.opp_done = ["guan_courier"]
    natural.sync(NOW)
    assert natural.state.player.summons is not None
    _member(on, "乙", rank=rank)
    [msg] = admin.admin_summon("乙")
    saved = _saved(admin, "乙")
    assert saved.player.summons.model_dump() == natural.state.player.summons.model_dump()
    assert saved.player.surveyed == natural.state.player.surveyed and saved.player.surveyed
    entry = _entry(saved, "召見")
    told = _entry(natural.state, "召見")  # 審查 M-1：他那一則跟自然收到的一模一樣，不寫是管理者發的
    assert (entry.title, entry.tag, entry.lines, entry.changes) == (told.title, told.tag, told.lines, told.changes)
    assert entry.tag != "管理者" and _entry(admin.state, "發召見").tag == "管理者"  # 管理者自己那一則照舊標
    assert saved.player.contrib == 0 and saved.player.opp_done == []
    assert msg == f"已替乙發第 {rank + 1} 階的召見：{_said(entry)[0]}"
    assert _entry(admin.state, "發召見").lines == [msg]


def test_summon_refusals(on, monkeypatch):
    admin = _game(on)
    assert _game(on, "路人").admin_summon("乙") == ["（只有管理者能發召見。）"]
    assert admin.admin_summon("沒這人") == ["（江湖上沒有「沒這人」這個人。）"]
    _member(on, "散", faction=None)
    assert admin.admin_summon("散") == ["（散是散人，沒有陣營可以召見他。）"]
    _member(on, "乙")
    admin.admin_summon("乙")
    assert admin.admin_summon("乙") == ["（乙手上已經有一張第 2 階的召見了。）"]
    seated = _member(on, "丙", rank=3)
    seated.state.player.qualified = True
    open_characters().save(seated.state)
    assert admin.admin_summon("丙") == ["（丙已經取得第 4 階的資格了。）"]
    _member(on, "丁", rank=2)
    with monkeypatch.context() as patch:  # 只換這一段（不能 undo 整個 monkeypatch：conftest 換掉的資料庫路徑也會被還原）
        patch.setattr(ranks, "current_cast", lambda *args, **kwargs: None)  # 第 3 階第一段此刻沒有人能出面（裁決 E3）
        assert admin.admin_summon("丁") == [f"（第 3 階此刻沒有人能出面召見丁：{ranks.NO_PRESENTER['guan']}）"]
    stalled = open_characters().load("丁").player
    assert stalled.summons is None and stalled.summons_stall == ""  # 拒絕：他的存檔不留「說過了」的記號
    on.promotions = [x for x in on.promotions if not (x.faction == "guan" and x.rank == 4)]
    _member(on, "戊", rank=3)
    assert admin.admin_summon("戊") == ["（戊已經升到頂了。）"]
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_summon("戊") == [PAUSED_REFUSAL]


def test_summon_refused_with_the_switch_off(real):
    admin = _game(real)
    _member(real, "乙")
    assert admin.admin_summon("乙") == ["（這一季沒有陣營的階級，發不了召見。）"]
    assert open_characters().load("乙").player.summons is None


def test_the_target_is_caught_up_before_the_admin_acts(on):
    """跟伺服器替每個人做動作一樣（重讀 → 同步 → 動作 → 存檔）：先把他補算到此刻（體力照他自己的步調回、對時點換成此刻），再發召見、存回去。"""
    admin = _game(on)
    target = _member(on, "乙", save=False)
    target.state.player.stamina = 0.0
    target.state.last_real = NOW - 600
    open_characters().save(target.state)
    admin.admin_summon("乙")
    saved = open_characters().load("乙")
    assert saved.last_real == NOW and saved.player.stamina > 0 and saved.player.summons is not None


def test_the_name_is_matched_like_the_saves_and_the_admin_can_target_himself(on):
    """名號照角色存檔的比法（不分大小寫、不管前後空白）；填自己的名號就是自己這一份（伺服器動作結束時存的就是它）。"""
    admin = _game(on)
    _member(on, "Ruby")
    admin.admin_summon("  ruby ")
    assert open_characters().load("Ruby").player.summons is not None
    admin.state.player.faction = "guan"
    admin.admin_summon("管")
    assert admin.state.player.summons is not None and _entry(admin.state, "召見").tag == ""


# ── 給他一個機緣：每一種 ─────────────────────────────────


def test_timing_gives_the_clue_exactly_as_hearing_it(on):
    """天時地利型：自然那一刻是聽到線索（花體力的行動之後在潁川汝南擲中）。管理者給的：記進同一份聽過的線索、紀錄同一句。"""
    admin = _game(on)
    natural = _member(on, "甲", save=False)
    heard = opportunities.hear_clues(natural.state, on, "yingru", FixedRandom(0.0), world=natural.world)
    assert natural.state.player.opp_clues == ["guan_courier"]
    _member(on, "乙")
    [msg] = admin.admin_give_opportunity("乙", "guan_courier")
    saved = _saved(admin, "乙")
    assert saved.player.opp_clues == natural.state.player.opp_clues
    entry = _entry(saved, "聽聞")  # 審查 M-1：自然聽到線索不會說出是哪一個機緣，也不寫是管理者給的
    assert _said(entry) == heard and entry.tag == ""
    assert not any(e.title.startswith("機緣") for e in saved.journal)
    assert opportunities.heard_clues(saved, on) == opportunities.heard_clues(natural.state, on)  # 見聞頁的個人線索
    assert msg.startswith("已給乙機緣「荒丘的信使」：聽到了線索")
    assert admin.admin_give_opportunity("乙", "guan_courier") == ["（乙已經聽過「荒丘的信使」的線索。）"]


def test_accumulate_reaches_the_milestone_exactly_as_counting_up(on):
    """累積型：自然那一刻是第 n 次湊滿、拿到東西（第 2 階行動成功 n 次）。管理者給的：次數、東西、要送去的戰線、那一句都一樣，
    送的選項在官軍主將那裡就按得下去。"""
    admin = _game(on)
    natural = _member(on, "甲", at="changshe", save=False)
    said = []
    for _ in range(50):
        said = opportunities.after_success(natural.state, on, "rank2", "changshe", random.Random(0))
        if "guan_deserter" in natural.state.player.opp_items:
            break
    _member(on, "乙", at="changshe")
    admin.admin_give_opportunity("乙", "guan_deserter")
    saved = _saved(admin, "乙")
    p, q = saved.player, natural.state.player
    assert (p.opp_counts, p.opp_items, p.opp_fronts) == (q.opp_counts, q.opp_items, q.opp_fronts)
    assert p.opp_fronts == {"guan_deserter": "yingru"}  # 長社在潁川汝南：降卒要送去那條戰線的官軍主將
    entry = _entry(saved, "機緣・降卒的消息")
    assert _said(entry) == said[-1:] and entry.tag == ""
    assert admin.admin_give_opportunity("乙", "guan_deserter") == ["（乙已經拿到知道運糧小道的降卒了，送去就完成。）"]


def test_bond_raises_the_affinity_to_where_the_topic_appears(on):
    """情誼型：自然那一刻是情誼到了話題出現的門檻（跟他交談時選單上多一個話題）。管理者給的：情誼補到門檻（跟事件加情誼同一條）。"""
    admin = _game(on)
    _member(on, "乙")
    before = _saved(admin, "乙")
    assert not any(o.id == "talk:opp:guan_zhujun" for o in opportunities.talk_options(before, on, "zhujun"))
    admin.admin_give_opportunity("乙", "guan_zhujun")
    saved = _saved(admin, "乙")
    need = foreshadow.need(on, next(o for o in on.opportunities if o.id == "guan_zhujun").bond.affinity)
    assert saved.player.affinities["zhujun"] == need
    assert any(o.id == "talk:opp:guan_zhujun" for o in opportunities.talk_options(saved, on, "zhujun"))
    entry = _entry(saved, "機緣・朱儁的出身")
    assert _said(entry) == [f"朱儁情誼 +{need}"] and entry.tag == ""
    assert admin.admin_give_opportunity("乙", "guan_zhujun") == [
        f"（乙跟朱儁的情誼已經到 {need}，話題「出身」已經在對話選單上。）"]


def test_the_bond_entry_says_what_else_the_affinity_changes(on):
    """審查 M-5：情誼型補的是真的情誼——清單上那一項帶一句話（確認框照它問），數字照程式算：招募成算多幾個百分點
    （roster.recruit_chance）、換季帶幾成（Config.affinity_carry_ratio）；其他種類沒有這一句。"""
    admin = _game(on)
    _member(on, "乙")
    view = admin.admin_player_choices("乙")
    notes = {x["id"]: x["note"] for x in view["opportunities"]}
    need = foreshadow.need(on, next(o for o in on.opportunities if o.id == "guan_zhujun").bond.affinity)
    cfg = on.config
    gain = round((min(0.95, cfg.recruit_base_chance + need / 100 * cfg.recruit_affinity_bonus) - cfg.recruit_base_chance) * 100)
    note = notes["guan_zhujun"]
    assert f"朱儁情誼 0→{need}" in note and f"招募他的成算約 +{gain} 個百分點" in note
    assert f"換季帶 {cfg.affinity_carry_ratio:.0%}（{int(need * cfg.affinity_carry_ratio)} 點）" in note
    assert "伏筆的對話片段" in note and "（他現在不在招募名單上）" in note  # 朱儁是 locked：招募名單上沒有他
    assert notes["guan_courier"] == notes["guan_deserter"] == ""


def test_puzzle_hands_over_every_piece_so_presenting_is_next(on):
    admin = _game(on)
    _member(on, "乙", rank=3)
    admin.admin_give_opportunity("乙", "guan_three_plans")
    saved = _saved(admin, "乙")
    o = next(x for x in on.opportunities if x.id == "guan_three_plans")
    assert saved.player.opp_pieces["guan_three_plans"] == [piece.key for piece in o.puzzle.pieces]
    ids = [x.id for x in opportunities.place_options(saved, on, o.puzzle.present.at)]
    assert "opp:present:guan_three_plans" in ids  # 下一步：到呈交的地方交出去
    assert admin.admin_give_opportunity("乙", "guan_three_plans") == ["（「平亂三策」要的東西乙都湊齊了。）"]


def test_deduce_tells_every_trait_of_this_seasons_mole_as_hearing_them_would(on):
    """推理型：自然那一刻是在各大區聽到內鬼的特徵。雙胞胎：甲在每個大區一直聽到聽不到為止；乙由管理者給——聽過的特徵一樣。"""
    admin = _game(on)
    natural = _member(on, "甲", faction="huang", rank=3, save=False)
    o = next(x for x in on.opportunities if x.id == "huang_mole")
    for region in {t.region for t in o.deduce.traits}:
        for _ in range(10):
            opportunities.hear_clues(natural.state, on, region, FixedRandom(0.0), world=natural.world)
    mole = {k for k in natural.state.player.opp_clues if k.startswith("huang_mole:")}
    assert mole
    _member(on, "乙", faction="huang", rank=3)
    admin.admin_give_opportunity("乙", "huang_mole")
    saved = _saved(admin, "乙")
    assert {k for k in saved.player.opp_clues if k.startswith("huang_mole:")} == mole
    entry = _entry(saved, "聽聞")
    assert len(_said(entry)) == len(mole) and entry.tag == ""
    assert admin.admin_give_opportunity("乙", "huang_mole") == ["（內鬼的特徵乙都聽過了。）"]


def test_opportunity_refusals(on):
    admin = _game(on)
    assert _game(on, "路人").admin_give_opportunity("乙", "guan_courier") == ["（只有管理者能給機緣。）"]
    _member(on, "乙")
    _member(on, "散", faction=None)
    assert admin.admin_give_opportunity("乙", "nope") == ["（沒有這個機緣。）"]
    assert admin.admin_give_opportunity("沒這人", "guan_courier") == ["（江湖上沒有「沒這人」這個人。）"]
    assert admin.admin_give_opportunity("乙", "huang_dawn") == ["（「黎明祭天」是黃巾軍的機緣，乙是官軍的人。）"]
    assert admin.admin_give_opportunity("散", "guan_courier") == ["（「荒丘的信使」是官軍的機緣，散是散人。）"]
    assert admin.admin_give_opportunity("乙", "guan_three_plans") == ["（「平亂三策」是第 4 階的機緣，乙要先升到第 3 階。）"]
    done = _member(on, "丙", rank=3)
    done.state.player.opp_done = ["guan_courier"]
    open_characters().save(done.state)
    assert admin.admin_give_opportunity("丙", "guan_courier") == ["（丙已經完成過「荒丘的信使」。）"]
    assert admin.admin_give_opportunity("丙", "guan_three_roads") == [opportunities.PLOT_NO_OFFER]
    assert open_characters().load("乙").player.opp_clues == []
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_give_opportunity("乙", "guan_courier") == [PAUSED_REFUSAL]


def test_opportunity_refused_with_the_switch_off(real):
    admin = _game(real)
    _member(real, "乙")
    assert admin.admin_give_opportunity("乙", "guan_courier") == ["（這一季沒有機緣。）"]


# ── 給他一個伏筆片段 ─────────────────────────────────


def test_fragment_is_added_exactly_as_hearing_it(on):
    """雙胞胎：甲在老船夫的事件裡自然聽到長社（官軍）那條的第 2 則；乙由管理者給同一則——聽過的片段、紀錄那一句一樣（天機的風向照填）。
    不發傳聞、不碰鎖定；給管理者的那一句不寫片段的原文。"""
    admin = _game(on)
    natural = _member(on, "甲", save=False)
    heard = foreshadow.hear_from_event(natural.state, on, "fs_ev_boatman", natural.world)
    assert natural.state.player.fragments == {"fs_changshe_guan": [1]}
    _member(on, "乙")
    season = admin.world.get_season()
    rumors, locks = len(season.rumors), dict(season.locks)
    [msg] = admin.admin_give_fragment("乙", "fs_changshe_guan:1")
    saved = _saved(admin, "乙")
    assert saved.player.fragments == natural.state.player.fragments
    entry = _entry(saved, "聽聞")
    assert _said(entry) == heard and entry.tag == ""
    assert _entry(admin.state, "給伏筆片段").tag == "管理者"
    assert foreshadow.heard_texts(saved, on, admin.world) == foreshadow.heard_texts(natural.state, on, natural.world)
    after = admin.world.get_season()
    assert len(after.rumors) == rumors and after.locks == locks
    assert msg == "已讓乙聽到長社火攻那條伏筆的第 2 則片段。"
    assert admin.admin_give_fragment("乙", "fs_changshe_guan:1") == ["（乙已經聽過這一則了。）"]


def test_fragment_refusals(on):
    admin = _game(on)
    assert _game(on, "路人").admin_give_fragment("乙", "fs_changshe_guan:0") == ["（只有管理者能給伏筆片段。）"]
    _member(on, "乙")
    _member(on, "散", faction=None)
    for ref in ("nope:0", "fs_changshe_guan:9", "fs_changshe_guan:x", "fs_changshe_guan"):
        assert admin.admin_give_fragment("乙", ref) == ["（沒有這一則伏筆片段。）"], ref
    assert admin.admin_give_fragment("沒這人", "fs_changshe_guan:0") == ["（江湖上沒有「沒這人」這個人。）"]
    assert admin.admin_give_fragment("乙", "fs_changshe_huang:0") == ["（這條伏筆是黃巾軍的，乙是官軍的人。）"]
    assert admin.admin_give_fragment("散", "fs_changshe_guan:0") == ["（這條伏筆是官軍的，散是散人。）"]
    done = _member(on, "丙")
    done.state.player.fs_done = ["fs_changshe_guan"]
    open_characters().save(done.state)
    assert admin.admin_give_fragment("丙", "fs_changshe_guan:0") == ["（丙已經走完這條伏筆的最後一步。）"]
    admin.admin_resolve_event("changshe_fire", "guan:大勝")
    assert admin.admin_give_fragment("乙", "fs_changshe_guan:0") == ["（長社火攻已經發生了，這條伏筆用不上了。）"]
    assert open_characters().load("乙").player.fragments == {}
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_give_fragment("乙", "fs_luzhi_guan:0") == [PAUSED_REFUSAL]


def test_fragment_refused_with_the_switch_off(real):
    admin = _game(real)
    _member(real, "乙")
    assert admin.admin_give_fragment("乙", "fs_changshe_guan:0") == ["（這一季沒有伏筆。）"]


# ── 查一個玩家（管理者區的清單）─────────────────────────────


def test_player_choices_list_only_what_can_apply(on):
    admin = _game(on)
    _member(on, "乙", at="changshe")
    view = admin.admin_player_choices("乙")
    assert view["name"] == "乙" and view["line"].startswith("乙：官軍・")
    assert view["summons"] == {"ok": True, "note": "會發第 2 階的召見"}
    assert [x["id"] for x in view["opportunities"]] == ["guan_zhujun", "guan_courier", "guan_deserter"]  # 第 3 階的、官軍的
    assert view["opportunities"][1]["label"] == "官軍・第 3 階・荒丘的信使（天時地利型）"
    guan_chains = [c for c in on.foreshadows.chains if c.side == "guan"]
    assert [x["id"] for x in view["fragments"]] == [f"{c.id}:{i}" for c in guan_chains for i in range(len(c.fragments))]
    assert "{風向}" in next(x["label"] for x in view["fragments"] if x["id"] == "fs_changshe_guan:1")  # 原文照內容檔，天機不填
    admin.admin_give_opportunity("乙", "guan_courier")
    admin.admin_give_fragment("乙", "fs_changshe_guan:1")
    admin.admin_summon("乙")
    view = admin.admin_player_choices("乙")
    assert "guan_courier" not in [x["id"] for x in view["opportunities"]]
    assert "fs_changshe_guan:1" not in [x["id"] for x in view["fragments"]]
    assert view["summons"] == {"ok": False, "note": "（乙手上已經有一張第 2 階的召見了。）"}
    assert admin.admin_player_choices("沒這人") == {"refusal": "（江湖上沒有「沒這人」這個人。）"}
    assert _game(on, "路人").admin_player_choices("乙") == {"refusal": "（只有管理者能查玩家。）"}
