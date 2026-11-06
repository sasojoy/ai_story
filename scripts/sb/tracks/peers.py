"""same_behavior 一軌一檔：peers（這一檔登記 peers）。"""
from __future__ import annotations

import contextlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track

# ═══════════════════════════ peers（全部拆包第 37 批「玩家互動一」，dev/peers-1）：peers 一軌 ═══════════════════════════
# 此地還有、玩家卡、邀請框（invite:）、打招呼、贈物、名帖、/api/peer 與 /api/mingtie 四條路由（計畫 docs/superpowers/plans/2026-11-06-玩家互動包-第1批.md）。
# 切磋、論武、截殺是第 38 批，這一軌只在玩家卡上看得到它們的鈕（card 一併進輸出），不按。名字一律原創（第 22 批認定第 3 條）。


class PeersScenario(Scenario):
    """玩家互動一軌（全部拆包第 37 批；--track peers，自己一個資料庫）。
    此地還有（/api/main 的 here、calls）：同地點有別人〔照名號排序〕、同步太久的（presence_seconds 外）不列、剛好在窗口內外、在路上的看不到也不被看到、
    別處的、序章裡的；窗口縮成 900 秒再量一次。玩家卡（GET /api/peer）：在場的、不在場的、路上的人去看、沒這個人、看不到名帖的。
    打招呼（挑釁，POST /api/peer/act greet）：不附話、附話、太長、重發（還沒回應）、對方回禮（選單 invite:cold|retort:<編號>、卡上 reply:）、不接他的挑釁話（mute／unmute）、
    作廢（逾時）、沒有這個動作、對方不在。贈物（gift）：送出、同一對人滿了、一天滿了、不夠、數量零、送不出去的階、第四階、沒有素材的人卡上沒有鈕。
    名帖（/api/mingtie/save、report、GET；卡上 mingtie send／yes／no）：定稿〔畫壞了、頭銜不在池裡、空的、太長、一天滿了〕、遞帖、回帖（選單 invite:yes）、
    婉拒、沒有自己的名帖回不了、換新帖、同一版再遞、一天遞滿、檢舉〔藏起來、滿了等管理者〕、管理者撤下與放回。三種設定 week7、season21、test。
    **前半停在邀請送出還沒接受的五處**（打招呼一張、遞名帖一張、一張待逾時作廢、兩張半截的名帖）：後半新程式接著答（選單、卡上）、作廢的那張答不了；
    假人（BotRunner 兩個〔收到打招呼與名帖、自己做名帖、向此地的人遞帖〕、整季機器人眼前有邀請時的選單與挑法）；換季（名帖跨季帶著走、邀請清空）。"""

    VIEW, PEER, PEER2, GIVER = "霜林客", "晚照生", "孤雁歸", "拾穗人"
    STALE, ELSE, ROAD = "殘月客", "遠山客", "渡頭客"
    HALF_A, HALF_B = "折柳人", "聽雨人"
    MT_A, MT_B, MT_C = "畫扇人", "題襟客", "拓碑人"
    BOT_HUMAN = "撥雲客"
    BOT_SEATS = ["伴甲", "伴乙"]
    PLAYERS = {VIEW: "guan", PEER: "guan", PEER2: "huang", GIVER: "guan", STALE: "guan", ELSE: "huang", ROAD: None,
               HALF_A: "guan", HALF_B: "guan", MT_A: "guan", MT_B: "guan", MT_C: "huang", BOT_HUMAN: "guan"}
    PHASES_FIRST = ["setup", "seat", "here", "card", "greet", "gifts", "mingtie", "reports", "half"]
    PHASES_SECOND = ["resume", "answer", "bots", "season"]
    STROKES = [[0, 0, 10, 10, 120, 80], [1, 1, 40, 200, 160, 220, 250, 390]]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        self.c.config.presence_seconds = 86400.0  # 正式值：每種設定同一個窗口（窗口本身另外在 here 縮小再量）
        self.c.config.invite_ttl_seconds = 36000.0  # 邀請逾時拉長：前半停下、後半接手之間隔了幾十步，不拉長的話前半留下的邀請到後半都作廢了（作廢另用 expire_all 擺）

    # ── 小工具 ──

    def begin(self) -> None:
        super().begin()
        self.server.BOARDS_CACHE.clear()  # 名帖頭銜讀整張榜：server.boards_now 的快取用真的 time.monotonic（預設參數），整段跑得快、前半後半隔了一個行程，快取撞不撞到不同

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def tuned(self, owner=None, **values):
        owner = self.c.config if owner is None else owner
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", dict(values))
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def hub(self) -> str:
        return self.c.scenario.start_location

    def elsewhere(self) -> str:
        return next((loc for loc in sorted(self.c.locations) if loc != self.hub()), self.hub())

    def sync(self, *names: str) -> None:
        for who in names:
            self.main(who)

    def invites_of(self, who: str, kind: str | None = None) -> list:
        w = self.world.get_season()
        key = who.lower()
        return [i for i in w.invites if i.target.lower() == key and (kind is None or i.kind == kind)]

    def reply(self, who: str, sender: str, verb: str, kind: str | None = None) -> None:
        """選單上回他的邀請（invite:<回應>:<編號>，同真人按的那一顆）；先看一眼選單；沒有他發的邀請寫「沒有」。"""
        self.main(who)
        found = [i for i in self.invites_of(who, kind) if i.sender == sender]
        if not found:
            emit(f"{who} 沒有 {sender} 的邀請", None)
            return
        self.choose(who, f"invite:{verb}:{found[0].id}")

    def act(self, who: str, name: str, action: str, **body):
        return self.call(who, "POST", "/api/peer/act", {"name": name, "action": action, **body})[1]

    def card_of(self, who: str, name: str):
        return self.call(who, "GET", f"/api/peer?name={name}")[1]

    def expire_all(self, sender: str | None = None) -> None:
        """還在等的邀請（發的人是 sender，沒給就全部）直接擺成逾時：只靠步數等不到 invite_ttl_seconds。"""
        def fn(w) -> None:
            for inv in w.invites:
                if sender is None or inv.sender == sender:
                    inv.expires_at = w.time - 1.0
        self.world.mutate_season(fn)
        emit(f"擺成逾時 {sender or '全部'}", None)

    def backdate(self, sender: str) -> None:
        """發出去的邀請擺成很久以前收到的（假人收到之後要隔一段現實秒才回），逾時留得夠遠。"""
        def fn(w) -> None:
            for inv in w.invites:
                if inv.sender == sender:
                    inv.sent_at = w.time - 600.0 * max(1.0, self.c.config.time_scale)
                    inv.expires_at = w.time + 3600.0 * max(1.0, self.c.config.time_scale)
        self.world.mutate_season(fn)
        emit(f"擺成早收到 {sender}", None)

    def you(self, who: str, tag: str) -> None:
        """存檔裡玩家互動碰得到的格子：在哪、路上、素材、名帖與名帖匣、定稿與遞帖的次數、檢舉過的、不接誰的挑釁話、贈物次數、最新兩則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        card = p.mingtie
        emit(f"{who} {tag}", {
            "loc": p.location, "journey": p.journey is not None, "last_real": state.last_real, "faction": p.faction,
            "materials": dict(sorted(p.materials.items())),
            "mingtie": None if card is None else [card.version, card.motto, list(card.titles), len(card.strokes)],
            "box": [[m.name, m.card.version, m.when, m.place, m.season] for m in p.mingtie_box],
            "mday": [p.mingtie_day, p.mingtie_made, p.mingtie_sent], "hidden": list(p.mingtie_hidden), "muted": list(p.taunt_muted),
            "gift": [p.gift_day, p.gifts_today],
            "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:2]]})

    def world_view(self, tag: str) -> None:
        w = self.world.get_season()
        sh = self.world.read()
        emit(f"世界 {tag}", {
            "invites": [[i.id, i.kind, i.sender, i.target, i.location, i.sent_at, i.expires_at, dict(sorted(i.payload.items()))] for i in w.invites],
            "tally": [dict(sorted(w.gift_tally.items())), dict(sorted(w.spar_tally.items())), dict(sorted(w.discuss_tally.items()))],
            "reports": {k: list(v) for k, v in sorted(sh.mingtie_reports.items())},
            "removed": dict(sorted(sh.mingtie_removed.items())), "cleared": list(sh.mingtie_cleared)})

    def gift_mats(self) -> tuple[list[str], list[str], list[str]]:
        """（送得出去的素材、超過 gift_max_tier 階的、第四階的）各最多兩樣。"""
        from tianxia import four_tiers

        c, top = self.c, self.c.config.gift_max_tier
        ok, high, tier4 = [], [], []
        for mid in sorted(c.materials):
            m = c.materials[mid]
            if four_tiers.tier4_id(c, mid):
                tier4.append(mid)
            elif m.tier <= top:
                ok.append(mid)
            else:
                high.append(mid)
        return ok[:2], high[:1], tier4[:1]

    # ── 前半 ──

    def seat(self) -> None:
        hub, far = self.hub(), self.elsewhere()
        for who, side in self.PLAYERS.items():
            self.place(who, far if who == self.ELSE else hub, side)
        ok, high, tier4 = self.gift_mats()
        self.edit(self.GIVER, lambda p: p.materials.update({m: 6 for m in [*ok, *high, *tier4]}))
        emit("素材", {"ok": ok, "high": high, "tier4": tier4})
        from tianxia.state import Journey

        self.edit(self.ROAD, lambda p: setattr(p, "journey", Journey(mode="walk", path=[far], arrive_at=[10 ** 9])))
        for who in self.PLAYERS:
            self.main(who)
        self.world_view("坐定")

    def here(self) -> None:
        """此地還有：誰列得出來、誰列不出來；窗口邊上內外；在路上；別處。"""
        self.sync(self.PEER, self.PEER2, self.GIVER)
        self.main(self.VIEW)
        self.edit_state(self.STALE, lambda s: setattr(s, "last_real", CLOCK[0] - 10 * 86400.0))
        self.main(self.VIEW)
        view = self.main(self.VIEW)
        emit("名單（照名號排序）", [p["name"] for p in (view.get("here") or [])] if isinstance(view, dict) else None)
        with self.tuned(presence_seconds=900.0):
            self.edit_state(self.PEER2, lambda s: setattr(s, "last_real", CLOCK[0] - 1500.0))
            self.edit_state(self.GIVER, lambda s: setattr(s, "last_real", CLOCK[0] - 300.0))
            self.main(self.VIEW)
            emit("窗口 900：外的卡", self.card_of(self.VIEW, self.PEER2).get("card") is None)
            emit("窗口 900：內的卡", self.card_of(self.VIEW, self.GIVER).get("card") is not None)
        self.sync(self.PEER2, self.GIVER)
        self.main(self.VIEW)
        self.main(self.ROAD)  # 在路上的人看不到人
        self.main(self.ELSE)
        self.main(self.NEWBIE)
        self.you(self.STALE, "同步太久")
        self.you(self.ROAD, "在路上")

    def card(self) -> None:
        """玩家卡：在場的、同步太久的、在路上的、別處的、沒這個人；路上的人去看別人。"""
        for name in (self.PEER, self.PEER2, self.GIVER, self.STALE, self.ROAD, self.ELSE, "無名氏", " " + self.PEER):
            emit(f"卡 {name!r}", self.card_of(self.VIEW, name))
        emit("路上的人看卡", self.card_of(self.ROAD, self.PEER))
        emit("沒有素材的人看有素材的人", self.card_of(self.VIEW, self.GIVER).get("card"))

    def greet(self) -> None:
        """打招呼（挑釁）：不附話、附話、太長、重發；對方回禮（選單）；卡上回；不接他的挑釁話；作廢；沒有這個動作；對方不在。"""
        self.sync(self.PEER, self.PEER2, self.GIVER)
        self.act(self.VIEW, self.PEER, "greet", arg="taunt")
        self.act(self.VIEW, self.PEER, "greet", arg="taunt")  # 還沒回應
        self.world_view("挑釁之後")
        self.you(self.PEER, "被挑釁")
        self.card_of(self.PEER, self.VIEW)
        self.reply(self.PEER, self.VIEW, "retort", "greet")
        self.you(self.VIEW, "挑釁被回敬")
        self.act(self.PEER2, self.VIEW, "greet", arg="mute")  # 不接他的挑釁話
        self.act(self.VIEW, self.PEER2, "greet", arg="taunt", text="三腳貓功夫也敢出門")
        self.card_of(self.PEER2, self.VIEW)
        self.reply(self.PEER2, self.VIEW, "cold", "greet")
        self.you(self.PEER2, "不接挑釁話")
        self.you(self.VIEW, "對方冷眼以對")
        self.act(self.PEER2, self.VIEW, "greet", arg="unmute")
        self.act(self.VIEW, self.GIVER, "greet", arg="taunt", text="這一句字數太多太多太多太多太多太多太多太多太多太多太多")  # 太長
        self.act(self.VIEW, self.GIVER, "greet", arg="taunt", text="有種來比")
        self.card_of(self.GIVER, self.VIEW)
        self.act(self.GIVER, self.VIEW, "greet", arg="reply:cold")  # 卡上回
        self.act(self.GIVER, self.VIEW, "greet", arg="reply:cold")  # 已經回過了
        self.act(self.VIEW, self.GIVER, "greet", arg="bogus")  # 沒有這種禮數
        self.act(self.VIEW, self.GIVER, "nope")  # 沒有這個動作
        self.act(self.VIEW, self.ELSE, "greet", arg="taunt")  # 不在這裡
        self.act(self.VIEW, "無名氏", "greet", arg="taunt")
        self.act(self.ROAD, self.PEER, "greet", arg="taunt")  # 自己在路上
        self.act(self.VIEW, self.PEER, "greet", arg="taunt", text="再來一次")
        self.expire_all(self.VIEW)  # 作廢
        self.reply(self.PEER, self.VIEW, "retort", "greet")
        self.main(self.VIEW)
        self.world_view("作廢之後")

    def gifts(self) -> None:
        """贈物：送出、同一對人滿了、一天滿了、不夠、零個、送不出去的階、第四階、沒素材的人。"""
        ok, high, tier4 = self.gift_mats()
        self.sync(self.PEER, self.PEER2, self.GIVER)
        self.card_of(self.GIVER, self.PEER)
        if ok:
            self.act(self.GIVER, self.PEER, "gift", arg="material", choice=ok[0], amount=2)
            self.act(self.GIVER, self.PEER, "gift", arg="material", choice=ok[0], amount=0)
            self.act(self.GIVER, self.PEER, "gift", arg="material", choice=ok[0], amount=99)
            self.act(self.GIVER, self.PEER, "gift", arg="bogus", choice=ok[0], amount=1)
            self.you(self.PEER, "收了禮")
            with self.tuned(gift_per_pair_day=1):
                self.act(self.GIVER, self.PEER, "gift", arg="material", choice=ok[0], amount=1)  # 同一對人滿了
                self.card_of(self.GIVER, self.PEER)
            with self.tuned(gift_per_day=1):
                self.act(self.GIVER, self.PEER2, "gift", arg="material", choice=ok[-1], amount=1)  # 一天滿了
                self.card_of(self.GIVER, self.PEER2)
        if high:
            self.act(self.GIVER, self.PEER2, "gift", arg="material", choice=high[0], amount=1)
        if tier4:
            self.act(self.GIVER, self.PEER2, "gift", arg="material", choice=tier4[0], amount=1)
        self.act(self.VIEW, self.PEER, "gift", arg="material", choice="nothing", amount=1)  # 沒有素材的人
        self.you(self.GIVER, "送完")
        self.world_view("贈物之後")

    def mingtie(self) -> None:
        """名帖：定稿的各種結果、遞帖、回帖、婉拒、沒有自己的名帖回不了、換新帖、同一版、一天遞滿。"""
        self.sync(self.MT_A, self.MT_B, self.MT_C)
        view = self.call(self.MT_A, "GET", "/api/mingtie")[1]
        pool = (view.get("pool") if isinstance(view, dict) else None) or []
        titles = [t if isinstance(t, str) else str(t) for t in pool[:1]]
        save = lambda who, **kw: self.call(who, "POST", "/api/mingtie/save", {"strokes": self.STROKES, "titles": [], "motto": "", **kw})  # noqa: E731
        save(self.MT_A, strokes=[[9, 9, 1, 1, 2, 2]])  # 畫壞了
        save(self.MT_A, titles=["沒有這個頭銜"])  # 頭銜不在池裡
        save(self.MT_A, strokes=[], titles=[], motto="")  # 空的
        save(self.MT_A, motto="這一句字數實在是太多太多太多太多太多了吧")  # 太長
        save(self.MT_A, titles=titles, motto="路過留名")
        save(self.MT_B, motto="山高水長")
        self.call(self.MT_A, "GET", "/api/mingtie")
        with self.tuned(self.c.config.mingtie, made_per_day=2):
            save(self.MT_B, motto="再改一次")
            save(self.MT_B, motto="第三次")  # 一天滿了
        self.card_of(self.MT_A, self.MT_B)
        self.card_of(self.MT_C, self.MT_B)  # 沒有名帖的人看有名帖的人
        # 遞帖：還沒遞過 → 遞；等回帖時再遞；回帖；同一版再遞；換新帖
        self.act(self.MT_A, self.MT_B, "mingtie", arg="send")
        self.act(self.MT_A, self.MT_B, "mingtie", arg="send")  # 還在等
        self.card_of(self.MT_B, self.MT_A)
        self.reply(self.MT_B, self.MT_A, "yes", "mingtie")
        self.act(self.MT_A, self.MT_B, "mingtie", arg="send")  # 他手上已經有這一版
        self.call(self.MT_A, "GET", "/api/mingtie")
        self.call(self.MT_B, "GET", "/api/mingtie")
        save(self.MT_A, motto="換個說法")  # 版本 +1
        self.act(self.MT_A, self.MT_B, "mingtie", arg="send")  # 換新帖
        self.act(self.MT_B, self.MT_A, "mingtie", arg="yes")  # 卡上回帖
        # 沒有自己名帖的人收到：回不了、只能婉拒
        self.act(self.MT_A, self.MT_C, "mingtie", arg="send")
        self.act(self.MT_C, self.MT_A, "mingtie", arg="yes")
        self.reply(self.MT_C, self.MT_A, "yes", "mingtie")
        self.act(self.MT_C, self.MT_A, "mingtie", arg="no")
        self.act(self.MT_C, self.MT_A, "mingtie", arg="send")  # 自己沒有名帖
        with self.tuned(self.c.config.mingtie, send_per_day=1):
            self.act(self.MT_A, self.PEER, "mingtie", arg="send")  # 一天遞滿
            self.card_of(self.MT_A, self.PEER2)
        self.act(self.MT_A, self.ELSE, "mingtie", arg="send")  # 不在這裡
        self.you(self.MT_A, "遞完帖")
        self.you(self.MT_B, "收了帖")
        self.world_view("名帖之後")

    def reports(self) -> None:
        """檢舉與管理者撤下、放回：自己的、找不到的、藏起來、滿了等管理者看、撤下、放回。"""
        self.sync(self.MT_A, self.MT_B)
        ver = (self.chars.load(self.MT_A).player.mingtie or type("X", (), {"version": 0})).version
        self.call(self.MT_B, "POST", "/api/mingtie/report", {"name": self.MT_A, "version": 999})  # 找不到
        self.call(self.MT_A, "POST", "/api/mingtie/report", {"name": self.MT_A, "version": ver})  # 自己的
        self.call(self.MT_B, "POST", "/api/mingtie/report", {"name": self.MT_A, "version": "x"})
        with self.tuned(self.c.config.mingtie, report_hide=2):
            self.call(self.MT_B, "POST", "/api/mingtie/report", {"name": self.MT_A, "version": ver})
            self.card_of(self.MT_B, self.MT_A)  # 自己檢舉過的只剩頭銜
            self.card_of(self.PEER, self.MT_A)
            self.call(self.MT_C, "POST", "/api/mingtie/report", {"name": self.MT_A, "version": ver})
            self.card_of(self.PEER, self.MT_A)  # 滿了：對所有人藏起來
            self.call(ADMIN, "GET", "/api/admin")
            self.do(ADMIN, "mingtie_restore", {"name": self.MT_A, "version": ver})
            self.card_of(self.PEER, self.MT_A)  # 放回：檢舉再多也照畫
            self.do(ADMIN, "mingtie_remove", {"name": self.MT_A, "version": ver})
            self.card_of(self.PEER, self.MT_A)  # 撤下
            self.call(self.MT_A, "GET", "/api/mingtie")
        self.do(ADMIN, "mingtie_remove", {"name": "無名氏", "version": 1})
        self.call(self.PEER, "POST", "/api/do/mingtie_remove", {"name": self.MT_A, "version": ver})  # 不是管理者
        self.call(self.MT_B, "POST", "/api/mingtie/bogus", {})  # 沒有這個動作
        self.you(self.MT_A, "被撤下")
        self.world_view("檢舉之後")

    def half(self) -> None:
        """前半停在邀請送出還沒接受：一張打招呼、兩張名帖（一張換新帖）、一張待逾時作廢的，與一張自己沒有名帖回不了的。"""
        self.sync(self.HALF_A, self.HALF_B, self.MT_A, self.MT_B, self.PEER2, self.VIEW)
        self.act(self.HALF_A, self.HALF_B, "greet", arg="taunt", text="後會有期")
        self.call(self.MT_A, "POST", "/api/mingtie/save", {"strokes": self.STROKES, "titles": [], "motto": "重新題字"})  # 撤下之後再寫一張
        self.act(self.MT_A, self.MT_B, "mingtie", arg="send")
        self.act(self.VIEW, self.PEER2, "greet", arg="taunt", text="等你回話")
        self.act(self.MT_A, self.HALF_B, "mingtie", arg="send")
        self.act(self.HALF_B, self.HALF_A, "mingtie", arg="send")  # 自己沒有名帖
        self.main(self.HALF_B)
        self.main(self.PEER2)
        self.you(self.HALF_B, "前半停在這裡")
        self.you(self.PEER2, "前半停在這裡")
        self.world_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        for who in (self.HALF_B, self.PEER2, self.MT_B, self.VIEW):
            self.main(who)

    def answer(self) -> None:
        """新程式接著答：選單上回禮、卡上回帖；作廢的那一張答不了；窗口外的人。"""
        self.sync(self.HALF_A, self.HALF_B, self.MT_A, self.MT_B, self.PEER2, self.VIEW)
        self.reply(self.HALF_B, self.HALF_A, "retort", "greet")
        self.act(self.MT_B, self.MT_A, "mingtie", arg="yes")  # 卡上回帖
        self.expire_all(self.VIEW)
        self.reply(self.PEER2, self.VIEW, "cold", "greet")
        self.choose(self.PEER2, "invite:cold:" + "0" * 12)  # 不在了的邀請
        self.reply(self.HALF_B, self.MT_A, "no", "mingtie")
        self.main(self.VIEW)
        for who in (self.HALF_A, self.HALF_B, self.MT_A, self.MT_B, self.PEER2, self.VIEW):
            self.you(who, "答完")
        self.world_view("接手之後")

    def bots(self) -> None:
        """假人：BotRunner 兩個（站在玩家站的地方）收到打招呼與名帖、自己做名帖、向此地的人遞帖；整季機器人眼前有邀請時的選單與挑法。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        hub = self.hub()
        for who in self.PLAYERS:
            if who != self.BOT_HUMAN:
                self.place(who, self.elsewhere())  # 假人只跟這一位真人同地
        self.place(self.BOT_HUMAN, hub)
        on = any(f.id == "guan" for f in self.c.scenario.factions)
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, hub, None
            p.visited.add(p.location)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        self.call(self.BOT_HUMAN, "POST", "/api/mingtie/save", {"strokes": self.STROKES, "titles": [], "motto": "兩位請了"})
        for name in self.BOT_SEATS:
            self.card_of(self.BOT_HUMAN, name)  # 假人的卡跟真人的一樣
        self.act(self.BOT_HUMAN, self.BOT_SEATS[0], "greet", arg="taunt", text="來比劃比劃")
        self.act(self.BOT_HUMAN, self.BOT_SEATS[1], "mingtie", arg="send")
        self.backdate(self.BOT_HUMAN)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(41), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_PEERS_TICKS", "8"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            self.you(name, "假人之後")
        self.you(self.BOT_HUMAN, "假人之後")
        self.call(self.BOT_HUMAN, "GET", "/api/mingtie")
        self.main(self.BOT_HUMAN)
        for name in self.BOT_SEATS:
            self.card_of(self.BOT_HUMAN, name)
        self.world_view("假人之後")
        # 整季機器人眼前有人遞來的邀請：選單上有 invite:，挑法不按它（bot.pick 排除）
        self.place(self.PEER2, hub)
        self.sync(self.PEER2, self.BOT_HUMAN)
        self.act(self.BOT_HUMAN, self.PEER2, "greet", arg="taunt")
        self.begin()
        solo = self.server.game_for(self.PEER2)
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單（有邀請）", [o.id for o in opts])
        emit("整季機器人挑的（有邀請）", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(30)}))

    def season(self) -> None:
        """收季、開下一季：邀請整個重來、名帖跨季帶著走（名帖匣標季）、贈物次數跟著新角色。"""
        self.do(ADMIN, "end_season")
        self.world_view("收季之後")
        self.do(ADMIN, "next_season")
        for who in (self.MT_A, self.MT_B, self.GIVER, self.VIEW, self.HALF_B):
            self.main(who)
            self.you(who, "換季之後")
        self.call(self.MT_A, "GET", "/api/mingtie")
        self.call(self.MT_B, "GET", "/api/mingtie")
        self.world_view("換季之後")


# 改一個字（selftest）：不接他的挑釁話那一句（social.MUTED；搬之前在 tianxia/social.py，搬進包之後 Task 3 把包裡的檔補進這張清單），week7 greet 那一段抓到
register_track("peers", PeersScenario, (("tianxia/social.py", "tianxia/features/peers/social.py"), ("那一句你不會看到。", "那一句你不會看到！")), "week7")
