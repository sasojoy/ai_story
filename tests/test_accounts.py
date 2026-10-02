import json

import pytest

from tianxia.accounts import AccountError, AccountStore


class Clock:
    def __init__(self, now: float = 1_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return AccountStore(tmp_path / "accounts" / "accounts.json", clock=clock)


def test_register_stores_a_salted_hash_not_the_password(store):
    store.register("Rayal_01", "secret-pw")
    text = store.path.read_text(encoding="utf-8")
    assert "secret-pw" not in text
    data = json.loads(text)
    record = data["accounts"]["rayal_01"]
    assert data["version"] == 1
    assert record["login"] == "Rayal_01" and record["character"] is None and record["created"] == 1_000.0
    assert len(bytes.fromhex(record["salt"])) == 16 and len(bytes.fromhex(record["hash"])) == 32


def test_the_same_password_gets_a_different_salt(store):
    store.register("alpha", "same-pw")
    store.register("beta", "same-pw")
    a, b = store.get("alpha"), store.get("beta")
    assert a.salt != b.salt and a.hash != b.hash


@pytest.mark.parametrize("login", ["ab", "a" * 21, "有中文", "bad name", "dash-no", "", None])
def test_the_login_format_is_checked(store, login):
    with pytest.raises(AccountError, match="帳號只能用英文字母、數字、底線，3～20 字。"):
        store.register(login, "secret-pw")


def test_the_password_length_is_checked(store):
    with pytest.raises(AccountError, match="密碼至少 6 字。"):
        store.register("alpha", "12345")
    with pytest.raises(AccountError, match="密碼最多 128 字。"):
        store.register("alpha", "x" * 129)
    assert store.get("alpha") is None


def test_logins_are_case_insensitive_and_unique(store):
    store.register("Rayal", "secret-pw")
    with pytest.raises(AccountError, match="這個帳號已有人使用。"):
        store.register("rAYAL", "other-pw")
    assert store.authenticate("RAYAL", "secret-pw").login == "Rayal"


def test_an_unknown_account_and_a_wrong_password_read_the_same(store):
    store.register("alpha", "secret-pw")
    with pytest.raises(AccountError) as wrong:
        store.authenticate("alpha", "nope-nope")
    with pytest.raises(AccountError) as unknown:
        store.authenticate("nobody", "secret-pw")
    assert str(wrong.value) == str(unknown.value) == "帳號或密碼不對。"


def test_five_failures_in_ten_minutes_lock_the_login(store, clock):
    store.register("alpha", "secret-pw")
    for _ in range(5):
        with pytest.raises(AccountError, match="帳號或密碼不對。"):
            store.authenticate("alpha", "nope-nope")
        clock.now += 10
    with pytest.raises(AccountError, match="嘗試太多次，請 10 分鐘後再試。"):
        store.authenticate("alpha", "secret-pw")  # 對的密碼也先不收
    clock.now += 600
    assert store.authenticate("alpha", "secret-pw").login == "alpha"


def test_unknown_accounts_are_throttled_too(store):
    for _ in range(5):
        with pytest.raises(AccountError, match="帳號或密碼不對。"):
            store.authenticate("ghost", "whatever1")
    with pytest.raises(AccountError, match="嘗試太多次"):
        store.authenticate("ghost", "whatever1")


def test_a_success_clears_the_failures(store):
    store.register("alpha", "secret-pw")
    for _ in range(4):
        with pytest.raises(AccountError):
            store.authenticate("alpha", "nope-nope")
    store.authenticate("alpha", "secret-pw")
    for _ in range(4):
        with pytest.raises(AccountError, match="帳號或密碼不對。"):
            store.authenticate("alpha", "nope-nope")


def test_stores_built_on_the_same_failures_dict_share_the_count(tmp_path, clock):
    failures: dict[str, list[float]] = {}
    path = tmp_path / "accounts.json"
    for _ in range(5):
        with pytest.raises(AccountError):
            AccountStore(path, clock=clock, failures=failures).authenticate("x_y", "whatever1")
    with pytest.raises(AccountError, match="嘗試太多次"):
        AccountStore(path, clock=clock, failures=failures).authenticate("x_y", "whatever1")


def test_bind_a_character_and_find_by_login_or_name(store):
    store.register("alpha", "secret-pw")
    store.bind_character("ALPHA", "沈青衫")
    assert store.get("alpha").character == "沈青衫"
    assert store.owner_of("沈青衫") == "alpha"
    assert store.owner_of("無名氏") is None
    assert store.find("Alpha") == "alpha"
    assert store.find("沈青衫") == "alpha"
    assert store.find("沒這個人") is None
    assert store.find("  ") is None


def test_a_name_belongs_to_one_account_and_an_account_to_one_name(store):
    store.register("alpha", "secret-pw")
    store.register("beta", "secret-pw")
    store.bind_character("alpha", "沈青衫")
    store.bind_character("alpha", "沈青衫")  # 同一個名號再綁一次沒關係
    with pytest.raises(AccountError, match="這個名號已有人使用。"):
        store.bind_character("beta", "沈青衫")
    with pytest.raises(AccountError, match="這個帳號已經有角色了。"):
        store.bind_character("alpha", "柳如煙")


def test_change_password_needs_the_old_one(store):
    store.register("alpha", "secret-pw")
    with pytest.raises(AccountError, match="舊密碼不對。"):
        store.change_password("alpha", "wrong-pw", "new-secret")
    with pytest.raises(AccountError, match="密碼至少 6 字。"):
        store.change_password("alpha", "secret-pw", "123")
    store.change_password("alpha", "secret-pw", "new-secret")
    assert store.authenticate("alpha", "new-secret").login == "alpha"
    with pytest.raises(AccountError, match="帳號或密碼不對。"):
        store.authenticate("alpha", "secret-pw")


def test_set_password_needs_no_old_one_and_lifts_the_lock(store):
    store.register("alpha", "secret-pw")
    for _ in range(5):
        with pytest.raises(AccountError):
            store.authenticate("alpha", "nope-nope")
    store.set_password("alpha", "temp-pass")
    assert store.authenticate("alpha", "temp-pass").login == "alpha"


def test_a_missing_file_is_an_empty_store(store):
    assert store.get("alpha") is None
    assert store.find("alpha") is None
    assert not store.path.exists()
