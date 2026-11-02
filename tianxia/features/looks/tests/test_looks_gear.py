"""疊圖飾品（Joy 2026-11-02 選「疊圖飾品」）：content/looks.json 寫了 slot 的那幾件。頭、臉、腰各戴一件，任何一套形象都戴得上；
擂台、走一趟送的皮是「形象~飾品.飾品」；假人也照名號戴（不然戴飾品的一定是真人）。"""
from __future__ import annotations

import pytest
from test_looks import _game, on  # noqa: F401  on 是 fixture

from tianxia.features.looks import actions, rules
from tianxia.features.mall import rules as mall_rules
from tianxia.models import Look, MallItem
from tianxia.wallet import Wallet


@pytest.fixture
def gear(on):  # noqa: F811
    on.looks.update({
        "head_red_band": Look(id="head_red_band", name="紅頭巾", slot="head", bots=True),
        "head_straw": Look(id="head_straw", name="草帽", slot="head"),
        "waist_jade": Look(id="waist_jade", name="玉佩", slot="waist"),
    })
    for gid, name in (("head_red_band", "紅頭巾"), ("head_straw", "草帽"), ("waist_jade", "玉佩")):
        on.mall[f"gear_{gid}"] = MallItem(id=f"gear_{gid}", name=name, price=150, kind="look", look=gid, effects={"gear": 1})
    return on


def test_buy_wear_swap_and_take_off(gear):
    game = _game(gear)
    assert game.arena_look() == "" and actions.view(game)["gear"][0]["item"] == "gear_head_red_band"
    assert actions.wear_gear(game, "head_red_band")[-1] == rules.GEAR_NOT_OWNED
    for gid in ("head_red_band", "head_straw", "waist_jade"):
        game.mall_buy(f"gear_{gid}", f"ref-gear-{gid}")
    assert Wallet(game.world.db).balance("沈浪") == 5000 - 450
    assert "戴上了「紅頭巾」" in actions.wear_gear(game, "head_red_band")[-1]
    actions.wear_gear(game, "waist_jade")
    assert game.arena_look() == "~head_red_band.waist_jade"  # 預設的斗笠小子也戴得上
    actions.wear_gear(game, "head_straw")  # 同一個位置換一件
    assert game.arena_look() == "~head_straw.waist_jade"
    game.mall_buy("look_moying", "ref-look-moying")
    actions.wear(game, "moying")
    assert game.arena_look() == "moying~head_straw.waist_jade" and game.feature_status()["look"] == "moying~head_straw.waist_jade"
    assert "拿下了「草帽」" in actions.wear_gear(game, "head_straw")[-1]
    view = actions.view(game)
    assert view["skin"] == "moying~waist_jade" and [g["id"] for g in view["gear"] if g["worn"]] == ["waist_jade"]
    assert [lk["id"] for lk in view["looks"]] == ["", "moying", "jinshen"]  # 飾品不混進整套的那一排
    assert actions.wear(game, "waist_jade")[-1] == rules.NOT_OWNED  # 飾品不能當整套穿


def test_bots_wear_gear_by_name_and_some_wear_none(gear):
    picks = {tuple(rules.bot_gear(gear, f"假{i}")) for i in range(40)}
    assert () in picks and ("head_red_band",) in picks
    assert all(set(p) <= {"head_red_band"} for p in picks)  # bots 關著的不戴
    assert rules.bot_gear(gear, "假3") == rules.bot_gear(gear, "假3")


def test_content_checks_gear_ids_and_effects(gear):
    gear.looks["waist_bad"] = Look(id="head_bad", name="壞", slot="waist")
    gear.looks["head_whole"] = Look(id="head_whole", name="全套")
    problems = rules.problems(gear)
    assert any("head_bad" in p and "waist_" in p for p in problems) and any("head_whole" in p for p in problems)
    wrong = MallItem(id="gear_wrong", name="錯的", price=150, kind="look", look="waist_jade", effects={"look": 1})
    assert any("飾品的效果只寫" in p for p in mall_rules.item_problems(wrong, gear))
