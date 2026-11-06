"""陣營（功能包；開發規範手冊 3.2；全部拆包第 35 批）。README.md 寫這一包做什麼、導覽與設計稿。

- join_actions.py：投靠與拜入門派（投靠兩步確認、選邊、拜入要依附的門派之後的傾向、待確認的選單、sect: 那一顆）；「你這一步」的去投靠那一格（第 36 批）
- lean_actions.py：豪強改幫（三陣營四勝利）
- defect_actions.py：叛投的行動（確認、驗證、同伴回江湖、選單能叛投去的、確認畫面的場景）
- defection.py：叛投的規則（原 tianxia/defection.py；那個名字留成指到這裡的別名）
- ending_actions.py：季末與三方卡（起手資源與稱號、結局卡、三方卡、此刻拿第幾階、四勝利開著沒）
- bots.py：假人的分數（原本 bot_policy.score 的 defect／sect 那兩段；faction: 原本落到最後的 None）
"""
from __future__ import annotations

from tianxia.core.features import DefectHook, Feature, HowtoHook, MenuHook, Outcome, SeamHook, StepHook


class FactionFeature(Feature):
    name = "faction"
    prefix = ("faction", "defect", "sect")  # faction:…（投靠、確認、選邊、改幫）、defect:…（叛投）、sect:<事件>（拜入門派）
    bot_always = ("defect:", "faction:lean:")  # 叛投、改幫隨時按得下去：整季機器人不按（原本 bot.pick 的排除；機器人不換邊）
    player_fields = ("pending_faction", "pending_defect", "pending_ally")  # 按了投靠／叛投還在確認畫面上、挑好的依附那一軍；換季照新角色重來
    content = ("sects.json", "events/sects.json")  # 門派與拜入門派的事件（總表附錄甲：歸陣營）；content.py 照它到這一包的 content/ 載；檔名照舊
    carried: tuple[str, ...] = ()
    _defection: tuple[DefectHook, ...] | None = None

    def enabled(self, ctx) -> bool:
        """一律開著：choose 與 bot_pick 原位本來就不看任何開關（投靠要劇本有陣營、改幫要四勝利、拜入門派要一類一顆，判斷在選單與步驟裡）；
        搬包之前就是這樣，行為一個字不變。"""
        return True

    def choose(self, ctx, kind, arg):
        """faction／defect／sect 三個前綴原本是 Game.choose 的 elif 最後幾支，標題是 Game._action_title 開頭那兩支（sect 沒有自己的支，
        掉到最後的「提前出關」，隨後被事件標題換掉——照舊問核心的 _action_title）。標題在動作之前拿（同原本）。"""
        s, c = ctx.state, ctx.content
        if kind == "faction":
            from tianxia import wins  # noqa: PLC0415
            from tianxia import allied  # noqa: PLC0415
            from . import join_actions  # noqa: PLC0415

            if arg == "confirm":
                title = f"投靠{allied.label(c, s.player.pending_faction, s.player.pending_ally)}"
            elif arg == "cancel":
                title = "再想想"
            elif arg.startswith("ally:"):  # 豪強分屬兩軍：挑依附哪一軍
                title = f"依附{c.scenario.faction_name(arg[5:], arg[5:])}"
            elif arg.startswith("lean:"):  # 三陣營四勝利：豪強改幫另一軍
                title = wins.LEAN_BUTTON.format(side=c.scenario.faction_name(arg[5:], arg[5:]))
            else:
                title = f"考慮投靠{c.scenario.faction(arg).name}"
            return Outcome(title=title, run=lambda: join_actions.faction_step(ctx, arg))
        if kind == "defect":
            from . import defect_actions, defection  # noqa: PLC0415

            if arg == "confirm":
                title = defection.slot_label(s, c, c.scenario.faction(s.player.pending_defect), s.player.pending_ally)
            elif arg == "cancel":
                title = "再想想"
            else:
                fid, _, ally = arg.partition(":")  # 豪強分屬兩軍：defect:<陣營>:<依附的那一軍>
                title = f"考慮{defection.slot_label(s, c, c.scenario.faction(fid), ally or None)}"
            return Outcome(title=title, run=lambda: defect_actions.defect_step(ctx, arg))
        if kind == "sect":  # 拜入門派（一類一顆，join_actions.sect_options）：端出那一則事件，不花體力
            from . import join_actions  # noqa: PLC0415

            return Outcome(title=ctx._action_title(kind, arg), run=lambda: join_actions.sect_choose(ctx, arg))
        return None

    def on_drop_stale(self, ctx) -> None:
        """內容改版後拿掉的陣營：還在確認畫面上的投靠、改依附、叛投作廢（原本在 Game._drop_stale_references 中段，現在接在最後；
        中間到 features_core.on_drop_stale 沒有任何一行讀 pending_faction、pending_ally、pending_defect）。"""
        p = ctx.state.player
        ids = {f.id for f in ctx.content.scenario.factions}
        if p.pending_faction and p.pending_faction not in ids:
            p.pending_faction = None
        if p.pending_ally and p.pending_ally not in ids:
            p.pending_ally = None
        if p.pending_defect and p.pending_defect not in ids:
            p.pending_defect = None

    def bot_pick(self, ctx, option):
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def bot_idle(self, ctx, option):
        """拜入門派 sect:<事件>（一類一顆）：不花體力、婉拒之後還在，同 act:rest；只在第一次看到那一則時按得下去（整季機器人還是隨機挑，婉拒的就不再按。原本 bot.pick 那一條；不問 enabled）。"""
        return option.id.startswith("sect:") and option.id.partition(":")[2] in ctx.state.player.seen_events

    def defection(self) -> tuple[DefectHook, ...]:
        """叛投：clear 位置的 progress 那一格（階、召見、部下、貢獻、兩本帳、捐獻；原本 defection._CLEAR_CORE）與 after 位置的 leave_behind 那一格
        （寫了新陣營不合的同伴當場回江湖；原本 engine._DEFECT_AFTER_CORE）：不問 enabled。位置在 DEFECT_ORDER，一個字不動。
        建一次就留著，在叫的那一下才照模組屬性找 defection._clear_own、defect_actions.leave_behind（monkeypatch 照樣有效）。"""
        if self._defection is None:
            from . import defect_actions, defection  # noqa: PLC0415

            self._defection = (
                DefectHook("clear", "progress", lambda p: defection._clear_own(p)),
                DefectHook("after", "leave_behind", lambda ctx, side: defect_actions.leave_behind(ctx, side)),
            )
        return self._defection

    # core_step（全部拆包第 36 批「你這一步」）
    _steps: tuple[StepHook, ...] | None = None

    def steps(self) -> tuple[StepHook, ...]:
        """「你這一步」的 join 那一格（去投靠；原本 weekcard._steps 最後那一段與 step._target 的去投靠那一支）：排最後（STEP_ORDER）。
        不問 enabled（散人、劇本有陣營、季沒收的判斷在 join_step_items 裡）。建一次就留著，在叫的那一下才照模組屬性找
        join_actions.join_step_items／join_step_place（monkeypatch 照樣有效）。"""
        if self._steps is None:
            from . import join_actions  # noqa: PLC0415

            self._steps = (StepHook("join", lambda ctx, status, orders: join_actions.join_step_items(ctx), ref="join",
                                    place=lambda ctx, ref: join_actions.join_step_place(ctx, ref)),)
        return self._steps

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """season.grant 的 faction 那一格（順序在 SEAM_ORDER；不問 enabled：on_season_start 在開場那一則之前、這一格在它之後）：上一季論了功的人起手資源與稱號（ending_actions.season_grant）。"""
        if self._seams is None:
            from . import ending_actions  # noqa: PLC0415

            self._seams = (SeamHook("season.grant", "faction", lambda ctx, old: ending_actions.season_grant(ctx, old)),)
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單與動身的格（順序在 MENU_ORDER；不問 enabled）：待確認的畫面接管整個選單（空的也算，髒存檔）；此地的拜入、投靠、叛投、改幫；還沒挑依附哪一邊不算閒著；動身被擋。"""
        if self._menus is None:
            from . import defect_actions, join_actions, lean_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "faction", lambda ctx: join_actions.pending_options(ctx)),
                MenuHook("here", "sect", lambda ctx, loc, cost, odds: join_actions.sect_cell(ctx)),
                MenuHook("here", "join", lambda ctx, loc, cost, odds: join_actions.join_options(ctx)),
                MenuHook("here", "defect", lambda ctx, loc, cost, odds: defect_actions.defect_options(ctx)),
                MenuHook("here", "lean", lambda ctx, loc, cost, odds: lean_actions.lean_options(ctx)),
                MenuHook("idle", "faction", lambda ctx: join_actions.picking_ally(ctx)),
                MenuHook("block", "faction", lambda state, content: join_actions.travel_block(state, content)),
            )
        return self._menus

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的join、factions 兩格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (
            HowtoHook("join", lambda content, season, page: words.join_section(content, season)),
            HowtoHook("factions", lambda content, season, page: words.factions_section(content, season)),
        )


FEATURE = FactionFeature()
