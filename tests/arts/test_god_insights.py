"""神品意境模板（特殊頓悟第一批；設計稿 https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3）：四十個模板寫在 content/traits.json 的 god，
十路（八種屬性加正、邪）× 四型各一個；當大獎記在意境上時，查大獎的地方都找得到。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import real_content
from tianxia import insight_fx, traits
from tianxia.content import ContentError, load_content
from tianxia.models import GOD_FORMS


def test_forty_templates_one_per_path_and_form():
    c = real_content()
    gods = c.traits.god
    assert len(gods) == 40
    paths = {(g.attribute, g.lean) for g in gods}
    assert len(paths) == 10
    assert {("陽", "正"), ("陰", "邪")} <= paths
    for path in paths:
        assert sorted(g.form for g in gods if (g.attribute, g.lean) == path) == sorted(GOD_FORMS)


def test_templates_carry_a_general_of_their_own_attribute():
    c = real_content()
    for g in c.traits.god:
        general = traits.general(c, g.general)
        assert general is not None and general.attribute == g.attribute, g.id


def test_a_god_template_resolves_like_a_grand():
    c = real_content()
    g = c.traits.god[0]
    assert insight_fx.grand(c, g.id) is g
    assert traits.high(c, g.id) is g
    assert insight_fx.grand_of(c, g.attribute) not in c.traits.god  # 合成照舊拿那一路的真意，不會擲到神品


def test_two_templates_on_one_path_and_form_are_refused(tmp_path):
    src = Path(__file__).resolve().parents[2] / "content"
    root = tmp_path / "content"
    shutil.copytree(src, root)
    path = root / "traits.json"
    book = json.loads(path.read_text(encoding="utf-8"))
    twin = dict(book["god"][0], id="god_twin", name="雙生神品", tactic=dict(book["god"][0]["tactic"], name="雙生神品"))
    book["god"].append(twin)
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ContentError, match="一路一型"):
        load_content(root)
