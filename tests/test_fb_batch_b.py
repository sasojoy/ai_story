"""回饋單乙批（PM 2026-10-14 派工：世界、決戰、玉璽、規則、內容）：一張單一段，各自的重現與修正。"""
from __future__ import annotations

import random

from test_discuss import pair  # noqa: F401（fixture）
from test_fb120_battle_fold import battle, node  # noqa: F401（fixture）
from test_prologue_web import run
from test_seal import sealed  # noqa: F401（fixture）
from test_seal_mandate import mandated  # noqa: F401（fixture）

import server
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
    from conftest import classic_rules

    c = classic_rules(real)  # 操練是舊遊歷的（出陣開著時這裡是出陣・守，見 test_sortie）
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

    from tianxia import materials

    cap = content.config.gift_per_pair_day
    assert cap == 5
    a = _player(content, "甲")
    _player(content, "乙")
    a.state.player.materials = {"gang_1": 50}
    one = f"你把{materials.item_text(content, 'gang_1', 1)}送給了乙。"
    for _ in range(cap):
        assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})[0] == one
    full = social.pair_full(a, "gift")
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1}) == [full]  # 第六次：照樣不收、不寫紀錄
    assert a.state.player.materials["gang_1"] == 50 - cap
    gifts = [b for b in a.peer_card("乙")["actions"] if b["action"] == "gift"]
    assert gifts and not any(b["enabled"] for b in gifts) and all(b["note"] == full for b in gifts)
    sent = [e for e in a.state.journal if e.title == "贈物・乙"]
    assert len(sent) == 1 and len(sent[0].lines) == cap
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    got = [e for e in b.state.journal if e.title == "收禮・甲"]
    assert len(got) == 1 and len(got[0].lines) == cap  # 連送五次：收禮併成一則
    assert b.peer_act("甲", "gift", {"arg": "material", "choice": "gang_1", "amount": 1}) == [full]  # 同一對人：反過來送也算在同一本帳
    key = b._spar_pair("甲")
    b.state.world.gift_tally[key][0] -= 1  # 帳記的是昨天：今天重算
    assert b.peer_act("甲", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})[0].startswith("你把")


def test_fb116_gifts_from_someone_else_in_between_start_a_new_entry(content):
    from test_social import NOW, _as, _done, _player

    give = {"arg": "material", "choice": "gang_1", "amount": 1}
    a = _player(content, "甲")
    c = _player(content, "丙")
    _player(content, "乙")
    a.state.player.materials = {"gang_1": 5}
    c.state.player.materials = {"gang_1": 5}
    _done(c)
    a.peer_act("乙", "gift", give)
    _done(a)
    c = _as(content, a.world, "丙", NOW + 1)
    c.peer_act("乙", "gift", give)
    _done(c)
    a = _as(content, a.world, "甲", NOW + 2)
    a.peer_act("乙", "gift", give)
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    assert [e.title for e in b.state.journal[:3]] == ["收禮・甲", "收禮・丙", "收禮・甲"]  # 只併「連著」同一個人送的


def test_fb116_a_pair_discusses_at_most_twice_a_game_day(pair):
    from test_discuss import _accept, _do, _invite

    content, world = pair
    cap = content.config.discuss_per_pair_day
    assert cap == 2
    _invite(content, world, "insight:feng")
    assert "烈焰境" in _accept(content, world, "insight:huo")[0]  # 武學重構（10/21）：論武只合意境
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    _invite(content, world, f"insight:{made.id}")
    # 第二張邀請還在等的時候，這一對人今天的帳被別處用滿了（另一個分頁、假人）：答應那一下重驗，不開爐
    key = "|".join(sorted(("甲", "乙")))
    world.mutate_season(lambda s: s.discuss_tally.update({key: [game_day(content, s), cap]}))
    full = _do(content, world, "乙", lambda g: social.pair_full(g, "discuss"))[0]
    assert _accept(content, world, "insight:huo", ("風火境", "風助火勢。")) == [full]
    assert world.lookup_insight_recipe(fusion.merge_key(made.id, "huo")) is None
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", {"arg": "invite:insight:feng"}))
    assert msgs == [full]  # 卡上那一顆也按不下去


# ── FB-157：換版時一個程式沒帶週末設定，這一週會重掛 → 第一季掛過的週（hooked_week）也算掛過；啟動時設定對不上就印警告 ──


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
    assert "最後" not in act.text  # 審查：14 天的季打贏波才（kou_boss）可能第 2、3 天就進第 3 幕，不寫還剩多少時間


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


# ── FB-190：玩法說明裡挑戰的幾句插在「情誼」中間 → 另起一段，寫誰能挑戰、閉門不見 ──


def test_fb190_challenges_get_their_own_section_after_the_bond(real, world):
    from tianxia import howto

    cfg = real.config
    page = howto.page(real, world.get_season(), recruitable=False)
    bond = page[page.index("#### 情誼"):page.index(f"#### {howto.CHALLENGE_TITLE}")]
    fight = page[page.index(f"#### {howto.CHALLENGE_TITLE}"):page.index("#### 心得")]
    assert bond.strip().splitlines()[-1] == f"- 換季只帶 {cfg.affinity_carry_ratio * 10:g} 成到下一季。"  # 情誼那一段照舊以它收尾
    assert "聲威" not in bond and "打贏大勢人物本人" not in bond
    assert "投靠了陣營的人" in fight and "散人不能挑戰" in fight and "地方豪強兩邊的人物都能挑戰" in fight
    assert f"{cfg.snub_hours:g} 個現實小時內" in fight and "閉門不見" in fight
    assert f"打贏大勢人物本人，他對你的情誼會掉 {cfg.figure_defeat_affinity}" in fight
    assert howto.CHALLENGE_UNTIMED[2] in fight  # 14 天的季：聲威掉到 0 退場那幾句也在這一段
    cfg.figure_challenge_every_season = False
    assert f"#### {howto.CHALLENGE_TITLE}" not in howto.page(real, world.get_season(), recruitable=False)


# ── FB-136：決戰開打那一刻看不到三招的鈕 → 輪到出招的回合，三招緊接在場景底下，放手一搏的輸入框與說書人的框排在三招後面 ──
# 在 d2827139 上重現（14 天、官軍、騎著馬上陣、老石「要打大仗了」的框還在，375×812）：框 608～738、輸入框與底下那句 746～843、
# 三招 855～999，分頁列頂 756——第一屏一顆都看不到（QA 那時是 733 起）。照在路上的排法（FB-055）：輪到你按的排前面。
# node 裡沒有版面，這裡只比先後；量到的位置寫在試玩回饋那一列

SHOWDOWN_BOX = {"speaker": "老石", "key": "h_showdown", "scene": "", "text": "「要打大仗了。」", "line": "", "done": [], "end": True,
                "pending": False, "full": True, "hint": True}


@node
def test_fb136_in_a_battle_round_the_three_moves_come_right_after_the_scene(battle):
    _, fighter = battle
    m = {**server.main_view(fighter), "guide": SHOWDOWN_BOX}
    assert m["free_text"] is not None and [o["id"] for o in m["options"] if o["id"].startswith("battle:act:")]
    page = run(m, "return H.pageJianghu();")
    scene, moves = page.index('<section class="card scene">'), page.index('<div class="options">')
    free, box = page.index('<form class="free"'), page.index('<section class="card guide"')
    assert scene < moves < free < box
    assert page.index('data-id="battle:act:') < free  # 三招都在輸入框前面（選單那一塊裡）


@node
def test_fb136_outside_a_battle_round_the_box_stays_above_the_actions(battle):
    """不是輪到出招（只能觀戰、平常閒著）：說書人的框照企劃者 10/5 的決定留在行動列上面。"""
    watcher, _ = battle
    m = {**server.main_view(watcher), "guide": SHOWDOWN_BOX}
    page = run(m, "return H.pageJianghu();")
    assert page.index('<section class="card guide"') < page.index('class="act-bar')
