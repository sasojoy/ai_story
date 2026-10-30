"""特殊頓悟（企劃者 2026-10-26「合，開始開發」；設計稿 https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3，七項照建議、本命走甲）。

有所感選對做法、擲中進感悟狀態的那一刻再擲一次（Config.epiphany：這一季第一次 3%、第二次 1.5%、第三次 0.75%，悟性高過 5 每點
乘 1.05、最多乘 1.5；第一次有保底；新手期也擲，序章不擲）。中了不畫那一筆，改開一條「頓悟」的線（tianxia/storyline.py，程式組的線）：

| 關 | 是什麼 | 記號 |
|---|---|---|
| 一、心靈拷問（quiz） | 三題問心，一題問心中之形 | 每題的答案標一個型（攻守變心）+2，有的另標正或邪；心中之形標剛柔快慢 |
| 二、心境小試（task） | 一件引擎查得到的小事（TRIALS），沒有期限 | 做成了那件事自己的型 +1 |
| 三、心魔（fight） | 打自己的影子：難度＝你此刻的全隊威力 × demon_scale（StoryStage.mirror） | 打贏那一場靠哪一招最多（強攻攻、固守守、奇襲變，都沒有是心）+2 |

失敗可以重複挑戰（Joy 10/26「留住玩家很重要」）：拷問與小試沒有期限，心魔打輸了過 retry_days 個遊戲日再打、次數不限，所以沒有失敗的結局；
季末還沒過完的照一條線的規矩寫「此事未了」進傳。

心魔過了（END_HOOKS）挑模板：路＝做法的屬性與心中之形照合併的規則結合（insights.merged_attribute，八路）；善名到悟浩然的門檻、
拷問至少兩題選了正的改走「正」，惡名與邪一樣。型＝攻守變心記號最多的那一個（同分照天機｜名號｜第幾次的雜湊；手上已經有這個模板換次高的）。
挑好了存成待取名（PlayerState.god_naming）。按「靜心思名」（dunwu:think）才排候選：伺服器走三段式（A 在鎖內 Game.epiphany_request
開單、B 在鎖外 propose_names 請模型一次取三個、C 在鎖內 Game.epiphany_names 重驗、不夠三個用字表補）；假人也走同一條（bot_runner，
名字看不出是假人）；引擎直接按（整季機器人、測試、沒開模型）就是字表。也可以自己寫一個（過 naming.name_problem）。
名字這一季全服不重複（WorldState.god_names）。取了名收進自己的意境（sensing.add_own）：上品、那一路一般功效三重、真意是模板的戰法，
品相照 insight_fx.look 是「神」。寫進傳；這一季第一個悟出這個模板的寫進江湖史。

神品意境不能揣摩、不能拿去合成、熔不得（fusion.merge_problem、library.melt_insight_problem），身上同時只准裝一個（arts.slot_problem），
都認 insight_fx.is_god。
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from types import SimpleNamespace

from pydantic import BaseModel

from . import annals, insight_fx, insights, naming, storyline
from .martial_arts import Insight
from .models import (
    GOD_FORMS, Content, Effect, GodTrait, StoryAnswer, StoryDef, StoryEnding, StoryFail, StoryQuestion, StoryStage,
)
from .ollama_client import capped
from .rules import apply_effect, day_seconds
from .state import GameState, GodNaming, InsightFx, StoryProgress
from .world_state import WorldStateStore

KIND = "頓悟"  # StoryDef.kind（Config.jianfa.story_caps 的「頓悟」一條）
OPTION = "dunwu"  # 取名的選單：dunwu:think（靜心思名，排出候選）、dunwu:<候選序號>、dunwu:own（自己寫，走輸入框）
OWN = "own"
THINK = "think"
SHAPES = ("剛", "柔", "快", "慢")
SHAPE_MARK = "形"  # 心中之形的記號：「形剛」「形柔」…
RIGHT, WRONG = "正", "邪"
NAMES_OFFERED = 3
FALLBACK_TRIES = 12
IMAGE = {key: f"stories/dunwu_{key}" for key in ("enter", "demon", "done", "fail")}  # web/img/stories/dunwu_*.webp（Joy 10/26 給的圖）

# ── 玩家看得到的字 ──
TITLE = "特殊頓悟"
INTRO = "心念凝住的那一刻，四周忽然靜了下來。你沒有去畫那個形——它自己往心裡沉，沉到一個你從沒到過的地方。"
DONE_TEXT = "心魔散去，留下的是一個從沒有人走過的境界。"
DONE_ANNAL = "{name}頓悟，心魔已除。"
UNFINISHED = "{name}入了頓悟，心魔未除，到季末都沒有了結。"
ASK_HINT = "靜心自問"
DEMON_HINT = "去面對心魔"
DEMON_CARD = "你在心裡看見了一個人，跟你一模一樣，朝你走過來。"
# 心魔打輸了（還能再打）：跳一張卡（圖是 IMAGE["fail"]）、紀錄一行、行狀一行（Joy 2026-10-28「心魔挑戰失敗沒有明顯提示，我們不是有做圖片嗎」）
FAIL_TITLE = "心魔未破"
FAIL_CARD = "那個跟你一模一樣的人，這一次比你快了半步。\n\n這一關沒有過，前面問過的心、試過的手都還算數。過 {days}，可以再去面對它{weaker}。"
FAIL_WEAKER = "，它也會弱一些"
FAIL_LOG = "心魔未破：過 {days}可以再去面對它，前面過了的關都留著。"
FAIL_ANNAL = "{name}頓悟時與心魔一戰，未能破之。"
NAME_ASK = "替這個境界取個名字：挑一個，或自己寫一個。"
THINK_LABEL = "靜心思名"
THINK_ASK = "這個境界還沒有名字。靜下心來想一想，或者自己寫一個。"
NAME_OWN = "自己取一個名字…"
NAME_OWN_ASK = "（寫下你替它取的名字。）"
NAME_TAKEN = "這一季江湖上已經有一個神品意境叫這個名字了，換一個吧。"
GOT_LINE = "你悟得了神品意境「{name}」（屬{attribute}）！"
ONLY_ONE = "這是今生僅見的境界——江湖上不會有第二份同名的。"
FIRST_ANNAL = "{name}頓悟，悟出神品意境「{insight}」。"
FIRST_CHRONICLE = "{name}頓悟，悟出神品意境「{insight}」，這一季第一個走到這一境。"
SHAPE_QUESTION = "此刻你心裡浮起一個形。它像什麼？"
SHAPE_ANSWERS = {
    "剛": "一塊壓不碎的鐵",
    "柔": "一道繞過石頭的水",
    "快": "一道劃過天邊的電",
    "慢": "一座千年不動的山",
}
# 問心（三題，從這裡照種子挑）：每一個答案標一個型（攻守變心），有的另標正或邪
QUESTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("那日你放走的人，後來殺了人。你後悔嗎？", [
        ("後悔。下一次我會先出手。", "攻", ""), ("不後悔。我只能做我當下認為對的事。", "心", RIGHT),
        ("我會去找到他，親手了結這件事。", "變", ""), ("那是他的罪，不是我的。", "守", WRONG)]),
    ("有人擋在你的路上，不肯讓。", [
        ("推開他。", "攻", ""), ("等他自己讓開。", "守", ""), ("繞過去。", "變", ""), ("問他為什麼不讓。", "心", RIGHT)]),
    ("你最怕的是什麼？", [
        ("輸。", "攻", ""), ("護不住身邊的人。", "守", RIGHT), ("被人看穿。", "變", ""), ("忘了自己為什麼出發。", "心", "")]),
    ("一場仗打到一半，你發現自己站錯了邊。", [
        ("打完再說。", "攻", WRONG), ("收手，先護住自己人。", "守", ""), ("倒戈。", "變", ""), ("放下兵器，走進對面的陣裡。", "心", RIGHT)]),
    ("師父教你的那一招，你一直沒練成。", [
        ("再練一千遍。", "攻", ""), ("先把會的練到滴水不漏。", "守", ""), ("改成自己的招。", "變", ""), ("也許那一招本來就不是給我的。", "心", "")]),
    ("有人給你一把刀，說能殺盡天下惡人。", [
        ("接過來。", "攻", WRONG), ("不接，誰都不該有這種刀。", "守", RIGHT), ("接過來，然後折斷。", "變", ""), ("問他自己為什麼不用。", "心", "")]),
    ("你一個人走在夜路上，後面有腳步聲。", [
        ("回頭迎上去。", "攻", ""), ("停下來，背靠著牆。", "守", ""), ("加快腳步，找個轉角等他。", "變", ""), ("照原來的步子走。", "心", "")]),
    ("餓了三天的人搶了你的乾糧。", [
        ("追上去拿回來。", "攻", WRONG), ("算了，分他一半。", "守", RIGHT), ("跟著他，看他要拿去哪。", "變", ""), ("想起自己也餓過。", "心", RIGHT)]),
]
ASKED = 3
# 心境小試（引擎查得到的小事）：名字 → （「未了之事」那一行寫的這一步、做成了加哪一型）
WAIT = "wait"  # 靠時間的那一種小試：等 Config.epiphany.trial_wait_days 個遊戲日（別的三種靠玩家動手）
TRIALS: dict[str, tuple[str, str]] = {
    "win": ("出手打贏一場", "攻"),
    "terrain": ("到{tag}靜坐", "守"),
    "roam": ("四處探訪三回", "變"),
    # 以前寫「靜候一日」：等多久改成設定之後這句話就會騙人（同心魔那一句，FB-900），
    # 所以話裡不寫時間，還要多久由選單那一行的倒數寫（storyline.TASK_LEFT，FB-902）
    WAIT: ("靜候，什麼都別急", "心"),
}
TERRAINS = ("山林", "河畔", "野外", "寺院", "古戰場")
MOVE_FORMS = {"強攻": "攻", "固守": "守", "奇襲": "變"}
START = "_t0"  # 小試開始的那一刻（世界秒，取整）、與那一刻的探索次數：存在線的記號裡（底線開頭，不參與挑型）
START_ROAM = "_roam0"
TAG = "_tag"  # 靜坐要去的地形：TERRAINS 的第幾個


def rules(content: Content):
    return content.config.epiphany


def on(content: Content, state: GameState) -> bool:
    return rules(content).enabled and storyline.on(content, state)


def _seed(state: GameState, *parts: object) -> str:
    return "|".join(str(x) for x in (state.world.tianji, KIND, state.player.name, state.player.epiphanies, *parts))


def _rng(state: GameState, *parts: object) -> random.Random:
    return random.Random(hashlib.sha256(_seed(state, *parts).encode("utf-8")).hexdigest())


def busy(state: GameState, content: Content) -> bool:
    """還有一條頓悟的線沒收、或悟了還沒取名：不再擲（同時只有一個）。"""
    if state.player.god_naming is not None:
        return True
    return any((d := storyline.definition(content, pr)) is not None and d.kind == KIND for pr in storyline.active(state))


def chance(state: GameState, content: Content) -> float:
    """這一次擲中感悟時頓悟的機率：這一季第幾次照 chances，悟性高過 wis_from 每點乘 1 + wis_step（最多 wis_cap）；列完是 0。"""
    r = rules(content)
    n = state.player.epiphanies
    if n >= len(r.chances):
        return 0.0
    wis = state.player.stats.get("wis", 5)
    return min(1.0, r.chances[n] * min(r.wis_cap, (1 + r.wis_step) ** max(0, wis - r.wis_from)))


def roll(state: GameState, content: Content, rng, boost: float = 1.0) -> bool:
    """擲中感悟（sensing.choose 進了感悟狀態）之後擲一次：中了回真（呼叫端收掉那一份感悟、開線）。關著、序章（呼叫端不叫）、
    還有一條沒收、這一季次數用完都不擲（不動 rng）。第一次有保底：這一季擲中感悟 pity 次都沒中，下一次必中。
    boost：走一趟的稀有倍數（outing.rare_boost），乘在機率上。"""
    if not on(content, state) or busy(state, content):
        return False
    p = state.player
    odds = chance(state, content)
    if odds <= 0:
        return False
    pity = rules(content).pity
    if p.epiphanies == 0 and pity and p.epiphany_dry >= pity:
        return True
    if rng.random() < odds * boost:
        return True
    p.epiphany_dry += 1
    return False


# ── 組線 ──────────────────────────────────────────────


def _questions(state: GameState) -> list[StoryQuestion]:
    picked = _rng(state, "問").sample(range(len(QUESTIONS)), ASKED)
    out = []
    for i in picked:
        text, answers = QUESTIONS[i]
        out.append(StoryQuestion(text=text, answers=[
            StoryAnswer(text=a, marks={form: 2, **({lean: 1} if lean else {})}) for a, form, lean in answers
        ]))
    out.append(StoryQuestion(text=SHAPE_QUESTION, answers=[
        StoryAnswer(text=SHAPE_ANSWERS[shape], marks={f"{SHAPE_MARK}{shape}": 1}) for shape in SHAPES
    ]))
    return out


def _trial(state: GameState, content: Content) -> tuple[str, str, int]:
    """這一次的小試：（名字, 「未了之事」那一行, 靜坐的地形是 TERRAINS 的第幾個，不是靜坐是 -1）。靜坐挑內容裡有、此刻腳下不是的地形。"""
    rng = _rng(state, "試")
    name = rng.choice(sorted(TRIALS))
    if name != "terrain":
        return name, TRIALS[name][0], -1
    here = set(content.locations[state.player.location].tags) if state.player.location else set()
    have = {t for loc in content.locations.values() for t in loc.tags}
    tags = [i for i, t in enumerate(TERRAINS) if t in have and t not in here]
    if not tags:
        return "wait", TRIALS["wait"][0], -1
    i = rng.choice(tags)
    return name, TRIALS[name][0].format(tag=TERRAINS[i]), i


def build(state: GameState, content: Content, method: str) -> tuple[StoryDef, dict[str, int]]:
    """這一次頓悟的線（整份存進進度：storyline.start custom）與開線時要先記下的記號：做法的屬性（剛柔快慢）記成「法剛」…，
    小試是靜坐時記要去的地形（TAG）。"""
    r = rules(content)
    n = state.player.epiphanies + 1
    trial, hint, tag = _trial(state, content)
    stages = [
        StoryStage(id="ask", kind="quiz", questions=_questions(state), hint=ASK_HINT, next="trial", immediate=False),
        StoryStage(id="trial", kind="task", task=f"{KIND}:{trial}", hint=hint, next="demon"),
        StoryStage(id="demon", kind="fight", mirror=r.demon_scale, hint=DEMON_HINT, card=DEMON_CARD, image=IMAGE["demon"],
                   mirror_weaken=r.demon_weaken, mirror_floor=r.demon_floor,
                   retries=10**6, retry_days=r.retry_days, win="done", lose="done",
                   fail=StoryFail(title=FAIL_TITLE, card=FAIL_CARD.replace("{weaker}", FAIL_WEAKER if r.demon_weaken > 0 else ""),
                                  log=FAIL_LOG, annal=FAIL_ANNAL, image=IMAGE["fail"])),
    ]
    ending = StoryEnding(id="done", title="悟成", text=DONE_TEXT, annal=DONE_ANNAL, image=IMAGE["done"])
    line = StoryDef(id=f"{KIND}{n}", title=TITLE, kind=KIND, image=IMAGE["enter"], intro=INTRO, stages=stages, endings=[ending],
                    unfinished=UNFINISHED)
    return line, {f"法{method}": 1, **({TAG: tag} if tag >= 0 else {})}


def begin(state: GameState, content: Content, method: str, place: str) -> StoryProgress | None:
    """中了：開線、記下做法與小試的地形，這一季頓悟次數 +1、保底歸零。開不了（沒空位）是 None。"""
    line, marks = build(state, content, method)
    progress = storyline.start(state, content, line)
    if progress is None:
        return None
    progress.marks.update(marks)
    progress.said.append(place)  # 在哪裡悟的：收尾寫傳與取名用（said 是這條線自己留的字，頓悟沒有隨口應對）
    state.player.epiphanies += 1
    state.player.epiphany_dry = 0
    return progress


# ── 小試（storyline.TASKS）──────────────────────────────


def _mark_start(state: GameState, progress: StoryProgress) -> None:
    if START not in progress.marks:
        progress.marks[START] = int(state.world.time)
        progress.marks[START_ROAM] = state.player.explore_seq


def _done(progress: StoryProgress, trial: str) -> bool:
    form = TRIALS[trial][1]
    progress.marks[form] = progress.marks.get(form, 0) + 1
    return True


def _task(trial: str):
    def check(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, stage: StoryStage) -> bool:
        _mark_start(state, progress)
        p = state.player
        since = progress.marks[START]
        if trial == "win":
            ok = any(b.time >= since and b.tier in ("大勝", "險勝") for b in state.battles)
        elif trial == "terrain":
            tag = TERRAINS[progress.marks.get(TAG, 0)]
            ok = p.location is not None and p.journey is None and tag in content.locations[p.location].tags
        elif trial == "roam":
            ok = p.explore_seq - progress.marks[START_ROAM] >= 3
        else:
            ok = _wait_left(state, content, progress) is None
        return _done(progress, trial) if ok else False
    return check


for _name in TRIALS:
    storyline.TASKS[f"{KIND}:{_name}"] = _task(_name)


def _wait_left(state: GameState, content: Content, progress: StoryProgress) -> float | None:
    """「靜候」那一種小試還差幾世界秒（到了、或還沒開始算就是 None）。

    每次都照此刻的 `Config.epiphany.trial_wait_days` 算，所以改了設定對**正在走的線**也立刻生效
    （FB-902：7 天的季裡「一日」是真實 24 小時，玩家卡在這一步、畫面上又什麼都看不到）。"""
    since = progress.marks.get(START)
    if since is None:
        return None
    left = since + rules(content).trial_wait_days * day_seconds(content, state.world) - state.world.time
    return left if left > 0 else None


storyline.TASK_LEFT[f"{KIND}:{WAIT}"] = _wait_left


def _refresh(content: Content, line: StoryDef) -> StoryDef:
    """每次讀這一條線都照此刻的設定重算心魔那一關的數字（storyline.REFRESH_HOOKS）：
    線是程式組的、整份存在 progress.custom 裡，不這樣做的話改了設定只對之後新開的線有效。"""
    r = rules(content)
    stages = [
        s.model_copy(update={"retry_days": r.retry_days, "mirror_weaken": r.demon_weaken,
                             "mirror_floor": r.demon_floor, "mirror": r.demon_scale})
        if s.kind == "fight" and s.mirror is not None else
        # 「靜候」那一段的 hint：以前寫死「靜候一日」，等多久變成設定之後那句話會騙人（FB-902）。
        # 進行中的線 hint 是存檔裡那一份，所以這裡也換成新的那一句（還要多久由倒數寫）
        s.model_copy(update={"hint": TRIALS[WAIT][0]}) if s.task == f"{KIND}:{WAIT}" else s
        for s in line.stages
    ]
    return line.model_copy(update={"stages": stages})


storyline.REFRESH_HOOKS[KIND] = _refresh


# ── 心魔（storyline.FIGHT_HOOKS）──────────────────────────


def _fought(state: GameState, content: Content, progress: StoryProgress, stage: StoryStage, record) -> None:
    """心魔打完：贏了照戰報的回合數哪一招最多（強攻攻、固守守、奇襲變），那一型 +2；都沒有是心。輸了不記（再打一次）。"""
    if record.tier not in ("大勝", "險勝"):
        return
    counts = {form: sum(line.count(move) for line in record.rounds) for move, form in MOVE_FORMS.items()}
    best = max(counts, key=lambda f: (counts[f], f)) if any(counts.values()) else "心"
    progress.marks[best] = progress.marks.get(best, 0) + 2


storyline.FIGHT_HOOKS[KIND] = _fought


# ── 挑模板 ─────────────────────────────────────────────


def owned_templates(state: GameState) -> set[str]:
    return {fx.grand for fx in state.player.insight_fx.values() if fx.grand and fx.grand.startswith(insight_fx.GOD_PREFIX)}


def path_of(state: GameState, content: Content, progress: StoryProgress) -> tuple[str, str]:
    """路：（屬性, 正邪）。做法與心中之形照合併的規則結合成八路之一；善名到悟浩然的門檻、拷問至少兩題選了正的走正（陽），
    惡名到悟血煞的門檻、至少兩題選了邪的走邪（陰）。"""
    m = progress.marks
    method = next((k[1:] for k in m if k.startswith("法")), "剛")
    shape = next((k[len(SHAPE_MARK):] for k in m if k.startswith(SHAPE_MARK)), method)
    attribute = insights.merged_attribute(
        SimpleNamespace(id=method, attribute=method), SimpleNamespace(id=shape, attribute=shape), _seed(state, "路"),
    )
    stats = state.player.stats
    for lean, insight_id, attr in ((RIGHT, "haoran", "陽"), (WRONG, "xuesha", "陰")):
        grant = content.insights[insight_id].grant if insight_id in content.insights else None
        if m.get(lean, 0) >= 2 and grant is not None and stats.get(grant.stat, 0) >= grant.at:
            return attr, lean
    return attribute, "無"


def pick(state: GameState, content: Content, progress: StoryProgress) -> GodTrait | None:
    """挑模板：先定路，再照攻守變心的記號挑型（同分照種子；手上已經有的換次高的）。這一路一個都沒有是 None。"""
    attribute, lean = path_of(state, content, progress)
    pool = {g.form: g for g in content.traits.god if g.attribute == attribute and g.lean == lean}
    if not pool:
        return None
    m = progress.marks
    salt = {form: hashlib.sha256(_seed(state, "型", form).encode("utf-8")).digest()[0] for form in GOD_FORMS}
    order = sorted(pool, key=lambda f: (-m.get(f, 0), salt[f]))
    have = owned_templates(state)
    return next((pool[f] for f in order if pool[f].id not in have), pool[order[0]])


def _taken(state: GameState, world: WorldStateStore, name: str) -> bool:
    return name in world.get_season().god_names or name in {i.name for i in state.player.own_insights.values()} or world.is_character_name(name)


def candidates(state: GameState, content: Content, world: WorldStateStore, god: GodTrait) -> list[str]:
    """三個候選的名字（字表；同一季同一個人同一次頓悟永遠一樣）：過不了名字檢查、這一季全服用掉了、自己手上有的都換。"""
    out: list[str] = []
    tianji = state.world.tianji
    for salt in range(FALLBACK_TRIES * NAMES_OFFERED):
        name = naming.fallback_name(content, _seed(state, "名", god.id), "意境", salt=salt, tianji=tianji)
        if name not in out and not _taken(state, world, name) and naming.name_problem(name, content) is None:
            out.append(name)
        if len(out) == NAMES_OFFERED:
            break
    return out


def _end(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, ending) -> list[str]:
    """收尾鉤子：心魔過了挑模板、排好候選的名字等著取名；季末未了（ending 是 None）什麼都不做（傳已經寫了此事未了）。"""
    if ending is None or world is None:
        return []
    god = pick(state, content, progress)
    if god is None:
        return []
    place = progress.said[0] if progress.said else ""
    asked = [q.text for q in (progress.custom.stages[0].questions if progress.custom else [])]
    state.player.god_naming = GodNaming(
        line=progress.line, god=god.id, attribute=god.attribute, lean=god.lean, place=place, answers=asked,
    )
    return [THINK_ASK]


storyline.END_HOOKS[KIND] = _end


# ── 取名、收進意境 ───────────────────────────────────────


def menu(state: GameState) -> list[tuple[str, str]]:
    """等著取名時的選單：還沒想過名字是「靜心思名」＋自己寫；想過了是三個候選＋自己寫。"""
    naming_ = state.player.god_naming
    if naming_ is None:
        return []
    if not naming_.asked:
        return [(f"{OPTION}:{THINK}", THINK_LABEL), (f"{OPTION}:{OWN}", NAME_OWN)]
    return [(f"{OPTION}:{i}", name) for i, name in enumerate(naming_.candidates)] + [(f"{OPTION}:{OWN}", NAME_OWN)]


def _god(content: Content, god_id: str) -> GodTrait | None:
    return next((g for g in content.traits.god if g.id == god_id), None)


@dataclass(frozen=True)
class NameAsk:
    """A 段開的單（鎖內、只讀）：哪一條線、哪一個模板，送模型的訊息。拿著它就能在鎖外叫模型，不必再碰遊戲狀態。"""

    line: str
    god: str
    messages: list[dict[str, str]]


class GodNames(BaseModel):
    """模型唯一被允許回傳的東西：三個名字。沒有任何數字欄位。"""

    names: list[str]


NAME_PROMPT = (
    "有一個武人在{place}頓悟，打敗了自己的心魔，悟出一個從沒有人走過的意境。\n"
    "這個意境屬「{attribute}」{lean}，路數是「{form}」：{desc}\n"
    "他頓悟時心裡問過自己：{asked}\n"
    "請替這個意境取三個不同的名字，要有境界感、像一句意象，不要直接寫屬性或招式的字眼。\n"
    "names：三個名字，每個 {low}～{high} 個中文字，必須原創，不可使用金庸等武俠小說裡的專有名詞，不要標點符號。"
)
FORM_WORDS = {"攻": "以攻為先", "守": "以守為本", "變": "以變制勝", "心": "以心馭招"}


def name_request(state: GameState, content: Content) -> NameAsk | None:
    """A 段（行動鎖內、很快、只讀）：還沒想過名字的那一個神品，開一張請模型取三個名字的單；不在等著取名、已經想過了是 None。"""
    naming_ = state.player.god_naming
    if naming_ is None or naming_.asked:
        return None
    god = _god(content, naming_.god)
    if god is None:
        return None
    lean = {"正": "，走正道", "邪": "，走邪路"}.get(god.lean, "")
    prompt = NAME_PROMPT.format(
        place=naming_.place or "江湖上", attribute=god.attribute, lean=lean, form=FORM_WORDS.get(god.form, god.form), desc=god.desc,
        asked="；".join(naming_.answers) or "（沒有說出口）", low=naming.NAME_MIN_CHARS, high=naming.NAME_MAX_CHARS,
    )
    messages = [{"role": "system", "content": naming.SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    return NameAsk(naming_.line, god.id, messages)


def propose_names(
    client, content: Content, ask: NameAsk, budget: float | None = None, person: naming.PersonCheck | None = None,
) -> list[str]:
    """B 段（鎖外、很慢，不碰狀態、不拿鎖）：請模型一次取三個名字，每個過一次名字檢查（給了 person 也擋角色的名號）；
    連不上、逾時、取壞了都是空的（C 段用字表補）。只叫一次，預算照 naming 的分法（一次最多兩趟）。"""
    if client is None:
        return []
    caller = client
    if budget is not None:
        per_post = naming.per_post_seconds(client, budget)
        if per_post is None:
            return []
        caller = capped(client, per_post)
    try:
        reply = caller.chat_structured(ask.messages, GodNames, required_fields=["names"])
    except Exception:  # noqa: BLE001  連不上、404、逾時——一律當作沒拿到
        return []
    out: list[str] = []
    for raw in (reply.names if reply is not None else [])[: NAMES_OFFERED * 2]:
        name = naming.clean_name(raw if isinstance(raw, str) else "")
        if name and name not in out and naming.name_problem(name, content, person) is None:
            out.append(name)
    return out[:NAMES_OFFERED]


def fill(state: GameState, content: Content, world: WorldStateStore, ask: NameAsk | None, names: list[str]) -> list[str]:
    """C 段（鎖內）：還在等同一個神品的名字（ask 是 None＝引擎直接按，不核對單子）才排候選：模型給的名字重驗一次
    （名字檢查、這一季全服用掉了、自己手上有的都不收），不夠三個用字表補。回那一句叫人挑。"""
    naming_ = state.player.god_naming
    if naming_ is None or naming_.asked or (ask is not None and (ask.line != naming_.line or ask.god != naming_.god)):
        return []
    god = _god(content, naming_.god)
    if god is None:
        return []
    out: list[str] = []
    for raw in names:
        name, _ = naming.recheck(content, (raw, ""), world.is_character_name)
        if name and name not in out and not _taken(state, world, name):
            out.append(name)
    for name in candidates(state, content, world, god):
        if len(out) >= NAMES_OFFERED:
            break
        if name not in out:
            out.append(name)
    naming_.candidates, naming_.asked = out[:NAMES_OFFERED], True
    return [NAME_ASK]


def scene_text(state: GameState, content: Content) -> str:
    """取名那一張場景：這一境是哪一路、真意寫什麼，叫人取名（Markdown）。"""
    naming_ = state.player.god_naming
    god = _god(content, naming_.god) if naming_ is not None else None
    if god is None:
        return ""
    return f"**{TITLE}・悟成**\n\n{DONE_TEXT}\n\n> 屬{god.attribute}・{god.desc}\n\n{NAME_ASK if naming_.asked else THINK_ASK}"


def name_problem(state: GameState, content: Content, world: WorldStateStore, name: str) -> str | None:
    problem = naming.name_problem(name, content, person=world.is_character_name)
    if problem is not None:
        return problem
    if _taken(state, world, name):
        return NAME_TAKEN
    return None


def choose(state: GameState, content: Content, world: WorldStateStore, arg: str, text: str | None = None) -> list[str]:
    """選了一個候選（dunwu:<序號>）或自己寫（dunwu:own，text 是寫的名字；沒寫只回一句叫出輸入框）。"""
    naming_ = state.player.god_naming
    if naming_ is None:
        return ["（此刻無法這麼做。）"]
    if arg == THINK:  # 引擎直接按（伺服器與假人程式在外面走三段式，交給 fill）：字表
        return fill(state, content, world, None, []) or ["（此刻無法這麼做。）"]
    if arg == OWN:
        name = naming.clean_name(text or "")
        if not name:
            return [NAME_OWN_ASK]
    elif naming_.asked and arg.isdecimal() and int(arg) < len(naming_.candidates):
        name = naming_.candidates[int(arg)]
    else:
        return ["（此刻無法這麼做。）"]
    problem = name_problem(state, content, world, name)
    if problem is not None:
        return [problem]
    return grant(state, content, world, name)


def grant(state: GameState, content: Content, world: WorldStateStore, name: str) -> list[str]:
    """登記名字（這一季全服不重複，鎖內原子：mutate_season 裡再查一次），收進自己的意境，寫傳；這一季第一個悟出這個模板的上江湖史。"""
    from . import sensing  # noqa: PLC0415  sensing → insights → …

    p = state.player
    naming_ = p.god_naming
    god = next(g for g in content.traits.god if g.id == naming_.god)
    claimed: dict[str, bool] = {}

    def claim(season) -> None:
        claimed["ok"] = name not in season.god_names
        if claimed["ok"]:
            season.god_names[name] = p.name
            claimed["first"] = god.id not in season.god_firsts
            if claimed["first"]:
                season.god_firsts[god.id] = f"{name}|{p.name}"

    season = world.mutate_season(claim)
    if not claimed["ok"]:
        return [NAME_TAKEN]
    state.world.god_names, state.world.god_firsts = dict(season.god_names), dict(season.god_firsts)
    own = sensing.add_own(state, Insight(
        id="", name=name, attribute=god.attribute, lean=god.lean, note=god.desc, creator=p.name, creator_shown=p.name, place=naming_.place,
    ))
    p.insight_fx[own.id] = InsightFx(quality=insight_fx.QUALITIES[-1], general={god.general: insight_fx.MAX_LAYERS}, grand=god.id)
    p.god_naming = None
    annals.note(state, content, annals.STORY, FIRST_ANNAL.format(name=p.name, insight=name), 5)
    msgs = [GOT_LINE.format(name=name, attribute=god.attribute), god.desc, ONLY_ONE]
    if claimed.get("first"):
        msgs += apply_effect(Effect(chronicle=FIRST_CHRONICLE.format(name="{name}", insight=name)), state, content, world)
    return msgs
