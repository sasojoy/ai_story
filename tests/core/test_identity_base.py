"""帳號綁定的核心那一半（tianxia/core/identity_base.py；帳號與客服第 201 批）：正規化、遮罩、金鑰、phone_ok、名號擋不擋。"""
import json

import pytest

from tianxia.core import identity_base as ib


@pytest.fixture
def keyed(tmp_path, monkeypatch):
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": "k" * 32}), encoding="utf-8")
    monkeypatch.setattr(ib, "KEY_FILE", path)
    return path


@pytest.mark.parametrize("text", [
    "0912345678", "0912-345-678", "0912 345 678", "(0912)345678", "+886912345678", "+886 912 345 678",
    "+886-912-345-678", "０９１２３４５６７８", "　0912345678　",
])
def test_identity_base_normalize_phone_taiwan_forms(text):
    assert ib.normalize_phone(text) == "+886912345678"


@pytest.mark.parametrize("text", ["", None, "02-2345-6789", "091234567", "09123456789", "+85291234567", "8869123456789", "abc"])
def test_identity_base_normalize_phone_rejects(text):
    assert ib.normalize_phone(text) is None


def test_identity_base_normalize_and_mask():
    assert ib.normalize_email("R.a.Y+game@Gmail.com") == "ray@gmail.com"
    assert ib.normalize_email("r.ay+x@googlemail.com") == "ray@googlemail.com"
    assert ib.normalize_email(" Ray.Lin+x@Example.COM ") == "ray.lin@example.com"
    for bad in ("", None, "ray", "a@b", "@gmail.com", "+x@gmail.com", "a@@b.com", "a b@c.com"):
        assert ib.normalize_email(bad) is None, bad
    assert ib.mask_phone("+886912345678") == "09*****678"
    assert ib.mask_email("ray@gmail.com") == "r*@gmail.com"
    assert ib.mask_email("raymond@gmail.com") == "r*@gmail.com"  # 看不出幾個字
    assert "12345" not in ib.mask_phone("+886912345678")


def test_identity_base_key_and_hmac(tmp_path, keyed):
    assert ib.read_key() == b"k" * 32
    assert ib.read_key(tmp_path / "nope.json") is None
    for text in ("not json", json.dumps([1]), json.dumps({"key": "short"}), json.dumps({"key": 5})):
        bad = tmp_path / "bad.json"
        bad.write_text(text, encoding="utf-8")
        assert ib.read_key(bad) is None, text
    a = ib.subject_hmac(b"k" * 32, "phone", "+886912345678")
    assert a == ib.subject_hmac(b"k" * 32, "phone", "+886912345678")
    assert a != ib.subject_hmac(b"k" * 32, "email", "+886912345678")
    assert a != ib.subject_hmac(b"j" * 32, "phone", "+886912345678")
    assert "912345678" not in a


def test_identity_base_on_needs_switch_and_key(content, tmp_path, monkeypatch, keyed):
    assert ib.on(content) is False  # 預設關
    content.config.identity.enabled = True
    assert ib.on(content) is True
    monkeypatch.setattr(ib, "KEY_FILE", tmp_path / "missing.json")
    assert ib.on(content) is False


def _bind(game, provider=None):
    from tianxia.accounts import AccountStore

    store = AccountStore(game.world.db)
    store.register("ray1", "secret1")
    store.bind_character("ray1", game.state.player.name)
    if provider:  # 直接寫一列（綁定的路第 204 批才有）
        with game.world.db.transaction() as conn:
            conn.execute(
                "INSERT INTO logins (provider, subject, account_id, display) "
                "SELECT ?, ?, account_id, '09*****678' FROM logins WHERE provider = 'password' AND subject = 'ray1'",
                (provider, "h" * 64),
            )


def test_phone_ok_order(game, keyed):
    """第 205 批照設計 4.5 的順序：關著、phone_gate 關、不在名單、假人回真；不是假人又查不到帳號回假；其餘看有沒有 phone 列。"""
    from tianxia.state import BotProfile

    cfg = game.content.config.identity
    assert ib.phone_ok(game, "raid") is True  # 關著
    cfg.enabled = True
    assert ib.phone_ok(game, "raid") is True  # phone_gate 關
    cfg.phone_gate = True
    assert ib.phone_ok(game, "raid") is False  # 不是假人、查不到帳號
    assert ib.phone_ok(game, "not_listed") is True  # 不在名單
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.phone_ok(game, "raid") is True  # 假人一律過（假人沒有帳號）
    game.state.player.bot = None
    _bind(game)
    assert ib.phone_ok(game, "raid") is False  # 有帳號、沒綁手機
    assert ib.phone_ok(game, "not_listed") is True


def test_phone_ok_true_when_identity_is_off_even_with_phone_gate_on(game, keyed, tmp_path, monkeypatch):
    """緊急關掉 identity（enabled 關、或金鑰讀不到）時 phone_gate 開著也一律過：九個入口不能被關著的包擋住（L 波審查）。"""
    cfg = game.content.config.identity
    cfg.phone_gate = True
    _bind(game)  # 有帳號、沒綁手機：identity 開著的話會擋
    assert ib.phone_ok(game, "raid") is True  # enabled 關
    cfg.enabled = True
    assert ib.phone_ok(game, "raid") is False  # 對照：開著就擋
    monkeypatch.setattr(ib, "KEY_FILE", tmp_path / "missing.json")
    assert ib.phone_ok(game, "raid") is True  # 金鑰讀不到＝沒開


def test_phone_ok_true_once_the_phone_is_bound(game, keyed):
    cfg = game.content.config.identity
    cfg.enabled = True
    cfg.phone_gate = True
    _bind(game, "phone")
    assert ib.phone_ok(game, "raid") is True


def test_phone_subject_only_when_gated_and_bound(game, keyed):
    """phone_subject：走到「有 phone 列」才回那一列的 subject；閘關、不在名單、假人、沒綁都 None。"""
    from tianxia.state import BotProfile

    cfg = game.content.config.identity
    cfg.enabled = True
    _bind(game, "phone")
    assert ib.phone_subject(game, "mall_grant") is None  # phone_gate 關
    cfg.phone_gate = True
    assert ib.phone_subject(game, "mall_grant") == "h" * 64
    assert ib.phone_subject(game, "not_listed") is None
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.phone_subject(game, "mall_grant") is None
    game.state.player.bot = None
    with game.world.db.transaction() as conn:
        conn.execute("DELETE FROM logins WHERE provider = 'phone'")
    assert ib.phone_subject(game, "mall_grant") is None  # 沒綁
    assert isinstance(ib.PHONE_NEEDED, str) and ib.PHONE_NEEDED


def test_account_key_for_reads_logins(game):
    """第 203 批：身分綁在哪個帳號——有密碼的回小寫帳號，沒有的回 id:<n>，查無回 None。"""
    from tianxia.accounts import AccountStore

    db = game.world.db
    assert ib.account_key_for(db, "phone", "h" * 64) is None
    _bind(game, "phone")
    assert ib.account_key_for(db, "phone", "h" * 64) == "ray1"
    key = AccountStore(db).create_without_password("email", "e" * 64, "r*@gmail.com")
    assert ib.account_key_for(db, "email", "e" * 64) == key and key.startswith("id:")
    assert ib.account_key_for(db, "email", "h" * 64) is None


def test_account_key_for_is_login_key(game, monkeypatch):
    """第 204 批（K 波審查）：併成一份，就是 AccountStore.login_key。"""
    from tianxia.accounts import AccountStore

    seen = []
    monkeypatch.setattr(AccountStore, "login_key", lambda self, provider, subject: seen.append((provider, subject)) or "k")
    assert ib.account_key_for(game.world.db, "phone", "h" * 64) == "k" and seen == [("phone", "h" * 64)]


def test_staff_session_ok_off_uses_session_created(game, content):
    """第 204 批：identity 關著時看 session 建立的時間（staff_hours 內）；查不到回假。"""
    from tianxia.accounts import AccountStore, SessionStore

    db = game.world.db
    AccountStore(db).register("kefu_01", "secret-pw")
    token = SessionStore(db, clock=lambda: 1000.0).create("kefu_01")
    clocked = SessionStore(db, clock=lambda: 1000.0)
    assert clocked.created_at(token) == 1000.0 and clocked.created_at("nope") is None
    assert content.config.identity.enabled is False
    assert ib.staff_session_ok(db, content, token, 1000.0 + 6 * 3600) is True
    assert ib.staff_session_ok(db, content, token, 1000.0 + 6 * 3600 + 1) is False
    assert ib.staff_session_ok(db, content, "nope", 1000.0) is False
    assert ib.staff_session_ok(db, content, None, 1000.0) is False


def test_session_auth_roundtrip_and_last_checked(tmp_path):
    side = tmp_path / "g-identity.sqlite"
    assert ib.session_auth("t", side) is None
    ib.record_session("t", "phone", 100.0, side)
    assert ib.session_auth("t", side) == {"method": "phone", "at": 100.0, "verified": None, "verified_by": None}
    assert ib.last_checked(ib.session_auth("t", side)) == 100.0
    assert ib.record_reauth("t", "password", 500.0, side) is True
    assert ib.session_auth("t", side)["method"] == "phone" and ib.last_checked(ib.session_auth("t", side)) == 500.0
    assert ib.side_file(tmp_path / "g.db") == side


def test_blocked_name_only_when_on(content, keyed):
    names = ("客服", "GM", "gm", "id:3", "ID:3", "官方", "管理員")
    assert not any(ib.blocked_name(n, content) for n in names)
    content.config.identity.enabled = True
    assert all(ib.blocked_name(n, content) for n in names)
    assert not ib.blocked_name("沈浪", content)
    assert not ib.blocked_name("客服甲", content)


# ── 第 207 批：管理者的 session、名單上的帳號、12 字 ──


def test_admin_session_ok_off_is_always_true(game, content, tmp_path, monkeypatch):
    """關著一律回真（管理者行為位元組一樣）：不看 session 建立的時間（不走 staff_session_ok 關著那一支），也不碰旁檔。"""
    from tianxia.accounts import AccountStore, SessionStore

    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    db = game.world.db
    AccountStore(db).register("boss_01", "secret-pw")
    token = SessionStore(db, clock=lambda: 1000.0).create("boss_01")
    assert content.config.identity.enabled is False

    def never():
        raise AssertionError("關著不讀時鐘")

    for t in (None, "nope", token):
        assert ib.admin_session_ok(content, t, never) is True
    assert not ib.side_file().exists()


def test_admin_session_ok_on_needs_password_within_hours(game, content, keyed, tmp_path, monkeypatch):
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "g.db"))
    content.config.identity.enabled = True
    db = game.world.db
    hours = content.config.identity.staff_hours * 3600
    ib.record_session("pw", "password", 1000.0)
    assert ib.admin_session_ok(content, "pw", lambda: 1000.0 + hours) is True
    assert ib.admin_session_ok(content, "pw", lambda: 1000.0 + hours + 1) is False
    ib.record_reauth("pw", "password", 1000.0 + hours + 1)
    assert ib.admin_session_ok(content, "pw", lambda: 1000.0 + hours + 2) is True  # 重驗過回來
    for method in ("phone", "email", "line", "google"):
        ib.record_session(method, method, 1000.0)
        assert ib.admin_session_ok(content, method, lambda: 1000.0) is False
    assert ib.admin_session_ok(content, None, lambda: 1000.0) is False
    assert ib.admin_session_ok(content, "nope", lambda: 1000.0) is False


def test_listed_matches_admins_and_support(content, monkeypatch):
    monkeypatch.delenv(ib.SUPPORT_ENV, raising=False)
    content.config.admins = ["Rayal", "段青山"]
    content.config.support.staff = ["kefu_01", "77"]
    assert ib.listed(content, character="段青山") is True
    assert ib.listed(content, login="RAYAL") is True  # 帳號名照名號的寫法比、不分大小寫（註冊時還沒角色）
    assert ib.listed(content, login="KeFu_01") is True
    assert ib.listed(content, login="someone", account_id=77) is True
    assert ib.listed(content, login="77") is False  # 全是數字的一筆只當 id（同 support_staff）
    assert ib.listed(content, login="someone", character="沈浪", account_id=5) is False
    assert ib.listed(content) is False


def test_support_bot_token_reads_only_a_long_token(monkeypatch, tmp_path):
    """客服自動受理第 216 批（設計第八節）：.local/support.json 只讀 bot_token 一鍵；沒檔、少於 32 字、壞 json、不是字串、不是物件一律 None；
    照修改時間重讀。"""
    import os

    from tianxia import content as content_module

    monkeypatch.setattr(content_module, "LOCAL_DIR", tmp_path)
    ib._support_bot_cache.update(path=None, mtime=None, token=None)
    path = tmp_path / ib.SUPPORT_BOT_FILE
    assert ib.support_bot_file() == path
    assert ib.support_bot_token() is None  # 沒檔

    def write(text: str, bump: int) -> None:
        path.write_text(text, encoding="utf-8")
        st = path.stat()
        os.utime(path, (st.st_atime, st.st_mtime + bump))

    write(json.dumps({"bot_token": "x" * 31}), 1)
    assert ib.support_bot_token() is None  # 短
    write("{not json", 2)
    assert ib.support_bot_token() is None  # 壞 json
    write(json.dumps({"bot_token": 12345678901234567890123456789012345}), 3)
    assert ib.support_bot_token() is None  # 不是字串
    write(json.dumps(["x" * 40]), 4)
    assert ib.support_bot_token() is None  # 不是物件
    path.write_bytes(b"\xff\xfe\x00bad")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    assert ib.support_bot_token() is None  # 解碼錯
    write(json.dumps({"bot_token": "a" * 32, "other": "ignored"}), 6)
    assert ib.support_bot_token() == "a" * 32
    write(json.dumps({"bot_token": "b" * 40}), 7)
    assert ib.support_bot_token() == "b" * 40  # mtime 變了就重讀
    path.unlink()
    assert ib.support_bot_token() is None


def test_check_password_strict_needs_12():
    from tianxia import accounts

    assert accounts.check_password("12345678") == "12345678"  # strict 假（identity 關著）：一個字不變
    for short in ("", "12345", "12345678901"):
        with pytest.raises(accounts.AccountError) as got:
            accounts.check_password(short, strict=True)
        assert str(got.value) == accounts.STRICT_SHORT_PASSWORD
    assert accounts.check_password("123456789012", strict=True) == "123456789012"
    with pytest.raises(accounts.AccountError) as got:
        accounts.check_password("x" * (accounts.PASSWORD_MAX + 1), strict=True)
    assert str(got.value) == accounts.LONG_PASSWORD
    assert accounts.STRICT_SHORT_PASSWORD == "密碼至少 12 字。"  # 第 209 批：全體同一句，不帶「這個帳號」



def test_notify_without_notifier_is_zero(monkeypatch):
    """第 209 批：admin 包經核心寄通知；identity 包沒登記（沒掛路由）回 0、不丟例外。"""
    import tianxia.core.identity_base as ib

    monkeypatch.setattr(ib, "_NOTIFIER", None)
    assert ib.notify(1, "x") == 0
    seen = []
    ib.set_notifier(lambda account_id, text: seen.append((account_id, text)) or 2)
    assert ib.notify(5, "y") == 2 and seen == [(5, "y")]
    assert ib.NOTICE_ADMIN_RESET == "管理者幫這個帳號重設了密碼。不是你要求的話，請馬上寫信給客服。"

def test_account_store_passes_strict(game):
    from tianxia import accounts

    store = accounts.AccountStore(game.world.db)
    with pytest.raises(accounts.AccountError):
        store.register("boss_01", "secret-pw", strict=True)
    store.register("boss_01", "secret-pw")
    with pytest.raises(accounts.AccountError):
        store.change_password("boss_01", "secret-pw", "other-pw-1", strict=True)
    with pytest.raises(accounts.AccountError):
        store.set_password("boss_01", "other-pw-1", strict=True)
    store.change_password("boss_01", "secret-pw", "a-long-password", strict=True)
    store.set_password("boss_01", "another-long-pw", strict=True)
    assert store.authenticate("boss_01", "another-long-pw") is not None


# ── 扣押期（帳號與客服第 208 批；設計 4.3、4.4、6.4）：hold_reason、record_admin_reset、reset_held ──

H_NOW = 2_000_000_000.0


def _held_game(game, keyed, now=H_NOW):
    """identity 開著、名號綁了帳號 ray1、Game.now＝now；回 accounts.id。"""
    from tianxia.accounts import AccountStore

    game.content.config.identity.enabled = True
    _bind(game)
    game.now = now
    return AccountStore(game.world.db).account_id("ray1")


def _side_exec(sql, args=()):
    import sqlite3

    path = ib.side_file()
    ib.ensure_schema(path, "hold", ib.HOLD_TABLES, ib.META_COLUMNS)
    with sqlite3.connect(path) as conn:
        conn.execute(sql, args)


def test_hold_reason_off_is_none(game, keyed, tmp_path, monkeypatch):
    aid = _held_game(game, keyed)
    _side_exec("INSERT INTO holds (account_id, until) VALUES (?, ?)", (aid, H_NOW + 100))
    assert ib.hold_reason(game, "mall_buy") is not None  # 對照：開著就擋
    game.content.config.identity.enabled = False
    assert ib.hold_reason(game, "mall_buy") is None
    game.content.config.identity.enabled = True
    monkeypatch.setattr(ib, "KEY_FILE", tmp_path / "missing.json")
    assert ib.hold_reason(game, "mall_buy") is None  # 金鑰讀不到＝沒開


def test_hold_reason_bot_and_no_account_none(game, keyed):
    """假人與沒帳號的名號同一個樣子（都 None）：看不出誰是假人；扣押是帳號的狀態，沒帳號不擋（跟 phone_ok 不同）。"""
    from tianxia.state import BotProfile

    game.content.config.identity.enabled = True
    game.now = H_NOW
    _side_exec("INSERT INTO holds (account_id, until) VALUES (1, ?)", (H_NOW + 100,))
    assert ib.hold_reason(game, "mall_buy") is None  # 沒帳號
    game.state.player.bot = BotProfile(personality="普通", seed=1)
    assert ib.hold_reason(game, "mall_buy") is None  # 假人


def test_hold_reason_new_binding_72h(game, keyed):
    aid = _held_game(game, keyed)
    hours = game.content.config.identity.new_binding_hours
    _side_exec("INSERT INTO bindings_meta (account_id, provider, subject_hmac, verified_at, bound_at) VALUES (?, 'password', 'x', 0, NULL)",
               (aid,))
    assert ib.hold_reason(game, "gift") is None  # bound_at 是 NULL：開帳號那一種，不算新綁
    _side_exec("INSERT INTO bindings_meta (account_id, provider, subject_hmac, verified_at, bound_at) VALUES (?, 'phone', 'h', ?, ?)",
               (aid, H_NOW - 71 * 3600, H_NOW - 71 * 3600))
    assert ib.hold_reason(game, "gift") == ib.HOLD_NEW.format(hours=hours)
    game.now = H_NOW + 2 * 3600  # 綁了 73 小時
    assert ib.hold_reason(game, "gift") is None


def test_hold_reason_stale_hold(game, keyed):
    aid = _held_game(game, keyed)
    days = game.content.config.identity.stale_hold_days
    _side_exec("INSERT INTO holds (account_id, until) VALUES (?, ?)", (aid, H_NOW + 10))
    assert ib.hold_reason(game, "looks_market") == ib.HOLD_STALE.format(days=days)
    game.now = H_NOW + 10
    assert ib.hold_reason(game, "looks_market") is None


def test_hold_reason_admin_reset(game, keyed):
    aid = _held_game(game, keyed)
    hours = game.content.config.identity.reset_hold_hours
    assert hours == 72
    ib.record_admin_reset(aid, H_NOW - 3600, hours, "x")
    _side_exec("INSERT INTO holds (account_id, until) VALUES (?, ?)", (aid, H_NOW + 10))
    assert ib.hold_reason(game, "mall_buy") == ib.HOLD_RESET.format(hours=hours)  # 重設排在只剩過期一種之前
    assert ib.reset_held(aid, H_NOW) is True and ib.reset_held(aid, H_NOW + 71 * 3600) is False
    assert ib.reset_held(aid + 1, H_NOW) is False


def test_hold_reason_unknown_key(game, keyed):
    aid = _held_game(game, keyed)
    _side_exec("INSERT INTO holds (account_id, until) VALUES (?, ?)", (aid, H_NOW + 100))
    assert ib.hold_reason(game, "raid") is None
    assert set(ib.HOLD_KEYS) == {"mall_buy", "gift", "looks_market"}


def test_hold_reason_no_side_file_does_not_create(game, keyed):
    _held_game(game, keyed)
    assert not ib.side_file().exists()
    assert ib.hold_reason(game, "mall_buy") is None
    assert not ib.side_file().exists()
    assert ib.reset_held(1, H_NOW) is False and not ib.side_file().exists()


def test_record_admin_reset_writes_hold_and_note(tmp_path):
    import sqlite3

    side = tmp_path / "g-identity.sqlite"
    ib.record_admin_reset(7, 1000.0, 72, "管理者重設了", side)
    ib.record_admin_reset(7, 500.0, 72, "第二次（較早）", side)
    with sqlite3.connect(side) as conn:
        assert conn.execute("SELECT until FROM reset_holds WHERE account_id = 7").fetchone()[0] == 1000.0 + 72 * 3600  # 取晚的
        notes = conn.execute("SELECT account_id, text, at, state FROM account_notes ORDER BY id").fetchall()
    assert notes == [(7, "管理者重設了", 1000.0, 0), (7, "第二次（較早）", 500.0, 0)]
    assert ib.reset_held(7, 1000.0 + 72 * 3600 - 1, side) is True
    assert "{hours}" in ib.NOTE_ADMIN_RESET


def test_store_ddl_matches_core():
    """holds、account_notes、bindings_meta、reset_holds 的 DDL 只有核心一份：identity 包的 store.TABLES 用的就是那幾個常數。"""
    from tianxia.features.identity import store as idstore

    for sql in ib.HOLD_TABLES:
        assert sql in idstore.TABLES
    for col in ib.META_COLUMNS:
        assert col in idstore.ADDED_COLUMNS
