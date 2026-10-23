"""輿圖第三版第 1 批（翻地與爭搶）QA 的順帶幾樣（試玩回饋檔尾那一節的「順帶」；PM 2026-10-21 派一起修）：

1. 守的那一句四捨五入成「拉回了 0」接著「全數歸零」：量不到 1 時不寫 0，寫「一點」（推也一樣；待 joy 潤）。
2. 戰書的時刻後面直接接字（「週三 12:00攻汝南荒野」「併進第 1 週・週六 12:00那一場」）：時刻與後面的字中間補一個空格，同別處接在時刻後面的寫法。
3. 管理者白天開單時〈天下形勢〉寫「一仗打到入夜」：在 test_xingshi_fb610_order.py（同一個函式）。
4. 假人照開季的截糧軍令跑去推不動的地方出陣：假人挑出陣地點時先問 conquest.push_problem，推不動的不去、不出陣。"""
from __future__ import annotations

import re

import pytest

from conquest_kit import announce, conquest_game, go, join
from tianxia import bot_policy, conquest, conquest_day, orders
from tianxia.engine import Option
from tianxia.state import BotProfile, Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0
STUCK = re.compile(r"\d:\d\d[^\s\d]")  # 時刻後面直接接字


def test_a_pull_under_one_does_not_say_zero():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    conquest.push(w, c, "hilltop_wilds", "huang", "丁", 0.4, "attack")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 5, "hold")
    assert done.moved == pytest.approx(0.4)
    assert not any("拉回了 0" in line for line in done.lines), done.lines  # 修前「把對面的進度拉回了 0。」接「全數歸零」
    assert any("拉回了一點" in line for line in done.lines)
    big = conquest.push(w, c, "hilltop_wilds", "huang", "丁", 3, "attack")
    pulled = conquest.push(w, c, "hilltop_wilds", "guan", "甲", 3, "hold")
    assert big.moved == 3 and any("拉回了 3" in line for line in pulled.lines)  # 一以上照舊寫數字


def test_a_push_under_one_does_not_say_zero():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "甲", 99.7, "attack")
    done = conquest.push(w, c, "hilltop_wilds", "guan", "乙", 2, "attack")
    assert done.flipped and done.moved == pytest.approx(0.3)
    assert not any("推進了 0" in line for line in done.lines), done.lines
    assert any("推進了一點" in line for line in done.lines)


def _seated(side="guan", loc="hilltop_wilds", name="沈浪", world=None):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    game.state.player.qualified = True
    game.state.world.seats[side] = [name]
    return game


def test_letter_times_have_a_space_before_the_words():
    game = _seated(loc="runan_wilds")
    w, c = game.state.world, game.content
    conquest.push(w, c, "runan_wilds", "guan", "先鋒", 60, "attack")
    conquest.push(w, c, "runan_wilds", "huang", "先鋒", 60, "attack")
    mine = game.conquest_letter("runan_wilds")
    game._save_season()
    rival = _seated(side="huang", loc="runan_wilds", name="張角徒", world=game.world)
    joined = rival.conquest_letter("runan_wilds")
    news = [r.text for r in rival.state.world.rumors if "戰書" in r.text]
    texts = mine + joined + news
    assert len(news) == 2 and any("下了戰書" in t for t in mine) and any("併進" in t for t in joined)
    for text in texts:
        assert not STUCK.search(text), text  # 修前「定於第 1 週・週三 12:00攻汝南荒野」「併進第 1 週・週六 12:00那一場」


def test_admin_letter_time_has_a_space_before_the_words():
    game = _seated()
    text = conquest_day.place_now(game.state.world, game.content, "huang", "runan_wilds", NOW)
    assert "攻汝南荒野" in text and not STUCK.search(text), text  # 修前「黃巾軍定於第 1 週・週四 15:30攻荒丘。」


def _bot(game, side):
    game.state.player.bot = BotProfile(personality="普通", seed=7, faction=side, season_number=game.world.get_season_number())
    return game


def _intercept(game, side, loc, front):
    s, c = game.state, game.content
    s.world.orders.clear()
    order = Order(id=f"t:{side}:intercept", template="intercept", faction=side, week=orders.period_of(s, c), front=front,
                  location=loc, quota=99, text="（測試）")
    s.world.orders.append(order)
    return order


def test_bots_do_not_sortie_where_they_cannot_push(monkeypatch):
    """QA：開季的截糧軍令把官軍的假人拉到下曲陽（官軍開季碰不到、推不動），在那裡一直出陣、連輸中立駐軍。
    2026-10-22（7 天季領地爭奪調整）之後假人出陣也看勝算（bot_policy._outmatched，測試在 test_bot_policy_conquest.py）：剛建的假人在荒丘
    攻打的贏面不到門檻；這一條只鎖「推不推得動」，勝算一律當成穩勝。"""
    monkeypatch.setattr(bot_policy, "_sortie_win", lambda game, loc_id: 1.0)
    game = _bot(go(join(conquest_game("season21", name="假官"), "guan"), "xiaquyang"), "guan")
    w, c = game.state.world, game.content
    _intercept(game, "guan", "xiaquyang", "jizhou")
    assert conquest.push_problem(w, c, "guan", "xiaquyang", "attack") is not None  # 推不動
    assert orders.win_counts(game.state, c, "guan", "xiaquyang")  # 截糧照舊記得到（修前就是這個加分把假人留在這裡出陣）
    train = Option(id="act:train", label="出陣・攻")
    assert bot_policy.score(game, train, game.state.player.bot) is None  # 修前照樣打分數（還多一份軍令的加分）
    go(game, "hilltop_wilds")  # 推得動的地方照舊會出陣
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") is None
    assert bot_policy.score(game, train, game.state.player.bot) is not None


def test_bots_are_not_led_to_an_intercept_spot_they_cannot_push():
    game = _bot(go(join(conquest_game("season21", name="假官"), "guan"), "luzhi_camp"), "guan")
    _intercept(game, "guan", "xiaquyang", "jizhou")
    assert "xiaquyang" in orders.targets(game.state, game.content, "guan")  # 軍令本身照舊列它（卡上照寫）
    assert bot_policy._order_hop(game) is None  # 修前往下曲陽走


def test_bots_still_go_to_a_frozen_block_of_their_own_to_defend():
    """FB-605 之後守城會列自家被戰書凍結的那一塊（推不動，等著攻城戰）：假人照樣往那裡走（加入攻城站守方才記得到），不被上面那一條擋掉。"""
    game = _bot(go(join(conquest_game("season21", name="假黃"), "huang"), "huangjin_camp"), "huang")
    s, c = game.state, game.content
    s.world.orders.clear()
    s.world.orders.append(Order(id="t:huang:defend", template="defend", faction="huang", week=orders.period_of(s, c), front="yingru",
                                quota=99, text="（測試）"))
    conquest.push(s.world, c, "runan", "guan", "敵將", 60, "attack")
    announce(game, "runan", "guan")
    assert orders.targets(s, c, "huang") == ["runan"]
    assert bot_policy._order_hop(game) is not None
