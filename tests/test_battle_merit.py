"""決戰的個人戰功（Joy 2026-10-10：「戰線推進是陣營，個人的部分有辦法做出戰績跟區別嗎」）：
出手、帶頭佔上風、放手一搏成了、點名打傷、被盯上撐住各記分（battle_instance.merit），戰局條旁列「本場戰功」，
收場時兩軍各一位首功上天下大事傳聞、加名望，玩家卡寫這一季參戰幾場、首功幾次，軍餉照戰功分（最多兩倍）。"""
import json

import pytest
from test_battle_gauge import showdown  # noqa: F401（fixture）
from test_battle_targeting import _battle, _round, gamble  # noqa: F401（fixture）
from test_prologue_web import run

import server
import webharness
from tianxia import battle_instance as bi
from tianxia import social
from tianxia.models import BattleTuning, ShowdownPay

node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def test_every_part_of_the_merit_is_counted(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "guan"), ("姑姑", "huang"), ("丙", "huang")])
    battle.marked["姑姑"] = 0  # 姑姑這一幕顯眼：對面的強攻集火她
    _round(battle, gamble, {"甲": ("生擒姑姑", 40), "乙": "強攻", "姑姑": "固守", "丙": "固守"})
    a, b, gk = (battle.participants[n] for n in ("甲", "乙", "姑姑"))
    assert (a.acted_rounds, a.gambles_won, a.hits_landed) == (1, 1, 1)
    assert gk.stood_marked == 1 and gk.acted_rounds == 1  # 被點名、被集火，回合結束還站著
    points = BattleTuning().merit_points
    assert bi.merit(BattleTuning(), a) == points["acted"] + points["gamble"] + points["hit"]
    assert bi.merit_parts(a) == ["出手 1 回合", "搏成 1 次", "點名打傷 1 次"]
    assert bi.merit_parts(gk)[0] == "出手 1 回合" and bi.merit_parts(gk)[-1] == "被盯上撐住 1 回合"
    assert b.gambles_won == b.hits_landed == 0


def test_an_idle_fighter_has_no_merit_and_the_board_skips_them(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("乙", "guan"), ("丙", "huang")])
    _round(battle, gamble, {"甲": "奇襲", "丙": "固守"})  # 乙沒出手
    battle.round.auto_picked = []
    tuning = BattleTuning()
    assert bi.merit(tuning, battle.participants["乙"]) == 0
    board = bi.merit_board(battle, tuning, "guan", "huang", "乙")
    assert [row["name"] for row in board["left"]] == ["甲"]  # 戰功 0 的不列
    assert board["me"] == {"rank": 2, "of": 2, "merit": 0, "parts": []}
    assert bi.top_merit(battle, tuning, "guan").name == "甲"


def test_the_board_lists_the_top_three_each_side_and_marks_you(gamble):
    people = [(n, "guan") for n in "甲乙丙丁"] + [("戊", "huang")]
    battle = _battle(gamble, people)
    for n, k in zip("甲乙丙丁", (4, 3, 2, 1)):
        battle.participants[n].acted_rounds = k
    board = bi.merit_board(battle, BattleTuning(), "guan", "huang", "丁")
    assert [(r["name"], r["merit"]) for r in board["left"]] == [("甲", 8), ("乙", 6), ("丙", 4)]
    assert board["right"] == [] and board["me"]["rank"] == 4 and board["me"]["of"] == 4


def test_the_gauge_carries_the_board_for_the_viewer(gamble):
    battle = _battle(gamble, [("甲", "guan"), ("丙", "huang")])
    _round(battle, gamble, {"甲": "奇襲", "丙": "固守"})
    g = bi.gauge(battle, gamble, "huang", timetable=False, viewer="丙")
    assert g["merit"]["left"][0]["name"] == "丙" and g["merit"]["left"][0]["mine"]
    assert g["merit"]["me"]["rank"] == 1


def test_old_participants_read_with_no_merit_counters():
    p = bi.BattleParticipant.model_validate({"name": "甲", "faction": "guan", "neili": 1, "neili_cap": 1})
    assert (p.gambles_won, p.hits_landed, p.stood_marked) == (0, 0, 0)


# ── 收場：首功、名望、玩家卡、軍餉 ─────────────────────────────


def _fight(on, a, b, a_tag="battle:act:guan_raid", b_tag="battle:act:huang_hold"):
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()
    for _ in range(20):
        battle = a.world.get_battle()
        if battle.phase == "ended":
            break
        for g, tag in ((a, a_tag), (b, b_tag)):
            now = g.world.get_battle()
            if now.phase == "active" and g.state.player.name not in now.round.pending_actions:
                g.choose(tag)
    a.sync(a.now)
    b.sync(b.now)
    return a.world.get_battle()


def test_each_army_gets_a_first_merit_who_goes_round_the_world(showdown):
    on, a, b = showdown
    fame = (a.state.player.stats.get("fame", 0), b.state.player.stats.get("fame", 0))
    battle = _fight(on, a, b)
    assert battle.phase == "ended"
    line = "宛城之戰論功：官軍首功甲，黃巾軍首功乙。"
    assert line in [r.text for r in a.world.get_season().rumors]
    top = on.config.battle.top_fame
    for g, f in zip((a, b), fame):
        assert (g.state.player.showdowns, g.state.player.top_merits) == (1, 1)
        assert g.state.player.stats["fame"] >= f + top
        entry = next(e for e in g.state.journal if e.battle_id is not None)
        assert any(t.startswith("你的戰功 ") and "排第 1／1" in t for t in entry.lines)
        assert any(t.endswith("這一仗的首功，名字傳遍了江湖。") for t in entry.lines)
    assert social.card(a, b)["record"] == "參戰 1 場・首功 1 次"


def test_a_fresh_player_card_has_no_record(showdown):
    _, a, b = showdown
    assert social.card(a, b)["record"] == ""


def test_pay_follows_merit_up_to_twice_the_old_full_share(showdown):
    on, a, _ = showdown
    on.config.showdown_pay = ShowdownPay()
    battle = bi.BattleInstance(battle_id="t", phase="ended")
    me = bi.BattleParticipant(name=a.state.player.name, faction="guan", neili=1, neili_cap=1, acted_rounds=6)
    assert a._showdown_pay(battle, me, [])[:2] == ["銀兩 +40", "經驗 +60"]  # 只出手 6 回合：一倍，跟以前一樣
    me.led_rounds, me.gambles_won, me.hits_landed = 9, 5, 5  # 戰功遠超過：夾在兩倍
    assert a._showdown_pay(battle, me, [])[:2] == ["銀兩 +80", "經驗 +120"]


@node
def test_the_page_draws_the_merit_board_once_the_fight_is_on(showdown):
    _, a, b = showdown
    m = server.main_view(a)
    assert 'class="g-merit"' not in run(m, "return H.pageJianghu();")  # 集結中不畫
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()
    a.choose("battle:act:guan_raid")
    b.choose("battle:act:huang_hold")
    m = server.main_view(a)
    page = run(m, "return H.pageJianghu();")
    assert 'class="g-merit"' in page and "本場戰功" in page
    assert '<li class="mine"><i>1</i><span>甲</span>' in page and "你排第 1／1・戰功" in page


@node
def test_the_player_card_shows_the_record(showdown):
    _, a, b = showdown
    b.state.player.showdowns, b.state.player.top_merits = 3, 1
    out = run(server.main_view(a), "H.S.peer = { name: '乙', card: CARD }; return H.peerHtml();".replace(
        "CARD", json.dumps(social.card(a, b), ensure_ascii=False)))
    assert '<p class="peer-record">參戰 3 場・首功 1 次</p>' in out
