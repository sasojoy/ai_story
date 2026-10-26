"""減法季批 7c：買來的深交名額不給數值（企劃者 2026-10-26 定。PM 問「買深交名額讓第四位人物也教本命武學，算不算『不賣數值』的例外？」，
企劃者答「不算」）：靠名額進深交名單的那一位（deep_order 裡排在 Config.jianfa.deep_figures 之後的），情誼照長、對話照談，
但不教本命武學（過 70）、不送名將本命兵器（過 80）；名單內的三位照舊。「靠名額的那一位」只是名單的位置（還在 70 以上的照先來後到），
不另存欄位、不動資料庫結構；名單裡有人掉下 70，後面的就遞補成名單內的。"""
from __future__ import annotations

import pytest
from test_deep_cap import _game, _set, _talk

from tianxia import signature_arms, zhuan_end
from tianxia.characters import name_key
from tianxia.state import SignatureClaim
from tianxia.tactics import figure_arts
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow

LIST3 = {"zhujun": 80, "huangfusong": 72, "luzhi": 70}
ARM3 = {"liubei": 82, "guanyu": 81, "zhangfei": 80}  # 三位都有本命兵器


def _buy_slot(game, tag: str = "deep-7c") -> None:
    wallet = Wallet(game.world.db)
    wallet.post(name_key(game.state.player.name), 1000, "grant", f"test:{tag}", time=game.now)
    assert game.mall_buy("deep_slot", tag)[0].startswith("買下")


# 批 7d（企劃者 2026-10-26，FB-869）：「某某把你當作知己，卻不打算把看家本領交出來」不給玩家看——規則照舊，句子不說
def _said_keep(msgs) -> bool:
    return any("看家本領" in m or "把你當作知己" in m for m in msgs)


def test_a_figure_let_in_by_a_bought_slot_does_not_teach_the_signature_art():
    game = _game()
    p = game.state.player
    _set(game, LIST3)
    game.sync(game.now)
    _buy_slot(game)
    p.affinities["caocao"] = 69
    arts = set(p.arts)
    msgs = _talk(game, "caocao")
    assert p.deep_order == ["zhujun", "huangfusong", "luzhi", "caocao"]
    assert p.affinities["caocao"] >= 70  # 情誼照長
    assert "學會本命:caocao" not in p.flags and set(p.arts) == arts and not any("傾囊相授" in m for m in msgs)
    assert not _said_keep(msgs)  # 進名單那一下不說
    assert not any(e.title == "深交" or any("看家本領" in line for line in e.lines) for e in game.state.journal)
    # 再談一輪：還是不教（也不說）
    msgs = _talk(game, "caocao")
    assert "學會本命:caocao" not in p.flags and not _said_keep(msgs) and not any("傾囊相授" in m for m in msgs)
    assert p.affinities["caocao"] > 70


def test_the_three_on_the_list_still_teach_even_with_a_slot_bought():
    game = _game()
    p = game.state.player
    _buy_slot(game)
    for cid in ARM3:
        assert figure_arts(game.content, game.content.characters[cid]), cid  # 這三位真的有本命可教
    for cid in ARM3:
        p.affinities[cid] = 69
        msgs = _talk(game, cid)
        assert p.affinities[cid] >= 70 and f"學會本命:{cid}" in p.flags and any("傾囊相授" in m for m in msgs), cid
        assert not _said_keep(msgs), cid
    assert p.deep_order == list(ARM3)
    p.affinities["caocao"] = 69
    msgs = _talk(game, "caocao")
    assert p.deep_order[-1] == "caocao" and "學會本命:caocao" not in p.flags and not any("傾囊相授" in m for m in msgs)


def test_a_bought_slot_lets_in_a_figure_with_nothing_to_give_and_keeps_his_affinity():
    game = _game()
    s, c = game.state, game.content
    p = s.player
    arm_owners = {arm.character for arm in c.gear.signature_arms}
    bare = next(cid for cid, ch in c.characters.items() if cid not in arm_owners and not figure_arts(c, ch))  # 沒有本命、也沒有本命兵器的人物
    _set(game, LIST3)
    zhuan_end.enforce_deep_cap(s, c, slots=1)
    _set(game, {bare: 75})
    assert zhuan_end.enforce_deep_cap(s, c, slots=1) == [] and p.deep_order[-1] == bare and p.affinities[bare] == 75
    # 本命武學已經學過、本命兵器這一季已經給了別人：照樣進名單
    p.flags.add("學會本命:caocao")
    s.world.signature_arms["caocao"] = SignatureClaim(owner="別人", via="gift")
    _set(game, {"caocao": 75})
    assert zhuan_end.enforce_deep_cap(s, c, slots=2) == [] and p.deep_order[-1] == "caocao"


def test_nobody_is_held_back_without_a_bought_slot_the_fourth_just_stops_at_69():
    game = _game()
    p = game.state.player
    _set(game, LIST3)
    game.sync(game.now)
    p.affinities["caocao"] = 69
    msgs = _talk(game, "caocao")
    assert p.affinities["caocao"] == 69 and "學會本命:caocao" not in p.flags
    assert not any("停在 69" in m or "你已深交" in m for m in msgs)  # 批 7d：夾在 69 的規則照 7b，可是那一句不給玩家看
    assert not _said_keep(msgs)


def test_a_freed_place_lets_the_slot_figure_in_and_he_teaches_on_the_next_talk():
    game = _game()
    p = game.state.player
    _set(game, LIST3)
    game.sync(game.now)
    _buy_slot(game)
    p.affinities["caocao"] = 69
    _talk(game, "caocao")
    assert "學會本命:caocao" not in p.flags
    _set(game, {"luzhi": 60})  # 名單裡的人情誼掉下 70：位子讓出來（deep_order 還沒整理，也照此刻的情誼算）
    msgs = _talk(game, "caocao")
    assert "學會本命:caocao" in p.flags and any("傾囊相授" in m for m in msgs)


def test_a_slot_figure_sends_no_arm_at_80_while_the_three_on_the_list_do():
    game = _game()
    p = game.state.player
    _set(game, ARM3)
    game.sync(game.now)
    _buy_slot(game)
    _set(game, {"caocao": 85})
    game.sync(game.now)
    assert p.deep_order == list(ARM3) + ["caocao"] and p.affinities["caocao"] == 85
    game.choose("act:explore")
    claims = game.state.world.signature_arms
    assert set(claims) == set(ARM3) and "caocao" not in claims  # 名單內三位照舊會送，靠名額的那一位不送
    assert p.affinities["caocao"] == 85  # 情誼不被夾


def test_a_freed_place_brings_the_slot_figures_arm():
    game = _game()
    p = game.state.player
    _set(game, ARM3)
    game.sync(game.now)
    _buy_slot(game)
    _set(game, {"caocao": 85})
    game.sync(game.now)

    def _next_action() -> None:  # 每個動作最後的那兩步（Game.choose 在 _log 之前叫；探索會撞上事件，第二下按不了，所以直接叫）
        game._deep_cap_now()
        game._signature_arms()

    _next_action()
    assert "caocao" not in game.state.world.signature_arms and set(game.state.world.signature_arms) == set(ARM3)
    _set(game, {"guanyu": 60})  # 名單裡有人掉下 70（deep_order 沒整理）
    _next_action()
    assert "caocao" in game.state.world.signature_arms


def test_the_seize_route_does_not_look_at_the_slot():
    """孫堅的本命兵器還有一條路：這一季打贏他本人 signature_wins 次（跟情誼無關），靠名額深交的孫堅一樣奪得走。"""
    game = _game()
    p = game.state.player
    _set(game, {**LIST3, "sunjian": 90})
    p.deep_order = [*LIST3, "sunjian"]
    assert zhuan_end.by_slot(game.state, game.content, "sunjian")
    p.figure_wins["sunjian"] = game.content.config.weapons.signature_wins
    items, _ = signature_arms.due(game.state, game.content)
    assert [item.signature for item in items] == ["sunjian"]
    assert game.state.world.signature_arms["sunjian"].via == "seized"


def test_by_slot_follows_the_live_list_and_the_switch():
    game = _game()
    s, c = game.state, game.content
    s.player.deep_order = ["zhujun", "huangfusong", "luzhi", "caocao"]
    _set(game, {**LIST3, "caocao": 75})
    assert [zhuan_end.by_slot(s, c, cid) for cid in s.player.deep_order] == [False, False, False, True]
    _set(game, {"zhujun": 50})  # 掉下去的讓出位子，後面的遞補
    assert [zhuan_end.by_slot(s, c, cid) for cid in s.player.deep_order] == [False, False, False, False]
    assert not zhuan_end.by_slot(s, c, "nobody")
    off = _game(zhuan_end=False)
    off.state.player.deep_order = ["zhujun", "huangfusong", "luzhi", "caocao"]
    _set(off, {**LIST3, "caocao": 75})
    assert not zhuan_end.by_slot(off.state, off.content, "caocao")  # 關著什麼都不管


def test_the_shop_note_says_what_the_slot_does_not_give():
    game = _game()
    note = game.content.mall["deep_slot"].note
    assert "不給數值" in note and "本命武學" in note and "本命兵器" in note
    shelf = {row["id"]: row for row in game.mall_view()["items"]}
    assert "本命武學" in shelf["deep_slot"]["note"] and "不給數值" in shelf["deep_slot"]["note"]  # 商城那一格照內容的說明


def test_a_bot_never_holds_a_slot_so_the_fourth_stops_at_69_like_a_human_without_one():
    game = _game()
    p = game.state.player
    p.bot = True
    _set(game, LIST3)
    game.sync(game.now)
    _set(game, {"caocao": 75})
    game.sync(game.now)
    assert p.affinities["caocao"] == 69 and len(p.deep_order) == 3
    assert not any(zhuan_end.by_slot(game.state, game.content, cid) for cid in p.deep_order)
