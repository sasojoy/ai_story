"""商城（docs/superpowers/specs/2026-10-20-商城架構-design.md）：元寶、商品、購買與發貨、月卡、封測發放、管理者工具的規則。
功能包 tianxia/features/mall/ 的純規則（開發規範手冊 3.2；原本是 tianxia/mall.py，那一個名字留成指到這裡的別名）。

- 開關 Config.mall.enabled（on）：關著時什麼都不做、不讀不寫資料庫（月卡不加上限），呼叫端照舊。
- 商品寫在 content/mall.json（joy 寫），效果只能從允許的效果表 EFFECTS 挑（4.3：用允許表不用禁止表）；載入時 content.check_mall
  叫 item_problems 擋表外的。外觀、通行證的種類留著，允許表裡還沒有它們的效果，所以這一版寫不出來。
- 錢包的讀寫在 tianxia/wallet.py；這裡只排順序與寫字。一次購買：查重 → 上架 → 限購 → 餘額 → 寫購買紀錄 → 扣元寶 → 發貨，
  呼叫端（伺服器的行動鎖）是一筆交易，出錯整筆撤回（4.4）。
- 不讀時鐘：現實時間 now 與回體丹的那一天 day（Game._pill_day）都由呼叫端傳進來。

新寫給玩家看的字都待 joy 潤。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from tianxia import calendar, naming
from tianxia import library  # 過渡：待搬（功法庫上限 cap_of，開發規範手冊 3.10）
from tianxia.characters import name_key
# 票的庫存、月卡加的上限、哪一件賣這種效果搬進核心的錢包服務（開發規範手冊 3.10）；這裡照舊叫得到（mall.tokens……）
from tianxia.core.services import CARD_KEY, card_bonus, item_for, look_ids, tokens  # noqa: F401
from tianxia.models import Content, MallItem
from tianxia.state import GameState
from tianxia.wallet import Wallet


@dataclass(frozen=True)
class EffectSpec:
    kind: str  # 這個效果屬於哪一種商品（MallItem.kind）
    label: str  # 寫給玩家看的那一句；{n} 是數量、{pill} 是回體丹的名字、{bonus} 是月卡多幾顆
    max: int  # 一件商品最多寫多少


# 允許的效果表（4.3）：回體丹、月卡、月卡當場回的元寶、重修列傳。要加新的效果先改這張表、再上架；外觀、通行證開了才會有它們的效果
# （Joy 2026-10-21：外觀不做）。月卡每天領的那一份不是商品的效果，寫在 Config.mall（card_daily_*），買哪一張卡都一樣。
EFFECTS: dict[str, EffectSpec] = {
    "pills": EffectSpec("consumable", "{pill} {n} 顆", 999),
    "card_days": EffectSpec("card", "月卡 {n} 天（每天多服 {bonus} 顆{pill}{daily}）", 366),
    "card_rebate": EffectSpec("card", "當場回 {n} 元寶", 100000),  # 月卡買下當場拿回的元寶（定案甲：600 回 300）；要比價錢少
    "zhuan_rewrite": EffectSpec("consumable", "列傳多重寫 {n} 次", 9),  # 重修列傳：休季時列傳多重寫幾次（Config.biography.rewrites 之外）
    "rename": EffectSpec("consumable", "易名帖 {n} 張", 1),  # 易名帖：買了得一張帖，在設定頁改名、當場生效（rename.py）
    # 功法庫擴充：武學與意境合計的持有上限多幾格（PlayerState.holding_bonus），買下當場生效、只這一季（Joy 2026-10-21 一張 15 格、不限張數）
    "holding": EffectSpec("consumable", "功法庫多放 {n} 格（這一季）", 999),
    # 破境丹（Joy 2026-10-21「把破境丹也加入商城，取消可以用心得衝」）：收進行囊（PlayerState.legend_items），到了極處服下強行衝關
    "legend": EffectSpec("consumable", "{legend} {n} 顆", 99),
    # 重悟帖（Joy 2026-10-21「弄個商城道具可以直接重骰，有上限」）：自創成形之後直接重骰一次（PlayerState.create_rerolls，換季帶著走；一門最多 Config.arts.create_reroll_cap 次）
    "create_reroll": EffectSpec("consumable", "自創重骰 {n} 次", 99),
    # 列傳為終點的四件（減法季批 7b，整合設計第九章；zhuan_end.py）：都不改角色，購買那一列就是票（同重修列傳）。插畫、紀念印、
    # 親筆評曰休季時按鈕用掉（data 記 used、season，親筆評曰另記 fid）；深交名額不用按，只算買的那一季（tokens(season=)）
    "zhuan_art": EffectSpec("consumable", "列傳插畫 {n} 張（休季時用）", 1),
    "zhuan_seal": EffectSpec("consumable", "紀念印 {n} 方（休季時用）", 1),
    "zhuan_quote": EffectSpec("consumable", "人物親筆評曰 {n} 張（休季時挑人物）", 1),
    "deep_slot": EffectSpec("consumable", "深交名額 +{n}（這一季）", 1),
    # 題壁墨（走一趟，Joy 2026-10-29～30「任意留言需要消耗商城道具」「題壁墨都先只能元寶買」）：不改角色，那一列購買就是一張；
    # 走完一趟自己寫一句時用掉一張（data 記 used、place、inscription；outing.INK）。換季也帶著走
    "inscribe": EffectSpec("consumable", "題壁墨 {n} 張", 99),
    # 擂台形象（功能包 looks；Joy 2026-10-31「預設形象就是斗笠小子」、買的東西不能不見）：商品的 look 寫哪一套，購買那一列的 data 記
    # look_id，那一列就是這一套（帳號的，換季也帶著走）；穿哪一套在萬寶閣的「形象」那一頁換
    "look": EffectSpec("look", "擂台形象一套（換季也帶著走）", 1),
}
TICKET_NAMES = {"zhuan_art": "列傳插畫", "zhuan_seal": "紀念印", "zhuan_quote": "人物親筆評曰", "deep_slot": "深交名額", "inscribe": "題壁墨"}  # 退款那一句
KIND_NAMES = {"look": "形象", "consumable": "消耗品", "card": "月卡", "pass": "通行證"}
REASONS = {"grant": "封測發放", "buy": "購買", "refund": "退款", "reissue": "補發", "revoke": "扣回", "topup": "儲值"}
# 月卡的元寶照舊記成 grant（帳本的原因有 CHECK，加原因要改結構；不改結構版本），照編號的開頭認是月卡的哪一份：
# 當場回的 card:rebate:<購買 id>、每天領的 card:daily:<主人>:<日>；退款時扣回當場回的那一份 refund:rebate:<購買 id>（revoke）
CARD_REFS = {"card:rebate:": "月卡回饋", "card:daily:": "月卡每日", "refund:rebate:": "扣回月卡回饋"}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_EPOCH = date(1970, 1, 1)

TITLE = "商城"  # 江湖紀錄的標題（發放、購買）
# 以下都待 joy 潤
GRANT_LINE = "封閉測試期間，帳上先撥給你 {n} 元寶，可以到商城看看。"
OFF = "商城沒有開。"
NO_ITEM = "沒有這件商品。"  # 沒上架的也回這一句（不露下一季、下一段日子要賣什麼）
DUPLICATE = "這一筆已經買好了：「{name}」。"
SHORT = "元寶不夠：「{name}」要 {price}，你有 {balance}。"
SHORT_MANY = "元寶不夠：「{name}」×{n} 要 {price}，你有 {balance}。"
LIMIT_DAY = "「{name}」今天已經買了 {n} 次，明日 00:00 後再來。"
LIMIT_SEASON = "「{name}」這一季已經買了 {n} 次。"
LIMIT_ACCOUNT = "「{name}」每個帳號限買 {n} 次，已經買滿了。"
BOUGHT = "買下「{name}」：{effects}。元寶 -{price}（還剩 {left}）。"
BOUGHT_MANY = "買下「{name}」×{n}：每一件{effects}。元寶 -{price}（還剩 {left}）。"  # 一次買好幾件（Joy 2026-10-22）；字待 joy 潤
CLAMPED = "（限購只剩 {n} 件，就買 {n} 件。）"  # 選的數量比限購剩的多：照剩的買；字待 joy 潤
MAX_QTY = 99  # 一次最多選幾件（網頁的數量框也照它）
CARD_UNTIL = "月卡到 {day}"  # 江湖紀錄的變化：卡用到哪一天（含）
# 管理者工具（4.7）：只有管理者看得到
NEED_NOTE = "（要寫原因：每一筆都會記進帳。）"
BAD_AMOUNT = "（元寶要寫正整數。）"
NEED_REF = "（這一筆沒有編號，沒有記帳。）"
REVOKE_SHORT = "（{name}只有 {balance} 元寶，扣不了 {n}：餘額不能是負的。）"
DONE_BEFORE = "（這個編號已經記過帳了，沒有再記一次。）"
REISSUED = "已替{name}補發 {n} 元寶（餘額 {left}）。"
REVOKED = "已從{name}扣回 {n} 元寶（餘額 {left}）。"
NO_PURCHASE = "（{name}沒有這一筆購買。）"
REFUNDED_BEFORE = "（這一筆已經退過了。）"
REFUNDED = "已退{name}的「{item}」：元寶 +{price}（餘額 {left}）。{took}"
PILLS_BACK = "{pill}收回 {n} 顆。"
PILLS_USED = "用掉的 {n} 顆不追。"
HOLDING_UP = "功法庫上限 +{n}（現在 {cap} 格，這一季）"
HOLDING_BACK = "功法庫上限收回 {n} 格。"
REROLL_BACK = "重悟帖收回 {n} 張。"
CARD_BACK = "月卡少 {n} 天。"
TICKET_BACK = "{name}作廢。"  # 列傳的四件（批 7b）：退了那一列就不算票、用過的也不再畫
REBATE_BACK = "當場回的 {n} 元寶扣回。"
# 月卡每日領（定案甲）：待 joy 潤
DAILY_PART = "，每天領 {ingots} 元寶與 {pills} 顆{pill}"  # 效果那一句（月卡）多這一段
CLAIMED = "領了月卡今天的份：元寶 +{ingots}、{pill} +{pills}（元寶 {left}）。"
CLAIMED_BEFORE = "月卡今天的份已經領過了，明日 00:00 後再來。"
NO_CARD = "你沒有月卡，或月卡已經到期。"
NO_DAILY = "月卡沒有每天領的份。"
# 易名帖（rename.py）：待 joy 潤
NO_RENAME = "你手上沒有易名帖，先到萬寶閣買一張。"
RENAME_SAME = "新名號跟原本的一樣。"
RENAME_BUSY = "決戰或奪璽單挑還沒打完，先別改名。"
RENAME_ADMIN = "管理者的名號不能用易名帖改。"
RENAMED = "你從此改名「{new}」。"
RENAMED_CHRONICLE = "{old}改名{new}。"
# 擂台形象（功能包 looks）：待 joy 潤
LOOK_GOT = "形象「{name}」（到萬寶閣的「形象」換上）"
LOOK_OWNED = "你已經有「{name}」這一套形象了。"
LOOK_BACK = "形象「{name}」收回。"


@dataclass(frozen=True)
class Bought:
    item: MallItem
    lines: list[str]  # 回給玩家、寫進江湖紀錄的那一句
    changes: list[str]  # 江湖紀錄的變化（元寶、拿到的東西）


def on(content: Content) -> bool:
    return content.config.mall.enabled


def grant_ref(owner: str) -> str:
    return f"grant:beta:{owner}"


def grant_beta(content: Content, wallet: Wallet, owner: str, now: float) -> int:
    """封測發放（4.2）：這個錢包還沒發過就發 Config.mall.beta_grant，回發了幾個；發過了、數字是 0、開關關著回 0。
    編號只看主人（grant:beta:<主人>），所以換季、再登入、換一份設定都不會再發一次。"""
    amount = content.config.mall.beta_grant
    if not on(content) or amount <= 0:
        return 0
    return amount if wallet.post(owner, amount, "grant", grant_ref(owner), time=now) else 0


def date_day(text: str) -> int:
    """台灣日期 YYYY-MM-DD → 回體丹那一套的日數（Game._pill_day：照台灣日期、從 1970-01-01 起算）。格式不對丟 ValueError。"""
    if not _DATE.fullmatch(text or ""):
        raise ValueError(text)
    return (date.fromisoformat(text) - _EPOCH).days


def day_text(day: int) -> str:
    """日數 → 「10/25」（台灣日期）。"""
    d = _EPOCH + timedelta(days=day)
    return f"{d.month}/{d.day}"


def daily_amounts(content: Content) -> tuple[int, int]:
    """月卡每天領的元寶與回體丹（Config.mall.card_daily_*）；兩個都是 0 是沒有這一份。"""
    m = content.config.mall
    return m.card_daily_ingots, m.card_daily_pills


def effects_text(item: MallItem, content: Content) -> str:
    """這件買了拿到什麼（照允許表的寫法，例「回體丹 5 顆」「月卡 30 天（每天多服 1 顆回體丹，每天領 60 元寶與 1 顆回體丹）」）。"""
    cfg = content.config
    ingots, pills = daily_amounts(content)
    daily = DAILY_PART.format(ingots=ingots, pills=pills, pill=cfg.stamina_pill_name) if ingots or pills else ""
    return "、".join(
        EFFECTS[key].label.format(n=n, pill=cfg.stamina_pill_name, bonus=cfg.mall.card_pill_bonus, daily=daily, legend=cfg.legend_item_name)
        for key, n in item.effects.items() if key in EFFECTS
    )


@dataclass(frozen=True)
class Moment:
    """上架看的「此刻」（減法季批 7b 的 MallWindow.rule、phases、from_week 用）：phase 是 season（籌備中、開打的季）或 resting（休季），
    week 是季曆第幾週（開打的季才有；籌備中、休季是 None），rules 是這一季（開季的章）開著的子開關名。呼叫端（Game._mall_moment）給；
    沒給（MOMENT）就是季中、不知道第幾週、子開關都不算：只有沒寫這三樣的商品照舊上架。
    segments：這一季的季曆照段（7 天濃縮季，calendar.week7_on）：說明裡的上架時機（{上架}）寫「第 5 天」不寫「第三週」（FB-849）。
    blocked：商品 id → 這個人這一季用不上的那一句（FB-845，例：沒投靠一方的人買不了列傳插畫）：貨架上那一列灰掉寫這一句、
    買也買不了（buy_problem）；沒有這個商品的鍵就是買得了。"""

    phase: str = "season"
    week: int | None = None
    rules: frozenset[str] = frozenset()
    segments: bool = False
    blocked: dict[str, str] = field(default_factory=dict)


MOMENT = Moment()
SLOTS = ("{上架}",)  # 商品說明（content/mall.json 的 note）裡照季換字的插槽：上架時機，note_text 填，item_problems 驗
_NUMERALS = "〇一二三四五六七八九十"


def _week_cn(n: int) -> str:
    return _NUMERALS[n] if 0 <= n <= 10 else "十" + _NUMERALS[n - 10] if 11 <= n < 20 else str(n)


def note_text(item: MallItem, content: Content, moment: Moment = MOMENT) -> str:
    """商品說明（FB-849）：{上架} 換成上架時機，讀 MallWindow.from_week、照這一季的季曆寫——7 天濃縮季的「週」是段，畫面上沒有第三週，
    寫這一段的第一天（calendar.segment_days，「第 5 天」）；其他季照舊「第三週」。沒有插槽的說明原樣不動。待 joy 潤。"""
    if "{上架}" not in item.note or item.on_sale.from_week is None:
        return item.note
    week = item.on_sale.from_week
    when = f"第 {calendar.segment_days(week, content)[0]} 天" if moment.segments else f"第{_week_cn(week)}週"
    return item.note.replace("{上架}", when)


def on_sale(item: MallItem, day: int, season: int, moment: Moment = MOMENT) -> bool:
    """這一天、這一季上不上架（MallWindow：季的清單空的是每一季；日期含頭尾、不寫是不限）。減法季批 7b：寫了 rule 的要那個子開關
    這一季開著；寫了 phases 的要此刻在那一段；寫了 from_week 的季中要到那一週（休季不看）。"""
    window = item.on_sale
    if window.seasons and season not in window.seasons:
        return False
    if window.start and day < date_day(window.start):
        return False
    if window.end and day > date_day(window.end):
        return False
    if window.rule is not None and window.rule not in moment.rules:
        return False
    if window.phases and moment.phase not in window.phases:
        return False
    return window.from_week is None or moment.phase == "resting" or (moment.week is not None and moment.week >= window.from_week)


def limit_problem(item: MallItem, wallet: Wallet, owner: str, day: int, season: int) -> str | None:
    """限購滿了的那一句；還能買是 None。數的是沒退的購買（Wallet.count）。"""
    limit = item.limit
    if limit.day is not None and wallet.count(owner, item.id, day=day) >= limit.day:
        return LIMIT_DAY.format(name=item.name, n=limit.day)
    if limit.season is not None and wallet.count(owner, item.id, season=season) >= limit.season:
        return LIMIT_SEASON.format(name=item.name, n=limit.season)
    if limit.account is not None and wallet.count(owner, item.id) >= limit.account:
        return LIMIT_ACCOUNT.format(name=item.name, n=limit.account)
    return None


def limit_left(item: MallItem, wallet: Wallet, owner: str, day: int, season: int) -> int | None:
    """限購還剩幾件（三種限購取最少的，不會是負的）；沒有限購是 None。"""
    limit, left = item.limit, []
    if limit.day is not None:
        left.append(limit.day - wallet.count(owner, item.id, day=day))
    if limit.season is not None:
        left.append(limit.season - wallet.count(owner, item.id, season=season))
    if limit.account is not None:
        left.append(limit.account - wallet.count(owner, item.id))
    return max(0, min(left)) if left else None


def buy_problem(item: MallItem, wallet: Wallet, owner: str, day: int, season: int, moment: Moment = MOMENT) -> str | None:
    """買不了的那一句（限購、這個人這一季用不上、元寶不夠）；買得了是 None。上架由呼叫端先看（on_sale）。
    限購排在「用不上」前面（FB-845：季中買了一張、休季才知道用不上，再按說的是限購）。"""
    problem = limit_problem(item, wallet, owner, day, season)
    if problem:
        return problem
    if item.look and item.look in look_ids(wallet, owner):
        return LOOK_OWNED.format(name=item.name)
    unfit = moment.blocked.get(item.id)
    if unfit:
        return unfit
    balance = wallet.balance(owner)
    return SHORT.format(name=item.name, price=item.price, balance=balance) if balance < item.price else None


def buy_ref(owner: str, ref: str) -> str:
    """購買的編號：帶上主人，兩個人送一樣的 ref 也不會撞在一起。"""
    return f"buy:{owner}:{ref}"


def buy(
    state: GameState, content: Content, wallet: Wallet, item_id: str, ref: str, *, now: float, day: int, season: int, qty: int = 1,
    moment: Moment = MOMENT,
) -> Bought | str:
    """買 qty 件（4.4；一次買好幾件，Joy 2026-10-22「應該可以一次買多個」）：查重 → 上架 → 限購 → 餘額 → 寫購買紀錄 → 扣元寶 → 發貨，
    全部在一筆交易裡（呼叫端開著就併進去）。qty 夾在 1～MAX_QTY、再夾在限購剩的件數裡（訊息照實際買的件數寫）；
    元寶不夠買這麼多件就整筆不買。每一件各記一筆購買與一筆帳（限購、退款、易名帖都照一件一筆數）：第一件的編號就是 ref
    （重送同一個查得到），第 k 件接「#k」。回字串是不成（或這個編號已經買過了）的那一句，什麼都沒寫；發貨途中丟例外整筆撤回。
    發貨先寫資料庫（月卡）、最後才動 state（回體丹），所以例外丟出來時 state 也還沒被改到。"""
    owner = name_key(state.player.name)
    full = buy_ref(owner, ref)
    with wallet.db.transaction():
        done = wallet.purchase_by_ref(full)
        if done is not None:
            known = content.mall.get(done.item)
            return DUPLICATE.format(name=known.name if known else done.item)
        item = content.mall.get(item_id)
        if item is None or not on_sale(item, day, season, moment):
            return NO_ITEM
        problem = buy_problem(item, wallet, owner, day, season, moment)
        if problem:
            return problem
        want = max(1, min(MAX_QTY, int(qty)))
        room = limit_left(item, wallet, owner, day, season)
        n = want if room is None else min(want, room)
        balance = wallet.balance(owner)
        if balance < item.price * n:
            return (SHORT_MANY.format(name=item.name, n=n, price=item.price * n, balance=balance) if n > 1
                    else SHORT.format(name=item.name, price=item.price, balance=balance))
        changes: list[str] = []
        for k in range(1, n + 1):
            unit = full if k == 1 else f"{full}#{k}"
            data = dict(item.effects) | ({"look_id": item.look} if item.look else {})  # 形象：那一列記是哪一套（商品下架了也認得）
            pid = wallet.add_purchase(owner, unit, item.id, item.price, time=now, day=day, season=season, data=data)
            if not wallet.post(owner, -item.price, "buy", unit, time=now, purchase_id=pid):
                raise RuntimeError(f"購買編號 {unit} 已經記過帳，購買紀錄卻沒有")  # 兩張表對不上：整筆撤回，不發貨
            changes += _deliver(state, content, wallet, owner, item, day, pid, now)
        left = wallet.balance(owner)
    effects = effects_text(item, content)
    if n == 1:
        line = BOUGHT.format(name=item.name, effects=effects, price=item.price, left=left)
    else:
        line = BOUGHT_MANY.format(name=item.name, n=n, effects=effects, price=item.price * n, left=left)
    if n < want:
        line += CLAMPED.format(n=n)
    return Bought(item=item, lines=[line], changes=[f"元寶 -{item.price * n}", *_merge(changes)])


def _merge(changes: list[str]) -> list[str]:
    """好幾件的變化併起來：「回體丹 +5」五次寫成「回體丹 +25」，括號裡那一段照最後一件（功法庫上限寫最後的格數）；
    沒有數字的（「月卡到 11/30」）同一個開頭只留最後一筆。照第一次出現的先後。"""
    out: dict[str, tuple[int | None, str]] = {}
    for change in changes:
        m = _CHANGE.match(change)
        if m:
            head, num, rest = m.group(1), int(m.group(2)), m.group(3)
            prev = out.get(head, (0, ""))[0] or 0
            out[head] = (prev + num, rest)
        else:
            out[change.split(" ", 1)[0]] = (None, change)
    return [f"{head} +{num}{rest}" if num is not None else rest for head, (num, rest) in out.items()]


_CHANGE = re.compile(r"^(.*?) \+(\d+)(.*)$")


def card_span(span: tuple[int, int] | None, day: int, days: int) -> tuple[int, int]:
    """月卡再加 days 天（4.5）：還沒到期（到期日在今天之後）就從到期日往後接，開始日不動；沒有或過期了從今天起算。"""
    if span is not None and span[1] > day:
        return span[0], span[1] + days
    return day, day + days


def _deliver(
    state: GameState, content: Content, wallet: Wallet, owner: str, item: MallItem, day: int, pid: int, now: float,
) -> list[str]:
    """發貨：月卡寫進 mall_entitlements（當場回的元寶記一筆帳 card:rebate:<購買>）、回體丹進角色（走拿到回體丹的那條路：手上的
    顆數加上去）；重修列傳不用發，那一筆購買就是一次（rewrite_tokens 數沒用掉的）。回江湖紀錄的變化。"""
    changes: list[str] = []
    days = item.effects.get("card_days", 0)
    if days:
        start, end = card_span(wallet.card(owner, CARD_KEY), day, days)
        wallet.set_card(owner, CARD_KEY, start, end)
        changes.append(CARD_UNTIL.format(day=day_text(end - 1)))
    rebate = item.effects.get("card_rebate", 0)
    if rebate:
        wallet.post(owner, rebate, "grant", f"card:rebate:{pid}", time=now, purchase_id=pid, note=CARD_REFS["card:rebate:"])
        changes.append(f"元寶 +{rebate}（{CARD_REFS['card:rebate:']}）")
    if item.effects.get("zhuan_rewrite", 0):
        changes.append(f"列傳重寫 +{item.effects['zhuan_rewrite']}")
    if item.effects.get("rename", 0):
        changes.append("易名帖 +1（到設定頁改名）")
    holding = item.effects.get("holding", 0)
    if holding:
        state.player.holding_bonus += holding
        changes.append(HOLDING_UP.format(n=holding, cap=library.cap_of(state, content)))
    pills = item.effects.get("pills", 0)
    if pills:
        state.player.stamina_pills += pills
        changes.append(f"{content.config.stamina_pill_name} +{pills}")
    legend = item.effects.get("legend", 0)
    if legend:
        state.player.legend_items += legend
        changes.append(f"{content.config.legend_item_name} +{legend}")
    rerolls = item.effects.get("create_reroll", 0)
    if rerolls:
        state.player.create_rerolls += rerolls
        changes.append(f"重悟帖 +{rerolls}")
    if item.look:
        look = content.looks.get(item.look)
        changes.append(LOOK_GOT.format(name=look.name if look else item.look))
    for key, name in TICKET_NAMES.items():  # 列傳的四件（批 7b）：不改角色，那一列購買就是票
        if item.effects.get(key, 0):
            changes.append(f"{name} +{item.effects[key]}")
    return changes


def real_text(now: float, content: Content) -> str:
    """現實時間 → 台灣時間「10/25 21:40」（購買紀錄與帳；不是季曆的時刻，所以不走 calendar.point_text）。"""
    offset = content.config.pill_day_utc_offset_hours
    moment = datetime.fromtimestamp(now, tz=timezone(timedelta(hours=offset)))
    return f"{moment.month}/{moment.day} {moment.hour:02d}:{moment.minute:02d}"


def card_view(content: Content, wallet: Wallet, owner: str, day: int) -> dict | None:
    """月卡此刻有沒有效：有效回 {until: 用到哪一天（含）, bonus: 多幾顆, left: 連今天還有幾天, daily: 今天的份}，其餘 None。
    daily 是 {ingots, pills, claimed: 今天領過了沒}；Config.mall 沒有每天領的份是 None。"""
    span = wallet.card(owner, CARD_KEY)
    if span is None or not span[0] <= day < span[1]:
        return None
    ingots, pills = daily_amounts(content)
    daily = {"ingots": ingots, "pills": pills, "claimed": wallet.has_ref(daily_ref(owner, day))} if ingots or pills else None
    return {"until": day_text(span[1] - 1), "bonus": content.config.mall.card_pill_bonus, "left": span[1] - day, "daily": daily}


def daily_ref(owner: str, day: int) -> str:
    """月卡每天那一份的編號：一個主人一天一個，所以同一天只領得到一次；沒領的那一天沒有這一筆，之後也補不回來（Joy：沒上線不補）。"""
    return f"card:daily:{owner}:{day}"


@dataclass(frozen=True)
class Claimed:
    lines: list[str]
    changes: list[str]


def claim_daily(state: GameState, content: Content, wallet: Wallet, *, now: float, day: int) -> Claimed | str:
    """領月卡今天的份（定案甲）：卡在期間裡、今天還沒領過才給；元寶記一筆帳（card:daily:<主人>:<日>，原因 grant），回體丹進角色。
    回字串是領不了的那一句，什麼都沒寫。先寫帳、最後才動 state（同 buy）。"""
    if not on(content):
        return OFF
    owner = name_key(state.player.name)
    ingots, pills = daily_amounts(content)
    if not ingots and not pills:
        return NO_DAILY
    with wallet.db.transaction():
        span = wallet.card(owner, CARD_KEY)
        if span is None or not span[0] <= day < span[1]:
            return NO_CARD
        ref = daily_ref(owner, day)
        if wallet.has_ref(ref):
            return CLAIMED_BEFORE
        # 元寶 0 也記一筆 0 的帳：編號就是「今天領過了」的記號
        wallet.post(owner, ingots, "grant", ref, time=now, note=CARD_REFS["card:daily:"])
        left = wallet.balance(owner)
    state.player.stamina_pills += pills
    pill = content.config.stamina_pill_name
    changes = ([f"元寶 +{ingots}"] if ingots else []) + ([f"{pill} +{pills}"] if pills else [])
    return Claimed(lines=[CLAIMED.format(ingots=ingots, pills=pills, pill=pill, left=left)], changes=changes)


def rewrite_tokens(wallet: Wallet, owner: str) -> list[int]:
    """重修列傳還沒用掉的那幾筆購買。"""
    return tokens(wallet, owner, "zhuan_rewrite")


def rename_tokens(wallet: Wallet, owner: str) -> list[int]:
    """易名帖還沒用掉的那幾筆購買。"""
    return tokens(wallet, owner, "rename")


def reason_text(reason: str, ref: str) -> str:
    """帳那一列的原因：月卡的那幾份照編號的開頭寫（CARD_REFS），其餘照 REASONS。"""
    for head, text in CARD_REFS.items():
        if ref.startswith(head):
            return text
    return REASONS.get(reason, reason)


def perks(item: MallItem, content: Content) -> list[str]:
    """月卡的好處一條一條（貨架那一張大卡與購買確認列的；定案甲）。待 joy 潤。"""
    cfg = content.config
    pill = cfg.stamina_pill_name
    out = []
    rebate = item.effects.get("card_rebate", 0)
    if rebate:
        out.append(f"買下當場拿回 {rebate} 元寶")
    ingots, pills = daily_amounts(content)
    if ingots or pills:
        out.append("每天上線領 " + "＋".join(([f"{ingots} 元寶"] if ingots else []) + ([f"{pill} {pills} 顆"] if pills else [])) + "（沒上線那天不補）")
    if cfg.mall.card_pill_bonus:
        out.append(f"每天能多服 {cfg.mall.card_pill_bonus} 顆{pill}")
    out.append(f"{item.effects.get('card_days', 0)} 天；再買從到期日往後接")
    return out


def limit_text(item: MallItem, wallet: Wallet, owner: str, day: int, season: int) -> str:
    """限購那一行（例「每天限 2 次（今天已買 1）」）；不限是空字串。待 joy 潤。"""
    limit, parts = item.limit, []
    if limit.day is not None:
        parts.append(f"每天限 {limit.day} 次（今天已買 {wallet.count(owner, item.id, day=day)}）")
    if limit.season is not None:
        parts.append(f"每季限 {limit.season} 次（這一季已買 {wallet.count(owner, item.id, season=season)}）")
    if limit.account is not None:
        parts.append(f"每個帳號限 {limit.account} 次（已買 {wallet.count(owner, item.id)}）")
    return "、".join(parts)


def view(content: Content, wallet: Wallet, owner: str, day: int, season: int, moment: Moment = MOMENT) -> dict:
    """商城那一頁的資料：餘額、月卡、這一刻上架的商品（照 content/mall.json 的順序；沒上架的不列）。每件寫買不買得了、
    為什麼、買了之後剩多少（購買確認用，4.6）；gives 是這件發什麼（允許表的鍵 → 數量）、card_to 是今天買的話月卡用到哪一天
    （含；不是月卡是 None）：購買確認寫「丹或月卡變成多少」用（商城第二批）。"""
    balance = wallet.balance(owner)
    span = wallet.card(owner, CARD_KEY)
    items = []
    for item in content.mall.values():
        if not on_sale(item, day, season, moment):
            continue
        why = buy_problem(item, wallet, owner, day, season, moment)
        days = item.effects.get("card_days", 0)
        room = limit_left(item, wallet, owner, day, season)
        # 一次最多買幾件（網頁的數量框，Joy 2026-10-22）：限購剩的、元寶買得起的、MAX_QTY 取最少；月卡一次一張（確認那一行寫用到哪一天）
        most = 0 if why else 1 if days else min(MAX_QTY, balance // max(1, item.price), MAX_QTY if room is None else room)
        items.append({
            "id": item.id, "name": item.name, "note": note_text(item, content, moment), "price": item.price, "kind": item.kind,
            "kind_name": KIND_NAMES[item.kind], "effects": effects_text(item, content),
            "limit": limit_text(item, wallet, owner, day, season), "can": why is None, "why": why, "after": balance - item.price + item.effects.get("card_rebate", 0),
            "gives": {key: n for key, n in item.effects.items() if key in EFFECTS},
            "card_to": day_text(card_span(span, day, days)[1] - 1) if days else None,
            "perks": perks(item, content) if days else [],
            "max": most,
            "look": item.look or None,  # 形象：哪一套（貨架那一格畫那一套站著的樣子）
        })
    ingots, pills = daily_amounts(content)
    daily = {"ingots": ingots, "pills": pills} if ingots or pills else None  # 月卡每天領的份（購買確認那一列）
    return {"balance": balance, "card": card_view(content, wallet, owner, day), "items": items, "daily": daily,
            "looks": bool(content.looks)}  # 有擂台形象（功能包 looks）：萬寶閣多一頁「形象」


def records(
    content: Content, wallet: Wallet, owner: str, *, admin: bool = False, season_time: Callable[[float], str | None] | None = None,
) -> dict:
    """購買紀錄與帳（最近 Config.mall.records_shown 筆，新的在前）；帳的每一列寫那一筆之後的餘額。admin 為真時多寫編號與
    經手的管理者（管理者查帳）；玩家自己看的不寫是誰經手。連著一筆購買的那幾列（購買、退款）寫商品的名字 item 與那一筆退了沒
    refunded（紀錄頁照它寫標題，商城第二批）；其餘 item 是 None。"""
    shown = content.config.mall.records_shown
    balance = wallet.balance(owner)
    after, ledger = balance, []
    for row in wallet.ledger(owner, shown):
        bought = wallet.purchase(row.purchase_id) if row.purchase_id is not None else None
        known = content.mall.get(bought.item) if bought is not None else None
        line = {"time": real_text(row.time, content), "season_time": season_time(row.time) if season_time else None, "delta": row.delta, "reason": reason_text(row.reason, row.ref),
                "note": row.note, "balance": after, "item": (known.name if known else bought.item) if bought is not None else None,
                "refunded": bought is not None and bought.refunded is not None}
        if admin:
            line.update(ref=row.ref, admin=row.admin, purchase=row.purchase_id)
        ledger.append(line)
        after -= row.delta
    purchases = []
    for bought in wallet.purchases(owner, shown):
        known = content.mall.get(bought.item)
        purchases.append({"id": bought.id, "time": real_text(bought.time, content), "item": known.name if known else bought.item,
                          "price": bought.price, "refunded": bought.refunded is not None})
    return {"balance": balance, "ledger": ledger, "purchases": purchases}


def adjust(
    wallet: Wallet, owner: str, shown: str, amount: int, reason: str, ref: str, *, now: float, admin: str, note: str,
) -> str:
    """管理者補發（reissue）或扣回（revoke）元寶（4.7）：原因必填、元寶是正整數、扣回不能扣到負的；回那一句（成了或不成）。
    ref 是這一筆的編號（伺服器產），同一個編號重送不會記兩次。"""
    note = (note or "").strip()
    if not note:
        return NEED_NOTE
    if not isinstance(amount, int) or amount <= 0:
        return BAD_AMOUNT
    if not ref:
        return NEED_REF
    with wallet.db.transaction():
        if reason == "revoke":
            balance = wallet.balance(owner)
            if balance < amount:
                return REVOKE_SHORT.format(name=shown, balance=balance, n=amount)
        if not wallet.post(owner, amount if reason == "reissue" else -amount, reason, f"admin:{ref}", time=now, admin=admin, note=note):
            return DONE_BEFORE
        left = wallet.balance(owner)
    return (REISSUED if reason == "reissue" else REVOKED).format(name=shown, n=amount, left=left)


def refund(
    state: GameState, content: Content, wallet: Wallet, purchase_id: int, *, now: float, admin: str, note: str,
    season: int | None = None,
) -> str:
    """管理者退一筆購買（4.7）：元寶照價錢全退；回體丹收回手上還有的（最多當初那幾顆，用掉的不追）；月卡把那一張的天數
    扣回去（那一張屬於已經過期的舊卡就不動現在這一張）。一筆只能退一次（編號 refund:<購買>）。state 是那個人的存檔，
    呼叫端存回去；回那一句（成了或不成）。"""
    owner = name_key(state.player.name)
    shown = state.player.name
    note = (note or "").strip()
    if not note:
        return NEED_NOTE
    bought = wallet.purchase(purchase_id)
    if bought is None or bought.owner != owner:
        return NO_PURCHASE.format(name=shown)
    if bought.refunded is not None:
        return REFUNDED_BEFORE
    took: list[str] = []
    with wallet.db.transaction():
        if not wallet.post(owner, bought.price, "refund", f"refund:{bought.id}", time=now, admin=admin, note=note,
                           purchase_id=bought.id):
            return REFUNDED_BEFORE
        wallet.mark_refunded(bought.id, now)
        days = int(bought.data.get("card_days", 0))
        span = wallet.card(owner, CARD_KEY)
        if days and span is not None and bought.day >= span[0]:
            wallet.set_card(owner, CARD_KEY, span[0], max(span[0], span[1] - days))
            took.append(CARD_BACK.format(n=days))
        rebate = int(bought.data.get("card_rebate", 0))
        if rebate and wallet.has_ref(f"card:rebate:{bought.id}"):  # 當場回的那一份扣回（退了全價，餘額一定夠：回饋比價錢少）
            wallet.post(owner, -rebate, "revoke", f"refund:rebate:{bought.id}", time=now, admin=admin,
                        note=CARD_REFS["refund:rebate:"], purchase_id=bought.id)
            took.append(REBATE_BACK.format(n=rebate))
        holding = int(bought.data.get("holding", 0))
        if holding and (season is None or bought.season == season):  # 上一季買的擴充換季時已經跟著歸零了，不動這一季的
            back = min(holding, state.player.holding_bonus)
            state.player.holding_bonus -= back
            took.append(HOLDING_BACK.format(n=back))
        pills = int(bought.data.get("pills", 0))
        if pills:
            back = min(pills, state.player.stamina_pills)
            state.player.stamina_pills -= back
            took.append(PILLS_BACK.format(pill=content.config.stamina_pill_name, n=back))
            if back < pills:
                took.append(PILLS_USED.format(n=pills - back))
        legend = int(bought.data.get("legend", 0))
        if legend:  # 破境丹：還在行囊裡的收回，服掉的不追（同回體丹）
            back = min(legend, state.player.legend_items)
            state.player.legend_items -= back
            took.append(PILLS_BACK.format(pill=content.config.legend_item_name, n=back))
            if back < legend:
                took.append(PILLS_USED.format(n=legend - back))
        rerolls = int(bought.data.get("create_reroll", 0))
        if rerolls:  # 重悟帖換季帶著走（同回體丹）：還在手上的收回，用掉的不追
            back = min(rerolls, state.player.create_rerolls)
            state.player.create_rerolls -= back
            took.append(REROLL_BACK.format(n=back))
        for key, name in TICKET_NAMES.items():  # 列傳的四件（批 7b）：退了那一列就不算票（沒用的不能用、用過的列傳不再畫、名額少一位）
            if bought.data.get(key):
                took.append(TICKET_BACK.format(name=name))
        if bought.data.get("look_id"):  # 形象：退了那一列就不算買到（正穿著的換回預設的斗笠小子，形象包讀的時候照 look_ids 看）
            look = content.looks.get(bought.data["look_id"])
            took.append(LOOK_BACK.format(name=look.name if look else bought.data["look_id"]))
        left = wallet.balance(owner)
    known = content.mall.get(bought.item)
    return REFUNDED.format(name=shown, item=known.name if known else bought.item, price=bought.price, left=left, took="".join(took))


def item_problems(item: MallItem, content: Content) -> list[str]:
    """一件商品哪裡寫錯（content.check_mall 用）；空的是可以上架。"""
    where = f"商城 {item.id}"
    out: list[str] = []
    if not item.effects:
        out.append(f"{where}：沒有效果")
    for key, n in item.effects.items():
        spec = EFFECTS.get(key)
        if spec is None:
            out.append(f"{where}：效果 {key} 不在允許的效果表裡（{'、'.join(EFFECTS)}）")
            continue
        if spec.kind != item.kind:
            out.append(f"{where}：效果 {key} 是{KIND_NAMES[spec.kind]}的，這件的種類寫{KIND_NAMES[item.kind]}")
        if not 1 <= n <= spec.max:
            out.append(f"{where}：{key} 的數量要 1～{spec.max}（寫了 {n}）")
    if item.kind == "look" or item.look:
        if item.look not in content.looks:
            out.append(f"{where}：形象要寫 content/looks.json 裡的一套（寫了「{item.look}」）")
        if item.effects != {"look": 1}:
            out.append(f"{where}：形象的效果只寫 {{\"look\": 1}}（寫了 {item.effects}）")
    if item.effects.get("card_rebate", 0) >= item.price:
        out.append(f"{where}：當場回的元寶（{item.effects['card_rebate']}）要比價錢（{item.price}）少")
    if item.effects.get("card_rebate") and not item.effects.get("card_days"):
        out.append(f"{where}：card_rebate 要跟 card_days 寫在同一張月卡上")
    problem = naming.name_problem(item.name, content)
    if problem:
        out.append(f"{where}：名字「{item.name}」{problem}")
    window = item.on_sale
    days: list[int] = []
    for text in (window.start, window.end):
        if text is None:
            continue
        try:
            days.append(date_day(text))
        except ValueError:
            out.append(f"{where}：上架日期要寫 YYYY-MM-DD（寫了 {text}）")
    if window.start and window.end and len(days) == 2 and days[0] > days[1]:
        out.append(f"{where}：上架日期的開始（{window.start}）在結束（{window.end}）之後")
    if any(n < 1 for n in window.seasons):
        out.append(f"{where}：上架的季要是正整數（寫了 {window.seasons}）")
    if window.rule is not None and not isinstance(getattr(content.config.jianfa, window.rule, None), bool):
        out.append(f"{where}：上架的子開關 {window.rule} 不是 Config.jianfa 的子開關")
    for slot in re.findall(r"\{[^{}]*\}", item.note):  # 說明裡照季換字的插槽（FB-849）
        if slot not in SLOTS:
            out.append(f"{where}：說明裡不認得的插槽 {slot}（認得 {'、'.join(SLOTS)}）")
    if "{上架}" in item.note and window.from_week is None:
        out.append(f"{where}：說明寫了 {{上架}}，上架時段要寫 from_week")
    return out
