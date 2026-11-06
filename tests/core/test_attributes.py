"""屬性與跨季架構 v2 第十節 ① 骨架：屬性定義、效果表（team.attr_effect）、相對檢定與獎勵等級（content.resolve_grades）。

現在的四項與現在的數字接上骨架，玩家看到的一個字都不變（scripts/same_behavior.py 另外證明）；這裡守表的讀法與掃描。"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

from conftest import real_content
from tianxia import content as content_mod, rules, team
from tianxia.content import ContentError
from tianxia.models import AttrEffect, Check, Effect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import convert_grades  # noqa: E402


def test_attributes_file_names_the_four_and_lore_in_order():
    c = real_content()
    assert tuple(a.key for a in c.attributes) == team.COMBAT_STATS
    assert {a.key: c.config.stat_names[a.key] for a in c.attributes} == {a.key: a.name for a in c.attributes}


def test_a_new_name_in_attributes_json_reaches_stat_names(tmp_path):
    c = real_content()
    path = tmp_path / "attributes.json"
    raw = [{"key": a.key, "name": a.name} for a in c.attributes]
    raw[0]["name"] = "武力"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    content_mod._load_attributes(c, path)
    assert c.config.stat_names["str"] == "武力"


def test_the_default_effect_table_is_todays_numbers():
    c = real_content()
    cfg = c.config
    for value in (1, 5, 9.5, 15):
        assert team.hook_effect(c, "outer", {"str": value}) == cfg.stat_bonus_per_point * (value - team.BASE_STAT)
        assert team.hook_effect(c, "inner", {"con": value}) == cfg.stat_bonus_per_point * (value - team.BASE_STAT)
        assert team.hook_effect(c, "dodge", {"agi": value}) == (value - team.BASE_STAT) * cfg.dodge_per_point
        assert team.hook_effect(c, "outer", {"str": value}) == team.stat_bonus(c, value)


def test_curves_and_summing():
    c = real_content()
    c.config.attributes.effects = [
        AttrEffect(attr="str", hook="outer", curve="contest", cap=0.5, scale=10),
        AttrEffect(attr="wis", hook="outer", curve="tiers", steps=[(40, 0.1), (80, 0.2)]),
    ]
    got = team.hook_effect(c, "outer", {"str": 60, "wis": 85}, rivals={"str": 50})
    assert got == pytest.approx(0.5 * math.tanh(1.0) + 0.2)
    assert team.hook_effect(c, "outer", {"str": 50, "wis": 39}, rivals={"str": 50}) == 0.0
    assert team.hook_effect(c, "dodge", {"agi": 15}) == 0.0  # 沒掛任何一條


def test_effect_rows_are_checked_on_load():
    c = real_content()
    c.config.attributes.effects = [AttrEffect(attr="luck", hook="nowhere")]
    with pytest.raises(ContentError, match="luck"):
        content_mod.validate(c)


# ── 相對檢定、獎勵等級 ──


def test_grade_resolves_to_dc_plus_shift_and_serialises_back():
    c = real_content()
    check = Check(stat="wis", grade="hard", shift=1)
    effect = Effect(stats={"silver": "medium", "fame": 1})
    first = next(e for e in c.events.values() if e.choices)  # 塞進一則事件的第一個選項
    first.choices[0].check = check
    first.choices[0].effect = effect
    content_mod.resolve_grades(c)
    assert check.difficulty == 8
    assert list(effect.stats.items()) == [("silver", 20), ("fame", 1)]  # 鍵的順序不動
    assert check.model_dump() == {"stat": "wis", "grade": "hard", "shift": 1, "by": "team", "practice": None}
    assert Check(stat="wis", difficulty=6).model_dump()["difficulty"] == 6


def test_bad_grades_are_refused():
    c = real_content()
    first = next(e for e in c.events.values() if e.choices)
    first.choices[0].check = Check(stat="wis", grade="impossible")
    with pytest.raises(ContentError, match="impossible"):
        content_mod.resolve_grades(c)
    with pytest.raises(ValueError):
        Check(stat="wis")
    with pytest.raises(ValueError):
        Check(stat="wis", difficulty=5, shift=1)


def test_real_content_writes_grades_and_the_bands_match_the_ruling():
    """企劃者 2026-11-04「照建議」：3～4 易、5～6 尋常、7～8 難、9～12 極難、13 以上傳說。"""
    for d, key in ((3, "easy"), (4, "easy"), (5, "normal"), (6, "normal"), (7, "hard"), (8, "hard"),
                   (9, "harsh"), (12, "harsh"), (13, "legend"), (15, "legend")):
        grade, shift = convert_grades.grade_of(d)
        assert grade == key
        dc = {g.key: g.dc for g in real_content().config.checks.grades}[grade]
        assert dc + shift == d
    leftover = [p.name for p in content_mod.real_files().values()
                if convert_grades.convert_text(p.read_text(encoding="utf-8"))[1]]
    assert leftover == [], f"還有寫舊難度的檢定：跑 python scripts/convert_grades.py checks --apply（{leftover}）"


def test_check_rules_are_todays_odds(content):
    cfg = content.config.checks
    assert (cfg.base_rate, cfg.per_point, cfg.floor, cfg.ceil) == (0.5, 0.1, 0.05, 0.95)
    assert rules.check_expect.__doc__  # 期望值的讀點存在（現在＝江湖水漲）


# ── 掃描：直接讀屬性鍵的地方只准少、不准多 ──

DIRECT = re.compile(r"""(?:get\(|\[)["'](?:str|agi|con|wis|lore)["']""")
# 第 ① 階段留著的（多半是正在搬包的修練、有所感兩包，或只是拿顯示名）：之後改走 attr_effect，改完把數字調低
ALLOWED = {  # 第 ② 階段第 1 批把本人的舊讀點都改走 team.v1_stat／attrset.legacy；剩下的是顯示名、部下與同伴的模板、設定表
    "tianxia/features/cultivation/chuangong.py": 3, "tianxia/skillview.py": 1, "tianxia/team.py": 4, "tianxia/models.py": 3,
}


def test_direct_attribute_reads_only_shrink():
    found: dict[str, int] = {}
    for path in [*(ROOT / "tianxia").rglob("*.py"), ROOT / "server.py"]:
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel:
            continue
        n = len(DIRECT.findall(path.read_text(encoding="utf-8")))
        if n:
            found[rel] = n
    grew = {k: (v, ALLOWED.get(k, 0)) for k, v in found.items() if v > ALLOWED.get(k, 0)}
    assert not grew, f"新的地方直接讀屬性：改走 team.attr_effect（效果表 Config.attributes.effects）{grew}"
