from typing import Dict, List, Optional, Set, Tuple

from src.content_loader import load_json_or_default
from src.models import GameStateDelta, PlayerState


# 每回合固定顯示 3 個選項，插槽位置用 A/B/C 標示；保底 (fallback) 選項固定用這三個分類
# 對應三個插槽——不是每位角色所有可能的分類 (例如「黑化臨界」「終極臨界」只由
# src/npc_agent.py 依好感度門檻決定性地系統插入，不會出現在保底候選池裡)。
POSITION_LABELS = ["A", "B", "C"]
FALLBACK_TAG_SLOTS = ["真誠切磋", "中性互動", "強攻鋪墊"]


def load_npc_fallbacks(path: str = "config/npc_fallbacks.json") -> Dict[str, Dict]:
    """讀取每個 NPC 的保底劇情/選項內容；查無設定檔時回傳空 dict，交由呼叫端動態生成通用內容"""
    return load_json_or_default(path, {})


def _generic_option_pools(name_for_text: str, location: str) -> Dict[str, List[str]]:
    """查無 npc_fallbacks.json 資料的 NPC (例如玩家自訂/新增角色) 用姓名動態生成通用選項池，
    依分類 (tag) 而非舊版 A~E 位置類別索引。"""
    return {
        "真誠切磋": [
            f"坦然向{name_for_text}展現真本事，不耍花招",
            f"誠心向{name_for_text}請教，展現尊重的姿態",
            f"以真心話回應{name_for_text}，不刻意討好",
        ],
        "中性互動": [
            f"與{name_for_text}並肩談論當前局勢 [{location}]",
            f"陪{name_for_text}處理眼前瑣事，觀察其反應",
            f"與{name_for_text}保持不遠不近的距離閒聊",
        ],
        "強攻鋪墊": [
            f"尋機摸清{name_for_text}的防備，暗中盤算強硬手段",
            f"言語試探{name_for_text}的底線，帶著壓迫感",
            f"逼近{name_for_text}，用氣勢施加壓力",
        ],
    }


def _resolve_option_pools(npc_name: str, location: str, disp_name: Optional[str] = None) -> Dict[str, List[str]]:
    name_for_text = disp_name or npc_name
    entry = load_npc_fallbacks().get(npc_name)
    if entry and entry.get("option_pools"):
        return {
            tag: [tpl.format(disp_name=name_for_text, location=location) for tpl in templates]
            for tag, templates in entry["option_pools"].items()
        }
    return _generic_option_pools(name_for_text, location)


def generate_single_fallback_option(
    idx: int,
    npc_name: str,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
    tag: Optional[str] = None,
) -> Tuple[str, str]:
    """產生單一插槽 (依 idx 對應 A~C) 的保底選項與其分類，優先從選項池挑選未使用過的候選；
    回傳 (選項文字, 分類 tag)。"""
    exclude = exclude_opts or set()
    position_label = POSITION_LABELS[idx % 3]
    content_tag = tag or FALLBACK_TAG_SLOTS[idx % 3]
    candidates = _resolve_option_pools(npc_name, location, disp_name).get(content_tag, [])

    for candidate in candidates:
        option = f"{position_label}) {candidate.strip()}"
        if option not in exclude:
            return option, content_tag

    name_for_text = disp_name or npc_name
    descriptions = {
        "真誠切磋": f"坦然向{name_for_text}展現真本事，不耍花招",
        "中性互動": f"與{name_for_text}保持不遠不近的距離閒聊近況",
        "強攻鋪墊": f"逼近{name_for_text}，用氣勢施加壓力",
    }
    desc = descriptions.get(content_tag, f"與{name_for_text}互動 [{location}]")
    dynamic_option = f"{position_label}) {desc} (第{turn}回合)"
    if dynamic_option in exclude:
        dynamic_option = f"{position_label}) {desc} (第{turn}回合-{len(exclude) + 1})"
    return dynamic_option, content_tag


def generate_fallback_options(
    npc_name: str,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """產生完整 3 個 (A~C) 保底動態選項與其分類，CLI/Web UI/NPCAgent 共用；
    回傳 (選項文字清單, 對應分類清單)，兩者長度皆為 3、依序對應。"""
    exclude = set(exclude_opts) if exclude_opts else set()
    options: List[str] = []
    tags: List[str] = []
    for idx in range(3):
        option, tag = generate_single_fallback_option(idx, npc_name, location, turn, exclude, disp_name)
        options.append(option)
        tags.append(tag)
        exclude.add(option)
    return options, tags


def generate_fallback_narrative(
    npc_name: str,
    player_name: str,
    location: str,
    disp_name: Optional[str] = None,
    identity: Optional[str] = None,
) -> Tuple[str, str]:
    """產生保底劇情段落與 NPC 情緒標籤；查無資料的新 NPC 用其身份動態生成通用劇情。"""
    name_for_text = disp_name or npc_name
    entry = load_npc_fallbacks().get(npc_name)
    if entry and entry.get("narrative"):
        narrative = entry["narrative"].format(disp_name=name_for_text, player_name=player_name, location=location)
        tag = entry.get("tag", "思索")
    else:
        identity_str = f"（{identity}）" if identity else ""
        narrative = (
            f"{player_name}對著{name_for_text}{identity_str}開口表達意圖。{name_for_text}眼神微動，"
            f"轉過身來打量著你，緩緩說道：『這般心思，倒是值得細細思量。』"
        )
        tag = "思索"

    return narrative, tag


def generate_fallback_delta(
    npc_name: str,
    player_state: PlayerState,
    location: str,
    turn: int = 1,
    exclude_opts: Optional[Set[str]] = None,
    disp_name: Optional[str] = None,
    identity: Optional[str] = None,
) -> GameStateDelta:
    """組合保底劇情與保底選項為完整的 GameStateDelta，供 LLM 呼叫失敗時使用。

    intimacy_change 固定為 0：這個 delta 代表的是「LLM 這回合完全連不上」，好感度變化
    應該由呼叫端 (src/npc_agent.py) 依玩家這次選擇的選項分類查表覆寫，不是這個函式的責任。"""
    narrative, tag = generate_fallback_narrative(npc_name, player_state.name, location, disp_name, identity)
    options, option_tags = generate_fallback_options(npc_name, location, turn, exclude_opts, disp_name)
    return GameStateDelta(
        narrative=narrative,
        player_hp_change=0,
        player_stamina_change=0,
        player_gold_change=0,
        intimacy_change=0,
        cultivation_exp_gained=5,
        inventory_added=[],
        inventory_removed=[],
        npc_status_tag=tag,
        world_flag_set={},
        options=options,
        option_tags=option_tags,
    )


def inject_critical_option(
    delta: GameStateDelta,
    predicted_intimacy: int,
    disp_name: str,
    bad_ending_flow: Optional[List[str]] = None,
    good_threshold: int = 70,
    bad_threshold: int = -40,
) -> None:
    """好感度接近門檻時，決定性地把最後一格選項換成關鍵臨界選項，取代 LLM 自由發想——
    確保「終極劇情/黑化結局」這種不可逆分岔是系統控制、玩家清楚知道自己在選什麼，
    不是隨機從候選池撞到的。就地修改 delta.options/delta.option_tags 最後一格 (index 2)。"""
    if len(delta.options) < 3 or len(delta.option_tags) < 3:
        return

    if predicted_intimacy >= good_threshold:
        delta.options[2] = f"C) 向{disp_name}坦露心跡，準備迎向這段關係的終極時刻"
        delta.option_tags[2] = "終極臨界"
    elif predicted_intimacy <= bad_threshold:
        flow_hint = bad_ending_flow[0] if bad_ending_flow else "圖窮匕見，強行壓制"
        delta.options[2] = f"C) {flow_hint}——徹底壓制{disp_name}，不再留任何餘地"
        delta.option_tags[2] = "黑化臨界"
