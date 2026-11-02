"""擂台形象的動作（功能包 tianxia/features/looks/）。ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from tianxia import journal  # 核心（江湖紀錄）
from tianxia.state import JournalEntry

from . import market, moves, orders, rules, scenes, studio

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
    out["market"] = market_view(ctx)  # 形象市集（第四批）
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

GEN_ENV = "TIANXIA_LOOK_GEN"  # 生圖器：沒設或 off＝等管理者上傳；fake＝假的（開發、測試：抄一套現成的圖，不叫外部服務）；api＝畫坊（run_studio.py）自動畫
WEB_IMG = Path(__file__).resolve().parents[3] / "web" / "img"


def gen_mode() -> str:
    return os.environ.get(GEN_ENV, "off").strip().lower() or "off"


def image_root(ctx: Game) -> Path:
    """自建形象的圖放哪：資料庫旁邊的 looks/（不進版控；換一份資料庫就是另一份）。"""
    return images_beside(ctx.world.db.path)


def images_beside(db_path) -> Path:
    return Path(db_path).resolve().parent / "looks"


def images_version() -> str:
    """自建的圖此刻的版本（main.looks_ver）：網頁拿它當圖網址的 ?v=，圖一換網址就換。

    為什麼要這一個（Joy 2026-11-02「我手機現在看還是大的圖」）：那一條路由改成 no-cache ＋ ETag 之後，
    新抓的客戶端都會回來驗；但在那之前抓過的，手上那筆帶著舊的 max-age=86400，整天都不會回來問。
    網址帶版本就不受影響——新網址就是新的快取鍵（同 server.versioned_page 對自家檔案那一套）。
    照每個檔的修改時刻與大小算，所以 refit、重畫、退回重來都會換；幾十個檔，一次 stat 不花時間。
    """
    from tianxia.database import default_path  # noqa: PLC0415  伺服器才知道資料庫在哪

    root = images_beside(default_path())
    if not root.is_dir():
        return "0"
    parts: list[str] = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file():
                st = f.stat()
                parts.append(f"{folder.name}/{f.name}:{int(st.st_mtime)}:{st.st_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:10] if parts else "0"


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


def withdraw(ctx: Game, pid: int, kind: str) -> list[str]:
    """下單的人自己撤回還沒上架的自建形象（kind "look"）或招式動畫（"move"）：元寶全退（orders.withdraw），寫一則「形象」江湖紀錄。
    只認自己的單。"""
    wallet = ctx._wallet()
    if wallet is None or not rules.on(ctx.content):
        return ctx._log([rules.OFF])
    mod = moves if kind == "move" else orders
    item = mod.item_of(ctx.content)
    found = None if item is None else mod.find(wallet, item.id, pid)
    if found is None or found.owner != ctx._mall_owner():
        return ctx._log([f"（沒有第 {pid} 號訂單。）"])
    line = orders.withdraw(wallet, found, now=ctx.pill_now())
    if not line.startswith("（"):
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 +{item.price}"]))
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


def current_move_name(ctx: Game) -> str:
    """現在練的那一門自創長出來的招名（落款寫它）；沒有就是武功的名字。"""
    art, name = current_art(ctx)
    found = ctx.world.get_skill(art) if art else None
    return (getattr(found, "move_name", "") or name) if found is not None else ""


def preview_scene(ctx: Game, text: str) -> dict:
    """一句話自創的預覽（不扣元寶、不存）：過字數、只能中文、字表，回導演稿（scenes.direct）或不行的那一句。"""
    text = moves.speech.clean(text)
    problem = scenes.text_problem(text) or moves.speech.word_problem(text, ctx.content, moves.speech.MOTTO, scenes.MAX_TEXT)
    if problem:
        return {"problem": problem}
    return {"scene": scenes.direct(text, current_move_name(ctx))}


def scene_of(ctx: Game, mid: str) -> dict | None:
    """擂台上要演的那一招的導演稿（上架了的才給；舊的光效單是 None）。"""
    wallet, item = ctx._wallet(), moves.item_of(ctx.content)
    if wallet is None or item is None or not moves.is_move(mid):
        return None
    found = moves.find(wallet, item.id, int(mid[len(moves.PREFIX):]))
    return found.scene if found is not None and found.status == orders.MADE else None


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
                            now=ctx.pill_now(), day=ctx._pill_day(), season=ctx.world.get_season_number(), move_name=current_move_name(ctx))
    if pid is None:
        return ctx._log([line])
    item = moves.item_of(ctx.content)
    journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 -{item.price}"]))
    found = moves.find(wallet, item.id, pid)
    if gen_mode() == "fake" and found.scene is None:  # 舊的光效單才抄範例；一句話自創要畫的等管理者上傳
        moves.fake_generate(image_root(ctx), moves.move_id(pid), FX_SAMPLE)
        moves.mark(wallet, found, image_root(ctx))
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


def admin_move_upload(ctx: Game, pid: int, data: bytes, slot: str = moves.SHEET) -> list[str]:
    """上傳一張：舊的光效單是 fx；一句話自創的是導演稿要畫的那幾格（art1、art2）。到齊了變待審。"""
    wallet, found, problem = _admin_move(ctx, pid)
    if problem:
        return ctx._log([problem])
    if found.status not in (orders.PENDING, orders.REVIEW):
        return ctx._log([f"（「{found.art_name}」的招式{orders.STATUS_TEXT[found.status]}了，不收圖。）"])
    problem = moves.art_problem(found, slot, data)
    if problem:
        return ctx._log([f"（{problem}）"])
    root = image_root(ctx)
    orders.save_sheet(root, moves.move_id(pid), slot, data)
    now = moves.mark(wallet, found, root)
    if now.status == orders.REVIEW:
        return ctx._log([f"收到「{found.art_name}」的圖，到齊了，可以審核。"])
    return ctx._log([f"收到「{found.art_name}」的 {slot}，還缺 {'、'.join(moves.missing(found, root))}。"])


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
        arts = [{"slot": a["slot"], "label": a["label"], "have": orders.sheet_file(root, mid, a["slot"]) is not None,
                 "prompt": scenes.art_prompt(m.prompt, a) if m in open_ else ""} for a in scenes.needs_art(m.scene or {})]
        return {"id": m.pid, "owner": wallet.character_name(m.owner) or m.owner, "art": m.art_name, "style_text": moves.STYLES.get(m.style, m.style),
                "prompt": m.prompt, "status": m.status, "status_text": orders.STATUS_TEXT[m.status], "reason": m.reason, "move": mid,
                "scene": m.scene is not None, "arts": arts, "missing": moves.missing(m, root),
                "have": not moves.missing(m, root), "studio": studio.note(wallet.purchase(m.pid).data), "gen_prompt": moves.gen_prompt(m) if m in open_ and m.scene is None else ""}
    return {"sheet": moves.SHEET, "size": f"{moves.FRAMES * orders.CELL}×{orders.CELL}", "open": [row(m) for m in open_], "done": [row(m) for m in done]}


def admin_view(ctx: Game) -> dict | None:
    """管理者那一頁：還沒做完的訂單（等圖、待審）在前，最近做完的十張在後。每張寫下單的人、名字、樣子、十張到了哪幾張、
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
                "have": orders.present(root, orders.look_id(o.pid)), "studio": studio.note(wallet.purchase(o.pid).data), "prompts": orders.gen_prompts(o) if o in open_ else {}}
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
    return ctx._log([f"收到「{found.name}」的 {sheet}（{have}/{len(orders.SHEETS)}）" + ("，全套齊了，可以審核。" if now.status == orders.REVIEW else "。")])


def admin_studio_retry(ctx: Game, pid: int) -> list[str]:
    """管理者按「再畫一次」：畫坊停手的那一張訂單（形象或絕招）清掉停手，下一輪從缺的那一張重來。"""
    wallet = ctx._wallet()
    if wallet is None or not ctx.is_admin():
        return ctx._log(["（此刻無法這麼做。）"])
    if not studio.retry(wallet, pid):
        return ctx._log([f"（第 {pid} 號訂單畫坊沒有停手。）"])
    return ctx._log([f"第 {pid} 號訂單交回畫坊，下一輪重畫。"])


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


# ── 形象市集（第四批；market.py）─────────────────────────


def _made_names(ctx: Game, wallet) -> dict[str, str]:
    """全服做好了的自建形象：id → 名字。"""
    item = orders.item_of(ctx.content)
    return {} if item is None else {o.look: o.name for o in orders.every(wallet, item.id) if o.status == orders.MADE and o.look}


def settle(ctx: Game) -> list[str]:
    """把押滿了的市集分成入帳（看「形象」那一頁時順手結；入了寫一則「形象」江湖紀錄）。"""
    wallet, item = ctx._wallet(), market.item_of(ctx.content)
    if wallet is None or item is None or not rules.on(ctx.content) or ctx.state.player.bot:
        return []
    n = market.settle(wallet, item.id, ctx._mall_owner(), ctx.pill_now())
    if not n:
        return []
    line = market.SETTLED.format(n=n)
    journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 +{n}"]))
    return [line]


def market_view(ctx: Game) -> dict | None:
    """市集那一段：別人掛著的（我買過的、我自己的不列）、我做的每一套掛了沒、賣了幾份、分成入帳與押著的。"""
    wallet, item = ctx._wallet(), market.item_of(ctx.content)
    if wallet is None or item is None:
        return None
    owner = ctx._mall_owner()
    names = _made_names(ctx, wallet)
    have = market.bought(wallet, owner)
    listed = {x["look"]: x for x in market.listings(wallet)}
    shelf = [{"look": x["look"], "name": names[x["look"]], "seller": wallet.character_name(x["seller"]) or x["seller"], "price": x["price"]}
             for x in listed.values() if x["seller"] != owner and x["look"] in names and x["look"] not in have]
    mine = [{"look": look, "name": name, "price": listed[look]["price"] if look in listed else None}
            for look, name in market.made_by(wallet, owner).items()]
    return {"shelf": shelf, "mine": mine, "min": market.PRICE_MIN, "max": market.PRICE_MAX, "default": market.PRICE_DEFAULT,
            "share": market.SHARE, "hold_days": market.HOLD_DAYS, "paid_only": ctx.content.config.mall.market_paid_only,
            **market.earnings(wallet, item.id, owner)}


def market_list(ctx: Game, look: str, price: int) -> list[str]:
    wallet = ctx._wallet()
    if wallet is None or market.item_of(ctx.content) is None or not rules.on(ctx.content):
        return ctx._log([market.NOT_OPEN])
    done, line = market.list_look(wallet, ctx._mall_owner(), look, price)
    if done:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line]))
    return ctx._log([line])


def market_unlist(ctx: Game, look: str) -> list[str]:
    wallet = ctx._wallet()
    if wallet is None or market.item_of(ctx.content) is None or not rules.on(ctx.content):
        return ctx._log([market.NOT_OPEN])
    return ctx._log([market.unlist_look(wallet, ctx._mall_owner(), look)[1]])


def market_buy(ctx: Game, look: str, ref: str) -> list[str]:
    """買市集上的一套（假人不買）：成了寫一則「形象」江湖紀錄。"""
    wallet = ctx._wallet()
    if wallet is None or market.item_of(ctx.content) is None or not rules.on(ctx.content) or ctx.state.player.bot:
        return ctx._log([market.NOT_OPEN])
    found = market.listing(wallet, look)
    seller = (wallet.character_name(found["seller"]) or found["seller"]) if found else ""
    pid, line = market.buy(ctx.content, wallet, ctx._mall_owner(), look, ref, names=_made_names(ctx, wallet), seller_name=seller,
                           now=ctx.pill_now(), day=ctx._pill_day(), season=ctx.world.get_season_number())
    if pid is not None:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=TITLE, lines=[line], changes=[f"元寶 -{found['price']}"]))
    return ctx._log([line])
