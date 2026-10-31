"""擂台形象的動作（功能包 tianxia/features/looks/）。ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from tianxia import journal  # 核心（江湖紀錄）
from tianxia.state import JournalEntry

from . import orders, rules

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
    return rules.view(ctx.content, wallet, ctx._mall_owner(), _shop(ctx))


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
    return {"sheets": orders.SHEETS, "gen": gen_mode(), "open": [row(o) for o in open_], "done": [row(o) for o in done]}


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
