"""same_behavior 一軌一檔：relay（這一檔登記 relay）。"""
from __future__ import annotations

import contextlib
import hashlib
import json

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.switchboard import SwitchboardScenario

# ═══════════════════════════ 全部拆包第 69 批：三段式的鎖外那一段（relay 一軌）═══════════════════════════
# 計畫 docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md 第二節。

RELAY_THREADS = ("battle-tales", "arena-crowd", "tavern-chatter", "letter", "yuedan", "xingshi", "event-flavor")  # 名字算行為（看守、Scribe 都認）
RELAY_ONCE = ("crowd_once", "chatter_once", "letter_once", "yuedan_once", "xingshi_once")  # 測試與腳本直接叫的那幾支（殼留一行包裝）
# 三段式走的每一條路：（路徑、body、Game 的 A 段、Game 的 C 段）。A、C 換成記參數的假身（這一批不動 Game），看的是 B 段排隊那一下帶了什麼、擋下來之後走不走 C。
# None 是那一段不換（照真的走，回一句拒絕）：對話的 C 段是 Game.choose；挑釁那一句沒有 A，C 是玩家卡的 peer_act。
RELAY_GATES = (
    ("/api/do/outing_tale", {}, "outing_tale_request", "outing_set_tale"),
    ("/api/do/battle_text", {"text": "火燒連營"}, "battle_text_request", "submit_battle_custom_action"),
    ("/api/do/seal_text", {"text": "劍出如電"}, "seal_text_request", "seal_gamble"),
    ("/api/do/duel_text", {"text": "閉眼亂揮"}, "duel_text_request", "duel_gamble"),
    ("/api/do/create_intent", {"text": "風過林梢"}, "create_request", "create_intent"),
    ("/api/do/create_reread", {"text": "寒潭映月"}, "create_reread_request", "create_reread"),
    ("/api/do/ascend_line", {}, "ascend_request", "ascend_line"),
    ("/api/do/tavern_ask", {"text": "近來如何"}, "tavern_ask_request", "tavern_ask"),
    ("/api/do/feast_text", {"text": "願天下太平"}, "feast_text_request", "feast_toast"),
    ("/api/do/persuade_text", {"id": "e1", "text": "放下刀槍"}, "persuade_request", "persuade"),
    ("/api/do/outing_say", {"text": "到此一遊"}, None, "outing_say"),
    ("/api/menxia/forge", {"insights": ["甲", "乙"]}, "forge_request", "forge"),
    ("/api/sense", {"points": [[1, 1, 0]], "png": "x"}, "sense_request", "sense_draw"),
    ("/api/choose", {"id": "dunwu:think"}, "epiphany_request", "epiphany_names"),
    ("/api/say", {"text": "不如持重些"}, "dialogue_request", None),
    ("/api/choose", {"id": "talk:0"}, "dialogue_request", None),
    ("/api/peer/act", {"name": "晚舟", "action": "discuss", "arg": "invite:x"}, "peer_request", None),
    ("/api/peer/act", {"name": "晚舟", "action": "greet", "arg": "taunt", "text": "有種來比"}, None, None),
)


def _relay_repr(value) -> str:
    import re

    return re.sub(r" at 0x[0-9A-Fa-f]+", "", repr(value))


class RelayGate:
    """佇列的假身：busy（同一個人已經有一件）、timeout（排太久）、full（假人滿了，佇列直接給 fallback）。記下排隊那一下的名號、是不是當假人排、等多久、退路。"""

    def __init__(self, kind: str):
        self.kind = kind

    def run(self, owner, job, *, fallback=None, bot=False, wait=None):
        from llm_queue import Busy, QueueTimeout

        emit("→ 排隊", [self.kind, owner, bot, wait, _relay_repr(fallback)])
        if self.kind == "busy":
            raise Busy("relay")
        if self.kind == "timeout":
            raise QueueTimeout("relay")
        return fallback


class RelayScenario(Scenario):
    """三段式的鎖外那一段一軌（全部拆包第 69 批；--track relay，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    這一批搬的是殼的接線，所以看接線：B 段排隊那一下帶了什麼（名號、當不當假人排、等多久、退路）、擋下來走不走 C、C 收到什麼；放鎖之後背景那幾條開不開、照什麼順序開。
    Game 的 A、C 這一批不動（各軌走真的），gates、zhuan_gate 把它們換成記參數的假身；模型那一趟也不跑（假模型在各軌）。

    前半：setup 開季建人；quiet 開關開著開頁（week7、season21 開局就有一封信，開 letter 一條；test 一條都不開），擺好等著的、開關關著開頁（一條都不開、單子留著）；
    feast 宴客自己寫的那一句（別軌沒有人打到 /api/do/feast_text，這一軌走真的：沒坐在席上、模型叫不動照保底分記了、同一場再敬一次、空的、模型回了記 90；test 沒有宴客，都回一句）；
    table_forge 動作表那一條 forge（帶 NO_NAME，端點不走它）與 forge_args 的轉型；
    gates 十八條路（/api/do 查表之前先接走的十一個、開爐、畫完那一筆、靜心思名、自己說、talk:N、論武取名、挑釁那一句）× 佇列三種回法（busy、timeout、full）；
    half 舊程式寫到一半：五格都等著，形勢的單被舊程式拿走了（taken）還沒寫回來——舊程式停在這裡。
    後半是重開的伺服器：resume 重新登入；picked_up 拿走了的單不再開、放回去才開，開頁（act_look）照 arena-crowd、tavern-chatter、letter、yuedan、xingshi 的順序一條一條就地跑完；
    acted 同一件事走 act（按一顆鈕）；held 背景那幾條攔著不跑，下一個請求一條都不多開，跑完再擺才開；failing 畫面丟例外：一條都不開、例外原樣丟出去、單子留著，下一個請求才開；
    queued 背景五支（crowd_once、chatter_once、letter_once、yuedan_once、xingshi_once）× 佇列三種回法（名號、等多久、退路，形勢的單放回去）；
    zhuan_gate 寫傳那一條（正文沒給 busy 拿退路、評曰逐條排、沒有評曰的那一支、同一篇已經在寫）；bots 假人兩個若干輪（假人走自己的三段式，不走這一批搬的東西；test 沒有輪到假人）；season 收季、休季開頁、下一季。
    test 設定沒有決戰、酒肆、書信、月旦評、形勢：那幾格寫一行略過，背景只開 arena-crowd。

    這一軌走不到的：模型真的回話的那一趟（各包自己的軌：talk、socialize、craft、arts、sense、crossblade、bout、ring、tavern、companions、figact、landturn、zhuan、carve、explore、battle）；
    決戰那一格 battle-tales（scribe 一軌）；write_* 開頭「已經有一條」那一支（只有兩個請求同時過了 waiting 才走到，held 擋在 waiting 那一步）；真的瀏覽器（web/ 沒動）。"""

    PLAYERS = {"岑渡": "guan", "晚舟": "huang"}
    NEWBIE = "遠山客"
    BOT_SEATS = ["渡甲", "渡乙"]
    CEN = "岑渡"
    PHASES_FIRST = ["setup", "quiet", "feast", "table_forge", "gates", "half"]
    PHASES_SECOND = ["resume", "picked_up", "acted", "held", "failing", "queued", "zhuan_gate", "bots", "season"]

    # ── 小工具 ──

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    @contextlib.contextmanager
    def threads_on(self, *, hold: bool = False):
        """打開 TALE_THREADS（只開這一段：別的背景寫字看同一個開關）。這一批的背景執行緒開的那一下記名字；hold 是攔著不跑（一人一條的那幾張表一直佔著），否則就地跑完（背景那一條跟主線搶假時鐘，跑兩次就不一樣）。"""
        import threading

        real = threading.Thread
        held: list = []

        class Caught(real):
            def start(self):
                if self.name in RELAY_THREADS or self.name.startswith("zhuan-"):
                    emit("→ 開背景執行緒", self.name)
                    if hold:
                        held.append(self)
                    else:
                        self.run()
                else:
                    super().start()

        threading.Thread = Caught
        self.server.TALE_THREADS = True
        try:
            yield held
        finally:
            threading.Thread = real
            self.server.TALE_THREADS = False

    def seed(self, who: str) -> None:
        """擺好六格裡五格等著鎖外工作的東西（決戰那一格在 scribe 一軌）：一封還沒重寫的信、一句場邊那一句、該換閒談的酒肆、一批月旦評、一張〈天下形勢〉的單。這份內容沒有的那一格略過（寫出來）。"""
        from tianxia.features.bout import arena_crowd
        from tianxia.features.companions import letters
        from tianxia.features.tavern import rules as tavern
        from tianxia.features.territory_acts import xingshi
        from tianxia.features.figure_acts import yuedan
        from tianxia.state import CrowdNote, Letter, XingshiTicket, YuedanEntry

        place = next((i for i in sorted(self.c.locations) if tavern.tavern_at(self.c, i)), None) if tavern.on(self.c) else None
        sender = next(iter(sorted(self.c.characters)), "")

        def fn(p) -> None:
            if letters.on(self.c) and sender:
                p.letters.append(Letter(id=len(p.letters) + 900, kind="道賀", sender=sender, at=0.0, text="聽聞閣下近來的作為。"))
            p.arena_crowd_note = CrowdNote(fight_id=7, round=1, kind=next(iter(arena_crowd.WHAT)), side="me", name=who, rival="對手", fixed="台下一陣騷動。", text="台下一陣騷動。")
            if place:
                p.location, p.journey, p.picking_tavern = place, None, True

        self.edit(who, fn)

        def world(s) -> None:
            if place:
                s.tavern_chatter.pop(place, None)
            if yuedan.on(self.c):
                s.yuedan.append(YuedanEntry(week=1, name=who, board="名人", fact="名望 9", line=yuedan.fixed_line("名人", who), at=s.time))
            if xingshi.on(self.c, s):
                s.xingshi_ticket = XingshiTicket(n=len(s.xingshi) + 1, key=STEP[0], opened_real=CLOCK[0], facts=["甲地易手"], line="是日：甲地易手。")

        self.world.mutate_season(world)
        emit("擺好等著的", {"酒肆": place, "信": letters.on(self.c) and bool(sender), "月旦評": yuedan.on(self.c), "形勢": xingshi.on(self.c, self.world.get_season())})

    def me(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        w = self.world.get_season()
        emit(f"{who} {tag}", {
            "letters": [[x.id, x.written, x.read, x.text] for x in p.letters], "crowd": p.arena_crowd_note.model_dump(mode="json") if p.arena_crowd_note else None,
            "chatter": {k: list(v) for k, v in sorted(w.tavern_chatter.items())}, "yuedan": [x.model_dump(mode="json") for x in w.yuedan],
            "ticket": w.xingshi_ticket.model_dump(mode="json") if w.xingshi_ticket else None, "xingshi": [x.model_dump(mode="json") for x in w.xingshi],
        })

    def canned(self):
        """A 段的假單子：B 段排隊之前會讀到的欄位都有；模型那一趟不會跑（佇列擋掉或直接給退路）。"""
        from types import SimpleNamespace

        return SimpleNamespace(
            text="一句話", option_id="talk:0", companion_id="無名", player_action="問候", battle_id=next(iter(sorted(self.c.battles)), ""), act_index=0, faction_name="官軍",
            name=self.CEN, target=None, sex=None, title="題", scene="景", setting="", place="", boss="boss", secret=False, question="問", via="seize", needs_name=True, facts=[], png="",
        )

    def through(self, who: str, kind: str, path: str, body: dict, a: str | None, c: str | None, req) -> None:
        """打一條三段式：佇列是 kind，A、C 換成假身；回應只記狀態碼、回話與畫面的雜湊；打完把人的存檔放回去。"""
        from tianxia.engine import Game

        saved = self.chars.load(who)
        swapped = []

        def spy(name: str, back) -> None:
            swapped.append((name, getattr(Game, name)))

            def fake(_g, *args, **kw):
                emit(f"→ Game.{name}", _relay_repr([args, kw]))
                return back

            setattr(Game, name, fake)

        if a:
            spy(a, req)
        if c:
            spy(c, ["（C 段）"])
        self.begin()
        self.server.QUEUE = RelayGate(kind)
        try:
            r = self.clients[who].post(path, json=body)
            raw = r.json()
            data = {k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode("utf-8")).hexdigest()[:16] if k in ("main", "menxia") else v for k, v in raw.items()} if isinstance(raw, dict) else raw
            status = r.status_code
        except Exception as exc:  # noqa: BLE001  伺服器丟出來的例外：兩份程式要丟一樣的
            status, data = "例外", f"{type(exc).__name__}: {exc}"
        finally:
            self.server.QUEUE = None
            for name, real in swapped:
                setattr(Game, name, real)
        emit(f"{who} {kind} {path} {json.dumps(body, ensure_ascii=False)} {status}", data)
        with self.world.action_lock():
            self.chars.save(saved)

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        for who, side in self.PLAYERS.items():
            self.place(who, None, faction=side if self.factions_on() else "keep")

    def quiet(self) -> None:
        """沒有等著的：開關開著也一條都不開。有等著的、開關關著（測試與假人程式的情形）：一樣一條都不開，單子留著。"""
        with self.threads_on():
            self.main(self.CEN)
        self.seed(self.CEN)
        self.begin()
        emit("形勢的單 開關關著", self.server._xingshi_waiting(self.server.game_for(self.CEN)))
        self.main(self.CEN)
        self.me(self.CEN, "開關關著")

    def feast(self) -> None:
        """宴客自己寫的那一句（別軌沒有人打到 /api/do/feast_text）：沒坐在席上、坐下了模型叫不動（照保底分）、同一場再敬一次、空的；模型回了（feasts.score 換成回 90）。"""
        from tianxia.features.feast import rules as feasts
        from tianxia.state import Feast

        who, peer = self.CEN, "晚舟"
        self.do(who, "feast_text", {"text": "願天下太平"})
        host = "xushao" if "xushao" in self.c.characters else next(iter(sorted(self.c.characters)), "")
        if not host:
            emit("這份內容沒有人物", None)
            return
        seats = {}

        def open_feast(s) -> None:
            for name in (who, peer):
                s.feast_seq += 1
                seats[name] = s.feast_seq
                s.feasts.append(Feast(id=s.feast_seq, host=host, place=self.chars.load(name).player.location, start=s.time, end=s.time + 2 * feasts.HOUR))

        self.world.mutate_season(open_feast)
        self.edit(who, lambda p: setattr(p, "feasting", seats[who]))
        self.edit(peer, lambda p: setattr(p, "feasting", seats[peer]))
        self.do(who, "feast_text", {"text": "願天下太平"})
        self.do(who, "feast_text", {"text": "再敬一杯"})
        self.do(who, "feast_text", {"text": ""})
        real = feasts.score
        feasts.score = lambda client, req: 90
        try:
            self.do(peer, "feast_text", {"text": "四海昇平"})
        finally:
            feasts.score = real
        self.edit(who, lambda p: setattr(p, "feasting", None))
        self.edit(peer, lambda p: setattr(p, "feasting", None))
        emit("席上敬的酒", [x.model_dump(mode="json") for x in self.world.get_season().feasts])

    def table_forge(self) -> None:
        """動作表那一條 forge（端點走三段式、不走它；帶 NO_NAME，就算在鎖裡叫也不叫模型）與煉製頁送來的東西怎麼轉。"""
        self.begin()
        game = self.server.game_for(self.CEN)
        with self.server._locked(game):
            emit("MENXIA_ACTIONS forge", self.server.MENXIA_ACTIONS["forge"](game, {"insights": ["甲", "乙"]}))
        emit("forge_args", [self.server.forge_args(b) for b in ({}, {"art": "劍", "insights": ["甲", 1]}, {"insights": "甲"}, {"art": 0})])

    def gates(self) -> None:
        """每一條三段式、佇列的三種回法：同一個人已經有一件、排太久（給了 busy 的丟那一句、C 段不走；沒給的拿退路），假人滿了（拿退路走 C）。"""
        req = self.canned()
        for kind in ("busy", "timeout", "full"):
            for path, body, a, c in RELAY_GATES:
                if path.endswith("battle_text") and not req.battle_id:
                    emit("這份內容沒有決戰", path)
                    continue
                self.through(self.CEN, kind, path, body, a, c, req)

    def half(self) -> None:
        """舊程式寫到一半：五格都等著，形勢的單被舊程式拿走了（A 段記了 taken）還沒寫回來，伺服器就重開了。"""
        self.seed(self.CEN)
        self.begin()
        game = self.server.game_for(self.CEN)
        with self.server._locked(game):
            request = game.xingshi_request()
        emit("舊程式拿走的單", request.model_dump(mode="json") if hasattr(request, "model_dump") else _relay_repr(request))
        self.me(self.CEN, "舊程式停在這裡")

    # ── 後半（重開的伺服器接同一個資料庫） ──

    def resume(self) -> None:
        self.login_all()

    def picked_up(self) -> None:
        """新程式接手：形勢的單被拿走了不再開（放回去才開）；開頁那一下（act_look）照 crowd、chatter、letter、yuedan、xingshi 的順序一條一條開。"""
        self.begin()
        game = self.server.game_for(self.CEN)
        emit("形勢的單 被拿走了", self.server._xingshi_waiting(game))
        emit("形勢的單 被拿走了 xingshi_once", self.server.xingshi_once(game))

        def release(s) -> None:
            if s.xingshi_ticket is not None:
                s.xingshi_ticket.taken = False

        self.world.mutate_season(release)
        with self.threads_on():
            self.main(self.CEN)
        self.me(self.CEN, "開頁之後")

    def acted(self) -> None:
        """同一件事走 act（按一顆鈕之後）：一樣的順序。"""
        self.seed(self.CEN)
        with self.threads_on():
            self.do(self.CEN, "guide_ack")
        self.me(self.CEN, "按鈕之後")

    def held(self) -> None:
        """還在寫（背景那一條沒跑完）：下一個請求一條都不多開；跑完之後（一人一條的表空了）再有等著的才開下一條。"""
        self.seed(self.CEN)
        with self.threads_on(hold=True) as held:
            self.main(self.CEN)
            self.main(self.CEN)
            self.me(self.CEN, "還在寫")
            emit("攔著的", [t.name for t in held])
            for t in held:
                self.begin()
                t.run()
        self.me(self.CEN, "寫完了")
        self.seed(self.CEN)
        with self.threads_on():
            self.main(self.CEN)
        self.me(self.CEN, "再開一輪")

    def failing(self) -> None:
        """畫面丟例外（act_look）：同步與存檔留著、鎖外工作一條都不開，例外原樣丟出去；下一個請求才開。"""
        self.seed(self.CEN)
        real = self.server.main_view

        def boom(_game):
            raise RuntimeError("relay：畫面丟例外")

        self.server.main_view = boom
        try:
            with self.threads_on():
                self.begin()
                try:
                    r = self.clients[self.CEN].get("/api/main")
                    emit("畫面丟例外 回應", r.status_code)
                except RuntimeError as exc:
                    emit("畫面丟例外 丟出來", str(exc))
        finally:
            self.server.main_view = real
        self.me(self.CEN, "畫面丟例外之後")
        with self.threads_on():
            self.main(self.CEN)
        self.me(self.CEN, "畫面好了")

    def queued(self) -> None:
        """背景那幾件排隊：名號（這個人、§史官、§說書）、當假人排、等多久、退路；擋下來時信與那一句照固定句，形勢的單放回去。"""
        for kind in ("busy", "timeout", "full"):
            self.seed(self.CEN)
            self.server.QUEUE = RelayGate(kind)
            try:
                for name in RELAY_ONCE:
                    self.begin()
                    emit(f"{kind} {name}", getattr(self.server, name)(self.server.game_for(self.CEN)))
            finally:
                self.server.QUEUE = None
            self.me(self.CEN, f"{kind} 之後")

    def zhuan_gate(self) -> None:
        """寫傳的背景那一條（write_zhuan；真的那一條在 zhuan 一軌）：正文走 model_call、沒給 busy 拿退路；評曰逐條排、名號帶 #評曰；沒有評曰的走另一支。"""
        from types import SimpleNamespace

        from tianxia.engine import Game

        season = self.world.get_season_number()
        real_req, real_write = Game.biography_request, Game.write_biography

        def write(_g, request, text, now, **kw):
            emit("→ Game.write_biography", [_relay_repr(text), kw])

        Game.write_biography = write
        try:
            for kind, verdicts in (("busy", [SimpleNamespace(fid="甲"), SimpleNamespace(fid="乙")]), ("timeout", [SimpleNamespace(fid="丙")]), ("full", [])):
                Game.biography_request = lambda _g, _s, _r, v=verdicts: SimpleNamespace(verdicts=v)
                self.server.QUEUE = RelayGate(kind)
                try:
                    with self.threads_on():
                        self.begin()
                        emit(f"{kind} write_zhuan", self.server.write_zhuan(self.server.game_for(self.CEN), season, False))
                finally:
                    self.server.QUEUE = None
        finally:
            Game.biography_request, Game.write_biography = real_req, real_write
        self.begin()
        game = self.server.game_for(self.CEN)
        self.server.ZHUAN_JOBS[self.server._zhuan_key(game, season)] = 0.0
        try:
            emit("同一篇已經在寫", self.server.write_zhuan(game, season, False))
        finally:
            self.server.ZHUAN_JOBS.clear()

    def bots(self) -> None:
        """假人（走 Game 的公開方法、自己的三段式，不走這一批搬的東西）：兩個若干輪之後，真人開頁照常接得上。"""
        SwitchboardScenario.bots(self)
        self.main(self.CEN)

    def season(self) -> None:
        """收季、休季開頁（信、那一句還在）、下一季。"""
        self.seed(self.CEN)
        self.do(ADMIN, "end_season")
        with self.threads_on():
            self.main(self.CEN)
        self.me(self.CEN, "休季")
        self.do(ADMIN, "next_season")
        with self.threads_on():
            self.main(self.CEN)
        self.me(self.CEN, "下一季")


# 改一個字（selftest）：宴客敬酒詞評不到時的保底分（第 69 批搬進宴客包 routes.py；搬進包的檔、殼兩處找）。gates 段排隊那一下照字寫退路、full 走 C 段也帶它。
register_track("relay", RelayScenario, (("tianxia/features/feast/routes.py", "server.py"),
                                        ("fallback=feasts.DEFAULT_SCORE", "fallback=feasts.DEFAULT_SCORE + 1")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
