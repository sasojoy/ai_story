"""本週卡「你這一步」的第一順位接上託付（減法季批 6；整合設計 6.1；批 1 欄位表「託付的正式來源」）：身上還在辦的那一件人物託付
排在最前面（在懸賞列裡標了 commission 的委託之前），寫「到長社，替盧植交信。」；辦完、作罷、關著的季照舊。正式內容的 season21。

章回主線（Config.jianfa.chapters，38dfd05a，企劃者 2026-10-29 同意設計稿第四節）開著、手上有一回時，章回那一步是「眼下要事」第一件、
永遠排在差事前面（引擎的排序不改，FB-9037）：差事自己的順序（領頭、換一件事從下一件排起）關掉章回測，章回排在差事前面另外鎖一條。"""
from __future__ import annotations


from stances_kit import LUZHI, real_game
from tianxia import errands, step, weekcard


def _steps(g):
    return weekcard.week_card(g, g.status_data(), g.orders_view())["steps"]


def _no_chapters(c):
    c.config.jianfa.chapters = False  # 章回卡不在「你這一步」最前面：差事照舊領頭


def test_an_open_errand_leads_your_next_step():
    """章回主線關著（FB-9037：章回開著時章回領頭，見 test_an_open_chapter_leads_the_errand）。"""
    g = real_game(setup=_no_chapters)
    s, c = g.state, g.content
    before = _steps(g)
    s.player.affinities[LUZHI] = 50
    errands.give(s, c, LUZHI, "luzhi_letter")
    e = s.player.errands[-1]
    steps = _steps(g)
    first = steps[0]
    assert first["kind"] == "errand" and first["id"] == e.id and first["who"] == "盧植"
    assert first["text"] == errands.STEP.format(place=c.locations[e.target].name, who="盧植", label=errands.LABELS["letter"])
    assert first["target"]["location"] == e.target and first["target"]["minutes"] >= 1
    assert steps[1:] == before  # 其餘照舊排在後面
    e.status = "done"
    assert _steps(g) == before


def test_four_wins_keeps_the_errand_target_and_step_next_order():
    """批 3c 合進來之後（step.finish 替每一件補 target、id）：四勝利開著時，託付那一件（errands.step_items 自己帶了 id 與 target、
    沒有 _ref）的 target 不被洗成 null；「換一件事」（step:next）照舊從下一件排起、轉一圈回來。章回主線關著（FB-9037）。"""
    g = real_game(setup=_no_chapters)
    s, c = g.state, g.content
    assert step.on(g)  # season21：四勝利開著
    s.player.affinities[LUZHI] = 50
    errands.give(s, c, LUZHI, "luzhi_letter")
    e = s.player.errands[-1]
    steps = _steps(g)
    assert len(steps) >= 2 and "_ref" not in steps[0]
    assert steps[0]["kind"] == "errand" and steps[0]["id"] == e.id
    assert steps[0]["target"] == errands.card(s, c, e)["target"] and steps[0]["target"]["location"] == e.target
    assert g.choose(step.NEXT) == []
    rotated = _steps(g)
    assert rotated == steps[1:] + steps[:1]  # 從下一件排起
    assert rotated[-1]["target"]["location"] == e.target
    for _ in range(len(steps) - 1):
        g.choose(step.NEXT)
    assert _steps(g) == steps  # 轉一圈回來


def test_an_open_chapter_leads_the_errand():
    """章回主線開著、手上有一回（season21 一開季就有）：章回那一步排第一，差事緊跟在後（FB-9037：排序是設計，不是退步）；其餘照舊在後面，
    「換一件事」不把章回輪走。"""
    g = real_game()
    s, c = g.state, g.content
    before = _steps(g)
    assert before and before[0]["kind"] == "chapter"
    s.player.affinities[LUZHI] = 50
    errands.give(s, c, LUZHI, "luzhi_letter")
    e = s.player.errands[-1]
    steps = _steps(g)
    assert [x["kind"] for x in steps[:2]] == ["chapter", "errand"] and steps[1]["id"] == e.id and steps[1]["who"] == "盧植"
    assert steps[0] == before[0]  # 章回那一步不受差事影響
    assert steps[2:] == before[1:]  # 其餘照舊排在後面
    assert g.choose(step.NEXT) == []
    assert _steps(g)[0] == steps[0]  # 章回不跟著「換一件事」輪
    e.status = "done"
    assert _steps(g)[0]["kind"] == "chapter" and all(x["kind"] != "errand" for x in _steps(g))


def test_closed_seasons_keep_the_old_steps():
    g = real_game(setup=lambda c: setattr(c.config.jianfa, "errands", False))
    s, c = g.state, g.content
    before = _steps(g)
    errands.give(s, c, LUZHI, "luzhi_letter")  # 就算身上有（換了設定），關著不列
    assert _steps(g) == before
