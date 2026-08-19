import random
from typing import Any, Dict

from src.content_loader import load_json_or_default
from src.state import GameState


def load_npc_autonomy_config(path: str = "config/npc_autonomy.json") -> Dict[str, Any]:
    """讀取每個 NPC 的背景活動內容池；查無設定檔時回傳空 pool，NPC 自主行動會直接跳過"""
    return load_json_or_default(path, {"activities_pool": {}})


def simulate_npc_autonomous_actions(state: GameState) -> None:
    """每回合對非當前互動 NPC 進行一次背景活動推演與社交關係演變，並寫入江湖新聞牆。
    資料驅動化：活動內容池來自 config/npc_autonomy.json，取代原本寫死在程式碼裡的 activities_pool。"""
    activities_pool = load_npc_autonomy_config().get("activities_pool", {})
    current_npc_name = state.current_agent.profile.name if state.current_agent else ""

    for name, agent in state.agents.items():
        if name == current_npc_name:
            continue

        pool = activities_pool.get(name, [])
        if not pool:
            continue

        entry = random.choice(pool)
        act_text = entry.get("text", "")
        rel_changes = entry.get("relationship_changes", {})

        profile = agent.profile
        profile.current_activity = act_text
        profile.recent_activities.append(f"[第{state.game_turn}回合] {act_text}")
        if len(profile.recent_activities) > 5:
            profile.recent_activities = profile.recent_activities[-5:]

        for target_npc, change in rel_changes.items():
            curr_rel = profile.relationships.get(target_npc, 0)
            profile.relationships[target_npc] = max(-100, min(100, curr_rel + change))

        disp_name = profile.display_name or profile.name
        news_item = f"【江湖動態 · 回合{state.game_turn}】[{disp_name}] {act_text}"
        state.world_news.insert(0, news_item)

    if len(state.world_news) > 10:
        state.world_news = state.world_news[:10]
