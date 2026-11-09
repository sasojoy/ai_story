"""same_behavior 一軌一檔：primer（這一檔登記 primer）。"""
from __future__ import annotations

import contextlib

from sb.harness import ADMIN, emit, register_track
from sb.tracks.shut import ShutScenario
from sb.tracks.socialize import SocializeScenario
from sb.tracks.strip import StripScenario

# ═══════════════════════════ primer：玩法說明（全部拆包第 59 批，dev/guide-howto） ═══════════════════


class PrimerScenario(StripScenario):
    """玩法說明（全部拆包第 59 批；--track primer，自己一個資料庫）。平常的 /api/howto、status 的 stamina_help 與 war_help、行動列底下探索、出陣、交友那幾行，
    strip、shut、sortie、duel 幾軌已經走到；這一軌補它們走不到的兩塊。
    一、說明頁不看個人、只看內容與這一季，三種設定各只走得到一條路：pages 換一批記憶體裡的設定（兩份程式同一步換、同一步換回），每一種打一次 /api/howto、讀一次狀態列的兩份說明。
    二、行動列底下「求見」那幾行（只有一位人物時的 call:<人物>、兩位以上的 act:call）：一類一顆開著的季沒有這兩顆、測試內容沒有大勢人物，所以別的軌一次也沒走到。doors 把一類一顆
    關掉（測試內容另外把三位人物擺成大勢人物），名望夠、名望不夠、談滿、閉門不見、名單開著各看一次。
    半舊半新切在 half：名單開著（行動列底下不寫 call: 那幾行）、舊角色的回體丹還沒補（讀檔那一刻才補、才寫那一行）；後半第一件事是新程式接手；還有新人建角色那一行新手福利。
    假人：說明頁與行動列底下那幾行都是 server 才讀，假人碰得到的只有建角色那一行，bots 照拿掉一那一軌走一遍、紀錄標題與存檔都寫。
    這一軌走不到的（要假的比重或內容，pytest 守）：見計畫 docs/superpowers/plans/2026-11-06-玩法說明-第59批.md 第七節。"""

    OPENER, LISTER, TOPPED, RANGER = "溫如晦", "柏青崖", "鮑遲暮", "籍長風"
    ARRIVAL, ARRIVAL2 = "甄小滿", "蓋聽瀾"  # 後半才建角色
    PLAYERS = {OPENER: "guan", LISTER: "guan", TOPPED: "huang", RANGER: None}
    NEWBIE = "晏初晴"
    BOT_SEATS = [("燈甲", "yingshui"), ("燈乙", "yingchuan")]
    PHASES_FIRST = ["setup", "pages", "doors", "half"]
    PHASES_SECOND = ["resume", "taken_over", "pages", "doors", "arrival", "bots", "season"]

    layout = SocializeScenario.layout
    hall_spot = SocializeScenario.hall_spot
    alone_spot = SocializeScenario.alone_spot
    fame = SocializeScenario.fame
    fresh = ShutScenario.fresh

    # ── 小工具 ──

    def tunes(self) -> list[tuple[str, list[tuple[object, dict]]]]:
        """說明頁的每一種：(叫法, [(設定物件, 換成什麼), …])。"""
        c = self.c.config
        return [
            ("一類一顆關著", [(c, {"precise_actions": False})]),
            ("約戰關著", [(c.jianfa, {"sortie_duel": False})]),
            ("探索一顆關著", [(c.jianfa, {"explore_one": False})]),
            ("減法季的閘關著", [(c.jianfa, {"drill_gates": False, "stat_milestones": False})]),
            ("屬性五段開著", [(c.jianfa, {"drill_gates": True, "stat_milestones": True})]),
            ("名聲關著", [(c.renown, {"titles": False})]),
            ("第一季規則關著", [(c, {"season_one": False})]),
            ("地盤關著", [(self.c.scenario, {"territory": None})]),
            ("新手期照季曆", [(c, {"newbie_real_hours": 0, "newbie_stamina_multiplier": 2.0})]),
            ("新手期回復加快", [(c, {"newbie_real_hours": 48, "newbie_stamina_multiplier": 2.0})]),
            ("新手期沒有好處", [(c, {"newbie_real_hours": 48, "newbie_stamina_multiplier": 1.0, "newbie_pills_per_day": 0}), (c.raid, {"enabled": False})]),
            ("一鍵補滿", [(c, {"beta_free_refill": True})]),
            ("回體丹關著", [(c, {"stamina_pills_per_day": 0})]),
            ("兵器防具關著", [(c.weapons, {"enabled": False}), (c.armor, {"enabled": False})]),
            ("素材四階關著", [(c.four_tiers, {"enabled": False})]),
            ("商城關著", [(c.mall, {"enabled": False})]),
            ("酒肆關著", [(c.tavern, {"enabled": False})]),
            ("設伏關著", [(c.ambush, {"enabled": False})]),
            ("玉璽關著", [(c.seal, {"enabled": False})]),
            ("意境最濃與地利關著", [(c.insight_strong, {"enabled": False}), (c.terrain_arts, {"enabled": False})]),
            ("兩份意境的算法換了", [(c.arts, {"stack_share": 0.4, "stack_ceiling": 2.0}), (c.sortie, {"hold_share": 0.3})]),
            ("挑戰本人的數字都是零", [(c, {"figure_prestige_regen": 0, "figure_daily_loss_cap": 0, "snub_hours": 0, "figure_draw_share": 0}), (c.rise, {"enabled": False})]),
            ("破境丹撿不到", [(c, {"explore_legend_chance": 0})]),
            ("殘譜與線索的開關關著", [(c.forge_secrets, {"split_clues": False, "scrap_every_mode": False})]),
        ]

    @contextlib.contextmanager
    def tuned_all(self, rows: list[tuple[object, dict]]):
        """幾個設定物件一起換（這份內容沒有那一格的略過：測試內容少幾樣），出來照原樣還原。"""
        saved = [(o, {k: getattr(o, k) for k in vals if hasattr(o, k)}) for o, vals in rows]
        emit("這一下的設定", [sorted(vals.items(), key=str) for _, vals in rows])
        for (o, vals), (_, old) in zip(rows, saved):
            for k in old:
                setattr(o, k, vals[k])
        try:
            yield
        finally:
            for o, old in saved:
                for k, v in old.items():
                    setattr(o, k, v)

    @contextlib.contextmanager
    def stamped(self, **values):
        """這一季開季蓋的章這幾步換掉（改資料庫，兩份程式同一步換、同一步換回）。"""
        with self.world.action_lock():
            season = self.world.get_season()
            old = {k: getattr(season, k) for k in values}
            for k, v in values.items():
                setattr(season, k, v)
            self.world.save_season(season)
        emit("這一季的章", sorted(values.items()))
        try:
            yield
        finally:
            with self.world.action_lock():
                season = self.world.get_season()
                for k, v in old.items():
                    setattr(season, k, v)
                self.world.save_season(season)

    def read_help(self, who: str, tag: str) -> None:
        """玩法說明那一頁（/api/howto）與狀態列點開的兩份說明（stamina_help、war_help；第一季才有 war_help）。"""
        self.call(who, "GET", "/api/howto")
        self.begin()
        status = self.game(who).status_data()
        emit(f"{who} {tag} 狀態列的說明", {"stamina": status.get("stamina_help"), "war": status.get("war_help"), "entry": status.get("howto_entry")})

    @contextlib.contextmanager
    def staged(self):
        """(只有一位的地點, 那一位, 兩位以上的地點, 那幾位)：一類一顆關著；測試內容沒有大勢人物，另外把三位人物擺上去（audience_fame 3，名望 0 的見不到）。"""
        cfg = self.c.config
        if any(ch.deep_interaction for ch in self.c.characters.values()):
            with self.tuned_all([(cfg, {"precise_actions": False})]):
                yield (*self.alone_spot(), *self.hall_spot())
            return
        spots, cids = sorted(self.c.locations), sorted(self.c.characters)
        rows = [(self.c.characters[cid], {"deep_interaction": True, "audience_fame": 3, "talk_at": spot, "recruit_at": spot})
                for cid, spot in zip(cids, [spots[0], spots[1], spots[1]])]
        with self.tuned_all([(cfg, {"precise_actions": False}), *rows]):
            yield spots[0], cids[0], spots[1], cids[1:3]

    def notes(self, who: str, tag: str) -> None:
        view = self.main(who)
        emit(f"{who} {tag}", {"options": [o for o in view.get("options", []) if str(o.get("id", "")).startswith(("act:socialize", "act:call", "call:"))],
                              "notes": view.get("action_notes")})

    # ── 前半 ──

    def setup(self) -> None:
        StripScenario.setup(self)
        for who in self.PLAYERS:
            self.edit(who, lambda p: setattr(p, "fortune", True))  # 福緣先記成領過：這一軌不看交友事件

    def pages(self) -> None:
        """說明頁換一批設定各看一次（有陣營的一位、散人照舊不一樣的只有狀態列那幾句：散人看平常那一次）。"""
        self.read_help(self.RANGER, "平常")
        self.read_help(self.OPENER, "平常")
        for tag, rows in self.tunes():
            with self.tuned_all(rows):
                self.read_help(self.OPENER, tag)
        with self.stamped(forge_divine_per_kind=False, forge_split_clues=False):
            self.read_help(self.OPENER, "這一季沒蓋鑄譜的章")
            with self.tuned_all([(self.c.config.forge_secrets, {"split_clues": False, "scrap_every_mode": False})]):
                self.read_help(self.OPENER, "鑄譜的章與開關都沒有")
        before = self.chars.load(self.RANGER).player.stamina_pills
        self.edit(self.RANGER, lambda p: (setattr(p, "stamina_pills", 0), setattr(p, "pills_topped_to", 10 ** 6)))
        self.read_help(self.RANGER, "手上沒丹")
        self.edit(self.RANGER, lambda p: setattr(p, "stamina_pills", before))

    def doors(self) -> None:
        """行動列底下求見那幾行（Game.action_notes 的最後一段）：名望夠、名望不夠、談滿、閉門不見；兩位以上的地點 act:call；名單開著不寫 call:。"""
        from tianxia import figures, rules

        who = self.OPENER
        with self.staged() as (spot, lone, hall, figs):
            if spot is not None:
                self.place(who, spot)
                self.edit(who, lambda p: (p.talks_today.clear(), p.snubbed_until.clear()))
                self.fame(who, 9999)
                self.notes(who, "只有一位・名望夠")
                self.fame(who, 0)
                self.notes(who, "只有一位・名望不夠")
                self.fame(who, 9999)
                day = rules.game_day(self.c, self.world.get_season())
                self.edit(who, lambda p: p.talks_today.update({lone: [day, self.c.config.talk_turns_per_day]}))
                self.notes(who, "只有一位・談滿")
                self.edit(who, lambda p: p.talks_today.clear())
                fig = figures.of_character(self.c, lone)
                if fig is not None:  # 測試內容擺上去的人物不在人物表上，閉不了門
                    self.edit(who, lambda p: p.snubbed_until.update({fig: 1.0e12}))
                    self.notes(who, "只有一位・閉門不見")
                    self.edit(who, lambda p: p.snubbed_until.clear())
            if hall is not None:
                self.place(who, hall)
                self.fame(who, 9999)
                self.notes(who, "兩位以上")
                self.choose(who, "act:call")
                self.notes(who, "兩位以上・名單開著")
                self.choose(who, "call:back")

    def half(self) -> None:
        """切在寫到一半：一位的求見名單開著；一位的回體丹還沒補（舊存檔的 pills_topped_to 是 0，讀檔那一刻才補、才寫那一行）。"""
        with self.staged() as (_, _, hall, _):
            if hall is not None:
                self.place(self.LISTER, hall)
                self.fame(self.LISTER, 9999)
                self.main(self.LISTER)
                self.choose(self.LISTER, "act:call")
            self.notes(self.LISTER, "名單開著")
        self.edit(self.TOPPED, lambda p: (setattr(p, "pills_topped_to", 0), setattr(p, "stamina_pills", 0)))

    # ── 後半 ──

    def taken_over(self) -> None:
        """新程式接手：名單接著開著（一類一顆照舊關著）、回體丹這時候才補。"""
        with self.staged():
            self.notes(self.LISTER, "接手之後")
            self.choose(self.LISTER, "call:back")
        self.read_help(self.TOPPED, "接手之後")
        self.me(self.TOPPED, "回體丹補了")

    def arrival(self) -> None:
        """新人建角色：江湖紀錄開場那一行新手福利（一鍵補滿開著與關著各一位）。"""
        self.fresh(self.ARRIVAL)
        with self.tuned_all([(self.c.config, {"beta_free_refill": True})]):
            self.fresh(self.ARRIVAL2)
        self.begin()
        for who in (self.ARRIVAL, self.ARRIVAL2):
            emit(f"{who} 開場", [[e.title, e.tag, list(e.lines)] for e in self.chars.load(who).journal[-1:]])
        self.read_help(self.ARRIVAL, "新人")

    def season(self) -> None:
        """收季、開下一季：說明頁、狀態列的說明跟著新的一季。"""
        self.do(ADMIN, "end_season")
        self.read_help(self.RANGER, "休季")
        self.do(ADMIN, "next_season")
        self.read_help(self.OPENER, "下一季")


# 改一個字（selftest）：玩法說明體力那一節最後一句（第 59 批搬進包，舊名的檔、搬進包的檔兩處找）
register_track("primer", PrimerScenario, (("tianxia/features/guide/howto.py",),
                                          ("點狀態列的體力條，也看得到這幾句。", "點狀態列的體力條，也看得到這幾句！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "hire", "jieyi", "legacy", "looks", "mall", "military",
                       "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern",
                       "territory_acts", "travel", "zhuan", "zongmen"))
