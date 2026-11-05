"""列傳包的動作（全部拆包第 29 批：原本 Game 上的 20 個方法，計畫 docs/superpowers/plans/2026-11-04-列傳包-第1批.md 1.1）。
Game 留 9 個一行委派（換季的 _zhuan_past、同步的 _zhuan_tick、_everyday_options 的 _zhuan_options、server 與測試叫的 annals_view、biography_entry、
biography_request、write_biography、biography_view、share_biography）；其餘 11 個只在包內互相叫，直接拿掉。
寫傳的三段式：A biography_request（request，鎖內只讀）→ B server.write_zhuan（鎖外叫模型，留在殼；鎖外工作的掛鉤是總表第 69 批）→
C write_biography（write，鎖內重驗：request 再問一次，對不上就不存）。
第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用 tianxia/core/services.py 那張清單上的。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia import gender, journal
from tianxia.core.option import Option
from tianxia.rules import jianfa
from tianxia.state import GameState, JournalEntry, WorldState

from . import biography, zhuan_end
from . import standing as standing_mod  # 行狀的查詢那一半（第 29 批之二）

if TYPE_CHECKING:
    from tianxia.engine import Game


def profile(ctx: Game, old: GameState, season: WorldState | None) -> dict:
    """換季存行狀時的身家（_reset_player_for_new_season；Game._zhuan_profile 一行委派過來，核心不能 import 包）。"""
    return standing_mod.profile(old, ctx.content, season=season)


def past(ctx: Game, old: GameState) -> WorldState | None:
    """換季那一刻（_reset_player_for_new_season）：上一季開著列傳為終點（zhuan_end）就回那一季（WorldStateStore.past_season），
    先替這個人補上收季之後還沒記的季末論功與〈天下形勢〉（同步時記的那兩種，standing_mod.tier_note、xingshi_notes），身家照它多論功的那幾樣；
    關著（設定沒開就不讀資料庫）是 None，一個字都不變。old 是上一季的存檔，馬上就丟：old.world 換成上一季那一份才記得到正確的時刻。"""
    cfg = ctx.content.config.jianfa
    if not (cfg.enabled and cfg.zhuan_end):
        return None
    last = ctx.world.past_season(old.player.season_number)
    if last is None or not jianfa(ctx.content, last, "zhuan_end"):
        return None
    old.world = last
    standing_mod.xingshi_notes(old, ctx.content, last)
    standing_mod.tier_note(old, ctx.content, last)
    return last


def tick(ctx: Game) -> None:
    """列傳為終點（減法季批 7b-1）：同步時替自己記行狀——〈天下形勢〉上一次看到之後寫到名號的那幾篇（standing_mod.xingshi_notes），
    季收了之後的季末論功（standing_mod.tier_note）。只改自己的存檔，不存季。關著（zhuan_end）什麼都不做。"""
    s, c = ctx.state, ctx.content
    if not jianfa(c, s.world, "zhuan_end"):
        return
    standing_mod.xingshi_notes(s, c, s.world)
    if s.world.ended:
        standing_mod.tier_note(s, c, s.world)


def annals_view(ctx: Game) -> dict:
    """見聞的「行狀」頁（玩家傳第一批）：這一季至今記下的事，照時間先後；開關關著時 on 是 False、rows 是空的。
    books 是歷季列傳（第二批）：存著的每一季（這一季收了、還沒換季的也算），新的在前。"""
    on = annals.on(ctx.content)
    return {
        "on": on, "name": ctx.state.player.name, "rows": standing_mod.rows(ctx.state, ctx.content) if on else [],
        "books": biography_list(ctx) if on else [],
    }


# ── 玩家傳第二批：季末寫成《某某傳》、公開分享 ──


def season_closed(ctx: Game) -> bool:
    """這一季收了（休季）：這一季的傳寫得了。"""
    return ctx.world.season_phase() == "resting"


def entry(ctx: Game) -> dict | None:
    """休季時江湖頁最上面的「讀你的傳」（這一季的那一篇）：季收了、有行狀或已經存了那一篇才有；假人、開關關著、季還在跑是 None。
    輪詢每次都問：季還在跑時不讀資料庫。列傳為終點開著（減法季批 7b）多 tier、illustration、seal（extra）。"""
    p = ctx.state.player
    if not annals.on(ctx.content) or p.bot is not None or not ctx.state.world.ended:
        return None
    if not p.annals and ctx.world.biography(p.season_number, p.name) is None:
        return None
    return {"season": p.season_number, "title": biography.title(p.name), **extra(ctx, p.season_number)}


# ── 列傳為終點（減法季批 7b）：休季用票、列傳多畫的那幾樣 ──


def season_of(ctx: Game, season: int) -> WorldState | None:
    """那一季的 WorldState（這一季照手上的，以前的照 past_season）；沒有是 None。"""
    p = ctx.state.player
    return ctx.state.world if season == p.season_number else ctx.world.past_season(season)


def purchases(ctx: Game) -> list:
    return ctx.wallet.purchases()


def extra(ctx: Game, season: int) -> dict:
    """列傳多畫的那幾樣（zhuan_end.extras：季末論功、插畫的圖庫鍵、紀念印的字）；那一季沒開列傳為終點是空的（一個鍵都不多）。
    這一季的身家照角色身上的，以前的季照存起來的那一份。評曰的名單照寫成的那一篇傳列（FB-847，zhuan_end.extras 的 text）：
    還沒寫成是 None（預告要寫的人）。"""
    p = ctx.state.player
    world = season_of(ctx, season)
    if world is None or not zhuan_end.on(ctx.content, world):
        return {}
    row = ctx.world.biography(season, p.name)
    if season == p.season_number:
        profile = standing_mod.profile(ctx.state, ctx.content, season=world)
    else:
        profile = row["profile"] if row is not None else {}
    text = row["text"] if row is not None else None
    return zhuan_end.extras(ctx.content, season, profile, zhuan_end.season_tickets(purchases(ctx), season), text)


def options(ctx: Game) -> list[Option]:
    """休季用列傳的票（減法季批 7b；設計第九章）：列傳為終點開著、季收了，手上有沒用的票才有那一顆。插畫：投靠了劇本裡的陣營、
    這一季還沒用過、不是第一階（第一階白送）；紀念印：這一季還沒蓋；親筆評曰：情誼 40～69、這一季還沒替你寫的人物一位一顆。"""
    s, c = ctx.state, ctx.content
    if not s.world.ended or not zhuan_end.on(c, s.world):
        return []
    bought = purchases(ctx)
    if not bought:
        return []
    n = s.player.season_number
    used = zhuan_end.season_tickets(bought, n)
    standing = standing_mod.standing(s, c, s.world)
    out = []
    # 票綁買的那一季（FB-845）：只數這一季買的，之前的季沒用掉的不再冒出用票的鈕
    if zhuan_end.unused(bought, zhuan_end.ART, n) and standing.get("illustration") and not used["art"] and standing.get("tier") != 1:
        out.append(Option(id=zhuan_end.PICK_ART, label=zhuan_end.ART_BUTTON))
    if zhuan_end.unused(bought, zhuan_end.SEAL_TICKET, n) and not used["seal"]:
        out.append(Option(id=zhuan_end.SEAL, label=zhuan_end.SEAL_BUTTON.format(seal=zhuan_end.seal_text(c, n, standing))))
    if zhuan_end.unused(bought, zhuan_end.QUOTE_TICKET, n):
        taken = set(used["quotes"]) | set(verdict_taken(standing))
        out += [Option(id=f"{zhuan_end.QUOTE}{cid}", label=zhuan_end.QUOTE_BUTTON.format(name=c.characters[cid].name, value=value))
                for cid, value in zhuan_end.quote_figures(s, c, taken)]
    return out


def verdict_taken(standing: dict) -> list[str]:
    """這一季已經白送評曰的人物（standing_mod.standing 的 verdicts：第一二階的主將或家主、情誼 70 以上的；親筆評曰不再列他們）。"""
    return [w["fid"] for w in standing.get("verdicts", [])]


def act(ctx: Game, option_id: str) -> list[str]:
    """用掉一張列傳的票（options 驗過有票、按得下去）：那一列購買記 used、season（親筆評曰另記 fid），寫一則「列傳」紀錄。"""
    s, c = ctx.state, ctx.content
    n = s.player.season_number
    now = ctx.pill_now()
    if option_id == zhuan_end.PICK_ART:
        ctx.wallet.consume(zhuan_end.ART, bought_in=n, at=now, season=n, art=zhuan_end.illustration_for(s, c, s.world))
        lines = [zhuan_end.ART_DONE]
    elif option_id == zhuan_end.SEAL:
        ctx.wallet.consume(zhuan_end.SEAL_TICKET, bought_in=n, at=now, season=n)
        lines = [zhuan_end.SEAL_DONE.format(seal=zhuan_end.seal_text(c, n, standing_mod.standing(s, c, s.world)))]
    else:
        cid = option_id.removeprefix(zhuan_end.QUOTE)
        ctx.wallet.consume(zhuan_end.QUOTE_TICKET, bought_in=n, at=now, season=n, fid=cid)
        lines = [zhuan_end.QUOTE_DONE.format(name=c.characters[cid].name)]
        row = ctx.world.biography(n, s.player.name)
        if row is not None and row["text"] is not None:
            lines.append(zhuan_end.QUOTE_LATER)
    journal.add_entry(s, JournalEntry(time=s.world.time, title=zhuan_end.TITLE, lines=lines))
    return lines


def biography_list(ctx: Game) -> list[dict]:
    """歷季列傳：每一季一列（季別、篇名、寫成了沒、公開了沒）。這一季收了、行狀還在角色身上（還沒換季）的那一季排第一。"""
    p = ctx.state.player
    rows = {b["season"]: b for b in ctx.world.biographies_of(p.name)}
    out = []
    if season_closed(ctx) and p.annals and p.season_number not in rows:
        out.append({"season": p.season_number, "title": biography.title(p.name), "written": False, "public": False})
    out += [
        {"season": n, "title": biography.title(b["name"]), "written": b["text"] is not None, "public": b["public"]}
        for n, b in sorted(rows.items(), reverse=True)
    ]
    return out


def request(ctx: Game, season: int, rewrite: bool = False) -> biography.BiographyRequest | None:
    """A 段（鎖內、只讀）：那一季那一篇要寫（或重寫）的單子。寫不了回 None：開關關著、假人、這一季還沒收、那一季沒有行狀、
    已經寫過而不是重寫、重寫的次數用完了。這一季收了、還沒換季時，行狀與身家照角色身上的；以前的季照存起來的。"""
    c, p = ctx.content, ctx.state.player
    if not annals.on(c) or p.bot is not None:
        return None
    row = ctx.world.biography(season, p.name)
    if row is None:
        if rewrite or season != p.season_number or not season_closed(ctx) or not p.annals:
            return None
        entries = tuple(e.model_dump() for e in sorted(p.annals, key=lambda e: e.time))
        profile = standing_mod.profile(ctx.state, c, season=ctx.state.world)
    else:
        if season == p.season_number and not season_closed(ctx):
            return None
        entries = tuple(sorted(row["annals"], key=lambda e: e.get("time", 0.0)))
        profile = row["profile"]
        if season == p.season_number and p.annals and row["text"] is None:  # 這一季還沒寫成：照角色身上最新的
            entries = tuple(e.model_dump() for e in sorted(p.annals, key=lambda e: e.time))
            profile = standing_mod.profile(ctx.state, c, season=ctx.state.world)
        written = row["text"] is not None
        if written != rewrite or (rewrite and row["rewrites"] >= rewrites_allowed(ctx)):
            return None
    if not entries:
        return None
    chronicle = dict(ctx.world.chronicle_before(season + 1)).get(season, [])
    era = [r.text for r in chronicle][: biography.ERA_MAX]
    return biography.BiographyRequest(
        season=season, name=p.name, scenario=c.scenario.name, era_note=c.scenario.era_note, profile=profile,
        annals=entries, era=tuple(era), rewrite=rewrite, sex=gender.of(p), verdicts=verdict_jobs(ctx, season, entries, profile),
    )


def verdict_jobs(ctx: Game, season: int, entries: tuple[dict, ...], profile: dict) -> tuple:
    """人物評曰的單子（減法季批 7b-2，zhuan_end.verdict_request）：身家裡白送的寫手（第一二階的主將或家主、情誼 70 以上的），
    接這一季用了親筆評曰請的那幾位。那一季沒開列傳為終點是空的。"""
    c, p = ctx.content, ctx.state.player
    world = season_of(ctx, season)
    if world is None or not zhuan_end.on(c, world):
        return ()
    free = [zhuan_end.Writer(w["fid"], w["reason"]) for w in profile.get("verdicts", [])]
    bought = zhuan_end.season_tickets(purchases(ctx), season)["quotes"]
    writers = zhuan_end.with_bought(free, bought, c)
    fixed = zhuan_end.fixed_verdicts(c, writers, p.name, season)  # 整篇一起挑固定句：模型叫不動時兩位寫手也不會一字不差（FB-848）
    return tuple(zhuan_end.verdict_request(c, w, p.name, gender.of(p), entries, profile, season, fixed=fixed[w.fid])
                 for w in writers)


def write(
    ctx: Game, req: biography.BiographyRequest, text: str | None, now: float, verdicts: dict[str, str] | None = None,
) -> bool:
    """C 段（鎖內）：重驗單子（同一季、同一份行狀、還寫得了），存進 biographies。text 是 B 段模型寫好、清過的全文；None 就照規則拼。
    這一季的先把行狀與身家存起來（換季時存的是同一份；之後再來的決戰照 add_saved_annal 補）。存了回 True。
    列傳為終點（減法季批 7b-2）：單子上的每一位評曰寫手接一段「評曰：」（verdicts 是 B 段寫好的，人物 id → 一句；沒寫成照固定句）。"""
    current = request(ctx, req.season, req.rewrite)
    if current is None or current.annals != req.annals:
        return False
    p = ctx.state.player
    if req.season == p.season_number and p.annals:
        ctx.world.save_annals(req.season, p.name, list(req.annals), dict(req.profile))
    by = biography.MODEL if text else biography.RULE
    row = ctx.world.biography(req.season, p.name) if req.rewrite else None
    body = text or biography.rule_text(req)
    for job in req.verdicts:  # 人物評曰（批 7b-2）：一位一段，接在正文（含史官的評曰）後面
        body += "\n\n" + zhuan_end.apply_verdict(job, (verdicts or {}).get(job.fid, ""))
    stored = ctx.world.store_biography(req.season, p.name, body, by, now, req.rewrite)
    if stored and row is not None and row["rewrites"] >= ctx.content.config.biography.rewrites:
        use_rewrite_token(ctx, now)  # 白送的重寫用完了，這一次是萬寶閣買的「重修列傳」
    return stored


def rewrite_tokens(ctx: Game) -> list[int]:
    """萬寶閣「重修列傳」還沒用掉的那幾筆購買（錢包服務的 zhuan_rewrite 票）；商城關著是空的。"""
    return ctx.wallet.tokens("zhuan_rewrite")


def rewrites_allowed(ctx: Game) -> int:
    """一篇傳能重寫幾次：Config.biography.rewrites 加上手上還沒用掉的「重修列傳」（Joy 2026-10-21 定案：200 元寶、一季兩次）。"""
    return ctx.content.config.biography.rewrites + len(rewrite_tokens(ctx))


def use_rewrite_token(ctx: Game, now: float) -> None:
    ctx.wallet.consume("zhuan_rewrite", at=now)


def view(ctx: Game, season: int) -> dict | None:
    """修練之外的一本書（網頁的「讀你的傳」）：篇名、段落、誰寫的、公開了沒、分享代碼、還能不能重寫、還沒寫成時寫不寫得了。
    那一季沒有（沒有行狀、還沒收季）回 None。"""
    p = ctx.state.player
    row = ctx.world.biography(season, p.name)
    if row is None or row["text"] is None:
        ready = request(ctx, season) is not None
        if row is None and not ready:
            return None
        return {
            "season": season, "title": biography.title(p.name), "written": False, "can_write": ready, "paragraphs": [],
            "scenario": ctx.content.scenario.name, **extra(ctx, season),  # 列傳為終點（批 7b）：關著一個鍵都不多
        }
    return {
        "season": season, "title": biography.title(row["name"]), "written": True, "paragraphs": row["text"].split("\n\n"),
        "by": row["written_by"], "public": row["public"], "code": row["share_code"] if row["public"] else None,
        "can_rewrite": row["rewrites"] < rewrites_allowed(ctx), "scenario": ctx.content.scenario.name,
        **extra(ctx, season),
    }


def share(ctx: Game, season: int, public: bool, code: str) -> str | None:
    """公開或收回那一季的傳（寫成了才行）；回傳分享代碼（收回時也回，網頁不用它）。code 是伺服器產生的亂碼，已經有代碼就沿用。"""
    if not annals.on(ctx.content) or ctx.state.player.bot is not None:
        return None
    return ctx.world.share_biography(season, ctx.state.player.name, public, code)


def choose_unlisted(ctx: Game, option_id: str) -> list[str] | None:
    """休季用列傳的票（減法季批 7b；原本 Game.choose 在 choose_unlisted 之後、查選單之前那一行）：前綴 zhuan:、選單上有而且亮著才接，
    不走行動那一串（季收了，不推大勢、不存季）；不是就回 None，核心照舊查選單。先看前綴再叫 options（不是 zhuan: 的 id 不多叫一次選單）。"""
    if option_id.startswith(zhuan_end.PREFIX) and any(o.id == option_id and o.enabled for o in ctx.options(odds=False)):
        return ctx._log(act(ctx, option_id))
    return None
