"""本週卡「你這一步」（畫面叫「眼下要事」）的候選與目標（減法季整合設計 6.1；批 3c 那一半是計畫 Task 3c-3；全部拆包第 36 批改成掛鉤）。

畫面只有一份「你這一步」：main.week_card.steps（weekcard._steps 叫 items 組候選、finish 補目標與輪轉）。候選照核心的「你這一步」順序表
（core/features.py 的 STEP_ORDER：託付 → 委託 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠）一格一格叫（items）：各包登記自己那一格
（Feature.steps()：人物情誼的託付、軍情的軍令與伏筆、新手引導的新手目標、陣營的去投靠），還沒成包的懸賞榜兩格（委託、揭了的懸賞）由這裡
代叫（_STEP_CORE，第 45 批）；每一件 {"kind", "text", …}，要補目標的掛一個 _ref。四勝利開著的季（on）這裡替每一件補（finish：照 _ref 的
第一個字找回寫它的那一格、叫那一格的 place）：
- target：要去的地點 {"location", "name", "minutes"}（走過去的現實分鐘，Game.place_minutes；就在那裡 0、走不到 null）；沒有地點是 null；
- id：哪一道軍令、哪一張懸賞或委託、哪一條伏筆、哪一條新手目標、投靠哪一方；
- then：護糧軍令還沒接糧車時（target 是起點）多這一個，糧車要送到的終點 {"location", "name"}：輿圖把兩點都框進畫面（Joy 2026-10-31）；

並照「換一件事」（step:next，Game.choose 先接走、不在選單上）今天按了幾次從那一件排起（PlayerState.step_day／step_skip，pill_day 換日從頭）。
關著的季 weekcard 一個字都不變（finish 只拿掉 weekcard 內部的 _ref）。只讀，skip 只改那兩個欄位。

核心本體（全部拆包第 36 批收進 MODULES）：不 import 功能包；懸賞榜兩格在叫的那一下才 import 舊模組 bounties（過渡：待搬，第 45 批）。
- scripts/test_for.py：改這個檔跑核心測試＋煙霧＋自己檔名的 tests/bots/test_step.py（NOT_CORE_TESTS：改別的核心模組不多跑它）。
  STEP_ORDER 的先後由核心契約 tests/core/test_contract_core.py 逐字鎖住（核心測試，會跟著跑）。
- 不寫 step 檔名的混合檔 test_for 挑不到，另外跑（-n 4，不含 slow）：tests/map/test_weekcard.py、tests/core/test_chapters.py、
  tests/figures/test_week_unlock.py、tianxia/features/companions/tests/test_errands_weekcard.py、tianxia/features/guide/tests/test_opening.py；
  slow 的 tianxia/features/faction/tests/test_sides_card.py、tests/web/test_week_card_web.py 要跑就 --slow。
- 反過來也挑不到（第 36 批審查）：test_for 碰到核心模組就不往上找，bounties 又是在函式裡才 import（不算進依賴），所以改 step、weekcard
  依賴的舊模組時上面那一串（加 tests/bots/test_step.py）多半挑不到。第 45 批之前改 bounties.py 另跑 tests/bots/test_step.py
  （test_bounty_newbie_and_join_get_their_places、test_errand_and_foreshadow_get_their_places 釘住委託、懸賞兩格）、
  tests/map/test_weekcard.py；改 chapters.py、atlas.py、orders.py、figures.py、seal_acts.py 少挑哪幾個見
  docs/superpowers/plans/2026-11-06-你這一步-第36批.md 第六節。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core import features as features_core
from tianxia.core.features import StepHook

from .rules import jianfa

if TYPE_CHECKING:
    from .engine import Game

NEXT = "step:next"  # 「換一件事」：不在選單上（假人碰不到），Game.choose 先接走
REF = "_ref"  # weekcard._steps 掛在每一件上、給 finish 找目標的內部鍵；送出去之前一定拿掉


def on(game: Game) -> bool:
    """這一季「你這一步」有批 3c 那一半：四勝利開著（減法季的總開關＋開季的章），季還沒收。"""
    w = game.state.world
    return jianfa(game.content, w) and not w.ended


def place(game: Game, loc_id: str | None) -> dict | None:
    """目標地點：{"location", "name", "minutes"}；不是地圖上的地點是 None。"""
    if loc_id is None or loc_id not in game.content.locations:
        return None
    return {"location": loc_id, "name": game.content.locations[loc_id].name, "minutes": game.place_minutes(loc_id)}


def skipped(game: Game) -> int:
    """今天按了幾次「換一件事」（隔天從 0 算）。"""
    p = game.state.player
    return p.step_skip if p.step_day == game._pill_day() else 0  # noqa: SLF001


def items(game: Game, status: dict, orders: list[dict]) -> list[dict]:
    """「你這一步」的候選（weekcard._steps 叫）：照 core/features.py 的 STEP_ORDER 一格一格叫 items(game, status, orders)，照順序接起來
    （包登記的格與這裡代叫的懸賞榜兩格，_STEP_CORE）。status、orders 是殼算好傳進來的那一份（Game.status_data()、Game.orders_view()），不重算。"""
    out: list[dict] = []
    for hook in features_core.step_table(_STEP_CORE):
        out += hook.items(game, status, orders)
    return out


def finish(game: Game, items: list[dict]) -> list[dict]:
    """weekcard._steps 排好的那一串：每一件拿掉 _ref；四勝利開著時補 target（沒有地點是 null）與 id，再照今天換了幾次從那一件排起。
    已經帶了 target 的那一件照留（人物的託付：errands.step_items 自己寫好 id 與 target、沒有 _ref，減法季批 6）。
    補目標照 _ref 的第一個字找回寫它的那一格的 place（core/features.py 的 StepHook；step_places），回 (id, target, then)。"""
    live = on(game)
    places = features_core.step_places(_STEP_CORE) if live else {}
    out = []
    for item in items:
        ref = item.pop(REF, None)
        if live and "target" not in item:
            fill = places.get(ref[0]) if ref else None
            ident, target, then = fill(game, ref) if fill is not None else (None, None, None)
            item["target"] = target
            if ident is not None:
                item["id"] = ident
            if then is not None and target is not None:
                item["then"] = then
        out.append(item)
    k = skipped(game) % len(out) if live and out else 0
    return out[k:] + out[:k]


def skip(game: Game) -> list[str]:
    """「換一件事」：今天換的次數 +1（隔天重來）；本週卡的 steps 就從下一件排起。規則關著什麼都不做。不花體力、不寫江湖紀錄，回空的。"""
    if not on(game):
        return []
    p, day = game.state.player, game._pill_day()  # noqa: SLF001
    p.step_skip = (p.step_skip if p.step_day == day else 0) + 1
    p.step_day = day
    return []


# core_step（全部拆包第 36 批）：「你這一步」由核心代叫的兩格（懸賞榜還沒成包）。每一格在叫的那一下才 import bounties、照模組屬性找函式。
def _commission_items(status: dict) -> list[dict]:
    """懸賞列裡的委託（書信附的、人物的求援；bounties.status 組的 commission 列）：接在人物的託付後面、軍令前面。"""
    return [{"kind": "errand", "text": f"{b['title']}：{b['how']}", "who": b.get("issuer", ""), "reward": b.get("reward", ""),
             REF: ("errand", b.get("id"))} for b in status.get("bounties") or [] if b.get("commission")]


def _bounty_items(status: dict) -> list[dict]:
    """手上揭了、還沒做完的懸賞（不是委託、沒有 have）：接在軍令後面、伏筆前面。"""
    return [{"kind": "bounty", "text": f"{b['title']}：{b['how']}", "reward": b.get("reward", ""), REF: ("bounty", b.get("id"))}
            for b in status.get("bounties") or [] if not b.get("commission") and not b.get("have")]


def _bounty_place(game: Game, ref: tuple) -> tuple:
    """懸賞列上的那一張（懸賞榜的、人物的委託與求援）：(id, target, None)；找不到 (ref[1], None, None)。"""
    from tianxia import bounties  # noqa: PLC0415  過渡：待搬（第 45 批：懸賞榜包登記 commission、bounty 兩格）

    s, c = game.state, game.content
    pool = [*bounties.open_commissions(s, c), *bounties.rallies(s, c), *s.world.bounties]
    b = next((x for x in pool if x.id == ref[1]), None) if ref[1] else None
    if b is None:
        return ref[1], None, None
    return b.id, place(game, b.end if b.kind == "escort" else b.location if b.kind in ("strike", "scout") else None), None


_STEP_CORE: dict[str, StepHook] = {
    "commission": StepHook("commission", lambda ctx, status, orders: _commission_items(status), ref="errand",
                           place=lambda ctx, ref: _bounty_place(ctx, ref)),  # 過渡：待搬（第 45 批）
    "bounty": StepHook("bounty", lambda ctx, status, orders: _bounty_items(status), ref="bounty",
                       place=lambda ctx, ref: _bounty_place(ctx, ref)),  # 過渡：待搬（第 45 批）
}
