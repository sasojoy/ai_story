"""FB-846：兩張親筆評曰照「請的先後」排，不是買的先後倒過來（QA 減法季批 7b：先請曹操、再請波才，名單與寫成的傳都是波才在前）。
原因：zhuan_end.season_tickets 照 Wallet.purchases（新的在前）收 quotes，而每一次請都用最舊的一張票，先請的人記在舊的那一筆、排到後面。"""
from __future__ import annotations

import pytest
from zhuan_fix_kit import add_story, close_season, figures, make_game, verdict_paras

from tianxia import zhuan_end
from tianxia.wallet import Purchase

pytestmark = pytest.mark.slow


def test_quotes_follow_the_order_they_were_asked():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55, "zhujun": 45, "caocao": 50})
    add_story(game)
    close_season(game)
    for ref in ("q1", "q2"):
        assert game.mall_buy("zhuan_quote", ref)[0].startswith("買下")
    game.choose("zhuan:quote:caocao")
    game.choose("zhuan:quote:luzhi")
    assert figures(game.biography_entry()) == ["caocao", "luzhi"]
    assert [j.fid for j in game.biography_request(1).verdicts] == ["caocao", "luzhi"]
    assert game.write_biography(game.biography_request(1), None, game.now + 40)
    assert [p[3:5] for p in verdict_paras(game.biography_view(1)["paragraphs"])] == ["曹操", "盧植"]
    assert figures(game.biography_view(1)) == ["caocao", "luzhi"]


def test_the_order_does_not_depend_on_when_the_tickets_were_bought():
    """買一張、請一位，再買一張、請一位：照請的先後。"""
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55, "caocao": 50})
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    game.mall_buy("zhuan_quote", "q2")
    game.choose("zhuan:quote:caocao")
    assert figures(game.biography_entry()) == ["luzhi", "caocao"]


def test_season_tickets_collects_the_quotes_oldest_purchase_first():
    def ticket(pid, fid):
        return Purchase(id=pid, owner="x", ref=f"r{pid}", item="zhuan_quote", price=1, time=0, day=0, season=1,
                        data={"zhuan_quote": 1, "used": float(pid), "season": 1, "fid": fid}, refunded=None)

    newest_first = [ticket(5, "c"), ticket(4, "b"), ticket(3, "a")]  # Wallet.purchases 的次序
    assert zhuan_end.season_tickets(newest_first, 1)["quotes"] == ["a", "b", "c"]
