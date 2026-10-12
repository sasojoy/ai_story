"""散人玩法的網頁那一半：狀態列展開時的遊俠名號（俠名、下一階、這一階的好處）與江湖頁的懸賞卡（手上揭了的、看懸賞榜）。
餵真的引擎給的 /api/main 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有node 就略過。"""
from __future__ import annotations

import pytest
from test_bounties import _do, _post, setup  # noqa: F401  （setup 是 fixture）
from test_bounty_hand_in import _art, _edit, _fused
from test_prologue_web import run

import server
import webharness
from tianxia import bounties
from tianxia.characters import CharacterStore

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _view(content, world, name):
    return _do(content, world, name, server.main_view)[0]


def test_the_expanded_name_shows_the_ranger_ladder(setup):  # noqa: F811
    content, world = setup
    state = CharacterStore(world.db).load("丙")
    state.player.ranger_good = 7  # 第 1 階（5），再 8 點到第 2 階（15）
    CharacterStore(world.db).save(state)
    m = _view(content, world, "丙")
    top = run(m, "return H.topHtml();", S={"showMore": True})
    assert "江湖遊俠" in top and "俠名 7，再攢 8 點可稱「一方豪俠」" in top and "求見門檻 -3" in top
    assert "who-ranger" not in run(m, "return H.topHtml();")  # 收起來只有頭銜那一行
    assert "who-ranger" not in run(_view(content, world, "甲"), "return H.topHtml();", S={"showMore": True})  # 陣營的人凍結：不畫


def test_the_bounty_card_lists_what_you_hold_and_opens_the_board(setup):  # noqa: F811
    content, world = setup
    assert "🪧 懸賞" not in run(_view(content, world, "丙"), "return H.pageJianghu();")  # 沒揭就不畫
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    _do(content, world, "丙", lambda g: g.choose("bounty:back"))
    page = run(_view(content, world, "丙"), "return H.pageJianghu();")
    assert "🪧 懸賞（1）" in page and "打探・湖邊" in page and "到湖邊探索一次" in page and "俠名 +2" in page
    assert "期限 到季末・名額還剩 1" in page  # 每一列寫期限與名額（FB-121 第 5 件；測試的單掛到季末之後）
    assert 'data-act="choose" data-id="act:bounties"' in page.split("🪧")[1]  # 在城鎮：卡底下開得了懸賞榜
    assert page.index("🪧") > page.index('data-id="act:explore"')  # 排在行動列下面，不擠第一屏
    shut = run(_view(content, world, "丙"), "return H.pageJianghu();", S={"bountyShut": b.id})
    assert '<details class="fold bounties" data-key="' + b.id + '" >' in shut  # 收起來照手上那幾張記住

    state = CharacterStore(world.db).load("丙")
    state.player.location = "lake"
    CharacterStore(world.db).save(state)
    away = run(_view(content, world, "丙"), "return H.pageJianghu();")
    assert "到城鎮的懸賞榜前" in away and 'data-id="act:bounties"' not in away


def test_the_wanted_amount_box_starts_at_the_lowest_bounty(setup):  # noqa: F811
    """FB-121 第 6 件：通緝的金額輸入框下限照規則（post_min，20 兩），不是贈物那樣的 1；贈物照舊從 1 起。"""
    content, world = setup
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    i = next(k for k, b in enumerate(card["actions"]) if b["action"] == "wanted")
    gift = next(b for b in card["actions"] if b["action"] == "gift" and b["amount"] > 0)
    assert card["actions"][i]["amount_min"] == content.config.bounties.post_min == 20 and gift["amount_min"] == 1
    html = run(_view(content, world, "甲"), "H.render(); return T.els.app.innerHTML;",
               S={"peer": {"name": "乙", "card": card, "amountFor": i}})
    box = html.split('id="peer-amount"')[1].split("</form>")[0]
    assert 'min="20"' in box and "：20～200" in box


def test_the_bounty_card_lists_a_hand_in_you_can_make(setup):  # noqa: F811
    """懸賞榜設計 4.9：身上有合用的求藝，卡上就列那一張，多一行身上合用的是哪幾件；人在城外時卡底那句寫得出可以交；
    第三層（替那一張挑一件）開著時，選單就是懸賞榜，卡底不再叫人去看榜。"""
    content, world = setup
    good = _fused(world, "烈焰掌")
    _edit(world, "丙", lambda p: p.arts.append(good.id))
    b = _art(world)
    card = run(_view(content, world, "丙"), "return H.pageJianghu();").split("🪧")[1].split("</details>")[0]
    assert "懸賞（1）" in card and "求藝・剛" in card and bounties.HAVE + "【烈焰掌】" in card and "期限 到季末・名額還剩 3" in card
    assert 'data-id="act:bounties"' in card  # 在城鎮：卡底開得了懸賞榜
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    _do(content, world, "丙", lambda g: g.choose(f"bounty:pick:{b.id}"))
    card = run(_view(content, world, "丙"), "return H.pageJianghu();").split("🪧")[1]
    assert "bounty-foot" not in card.split("</details>")[0]
    _do(content, world, "丙", lambda g: g.choose("bounty:back"))
    _edit(world, "丙", lambda p: setattr(p, "location", "lake"))
    away = run(_view(content, world, "丙"), "return H.pageJianghu();")
    assert bounties.HAVE + "【烈焰掌】" in away and "到城鎮的懸賞榜前，可以揭新的、放棄，或交出合用的功夫與兵器。" in away


def test_with_the_board_open_the_card_points_nowhere(setup):  # noqa: F811
    content, world = setup
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    card = run(_view(content, world, "丙"), "return H.pageJianghu();").split("🪧")[1]
    assert "bounty-foot" not in card.split("</details>")[0]  # 選單就是懸賞榜：不再叫人去看榜
