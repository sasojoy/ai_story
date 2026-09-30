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
