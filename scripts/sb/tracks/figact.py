"""same_behavior 一軌一檔：figact（這一檔登記 figact）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track

# ═══════════════════════════ figact：大勢人物的行動（全部拆包第 31 批，dev/figure-acts-1） ═══════════════════════════
# 挑戰大勢人物本人（Game 上 _challenge 等 13 個）、護衛犒軍探望（aid:，figure_aid）、助他一臂或壞他的事（plan:）、月旦評（yuedan）、管理者救回人物
# 搬進新包 tianxia/features/figure_acts/（舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-大勢人物包-第1批.md）。角色的名字都是原創的（PM 11/04：新開的軌不用既有作品的人名）。

FIGACT_YUE = "少年英發，前程無量"  # 假模型寫的月旦評（八到十六字，不含名號）
_FIGACT_CLIENTS: dict[type, type] = {}


def _figact_client(base: type) -> type:
    """月旦評的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["yuedan"] 給了（"all"＝每個人都寫、"mixed"＝第二個人寫太短）時，
    YuedanBatch 照名單回評語；其餘照 base（丟連線錯誤，月旦評照固定句發）。"""
    if base not in _FIGACT_CLIENTS:
        class FigActClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "YuedanBatch" and MODEL.get("yuedan"):
                    import re

                    names = re.findall(r"^\d+\. (.+?)（", messages[-1]["content"], re.M)
                    lines = [{"name": n, "line": "太短" if MODEL["yuedan"] == "mixed" and i == 1 else FIGACT_YUE} for i, n in enumerate(names)]
                    return schema.model_validate({"lines": lines})
                return super().chat_structured(messages, schema, *a, **k)

        _FIGACT_CLIENTS[base] = FigActClient
    return _FIGACT_CLIENTS[base]


class FigActScenario(Scenario):
    """大勢人物的行動（全部拆包第 31 批；--track figact，自己一個資料庫）。
    挑戰本人（官軍大本營「常社」的皇甫嵩，黃巾的人挑他）：封雲舟打贏（模型判讀回了；寶物、三階、四階的機會調成必中；他敗走、情誼、聲威、閉門不見、
    戰報與江湖紀錄）、同一天再打贏一次（聲威一天只扣一次）、閉門不見時按灰鈕；寧無咎打成僵持、岳臨風落敗、尹疏桐在模型叫不動時打贏；選單上的勝算與灰鈕、
    官軍的人看不到挑戰鈕、散人沒有陣營沒有鈕。護衛犒軍探望（aid:）：葛望之護衛皇甫嵩、紀長庚來挑戰被護衛擋下或闖過；莊子衿犒軍（聲威被打掉才有）；
    魏敬之在官軍大本營探望退場等著回來的朱儁（朱儁是內容表上的人，這裡直接擺成退場）；黃巾的人看不到護衛鈕；護衛下線時替人物擋下的挑戰，回來同步補名望與心得。
    助他一臂與壞他的事（plan:）：擺一件開著的盤算（孫堅在宛城），蘇引鳳（官軍，只能助他）、段無咎（黃巾，只能壞他）、何不言（散人，兩樣都行）、
    重複、不在那裡；**前半停在助他一臂還沒結**（盤算還沒到點），後半快轉過了到點，結果進同步的紀錄。
    月旦評（A 鎖內拿單子、B 鎖外請模型、C 鎖內重驗才發）：快轉到第 2 週自然評一批，**前半停在寫到一半**（單子在、還沒寫）；後半先在模型叫不動時發（固定句）、
    再擺一批在模型回了時發（有一句寫太短退回固定句）、再擺一批等太久照固定句發；玩家卡上的評語。管理者救回人物（叫回選單、救回、沒退場的、不是管理者）。
    假人：BotRunner 兩個（官軍，站在常社；bot_policy.score 問 aid:、體力花不完時 _stamina_play 挑 aid:）；整季機器人在常社的選單（aid:、act:challenge: 都不按）；換季。
    沒有大勢人物的內容（測試內容）、護衛犒軍關著的設定，同一串 API 照打，寫「沒有」。"""

    GUAN_HALL = "changshe"  # 官軍的皇甫嵩一開始就在這裡（時刻表的季是波才先到；seat 依此刻誰在哪挑一處兩軍都有人物的地點）
    HUANG_WIN, HUANG_WIN2, HUANG_DRAW, HUANG_LOSE, HUANG_DEAD = "封雲舟", "寧無咎", "岳臨風", "尹疏桐", "紀長庚"
    GUARD, RALLIER, VISITOR = "葛望之", "莊子衿", "魏敬之"
    GUAN_PEER = "沈夜航"  # 官軍的人去挑戰同陣營的人物：沒有鈕
    HELPER, BLOCKER, FREE = "蘇引鳳", "段無咎", "何不言"
    VIEWER, STRANGER = "謝臨川", "鄭無雙"  # 月旦評：玩家卡的看的人、被評到的人（跟看的人站在同一處）
    PLAYERS = {HUANG_WIN: "huang", HUANG_WIN2: "huang", HUANG_DRAW: "huang", HUANG_LOSE: "huang", HUANG_DEAD: "huang",
               GUARD: "guan", RALLIER: "guan", VISITOR: "guan", GUAN_PEER: "guan", HELPER: "guan", BLOCKER: "huang", FREE: None,
               VIEWER: None, STRANGER: None}
    BOT_SEATS = ["人甲", "人乙"]
    PHASES_FIRST = ["setup", "seat", "challenge", "guarded", "rally_visit", "yuedan_open", "plan_open", "half"]
    PHASES_SECOND = ["resume", "plan_settle", "yuedan_on", "admin", "bots", "season"]

    hall = GUAN_HALL
    foe, bocai_side, friend, fallen = "nobody", "nobody", "nobody", "nobody"  # seat 挑：黃巾的人挑誰、官軍的人挑誰、護衛犒軍誰、退場等著回來的是誰
    plan_stop, plan_who, plan_place = "nobody", "nobody", None

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _figact_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        self.c.config.figure_life.yuedan_wait_seconds = 10 ** 9  # 等太久照固定句發：預設的 900 世界秒幾步就到了，這裡先壓住，要的那一段再調

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    @contextlib.contextmanager
    def tuned(self, owner=None, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config if owner is None else owner
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {k: v for k, v in values.items()})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    @contextlib.contextmanager
    def fights(self, tier: str | None):
        """這幾下的仗照寫好的 tier（同 Scenario.winning：威力、難度、亂數照算，只換結果）。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None and tier is not None:
                kwargs["tier"] = tier
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    @contextlib.contextmanager
    def drops(self):
        """寶物、三階、四階的機會調成必中（一人一季的上限照設定）。"""
        cfg = self.c.config
        before = (cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance)
        cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance = 1.0, 1.0, 1.0
        emit("掉落機會調成必中", None)
        try:
            yield
        finally:
            cfg.treasures.challenge_chance, cfg.forge_secrets.challenge_tier3, cfg.four_tiers.challenge_chance = before

    def game(self, who: str):
        """鎖外只讀的一份 Game（讀選單、算勝算；不存檔）。"""
        from tianxia.engine import Game

        self.begin()
        state = self.chars.load(who)
        state.world = self.world.get_season()
        return Game(self.c, state, world=self.world)

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    def edit_world(self, fn) -> None:
        self.world.mutate_season(fn)

    def on(self) -> bool:
        """這份內容有大勢人物、有陣營（挑戰本人看這個）。"""
        return bool(self.c.figures) and bool(self.c.scenario.factions)

    def base_of(self, faction: str) -> str | None:
        f = self.c.scenario.find_faction(faction)
        return f.join_at[0] if f is not None and f.join_at else None

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：所在、體力銀兩心得名望、打贏他幾次、這一季掉過什麼（寶物、三四階）、閉門不見、擾亂一天一次的帳、情誼、背包裡三四階素材、
        行狀、最新三則紀錄、最新一場戰報。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        mats = self.c.materials
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "stamina": p.stamina, "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0),
            "fame": p.stats.get("fame", 0), "wins": dict(sorted(p.figure_wins.items())), "rare": p.figure_rare_drops,
            "tier3": dict(sorted(p.tier3_drops.items())), "tier4": [list(p.tier4_wins), p.tier4_challenge_drops],
            "treasure": sorted(p.treasure_drops), "snub": dict(sorted(p.snubbed_until.items())), "dented": dict(sorted(p.figure_dented.items())),
            "aff": dict(sorted(p.affinities.items())), "mats": {k: v for k, v in sorted(p.materials.items()) if v > 0 and k in mats and mats[k].tier >= 3},
            "annals": [[a.kind, a.text] for a in p.annals][-4:], "journal": [[e.title, e.tag, list(e.lines)[:5]] for e in state.journal[:3]],
            "battle": None if not state.battles else state.battles[-1].model_dump(mode="json")})

    def world_view(self, tag: str) -> None:
        """全服這一包碰得到的帳：人物的聲威與狀態、站崗的護衛、犒軍探望的次數帳、盤算、月旦評、補給護衛的那幾句、世界旗標、最新天下大事與江湖史。"""
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "figures": {k: v.model_dump(mode="json") for k, v in sorted(w.figures.items())},
            "guards": [g.model_dump(mode="json") for g in w.figure_guards], "tally": dict(sorted(w.aid_tally.items())),
            "credits": {k: list(v) for k, v in sorted(w.guard_credits.items())}, "plans": [x.model_dump(mode="json") for x in w.plans],
            "yuedan": [x.model_dump(mode="json") for x in w.yuedan], "yuedan_week": w.yuedan_week, "flags": sorted(getattr(w, "flags", []) or []),
            "rumors": [r.text for r in w.rumors][-4:], "chronicle": [r.text for r in w.chronicle][-3:]})

    def week_of(self) -> int:
        from tianxia import calendar

        s = self.world.get_season()
        return calendar.point(s.time, self.c, s).week

    def forward_to_week(self, week: int) -> None:
        """管理者快轉（一天一天）到季曆第 week 週（季不夠長就快轉到頭）。"""
        for _ in range(40):
            if self.week_of() >= week:
                break
            self.do(ADMIN, "fast_forward", {"hours": 24})
        emit("季曆第幾週", self.week_of())

    def press(self, who: str, option_id: str, tag: str) -> None:
        """按選單上的一顆（灰著照按，被擋的那一句也要寫出來；選單上沒有也照按〔清單外〕）。"""
        opts = self.options(who)
        have = opts.get(option_id)
        emit(f"{who} {tag} 按 {option_id}", None if have is None else {"label": have.get("label"), "enabled": have.get("enabled")})
        self.choose(who, option_id)

    def menu(self, who: str, tag: str, *prefixes: str) -> None:
        """選單上這幾種開頭的選項（id、字、灰不灰）。"""
        opts = self.options(who)
        emit(f"{who} {tag} 選單上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(prefixes)])

    # ── 前半 ──

    def seat(self) -> None:
        """挑一處兩軍都有人物的地點（此刻誰在哪看存檔：時刻表的季波才先在常社，其他季皇甫嵩在）：黃巾的人在那裡挑官軍的人物、官軍的人挑黃巾的人物，
        官軍的人在那裡護衛、犒軍；探望的人站官軍的報到處，退場等著回來的是另一位官軍人物；盤算的人之後再站過去。"""
        from tianxia import figures

        g = self.game(self.VIEWER)
        c = self.c
        best = None
        for loc in sorted(c.locations):
            ids = figures.present_at(g.state, c, loc)
            guan = [f for f in ids if c.figures[f].faction == "guan" and figures.can_challenge(g.state, c, f)]
            huang = [f for f in ids if c.figures[f].faction == "huang" and figures.can_challenge(g.state, c, f)]
            score = (bool(guan) + bool(huang), loc == self.GUAN_HALL)
            if (guan or huang) and (best is None or score > best[0]):
                best = (score, loc, guan, huang)
        if best is not None:
            _, self.hall, guan, huang = best
            self.foe = ("huangfusong" if "huangfusong" in guan else guan[0]) if guan else "nobody"
            self.bocai_side = huang[0] if huang else "nobody"
            self.friend = self.foe if self.foe != "nobody" else next((f for f in figures.present_at(g.state, c, self.hall) if c.figures[f].faction == "guan"), "nobody")
            self.fallen = next((f for f, d in c.figures.items() if d.faction == "guan" and f != self.friend), "nobody")
        emit("挑的地點與人物", {"hall": self.hall, "foe": self.foe, "bocai_side": self.bocai_side, "friend": self.friend, "fallen": self.fallen})
        for who, side in self.PLAYERS.items():
            if who == self.VISITOR:
                self.place(who, self.base_of("guan") or self.hall, side)
            else:
                self.place(who, self.hall, side)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        emit("大勢人物表", {"on": self.on(), "aid": self.c.config.figure_aid.enabled, "plans": self.c.config.plans.enabled,
                           "yuedan": self.c.config.figure_life.yuedan})
        self.world_view("開場")

    def yuedan_open(self) -> None:
        """快轉到第 2 週：月旦評跨進新的一週自然評一批（單子在、還沒寫）；前半就停在這個狀態。"""
        self.forward_to_week(2)
        for who in (self.VIEWER, self.STRANGER, self.HUANG_WIN):
            self.main(who)
        self.world_view("第 2 週")

    def challenge(self) -> None:
        """挑戰皇甫嵩：選單、勝算、打贏（掉落必中）、閉門不見、同一天再打贏、僵持、落敗、模型叫不動時打贏；官軍的人與散人看不到鈕。"""
        fid = self.foe
        for who in (self.HUANG_WIN, self.GUAN_PEER, self.FREE):
            self.main(who)
            self.menu(who, "挑戰之前", "act:challenge:")
            self.me(who, "挑戰之前")
        # 打贏
        MODEL["judge"] = True
        try:
            with self.fights("大勝"), self.drops():
                self.press(self.HUANG_WIN, f"act:challenge:{fid}", "打贏")
        finally:
            MODEL["judge"] = False
        self.me(self.HUANG_WIN, "打贏之後")
        self.world_view("打贏之後")
        self.menu(self.HUANG_WIN, "閉門不見", "act:challenge:")
        with self.fights("大勝"):
            self.press(self.HUANG_WIN, f"act:challenge:{fid}", "閉門不見硬按")
        # 閉門不見解了（擺成到了）再打贏：同一天聲威不再扣
        self.edit(self.HUANG_WIN, lambda p: p.snubbed_until.clear())
        with self.fights("險勝"), self.drops():
            self.press(self.HUANG_WIN, f"act:challenge:{fid}", "解了之後再贏")
        self.me(self.HUANG_WIN, "再贏之後")
        # 僵持、落敗
        with self.fights("僵持"):
            self.press(self.HUANG_WIN2, f"act:challenge:{fid}", "僵持")
        self.me(self.HUANG_WIN2, "僵持之後")
        with self.fights("落敗"):
            self.press(self.HUANG_DRAW, f"act:challenge:{fid}", "落敗")
        self.me(self.HUANG_DRAW, "落敗之後")
        # 模型叫不動（判讀走固定句）
        with self.fights("大勝"), self.drops():
            self.press(self.HUANG_LOSE, f"act:challenge:{fid}", "沒有判讀打贏")
        self.me(self.HUANG_LOSE, "沒有判讀打贏之後")
        # 官軍的人挑黃巾的人物（含打贏之後的敗走，另一個方向）
        with self.fights("大勝"), self.drops():
            self.press(self.GUAN_PEER, f"act:challenge:{self.bocai_side}", "官軍打贏黃巾的人物")
        self.me(self.GUAN_PEER, "官軍打贏之後")
        # 清單外：不在這裡的人物、沒有的人物
        self.choose(self.HUANG_LOSE, f"act:challenge:{self.bocai_side}")  # 同陣營的人物：打不得
        self.choose(self.HUANG_LOSE, "act:challenge:nobody")
        self.world_view("挑戰之後")

    def guarded(self) -> None:
        """護衛：葛望之護衛皇甫嵩（再按一次是灰的）；黃巾的人看不到護衛鈕；紀長庚來挑戰，護衛擋下或闖過；下線時替人物擋下的挑戰，回來同步補名望與心得。"""
        fid = self.friend
        self.main(self.GUARD)
        self.menu(self.GUARD, "護衛之前", "aid:")
        self.press(self.GUARD, f"aid:guard:{fid}", "護衛")
        self.menu(self.GUARD, "護衛之後", "aid:")
        self.press(self.GUARD, f"aid:guard:{fid}", "再護衛一次")
        self.me(self.GUARD, "護衛之後")
        def harden(s) -> None:
            for post in s.figure_guards:
                post.power = 1.0e9

        self.edit_world(harden)  # 護衛的身手壓到最高：第一個來的過不去
        self.menu(self.HUANG_DEAD, "黃巾的人", "aid:", "act:challenge:")
        with self.fights("大勝"):
            self.press(self.HUANG_DEAD, f"act:challenge:{fid}", "被護衛擋")
        self.me(self.HUANG_DEAD, "被護衛擋之後")
        def weaken(s) -> None:
            for post in s.figure_guards:
                post.power = 1.0

        self.edit_world(weaken)  # 護衛的身手壓到最低：下一個來的闖得過去（那一班散、打到他本人）
        with self.fights("大勝"):
            self.press(self.HUANG_WIN2, f"act:challenge:{fid}", "闖護衛")
        self.me(self.HUANG_WIN2, "闖護衛之後")
        self.world_view("護衛之後")
        self.main(self.GUARD)  # 回來同步：補名望、心得
        self.me(self.GUARD, "回來同步")
        # 清單外的 aid:
        for bad in ("aid:guard:nobody", "aid:guard:", f"aid:wave:{fid}", f"aid:rally:{self.bocai_side}"):
            self.choose(self.GUARD, bad)

    def rally_visit(self) -> None:
        """犒軍（聲威被打掉了才有；扣體力、銀兩，補到一天的上限）、同一天再犒；探望（官軍報到處，退場等著回來的朱儁；一天一次）。"""
        fid = self.friend
        self.menu(self.RALLIER, "犒軍之前", "aid:")
        self.press(self.RALLIER, f"aid:rally:{fid}", "犒軍")
        self.press(self.RALLIER, f"aid:rally:{fid}", "再犒一次")
        self.me(self.RALLIER, "犒軍之後")
        self.world_view("犒軍之後")
        # 朱儁退場等著回來
        from tianxia.state import FigureState

        def fall(s) -> None:
            if self.fallen in self.c.figures:
                fs = s.figures.get(self.fallen) or FigureState(prestige=0)
                fs.prestige, fs.status, fs.front, fs.location = 0, "retired", None, ""
                fs.back_at, fs.back_front = s.time + 100 * 3600, "yingru"
                s.figures[self.fallen] = fs

        self.edit_world(fall)
        self.main(self.VISITOR)
        self.menu(self.VISITOR, "探望之前", "aid:")
        self.press(self.VISITOR, f"aid:visit:{self.fallen}", "探望")
        self.press(self.VISITOR, f"aid:visit:{self.fallen}", "再探望一次")
        self.press(self.VISITOR, "aid:visit:nobody", "探望沒有的人")
        self.me(self.VISITOR, "探望之後")
        self.world_view("探望之後")

    def plan_open(self) -> None:
        """第 2 週這一刻自然開著的一件盤算（內容的行程到了公告的時候；沒有就擺一件）：站對邊的人助他一臂、站錯邊的人按助他一臂被擋、散人壞他的事、重複、
        插過手又按另一顆、不在那裡、沒有這一件；**前半停在助他一臂還沒結**（到點還要一陣子）。"""
        from tianxia.state import Plan

        s = self.world.get_season()
        pair = None
        for plan in s.plans:
            found = next(((it, st) for it in self.c.itineraries for st in it.stops if st.id == plan.stop and st.contest), None)
            if not plan.settled and found is not None and plan.place in self.c.locations:
                pair, self.plan_stop, self.plan_who, self.plan_place = found, plan.stop, plan.who, plan.place
                break
        if pair is None:
            pair = next(((it, st) for it in self.c.itineraries for st in it.stops if st.contest and st.place in self.c.locations), None)
            if pair is None:
                emit("這份內容沒有盤算", None)
                return
            self.plan_who, self.plan_stop, self.plan_place = pair[0].who, pair[1].id, pair[1].place

            def seed(w) -> None:
                w.plans = [x for x in w.plans if x.stop != self.plan_stop]
                w.plans.append(Plan(stop=self.plan_stop, who=self.plan_who, place=self.plan_place, open_at=w.time, due=w.time + 12 * 3600))

            self.edit_world(seed)
        side = pair[1].contest.side
        emit("盤算", {"stop": self.plan_stop, "who": self.plan_who, "place": self.plan_place, "side": side})
        ally, wrong = (self.HELPER, self.BLOCKER) if side == "guan" else (self.BLOCKER, self.HELPER)
        for who in (ally, wrong, self.FREE):
            self.place(who, self.plan_place)
        for who in (ally, wrong, self.FREE):
            self.main(who)
            self.menu(who, "盤算之前", "plan:")
        stop = self.plan_stop
        self.press(ally, f"plan:help:{stop}", "助他一臂")
        self.press(ally, f"plan:help:{stop}", "助他一臂（重複）")
        self.press(ally, f"plan:block:{stop}", "壞他的事（插過手了）")
        self.press(wrong, f"plan:help:{stop}", "站錯邊助他一臂")
        self.press(self.FREE, f"plan:block:{stop}", "散人壞他的事")
        self.choose(self.FREE, "plan:help:nobody")
        self.place(self.GUARD, self.hall)
        self.choose(self.GUARD, f"plan:help:{stop}")  # 不在那裡
        for who in (ally, wrong, self.FREE):
            self.menu(who, "盤算之後", "plan:")
            self.me(who, "盤算之後")
        self.world_view("盤算還沒結")

    PICKS = ("hall", "foe", "bocai_side", "friend", "fallen", "plan_stop", "plan_who", "plan_place")

    def half(self) -> None:
        for who in [*self.PLAYERS, ADMIN]:
            self.me(who, "前半停在這裡")
        self.world_view("前半停在這裡")
        Path(str(self.db) + ".figact.json").write_text(json.dumps({k: getattr(self, k) for k in self.PICKS}, ensure_ascii=False), encoding="utf-8")

    # ── 後半 ──

    def resume(self) -> None:
        for k, v in json.loads(Path(str(self.db) + ".figact.json").read_text(encoding="utf-8")).items():  # 前半挑的地點與人物（後半是新的行程）
            setattr(self, k, v)
        self.login_all()

    def plan_settle(self) -> None:
        """快轉過了到點：盤算結算，助他一臂與壞他的事的人下一次同步收到結果（紀錄、情誼）。"""
        for _ in range(10):  # 快轉到這一件盤算結算為止（十二小時一跳）
            plan = next((x for x in self.world.get_season().plans if x.stop == self.plan_stop), None)
            if plan is None or plan.settled:
                break
            self.do(ADMIN, "fast_forward", {"hours": 12})
        self.world_view("盤算到點之後")
        for who in (self.HELPER, self.BLOCKER, self.FREE):
            self.main(who)
            self.me(who, "盤算結算之後")

    def yuedan_pending(self) -> list[str]:
        return [e.name for e in self.world.get_season().yuedan if not e.published]

    def seed_batch(self, names: list[str]) -> None:
        """擺一批還沒寫的月旦評（跟 tick 自己評的一樣：固定句、還沒寫、還沒發）。"""
        from tianxia import yuedan
        from tianxia.state import YuedanEntry

        def seed(s) -> None:
            week = max(self.week_of(), 1)
            for n in names:
                s.yuedan.append(YuedanEntry(week=week, name=n, board="名人", fact="名望 9", line=yuedan.fixed_line("名人", n), at=s.time))

        self.edit_world(seed)

    def yuedan_on(self) -> None:
        """月旦評的 A、B、C：前半留下的那一批在模型叫不動時發（固定句）；擺一批在模型回了時發（一句寫太短退回固定句）；擺一批等太久照固定句發；
        沒有單子的時候叫一次；玩家卡上的評語。"""
        emit("等著發的", self.yuedan_pending())
        MODEL["yuedan"] = None
        emit("模型叫不動 yuedan_once", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
        emit("等著發的（發完）", self.yuedan_pending())
        self.world_view("模型叫不動發完")
        emit("沒有單子 yuedan_once", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
        for mode in ("mixed", "all"):
            self.seed_batch([self.STRANGER, self.VIEWER, self.HUANG_WIN])
            MODEL["yuedan"] = mode
            try:
                emit(f"模型回了 yuedan_once {mode}", self.server.yuedan_once(self.server.game_for(self.VIEWER)))
            finally:
                MODEL["yuedan"] = None
            self.world_view(f"模型回了發完 {mode}")
        self.seed_batch([self.STRANGER, self.HELPER])
        with self.tuned(self.c.config.figure_life, yuedan_wait_seconds=0.0):
            self.main(self.VIEWER)
            self.do(ADMIN, "fast_forward", {"hours": 1})
        self.world_view("等太久發完")
        for who in (self.VIEWER, self.STRANGER):
            self.main(who)
        emit("玩家卡", self.call(self.VIEWER, "GET", f"/api/peer?name={self.STRANGER}")[1])

    def admin(self) -> None:
        """管理者救回人物：叫回選單（朱儁退場等著）、救回、沒退場的、不是管理者、沒有這個人。"""
        view = self.call(ADMIN, "GET", "/api/admin")[1]
        emit("叫回人物選單", view.get("fallen") if isinstance(view, dict) else view)
        self.do(self.HELPER, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": self.fallen})
        self.do(ADMIN, "revive_figure", {"id": "nobody"})
        self.do(ADMIN, "revive_figure", {})
        view = self.call(ADMIN, "GET", "/api/admin")[1]
        emit("叫回人物選單（救回之後）", view.get("fallen") if isinstance(view, dict) else view)
        self.world_view("救回之後")
        self.main(self.VISITOR)
        self.menu(self.VISITOR, "救回之後", "aid:")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在常社、體力滿）若干輪；直接問 bot_policy.score 對 aid:、plan: 各幾分；體力花不完時 _stamina_play 挑到什麼（機會調成必挑）；
        整季機器人在常社的選單挑哪一顆（aid:、act:challenge: 都不按）。"""
        from collections import Counter

        from tianxia import bot, bot_policy, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        spot = self.hall if self.hall in self.c.locations else sorted(self.c.locations)[0]
        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if "guan" in sides else None, season_number=self.world.get_season_number())
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
            p.stats["silver"] = 300
            self.chars.save(g.state)
        for name in self.BOT_SEATS[:1]:
            self.begin()
            g = Game(self.c, self.chars.load(name), world=self.world)
            g.state.world = self.world.get_season()
            g.sync(CLOCK[0])
            profile = g.state.player.bot
            rows = [[o.id, o.enabled, bot_policy.score(g, o, profile)] for o in g.options(odds=False, tick=False) if o.id.startswith(("aid:", "plan:", "act:challenge:"))]
            emit(f"假人 {name} 問 score", rows)
            before = bot_policy.PLAY_CHANCE
            bot_policy.PLAY_CHANCE = 2.0
            try:
                emit(f"假人 {name} _stamina_play", bot_policy._stamina_play(g, random.Random(5)))
            finally:
                bot_policy.PLAY_CHANCE = before
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_FIGACT_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("人假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"人假人 {name}", {"loc": p.location, "stamina": p.stamina, "silver": p.stats.get("silver", 0),
                                    "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                    "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "人丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.faction, p.location, p.journey = "guan" if "guan" in sides else None, spot, None
        p.visited.add(spot)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))

    def season(self) -> None:
        """收季、開下一季：護衛的崗、犒軍探望的帳、盤算、月旦評、人物的聲威與打贏幾次都隨季換掉。"""
        self.do(ADMIN, "end_season")
        self.main(self.HUANG_WIN)
        self.do(ADMIN, "next_season")
        self.world_view("換季之後")
        for who in (self.HUANG_WIN, self.GUARD, self.VISITOR, self.HELPER):
            self.main(who)
            self.me(who, "換季之後")
            self.menu(who, "換季之後", "aid:", "plan:", "act:challenge:")


# 改一個字（selftest）：月旦評發出去那一則的開頭（搬之前在 tianxia/yuedan.py、之後在 tianxia/features/figure_acts/yuedan.py）
register_track("figact", FigActScenario, (("tianxia/features/figure_acts/yuedan.py", "tianxia/yuedan.py"),
                                          ('HEAD = "{critic}月旦評（{week}）："', 'HEAD = "{critic}月旦評！（{week}）："')), "week7")
