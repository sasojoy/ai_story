"""單挑（單人頭目戰、擂台與台下的場邊事件）。功能包，開發規範手冊 3.2；全部拆包第 12 批搬進來（計畫
docs/superpowers/plans/2026-11-03-單挑包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

單挑底層（剋、推力、挨打、防具、放手一搏、勝負：頭目戰、擂台、奪璽單挑共用）在核心 tianxia/core/duel_base.py；擂台的名次與稱號
（酒肆、名帖、玩家卡、榜單都讀）在核心 tianxia/core/arena_ranks.py——這一包的規則模組從那兩份 re-export。

- duel_rules.py、arena_rules.py、arena_crowd.py：純規則（原 tianxia/duel.py、arena.py、arena_crowd.py；那三個名字留成指到這裡的別名）
- duel_actions.py、arena_actions.py：原本 Game 上頭目戰 16 個、擂台 22 個方法（Game 留 28 個一行委派，含 5 個新開的查詢與審查修正
  補的 _duel_menu）
- bots.py：假人的分數（原本 bot_policy.score 的 duel、arena 那兩段）

拿 duel、arena 兩個前綴：假人看到這兩種選項怎麼按問這一包（bot_pick）。原位接上第 11 批掛鉤的：坐在擂台邊與進擂台那一顆、收店
（店面登記 shops）、打開擂台與那一下的標題（act 子動詞 verbs）、報名與挑人（choose）、擂台打到一半的三招與認輸（menu）、
場邊事件的內容檢查（check_content）。沒有對應掛鉤、留在 Game 原位叫一行委派的（choose 不建紀錄的出招、灰掉的挑擂鈕、頭目戰打到一半的
選單、場景卡、
sync 的補送、閉關中與路上的入口、店面那一頁、戰力快照抄防具、奪璽單挑的陣營名、舊探索撞上頭目）寫在 README。
"""
from __future__ import annotations

from tianxia.core.features import Feature, Outcome, Shop, Verb, WorldHook


class BoutFeature(Feature):
    name = "bout"
    prefix = ("duel", "arena")  # duel:<招>、duel:flee；arena:<招>、arena:yield、arena:join、arena:fight:<名號鍵>、arena:back、arena:none
    content = ("duels.json", "arena_crowd.json")  # 頭目、場邊事件的固定句（content.py 照舊讀）
    # 頭目戰：正在打的那一場、這一季（與這一週）遇上幾次的帳、上一場開打的時刻；擂台：正在打的那一場、剛打完的收場卡、坐在擂台邊、
    # 今天挑了幾次（記在哪一天）、場邊事件每一種落在自己身上是哪一天、還等著模型重寫的那一句——換季都跟著新角色重來
    player_fields = ("duel", "duel_tally", "duel_last", "arena", "arena_last", "picking_arena", "arena_day", "arena_today",
                     "arena_crowd_seen", "arena_crowd_note")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """內容裡有頭目（duels.json）、或擂台開著（Config.arena.enabled），或此刻還在頭目戰、擂台上、坐在擂台邊：開關在坐著、打著的時候
        被關掉（沒經過 sync 收店）照樣按得到返回與三招、假人照樣只按返回（同酒肆）——搬包之前 choose 的那幾支、bot_policy.score 的那兩段
        都不看開關。"""
        from tianxia.core import arena_ranks  # noqa: PLC0415

        p = ctx.state.player
        return bool(ctx.content.duels) or arena_ranks.on(ctx.content) or p.duel is not None or p.arena is not None or p.picking_arena

    def menu(self, ctx):
        """擂台打到一半（原本 Game._everyday_options 在 features_core.menu 下一行那一支；這一包排在宴客後面＝原本那一行的位置）：
        選單整個是三招與認輸（arena_actions.fight_menu）；放手一搏同頭目戰走輸入框。頭目戰的三招與抽身排在 features_core.menu 前面一行
        （接上這個掛鉤會排到宴客的席位後面）：本體在 duel_actions.duel_menu，_everyday_options 原位叫 Game._duel_menu 一行委派。"""
        if ctx.state.player.arena is None:
            return None
        from . import arena_actions  # noqa: PLC0415

        return arena_actions.fight_menu(ctx)

    def choose(self, ctx, kind, arg):
        """arena:join／fight:<名號鍵>／back（坐在擂台邊那一串給的）：標題照原 Game._action_title 的 arena 那一支（挑人寫「擂台・他」），
        動作照原 Game._arena（報名或更新分身、開打、返回）。三招與認輸在 Game.choose 原位（查完選單、建紀錄之前，出招不寫紀錄）已經接走；
        duel: 也是（同決戰的 battle:，總表第 57 批「選單上、不建紀錄」那一格四包一起接）。"""
        if kind != "arena":
            return None
        from . import arena_actions  # noqa: PLC0415

        return Outcome(title=arena_actions.arena_title(ctx, arg), run=lambda: arena_actions.arena_choice(ctx, arg))

    def bot_pick(self, ctx, option):
        """假人看到 duel:、arena: 那一顆的分數（原本 bot_policy.score 的那兩段）。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    def check_content(self, content, need) -> None:
        """場邊事件的固定句（content/arena_crowd.json）：原本是 content.check_arena_crowd（核心不 import 包，搬進來；content.validate 的
        check_features 叫，排在 check_art 前面——只有兩樣同時寫壞時錯誤的先後不一樣）。開關關著也照驗（缺種類那一條自己看開關）。"""
        from . import arena_crowd  # noqa: PLC0415

        arena_crowd.check_content(content, need)

    # ── 接縫掛鉤（第 11 批開的；全部拆包第 12 批接上原本在 Game 原位的擂台那幾行）──

    _shops: tuple[Shop, ...] | None = None

    def shops(self) -> tuple[Shop, ...]:
        """店面登記：擂台是「舊的六間店」的最後一間（原本 Game 上七間店共用的那幾處，擂台那幾行照抄；排在 FEATURES 最後＝酒肆後面）——
        坐在擂台邊（picking_arena）選單整個是擂台那一串（arena_actions.arena_options）；此地還能做裡「擂台」那一顆（arena.here：開著、季在跑、
        不在序章、到了開擂台的那一週；哪裡都有）；店面那一頁的 key 是 arena（坐著、這裡也還開著；打到一半那一行只讀存檔，留在
        Game._shop_open 原位）；動身、此地不開了收起來（picking_arena = False）。閉關中、在路上的入口不是「此地還能做」，留在原位叫
        Game._arena_entry。建一次就留著，每一格在叫的那一下才照模組屬性找函式（monkeypatch 照樣有效）。"""
        if self._shops is None:
            from . import arena_actions  # noqa: PLC0415
            from . import arena_rules as arena  # noqa: PLC0415

            self._shops = (Shop(
                key="arena", inside=lambda ctx: ctx.state.player.picking_arena, here=lambda ctx: arena.here(ctx.state, ctx.content),
                close=lambda ctx: arena_actions.close(ctx), menu=lambda ctx: arena_actions.arena_options(ctx),
                entry=lambda ctx: arena_actions.entry_option(ctx),
            ),)
        return self._shops

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:arena 的主人（act 子動詞）：按下去打開擂台（arena_actions.arena_open：不花體力，頭一句是名次、稱號與戰績；原本 Game._act
        中段那一支）、紀錄標題「擂台・此地」（arena_actions.arena_sign；原本 Game._action_title 那張表的 arena）。兩樣都不問 enabled
        （原位不看開關）。進擂台那一顆在店面登記（Shop.entry）。"""
        if self._verbs is None:
            from . import arena_actions  # noqa: PLC0415

            self._verbs = (Verb("arena", run=lambda ctx, prepared: arena_actions.arena_open(ctx),
                                title=lambda ctx: arena_actions.arena_sign(ctx)),)
        return self._verbs

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層 close 的 arena 那一格（收季記擂台前三名；原本 world.end_season 經舊名 arena 叫 close_season，第 12 批 PM 認定第 2 條）：
        不問 enabled（原位只看擂台開著沒）。建一次就留著，在叫的那一下才照模組屬性找 arena_rules.world_close（monkeypatch 照樣有效）。"""
        if self._world is None:
            from . import arena_rules  # noqa: PLC0415

            self._world = (WorldHook("close", "arena", lambda *args: arena_rules.world_close(*args)),)
        return self._world


FEATURE = BoutFeature()
