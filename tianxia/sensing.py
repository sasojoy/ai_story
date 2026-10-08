"""有所感（悟意境設計第零節；企劃者 2026-10-06「甲案加乙案」）：探索落在悟意境那一支、這一處有場景時，不再直接悟到，
而是跳出一張「有所感」的卡：

1. 場景＋三四個做法（甲案）。選的做法屬性在這一處悟得到的意境裡才算選對；選錯什麼都沒悟到，這一處到換日之前不能再悟（Q2；遊戲日跟著季長縮）。
2. 選對還要擲一次（Q3）：七成，悟性每點 ±3%，夾在 40～95；這一處悟成過的人越多越容易（模糊人數每一檔 +3%，最多 +9%，Q7）。
   沒擲中給一點心得（「差一點就抓到了」）。
3. 擲中就進感悟狀態（乙案）：玩家一筆畫下心中的形。規則讀那一筆的屬性（glyph.py），跟做法的屬性用合併的規則結合
   （insights.merged_attribute）。結合出來的剛好是這一處的基本意境就是悟到它；不是的話交給模型看圖取名，
   悟到一個**自己的**意境（0.2b：存在自己的存檔，id「悟:流水號」，名字不要求全服唯一）。
4. 不想畫可以「順其自然」：當成畫出來跟做法同一個屬性，落回這一處的基本意境，不叫模型。

序章草廬那一段（InsightScene.prologue）：四個做法都對、必中（擲骰交給呼叫端的 SureRandom），畫什麼都落回做法那個基本意境。
這個模組只改狀態、回訊息；江湖紀錄、首悟紀錄、引導在 engine。看圖取名走三段式：request（A，鎖內、只讀）→
insight_llm.name（B，鎖外）→ finish（C，鎖內，重驗才套用）。"""
from __future__ import annotations

import random
from types import SimpleNamespace

from pydantic import BaseModel, Field

from . import glyph, insight_llm, insights, naming
from .martial_arts import Insight
from .models import Content, InsightScene, Location
from .ollama_client import OllamaClient
from .rules import day_ends_text, game_day
from .state import GameState, Sensing
from .world_state import WorldStateStore

MARK = "悟"  # 地方痕跡的名字：「地點 id:悟」，這一處悟成過幾個人（rules.add_marks，一人一個遊戲日只算一次）
DRAW = "sense:draw"  # 感悟狀態的「畫下來」：按下去只叫出畫布，真正送出走 request／finish
LET_GO = "sense:let"  # 「順其自然」：不畫了，落回做法那個基本意境
PREFIX = "sense:"
FALLBACK_TRIES = 8  # 退路字表換名字最多試幾次（跟自己手上的意境、江湖上的名號撞名就換）
STALE = "（那一刻已經過去了，心中的形也散了。）"
# 選做法之前卡上先說選錯的代價（explain-1；待 joy 潤）：跟 choose 的規則一樣——選錯了這一處到換日之前不再悟（missed_today）。
# 換日照遊戲日（rules.game_day，跟著季長縮，企劃者 2026-10-08）：週末那一季一天不是 24 小時，所以不寫「今天」，寫換日的那一刻
# （rules.day_ends_text：第一季是季曆的寫法，開關關著是「第N天 HH:MM」）。序章草廬不寫（做法都對）
MISS_WARNING = "選錯了做法，這裡要到 {moment} 之後才悟得出。"
MISS_LINE = "心浮氣躁，什麼也沒抓住。要到 {moment} 之後，這裡才悟得出東西。"  # 選錯了的那一句（待 joy 潤）
# 換日寫不出來（這一季最後一個遊戲日、季末延後或提前，rules.day_ends_text 是 None）時的兩句（day-scale 審查 M2；待 joy 潤）
MISS_WARNING_SEASON = "選錯了做法，這一季之內在這裡就悟不出了。"
MISS_LINE_SEASON = "心浮氣躁，什麼也沒抓住。這一季之內，這裡是悟不出東西了。"
# 選做法那一步的提示（explain-2 第三項，FB-100「有所感只能用猜的、略過序章的人不知道意境是什麼」；待 joy 潤）：
# 標題後面寫這一處的地形（地點的標籤）、每個做法的鈕上寫它是哪一種心意（做法自己的屬性），做法底下兩行小字（網頁排在鈕的下面，
# 不把做法往下推）：做法跟此地的關係、意境拿來做什麼。全都不看這一處悟得到哪一種（不讀 pool_attributes）：哪一個做法是對的，
# 卡上看不出來——四個做法換哪一個是對的，卡上的字一個都不變。場景的文字是 joy 的，不動。序章草廬（做法都對）不加。
FRAMING = "做法各是一種心意（{kinds}），跟此地景致合得上的那一種，才悟得出這裡的意境。"
INSIGHT_LINE = "意境能融進武學出新招、兩兩合成新的意境；融過它的武學，要靠它修練衝品質。"


def mark_key(location: str) -> str:
    return f"{location}:{MARK}"


def can_sense(state: GameState, content: Content, loc: Location) -> bool:
    """探索落在悟意境那一支時，這一處走不走「有所感」：有場景就走（序章的草廬另外由 prologue.explore_scene 指定）。"""
    return bool(content.insight_scenes) and bool(insights.scenes_for(loc, content))


def missed_today(state: GameState, content: Content, loc: Location) -> bool:
    """這個遊戲日在這一處選錯過做法：探索不再落在悟意境那一支（Q2，換日就好；遊戲日跟著季長縮，rules.game_day）。
    帳上記的是別的號碼（前幾天的，或縮放之前照 24 小時記的舊帳）就當沒選錯過。"""
    return state.player.sense_misses.get(loc.id) == game_day(content, state.world)


def _until(template: str, season_line: str, state: GameState, content: Content) -> str:
    """寫得出換日的那一刻就填進 template，寫不出來（這一季之內不會再換日）用 season_line。"""
    moment = day_ends_text(content, state.world)
    return template.format(moment=moment) if moment else season_line


def miss_warning(state: GameState, content: Content) -> str:
    """選做法之前卡上那一行：選錯了要到哪一刻之後才悟得出（此刻所在的遊戲日結束的那一刻）。"""
    return _until(MISS_WARNING, MISS_WARNING_SEASON, state, content)


def start(state: GameState, content: Content, scene: InsightScene, rng: random.Random) -> list[str]:
    """有所感：存一份待決的感悟，做法洗牌。卡片本身由 scene_text 畫。"""
    p = state.player
    p.sense_serial += 1
    order = list(range(len(scene.methods)))
    rng.shuffle(order)
    p.sensing = Sensing(location=p.location, scene=scene.id, order=order, serial=p.sense_serial)
    return [f"你在{content.locations[p.location].name}停下腳步，心有所感。"]


def pick_scene(loc: Location, content: Content, rng: random.Random) -> InsightScene:
    return rng.choice(insights.scenes_for(loc, content))


def current(state: GameState, content: Content) -> tuple[Sensing, InsightScene, Location] | None:
    """還在有所感：（那一份, 場景, 地點）；作廢的（人走了、場景被拿掉、順序對不上）是 None。"""
    s = state.player.sensing
    if s is None:
        return None
    scene = content.insight_scenes.get(s.scene)
    loc = content.locations.get(s.location)
    if scene is None or loc is None or state.player.location != s.location or sorted(s.order) != list(range(len(scene.methods))):
        return None
    if s.stage == "draw" and s.method not in {m.attribute for m in scene.methods}:
        return None
    return s, scene, loc


def drop_stale(state: GameState, content: Content) -> None:
    """讀檔、同步時：作廢的感悟拿掉（內容改版、人被帶走），選單才不會卡住。"""
    if state.player.sensing is not None and current(state, content) is None:
        state.player.sensing = None


def _tier(n: int) -> int:
    """模糊人數的第幾檔（rules.fuzzy_count）：還沒有人 0、一兩個人 1、幾個人 2、十來個人以上 3。"""
    return 0 if n <= 0 else 1 if n <= 2 else 2 if n <= 9 else 3


def rate(state: GameState, content: Content, loc: Location) -> int:
    """選對做法之後進入感悟狀態的成功率（%）：七成，悟性每點 ±3%，夾在 40～95；再加這一處的痕跡（每檔 +3%，最多 +9%）。
    卡上不寫這個數字（Q4：只有場景線索，不寫成算）。"""
    cfg = content.config
    wis = state.player.stats.get("wis", 5)
    low, high = cfg.sense_rate_range
    base = min(max(cfg.sense_rate + (wis - 5) * cfg.sense_rate_per_wis, low), high)
    bonus = min(cfg.sense_marks_cap, _tier(state.world.marks.get(mark_key(loc.id), 0)) * cfg.sense_marks_bonus)
    return base + bonus


def place_tags(scene: InsightScene, loc: Location) -> str:
    """標題後面括號裡的地形：這一處的地點標籤（河畔、城鎮……；「哪裡悟得到什麼看地形」）。序章草廬不寫；沒有標籤是空字串。"""
    return "" if scene.prologue or not loc.tags else f"（{'、'.join(loc.tags)}）"


def scene_text(state: GameState, content: Content) -> str:
    """場景那一塊（Markdown）：標題（後面括號寫這一處的地形，explain-2）、場景；進了感悟狀態再接一句叫人畫下來。"""
    got = current(state, content)
    if got is None:
        return ""
    s, scene, loc = got
    marks = insights_marks(state, loc)
    text = scene.text.replace("{痕跡}", marks)
    title = f"**有所感・{scene.title}**{place_tags(scene, loc)}"  # 地形跟標題同一行：不多佔高度
    if s.stage == "draw":
        method = next(m for m in scene.methods if m.attribute == s.method)
        return (
            f"{title}\n\n{text}\n\n你{method.text}——心念漸漸凝住了。"
            "此刻心中有一個形：一筆畫下來，手指離開就算畫完。"
        )
    # 選做法這一步：底下一小行（引用寫法，網頁畫成場景裡的小字淡色，比一整段內文矮）說選錯的代價；序章四景做法都對，不寫
    warning = "" if scene.prologue else f"\n\n> {miss_warning(state, content)}"
    return f"{title}\n\n{text}{warning}"


def method_help(state: GameState, content: Content) -> dict | None:
    """選做法那一步，網頁畫在做法上與做法底下的提示（explain-2）：tags＝選項 id → 那個做法是哪一種心意（鈕上原本寫 1～4 的那一格
    改寫它，不多佔寬度），lines＝做法底下的兩行小字（FRAMING、INSIGHT_LINE）。只讀做法自己的屬性與這張卡上有哪幾種，
    不讀這一處悟得到什麼：哪一個是對的看不出來。不在選做法這一步、或是序章草廬：None。"""
    got = current(state, content)
    if got is None or got[0].stage != "choose" or got[1].prologue:
        return None
    s, scene, _ = got
    # 照固定的順序（剛柔快慢）列，不照內容寫的順序：內容裡常把對的那一個寫在最前面，照它列就等於說出答案
    present = {m.attribute for m in scene.methods}
    kinds = "、".join(a for a in insights.SENSE_ATTRIBUTES if a in present)
    return {
        "tags": {f"{PREFIX}{i}": scene.methods[j].attribute for i, j in enumerate(s.order)},
        "lines": [FRAMING.format(kinds=kinds), INSIGHT_LINE],
    }


def insights_marks(state: GameState, loc: Location) -> str:
    from .rules import fuzzy_count  # noqa: PLC0415  rules → insights → …，延後免得循環

    return fuzzy_count(state.world.marks.get(mark_key(loc.id), 0))


def menu(state: GameState, content: Content) -> list[tuple[str, str]]:
    """選單（id, 字）：還沒選是洗過牌的做法；進了感悟狀態是「畫下來」與「順其自然」。"""
    got = current(state, content)
    if got is None:
        return []
    s, scene, _ = got
    if s.stage == "draw":
        return [(DRAW, "把心中的形畫下來"), (LET_GO, "不畫了，順其自然")]
    return [(f"{PREFIX}{i}", scene.methods[j].text) for i, j in enumerate(s.order)]


def choose(state: GameState, content: Content, index: int, rng: random.Random) -> list[str]:
    """選了一個做法：選錯什麼都沒有（這一處到換日之前不再悟），選對擲骰；擲中進感悟狀態，沒擲中給一點心得。"""
    got = current(state, content)
    p = state.player
    if got is None or got[0].stage != "choose" or not 0 <= index < len(got[0].order):
        return ["（此刻無法這麼做。）"]
    s, scene, loc = got
    method = scene.methods[s.order[index]]
    msgs = [f"你{method.text}。"]
    if not scene.prologue and method.attribute not in insights.pool_attributes(loc, content):
        p.sensing = None
        p.sense_misses[loc.id] = game_day(content, state.world)
        return msgs + [_until(MISS_LINE, MISS_LINE_SEASON, state, content)]
    if rng.random() * 100 >= rate(state, content, loc):
        p.sensing = None
        amount = content.config.sense_miss_xinde
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        return msgs + ["差一點就抓到了——心念一散，只留下一點體會。", f"心得 +{amount}"]
    s.stage, s.method = "draw", method.attribute
    return msgs + ["心念漸漸凝住了，心中隱隱有一個形。"]


class SenseRequest(BaseModel):
    """感悟狀態畫完那一筆的單子（A 段開、B 段拿去叫模型、C 段交回 finish 重驗）。points 是 None＝順其自然、沒畫。"""

    serial: int
    location: str
    method: str  # 做法的屬性
    drawn: str  # 畫出來的屬性（順其自然＝做法的屬性）
    attribute: str  # 兩者結合出來的屬性
    base: str | None  # 剛好是這一處的基本意境就是它；None＝要悟一個自己的新意境（要取名）
    mood: str = ""  # 規則從那一筆讀到的意象（glyph.Glyph.mood；給模型當線索、模型叫不動時當說明，不寫筆畫的幾何）
    points: list[list[int]] = Field(default_factory=list)  # 畫的那一筆（縮到 0～100 的點位，存進意境畫縮圖）
    raw: list | None = None  # 原始點位：C 段重讀一次，確定跟 A 段讀到的一樣
    png: str = ""  # 畫布存的小 PNG（base64）；只轉交給模型看，不存
    facts: dict[str, str] = Field(default_factory=dict)  # 給模型的地點、場景、做法、那一筆的意象

    @property
    def needs_name(self) -> bool:
        return self.base is None


def _outcome(
    state: GameState, content: Content, world: WorldStateStore, s: Sensing, scene: InsightScene, loc: Location, drawn: str,
) -> tuple[str, str | None]:
    """做法的屬性＋畫出來的屬性 → （結合出來的屬性, 落回的基本意境或 None）。序章一律落回做法那個基本意境。
    結合照合併的規則（insights.merged_attribute）：同屬性就是它；剛快陽、柔慢陰、快柔虛、剛慢實；其他由種子挑一個。
    種子是「天機｜悟｜地點｜做法｜畫的」：同一季同一處同樣的組合，結合出來的永遠一樣。"""
    method = s.method or ""
    if scene.prologue:
        return method, insights.base_of(method, loc, content)
    seed = f"{world.read().tianji}|{MARK}|{loc.id}|{method}|{drawn}"
    attribute = insights.merged_attribute(
        SimpleNamespace(id=method, attribute=method), SimpleNamespace(id=drawn, attribute=drawn), seed,
    )
    return attribute, insights.base_of(attribute, loc, content)


def request(
    state: GameState, content: Content, world: WorldStateStore, points: list | None, png: str = "",
) -> SenseRequest | str:
    """A 段（鎖內、只讀）：還在感悟狀態才開單；讀不出那一筆回一句話（字串）。points 是 None＝順其自然。"""
    got = current(state, content)
    if got is None or got[0].stage != "draw":
        return STALE
    s, scene, loc = got
    if points is None:
        drawn, mood, box = s.method or "", "", []
    else:
        try:
            read = glyph.read(points)
        except glyph.GlyphError as e:
            return str(e)
        drawn, mood, box = read.attribute, read.mood(), read.points
    attribute, base = _outcome(state, content, world, s, scene, loc, drawn)
    method = next(m for m in scene.methods if m.attribute == s.method)
    facts = {
        "place": loc.name, "scene": scene.title, "text": scene.text.replace("{痕跡}", "").strip(),
        "method": method.text, "mood": mood or "（沒有畫）", "attribute": attribute,
    }
    return SenseRequest(
        serial=s.serial, location=loc.id, method=s.method or "", drawn=drawn, attribute=attribute, base=base, mood=mood,
        points=box, raw=points, png=png if base is None else "", facts=facts,
    )


def _own_names(state: GameState) -> set[str]:
    return {i.name for i in state.player.own_insights.values()}


def own_name(
    state: GameState, content: Content, world: WorldStateStore, key: str, proposed: tuple[str | None, str] | None,
) -> tuple[str, str, bool]:
    """私有意境的名字（悟意境設計 0.2b 第 3 點）：（名字, 說明, 是不是模型取的）。模型取的再過一次完整的過濾
    （naming.recheck，含江湖上的名號），也不能跟自己手上已有的意境同名；過不了走退路字表（種子是 key，換鹽再試）。
    不跟別人比：私有的名字不要求全服唯一。"""
    taken = _own_names(state)
    name, note = naming.recheck(content, proposed or (None, ""), person=world.is_character_name)
    if name is not None and name not in taken:
        return name, note, True
    tianji = world.read().tianji
    for salt in range(FALLBACK_TRIES):
        fallback = naming.fallback_name(content, key, "意境", salt=salt, tianji=tianji)
        if fallback not in taken and not world.is_character_name(fallback):
            return fallback, "", False
    return fallback, "", False  # 八次都撞到（自己手上意境極多）：照最後一個用，私有的名字本來就不要求唯一


def add_own(state: GameState, insight: Insight) -> Insight:
    """把一個私有意境收進自己的存檔（id 照自己的流水號），回收好的那一個。"""
    p = state.player
    p.own_serial += 1
    own = insight.model_copy(update={"id": f"{insights.OWN_PREFIX}{p.own_serial}"})
    p.own_insights[own.id] = own
    p.insights.append(own.id)
    return own


def finish(
    state: GameState, content: Content, world: WorldStateStore, req: SenseRequest,
    proposed: tuple[str | None, str] | None = None, client: OllamaClient | None = None,
) -> tuple[list[str], Insight | None, bool]:
    """C 段（鎖內）：重驗還是同一次感悟、同一筆讀出同一個屬性，才套用。回（訊息, 悟到的私有新意境或 None, 名字是不是模型取的）。
    落回基本意境走 insights.learn（已經會的化成心得）。要取名的：proposed 是鎖外先取好的（名字, 說明）；沒給（整季機器人、
    腳本、測試）而且給了 client，才在這裡叫模型（呼叫端給的是行動鎖內的短逾時複本，只看文字特徵、不看圖）。"""
    got = current(state, content)
    if got is None or got[0].stage != "draw" or got[0].serial != req.serial or got[0].location != req.location:
        return [STALE], None, False
    s, scene, loc = got
    drawn = s.method or ""
    if req.raw is not None:
        try:
            drawn = glyph.read(req.raw).attribute
        except glyph.GlyphError:
            return [STALE], None, False
    attribute, base = _outcome(state, content, world, s, scene, loc, drawn)
    if (s.method, drawn, attribute, base) != (req.method, req.drawn, req.attribute, req.base):
        return [STALE], None, False
    p = state.player
    p.sensing = None
    # 玩家面前不寫筆畫的幾何（企劃者 2026-10-06）：畫了只說畫了，那一筆給人的感覺留給意境的說明
    lead = ["你一筆畫下心中的形。"] if req.raw is not None else ["你沒有去抓它，任那份感覺自己沉下來。"]
    if base is not None:
        return lead + insights.learn(state, content, world, base), None, False
    if proposed is None and client is not None:
        got_name, got_note, _ = insight_llm.name(client, content, req.facts, person=world.is_character_name)
        proposed = (got_name, got_note)
    name, note, by_model = own_name(state, content, world, f"{MARK}|{p.name}|{p.own_serial + 1}", proposed)
    note = insight_llm.plain(note) or mood_note(req.mood)  # 模型沒寫、寫了筆畫的幾何、或走退路字表：說明用規則讀到的意象
    own = add_own(state, Insight(
        id="", name=name, attribute=attribute, lean="無", note=note, creator=p.name, creator_shown=p.name,
        place=loc.name, glyph=req.points,
    ))
    msgs = lead + [f"你悟得了「{own.name}」的意境（屬{own.attribute}）！"]
    if own.note:
        msgs.append(own.note)
    msgs.append("這份領悟是你自己的，江湖上沒有第二份。")
    return msgs, own, by_model


def mood_note(mood: str) -> str:
    """模型給不出說明時的退路：規則讀到的意象寫成一句（「意境之中，山岳般的沉穩厚重、氣象開闊。」）；沒有意象是空字串。"""
    return f"意境之中，{mood}。" if mood else ""


def first_key(req: SenseRequest) -> str:
    """首悟紀錄的鍵（0.2b 第 4、5 點）：某地、某做法、某畫法。只拿來記「誰第一個」，不是配方、不查快取。"""
    return f"{req.location}|{req.method}|{req.drawn}"
