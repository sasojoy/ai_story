import json
import os
from typing import Dict, List, Optional, Set, Tuple

from src.models import GameStateDelta, PlayerState


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CATEGORIES = ["A", "B", "C", "D", "E"]


def load_npc_fallbacks(path: str = "config/npc_fallbacks.json") -> Dict[str, Dict]:
    """讀取每個 NPC 的保底劇情/選項內容；查無設定檔時回傳空 dict，交由呼叫端動態生成通用內容"""
    full_path = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _generic_option_pools(name_for_text: str, location: str) -> Dict[str, List[str]]:
    """查無 npc_fallbacks.json 資料的 NPC (例如玩家自訂/新增角色) 用姓名動態生成通用選項池"""
    return {
        "A": [
            f"抱拳向{name_for_text}詢問當前地區 [{location}] 的傳聞",
            f"探聽關於{name_for_text}的出身來歷與背後勢力",
            f"誠懇向{name_for_text}討教當前局勢與解毒線索",
        ],
        "B": [
            f"冷靜分析四大勢力利害關係與{name_for_text}進行談判",
            f"拿出黑市情報籌碼提議與{name_for_text}利益均沾",
            f"運用江湖談判與利益交換試圖說服{name_for_text}",
        ],
        "C": [
            f"湊近{name_for_text}耳邊輕語並進行身體接觸試探",
            f"牽起{name_for_text}的手指展露魅力拉近情感距離",
            f"上前擁住{name_for_text}運轉靈氣進行雙修親密試探",
        ],
        "D": [
            f"眼神一冷搜刮{name_for_text}隨身帶有的密卷與銀票",
            f"亮出利刃冷聲威脅{name_for_text}透露秘密",
            f"出其不意亮出暗器強襲{name_for_text}索要情報",
        ],
        "E": [
            f"在當前區域 [{location}] 仔細搜尋蛛絲馬跡",
            f"移動前往周邊安全區域避開風頭",
            f"移動前往鄰近地點尋找避難所",
        ],
    }


def _resolve_option_pools(npc_name: str, location: str, disp_name: Optional[str] = None) -> Dict[str, List[str]]:
    name_for_text = disp_name or npc_name
    entry = load_npc_fallbacks().get(npc_name)
    if entry and entry.get("option_pools"):
        return {
            category: [tpl.format(disp_name=name_for_text, location=location) for tpl in templates]
            for category, templates in entry["option_pools"].items()
        }
    return _generic_option_pools(name_for_text, location)


def generate_single_fallback_option(
    idx: int,
    npc_name: str,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
) -> str:
    """產生單一分類 (依 idx 對應 A~E) 的保底選項，優先從選項池挑選未使用過的候選"""
    exclude = exclude_opts or set()
    category = CATEGORIES[idx % 5]
    candidates = _resolve_option_pools(npc_name, location, disp_name).get(category, [])

    for candidate in candidates:
        option = f"{category}) {candidate.strip()}"
        if option not in exclude:
            return option

    name_for_text = disp_name or npc_name
    descriptions = {
        "A": f"向{name_for_text}打聽關於[{location}]的最新情報",
        "B": f"與{name_for_text}進行冷靜利害分析與利益交涉",
        "C": f"上前對{name_for_text}展露魅力進行深層拉扯",
        "D": f"亮出冷刃戒備並強行搜刮{name_for_text}身上的秘卷",
        "E": f"在[{location}]區域搜尋周邊秘密出口",
    }
    dynamic_option = f"{category}) {descriptions[category]} (第{turn}回合)"
    if dynamic_option in exclude:
        dynamic_option = f"{category}) {descriptions[category]} (第{turn}回合-{len(exclude) + 1})"
    return dynamic_option


def generate_fallback_options(
    npc_name: str,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
) -> List[str]:
    """產生完整 5 個 (A~E) 保底動態選項，CLI/Web UI/NPCAgent 共用"""
    exclude = set(exclude_opts) if exclude_opts else set()
    result = []
    for idx in range(5):
        option = generate_single_fallback_option(idx, npc_name, location, turn, exclude, disp_name)
        result.append(option)
        exclude.add(option)
    return result


def generate_fallback_narrative(
    npc_name: str,
    player_name: str,
    location: str,
    disp_name: Optional[str] = None,
    identity: Optional[str] = None,
) -> Tuple[str, str]:
    """產生保底劇情段落與 NPC 情緒標籤；查無資料的新 NPC 用其身份動態生成通用劇情"""
    name_for_text = disp_name or npc_name
    entry = load_npc_fallbacks().get(npc_name)
    if entry and entry.get("narrative"):
        narrative = entry["narrative"].format(disp_name=name_for_text, player_name=player_name, location=location)
        return narrative, entry.get("tag", "思索")

    identity_str = f"（{identity}）" if identity else ""
    narrative = (
        f"{player_name}對著{name_for_text}{identity_str}開口表達意圖。{name_for_text}眼神微動，"
        f"轉過身來打量著你，緩緩說道：『江湖險惡，不知閣下專程前來所為何事？』"
    )
    return narrative, "思索"


def generate_fallback_delta(
    npc_name: str,
    player_state: PlayerState,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
    identity: Optional[str] = None,
) -> GameStateDelta:
    """組合保底劇情與保底選項為完整的 GameStateDelta，供 LLM 呼叫失敗時使用"""
    narrative, tag = generate_fallback_narrative(npc_name, player_state.name, location, disp_name, identity)
    options = generate_fallback_options(npc_name, location, turn, exclude_opts, disp_name)
    return GameStateDelta(
        narrative=narrative,
        player_hp_change=0,
        player_stamina_change=0,
        player_gold_change=0,
        intimacy_change=2,
        cultivation_exp_gained=5,
        inventory_added=[],
        inventory_removed=[],
        npc_status_tag=tag,
        world_flag_set={},
        options=options,
    )
