"""假人看到酒肆的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 tavern 那一段，主動搬六包第 10 批搬來）與進酒肆問一件事（visit；原本 bot_policy._tavern，全部拆包第 60 批搬來）。
bot_policy.take_turn 的 _tavern 那一步叫 visit（進去、問一件、出門；TAVERN_CHANCE 照舊在 bot_policy，叫的那一下才讀，測試換的是它的屬性）；
萬一停在酒肆的選單上，只按「出酒肆」。**模組層不准碰 engine、bot_policy**（bot_policy 模組層 import 這個檔）。"""
from __future__ import annotations

import random

from tianxia.core.option import Option

from . import actions, rules

# 酒肆（tianxia/tavern.py）：人在有酒肆的城鎮、手上銀兩比這一下的價錢多 TAVERN_RESERVE 時，每一輪 bot_policy.TAVERN_CHANCE 的機會進去問一件事、
# 問完出門。真人會打聽人，假人也要會：不然「有人打聽你」的風聲只會來自真人，看得出誰是假人。問什麼照 TAVERN_ASKS 的權重擲；
# 打聽人挑在座的客人、問過的名號或這一區的大勢人物，打聽素材挑一階、二階的；偶爾對查到過的人雇最便宜的那一檔殺手
# （「有人出錢買你」不能只來自真人；同陣營也雇，跟真人一樣不限，企劃者 2026-10-27）；失手過的照加價後的價錢量銀兩。不寫題壁、不請酒、不藏行跡、不反查。
TAVERN_RESERVE = 30
TAVERN_ASKS = (("news", 5), ("seek", 3), ("material", 2), ("ties", 1), ("hit", 0.5))


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return 0.0 if option.id.partition(":")[2] == "back" else None


def visit(game, rng: random.Random, chance: float) -> list[str] | None:
    """進酒肆問一件事、出門；這一輪不做是 None。選單上沒有「酒肆」時不擲骰。"""
    s = game.state
    if "act:tavern" not in {o.id for o in game.options(odds=False, tick=False) if o.enabled}:
        return None
    if rng.random() >= chance:
        return None
    op = rng.choices([k for k, _ in TAVERN_ASKS], weights=[w for _, w in TAVERN_ASKS])[0]
    t = game.content.config.tavern
    price = actions.tavern_price(game, {"news": t.news_price, "seek": t.seek_price, "ties": t.ties_price,
                                        "hit": t.hit_prices[0]}.get(op, max(t.material_prices.values())))
    if s.player.stats.get("silver", 0) < price + TAVERN_RESERVE:
        return None
    msgs = game.choose("act:tavern")
    view = actions.tavern_view(game)
    target = ""
    if op in ("seek", "ties"):
        names = list(view["guests"]) + list(view["known"])
        if not names or rng.random() < 0.4:
            figures = [game.content.characters[f.character].name for f in game.content.figures.values()
                       if f.character in game.content.characters]
            names = names + figures
        target = rng.choice(names) if names else ""
        if not target:
            op = "news"
    elif op == "hit":
        purse = s.player.stats.get("silver", 0) - TAVERN_RESERVE
        foes = [n for n in view["known"] if actions.tavern_hit_problem(game, n, 0)[0] is None
                and actions.tavern_price(game, rules.hit_price_base(game.content, 0, rules.hit_streak(
                    s.world, s.player.name, n, t.hit_fail_max))) <= purse]
        if foes:
            msgs += actions.tavern_do(game, "hit", rng.choice(foes), "0")
            if s.player.picking_tavern:
                msgs += game.choose(view["back"])
            return msgs
        op = "news"
    elif op == "material":
        mats = [m["id"] for m in view["materials"] if m["tier"] <= 2]
        target = rng.choice(mats) if mats else ""
        if not target:
            op = "news"
    msgs += actions.tavern_do(game, op, target)
    if s.player.picking_tavern:
        msgs += game.choose(view["back"])
    return msgs
