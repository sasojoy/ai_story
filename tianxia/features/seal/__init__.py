"""玉璽碎片（功能包；開發規範手冊 3.2）：碎片的季流程——現世與璽動（集結那一刻）、開季藏一片與探索撿到、時刻表決戰收場、補送、
天命之季與天命之爭、換季的隱沒與散去，與管理者的強制現世、隱沒判斷、蓋天命之季。全部拆包第 27 批「玉璽一」搬進來
（計畫 docs/superpowers/plans/2026-11-07-玉璽包-第1批.md）。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- seal.py：碎片的規則與字句（原 tianxia/seal.py 整份；那個名字留成指到這裡的 sys.modules 別名）。核心與決戰包讀的那一小半在核心本體
  tianxia/core/seal_base.py，這裡 re-export 同一批。
- actions.py：原本 Game 上的季流程（抄本、撿到、份量快照與加權、補送、奪璽單挑的戰報、定天命、收場）；Game 留一行委派
- admin.py：管理者的強制現世（含現在藏一片）、隱沒判斷、蓋天命之季；Game 留一行委派（測試、管理頁的讀取叫）；管理者工具在 routes.py 的 admin_tools（全部拆包第 68 批）
- season.py：開季藏一片、天命之季的章、舊季收尾（原本核心 sqlite_world 的三段）

第 28 批「玉璽二」再搬進來（計畫 docs/superpowers/plans/2026-11-06-玉璽包-第2批.md）：
- duel_rules.py：奪璽單挑的純規則（原 tianxia/seal_duel.py 整份，舊名留成別名）
- duel_actions.py：奪璽單挑的玩法（挑挑戰者與開單挑、推進、三招、放手一搏、奪璽卡、背景輪詢）；Game 留一行委派
- card.py：碎片卡與七種獨門行動（規則讀同包 acts.py；第 51 批「玉璽三」：acts.py 是原 seal_acts 的包這一半，璽效查詢那一半留在共用規則層 tianxia/seal_acts.py）；admin.py 加強制璽動、指定、開單挑、定結果、取消、管理頁一組
- bots.py：假人看到 seal: 一律不按

選項前綴 seal:（bot_pick 問 bots.score；menu、choose 不接；選單上的一招是 MENU_ORDER["quick"] 的 seal 那一格，第 57 批）、沒有 APIRouter（管理者的 seal_*、seal_use 在 routes.py 的 admin_tools、main_actions，全部拆包第 68 批；seal_text 是鎖外三段式，第 69 批進 routes.py 的 outlock）。
掛鉤：事件 outing、battle_end 的 seal 兩格（bus）、世界層 muster、open、next×2、retire 五格（world）、效果 runic、shard 兩格（effects）、
接縫 deliver_results（sync 的收場補送）、補算與換季四格（seams，第 55 批）；都不問 enabled（格裡自己問 content.seal、Config.seal.enabled：散去不看開關、隱沒看開關）。
"""
from __future__ import annotations

from tianxia.core.features import BusHook, EffectHook, Feature, HowtoHook, MenuHook, SeamHook, StatusHook, WorldHook


class SealFeature(Feature):
    name = "seal"
    web = ("seal.js", "seal.css")  # 奪璽卡、碎片卡與獨門行動（全部拆包第 66 批從 app.js 切出來；獨門行動的樣子第 67 批從 style.css 切出來）；sealWatched、sealTitle 留在 app.js 伺服器推送那一段
    prefix = "seal"  # 選項前綴 seal:（碎片卡、獨門行動、奪璽單挑的三招）；第 28 批登記，choose、menu 不接（MENU_ORDER 的 front、quick 那兩格）
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：抄本 heirloom（傳承那一格，照全服登記重抄）、補送到第幾號 seal_seen。
    # 換季（season.carry 那一格）兩個都照帶；heirloom 換季後建 Game 時照登記重抄（copy_heirloom），所以不算帶走的
    player_fields = ("heirloom", "seal_seen")
    carried: tuple[str, ...] = ("seal_seen",)
    # 七片碎片（content.py 照它到這一包的 content/ 載、照舊驗：_validate_seal 留原處，不接 check_content，第 34 批認定第 2 條）；檔名照舊
    content = ("seal.json",)

    def enabled(self, ctx) -> bool:
        """碎片開著：Config.seal.enabled，而且內容有 content/seal.json（seal.on）。掛鉤都不問它。"""
        from . import seal  # noqa: PLC0415

        return seal.on(ctx.content)

    def bot_pick(self, ctx, option):
        """假人看到 seal: 那一顆的分數（原本 bot_policy.score 的 seal 那一段）：一律不按。"""
        from . import bots  # noqa: PLC0415

        return bots.score(option)

    # 接縫掛鉤（第 11 批）
    def deliver_results(self, ctx) -> None:
        """收場補送那一格（sync；原本緊接在 features_core.deliver_results 後面的 Game._deliver_seal_results）：玉璽碎片的事補送到自己
        手上（actions.deliver_results）。不問 enabled（補送本身只看 content.seal：主機關掉開關也照補）；排在決戰包後面，先後跟原本一樣。"""
        from . import actions  # noqa: PLC0415

        actions.deliver_results(ctx)

    # core_eventbus（全部拆包第 26 批「事件機制」）
    _bus: tuple[BusHook, ...] | None = None

    def bus(self) -> tuple[BusHook, ...]:
        """事件 outing 的 seal 那一格（探索一顆收尾：撿玉璽碎片，排在打探懸賞之後；原本核心 engine._BUS_CORE 代叫 Game._seal_find）與
        battle_end 的 seal 那一格（時刻表決戰收場，回 None、不接；原本代叫 Game._seal_settle）。不問 enabled（判斷都在被叫的函式裡）。
        建一次就留著，在叫的那一下才照模組屬性找 actions.seal_find、actions.settle（scripts/measure_seal.py 換掉 settle 照樣打得到）。"""
        if self._bus is None:
            from . import actions  # noqa: PLC0415

            self._bus = (
                BusHook("outing", "seal", lambda ctx, loc_id: actions.seal_find(ctx, loc_id)),
                BusHook("battle_end", "seal", lambda ctx, battle, definition, result: actions.settle(ctx, battle, definition, result)),
            )
        return self._bus

    # core_world（全部拆包第 25 批「世界層掛鉤」）
    _world: tuple[WorldHook, ...] | None = None

    def world(self) -> tuple[WorldHook, ...]:
        """世界層的五格（原本核心代叫：world._MUSTER_CORE 的 seal、sqlite_world 的 _open_core、_next_core 的 seal.*、_RETIRE_CORE 的 seal）：
        集結那一刻擲現世與璽動（seal.on_muster）、開季藏一片（season.stamp_cache）、換季蓋天命之季的章（content.seal 與 Config.seal.enabled
        都開著才叫，原位就是這樣）與藏一片、舊季收尾（season.retire，回寫了上一季的江湖史沒）。格的位置照 WORLD_ORDER、簽名照原樣；
        不問 enabled。建一次就留著，在叫的那一下才照模組屬性找。"""
        if self._world is None:
            from . import season, seal  # noqa: PLC0415

            self._world = (
                WorldHook("muster", "seal", lambda store, content, definition, start, now: seal.on_muster(store, content, definition, now)),
                WorldHook("open", "seal.cache", lambda state, content, now: season.stamp_cache(state, content)),
                WorldHook("next", "seal.mandate", lambda state, content, now, old: (
                    season.stamp_mandate(state, content) if content.seal and content.config.seal.enabled else None)),
                WorldHook("next", "seal.cache", lambda state, content, now, old: season.stamp_cache(state, content)),
                WorldHook("retire", "seal", lambda state, content, now, seen_real: season.retire(state, content, now, seen_real)),
            )
        return self._world

    # core_effects（全部拆包第 32 批「效果與叛投掛鉤」）
    _effects: tuple[EffectHook, ...] | None = None

    def effects(self) -> tuple[EffectHook, ...]:
        """效果的兩格（原本核心 rules._EFFECT_CORE 延後 import 代叫）：符文殘片（runic）、舊鏈的玉璽碎片（shard，排在江湖史之後）。
        不問 enabled。建一次就留著，在叫的那一下才照模組屬性找 seal.effect_runic、seal.effect_shard。格的位置照 EFFECT_ORDER。"""
        if self._effects is None:
            from . import seal  # noqa: PLC0415

            self._effects = (
                EffectHook("runic", lambda r: seal.effect_runic(r)),
                EffectHook("shard", lambda r: seal.effect_shard(r)),
            )
        return self._effects

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """補算與換季的四格（順序在 SEAM_ORDER；不問 enabled）：sync 補算自己的時間之前、清失效參照中段照登記重抄抄本（actions.copy_heirloom：碎片關著時也要叫、
        把抄本清掉，on_sync、on_drop_stale 只問開著的包，接不了）；排程那一下推奪璽單挑（duel_actions.tick）；換季照帶。建一次就留著，在叫的那一下才照模組屬性找。"""
        if self._seams is None:
            from . import actions, duel_actions  # noqa: PLC0415

            self._seams = (
                SeamHook("sync.heirloom", "seal", lambda ctx: actions.copy_heirloom(ctx)),
                SeamHook("stale.mid", "seal", lambda ctx: actions.copy_heirloom(ctx)),
                SeamHook("tick", "seal", lambda ctx: duel_actions.tick(ctx)),
                SeamHook("season.carry", "seal", _carry_season),
            )
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單的三格（順序在 MENU_ORDER；不問 enabled）：誰輪詢誰推奪璽單挑（tick，同決戰，5.4）；單挑的那幾顆排在決戰的鈕與平常的選單最前面（front）；
        按下去的那一招不建紀錄（quick，第 57 批；收場由 _deliver_seal_results 補一份戰報與一則紀錄，5.9）。"""
        if self._menus is None:
            from . import duel_actions  # noqa: PLC0415

            self._menus = (
                MenuHook("tick", "seal", lambda ctx: duel_actions.tick(ctx)),
                MenuHook("front", "seal", lambda ctx: duel_actions.options(ctx)),
                MenuHook("quick", "seal", lambda ctx, kind, arg, option_id: duel_actions.act(ctx, arg) if kind == "seal" else None),
            )
        return self._menus

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的兩個插句（fame_seal、land_seal，核心 HOWTO_INSERTS）：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (
            HowtoHook("fame_seal", lambda content, season, page: words.fame_seal(content)),
            HowtoHook("land_seal", lambda content, season, page: words.land_seal(content)),
        )

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import card, duel_actions  # noqa: PLC0415

            self._status_slots = (
                # 奪璽卡（玉璽碎片設計 5.10）：全服看得到，沒有單挑是 None；持有者的碎片卡（第十節）；seal_watch 為真時網頁在背景也輪詢、輪到出招改分頁標題（5.5）
                StatusHook("status", "seal", lambda ctx, frame: {"seal_duel": duel_actions.duel_card(ctx), "seal": card.view(ctx), "seal_watch": duel_actions.watch(ctx)}),
                # 管理頁的玉璽一組（碎片關著是 None，不畫；第二輪第 90 批從殼的 admin_choices 搬來）
                StatusHook("admin", "seal", lambda ctx, frame: {"seal": ctx.admin_seal_choices()}),
            )
        return self._status_slots

    def main_actions(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.main_actions(shell)

    def admin_tools(self, shell) -> dict:
        from . import routes  # noqa: PLC0415  只在殼建動作表時才 import（同 routes 掛鉤）

        return routes.admin_tools(shell)

    def outlock(self, shell):
        from . import routes  # noqa: PLC0415  只在殼建鎖外工作時才 import（同 routes 掛鉤）

        return routes.outlock(shell)


def _carry_season(ctx, old, fresh) -> None:
    fresh.player.heirloom = old.player.heirloom  # 玉璽碎片的抄本與補送的進度跨季帶走（玉璽碎片設計 7.5；同步時本來就照登記重抄）
    fresh.player.seal_seen = old.player.seal_seen


FEATURE = SealFeature()
