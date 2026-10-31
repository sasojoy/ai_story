"""全服決戰「看」那一半的字、常數與鎖外三段式的兩張單子（主動搬六包第 5 批；原本寫在 engine.py 的模組層與 Game 的類別屬性）。
純資料，不碰存檔、不碰 Game。engine 照舊留著測試從那裡拿的幾個名字（ESCORT_MUSTER、ESCORT_SCENE、RESTORED_NOTE、ROUND_BLOCKS、
TROOPS_LINE、TROOPS_REPORT）與 Game.BATTLE_GAMBLE_NOTE／BATTLE_GAMBLE_LAST，都指到這裡同一個值。
"""
from __future__ import annotations

from pydantic import BaseModel

from tianxia import battle_instance  # 過渡：待搬（戰鬥規則核心：補劇情的單子用它的 TaleItem）

ROUND_BLOCKS = 5  # 決戰場景上留最近幾段戰況（開打那一句也算一段）
GAMBLE_SAID = "放手一搏：「"  # battle_instance.resolve_round 寫「某某放手一搏：「…」（評估成功率 N%）」那一行的認法
SIDE_TAG = "〔{side}〕"  # 戰況每一條是哪一軍的（Joy 2026-10-14）；網頁 app.js 的 roundBlocks 認這個寫法
ROUND_HEAD = "##### 第 {n} 回合"  # 一回合一段的標題（Joy 2026-10-14）；網頁 app.js 的 ROUND_HEAD 認這個寫法
RESTORED_NOTE = "（這份戰報是後來補回來的；軍餉與名望當時已經發過。）"  # view.restore_showdowns
RESULT_LOOKBACK = 50  # 補戰報往回讓幾場流水號（攻城戰同時打，先開的可能晚收場；一天最多四場，五十場是十來天）
# 決戰戰況裡一軍這一回合發動戰法的那幾句摺成一行（Joy 2026-10-30「一堆好像是武學的技能，有什麼實質的作用」）：照 kind 歸成看得懂的幾類，
# 點開才是逐人那幾句（網頁 roundBlocks 把巢狀的那一層畫成摺疊）；自己的那一句不摺。沒列到的 kind 歸「其他」
WAR_FOLD = "{side}本回合 {n} 人發動武學"
WAR_FOLD_KINDS = {
    "回氣血": ("mend", "drain", "rally", "cleanse"),
    "加重": ("heavy_blow", "tiger", "waver", "bloodrage", "marshal", "tide", "night_raid", "reinforce", "sacrifice", "momentum", "assault", "zhaoyi"),
    "連環": ("chase_disarm", "vanguard", "surge", "cavalry", "swift", "last_rally", "oath"),
    "化影": ("veil", "shadow"),
    "無隙": ("unbroken", "flawless", "streak"),
    "固守": ("steady", "hold_city"),
    "號令": ("order",),
}
WAR_FOLD_MIN = 2  # 一軍這一回合至少幾句才摺（只有一句照舊一行）
MY_MOVE = "**你**　{move}"  # 決戰戰報的完整戰況：每一回合最後一條，自己這一回合出了什麼（BattleParticipant.moves）
SLAY_LINE = "你陣前擊退了{name}，這一戰的頭功傳遍兩軍。"  # 待 joy 潤：龍頭上陣，最後一擊的人（戰報與紀錄）
# 歷史武將同行第五節（待 joy 潤）：決戰畫面上自己的那一位（加入時挑一位隨你上陣那幾句是「打」那一半，還在 engine）
ESCORT_MUSTER = "{name}隨你出陣。"
ESCORT_SCENE = "隨你出陣：{name}（氣血 {hp}/{cap}）"
ESCORT_FELL = "隨你出陣：{name}（敗走）"
TROOPS_LINE = "你帶著{names}上陣，強攻、奇襲多 {pct}"  # 待 joy 潤（PM 2026-10-12）：決戰畫面，接在騎兵那一句後面（加入時的快照）
TROOPS_REPORT = "{names}跟著你衝陣"  # 待 joy 潤（PM 2026-10-12）：決戰的戰報
SHOWDOWN_TIER4 = "論功行賞，另得四階料【{name}】一個。"  # 待 joy 潤：時刻表決戰得勝那一方出手夠的人（正式季整合 4.5）

# 放手一搏輸入框旁邊那一句（試玩回饋 2026-10-08）：成功率照舊不事前顯示（賭局的感覺），只講清楚賭的是什麼
BATTLE_GAMBLE_NOTE = "寫得越險，成了戰果越大；失手時大局只會小小倒退，重傷的是你自己，氣血見底就倒下出局。"

# 氣血池撐不過一次最壞的失手時多這一句（長社火攻 14 個真人倒下 12 個，都是自己放手一搏失手扣光的；PM 2026-10-15）。
# 不寫數字
BATTLE_GAMBLE_LAST = "你的氣血已經撐不住再一次失手——這一搏若是沒成，你就倒下了。"


class BattleTextRequest(BaseModel):
    """放手一搏鎖外評估的單子（server.py 的 A 段拿到、B 段送模型評成功率、C 段交回 submit_battle_custom_action 重驗才送出）。"""
    battle_id: str
    act_index: int  # 送出時是第幾幕：評分照這一幕的情境（C 段送出時換了幕也照這個評過的分）
    faction_name: str
    text: str
    name: str = ""  # 送出的人的名號：劇情以他開頭（試玩回饋 2026-10-08）
    sex: str = "男"  # 送出的人的性別（gender）：模型寫劇情時的稱呼
    target: str = ""  # 點名的對手與身手（battle_instance.target_line，Joy 2026-10-10）：給模型多一行；沒點名是空的


class BattleTaleRequest(BaseModel):
    """回合結算後補放手一搏劇情的單子（server.narrate_battle 的 A 段拿到、B 段一整批送模型寫、C 段交回 apply_battle_tales
    重驗同一場才補）。done 是這一批的（回合, 名號）：寫到沒寫到，C 段都從等著補的單子拿掉。"""
    battle_id: str
    record_id: int | None
    opened: float  # 這一場集結截止的時間：跟 battle_id、record_id 一起認同一場
    act_index: int
    items: list[battle_instance.TaleItem]
    done: list[tuple[int, str]]
