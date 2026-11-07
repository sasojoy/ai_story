"""交友求見的查詢與文字（功能包 socialize；全部拆包第 21 批，計畫 docs/superpowers/plans/2026-11-04-交友求見包-第1批.md）：原本 Game 上的 19 個方法
（見不見得到、這個遊戲日還能談幾輪、交友這一下會做什麼、談滿了怎麼寫、交友會不會開口），名字去掉前導底線、第一個參數是 ctx（第一階就是 Game）。純讀，不改狀態（會排提示、花亂數的 `no_audience_line` 在 actions.py；檔名叫 view 不叫 rules：手冊 3.2 的 rules.py 不碰 Game，這裡第一個參數是 ctx）。

核心的 `rules.can_meet`（伏筆的偷聽也用它）是另一回事，這裡 import 成 core_can_meet；包裡的 `figure_can_meet` 是 Game._can_meet 的本體。
"""
from __future__ import annotations

from tianxia import precise, ranks, roster, treasures  # 共用規則層（階級 ranks 第 40 批收進；precise、roster、treasures）
from tianxia.core import xinshen  # 心神（核心的資源）：開著時每位人物一天能談到 turns_per_figure 輪
from tianxia.core.services import AUDIENCE_HALL_FIGURES, SNUB_NOTE, SOCIAL_NO_ONE
from tianxia.events import event_candidates, has_events_here  # 過渡：待搬（事件：候選、這個地點有沒有）
from tianxia.models import Event
from tianxia.rules import audience_bar, day_turn, game_day
from tianxia.rules import can_meet as core_can_meet

SOCIAL_TALK = "跟{name}說話"  # 待 joy 潤：一類一顆的交友只有一位說得上話的人物時，鈕上那一格（正式季整合 2.8）
SOCIAL_LIST_INTRO = "{here}有好幾位人物，挑一位說話。每位人物各算各的，最多談 {per_day} 輪，{again}；名望不夠的見不到。"  # 待 joy 潤（FB-421）
AUDIENCE_MEET = "先設法結識"  # 待 joy 潤：一類一顆的求見名單上，名望不夠、但這裡有他的結識事件的那一位


def talk_cap(ctx) -> int:
    """跟每位人物每個遊戲日能長情誼的輪數：talk_turns_per_day ＋ 玄紐（玉璽碎片設計 7.1）。心神關著時也就是能談的輪數。"""
    return ctx.content.config.talk_turns_per_day + round(treasures.amount(ctx.state, ctx.content, "talk_turns"))


def talk_full_cap(ctx) -> int:
    """跟每位人物每個遊戲日最多能談的輪數：心神開著時是 Config.xinshen.turns_per_figure（Joy 同意 8；玄紐給得更多時照玄紐），
    關著照舊 talk_cap。"""
    cap = talk_cap(ctx)
    return max(cap, ctx.content.config.xinshen.turns_per_figure) if xinshen.on(ctx.content) else cap


def talk_idle(ctx, companion_id: str) -> bool:
    """這一輪只是閒聊（心神開著、今天跟他長情誼的那幾輪用完了）：照樣聊、他照樣記得，情誼、心意、條件不再動。"""
    return xinshen.on(ctx.content) and talks_used(ctx, companion_id) >= talk_cap(ctx)


def talkable(ctx, companion_id: str) -> bool:
    """說得上話：見得到（名望或結識）、這個遊戲日還沒談滿、沒對你閉門不見。"""
    return figure_can_meet(ctx, companion_id) and talks_left(ctx, companion_id) > 0 and not ctx._snubbed_character(companion_id)


def why_not_talk(ctx, companion_id: str) -> str:
    if ctx._snubbed_character(companion_id):
        return SNUB_NOTE
    if not figure_can_meet(ctx, companion_id):
        return f"名望還差 {fame_gap(ctx, companion_id)}"
    return talked_out_note(ctx)


def meet_event(ctx, companion_id: str | None = None) -> Event | None:
    """這裡此刻抽得到的結識事件（照內容順序第一則）；給了 companion_id 只要結識他的那一則。"""
    for event in event_candidates(ctx.state, ctx.content, "socialize", "common"):
        met = precise.meets(event)
        if met and (companion_id is None or companion_id in met):
            return event
    return None


def fortune_free(ctx) -> str | None:
    """福緣送得出的那一位（可招募、還沒被人招走的第一位）；沒有是 None。"""
    candidates = [cid for cid, ch in ctx.content.characters.items() if ch.kind == "recruitable"]
    return next((cid for cid in candidates if roster.owned_by(ctx.world, cid) is None), None)


def social_plan(ctx) -> tuple[str | None, str | None]:
    """一類一顆的交友這一下會做什麼（選單、動作、對話備料、假人讀同一份）：
    ("fortune", None) 福緣的同伴入門；("once", None) 留在交友的一次性事件；("talk", 人物) 直接開口；("list", None) 兩位以上、打開名單；
    ("meet", 人物或 None) 見不到人、走結識事件；(None, 原因) 沒有人可以說話。"""
    s, c = ctx.state, ctx.content
    if roster.fortune_due(s, c) and fortune_free(ctx) is not None:  # 沒有同伴可給時不再送 30 心得（2.8【PM】）
        return "fortune", None
    if event_candidates(s, c, "socialize", "rare"):
        return "once", None
    people = ctx._figures_here()
    if len(people) >= AUDIENCE_HALL_FIGURES:
        if any(talkable(ctx, cid) or meet_event(ctx, cid) is not None for cid in people):
            return "list", None
        gaps = [cid for cid in people if not ctx._snubbed_character(cid) and not figure_can_meet(ctx, cid)]
        return None, why_not_talk(ctx, min(gaps, key=lambda cid: fame_gap(ctx, cid)) if gaps else people[0])
    if people and talkable(ctx, people[0]):
        return "talk", people[0]
    if meet_event(ctx) is not None:
        return "meet", None
    return None, why_not_talk(ctx, people[0]) if people else SOCIAL_NO_ONE


def figure_can_meet(ctx, companion_id: str) -> bool:
    """見得到這位人物：名望到了他的求見門檻，或是透過他的「結識」事件認識過（企劃者 2026-10-02 決定）。
    判斷在 rules.can_meet，伏筆的偷聽也用它。"""
    return core_can_meet(ctx.state, ctx.content, companion_id)


def public_can_meet(ctx, companion_id: str) -> bool:
    """見得到這位人物嗎（名望與陣營階級、或結識過）；機器人用來避開會被打發的求見。"""
    return ctx._can_meet(companion_id)


def fame_gap(ctx, companion_id: str) -> int:
    """離這位人物的求見門檻還差多少名望（門檻已含同陣營的階級折抵，見 rules.audience_bar）；見得到時不會拿來用。"""
    return audience_bar(ctx.state, ctx.content, companion_id) - ctx.state.player.stats.get("fame", 0)


def talks_used(ctx, companion_id: str) -> int:
    """這個遊戲日（rules.game_day，跟著季長縮）已經跟這位人物聊了幾輪；紀錄是別的號碼（前幾天的，或縮放之前照 24 小時
    記的舊帳）就當沒聊過。"""
    record = ctx.state.player.talks_today.get(companion_id)
    return record[1] if record and record[0] == game_day(ctx.content, ctx.state.world) else 0


def talks_left(ctx, companion_id: str) -> int:
    """這個遊戲日還能跟這位人物聊幾輪（心神開著時連閒聊的那幾輪，talk_full_cap）。"""
    return max(0, talk_full_cap(ctx) - talks_used(ctx, companion_id))


def talks_reopen(ctx) -> tuple[str, str | None]:
    """談滿了的人物什麼時候再見得到：此刻所在的遊戲日結束的那一刻，照季的時間寫法（rules.day_turn）；None＝這一季之內
    不會再換日（最後一個遊戲日、季末提前），句子改寫「這一季之內」（day-scale 審查 M2）；季末延後、換日在名義季長之後寫不出那一刻
    時是 ("later", None)，句子寫「過一陣子」（FB-102）。回傳 rules.day_turn 的（哪一種, 時刻）。"""
    return day_turn(ctx.content, ctx.state.world)


def deep_interaction_target(ctx) -> str | None:
    """這個地點此刻能深度對話的人物 id：見得到（名望或結識）、這個遊戲日還沒聊滿，也沒在對你閉門不見（T4）；沒有就是 None。"""
    for companion_id in ctx._figures_here():
        if figure_can_meet(ctx, companion_id) and talks_left(ctx, companion_id) > 0 and not ctx._snubbed_character(companion_id):
            return companion_id
    return None


def audience_hall(ctx) -> bool:
    """這裡有兩位以上的大勢人物：交友不再直接找第一位見得到的人，改按「求見」指名（企劃者 2026-10-03 決定）。"""
    return len(ctx._figures_here()) >= AUDIENCE_HALL_FIGURES


def socialize_figure(ctx) -> str | None:
    """交友會直接開口對話的那位人物：只有這裡至多一位大勢人物時才有（見得到、這個遊戲日還沒談滿，見
    deep_interaction_target）；兩位以上的地點交友只走福緣與地點事件，人物要按「求見」指名。"""
    if precise.on(ctx.content, ctx.state.world):  # 一類一顆：照 social_plan
        kind, arg = social_plan(ctx)
        return arg if kind == "talk" else None
    if audience_hall(ctx):
        return None
    return deep_interaction_target(ctx)


def talked_out_note(ctx) -> str:
    """談滿了的求見鈕括號裡那一句（單人地點的「求見某某」與求見名單共用；待 joy 潤）：寫換日的那一刻，不寫「今天／明天」
    ——週末那一季的一天不是 24 小時（企劃者 2026-10-08）。開頭一律是「已經談滿」：網頁行動列的格子認它，只寫「已談滿」（審查 I1）。"""
    kind, moment = talks_reopen(ctx)
    when = f"{moment} 之後再來" if moment else "過一陣子再來" if kind == "later" else "這一季之內不能再來"  # 「過一陣子」：FB-102
    return f"已經談滿 {talk_full_cap(ctx)} 輪，{when}"


def starts_dialogue(ctx) -> bool:
    """在這裡交友會直接跟大勢人物對話（伺服器假人不閒聊大勢人物，見 bot_policy）。在召見的地點不會：交友端出晉升奇遇。"""
    if precise.on(ctx.content, ctx.state.world):
        return ctx._socialize_figure() is not None  # 經 ctx：測試與腳本換掉 Game._socialize_figure，換掉的才打得到
    return ranks.summons_event(ctx.state, ctx.content) is None and ctx._socialize_figure() is not None


def is_futile(ctx) -> bool:
    """在這裡交友注定白跑一趟（伺服器假人不該去按）：這個地點沒有交友事件、沒有見得到的大勢人物，
    而且福緣還沒到期（交友最先發福緣，見 _act）。"""
    s, c = ctx.state, ctx.content
    if precise.on(c, s.world):  # 一類一顆：沒有人可以說話時鈕是灰的
        return social_plan(ctx)[0] is None
    return (
        not has_events_here(c, c.locations[s.player.location], "socialize")
        and ctx._socialize_figure() is None
        and not roster.fortune_due(s, c)
    )
