import time
from pathlib import Path

import pytest

from tianxia.martial_arts import generate_from_name
from tianxia.world_state import WorldStateStore, _locked


@pytest.fixture
def store(tmp_path):
    return WorldStateStore(path=tmp_path / "world" / "state.json")


def test_read_missing_file_returns_empty_state(store):
    state = store.read()
    assert state.created_skills == {}
    assert state.companion_tag_counts == {}


def test_claim_skill_name_succeeds_once(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(art) is True
    assert store.is_skill_name_taken("裂石拳") is True


def test_claim_skill_name_fails_when_already_taken(store):
    art = generate_from_name("裂石拳", "武學", "裂石拳")
    store.claim_skill_name(art)
    same_name_again = generate_from_name("裂石拳", "武學", "裂石拳")
    assert store.claim_skill_name(same_name_again) is False


def test_claim_skill_name_persists_across_store_instances(tmp_path):
    path = tmp_path / "world" / "state.json"
    art = generate_from_name("驚鴻一劍", "武學", "驚鴻一劍")
    WorldStateStore(path=path).claim_skill_name(art)
    reopened = WorldStateStore(path=path)
    assert reopened.is_skill_name_taken("驚鴻一劍") is True


def test_record_companion_tag_accumulates_counts(store):
    store.record_companion_tag("dongzhuo", "真誠切磋")
    store.record_companion_tag("dongzhuo", "真誠切磋")
    store.record_companion_tag("dongzhuo", "強攻鋪墊")
    counts = store.read().companion_tag_counts["dongzhuo"]
    assert counts == {"真誠切磋": 2, "強攻鋪墊": 1}


def test_companion_drift_note_round_trips(store):
    assert store.get_companion_drift_note("dongzhuo") == ""
    store.set_companion_drift_note("dongzhuo", "漸露驕縱之色")
    assert store.get_companion_drift_note("dongzhuo") == "漸露驕縱之色"


def test_lock_is_reclaimed_after_stale_timeout(tmp_path):
    lock_dir = tmp_path / "stale.lock"
    lock_dir.mkdir()
    old = time.time() - 999
    import os
    os.utime(lock_dir, (old, old))
    # 鎖已經存在但夠舊，_locked 應該強制回收而不是等到逾時炸掉。
    with _locked(lock_dir):
        assert lock_dir.exists()
    assert not lock_dir.exists()


def test_lock_prevents_concurrent_mutation_from_corrupting_state(tmp_path):
    path = tmp_path / "world" / "state.json"
    store_a = WorldStateStore(path=path)
    store_b = WorldStateStore(path=path)
    for i in range(20):
        art = generate_from_name(f"武學{i}", "武學", f"武學{i}")
        (store_a if i % 2 == 0 else store_b).claim_skill_name(art)
    assert len(store_a.read().created_skills) == 20


# ── 江湖大事潤色（全服共用一次，還要改進第 3 點）──────────────────


def test_event_flavor_starts_empty(store):
    assert store.get_event_flavor("huangjin_80") == ""


def test_set_event_flavor_first_write_wins(store):
    store.set_event_flavor("huangjin_80", "城頭的旗幟已經換了顏色。")
    store.set_event_flavor("huangjin_80", "別的玩家搶先寫入的另一句話。")
    assert store.get_event_flavor("huangjin_80") == "城頭的旗幟已經換了顏色。"


# ── 傳國玉璽碎片（跨季，還要改進第 2 點）─────────────────────────


def test_record_jade_seal_fragment_numbers_in_order(store):
    first = store.record_jade_seal_fragment("強者", "黃巾之亂", "強者擊敗看守者，取得第一塊碎片。")
    second = store.record_jade_seal_fragment("弱者", "黃巾之亂", "弱者意外尋得第二塊碎片。")
    assert (first.number, second.number) == (1, 2)
    assert [f.finder for f in store.get_jade_seal_fragments()] == ["強者", "弱者"]


def test_record_jade_seal_fragment_stops_after_seven(store):
    for i in range(7):
        store.record_jade_seal_fragment(f"玩家{i}", "測試季", "找到了。")
    assert store.record_jade_seal_fragment("第八人", "測試季", "來晚了。") is None
    assert len(store.get_jade_seal_fragments()) == 7


def test_jade_seal_summary_before_and_after_a_fragment_is_found(store):
    assert "尚無人尋獲" in store.jade_seal_summary()
    store.record_jade_seal_fragment("強者", "黃巾之亂", "強者擊敗看守者，取得第一塊碎片。")
    summary = store.jade_seal_summary()
    assert "1/7" in summary and "強者" in summary and "黃巾之亂" in summary
