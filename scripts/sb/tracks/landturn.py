"""same_behavior 一軌一檔：landturn（這一檔登記 landturn）。"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, CLOCK0, MODEL, STEP, STEP_SECONDS, emit, register_track

# ═══════════════════════════ landturn：地盤一軌（全部拆包第 46 批，dev/territory-acts-1） ═══════════════════════════
# 地盤（Game 上的戰書與攻城時段、22:00 換天、〈天下形勢〉三段式、地盤畫面的資料、分紅與守城功補送、管理者五個救場工具；tianxia/conquest_day.py、
# xingshi.py；/api/xingshi）搬進新包 tianxia/features/territory_acts/（計畫 docs/superpowers/plans/2026-11-06-地盤包-第1批.md）。角色的名字都是原創的（PM 11/04）。

_LANDTURN_CLIENTS: dict[type, type] = {}
LANDTURN_ESSAY = "天下形勢一日三變，官軍黃巾各據一方，鄉野之間人心浮動，商旅避路而行，驛馬晝夜不息，城中百姓閉戶觀望。" * 3


def _landturn_client(base: type) -> type:
    """〈天下形勢〉的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["xingshi"] 給了（"good"＝回一篇夠長的、"short"＝回太短的）時回文章；
    其餘照 base（丟連線錯誤，照固定段）。"""
    if base not in _LANDTURN_CLIENTS:
        class LandTurnClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "XingshiReply" and MODEL.get("xingshi"):
                    return schema.model_validate({"essay": LANDTURN_ESSAY if MODEL["xingshi"] == "good" else "太短"})
                return super().chat_structured(messages, schema, *a, **k)

        _LANDTURN_CLIENTS[base] = LandTurnClient
    return _LANDTURN_CLIENTS[base]


class LandTurnScenario(Scenario):
    """地盤一軌（--track landturn，自己一個資料庫）。
    戰書：散人、不在任的第 4 階、進度不到門檻、不存在的地點各按一次被擋；在任的第 4 階（官軍）下戰書排一場攻城（時段、天下大事、江湖紀錄、那一塊凍結），
    同一天第二張被擋（一邊一天一張），黃巾的在任第 4 階併進同一場；江湖畫面的 conquest（時程表、每一塊、能不能下戰書）、管理者頁的下拉選單。
    分紅：一塊推滿易手（兩個人分紅、其中一個當場同步補、另一個留到後半）、守城功（一筆擺進帳裡）。**前半停在戰書下了、還沒到攻城時段**（那一場排著、
    分紅有人還沒領、一張戰書的時段被擺成「伺服器停過」的樣子、一張〈天下形勢〉的單 A 段拿走了而 C 段還沒收；land 撥過一次 22:00，那張前半就收掉了，所以另開一張）。
    後半：登入就補（分紅）；沒跨過 22:00 什麼都不變；同步跨過 22:00（第一個看到新的一天的人觸發：前一天沒開成的作罷、新的一天可以再下戰書、開一張〈天下形勢〉的單）；
    〈天下形勢〉三段式（A 拿單、B 鎖外請模型〔叫不動／回了／回太短〕、C 收；進度條 xingshi_mark、/api/xingshi）；沒人在線的排程（server.world_step）跨過 22:00；管理者快轉
    跨過 22:00（日子只准往前走）；單開了超過寬限照固定段收；佇列沒讓這一趟跑把單放回去。管理者五個救場工具（定一塊歸誰、定進度、立刻下戰書、取消一場攻城、
    現在就開一篇天下形勢）各幾種擋與成。假人：BotRunner 兩個、整季機器人眼前的選單。換季。
    地盤要劇本有陣營、寫了 territory：測試內容走不到（同一串 API 照打，寫「沒有」）。"""

    G_SEAT, G_LAY, G_PAY = "段臨川", "蘇折柳", "魏啟明"
    H_SEAT, H_PAY = "梁破軍", "傅雁來"
    LONE = "尹無涯"
    NEWBIE = "初來客"
    PLAYERS = {G_SEAT: "guan", G_LAY: "guan", G_PAY: "guan", H_SEAT: "huang", H_PAY: "huang", LONE: None}
    BOT_SEATS = ["營丁", "營戊"]
    PHASES_FIRST = ["setup", "land", "refuse", "letter", "pay", "half"]
    PHASES_SECOND = ["resume", "quiet", "turn1", "essay1", "turn2", "essay2", "turn3", "essay3", "tickets", "admin", "bots", "season"]

    PICKS = ("blocks",)
    blocks: dict = {}

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _landturn_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def clock_to(self, day: int, hour: int, minute: int = 0) -> None:
        """時鐘撥到第 day 天（CLOCK0 那天是第 0 天，台灣 12:00）當地的 hour:minute（只准往前；下一個請求再 +1 步）。"""
        target = CLOCK0 - 12 * 3600 + day * 86400 + hour * 3600 + minute * 60
        STEP[0] = max(STEP[0], int((target - CLOCK0) // STEP_SECONDS))
        from tianxia.features.territory_acts import conquest_day

        emit(f"時鐘撥到 第 {day} 天 {hour:02d}:{minute:02d}",
             {"offset": self.c.config.pill_day_utc_offset_hours, "key": conquest_day.day_key(CLOCK0 + (STEP[0] + 1) * STEP_SECONDS, self.c.config)})

    def on(self) -> bool:
        from tianxia import conquest, territory

        w = self.world.get_season()
        return bool(territory.on(self.c) and conquest.on(self.c, w))

    def essay_on(self) -> bool:
        from tianxia.features.territory_acts import xingshi

        return xingshi.on(self.c, self.world.get_season())

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "silver": p.stats.get("silver"), "level": p.member.level, "points": p.stat_points,
            "journal": [[e.title, e.tag, list(e.lines)[:5]] for e in state.journal[:3]],
            "state": hashlib.sha256(state.model_dump_json().encode("utf-8")).hexdigest()})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：領地爭奪的整份帳（時程表、每塊的條、分紅、日誌、settled_key、一邊一天一張）與〈天下形勢〉（收下的、等著的單、讀到哪裡）、傳聞與天下大事的尾巴。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "time": w.time, "ended": w.ended,
            "conquest": None if w.conquest is None else w.conquest.model_dump(mode="json"),
            "xingshi": [e.model_dump(mode="json") for e in w.xingshi],
            "ticket": None if w.xingshi_ticket is None else w.xingshi_ticket.model_dump(mode="json"),
            "mark": None if w.xingshi_mark is None else w.xingshi_mark.model_dump(mode="json"),
            "rumors": [r.text for r in w.rumors][-6:], "chronicle": [r.text for r in w.chronicle][-4:]})

    def seat(self, who: str, side: str) -> None:
        """這一週在任的第 4 階（有資格、席次上有名）。"""
        self.edit(who, lambda p: setattr(p, "qualified", True))
        self.world.mutate_season(lambda s: s.seats.__setitem__(side, [who]))

    def file_letter(self, who: str, loc: str, tag: str) -> None:
        emit(f"{who} {tag} 下戰書 {loc}", None)
        self.do(who, "conquest_letter", {"loc": loc})
        self.me(who, tag)

    def view(self, who: str, tag: str) -> None:
        """江湖畫面上這一包的鍵（conquest、xingshi、xingshi_mark）與 /api/xingshi（形勢頁）。"""
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        emit(f"{who} {tag} 畫面上", {k: main.get(k) for k in ("conquest", "xingshi", "xingshi_mark")})
        self.call(who, "GET", "/api/xingshi")

    # ── 前半 ──

    def land(self) -> None:
        """挑地點：A（開季沒人佔的塊，雙方都推得）、B（推滿易手的）、C（守城功）、D（換天之後再下一張戰書的）；在任的第 4 階；人站到 A 去。"""
        from tianxia import conquest
        from tianxia.features.territory_acts import xingshi

        self.clock_to(1, 9, 0)
        c = self.c
        w = self.world.get_season()
        emit("設定開關", {"territory_on": self.on(), "xingshi_on": self.essay_on(), "xingshi_lines": bool(c.xingshi_lines),
                       "xingshi_enabled": c.config.xingshi.enabled, "letter_at": c.config.conquest.letter_at, "settle_hour": c.config.conquest.settle_hour})
        if not self.on():
            emit("這一季沒有地盤：戰書、換天、形勢、分紅、救場都走不到（同一串 API 照打，看擋的那一句）", None)
            self.blocks = {}
        else:
            capturable = [loc for loc in sorted(conquest.blocks(c)) if conquest.capturable(c, loc)]
            neutral = [loc for loc in capturable if conquest.holder(w, c, loc) is None]
            pool = neutral + [loc for loc in capturable if loc not in neutral]
            pick = lambda i: pool[i % len(pool)] if pool else "nowhere"  # noqa: E731
            self.blocks = {"A": pick(0), "B": pick(1), "C": pick(2), "D": pick(3)}
        emit("挑的地點", {"blocks": self.blocks, "holders": {k: conquest.holder(w, c, v) for k, v in self.blocks.items() if v in c.locations}})
        home = self.blocks.get("A", "nowhere")
        for who, side in self.PLAYERS.items():
            self.place(who, home if home in c.locations else None, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        self.seat(self.G_SEAT, "guan")
        self.seat(self.H_SEAT, "huang")
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("開場")

    def refuse(self) -> None:
        """下不了戰書的幾種：散人、不在任、進度不到門檻、不存在的地點。"""
        a = self.blocks.get("A", "nowhere")
        self.file_letter(self.LONE, a, "散人")
        self.file_letter(self.G_LAY, a, "不在任")
        self.file_letter(self.G_SEAT, a, "進度不到")
        self.file_letter(self.G_SEAT, "nowhere", "沒有這個地點")
        self.view(self.G_SEAT, "下戰書之前")

    def letter(self) -> None:
        """在任的第 4 階下戰書：官軍下 A（排一場、凍結）、同一天第二張被擋、黃巾併進同一場；各看一遍江湖畫面與管理者頁的下拉選單。"""
        a, b = self.blocks.get("A", "nowhere"), self.blocks.get("B", "nowhere")
        if self.on():
            self.preset_bar(a, "guan", 85.0, self.G_PAY)
            self.preset_bar(a, "huang", 70.0, self.H_PAY)
            self.preset_bar(b, "guan", 80.0, self.G_PAY)
        self.view(self.G_SEAT, "進度到了")
        self.view(self.LONE, "散人看")
        self.file_letter(self.G_SEAT, a, "官軍下")
        self.file_letter(self.G_SEAT, b, "同一天第二張")
        self.file_letter(self.H_SEAT, a, "黃巾併進去")
        self.view(self.G_SEAT, "下了之後")
        self.view(self.H_SEAT, "黃巾看")
        self.call(ADMIN, "GET", "/api/admin")
        self.world_view("下了戰書")

    def pay(self) -> None:
        """分紅與守城功：B 推滿易手（G_PAY、G_LAY 分紅），只有 G_PAY 同步補；守城功擺一筆給 H_PAY（C，沒人去同步）。"""
        from tianxia.state import ConquestPayout

        b, cc = self.blocks.get("B", "nowhere"), self.blocks.get("C", "nowhere")
        if self.on():
            self.preset_bar(b, "guan", 90.0, self.G_PAY)

            def two(s) -> None:
                s.conquest.fights[b].bars["guan"].pushers = {self.G_PAY: 60.0, self.G_LAY: 30.0}

            self.world.mutate_season(two)

            def guard(s) -> None:
                s.conquest.payouts.append(ConquestPayout(name=self.H_PAY, kind="guard", loc=cc, side="huang", share=1.0, top=True,
                                                         time=s.time, silver=40, exp=30, fame=5))

            self.world.mutate_season(guard)
        self.do(ADMIN, "conquest_progress", {"id": b, "side": "guan", "value": 100})
        self.world_view("推滿之後（分紅還沒領）")
        self.main(self.G_PAY)
        self.me(self.G_PAY, "同步補了分紅")
        self.world_view("一個人領了")

    def half(self) -> None:
        """前半停在戰書下了、還沒到攻城時段：那一場排著；黃巾併進去的那一場，時段擺成「伺服器停過、時辰沒到」（換天時照作罷收）。"""
        def stale(s) -> None:
            if s.conquest is None:
                return
            for slot in s.conquest.schedule:
                if slot.status == "planned":
                    slot.at = slot.muster_at = s.time + 10 ** 8

        self.world.mutate_season(stale)
        if self.essay_on():  # 〈天下形勢〉寫到一半：land 撥過 22:00 的那張單前半就收掉了，這裡另開一張、A 段拿走、C 段還沒收（後半的同步照寬限收）
            self.do(ADMIN, "xingshi_now")
            self.begin()
            game = self.server.game_for(self.G_SEAT)
            with self.server._locked(game):
                req = game.xingshi_request()
            emit("前半拿走單子（A 段）", None if req is None else {"n": req.n, "key": req.key})
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".landturn.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".landturn.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        self.login_all()  # 登入就同步：沒領的分紅在這裡補（G_LAY、H_PAY）
        for who in (self.G_LAY, self.H_PAY, self.G_PAY):
            self.me(who, "登入之後")
        self.world_view("登入之後")

    def quiet(self) -> None:
        """同一天、沒跨過 22:00：換天的掛鉤什麼都不做（settled_key 不動）。"""
        self.clock_to(1, 10, 30)
        for who in (self.G_SEAT, self.LONE):
            self.main(who)
        self.world_view("沒跨過")

    def turn1(self) -> None:
        """同步跨過 22:00：第一個看到新的一天的人觸發——前一天沒開成的那一場作罷、開一張〈天下形勢〉的單；新的一天官軍可以再下一張戰書。"""
        self.clock_to(1, 22, 5)
        self.view(self.G_SEAT, "跨過 22:00")
        self.world_view("換天一")
        d = self.blocks.get("D", "nowhere")
        if self.on():
            self.preset_bar(d, "guan", 75.0, self.G_PAY)
        self.file_letter(self.G_SEAT, d, "新的一天再下")
        self.view(self.H_SEAT, "黃巾看")
        for who in (self.G_LAY, self.LONE):
            self.main(who)

    def essay(self, tag: str) -> None:
        self.view(self.G_SEAT, f"{tag} 單子開著")
        self.world_view(f"{tag} 單子開著")
        emit(f"{tag} xingshi_once", self.server.xingshi_once(self.server.game_for(self.G_SEAT)))
        self.view(self.G_SEAT, f"{tag} 收下之後")
        self.world_view(f"{tag} 收下之後")

    def essay1(self) -> None:
        """B 段模型叫不動：照固定段收。"""
        MODEL["xingshi"] = None
        self.essay("叫不動")

    def turn2(self) -> None:
        """沒人在線，伺服器排程（server.world_step）跨過 22:00 也換天。"""
        self.clock_to(2, 22, 5)
        self.begin()
        emit("排程 world_step", self.server.world_step(time.time))
        self.world_view("換天二（排程）")

    def essay2(self) -> None:
        """B 段模型回了一篇夠長的。"""
        MODEL["xingshi"] = "good"
        try:
            self.essay("模型回了")
        finally:
            MODEL["xingshi"] = None

    def turn3(self) -> None:
        """管理者快轉跨過 22:00（advance）；之後現實時鐘的人同步，日子只准往前走（不重排、不倒退）。"""
        self.do(ADMIN, "fast_forward", {"hours": 24})
        self.world_view("換天三（快轉）")
        self.clock_to(3, 9, 0)
        self.main(self.G_SEAT)
        self.world_view("快轉之後現實時鐘的人同步")

    def essay3(self) -> None:
        """B 段模型回了太短的：過不了 clean，照固定段。"""
        MODEL["xingshi"] = "short"
        self.do(ADMIN, "xingshi_now")  # 快轉那一張單，現實時鐘的人一同步就過了寬限收掉了：這一張另外開
        try:
            self.essay("回太短")
        finally:
            MODEL["xingshi"] = None

    def tickets(self) -> None:
        """單子的其他走法：管理者現在就開一篇（兩次：第二次先把還在等的收掉）；佇列沒讓這一趟跑（單子放回去、隔 retry 再試）；開了超過寬限照固定段收。"""
        self.do(ADMIN, "xingshi_now")
        self.view(self.G_SEAT, "現在就開一篇")
        self.do(ADMIN, "xingshi_now")
        self.world_view("開了第二篇")
        real_queue = self.server.QUEUE

        class Skip:
            def run(self, *a, **k):
                from llm_queue import Busy

                raise Busy("same_behavior")

        self.server.QUEUE = Skip()
        try:
            emit("佇列沒輪到 xingshi_once", self.server.xingshi_once(self.server.game_for(self.G_SEAT)))
        finally:
            self.server.QUEUE = real_queue
        self.world_view("放回去之後")
        STEP[0] += 30  # 超過 grace_seconds（900 秒）：下一個同步的人照固定段收
        self.main(self.G_SEAT)
        self.world_view("過了寬限")
        self.view(self.LONE, "散人看形勢")

    def admin(self) -> None:
        """管理者五個救場工具：定一塊歸誰（成、本來就這樣、不是搶得下的、不是兩軍）、定進度（部分、推滿、不是此刻佔著的那一方才收）、立刻下戰書（成、已有一場、不收）、
        取消一場攻城（成、找不到）、現在就開一篇天下形勢（上面已走）；非管理者按了被擋；管理者頁的下拉選單。"""
        a, b, cc, d = (self.blocks.get(k, "nowhere") for k in ("A", "B", "C", "D"))
        self.do(self.G_SEAT, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "huang"})
        self.do(ADMIN, "conquest_set", {"id": "nowhere", "side": "guan"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": "dragon"})
        self.do(ADMIN, "conquest_set", {"id": cc, "side": ""})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "huang", "value": 55})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "huang", "value": 0})
        self.do(ADMIN, "conquest_progress", {"id": d, "side": "nobody", "value": 10})
        self.do(ADMIN, "conquest_progress", {"id": a, "side": "huang", "value": 100})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "huang"})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "huang"})
        self.do(ADMIN, "admin_conquest_letter", {"id": b, "side": "guan"})
        self.do(ADMIN, "admin_conquest_letter", {"id": "nowhere", "side": "guan"})
        self.call(ADMIN, "GET", "/api/admin")
        self.main(self.G_SEAT)  # 下一個同步的人把剛下的戰書開成集結
        w = self.world.get_season()
        slots = [] if w.conquest is None else [s.id for s in w.conquest.schedule if s.status not in ("done", "void")]
        emit("還沒打完的攻城", slots)
        for sid in slots[:1] + ["no-such-slot"]:
            self.do(ADMIN, "conquest_cancel", {"id": sid})
        self.do(ADMIN, "xingshi_now")
        self.world_view("救場之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在 A）若干輪，跨過 22:00 再若干輪；整季機器人眼前的選單挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        home = self.blocks.get("A", "nowhere")
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.journey = p.bot.faction, None
            if home in self.c.locations:
                p.location = home
                p.visited.add(home)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for k in range(int(os.environ.get("SB_LANDTURN_TICKS", "8"))):
                if k == 4:
                    self.clock_to(4, 22, 10)
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "營己", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.journey = "guan" if "guan" in sides else None, None
        if home in self.c.locations:
            p.location = home
            p.visited.add(home)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：戰書、時程表、分紅、形勢單怎麼處理。"""
        self.do(ADMIN, "end_season")
        for who in (self.G_SEAT, self.H_SEAT, self.LONE):
            self.view(who, "收季之後")
        self.do(ADMIN, "next_season")
        for who in (self.G_SEAT, self.H_SEAT, self.LONE):
            self.view(who, "換季之後")
            self.me(who, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：前一天沒開成的攻城作罷那一句（搬之前在 tianxia/conquest_day.py、之後在 tianxia/features/territory_acts/conquest_day.py；
# 第 2 項是之後的檔名，搬的人照實際的檔名改這一個字串）
register_track("landturn", LandTurnScenario, (("tianxia/features/territory_acts/conquest_day.py",),
                                              ('VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷。"',
                                               'VOID_LATE = "{who}原定攻{place}，時辰已過，這一仗作罷！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
