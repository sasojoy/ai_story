"""same_behavior 一軌一檔：arts（這一檔登記 arts）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import DUEL_PROFILES, Scenario
from sb.harness import ADMIN, BUF, CLOCK0, MODEL, _setup_child, db_text, emit, register_bots, register_track

# ═══════════════════════════ arts（全部拆包第 23 批「修練」，dev/arts-1）：arts 一軌 ═══════════════════════════
# 改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡三段式、傳功、配點、拜師學藝（learn:）搬進修練包（計畫
# docs/superpowers/plans/2026-11-01-修練包-第1批.md）。名號一律原創（PM 11/04）。

ARTS_LINE = "千招落盡，只剩你與那一腿，風聲都慢了下來。"  # 假模型寫的破境卡那一句：合格（八到四十字、沒有數字英文）、跟兩句套句都不一樣
_ARTS_CLIENTS: dict[type, type] = {}


def _arts_client(base: type) -> type:
    """破境卡那一句的假模型（base 是 _setup_child 那一層換好的 client 類別；同 _tavern_client）：LineReading 回 MODEL["ascend_line"] 那一句，
    其餘照 base（丟連線錯誤、大場面判讀）。"""
    if base not in _ARTS_CLIENTS:
        class ArtsClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "LineReading":
                    return schema(line=MODEL["ascend_line"])
                return super().chat_structured(messages, schema, *a, **k)

        _ARTS_CLIENTS[base] = ArtsClient
    return _ARTS_CLIENTS[base]


class ArtsScenario(Scenario):
    """修練（--track arts，自己一個資料庫）：修練頁的每一顆（/api/menxia/<op>、/api/do/allocate、/api/do/ascend_line）與 learn:。
    - 籌備中（管理者還沒開季）：修練頁的動作一律回「賽季籌備中」那一句（裝飾器 _not_while_preparing 搬進核心）。
    - 學藝（learn:）：書院那幾門灰著（書院弟子、俠名）、付不起灰著（按了被擋）、兩處各學一門、學過的不在選單上、再按一次被擋；
      改練（換上庫裡學來的那一門）、換回、沒有這一門。
    - 練成：心得不足、練到第十成（第一下受傷：機率在記憶體裡擺成 1）、練無可練、內功；裝意境（第一格空著時指定第二格、不指定格、沒有這個意境、沒有這門武學）、
      拆下、拆不在槽上的。
    - 熔煉：身上的熔不掉、庫裡沒有、熔庫裡學來的一門、熔一個意境、批量熔煉（一門武學與一個意境）；配點：沒有點、配兩點、沒有這一項、到頂。
    - 破境丹衝絕學：自創一門上品（三段式立意，模型擋著走關鍵字表）、還沒到極處、等契機、沒有丹、體力不足、下品的、沒有這門；
      敗的那一下（機會在記憶體裡壓到 1%：撞回來、下一次多一成），再服丹衝到衝開為止。
      **前半停在這裡**：破境卡寫好了、那一句還沒寫回（PlayerState.ascension.line 是空的）。同一刻另有一位等著定名的舊存檔（PlayerState.naming，
      手上的是自己自創、自己第一個練成的那一門）、一位手上有同一門的人、一位境界卡沒配完的人、一位走到裝意境那一步的序章新人。
    - 後半第一件事：新程式走破境卡三段式（A 開單、B 模型擋著走套句、C 存回）、再按一次（卡上已經有那一句）、收掉。
      接著定名（名字不行、被用掉、定成）與手上同一門的人下一次同步補一則（_deliver_renames）；序章新人接著練成、熔煉（序章的拒絕）；
      傳功給同伴與部下（心得不足、每一項、本人、名冊上沒有）；境界卡（屬性五段在記憶體裡打開：season21、week7）與配點那一句；
      絕學的契機（核心的單打服務 _seize：基礎武學擺成上品第十成，照原本的機會打五場、必中一場〔照舊一句升品〕；自創一門換上、必中一場
      〔破境卡、卡上那一句 via seize：假模型寫得好，線上正常走的那一條，C 段存回模型那一句〕）；追風步的舊品質讀檔時拿掉；最後每個人的修練頁。"""

    PRACTICE, PILL, NAMER, HOLDER, TEACHER, FIGHTER = "墨池", "寒江", "竹影", "松風", "石泉", "雲岫"
    PUPIL = "初學"
    PHASES_FIRST = ["setup", "learn", "switch", "practice", "slot", "melt", "allocate", "create", "pill", "pending", "hut_slot"]
    PHASES_SECOND = ["card", "resume", "naming", "renames", "hut_rest", "teach", "milestone", "seize", "zhuifeng", "pages"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("ascend_line") is not None:
                client.__class__ = _arts_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

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
        players = [self.PRACTICE, self.PILL, self.NAMER, self.HOLDER, self.TEACHER, self.FIGHTER, self.PUPIL]
        for who in players:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        # 籌備中（管理者還沒開季）：修練頁的動作一律擋（_not_while_preparing），定名的 A 段（假人用）也是 None
        who = self.PRACTICE
        self.mx(who, "practice", {"kind": "武學"})
        self.mx(who, "switch", {"art": "jichu_quanjiao"})
        self.mx(who, "slot", {"art": "jichu_quanjiao", "insight": "feng"})
        self.mx(who, "unslot", {"art": "jichu_quanjiao", "insight": "feng"})
        self.mx(who, "melt", {"art": "jichu_quanjiao"})
        self.mx(who, "melt_insight", {"insight": "feng"})
        self.mx(who, "melt_many", {"arts": ["jichu_quanjiao"], "insights": []})
        self.mx(who, "cultivate", {"art": "jichu_quanjiao", "use_legend": True})
        self.mx(who, "name", {"name": "籌備中的名"})
        self.mx(who, "chuangong", {"person": "nobody", "what": "str"})
        self.do(who, "allocate", {"stat": "str"})
        self.menxia(who)
        self.do(ADMIN, "open_season")
        for who in players[:-1]:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        factions = {f.id: f for f in self.c.scenario.factions}
        guan = factions.get("guan")
        if guan is not None and guan.join_at and self.place(self.FIGHTER, guan.join_at[0]):
            self.choose(self.FIGHTER, "faction:guan")
            self.choose(self.FIGHTER, "faction:confirm")
            self.settle_choices(self.FIGHTER)
        for who in players[:-1]:
            self.place(who, None)  # 體力補滿、過了新手期

    # ── 小工具 ──

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def menxia(self, who: str, person: str | None = None):
        return self.call(who, "GET", "/api/menxia" + (f"?person={person}" if person else ""))[1]

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟修練有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        m = p.member
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "wugong": [m.wugong_id, m.wugong_level], "neigong": [m.neigong_id, m.neigong_level], "level": m.level,
            "injury": m.injury, "neili": m.neili, "arts": list(p.arts), "art_levels": dict(sorted(p.art_levels.items())),
            "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())), "insights": list(p.insights),
            "stats": dict(sorted(p.stats.items())), "stat_points": p.stat_points, "milestone_due": p.milestone_due,
            "legend_items": p.legend_items, "legend_fails": dict(sorted(p.legend_fails.items())), "naming": p.naming,
            "renames_told": list(p.renames_told), "ascension": None if p.ascension is None else p.ascension.model_dump(),
            "follower_drill": [d.model_dump() for d in p.follower_drill], "stamina": p.stamina,
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def xinde(self, who: str, amount: int) -> None:
        self.edit(who, lambda p: p.stats.__setitem__("xinde", amount))

    def academy(self) -> str:
        return "lake" if self.profile == "test" else "yingchuan_academy"

    def base_insights(self) -> list[str]:
        """這份內容的基本意境（意境表的前幾個；測試內容另一套）。"""
        return sorted(self.c.insights)[:4]

    def worn(self, who: str) -> str | None:
        return self.chars.load(who).player.member.wugong_id

    def create_art(self, who: str, name: str) -> str | None:
        """自創一門武學（執器、擺式、立意〔三段式：模型擋著，照關鍵字表讀〕、立名）：回那一門的 id（不在手上是 None）。"""
        from tianxia.features.craft import create

        self.xinde(who, 20000)
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.do(who, "create_intent", {"text": "風過林梢，影不留痕"})
        self.mx(who, "create_name", {"name": name, "move": ""})
        p = self.chars.load(who).player
        own = next((a for a in [p.member.wugong_id, *p.arts] if a and a not in self.c.skills), None)
        emit(f"{who} 自創的那一門", own)
        return own

    # ── 前半 ──

    def lesson_spots(self) -> list[str]:
        """學藝的地方：書院（只教書院弟子、要俠名的，散人都灰著）、潁水與樓桑村（散人學得了、要學費）；測試內容是湖邊。"""
        return ["lake"] if self.profile == "test" else [self.academy(), "yingshui", "loushang_village"]

    def learn(self) -> None:
        """拜師學藝（learn:，修練包的前綴）：書院那幾門灰著（書院弟子、俠名）；付不起灰著、按了被擋；學兩門（兩處各一門）；
        學過的不在選單上、再按一次被擋。"""
        who = self.PRACTICE
        for loc in self.lesson_spots():
            if not self.place(who, loc):
                continue
            self.edit(who, lambda p: p.stats.__setitem__("silver", 0))
            view = self.main(who)
            shown = {i: o for i, o in self.ids(view).items() if i.startswith("learn:")}
            emit(f"{loc} 學藝的鈕（沒錢）", shown)
            if shown:
                self.choose(who, next(iter(shown)))  # 灰著的照樣按（書院弟子、付不起）：被擋
            self.edit(who, lambda p: p.stats.__setitem__("silver", 2000))
            lessons = [i for i, o in self.ids(self.main(who)).items() if i.startswith("learn:") and o.get("enabled")]
            emit(f"{loc} 學藝的鈕", lessons)
            if lessons:
                self.choose(who, lessons[0])
                emit(f"{loc} 學過之後的鈕", [i for i in self.ids(self.main(who)) if i.startswith("learn:")])
                self.choose(who, lessons[0])  # 已經不在選單上：被擋
        self.state_of(who, "學藝之後")

    def switch(self) -> None:
        """改練：換上庫裡的一門、換回原本那一門、沒有這一門。"""
        who = self.PRACTICE
        p = self.chars.load(who).player
        before = p.member.wugong_id
        other = next((a for a in p.arts if a in self.c.skills and self.c.skills[a].kind == "武學"), None)
        if other is not None:
            self.mx(who, "switch", {"art": other})
            if before is not None:
                self.mx(who, "switch", {"art": before})
        self.mx(who, "switch", {"art": "沒有這門"})
        self.state_of(who, "改練之後")

    def practice(self) -> None:
        """練成：心得不足、一路練到第十成（受傷照擲；第一下受傷的機率在記憶體裡擺成 1，兩份程式同一套）、練無可練、內功兩成。"""
        who = self.PRACTICE
        self.xinde(who, 0)
        self.mx(who, "practice", {"kind": "武學"})
        self.xinde(who, 5000)
        cfg = self.c.config
        before, cfg.practice_injury_chance = cfg.practice_injury_chance, 1.0
        try:
            self.mx(who, "practice", {"kind": "武學"})  # 這一番苦練傷了氣血
        finally:
            cfg.practice_injury_chance = before
        for _ in range(9):
            self.mx(who, "practice", {"kind": "武學"})
        for _ in range(2):
            self.mx(who, "practice", {"kind": "內功"})
        self.state_of(who, "練成之後")

    def slot(self) -> None:
        """意境裝卸：指定格（第一格空著時指定第二格：不給 index 會落到第一格，才分得出 index 有沒有傳到底；審查補的，網頁每一次裝都帶 index）、
        不指定格（挑空的那一格）、沒有這個意境、沒有這門武學；拆下、拆不在槽上的。"""
        who = self.PRACTICE
        ins = self.base_insights()
        self.edit(who, lambda p: p.insights.extend(i for i in ins if i not in p.insights))
        art = self.worn(who) or ""
        if len(ins) > 1:
            self.mx(who, "slot", {"art": art, "insight": ins[1], "index": 1})
            emit("指定第二格之後的槽", self.chars.load(who).player.art_slots.get(art))
        if ins:
            self.mx(who, "slot", {"art": art, "insight": ins[0]})
        self.mx(who, "slot", {"art": art, "insight": "沒有這個意境"})
        if ins:
            self.mx(who, "slot", {"art": "沒有這門", "insight": ins[0]})
            self.mx(who, "unslot", {"art": art, "insight": ins[0]})
            self.mx(who, "unslot", {"art": art, "insight": ins[0]})  # 已經不在槽上
        self.state_of(who, "裝卸意境之後")

    def melt(self) -> None:
        """熔煉：身上的熔不掉、庫裡沒有、熔一門、熔一個意境、批量熔煉（武學與意境一起）。"""
        who = self.PRACTICE
        p = self.chars.load(who).player
        self.mx(who, "melt", {"art": p.member.wugong_id or ""})
        self.mx(who, "melt", {"art": "沒有這門"})
        library = [a for a in p.arts]
        if library:
            self.mx(who, "melt", {"art": library[0]})
        p = self.chars.load(who).player
        loose = [i for i in p.insights if not any(i in (slots or []) for slots in p.art_slots.values())]
        if loose:
            self.mx(who, "melt_insight", {"insight": loose[0]})
        p = self.chars.load(who).player
        loose = [i for i in p.insights if not any(i in (slots or []) for slots in p.art_slots.values())]
        self.mx(who, "melt_many", {"arts": list(p.arts), "insights": loose[:1]})
        self.mx(who, "melt_many", {"arts": "不是串列", "insights": []})
        self.state_of(who, "熔煉之後")

    def allocate(self) -> None:
        """配點：沒有點、配兩點、沒有這一項、到頂。"""
        who = self.PRACTICE
        self.edit(who, lambda p: setattr(p, "stat_points", 0))
        self.do(who, "allocate", {"stat": "str"})
        self.edit(who, lambda p: setattr(p, "stat_points", 3))
        self.do(who, "allocate", {"stat": "str"})
        self.do(who, "allocate", {"stat": "str"})
        self.do(who, "allocate", {"stat": "沒有這項"})
        self.edit(who, lambda p: p.stats.__setitem__("agi", self.c.config.stat_cap))
        self.do(who, "allocate", {"stat": "agi"})
        self.state_of(who, "配點之後")

    def create(self) -> None:
        """寒江自創一門（上品），換上身。"""
        who = self.PILL
        own = self.create_art(who, "寒江掌")
        if own is not None and own in self.chars.load(who).player.arts:
            self.mx(who, "switch", {"art": own})
        self.state_of(who, "自創之後")

    def pill(self) -> None:
        """破境丹衝絕學：拒絕的幾種，再服丹衝到衝開為止。前半停在破境卡寫好、那一句還沒寫回。"""
        who = self.PILL
        own = self.worn(who)
        if own is None:
            return
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 還沒到極處（第一成）
        self.edit(who, lambda p: setattr(p.member, "wugong_level", 10))
        self.mx(who, "cultivate", {"art": own})  # 沒勾服丹：等契機那一句
        self.edit(who, lambda p: setattr(p, "legend_items", 0))
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 沒有丹
        self.edit(who, lambda p: (setattr(p, "legend_items", 1), setattr(p, "stamina", 1.0)))
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 體力不足
        neigong = self.chars.load(who).player.member.neigong_id
        if neigong is not None:
            self.mx(who, "cultivate", {"art": neigong, "use_legend": True})  # 下品：品級不靠修練
        self.mx(who, "cultivate", {"art": "沒有這門", "use_legend": True})
        self.edit(who, lambda p: setattr(p, "legend_items", 12))
        cfg = self.c.config
        before, cfg.legend_item_bonus = cfg.legend_item_bonus, 0  # 敗的那一下：機會在記憶體裡壓到 1%（兩份程式同一套），撞回來、下一次多一成
        try:
            self.place(who, None)
            self.mx(who, "cultivate", {"art": own, "use_legend": True})
        finally:
            cfg.legend_item_bonus = before
        for _ in range(12):
            self.place(who, None)
            self.mx(who, "cultivate", {"art": own, "use_legend": True})
            if self.chars.load(who).player.ascension is not None:
                break
        self.mx(who, "cultivate", {"art": own, "use_legend": True})  # 已經是絕學
        self.state_of(who, "服丹衝關之後")
        emit("破境卡（那一句還沒寫）", (self.main(who).get("status") or {}).get("ascension"))

    def pending(self) -> None:
        """寫到一半的另外三種：等著定名的舊存檔（竹影自創的那一門、自己第一個練成；松風手上也有同一門）、境界卡沒配完的人（石泉）。"""
        own = self.create_art(self.NAMER, "竹影拳")
        if own is not None:
            self.world.claim_master(own, self.NAMER)
            self.edit(self.NAMER, lambda p: setattr(p, "naming", own))
            self.edit(self.HOLDER, lambda p: p.arts.append(own))
            self.menxia(self.NAMER)
        self.edit(self.TEACHER, lambda p: (setattr(p, "stat_points", 2), setattr(p, "milestone_due", 20)))
        for who in (self.NAMER, self.HOLDER, self.TEACHER):
            self.state_of(who, "前半最後")

    def hut_slot(self) -> None:
        """序章新人走到裝意境那一步（同 Scenario.prologue 的前幾步）；沒有序章的季什麼都不做。"""
        from tianxia.features.sense import sensing

        who = self.PUPIL
        view = self.main(who)
        if not view.get("prologue"):
            emit(f"{who}：這一季沒有序章", None)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.mx(who, "slot", {"art": "jichu_tuna", "insight": got[0]})  # 序章只准裝師父點名的那一門
            self.mx(who, "slot", {"art": "jichu_quanjiao", "insight": got[0]})
        self.menxia(who)
        self.state_of(who, "序章裝意境之後")

    # ── 後半 ──

    def card(self) -> None:
        """後半第一件事：新程式接著寫破境卡那一句（三段式：A 開單、B 模型擋著走套句、C 存回）；再按一次；收掉。"""
        who = self.PILL
        self.relogin(who)
        emit("破境卡（後半拿到的）", (self.main(who).get("status") or {}).get("ascension"))
        self.do(who, "ascend_line")
        emit("破境卡（寫回之後）", (self.main(who).get("status") or {}).get("ascension"))
        self.do(who, "ascend_line")  # 已經寫過：A 段不開單
        self.mx(who, "ascend_dismiss")
        self.state_of(who, "破境卡收掉之後")

    def resume(self) -> None:
        self.login_all()

    def naming(self) -> None:
        """舊存檔等著定名：名字不行、被用掉、定成。"""
        who = self.NAMER
        self.menxia(who)
        self.mx(who, "name", {"name": ""})
        self.mx(who, "name", {"name": "寒江掌"})
        self.mx(who, "name", {"name": "竹影神拳"})
        self.mx(who, "name", {"name": "再定一次"})  # 已經定過了
        self.state_of(who, "定名之後")

    def renames(self) -> None:
        """手上有同一門的人下一次同步補一則（_deliver_renames）；再同步一次不重複。定名的人自己不補。"""
        self.main(self.HOLDER)
        self.state_of(self.HOLDER, "定名之後同步")
        self.main(self.HOLDER)
        self.main(self.NAMER)
        self.state_of(self.NAMER, "自己定的名同步之後")

    def hut_rest(self) -> None:
        """序章新人（前半停在裝意境那一步）接著練成、熔煉：序章的拒絕（別的一欄、批量熔煉、熔意境）。"""
        who = self.PUPIL
        if not self.main(who).get("prologue"):
            return
        self.menxia(who)
        self.mx(who, "practice", {"kind": "內功"})
        self.mx(who, "practice", {"kind": "武學"})
        self.mx(who, "practice", {"kind": "武學"})
        p = self.chars.load(who).player
        self.mx(who, "melt_many", {"arts": list(p.arts), "insights": list(p.insights)})
        if p.insights:
            self.mx(who, "melt_insight", {"insight": p.insights[0]})
            self.mx(who, "unslot", {"art": "jichu_quanjiao", "insight": p.insights[0]})
        self.mx(who, "melt", {"art": "jichu_tuna"})
        self.state_of(who, "序章練成、熔煉之後")

    def teach(self) -> None:
        """傳功：同伴（練武學、內功、三項屬性、不傳的一項）、部下（第一季規則的季：多練一成、臂力）、心得不足、本人、名冊上沒有。"""
        who = self.TEACHER
        mate = sorted(self.c.characters)[0]
        skills = [sid for sid, s in sorted(self.open_skills().items()) if s.quality == "下品"]
        self.world.try_recruit(mate, who)
        if skills:
            self.world.update_companion(mate, lambda pr: (setattr(pr, "wugong_id", skills[0]), setattr(pr, "neigong_id", skills[-1])))
        if self.c.followers:
            first = sorted(self.c.followers)[0]
            self.edit(who, lambda p: setattr(p, "followers", [first]))
        self.xinde(who, 0)
        self.menxia(who, mate)
        self.mx(who, "chuangong", {"person": mate, "what": "wugong"})
        self.xinde(who, 20000)
        for what in ("wugong", "neigong", "str", "agi", "con", "wis"):
            self.mx(who, "chuangong", {"person": mate, "what": what})
        self.menxia(who, "follower:0")
        for what in ("wugong", "str"):
            self.mx(who, "chuangong", {"person": "follower:0", "what": what})
        self.mx(who, "chuangong", {"person": "player", "what": "str"})
        self.mx(who, "chuangong", {"person": "沒有這個人", "what": "str"})
        emit("同伴的進度", self.world.get_companion(mate).model_dump())
        self.state_of(who, "傳功之後")

    @contextlib.contextmanager
    def milestones_on(self):
        """減法季屬性五段：兩種現役設定（season21、week7）都關著，在記憶體裡打開（兩份程式同一套），做完擺回來。"""
        jf = getattr(self.c.config, "jianfa", None)
        before = getattr(jf, "stat_milestones", None)
        if jf is not None and self.profile in DUEL_PROFILES:
            jf.stat_milestones = True
        try:
            yield
        finally:
            if jf is not None:
                jf.stat_milestones = before

    def milestone(self) -> None:
        """境界卡（減法季屬性五段，milestones_on）：卡、配兩點（配點那一句）、配完收卡。"""
        who = self.TEACHER
        with self.milestones_on():
            emit("境界卡", self.main(who).get("milestone"))
            self.do(who, "allocate", {"stat": "str"})
            emit("境界卡（配了一點）", self.main(who).get("milestone"))
            self.do(who, "allocate", {"stat": "con"})
            emit("境界卡（配完）", self.main(who).get("milestone"))
        self.state_of(who, "境界卡之後")

    def seize(self) -> None:
        """絕學的契機（核心的單打服務 _seize → 修練包）：身上那一門（基礎武學）擺成上品第十成，照寫好的打贏幾場；出陣開著的季在
        汝南荒野出陣，關著的在長社遊歷。再自創一門換上、擺到第十成，打一場必中的：自創的那一門破境（破境卡、江湖史、傳聞），
        卡上那一句走三段式，模型寫得好（假模型；後半第一件事的寒江那一張走模型擋著的套句，只走那一條的話 C 段把模型的句子丟掉也看不出來）。"""
        from tianxia import territory

        who = self.FIGHTER
        p = self.chars.load(who).player
        art = p.member.wugong_id
        if art is None:
            art = next((sid for sid, s in sorted(self.open_skills().items()) if s.quality == "下品" and s.kind == "武學"), None)
            self.edit(who, lambda pl: setattr(pl.member, "wugong_id", art))
        self.edit(who, lambda pl: (pl.art_quality.__setitem__(art, "上品"), setattr(pl.member, "wugong_level", 10)))
        loc = "runan_wilds" if territory.on(self.c) else ("lake" if self.profile == "test" else "changshe")
        self.set_duel(False)  # 約戰開著的季按出陣只打開那張卡（不打）：契機要的是真的打一場（同出陣一軌的攻）
        try:
            self.seize_fights(who, loc, 5)  # 照原本的機會擲（難度比夠的季摸到了又滑走；none、test 的對手太弱，不到 min_ratio 不擲）
            self.seize_sure(who, loc)  # 基礎武學（不是自創的）：照舊一句升品，沒有破境卡
            own = self.create_art(who, "雲岫腿")
            if own is not None and own in self.chars.load(who).player.arts:
                self.mx(who, "switch", {"art": own})
                self.edit(who, lambda pl: setattr(pl.member, "wugong_level", 10))
                self.seize_sure(who, loc)  # 自創的那一門：破境
        finally:
            self.set_duel(True)
        self.state_of(who, "契機之後")
        emit("契機的破境卡", (self.main(who).get("status") or {}).get("ascension"))
        MODEL["ascend_line"] = ARTS_LINE
        try:
            self.do(who, "ascend_line")
        finally:
            MODEL["ascend_line"] = None
        emit("契機的破境卡（寫回之後）", (self.main(who).get("status") or {}).get("ascension"))
        with self.milestones_on():  # 單點突變補的（Task 5）：打過幾場、威力夠大，配點那一句才寫全隊前後；身法不動威力、不寫那一段
            self.do(who, "allocate", {"stat": "str"})
            self.do(who, "allocate", {"stat": "agi"})
        self.state_of(who, "契機之後配點")

    def seize_sure(self, who: str, loc: str) -> None:
        """打一場必中的契機：機會在記憶體裡擺成必中、難度比不設門檻（兩份程式同一套），做完擺回來。"""
        rule = self.c.config.breakthrough
        before = rule.chance, rule.max_chance, rule.min_ratio
        rule.chance, rule.max_chance, rule.min_ratio = 10 ** 6, 100, 0.0
        try:
            self.seize_fights(who, loc, 1)
        finally:
            rule.chance, rule.max_chance, rule.min_ratio = before

    def seize_fights(self, who: str, loc: str, times: int) -> None:
        for i in range(times):
            if not self.place(who, loc):
                return
            self.edit(who, lambda pl: setattr(pl, "sorties_today", 0))
            option = self.ids(self.main(who)).get("act:train")
            emit(f"契機的 act:train（第 {i + 1} 場）", option)
            if not option or not option.get("enabled"):
                break
            with self.winning():
                self.choose(who, "act:train")
            self.settle_choices(who)
            state = self.chars.load(who)
            record = state.battles[0] if state.battles else None
            emit(f"契機那一場（第 {i + 1} 場）", None if record is None else {
                "tier": record.tier, "difficulty": record.difficulty, "our_power": record.our_power, "notes": record.notes})

    def zhuifeng(self) -> None:
        """追風步的舊品質（中間一版寫成了絕學）：讀檔時拿掉（_drop_stale_references → _drop_old_zhuifeng），按一下存回去。
        手上要真的有追風步（單點突變補的，Task 5）：不在手上的那一門，品質讀檔時本來就照「手上有的」清掉，拿不拿掉看不出來。"""
        who = self.PRACTICE

        def fn(p) -> None:
            if "zhuifeng" not in p.arts:
                p.arts.append("zhuifeng")
            p.art_quality["zhuifeng"] = "絕學"

        self.edit(who, fn)
        self.mx(who, "ascend_dismiss")
        p = self.chars.load(who).player
        emit("追風步的品質", {"held": "zhuifeng" in p.arts, "quality": p.art_quality.get("zhuifeng")})

    def pages(self) -> None:
        """每個人最後的修練頁（唯讀那十一個：名冊、功法卡、背包、持有數、功法庫、意境、等著定名的、傳功鈕……）與江湖畫面。"""
        for who in (self.PRACTICE, self.PILL, self.NAMER, self.HOLDER, self.TEACHER, self.FIGHTER, self.PUPIL):
            self.menxia(who)
            self.main(who)


# 假人：none（舊遊歷、沒有第一季規則）、weekend（序章、部下）、week7（減法季）。測試內容的 BotRunner 一個都不上線（acted 0），不跑
ARTS_BOT_PROFILES = ("week7",)
ARTS_SEATS = [("硯甲", "yingchuan_academy"), ("硯乙", "yingchuan"), ("硯丙", "yingchuan"), ("硯丁", "yingchuan")]


def arts_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """修練的假人（--seats arts）：整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）與伺服器假人（BotRunner＋bot_policy.take_turn，
    random.Random(7)、假時鐘、每一輪 +300 秒）四個跑 N 輪——硯甲在潁川書院（學藝：銀兩夠、庫有空）、硯乙身上一門上品第十成、手上有破境丹
    （tend_arts 的服丹衝關）、硯丙自創一門、自己第一個練成、等著定名（絕學定名的 A 段 mastery_request → 假人程式的 B 段〔模型擋著〕→ C 段字表另組）、
    硯丁心得多、名下一位同伴、手上有屬性點（傳功門下、配點）。寫存檔、修練那幾種紀錄的則數、名下同伴的進度、資料庫的雜湊。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.features.craft import create
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.ollama_client import OllamaClient
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def content_of():
        return load_content(root / "content", profile=None if profile == "none" else profile)

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title.partition("・")[0] for s in states for e in s.journal).items()))

    def arts_of(state) -> dict:
        p = state.player
        return {"wugong": [p.member.wugong_id, p.member.wugong_level], "neigong": [p.member.neigong_id, p.member.neigong_level],
                "arts": list(p.arts), "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())),
                "stats": dict(sorted(p.stats.items())), "stat_points": p.stat_points, "legend_items": p.legend_items,
                "legend_fails": dict(sorted(p.legend_fails.items())), "naming": p.naming,
                "ascension": None if p.ascension is None else p.ascension.model_dump()}

    content = content_of()
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("修練整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("修練整季機器人 紀錄標題", titles([game.state]))
    emit("修練整季機器人 武學", arts_of(game.state))
    emit("修練整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = content_of()
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    mate = sorted(content.characters)[0]
    for i, (name, loc) in enumerate(ARTS_SEATS):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=41 + i, faction=None, season_number=world.get_season_number())
        p.location, p.journey = loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        if name == "硯甲":
            p.stats["silver"] = 2000
        elif name == "硯乙":
            art = p.member.wugong_id
            if art is not None:
                p.art_quality[art] = "上品"
                p.member.wugong_level = 10
            p.legend_items = 6
        elif name == "硯丙":
            p.stats["xinde"] = 20000
            g.create_begin("武學", "拳腳")
            g.create_pose(create.preset(content, "進擊"))
            g.create_intent("流水不爭先，爭的是滔滔不絕")
            g.create_name("硯丙掌")
            own = next((a for a in [p.member.wugong_id, *p.arts] if a and a not in content.skills), None)
            if own is not None:
                world.claim_master(own, name)
                p.naming = own
        elif name == "硯丁":
            p.stats["xinde"] = 20000
            p.stat_points = 3
            world.try_recruit(mate, name)
        chars.save(g.state)
    clock = [CLOCK0]
    # 假人程式照 run_bots 帶一個 client（_setup_child 換成叫不動的那一個）：絕學定名的 B 段請模型、模型擋著，C 段照字表另組（bot_policy.apply_job）
    client = OllamaClient.from_config(content.config) if content.config.bot_naming else None
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0], client=client)
    totals = Counter()
    for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                      named=report.named)
    states = chars.all(bots_only=True)
    emit("修練假人 一輪一輪", dict(sorted(totals.items())))
    emit("修練假人 紀錄標題", titles(states))
    emit("修練假人 武學", {s.player.name: arts_of(s) for s in states})
    emit("修練假人 名下的同伴", world.get_companion(mate).model_dump())
    emit("修練假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("修練假人 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "修練假人", dict(totals), titles(states))


# 改一個字（selftest）：配點沒有點那一句（搬之前在 engine.py 的 allocate_stat、之後在 features/cultivation/actions.py），week7 墨池配點那一下抓到
# 改一個字（合回 develop 第 0 段換過）：原本改的是舊配點那一句，五項屬性的季（week7、season21）走 _allocate_v2、碰不到；換成練成絕學定名那一句
register_track("arts", ArtsScenario, (("tianxia/features/cultivation/actions.py", "tianxia/engine.py"),
                                      ("練成絕學的人，定名", "練成絕學的人，命名")), "week7",
               covers=("battle", "bounties", "bout", "companions", "craft", "cultivation", "explore", "faction", "figure_acts", "gear",
                       "guide", "military", "peers", "seal", "seclusion", "sense", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "travel", "zhuan"))
register_bots("arts", ARTS_BOT_PROFILES, arts_bots_run)  # 修練那一軌的假人（--seats arts）
