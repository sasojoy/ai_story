"""回體丹（核心本體；第二輪第 80 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第80批.md，導覽 docs/guide/行動與地盤.md「體力」）：
服一顆、一天的上限、測試期間的一鍵補滿、讀檔補丹。原本是 Game 上的 6 個方法，本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3），函式名拿掉開頭的底線，
Game 留 5 個一行委派（server 的 pill 路由、假人的 bot.take_pill、序章、狀態列、商城、測試與 Game 原位在叫；只有這裡叫的 refill_stamina 不留）。
模組層的 REFILL_TITLE、REFILL_LINE、REFILL_FULL、REFILL_HUT、PILL_DAY_FULL、_cn_count 由 engine 照名字 import 回去（tests/bots/test_stamina_refill.py、test_pill_per_day.py 從 engine 拿）。

take_stamina_pill 的 @_not_while_preparing 留在 Game 的委派上，這裡不掛：裝飾器看的是 Game，換掉 Game.take_stamina_pill 的腳本（measure_sanren、sim_season_one）照舊蓋住同一層。

哪些經 ctx（手冊第十五節「換掉的才打得到」；tests/core/boundary_tables.py 的 PILLS_VIA_CTX 守）：
- 被腳本換掉的 take_stamina_pill 模組裡沒有人互叫，都經委派，打得到。其他互叫直接叫函式：take_stamina_pill → refill_stamina、pills_left_today、pill_cap；pills_left_today → pill_cap。
- 包的委派（CORE_DELEGATE_CALLERS）：take_stamina_pill → _note_action（序章服丹，新手引導）、top_up_pills → _top_up_line（讀檔補丹那一行的字）。
- 留在 Game 上的：state、content、now、advanced_real、_pill_day、_pill_card_bonus、_guide、_log、_write。
  _pill_day、_day_of、_pill_card_bonus 第二輪總表沒列，留原位（_pill_day 40 個檔 98 處在叫，scripts/measure_arena_crowd.py 在物件上換它）；Game._pill_day 照舊叫 self.pill_now()，走委派。

engine 在 `from .core import pushing` 之後才 import 這一份（這裡 import 的模組那時都已經載入，載入順序不變）。同 event_check 不進 MODULES、不進 FEATURES；這裡不 import 包。

改這一份要跑的測試：
- scripts/test_for.py：這個檔在 CORE_SERVICES。hunk 落在函式、類別、常數上 → 名字的功能群＋這個檔的底（檔名有 pill、stamina 的，量到 7 個檔）＋邊界測試；函式以外或指名了卻沒有差 → 核心測試＋煙霧。
  pill_cap 另外寫到的 test_mall、test_wallet 留閘門。
- same_behavior：compare --tracks surge（這一批開的一軌：滿的、兩顆、今天服滿、五顆與十一顆的字、不限、沒有丹、新手期、一鍵補滿、序章三步、讀檔補丹、假人服丹），其餘經 strip、aftermath、tavern、switchboard。
- 假人的路：tianxia/bot.py 的 take_pill（pills_left_today、take_stamina_pill(pill_only=True)）、bot_policy.py 叫 bot.take_pill、features/guide/actions.py 序章服丹。
- 反方向（第 36 批認定第 1 條）：這裡 import 的模組都是核心或共用層，test_for.pick 在搬之前、之後挑的一樣，沒有少挑到的，不必另外跑。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import journal, roster
from .. import prologue as prologue_rules
from ..state import JournalEntry

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）

# 測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07）。以下四句與鈕上的字（Config.beta_free_refill_label）全是新寫的，待 joy 潤：
REFILL_TITLE = "補滿體力"  # 江湖紀錄那一則的標題（joy 的丹是「服下回體丹」）
REFILL_LINE = "你運了口氣，體力回滿了。"  # 補滿成功時寫進紀錄的那一句
REFILL_FULL = "體力是滿的，用不著補。"  # 體力本來就是滿的：跟丹的「這時候服丹是糟蹋」一樣，只回一句話、不寫紀錄
PILL_DAY_FULL = "今天已服{n}顆，明日 00:00 後再服。"  # 回體丹一天的上限（企劃者 2026-10-12）
CN_COUNTS = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def _cn_count(n: int) -> str:
    return CN_COUNTS.get(n, str(n))


REFILL_HUT = "草廬裡先照師父說的做，體力等出了草廬再補。"  # 序章裡不能補（序章的體力是照步驟算好的），跟丹的「出了草廬再吃」同一個道理


def top_up_pills(ctx) -> None:
    """拿掉一鍵補滿之後補回體丹（企劃者 2026-10-12；見 PlayerState.pills_topped_to）：讀檔那一刻，贈送的數比上次補到的多，
    手上不到那個數就補到那個數、江湖紀錄寫一行。真人、假人、整季機器人一樣（假人看不出來）。"""
    cfg, p = ctx.content.config, ctx.state.player
    target = cfg.beta_gift_stamina_pills if cfg.beta_gift else 0
    if target <= p.pills_topped_to:
        return
    p.pills_topped_to = target
    if p.stamina_pills >= target:
        return
    added = target - p.stamina_pills
    p.stamina_pills = target
    ctx._write(cfg.stamina_pill_name, [ctx._top_up_line(added)])


def take_stamina_pill(ctx, *, pill_only: bool = False) -> list[str]:
    """服一顆回體丹（企劃者 2026-10-07）：體力回 stamina_pill_restore，夾在上限。沒有丹、體力是滿的、還在草廬序章裡
    （序章的體力是照步驟算好的：探索、合成、修練剛好用完，接著才教調息，prologue.start_stamina）、今天已經服滿
    （stamina_pills_per_day，pills_left_today）都只回一句話、不收丹。吃了才寫江湖紀錄（數值變化寫體力與丹）。
    測試期間 Config.beta_free_refill 打開時，同一個入口改成免費補滿（_refill_stamina），不收丹。pill_only 是給假人與
    整季機器人的：他們照舊只吃丹（bot.take_pill），不吃這份測試期間的免費補滿；開關關著時 pill_only 沒有作用。"""
    p, cfg = ctx.state.player, ctx.content.config
    hut_pill = prologue_rules.pills_open(ctx.state, ctx.content)  # 序章教服丹那一步起（新手引導重做）：照真的服一顆
    if cfg.beta_free_refill and not pill_only and not hut_pill:
        return refill_stamina(ctx)
    name = cfg.stamina_pill_name
    if p.stamina_pills <= 0:
        return ctx._log([f"你身上沒有{name}了。"])
    if prologue_rules.active(ctx.state, ctx.content) and not hut_pill:
        return ctx._log([f"草廬裡先照師父說的做，{name}留著出了草廬再吃。"])
    if pills_left_today(ctx) == 0:
        return ctx._log([PILL_DAY_FULL.format(n=_cn_count(pill_cap(ctx)))])
    if p.stamina >= cfg.stamina_max:
        return ctx._log(["體力是滿的，這時候服丹是糟蹋。"])
    before = p.stamina
    p.stamina = min(float(cfg.stamina_max), p.stamina + cfg.stamina_pill_restore)
    p.stamina_pills -= 1
    today = ctx._pill_day()
    p.pills_today = (p.pills_today if p.pill_day == today else 0) + 1
    p.pill_day = today
    msgs = [f"你服下一顆{name}，一股暖意自丹田散開，精神為之一振。"]
    journal.add_entry(ctx.state, JournalEntry(
        time=ctx.state.world.time, title=f"服下{name}", lines=msgs,
        changes=[f"體力 +{round(p.stamina - before)}", f"{name} -1"],
    ))
    p.guide_done = []
    rewards = ctx._guide(ctx._note_action("pill"))  # 序章「服一顆回體丹」（新手引導重做）
    return ctx._log(msgs + [f"體力 +{round(p.stamina - before)}（{name}還剩 {p.stamina_pills} 顆）"] + rewards)


def pill_now(ctx) -> float:
    """回體丹換日看的現實時間：sync 給的 now，加上 advance 推過的那一截（advanced_real）。"""
    return ctx.now + ctx.advanced_real


def pill_cap(ctx) -> int:
    """一天最多服幾顆：新手期照 newbie_pills_per_day（有寫才算），其餘照 stamina_pills_per_day；0 是不限。
    商城的月卡（錢包服務的 card_bonus）讓有上限的那一個多 Config.mall.card_pill_bonus 顆（平常 2→3、新手期 5→6）；不限照舊不限。"""
    cfg = ctx.content.config
    if cfg.stamina_pills_per_day > 0 and cfg.newbie_pills_per_day > 0 and roster.newbie(ctx.state, ctx.content):
        cap = cfg.newbie_pills_per_day
    else:
        cap = cfg.stamina_pills_per_day
    return cap if cap <= 0 else cap + ctx._pill_card_bonus()


def pills_left_today(ctx) -> int | None:
    """今天還能服幾顆回體丹（pill_cap）；不限是 None。不看手上有幾顆。"""
    cap = pill_cap(ctx)
    if cap <= 0:
        return None
    p = ctx.state.player
    return max(0, cap - (p.pills_today if p.pill_day == ctx._pill_day() else 0))


def refill_stamina(ctx) -> list[str]:
    """測試期間一鍵補滿體力（Config.beta_free_refill，企劃者 2026-10-07；take_stamina_pill 在開關打開時走這裡）：
    補到 stamina_max（狀態列顯示的那個上限），不收丹、不收銀兩、不限次數。規矩跟丹一模一樣：還在草廬序章裡、體力已經是滿的
    都只回一句話（不寫紀錄、不動東西）；籌備中由 take_stamina_pill 的 _not_while_preparing 擋；其餘不看——閉關中、
    在路上都照補、不動那個狀態（丹也不看 busy_until、journey）。補成了寫一則江湖紀錄（數值變化只寫體力，沒有丹的那一項）。"""
    p, cfg = ctx.state.player, ctx.content.config
    if prologue_rules.active(ctx.state, ctx.content):
        return ctx._log([REFILL_HUT])
    if p.stamina >= cfg.stamina_max:
        return ctx._log([REFILL_FULL])
    gained = f"體力 +{int(cfg.stamina_max) - int(p.stamina)}"  # 狀態列顯示 int(體力)：寫的數字就是條子實際走的那一段（體力有小數是常態）
    p.stamina = float(cfg.stamina_max)
    journal.add_entry(ctx.state, JournalEntry(
        time=ctx.state.world.time, title=REFILL_TITLE, lines=[REFILL_LINE], changes=[gained],
    ))
    return ctx._log([REFILL_LINE, gained])
