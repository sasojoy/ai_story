"""事件檢定（核心本體；全部拆包第 16 批，計畫 docs/superpowers/plans/2026-11-01-事件檢定進核心.md，導覽 docs/guide/核心與存檔.md「事件檢定」）：
端出事件卡、固定選項的檢定與結果、效果套用、事件裡打一場、隨口應對的三段式。原本是 Game 上的 17 個方法，本體照抄、self 換成 ctx
（第一階 ctx 就是 Game，開發規範手冊 3.3），Game 留 15 個一行委派（server、假人、測試、探索包都在叫；只有這裡叫的 answer_branch、
deed_credit 不留）。模組裡互相叫直接叫函式；被測試換掉的 Game 方法經 ctx.<名>（手冊第十五節：換掉的才打得到）——ctx._present
（tests/bots/test_event_rotation 換掉 Game._present）、ctx._apply（tests/figures/test_seats 換掉 Game._apply：效果裡記的貢獻要排在抄帳之前）、
ctx.free_text_request（tests/server/test_server 換掉 Game.free_text_request：暫停中不問引擎）；留在 Game 上的（選單、分派、記錄、
戰鬥的單打服務、地盤的進度……）一律經 ctx。

- 事件卡：present（把事件端到眼前）、event_text（旁白）、event_tier（州郡大事、天下大事那一行）、event_option_view（江湖頁的鈕）、
  choice_label_of（選單上那一顆的字）
- 固定選項：resolve_choice（按下去：檢定、打一場、套效果、行狀）、event_battle（劇情戰）、apply（效果；串下一則）、tale_clue（說書的口訣）
- 隨口應對：free_text_of、branches_of、event_free_text_prompt（那一顆與輸入框）、free_text_request（A 段，鎖內只讀）、
  answer_event（C 段）、answer_branch（分岔的 C 段）、deed_credit（分岔的後果記貢獻）、add_gamble_narration（E 段，潤色插回紀錄）；
  鎖外的 B、D 段照舊在 server.answer_event，叫 Game 的委派
- 模組層的名字：FREE_TEXT_OPTION、EVIL_ANNAL、FreeTextRequest、FreeTextOutcome（engine 照名字 import 回來，`from tianxia.engine import …` 照舊）

名字的綁法照 engine：engine 拿名字的（rules.roll_check、apply_effect……）這裡也拿名字，engine 叫模組屬性的（events.note_round、team、
event_llm、secret_recipes）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣。engine 在 `from .world import (...)` 之後才 import 這一份
（這裡 import 的模組那時都已經載入，載入順序不變）。

改這一份要跑的測試（dev/core-events-1 審查修正，PM 2026-11-03；導覽〈核心與存檔〉「事件檢定」）：
- scripts/test_for.py：核心測試＋煙霧，再並上寫到改到的函式（連模組裡直接叫它、用到它的，一路往上）的 Game 委派名、模組名＋函式名、
  類別與常數的測試檔（test_for.core_module_callers）。tale_clue 挑到 tests/arts/test_secret_recipes.py、tests/gear/test_forge_secrets.py；
  present 挑到寫 _present 的 tests/ranger/test_stances_fix6.py（人物心意那一則）、tests/figures/test_seats.py、tests/core/test_events.py……；
  沒留委派的 answer_branch、deed_credit 照叫它的 answer_event 挑到隨口應對那幾個（test_free_text_and_marks、test_outcomes_answer……）。
- present、event_text、choice_label_of、resolve_choice、apply 是每一則事件都走的（端出卡、選單上的字、按下固定選項、套效果），只挑那一個
  函式的不夠：改了，提交之後照整個檔挑一次 `scripts/test_for.py tianxia/core/event_check.py --base HEAD --slow`（工作樹跟 HEAD 沒有差
  時照整個檔算；還沒提交就只挑改到的那幾個函式的）。
- 一個名字都沒寫、經 choose、探索、整季走的，改了 present 等等 test_for 也挑不到，另外跑（-m "slow or not slow" -n 4）：
  - present 記看過的事件：tianxia/features/explore/tests/test_explore.py（test_a_seen_once_event_never_comes_back）、tests/season/test_real_content.py
    （slow：test_bot_plays_a_full_season）——審查把 seen_events.add 拿掉，test_for 挑的與原本列的 18 個檔都沒紅，只有這兩個紅
  - 端出事件與固定選項：tests/bots/test_event_llm.py、tests/core/test_event_ease.py、tests/core/test_event_reward_caps.py、
    tests/core/test_event_tiers.py（整檔 slow；event_tier 沒有測試寫到它的名字）、tests/core/test_events_new_regions.py、
    tests/core/test_faction_events.py、tests/figures/test_foreshadow.py、tests/figures/test_item7_foreshadow_cooldown.py、
    tests/season/test_real_foreshadows.py
- 與 scripts/same_behavior.py 的 events 一軌（compare --tracks events；見計畫第五、六節）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from . import annal_base as annals
from . import bounty_base
from .. import battlelog, event_llm, forge_secrets, journal, narration, secret_recipes, story_base, team, tiers
from .. import events as event_rules  # note_round 走模組屬性（測試要能換掉它，確認只有端出事件那一下會叫；照 engine 的叫法）
from .. import outcomes as outcome_rules
from .. import prologue as prologue_rules
from .. import stance_world as stance_rules  # 人物心意的世界那一半（共用規則層，全部拆包第 19 批）
from ..events import choice_label, stamina_note, visible_choices
from ..journal import Draft
from ..models import FREE_TEXT_MAX, Choice, Effect, Event, FreeTextChoice, Outcome
from ..rules import (
    apply_effect, check_gap, check_result_line, evil_success, failed, fill_marks, free_text_rate, jianfa, rate_words, roll_check,
)
from ..world import check_thresholds

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）

FREE_TEXT_OPTION = "choice:free"  # 事件的「隨口應對」：按下去只是叫出輸入框，真正送出走 free_text_request／answer_event
EVIL_ANNAL = "，行了一件惡事，成了。"  # 行狀：隨口應對判成惡行而且成了（FB-223），接在「遇上【某事】，隨口應對」後面。待 joy 潤


class FreeTextRequest(BaseModel):
    """隨口應對鎖外評估的單子（server.py 的 A 段拿到、B 段送模型、C 段交回 answer_event 重驗）。"""
    event_id: str
    text: str
    # 減法季批 4：分岔開著、這則事件寫了後果時是可能的走向（outcomes.tags；B 段照它改叫 event_llm.judge_outcome）；其餘是空的
    outcomes: list[dict[str, str]] = []


class FreeTextOutcome(BaseModel):
    """擲完骰的結果：server.py 拿它在鎖外請模型潤色，再交回 add_gamble_narration 插進那一則江湖紀錄。"""
    event_id: str
    text: str
    success: bool
    effect_text: str
    time: float  # 那一則紀錄的遊戲時間與標題，插潤色前用來認是不是同一則
    title: str
    evil: bool = False  # 判成惡行而且成了（FB-223）：effect_text 是 rules.EVIL_DONE，潤色照惡行寫、寫成了換掉那一句
    outcome: str = ""  # 減法季批 4：分岔開著時走的是哪一種後果（id）；關著是空的


# ── 事件卡 ──


def present(ctx, event: Event, action: str | None = None) -> list[str]:
    """把事件端到玩家眼前。action 是抽中它的行動（探索、交友、遊歷）：這時才記進 joy 的防重複輪替
    （events.note_round；pick_event 本身不改狀態，預覽怎麼抽都不算）。next_event 串接、晉升召見不是從池子抽的，不給 action。
    重複的事件不請模型補點綴句（2026-10-12 拿掉）：那句在行動鎖裡等模型最多 15 秒、全服跟著等，探索幾乎每次都撞到重複的事件，
    寫出來卻只進 GameState.log（事件文字在紀錄裡是藏起來的、場景照內容原文畫），畫面上從來看不到。"""
    if action is not None:
        event_rules.note_round(ctx.state, ctx.content, event, action)
        stance_rules.met(ctx.state, ctx.content, event.id)  # 人物心意開的那一則：每人每天一則（減法季批 6 修正輪）
    ctx.state.pending_event = event.id
    ctx.state.player.seen_events.add(event.id)
    head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
    text = fill_marks(event_text(ctx, event), ctx.state)
    ctx._outcome(journal.event_marker(event.title, event.qiyu), head)
    ctx._hide(text)
    return [head, text] + ctx._hear_from_event(event.id)  # 片段事件（計畫 T7；本體在軍情包，全部拆包第 34 批）


def event_text(ctx, event: Event) -> str:
    """事件卡上的旁白（還沒套 fill_marks）：減法季這一週改寫好了就用改寫的（narration.text_of），否則照內容原文。"""
    return narration.text_of(ctx.content, ctx.state.world, event, ctx.state.player.season_number, ctx.narration)


def event_tier(ctx) -> dict | None:
    """眼前這一則事件是第二、三階時，場景卡上那一行小字與框色（事件分級設計稿：州郡大事、天下大事）；第一階、沒有事件、
    全服戰鬥蓋著場景都是 None。"""
    s = ctx.state
    if not s.pending_event or s.world.ended or ctx._battle_for_me(tick=False) is not None:
        return None
    event = ctx.content.events.get(s.pending_event)
    if event is None or event.tier <= 1:
        return None
    return {"tier": event.tier, "name": tiers.NAMES[event.tier]}


def event_option_view(ctx) -> dict[str, dict] | None:
    """江湖頁事件選項的樣子（減法季批 1，整合設計 6.4）：鈕上只留動作，底下一行小字寫成算，失手的代價不寫在鈕上。
    眼前沒有事件是 None；有的話每一顆 choice:N 一筆 {"act": 動作（拜入門派會作廢懸賞的那一句照樣接在後面）, "kind": 檢定的屬性鍵／
    "fight"／""（網頁照它畫鈕前的小圖示）, "worry": 檢定是「{屬性名} {數值}：{心裡話}」（events.check_note）、動手是「對手：{名字}・{勝算}」、
    不擲骰是空字串, "sure": 有把握（檢定不缺、勝算穩勝或有把握）——網頁照它決定那一行要不要標成擔心的顏色}。
    成算每一顆都寫（Joy 2026-10-27 在決定卡上選「每顆都寫回來」；批 1 原本只在「難說」以下才寫心裡話、不寫屬性與數值）。
    選單上的標籤一個字不改（假人與模擬照舊讀它）。
    只讀：勝算照 odds 的備忘，不擲骰。"""
    s, c = ctx.state, ctx.content
    if not s.pending_event or s.pending_event not in c.events:
        return None
    out: dict[str, dict] = {}
    for i, ch in visible_choices(c.events[s.pending_event], s, c):
        act = ch.text + bounty_base.join_note(s, c, ch)
        if ch.combat:
            squad = ctx._story_squad(c.squads[ch.combat])
            odds = team.estimate(s, c, ctx.world, squad.id, difficulty=squad.difficulty, memo=ctx.odds_memo)
            out[f"choice:{i}"] = {"act": act, "kind": "fight", "worry": f"對手：{squad.name}・{odds}", "sure": odds in ("穩勝", "有把握")}
        elif ch.check:
            gap = check_gap(ch.check, s, c, ctx.world)
            out[f"choice:{i}"] = {"act": act, "kind": ch.check.stat, "worry": event_rules.check_note(ch.check, s, c, ctx.world), "sure": gap >= 0}
        else:
            out[f"choice:{i}"] = {"act": act, "kind": "", "worry": "", "sure": True}
    return out


def choice_label_of(ctx, choice: Choice, odds: bool) -> str:
    """動手的選項寫對手與勝算，後面照樣接體力的代價（輸了多扣的，企劃者裁決 E6；events.stamina_note）；
    有檢定的寫一行「（屬性 數值：心裡話）」（events.choice_label）。拜入陣營名下的門派、而且手上有新陣營接不了的懸賞時，
    最後多一個括號講會作廢幾張（bounty_base.join_note，FB-159）。"""
    if choice.combat and odds:
        squad = ctx._story_squad(ctx.content.squads[choice.combat])
        odds_text = team.estimate(ctx.state, ctx.content, ctx.world, squad.id, difficulty=squad.difficulty)
        label = f"{choice.text}（對手：{squad.name}・{odds_text}）{stamina_note(choice, ctx.content)}"
    else:
        label = choice_label(choice, ctx.state, ctx.content, ctx.world)
    return label + bounty_base.join_note(ctx.state, ctx.content, choice)


# ── 固定選項：檢定、打一場、效果 ──


def resolve_choice(ctx, index: int) -> list[str]:
    s, c = ctx.state, ctx.content
    event = c.events[s.pending_event]
    choice = event.choices[index]
    s.pending_event = None
    msgs = [f"▸ {choice.text}"]
    ctx._hide(msgs[0])
    rare = event.once or event.qiyu  # 行狀：一次性的事、奇遇記下你怎麼選的（平常的事件太多，不記）
    what = f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，你選了「{choice.text}」"
    if choice.combat:
        if rare:
            annals.note(s, c, annals.DEED, what + "。", 3)
        msgs += event_battle(ctx, event, choice)
        return msgs + ctx._event_progress()  # 領地爭奪：在區塊了結一則事件推一次進度（開關關著是空的）
    if choice.check:
        success = roll_check(choice.check, s, c, ctx.world, ctx.rng)
        tag, line = check_result_line(success)  # 一律是本人：不寫誰出手（企劃者 2026-10-05）
        msgs.append(line)
        ctx._outcome(tag, line)
        if rare:
            annals.note(s, c, annals.DEED, what + ("，成了。" if success else "，沒成。"), 3)
        msgs += ctx._apply(choice.effect if success else failed(choice.fail_effect, c), once=event.once) + tale_clue(ctx, event)
        return msgs + ctx._event_progress()
    if rare:
        annals.note(s, c, annals.DEED, what + "。", 3)
    msgs += ctx._apply(choice.effect, once=event.once) + tale_clue(ctx, event)
    return msgs + ctx._event_progress()


def tale_clue(ctx, event: Event) -> list[str]:
    """說書的事件了結時，偶爾多一句說書版的口訣（武學，Config.secrets，tianxia/secret_recipes.py），記進武學譜；鑄器另擲一次
    （Config.forge_secrets，打造隱藏配方設計 6.2，兩句都中兩句都寫）。擲骰用自己的亂數，不動 ctx.rng。"""
    s, cfg = ctx.state, ctx.content.config.secrets
    if event.id not in cfg.tale_events:
        return []
    out = []
    seed = f"說書|{s.player.name}|{s.world.time}|{event.id}"
    if secret_recipes.roll(cfg.tale_chance, seed):
        clue = secret_recipes.hear(s, ctx.content, secret_recipes.tianji_of(ctx.world), secret_recipes.TALE, seed)
        if clue:
            out.append(cfg.tale_frame.format(clue=clue))
    return out + ctx._forge_clue(forge_secrets.TALE, f"鑄說書|{s.player.name}|{s.world.time}|{event.id}")


def event_battle(ctx, event: Event, choice: Choice) -> list[str]:
    s, c = ctx.state, ctx.content
    squad = ctx._story_squad(c.squads[choice.combat])  # 大場面照江湖水漲浮上來
    judged = ctx._judged(squad)  # 打頭目這種大場面：有鎖外的判讀就用（武學與成長設計 8.3）
    result = ctx._fight_with(squad, judged, dodge=False, difficulty=squad.difficulty)  # 劇情戰的勝敗是人寫好的：不閃（最終審查 I1）
    record = battlelog.new_record(s, c, ctx.world, squad, result, "event", event.title)
    record.notes += ctx._style_note(squad, result) + ctx._terrain_note()  # 劇情戰不扣氣血，地利照寫：威力真的有算
    ctx._narrate(record, result, judged)
    # 回合照開打時的陣容與身法演，所以要在發獎勵、套效果之前：效果可能加身法、教武學、給同伴或部下，
    # 不能回頭改寫這一場（例如 wolves 打贏身法 +1，不能變成「因為獎勵才先出手」）。
    # 劇情戰不扣氣血：對手的出手不寫數字（計畫三 G5）
    ctx._play_rounds(record, squad, result.tier, None, ctx._hp_facts(), clash=result.clash)  # 氣血照開打時的樣子：厚拉高的下限這一場也起了作用
    won = result.tier in team.WIN_TIERS
    rewards = ctx._battle_rewards(squad, record) if won else []
    effect = choice.effect if won else failed(choice.fail_effect, c)  # 打輸另扣的體力減半，同檢定失敗（企劃者裁決 E6）
    story = apply_effect(effect, s, c, ctx.world, push=ctx.push_trend, once=event.once)
    changes, notes = battlelog.split_changes(story, for_record=True)
    record.changes += changes
    record.notes += notes
    story += ctx._seize(record)
    msgs = [ctx._file_battle(record)] + rewards + story
    if ctx.is_big(squad) and not prologue_rules.active(s, c):  # 名聲 4.5：天下聞名打大場面點名
        ctx._famed_news(c.locations[s.player.location].name, squad.name, result.tier)
    if effect.next_event:
        msgs += ctx._present(c.events[effect.next_event])
    return msgs


def apply(ctx, effect: Effect, once: bool = False) -> list[str]:
    """套用事件選項的效果；once＝事件標了 once（推大勢不照季長縮放，FB-166，rules.apply_effect）。"""
    msgs = apply_effect(effect, ctx.state, ctx.content, ctx.world, push=ctx.push_trend, once=once)
    if effect.text and prologue_rules.active(ctx.state, ctx.content):
        for msg in msgs:  # 草廬四景的結果文字已經寫了「你悟到了「…之意境」」，引擎的「你悟得了「…」的意境」是同一件事：紀錄只留前一句
            if msg.startswith("你悟得了「"):
                ctx._hide(msg)
    if effect.next_event:
        msgs += ctx._present(ctx.content.events[effect.next_event])
    return msgs


# ── 隨口應對（三段式：A 段 free_text_request、C 段 answer_event／answer_branch、E 段 add_gamble_narration）──


def free_text_of(ctx, event: Event) -> FreeTextChoice | None:
    """這則事件此刻有沒有「隨口應對」那一顆：寫了 free_text，而且不是只在分岔開著時才有的那一種（outcomes_only，人拉犁；PM 2026-10-25
    第 7 件）——那一種在關著的季沒有這一顆，選單、輸入框的提示語、新手提示都照沒有。"""
    free = event.free_text
    if free is None or (free.outcomes_only and not jianfa(ctx.content, ctx.state.world, "free_text_outcomes")):
        return None
    return free


def branches_of(ctx, event: Event) -> list[Outcome]:
    """這一則的隨口應對此刻照分岔走嗎（減法季批 4，整合設計 5.1）：子開關 free_text_outcomes 開著（加上這一季的章）、事件寫了後果，
    是那幾種後果（最後一種是 fallback）；其餘是空的，照舊用 stat、effect、fail_effect。"""
    free = free_text_of(ctx, event)
    if free is None or not free.outcomes or not jianfa(ctx.content, ctx.state.world, "free_text_outcomes"):
        return []
    return free.outcomes


def event_free_text_prompt(ctx) -> str | None:
    """眼前的事件可以隨口應對時回傳提示語（選單上那一顆的標籤），否則 None；server.py 用它決定輸入框。"""
    event_id = ctx.state.pending_event
    free = None if event_id is None else free_text_of(ctx, ctx.content.events[event_id])
    return None if free is None else free.prompt


def free_text_request(ctx, text: str) -> FreeTextRequest | None:
    """隨口應對的階段 A（server.py 在行動鎖內、很快地呼叫）：眼前的事件可以隨口應對、寫的字是 1～20 字，
    就回傳要在鎖外送模型評估的單子；不行就是 None。只讀、不改狀態，也不推進戰鬥（理由同 dialogue_request）。"""
    text = text.strip()
    event_id = ctx.state.pending_event
    if not text or len(text) > FREE_TEXT_MAX or event_id is None:
        return None
    if FREE_TEXT_OPTION not in {o.id for o in ctx.options(odds=False, tick=False) if o.enabled}:
        return None
    branches = branches_of(ctx, ctx.content.events[event_id])
    return FreeTextRequest(event_id=event_id, text=text, outcomes=outcome_rules.tags(branches) if branches else [])


def answer_event(
    ctx, request: FreeTextRequest, llm_rate: int | None = None, moral: str | None = None, outcome: str | None = None,
) -> list[str]:
    """隨口應對的階段 C（鎖內）：重驗還停在同一則事件、寫的是同一句話，才算成功率、擲骰、套用效果。
    llm_rate 是鎖外評好的 0～100、moral 是同一次評出來的善惡（event_llm.MORALS）；llm_rate 沒給（直接呼叫的測試、腳本）
    就在這裡評（行動鎖內，用 _quick_client 的短逾時複本），評不到一樣退回 40、善惡當「中」。
    成功率＝LLM 評分加屬性修正、夾在 5～85（rules.free_text_rate）；擲骰用引擎自己的 rng。
    善惡再驗一次（event_llm.moral_of：不是那三個字當「中」）。判成「惡」而且擲中了（FB-223）：成功效果換成惡行的版本
    （rules.evil_success：善名換惡名、扣惡名與加情誼拿掉、結果句換成 rules.EVIL_DONE），潤色照惡行寫（FreeTextOutcome.evil）；
    「善」「中」、或「惡」沒擲中，一個字都不變。
    分岔開著、這則事件寫了後果（_branches）時改走 _answer_branch（outcome 是 B 段歸好的那一種的 id）；關著的季 outcome 不理。"""
    s, c = ctx.state, ctx.content
    ctx.last_gamble = None
    current = ctx.free_text_request(request.text)
    if current is None or current.event_id != request.event_id:
        return ctx._log(["（事情已經過去了，這句話沒派上用場。）"])
    event = c.events[request.event_id]
    story_base.heard(s, c, event.id, request.text)  # 一條線的段落：自己寫的那一句記進那條線（結尾與模型用）
    branches = branches_of(ctx, event)
    if branches:
        return answer_branch(ctx, event, request, branches, llm_rate, moral, outcome)
    choice = event.free_text
    if llm_rate is None:
        # 判善惡那一次照 _quick_client 的額度：評分失敗用掉了額度就不叫、當「中」
        verdict = event_llm.judge_event_gamble(ctx._quick_client(), event, request.text, moral_client=ctx._quick_client)
        llm_rate = verdict.rate
        moral = verdict.moral if moral is None else moral
    moral = event_llm.moral_of(moral)
    ctx.state.battle_card = None
    faction_before = s.player.faction
    ctx._draft = Draft(f"{event.title}・隨口應對")
    ctx._affinity_before = dict(s.player.affinities)
    try:
        s.pending_event = None
        rate = free_text_rate(llm_rate, choice, s, c, ctx.world)
        success = ctx.rng.random() * 100 < rate
        evil = success and moral == event_llm.MORAL_EVIL  # 惡行而且成了（FB-223）；善惡不碰 rng
        tag, line = check_result_line(success)  # 一律是本人：不寫誰出手
        msgs = [f"你：「{request.text}」（{rate_words(rate)}）", line]
        ctx._outcome(tag, line)
        # 行狀：隨口應對是自己的話，一律記；一次性的事、奇遇份量重一些。惡行成了照實寫（EVIL_ANNAL）
        done = EVIL_ANNAL if evil else "，成了。" if success else "，沒成。"
        annals.note(s, c, annals.DEED, f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，隨口應對{done}",
                    3 if event.once or event.qiyu else 1, quote=request.text)
        if evil:
            effect = evil_success(choice.effect)
        else:
            effect = choice.effect if success else failed(choice.fail_effect, c)  # 失手另扣的體力減半（體力平衡提案）
        msgs += ctx._apply(effect, once=event.once)
        msgs += ctx._event_progress()  # 領地爭奪：隨口應對了結也推一次進度（開關關著是空的）
        ctx._begin_enlistment(faction_before)  # 隨口應對的結果也可能拜入門派
        ctx._greet_rejoin(faction_before)  # 同樣：入伍段早就走完的人拜入門派，引薦人打個招呼（新手引導計畫三）
        gifts = ctx._general_gifts() + ctx._signature_arms()  # 隨口應對的效果也可能加情誼（同 choose：另起一則）
        msgs += check_thresholds(s, c, ctx.world, ctx._flavor_sink(), now=ctx.now)
        msgs += ctx._report_seat()  # 隨口應對的效果也可能推大勢、記貢獻：第四階席次的帳在這裡也抄（正式版丁）
        ctx._check_hints()  # 隨口應對了結了事件：同選項一樣，碰到的新玩法排一條、排著的上框（新手引導計畫三）
        journal.add_entry(s, ctx._draft.entry(s.world.time, msgs))
        ctx._gift_entry(gifts)
        msgs += gifts
        ctx.last_gamble = FreeTextOutcome(
            event_id=event.id, text=request.text, success=success, effect_text=fill_marks(effect.text, s),
            time=s.world.time, title=ctx._draft.title, evil=evil,
        )
    finally:
        ctx._draft = None
        ctx._affinity_before = None
    ctx._record_faction()
    ctx._save_season()
    return ctx._log(msgs)


def answer_branch(
    ctx, event: Event, request: FreeTextRequest, branches: list[Outcome], llm_rate: int | None, moral: str | None,
    outcome: str | None,
) -> list[str]:
    """隨口應對分岔的 C 段（減法季批 4；整合設計 5.1、5.9，主機側計畫 Task 4-2）：照 outcomes.plan 分四條走——
    check 照那一種的檢定擲骰（ctx.rng；成功率比的是那一種的難度，outcomes.rate）、成套 effect 敗套 fail_effect；combat 照固定選項開打
    （_event_battle），贏套 effect、輸套 fail_effect；cost 掏銀兩、必成（不夠就回 NOT_ENOUGH_SILVER、不做、不扣次數，事件還停著）；
    最後一種（fallback）只套那一句。outcome 是 B 段歸好的 id（不在清單一律最後一種）；llm_rate 沒給（直接呼叫的測試、腳本）就在鎖內
    自己歸類（event_llm.judge_outcome，_quick_client 的額度）。
    善惡（FB-223）只在歸到最後一種時照舊看模型的評分（判「惡」就是惡行成了：rules.evil_success）；選中別的後果時只看那一種自己的效果
    （作惡那一種本來就扣善名），同一句話不加兩次（PM 2026-10-25 第 8 件）。成了的後果記貢獻（_deed_credit）。
    行狀只寫後果的類名，不存玩家寫的句子（公開的只有後果與痕跡）；江湖紀錄是自己的，照舊寫那一句，括號裡多寫類名。"""
    s, c = ctx.state, ctx.content
    if llm_rate is None:
        verdict = event_llm.judge_outcome(ctx._quick_client(), event, branches, request.text, moral_client=ctx._quick_client)
        llm_rate, outcome = verdict.rate, verdict.outcome
        moral = verdict.moral if moral is None else moral
    plan = outcome_rules.plan(branches, outcome, llm_rate, s, c, ctx.world)
    chosen = plan.outcome
    problem = outcome_rules.cost_problem(chosen, s) if plan.way == "cost" else ""
    if problem:
        return ctx._log([problem])
    fallback = plan.way == "fallback"
    moral = event_llm.moral_of(moral) if fallback else event_llm.MORAL_NEUTRAL
    # 類名（短名）寫進紀錄的括號與行狀；歸到最後一種（走開）不寫類名，照關著時的寫法（FB-800，PM 2026-10-25：紀錄與行狀
    # 「隨口應對，行了一件惡事，成了。」不寫成「隨口應對：走開，…」；判善、判中也不寫）
    name = "" if fallback else outcome_rules.kind_name(chosen)
    s.battle_card = None
    faction_before = s.player.faction
    ctx._draft = Draft(f"{event.title}・隨口應對")
    ctx._affinity_before = dict(s.player.affinities)
    try:
        s.pending_event = None
        evil = False
        if plan.way == "check":
            success = ctx.rng.random() * 100 < plan.rate
            tag, line = check_result_line(success)  # 一律是本人：不寫誰出手
            msgs = [f"你：「{request.text}」（{name}・{rate_words(plan.rate)}）", line]
            ctx._outcome(tag, line)
            effect = chosen.effect if success else failed(chosen.fail_effect, c)
            msgs += ctx._apply(effect, once=event.once)
        elif plan.way == "combat":
            msgs = [f"你：「{request.text}」（{name}）"]
            msgs += event_battle(ctx, event, outcome_rules.as_choice(chosen))  # 效果在打完那一刻照勝負套
            success = s.battles[0].tier in team.WIN_TIERS
            effect = chosen.effect if success else failed(chosen.fail_effect, c)
        else:  # 掏錢的、最後一種：不擲骰、必成
            success = True
            evil = fallback and moral == event_llm.MORAL_EVIL
            effect = evil_success(chosen.effect) if evil else outcome_rules.paid(chosen)
            msgs = [f"你：「{request.text}」" + (f"（{name}）" if name else "")]
            msgs += ctx._apply(effect, once=event.once)
        deed_credit(ctx, chosen, success)
        done = EVIL_ANNAL if evil else "。" if fallback else "，成了。" if success else "，沒成。"
        annals.note(s, c, annals.DEED, f"遇上{'奇遇' if event.qiyu else ''}【{event.title}】，隨口應對{'：' + name if name else ''}{done}",
                    3 if event.once or event.qiyu else 1)  # 不存玩家的句子（quote 空著）
        msgs += ctx._event_progress()  # 領地爭奪：隨口應對了結也推一次進度（開關關著是空的）
        ctx._begin_enlistment(faction_before)
        ctx._greet_rejoin(faction_before)
        gifts = ctx._general_gifts() + ctx._signature_arms()
        msgs += check_thresholds(s, c, ctx.world, ctx._flavor_sink(), now=ctx.now)
        msgs += ctx._report_seat()
        ctx._check_hints()
        journal.add_entry(s, ctx._draft.entry(s.world.time, msgs))
        ctx._gift_entry(gifts)
        msgs += gifts
        ctx.last_gamble = FreeTextOutcome(
            event_id=event.id, text=request.text, success=success, effect_text=fill_marks(effect.text, s),
            time=s.world.time, title=ctx._draft.title, evil=evil, outcome=chosen.id,
        )
    finally:
        ctx._draft = None
        ctx._affinity_before = None
    ctx._record_faction()
    ctx._save_season()
    return ctx._log(msgs)


def deed_credit(ctx, outcome: Outcome, success: bool) -> None:
    """分岔的後果記貢獻（整合設計 5.3）：成了、不是作惡那一種（PM 2026-10-25 第 6 件）、有那一邊（散人照留痕跡、不記貢獻，同推線）。
    一天（季曆日，同推線的上限）最多 Config.jianfa.deed_contribution_cap，超過的不記（PlayerState.deed_day／deed_today）。
    走 wins.credit：兩軍照舊加 contrib 與那一週的帳，豪強另記此刻幫的那一軍那一本。"""
    ctx._deed_points(outcome.effect.contribution if success and not outcome.evil else 0)


def add_gamble_narration(ctx, outcome: FreeTextOutcome, narration: str) -> None:
    """隨口應對的潤色（鎖外生成）插回那一則江湖紀錄：接在「你：「…」」那一行後面、結果文字前面。
    認不到那一則（紀錄已經被後來的事併掉或擠到後面）就不插，潤色本來就是錦上添花。
    潤色那一段已經把結果句整句寫進去了（空白、標點不算，event_llm.tells_the_outcome）就拿掉後面引擎那一行結果句，
    不寫兩次（FB-124）；這時模型那一段不切（結果句常常接在它自己的半句後面，切了會留下斷掉的逗號）。
    只寫到結果句的頭半句、收在那一段的尾巴上（FB-222）：把尾巴重疊的那一截切掉（event_llm.trim_echo），結果句照接整句；
    整段都是重疊的就不插。
    惡行成了（FB-223，outcome.evil）：潤色那一段就是結果，換掉 rules.EVIL_DONE 那一句固定的話（那一句只在潤色沒寫成時收尾）。"""
    journal_entries = ctx.state.journal
    if not narration or not journal_entries:
        return
    entry = journal_entries[0]
    if entry.time != outcome.time or entry.title != outcome.title:
        return
    lines = list(entry.lines)
    said = next((i for i, line in enumerate(lines) if line.startswith(f"你：「{outcome.text}」")), None)
    at = 0 if said is None else said + 1
    if outcome.evil:
        fixed = next((i for i in range(at, len(lines)) if lines[i] == outcome.effect_text), None)
        if fixed is not None:
            del lines[fixed]
        lines.insert(at, narration)
        journal_entries[0] = entry.model_copy(update={"lines": lines})
        return
    told = event_llm.tells_the_outcome(narration, outcome.effect_text)
    if not told:
        narration = event_llm.trim_echo(narration, outcome.effect_text)
        if not narration:
            return
    lines.insert(at, narration)
    if told:
        echo = next((i for i in range(at + 1, len(lines)) if lines[i] == outcome.effect_text), None)
        if echo is not None:
            del lines[echo]
    journal_entries[0] = entry.model_copy(update={"lines": lines})
