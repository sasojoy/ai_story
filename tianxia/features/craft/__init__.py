"""煉製與自創（功能包；開發規範手冊 3.2）：煉製頁的意境開爐（兩個意境合成或同一種的兩份揣摩，取名的三段式、預覽）與自創武學五步
（執器、擺式、立意、成形、立名）、重悟帖、作罷。全部拆包第 44 批搬進來（計畫 docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md）。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- create.py：自創的規則（原 tianxia/create.py；舊名留成別名）。擺式的幾何抽到共用規則層 tianxia/pose.py，create 照名字 re-export
- actions.py：原本 Game 上的 16 個方法（Game 留 16 個一行委派給 server、假人、測試與核心原位、引導包）
- routes.py：/api/forge_line（原本寫在 server.py；殼照 FEATURES 掛）

掛鉤：routes、content（create_forms.json）、on_drop_stale（內容改版後內容裡沒有這個器的舊單子收掉，原本接在 _drop_stale_references 的 arts_mod.prune 之後）。
沒有選項前綴、沒有 choose：煉製頁全是網頁按鈕打 /api/menxia/<op>。假人經 Game 的公開方法碰這一包（bot_policy.tend_arts、bot.create_art）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, StatusHook


class CraftFeature(Feature):
    name = "craft"
    prefix = None  # 沒有選項前綴：煉製頁全是網頁按鈕打 /api/menxia/<op>、/api/do/<op>
    web = ("craft.js", "craft.css")  # 煉製頁的畫法（全部拆包第 64 批從 app.js 切出來）；點擊分派的 case、renderPage 的 fixedKiln 照舊在 app.js（殼）。css 第 67 批才切
    content = ("create_forms.json",)  # content.py 照舊讀（自創的偏向表、擺式預設、招式表）；preset_recipes.json 是序章、命名、引導共用的，不歸這一包
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：自創走到一半的單子、這一季自創付了幾次心得。換季跟著新角色重來。
    # 重悟帖張數 create_rerolls 歸商城（player_fields／carried）；意境 insights、own_insights 是共用規則層的
    player_fields = ("creating", "created_count")
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """一直開著：煉製頁每一季都有（自創有沒有開看 Config.arts.create_xinde，由 create.allowed 擋，原位本來就不看開關）。"""
        return True

    def on_drop_stale(self, ctx) -> None:
        """自創的舊三步單子收掉（還沒付錢；create.prune）。原本接在 _drop_stale_references 的 arts_mod.prune 之後，現在接在最後——
        中間到 features_core.on_drop_stale 沒有任何一行讀 creating。"""
        from . import create  # noqa: PLC0415

        create.prune(ctx.state, ctx.content)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import actions  # noqa: PLC0415

            self._status_slots = (
                # 自創武學那一塊（煉製頁）
                StatusHook("status", "create", lambda ctx, frame: {"create": actions.view(ctx)}),
            )
        return self._status_slots


FEATURE = CraftFeature()
