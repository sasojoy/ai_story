import json
import os
from typing import Dict, Any, Optional, List, Set
from src.models import GameConfig, NPCProfile, PlayerState, GameStateDelta
from src.ollama_client import OllamaClient
from src.npc_agent import NPCAgent


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class GameEngine:
    def __init__(
        self,
        config_path: str = "config/game_config.json",
        npcs_path: str = "config/npcs.json",
        world_intro_path: str = "config/world_intro.json",
        world_map_path: str = "config/world_map.json"
    ):
        self.config_path = config_path if os.path.isabs(config_path) else os.path.join(BASE_DIR, config_path)
        self.npcs_path = npcs_path if os.path.isabs(npcs_path) else os.path.join(BASE_DIR, npcs_path)
        self.world_intro_path = world_intro_path if os.path.isabs(world_intro_path) else os.path.join(BASE_DIR, world_intro_path)
        self.world_map_path = world_map_path if os.path.isabs(world_map_path) else os.path.join(BASE_DIR, world_map_path)

        self.game_config = self._load_game_config()
        self.client = OllamaClient(
            base_url=self.game_config.ollama_url,
            model=self.game_config.model_name,
            timeout=self.game_config.timeout
        )

        self.player_state = PlayerState()
        self.world_flags: Dict[str, bool] = {}

        self.world_intro = self._load_world_intro()
        self.world_map = self._load_world_map()

        self.current_location: str = "龍門客棧"
        self.unlocked_locations: Set[str] = set()

        for reg_name, reg_info in self.world_map.get("regions", {}).items():
            if reg_info.get("is_unlocked"):
                self.unlocked_locations.add(reg_name)

        self.game_turn: int = 1
        self.main_quest_summary: str = self.world_intro.get(
            "initial_main_quest",
            "重傷逃亡，於龍門客棧尋求療傷與避難，同時查明懷中血秘卷與自身體內毒詛的真相。"
        )
        self.factions: Dict[str, int] = dict(self.world_intro.get(
            "factions",
            {"正派武林盟": -30, "血衣樓": -50, "合歡宗": 0, "朝廷禁衛": -80}
        ))

        self.agents: Dict[str, NPCAgent] = {}
        self._load_npcs()

        self.current_agent: Optional[NPCAgent] = None
        self._update_bound_npc_for_location()

    def _load_game_config(self) -> GameConfig:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return GameConfig.model_validate(data)
            except Exception as e:
                print(f"讀取遊戲設定失敗，使用預設值: {e}")
        return GameConfig()

    def _load_world_intro(self) -> Dict[str, Any]:
        if os.path.exists(self.world_intro_path):
            try:
                with open(self.world_intro_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"讀取世界開場失敗，使用預設值: {e}")
        return {
            "title": "刀鋒 Blade RPG",
            "opening_narrative": "大雨傾盆，你在龍門客棧草堆中甦醒...",
            "background_conflict": "四大勢力盤根錯節，你身處風暴中心。",
            "initial_main_quest": "重傷逃亡，尋求解毒與秘卷真相。",
            "factions": {"正派武林盟": -30, "血衣樓": -50, "合歡宗": 0, "朝廷禁衛": -80}
        }

    def _load_world_map(self) -> Dict[str, Any]:
        if os.path.exists(self.world_map_path):
            try:
                with open(self.world_map_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"讀取世界地圖失敗，使用預設值: {e}")
        return {
            "regions": {
                "龍門客棧": {
                    "name": "龍門客棧",
                    "description": "大漠黃沙中的兩層木造酒樓，酒香與血腥氣交織。",
                    "connections": ["黑風寨山腳", "少林寺下鎮"],
                    "is_unlocked": True,
                    "danger_level": "低",
                    "bound_npc": "風騷老闆娘"
                }
            }
        }

    def _load_npcs(self):
        if os.path.exists(self.npcs_path):
            try:
                with open(self.npcs_path, "r", encoding="utf-8") as f:
                    npcs_data = json.load(f)
                    for key, profile_dict in npcs_data.items():
                        profile = NPCProfile.model_validate(profile_dict)
                        self.agents[profile.name] = NPCAgent(profile)
            except Exception as e:
                print(f"讀取 NPC 載入失敗: {e}")

    def get_current_region(self) -> Dict[str, Any]:
        regions = self.world_map.get("regions", {})
        return regions.get(self.current_location, {
            "name": self.current_location,
            "description": "一片未知的荒野大漠。",
            "connections": [],
            "danger_level": "未知",
            "bound_npc": ""
        })

    def get_available_exits(self) -> List[str]:
        reg = self.get_current_region()
        return reg.get("connections", [])

    def _update_bound_npc_for_location(self):
        reg = self.get_current_region()
        bound_npc_name = reg.get("bound_npc", "")
        if bound_npc_name and bound_npc_name in self.agents:
            self.current_agent = self.agents[bound_npc_name]
        elif self.agents and not self.current_agent:
            self.current_agent = list(self.agents.values())[0]

    def move_to_location(self, location_name: str) -> bool:
        """切換玩家當前所在區域地點"""
        regions = self.world_map.get("regions", {})
        if location_name in regions:
            self.current_location = location_name
            self.unlocked_locations.add(location_name)
            self._update_bound_npc_for_location()
            return True
        return False

    def set_player_name(self, name: str):
        if name and name.strip():
            self.player_state.name = name.strip()

    def switch_npc(self, npc_name: str) -> bool:
        """切換當前互動的 NPC"""
        if npc_name in self.agents:
            self.current_agent = self.agents[npc_name]
            return True
        return False

    def save_slot(self, slot_id: int = 1) -> str:
        """快速存檔指定 Slot (1~5)"""
        from src.save_manager import save_game
        return save_game(slot_id, self)

    def load_slot(self, slot_id: int = 1) -> bool:
        """讀取指定 Slot (1~5) 存檔"""
        from src.save_manager import load_game
        return load_game(slot_id, self)

    def load_latest_slot(self) -> bool:
        """讀取最新一次存檔"""
        from src.save_manager import get_latest_save_slot_id, load_game
        slot_id = get_latest_save_slot_id()
        if slot_id is not None:
            return load_game(slot_id, self)
        return False

    def apply_delta(self, delta: GameStateDelta):
        """套用 GameStateDelta 變更玩家狀態、地點、親密度、雙修修為與世界標記"""
        # 回合數 +1
        self.game_turn += 1

        # 地點變更與解鎖
        if delta.current_location and delta.current_location.strip():
            self.move_to_location(delta.current_location.strip())

        for loc in delta.unlocked_locations:
            if loc and loc.strip():
                self.unlocked_locations.add(loc.strip())

        # 更新 HP 與 體力
        self.player_state.hp = max(
            0, min(self.player_state.max_hp, self.player_state.hp + delta.player_hp_change)
        )
        self.player_state.stamina = max(
            0, min(self.player_state.max_stamina, self.player_state.stamina + delta.player_stamina_change)
        )

        # 更新金幣與魅力
        self.player_state.gold = max(0, self.player_state.gold + delta.player_gold_change)
        self.player_state.charm = max(0, self.player_state.charm + delta.player_charm_change)

        # 更新當前 NPC 親密度/好感度
        if self.current_agent and delta.intimacy_change != 0:
            current_intimacy = self.current_agent.profile.intimacy
            self.current_agent.profile.intimacy = max(0, min(100, current_intimacy + delta.intimacy_change))

        # 解鎖雙修功法/武學
        if delta.cultivation_art_learned and delta.cultivation_art_learned.strip():
            art = delta.cultivation_art_learned.strip()
            if art not in self.player_state.cultivation_arts:
                self.player_state.cultivation_arts.append(art)

        # 修為經驗與等級提升
        if delta.cultivation_exp_gained > 0:
            self.player_state.cultivation_exp += delta.cultivation_exp_gained
            required_exp = self.player_state.cultivation_level * 100
            if self.player_state.cultivation_exp >= required_exp:
                self.player_state.cultivation_level += 1
                self.player_state.charm += 2
                self.player_state.max_stamina += 20
                self.player_state.stamina = self.player_state.max_stamina

        # 新增/移除物品
        for item in delta.inventory_added:
            if item and item not in self.player_state.inventory:
                self.player_state.inventory.append(item)

        for item in delta.inventory_removed:
            if item in self.player_state.inventory:
                self.player_state.inventory.remove(item)

        # 更新世界事件標記
        for flag_key, flag_value in delta.world_flag_set.items():
            self.world_flags[flag_key] = flag_value

        # 動態更新主線故事摘要
        if delta.main_quest_summary_update and delta.main_quest_summary_update.strip():
            self.main_quest_summary = delta.main_quest_summary_update.strip()

        # 動態更新勢力聲望
        for faction_name, reputation_change in delta.faction_reputation_changes.items():
            current_rep = self.factions.get(faction_name, 0)
            self.factions[faction_name] = current_rep + reputation_change

    def interact(self, player_action: str) -> GameStateDelta:
        """與當前 NPC 互動"""
        if not self.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")

        reg_info = self.get_current_region()

        delta = self.current_agent.process_action(
            client=self.client,
            player_action=player_action,
            player_state=self.player_state,
            game_turn=self.game_turn,
            main_quest_summary=self.main_quest_summary,
            factions=self.factions,
            current_location=self.current_location,
            current_region_desc=reg_info.get("description", ""),
            available_exits=self.get_available_exits()
        )

        self.apply_delta(delta)
        return delta
