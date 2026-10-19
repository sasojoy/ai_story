"""scripts/measure_tactics.py 的 --gear（第 35 項：寶物八種、玉璽七片哪些進打仗）要一直跑得動、分類不能漏。
腳本不在引擎裡，引擎改了它就悄悄壞掉；這裡只跑小場面、不驗平衡，驗「分類涵蓋每一個效果鍵、數字照 Config 讀、跑得完、結果合理」。"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest import mock

import pytest

from tianxia.content import load_content
from tianxia.models import TREASURE_EFFECTS

pytestmark = pytest.mark.slow  # 每一條都載正式內容（超過一秒）；gear 那一條跑整段

ROOT = Path(__file__).parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("measure_tactics", ROOT / "scripts" / "measure_tactics.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_tactics"] = module
    with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):  # 匯入時它會換掉 stdout
        spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def m():
    return _load()


@pytest.fixture(scope="module")
def content():
    return load_content(ROOT / "content")


def test_every_treasure_and_seal_effect_is_classified(m, content):
    """KIND 涵蓋寶物與玉璽的每一個效果鍵（新加的寶物或碎片效果要先來分類，平衡表才不會漏），也只有這些鍵。"""
    keys = set(content.config.treasures.effects) | set(TREASURE_EFFECTS) | {s.effect for s in content.seal.values()}
    assert set(m.KIND) == keys
    assert set(m.KIND.values()) <= {m.DIRECT, m.INDIRECT, m.UNTOUCHED}
    assert set(m.NOTE) == set(m.KIND)
    assert {k for k, v in m.KIND.items() if v == m.DIRECT} == {"dodge", "hp_cap"}


def test_gear_rows_read_the_numbers_from_config(m, content):
    rows = m.gear_rows(content)
    assert len(rows) == len(content.config.treasures.effects) + len(content.seal) == 15
    for r in rows:
        table = content.config.treasures.effects if r.source == "寶物" else content.config.seal.effects
        assert r.value == table[r.key]
        assert r.kind == m.KIND[r.key]
    assert [r.name for r in rows if r.source == "玉璽"] == [s.name for s in content.seal.values()]
    # 改了 Config 的數字，表跟著變（不寫死）
    tweaked = content.model_copy(deep=True)
    tweaked.config.seal.effects["dodge"] = 0.07
    assert next(r for r in m.gear_rows(tweaked) if r.key == "dodge").value == 0.07


def test_the_jinjiao_holder_reaches_the_real_dodge_hook(m, content):
    from tianxia import team
    gain = content.config.seal.effects["dodge"]
    assert team.dodge_chance(m.wearing(content, None), content) == 0
    assert team.dodge_chance(m.wearing(content, "dodge"), content) == pytest.approx(gain)
    assert team.dodge_chance(m.wearing(content, "dodge", agi=15), content) == pytest.approx(10 * content.config.dodge_per_point + gain)


def test_dodge_only_turns_losses_into_draws(m, content):
    for kit in ([], m.kit_full(content, 0)):
        for ratio in (0.6, 1.0):
            floor = None if ratio < 0.8 else 0.1
            bare, same, worn = m.dodge_table(content, 200, kit, ratio, [0.0, 0.0, 0.5], draw_floor=floor)
            assert bare == same  # 機率一樣，結果一模一樣
            assert bare["落敗"] > 0  # 這一格真的有輸的（不然量不到金角）
            assert worn["大勝"] == bare["大勝"] and worn["險勝"] == bare["險勝"]
            assert worn["落敗"] < bare["落敗"] and worn["僵持"] > bare["僵持"]
            assert worn["落敗"] + worn["僵持"] == pytest.approx(bare["落敗"] + bare["僵持"])
    small = m.dodge_table(content, 200, [], 0.6, [0.0, content.config.seal.effects["dodge"]])
    assert small[1]["落敗"] <= small[0]["落敗"] and small[1]["僵持"] >= small[0]["僵持"]


def test_chain_table_is_repeatable_and_in_range(m, content):
    a = m.chain_table(content, 30, 3, 1.0)
    assert a == m.chain_table(content, 30, 3, 1.0)  # 種子固定
    assert len(a) == 3
    assert all(0 <= won <= 1 and 0 <= left <= 1 for won, left in a)
    assert a[-1][1] < 1  # 連打不療傷，氣血真的有掉
    assert len(m.chain_table(content, 30, 3, content.config.seal.effects["hp_cap"])) == 3


def test_ring_share_without_the_new_arguments_is_unchanged(m, content):
    """ring_share 多了 hp_a、hp_b（螭首用），不帶時跟加之前一模一樣（改之前照同一份內容量下的三個數）。"""
    share = m.ring_share(content, 20)
    assert share([], []) == 0.45454545454545453
    assert share(m.full_kit(content, 0), m.self_kit(content, 0)) == 0.6388888888888888
    assert share(m.slot_kit(content, 0, "rolled"), m.self_kit(content, 0)) == 0.6363636363636364
    assert m.ring_share(content, 20, hp_a=1000, hp_b=1000)([], []) == share([], [])


def test_gear_runs_to_the_end_and_names_every_effect(m):
    content = load_content(ROOT / "content")  # gear 會暫時打開兩個開關，用自己的一份
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out):
        m.gear(content, 10, 2)
    text = out.getvalue()
    for item in content.gear.treasures.values():
        assert item.name in text
    for shard in content.seal.values():
        assert f"〔{shard.name}〕" in text
    for head in ("── 一覽", "── 直接", "── 間接", "── 不碰", "── 怎麼讀"):
        assert head in text
    assert "沒分類" not in text
    assert content.config.treasures.enabled and content.config.seal.enabled  # 量完放回去（正式內容本來就開著）
