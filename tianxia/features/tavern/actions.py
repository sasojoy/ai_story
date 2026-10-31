"""酒肆的動作（功能包 tianxia/features/tavern/；原本是 Game 上酒肆的 43 個方法，開發規範手冊 3.2、主動搬六包第 10 批）。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。本體照搬、一個字不改（self 換成 ctx；包裡互相叫直接叫這裡的
函式）。函式名＝原本的方法名去掉前導底線（`_tavern_news` → `tavern_news`、`_deliver_hits` → `deliver_hits`），兩個例外：公開的
`tavern_ask` 是 `tavern_ask_reply`、私有的 `_tavern_ask` 是 `tavern_ask_once`——這裡 `tavern_ask` 是問酒家那個模組（ask.py）的名字，
本體照舊寫 `tavern_ask.topics(...)`。另加一個 `tavern_sign`：`act:tavern` 那一下紀錄的標題（Game._action_title 叫 Game._tavern_sign）。
`_tavern_run` 的動作表原本放的是 Game 的方法本身（`self._tavern_news`），這裡換成同樣不帶參數的 lambda。
Game 上留 19 個一行委派（server、假人、腳本、測試與核心原位還在叫：選單接管那一格、act:tavern、sync 的下線殺手與三個 deliver、
choose 最後那一下殺手檢查、shop_view、紀錄標題）。換掉的模組屬性一律照模組叫（tavern_rules.find_chance、encounter.resolve_encounter），
Game._spar_power 經 ctx 叫（測試換掉的才打得到）。
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from tianxia import team
from tianxia import annals  # 過渡：待搬（行狀：殺手那一場記一筆）
from tianxia import battlelog  # 過渡：待搬（戰報：殺手那一場）
from tianxia import bounties  # 過渡：待搬（懸賞榜：通緝名單、牆上的榜）
from tianxia import encounter  # 過渡：待搬（單次判定：殺手那一場；測試換掉 encounter.resolve_encounter）
from tianxia import equipment  # 過渡：待搬（店沒開時那一句 NOT_NOW）
from tianxia import renown  # 過渡：待搬（名望、惡名、名望段）
from tianxia import roster  # 過渡：待搬（截殺與通緝的新手期）
from tianxia import shopview  # 過渡：待搬（店面：掌櫃那一句、素材屬性的排序）
from tianxia import social  # 過渡：待搬（此地還有誰、站哪一邊）
from tianxia.calendar import DAY, HOUR
from tianxia.characters import CharacterStore, name_key
from tianxia.core.option import Option
from tianxia.models import Squad
from tianxia.rules import add_rumor, display_name
from tianxia.state import PLAYER, GameState, TavernHit, TavernWatch, Whisper

from . import ask as tavern_ask
from . import rules as tavern_rules

if TYPE_CHECKING:
    from tianxia.engine import Game

# ── 酒肆（企劃者 2026-10-18；設計稿 https://claude.ai/artifact/3CfrzfpT1HzCxy6S985Q5W）────────────
# 規則全在 rules.py（tavern_rules）；這裡只管接上選單、扣錢、讀別人的存檔、寫紀錄與季。


def tavern_sign(ctx: Game) -> str:
    """act:tavern 那一下江湖紀錄的標題（招牌；Game._action_title 經 Game._tavern_sign 叫，同出陣的 _train_title）。"""
    return tavern_rules.sign(ctx.state, ctx.content)


def tavern_open(ctx: Game) -> bool:
    """酒肆那一串此刻開著、人也還在酒肆裡（MAIN_ACTIONS["tavern"] 收不收的判斷）。"""
    return ctx.state.player.picking_tavern and tavern_rules.here(ctx.state, ctx.content)


def tavern_enter(ctx: Game) -> list[str]:
    s, c = ctx.state, ctx.content
    if not (tavern_rules.on(c) and tavern_rules.here(s, c)) or not ctx._idle():
        return [tavern_rules.NOT_HERE]
    s.player.picking_tavern, s.player.shop_clue = True, ""
    ctx._shop_say("enter")
    return [tavern_rules.ENTERED.format(sign=tavern_rules.sign(s, c))]


def tavern_price(ctx: Game, base: int) -> int:
    return tavern_rules.price(ctx.content, ctx.state.world, base)


def tavern_options(ctx: Game) -> list[Option]:
    """酒肆那一串（店面關著、假人與整季機器人看的選單）：聽消息、請酒、藏行跡、反查、懸賞榜、出酒肆。查人、交情、素材、題壁要打字或挑東西，
    只在店面上（MAIN_ACTIONS["tavern"]）。錢不夠的灰掉寫還差多少。都不花體力。"""
    s, c = ctx.state, ctx.content
    cfg = c.config.tavern
    opts = []
    for oid, label, base, problem in (
        (tavern_rules.NEWS_ID, tavern_rules.NEWS_LABEL, cfg.news_price, None),
        (tavern_rules.TREAT_ID, tavern_rules.TREAT_LABEL, cfg.treat_price, tavern_treat_problem(ctx)),
        ("tavern:hide", tavern_rules.HIDE_LABEL, cfg.hide_price, tavern_hide_problem(ctx)),
        ("tavern:trace", tavern_rules.TRACE_LABEL, cfg.trace_price, None),
    ):
        price = tavern_price(ctx, base)
        problem = problem or tavern_rules.pay_problem(s, price)
        text = label.format(price=price)
        opts.append(Option(id=oid, label=text if problem is None else f"{text}・{problem}", enabled=problem is None))
    if bounties.board_here(s, c) and bounties.visible(s, c):
        opts.append(Option(id=tavern_rules.BOARD_ID, label=tavern_rules.BOARD_LABEL))
    return opts + [Option(id=tavern_rules.BACK_ID, label=tavern_rules.BACK_LABEL)]


def tavern_choice(ctx: Game, arg: str) -> list[str]:
    if arg == "back":
        tavern_rules.close(ctx.state)
        return [tavern_rules.LEFT]
    if arg == "board":  # 牆上的懸賞榜：收起酒肆、打開懸賞榜（同城裡的 act:bounties）
        tavern_rules.close(ctx.state)
        ctx.state.player.picking_bounty = True
        ctx._shop_say("enter")
        return [f"你走到牆邊，看起{bounties.BOARD}。"]
    return tavern_run(ctx, arg)


def tavern_do(ctx: Game, op: str, target: str = "", text: str = "") -> list[str]:
    """酒肆那一頁的動作（MAIN_ACTIONS["tavern"]）：news 聽消息、seek 查人在哪、ties 打聽交情、material 打聽素材（target 是素材 id）、
    wall 題壁（text）、treat 請酒、hide 藏行跡、trace 反查。酒肆開著才收；做成了寫一則紀錄（同一趟坐下來的併成一則）。"""
    if not tavern_open(ctx):
        return ctx._log([equipment.NOT_NOW])
    return ctx._log(tavern_run(ctx, str(op), str(target or "").strip(), str(text or "")))


def tavern_run(ctx: Game, op: str, target: str = "", text: str = "") -> list[str]:
    s = ctx.state
    before = s.player.stats.get("silver", 0)
    handler = {
        "news": lambda: tavern_news(ctx), "treat": lambda: tavern_treat(ctx), "hide": lambda: tavern_hide(ctx),
        "trace": lambda: tavern_trace(ctx),
        "seek": lambda: tavern_seek(ctx, target, watch=text == "watch"), "ties": lambda: tavern_ties(ctx, target),
        "material": lambda: tavern_material(ctx, target), "wall": lambda: tavern_wall(ctx, text),
        "hit": lambda: tavern_hit(ctx, target, text), "guard": lambda: tavern_guard(ctx),
        "ask": lambda: tavern_ask_once(ctx, text),
    }.get(op)
    if handler is None:
        return ["（沒有這個動作。）"]
    msgs = handler()
    paid = before - s.player.stats.get("silver", 0)
    if paid:
        msgs = msgs + [f"銀兩 {-paid:+d}"]
    if paid:  # 真的花了錢（問不到退一半也算）才寫紀錄；被拒、沒收錢的只回一句
        s.player.newbie_marks.add("tavern")  # 新手目標：在酒肆打聽一件事
        ctx._write(tavern_rules.sign(s, ctx.content), msgs, merge=True)
        ctx._save_season()
    return msgs


def tavern_charge(ctx: Game, base: int) -> int | None:
    """扣這一下的錢：付得起回價錢，付不起記掌櫃那一句、回 None。"""
    price = tavern_price(ctx, base)
    problem = tavern_rules.pay_problem(ctx.state, price)
    if problem is not None:
        ctx._shop_after(problem, "refused")
        return None
    tavern_rules.pay(ctx.state, price)
    return price


def tavern_short(ctx: Game, base: int) -> list[str]:
    return [tavern_rules.pay_problem(ctx.state, tavern_price(ctx, base)) or ""]


def tavern_wanted(ctx: Game) -> set[str]:
    """身上有通緝的名號鍵（名氣 +1）。"""
    return {name_key(b.target) for b in bounties.open_bounties(ctx.state, ctx.content) if b.kind == "wanted" and b.target}


def tavern_news(ctx: Game) -> list[str]:
    s, c = ctx.state, ctx.content
    pick = tavern_rules.news_pick(s, c)
    region = tavern_rules.region_lines(s, c)
    if pick is None and not region:
        ctx._shop_say("nothing")
        return [tavern_rules.NOTHING_NEW]
    if tavern_charge(ctx, c.config.tavern.news_price) is None:
        return tavern_short(ctx, c.config.tavern.news_price)
    lines = []
    if pick is not None:
        lines.append(f"{tavern_rules.NEWS_HEAD}「{pick.text}」")
        s.player.tavern_heard = (s.player.tavern_heard + [tavern_rules.rumor_key(pick)])[-200:]
    lines += region
    tavern_rules.add_note(s, c, "news", tavern_rules.TITLES["news"], lines)
    ctx._shop_say("news")
    return lines


def tavern_find(ctx: Game, target: str) -> tuple[str | None, Game | None]:
    """名號認人：先認人物（名字一模一樣），再認玩家存檔（不分大小寫）。回（人物 id, 玩家那一份）；都不是是 (None, None)。"""
    c = ctx.content
    for cid, ch in c.characters.items():
        if ch.name == target:
            return cid, None
    if name_key(target) == name_key(ctx.state.player.name):
        return None, None
    other = ctx._load_kin(target)
    if other is not None:
        other.state.world = ctx.state.world
    return None, other


def tavern_whisper(ctx: Game, kind: str, other: Game) -> None:
    """被打聽的人收到風聲：記在季上，他下次同步時補（_deliver_whispers）。匿名行走的人只會是個生面孔。"""
    s, c = ctx.state, ctx.content
    w = tavern_rules.whisper(kind, s, c, s.player.location, s.world.time)
    if s.player.anonymous:
        w.named = False
    tavern_rules.post_whisper(s.world, other.state.player.name, w)
    ctx.touched.add(other.state.player.name)


def tavern_watch_problem(ctx: Game, target: str) -> str | None:
    p, cfg = ctx.state.player, ctx.content.config.tavern
    mine = [w for w in p.tavern_watches if w.until_real > ctx.now]
    if any(name_key(w.target) == name_key(target) for w in mine):
        return tavern_rules.WATCH_SAME.format(name=target)
    if len(mine) >= cfg.watch_keep:
        return tavern_rules.WATCH_FULL.format(n=cfg.watch_keep)
    return None


def tavern_seek(ctx: Game, target: str, watch: bool = False) -> list[str]:
    lines = tavern_seek_once(ctx, target)
    if not watch or not target or name_key(target) == name_key(ctx.state.player.name) or ctx._tavern_seek_exact is None:
        return lines
    if ctx._tavern_seek_exact:
        return lines + [tavern_rules.WATCH_CLEAR]
    return lines + tavern_watch(ctx, target)


def tavern_watch(ctx: Game, target: str) -> list[str]:
    """託酒家留意：多付查人的 watch_share，記在自己身上；他自己同步時那個人打聽得到確切地點就捎信（_deliver_watches）。
    查無此人也照收（不讓人拿託付試出誰在不在），到期捎一句沒聽到準信。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    problem = tavern_watch_problem(ctx, target)
    if problem is not None:
        return [problem]
    base = int(round(cfg.seek_price * cfg.watch_share))
    if tavern_charge(ctx, base) is None:
        return tavern_short(ctx, base)
    p = s.player
    p.tavern_watches = [w for w in p.tavern_watches if w.until_real > ctx.now]
    p.tavern_watches.append(TavernWatch(target=target, place=p.location, until_real=ctx.now + cfg.watch_hours * 3600))
    line = tavern_rules.WATCH_PLACED.format(name=target)
    if p.tavern_notes:
        p.tavern_notes[-1].lines.append(line)
    return [line]


def deliver_watches(ctx: Game) -> None:
    """託的人自己同步時：留意的那個人打聽得到確切地點（從託的那一間算，打聽度 WATCH_AT 以上、沒下線太久）就捎信；到期的捎一句沒消息。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    p = s.player
    if not p.tavern_watches:
        return
    lines, keep = [], []
    for w in p.tavern_watches:
        other = ctx._load_kin(w.target)
        if other is not None:
            other.state.world = s.world
            op = other.state.player
            seen = op.seen_real or 0.0
            online = not seen or ctx.now - seen <= cfg.offline_hours * 3600
            if online and tavern_rules.hit_reach(c, w.place, other.state) >= tavern_rules.WATCH_AT:
                if op.journey is not None:
                    lines.append(tavern_rules.WATCH_ROAD.format(name=op.name, place=c.locations[op.journey.path[op.journey.last]].name))
                else:
                    lines.append(tavern_rules.WATCH_FOUND.format(name=op.name, place=c.locations[op.location].name))
                tavern_rules.remember(s, op.name)
                continue
        if w.until_real <= ctx.now:
            lines.append(tavern_rules.WATCH_LAPSED.format(name=w.target))
            continue
        keep.append(w)
    if len(keep) != len(p.tavern_watches):
        p.tavern_watches = keep
    if lines:
        ctx._write(tavern_rules.WATCH_TITLE, lines)


def tavern_seek_once(ctx: Game, target: str) -> list[str]:
    s, c = ctx.state, ctx.content
    cfg = c.config.tavern
    ctx._tavern_seek_exact = None  # 查人那一下問得多清楚（託酒家留意看它）：None 沒查成、True 確切地點、False 沒問清楚
    if not target:
        return [tavern_rules.ASK_EMPTY]
    if name_key(target) == name_key(s.player.name):
        return [tavern_rules.ASK_SELF]
    if tavern_charge(ctx, cfg.seek_price) is None:
        return tavern_short(ctx, cfg.seek_price)
    ctx._tavern_seek_exact = False
    price = tavern_price(ctx, cfg.seek_price)
    cid, other = tavern_find(ctx, target)
    if cid is not None:
        lines = tavern_rules.seek_figure_lines(s, c, cid)
        ctx._tavern_seek_exact = True  # 人物不託（他們走到哪都有人談）
    elif other is not None:
        lines, found = tavern_rules.seek_lines(s, c, other.state, ctx.now, tavern_wanted(ctx))
        seen = other.state.player.seen_real or 0.0
        ctx._tavern_seek_exact = found and (not seen or ctx.now - seen <= cfg.offline_hours * 3600) \
            and tavern_rules.person_reach(s, c, other.state, tavern_wanted(ctx)) >= tavern_rules.WATCH_AT
        tavern_whisper(ctx, "seek", other)
        if not found:
            back = tavern_rules.refund(s, c, price)
            ctx._shop_say("missed")
            lines = [tavern_rules.HALF_MISS.format(refund=back) if tavern_rules.person_fame(other.state, c) >= 1
                     else tavern_rules.NOBODY.format(refund=back)]
            tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
            return lines
        tavern_rules.remember(s, other.state.player.name)
    else:  # 沒有這個人：跟默默無名的人問不到同一句（不讓人拿酒肆試出誰在不在）
        back = tavern_rules.refund(s, c, price)
        ctx._shop_say("missed")
        lines = [tavern_rules.NOBODY.format(refund=back)]
        tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
        return lines
    tavern_rules.add_note(s, c, "seek", f"{tavern_rules.TITLES['seek']}・{target}", lines)
    ctx._shop_say("asked")
    return lines


def tavern_ties(ctx: Game, target: str) -> list[str]:
    s, c = ctx.state, ctx.content
    cfg = c.config.tavern
    if not target:
        return [tavern_rules.ASK_EMPTY]
    if name_key(target) == name_key(s.player.name):
        return [tavern_rules.ASK_SELF]
    if tavern_charge(ctx, cfg.ties_price) is None:
        return tavern_short(ctx, cfg.ties_price)
    price = tavern_price(ctx, cfg.ties_price)
    cid, other = tavern_find(ctx, target)
    wanted = tavern_wanted(ctx)
    found = True
    if cid is not None:
        holders = []
        if hasattr(ctx.world, "db"):
            for state in CharacterStore(ctx.world.db).all():
                n = state.player.affinities.get(cid, 0)
                if n > 0 and name_key(state.player.name) != name_key(s.player.name):
                    state.world = s.world
                    holders.append((state, n))
        holders.sort(key=lambda pair: (-pair[1], pair[0].player.name))
        lines = tavern_rules.ties_figure_lines(s, c, cid, holders, wanted)
    elif other is not None:
        mates = [c.characters[m].name for m in other.state.player.team if m in c.characters]
        lines, found = tavern_rules.ties_player_lines(s, c, other.state, mates, wanted)
        tavern_whisper(ctx, "ties", other)
        if found:
            tavern_rules.remember(s, other.state.player.name)
    else:
        lines, found = [], False
    if not found:
        back = tavern_rules.refund(s, c, price)
        ctx._shop_say("missed")
        lines = [tavern_rules.NOBODY.format(refund=back)]
    else:
        ctx._shop_say("asked")
    tavern_rules.add_note(s, c, "ties", f"{tavern_rules.TITLES['ties']}・{target}", lines)
    return lines


def tavern_material(ctx: Game, mid: str) -> list[str]:
    s, c = ctx.state, ctx.content
    material = c.materials.get(mid)
    if material is None:
        return [tavern_rules.MATERIAL_UNKNOWN]
    base = c.config.tavern.material_prices.get(material.tier, max(c.config.tavern.material_prices.values()))
    if tavern_charge(ctx, base) is None:
        return tavern_short(ctx, base)
    lines, found = tavern_rules.material_lines(s, c, material)
    if not found:
        back = tavern_rules.refund(s, c, tavern_price(ctx, base))
        lines = [tavern_rules.MATERIAL_NONE.format(name=material.name, refund=back)]
        ctx._shop_say("missed")
    else:
        ctx._shop_say("asked")
    tavern_rules.add_note(s, c, "material", f"{tavern_rules.TITLES['material']}・{material.name}", lines)
    return lines


def tavern_wall(ctx: Game, text: str) -> list[str]:
    s, c = ctx.state, ctx.content
    problem = tavern_rules.wall_problem(c, text)
    if problem is not None:
        ctx._shop_after(problem, "wall")
        return [problem]
    if tavern_charge(ctx, c.config.tavern.wall_price) is None:
        return tavern_short(ctx, c.config.tavern.wall_price)
    tavern_rules.write_wall(s.world, c, s.player.location, display_name(s), text)
    ctx._shop_say("wall")
    return [tavern_rules.WALL_DONE, f"「{text.strip()}」"]


def tavern_treat_problem(ctx: Game) -> str | None:
    return tavern_rules.TREAT_FULL if ctx.state.player.tavern_treat_day == ctx._pill_day() else None


def tavern_treat(ctx: Game) -> list[str]:
    s, c = ctx.state, ctx.content
    cfg = c.config.tavern
    problem = tavern_treat_problem(ctx)
    if problem is not None:
        ctx._shop_after(problem, "treat")
        return [problem]
    if tavern_charge(ctx, cfg.treat_price) is None:
        return tavern_short(ctx, cfg.treat_price)
    p = s.player
    p.tavern_treat_day = ctx._pill_day()
    who = display_name(s)
    s.world.tavern_treats[p.location] = (who, s.world.time)
    add_rumor(s, tavern_rules.TREAT_LINE.format(name=who, place=c.locations[p.location].name), p.location,
                    content=c, layer="local", named=not p.anonymous)
    ctx._shop_say("treat")
    return [tavern_rules.TREAT_DONE] + renown.gain(s, c, "fame", cfg.treat_fame)


def tavern_hide_problem(ctx: Game) -> str | None:
    p = ctx.state.player
    if p.hidden_until > ctx.state.world.time:
        return tavern_rules.HIDE_ALREADY.format(when=ctx.stamp(p.hidden_until))
    return None


def tavern_hide(ctx: Game) -> list[str]:
    s, c = ctx.state, ctx.content
    problem = tavern_hide_problem(ctx)
    if problem is not None:
        ctx._shop_after(problem, "hide")
        return [problem]
    if tavern_charge(ctx, c.config.tavern.hide_price) is None:
        return tavern_short(ctx, c.config.tavern.hide_price)
    s.player.hidden_until = s.world.time + DAY
    ctx._shop_say("hide")
    return [tavern_rules.HIDE_DONE]


def tavern_trace(ctx: Game) -> list[str]:
    s, c = ctx.state, ctx.content
    pending = [w for w in s.player.whispers if not (w.named or w.revealed)]
    if not pending:
        ctx._shop_say("nothing")
        return [tavern_rules.TRACE_NONE]
    if tavern_charge(ctx, c.config.tavern.trace_price) is None:
        return tavern_short(ctx, c.config.tavern.trace_price)
    others = {}
    last = pending[-1]
    other = ctx._load_kin(last.who)
    if other is not None:
        other.state.world = s.world
        others[name_key(last.who)] = other.state
    lines, _ = tavern_rules.trace_lines(s, c, others)
    tavern_rules.add_note(s, c, "trace", tavern_rules.TITLES["trace"], lines)
    ctx._shop_say("trace")
    return lines


# ── 買殺手（設計第六節）：雇（tavern_hit）、保鏢（tavern_guard）、殺手出手（tavern_hit_check，對方自己在城外做完一件事時）、
# 雇主收結果（deliver_hits，雇主自己同步時）。單子在季上（WorldState.tavern_hits），亂數用自己的種子，不動 Game.rng ──


def tavern_hit_problem(ctx: Game, target: str, tier: int) -> tuple[str | None, Game | None]:
    """雇不雇得了（拒絕的話, 對方那一份）：要先在酒肆查到過這個人（不然查無此人與默默無名讀得出差別）、不是自己、
    截殺的緊急開關開著（Config.raid.enabled）；同陣營也接（企劃者 2026-10-27「不應該限制玩家」，以前要有仇）；雙方都過了新手期、對方身上沒有別人的單、同一對人 hit_pair_hours 內沒雇過、季還在跑。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    if s.world.ended:
        return tavern_rules.HIT_ENDED, None
    if not 0 <= tier < len(cfg.hit_prices):
        return tavern_rules.HIT_BAD_TIER, None
    if not target or name_key(target) not in {name_key(n) for n in s.player.tavern_known} | tavern_wanted(ctx):
        return tavern_rules.HIT_NEED_KNOWN, None
    cid, other = tavern_find(ctx, target)
    if other is None:
        return tavern_rules.HIT_NEED_KNOWN, None
    them = other.state.player.name
    if name_key(them) == name_key(s.player.name):
        return tavern_rules.HIT_SELF, other
    if not c.config.raid.enabled:
        return tavern_rules.HIT_ENDED, other
    if roster.raid_newbie(s, c):
        return tavern_rules.HIT_NEWBIE_ME, other
    if roster.raid_newbie(other.state, c):
        return tavern_rules.HIT_NEWBIE_THEM.format(name=them), other
    if tavern_rules.active_hit(s.world, them, ctx.now) is not None:
        return tavern_rules.HIT_TAKEN.format(name=them), other
    recent = ctx.now - cfg.hit_pair_hours * 3600
    if any(name_key(h.client) == name_key(s.player.name) and name_key(h.target) == name_key(them) and h.placed_real > recent
           for h in s.world.tavern_hits):
        return tavern_rules.HIT_PAIR.format(name=them), other
    return None, other


def tavern_hit(ctx: Game, target: str, spec: str) -> list[str]:
    """雇殺手：spec 是「檔次」或「檔次:hush」（多付封口錢）。付了錢掛單；對方擲一次聽不聽得到風聲（不說是誰）。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    head, _, flag = str(spec or "").partition(":")
    tier = int(head) if head.strip().isdigit() else -1
    problem, other = tavern_hit_problem(ctx, target, tier)
    if problem is not None:
        ctx._shop_after(problem, "refused")
        return [problem]
    hush = flag == "hush"
    them = other.state.player.name
    w = s.world
    streak = tavern_rules.hit_streak(w, s.player.name, them, cfg.hit_fail_max)
    base = tavern_rules.hit_price_base(c, tier, streak) + (cfg.hush_price if hush else 0)
    price = tavern_charge(ctx, base)
    if price is None:
        return tavern_short(ctx, base)
    w.tavern_hit_seq += 1
    hit = TavernHit(id=w.tavern_hit_seq, client=s.player.name, target=them, tier=tier, price=price, place=s.player.location,
                    placed_real=ctx.now, until_real=ctx.now + cfg.hit_hours * 3600, hushed=hush, streak=streak)
    warn = cfg.hit_warn + 0.05 * renown.fame_tier(other.state, c)
    if tavern_rules.rng_for("酒肆殺手風聲", w.tavern_hit_seq, s.player.name, them, w.time).random() < warn:
        hit.warned = True
        note = Whisper(kind="hit", who=s.player.name, place=s.player.location, time=w.time,
                       hint=tavern_rules.side_hint(s, c), hushed=hush)
        tavern_rules.post_whisper(w, them, note)
        ctx.touched.add(them)
    w.tavern_hits.append(hit)
    name = tavern_rules.hit_tier_name(tier)
    lines = [tavern_rules.HIT_PLACED.format(name=them, tier=name, until=real_stamp(ctx, hit.until_real))]
    if streak:
        lines.append(tavern_rules.HIT_STREAK.format(name=them, n=streak, pct=round(cfg.hit_fail_price_step * streak * 100)))
    if hush:
        lines.append(tavern_rules.HIT_HUSHED)
    tavern_rules.add_note(s, c, "hit", f"{tavern_rules.TITLES['hit']}・{them}", lines)
    ctx._shop_say("asked")
    return lines


def real_stamp(ctx: Game, real: float) -> str:
    """現實秒換成玩家看得到的時刻（季曆的寫法）：照此刻的世界時間往後推。"""
    w = ctx.state.world
    return ctx.stamp(w.time + (real - ctx.now) * ctx.content.config.time_scale)


def tavern_guard_problem(ctx: Game) -> str | None:
    p = ctx.state.player
    if p.tavern_guard_until > ctx.now:
        return tavern_rules.GUARD_ALREADY.format(until=real_stamp(ctx, p.tavern_guard_until))
    return None


def tavern_guard(ctx: Game) -> list[str]:
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    problem = tavern_guard_problem(ctx)
    if problem is not None:
        ctx._shop_after(problem, "refused")
        return [problem]
    if tavern_charge(ctx, cfg.guard_price) is None:
        return tavern_short(ctx, cfg.guard_price)
    s.player.tavern_guard_until = ctx.now + cfg.guard_hours * 3600
    line = tavern_rules.GUARD_DONE.format(until=real_stamp(ctx, s.player.tavern_guard_until))
    tavern_rules.add_note(s, c, "guard", tavern_rules.TITLES["guard"], [line])
    ctx._shop_say("hide")
    return [line]


def tavern_hit_check(ctx: Game, away_from: float | None = None) -> list[str]:
    """自己（被盯上的人）剛做完一件事：有一張找你的單子、你人在城外、不在路上、不在決戰裡、沒剛被人截殺或設伏過、沒剛被殺手得手過
    （tavern_shield_until），殺手照打聽度擲一次找不找得到；找到了本人對本人打一場。到期的單子在這裡收（退款由雇主自己同步時領）。
    away_from 是同步時「上一次同步的現實秒」（下線那一段，企劃者 2026-10-27）：這一段跟單子的期限重疊、你下線那一刻站在城外，
    一樣擲一次（城鎮裡下線照舊安全）；在這一段裡到期的單子先擲再收。"""
    s, c = ctx.state, ctx.content
    w, me = s.world, s.player
    if not tavern_rules.on(c) or not w.tavern_hits:
        return []
    key = name_key(me.name)
    mine = [h for h in w.tavern_hits if not h.done and name_key(h.target) == key]
    if not mine:
        return []
    start = ctx.now if away_from is None else away_from
    live = [h for h in mine if h.until_real > start and h.placed_real < ctx.now]
    for h in mine:
        if h.until_real <= ctx.now:
            h.done, h.outcome = True, "過期"
    hit = next(iter(live), None)
    if hit is None or w.ended or me.journey is not None or tavern_rules.town(c, me.location) or roster.raid_newbie(s, c):
        return []
    if me.tavern_shield_until > ctx.now:
        return []
    battle = ctx._battle_now()  # 有攻城戰時是自己參戰的那一場（領地爭奪第二批）
    if battle is not None and me.name in battle.participants:
        return []
    shield = w.raided.get(key)
    if shield is not None and w.time - shield < c.config.raid.shield_seconds:
        return []
    rng = tavern_rules.rng_for("酒肆殺手", hit.id, me.name, w.time)
    reach = tavern_rules.hit_reach(c, hit.place, s, tavern_wanted_of(ctx, me.name))
    if rng.random() >= tavern_rules.find_chance(c, reach):
        return []
    hit.done = False  # 下線那一段裡到期的單子：上面先收成過期，擲中了照打
    return tavern_hit_fight(ctx, hit, rng, away=away_from is not None)


def tavern_wanted_of(ctx: Game, name: str) -> set[str]:
    """這個人身上有沒有通緝（名氣 +1）：有就回只含他名號鍵的集合。"""
    return {name_key(name)} & tavern_wanted(ctx)


def tavern_hit_fight(ctx: Game, hit, rng: random.Random, away: bool = False) -> list[str]:
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    w, me = s.world, s.player
    tier_name = tavern_rules.hit_tier_name(hit.tier)
    mine = ctx._spar_power(ctx, ctx)
    power = tavern_rules.hit_power_of(c, hit.tier, hit.streak)
    if me.tavern_guard_until > ctx.now:
        power *= cfg.guard_scale
    # 殺手照你自己的威力浮上來（同江湖水漲）：玉璽碎片的戰力不浮上去（改版），沒碎片時跟 mine 一樣
    killer = max(1.0, ctx._spar_power(ctx, ctx, seal=False) * power)
    result = encounter.resolve_encounter(mine, killer, rng)
    w.raided[name_key(me.name)] = w.time
    hit.done = True
    squad = Squad(id="assassin", name=tier_name, difficulty=killer)
    record = battlelog.new_record(s, c, ctx.world, squad, result, "assassin")
    record.ours = record.ours[:1]
    hp_lost: int | None = 0
    extra: list[str] = []
    if result.tier in team.WIN_TIERS:
        hit.outcome = "對方贏"
        found = math.floor(hit.price * cfg.hit_bounty_share)
        me.stats["silver"] = me.stats.get("silver", 0) + found
        record.silver = found
        story = tavern_rules.HIT_STORY_WON.format(tier=tier_name, n=found)
        record.changes += renown.gain(s, c, "fame", cfg.hit_win_fame)
        client = ctx._load_kin(hit.client)
        tier = renown.fame_tier(client.state, c) if client is not None else 0
        chance = (cfg.hit_reveal + 0.1 * tier) * (0.5 if hit.hushed else 1.0)
        if rng.random() < chance:
            extra.append(tavern_rules.HIT_REVEALED.format(who=hit.client))
            tavern_rules.remember(s, hit.client)
            hit.outcome = "對方贏・供出"
            add_rumor(s, tavern_rules.HIT_RUMOR.format(who=hit.client, name=me.name), hit.place, content=c, layer="local")
        else:
            extra.append(tavern_rules.HIT_SILENT)
    elif result.tier in team.DRAW_TIERS:
        hit.outcome = "平手"
        story = tavern_rules.HIT_STORY_DRAW.format(tier=tier_name)
    else:
        hit.outcome = "殺手贏"
        purse = me.stats.get("silver", 0)
        lost = min(cfg.hit_silver_cap, math.ceil(purse * cfg.hit_silver_share)) if purse > 0 else 0
        me.stats["silver"] = purse - lost
        record.silver = -lost
        con = team.con_of(s, c, ctx.world, PLAYER)
        now_hp, _ = team.member_neili(c, me.member, con, season=s.world)
        me.member.neili = min(now_hp, 1.0)  # 只剩一口氣（企劃者 2026-10-27）：防具、化勁都不擋，逼人去醫館
        hp_lost = max(0, round(now_hp - me.member.neili))
        record.changes.append(tavern_rules.HIT_HP_LEFT)
        me.tavern_shield_until = ctx.now + cfg.hit_shield_hours * 3600
        story = tavern_rules.HIT_STORY_LOST.format(tier=tier_name)
    if away:
        story = tavern_rules.HIT_AWAY.format(place=c.locations[me.location].name) + story
    record.notes.append(story)
    record.notes += extra
    annals.note(s, c, annals.FIGHT, story, 2)
    ctx._play_rounds(record, squad, result.tier, hp_lost)
    line = ctx._file_battle(record)
    msgs = [line, story, *extra, *battlelog.gains_list(record), *ctx._last_wear]
    ctx._write(tavern_rules.HIT_STRUCK, msgs, tag=battlelog.outcome_text(record))
    ctx.touched.add(hit.client)
    return msgs


def deliver_hits(ctx: Game) -> None:
    """雇主自己同步時：收自己雇的單子的結果（得手、失手、平手、到期退一半），一張一句、一則紀錄；得手的記惡名。"""
    s, c, cfg = ctx.state, ctx.content, ctx.content.config.tavern
    w, me = s.world, s.player
    if not w.tavern_hits:
        return
    key = name_key(me.name)
    lines: list[str] = []
    for h in w.tavern_hits:
        if name_key(h.client) != key or h.refunded:
            continue
        if not h.done and h.until_real <= ctx.now:
            h.done, h.outcome = True, "過期"
        if not h.done:
            continue
        h.refunded = True
        tier = tavern_rules.hit_tier_name(h.tier)
        if h.outcome == "過期":
            back = int(h.price * cfg.refund_share)
            me.stats["silver"] = me.stats.get("silver", 0) + back
            lines.append(tavern_rules.HIT_REFUND.format(name=h.target, tier=tier, n=back))
        elif h.outcome == "殺手贏":
            lines.append(tavern_rules.HIT_WON_CLIENT.format(tier=tier, name=h.target))
            lines += renown.gain(s, c, "evil", cfg.hit_evil)
        elif h.outcome.startswith("對方贏"):
            lines.append(tavern_rules.HIT_LOST_CLIENT.format(tier=tier, name=h.target))
            if h.outcome.endswith("供出"):
                lines.append(tavern_rules.HIT_LOST_NAMED)
        else:
            lines.append(tavern_rules.HIT_DRAW_CLIENT.format(tier=tier, name=h.target))
    if lines:
        ctx._write(tavern_rules.HIT_TITLE, lines)
        ctx._save_season()


# ── 問酒家（設計第八節）：A tavern_ask_request（只讀）→ B 鎖外 tavern.ask_write → C tavern_ask_reply（重驗同一間、同一句，再過一次 ask_clean）──


def tavern_ask_facts(ctx: Game, question: str = "") -> tuple[tuple[str, ...], tuple[str, ...]]:
    """問酒家的事實清單與問到的是哪幾類：先照問句找（tavern_ask.topics：名號、地名、素材、武學、店面、玩法、季勢；問句裡的玩家名號
    從存檔載入），再接原本那幾條（這一區的局勢、最近的傳聞、這裡的出產、座上客、你自己）。A、C 兩段各算一次，同一句算出來一樣。"""
    s, c = ctx.state, ctx.content
    p = s.player
    players: dict[str, GameState] = {}
    if hasattr(ctx.world, "db") and question:
        for name in tavern_ask.name_hits(question, CharacterStore(ctx.world.db).names()):
            other = ctx._load_kin(name)
            if other is not None:
                players[other.state.player.name] = other.state
    topic, kinds = tavern_ask.topics(s, c, question, players, tavern_wanted(ctx))
    extra = []
    guests = [o.player.name for o in social.here(ctx)][:6]
    if guests:
        extra.append(f"此刻也在{c.locations[p.location].name}的江湖人：{'、'.join(guests)}。")
    side = social.side(s, c)
    extra.append(f"問話的客官是{side}，名號{p.name}，此刻在{c.locations[p.location].name}。")
    base = [f for f in tavern_rules.ask_facts(s, c, extra) if f not in topic]
    return tuple(topic + base), tuple(kinds)


def tavern_chatter_request(ctx: Game) -> tavern_rules.ChatterRequest | None:
    """A 段（鎖內、只讀）：酒肆開著、這一間的閒談該換了，就開一張單（server.write_chatter 在背景請模型寫）。"""
    s, c = ctx.state, ctx.content
    loc = s.player.location
    if not tavern_open(ctx) or not tavern_rules.chatter_due(s.world, c, loc):
        return None
    return tavern_rules.ChatterRequest(place=loc, sign=tavern_rules.sign(s, c), asked_at=s.world.time,
                                       facts=tavern_rules.chatter_facts(s, c, loc))


def apply_tavern_chatter(ctx: Game, request: tavern_rules.ChatterRequest, lines: list[str]) -> bool:
    """C 段：這一間還是該換（沒有別人先寫好），就記下這一段；寫不出來記空清單，這一陣子照固定句、不再叫模型。記了回 True。"""
    s, c = ctx.state, ctx.content
    entry = s.world.tavern_chatter.get(request.place)
    if entry is not None and entry[0] >= request.asked_at and not tavern_rules.chatter_due(s.world, c, request.place):
        return False
    s.world.tavern_chatter[request.place] = (s.world.time, list(lines))
    ctx._save_season()
    return bool(lines)


def tavern_ask_request(ctx: Game, text: str) -> tavern_rules.AskRequest | list[str]:
    """A 段（鎖內、只讀）：酒肆開著、問句合格、付得起，就開一張單（問到秘密的單子標 secret，B 段不叫模型）；不然回那一句拒絕。"""
    s, c = ctx.state, ctx.content
    if not tavern_open(ctx):
        return [equipment.NOT_NOW]
    q = str(text or "").strip()
    problem = tavern_rules.ask_problem(c, q)
    if problem is None:
        problem = tavern_rules.pay_problem(s, tavern_price(ctx, c.config.tavern.ask_price))
    if problem is not None:
        return [problem]
    secret = tavern_rules.secret_asked(q)
    facts, kinds = ((), ()) if secret else tavern_ask_facts(ctx, q)
    return tavern_rules.AskRequest(name=s.player.name, place=s.player.location, sign=tavern_rules.sign(s, c), question=q,
                                   facts=facts, secret=secret, kinds=kinds)


def tavern_ask_reply(ctx: Game, text: str, reply: str | None, request: tavern_rules.AskRequest | None = None) -> list[str]:
    """C 段：重驗（酒肆還開著、還在同一間、同一句），回話再過一次 ask_clean（照此刻的清單），然後收錢寫紀錄。"""
    if not tavern_open(ctx):
        return ctx._log([equipment.NOT_NOW])
    q = str(text or "").strip()
    ok = request is not None and request.place == ctx.state.player.location and request.question == q
    ctx._tavern_reply = reply if ok else None
    try:
        return ctx._log(tavern_run(ctx, "ask", text=q))
    finally:
        ctx._tavern_reply = None


def tavern_ask_once(ctx: Game, text: str) -> list[str]:
    s, c = ctx.state, ctx.content
    cfg = c.config.tavern
    q = text.strip()
    problem = tavern_rules.ask_problem(c, q)
    if problem is not None:
        ctx._shop_after(problem, "refused")
        return [problem]
    if tavern_rules.secret_asked(q):
        half = max(0, cfg.ask_price // 2)
        if tavern_charge(ctx, half) is None:
            return tavern_short(ctx, half)
        lines = [tavern_rules.ASK_YOU.format(q=q), tavern_rules.ASK_SECRET]
        tavern_rules.add_note(s, c, "ask", tavern_rules.ASK_TITLE, lines)
        ctx._shop_say("nothing")
        return lines
    if tavern_charge(ctx, cfg.ask_price) is None:
        return tavern_short(ctx, cfg.ask_price)
    facts, kinds = tavern_ask_facts(ctx, q)
    req = tavern_rules.AskRequest(name=s.player.name, place=s.player.location, sign=tavern_rules.sign(s, c), question=q,
                                  facts=facts, kinds=kinds)
    reply = getattr(ctx, "_tavern_reply", None)  # B 段寫好的（tavern_ask 放的）；直接呼叫沒有 B 段，當叫不動
    reply = tavern_rules.ask_clean(reply, req) if reply else None
    if reply is None:
        tavern_rules.pay(s, -tavern_price(ctx, cfg.ask_price))  # 叫不動模型：退全額
        ctx._shop_say("nothing")
        return [tavern_rules.ASK_BUSY]
    lines = [tavern_rules.ASK_YOU.format(q=q), tavern_rules.ASK_HIM.format(a=reply)]
    if tavern_rules.unsure(reply):  # 酒家說不上來：退一半，指一條路（企劃者 2026-10-27）
        refund = tavern_price(ctx, cfg.ask_price) // 2
        tavern_rules.pay(s, -refund)
        lines.append(tavern_rules.ASK_UNSURE.format(refund=refund, tip=tavern_ask.pointer(list(kinds))))
    tavern_rules.add_note(s, c, "ask", tavern_rules.ASK_TITLE, lines)
    ctx._shop_say("asked")
    return lines


def deliver_whispers(ctx: Game) -> None:
    """酒肆的風聲（有人打聽你）：季上那幾則搬到身上，寫一則「風聲」紀錄。"""
    lines = tavern_rules.collect_whispers(ctx.state, ctx.content)
    if lines:
        ctx._write(tavern_rules.WHISPER_TITLE, lines)
        ctx._save_season()


def tavern_view(ctx: Game) -> dict:
    """酒肆那一頁（Game.shop_view 在酒肆開著時給）：招牌、銀兩、酒家那一句、出店、價錢、剛問到的、座上客、鄰桌閒談、題壁、
    請酒的人、記下的名號、素材清單、收到的風聲。只讀。"""
    s, c = ctx.state, ctx.content
    p, cfg = s.player, c.config.tavern
    loc = p.location
    guests = [o.player.name for o in social.here(ctx)]
    treat = tavern_rules.treat_shown(s.world, c, loc)
    prices = {k: tavern_price(ctx, getattr(cfg, f"{k}_price")) for k in ("news", "seek", "ties", "wall", "treat", "hide", "trace", "ask")}
    mats = []
    for m in sorted(c.materials.values(), key=lambda m: (m.tier, shopview.attribute_rank(m.attribute), m.id)):
        base = cfg.material_prices.get(m.tier, max(cfg.material_prices.values()))
        mats.append({"id": m.id, "name": m.name, "tier": m.tier, "attribute": m.attribute, "price": tavern_price(ctx, base)})
    hour = int(s.world.time // HOUR)
    me = name_key(p.name)
    hits = {
        "tiers": [{"tier": i, "name": tavern_rules.hit_tier_name(i), "price": tavern_price(ctx, base)}
                  for i, base in enumerate(cfg.hit_prices)],
        "hush": tavern_price(ctx, cfg.hush_price),
        "guard": tavern_price(ctx, cfg.guard_price),
        "guard_problem": tavern_guard_problem(ctx),
        "mine": [tavern_rules.HIT_ACTIVE.format(name=h.target, tier=tavern_rules.hit_tier_name(h.tier), until=real_stamp(ctx, h.until_real))
                 for h in s.world.tavern_hits if not h.done and name_key(h.client) == me and h.until_real > ctx.now],
        "ended": bool(s.world.ended),
        "streaks": [tavern_rules.HIT_STREAK.format(name=n, n=k, pct=round(cfg.hit_fail_price_step * k * 100))
                    for n in p.tavern_known if (k := tavern_rules.hit_streak(s.world, p.name, n, cfg.hit_fail_max))],
    }
    return {
        "shop": "tavern",
        "hits": hits,
        "sign": tavern_rules.sign(s, c),
        "silver": p.stats.get("silver", 0),
        "line": shopview.line_text(s, c, "tavern"),
        "back": tavern_rules.BACK_ID,
        "prices": prices,
        "problems": {"treat": tavern_treat_problem(ctx), "hide": tavern_hide_problem(ctx)},
        "notes": [{"kind": n.kind, "title": n.title, "lines": list(n.lines), "when": ctx.stamp(n.time)}
                  for n in reversed(p.tavern_notes)],
        "guests": guests[:6],
        "more_guests": max(0, len(guests) - 6),
        "treat": tavern_rules.TREAT_SEEN.format(name=treat) if treat else "",
        "chatter": [{"who": who, "said": said} for who, said in tavern_rules.chatter(c, loc, hour, s.world)],
        "walls": [{"who": w.who, "text": w.text, "when": ctx.stamp(w.time)} for w in reversed(s.world.tavern_walls.get(loc, []))],
        "wall_chars": cfg.wall_chars,
        "ask_chars": cfg.ask_chars,
        "watch": {"price": tavern_price(ctx, int(round(cfg.seek_price * cfg.watch_share))),
                  "mine": [tavern_rules.WATCH_ACTIVE.format(name=w.target, until=real_stamp(ctx, w.until_real))
                           for w in p.tavern_watches if w.until_real > ctx.now]},
        "known": list(reversed(p.tavern_known)),
        "materials": mats,
        "whispers": tavern_rules.whisper_view(c, s),
        "hidden": tavern_rules.HIDE_ALREADY.format(when=ctx.stamp(p.hidden_until)) if p.hidden_until > s.world.time else "",
        "board": tavern_rules.BOARD_ID if bounties.board_here(s, c) and bounties.visible(s, c) else "",
    }
