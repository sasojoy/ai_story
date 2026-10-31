"""深交不限人數（企劃者 2026-10-28「不要限制深交名額」）：減法季批 7b～7d 的深交上限（同時最多三位情誼過 70、第四位停在 69）、
深交名額（萬寶閣 deep_slot）與「靠名額的不教不送」都拿掉了。情誼照舊一路往上長，知己不限人數，本命武學、名將本命兵器回原本的規則；
深交名額下架，已經買過的那一列照樣讀得出來、退得了款（mall.EFFECTS 還認得 deep_slot）。"""
from __future__ import annotations

import pytest

from jianfa_kit import jianfa_game, ready
from tianxia import mall
from tianxia.characters import name_key
from tianxia.engine import Game
from tianxia.models import MallItem
from tianxia.wallet import Wallet

pytestmark = pytest.mark.slow  # 每條都開一份減法季的正式內容世界

FOUR = {"huangfusong": 72, "luzhi": 70, "zhujun": 80, "caocao": 75}


def _game() -> Game:
    game = ready(jianfa_game(), side="guan", loc="changshe")
    game.sync(game.now)
    return game


def _talk(game: Game, cid: str) -> list[str]:
    """跟 cid 談一輪（鎖外先生成好的那一輪，選「雪中送炭」那一類：情誼往上加）。"""
    from tianxia import companion_agent

    p = game.state.player
    p.pending_companion = cid
    p.last_offered_dialogue[cid] = [["送上一車糧草"], ["雪中送炭"]]
    turn = companion_agent.CompanionTurn(narrative="他點了點頭。", options=["再聊聊"], option_tags=["尋常寒暄"])
    return game.choose("talk:0", prepared=companion_agent.PreparedTurn("talk:0", cid, "送上一車糧草", turn))


def test_the_fourth_deep_friend_keeps_growing_and_the_page_says_nothing_more():
    game = _game()
    p = game.state.player
    p.affinities.update(FOUR)
    game.sync(game.now)
    game.choose("act:explore")
    assert {cid: p.affinities[cid] >= v for cid, v in FOUR.items()} == dict.fromkeys(FOUR, True)
    assert game.affinity_text("caocao") == f"情誼 {p.affinities['caocao']}"
    assert p.deep_order == []


def test_the_fourth_figure_teaches_the_signature_art():
    game = _game()
    p = game.state.player
    p.affinities.update({"huangfusong": 72, "luzhi": 70, "zhujun": 80, "caocao": 69})
    game.sync(game.now)
    _talk(game, "caocao")
    assert p.affinities["caocao"] >= 70 and "學會本命:caocao" in p.flags


def test_the_fourth_figure_sends_the_signature_arm():
    game = _game()
    p = game.state.player
    p.affinities.update({"huangfusong": 72, "luzhi": 70, "zhujun": 80})
    game.sync(game.now)
    p.affinities["caocao"] = 85
    game.choose("act:explore")
    assert p.affinities["caocao"] == 85 and "caocao" in game.state.world.signature_arms


def test_the_slot_is_off_the_shelf_and_an_old_purchase_still_reads():
    game = _game()
    assert "deep_slot" not in game.content.mall
    assert "deep_slot" not in {item["id"] for item in game.mall_view()["items"]}
    assert game.mall_buy("deep_slot", "d1") == [mall.NO_ITEM]
    wallet = Wallet(game.world.db)
    owner = name_key(game.state.player.name)
    wallet.post(owner, 1000, "grant", "test:deep", time=game.now)
    # 下架之前買的那一列：暫時放回架上買一張，再拿掉，帳與退款照樣認得
    game.content.mall["deep_slot"] = MallItem.model_validate({
        "id": "deep_slot", "name": "深交名額", "note": "舊的", "price": 250, "kind": "consumable", "effects": {"deep_slot": 1}})
    assert game.mall_buy("deep_slot", "old-1")[0].startswith("買下")
    del game.content.mall["deep_slot"]
    assert game.mall_view()["items"] and mall.tokens(wallet, owner, "deep_slot", season=1)
    p = game.state.player
    p.affinities.update(FOUR)
    game.sync(game.now)
    assert p.affinities["caocao"] == 75 and p.deep_order == []  # 有沒有買過都一樣：不限人數
