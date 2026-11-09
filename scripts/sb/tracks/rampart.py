"""same_behavior 一軌一檔：rampart（這一檔登記 rampart）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from collections import Counter

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, CLOCK0, STEP, emit, register_track

# ═══════════════════════════ rampart：攻城與軍令卡的冷門支（第二輪第 97 批，dev/shared-slim） ═══════════════════════
# 這一批把 siege.py 決戰那一半搬進決戰包、atlas 的軍令卡寫法搬進軍情包。battle、landturn、map 三軌（season21、week7）實跑數過：三方混戰的守將、補最後一刀、守住、
# 只到一軍，兩軍相爭，另一軍旁觀，改為助守，攻城卡與守城卡的幾句都是 0 次。這一軌只補這些。角色的名字都是原創的（PM 11/04）。


class RampartScenario(Scenario):
    """攻城冷門支與軍令卡（--track rampart，自己一個資料庫）。只打公開的 API 與不搬的世界層：**不准直接叫 siege、atlas 要搬的名字**（head 上它們不在那裡）。
    下面寫走到的，season21、week7 都實跑、逐函式數過、讀過輸出（dev/shared-slim）；測試內容沒有地盤，只看畫面、寫「沒有」。

    - cards（軍令卡）：照內容每一種模板、每一條戰線擺一道，看 how：照原樣（SIEGE_AREA_DUEL）；約戰關著（SIEGE_AREA_CONQUEST）；一處、兩處進度最高；打擊目標的所在沒摸清
      （「他現在在某一帶」，unlock_flag 暫時蓋上），打擊一位挑戰不了的人（「他眼下沒在戰線上領兵」）；地盤拿掉、攻城的地點蓋上（SIEGE_UNSEEN、SIEGE_SOME_UNSEEN：領地爭奪開著時
      碰不到的地點不列，只有舊地點清單走得到）；自家三塊被推到一樣高（DEFEND_AREA_CONQUEST，約戰開著與關著 DEFEND_ACT_DUEL、DEFEND_ACT_SORTIE）；南陽一線全被戰書凍結
      （SIEGE_NONE_CONQUEST，黃巾自家被凍結的新野 DEFEND_SIEGE_CONQUEST）。看完把領地爭奪那一份與軍令放回去。
    - single（單方攻中立地）：另一軍站在那一區看 watch_line（WATCH_LINE）、按加入「此刻無法」；散人先投效攻方再改為助守（HELP_GUARD_SWITCH）。守將守住。
    - blow（三方混戰）：兩軍與助守的散人，守將打倒（MELEE_RULE、BANNER_MELEE、size_melee_guard、BLOW_RUMOR、MELEE_TAKEN_TITLE）。
    - held_open、held_end（三方混戰守將沒倒）：**前半停在第一回合打完**（那一場還在打，收場的 settle 是新程式的）；MELEE_HELD_LINE。
    - lone_open、lone_close（只到一軍）：**前半同時停在集結中**，lone_army 轉回單方是新程式的；ABSENT_SCENE_LINE、BANNER_ABSENT，守將守住。
    - tie（兩軍相爭）：那一塊的隊伍暫時拿掉才開得成沒有守將的一場（開季中立的每一塊都有隊伍），BANNER_OPEN；最後一回合之前戰局擺回中線，STALEMATE_LINE、STALEMATE_TITLE。
    - no_name（守將還站著就算補上最後一刀）：最後一回合之前把 blow 擺好，BLOW_RUMOR_NOBODY。
    - bots：伺服器假人打一場三方混戰（兩軍各二），跑到收場，守軍守住。

    **這一軌走不到的**（靜態看的）：JOIN_SIDE、JOIN_OWN（選單上沒有那一顆，Game.choose 先回「此刻無法」；只有 tests/acts/test_conquest_siege.py 直接叫）；scene_line 與
    SCENE_LINE、MELEE_SCENE_LINE（只剩測試叫，畫面走 scene_note）；DEFEND_ACT_PLAIN（領地爭奪開著 territory.on 就是真的）；strike_how「他在哪裡你還沒摸清」
    （region_of 區外也歸最近的大區，有大區就不是 None）；settle 的 keeper 是 None（三方混戰一定有守將）。這幾句由 tests/acts/test_conquest_siege.py、test_conquest_flip.py 守。"""

    PLAYERS = {"霍長纓": "guan", "裴孤城": "guan", "邵鳴鏑": "huang", "屠蒼崖": "huang", "溫渡秋": None}
    NEWBIE = "初臨城下"
    G1, G2, H1, H2, LONE = tuple(PLAYERS)
    BOT_SEATS = [("垣甲", "guan"), ("垣乙", "guan"), ("垣丙", "huang"), ("垣丁", "huang")]
    BOTH = ("guan", "huang")
    # season21 開季就在潁汝開長社火攻（站那一區的人看到的是決戰）：這幾場都不放潁汝。同一刻有兩場的只有 B、C（各在一區）。
    SIEGES = {"E": (("guan",), "nanyang_wilds"), "A": (BOTH, "nanyang_road"), "B": (BOTH, "lulin_zhai"), "C": (BOTH, "baima_ford"),
              "D": (BOTH, "juma_river"), "F": (BOTH, "xiaquyang"), "G": (BOTH, "yu_river")}
    STEP_SECONDS = 10.0  # 同決戰那一軌：一回合最多等 180 秒，一步一分的話出招的請求還沒送齊回合就逾時
    PHASES_FIRST = ["setup", "join", "cards", "single", "blow", "held_open", "lone_open", "half"]
    PHASES_SECOND = ["resume", "held_end", "lone_close", "tie", "no_name", "bots"]

    # ── 小工具 ──

    def begin(self) -> None:
        """同決戰那一軌：一步十秒；每個請求換一份空的勝算記憶（前半＋後半是兩個行程）。"""
        STEP[0] += 1
        CLOCK[0] = CLOCK0 + STEP[0] * self.STEP_SECONDS
        random.seed(STEP[0])
        self.server.GAMES.clear()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip_past(self, deadline: float) -> None:
        steps = max(0, int((deadline - CLOCK0) // self.STEP_SECONDS) - STEP[0])
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 步", None)

    def on(self) -> bool:
        from tianxia import conquest, territory

        return bool(territory.on(self.c) and conquest.on(self.c, self.world.get_season()))

    def slot_of(self, key: str):
        season = self.world.get_season()
        if season.conquest is None:
            return None
        return next((s for s in season.conquest.schedule if s.id == f"rampart-{key}"), None)

    def battle_of(self, key: str):
        slot = self.slot_of(key)
        if slot is None or slot.record_id is None:
            return None
        return next((b for b in self.world.get_sieges() if b.record_id == slot.record_id), None) or self.world.ended_battle(slot.record_id)

    def row(self, key: str, tag: str) -> None:
        """這一場此刻的樣子：時程表那一筆、那一塊歸誰與進度、那一場（回合、戰局、結果、名單、SiegeInfo、留守與整份的雜湊）、天下大事最後幾句。"""
        from tianxia import conquest

        season = self.world.get_season()
        slot, b, loc = self.slot_of(key), self.battle_of(key), self.SIEGES[key][1]
        emit(f"攻城 {key} {tag}", {
            "slot": None if slot is None else [slot.id, slot.status, slot.record_id, slot.winner, slot.attackers],
            "holder": conquest.holder(season, self.c, loc), "bars": {s: round(v, 3) for s, v in sorted(conquest.bars(season, loc).items())},
            "day_log": None if season.conquest is None else [n.model_dump(mode="json") for n in season.conquest.day_log][-2:],
            "rumors": [r.text for r in season.rumors][-4:],
            "battle": None if b is None else {
                "id": b.battle_id, "phase": b.phase, "round": b.round_number, "trend": b.trend,
                "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin], "unfinished": b.unfinished,
                "who": {n: [q.faction, q.eliminated] for n, q in sorted(b.participants.items())},
                "commanders": [[c.fid, c.name, c.faction, c.neili, c.neili_cap, c.fallen_round, c.felled_by] for c in b.commanders],
                "siege": None if b.siege is None else b.siege.model_dump(mode="json"),
                "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()},
        })

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        emit(f"{who} {tag}", {
            "journal": [[e.title, e.tag, list(e.lines)[:4]] for e in state.journal[:3]],
            "state": hashlib.sha256(state.model_dump_json().encode("utf-8")).hexdigest()})

    def post(self, key: str, sync: str) -> None:
        """時程表上排一場（同 tests/kit/conquest_kit.announce：不看階與門檻），此刻就等著開集結；下一個同步的人開成集結（world.start_pending_battle）。
        開打在季時間半小時之後。不走管理者工具：它併不成兩軍（下第二張之前第一張就開了），這一軌最要的就是兩軍併成一場。"""
        from tianxia import conquest
        from tianxia.features.territory_acts import conquest_day
        from tianxia.state import SiegeSlot

        attackers, loc = self.SIEGES[key]

        def fn(w) -> None:
            if w.conquest is None:
                conquest.update(w, self.c)
            w.conquest.schedule.append(SiegeSlot(
                id=f"rampart-{key}", key=w.conquest.settled_key, loc=loc, minute=21 * 60, at=w.time + 1800, muster_at=w.time, status="waiting",
                attackers=list(attackers), by={a: conquest_day.LETTER for a in attackers}, reasons={a: "" for a in attackers}))

        self.world.mutate_season(fn)
        emit(f"排了 {key} {loc}", list(attackers))
        self.main(sync)
        self.row(key, "開了集結")

    def press(self, who: str, key: str, stem: str) -> None:
        """按這一場的那一顆（同一個大區兩場打得進去時鈕帶 @流水號，按自己那一場的）；選單上沒有也照按，看被擋的那一句。"""
        ids = self.ids(self.main(who))
        b = self.battle_of(key)
        pick = next((i for i in sorted(ids) if i.split("@")[0] == stem and ("@" not in i or (b is not None and i.endswith(f"@{b.record_id}")))), stem)
        emit(f"{who} 按 {pick}", ids.get(pick, {}).get("label"))
        self.choose(who, pick)

    def stage(self, key: str, fn) -> None:
        b = self.battle_of(key)
        if b is not None:
            self.world.mutate_siege(b.record_id, fn)

    def start(self, key: str, *who: str) -> None:
        """集結截止：時鐘推過截止，這幾位各看一次（第一個同步的人把那一場推到開打）。"""
        b = self.battle_of(key)
        if b is not None and b.phase == "muster":
            self.skip_past(b.muster_deadline_real)
        for name in who:
            self.main(name)
        self.row(key, "開打")

    def moves(self, plan: dict[str, str]) -> None:
        for who, move in plan.items():
            ids = self.ids(self.main(who))
            acts = sorted(i for i, o in ids.items() if i.startswith("battle:act:") and o.get("enabled"))
            if acts:
                self.choose(who, next((i for i in acts if f"（{move}" in ids[i].get("label", "")), acts[0]))

    def finish(self, key: str, plan: dict[str, str], before_last=None) -> None:
        """照回合出招打到收場；回合沒結就把時鐘推過期限。before_last：最後一回合之前改一下那一場（只叫一次）。收場之後每一位收補送。"""
        from tianxia.features.battle import instance as battle_instance

        first = next(iter(plan))
        for _ in range(14):
            b = self.battle_of(key)
            if b is None or b.phase == "ended":
                break
            if before_last is not None and b.round_number + 1 >= battle_instance.total_rounds(self.c.battles[b.battle_id]):
                self.stage(key, before_last)
                before_last = None
            at = b.round_number
            self.moves(plan)
            b = self.battle_of(key)
            if b is not None and b.phase == "active" and b.round_number == at:
                self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
                self.main(first)
        self.row(key, "收場")
        for who in plan:
            self.main(who)
            self.me(who, f"{key} 收補送之後")
        _, data = self.call(first, "GET", "/api/reports")
        for rid in [r["id"] for r in data.get("list", [])][:1] if isinstance(data, dict) else []:
            self.call(first, "GET", f"/api/reports?id={rid}")

    def seat(self, key: str, *who: str) -> None:
        for name in who:
            self.place(name, self.SIEGES[key][1])

    # ── 軍令卡 ──

    def look(self, tag: str) -> None:
        emit(f"軍令卡 {tag}", None)
        for who in (self.G1, self.H1):
            self.main(who)

    def cards(self) -> None:
        if not self.on():
            emit("這份內容沒有地盤：軍令卡、攻城那幾段略過，畫面照看", None)
            self.main(self.G1)
            return
        from tianxia import conquest, figures, orders, rules
        from tianxia.engine import Game

        self.do(ADMIN, "issue_orders")
        s, made = Game.for_world(self.c, self.world).state, []
        week = orders.period_of(s, self.c)
        for t in self.c.orders.templates:
            if t.side not in self.BOTH:
                continue
            if t.kind == "strike":
                fid = orders.strike_target(s, self.c, t)
                rows = [] if fid is None else [(None, fid)]
            else:
                rows = [(f, None) for f in rules.front_ids(self.c) if t.side in self.c.orders.slots.get(f, {})]
            for front, fid in rows:
                o = orders._build(s, self.c, t, week, front, fid)  # noqa: SLF001  同發令那一刻的填法（map 那一軌同一招）
                o.id = f"rp:{t.kind}:{t.side}:{front}"
                made.append(o)
            off = next((f for f in sorted(self.c.figures) if not figures.can_challenge(s, self.c, f)), None) if t.kind == "strike" else None
            if off is not None:  # 打擊一位此刻挑戰不了的人（「他眼下沒在戰線上領兵」）
                o = orders._build(s, self.c, t, week, None, off)  # noqa: SLF001
                o.id = f"rp:strike:{t.side}:off"
                made.append(o)

        def put(w) -> None:
            w.orders[:] = [o for o in w.orders if not o.id.startswith("rp:")] + made

        self.world.mutate_season(put)
        emit("擺的軍令", [[o.id, o.template, o.faction, o.front, o.location, o.figure] for o in made])
        world = self.world.get_season()
        saved = None if world.conquest is None else world.conquest.model_copy(deep=True)
        self.look("照原樣")
        self.set_duel(False)
        self.look("約戰關著")
        self.set_duel(True)
        self.preset_bar("nanyang_road", "guan", 30.0, self.G1)
        self.look("一處進度最高")
        self.preset_bar("nanyang_wilds", "guan", 30.0, self.G1)
        self.look("兩處進度最高")
        spots = [o.figure for o in made if o.template == "strike" and o.figure]
        with self.sealed(*sorted({figures.state_of(s, self.c, f).location for f in spots} & set(self.c.locations))):
            self.look("打擊目標的所在沒摸清")
        land = self.c.scenario.territory
        self.c.scenario.territory = None  # 同 map 那一軌：地盤拿掉才走舊的地點清單，蓋上的地點才留在 siege_places（領地爭奪開著時碰不到的地點不列）
        try:
            with self.sealed("guan_camp", "luzhi_camp"):
                self.look("地盤拿掉、攻城的地點沒摸清")
        finally:
            self.c.scenario.territory = land
        for loc in ("yingchuan", "yingshui", "yingchuan_wilds"):
            self.preset_bar(loc, "huang", 40.0, self.H1)
        self.look("對面把自家三塊推到一樣高")
        self.set_duel(False)
        self.look("對面把自家三塊推到一樣高、約戰關著")
        self.set_duel(True)

        def freeze(w) -> None:
            for loc in ("nanyang_road", "nanyang_wilds", "yu_river", "lulin_zhai", "xinye"):
                w.conquest.schedule.append(type(self).frozen_slot(w, loc))

        self.world.mutate_season(freeze)
        self.look("南陽一線全被戰書凍結")

        def back(w) -> None:
            w.conquest = saved
            w.orders[:] = [o for o in w.orders if not o.id.startswith("rp:")]

        self.world.mutate_season(back)
        self.look("放回去")
        emit("進度放回去", conquest.bars(self.world.get_season(), "nanyang_road"))

    @contextlib.contextmanager
    def sealed(self, *locs: str):
        """這幾處暫時蓋上 unlock_flag（算沒摸清，atlas.is_known）；出來放回原本的。"""
        keep = {loc: self.c.locations[loc].unlock_flag for loc in locs}
        for loc in locs:
            self.c.locations[loc].unlock_flag = "rampart_sealed"
        try:
            yield
        finally:
            for loc, flag in keep.items():
                self.c.locations[loc].unlock_flag = flag

    @staticmethod
    def frozen_slot(w, loc: str):
        """官軍下了戰書、還沒開集結的一場（只為了凍結那一塊，放回去時整份蓋掉）。"""
        from tianxia.features.territory_acts import conquest_day
        from tianxia.state import SiegeSlot

        return SiegeSlot(id=f"rampart-z-{loc}", key=w.conquest.settled_key, loc=loc, minute=21 * 60, at=w.time + 86400, muster_at=w.time + 80000,
                         attackers=["guan"], by={"guan": conquest_day.LETTER}, reasons={"guan": ""})

    # ── 攻城 ──

    def single(self) -> None:
        """單方攻中立地（官軍）：黃巾的人站在那一區，看場景那一句、按加入被擋；散人先投效官軍、再改為助守；打到收場。"""
        if not self.on():
            return
        self.seat("E", self.G1, self.H1, self.LONE)
        self.post("E", self.G1)
        self.press(self.H1, "E", "battle:join:huang")  # 選單上沒有這一顆：照按，「此刻無法」
        self.press(self.LONE, "E", "battle:enlist:guan")
        self.press(self.LONE, "E", "battle:enlist:huang")
        self.me(self.LONE, "改為助守之後")
        self.press(self.G1, "E", "battle:join:guan")
        self.start("E", self.G1, self.LONE, self.H1)
        self.finish("E", {self.G1: "強攻", self.LONE: "固守"})

    def blow(self) -> None:
        """三方混戰：官軍、黃巾、助守的散人；守將的氣血擺低，官軍那一下補上最後一刀，拿下那一塊。"""
        if not self.on():
            return
        from tianxia.core.battle_base import GUARD

        self.seat("A", self.G1, self.H1, self.LONE)
        self.post("A", self.G1)
        self.press(self.G1, "A", "battle:join:guan")
        self.press(self.H1, "A", "battle:join:huang")
        self.press(self.LONE, "A", f"battle:enlist:{GUARD}")
        self.start("A", self.G1, self.H1, self.LONE)

        def low(b) -> None:
            for c in b.commanders:
                if c.faction == GUARD:
                    c.neili_cap, c.neili = 1000.0, 10.0
            b.orders[GUARD] = "固守"

        self.stage("A", low)
        self.finish("A", {self.G1: "強攻", self.H1: "固守", self.LONE: "固守"})

    def held_open(self) -> None:
        """三方混戰守將沒倒的那一場：打完第一回合就切（前半）。"""
        if not self.on():
            return
        self.seat("B", self.G2, self.H2)
        self.post("B", self.G2)
        self.press(self.G2, "B", "battle:join:guan")
        self.press(self.H2, "B", "battle:join:huang")
        self.start("B", self.G2, self.H2)
        self.moves({self.G2: "固守", self.H2: "固守"})
        self.row("B", "第一回合之後")

    def lone_open(self) -> None:
        """只到一軍那一場：官軍與助守的散人加入，停在集結中就切（前半）；黃巾的人不來。"""
        if not self.on():
            return
        from tianxia.core.battle_base import GUARD

        self.seat("C", self.G1, self.LONE)
        self.post("C", self.G1)
        self.press(self.G1, "C", "battle:join:guan")
        self.press(self.LONE, "C", f"battle:enlist:{GUARD}")
        self.row("C", "集結中")

    def half(self) -> None:
        emit("前半停在：B 第一回合打完、C 集結中", None)

    def resume(self) -> None:
        self.login_all()

    def held_end(self) -> None:
        if not self.on():
            self.main(self.G1)
            return
        self.row("B", "接手")
        self.finish("B", {self.G2: "固守", self.H2: "固守"})

    def lone_close(self) -> None:
        """集結截止：另一軍沒到，轉回單方攻中立地（lone_army）；助守的人跟著守將站過去。打到收場。"""
        if not self.on():
            return
        self.start("C", self.G1, self.LONE)
        self.finish("C", {self.G1: "強攻", self.LONE: "固守"})

    def tie(self) -> None:
        """兩軍相爭：那一塊的隊伍暫時拿掉（開集結那一下才讀），沒有守將、兩軍正面打；最後一回合之前戰局擺回中線，出同一招，相持。"""
        if not self.on():
            return
        from tianxia.features.battle import instance as battle_instance

        _, loc = self.SIEGES["D"]
        place, land = self.c.locations[loc], self.c.scenario.territory
        enemies, garrison = list(place.enemies), land.neutral_garrison.get(loc)
        place.enemies = []
        land.neutral_garrison.pop(loc, None)
        try:
            self.seat("D", self.G2, self.H2)
            self.post("D", self.G2)
        finally:
            place.enemies = enemies
            if garrison is not None:
                land.neutral_garrison[loc] = garrison
        self.press(self.G2, "D", "battle:join:guan")
        self.press(self.H2, "D", "battle:join:huang")
        self.start("D", self.G2, self.H2)

        def center(b) -> None:
            b.trend = battle_instance.CENTER

        self.finish("D", {self.G2: "固守", self.H2: "固守"}, before_last=center)

    def no_name(self) -> None:
        """三方混戰最後一回合之前把 blow 擺好、守將還站著（felled_by 是空的）：寫沒有名字的那一句。"""
        if not self.on():
            return

        def blow(b) -> None:
            b.siege.blow = "huang"

        self.seat("F", self.G1, self.H1)
        self.post("F", self.G1)
        self.press(self.G1, "F", "battle:join:guan")
        self.press(self.H1, "F", "battle:join:huang")
        self.start("F", self.G1, self.H1)
        self.finish("F", {self.G1: "固守", self.H1: "固守"}, before_last=blow)

    def bots(self) -> None:
        """伺服器假人打一場三方混戰（同決戰那一軌 siege_bots 的寫法：BotRunner，random.Random(9)，時鐘一輪推一分）：兩軍各二，跑到收場再三輪。"""
        if not self.on():
            emit("這一季沒有地盤：假人那一段略過", None)
            return
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        _, loc = self.SIEGES["G"]
        for i, (name, faction) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(30 + i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=faction, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        self.post("G", self.G1)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(9), clock=lambda: CLOCK[0])
        online = server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_SIEGE_TICKS", "90"))):
                STEP[0] += 5  # 一輪推一分（這一軌一步十秒）
                self.begin()
                for report in (runner.tick(), runner.battle_tick()):
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                slot = self.slot_of("G")
                if slot is not None and slot.status in ("done", "void"):
                    totals["after_end"] += 1
                    if totals["after_end"] >= 3:
                        break
        finally:
            server_bots.is_online = online
        self.row("G", "假人那一場")
        names = {n for n, _ in self.BOT_SEATS}
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        emit("假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})


register_track("rampart", RampartScenario, (("tianxia/features/battle/siege_rules.py", "tianxia/siege.py"),
                                            ("{side}補上最後一刀，拿下{place}", "{side}補上最末一刀，拿下{place}")), "week7",
               covers=("battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction", "figure_acts",
                       "gear", "guide", "jieyi", "looks", "military", "outlets", "peers", "seal", "sense", "smithy",
                       "socialize", "sortie", "stamina_plays", "story", "tavern", "territory_acts", "travel", "zongmen"))
