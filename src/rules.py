import json
import os
from typing import Any, Dict, List, Optional


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_npc_stages(path: str = "config/npc_stages.json") -> Dict[str, List[Dict[str, Any]]]:
    """讀取每個 NPC 的親密度分級設定；查無設定檔或格式壞掉時回傳空 dict，交由呼叫端 fallback"""
    full_path = path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f).get("npc_stages", {})
        except Exception:
            pass
    return {}


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
