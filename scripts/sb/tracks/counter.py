"""same_behavior 一軌一檔：counter（這一檔登記 counter）。"""
from __future__ import annotations

from pathlib import Path

from sb.harness import emit, register_track
from sb.tracks.placard import PL_PREFIX, PlacardScenario

# ═══════════════════════════ counter：店面邊角一軌（第二輪第 93 批，dev/shops） ═══════════════════════════
# shopview 切五家之前量過（每一軌、三種設定記 tianxia/shopview.py 走到哪幾行），現有的軌沒走到的那幾句收在這裡；計畫 docs/superpowers/plans/2026-11-07-第二輪-第93批.md 第六節。
# 角色的名字都是原創的（第 22 批 PM 認定第 3 條）。


class CounterScenario(PlacardScenario):
    """店面邊角一軌（第二輪第 93 批；--track counter，自己一個資料庫）。借懸賞榜一軌的 setup、unlock、bill、post 與 tweak。每一步都存回應；分段：
    - divine_again：有了原品再開同一爐（have_divine）。
    - board_full：懸賞榜揭滿了還揭、揭一張不存在的（held_full、refused）。灰掉的鈕被 Game.choose 擋在前面，只有兩個分頁搶才到得了，所以這兩下在鎖裡直接叫包的 bounty。
    - old_save：舊存檔被拒的情況鍵沒有 shop_hold（照還成立算）。
    - blank_pool：內容沒寫這間店的句子（掌櫃那一句是空字串）。
    - rules_round：鐵匠的神器規矩講完一輪從頭。
    - solved_only：自己鑄譜上打中過、這一季現世、還沒人打出的那一件。
    - trade_words：素材頁那一句的兩種開關（升階關著、一定同屬性）與升階格子上的短原因（今天滿了、這一季滿了）。
    - donate_tier4：軍需帳跳過捐不了的四階。
    - half：**前半停在這裡**——七間店各坐一個人，掌櫃那一句停在被拒的情況（shop_hold 是舊程式記的）或進門。
    後半：resume 新程式接手，原因不成立了（手上那一張作廢、錢補夠了、背包動了）換回進門那一組，再離開；views 每個人再看一遍。
    假人：不讀店面頁，經選單碰到的 hold_for、problem_key、next_rule、board_key、attribute_rank、line_text、forged_key 現有軌的假人段走到（week7 量過），這一軌不開。
    測試內容的兵器、防具、收購升階本來關著：這一軌在記憶體裡打開（base 與 head 一樣）；鐵匠鋪、懸賞榜走得到。
    這一軌走不到的（讀輸出量過）：測試內容的神器、四階（have_divine、solved_only、神器規矩）與馬市、軍需帳、打點、酒肆、擂台的入口（選單上沒有，輸出寫「沒有」）；
    任何設定下 `_ring_short` 最後一行（challengers 已經濾掉排名與範圍，剩下的原因只有次數與冷卻，到不了）。"""

    C_DIVINE, C_FULL, C_OLD, C_BLANK, C_TELLER, C_SOLVED, C_TRADE = "櫃甲", "櫃乙", "櫃丙", "櫃丁", "櫃戊", "櫃己", "櫃庚"
    C_DONOR, C_POOR, C_DADIAN, C_WINE, C_RING = "櫃辛", "櫃壬", "櫃癸", "櫃子", "櫃丑"
    PLAYERS = {C_DIVINE: "guan", C_FULL: "guan", C_OLD: "guan", C_BLANK: "guan", C_TELLER: "guan", C_SOLVED: "guan", C_TRADE: "guan",
               C_DONOR: "guan", C_POOR: "guan", C_DADIAN: "guan", C_WINE: "guan", C_RING: "guan"}
    NEWBIE = "櫃新"
    BOT_SEATS: list[str] = []
    PHASES_FIRST = ["setup", "unlock", "seat", "divine_again", "board_full", "old_save", "blank_pool", "rules_round", "solved_only", "trade_words",
                    "donate_tier4", "half"]
    PHASES_SECOND = ["resume", "views"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        if profile == "test":  # 同 smithy 一軌：測試內容的兵器、防具、收購升階關著
            cf = self.c.config
            cf.weapons.enabled = cf.armor.enabled = cf.economy.sell = cf.economy.upgrade = True

    # ── 小工具 ──

    def tagged(self, tag: str) -> str:
        """有這個標籤的地點（照 id 排第一個）；這份內容沒有就回開局的地方，選單上照實沒有那一顆。"""
        return next((i for i, loc in sorted(self.c.locations.items()) if tag in (loc.tags or [])), self.hub())

    def base_of(self, side: str | None) -> str:
        from tianxia import territory

        return next((loc for loc, owner in sorted(territory.bases(self.c).items()) if owner == side), self.hub())

    def mats(self, tier: int) -> list[str]:
        return sorted(m.id for m in self.c.materials.values() if m.tier == tier)

    def kit(self, who: str, tiers: tuple[int, ...] = (1, 2, 3), each: int = 6, silver: int = 6000) -> None:
        def fn(p):
            p.stats["silver"] = silver
            for tier in tiers:
                for mid in self.mats(tier):
                    p.materials[mid] = p.materials.get(mid, 0) + each
        self.edit(who, fn)

    def press(self, who: str, prefix: str) -> str | None:
        """主畫面上第一顆按得下去、id 以 prefix 開頭的選項按下去；沒有就寫「沒有」。"""
        found = [i for i, o in self.ids(self.main(who)).items() if i.startswith(prefix) and o.get("enabled", True)]
        if not found:
            emit(f"{who} 沒有 {prefix}", None)
            return None
        self.choose(who, found[0])
        return found[0]

    def inside(self, who: str, tag: str, fn) -> None:
        """鎖裡直接叫（API 走不到的）：照伺服器的進鎖法重讀，做完存回去，下一步照舊從資料庫讀。"""
        self.begin()
        game = self.server.game_for(who)
        with self.server._locked(game):
            out = fn(game)
            self.chars.save(game.state)
        self.server.GAMES.clear()
        emit(f"{who} 鎖裡 {tag}", out)

    def shop_state(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        emit(f"{who} {tag}", {"line": p.shop_line, "hold": p.shop_hold, "clue": p.shop_clue, "seed": p.shop_line_seed, "rule": p.smith_rule,
                              "told": list(p.smith_rules_told), "silver": p.stats.get("silver", 0),
                              "sitting": [p.picking_smith, p.picking_bounty, p.picking_market, p.picking_donate, p.picking_dadian, p.picking_tavern, p.picking_arena]})

    # ── 前半 ──

    def seat(self) -> None:
        spots = {self.C_DONOR: self.base_of("guan"), self.C_DADIAN: self.base_of("guan"), self.C_BLANK: self.tagged("馬市"), self.C_POOR: self.tagged("馬市"), self.C_WINE: self.tagged("酒肆")}
        town = self.tagged("城鎮")
        for who in self.PLAYERS:
            self.place(who, spots.get(who, town), self.side(who))
            self.kit(who)
        emit("地點", {"town": town, **{k: v for k, v in sorted(spots.items())}})

    def divine_again(self) -> None:
        """有了原品再開同一爐：同一件神器一人一把（神器輪替季）。"""
        who = self.C_DIVINE
        self.kit(who, tiers=(4,))
        self.press(who, "act:smith")
        recipes = []
        for rid, r in sorted(self.c.forge_secrets.items()):
            if getattr(r, "divine", False) and getattr(r, "wave", 1) == 1 and r.slot == "weapon":
                main = next((m for m in self.mats(4) if self.c.materials[m].attribute == r.main.attribute), None)
                aux = next((m for m in self.mats(4) if self.c.materials[m].attribute == r.aux.attribute), None)
                if main and aux:
                    recipes.append({"kind": r.kind, "main": main, "aux": aux})
        emit("神器配方", recipes[:1])
        for body in recipes[:1]:
            self.do(who, "smith_forge", body)
            self.shop_state(who, "原品之後")
            self.do(who, "smith_forge", body)
            self.shop_state(who, "再開一爐")
        self.main(who)

    def board_full(self) -> None:
        """揭滿了還揭、揭一張不存在的：Game.choose 擋在灰掉的鈕前面，這兩下在鎖裡直接叫（兩個分頁搶的那一刻）。"""
        from tianxia.features.bounties import actions

        who = self.C_FULL
        cap = self.c.config.bounties.max_taken
        spot = (self.spots() or [self.hub()])[-1]
        self.post(*[self.bill(f"c{n}", "scout", "guan", location=spot) for n in range(cap + 1)])
        self.press(who, "act:bounties")
        for n in range(cap):
            self.choose(who, f"bounty:take:{PL_PREFIX}c{n}")
        self.shop_state(who, "揭滿")
        self.inside(who, "揭不存在的", lambda g: actions.bounty(g, f"take:{PL_PREFIX}nothing"))
        self.shop_state(who, "揭不存在的之後")
        self.main(who)
        self.inside(who, "揭滿了還揭", lambda g: actions.bounty(g, f"take:{PL_PREFIX}c{cap}"))
        self.shop_state(who, "揭滿了還揭之後")
        self.main(who)

    def old_save(self) -> None:
        """舊存檔：被拒的情況鍵還在、shop_hold 沒記，照還成立算。"""
        who = self.C_OLD
        self.press(who, "act:smith")

        def fn(p):
            p.shop_line, p.shop_hold = "refused", ""
        self.edit(who, fn)
        self.main(who)
        self.choose(who, "smith:back")

    def blank_pool(self) -> None:
        """內容沒寫這間店的句子：掌櫃那一句是空字串。兩份程式同一步拿掉、同一步放回。"""
        who = self.C_BLANK
        self.press(who, "act:market")
        saved = self.c.shop_lines.pop("market", None)
        try:
            self.main(who)
        finally:
            if saved is not None:
                self.c.shop_lines["market"] = saved
        self.main(who)
        self.choose(who, "market:back")

    def rules_round(self) -> None:
        """鐵匠的神器規矩講完一輪從頭（背包有四階、這一季每一句都講過）。"""
        who = self.C_TELLER
        pool = self.c.shop_lines.get("smith", {}).get("rules") or []
        self.kit(who, tiers=(4,), each=1)
        self.edit(who, lambda p: setattr(p, "smith_rules_told", list(range(len(pool)))))
        self.press(who, "act:smith")
        self.shop_state(who, "講完一輪又進門")
        self.choose(who, "smith:back")
        self.press(who, "act:smith")
        self.shop_state(who, "再進門")
        self.choose(who, "smith:back")

    def solved_only(self) -> None:
        """自己鑄譜上打中過、這一季現世、還沒人打出的那一件（只有他自己看得到）。"""
        who = self.C_SOLVED
        lineup = self.world.get_season().divine_lineup or []
        forged = {find.secret for _, find in self.world.divine_records()}
        rid = next((r for r in sorted(lineup) if r not in forged), None)
        emit("鑄譜上打中過的", rid)
        if rid is not None:
            self.edit(who, lambda p: p.divine_solved.update({rid: "上一季"}))
        self.press(who, "act:smith")
        self.choose(who, "smith:back")

    def trade_words(self) -> None:
        """素材頁那一句與升階格子上的短原因。"""
        who = self.C_TRADE
        cf = self.c.config
        self.kit(who, tiers=(2,), each=12)  # 二換三要的料夠換一個：今天滿了那一句
        self.press(who, "act:smith")
        with self.tweak(cf.economy, upgrade=False):
            self.main(who)
        with self.tweak(cf.economy, upgrade_same_share=1):
            self.main(who)
        self.edit(who, lambda p: setattr(p, "tier4_upgrades", cf.four_tiers.season_cap))
        self.main(who)
        with self.tweak(cf.four_tiers, enabled=False), self.tweak(cf.economy, upgrade_per_day={3: 1}):
            self.do(who, "smith_upgrade", {"attribute": "剛", "tier": 3})
            self.main(who)
        self.choose(who, "smith:back")

    def donate_tier4(self) -> None:
        """軍需帳跳過捐不了的四階（背包同時有捐得了的與捐不了的）。"""
        who = self.C_DONOR
        self.kit(who, tiers=(4,), each=1)
        self.press(who, "act:donate")
        self.main(who)

    def half(self) -> None:
        """七間店各坐一個人，掌櫃那一句停在被拒的情況：hold_for 由這一份程式記，後半由接手的程式讀。"""
        self.press(self.C_POOR, "act:market")
        self.inside(self.C_POOR, "錢不夠", lambda g: g._shop_after("還差 40 兩", "buy"))
        self.inside(self.C_DONOR, "捐不了", lambda g: g._shop_after("捐不了", "donate"))
        self.press(self.C_DADIAN, "act:dadian")
        self.inside(self.C_DADIAN, "記了一筆", lambda g: g._shop_say("done"))
        self.press(self.C_WINE, "act:tavern")
        self.inside(self.C_WINE, "錢不夠", lambda g: g._shop_after("還差 9 兩", "refused"))
        self.press(self.C_RING, "act:arena")
        pool = self.c.shop_lines.get("smith", {}).get("rules") or []
        self.edit(self.C_TELLER, lambda p: setattr(p, "smith_rules_told", list(range(len(pool) // 2))))
        self.press(self.C_TELLER, "act:smith")
        for who in (self.C_DIVINE, self.C_FULL, self.C_POOR, self.C_DONOR, self.C_DADIAN, self.C_WINE, self.C_RING, self.C_TELLER):
            self.shop_state(who, "切在這裡")
            self.main(who)

    # ── 後半 ──

    def resume(self) -> None:
        """新程式接手：原因還成立的那一句照撐；原因不成立了換回進門那一組；再離開。"""
        self.login_all()
        for who in (self.C_DIVINE, self.C_FULL, self.C_POOR, self.C_DONOR, self.C_DADIAN, self.C_WINE, self.C_RING, self.C_TELLER):
            self.shop_state(who, "接手時")
            self.main(who)

        def lapse(s) -> None:  # 手上那一張作廢了：揭滿那一句不成立
            bill = next((b for b in s.bounties if self.C_FULL in b.takers), None)
            if bill is not None:
                bill.takers.remove(self.C_FULL)
        self.world.mutate_season(lapse)
        self.main(self.C_FULL)
        for who in (self.C_POOR, self.C_WINE):  # 錢補夠了
            self.edit(who, lambda p: p.stats.update({"silver": 9000}))
            self.main(who)
        self.edit(self.C_DONOR, lambda p: p.stats.update({"silver": p.stats.get("silver", 0) + 1}))  # 指紋動了
        self.main(self.C_DONOR)
        self.edit(self.C_DIVINE, lambda p: p.stats.update({"silver": p.stats.get("silver", 0) + 1}))
        self.main(self.C_DIVINE)
        for who, back in ((self.C_DIVINE, "smith:back"), (self.C_FULL, "bounty:back"), (self.C_POOR, "market:back"), (self.C_DONOR, "donate:back"),
                          (self.C_DADIAN, "dadian:back"), (self.C_WINE, "tavern:back"), (self.C_RING, "arena:back"), (self.C_TELLER, "smith:back")):
            self.choose(who, back)
            self.shop_state(who, "離開")

    def views(self) -> None:
        for who in self.PLAYERS:
            self.main(who)


# 改一個字（selftest）：手上揭滿了記的那一句（第二段搬進 core/shop_base.py，兩處都列）
register_track("counter", CounterScenario, (("tianxia/core/shop_base.py",), ('return "held"', 'return "hold"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
