"""same_behavior 一軌一檔：outlets（這一檔登記 outlets）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ outlets：銀兩出口一軌（全部拆包第 43 批，dev/outlets-1） ═══════════════════════════
# 銀兩出口與捐軍備（捐素材、捐銀兩、名師指點、買破境丹、看火候、打點門路與那一間「打點」店；`donate:`、`dadian:` 兩個前綴）。計畫 docs/superpowers/plans/2026-11-05-銀兩出口包-第1批.md。

OUTLETS_NAMES = {"賀萬鈞": "guan", "裴雲舟": "huang", "邢孤雁": "guan", "霍青萍": None, "史臨淵": "guan", "駱風吟": "guan", "柳尋芳": "guan",
                 "計玄機": "guan", "石開山": "guan"}


class OutletsScenario(Scenario):
    """銀兩出口一軌（--track outlets，自己一個資料庫）。
    捐素材：自家大本營的軍需官那一串（打開、按一種、按離開）、直接捐（一種、幾種一起）、散人被擋、背包是空的、今天的點數收不下（切一半、其餘留著、
    一顆都收不下）、不在大本營、換天之後又能捐。捐銀兩：一下捐多少、錢不夠（灰）、今天的兩數捐滿、點數跟捐素材共用；散人、不在大本營被擋。
    醫館：名師指點（成、請了還沒用、錢不夠）、買破境丹（成、這一季買滿、錢不夠）。打點門路：大勢人物所在的地方（成、今天打過了、情誼到頂、錢不夠、
    人物不在此地）。看火候：有鐵匠鋪的城鎮（成、請了還沒開爐、錢不夠）。「打點」那一間店：進去、在裡頭做一樣（掮客換一句）、離開、動身、銀兩出口關了被收起。
    **前半停在兩處寫到一半**：一個人坐在「打點」店裡沒結、一個人開著軍需官那一串沒結；後半是新的行程，接著在裡面按。
    假人：BotRunner 兩個（官軍，站在自家大本營、背包有多的素材、手上有錢）；整季機器人與假人眼前的選單與分數（act:dadian、act:donate、dadian:、donate:）。
    設定：season21、week7（銀兩出口、捐軍備都開著）、test（兩樣都關著；同一串 API 照打，寫「沒有」）。"""

    DONOR_G, DONOR_H, POOR, LONE = "賀萬鈞", "裴雲舟", "邢孤雁", "霍青萍"
    CLINIC, FIG, SMITH = "史臨淵", "駱風吟", "柳尋芳"
    SHOP_IN, DONATE_IN = "計玄機", "石開山"
    PLAYERS = dict(OUTLETS_NAMES)
    BOT_SEATS = ["糧官甲", "糧官乙"]
    PHASES_FIRST = ["setup", "seat", "materials", "silver_gift", "bribe", "furnace", "shop", "open_two", "half"]
    PHASES_SECOND = ["resume", "in_shop", "in_donate", "shut", "depart", "next_day", "bots", "season"]
    PICKS = ("base", "clinic", "fig_loc", "fig_id", "smith", "mats")
    base: dict = {}
    clinic = fig_loc = fig_id = smith = ""
    mats: list = []

    # ── 小工具 ──

    @contextlib.contextmanager
    def tuned(self, owner_name: str, **values):
        """這一下把 Config 上某一塊（economy、silver_outlets）的設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = getattr(self.c.config, owner_name)
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {owner_name: dict(values)})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        have = self.options(who).get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> dict:
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])
        return opts

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、陣營、銀兩、背包、軍需帳與銀兩帳的天與數、請過的指點與火候、買過幾枚丹、打點過的人與情誼、兩間店開著沒、
        最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "silver": p.stats.get("silver", 0), "materials": dict(sorted(p.materials.items())), "legend_items": p.legend_items,
            "donate": [p.donate_day, p.donated_today], "silver_donate": [p.silver_donate_day, p.silver_donated],
            "mentor": [p.mentor_day, p.mentor_ready], "furnace": [p.furnace_day, p.furnace_ready], "bought": p.legend_silver_bought,
            "bribed": dict(sorted(p.bribed.items())), "affinities": dict(sorted(p.affinities.items())),
            "picking": [p.picking_donate, p.picking_dadian], "shop": [p.shop_line, p.shop_clue, p.shop_hold], "contrib": p.contrib,
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：軍備存量、戰線的值。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {"armaments": {k: dict(sorted(v.items())) for k, v in sorted(w.armaments.items())},
                           "rumors": [r.text for r in w.rumors][-3:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def forward_day(self) -> None:
        """時鐘往前走整整一天（回體丹的換日看現實鐘〔台灣 00:00〕，admin 的 fast_forward 只動賽季的鐘；一天的帳隔天重算）。"""
        STEP[0] += 1440

    def day_reset(self, who: str) -> None:
        """把這個人一天一次的帳清掉（捐素材的點數、捐銀兩的兩數、指點、火候、打點）：不必真的過一天就能再走一遍。"""
        def fn(p) -> None:
            p.donate_day, p.donated_today, p.silver_donate_day, p.silver_donated = -1, 0, -1, 0
            p.mentor_day, p.mentor_ready, p.furnace_day, p.furnace_ready = -1, False, -1, False
            p.bribed.clear()
        self.edit(who, fn)

    def bag(self, who: str, **by_slot: int) -> None:
        """背包放素材：slot 名字是 low（最低階捐得了的）、high（最高階捐得了的）。"""
        pick = {"low": self.mats[0] if self.mats else None, "high": self.mats[-1] if self.mats else None}
        self.edit(who, lambda p: [p.materials.__setitem__(pick[k], n) for k, n in by_slot.items() if pick.get(k)])

    def silver_of(self, who: str, n: int) -> None:
        self.edit(who, lambda p: p.stats.update({"silver": n}))

    # ── 前半 ──

    def seat(self) -> None:
        """挑地點：兩個陣營的大本營（投靠點）、有醫館的城鎮、有大勢人物（有對話人物）在的地方、有鐵匠鋪的城鎮、捐得了的素材（照階排）。"""
        from tianxia import economy, equipment, figures, territory
        from tianxia.engine import Game

        c = self.c
        bases = territory.bases(c)
        self.base = {}
        for loc, side in sorted(bases.items()):
            self.base.setdefault(side, loc)
        first = sorted(c.locations)[0]
        self.clinic = next((loc for loc in sorted(c.locations) if "醫館" in (c.locations[loc].tags or [])), first)
        shell = Game.for_world(c, self.world)
        s = shell.state
        self.fig_loc, self.fig_id = first, ""
        for loc in sorted(c.locations):
            got = [fid for fid in figures.present_at(s, c, loc) if c.figures[fid].character is not None]
            if got:
                self.fig_loc, self.fig_id = loc, got[0]
                break
        self.smith = first
        for loc in sorted(c.locations):
            s.player.location, s.player.journey = loc, None
            if equipment.smith_open(s, c):
                self.smith = loc
                break
        self.mats = [m.id for m in sorted(c.materials.values(), key=lambda m: (m.tier, m.id)) if economy.donate_points(c, m.id) > 0]
        emit("挑的地點", {"base": self.base, "clinic": self.clinic, "fig": [self.fig_loc, self.fig_id], "smith": self.smith, "mats": self.mats[:1] + self.mats[-1:],
                         "donate_on": bool(c.config.economy.donate), "silver_on": bool(c.config.silver_outlets.enabled)})
        home = lambda side: self.base.get(side, first)  # noqa: E731
        spots = {self.DONOR_G: home("guan"), self.DONOR_H: home("huang"), self.POOR: home("guan"), self.LONE: home("guan"), self.CLINIC: self.clinic,
                 self.FIG: self.fig_loc, self.SMITH: self.smith, self.SHOP_IN: self.clinic, self.DONATE_IN: home("guan")}
        for who, side in self.PLAYERS.items():
            self.place(who, spots[who], side)
            self.silver_of(who, 0 if who == self.POOR else 2000)
        self.world_view("開場")

    def materials(self) -> None:
        """捐素材：賀萬鈞打開軍需官那一串、按一種、直接捐一種、幾種一起捐、按離開；裴雲舟把一天的點數設得很小（切一半、其餘留著、一顆都收不下）；
        邢孤雁背包空的；霍青萍是散人。"""
        self.bag(self.DONOR_G, low=12, high=3)
        self.bag(self.DONOR_H, low=9, high=2)
        low, high = (self.mats[0], self.mats[-1]) if self.mats else ("none", "none")
        self.menu(self.DONOR_G, "捐之前", "act:donate")
        self.press(self.DONOR_G, "act:donate", "打開軍需官")
        opts = self.menu(self.DONOR_G, "軍需官那一串", "donate:")
        pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i not in ("donate:back", "donate:room")), None)
        if pick is not None:
            self.press(self.DONOR_G, pick, "按一種")
        self.press(self.DONOR_G, "donate:back", "離開")
        self.me(self.DONOR_G, "按完軍需官")
        self.do(self.DONOR_G, "donate", {"material": low, "count": 2})
        self.do(self.DONOR_G, "donate", {"items": [{"material": low, "count": 1}, {"material": high, "count": 1}, {"material": "none_such", "count": 1}]})
        self.do(self.DONOR_G, "donate", {"material": "none_such", "count": 1})
        self.do(self.DONOR_G, "donate", {"items": "壞的"})
        self.me(self.DONOR_G, "直接捐完")
        with self.tuned("economy", donate_daily_cap=4):
            self.press(self.DONOR_H, "act:donate", "點數很小")
            self.menu(self.DONOR_H, "點數很小", "donate:")
            self.do(self.DONOR_H, "donate", {"material": high, "count": 2})  # 一顆都收不下（單顆比今天的點數大）
            self.do(self.DONOR_H, "donate", {"material": low, "count": 9})  # 切一半、其餘留著
            self.do(self.DONOR_H, "donate", {"material": low, "count": 1})  # 今天捐滿了
            self.menu(self.DONOR_H, "捐滿之後", "donate:", "act:donate")
        self.me(self.DONOR_H, "切一半之後")
        self.press(self.DONOR_H, "donate:back", "離開")
        self.press(self.POOR, "act:donate", "背包空的")
        self.menu(self.POOR, "背包空的", "donate:")
        self.do(self.POOR, "donate", {"material": low, "count": 1})
        self.press(self.POOR, "donate:back", "離開")
        self.press(self.LONE, "act:donate", "散人")
        self.do(self.LONE, "donate", {"material": low, "count": 1})
        self.place(self.DONOR_G, self.clinic)
        self.bag(self.DONOR_G, low=3)
        self.do(self.DONOR_G, "donate", {"material": low, "count": 1})  # 不在大本營
        self.place(self.DONOR_G, self.base.get("guan", self.clinic))
        self.world_view("捐素材之後")

    def enter(self, who: str) -> None:
        """走進「打點」那一間店（五樣都在店裡，不在店裡按只算清單外）。"""
        self.press(who, "act:dadian", "進店")

    def leave(self, who: str) -> None:
        self.press(who, "dadian:back", "離開店")

    def silver_gift(self) -> None:
        """捐銀兩：賀萬鈞進店，按到今天的兩數捐滿（一下 donate_step 兩）再多按一次；裴雲舟今天的點數已經滿了；邢孤雁錢不夠；霍青萍是散人。"""
        self.enter(self.DONOR_G)
        self.menu(self.DONOR_G, "捐銀兩前", "act:silver_donate")
        for k in range(14):
            self.press(self.DONOR_G, "act:silver_donate", f"第 {k + 1} 下")
            if k in (2, 5):
                self.me(self.DONOR_G, f"捐銀兩 {k + 1} 下")
        self.me(self.DONOR_G, "捐銀兩之後")
        self.leave(self.DONOR_G)
        self.press(self.DONOR_G, "act:silver_donate", "沒進店直接按（清單外）")
        self.enter(self.DONOR_H)
        self.menu(self.DONOR_H, "點數滿了", "act:silver_donate")
        self.press(self.DONOR_H, "act:silver_donate", "點數滿了")
        self.leave(self.DONOR_H)
        self.enter(self.POOR)
        self.menu(self.POOR, "錢不夠", "act:silver_donate")
        self.press(self.POOR, "act:silver_donate", "錢不夠")
        self.edit(self.POOR, lambda p: p.stats.update({"silver": 3}))
        self.press(self.POOR, "act:silver_donate", "不到一點")
        self.leave(self.POOR)
        self.silver_of(self.POOR, 0)
        self.press(self.LONE, "act:dadian", "散人")
        self.press(self.LONE, "act:silver_donate", "散人")
        with self.tuned("silver_outlets", donate_daily_silver=150, donate_step=100):
            self.silver_of(self.DONOR_H, 500)
            self.edit(self.DONOR_H, lambda p: (setattr(p, "donated_today", 0), setattr(p, "donate_day", -1)))
            self.enter(self.DONOR_H)
            for k in range(3):
                self.press(self.DONOR_H, "act:silver_donate", f"兩數上限第 {k + 1} 下")
            self.leave(self.DONOR_H)
        self.me(self.DONOR_H, "兩數上限之後")
        self.world_view("捐銀兩之後")

    def bribe(self) -> None:
        """打點門路：駱風吟進店，在大勢人物所在的地方按打點（成、今天打過了）、再按一個不在這裡的人物、情誼到頂（上限調成 0）、錢不夠、不在這裡的人。"""
        fid = self.fig_id or "none_such"
        self.enter(self.FIG)
        self.menu(self.FIG, "有人物", "act:bribe:")
        self.press(self.FIG, f"act:bribe:{fid}", "第一次")
        self.press(self.FIG, f"act:bribe:{fid}", "今天打點過了")
        self.press(self.FIG, "act:bribe:none_such", "不在這裡的人物")
        self.me(self.FIG, "打點之後")
        self.silver_of(self.FIG, 10)
        self.day_reset(self.FIG)
        self.press(self.FIG, f"act:bribe:{fid}", "隔天錢不夠")
        self.silver_of(self.FIG, 500)
        self.day_reset(self.FIG)
        with self.tuned("silver_outlets", bribe_max=0):
            self.menu(self.FIG, "情誼到頂", "act:bribe:")
            self.press(self.FIG, f"act:bribe:{fid}", "情誼到頂")
        self.press(self.FIG, f"act:bribe:{fid}", "錢夠了再打點")
        self.leave(self.FIG)
        self.place(self.FIG, self.clinic)
        self.press(self.FIG, f"act:bribe:{fid}", "人物不在這裡（沒進店）")
        self.place(self.FIG, self.fig_loc)
        self.me(self.FIG, "打點完")

    def furnace(self) -> None:
        """看火候：柳尋芳進店（有鐵匠鋪的城鎮），按（成、請了還沒開爐、錢不夠）；今天不能再請；不在鐵匠鋪的城鎮。"""
        self.enter(self.SMITH)
        self.menu(self.SMITH, "有鐵匠鋪", "act:furnace")
        self.press(self.SMITH, "act:furnace", "第一次")
        self.press(self.SMITH, "act:furnace", "請了還沒開爐")
        self.edit(self.SMITH, lambda p: setattr(p, "furnace_ready", False))
        self.press(self.SMITH, "act:furnace", "今天請過了")
        self.day_reset(self.SMITH)
        self.silver_of(self.SMITH, 1)
        self.press(self.SMITH, "act:furnace", "隔天錢不夠")
        self.leave(self.SMITH)
        self.me(self.SMITH, "看火候之後")
        self.press(self.FIG, "act:furnace", "不在鐵匠鋪")

    def shop(self) -> None:
        """「打點」那一間店：史臨淵進去、看選單、在裡頭請一次名師指點（掮客換一句）、再請一次、買丹（錢不夠、買到這一季買滿）、離開；
        散人看不到這間店；銀兩出口關著時按進去。"""
        self.menu(self.CLINIC, "此地還能做", "act:dadian")
        self.enter(self.CLINIC)
        self.menu(self.CLINIC, "店裡", "act:", "dadian:")
        self.silver_of(self.CLINIC, 20)
        self.press(self.CLINIC, "act:buy_legend", "錢不夠買丹")
        self.press(self.CLINIC, "act:mentor", "錢不夠請指點")
        self.silver_of(self.CLINIC, 5000)
        self.press(self.CLINIC, "act:mentor", "店裡請指點")
        self.press(self.CLINIC, "act:mentor", "店裡再請一次")
        for k in range(4):
            self.press(self.CLINIC, "act:buy_legend", f"買丹第 {k + 1} 次")
        self.me(self.CLINIC, "買丹買滿")
        self.day_reset(self.CLINIC)
        self.press(self.CLINIC, "act:mentor", "清了帳再請指點")
        self.leave(self.CLINIC)
        self.me(self.CLINIC, "出店之後")
        self.menu(self.LONE, "散人", "act:dadian")
        self.press(self.LONE, "act:dadian", "散人進店")
        with self.tuned("silver_outlets", enabled=False):
            self.menu(self.CLINIC, "銀兩出口關著", "act:dadian", "act:mentor")
            self.press(self.CLINIC, "act:dadian", "關著進店")
            self.press(self.CLINIC, "act:mentor", "關著請指點")
            self.press(self.CLINIC, "act:silver_donate", "關著捐銀兩")
            self.press(self.CLINIC, "act:buy_legend", "關著買丹")
            self.press(self.CLINIC, "act:furnace", "關著看火候")
            self.press(self.CLINIC, "act:bribe:none_such", "關著打點")

    def open_two(self) -> None:
        """寫到一半的兩個人：計玄機坐在「打點」店裡沒離開，石開山開著軍需官那一串沒離開（前半停在這裡）。"""
        self.place(self.SHOP_IN, self.clinic)
        self.silver_of(self.SHOP_IN, 3000)
        self.press(self.SHOP_IN, "act:dadian", "進店")
        self.main(self.SHOP_IN)
        self.place(self.DONATE_IN, self.base.get("guan", self.clinic))
        self.bag(self.DONATE_IN, low=6, high=1)
        self.press(self.DONATE_IN, "act:donate", "打開軍需官")
        self.main(self.DONATE_IN)

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".outlets.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".outlets.json").read_text(encoding="utf-8")).items():  # 前半挑的地點（後半是新的行程）
            setattr(self, k, v)
        for who in list(self.clients):
            self.relogin(who)
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "接手")

    def in_shop(self) -> None:
        """接著坐在店裡的人：看選單、請一次指點（掮客換一句）、買丹、離開。"""
        self.menu(self.SHOP_IN, "接手後店裡", "act:", "dadian:")
        self.press(self.SHOP_IN, "act:mentor", "接手後請指點")
        self.press(self.SHOP_IN, "act:buy_legend", "接手後買丹")
        self.press(self.SHOP_IN, "dadian:back", "接手後離開")
        self.me(self.SHOP_IN, "出店之後")
        self.main(self.SHOP_IN)

    def in_donate(self) -> None:
        """接著開著軍需官那一串的人：按一種、按離開；離開之後再按一次 donate:back（清單外）。"""
        opts = self.menu(self.DONATE_IN, "接手後軍需官", "donate:")
        pick = next((i for i, o in opts.items() if i.startswith("donate:") and o.get("enabled") and i not in ("donate:back", "donate:room")), None)
        if pick is not None:
            self.press(self.DONATE_IN, pick, "接手後按一種")
        self.press(self.DONATE_IN, "donate:back", "接手後離開")
        self.press(self.DONATE_IN, "donate:back", "離開之後再按")
        self.me(self.DONATE_IN, "離開軍需官之後")

    def shut(self) -> None:
        """店開著、設定在這之間被關掉：計玄機再進店、石開山再開軍需官，這時把銀兩出口與捐軍備關掉，一同步就收店。"""
        self.press(self.SHOP_IN, "act:dadian", "再進店")
        self.press(self.DONATE_IN, "act:donate", "再開軍需官")
        self.me(self.SHOP_IN, "關掉之前")
        with self.tuned("silver_outlets", enabled=False):
            self.main(self.SHOP_IN)
            self.me(self.SHOP_IN, "銀兩出口關掉之後")
        with self.tuned("economy", donate=False):
            self.main(self.DONATE_IN)
            self.me(self.DONATE_IN, "捐軍備關掉之後")
            self.choose(self.DONATE_IN, "donate:back")
        self.main(self.SHOP_IN)
        self.main(self.DONATE_IN)

    def depart(self) -> None:
        """坐在店裡動身：計玄機進店之後走一步，店收起來；石開山開著軍需官也走一步。"""
        for who in (self.SHOP_IN, self.DONATE_IN):
            self.press(who, "act:dadian" if who == self.SHOP_IN else "act:donate", "進店再動身")
            # 坐著的選單是店裡那一串、沒有 move:：照酒肆軌，在鎖裡直接叫一次 Game._depart（收店那一行就在它裡面）
            from tianxia import atlas
            from tianxia.engine import Game

            here = self.chars.load(who).player.location
            dest = self.c.locations[here].connections[0]
            self.begin()
            with self.world.action_lock():
                game = Game(self.c, self.chars.load(who), world=self.world)
                game.sync(CLOCK[0])
                route = atlas.way_to(game.state, self.c, dest)
                emit(f"{who} 直接動身", game._depart(route, "walk") if route is not None else None)
                self.chars.save(game.state)
            self.me(who, "動身之後")

    def next_day(self) -> None:
        """換天：每一本帳重算（捐素材的點數、捐銀兩的兩數、指點與火候一天一次、打點每位一天一次）。"""
        self.forward_day()
        self.place(self.DONOR_G, self.base.get("guan", self.clinic))
        self.silver_of(self.DONOR_G, 2000)
        self.bag(self.DONOR_G, low=5)
        self.enter(self.DONOR_G)
        self.press(self.DONOR_G, "act:silver_donate", "換天捐銀兩")
        self.leave(self.DONOR_G)
        self.do(self.DONOR_G, "donate", {"material": self.mats[0] if self.mats else "none_such", "count": 5})
        self.me(self.DONOR_G, "換天之後")
        self.world_view("換天之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在自家大本營、背包有多的素材、手上有錢）若干輪；假人眼前的選單與分數；整季機器人眼前的選單挑哪一顆。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        home = self.base.get("guan", sorted(self.c.locations)[0])
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, home, None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 900
            for mid in self.mats[:2]:
                p.materials[mid] = 30
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_OUTLETS_TICKS", "6"))):
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
            emit(f"假人 {name}", {"loc": p.location, "silver": p.stats.get("silver", 0), "materials": dict(sorted(p.materials.items())),
                                  "donate": [p.donate_day, p.donated_today], "picking": [p.picking_donate, p.picking_dadian],
                                  "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "糧官丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, home, None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        p.stats["silver"] = 900
        for mid in self.mats[:2]:
            p.materials[mid] = 30
        p.bot = BotProfile(personality="普通", seed=77, faction=p.faction, season_number=self.world.get_season_number())
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        emit("假人眼前的分數", [[o.id, bot_policy.score(solo, o, p.bot)] for o in opts if o.id in ("act:donate", "act:dadian")])
        for flag, door in (("picking_donate", "act:donate"), ("picking_dadian", "act:dadian")):
            if not any(o.id == door for o in opts):
                emit(f"{door} 不在選單上，直接擺 {flag}", None)
            setattr(p, flag, True)
            inside = solo.options(odds=False)
            emit(f"坐在店裡 {flag} 的選單", [o.id for o in inside])
            emit(f"坐在店裡 {flag} 的分數", [[o.id, bot_policy.score(solo, o, p.bot)] for o in inside])
            emit(f"坐在店裡 {flag} 整季機器人挑的", sorted({str(bot.pick(solo, inside, random.Random(k))) for k in range(40)}))
            setattr(p, flag, False)

    def season(self) -> None:
        """收季、開下一季：手上的指點與火候、買過幾枚丹、開著的店、各本帳怎麼帶。"""
        self.place(self.CLINIC, self.clinic)
        self.silver_of(self.CLINIC, 5000)
        self.press(self.CLINIC, "act:dadian", "收季前進店")
        self.me(self.CLINIC, "收季前")
        self.do(ADMIN, "end_season")
        for who in (self.CLINIC, self.DONOR_G, self.DONATE_IN):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.CLINIC, self.DONOR_G, self.DONATE_IN, self.POOR):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：捐軍備記貢獻那一句（搬之前在 engine.py 的 _credit_donation、之後在 tianxia/features/outlets/ 的捐軍備動作檔；
# 第 2 項是之前的檔名，搬的人照實際的檔名改第 1 項的字串）
register_track("outlets", OutletsScenario, (("tianxia/features/outlets/donate_actions.py", "tianxia/engine.py"),
                                            ('msgs.append(f"貢獻 +{total}")', 'msgs.append(f"貢獻 +{total}！")')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "outlets", "peers",
                       "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts", "travel",
                       "zhuan"))
