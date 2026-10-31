"""擂台形象的動作（功能包 tianxia/features/looks/）。ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from tianxia import journal  # 核心（江湖紀錄）
from tianxia.state import JournalEntry

from . import moves, orders, rules

if TYPE_CHECKING:
    from tianxia.engine import Game

TITLE = "形象"  # 江湖紀錄的標題


def look_of(ctx: Game) -> str:
    """這個人上擂台穿哪一套（報名、更新分身、挑人那一刻記下來）：形象關著是預設；假人照名號挑；真人照自己換上的。"""
    if not rules.on(ctx.content):
        return rules.DEFAULT
    if ctx.state.player.bot:
        return rules.bot_look(ctx.content, ctx.state.player.name)
    wallet = ctx._wallet()
    return rules.DEFAULT if wallet is None else rules.worn(ctx.content, wallet, ctx._mall_owner())


def _shop(ctx: Game) -> dict[str, str]:
    """哪一套此刻在萬寶閣賣（look id → 商品 id）：照商品表裡寫了 look 的那幾件。"""
    return {item.look: item.id for item in ctx.content.mall.values() if item.look}


def view(ctx: Game) -> dict | None:
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return None
    out = rules.view(ctx.content, wallet, ctx._mall_owner(), _shop(ctx))
    out["moves"] = moves_view(ctx)  # 招式動畫（第三批）
    return out


def wear(ctx: Game, look: str) -> list[str]:
    """換上一套（萬寶閣「形象」那一頁）；換了寫一則「形象」江湖紀錄。已經報名擂台的，分身下一次更新才換（同兵器）。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    done, line = rules.wear(ctx.content, wallet, ctx._mall_owner(), look)
    if done:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line]))
    return ctx._log([line])


# ── 自建形象（第二批；orders.py）─────────────────────────

GEN_ENV = "TIANXIA_LOOK_GEN"  # 生圖器：沒設或 off＝等管理者上傳；fake＝假的（開發、測試：抄一套現成的圖，不叫外部服務）
WEB_IMG = Path(__file__).resolve().parents[3] / "web" / "img"


def gen_mode() -> str:
    return os.environ.get(GEN_ENV, "off").strip().lower() or "off"


def image_root(ctx: Game) -> Path:
    """自建形象的圖放哪：資料庫旁邊的 looks/（不進版控；換一份資料庫就是另一份）。"""
    return images_beside(ctx.world.db.path)


def images_beside(db_path) -> Path:
    return Path(db_path).resolve().parent / "looks"


def order(ctx: Game, name: str, prompt: str, ref: str) -> list[str]:
    """下單（orders.place）：成了寫一則「形象」江湖紀錄；生圖器是 fake 就當場抄好圖、變成待審。時間照回體丹那一套。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    pid, line = orders.place(ctx.content, wallet, ctx._mall_owner(), name, prompt, ref,
                             now=ctx.pill_now(), day=ctx._pill_day(), season=ctx.world.get_season_number())
    if pid is None:
        return ctx._log([line])
    item = orders.item_of(ctx.content)
    journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 -{item.price}"]))
    if gen_mode() == "fake":
        sources = sorted(p for p in (WEB_IMG / "looks").iterdir() if p.is_dir()) + [WEB_IMG / "arena"]
        orders.fake_generate(image_root(ctx), orders.look_id(pid), orders.speech.clean(prompt), sources)
        orders.mark(wallet, orders.find(wallet, item.id, pid), image_root(ctx))
    return ctx._log([line])


def _admin_order(ctx: Game, pid: int):
    wallet = ctx._wallet()
    item = orders.item_of(ctx.content)
    if wallet is None or item is None or not ctx.is_admin():
        return None, None, "（此刻無法這麼做。）"
    found = orders.find(wallet, item.id, pid)
    return wallet, found, None if found is not None else f"（沒有第 {pid} 號訂單。）"


# ── 招式動畫（第三批；moves.py）─────────────────────────

FX_SAMPLE = WEB_IMG / "arena" / "fx_sample.webp"  # 範例光效（假的生圖器抄這一張；萬寶閣也拿它當示範）


def current_art(ctx: Game) -> tuple[str, str]:
    """現在練的武功，是自己合成或自創的（全服登記的，不在內容裡）才算：回（id, 顯示的名字）；不是回（"", ""）。"""
    wid = ctx.state.player.member.wugong_id
    if not wid or wid in ctx.content.skills:
        return "", ""
    art = ctx.world.get_skill(wid)
    return (wid, art.name) if art is not None else ("", "")


def current_style(ctx: Game) -> str:
    weapon = ctx.state.player.weapon
    return moves.style_of(weapon.kind if weapon is not None else "")


def move_of(ctx: Game) -> str:
    """上擂台那一刻疊哪一張光效（m<id>；沒有是空字串）：現在練的那一門這一季綁了招式、手上的打法對得上。假人沒有。"""
    if not rules.on(ctx.content) or ctx.state.player.bot:
        return ""
    wallet = ctx._wallet()
    if wallet is None:
        return ""
    art, _ = current_art(ctx)
    return moves.bound(wallet, ctx._mall_owner(), art, current_style(ctx), ctx.world.get_season_number())


def moves_view(ctx: Game) -> dict | None:
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return None
    art, name = current_art(ctx)
    return moves.view(ctx.content, wallet, ctx._mall_owner(), art, name, current_style(ctx), ctx.world.get_season_number())


def order_move(ctx: Game, prompt: str, ref: str) -> list[str]:
    """替現在練的武功下單招式動畫（moves.place）：成了寫一則「形象」江湖紀錄；生圖器是 fake 就當場抄範例、變成待審。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    art, name = current_art(ctx)
    pid, line = moves.place(ctx.content, wallet, ctx._mall_owner(), art, name, current_style(ctx), prompt, ref,
                            now=ctx.pill_now(), day=ctx._pill_day(), season=ctx.world.get_season_number())
    if pid is None:
        return ctx._log([line])
    item = moves.item_of(ctx.content)
    journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 -{item.price}"]))
    if gen_mode() == "fake":
        moves.fake_generate(image_root(ctx), moves.move_id(pid), FX_SAMPLE)
        moves.mark(wallet, moves.find(wallet, item.id, pid), image_root(ctx))
    return ctx._log([line])


def bind_move(ctx: Game, pid: int) -> list[str]:
    """把招式庫的一招綁到現在練的武功上（這一季；同打法免費）。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    art, name = current_art(ctx)
    done, line = moves.bind(wallet, ctx._mall_owner(), pid, art, name, current_style(ctx), ctx.world.get_season_number())
    if done:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line]))
    return ctx._log([line])


def _admin_move(ctx: Game, pid: int):
    wallet = ctx._wallet()
    item = moves.item_of(ctx.content)
    if wallet is None or item is None or not ctx.is_admin():
        return None, None, "（此刻無法這麼做。）"
    found = moves.find(wallet, item.id, pid)
    return wallet, found, None if found is not None else f"（沒有第 {pid} 號招式訂單。）"


def admin_move_upload(ctx: Game, pid: int, data: bytes) -> list[str]:
    wallet, found, problem = _admin_move(ctx, pid)
    if problem:
        return ctx._log([problem])
    if found.status not in (orders.PENDING, orders.REVIEW):
        return ctx._log([f"（「{found.art_name}」的招式{orders.STATUS_TEXT[found.status]}了，不收圖。）"])
    problem = moves.sheet_problem(moves.SHEET, data)
    if problem:
        return ctx._log([f"（{problem}）"])
    root = image_root(ctx)
    orders.save_sheet(root, moves.move_id(pid), moves.SHEET, data)
    moves.mark(wallet, found, root)
    return ctx._log([f"收到「{found.art_name}」的光效，可以審核。"])


def admin_move_release(ctx: Game, pid: int) -> list[str]:
    wallet, found, problem = _admin_move(ctx, pid)
    if problem:
        return ctx._log([problem])
    return ctx._log([moves.release(wallet, found, image_root(ctx))])


def admin_move_reject(ctx: Game, pid: int, note: str) -> list[str]:
    wallet, found, problem = _admin_move(ctx, pid)
    if problem:
        return ctx._log([problem])
    return ctx._log([orders.reject(wallet, found, now=ctx.pill_now(), admin=ctx.state.player.name, note=note)])


def _admin_moves(ctx: Game, wallet) -> dict | None:
    item = moves.item_of(ctx.content)
    if item is None:
        return None
    root = image_root(ctx)
    every = moves.every(wallet, item.id)
    open_ = [m for m in every if m.status in (orders.PENDING, orders.REVIEW)]
    done = [m for m in reversed(every) if m.status not in (orders.PENDING, orders.REVIEW)][:10]

    def row(m):
        mid = moves.move_id(m.pid)
        return {"id": m.pid, "owner": wallet.character_name(m.owner) or m.owner, "art": m.art_name, "style_text": moves.STYLES.get(m.style, m.style),
                "prompt": m.prompt, "status": m.status, "status_text": orders.STATUS_TEXT[m.status], "reason": m.reason, "move": mid,
                "have": orders.sheet_file(root, mid, moves.SHEET) is not None, "gen_prompt": moves.gen_prompt(m) if m in open_ else ""}
    return {"sheet": moves.SHEET, "size": f"{moves.FRAMES * orders.CELL}×{orders.CELL}", "open": [row(m) for m in open_], "done": [row(m) for m in done]}


def admin_view(ctx: Game) -> dict | None:
    """管理者那一頁：還沒做完的訂單（等圖、待審）在前，最近做完的十張在後。每張寫下單的人、名字、樣子、九張到了哪幾張、
    給生圖工具的提示詞。"""
    wallet = ctx._wallet()
    item = orders.item_of(ctx.content)
    if wallet is None or item is None or not ctx.is_admin():
        return None
    root = image_root(ctx)
    every = orders.every(wallet, item.id)
    open_ = [o for o in every if o.status in (orders.PENDING, orders.REVIEW)]
    done = [o for o in reversed(every) if o.status not in (orders.PENDING, orders.REVIEW)][:10]

    def row(o):
        return {"id": o.pid, "owner": wallet.character_name(o.owner) or o.owner, "name": o.name, "prompt": o.prompt,
                "status": o.status, "status_text": orders.STATUS_TEXT[o.status], "reason": o.reason, "look": orders.look_id(o.pid),
                "have": orders.present(root, orders.look_id(o.pid)), "prompts": orders.gen_prompts(o) if o in open_ else {}}
    return {"sheets": orders.SHEETS, "gen": gen_mode(), "open": [row(o) for o in open_], "done": [row(o) for o in done],
            "moves": _admin_moves(ctx, wallet)}


def admin_upload(ctx: Game, pid: int, sheet: str, data: bytes) -> list[str]:
    wallet, found, problem = _admin_order(ctx, pid)
    if problem:
        return ctx._log([problem])
    if found.status not in (orders.PENDING, orders.REVIEW):
        return ctx._log([f"（「{found.name}」{orders.STATUS_TEXT[found.status]}了，不收圖。）"])
    problem = orders.sheet_problem(sheet, data)
    if problem:
        return ctx._log([f"（{problem}）"])
    root = image_root(ctx)
    orders.save_sheet(root, orders.look_id(pid), sheet, data)
    now = orders.mark(wallet, found, root)
    have = len(orders.present(root, orders.look_id(pid)))
    return ctx._log([f"收到「{found.name}」的 {sheet}（{have}/{len(orders.SHEETS)}）" + ("，九張齊了，可以審核。" if now.status == orders.REVIEW else "。")])


def admin_release(ctx: Game, pid: int) -> list[str]:
    wallet, found, problem = _admin_order(ctx, pid)
    if problem:
        return ctx._log([problem])
    return ctx._log([orders.release(wallet, found, image_root(ctx))])


def admin_reject(ctx: Game, pid: int, note: str) -> list[str]:
    wallet, found, problem = _admin_order(ctx, pid)
    if problem:
        return ctx._log([problem])
    return ctx._log([orders.reject(wallet, found, now=ctx.pill_now(), admin=ctx.state.player.name, note=note)])
