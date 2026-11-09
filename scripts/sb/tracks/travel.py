"""same_behavior 一軌一檔：travel（這一檔登記 travel）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.stamina import StaminaScenario

class TravelScenario(StaminaScenario):
    """移動一軌（全部拆包第 47 批；--track travel，自己一個資料庫）。移動選單（主畫面選的走法：預設步行、`X-Move-Mode: dash` 疾行；
    每一個相鄰的 `move:<地點>[:dash]`）、輿圖的安排前往 `/api/travel`（步行、疾行；不認得的走法、舊的趕路、不存在的地方、體力不足、
    新人身上還有事件待處理、自己站的地方都寫原因）、路上三樣小事（`road:think`／`road:ask`／`road:gather`：做過的灰掉、硬按；
    收穫每個遊戲日的上限拿滿了照樣按得下去只是沒有收穫）、喊停（`act:halt`：到下一站就停；舊的趕路還在路上那一趟多一句不退體力）、
    折返（`road:back`、疾行的 `road:back:dash`）、抵達（含有人設伏的那一頭：自己人、散人走過不打，敵對的自然打、伏兵必勝、伏兵必敗）、
    抵達一站的路上見聞（把機率拉到 1）。
    **前半停在五件寫到一半的事**：走在路上做了一件小事、還有兩樣沒做（邢瀚海）；喊了停、還沒走到那一站（殷聽濤）；折返了、還在走回去的路上
    （汲長風）；舊的趕路出發了還在路上（戈青嵐）；設伏埋了、前半祝臨川疾行踩過一次（鄒歸帆埋的）。
    後半：新程式接著做完小事（含收穫上限拿滿的對照）、走到停下、折返再折返、走完；伏兵那一段讓人走過；假人（BotRunner 兩個走出去；
    整季機器人眼前的選單與挑法、bot_policy.score 對 move:／road: 的分數）；收季、開下一季。
    **結伴同行的路上那一半**（`_share_road`、`act:part`）是第 48 批（移動二）的，不擺在這一軌：另開 `roadmate` 軌（`RoadmateScenario`，借這一軌的小工具）。
    沒有陣營的內容（測試內容）同一串 API 照打，設伏寫「沒有」。"""

    A, B1, B2, B3, C, G = "鄒歸帆", "洪疏桐", "岑尋舟", "樂謹言", "苗遠山", "盧靜川"
    W1, W2, W3, W4, W5 = "邢瀚海", "祝臨川", "殷聽濤", "汲長風", "戈青嵐"
    NEWBIE = "初出茅廬"
    PLAYERS = {A: "guan", B1: "huang", B2: "huang", B3: "huang", C: "guan", G: None,
               W1: "guan", W2: "huang", W3: "guan", W4: None, W5: None}
    BOT_SEATS = ["行甲", "行乙"]
    PHASES_FIRST = ["setup", "seat", "menu", "refuse", "ambush_set", "go", "half"]
    PHASES_SECOND = ["resume", "tasks", "halts", "backs", "arrivals", "hits", "bots", "season"]
    WALKERS = (W1, W2, W3, W4, W5)

    # ── 小工具 ──

    @contextlib.contextmanager
    def tune(self, **values):
        """記憶體裡的路上設定這幾步換掉（兩份程式同一步換、同一步換回）。"""
        cfg = self.c.config
        old = {k: getattr(cfg, k) for k in values}
        for k, v in values.items():
            setattr(cfg, k, v)
        try:
            yield
        finally:
            for k, v in old.items():
                setattr(cfg, k, v)

    def call_mode(self, who: str, method: str, url: str, body: dict | None, mode: str):
        """帶著主畫面選的走法（X-Move-Mode）打一下：選單上的「前往」「折返」照它標、choose 只認選單上真的有的 id。"""
        self.begin()
        client = self.clients[who]
        headers = {"X-Move-Mode": mode}
        r = client.post(url, json=body if body is not None else {}, headers=headers) if method == "POST" else client.get(url, headers=headers)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = r.text[:300]
        emit(f"{who} {method} {url} [{mode}] {json.dumps(body, ensure_ascii=False) if body else ''} {r.status_code}", data)
        return r.status_code, data

    def travel(self, who: str, place: str, mode: str):
        """輿圖的安排前往（/api/travel）：回 {main, arrived} 或 {arrived: false, reason, map}。"""
        return self.call(who, "POST", "/api/travel", {"place": place, "mode": mode})[1]

    def far(self, who: str) -> str | None:
        """從這個人站的地方走得到、路程最長的地點（路程一樣長取 id 排前面的）：這一趟走得久，前半切下去的時候人還在路上。"""
        from tianxia import atlas

        with self.world.action_lock():
            state = self.chars.load(who)
        found = atlas.shortest_routes(state, self.c)
        best = None
        for loc_id, route in sorted(found.items()):
            if not route.path or loc_id == state.player.location or atlas.travel_refusal(state, self.c, loc_id, "walk") is not None:
                continue
            if best is None or round(route.minutes, 6) > best[0]:
                best = (round(route.minutes, 6), loc_id)
        return best[1] if best else None

    def far_first(self, who: str) -> str | None:
        """從這個人站的地方走得到、第一段路最長的地點（一樣長取 id 排前面的）：出發之後第一站要很久才到，前半切下去、後半第一步的時候人還沒走過
        第一站（走過了換站，路上做過的小事 leg_actions 就被清掉，半舊半新讀不到）。"""
        from tianxia import atlas

        with self.world.action_lock():
            state = self.chars.load(who)
        found = atlas.shortest_routes(state, self.c)
        best = None
        for loc_id, route in sorted(found.items()):
            if not route.path or loc_id == state.player.location or atlas.travel_refusal(state, self.c, loc_id, "walk") is not None:
                continue
            if best is None or round(route.legs[0], 6) > best[0]:
                best = (round(route.legs[0], 6), loc_id)
        return best[1] if best else None

    def near(self, who: str) -> str | None:
        """相鄰的第一個地點（序章的草廬只給站在那裡的人，這裡不管）。"""
        with self.world.action_lock():
            state = self.chars.load(who)
        loc = self.c.locations[state.player.location]
        return str(loc.connections[0]) if loc.connections else None

    def ways(self, who: str, tag: str, mode: str = "walk") -> dict:
        """此刻選單上跟移動有關的那幾顆（前往、折返、路上小事、喊停、分道揚鑣、在路上那一格），連同開著與否與標籤。"""
        view = self.call_mode(who, "GET", "/api/main", None, mode)[1]
        mine = {i: [o.get("enabled"), o.get("label")] for i, o in self.ids(view).items()
                if i.startswith(("move:", "road:", "act:halt", "act:part", "act:on_road"))}
        emit(f"{who} 移動選單 {tag}", mine)
        return mine

    def dash_step(self, who: str) -> None:
        """主畫面選疾行：選單上第一顆按得下去的 move:<地點>:dash 按下去（一站一站立刻到）。"""
        view = self.call_mode(who, "GET", "/api/main", None, "dash")[1]
        pick = next((i for i, o in self.ids(view).items() if i.startswith("move:") and i.endswith(":dash") and o.get("enabled")), None)
        emit(f"{who} 疾行一步", pick)
        if pick is not None:
            self.call_mode(who, "POST", "/api/choose", {"id": pick}, "dash")

    def walk_step(self, who: str) -> None:
        pick = next((i for i, o in self.ids(self.main(who)).items() if i.startswith("move:") and i.count(":") == 1 and o.get("enabled")), None)
        emit(f"{who} 步行一步", pick)
        if pick is not None:
            self.choose(who, pick)

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": None if p.journey is None else p.journey.model_dump(mode="json"), "faction": p.faction,
            "legs": sorted(p.leg_actions), "rewards": {k: list(v) for k, v in sorted(p.road_rewards_today.items())},
            "sights": list(p.recent_sights), "visited": sorted(p.visited), "stamina": p.stamina, "silver": p.stats.get("silver"),
            "xinde": p.stats.get("xinde"), "materials": dict(sorted(p.materials.items())),
            "ambush": None if p.ambush is None else p.ambush.model_dump(mode="json"), "tagalong": None if p.tagalong is None else str(p.tagalong),
            "journal": [[e.title, e.tag, list(e.lines)[:5], list(e.changes)[:3]] for e in state.journal[:4]]})

    def rumor(self) -> None:
        """路上沿途打聽聽得到的傳聞：出發地、遠處兩個大區各掛一則（聽得到的才挑）。"""
        from tianxia import atlas
        from tianxia.state import Rumor

        regions = []
        for loc in (self.hub(), self.far(self.W1) or self.hub()):
            region = atlas.region_of(self.c, loc)
            regions.append(None if region is None else region.id)

        def fn(s) -> None:
            for i, region in enumerate(regions):
                s.rumors.append(Rumor(time=s.time, text=f"（對照）沿途的傳聞第{i + 1}則", region=region, location=None))

        self.world.mutate_season(fn)
        emit("掛上的傳聞", regions)

    def moving(self) -> list[str]:
        return [w for w in self.WALKERS if (s := self.chars.load(w)) is not None and s.player.journey is not None]

    # ── 前半 ──

    def seat(self) -> None:
        at, to = self.pair()
        emit("設伏的那一段路", [at, to])
        spots = {self.A: at, self.G: at, self.B1: to, self.B2: to, self.B3: to, self.C: self.hub()}
        for who, side in self.PLAYERS.items():
            self.place(who, spots.get(who, self.hub()), side)
            self.edit(who, lambda p: p.stats.update({"silver": 400}))
        for who in self.PLAYERS:
            self.main(who)
        self.stock_view("坐定")

    def menu(self) -> None:
        """站著不動的移動選單：步行一種標籤、疾行一種標籤（體力夠）。"""
        self.ways(self.W1, "步行")
        self.ways(self.W1, "疾行", "dash")
        self.ways(self.G, "散人站在路旁")

    def refuse(self) -> None:
        """走不成的幾種：新人（身上有事件待處理）、不存在的地方、舊的趕路與不認得的走法（/api/travel 不收）、體力不足的疾行、
        選單上沒有的 move:（硬按）、自己站的地方。"""
        here, near, far = self.hub(), self.near(self.NEWBIE), self.far(self.W5)
        emit("對照用的地點", [here, near, far])
        self.ways(self.NEWBIE, "新人")
        if near is not None:
            self.travel(self.NEWBIE, near, "walk")
            self.choose(self.NEWBIE, f"move:{near}")
        self.travel(self.W5, "不存在的地方", "walk")
        self.travel(self.W5, near or here, "hurry")
        self.travel(self.W5, near or here, "bogus")
        self.travel(self.W5, here, "walk")
        if far is not None:
            self.edit(self.W5, lambda p: setattr(p, "stamina", 0.0))
            self.travel(self.W5, far, "dash")
            self.travel(self.W5, far, "walk")
            self.choose(self.W5, f"move:{far}")
            self.refill(self.W5)

    def go(self) -> None:
        """出發（世界時鐘一請求走一分鐘，所以這一段不插別的請求，前半切下去的時候人還在路上）：W2 疾行（抵達的那一站把路上見聞的機率拉到 1）
        再主畫面選疾行走一步；W1、W3、W4、W5 緊接著步行走遠處；W1 做一件小事、W3 喊停、W4 折返、W5 把那一趟換成舊的趕路
        （拿掉趕路之前出發的樣子）。選單長什麼樣看每一下 choose 回的 main。"""
        dest = {w: self.far(w) for w in self.WALKERS}
        dest[self.W1] = self.far_first(self.W1)  # 第一段最長：前半切下去的時候小事還記在 leg_actions 裡、後半第一步還沒換站
        emit("各人要去的遠處", dest)
        if dest[self.W2] is not None:
            with self.tune(road_sight_chance=1.0):
                self.travel(self.W2, dest[self.W2], "dash")
        self.me(self.W2, "疾行抵達")
        self.dash_step(self.W2)
        self.me(self.W2, "再疾行一步")
        for who in (self.W1, self.W3, self.W4, self.W5):
            if dest[who] is not None:
                self.travel(who, dest[who], "walk")
        self.choose(self.W1, "road:think")
        self.choose(self.W3, "act:halt")
        self.choose(self.W4, "road:back")
        self.edit(self.W5, lambda p: setattr(p.journey, "mode", "hurry") if p.journey is not None else None)
        for who in self.WALKERS:
            self.me(who, "出發之後")

    def half(self) -> None:
        for who in (self.W1, self.W3, self.W4, self.W5, self.A):
            self.me(who, "前半最後")
        self.stock_view("前半最後（埋著）")

    # ── 後半 ──

    def resume(self) -> None:
        """只先登入管理者和還在路上的四個人（每登入一個世界時鐘走一分鐘，全登入的話路上的人先走完了）；其他人到 hits 才登入。
        整段也照這個順序登入，兩邊的步數才對得上。"""
        self.relogin(ADMIN)
        for who in (self.W1, self.W3, self.W4, self.W5):
            self.relogin(who)
        self.rumor()

    def tasks(self) -> None:
        """W1 接著做完小事（打聽聽得到傳聞、採集必中；做過的再按灰著、硬按）；W5（舊的趕路）在收穫上限是 0 的設定下三樣都做一遍。"""
        with self.tune(road_gather_chance=1.0):
            for what in ("ask", "gather", "think", "gather"):
                self.choose(self.W1, f"road:{what}")
        with self.tune(road_reward_daily_cap=0, road_gather_chance=1.0):
            for what in ("think", "gather", "ask"):
                self.choose(self.W5, f"road:{what}")
        self.me(self.W1, "小事做完")
        self.me(self.W5, "收穫拿滿")
        self.choose(self.W5, "act:halt")  # 舊的趕路還在路上：喊停多一句「趕路已經花掉的體力不退」
        self.me(self.W5, "趕路喊停之後")

    def halts(self) -> None:
        """W3 走到喊停的那一站就停下；停下之後再喊停（不在路上了，硬按）。"""
        self.do(ADMIN, "fast_forward", {"hours": 1})
        self.main(self.W3)
        self.me(self.W3, "喊停的那一站")
        self.choose(self.W3, "act:halt")

    def backs(self) -> None:
        """W4 從停下的地方再出發走遠處，折返（步行），緊接著再折返（主畫面選疾行的 road:back:dash，立刻回到身後那一站）。"""
        far = self.far(self.W4)
        if far is not None:
            self.travel(self.W4, far, "walk")
        self.ways(self.W4, "出發之後（疾行標籤）", "dash")
        self.call_mode(self.W4, "POST", "/api/choose", {"id": "road:back:dash"}, "dash")  # 還在路上的時候按：帶著走法的折返
        if far is not None:
            self.travel(self.W4, far, "walk")
        self.choose(self.W4, "road:back")
        self.me(self.W4, "疾行折返之後")
        self.ways(self.W4, "折返完")

    def arrivals(self) -> None:
        """還在路上的一路走完（快轉六小時、同步一次）；每個人走完看一眼，再各步行一步（停在路旁的也動一動）。"""
        for _ in range(8):
            traveling = self.moving()
            if not traveling:
                break
            self.do(ADMIN, "fast_forward", {"hours": 6})
            for who in traveling:
                self.main(who)
        for who in self.WALKERS:
            self.me(who, "走完")
        for who in (self.W1, self.W3):
            self.walk_step(who)
            self.me(who, "再走一步")
        self.stock_view("走完")

    def hits(self) -> None:
        """其他人到這裡才登入（見 resume），再照 StaminaScenario.hits：自己人、散人走過不打，敵對的自然打、伏兵必勝、伏兵必敗。"""
        for who in self.PLAYERS:
            if who not in (self.W1, self.W3, self.W4, self.W5):
                self.relogin(who)
        self.relogin(self.NEWBIE)
        super().hits()

    def bots(self) -> None:
        """假人：BotRunner 兩個（站在城裡，體力滿）若干輪，看他們走出去；整季機器人眼前的選單與挑法、bot_policy.score 對 move:／road: 的分數
        （一個站著、一個在路上）。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = bool(self.c.scenario.factions)
        made = []
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=81 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(self.hub())
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
            made.append(name)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_TRAVEL_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in made:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "journey": None if s.player.journey is None else s.player.journey.model_dump(mode="json"),
                                  "visited": sorted(s.player.visited), "stamina": s.player.stamina,
                                  "journal": [[e.title, e.tag, list(e.lines)[:3]] for e in s.journal[:5]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        for name, road in (("效戊", False), ("效己", True)):
            self.begin()
            solo = Game.new(self.c, name, rng=random.Random(7), world=self.world, graduated=True)
            solo.client = None
            solo.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                solo.choose(first)
            p = solo.state.player
            p.bot = BotProfile(personality="普通", seed=99, faction="guan" if on else None, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(self.hub())
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            if road:
                far = self.far(self.W1)
                if far is not None:
                    emit(f"{name} 出發", solo.travel(far, "walk")[-1:])
            opts = solo.options(odds=False)
            mine = [o for o in opts if o.id.startswith(("move:", "road:", "act:halt"))]
            emit(f"{name} 眼前的選單", [[o.id, o.enabled, o.label] for o in opts])
            emit(f"{name} 的分數", {o.id: bot_policy.score(solo, o, p.bot) for o in mine})
            emit(f"{name} 整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.stock_view("收季之後")
        for who in (self.W1, self.W4, self.A):
            self.me(who, "收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.W1)
        for who in (self.W1, self.W4, self.A):
            self.me(who, "換季之後")
        self.stock_view("換季之後")


# 改一個字（selftest）：舊的趕路喊停那一句（go_actions.halt，第 47 批從 Game._halt 搬進 tianxia/features/travel/；base 上還在 engine.py，所以兩個檔都寫）
register_track("travel", TravelScenario, (("tianxia/features/travel/go_actions.py", "tianxia/engine.py"), ("（趕路已經花掉的體力不退。）", "（趕路已經花掉的體力不退！）")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "map", "military", "outlets",
                       "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts",
                       "travel", "zhuan", "zongmen"))
