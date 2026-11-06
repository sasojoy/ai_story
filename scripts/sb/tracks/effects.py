"""same_behavior 一軌一檔：effects（這一檔登記 effects）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ effects：效果與叛投一軌（全部拆包第 32 批，dev/core-effects-1） ═══════════════════════════
# 效果與叛投掛鉤（核心批）：rules.apply_effect 照效果欄位分派給主人（晉升、帶兵、招同伴、伏筆、碎片、屯糧、四勝利記帳，還有一條線的一步），
# 叛投那一刻各包清自己的進度（計畫 docs/superpowers/plans/2026-11-06-效果與叛投掛鉤-第32批.md）。角色的名字都是原創的（PM 11/04）。
# 對照用的事件（FX_PREFIX 開頭）只加進這一個子行程手上的內容（actions 是空的：探索抽不到，只擺到眼前），效果的值照內容裡第一則寫了那個欄位的
# 事件抄（沒有的照 fallback 補），base 與 head 加的一模一樣；只打公開的 API 按下去。

FX_PREFIX = "sbfx_"
FX_SKIP = ("next_event", "contribution")  # apply_effect 不讀的兩個欄位（串接是事件檢定的事；contribution 只准寫在隨口應對的分岔上）


class EffectsScenario(Scenario):
    """效果與叛投一軌（全部拆包第 32 批；--track effects，自己一個資料庫）。
    一則一種（single）：照 apply_effect 的分派順序，每一種主人在別處的欄位各擺一則事件到眼前按下去——靠山、捐糧（四勝利記帳）、伏筆片段、符文殘片、
    一般伏筆、召見往下一段、晉升、部下、結識同伴、伏筆物品與計數、玉璽碎片（舊鏈的世界旗標）、一條線的一步；按之前擺好那一種要的（糧草、召見、線的進度）。
    一則好幾種（combined）：內容裡每一個欄位抄一個值併成一則（next_event、contribution 除外），官軍、黃巾、散人各按一次（同一則效果帶好幾個欄位時，
    回話的先後、世界旗標與存檔寫入的先後都看得出來）。
    叛投（defect_full）：官軍的人手上擺滿會被清的進度（押著的糧車〔護糧軍令〕、階與召見與第 4 階資格與「只缺一個機會」、部下與傳功、貢獻與每週貢獻、
    豪強兩本帳、捐獻、舊陣營引薦人排著的提示〔師父的一條不動〕、機緣與靠山、響應的集體密謀、第四階席次與帳、揭著的舊陣營懸賞、寫了 side 的同伴、
    欠著人物的請託〔NPC 智能〕），在黃巾的投靠點按叛投、確定。
    **前半停在兩件寫到一半的事**：一則好幾種的事件卡擺在眼前還沒按（效果還沒套）、另一個人按了叛投還在確認畫面上（先按、還沒確定）。
    後半：新程式接著按那一張卡、按「確定叛投」；假人（BotRunner 兩個眼前擺著那一則好幾種的卡、整季機器人眼前的選單與挑法：叛投那幾顆照排除）；收季、開下一季。
    沒有陣營、沒有那些內容的（測試內容）同一串 API 照打，寫「沒有」。"""

    G1, H1, G2, H2, LONE, WAIT = "岑望川", "鍾雨樵", "裴映川", "藺秋原", "閔遠帆", "盧聽濤"
    DF1, DF2, LEAD = "殷照野", "談秋聲", "范清和"
    PLAYERS = {G1: "guan", H1: "huang", G2: "guan", H2: "huang", LONE: None, WAIT: "guan", DF1: "guan", DF2: "guan", LEAD: "guan"}
    BOT_SEATS = ["效甲", "效乙"]
    PHASES_FIRST = ["setup", "seat", "single", "combined", "defect_full", "half"]
    PHASES_SECOND = ["resume", "answer", "confirm", "bots", "season"]
    # 一則一種：（格, 抄哪幾個欄位, 誰按）；照 apply_effect 的先後排（計畫第一節 1.2）
    SINGLES = (
        ("patron", ("patron",), "G1"),
        ("grain", ("donate_grain",), "H1"),
        ("fs_fragments", ("fs_fragments",), "H1"),
        ("runic", ("runic",), "H1"),
        ("event_mods", ("event_mods",), "G1"),
        ("summons_next", ("summons_next",), "G1"),
        ("promote", ("promote",), "G1"),
        ("followers", ("followers",), "G1"),
        ("recruit", ("recruit",), "G1"),
        ("foreshadow", ("clue_items", "fs_counters"), "H1"),
        ("shard", ("world_flags_add",), "G1"),
        ("story", ("story",), "G1"),
    )

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.singles = {slot: self.single_effect(slot, fields) for slot, fields, _who in self.SINGLES}
        self.combo = self.combined_effect()
        self.inject()

    # ── 對照用的事件（每個子行程照內容算一次：前半、後半兩個行程算出來的一樣） ──

    def hub(self) -> str:
        return self.c.scenario.start_location

    def sample(self, field: str):
        """內容裡第一則（照事件 id、選項、先成後敗）寫了這個欄位的效果的值；沒有是 None。"""
        import copy

        for eid in sorted(self.c.events):
            if eid.startswith(FX_PREFIX):
                continue
            for ch in self.c.events[eid].choices:
                for eff in (ch.effect, ch.fail_effect):
                    value = getattr(eff, field)
                    if value:
                        return copy.deepcopy(value)
        return None

    def fallback(self, field: str):
        """內容裡沒有人寫的欄位補一個（正式內容沒有結識同伴的事件；測試內容沒有晉升、伏筆那幾種）。補不出來是 None。"""
        c = self.c
        if field == "patron":
            return "cao"
        if field == "promote":
            return 2
        if field == "runic":
            return 2
        if field == "followers":
            return [sorted(c.followers)[0]] if c.followers else None
        if field == "donate_grain":
            return {self.hub(): 3}
        if field == "insights":  # 正式內容沒有事件給意境：第一個地點探索悟得到的基本意境
            got = next((i for loc in sorted(c.locations) for i in c.locations[loc].insights), None)
            return [got] if got else None
        if field == "gear":  # 正式內容沒有事件給寶物：掉落池的第一件，沒有就一匹良駒
            return next((tid for tid, t in sorted(c.gear.treasures.items()) if getattr(t, "pool", True)), "good_horse")
        if field == "fs_counters":  # 伏筆的隱藏計數（官銀）
            return {"guanyin": 1}
        if field == "recruit":
            free = [cid for cid in sorted(c.characters) if c.characters[cid].kind is not None and c.characters[cid].side in (None, "guan")]
            return free[0] if free else None
        return None

    def single_effect(self, slot: str, fields: tuple[str, ...]) -> dict | None:
        if slot == "shard":  # 舊鏈的玉璽碎片：劇本的碎片旗標（沒寫就換一個對照用的旗標，照樣是「這一下新立的世界旗標」）
            return {"world_flags_add": [self.c.scenario.jade_seal_flag or f"{FX_PREFIX}flag"], "chronicle": "{name}在對照的路上拾得一物。"}
        if slot == "story":  # 一條線的一步：挑一步有紀念物的（「收進行囊」那一句才看得出這一格在回話裡的先後）；沒有就照 sample
            import copy

            steps = [eff.story for eid in sorted(self.c.events) if not eid.startswith(FX_PREFIX) for ch in self.c.events[eid].choices
                     for eff in (ch.effect, ch.fail_effect) if eff.story is not None]
            kept = next((s for s in steps if s.keepsake), None)
            if kept is not None:
                return {"story": copy.deepcopy(kept)}
        out = {}
        for f in fields:
            value = self.sample(f)
            value = self.fallback(f) if value is None else value
            if value is not None:
                out[f] = value
        return out or None

    def combined_effect(self) -> dict:
        """每一個欄位抄一個值（next_event、contribution 除外）；七種主人在別處的照一則一種那一份補齊。"""
        from tianxia.models import Effect

        out = {}
        for f in Effect.model_fields:
            if f in FX_SKIP:
                continue
            value = self.sample(f)
            value = self.fallback(f) if value is None else value
            if value is not None:
                out[f] = value
        for kw in self.singles.values():
            for f, value in (kw or {}).items():
                out.setdefault(f, value)
        if (self.singles.get("story") or {}).get("story") is not None:  # 一條線那一步用有紀念物的那一步（回話裡排最後的那一句）
            out["story"] = self.singles["story"]["story"]
        flag = self.c.scenario.jade_seal_flag
        if flag and flag not in out.get("world_flags_add", []):
            out["world_flags_add"] = [*out.get("world_flags_add", []), flag]
        return out

    def inject(self) -> None:
        from tianxia.models import Choice, Effect, Event

        def event(eid: str, kw: dict) -> Event:
            return Event(id=eid, title=f"對照・{eid.removeprefix(FX_PREFIX)}", text="（對照用的事件：只擺到眼前）", actions=[],
                         choices=[Choice(text="照辦", effect=Effect(**kw))])

        for slot, kw in self.singles.items():
            if kw is not None:
                self.c.events[f"{FX_PREFIX}{slot}"] = event(f"{FX_PREFIX}{slot}", kw)
        self.c.events[f"{FX_PREFIX}all"] = event(f"{FX_PREFIX}all", self.combo)

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    def factions_on(self) -> bool:
        return any(f.id == "huang" for f in self.c.scenario.factions) and any(f.id == "guan" for f in self.c.scenario.factions)

    def grain(self, who: str, n: int) -> None:
        """背包裡放 n 份糧草（慢屬性的素材，每一種都放：捐糧照 foreshadow.spend_grain 從哪一種扣都看得出來）。"""
        mats = sorted(m.id for m in self.c.materials.values() if m.attribute == "慢")
        self.edit(who, lambda p: p.materials.update({m: n for m in mats}))

    def prep(self, who: str, kw: dict) -> None:
        """按之前擺好這一則要的：糧草（捐糧）、還沒去的第 3 階召見（召見往下一段；陣營的人）、那一條線還沒收的進度（一條線的一步）。"""
        from tianxia.state import StoryProgress, Summons

        if kw.get("donate_grain"):
            self.grain(who, 40)
        if kw.get("summons_next") and self.PLAYERS.get(who):
            self.edit(who, lambda p: setattr(p, "summons", Summons(rank=3, location=self.hub())))
        step = kw.get("story")
        if step is not None and step.line:
            self.edit(who, lambda p: p.storylines.setdefault(step.line, StoryProgress(line=step.line, stage=f"{FX_PREFIX}stage")))

    @contextlib.contextmanager
    def old_shard(self, on: bool):
        """舊鏈的玉璽碎片那一下：玉璽碎片關著（開著的話舊鏈不寫跨季紀錄，三種設定都看不到這一格）、劇本有碎片旗標（測試內容沒寫就用對照用的那一個）；
        出來還原。"""
        if not on:
            yield
            return
        seal, scen = self.c.config.seal, self.c.scenario
        before = (seal.enabled, scen.jade_seal_flag)
        seal.enabled, scen.jade_seal_flag = False, scen.jade_seal_flag or f"{FX_PREFIX}flag"
        emit("舊鏈的玉璽碎片這一下", {"seal_enabled_before": before[0], "flag": scen.jade_seal_flag})
        try:
            yield
        finally:
            seal.enabled, scen.jade_seal_flag = before

    def card(self, who: str, eid: str) -> bool:
        if eid not in self.c.events:
            emit(f"{who}：這份內容沒有 {eid}", None)
            return False
        self.edit_state(who, lambda s: setattr(s, "pending_event", eid))
        return True

    def press_card(self, who: str, tag: str) -> None:
        opts = self.ids(self.main(who))
        emit(f"{who} {tag} 卡上", [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith("choice:")])
        self.choose(who, "choice:0")

    def me(self, who: str, tag: str) -> None:
        """存檔裡效果與叛投碰得到的那幾格（主人在別處的都列；其餘看段落的資料庫雜湊）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player

        def dump(x):
            return None if x is None else x.model_dump(mode="json")

        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "ally": p.ally, "sect": p.sect, "defected": p.defected, "pending": [p.pending_defect, p.pending_ally],
            "rank": p.rank, "qualified": p.qualified, "hinted": list(p.rank_hinted), "stall": p.summons_stall, "summons": dump(p.summons),
            "followers": list(p.followers), "drill": [dump(d) for d in p.follower_drill], "patron": p.patron, "contrib": p.contrib,
            "weeks": dict(sorted(p.contrib_weeks.items())), "ledgers": dict(sorted(p.ledgers.items())), "lean": p.lean_changed,
            "donations": dict(sorted(p.donations.items())), "convoy": dump(p.convoy), "runic": p.runic_pieces,
            "fragments": {k: list(v) for k, v in sorted(p.fragments.items())}, "clues": dict(sorted(p.clue_items.items())),
            "counters": dict(sorted(p.fs_counters.items())), "hints": [[n.id, n.by] for n in p.hint_queue],
            "opp": [list(p.opp_done), dict(sorted(p.opp_counts.items())), dict(sorted(p.opp_items.items())), list(p.opp_clues)],
            "stories": {k: [v.stage, dict(sorted(v.marks.items())), v.go, v.ending] for k, v in sorted(p.storylines.items())},
            "keepsakes": list(p.keepsakes), "flags": sorted(p.flags), "stats": dict(sorted(p.stats.items())),
            "affinity": dict(sorted(p.affinities.items())), "materials": dict(sorted(p.materials.items())),
            "debts": sorted(p.parley_debts), "pending_event": state.pending_event,
            "journal": [[e.title, e.tag, list(e.lines)[:6]] for e in state.journal[:3]]})

    def world_view(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"世界 {tag}", {
            "flags": sorted(w.flags), "event_mods": dict(sorted(w.event_mods.items())),
            "plots": [[x.id, x.faction, x.status, list(x.members), dict(sorted(x.parts.items()))] for x in w.plots],
            "bounties": [[b.id, b.faction, list(b.takers)] for b in w.bounties if b.id.startswith(FX_PREFIX)],
            "seats": {k: list(v) for k, v in sorted(w.seats.items())},
            "ledger": {k: {n: dict(sorted(x.items())) for n, x in sorted(v.items())} for k, v in sorted(w.seat_ledger.items())},
            "pushers": {k: sorted(v) for k, v in sorted(w.active_pushers.items())},
            "jade": [[f.number, f.finder, f.text] for f in self.world.get_jade_seal_fragments()],
            "rumors": [r.text for r in w.rumors][-8:], "chronicle": [r.text for r in w.chronicle][-4:]})

    # ── 前半 ──

    def setup(self) -> None:
        super().setup()
        emit("對照用的事件", {eid: self.c.events[eid].choices[0].effect.model_dump(mode="json", exclude_defaults=True)
                              for eid in sorted(self.c.events) if eid.startswith(FX_PREFIX)})

    def seat(self) -> None:
        on = self.factions_on()
        for who, side in self.PLAYERS.items():
            self.place(who, self.hub(), side if on else None)
            self.edit(who, lambda p: p.stats.update({"silver": 500}))
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("坐定")

    def single(self) -> None:
        """一則一種：照 apply_effect 的先後，一種一則按下去（同一個人接連按，前一則留下的會被下一則讀到：召見往下一段之後才晉升）。"""
        for slot, _fields, who_key in self.SINGLES:
            who = getattr(self, who_key)
            kw = self.singles[slot]
            if kw is None:
                emit(f"一則一種 {slot}：這份內容沒有", None)
                continue
            self.prep(who, kw)
            if self.card(who, f"{FX_PREFIX}{slot}"):
                with self.old_shard(slot == "shard"):
                    self.press_card(who, f"一則一種 {slot}")
                self.me(who, f"一則一種 {slot} 之後")
        self.world_view("一則一種之後")

    def combined(self) -> None:
        """一則好幾種：官軍、黃巾、散人各按一次。"""
        for who in (self.G2, self.H2, self.LONE):
            self.prep(who, self.combo)
            if self.card(who, f"{FX_PREFIX}all"):
                self.press_card(who, "一則好幾種")
                self.me(who, "一則好幾種之後")
        self.world_view("一則好幾種之後")

    def stage_defector(self, who: str, n: int) -> None:
        """叛投之前手上擺滿會被清的進度（n 讓兩個人擺的數不一樣）；全服那一側：響應的密謀、席次與帳、揭著的懸賞、寫了 side 的同伴。"""
        from tianxia import roster
        from tianxia.state import Bounty, Convoy, FollowerDrill, HintNote, ParleyDebt, Plot, Summons

        c, side = self.c, "guan"
        now = self.world.get_season().time
        far = now + 30 * 86400.0
        follower = sorted(c.followers)[0] if c.followers else None
        opp = c.opportunities[0].id if c.opportunities else f"{FX_PREFIX}opp"
        debtor = sorted(c.characters)[0] if c.characters else None
        trek = sorted(i for i in c.locations if i != self.hub())

        def fn(p) -> None:
            p.rank, p.qualified, p.rank_hinted, p.summons_stall = 3, True, [3], "（對照）沒有人能引見"
            p.summons = Summons(rank=4, location=self.hub())
            p.followers = [follower] * n if follower else []
            p.follower_drill = [FollowerDrill(cheng=n, arm=1)] if follower else []
            p.contrib, p.contrib_weeks = 5 + n, {1: 2, 2: 3 + n}
            p.ledgers, p.lean_changed = {"guan": 4, "huang": n}, 1
            p.donations = {f"{self.hub()}:糧草": 6 + n}
            p.convoy = Convoy(order=f"{FX_PREFIX}escort", grain=4 + n, from_loc=self.hub(), to_loc=trek[0] if trek else self.hub())
            p.hint_queue = [HintNote(id=f"{FX_PREFIX}old", speaker="（對照）引薦人", text="（對照）舊陣營排著的話。", by=side),
                            HintNote(id=f"{FX_PREFIX}mentor", speaker="（對照）師父", text="（對照）師父排著的話。")]
            p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts = [opp], {opp: n}, {opp: "（對照）信物"}, {opp: "front"}
            p.opp_tried, p.opp_pieces, p.opp_clues, p.patron = {opp: 1}, {opp: ["a"]}, [opp], "cao"
            p.runic_pieces, p.fragments = 2, {f"{FX_PREFIX}chain": [0]}
            if debtor is not None:
                p.parley_debts = {debtor: ParleyDebt(kind="plea", condition="silver", due=far)}

        self.edit(who, fn)

        def world_fn(s) -> None:
            s.plots.append(Plot(id=9900 + n, opp=opp, faction=side, leader=self.LEAD, shown=self.LEAD, members=[self.LEAD, who],
                                parts={"a": who, "b": self.LEAD}, deadline=far))
            s.seats.setdefault(side, []).append(who)
            s.seat_ledger.setdefault(side, {})[who] = {1: 3 + n}
            s.bounties.append(Bounty(id=f"{FX_PREFIX}{n}", kind="scout", faction=side, week=1, expires=far, silver=10, deeds=1, quota=2,
                                     location=self.hub(), takers=[who]))

        self.world.mutate_season(world_fn)
        mate = next((cid for cid in sorted(c.characters) if c.characters[cid].side == side and roster.owned_by(self.world, cid) is None), None)
        emit(f"{who} 名下寫了 side 的同伴", [mate, mate is not None and self.world.try_recruit(mate, who, cap=3)])

    def to_target(self, who: str) -> str | None:
        target = next((f for f in self.c.scenario.factions if f.id == "huang" and f.join_at), None)
        if target is None:
            return None
        self.place(who, target.join_at[0])
        ids = [i for i in self.ids(self.main(who)) if i.startswith("defect:")]
        emit(f"{who} 叛投那幾顆", ids)
        return "defect:huang" if "defect:huang" in ids else (ids[0] if ids else None)

    def defect_full(self) -> None:
        """官軍的人手上擺滿會被清的進度，在黃巾的投靠點按叛投、確定。"""
        if not self.factions_on():
            emit("叛投：這份內容沒有兩軍", None)
            return
        self.stage_defector(self.DF1, 1)
        self.me(self.DF1, "叛投之前")
        self.world_view("叛投之前")
        oid = self.to_target(self.DF1)
        if oid is not None:
            self.choose(self.DF1, oid)
            self.choose(self.DF1, "defect:confirm")
        self.me(self.DF1, "叛投之後")
        self.world_view("叛投之後")

    def half(self) -> None:
        """前半停在兩件寫到一半的事：一則好幾種的事件卡擺在盧聽濤眼前還沒按；談秋聲按了叛投、停在確認畫面上。"""
        self.prep(self.WAIT, self.combo)
        self.card(self.WAIT, f"{FX_PREFIX}all")
        self.me(self.WAIT, "前半停在這裡")
        if self.factions_on():
            self.stage_defector(self.DF2, 2)
            oid = self.to_target(self.DF2)
            if oid is not None:
                self.choose(self.DF2, oid)
            self.me(self.DF2, "前半停在這裡")
        self.world_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.WAIT, self.DF2, self.G1):
            self.main(who)

    def answer(self) -> None:
        """新程式接著按前半擺在眼前的那一張卡（效果在新程式這一下才套）。"""
        self.press_card(self.WAIT, "接手")
        self.me(self.WAIT, "接手之後")
        self.world_view("接手之後")

    def confirm(self) -> None:
        """新程式接著按「確定叛投」（前半按了叛投、確認畫面還開著）。"""
        if not self.factions_on():
            return
        emit(f"{self.DF2} 確認畫面上", sorted(self.ids(self.main(self.DF2))))
        self.choose(self.DF2, "defect:confirm")
        self.me(self.DF2, "確定之後")
        self.world_view("確定之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍，站在開局的地方，眼前擺著那一則好幾種的卡）若干輪；整季機器人站在黃巾的投靠點、眼前擺著那一張卡的選單與挑法
        （叛投那幾顆照排除；卡上有結識同伴的那一顆照 bot.pick 先挑）。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.stats["silver"] = 300
            g.state.pending_event = f"{FX_PREFIX}all"
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(31), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_EFFECTS_TICKS", "6"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "pending_event": s.pending_event,
                                  "card": [[e.title, list(e.lines)] for e in s.journal if e.title.startswith("對照")][:1],
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.world_view("假人之後")
        self.begin()
        solo = Game.new(self.c, "效丙", rng=random.Random(7), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        target = next((f for f in self.c.scenario.factions if f.id == "huang" and f.join_at), None)
        p.faction, p.location, p.journey = ("guan" if on else None), (target.join_at[0] if target is not None else self.hub()), None
        p.visited.add(p.location)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.stamina = float(self.c.config.stamina_max)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（投靠點）", [o.id for o in opts])
        emit("整季機器人挑的（投靠點）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        solo.state.pending_event = f"{FX_PREFIX}all"
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（卡上）", [o.id for o in opts])
        emit("整季機器人挑的（卡上）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(20)}))

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.world_view("收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.G1)
        self.me(self.G1, "換季之後")
        self.world_view("換季之後")


# 改一個字（selftest）：叛投之後新陣營那一則陣營軍情（defection.defect；第 35 批陣營成包時那一行搬進包，這裡要多寫包裡的檔）
register_track("effects", EffectsScenario, (("tianxia/defection.py", "tianxia/features/faction/defection.py"), ("投奔過來了。", "投奔過來了！")), "week7")
