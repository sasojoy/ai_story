"""寄放補送、名將贈禮與本命兵器（全部拆包第 42 批；裝備四欄設計 6.4 名將贈禮、6.5 寄放；兵器設計 4.10 本命兵器）。原本 Game 上的 5 個方法，
Game 留五個一行委派：_deliver_held_gear（sync、advance 叫，位置固定在 _deliver_big_events 之後）、_general_gifts、_signature_arms、_gift_entry
（choose 後半與核心事件檢定的 answer_event、answer_branch 叫；大勢人物包的挑戰本人也經 ctx 叫 _signature_arms）、_people_here（測試直接叫）。
計畫 docs/superpowers/plans/2026-11-07-裝備包-第1批.md 1.1。第一個參數 ctx 是 Game（手冊 3.3）。
規則照模組屬性叫（treasures.gifts_due、treasures.deliver_held……：量表腳本換掉模組上的，這裡照樣打得到）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import figures  # 共用規則層
from tianxia import treasures  # 共用規則層
from tianxia import journal  # 核心
from tianxia.core import annal_base as annals  # 核心（行狀記一筆，第 29 批之二）
from tianxia.state import JournalEntry  # 核心

from . import signature_arms

if TYPE_CHECKING:
    from tianxia.engine import Game


def deliver_held_gear(ctx: Game) -> None:
    """寄放的東西補發（裝備四欄 6.5）：懸賞的重賞、名將贈禮在裝備庫滿了時寄放在 PlayerState.held_gear；同步與快轉時那一欄開著、
    身上空著或裝備庫有空位就補，一次補到裝備庫滿為止，補不完的留著（treasures.deliver_held）。閉關中也補（寶物閉關中本來就能換，
    2.3【定】）。整季機器人只 advance、不 sync，所以 advance 也叫，不然整季模擬裡寄放的東西永遠補不回來。補了就寫一則江湖紀錄。"""
    lines = treasures.deliver_held(ctx.state, ctx.content)
    if lines:
        ctx._write(treasures.HELD_TITLE, lines)


def general_gifts(ctx: Game) -> list[str]:
    """名將贈禮（裝備四欄 6.4）：情誼到 gift_affinity 的人物把贈禮交給你，每位名將每季全服只送一人（treasures.gifts_due 記進
    WorldState.general_gifts，這一下動作最後的 _save_season 存回去）。choose 與 answer_event 最後各叫一次：情誼從對話（companion_agent）、
    事件（Effect.affinity）、隨口應對來都走得到，不必在兩條路各寫一份。"""
    given = dict(ctx.state.world.general_gifts)
    msgs = treasures.gifts_due(ctx.state, ctx.content, ctx._people_here())
    for cid, who in ctx.state.world.general_gifts.items():
        if cid not in given and who == ctx.state.player.name:  # 行狀：哪一位名將送的（送的是什麼，annals.watch 照裝備記）
            annals.note(ctx.state, ctx.content, annals.FIGURE, f"{annals.figure_name(ctx.content, cid)}看重你，送了你一份贈禮。", 4, figure=cid)
    return msgs


def people_here(ctx: Game) -> set[str]:
    """此刻站在你身邊的人物：同 _figures_here 的所在（人物表上的人照此刻的所在與狀態，其餘照 recruit_at、talk_at），不限深度互動；
    在路上一個都沒有。再加上這一下加了情誼的人（終審 F2：情誼只從當面的事來——對話、晉升事件、伏筆收尾——劉關張在婁桑村的晉升
    事件裡當面出現，不在他們平常站的地方）。名將贈禮與本命兵器照它寫當面交給你還是託人送來（FB-139、FB-149）。"""
    s, c = ctx.state, ctx.content
    before = ctx._affinity_before or {}
    raised = {cid for cid, v in s.player.affinities.items() if ctx._affinity_before is not None and v > before.get(cid, 0)}
    if s.player.journey is not None:
        return raised
    here, placed = s.player.location, figures.placed_characters(s, c)
    return raised | {cid for cid, ch in c.characters.items()
                     if (placed[cid] == here if cid in placed else here in (ch.recruit_at, ch.talk_at))}


def gift_entry(ctx: Game, lines: list[str]) -> None:
    """名將贈禮與本命兵器（情誼那條路）另起一則江湖紀錄（FB-139、FB-149），排在當下那個動作的那一則之後。沒有就不寫。"""
    if lines:
        journal.add_entry(ctx.state, JournalEntry(time=ctx.state.world.time, title=treasures.GIFT_TITLE, tag=lines[0], lines=lines[1:]))


def signature_arms_due(ctx: Game, record=None, beaten: str | None = None, later: list | None = None) -> list[str]:
    """名將本命兵器（兵器設計 4.10；打造第三批，signature_arms.due）：情誼到 signature_affinity 他送你，打贏他本人 signature_wins 次
    他讓你奪走；每位名將每季全服一人（WorldState.signature_arms，這一下動作最後的 _save_season 存回去，同名將贈禮）。choose 與
    answer_event 最後各叫一次（情誼從對話、事件、隨口應對來都走得到）；_challenge 打贏時帶 record、beaten 先叫一次，那一把寫進
    這一場戰報的「得失」（同寶物掉落）——只寫被打敗的那一位的那一把：同一下動作裡別位名將的情誼也到了、一起給的，不寫進這一場
    （終審 minor）。行狀記一筆（人物）；later 給了（_challenge）就先放進去，等那一場自己的行狀記完再記，行狀才照時間先後。
    不擲骰：不碰 Game.rng。"""
    s, c = ctx.state, ctx.content
    items, msgs = signature_arms.due(s, c, beaten=beaten, present=ctx._people_here())
    for item in items:
        arm = next((a for a in c.gear.signature_arms if a.character == item.signature), None)
        if record is not None and beaten is not None and arm is not None and arm.figure == beaten:
            record.materials.append(signature_arms.GAIN_LINE.format(name=item.name))
        note = (signature_arms.annal_line(c, item, s.world.signature_arms[item.signature].via), item.signature)
        if later is None:
            annals.note(s, c, annals.FIGURE, note[0], 4, figure=note[1])
        else:
            later.append(note)
    return msgs
