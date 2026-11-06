"""same_behavior 一軌一檔：bout（這一檔登記 bout、ring）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track
from sb.tracks.explore import ExploreScenario, _explore_rules

# ═══════════════════════════ bout：單挑兩軌（全部拆包第 12 批，dev/bout-1） ═══════════════════════════
# 單人頭目戰、擂台（含看台的場邊事件）搬進 tianxia/features/bout/（計畫 docs/superpowers/plans/2026-11-03-單挑包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後兩行登記（register_track），PM 合的時候不跟別人的行穿插。同一套段落登記兩軌：bout 切在擂台報名之後、被挑之前
# （WorldState.arena 有人守擂、還沒人來挑；同一刻江小魚的頭目戰第一回合出過招、DuelState 寫進存檔），ring 切在擂台寫到一半（擂台打到一半、
# 場邊那一句等著重寫、守擂的那一筆沒補、坐在擂台邊、記下的俸沒領；審查修正，取代原本切在頭目戰打到一半、跟 bout 重複的 boss 那一軌）。
# 打法照 ExploreScenario 的小工具：抽到哪一類（探索一顆）、頭目的機率（Config.duel.explore_chance 換成 1）在要的那幾步換掉；勝負靠把
# 這一場的氣勢擺在門檻上（直接改資料庫）再出招，打的照真的算。模型：放手一搏的成功率與兩版劇情、台下觀眾的反應、場邊那一句的重寫
# 換成假的（MODEL["bout"] 開著時），其餘照舊不連網路。

BOUT_ONE = "雙刀一交，借勢翻身上台角，反手劈下。"  # 放手一搏寫的那一句（20 字以內）
_BOUT_CLIENTS: dict[type, type] = {}


def _bout_client(base: type) -> type:
    """放手一搏、看台、場邊那一句的假模型（base 是 _setup_child 換好的 client 類別）：SuccessRateJudgment 回 MODEL["bout"] 的成功率與
    兩版劇情（照提示裡的名號開頭）、CrowdJudge 回那一個反應、CrowdLine 回一句寫到該寫的人；其餘照 base。"""
    if base not in _BOUT_CLIENTS:
        import re

        class BoutClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                text = "\n".join(str(m.get("content", "")) for m in messages)
                if schema.__name__ == "SuccessRateJudgment":
                    found = re.search(r"玩家：(.+?)（所屬", text)
                    who = found.group(1) if found else "他"
                    return schema(success_rate=MODEL["bout"]["rate"], reasoning="",
                                  win=f"{who}一刀劈中，對手踉蹌退了三步。", lose=f"{who}一刀劈空，反被逼到台角。")
                if schema.__name__ == "CrowdJudge":
                    return schema(crowd=MODEL["bout"]["crowd"])
                if schema.__name__ == "CrowdLine":
                    found = re.search(r"一定要寫到「(.+?)」", text)
                    return schema(line=f"台下一陣騷動，{found.group(1) if found else ''}趁機穩住了腳步。")
                return super().chat_structured(messages, schema, *a, **k)

        _BOUT_CLIENTS[base] = BoutClient
    return _BOUT_CLIENTS[base]


class BoutScenario(ExploreScenario):
    """單挑（全部拆包第 12 批；--track bout、--track ring，各自一個資料庫）。照調查 area_combat.json 的 features/bout 那一段與派工：
    頭目戰——撞上頭目（不帶設定的舊探索、weekend 的三選一練功、week7／season21 的探索一顆；三選一的找素材在正式內容裡撞不上頭目——
    一類一顆開著時一定給料、不擲頭目，有分支層時按了只展開分支——Game._gather 改叫 _boss_ready() 那一行這裡走不到）、場景與輸入框、出招、放手一搏
    （/api/do/duel_text 鎖外三段式，假模型）、打贏（戰報、掉落、名望、破境丹的擲骰）、打輸、抽身、冷卻中與次數用完（三選一的練功鈕與
    行動列那一行）、穿防具開打（快照的減損、打完照磨）；擂台——打開（名次那一句）、報名、更新分身、挑一場、灰掉的挑擂鈕回原因、出招、
    放手一搏與看台的反應、場邊事件與鎖外重寫那一句（server.crowd_once）、認輸、名次交換、收場卡（店面那一頁）、守的人補戰報、
    換日領俸、坐在擂台邊動身與擂台關了收店；稱號被讀——玩家卡、名帖匣、榜單、狀態列、酒肆查人；伺服器假人（BotRunner：報名、
    挑擂、打到一半的頭目戰照架勢出招、坐在擂台邊只會返回）與整季機器人在頭目戰的選單上挑；收季（前三名、季末獎勵、打到一半的那一場
    作廢、江湖史的歷屆擂主）、開下一季。測試內容沒有頭目、擂台關著：同一串 API 照打（證明關著一個字都不變）。season21 的擂台照週解鎖
    （第 2 週才開）：記憶體裡關掉週解鎖（兩份程式、前後兩個行程都關），seat 那一段照開著的寫一次鎖著的樣子。"""

    PLAYERS = {"江小魚": None, "花無缺": "guan", "鐵心蘭": "huang", "燕南天": None, "邀月": None, "憐星": None}
    NEWBIE = "小仙女"
    # 頭目在哪（content/duels.json）：長社、汝南荒野（黃巾小帥）；南陽荒野、南陽官道（山匪頭子）；豪族塢堡、燕山腳下（河北豪強的門客）
    SEATS = {"江小魚": "changshe", "花無缺": "nanyang_wilds", "鐵心蘭": "yanshan_foot", "燕南天": "yingchuan", "邀月": "yingchuan",
             "憐星": "yingchuan"}
    BOT_SEATS = [("錦衣客", "changshe"), ("黑衣客", "yingchuan"), ("白衣客", "yingchuan"), ("灰衣客", "runan")]
    ALL = ["setup", "seat", "meet", "arena_join", "resume", "duel_more", "duel_lose", "duel_flee", "duel_old", "boss_gate", "arena_fight",
           "arena_more", "arena_refuse", "arena_yield", "defend", "wages", "titles", "depart", "closed", "bots", "season"]
    PHASES_FIRST = ALL[:ALL.index("arena_join") + 1]  # bout：切在擂台報名之後、被挑之前
    PHASES_SECOND = ALL[ALL.index("arena_join") + 1:]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            if MODEL.get("bout") is not None:
                client.__class__ = _bout_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        if profile == "season21":  # 擂台照週解鎖（第 2 週）：兩個行程都關（不寫輸出：前半＋後半要跟整段一樣）
            self.c.config.jianfa.week_unlock = False

    # ── 小工具 ──

    def begin(self) -> None:
        """每個請求換一份空的勝算記憶、清掉榜單的快取（server.boards_now 照真的 time.monotonic 判斷過期：不清的話跑得快慢決定讀到哪一份）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()
        self.server.BOARDS_CACHE.clear()

    def setup(self) -> None:
        Scenario.setup(self)  # 不擺探索那一軌的高寄萍

    @contextlib.contextmanager
    def model(self, rate: int = 70, crowd: str = "叫好"):
        MODEL["bout"] = {"rate": rate, "crowd": crowd}
        try:
            yield
        finally:
            MODEL.pop("bout", None)

    def me(self, who: str, tag: str) -> None:
        """存檔裡單挑那幾格（單挑包認領的十個欄位），加上氣血、內傷、銀兩、心得、名望、破境丹、防具、最新一份戰報與江湖紀錄的標題。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player

        def dump(x):
            return None if x is None else x.model_dump(mode="json")

        emit(f"{who} {tag}", {
            "duel": dump(p.duel), "duel_tally": dict(sorted(p.duel_tally.items())), "duel_last": list(p.duel_last),
            "arena": dump(p.arena), "arena_last": dump(p.arena_last), "picking_arena": p.picking_arena, "arena_day": p.arena_day,
            "arena_today": p.arena_today, "arena_crowd_seen": dict(sorted(p.arena_crowd_seen.items())),
            "arena_crowd_note": dump(p.arena_crowd_note), "neili": p.member.neili, "injury": p.member.injury,
            "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "fame": p.stats.get("fame", 0),
            "legend": p.legend_items, "armor": dump(p.armor), "battle": dump(state.battles[-1]) if state.battles else None,
            "journal": [e.title for e in state.journal[:4]]})

    def ladder(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"擂台 {tag}", {"entries": {k: e.model_dump(mode="json") for k, e in sorted(w.arena.items())},
                            "pairs": dict(sorted(w.arena_pairs.items())), "seq": w.arena_seq, "closed": w.arena_closed, "day": w.arena_day})

    def arm(self, who: str, level: int = 0) -> None:
        """學一門武學（沒有的話）；level 給了，武學、內功練到那一成。"""
        from tianxia import rules

        c = self.c
        skill = "jichu_quanjiao" if "jichu_quanjiao" in c.skills else sorted(c.skills)[0]

        def fn(state) -> None:
            if state.player.member.wugong_id is None:
                rules.learn_skill(state, c, skill)
            if level:
                state.player.member.wugong_level, state.player.member.neigong_level = level, level

        self.edit_state(who, fn)

    def encounter(self, who: str, mode: str = "PRACTICE") -> bool:
        """在這裡探索、撞上頭目（探索一顆抽到遭遇、頭目的機率換成 1；三選一的季按 mode 那一顆；舊探索照擲）。撞上了是 True。"""
        explore_one = _explore_rules()
        self.place(who, None)  # 體力補滿
        with self.draws(explore_one.ENCOUNTER), self.tweak(self.c.config.duel, explore_chance=1.0):
            self.choose(who, "act:explore")
            opts = self.options(who)
            oid = f"explore:{mode.lower()}"  # 第 13 批之前 explore_modes.option_id(getattr(explore_modes, mode))：同一個字
            if any(i.startswith("explore:") for i in opts):
                emit(f"{who} 三選一的 {oid}", opts.get(oid))
                if (opts.get(oid) or {}).get("enabled"):
                    self.choose(who, oid)
        duel = self.chars.load(who).player.duel
        emit(f"{who} 撞上頭目了嗎", None if duel is None else duel.model_dump(mode="json"))
        return duel is not None

    def bout(self, who: str, prefix: str, edge: float | None, rounds: int = 8) -> None:
        """一路出招到收場（prefix 是 duel 或 arena）：每一招之前把氣勢擺在 edge（None 照打）；招照固守、強攻、奇襲輪著出，鎖住的跳過。"""
        moves = ("固守", "強攻", "奇襲")
        for i in range(rounds):
            p = self.chars.load(who).player
            if (p.duel if prefix == "duel" else p.arena) is None:
                return
            if edge is not None:
                self.edit(who, lambda q: setattr(q.duel if prefix == "duel" else q.arena, "edge", edge))
            opts = self.options(who)
            pick = next((f"{prefix}:{m}" for m in moves[i % 3:] + moves[:i % 3] if (opts.get(f"{prefix}:{m}") or {}).get("enabled")), None)
            if pick is None:
                emit(f"{who} 選單上沒有招", sorted(opts))
                return
            self.choose(who, pick)

    def gamble(self, who: str, text: str = BOUT_ONE, rate: int = 70, crowd: str = "叫好") -> None:
        """放手一搏：頭目戰、擂台都走 /api/do/duel_text（鎖外三段式；假模型評 rate、台下觀眾 crowd）。"""
        with self.model(rate, crowd):
            self.do(who, "duel_text", {"text": text})

    def today(self, who: str) -> int:
        """這個人此刻回體丹那一套的今天（擂台的次數、俸照它換日）。"""
        from tianxia.engine import Game

        self.begin()
        game = Game(self.c, self.chars.load(who), world=self.world)
        game.sync(CLOCK[0])
        return game._pill_day()

    @staticmethod
    def fight_id(foe: str) -> str:
        from tianxia.characters import name_key

        return f"arena:fight:{name_key(foe)}"

    def lock_sync(self, name: str) -> None:
        """沒有帳號的人（bots 那一段補的假人）同步一次：照 BotRunner 在行動鎖裡建一份 Game（不叫模型）、sync、存回去。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load(name), world=self.world)
            game.client = None
            game.sync(CLOCK[0])
            self.chars.save(game.state)

    def boss_note(self, who: str, tag: str) -> None:
        """三選一的練功鈕與行動列底下那一行（頭目在不在、冷卻中、次數用完都寫在這兩處；別的季沒有這一顆，寫探索那一格）。"""
        view = self.main(who)
        oid = "explore:practice"  # 第 13 批之前 explore_modes.option_id(explore_modes.PRACTICE)：同一個字
        emit(f"{who} {tag}", {"practice": self.ids(view).get(oid), "explore": self.ids(view).get("act:explore"),
                              "notes": dict(sorted((view.get("action_notes") or {}).items()))})

    # ── 前半 ──

    def seat(self) -> None:
        """站好位置、學武學（江小魚練到第九成、穿一件三階上品的甲）、有陣營的劇本給花無缺官軍、鐵心蘭黃巾；每個人的擂台入口與探索那一格。
        season21 先照週解鎖開著寫一次（第 1 週擂台還鎖著）。"""
        from tianxia.state import Equipment

        factions = {f.id for f in self.c.scenario.factions}
        for who, loc in self.SEATS.items():
            side = self.PLAYERS[who]
            self.place(who, loc, faction=side if side in factions else "keep")
            self.arm(who, 9 if who == "江小魚" else 0)
        self.edit("江小魚", lambda p: setattr(p, "armor", Equipment(id="江小魚:1", slot="armor", name="試甲", attribute="剛", tier=3,
                                                                    quality="上品", edge=100)))
        if self.profile == "season21":
            with self.tweak(self.c.config.jianfa, week_unlock=True):
                emit("season21 週解鎖開著時的擂台入口", self.options("燕南天").get("act:arena"))
        for who in self.SEATS:
            view = self.main(who)
            emit(f"{who} 的擂台入口與探索", {"arena": self.ids(view).get("act:arena"), "explore": self.ids(view).get("act:explore"),
                                         "note": (view.get("action_notes") or {}).get("act:explore")})

    def meet(self) -> None:
        """江小魚在長社撞上頭目（穿著甲：減損快照進這一場）：場景卡、三招與抽身、輸入框；出一招（第一回合）：頭目戰打到一半，bout 那一軌的切點（arena_join 之後）跨過它。"""
        if not self.encounter("江小魚"):
            return
        view = self.main("江小魚")
        emit("頭目戰的選單", sorted(self.ids(view)))
        self.choose("江小魚", "duel:固守")
        self.me("江小魚", "第一回合之後")

    def arena_join(self) -> None:
        """擂台：憐星打開看一眼就返回；花無缺、鐵心蘭、燕南天依序報名（排第一、二、三）；鐵心蘭再按一次是更新分身；燕南天打開時的名次那一句。
        bout 那一軌切在這裡（有人守擂、還沒人來挑）。"""
        self.choose("憐星", "act:arena")
        self.main("憐星")
        self.choose("憐星", "arena:back")
        for who in ("花無缺", "鐵心蘭", "燕南天"):
            self.place(who, None)
            self.choose(who, "act:arena")
            self.choose(who, "arena:join")
            self.choose(who, "arena:back")
        self.choose("鐵心蘭", "act:arena")
        self.choose("鐵心蘭", "arena:join")
        self.choose("鐵心蘭", "arena:back")
        self.choose("燕南天", "act:arena")
        self.choose("燕南天", "arena:back")
        self.ladder("報名之後")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def duel_more(self) -> None:
        """江小魚接著打（新程式接手舊程式打到一半的那一場）：放手一搏（假模型 70）、再把氣勢擺在 89 一路出招到收場（打贏：掉落、名望、
        破境丹的擲骰、甲照磨）；收場之後在長社再探索一次（冷卻中：不撞頭目）。"""
        if self.chars.load("江小魚").player.duel is None:
            emit("江小魚沒有在打頭目", None)
            return
        self.gamble("江小魚")
        self.me("江小魚", "放手一搏之後")
        self.bout("江小魚", "duel", 89.0)
        self.me("江小魚", "打完頭目")
        self.encounter("江小魚")
        self.me("江小魚", "冷卻中再探索")

    def duel_lose(self) -> None:
        """花無缺在南陽荒野撞上山匪頭子，氣勢擺在 11 一路出招：打輸（掉的氣血扣回本人、兩成變內傷）。三選一的找素材在正式內容裡撞不上頭目
        （一類一顆開著時一定給料、不擲頭目；有分支層時按了只展開分支）：Game._gather 撞頭目那一行這裡走不到。"""
        if self.encounter("花無缺"):
            self.bout("花無缺", "duel", 11.0)
        self.me("花無缺", "打輸頭目")

    def duel_flee(self) -> None:
        """鐵心蘭在燕山腳下撞上河北豪強的門客：放手一搏（模型叫不到：評 40、固定句），再抽身退走（不寫戰報、掉的氣血不回）；走到黃巾大營
        （沒有頭目）看練功鈕與行動列那一行。"""
        if self.encounter("鐵心蘭"):
            self.do("鐵心蘭", "duel_text", {"text": "閉眼亂揮一通。"})
            self.choose("鐵心蘭", "duel:flee")
        self.me("鐵心蘭", "抽身之後")
        self.place("鐵心蘭", "huangjin_camp" if "huangjin_camp" in self.c.locations else None)  # 沒有頭目的地方：練功鈕與行動列寫什麼
        self.boss_note("鐵心蘭", "沒有頭目的地方的練功鈕與行動列")

    @contextlib.contextmanager
    def explore_modes_off(self):
        """舊探索：三選一的開關在記憶體裡關掉（第 13 批之前）；第 13 批之後沒有那個開關，換成它關著時連帶關掉的那幾樣
        （一類一顆、事件五折、觀山石的加成；計畫 2026-11-04-拿掉一-第13批.md 2.1），兩份程式走的是同一條路。
        event_trend_share 搬出來了就是「之後」（Task 2 做完、三選一還在的那一刻兩邊都關）。"""
        cfg = self.c.config
        if not hasattr(cfg, "event_trend_share"):
            with self.tweak(cfg.explore_modes, enabled=False):
                yield
            return
        with self.tweak(cfg, precise_actions=False, event_trend_share=1.0, sense_treasure_points=0):
            if hasattr(cfg, "explore_modes"):
                with self.tweak(cfg.explore_modes, enabled=False):
                    yield
            else:
                yield

    def duel_old(self) -> None:
        """舊探索撞上頭目（三選一的開關在記憶體裡關掉：不帶設定與 weekend 的 act:explore 走 _explore 那一條；探索一顆的季照樣是出門一趟）：
        憐星在汝南荒野撞上黃巾小帥，抽身退走。"""
        self.place("憐星", "runan_wilds")
        with self.explore_modes_off():
            if self.encounter("憐星"):
                self.choose("憐星", "duel:flee")
        self.me("憐星", "舊探索的頭目之後")

    def boss_gate(self) -> None:
        """遇不上頭目的兩種（三選一的練功鈕與行動列那一行寫原因；長社對官軍的人只有頭目、沒有尋常對手，練功那一格才寫頭目）：花無缺剛打完
        山匪頭子（冷卻中）、冷卻擺過去之後長社這一隻次數用完（季的帳與週的帳都擺滿）；再探索一次也不撞上。江小魚剛打完、在長社再看一次。"""
        from tianxia import duel

        self.place("江小魚", "changshe")
        self.boss_note("江小魚", "冷卻中的練功")
        self.place("花無缺", "changshe")
        self.boss_note("花無缺", "冷卻中的練功")
        c = self.c

        def used_up(state) -> None:
            state.player.duel_last = []
            for boss in duel.here(state, c):
                state.player.duel_tally[duel.season_key(state, boss.id)] = c.config.duel.per_boss_season
                if c.config.duel.per_boss_week:
                    state.player.duel_tally[duel.week_key(state, c, boss.id)] = c.config.duel.per_boss_week

        for who in ("花無缺", "江小魚"):
            self.edit_state(who, used_up)
            emit(f"{who} 冷卻擺過去、長社的頭目次數擺滿", None)
            self.boss_note(who, "次數用完的練功")
            self.encounter(who)

    def arena_fight(self) -> None:
        """江小魚報名（排第四）、挑燕南天（第三）：看台的場邊事件機率換成 1；放手一搏（假模型 70、台下「離譜」）——打到一半
        （ArenaFight 第一回合寫進存檔、場邊那一句等著鎖外重寫）。ring 那一軌切在這裡（審查修正：拆成兩段，arena_more 接著打）。"""
        self.place("江小魚", None)
        self.choose("江小魚", "act:arena")
        self.choose("江小魚", "arena:join")
        view = self.main("江小魚")
        emit("江小魚 擂台上挑得到的", sorted(i for i in self.ids(view) if i.startswith("arena:")))
        with self.tweak(self.c.config.arena.crowd, chance=1.0, outrage_chance=1.0):
            self.choose("江小魚", self.fight_id("燕南天"))
            self.gamble("江小魚", crowd="離譜")  # 台下看不下去：場邊事件擲中「離譜」那一種
        self.me("江小魚", "放手一搏之後（擂台打到一半）")

    def arena_more(self) -> None:
        """江小魚接著打燕南天（ring 那一軌是新程式接手舊程式打到一半的那一場）：氣勢擺在 89 出招到收場（大勝：交換名次、留一筆給燕南天、
        收場卡）；伺服器在鎖外重寫場邊那一句（server.crowd_once：ring 那一軌重寫的是舊程式記下的單子）。"""
        with self.tweak(self.c.config.arena.crowd, chance=1.0, outrage_chance=1.0):
            self.bout("江小魚", "arena", 89.0)
        self.me("江小魚", "挑完燕南天")
        self.begin()
        with self.model():
            emit("場邊那一句鎖外重寫", self.server.crowd_once(self.server.game_for("江小魚")))
        self.me("江小魚", "重寫之後")
        self.main("江小魚")
        self.ladder("挑完燕南天")

    def arena_refuse(self) -> None:
        """灰掉的挑擂鈕：今天的次數擺成用完（全部灰掉、寫明日再挑），按下去回原因、不寫紀錄；擺回來。"""
        today = self.today("江小魚")
        left = self.c.config.arena.per_day
        self.edit("江小魚", lambda p: (setattr(p, "arena_day", today), setattr(p, "arena_today", left)))
        emit("江小魚 今天的次數擺成用完", today)
        view = self.main("江小魚")
        emit("江小魚 灰掉的挑擂鈕", {i: o for i, o in sorted(self.ids(view).items()) if i.startswith("arena:")})
        self.choose("江小魚", self.fight_id("花無缺"))
        self.edit("江小魚", lambda p: setattr(p, "arena_today", 1))

    def arena_yield(self) -> None:
        """江小魚挑鐵心蘭（第二），出一招就認輸（落敗：名次不動、留一筆給鐵心蘭）。"""
        self.choose("江小魚", self.fight_id("鐵心蘭"))
        self.bout("江小魚", "arena", None, rounds=1)
        if self.chars.load("江小魚").player.arena is not None:
            self.choose("江小魚", "arena:yield")
        self.me("江小魚", "認輸之後")
        self.choose("江小魚", "arena:back")
        self.ladder("認輸之後")

    def defend(self) -> None:
        """守擂的人下一次同步補戰報與「守擂・挑的人」：燕南天（被挑贏、名次掉一名）、鐵心蘭（守住）。"""
        for who in ("燕南天", "鐵心蘭"):
            self.main(who)
            self.me(who, "補守擂之後")

    def wages(self) -> None:
        """換日（現實時間，同回體丹）：時鐘推過一天，第一個同步的人記前幾名的俸，每個人同步時領。"""
        STEP[0] += 1440
        emit("時鐘推過一天", None)
        self.wages_collect()

    def wages_collect(self) -> None:
        for who in ("花無缺", "鐵心蘭", "江小魚", "燕南天"):
            self.main(who)
            self.me(who, "換日之後")
        self.ladder("換日之後")

    # ── ring 那一軌（審查修正）切點前多走的兩段：bout 那一軌不走 ──

    def ring_yield(self) -> None:
        """鐵心蘭（第二）挑花無缺（第一），一開打就認輸（落敗：名次不動、留一筆給花無缺、兩人都打過一場）；不按返回，坐在擂台邊。"""
        self.place("鐵心蘭", None)
        self.choose("鐵心蘭", "act:arena")
        self.choose("鐵心蘭", self.fight_id("花無缺"))
        if self.chars.load("鐵心蘭").player.arena is not None:
            self.choose("鐵心蘭", "arena:yield")
        self.me("鐵心蘭", "挑花無缺認輸之後")
        self.ladder("鐵心蘭認輸之後")

    def wages_roll(self) -> None:
        """換日（同 wages 那一步，挪到切點前）：時鐘推過一天，邀月（沒上擂台）先同步，記下打過一場的前幾名的俸（還沒領）。"""
        STEP[0] += 1440
        emit("時鐘推過一天", None)
        self.main("邀月")
        self.ladder("換日記俸之後")

    def titles(self) -> None:
        """稱號被讀：花無缺（天下第一）的狀態列與名帖匣；邀月在潁川看他的玩家卡、看榜單、在酒肆打聽他（名氣）。"""
        self.place("花無缺", "yingchuan")
        self.place("邀月", "yingchuan")
        view = self.main("花無缺")
        emit("花無缺 狀態列", view.get("status"))
        self.call("花無缺", "GET", "/api/mingtie")
        self.call("邀月", "GET", "/api/peer?name=花無缺")
        self.call("邀月", "GET", "/api/boards")
        self.choose("邀月", "act:tavern")
        self.do("邀月", "tavern", {"op": "seek", "target": "花無缺", "text": ""})
        self.choose("邀月", "tavern:back")

    def depart(self) -> None:
        """坐在擂台邊動身：鐵心蘭打開擂台，從輿圖安排前往被擋（atlas.travel_block）；Game._depart 在鎖裡直接叫一次（同酒肆那一軌：坐在
        店裡的人平常走不到這一行），擂台跟別的店一起收起來、動身上路。之後擺回原地。"""
        from tianxia import atlas
        from tianxia.engine import Game

        start = self.chars.load("鐵心蘭").player.location
        dest = self.c.locations[start].connections[0] if self.c.locations[start].connections else start
        self.place("鐵心蘭", start)
        self.choose("鐵心蘭", "act:arena")
        self.call("鐵心蘭", "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.me("鐵心蘭", "從輿圖安排前往之後")
        self.begin()
        with self.world.action_lock():
            game = Game(self.c, self.chars.load("鐵心蘭"), world=self.world)
            game.sync(CLOCK[0])
            route = atlas.way_to(game.state, self.c, dest)
            emit("鐵心蘭 直接動身", game._depart(route, "walk") if route is not None else None)
            self.chars.save(game.state)
        self.me("鐵心蘭", "動身之後")
        self.place("鐵心蘭", start)

    def closed(self) -> None:
        """擂台開關關掉（記憶體裡，做完開回來）：燕南天開著時坐進擂台、照那一刻建一份 Game（沒有收店）；關掉之後不 sync，選單照舊是擂台
        那一串、假人看「返回」照舊 0 分、按得出去。憐星坐進擂台之後關掉、再同步：收店、入口沒了、挑擂與報名都被拒。"""
        from tianxia import bot_policy
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        self.choose("燕南天", "act:arena")
        self.choose("憐星", "act:arena")
        self.begin()
        game = Game(self.c, self.chars.load("燕南天"), world=self.world)
        cfg = self.c.config.arena
        before = cfg.enabled
        cfg.enabled = False
        try:
            menu = game.options(odds=False)
            emit("關掉那一刻 燕南天的選單（沒有 sync）", [o.id for o in menu])
            back = next((o for o in menu if o.id == "arena:back"), None)
            if back is not None:
                emit("關掉那一刻 假人看返回", bot_policy.score(game, back, BotProfile(personality="普通", seed=1)))
                emit("關掉那一刻 返回", game.choose("arena:back"))
            view = self.main("憐星")
            emit("關著 憐星的選單", sorted(self.ids(view)))
            self.choose("憐星", "arena:join")
            self.choose("憐星", "act:arena")
            self.me("憐星", "關著")
        finally:
            cfg.enabled = before

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(13)、時鐘一輪推四分）：同一個資料庫補四個假人——錦衣客在長社撞上頭目
        （打到一半：take_turn 照架勢出招）、黑衣客坐在擂台邊（bot_policy.score 問單挑包「返回」那一顆）、另兩位閒著；bot_policy.ARENA_CHANCE
        換成 1（照舊是 bot_policy 的模組屬性，_arena 那一步照舊在 bot_policy）。整季機器人（bot.pick）在錦衣客的頭目戰選單上挑一顆（不按：
        那一場留給 BotRunner 照架勢打完）；灰衣客走到汝南荒野撞上黃巾小帥，那一場由整季機器人從頭按到尾（season_bot_duel，BotRunner 之前）。
        測試內容沒有頭目、擂台關著：只擺人、照跑。"""
        from collections import Counter

        from tianxia import bot, bot_policy, duel, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        for i, (name, loc) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=None, season_number=self.world.get_season_number())
            if loc in self.c.locations:
                p.location, p.journey = loc, None
                p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.picking_arena = i == 1
            self.chars.save(g.state)
            self.arm(name, 6 if i == 0 else 0)
            if i == 0:
                self.begin()
                with self.world.action_lock():
                    g = Game(self.c, self.chars.load(name), rng=random.Random(5), world=self.world)
                    g.client = None
                    g.sync(CLOCK[0])
                    boss = duel.available(g.state, self.c)
                    emit("錦衣客 撞上的頭目", None if boss is None else boss.id)
                    if boss is not None:
                        emit("錦衣客 開打", g._duel_start(boss))
                        emit("整季機器人在頭目戰的選單上挑", bot.pick(g, g.options(odds=False), random.Random(0)))
                    self.chars.save(g.state)
        self.season_bot_duel("灰衣客", "runan_wilds")  # BotRunner 之前：閒著的那一位（打完的冷卻與氣血照帶進 BotRunner）
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(13), clock=lambda: CLOCK[0])
        chance, tick, online = bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))}
        bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds = 1.0, 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_BOUT_TICKS", "30"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            bot_policy.ARENA_CHANCE, self.c.config.bot_tick_seconds, server_bots.is_online = chance, tick, online
        states = self.chars.all(bots_only=True)
        emit("單挑假人 一輪一輪", dict(sorted(totals.items())))
        emit("單挑假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("單挑假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        self.ladder("假人之後")

    def season_bot_duel(self, name: str, loc: str) -> None:
        """整季機器人把一場頭目戰從頭打到尾（審查修正：以前只挑一顆、沒按下去）：name（剛補的、閒著的假人）走到 loc 撞上頭目，每一招照
        bot.pick 挑、照 Game.choose 按（同 bot.play_season），打到收場。在行動鎖裡、固定種子；測試內容沒有這個地點、沒有頭目：只寫一行。"""
        from tianxia import bot, duel
        from tianxia.engine import Game

        if loc not in self.c.locations:
            emit(f"{name} 整季機器人的頭目戰（這份內容沒有 {loc}）", None)
            return
        self.begin()
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(name), rng=random.Random(7), world=self.world)
            g.client = None
            g.sync(CLOCK[0])
            p = g.state.player
            p.location, p.journey = loc, None
            p.visited.add(loc)
            boss = duel.available(g.state, self.c)  # 經舊名 duel：base（搬包之前）沒有 Game._boss_ready
            emit(f"{name} 撞上的頭目（整季機器人）", None if boss is None else boss.id)
            picks: list[str | None] = []
            if boss is not None:
                g._duel_start(boss)
                rng = random.Random(0)
                while g.state.player.duel is not None and len(picks) < 20:
                    pick = bot.pick(g, g.options(odds=False), rng)
                    picks.append(pick)
                    if pick is None:
                        break
                    g.choose(pick)
            emit(f"{name} 整季機器人按的招", picks)
            self.chars.save(g.state)
        self.me(name, "整季機器人打完頭目")

    def season(self) -> None:
        """收季：江小魚挑花無缺打到一半（出一招）就收季——前三名排好、江湖史記擂主；江小魚同步時那一場作廢；前三名休季同步領季末的獎勵
        （名次被 bots 那一段的假人搶走的，照 BotRunner 在鎖裡同步一次：審查修正，以前只走到第三名）；江湖史的歷屆擂主。開下一季：
        單挑那十個欄位跟著新角色重來、季上的擂台是空的。"""
        self.place("江小魚", None)
        view = self.choose("江小魚", "act:arena")
        fights = [i for i, o in self.ids(view).items() if i.startswith("arena:fight:") and o.get("enabled")]
        emit("江小魚 收季之前挑誰", fights[:1])
        if fights:
            self.choose("江小魚", fights[0])
            self.bout("江小魚", "arena", None, rounds=1)
        self.me("江小魚", "收季之前打到一半")
        self.do(ADMIN, "end_season")
        self.ladder("收季之後")
        players = ("江小魚", "花無缺", "鐵心蘭", "燕南天")
        for who in players:
            view = self.main(who)
            self.me(who, "休季同步之後")
        placed = sorted((e.place, e.name) for e in self.world.get_season().arena.values() if e.place)
        emit("收季之後的前三名", placed)
        for _, name in placed:
            if name not in players:
                self.lock_sync(name)
                self.me(name, "休季同步之後")
        emit("江湖史", view.get("chronicle"))
        self.do(ADMIN, "next_season")
        for who in ("江小魚", "花無缺"):
            self.main(who)
            self.me(who, "換季之後")
        self.ladder("換季之後")


class RingScenario(BoutScenario):
    """同一套段落換個先後，切在擂台寫到一半（--track ring；審查修正，取代切在頭目戰打到一半的 boss 那一軌：那一刻 bout 那一軌的切點
    本來就跨過了）。切的那一刻，舊程式寫下、新程式接手的：江小魚挑燕南天放手一搏過一招（ArenaFight 打到一半）、場邊那一句等著鎖外
    重寫（arena_crowd_note；燕南天那邊的場邊帳記在季上）；鐵心蘭挑花無缺認輸（花無缺守擂的那一筆還沒補）、坐在擂台邊（picking_arena）；
    換過日、邀月同步時記下的俸還沒領（花無缺、鐵心蘭：打過一場的才有）。後半由新程式接著打完、重寫那一句、補戰報、領俸、收店。
    擂台那幾段多走 ring_yield、wages_roll（換日挪到切點前，後半的領俸不再推一天：一軌只推一天，週末季 2.5 天跑不完）。"""

    PHASES_FIRST = [n for n in BoutScenario.ALL[:BoutScenario.ALL.index("arena_fight")] if n != "resume"] + [
        "ring_yield", "wages_roll", "arena_fight"]
    PHASES_SECOND = ["resume", "arena_more", "arena_refuse", "arena_yield", "defend", "wages_collect", "titles", "depart", "closed",
                     "bots", "season"]


# 改一個字（selftest）：bout 改擂台報名那一句（搬之前在 tianxia/arena.py、之後在包裡的 arena_rules.py），ring 改撞上頭目那一句
# （搬之前在 engine.py 的 _duel_start、之後在包裡的 duel_actions.py）
register_track("bout", BoutScenario, (("tianxia/features/bout/arena_rules.py", "tianxia/arena.py"),
                                       ("別人隨時可以來挑。", "別人隨時可以來挑！")), "week7")
register_track("ring", RingScenario, (("tianxia/features/bout/duel_actions.py", "tianxia/engine.py"),
                                       ("攔住了去路！", "攔住了去路。")), "week7")
