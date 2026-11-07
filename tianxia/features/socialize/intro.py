"""點大勢人物那一層的人物簡介（原本寫在 server.py，第二輪第 83 批搬進交友包）：/api/main 的 figures_here 那一格（包的 status_slots）叫 figure_intro。
開新檔、不放 view.py：view.py 引擎與假人都載，放那裡假人行程也要在 import 時讀檔；這個檔只有殼與 status_slots 那一下才 import。
FIGURE_INTROS 殼留一行別名（server.FIGURE_INTROS 是同一個物件，測試與 same_behavior 在讀）。"""
import json
from pathlib import Path

from tianxia import persona_rules  # 人物性子：簡介的如今與變化紀錄（共用規則層）


def _figure_intros() -> dict:
    """點大勢人物那一層的人物簡介（content/figure_intros.json；給不熟三國的玩家看，Joy 11/6）：沒有這個檔就是空的，畫面不畫簡介。"""
    try:
        data = json.loads((Path(__file__).parents[3] / "content" / "figure_intros.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


FIGURE_INTROS = _figure_intros()


def figure_intro(cid: str, game=None) -> dict | None:
    """{who 是誰, role 身分, nature 本性, now 如今, history 變化紀錄}。人物性子（功能包 persona；共用規則層 persona_rules.view）開著、他換過段時
    now 寫如今那一段、history 一行一筆（「第 1 週・週五 起，脾氣沒那麼火爆了」），拉鋸與「你勸過他 N 次」接在最後；
    關著、沒換過段 now 是 None、history 是空的，畫面不畫這兩格。簡介檔沒寫他、他卻有性子的，只畫如今與紀錄。"""
    row = FIGURE_INTROS.get(cid) or {}
    shift = persona_rules.view(game.state, game.content, cid) if game is not None else None
    if not row and not (shift and (shift["now"] or shift["history"])):
        return None
    extra = [x for x in ((shift or {}).get("torn"), (shift or {}).get("mine")) if x]
    return {"who": row.get("who", ""), "role": row.get("role", ""), "nature": row.get("nature", ""),
            "now": (shift or {}).get("now"), "history": [*(shift or {}).get("history", []), *extra] if shift else []}
