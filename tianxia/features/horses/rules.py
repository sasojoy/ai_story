"""馬的來路：給玩家看的字與只看數字的判斷（不碰存檔）。Joy 2026-11-10 選擇卡選「奪馬＋馴野馬＋論功賜馬」。"""
from __future__ import annotations

TITLE = "馴野馬"  # 待 joy 潤：江湖紀錄的標題
KIND = "horses"

# 奪馬（事件 win）
SEIZE_LINE = "{foe}裡有一匹沒了主人的{grade}【{name}】，你牽了回來。"  # 待 joy 潤

# 論功賜馬（事件 showdown_pay）
MERIT_LINE = "論功行賞，你戰功排第 {rank}，主帥賜你{grade}【{name}】。"  # 待 joy 潤
MERIT_GAIN = "賜馬【{name}】"  # 待 joy 潤

# 馴野馬
TAME_LABEL = "馴野馬"  # 待 joy 潤：鈕（後面接體力與第幾步）
TAME_STEP_NOTE = "第 {step}／{steps} 步"  # 待 joy 潤
TAME_STEP = [  # 待 joy 潤：前幾步（照步數，最後一句重複用）
    "你拿{material}引著野馬群，慢慢靠近了一匹落單的。",
    "你翻上馬背，被甩下來兩次，第三次總算坐穩了一會。",
]
TAME_DONE = "牠終於不再踢跳，低頭吃你手上的{material}。你馴成了一匹{grade}【{name}】。"  # 待 joy 潤
TAME_STEED = "坊間傳言：{who}在{place}馴服了一匹野生的名駒【{name}】。"  # 待 joy 潤：天下大事
TAME_FAIL = "野馬一聲長嘶，掙斷套索跑回馬群，前面的功夫白費了。"  # 待 joy 潤
TAME_GONE = "這一週的野馬群已經被人馴走了，下週再來"  # 待 joy 潤：灰掉的理由
TAME_CAPPED = "這一季你已經馴過一匹了"  # 待 joy 潤
TAME_NO_MATERIAL = "身上沒有一階素材"  # 待 joy 潤
TAME_NO_ROOM = "裝備庫滿了，牽不回去"  # 待 joy 潤
TAME_GAIN = "馴得【{name}】"  # 待 joy 潤


def herd_key(week: int, loc_id: str) -> str:
    return f"{week}|{loc_id}"


def merit_tier(rank: int, steed_top: int, horse_top: int) -> int | None:
    """戰功第 rank 名（從 1 起）賜哪一階：名駒 3、良駒 2、不賜 None。"""
    if rank <= steed_top:
        return 3
    if rank <= horse_top:
        return 2
    return None
