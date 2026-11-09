"""same_behavior 一軌一檔：gear（這一檔登記 gear）。"""
from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, db_text, emit, register_track

# ═══════════════════════════ gear：裝備一軌（全部拆包第 42 批，dev/gear-1） ═══════════════════════════
# 裝備（馬市的買、餵、換上，修練頁 /api/menxia/{wield,dismantle,feed,dismantle_many}，寄放補送，名將贈禮與本命兵器，神器譜 /api/boards、/api/board_card）：
# Game 上 13 個方法與 tianxia/signature_arms.py 之後搬進 tianxia/features/gear/（計畫 docs/superpowers/plans/2026-11-07-裝備包-第1批.md）。
# 角色的名字都是原創的（第 22 批 PM 認定第 3 條）。

GEAR_BOTS = ["牧甲", "牧乙"]
GEAR_SILVER = 6000
GEAR_RACK_CAP = 5  # 裝備庫幾格：預設 100 格，要「裝備庫滿了」得塞一百件；這一軌在記憶體裡壓成 5（兩份程式一樣）
# 測試內容沒有 gear.json（沒有寶物、名駒、贈禮、本命兵器）：在記憶體裡補一份，人物用測試內容的（兩份程式一樣）
GEAR_TEST_BOOK = {
    "treasures": {
        "gt_a": {"id": "gt_a", "name": "銅鈴匣", "effect": "cultivate", "pool": False},
        "gt_b": {"id": "gt_b", "name": "墨玉扣", "effect": "insight", "pool": False},
        "gt_c": {"id": "gt_c", "name": "青蓑", "effect": "win_material", "pool": False},
        "gt_d": {"id": "gt_d", "name": "黃麻鞍", "effect": "audience", "pool": False},
    },
    "steeds": {"gs_a": {"id": "gs_a", "name": "流雲駒", "quality": "上品"}, "gs_b": {"id": "gs_b", "name": "追星駒", "quality": "中品"}},
    "gifts": [
        {"character": "mate", "gear": "gt_a"}, {"character": "scholar", "gear": "gt_b"}, {"character": "hero", "gear": "gt_c"},
        {"character": "captain", "gear": "gt_d"}, {"character": "friend", "gear": "gs_a"}, {"character": "pupil", "gear": "gs_b"},
    ],
    "signature_arms": [
        {"character": "mate", "name": "斷水刀", "kind": "刀", "attribute": "剛"},
        {"character": "hero", "name": "寒枝劍", "kind": "劍", "attribute": "柔"},
        {"character": "scholar", "name": "鳴沙槍", "kind": "槍", "attribute": "剛"},
        {"character": "captain", "name": "霜痕棍", "kind": "棍", "attribute": "柔"},
    ],
}


class GearScenario(Scenario):
    """裝備一軌（全部拆包第 42 批；--track gear，自己一個資料庫）。每一步都存回應；分段：
    - setup：籌備中（管理者還沒開季）只證到批量拆解被擋（@not_while_preparing）；進馬市、買、換上、餵、拆解也各按一下，但都沒走到
      （審查實測），不算證明「籌備中照常做」；開季、補體力、擺位置，給銀兩與一階素材。
    - closed：不在馬市的人按進門、買、餵、換上、離開；在馬市沒進門的人按買（FB-195：選單上沒有，回為什麼不成或「情形變了」）。
    - stall：進門、買得起與買不起、已經有馬時新的進裝備庫、裝備庫滿了、餵（不餓、沒素材、餵飽）、換上（裝備庫那一匹、不存在的）、離開兩次。
    - bench：修練頁 /api/menxia/{wield,dismantle,feed,dismantle_many}：兵、甲、騎、寶四種 id，空 id、不存在的、坐騎寶物不能拆、路上換坐騎被擋、閉關中換寶物
      （路辛約 2 分鐘就到了：路上「餵被擋」那一支沒走到，審查實測）。
    - held：裝備庫滿時寄放的東西，sync 補送（先滿著補不進去、騰出空位再補）。
    - gifts：名將贈禮與本命兵器（情誼經 choose 到門檻）：當面交給你、託人送來、每位名將每季全服一人、名駒；答覆事件（放手一搏）那一條路也打一下。
    - fight：挑戰本人打贏兩次（還不夠）；內容沒有大勢人物的（測試內容）寫「沒有」。
    - boards：/api/boards 的神器譜與 /api/board_card（神器譜每一筆、不存在的、缺參數）。
    - half：**前半停在這裡**——馬市開著剛買了一匹、坐騎餓了還沒餵、情誼差一下到贈禮門檻、寄放裡有東西等補送、打贏本人兩次（第三次由後半打）。
    - 後半：resume 接著走、views（每個人看一遍主畫面與門下頁與神器譜）、bots（BotRunner 兩個〔牧甲坐在馬市、牧乙在門外；牧乙沒進馬市，
      act:market 的假人路徑靠 bot_policy.pick 驅動的牧丁與整季機器人，審查實測〕＋bot_policy.pick 兩個＋
      整季機器人 visit_market、feed_mount、wear_better、advance 補送寄放）、season（換季：神器譜跨季；收季前沒人坐在馬市裡，
      「開著的馬市跟新角色重來」沒走到，換季後照樣按一下 market:back，審查實測）。
    測試內容的兵器、防具、坐騎、寶物本來關著，馬市的標籤也沒有：這一軌在記憶體裡打開、補上（base 與 head 一樣）。"""

    SHOPPER, POOR, HORSED, FULLRACK, FEEDER, AWAY = "駒甲", "駒乙", "駒丙", "駒丁", "駒戊", "駒己"
    BENCH, ROAD, SECLUDED, PREP = "列庚", "路辛", "關壬", "備未"
    HELD, NEAR, FAR, TAKEN, STEED, FIGHT = "寄癸", "贈子", "贈丑", "贈辰", "贈寅", "贈卯"
    H_BUY, H_FEED, H_NEAR, H_HELD, H_FIGHT = "半辰", "半巳", "半午", "半未", "半申"
    PLAYERS = [SHOPPER, POOR, HORSED, FULLRACK, FEEDER, AWAY, BENCH, ROAD, SECLUDED, PREP, HELD, NEAR, FAR, TAKEN, STEED, FIGHT,
               H_BUY, H_FEED, H_NEAR, H_HELD, H_FIGHT]
    PHASES_FIRST = ["setup", "closed", "stall", "bench", "held", "gifts", "fight", "boards", "half"]
    PHASES_SECOND = ["resume", "views", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        cf = self.c.config
        if profile == "test":  # 測試內容四欄都關、沒有馬市、沒有 gear.json：打開、補上（兩份程式一樣）
            from tianxia.models import GearBook

            cf.weapons.enabled = cf.armor.enabled = cf.mounts.enabled = cf.treasures.enabled = True
            town = self.c.locations["town"]
            if "馬市" not in (town.tags or []):
                town.tags = [*(town.tags or []), "馬市"]
            if not self.c.gear.gifts:
                self.c.gear = GearBook.model_validate(GEAR_TEST_BOOK)
        cf.weapons.rack_cap = GEAR_RACK_CAP

    # ── 小工具 ──

    def begin(self) -> None:
        """每個請求前把榜單的快取清掉（server.BOARDS_CACHE 是行程裡的快取：前半＋後半是兩個行程，不清的話整段與切開的榜單新舊不同）。"""
        super().begin()
        self.server.BOARDS_CACHE.clear()

    def market(self) -> str:
        """有「馬市」標籤的地點：表上第一個（測試內容是 __init__ 補上的那一處）。"""
        return next(i for i, loc in sorted(self.c.locations.items()) if "馬市" in (loc.tags or []))

    def wild(self) -> str:
        market = self.market()
        return next((i for i, loc in sorted(self.c.locations.items()) if i != market and "馬市" not in (loc.tags or [])), market)

    def mats(self, tier: int) -> list[str]:
        return sorted(m.id for m in self.c.materials.values() if m.tier == tier)

    def opts(self, who: str) -> dict[str, dict]:
        self.begin()
        r = self.clients[who].get("/api/main")
        try:
            return self.ids(r.json())
        except Exception:  # noqa: BLE001
            return {}

    def press(self, who: str, option_id: str, tag: str = "") -> None:
        """按選單上的一顆（灰著、不在選單上也照按，被擋的那一句也要寫出來）。"""
        have = self.opts(who).get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    def kit(self, who: str, silver: int = GEAR_SILVER, each: int = 3) -> None:
        def fn(p):
            p.stats["silver"] = silver
            for mid in self.mats(1):
                p.materials[mid] = each
            p.stamina = float(self.c.config.stamina_max)
            p.joined_at = -1.0e9
        self.edit(who, fn)

    def stock(self, who: str, weapons_n: int = 0, armors_n: int = 0, horses_n: int = 0, treasures_n: int = 0, worn: bool = False) -> None:
        """身上與裝備庫擺東西：worn 先把四欄穿滿，再往裝備庫放這幾件。"""
        from tianxia import armor, mounts, treasures, weapons
        from tianxia.models import WEAPON_KINDS

        tid = next(iter(sorted(self.c.gear.treasures)), None)

        def fn(state):
            p = state.player
            if worn:
                p.weapon = weapons.new_weapon(state, name="試手劍", kind=WEAPON_KINDS[0], attribute="剛", tier=1, quality="中品")
                p.armor = armor.new_armor(state, name="試手甲", attribute="剛", tier=1, quality="中品")
                p.mount = mounts.new_mount(state, name="試手馬", tier=2, quality="中品")
                if tid is not None:
                    p.treasure = treasures.new_treasure(state, self.c, tid)
            for k in range(weapons_n):
                p.rack.append(weapons.new_weapon(state, name=f"備用兵{k}", kind=WEAPON_KINDS[k % 3], attribute="剛", tier=1, quality="下品"))
            for k in range(armors_n):
                p.rack.append(armor.new_armor(state, name=f"備用甲{k}", attribute="柔", tier=1, quality="下品"))
            for k in range(horses_n):
                p.rack.append(mounts.new_mount(state, name=f"備用馬{k}", tier=1, quality="下品"))
            if tid is not None:
                for k in range(treasures_n):
                    p.rack.append(treasures.new_treasure(state, self.c, tid))
        self.edit_state(who, fn)

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟裝備有關的那幾格與最新那一則紀錄。"""
        s = self.chars.load(who)
        p = s.player
        latest = (s.journal or [None])[0]
        dump = lambda e: None if e is None else e.model_dump(mode="json")  # noqa: E731
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": p.journey is not None, "silver": p.stats.get("silver"), "mats": dict(sorted(p.materials.items())),
            "weapon": dump(p.weapon), "armor": dump(p.armor), "mount": dump(p.mount), "treasure": dump(p.treasure),
            "rack": [dump(e) for e in p.rack], "held": [dump(e) for e in p.held_gear],
            "picking": p.picking_market, "shop_line": p.shop_line, "shop_clue": p.shop_clue, "hunger_warned": p.hunger_warned,
            "aff": dict(sorted(p.affinities.items())), "wins": dict(sorted(p.figure_wins.items())), "stamina": p.stamina,
            "annals": [[a.kind, a.text] for a in p.annals][-3:],
            "latest": [dump(e) for e in (s.journal or [])[:3]] if latest is not None else None,
        })

    def world_gear(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"世界 {tag}", {"gifts": dict(sorted(w.general_gifts.items())),
                            "arms": {k: v.model_dump(mode="json") for k, v in sorted(w.signature_arms.items())},
                            "rumors": [r.text for r in w.rumors][-3:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def cast(self) -> tuple[list[str], list[str]]:
        """贈禮的人物：送寶物的（內容裡的先後）、送名駒的。"""
        book = self.c.gear
        steeds = set(book.steeds)
        return ([g.character for g in book.gifts if g.gear not in steeds], [g.character for g in book.gifts if g.gear in steeds])

    def where(self, cid: str) -> str:
        """此刻在哪裡找得到他（同 Game._people_here 的所在：人物表上的人照此刻的所在，其餘 recruit_at、talk_at）。"""
        from tianxia import figures
        from tianxia.engine import Game

        self.begin()
        state = self.chars.load(self.PREP)
        state.world = self.world.get_season()
        game = Game(self.c, state, world=self.world)
        placed = figures.placed_characters(game.state, self.c)
        ch = self.c.characters[cid]
        found = placed.get(cid) if cid in placed else (ch.recruit_at or ch.talk_at)
        return found if found in self.c.locations else self.wild()

    def elsewhere(self, cid: str) -> str:
        here = self.where(cid)
        return self.market() if here != self.market() else self.wild()

    def befriend(self, who: str, cid: str, value: int) -> None:
        self.edit(who, lambda p: p.affinities.__setitem__(cid, value))

    def touch(self, who: str) -> None:
        """做一件不要緊的事（choose 最後會問名將贈禮與本命兵器）：先離開店、再試對話、進店，最後才拿第一顆能按的。"""
        enabled = [i for i, o in self.opts(who).items() if o.get("enabled", True)]
        for pre in ("market:back", "smith:back", "bounty:back", "talk:", "act:smith", "act:market", "act:halt", "act:rest"):
            found = next((i for i in enabled if i.startswith(pre)), None)
            if found:
                emit(f"{who} 做的事", found)
                self.choose(who, found)
                return
        emit(f"{who} 做的事", enabled[:1])
        if enabled:
            self.choose(who, enabled[0])

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
        who = self.PREP  # 籌備中：只證到批量拆解擋（@not_while_preparing）；馬市、買、換上、餵、拆解也按，但沒走到（審查實測，照實記）
        self.choose(who, "act:market")
        self.choose(who, "market:buy")
        self.mx(who, "wield", {"weapon": "兵:1"})
        self.mx(who, "feed")
        self.mx(who, "dismantle", {"weapon": "兵:1"})
        self.mx(who, "dismantle_many", {"items": ["兵:1", "甲:2"]})
        self.call(who, "GET", "/api/boards")
        self.call(who, "GET", "/api/board_card?board=%E7%A5%9E%E5%99%A8&season=1&ref=x")
        self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, self.wild() if who in (self.AWAY, self.ROAD) else self.market())
            self.kit(who)
        self.world_gear("開場")

    def closed(self) -> None:
        """不在馬市：進門、買、餵、換上、離開都被擋；在馬市沒進門：選單上沒有 market: 那一串，按了回為什麼不成。"""
        who = self.AWAY
        for oid in ("act:market", "market:buy", "market:feed", "market:wield:騎:1", "market:back"):
            self.choose(who, oid)
        self.mx(who, "feed")
        self.state_of(who, "被擋之後")
        who = self.SHOPPER
        for oid in ("market:buy", "market:feed", "market:wield:騎:1", "market:back", "market:bogus"):
            self.press(who, oid, "沒進門")
        self.state_of(who, "沒進門")

    def stall(self) -> None:
        """馬市：進門、買、再買、沒錢、餵、換上、離開。"""
        who = self.SHOPPER
        self.press(who, "act:market")
        self.state_of(who, "進門")
        self.press(who, "market:buy", "買得起")
        self.state_of(who, "買了第一匹")
        self.press(who, "market:buy", "已經有馬")
        self.state_of(who, "買了第二匹（進裝備庫）")
        self.press(who, "market:feed", "不餓")
        self.edit(who, lambda p: setattr(p.mount, "edge", 30))
        self.edit(who, lambda p: p.materials.clear())
        self.press(who, "market:feed", "沒素材")
        self.kit(who, silver=GEAR_SILVER)
        self.press(who, "market:feed", "餵飽")
        self.state_of(who, "餵過之後")
        rack_horses = [e.id for e in self.chars.load(who).player.rack if e.slot == "mount"]
        for mid in (rack_horses[:1] or ["騎:1"]) + ["騎:999", "騎:999"]:
            self.press(who, f"market:wield:{mid}", "換上")
        self.press(who, "market:wield:", "空 id")
        self.state_of(who, "換上之後")
        self.press(who, "market:back")
        self.press(who, "market:back", "已經離開")
        self.state_of(who, "離開之後")
        who = self.POOR  # 買不起：鈕灰著寫還差多少
        self.edit(who, lambda p: p.stats.__setitem__("silver", 10))
        self.press(who, "act:market")
        self.press(who, "market:buy", "買不起")
        self.state_of(who, "買不起之後")
        self.press(who, "market:back")
        who = self.HORSED  # 已經有馬：新的進裝備庫
        self.stock(who, horses_n=1, worn=True)
        self.press(who, "act:market")
        self.press(who, "market:buy", "身上有馬")
        self.state_of(who, "身上有馬再買")
        self.press(who, "market:back")
        who = self.FULLRACK  # 裝備庫滿了
        self.stock(who, weapons_n=GEAR_RACK_CAP - 1, horses_n=1, worn=True)
        self.press(who, "act:market")
        self.press(who, "market:buy", "裝備庫滿了")
        self.press(who, "market:back")
        who = self.FEEDER
        self.stock(who, worn=True)
        self.edit(who, lambda p: setattr(p.mount, "edge", 10))
        self.press(who, "act:market")
        self.press(who, "market:feed", "餓了")
        self.press(who, "market:feed", "吃飽了")
        self.press(who, "market:back")
        self.state_of(who, "餵完離開")

    def bench(self) -> None:
        """修練頁：換上、拆解、餵、批量拆解（兵、甲、騎、寶四種 id；路上、閉關中）。"""
        who = self.BENCH
        self.stock(who, weapons_n=2, armors_n=1, horses_n=1, treasures_n=1, worn=True)
        self.state_of(who, "備好")
        p = self.chars.load(who).player
        ids = {slot: [e.id for e in p.rack if e.slot == slot] for slot in ("weapon", "armor", "mount", "treasure")}
        for slot in ("weapon", "armor", "mount", "treasure"):
            for item in ids[slot][:1]:
                self.mx(who, "wield", {"weapon": item})
        for item in ("兵:999", "", "不是裝備"):
            self.mx(who, "wield", {"weapon": item})
        self.mx(who, "wield")  # 沒給鍵
        self.mx(who, "wield", {"item": ids["weapon"][0] if ids["weapon"] else "兵:1"})  # 給了別的鍵：讀的是 weapon，當空 id
        self.state_of(who, "換上之後")
        p = self.chars.load(who).player
        ids = {slot: [e.id for e in p.rack if e.slot == slot] for slot in ("weapon", "armor", "mount", "treasure")}
        for slot in ("mount", "treasure", "weapon", "armor"):  # 坐騎寶物不能拆
            for item in ids[slot][:1]:
                self.mx(who, "dismantle", {"weapon": item})
        for item in ("兵:999", ""):
            self.mx(who, "dismantle", {"weapon": item})
        self.edit(who, lambda p: setattr(p.mount, "edge", 20))
        self.mx(who, "feed")
        self.mx(who, "feed")
        self.state_of(who, "拆解與餵之後")
        p = self.chars.load(who).player
        every = [e.id for e in p.rack] + ["兵:999"]
        self.mx(who, "dismantle_many", {"items": []})
        self.mx(who, "dismantle_many", {"items": "兵:1"})
        self.mx(who, "dismantle_many")
        self.mx(who, "dismantle_many", {"items": every})
        self.state_of(who, "批量拆解之後")
        who = self.ROAD  # 路上：換坐騎被擋，換寶物不擋；約 2 分鐘就到了，「餵被擋」那一支沒走到（審查實測）
        self.stock(who, horses_n=1, treasures_n=1, worn=True)
        first = next((i for i in self.opts(who) if i.startswith("move:")), None)
        emit(f"{who} 出發", first)
        if first:
            self.choose(who, first)
        p = self.chars.load(who).player
        for slot in ("mount", "treasure"):
            for item in [e.id for e in p.rack if e.slot == slot][:1]:
                self.mx(who, "wield", {"weapon": item})
        self.mx(who, "feed")
        self.mx(who, "dismantle_many", {"items": [e.id for e in p.rack]})
        self.state_of(who, "路上")
        who = self.SECLUDED  # 閉關中：寶物照換，餵被擋
        self.stock(who, horses_n=1, treasures_n=1, worn=True)
        self.edit(who, lambda p: setattr(p, "busy_until", 4.0e9))
        p = self.chars.load(who).player
        for slot in ("treasure", "mount"):
            for item in [e.id for e in p.rack if e.slot == slot][:1]:
                self.mx(who, "wield", {"weapon": item})
        self.mx(who, "feed")
        self.state_of(who, "閉關中")

    def held(self) -> None:
        """寄放：裝備庫滿時重賞寄放，sync 補送（滿著補不進去；騰出空位再補，閉關中也補）。"""
        from tianxia import mounts, treasures

        who = self.HELD
        tid = next(iter(sorted(self.c.gear.treasures)), None)

        def fn(state):
            p = state.player
            p.held_gear.append(mounts.new_mount(state, name="重賞馬", tier=2, quality="中品"))
            if tid is not None:
                p.held_gear.append(treasures.new_treasure(state, self.c, tid))
        self.stock(who, weapons_n=GEAR_RACK_CAP, worn=True)
        self.edit_state(who, fn)
        self.state_of(who, "寄放著、庫是滿的")
        self.main(who)  # sync：滿著補不進去
        self.state_of(who, "滿著補不進去")
        self.mx(who, "dismantle_many", {"items": [e.id for e in self.chars.load(who).player.rack[:3]]})
        self.edit(who, lambda p: setattr(p, "busy_until", 4.0e9))  # 閉關中也補
        self.main(who)
        self.state_of(who, "騰出空位之後補送")

    def gifts(self) -> None:
        """名將贈禮與本命兵器：情誼到門檻，做一件事（choose 最後問）；當面、託人送來、名駒、同一位名將已經送過人。"""
        tre, ste = self.cast()
        emit("贈禮的人物", {"寶物": tre, "名駒": ste, "本命": [a.character for a in self.c.gear.signature_arms]})
        if len(tre) < 2 or not ste:
            emit("這份內容沒有那麼多贈禮", None)
            return
        near, far, steed = tre[0], tre[1], ste[0]
        self.place(self.NEAR, self.where(near))  # 他就在身邊：當面交給你
        self.befriend(self.NEAR, near, 85)
        self.state_of(self.NEAR, "情誼到了")
        self.touch(self.NEAR)
        self.state_of(self.NEAR, "當面")
        self.place(self.FAR, self.elsewhere(far))  # 他不在：託人送來
        self.befriend(self.FAR, far, 85)
        self.touch(self.FAR)
        self.state_of(self.FAR, "託人送來")
        self.place(self.TAKEN, self.where(near))  # 同一位名將這一季已經送過人
        self.befriend(self.TAKEN, near, 90)
        self.touch(self.TAKEN)
        self.state_of(self.TAKEN, "已經送過人")
        self.place(self.STEED, self.elsewhere(steed))  # 名駒（情誼在本命兵器的門檻以下，只有名駒）
        self.befriend(self.STEED, steed, 65)
        self.touch(self.STEED)
        self.state_of(self.STEED, "名駒")
        self.world_gear("贈禮之後")
        # 答覆事件（放手一搏）那一條路也問名將贈禮：沒有待答的事件時只回一句；有的話照走
        self.call(self.NEAR, "POST", "/api/answer", {"text": "我自有辦法"})
        self.call(self.FAR, "POST", "/api/answer", {"text": ""})

    def revive(self) -> None:
        """打贏他、他敗走了：管理者先救回（不然下一個人按不到挑戰鈕）。沒有帶本命兵器的大勢人物（測試內容）什麼都不做。"""
        for arm in self.c.gear.signature_arms:
            if arm.figure and arm.figure in self.c.figures:
                self.do(ADMIN, "revive_figure", {"id": arm.figure})

    def foe(self):
        """帶本命兵器的大勢人物（內容寫了 figure 的那位）此刻在哪、哪個陣營的人挑得了他；沒有（測試內容）是 None。"""
        from tianxia import figures
        from tianxia.engine import Game

        arms = [a for a in self.c.gear.signature_arms if a.figure]
        if not arms or not self.c.figures:
            return None
        self.begin()
        state = self.chars.load(self.PREP)
        state.world = self.world.get_season()
        game = Game(self.c, state, world=self.world)
        for arm in arms:
            fig = self.c.figures.get(arm.figure)
            now = figures.state_of(game.state, self.c, arm.figure)
            if fig is None or not figures.can_challenge(game.state, self.c, arm.figure):
                continue
            side = next((f.id for f in self.c.scenario.factions if f.id != fig.faction and f.id in ("guan", "huang")), None)
            if side is not None:
                return arm.figure, now.location, side
        return None

    def fight(self) -> None:
        """挑戰本人打贏兩次（還不夠 signature_wins 次，沒有本命兵器）。"""
        found = self.foe()
        emit("本命兵器的大勢人物", found)
        if found is None:
            emit("這份內容沒有帶本命兵器的大勢人物（測試內容沒有大勢人物）：走不到", None)
            return
        fid, loc, side = found
        who = self.FIGHT
        self.place(who, loc, side)
        for k in range(2):
            if k:
                self.revive()
            self.edit(who, lambda p: p.snubbed_until.clear())
            self.kit(who)
            with self.winning():
                self.press(who, f"act:challenge:{fid}", f"打贏第 {k + 1} 次")
            self.state_of(who, f"打贏 {k + 1} 次之後")
        self.world_gear("打贏之後")

    def boards(self) -> None:
        """神器譜與榜單卡：/api/boards、/api/board_card（神器譜每一筆、不存在的、缺參數）。"""
        from urllib.parse import urlencode

        status, data = self.call(self.NEAR, "GET", "/api/boards")
        book = [b for b in (data.get("boards") or []) if b.get("id") == "神器"] if isinstance(data, dict) else []
        rows = book[0]["book"] if book else []
        emit("神器譜幾筆", len(rows))
        for row in rows[:4]:
            self.call(self.NEAR, "GET", "/api/board_card?" + urlencode({"board": "神器", "season": row["season"], "ref": row["ref"]}))
        for query in ({"board": "神器", "season": 1, "ref": "不存在"}, {"board": "神器", "season": 0, "ref": "本命|nobody"}, {"board": "神器"}, {"board": "不是榜"}):
            self.call(self.FAR, "GET", "/api/board_card?" + urlencode(query))

    def half(self) -> None:
        """**前半停在這裡**：馬市開著剛買了一匹、坐騎餓了還沒餵、情誼差一下到贈禮門檻、寄放裡有東西等補送、打贏本人兩次。"""
        from tianxia import mounts, treasures

        tre, ste = self.cast()
        who = self.H_BUY  # 馬市開著，剛買了一匹（身上有馬、庫裡有一匹，店還開著）
        self.press(who, "act:market")
        self.press(who, "market:buy")
        self.state_of(who, "半途：剛買一匹")
        who = self.H_FEED  # 坐騎餓了還沒餵
        self.stock(who, worn=True)
        self.edit(who, lambda p: setattr(p.mount, "edge", 25))
        self.state_of(who, "半途：餓了")
        if len(tre) >= 4:
            who = self.H_NEAR  # 情誼差一下到贈禮門檻（60）
            self.place(who, self.where(tre[3]))
            self.befriend(who, tre[3], self.c.config.treasures.gift_affinity - 1)
            self.touch(who)
            self.state_of(who, "半途：差一下")
            who = self.H_HELD  # 重賞寄放著、裝備庫是滿的
            tid = next(iter(sorted(self.c.gear.treasures)), None)
            self.stock(who, weapons_n=GEAR_RACK_CAP, worn=True)
            self.place(who, self.elsewhere(tre[2]))
            self.befriend(who, tre[2], 85)
            self.touch(who)  # 名將贈禮 + 本命兵器：庫是滿的，寄放
            self.state_of(who, "半途：寄放著")
        else:
            emit("這份內容贈禮不夠四位", None)
        self.revive()
        found = self.foe()
        if found is not None:
            fid, loc, side = found
            who = self.H_FIGHT  # 打贏兩次（還差一次）：第三次由後半打
            self.place(who, loc, side)
            self.edit(who, lambda p: p.figure_wins.__setitem__(fid, self.c.config.weapons.signature_wins - 2))
            self.edit(who, lambda p: p.snubbed_until.clear())
            with self.winning():
                self.press(who, f"act:challenge:{fid}", "打贏")
            self.state_of(who, "半途：打贏本人 (n-1) 次")
        self.world_gear("半途")
        self.database("前半結束")

    def database(self, tag: str) -> None:
        emit(tag, hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

    # ── 後半 ──

    def resume(self) -> None:
        """新程式接著走：店還開著的繼續買與離開、餓了的馬餵、情誼補到門檻、騰出空位補送、第三次打贏本人。"""
        self.login_all()
        tre, ste = self.cast()
        who = self.H_BUY
        self.press(who, "market:buy", "接著買（進庫）")
        self.press(who, "market:feed", "接著餵")
        self.press(who, "market:back")
        self.state_of(who, "接著做完")
        who = self.H_FEED
        self.mx(who, "feed")
        self.press(who, "act:market")
        self.press(who, "market:feed", "已經餵過")
        self.press(who, "market:back")
        self.state_of(who, "餵完")
        if len(tre) >= 4:
            who = self.H_NEAR
            self.befriend(who, tre[3], self.c.config.treasures.gift_affinity)
            self.touch(who)
            self.state_of(who, "接著到門檻")
            who = self.H_HELD
            self.mx(who, "dismantle_many", {"items": [e.id for e in self.chars.load(who).player.rack[:3]]})
            self.main(who)  # sync 補送
            self.state_of(who, "騰出空位補送")
        self.revive()
        found = self.foe()
        if found is not None:
            fid, loc, side = found
            who = self.H_FIGHT
            self.place(who, loc, side)
            self.edit(who, lambda p: p.snubbed_until.clear())
            self.kit(who)
            with self.winning():
                self.press(who, f"act:challenge:{fid}", "第三次打贏")
            self.state_of(who, "第三次打贏之後")
        self.world_gear("接著做完")
        self.database("接手之後")

    def views(self) -> None:
        """每個人看一遍主畫面、門下頁、神器譜。"""
        for who in self.PLAYERS:
            self.main(who)
            self.call(who, "GET", "/api/menxia")
        self.boards()

    def bots(self) -> None:
        """伺服器假人兩個（BotRunner：bot_policy 的 market:；門外的牧乙沒進馬市，act:market 靠 pick 驅動的牧丁與整季機器人）、
        直接用 bot_policy.pick 驅動兩個、整季機器人；不寫誰是假人。"""
        from collections import Counter

        from tianxia import bot, bot_policy, mounts, server_bots, treasures
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        def make(name: str, seed: int, inside: bool, rng_seed: int):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(rng_seed), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=seed, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            p.location, p.journey = self.market(), None
            p.visited.add(self.market())
            p.stats["silver"] = GEAR_SILVER
            for mid in self.mats(1):
                p.materials[mid] = 4
            p.stamina = float(self.c.config.stamina_max)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            g.state.pending_event = None  # 開局那一件事先放下
            if inside:
                p.picking_market = True
            return g

        for i, name in enumerate(GEAR_BOTS):  # 甲已經坐在馬市裡（market: 的分數）；乙在門外，沒進馬市（act:market 靠下面 pick 驅動的牧丁與整季機器人；審查實測）
            g = make(name, 71 + i, i == 0, i)
            emit(f"假人 {name} 進場前", {"want": bot.market_want(g), "loc": g.state.player.location,
                                         "options": [o.id for o in g.options(odds=False, tick=False)][:14]})
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(GEAR_BOTS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_GEAR_TICKS", "14"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in GEAR_BOTS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"silver": p.stats.get("silver"), "mount": None if p.mount is None else p.mount.model_dump(mode="json"),
                                  "rack": [e.model_dump(mode="json") for e in p.rack], "picking": p.picking_market,
                                  "titles": dict(sorted(Counter(e.title.partition("・")[0] for e in s.journal).items())),
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        # 打分數挑選項（bot_policy.pick：market: 與 act:market 的分數，不經 take_turn 前面那一串別的事）：甲坐在馬市裡、乙在門外，各按到不想按為止
        for k, (name, inside) in enumerate((("牧丙", True), ("牧丁", False))):
            drv = make(name, 80 + k, inside, 40 + k)
            profile = BotProfile(personality="普通", seed=80 + k, faction=None, season_number=self.world.get_season_number())
            trace = []
            for step in range(12):
                self.begin()
                options = [o for o in drv.options(odds=False, tick=False) if o.enabled and o.id.startswith(("market:", "act:market"))]
                if step == 0:
                    emit(f"假人 {name} 分數", [[o.id, bot_policy.score(drv, o, profile)] for o in options])
                choice = bot_policy.pick(drv, options, profile, random.Random(step))
                trace.append(choice)
                if choice is None:
                    break
                drv.choose(choice)
            emit(f"假人 {name} 挑的", trace)
            p = drv.state.player
            emit(f"假人 {name} 之後", {"silver": p.stats.get("silver"), "mount": None if p.mount is None else p.mount.model_dump(mode="json"),
                                        "rack": [e.model_dump(mode="json") for e in p.rack], "picking": p.picking_market,
                                        "journal": [[e.title, list(e.lines)[:3]] for e in drv.state.journal[:5]]})
        # 整季機器人：路過馬市看一眼（visit_market）、餵（feed_mount）、換更好的（wear_better）、advance 補送寄放
        solo = make("牧戊", 90, False, 5)
        p = solo.state.player
        tid = next(iter(sorted(self.c.gear.treasures)), None)
        emit("整季機器人 進門前", {"want": bot.market_want(solo)})
        bot.visit_market(solo)
        emit("整季機器人 visit_market", {"silver": p.stats.get("silver"), "mount": None if p.mount is None else p.mount.model_dump(mode="json"),
                                        "rack": [e.model_dump(mode="json") for e in p.rack], "picking": p.picking_market,
                                        "journal": [[e.title, list(e.lines)[:3]] for e in solo.state.journal[:5]]})
        if p.mount is not None:
            p.mount.edge = 20
            bot.feed_mount(solo)
        if tid is not None:
            p.rack.append(treasures.new_treasure(solo.state, self.c, tid))
        bot.wear_better(solo)
        emit("整季機器人 餵與換", {"mount": None if p.mount is None else p.mount.model_dump(mode="json"),
                                  "treasure": None if p.treasure is None else p.treasure.model_dump(mode="json"), "rack": len(p.rack)})
        p.held_gear.append(mounts.new_mount(solo.state, name="補送馬", tier=2, quality="中品"))
        while len(p.rack) < self.c.config.weapons.rack_cap:  # 庫滿了，advance 補不進去
            p.rack.append(mounts.new_mount(solo.state, name="塞滿", tier=1, quality="下品"))
        solo.advance(3600)
        emit("整季機器人 advance 補送（庫滿）", {"held": len(p.held_gear), "rack": len(p.rack)})
        p.rack.pop()
        solo.advance(3600)  # 只 advance、不 sync：整季機器人補寄放的東西走這裡
        emit("整季機器人 advance 補送（有空位）", {"held": [e.name for e in p.held_gear], "rack": [e.name for e in p.rack],
                                                  "journal": [[e.title, list(e.lines)[:3]] for e in solo.state.journal[:3]]})

    def season(self) -> None:
        """收季、開下一季：神器譜跨季還在；換季後按 market:back。收季前沒人坐在馬市裡，「開著的馬市跟新角色重來」沒走到（審查實測）。"""
        self.do(ADMIN, "end_season")
        for who in (self.H_BUY, self.SHOPPER):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.H_BUY, self.SHOPPER, self.NEAR):
            self.state_of(who, "換季之後（動作前的存檔）")
            self.main(who)
            self.press(who, "market:back", "換季後")
            self.state_of(who, "換季之後（動作後）")
        self.boards()


# 改一個字（selftest）：名將託人送來那一句（signature_arms.GIFT_SENT_LINE；搬之前在 tianxia/signature_arms.py、之後在 tianxia/features/gear/signature_arms.py，
# 第 1 項是搬進包的檔、第 2 項是舊名的檔，搬的人照實際的檔名改）。抓到的地方：贈丑的本命兵器（他不在身邊，託人送來）
register_track("gear", GearScenario, (("tianxia/features/gear/signature_arms.py",),
                                      ("託人把【{arm}】送到你手上", "託人將【{arm}】送到你手上")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "map", "military",
                       "outlets", "peers", "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "territory_acts", "travel", "zhuan"))
