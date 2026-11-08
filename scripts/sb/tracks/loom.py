"""same_behavior 一軌一檔：loom（這一檔登記 loom）。"""
from __future__ import annotations

from pathlib import Path

from sb.harness import emit, register_track
from sb.tracks.world import WorldScenario

# ═══════════════════════════ core_world2（全部拆包第 40 批「世界模型二」） ═══════════════════════════
# core_world2（全部拆包第 40 批；計畫 docs/superpowers/plans/2026-11-06-世界模型二-第40批.md 1.14、Task 1）：這一段整段是第 40 批加的——
# 情境 LoomScenario（--track loom，自己一個資料庫、自己切一半），最後一行登記。現有 37 軌走不到、或沒跨過切點的那幾下補在這裡
# （計畫 1.14：開工那一筆 37 軌 × 三種設定逐項量過，哪一軌走到哪一項在那張表）。


class LoomScenario(WorldScenario):
    """世界模型二一軌（全部拆包第 40 批；--track loom，自己一個資料庫）。世界一步、條件、伏筆與機緣讀的那一半、鐵匠鋪的單子：
    - 條件三種（story_marks、story_marks_max、clue_items）成立與不成立各一：正式內容沒有一則條件寫 clue_items、測試內容沒有一條線的事件，
      所以這一軌在記憶體裡替一則事件的前三個選項各掛一種（兩個行程各自掛：前半、後半各自載入內容）。蘇織雲帶著那條線的記號（一條收了的線）
      與伏筆物品、溫硯秋什麼都沒有；兩個人都把那一則事件擺成待選（pending_event），看選單上出現哪幾個選項——**前半停在兩個人都還擺著**，
      後半接手的那一份照它的讀法再畫一次選單，再把事件收掉。
    - 伏筆、機緣讀的那一半：蘇織雲手上擺伏筆物品、聽過第一條鏈的第一則片段、一則機緣線索：門下頁（/api/menxia 的 clue_items：held_items）
      與 /api/main 的見聞（rumor_layers：heard_texts、heard_clues）前半、後半各看一次。測試內容伏筆關著，照打寫空的。
    - 世界一步跨過切點：前半一次快轉進第 2 週（週初與每天的掛鉤跑到這一週的中間），切點那一下把一位大勢人物的聲威擺低三點（後半的自然回復經
      犒軍共用的一天上限補回來）、一位擺成退場、六個世界時之後回來（後半 figures.revive 寫回來那一句）、一位對話人物擺一場三十天之後
      才散的宴（後半人物行事先問他在不在擺宴）；後半一次快轉跨過下一個週一（週初與每天的掛鉤、人物行事、設宴、求援委託、盤算、月旦評），
      前後把每一位人物與宴席寫出來。
    - 鐵匠鋪的單子：切點那一下替岑鑄心擺一張指著內容沒有的素材的兵器單子、替范冶塵擺一張防具單子（兩個人站在城鎮、鐵匠鋪開著）；後半第一下
      先把防具這一欄關掉（武器照開，鐵匠鋪照開門），接手那一份讀檔就清掉兩張（_drop_stale_references：失效、那一欄關了），再把防具開回來。
      同步那一處（sync 中段）每一個請求都在讀檔清過之後才到，經 API 走不到（計畫 1.14）。
    - 假人：BotRunner 兩個若干輪、整季機器人眼前的選單（照 world 一軌）。
    沒有大勢人物、伏筆、城鎮的內容同一串 API 照打，寫「沒有」。"""

    WEAVER, PLAIN, SMITH_A, SMITH_B = "蘇織雲", "溫硯秋", "岑鑄心", "范冶塵"
    PLAYERS = {WEAVER: "guan", PLAIN: "huang", SMITH_A: "guan", SMITH_B: "huang"}
    BOT_SEATS = ["織甲", "織乙"]
    LINE, MARK, GONE = "loom", "織", "loom_gone"  # 那條收了的線、記號；內容裡沒有的素材 id
    PHASES_FIRST = ["setup", "seat", "days", "marks", "cond_first", "half"]
    PHASES_SECOND = ["smith_off", "resume", "cond_second", "smith_on", "weeks", "bots"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.item = self.c.foreshadows.items[0].id if self.c.foreshadows.items else "loom_clue"
        self.event_id = self._hang_conditions()

    def _hang_conditions(self) -> str | None:
        """記憶體裡替一則事件的前三個選項各掛一種條件（照 id 排第一則：至少三個選項、前三個沒有條件、檢定、打一場、俠寇，沒有隨口應對；
        沒有的話放寬成只看打一場與俠寇）。不寫進輸出（後半是新的行程：寫了前半＋後半就比整段多一行）。"""
        from tianxia.models import Condition

        key = f"{self.LINE}:{self.MARK}"

        def plain(ch, strict: bool) -> bool:
            return ch.combat is None and ch.needs is None and (not strict or (ch.condition == Condition() and ch.check is None))

        for strict in (True, False):  # 測試內容只有一則三個選項的事件（drunk：第一個有檢定、第三個有條件）：照寬的再挑一次，條件整個換掉
            for eid in sorted(self.c.events):
                ev = self.c.events[eid]
                if ev.free_text is None and len(ev.choices) >= 3 and all(plain(ch, strict) for ch in ev.choices[:3]):
                    ev.choices[0].condition = Condition(story_marks={key: 1})
                    ev.choices[1].condition = Condition(story_marks_max={key: 0})
                    ev.choices[2].condition = Condition(clue_items={self.item: 1})
                    return eid
        return None

    def _opp_clue(self) -> str | None:
        for o in self.c.opportunities:
            if o.kind == "timing":
                return o.id
            if o.kind == "deduce" and o.deduce.traits:
                return f"{o.id}:{o.deduce.traits[0].key}"
        return None

    def pend(self, who: str, event_id: str | None) -> None:
        """把待選的事件直接擺上（或收掉）：伺服器每次進鎖重讀。"""
        with self.world.action_lock():
            state = self.chars.load(who)
            state.pending_event = event_id
            self.chars.save(state)
        emit(f"{who} 待選的事件 → {event_id}", None)

    def reads(self, tag: str) -> None:
        """兩個人的選單與見聞（/api/main）、門下頁的伏筆物品（/api/menxia）。"""
        for who in (self.WEAVER, self.PLAIN):
            view = self.main(who)
            emit(f"{who} 選單 {tag}", sorted(self.ids(view)))
            self.call(who, "GET", "/api/menxia")

    def figure_view(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"人物 {tag}", {
            "figures": {fid: [st.prestige, st.status, st.front, st.location, st.back_at, st.back_front] for fid, st in sorted(w.figures.items())},
            "feasts": [[f.id, f.host, f.place, f.start, f.end, f.settled] for f in w.feasts],
            "aid_tally": dict(sorted(w.aid_tally.items())), "rumors": [r.text for r in w.rumors][-6:]})

    def drafts(self, tag: str) -> None:
        for who in (self.SMITH_A, self.SMITH_B):
            p = self.chars.load(who).player
            emit(f"{who} 單子 {tag}", {"loc": p.location, "picking": p.picking_smith,
                                       "draft": None if p.smith_draft is None else p.smith_draft.model_dump(mode="json")})

    # ── 前半 ──

    def days(self) -> None:
        """一次快轉跨過下一個週一、再進那一週的四成（週初與每天的掛鉤在同一個請求裡跑）。"""
        self.forward(self.hours_to(self.into_next_week(1)), "前半跨週")

    def marks(self) -> None:
        """蘇織雲帶著記號（一條收了的線）、伏筆物品、聽過的片段與機緣線索；溫硯秋什麼都沒有。"""
        from tianxia.state import StoryProgress

        chain = next((c for c in self.c.foreshadows.chains if c.fragments), None)
        clue = self._opp_clue()

        def fn(p) -> None:
            p.storylines[self.LINE] = StoryProgress(line=self.LINE, marks={self.MARK: 1}, ending="織成")
            p.clue_items[self.item] = 1
            if chain is not None:
                p.fragments[chain.id] = [0]
            if clue is not None:
                p.opp_clues.append(clue)
        self.edit(self.WEAVER, fn)
        emit("掛了條件的事件", {"event": self.event_id, "line": self.LINE, "mark": self.MARK, "item": self.item,
                                "chain": None if chain is None else chain.id, "clue": clue})
        self.reads("帶上之後")

    def cond_first(self) -> None:
        if self.event_id is None:
            emit("這份內容沒有能掛條件的事件：略過", None)
            return
        for who in (self.WEAVER, self.PLAIN):
            self.pend(who, self.event_id)
        self.reads("前半：事件擺著")

    def half(self) -> None:
        """**前半停在世界一步推到一半**：週初與每天的掛鉤跑到第 2 週的中間；兩個人還擺著那一則事件；一位人物聲威低、一位退場等著回來、一位
        對話人物擺著宴；兩張鐵匠鋪的單子（一張失效、一張防具）。擺完不再打這幾個人的 API（讀檔清單子要留給後半接手的那一份）。"""
        from tianxia import equipment
        from tianxia.features.smithy import smithing
        from tianxia.models import WEAPON_KINDS
        from tianxia.state import Feast, SmithDraft

        s = self.world.get_season()
        live = sorted(fid for fid, st in s.figures.items() if st.status == "active" and fid in self.c.figures)
        movers = sorted(cid for cid, ch in self.c.characters.items() if ch.deep_interaction and ch.follows is None)
        if len(live) >= 2:
            low, gone = live[0], live[1]
            back = s.time + 6 * 3600.0

            def fn(w) -> None:
                w.figures[low].prestige = max(1, self.c.figures[low].start_prestige - 3)
                out = w.figures[gone]
                out.back_front, out.front, out.status, out.back_at = out.front, None, "retired", back
            self.world.mutate_season(fn)
            emit("擺人物", {"low": low, "gone": gone, "back_at": back})
        else:
            emit("這份內容沒有大勢人物：略過", None)
        if movers:
            host = movers[0]

            def feast(w) -> None:
                w.feast_seq += 1
                w.feasts.append(Feast(id=w.feast_seq, host=host, place=self.hub(), start=w.time, end=w.time + 30 * 86400.0))
            self.world.mutate_season(feast)
            emit("擺宴（對話人物留在原地）", host)
        else:
            emit("這份內容沒有對話人物：略過", None)
        town = next((i for i in sorted(self.c.locations) if equipment.TOWN_TAG in (self.c.locations[i].tags or [])), None)
        if town is None:
            emit("這份內容沒有城鎮：鐵匠鋪那一段略過", None)
        else:
            def stale(p) -> None:
                p.location, p.journey, p.picking_smith = town, None, True
                p.smith_draft = SmithDraft(kind=WEAPON_KINDS[0], main=self.GONE)

            def armor(p) -> None:
                p.location, p.journey, p.picking_smith = town, None, True
                p.smith_draft = SmithDraft(kind=smithing.ARMOR_KIND)
            self.edit(self.SMITH_A, stale)
            self.edit(self.SMITH_B, armor)
            emit("擺單子", {"town": town, "weapons": self.c.config.weapons.enabled, "armor": self.c.config.armor.enabled})
        self.drafts("前半停在這裡")
        self.figure_view("前半停在這裡")
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def smith_off(self) -> None:
        """防具這一欄關掉（武器照開：鐵匠鋪照開門，防具的單子在這裡打不了了）。同一個行程裡共用 CONTENT，smith_on 開回來。"""
        self.c.config.armor.enabled = False
        emit("防具這一欄關了", {"weapons": self.c.config.weapons.enabled})

    def resume(self) -> None:
        self.login_all()
        for who in self.PLAYERS:
            self.main(who)
        self.drafts("接手之後")
        self.season_view("接手")

    def cond_second(self) -> None:
        self.reads("後半：接手畫的")
        for who in (self.WEAVER, self.PLAIN):
            self.pend(who, None)
        self.reads("事件收掉之後")

    def smith_on(self) -> None:
        self.c.config.armor.enabled = True
        emit("防具這一欄開回來", None)
        for who in (self.SMITH_A, self.SMITH_B):
            self.main(who)
        self.drafts("開回來之後")

    def weeks(self) -> None:
        """一次快轉跨過下一個週一、再進那一週的四成：自然回復、退場的人回來、宴散、人物行事、設宴、求援委託、盤算、月旦評、週初與每天的掛鉤。"""
        if self.world.get_battle() is not None and self.world.get_battle().phase != "ended":
            self.cancel("接手開的")
        self.figure_view("快轉之前")
        self.forward(self.hours_to(self.into_next_week(1)), "跨週")
        self.figure_view("快轉之後")
        for who in (self.WEAVER, self.PLAIN):
            self.main(who)
            self.me(who, "跨週之後")


# 改一個字（selftest）：退場的大勢人物回來那一句（figures.revive 的 BACK_LINE；figures 這一批收進共用規則層、留在原檔）
register_track("loom", LoomScenario, (("tianxia/figures.py",), ("重新出來領兵", "重新出來帶兵")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
