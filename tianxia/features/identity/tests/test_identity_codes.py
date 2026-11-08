"""驗證碼的純規則與寄送介面（features/identity/codes.py、senders.py；帳號與客服第 203 批，設計 4.2、4.6、4.7）。
路由那一側在 test_identity_code_routes.py。時間一律傳入；寄送與 Turnstile 一律假的，不打網路。"""
from __future__ import annotations

import io
import json
import re
import sqlite3
from pathlib import Path

import pytest

from tianxia.core import identity_base
from tianxia.core.tuning.identity import IdentityTuning
from tianxia.features.identity import codes, senders
from tianxia.features.identity import store as idstore

KEY = b"k" * 32
T0 = 1_800_000_000.0
PHONE = "0912345678"
MAIL = "Ray.Lin+x@gmail.com"


@pytest.fixture
def kit(tmp_path):
    fakes = senders.Senders(senders.FakeSms(), senders.FakeMail(), senders.FakeTurnstile())
    s = idstore.IdentityStore(tmp_path / "g-identity.sqlite")
    cfg = IdentityTuning(enabled=True, ways=["email", "phone"])
    bound: set[str] = set()

    def send(channel="phone", to=PHONE, *, now=T0, token="ok", ip="203.0.113.5", dev=None, cfg=cfg):
        return codes.send(
            cfg=cfg, key=KEY, store=s, senders=fakes, channel=channel, to=to, token=token, ip=ip, hostname="example.com",
            dev_hash=dev, is_bound=lambda subj: subj in bound, now=now,
        )

    class Kit:
        pass

    k = Kit()
    k.store, k.cfg, k.fakes, k.bound, k.send, k.path = s, cfg, fakes, bound, send, s.path
    k.subj = lambda channel="phone", to=PHONE: identity_base.subject_hmac(KEY, channel, codes.normalize(channel, to)[0])
    return k


def _last_code(k, channel="phone") -> str:
    box = k.fakes.sms.outbox if channel == "phone" else k.fakes.mail.outbox
    return re.search(r"\d{6}", box[-1][1]).group(0)


def test_ip_buckets_v4_and_v6():
    assert codes.ip_buckets("203.0.113.5") == ["v4:203.0.113.5"]
    assert codes.ip_buckets("2001:db8:1:2:aaaa::1") == ["v6/64:2001:db8:1:2::", "v6/48:2001:db8:1::"]
    assert codes.ip_buckets("::ffff:203.0.113.5") == ["v4:203.0.113.5"]
    assert codes.ip_buckets("") == ["raw:"]


def test_pool_of_and_new_code():
    assert codes.pool_of("login", True) == "login" and codes.pool_of("login", False) == "anon"
    assert codes.pool_of("bind", False) == "bind"
    assert codes.new_code(lambda n: 42) == "000042" and codes.new_code(lambda n: n - 1) == "999999"
    assert re.fullmatch(r"\d{6}", codes.new_code())
    assert codes.code_hmac(KEY, "c1", "123456") != codes.code_hmac(KEY, "c2", "123456")


def test_send_normalizes_and_rejects_non_taiwan(kit):
    for channel, to, want in (("phone", "+1 415 555 0100", codes.BAD_PHONE), ("phone", "02-2345-6789", codes.BAD_PHONE),
                              ("email", "not-a-mail", codes.BAD_EMAIL)):
        status, body, cid = kit.send(channel, to)
        assert (status, body, cid) == (400, {"error": want}, None)
    assert kit.fakes.sms.outbox == [] and kit.fakes.mail.outbox == []
    with sqlite3.connect(kit.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM counters").fetchone()[0] == 0


def test_turnstile_checked_server_side(kit):
    status, body, cid = kit.send(token="nope")
    assert (status, body, cid) == (400, {"error": codes.NEED_HUMAN}, None)
    assert kit.fakes.sms.outbox == []
    with sqlite3.connect(kit.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM counters").fetchone()[0] == 0  # 不碰計數

    seen = []

    def fake_urlopen(answer):
        def opener(req, timeout):
            seen.append((req.full_url, timeout, req.data.decode()))
            return io.BytesIO(json.dumps(answer).encode())
        return opener

    good = {"success": True, "hostname": "example.com", "action": "identity_code"}
    v = senders.CloudflareTurnstile("sec", "identity_code", urlopen=fake_urlopen(good))
    assert v.verify("tok", "1.2.3.4", "example.com") is True
    assert seen[0][0] == senders.SITEVERIFY and seen[0][1] == 5 and "secret=sec" in seen[0][2] and "response=tok" in seen[0][2]
    for bad in ({**good, "hostname": "evil.com"}, {**good, "action": "other"}, {**good, "success": False}):
        assert senders.CloudflareTurnstile("sec", "identity_code", urlopen=fake_urlopen(bad)).verify("tok", "", "example.com") is False

    def broken(req, timeout):
        raise OSError("down")
    assert senders.CloudflareTurnstile("sec", "identity_code", urlopen=broken).verify("tok", "", "example.com") is False
    assert senders.CloudflareTurnstile("", "identity_code", urlopen=fake_urlopen(good)).verify("tok", "", "example.com") is False
    assert senders.FakeTurnstile().verify("ok", "", "") and not senders.FakeTurnstile().verify("", "", "")


def test_send_reply_identical_bound_unbound_and_capped(kit):
    a = kit.send()
    kit.bound.add(kit.subj("phone", "0922222222"))
    b = kit.send(to="0922222222", ip="203.0.113.6")
    capped = kit.send(now=T0 + 1)  # 60 秒內再寄：滿了
    assert a[0] == b[0] == capped[0] == 200
    assert json.dumps(a[1]) == json.dumps(b[1]) == json.dumps(capped[1])
    assert a[1] == {"message": codes.SENT, "notice": codes.NOTICE, "privacy": "/privacy"}
    assert a[2] and b[2] and capped[2] is None  # 滿了不開新單
    assert len(kit.fakes.sms.outbox) == 2
    assert kit.store.challenge(a[2]) is not None  # 舊單不動


def test_resend_60_seconds_per_subject(kit):
    assert kit.send()[2]
    assert kit.send(now=T0 + 59)[2] is None
    assert kit.send(to="0933333333", now=T0 + 59)[2]  # 別的號碼不受影響
    assert kit.send(now=T0 + 61)[2]


def test_daily_shared_and_trusted_pools_separate(kit):
    subj = kit.subj()
    kit.store.trust_device("mine", subj, T0)
    for i in range(5):  # 別人（沒登入過的瀏覽器）刷滿共用格
        assert kit.send(now=T0 + 61 * i, ip=f"198.51.100.{i}")[2]
    assert kit.send(now=T0 + 61 * 5, ip="198.51.100.9")[2] is None
    assert kit.send(now=T0 + 61 * 6, ip="198.51.100.9", dev="forged")[2] is None  # 偽造的 tx_dev 算共用格
    for i in range(5):  # 信任的瀏覽器自己的 5 次
        assert kit.send(now=T0 + 61 * (7 + i), ip="192.0.2.1", dev="mine")[2]
    assert kit.send(now=T0 + 61 * 12, ip="192.0.2.1", dev="mine")[2] is None
    assert kit.send(now=T0 + 86401 + 61 * 12, ip="192.0.2.2")[2]  # 隔天共用格又有了


def test_source_hour_ipv4_and_ipv6_64_48(kit):
    def run(ip, i):
        return kit.send(to=f"09{i:08d}", ip=ip, now=T0 + i)[2]

    for i in range(10):
        assert run(f"2001:db8:1:2::{i + 1:x}", i)  # 同一個 /64 不同位址共用一格
    assert run("2001:db8:1:2::ff", 10) is None
    assert run("2001:db8:1:3::1", 11) is None  # 同 /48 不同 /64：撞 /48 那一格
    assert run("2001:db8:2:3::1", 12)  # 別的 /48
    for i in range(10):
        assert run("192.0.2.7", 20 + i)
    assert run("192.0.2.7", 30) is None
    assert run("192.0.2.8", 31)
    assert run("192.0.2.7", 20 + 3601)  # 一小時後


def test_pool_caps_hour_and_day(kit):
    cfg = kit.cfg.model_copy(update={"sms_caps": {"login": [3, 2], "bind": [1, 1], "anon": [2, 1]}, "source_hour": 999})
    bound = [f"09{i:08d}" for i in range(10)]
    for to in bound:
        kit.bound.add(kit.subj("phone", to))
    got = [kit.send(to=f"0955{i:06d}", now=T0 + i, cfg=cfg)[2] is not None for i in range(2)]
    assert got == [True, False]  # 匿名池每小時 1
    got = [kit.send(to=bound[i], now=T0 + i, cfg=cfg)[2] is not None for i in range(3)]
    assert got == [True, True, False]  # 登入池每小時 2，跟匿名池分開
    assert kit.send(to=bound[3], now=T0 + 3601, cfg=cfg)[2]
    assert kit.send(to=bound[4], now=T0 + 7300, cfg=cfg)[2] is None  # 登入池每天 3
    assert kit.send(to="0955999999", now=T0 + 3601, cfg=cfg)[2]
    assert kit.send(to="0955999998", now=T0 + 7300, cfg=cfg)[2] is None  # 匿名池每天 2
    assert kit.send("email", "a@b.co", now=T0 + 7300, cfg=cfg)[2]  # Email 自己的池（mail_caps 照預設）
    assert kit.send(to="0955999997", now=T0 + 7300, cfg=cfg)[1]["message"] == codes.SENT


def test_sender_failure_says_cannot_send_and_keeps_count(kit):
    kit.fakes.sms.fail = True
    assert kit.send()[:2] == (400, {"error": codes.CANNOT_SEND})
    kit.fakes.sms.fail = False
    assert kit.send(now=T0 + 1)[2] is None  # 計數不退：60 秒的格還在
    assert senders.NoSender().__class__.__name__ == "NoSender"
    with pytest.raises(senders.SendFailed):
        senders.NoSender().send("x", "y")
    with pytest.raises(senders.SendFailed):
        senders.NoSender().send("x", "y", "z")


def test_new_code_voids_old(kit):
    first = kit.send()[2]
    code1 = _last_code(kit)
    second = kit.send(now=T0 + 61)[2]
    assert kit.store.challenge(first) is None
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=first, code=code1, now=T0 + 62) is None
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=second, code=_last_code(kit), now=T0 + 62)["id"] == second


def test_wrong_code_five_times_kills_challenge(kit):
    cid = kit.send()[2]
    code = _last_code(kit)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(4):
        assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=wrong, now=T0 + 1) is None
    assert kit.store.challenge(cid)["tries"] == 4
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=wrong, now=T0 + 1) is None
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=code, now=T0 + 1) is None  # 第五次錯就作廢


def test_code_expires_after_ttl(kit):
    cid = kit.send()[2]
    code = _last_code(kit)
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=code, now=T0 + 301) is None
    assert kit.store.challenge(cid) is None
    cid = kit.send(now=T0 + 400)[2]
    row = codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=_last_code(kit), now=T0 + 699)
    assert row["channel"] == "phone" and row["subject_hmac"] == kit.subj()
    assert kit.store.challenge(cid) is None  # 對了刪單：同一碼不能用第二次
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=None, code="1", now=T0) is None
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid="", code="1", now=T0) is None


def test_same_code_in_flight_twice_only_one_wins(kit):
    """兩個請求同時送同一張對的碼：都讀到單、只有刪得到單的那一個算對（K 波修；以前兩個都開 session）。"""
    cid = kit.send()[2]
    code = _last_code(kit)
    seen = kit.store.challenge(cid)

    class Late:  # 第二個請求：讀單時單還在（讀到的是先前那一份），刪單時已經被第一個刪了
        def challenge(self, _cid):
            return dict(seen)

        def __getattr__(self, name):
            return getattr(kit.store, name)

    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code=code, now=T0 + 1)["id"] == cid
    assert codes.verify(cfg=kit.cfg, key=KEY, store=Late(), cid=cid, code=code, now=T0 + 1) is None


def test_challenge_of_another_purpose_is_refused(kit):
    """單綁用途：這一批只認 login，別種用途的單（例：之後的 bind）碼對了也回 None（路由回 BAD_CODE）。"""
    cid = "bind-cid-0001"
    kit.store.put_challenge(cid, "bind", "phone", kit.subj(), "09*****678", codes.code_hmac(KEY, cid, "123456"), T0 + 300, T0)
    assert codes.verify(cfg=kit.cfg, key=KEY, store=kit.store, cid=cid, code="123456", now=T0 + 1) is None


def test_only_hmac_stored(kit):
    kit.send()
    kit.send("email", MAIL)
    blob = Path(kit.path).read_bytes()
    texts = []
    with sqlite3.connect(kit.path) as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for row in conn.execute(f"SELECT * FROM {table}"):
                texts += [v for v in row if isinstance(v, str)]  # 時間是數字，不拿來比（碼的六位數可能剛好在時間戳裡）
    dump = "\n".join(texts)
    for plain in (PHONE, "912345678", "+886912345678", "raylin@gmail.com", "Ray.Lin"):
        assert plain not in dump and plain.encode() not in blob, plain
    for code in (_last_code(kit, "phone"), _last_code(kit, "email")):
        assert code not in texts, code
    assert "09*****678" in dump and "r*@gmail.com" in dump


def test_texts_mark_purpose_and_staff_warning(kit):
    kit.send()
    kit.send("email", MAIL)
    sms = kit.fakes.sms.outbox[-1]
    mail = kit.fakes.mail.outbox[-1]
    assert sms[0] == "+886912345678" and mail[0] == "raylin@gmail.com"
    assert kit.fakes.mail.subjects[-1] == codes.MAIL_SUBJECT
    for text in (sms[1], mail[1], codes.SMS_BIND, codes.MAIL_BIND):
        assert "客服不會跟你要驗證碼" in text
    assert "綁到遊戲帳號" in codes.SMS_BIND and "綁到遊戲帳號" in codes.MAIL_BIND
    assert "綁到" not in sms[1] and "綁到" not in mail[1]
    assert codes.text_for("phone", "bind", "123456")[1].startswith(codes.SMS_BIND.split("{")[0])


def test_codes_texts_marked():
    """codes.py 每個玩家字常數那一行（最上面那一段）有「待 joy 潤」。"""
    src = Path(codes.__file__).read_text(encoding="utf-8").splitlines()
    names = ("SENT", "CANNOT_SEND", "BAD_PHONE", "BAD_EMAIL", "NEED_HUMAN", "BAD_CODE", "NOTICE", "SMS_LOGIN", "SMS_BIND",
             "MAIL_SUBJECT", "MAIL_LOGIN", "MAIL_BIND")
    for name in names:
        lines = [ln for ln in src if ln.startswith(f"{name} = ")]
        assert len(lines) == 1 and "待 joy 潤" in lines[0], name


def test_pick_fake_or_real(tmp_path, monkeypatch):
    from tianxia.content import load_content

    content = load_content(Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "content")
    monkeypatch.setattr(content.config.identity, "fake_services", True)
    assert senders.pick(content) is senders.FAKES
    monkeypatch.setattr(content.config.identity, "fake_services", False)
    path = tmp_path / "identity.json"
    path.write_text(json.dumps({"key": "k" * 32, "turnstile_secret": "s3"}), encoding="utf-8")
    monkeypatch.setattr(identity_base, "KEY_FILE", path)
    real = senders.pick(content)
    assert isinstance(real.sms, senders.NoSender) and isinstance(real.mail, senders.NoSender)
    assert isinstance(real.turnstile, senders.CloudflareTurnstile) and real.turnstile.secret == "s3"
