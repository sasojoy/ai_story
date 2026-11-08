"""易名帖：客服本人也不能改名（帳號與客服第 212 批；計畫「J 波落地時 PM 加的」第 2 條）。客服名單認帳號（core/identity_base.support_staff_name：
名號 → 帳號 → 名單），客服開關（Config.support.enabled）關著不多擋；擋下來帖不用掉、什麼都不動。"""
from __future__ import annotations

import pytest
from test_mall import _wallet
from test_mall_card_daily import _ready, _rename_on, on  # noqa: F401  on 是 fixture

from tianxia import content as content_module
from tianxia.accounts import AccountStore
from tianxia.core import identity_base
from tianxia.features.mall import actions as mall_actions
from tianxia.features.mall import rules as mall


@pytest.fixture
def staff_game(on, monkeypatch, tmp_path):  # noqa: F811
    """沈浪有帳號 kefu_01、買了一張易名帖；名單寫 kefu_01。這台機器的 .local/support.txt、TIANXIA_SUPPORT 隔開。"""
    monkeypatch.setattr(content_module, "LOCAL_DIR", tmp_path)
    monkeypatch.delenv(identity_base.SUPPORT_ENV, raising=False)
    identity_base._support_cache.update(path=None, mtime=None, names=frozenset())
    game = _ready(_rename_on(on))
    accounts = AccountStore(game.world.db)
    accounts.register("kefu_01", "secret-pw")
    accounts.bind_character("kefu_01", "沈浪")
    mall_actions.buy(game, "rename", "n")
    on.config.support.staff = ["kefu_01"]
    return game


def test_staff_cannot_rename_when_support_on(staff_game):
    staff_game.content.config.support.enabled = True
    w = _wallet(staff_game)
    before = (w.balance("沈浪"), len(mall.rename_tokens(w, "沈浪")))
    assert mall_actions.rename_self(staff_game, "沈青") == [mall_actions.RENAME_STAFF]
    assert staff_game.state.player.name == "沈浪"
    assert (w.balance("沈浪"), len(mall.rename_tokens(w, "沈浪"))) == before == (5000 - 300, 1)  # 帖不用掉


def test_support_off_staff_renames_as_before(staff_game):
    assert staff_game.content.config.support.enabled is False
    msg = mall_actions.rename_self(staff_game, "沈青")
    assert "沈青" in msg[0] and staff_game.state.player.name == "沈青"


def test_non_staff_renames_when_support_on(staff_game):
    staff_game.content.config.support.enabled = True
    staff_game.content.config.support.staff = ["someone_else", "999"]
    msg = mall_actions.rename_self(staff_game, "沈青")
    assert "沈青" in msg[0] and staff_game.state.player.name == "沈青"
