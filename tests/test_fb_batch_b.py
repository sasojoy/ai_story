"""回饋單乙批（PM 2026-10-14 派工：世界、決戰、玉璽、規則、內容）：一張單一段，各自的重現與修正。"""
from __future__ import annotations

import random

from test_discuss import pair  # noqa: F401（fixture）
from test_seal import sealed  # noqa: F401（fixture）
from test_seal_mandate import mandated  # noqa: F401（fixture）

from tianxia import atlas, fusion, seal, social
from tianxia.engine import Game
from tianxia.rules import game_day


def _ids(connections):
    return {c if isinstance(c, str) else c.to for c in connections}


# ── FB-184：官軍沒有操練點 → 潁川郡與長社之間新開「官軍大營」──
# 掛在潁川郊野上（同黃巾別部營寨掛在長社上）：潁川郡 → 潁川郊野 → 長社那條路的中間站，開局兩步走得到。
# 直接接長社，汝南荒野的小地圖上它跟黃巾別部營寨的方向字疊在一起（試過 37 個位置都疊）；也接潁川郡的話，
# 離潁川郡不超過 4.8 分鐘、離草廬 60 以上又不壓到初戰地圖的位置找不到（tests/test_real_map.py、test_real_content.py）


def test_fb184_the_government_army_drills_at_a_camp_between_yingchuan_and_changshe(real):
    c = real
    camp = c.locations["guan_camp"]
    assert _ids(camp.connections) == {"yingchuan_wilds"} and "guan_camp" in _ids(c.locations["yingchuan_wilds"].connections)
    assert {"yingchuan", "changshe"} <= _ids(c.locations["yingchuan_wilds"].connections)  # 潁川郡 → 潁川郊野 → 長社的中間站
    assert atlas.region_of(c, "guan_camp").id == "yingru" and "營寨" in camp.tags
    assert camp.enemies and all(c.squads[e].faction == "guan" for e in camp.enemies)  # 整支都是官軍：官軍的人在這裡只會操練
    assert camp.train_trend == {"yingru": 2}  # 同黃巾別部營寨的兩點、方向相反
    game = Game.new(c, "營中客", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "guan_camp"
    option = next(o for o in game.options() if o.id == "act:train")
    assert option.label.startswith("操練") and "零風險" in option.label
    guan = game.train_trend_push("guan_camp")
    silver = p.stats["silver"]
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs) and game.state.battles == [] and p.stats["silver"] == silver
    p.faction = "huang"
    huang = game.train_trend_push("guan_camp")
    assert guan and set(guan) == set(huang)
    assert all(guan[k] < 0 < huang[k] for k in guan)  # 官軍往官軍那一邊推、黃巾在這裡打贏往黃巾那一邊推


# ── FB-116：玩家互動的漏洞 → 贈物同一個人連送併成一則、同一對人每個遊戲日有上限；論武同一對人每個遊戲日有上限 ──


def test_fb116_gifts_fold_into_one_entry_and_stop_at_the_daily_cap(content):
    from test_social import NOW, _as, _done, _player

    cap = content.config.gift_per_pair_day
    assert cap == 5
    a = _player(content, "甲")
    _player(content, "乙")
    a.state.player.stats["silver"] = 50
    for _ in range(cap):
        assert a.peer_act("乙", "gift", {"arg": "silver", "amount": 1})[0] == "你把銀子 1 兩送給了乙。"
    full = social.GIFT_FULL.format(n=cap)
    assert a.peer_act("乙", "gift", {"arg": "silver", "amount": 1}) == [full]  # 第六次：照樣不收、不寫紀錄
    assert a.state.player.stats["silver"] == 50 - cap
    gifts = [b for b in a.peer_card("乙")["actions"] if b["action"] == "gift"]
    assert gifts and not any(b["enabled"] for b in gifts) and all(b["note"] == full for b in gifts)
    sent = [e for e in a.state.journal if e.title == "贈物・乙"]
    assert len(sent) == 1 and len(sent[0].lines) == cap and sent[0].changes == [f"銀兩 -{cap}"]
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    got = [e for e in b.state.journal if e.title == "收禮・甲"]
    assert len(got) == 1 and len(got[0].lines) == cap and got[0].changes == [f"銀兩 +{cap}"]  # 連送五次：收禮併成一則
    assert b.peer_act("甲", "gift", {"arg": "silver", "amount": 1}) == [full]  # 同一對人：反過來送也算在同一本帳
    key = b._spar_pair("甲")
    b.state.world.gift_tally[key][0] -= 1  # 帳記的是昨天：今天重算
    assert b.peer_act("甲", "gift", {"arg": "silver", "amount": 1})[0] == "你把銀子 1 兩送給了甲。"


def test_fb116_gifts_from_someone_else_in_between_start_a_new_entry(content):
    from test_social import NOW, _as, _done, _player

    a = _player(content, "甲")
    c = _player(content, "丙")
    _player(content, "乙")
    a.state.player.stats["silver"] = c.state.player.stats["silver"] = 10
    a.peer_act("乙", "gift", {"arg": "silver", "amount": 1})
    _done(a)
    c = _as(content, a.world, "丙", NOW + 1)
    c.peer_act("乙", "gift", {"arg": "silver", "amount": 1})
    _done(c)
    a = _as(content, a.world, "甲", NOW + 2)
    a.peer_act("乙", "gift", {"arg": "silver", "amount": 1})
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    assert [e.title for e in b.state.journal[:3]] == ["收禮・甲", "收禮・丙", "收禮・甲"]  # 只併「連著」同一個人送的


def test_fb116_a_pair_discusses_at_most_twice_a_game_day(pair):
    from test_discuss import _accept, _do, _invite

    content, world = pair
    cap = content.config.discuss_per_pair_day
    assert cap == 2
    _invite(content, world, "art:basic_fist")
    assert "烈焰拳" in _accept(content, world, "insight:huo")[0]
    _invite(content, world, "insight:feng")
    # 第二張邀請還在等的時候，這一對人今天的帳被別處用滿了（另一個分頁、假人）：答應那一下重驗，不開爐
    key = "|".join(sorted(("甲", "乙")))
    world.mutate_season(lambda s: s.discuss_tally.update({key: [game_day(content, s), cap]}))
    full = social.DISCUSS_FULL.format(n=cap)
    assert _accept(content, world, "insight:huo", ("風火境", "風助火勢。")) == [full]
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", {"arg": "invite:art:basic_fist"}))
    assert msgs == [full]  # 卡上那一顆也按不下去


# ── FB-157：換版時一個程式沒帶週末設定，這一週會重掛 → 第一季掛過的週（hooked_week）也算掛過；啟動時設定對不上就印警告 ──


def test_fb157_an_old_weekend_save_run_without_the_profile_does_not_post_the_week_again():
    from conftest import real_content

    from tianxia import bounties, calendar
    from tianxia.world import advance_world_state
    from tianxia.world_state import fresh_season

    weekend, plain = real_content("weekend"), real_content()
    season = fresh_season(weekend)  # 週末那一季：開季時蓋了第一季的章
    assert season.season_one and not plain.config.season_one
    week = 3
    season.time = calendar.week_start(week, weekend, season) + 0.5 * calendar.HOUR
    season.hooked_week, season.bounty_week = week, 0  # 舊存檔：第一季的週初掛鉤掛過第 3 週，還沒有 bounty_week
    assert calendar.point(season.time, plain, season).week == week
    advance_world_state(season, plain, calendar.HOUR, random.Random(0))  # 沒帶設定的程式推一步：走規則關著那一條（bounties.tick）
    assert not [b for b in season.bounties if b.week == week] and season.bounty_week == 0


def test_fb157_a_program_without_the_profile_warns_at_start():
    from conftest import real_content

    from tianxia import calendar
    from tianxia.world_state import fresh_season

    weekend, plain = real_content("weekend"), real_content()
    stamped = fresh_season(weekend)
    line = calendar.profile_warning(plain, stamped)
    assert line == calendar.PROFILE_MISMATCH and "TIANXIA_PROFILE" in line
    assert calendar.profile_warning(weekend, stamped) is None  # 設定對得上
    assert calendar.profile_warning(weekend, fresh_season(plain)) is None  # 開關剛打開、還在跑的舊季照舊用 beta 的規則：正常
    assert calendar.profile_warning(plain, None) is None  # 還沒有季


# ── FB-167：「以前不會提前收季」那一句的斷行與時刻寫法 → 時刻寫成跟狀態列一樣的「第 11 天」、整塊不斷行 ──


def test_fb167_the_early_end_time_is_one_unbreakable_block_like_the_status_bar():
    from conftest import real_content

    from tianxia import calendar
    from tianxia.guide import quest_text
    from tianxia.state import new_game_state
    from tianxia.world import early_end_note
    from tianxia.world_state import fresh_season

    content = real_content()
    state = new_game_state(content, "沈浪")
    state.world = fresh_season(content)
    assert calendar.stamp_text(calendar.week_start(10, content, state.world), content, state.world) == "第11天 12:00"
    nbsp = "\u00a0"
    assert early_end_note(state, content) == f"（第{nbsp}11{nbsp}天{nbsp}12:00 以前不會提前收季）"  # 只在「以前」前面斷得開
    assert "第11天" not in quest_text(state, content)


# ── FB-170：打贏波才之後主線寫「波才若未除」 → 第 3 幕那一句不管怎麼進來的都通 ──


def test_fb170_act_three_reads_true_however_it_was_reached(real):
    act = next(a for s in real.scenario.storylines for a in s.acts if a.id == "huangjin_3")
    ways = next(a for s in real.scenario.storylines for a in s.acts if a.id == "huangjin_2").advance_when.any_of
    assert any(c.world_flags_all == ["bocai_defeated"] for c in ways)  # 打贏波才也會進第 3 幕
    assert "波才" not in act.text  # 不寫他還在不在：打贏他、聲勢到 70、第 10 天，三條路進來的都讀得通


# ── FB-174：「你未及趕到」只寫給整場都沒自己出手的人；FB-175：兩份奪璽戰報的時刻照單挑收場那一刻 ──


def test_fb174_a_side_that_played_some_rounds_is_not_written_as_absent(content):
    from test_seal import put_shards
    from test_seal_duel import _duel, _shared

    from tianxia import seal_duel

    put_shards(content)
    st = _shared(content, _duel(phase="muster", starts_real=0.0))
    st.seal_duels[0].challenger.hp = st.seal_duels[0].challenger.hp_cap = 3000.0  # 撐得過兩回合：第二回合才自己出手
    st.seal_duels[0].holder.hp = st.seal_duels[0].holder.hp_cap = 3000.0
    t, acted = 0.0, False
    while st.seal_duels and t < 3000.0:
        d = st.seal_duels[0]
        d.challenger.last_seen = t  # 挑戰者一直開著分頁（在場），可是只在第二回合自己出了一手；懷璽一直不在
        if d.phase == "active" and d.round == 1 and not acted:
            d.pending["challenger"], acted = "強攻", True
        seal_duel.advance(st, content, t)
        t += 20.0
    event = st.seal.history[-1]
    assert acted and event.kind in ("take", "keep")
    assert set(event.proxied) == {"challenger", "holder"}  # 兩邊都被代出過
    assert event.absent == ["holder"]  # 整場一手都沒自己出的只有懷璽
    assert event.at == st.season.time  # FB-175：記下收場那一刻（世界秒）


def test_fb175_both_reports_carry_the_moment_the_duel_closed(sealed, world):
    from test_seal_engine import _finished, _player

    challenger = _finished(sealed, world, taken=True)
    event = world.seal_state().registry.history[-1]
    assert event.at is not None
    old = _player(sealed, world, "懷璽", now=900.0)  # 收場之後好一陣子才同步
    new = _player(sealed, world, challenger, now=1500.0)
    for game in (old, new):
        report = next(b for b in game.state.battles if b.kind == "seal")
        entry = next(e for e in game.state.journal if e.title.startswith("奪璽"))
        assert report.time == event.at and entry.time == event.at and game.state.world.time > event.at
        assert seal.PROXY_LINE in report.notes  # 兩個人都沒來：整場代打，照舊寫「未及趕到」


def test_fb174_some_proxied_rounds_get_the_milder_line(sealed, world):
    from test_seal_engine import _player

    from tianxia.world_state import SealEvent

    game = _player(sealed, world, "懷璽", now=10.0)
    e = SealEvent(seq=99, season=world.get_season_number(), kind="keep", shard="chishou", holder="懷璽", other="挑戰者",
                  result="落敗", edge=30.0, lines=["一句。"], proxied=["holder"], absent=[], at=game.state.world.time)
    game._file_seal(e, "螭首", True)
    notes = game.state.battles[0].notes
    assert seal.PROXY_SOME_LINE in notes and seal.PROXY_LINE not in notes


# ── FB-189：沒有人持有碎片的天命之季，決戰畫面不寫「懷璽的人到場」 ──


def test_fb189_the_holders_clause_only_shows_when_someone_holds_a_shard(mandated, world):
    from test_seal_mandate import _destiny_open, _opened
    from test_seal_mandate import _player as _mandate_player

    _opened(mandated, world)
    game = _mandate_player(mandated, world, "官一", "guan")
    _destiny_open(mandated, world)  # 第 2 輪：七片全都沒人持有
    game.sync(10.0)
    scene = game.scene_text()
    assert "天命之爭：" in scene and seal.MANDATE_WEIGHT not in scene
    assert not seal.holders(world.seal_state().registry)
