"""計畫第八章裁決 24（PM 2026-10-20，照企劃者 10/17 行動精準化「鈕寫什麼就要給什麼」，同裁決 18 的道理）：領地爭奪開著時，
守勢行動（巡哨、傳道、保境安民）只給自家的地方——站在別人的地方（敵方的大本營與區塊、廣宗）或還沒佔下的中立地，那一顆灰著寫原因
（跟出陣用完、「此地不在爭奪之列」同一種寫法），按下去什麼都不給：不扣體力與出陣次數、不推線、不記守城。自家的地方照舊。
守城軍令記得了次數的地點只有「自家今天被公告的那一塊」（裁決 11），敵方大本營從來不在裡面；這一支把它鎖住。
關著的季（週末、14 天、21 天）一個字都不變。"""
from __future__ import annotations

import random

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game
from tianxia import bot_policy, conquest, howto, orders, sortie
from tianxia.state import BotProfile, Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

# （陣營, 地點, 這裡是誰的）：敵方大本營、敵方區塊、廣宗（fixed，黃巾的）、還沒佔下的中立地（區塊表 v3：汝南荒野改成中立、
# 嵩山深處改成官軍的，敵方區塊換汝南、中立地換淯水河畔）
OTHERS = (
    ("guan", "huangjin_camp", "other"),
    ("guan", "runan", "other"),
    ("guan", "guangzong", "other"),
    ("guan", "yu_river", "open"),
    ("guan", "hilltop_wilds", "open"),
    ("huang", "changshe", "other"),
    ("huang", "yingchuan_wilds", "other"),
    ("huang", "nanyang_road", "open"),
)
OWN = (("guan", "changshe"), ("guan", "yingchuan_wilds"), ("huang", "huangjin_camp"), ("huang", "runan"))


def _duty(game):
    return next((o for o in game.options() if o.id == "act:duty"), None)


def _snapshot(game):
    s, w = game.state, game.state.world
    return {
        "stamina": s.player.stamina, "sorties": (s.player.sortie_day, s.player.sorties_today), "contrib": s.player.contrib,
        "trends": dict(w.trends), "offset": dict(w.conquest.offset), "journal": len(s.journal),
        "orders": [(o.id, dict(o.progress)) for o in w.orders],
    }


@pytest.mark.parametrize(("side", "loc", "kind"), OTHERS)
def test_duty_is_grey_with_a_reason_off_own_ground(side, loc, kind):
    game = go(join(conquest_game("season21"), side), loc)
    option = _duty(game)
    assert option is not None and not option.enabled  # 修前按得下去
    name = game.content.orders.duties[side].name
    reason = sortie.DUTY_OUT_OPEN if kind == "open" else sortie.DUTY_OUT_OTHER
    assert option.label == f"{name}（{reason}）"
    assert conquest.holder(game.state.world, game.content, loc) in (None, "huang" if side == "guan" else "guan")


@pytest.mark.parametrize(("side", "loc", "kind"), OTHERS)
def test_pressing_it_gives_nothing(side, loc, kind):
    game = go(join(conquest_game("season21"), side), loc)
    w, c = game.state.world, game.content
    w.orders.append(Order(id="t:defend", template="defend", faction=side, week=orders.period_of(game.state, c),
                          front=conquest.line_of(w, c, loc) or "yingru", quota=5, text="（測試）"))
    before = _snapshot(game)
    msgs = game.choose("act:duty")
    assert msgs == ["（此刻無法這麼做。）"]
    assert _snapshot(game) == before  # 不扣體力與出陣次數、不推線、不記貢獻與守城、不寫江湖紀錄


@pytest.mark.parametrize(("side", "loc"), OWN)
def test_own_ground_still_gives_it(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    option = _duty(game)
    assert option is not None and option.enabled
    before = _snapshot(game)
    game.choose("act:duty")
    after = _snapshot(game)
    assert after["stamina"] < before["stamina"] and after["sorties"][1] == before["sorties"][1] + 1
    assert after["offset"] != before["offset"]  # 自家的地方照舊推線（裁決 11）


def test_taking_a_neutral_block_turns_the_button_on_and_losing_it_turns_it_off():
    game = go(join(conquest_game("season21"), "guan"), "yu_river")  # 區塊表 v3 之前用嵩山深處（現在是官軍的）
    w, c = game.state.world, game.content
    assert not _duty(game).enabled
    conquest.set_control(w, c, "yu_river", "guan")
    assert _duty(game).enabled
    conquest.set_control(w, c, "yu_river", "huang")
    option = _duty(game)
    assert not option.enabled and option.label.endswith(f"（{sortie.DUTY_OUT_OTHER}）")


def test_a_gentry_follows_the_side_it_leans_on():
    game = go(join(conquest_game("season21"), "haoqiang"), "changshe")
    game.state.player.ally = "guan"
    assert _duty(game).enabled  # 依附官軍：長社是自家的
    go(game, "huangjin_camp")
    assert not _duty(game).enabled
    game.state.player.ally = "huang"
    assert _duty(game).enabled and not _duty(go(game, "changshe")).enabled


def test_places_that_are_not_blocks_are_untouched():
    """不是區塊的地點（南華觀、豪強三處投靠點）誰也不佔：先不動（裁決只點名別人的區塊與沒佔下的中立地），要不要擋交 PM。"""
    game = go(join(conquest_game("season21"), "guan"), "jade_cave")
    assert "jade_cave" not in conquest.blocks(game.content)
    assert _duty(game) is not None and _duty(game).enabled


def test_the_defend_order_never_counts_or_lists_an_enemy_base():
    """守城軍令（裁決 11）：自家今天被公告的那一塊；敵方的大本營、區塊、自家沒被公告的區塊，記不到、假人也不往那裡走。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    guan_block = next(loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and conquest.holder(w, c, loc) == "guan"
                      and conquest.line_of(w, c, loc) == "yingru")
    announce(game, guan_block, "huang")
    w.orders.append(Order(id="t:defend", template="defend", faction="guan", week=orders.period_of(game.state, c), front="yingru",
                          quota=5, text="守"))
    state = join(game, "guan").state
    assert orders.duty_counts(state, c, "guan", guan_block)
    for loc in ("huangjin_camp", "runan", "runan_academy", "runan_wilds", "hilltop_wilds", "changshe", "yingchuan_wilds", "deep_mountain"):
        assert not orders.duty_counts(state, c, "guan", loc), loc  # 敵方大本營、敵方區塊、中立地、自家大本營與沒被公告的自家區塊
    assert orders.targets(state, c, "guan") == [guan_block]
    for loc in ("huangjin_camp", "runan"):  # 真的站在敵方那裡也記不到（修前就是如此，只是鈕按得下去、線照推）
        assert not orders._counts(c, w.orders[-1], "duty", loc, None, None, None, None, None, w)


def test_bots_never_press_it_off_own_ground():
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    game = go(join(conquest_game("season21"), "guan"), "huangjin_camp")
    options = [o for o in game.options(odds=False, tick=False) if o.enabled]
    assert "act:duty" not in {o.id for o in options}
    rng = random.Random(3)
    assert all(bot_policy.pick(game, options, profile, rng) != "act:duty" for _ in range(200))


def test_howto_says_duty_stays_on_own_ground():
    game = conquest_game("season21")
    lines = " ".join(howto.territory_lines(game.content, True, game.state.world))
    assert "守勢行動也只在自家的領地做" in lines
    off = plain_game("season21")
    assert "守勢行動" not in " ".join(howto.territory_lines(off.content, True, off.state.world))  # 關著：拔河那一版，一個字不變


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])  # 週末、14 天（不帶設定檔）、21 天；一個測試只開一季
def test_switch_off_the_duty_button_is_unchanged(profile):
    """領地爭奪關著（正式內容的預設，週末、14 天、21 天都一樣）：每一個地點都沒有灰掉的原因；別人的地方、中立地照舊按得下去、
    照舊那一個標籤。14 天的季沒有第一季規則、沒有軍令，守勢行動本來就不在選單上（修前修後都一樣）。"""
    game = go(join(plain_game(profile), "guan"), "huangjin_camp")
    for loc_id in game.content.locations:
        assert sortie.duty_problem(game.content, game.state.world, "guan", loc_id) == ""
    option = _duty(game)
    if profile is None:
        assert option is None
        return
    assert option is not None and option.enabled
    assert option.label.startswith(game.content.orders.duties["guan"].name)
    assert sortie.DUTY_OUT_OTHER not in option.label and sortie.DUTY_OUT_OPEN not in option.label
    assert go(game, "deep_mountain") is game and _duty(game).enabled
