"""煉製與自創包的動作（全部拆包第 44 批）：原本 Game 上煉製頁開爐與自創五步的 16 個方法，Game 留一行委派給 server、假人、測試與核心原位、引導包。
計畫 docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md 1.1。第一個參數 ctx 是 Game（手冊 3.3）；叫回 Game 的只用 tianxia/core/services_list.md 那張清單上的；
這一包互相叫直接叫函式。規則照模組屬性叫（create.set_intent……：測試換掉模組上的，這裡照樣打得到）。

鎖外三段式（A 開單、B 叫模型、C 重驗）照舊：
- 開爐：A forge_request（鎖內、只讀）→ B server.prepare_forge（naming.generate，鎖外）→ C forge(proposed=...) 整個重驗；
  proposed 沒給（整季機器人、腳本、測試）時 fusion.merge 在鎖內用 ctx._quick_client()
- 立意：A intent_request → B routes.create_intent（create.read，鎖外）→ C intent；重讀同（reread_request／reread，B 叫 create.read_or_none）
B 段留在 server.py（鎖外工作的掛鉤是總表第 69 批）。

「forge」兩個意思：這一包的 forge* 是煉製頁的意境開爐；鐵匠鋪的打造（smith_forge、forge_plan、forge_secrets）不在這裡。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import fusion  # 共用規則層（合成與揣摩）
from tianxia import insight_fx, journal  # 共用規則層、核心
from tianxia import prologue as prologue_rules  # 共用規則層（序章只准照劇本合成）
from tianxia import renown  # 共用規則層（首創回饋補名望）
from tianxia.core.services import PREPARING_REFUSAL, not_while_preparing

from . import create, forge_view

if TYPE_CHECKING:
    from tianxia import naming
    from tianxia.engine import Game


# ── 開爐（煉製頁：兩個意境合成或揣摩）──


def forge_request(
    ctx: Game, art_id: str | None, insight_ids: list[str], named_outside: bool = False,
) -> naming.NamingRequest | None:
    """開爐首次取名或挑選的 A 段（呼叫端在行動鎖內、很快地呼叫；server.prepare_forge、bot_policy.tend_arts）：這一爐要不要模型？
    要就回送模型的單子（naming.NamingRequest），由呼叫端在鎖外交給 naming.generate（B 段），再進鎖把結果交給
    forge(..., proposed=...)（C 段）。單子有兩種：沒人合過、長新的 → 取名（choices 是空的）；合到舊的、候選兩個以上
    → 從候選挑一個（choices 是候選的名字，見 fusion.forge_request）。不要的時候是 None：這個 Game 沒有 client
    （例如伺服器假人鎖內的 Game）而且呼叫端不會自己叫模型、賽季籌備中、這一爐會被拒絕、配方已經有人登記、合到舊的而且
    只有一個候選。只讀、不改狀態——跟 dialogue_request 同一個做法。煉製只剩意境＋意境（Joy 2026-10-21），art_id 有就是 None。
    named_outside：呼叫端會在鎖外自己叫模型（伺服器假人程式：它的 Game 沒有 client，B 段用 bot_runner 自己的 client
    叫 naming.generate），照樣開單。"""
    if (ctx.client is None and not named_outside) or ctx._preparing():
        return None
    if art_id or prologue_rules.fuse_problem(ctx.state, ctx.content, insight_ids) is not None:
        return None  # 會被擋下的一爐：不開取名的單子（forge 照常回那句話）
    return fusion.forge_request(ctx.state, ctx.content, ctx.world, art_id, insight_ids)


@not_while_preparing
def forge(
    ctx: Game, art_id: str | None, insight_ids: list[str], proposed: tuple[str | None, str] | None = None,
    pour: bool = False, intent: str | None = None,
) -> list[str]:
    """煉製頁的開爐：只剩兩個意境（不同的＝合成、同一種的兩份＝揣摩；見 fusion.py）。武學＋武學、武學＋意境 Joy 2026-10-21
    拿掉了：art_id 有就回 ART_IN_FURNACE（意境到修練頁裝進武學的槽）。
    proposed 是鎖外先取好的（名字, 說明）（C 段，見 forge_request）：這裡整個重驗（A 段之後意境可能熔掉、心得或體力
    可能花掉、配方可能被別人或同一個人的另一個請求登記了），名字再過一次過濾、登記時原子判斷重名，過不了走退路字表；
    給了 proposed 就不會在這裡叫模型（伺服器與假人程式一律給，不需要模型時是 (None, "")）。沒給（整季機器人、腳本、測試）
    首次出現的配方照舊在這裡叫模型，那是在行動鎖內，所以用 _quick_client 的短逾時複本，取不到名字就走退路字表。
    江湖紀錄的標題照煉製頁寫「煉製」（FB-047），做成了才寫，被拒絕只回一句話、什麼都不收。
    合成花心得與體力（設計 12.1）：花了的體力跟心得一起寫在這一則的數值變化上。"""
    ctx.forged = False
    ctx.forged_thing = None
    ctx.secret_solved = None
    if art_id or len(insight_ids) != 2:
        return ctx._log([fusion.ART_IN_FURNACE if art_id else fusion.TWO_INSIGHTS])
    refusal = prologue_rules.fuse_problem(ctx.state, ctx.content, insight_ids)  # 序章只准照劇本合成
    if refusal is not None:
        return ctx._log([refusal])
    xinde, stamina = ctx._xinde(), ctx.state.player.stamina
    solved = ctx._solved_secrets()
    mixed = insight_fx.base_id(insight_ids[0]) != insight_fx.base_id(insight_ids[1])  # 兩種不同的意境（合成；同一種是揣摩）
    insight, msgs = fusion.merge(ctx.state, ctx.content, ctx.world, ctx._quick_client(), *insight_ids, proposed=proposed, intent=intent, pour=pour)
    tag = f"合併「{insight.name}」" if insight is not None else None
    if insight is not None:
        ctx.forged_thing = ("ins", insight.id)
        if mixed:
            ctx.state.player.newbie_marks.add("merge")  # 新手目標：在煉製合出一個新的意境
    out = ctx._log(msgs)
    ctx.forged = tag is not None
    if tag is not None:
        ctx._save_season()  # 首創秘方會記一則傳聞（fusion._secret_lines）；傳聞在共用賽季裡，要存回去
        spent = round(stamina - ctx.state.player.stamina)  # 三種合成都花體力：數值變化寫在紀錄上，跟修練一樣
        out += ctx._menxia_entry(  # 結果那一句（第一則訊息）也寫進這一則的敘事，拿到新東西的那一行才配得到 journal._NEW_THING（FB-073）
            tag, xinde, guide=True, title=journal.CRAFT, extra=[f"體力 -{spent}"] if spent > 0 else None,
            lines=out[:1],
        )
        ctx._note_solved(solved)
    return out


@not_while_preparing
def infuse(ctx: Game, body: str, others: list[str]) -> list[str]:
    """化入（意境合成改版，fusion.infuse）：others 化進 body。不收錢；做成了寫一則煉製的紀錄。"""
    ok, msgs = fusion.infuse(ctx.state, ctx.content, ctx.world, body, others)
    out = ctx._log(msgs)
    if ok:
        out += ctx._menxia_entry("化入", ctx._xinde(), guide=False, title=journal.CRAFT, lines=out[:1])
    return out


def status_fusion(ctx: Game) -> dict:
    """狀態列的 fusion 格（煉製頁的化入要的；改版沒開是 {}）。"""
    return fusion.status(ctx.state, ctx.content)


def forge_line(ctx: Game, insight_ids: list[str]) -> str:
    return forge_view.forge_line(ctx.state, ctx.content, ctx.world, insight_ids)


def forge_preview(ctx: Game, insight_ids: list[str]) -> dict | None:
    """兩格都放好時煉製頁的預覽卡（forge_view.forge_preview）。只讀。"""
    return forge_view.forge_preview(ctx.state, ctx.content, ctx.world, insight_ids)


def forge_picks(ctx: Game, insight_ids: list[str]) -> dict | None:
    """爐裡只放了一個意境時，另一格放得進來的每一個合不合得了（forge_view.forge_picks）。只讀。"""
    return forge_view.forge_picks(ctx.state, ctx.content, ctx.world, insight_ids)


# ── 自創武學（五步：執器、擺式、立意、成形、立名；規則在 create.py）──


@not_while_preparing
def begin(ctx: Game, kind: str, form: str) -> list[str]:
    """執器：內功或武學、兵器種類或行功之法。只開單、不收錢、不寫紀錄。"""
    return ctx._log(create.begin(ctx.state, ctx.content, kind, form))


@not_while_preparing
def pose(ctx: Game, pose: dict) -> list[str]:
    """擺式：火柴人的九個角度（create.POSE_KEYS）。只改單子。"""
    return ctx._log(create.set_pose(ctx.state, ctx.content, pose))


def intent_request(ctx: Game, text: str) -> create.IntentRequest | list[str]:
    """立意的 A 段（鎖內、只讀）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。"""
    if ctx._preparing():
        return [PREPARING_REFUSAL]
    problem = create.intent_problem(ctx.state, ctx.content, text)
    if problem is not None:
        return [problem]
    return create.request(ctx.state, text)


@not_while_preparing
def intent(ctx: Game, text: str, reading: create.IntentReading | None = None) -> list[str]:
    """立意（C 段，或直接呼叫）：reading 是鎖外讀好的；沒給（假人、整季機器人、腳本）照關鍵字表讀。
    記下之後馬上成形（擲四格顏色），心得在這一刻收（一張單子一次，Joy 2026-10-21）：收了寫一則煉製紀錄。"""
    xinde = ctx._xinde()
    msgs = ctx._log(create.set_intent(ctx.state, ctx.content, ctx.world, text, reading))
    if ctx._xinde() != xinde:
        ctx._menxia_entry(msgs[0], xinde, title=journal.CRAFT, action="forge")
    return msgs


def reread_request(ctx: Game, text: str) -> create.IntentRequest | list[str]:
    """重讀這句意的 A 段（鎖內、只讀）：送得出去回傳要在鎖外請模型讀的單子，不行回傳那一句話。"""
    if ctx._preparing():
        return [PREPARING_REFUSAL]
    problem = create.reread_problem(ctx.state, ctx.content, text)
    if problem is not None:
        return [problem]
    return create.request(ctx.state, text)


@not_while_preparing
def reread(ctx: Game, text: str, reading: create.IntentReading | None) -> list[str]:
    """重悟帖：重讀這句意（C 段，create.reread）。reading 是 None（模型叫不動）什麼都不改、不扣帖。"""
    return ctx._log(create.reread(ctx.state, ctx.content, ctx.world, text, reading))


@not_while_preparing
def reroll(ctx: Game) -> list[str]:
    """重悟帖：成了形直接重骰（create.reroll）。只改單子與帖數。"""
    return ctx._log(create.reroll(ctx.state, ctx.content, ctx.world))


@not_while_preparing
def back(ctx: Game, to: str) -> list[str]:
    """回頭重擺式或重立意（成形之後回頭用掉一次重來）。"""
    return ctx._log(create.back(ctx.state, ctx.content, to))


@not_while_preparing
def name(ctx: Game, name: str, move: str | None = None) -> list[str]:
    """立名：付心得、登記（create.finish，一律上品）；move 是招名（空的照模型起的）。做成了寫一則煉製紀錄，被拒絕只回一句。"""
    xinde = ctx._xinde()
    art, msgs = create.finish(ctx.state, ctx.content, ctx.world, name, move)
    ctx.forged = art is not None
    ctx.forged_thing = ("art", art.id) if art is not None else None
    msgs = ctx._log(msgs)
    if art is not None:
        ctx._menxia_entry(msgs[0], xinde, guide=True, title=journal.CRAFT, action="forge", lines=msgs[1:])
    return msgs


@not_while_preparing
def cancel(ctx: Game) -> list[str]:
    return ctx._log(create.cancel(ctx.state))


def view(ctx: Game) -> dict:
    """煉製頁「自創」那一塊（create.view）。只讀。"""
    return create.view(ctx.state, ctx.content, ctx.world)


def deliver_echoes(ctx) -> None:
    """首創名望回饋（Config.first_echo）：這一季別人照著你首創的武學或意境合了出來（兵器配方打了出來）（fusion.echo 記在 WorldState.echoes），
    你同步時補名望——每多一個人 +fame_per，補到第幾個人記在 Echo.paid，所以一個人只算一次。好幾門一起補就合成一則紀錄。
    做法同 _deliver_renames：合的那一下不動別人的角色，每個人自己的 Game 同步時自己補。第一季沒開著時 echoes 是空的。"""
    p = ctx.state.player
    rule = ctx.content.config.first_echo
    lines, gained = [], 0
    for entry in ctx.state.world.echoes.values():
        co = entry.co_creator == p.name  # 論武合出來的：另一個首創者照自己的帳補（co_paid）
        due = len(entry.followers) - (entry.co_paid if co else entry.paid)
        if p.name not in (entry.creator, entry.co_creator) or due <= 0:
            continue
        if co:
            entry.co_paid = len(entry.followers)
        else:
            entry.paid = len(entry.followers)
        gained += due * rule.fame_per
        lines.append(f"江湖上又有 {due} 人照著你首創的{entry.name}{entry.made}了出來。")
    if not lines:
        return
    ctx._write(journal.ECHO, lines + renown.gain(ctx.state, ctx.content, "fame", gained))  # 名聲設計 3.2
    ctx._save_season()  # 補到第幾個人記在共用賽季裡
