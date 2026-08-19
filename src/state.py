from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from src.models import PlayerState
from src.npc_agent import NPCAgent


@dataclass
class GameState:
    """純資料容器，取代原本散落在 GameEngine 身上的執行期狀態欄位。
    不含任何規則邏輯（規則放在 src/rules.py）、不含靜態設定檔內容
    （world_map/story_outline 等維持是 GameEngine 自己載入持有的唯讀設定）。"""

    player_state: PlayerState
    agents: Dict[str, NPCAgent] = field(default_factory=dict)
    current_agent: Optional[NPCAgent] = None
    current_location: str = "龍門客棧"
    unlocked_locations: Set[str] = field(default_factory=set)
    game_turn: int = 1
    main_quest_summary: str = ""
    story_milestones: List[str] = field(default_factory=list)
    recent_world_events: List[str] = field(default_factory=list)
    world_news: List[str] = field(default_factory=list)
    factions: Dict[str, int] = field(default_factory=dict)
    world_flags: Dict[str, bool] = field(default_factory=dict)
