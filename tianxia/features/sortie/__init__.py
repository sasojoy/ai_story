"""出陣（投靠了陣營的人在領地爭奪的區塊上攻、守；混戰；出陣回報）。功能包，開發規範手冊 3.2；主動搬六包第 1 批搬進來。
README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：純規則（原 tianxia/sortie.py；那個名字留成指到這裡的別名）
- actions.py：原本 Game 上出陣本體、混戰、出陣回報的 21 個方法（Game 留 13 個一行委派）

這一批不拿選項前綴（prefix 是 None）：出陣那一格的 id 照留核心的 act:train（遊歷、序章的雪恥、並肩出陣、大場面判讀都認它），
分派留在 Game._act；約戰的 sortie:* 是第 2 批。所以這一包現在只接 enabled 與欄位，假人照舊走 bot_policy。
換季照帶今天出陣的次數（carried 那兩格）照舊寫在 Game._reset_player_for_new_season、不掛 on_season_start：遊戲當下的掛鉤只叫
開著的包，掛在這裡的話地盤關著的那一季就不帶了（同商城的 carried；dev/sortie-1 審查，tests/test_sortie_season_carry.py 守）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class SortieFeature(Feature):
    name = "sortie"
    prefix: str | None = None  # 第 2 批（出陣約戰）拿 sortie:；act:train 是核心的前綴
    # 今天出陣幾次（換日同回體丹）、這一季出陣攻打打贏掉過幾件寶物與良駒（treasures.sortie_rare 的一季上限）
    player_fields = ("sortie_day", "sorties_today", "sortie_treasures", "sortie_horses")
    carried = ("sortie_day", "sorties_today")  # 換季不能多出一輪陣（Game._reset_player_for_new_season 照帶）；掉寶的上限跟著新的一季重來

    def enabled(self, ctx) -> bool:
        """出陣開著：地盤（＝領地爭奪）開著就有，沒有自己的開關（rules.on 就是 territory.on，只看內容）。"""
        from tianxia import territory  # noqa: PLC0415  過渡：待搬（地盤；出陣沒有自己的開關）

        return territory.on(ctx.content)


FEATURE = SortieFeature()
