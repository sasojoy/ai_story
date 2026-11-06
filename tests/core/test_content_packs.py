"""內容照包分（全部拆包第 62 批；計畫 docs/superpowers/plans/2026-11-06-內容照包分-第62批.md）：各包宣告的內容檔住在
tianxia/features/<包>/content/，content.py 只有真實的根才去包裡找。load_content 裡一堆 .exists() 判斷式，檔案搬丟了不會紅、只會靜靜變成空的，
所以這裡釘住四件事：檔在該在的地方、事件的先後、其他的根照舊攤平、兩種放錯當場報錯。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import FIXTURE, real_content
from tianxia import content as content_mod
from tianxia.content import ContentError, content_path, load_content, real_event_files, real_files
from tianxia.core import features, registry

REAL_ROOT = content_mod.REAL_ROOT
HOME = Path(content_mod.__file__).resolve().parent / "features"


def test_every_declared_file_is_in_its_pack_and_not_left_in_content():
    packs = features.pack_content()
    assert packs
    for rel, path in packs.items():
        assert path.is_file(), rel
        assert not (REAL_ROOT / rel).exists(), f"{rel} 兩處都有"


def test_every_json_in_a_pack_content_folder_is_declared():
    """不多不少：包裡多一個沒宣告的檔，content.py 讀不到、也不會報錯。"""
    assert set(HOME.glob("*/content/**/*.json")) == set(features.pack_content().values())


def test_real_files_cover_both_places_by_their_old_relative_path():
    files = real_files()
    assert list(files) == sorted(files)
    assert files["sects.json"] == HOME / "faction" / "content" / "sects.json"
    assert files["events/sects.json"] == HOME / "faction" / "content" / "events" / "sects.json"  # 用相對路徑認、不用檔名認
    assert files["events/opening.json"] == HOME / "guide" / "content" / "events" / "opening.json"  # 同一包的兩個檔：開局的事件池與下面的開局第一分鐘
    assert files["opening.json"] == HOME / "guide" / "content" / "opening.json"
    assert files["profiles/week7.json"].is_file() and files["config.json"] == REAL_ROOT / "config.json"
    assert content_path("mall.json") == HOME / "mall" / "content" / "mall.json"
    assert content_path("config.json") == REAL_ROOT / "config.json"


def test_event_files_sort_by_name_across_packs():
    """content.events 的先後就是事件池抽籤的先後：照檔名排、跨包穿插，跟全放在一個資料夾時一樣。"""
    files = real_event_files()
    names = [path.name for path in files]
    assert names == sorted(names) and len(set(names)) == len(names)
    at = names.index
    assert at("explore_youzhou.json") < at("foreshadow_fragments.json") < at("foreshadow_prep.json") < at("general.json")
    assert files[at("explore_youzhou.json")].parent == HOME / "explore" / "content" / "events"
    assert files[at("foreshadow_prep.json")].parent == HOME / "military" / "content" / "events"
    assert files[at("general.json")].parent == REAL_ROOT / "events"
    in_order = [raw["id"] for path in files for raw in json.loads(path.read_text(encoding="utf-8"))]
    assert list(real_content().events) == in_order


def test_other_roots_stay_flat_and_never_fall_back_to_the_packs(tmp_path):
    """測試內容靠「沒有這個檔就是空的」（沒有 mall.json 就沒有商品）：掉回包裡就變了。"""
    root = tmp_path / "content"
    shutil.copytree(FIXTURE, root)
    assert not (root / "mall.json").exists()
    assert load_content(root).mall == {}


def test_a_file_in_both_places_is_refused(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(content_mod, "REAL_ROOT", root)
    (root / "mall.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ContentError, match="mall.json 兩處都有"):
        load_content(root)


def test_a_declared_file_that_is_gone_is_refused(tmp_path, monkeypatch):
    """不報的話 .exists() 判成空的：檔案搬丟了全部照樣綠。"""
    root = tmp_path.resolve()
    monkeypatch.setattr(content_mod, "REAL_ROOT", root)
    monkeypatch.setattr(features, "pack_content", lambda: {"gone.json": root / "pack" / "gone.json"})
    with pytest.raises(ContentError, match="gone.json"):
        load_content(root)


def test_two_packs_cannot_declare_the_same_file(monkeypatch):
    class One:
        name, content = "one", ("twice.json",)

    class Two:
        name, content = "two", ("twice.json",)

    monkeypatch.setattr(registry, "DECLARED", (One, Two))
    with pytest.raises(ContentError, match="twice.json"):
        features.pack_content()


def test_swapping_the_feature_list_does_not_move_the_content(monkeypatch):
    """契約測試把 FEATURES 換成假的包：內容母本可能正好在這時候建，內容的位置不能跟著換（registry.DECLARED 的理由）。"""
    before = features.pack_content()
    monkeypatch.setattr(registry, "FEATURES", [])
    assert features.pack_content() == before
