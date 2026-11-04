"""一條線包的動作（全部拆包第 30 批：原本 Game 上的 10 個方法，計畫 docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md 1.1）。
Game 留 10 個一行委派（server、假人、腳本、測試在叫的；story_act、story_fight、story_bout 只有這一包叫，不留）。第一個參數 ctx 是 Game（手冊 3.3）；
叫回 Game 的只用 tianxia/core/services.py 那張清單上的；這一包互相叫直接叫函式。最後四段（story_menu、story_options、close_season、story_title）是核心原位
（答題的選單、「未了之事」那一顆、換季收線、江湖紀錄的標題）叫的本體，story_title 與 story_act 接 choose 掛鉤。

章回主線 chapters 在這個檔載入的時候就 import（模組層，不能晚）：它載入時往 storyline.TASKS 登記「章回的一拍」（chapter_beat），原本是 engine 在模組層 import 它，
第一次 tick 之前 TASKS 裡就有；搬走之後換成這裡，載入時機不變（engine import 這個檔）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import battlelog, journal, team  # 共用規則層（戰報）、核心
from tianxia import chapters  # 過渡：待搬（章回主線：模組層 import，載入時登記 storyline.TASKS；第 40 批）
from tianxia.core.option import Option
from tianxia.models import Squad, StoryDef, StoryStage
from tianxia.rules import fill_marks
from tianxia.state import StoryCard, StoryProgress

from . import storyline

if TYPE_CHECKING:
    from tianxia.engine import Game


def story_start(ctx: Game, definition: StoryDef) -> list[str]:
    """程式組的線（例：特殊頓悟）從這裡開：整份 StoryDef 存進進度，第一段是事件、人又在那裡就直接端出來。
    關著、這一季開過同一個 id、這一種沒有空位（Config.jianfa.story_caps）時回空的、什麼都不動。呼叫端自己存檔。"""
    return story_begin(ctx, definition, custom=True)


def story_cards(ctx: Game) -> list[StoryCard]:
    """等著跳出來的卡（開頭、此事已了・入傳、此事未了），照發生的順序。"""
    return list(ctx.state.player.story_cards)


def story_seen(ctx: Game) -> None:
    storyline.seen(ctx.state)


def story_card_view(ctx: Game) -> list[dict]:
    """網頁跳顯框要的那幾張卡（特殊事件設計稿的跳顯框）：sort 是這條線的類別（奇事、頓悟），自訂的線照存檔裡那一份。
    image 是 web/img/ 底下不含副檔名的路徑，圖檔在不在是伺服器的事（同 scene_art）。"""
    p = ctx.state.player
    out = []
    for card in p.story_cards:
        progress = p.storylines.get(card.line)
        line = storyline.definition(ctx.content, progress) if progress is not None else ctx.content.storylines.get(card.line)
        out.append({
            "line": card.line, "kind": card.kind, "sort": line.kind if line is not None else storyline.JOURNAL,
            "title": card.title, "text": card.text, "image": card.image, "ending": card.ending, "failed": card.failed,
        })
    return out


def story_begin(ctx: Game, definition: StoryDef, custom: bool = False) -> list[str]:
    progress = storyline.start(ctx.state, ctx.content, definition, custom=custom)
    if progress is None:
        return []
    head = f"✦ 奇事：{definition.title}"
    ctx._outcome(journal.event_marker(definition.title, True), head)
    intro = [fill_marks(definition.intro, ctx.state)] if definition.intro else []
    return [head] + intro + story_tick(ctx)


def story_tick(ctx: Game) -> list[str]:
    """一條線往前走（storyline.tick）；剛進的那一段是事件、人就在那裡時直接端出來。關著是空的。
    章回主線（chapters）排在前後：先開該開的回、收錯過的回，走完之後把剛走進最後一段的回記成做成（世界的帳改了就存共用的季）。"""
    before = (dict(ctx.state.world.chapter_done), {k: dict(v) for k, v in ctx.state.world.chapter_weights.items()})
    head = chapters.tick(ctx.state, ctx.content, ctx.world)
    msgs, event_id = storyline.tick(ctx.state, ctx.content, ctx.world)
    msgs = head + msgs + chapters.after(ctx.state, ctx.content)
    if (ctx.state.world.chapter_done, ctx.state.world.chapter_weights) != before:
        ctx._save_season()
    if event_id is not None:
        msgs += ctx._present(ctx.content.events[event_id])
    return msgs


def story_act(ctx: Game, arg: str) -> list[str]:
    """按「未了之事」那一顆（story:<線>）：事件段端出事件、答題段出第一題、打一場的段直接打；答題的答案是 story:<線>:a<序號>，
    先擱著是 story:<線>:later。選單上才有這幾顆（choose 先驗過），所以這裡不再驗地方。"""
    s, c = ctx.state, ctx.content
    line_id, _, sub = arg.partition(":")
    if sub:
        return storyline.answer(s, c, line_id, sub)
    progress = s.player.storylines[line_id]
    line, stage = storyline.current(c, progress)
    if stage.kind == "event":
        progress.opened = True
        return ctx._present(c.events[stage.event])
    if stage.kind == "quiz":
        return [f"【{line.title}】"] + storyline.open_quiz(s, c, progress)
    return story_fight(ctx, progress, stage)


def story_fight(ctx: Game, progress: StoryProgress, stage: StoryStage) -> list[str]:
    """一條線的 fight 段：照劇情戰打（不閃、不扣氣血，同 _event_battle），打完交給 storyline.fought（鉤子寫記號、往 win 或 lose、輸了等再試）。"""
    c = ctx.content
    if stage.mirror is not None:  # 自己的影子不在內容的隊伍表裡：打這一場的時候借放一下（行動鎖裡，打完就拿掉）
        squad = mirror_squad(ctx, progress, stage)
        c.squads[squad.id] = squad
        try:
            return story_bout(ctx, progress, stage, squad)
        finally:
            c.squads.pop(squad.id, None)
    return story_bout(ctx, progress, stage, ctx._story_squad(c.squads[stage.squad]))


def story_bout(ctx: Game, progress: StoryProgress, stage: StoryStage, squad: Squad) -> list[str]:
    s, c = ctx.state, ctx.content
    judged = ctx._judged(squad)
    result = ctx._fight_with(squad, judged, dodge=False, difficulty=squad.difficulty)
    line = storyline.definition(c, progress)
    record = battlelog.new_record(s, c, ctx.world, squad, result, "event", line.title)
    record.notes += ctx._style_note(squad, result) + ctx._terrain_note()
    ctx._narrate(record, result, judged)
    ctx._play_rounds(record, squad, result.tier, None, ctx._hp_facts(), clash=result.clash)
    won = result.tier in team.WIN_TIERS
    rewards = ctx._battle_rewards(squad, record) if won and stage.mirror is None else []  # 打自己的影子沒有東西掉
    after = storyline.fought(s, c, progress, won, record)  # 打輸、還能再打（心魔未破）：跳卡、記行狀，紀錄多一行
    return [ctx._file_battle(record)] + rewards + after


def mirror_squad(ctx: Game, progress: StoryProgress, stage: StoryStage) -> Squad:
    """fight 段的對手是自己的影子（StoryStage.mirror，特殊頓悟的心魔）：難度＝你此刻的全隊威力（氣血當滿的、不算地利與碎片，同江湖水漲）
    × mirror，名字是 mirror_name。"""
    base = Squad(id=f"mirror:{progress.line}", name=stage.mirror_name, difficulty=1.0)
    power = team.power_vs(ctx.state, ctx.content, ctx.world, base, fresh=True, terrain=False, seal=False)
    scale = stage.mirror
    if stage.mirror_weaken:  # 重複挑戰時越打越弱（企劃者 2026-10-28）：輸過幾次就削幾次，削到 mirror_floor 為止
        scale = max(stage.mirror_floor, stage.mirror - stage.mirror_weaken * progress.tries)
    return base.model_copy(update={"difficulty": round(max(1.0, power * scale), 1)})


# ── 核心原位叫的（Game 留一行委派）與 choose 掛鉤的本體 ─────────────────────────────────────


def story_menu(ctx: Game) -> list[Option] | None:
    """一條線的答題（storyline.quiz_menu；Game._everyday_options 在有所感的選單之後）：只有這一題的答案與「先擱著」；不在答題中是 None。"""
    s, c = ctx.state, ctx.content
    if s.player.story_open is not None:
        menu = storyline.quiz_menu(s, c)
        if menu:
            return [Option(id=option_id, label=label) for option_id, label in menu]
    return None


def story_options(ctx: Game) -> list[Option]:
    """一條線（特殊事件）：此刻在這裡做得了的那一段一顆，不花體力（Game._everyday_options，應召之後、此地的人之前）。"""
    return [Option(id=option_id, label=label, enabled=ok) for option_id, label, ok in storyline.options(ctx.state, ctx.content)]


def close_season(ctx: Game, old) -> None:
    """換季收線（Game._reset_player_for_new_season，存上一季的行狀之前）：還沒收的寫「此事未了」進傳（休季時同步過的已經寫了）。"""
    storyline.close_season(old, ctx.content)


def story_title(ctx: Game, arg: str) -> str:
    """story:* 那一下江湖紀錄的標題（choose 掛鉤的 Outcome.title；原本 Game._action_title 的 storyline.OPTION 那一支）：寫線的名字。"""
    progress = ctx.state.player.storylines.get(arg.partition(":")[0])
    line = storyline.definition(ctx.content, progress) if progress is not None else None
    return line.title if line is not None else "奇事"


def scene(ctx: Game) -> str | None:
    """自己眼前的場景卡（接縫掛鉤；原本 Game._own_scene_text 有所感、取名那兩支之後的一支）：一條線的答題，場景寫這一題（選單上是答案）；沒有答題是 None。"""
    s, c = ctx.state, ctx.content
    question = storyline.question_text(s, c) if s.player.story_open is not None else None
    if not question:
        return None
    line = storyline.definition(c, s.player.storylines[s.player.story_open])
    return f"**{line.title}**\n\n{question}"
