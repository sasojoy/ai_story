"""same_behavior 一軌一檔：redress（這一檔登記 redress）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── core_imports（第二輪第 98 批：engine 對包的 import 清到零）─────────────────────


class RedressScenario(Scenario):
    """序章那一場的戰報標題一軌（第二輪第 98 批；--track redress，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    這一批把 _squad_encounter 收進 core/combat.py，那一段別的軌走到了，只差一行（aftermath week7、train season21 與 test、roam week7、strip season21 合起來量過）：
    「站在草廬、序章沒走完、而且有地盤」才把戰報標題寫成雪恥。season21、week7 的新人走開局第一分鐘、不進草廬，所以沒有軌走到它；
    這一批正好要改那一行（sortie.on 換 territory.on、PROLOGUE_FIGHT 的字搬進核心）。這一軌在記憶體裡把人擺回草廬，走到它。
    測試內容沒有草廬：寫「沒有」略過擺人那一步，同一串動作照打，標題是舊的。
    四種打法：照寫好的險勝（act:train）、照寫好的落敗（把那一步的結果在記憶體裡換掉）、沒寫死的一步（Game._squad_encounter，走判讀與地形、武學的註腳）、
    同一處的野怪（wild）與出陣的攻（as_sortie）；最後出了草廬再打一場對照（標題回到平常的）。
    半舊半新：切在險勝打完、戰報已經寫進存檔、序章往下走了一步的那一刻；後半第一件事重新登入、新程式讀舊程式寫的戰報，再打一場。
    這一軌走不到的：判讀真的回來的那一支（這一軌沒有走鎖外三段式）。假人：碰不到（season21、week7 的假人站在城門口，不進草廬），所以沒有假人段；
    _squad_encounter 其餘的路歸 aftermath、train 兩軌的假人段。"""

    PLAYERS = {"陶照野": None, "石見微": None, "阮青梧": None, "聶行舟": None}
    NEWBIE = "沈不語"
    SCRIPTED, OPEN, ROUGH, LOST = "陶照野", "石見微", "阮青梧", "聶行舟"
    PHASES_FIRST = ["setup", "scripted", "half"]
    PHASES_SECOND = ["resume", "reread", "open_step", "wild_here", "sortie_here", "lost", "away"]

    # ── 小工具 ──

    def foe(self) -> str:
        """中立的對手（不會變成跟自家操練）：名字排最前面的那一支。"""
        return next(i for i, squad in sorted(self.c.squads.items()) if squad.faction is None)

    def hut(self, who: str, forced: bool) -> bool:
        """把人擺回草廬、停在序章的某一步：forced 是寫好結果的那一步（雪恥），否則是序章第一步。沒有草廬的內容回 False。"""
        t = self.c.tutorial
        if t.location is None:
            emit(f"{who}：這份內容沒有草廬", None)
            return False
        index = next(i for i, step in enumerate(t.steps) if step.force_tier) if forced else 0

        def fn(p) -> None:
            p.location, p.tutorial_step, p.journey = t.location, index, None

        self.edit(who, fn)
        return True

    def latest(self, who: str, tag: str) -> None:
        battles = self.chars.load(who).battles  # 新的排在前面
        emit(f"{who} {tag} 戰報的標題", [b.label for b in battles])
        emit(f"{who} {tag} 最新一份", None if not battles else battles[0].model_dump(mode="json"))

    def strike(self, who: str, tag: str, **kw) -> None:
        """直接打一場（Game._squad_encounter 沒有路由叫它：server 走 act:train，這幾種打法要指定 wild、as_sortie）。"""
        self.begin()
        msgs = self.server.act(self.server.game_for(who), lambda g: g._squad_encounter(self.foe(), **kw))
        emit(f"{who} {tag} 回話", msgs)
        self.latest(who, tag)

    # ── 段落 ──

    def scripted(self) -> None:
        self.hut(self.SCRIPTED, True)
        emit("雪恥那一顆", self.ids(self.main(self.SCRIPTED)).get("act:train"))
        self.choose(self.SCRIPTED, "act:train")
        self.latest(self.SCRIPTED, "照寫好的險勝")

    def half(self) -> None:
        self.main(self.SCRIPTED)

    def resume(self) -> None:
        self.login_all()

    def reread(self) -> None:
        self.call(self.SCRIPTED, "GET", "/api/reports")
        self.main(self.SCRIPTED)
        self.strike(self.SCRIPTED, "接回來再打一場")

    def open_step(self) -> None:
        self.hut(self.OPEN, False)
        self.strike(self.OPEN, "沒寫死的一步")

    def wild_here(self) -> None:
        self.hut(self.ROUGH, False)
        self.strike(self.ROUGH, "同一處的野怪", wild=True)

    def sortie_here(self) -> None:
        self.hut(self.ROUGH, False)
        self.strike(self.ROUGH, "同一處出陣的攻", as_sortie=True)

    def lost(self) -> None:
        if not self.hut(self.LOST, True):
            self.strike(self.LOST, "沒有草廬照打")
            return
        step = next(s for s in self.c.tutorial.steps if s.force_tier)
        before, step.force_tier = step.force_tier, "落敗"
        try:
            self.choose(self.LOST, "act:train")
        finally:
            step.force_tier = before
        self.latest(self.LOST, "照寫好的落敗")

    def away(self) -> None:
        here = sorted(i for i, loc in self.c.locations.items() if i != self.c.tutorial.location and loc.enemies)[0]

        def fn(p) -> None:
            p.location, p.tutorial_step = here, self.c.tutorial.prologue_steps

        self.edit(self.OPEN, fn)
        self.strike(self.OPEN, "出了草廬")


# 改一個字（selftest）：序章那一場的字（第 98 批從 features/sortie/rules.py 搬到 core/services.py，兩處找），雪恥那一顆與戰報的標題都抓到
register_track("redress", RedressScenario, (("tianxia/core/services.py", "tianxia/features/sortie/rules.py"),
                                            ('PROLOGUE_FIGHT = "雪恥"', 'PROLOGUE_FIGHT = "雪恨"')), "season21",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
