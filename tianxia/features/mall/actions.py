"""商城的動作（功能包 tianxia/features/mall/；原本是 Game 上的 mall_*、admin_mall_* 與幾個私有方法，開發規範手冊 3.2、3.10）。

ctx 是 Game（第一階）；只叫 tianxia/core/services.py 那張清單上的方法。Game.mall_* 留一行委派到這裡（server、測試照舊叫 Game）。
商城的兩個屬性 ctx.mall_bought、ctx.mall_already 還住在 Game 上（伺服器在鎖裡讀，見 routes.py）。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from tianxia import calendar
from tianxia import journal  # 核心（江湖紀錄，PM 10/31）：帶 changes 的那一則 ctx._write 寫不了
from tianxia import server_bots  # 過渡：待搬（保留的名號：易名帖撞名照建角色）
from tianxia import zhuan_end  # 過渡：待搬（這一季用不上的列傳插畫票不賣，FB-845）
from tianxia.accounts import NAME_TAKEN as NAME_IN_USE, AccountStore
from tianxia.characters import CharacterStore, name_key
from tianxia.core.services import NO_SUCH_PLAYER
from tianxia.rules import jianfa
from tianxia.state import GameState, JournalEntry, Rumor
from tianxia.wallet import Wallet

from . import rename
from . import rules as mall

if TYPE_CHECKING:
    from tianxia.engine import Game


def grant(ctx: Game) -> None:
    """封測發放（mall.grant_beta）：這個錢包還沒發過就發，寫一則「商城」江湖紀錄。own_turn_checks 叫。"""
    wallet = ctx._wallet()
    if wallet is None:
        return
    amount = mall.grant_beta(ctx.content, wallet, ctx._mall_owner(), ctx.now)
    if amount:
        journal.add_entry(ctx.state, JournalEntry(
            time=ctx.state.world.time, title=mall.TITLE, lines=[mall.GRANT_LINE.format(n=amount)], changes=[f"元寶 +{amount}"],
        ))


def buy(ctx: Game, item_id: str, ref: str, qty: int = 1) -> list[str]:
    """買一件商品（mall.buy）：ref 是這一次購買的編號（網頁按下確認那一刻產，重送同一個不會買兩次）。成了寫一則「商城」
    江湖紀錄（變化寫元寶與拿到的東西）；不成、或這個編號已經買過了只回一句、不寫紀錄。伺服器在行動鎖裡叫：扣元寶、
    寫購買紀錄、發貨同一筆交易。時間照回體丹那一套（pill_now、_pill_day），不讀時鐘。買成了 ctx.mall_bought 記那件的 id，
    不成（含這個編號已經買過了）是 None；這個編號已經買過了 ctx.mall_already 記那一筆的商品 id（FB-491），其餘是 None。
    qty 是一次買幾件（Joy 2026-10-22），照 mall.buy 夾在限購剩的件數裡。"""
    ctx.mall_bought = ctx.mall_already = None
    wallet = ctx._wallet()
    if wallet is None:
        return ctx._log([mall.OFF])
    result = mall.buy(
        ctx.state, ctx.content, wallet, item_id, ref,
        now=ctx.pill_now(), day=ctx._pill_day(), season=ctx.world.get_season_number(), qty=qty, moment=moment(ctx),
    )
    if isinstance(result, str):
        done = wallet.purchase_by_ref(mall.buy_ref(ctx._mall_owner(), ref))
        ctx.mall_already = done.item if done is not None else None
        return ctx._log([result])
    journal.add_entry(ctx.state, JournalEntry(
        time=ctx.state.world.time, title=mall.TITLE, lines=result.lines, changes=result.changes,
    ))
    ctx.mall_bought = result.item.id
    return ctx._log(result.lines)


def moment(ctx: Game) -> mall.Moment:
    """上架看的「此刻」（減法季批 7b：MallWindow 的 rule、phases、from_week）：休季或季中、開打的季是季曆第幾週、這一季（開季的章）
    開著哪幾個商品寫到的子開關；segments 是這一季的季曆照不照段（7 天濃縮季），商品說明的上架時機（{上架}）照它寫（FB-849）；
    blocked 是這個人這一季用不上的商品 → 原因（現在只有列傳插畫票，zhuan_end.art_problem；FB-845）：貨架灰掉、買不了。
    沒寫這三樣的商品不看它，一個字都不變。"""
    c, w = ctx.content, ctx.state.world
    phase = ctx.world.season_phase()
    rules_named = {item.on_sale.rule for item in c.mall.values() if item.on_sale.rule}
    rules = frozenset(part for part in rules_named if jianfa(c, w, part))
    blocked: dict[str, str] = {}
    if "zhuan_end" in rules and (unfit := zhuan_end.art_problem(ctx.state, c, w)):  # 這一季用不上的插畫票不賣（FB-845）
        blocked.update({item.id: unfit for item in c.mall.values() if item.effects.get(zhuan_end.ART)})
    return mall.Moment(
        phase="resting" if phase == "resting" else "season",
        week=calendar.point(w.time, c, w).week if phase == "running" and not w.ended else None,
        rules=rules, segments=calendar.week7_on(w, c), blocked=blocked,
    )


def entry(ctx: Game) -> dict | None:
    """狀態列的商城入口（齒輪旁的錠子鈕、底部第六格；商城第二批）：{balance}；商城關著是 None（沒有入口）。
    江湖畫面每次都送，所以只讀餘額（帳的加總），不排商品。"""
    wallet = ctx._wallet()
    if wallet is None:
        return None
    owner = ctx._mall_owner()
    card = mall.card_view(ctx.content, wallet, owner, ctx._pill_day())
    # 月卡今天的份（定案甲）：卡有效、有每天領的份才有這個鍵；江湖頁照它畫「月卡・今日份」小卡（領過了收起）
    daily = card["daily"] if card is not None else None
    names = len(mall.rename_tokens(wallet, owner))  # 手上的易名帖：設定頁照它畫改名那一格（沒有不送這個鍵）
    return {"balance": wallet.balance(owner), **({"daily": daily} if daily is not None else {}), **({"rename": names} if names else {})}


def rename_left(ctx: Game) -> int:
    """手上還沒用掉的易名帖幾張（設定頁照它畫改名那一格）；商城關著是 0。"""
    wallet = ctx._wallet()
    return 0 if wallet is None else len(mall.rename_tokens(wallet, ctx._mall_owner()))


def rename_self(ctx: Game, new: str, taken: Callable[[str], bool] | None = None) -> list[str]:
    """易名帖：改自己的名號，當場生效（Joy 2026-10-21 決策卡「當場生效」；rename.py）。new 是伺服器量過長度、去過看不見的字元的；
    taken 是伺服器的「名號有人用」（角色、帳號、保留的名號同一句話，不洩漏誰是假人），沒給（測試、腳本）照角色表與保留名號查。
    成了：資料庫裡名號當身分的地方一起換（world.rename_character）、自己的存檔照新名號存、用掉一張帖、江湖史一行、一則「商城」紀錄。
    不成只回一句、什麼都不動。呼叫端要拿著行動鎖（server 的 act）。"""
    wallet = ctx._wallet()
    if wallet is None:
        return [mall.OFF]
    p = ctx.state.player
    old = p.name
    left = mall.rename_tokens(wallet, ctx._mall_owner())
    if not left:
        return [mall.NO_RENAME]
    if p.bot is not None or ctx.is_admin():
        return [mall.RENAME_ADMIN]
    if new == old:
        return [mall.RENAME_SAME]
    if taken is None:
        store = CharacterStore(ctx.world.db)
        reserved = {n.casefold() for n in server_bots.reserved_names(ctx.content)}
        taken = lambda n: store.exists(n) or n.casefold() in reserved  # noqa: E731
    if name_key(new) != name_key(old) and taken(new):
        return [NAME_IN_USE]
    if rename.clash(old, name_key(old), ctx.content) or rename.clash(new, name_key(new), ctx.content):
        return [rename.CLASHED]
    shared = ctx.world.read()
    live = shared.model_dump_json(include={"seal_duels"}) + (shared.active_battle.model_dump_json() if shared.active_battle else "")
    if f'"{old}"' in live or f'"{name_key(old)}"' in live:
        return [mall.RENAME_BUSY]
    ctx._save_season()  # 先把這一次同步動到的季寫回去，改名照資料庫那一份換
    ctx.world.rename_character(old, new)
    mapping = {old: new, name_key(old): name_key(new)}
    ctx.state = GameState.model_validate(rename.swap(ctx.state.model_dump(mode="json"), mapping))
    ctx._reconcile_season()
    wallet.mark_used(left[0], ctx.pill_now())
    ctx.state.world.chronicle.append(Rumor(time=ctx.state.world.time, text=mall.RENAMED_CHRONICLE.format(old=old, new=new)))
    line = mall.RENAMED.format(new=new)
    journal.add_entry(ctx.state, JournalEntry(
        time=ctx.state.world.time, title=mall.TITLE, lines=[line], changes=[f"名號 {old} → {new}"],
    ))
    ctx._save_season()
    CharacterStore(ctx.world.db).save(ctx.state)
    ctx.touched.update(n for n in CharacterStore(ctx.world.db).names() if n != new)  # 別人的分頁也重抓（他們存檔裡的名字換了）
    return ctx._log([line])


def claim(ctx: Game) -> list[str]:
    """領月卡今天的份（mall.claim_daily；Joy 2026-10-21 定案甲・每日領）：成了寫一則「商城」江湖紀錄，不成只回一句。
    一天照回體丹那一套（_pill_day，台灣 00:00 換日）；沒上線那一天不補（編號一天一個，過了那天就領不到）。"""
    wallet = ctx._wallet()
    if wallet is None:
        return ctx._log([mall.OFF])
    result = mall.claim_daily(ctx.state, ctx.content, wallet, now=ctx.pill_now(), day=ctx._pill_day())
    if isinstance(result, str):
        return ctx._log([result])
    journal.add_entry(ctx.state, JournalEntry(
        time=ctx.state.world.time, title=mall.TITLE, lines=result.lines, changes=result.changes,
    ))
    return ctx._log(result.lines)


def view(ctx: Game) -> dict | None:
    """商城那一頁的資料（mall.view）；商城關著是 None。另附貨架上面兩張小卡與購買確認要的回體丹（pills：名字、手上幾顆、
    今天還能服幾顆〔不限是 None〕、一天上限〔含月卡；0 是不限〕、一顆回多少、月卡多幾顆）與封測發了多少（grant，商城第二批）。"""
    wallet = ctx._wallet()
    if wallet is None:
        return None
    data = mall.view(ctx.content, wallet, ctx._mall_owner(), ctx._pill_day(), ctx.world.get_season_number(), moment(ctx))
    cfg = ctx.content.config
    data["pills"] = {
        "name": cfg.stamina_pill_name, "count": ctx.state.player.stamina_pills, "today": ctx.pills_left_today(),
        "cap": ctx.pill_cap(), "restore": cfg.stamina_pill_restore, "bonus": cfg.mall.card_pill_bonus,
    }
    data["grant"] = cfg.mall.beta_grant
    return data


def records(ctx: Game) -> dict | None:
    """自己的購買紀錄與帳（mall.records，不寫經手的管理者）；商城關著是 None。"""
    wallet = ctx._wallet()
    return None if wallet is None else mall.records(ctx.content, wallet, ctx._mall_owner(), season_time=lambda real: _season_stamp(ctx, real))


def _season_stamp(ctx: Game, real: float) -> str | None:
    """帳上那一筆（現實時間）在這一季的季曆是幾時（全面自檢 U-12：元寶是真錢、照舊寫現實時間，旁邊多寫季曆）。
    照現在的賽季時鐘倒推（暫停過的那一段不扣，差一點無妨）；這一季開始以前的與休季不寫。"""
    world = ctx.state.world
    if world.ended:
        return None
    at = world.time - max(0.0, ctx.now - real) * ctx.content.config.time_scale
    return ctx.stamp(at) if at >= 0 else None


# ── 管理者（商城架構設計 4.7；帳跟季無關：籌備中、休季、暫停中都做得了）──


def _admin(ctx: Game, action: str) -> tuple[Wallet | None, str | None]:
    """管理者商城工具的共同檢查：(錢包, None)，或 (None, 拒絕的那一句)。"""
    if not ctx.is_admin():
        return None, f"（只有管理者能{action}。）"
    wallet = ctx._wallet()
    return (None, mall.OFF) if wallet is None else (wallet, None)


def _target(ctx: Game, wallet: Wallet, text: str) -> tuple[str, str] | None:
    """管理者填的名號或帳號 → (錢包的主人, 名號)。先照角色找（真人假人一樣），再照帳號找它綁的角色；都沒有是 None。"""
    text = (text or "").strip()
    if not text:
        return None
    shown = wallet.character_name(name_key(text))
    if shown is not None:
        return name_key(text), shown
    account = AccountStore(ctx.world.db).get(text)
    if account is None or account.character is None:
        return None
    shown = wallet.character_name(name_key(account.character))
    return None if shown is None else (name_key(account.character), shown)


def _adjust(ctx: Game, name: str, amount: int, note: str, ref: str, reason: str) -> list[str]:
    wallet, refusal = _admin(ctx, "補發元寶" if reason == "reissue" else "扣回元寶")
    if refusal:
        return ctx._log([refusal])
    target = _target(ctx, wallet, name)
    if target is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=(name or "").strip())])
    owner, shown = target
    msg = mall.adjust(wallet, owner, shown, amount, reason, ref, now=ctx.now, admin=ctx.state.player.name, note=note)
    if not msg.startswith("（"):
        ctx._write("商城", [msg], tag="管理者")
    return ctx._log([msg])


def admin_reissue(ctx: Game, name: str, amount: int, note: str, ref: str) -> list[str]:
    """管理者替某個名號（或帳號）補發元寶（4.7）：原因必填、寫進帳（誰、何時、為什麼）；ref 是這一筆的編號（伺服器產）。"""
    return _adjust(ctx, name, amount, note, ref, "reissue")


def admin_revoke(ctx: Game, name: str, amount: int, note: str, ref: str) -> list[str]:
    """管理者從某個名號（或帳號）扣回元寶（4.7）：餘額不能是負的。"""
    return _adjust(ctx, name, amount, note, ref, "revoke")


def admin_refund(ctx: Game, name: str, purchase_id: int, note: str) -> list[str]:
    """管理者退一筆購買（mall.refund）：元寶全退、收回手上還有的回體丹、月卡扣回天數；改到的存檔存回去（_save_target）。"""
    wallet, refusal = _admin(ctx, "退購買")
    if refusal:
        return ctx._log([refusal])
    target = _target(ctx, wallet, name)
    game = None if target is None else ctx._admin_target(target[1])
    if game is None:
        return ctx._log([NO_SUCH_PLAYER.format(name=(name or "").strip())])
    msg = mall.refund(
        game.state, ctx.content, wallet, purchase_id, now=ctx.now, admin=ctx.state.player.name, note=note,
        season=ctx.world.get_season_number(),
    )
    ctx._save_target(game)
    if not msg.startswith("（"):
        ctx._write("商城", [msg], tag="管理者")
    return ctx._log([msg])


def admin_ledger(ctx: Game, name: str) -> dict:
    """管理者查某個名號（或帳號）的帳（4.7）：{name, balance, card, ledger, purchases}，帳多寫編號與經手的管理者；
    不是管理者、商城關著、查不到回 {refusal}。真人假人回的一模一樣（不寫帳號）。只讀。"""
    wallet, refusal = _admin(ctx, "查帳")
    if refusal:
        return {"refusal": refusal}
    target = _target(ctx, wallet, name)
    if target is None:
        return {"refusal": NO_SUCH_PLAYER.format(name=(name or "").strip())}
    owner, shown = target
    data = mall.records(ctx.content, wallet, owner, admin=True)
    return {"name": shown, "balance": data["balance"], "card": mall.card_view(ctx.content, wallet, owner, ctx._pill_day()),
            "ledger": data["ledger"], "purchases": data["purchases"]}
