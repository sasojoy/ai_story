"""〈天下形勢〉開單到收下（功能包 territory_acts；全部拆包第 46 批）：三段式的 A（鎖內拿單）與 C（鎖內重驗才收）、換天開單、寬限到了照固定段收、見聞頁的資料。
原本 Game 上的 _xingshi_start／open／finish／grace、xingshi_waiting、release_xingshi、xingshi_request、settle_xingshi、xingshi_view、xingshi_mark、
admin_xingshi_now，名字去掉前導底線與 xingshi 的字、第一個參數是 ctx。B 段（鎖外請模型）與背景執行緒留在 server.py（用殼的佇列與預算）。
"""
from __future__ import annotations

from tianxia.rules import add_chronicle, add_rumor
from tianxia.state import XingshiEssay, XingshiMark, XingshiTicket

from . import xingshi

# 領地爭奪第三批 A：管理者「現在就開一篇天下形勢」的回話（管理者看的，待 joy 潤）
XINGSHI_OFF = "這一季沒有〈天下形勢〉。"
XINGSHI_OPENED = "第 {n} 篇〈天下形勢〉開了單：伺服器在背景請模型寫，寫不出來或 {minutes} 分鐘沒交回就照固定段收。"


def start(ctx) -> None:
    """這一季第一次結算（只記下 key 的那一下）：記〈天下形勢〉的起點——三條線此刻的值、day_log 與天下大事讀到哪裡（XingshiMark）。
    已經記過、或〈天下形勢〉關著不動。"""
    c, w = ctx.content, ctx.state.world
    if not xingshi.on(c, w) or w.xingshi_mark is not None:
        return
    w.xingshi_mark = XingshiMark(log=len(w.conquest.day_log), rumors=len(w.rumors), lines=xingshi.line_values(w, c))

def open_ticket(ctx, key: int) -> None:
    """結算完那一下開一張新的單（WorldState.xingshi_ticket）：事實是上一篇以來的 day_log、三條線比上一篇的動向、天下大事（xingshi.facts），
    「是日：…」照收場的那幾筆（summary_line）。上一張還沒收的先照固定段收（一天一篇，不會兩張單並存）；讀到哪裡往前挪（XingshiMark）。"""
    c, w = ctx.content, ctx.state.world
    if not xingshi.on(c, w):
        return
    if w.xingshi_ticket is not None:
        finish(ctx, None)
    mark = w.xingshi_mark or XingshiMark()
    notes = w.conquest.day_log[mark.log:]
    n = max([e.n for e in w.xingshi], default=0) + 1
    w.xingshi_ticket = XingshiTicket(
        n=n, key=key, opened_real=ctx.now,  # 現實時鐘（FB-577）
        facts=xingshi.facts(w, c, notes, mark.lines, mark.rumors, night=xingshi.is_night(ctx.pill_now(), c),  # 白天開的不寫「打到入夜」
                            marks_from=mark.fired),  # 減法季批 4：上一篇開單以後過門檻的痕跡（PM 2026-10-25 修正輪：不再靠世界層傳聞補）
        line=xingshi.summary_line(notes, c),
    )
    w.xingshi_mark = XingshiMark(log=len(w.conquest.day_log), rumors=len(w.rumors), lines=xingshi.line_values(w, c),
                                 fired=len(w.marks_fired))  # 這一篇開單那一刻讀到哪裡：開單到收下之間過門檻的，下一篇寫

def finish(ctx, essay: str | None) -> XingshiEssay:
    """收下還在等的那一張：模型寫的過得了 xingshi.clean 就用，不然照固定段（by_rule，畫面上看不出差別）；天下大事一則、江湖史一筆，
    這一季最多留 Config.xingshi.keep 篇。呼叫端確認有單、自己存季。"""
    c, w = ctx.content, ctx.state.world
    ticket = w.xingshi_ticket
    text = xingshi.clean(essay) if essay else None
    done = XingshiEssay(
        key=ticket.key, time=w.time, n=ticket.n, line=ticket.line, by_rule=text is None,
        essay=text if text is not None else xingshi.rule_text(ticket.facts, c, f"{w.tianji}|{ticket.key}|{ticket.n}"),
    )
    w.xingshi = (w.xingshi + [done])[-c.config.xingshi.keep:]
    news = xingshi.rumor_text(ticket.line)
    add_rumor(ctx.state, news, content=c, layer="world")
    add_chronicle(ctx.state, news)
    w.xingshi_ticket = None
    return done

def grace(ctx) -> bool:
    """還在等模型的那一張單開了 Config.xingshi.grace_seconds（現實秒）還沒交回：照固定段收（伺服器關著、模型壞了，照樣每天一篇）。
    暫停中不收（暫停凍結世界的變化）。收了回 True（呼叫端存季）。開單、寬限、重試一律照現實時鐘 ctx.now（FB-577：管理者快轉推的
    advanced_real 只活在那一個 Game 裡，拿 pill_now 開的單，沒快轉過的 Game 要等現實追上十幾個小時才收得掉）；換天照舊認 pill_now。"""
    c, w = ctx.content, ctx.state.world
    ticket = w.xingshi_ticket
    if ticket is None or not xingshi.on(c, w) or ctx.world.paused_at() is not None:
        return False
    if ctx.now - ticket.opened_real < c.config.xingshi.grace_seconds:
        return False
    finish(ctx, None)
    return True

def waiting(ctx) -> bool:
    """有一張單等著伺服器拿去請模型寫（server._xingshi_waiting 問；還沒被拿走、上一趟沒輪到的隔過 retry_seconds 了）。只讀。"""
    ticket = ctx.state.world.xingshi_ticket
    return (ticket is not None and not ticket.taken and ctx.now >= ticket.retry_at
            and xingshi.on(ctx.content, ctx.state.world))

def release(ctx, request: xingshi.XingshiRequest) -> bool:
    """B 段沒叫成模型（佇列裡假人的名額被佔、排不到）：同一張單放回去（taken 清掉），隔 Config.xingshi.retry_seconds 再拿；
    寬限到了還沒寫成，照舊由 _xingshi_grace 照固定段收（PM，第三批 A 回報之後：不要一被擋就退回固定段）。放了回 True、存季。"""
    ticket = ctx.state.world.xingshi_ticket
    if ticket is None or ticket.n != request.n or ticket.key != request.key:
        return False
    ticket.taken, ticket.retry_at = False, ctx.now + ctx.content.config.xingshi.retry_seconds
    ctx._save_season()
    return True

def request(ctx) -> xingshi.XingshiRequest | None:
    """A 段（server.xingshi_once 在行動鎖內叫）：拿走還在等的那一張單（記 taken、存季，同一張不再拿第二次），回請模型寫要的東西；
    沒有、已經被拿走是 None。"""
    w = ctx.state.world
    if not waiting(ctx):
        return None
    ticket = w.xingshi_ticket
    ticket.taken = True
    ctx._save_season()
    return xingshi.XingshiRequest(n=ticket.n, key=ticket.key, line=ticket.line, facts=list(ticket.facts))

def settle(ctx, request: xingshi.XingshiRequest, essay: str | None) -> bool:
    """C 段：還是同一張單（篇次與 key 都對得上、還沒收）才收；文章過不了 xingshi.clean 照固定段。收了回 True、存季。
    單子換了（過了 grace 已經照固定段收、隔天開了新的）就丟掉。"""
    ticket = ctx.state.world.xingshi_ticket
    if ticket is None or ticket.n != request.n or ticket.key != request.key:
        return False
    finish(ctx, essay)
    ctx._save_season()
    return True

def view(ctx) -> dict:
    """見聞「形勢」頁（/api/xingshi）：這一季收下的每一篇（新的在前；標題、時刻、「是日：…」、文章），pending＝今天這一篇還在寫。
    不寫是不是模型寫的（by_rule 不送）。〈天下形勢〉關著是 {"on": False}。"""
    c, w = ctx.content, ctx.state.world
    if not xingshi.on(c, w):
        return {"on": False}
    essays = [{"n": e.n, "title": xingshi.HEAD.format(n=e.n), "time": ctx.stamp(e.time), "line": e.line, "essay": e.essay}
              for e in reversed(w.xingshi)]
    return {"on": True, "pending": w.xingshi_ticket is not None, "essays": essays}

def mark(ctx) -> str:
    """見聞「形勢」頁要不要重抓（FB-578；server.main_view 的 xingshi_mark）：收下的最新一篇的篇次，有一張還在寫就多一個「+」。
    開了新單、寫好了都會變，網頁停在那一頁時看到它變了就重抓 /api/xingshi。只讀。"""
    w = ctx.state.world
    latest = max((e.n for e in w.xingshi), default=0)
    return f"{latest}{'+' if w.xingshi_ticket is not None else ''}"

def admin_now(ctx) -> list[str]:
    """管理者（測試與試玩用）：現在就開一篇〈天下形勢〉——照上一篇以來的事實開一張單，效果跟每天結算那一下一樣（還在等的那一張先照
    固定段收）。伺服器照常在背景請模型寫，寫不出來照固定段。"""
    refusal = ctx._admin_refusal("現在就開一篇天下形勢")
    if refusal:
        return ctx._log(refusal)
    c, w = ctx.content, ctx.state.world
    if not xingshi.on(c, w) or w.conquest is None or w.ended:
        return ctx._log([f"（{XINGSHI_OFF}）"])
    open_ticket(ctx, w.conquest.settled_key)
    line = XINGSHI_OPENED.format(n=w.xingshi_ticket.n, minutes=round(c.config.xingshi.grace_seconds / 60))
    ctx._write("天下形勢", [line], tag="管理者")
    ctx._save_season()
    return ctx._log([line])
