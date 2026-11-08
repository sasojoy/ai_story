"""same_behavior 一軌一檔：levy（這一檔登記 levy）。"""
from __future__ import annotations

import random
from pathlib import Path

from sb.harness import CLOCK, emit, register_track
from sb.tracks.companions import CompanionsScenario, GameStateHolder
from sb.tracks.reckon import ReckonScenario

# ═══════════════════════════ core_seams（全部拆包第 57 批：分派與標題收接縫，act 子動詞帶後綴、公開的路走不到的那幾格） ═══════════════════════════
class LevyScenario(CompanionsScenario):
    """act 子動詞裡現有的軌走不到的那幾格一軌（全部拆包第 57 批；--track levy，自己一個資料庫）。借 companions 的 setup、seat 與小工具。
    開工那一筆 53 軌 × 三種設定逐一量過（記 Game._act 收到的 what）：act:recruit:<人物>（按下去、紀錄標題、FB-363）與 act:rest 沒有任何一軌走到——season21、week7 是五項屬性的季，
    歷史武將不同行（roster.on），companions 一軌招募那一段的鈕是空的；測試內容沒有十五位；調息那一顆序章才有。其餘子動詞都有軌走到（計畫第七節那張表）。
    這一軌在記憶體裡關掉五項屬性、打開歷史武將同行；測試內容把舊招募那幾位標成 recruitable、deep_interaction（兩個行程都做，不寫輸出）。

    前半切在 half：褚明遠按了一次招募被婉拒（「招募・某某」那一則是舊程式寫的）；測試內容的沈硯冰按了求見、名單開著。後半新程式接手（實跑讀過輸出）：
    - recruit_on：沈硯冰按返回；褚明遠再按一次被要求決鬥，再按到招到（季上 owners 記他、紀錄標題「招募・某某」）。
    - taken：葉聽瀾站到有主那一位旁邊，鈕不在選單上卻還按，回「【某某】已經被褚明遠招攬走了」（FB-363，Refused）；不認得的 id 照舊「此刻無法」；站到第二位旁邊：正式內容那一位只追隨官軍，
      鈕灰掉、按了「此刻無法」；測試內容沒寫陣營，照常招。
    - rest_door：沈硯冰在鎖裡走 choose（換掉 prologue.instant_rest，同 tests/conftest.py；同 guide 一軌在鎖裡直接叫 _rest），選單上有 act:rest、回那一句、標題「調息・此地」，不存。
    - machines：兩位假人站在第二位旁邊、情誼到門檻（正式內容官軍那位鈕亮、黃巾那位灰掉）：整季機器人（bot.pick）六顆種子都不挑 act:recruit:<人物>（測試內容會挑到舊的 act:recruit）；
      BotRunner 三輪（正式內容才出手）之後 owners 裡沒有他們。

    **這一軌走不到的**（實跑讀過）：正式內容這時候沒有兩位以上人物站著的地方，沈硯冰那一段沒有鈕、按了「此刻無法」、call:back 也是（act:call 是 here、socialize 兩軌走到）；
    舊招募那一顆（act:recruit）測試內容這裡只畫不按（companions 等四軌按）；測試內容沒有陣營，假人不上線、站到第二位旁邊的那一段照樣印。"""

    RECRUITER, RIVAL, DRIFTER, PREP = "褚明遠", "葉聽瀾", "沈硯冰", "方遠岑"
    PLAYERS = {RECRUITER: "guan", RIVAL: "huang", DRIFTER: None}
    BOT_SEATS = ["徵甲", "徵乙"]
    PHASES_FIRST = ["setup", "seat", "warm", "half"]
    PHASES_SECOND = ["resume", "recruit_on", "taken", "rest_door", "machines"]
    REST_LINE = "（調息：一坐就回滿。）"

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        cfg = self.c.config
        cfg.attributes.v2.enabled = False  # 五項屬性的季歷史武將不同行（roster.on）：記憶體裡關掉才招得到（兩個行程都關，不寫輸出）
        cfg.companions.enabled = True
        chars = self.c.characters
        named = sorted(cid for cid, ch in chars.items() if ch.recruitable)
        self.old_book = not named  # 測試內容沒有十五位：把舊招募（recruit_at）那幾位也標成 recruitable，同一地點兩種鈕都畫得出來
        if self.old_book:
            named = sorted(cid for cid, ch in chars.items() if ch.kind == "recruitable")
            for cid in named:
                chars[cid] = chars[cid].model_copy(update={"recruitable": True, "deep_interaction": True})
        self.named = named
        self.first = next((cid for cid in named if chars[cid].side == "guan"), named[0])
        self.second = next((cid for cid in named if cid != self.first and chars[cid].side == "guan"), next((cid for cid in named if cid != self.first), self.first))

    def stand(self, who: str, cid: str) -> None:
        """站到這一位旁邊：正式內容照他此刻在的地方（beside），測試內容照 recruit_at。"""
        if self.old_book:
            self.place(who, self.c.characters[cid].recruit_at)
        else:
            self.beside(who, cid)

    def crowded(self) -> str | None:
        """照地點名排第一個有兩位以上人物站著的地方（行動列上才有 act:call，同 socialize 一軌的 open_list）：拿一份不存的 Game 換地點問 _figures_here。"""
        from tianxia.engine import Game

        g = Game(self.c, self.chars.load(self.DRIFTER), random.Random(0), self.world)
        g.state.world = self.world.get_season()
        for loc in sorted(self.c.locations):
            g.state.player.location = loc
            if len(g._figures_here()) >= 2:
                return loc
        return None

    def titles(self, who: str, tag: str) -> None:
        emit(f"{who} {tag}：最新三則紀錄的標題", [e.title for e in self.chars.load(who).journal[:3]])

    def warm(self) -> None:
        """三個人的情誼補到招募門檻，按鈕才畫得出來（roster.affinity_ok）；褚明遠站到第一位旁邊。"""
        need = self.c.config.recruit_min_affinity
        for who in self.PLAYERS:
            self.edit(who, lambda p: p.affinities.update({cid: need for cid in self.named}))
        self.stand(self.RECRUITER, self.first)
        emit("第一位旁邊的招募鈕", self.buttons(self.RECRUITER, "act:recruit"))

    def half(self) -> None:
        """前半切在這裡：褚明遠按了一次招募被婉拒（那一則的標題是舊程式寫的），沈硯冰的求見名單開著（act:call，picking_audience）還沒按任何一顆。"""
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=0.0):
            self.choose(self.RECRUITER, f"act:recruit:{self.first}")
        self.me(self.RECRUITER, "招募被婉拒")
        self.place(self.DRIFTER, self.crowded())
        emit("沈硯冰的求見鈕", self.buttons(self.DRIFTER, "act:call"))
        self.choose(self.DRIFTER, "act:call")
        self.titles(self.DRIFTER, "按了求見")

    def resume(self) -> None:
        self.login_all()

    def recruit_on(self) -> None:
        """新程式接手：舊程式開著的求見名單按返回；褚明遠再按一次被要求決鬥、再按到招到（名下、標題「招募・某某」）。"""
        who, first = self.RECRUITER, self.first
        self.choose(self.DRIFTER, "call:back")
        self.titles(self.DRIFTER, "收回名帖")
        self.titles(who, "舊程式寫的")
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=1.0):
            self.choose(who, f"act:recruit:{first}")
        self.me(who, "招募被要求決鬥")
        with self.tuned(recruit_base_chance=9.0):
            for _ in range(4):
                if self.world.get_companion(first).owner is not None:
                    break
                self.stand(who, first)
                self.choose(who, f"act:recruit:{first}")
            self.me(who, "招到一位")
            self.season_view("招到之後")
            emit("招到之後的招募鈕", self.buttons(who, "act:recruit"))

    def taken(self) -> None:
        """慢一步（FB-363）：葉聽瀾站到有主的那一位旁邊，鈕不在選單上卻還按，回「已經被某某招攬走了」（Refused）；不認得的 id 照舊「此刻無法」；
        站到第二位旁邊：正式內容只追隨官軍，灰掉，按了「此刻無法」；測試內容沒寫陣營，照常招。"""
        who = self.RIVAL
        self.stand(who, self.first)
        emit("有主那一位旁邊的招募鈕", self.buttons(who, "act:recruit"))
        self.choose(who, f"act:recruit:{self.first}")
        self.choose(who, "act:recruit:nobody")
        self.stand(who, self.second)
        emit("第二位旁邊的招募鈕", self.buttons(who, "act:recruit"))
        with self.tuned(recruit_base_chance=9.0):
            self.choose(who, f"act:recruit:{self.second}")
        self.me(who, "按第二位")
        self.season_view("都按完")

    def rest_door(self) -> None:
        """act:rest（序章教體力那一步的調息）：正式內容的草廬已經沒有那一步，公開的路走不到。同 guide 一軌在鎖裡直接叫，只是這裡走 choose（照 tests/conftest.py 換掉
        prologue.instant_rest）：選單上那一顆、按下去的回話、那一下江湖紀錄的標題、體力，不存。"""
        from unittest import mock

        from tianxia.engine import Game

        with self.world.action_lock():
            g = Game(self.c, self.chars.load(self.DRIFTER), random.Random(0), self.world)
            g.state.player.stamina = 0.0
            with mock.patch("tianxia.prologue.instant_rest", return_value=self.REST_LINE):
                emit("調息那一顆", [o.id for o in g.options(odds=False) if o.id == "act:rest"])
                emit("按調息", g.choose("act:rest"))
            emit("調息之後", [g.state.journal[0].title, g.state.player.stamina])

    def machines(self) -> None:
        """假人碰得到：兩位假人站在第二位旁邊、情誼到門檻（招募鈕在選單上）。BotRunner 三輪；整季機器人（bot.pick）再挑一次（照常避開 act:recruit:<人物>，測試內容照挑舊的 act:recruit）。"""
        from tianxia import bot
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        need = self.c.config.recruit_min_affinity
        at = self.c.characters[self.second].recruit_at if self.old_book else None
        if at is None:
            from tianxia import figure_life

            at = figure_life.where(GameStateHolder(self.world.get_season()), self.c, self.second)
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=sides[i % 2] if sides else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, at, None
            p.visited.add(at)
            p.affinities.update({cid: need for cid in self.named})
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        for name in self.BOT_SEATS:
            self.begin()
            g = Game(self.c, self.chars.load(name), random.Random(0), self.world)
            g.client = None
            options = g.options(odds=False)
            emit(f"{name} 站在第二位旁邊", {"recruit": [[o.id, o.enabled] for o in options if o.id.startswith("act:recruit")],
                                       "pick": [bot.pick(g, options, random.Random(i)) for i in range(6)]})
        ReckonScenario.bot_rounds(self, 3)
        for name in self.BOT_SEATS:
            state = self.chars.load(name)
            emit(f"{name} 三輪之後", {"at": state.player.location, "journal": [e.title for e in state.journal[:3]]})
        self.season_view("假人之後")


# 改一個字（selftest）：招募某一位那一下的紀錄標題（第 57 批第 2 段從 engine._action_title 搬進人物情誼包 __init__.py 的 Verb，那一行寫 f"招募・{ctx.content.characters[tail].name}"；搬到別的檔就補這裡的檔清單）
register_track("levy", LevyScenario, (("tianxia/engine.py", "tianxia/features/companions/__init__.py"), ("招募・{c", "招募！{c")), "season21",
               covers=("battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction", "figure_acts",
                       "gear", "guide", "looks", "military", "outlets", "peers", "seal", "seclusion", "sense", "smithy",
                       "socialize", "sortie", "stamina_plays", "story", "tavern", "travel", "zhuan"))
