"""名帖（Joy 2026-10-19：「優化對他抱拳改成互贈名帖，新增製作名帖功能，要新製作名帖才能跟人交換，名帖製作是一張畫布可以讓玩家創作
當作他的標籤，名帖中會有一些 title，系統自動產生，點擊按鈕刷新……有一點像是我們傳記的超濃縮」；「製作名帖要花錢好像很過分，
然後名帖要留空間讓玩家可以自己留一句話」）。設計稿 https://claude.ai/artifact/YLTXjaX77DJRsCmMX57xAi（Joy「照建議」）。

一張名帖（state.Mingtie）：筆劃（墨、朱砂、石青三色、細粗兩種筆，畫布 300×400，存的是一筆一筆的點，不收圖片）、
頭銜（引擎照他這一路做過的事算出來的那一串裡挑 MingtieTuning.titles 個；earned）、自題一句（speech 擋髒話）。
不花錢、不給任何數值；照次數擋洗版（一天定稿幾次、一天遞幾張、同一個人只能換一次，之後再遞是換新帖）。
交換走玩家卡上的邀請（invites，kind "mingtie"）：遞名帖 → 對方回帖才兩邊各收一張（MingtieCopy，存遞出那一刻的樣子）。
檢舉與撤下記在全服的 SharedWorldState（mingtie_reports、mingtie_removed、mingtie_cleared），不分季；看得到看不到只問 shown。
純規則：只動傳進來的狀態；誰在不在、存檔、紀錄由 Game 做（engine 的「名帖」那一段）。"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from . import arena, calendar, library, ranks, renown, tactics
from .characters import name_key
from .models import Content
from .state import GameState, Mingtie, MingtieCopy

if TYPE_CHECKING:
    from .world_state import SharedWorldState

WIDTH, HEIGHT = 300, 400
INKS = ("#24211d", "#b23a2a", "#2f5d78")  # 墨、朱砂、石青（畫布固定是紙色，不跟深淺色走）
INK_NAMES = ("墨", "朱砂", "石青")
PENS = (3, 10)  # 細筆、粗筆

NO_CARD = "先做一張名帖"  # 待 joy 潤
MADE_FULL = "今天已定稿 {n} 次，明日 00:00 後再改。"
SENT_FULL = "今天已遞了 {n} 張名帖，明日 00:00 後再遞。"
SAME_CARD = "已經跟{him}換過這一張了"
WAITING = "等{him}回帖"
BAD_DRAWING = "（這張畫讀不出來，再畫一次。）"
BAD_TITLE = "（頭銜要從你掙到的那幾個裡挑。）"
EMPTY = "（名帖上什麼都沒有：畫幾筆、挑幾個頭銜，或寫一句話。）"
MADE = "名帖定稿了。"
REMOVED_LINE = "你的名帖被撤下了：畫與自題那一句都清掉了，頭銜照留。可以再做一張。"  # 待 joy 潤
REPORTED = "已檢舉。這一張你不會再看到；管理者會看。"


def key(name: str, version: int) -> str:
    return f"{name_key(name)}|{version}"


# ── 筆劃 ──


def parse_strokes(raw, content: Content) -> list[list[int]] | None:
    """客戶端送來的筆劃：[[墨色, 筆粗, x0, y0, x1, y1, …], …]。格式不對、超過筆數或點數、座標出了畫布，回 None。"""
    cfg = content.config.mingtie
    if not isinstance(raw, list) or len(raw) > cfg.max_strokes:
        return None
    out, points = [], 0
    for stroke in raw:
        if not isinstance(stroke, list) or len(stroke) < 4 or len(stroke) % 2:
            return None
        try:
            ink, pen, *xy = (int(v) for v in stroke)
        except (TypeError, ValueError):
            return None
        if not (0 <= ink < len(INKS) and 0 <= pen < len(PENS)):
            return None
        if any(not (0 <= v <= (WIDTH if i % 2 == 0 else HEIGHT)) for i, v in enumerate(xy)):
            return None
        points += len(xy) // 2
        if points > cfg.max_points:
            return None
        out.append([ink, pen, *xy])
    return out


# ── 一天幾次（照回體丹換日）──


def roll_day(state: GameState, day: int) -> None:
    p = state.player
    if p.mingtie_day != day:
        p.mingtie_day, p.mingtie_made, p.mingtie_sent = day, 0, 0


def made_left(state: GameState, content: Content, day: int) -> int:
    roll_day(state, day)
    return max(0, content.config.mingtie.made_per_day - state.player.mingtie_made)


def sent_left(state: GameState, content: Content, day: int) -> int:
    roll_day(state, day)
    return max(0, content.config.mingtie.send_per_day - state.player.mingtie_sent)


# ── 頭銜（全由引擎照存檔算，不叫模型；真人假人同一套來源）──


def _board_titles(state: GameState, board: dict | None) -> list[str]:
    """榜單：這一季前十名寫「某某榜第N」（榜單由呼叫端給：伺服器的快取 boards_now、假人自己掃一次；沒給就沒有這幾個）。"""
    if not board:
        return []
    from .leaderboard import BOARDS  # noqa: PLC0415  leaderboard → team → …，延後 import

    me, out = name_key(state.player.name), []
    for kind, label, _ in BOARDS:
        if kind == "擂台":
            continue  # 擂台的名次已經是擂台稱號（天下第一、擂台三甲、擂台十傑），不再寫一次
        rows = board.get(kind) or []
        for i, row in enumerate(rows[:10]):
            if name_key(row[0]) == me:
                out.append(f"{label}第{_cn(i + 1)}")
                break
    return out


def _cn(n: int) -> str:
    digits = "〇一二三四五六七八九"
    return "十" if n == 10 else digits[n]


def earned(state: GameState, content: Content, world=None, board: dict | None = None) -> list[str]:
    """這個人此刻掙得到的頭銜（照順序、不重複）：名聲兩個稱號、陣營與頭銜、擂台稱號、榜單名次、決戰首功、絕學、
    本命武學是誰親傳、神器與本命兵器、情誼最深的人物、名望最高的帖友，再加上過去幾季記下的（title_book）。
    world 是 WorldStateStore（解武學的名字用不到，留著給之後的頭銜）；沒有的那幾樣就不寫。"""
    p, c = state.player, content
    out: list[str] = []
    out += renown.titles(state, c)
    factions = {f.id: f.name for f in c.scenario.factions}
    faction = factions.get(p.faction) if p.faction else None
    rank = ranks.title(c, state)
    if faction:
        out.append(f"{faction}・{rank}" if rank else faction)
    if p.sect and p.sect in c.sects:
        out.append(f"{c.sects[p.sect].name}門下")
    if arena.on(c):
        ring = arena.title_of(state.world, p.name)
        if ring:
            out.append(ring)
    out += _board_titles(state, board)
    if p.top_merits:
        out.append(f"決戰首功{_count(p.top_merits)}次")
    mastered = sum(1 for art_id in library.owned_arts(state) if p.art_quality.get(art_id) == "絕學")
    if mastered:
        out.append(f"練成絕學{_count(mastered)}門")
    owned = set(library.owned_arts(state))
    for ch in c.characters.values():  # 只認本命（tactics.figure_arts）：基礎吐納、書生劍這種同伴起始帶的學來的武學不是誰親傳的（FB-640）
        if set(tactics.figure_arts(c, ch)) & owned:
            out.append(f"{ch.name}親傳")
    for item in [p.weapon, p.armor, *p.rack]:
        if item is None:
            continue
        if item.signature and item.signature in c.characters:
            out.append(f"{c.characters[item.signature].name}的本命兵器")
        elif item.original and item.secret and "無名" not in item.name:
            out.append(f"神器【{item.name}】之主")
    close = sorted(((v, cid) for cid, v in p.affinities.items() if v >= 60 and cid in c.characters), reverse=True)
    if close:
        out.append(f"{c.characters[close[0][1]].name}的知交")
    friends = sorted(p.mingtie_box, key=lambda x: (-x.fame, x.when))
    if friends:
        out.append(f"{friends[0].name}的帖友")
    out += p.title_book
    seen, uniq = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _count(n: int) -> str:
    return _cn(n) if 0 < n <= 10 else str(n)


def season_book(state: GameState, content: Content, season: int, board: dict | None = None) -> list[str]:
    """換季時記進 title_book 的：這一季掙到的頭銜裡值得留名的（名聲、擂台、榜單、首功、絕學、神器），前面寫第幾季。"""
    keep = earned(state.model_copy(update={"player": state.player.model_copy(update={"title_book": [], "mingtie_box": []})}),
                  content, board=board)
    lasting = [t for t in keep if not t.endswith("的知交") and not t.endswith("門下") and "・" not in t]
    return [f"第{season}季 {t}" for t in lasting]


def pick(pool: list[str], n: int, seed: str) -> list[str]:
    """假人挑 n 個頭銜：照名號雜湊排。"""
    ranked = sorted(pool, key=lambda t: hashlib.sha256(f"{seed}|{t}".encode()).hexdigest())
    return ranked[:n]


# ── 交換 ──


def copy_of(state: GameState, name: str) -> MingtieCopy | None:
    k = name_key(name)
    return next((x for x in state.player.mingtie_box if name_key(x.name) == k), None)


def given(state: GameState, other: str) -> int:
    """你上次遞給他的是你的第幾版（0＝沒換過）。"""
    mine = copy_of(state, other)
    return 0 if mine is None else mine.gave


def file_copy(receiver: GameState, giver: GameState, content: Content, gave: int) -> None:
    """把 giver 此刻的名帖收進 receiver 的名帖匣（同一個人只留最新的一張，排到最後），gave 是 receiver 這一次遞出的是第幾版。"""
    p, card = receiver.player, giver.player.mingtie
    if card is None:
        return
    k = name_key(giver.player.name)
    p.mingtie_box = [x for x in p.mingtie_box if name_key(x.name) != k]
    loc = content.locations.get(receiver.player.location)
    p.mingtie_box.append(MingtieCopy(
        name=giver.player.name, card=card.model_copy(deep=True), when=calendar.stamp_text(receiver.world.time, content, receiver.world),
        place=loc.name if loc else "", season=p.season_number, fame=giver.player.stats.get("fame", 0), gave=gave,
    ))
    cap = content.config.mingtie.box_cap
    if len(p.mingtie_box) > cap:
        p.mingtie_box = p.mingtie_box[-cap:]


# ── 檢舉與撤下（全服）──


def shown(shared: SharedWorldState | None, name: str, version: int, viewer: GameState | None, content: Content) -> bool:
    """這一張（某人第幾版）看不看得到：管理者撤下過的不畫、你自己檢舉過的不畫、被檢舉滿 report_hide 次而管理者還沒放回的不畫。"""
    k = key(name, version)
    if viewer is not None and k in viewer.player.mingtie_hidden:
        return False
    if shared is None:
        return True
    if shared.mingtie_removed.get(name_key(name), 0) >= version:
        return False
    return k in shared.mingtie_cleared or len(shared.mingtie_reports.get(k, [])) < content.config.mingtie.report_hide


def report(shared: SharedWorldState, name: str, version: int, reporter: str) -> None:
    k = key(name, version)
    who = shared.mingtie_reports.setdefault(k, [])
    if name_key(reporter) not in who:
        who.append(name_key(reporter))


def pending_reports(shared: SharedWorldState, content: Content) -> list[tuple[str, int, int]]:
    """管理者要看的：被檢舉過、還沒撤下也還沒放回的（名號鍵, 版本, 幾個人檢舉），檢舉多的在前。"""
    out = []
    for k, who in shared.mingtie_reports.items():
        nk, _, v = k.rpartition("|")
        version = int(v)
        if k in shared.mingtie_cleared or shared.mingtie_removed.get(nk, 0) >= version:
            continue
        out.append((nk, version, len(who)))
    return sorted(out, key=lambda r: (-r[2], r[0]))


def wipe(card: Mingtie) -> Mingtie:
    """管理者撤下：畫與自題清掉，頭銜照留；版本 +1（新的一版是乾淨的，照畫）。"""
    return Mingtie(strokes=[], titles=list(card.titles), motto="", version=card.version + 1)


# ── 畫面 ──


def view(card: Mingtie | None) -> dict | None:
    if card is None:
        return None
    return {"strokes": card.strokes, "titles": card.titles, "motto": card.motto, "version": card.version}


def blank_view(card: Mingtie) -> dict:
    """看不到的那一張（被檢舉藏起來、撤下）：照樣有頭銜，畫與那一句不給。"""
    return {"strokes": [], "titles": card.titles, "motto": "", "version": card.version, "hidden": True}


# ── 假人 ──


def bot_card(state: GameState, content: Content, pool: list[str]) -> Mingtie:
    """假人的名帖：照名號雜湊挑一張現成的畫（有時多幾筆），頭銜挑 titles 個，自題一半從句庫挑、一半留空。
    真人也能挑同一批現成的畫、也有很多人不寫那一句，所以看不出來。"""
    seed = int(hashlib.sha256(f"名帖|{state.player.name}".encode()).hexdigest(), 16)
    arts, mottos = content.mingtie.arts, content.mingtie.mottos
    strokes = [list(s) for s in arts[seed % len(arts)].strokes] if arts else []
    if strokes and (seed >> 8) % 3 == 0:  # 三個裡有一個在畫上加一筆朱砂的落款
        x, y = 30 + (seed >> 16) % 60, 330 + (seed >> 24) % 40
        strokes.append([1, 1, x, y, x + 2, y + 1])
    motto = mottos[(seed >> 32) % len(mottos)] if mottos and (seed >> 40) % 2 == 0 else ""
    titles = pick(pool, content.config.mingtie.titles, state.player.name)
    return Mingtie(strokes=strokes, titles=titles, motto=motto, version=1)
