"""條款的核心接縫（tianxia/core/terms_base.py；帳號與客服第 206 批）：註冊與建角色查兩個勾選、建好帳號記版本。
terms 包在殼掛路由那一下 set_hook；核心只放掛鉤與純規則，不 import 包、不讀時鐘。"""
import pytest

from tianxia.core import terms_base as tb


class FakeHook:
    def __init__(self, version="v2", stale=False):
        self.v, self.stale, self.calls = version, stale, []

    def version(self):
        return self.v

    def record(self, account_key, version, source):
        if self.stale:
            raise ValueError("stale")
        self.calls.append((account_key, version, source))


@pytest.fixture(autouse=True)
def keep_hook():
    """hook 是模組全域（殼 import 時 terms 包登記）：每條測試結束放回原來那個，別的測試照樣讀得到。"""
    before = tb._HOOK
    yield
    tb.set_hook(before)


@pytest.fixture
def hook():
    h = FakeHook()
    tb.set_hook(h)
    return h


def test_terms_base_off_or_no_hook_lets_everything_through(content):
    tb.set_hook(None)
    assert tb.on(content) is False
    assert tb.register_problem(content, {}) is None
    assert tb.record(content, "ab", "v2") is False
    content.config.terms.enabled = True
    assert tb.on(content) is True
    assert tb.register_problem(content, {}) is None  # 開著但 terms 包沒掛（沒有 hook）：照舊，不擋
    assert tb.record(content, "ab", "v2") is False
    h = FakeHook()
    tb.set_hook(h)
    content.config.terms.enabled = False
    assert tb.register_problem(content, {}) is None  # 關著有 hook 也不查
    assert tb.record(content, "ab", "v2") is False and h.calls == []


def test_terms_base_needs_both_ticks_and_the_current_version(content, hook):
    content.config.terms.enabled = True
    bad = [
        {},
        {"age_ok": True, "terms_version": "v2"},
        {"terms_agree": True, "terms_version": "v2"},
        {"age_ok": True, "terms_agree": True, "terms_version": "v1"},
        {"age_ok": True, "terms_agree": True},
        {"age_ok": "", "terms_agree": "on", "terms_version": "v2"},
    ]
    for body in bad:
        got = tb.register_problem(content, body)
        assert got == tb.REGISTER_NEED, body
        assert "v2" not in got and "v1" not in got  # 三種情形同一句，不透露版本
    for yes in (True, "on", "true", "1"):
        assert tb.register_problem(content, {"age_ok": yes, "terms_agree": yes, "terms_version": "v2"}) is None


def test_terms_base_record_passes_the_ticked_version(content, hook):
    content.config.terms.enabled = True
    assert tb.record(content, "ab", "v2") is True
    assert hook.calls == [("ab", "v2", "register")]


def test_terms_base_record_swallows_stale(content, hook):
    content.config.terms.enabled = True
    hook.stale = True
    assert tb.record(content, "ab", "v1") is False  # 不丟例外、不 500：登入後同意層補問


def test_terms_base_record_swallows_a_side_file_write_failure(content):
    """旁檔寫不進去（鎖住、磁碟滿）也不往上丟：帳號已經開好了，回 False，登入後同意層補問。"""
    import sqlite3

    class Broken(FakeHook):
        def record(self, account_key, version, source):
            raise sqlite3.OperationalError("database is locked")

    content.config.terms.enabled = True
    tb.set_hook(Broken())
    assert tb.record(content, "ab", "v2") is False


class GateHook(FakeHook):
    """第 249 批：must(account_key) 照給的集合回答；broken 時丟例外（旁檔鎖住、壞掉）。"""

    def __init__(self, must=(), broken=None):
        super().__init__()
        self.musts, self.broken, self.asked = set(must), broken, []

    def must(self, account_key):
        self.asked.append(account_key)
        if self.broken is not None:
            raise self.broken
        return account_key in self.musts


def test_gate_problem_off_or_no_hook_lets_everything_through(content):
    """關著或沒掛 hook：第一行就回 None，連 must 都不問（條款關著行為不變；假人程式那一側 _HOOK 是 None）。"""
    tb.set_hook(None)
    content.config.terms.enabled = True
    assert tb.gate_problem(content, "ab") is None
    h = GateHook(must={"ab"})
    tb.set_hook(h)
    content.config.terms.enabled = False
    assert tb.gate_problem(content, "ab") is None and h.asked == []


def test_gate_problem_says_the_one_line_only_for_must(content):
    content.config.terms.enabled = True
    tb.set_hook(GateHook(must={"ab"}))
    assert tb.gate_problem(content, "ab") == tb.GATE_NEED
    assert tb.gate_problem(content, "cd") is None
    assert "重新整理" in tb.GATE_NEED  # 網頁不會自己重問，句子要叫他重新整理


def test_gate_problem_lets_through_and_logs_when_the_side_file_breaks(content, caplog):
    """旁檔鎖住、壞掉，或舊 hook 沒有 must：放行（網頁那一層照樣問），記一行 log，不丟例外。"""
    import logging
    import sqlite3

    content.config.terms.enabled = True
    tb.set_hook(GateHook(must={"ab"}, broken=sqlite3.OperationalError("database is locked")))
    with caplog.at_level(logging.ERROR, logger=tb.__name__):
        assert tb.gate_problem(content, "ab") is None
    assert any("gate check failed" in r.getMessage() for r in caplog.records)
    tb.set_hook(FakeHook())  # 第 206 批的舊 hook：沒有 must → AttributeError 一樣吞
    assert tb.gate_problem(content, "ab") is None
