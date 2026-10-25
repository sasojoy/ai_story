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
    assert zhuan_end.enforce_deep_cap(s, c, slots=1) == [] and s.player.affinities["caocao"] == 75  # 名額票多一位
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
