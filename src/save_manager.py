import os
import json
import datetime
import re
from typing import Dict, Any, List, Optional
from src.models import PlayerState


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAVES_DIR = os.path.join(BASE_DIR, "saves")


def ensure_saves_dir():
    if not os.path.exists(SAVES_DIR):
        os.makedirs(SAVES_DIR, exist_ok=True)


def sanitize_account_name(name: str) -> str:
    cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '_', name.strip())
    return cleaned if cleaned else "guest_user"


def get_save_path(slot_id: int) -> str:
    ensure_saves_dir()
    return os.path.join(SAVES_DIR, f"save_slot_{slot_id}.json")


def get_account_save_path(account_name: str) -> str:
    ensure_saves_dir()
    safe_name = sanitize_account_name(account_name)
    return os.path.join(SAVES_DIR, f"account_{safe_name}.json")


def save_game(slot_id: int, engine: Any) -> str:
    ensure_saves_dir()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    npcs_data = {}
    for name, agent in engine.agents.items():
        npcs_data[name] = {
            "intimacy": agent.profile.intimacy,
            "current_activity": agent.profile.current_activity,
            "relationships": agent.profile.relationships,
            "recent_activities": agent.profile.recent_activities,
            "current_status_tag": agent.current_status_tag,
            "history": agent.history
        }

    quest_short = engine.main_quest_summary[:18] + "..." if len(engine.main_quest_summary) > 18 else engine.main_quest_summary
    summary = f"[{engine.player_state.name}] {engine.current_location} (第 {engine.game_turn} 回合) - {quest_short}"

    save_data = {
        "slot_id": slot_id,
        "timestamp": now_str,
        "summary": summary,
        "player_state": engine.player_state.model_dump(),
        "current_location": engine.current_location,
        "unlocked_locations": list(engine.unlocked_locations),
        "main_quest_summary": engine.main_quest_summary,
        "game_turn": engine.game_turn,
        "factions": engine.factions,
        "world_flags": engine.world_flags,
        "world_news": getattr(engine, "world_news", []),
        "current_npc_name": engine.current_agent.profile.name if engine.current_agent else "",
        "npcs_data": npcs_data
    }

    save_path = get_save_path(slot_id)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    return f"存檔成功！(Slot {slot_id} - {now_str})"


def save_account_game(account_name: str, engine: Any) -> str:
    ensure_saves_dir()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    npcs_data = {}
    for name, agent in engine.agents.items():
        npcs_data[name] = {
            "intimacy": agent.profile.intimacy,
            "current_activity": agent.profile.current_activity,
            "relationships": agent.profile.relationships,
            "recent_activities": agent.profile.recent_activities,
            "current_status_tag": agent.current_status_tag,
            "history": agent.history
        }

    quest_short = engine.main_quest_summary[:18] + "..." if len(engine.main_quest_summary) > 18 else engine.main_quest_summary
    summary = f"[{engine.player_state.name}] {engine.current_location} (第 {engine.game_turn} 回合) - {quest_short}"

    save_data = {
        "account_name": account_name,
        "timestamp": now_str,
        "summary": summary,
        "player_state": engine.player_state.model_dump(),
        "current_location": engine.current_location,
        "unlocked_locations": list(engine.unlocked_locations),
        "main_quest_summary": engine.main_quest_summary,
        "game_turn": engine.game_turn,
        "factions": engine.factions,
        "world_flags": engine.world_flags,
        "world_news": getattr(engine, "world_news", []),
        "current_npc_name": engine.current_agent.profile.name if engine.current_agent else "",
        "npcs_data": npcs_data
    }

    save_path = get_account_save_path(account_name)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    return f"帳號 [{account_name}] 即時自動存檔成功！({now_str})"


def load_game(slot_id: int, engine: Any) -> bool:
    save_path = get_save_path(slot_id)
    return load_game_from_file(save_path, engine)


def load_account_game(account_name: str, engine: Any) -> bool:
    save_path = get_account_save_path(account_name)
    return load_game_from_file(save_path, engine)


def has_account_save(account_name: str) -> bool:
    save_path = get_account_save_path(account_name)
    return os.path.exists(save_path)


def load_game_from_file(save_path: str, engine: Any) -> bool:
    if not os.path.exists(save_path):
        return False

    try:
        with open(save_path, "r", encoding="utf-8") as f:
            save_data = json.load(f)

        # 還原 PlayerState
        engine.player_state = PlayerState.model_validate(save_data["player_state"])

        # 還原基本環境與主線
        engine.current_location = save_data.get("current_location", "龍門客棧")
        engine.unlocked_locations = set(save_data.get("unlocked_locations", ["龍門客棧"]))
        engine.main_quest_summary = save_data.get("main_quest_summary", "")
        engine.game_turn = save_data.get("game_turn", 1)
        engine.factions = dict(save_data.get("factions", {}))
        engine.world_flags = dict(save_data.get("world_flags", {}))
        if "world_news" in save_data:
            engine.world_news = list(save_data["world_news"])

        # 還原 NPC 狀態與對話歷史
        npcs_data = save_data.get("npcs_data", {})
        for name, npc_info in npcs_data.items():
            if name in engine.agents:
                agent = engine.agents[name]
                agent.profile.intimacy = npc_info.get("intimacy", 0)
                if "current_activity" in npc_info:
                    agent.profile.current_activity = npc_info["current_activity"]
                if "relationships" in npc_info:
                    agent.profile.relationships = dict(npc_info["relationships"])
                if "recent_activities" in npc_info:
                    agent.profile.recent_activities = list(npc_info["recent_activities"])
                agent.current_status_tag = npc_info.get("current_status_tag", "正常")
                agent.history = list(npc_info.get("history", []))

        # 切換至存檔時的當前 NPC 或地點預設 NPC
        target_npc = save_data.get("current_npc_name", "")
        if target_npc and target_npc in engine.agents:
            engine.current_agent = engine.agents[target_npc]
        else:
            engine._update_bound_npc_for_location()

        return True
    except Exception as e:
        print(f"載入存檔檔 {save_path} 失敗: {e}")
        return False


def list_saves() -> List[Dict[str, Any]]:
    ensure_saves_dir()
    saves_list = []
    for slot_id in range(1, 6):
        save_path = get_save_path(slot_id)
        if os.path.exists(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saves_list.append({
                        "slot_id": slot_id,
                        "timestamp": data.get("timestamp", "未知時間"),
                        "summary": data.get("summary", "無摘要"),
                        "player_name": data.get("player_state", {}).get("name", "無名俠客"),
                        "location": data.get("current_location", "未知地點"),
                        "game_turn": data.get("game_turn", 1),
                        "exists": True
                    })
            except Exception:
                saves_list.append({
                    "slot_id": slot_id,
                    "timestamp": "損壞的存檔",
                    "summary": "無法讀取",
                    "exists": True
                })
        else:
            saves_list.append({
                "slot_id": slot_id,
                "timestamp": "空存檔槽位",
                "summary": "尚未存檔",
                "exists": False
            })
    return saves_list


def get_latest_save_slot_id() -> Optional[int]:
    saves = list_saves()
    existing_saves = [s for s in saves if s["exists"] and s["summary"] != "無法讀取"]
    if not existing_saves:
        return None
    existing_saves.sort(key=lambda s: s["timestamp"], reverse=True)
    return existing_saves[0]["slot_id"]
