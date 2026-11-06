"""人物性子（功能包；開發規範手冊 3.2）：跟人物說話會慢慢把他的性子往某一頭推（設計稿「人物性子會變」，Joy 2026-11-06「可以」）。
這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

- rules.py：純規則（記一筆、每天結算、換段、行狀、對話提示、簡介）。
- 對話那一輪的歸類與提示接在 companion_agent（舊模組，還沒搬：它叫 rules.ends_for、prompt_lines、hear、covers）。
- 這裡的掛鉤：on_sync 替全服結算到今天、記勸過的人的行狀；check_content 驗 content/personas.json。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class PersonaFeature(Feature):
    name = "persona"
    prefix = "persona"  # 沒有選項；前綴留著（核心只把這個前綴的 id 交給這一包）
    content = ("personas.json",)  # content.py 照舊讀進 Content.personas
    player_fields: tuple[str, ...] = ("persona_notes",)
    carried: tuple[str, ...] = ()  # 換季跟著新角色重來（Joy 11/6「全部歸回本性」）

    def enabled(self, ctx) -> bool:
        from . import rules  # noqa: PLC0415

        return rules.on(ctx.content)

    def on_sync(self, ctx, elapsed) -> None:
        from . import actions  # noqa: PLC0415

        actions.on_sync(ctx)

    def check_content(self, content, need) -> None:
        from . import checks  # noqa: PLC0415

        checks.check(content, need)


FEATURE = PersonaFeature()
