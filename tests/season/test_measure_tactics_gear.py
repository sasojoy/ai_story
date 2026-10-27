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

ROOT = Path(__file__).parents[2]


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
    """正式內容、玉璽碎片改版（Config.seal.revamp，預設開）關掉：--gear 量的是舊的七個效果（gear 自己跑的時候也暫時關掉改版）；
    改版的效果鍵照樣要分類（下一條）。"""
    c = load_content(ROOT / "content")
    c.config.seal.revamp.enabled = False
    return c


def test_every_treasure_and_seal_effect_is_classified(m, content):
    """KIND 涵蓋寶物與玉璽的每一個效果鍵（新加的寶物或碎片效果要先來分類，平衡表才不會漏），也只有這些鍵。
    玉璽碎片改版的效果鍵（content/seal.json 的 effects，數字在 Config.seal.revamp.effects）也算（改版設計第三章）。"""
    keys = (set(content.config.treasures.effects) | set(TREASURE_EFFECTS) | {s.effect for s in content.seal.values()}
            | {k for s in content.seal.values() for k in s.effects} | set(content.config.seal.revamp.effects))
    assert set(m.KIND) == keys
    assert set(m.KIND.values()) <= {m.DIRECT, m.INDIRECT, m.UNTOUCHED}
    assert set(m.NOTE) == set(m.KIND)
    assert {k for k, v in m.KIND.items() if v == m.DIRECT} == {"dodge", "hp_cap"}


def test_gear_rows_read_the_numbers_from_config(m, content):
    rows = m.gear_rows(content)
    assert len(rows) == len(content.config.treasures.effects) + len(content.seal) == 15
    for r in rows:
        table = content.config.treasures.effects if r.source == "寶物" else content.config.seal.effects
        assert r.kind == m.KIND[r.key]
        if r.key == "insight" and content.config.explore_modes.enabled:
            continue  # 觀山石：探索三選一開著時數字出自 sense_treasure_points（FB-455，下面另一條驗）
        assert r.value == table[r.key]
        assert r.field.endswith(f"effects[{r.key}]")
    assert [r.name for r in rows if r.source == "玉璽"] == [s.name for s in content.seal.values()]
    # 改了 Config 的數字，表跟著變（不寫死）
    tweaked = content.model_copy(deep=True)
    tweaked.config.seal.effects["dodge"] = 0.07
    assert next(r for r in m.gear_rows(tweaked) if r.key == "dodge").value == 0.07


def test_the_insight_row_names_the_field_its_number_comes_from(m, content):
    """FB-455：觀山石那一列照探索三選一的開關標數字出自哪個欄位——開著時「+15 個百分點」是 sensing.rate 加的
    Config.explore_modes.sense_treasure_points（effects[insight] 的 1.5 只拿來比 > 1），關著才是 Config.treasures.effects[insight] 的倍數。"""
    cfg = content.config
    assert cfg.explore_modes.enabled  # 正式內容開著
    sense = cfg.explore_modes.sense_treasure_points
    row = next(r for r in m.gear_rows(content) if r.key == "insight")
    assert (row.field, row.value) == ("Config.explore_modes.sense_treasure_points", sense)
    assert f"+{sense:g} 個百分點" in row.text  # 同一列的字跟它標的數字對得上
    # 間接那一行照舊說 effects[insight] 的倍數只在三選一關著時用
    line = m._indirect(content, row)
    assert f"Config.treasures.effects[insight]＝{cfg.treasures.effects['insight']:g} 只在三選一關著時用" in line
    closed = content.model_copy(deep=True)
    closed.config.explore_modes.enabled = False
    row = next(r for r in m.gear_rows(closed) if r.key == "insight")
    assert (row.field, row.value) == ("Config.treasures.effects[insight]", closed.config.treasures.effects["insight"])
    assert f"×{row.value:g}" in row.text


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
    # 武學重構合進來之後 full_kit 換成槽裝滿的那一套、slot_kit 換成 slots_kit：照合併當下（2026-10-21）重抄；
    # 招式與絕學稿案二～四批合進 main（2026-10-21，純／渾與後勁改了整套的手感）再抄一次；
    # 2026-10-22 玩家那一套的真意不再算兩次（跟遊戲一樣），又抄一次
    assert share(m.full_kit(content, 0), m.self_kit(content, 0)) == 0.7948717948717948
    assert share(m.slots_kit(content, 0, "中品", 2), m.self_kit(content, 0)) == 0.4864864864864865
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
    assert content.config.seal.revamp.enabled  # 改版量的時候暫時關掉，量完放回去


def test_chizhang_row_reads_the_create_odds(m, content):
    """武學重構：赤璋改加自創的意分（create.seal_points），那一行照 create.power_scale_of 寫。main 的 d0ca2c25 起自創一律
    Config.arts.create_grade（create.grade_odds 拿掉了），那一行改寫品級固定、意分只推底子（release/1021 合併，FB-640 那一輪）。"""
    line = m._indirect(content, next(r for r in m.gear_rows(content) if r.key == "fuse_points"))
    assert "自創的意分" in line and "底子" in line and content.config.arts.create_grade in line


def test_player_kits_count_each_tactic_once(m, content):
    """量表組的玩家那一套跟遊戲一樣，同名的戰法只有一個（真意曾經加兩次：tactic_defs 已經帶著，又另外加一次）。"""
    kits = [m.piece_kit(content, 0, "上品", 3, 1.0, 0.5), m.stack_kit(content, 0), m.own_kit(content, 0, ascended=True)]
    for hs in kits:
        names = [h.tactic.name for h in hs]
        assert len(names) == len(set(names)), names
