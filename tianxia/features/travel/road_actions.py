"""出發、路上小事、路上見聞（功能包 tianxia/features/travel/；原本是 Game._move、_road、_road_*、_road_sight，全部拆包第 47 批）。
ctx 是 Game（第一階）。出發本身（departure.depart）經 ctx._depart 叫（人物帶路與測試換掉的 Game._depart 才打得到）；sight 由 departure.arrivals 迴圈中途直接叫（位置不動）；
收穫由 think／ask／gather 回傳，road 再交給 party.share_road 分給結伴同行的人（不再寄放在 Game 上）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas, materials  # 過渡：待搬（輿圖：路程與所在大區）
from tianxia.models import RoadKind
from tianxia.rules import apply_effect, audible, day_turn, ears_of, game_day, here_regions

from . import menu, party

if TYPE_CHECKING:
    from tianxia.engine import Game


def move(ctx: Game, arg: str) -> list[str]:
    """選單上的「前往 某地」：沿直接相連的那條路出發。arg 是 move: 後面那段——只有地點就是步行，
    「地點:走法」是主畫面「走法」切換選的趕路或疾行（見 menu.move_option）。"""
    dest_id, _, mode = arg.partition(":")
    legs = atlas.path_legs(ctx.content, ctx.state.player.location, [dest_id])
    return ctx._depart(atlas.Route((dest_id,), tuple(legs)), mode or "walk")


def road(ctx: Game, arg: str) -> list[str]:
    """路上的選項（路上設計第三、四節）。road:back[:<走法>] 是折返：回身後那一站，跟大地圖改道走同一條路（見 Game._depart）。
    其餘是路上小事（ROAD_TASKS）：記進這一段做過的，結果照既有慣例寫成「心得 +3」這種變化量。"""
    what, _, mode = arg.partition(":")
    if what == "back":
        return ctx._depart(menu.back_way(ctx), mode or "walk")
    ctx.state.player.leg_actions.add(what)
    tasks = {"think": think, "ask": ask, "gather": gather}
    msgs, gain = tasks[what](ctx)  # 這件小事的收穫（分給結伴同行的人，party.share_road）；各個小事真的給了東西才有，沒有是 None
    return msgs + party.share_road(ctx, what, gain)


def road_ends(ctx: Game) -> tuple[str, str]:
    """這段路的兩頭：身後那一站、前面那一站。"""
    spot = atlas.road_spot(ctx.state, ctx.content)
    return spot.behind, spot.ahead


def rewards_used(ctx: Game, kind: str, day: int | None = None) -> int:
    """這一個遊戲日（rules.game_day，跟每天對話輪數同一個算法、跟著季長縮；不給就是此刻的）路上已經拿過幾次收穫；
    kind 是 "task"（路上小事）或 "sight"（見聞）。紀錄是別的號碼就當沒拿過。"""
    record = ctx.state.player.road_rewards_today.get(kind)
    return record[1] if record and record[0] == (day or game_day(ctx.content, ctx.state.world)) else 0


def reward_due(ctx: Game, kind: str, day: int | None = None) -> bool:
    """這一個遊戲日路上這一種收穫還沒拿滿（企劃者 2026-10-03 決定的每天上限 road_reward_daily_cap）。"""
    return rewards_used(ctx, kind, day) < ctx.content.config.road_reward_daily_cap


def count_reward(ctx: Game, kind: str, day: int | None = None) -> None:
    """記一次真的給出去的收穫（沒撿到東西的採集不算）。"""
    day = day or game_day(ctx.content, ctx.state.world)
    ctx.state.player.road_rewards_today[kind] = [day, rewards_used(ctx, kind, day) + 1]


def reopen(ctx: Game, after: str) -> str:
    """路上收穫拿滿了那兩句括號裡的話：「〔換日的那一刻〕 {after}」；這一季之內不會再換日（rules.day_turn 是 "season"，
    day-scale 審查 M2）時是「這一季之內不會再有」（待 joy 潤）。"""
    kind, moment = day_turn(ctx.content, ctx.state.world)
    if kind == "later":  # 季末延後、換日寫不出那一刻（FB-102，待 joy 潤）：「之後才會再有」→「過一陣子才會再有」
        return "過一陣子" + after.removeprefix("之後")
    return f"{moment} {after}" if moment else "這一季之內不會再有"


def think(ctx: Game) -> tuple[list[str], tuple | None]:
    """邊走邊想：心得（一次遊歷大約 12～20，這裡刻意少很多）。這個遊戲日的收穫拿滿了就照樣想，只是沒有心得
    （寫換日的那一刻，待 joy 潤）。"""
    if not reward_due(ctx, "task"):
        return [f"你邊走邊想，這陣子想得夠多了，沒有新的心得（{reopen(ctx, '之後才會再有')}）。"], None
    p, amount = ctx.state.player, ctx.content.config.road_think_xinde
    p.stats["xinde"] = p.stats.get("xinde", 0) + amount
    count_reward(ctx, "task")
    return ["你邊走邊想，把這幾天的見聞在心裡過了一遍。", f"心得 +{amount}"], ("xinde", amount)


def ask(ctx: Game) -> tuple[list[str], tuple | None]:
    """沿途打聽：這段路兩頭所在大區（Rumor.region；兩頭不同區時兩區都算）最近幾則傳聞裡隨機挑一則；沒有就寫一句，
    仍算做過。聽得到的才挑（rules.audible：別的陣營的軍情、寫給別人的個人線索聽不到）；第一季只挑傳聞板上的
    （最近 rumor_board_days 個季曆天，天下大事也一樣——打聽的是「這一帶最近」的事）。"""
    s, c = ctx.state, ctx.content
    ears, regions = ears_of(s, c), here_regions(s, c)  # 在路上時 here_regions 就是這段路兩頭的大區（beta 的 ears.regions 是空的）
    heard = [
        r for r in s.world.rumors if r.region in regions and r.time >= ears.since and audible(r, ears)
    ][-c.config.road_rumor_pool:]
    if not heard:
        return ["你沿途問了幾個人，這一帶最近沒什麼新鮮事。"], None
    text = ctx.rng.choice(heard).text
    return [f"你沿途向人打聽，聽說：{text}"], ("rumor", text)


def gather(ctx: Game) -> tuple[list[str], tuple | None]:
    """路邊採集：一定機率撿到一樣一階素材；屬性照這段路兩頭的地點寫的素材（Location.materials），兩頭都沒寫就隨機。
    這個遊戲日的收穫拿滿了就不翻（也不擲骰，寫換日的那一刻，待 joy 潤）；撿到了才算一次收穫。"""
    s, c = ctx.state, ctx.content
    if not reward_due(ctx, "task"):
        return [f"你留心路邊，這陣子已經撿夠了，沒再去翻（{reopen(ctx, '之後再說')}）。"], None
    if ctx.rng.random() >= c.config.road_gather_chance:
        return ["你在路邊翻找了一陣，沒找到什麼能用的。"], None
    kinds = {c.materials[m].attribute for end in road_ends(ctx) for m in c.locations[end].materials if m in c.materials}
    pool = [m for m in materials.by_tier(c, 1) if m.attribute in kinds] or materials.by_tier(c, 1)
    if not pool:  # 內容裡沒有一階素材：當成沒找到
        return ["你在路邊翻找了一陣，沒找到什麼能用的。"], None
    count_reward(ctx, "task")
    found = ctx.rng.choice(pool).id
    return ["你在路邊翻找了一陣。", materials.grant(s, c, found)], ("material", found)


def sight(ctx: Game, road: RoadKind, loc_id: str, when: float | None = None) -> list[str]:
    """路上見聞（路上設計第五節）：抵達一站時有 road_sight_chance 的機會，從符合這段路的種類、剛抵達那一站
    見聞裡平均挑一則（最近看過的 road_sight_recent 則先排除，池子不夠才重複）。文字寫進這次抵達的紀錄，小
    接在後面。寫好的文字、不呼叫模型，下線補算時照樣發生。機率是 0 或池子是空的時候連骰子都不擲。
    有收穫的見聞受每天上限管（企劃者 2026-10-03 決定，跟路上小事各算各的）：抵達那一個遊戲日（when，下線補算時是當時的
    抵達時間；遊戲日跟著季長縮，rules.game_day）的 "sight" 收穫拿滿了，給銀兩、素材的見聞就不挑（文字寫的就是拿到東西），
    給心得的照寫文字、不給心得；真的給了才算一次。沒有收穫的見聞不算次數。"""
    s, c = ctx.state, ctx.content
    day = game_day(c, s.world, when)
    capped = not reward_due(ctx, "sight", day)
    region = atlas.region_of(c, loc_id)
    area = region.id if region is not None else None
    pool = [
        sight for sight in c.road_sights.values()
        if (not sight.roads or road in sight.roads) and (not sight.regions or area in sight.regions)
        and not (capped and (sight.effect.materials or sight.effect.stats.get("silver")))
    ]
    chance = c.config.road_sight_chance
    if not pool or chance <= 0 or ctx.rng.random() >= chance:
        return []
    recent = s.player.recent_sights
    pick = ctx.rng.choice([x for x in pool if x.id not in recent] or pool)
    keep = c.config.road_sight_recent
    s.player.recent_sights = (recent + [pick.id])[-keep:] if keep else []
    rewarded = bool(pick.effect.stats or pick.effect.materials)  # 載入檢查保證見聞只會有這兩種效果
    if not rewarded or capped:
        return [pick.text]
    count_reward(ctx, "sight", day)
    return [pick.text] + apply_effect(pick.effect, s, c, ctx.world, push=ctx.push_trend)
