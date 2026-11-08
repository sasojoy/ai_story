"""same_behavior 一軌一檔：omen（這一檔登記 omen）。"""
from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.military import MilitaryScenario

# ═══════════════════════════ omen：軍情二軌（全部拆包第 34 批，dev/military-2） ═══════════════════════════
# 機緣（opp:）與伏筆（fs:）：出現、接下、做完、過期；效果帶伏筆的欄位；叛投時手上有機緣與密謀。計畫 docs/superpowers/plans/2026-11-06-軍情包-第2批.md。

OMEN_OPP = ("opp:",)


class OmenScenario(MilitaryScenario):
    """軍情二軌（--track omen，自己一個資料庫；沿用軍情一軌的小工具 tuned／fights／options／press／menu／hop／forward_to_week）。
    機緣：管理者給機緣（十三種各給一個合適的人，另外：散人、別的陣營、階不夠、集體密謀型、已經給過、沒有這個機緣、沒有這個人）；累積型自然做（第 2 階行動
    湊次數，拿到東西）；天時地利型聽線索、到地點等時段去試；拼圖型拿齊東西去呈交；推理型到問話的人那裡指認（錯的、對的）；集體密謀（請命、響應、做一處、
    過了期限）。伏筆：管理者給片段（要有鏈、要是他那一方的、聽過的、超出的、不存在的）；行動之後自然聽到（機率調到一定聽到）；最後一步（到地點、擺好物品、
    等時間窗、看題、答錯、冷卻、答對、作罷、有追問的）；江湖頁的個人線索與本週卡的「你這一步」。
    **前半停在兩件寫到一半的事**：機緣接了還沒做完（累積型拿到東西還沒送、拼圖型湊齊還沒呈交、天時地利型拿到密信還沒送、密謀牽頭了還缺幾處）、伏筆埋了還沒收
    （聽過片段、物品擺好、最後一步看了題還沒答）。後半：新程式接著送、交、答，再過期、叛投（手上有機緣與響應的密謀）、換季。
    假人：BotRunner 兩個站在機緣與伏筆的選項眼前跑幾輪（機器人不碰 opp:、fs:，輸出裡 acted 的數字與存檔雜湊寫下來）、整季機器人眼前的選單與挑的。
    沒有機緣、沒有伏筆的內容（測試內容）同一串 API 照打，寫「沒有」。"""

    G_ACC, G_NAT, G_TIME, G_PUZ, G_LEAD, G_JOIN = "章臨淵", "祝雲棲", "韓暮寒", "紀長風", "葉凌霜", "桑晚照"
    G_FS, G_FS2, G_LOW = "邵清鴻", "庾子期", "尹新芽"
    H_DED, H_NAT, H_TIME, H_LEAD, H_JOIN, H_FS = "屠滄浪", "宗岳", "伍寒松", "穆長亭", "冉飛星", "戴鳴玉"
    HAO = "裘千尋"
    LONE = "白無相"
    PLAYERS = {G_ACC: "guan", G_NAT: "guan", G_TIME: "guan", G_PUZ: "guan", G_LEAD: "guan", G_JOIN: "guan", G_FS: "guan", G_FS2: "guan",
               G_LOW: "guan", H_DED: "huang", H_NAT: "huang", H_TIME: "huang", H_LEAD: "huang", H_JOIN: "huang", H_FS: "huang",
               HAO: "haoqiang", LONE: None}
    BOT_SEATS = ["象甲", "象乙"]
    PHASES_FIRST = ["setup", "seat", "offers", "refusals", "natural", "hearing", "puzzle_deduce", "plots", "fragments", "asking", "half"]
    PHASES_SECOND = ["resume", "finish_fs", "finish_items", "finish_plots", "expire", "defect", "bots", "season"]
    PICKS = ("hub", "ask_loc", "sweep_pressed")
    sweep_pressed: list = []
    hub = "nobody"
    ask_loc: dict = {}

    # ── 小工具 ──

    def opps(self) -> list:
        return sorted(self.c.opportunities, key=lambda o: o.id)

    def chains(self) -> list:
        return sorted(self.c.foreshadows.chains, key=lambda ch: ch.id)

    def locs_of(self, model) -> list[str]:
        """一個機緣或一條鏈的內容裡寫到的地點（照字串對地點表，多找不傷）。"""
        def walk(v):
            if isinstance(v, dict):
                for x in v.values():
                    yield from walk(x)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    yield from walk(x)
            elif isinstance(v, str) and v in self.c.locations:
                yield v

        return sorted(set(walk(model.model_dump(mode="json"))))

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、陣營、階、體力、機緣與伏筆的全部欄位、最新兩則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "rank": p.rank, "stamina": p.stamina,
            "opp": {"done": list(p.opp_done), "counts": dict(sorted(p.opp_counts.items())), "items": dict(sorted(p.opp_items.items())),
                    "fronts": dict(sorted(p.opp_fronts.items())), "clues": list(p.opp_clues), "tried": dict(sorted(p.opp_tried.items())),
                    "pieces": {k: list(v) for k, v in sorted(p.opp_pieces.items())}, "settled": list(p.opp_settled), "patron": p.patron},
            "fs": {"fragments": {k: list(v) for k, v in sorted(p.fragments.items())}, "items": dict(sorted(p.clue_items.items())),
                   "counters": dict(sorted(p.fs_counters.items())), "done": list(p.fs_done),
                   "cool": dict(sorted(p.fs_cooldown_until.items())), "asking": p.fs_asking, "asked": p.fs_asked},
            "affinity": dict(sorted(p.affinities.items())), "journal": [[e.title, e.tag, list(e.lines)[:3]] for e in state.journal[:2]]})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：密謀（發起的、響應的、做完的幾處）、陣營軍情的尾巴。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {"plots": [x.model_dump(mode="json") for x in w.plots], "time": w.time,
                          "rumors": [r.text for r in w.rumors][-4:]})

    def sweep(self, who: str, locs: list[str], tag: str, prefixes: tuple = OMEN_OPP, per: int = 2, stop: bool = False,
              skip: frozenset = frozenset()) -> int:
        """逐個地點站過去，按那裡選單上這個前綴的鈕（每處最多 per 顆，灰的只寫不按；skip 裡的鈕不按）。回傳按了幾顆；按過的記在 self.sweep_pressed。"""
        pressed = 0
        for loc in locs:
            if not self.place(who, loc):
                continue
            opts = self.options(who)
            hits = [i for i in opts if i.startswith(prefixes)]
            if not hits:
                continue
            emit(f"{who} {tag} 在 {loc}", [[i, opts[i].get("label"), opts[i].get("enabled")] for i in hits])
            for i in [i for i in hits if opts[i].get("enabled") and i not in skip][:per]:
                self.choose(who, i)
                self.sweep_pressed = [*getattr(self, "sweep_pressed", []), i]
                pressed += 1
            if stop and pressed:
                break
        return pressed

    def give(self, who: str, oid: str) -> None:
        self.do(ADMIN, "give_opportunity", {"name": who, "id": oid})

    def hours(self, n: int) -> None:
        self.do(ADMIN, "fast_forward", {"hours": n})

    def chain_for(self, side: str, kind: str | None = None):
        """這一方第一條（有題的、不是夜裡的；kind 是 then＝有追問的、plain＝沒有追問的）鏈；沒有是 None。"""
        for ch in self.chains():
            f = ch.final
            if ch.side != side or not f.question or f.night:
                continue
            if ch.event in self.world.get_season().timeline:  # 大事已經發生的鏈：看題、答題都是空按
                continue
            if kind == "then" and not f.then:
                continue
            if kind == "plain" and f.then:
                continue
            return ch
        return None

    @staticmethod
    def fill_req(p, req) -> None:
        """把這一份條件擺到合格（物品、計數、情誼、捐獻；幾選一的擺第一個）。"""
        if req is None:
            return
        for k, v in (getattr(req, "clue_items", None) or {}).items():
            p.clue_items[k] = max(p.clue_items.get(k, 0), v)
        for k, v in (getattr(req, "counters", None) or {}).items():
            p.fs_counters[k] = max(p.fs_counters.get(k, 0), v)
        for k, v in (getattr(req, "affinity", None) or {}).items():
            p.affinities[k] = max(p.affinities.get(k, 0), v)
        for k, v in (getattr(req, "donations", None) or {}).items():
            p.donations[k] = max(p.donations.get(k, 0), v)
        if getattr(req, "any_of", None):
            OmenScenario.fill_req(p, req.any_of[0])

    def widen(self) -> None:
        """伏筆最後一步的時間窗拉寬（內容在這個行程裡共用，兩半各叫一次）：不靠快轉等窗開，免得把大事的日子燒掉。"""
        for ch in self.chains():
            for trip in [ch.final, *(ch.final.steps or [])]:
                if hasattr(trip, "window_days"):
                    trip.window_days = 60
        emit("伏筆時間窗", "拉寬")

    def open_ask(self, who: str, cid: str) -> None:
        """還沒在答題就按「呈證」看題。"""
        opts = self.options(who)
        if not any(i.startswith(f"fs:{cid}:") for i in opts):
            self.press(who, f"fs:{cid}", "看題")

    def need_items(self, who: str, ch) -> None:
        """擺好最後一步要的（整條的加每一趟的）：物品、計數、情誼、捐獻，再放糧草。"""
        reqs = [ch.final.requires, *[getattr(t, "requires", None) for t in (ch.final.steps or [])]]
        self.edit(who, lambda p: [self.fill_req(p, r) for r in reqs])
        self.grain(who, 40)

    # ── 前半 ──

    def seat(self) -> None:
        from tianxia.rules import front_of

        c = self.c
        fronted = [loc for loc in sorted(c.locations) if front_of(c, loc) is not None]
        guan = next((f for f in c.scenario.factions if f.id == "guan" and f.join_at), None)
        self.hub = guan.join_at[0] if guan is not None else (fronted[0] if fronted else sorted(c.locations)[0])
        self.ask_loc = {}
        self.widen()
        ranks = {self.G_PUZ: 4, self.G_LEAD: 4, self.G_JOIN: 4, self.H_DED: 4, self.H_LEAD: 4, self.H_JOIN: 4, self.G_LOW: 1}
        emit("挑的地點", {"hub": self.hub, "opps": [o.id for o in self.opps()], "chains": [ch.id for ch in self.chains()]})
        for who, side in self.PLAYERS.items():
            self.place(who, self.hub, side)
            self.edit(who, lambda p, who=who: (setattr(p, "rank", ranks.get(who, 3)), p.stats.update({"silver": 500}),
                                               setattr(p, "tutorial_step", len(self.c.tutorial.steps))))
        self.world_view("開場")

    def offers(self) -> None:
        """管理者給機緣：十三種各給一個合適的人（官軍三人、黃巾三人、豪強一人）。"""
        who_for = {"bond": {"guan": self.G_ACC, "huang": self.H_NAT, "haoqiang": self.HAO},
                   "accumulate": {"guan": self.G_ACC, "huang": self.H_NAT, "haoqiang": self.HAO},
                   "timing": {"guan": self.G_TIME, "huang": self.H_TIME, "haoqiang": self.HAO},
                   "puzzle": {"guan": self.G_PUZ}, "deduce": {"huang": self.H_DED},
                   "plot": {"guan": self.G_LEAD, "huang": self.H_LEAD}}
        if not self.c.opportunities:
            emit("機緣：這份內容沒有機緣", None)
        for o in self.opps():
            who = who_for.get(o.kind, {}).get(o.faction)
            if who is None:
                continue
            if o.kind == "accumulate" and who in (self.G_ACC, self.H_NAT):
                continue  # 累積型留給 natural 自己做
            self.give(who, o.id)
        for who in self.PLAYERS:
            self.main(who)
        for who in (self.G_ACC, self.G_TIME, self.G_PUZ, self.H_DED, self.H_TIME, self.HAO):
            self.me(who, "給了機緣之後")

    def refusals(self) -> None:
        """管理者給機緣被拒絕的幾種：別的陣營、散人、階不夠、集體密謀型、已經給過、沒有這個機緣、沒有這個人、空的名號。"""
        o = self.opps()
        guan = next((x for x in o if x.faction == "guan" and x.kind == "timing"), None)
        huang = next((x for x in o if x.faction == "huang" and x.kind == "timing"), None)
        plot = next((x for x in o if x.kind == "plot" and x.faction == "guan"), None)
        puzzle = next((x for x in o if x.kind == "puzzle"), None)
        for who, x in ((self.H_TIME, guan), (self.LONE, huang), (self.G_LOW, guan), (self.G_LEAD, plot), (self.G_TIME, guan),
                       (self.G_LOW, puzzle), (self.G_ACC, None), ("無此人", guan), ("", guan)):
            self.do(ADMIN, "give_opportunity", {"name": who, "id": x.id if x is not None else "no_such_opportunity"})

    def natural(self) -> None:
        """累積型自然做：官軍黃巾各一人在有戰線的地方按第 2 階行動，湊到次數就拿到東西（前半停在拿到東西還沒送）。"""
        for who in (self.G_NAT, self.H_NAT):
            self.place(who, self.hub)
            for k in range(4):
                self.menu(who, f"第 {k + 1} 次前", "act:rank2")
                self.press(who, "act:rank2", f"第 {k + 1} 次")
            self.me(who, "湊次數之後")

    def hearing(self) -> None:
        """行動之後自然聽到線索：把需求係數壓到最小（機率一定聽到），站在線索的大區按一次第 2 階行動。"""
        from tianxia import atlas

        regions: dict[str, str] = {}
        for loc in sorted(self.c.locations):
            r = atlas.region_of(self.c, loc)
            if r is not None:
                regions.setdefault(r.id, loc)
        wanted = sorted({r for o in self.opps() if o.kind == "timing" for r in (o.timing.clue_regions or [])}
                        | {f.region for ch in self.chains() for f in ch.fragments if f.region})
        emit("聽的大區", {r: regions.get(r) for r in wanted})
        with self.tuned(foreshadow_tiers=[(10 ** 9, 0.01)]):
            for who in (self.G_FS2, self.H_FS, self.G_TIME, self.H_TIME):
                for r in wanted:
                    if r in regions and self.place(who, regions[r]):
                        self.press(who, "act:rank2", f"在 {r} 聽")
        for who in (self.G_FS2, self.H_FS, self.G_TIME, self.H_TIME):
            self.me(who, "聽過之後")

    def puzzle_deduce(self) -> None:
        """拼圖型：湊齊的人去呈交的地點看一眼（前半不交）；推理型：到問話的人那裡指認，錯的先、對的後（隔一天再來）。"""
        for o in self.opps():
            if o.kind == "puzzle":
                emit("拼圖型呈交的地點", self.locs_of(o))
        for o in self.opps():
            if o.kind == "deduce":
                locs = self.locs_of(o)
                self.sweep_pressed = []
                self.sweep(self.H_DED, locs, "指認", prefixes=("opp:accuse:",), per=1)  # 一天只算一次：先按第一個（錯的）
                self.me(self.H_DED, "指認之後")

    def plots(self) -> None:
        """集體密謀：官軍、黃巾各一場，牽頭的在有己方人物的地方請命、另一個響應、各做一處（前半停在還缺幾處）。"""
        for lead, join in ((self.G_LEAD, self.G_JOIN), (self.H_LEAD, self.H_JOIN)):
            plot = next((o for o in self.opps() if o.kind == "plot" and o.faction == self.PLAYERS[lead]), None)
            if plot is None:
                emit(f"{lead} 沒有密謀可發起", None)
                continue
            petition = None
            for loc in sorted(self.c.locations):
                self.place(lead, loc)
                if self.options(lead).get(f"opp:plot:{plot.id}", {}).get("enabled"):
                    petition = loc
                    break
            emit(f"{lead} 請命的地點", petition)
            if petition is not None:
                self.choose(lead, f"opp:plot:{plot.id}")
            self.world_view(f"{lead} 請命之後")
            self.place(join, self.hub)
            self.sweep(join, [self.hub], "響應", prefixes=("opp:join:",), per=1)
            self.sweep(lead, self.locs_of(plot), "牽頭做一處", prefixes=("opp:part:",), per=1)
            self.sweep(join, self.locs_of(plot), "響應的做一處", prefixes=("opp:part:",), per=1)
            self.me(lead, "密謀之後")
        self.world_view("兩場密謀之後")

    def fragments(self) -> None:
        """管理者給伏筆片段：每一條鏈給對的那一方（前兩則）；也給不對的（別的陣營、散人）、聽過的、超出的、格式不對的、不存在的鏈與人。"""
        if not self.chains():
            emit("伏筆：這份內容沒有伏筆", None)
        self.do(ADMIN, "give_fragment", {"name": self.G_FS, "id": "no_such_chain:0"})  # 沒有伏筆的內容也走一次管理者的入口
        for ch in self.chains():
            who = {"guan": self.G_FS, "huang": self.H_FS}.get(ch.side)
            if who is None:
                continue
            for i in range(min(2, len(ch.fragments))):
                self.do(ADMIN, "give_fragment", {"name": who, "id": f"{ch.id}:{i}"})
        ch = self.chain_for("guan")
        other = self.chain_for("huang")
        if ch is not None and other is not None:
            for who, ref in ((self.G_FS, f"{ch.id}:0"), (self.H_FS, f"{ch.id}:2"), (self.LONE, f"{ch.id}:2"), (self.G_FS, f"{ch.id}:99"),
                             (self.G_FS, f"{ch.id}:x"), (self.G_FS, "no_such_chain:0"), ("無此人", f"{ch.id}:2")):
                self.do(ADMIN, "give_fragment", {"name": who, "id": ref})
        for ch in self.chains():
            who = {"guan": self.G_FS, "huang": self.H_FS}.get(ch.side)
            if who is not None:
                for i in range(2, len(ch.fragments)):
                    self.do(ADMIN, "give_fragment", {"name": who, "id": f"{ch.id}:{i}"})
        for who in (self.G_FS, self.H_FS):
            self.main(who)
            self.me(who, "給了片段之後")
            self.call(who, "GET", "/api/main")

    def asking(self) -> None:
        """最後一步：擺好物品、等到時間窗開、按「呈證」看題（前半停在看了題還沒答）。官軍一人、黃巾一人；有追問的鏈留給作罷與追問。"""
        for who, side, kind in ((self.G_FS, "guan", "plain"), (self.H_FS, "huang", "plain"), (self.G_FS2, "guan", "then")):
            ch = self.chain_for(side, kind) or self.chain_for(side)
            if ch is None:
                emit(f"{who} 沒有可走的鏈", None)
                continue
            self.ask_loc[who] = [ch.id, ch.final.location]
            self.need_items(who, ch)
            for i in range(len(ch.fragments)):
                self.do(ADMIN, "give_fragment", {"name": who, "id": f"{ch.id}:{i}"})
            self.place(who, ch.final.location)
            opt = self.options(who).get(f"fs:{ch.id}")
            opened = opt is not None and bool(opt.get("enabled"))
            emit(f"{who} 最後一步", {"chain": ch.id, "at": ch.final.location, "opened": opened})
            self.menu(who, "最後一步的鈕", "fs:")
            if opened:
                self.press(who, f"fs:{ch.id}", "看題")
                self.menu(who, "看題之後", "fs:")
            self.me(who, "看題之後")
        self.call(self.G_FS, "GET", "/api/main")

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".omen.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".omen.json").read_text(encoding="utf-8")).items():
            setattr(self, k, v)
        self.widen()  # 登入就同步、本週卡要讀時間窗：先拉寬，後半才跟整段一樣
        self.login_all()
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "接手")

    def finish_items(self) -> None:
        """前半拿著的東西：累積型送去（有主將的地方，逐處找）、拼圖型呈交；隔天再指認；天時地利型每三個小時換個時段到地點試。"""
        sides = {f.id: f for f in self.c.scenario.factions}
        for who in (self.G_ACC, self.G_NAT, self.H_NAT, self.HAO, self.G_PUZ, self.G_TIME, self.H_TIME):
            held = self.chars.load(who).player
            if not (held.opp_items or held.opp_pieces):
                emit(f"{who} 手上沒有要送的", None)
                continue
            side = sides.get(self.PLAYERS[who] or "")
            where = [self.hub, *(side.join_at if side is not None else [])]
            for o in self.opps():
                if o.faction == self.PLAYERS[who]:
                    where += self.locs_of(o)
            self.sweep(who, list(dict.fromkeys(where + sorted(self.c.locations))), "送交", prefixes=("opp:deliver:", "opp:present:"), per=3, stop=True)
            self.me(who, "送交之後")
        self.hours(24)
        for o in self.opps():
            if o.kind == "deduce":
                for day in range(3):  # 每天換一個沒指認過的，指認對了選單上的鈕就沒了
                    tried = frozenset(getattr(self, "sweep_pressed", []))
                    self.sweep(self.H_DED, self.locs_of(o), f"隔天指認 {day}", prefixes=("opp:accuse:",), per=1, skip=tried)
                    self.me(self.H_DED, f"隔天指認之後 {day}")
                    self.hours(24)
        for step in range(24):  # 天時地利型：每個小時換個時段（黎明這種窄的窗三小時一步會跳過），站到地點試一次
            self.hours(1)
            for who in (self.G_TIME, self.H_TIME, self.HAO):
                for o in self.opps():
                    if o.kind == "timing" and o.faction == self.PLAYERS[who]:
                        self.sweep(who, self.locs_of(o), f"時段 {step}", prefixes=("opp:try:", "opp:deliver:"), per=1)
        for who in (self.G_TIME, self.H_TIME, self.HAO):  # 拿到密信的把信送去
            if self.chars.load(who).player.opp_items:
                self.sweep(who, sorted(self.c.locations), "送信", prefixes=("opp:deliver:",), per=1, stop=True)
            self.me(who, "試過之後")

    def hub_list(self) -> list[str]:
        return [self.hub]

    def finish_plots(self) -> None:
        """密謀接著做：響應的與牽頭的把還缺的處補齊（逐處站過去），再同步結算。"""
        for lead, join in ((self.G_LEAD, self.G_JOIN), (self.H_LEAD, self.H_JOIN)):
            for o in self.opps():
                if o.kind == "plot" and o.faction == self.PLAYERS[lead]:
                    for who in (lead, join, lead, join):
                        self.sweep(who, self.locs_of(o), "補一處", prefixes=("opp:part:", "opp:join:"), per=1)
            for who in (lead, join):
                self.main(who)
                self.me(who, "密謀結算之後")
        self.world_view("密謀補齊之後")

    def finish_fs(self) -> None:
        """前半看了題的人接著答：先答錯（冷卻、可能收走物品），冷卻清掉再答對；有追問的鏈走完追問；另一個人看了題按作罷。"""
        for who, (cid, loc) in sorted(self.ask_loc.items()):
            ch = next((x for x in self.chains() if x.id == cid), None)
            if ch is None:
                continue
            f = ch.final
            right = f.answer if not str(f.answer).startswith("tianji") else f.options[0].id
            wrong = next((o.id for o in f.options if o.id != right), None)
            self.place(who, loc)
            self.need_items(who, ch)
            self.menu(who, "接著答前", "fs:")
            if who == self.G_FS2:
                self.open_ask(who, cid)
                self.press(who, "fs:leave", "作罷")
                self.me(who, "作罷之後")
            elif wrong is not None:
                self.open_ask(who, cid)
                self.press(who, f"fs:{cid}:{wrong}", "答錯")
                self.menu(who, "答錯之後", "fs:")
                self.me(who, "答錯之後")
                self.edit(who, lambda p: p.fs_cooldown_until.clear())  # 冷卻當作過了（不靠快轉燒掉大事的日子）
                self.need_items(who, ch)
                self.place(who, loc)
            self.open_ask(who, cid)
            self.press(who, f"fs:{cid}:{right}", "答對")
            for ask in (f.then or []):
                a = ask.answer if not str(ask.answer).startswith("tianji") else ask.options[0].id
                self.press(who, f"fs:{cid}:{a}", "追問")
            self.menu(who, "答對之後", "fs:")
            self.me(who, "答對之後")
        for who in (self.G_FS, self.H_FS, self.G_FS2):
            self.main(who)

    def expire(self) -> None:
        """過期：沒補齊的密謀過了期限（作罷、結算說失敗）；時間窗過了的伏筆按鈕變灰或不見。"""
        for _ in range(12):
            self.hours(24)
            w = self.world.get_season()
            if w.ended or all(x.status != "open" or w.time > x.deadline for x in w.plots):
                break
        for who in (self.G_LEAD, self.G_JOIN, self.H_LEAD, self.H_JOIN, self.G_FS, self.H_FS, self.G_ACC):
            self.main(who)
            self.me(who, "過期之後")
        self.world_view("過期之後")

    def defect(self) -> None:
        """叛投：官軍的人手上有機緣的進度與響應的密謀，到黃巾的投靠點按叛投、確定（機緣清掉、聽過的線索留下、響應的密謀退出）。"""
        target = next((f for f in self.c.scenario.factions if f.id == "huang" and f.join_at), None)
        if target is None:
            emit("叛投：這份內容沒有黃巾", None)
            return
        who = self.G_NAT
        self.edit(who, lambda p: (p.opp_done.append("對照"), p.opp_counts.update({"對照": 1}), p.opp_items.update({"對照": "信物"}),
                                  p.opp_clues.append("對照線索"), p.opp_tried.update({"對照": 1})))
        self.me(who, "叛投之前")
        self.place(who, target.join_at[0])
        ids = [i for i in self.options(who) if i.startswith("defect:")]
        emit(f"{who} 叛投那幾顆", ids)
        if ids:
            self.choose(who, "defect:huang" if "defect:huang" in ids else ids[0])
            self.choose(who, "defect:confirm")
        self.me(who, "叛投之後")
        self.world_view("叛投之後")

    def bots(self) -> None:
        """假人：兩個官軍站在機緣的東西與伏筆的鈕眼前跑幾輪（機器人不按 opp:、fs:）；整季機器人眼前的選單與挑的。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=191 + i, faction="guan", season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey, p.rank = "guan", self.hub, None, 3
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.opp_items.update({o.id: "（對照）信物" for o in self.opps() if o.faction == "guan" and o.kind == "accumulate"})
            p.fragments.update({ch.id: [0] for ch in self.chains() if ch.side == "guan"})
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(29), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {191 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_OMEN_TICKS", "8"))):
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
            emit(f"假人 {name}", {"loc": p.location, "stamina": p.stamina, "opp_items": dict(sorted(p.opp_items.items())), "opp_done": list(p.opp_done),
                                  "fs_done": list(p.fs_done), "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "象丙", rng=random.Random(7), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey, p.rank = "guan", self.hub, None, 3
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        p.opp_items.update({o.id: "（對照）信物" for o in self.opps() if o.faction == "guan" and o.kind == "accumulate"})
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：機緣與伏筆的進度跟著新角色清空（密謀跟著賽季整個換新）。"""
        self.do(ADMIN, "end_season")
        for who in (self.G_LEAD, self.G_FS, self.H_FS):
            self.main(who)
        self.do(ADMIN, "next_season")
        for who in (self.G_LEAD, self.G_FS, self.H_FS, self.G_ACC):
            self.main(who)
            self.me(who, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：機緣完成那一句（搬之前在 tianxia/opportunities.py、搬之後在 tianxia/features/military/ 的機緣檔；搬的人照實際的檔名多寫一個）
register_track("omen", OmenScenario, (("tianxia/features/military/opp_rules.py",), ('DONE = "（機緣「{name}」完成。）"', 'DONE = "（機緣「{name}」完成！）"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "map", "military",
                       "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern",
                       "territory_acts", "travel", "zhuan"))
