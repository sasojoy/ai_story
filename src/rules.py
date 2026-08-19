from typing import Any, Dict, List, Optional

from src.content_loader import load_json_or_default
from src.models import GameStateDelta
from src.state import GameState


def load_npc_stages(path: str = "config/npc_stages.json") -> Dict[str, List[Dict[str, Any]]]:
    """讀取每個 NPC 的親密度分級設定；查無設定檔或格式壞掉時回傳空 dict，交由呼叫端 fallback"""
    return load_json_or_default(path, {}).get("npc_stages", {})


def get_intimacy_stage(npc_name: str, intimacy: int) -> Optional[Dict[str, Any]]:
    """依親密度查詢 config/npc_stages.json 對應的分級資料 (stage/stage_title/behavior/unlocked_topics)。
    查無該 NPC 資料 (或設定檔被改壞) 時回傳 None，呼叫端應 fallback 回舊版 25/50/75 寫死門檻確保向後相容。"""
    stages = load_npc_stages().get(npc_name)
    if not stages:
        return None
    for stage_info in stages:
        lo, hi = stage_info.get("intimacy_range", [0, 100])
        if lo <= intimacy <= hi:
            return stage_info
    return None


def get_intimacy_stage_number(npc_name: str, intimacy: int) -> int:
    """回傳 1~4 的親密度分級數字。查無該 NPC 的 npc_stages.json 資料時，
    fallback 回舊版寫死的 25/50/75 門檻 (對應 stage 1~4)，維持向後相容。"""
    stage_info = get_intimacy_stage(npc_name, intimacy)
    if stage_info:
        return stage_info.get("stage", 1)
    if intimacy >= 75:
        return 4
    if intimacy >= 50:
        return 3
    if intimacy >= 25:
        return 2
    return 1


def update_bound_npc_for_location(state: GameState, world_map: Dict[str, Any]) -> None:
    """依 state.current_location 對應 world_map 區域綁定的 NPC 更新 state.current_agent；
    查無綁定 NPC 且目前尚未選定任何互動對象時，退而選第一個可用的 NPC（僅用於初始化）"""
    regions = world_map.get("regions", {})
    reg = regions.get(state.current_location, {})
    bound_npc_name = reg.get("bound_npc", "")
    if bound_npc_name and bound_npc_name in state.agents:
        state.current_agent = state.agents[bound_npc_name]
    elif state.agents and not state.current_agent:
        state.current_agent = list(state.agents.values())[0]


def move_to_location(state: GameState, world_map: Dict[str, Any], location_name: str) -> bool:
    """切換玩家所在區域；驗證地點存在於 world_map，並依區域綁定更新 current_agent。
    刻意不在這裡觸發 NPC 自主行動模擬——呼叫端（GameEngine.interact* 或直接的地點移動事件）
    負責在整個「回合」結束時觸發恰好一次，避免同一回合觸發兩次
    （這是 ARCHITECTURE.md 記錄的既有 bug，Stage 7 順手修掉）。"""
    regions = world_map.get("regions", {})
    if location_name not in regions:
        return False
    state.current_location = location_name
    state.unlocked_locations.add(location_name)
    update_bound_npc_for_location(state, world_map)
    return True


def apply_delta(state: GameState, delta: GameStateDelta, world_map: Dict[str, Any]) -> None:
    """回合結算：套用 GameStateDelta 到 GameState（位置解鎖、HP/體力/背包、勢力聲望、
    親密度、雙修修為與升級、世界標記、主線摘要與里程碑、近期江湖動態）"""
    state.game_turn += 1

    if delta.current_location and delta.current_location.strip():
        move_to_location(state, world_map, delta.current_location.strip())

    for loc in delta.unlocked_locations:
        if loc and loc.strip():
            state.unlocked_locations.add(loc.strip())

    player = state.player_state
    player.hp = max(0, min(player.max_hp, player.hp + delta.player_hp_change))
    player.stamina = max(0, min(player.max_stamina, player.stamina + delta.player_stamina_change))
    player.gold = max(0, player.gold + delta.player_gold_change)
    player.charm = max(0, player.charm + delta.player_charm_change)

    if state.current_agent and delta.intimacy_change != 0:
        current_intimacy = state.current_agent.profile.intimacy
        state.current_agent.profile.intimacy = max(0, min(100, current_intimacy + delta.intimacy_change))

    if delta.cultivation_art_learned and delta.cultivation_art_learned.strip():
        art = delta.cultivation_art_learned.strip()
        if art not in player.cultivation_arts:
            player.cultivation_arts.append(art)

    if delta.cultivation_exp_gained > 0:
        player.cultivation_exp += delta.cultivation_exp_gained
        required_exp = player.cultivation_level * 100
        if player.cultivation_exp >= required_exp:
            player.cultivation_level += 1
            player.charm += 2
            player.max_stamina += 20
            player.stamina = player.max_stamina

    for item in delta.inventory_added:
        if item and item not in player.inventory:
            player.inventory.append(item)

    for item in delta.inventory_removed:
        if item in player.inventory:
            player.inventory.remove(item)

    for flag_key, flag_value in delta.world_flag_set.items():
        state.world_flags[flag_key] = flag_value

    if delta.main_quest_summary_update and delta.main_quest_summary_update.strip():
        state.main_quest_summary = delta.main_quest_summary_update.strip()

    if delta.milestone_unlocked and delta.milestone_unlocked.strip():
        ms = delta.milestone_unlocked.strip()
        if ms not in state.story_milestones:
            state.story_milestones.append(ms)

    for faction_name, reputation_change in delta.faction_reputation_changes.items():
        current_rep = state.factions.get(faction_name, 0)
        state.factions[faction_name] = current_rep + reputation_change

    if delta.narrative and delta.narrative.strip() and delta.narrative.strip() != "...":
        npc_n = state.current_agent.profile.name if state.current_agent else "NPC"
        event_summary = f"[{npc_n} - {state.current_location}] {delta.narrative[:40]}..."
        state.recent_world_events.append(event_summary)
        if len(state.recent_world_events) > 5:
            state.recent_world_events = state.recent_world_events[-5:]


def evaluate_ending(state: GameState, story_outline: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """依目前 GameState 判斷是否已達成四大結局之一"""
    endings = story_outline.get("endings", {})

    def _intimacy_of(npc_name: str) -> int:
        agent = state.agents.get(npc_name)
        return agent.profile.intimacy if agent else 0

    # 結局 1: 暗黑巨擘
    if state.factions.get("血衣樓", 0) >= 50 and state.world_flags.get("joined_xueyilou"):
        return endings.get("ending_1")

    # 結局 2: 雙宿雙飛
    if (_intimacy_of("合歡宗聖女") >= 70 or _intimacy_of("風騷老闆娘") >= 70) and state.player_state.cultivation_level >= 3:
        return endings.get("ending_2")

    # 結局 3: 金融霸主
    if state.player_state.gold >= 1000 and _intimacy_of("錢莊老王") >= 50:
        return endings.get("ending_3")

    # 結局 4: 回合數達 15 以上觸發龍門傳奇終局
    if state.game_turn >= 15:
        return endings.get("ending_4")

    return None


def get_current_chapter_info(state: GameState, story_outline: Dict[str, Any]) -> Dict[str, Any]:
    """依目前回合數查詢對應的章節資訊"""
    chapters = story_outline.get("chapters", [])
    for ch in chapters:
        t_min, t_max = ch.get("turns_range", [1, 999])
        if t_min <= state.game_turn <= t_max:
            return ch
    return chapters[-1] if chapters else {
        "chapter_id": 5,
        "title": "第五章：江湖大終局與命運審判",
        "goal": "導向四大終局之一並頒發終局稱號。"
    }
