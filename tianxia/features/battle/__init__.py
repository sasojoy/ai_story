"""全服決戰（官軍、黃巾兩軍在一個大區集結、一回合一回合打；收場之後每個人下一次同步補戰報、江湖紀錄、軍餉、行狀）。功能包，開發規範手冊 3.2；
主動搬六包第 5 批搬進「看」的那一半。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：決戰畫面與戰報的字、常數，鎖外三段式的兩張單子（放手一搏評分、補劇情）
- view.py：原本 Game 上「看」那一半的 31 個方法——場景、戰局條、攻城條、一回合一段的戰況、收場補送（戰報、江湖紀錄、軍餉、行狀、戰功）、
  補回被洗掉的戰報、放手一搏的輸入框與三段式、補劇情（Game 留 22 個一行委派）
- admin.py：全部拆包第 6 批，管理者的決戰工具 7 個方法——立刻開戰的選單、立刻開戰、取消決戰、三場大戲那三顆鈕（Game 留 6 個一行委派）
- sieges.py：全部拆包第 6 批，攻城 7 個方法——還沒收場的那一串、這一場的定義、推一場、收兵、取消、收場與守城軍令（Game 留 6 個一行委派；
  攻城的規則本身在 tianxia/siege.py，共用規則層）
- muster.py：全部拆包第 7 批，集結、加入、晚到、臨時投效、改投、挑同伴、在不在場、假人趕路、出招的分派 29 個方法（Game 留 13 個一行委派）
- escorts.py：全部拆包第 7 批整個從 tianxia/escorts.py 搬來（隨你出陣的同伴打完回江湖；舊名是別名）
- bots.py：全部拆包第 7 批，假人看到 battle: 的選項怎麼按（原本 bot_policy.score 的 battle 那一段）
- progress.py：全部拆包第 8 批，推進與結算 20 個方法——我在哪一場、一回合一回合推（回合首功包在外面）、收兵（季終、取消、收季）、收場與論功、
  只能觀戰與整個取代畫面、份量快照補上（Game 留 14 個一行委派）
- generals.py：全部拆包第 8 批整個從 tianxia/generals.py 搬來（龍頭上陣：開集結派人上陣、陣前那一行、收場扣聲威；舊名是別名）——挑法 on、pick
  留在共用規則層 tianxia/chiefs.py（siege 也讀），這裡 re-export
- instance.py：全部拆包第 54 批從 tianxia/battle_instance.py 搬來（集結、出招、結算回合、戰局條與論功的字、鎖外評分與補劇情，111 個名字；舊名是別名）——
  資料型別與別處要讀的判定（63 個名字）在核心 tianxia/core/battle_base.py，這裡 re-export 同一批物件

全部拆包第 7 批拿了 battle: 前綴：假人看到 battle: 的選項怎麼按問這一包（bot_pick → bots.py，原本是 bot_policy.score 的 battle 那一段）。
battle: 的分派是 MENU_ORDER["quick"] 的 battle 那一格（全部拆包第 57 批；查完選單、清掉「剛剛」與引導之後、建紀錄之前）：choose_unlisted
在查選單之前、choose 掛鉤會建紀錄，都不是那個位置（計畫 2026-11-01-決戰包-第3批.md 1.4），所以 choose 掛鉤照預設回 None。
換季照帶補過的決戰（carried 那一格）第 55 批起是 season.carry 的 battle 那一格、不掛 on_season_start（同出陣第 1 批審查之後的做法）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, MenuHook, SeamHook, StatusHook, WorldHook, slot_some


class BattleFeature(Feature):
    name = "battle"
    web = ("battle.js", "battle.css")  # 集結、戰場、戰局條、MVP、攻城條（全部拆包第 67 批從 main.js、style.css 切出來）
    prefix: str | None = "battle"  # 全部拆包第 7 批拿的：battle:join／enlist／escort／act……（選項照舊由 Game 的 _battle_menu 委派給，分派是 MENU_ORDER["quick"] 那一格，第 57 批）
    content = ("battles.json",)  # 決戰與攻城範本（content.py 照它到這一包的 content/ 載；攻城的規則在 siege.py，共用規則層）
    # 補過的決戰（跨季照帶：決戰常把季收掉，下一季才回來的人也要補、而且只補一次）、這一季參戰幾場與首功幾次（玩家卡、名帖）。
    # showdowns_restored（補回被洗掉的戰報，一季查一次）也是這一包的，但每一季第一次同步就寫成那一季的編號：契約測試的「換季回到預設」
    # 對它不成立，不放進來（README 照列）
    # 第 7 批（集結、挑同伴）再認兩格：escort_pick（按了加入、還在挑誰隨你上陣）、parted_done（同伴回江湖、情誼已經減半、全服的記號還沒清；
    # muster.settle_partings 讀寫）——換季都跟著新角色重來
    player_fields = ("battle_results_seen", "showdowns", "top_merits", "escort_pick", "parted_done")
    carried = ("battle_results_seen",)  # season.carry 那一格照帶（不看開關，同商城、出陣的 carried）

    def enabled(self, ctx) -> bool:
        """內容裡有決戰（battles.json）就有：決戰本身沒有開關（beta、第一季、減法季都打）。遊戲當下的掛鉤全是預設的空的，開著關著結果都一樣；
        第 11 批的接縫掛鉤不問它（下面）。"""
        return bool(ctx.content.battles)

    def bot_pick(self, ctx, option):
        """假人看到 battle: 那一顆的分數（全部拆包第 7 批：原本 bot_policy.score 的 battle 那一段）。關著（內容沒有決戰）核心不問、
        回 None——那時選單上本來就沒有 battle: 的選項。"""
        from . import bots  # noqa: PLC0415

        return bots.score(ctx, option)

    # ── 接縫掛鉤（全部拆包第 11 批：原本在 Game 原位直接叫這一包的那幾行；不問 enabled）──

    def deliver_results(self, ctx) -> None:
        """收場補送（原本 Game.sync 補份量快照之後、玉璽碎片之前那一行）：下線時收場的決戰與攻城，回來第一次同步補上（休季、籌備中也一樣，
        FB-027）。經 Game 叫：tests/core/test_renown_cross.py 換掉 Game._deliver_battle_results（服務清單三、過渡）。
        全部拆包第 8 批把緊接著的前一行（補份量快照：場上沒有份量快照的自己，上線前就在決戰裡；排程的 world_tick 不走這裡）併進這一格、
        排在補送前面（登記的包只有這一包有這個掛鉤，先後一個不變）。"""
        from . import progress  # noqa: PLC0415

        progress.backfill_battle_scores(ctx)
        ctx._deliver_battle_results()

    def scene_over(self, ctx):
        """蓋在畫面上的（原本 Game.scene_text 最前面那幾行）：有全服戰鬥時大家都看得到戰場（序章裡不畫，battle_for_me；tick=False：一次請求
        只推進一次）；回（戰場那一段, 開打了在場上的人〔fighting〕戰場整個取代畫面）。沒有是 None。"""
        from . import progress, view  # noqa: PLC0415

        battle_status = progress.battle_for_me(ctx, tick=False)
        if battle_status is None:
            return None
        return view.battle_scene_text(ctx, *battle_status), progress.fighting(ctx, *battle_status)

    def record_detail(self, ctx, record):
        """戰報頁那一筆（原本 Game.battle_detail 裡那幾行）：決戰那一筆照 battles 表重讀完整戰況（收場之後才補上的放手一搏劇情也在）；
        不是決戰、表上沒有那一場、自己不在名單上、內容裡沒有那一場是 None（照原本那一筆）。"""
        if record.battle_ref is None:
            return None
        from . import view  # noqa: PLC0415

        battle = ctx.world.ended_battle(record.battle_ref)
        me = battle.participants.get(ctx.state.player.name) if battle is not None else None
        definition = ctx.content.battles.get(battle.battle_id) if battle is not None else None
        if me is None or definition is None:
            return None
        return record.model_copy(update={"log": view.round_blocks(ctx, battle, definition, last=None, oldest_first=True, me=me)})

    # ── 接縫掛鉤（全部拆包第 8 批：收季的收兵；第 11 批 PM 認定第 7 條）──

    def on_season_close(self, ctx, reread: bool) -> None:
        """收季的收兵（原本 Game.admin_end_season 讀回收季那一份季之後、Game.admin_next_season 休季時那兩段；不問 enabled）：沒打完的決戰收掉
        （reread：開下一季，收之前讀回手上那一份季）、每一場攻城收掉（reread 同上）——不算勝負，參戰者各補一則（FB-015、FB-035）。本體在
        progress.close_season。"""
        from . import progress  # noqa: PLC0415

        progress.close_season(ctx, reread)

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 muster 的 generals 那一格（龍頭上陣；原本 world._open_claimed 函式裡 import 舊名 generals 叫 on_muster）：不問 enabled
        （原位不看決戰包的開關，判斷在 on_muster 裡）。建一次就留著，在叫的那一下才照模組屬性找 generals.world_muster（monkeypatch 照樣有效）。"""
        if self._world is None:
            from . import generals  # noqa: PLC0415

            self._world = (WorldHook("muster", "generals", lambda *args: generals.world_muster(*args)),)
        return self._world

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的三格（順序在 SEAM_ORDER；不問 enabled）：sync 同伴回江湖（muster.settle_partings，回傳不接）、排程那一下推一次決戰（經 ctx._battle_status：
        test_engine、test_hints 換掉 Game 上的名字才打得到；回傳不接）、換季照帶補過的決戰。"""
        if self._seams is None:
            from . import muster  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.deliver", "partings", lambda ctx: _quiet(muster.settle_partings(ctx, True))),
                SeamHook("tick", "battle", lambda ctx: _quiet(ctx._battle_status(tick=True))),
                SeamHook("season.carry", "battle", _carry_season),
            )
        return self._seams

    # core_seams（全部拆包第 57 批「分派與標題收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """quick 的 battle 那一格（順序在 MENU_ORDER；不問 enabled）：決戰選項不走 Draft（加入與趕到由 battle_choose 自己寫一則紀錄，每回合的出招不寫，FB-030）。
        決戰那幾顆與平常的選單怎麼接、整個取代、只能看三種結果留在 Game.options 原位（第 56 批計畫第四節）。"""
        if self._menus is None:
            from . import muster  # noqa: PLC0415

            self._menus = (MenuHook("quick", "battle", lambda ctx, kind, arg, option_id: muster.battle_choose(ctx, arg) if kind == "battle" else None),)
        return self._menus

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import view  # noqa: PLC0415

            self._status_slots = (
                # 決戰的即時戰局條（Joy 2026-10-10）：場景裡畫著的這一場（集結、開打），與「剛剛」是一場決戰時收場那一刻的
                StatusHook("main", "gauges", lambda ctx, frame: {"battle_gauge": view.battle_gauge(ctx),
                                                                 "card_gauge": view.card_gauge(ctx) if frame.card is not None else None}),
                # 領地爭奪第三批 A：場景裡畫的是攻城戰時，最上面那一條「攻城・地點｜守方：某某」（企劃者挑甲；決戰沒有這個鍵）
                StatusHook("main", "siege", lambda ctx, frame: slot_some("siege", view.siege_banner(ctx))),
            )
        return self._status_slots

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.admin_tools(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


def _quiet(_) -> None:
    """回傳不接的格一定回 None（seam_lines 只收 list 或 None，list 會併進回話）。"""


def _carry_season(ctx, old, fresh) -> None:
    fresh.player.battle_results_seen = old.player.battle_results_seen  # 補送過的決戰不再補一次（FB-027）


FEATURE = BattleFeature()
