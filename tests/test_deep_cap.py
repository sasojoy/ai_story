"""減法季批 7b-3：深交上限（企劃者 2026-10-24：同時情誼漲得過 signature_affinity〔70〕的人物最多 deep_figures〔3〕位，第 4 位起
停在 69、人物頁寫「已深交三位」；深交名額〔250 元寶、整季、只這一季〕讓它多一位）。情誼沒有單一寫入口，在 Game._log 裡事後夾。"""
from __future__ import annotations

import json

import pytest

from jianfa_kit import jianfa_game, ready
from tianxia import zhuan_end
from tianxia.characters import name_key
from tianxia.engine import Game
from tianxia.wallet import Wallet


def _game(**flags) -> Game:
    game = ready(jianfa_game(**flags), side="guan", loc="changshe")
    game.sync(game.now)
    return game


def _set(game: Game, values: dict[str, int]) -> None:
    game.state.player.affinities.update(values)


# ── 純規則 ──


@pytest.mark.slow
def test_the_fourth_stops_at_69_and_a_slot_lets_one_more_through():
    game = _game()
    s, c = game.state, game.content
    _set(game, {"huangfusong": 72, "luzhi": 70, "zhujun": 80})
    assert zhuan_end.enforce_deep_cap(s, c) == []
    assert s.player.deep_order == ["zhujun", "huangfusong", "luzhi"]  # 同一下過門檻的照情誼高、id 排
    _set(game, {"caocao": 75})
    lines = zhuan_end.enforce_deep_cap(s, c)
    assert s.player.affinities["caocao"] == 69 and lines == ["你已深交三位人物，曹操的情誼停在 69。"]
    assert zhuan_end.deep_note(s, c, "caocao") == "已深交三位"
    assert zhuan_end.deep_note(s, c, "luzhi") == "" and zhuan_end.deep_note(s, c, "zhangjiao") == ""
    _set(game, {"caocao": 75})
    # 名額票多一位；批 7c：靠名額進來的不給數值，進名單那一下說一句（曹操有本命武學與本命兵器可以給）
    assert zhuan_end.enforce_deep_cap(s, c, slots=1) == [zhuan_end.DEEP_KEEP.format(name="曹操")] and s.player.affinities["caocao"] == 75
    assert s.player.deep_order[-1] == "caocao"
    _set(game, {"luzhi": 60, "caocao": 75})  # 掉到 70 以下的讓出位子
    assert zhuan_end.enforce_deep_cap(s, c) == [] and "luzhi" not in s.player.deep_order


# ── 接線 ──


@pytest.mark.slow
def test_the_cap_holds_through_actions_and_sync_and_the_figure_page_says_so():
    game = _game()
    p = game.state.player
    _set(game, {"huangfusong": 72, "luzhi": 70, "zhujun": 80})
    game.sync(game.now)
    _set(game, {"caocao": 74})
    msgs = game.sync(game.now)  # 同步最後走 _log：在那裡夾
    assert p.affinities["caocao"] == 69 and "你已深交三位人物，曹操的情誼停在 69。" in msgs
    assert game.state.journal[0].title == zhuan_end.DEEP_TITLE
    assert game.affinity_text("caocao") == "情誼 69・已深交三位"
    assert game.affinity_text("zhujun") == "情誼 80"
    saved = json.loads(p.model_dump_json())
    assert saved["deep_order"] == ["zhujun", "huangfusong", "luzhi"]
    # 買了深交名額：這一季多一位
    wallet = Wallet(game.world.db)
    owner = name_key(p.name)
    wallet.post(owner, 1000, "grant", "test:deep", time=game.now)
    assert game.mall_buy("deep_slot", "deep-1")[0].startswith("買下")
    _set(game, {"caocao": 74})
    game.sync(game.now)
    assert p.affinities["caocao"] == 74 and game.affinity_text("caocao") == "情誼 74"


def _talk(game: Game, cid: str) -> list[str]:
    """跟 cid 談一輪（鎖外先生成好的那一輪，選「雪中送炭」那一類：情誼 +8 再照 affinity_gain_scale 打折）。"""
    from tianxia import companion_agent

    p = game.state.player
    p.pending_companion = cid
    p.last_offered_dialogue[cid] = [["送上一車糧草"], ["雪中送炭"]]
    turn = companion_agent.CompanionTurn(narrative="他點了點頭。", options=["再聊聊"], option_tags=["尋常寒暄"])
    return game.choose("talk:0", prepared=companion_agent.PreparedTurn("talk:0", cid, "送上一車糧草", turn))


@pytest.mark.slow
def test_the_fourth_figure_cannot_teach_the_signature_art_past_the_cap():
    """深交名單滿了，第四位人物在一輪對話裡越過 70：先夾回 69 才看本命武學（companion_agent._maybe_grant_signature_skill），
    不教、不記旗標；買了深交名額，情誼過得去，但他也不教（批 7c：買來的名額不給數值，教不教看有沒有排進名單裡前三位，見
    test_deep_slot_no_stats.py）。名將本命兵器（80）、贈禮在同一個動作裡照夾過的情誼判。"""
    game = _game()
    p = game.state.player
    _set(game, {"huangfusong": 72, "luzhi": 70, "zhujun": 80})
    game.sync(game.now)
    assert p.deep_order == ["zhujun", "huangfusong", "luzhi"]
    p.affinities["caocao"] = 69
    arts = set(p.arts)
    msgs = _talk(game, "caocao")
    assert p.affinities["caocao"] == 69 and "你已深交三位人物，曹操的情誼停在 69。" in msgs
    assert "學會本命:caocao" not in p.flags and set(p.arts) == arts and not any("傾囊相授" in m for m in msgs)
    wallet = Wallet(game.world.db)
    wallet.post(name_key(p.name), 1000, "grant", "test:deep3", time=game.now)
    assert game.mall_buy("deep_slot", "deep-3")[0].startswith("買下")
    msgs = _talk(game, "caocao")
    assert p.affinities["caocao"] >= 70 and p.deep_order[-1] == "caocao"  # 情誼過得去
    assert "學會本命:caocao" not in p.flags and set(p.arts) == arts and not any("傾囊相授" in m for m in msgs)  # 批 7c：靠名額的不教


@pytest.mark.slow
def test_a_signature_arm_waits_for_the_capped_affinity():
    """名將本命兵器在動作中途看情誼（Game._signature_arms，80）：這一下名單外的第四位情誼衝過 80，引擎先夾回 69 才送，送不出去。"""
    game = _game()
    p = game.state.player
    _set(game, {"huangfusong": 72, "luzhi": 70, "zhujun": 80})
    game.sync(game.now)
    p.affinities["caocao"] = 85  # 這一下的某個效果把他推過 80（直接寫，等同動作裡改的情誼）
    game.choose("act:explore")
    assert p.affinities["caocao"] == 69 and "caocao" not in game.state.world.signature_arms


@pytest.mark.slow
def test_the_slot_counts_only_this_season():
    from tianxia import mall

    game = _game()
    wallet = Wallet(game.world.db)
    owner = name_key(game.state.player.name)
    wallet.post(owner, 1000, "grant", "test:deep2", time=game.now)
    game.mall_buy("deep_slot", "deep-2")
    assert len(mall.tokens(wallet, owner, "deep_slot", season=1)) == 1
    assert mall.tokens(wallet, owner, "deep_slot", season=2) == []


@pytest.mark.slow
def test_off_no_cap_and_no_key():
    game = _game(zhuan_end=False)
    p = game.state.player
    _set(game, {"huangfusong": 72, "luzhi": 70, "zhujun": 80, "caocao": 75})
    game.sync(game.now)
    assert p.affinities["caocao"] == 75 and game.affinity_text("caocao") == "情誼 75"
    assert "deep_order" not in json.loads(p.model_dump_json())
