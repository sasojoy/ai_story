from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional


def is_placeholder_option(text: str) -> bool:
    text_lower = str(text).lower()
    placeholders = ["選項文字", "常規選項", "搞笑選項", "謀略選項", "談判選項", "暗黑選項", "正派選項", "選項a", "選項b", "選項c", "選項d", "選項e"]
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
    intimacy_change: int = Field(default=0, description="當前 NPC 親密度/好感度變更值 (可為正負數, 範圍 -50~80)。實際套用時系統會依玩家選擇的選項分類 (tag) 查表覆寫這個數字，不採用 LLM 自己填的值。")
    cultivation_art_learned: Optional[str] = Field(default=None, description="新解鎖領悟的雙修功法或武學")
    cultivation_exp_gained: int = Field(default=0, description="修為/雙修經驗值增長")
    inventory_added: List[str] = Field(default_factory=list, description="獲得的物品清單")
    inventory_removed: List[str] = Field(default_factory=list, description="失去的物品清單")
    npc_status_tag: str = Field(default="正常", description="NPC 當前情緒或心理狀態標籤,如:震驚、崩潰、動情、配合")
    world_flag_set: Dict[str, bool] = Field(default_factory=dict, description="引發的世界事件標記")
    current_location: Optional[str] = Field(default=None, description="玩家當前所在地點 (如: 龍門客棧, 黑風寨山腳, 亂葬崗)")
    unlocked_locations: List[str] = Field(default_factory=list, description="新解鎖的地點清單 (如: ['亂葬崗', '血衣樓分舵'])")
    main_quest_summary_update: Optional[str] = Field(
        default=None,
        description="根據玩家最新選擇動態改寫的一句話主線故事摘要（只描述整體主線進度，不用列出每位角色）"
    )
    npc_relationship_note_update: Optional[str] = Field(
        default=None,
        description="這回合結束後，跟目前互動角色之間關係現況的一句話更新（只寫這一位角色，不要提其他角色）"
    )
    milestone_unlocked: Optional[str] = Field(
        default=None,
        description="新觸發解鎖的故事里程碑狀態鎖 (例如: '第一層毒詛解開', '獲得龍門密道地圖')"
    )
    faction_reputation_changes: Dict[str, int] = Field(
        default_factory=dict,
        description="各勢力聲望變更值 (例如: {'正派武林盟': -20, '合歡宗': +30})"
    )
    options: List[str] = Field(
        default_factory=lambda: [
            "A) 亮出真本事，堂堂正正試探對方的反應",
            "B) 不遠不近地陪伴與交談，維持中性距離",
            "C) 尋機施展強硬手段，逼對方就範"
        ],
        description="提供給玩家選擇的 3 個動態劇情選項，全部圍繞單一角色的情慾/征服脈絡發想 (A/B/C)"
    )
    option_tags: List[str] = Field(
        default_factory=lambda: ["真誠切磋", "中性互動", "強攻鋪墊"],
        description="對應 options 每個選項的分類標籤，只能從當前 NPC 固定的分類清單中選一個 "
                     "(例如 真誠切磋/中性互動/花言巧語/強攻鋪墊)；系統依這個分類查表決定好感度變化，"
                     "不採用 LLM 自己判斷的數字。長度必須與 options 一致。"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_dict(cls, data: Any) -> Any:
        import re

        if not isinstance(data, dict):
            return data

        # 1. 處理數值欄位為 None 或字串的情況
        for int_field in [
            "player_hp_change", "player_stamina_change", "player_gold_change",
            "player_charm_change", "intimacy_change", "cultivation_exp_gained"
        ]:
            val = data.get(int_field)
            if val is None:
                data[int_field] = 0
            elif isinstance(val, (int, float)):
                data[int_field] = int(val)
            elif isinstance(val, str):
                m = re.search(r'[-+]?\d+', val)
                data[int_field] = int(m.group(0)) if m else 0
            else:
                data[int_field] = 0

        # 2. 處理容器欄位 (List[str])
        for list_field in ["inventory_added", "inventory_removed", "unlocked_locations"]:
            val = data.get(list_field)
            if val is None:
                data[list_field] = []
            elif isinstance(val, str):
                s_val = val.strip()
                data[list_field] = [s_val] if s_val and s_val != "無" else []
            elif isinstance(val, dict):
                data[list_field] = [str(v) for v in val.values() if v]
            elif isinstance(val, list):
                data[list_field] = [str(x) for x in val if x]
            else:
                data[list_field] = []

        # 3. 處理 Dict[str, int] 欄位 (faction_reputation_changes)
        f_rep = data.get("faction_reputation_changes")
        if not isinstance(f_rep, dict):
            data["faction_reputation_changes"] = {}
        else:
            clean_f_rep = {}
            for k, v in f_rep.items():
                if isinstance(v, (int, float)):
                    clean_f_rep[str(k)] = int(v)
                elif isinstance(v, str):
                    m = re.search(r'[-+]?\d+', v)
                    clean_f_rep[str(k)] = int(m.group(0)) if m else 0
            data["faction_reputation_changes"] = clean_f_rep

        # 4. 處理 world_flag_set 欄位型態過濾與相容
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
        else:
            data["world_flag_set"] = {}

        # 5. 處理 current_location (若 LLM 回傳 dict 如 {'name': '龍門客棧'})
        if "current_location" in data and data["current_location"]:
            if isinstance(data["current_location"], dict):
                loc_val = data["current_location"].get("name") or data["current_location"].get("location") or str(data["current_location"])
                data["current_location"] = str(loc_val)
            elif not isinstance(data["current_location"], str):
                data["current_location"] = str(data["current_location"])

        # 6. 處理 narrative 欄位別名
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

        # 6.5 部分小型模型偶爾會把選項清單誤附加在 narrative 段落尾端而非獨立的 options 欄位，
        # 這裡偵測「選項 A)」/「选项A)」這類標記並截斷，避免選項清單重複出現在劇情文字中
        leak_match = re.search(r'(選項|选项)\s*A\s*[)\.、）]', data["narrative"])
        if leak_match and leak_match.start() > 10:
            trimmed = data["narrative"][:leak_match.start()].rstrip("*# \n")
            data["narrative"] = trimmed or data["narrative"]

        # 7. 處理 npc_status_tag 別名與靜默標籤轉置
        if "npc_status_tag" not in data or not data["npc_status_tag"]:
            for alias in ["status", "npc_status", "tag", "emotion"]:
                if alias in data and data[alias]:
                    data["npc_status_tag"] = str(data[alias])
                    break
        if not data.get("npc_status_tag") or data.get("npc_status_tag") in ["靜默", "None", "null", ""]:
            data["npc_status_tag"] = "凝視"

        # 8. 處理 main_quest_summary_update 與 milestone_unlocked 別名
        if not data.get("main_quest_summary_update"):
            for alias in ["main_quest_update", "quest_update", "main_quest", "quest_summary"]:
                if alias in data and data[alias] and isinstance(data[alias], str):
                    data["main_quest_summary_update"] = str(data[alias]).strip()
                    break

        if not data.get("milestone_unlocked"):
            for alias in ["milestone", "milestone_update", "story_milestone", "unlocked_milestone"]:
                if alias in data and data[alias] and isinstance(data[alias], str):
                    data["milestone_unlocked"] = str(data[alias]).strip()
                    break

        # 9. 處理 options 欄位
        raw_options = data.get("options")
        clean_opts = []

        if isinstance(raw_options, dict):
            raw_options = list(raw_options.values())
        elif isinstance(raw_options, str):
            raw_options = [line.strip() for line in raw_options.splitlines() if line.strip()]

        if isinstance(raw_options, list):
            for item in raw_options:
                val = ""
                if isinstance(item, str):
                    val = item
                elif isinstance(item, dict):
                    val = item.get("text") or item.get("option") or item.get("description") or item.get("label")
                    if not val:
                        # 有些模型把完整選項文字放在 "value"、字母代號放在 "key"
                        # （例如 {"key": "C", "value": "C) ..."}），跟預期的
                        # {"value": "A", "text": "..."} 欄位語意剛好相反；用字串長度挑出
                        # dict 裡最長的字串當內容，避免把整個 dict 的 repr 塞進畫面。
                        candidates = [v for v in item.values() if isinstance(v, str) and v.strip()]
                        val = max(candidates, key=len) if candidates else str(item)
                    val = str(val)
                    prefix = item.get("value", "")
                    if prefix and len(str(prefix)) <= 3 and not val.startswith(str(prefix)):
                        val = f"{prefix}) {val}"

                val = sanitize_option_text(val)
                if val and not is_placeholder_option(val):
                    clean_opts.append(str(val))

        if len(clean_opts) >= 3:
            data["options"] = clean_opts[:3]
        else:
            data["options"] = [
                "A) 亮出真本事，堂堂正正試探對方的反應",
                "B) 不遠不近地陪伴與交談，維持中性距離",
                "C) 尋機施展強硬手段，逼對方就範"
            ]

        # 10. 處理 option_tags 欄位：長度需跟 options 一致，不足或非法一律補中性標籤，
        # 實際是否為當前 NPC 合法的分類清單交由呼叫端 (src/npc_agent.py) 再次校驗，
        # 這裡只保證型態正確、長度對齊，不在 pydantic 層做業務規則檢查。
        n_opts = len(data["options"])
        raw_tags = data.get("option_tags")
        if isinstance(raw_tags, dict):
            raw_tags = list(raw_tags.values())
        clean_tags = []
        if isinstance(raw_tags, list):
            clean_tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        while len(clean_tags) < n_opts:
            clean_tags.append("中性互動")
        data["option_tags"] = clean_tags[:n_opts]

        return data


class NPCProfile(BaseModel):
    name: str
    identity: str
    personality: str
    display_name: Optional[str] = None
    faction: Optional[str] = None
    hp: int = 100
    location: str
    intimacy: int = 0
    current_activity: str = "正在靜待時機"
    relationships: Dict[str, int] = Field(default_factory=dict)
    recent_activities: List[str] = Field(default_factory=list)
    body: Dict[str, Any] = Field(
        default_factory=dict,
        description="身材描述資料 (height_cm/build/measurements_cm/sensitivity_note 等，不強制欄位)"
    )
    character_tags: List[str] = Field(
        default_factory=list,
        description="角色屬性標籤（身材/性格傾向/身份關係/癖好取向/行為偏好，例如「巨乳」"
                     "「傲嬌」「人妻」「喜歡口交」），單一扁平清單、不分子類別，純粹用來跟 "
                     "config/scene_templates.json 的 required_tags 比對挑選結局劇情模板。跟 "
                     "body/personality 的自由文字描述是兩回事——那兩個欄位負責提供敘事用的"
                     "細節文字，這個欄位只負責『這個角色適用哪些模板』的比對"
    )
    bad_ending_flow: List[str] = Field(
        default_factory=list,
        description="黑化結局的劇情步驟大綱，僅供之後無審查模型接手寫實際劇情文字時當大綱參考"
    )
    intimacy_tags: Dict[str, int] = Field(
        default_factory=lambda: {
            "真誠切磋": 6,
            "中性互動": 2,
            "花言巧語": -3,
            "強攻鋪墊": -8,
            "黑化臨界": -25,
            "終極臨界": 10,
        },
        description="選項分類 (tag) 對應的固定好感度增減值，見 resolve_intimacy_delta()"
    )
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "realm": "後天境",
            "attack": 50,
            "defense": 40,
            "agility": 50,
            "weapon": "尋常兵刃"
        }
    )
    biography: List[str] = Field(
        default_factory=lambda: [
            "【初見印象】江湖中人，神祕莫測，需透過對話與提升親密度逐步解鎖其生平與不為人知的祕密。"
        ]
    )
    system_prompt_override: Optional[str] = None

    @property
    def narrative_name(self) -> str:
        return self.display_name or self.name

    def resolve_intimacy_delta(self, tag: Optional[str]) -> int:
        """依選項分類 (tag) 查表拿到固定好感度增減值；tag 為 None 或不在清單內時
        一律 fallback 成「中性互動」(查無「中性互動」則視為 0)，不採用 LLM 自報的數字。"""
        if not tag:
            return 0
        return self.intimacy_tags.get(tag, self.intimacy_tags.get("中性互動", 0))

    def get_unlocked_biography(self) -> List[str]:
        """根據親密度解鎖生平故事章節；分級門檻以 config/npc_stages.json 為 SSOT，
        查無該 NPC 資料時 fallback 回舊版寫死的 25/50/75 門檻 (見 src/rules.py)"""
        total = len(self.biography)
        if total == 0:
            return []
        from src.rules import get_intimacy_stage_number
        count = min(get_intimacy_stage_number(self.name, self.intimacy), total)
        return self.biography[:count]

    def get_unlocked_stats(self) -> Dict[str, Any]:
        """根據親密度解鎖數值情報；分級門檻以 config/npc_stages.json 為 SSOT，
        查無該 NPC 資料時 fallback 回舊版寫死的 25/50/75 門檻 (見 src/rules.py)"""
        unlocked = {}
        unlocked["hp"] = self.hp
        unlocked["location"] = self.location

        from src.rules import get_intimacy_stage_number
        stage = get_intimacy_stage_number(self.name, self.intimacy)

        if stage <= 1:
            unlocked["realm"] = "???"
            unlocked["attack"] = "???"
            unlocked["defense"] = "???"
            unlocked["agility"] = "???"
            unlocked["weapon"] = "???"
        elif stage == 2:
            unlocked["realm"] = self.stats.get("realm", "後天境")
            unlocked["attack"] = self.stats.get("attack", 50)
            unlocked["defense"] = "???"
            unlocked["agility"] = "???"
            unlocked["weapon"] = self.stats.get("weapon", "未知")
        else:
            unlocked.update(self.stats)
        return unlocked


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
