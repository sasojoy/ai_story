"""減法季批 3b 收尾：約戰結算記一則行狀（annals.DUEL；計畫 8.0 的「3b 約戰結算 → DUEL」，給 7b-1 剩下的那一小步〔列傳讀約戰〕認得出來）。

攻方與應戰的人各記一則，地點是約戰的那一塊（結算時人已經走了也一樣）；同去的人沒下場不記。攻方寫「在某地約戰某某，結果。」，
應戰的人（含補位的）寫「應下某某在某地的約戰，結果。」（FB-897：列傳補了主詞之後，守方的傳不能讀起來像他下的戰書）。行狀頁的小標與
季末的傳的段落都跟其他單挑一樣（KINDS 寫「交手」、GROUPS 歸 FIGHT），畫面上看不出差別。"""
from __future__ import annotations


from duel_kit import FAR, LOC, MOVES, NOW, WINDOW, do, duel_content, duel_world, load, rounds_go, seat, tick
from tianxia import annals, sortie_duel


def _settled(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang")
    seat(c, world, "丙", "guan")
    rounds_go(monkeypatch, "大勝")
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    duel_id = next(iter(world.sortie_duels()))
    do(c, world, "乙", lambda g: g.choose(f"sortie:answer:{duel_id}:固守,固守,固守"), NOW + 60)
    do(c, world, "丙", lambda g: g.choose(f"sortie:join:{duel_id}"), NOW + 90)
    seat(c, world, "乙", "huang", FAR)  # 應戰之後走了：行狀的地點照樣寫約戰的那一塊
    tick(c, world, NOW + WINDOW + 1)
    return c, world


def _duels(world, name):
    return [e for e in load(world, name).player.annals if e.kind == annals.DUEL]


def test_both_fighters_get_a_duel_annal_at_the_duel_place(monkeypatch):
    c, world = _settled(monkeypatch)
    place = c.locations[LOC].name
    mine, theirs = _duels(world, "甲"), _duels(world, "乙")
    assert [e.text for e in mine] == [f"在{place}約戰乙，大勝。"]
    assert [e.text for e in theirs] == [f"應下甲在{place}的約戰，落敗。"]  # 守方不寫成他去約戰（FB-897）
    assert mine[0].place == theirs[0].place == place
    assert _duels(world, "丙") == []  # 同去的人沒下場
    assert mine[0].keep == ["乙"] and theirs[0].keep == ["甲"]  # 對手是玩家：名號原樣留給季末的備援列傳（FB-9020）


def test_the_answerer_has_his_own_line_and_the_attacker_keeps_the_old_one():
    """FB-897：兩句字不同；守方那句沒有「約戰某某」（那是下戰書的人說的話），而且兩句都沒有代詞、沒有阿拉伯數字（對手的名號原樣放進去）。"""
    attack, answer = sortie_duel.ANNAL_LINE, sortie_duel.ANNAL_ANSWER_LINE
    assert attack == "在{place}約戰{rival}，{tier}。"  # 攻方照舊
    assert answer == "應下{rival}在{place}的約戰，{tier}。"
    assert answer != attack and "約戰{rival}" not in answer and sortie_duel.ANSWER_LINE != answer  # 約戰卡的「你應下…」是另一個字串
    for line in (attack, answer):
        assert "你" not in line and not any(ch.isascii() and ch.isdigit() for ch in line)


def test_a_filled_in_defender_reads_like_one_who_answered(monkeypatch):
    """補位的人（到時沒人應戰，同一區對面的假人頂上）也是守方：他的行狀同真人應戰那一句，攻方照舊，沒人頂上的守軍迎戰時攻方寫約戰守軍。"""
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang", FAR)  # 真人在別區，不補位
    seat(c, world, "丁", "huang", LOC, bot=True)
    rounds_go(monkeypatch, "大勝")
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    tick(c, world, NOW + WINDOW + 1)
    assert next(iter(world.sortie_duels().values())).defender.name == "丁"
    place = c.locations[LOC].name
    assert [e.text for e in _duels(world, "丁")] == [f"應下甲在{place}的約戰，落敗。"]
    assert [e.text for e in _duels(world, "甲")] == [f"在{place}約戰丁，大勝。"]
    assert _duels(world, "丁")[0].keep == ["甲"] and _duels(world, "甲")[0].keep == ["丁"]  # 補位的人也是玩家
    assert _duels(world, "乙") == []


def test_the_garrison_still_reads_as_the_attackers_line(monkeypatch):
    c = duel_content()
    world = duel_world(c)
    seat(c, world, "甲", "guan")
    seat(c, world, "乙", "huang", FAR)
    rounds_go(monkeypatch, "大勝")
    do(c, world, "甲", lambda g: g.choose(f"sortie:go:{MOVES}"))
    tick(c, world, NOW + WINDOW + 1)
    assert next(iter(world.sortie_duels().values())).defender.garrison
    assert [e.text for e in _duels(world, "甲")] == [f"在{c.locations[LOC].name}約戰守軍，大勝。"]
    assert _duels(world, "甲")[0].keep == []  # 守軍不是玩家的名號：不必留
    assert _duels(world, "乙") == []


def test_duel_annals_read_like_any_other_fight(monkeypatch):
    assert annals.KINDS[annals.DUEL] == annals.KINDS[annals.FIGHT]
    assert annals.GROUPS[annals.DUEL] == annals.FIGHT
    assert annals.heard(annals.AnnalEntry(kind=annals.DUEL, time=0, when="", text="x"))  # 酒肆照樣打聽得到（同其他單挑）
