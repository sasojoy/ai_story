"""same_behavior 一軌一檔：map（這一檔登記 map）。"""
from __future__ import annotations

import hashlib
import json
import os
import random

from sb.base import DUEL_PROFILES, Scenario
from sb.harness import ADMIN, CLOCK, CLOCK0, STEP, emit, register_track

# ═══════════════════════════ map（全部拆包第 49 批：輿圖一——天下圖、區圖、小地圖、地點詳情、疊層） ═══════════════════════════

MAP_LAYER_IDS = ("situation", "enemies", "story", "routes")  # Game.MAP_LAYERS（atlas.LAYERS）的四個圖層


class MapScenario(Scenario):
    """輿圖一軌（全部拆包第 49 批；--track map，自己一個資料庫）。輿圖是只讀的畫面，沒有選項前綴、不擲骰：每一個畫面都從存檔與世界現算，
    所以情境是「擺不同的局面，把三條路由與網頁檔各打一遍」。
    **三條路由**：`GET /api/map`（舊的整張 SVG 與詳情欄：四個圖層、不存在的圖層、有效／無效的 place、沒登入）、`GET /api/map/base`（底圖與
    清單，伺服器照鍵快取：同一個人連問兩次、不同的人、看的人換地點）、`GET /api/map/state`（疊層：勝算、出陣、分鐘、戰線、每一週的地盤），
    還有 `POST /api/travel` 走不成時帶的 `map`（打開輿圖之後才冒出事件、就在這裡、沒這個地方）與成功時地點詳情的安排前往（travel_options）。
    **局面**：官軍、黃巾、散人、剛進門還在序章的人各看一遍；出陣約戰開著／關著（出陣那一格與推薦）；意境提示、盡頭阻力、劇本的地盤
    各翻一下（翻前翻後各清一次底圖快取；盡頭阻力這一包不讀，翻了輸出本來就一樣）；走在路上的人（路上的「你」與到選定地點的粗線）；時間過了兩天（軍令、戰線、每週地盤）；地盤進度擺到高（警報、易手標記）。
    **網頁檔**：`GET /static/map.js` 的整檔 sha256（網頁拿到的內容一個位元組不變）與 `/` 載入它的那一行、載入版本號。
    **寫到一半**：地圖本身沒有寫到一半的狀態（每個畫面從存檔現算）；前半停在有人走在路上、有人剛擺好地盤進度的那一刻，後半新程式接手：
    路上的人走到、畫面照存檔的 journey 現算。**假人**：假人不看地圖（沒有任何 /api/map 的呼叫），碰到輿圖的只有 `bot_policy` 的
    `_toward_battle` 叫 `Game.travel_options`——它要有決戰在集結才走得到：第 49 批這一段沒有開決戰（season21 量過一次也沒走到），
    map2（第 50 批）起 bots 段先開一場決戰的集結（長社火攻已經結算時開廣宗；測試內容沒有陣營不開，見下面 bots 那一條），
    season21、week7 各走到 8 次。假人跑完照舊比存檔與世界雜湊，`travel_options` 另由 /api/map 的地點詳情與 /api/travel 走到。
    **map2（全部拆包第 50 批：atlas 拆兩半，圖層那一半進輿圖包 layers.py）補的**，切點與段落見 PHASES（下面「走到」的都在 dev/map-2 Task 1
    那一筆實跑、逐函式數過呼叫次數）：
    - orders_how：/api/main 的本週軍令卡（order_cards.order_how）。管理者重發之外，照內容每一種模板官軍、黃巾各擺一道（orders._build），所以
      攻城（出陣與遊歷兩種寫法、約戰開著與關著）、守城（領地爭奪的記不到與照守勢行動）、截糧（出陣與遊歷）、護糧、打擊（他現在在哪）都走到；
      局面三種：照原樣、約戰關著（sortie_duel.on 那兩支，season21、week7）、劇本的地盤拿掉（territory.on＝出陣關著，領地爭奪跟著關）。
      局勢圖層那一張帶打擊目標的 ◎（strike_marks 摸清的那一支）。上面三種局面守城都是記不到或照守勢行動，守城「有地點」那一支
      （order_how 的 conquest.duel_on、territory.on 那兩行）由 defended 補（第 50 批審查）：每一方的守城軍令在自家一塊擺上對面的進度，
      約戰照原樣與關著各看一遍（season21 實跑：「對面在那裡約戰時去應戰、守住」與「出陣守一回，或按」各 3 處，之前都是 0），看完放回去。
    - details、details_again：舊的整張圖一處一處點（每一處的詳情欄、標頭、前往鈕；SVG 照雜湊，圖層照順序輪）：開季與過了四天，官軍、黃巾每一處，
      散人與序章新人頭尾兩處——大區的大勢、此刻由誰控制與中立地、常出沒的龍頭人物與聲威會回、敵情與自己陣營的「操練」、意境、地利、
      最近的傳聞、「這一帶離得遠」（season21、week7）、主線目標（只有測試內容：另兩種是第一季，不觸發 beta 主線）、路線（就在這裡、
      剛出發折返立刻到）都走到；被佔下的中立地「（開季是中立地）」沒走到。
    - blocks：atlas.travel_block 的先後一層一層剝（祁照晚）：叛投待確認 → 正在答話（fs_asking）→ 跟著韓望舒同行（tagalong＋journey）→
      閉關中 → 守著埋伏 → 全部拿掉之後走得成；每一層 /api/travel 那一句、輿圖前往鈕上那一句、疊層的 travel_block 各看一次。之前先擺
      「跟著、站著」按前往（不擋：自己先走就散了）。測試內容沒有陣營、沒有伏筆鏈，只剝後三層。
    - cut（前半停在）：葉聞鐘看了題還沒答（fs_asking）、柏青崖跟著韓望舒走在路上；unblock（後半，新程式接手）：兩個人看輿圖、按前往被擋、
      按作罷（fs:leave）／分道揚鑣（act:part）之後再按前往（改道），arrive 那一段走到。這一段靠 season21、week7：測試內容沒有伏筆鏈（葉聞鐘
      不擺題、直接走得成），路只有 3 分鐘（柏青崖前半停在路上，可是除了所在與目的地沒有別處可按；後半重新登入時已經到了）。
    - bots：開一場決戰的集結（長社火攻已經結算時開廣宗；測試內容沒有陣營不開），兩個假人的 _toward_battle 經 Game.travel_options 往那一區走
      （season21、week7 各 8 次，atlas.region_locations 也是這裡走到）。
    **這一軌走不到的**（實跑數過，三種設定都是 0 次；搬的時候 ast 逐條比）：「此地的大勢人物」那一段（_here_text、HERE_TITLE、IDLE_NOTE 按兵不動：
    只在沒有時刻表的季，三種設定都不是）；龍頭人物「出兵之前」的「（…起）」（_figure_activity 的 started 那一支：顯示到的人物都已出兵或沒有戰線）；
    road_hops（全圖開放關著才用）；打擊目標沒摸清只標大區那一支（全圖開放，都摸清了）；mapdata.mostly_here 照表的那一支（services.hint_in：
    探索一顆開著時 /api/main 的 mostly 由探索包的出門一趟回答，沒走到輿圖這一支）；sim_shown 只有測試內容走到（另兩種是第一季的規則）；
    守城卡並列最高的多過 SIEGE_NAMED_MAX（DEFEND_AREA_CONQUEST）與被戰書凍結的（DEFEND_SIEGE_CONQUEST）兩句（這一批沒改那兩行）；
    守城那一行 territory.on 是假的那一支（DEFEND_ACT_PLAIN 在領地爭奪裡）靜態走不到：conquest.on 就是 territory.on。"""

    PLAYERS = {"韓望舒": "guan", "賀凌川": "huang", "祝聽雨": None, "岑九皋": "guan"}
    GUAN, HUANG, LONE, WALKER = tuple(PLAYERS)
    NEWBIE = "初來乍到"
    BOT_SEATS = ["輿甲", "輿乙"]
    # map2（全部拆包第 50 批：atlas 拆兩半）補的三個人（原創名字；不放進 PLAYERS，seat 照原樣只擺四個人）：travel_block 的先後一層一層剝、
    # 前半停在看了題還沒答、前半停在跟著帶頭的人走在路上
    PEEL, ASKER, TAGGER = "祁照晚", "葉聞鐘", "柏青崖"
    PHASES_FIRST = ["setup", "seat", "layers", "base", "state", "orders_how", "details", "toggles", "web", "road", "blocks", "cut", "half"]
    PHASES_SECOND = ["resume", "unblock", "arrive", "days", "details_again", "fronts", "web_again", "bots", "season"]

    # ── 小工具 ──

    def factions_on(self) -> bool:
        return any(f.id == "huang" for f in self.c.scenario.factions) and any(f.id == "guan" for f in self.c.scenario.factions)

    def side(self, who: str) -> str | None:
        return self.PLAYERS.get(who) if self.factions_on() else None

    def hub(self) -> str:
        return self.c.scenario.start_location

    def get(self, who: str, url: str):
        return self.call(who, "GET", url)[1]

    @staticmethod
    def q(layer: str, place: str | None = None) -> str:
        from urllib.parse import quote

        return "/api/map?layer=" + quote(layer) + ("" if place is None else "&place=" + quote(place))

    def places_of(self, who: str) -> list[str]:
        self.begin()  # 問一下有哪些地點可以選（不寫進輸出：整張 SVG 約 170KB，要看的畫面另外打）
        data = self.clients[who].get("/api/map").json()
        return [p["id"] for p in data.get("places", [])] if isinstance(data, dict) else []

    def three_views(self, who: str, tag: str, full: bool = False) -> None:
        """底圖、疊層各打一遍（同一個人此刻看到的輿圖）；full 為真再加舊的整張圖（SVG 每張約 170KB，要的幾處才打）。"""
        emit(f"{who} 看輿圖 {tag}", None)
        self.get(who, "/api/map/base")
        self.get(who, "/api/map/state")
        if full:
            self.get(who, "/api/map")

    def farthest(self, who: str) -> str | None:
        """離這個人此刻站的地方（直線）最遠的地點：走起來最久，前半停在這一趟走到一半。"""
        here = self.c.locations[self.chars.load(who).player.location]
        known = [i for i in self.places_of(who) if i in self.c.locations]
        if not known:
            return None
        return max(known, key=lambda i: ((self.c.locations[i].x - here.x) ** 2 + (self.c.locations[i].y - here.y) ** 2, i))

    # ── map2 的小工具（全部拆包第 50 批） ──

    @staticmethod
    def dig(view, path: str):
        for part in path.split("."):
            view = view.get(part) if isinstance(view, dict) else None
        return view

    def peek(self, who: str, url: str, keys: tuple[str, ...], body: dict | None = None):
        """打一條 API（body 給了是 POST），只寫幾個鍵（a.b 是巢狀的鍵），整份回應另寫 sha256 與長度：每一個位元組照樣比得到，
        輸出不必帶整張 SVG（舊的整張圖一張約 170KB）。回整份回應。"""
        self.begin()
        client = self.clients[who]
        r = client.post(url, json=body) if body is not None else client.get(url)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = None
        emit(f"{who} {'POST' if body is not None else 'GET'} {url} {json.dumps(body, ensure_ascii=False) if body else ''} {r.status_code}",
             {**{k: self.dig(data, k) for k in keys}, "sha": hashlib.sha256(r.content).hexdigest(), "len": len(r.content)})
        return data

    def go_to(self, who: str, place: str | None, mode: str = "walk") -> None:
        """按前往（/api/travel）：走不成的那一句（reason）與它帶的輿圖底下的鈕（map.travel），整份回應照雜湊比；接著看疊層的 travel_block。"""
        if place is None:
            emit(f"{who} 沒有可以前往的地點", None)
            return
        self.peek(who, "/api/travel", ("arrived", "reason", "map.travel", "map.selected"), {"place": place, "mode": mode, "layer": "routes"})
        self.peek(who, "/api/map/state", ("travel_block", "journey", "here"))

    def me(self, who: str, tag: str) -> None:
        """這個人身上擋不擋得住前往的那幾格（不經 API，讀資料庫）。"""
        p = self.chars.load(who).player
        j = p.journey
        emit(f"{who} {tag}", {"loc": p.location, "journey": None if j is None else [j.path[j.last], j.reached, j.last],
                              "asking": p.fs_asking, "tagalong": None if p.tagalong is None else p.tagalong.leader,
                              "defect": p.pending_defect, "busy": p.busy_until, "ambush": None if p.ambush is None else p.ambush.key})

    def enroll(self, who: str, side: str | None, loc: str) -> None:
        """另外註冊一個人（照 setup 的寫法：註冊、建角色、跳過教學、選掉開局三選一），擺到 loc、陣營照 side（沒有陣營的內容是散人）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        self.do(who, "skip_tutorial")
        self.settle_choices(who)
        self.place(who, loc, side if self.factions_on() else None)

    def chain_id(self) -> str | None:
        """一條真的有的伏筆鏈（照 id 排第一條）：fs_asking 指到內容裡沒有的鏈，建 Game 時軍情包的清失效參照會清掉；沒有鏈的內容是 None。"""
        chains = sorted(self.c.foreshadows.chains, key=lambda ch: ch.id)
        return chains[0].id if chains else None

    def other_place(self, who: str, *avoid: str | None) -> str | None:
        """這個人畫得出來的地點裡，不是他此刻所在、也不是 avoid 那幾處的第一個（照 id）。"""
        here = self.chars.load(who).player.location
        return next((i for i in sorted(self.places_of(who)) if i in self.c.locations and i != here and i not in avoid), None)

    def follow(self, who: str, leader: str) -> None:
        """直接擺成「跟著 leader 結伴同行」（同 roadmate 一軌的對照）；since 擺在很遠的未來，等太久散了那一條不會因為步數累積就清掉。"""
        from tianxia.state import Tagalong

        self.edit(who, lambda p: setattr(p, "tagalong", Tagalong(leader=leader, since=CLOCK0 + 10 ** 7)))

    def lay_ambush(self, who: str) -> None:
        """直接擺成「正守著埋伏」：季上一筆、角色身上一筆（同 ambush_rules.place；路段鍵同 ambush_rules.key），到期擺在很遠的未來，
        同步時體力玩法包的 expire 對得到季上那一筆、不會收起來。"""
        from tianxia.state import Ambush, AmbushPost

        p0 = self.chars.load(who).player
        to = next(loc for loc in sorted(self.c.locations) if loc != p0.location)
        seg, until = "|".join(sorted((p0.location, to))), 4.0e9
        self.world.mutate_season(lambda w: w.ambushes.setdefault(seg, []).append(
            Ambush(owner=who, at=p0.location, to=to, set_at=w.time, until=until, side=p0.faction)))
        self.edit(who, lambda p: setattr(p, "ambush", AmbushPost(key=seg, to=to, until=until)))

    def detail_tour(self, who: str, tag: str, places: list[str]) -> None:
        """舊的整張圖一處一處點（圖層照順序輪：四層的 SVG 各輪得到）：寫詳情欄、標頭、安排前往的鈕，SVG 與整份回應照雜湊比。"""
        emit(f"{who} 一處一處看詳情 {tag}", len(places))
        for i, loc_id in enumerate(places):
            self.peek(who, self.q(MAP_LAYER_IDS[i % len(MAP_LAYER_IDS)], loc_id), ("selected", "here", "header", "detail", "travel"))

    # ── 前半 ──

    def seat(self) -> None:
        spots = sorted(self.c.locations)
        here = {self.GUAN: self.hub(), self.HUANG: self.hub(), self.LONE: spots[-1], self.WALKER: spots[len(spots) // 2]}
        for who in self.PLAYERS:
            self.place(who, here[who], self.side(who))
            self.edit(who, lambda p: p.stats.update({"silver": 200}))
        for who in (*self.PLAYERS, self.NEWBIE):
            self.main(who)

    def layers(self) -> None:
        """舊的整張圖：四個圖層、不存在的圖層（回預設）、沒給圖層；有效的 place（頭、中、尾）與無效的；四種人各看。"""
        for who in (self.GUAN, self.HUANG, self.LONE, self.NEWBIE):
            places = self.places_of(who)
            emit(f"{who} 畫得出來的地點數", len(places))
            picks = [places[0], places[-1]] if places else []
            for layer in (*MAP_LAYER_IDS, "沒這層") if who == self.GUAN else ("situation", "story"):
                self.get(who, self.q(layer))
            for pick in picks if who == self.GUAN else picks[-1:]:
                for layer in MAP_LAYER_IDS if who == self.GUAN else ("enemies", "routes"):
                    self.get(who, self.q(layer, pick))
            self.get(who, self.q("situation", "nowhere"))
        client = self.TestClient(self.server.app)  # 沒登入
        for url in ("/api/map", "/api/map/base", "/api/map/state"):
            r = client.get(url)
            emit(f"沒登入 GET {url}", [r.status_code, r.text[:200]])

    def base(self) -> None:
        """底圖：每個人連問兩次（第二次是伺服器的快取）；不同的人（開放的地點不同、鍵不同）；看的人換了地點。"""
        for who in (self.GUAN, self.HUANG, self.LONE, self.NEWBIE):
            self.get(who, "/api/map/base")
            self.get(who, "/api/map/base")
        far = sorted(self.c.locations)[0]
        self.place(self.GUAN, far)
        self.get(self.GUAN, "/api/map/base")
        self.place(self.GUAN, self.hub())
        self.get(self.GUAN, "/api/map/base")

    def state(self) -> None:
        """疊層：四種人各看；出陣約戰關著（出陣那一格與今天去哪裡出陣的推薦換一種算法）再打開。"""
        for who in (self.GUAN, self.HUANG, self.LONE, self.NEWBIE):
            self.get(who, "/api/map/state")
        if self.profile in DUEL_PROFILES:
            self.set_duel(False)
            try:
                for who in (self.GUAN, self.HUANG):
                    self.three_views(who, "約戰關著")
            finally:
                self.set_duel(True)
            self.get(self.GUAN, "/api/map/state")

    def orders_how(self) -> None:
        """map2：軍令卡的 how（/api/main 的 orders：order_cards.order_how——打擊 strike_how 他在哪、攻城 siege_how、守城、截糧、護糧各一句）。
        管理者重發本週軍令，官軍、黃巾各看一遍，局勢圖層（打擊目標的 ◎）也打一張；再換三種局面各看一遍：約戰關著（sortie_duel.on 那兩支）、
        劇本的地盤拿掉（territory.on 也就是出陣關著：攻城、守城、截糧寫遊歷那一種，領地爭奪跟著關），翻前翻後清底圖快取、翻完還原。
        重發的那一批每一方每天只有一兩道：另外照內容的每一種模板（官軍、黃巾各自的攻城、守城、截糧、護糧、打擊）各擺一道
        （orders._build，同發令那一刻的填法；id 前面加 m2:，打擊挑的人照 orders.strike_target，挑不到就不擺）。
        測試內容沒有陣營與軍令：同一串照打，orders 是 null。"""
        from tianxia import orders, rules
        from tianxia.engine import Game

        self.do(ADMIN, "issue_orders")
        shell = Game.for_world(self.c, self.world)
        s, made = shell.state, []
        week = orders.period_of(s, self.c)
        for t in self.c.orders.templates:
            if t.side not in ("guan", "huang"):
                continue
            fid = orders.strike_target(s, self.c, t) if t.kind == "strike" else None
            front = None if t.kind == "strike" else next(
                (f for f in rules.front_ids(self.c) if t.side in self.c.orders.slots.get(f, {})), None)
            if (t.kind == "strike" and fid is None) or (t.kind != "strike" and front is None):
                continue
            o = orders._build(s, self.c, t, week, front, fid)  # noqa: SLF001  同發令那一刻的填法
            o.id = "m2:" + o.id
            made.append(o)

        def put(w) -> None:
            w.orders[:] = [o for o in w.orders if not o.id.startswith("m2:")] + made

        self.world.mutate_season(put)
        emit("map2 擺的軍令", [[o.id, o.template, o.faction, o.front, o.location, o.figure] for o in made])
        scenario = self.c.scenario
        cases = [("照原樣", None, None)]
        if self.profile in DUEL_PROFILES:
            cases.append(("約戰關著", False, None))
        cases.append(("劇本的地盤拿掉", None, "drop") if scenario.territory is not None else ("劇本本來就沒有地盤", None, None))
        for label, duel, land in cases:
            old_land = scenario.territory
            if duel is not None:
                self.set_duel(duel)
            if land == "drop":
                scenario.territory = None
            self.server.MAP_BASE.clear()
            try:
                emit(f"軍令卡 {label}", None)
                for who in (self.GUAN, self.HUANG, self.LONE):
                    self.peek(who, "/api/main", ("orders",))
                self.peek(self.GUAN, self.q("situation"), ("detail", "legend"))
            finally:
                scenario.territory = old_land
                self.set_duel(True)
                self.server.MAP_BASE.clear()
        self.defended()

    def defended(self) -> None:
        """map2（第 50 批審查補的）：守城卡「有地點」那一支（order_cards.order_how 守城那兩行 conquest.duel_on、territory.on）。上面三種局面
        守城都是「沒有對面在推」或照守勢行動，走不到那兩行：每一方的守城軍令（m2: 那一批），在它那條戰線上挑第一塊自家佔著、只差沒人在推的
        區塊（conquest.push_problem 守那一邊只回 WHY_IDLE），把對面那一條擺到 40（不到警報線 alarm_at），照原樣（約戰開著）與約戰關著
        官軍、黃巾各看一遍軍令卡、局勢圖層打一張；看完把領地爭奪那一份整個放回去，後面的段落照舊。測試內容沒有軍令，不擺。"""
        from tianxia import conquest

        world = self.world.get_season()
        spots: list[tuple[str, str]] = []
        for o in world.orders:
            if not o.id.startswith("m2:") or o.template != "defend" or o.front is None:
                continue
            loc = next((b for b in conquest.blocks(self.c) if conquest.line_of(world, self.c, b) == o.front
                        and conquest.holder(world, self.c, b) == o.faction
                        and conquest.push_problem(world, self.c, o.faction, b, "hold") == conquest.WHY_IDLE), None)
            if loc is not None:
                spots.append((loc, "huang" if o.faction == "guan" else "guan"))
        emit("map2 守城擺的地方", spots)
        if not spots:
            return
        saved = None if world.conquest is None else world.conquest.model_copy(deep=True)
        try:
            for loc, foe in spots:
                self.preset_bar(loc, foe, 40.0, self.GUAN if foe == "guan" else self.HUANG)
            cases = [("對面推到自家一塊", None)] + ([("對面推到自家一塊、約戰關著", False)] if self.profile in DUEL_PROFILES else [])
            for label, duel in cases:
                if duel is not None:
                    self.set_duel(duel)
                self.server.MAP_BASE.clear()
                try:
                    emit(f"軍令卡 {label}", None)
                    for who in (self.GUAN, self.HUANG):
                        self.peek(who, "/api/main", ("orders",))
                    self.peek(self.GUAN, self.q("situation"), ("detail", "legend"))
                finally:
                    self.set_duel(True)
                    self.server.MAP_BASE.clear()
        finally:
            def back(w) -> None:
                w.conquest = saved

            self.world.mutate_season(back)
            self.server.MAP_BASE.clear()

    def details(self) -> None:
        """map2：詳情欄（輿圖包 layers.detail_text〔拆之前在 atlas〕與它叫的圖層那一半：大區的大勢、地盤、龍頭人物〔常出沒、此地的大勢人物、出兵之前的「第 N 週起」、
        按兵不動、聲威會回〕、敵情〔自己陣營的操練〕、意境與地利、劇情〔主線目標、最近的傳聞、這一帶離得遠〕、路線）一處一處點：
        官軍、黃巾每一個畫得出來的地點各點一次，散人與序章新人點頭尾兩處。"""
        for who in (self.GUAN, self.HUANG):
            self.detail_tour(who, "開季", sorted(self.places_of(who)))
        for who in (self.LONE, self.NEWBIE):
            places = sorted(self.places_of(who))
            self.detail_tour(who, "開季", places[:1] + places[-1:])

    def toggles(self) -> None:
        """輿圖看的設定各翻一下（在記憶體裡，翻完還原；兩份程式同一步翻、同一步翻回）：意境提示（輿圖的意境濾鏡與詳情那一行）、
        盡頭阻力（疊層的推力說明）、劇本的地盤（寫了 territory 的才有地盤那一層；翻成沒有就是測試內容那種畫面）。
        全圖開放、地盤、出陣已經不是 Config 的開關（Config 上沒有 open_map、territory.enabled、sortie.enabled），不翻。"""
        cfg, scenario = self.c.config, self.c.scenario
        for label, holder, attr, value in (("意境提示", cfg.insight_strong, "enabled", not cfg.insight_strong.enabled),
                                           ("盡頭阻力", cfg.push_resistance, "enabled", not cfg.push_resistance.enabled),
                                           ("劇本的地盤", scenario, "territory", None)):
            old = getattr(holder, attr)
            if old is None:
                emit(f"開關 {label}：這份內容沒有", None)
                continue
            setattr(holder, attr, value)
            self.server.MAP_BASE.clear()  # 底圖快取的鍵不含這些開關：不清的話翻了也看不到（審查 11/05：意境提示整段只算過一次底圖）
            try:
                emit(f"開關 {label} 翻成", None if value is None else value)
                for who in (self.GUAN, self.NEWBIE):
                    self.three_views(who, f"{label}翻過", full=who == self.GUAN)
            finally:
                setattr(holder, attr, old)
                self.server.MAP_BASE.clear()
        self.three_views(self.GUAN, "開關都還原")

    def web(self) -> None:
        """網頁檔：map.js 的整檔 sha256、長度、型別與快取標頭；index.html 載入 map.js 與 app.js 的那兩行與先後、樣式表。
        app.js 不比整檔雜湊、也不比別的 script：這一軌守的是 map.js，別的批把一段搬出 app.js、開自己的檔是刻意的（例：web/legacy.js），比了只會紅。"""
        import re

        who = self.GUAN
        self.begin()
        client = self.clients[who]
        for url in ("/static/map.js", "/static/app.js", "/static/沒有這個檔.js"):
            r = client.get(url)
            body = [] if url == "/static/app.js" else [len(r.content), hashlib.sha256(r.content).hexdigest()]
            emit(f"GET {url}", [r.status_code, *body, r.headers.get("content-type"), r.headers.get("cache-control")])
        page = client.get("/")
        scripts = [s for s in re.findall(r'<script src="([^"]+)"', page.text) if s.split("?")[0] in ("/static/map.js", "/static/app.js")]
        emit("GET / 載入的檔", [page.status_code, [s.split("?")[0] if s.startswith("/static/app.js") else s for s in scripts],  # ?v= 是內容的雜湊：map.js 留、app.js 不留
                                 re.findall(r'<link rel="stylesheet" href="([^"]+)"', page.text)])

    def road(self) -> None:
        """安排前往：走不成的帶 map（就在這裡、沒這個地方；剛進門的人也站在那裡，跟就在這裡是同一種）；走成的兩種（步行、疾行：賀凌川疾行那一趟當場就到）；走在路上的人看輿圖。"""
        far = self.farthest(self.WALKER)
        emit("岑九皋走最遠的一趟", far)
        if far is not None:
            self.call(self.WALKER, "POST", "/api/travel", {"place": far, "mode": "walk", "layer": "enemies"})
            self.three_views(self.WALKER, "走在路上", full=True)
            for layer in MAP_LAYER_IDS:
                self.get(self.WALKER, self.q(layer, far))
        here = self.chars.load(self.GUAN).player.location
        self.call(self.GUAN, "POST", "/api/travel", {"place": here, "mode": "walk", "layer": "routes"})
        self.call(self.GUAN, "POST", "/api/travel", {"place": "nowhere", "mode": "walk"})
        self.call(self.NEWBIE, "POST", "/api/travel", {"place": here, "mode": "dash"})
        spots = [p for p in self.places_of(self.HUANG) if p != self.chars.load(self.HUANG).player.location]
        if spots:
            self.call(self.HUANG, "POST", "/api/travel", {"place": spots[len(spots) // 2], "mode": "dash"})
            self.three_views(self.HUANG, "疾行出發之後")

    def blocks(self) -> None:
        """map2：atlas.travel_block 的先後（先後就是回給玩家的那一句）一層一層剝。祁照晚先擺「跟著韓望舒」、站著按前往（不擋：跟著的人
        自己先走就散了），走在路上之後五格疊上去：叛投待確認（有陣營的內容）、正在答話（fs_asking，有伏筆鏈的內容）、跟著別人走在路上
        （tagalong＋journey）、閉關中、守著埋伏；每一層按一次前往（/api/travel 那一句與疊層的 travel_block），再拿掉最上面那一格。"""
        who = self.PEEL
        self.enroll(who, "guan", self.hub())
        far = self.farthest(who)
        self.follow(who, self.GUAN)
        self.me(who, "跟著韓望舒、站著")
        self.go_to(who, far)
        self.me(who, "站著按了前往之後")
        other = self.other_place(who, far)
        chain = self.chain_id()
        layers = []
        if self.factions_on():
            layers.append(("pending_defect", "huang"))
        if chain is not None:
            layers.append(("fs_asking", chain))
        layers += [("tagalong", "follow"), ("busy_until", 4.0e9), ("ambush", "lay")]
        emit("一層一層疊上去的", [name for name, _ in layers])
        for name, value in layers:
            if value == "follow":
                self.follow(who, self.GUAN)
            elif value == "lay":
                self.lay_ambush(who)
            else:
                self.edit(who, lambda p, name=name, value=value: setattr(p, name, value))
        for name, _ in [*layers, ("全部拿掉", None)]:
            self.me(who, f"最上面是 {name}")
            self.go_to(who, other)
            self.peek(who, self.q("routes", other), ("travel",))
            if name == "全部拿掉":
                break
            self.edit(who, lambda p, name=name: setattr(p, name, None))
        self.me(who, "剝完")

    def cut(self) -> None:
        """map2 的切點：葉聞鐘看了題還沒答（fs_asking 有值；沒有伏筆鏈的內容照擺一個人、不擺題）、柏青崖跟著韓望舒走在路上
        （先自己出發、再擺成跟著；測試內容的路短，切下去時多半已經到了，切在路上靠 season21、week7）。兩個人各按一次前往。"""
        self.enroll(self.ASKER, "guan", self.hub())
        chain = self.chain_id()
        if chain is not None:
            self.edit(self.ASKER, lambda p: setattr(p, "fs_asking", chain))
        self.main(self.ASKER)
        self.go_to(self.ASKER, self.other_place(self.ASKER))
        self.me(self.ASKER, "前半停在")
        self.enroll(self.TAGGER, "guan", self.hub())
        far = self.farthest(self.TAGGER)
        self.go_to(self.TAGGER, far)
        self.follow(self.TAGGER, self.GUAN)
        self.main(self.TAGGER)
        self.go_to(self.TAGGER, self.other_place(self.TAGGER, far))
        self.me(self.TAGGER, "前半停在")

    def half(self) -> None:
        """前半停在：祝聽雨站在最遠的地方等著、岑九皋走在路上、地盤進度擺到高（有地盤的內容）。"""
        if self.contested():
            from tianxia import conquest

            blocks = sorted(conquest.blocks(self.c))
            for loc, side in zip(blocks[:2], ("guan", "huang")):
                self.preset_bar(loc, side, 60.0, self.GUAN if side == "guan" else self.HUANG)
        for who in (self.WALKER, self.HUANG, self.LONE):
            self.get(who, "/api/map/state")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.WALKER, self.HUANG):
            self.three_views(who, "接手")

    def unblock(self) -> None:
        """map2 後半：新程式接手前半擺好的兩個人。葉聞鐘看輿圖、按前往（擋在答話）、按作罷（fs:leave）、再按前往；
        柏青崖看輿圖、按前往（擋在跟著同行）、在路上按分道揚鑣（act:part）、再按前往（改道）。抵達在下一段 arrive。"""
        self.three_views(self.ASKER, "接手")
        target = self.other_place(self.ASKER)
        self.go_to(self.ASKER, target)
        self.peek(self.ASKER, "/api/choose", ("message",), {"id": "fs:leave"})
        self.me(self.ASKER, "作罷之後")
        self.go_to(self.ASKER, target)
        self.me(self.ASKER, "作罷之後再按前往")
        self.three_views(self.TAGGER, "接手")
        p = self.chars.load(self.TAGGER).player
        target = self.other_place(self.TAGGER, None if p.journey is None else p.journey.path[p.journey.last])
        self.go_to(self.TAGGER, target)
        self.peek(self.TAGGER, "/api/choose", ("message",), {"id": "act:part"})
        self.me(self.TAGGER, "分道揚鑣之後")
        self.go_to(self.TAGGER, target)
        self.me(self.TAGGER, "分道揚鑣之後再按前往")

    def arrive(self) -> None:
        """走在路上的人走到（時鐘一段一段往前推、每一下同步），到了之後再看一遍（map2：葉聞鐘、柏青崖改道之後也在這裡走到）。"""
        for who in (self.WALKER, self.HUANG, self.TAGGER, self.ASKER):
            n = 0
            while n < 40 and self.chars.load(who).player.journey is not None:
                STEP[0] += 20
                self.main(who)
                n += 1
            emit(f"{who} 同步了 {n} 次抵達", self.chars.load(who).player.location)
            self.three_views(who, "抵達之後", full=who == self.WALKER)

    def days(self) -> None:
        """時間過了兩天、再兩天（軍令、戰線、每週地盤、傳聞跟著走）：每過一段，四種人各看一遍。"""
        for _ in range(2):
            STEP[0] += 2 * 1440
            for who in (self.GUAN, self.HUANG, self.LONE, self.NEWBIE):
                self.main(who)
            for who in (self.GUAN, self.HUANG):
                self.three_views(who, "過了兩天", full=who == self.GUAN)

    def details_again(self) -> None:
        """map2：過了四天（傳聞、軍令、戰線、人物都動了）再一處一處點：官軍、黃巾每一處，散人頭尾兩處。"""
        for who in (self.GUAN, self.HUANG):
            self.detail_tour(who, "過了四天", sorted(self.places_of(who)))
        places = sorted(self.places_of(self.LONE))
        self.detail_tour(self.LONE, "過了四天", places[:1] + places[-1:])

    def fronts(self) -> None:
        """地盤進度擺到高、警報線以上：疊層的警報與易手標記；官軍、黃巾、散人各看。"""
        if self.contested():
            from tianxia import conquest

            blocks = sorted(conquest.blocks(self.c))
            emit("地盤區塊", blocks[:3])
            for loc, side in zip(blocks[-2:], ("huang", "guan")):
                self.preset_bar(loc, side, 90.0, self.HUANG if side == "huang" else self.GUAN)
        else:
            emit("地盤：這份內容沒有", None)
        for who in (self.GUAN, self.HUANG, self.LONE):
            self.get(who, "/api/map/state")
        self.get(self.GUAN, self.q("situation", self.chars.load(self.GUAN).player.location))

    def web_again(self) -> None:
        self.web()

    def bots(self) -> None:
        """假人：BotRunner 兩個在城裡若干輪（bot_policy 的移動選項叫 Game.travel_options）；沒有任何 /api/map 的呼叫。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        spot = self.hub()
        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, spot, None
            p.visited.add(spot)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        if on:  # map2：開一場決戰的集結，假人的 _toward_battle（自己這一方在集結、人不在那一區）才會經 Game.travel_options 往那裡走
            # 長社火攻到這一段多半已經結算了（管理者開不了），開不成就開廣宗（同 battle 一軌假人打的第二場）
            for op, battle_id in (("start_showdown", "changshe_fire"), ("start_showdown", "guangzong")):
                self.do(ADMIN, op, {"id": battle_id})
                b = self.world.get_battle()
                if b is not None and b.phase == "muster":
                    break
            emit("假人那一段的決戰", None if b is None else [b.battle_id, b.phase])
        else:
            emit("假人那一段的決戰：這份內容沒有陣營", None)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(43), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_MAP_TICKS", "10"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "journey": None if s.player.journey is None else s.player.journey.model_dump(mode="json"),
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.three_views(self.GUAN, "收季之後", full=True)
        self.do(ADMIN, "next_season")
        self.main(self.GUAN)
        self.three_views(self.GUAN, "換季之後", full=True)


# 改一個字（selftest）：局勢圖層圖例那一句（mapview.LEGEND_LAYERS["situation"]；舊名的檔與搬進包的檔兩處找，哪一處有就改哪一處）
register_track("map", MapScenario, (("tianxia/mapview.py", "tianxia/features/map/mapview.py"),
                                    ("常出沒　大區越紅，大勢越凶", "常出沒　大區越紅，大勢越凶！")), "week7")
