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
        world_map_path: str = "config/world_map.json",
        story_outline_path: str = "config/story_outline.json"
    ):
        self.config_path = config_path if os.path.isabs(config_path) else os.path.join(BASE_DIR, config_path)
        self.npcs_path = npcs_path if os.path.isabs(npcs_path) else os.path.join(BASE_DIR, npcs_path)
        self.world_intro_path = world_intro_path if os.path.isabs(world_intro_path) else os.path.join(BASE_DIR, world_intro_path)
        self.world_map_path = world_map_path if os.path.isabs(world_map_path) else os.path.join(BASE_DIR, world_map_path)
        self.story_outline_path = story_outline_path if os.path.isabs(story_outline_path) else os.path.join(BASE_DIR, story_outline_path)

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
        self.story_outline = self._load_story_outline()

        self.current_location: str = "龍門客棧"
        self.unlocked_locations: Set[str] = set()
        self.story_milestones: List[str] = ["客棧甦醒與初入龍門"]
        self.recent_world_events: List[str] = []
        self.world_news: List[str] = [
            "【江湖動態】[阿福] 正在暗巷擦拭漆黑古鐵劍，拒絕了血衣樓無預付訂金的刺殺指令。",
            "【江湖動態】[老王] 正在龍門錢莊清點黑市黃金，盤算各大門派的地下債務。",
            "【江湖動態】[柳如煙] 於天字房微醺品酒，暗中打量著闖入龍門客棧的各路強者。",
            "【江湖動態】[賽金花] 在客棧酒櫃前斟酒招攬豪客，打探著血秘卷的傳聞。"
        ]

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

    def _load_story_outline(self) -> Dict[str, Any]:
        if os.path.exists(self.story_outline_path):
            try:
                with open(self.story_outline_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"讀取故事大綱失敗，使用預設值: {e}")
        return {
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

    def get_current_chapter_info(self) -> Dict[str, Any]:
        chapters = self.story_outline.get("chapters", [])
        for ch in chapters:
            t_min, t_max = ch.get("turns_range", [1, 999])
            if t_min <= self.game_turn <= t_max:
                return ch
        return chapters[-1] if chapters else {
            "chapter_id": 5,
            "title": "第五章：江湖大終局與命運審判",
            "goal": "導向四大終局之一並頒發終局稱號。"
        }

    def evaluate_ending(self) -> Optional[Dict[str, Any]]:
        endings = self.story_outline.get("endings", {})
        
        # 結局 1: 暗黑巨擘
        if self.factions.get("血衣樓", 0) >= 50 and self.world_flags.get("joined_xueyilou"):
            return endings.get("ending_1")

        # 結局 2: 雙宿雙飛
        sh_intimacy = self.agents.get("合歡宗聖女", NPCAgent(NPCProfile(name="", identity="", personality="", location=""))).profile.intimacy
        boss_intimacy = self.agents.get("風騷老闆娘", NPCAgent(NPCProfile(name="", identity="", personality="", location=""))).profile.intimacy
        if (sh_intimacy >= 70 or boss_intimacy >= 70) and self.player_state.cultivation_level >= 3:
            return endings.get("ending_2")

        # 結局 3: 金融霸主
        wang_intimacy = self.agents.get("錢莊老王", NPCAgent(NPCProfile(name="", identity="", personality="", location=""))).profile.intimacy
        if self.player_state.gold >= 1000 and wang_intimacy >= 50:
            return endings.get("ending_3")

        # 結局 4: 回合數達 15 以上觸發龍門傳奇終局
        if self.game_turn >= 15:
            return endings.get("ending_4")

        return None

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
            self.simulate_npc_autonomous_actions()
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

    def auto_save(self, account_name: str = None) -> str:
        """帳號即時自動存檔"""
        from src.save_manager import save_account_game
        target_account = account_name or self.player_state.name
        return save_account_game(target_account, self)

    def load_slot(self, slot_id: int = 1) -> bool:
        """讀取指定 Slot (1~5) 存檔"""
        from src.save_manager import load_game
        return load_game(slot_id, self)

    def load_account(self, account_name: str) -> bool:
        """讀取指定帳號即時存檔"""
        from src.save_manager import load_account_game
        return load_account_game(account_name, self)

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

        # 動態更新主線故事摘要與里程碑
        if delta.main_quest_summary_update and delta.main_quest_summary_update.strip():
            self.main_quest_summary = delta.main_quest_summary_update.strip()

        if delta.milestone_unlocked and delta.milestone_unlocked.strip():
            ms = delta.milestone_unlocked.strip()
            if ms not in self.story_milestones:
                self.story_milestones.append(ms)

        # 動態更新勢力聲望
        for faction_name, reputation_change in delta.faction_reputation_changes.items():
            current_rep = self.factions.get(faction_name, 0)
            self.factions[faction_name] = current_rep + reputation_change

        # 記錄近期江湖動態 (故事動態鏈)
        if delta.narrative and delta.narrative.strip() and delta.narrative.strip() != "...":
            npc_n = self.current_agent.profile.name if self.current_agent else "NPC"
            event_summary = f"[{npc_n} - {self.current_location}] {delta.narrative[:40]}..."
            self.recent_world_events.append(event_summary)
            if len(self.recent_world_events) > 5:
                self.recent_world_events = self.recent_world_events[-5:]

    def simulate_npc_autonomous_actions(self):
        """每回合進行非當前 NPC 的自主行為推演與社交關聯演變"""
        import random

        activities_pool = {
            "殺手阿福": [
                ("正在暗巷擦拭漆黑古鐵劍，冷眼觀察周邊埋伏的血衣樓刺客", {"錢莊老王": -5}),
                ("收劍歸鞘，嚴正拒絕任何未支付預付金的刺殺委託", {"風騷老闆娘": +5}),
                ("在暗巷一招震退兩名前來試探的血衣樓小卒", {"風騷老闆娘": +5, "錢莊老王": -5}),
                ("坐在客棧外石凳上閉目養神，擦拭手背上的陳年劍傷", {})
            ],
            "錢莊老王": [
                ("正在錢莊撥打金算盤，精算四大勢力的地下借貸與武器抵押", {"合歡宗聖女": -5}),
                ("親自跑去龍門客棧推銷黑市黃金借貸，被賽金花打發了一壺烈酒", {"風騷老闆娘": +5}),
                ("在櫃檯前查驗剛收到的黃金熔錠，暗中計算如何向阿福追討黑市貸款", {"殺手阿福": -5}),
                ("籌劃龍門錢莊地下資金鏈，嘗試拉攏各大武林勢力入股", {"風騷老闆娘": +5})
            ],
            "合歡宗聖女": [
                ("正在天字房紅燭下品嚐西域葡萄酒，搖曳七情魔音鈴修煉太上陰陽心法", {"風騷老闆娘": +5}),
                ("暗中派香婢向下樓與賽金花對接，交換朝廷錦衣衛與血衣樓的最新情報", {"風騷老闆娘": +10}),
                ("站在天字房窗前俯瞰龍門客棧暗巷，暗中觀察阿福的拔劍出招速度", {"殺手阿福": +5}),
                ("在紅燭微光下研讀上古雙修祕籍殘頁，尋解開師門詛咒的雄性強者", {})
            ],
            "風騷老闆娘": [
                ("正在酒櫃前與過往客商調情斟酒，用柔情與酒香換取黑市秘寶資訊", {"合歡宗聖女": +5}),
                ("親自前往龍門客棧地下暗道清點密藏，暗中資助義軍物資糧草", {"殺手阿福": +5}),
                ("微笑着指點老王關於龍門客棧的租憑契約條款，小賺了一筆利息", {"錢莊老王": -5}),
                ("倚靠在客棧二樓欄杆邊抿酒，眼神掃過堂內每位江湖豪客的腰間佩兵", {})
            ]
        }

        current_npc_name = self.current_agent.profile.name if self.current_agent else ""

        for name, agent in self.agents.items():
            if name == current_npc_name:
                continue

            p = agent.profile
            pool = activities_pool.get(name, [])
            if pool:
                act_text, rel_changes = random.choice(pool)
                p.current_activity = act_text
                p.recent_activities.append(f"[第{self.game_turn}回合] {act_text}")
                if len(p.recent_activities) > 5:
                    p.recent_activities = p.recent_activities[-5:]

                for target_npc, change in rel_changes.items():
                    curr_rel = p.relationships.get(target_npc, 0)
                    p.relationships[target_npc] = max(-100, min(100, curr_rel + change))

                disp_name = p.display_name or p.name
                news_item = f"【江湖動態 · 回合{self.game_turn}】[{disp_name}] {act_text}"
                self.world_news.insert(0, news_item)

        if len(self.world_news) > 10:
            self.world_news = self.world_news[:10]

    def interact(self, player_action: str) -> GameStateDelta:
        """與當前 NPC 互動"""
        if not self.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")

        reg_info = self.get_current_region()
        ch_info = self.get_current_chapter_info()

        delta = self.current_agent.process_action(
            client=self.client,
            player_action=player_action,
            player_state=self.player_state,
            game_turn=self.game_turn,
            main_quest_summary=self.main_quest_summary,
            factions=self.factions,
            current_location=self.current_location,
            current_region_desc=reg_info.get("description", ""),
            available_exits=self.get_available_exits(),
            recent_world_events=self.recent_world_events,
            story_chapter_title=ch_info.get("title", "第一章：血夜甦醒與龍門破局"),
            story_chapter_goal=ch_info.get("goal", "尋求療傷與避難，查明懷中血秘卷真相。")
        )

        self.apply_delta(delta)
        self.simulate_npc_autonomous_actions()
        return delta

    def interact_stream(self, player_action: str):
        """與當前 NPC 串流互動"""
        if not self.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")

        reg_info = self.get_current_region()
        ch_info = self.get_current_chapter_info()

        for partial_narrative, delta in self.current_agent.process_action_stream(
            client=self.client,
            player_action=player_action,
            player_state=self.player_state,
            game_turn=self.game_turn,
            main_quest_summary=self.main_quest_summary,
            factions=self.factions,
            current_location=self.current_location,
            current_region_desc=reg_info.get("description", ""),
            available_exits=self.get_available_exits(),
            recent_world_events=self.recent_world_events,
            story_chapter_title=ch_info.get("title", "第一章：血夜甦醒與龍門破局"),
            story_chapter_goal=ch_info.get("goal", "尋求療傷與避難，查明懷中血秘卷真相。")
        ):
            if delta is not None:
                self.apply_delta(delta)
                self.simulate_npc_autonomous_actions()
            yield partial_narrative, delta
