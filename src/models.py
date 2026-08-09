from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional


def is_placeholder_option(text: str) -> bool:
    text_lower = str(text).lower()
    placeholders = ["選項文字", "常規選項", "搞笑選項", "暗黑選項", "正派選項", "選項a", "選項b", "選項c"]
    return any(p in text_lower for p in placeholders)


def sanitize_option_text(text: str, default_exit: str = "黑風寨山腳") -> str:
    text = str(text)
    text = text.replace("[地區名]", default_exit).replace("[地點名]", default_exit).replace("[地區]", default_exit)
    return text


class GameStateDelta(BaseModel):
    narrative: str = Field(default="", description="故事劇情發展與 NPC 的反應描述")
    player_hp_change: int = Field(default=0, description="玩家 HP 變更值,可為正負數")
    player_stamina_change: int = Field(default=0, description="玩家體力變更值,可為正負數")
    player_gold_change: int = Field(default=0, description="玩家金幣變更值,可為正負數")
    player_charm_change: int = Field(default=0, description="玩家魅力變更值,可為正負數")
    intimacy_change: int = Field(default=0, description="當前 NPC 親密度/好感度變更值 (可為正負數, 0~100)")
    cultivation_art_learned: Optional[str] = Field(default=None, description="新解鎖領悟的雙修功法或武學")
    cultivation_exp_gained: int = Field(default=0, description="修為/雙修經驗值增長")
    inventory_added: List[str] = Field(default_factory=list, description="獲得的物品清單")
    inventory_removed: List[str] = Field(default_factory=list, description="失去的物品清單")
    npc_status_tag: str = Field(default="正常", description="NPC 當前情緒或心理狀態標籤,如:震驚、崩潰、動情、配合")
    world_flag_set: Dict[str, bool] = Field(default_factory=dict, description="引發的世界事件標記")
    current_location: Optional[str] = Field(default=None, description="玩家當前所在地點 (如: 龍門客棧, 黑風寨山腳, 亂葬崗)")
    unlocked_locations: List[str] = Field(default_factory=list, description="新解鎖的地點清單 (如: ['亂葬崗', '血衣樓分舵'])")
    available_exits: List[str] = Field(default_factory=list, description="當前地點可連通移動的鄰近區域地點清單")
    main_quest_summary_update: Optional[str] = Field(
        default=None,
        description="根據玩家最新選擇動態改寫的主線故事摘要"
    )
    faction_reputation_changes: Dict[str, int] = Field(
        default_factory=dict,
        description="各勢力聲望變更值 (例如: {'正派武林盟': -20, '合歡宗': +30})"
    )
    options: List[str] = Field(
        default_factory=lambda: [
            "A) 亮出兵器靜觀其變，開口詢問對方的意圖",
            "B) 掏出《勞動基準法》與理賠條款進行談判拉扯",
            "C) 上前進行身體接觸與耳邊輕語誘惑條款"
        ],
        description="提供給玩家選擇的 3 個劇情選項"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_dict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. 處理數值欄位為 None 的情況
        for int_field in [
            "player_hp_change", "player_stamina_change", "player_gold_change",
            "player_charm_change", "intimacy_change", "cultivation_exp_gained"
        ]:
            if data.get(int_field) is None:
                data[int_field] = 0

        # 2. 處理容器欄位為 None 或非目標型態的情況
        if data.get("faction_reputation_changes") is None or not isinstance(data.get("faction_reputation_changes"), dict):
            data["faction_reputation_changes"] = {}

        for list_field in ["inventory_added", "inventory_removed", "unlocked_locations", "available_exits"]:
            if data.get(list_field) is None or not isinstance(data.get(list_field), list):
                data[list_field] = []

        # 3. 處理 world_flag_set 欄位型態過濾與相容
        if "world_flag_set" in data and isinstance(data["world_flag_set"], dict):
            clean_flags = {}
            for k, v in data["world_flag_set"].items():
                if k in ["current_location", "location"] and isinstance(v, str):
                    data["current_location"] = str(v)
                else:
                    if isinstance(v, bool):
                        clean_flags[str(k)] = v
                    elif isinstance(v, (int, float)):
                        clean_flags[str(k)] = bool(v != 0)
                    elif isinstance(v, str):
                        v_str = v.lower().strip()
                        if v_str in ["true", "1", "yes"]:
                            clean_flags[str(k)] = True
                        elif v_str in ["false", "0", "no"]:
                            clean_flags[str(k)] = False
                        else:
                            clean_flags[str(k)] = bool(v_str)
            data["world_flag_set"] = clean_flags
        elif data.get("world_flag_set") is None or not isinstance(data.get("world_flag_set"), dict):
            data["world_flag_set"] = {}

        # 4. 處理 current_location (若 LLM 回傳 dict 如 {'name': '龍門客棧'})
        if "current_location" in data and data["current_location"]:
            if isinstance(data["current_location"], dict):
                loc_val = data["current_location"].get("name") or data["current_location"].get("location") or str(data["current_location"])
                data["current_location"] = str(loc_val)
            elif not isinstance(data["current_location"], str):
                data["current_location"] = str(data["current_location"])

        # 5. 處理 narrative 欄位別名
        if not data.get("narrative") or str(data.get("narrative")).strip() in ["...", ""]:
            for alias in [
                "content", "story", "description", "response", "answer",
                "reply", "text", "detail", "output", "message", "narrative_description", "action"
            ]:
                if alias in data and data[alias] and str(data[alias]).strip():
                    data["narrative"] = str(data[alias]).strip()
                    break
        if not data.get("narrative"):
            data["narrative"] = "..."

        # 6. 處理 npc_status_tag 別名
        if "npc_status_tag" not in data or not data["npc_status_tag"]:
            for alias in ["status", "npc_status", "tag", "emotion"]:
                if alias in data and data[alias]:
                    data["npc_status_tag"] = str(data[alias])
                    break
        if "npc_status_tag" not in data or not data["npc_status_tag"]:
            data["npc_status_tag"] = "正常"

        # 7. 處理 main_quest_summary_update 別名
        if not data.get("main_quest_summary_update"):
            for alias in ["main_quest_update", "quest_update", "main_quest", "quest_summary"]:
                if alias in data and data[alias] and isinstance(data[alias], str):
                    data["main_quest_summary_update"] = str(data[alias]).strip()
                    break

        # 8. 處理 options 欄位 (清理並自動替代佔位字詞)
        if "options" in data and isinstance(data["options"], list):
            clean_opts = []
            for item in data["options"]:
                val = ""
                if isinstance(item, str):
                    val = item
                elif isinstance(item, dict):
                    val = item.get("text") or item.get("option") or item.get("description") or item.get("label") or str(item)
                    prefix = item.get("value", "")
                    if prefix and not str(val).startswith(prefix):
                        val = f"{prefix}) {val}"

                val = sanitize_option_text(val)
                if val and not is_placeholder_option(val):
                    clean_opts.append(str(val))

            if len(clean_opts) >= 3:
                data["options"] = clean_opts[:3]
            else:
                data["options"] = [
                    "A) 亮出兵器靜觀其變，開口詢問對方的意圖",
                    "B) 移動前往黑風寨山腳避開風頭",
                    "C) 上前進行身體接觸與耳邊輕語誘惑條款"
                ]

        return data


class NPCProfile(BaseModel):
    name: str
    identity: str
    personality: str
    hp: int = 100
    location: str
    intimacy: int = 0
    system_prompt_override: Optional[str] = None


class PlayerState(BaseModel):
    name: str = "無名俠客"
    hp: int = 100
    max_hp: int = 100
    stamina: int = 100
    max_stamina: int = 100
    charm: int = 15
    gold: int = 50
    cultivation_level: int = 1
    cultivation_exp: int = 0
    cultivation_arts: List[str] = Field(
        default_factory=lambda: ["吐納基礎心法"]
    )
    inventory: List[str] = Field(
        default_factory=lambda: ["鏽蝕鐵劍", "止血草"]
    )


class GameConfig(BaseModel):
    ollama_url: str = "http://localhost:11434"
    model_name: str = "qwen2.5:7b"
    context_length: int = 4096
    timeout: int = 60
