"""宴客的動作（功能包 tianxia/features/feast/；原本是 Game 上的 _feast_* 與 feast_*，開發規範手冊 3.2）。
ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。Game.feast_*（server 的三段式叫的）留一行委派到這裡。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core.option import Option
from tianxia.core.services import PAUSED_TEXT
from tianxia.state import Feast

from . import rules as feasts

if TYPE_CHECKING:
    from tianxia.engine import Game


def seat(ctx: Game) -> Feast | None:
    """我坐著的那一場（PlayerState.feasting）還能敬酒：還擺著、我在那裡、我還沒敬過。不然是 None。"""
    f = feasts.find(ctx.state, ctx.state.player.feasting)
    return f if feasts.toast_problem(ctx.state, ctx.content, f) is None else None


def options(ctx: Game) -> list[Option]:
    """「此地還能做」裡的入席：這裡擺著的每一場一顆（不花體力）；敬過了灰掉。"""
    s, c = ctx.state, ctx.content
    out: list[Option] = []
    for f in feasts.here(s, c):
        host = feasts.host_name(c, f)
        if feasts.toasted(s, f):
            out.append(Option(id=f"feast:join:{f.id}", label=feasts.DONE_LABEL.format(host=host), enabled=False))
        else:
            out.append(Option(id=f"feast:join:{f.id}", label=feasts.JOIN_LABEL.format(host=host)))
    return out


def menu(ctx: Game) -> list[Option] | None:
    """赴宴（第三批）：坐在席上時整個選單換成固定的敬酒詞與離席；自己寫的走輸入框（free_text_prompt）。沒坐著是 None。"""
    if ctx.state.player.feasting is None or seat(ctx) is None:
        return None
    return [Option(id=f"feast:toast:{i}", label=feasts.TOAST_LABEL.format(text=t)) for i, t in enumerate(feasts.FIXED_TOASTS)] + [
        Option(id="feast:leave", label=feasts.LEAVE_LABEL)]


def title(ctx: Game, arg: str) -> str:
    """這一下江湖紀錄的標題（動作之前先算：敬酒、離席照坐著的那一場，入席照 id）：「宴客・某某」，找不到那一場是「宴客」。"""
    s, c = ctx.state, ctx.content
    f = feasts.find(s, s.player.feasting) if arg.startswith(("toast", "leave")) else feasts.find(
        s, int(arg.partition(":")[2]) if arg.partition(":")[2].isdecimal() else None)
    return f"{feasts.TITLE}・{feasts.host_name(c, f)}" if f is not None else feasts.TITLE


def act(ctx: Game, arg: str) -> list[str]:
    """入席（feast:join:<id>，不花體力）、挑一句固定的敬酒詞（feast:toast:<i>）、離席（feast:leave）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    verb, _, rest = arg.partition(":")
    if verb == "join":
        f = feasts.find(s, int(rest) if rest.isdecimal() else None)
        problem = feasts.toast_problem(s, c, f)
        if problem is not None:
            return [problem]
        p.feasting = f.id
        return [feasts.SEATED.format(host=feasts.host_name(c, f), n=len(f.toasts))]
    if verb == "leave":
        p.feasting = None
        return [feasts.LEFT]
    if verb == "toast" and rest.isdecimal() and int(rest) < len(feasts.FIXED_TOASTS):
        f = seat(ctx)
        if f is None:
            p.feasting = None
            return [feasts.GONE]
        return feasts.toast(s, c, f, feasts.FIXED_TOASTS[int(rest)], feasts.FIXED_SCORE, fixed=True)
    return ["（此刻無法這麼做。）"]


def on_sync(ctx: Game) -> None:
    """同步時：散席時我那一句是席間最佳，補名望（一則「宴客」紀錄）；宴散了、人走了，收起敬酒的選單。"""
    cheered = feasts.deliver(ctx.state, ctx.content)
    if cheered:
        ctx._write(feasts.TITLE, cheered)
    if ctx.state.player.feasting is not None and seat(ctx) is None:
        ctx.state.player.feasting = None


def scene(ctx: Game) -> str | None:
    """坐在宴席上時的場景卡（主人、地方、最近三句敬酒詞）；沒坐著（或那一場不能敬了）是 None。"""
    f = seat(ctx) if ctx.state.player.feasting is not None else None
    return feasts.scene(ctx.state, ctx.content, f) if f is not None else None


def free_text_prompt(ctx: Game) -> str | None:
    """坐在宴席上時輸入框的提示語（server.main_view；送出走 feast_text），否則 None。"""
    return feasts.FREE_PROMPT if ctx.state.player.feasting is not None and seat(ctx) is not None else None


def text_request(ctx: Game, text: str) -> feasts.ToastRequest | list[str]:
    """自己寫的敬酒詞，A 段（只讀）：坐在宴席上、這一場還能敬、字數對，就開評分的單子；不然回拒絕的話。"""
    if ctx.world.paused_at() is not None:
        return [f"（{PAUSED_TEXT}。）"]
    f = seat(ctx)
    if f is None:
        return [feasts.NOT_HERE]
    text = feasts.clean_text(text)
    problem = feasts.text_problem(text)
    if problem is not None:
        return [problem]
    return feasts.request(ctx.state, ctx.content, f, text)


def toast(ctx: Game, text: str, score: int, request: feasts.ToastRequest | None = None) -> list[str]:
    """C 段：重驗同一場、同一句才記（分數再夾一次）；對不上回拒絕的話、不寫紀錄。寫一則「宴客・某某」。"""
    now = text_request(ctx, text)
    if isinstance(now, list):
        return now
    if request is not None and (request.feast != now.feast or request.text != now.text):
        return [feasts.GONE]
    f = feasts.find(ctx.state, now.feast)
    msgs = feasts.toast(ctx.state, ctx.content, f, now.text, score, fixed=False)
    ctx._write(f"{feasts.TITLE}・{feasts.host_name(ctx.content, f)}", msgs)
    ctx._save_season()
    return msgs
