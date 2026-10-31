"""全服決戰（官軍、黃巾兩軍在一個大區集結、一回合一回合打；收場之後每個人下一次同步補戰報、江湖紀錄、軍餉、行狀）。功能包，開發規範手冊 3.2；
主動搬六包第 5 批搬進「看」的那一半。README.md 寫這一包做什麼、導覽與設計稿、認領的欄位、還留在原位的接縫。

- rules.py：決戰畫面與戰報的字、常數，鎖外三段式的兩張單子（放手一搏評分、補劇情）
- view.py：原本 Game 上「看」那一半的 31 個方法——場景、戰局條、攻城條、一回合一段的戰況、收場補送（戰報、江湖紀錄、軍餉、行狀、戰功）、
  補回被洗掉的戰報、放手一搏的輸入框與三段式、補劇情（Game 留 22 個一行委派）

這一批不拿選項前綴（prefix 是 None）：battle: 的分派（集結、投效、挑同伴、出招）是「打」那一半，還在 Game（第 6～8 批），第 7 批搬集結時
拿前綴、同時把 bot_policy.score 的 battle: 那一段搬進這一包的 bots.py。所以這一包現在只接 enabled 與欄位，假人照舊走 bot_policy。
換季照帶補過的決戰（carried 那一格）照舊寫在 Game._reset_player_for_new_season、不掛 on_season_start（同出陣第 1 批審查之後的做法）。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class BattleFeature(Feature):
    name = "battle"
    prefix: str | None = None  # 第 7 批（集結）拿 battle:；這一批搬的「看」那一半沒有選項
    content = ("battles.json",)  # 決戰與攻城範本（content.py 照舊讀；攻城的規則在 siege.py，共用規則層）
    # 補過的決戰（跨季照帶：決戰常把季收掉，下一季才回來的人也要補、而且只補一次）、這一季參戰幾場與首功幾次（玩家卡、名帖）。
    # showdowns_restored（補回被洗掉的戰報，一季查一次）也是這一包的，但每一季第一次同步就寫成那一季的編號：契約測試的「換季回到預設」
    # 對它不成立，不放進來（README 照列）
    player_fields = ("battle_results_seen", "showdowns", "top_merits")
    carried = ("battle_results_seen",)  # Game._reset_player_for_new_season 照帶（不看開關，同商城、出陣的 carried）

    def enabled(self, ctx) -> bool:
        """內容裡有決戰（battles.json）就有：決戰本身沒有開關（beta、第一季、減法季都打）。這一包的掛鉤全是預設的空的，開著關著結果都一樣。"""
        return bool(ctx.content.battles)


FEATURE = BattleFeature()
