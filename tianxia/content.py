"""載入 content/ 底下的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。

sanguo-companions 合併大幅簡化了這裡的驗證規則（見設計文件開放決策記錄）：舊制度圍繞
天地玄黃品階/統御區間/流派資質 S 級數量/招賢卡池/收徒地點的一大批交叉檢查全部拿掉，
因為新制度（同伴全服唯一、無抽卡、無多隊、無舊武學品階系統）根本沒有這些概念。只保留
基本的交叉引用完整性檢查（id 存在、不重複、地點互相連通等），細緻的內容規則之後好玩
再視需要補回來。
"""
from __future__ import annotations

import json
import math
import re
import string
from pathlib import Path
from typing import get_args

from pydantic import BaseModel, ValidationError

from . import encounter
from .companion_agent import DIALOGUE_TAGS
from .front_lines import BAND_KEYS, GEJU_KEYS
from .materials import TIER_NAMES
from .models import (
    FRONT_KEY, REVEAL_KEYS, ROADS, STATS, Attribute, BattleDef, CharacterDef, CheckVoice, CombatLines, Condition, Config,
    Content, CraftNames, Effect, Event, FigureDef, FollowerDef, Foreshadows, FrontLines, InsightDef, Location, OppDef,
    OrdersContent, PresetRecipe, PromotionDef, MapLayout, Material, RoadSight, Scenario, Sect, SimRumor, SkillDef, Squad,
    TimetableEvent, TraitBook, Tutorial, allow_known,
)
from .martial_arts import ATTRIBUTES, QUALITIES
from .naming import PRESET_CLASH, name_problem
from .zh import to_traditional

ROAD_SIGHTS_PER_SPOT = 2  # 路上見聞：每一種路、每一個大區的組合至少要有幾則可挑（路上設計第五節）
ROAD_SIGHT_CAPS = {"silver": 10, "xinde": 5}  # 路上見聞的小收穫上限
TERRAIN_SIZE = (8, 40)  # 山脈、丘陵的山頭高度範圍（輿圖美術設計第四節）
TIMETABLE_SIDES = ("guan", "huang")  # 時刻表的鎖定、決戰、@commander 只有官軍與黃巾兩方（豪強是第三方）
TIMETABLE_KEYS = {  # 每種大事該有的結果鍵（不含版本；有版本時每個版本各一套）
    "fixed": ["fixed"],
    "roll": ["成", "不成"],
    "showdown": [f"{side}:{tier}" for side in TIMETABLE_SIDES for tier in ("大勝", "險勝")],
}


class ContentError(Exception):
    pass


# 設定覆寫檔（content/profiles/<名字>.json）的環境變數。server.py、run_bots.py、scripts/sim_*.py 讀它傳進
# load_content；引擎自己不讀環境變數（計畫 T2「總開關與週末設定」）。
PROFILE_ENV = "TIANXIA_PROFILE"


def load_content(root: Path, profile: str | None = None) -> Content:
    """profile 給了就把 profiles/<profile>.json 的鍵蓋在 config.json 上（例如週末設定一次打開季曆與 2.5 天的季），
    不必手改 config.json；覆寫檔只能寫 Config 有的欄位，拼錯在載入當下就報錯。"""
    root = Path(root)
    events: dict[str, Event] = {}
    for path in sorted((root / "events").glob("*.json")):
        for raw in _read(path):
            event = _build(Event, raw)
            if event.id in events:
                raise ContentError(f"事件 id 重複：{event.id}（{path.name}）")
            events[event.id] = event
    content = Content(
        config=_config(root, profile),
        scenario=Scenario(**_read(root / "scenario.json")),
        locations=_index(Location, _read(root / "locations.json")),
        skills=_index(SkillDef, _read(root / "skills.json")),
        insights=_index(InsightDef, _read(root / "insights.json")),
        traits=_traits(root / "traits.json"),
        trait_lines=_trait_lines(root / "trait_lines.json"),
        materials=_index(Material, _read(root / "materials.json")),
        craft_names=CraftNames(**_read(root / "craft_names.json")),
        combat_lines=_combat_lines(root / "combat_lines.json"),
        check_voice=_check_voice(root / "check_voice.json"),
        front_lines=_front_lines(root / "front_lines.json"),
        banned_names=_read(root / "banned_names.json"),
        sects=_index(Sect, _read(root / "sects.json")),
        characters=_index(CharacterDef, _read(root / "characters.json")),
        squads=_index(Squad, _read(root / "squads.json")),
        battles=_index(BattleDef, _read(root / "battles.json")) if (root / "battles.json").exists() else {},
        road_sights=_index(RoadSight, _read(root / "road_sights.json")),
        timetable=[_build(TimetableEvent, raw) for raw in _read(root / "timetable.json")]
        if (root / "timetable.json").exists() else [],
        foreshadows=_foreshadows(root / "foreshadows.json"),
        orders=_orders(root / "orders.json"),
        promotions=[_build(PromotionDef, raw) for raw in _read(root / "promotions.json")]
        if (root / "promotions.json").exists() else [],
        opportunities=[_build(OppDef, raw) for raw in _read(root / "opportunities.json")]
        if (root / "opportunities.json").exists() else [],
        followers={raw["id"]: _build(FollowerDef, raw) for raw in _read(root / "followers.json")}
        if (root / "followers.json").exists() else {},
        preset_recipes=[_build(PresetRecipe, raw) for raw in _read(root / "preset_recipes.json")]
        if (root / "preset_recipes.json").exists() else [],
        figures=_index(FigureDef, _read(root / "figures.json")) if (root / "figures.json").exists() else {},
        events=events,
        map=MapLayout(**_read(root / "map.json")),
        tutorial=Tutorial(**_read(root / "tutorial.json")),
    )
    content.config.admins = _with_local_admins(content.config.admins)
    validate(content)
    _scale_marks(content, content.config.mark_threshold_scale)
    return content


def _config(root: Path, profile: str | None) -> Config:
    raw = _read(root / "config.json")
    if profile is not None:
        path = root / "profiles" / f"{profile}.json"
        if not path.exists():
            raise ContentError(f"找不到設定覆寫檔 {profile}（應該在 {path}）")
        overrides = _read(path)
        unknown = sorted(set(overrides) - set(Config.model_fields))
        if unknown:
            raise ContentError(f"設定覆寫檔 {path.name} 有 Config 沒有的欄位：{'、'.join(unknown)}")
        raw = {**raw, **overrides}
    return Config(**raw)  # 值寫錯照舊由模型擋（跟 config.json 本身寫錯一樣丟 ValidationError）


def profile_line(content: Content, profile: str | None) -> str:
    """啟動時跟資料庫路徑一起印的那一行：用的是哪一份設定、打開了什麼。設錯時一眼看得出來。"""
    if profile is None:
        return "設定：預設"
    cfg = content.config
    switch = "開啟" if cfg.season_one else "關閉"
    return f"設定：{profile}（第一季濃縮版規則{switch}、季長 {cfg.season_days:g} 天、人數上限 {cfg.server_max_players}）"


def _scale_marks(obj, scale: float) -> None:
    """地方痕跡的門檻照伺服器人數換算（探索的多人與LLM玩法 §8.2）：每個 Condition 的 marks_min／marks_max
    乘上 scale、無條件進位。在載入時做一次，條件判定（rules.check_condition）就不必知道設定。"""
    if scale == 1:
        return
    if isinstance(obj, Condition):
        for limits in (obj.marks_min, obj.marks_max):
            for key, value in limits.items():
                limits[key] = math.ceil(value * scale)
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            _scale_marks(getattr(obj, name), scale)
    elif isinstance(obj, dict):
        for value in obj.values():
            _scale_marks(value, scale)
    elif isinstance(obj, list):
        for value in obj:
            _scale_marks(value, scale)


MARKS_TOKEN = re.compile(r"\{marks:([^{}]+)\}")  # 文字裡的模糊人數（rules.fill_marks）
LORE = "lore"  # 博聞（team.LORE）：只靠升級的點數增加，任何獎勵都不能給、不能扣（validate 的 no_lore）
FREE_TEXT_REWARDS = ("silver", "fame", "good", "xinde", "str", "agi", "con", "wis")  # 隨口應對的獎勵不能超過檢定選項的這幾項（博聞不在內：一律不能給）


LOCAL_DIR = Path(__file__).resolve().parent.parent / ".local"
ADMINS_FILE = LOCAL_DIR / "admins.txt"


def _with_local_admins(admins: list[str]) -> list[str]:
    """`config.json` 的管理者名單，加上這台機器自己的 `.local/admins.txt` 與 `TIANXIA_ADMINS`。

    為什麼不要直接改 `content/config.json`：那是版控裡的檔案，每次 pull 下來都會被蓋回去，
    等於每次更新都要重設一次自己的管理者（企劃者實際踩到）。`.local/` 已經在 `.gitignore`
    裡（密碼也放那），所以放這裡的設定不會進版控、也不會被 pull 覆蓋。

    - `.local/admins.txt`：一行一個名號，`#` 開頭當註解。設一次就一直有效，是推薦的做法。
    - `TIANXIA_ADMINS`：逗號分隔，臨時或 CI 用。
    兩邊都是**附加**，不會蓋掉 config.json 原本的名單。
    """
    import os  # noqa: PLC0415  只有這裡用得到

    extra: list[str] = []
    if ADMINS_FILE.exists():
        extra += [
            line.strip() for line in ADMINS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    extra += [name.strip() for name in os.environ.get("TIANXIA_ADMINS", "").split(",") if name.strip()]
    out = list(admins)
    out += [name for name in extra if name not in out]
    return out


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _foreshadows(path: Path) -> Foreshadows:
    """content/foreshadows.json（計畫 T7）：不存在或是空的檔案都當成沒有伏筆。"""
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return Foreshadows()
    try:
        return Foreshadows(**_read(path))
    except ValidationError as e:
        raise ContentError(f"foreshadows.json：{e}") from e


def _orders(path: Path) -> OrdersContent:
    """content/orders.json（計畫 T6）：不存在時當成沒有軍令（測試夾具沒有這個檔）。"""
    if not path.exists():
        return OrdersContent()
    try:
        return OrdersContent(**_read(path))
    except ValidationError as e:
        raise ContentError(f"orders.json：{e}") from e


def _check_voice(path: Path) -> CheckVoice:
    """content/check_voice.json（檢定選項括號裡的那一句，joy 寫的；企劃者 2026-10-05 定案取代 S1 的 check_lines.json）：
    必備的檔——每個檢定選項都要有一句；找不到、不是合法的 JSON、欄位寫錯都改報 ContentError 並指出是這個檔（joy 會手改）。"""
    if not path.exists():
        raise ContentError(f"check_voice.json：找不到檔案（應該在 {path}）")
    try:
        return CheckVoice(**_read(path))
    except json.JSONDecodeError as e:
        raise ContentError(f"check_voice.json：不是合法的 JSON：{e}") from e
    except (ValidationError, TypeError) as e:
        raise ContentError(f"check_voice.json：{e}") from e


def _combat_lines(path: Path) -> CombatLines:
    """content/combat_lines.json（回合演出的句型，武學與成長設計 8.2；S1／Joy 照內容表手改）：必備的檔；找不到、
    不是合法的 JSON、欄位或屬性寫錯都改報 ContentError 並指出是這個檔（跟 check_voice.json 一樣）。"""
    if not path.exists():
        raise ContentError(f"combat_lines.json：找不到檔案（應該在 {path}）")
    try:
        return CombatLines(**_read(path))
    except json.JSONDecodeError as e:
        raise ContentError(f"combat_lines.json：不是合法的 JSON：{e}") from e
    except (ValidationError, TypeError) as e:
        raise ContentError(f"combat_lines.json：{e}") from e


def _traits(path: Path) -> TraitBook:
    """content/traits.json（武學的功效，武學與成長設計 13.2、13.4）：選填——沒有這個檔就是沒有功效；有的話，
    不是合法的 JSON、欄位或掛點寫錯都改報 ContentError 並指出是這個檔（跟 combat_lines.json 一樣）。"""
    if not path.exists():
        return TraitBook()
    try:
        return TraitBook.model_validate(_read(path))
    except json.JSONDecodeError as e:
        raise ContentError(f"traits.json：不是合法的 JSON：{e}") from e
    except ValidationError as e:
        raise ContentError(f"traits.json：{e}") from e


def _trait_lines(path: Path) -> dict[str, list[str]]:
    """content/trait_lines.json（功效的演出句，S1 寫的；形狀是 {功效名: [句子, ...]}）：選填；寫壞了報 ContentError 並指出是這個檔。
    句子的內容（佔位、繁體、不寫數字）由 check_traits 查。"""
    if not path.exists():
        return {}
    try:
        raw = _read(path)
    except json.JSONDecodeError as e:
        raise ContentError(f"trait_lines.json：不是合法的 JSON：{e}") from e
    shaped = isinstance(raw, dict) and all(
        isinstance(lines, list) and all(isinstance(line, str) for line in lines) for lines in raw.values()
    )
    if not shaped:
        raise ContentError("trait_lines.json：要寫成 {功效名: [句子, ...]}，每個功效一串句子")
    return raw


def _front_lines(path: Path) -> FrontLines:
    """content/front_lines.json（FB-064，戰況變化的說法）：必備的檔；找不到、不是合法的 JSON、欄位寫錯都改報
    ContentError 並指出是這個檔（跟 check_voice.json 一樣）。"""
    if not path.exists():
        raise ContentError(f"front_lines.json：找不到檔案（應該在 {path}）")
    try:
        return FrontLines(**_read(path))
    except json.JSONDecodeError as e:
        raise ContentError(f"front_lines.json：不是合法的 JSON：{e}") from e
    except (ValidationError, TypeError) as e:
        raise ContentError(f"front_lines.json：{e}") from e


def _build(model, raw: dict):
    """建立一筆有 id 的內容；欄位錯誤時改報 ContentError，並指出是哪一筆。"""
    try:
        return model(**raw)
    except ValidationError as e:
        raise ContentError(f"{model.__name__} {raw.get('id', '?')}：{e}") from e


def _index(model, items: list[dict]) -> dict:
    result = {}
    for raw in items:
        obj = _build(model, raw)
        if obj.id in result:
            raise ContentError(f"{model.__name__} id 重複：{obj.id}")
        result[obj.id] = obj
    return result


def _material_sources(c: Content) -> set[str]:
    """所有拿得到的素材 id：路邊採集、對手掉（含依難度的預設表）、事件與路上見聞給。

    探索不再撿素材（武學與成長計畫一：探索改悟意境），地點能給素材的只剩路邊採集（Game._road_gather）：
    採到的永遠是一階，屬性看這段路兩頭的地點寫了哪些素材（只看屬性，不看寫的是幾階），兩頭都沒寫就隨機一階。
    所以地點寫了二、三階素材，那一階並不會因此拿得到。"""
    from .materials import _default_rolls, by_tier  # noqa: PLC0415  延後 import，避免循環依賴

    reachable: set[str] = set()
    first_tier = by_tier(c, 1)
    for loc in c.locations.values():
        for conn in loc.connections:  # 路都是雙向的（載入時檢查過）：每一條路從兩頭各看一次，結果一樣
            kinds = {
                c.materials[mid].attribute
                for end in (loc, c.locations.get(str(conn)))
                if end is not None for mid in end.materials if mid in c.materials
            }
            picked = [m.id for m in first_tier if m.attribute in kinds]  # 跟 Game._road_gather 一樣：挑不到就退回全部一階
            reachable |= set(picked or [m.id for m in first_tier])
    for squad in c.squads.values():
        if squad.drops:
            reachable |= {d.material for d in squad.drops}
            continue
        for tier, _chance in _default_rolls(squad):
            reachable |= {m.id for m in by_tier(c, tier, squad.attribute)}
    for ev in c.events.values():
        for ch in ev.choices:
            reachable |= set(ch.effect.materials) | set(ch.fail_effect.materials)
    for sight in c.road_sights.values():
        reachable |= set(sight.effect.materials)
    return reachable


NUMBER_IN_TEXT = re.compile(r"[0-9０-９%％]")  # 心裡話不能攤出成功率（也不能寫難度）


def check_check_voice(c: Content, need) -> None:
    """檢定選項括號裡的那一句（content/check_voice.json，joy 寫的；取代 S1 的 check_lines.json，驗證照它的標準）：
    至少一檔、照 min_gap 由高到低排而且不重複；每一檔都要說得出每一種有人檢定的屬性（沒寫的屬性用 "default"）；
    鍵只能是屬性或 default；每一句都不能是空的、只用繁體中文、不能寫阿拉伯數字（半形、全形）或百分號（選項上不攤出成功率）。
    熟練加成併進括號的那一句（config.practice_bonus 的 line）照同樣的文字規矩。"""
    bands = c.check_voice.bands

    def check_text(where: str, text: str) -> None:
        need(bool(text.strip()), f"{where}：有空白的句子")
        need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
        need(not NUMBER_IN_TEXT.search(text), f"{where}：不能寫數字或百分比，成功率不攤在選項上（「{text[:12]}」）")

    need(bool(bands), "check_voice.json：至少要有一檔（每個檢定選項的括號裡都要有一句）")
    gaps = [band.min_gap for band in bands]
    need(gaps == sorted(gaps, reverse=True) and len(set(gaps)) == len(gaps), "check_voice.bands 要照 min_gap 由高到低排、不能重複")
    checked = {ch.check.stat for e in c.events.values() for ch in e.choices if ch.check is not None}
    for band in bands:
        where = f"check_voice 的 min_gap {band.min_gap:g} 那一檔"
        for key, text in band.lines.items():
            need(key in STATS or key == "default", f"{where}：不認得的鍵 {key}（只能是屬性或 default）")
            check_text(f"{where}.{key}", text)
        for stat in sorted(checked):
            need(bool((band.lines.get(stat) or band.lines.get("default") or "").strip()),
                 f"{where}說不出 {stat} 的心聲（補這個屬性或 default）")
    for kind, rule in c.config.practice_bonus.items():
        if rule.line:
            check_text(f"config.practice_bonus.{kind}.line", rule.line)


def check_front_lines(c: Content, need) -> None:
    """戰況變化的說法（content/front_lines.json，FB-064）：generic 三段（front_lines.BANDS）一段都不能少、
    不能多出不認得的段；各陣營自己的說法（by_side）只能寫存在的陣營與段、可以只寫其中幾段；割據要有漲與落兩組；
    sides 的陣營名也要是存在的陣營。每一句、每個陣營名都不能是空的、只用繁體中文、不能寫數字或百分比（畫面上只有一句話、不攤出數字）。"""
    lines = c.front_lines
    factions = {f.id for f in c.scenario.factions}

    def check_text(where: str, text: str) -> None:
        need(bool(text.strip()), f"{where}：有空白的句子")
        need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
        need(not NUMBER_IN_TEXT.search(text), f"{where}：不能寫數字或百分比，戰況變化只用一句話說（「{text[:12]}」）")

    def check_pool(where: str, pool: list[str]) -> None:
        need(bool(pool), f"{where}：不能是空的")
        for text in pool:
            check_text(where, text)

    for band in BAND_KEYS:
        need(band in lines.generic, f"front_lines.generic 缺少 {band} 那一段")
    for band, pool in lines.generic.items():
        need(band in BAND_KEYS, f"front_lines.generic：不認得的段 {band}（只有 {'、'.join(BAND_KEYS)}）")
        check_pool(f"front_lines.generic.{band}", pool)
    for side, name in lines.sides.items():
        need(side in factions, f"front_lines.sides：不存在的陣營 {side}")
        check_text(f"front_lines.sides.{side}", name)
    for side, bands in lines.by_side.items():
        need(side in factions, f"front_lines.by_side：不存在的陣營 {side}")
        for band, pool in bands.items():
            need(band in BAND_KEYS, f"front_lines.by_side.{side}：不認得的段 {band}（只有 {'、'.join(BAND_KEYS)}）")
            check_pool(f"front_lines.by_side.{side}.{band}", pool)
    for key in GEJU_KEYS:
        need(key in lines.geju, f"front_lines.geju 缺少 {key}（漲 up、落 down 各一組）")
    for key, pool in lines.geju.items():
        need(key in GEJU_KEYS, f"front_lines.geju：不認得的鍵 {key}（只有 {'、'.join(GEJU_KEYS)}）")
        check_pool(f"front_lines.geju.{key}", pool)


def check_combat_lines(c: Content, need) -> None:
    """回合演出的句型（content/combat_lines.json，武學與成長設計 8.2；S1／Joy 照內容表手改）：我方八種屬性都要有句子
    （武學一定有屬性）；對手的每種屬性可以不寫（退回 theirs_any）。每一句都不能是空的、只用繁體中文、不能寫阿拉伯數字
    或百分比（後面接的「對手氣勢 -N」「你氣血 -N」才是數字，句子裡再寫數字會攪在一起；國字的「一步一步」可以），也不能寫
    【】（武學名的「以【某某】」由引擎加上）。"""
    lines = c.combat_lines
    for attribute in get_args(Attribute):
        need(bool(lines.ours.get(attribute)), f"combat_lines.ours 缺少屬性 {attribute}")
    pools = [(f"combat_lines.ours.{a}", pool) for a, pool in lines.ours.items()]
    pools += [(f"combat_lines.theirs.{a}", pool) for a, pool in lines.theirs.items()]
    pools += [("combat_lines.bare", lines.bare), ("combat_lines.theirs_any", lines.theirs_any)]
    for where, pool in pools:
        for text in pool:
            need(bool(text.strip()), f"{where}：有空白的句子")
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
            need(not NUMBER_IN_TEXT.search(text), f"{where}：不能寫數字或百分比，回合的數字由引擎接在後面（「{text[:12]}」）")
            need("【" not in text and "】" not in text, f"{where}：不能寫【】，武學名由引擎加上（「{text[:12]}」）")


TRAIT_LINE_SLOTS = {"who", "art", "foe"}  # 演出句的三個佔位（S1：出手的人、帶功效的那一門、對手）


def _placeholder_problem(line: str) -> str | None:
    """演出句的佔位有沒有問題；沒問題是 None。之後 trait_line 用 str.format(who=…, art=…, foe=…) 把句子套上去，
    所以每一個佔位都要是乾淨的 {who}、{art}、{foe}（不接格式、不接轉換、不取屬性或索引），大括號要成對、不能有空的 {}；
    載入時沒擋下的話，會在戰鬥打到一半才丟 ValueError、KeyError、AttributeError。
    連續的 {{ 與 }} 在 str.format 裡是寫出一個大括號的跳脫，但演出句裡不會有人真的要大括號，多半是寫壞了的佔位，一律擋下。"""
    if "{{" in line or "}}" in line:
        return "不能有連續的 {{ 或 }}（演出句裡用不到大括號本身，佔位只能是 {who}、{art}、{foe}）"
    try:
        parsed = list(string.Formatter().parse(line))
    except ValueError as e:  # 大括號沒有成對（{who搶先、多出來的 }）
        return f"佔位的大括號沒有成對（{e}）"
    for _, field, spec, conversion in parsed:
        if field is None:  # 句子尾巴那一段純文字
            continue
        if field not in TRAIT_LINE_SLOTS or spec or conversion is not None:
            written = "{" + field + (f"!{conversion}" if conversion else "") + (f":{spec}" if spec else "") + "}"
            return f"用了不認得的佔位 {written}（只能是 {{who}}、{{art}}、{{foe}}，後面不能接格式或屬性）"
    return None


def check_traits(c: Content, need) -> None:
    """武學的功效（content/traits.json、trait_lines.json，武學與成長設計 13.2、13.4、13.5）：一般功效一個屬性一個、八個都要有，
    名字不重複；特別功效的 id 不重複；掛點不重複（Loadout 與 traits.amount 都是照掛點找，兩個掛同一點會悄悄只剩一個，
    含 pool 是 false 的獨特功效）；武學（SkillDef.special）指的特別功效要存在，不在共用清單（pool 是 false）的只能給一門；
    每個功效都有演出句、演出句的鍵都是功效名（鍵拼錯的永遠挑不到）。每一句都不能是空的、只用繁體中文、不能寫數字或百分比
    （功效幾層、多少由規則算，句子只寫打法），佔位只能是乾淨的 {who}、{art}、{foe}（_placeholder_problem）。品質的強度倍數
    （Config.trait_quality_multiplier）四個品質都要寫，少一個那一品的功效強度會悄悄變成 ×1。
    這份內容選填：兩個檔都沒有就是沒有功效。"""
    book = c.traits
    specials = {t.id: t for t in book.special}
    for quality in QUALITIES:
        need(
            quality in c.config.trait_quality_multiplier,
            f"config.trait_quality_multiplier 缺少品質 {quality}（沒寫的那一品，功效強度會悄悄變成 ×1）",
        )
    if book.general or book.special:
        need(sorted(t.attribute for t in book.general) == sorted(ATTRIBUTES), "content/traits.json：一般功效要一個屬性一個，八個都要有")
        names = [t.name for t in book.general] + [t.name for t in book.special]
        need(len(names) == len(set(names)), "content/traits.json：功效的名字不能重複")
        need(len(specials) == len(book.special), "content/traits.json：特別功效的 id 不能重複")
        general_hooks = [t.hook for t in book.general]
        need(len(general_hooks) == len(set(general_hooks)), "content/traits.json：一般功效的掛點不能重複")
        by_hook: dict[str, str] = {}
        for t in book.special:
            first = by_hook.setdefault(t.hook, t.id)
            need(first == t.id, f"content/traits.json：特別功效 {first} 與 {t.id} 掛在同一個掛點 {t.hook}，身上只會留下一個")
    owners: dict[str, list[str]] = {}
    for skill in c.skills.values():
        if skill.special is not None:
            need(skill.special in specials, f"武學 {skill.id}：特別功效 {skill.special} 不存在")
            owners.setdefault(skill.special, []).append(skill.id)
    for sid, skills in owners.items():
        if sid in specials and not specials[sid].pool:
            need(len(skills) == 1, f"特別功效 {sid} 不在共用清單裡，只能給一門（現在是 {'、'.join(skills)}）")
    names = {t.name for t in book.general} | {t.name for t in book.special}
    for name in sorted(names):
        need(bool(c.trait_lines.get(name)), f"content/trait_lines.json：功效 {name} 沒有演出句")
    for name, lines in c.trait_lines.items():
        where = f"content/trait_lines.json：{name}"
        need(name in names, f"{where} 不是 content/traits.json 裡的功效（鍵拼錯的句子永遠不會被挑到）")
        for line in lines:
            problem = _placeholder_problem(line)
            need(problem is None, f"{where} 的句子「{line[:12]}」{problem}")
            need(bool(line.strip()), f"{where}：有空白的句子")
            need(to_traditional(line) == line, f"{where}：文字只能用繁體中文（「{line[:12]}」）")
            need(not NUMBER_IN_TEXT.search(line), f"{where}：不能寫數字或百分比，功效的數字由規則算、句子只寫打法（「{line[:12]}」）")


def check_timetable(c: Content, need, known, front_ids: list[str], trend_ids: set[str]) -> None:
    """時刻表（content/timetable.json，計畫 T2）：戰線（大事的 front、人物效果的 front 與 only_if、@commander 的戰線）
    寫的是戰線 id（大區的 front，T1：yingru／nanyang／jizhou），不是大區 id——幽州是大區、它的戰線是冀州，寫 youzhou
    讀戰況時會讀到固定的 50；結果鍵照種類齊全、鎖定對得到結果、人物與修正的
    對象存在、文字只用繁體中文。大勢線的推動（第三方、結果）要是存在的線、而且不能是衍生線（黃巾聲勢由三條戰線合成）。
    人物認人物表（figures.json，T4）的 id；沒有人物表的內容（測試夾具）照舊認 characters.json。
    人物欄位（{人物:<id>}、@人物:<id>，FB-042）只認人物表：找人要看他的陣營與戰線。"""
    from .timetable import PERSON_KEY, PERSON_SLOT  # noqa: PLC0415  延後 import（同 validate 的 atlas）

    figure_ids = c.figures or c.characters
    ids = [e.id for e in c.timetable]
    duplicated = sorted({eid for eid in ids if ids.count(eid) > 1})
    need(not duplicated, f"時刻表 id 重複：{'、'.join(duplicated)}")
    trends = trend_ids - {t.id for t in c.scenario.trends if t.derived}  # 衍生線（黃巾聲勢）由三條戰線合成，時刻表不能直接推
    earlier: dict[str, TimetableEvent] = {}
    order = {e.id: i for i, e in enumerate(c.timetable)}
    rolled = {e.id for e in c.timetable if e.roll_side is not None}

    def check_text(where: str, text: str | None) -> None:
        if text:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}…」）")

    def check_people(where: str, ev: TimetableEvent, texts, keys) -> None:
        """人物欄位（濃縮版內容表 8.1）：texts 裡的 {人物:<id>} 與人物效果的鍵 keys 裡的 @人物:<id>。id 要在人物表上，
        而且是官軍或黃巾的人物（沒有人時寫的泛稱只有這兩方）；用到的大事要有 front（照這件大事的戰線找人）。"""
        ids = [fid for text in texts if text for fid in PERSON_SLOT.findall(text)]
        ids += [key.removeprefix(PERSON_KEY) for key in keys if key.startswith(PERSON_KEY)]
        if not ids:
            return
        ids = list(dict.fromkeys(ids))
        known(where, ids, c.figures, "人物")
        need(ev.front is not None, f"{where}：用到人物欄位（{{人物:…}}、@人物:…）的大事要寫 front")
        for fid in ids:
            fig = c.figures.get(fid)
            need(fig is None or fig.faction in TIMETABLE_SIDES,
                 f"{where}：人物欄位的 {fid} 要是官軍或黃巾的人物（沒有人時寫的泛稱只有這兩方）")

    def check_figure(where: str, key: str, change) -> None:
        if key.startswith("@commander:"):
            front, _, side = key.removeprefix("@commander:").partition(":")
            known(where, [front], front_ids, "戰線")
            need(side in TIMETABLE_SIDES, f"{where}：{key} 的那一方只能是 guan 或 huang")
        elif not key.startswith(PERSON_KEY):  # @人物:<id> 由 check_people 查
            known(where, [key], figure_ids, "人物")
        if change.front is not None:
            known(where, [change.front], front_ids, "戰線")
        if change.location is not None:
            known(where, [change.location], c.locations, "地點")
        if change.fate == "到任":
            need(change.front is not None and change.location is not None, f"{where}：{key} 到任要寫 front 與 location")
        known(where, change.only_if, figure_ids, "人物")
        known(where, change.only_if.values(), front_ids, "戰線")
        check_text(where, change.note)

    for ev in c.timetable:
        where = f"時刻表 {ev.id}"
        need(ev.week <= c.config.season_weeks, f"{where}：第 {ev.week} 週超出季曆的 {c.config.season_weeks} 週")
        if ev.front is not None:
            known(where, [ev.front], front_ids, "戰線")
        if ev.kind == "roll":
            need(ev.roll_side is not None, f"{where}：擲骰的大事要寫 roll_side（成對哪一方有利）")
            need(ev.front is not None or ev.base_chance is not None, f"{where}：沒有戰線時要寫 base_chance")
        else:
            need(ev.roll_side is None and ev.base_chance is None, f"{where}：只有擲骰的大事寫 roll_side、base_chance")
        if ev.version_from is not None:
            known(where, [ev.version_from], earlier, "（更早的）時刻表大事")
            source = earlier.get(ev.version_from)
            if source is not None:
                known(where, ev.versions, source.outcomes, f"{ev.version_from} 的結果")
            need(bool(ev.versions), f"{where}：有 version_from 就要寫 versions")
        else:
            need(not ev.versions, f"{where}：有 versions 就要寫 version_from")
        if ev.skip_if_out is not None:
            known(where, [ev.skip_if_out], figure_ids, "人物")
        versions = list(dict.fromkeys(ev.versions.values()))
        base = TIMETABLE_KEYS.get(ev.kind)
        if base is not None:  # 季末的結局句寫在劇本的結局（Ending.text），其餘句子在 early_preface、out_lines、ending_chronicle
            expected = [f"{v}:{k}" for v in versions for k in base] if versions else base
            missing = [k for k in expected if k not in ev.outcomes]
            extra = [k for k in ev.outcomes if k not in expected]
            need(not missing, f"{where}：缺少結果 {'、'.join(missing)}")
            need(not extra, f"{where}：多了不認得的結果 {'、'.join(extra)}")
        for side, key in ev.lock_result.items():
            need(side in TIMETABLE_SIDES, f"{where}：lock_result 的鎖定方只能是 guan 或 huang（寫的是 {side}）")
            need(all(f"{v}:{key}" in ev.outcomes for v in versions) if versions else key in ev.outcomes,
                 f"{where}：lock_result 指到不存在的結果 {key}")
        known(where, ev.third_party_trends, trends, "大勢線")
        check_text(where, ev.preface)
        if ev.kind != "finale":  # 季末大事的三種句子（計畫 T9）
            need(not (ev.early_preface or ev.out_lines or ev.ending_chronicle),
                 f"{where}：early_preface、out_lines、ending_chronicle 只有季末大事能寫")
        known(where, ev.out_lines, c.characters, "人物")
        for text in (ev.early_preface, ev.ending_chronicle, *ev.out_lines.values()):
            check_text(where, text)
        check_text(where, ev.third_party_text)
        check_text(where, ev.third_party_chronicle)
        need(all(side in TIMETABLE_SIDES for side in ev.locked_chronicle), f"{where}：locked_chronicle 的鍵只能是 guan 或 huang")
        for text in ev.locked_chronicle.values():
            check_text(where, text)
        # 結算時經過 fill_slots 的句子才填人物欄位（preface 與季末大事的句子不填）
        check_people(where, ev, [ev.third_party_text, ev.third_party_chronicle, *ev.locked_chronicle.values()], [])
        for key, outcome in ev.outcomes.items():
            ow = f"{where} 結果 {key}"
            known(ow, outcome.trends, trends, "大勢線")
            for target in outcome.chance_mods:  # 修正只對之後還要擲骰的大事有意義（例：長社黃巾大勝讓盧植圍廣宗更難）
                need(
                    target in rolled and order[target] > order[ev.id],
                    f"{ow}：chance_mods 的 {target} 要是排在後面、照擲骰結算的大事",
                )
            for label, texts in (("locked_text", outcome.locked_text), ("loser_text", outcome.loser_text)):
                need(all(side in TIMETABLE_SIDES for side in texts), f"{ow}：{label} 的鍵只能是 guan 或 huang")
            need(set(outcome.loser_text) <= set(outcome.locked_text), f"{ow}：有搶輸的一句就要有那一方的具名公告")
            for fid, change in outcome.figures.items():
                check_figure(ow, fid, change)
            texts = [outcome.text, outcome.note, outcome.chronicle, outcome.third_party_text,
                     *outcome.locked_text.values(), *outcome.loser_text.values()]
            for text in texts:
                check_text(ow, text)
            check_people(ow, ev, [*texts, *(change.note for change in outcome.figures.values())], outcome.figures)
        earlier[ev.id] = ev


def check_figures(c: Content, need, known, front_ids: list[str]) -> None:
    """大勢人物（content/figures.json，計畫 T4）：對話人物、陣營、戰線（戰線 id，不是大區）、地點、代表本人的隊伍都存在，
    隊伍跟人物同一個陣營；一個對話人物只能是一位大勢人物，而且人物的 id 就是對話人物的 id（伏筆用對話人物的 id 讀人物的
    狀態）；接位的人存在、同一個陣營、接位鏈不繞回來；名字只用繁體中文。"""
    faction_ids = [f.id for f in c.scenario.factions]
    owner: dict[str, str] = {}  # 對話人物 → 第一個用它的大勢人物
    for fid, fig in c.figures.items():
        where = f"大勢人物 {fid}"
        if fig.character is not None:
            known(where, [fig.character], c.characters, "人物")
            need(owner.setdefault(fig.character, fid) == fid, f"{where}：人物 {fig.character} 已經是 {owner[fig.character]} 了")
            need(fig.character == fid, f"{where}：對話人物要跟人物 id 一樣（現在是 {fig.character}）——伏筆用人物 id 找他的狀態")
        known(where, [fig.faction], faction_ids, "陣營")
        if fig.front is not None:
            known(where, [fig.front], front_ids, "戰線")
        known(where, [fig.location], c.locations, "地點")
        known(where, [fig.squad], c.squads, "敵方隊伍")
        squad = c.squads.get(fig.squad)
        need(squad is None or squad.faction == fig.faction, f"{where}：隊伍 {fig.squad} 的陣營要跟人物一樣（{fig.faction}）")
        need(
            fig.active_from_week <= c.config.season_weeks,
            f"{where}：第 {fig.active_from_week} 週超出季曆的 {c.config.season_weeks} 週",
        )
        need(to_traditional(fig.name) == fig.name, f"{where}：名字只能用繁體中文（{fig.name}）")
        if fig.successor is None:
            continue
        known(where, [fig.successor], c.figures, "大勢人物")
        heir = c.figures.get(fig.successor)
        need(heir is None or heir.faction == fig.faction, f"{where}：接位的 {fig.successor} 要跟他同一個陣營")
        chain, nxt = [fid], fig.successor
        while nxt in c.figures and nxt not in chain:
            chain.append(nxt)
            nxt = c.figures[nxt].successor
        need(nxt not in chain, f"{where}：接位鏈繞回來了（{'→'.join(chain)}→{nxt}）")


ORDER_SLOTS = ("{戰線}", "{地點}", "{起點}", "{終點}", "{主將}", "{人物}", "{號令}")
ORDER_PERSONAL = {"siege": "win", "defend": "duty", "intercept": "win", "escort": "convoy", "strike": "challenge"}


def check_orders(c: Content, need, known, front_ids: list[str]) -> None:
    """軍令（content/orders.json，計畫 T6）：模板的陣營在劇本裡、同一個陣營每種一筆、個人部分照種類；文字只用認得的插槽；
    插槽的戰線與陣營存在，截糧的地點在那條戰線上、護糧的終點是那個陣營的投靠點；守勢行動的陣營存在；
    運糧隊存在、屬於那個陣營；號令的人物在人物表裡。"""
    from .atlas import region_of  # noqa: PLC0415  同 validate：atlas → world → rules，延後載入

    o = c.orders
    factions = {f.id: f for f in c.scenario.factions}
    seen: set[tuple[str, str]] = set()
    for t in o.templates:
        where = f"orders.json 的 {t.kind}／{t.side}"
        need(t.side in factions, f"{where}：陣營 {t.side} 不在劇本裡")
        need((t.kind, t.side) not in seen, f"{where}：同一個陣營的同一種軍令寫了兩筆")
        seen.add((t.kind, t.side))
        need(t.personal == ORDER_PERSONAL[t.kind], f"{where}：個人部分應該是 {ORDER_PERSONAL[t.kind]}，寫的是 {t.personal}")
        for text in (t.text, t.faction_rumor, t.leak_rumor):
            for slot in re.findall(r"\{[^{}]*\}", text):
                need(slot in ORDER_SLOTS, f"{where}：不認得的插槽 {slot}")
        for front in t.when.opening_fronts:
            need(front in front_ids and front in o.slots, f"{where}：開局週的戰線 {front} 不是有插槽的戰線")
    for front, by_side in o.slots.items():
        need(front in front_ids, f"orders.json 的 slots：{front} 不是戰線")
        for side, slot in by_side.items():
            where = f"orders.json 的 slots.{front}.{side}"
            need(side in factions, f"{where}：陣營 {side} 不在劇本裡")
            known(where, [slot.intercept, *slot.escort], c.locations, "地點")
            if slot.intercept in c.locations:
                region = region_of(c, slot.intercept)
                need(region is not None and region.front == front, f"{where}：截糧的地點 {slot.intercept} 不在這條戰線上")
            if side in factions:
                need(slot.escort[1] in factions[side].join_at, f"{where}：護糧的終點 {slot.escort[1]} 不是這個陣營的據點")
    known("orders.json 的 duties", o.duties, factions, "陣營")
    for side, squad_id in o.convoy_squads.items():
        squad = c.squads.get(squad_id)
        need(squad is not None and squad.faction == side, f"orders.json 的 convoy_squads：{side} 的糧隊 {squad_id} 不存在或不屬於這個陣營")
    known("orders.json 的 callers", [x.figure for x in o.callers if x.figure is not None], c.figures, "人物")


def check_promotions(c: Content, need, known) -> None:
    """晉升（content/promotions.json、followers.json，計畫 T5）：陣營在劇本裡、每陣營每階一筆；人物在人物表；地點存在
    （或 nearest_base）；奇遇存在；有接手的人就要有接手版的奇遇與召見；部下的陣營存在、武學在 skills.json；
    promote／followers 只寫在晉升奇遇的選項上，給的部下是那個陣營的。"""
    factions = {f.id for f in c.scenario.factions}
    seen: set[tuple[str, int]] = set()
    promo_events: dict[str, str] = {}
    for promo in c.promotions:
        where = f"promotions.json 的 {promo.faction}／第 {promo.rank} 階"
        need(promo.faction in factions, f"{where}：陣營不在劇本裡")
        need((promo.faction, promo.rank) not in seen, f"{where}：同一個陣營的同一階寫了兩筆")
        seen.add((promo.faction, promo.rank))
        known(where, [x for x in (promo.figure, promo.successor) if x is not None], c.figures, "人物")
        if promo.location != "nearest_base":
            known(where, [promo.location], c.locations, "地點")
        need(
            (promo.successor is None) == (promo.event_handoff is None) == (promo.summons_handoff is None),
            f"{where}：有接手的人就要有接手版的奇遇與召見，沒有就都不寫",
        )
        for event_id in filter(None, (promo.event_main, promo.event_handoff)):
            known(where, [event_id], c.events, "事件")
            promo_events[event_id] = promo.faction
    for fid, follower in c.followers.items():
        where = f"followers.json 的 {fid}"
        need(follower.faction in factions, f"{where}：陣營不在劇本裡")
        known(where, [follower.wugong], c.skills, "武學")
    for event in c.events.values():
        for choice in event.choices:
            if choice.effect.promote is None and not choice.effect.followers:
                continue
            where = f"事件 {event.id}"
            need(event.id in promo_events, f"{where}：promote／followers 只能寫在晉升奇遇（promotions.json 的事件）")
            known(where, choice.effect.followers, c.followers, "部下")
            side = promo_events.get(event.id)
            need(all(c.followers[f].faction == side for f in choice.effect.followers if f in c.followers),
                 f"{where}：給的部下要是 {side} 的")


def check_opportunities(c: Content, need, known, front_ids: list[str]) -> None:
    """機緣（content/opportunities.json、orders.json 的 rank2，正式版乙一）：id 不重複；陣營存在；kind 對應的那一塊要寫、
    別的不能寫；人物、地點、大區、戰線存在；累積型的來源行動（第 2 階行動、守勢行動）自己陣營要有；有東西要送的天時地利型
    要寫送的選項與送到的那一句；文字只能繁體。front_ids 是 validate 的那一份戰線清單。"""
    ids = [o.id for o in c.opportunities]
    need(len(set(ids)) == len(ids), "opportunities.json：機緣 id 重複")
    factions = {f.id for f in c.scenario.factions}
    regions = {r.id for r in c.map.regions}
    for o in c.opportunities:
        where = f"機緣 {o.id}"
        need(o.faction in factions, f"{where}：沒有陣營 {o.faction}")
        blocks = {"bond": o.bond, "accumulate": o.accumulate, "timing": o.timing}
        need(blocks[o.kind] is not None, f"{where}：kind 是 {o.kind}，要寫 {o.kind} 那一塊")
        need(all(v is None for k, v in blocks.items() if k != o.kind), f"{where}：只能寫 {o.kind} 那一塊")
        texts = [o.name]
        if o.bond is not None:
            known(where, [o.bond.character], c.characters, "人物")
            texts += [o.bond.topic, o.bond.text]
        if o.accumulate is not None:
            a = o.accumulate
            need(a.source != "rank2" or o.faction in c.orders.rank2, f"{where}：來源是第 2 階行動，這個陣營卻沒有（orders.json 的 rank2）")
            need(a.source != "duty" or o.faction in c.orders.duties, f"{where}：來源是守勢行動，這個陣營卻沒有（orders.json 的 duties）")
            texts += [a.tick, a.milestone, a.item, a.label, a.done]
        if o.timing is not None:
            t = o.timing
            known(where, t.at + [h.at for h in t.hosts], c.locations, "地點")
            known(where, [h.figure for h in t.hosts], c.figures, "人物")
            need(all(r in regions for r in t.clue_regions), f"{where}：clue_regions 有不存在的大區")
            need(t.deliver_front is None or t.deliver_front in front_ids, f"{where}：deliver_front {t.deliver_front} 不是戰線")
            need(t.when != "night" or bool(t.at), f"{where}：夜裡要寫地點")
            need(t.when != "dawn" or bool(t.hosts), f"{where}：黎明要寫主持人")
            need((t.item is None) == (t.deliver_front is None), f"{where}：item 與 deliver_front 要一起寫")
            need(t.item is None or bool(t.deliver_label.strip()), f"{where}：有 item 就要寫 deliver_label（交東西的選項）")
            need(t.item is None or bool(t.done.strip()), f"{where}：有 item 就要寫 done（交到那一刻的敘事）")
            texts += [t.clue, t.label, t.ok, t.fail, t.deliver_label, t.done] + ([t.item] if t.item else [])
        for text in texts:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    for faction_id, action in c.orders.rank2.items():
        need(faction_id in factions, f"orders.json rank2：沒有陣營 {faction_id}")
        for text in (action.name, action.ok, action.fail):
            need(to_traditional(text) == text, f"orders.json rank2.{faction_id}：文字只能用繁體中文（「{text[:12]}」）")


def check_foreshadows(
    c: Content, need, known, region_ids: list[str], front_ids: list[str], counters_written: dict[str, str],
) -> None:
    """伏筆（content/foreshadows.json，計畫 T7）：鏈的大事在時刻表上、陣營在劇本裡；片段的大區是大區、事件與人物存在；
    最後一步的地點、物品、人物存在，答案是選項之一或 tianji:<天機>（天機的選項要剛好是候選）；文字只用繁體中文。
    伏筆計數：效果寫的要有鏈讀，鏈讀的要有效果寫（官銀由 guanyin 的規則寫）。"""
    from .foreshadow import FIGURE_SLOT, GUANYIN, TIANJI, TIANJI_ANSWER, asks_of, trips  # noqa: PLC0415  延後 import

    fs = c.foreshadows
    faction_ids = [f.id for f in c.scenario.factions]
    item_ids = [item.id for item in fs.items]
    chain_ids = [ch.id for ch in fs.chains]
    for label, ids in (("伏筆物品", item_ids), ("伏筆", chain_ids)):
        duplicated = sorted({x for x in ids if ids.count(x) > 1})
        need(not duplicated, f"{label} id 重複：{'、'.join(duplicated)}")
    events = {e.id: e for e in c.timetable}

    def check_text(where: str, text: str | None) -> None:
        if text:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}…」）")

    for item in fs.items:
        need(bool(item.name.strip()), f"伏筆物品 {item.id}：name 不能是空的")
        check_text(f"伏筆物品 {item.id}", item.name)

    counters_read: set[str] = set()
    items_read: set[str] = set()

    def check_requires(where: str, req, top: bool = True) -> None:
        known(where, req.clue_items, item_ids, "伏筆物品")
        items_read.update(req.clue_items)
        known(where, req.affinity, c.characters, "人物")
        for key in req.donations:
            loc, sep, kind = key.partition(":")
            need(bool(sep and kind), f"{where}：捐獻 {key!r} 要寫成「據點 id:種類」")
            known(where, [loc], c.locations, "地點")
        counters_read.update(req.counters)
        amounts = [*req.clue_items.values(), *req.donations.values(), *req.affinity.values(), *req.counters.values()]
        need(req.grain >= 0 and all(n >= 0 for n in amounts), f"{where}：條件的數量不能是負的")
        need(top or req.check is None, f"{where}：檢定不能寫在 any_of 裡")
        for sub in req.any_of:
            check_requires(where, sub, top=False)

    def check_wrong(where: str, wrong) -> None:
        known(where, wrong.lose_items, item_ids, "伏筆物品")
        known(where, wrong.affinity, c.characters, "人物")
        check_text(where, wrong.text)

    def check_ask(where: str, ask) -> None:
        option_ids = [o.id for o in ask.options]
        need(len(set(option_ids)) == len(option_ids), f"{where}：選項 id 重複")
        check_text(where, ask.question)
        for o in ask.options:
            check_text(where, o.text)
            if o.wrong is not None:
                check_wrong(f"{where} 選項 {o.id}", o.wrong)
        if ask.answer.startswith(TIANJI_ANSWER):
            key = ask.answer.removeprefix(TIANJI_ANSWER)
            known(where, [key], TIANJI, "天機")
            if key in TIANJI:
                need(
                    sorted(option_ids) == sorted(TIANJI[key]),
                    f"{where}：天機 {key} 的選項要剛好是{'、'.join(TIANJI[key])}（寫的是{'、'.join(option_ids)}）",
                )
        else:
            need(ask.answer in option_ids, f"{where}：答案 {ask.answer} 不是選項之一，也不是 tianji:<天機>")

    for ch in fs.chains:
        where = f"伏筆 {ch.id}"
        known(where, [ch.event], events, "時刻表大事")
        known(where, [ch.side], faction_ids, "陣營")
        event = events.get(ch.event)
        versions = set(event.versions.values()) if event is not None else set()
        if ch.front is not None:
            known(where, [ch.front], front_ids, "戰線")  # 戰線 id，不是大區（同時刻表）
        need(
            ch.front is not None or event is None or event.front is not None,
            f"{where}：要寫 front（{ch.event} 沒有戰線，最後一步的戰況看不到任何一條線）",
        )
        if event is not None and event.kind != "showdown" and ch.side in TIMETABLE_SIDES:  # 決戰的結果由 T8 給鍵
            need(ch.side in event.lock_result, f"{where}：{ch.event} 的 lock_result 沒有 {ch.side}，鎖定了也改不了結果")
        if ch.invalid_if.figure_out is not None:
            known(where, [ch.invalid_if.figure_out], c.characters, "人物")
        for i, f in enumerate(ch.fragments):
            fw = f"{where} 片段{i + 1}"
            known(fw, [f.region], region_ids, "大區")
            check_text(fw, f.text)
            for text in f.versions.values():
                check_text(fw, text)
            known(fw, f.versions, versions, "版本")
            if f.source == "event":
                need(f.event is not None, f"{fw}：來源是 event 就要寫 event")
                if f.event is not None:
                    known(fw, [f.event], c.events, "事件")
            else:
                need(f.event is None, f"{fw}：只有來源是 event 的才寫 event")
            if f.source == "talk":
                need(f.character is not None and bool(f.topic.strip()), f"{fw}：來源是 talk 就要寫 character 與 topic")
                speakers = [x for x in (f.character, f.stand_in) if x is not None]
                known(fw, speakers, c.characters, "人物")
                for fid in speakers:  # 對話得找得到人：要有對話的地方（talk_at）而且能深度對話
                    who = c.characters.get(fid)
                    need(
                        who is None or (who.talk_at is not None and who.deep_interaction),
                        f"{fw}：{fid} 沒有 talk_at（或不能深度對話），這一則永遠聽不到",
                    )
                check_text(fw, f.topic)
            else:
                need(
                    f.character is None and f.stand_in is None and not f.topic and f.affinity_min == 0,
                    f"{fw}：只有來源是 talk 的才寫 character、stand_in、topic、affinity_min",
                )
        final = ch.final
        if final.steps:
            need(final.location is None, f"{where}：寫了 steps 就不要在 final 上寫 location（每一趟各寫各的）")
            need(
                not (final.question or final.options or final.answer or final.then or final.label),
                f"{where}：寫了 steps 就把 label、題目寫在每一趟裡",
            )
        else:
            need(final.location is not None, f"{where}：最後一步要寫 location（或寫 steps）")
        check_requires(f"{where} 最後一步", final.requires)
        seen: set[str] = set()
        for i, trip in enumerate(trips(final)):
            tw = f"{where} 第 {i + 1} 趟" if final.steps else f"{where} 最後一步"
            if trip.location is not None:
                known(tw, [trip.location], c.locations, "地點")
                need(trip.location not in seen, f"{where}：兩趟不能在同一個地點（{trip.location}）")
                seen.add(trip.location)
            else:
                need(not final.steps, f"{tw}：每一趟都要寫 location")
            need(bool(trip.label.strip()), f"{tw}：要寫 label（選單上的字）")
            if trip is not final:
                check_requires(tw, trip.requires)
            need(
                bool(trip.question) or (not trip.options and trip.answer is None and not trip.then),
                f"{tw}：有選項、答案或追問就要寫 question",
            )
            need(not trip.question or bool(trip.options), f"{tw}：題目要有選項")
            need(not trip.question or trip.answer is not None, f"{tw}：題目要有答案（answer）")
            check_wrong(tw, trip.wrong)
            for text in (trip.label, trip.unready, trip.success_text):
                check_text(tw, text)
        for aw, ask in asks_of(ch):
            if ask.options:  # 沒有選項的題上面已經報了
                check_ask(f"{where} {aw}", ask)
        need(bool(final.success_text.strip()), f"{where}：要寫 success_text（完成時的敘事）")
        check_text(where, final.success_text)
        for text in final.success_versions.values():
            check_text(where, text)
        known(where, final.success_versions, versions, "版本")
        known(where, [x for x in (final.figure, final.stand_in) if x is not None], c.characters, "人物")
        texts = [final.success_text, *final.success_versions.values(), *(step.success_text for step in final.steps)]
        uses_figure = any(FIGURE_SLOT in text for text in texts)
        need(final.figure is not None or not uses_figure, f"{where}：用了 {FIGURE_SLOT} 就要寫 figure")
        if final.window == "during_muster":
            need(event is None or event.kind == "showdown", f"{where}：window 是 during_muster 的只能用在決戰（{ch.event} 不是）")

    rule = fs.guanyin
    if rule is not None:
        known("伏筆的官銀", [rule.side, rule.squad_faction], faction_ids, "陣營")
        known("伏筆的官銀", rule.regions, region_ids, "大區")
        check_text("伏筆的官銀", rule.text)
        counters_written.setdefault(GUANYIN, "伏筆的官銀")
    for key, where in sorted(counters_written.items()):
        need(key in counters_read, f"{where}：伏筆計數 {key} 寫了卻沒有任何一條鏈讀它")
    for item_id in item_ids:
        need(item_id in items_read, f"伏筆物品 {item_id}：沒有任何一條鏈的條件讀它")
    for key in sorted(counters_read - set(counters_written)):
        need(False, f"伏筆計數 {key}：有鏈讀它，卻沒有任何效果（或官銀的規則）寫它")


def validate(c: Content) -> None:
    errors: list[str] = []
    from .atlas import region_of  # noqa: PLC0415  延後 import：atlas → world → rules 一路載入，content 不必一開始就依賴它們

    trend_ids = {t.id for t in c.scenario.trends}
    hidden = {t.id for t in c.scenario.trends if t.hidden}
    derived = {t.id for t in c.scenario.trends if t.derived}  # 衍生線（第一季濃縮版的黃巾聲勢）
    season_one_trends = {t.id for t in c.scenario.trends if t.season_one}  # 第一季才有的線（三條戰線、豪強割據）
    region_fronts = {region.front for region in c.map.regions if region.front}  # 戰線
    # 大區多邊形都寫得對（至少 3 個 [x, y] 點）：查地點在哪個大區（atlas.region_of）要拆每個點，寫壞了會炸成 ValueError，
    # 所以要先確定沒壞才查；壞的由後面的大區檢查照舊回報
    polygons_ok = all(
        len(region.points) >= 3 and all(len(point) == 2 for point in region.points) for region in c.map.regions
    )

    def need(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    def known(where: str, keys, valid, kind: str) -> None:
        for key in keys:
            need(key in valid, f"{where}：未知的{kind} {key}")

    for kind in c.config.practice_bonus:  # 熟練加成看的是本人的名聲（善名、惡名、名望……），不是戰鬥屬性
        need(kind in STATS and kind not in ("str", "agi", "con", "wis", "lore"), f"config.practice_bonus 的 {kind} 不是名聲類的屬性")

    faction_ids = [f.id for f in c.scenario.factions]
    item_ids = [item.id for item in c.foreshadows.items]
    counters_written: dict[str, str] = {}  # 伏筆計數 → 第一個寫它的地方（效果的 fs_counters）

    def not_derived(where: str, keys, field: str = "") -> None:
        """衍生線（開關開著時由來源線合成的黃巾聲勢）不能被直接推，要推就推它的來源線。"""
        for key in keys:
            need(key not in derived, f"{where}：{field}不能推衍生線 {key}（要推就推它的來源線）")

    def front_needs_total(where: str, keys) -> None:
        """front 在開關關著時要算進由戰線合成的那條線，所以劇本得有一條衍生線。"""
        need(
            FRONT_KEY not in keys or bool(derived),
            f"{where}：用了 front，劇本卻沒有由戰線合成的大勢線（開關關著時 front 要算進它）",
        )

    marks_written: dict[str, str] = {}  # 痕跡 → 第一個寫它的地方
    marks_read: dict[str, str] = {}  # 痕跡 → 第一個讀它的地方（條件或文字裡的模糊人數）

    def check_mark_key(where: str, key: str) -> None:
        loc, sep, name = key.partition(":")
        need(bool(sep and name.strip()), f"{where}：痕跡 {key!r} 要寫成「地點 id:痕跡名」")
        need(loc in c.locations, f"{where}：痕跡 {key!r} 的地點 {loc} 不存在")

    def read_marks_in(where: str, text: str) -> None:
        for key in MARKS_TOKEN.findall(text):
            check_mark_key(where, key)
            marks_read.setdefault(key, where)

    def check_condition(where: str, cond: Condition) -> None:
        for key in [*cond.marks_min, *cond.marks_max]:
            check_mark_key(where, key)
            marks_read.setdefault(key, where)
        known(where, [*cond.min_stats, *cond.max_stats], STATS, "屬性")
        known(where, cond.sects, c.sects, "門派")
        known(where, [*cond.skills_all, *cond.skills_none], c.skills, "武學")
        known(where, [*cond.trend_min, *cond.trend_max], trend_ids, "大勢線")
        for key in [*cond.trend_min, *cond.trend_max]:
            need(
                key not in season_one_trends,
                f"{where}：條件不能讀第一季的線 {key}（條件讀的是大勢的原數字：開關關著時戰線與割據沒有值、"
                "季中才開季的那一季讀不到起始值；要讀就讀黃巾聲勢這種衍生線或一般的線）",
            )
        known(where, [*cond.revealed_all, *cond.revealed_none], trend_ids, "大勢線")
        known(where, cond.members_none, c.characters, "人物")
        known(where, cond.factions, faction_ids, "陣營")
        known(where, cond.clue_items, item_ids, "伏筆物品")
        for week in (cond.week_min, cond.week_max):
            need(week is None or 1 <= week <= c.config.season_weeks, f"{where}：週次 {week} 不在 1～{c.config.season_weeks} 之間")
        for sub in cond.any_of:
            check_condition(where, sub)

    def no_lore(where: str, eff: Effect) -> None:
        """博聞只靠升級的點數增加（設計 6.3；PM 2026-10-05）：任何效果的 stats 都不能有 lore，給、扣、寫 0 都不行。
        檢定（Check／隨口應對的 stat）可以照樣考博聞，那不是獎勵。"""
        need(LORE not in eff.stats, f"{where}：stats 不能有 {LORE}（博聞只能靠升級的點數增加，事件、奇遇、隨口應對的獎勵都不能給、也不能扣）")

    def check_effect(where: str, eff: Effect) -> None:
        no_lore(where, eff)
        for key, n in eff.marks.items():
            check_mark_key(where, key)
            need(1 <= n <= 3, f"{where}：痕跡 {key} 一次只能加 1～3（不能減）")
            marks_written.setdefault(key, where)
        read_marks_in(where, eff.text)
        known(where, eff.stats, STATS, "屬性")
        known(where, eff.learn_skills, c.skills, "武學")
        known(where, eff.materials, c.materials, "素材")
        known(where, eff.insights, c.insights, "意境")
        for insight_id in eff.insights:
            if insight_id in c.insights and c.insights[insight_id].grant is not None:
                need(False, f"{where}：{c.insights[insight_id].name}只能靠名聲悟得，事件不能給")
        known(where, eff.affinity, c.characters, "人物")
        known(where, eff.trend, trend_ids | {FRONT_KEY}, "大勢線")
        front_needs_total(where, eff.trend)
        not_derived(where, eff.trend)
        known(where, eff.clue_items, item_ids, "伏筆物品")
        for key in eff.fs_counters:
            counters_written.setdefault(key, where)
        if eff.join_sect:
            known(where, [eff.join_sect], c.sects, "門派")
        if eff.next_event:
            known(where, [eff.next_event], c.events, "事件")
        if eff.recruit:
            known(where, [eff.recruit], c.characters, "人物")
            if eff.recruit in c.characters:
                need(c.characters[eff.recruit].kind == "recruitable", f"{where}：結識的 {eff.recruit} 不是可招募的同伴")

    def check_free_text(where: str, ev: Event) -> None:
        """隨口應對（§8.1）：賣的是好玩不是划算，獎勵不能比同一則事件裡最好的檢定選項高；
        也不能串到下一則事件、結識人物、拜師或改旗標（那些都要靠手寫的選項）。"""
        ft, fw = ev.free_text, f"{where} 隨口應對"
        check_effect(fw, ft.effect)
        check_effect(fw, ft.fail_effect)
        rivals = [ch.effect for ch in ev.choices if ch.check is not None] or [ch.effect for ch in ev.choices]
        for key in FREE_TEXT_REWARDS:
            best = max(eff.stats.get(key, 0) for eff in rivals)
            need(
                ft.effect.stats.get(key, 0) <= best,
                f"{fw}：{key} +{ft.effect.stats.get(key, 0)} 比檢定選項最多的 +{best} 還高",
            )
        best_materials = max(sum(eff.materials.values()) for eff in rivals)
        need(
            sum(ft.effect.materials.values()) <= best_materials,
            f"{fw}：素材 {sum(ft.effect.materials.values())} 個比檢定選項最多的 {best_materials} 個還多",
        )
        best_insights = max(len(eff.insights) for eff in rivals)
        need(
            len(ft.effect.insights) <= best_insights,
            f"{fw}：意境 {len(ft.effect.insights)} 個比檢定選項最多的 {best_insights} 個還多",
        )
        for label, eff in (("effect", ft.effect), ("fail_effect", ft.fail_effect)):
            banned = [
                name for name, used in (
                    ("next_event", eff.next_event), ("recruit", eff.recruit), ("join_sect", eff.join_sect),
                    ("flags_add", eff.flags_add), ("world_flags_add", eff.world_flags_add),
                ) if used
            ]
            need(not banned, f"{fw} {label}：不能有 {'、'.join(banned)}")

    cfg = c.config
    for action in ("explore", "train", "socialize"):
        need(action in cfg.action_cost, f"config.action_cost 缺少 {action}")
    for stat in STATS:
        need(stat in cfg.start_stats, f"config.start_stats 缺少 {stat}")
    missing_roads = [road for road in ROADS if road not in cfg.road_factor]
    need(not missing_roads, f"config.road_factor 缺少 {'、'.join(missing_roads)}")
    need(all(factor > 0 for factor in cfg.road_factor.values()), "config.road_factor 的係數都要大於 0")
    need(
        cfg.chaos_low <= cfg.chaos_high,
        f"config.chaos_low 不能大於 chaos_high（{cfg.chaos_low} > {cfg.chaos_high}：亂局的區間是空的，割據只會一路回落）",
    )

    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        need(len(set(loc.connections)) == len(loc.connections), f"{where}：connections 重複列了同一個地點")
        for dest in loc.connections:
            if dest not in c.locations:
                errors.append(f"{where}：連到不存在的地點 {dest}")
            elif loc.id not in c.locations[dest].connections:
                errors.append(f"地點 {loc.id} 連到 {dest}，但 {dest} 沒有連回來")
            elif loc.road_to(dest) != c.locations[dest].road_to(loc.id) and loc.id < dest:
                errors.append(
                    f"地點 {loc.id} 到 {dest} 寫的是{loc.road_to(dest)}，{dest} 回來寫的是"
                    f"{c.locations[dest].road_to(loc.id)}（一條路兩頭要寫同一種）"
                )
        for version in loc.desc_when:  # 描寫隨世界旗標換版（計畫 T8 的宛城）
            need(bool(version.world_flag.strip()), f"{where}：desc_when 要寫 world_flag")
            need(to_traditional(version.text) == version.text, f"{where}：desc_when 的文字只能用繁體中文（「{version.text[:12]}…」）")
        known(where, loc.enemies, c.squads, "敵方隊伍")
        known(where, loc.train_trend, trend_ids | {FRONT_KEY}, "大勢線")
        not_derived(where, loc.train_trend, "train_trend ")
        front_needs_total(where, loc.train_trend)
        if polygons_ok:
            local = region_of(c, loc.id)
            local_front = local.front if local is not None else None
            for key in loc.train_trend:
                if key in region_fronts:
                    need(
                        key == local_front,
                        f"{where}：train_trend 的 {key} 不是這個地點所在大區的戰線（{local_front or '這裡沒有戰況'}）",
                    )
        known(where, loc.materials, c.materials, "素材")
        need(
            0 <= loc.x <= c.map.width and 0 <= loc.y <= c.map.height,
            f"{where}：座標 ({loc.x}, {loc.y}) 超出地圖範圍",
        )
    need(c.scenario.start_location in c.locations, f"劇本起點 {c.scenario.start_location} 不存在")

    for sect in c.sects.values():
        known(f"門派 {sect.id}", [sect.location], c.locations, "地點")

    for squad in c.squads.values():
        known(f"敵方隊伍 {squad.id}", [drop.material for drop in squad.drops], c.materials, "素材")
        if squad.faction is not None:
            known(f"敵方隊伍 {squad.id}", [squad.faction], [f.id for f in c.scenario.factions], "陣營")

    # 每一種素材都要至少有一個拿得到的管道，否則它是死內容。第一版的「鎮山鐵」就是這樣
    # 漏掉的：掉天品的兩個對手屬剛與屬柔、奇遇給屬快，屬慢沒人負責，而難度 >=100 的對手
    # 都寫了明確 drops，所以依難度的預設表（會按對手屬性挑）對它們根本不執行。
    unreachable = sorted(set(c.materials) - _material_sources(c))
    need(
        not unreachable,
        "這些素材沒有任何取得管道（沒有對手掉、沒有地點撿、沒有事件給）："
        + "、".join(f"{c.materials[mid].name}（{mid}）" for mid in unreachable),
    )

    # 合成、合併的決定性組名字表（模型不可用時的退路）：不能是空的，而且組出來的每一個名字都得
    # 通過命名過濾——這條退路一定會被走到（整季模擬把模型 mock 掉），組出壞名字會永久登記。
    names = c.craft_names
    need(bool(names.prefixes), "craft_names.prefixes 不能是空的")
    need(bool(names.wugong), "craft_names.wugong 不能是空的")
    need(bool(names.neigong), "craft_names.neigong 不能是空的")
    need(bool(names.insight), "craft_names.insight 不能是空的")
    for prefix in names.prefixes:
        for suffix in [*names.wugong, *names.neigong, *names.insight]:
            reason = name_problem(prefix + suffix, c)
            need(reason is None, f"craft_names 組出的名字「{prefix + suffix}」過不了命名過濾：{reason}")
    for word in c.banned_names:
        need(bool(word.strip()), "banned_names 裡有空字串")
    check_check_voice(c, need)
    check_front_lines(c, need)
    check_combat_lines(c, need)
    check_traits(c, need)
    # 沒寫 drops 的對手走 materials.py 依難度的預設掉落表，所以每一階都得有素材可挑。
    for tier in sorted(TIER_NAMES):
        need(
            any(m.tier == tier for m in c.materials.values()),
            f"content/materials.json 沒有任何第 {tier} 階（{TIER_NAMES[tier]}）的素材，預設掉落表會挑不到東西",
        )

    for ev in c.events.values():
        where = f"事件 {ev.id}"
        known(where, ev.locations, c.locations, "地點")
        check_condition(where, ev.condition)
        need(
            any(ch.condition == Condition() for ch in ev.choices),
            f"{where}：至少要有一個沒有條件的選項，否則玩家可能卡住",
        )
        for i, ch in enumerate(ev.choices):
            cw = f"{where} 選項{i}"
            check_condition(cw, ch.condition)
            check_effect(cw, ch.effect)
            check_effect(cw, ch.fail_effect)
            if ch.combat:
                known(cw, [ch.combat], c.squads, "敵方隊伍")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")
                if ch.check.practice:
                    known(cw, [ch.check.practice], c.config.practice_bonus, "熟練（config.practice_bonus）")
        read_marks_in(where, ev.text)
        if ev.free_text is not None:
            check_free_text(where, ev)
        recruits = {eff.recruit for ch in ev.choices for eff in (ch.effect, ch.fail_effect) if eff.recruit}
        for cid in sorted(recruits):
            need(
                cid in ev.condition.members_none,
                f"{where}：結識 {cid} 的事件，condition.members_none 要列出 {cid}（已入門就不該再遇到）",
            )
        if ev.fortune:
            need(not ev.actions, f"{where}：福緣事件只由交友觸發，actions 要是空的")
            need(all(ch.effect.recruit for ch in ev.choices), f"{where}：福緣事件的每個選項都要結識一個人")
            for i, ch in enumerate(ev.choices):
                need(
                    ch.check is None and ch.combat is None,
                    f"{where} 選項{i}：福緣事件的選項不能有檢定或戰鬥（福緣自己送上門時直接套用第一個選項的效果）",
                )

    for trend in c.scenario.trends:
        need(
            trend.id != FRONT_KEY,
            f"大勢線 {trend.id}：id 不能叫 {FRONT_KEY}（那是效果與歷練裡「所在大區的戰線」的特殊鍵，撞名會分不出推的是哪一條）",
        )
        if not trend.derived:
            continue
        where = f"大勢線 {trend.id}"
        known(where, trend.derived, trend_ids, "大勢線")
        need(not set(trend.derived) & derived, f"{where}：來源不能是另一條衍生線")
        need(all(weight > 0 for weight in trend.derived.values()), f"{where}：權重都要大於 0")
        total = sum(trend.derived.values())
        need(abs(total - 1) < 1e-6, f"{where}：權重加起來要是 1（現在是 {total:g}）")

    region_ids = [region.id for region in c.map.regions]
    duplicated = sorted({rid for rid in region_ids if region_ids.count(rid) > 1})
    need(not duplicated, f"大區 id 重複：{'、'.join(duplicated)}")
    for region in c.map.regions:
        where = f"大區 {region.id}"
        known(where, region.trends, trend_ids, "大勢線")
        if region.front is not None:
            known(where, [region.front], trend_ids, "大勢線")
            need(region.front not in derived, f"{where}：front 不能是衍生線 {region.front}")
        need(
            len(region.points) >= 3 and all(len(point) == 2 for point in region.points),
            f"{where}：多邊形至少要有 3 個 [x, y] 點",
        )

    # 河流、地形、指北針（輿圖美術設計第四節）：座標都要在地圖範圍內。
    def on_map(points) -> bool:
        return all(len(p) == 2 and 0 <= p[0] <= c.map.width and 0 <= p[1] <= c.map.height for p in points)

    for i, river in enumerate(c.map.rivers):
        where = f"河流 {river.name}" if river.name else f"河流第 {i + 1} 條"
        need(len(river.points) >= 2, f"{where}：至少要有 2 個 [x, y] 點")
        need(on_map(river.points), f"{where}：座標超出地圖範圍")
        need(0 < river.width[0] <= river.width[1], f"{where}：width 寫 [上游寬, 下游寬]，都要大於 0、往下游不能變窄")
    for i, piece in enumerate(c.map.terrain):
        where = f"地形 {piece.name}" if piece.name else f"地形第 {i + 1} 筆"
        if piece.kind == "forest":
            need(len(piece.points) >= 3, f"{where}：林地的 points 至少要有 3 個 [x, y] 點")
        else:
            need(len(piece.spine) >= 2, f"{where}：spine 至少要有 2 個 [x, y] 點")
            low, high = TERRAIN_SIZE
            need(low <= piece.size <= high, f"{where}：size 要在 {low}～{high} 之間（寫的是 {piece.size}）")
        need(on_map(piece.spine + piece.points), f"{where}：座標超出地圖範圍")
    need(c.map.compass is None or on_map([c.map.compass]), f"指北針 {c.map.compass} 超出地圖範圍")

    # 路上見聞（路上設計第五節）：每一種路、每一個大區的組合都要有幾則可挑；小收穫不超過上限、一則最多一種、
    # 不能有別的效果（不發傳聞：每人每站都可能觸發，發到傳聞板會洗版）；文字只用繁體中文。
    for road in ROADS:
        for area in region_ids or [None]:
            count = sum(
                1 for sight in c.road_sights.values()
                if (not sight.roads or road in sight.roads) and (not sight.regions or area in sight.regions)
            )
            need(
                count >= ROAD_SIGHTS_PER_SPOT,
                f"路上見聞：{road}・{area or '不分大區'} 只有 {count} 則可挑（至少要 {ROAD_SIGHTS_PER_SPOT} 則）",
            )
    for sight in c.road_sights.values():
        where = f"路上見聞 {sight.id}"
        known(where, sight.regions, region_ids, "大區")
        need(bool(sight.text.strip()), f"{where}：text 不能是空的")
        need(to_traditional(sight.text) == sight.text, f"{where}：text 只能用繁體中文")
        eff = sight.effect
        need(
            eff.model_copy(update={"stats": {}, "materials": {}}) == Effect(),
            f"{where}：小收穫只能用 stats 或 materials（不能寫 text、rumor 或其他效果）",
        )
        need(len(eff.stats) + len(eff.materials) <= 1, f"{where}：小收穫一則最多一種")
        no_lore(where, eff)
        for stat, amount in eff.stats.items():
            if stat == LORE:  # no_lore 已經報過，不再用「只能是銀兩或心得」重複報一次
                continue
            cap = ROAD_SIGHT_CAPS.get(stat)
            need(cap is not None and 0 < amount <= cap, f"{where}：stats 只能是銀兩 1～10 或心得 1～5（寫的是 {stat} {amount}）")
        known(where, eff.materials, c.materials, "素材")
        for mid, count in eff.materials.items():
            if mid in c.materials:
                need(count == 1 and c.materials[mid].tier == 1, f"{where}：素材只能是一階 1 個（寫的是 {mid} ×{count}）")

    for th in c.scenario.thresholds:
        where = f"門檻 {th.id}"
        known(where, [th.trend], trend_ids, "大勢線")
        need(
            th.trend not in season_one_trends,
            f"{where}：不能掛在第一季的線 {th.trend}（門檻看的是原數字：開關關著時戰線與割據沒有值；要掛就掛衍生線或一般的線）",
        )
        if th.location:
            known(where, [th.location], c.locations, "地點")
        if th.starts_battle:
            known(where, [th.starts_battle], c.battles, "戰鬥")
        need(
            not (th.trend in hidden and th.op == "<="),
            f"{where}：隱藏大勢線不能用 <= 門檻（未浮現時數值為 0，會立刻觸發）",
        )
    for sim in c.scenario.sim_players:
        where = f"虛擬玩家 {sim.name}"
        known(where, sim.trend, trend_ids, "大勢線")
        not_derived(where, sim.trend)
        if sim.requires_revealed:
            known(where, [sim.requires_revealed], trend_ids, "大勢線")
        known(where, sim.haunts, c.locations, "地點")
        for rumor in sim.rumors:
            if isinstance(rumor, SimRumor):
                known(f"{where} 的傳聞「{rumor.text}」", [rumor.location], c.locations, "地點")
        check_condition(where, sim.condition)
    for ending in c.scenario.endings:
        check_condition(f"結局 {ending.id}", ending.condition)
        if not ending.season_one:
            need(
                not (ending.stance_min or ending.stance_max or ending.stance_top),
                f"結局 {ending.id}：stance_min／stance_max／stance_top 只有第一季的結局（season_one）能寫",
            )

    line_ids = [s.id for s in c.scenario.storylines]
    need(len(set(line_ids)) == len(line_ids), "主線 id 重複")
    for i, line in enumerate(c.scenario.storylines):
        where = f"主線 {line.id}"
        if i == 0:
            need(line.replaces_when is None, f"{where}：第一條主線不能有 replaces_when")
        else:
            need(line.replaces_when is not None, f"{where}：支線主線必須有 replaces_when")
            if line.replaces_when is not None:
                check_condition(where, line.replaces_when)
        for j, act in enumerate(line.acts):
            aw = f"{where} 第{j + 1}幕 {act.id}"
            known(aw, act.places, c.locations, "地點")
            if j == len(line.acts) - 1:
                need(act.advance_when is None, f"{aw}：最後一幕不能有 advance_when")
            else:
                need(act.advance_when is not None, f"{aw}：非最後一幕必須有 advance_when")
                if act.advance_when is not None:
                    check_condition(aw, act.advance_when)
    for ending in c.scenario.endings:
        if ending.storyline:
            known(f"結局 {ending.id}", [ending.storyline], line_ids, "主線")
    fire_ids = [t.id for t in c.scenario.thresholds] + [e.id for e in c.scenario.world_events]
    need(len(set(fire_ids)) == len(fire_ids), "大勢門檻與世界事件的 id 重複")
    for event in c.scenario.world_events:
        check_condition(f"世界事件 {event.id}", event.condition)
        if event.location:
            known(f"世界事件 {event.id}", [event.location], c.locations, "地點")
        if event.starts_battle:
            known(f"世界事件 {event.id}", [event.starts_battle], c.battles, "戰鬥")
    # 第一季不觸發的 beta 內容（計畫 T8、與 T4 說好的格式）：照種類各自檢查 id 存在，不跨種類比對
    off = c.scenario.season_one_off
    for kind, ids, valid, label in (
        ("thresholds", off.thresholds, {t.id for t in c.scenario.thresholds}, "門檻"),
        ("storylines", off.storylines, line_ids, "主線"),
        ("battles", off.battles, c.battles, "戰鬥"),
        ("events", off.events, c.events, "事件"),
        ("milestones", off.milestones, {m.id for m in c.scenario.milestones}, "個人目標"),
    ):
        known(f"第一季不觸發的 {kind}", ids, valid, label)

    scenario_faction_ids = [f.id for f in c.scenario.factions]
    need(len(set(scenario_faction_ids)) == len(scenario_faction_ids), "劇本：陣營 id 重複")
    for faction in c.scenario.factions:
        known(f"陣營 {faction.id}", faction.join_at, c.locations, "地點")
        known(f"陣營 {faction.id}", faction.sects, c.sects, "門派")
        known(f"陣營 {faction.id}", faction.goals, trend_ids, "大勢線")
        not_derived(f"陣營 {faction.id}", faction.goals, "goals ")
        need(all(d in (-1, 1) for d in faction.goals.values()), f"陣營 {faction.id}：goals 的方向只能是 1 或 -1")
        need(to_traditional(faction.defect_text) == faction.defect_text,
             f"陣營 {faction.id}：defect_text 只能用繁體中文（「{faction.defect_text[:12]}」）")

    showdown_events = {e.id: e for e in c.timetable if e.kind == "showdown"}
    showdown_battles: dict[tuple[str, str | None], str] = {}  # （時刻表決戰, 版本）→ 第一筆寫它的戰鬥

    def check_showdown_battle(battle: BattleDef, where: str) -> None:
        """時刻表決戰（計畫 T8）：指到時刻表上的一件決戰；分版本的每一筆寫一個那件大事的版本、不分的不寫；
        要寫戰線（起點照它算）與守方（剛好 50 算誰贏）；陣營依序是官軍、黃巾（戰局以官軍為正向，時刻表的結果鍵也是）；
        同一件決戰的同一版只能有一筆。"""
        known(where, [battle.timetable_event], showdown_events, "時刻表決戰")
        event = showdown_events.get(battle.timetable_event)
        if event is not None:
            versions = list(dict.fromkeys(event.versions.values()))
            need(
                battle.version in versions if versions else battle.version is None,
                f"{where}：version {battle.version} 不是 {event.id} 的版本（{'、'.join(versions) or '不分版本'}）",
            )
        need(battle.front is not None and battle.defender is not None, f"{where}：時刻表決戰要寫 front 與 defender")
        if battle.front is not None:
            known(where, [battle.front], region_fronts, "戰線")
        need(
            [f.id for f in battle.factions] == list(TIMETABLE_SIDES),
            f"{where}：時刻表決戰的陣營要依序是 {'、'.join(TIMETABLE_SIDES)}（戰局以官軍為正向）",
        )
        key = (battle.timetable_event, battle.version)
        version = f" 的 {key[1]} 版" if key[1] else ""
        need(key not in showdown_battles, f"時刻表決戰 {key[0]}{version}有兩筆戰鬥：{showdown_battles.get(key)}、{battle.id}")
        showdown_battles.setdefault(key, battle.id)

    for battle in c.battles.values():
        where = f"戰鬥 {battle.id}"
        battle_sides = [f.id for f in battle.factions]  # 不能叫 faction_ids：那是劇本陣營的名單，後面的條件檢查還要用
        need(len(set(battle_sides)) == len(battle_sides), f"{where}：陣營 id 重複")
        if scenario_faction_ids:
            known(where, battle_sides, scenario_faction_ids, "陣營")
        if battle.region is not None:
            known(where, [battle.region], region_ids, "大區")
        need(
            battle.region is not None or not c.map.regions,
            f"{where}：要寫 region（決戰所在的大區；人要在那裡才能加入）",
        )
        act_ids = [a.id for a in battle.acts]
        need(len(set(act_ids)) == len(act_ids), f"{where}：幕 id 重複")
        # 換幕照回合數走（rounds_per_act），不看戰局，幕本身沒有換幕條件；rounds_per_act、decisive_margin
        # 至少 1 由模型的 ge=1 擋（戰鬥系統設計 3.2）
        for act in battle.acts:
            aw = f"{where} {act.id}"
            for option in act.options:
                if not option.free_text:  # free_text 選項不查表，機制走 FreeTextGamble 擲骰，不需要 action_tags 裡有對應的 tag
                    known(f"{aw} 選項「{option.text}」", [option.tag], battle.action_tags, "行動分類")
                if option.faction is not None:
                    known(f"{aw} 選項「{option.text}」", [option.faction], battle_sides, "陣營")
        need(
            battle.free_text_gamble is not None or not any(o.free_text for a in battle.acts for o in a.options),
            f"{where}：有 free_text 選項，必須設定 free_text_gamble",
        )
        for outcome in battle.outcomes:
            known(f"{where} 結果「{outcome.title}」", [outcome.faction], battle_sides, "陣營")
            known(f"{where} 結果「{outcome.title}」", outcome.trend_delta, trend_ids, "大勢線")
            not_derived(f"{where} 結果「{outcome.title}」", outcome.trend_delta)
        need(
            battle.outcomes[-1].trend_min is None and battle.outcomes[-1].trend_max is None,
            f"{where}：最後一個結果必須沒有數值門檻（作為保底結果，一定要能命中）",
        )
        if battle.timetable_event is not None:
            check_showdown_battle(battle, where)

    for season_one in (False, True):  # beta 季與第一季各自的保底：那一季清單裡的最後一筆（world.evaluate_ending，計畫 T9）
        endings = [e for e in c.scenario.endings if e.season_one == season_one]
        if season_one and not endings:
            continue
        last = endings[-1] if endings else None
        need(
            last is not None and last.condition == Condition() and last.storyline is None
            and not last.stance_min and not last.stance_max,
            f"劇本{'第一季' if season_one else ''}的最後一個結局必須沒有條件、也不限主線（作為保底結局）",
        )

    for milestone in c.scenario.milestones:
        check_condition(f"個人目標 {milestone.id}", milestone.condition)
    flags = [step.season_one for step in c.tutorial.steps]
    need(
        flags == sorted(flags),
        "tutorial.json：第一季才有的步驟（season_one）要排在最後——存檔記的是第幾步，插在中間會指到不同的步驟",
    )
    for step in c.tutorial.steps:
        where = f"新手引導 {step.id}"
        known(where, step.done_when.locations, c.locations, "地點")
        check_condition(where, step.done_when.condition)
        check_effect(where, step.reward)

    # ── 序章（新手引導計畫一）──
    t = c.tutorial
    huts = [loc.id for loc in c.locations.values() if loc.prologue_only]
    if t.location is None:
        need(not huts, f"地點 {huts} 標了 prologue_only，但 tutorial.json 沒有序章（location）")
        need(t.prologue_steps == 0, "tutorial.json：沒有序章（location）時 prologue_steps 要是 0")
    else:
        need(huts == [t.location], f"tutorial.json：序章的地點 {t.location} 要是唯一一個 prologue_only 的地點（現在是 {huts}）")
        hut = c.locations.get(t.location)
        need(
            hut is not None and [getattr(x, "to", x) for x in hut.connections] == [c.scenario.start_location],
            f"序章的地點 {t.location} 只能連到起點 {c.scenario.start_location}",
        )
        base = sum(1 for step in t.steps if not step.season_one)
        need(1 <= t.prologue_steps <= base, f"tutorial.json：prologue_steps 要在 1～{base}（不分季的步數）之間")
        need(t.start_event in c.events, f"tutorial.json：start_event {t.start_event} 不存在")
        if 1 <= t.prologue_steps <= len(t.steps):  # 序章最後一步（出師）要放得出草廬：allow 有 move:（prologue.can_travel 看的就是它）
            last = t.steps[t.prologue_steps - 1]
            need(
                any(entry.startswith("move:") for entry in last.allow),
                f"新手引導 {last.id}：序章最後一步的 allow 要有 move:（不然走不出草廬）",
            )
    for i, step in enumerate(t.steps):
        where = f"新手引導 {step.id}"
        special = (step.scene or step.line or step.reveal or step.glow or step.allow or step.explore_event or step.enemies
                   or step.force_tier or step.sure_cultivate or step.instant_rest or step.fuse_base or step.melt_only
                   or step.give_art)
        need(not special or i < t.prologue_steps, f"{where}：序章才有的欄位只能寫在前 {t.prologue_steps} 步")
        bad = [k for k in step.reveal if k not in REVEAL_KEYS]
        need(not bad, f"{where}：reveal 不認得 {bad}")
        unknown = [entry for entry in step.allow if not allow_known(entry)]
        need(
            not unknown,
            f"{where}：allow 不是選單上的行動 {unknown}（閒著的選單做得出來的 id 列在 models.ALLOW_FIXED／ALLOW_FAMILIES；"
            "引擎新加的行動要先補進那裡）",
        )
        need(step.explore_event is None or step.explore_event in c.events, f"{where}：explore_event {step.explore_event} 不存在")
        known(where, step.enemies, c.squads, "對手")
        need(step.force_tier is None or step.force_tier in encounter.TIERS, f"{where}：force_tier {step.force_tier} 不是判定結果")
        for art in (step.fuse_base, step.melt_only, step.give_art.id if step.give_art else None):
            need(art is None or art in c.skills, f"{where}：武學 {art} 不存在")
    recipe_keys, recipe_names = set(), set()
    for recipe in c.preset_recipes:
        where = f"師門配方 {recipe.base}+{recipe.insight}"
        need(recipe.base in c.skills, f"{where}：底 {recipe.base} 不存在")
        recipe_insight = c.insights.get(recipe.insight)
        need(recipe_insight is not None and recipe_insight.grant is None, f"{where}：意境 {recipe.insight} 要是探索悟得到的基本意境")
        need((recipe.base, recipe.insight) not in recipe_keys, f"{where}：同一個底與意境寫了兩次")
        need(recipe.name not in recipe_names, f"師門配方的名字 {recipe.name} 重複")
        problem = name_problem(recipe.name, c)
        need(problem in (None, PRESET_CLASH), f"{where}：名字 {recipe.name} 過不了命名過濾（{problem}）")
        recipe_keys.add((recipe.base, recipe.insight))
        recipe_names.add(recipe.name)

    # ── 意境與基礎武學（武學與成長設計附錄 A～C）──
    for insight in c.insights.values():
        need(insight.grant is None or insight.lean != "無", f"意境 {insight.id}：靠名聲悟得的意境要有正邪")
    for loc in c.locations.values():
        known(f"地點 {loc.id}", loc.insights, c.insights, "意境")
        for insight_id in loc.insights:
            if insight_id in c.insights and c.insights[insight_id].grant is not None:
                need(False, f"地點 {loc.id}：{c.insights[insight_id].name}只能靠名聲悟得，不能放在地點上")
    for skill in c.skills.values():
        if skill.learn is None:
            continue
        where = f"武學 {skill.id}"
        need(skill.quality != "絕學", f"{where}：絕學（本命武學）不能在各地學")
        known(where, [skill.learn.at], c.locations, "地點")
        if skill.learn.faction:
            known(where, [skill.learn.faction], faction_ids, "陣營")
        if skill.learn.sect:
            known(where, [skill.learn.sect], c.sects, "門派")
    starters = c.config.starter_skills
    known("config.starter_skills", starters, c.skills, "武學")
    if starters and all(s in c.skills for s in starters):
        need(
            sorted(c.skills[s].kind for s in starters) == ["內功", "武學"],
            "config.starter_skills 要剛好一門內功、一門武學",
        )
        need(all(c.skills[s].quality == "下品" for s in starters), "config.starter_skills 要是下品的基礎武學")

    for ch in c.characters.values():
        where = f"人物 {ch.id}"
        for stat in ("str", "agi", "con", "wis"):
            need(stat in ch.stats, f"{where}：stats 缺少 {stat}")
        if ch.sect:
            known(where, [ch.sect], c.sects, "門派")
        if ch.starting_wugong:
            known(where, [ch.starting_wugong], c.skills, "武學")
            if ch.starting_wugong in c.skills:
                need(c.skills[ch.starting_wugong].kind == "武學", f"{where}：starting_wugong 要指向 kind=武學 的武學")
        if ch.starting_neigong:
            known(where, [ch.starting_neigong], c.skills, "武學")
            if ch.starting_neigong in c.skills:
                need(c.skills[ch.starting_neigong].kind == "內功", f"{where}：starting_neigong 要指向 kind=內功 的武學")
        need(
            ch.kind is not None or ch.starting_wugong is None,
            f"{where}：敵人（kind 沒填）不需要 starting_wugong，那是同伴才有的欄位",
        )
        if ch.recruit_at:
            known(where, [ch.recruit_at], c.locations, "地點")
            need(ch.kind == "recruitable", f"{where}：只有 kind=recruitable 的同伴需要 recruit_at")
        if ch.talk_at:
            known(where, [ch.talk_at], c.locations, "地點")
            need(ch.kind == "locked", f"{where}：只有 kind=locked 的龍頭人物需要 talk_at（可招募的同伴用 recruit_at）")
        if ch.affinity_tag_deltas:
            for tag in ch.affinity_tag_deltas:
                need(tag in DIALOGUE_TAGS, f"{where}：affinity_tag_deltas 的 {tag!r} 不是合法的交友 tag")
        need(len(ch.brush_off) <= 3, f"{where}：brush_off 最多三句")
    for squad in c.squads.values():
        where = f"敵方隊伍 {squad.id}"
        need(squad.difficulty >= 0, f"{where}：difficulty 不能是負的")

    front_ids = sorted(region_fronts)  # 戰線 id 照 T1 的大區 front，不另寫一份清單
    check_timetable(c, need, known, front_ids, trend_ids)
    check_figures(c, need, known, front_ids)
    check_foreshadows(c, need, known, region_ids, front_ids, counters_written)
    check_orders(c, need, known, front_ids)
    check_promotions(c, need, known)
    check_opportunities(c, need, known, front_ids)

    for key, where in sorted(marks_written.items()):
        need(key in marks_read, f"{where}：痕跡 {key} 寫了卻沒有任何條件或文字讀它")
    for key, where in sorted(marks_read.items()):
        need(key in marks_written, f"{where}：痕跡 {key} 沒有任何效果寫它，條件永遠不會成立")

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
