"""有所感與頓悟（功能包；開發規範手冊 3.2）：探索撞上有所感（選做法、擲中、畫一筆或順其自然）、自己畫字悟出的意境（看圖取名的三段式）、
特殊頓悟（心靈拷問、心境小試、心魔、取名）。全部拆包第 24 批搬進來。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- sensing.py：有所感的規則（原 tianxia/sensing.py）；epiphany.py：特殊頓悟（原 tianxia/epiphany.py：import 的時候登記一條線的鉤子）；
  glyph.py：讀筆畫（原 tianxia/glyph.py）；insight_llm.py：看圖取名的 B 段（原 tianxia/insight_llm.py）——舊名都留成別名
- actions.py：原本 Game 上的 10 個方法（Game 留 8 個一行委派）與核心原位、探索包、引導包叫的 7 個服務的本體
- routes.py：/api/sense、/api/sense_read、/api/sense_warm（原本寫在 server.py；殼照 FEATURES 掛）

掛鉤：choose（只吃 sense:；dunwu: 要帶自己寫的名字，留在 Game.choose 原位叫委派）、scene（接縫掛鉤：有所感的卡、取名那一張）、routes。
"""
from __future__ import annotations

from tianxia.core.features import Feature, HowtoHook, MenuHook, Outcome, SeamHook, StatusHook
from tianxia.core.features import ContentSlot


class SenseFeature(Feature):
    name = "sense"
    web = ("sense.js",)  # 有所感的畫布、悟來的那一筆、神品意境取名（全部拆包第 66 批從 app.js 切出來）；OWN_NAME_* 第 67 批從 main.js 切進來
    # sense:<做法>、sense:draw、sense:let（有所感）；dunwu:think、dunwu:<候選>、dunwu:own（特殊頓悟取名）。Feature.prefix 收 tuple（第 11 批）
    prefix = ("sense", "dunwu")
    content = ("insight_scenes.json",)  # content.py 照它到這一包的 content/ 載、content.check_insight_scenes 照舊驗（核心沒有 import 這一包）；檔名照舊
    # 認領的 PlayerState 欄位（手冊 3.5：留在原地）：有所感那一份與流水號、選錯的帳；特殊頓悟這一季的次數與保底、等著取名的那一個。
    # 換季全部跟著新角色重來（Game._reset_player_for_new_season 本來就不帶）。私有意境 own_insights／own_serial 是共用規則層 insights 的（合成也寫）
    player_fields = ("sensing", "sense_serial", "sense_misses", "epiphanies", "epiphany_dry", "god_naming")
    carried: tuple[str, ...] = ()

    # core_content（第二輪第 100 批）：位置固定的內容驗證，先後在 content.validate 那幾行，格在核心 CONTENT_SLOTS；在叫的那一下才照模組屬性找
    def content_slots(self) -> tuple[ContentSlot, ...]:
        from . import checks  # noqa: PLC0415

        return (
            ContentSlot("insight_scenes", lambda *a: checks.check_insight_scenes(*a)),
            ContentSlot("insight_strong", lambda *a: checks.check_insight_strong(*a)),
        )

    def enabled(self, ctx) -> bool:
        """一直開著：有所感沒有總開關（有沒有場景看內容 content/insight_scenes.json），特殊頓悟看自己的 Config.epiphany——
        搬包之前 choose 的 sense、dunwu 兩支與選單、場景都不看任何一包的開關。"""
        return True

    def choose(self, ctx, kind, arg):
        """sense:<做法>、sense:let（原本 Game.choose 的 sense 那一支叫 Game._sense；「畫下來」sense:draw 在建紀錄之前就回了，MENU_ORDER["quick"] 那一格）：標題照
        原本 Game._action_title 的 sense 那一支（「有所感・場景」，動作之前先拿）。dunwu: 不接（自己寫的名字在 Game.choose 的 text，
        掛鉤不帶），留在原位叫 Game._epiphany_name。"""
        if kind != "sense":
            return None
        from . import actions  # noqa: PLC0415

        return Outcome(title=actions.sense_title(ctx), run=lambda: actions.sense(ctx, arg))

    def bot_idle(self, ctx, option) -> bool:
        """特殊頓悟取名的「自己寫」（dunwu:own）：要寫字，按了只回一句叫出輸入框，一直按得下去；整季機器人先按靜心思名、再從三個候選裡挑（原本 bot.pick 那一條，第 60 批；不問 enabled）。"""
        return option.id == "dunwu:own"

    def scene(self, ctx):
        """自己眼前的場景卡（接縫掛鉤，第 11 批；原本 Game._own_scene_text 宴客那一行之後的兩支）：有所感的卡、特殊頓悟取名那一張；
        都不是是 None。不問 enabled（原位本來就不看開關）。"""
        from . import actions  # noqa: PLC0415

        return actions.scene(ctx)

    def routes(self, shell):
        from . import routes  # noqa: PLC0415  只在殼掛的時候才 import（routes 用 fastapi）

        return routes.router(shell)

    # core_seams（全部拆包第 55 批「補算與換季收接縫」）
    _seams: tuple[SeamHook, ...] | None = None

    def seams(self) -> tuple[SeamHook, ...]:
        """stale.early 的 sense 那一格（順序在 SEAM_ORDER；不問 enabled）：有所感的場景被拿掉、人不在那裡了：作廢（後面的收店讀它，所以不放 on_drop_stale）。"""
        if self._seams is None:
            from . import actions  # noqa: PLC0415

            self._seams = (SeamHook("stale.early", "sense", lambda ctx: actions.sense_drop_stale(ctx)),)
        return self._seams

    # core_seams（全部拆包第 56 批「選單收接縫」）
    _menus: tuple[MenuHook, ...] | None = None

    def menus(self) -> tuple[MenuHook, ...]:
        """選單的三格（順序在 MENU_ORDER；不問 enabled）：有所感接管整個選單（擂台之後、一條線的答題之前；menu 掛鉤在擂台前面，接不了）；還沒了結不算閒著；
        「畫下來」只叫出畫布、不建紀錄（quick，第 57 批；畫完送出走 sense_request／sense_draw）。"""
        if self._menus is None:
            from . import actions  # noqa: PLC0415

            self._menus = (
                MenuHook("take", "sense", lambda ctx: actions.sense_menu(ctx)),
                MenuHook("idle", "sense", lambda ctx: ctx.state.player.sensing is not None),
                MenuHook("quick", "canvas", lambda ctx, kind, arg, option_id: actions.sense_canvas(ctx, option_id)),
            )
        return self._menus

    # howto（全部拆包第 59 批「引導二」）
    def howto(self) -> tuple[HowtoHook, ...]:
        """玩法說明的insight 那一格：順序在核心 HOWTO_ORDER，不問 enabled；在叫的那一下才照模組屬性找。"""
        from . import howto as words  # noqa: PLC0415

        return (HowtoHook("insight", lambda content, season, page: words.insight_section(content, season)),)

    # shell_web（全部拆包第 66 批：狀態列與江湖畫面的格，先後在 STATUS_ORDER；不問 enabled，原位那幾行本來就不看包的開關）
    _status_slots: tuple[StatusHook, ...] | None = None

    def status_slots(self) -> tuple[StatusHook, ...]:
        """建一次就留著，在叫的那一下才照模組屬性找（monkeypatch 照樣有效）；frame 見 core/features.py 的 StatusHook。"""
        if self._status_slots is None:
            from . import actions  # noqa: PLC0415

            self._status_slots = (
                # 有所感選做法那一步（explain-2）：做法鈕上寫的心意（選項 id → 剛柔快慢）與鈕底下兩行小字；不在選做法是 None
                StatusHook("main", "sense_help", lambda ctx, frame: {"sense_help": actions.method_help(ctx, (o.id for o in frame.options))}),
            )
        return self._status_slots


FEATURE = SenseFeature()
