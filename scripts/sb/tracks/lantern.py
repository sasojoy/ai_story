"""same_behavior 一軌一檔：lantern（這一檔登記 lantern）。"""
from __future__ import annotations

from sb.base import Scenario
from sb.harness import emit, register_track

# ── core_views（第二輪第 81 批：畫面搬出 engine）──────────────────────────


class LanternScenario(Scenario):
    """狀態列的文字版一軌（第二輪第 81 批；--track lantern，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    這一批把畫面搬進 core/status_view.py、core/page_view.py，別的軌經 /api/main 都走到了（照分支量過，第 81 批計畫第五節）；
    只有 Game.status_text 與 _when_text 沒有路由（server 不叫，只有測試寫到），這一軌直接拿 Game 在鎖裡讀 status_text，三種設定各讀一輪：
    平常（season21、week7 寫季曆那一句與心得的提示；測試內容寫「第 N 天 HH:MM（本季共 M 天）」、沒有提示）、內傷、匿名、閉關中、按了前往之後的在路上。
    帶人那一行只有測試內容走到：season21、week7 讀到的隊伍是空的（status_data 的 team 由 battle、companions 兩軌走到）。
    半舊半新：status_text 只讀不寫，沒有寫到一半的狀態。切在按了前往、存檔裡還在路上的那一刻；後半第一件事是重新登入（三步），接回來那一筆已經到了。
    這一軌走不到的：籌備中、休季的 status_text。假人：碰不到（假人的 bot 三支不讀 status_text），所以沒有假人段。"""

    PLAYERS = {"溫若拙": None}
    NEWBIE = "葉聽瀾"
    PHASES_FIRST = ["setup", "plain", "hurt", "hidden", "mates", "retreat", "road", "half"]
    PHASES_SECOND = ["resume", "still_on_road", "plain_again"]
    GUEST = "溫若拙"

    def read(self, who: str, tag: str) -> None:
        """Game.status_text 沒有路由叫它（server 不用），直接拿 Game 在鎖裡讀一次。"""
        self.begin()
        game = self.server.game_for(who)
        with self.server._locked(game):
            emit(f"{who} {tag} status_text", game.status_text())

    def plain(self) -> None:
        for who in (self.GUEST, self.NEWBIE):
            self.read(who, "平常")

    def hurt(self) -> None:
        def fn(p) -> None:
            p.member.injury = 2.0

        self.edit(self.GUEST, fn)
        self.read(self.GUEST, "內傷")

    def hidden(self) -> None:
        def fn(p) -> None:
            p.anonymous = True

        self.edit(self.GUEST, fn)
        self.read(self.GUEST, "匿名")

    def mates(self) -> None:
        mate = sorted(self.c.characters)[0]

        def fn(p) -> None:
            p.team = [mate]

        self.edit(self.GUEST, fn)
        self.read(self.GUEST, "帶人")

    def retreat(self) -> None:
        with self.world.action_lock():
            state = self.chars.load(self.GUEST)
            state.player.busy_until = state.world.time + 86400.0
            self.chars.save(state)
        self.read(self.GUEST, "閉關中")

        def fn(p) -> None:
            p.busy_until = None

        self.edit(self.GUEST, fn)

    def road(self) -> None:
        view = self.main(self.GUEST)
        target = next((i for i, o in self.ids(view).items() if i.startswith("move:") and o.get("enabled")), None)
        emit("走的那一顆", target)
        if target is not None:
            self.choose(self.GUEST, target)
        self.read(self.GUEST, "按了前往")

    def half(self) -> None:
        self.main(self.GUEST)

    def resume(self) -> None:
        self.login_all()

    def still_on_road(self) -> None:
        self.read(self.GUEST, "接回來")

    def plain_again(self) -> None:
        self.read(self.NEWBIE, "接回來")
        self.main(self.GUEST)


# 改一個字（selftest）：閉關那一行（第 81 批從 engine.py 搬到 core/status_view.py，兩處找）
register_track("lantern", LanternScenario, (("tianxia/core/status_view.py", "tianxia/engine.py"), ("🧘 閉關中，現實約 ", "🧘 閉關中，現實大約 ")), "season21",
               covers=("battle", "bounties", "bout", "companions", "cultivation", "explore", "faction", "figure_acts", "gear", "guide",
                       "map", "military", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "travel", "zhuan"))
