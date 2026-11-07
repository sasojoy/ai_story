"""探索的底（功能包 tianxia/features/explore/；全部拆包第 18 批，計畫 docs/superpowers/plans/2026-11-04-探索包-第3批.md 1.1）：
原本 Game 上舊探索的 8 個方法——`_explore`、`_explore_outcome`（含序章草廬四景）、`_explore_weights`、`_explore_can`、`_wild_foes`、
`_here_squads`、撿破境丹 `_legend_find`、練功分級 `_practice_tier`。Game 留 6 個一行委派（`_explore_outcome`、`_here_squads` 只有這一包自己叫，
不留）。

ctx 是 Game（第一階）；只叫 tianxia/core/services_list.md 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx）。**經 ctx 叫的**：
`_explore_weights`、`_explore_can`、`_legend_find`、`_wild_foes`（測試與 scripts/same_behavior.py 在 Game 上換掉它們，包裡直接叫模組函式就換不到）；
`_explore_outcome`、`_here_squads` 沒有人換過，包內直接叫。擲骰順序（頭目 → 奇遇 → 比重抽一支 → 野怪／事件）、`_legend_find` 機率 0 不擲、
序章裡不撿破境丹也不擲，都照原本；`ctx.rng` 就是原本的 `self.rng`。

跟核心的 tianxia/core/explore_base.py（全部拆包第 50 批）同檔名、不同模組：這一份是探索包的探索的底，那一份是核心的探索表小函式
（LOSE_WORD、六種地點與四類事、「多半」那兩個字、terrain_tags）；兩份照留、不改名（第 50 批 PM 認定第 5 條）。
"""
from __future__ import annotations

import random

from tianxia import insights  # 共用規則層（這裡悟不悟得出）
from tianxia import prologue as prologue_rules  # 共用規則層（序章草廬四景）
from tianxia import renown, team, territory, training, treasures  # 核心、共用規則層
from tianxia.events import event_candidates, pick_event  # 共用規則層（事件：候選、抽一則）
from tianxia.models import EXPLORE_BRANCHES, ExploreBranch, Location, Squad


def practice_tier(ctx, loc: Location) -> int | None:
    """這裡練功是第幾級（0、1、2；Config.training）：照此刻這裡最弱、不是自己人的對手。城裡操練關著、這裡沒有對手是 None。"""
    if not training.on(ctx.content, ctx.state.world):
        return None
    foes = ctx._wild_foes(loc)
    return training.tier_of(ctx.content.config.training, min(f.difficulty for f in foes)) if foes else None


def explore(ctx) -> list[str]:
    """探索三選一（FB-013，docs/superpowers/specs/2026-10-03-探索三選一-design.md）。

    1. 奇遇判定最優先：這裡有還能遇上的一次性或奇遇事件時，先滾 `rare_explore_chance`，中了就是它。
    2. 沒中就照地點類型（`Config.explore_mix`）的比例抽悟意境、野怪、事件三支之一；做不了的那一支
       （沒有會打的對手、沒有可重複的事件）從候選裡拿掉，用剩下的比例重抽——等於把它的比例按比例分給另外兩支。
    3. 三支都做不了才是一無所獲。
    4. 不論走哪一支，結束後再擲一次有沒有撿到破境丹（`_legend_find`）。

    以前是「先滾三成素材，再一定撞到一個事件」：40 個地點有 38 個探索 100% 跳事件，荒郊野外跟
    城裡的手感一樣（QA 量過）。奇遇事件只走第 1 步、不進事件那一支，所以一直是稀有的。
    """
    if prologue_rules.active(ctx.state, ctx.content):
        return explore_outcome(ctx)  # 序章裡不撿破境丹（新手引導計畫一）
    scouted = ctx.publish("explore", ctx.state.player.location)  # 事件 explore（第 26 批）：懸賞榜的打探，探索一次就算
    return explore_outcome(ctx) + ctx._legend_find() + ctx._scrap_find() + scouted


def legend_find(ctx, rng: random.Random | None = None) -> list[str]:
    """探索不論走哪一支，結束後擲一次有沒有撿到破境丹（企劃者 2026-10-05：到處探索都有約 2% 的機會；帶著「探索撿破境丹」的寶物時門檻 ×2）。
    機率是 0 就不擲骰（先判斷機率，亂數序列一個都不動：測試內容把它設成 0，既有的固定種子序列才不會位移）。
    兩行：「獲得」開頭的敘事（江湖紀錄給它掃光，journal._NEW_THING）與「破境丹 +1」（寫進紀錄的數值變化）。
    rng：探索三選一傳自己的亂數；舊的探索不傳，照舊用 Game.rng。"""
    cfg = ctx.content.config
    # 寶物「探索撿破境丹」（裝備四欄 6.2）：只放大門檻（夾在 1 以下），擲的還是同一顆 ctx.rng.random()——帶不帶都只擲一次，
    # 序列不位移；基本機率是 0 照舊不擲（測試內容）
    chance = min(1.0, cfg.explore_legend_chance * treasures.amount(ctx.state, ctx.content, "legend"))
    if cfg.explore_legend_chance <= 0 or (rng or ctx.rng).random() >= chance:
        return []
    ctx.state.player.legend_items += 1
    return [f"獲得 【{cfg.legend_item_name}】一枚——{cfg.legend_item_note}", f"{cfg.legend_item_name} +1"]


def explore_outcome(ctx) -> list[str]:
    s, c = ctx.state, ctx.content
    loc = c.locations[s.player.location]
    sight = prologue_rules.explore_event(s, c)
    if sight is not None:  # 序章第 3 步：草廬四景四選一（新手引導設計 3.2），不抽奇遇、不分三支
        return ctx._present(c.events[sight], "explore")
    scene = prologue_rules.explore_scene(s, c)
    if scene is not None:  # 序章第 3 步的有所感版（悟意境設計第七節）：草廬四景就是四個做法，都對、必中
        return ctx._sense_start(scene, ctx.rng)
    boss = ctx._boss_ready()  # 單人頭目戰：只有這裡有頭目時才擲（沒有頭目的地點、測試內容，亂數序列一個都不動）
    # 名聲 4.4：名望高、頭目找上門的機會乘 renown.duel_chance（只放大門檻，擲的還是同一顆骰）
    if boss is not None and ctx.rng.random() < c.config.duel.explore_chance * renown.duel_chance(s, c):
        return ctx._duel_start(boss)
    if event_candidates(s, c, "explore", "rare") and ctx.rng.random() < c.config.rare_explore_chance:
        return ctx._present(pick_event(s, c, "explore", ctx.rng, "rare"), "explore")
    weighted = ctx._explore_weights(loc)
    if not weighted:
        return ["你四處走走，一無所獲。"]
    branch = ctx.rng.choices([b for b, _ in weighted], weights=[w for _, w in weighted])[0]
    if branch == "insight":  # 有場景：有所感，要選做法、畫一筆才悟得到（悟意境設計第零節）；沒有場景的內容（測試內容）照舊直接悟
        return ctx._sense_here(loc, ctx.rng)  # 就是靜心感悟那四行（有所感包，第 24 批）
    if branch == "wild":
        squad = min(ctx._wild_foes(loc), key=lambda foe: foe.difficulty)  # 同分取這裡列的第一路
        return [f"你在{loc.name}走著，{squad.name}突然殺出！"] + ctx._squad_encounter(squad.id, wild=True)
    return ctx._present(pick_event(s, c, "explore", ctx.rng, "common"), "explore")


def explore_weights(ctx, loc: Location) -> list[tuple[ExploreBranch, float]]:
    """探索三選一此刻在這裡的候選與比重（探索三選一設計第三節）：照地點類型（Config.explore_mix），比例是 0 的與做不了的
    （_explore_can）拿掉；悟意境那一支的比重 ×（1＋3%×（悟性−5））× 寶物（treasures.amount 的 insight，裝備四欄 6.2），另外兩支不動（武學與成長設計 6.1）。
    探索真的擲骰（_explore_outcome）與行動列底下那一行（action_notes，explain-1）讀同一份：說的跟擲的不會走樣。"""
    s, c = ctx.state, ctx.content
    mix = c.config.explore_mix_of(loc.tags).weights
    wis = team.stat_factor(c, team.v1_stat(s, c, "wis"), s.world)
    sharp = wis * treasures.amount(s, c, "insight")  # 寶物「探索悟意境」跟悟性疊乘（裝備四欄 6.2）
    return [
        (b, mix[b] * (sharp if b == "insight" else 1))
        for b in EXPLORE_BRANCHES if mix.get(b, 0) > 0 and ctx._explore_can(b, loc)
    ]


def explore_can(ctx, branch: ExploreBranch, loc: Location) -> bool:
    """探索三選一的這一支在這裡做不做得了。"""
    if branch == "insight":
        if ctx._sense_missed(loc):
            return False  # 這個遊戲日在這裡選錯過做法：換日之前這裡悟不出什麼（Q2）
        return bool(insights.explore_gives(loc, ctx.content))  # 輿圖詳情欄「這裡能悟」用同一個判斷（W3）
    if branch == "wild":
        return bool(ctx._wild_foes(loc))
    return bool(event_candidates(ctx.state, ctx.content, "explore", "common"))


def wild_foes(ctx, loc: Location) -> list[Squad]:
    """探索時可能殺出來的野怪：這裡此刻站的隊伍（地盤易手照控制方，_here_squads）裡不是自己陣營的那幾路
    （自己人不會突然殺出來，也不在這裡操練）。"""
    squads = [ctx.content.squads[sid] for sid in here_squads(ctx, loc.id)]
    return [squad for squad in squads if not ctx._drills_with(squad)]


def here_squads(ctx, loc_id: str) -> list[str]:
    """這個地點此刻站的隊伍（territory.squads_at；地盤易手的開關關著就是 loc.enemies）。"""
    return territory.squads_at(ctx.state.world, ctx.content, loc_id)
