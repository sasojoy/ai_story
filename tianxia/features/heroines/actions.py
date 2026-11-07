"""女子與隱線的動作（ctx 是 Game；只叫 tianxia/core/services.py 清單上的）。

- options：「此地還能做」裡，此地出現的女子有一段隱線端得出來時多一顆（不花體力）。
- menu：那一段端在眼前時，選單只剩應下與婉拒。
- choose：heroines:open:<人物> 端出那一段；heroines:yes／heroines:no 收。
- set_adult：設定頁的成人內容開關（路由叫；假人不准開）。
- on_season_start：開關照帶，隱線重來（奇事、情誼都換季重來）。"""
from __future__ import annotations

from tianxia import rules as core_rules
from tianxia.core.option import Option

from . import rules

PREFIX = "heroines"
OPEN, YES, NO = "open", "yes", "no"


def _scene_now(ctx):
    """此刻端在眼前的那一段 (人物 id, HeroineScene)；沒有、或對不上了是 None。"""
    key = rules.notes(ctx.state).scene
    if not key or ":" not in key:
        return None
    cid, step = key.rsplit(":", 1)
    hd = rules.heroine(ctx.content, cid)
    scene = None if hd is None else next((s for s in hd.scenes if str(s.step) == step), None)
    return None if scene is None else (cid, scene)


def options(ctx) -> list[Option]:
    s = ctx.state
    if s.player.journey is not None or not rules.adult(s):
        return []
    out = []
    for cid in ctx._figures_here():
        scene = rules.next_scene(s, ctx.content, cid)
        if scene is not None:
            out.append(Option(id=f"{PREFIX}:{OPEN}:{cid}", label=scene.label))
    return out


def menu(ctx) -> list[Option] | None:
    now = _scene_now(ctx)
    if now is None:
        return None
    _, scene = now
    return [Option(id=f"{PREFIX}:{YES}", label=scene.accept_label), Option(id=f"{PREFIX}:{NO}", label=scene.decline_label)]


def title(ctx, arg: str) -> str:
    now = _scene_now(ctx)
    cid = now[0] if now is not None else arg.split(":", 1)[-1]
    ch = ctx.content.characters.get(cid)
    return ch.name if ch is not None else "渡口"


def act(ctx, arg: str) -> list[str]:
    s, c = ctx.state, ctx.content
    n = rules.notes(s)
    if arg.startswith(OPEN + ":"):
        cid = arg.split(":", 1)[1]
        scene = rules.next_scene(s, c, cid) if cid in ctx._figures_here() else None
        if scene is None:
            return [rules.NO_BOT]
        n.scene = f"{cid}:{scene.step}"
        return [scene.text]
    now = _scene_now(ctx)
    n.scene = None
    if now is None or not rules.adult(s):
        return [rules.NO_BOT]
    cid, scene = now
    if arg == YES:
        n.steps[cid] = max(n.steps.get(cid, 0), scene.step)
        return [scene.accept]
    n.declined[cid] = core_rules.game_day(c, s.world)
    return [scene.decline]


def set_adult(ctx, value: bool) -> list[str]:
    """設定頁的成人內容：打開之前網頁已經跳過一張「我已年滿十八歲」的確認卡（沒按確認不會送到這裡）。關掉那一刻端在眼前的那一段收起來。"""
    s = ctx.state
    if s.player.bot:
        return [rules.NO_BOT]
    s.player.heroines_adult = bool(value)
    if not value:
        rules.notes(s).scene = None
    return [rules.ADULT_ON if value else rules.ADULT_OFF]


def on_season_start(ctx, old) -> None:
    """換季：成人內容的開關照帶（設定是人的，不是角色的）；隱線跟著奇事、情誼一起重來。"""
    ctx.state.player.heroines_adult = old.player.heroines_adult and not ctx.state.player.bot


def status(ctx) -> dict:
    """設定頁那一格：成人內容開著沒（假人不給）。"""
    if ctx.state.player.bot:
        return {}
    return {"heroines": {"adult": rules.adult(ctx.state)}}
