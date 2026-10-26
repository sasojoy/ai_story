"""FB-847：評曰名單（main.zhuan／/api/zhuan 的 verdicts）照寫成的那一篇傳列。
（一）傳寫成之後才請的人不列，等重修寫進去才列；（二）管理者退了已經用過的那一張，寫成的正文照留，名單也照正文列（不因退款拿掉）。
還沒寫成時列的是「要寫的人」（預告）。名單從正文的段首「評曰：某某云：「」認，不另存一份。"""
from __future__ import annotations

import pytest
from zhuan_fix_kit import add_story, admin_of, close_season, figures, make_game, verdict_paras

from jianfa_kit import jianfa_game
from tianxia import zhuan_end
from tianxia.characters import name_key
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow


def _written():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    return game


def test_a_quote_asked_after_the_biography_is_written_is_listed_only_after_the_rewrite():
    game = _written()
    assert game.biography_entry()["verdicts"] == []
    game.mall_buy("zhuan_quote", "q1")
    out = game.choose("zhuan:quote:luzhi")
    assert zhuan_end.QUOTE_LATER in out
    assert game.biography_entry()["verdicts"] == [] and game.biography_view(1)["verdicts"] == []
    assert verdict_paras(game.biography_view(1)["paragraphs"]) == []
    request = game.biography_request(1, rewrite=True)
    assert request is not None and [j.fid for j in request.verdicts] == ["luzhi"]
    assert game.write_biography(request, None, game.now + 60)
    got = game.biography_entry()["verdicts"]
    assert got == [{"figure": "luzhi", "name": "盧植", "reason": zhuan_end.BOUGHT}]
    assert game.biography_view(1)["verdicts"] == got
    assert game.biography_view(1)["paragraphs"][-1].startswith("評曰：盧植云：「")


def test_before_the_biography_is_written_the_list_says_who_will_write():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    assert figures(game.biography_entry()) == ["luzhi"]  # 還沒寫：預告要寫的人
    assert figures(game.biography_view(1)) == ["luzhi"]
    assert game.biography_view(1)["written"] is False


def test_a_refunded_used_quote_stays_listed_because_the_text_still_has_it():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    assert figures(game.biography_entry()) == ["luzhi"]
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    pid = next(b.id for b in wallet.purchases(owner) if b.item == "zhuan_quote")
    msg = admin_of(game).admin_mall_refund(game.state.player.name, pid, "測試退款")[0]
    assert "人物親筆評曰作廢" in msg
    game.sync(game.now + 40)
    assert figures(game.biography_entry()) == ["luzhi"]  # 正文還有他，名單就還有他
    assert figures(game.biography_view(1)) == ["luzhi"]
    assert verdict_paras(game.biography_view(1)["paragraphs"])[0].startswith("評曰：盧植云：「")


def test_a_refund_before_the_biography_is_written_takes_him_off_the_list_and_the_text():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_quote", "q1")
    game.choose("zhuan:quote:luzhi")
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    pid = next(b.id for b in wallet.purchases(owner) if b.item == "zhuan_quote")
    admin_of(game).admin_mall_refund(game.state.player.name, pid, "測試退款")
    game.sync(game.now + 40)
    assert game.biography_entry()["verdicts"] == []
    assert game.write_biography(game.biography_request(1), None, game.now + 50)
    assert verdict_paras(game.biography_view(1)["paragraphs"]) == [] and game.biography_view(1)["verdicts"] == []


def test_the_list_is_what_the_text_has_free_writers_first_then_the_asked_ones():
    game = make_game()
    game.state.player.affinities.update({"zhujun": 75, "luzhi": 55, "caocao": 50})
    add_story(game)
    close_season(game)
    for ref in ("q1", "q2"):
        game.mall_buy("zhuan_quote", ref)
    game.choose("zhuan:quote:luzhi")
    game.choose("zhuan:quote:caocao")
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    got = game.biography_entry()["verdicts"]
    assert [(v["figure"], v["reason"]) for v in got] == [
        ("zhujun", zhuan_end.AFFINITY), ("luzhi", zhuan_end.BOUGHT), ("caocao", zhuan_end.BOUGHT)]
    assert [p[3:5] for p in verdict_paras(game.biography_view(1)["paragraphs"])] == ["朱儁", "盧植", "曹操"]


def test_written_writers_reads_only_the_verdict_paragraphs():
    content = jianfa_game().content
    text = "\n\n".join([
        "沈浪者，不知何許人也。",
        "評曰：此人敢作敢當，頗有可取。",  # 史官自己的評曰
        "評曰：盧植云：「沈浪此季之功，吾親書以表之。」",
        "評曰：不知名者云：「這一段不認得。」",
        "評曰：盧植云：「同一位不重複列。」",
        "評曰：曹操云：「可託大事。」",
        "評曰：皇甫嵩云：「三個字的名字也認得。」",
    ])
    got = zhuan_end.written_writers(text, content, {"caocao": zhuan_end.TIER})
    assert got == [zhuan_end.Writer("luzhi", zhuan_end.BOUGHT), zhuan_end.Writer("caocao", zhuan_end.TIER),
                   zhuan_end.Writer("huangfusong", zhuan_end.BOUGHT)]
    assert zhuan_end.written_writers("", content, {}) == []


def test_the_public_page_extras_do_not_move(monkeypatch):
    """公開頁只用插畫與紀念印；名單改照正文列不動它們。"""
    import server

    game = make_game()
    add_story(game)
    close_season(game)
    game.mall_buy("zhuan_seal", "s1")
    game.choose(zhuan_end.SEAL)
    assert game.write_biography(game.biography_request(1), None, game.now + 30)
    code = game.share_biography(1, True, "fb847")
    monkeypatch.setattr(server, "CONTENT", game.content)
    got = server.zhuan_extras(game.world, game.world.biography_by_code(code))
    assert set(got) == {"seal"} and got["seal"].startswith("黃巾之亂・第 1 季")
