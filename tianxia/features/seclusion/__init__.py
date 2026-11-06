"""閉關（功能包；開發規範手冊 3.2；全部拆包第 39 批，小包併批）。README.md 寫這一包做什麼、導覽與設計稿。

- actions.py：原本 Game 上的 seclusion_refusal、seclude、_finish_seclusion（Game 留一行委派給 server 的修練頁、_advance_player_local 與測試）

閉關鈕在修練頁（server 的 /api/do/seclude → Game.seclude）；閉關中選單只剩 act:break 與擂台入口（核心 _everyday_options 原位，總表第 57 批才碰）。
按 act:break 提早出關由這一包的 Verb("break") 接走。沒有選項前綴、沒有選單、沒有 bots.py（假人不閉關）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, SeamHook, Verb


class SeclusionFeature(Feature):
    name = "seclusion"
    prefix = None  # 沒有選項前綴：act:break 是核心 act 的子動詞，走 verbs()
    player_fields = ("seclusion_start", "seclusion_done")  # 閉關開始的時刻、上一次出關的時刻（天時地利「心靜」讀）；busy_until 是核心的，不認領
    carried: tuple[str, ...] = ()  # 換季照 _reset_player_for_new_season 重來

    def enabled(self, ctx) -> bool:
        return False  # 沒有遊戲當下的掛鉤要問（verbs 不看 enabled：原位本來就不看開關）

    _verbs: tuple[Verb, ...] | None = None

    def verbs(self) -> tuple[Verb, ...]:
        """act:break 的主人（act 子動詞）：按下去提早出關（原本 Game._act 在 features_core.act 之後那一支，回 _finish_seclusion 的句子）。
        標題不給（Game._action_title 走預設的「提前出關」）。不問 enabled。建一次就留著，在叫的那一下才照模組屬性找 actions.finish
        （monkeypatch 照樣有效）。"""
        if self._verbs is None:
            from . import actions  # noqa: PLC0415

            self._verbs = (Verb("break", run=lambda ctx, prepared: actions.finish(ctx, ctx.state.world.time)),)
        return self._verbs

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """local 的 seclusion 那一格（順序在 SEAM_ORDER；不問 enabled）：補算自己的時間最後，自己滿時的出關（actions.finish_due），排在福緣之前。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (SeamHook("local", "seclusion", lambda ctx: actions.finish_due(ctx)),)
        return self._seams


FEATURE = SeclusionFeature()
