"""玩法說明與新手引導的字（出陣探索與地盤設計第七節）。
這一份先放出陣、推力、地盤那幾塊（PM 2026-10-14：探索三選一與地盤福利另外平行做，合進來之後再補那兩段）。"""
from __future__ import annotations

from conftest import classic_rules, real_content
from jianfa_kit import classic_explore
from tianxia import howto
import random
import re
from conftest import classic_rules
from tianxia import foreshadow, howto, timetable
from tianxia.engine import Game
from tianxia.rules import STANCE_NAMES


def _page(content):
    from tianxia.world_state import fresh_season

    return howto.page(content, fresh_season(content), recruitable=False)


def test_the_territory_prices_follow_the_config():
    c = real_content("week7")
    c.config.territory.own_price, c.config.territory.enemy_price = 0.85, 1.5
    line = " ".join(howto.territory_lines(c))
    assert "便宜15%" in line and "貴五成" in line


def test_the_first_order_hint_points_at_the_sortie():
    c = real_content()
    recruiters = c.tutorial.enlist.recruiters
    assert "出陣" in recruiters["guan"].order_hint and "出陣" in recruiters["huang"].order_hint


# ── 原 test_fb112_howto_truth.py（整檔搬進來） ──
# FB-112（QA 93e7037，2026-10-08）：第二批新手說明（tianxia/howto.py：主線小標、戰況圖卡、玩法說明的投靠與軍令、三方有什麼不同）
# 講得比規則寬。現在照程式與內容寫：
#
# - 伏筆：只有官軍、黃巾做完能改寫一件大事（foreshadow.LOCK_SIDES）；散人拿不到片段、做不了最後一步（foreshadow.capable 要陣營對得上）；
#   豪強分屬兩軍，照依附的那一邊（以前豪強第三方做完只在揭曉時留名、推一把割據，2026-10-31 拿掉）。
# - 推線：不是每一處都推（Location.train_trend 空著的不推，潁水河畔就是），寫「有些地方…（行動列底下那一行寫著）」。
# - 軍令湊滿額度推一把：只對有推線軍令的陣營（orders.json 的 effect.trend）；豪強只有打擊（挫大勢人物的聲威）。
# - 豪強操練：它能操練的地方（有它自己隊伍的地點）都沒有 train_trend，就照實說操練推不動。
# - 散人可以臨時投效：到決戰的大區，挑交戰兩軍之一，只算那一場（試玩回饋 2026-10-08 的決戰規則）。
# - 決戰的職位這一版不寫（控制者裁示：戰鬥那條線還在改）。
#
# 用真實內容（週末設定）；事實照內容與程式算，句子待 joy 潤：比的是有沒有說到那件事，盡量不鎖死字句。

def _quest(on):
    return "".join(howto.quest_help(on))


def _fronts(on):
    game = Game.new(on, "甲", rng=random.Random(0))
    return howto.fronts_help(game.state, on)[1]


def _sides_that_lock():
    return [timetable.SIDE_NAMES[s] for s in foreshadow.LOCK_SIDES]


def test_only_the_two_armies_can_rewrite_a_big_event(on):
    quest = _quest(on)
    before = quest[:quest.index("改寫")]
    assert all(name in before for name in _sides_that_lock())  # 「官軍、黃巾……能暗中改寫」
    hao = STANCE_NAMES["haoqiang"]
    assert f"地方{hao}照依附的那一邊" in quest and "割據" not in quest  # 豪強分屬兩軍：沒有第三方（2026-10-31 留名、推割據那一句拿掉）
    assert "散人" in quest and "伏筆" in quest[quest.index("散人"):]  # 散人拿不到伏筆


def test_pushing_a_front_is_only_some_places_and_the_note_row_says_which(on):
    # 遊歷的說法（出陣開著時只在戰線地點才有出陣、每一處都推，說法換成 howto.SORTIE_PLACES，見 tests/test_core_loop_howto.py）
    on = classic_rules(on)
    quiet =[loc for loc in on.locations.values() if loc.enemies and not loc.train_trend]
    assert any(loc.id == "yingshui" for loc in quiet)  # 潁水河畔有對手、不推線：所以不能說「在戰線上遊歷打贏就推」
    for line in (_quest(on), _fronts(on), howto.join_lines(on, Game.new(on, "乙").state.world)[0]):
        assert "有些地方" in line and "行動列底下" in line, line
        assert "在戰線上遊歷打贏、操練，會把" not in line


def test_the_order_push_is_claimed_only_for_sides_whose_orders_push(on):
    pushers = {t.side for t in on.orders.templates if t.effect.trend > 0}
    assert pushers == {"guan", "huang"}
    line = _fronts(on)
    end = line.index("軍令湊滿額度")
    clause = line[line.rindex("；", 0, end) + 1:end]  # 軍令那一句（前一句寫地方豪強算依附的那一邊）
    assert all(STANCE_NAMES[s] in clause for s in pushers) and STANCE_NAMES["haoqiang"] not in clause
    on.orders.templates = [t for t in on.orders.templates if t.side != "huang" or t.kind == "strike"]  # 黃巾只剩打擊
    line = _fronts(on)
    end = line.index("軍令湊滿額度")
    assert STANCE_NAMES["huang"] not in line[line.rindex("；", 0, end) + 1:end]


def _hao_row(on):
    rows = howto.faction_lines(on, Game.new(on, "丙").state.world)
    return next(r for r in rows if r.startswith("**地方豪強**"))


def test_drifters_hear_they_can_enlist_for_one_battle(on):
    world = Game.new(on, "丁").state.world
    join = howto.join_lines(on, world)[0]
    tail = join[join.index("散人"):]
    assert "臨時投效" in tail and "只算那一場" in tail and "決戰" in tail and "大區" in tail


def _page_fb112(on):
    return howto.page(on, Game.new(on, "己").state.world, recruitable=False)


def test_the_how_to_page_says_only_some_places_push_too(on):
    """審查 M4：玩法說明「遊歷」那一項以前寫「打贏或操練多半還會推動戰局」——豪強的操練從來不推、潁水河畔什麼都不推。
    「遊歷」那一項只在出陣關著時才有（開著時是「出陣」，見 tests/test_core_loop_howto.py）。"""
    text = _page_fb112(classic_rules(on))
    assert "多半還會" not in text
    train = next(line for line in text.splitlines() if line.startswith("- **遊歷**"))
    assert "有些地方" in train and "行動列底下" in train


def test_the_how_to_page_does_not_promise_fragments_to_drifters(on):
    """審查 M4：「情誼夠深，他會跟你聊起…伏筆的片段」散人也看得到，可是散人拿不到片段（foreshadow.capable 要陣營對得上）。"""
    line = next(line for line in _page_fb112(on).splitlines() if "伏筆的片段" in line)
    assert "散人" in line[line.index("伏筆的片段"):] or "散人" in line[:line.index("伏筆的片段")], line


def test_the_number_of_rewritable_events_follows_the_lock_sides(on, monkeypatch):
    """審查 M4：「其中 N 件可以被關鍵伏筆改寫」數的是會鎖定大事的那兩方的鏈（timetable.SIDE_NAMES，跟 foreshadow.LOCK_SIDES 同一份），不另寫一份。"""
    events = lambda sides: len({c.event for c in on.foreshadows.chains if c.side in sides})  # noqa: E731
    assert howto._lockable(on) == events(set(foreshadow.LOCK_SIDES))  # noqa: SLF001
    monkeypatch.setattr(timetable, "SIDE_NAMES", {"haoqiang": "豪強"})  # 換一份：數字跟著換，不是寫死的兩方
    assert howto._lockable(on) == events({"haoqiang"}) != events(set(foreshadow.LOCK_SIDES))  # noqa: SLF001


def test_battle_roles_are_not_explained_yet(on):
    world = Game.new(on, "戊").state.world
    text = "".join(howto.join_lines(on, world) + howto.faction_lines(on, world) + howto.quest_help(on) + [_fronts(on)])
    assert "職位" not in text and not re.search(r"先鋒|主將|軍師", text)


# ── 原 test_fb_batch_b.py ──

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
