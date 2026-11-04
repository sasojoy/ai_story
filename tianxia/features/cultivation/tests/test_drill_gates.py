"""遭遇的三道閘（減法季整合設計 4.2；主機側實作計畫 Task 2-4）的純規則：疲勞、對手要配得上你、45 級以後只認打出來的經驗。

批 0 的 `Config.jianfa` 還沒到：數字吃 `tianxia/jianfa_numbers.py` 的 `JianfaNumbers`，這裡直接建它。引擎接線（遭遇拍乘兩道閘、
`PlayerState.fights_today`、十一處給經驗的地方標來源、`team.add_exp` 的來源）在批 0 之後。"""
import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import growth, team
from tianxia.jianfa_numbers import JianfaNumbers

CFG = JianfaNumbers()


# ── 第一道：疲勞 ──────────────────────────────────────────────


def test_the_first_15_fights_of_a_day_are_full():
    assert [growth.fatigue_factor(CFG, n) for n in range(1, 16)] == [1.0] * 15


def test_from_the_16th_fight_each_one_gives_0_8_of_the_last_down_to_0_3():
    f = [growth.fatigue_factor(CFG, n) for n in range(15, 31)]
    assert f[1] == pytest.approx(0.8 * f[0])  # 第 16 場是第 15 場的 0.8 倍
    assert f[2] == pytest.approx(0.8 * f[1])  # 疊加
    assert f[-1] == pytest.approx(0.3)  # 第 30 場夾在 0.3
    assert min(f) == pytest.approx(0.3) and f == sorted(f, reverse=True)
    assert growth.fatigue_factor(CFG, 21) == pytest.approx(0.3)  # 0.8 的 6 次方 0.262 已經低於 0.3


def test_fights_are_counted_per_day_and_reset_when_the_day_turns():
    assert growth.nth_fight(fight_day=5, fights_today=0, today=5) == 1
    assert growth.nth_fight(fight_day=5, fights_today=15, today=5) == 16
    assert growth.nth_fight(fight_day=5, fights_today=40, today=6) == 1  # 換日歸零
    assert growth.nth_fight(fight_day=None, fights_today=0, today=6) == 1  # 舊存檔沒有這一天


# ── 第二道：對手要配得上你 ──────────────────────────────────────


def test_a_foe_at_or_above_your_band_gives_full():
    assert growth.outlevel_factor(CFG, level=20, difficulty=20) == 1.0
    assert growth.outlevel_factor(CFG, level=29, difficulty=20) == 1.0  # 同一檔（20～29）
    assert growth.outlevel_factor(CFG, level=20, difficulty=60) == 1.0


def test_one_band_below_halves_and_two_or_more_give_a_tenth():
    assert growth.outlevel_factor(CFG, level=20, difficulty=15) == 0.5  # 低一檔
    assert growth.outlevel_factor(CFG, level=20, difficulty=8) == 0.1  # 低兩檔（地痞）
    assert growth.outlevel_factor(CFG, level=45, difficulty=15) == 0.1  # 低三檔也是一成
    assert growth.outlevel_factor(CFG, level=9, difficulty=8) == 1.0  # 9 級打地痞還是同一檔


def test_the_band_width_and_steps_come_from_the_numbers():
    wide = JianfaNumbers(drill_outlevel_band=20, drill_outlevel_steps=(0.6, 0.3, 0.05))
    assert growth.outlevel_factor(wide, level=45, difficulty=35) == 0.6
    assert growth.outlevel_factor(wide, level=45, difficulty=15) == 0.3
    assert growth.outlevel_factor(wide, level=65, difficulty=8) == 0.05


# ── 第三道：45 級以後只認打出來的經驗 ────────────────────────────


def test_every_fight_counts_as_battle_and_the_rest_do_not():
    """設計 4.2：「交戰」＝任何一場仗（野外遭遇與地痞、頭目、出陣約戰與應戰、切磋、截殺、擂台、全服決戰、挑戰本人）。"""
    fights = ("encounter", "camp_spar", "battle", "boss", "sortie", "answer", "spar", "raid", "arena", "showdown", "challenge", "dividend")
    others = ("event", "insight", "errand", "material", "drill", "bounty", "hold")
    assert {k: growth.exp_source(k) for k in fights} == dict.fromkeys(fights, growth.BATTLE)
    assert {k: growth.exp_source(k) for k in others} == dict.fromkeys(others, growth.OTHER)
    with pytest.raises(ValueError, match="打坐"):
        growth.exp_source("打坐")  # 接線時寫錯的來源要當場炸，不要悄悄當成哪一種


def test_below_45_any_exp_counts():
    assert growth.capped_exp(CFG, 30, 120, growth.OTHER, room=10_000) == (120, 0)
    assert growth.capped_exp(CFG, 30, 120, growth.BATTLE, room=10_000) == (120, 0)


def test_from_44_event_exp_reaches_45_and_the_rest_turns_to_xinde():
    """44→45 用事件的經驗升得上；過了 45 的那一截不留在經驗裡（不然之後一場仗就帶著它升 46），整截換心得。"""
    assert growth.capped_exp(CFG, 44, 300, growth.OTHER, room=500) == (300, 0)
    assert growth.capped_exp(CFG, 44, 800, growth.OTHER, room=500) == (500, 300)


def test_at_45_and_above_only_battle_exp_levels_up():
    assert growth.capped_exp(CFG, 45, 200, growth.OTHER, room=0) == (0, 200)
    assert growth.capped_exp(CFG, 49, 200, growth.OTHER, room=0) == (0, 200)  # 第 50 級只靠打仗到得了
    assert growth.capped_exp(CFG, 45, 200, growth.BATTLE, room=0) == (200, 0)
    assert growth.capped_exp(CFG, 49, 200, growth.BATTLE, room=0) == (200, 0)
    # 到了 45 就全換，不靠 room：接線時 room 算錯（例如拿同伴的等級算）也不會讓事件的經驗漏進 46
    assert growth.capped_exp(CFG, 45, 200, growth.OTHER, room=500) == (0, 200)


def test_nothing_to_give_gives_nothing():
    assert growth.capped_exp(CFG, 45, 0, growth.OTHER, room=0) == (0, 0)
    assert growth.capped_exp(CFG, 30, -5, growth.OTHER, room=100) == (0, 0)


def test_room_to_the_cap_follows_the_level_costs():
    """離 45 級還差多少，照遊戲的升級表（team.level_cost：30 級起加陡）算，扣掉這一級已經攢的。"""
    config = real_content("season21").config
    member = type("M", (), {"level": 43, "exp": 100})()
    want = team.level_cost(config, 43) + team.level_cost(config, 44) - 100
    assert growth.room_to_cap(CFG, config, member) == want
    member.level, member.exp = 45, 30
    assert growth.room_to_cap(CFG, config, member) == 0


def test_the_cap_comes_from_the_numbers():
    low = JianfaNumbers(drill_level_cap=40)
    assert growth.capped_exp(low, 40, 50, growth.OTHER, room=0) == (0, 50)
    assert growth.capped_exp(low, 39, 50, growth.OTHER, room=20) == (20, 30)


def test_bad_gate_numbers_are_rejected():
    with pytest.raises(ValidationError):
        JianfaNumbers(drill_floor=1.5)
    with pytest.raises(ValidationError):
        JianfaNumbers(drill_decay=0)
    with pytest.raises(ValidationError):
        JianfaNumbers(drill_outlevel_steps=())
