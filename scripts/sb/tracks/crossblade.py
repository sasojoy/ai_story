"""same_behavior 一軌一檔：crossblade（這一檔登記 crossblade）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track
from sb.tracks.craft import _craft_client
from sb.tracks.peers import PeersScenario

# ═══════════════════════════ crossblade（全部拆包第 38 批「玩家互動二」，dev/peers-2）：crossblade 一軌 ═══════════════════════════
# 切磋、論武（三段式首創取名）、截殺（含策馬脫身），加上假人答切磋、答論武、截殺（計畫 docs/superpowers/plans/2026-11-07-玩家互動包-第2批.md）。
# 第 37 批的 peers 軌只在玩家卡上看得到這三樣的鈕、不按；這一軌把它們按到底。結伴同行（travel 邀請答應走到 _join）是第 48 批的軌，這裡不走。
# 名字一律原創（第 22 批認定第 3 條）。


class CrossbladeScenario(PeersScenario):
    """玩家互動二軌（全部拆包第 38 批；--track crossblade，自己一個資料庫；疊在 PeersScenario 的小工具上）。
    切磋（POST /api/peer/act spar）：發邀請、重發、對方婉拒（選單 invite:no）、收回、答應（卡上 yes）打一場〔照寫好的結果：大勝、僵持、落敗〕、
    同一對一天滿了、體力不夠〔邀的人、被邀的人、答應前累倒〕、對方此刻正忙、對方走了（選單答應、發邀請的人收到一句）、逾時作廢、休季。
    論武（discuss）：卡上每一樣出得了的一顆、帶一樣發邀請、帶沒有的、重發、婉拒、收回、答應時挑一樣；三段式走 A 段開單 → B 段模型擋掉走 NO_NAME →
    C 段帶 proposed〔模型回了名字〕；首創、配方已有、出同一樣、已經有了、心得不夠、體力不夠、選單上答應（灰的）；peer_brief 那一句（回應的 brief）。
    截殺（raid）：敵對陣營、散人揭通緝、同陣營沒有鈕、城鎮擋、新手期〔雙方〕、體力不夠、在忙、同一對冷卻、被截過的護身、混戰過的拒絕話（FB-607）、
    策馬脫身、打贏打輸平手的銀兩與氣血、官府通緝的惡名、對方下線但還在窗口內、窗口外、Config.raid.enabled 關著不畫、休季。
    三種設定 week7、season21、test（test 內容沒有陣營、第一季開關關著：切磋論武的鈕畫不出來、直接打 API 都是「（此刻無法這麼做。）」，截殺的鈕畫不出來）。
    **前半停在**：切磋邀請送出沒接受（兩張）、論武邀請送出沒接受（一張，首創）、一對人今天打了一半、截殺的冷卻與護身還沒過；
    後半新程式接著答、跨過冷卻與護身再截殺、假人（BotRunner 答切磋、答論武、截殺；整季機器人眼前有邀請的選單）、休季、換季。"""

    S_A, S_B, S_C, S_D, S_E = "鳴鏑", "臨淵", "負霜", "枕戈", "枕流"
    D_A, D_B, D_C, D_D, D_E, D_F = "折桂", "探驪", "觀瀾", "聽松", "拾遺", "掇英"
    R_G1, R_G2, R_H1, R_H2 = "斬蛟", "破浪", "擒龍", "伏虎"
    R_RANGER, R_NEW, R_OFF = "孤鶩", "初生犢", "夜歸人"
    BOT_SEATS = ["隨鴻", "逐電"]
    PLAYERS = {S_A: "guan", S_B: "guan", S_C: "huang", S_D: "guan", S_E: "guan",
               D_A: "guan", D_B: "guan", D_C: "huang", D_D: "guan", D_E: "guan", D_F: "huang",
               R_G1: "guan", R_G2: "guan", R_H1: "huang", R_H2: "huang", R_RANGER: None, R_NEW: "huang", R_OFF: "huang"}
    RAIDERS = [R_G1, R_G2, R_H1, R_H2, R_RANGER, R_NEW, R_OFF]
    PHASES_FIRST = ["setup", "seat", "spar_cards", "spar_fights", "spar_refused", "discuss_cards", "discuss_make", "discuss_refused",
                    "raid_cards", "raid_fights", "raid_refused", "raid_flee", "half"]
    PHASES_SECOND = ["resume", "answer", "raid_again", "bots", "season"]
    HD = "cb_"

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _craft_client(type(client))  # 取名（NameReply）MODEL["craft_name"] 給了就回它，沒給照舊丟連線錯誤＝模型擋著
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    @contextlib.contextmanager
    def model(self, name: dict | None = None):
        """這幾下取名模型回的東西；出來就是擋著。"""
        MODEL["craft_name"] = name
        emit("模型", {"name": name})
        try:
            yield
        finally:
            MODEL["craft_name"] = None

    @contextlib.contextmanager
    def forced(self, tier: str):
        """這一場照寫好的結果打（發起的那一方看；切磋、截殺都從發起的那一方算）：單次判定照樣擲、用掉那一場的亂數，之後只把結果換掉。"""
        from tianxia import encounter

        real = encounter.resolve_encounter
        margin = {"大勝": 1000.0, "險勝": 5.0, "僵持": 0.0, "落敗": -1000.0}[tier]

        def fake(*args, **kwargs):
            return real(*args, **kwargs).model_copy(update={"tier": tier, "margin": margin})

        encounter.resolve_encounter = fake
        emit("這一場照寫好的打", tier)
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    @contextlib.contextmanager
    def fleeing(self, odds: float):
        """這一下策馬脫身的機會照給的數（跑不跑得掉不靠亂數）。"""
        from tianxia.engine import Game

        real = Game.raid_flee_odds
        Game.raid_flee_odds = lambda self, other: odds
        emit("策馬脫身的機會", odds)
        try:
            yield
        finally:
            Game.raid_flee_odds = real

    @contextlib.contextmanager
    def bot_dice(self, chance: float):
        """假人截殺的機會與挑的勝算（舊名在 bot_policy；搬進包之後包的 bots 也有一份同值常數，兩處都換）。"""
        from tianxia import bot_policy

        targets = [bot_policy]
        try:
            from tianxia.features.peers import bots as peers_bots
            targets.append(peers_bots)
        except ImportError:
            pass
        words = ("穩勝", "有把握", "五五波", "不樂觀", "沒把握", "穩輸")
        saved = [(m, getattr(m, "RAID_CHANCE", None), getattr(m, "RAID_ODDS", None), getattr(m, "INVITE_YES", None)) for m in targets]
        for m in targets:
            if hasattr(m, "RAID_CHANCE"):
                m.RAID_CHANCE, m.RAID_ODDS, m.INVITE_YES = chance, words, 1.0  # 答切磋、答論武也一律答應（不然擲不到就看不到取名那條路）
        emit("假人截殺的機會", chance)
        try:
            yield
        finally:
            for m, c, o, y in saved:
                if hasattr(m, "RAID_CHANCE"):
                    m.RAID_CHANCE, m.RAID_ODDS, m.INVITE_YES = c, o, y

    def kind_of(self, loc: str) -> str:
        return self.c.config.explore_mix_of(self.c.locations[loc].tags).kind

    def town(self) -> str:
        hub = self.hub()
        return hub if self.kind_of(hub) == "town" else next((x for x in sorted(self.c.locations) if self.kind_of(x) == "town"), hub)

    def field(self) -> str:
        return next((x for x in sorted(self.c.locations) if self.kind_of(x) != "town"), self.hub())

    def ins(self) -> list[str]:
        return sorted(self.c.insights)[:6]

    def item(self, i: int) -> str:
        return f"insight:{self.ins()[i]}"

    def refill(self, *names: str) -> None:
        for who in names:
            self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))

    def stamina(self, who: str, value: float) -> None:
        self.edit(who, lambda p: setattr(p, "stamina", value))
        emit(f"{who} 體力擺成", value)

    def busy(self, who: str, on: bool) -> None:
        far = self.world.get_season().time + 10 ** 7
        self.edit(who, lambda p: setattr(p, "busy_until", far if on else None))
        emit(f"{who} 閉關", on)

    def hop(self, who: str, loc: str) -> None:
        self.edit(who, lambda p: (setattr(p, "location", loc), p.visited.add(loc)))
        emit(f"{who} 站到", loc)

    def world_mut(self, fn, tag: str) -> None:
        self.world.mutate_season(fn)
        emit(tag, None)

    def cross_state(self, who: str, tag: str) -> None:
        """存檔裡切磋、論武、截殺碰得到的格子：在哪、體力、銀兩心得氣血惡名、等級經驗、意境、坐騎、最新兩則紀錄與戰報；整份存檔的雜湊。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "stamina": p.stamina, "faction": p.faction, "busy": p.busy_until is not None,
            "stats": dict(sorted((k, v) for k, v in p.stats.items() if k in ("silver", "xinde", "evil", "hp"))), "level": p.member.level,
            "exp": getattr(p.member, "exp", None), "points": p.stat_points, "insights": list(p.insights),
            "mount": None if p.mount is None else p.mount.name, "contrib": p.contrib,
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]],
            "battles": [[r.kind, r.tier, r.changes, r.notes] for r in state.battles[:2]],
            "hash": hashlib.sha256(state.model_dump_json().encode("utf-8")).hexdigest()})

    def world_cross(self, tag: str) -> None:
        from tianxia import fusion

        w = self.world.get_season()
        recipes = []
        for a, b in ((0, 1), (2, 3)):
            r = self.world.lookup_insight_recipe(fusion.merge_key(self.ins()[a], self.ins()[b]))
            recipes.append(None if r is None else [r.id, r.name, r.creator, r.co_creator, r.creator_shown])
        emit(f"世界 {tag}", {
            "invites": [[i.id, i.kind, i.sender, i.target, i.location, i.sent_at, i.expires_at, dict(sorted(i.payload.items()))] for i in w.invites],
            "tally": [dict(sorted(w.spar_tally.items())), dict(sorted(w.discuss_tally.items()))],
            "raids": [dict(sorted(w.raids.items())), dict(sorted(w.raided.items())), dict(sorted(w.clashes.items())), dict(sorted(w.clashed.items()))],
            "bounties": [[b.id, b.kind, b.target, list(b.takers), list(b.done_by)] for b in w.bounties if b.id.startswith(self.HD)],
            "recipes": recipes, "ended": w.ended})

    def bounty(self, bid: str, who: str, target: str, auto_by: str | None = None) -> None:
        from tianxia.state import Bounty

        far = self.world.get_season().time + 30 * 86400.0
        b = Bounty(id=f"{self.HD}{bid}", kind="wanted", faction=None, week=1, expires=far, silver=20, deeds=1, takers=[who], target=target,
                   poster="官府" if auto_by else None, auto_by=auto_by)
        self.world_mut(lambda s: s.bounties.append(b), f"掛上通緝 {bid} {who} → {target}")

    def age_raids(self, seconds: float) -> None:
        """截殺的冷卻與護身往前挪（只靠步數等不到 3 小時與 1 小時）。"""
        def fn(w) -> None:
            for book in (w.raids, w.raided, w.clashes, w.clashed):
                for k in list(book):
                    book[k] -= seconds
        self.world_mut(fn, f"冷卻與護身往前挪 {seconds}")

    def unshield(self, who: str) -> None:
        from tianxia.characters import name_key

        def fn(w) -> None:
            w.raided.pop(name_key(who), None)
            w.clashed.pop(name_key(who), None)
        self.world_mut(fn, f"{who} 的護身解了")

    def spar(self, a: str, b: str, verb: str = "invite") -> None:
        self.act(a, b, "spar", arg=verb)

    # ── 前半 ──

    def seat(self) -> None:
        town, field = self.town(), self.field()
        emit("地點", {"town": town, "field": field, "kinds": [self.kind_of(town), self.kind_of(field)]})
        for who, side in self.PLAYERS.items():
            self.place(who, field if who in self.RAIDERS else town, side)
        ins = self.ins()
        give = {self.D_A: [ins[0], ins[2]], self.D_B: [ins[1], ins[3]], self.D_C: [ins[2]], self.D_D: [ins[3]],
                self.D_E: [ins[0], ins[4]], self.D_F: [ins[0], ins[1]]}
        for who, ids in give.items():
            self.edit(who, lambda p, ids=ids: (p.insights.extend(i for i in ids if i not in p.insights), p.stats.__setitem__("xinde", 20000)))
        self.edit(self.R_NEW, lambda p: setattr(p, "joined_at", self.world.get_season().time))  # 新手期：從加入那一刻算
        for who in self.PLAYERS:
            self.edit(who, lambda p: p.stats.__setitem__("silver", 300))
        for who in self.PLAYERS:
            self.main(who)
        self.world_cross("坐定")

    def spar_cards(self) -> None:
        """切磋的卡：沒有邀請時一顆；對方在忙、體力不夠時寫為什麼。"""
        self.sync(self.S_A, self.S_B, self.S_C, self.S_D, self.S_E)
        self.card_of(self.S_A, self.S_B)
        self.card_of(self.S_A, self.S_C)
        self.busy(self.S_D, True)
        self.card_of(self.S_A, self.S_D)
        self.spar(self.S_A, self.S_D)  # 對方此刻正忙
        self.busy(self.S_D, False)
        self.stamina(self.S_E, 0.0)
        self.card_of(self.S_A, self.S_E)
        self.spar(self.S_A, self.S_E)  # 對方體力不夠
        self.spar(self.S_E, self.S_A)  # 自己體力不夠
        self.refill(self.S_E)
        self.act(self.S_A, "無名氏", "spar", arg="invite")
        self.act(self.S_A, self.S_B, "spar", arg="bogus")  # 沒有這種動作的參數
        self.act(self.S_A, self.S_B, "spar", arg="yes")  # 沒有邀請
        self.world_cross("切磋看卡之後")

    def spar_fights(self) -> None:
        """發邀請、重發、婉拒、收回、答應打一場（大勝、僵持、落敗）、同一對一天滿了。"""
        a, b, c, d = self.S_A, self.S_B, self.S_C, self.S_D
        self.spar(a, b)
        self.spar(a, b)  # 已經有一張
        self.main(b)
        self.main(a)
        self.reply(b, a, "no", "spar")  # 婉拒
        self.cross_state(a, "被婉拒")
        self.spar(a, b)
        self.card_of(b, a)
        self.spar(a, b, "cancel")  # 發邀請的人收回
        self.spar(b, a, "cancel")  # 不是自己發的邀請
        self.spar(a, b)
        with self.forced("大勝"):
            self.act(b, a, "spar", arg="yes")  # 答應：打一場
        for who in (a, b):
            self.cross_state(who, "打完（發起的大勝）")
        self.world_cross("切磋一場之後")
        # 同一對人一天兩場：第一場僵持、第二場落敗，第三場被擋
        self.spar(c, d)
        with self.forced("僵持"):
            self.act(d, c, "spar", arg="yes")
        self.refill(c, d)
        self.spar(c, d)
        with self.forced("落敗"):
            self.reply(d, c, "yes", "spar")  # 選單上答應
        self.refill(c, d)
        for who in (c, d):
            self.cross_state(who, "打完（僵持、落敗）")
        self.card_of(c, d)
        self.spar(c, d)  # 今天這一對打滿了
        self.spar(d, c)
        self.world_cross("切磋打滿之後")

    def spar_refused(self) -> None:
        """對方走了（選單答應，發邀請的人收到一句）；答應前累倒；逾時作廢。"""
        a, b, c, e = self.S_A, self.S_B, self.S_C, self.S_E
        self.spar(b, e)
        self.hop(b, self.field())  # 發邀請的人走了
        self.reply(e, b, "yes", "spar")
        self.main(b)
        self.hop(b, self.town())
        self.main(e)
        self.spar(e, a)
        self.stamina(e, 0.0)  # 答應之前累倒
        self.reply(a, e, "yes", "spar")
        self.refill(e)
        self.main(e)
        self.spar(a, c)  # 逾時作廢
        self.expire_all(a)
        self.reply(c, a, "yes", "spar")
        self.act(c, a, "spar", arg="yes")
        for who in (a, b, c, e):
            self.cross_state(who, "切磋被拒絕之後")
        self.world_cross("切磋被拒絕之後")

    def discuss_cards(self) -> None:
        """論武的卡：每一樣出得了的一顆；沒有東西可出；體力不夠、對方在忙寫為什麼。"""
        self.sync(self.D_A, self.D_B, self.D_C, self.D_D, self.D_E, self.D_F, self.S_B)
        self.card_of(self.D_A, self.D_B)
        self.card_of(self.S_B, self.D_A)  # 身上沒有東西可出
        self.stamina(self.D_C, 0.0)
        self.card_of(self.D_A, self.D_C)
        self.act(self.D_A, self.D_C, "discuss", arg=f"invite:{self.item(0)}")  # 對方體力不夠
        self.refill(self.D_C)
        self.busy(self.D_D, True)
        self.act(self.D_A, self.D_D, "discuss", arg=f"invite:{self.item(0)}")  # 對方在忙
        self.busy(self.D_D, False)
        self.act(self.D_A, self.D_B, "discuss", arg="invite")  # 沒帶東西
        self.act(self.D_A, self.D_B, "discuss", arg="invite:insight:沒有這個意境")  # 身上沒有這一樣
        self.act(self.D_A, self.D_B, "discuss", arg="bogus")
        self.act(self.D_A, self.D_B, "discuss", arg=f"yes:{self.item(1)}")  # 沒有邀請

    def discuss_make(self) -> None:
        """帶一樣發邀請、重發、婉拒、收回；答應時挑一樣：A 段開單、B 段模型擋掉走 NO_NAME、C 段帶 proposed；配方已有；已經有了。"""
        a, b, e, f = self.D_A, self.D_B, self.D_E, self.D_F
        self.act(a, b, "discuss", arg=f"invite:{self.item(0)}")
        self.act(a, b, "discuss", arg=f"invite:{self.item(2)}")  # 已經有一張
        self.main(b)
        self.main(a)
        self.card_of(b, a)
        self.reply(b, a, "no", "discuss")  # 婉拒
        self.act(a, b, "discuss", arg=f"invite:{self.item(0)}")
        self.act(a, b, "discuss", arg="cancel")  # 收回
        self.act(b, a, "discuss", arg="cancel")  # 已經不在了
        self.act(a, b, "discuss", arg=f"invite:{self.item(0)}")
        self.reply(b, a, "yes", "discuss")  # 選單上答應（要在卡上挑一樣）
        with self.model(None):  # B 段模型擋掉：走 NO_NAME，C 段用退路字表
            self.act(b, a, "discuss", arg=f"yes:{self.item(1)}")
        for who in (a, b):
            self.cross_state(who, "論武首創（模型擋著）")
        self.world_cross("論武首創之後")
        # 已經有了：他們兩個再來一次，出的還是那兩樣
        self.act(a, b, "discuss", arg=f"invite:{self.item(0)}")
        with self.model({"name": "不該用到的名", "description": "不會用到"}):
            self.act(b, a, "discuss", arg=f"yes:{self.item(1)}")
        self.main(b)
        self.main(a)
        # 配方已有：另一對人合同一個配方（A 段不開單），先出同一樣被擋
        self.act(e, f, "discuss", arg=f"invite:{self.item(0)}")
        self.act(f, e, "discuss", arg=f"yes:{self.item(0)}")  # 出同一樣
        self.card_of(f, e)
        with self.model({"name": "不該再取的名", "description": "不會用到"}):
            self.act(f, e, "discuss", arg=f"yes:{self.item(1)}")
        for who in (e, f):
            self.cross_state(who, "論武配方已有")
        self.world_cross("論武配方已有之後")

    def discuss_refused(self) -> None:
        """心得不夠、體力不夠（答應前累倒）、對方走了；逾時作廢。"""
        a, c, d, f = self.D_A, self.D_C, self.D_D, self.D_F
        self.act(c, f, "discuss", arg=f"invite:{self.item(2)}")
        self.edit(f, lambda p: p.stats.__setitem__("xinde", 0))
        self.act(f, c, "discuss", arg=f"yes:{self.item(1)}")  # 心得不夠
        self.card_of(f, c)
        self.edit(f, lambda p: p.stats.__setitem__("xinde", 20000))
        self.act(c, f, "discuss", arg="cancel")
        self.act(a, d, "discuss", arg=f"invite:{self.item(2)}")
        self.stamina(d, -100.0)  # 答應之前累倒（同步補不回 3 點）；沒答成，(2,3) 這個配方留給後半首創
        self.act(d, a, "discuss", arg=f"yes:{self.item(3)}")
        self.refill(d)
        self.main(a)
        self.act(a, d, "discuss", arg=f"invite:{self.item(2)}")
        self.hop(a, self.field())  # 發邀請的人走了
        self.reply(d, a, "no", "discuss")
        self.hop(a, self.town())
        self.main(a)
        self.act(a, d, "discuss", arg=f"invite:{self.item(2)}")  # 逾時作廢
        self.expire_all(a)
        self.act(d, a, "discuss", arg=f"yes:{self.item(3)}")
        for who in (a, c, d, f):
            self.cross_state(who, "論武被拒絕之後")
        self.world_cross("論武被拒絕之後")

    def raid_cards(self) -> None:
        """截殺的卡：敵對陣營一顆（勝算）、同陣營沒有、散人沒有；散人揭了通緝才有；關著時不畫。"""
        g1, g2, h1, h2, rg = self.R_G1, self.R_G2, self.R_H1, self.R_H2, self.R_RANGER
        self.sync(*self.RAIDERS)
        self.card_of(g1, h1)
        self.card_of(g1, g2)
        self.card_of(rg, h2)
        self.card_of(g1, rg)
        self.bounty("w1", rg, h2)
        self.card_of(rg, h2)
        with self.tuned(owner=self.c.config.raid, enabled=False):
            self.card_of(g1, h1)
            self.act(g1, h1, "raid")
        self.act(g1, g2, "raid")  # 同陣營
        self.act(rg, h1, "raid")  # 散人沒揭通緝
        self.act(g1, "無名氏", "raid")
        self.world_cross("截殺看卡之後")

    def raid_fights(self) -> None:
        """打贏、打輸、僵持、對方下線（還在窗口內）、窗口外、散人揭通緝交差、官府通緝的惡名；冷卻與護身。"""
        g1, g2, h1, h2, rg, off = self.R_G1, self.R_G2, self.R_H1, self.R_H2, self.R_RANGER, self.R_OFF
        self.edit(h1, lambda p: p.stats.__setitem__("evil", 50))
        self.bounty("o1", g1, h1, auto_by="官府")
        # 散人揭了通緝打贏：交差（賞銀、俠名）
        self.refill(rg)
        with self.forced("大勝"):
            self.act(rg, h2, "raid")
        for who in (rg, h2):
            self.cross_state(who, "散人截殺通緝的人")
        self.unshield(h2)
        with self.forced("大勝"):
            self.act(g1, h1, "raid")  # 打贏（官府通緝的惡名）
        for who in (g1, h1):
            self.cross_state(who, "截殺打贏")
        self.act(g1, h1, "raid")  # 冷卻中
        self.act(g2, h1, "raid")  # 被截過的護身
        with self.forced("落敗"):
            self.act(g2, h2, "raid")  # 打輸
        for who in (g2, h2):
            self.cross_state(who, "截殺打輸")
        with self.forced("僵持"):
            self.act(h2, g1, "raid")  # 僵持
        for who in (h2, g1):
            self.cross_state(who, "截殺僵持")
        # 對方下線：同步是十幾個鐘頭前，還在窗口內
        self.edit_state(off, lambda s: setattr(s, "last_real", CLOCK[0] - 20 * 3600.0))
        self.card_of(g2, off)
        self.refill(g2)
        with self.forced("大勝"):
            self.act(g2, off, "raid")
        self.cross_state(off, "下線時被截殺")
        self.main(off)
        with self.tuned(presence_seconds=900.0):  # 窗口縮小：他在窗口外
            self.edit_state(off, lambda s: setattr(s, "last_real", CLOCK[0] - 5000.0))
            self.card_of(g1, off)
            self.act(g1, off, "raid")
        self.world_cross("截殺打完之後")

    def raid_refused(self) -> None:
        """城鎮擋、新手期（雙方）、體力不夠、在忙、混戰過的拒絕話（FB-607）。"""
        from tianxia.characters import name_key

        g1, g2, h1, new = self.R_G1, self.R_G2, self.R_H1, self.R_NEW
        self.act(self.S_A, self.S_C, "raid")  # 兩個人都在城鎮裡
        self.card_of(self.S_A, self.S_C)
        self.act(g2, new, "raid")  # 對方在新手期
        self.act(new, g2, "raid")  # 自己在新手期
        self.stamina(g2, 0.0)
        self.act(g2, self.R_OFF, "raid")  # 體力不夠
        self.refill(g2)
        self.busy(g2, True)
        self.act(g2, h1, "raid")  # 自己在忙
        self.busy(g2, False)

        def fn(w) -> None:  # 混戰過（翻地與爭搶）寫的那一筆：照實寫交過手，不寫截殺過
            key, t = f"{name_key(g2)}>{name_key(self.R_H2)}", w.time - 10.0
            w.raids[key] = w.clashes[key] = t
            w.raided[name_key(self.R_H2)] = w.clashed[name_key(self.R_H2)] = t
        self.world_mut(fn, "擺混戰過的那一筆")
        self.act(g2, self.R_H2, "raid")  # 冷卻（混戰過）
        self.act(g1, self.R_H2, "raid")  # 護身（混戰過）
        self.world_cross("截殺被拒絕之後")

    def raid_flee(self) -> None:
        """策馬脫身：他的馬比較快，卡上多一句；機會給滿時跑掉（不打、誰都不失什麼、體力冷卻照付）。"""
        from tianxia.state import Equipment

        g1, h1 = self.R_G1, self.R_H1
        self.unshield(h1)
        self.age_raids(self.c.config.raid.pair_cooldown_seconds + 1.0)
        self.refill(g1, h1)
        with self.tuned(owner=self.c.config.mounts, enabled=True):
            self.edit(h1, lambda p: setattr(p, "mount", Equipment(id="騎:1", slot="mount", name="棗騮馬", tier=3, quality="上品", edge=100)))
            self.card_of(g1, h1)  # 確認句多一句馬
            with self.fleeing(1.0):
                self.act(g1, h1, "raid")  # 跑掉了
            for who in (g1, h1):
                self.cross_state(who, "策馬脫身")
            self.age_raids(self.c.config.raid.pair_cooldown_seconds + 1.0)
            self.unshield(h1)
            self.refill(g1)
            with self.fleeing(0.0):
                with self.forced("險勝"):
                    self.act(g1, h1, "raid")  # 擲了沒跑掉：照打
            for who in (g1, h1):
                self.cross_state(who, "沒跑掉")
        self.world_cross("策馬脫身之後")

    def half(self) -> None:
        """前半停在：兩張切磋邀請（鳴鏑→臨淵、負霜→枕流）、一張論武邀請（觀瀾→聽松，首創）、一對人今天打了一場、截殺的冷卻與護身還沒過。"""
        self.refill(*self.PLAYERS)
        self.sync(self.S_A, self.S_B, self.S_C, self.S_E, self.D_C, self.D_D, self.R_G1, self.R_H1)
        self.age_raids(self.c.config.raid.pair_cooldown_seconds + 1.0)
        self.unshield(self.R_H1)
        with self.forced("大勝"):
            self.act(self.R_G1, self.R_H1, "raid")  # 冷卻與護身這一下剛記
        self.spar(self.S_A, self.S_B)
        self.spar(self.S_C, self.S_E)
        self.act(self.D_C, self.D_D, "discuss", arg=f"invite:{self.item(2)}")
        self.main(self.S_B)
        self.main(self.S_E)
        self.main(self.D_D)
        self.world_cross("前半停在這裡")
        for who in (self.S_A, self.S_E, self.D_D, self.R_H1):
            self.cross_state(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.S_B, self.S_E, self.D_D, self.R_G1):
            self.main(who)

    def answer(self) -> None:
        """新程式接著答：臨淵答應切磋（今天這一對打了一場，這是第二場）；枕流累倒答不了、負霜收到一句；聽松答論武（首創，模型回了名字，C 段帶 proposed）。"""
        self.sync(self.S_A, self.S_B, self.S_C, self.S_E, self.D_C, self.D_D)
        with self.forced("險勝"):
            self.act(self.S_B, self.S_A, "spar", arg="yes")
        self.stamina(self.S_E, -100.0)  # 同步補不回 6 點：選單上那一顆是灰的，改走卡上的答應（卡的路不看選單）
        self.act(self.S_E, self.S_C, "spar", arg="yes")
        self.main(self.S_C)
        self.refill(self.S_E, self.S_A, self.S_B)
        self.spar(self.S_A, self.S_B)  # 今天這一對打滿了
        with self.model({"name": "霧簷論", "description": "簷下霧氣不散的意思"}):
            self.act(self.D_D, self.D_C, "discuss", arg=f"yes:{self.item(3)}")
        for who in (self.S_A, self.S_B, self.S_C, self.S_E, self.D_C, self.D_D):
            self.cross_state(who, "答完")
        self.world_cross("接手之後")

    def raid_again(self) -> None:
        """跨過冷卻與護身再截殺：冷卻還在、護身還在、都過了就打。"""
        g1, h1 = self.R_G1, self.R_H1
        self.refill(g1, self.R_G2)
        self.act(g1, h1, "raid")  # 前半記的冷卻與護身還在
        self.age_raids(self.c.config.raid.shield_seconds + 1.0)
        self.act(self.R_G2, h1, "raid")  # 護身過了、這一對沒打過
        self.refill(self.R_G2)
        self.age_raids(self.c.config.raid.pair_cooldown_seconds)
        with self.forced("落敗"):
            self.act(g1, h1, "raid")  # 冷卻也過了
        for who in (g1, h1, self.R_G2):
            self.cross_state(who, "跨過冷卻之後")
        self.world_cross("跨過冷卻之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個——隨鴻（官軍，站城裡，收到切磋與論武的邀請；模型擋著那幾輪不答論武，模型回了才答）、逐電（黃巾，站野外，此地有敵對陣營的人時截殺）；
        整季機器人眼前有邀請的選單與挑法。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        town, field = self.town(), self.field()
        for who in self.PLAYERS:
            self.hop(who, field if who in (self.R_G1, self.R_G2) else town)
        on = any(f.id == "guan" for f in self.c.scenario.factions)
        sides = ["guan", "huang"]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=sides[i] if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, (town if i == 0 else field), None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.insights.extend(x for x in self.ins()[:4] if x not in p.insights)
            p.stats["xinde"] = 20000
            self.chars.save(g.state)
        bot_a, bot_b = self.BOT_SEATS
        self.refill(self.S_A, self.D_E, self.R_G1, self.R_G2)
        self.sync(self.S_A, self.D_E, self.R_G1, self.R_G2)
        self.card_of(self.S_A, bot_a)  # 假人的卡跟真人的一樣
        self.card_of(self.R_G1, bot_b)
        self.edit(self.D_B, lambda p: p.insights.append(self.ins()[5]) if self.ins()[5] not in p.insights else None)
        self.world_cross("假人前")

        def back(invite) -> None:  # 假人一離開原地就看不到邀請（要在發邀請的那個地點才答）：每一段之前把他們放回原位再發邀請
            for i, name in enumerate(self.BOT_SEATS):
                self.hop(name, town if i == 0 else field)
            self.refill(self.S_A, self.D_E, self.D_B, self.R_G1, self.R_G2)
            self.sync(self.S_A, self.D_E, self.D_B, self.R_G1, self.R_G2)
            invite()
        segments = [  # （名稱, 模型回的, 發邀請, 幾輪）：假人這邊沒有 ins[4]、ins[5]，跟他的每一樣都是新配方，A 段開單
            ("模型擋著", None, lambda: self.act(self.D_E, bot_a, "discuss", arg=f"invite:{self.item(4)}"), 2),
            ("模型回了", {"name": "雲駐論", "description": "雲停在簷上不走的意思"},
             lambda: self.act(self.D_B, bot_a, "discuss", arg=f"invite:{self.item(5)}"), 2),
            ("切磋", None, lambda: self.spar(self.S_A, bot_a), 1),
        ]
        from tianxia.ollama_client import OllamaClient

        # 給假人程式一個取名的 client（run_bots.py 的做法）：沒給的話取名的名額是關的，答論武遇到首創就放著不答
        runner = BotRunner(self.c, self.world, self.chars, client=OllamaClient.from_config(self.c.config), rng=random.Random(43),
                           clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            with self.bot_dice(1.0):
                for stage, name, invite, ticks in segments:
                    back(invite)
                    with self.model(name):
                        for _ in range(ticks * int(os.environ.get("SB_CROSS_TICKS", "1"))):
                            STEP[0] += 4
                            self.begin()
                            report = runner.tick()
                            totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed,
                                          online=report.online, named=report.named)
                    emit(f"假人 {stage}之後", dict(sorted(totals.items())))
                    self.world_cross(f"假人 {stage}之後")
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        for who in (*self.BOT_SEATS, self.S_A, self.D_E, self.R_G1, self.R_G2):
            self.cross_state(who, "假人之後")
        for name in self.BOT_SEATS:
            self.card_of(self.S_A, name)
        # 整季機器人眼前有人遞來的邀請：選單上有 invite:，挑法不按它（bot.pick 排除）
        self.sync(self.S_B, self.S_D)
        self.refill(self.S_B, self.S_D)
        self.spar(self.S_B, self.S_D)
        self.begin()
        solo = self.server.game_for(self.S_D)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（有邀請）", [o.id for o in opts])
        emit("整季機器人挑的（有邀請）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(30)}))

    def season(self) -> None:
        """休季：切磋、論武、截殺的鈕不畫、直接打 API 也被擋；開下一季：邀請與帳整個重來。"""
        self.do(ADMIN, "end_season")
        self.world_cross("收季之後")
        self.refill(self.S_A, self.S_B, self.R_G1, self.R_H1, self.D_A, self.D_B)
        for who in (self.S_A, self.S_B, self.D_A, self.D_B):
            self.hop(who, self.town())
        for who in (self.R_G1, self.R_H1):
            self.hop(who, self.field())
        self.sync(self.S_A, self.S_B, self.D_A, self.D_B, self.R_G1, self.R_H1)
        self.card_of(self.S_A, self.S_B)
        self.card_of(self.D_A, self.D_B)
        self.card_of(self.R_G1, self.R_H1)
        self.spar(self.S_A, self.S_B)
        self.act(self.D_A, self.D_B, "discuss", arg=f"invite:{self.item(0)}")
        self.act(self.R_G1, self.R_H1, "raid")
        self.do(ADMIN, "next_season")
        for who in (self.S_A, self.S_B, self.D_A, self.D_B, self.R_G1, self.R_H1):
            self.main(who)
            self.cross_state(who, "換季之後")
        self.world_cross("換季之後")


# 改一個字（selftest）：被截過的護身那一句（Game.raid_refusal；搬之前在 engine.py，搬進包之後在 tianxia/features/peers/raid_actions.py〔計畫 1.1 的檔名；搬的人照實際的檔名改第 2 項〕），week7 raid_fights 那一段抓到
register_track("crossblade", CrossbladeScenario, (("tianxia/engine.py", "tianxia/features/peers/raid_actions.py"), ("剛被人截殺過，元氣未復，這時下手太不講江湖道義。", "剛被人截殺過，元氣未復，這時下手太不講江湖道義！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
