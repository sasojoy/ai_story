"""same_behavior 一軌一檔：scribe（這一檔登記 scribe）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from sb.harness import ADMIN, CLOCK, emit, page_script, register_track
from sb.tracks.battle import BattleScenario

# ═══════════════════════════ scribe（全部拆包第 52 批：戰記） ═══════════════════════════
# tianxia/tale.py、tale_html.py、server 的戰記那一段（TALES、tale_view、tale_cover、tale_page_view、tale_round、start_tales）與放手一搏補劇情那一條
# （_tales_waiting、narrate_battle、narrate_once）、/api/tale/{id}、/zhanji/{code}。以前沒有軌走到（battle 那幾軌只叫 narrate_once，TALES 一直是 None）。
# 只用 server 上的名字（tests/conftest.py 收尾也認這幾個）：TALES、TALES_STOP、TALES_THREAD、TALES_CLIENT、TALES_IN_CHRONICLE、TALE_COVER_DIR、TALE_THREADS、
# TALE_RUNNING、QUEUE、LAST_HUMAN、_monotonic、power_save；哪個名字搬走了這一軌就打不到，比對會紅。


class _StopAfter:
    """TALES_STOP 的替身（start_tales 的 loop 每一輪問它）：前 rounds 次回 False（跑一輪），之後回 True（收）；記下問的秒數（TALE_ROUND_SECONDS）。
    不用真的 Event：真的要等 30 秒一輪，而且背景那一輪跟主線搶假時鐘，跑兩次就不一樣。主線在 join 上等，同一時間只有一條在跑。"""

    def __init__(self, rounds: int):
        self.left, self.asked = rounds, []

    def wait(self, seconds: float) -> bool:
        self.asked.append(seconds)
        self.left -= 1
        return self.left < 0


def _scribe_client(base: type) -> type:
    """戰記那一趟的假模型（不連網路）：ActReply 照單子上的拍子每拍一段（不寫阿拉伯數字、每段不一樣、帶上那一拍的事實，才過得了 fits 與去重），
    CastReply 照名錄每人一句；回答之前把送來的提示整份寫進輸出。其餘照 base（丟連線錯誤）。"""
    import re

    class ScribeClient(base):
        def chat_structured(self, messages, schema, *a, **k):
            if schema.__name__ in ("ActReply", "CastReply"):
                emit(f"模型單子 {schema.__name__}", {"messages": messages, "rest": repr((a, sorted(k.items())))})
            if schema.__name__ == "ActReply":
                beats = re.findall(r"^  (\d+-\d+)：([^（\n]*)", messages[-1]["content"], re.M)
                digit = "零一二三四五六七八九"
                said = ["".join(digit[int(c)] if c.isdigit() else "之" for c in beat) for beat, _ in beats]
                return schema(scenes=[{"id": beat, "head": "陣前", "text": f"{fact}鼓聲又起，塵土蔽日，{tag}處的人馬都看著這一下。"}
                                      for (beat, fact), tag in zip(beats, said)])
            if schema.__name__ == "CastReply":
                names = re.findall(r"^- (.+?)（", messages[-1]["content"], re.M)
                return schema(cast=[{"name": n, "line": "臨陣不亂，同袍都記得。"} for n in names])
            return super().chat_structured(messages, schema, *a, **k)

    return ScribeClient


class ScribeScenario(BattleScenario):
    """戰記一軌（全部拆包第 52 批；--track scribe，自己一個資料庫；計畫 docs/superpowers/plans/2026-11-06-戰記包-第1批.md）。小工具與決戰的打法照決戰那一軌，
    班底換原創名字（PM 11/04）。模型一律擋著（_setup_child 換好的 client 只丟連線錯誤，整軌預設走引擎自己那幾句）；只有 modeled、short_budget 塞假的
    ScribeClient。測試內容沒有決戰：同一串 API 照打（只有 none、404、沒登入那幾支），收場的那幾場都略過。

    前半（照段落順序）：unplugged 還沒接上（TALES 是 None：/api/tale 回 none、分享頁 404、tale_round 不做事）；boot 開機（start_tales 建小檔、開執行緒、馬上收；
    封面的順序照 tale_cover 一場一場問，TALE_COVER_DIR 換成空資料夾再放圖問一次）；open、muster、start 開一場真的決戰 A（時刻表的季長社火攻、測試內容沒有）；
    midway 開打了問 /api/tale（還沒收場：none）；gamble 官軍放手一搏；behind 補劇情走真的那一條（TALE_THREADS 開著的一個請求，_tales_waiting → narrate_battle，
    「battle-tales」那條執行緒換成就地跑，順序才固定；TALE_RUNNING 開著時兩個都回 False）；fight 打到收場；settle、reports 補送與戰報（tale_id）；
    due 收場了還沒寫（pending）；away 省電模式沒人在線不寫；blocked 有人在線、模型擋著寫成引擎那幾句（寫過的不重寫）；
    shared 發分享代碼（同一篇同一個代碼）、分享頁與 ?in=1、認不得的代碼與流水號 404、沒登入 401；bots 假人打第二場 B（他們進名錄）；
    written_two 寫 B、不發代碼；siege_due 擺一場收掉的攻城 C（守將那一格）、一場季終收兵的 D（unfinished：none，tale_round 也跳過它），都不寫。

    **這裡切一半**（寫到一半）：A 寫好、發了代碼，B 寫好、沒發，C 收場了等著寫，D 不該有。後半是重開的伺服器接同一個小檔：
    resume 重新登入、start_tales 開舊檔；reread 舊的那幾篇照讀（A 同一個代碼、B 這時才發、C 還是 pending、D 還是 none）；queued 佇列沒輪到（Busy：不寫，C 還是 pending）與
    輪到（寫成 C，排隊的名號、假人排、等多久寫進輸出）；looped 走背景那一圈（loop：建不起 client 照引擎那幾句寫 E；一輪丟例外不會停）；
    modeled 新的小檔、假模型把每一場重寫一次（提示整份進輸出、compose 照模型的字）；short_budget 寫到一半預算用完（第一幕有字、其餘照引擎那一句、名錄不叫）；
    spoiled 小檔裡一篇讀不懂（pending、分享頁 404、不重寫）；chronicle TALES_IN_CHRONICLE 開著 /api/main 的 tales 與 tale_index 一場一筆；
    season 收季之後不寫、換季之後舊的照讀、新的一季目錄是空的。小檔每幾段寫一次（整篇的雜湊、made_at、哪幾篇發過代碼）；代碼每次亂數，寫進輸出之前一律換成 <代碼N>。

    這一軌走不到的：真的 uvicorn 啟動（main() 另外會開排程、推送一堆執行緒；main 走不走到掛鉤由包的 tests 守）；奪璽單挑的戰報（_tale_ref 留在 reports_view 旁邊沒有搬）。"""

    PLAYERS = {"祁照夜": "guan", "溫聽瀾": "huang", "裴遠山": "haoqiang", "閔寄舟": None}
    NEWBIE = "顏初雪"
    GAMBLER, LATE_GAMBLER, IDLER = "祁照夜", "溫聽瀾", "閔寄舟"
    BOT_SEATS = [("假乾", "guan"), ("假坤", "guan"), ("假艮", "huang"), ("假兌", "huang")]
    PHASES_FIRST = ["setup", "join", "seat", "unplugged", "boot", "open", "muster", "start", "midway", "gamble", "behind", "fight", "settle",
                    "reports", "due", "away", "blocked", "shared", "bots", "written_two", "siege_due"]
    PHASES_SECOND = ["resume", "reread", "queued", "looped", "modeled", "short_budget", "spoiled", "chronicle", "season"]

    # ── 小工具 ──

    def side_file(self) -> Path:
        return self.db.with_name(f"{self.db.stem}-tale.sqlite")

    def shares(self) -> dict[int, str]:
        """小檔裡發過的分享代碼（流水號 → 代碼）。"""
        if not self.side_file().exists():
            return {}
        with contextlib.closing(sqlite3.connect(self.side_file())) as con:
            return {r: c for c, r in con.execute("SELECT code, record_id FROM shares").fetchall()}

    def masked(self, text: str) -> str:
        """代碼是亂數（secrets）：寫進輸出之前換成 <代碼N>，新舊與跑兩次才比得起來。"""
        for record_id, code in self.shares().items():
            text = text.replace(code, f"<代碼{record_id}>")
        return text

    def sidecar(self, tag: str) -> None:
        """小檔此刻的樣子（db_text 只讀主檔）：每一篇的季、整篇的雜湊、made_at，與哪幾篇發過代碼。"""
        rows, shared = [], []
        if self.side_file().exists():
            with contextlib.closing(sqlite3.connect(self.side_file())) as con:
                rows = [[r, s, hashlib.sha256(d.encode("utf-8")).hexdigest(), m] for r, s, d, m in
                        con.execute("SELECT record_id, season, data, made_at FROM tales ORDER BY record_id").fetchall()]
                shared = [r for (r,) in con.execute("SELECT record_id FROM shares ORDER BY record_id").fetchall()]
        emit(f"小檔 {tag}", {"tales": rows, "shared": shared})

    def tale_get(self, who: str | None, record_id: int) -> None:
        """打 /api/tale/<流水號>（who 是 None：沒登入的人）；回應裡的代碼換掉再寫。"""
        self.begin()
        url = f"/api/tale/{record_id}"
        r = (self.clients[who] if who else self.TestClient(self.server.app)).get(url)
        emit(f"{who or '沒登入'} GET {url} {r.status_code}", json.loads(self.masked(r.text)))

    def page(self, record_id: int) -> None:
        """分享頁（沒登入的人開）：整頁與遊戲裡那一層（?in=1）。還沒發代碼就寫一行。"""
        code = self.shares().get(record_id)
        if code is None:
            emit(f"第 {record_id} 場還沒發代碼", None)
            return
        anyone = self.TestClient(self.server.app)
        for suffix in ("", "?in=1"):
            self.begin()
            r = anyone.get(f"/zhanji/{code}{suffix}")
            emit(f"GET /zhanji/<代碼{record_id}>{suffix} {r.status_code}", self.masked(page_script(r.text)))

    def write_one(self, tag: str) -> None:
        self.begin()
        emit(f"{tag}：tale_round", self.server.tale_round())

    def nth(self, i: int) -> int:
        """第 i 場收場的（照開戰先後，不分季）；這份內容沒有決戰的話回 1＋i：照樣打 API，回 none。"""
        rows = [b.record_id for _, b in self.world.ended_battles()]
        return rows[i] if i < len(rows) else 1 + i

    def quick_end(self, battle_id: str, *, unfinished: bool = False) -> None:
        """直接在共用狀態開一場再收掉（同 tests/server/test_server.py 的 _ended_showdown：沒有回合紀錄也寫得出戰記）。這份內容沒有那一場就略過。"""
        definition = self.c.battles.get(battle_id)
        if definition is None:
            emit(f"這份內容沒有 {battle_id}", None)
            return
        self.begin()
        self.world.start_battle(definition, now=CLOCK[0])
        self.world.mutate_battle(self._ended(unfinished))
        emit(f"收掉一場 {battle_id}{'（季終沒打完）' if unfinished else ''}", self.world.get_battle().record_id)

    @staticmethod
    def _ended(unfinished: bool = False):
        def fn(b) -> None:
            b.phase, b.unfinished = "ended", unfinished
            b.outcome_title = "" if unfinished else "官軍守住了"
            b.outcome_side = "guan"
            b.outcome_reason = "" if unfinished else "攻到最後一回合也沒破城。"

        return fn

    @contextlib.contextmanager
    def inline_thread(self, name: str):
        """這一段裡名字是 name 的執行緒就地跑完（start 當場 run）：背景那一條跟主線搶假時鐘，跑兩次就不一樣。別的執行緒照舊（TestClient 自己會開）。"""
        import threading

        real = threading.Thread

        class Inline(real):
            def start(self):
                if self.name == name:
                    self.run()
                else:
                    super().start()

        threading.Thread = Inline
        try:
            yield
        finally:
            threading.Thread = real

    def start_thread(self, tag: str, rounds: int) -> None:
        """start_tales：建小檔、建 client（照設定，擋著模型的那一個）、開執行緒；loop 跑 rounds 輪就收（主線 join，同一時間只有一條在跑）。"""
        self.begin()
        real = self.server.TALES_STOP
        stop = self.server.TALES_STOP = _StopAfter(rounds)
        try:
            thread = self.server.start_tales(self.c.config)
            thread.join(120.0)
        finally:
            self.server.TALES_STOP = real
        emit(f"{tag}：背景執行緒", {
            "thread": [thread.name, thread.daemon, thread.is_alive()], "same": self.server.TALES_THREAD is thread, "asked": stop.asked,
            "store": self.server.TALES.path.name.replace(self.db.stem, "<db>"), "client": type(self.server.TALES_CLIENT).__name__})

    def season_bot(self) -> None:
        """整季機器人那一場自己一個資料庫，不經過戰記：略過。"""

    # ── 前半 ──

    def unplugged(self) -> None:
        """主機還沒接上（TALES 是 None）：/api/tale 一律 none、沒登入進不去、分享頁 404、tale_round 不做事、江湖史目錄是空的。"""
        self.tale_get(self.GAMBLER, 1)
        self.tale_get(None, 1)
        self.begin()
        emit("tale_view 還沒接上", self.server.tale_view(1))
        r = self.TestClient(self.server.app).get("/zhanji/nope")
        emit(f"GET /zhanji/nope {r.status_code}", page_script(r.text))
        self.write_one("還沒接上")
        game = self.server.game_for(self.GAMBLER)
        emit("tale_index 還沒接上", self.server.tale_index(game))

    def boot(self) -> None:
        self.start_thread("開機", 0)
        self.sidecar("開機")
        self.covers()

    def covers(self) -> None:
        """封面的順序（那一場自己的圖 > 攻城共用 > 通用 > 那一區的地點圖 > 事件插圖）：每一場照 web/img/tale 問一次；TALE_COVER_DIR 換成空資料夾、再放圖各問一次。"""
        battles = sorted(self.c.battles)
        ask = lambda: {i: self.server.tale_cover(self.c.battles[i]) for i in battles} | {"沒有這一場": self.server.tale_cover(None)}  # noqa: E731
        emit("封面", ask())
        real = self.server.TALE_COVER_DIR
        empty = self.db.with_name(f"{self.db.stem}-covers")
        shutil.rmtree(empty, ignore_errors=True)
        empty.mkdir(parents=True)
        self.server.TALE_COVER_DIR = empty
        try:
            emit("封面 資料夾是空的", ask())
            for name in ("siege", "default", "wancheng", "changshe_fire"):
                (empty / f"{name}.webp").write_bytes(b"x")
                emit(f"封面 放了 {name}", ask())
        finally:
            self.server.TALE_COVER_DIR = real
        shutil.rmtree(empty, ignore_errors=True)

    def midway(self) -> None:
        """開打了還沒收場：/api/tale 回 none（不是 pending）。"""
        b = self.world.get_battle()
        self.tale_get(self.GAMBLER, b.record_id if b is not None else 1)

    def behind(self) -> None:
        """第一回合結算之後的補劇情走伺服器真的那一條：TALE_THREADS 關著 _tales_waiting 是 False；打開了是 True；已經有一條在寫（TALE_RUNNING）兩個都回 False；
        接著一個請求（/api/main）在鎖外叫 narrate_battle（「battle-tales」就地跑）。只開這一個請求：別的背景寫字看同一個開關，開久了它們會真的開執行緒。"""
        self.begin()
        game = self.server.game_for(self.GAMBLER)
        emit("TALE_THREADS 關著", self.server._tales_waiting(game))
        self.server.TALE_THREADS = True
        try:
            emit("TALE_THREADS 開著", self.server._tales_waiting(game))
            self.server.TALE_RUNNING = True
            emit("已經有一條在寫", [self.server._tales_waiting(game), self.server.narrate_battle(game)])
            self.server.TALE_RUNNING = False
            with self.inline_thread("battle-tales"):
                self.main(self.GAMBLER)
        finally:
            self.server.TALE_THREADS = False
        emit("寫完了", self.server.TALE_RUNNING)
        self.battle_row("補完劇情")

    def settle(self) -> None:
        """收場之後每個人同步一次（補送；戰報才有那一筆）。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)

    def due(self) -> None:
        self.tale_get(self.GAMBLER, self.nth(0))
        self.begin()
        emit("tale_view 不帶請求", self.server.tale_view(self.nth(0)))
        self.sidecar("收場了還沒寫")

    def away(self) -> None:
        """省電模式、最後一次有真人的請求已經過了窗口：不寫，模型不載回 VRAM。"""
        self.begin()
        power_on, last = self.server.power_save.on, self.server.LAST_HUMAN
        self.server.power_save.on, self.server.LAST_HUMAN = (lambda: True), float("-inf")
        try:
            emit("省電、沒人在線：tale_round", self.server.tale_round())
        finally:
            self.server.power_save.on, self.server.LAST_HUMAN = power_on, last
        self.sidecar("省電沒寫")

    def blocked(self) -> None:
        """省電模式但有人在線（第一篇就走這一支，多讀一次假時鐘）：照寫；模型擋著，整篇是引擎那幾句。寫過的不重寫。"""
        self.begin()
        power_on, last = self.server.power_save.on, self.server.LAST_HUMAN
        self.server.power_save.on, self.server.LAST_HUMAN = (lambda: True), CLOCK[0]
        try:
            emit("省電、有人在線：tale_round", self.server.tale_round())
        finally:
            self.server.power_save.on, self.server.LAST_HUMAN = power_on, last
        self.sidecar("寫了第一篇")
        self.write_one("寫過的不重寫")

    def shared(self) -> None:
        a = self.nth(0)
        self.tale_get(self.GAMBLER, a)  # 第一次問：這時才發代碼
        self.tale_get(self.LATE_GAMBLER, a)  # 第二個人問：同一個代碼
        self.begin()
        emit("tale_view 不帶請求（沒有 url）", json.loads(self.masked(json.dumps(self.server.tale_view(a), ensure_ascii=False))))
        self.page(a)
        anyone = self.TestClient(self.server.app)
        for url in ("/zhanji/nope", f"/zhanji/{a}"):
            self.begin()
            r = anyone.get(url)
            emit(f"GET {url} {r.status_code}", page_script(r.text))
        self.tale_get(None, a)
        self.sidecar("發了代碼")

    def written_two(self) -> None:
        """假人那一場（B）：名錄裡有他們，寫法一樣。不發代碼：切一半時 B 是寫好了、還沒人要過網址。"""
        self.write_one("假人那一場")
        self.sidecar("寫了第二篇")

    def siege_due(self) -> None:
        """一場收掉的攻城（C：單方攻中立地，守將那一格）與一場季終收兵的決戰（D）；都不寫，tale_round 留到後半。"""
        from tianxia.features.battle.instance import SiegeInfo

        ids = sorted(i for i in self.c.battles if i.startswith("siege_"))
        if ids:
            self.begin()
            info = SiegeInfo(slot_id="scribe", loc=sorted(self.c.locations)[0], attackers=["guan"], holder=None, guard_side="huang")
            battle = self.world.start_siege(self.c.battles[ids[0]], CLOCK[0], 50, info)
            self.world.mutate_siege(battle.record_id, self._ended())
            emit(f"收掉一場攻城 {ids[0]}", battle.record_id)
        else:
            emit("這份內容沒有攻城", None)
        self.quick_end(self.target()[1], unfinished=True)
        self.tale_get(self.GAMBLER, self.nth(2))
        self.tale_get(self.GAMBLER, self.nth(3))

    # ── 後半（重開的伺服器接同一個小檔） ──

    def resume(self) -> None:
        self.login_all()
        self.start_thread("重開", 0)
        self.sidecar("重開之後")

    def reread(self) -> None:
        a, b, c, d = self.nth(0), self.nth(1), self.nth(2), self.nth(3)
        emit("A 的代碼沒變（第二次問之前就在）", a in self.shares())
        self.tale_get(self.GAMBLER, a)
        self.page(a)
        self.tale_get(self.GAMBLER, b)  # 這時才發
        self.page(b)
        self.tale_get(self.GAMBLER, c)
        self.tale_get(self.GAMBLER, d)
        self.sidecar("重讀之後")

    def queued(self) -> None:
        """佇列開著（當假人排，名號 TALE_OWNER_KEY）：沒輪到（Busy）這一輪不寫；輪到了寫 C。"""
        from llm_queue import Busy

        seen = []

        class Skip:
            def run(self, *a, **k):
                seen.append(["沒輪到", list(a[:1]), {x: y for x, y in k.items() if x != "fallback"}, repr(k.get("fallback"))])
                raise Busy("same_behavior")

        class Turn:
            def run(self, owner, fn, **k):
                seen.append(["輪到了", [owner], {x: y for x, y in k.items() if x != "fallback"}, repr(k.get("fallback"))])
                return fn()

        for tag, queue in (("佇列沒輪到", Skip()), ("佇列輪到了", Turn())):
            self.server.QUEUE = queue
            try:
                self.write_one(tag)
            finally:
                self.server.QUEUE = None
            emit(f"{tag}：排隊的那一下", seen)
            self.tale_get(self.GAMBLER, self.nth(2))
        self.sidecar("佇列之後")
        self.page(self.nth(2))  # 還沒發代碼
        self.tale_get(self.LATE_GAMBLER, self.nth(2))
        self.page(self.nth(2))  # 攻城的封面與守將

    def looped(self) -> None:
        """背景那一圈（start_tales 的 loop）：建不起 client（TALES_CLIENT 是 None）照引擎那幾句寫 E；有一輪丟例外（省電的判斷炸了）照樣往下走、不讓執行緒死掉。"""
        from tianxia import ollama_client

        self.quick_end(self.target()[1])
        real = ollama_client.OllamaClient.from_config

        def broken(cls, cfg):
            raise RuntimeError("same_behavior：建不起 client")

        ollama_client.OllamaClient.from_config = classmethod(broken)
        try:
            self.start_thread("建不起 client、跑一輪", 1)
        finally:
            ollama_client.OllamaClient.from_config = real
        self.sidecar("背景寫了一篇")
        power_on = self.server.power_save.on

        def boom() -> bool:
            raise RuntimeError("same_behavior：這一輪炸了")

        self.server.power_save.on = boom
        try:
            self.start_thread("一輪炸了", 2)
        finally:
            self.server.power_save.on = power_on
        self.sidecar("炸了一輪之後")

    def scribe_store(self, tag: str):
        """換一個全新的小檔（同一批收場的決戰可以再寫一次）。回原本那一個。"""
        from tianxia.features.tale.tale import TaleStore

        side = self.db.with_name(f"{self.db.stem}-{tag}.sqlite")
        if side.exists():
            side.unlink()
        real = self.server.TALES
        self.server.TALES = TaleStore(side)
        return real

    def modeled(self) -> None:
        """模型回了（假的 ScribeClient）：新的小檔，每一場重寫一次，新的先寫；提示整份進輸出，寫出來的照模型的字（真的決戰那一篇有放手一搏與原話）。"""
        from tianxia import ollama_client

        client = ollama_client.OllamaClient.from_config(self.c.config)
        client.__class__ = _scribe_client(type(client))
        real, real_client = self.scribe_store("tale-modeled"), self.server.TALES_CLIENT
        self.server.TALES_CLIENT = client
        try:
            for i in range(6):
                self.begin()
                got = self.server.tale_round()
                emit(f"模型回了 第 {i + 1} 輪", got)
                if got is None:
                    break
                emit("寫出來的那一篇", self.server.TALES.get(got).model_dump())
            self.begin()
            game = self.server.game_for(self.GAMBLER)
            emit("目錄關著", self.server.tale_index(game))
        finally:
            self.server.TALES, self.server.TALES_CLIENT = real, real_client

    def short_budget(self) -> None:
        """寫到一半預算用完：同一批再寫一次，其餘先寫掉，最舊那一場（真的決戰 A，打到第二幕）第一幕有字、之後 next_client 回 None（剩下的幕與名錄照引擎那幾句）。"""
        from tianxia import ollama_client

        client = ollama_client.OllamaClient.from_config(self.c.config)
        client.__class__ = _scribe_client(type(client))
        real, real_client = self.scribe_store("tale-short"), self.server.TALES_CLIENT
        real_clock = self.server._monotonic
        self.server.TALES_CLIENT = client
        try:
            todo = [b.record_id for b in self.world.season_ended_battles(self.world.get_season_number()) if not b.unfinished and b.outcome_title]
            for _ in todo[1:]:
                self.begin()
                self.server.tale_round()
            calls = [0]

            def ticking() -> float:  # started、第一幕的 fresh 照常；之後每一次都超過預算
                calls[0] += 1
                return CLOCK[0] + (0.0 if calls[0] <= 2 else 10.0 ** 6)

            self.server._monotonic = ticking
            self.begin()
            got = self.server.tale_round()
            emit("預算用完的那一篇", None if got is None else self.server.TALES.get(got).model_dump())
            emit("讀了幾次時鐘", calls[0])
        finally:
            self.server.TALES, self.server.TALES_CLIENT = real, real_client
            self.server._monotonic = real_clock

    def spoiled(self) -> None:
        """小檔裡一篇讀不懂（舊格式）：當作沒有（pending），分享頁 404；done 還算寫過，不重寫。放回去。"""
        a = self.nth(0)
        with contextlib.closing(sqlite3.connect(self.side_file())) as con, con:
            row = con.execute("SELECT data FROM tales WHERE record_id = ?", (a,)).fetchone()
            con.execute("UPDATE tales SET data = '{}' WHERE record_id = ?", (a,))
        self.tale_get(self.GAMBLER, a)
        self.page(a)
        self.write_one("讀不懂的那一篇")
        self.begin()
        game = self.server.game_for(self.GAMBLER)
        self.server.TALES_IN_CHRONICLE = True
        try:
            emit("目錄 讀不懂的不列", self.server.tale_index(game))
        finally:
            self.server.TALES_IN_CHRONICLE = False
        if row is not None:
            with contextlib.closing(sqlite3.connect(self.side_file())) as con, con:
                con.execute("UPDATE tales SET data = ? WHERE record_id = ?", (row[0], a))
        self.sidecar("放回去")

    def chronicle(self) -> None:
        """江湖史的目錄：開關關著是空的；開著一場一筆、新的在前（/api/main 的 tales）。"""
        self.main(self.GAMBLER)
        self.server.TALES_IN_CHRONICLE = True
        try:
            self.main(self.GAMBLER)
        finally:
            self.server.TALES_IN_CHRONICLE = False

    def season(self) -> None:
        """收季之後：有一場等著寫也不寫（season_phase 不是 running）；開下一季：舊的照讀（/api/tale、分享頁）、這一季的目錄是空的、上一季等著的不再寫。"""
        self.quick_end(self.target()[1])
        self.do(ADMIN, "end_season")
        self.write_one("休季")
        self.tale_get(self.GAMBLER, self.nth(0))
        self.do(ADMIN, "next_season")
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.write_one("下一季")
        self.tale_get(self.GAMBLER, self.nth(0))
        self.page(self.nth(0))
        self.server.TALES_IN_CHRONICLE = True
        try:
            self.main(self.GAMBLER)
        finally:
            self.server.TALES_IN_CHRONICLE = False
        self.sidecar("最後")


# 改一個字（selftest）：開篇那一拍（戰記本體，第 52 批搬進包；舊名的檔、搬進包的檔兩處找）
register_track("scribe", ScribeScenario, (("tianxia/features/tale/tale.py",),
                                          ('OPEN_LINE = "{name}帶著人馬到了。"', 'OPEN_LINE = "{name}帶著人馬到了！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "map", "military",
                       "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tale",
                       "tavern", "territory_acts", "travel", "zhuan", "zongmen"))
