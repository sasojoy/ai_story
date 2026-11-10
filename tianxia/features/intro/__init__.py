"""開局前導（功能包；開發規範手冊 3.2）：新角色取完名號、站到潁川城門口之前，演一段不到一分鐘的水墨畫本——時空背景與四位大勢人物
（張角、皇甫嵩、朱儁、波才）。可以跳過，看過不再自動播，設定裡能重看。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

沒有選項、沒有 PlayerState 欄位（看過記在 flags）。接 status_slots（狀態列 intro 那一格：要不要先看）、routes（畫本、記看過）、check_content。
內容檔 content/intro.json 由這一包自己讀（rules.load），content.py 不讀它。
"""
from __future__ import annotations

from tianxia.core.features import Feature, StatusHook


class IntroFeature(Feature):
    name = "intro"
    prefix = None  # 沒有選項：畫本是一層蓋在江湖頁上的畫面
    web: tuple[str, ...] = ("intro.js", "intro.css")
    content: tuple[str, ...] = ("intro.json",)
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        return ctx.content.config.intro.enabled  # 預設關：Config.intro.enabled（tianxia/core/tuning/intro.py）

    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """狀態列 intro 那一格（接在 status 表尾；不問 enabled，所以自己問）：開著才有這個鍵，pending 是這個角色現在要不要先看。"""
        if self._status_slots is None:
            from . import rules  # noqa: PLC0415

            def run(ctx, frame) -> dict:
                if not self.enabled(ctx):
                    return {}
                return {"intro": {"pending": rules.pending(ctx)}}

            self._status_slots = (StatusHook("status", "intro", run),)
        return self._status_slots

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只有殼掛路由時才 import（routes 要 fastapi）

        return routes.router(shell)

    def check_content(self, content, need) -> None:
        from . import rules  # noqa: PLC0415

        for problem in rules.check(content):
            need(False, problem)


FEATURE = IntroFeature()
