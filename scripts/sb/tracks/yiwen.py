"""same_behavior 一軌一檔：yiwen（這一檔登記 yiwen）。"""
from __future__ import annotations

from sb.harness import ADMIN, emit, register_track
from sb.tracks.peers import PeersScenario

# ── yiwen（異聞第 247 批；開關 Config.yiwen.enabled 預設關＋開季蓋章 WorldState.yiwen_on）：異聞一之一 ──────────────


class YiwenScenario(PeersScenario):
    """異聞的一軌（第 247 批；--track yiwen，自己一個資料庫）。借 peers 一軌的小工具（edit_state、begin 清榜單快取）。班底的名字都是原創。
    關著段（記憶體裡把開關關掉）：探索一段、/api/do/yiwen_step 回空、讀 /api/main 的 yiwen 鍵與存檔那一格。
    開著段（記憶體裡打開、這一季補蓋章、撞見機率調成 1）：甲在野地探索撞見、撞見卡、三步都按第一顆（每一幕是替身）、收起。
    後半第一件事無條件重新登入、再打開：乙在同一處重走（重走機率調成 1）、三步重放（回聲、第一步的朱批、同一個圓章）、別人沒走過的那一顆鎖著；
    收季、開下一季：眼前那一則清空、下一季照開關蓋章。
    這一軌走不到的：測試內容（test 設定）走舊探索，撞不到異聞（總計畫「對不上的」第 13 條）：那一種設定兩邊照樣一樣；
    模型（異聞二）、岔路與道具（異聞三）、定論與逾時（異聞四）。"""

    LEAD, TRAIL = "霜橋客", "柳岸生"
    PLAYERS = {LEAD: None, TRAIL: None}
    NEWBIE = "遠客"
    PHASES_FIRST = ["setup", "seat", "closed", "meet", "walk"]
    PHASES_SECOND = ["resume", "trail", "season"]

    def switch(self, on: bool) -> None:
        t = self.c.config.yiwen
        t.enabled = on
        t.discover_chance = 1.0 if on else 0.0002
        t.rewalk_chance = 1.0 if on else 0.07
        if on:
            self.world.mutate(lambda st: setattr(st.season, "yiwen_on", True))

    def wild(self) -> str:
        from tianxia.core import explore_base

        if "yingchuan_wilds" in self.c.locations:  # 正式內容：潁川郊野（野地，沒有決戰的大區）
            return "yingchuan_wilds"
        return next((lid for lid, loc in sorted(self.c.locations.items()) if explore_base.kind_of(self.c.config.jianfa, loc).kind == "wild"),
                    self.hub())

    def yiwen_of(self, who: str, tag: str) -> None:
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        emit(f"{who} {tag}：main.yiwen", main.get("yiwen") if isinstance(main, dict) else None)
        w = self.chars.load(who).player.yiwen
        emit(f"{who} {tag}：存檔", w.model_dump(mode="json") if w is not None else None)
        emit(f"{who} {tag}：選單", sorted(i for i in self.ids(main) if i.startswith("yiwen:")))

    def card(self, who: str):
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        y = main.get("yiwen") if isinstance(main, dict) else None
        return y.get("card") if isinstance(y, dict) else None

    def explore(self, who: str) -> None:
        self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
        if "act:explore" not in self.ids(self.main(who)):
            emit(f"{who} 選單上沒有探索", sorted(self.ids(self.main(who)))[:20])
            return
        emit(f"{who} 探索", self.choose(who, "act:explore"))

    def steps(self, who: str, picks=(0, 0, 0)) -> None:
        for i in picks:
            card = self.card(who)
            if card is None:
                emit(f"{who} 沒有撞見卡", None)
                return
            body = {"tale": card["tale"], "opening": card["opening"], "node": card["node"], "pick": i}
            emit(f"{who} 按第 {i} 顆", self.do(who, "yiwen_step", body))
            emit(f"{who} 那一張卡", self.card(who))

    # ── 段落 ──

    def seat(self) -> None:
        here = self.wild()
        for who in self.PLAYERS:
            self.place(who, here)
            self.edit(who, lambda p: setattr(p.member, "level", 20))
        emit("坐在", here)
        for who in self.PLAYERS:
            self.main(who)

    def closed(self) -> None:
        self.switch(False)
        self.explore(self.LEAD)
        emit("關著按 yiwen_step", self.do(self.LEAD, "yiwen_step", {"tale": 1, "opening": "fog_figure", "node": 0, "pick": 0}))
        self.yiwen_of(self.LEAD, "關著")

    def meet(self) -> None:
        self.switch(True)
        self.c.config.guard.enabled = False  # 親衛隊長第一段就撞見那個孩子（接管選單）：這一軌只看異聞
        self.explore(self.LEAD)
        self.yiwen_of(self.LEAD, "撞見")

    def walk(self) -> None:
        self.steps(self.LEAD)
        self.yiwen_of(self.LEAD, "走完")
        emit("收起", self.choose(self.LEAD, "yiwen:drop"))
        self.yiwen_of(self.LEAD, "收起")

    def resume(self) -> None:
        # 後半是另一個行程：記憶體裡的設定先照前半收尾的樣子擺回去（不打請求），再無條件重新登入
        self.c.config.yiwen.enabled = True
        self.c.config.yiwen.discover_chance = 0.0
        self.c.config.yiwen.rewalk_chance = 1.0
        self.c.config.guard.enabled = False
        self.login_all()

    def trail(self) -> None:
        self.explore(self.TRAIL)
        self.yiwen_of(self.TRAIL, "重走")
        card = self.card(self.TRAIL)
        if card is not None:
            emit("別人沒走過的那一顆", self.do(self.TRAIL, "yiwen_step", {"tale": card["tale"], "opening": card["opening"], "node": 0, "pick": 1}))
        self.steps(self.TRAIL)
        self.yiwen_of(self.TRAIL, "重走完")

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.main(self.TRAIL)
        self.do(ADMIN, "next_season")
        self.yiwen_of(self.TRAIL, "下一季")
        emit("下一季的章 yiwen_on", getattr(self.world.get_season(), "yiwen_on", None))


# 改一個字（selftest）：重走的擲骰反過來，乙永遠撞不到那一則，season21 trail 那一段抓到
register_track("yiwen", YiwenScenario, (("tianxia/features/yiwen/actions.py",), ("if old and r_walk < t.rewalk_chance:", "if old and r_walk > t.rewalk_chance:")),
               "season21", covers=("yiwen", "explore"))
