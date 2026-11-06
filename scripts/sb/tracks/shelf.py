"""same_behavior 一軌一檔：shelf（這一檔登記 shelf）。"""
from __future__ import annotations

import hashlib
import json
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, TRACK_REQUIRES, emit, register_track

# ═══════════════════════════ shelf（全部拆包第 62 批：內容照包分；core_content） ═══════════════════════════
# core_content：這一段整段是第 62 批加的，上面別人的行一個字不動。
# 為什麼另開一軌：別的軌只看得到走到的那幾筆內容。載入時「沒有這個檔就是空的」，沒人抽到的句子、沒人打得出的名器，檔案搬丟了照樣全綠。


class ShelfScenario(Scenario):
    """整份內容一軌（全部拆包第 62 批；--track shelf，自己一個資料庫）。班底的名字都是原創（PM 11/04）。

    前半（照段落順序）：setup、seat 開季、兩個人就位；ledger_front 重新載入一份內容（season21、week7 讀 content/，test 讀測試內容），
    Content 前一半的欄位一格一行（筆數、整格的雜湊、第一個與最後一個鍵：dict 的先後算行為，同名蓋掉的先後也在裡面），再加人物簡介
    （FIGURE_INTROS：殼在 import 時自己讀，不經過 Content）；walk 兩個人看畫面；half 停在寫到一半：翻書人身上掛著 events/sects.json 的
    yingchuan_join、抄經客掛著 events/social_runan.json 的 sc_rn_feast，都還沒選（測試內容沒有這兩則，都掛測試內容的第一則）。
    後半是重開的行程：resume 重新登入、看畫面；ledger_back 重新載入一份內容，後一半的欄位一格一行；settle 接手的程式照事件 id 找到內容、
    選掉第一個選項；bots 兩個假人（一軍一個）擺好之後 BotRunner 跑 4 輪；season 收季、開下一季。

    這一軌走不到的：內容裡一筆一筆的規則（別的軌按得到才按得到；這一軌只釘內容的字與先後）；content.validate 的錯誤訊息（tests/core/test_content.py 守）；
    測試內容的假人沒有上線（online 0，一輪什麼也不做），假人那一段只有 season21、week7 真的在動。"""

    PLAYERS = {"翻書人": "guan", "抄經客": "huang"}
    NEWBIE = "初開卷"
    BOT_SEATS = [("架甲", "guan"), ("架乙", "huang")]
    READER, COPIER = "翻書人", "抄經客"
    PENDING = {READER: "yingchuan_join", COPIER: "sc_rn_feast"}
    PHASES_FIRST = ["setup", "seat", "ledger_front", "walk", "half"]
    PHASES_SECOND = ["resume", "ledger_back", "settle", "bots", "season"]

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    def seat(self) -> None:
        for who, side in self.PLAYERS.items():
            self.place(who, self.c.scenario.start_location, side if self.factions_on() else None)

    def fresh(self):
        """重新載入一份內容（不用 server.CONTENT：那一份一路被情境改設定，整段與接手的行程看到的才會一樣）。"""
        from tianxia.content import load_content

        if self.profile == "test":
            return load_content(self.root / "tests" / "fixtures" / "content")
        return load_content(self.root / "content", profile=self.profile)

    def ledger(self, part: str) -> None:
        c = self.fresh()
        names = list(type(c).model_fields)
        cut = len(names) // 2
        whole = c.model_dump(mode="json")
        for name in names[:cut] if part == "前" else names[cut:]:
            value = whole.get(name)  # Content 的序列化會拿掉沒寫的那幾格（_drop_unset）：測試內容沒有痕跡規則就是 None
            row = {"雜湊": hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()}
            if isinstance(value, (dict, list)):
                row["筆數"] = len(value)
            if isinstance(value, dict) and value:
                keys = list(value)
                row["頭尾"] = [keys[0], keys[-1]]
            emit(f"內容 {name}", row)

    def ledger_front(self) -> None:
        self.ledger("前")
        intros = self.server.FIGURE_INTROS
        emit("人物簡介", {"筆數": len(intros), "雜湊": hashlib.sha256(json.dumps(intros, ensure_ascii=False).encode("utf-8")).hexdigest()})

    def walk(self) -> None:
        for who in self.PLAYERS:
            self.main(who)

    def half(self) -> None:
        events = self.c.events
        for who, wanted in self.PENDING.items():
            event = wanted if wanted in events else next(iter(events))
            with self.world.action_lock():
                state = self.chars.load(who)
                state.pending_event = event
                self.chars.save(state)
            emit(f"{who} 掛著的事件", event)
            self.main(who)

    def resume(self) -> None:
        self.login_all()
        for who in self.PLAYERS:
            self.main(who)

    def ledger_back(self) -> None:
        self.ledger("後")

    def settle(self) -> None:
        for who in self.PLAYERS:
            options = self.ids(self.main(who))
            emit(f"{who} 接手之後的選項", {i: o.get("enabled") for i, o in options.items() if i.startswith("choice:")})
            first = [i for i, o in options.items() if i.startswith("choice:") and o.get("enabled")]
            if first:
                self.choose(who, first[0])
            self.main(who)

    def bots(self) -> None:
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, (name, side) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=97 + i, faction=side if on else None, season_number=self.world.get_season_number())
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
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(53), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {97 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(4):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.main(self.READER)
        self.do(ADMIN, "next_season")
        self.main(self.READER)


# 改一個字（selftest）：四階名器一件的說明（沒有一軌打得出這一件，別的軌抓不到）；搬進包的檔、舊位置兩處找
register_track("shelf", ShelfScenario, (("tianxia/features/smithy/content/tier4_named.json", "content/tier4_named.json"),
                                        ("握著像握一捧井水。", "握著像握一捧井水！")), "week7")
TRACK_REQUIRES["shelf"] = "content/figure_intros.json"  # 這一軌讀 server.FIGURE_INTROS；合回 develop 第 1 段之前的主幹沒有這個檔（_tracks_on 看的是 base）
