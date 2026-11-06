"""假人看到「探索」那一格怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 act:explore 那幾行與 _outing_score、_short_of_materials，全部拆包第 60 批搬來，Verb.bot 問）。

_crippled、_bounty_here 與分數常數（OUTING_SCORE、BOUNTY_SCORE、NEED_MATERIAL_SCORE、ACT_SCORES）還在 bot_policy（移動包的 move: 也讀，測試也讀這幾個名字），所以經 `from tianxia import bot_policy`
延後 import（舊模組 import engine，包不能在模組載入時 import 它；第 47 批前例）；照模組屬性讀，測試換掉也生效。
走一趟挑幾段、走完那一句在 bot.py（整季機器人與假人共用的底層，不搬）。
"""
from __future__ import annotations

OUTING_CRIPPLED_SHARE = 0.5  # 內傷重又付不起醫館（_crippled）時，遭遇佔比重這麼多以上的地方（這一趟有這麼大的機會遇敵）不出門（同不去練功）
NEED_MATERIAL_BELOW = 6  # 背包裡的一階素材少於這麼多個：多半給素材的那一趟再加 bot_policy.NEED_MATERIAL_SCORE


def score(game) -> float | None:
    """act:explore 的分數：探索一顆開著（Game.outing_plan 不是 None）照那一趟的比重；關著（舊探索、序章）這裡有打探懸賞就去，不然照 ACT_SCORES。"""
    from tianxia import bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    plan = game.outing_plan()
    if plan is not None:  # 減法季探索一顆：「探索」就是出門一趟（有體力才按得下去）
        return _outing_score(game, plan)
    if bp._bounty_here(game, "scout"):
        return bp.BOUNTY_SCORE
    return bp.ACT_SCORES["explore"]


def _outing_score(game, plan) -> float | None:
    """探索一顆的分數（Game.outing_plan 那一份比重）：底分 OUTING_SCORE，遭遇佔比重的那一份（一趟只抽一件事，就是這一趟遇敵的機會；接了討伐懸賞是整趟）乘下一場的疲勞（Game.fatigue_next：減法季三道閘，
    今天打得多了遭遇的收穫少，出門的意願跟著降；三道閘關著是 1）；接了這裡的討伐懸賞、這裡有打探懸賞各加 BOUNTY_SCORE；缺素材而這裡素材的比重
    不比遭遇低再加 NEED_MATERIAL_SCORE。內傷重、付不起醫館的不去多半遇敵的地方（去城裡、寺裡攢錢）。"""
    from tianxia import bot_policy as bp  # noqa: PLC0415  過渡：待搬（假人的分數與挑法還在舊模組）

    w = plan.weights
    total = sum(w.values()) or 1
    fight = w.get("encounter", 0) / total
    if fight >= OUTING_CRIPPLED_SHARE and bp._crippled(game):
        return None
    tired = game.fatigue_next()
    value = bp.OUTING_SCORE if tired >= 1 else bp.OUTING_SCORE * (1 - fight * (1 - tired))
    value += bp.BOUNTY_SCORE if plan.how == "bounty" else 0.0
    value += bp.BOUNTY_SCORE if bp._bounty_here(game, "scout") else 0.0
    if _short_of_materials(game) and w.get("material", 0) >= w.get("encounter", 0):
        value += bp.NEED_MATERIAL_SCORE
    return value


def _short_of_materials(game) -> bool:
    """背包裡的一階素材少於 NEED_MATERIAL_BELOW 個（修兵器、餵馬、糧草都吃一階）。"""
    mats = game.content.materials
    return sum(n for mid, n in game.state.player.materials.items() if mid in mats and mats[mid].tier == 1) < NEED_MATERIAL_BELOW
