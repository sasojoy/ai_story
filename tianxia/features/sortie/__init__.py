"""出陣（投靠了陣營的人在領地爭奪的區塊上攻、守；混戰；出陣回報；約戰；舊遊歷、序章雪恥、跟自家隊伍操練、守勢）。功能包，開發規範手冊 3.2；
主動搬六包第 1、2 批與全部拆包第 17 批（出陣三）搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：純規則（原 tianxia/sortie.py；那個名字留成指到這裡的別名）
- actions.py：原本 Game 上出陣本體、混戰、出陣回報的 21 個方法（Game 留一行委派），與 act:train 那一格的 train_*（第 11 批）
- duel_rules.py、duel_actions.py：出陣約戰（第 2 批）
- train_actions.py：舊遊歷、序章雪恥、跟自家隊伍操練、守勢、遊歷推大勢（第 17 批；Game 留 8 個一行委派）

出陣那一格的 id 照留核心的 act:train（遊歷、序章的雪恥、並肩出陣、大場面判讀都認它）。第 11 批起這一包是那一格的主人（act 子動詞 verbs：
行動列那一格、底下那一行、按下去、紀錄標題），第 17 批連打的那一場（扣體力、並肩出陣、出陣或遊歷）、地盤關著的舊遊歷那一格與那一行、
「這一下打哪一路」（大場面判讀，Verb.squad）、守勢行動 act:duty（按下去；鈕在軍令的那幾顆裡、照舊經 Game._duty_option）一起收進來。
約戰的 sortie:*（第 2 批拿了前綴）不在選單上，Game.choose 查選單之前經 choose_unlisted 接走；窗滿了的約戰經 on_due 結算（三處都是第 11 批
的接縫掛鉤，下面）。假人：act:train、act:duty 的分數與約戰卡上的事在 bots.py（第 60 批，Verb.bot 問；其餘條件還在 bot_policy）。
換季照帶今天出陣的次數（carried 那兩格）第 55 批起是 season.carry 的 sortie 那一格、不掛 on_season_start：遊戲當下的掛鉤只叫
開著的包（同商城的 carried；dev/sortie-1 審查，tests/test_sortie_season_carry.py 守）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, SeamHook, StatusHook, Verb, slot_some


class SortieFeature(Feature):
    name = "sortie"
    web = ("sortie.js", "sortie.css")  # 出陣約戰的封招與前往（全部拆包第 66 批從 app.js 切出來）；出陣那一格的卡與樣子（全部拆包第 67 批從 main.js、style.css 切出來）；出陣那一格的卡與樣子（全部拆包第 67 批從 main.js、style.css 切出來）
    # 出陣約戰（第 2 批）的三個動作：sortie:go:<三招>、sortie:answer:<約戰 id>:<三招>、sortie:join:<約戰 id>。不在選單上（封招的組合放不進去），
    # Game.choose 最前面就接走（查選單、建 Draft 之前；關著的季照舊「此刻無法這麼做」），所以這一包不接 choose 掛鉤。假人：bot_policy.score
    # 沒有 sortie: 那一段（選單上本來就沒有它們），bot_pick 照預設回 None＝不按，跟原本落到 score 最後的 return None 一樣。
    # act:train（出陣那一格）、act:duty（守勢）照舊是核心的前綴
    prefix: str | None = "sortie"
    content = ("events/train_aftermath.json",)  # 遊歷打完接的戰後事件（全部拆包第 63 批）；content.py 照它到這一包的 content/ 載；檔名照舊
    # 今天出陣幾次（換日同回體丹）、這一季出陣攻打打贏掉過幾件寶物與良駒（treasures.sortie_rare 的一季上限）；
    # 約戰（第 2 批）：今天應戰幾次（換日同回體丹）、下一次出陣與應戰的冷卻（現實秒）、巡哨那一點貢獻記在哪一天幾次（都在 state.QUIET_DEFAULTS）
    player_fields = ("sortie_day", "sorties_today", "sortie_treasures", "sortie_horses",
                     "answer_day", "answers_today", "sortie_cooldown_until", "answer_cooldown_until", "duty_day", "duties_today")
    carried = ("sortie_day", "sorties_today")  # 換季不能多出一輪陣（season.carry 那一格照帶）；掉寶的上限跟著新的一季重來

    def enabled(self, ctx) -> bool:
        """一直開著（全部拆包第 17 批）：act:train 那一格每一季都是這一包的——地盤（＝領地爭奪，`rules.on`＝`territory.on`）開著是出陣
        （序章是雪恥），關著是舊遊歷。行動列那一格（Verb.cell）是給選項的、照問 enabled（第 11 批 PM 認定第 2 條），原本地盤關著時這一包
        關著、那一格由核心畫遊歷；舊遊歷收進來之後包要開著才畫得出來。這一包遊戲當下的掛鉤只有那一格（bot_pick 對 sortie:* 照預設回 None），
        其餘照舊：出陣、約戰、守勢各自先問自己的開關（rules.on、duel_rules.on、軍令開著沒）。"""
        return True

    def on_due(self, ctx) -> None:
        """到時的結算（接縫掛鉤，全部拆包第 11 批；原本 Game.world_tick、sync、advance 三處叫 Game._sortie_duel_tick 的那一行）：窗滿了的
        約戰照時結算（約戰關著、沒有到時的什麼都不做、不寫）。不問 enabled：原位本來就不看開關，duel_tick 自己看。"""
        from . import duel_actions  # noqa: PLC0415

        duel_actions.duel_tick(ctx)

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:train 那一格的主人（act 子動詞，第 11 批；actions.py 的 train_*）：行動列那一格（問 enabled）、底下那一行、按下去（約戰開著時
        打開那張卡；其餘打那一場：train_actions.train_fight，第 17 批）、紀錄標題（出陣／雪恥／遊歷・某地：關著照舊寫遊歷，所以不問 enabled）、
        只打開那張卡的回話（sortie_duel.PICK：不算做過、不寫紀錄）、這一下打哪一路（Verb.squad：大場面判讀，第 17 批）。act:duty（守勢，
        第 17 批）：按下去（train_actions.duty）；鈕在軍令那幾顆裡（軍情包 order_options 經 ctx 叫 Game._duty_option）；紀錄標題寫陣營自己的名字（巡哨、傳道、保境安民；第 57 批從核心那張表搬來）。
        建一次就留著，每一格在叫的那一下才照模組屬性找函式（monkeypatch 照樣有效；tests/core/test_contract_features.py 守）。"""
        if self._verbs is None:
            from . import actions, bots, duel_rules, train_actions  # noqa: PLC0415

            def title(ctx):
                return f"{actions.train_title(ctx)}・{ctx.content.locations[ctx.state.player.location].name}"

            def duty_title(ctx):
                duty = ctx.content.orders.duties.get(ctx.state.player.faction or "")
                return f"{duty.name if duty else '守勢'}・{ctx.content.locations[ctx.state.player.location].name}"

            self._verbs = (
                Verb("train", run=lambda ctx, prepared: actions.train_run(ctx, prepared), title=title,
                     cell=lambda ctx, loc, cost, odds: actions.train_cell(ctx, loc, cost, odds),
                     note=lambda ctx, loc: actions.train_note(ctx, loc), picks=(duel_rules.PICK,),
                     squad=lambda ctx: train_actions.train_squad(ctx), bot=lambda ctx, profile: bots.train(ctx, profile)),
                Verb("duty", run=lambda ctx, prepared: train_actions.duty(ctx), title=duty_title, bot=lambda ctx, profile: bots.duty(ctx)),
            )
        return self._verbs

    def choose_unlisted(self, ctx, option_id):
        """不在選單上的動作（接縫掛鉤，第 11 批；原本 Game.choose 本週卡「換一件事」之後、列傳的票之前那一行）：約戰開著時的貼、應戰、同去
        （sortie:go／answer／join，封招的組合放不進選單），各自在 world.mutate 裡重驗；約戰關著的季照舊當成不在選單上（回 None，核心照舊查選單）。"""
        from . import duel_actions, duel_rules  # noqa: PLC0415

        if option_id.startswith(duel_rules.PREFIX) and duel_actions.duel_on(ctx):
            return duel_actions.duel_choice(ctx, option_id)
        return None

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """season.carry 的 sortie 那一格（順序在 SEAM_ORDER；不看開關：地盤關著的那一季也帶，同商城的 legend_items、create_rerolls；dev/sortie-1 審查，features/sortie/tests/test_sortie_season_carry.py）。"""
        if self._seams is None:
            self._seams = (SeamHook("season.carry", "sortie", _carry_season),)
        return self._seams

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的sortie 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("sortie", lambda content, season, page: words.sortie_section(content, season)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import duel_actions, rules  # noqa: PLC0415

            self._status_slots = (
                # 出陣開著（出陣探索與地盤設計第二節）：行動列那一格叫「出陣」、等候的話換一句；關著時照舊「遊歷」
                StatusHook("main", "sortie", lambda ctx, frame: {"sortie": rules.on(ctx.content)}),
                # 出陣約戰（減法季批 3b，計畫 1.3）：出陣前那張卡與約戰卡清單；約戰關著沒有這兩個鍵
                StatusHook("main", "sortie_cards", lambda ctx, frame: {**slot_some("sortie_card", duel_actions.sortie_card(ctx)),
                                                                       **slot_some("sorties", duel_actions.sortie_cards(ctx))}),
            )
        return self._status_slots


def _carry_season(ctx, old, fresh) -> None:
    fresh.player.sortie_day, fresh.player.sorties_today = old.player.sortie_day, old.player.sorties_today  # 換季不能多出一輪陣


FEATURE = SortieFeature()
