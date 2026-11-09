"""江湖頁與店面的畫面資料（核心本體；第二輪第 81 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第81批.md，導覽 docs/guide/核心與存檔.md）。

原本是 Game 上的 26 個方法與模組層的 _timeline、BULLETIN_MAX（第一階 ctx 就是 Game，開發規範手冊 3.3）；Game 留 21 個一行委派（server、測試、包在叫），
_bulletin_events、_news_on_cards、_chip、_now_entry、_now_start 外面沒人叫，不留。模組裡互相叫直接叫函式（沒有一個被測試換掉，量過）；留在 Game 上的一律經 ctx，測試換 Game 上的照樣打得到。
要傳 callable 的：ctx.stamp、ctx._day_stamp（有委派）；_chip 沒有委派，functools.partial(_chip, ctx)（journal.ChipFn 都是 chip(change, seed) 位置參數）。

- 行動列底下那幾行：action_notes
- 店面：_shop_say、_shop_after、_shop_open、_shop_live、shop_view（第 93 批起問包：features.shop_page，一間店只有一包認）。_shop_open 讀 OPEN_CORE：engine._MENU_CORE["open"] 指到它（核心不 import engine），鍵不變
- 公告與結算卡：bulletin、_bulletin_events、_news_on_cards、season_result
- 三方卡、本週卡的分鐘：place_minutes
- 見聞與江湖史：trends_text、rumors_text、rumor_layers、chronicle_text、_timeline
- 江湖紀錄與「剛剛」：_day_stamp、_chip、latest_entry_html、journal_top_html、now_entry_html、_now_entry、now_front、journal_html、_now_start、shows_battle_card、battle_extra_html

名字的綁法照 engine：engine 拿名字的（rules 的 season_one、audible……）這裡也拿名字，engine 叫模組屬性的（journal.、timetable.……）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣。
engine 在 `from .core.event_check import …` 之後才 import 這一份（這裡 import 的模組那時都已經載入，載入順序不變）。

改這一份要跑的測試：scripts/test_for.py（CORE_SERVICES：這個檔的底 jianghu、shop、shop2、journal、rumor、front，加改到的函式那一群）；
same_behavior 所有軌（/api/main 逐位元組）：店面七間走 stack，結局卡與往季江湖史走 allegiance、battle，now_front 有值走 growth（計畫第五節）。
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any

from .. import atlas, battlelog, calendar, journal, mounts, rumor_view, timetable
from .. import prologue as prologue_rules
from ..rules import (
    HUANGJIN, audible, ears_of, front_chip, front_ids, is_revealed, season_one, trend_name, trend_shown, trend_value,
)
from . import arena_ranks, seal_base, shop_base
from . import features as features_core

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）
    from ..state import JournalEntry, Rumor

BULLETIN_MAX = 3  # 江湖頁那排小標「大事」點開的面板最多放這一週的幾則大事（計畫 T2；以前是公告卡）
# 店面開著沒的「核心代叫」那一格：engine._MENU_CORE["open"] 指到這裡（核心不 import engine；_shop_open 讀它）
OPEN_CORE: dict[str, Callable[..., Any]] = {"shops": lambda ctx: features_core.shop_open(ctx)}  # 店面登記的店（坐在店裡、這裡也還開著）


def action_notes(ctx: Game, option_ids: Iterable[str]) -> dict[str, str]:
    """江湖頁行動列底下那幾行（explain-1）：選單上的探索、遊歷、交友、求見這一下會怎樣，句子在 howto，事實照引擎的規則：
    探索的比重是擲骰用的那一份（_explore_weights），遊歷照這裡的對手與操練（出陣包 train_actions.train_line，經 act 子動詞的 Verb.note），交友照會不會直接開口談話
    （_socialize_figure）與這裡有沒有交友事件。只給 option_ids 裡有的。序章裡是空的：探索、遊歷照那一步寫好的走（草廬四景、
    斷眉），師父自己會說。只讀，不擲骰。"""
    s, c = ctx.state, ctx.content
    if prologue_rules.active(s, c):
        return {}
    ids = set(option_ids)
    loc = c.locations[s.player.location]
    notes: dict[str, str] = {}
    # 探索那一行（act 子動詞的主人，接縫掛鉤，第 11 批）：探索包——減法季探索一顆開著時寫這一處多半給什麼（比重照擲骰用的那一份）
    if "act:explore" in ids:
        explore_note = features_core.act_note(ctx, "explore", loc)
        if explore_note is not None:
            notes["act:explore"] = explore_note
    if "act:train" in ids:  # 出陣那一行（act 子動詞的主人，接縫掛鉤，第 11 批）：出陣包——約戰開著寫約戰那一句、出陣開著寫出陣那一行；都不是寫舊遊歷那一行（第 17 批收進包）
        train_note = features_core.act_note(ctx, "train", loc)
        if train_note is not None:
            notes["act:train"] = train_note
    for got in features_core.menu_run("notes", {}, ctx, ids, loc):  # 交友、求見那幾行（交友求見包，core_seams）；鍵的順序算行為
        notes.update(got)
    return notes


def _shop_say(ctx: Game, key: str, problem: str | None = None) -> None:
    """店面上掌櫃那一句（店面獨立介面設計 1.4、6.1）：記下店裡最後一件事的情況鍵、挑句子的種子（這一刻的季的時間），與被拒的那一句
    撐到什麼時候（shop_base.hold_for，FB-192：problem 是被拒的原因，錢不夠那一句照它記要多少銀兩）。"""
    p = ctx.state.player
    p.shop_line, p.shop_line_seed = key, int(ctx.state.world.time)
    p.shop_hold = shop_base.hold_for(ctx.state, ctx.content, key, problem)


def _shop_after(ctx: Game, problem: str | None, done: str, keyer=None) -> None:
    """照這一下的擋法記掌櫃那一句：做成了是 done，被拒照 shop_base.problem_key（懸賞榜照 board_key）換成情況鍵，連同被拒的原因（FB-192）。"""
    _shop_say(ctx, (keyer or shop_base.problem_key)(problem, done), problem)


def _shop_open(ctx: Game) -> str | None:
    """哪一間店開著（店面獨立介面設計 1.1；同 options() 的先後：懸賞榜、鐵匠鋪、馬市）。那個地方已經不開門了（同步之前）是 None；
    鐵匠鋪的一步一步單子還開著（開關關著時開的、舊存檔）也是 None，照舊畫那一串按鈕（店面上的鈕在單子那一步不在選單上）。"""
    # 先後在 MENU_ORDER["open"]（core_seams，全部拆包第 56 批）：擂台打到一半（Joy 2026-10-14「擂台應該要是獨立的一頁」）、懸賞榜、鐵匠鋪、馬市，最後是店面登記的店（坐在店裡、這裡也還開著）；
    # 格回 "" 是坐著、這裡不開門了
    return features_core.menu_first("open", OPEN_CORE, ctx) or None


def _shop_live(ctx: Game, option_ids=None, shop: str = "smith") -> bool:
    """這間店那一串此刻真的是眼前的選單（店面與直接開爐都問它）：選單上有這間店的離開鈕（shop_base.BACKS：鐵匠鋪 smith:back、
    馬市 market:back、懸賞榜 bounty:back 或第三層的 bounty:unpick），而且前面沒有決戰、奪璽單挑的鈕。決戰開打、休季時選單換成三招
    或「休季中」，店裡那一串根本不在上面（picking_* 卻還是真的）：這時給店面，出店會被拒絕、人就困在店裡，休季還開得了爐
    （第一批終審 Critical 1）。集結時決戰的鈕排在店裡那一串前面：照舊畫那一串，加入、趕到的鈕不被蓋住。
    option_ids 是現在的選單（main_view 已經讀過就傳進來）；沒給就讀一次（不推進戰鬥）。"""
    ids = [o.id for o in ctx.options(odds=False, tick=False)] if option_ids is None else list(option_ids)
    return any(back in ids for back in shop_base.BACKS[shop]) and not any(i.startswith(("battle:", "seal:")) for i in ids)


def shop_view(ctx: Game, option_ids=None) -> dict | None:
    """店面（店面獨立介面設計 6.1）：開關開著、有一間店開著（_shop_open）、那間店那一串是眼前的選單（_shop_live）才有；
    照哪一間店問那一包（Feature.shop_view，features.shop_page；一間店只有一包認）。"""
    c = ctx.content
    if not c.config.shop_screens:
        return None
    shop = _shop_open(ctx)
    if shop is None or not _shop_live(ctx, option_ids, shop):
        return None
    return features_core.shop_page(ctx, shop)


def bulletin(ctx: Game) -> list[str]:
    """江湖頁那排小標「大事」點開的本週大事（Markdown）：這一週已經發生的大事，新的在前、最多 BULLETIN_MAX 則。
    江湖紀錄裡的「江湖大事」只寫進剛好在場同步到的那個人，這張卡讓每個人都看得到。開關關著時是空的；
    休季時也是空的：結算卡已經列著這一季的每一件大事與結局（FB-046）。"""
    return [f"**{title}**\n\n{text}" for title, text in _bulletin_events(ctx)]


def _bulletin_events(ctx: Game) -> list[tuple[str, str]]:
    """本週大事面板上的（標題, 公告全文），新的在前、最多 BULLETIN_MAX 則。"""
    w, c = ctx.state.world, ctx.content
    if not calendar.season_one_on(w, c) or w.ended:
        return []
    start = calendar.week_start(calendar.point(w.time, c, w).week, c, w) - calendar.EPS_SECONDS
    titles = {e.id: e.title for e in timetable.events(w, c)}
    done = [(i, eid, r) for i, (eid, r) in enumerate(w.timeline.items()) if r.text and r.time >= start]
    done.sort(key=lambda item: (item[2].time, item[0]), reverse=True)
    return [(titles.get(eid, eid), r.text) for _, eid, r in done[:BULLETIN_MAX]]


def _news_on_cards(ctx: Game) -> set[str]:
    """江湖頁的卡片上已經寫著全文的時刻表公告：平常是本週大事（那排小標「大事」點開的面板），休季時是結算卡（結局與這一季的每一件大事）。"""
    w = ctx.state.world
    if w.ended and season_one(ctx.content, w):
        shown = {r.text for r in w.timeline.values()} | {w.ending_text}
    else:
        shown = {text for _, text in _bulletin_events(ctx)}
    shown.discard("")
    return shown


def season_result(ctx: Game) -> dict | None:
    """休季時江湖頁最上面的結算卡（計畫 T9）：結局與季末公告、最終三方態勢與三條戰況、時刻表每一件的結果（誰改寫的）、
    各陣營出力前五。只有第一季（開關開著＋這一季的章）收季之後才有；資料在收季那一刻存好（world.end_season），這裡只讀。
    時刻表那一列：結算過的是公告全文；跳過的寫「這一季沒有發生」；季提前收束、還沒輪到的寫「季已落幕，沒有發生」。
    改寫的人寫公告上的名字（timetable.shown：一律名號；只有這一版之前匿名鎖定的，照記下的「某位少俠」寫）。"""
    s, c = ctx.state, ctx.content
    w = s.world
    if not w.ended or not season_one(c, w):
        return None
    values = dict(w.final_trends)
    huangjin = values.get(HUANGJIN, 0)
    standing = {"guan": 100 - huangjin, "huang": huangjin}
    names = {f.id: f.name for f in c.scenario.factions}
    timeline = []
    for event in timetable.events(w, c):  # 天命之季含天命之爭（玉璽二）
        result = w.timeline.get(event.id)
        if result is None:
            text = "（季已落幕，沒有發生。）"
        elif not result.text:
            text = "（這一季沒有發生。）"
        else:
            text = result.text
        lock = w.locks.get(event.id) if result is not None and result.locked_by else None
        timeline.append({
            "week": event.week, "title": event.title, "text": text,
            "locked_by": timetable.shown(lock) if lock is not None else None,
        })
    out = {
        "title": w.ending_title, "text": w.ending_text,
        "stances": [{"side": side, "name": names.get(side, side), "value": value} for side, value in standing.items()],
        "fronts": [{"id": f, "name": trend_name(c, f), "value": values.get(f, 0)} for f in front_ids(c)],
        "timeline": timeline,
        "rankings": [
            {"faction": f.id, "name": f.name, "rows": [list(row) for row in w.final_rankings.get(f.id, [])]}
            for f in c.scenario.factions
        ],
    }
    ending = ctx.ending_card()  # 三陣營四勝利（減法季批 3c，欄位表 main.ending）：關著的季沒有這個鍵
    if ending is not None:
        out["ending"] = ending
    return out


def place_minutes(ctx: Game, loc_id: str) -> int | None:
    """從此刻的位置走到 loc_id（步行；騎著馬照馬的步調）要現實幾分鐘（同狀態列的「現實約 N 分鐘後抵達」）；就在這裡是 0、走不到是 None。
    先照摸清的路（atlas.way_to），走不到再照所有開放的地點（投靠點是公開的，三方卡照樣寫得出分鐘）。三方卡、本週卡的目標用。"""
    s, c = ctx.state, ctx.content
    if s.player.journey is None and s.player.location == loc_id:
        return 0
    route = atlas.way_to(s, c, loc_id)
    if route is None and s.player.journey is None:
        route = atlas.shortest_routes(s, c).get(loc_id)
    if route is None or not route.path:
        return None
    return ctx._real_minutes(atlas.travel_seconds(route.minutes, "walk", pace=mounts.pace(s, c)))


def trends_text(ctx: Game) -> str:
    w = ctx.state.world
    parts = []
    for trend in ctx.content.scenario.trends:
        if not trend_shown(ctx.content, w, trend.id) or not is_revealed(w, ctx.content, trend.id):
            continue
        value = trend_value(ctx.state, ctx.content, trend.id)
        bar = "█" * (value // 5) + "░" * (20 - value // 5)
        parts.append(f"**{trend.name}** {value}/100\n\n`{bar}`\n\n{trend.desc}")
    if w.ended:
        parts.append(f"## 結局：{w.ending_title}\n\n{w.ending_text}")
    return "\n\n".join(parts) or "（江湖暫時風平浪靜。）"


def rumors_text(ctx: Game, limit: int = 30) -> str:
    """見聞頁的傳聞（一條清單，main_view 的 rumors）：只列聽得到的（rules.audible——陣營軍情只給那個陣營、個人線索只給
    那個人；第一季的地方傳聞只給此刻人在那個大區的人、只留傳聞板上最近幾天的）。開關關著時跟以前一樣。"""
    ears = ears_of(ctx.state, ctx.content)
    heard = [r for r in ctx.state.world.rumors if audible(r, ears)]
    return _timeline(heard[-limit:][::-1], ctx._day_stamp) or "（尚無傳聞。）"


def rumor_layers(ctx: Game) -> list[dict[str, str]] | None:
    """見聞頁的傳聞分四層（天下大事、陣營軍情、所在大區、個人線索；rumor_view.layers），每層 {id, title, body}，body 是
    Markdown。只在第一季的規則開著時分：開關關著（或這一季開季時沒開）是 None，頁面照舊畫 rumors_text 那一條清單。"""
    if not season_one(ctx.content, ctx.state.world):
        return None
    return rumor_view.layers(ctx.state, ctx.content, ctx.world, ctx._day_stamp)


def chronicle_text(ctx: Game) -> str:
    """江湖史：這一季在最前面，往前每一季各一段（線上架構設計 3.2：江湖史跨季保留），再來是歷屆擂主，最後是玉璽碎片。
    神器譜搬到見聞的「榜單」（divine_book_view，Joy 2026-10-17）。"""
    number = ctx.world.get_season_number()
    if season_one(ctx.content, ctx.state.world):  # 見聞改版（Joy 2026-11-08 說好）：天下大事併進江湖史，照日子分段、新的在前
        current = _history_days(ctx) or "（江湖史尚無記載。）"
    else:
        current = _timeline(ctx.state.world.chronicle, ctx._day_stamp) or "（江湖史尚無記載。）"
    past = ctx.world.chronicle_before(number)
    parts = [f"### 第 {number} 季（本季）\n\n{current}" if past else current]
    parts += [f"### 第 {n} 季\n\n{_timeline(entries, calendar.day_text)}" for n, entries in past]  # 上一季照舊寫「第N天」
    champs = arena_ranks.champions([(number, [e.text for e in ctx.state.world.chronicle])]
                             + [(n, [e.text for e in entries]) for n, entries in past])  # 歷屆擂主（跨季）
    if champs:
        parts.append(champs)
    if seal_base.on(ctx.content):  # 七格玉璽排在江湖史最上面（第十節）；舊的碎片紀錄只當前史一行（11.5）
        old, view = ctx.world.get_jade_seal_fragments(), ctx.world.seal_state()
        parts.insert(0, seal_base.chronicle_block(ctx.content, view.registry, ctx.world.jade_seal_summary() if old else "",
                                                  mandate=seal_base.mandate_now(view.registry, view.season)))  # 天命之季多一句（玉璽二）
    else:
        parts.append(ctx.world.jade_seal_summary())
    return "\n\n---\n\n".join(parts)


XINGSHI_LINE = "天下形勢："  # 每天一篇〈天下形勢〉的那一行：見聞・戰況有全文，江湖史與傳聞不再列
SEASON_BOARD = re.compile(r"^第 \d+ 季.{1,6}(榜|譜)：")  # 季末逐張榜的榜首那幾行：這一季的看「榜單」，往季的照舊留在江湖史


def _history_days(ctx: Game) -> str:
    """這一季的江湖史（見聞改版，Joy 2026-11-08 說好「天下大事併進江湖史」）：江湖史的條目加上傳聞的天下大事，
    同一個時刻兩邊都有的（同一件事）只留寫得比較完整的那一則；天下形勢那一行（戰況有全文）、這一季的季末榜首（榜單看得到）不列。
    照日子分段（#### 那一天），新的在前；一天裡也是新的在前。"""
    w = ctx.state.world
    world_news = [r for r in w.rumors if r.layer == "world" and not r.text.startswith(XINGSHI_LINE)]
    kept, dropped = [], set()
    for e in w.chronicle:
        if XINGSHI_LINE in e.text or SEASON_BOARD.match(e.text):
            continue
        twin = next((i for i, r in enumerate(world_news) if r.time == e.time and i not in dropped and _same_event(e.text, r.text)), None)
        if twin is None:
            kept.append(e)
        elif len(e.text) > len(world_news[twin].text):  # 同一件事寫得比較完整的那一則留著
            kept.append(e)
            dropped.add(twin)
    world_news = [r for i, r in enumerate(world_news) if i not in dropped]
    days: list[tuple[str, list[str]]] = []
    for e in sorted([*kept, *world_news], key=lambda e: e.time, reverse=True):
        stamp = ctx._day_stamp(e.time)
        day, _, clock = stamp.rpartition(" ")
        if not day or ":" not in clock:  # 沒有時刻的寫法（舊季曆）：整串當那一天
            day, clock = stamp, ""
        if not days or days[-1][0] != day:
            days.append((day, []))
        days[-1][1].append(f"{clock}　{e.text}" if clock else e.text)
    return "\n\n".join(f"#### {day}\n\n" + "\n\n".join(rows) for day, rows in days)


def _pairs(text: str) -> set[str]:
    han = re.sub(r"[^\u4e00-\u9fff]", "", text)
    return {han[i:i + 2] for i in range(len(han) - 1)}


def _same_event(short: str, told: str) -> bool:
    """江湖史那一行跟同一個時刻的天下大事是不是同一件事：江湖史那一行的兩字詞有四分之一以上也出現在傳聞那一則裡
    （「長社一戰，波才敗走陽翟」對「……波才敗走陽翟」；季末的「黃巾之亂落幕」對同一刻的「攻下曲陽」只沾到「黃巾」，不算）。"""
    mine = _pairs(short)
    return bool(mine) and len(mine & _pairs(told)) / len(mine) >= 0.25


def _travel_end(entry: JournalEntry) -> str | None:
    """「前往 X」那一則的目的地；不是前往是 None。"""
    return entry.title[len(TRAVEL):] if entry.title.startswith(TRAVEL) else None


TRAVEL = "前往 "
TRAVEL_FOLD = "走了 {n} 段路"  # 待 joy 潤：連著的前往併成一行


def _add_changes(changes: list[str]) -> list[str]:
    """幾則的數值變化加在一起（「心得 +4」「心得 +4」→「心得 +8」）；認不得的照原樣留著。"""
    total: dict[str, int] = {}
    other: list[str] = []
    for c in changes:
        m = re.fullmatch(r"(\S+) ([+-]\d+)", c)
        if m is None:
            other.append(c)
        else:
            total[m[1]] = total.get(m[1], 0) + int(m[2])
    return [f"{k} {v:+d}" for k, v in total.items() if v] + other


def own_journal(ctx: Game, first: int = 1) -> list[JournalEntry]:
    """江湖紀錄頁「剛剛」以下那一串（見聞改版，Joy 2026-11-08 說好）：只放自己的事——江湖大事（江湖史有）不列；
    只有標題、要點開才知道是什麼的（「奇事」「懸賞榜」），把第一句當標記寫出來；連著的「前往」併成一行「走了 N 段路」。"""
    rows: list[JournalEntry] = []
    for e in ctx.state.journal[first:]:
        if e.title == journal.WORLD_NEWS:
            continue
        if not e.tag and e.lines:
            e = e.model_copy(update={"tag": e.lines[0]})
        end = _travel_end(e)
        prev = rows[-1] if rows else None
        if end is not None and prev is not None and (prev.title.startswith(TRAVEL) or prev.title.startswith(TRAVEL_FOLD[:2])) and not e.lines:
            stops = prev.tag.split(" → ") if prev.title.startswith(TRAVEL_FOLD[:2]) else [_travel_end(prev)]
            rows[-1] = prev.model_copy(update={
                "title": TRAVEL_FOLD.format(n=len(stops) + 1), "tag": " → ".join([end, *stops]),
                "changes": _add_changes([*prev.changes, *e.changes]), "lines": [],
            })
            continue
        rows.append(e)
    return rows


def _day_stamp(ctx: Game, time: float) -> str:
    """江湖史與傳聞的時間：沒有季曆時只寫天數（「第2天」），第一季寫季曆。"""
    return ctx.stamp(time, clock=False)


def _chip(ctx: Game, change: str, seed: str) -> tuple[str, int] | None:
    """江湖紀錄畫數值標籤時，戰況變化的換法（FB-064，journal.ChipFn）：紀錄裡存的是機器可讀的寫法，這裡照內容換成一句話、
    照「現在看的人」的陣營算對他是好事還是壞事（顏色在畫的那一刻才定，換了陣營再畫就跟著變）。"""
    return front_chip(ctx.content, ctx._side(), change, seed)


def latest_entry_html(ctx: Game) -> str:
    entries = ctx.state.journal
    return journal.card_html(entries[0], ctx.stamp, functools.partial(_chip, ctx)) if entries else ""


def journal_top_html(ctx: Game) -> str:
    """江湖紀錄頁的第一則（伺服器的 latest，底下接 journal_html(1, …)）：最新一則就是「剛剛」那張戰鬥卡片那一場時，
    放卡片沒寫到的補充（照舊）；其他時候畫最新一則——包括「剛剛」越過的那則配點（_now_start），它在江湖紀錄裡照樣列在最前面。"""
    if shows_battle_card(ctx) and _now_start(ctx) == 0:
        return battle_extra_html(ctx)
    return latest_entry_html(ctx)


def now_entry_html(ctx: Game) -> str:
    """江湖頁「剛剛」那一則（FB-046）：最新一則；最新的幾則若只是時刻表大事的公告（_deliver_big_events 補的），
    而且每一件的全文江湖頁的卡片上已經有了（_news_on_cards），就往前找第一則不是的——同一段公告不在「剛剛」
    再寫一次，剛做完的事也不會因為一件大事發生就被擠掉。江湖紀錄頁照舊從最新一則列起（latest_entry_html）。
    一次補好幾件時每一行是「季曆時間　公告全文」。
    配點那一則也越過（計畫二最終審查 M1，見 _now_start）；越過之後什麼都不剩（只有配點）時才放它，不讓「剛剛」空著。
    籌備中不放（FB-049）：那時最新一則是開場那一則，寫著「賽季開始」、叫人先去探索，選單卻只有「等待管理者開季」。
    草廬裡（序章，T7 審查 I2、I3）只放自己做的事的結果：江湖大事、你不在的時候、賽季開場（journal.is_world_entry）都不放，
    草廬的事件在眼前時整張卡不放（它只是重複事件的標題，還把選項擠到分頁列底下）。紀錄裡照舊都有。"""
    if ctx._preparing():
        return ""
    hut = prologue_rules.active(ctx.state, ctx.content)
    if hut and (ctx.state.pending_event is not None or ctx.state.player.sensing is not None):
        return ""  # 草廬的事件或草廬四景的有所感（做法、畫下來）在眼前：整張卡不放
    if ctx._opening_pending():
        return ""  # 開局第一分鐘（減法季批 7）：旁白與三選一就是第一張卡，開場那一則（含丹的福利）留在紀錄裡（整合設計 6.7）
    entry = _now_entry(ctx)
    return journal.card_html(entry, ctx.stamp, functools.partial(_chip, ctx)) if entry is not None else ""


def _now_entry(ctx: Game) -> JournalEntry | None:
    """「剛剛」那一則（now_entry_html 的挑法，不看籌備中與草廬的事件）。"""
    hut = prologue_rules.active(ctx.state, ctx.content)
    shown = _news_on_cards(ctx)

    def repeated(entry: JournalEntry) -> bool:
        story = entry.lines or [entry.tag]
        return entry.title == journal.WORLD_NEWS and all(
            line in shown or line.partition("　")[2] in shown for line in story
        )

    fresh = [e for e in ctx.state.journal if not repeated(e) and not (hut and journal.is_world_entry(e))]
    return next((e for e in fresh if e.title != journal.ALLOCATE), fresh[0] if fresh else None)


def now_front(ctx: Game) -> dict | None:
    """「剛剛」那一則是出陣、有出陣回報（JournalEntry.front，sortie.report）時給畫面的資料；不是 None。戰鬥卡片照 shows_battle_card 看
    同一則，不是戰鬥卡片照 now_entry_html 的挑法（那裡不放卡時這裡也不給）。"""
    if shows_battle_card(ctx):
        entry = ctx.state.journal[_now_start(ctx)]
    elif now_entry_html(ctx):
        entry = _now_entry(ctx)
    else:
        return None
    return entry.front.model_dump() if entry is not None and entry.front is not None else None


def journal_html(ctx: Game, start: int = 1, limit: int = 5, heading: str = "", empty: str = "") -> str:
    """江湖紀錄頁「剛剛」以下的第 start 則起 limit 則（own_journal 那一串：只放自己的事、前往併成一行）；start 0 從最新一則算起。"""
    first = min(start, 1)
    rows = own_journal(ctx, first)[start - first:start - first + limit]
    return journal.rows_html(rows, heading, empty, ctx.stamp, functools.partial(_chip, ctx))


def _now_start(ctx: Game) -> int:
    """「剛剛」從江湖紀錄的第幾則看起：最新的幾則若是配點就越過（計畫二最終審查 M1）。配點是點名號展開、在狀態列上按的，
    跟 journal.add_guide 一樣不換「剛剛」——升級那一仗打完照著「你有 N 點屬性可以分配」去配點，那一場的戰鬥卡片
    不會因此不見。全都是配點時從最新一則看起。江湖紀錄頁照舊從最新一則列起（journal_top_html／journal_html）。"""
    return next((i for i, e in enumerate(ctx.state.journal) if e.title != journal.ALLOCATE), 0)


def shows_battle_card(ctx: Game) -> bool:
    s, i = ctx.state, _now_start(ctx)
    return ctx.battle_card_id() is not None and len(s.journal) > i and s.journal[i].battle_id == s.battle_card


def battle_extra_html(ctx: Game, for_card: bool = False) -> str:
    """「剛剛」那張戰鬥卡片底下的補充：那一場那一則裡卡片沒寫到的（越過最新的配點，跟 shows_battle_card 看同一則）。
    for_card（江湖頁的「剛剛」用）：打完接著有事件待處理時，「你聽到一件事」那一行讓出來——事件的最後一個選項要留在第一屏
    （FB-076）；江湖紀錄頁最上面（journal_top_html）不給，照舊列出，那一行也還在紀錄那一則裡。"""
    if not shows_battle_card(ctx):
        return ""
    record = battlelog.find(ctx.state, ctx.state.battle_card)
    entry = ctx.state.journal[_now_start(ctx)]
    lines, changes = journal.card_leftovers(entry, battlelog.told_lines(record), battlelog.gains_list(record))
    if for_card and ctx.state.pending_event is not None:
        lines = journal.without_fragments(lines)
    return journal.extra_html(lines, changes, functools.partial(_chip, ctx), str(entry.time))


def _timeline(entries: list[Rumor], when: Callable[[float], str]) -> str:
    return "\n\n".join(f"{when(e.time)}　{e.text}" for e in entries)
