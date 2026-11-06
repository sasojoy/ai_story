"""列傳（功能包；開發規範手冊 3.2）：一季的終點是一篇列傳——寫傳（鎖內開單、鎖外叫模型、鎖內重驗再存的三段式）、休季三顆（用列傳插畫、
蓋紀念印、請人物親筆評曰）、行狀頁與分享。全部拆包第 29 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- biography.py：人物列傳的規則（原 tianxia/biography.py）；zhuan_end.py：列傳為終點的規則（原 tianxia/zhuan_end.py；核心要用的那一段
  illustration_for／writers／art_problem 在 core/services.py，這裡 re-export）；zhuan_html.py：公開頁（原根目錄 zhuan_html.py）——舊名都留成別名
- actions.py：原本 Game 上的 20 個方法（Game 留 10 個一行委派，第 29 批之二加了換季存行狀的 profile）與休季用票的 choose
- standing.py：行狀的查詢與行狀頁那一半（第 29 批之二，原 tianxia/annals.py 的 profile、standing、tier_*、xingshi_notes、rows）；
  記一筆那一半在核心 core/annal_base.py，這裡 re-export，舊名 tianxia/annals.py 是指到這個模組的 sys.modules 別名
- routes.py：/api/annals、/api/zhuan、/api/zhuan/write、/api/zhuan/share、/zhuan/{code}（原本寫在 server.py；殼照 FEATURES 掛）

選項前綴 zhuan:（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物 id>）。掛鉤：choose_unlisted（原本 Game.choose 在 choose_unlisted 之後、查選單之前
那一行）、routes、check_content。沒有假人分數（假人在休季整個不動，碰不到 zhuan:）。
"""
from __future__ import annotations

from tianxia.core.features import Feature, MenuHook, SeamHook

from . import zhuan_end


class ZhuanFeature(Feature):
    name = "zhuan"
    prefix = "zhuan"
    content = ("verdicts.json",)  # content.py 照舊讀（核心沒有 import 這一包）；驗證在下面的 check_content
    # 沒有認領的 PlayerState 欄位：annals、annals_mark、xingshi_seen 是行狀，核心 core/annal_base.py 管；列傳存在資料庫的 biographies 表、票在錢包裡
    player_fields: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()

    def enabled(self, ctx) -> bool:
        """列傳為終點開著沒（Config.jianfa.zhuan_end 加開季的章）。沒有任何掛鉤吃這個開關：各個動作本來就各自問 zhuan_end.on。"""
        return zhuan_end.on(ctx.content, ctx.state.world)

    def choose_unlisted(self, ctx, option_id):
        """休季用列傳的票（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物>）：選單上有、亮著才接，不走行動那一串；不是回 None，核心照舊查選單。"""
        from . import actions  # noqa: PLC0415

        return actions.choose_unlisted(ctx, option_id)

    def check_content(self, content, need) -> None:
        """人物評曰的固定句（content/verdicts.json：理由、長度、沒有數字；原本是 content.validate 裡的 check_verdicts）。
        錯誤的字串前綴「verdicts.json：」照舊。"""
        for line in zhuan_end.check_verdicts(content):
            need(False, f"verdicts.json：{line}")

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """sync.deliver 的 zhuan 那一格（順序在 SEAM_ORDER；不問 enabled）：〈天下形勢〉寫到名號、季末論功各記一則行狀（心意的行狀之後、書信之前）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (SeamHook("sync.deliver", "zhuan", lambda ctx: actions.tick(ctx)),)
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單的一格（順序在 MENU_ORDER；不問 enabled）：休季那一顆後面，列傳為終點開著、手上有列傳的票時多幾顆用票的鈕（減法季批 7b；關著、沒票一顆不多）。"""
        if self._menus is None:
            from . import actions  # noqa: PLC0415

            self._menus = (
                MenuHook("rest", "zhuan", lambda ctx: actions.options(ctx)),
            )
        return self._menus


FEATURE = ZhuanFeature()
