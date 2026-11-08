"""same_behavior 一軌一檔：beacon（這一檔登記 beacon）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ beacon（全部拆包第 53 批「手機通知」） ═══════════════════════════
# beacon（全部拆包第 53 批；計畫 docs/superpowers/plans/2026-11-06-手機通知包-第1批.md 第四節）：這一段整段是第 53 批加的——
# 情境 BeaconScenario（--track beacon，自己一個資料庫、自己切一半），最後一行登記。既有的軌都沒打過 /api/push 五條與 /sw.js，
# 也沒碰過網頁推送（WebPush、PushStore、Vapid）與通知看守（notice_round）；companions 軌只叫過 server._notice_keys，duel 軌只看過約戰那一種通知。


class _BeaconPhone:
    """一台假的手機：金鑰與 auth 由名字算出來（前半＋後半是兩個行程，後半要打得開前半訂閱的鑰匙），收到的本文照 RFC 8291 解開。"""

    def __init__(self, tag: str):
        from cryptography.hazmat.primitives.asymmetric import ec

        import server_push

        seed = hashlib.sha256(f"beacon:{tag}".encode("utf-8")).digest()
        order = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
        self.key = ec.derive_private_key(int.from_bytes(seed, "big") % (order - 1) + 1, ec.SECP256R1())
        self.auth = hashlib.sha256(f"beacon-auth:{tag}".encode("utf-8")).digest()[:16]
        self.endpoint = f"https://fcm.googleapis.com/fcm/send/{tag}"
        self.p256dh = server_push.b64url(server_push._public_bytes(self.key))

    def subscription(self, quiet: bool = True) -> dict:
        import server_push

        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": server_push.b64url(self.auth)}, "quiet": quiet}

    def open(self, body: bytes) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        import server_push

        salt, idlen = body[:16], body[20]
        as_public = body[21:21 + idlen]
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
        ua = server_push.unb64url(self.p256dh)
        ikm = HKDF(hashes.SHA256(), 32, self.auth, b"WebPush: info\x00" + ua + as_public).derive(shared)
        cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
        nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
        return json.loads(AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)[:-1].decode("utf-8"))


class _BeaconPost:
    """推送服務的替身（WebPush 的 post）：不出門，記下每一次送出的位址、標頭與解開的本文；回應的狀態碼照 status 表（沒寫的是 201）。"""

    def __init__(self, phones: dict[str, _BeaconPhone]):
        self.phones, self.status, self.calls = phones, {}, []

    def __call__(self, endpoint, data=None, timeout=None, headers=None):
        import server_push

        phone = self.phones.get(endpoint)
        claims = json.loads(server_push.unb64url(headers["Authorization"].split("t=")[1].split(",")[0].split(".")[1]))
        try:
            body = phone.open(data) if phone is not None else None
        except Exception as e:  # noqa: BLE001
            body = f"打不開（{type(e).__name__}）"
        code = self.status.get(endpoint, 201)
        self.calls.append({"to": endpoint.rsplit("/", 1)[-1], "code": code, "ttl": headers["TTL"], "enc": headers["Content-Encoding"],
                           "type": headers["Content-Type"], "urgency": headers["Urgency"], "aud": claims["aud"], "body": body})

        class Reply:
            status_code = code

        return Reply()


class BeaconScenario(Scenario):
    """手機通知一軌（全部拆包第 53 批；--track beacon，自己一個資料庫）。班底與手機的名字都是原創（PM 11/04）。
    推送服務一律換成 _BeaconPost（不出門），手機是 _BeaconPhone（金鑰由名字算，收到的本文照 RFC 8291 解開）；通知的看守執行緒不開
    （NOTICE_STOP 先設好，start_web_push 開的那一條一啟動就收），一輪一輪由這裡叫 server.notice_round。

    前半（照段落順序）：unplugged 還沒接上（WEB_PUSH 是 None：五條 /api/push 一律 404、/api/main 的 web_push 是假的，/sw.js 照樣有）；
    plug start_web_push（金鑰檔放資料庫旁邊、開關關著的設定回 None）；subscribe 不認得的位址與壞鑰匙擋掉、第一台送「開了」（就地跑）、
    第二到第六台 quiet（超過 max_devices 最舊的丟掉）、別人的帳號各訂各的；prefs 一種一個開關（壞的種類是錯誤）；
    rounds 看守的幾輪：訂閱那一刻身上有的事不跳、新的信與截殺跳（一輪一人最多 per_round 則，多的下一輪）、正在玩不跳、關掉的種類不跳也記成
    看過、決戰集結與〈天下形勢〉提到；probe 設定頁「傳一則測試通知」（沒這台、送成、推送服務回 410 刪掉這台、回 500、鑰匙壞掉）；
    half 停在寫到一半：鳴鶴有一件截殺的事發生了、看守還沒來得及跳（停機那段）。
    後半是重開的伺服器：resume 重新登入、start_web_push 接同一個小檔與金鑰（設定頁的開關還在）；restart 重開後第一輪只記下、不補跳停機
    發生的事，之後新的才跳；joiners 重開之後才來的人訂閱、退訂（別人的退不掉）；mail 隔天九點看守替人送信再跳；bots 假人沒有帳號，輪到他們
    什麼也不跳；season 收季、開下一季，看守與五條路由照常。
    開關關著的設定（test）同一串 API 照打：start_web_push 回 None，五條一律 404，輪一輪不跳。

    這一軌走不到的：真的 uvicorn 啟動與 main() 的 print（web_push_line 另外直接叫一次）；看守執行緒本身的 loop（_StepFailures；測試守）。"""

    PLAYERS = {"鳴鶴": "guan", "沉舟客": "huang"}
    NEWBIE = "初見燈"
    BOT_SEATS = ["燈甲", "燈乙"]
    PHASES_FIRST = ["setup", "seat", "unplugged", "plug", "subscribe", "prefs", "rounds", "probe", "half"]
    PHASES_SECOND = ["resume", "restart", "joiners", "mail", "bots", "season"]
    CRANE, BOAT = "鳴鶴", "沉舟客"
    TAGS = ["a1", "a2", "a3", "a4", "a5", "a6", "b1", "gone", "flaky", "bad", "c1"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.phones = {t: _BeaconPhone(t) for t in self.TAGS}
        self.post = _BeaconPost({p.endpoint: p for p in self.phones.values()})
        self.vapid_file = self.db.with_name(f"{self.db.stem}-vapid.pem")

    # ── 小工具 ──

    def hit(self, who: str | None, method: str, url: str, body: dict | None = None, *, tag: str = "", welcome: bool = False) -> dict | None:
        """打一支路由（who 是 None：沒登入的人）；公鑰是隨機的，換成長度再寫。welcome：「開了」那一則就地送（不開執行緒）。"""
        self.begin()
        client = self.clients[who] if who else self.TestClient(self.server.app)
        with self.inline_send() if welcome else contextlib.nullcontext():
            r = client.post(url, json=body if body is not None else {}) if method == "POST" else client.get(url)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = r.text[:200]
        if isinstance(data, dict) and isinstance(data.get("key"), str):
            data = {**data, "key": f"<公鑰 {len(data['key'])} 字>"}
        emit(f"{who or '沒登入'} {method} {url} {tag} {r.status_code}", data)
        return data if isinstance(data, dict) else None

    @contextlib.contextmanager
    def inline_send(self):
        """這一段裡送通知的執行緒（threading.Thread(target=push.send)）就地跑完：背景那一條跟主線搶假時鐘，跑兩次就不一樣。別的執行緒照舊。"""
        import threading

        real = threading.Thread

        class Inline(real):
            def start(self):
                if getattr(self._target, "__name__", "") == "send":
                    self.run()
                else:
                    super().start()

        threading.Thread = Inline
        try:
            yield
        finally:
            threading.Thread = real

    def sent(self, tag: str) -> None:
        """自上次以來推送服務收到的每一則（送到哪一台、狀態碼、標頭、解開的本文），寫完清掉。"""
        emit(f"送出 {tag}", list(self.post.calls))
        self.post.calls.clear()

    def devices(self, tag: str) -> None:
        push = self.server.WEB_PUSH
        if push is None:
            emit(f"裝置 {tag}", None)
            return
        emit(f"裝置 {tag}", {a: [d["endpoint"].rsplit("/", 1)[-1] for d in push.store.devices(a)] for a in sorted(push.store.accounts())})

    def seen(self, tag: str) -> None:
        sent = self.server.NOTICE_SENT
        emit(f"記下的事 {tag}", {a: sorted(v) for a, v in sorted(sent.items())})

    def round(self, tag: str, minutes: int = 0) -> int:
        """看守跑一輪（先過 minutes 分鐘：quiet_seconds 之內同步過算正在玩）。"""
        STEP[0] += minutes
        self.begin()
        n = self.server.notice_round()
        emit(f"看守 {tag}", n)
        self.sent(tag)
        return n

    def sender(self) -> str:
        return sorted(self.c.characters)[0]

    def add_raid(self, who: str, title: str, tag: str = "", at: float = 1.0) -> None:
        from tianxia.state import JournalEntry

        self.edit_state(who, lambda s: s.journal.append(JournalEntry(time=at, title=title, tag=tag)))

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    def plug(self) -> None:
        """start_web_push：金鑰檔在資料庫旁邊；看守的執行緒不要真的跑（先設好停旗，一開就收）。"""
        self.server.VAPID_FILE = self.vapid_file
        self.server.NOTICE_STOP.set()
        got = self.server.start_web_push(self.c.config, post=self.post)
        thread = self.server.NOTICE_THREAD
        if thread is not None:
            thread.join(5.0)
        line = self.server.web_push_line(self.c.config).replace(str(self.vapid_file), "<金鑰檔>")
        emit("start_web_push", {"push": got is not None, "thread": None if thread is None else [thread.name, thread.daemon],
                                "line": line, "key_file": self.vapid_file.exists()})

    # ── 前半 ──

    def seat(self) -> None:
        for who, side in self.PLAYERS.items():
            self.place(who, self.c.scenario.start_location, side if self.factions_on() else None)

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    def unplugged(self) -> None:
        """還沒接上：五條都 404（_web_push 先擋，不看內容），/sw.js 是靜態檔照給，/api/main 寫著手機通知關著。"""
        self.server.WEB_PUSH = None
        emit("web_push 旗", self.main(self.CRANE).get("web_push"))
        self.hit(self.CRANE, "GET", "/api/push", tag="還沒接上")
        self.hit(self.CRANE, "POST", "/api/push/prefs", {"kind": "letter", "on": False}, tag="還沒接上")
        self.hit(self.CRANE, "POST", "/api/push/test", {"endpoint": self.phones["a1"].endpoint}, tag="還沒接上")
        self.hit(self.CRANE, "POST", "/api/push/subscribe", self.phones["a1"].subscription(), tag="還沒接上")
        self.hit(self.CRANE, "POST", "/api/push/unsubscribe", {"endpoint": self.phones["a1"].endpoint}, tag="還沒接上")
        self.begin()
        r = self.TestClient(self.server.app).get("/sw.js")
        emit("GET /sw.js", [r.status_code, r.headers.get("content-type"), r.headers.get("cache-control"),
                            hashlib.sha256(r.content).hexdigest()])
        emit("通知一輪（沒接上）", self.server.notice_round())

    def subscribe(self) -> None:
        """訂閱：壞位址、壞鑰匙擋掉；好的記下。鳴鶴六台超過上限丟最舊的；沉舟客一台；每個人的帳號各自一份。"""
        good = self.phones["a1"].subscription()
        for tag, body in (("http 位址", {**good, "endpoint": "http://fcm.googleapis.com/fcm/send/x"}),
                          ("不認得的主機", {**good, "endpoint": "https://evil.example/fcm/send/x"}),
                          ("太長", {**good, "endpoint": "https://fcm.googleapis.com/" + "x" * 1100}),
                          ("鑰匙太短", {**good, "keys": {"p256dh": "short", "auth": good["keys"]["auth"]}}),
                          ("auth 太短", {**good, "keys": {"p256dh": good["keys"]["p256dh"], "auth": "a"}}),
                          ("沒有鑰匙", {"endpoint": good["endpoint"]})):
            self.hit(self.CRANE, "POST", "/api/push/subscribe", body, tag=tag)
        self.devices("擋掉之後")
        self.hit(self.CRANE, "POST", "/api/push/subscribe", self.phones["a1"].subscription(quiet=False), tag="第一台（送開了）", welcome=True)
        self.sent("開了")
        for tag in ("a2", "a3", "a4", "a5", "a6"):
            self.hit(self.CRANE, "POST", "/api/push/subscribe", self.phones[tag].subscription(), tag=tag)
        self.hit(self.BOAT, "POST", "/api/push/subscribe", self.phones["b1"].subscription(), tag="沉舟客的一台")
        self.hit(self.CRANE, "POST", "/api/push/subscribe", self.phones["a2"].subscription(), tag="同一台再訂一次")
        self.sent("訂閱之後")
        self.devices("訂完")
        self.seen("訂完")

    def prefs(self) -> None:
        self.hit(self.CRANE, "GET", "/api/push", tag="預設全開")
        self.hit(self.CRANE, "POST", "/api/push/prefs", {"kind": "duel", "on": False}, tag="關約戰")
        self.hit(self.CRANE, "POST", "/api/push/prefs", {"kind": "不存在", "on": True}, tag="壞的種類")
        self.hit(self.CRANE, "POST", "/api/push/prefs", {"kind": "duel", "on": True}, tag="開回來")
        self.hit(self.BOAT, "POST", "/api/push/prefs", {"kind": "xingshi", "on": False}, tag="沉舟客關形勢")
        self.hit(self.CRANE, "GET", "/api/push", tag="鳴鶴不受影響")
        self.hit(self.NEWBIE, "GET", "/api/push", tag="沒訂過的人")

    def rounds(self) -> None:
        """看守的幾輪。"""
        from tianxia.state import Letter, XingshiEssay

        who_sent = self.sender()
        self.round("訂閱那一刻身上有的事不跳", 10)
        self.edit_state(self.CRANE, lambda s: s.player.letters.append(Letter(id=91, kind="道賀", sender=who_sent, at=0, text="…")))
        self.add_raid(self.CRANE, "遭某甲截殺", "敗退", 11.0)
        self.add_raid(self.BOAT, "遭某乙截殺", "", 12.0)
        self.add_raid(self.CRANE, "截殺・某丙", "", 13.0)  # 自己去截別人：不跳
        self.round("新的信與截殺跳（自己去截別人的不跳）", 0)
        self.main(self.CRANE)
        self.add_raid(self.CRANE, "遭某丁截殺", "", 14.0)
        self.round("鳴鶴剛同步過（正在玩）", 0)
        self.round("隔了一陣子：記成看過的不補跳", 10)
        self.round("同一件不跳第二次", 5)
        for i in range(5):  # 一輪一人最多 per_round 則，多的下一輪
            self.add_raid(self.BOAT, f"遭某戊{i}截殺", "", 20.0 + i)
        self.round("沉舟客一口氣五件", 10)
        self.round("剩下的下一輪", 5)
        self.hit(self.BOAT, "POST", "/api/push/prefs", {"kind": "raid", "on": False}, tag="沉舟客關截殺")
        self.add_raid(self.BOAT, "遭某己截殺", "", 30.0)
        self.round("關掉的種類不跳", 10)
        self.hit(self.BOAT, "POST", "/api/push/prefs", {"kind": "raid", "on": True}, tag="沉舟客開回來")
        self.round("開回來不補跳舊的", 5)
        self.seen("看守幾輪之後")
        if self.c.battles:
            definition = self.c.battles[sorted(self.c.battles)[0]]
            self.begin()
            self.world.start_battle(definition, now=CLOCK[0])
            emit("開了一場決戰", [definition.id, self.world.get_battle().phase])
        else:
            emit("這份內容沒有決戰", None)
        name = self.CRANE
        self.world.mutate_season(lambda s: s.xingshi.append(XingshiEssay(key=1, time=1000, n=1, essay=f"潁川一帶，{name}連日奔走。", line="是日：兩軍相持。")))
        self.round("決戰集結與形勢提到", 10)

    def probe(self) -> None:
        """設定頁「傳一則測試通知」：沒這台、送成、推送服務回 410 刪掉、回 500、鑰匙壞掉。"""
        import server_push

        for tag in ("gone", "flaky"):
            self.hit(self.BOAT, "POST", "/api/push/subscribe", self.phones[tag].subscription(), tag=tag)
        bad = self.phones["bad"].subscription()
        bad["keys"]["p256dh"] = server_push.b64url(b"\x04" + b"\x01" * 64)  # 不在曲線上的點
        self.hit(self.BOAT, "POST", "/api/push/subscribe", bad, tag="bad")
        self.devices("加了三台之後")
        self.post.status[self.phones["gone"].endpoint] = 410
        self.post.status[self.phones["flaky"].endpoint] = 500
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": self.phones["c1"].endpoint}, tag="沒這台")
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": self.phones["a3"].endpoint}, tag="別人的那台（訂的人是鳴鶴）")
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": self.phones["b1"].endpoint}, tag="送成")
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": self.phones["gone"].endpoint}, tag="410")
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": self.phones["flaky"].endpoint}, tag="500")
        self.hit(self.BOAT, "POST", "/api/push/test", {"endpoint": bad["endpoint"]}, tag="鑰匙壞掉")
        self.sent("測試通知")
        self.devices("測試之後")
        self.add_raid(self.BOAT, "遭某庚截殺", "", 40.0)
        self.round("每一台各送一次（500 與壞鑰匙不成）", 10)

    def half(self) -> None:
        """前半停在寫到一半：鳴鶴有一件截殺的事發生了，看守還沒來得及跳（接著就是停機）。"""
        self.add_raid(self.CRANE, "遭某辛截殺", "停機時", 50.0)
        STEP[0] += 10
        self.devices("前半最後")
        self.seen("前半最後")

    # ── 後半 ──

    def resume(self) -> None:
        """重開：記憶體裡的 NOTICE_SENT、MAIL_DONE 沒了，小檔與金鑰檔還在；接上之後設定頁的開關照舊。"""
        self.server.NOTICE_SENT.clear()
        self.server.MAIL_DONE.clear()
        self.plug()  # 先接上再登入：登入回的 /api/main 寫著手機通知開著沒（整段與接手的行程才同一個樣子）
        self.login_all()
        self.devices("重開之後")
        self.hit(self.CRANE, "GET", "/api/push", tag="重開之後")
        self.hit(self.BOAT, "GET", "/api/push", tag="沉舟客的開關還在")

    def restart(self) -> None:
        """重開後第一輪只記下、不補跳停機時發生的事；之後新的才跳。"""
        self.round("重開後第一輪（只記下）", 10)
        self.seen("重開後第一輪")
        self.round("第二輪也不補跳", 5)
        self.add_raid(self.CRANE, "遭某壬截殺", "", 60.0)
        self.round("新的才跳", 10)

    def joiners(self) -> None:
        """重開之後才來的人訂閱（quiet：不送「開了」）、退訂；別人的位址退不掉；退光了帳號就不在看守的名單上。"""
        self.hit(self.NEWBIE, "POST", "/api/push/subscribe", self.phones["c1"].subscription(), tag="新來的")
        self.devices("新來的訂了")
        self.hit(self.BOAT, "POST", "/api/push/unsubscribe", {"endpoint": self.phones["a3"].endpoint}, tag="退別人的")
        self.hit(self.CRANE, "POST", "/api/push/unsubscribe", {"endpoint": self.phones["a3"].endpoint}, tag="退自己的")
        self.hit(self.CRANE, "POST", "/api/push/unsubscribe", {"endpoint": self.phones["a3"].endpoint}, tag="再退一次")
        self.hit(self.NEWBIE, "POST", "/api/push/unsubscribe", {"endpoint": self.phones["c1"].endpoint}, tag="退光")
        self.devices("退完")

    def mail(self) -> None:
        """隔天九點：看守替開了通知的人送今天的信，接著跳「某某派人送來一封信」（沒有書信的設定就沒有）。"""
        cid = self.sender()
        self.world.mutate(lambda st: setattr(st.season, "jianfa_on", True))
        self.edit(self.CRANE, lambda p: (p.affinities.update({cid: 40}), setattr(p, "cheers", [f"{cid}|在潁川打退了黃巾"])))
        STEP[0] += 1440
        self.round("隔天", 10)
        state = self.chars.load(self.CRANE)
        emit("鳴鶴的信", [[x.kind, x.sender, x.read] for x in state.player.letters][-3:])
        emit("送過信的日子", sorted(self.server.MAIL_DONE.items()))
        self.round("同一天不再送", 5)

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍）若干輪；他們沒有帳號，不在訂閱名單上，看守輪到什麼也不跳。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=83 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.c.scenario.start_location, None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {83 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(6):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        self.devices("假人之後")
        self.round("假人之後的一輪", 10)

    def season(self) -> None:
        """收季、開下一季：看守與五條路由照常。"""
        self.do(ADMIN, "end_season")
        self.round("休季", 10)
        self.hit(self.CRANE, "GET", "/api/push", tag="休季")
        self.do(ADMIN, "next_season")
        self.add_raid(self.CRANE, "遭某癸截殺", "", 70.0)
        self.round("下一季", 10)
        self.hit(self.CRANE, "GET", "/api/push", tag="下一季")
        self.devices("最後")


# 改一個字（selftest）：來信那一句通知（notices.LETTER；第 53 批搬進包，舊名的檔、搬進包的檔兩處找）
register_track("beacon", BeaconScenario, (("tianxia/features/notify/notices.py",),
                                          ('LETTER = "{who}派人送來一封信。"', 'LETTER = "{who}派人送來一封信！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "notify", "outlets",
                       "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts",
                       "travel", "zhuan"))
