from typing import TYPE_CHECKING, Optional

from src.models import GameStateDelta

if TYPE_CHECKING:
    from src.npc_agent import NPCAgent

# 獨立成一個小檔案而不是放進 src/rules.py：rules.py 會 import src/state.py，
# state.py 又 import src/npc_agent.py（NPCAgent 是 GameState.agents 的欄位型別），
# 如果這裡放進 rules.py，npc_agent.py 要用這裡的東西就會形成循環 import。

THREAD_CATEGORIES = {"B", "C", "D"}
# 原本 100（通常要鎖定 3~4 回合才收尾）；實測發現連續同質語境會提高小模型復讀崩潰的機率，
# 帳號存檔顯示鎖定情慾線後幾乎每回合都在復讀，改成 60 讓鎖定通常 1~2 回合就自然收尾，
# 縮短模型停留在同一種語氣情境的時間，同時仍保留「延續同一主題」的連貫性效果。
THREAD_INTENSITY_THRESHOLD = 60
THREAD_INTENSITY_BASE_STEP = 20

THREAD_CATEGORY_LABELS = {
    "B": "謀略/智取/談判",
    "C": "情慾/色誘/雙修",
    "D": "混亂/背叛/暗黑",
}

THREAD_RESOLVE_HINTS = {
    "B": "讓這場謀略博弈或談判走向一個明確結論",
    "C": "讓這段情感試探或雙修互動迎來一個關鍵轉折",
    "D": "讓這段背叛或混亂局勢迎來一次爆發性轉折",
}

# 給保底 (fallback) 劇情用的收尾句——LLM 完全連不上時，也要讓收尾回合讀起來像個收尾，
# 而不是隨機接上一句跟前面語氣不搭的通用保底劇情。跟 THREAD_RESOLVE_HINTS 分開維護是
# 因為 HINTS 是寫給 LLM 的指令語氣（「讓...迎向轉折」），這裡要的是能直接顯示給玩家看的
# 敘事散文，兩者文體不同，硬共用會讀起來很怪。
THREAD_FALLBACK_RESOLUTION_TEXT = {
    "B": "這場謀略交鋒到此似乎有了眉目，雙方都心照不宣地暫時按下不表，氣氛微妙地鬆懈下來。",
    "C": "這番旖旎纏綿在燭光搖曳中漸漸平息，兩人相視一笑，心照不宣地拉開了些許距離，空氣中還殘留著一絲曖昧的餘溫。",
    "D": "這場暗潮洶湧終於告一段落，剛才劍拔弩張的氣氛總算緩和下來，只是彼此眼底都還留著幾分警惕。",
}


def update_thread_state(agent: "NPCAgent", chosen_category: Optional[str], delta: GameStateDelta) -> None:
    """主題線鎖定狀態機：玩家從中立狀態選了 B/C/D 其中一類後，接下來幾回合的選項會朝同一
    主題延伸（A~D 四格都圍繞同一主題發想變體，E 維持地圖探索/轉移不變，作為隨時可脫離的
    逃生口），直到累積張力 (thread_intensity) 到門檻，下一回合先讓劇情自然收尾
    (thread_climax_pending)，收尾完那一回合結束後才真正重置回五種類型都開放的中立狀態。
    三個主題各自借用既有欄位當累積訊號，不新增 LLM 輸出欄位，避免加重小模型的 JSON 負擔：
    C 用 intimacy_change、D 用 faction_reputation_changes 變動幅度、B 用
    milestone_unlocked/main_quest_summary_update 是否有更新。"""
    if agent.thread_climax_pending:
        agent.active_thread = None
        agent.thread_intensity = 0
        agent.thread_climax_pending = False
        return

    if agent.active_thread is None:
        if chosen_category in THREAD_CATEGORIES:
            agent.active_thread = chosen_category
            agent.thread_intensity = THREAD_INTENSITY_BASE_STEP
        return

    if chosen_category == "E":
        agent.active_thread = None
        agent.thread_intensity = 0
        agent.thread_climax_pending = False
        return

    bonus = THREAD_INTENSITY_BASE_STEP
    if agent.active_thread == "C":
        bonus += abs(delta.intimacy_change)
    elif agent.active_thread == "D":
        bonus += sum(abs(v) for v in delta.faction_reputation_changes.values())
    elif agent.active_thread == "B":
        if delta.milestone_unlocked or delta.main_quest_summary_update:
            bonus += THREAD_INTENSITY_BASE_STEP

    agent.thread_intensity += bonus
    if agent.thread_intensity >= THREAD_INTENSITY_THRESHOLD:
        agent.thread_climax_pending = True
