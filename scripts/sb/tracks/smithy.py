"""same_behavior 一軌一檔：smithy（這一檔登記 smithy）。"""
from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MUTATIONS, STEP, db_text, emit, register_track

# ═══════════════════════════ smithy：鐵匠鋪一軌（全部拆包第 41 批，dev/smithy-1） ═══════════════════════════
# 鐵匠鋪（架上的買、修、淬煉、換上、拆解，一步一步打造與店面的直接開爐，隱藏配方與神器原品，神器定名、以器配招，收購升階，看火候，
# 裝備庫那一列的修與淬煉，/api/smith_line 與每一個 smith: 動作）：Game 上 23 個方法與 tianxia/smithing.py 之後搬進 tianxia/features/smithy/
# （計畫 docs/superpowers/plans/2026-11-06-鐵匠鋪包-第1批.md）。角色的名字都是原創的（第 22 批 PM 認定第 3 條）。

SMITHY_BOTS = ["匠甲", "匠乙"]
SMITHY_SILVER = 6000


class SmithyScenario(Scenario):
    """鐵匠鋪一軌（全部拆包第 41 批；--track smithy，自己一個資料庫）。每一步都存回應；分段：
    - setup：籌備中（管理者還沒開季）鐵匠鋪的每一個入口都擋；開季、補體力、擺到城鎮，給銀兩與各階素材。
    - closed：不在城鎮的人按進門、直接開爐、收購、升階、看火候、裝備庫那一列的修與淬煉、/api/smith_line，都回被擋的那一句。
    - shelf：架上買（空手、再買進裝備庫）、修（磨損了）、淬煉（淬到滿）、換上、拆解（含灰掉的）、切到防具頁買修淬換上、素材頁、離開。
    - gearwork：裝備庫那一列的修與淬煉（/api/menxia/repair_item、temper_item；兵與甲、不存在的、沒錢、淬滿了）。
    - trade：素材頁選單的賣與升（smith:sell／smith:upgrade），店面的 /api/do/smith_sell、smith_upgrade（過量、不認得、沒料）。
    - wizard：一步一步打造——挑種類、主料、輔料、退一步、不打了、開爐（兵器、防具）；每一步的回話與併成一則「打造」。
    - direct：/api/smith_line 的各種 body（空、一半、全、防具、不認得、形狀不對）；直接開爐的成與不成；看火候。
    - secrets：隱藏配方（首位發現與第二個人照著打）；鐵匠順口。
    - divine：神器原品（四階料）、仿品、定名（不合格、撞名、通過、沿用譜名、沒有等著定名的）、以器配招（各種被擋）。
    - half：**前半停在這裡**——一步一步單子打到一半（兵器、防具）、停在防具頁、停在素材頁、神器原品還沒定名、店開著剛看過火候。
    - 後半：resume 接著走（單子接著打、定名、離開）、views（每個人看一遍主畫面與門下頁）、bots（BotRunner 兩個＋整季機器人 visit_smith）、
      season（換季：開著的店與單子跟新角色重來）。
    測試內容的兵器、防具、收購升階本來關著：這一軌在記憶體裡打開（base 與 head 一樣）。"""

    BUYER, GEAR, TRADER, WIZ, DIRECT, SECRET, SECOND, DIV, DIV2 = "鉗甲", "架戊", "秤丁", "砧乙", "爐丙", "鏨己", "鏨庚", "鑄辛", "鑄壬"
    H_DRAFT, H_ARMOR, H_PAGE, H_MAT, H_DIV, H_FURN = "半爐", "半甲", "停頁", "停料", "待名", "火前"
    AWAY = "遠客"
    PLAYERS = [BUYER, GEAR, TRADER, WIZ, DIRECT, SECRET, SECOND, DIV, DIV2, H_DRAFT, H_ARMOR, H_PAGE, H_MAT, H_DIV, H_FURN, AWAY]
    PHASES_FIRST = ["setup", "closed", "shelf", "gearwork", "trade", "wizard", "direct", "secrets", "divine", "half"]
    PHASES_SECOND = ["resume", "views", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        if profile == "test":  # 測試內容的兵器、防具、收購升階關著：打開（兩份程式一樣）
            cf = self.c.config
            cf.weapons.enabled = cf.armor.enabled = cf.economy.sell = cf.economy.upgrade = True

    # ── 小工具 ──

    def town(self) -> str:
        """有「城鎮」標籤的地點（鐵匠鋪開門）：表上第一個。"""
        return next(i for i, loc in sorted(self.c.locations.items()) if "城鎮" in (loc.tags or []))

    def wild(self) -> str:
        return next((i for i, loc in sorted(self.c.locations.items()) if "城鎮" not in (loc.tags or [])), self.town())

    def mats(self, tier: int) -> list[str]:
        return sorted(m.id for m in self.c.materials.values() if m.tier == tier)

    def opts(self, who: str) -> dict[str, dict]:
        """現在眼前的選項（讀 /api/main，不寫進輸出：每一步的回應已經帶主畫面，views 另外逐人寫一遍）。"""
        self.begin()
        r = self.clients[who].get("/api/main")
        try:
            return self.ids(r.json())
        except Exception:  # noqa: BLE001
            return {}

    def live(self, who: str, prefix: str) -> list[str]:
        return [i for i, o in self.opts(who).items() if i.startswith(prefix) and o.get("enabled", True)]

    def press(self, who: str, prefix: str, n: int = 0) -> str | None:
        """主畫面上第 n 顆按得下去、id 以 prefix 開頭的選項按下去；沒有就寫「沒有」。"""
        found = self.live(who, prefix)
        if len(found) <= n:
            emit(f"{who} 沒有 {prefix}", [n, len(found)])
            return None
        self.choose(who, found[n])
        return found[n]

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def line(self, who: str, body) -> None:
        self.call(who, "POST", "/api/smith_line", body)

    def kit(self, who: str, silver: int = SMITHY_SILVER, tiers: tuple[int, ...] = (1, 2, 3), each: int = 3) -> None:
        """銀兩與各階素材（每種 each 個），補滿體力、過了新手期。"""
        def fn(p):
            p.stats["silver"] = silver
            for t in tiers:
                for mid in self.mats(t):
                    p.materials[mid] = p.materials.get(mid, 0) + each
            p.stamina = float(self.c.config.stamina_max)
            p.joined_at = -1.0e9
        self.edit(who, fn)

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟鐵匠鋪有關的那幾格與最新那一則紀錄。"""
        from tianxia import equipment

        p = self.chars.load(who).player
        latest = (self.chars.load(who).journal or [None])[0]
        emit(f"{who} {tag}", {
            "silver": p.stats.get("silver"), "materials": dict(sorted(p.materials.items())),
            "weapon": None if p.weapon is None else p.weapon.model_dump(mode="json"),
            "armor": None if p.armor is None else p.armor.model_dump(mode="json"),
            "rack": [e.model_dump(mode="json") for e in p.rack],
            "picking": p.picking_smith, "page": p.smith_page, "draft": None if p.smith_draft is None else p.smith_draft.model_dump(mode="json"),
            "shop_line": p.shop_line, "shop_clue": p.shop_clue, "smith_rule": p.smith_rule, "furnace": getattr(p, "furnace_ready", None),
            "slots": [(slot, [e.id for e in equipment.in_slot(p, slot)]) for slot in ("weapon", "armor")],
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def rack_ids(self, who: str, slot: str) -> list[str]:
        from tianxia import equipment

        return [e.id for e in equipment.in_slot(self.chars.load(who).player, slot)]

    def arm(self, p) -> None:
        """身上有一門配得上兵器的武學、一門內功（假人與整季機器人才知道要買哪一把、哪一件）。"""
        fist = next((k for k, s in sorted(self.c.skills.items()) if s.kind == "武學" and s.weapon is not None), None)
        inner = next((k for k, s in sorted(self.c.skills.items()) if s.kind == "內功"), None)
        emit("武學與內功", [fist, inner])
        p.member.wugong_id, p.member.wugong_level = fist, 1
        p.member.neigong_id, p.member.neigong_level = inner, 1
        p.arts = [x for x in (fist, inner) if x]

    def originals(self, who: str) -> list[str]:
        """手上（身上、裝備庫）的神器原品與仿品的 id。"""
        p = self.chars.load(who).player
        return [e.id for e in p.rack + [x for x in (p.weapon, p.armor) if x] if getattr(e, "original", False) or getattr(e, "copy_of", None)]

    def database(self, tag: str) -> None:
        """全服登記（神器譜、隱藏配方的首位發現、名字進江湖）：整份資料庫的雜湊。"""
        emit(tag, hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

    # ── 前半 ──

    def setup(self) -> None:
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        for who in self.PLAYERS:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        who = self.BUYER  # 籌備中：每一個入口都擋
        self.choose(who, "act:smith")
        self.choose(who, "smith:buy:劍")
        self.line(who, {"kind": "劍"})
        self.do(who, "smith_forge", {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(who, "smith_sell", {"material": "gang_1", "count": 1})
        self.do(who, "smith_upgrade", {"attribute": "剛", "tier": 2})
        self.do(who, "smith_furnace")
        self.mx(who, "repair_item", {"item": "兵:1"})
        self.mx(who, "temper_item", {"item": "兵:1"})
        self.mx(who, "name_divine", {"weapon": "兵:1", "name": "籌備中"})
        self.mx(who, "bind_art", {"weapon": "兵:1", "art": "x"})
        self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, self.town() if who != self.AWAY else self.wild())
            self.kit(who)
        for who in (self.DIV, self.DIV2, self.H_DIV):  # 四階的料：神器
            self.kit(who, tiers=(4,), each=2)

    def closed(self) -> None:
        """不在城鎮：進門與店面的每一個入口都擋；沒有選單可按的 smith: 也照打。"""
        who = self.AWAY
        self.choose(who, "act:smith")
        self.choose(who, "smith:buy:劍")
        self.choose(who, "smith:repair")
        self.choose(who, "smith:forge")
        self.line(who, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(who, "smith_forge", {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(who, "smith_sell", {"material": "gang_1", "count": 1})
        self.do(who, "smith_upgrade", {"attribute": "剛", "tier": 2})
        self.do(who, "smith_furnace")
        self.mx(who, "repair_item", {"item": "兵:1"})
        self.mx(who, "temper_item", {"item": "甲:1"})
        self.mx(who, "dismantle_many", {"items": ["兵:1", "甲:2"]})
        self.state_of(who, "被擋之後")
        self.place(self.BUYER, self.town())  # 在城鎮但沒進門：店面的入口也擋（選單上沒有鐵匠鋪那一串）
        self.do(self.BUYER, "smith_forge", {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(self.BUYER, "smith_sell", {"material": "gang_1", "count": 1})
        self.mx(self.BUYER, "repair_item", {"item": "兵:1"})
        self.choose(self.BUYER, "smith:page:armor")  # 沒進門就切頁
        self.state_of(self.BUYER, "沒進門")

    def shelf(self) -> None:
        """兵器頁與防具頁：買、修、淬煉、換上、拆解、切頁、離開。"""
        from tianxia.models import WEAPON_KINDS

        who = self.BUYER
        self.press(who, "act:smith")
        self.state_of(who, "進門")
        self.choose(who, "smith:buy:不是兵器")
        for kind in WEAPON_KINDS[:3]:  # 空手買一把就拿在手上，再買的進裝備庫
            self.choose(who, f"smith:buy:{kind}")
        self.state_of(who, "買了三把")
        self.edit(who, lambda p: setattr(p.weapon, "edge", 1) if p.weapon is not None else None)  # 磨損了
        self.press(who, "smith:repair")
        for _ in range(8):  # 淬煉到滿（淬滿了、沒料灰掉）
            self.press(who, "smith:temper")
        self.state_of(who, "修與淬煉之後")
        self.press(who, "smith:wield:")
        self.press(who, "smith:dismantle:")
        self.choose(who, "smith:dismantle-more")  # 灰掉的說明（沒有就被擋）
        self.choose(who, "smith:dismantle:兵:999")
        self.choose(who, "smith:wield:兵:999")
        self.state_of(who, "換上與拆解之後")
        self.choose(who, "smith:page:armor")  # 防具頁
        self.choose(who, "smith:armor-buy:剛")
        self.choose(who, "smith:armor-buy:柔")
        self.choose(who, "smith:armor-buy:不是屬性")
        self.edit(who, lambda p: setattr(p.armor, "edge", 1) if p.armor is not None else None)
        self.choose(who, "smith:armor-repair")
        for _ in range(8):
            self.choose(who, "smith:armor-temper")
        self.press(who, "smith:wield:")
        self.press(who, "smith:dismantle:")
        self.state_of(who, "防具頁之後")
        self.choose(who, "smith:page:material")  # 素材頁、再切回去
        self.choose(who, "smith:page:weapon")
        self.choose(who, "smith:page:nowhere")
        self.edit(who, lambda p: p.stats.__setitem__("silver", 0))  # 沒錢：買、修、淬煉在選單上灰掉，下面三下由 Game.choose 先擋（此刻無法這麼做），沒進包（第 41 批 PM 認定第 9 條）
        self.choose(who, "smith:buy:劍")
        self.choose(who, "smith:repair")
        self.choose(who, "smith:temper")
        self.choose(who, "smith:back")
        self.choose(who, "smith:back")  # 已經離開
        self.state_of(who, "離開之後")

    def gearwork(self) -> None:
        """裝備庫那一列的修與淬煉（走修練頁 /api/menxia/…）：先進門（擋法：鐵匠鋪開著、那一串是眼前的選單）。"""
        who = self.GEAR
        self.press(who, "act:smith")
        for kind in ("劍", "刀", "槍"):
            self.choose(who, f"smith:buy:{kind}")
        self.choose(who, "smith:page:armor")
        for attribute in ("剛", "柔"):
            self.choose(who, f"smith:armor-buy:{attribute}")
        self.choose(who, "smith:armor-buy:快")
        self.state_of(who, "備好")
        weapons_in, armors_in = self.rack_ids(who, "weapon"), self.rack_ids(who, "armor")
        self.edit(who, lambda p: [setattr(e, "edge", 1) for e in p.rack])
        for item in (weapons_in[:1] + armors_in[:1] + ["兵:77", "甲:77", "", "不是裝備"]):
            self.mx(who, "repair_item", {"item": item})
        for item in (weapons_in[:1] + armors_in[:1] + ["兵:77", ""]):
            for _ in range(6):  # 淬到滿
                self.mx(who, "temper_item", {"item": item})
        self.mx(who, "repair_item", {"weapon": weapons_in[0] if weapons_in else "兵:1"})  # 舊網頁送 weapon
        self.state_of(who, "裝備庫修淬之後")
        self.edit(who, lambda p: p.stats.__setitem__("silver", 0))
        for item in (weapons_in[-1:] + armors_in[-1:]):
            self.mx(who, "repair_item", {"item": item})
            self.mx(who, "temper_item", {"item": item})
        self.edit(who, lambda p: p.materials.clear())  # 沒有料
        self.mx(who, "temper_item", {"item": weapons_in[0] if weapons_in else "兵:1"})
        self.state_of(who, "沒錢沒料")
        self.choose(who, "smith:back")
        self.mx(who, "repair_item", {"item": weapons_in[0] if weapons_in else "兵:1"})  # 離開了：被擋
        self.mx(who, "dismantle_many", {"items": weapons_in[1:2] + armors_in[1:2]})  # 批量拆解（不擋地點）
        self.state_of(who, "離開之後")

    def trade(self) -> None:
        """素材頁選單與店面的收購、升階。"""
        who = self.TRADER
        self.press(who, "act:smith")
        self.choose(who, "smith:page:material")
        self.state_of(who, "素材頁")
        for _ in range(4):
            self.press(who, "smith:sell:")
        for _ in range(4):
            self.press(who, "smith:upgrade:")
        self.choose(who, "smith:sell:不是素材")
        self.choose(who, "smith:upgrade:剛")
        self.choose(who, "smith:upgrade:不是屬性:2")
        self.state_of(who, "選單賣升之後")
        mids = self.mats(1)
        for body in ({"material": mids[0], "count": 1}, {"material": mids[0], "count": 2}, {"material": mids[0], "count": 999},
                     {"material": mids[0], "count": 0}, {"material": "不是素材", "count": 1}, {"material": mids[-1]}, {}):
            self.do(who, "smith_sell", body)
        for body in ({"attribute": "剛", "tier": 2}, {"attribute": "柔", "tier": 2}, {"attribute": "剛", "tier": 3}, {"attribute": "剛", "tier": 4},
                     {"attribute": "快", "tier": 1}, {"attribute": "不是屬性", "tier": 2}, {"attribute": "慢", "tier": "x"}, {}):
            self.do(who, "smith_upgrade", body)
        self.state_of(who, "店面賣升之後")
        self.edit(who, lambda p: (p.materials.clear(), p.stats.__setitem__("silver", 0)))
        self.do(who, "smith_sell", {"material": mids[0], "count": 1})
        self.do(who, "smith_upgrade", {"attribute": "剛", "tier": 2})
        self.choose(who, "smith:back")
        self.do(who, "smith_sell", {"material": mids[0], "count": 1})  # 離開了：被擋
        self.state_of(who, "離開之後")

    def wizard(self) -> None:
        """一步一步打造：兵器（挑種類、主料、輔料、退一步、不打了、開爐）與防具；一爐一則「打造」。"""
        who = self.WIZ
        self.press(who, "act:smith")
        self.press(who, "smith:forge")  # 打開單子
        self.state_of(who, "打開單子")
        self.choose(who, "smith:forge-main:gang_1")  # 還沒挑種類就挑主料
        self.press(who, "smith:forge-kind:")
        self.press(who, "smith:forge-undo")  # 退一步
        self.press(who, "smith:forge-kind:", 1)
        self.press(who, "smith:forge-main:")
        self.press(who, "smith:forge-undo")
        self.press(who, "smith:forge-main:", 1)
        self.press(who, "smith:forge-aux:")
        self.state_of(who, "料都齊了")
        self.press(who, "smith:forge-go:")
        self.state_of(who, "開爐之後")
        self.press(who, "smith:forge")  # 再打一爐，這回不打了
        self.press(who, "smith:forge-kind:")
        self.press(who, "smith:forge-cancel")
        self.state_of(who, "不打了之後")
        self.choose(who, "smith:forge-go:劍:gang_1:kuai_1")  # 沒有單子就開爐（直接送 id）：不在選單上，Game.choose 先擋，沒進包（第 41 批 PM 認定第 9 條）
        self.choose(who, "smith:forge-go:劍:不是料:kuai_1")
        self.choose(who, "smith:forge-go:不是兵器:gang_1:kuai_1")
        self.choose(who, "smith:page:armor")  # 防具頁的單子
        self.press(who, "smith:forge")
        self.press(who, "smith:forge-main:")
        self.press(who, "smith:forge-aux:")
        self.press(who, "smith:forge-go:")
        self.state_of(who, "防具開爐之後")
        self.press(who, "smith:forge")
        self.press(who, "smith:forge-main:")
        self.edit(who, lambda p: p.materials.clear())  # 單子開著、料沒了：開爐被擋、單子還在
        self.choose(who, "smith:forge-go:防具:gang_1:kuai_1")
        self.state_of(who, "沒料開爐被擋")
        self.press(who, "smith:forge-cancel")
        self.choose(who, "smith:back")

    def direct(self) -> None:
        """店面：/api/smith_line 的各種 body；直接開爐的成與不成；看火候。"""
        who = self.DIRECT
        for body in ({}, {"kind": "劍"}, {"kind": "劍", "main": "gang_1"}, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"},
                     {"kind": "防具", "main": "gang_1", "aux": "rou_1"}, {"kind": "不是兵器", "main": "gang_1", "aux": "kuai_1"},
                     {"kind": "劍", "main": "不是料", "aux": "kuai_1"}, {"kind": "劍", "main": "gang_4", "aux": "kuai_3"},
                     {"kind": "劍", "main": "gang_1", "aux": "gang_1"}, {"kind": 3, "main": None, "aux": []}, {"kind": ["劍"]}):
            self.line(who, body)
        self.press(who, "act:smith")
        self.line(who, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        for body in ({"kind": "劍", "main": "gang_1", "aux": "kuai_1"}, {"kind": "刀", "main": "gang_1", "aux": "gang_1"},
                     {"kind": "防具", "main": "gang_1", "aux": "rou_1"}, {"kind": "槍", "main": "rou_2", "aux": "man_2"},
                     {"kind": "不是兵器", "main": "gang_1", "aux": "kuai_1"}, {"kind": "劍", "main": "不是料", "aux": "kuai_1"},
                     {"kind": "劍", "main": "gang_4", "aux": "kuai_4"}, {"kind": "劍"}, {}):
            self.do(who, "smith_forge", body)
        self.state_of(who, "直接開爐之後")
        self.edit(who, lambda p: p.stats.__setitem__("silver", 3))
        self.do(who, "smith_forge", {"kind": "劍", "main": "gang_2", "aux": "kuai_2"})  # 銀兩不夠
        self.edit(who, lambda p: p.stats.__setitem__("silver", SMITHY_SILVER))
        for _ in range(3):  # 看火候：一天一次、頭一下看、第二下用掉了
            self.do(who, "smith_furnace")
        self.do(who, "smith_forge", {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(who, "smith_furnace")
        self.state_of(who, "看火候之後")
        self.choose(who, "smith:back")
        self.do(who, "smith_furnace")  # 離開了：被擋

    def recipe_hits(self, n: int = 3) -> list[tuple[str, str, str, str]]:
        """正式內容的隱藏配方（非神器，前 n 個）：（種類或防具, 主料, 輔料, 配方 id）；測試內容沒有就空。"""
        out = []
        for rid, r in sorted(self.c.forge_secrets.items()):
            if getattr(r, "divine", False) or r.main.tier > 3:
                continue
            main = next((m for m in self.mats(r.main.tier) if self.c.materials[m].attribute == r.main.attribute), None)
            aux = next((m for m in self.mats(r.aux.tier) if self.c.materials[m].attribute == r.aux.attribute), None)
            if main and aux:
                out.append(("防具" if r.slot == "armor" else r.kind, main, aux, rid))
            if len(out) >= n:
                break
        return out

    def secrets(self) -> None:
        """隱藏配方：頭一個人打（首位發現）、第二個人照著打、鐵匠順口（花了錢料之後擲）。"""
        hits = self.recipe_hits(4)
        emit("隱藏配方", hits)
        for who in (self.SECRET, self.SECOND):
            self.press(who, "act:smith")
            for kind, main, aux, _rid in hits:
                self.line(who, {"kind": kind, "main": main, "aux": aux})
                self.do(who, "smith_forge", {"kind": kind, "main": main, "aux": aux})
            self.state_of(who, "打了隱藏配方")
            for _ in range(4):  # 多花幾次錢料，鐵匠順口
                self.press(who, "smith:buy:")
            self.state_of(who, "順口")
        self.database("隱藏配方之後")
        self.press(self.SECRET, "smith:forge")  # 單子上開爐的隱藏配方鍵（一步一步）：單子還沒挑種類與料，那一顆不在選單上，Game.choose 先擋，沒進包（第 41 批 PM 認定第 9 條）
        for kind, main, aux, _rid in hits[:1]:
            self.choose(self.SECRET, f"smith:forge-go:{kind}:{main}:{aux}")
        self.state_of(self.SECRET, "單子上的隱藏配方")

    def divine_recipes(self) -> list[tuple[str, str, str, str]]:
        """第一季現世的神器配方（四階料）：（種類或防具, 主料, 輔料, 配方 id）。"""
        out = []
        for rid, r in sorted(self.c.forge_secrets.items(), key=lambda kv: (kv[1].slot != "weapon", kv[0])):  # 兵器的先
            if not getattr(r, "divine", False) or getattr(r, "wave", 1) != 1:
                continue
            main = next((m for m in self.mats(4) if self.c.materials[m].attribute == r.main.attribute), None)
            aux = next((m for m in self.mats(4) if self.c.materials[m].attribute == r.aux.attribute), None)
            if main and aux:
                out.append(("防具" if r.slot == "armor" else r.kind, main, aux, rid))
        return out

    def divine(self) -> None:
        """神器原品（頭一個人）與仿品（第二個人）；定名：沒有等著的、不合格、撞名、通過、沿用譜名；以器配招被擋的各種。"""
        recipes = self.divine_recipes()
        emit("神器配方", recipes)
        who, other = self.DIV, self.DIV2
        for w in (who, other):
            self.press(w, "act:smith")
        for kind, main, aux, _rid in recipes[:2] + recipes[-1:]:  # 兩把兵器、一件防具（防具那一件天池露不夠，沒打成原品；兩兵一甲另由查核走到（第 41 批 PM 認定第 9 條））
            self.line(who, {"kind": kind, "main": main, "aux": aux})
            self.do(who, "smith_forge", {"kind": kind, "main": main, "aux": aux})
        self.state_of(who, "神器原品之後")
        for kind, main, aux, _rid in recipes[:1]:
            self.do(other, "smith_forge", {"kind": kind, "main": main, "aux": aux})  # 已經有人打出來了：仿品
        self.state_of(other, "仿品之後")
        self.database("神器之後")
        ids = self.originals(who)
        emit("神器 id", ids)
        self.mx(who, "name_divine", {"weapon": "兵:999", "name": "不存在"})  # 沒有等著你定名的
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "劍"})  # 不合格（太短、字不對）
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "天下第一神兵天下第一神兵"})
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "鉗甲"})  # 跟角色同名
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "霜刃"})
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "霜刃"})  # 定過了
        self.mx(who, "name_divine", {"weapon": ids[1] if len(ids) > 1 else "兵:2", "name": "霜刃"})  # 撞名
        self.mx(who, "name_divine", {"weapon": ids[1] if len(ids) > 1 else "兵:2", "keep": True})  # 沿用譜名
        self.state_of(who, "定名之後")
        self.database("定名之後")
        for item, art in ((ids[0] if ids else "兵:1", "不是武學"), ("兵:999", "x"), ("", ""), (ids[0] if ids else "兵:1", "")):
            self.mx(who, "bind_art", {"weapon": item, "art": art})  # 被擋的各種
        self.mx(other, "name_divine", {"weapon": "兵:1", "name": "仿品名"})  # 仿品不能定名
        self.mx(other, "bind_art", {"weapon": "兵:1", "art": "x"})
        self.choose(who, "smith:back")
        self.choose(other, "smith:back")

    def half(self) -> None:
        """前半停在這裡：兵器單子打到一半、防具單子打到一半、停在防具頁、停在素材頁、神器原品還沒定名、店開著剛看過火候。"""
        recipes = self.divine_recipes()
        who = self.H_DRAFT
        self.press(who, "act:smith")
        self.press(who, "smith:forge")
        self.press(who, "smith:forge-kind:")
        self.press(who, "smith:forge-main:")
        who = self.H_ARMOR
        self.press(who, "act:smith")
        self.choose(who, "smith:page:armor")
        self.press(who, "smith:forge")
        self.press(who, "smith:forge-main:")
        self.press(who, "smith:forge-aux:")
        who = self.H_PAGE
        self.press(who, "act:smith")
        self.choose(who, "smith:buy:劍")
        self.choose(who, "smith:page:armor")
        self.choose(who, "smith:armor-buy:剛")
        who = self.H_MAT
        self.press(who, "act:smith")
        self.choose(who, "smith:page:material")
        self.press(who, "smith:sell:")
        who = self.H_DIV
        self.press(who, "act:smith")
        for kind, main, aux, _rid in recipes[-2:-1]:
            self.do(who, "smith_forge", {"kind": kind, "main": main, "aux": aux})  # 還沒定名的神器原品（沒人搶先時是原品）
        who = self.H_FURN
        self.press(who, "act:smith")
        self.do(who, "smith_furnace")
        for name in (self.H_DRAFT, self.H_ARMOR, self.H_PAGE, self.H_MAT, self.H_DIV, self.H_FURN):
            self.state_of(name, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        """新程式接著走：單子接著打、停在的頁接著做、神器定名、離開。"""
        self.login_all()
        for name in (self.H_DRAFT, self.H_ARMOR, self.H_PAGE, self.H_MAT, self.H_DIV, self.H_FURN):
            self.state_of(name, "接手時")
        who = self.H_DRAFT
        self.press(who, "smith:forge-aux:")
        self.press(who, "smith:forge-go:")
        self.state_of(who, "接著打完")
        who = self.H_ARMOR
        self.press(who, "smith:forge-undo")
        self.press(who, "smith:forge-aux:", 1)
        self.press(who, "smith:forge-go:")
        self.state_of(who, "接著打完")
        who = self.H_PAGE
        self.choose(who, "smith:armor-repair")
        self.choose(who, "smith:armor-temper")
        self.press(who, "smith:wield:")
        self.choose(who, "smith:page:weapon")
        self.choose(who, "smith:back")
        self.state_of(who, "接著做完")
        who = self.H_MAT
        self.press(who, "smith:sell:")
        self.press(who, "smith:upgrade:")
        self.choose(who, "smith:page:weapon")
        self.choose(who, "smith:back")
        self.state_of(who, "接著做完")
        who = self.H_DIV
        ids = self.originals(who)
        for item in ids[:2]:
            self.mx(who, "name_divine", {"weapon": item, "keep": True})
        self.mx(who, "name_divine", {"weapon": ids[0] if ids else "兵:1", "name": "再定一次"})
        self.state_of(who, "定名之後")
        who = self.H_FURN
        self.do(who, "smith_furnace")  # 看過了：開爐前再看一次
        self.do(who, "smith_forge", {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})
        self.do(who, "smith_furnace")
        self.choose(who, "smith:back")
        self.state_of(who, "接著做完")
        self.database("接手之後")

    def views(self) -> None:
        """每個人看一遍主畫面與門下頁（店面那一頁在店開著時才有）。"""
        for who in self.PLAYERS:
            self.main(who)
            self.call(who, "GET", "/api/menxia")
            self.line(who, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})

    def bots(self) -> None:
        """伺服器假人兩個（BotRunner：bot_policy 的 smith:、act:smith）與整季機器人（bot.visit_smith）；不寫誰是假人。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        for i, name in enumerate(SMITHY_BOTS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            p.location, p.journey = self.town(), None
            p.visited.add(self.town())
            p.stats["silver"] = SMITHY_SILVER
            for mid in self.mats(1) + self.mats(2):
                p.materials[mid] = 4
            p.stamina = float(self.c.config.stamina_max)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.arm(p)
            g.state.pending_event = None  # 開局那一件事先放下（待答的事件在，選單上只有那幾個選項）
            if i == 0:  # 甲已經坐在鐵匠鋪裡（smith: 的分數）；乙在門外（act:smith 的分數）
                from tianxia import equipment

                equipment.open_smith(p, self.c)
            from tianxia import bot_policy

            emit(f"假人 {name} 進場前", {"want": bot_policy._smith_want(g), "art": p.member.wugong_id, "loc": p.location,
                                         "options": [o.id for o in g.options(odds=False, tick=False)][:14]})
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(SMITHY_BOTS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_SMITHY_TICKS", "14"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in SMITHY_BOTS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"silver": p.stats.get("silver"), "weapon": None if p.weapon is None else p.weapon.model_dump(mode="json"),
                                  "armor": None if p.armor is None else p.armor.model_dump(mode="json"), "rack": len(p.rack),
                                  "picking": p.picking_smith, "draft": None if p.smith_draft is None else p.smith_draft.model_dump(mode="json"),
                                  "titles": dict(sorted(Counter(e.title.partition("・")[0] for e in s.journal).items())),
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        # 打分數挑選項（bot_policy.pick：smith: 的分數與 act:smith 的分數，不經 take_turn 前面那一串別的事）：甲坐在店裡、乙在門外，各按到不想按為止
        for k, (name, inside) in enumerate((("匠丁", True), ("匠戊", False))):
            self.begin()
            drv = Game.new(self.c, name, rng=random.Random(40 + k), world=self.world, graduated=True)
            drv.client = None
            drv.sync(CLOCK[0])
            p = drv.state.player
            p.location, p.journey = self.town(), None
            p.stats["silver"] = SMITHY_SILVER
            for mid in self.mats(1) + self.mats(2) + self.mats(4):
                p.materials[mid] = 4
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.arm(p)
            drv.state.pending_event = None
            if inside:
                from tianxia import equipment

                equipment.open_smith(p, self.c)
            profile = BotProfile(personality="普通", seed=80 + k, faction=None, season_number=self.world.get_season_number())
            trace = []
            for step in range(24):
                self.begin()
                options = [o for o in drv.options(odds=False, tick=False) if o.enabled and o.id.startswith(("smith:", "act:smith"))]  # 只留鐵匠鋪的選項
                if step == 0:
                    emit(f"假人 {name} 分數", [[o.id, bot_policy.score(drv, o, profile)] for o in options if o.id.startswith(("smith:", "act:smith"))])
                choice = bot_policy.pick(drv, options, profile, random.Random(step))
                trace.append(choice)
                if choice is None:
                    break
                drv.choose(choice)
            emit(f"假人 {name} 挑的", trace)
            emit(f"假人 {name} 之後", {"silver": p.stats.get("silver"), "weapon": None if p.weapon is None else p.weapon.model_dump(mode="json"),
                                        "armor": None if p.armor is None else p.armor.model_dump(mode="json"),
                                        "rack": [e.model_dump(mode="json") for e in p.rack], "picking": p.picking_smith,
                                        "journal": [[e.title, list(e.lines)[:3]] for e in drv.state.journal[:5]]})
        self.begin()
        solo = Game.new(self.c, "匠丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        p = solo.state.player
        p.location, p.journey = self.town(), None
        p.stats["silver"] = SMITHY_SILVER
        for mid in self.mats(1) + self.mats(2) + self.mats(4):
            p.materials[mid] = 4
        p.tutorial_step = len(self.c.tutorial.steps)
        self.arm(p)
        solo.state.pending_event = None  # 開局那一件事先放下（visit_smith 有事件待答就不進門）
        emit("整季機器人 進門前", {"pending": bool(solo.state.pending_event), "loc": p.location, "journey": p.journey is not None,
                                "want": bot.smith_want(solo), "forge": bot.forge_ready(solo)})
        bot.visit_smith(solo)  # 整季機器人：進鐵匠鋪看一眼（換買修打淬）
        emit("整季機器人 visit_smith", {"silver": p.stats.get("silver"), "weapon": None if p.weapon is None else p.weapon.model_dump(mode="json"),
                                        "armor": None if p.armor is None else p.armor.model_dump(mode="json"),
                                        "rack": [e.model_dump(mode="json") for e in p.rack], "picking": p.picking_smith,
                                        "journal": [[e.title, list(e.lines)[:3]] for e in solo.state.journal[:6]]})
        bot.keep_book_names(solo)  # 這一軌只打到仿品；沿用譜名由上面 divine 那一段的 /api/menxia/name_divine keep 走到（第 41 批 PM 認定第 9 條）
        emit("整季機器人 沿用譜名", [e.name for e in p.rack])

    def season(self) -> None:
        """收季、開下一季：開著的店與單子跟新角色重來。"""
        self.do(ADMIN, "end_season")
        for who in (self.WIZ, self.DIRECT, self.H_DRAFT):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.H_DRAFT, self.H_ARMOR, self.BUYER):
            self.state_of(who, "換季之後（動作前的存檔）")
            self.main(who)
            self.choose(who, "smith:back")
            self.state_of(who, "換季之後（動作後）")
        self.line(self.BUYER, {"kind": "劍", "main": "gang_1", "aux": "kuai_1"})


# 改一個字（selftest）：一步一步打造「退一步」那一句（搬之前在 tianxia/smithing.py、之後在 tianxia/features/smithy/smithing.py；第 2 項是舊名的檔，
# 搬的人照實際的檔名改這一個字串）。抓到的地方：砧乙挑種類之後按「上一步」
register_track("smithy", SmithyScenario, (("tianxia/features/smithy/smithing.py",),
                                          ('UNDONE = "退回一步。"', 'UNDONE = "退回一步！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "outlets", "peers",
                       "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts",
                       "travel", "zhuan"))


# 鐵匠鋪那一軌改一個字的那一句（UNDONE，# smithy 那一段登記的）這一批跟著鐵匠鋪的常數搬進了 tianxia/core/smith_base.py：檔清單前面補上
# 新的那一處（_mutant 照順序找、哪一處剛好一次就改哪一處；舊的樹沒有這個檔，照舊落到後面兩處）。只動 selftest，compare 不讀 MUTATIONS。
_smithy_files, _smithy_line = MUTATIONS["smithy"]
MUTATIONS["smithy"] = (("tianxia/core/smith_base.py", *_smithy_files), _smithy_line)
del _smithy_files, _smithy_line
