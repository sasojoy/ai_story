"""same_behavior 一軌一檔：here（這一檔登記 here、places）。"""
from __future__ import annotations

from sb.harness import ADMIN, MODEL, STEP, TRACK_REQUIRES, emit, register_track
from sb.tracks.companions import CompanionsScenario
from sb.tracks.growth import _PrepTrack
from sb.tracks.socialize import SocializeScenario

# ═══════════════════════════ here、places（主幹合回 develop 第 2 段 D）═══════════════════════════
# 計畫 docs/superpowers/plans/2026-11-06-develop合回-D.md。
# here 盯這一批搬的 figures_here_view、talk_view、figures.side_name 與 figure_intro（合回第 4 段搬回 server.py；第 83 批進 socialize/intro.py）；places 盯留在原位的 place_state、place_state_view 與邸報（合回之前沒有一軌點名）。
# 往來紀錄（talk_log、/api/talk_log）不在這裡：小檔只清不比，這一批另外用兩台真伺服器比一次（計畫第六節）。角色的名字都是原創的。


class HereScenario(SocializeScenario):
    """江湖頁「此地人物」那一排與對話框頂上那一份（--track here，自己一個資料庫）。每一下 /api/main 整份寫，另外單獨寫 figures_here、talk 兩個鍵（逛一圈只寫這兩個）。
    這一排的每一支：只有一位（名望夠直接交友、名望不夠寫還差多少）、兩位以上（照名單、名望不夠）、閉門不見（那幾位寫閉門，不是大勢人物的照常）、談滿了（每日輪數調成 0）、
    福緣到了（說得上話但鈕上不是他，寫「先按交友」；正式內容沒有可招募的同伴，這一下調一位）、每一處有人物的地點站一下（陣營、半身像、簡介、護衛與挑戰那幾顆；不是大勢人物的沒有陣營）、
    開局事件擺著、在路上、事件中、對話中是空的、季收了是空的；一類一顆關著（只有一位直接 call:、兩位以上照舊名單）。對話框：正在談、接著談一輪情誼跟著變、告辭之後一排回來。
    **前半停在寫到一半的事**：范疏影還在談（模型回了一輪），祝長庚、牧初心的求見名單開著；岑未央在路上，盧清商的事件卡擺著，唐曉嵐的開局事件還擺著。
    後半新程式接著：接著談、按人物、按返回、到了、了結、跳過開局，之後一排都回來。假人碰不到（只有畫面讀，bot.py、bot_policy、bot_runner 都不叫），不跑假人段。
    測試內容沒有大勢人物（deep_interaction 全關），同一串 API 照打，一排都是空的。走不到的：序章裡站在人物旁邊（week7、season21 的新角色走開局、不進草廬，草廬也沒有人物；測試內容沒有序章，所以 figures_here_view 的 prologue_rules.active 那一項三種設定都守不到）；pending_companion 指到不在人物表的 id（Game._drop_stale_references 先清掉）、人物的陣營不在劇本裡（正式內容沒有這種人物）、kind 是 once 或 meet 那一句（正式內容此刻沒有這種事件，同一支「先按交友」福緣走到了）。"""

    ONE, DIM, HALLER, HALLOW, SHUT, CAPPED, LUCKY, TOURIST = "許聽瀾", "杜晚舟", "梁硯青", "阮星垂", "紀南枝", "柯望川", "嚴拾光", "邵遠山"
    ROADER, EVENTFUL, TALKER, PICKER, BACKER = "岑未央", "盧清商", "范疏影", "祝長庚", "牧初心"
    NEWBIE = "唐曉嵐"  # 只註冊、建角色，留著開局事件沒按（測試內容沒有開局，站在起點）
    GIVEN = "liubei"  # 福緣那一支要有一位可招募的同伴：正式內容沒有 recruitable，這一下把他調成可招募（只讀 fortune_free，沒有人按）
    PLAYERS = {who: "guan" for who in (ONE, DIM, HALLER, HALLOW, SHUT, CAPPED, LUCKY, TOURIST, ROADER, EVENTFUL, TALKER, PICKER, BACKER)}
    PHASES_FIRST = ["setup", "seat", "one", "hall", "shut", "capped", "lucky", "tour", "blank", "talking", "picking", "half"]
    PHASES_SECOND = ["resume", "talk_on", "picking_on", "blank_on", "loose", "season"]

    # ── 小工具 ──

    def row(self, who: str, tag: str) -> dict:
        view = self.main(who)
        m = view.get("main", view) if isinstance(view, dict) else {}
        emit(f"{who} {tag} 此地人物", {"figures_here": m.get("figures_here"), "talk": m.get("talk")})
        return m

    def glance(self, who: str, tag: str) -> None:
        """只寫這兩個鍵（逛一圈用：/api/main 整份寫太長）。"""
        self.begin()
        data = self.clients[who].get("/api/main").json()
        m = data.get("main", data)
        emit(f"{who} {tag} 此地人物", {"figures_here": m.get("figures_here"), "talk": m.get("talk")})

    def stand(self, who: str, loc: str, fame: int) -> None:
        self.place(who, loc)
        self.fame(who, fame)

    def seat(self) -> None:
        """福緣先全部記成領過（place 把加入的日子推到很久以前，同步一下就先送上門）；要看福緣那一支的人在 lucky 自己還原。"""
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))
        CompanionsScenario.seat(self)

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        who = self.NEWBIE
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})

    def one(self) -> None:
        loc, cid = self.alone_spot()
        if cid is None:
            emit("這份內容沒有只有一位大勢人物的地點", None)
            return
        for who, fame, tag in ((self.ONE, 9999, "只有一位・名望夠"), (self.DIM, 0, "只有一位・名望不夠")):
            self.stand(who, loc, fame)
            self.row(who, tag)

    def hall(self) -> None:
        loc, _ = self.hall_spot()
        if loc is None:
            emit("這份內容沒有兩位以上大勢人物的地點", None)
            return
        for who, fame, tag in ((self.HALLER, 9999, "兩位以上・名望夠"), (self.HALLOW, 0, "兩位以上・名望不夠")):
            self.stand(who, loc, fame)
            self.row(who, tag)

    def shut(self) -> None:
        """閉門不見：這幾位人物都不見他（只蓋得到大勢人物；沒有大勢人物的內容沒這一支）。"""
        from tianxia import figures

        spots = [loc for loc, _ in (self.hall_spot(), self.alone_spot()) if loc is not None]
        until = {figures.of_character(self.c, cid): 1.0e12 for figs in self.layout().values() for cid in figs if figures.of_character(self.c, cid) is not None}
        self.edit(self.SHUT, lambda p: p.snubbed_until.update(until))
        for loc in spots:
            self.stand(self.SHUT, loc, 9999)
            self.row(self.SHUT, f"閉門不見 {loc}")

    def capped(self) -> None:
        """談滿了（把每日輪數調成 0）。"""
        spots = [loc for loc, _ in (self.alone_spot(), self.hall_spot()) if loc is not None]
        with self.tuned(self.c.config, talk_turns_per_day=0):
            for loc in spots:
                self.stand(self.CAPPED, loc, 9999)
                self.row(self.CAPPED, f"談滿了 {loc}")

    def lucky(self) -> None:
        """福緣到了：一類一顆的交友先發福緣，這一位說得上話但鈕上不是他。"""
        loc, cid = self.alone_spot()
        if cid is None or self.GIVEN not in self.c.characters:
            return
        self.stand(self.LUCKY, loc, 9999)
        self.edit_state(self.LUCKY, lambda s: (setattr(s.player, "fortune", False), setattr(s.player, "joined_at", s.world.time)))
        with self.tuned(self.c.config, fortune_day_min=0), self.tuned(self.c.characters[self.GIVEN], kind="recruitable"):
            self.row(self.LUCKY, "福緣到了")
        self.edit(self.LUCKY, lambda p: setattr(p, "fortune", True))

    def tour(self) -> None:
        """每一處有人物的地點站一下：每一位的陣營、半身像、簡介、護衛與挑戰那幾顆。"""
        for loc in sorted(self.layout()):
            self.stand(self.TOURIST, loc, 9999)
            self.glance(self.TOURIST, f"逛到 {loc}")

    def blank(self) -> None:
        """開局事件擺著、在路上、事件中：一排都是空的。"""
        loc, _ = self.alone_spot()
        spot = loc or sorted(self.c.locations)[0]
        self.place(self.NEWBIE, spot)
        self.row(self.NEWBIE, "開局事件擺著")
        self.stand(self.ROADER, spot, 9999)
        far = next(i for i in sorted(self.c.locations) if i != spot)
        self.call(self.ROADER, "POST", "/api/travel", {"place": far, "mode": "walk"})
        self.row(self.ROADER, "在路上")
        self.stand(self.EVENTFUL, spot, 9999)
        event = next(e.id for e in sorted(self.c.events.values(), key=lambda e: e.id) if e.choices)
        self.edit_state(self.EVENTFUL, lambda s: setattr(s, "pending_event", event))
        emit(f"{self.EVENTFUL} 擺上事件卡", event)
        self.row(self.EVENTFUL, "事件中")

    def talking(self) -> None:
        """前半切在這裡：范疏影正在跟人物說話（模型回了一輪），話還沒說完。"""
        loc, cid = self.alone_spot()
        if cid is None:
            return
        MODEL["talk"] = {"stance": "suzhan"}
        self.stand(self.TALKER, loc, 9999)
        self.reach(self.TALKER, cid)
        self.row(self.TALKER, "正在說話")
        MODEL["talk"] = None

    def picking(self) -> None:
        """前半也切在這裡：兩位以上的地點，求見名單開著、還沒按；一排照畫。"""
        loc, _ = self.hall_spot()
        if loc is None:
            return
        for who in (self.PICKER, self.BACKER):
            self.stand(who, loc, 9999)
            self.open_list(who)
            self.row(who, "求見名單開著")

    # ── 後半 ──

    def talk_on(self) -> None:
        """接著談：舊程式留下的對話，新程式照樣畫對話框、再談一輪、告辭之後一排回來（情誼跟著變）。"""
        if self.chars.load(self.TALKER).player.pending_companion is None:
            emit(f"{self.TALKER} 沒有在談", None)
            return
        MODEL["talk"] = {"stance": "suzhan"}
        self.row(self.TALKER, "接著談")
        self.choose(self.TALKER, "talk:0")
        self.row(self.TALKER, "再談一輪")
        self.leave(self.TALKER)
        self.row(self.TALKER, "告辭之後")
        MODEL["talk"] = None

    def picking_on(self) -> None:
        loc, figs = self.hall_spot()
        if loc is None:
            return
        MODEL["talk"] = {"stance": "suzhan"}
        self.press(self.PICKER, f"call:{figs[0]}")
        self.row(self.PICKER, "按了人物")
        self.leave(self.PICKER)
        self.row(self.PICKER, "告辭之後")
        MODEL["talk"] = None
        self.press(self.BACKER, "call:back")
        self.row(self.BACKER, "按了返回")

    def blank_on(self) -> None:
        loc, _ = self.alone_spot()
        self.place(self.ROADER, loc or sorted(self.c.locations)[0])
        self.row(self.ROADER, "到了")
        self.settle_choices(self.EVENTFUL)
        self.row(self.EVENTFUL, "事件了結")
        self.do(self.NEWBIE, "skip_tutorial")
        self.settle_choices(self.NEWBIE)
        self.place(self.NEWBIE, loc or sorted(self.c.locations)[0])
        self.row(self.NEWBIE, "開局跳過")

    def loose(self) -> None:
        """一類一顆關著（precise_actions）：只有一位直接按 call:、兩位以上照舊打開名單。"""
        spot, _ = self.alone_spot()
        hall, _ = self.hall_spot()
        with self.tuned(self.c.config, precise_actions=False):
            if spot is not None:
                self.stand(self.ONE, spot, 9999)
                self.row(self.ONE, "一類一顆關著・只有一位")
                self.stand(self.DIM, spot, 0)
                self.row(self.DIM, "一類一顆關著・名望不夠")
            if hall is not None:
                self.stand(self.HALLER, hall, 9999)
                self.row(self.HALLER, "一類一顆關著・兩位以上")

    def season(self) -> None:
        loc, _ = self.alone_spot()
        spot = loc or sorted(self.c.locations)[0]
        self.stand(self.ONE, spot, 9999)
        self.row(self.ONE, "收季之前")
        self.do(ADMIN, "end_season")
        self.row(self.ONE, "季收了")
        self.do(ADMIN, "next_season")
        self.row(self.ONE, "下一季剛開")
        loc, _ = self.alone_spot()
        self.stand(self.ONE, loc or spot, 9999)
        self.row(self.ONE, "下一季")
        self.you(self.ONE, "下一季")


class PlacesScenario(SocializeScenario):
    """地點會變樣與上線邸報（--track places，自己一個資料庫；這一批不搬它們，合回之前沒有一軌點名，這一軌是合回之後才有的守門）。
    盤算到點照 place_win／place_lose 改地點（戰火，師父那一句 h_place 輪到）；走到變了樣的地方（到達那一句）；時刻表大事的 places（宛城，快轉到揭曉）。
    讀它的每一處：/api/main 的 place_state 與場景圖色調、場景那一句、店價倍數、馬市開不開與鈕、人物避不避、這裡抽得到的事件。
    **前半停在賈青苗站在太平的馬市、選單開著**。後半新程式接著：這裡打起來（馬市收掉）、淪陷（關）、收復成重建（開、貴一成）；葛遙川離線超過 away_hours 再上線看邸報；
    易手落入黃巾、佔著的一方又贏照舊淪陷、落入官軍收復；戰火又一仗鬧饑荒、none 不變；時間過了饑荒轉重建再回太平；假人站在戰火裡跑六輪；換季整個重來。
    測試內容 plans 關著，地點一律太平，同一串 API 照打。領地易手那一條路（conquest._announce）走 landturn 那一軌，這裡直接叫 flipped。"""

    WATCHER, EYE, TRADER, AWAY, HANDS, FARER = "溫寄北", "聶遠岑", "賈青苗", "葛遙川", "韓拾穗", "翁渡寒"
    PLAYERS = {who: "guan" for who in (WATCHER, EYE, TRADER, AWAY, HANDS, FARER)}
    WAN, MARKET, TABLE_EVENT = "wan_city", "runan_market", "zhangmancheng_wan"
    BOT_SEATS = ["界一", "界二"]
    PHASES_FIRST = ["setup", "seat", "peace", "plan_war", "arrive_war", "table", "market_open", "half"]
    PHASES_SECOND = ["resume", "market_on", "away", "hands", "clock", "bots", "season"]

    # ── 小工具 ──

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))
        CompanionsScenario.seat(self)

    def spot(self, loc: str) -> str:
        return loc if loc in self.c.locations else sorted(self.c.locations)[0]

    def marks(self, tag: str) -> None:
        from tianxia import place_state

        w = self.world.get_season()
        emit(f"地點的樣子 {tag}", {"on": place_state.on(self.c), "marks": {k: v.model_dump(mode="json") for k, v in sorted(w.places.items())},
                                   "now": {k: place_state.kind_at(w, self.c, k) for k in sorted(w.places)}})

    def look(self, who: str, tag: str) -> None:
        """/api/main 整份，加上讀地點樣子的那幾處：場景那一句、店價倍數、馬市、人物避不避、這裡抽得到的事件。"""
        from tianxia import events, mounts, place_state, territory

        view = self.main(who)
        m = view.get("main", view) if isinstance(view, dict) else {}
        self.begin()
        game = self.server.game_for(who)
        s, c = game.state, self.c
        w, loc = s.world, s.player.location
        emit(f"{who} {tag}", {
            "place": loc, "main": m.get("place_state"), "art": m.get("art"), "view": game.place_state_view(), "text": game.location_text(),
            "factor": place_state.factor(w, c, loc), "closed": place_state.market_closed(w, c, loc), "shunned": place_state.shunned(w, c, loc),
            "market": mounts.market_here(s, c), "button": "act:market" in self.ids(view), "picking": s.player.picking_market,
            "price": territory.price_here(s, c), "draws": [e.id for e in events.event_candidates(s, c, "explore", "common")]})

    def stage(self, tag: str, how) -> None:
        """直接改全服的樣子（寫明哪一支）：領地易手的 _announce 走 landturn 那一軌，這裡只看改完之後讀到的。"""
        from tianxia import place_state

        self.world.mutate_season(lambda w: how(place_state, w))
        self.marks(tag)

    # ── 前半 ──

    def peace(self) -> None:
        """太平：什麼都沒有。葛遙川站一下宛城、去過這幾處，之後一直不上線（邸報的「你去過的地方」）。"""
        wan, market = self.spot(self.WAN), self.spot(self.MARKET)
        self.place(self.EYE, wan)
        self.look(self.EYE, "太平")
        self.place(self.TRADER, market)
        self.look(self.TRADER, "太平")
        self.place(self.AWAY, wan)
        self.edit(self.AWAY, lambda p: p.visited.update(i for i in self.c.locations))
        self.main(self.AWAY)

    def plan_war(self) -> None:
        """盤算到點：照 PlanContest.place_win／place_lose 改地點（預設打過一仗）。"""
        from tianxia.features.guide import hints
        from tianxia import place_state
        from tianxia.state import Plan

        pair = next(((it, st) for it in self.c.itineraries for st in it.stops if st.contest and st.place in self.c.locations), None) if place_state.on(self.c) else None
        if pair is None:
            emit("這份內容沒有盤算（或地點不會變樣）", None)
            return
        it, st = pair
        self.place_war = st.place

        def seed(w) -> None:
            w.plans = [x for x in w.plans if x.stop != st.id]
            w.plans.append(Plan(stop=st.id, who=it.who, place=st.place, open_at=w.time, due=w.time + 12 * 3600))

        self.world.mutate_season(seed)
        emit("盤算", {"stop": st.id, "who": it.who, "place": st.place})
        self.place(self.WATCHER, st.place)
        self.look(self.WATCHER, "盤算之前")
        for _ in range(4):
            plan = next((x for x in self.world.get_season().plans if x.stop == st.id), None)
            if plan is None or plan.settled:
                break
            self.do(ADMIN, "fast_forward", {"hours": 12})
        self.marks("盤算到點之後")
        # 師父那一句 h_place：狀態提示一次排一條、要按「知道了」才排下一條，這裡把別的都記成說過，下一次同步就輪到它
        self.edit(self.WATCHER, lambda p: (p.hints_seen.update(set(hints.STATE) - {"h_place"}), p.hint_queue.clear()))
        self.look(self.WATCHER, "盤算到點之後")

    def arrive_war(self) -> None:
        """走到變了樣的地方：到達那一句（紀錄裡）。"""
        here = self.spot(self.MARKET)
        dest = next((loc for loc, mark in sorted(self.world.get_season().places.items())), None)
        if dest is None:
            emit("這份內容沒有變了樣的地點", None)
            return
        self.place(self.FARER, here)
        self.call(self.FARER, "POST", "/api/travel", {"place": dest, "mode": "walk"})
        for _ in range(8):
            if self.chars.load(self.FARER).player.journey is None:
                break
            STEP[0] += 30
            self.main(self.FARER)
        self.look(self.FARER, "走到了")
        self.you(self.FARER, "走到了")

    def table(self) -> None:
        """時刻表大事的 places（宛城：成了淪陷、不成戰火）：快轉到它揭曉。"""
        from tianxia import place_state

        if not place_state.on(self.c) or self.WAN not in self.c.locations:
            emit("這份內容沒有時刻表的地點變化", None)
            return
        for _ in range(8):
            if self.TABLE_EVENT in self.world.get_season().timeline:
                break
            self.do(ADMIN, "fast_forward", {"hours": 12})
        emit("時刻表揭曉", getattr(self.world.get_season().timeline.get(self.TABLE_EVENT), "key", None))
        self.marks("時刻表之後")
        self.look(self.EYE, "時刻表之後")

    def market_open(self) -> None:
        """前半切在這裡：賈青苗站在太平的馬市、選單開著，還沒按。"""
        self.look(self.TRADER, "馬市之前")
        self.choose(self.TRADER, "act:market")
        self.look(self.TRADER, "馬市開著")

    def half(self) -> None:
        for who in self.PLAYERS:
            self.you(who, "前半停在這裡")
        self.marks("前半停在這裡")

    # ── 後半 ──

    def market_on(self) -> None:
        """舊程式開著的馬市，這裡打起來了：戰火關馬市（選單收掉）、淪陷也關、重建開門但貴一成。"""
        market = self.spot(self.MARKET)
        self.look(self.TRADER, "接手")
        self.stage("馬市那裡打起來", lambda ps, w: ps.strike(w, self.c, market))
        self.look(self.TRADER, "戰火")
        self.stage("馬市那裡淪陷", lambda ps, w: ps.fall(w, self.c, market, "huang"))
        self.look(self.TRADER, "淪陷")
        self.stage("馬市那裡收復", lambda ps, w: ps.retake(w, self.c, market))
        self.look(self.TRADER, "重建")

    def away(self) -> None:
        """離線超過 away_hours 再上線：邸報（你去過的地方那一段讀世界記事）。"""
        STEP[0] += 70
        self.main(self.AWAY)
        self.you(self.AWAY, "再上線")

    def hands(self) -> None:
        """另外幾種變化：易手落入黃巾是淪陷、再打一仗黃巾贏照舊、落入官軍是收復；戰火又一仗鬧饑荒；盤算寫了 none 不變。"""
        wan, farm = self.spot(self.WAN), next((i for i in sorted(self.c.locations) if i not in (self.WAN, self.MARKET)), None)
        self.place(self.HANDS, wan)
        self.stage("易手落入黃巾", lambda ps, w: ps.flipped(w, self.c, wan, "huang"))
        self.look(self.HANDS, "淪陷")
        self.stage("佔著的一方又贏", lambda ps, w: ps.strike(w, self.c, wan, "huang"))
        self.stage("落入官軍", lambda ps, w: ps.flipped(w, self.c, wan, "guan"))
        self.look(self.HANDS, "收復")
        self.place(self.HANDS, farm)
        self.stage("這裡打一仗", lambda ps, w: ps.apply(w, self.c, farm, "war"))
        self.stage("再打一仗", lambda ps, w: ps.apply(w, self.c, farm, "war"))
        self.look(self.HANDS, "饑荒")
        self.stage("寫了 none", lambda ps, w: ps.apply(w, self.c, farm, "none"))

    def clock(self) -> None:
        """時間過了：饑荒、戰火轉重建，重建過了回太平（kind_at 現算，存檔不動）。天數照季長縮放。"""
        from tianxia.world_state import season_length_days

        t = self.c.config.plans
        days = season_length_days(self.world.get_season(), self.c)
        hours = int(days * 24 * (t.famine_days7 + t.rebuild_days7) / 7) + 1
        for i in range(3):
            self.do(ADMIN, "fast_forward", {"hours": hours // 3 + 1})
            self.marks(f"時間過了 第 {i + 1} 跳")
            self.look(self.HANDS, f"時間過了 第 {i + 1} 跳")

    def bots(self) -> None:
        """假人站在戰火裡：BotRunner 跑幾輪（馬市、店價、選單都讀地點的樣子）。"""
        market = self.spot(self.MARKET)

        def fn(state) -> None:
            state.player.location, state.player.journey = market, None
            state.player.visited.add(market)

        self.stage("假人那裡打起來", lambda ps, w: ps.strike(w, self.c, market))
        _PrepTrack.seats(self, self.BOT_SEATS, fn)
        _PrepTrack.tick(self, self.BOT_SEATS, 6, "戰火裡")

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.marks("季收了")
        self.do(ADMIN, "next_season")
        self.marks("下一季（換季整個重來）")
        self.look(self.HANDS, "下一季")


TRACK_REQUIRES.update({"here": "content/figure_intros.json", "places": "tianxia/place_state.py"})


# 改一個字（selftest）：說得上話但鈕上不是他的那一句（搬之前在 engine.py，搬之後在交友求見包）、戰火那一句（共用層 place_state，這一批不搬）
register_track("here", HereScenario, (("tianxia/engine.py", "tianxia/features/socialize/view.py", "tianxia/features/socialize/menus.py"),
                                      ('"先按「交友」"', '"先按下「交友」"')), "week7")
register_track("places", PlacesScenario, (("tianxia/place_state.py",), ("這一帶剛打過仗，焦土還沒冷", "這一帶剛打過仗，焦土還未冷")), "week7")
