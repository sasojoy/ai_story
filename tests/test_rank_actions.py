"""第一季正式版・戊一：第 3、4 階的行動（計畫 2026-10-06-第一季正式版-戊一）。

用真實內容（content/）：fixture real、on 在 tests/conftest.py（每個測試拿 real_content 的一份複本；on 是週末設定打開）。"""
from __future__ import annotations

import random
from unittest import mock

import pytest
from pydantic import ValidationError

from tianxia import models, rules
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import OrdersContent, RankAction
from tianxia.state import PlayerState


def _game(content, faction, at, rank=3):
    game = Game.new(content, "甲", rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank, p.location, p.stamina = faction, rank, at, 100
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def _always(ok=True):
    return mock.patch.object(rules, "check_chance", return_value=1.0 if ok else 0.0)


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_defaults_so_old_saves_load():
    assert PlayerState(name="甲", location="x", stats={}, stamina=0).rank_action_weeks == {}
    assert OrdersContent().rank_actions == []


def test_real_rank_actions(real):
    by_id = {a.id: a for a in real.orders.rank_actions}
    assert set(by_id) == {"incite", "fortify", "seize"}
    assert (by_id["seize"].rank, by_id["seize"].weekly, by_id["seize"].push) == (4, 1, 10)


def test_the_real_rows_follow_the_plan_table(real):
    """內容表（計畫 Task 1）：每一格都照寫；機制數字是【預設】，改了要改這裡與計畫。"""
    rows = {
        a.id: (a.faction, a.rank, a.name, a.stamina, a.weekly, a.tags, a.chaos_only,
               None if a.check is None else (a.check.stat, a.check.difficulty), a.push)
        for a in real.orders.rank_actions
    }
    assert rows == {
        "incite": ("huang", 3, "在一地煽動起事", 20, 3, ["城鎮"], False, ("wis", 7), 5),
        "fortify": ("haoqiang", 3, "修築塢堡", 20, 3, [], True, None, 5),
        "seize": ("haoqiang", 4, "趁亂占據郡縣", 30, 1, ["城鎮"], True, None, 10),
    }


def test_the_real_texts_name_the_place(real):
    """成功與失敗的敘事都是照{地點}填的；沒有檢定的行動不會失敗，沒有 fail。"""
    by_id = {a.id: a for a in real.orders.rank_actions}
    assert all("{地點}" in a.ok for a in by_id.values())
    assert "{地點}" in by_id["incite"].fail and by_id["fortify"].fail == "" and by_id["seize"].fail == ""


def test_real_content_with_rank_actions_validates(real):
    validate(real)  # 沒有檢定的行動 fail 空著是合法的（修築塢堡、趁亂占據郡縣）


def test_rank_action_faction_must_exist(real):
    real.orders.rank_actions[0].faction = "nobody"
    with pytest.raises(ContentError, match="rank_actions"):
        validate(real)


def test_rank_action_ids_must_not_repeat(real):
    real.orders.rank_actions.append(real.orders.rank_actions[0].model_copy())
    with pytest.raises(ContentError, match="rank_actions.*id 重複"):
        validate(real)


@pytest.mark.parametrize("field", ["name", "ok", "fail"])
def test_rank_action_text_must_be_traditional(real, field):
    incite = next(a for a in real.orders.rank_actions if a.id == "incite")
    setattr(incite, field, "这里的话是简体")
    with pytest.raises(ContentError, match="rank_actions.incite.*繁體"):
        validate(real)


def test_a_check_needs_a_fail_text(real):
    """有檢定就會有失敗：fail 空著，每次失敗第一句是空的。"""
    next(a for a in real.orders.rank_actions if a.id == "incite").fail = ""
    with pytest.raises(ContentError, match="fail"):
        validate(real)


def test_a_blank_fail_text_does_not_count(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").fail = "  "
    with pytest.raises(ContentError, match="fail"):
        validate(real)


def test_tags_must_be_tags_some_location_carries(real):
    """拼錯的標籤：那個行動在哪裡都不會出現，載入時就擋。"""
    next(a for a in real.orders.rank_actions if a.id == "incite").tags = ["城池村"]
    with pytest.raises(ContentError, match="tags"):
        validate(real)


def test_tags_may_mix_known_tags(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").tags = ["城鎮", "營寨"]
    validate(real)


def test_the_check_stat_must_be_a_known_stat(real):
    next(a for a in real.orders.rank_actions if a.id == "incite").check.stat = "luck"
    with pytest.raises(ContentError, match="未知的屬性 luck"):
        validate(real)


@pytest.mark.parametrize("change", [{"rank": 2}, {"rank": 5}, {"stamina": -1}, {"weekly": 0}, {"push": 0}, {"surprise": 1}])
def test_the_model_refuses_nonsense_numbers_and_unknown_fields(change):
    fields = {"id": "x", "faction": "huang", "rank": 3, "name": "甲", "stamina": 1, "weekly": 1, "push": 1, "ok": "好"}
    with pytest.raises(ValidationError):
        RankAction(**{**fields, **change})


def test_the_menu_family_is_registered_for_tutorial_allow_lists():
    """教學與入伍的 allow 要能寫 act:rank:…（models.ALLOW_FAMILIES；沒列的話那一步會把選單清空）。"""
    assert models.allow_known("act:rank:incite") and models.allow_known("act:rank:")
    assert not models.allow_known("act:rankings")  # 前綴是整個「act:rank:」，不是 act:rank 開頭的任何字串
