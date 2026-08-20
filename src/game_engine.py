import os
from typing import Dict, Any, Optional, List
from src.models import GameConfig, NPCProfile, PlayerState, GameStateDelta
from src.ollama_client import OllamaClient
from src.npc_agent import NPCAgent
from src.content_loader import load_json_or_default
from src.state import GameState
from src import rules
from src import npc_autonomy


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_DEFAULT_WORLD_INTRO: Dict[str, Any] = {
    "title": "刀鋒 Blade RPG",
    "opening_narrative": "大雨傾盆，你在龍門客棧草堆中甦醒...",
    "background_conflict": "四大勢力盤根錯節，你身處風暴中心。",
    "initial_main_quest": "重傷逃亡，尋求解毒與秘卷真相。",
    "factions": {"正派武林盟": -30, "血衣樓": -50, "合歡宗": 0, "朝廷禁衛": -80}
}

_DEFAULT_WORLD_MAP: Dict[str, Any] = {
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

_DEFAULT_STORY_OUTLINE: Dict[str, Any] = {
    "chapters": [
        {
            "chapter_id": 1,
            "title": "第一章：血夜甦醒與龍門破局",
            "turns_range": [1, 3],
            "goal": "尋求療傷與避難，查明血秘卷第一層真相。"
        },
        {
            "chapter_id": 2,
            "title": "第二章：地圖拓展與勢力抉擇",
            "turns_range": [4, 7],
            "goal": "探索周邊區域，決定勢力靠攏。"
        },
        {
            "chapter_id": 3,
            "title": "第三章：雙修解毒與陰謀真相",
            "turns_range": [8, 11],
            "goal": "進行深層雙修合練驅毒，揭發武林盟陰謀。"
        },
        {
            "chapter_id": 4,
            "title": "第四章：四方決裂與龍門之巔",
            "turns_range": [12, 14],
            "goal": "四大勢力決戰於龍門關。"
        },
        {
            "chapter_id": 5,
            "title": "第五章：江湖大終局與命運審判",
            "turns_range": [15, 999],
            "goal": "導向四大終局之一並頒發終局稱號。"
        }
    ]
}

_DEFAULT_WORLD_NEWS: List[str] = [
    "【江湖動態】[阿福] 正在暗巷擦拭漆黑古鐵劍，拒絕了血衣樓無預付訂金的刺殺指令。",
    "【江湖動態】[老王] 正在龍門錢莊清點黑市黃金，盤算各大門派的地下債務。",
    "【江湖動態】[柳如煙] 於天字房微醺品酒，暗中打量著闖入龍門客棧的各路強者。",
    "【江湖動態】[賽金花] 在客棧酒櫃前斟酒招攬豪客，打探著血秘卷的傳聞。"
]


class GameEngine:
    """`main.py`/`web_ui.py` 唯一的對外入口 (facade)：組合 content_loader/state/rules/npc_autonomy 等模組，
    對外方法簽章維持不變。實際的執行期狀態存放在 self.state (GameState)，資料型欄位透過底下的
    property 轉發，讓既有呼叫端 (尤其是直接做屬性存取的 save_manager.py) 完全不用修改。"""

    def __init__(
        self,
        config_path: str = "config/game_config.json",
        npcs_path: str = "config/npcs.json",
        world_intro_path: str = "config/world_intro.json",
        world_map_path: str = "config/world_map.json",
        story_outline_path: str = "config/story_outline.json"
    ):
        self.config_path = config_path if os.path.isabs(config_path) else os.path.join(BASE_DIR, config_path)
        self.npcs_path = npcs_path if os.path.isabs(npcs_path) else os.path.join(BASE_DIR, npcs_path)
        self.world_intro_path = world_intro_path if os.path.isabs(world_intro_path) else os.path.join(BASE_DIR, world_intro_path)
        self.world_map_path = world_map_path if os.path.isabs(world_map_path) else os.path.join(BASE_DIR, world_map_path)
        self.story_outline_path = story_outline_path if os.path.isabs(story_outline_path) else os.path.join(BASE_DIR, story_outline_path)

        game_config_dict = load_json_or_default(self.config_path, {})
        try:
            self.game_config = GameConfig.model_validate(game_config_dict)
        except Exception as e:
            print(f"讀取遊戲設定失敗，使用預設值: {e}")
            self.game_config = GameConfig()

        self.client = OllamaClient(
            base_url=self.game_config.ollama_url,
            model=self.game_config.model_name,
            timeout=self.game_config.timeout,
            context_length=self.game_config.context_length
        )

        # 靜態設定檔內容：載入一次後只讀，不屬於 GameState 管的執行期狀態
        self.world_intro = load_json_or_default(self.world_intro_path, _DEFAULT_WORLD_INTRO)
        self.world_map = load_json_or_default(self.world_map_path, _DEFAULT_WORLD_MAP)
        self.story_outline = load_json_or_default(self.story_outline_path, _DEFAULT_STORY_OUTLINE)

        agents = self._load_npcs()

        unlocked_locations = set()
        for reg_name, reg_info in self.world_map.get("regions", {}).items():
            if reg_info.get("is_unlocked"):
                unlocked_locations.add(reg_name)

        self.state = GameState(
            player_state=PlayerState(),
            agents=agents,
            current_agent=None,
            current_location="龍門客棧",
            unlocked_locations=unlocked_locations,
            game_turn=1,
            main_quest_summary=self.world_intro.get(
                "initial_main_quest",
                "重傷逃亡，於龍門客棧尋求療傷與避難，同時查明懷中血秘卷與自身體內毒詛的真相。"
            ),
            story_milestones=["客棧甦醒與初入龍門"],
            recent_world_events=[],
            world_news=list(_DEFAULT_WORLD_NEWS),
            factions=dict(self.world_intro.get(
                "factions",
                {"正派武林盟": -30, "血衣樓": -50, "合歡宗": 0, "朝廷禁衛": -80}
            )),
            world_flags={},
        )

        self._update_bound_npc_for_location()

    def _load_npcs(self) -> Dict[str, NPCAgent]:
        agents: Dict[str, NPCAgent] = {}
        npcs_data = load_json_or_default(self.npcs_path, {})
        for key, profile_dict in npcs_data.items():
            try:
                profile = NPCProfile.model_validate(profile_dict)
                agents[profile.name] = NPCAgent(profile)
            except Exception as e:
                print(f"讀取 NPC [{key}] 載入失敗: {e}")
        return agents

    # ---- 執行期狀態欄位轉發 (GameState 為唯一真實來源) ----

    @property
    def player_state(self) -> PlayerState:
        return self.state.player_state

    @player_state.setter
    def player_state(self, value: PlayerState) -> None:
        self.state.player_state = value

    @property
    def agents(self) -> Dict[str, NPCAgent]:
        return self.state.agents

    @agents.setter
    def agents(self, value: Dict[str, NPCAgent]) -> None:
        self.state.agents = value

    @property
    def current_agent(self) -> Optional[NPCAgent]:
        return self.state.current_agent

    @current_agent.setter
    def current_agent(self, value: Optional[NPCAgent]) -> None:
        self.state.current_agent = value

    @property
    def current_location(self) -> str:
        return self.state.current_location

    @current_location.setter
    def current_location(self, value: str) -> None:
        self.state.current_location = value

    @property
    def unlocked_locations(self):
        return self.state.unlocked_locations

    @unlocked_locations.setter
    def unlocked_locations(self, value) -> None:
        self.state.unlocked_locations = value

    @property
    def game_turn(self) -> int:
        return self.state.game_turn

    @game_turn.setter
    def game_turn(self, value: int) -> None:
        self.state.game_turn = value

    @property
    def main_quest_summary(self) -> str:
        return self.state.main_quest_summary

    @main_quest_summary.setter
    def main_quest_summary(self, value: str) -> None:
        self.state.main_quest_summary = value

    @property
    def story_milestones(self):
        return self.state.story_milestones

    @story_milestones.setter
    def story_milestones(self, value) -> None:
        self.state.story_milestones = value

    @property
    def recent_world_events(self):
        return self.state.recent_world_events

    @recent_world_events.setter
    def recent_world_events(self, value) -> None:
        self.state.recent_world_events = value

    @property
    def world_news(self):
        return self.state.world_news

    @world_news.setter
    def world_news(self, value) -> None:
        self.state.world_news = value

    @property
    def factions(self) -> Dict[str, int]:
        return self.state.factions

    @factions.setter
    def factions(self, value: Dict[str, int]) -> None:
        self.state.factions = value

    @property
    def world_flags(self) -> Dict[str, bool]:
        return self.state.world_flags

    @world_flags.setter
    def world_flags(self, value: Dict[str, bool]) -> None:
        self.state.world_flags = value

    # ---- 規則查詢：委派給 src/rules.py ----

    def get_current_chapter_info(self) -> Dict[str, Any]:
        return rules.get_current_chapter_info(self.state, self.story_outline)

    def evaluate_ending(self) -> Optional[Dict[str, Any]]:
        return rules.evaluate_ending(self.state, self.story_outline)

    def get_current_region(self) -> Dict[str, Any]:
        regions = self.world_map.get("regions", {})
        return regions.get(self.state.current_location, {
            "name": self.state.current_location,
            "description": "一片未知的荒野大漠。",
            "connections": [],
            "danger_level": "未知",
            "bound_npc": ""
        })

    def get_available_exits(self) -> List[str]:
        reg = self.get_current_region()
        return reg.get("connections", [])

    def _update_bound_npc_for_location(self):
        rules.update_bound_npc_for_location(self.state, self.world_map)

    def move_to_location(self, location_name: str) -> bool:
        """切換玩家當前所在區域地點；不在此觸發 NPC 自主行動模擬，
        呼叫端負責在整個回合結束時觸發恰好一次 (見 src/rules.py::move_to_location 說明)"""
        return rules.move_to_location(self.state, self.world_map, location_name)

    def set_player_name(self, name: str):
        if name and name.strip():
            self.state.player_state.name = name.strip()

    def switch_npc(self, npc_name: str) -> bool:
        """切換當前互動的 NPC"""
        if npc_name in self.state.agents:
            self.state.current_agent = self.state.agents[npc_name]
            return True
        return False

    def auto_save(self, account_name: str = None) -> str:
        """帳號即時自動存檔（目前唯一支援的存檔機制，見 ARCHITECTURE.md 存檔系統整併）"""
        from src.save_manager import save_account_game
        target_account = account_name or self.state.player_state.name
        return save_account_game(target_account, self)

    def load_account(self, account_name: str) -> bool:
        """讀取指定帳號即時存檔"""
        from src.save_manager import load_account_game
        return load_account_game(account_name, self)

    def apply_delta(self, delta: GameStateDelta):
        """套用 GameStateDelta 變更玩家狀態、地點、親密度、雙修修為與世界標記"""
        rules.apply_delta(self.state, delta, self.world_map)

    def simulate_npc_autonomous_actions(self):
        """每回合進行非當前互動 NPC 的自主行為推演與社交關聯演變"""
        npc_autonomy.simulate_npc_autonomous_actions(self.state)

    def interact(self, player_action: str, chosen_category: Optional[str] = None) -> GameStateDelta:
        """與當前 NPC 互動；chosen_category 是玩家選的選項所屬類別 (A~E)，用於主題線鎖定
        （見 src/rules.py::update_thread_state），CLI 沒有固定按鈕對應類別，預設 None 即可"""
        if not self.state.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")

        reg_info = self.get_current_region()
        ch_info = self.get_current_chapter_info()

        delta = self.state.current_agent.process_action(
            client=self.client,
            player_action=player_action,
            player_state=self.state.player_state,
            game_turn=self.state.game_turn,
            main_quest_summary=self.state.main_quest_summary,
            factions=self.state.factions,
            current_location=self.state.current_location,
            current_region_desc=reg_info.get("description", ""),
            available_exits=self.get_available_exits(),
            recent_world_events=self.state.recent_world_events,
            story_chapter_title=ch_info.get("title", "第一章：血夜甦醒與龍門破局"),
            story_chapter_goal=ch_info.get("goal", "尋求療傷與避難，查明懷中血秘卷真相。"),
            chosen_category=chosen_category
        )

        self.apply_delta(delta)
        self.simulate_npc_autonomous_actions()
        return delta

    def interact_stream(self, player_action: str, chosen_category: Optional[str] = None):
        """與當前 NPC 串流互動；chosen_category 見 interact() 的說明"""
        if not self.state.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")

        reg_info = self.get_current_region()
        ch_info = self.get_current_chapter_info()

        for partial_narrative, delta in self.state.current_agent.process_action_stream(
            client=self.client,
            player_action=player_action,
            player_state=self.state.player_state,
            game_turn=self.state.game_turn,
            main_quest_summary=self.state.main_quest_summary,
            factions=self.state.factions,
            current_location=self.state.current_location,
            current_region_desc=reg_info.get("description", ""),
            available_exits=self.get_available_exits(),
            recent_world_events=self.state.recent_world_events,
            story_chapter_title=ch_info.get("title", "第一章：血夜甦醒與龍門破局"),
            story_chapter_goal=ch_info.get("goal", "尋求療傷與避難，查明懷中血秘卷真相。"),
            chosen_category=chosen_category
        ):
            if delta is not None:
                self.apply_delta(delta)
                self.simulate_npc_autonomous_actions()
            yield partial_narrative, delta
