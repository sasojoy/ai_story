"""名帖（Joy 2026-10-19；規則在 mingtie.py）：給別人看的樣子、名帖匣、定稿、遞、回帖、檢舉，與管理者看檢舉、撤下、放回
（原本 Game 上的 _shared_or_none、mingtie_face、mingtie_view、mingtie_screen、make_mingtie、mingtie_send_problem、mingtie_send、_mingtie_swap、
report_mingtie、admin_mingtie_reports、admin_mingtie_remove、admin_mingtie_restore；全部拆包第 37 批搬進來，行為一個字不變）。
管理者的三個留委派（管理頁 mingtie 那一格叫 Game；撤下、放回兩個工具第 68 批搬進這一包的 routes.py，委派留給測試）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import gender, speech
from tianxia.characters import name_key
from tianxia.core import jieyi_base  # 名分（結義第一批）：名帖上的義名排行
from tianxia.core.services import NO_SUCH_PLAYER
from tianxia.state import Mingtie

from . import actions, invite_actions, invites
from . import mingtie as mingtie_rules

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.state import GameState


def shared_or_none(ctx):
    """全服的狀態（名帖的檢舉、撤下）：測試用的記憶體世界沒有就是 None（照畫）。"""
    try:
        return ctx.world.read()
    except (AttributeError, NotImplementedError):
        return None


def face(ctx, state: GameState) -> dict | None:
    """這個人的名帖給你看的樣子：還沒做是 None；被檢舉藏起來、管理者撤下、你檢舉過的只剩頭銜（mingtie.shown）。"""
    card = state.player.mingtie
    if card is None:
        return None
    seen = mingtie_rules.shown(shared_or_none(ctx), state.player.name, card.version, ctx.state, ctx.content)
    out = mingtie_rules.view(card) if seen else mingtie_rules.blank_view(card)
    seal = mingtie_rules.seal_of(state, ctx.content)  # 稱號與官職開著：戴著的那一個印成大印；關著沒有這個鍵
    return _with_jieyi(ctx, {**out, "seal": seal} if seal else out, state.player.name)


def _with_jieyi(ctx, card, name: str):
    """名分（結義第一批）：名帖上名號旁邊寫義名與排行（「潁川三義・行二」）；沒結義、開關關著沒有這個鍵。"""
    tag = jieyi_base.card_tag(ctx.content, ctx.world, name)
    return {**card, "jieyi": tag} if tag and isinstance(card, dict) else card


def _with_seal(card, seal):
    return {**card, "seal": seal} if seal and isinstance(card, dict) else card


def view(ctx, board: dict | None = None) -> dict:
    """見聞「名帖匣」：自己那一張、掙到的頭銜、今天還能定稿幾次遞幾張、畫布的規矩、現成的畫、收到的那幾張（新的在前）。
    board 是這一季的榜單（伺服器的 boards_now；頭銜「某某榜第N」照它）。"""
    p, c, cfg = ctx.state.player, ctx.content, ctx.content.config.mingtie
    day, shared = ctx._pill_day(), shared_or_none(ctx)
    box = []
    for copy in reversed(p.mingtie_box):
        seen = mingtie_rules.shown(shared, copy.name, copy.card.version, ctx.state, c)
        box.append({
            "name": copy.name, "when": copy.when, "place": copy.place, "season": copy.season,
            "card": _with_jieyi(ctx, mingtie_rules.view(copy.card) if seen else mingtie_rules.blank_view(copy.card), copy.name),
        })
    return {
        "mine": _with_jieyi(ctx, _with_seal(mingtie_rules.view(p.mingtie), mingtie_rules.seal_of(ctx.state, c)), p.name),
        "pool": mingtie_rules.earned(ctx.state, c, ctx.world, board),
        "made_left": mingtie_rules.made_left(ctx.state, c, day),
        "sent_left": mingtie_rules.sent_left(ctx.state, c, day),
        "limits": {
            "titles": cfg.titles, "motto": cfg.motto_max, "strokes": cfg.max_strokes, "points": cfg.max_points,
            "width": mingtie_rules.WIDTH, "height": mingtie_rules.HEIGHT, "inks": list(mingtie_rules.INKS),
            "ink_names": list(mingtie_rules.INK_NAMES), "pens": list(mingtie_rules.PENS),
        },
        "presets": [{"id": a.id, "name": a.name, "strokes": a.strokes} for a in c.mingtie.arts],
        "box": box,
    }


def screen(ctx, motto: str) -> str | None:
    """定稿之前要不要先請模型審自題那一句（三段式的 A 段）：字表先擋得下的、空的都不必問，回 None；要問回那一句（已整理過）。"""
    line = speech.clean(motto)
    cfg = ctx.content.config.mingtie
    if not line or speech.word_problem(line, ctx.content, speech.MOTTO, cfg.motto_max):
        return None
    return line


def make(ctx, strokes, titles, motto: str = "", verdict: str = "", board: dict | None = None) -> list[str]:
    """名帖定稿：筆劃照 parse_strokes 驗、頭銜要從掙到的那一串裡挑（最多 MingtieTuning.titles 個）、自題一句過 speech
    （verdict 是 B 段模型的判斷）。不花錢；一天最多定稿 made_per_day 次；定稿一次版本 +1（別人收著的舊版不變）。"""
    p, c, cfg = ctx.state.player, ctx.content, ctx.content.config.mingtie
    if not cfg.enabled:
        return ctx._log(["（此刻無法這麼做。）"])
    if mingtie_rules.made_left(ctx.state, c, ctx._pill_day()) <= 0:
        return ctx._log([mingtie_rules.MADE_FULL.format(n=cfg.made_per_day)])
    lines = mingtie_rules.parse_strokes(strokes, c)
    if lines is None:
        return ctx._log([mingtie_rules.BAD_DRAWING])
    picked = [str(t) for t in (titles or [])]
    pool = set(mingtie_rules.earned(ctx.state, c, ctx.world, board))
    if len(picked) > cfg.titles or len(set(picked)) != len(picked) or not set(picked) <= pool:
        return ctx._log([mingtie_rules.BAD_TITLE])
    line = speech.clean(motto)
    problem = speech.problem(line, c, speech.MOTTO, cfg.motto_max, verdict)
    if problem:
        return ctx._log([problem])
    if not lines and not picked and not line:
        return ctx._log([mingtie_rules.EMPTY])
    version = (p.mingtie.version if p.mingtie else 0) + 1
    p.mingtie = Mingtie(strokes=lines, titles=picked, motto=line, version=version)
    p.mingtie_made += 1
    ctx._write("名帖", [mingtie_rules.MADE], merge=True)
    return ctx._log([mingtie_rules.MADE])


def send_problem(ctx, other: Game) -> str | None:
    """遞名帖給他按不按得下去：要有自己的名帖、今天還能遞、他手上還沒有你這一版、你們之間沒有一張還在等的名帖。"""
    s, c = ctx.state, ctx.content
    me, him = s.player, gender.pronoun(other.state)
    if me.mingtie is None:
        return mingtie_rules.NO_CARD
    if invites.between(s.world, me.name, other.state.player.name, "mingtie") is not None:
        return mingtie_rules.WAITING.format(him=him)
    if mingtie_rules.given(ctx.state, other.state.player.name) >= me.mingtie.version:
        return mingtie_rules.SAME_CARD.format(him=him)
    if mingtie_rules.sent_left(ctx.state, c, ctx._pill_day()) <= 0:
        return mingtie_rules.SENT_FULL.format(n=c.config.mingtie.send_per_day)
    return None


def send(ctx, other: Game) -> list[str]:
    """遞名帖：一張邀請，他回帖才兩邊各收一張（_mingtie_swap）。不理就等它逾時，不退今天的次數。"""
    problem = send_problem(ctx, other)
    if problem is not None:
        return [problem]
    s, name = ctx.state, other.state.player.name
    renew = mingtie_rules.given(ctx.state, name) > 0
    invites.expire(s.world)
    invites.send(s.world, ctx.content, "mingtie", s.player.name, name, s.player.location)
    s.player.mingtie_sent += 1
    ctx._save_season()
    ctx.touched.add(name)
    return [f"你遞上{'新' if renew else ''}名帖，等{name}回帖。"]


def swap(ctx, inv, other: Game) -> list[str]:
    """回帖：兩邊各收對方此刻的那一張（存遞出那一刻的樣子），兩邊的江湖紀錄各一則。你得有自己的名帖、他也還有。"""
    me, them, c = ctx.state.player, other.state.player, ctx.content
    if me.mingtie is None or them.mingtie is None:
        invite_actions.tell_sender(ctx, inv, other)
        return [f"（{mingtie_rules.NO_CARD}。）" if me.mingtie is None else "（對方的名帖不在了。）"]
    mingtie_rules.file_copy(ctx.state, other.state, c, gave=me.mingtie.version)
    mingtie_rules.file_copy(other.state, ctx.state, c, gave=them.mingtie.version)
    other._write(f"名帖・{me.name}", [f"{me.name}回了帖，你們互換了名帖。"])
    return [f"你回了帖，與{them.name}互換了名帖。"]


def report(ctx, name: str, version: int) -> list[str]:
    """檢舉一張名帖：你馬上就看不到（mingtie_hidden）；全服記一筆，滿 report_hide 個人藏起來等管理者看。
    要是你看得到的那一張（名帖匣裡收著的、或他此刻就在這裡）。"""
    p, c = ctx.state.player, ctx.content
    try:
        version = int(version)
    except (TypeError, ValueError):
        return ctx._log(["（找不到這張名帖。）"])
    copy = mingtie_rules.copy_of(ctx.state, name)
    here = actions.peer(ctx, name)
    card = here.state.player.mingtie if here is not None else None
    if not ((copy and copy.card.version == version) or (card and card.version == version)):
        return ctx._log(["（找不到這張名帖。）"])
    if name_key(name) == name_key(p.name):
        return ctx._log(["（這是你自己的名帖。）"])
    k = mingtie_rules.key(name, version)
    if k not in p.mingtie_hidden:
        p.mingtie_hidden.append(k)
    ctx.world.mutate(lambda shared: mingtie_rules.report(shared, name, version, p.name))
    return ctx._log([mingtie_rules.REPORTED])


def admin_reports(ctx) -> list[dict]:
    """管理者「名帖檢舉」：被檢舉、還沒處理的（名號、第幾版、幾個人檢舉、那一張的樣子〔只有此刻還是那一版才看得到畫〕）。"""
    if not ctx.is_admin():
        return []
    shared = shared_or_none(ctx)
    if shared is None:
        return []
    rows = []
    for nk, version, count in mingtie_rules.pending_reports(shared, ctx.content):
        target = ctx._admin_target(nk, sync=False)
        card = target.state.player.mingtie if target is not None else None
        rows.append({
            "name": target.state.player.name if target is not None else nk, "version": version, "count": count,
            "card": mingtie_rules.view(card) if card is not None and card.version == version else None,
        })
    return rows


def admin_remove(ctx, name: str, version: int) -> list[str]:
    """撤下一張名帖：那一版以前的都不畫（別人名帖匣裡收著的也是）；他此刻那一張就是這一版的話，畫與自題清掉、頭銜照留、版本 +1，
    他的江湖紀錄一句（不寫是誰撤的）。"""
    refusal = ctx._admin_refusal("撤下名帖")
    if refusal:
        return ctx._log(refusal)
    target = ctx._admin_target(name, sync=False)
    if target is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=name.strip())])
    version, tp = int(version), target.state.player
    nk = name_key(tp.name)
    ctx.world.mutate(lambda shared: shared.mingtie_removed.__setitem__(nk, max(shared.mingtie_removed.get(nk, 0), version)))
    if tp.mingtie is not None and tp.mingtie.version <= version:
        tp.mingtie = mingtie_rules.wipe(tp.mingtie.model_copy(update={"version": version}))
        target._write("名帖", [mingtie_rules.REMOVED_LINE])
    ctx._save_target(target)
    msg = f"已撤下{tp.name}的名帖（第 {version} 版）。"
    ctx._write("撤下名帖", [msg], tag="管理者")
    return ctx._log([msg])


def admin_restore(ctx, name: str, version: int) -> list[str]:
    """放回：檢舉再多也照畫（管理者看過、沒事）。"""
    refusal = ctx._admin_refusal("放回名帖")
    if refusal:
        return ctx._log(refusal)
    k = mingtie_rules.key(name, int(version))
    ctx.world.mutate(lambda shared: None if k in shared.mingtie_cleared else shared.mingtie_cleared.append(k))
    msg = f"已放回{name.strip()}的名帖（第 {int(version)} 版）。"
    ctx._write("放回名帖", [msg], tag="管理者")
    return ctx._log([msg])
