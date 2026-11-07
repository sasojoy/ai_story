"""載入 content/ 底下與各包 content/ 底下（Feature.content 宣告的，全部拆包第 62 批）的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。

sanguo-companions 合併大幅簡化了這裡的驗證規則（見設計文件開放決策記錄）：舊制度圍繞
天地玄黃品階/統御區間/流派資質 S 級數量/招賢卡池/收徒地點的一大批交叉檢查全部拿掉，
因為新制度（同伴全服唯一、無抽卡、無多隊、無舊武學品階系統）根本沒有這些概念。只保留
基本的交叉引用完整性檢查（id 存在、不重複、地點互相連通等），細緻的內容規則之後好玩
再視需要補回來。
"""
from __future__ import annotations

import functools
import json
import math
import re
from pathlib import Path
from typing import get_args

from pydantic import BaseModel, ValidationError

from . import encounter
from .encounter import FALLBACK_TIER, TIER_RATIOS
from .front_lines import BAND_KEYS
from .materials import DEFAULT_DROPS, TIER_NAMES
from .models import (
    ArtBook,
    BEST_OF,
    BattleDef,
    CharacterDef,
    Check,
    CheckVoice,
    CombatLines,
    Condition,
    Config,
    Content,
    CraftNames,
    CreateForms,
    DIALOGUE_TAGS,
    DuelBoss,
    Effect,
    Event,
    FRONT_KEY,
    FigureDef,
    FollowerDef,
    Foreshadows,
    ForgeSecret,
    FrontLines,
    GLOW_KEYS,
    GOOD_HORSE,
    GearBook,
    GiftDef,
    HeroineDef,
    Hints,
    InsightDef,
    InsightScene,
    Itinerary,
    Location,
    Look,
    MOVES,
    MallItem,
    MapLayout,
    MarkRule,
    MarkText,
    Material,
    MingtieContent,
    Opening,
    OppDef,
    OrdersContent,
    PLACE_KINDS,
    PersonaAxis,
    PresetRecipe,
    PromotionDef,
    RECRUITER_ALLIED_FIELDS,
    REVEAL_KEYS,
    ROADS,
    RealDay,
    RealSlot,
    RelationDef,
    RoadSight,
    STATS,
    Scenario,
    SecretRecipe,
    Sect,
    ShardDef,
    SignatureArmDef,
    SimRumor,
    SkillDef,
    Squad,
    StatDef,
    SteedDef,
    StoryDef,
    TREASURE_EFFECTS,
    Tier4Named,
    TimetableEvent,
    TraitBook,
    TreasureDef,
    Tutorial,
    WEAPON_KINDS,
    allow_known,
)
from .martial_arts import ATTRIBUTE_COUNTERS, ATTRIBUTES
from .naming import GEAR_CLASH, PRESET_CLASH, SEAL_CLASH, name_problem
from .armor import FORGE_NOUNS as ARMOR_FORGE_NOUNS, word_problem as armor_word_problem
from .weapons import ATTR_WORDS as WEAPON_ATTR_WORDS, NOUNS as WEAPON_NOUNS, WEAPON_WORDS, kind_problem as weapon_kind_problem, shop_name as weapon_shop_name
from .zh import to_traditional
from .core.content_base import NUMBER_IN_TEXT, TIMETABLE_SIDES, check_line as _check_line, check_traditional as _check_traditional, event_effects, stage_events, week7 as _week7

FIGHT_TIERS = {tier for tier, _ in TIER_RATIOS} | {FALLBACK_TIER}  # 一場遭遇戰的結果：條件 fight_tiers 可以寫的值
ROAD_SIGHTS_PER_SPOT = 2  # 路上見聞：每一種路、每一個大區的組合至少要有幾則可挑（路上設計第五節）
ROAD_SIGHT_CAPS = {"silver": 10, "xinde": 5}  # 路上見聞的小收穫上限
TERRAIN_SIZE = (8, 40)  # 山脈、丘陵的山頭高度範圍（輿圖美術設計第四節）


class ContentError(Exception):
    pass


# 設定覆寫檔（content/profiles/<名字>.json）的環境變數。server.py、run_bots.py、scripts/sim_*.py 讀它傳進
# load_content；引擎自己不讀環境變數（計畫 T2「總開關與週末設定」）。
PROFILE_ENV = "TIANXIA_PROFILE"


def env_profile() -> str | None:
    """這台機器用哪一份設定覆寫檔：環境變數 TIANXIA_PROFILE（沒設或空字串＝預設）。server.py、run_bots.py 與主機端建角色的
    scripts/set_password.py 都從這裡讀，三邊的設定才會一樣（set_password 以前不看它：週末設定下建的角色拿到預設設定的贈禮那一行）。"""
    import os  # noqa: PLC0415  只有這裡與 _with_local_admins 用得到

    return os.environ.get(PROFILE_ENV) or None


DEFAULT_SERVING_PROFILE = "season21"  # 拿掉二（甲）：週末設定關門，主機端沒帶 TIANXIA_PROFILE 就套 21 天季


def serving_profile() -> str:
    """伺服器、假人與主機端工具「當主程式跑」時用的設定：環境變數有帶照它，沒帶套 season21。
    env_profile() 不改（import server 的測試與 same_behavior 的子行程靠它沒帶＝預設內容）。"""
    return env_profile() or DEFAULT_SERVING_PROFILE


TIER_BANDS = {2: (9, 12), 3: (12, 15)}  # 第二、三階事件的難度帶（事件分級設計稿：照剛開門的人定）；第一階照地點的危險度（tests/season/test_real_content.py）


def stamp_tier(event: Event) -> None:
    """事件分級：把事件的階蓋到它每一個檢定上（選項、隨口應對分岔的後果），rules.check_outlook 照它決定放不放寬。"""
    checks = [ch.check for ch in event.choices]
    if event.free_text is not None:
        checks += [o.check for o in event.free_text.outcomes]
    for check in checks:
        if check is not None:
            check.tier = event.tier


def _load_attributes(content: Content, path: Path) -> None:
    """屬性定義（content/attributes.json；屬性與跨季架構 v2 第二節第 1 層）：顯示名蓋進 Config.stat_names（畫面上讀 stat_names 的
    地方照舊），改名只改這個檔。第 ① 階段的鍵與順序要跟 team.COMBAT_STATS 一樣（第 ② 階段換成五項時一起改）。沒有這個檔照舊。"""
    if not path.exists():
        return
    content.attributes = [_build(StatDef, raw) for raw in _read(path)]
    for attr in content.attributes:
        content.config.stat_names[attr.key] = attr.name


@functools.cache
def _graded_fields(cls: type) -> tuple[str, ...]:
    """這一種模型裡可能（一路往下）放著 Check 或 Effect 的欄位：resolve_grades 只走這些（整份內容全走一遍要多花 0.2 秒）。"""
    return tuple(name for name, field in cls.model_fields.items() if _may_hold_grades(field.annotation, frozenset()))


def _may_hold_grades(tp, seen: frozenset) -> bool:
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        if tp in (Check, Effect):
            return True
        if tp in seen:
            return False
        return any(_may_hold_grades(f.annotation, seen | {tp}) for f in tp.model_fields.values())
    return any(_may_hold_grades(arg, seen) for arg in get_args(tp))


def resolve_grades(content: Content) -> None:
    """難度等級與獎勵等級換成數字（屬性與跨季架構 v2 第五節；載入時一次）：每一個寫 grade 的檢定照 Config.checks.grades 換成
    difficulty（dc ＋ shift），每一個效果的 stats 寫成等級的照 Config.rewards 換成 int（鍵的順序不動：江湖紀錄的得失照它寫）。
    寫錯的等級、超過的微調當場報錯。整份內容走一遍（設定本身不走）。"""
    checks = {g.key: g for g in content.config.checks.grades}
    shift_max = content.config.checks.shift_max
    rewards = content.config.rewards
    reward_at = {g.key: i for i, g in enumerate(rewards.grades)}
    errors: list[str] = []
    seen: set[int] = set()

    def visit(obj, where: str) -> None:
        if isinstance(obj, BaseModel):
            if id(obj) in seen or obj is content.config:
                return
            seen.add(id(obj))
            if isinstance(obj, Check) and obj.grade is not None:
                grade = checks.get(obj.grade)
                if grade is None:
                    errors.append(f"{where}：沒有「{obj.grade}」這個難度等級（Config.checks.grades）")
                elif abs(obj.shift) > shift_max:
                    errors.append(f"{where}：微調 {obj.shift} 超過 ±{shift_max}")
                else:
                    obj.difficulty = grade.dc + obj.shift
            if isinstance(obj, Effect) and any(isinstance(v, str) for v in obj.stats.values()):
                for key, value in list(obj.stats.items()):
                    if not isinstance(value, str):
                        continue
                    if key not in rewards.amounts or value not in reward_at:
                        errors.append(f"{where}：{key} 寫了「{value}」，不是獎勵等級（Config.rewards；只給 {'、'.join(rewards.amounts)}）")
                    else:
                        obj.stats[key] = rewards.amounts[key][reward_at[value]]
            for name in _graded_fields(type(obj)):
                visit(getattr(obj, name), f"{where}.{name}" if where else name)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (BaseModel, dict, list, tuple)):
                    visit(value, f"{where}[{key}]")
        elif isinstance(obj, (list, tuple)):
            for i, value in enumerate(obj):
                if isinstance(value, (BaseModel, dict, list, tuple)):
                    visit(value, f"{where}[{i}]")

    visit(content, "")
    if errors:
        raise ContentError("\n".join(errors[:20]))


# core_content（全部拆包第 62 批：內容照包分；計畫 docs/superpowers/plans/2026-11-06-內容照包分-第62批.md）：各包宣告的內容檔
# （Feature.content）住在 tianxia/features/<包>/content/<rel>，其餘的（config.json、profiles/、核心的事件池）住在 content/<rel>。
# 第 63 批（計畫 docs/superpowers/plans/2026-11-06-內容照包分-第63批.md）：測試內容同一個判準，包宣告了這個 rel 而且有檔的住在 tianxia/features/<包>/tests/content/<rel>，
# 其餘的住在 tests/fixtures/content/<rel>。
REAL_ROOT = Path(__file__).resolve().parent.parent / "content"  # 真實內容（同 LOCAL_DIR 的寫法）
TEST_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "content"  # 測試內容（第 63 批；同 REAL_ROOT，正式機沒有 tests/ 也不礙事：只比路徑）


def _locate(root: Path, only: str | None = None) -> dict[str, Path]:
    """這個根上哪些檔要去包裡找（rel → 真的在哪）。只有真實的 content/ 與測試內容（tests/fixtures/content，第 63 批）才去：其他的根（測試的 tmp 副本、
    序章母本）照舊攤平讀 root/<rel>。不能「根上找不到就去包裡找」：測試內容靠「沒有這個檔就是空的」（沒有 mall.json 就沒有商品），所以測試內容只收包裡真的有的（pack_test_content）。
    宣告了卻沒有檔、content/ 底下還留著同一份都當場報錯：load_content 裡一堆 .exists() 判斷式，不報的話檔案搬丟了會靜靜變成空的。
    only（只載核心加一包，第二級測試用）只有測試內容可以；兩處都有的先照整份查，再濾。"""
    resolved = root.resolve()
    if only is not None and resolved != TEST_ROOT:
        raise ContentError(f"只有測試內容可以只載一包（{only}）：{root} 不是 {TEST_ROOT}")
    if resolved == TEST_ROOT:
        from .core.features import pack_test_content  # noqa: PLC0415  同下面的 pack_content

        tests = pack_test_content()
        for rel, path in tests.items():
            if (root / rel).exists():
                raise ContentError(f"內容檔 {rel} 兩處都有：{path} 與 {root / rel}")
        return tests if only is None else pack_test_content(only)
    if resolved != REAL_ROOT:
        return {}
    from .core.features import pack_content  # noqa: PLC0415  同 check_features：登記的包延後載入（包會 import 核心）

    packs = pack_content()
    for rel, path in packs.items():
        if not path.exists():
            raise ContentError(f"內容檔 {rel} 有包宣告了，但 {path} 沒有這個檔")
        if (root / rel).exists():
            raise ContentError(f"內容檔 {rel} 兩處都有：{path} 與 {root / rel}")
    return packs


def _event_files(root: Path, packs: dict[str, Path]) -> list[Path]:
    """事件檔：root/events/*.json 加上包宣告的 events/*.json，全部照檔名排。content.events 的先後就是事件池抽籤的先後，所以要跨包穿插、
    排起來跟全放在一個資料夾時一樣（比 Path，同以前的 sorted(Path)）。同名不會走到這裡：rel 相同在 _locate、pack_content 就擋了。"""
    files = list((root / "events").glob("*.json")) + [path for rel, path in packs.items() if rel.startswith("events/")]
    return sorted(files, key=lambda path: Path(path.name))


def content_path(rel: str) -> Path:
    """真實內容的這個檔現在在哪（腳本與測試用；rel 是它在 content/ 底下的相對路徑，例 events/sects.json）。"""
    return _locate(REAL_ROOT).get(rel, REAL_ROOT / rel)


def real_files() -> dict[str, Path]:
    """真實內容的每一個 json：rel → 在哪，照 rel 排。掃整份內容的腳本與測試走這裡，不要自己 rglob content/：各包的檔不在那裡，改漏了不會紅、只會少掃。"""
    files = {path.relative_to(REAL_ROOT).as_posix(): path for path in REAL_ROOT.rglob("*.json")}
    files.update(_locate(REAL_ROOT))
    return dict(sorted(files.items()))


def real_event_files() -> list[Path]:
    """真實內容的事件檔，照載入的先後。"""
    return _event_files(REAL_ROOT, _locate(REAL_ROOT))


def load_content(root: Path, profile: str | None = None, *, only: str | None = None) -> Content:
    """profile 給了就把 profiles/<profile>.json 的鍵蓋在 config.json 上（例如 week7 一次打開季曆與 7 天的季），
    不必手改 config.json；覆寫檔只能寫 Config 有的欄位，拼錯在載入當下就報錯。
    only 是測試用（全部拆包第 63 批，只有測試內容可以）：只載核心加這一包，別包的測試內容當空的；這樣的內容不驗（別包的內容不在，一定報錯），validate 碰到它報 RuntimeError。"""
    root = Path(root)
    packs = _locate(root, only)

    def at(rel: str) -> Path:
        return packs.get(rel, root / rel)

    def required(rel: str, empty):
        """這幾格沒有 .exists()：攤平的根少了照舊當場炸；只載一包時別包的檔本來就不在，才當空的。"""
        return empty if only is not None and not at(rel).exists() else _read(at(rel))

    events: dict[str, Event] = {}
    for path in _event_files(root, packs):
        for raw in _read(path):
            event = _build(Event, raw)
            if event.id in events:
                raise ContentError(f"事件 id 重複：{event.id}（{path.name}）")
            stamp_tier(event)
            events[event.id] = event
    timetable_events = [_build(TimetableEvent, raw) for raw in _read(at("timetable.json"))] if at("timetable.json").exists() else []
    config = _config(root, profile)
    if config.season21:  # 21 天季自己一份時刻表（正式季整合設計 1.2 給開發 1）：驗證之前套上，週末與 14 天不經過這裡
        timetable_events = season21_timetable(timetable_events, config.season_segments)
    content = Content(
        config=config,
        scenario=Scenario(**_read(at("scenario.json"))),
        locations=_index(Location, _read(at("locations.json"))),
        skills=_index(SkillDef, _read(at("skills.json"))),
        insights=_index(InsightDef, _read(at("insights.json"))),
        traits=_traits(at("traits.json")),
        trait_lines=_trait_lines(at("trait_lines.json")),
        materials=_index(Material, _read(at("materials.json"))),
        craft_names=CraftNames(**_read(at("craft_names.json"))),
        combat_lines=_combat_lines(at("combat_lines.json")),
        check_voice=_check_voice(at("check_voice.json")),
        front_lines=_front_lines(at("front_lines.json")),
        banned_names=_read(at("banned_names.json")),
        sects=_index(Sect, required("sects.json", [])),
        characters=_index(CharacterDef, _read(at("characters.json"))
                          + (_read(at("hire.json")) if at("hire.json").exists() else [])),  # 一般 NPC 同伴（features/hire）
        squads=_index(Squad, _read(at("squads.json"))),
        battles=_index(BattleDef, _read(at("battles.json"))) if at("battles.json").exists() else {},
        road_sights=_index(RoadSight, required("road_sights.json", [])),
        timetable=[e for e in timetable_events if not e.mandate_only],
        mandate_timetable=[e for e in timetable_events if e.mandate_only],  # 天命之爭（玉璽二）：只有蓋了章的季看得到（timetable.events）
        foreshadows=_foreshadows(at("foreshadows.json")),
        orders=_orders(at("orders.json")),
        promotions=[_build(PromotionDef, raw) for raw in _read(at("promotions.json"))]
        if at("promotions.json").exists() else [],
        opportunities=[_build(OppDef, raw) for raw in _read(at("opportunities.json"))]
        if at("opportunities.json").exists() else [],
        followers={raw["id"]: _build(FollowerDef, raw) for raw in _read(at("followers.json"))}
        if at("followers.json").exists() else {},
        preset_recipes=[_build(PresetRecipe, raw) for raw in _read(at("preset_recipes.json"))]
        if at("preset_recipes.json").exists() else [],
        secret_recipes=[_build(SecretRecipe, raw) for raw in _read(at("secret_recipes.json"))]
        if at("secret_recipes.json").exists() else [],
        forge_secrets=_forge_secrets(at("forge_secrets.json")),
        tier4_named=_index(Tier4Named, _read(at("tier4_named.json"))) if at("tier4_named.json").exists() else {},
        shop_lines=_read(at("shop_lines.json")) if at("shop_lines.json").exists() else {},
        create_forms=CreateForms(**_read(at("create_forms.json"))) if at("create_forms.json").exists() else CreateForms(),
        banned_words=_read(at("banned_words.json")) if at("banned_words.json").exists() else [],
        mingtie=MingtieContent(**_read(at("mingtie.json"))) if at("mingtie.json").exists() else MingtieContent(),
        arena_crowd=_read(at("arena_crowd.json")) if at("arena_crowd.json").exists() else {},
        xingshi_lines=_read(at("xingshi_lines.json")) if at("xingshi_lines.json").exists() else {},
        seal=_shards(at("seal.json")),
        mall=_index(MallItem, _read(at("mall.json"))) if at("mall.json").exists() else {},  # 商城的商品（joy 寫）
        looks=_index(Look, _read(at("looks.json"))) if at("looks.json").exists() else {},  # 擂台形象（功能包 looks）
        relations=[_build(RelationDef, raw) for raw in _read(at("relations.json"))] if at("relations.json").exists() else [],
        heroines={cid: _build(HeroineDef, raw) for cid, raw in _read(at("heroines.json")).items() if not cid.startswith("_")}
        if at("heroines.json").exists() else {},  # 女子與隱線（features/heroines）
        personas={cid: [_build(PersonaAxis, raw) for raw in rows] for cid, rows in _read(at("personas.json")).items() if not cid.startswith("_")}
        if at("personas.json").exists() else {},  # 人物性子（features/persona）
        itineraries=[_build(Itinerary, raw) for raw in _read(at("itineraries.json"))] if at("itineraries.json").exists() else [],
        mark_rules=[_build(MarkRule, raw) for raw in _read(at("mark_rules.json"))] if at("mark_rules.json").exists() else [],
        outing_lines=_read(at("outing_lines.json")) if at("outing_lines.json").exists() else {},  # 探索一顆的段落（減法季批 2）
        verdicts=_read(at("verdicts.json")) if at("verdicts.json").exists() else {},  # 人物評曰的固定句（減法季批 7b-2）
        storylines=_index(StoryDef, _read(at("storylines.json"))) if at("storylines.json").exists() else {},  # 一條線（特殊事件）
        figures=_index(FigureDef, _read(at("figures.json"))) if at("figures.json").exists() else {},
        duels=_index(DuelBoss, _read(at("duels.json"))) if at("duels.json").exists() else {},
        gear=_gear(at("gear.json")),
        insight_scenes=_index(InsightScene, _read(at("insight_scenes.json")))
        if at("insight_scenes.json").exists() else {},
        events=events,
        map=MapLayout(**_read(at("map.json"))),
        tutorial=Tutorial(**required("tutorial.json", {})),
        opening=Opening(**_read(at("opening.json"))) if at("opening.json").exists() else None,  # 開局第一分鐘（減法季批 7）
        hints=Hints(**_read(at("hints.json"))) if at("hints.json").exists() else Hints(),
        art=ArtBook(**_read(at("art.json"))) if at("art.json").exists() else ArtBook(),  # 圖的分類表（減法季批 8）
    )
    content.config.admins = _with_local_admins(content.config.admins)
    _fill_story_lines(content)
    _load_attributes(content, at("attributes.json"))
    if at("attributes_v2.json").exists():  # 五項屬性（屬性與跨季架構 v2 第三節）：顯示名照季讀（attrset.names），不蓋 stat_names
        content.attributes_v2 = [_build(StatDef, raw) for raw in _read(at("attributes_v2.json"))]
    resolve_grades(content)
    if only is None:
        validate(content)
    else:
        content._only_pack = only
    _scale_marks(content, content.config.mark_threshold_scale)
    return content


def _segment_slot(real7: RealDay | None, segments: list[int]) -> RealSlot | None:
    """7 天濃縮季的第幾天、幾點換成季曆的（第幾段, 段裡第幾天, 幾點）：段 [2, 2, 3] 時第 4 天是第 2 段的第 1 天（weekday 1）。"""
    if real7 is None:
        return None
    start = 0
    for week, length in enumerate(segments, 1):
        if real7.day <= start + length:
            return RealSlot(week=week, weekday=real7.day - start - 1, hour=real7.hour)
        start += length
    return None  # 超過段的和（content.validate 擋）


def season21_timetable(events: list[TimetableEvent], segments: list[int] | None = None) -> list[TimetableEvent]:
    """21 天季的時刻表（Config.season21）：每一件照 real 換掉時刻——一般大事 day＝星期＋鐘點÷24（週二 12:00 是 1.5）、決戰與天命之爭
    寫 weekday、hour、季末只換週（季末的時刻照錨點算，timetable.finale_default）——再照時刻排（同一刻照檔案順序；季末排在那一週最後），
    畫面上的時刻表照時間排（正式季整合設計 1.2 給開發 4）。沒寫 real 的照原樣（content.validate 擋）。
    7 天濃縮季（segments 是 Config.season_segments）照 real7（第幾天、幾點）換成段裡的時刻，其餘一樣。"""
    moved = []
    for event in events:
        slot = _segment_slot(event.real7, segments) if segments else event.real
        if slot is None:
            moved.append(event)
        elif event.kind == "showdown":
            moved.append(event.model_copy(update={"week": slot.week, "weekday": slot.weekday, "hour": slot.hour}))
        elif event.kind == "finale":
            moved.append(event.model_copy(update={"week": slot.week}))
        else:
            moved.append(event.model_copy(update={"week": slot.week, "day": slot.weekday + slot.hour / 24}))

    def at(pair: tuple[int, TimetableEvent]) -> tuple[int, float, int]:
        order, event = pair
        if event.kind == "finale":
            return event.week, 7.0, order
        if event.kind == "showdown":
            weekday = 3 if event.weekday is None else event.weekday  # 同 timetable.SHOWDOWN_WEEKDAY、SHOWDOWN_HOUR
            return event.week, weekday + (20 if event.hour is None else event.hour) / 24, order
        return event.week, event.day, order

    return [event for _, event in sorted(enumerate(moved), key=at)]


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
    """啟動時跟資料庫路徑一起印的那一行：用的是哪一份設定、打開了什麼。設錯時一眼看得出來。
    測試期間一鍵補滿體力（Config.beta_free_refill）開著才在整行後面多一句；沒開的設定印的一個字都不變。"""
    cfg = content.config
    if profile is None:
        line = "設定：預設"
    else:
        switch = "開啟" if cfg.season_one else "關閉"
        line = f"設定：{profile}（第一季濃縮版規則{switch}、季長 {cfg.season_days:g} 天、人數上限 {cfg.server_max_players}）"
    return line + "　測試期一鍵補滿體力：開" if cfg.beta_free_refill else line


def _scale_marks(obj, scale: float) -> None:
    """地方痕跡的門檻照伺服器人數換算（探索的多人與LLM玩法 §8.2）：每個 Condition 的 marks_min／marks_max
    乘上 scale、無條件進位。在載入時做一次，條件判定（rules.check_condition）就不必知道設定。"""
    if scale == 1:
        return
    if isinstance(obj, Condition):
        for limits in (obj.marks_min, obj.marks_max):
            for key, value in limits.items():
                limits[key] = math.ceil(value * scale)
    if isinstance(obj, MarkRule):  # 痕跡過門檻（減法季批 4）同一個換算
        obj.threshold = math.ceil(obj.threshold * scale)
    if isinstance(obj, MarkText):
        obj.min = math.ceil(obj.min * scale)
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
STEP_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")  # 序章步驟文字裡要換掉的字（{武學}、{意境}、{心得}）
LORE = "lore"  # 博聞（team.LORE）：只靠升級的點數增加，任何獎勵都不能給、不能扣（validate 的 no_lore）
FREE_TEXT_REWARDS = ("silver", "fame", "good", "xinde", "str", "agi", "con", "wis")  # 隨口應對的獎勵不能超過檢定選項的這幾項（博聞不在內：一律不能給）
# 隨口應對分岔（減法季整合設計 5.1、5.9；check_outcomes）：一則 2～4 種後果（最後一種是 fallback），另外最多一種作惡的
OUTCOMES_MIN, OUTCOMES_MAX = 2, 4
OUTCOME_CHECK_STATS = ("str", "agi", "con", "wis", "lore")  # 後果的檢定（含 best_of 的每一項）看得了哪幾項
OUTCOME_EFFECT_FIELDS = {"text", "stats", "stamina", "marks", "contribution"}  # 後果的效果只准寫這幾樣（公開的只有後果與痕跡，5.1）
OUTCOME_DIGITS = re.compile(r"[0-9０-９]")  # 後果的敘事不寫阿拉伯數字（數字只能是引擎的）


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


def _gear(path: Path) -> GearBook:
    """content/gear.json（裝備三）：寶物表、名駒、名將贈禮、名將本命兵器（打造第三批）。沒有這個檔就是空的（測試內容）：寶物沒有來源、名將不送禮。
    只能有 treasures、steeds、gifts、signature_arms 四個鍵（拼錯在載入當下就報錯）。"""
    if not path.exists():
        return GearBook()
    raw = _read(path)
    extra = set(raw) - {"treasures", "steeds", "gifts", "signature_arms"}
    if extra:
        raise ContentError(f"content/gear.json 只能有 treasures、steeds、gifts、signature_arms：{sorted(extra)}")
    return GearBook(
        treasures=_index(TreasureDef, raw.get("treasures", [])),
        steeds=_index(SteedDef, raw.get("steeds", [])),
        gifts=[_build(GiftDef, item) for item in raw.get("gifts", [])],
        signature_arms=[_build(SignatureArmDef, item) for item in raw.get("signature_arms", [])],
    )


def _forge_secrets(path: Path) -> dict[str, ForgeSecret]:
    """content/forge_secrets.json（打造隱藏配方）：一條一筆的清單，照 id 收；沒有這個檔就是空的（測試內容）。id 重複在這裡就擋。"""
    if not path.exists():
        return {}
    out: dict[str, ForgeSecret] = {}
    for raw in _read(path):
        recipe = _build(ForgeSecret, raw)
        if recipe.id in out:
            raise ContentError(f"content/forge_secrets.json：id {recipe.id} 重複")
        out[recipe.id] = recipe
    return out


def _shards(path: Path) -> dict[str, ShardDef]:
    """content/seal.json（玉璽碎片）：一片一筆的清單，照 id 收；沒有這個檔就是空的（測試內容：碎片關著）。id 重複在這裡就擋。"""
    if not path.exists():
        return {}
    out: dict[str, ShardDef] = {}
    for raw in _read(path):
        shard = _build(ShardDef, raw)
        if shard.id in out:
            raise ContentError(f"content/seal.json：id {shard.id} 重複")
        out[shard.id] = shard
    return out


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

    探索不再撿素材（武學與成長計畫一：探索改悟意境），地點能給素材的只剩路邊採集（移動包 features/travel/road_actions.py 的 gather）：
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
            picked = [m.id for m in first_tier if m.attribute in kinds]  # 跟移動包 features/travel/road_actions.py 的 gather 一樣：挑不到就退回全部一階
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
    # 四階（正式季整合 4.5）只從幾條路來，這一批只有鐵匠鋪的三換四：素材四階與升階都開著時，同屬性有三階的四階拿得到
    if c.config.four_tiers.enabled and c.config.economy.upgrade:
        tier3 = {m.attribute for m in c.materials.values() if m.tier == 3}
        reachable |= {m.id for m in c.materials.values() if m.tier == 4 and m.attribute in tier3}
    if c.config.four_tiers.enabled and c.config.checkin.enabled:  # 21 天季的簽到（第 7 批）：第 6、13、20 天自己挑一種四階
        reachable |= {m.id for m in c.materials.values() if m.tier == 4}
    return reachable


def check_insight_scenes(c: Content, need) -> None:
    """有所感的場景（content/insight_scenes.json，悟意境設計 3.1、4.1）。沒有這個檔就不檢查（探索照舊直接悟）。
    - 每段三到四個做法、屬性各不相同；hints 要是它自己做法裡有的屬性；locations 要是存在的地點、tags 要至少對得上一個地點。
    - 用得到這段場景的每一個地點：至少一個做法是選得對的（做法屬性在這裡悟得到的意境裡），hints 也要指得到這裡悟得到的
      （寫了 hints 才查；通用場景可以不寫）——河邊的場景用在只悟得到火的地方，看懂場景的人反而選錯。
    - 探索悟得到意境的每一個地點（序章的草廬除外）都要有場景：不然那裡落在悟意境那一支時沒有卡可出。
    - 文字只能用繁體中文、不能寫數字或百分比（不攤成算，Q4）。"""
    from .insights import explore_gives, pool_attributes, scenes_for  # noqa: PLC0415  insights → state → models，延後免得循環

    scenes = c.insight_scenes
    if not scenes:
        return
    all_tags = {tag for loc in c.locations.values() for tag in loc.tags}

    check_text = functools.partial(_check_line, need)

    for scene in scenes.values():
        where = f"有所感 {scene.id}"
        attrs = [m.attribute for m in scene.methods]
        need(3 <= len(attrs) <= 4, f"{where}：做法要三到四個（現在 {len(attrs)} 個）")
        need(len(set(attrs)) == len(attrs), f"{where}：做法的屬性不能重複 {attrs}")
        need(set(scene.hints) <= set(attrs), f"{where}：hints {scene.hints} 要是它自己做法裡有的屬性")
        for loc_id in scene.locations:
            need(loc_id in c.locations, f"{where}：未知的地點 {loc_id}")
        for tag in scene.tags:
            need(tag in all_tags, f"{where}：沒有任何地點有標籤「{tag}」")
        for text, label in [(scene.title, "標題"), (scene.text.replace("{痕跡}", ""), "場景"), *((m.text, "做法") for m in scene.methods)]:
            check_text(f"{where}的{label}", text)
        need(not scene.prologue or not (scene.tags or scene.locations), f"{where}：序章的場景只給草廬用，不寫 tags、locations")
        need(scene.prologue or not scene.flags_add, f"{where}：flags_add 只給序章的場景用")
    if all(scene.prologue for scene in scenes.values()):
        return  # 只有序章草廬那一段：草廬外探索照舊直接悟，不要求每處都有場景
    hut = c.tutorial.location
    for loc in c.locations.values():
        if not explore_gives(loc, c) or loc.prologue_only or loc.id == hut:
            continue
        options = scenes_for(loc, c)
        need(bool(options), f"地點 {loc.id}：探索悟得到意境，卻沒有一段有所感的場景（insight_scenes.json 的 locations、tags 或通用場景）")
        pool = pool_attributes(loc, c)
        for scene in options:
            where = f"有所感 {scene.id}（用在 {loc.id}）"
            need(any(m.attribute in pool for m in scene.methods), f"{where}：沒有一個做法選得對（這裡悟得到的屬性 {sorted(pool)}）")
            need(not scene.hints or bool(set(scene.hints) & pool), f"{where}：線索 {scene.hints} 指不到這裡悟得到的 {sorted(pool)}")


def check_insight_strong(c: Content, need) -> None:
    """每個地點最濃的意境（意境提示設計第一節）：
    - 寫了的話，要是這個地點探索真的悟得到的；那一種意境要寫 strong_line（悟到時多的那一句）。
    - 開關開著時，探索悟得到意境的每一個地點（序章草廬除外）都要寫。
    - 有所感的場景要對得上：這裡用得到的每一段都要有最濃那一種屬性的做法；寫了線索的場景裡，至少一段指得到它
      （一段都沒寫線索的不查）——不然照著場景描寫選的人永遠選不到最濃的。
    正式內容的分布（每一種至少 5 處、五個大區都有）鎖在 tests/season/test_real_content.py。"""
    from .insights import explore_gives, scenes_for  # noqa: PLC0415  insights → state → models，延後免得循環

    hut = c.tutorial.location
    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        gives = explore_gives(loc, c)
        if loc.insight_strong is None:
            need(not (c.config.insight_strong.enabled and gives and not loc.prologue_only and loc.id != hut),
                 f"{where}：意境提示開著，探索悟得到意境的地點都要寫 insight_strong")
            continue
        need(loc.insight_strong in gives, f"{where}：最濃的意境 {loc.insight_strong} 要是這裡悟得到的 {gives}")
        d = c.insights.get(loc.insight_strong)
        need(d is not None and bool(d.strong_line), f"{where}：最濃的意境 {loc.insight_strong} 要寫 strong_line（悟到時多的那一句）")
        if d is None or loc.insight_strong not in gives:
            continue
        scenes = scenes_for(loc, c)
        for scene in scenes:
            need(any(m.attribute == d.attribute for m in scene.methods),
                 f"有所感 {scene.id}（用在 {loc.id}）：沒有最濃那一種（{d.attribute}）的做法")
        hinted = [scene for scene in scenes if scene.hints]
        need(not hinted or any(d.attribute in scene.hints for scene in hinted),
             f"{where}：有所感的場景沒有一段線索指得到最濃的「{d.name}」（{d.attribute}）")


def check_faction_choices(c: Content, need) -> None:
    """選項照陣營分邊（Condition.factions／factions_none，企劃者 2026-10-08「加入黃巾軍了，探索還一堆打黃巾的任務」）之後，
    每一種身分（散人與每個陣營）碰得到的事件，至少要剩一個選項看得見——不然那個人會卡在一則沒有選項的事件上。
    只看陣營這一項：其他條件（銀兩、旗標）本來就由寫事件的人負責留一條退路。"""
    def allows(cond: Condition, faction: str | None) -> bool:
        if cond.factions and faction not in cond.factions:
            return False
        return faction is None or faction not in cond.factions_none

    for event in c.events.values():
        for faction in [None, *(f.id for f in c.scenario.factions)]:
            if not allows(event.condition, faction):
                continue
            need(
                any(allows(choice.condition, faction) for choice in event.choices),
                f"事件 {event.id}：{faction or '散人'}碰得到這則事件，選項卻全被陣營條件擋掉了",
            )


def check_check_voice(c: Content, need) -> None:
    """檢定選項括號裡的那一句（content/check_voice.json，joy 寫的；取代 S1 的 check_lines.json，驗證照它的標準）：
    至少一檔、照 min_gap 由高到低排而且不重複；每一檔都要說得出每一種有人檢定的屬性（沒寫的屬性用 "default"）；
    鍵只能是屬性或 default；每一句都不能是空的、只用繁體中文、不能寫阿拉伯數字（半形、全形）或百分號（選項上不攤出成功率）。
    熟練加成併進括號的那一句（config.practice_bonus 的 line）照同樣的文字規矩。"""
    bands = c.check_voice.bands

    check_text = functools.partial(_check_line, need, numbers="，成功率不攤在選項上")

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
    不能多出不認得的段；各陣營自己的說法（by_side）只能寫存在的陣營與段、可以只寫其中幾段；
    sides 的陣營名也要是存在的陣營。每一句、每個陣營名都不能是空的、只用繁體中文、不能寫數字或百分比（畫面上只有一句話、不攤出數字）。"""
    lines = c.front_lines
    factions = {f.id for f in c.scenario.factions}

    check_text = functools.partial(_check_line, need, numbers="，戰況變化只用一句話說")

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


# 擂台場邊事件的固定句（原本的 check_arena_crowd）搬進單挑包：tianxia/features/bout/arena_crowd.py 的 check_content（全部拆包第 12 批）


# 〈天下形勢〉句型（content/xingshi_lines.json）的驗證（原本的 check_xingshi_lines）搬進地盤包的 check_content：tianxia/features/territory_acts/xingshi.py 的 check_lines（全部拆包第 46 批）


# 減法季探索一顆的「旅人」（整合設計 4.1）：野外的事件拍偏向救助旅人那一類（從現有的野外事件挑合適的標上，PM 2026-10-25 第 7 件）。
# 探索表與段落句子的兩個驗證（原本的 check_explore_one、check_outing_lines）搬進探索包的 check_content（主動搬六包第 3＋4 批：
# 核心不 import 包）；這兩個字留在核心——tests/core/test_jianfa_switch.py 從這裡拿、換掉 TRAVELER_MIN，包的驗證照舊讀這兩個模組屬性。
TRAVELER_TAG = "旅人"  # 同探索包的 explore_one.TRAVELER（核心不 import 包：抄一份字，包的測試守兩邊一樣）
TRAVELER_MIN = 3  # 野類地點抽得到的旅人事件至少幾則（PM 2026-10-25 第 7 件）


ART_PATH = re.compile(r"^(places|figures|events)/[a-z0-9_]+$")  # web/img/ 底下的路徑：子資料夾／鍵，不含副檔名
STORY_ART = re.compile(r"^stories/[a-z0-9_]+$")  # 一條線、段落卡與結局的專屬圖（web/img/stories/<鍵>.webp；頓悟是 dunwu_*）


def event_endings(ev: Event) -> list[Effect]:
    """一則事件了結時真的會套的那幾個效果：每個選項的成套（有檢定或開打的再加敗套）、隨口應對的成敗或分岔每一種後果的成敗。"""
    out = []
    for ch in ev.choices:
        out += [ch.effect] + ([ch.fail_effect] if ch.check is not None or ch.combat is not None else [])
    free = ev.free_text
    if free is not None:
        out += [e for o in free.outcomes for e in [o.effect] + ([o.fail_effect] if o.kind in ("check", "combat") else [])]
        if not free.outcomes_only:
            out += [free.effect, free.fail_effect]
    return out


def _fill_story_lines(c: Content) -> None:
    """一條線的段落事件（含串下去的）上，效果的 story 沒寫 line 的補上那一條線的 id（一則事件只准屬於一條線，check_storylines 驗）。"""
    for line in c.storylines.values():
        for eid in stage_events(c, line):
            for eff in event_effects(c.events[eid]):
                if eff.story is not None and not eff.story.line:
                    eff.story.line = line.id


def check_storylines(c: Content, need) -> None:
    """一條線（content/storylines.json，特殊事件設計稿；tianxia/storyline.py）：段與結局的 id 不重複、往哪裡都指得到、
    段落事件只能接在這條線上（actions 寫 []、只屬於一條線），fight 寫得出打哪一路、打贏打輸往哪裡，task 寫得出等什麼。
    效果的 story 只准寫在段落事件上，line 要是那一條線。"""
    owner: dict[str, str] = {}
    for line in c.storylines.values():
        lw = f"一條線 {line.id}"
        ids = [st.id for st in line.stages] + [e.id for e in line.endings]
        need(len(ids) == len(set(ids)), f"{lw}：段與結局的 id 有重複")
        known_ids = set(ids)
        for img in [line.image] + [e.image for e in line.endings] + [st.image for st in line.stages]:
            need(img is None or bool(STORY_ART.match(img)), f"{lw}：image「{img}」要寫成 stories/<鍵>")
        if line.start is not None:
            check_story_place(c, need, f"{lw} 的開頭", line.start.where)
        need(any(not e.failed for e in line.endings), f"{lw}：至少要有一個不是失敗的結局")
        if line.chapter is not None:
            check_chapter(c, need, line)
        for end in line.endings:
            need(end.effect.story is None, f"{lw} 結局 {end.id}：結局的效果不能再寫 story")
            need(bool(end.annal.strip()), f"{lw} 結局 {end.id}：annal（寫進傳的那一句）是空的")

        def target(where: str, go: str | None) -> None:
            need(go is None or go in known_ids, f"{where}：往「{go}」指不到這條線的段或結局")

        for st in line.stages:
            sw = f"{lw} 段 {st.id}"
            check_story_place(c, need, sw, st.where)
            for name in ("next", "late", "win", "lose"):
                target(f"{sw} 的 {name}", getattr(st, name))
            for route in st.routes:
                target(f"{sw} 的 routes", route.go)
            need(st.days is None or st.late is not None, f"{sw}：寫了期限 days 就要寫過期往哪裡（late）")
            routed = st.next is not None or bool(st.routes)
            if st.kind == "event":
                ev = c.events.get(st.event or "")
                need(ev is not None, f"{sw}：事件「{st.event}」不存在")
                if ev is None:
                    continue
                for eid, from_stage in stage_events(c, line).items():
                    if from_stage != st.id:
                        continue
                    chained = c.events[eid]
                    need(chained.actions == [], f"{sw}：事件 {eid} 的 actions 要寫 []（只由這條線端出來）")
                    need(owner.setdefault(eid, line.id) == line.id, f"{sw}：事件 {eid} 已經是一條線 {owner[eid]} 的段落")
                    for eff in event_effects(chained):
                        if eff.story is not None:
                            need(eff.story.line == line.id, f"{sw}：事件 {eid} 的 story.line 要是 {line.id}")
                            target(f"{sw} 事件 {eid} 的 story.go", eff.story.go)
                # 選項都寫了往哪裡（或事件串到下一則）才可以不寫 routes／next
                need(routed or all((eff.story is not None and eff.story.go) or eff.next_event for eff in event_endings(ev)),
                     f"{sw}：有選項沒寫 story.go，這一段又沒寫 next 或 routes（走完不知道往哪裡）")
            elif st.kind == "quiz":
                need(bool(st.questions), f"{sw}：quiz 要寫 questions")
                need(routed, f"{sw}：quiz 要寫 next 或 routes")
            elif st.kind == "fight":
                need(st.squad in c.squads, f"{sw}：打的那一路「{st.squad}」不在 squads")
                need(st.win is not None and st.lose is not None, f"{sw}：fight 要寫 win 與 lose")
            else:
                need(st.until is not None or bool(st.task), f"{sw}：task 要寫 until（條件）或 task（登記的判斷名）")
                need(routed, f"{sw}：task 要寫 next 或 routes")
    for ev in c.events.values():
        if ev.id in owner:
            continue
        need(all(eff.story is None for eff in event_effects(ev)), f"事件 {ev.id}：story 只能寫在一條線的段落事件上")


def check_chapter(c: Content, need, line) -> None:
    """章回主線的一回（tianxia/chapters.py）：kind 寫「章回」、陣營在劇本裡、beat／after_beat 是時刻表的大事、after 是同一方的別回，
    最後一段是 wait（task chapter_beat），有 missed 結局。"""
    from . import chapters  # noqa: PLC0415

    lw, spec = f"章回 {line.id}", line.chapter
    timetable_ids = {e.id for e in c.timetable}
    need(line.kind == chapters.KIND, f"{lw}：kind 要寫「{chapters.KIND}」")
    need(line.start is None, f"{lw}：章回由時刻表開，不寫 start")
    need(spec.side in {f.id for f in c.scenario.factions}, f"{lw}：陣營「{spec.side}」不在劇本裡")
    need(spec.beat in timetable_ids, f"{lw}：beat「{spec.beat}」不是時刻表的大事")
    need(spec.after_beat is None or spec.after_beat in timetable_ids, f"{lw}：after_beat「{spec.after_beat}」不是時刻表的大事")
    for before in spec.after:
        prev = c.storylines.get(before)
        need(prev is not None and prev.chapter is not None and prev.chapter.side == spec.side, f"{lw}：after「{before}」不是同一方的章回")
    last = line.stages[-1]
    need(last.id == chapters.WAIT and last.kind == "task" and last.task == chapters.TASK,
         f"{lw}：最後一段要是 {chapters.WAIT}（task {chapters.TASK}）")
    need(all(st.id != chapters.WAIT for st in line.stages[:-1]), f"{lw}：{chapters.WAIT} 只能是最後一段")
    need(line.ending(chapters.MISSED) is not None, f"{lw}：要有 {chapters.MISSED} 結局（大事結算了還沒做成）")


def check_story_place(c: Content, need, where: str, place) -> None:
    for lid in place.locations:
        need(lid in c.locations, f"{where}：地點「{lid}」不存在")
    regions = {r.id for r in c.map.regions}
    for rid in place.regions:
        need(rid in regions, f"{where}：大區「{rid}」不存在")


def check_art(c: Content, need) -> None:
    """圖的分類表與 image 欄位（減法季批 8 圖像版）：事件的 image 只能是 art.json 的 events 有的類型鍵；地點與人物的 image 是
    web/img/ 底下的路徑（places/…、figures/…）。圖檔在不在這裡不管（伺服器看，沒檔案就不給圖）。"""
    for key, name in c.art.events.items():
        need(bool(re.fullmatch(r"[a-z0-9_]+", key)), f"art.events 的類型鍵「{key}」只能是小寫英數與底線（圖檔名）")
        need(bool(name.strip()), f"art.events.{key} 的名字是空的")
    for ev in c.events.values():
        if ev.image is not None:
            need(ev.image in c.art.events, f"事件 {ev.id} 的 image「{ev.image}」不在 art.json 的 events 類型表裡")
    for loc in c.locations.values():
        if loc.image is not None:
            need(bool(ART_PATH.match(loc.image)), f"地點 {loc.id} 的 image「{loc.image}」要寫成 places/<鍵> 這種路徑（不含副檔名）")
    for ch in c.characters.values():
        if ch.image is not None:
            need(bool(ART_PATH.match(ch.image)), f"人物 {ch.id} 的 image「{ch.image}」要寫成 figures/<鍵> 這種路徑（不含副檔名）")


def check_features(c: Content, need) -> None:
    """功能包自己的內容驗證（FEATURES 的 check_content，照清單的順序；開發規範手冊 3.6）：關著的包照驗（檔案寫壞了早點知道）。"""
    from .core import features  # noqa: PLC0415  登記的包延後載入（包會 import 核心）

    features.check_content(c, need)


def check_shop_lines(c: Content, need) -> None:
    """店面上掌櫃的話（content/shop_lines.json，店面獨立介面設計 1.4；Joy 直接改字）：寫了的只能是認得的店與情況，每一句不能空、
    只用繁體中文、不寫數字；店面開關開著時，開門的店那一組每一種情況都要有句子：鐵匠鋪（兵器或防具開著）、馬市（坐騎開著）、
    懸賞榜（開著而且劇本有陣營）。"""
    from .shopview import SITUATIONS  # noqa: PLC0415  shopview → smithing → …：在函式裡 import

    for shop, pool in c.shop_lines.items():
        need(shop in SITUATIONS, f"shop_lines：不認得的店 {shop}")
        for key, lines in pool.items():
            need(key in SITUATIONS.get(shop, ()), f"shop_lines.{shop}：不認得的情況 {key}")
            for text in lines:
                _check_line(need, f"shop_lines.{shop}.{key}", text)
    opened = {
        "smith": c.config.weapons.enabled or c.config.armor.enabled,
        "market": c.config.mounts.enabled,
        "board": c.config.bounties.enabled and bool(c.scenario.factions),
        "donate": c.config.economy.donate and bool(c.scenario.factions),  # 大本營的軍需帳（素材與經濟 B6）
        "dadian": c.config.silver_outlets.enabled,  # 打點（21 天季的銀兩出口）
        "tavern": c.config.tavern.enabled and any("酒肆" in loc.tags for loc in c.locations.values()),  # 酒肆（企劃者 2026-10-18）
    }
    switched = {"sell": c.config.economy.sell, "upgrade": c.config.economy.upgrade,  # 素材與經濟：收購、升階關著時不必有那一句
                "rules": c.config.four_tiers.enabled,  # 素材四階關著時鐵匠不講神器的規矩（正式季整合 5.10）
                "have_divine": c.config.forge_secrets.rotation,  # 神器輪替關著時不會擋「已經有這一件神器」（FB-403）
                "black_market": c.config.economy.sell and c.config.renown.titles and c.config.renown.black_market}  # 名聲 5.2
    for shop, on in opened.items():
        if c.config.shop_screens and on:
            for key in SITUATIONS[shop]:
                if shop == "smith" and not switched.get(key, True):
                    continue
                need(bool(c.shop_lines.get(shop, {}).get(key)), f"shop_lines.{shop} 缺少情況 {key}（這間店開著時每一種情況至少一句）")


def _condition_flags(c: Content) -> set[str]:
    """劇本與事件的條件（含 any_of 底下的）讀到的世界旗標（world_flags_all／world_flags_none）。"""
    flags: set[str] = set()

    def walk(obj) -> None:
        if isinstance(obj, Condition):
            flags.update(obj.world_flags_all)
            flags.update(obj.world_flags_none)
        if isinstance(obj, BaseModel):
            for name in type(obj).model_fields:
                walk(getattr(obj, name))
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            for item in obj.values():
                walk(item)

    walk(c.scenario)
    walk(list(c.events.values()))
    return flags


def check_companions(c: Content, need) -> None:
    """歷史武將同行（Config.companions）：標了 recruitable 的人物不能是任何大勢人物（人物表寫了 character 的那十六位帶不走），
    要能深度對話（招募鈕照 Game._figures_here），side 寫的要是劇本的陣營。"""
    big = {fig.character for fig in c.figures.values() if fig.character}
    faction_ids = {f.id for f in c.scenario.factions}
    for cid, ch in c.characters.items():
        if not ch.recruitable:
            continue
        where = f"人物 {cid}"
        need(cid not in big, f"{where}：大勢人物不能標 recruitable（人物表寫了他）")
        need(ch.deep_interaction, f"{where}：標了 recruitable 要能深度對話（deep_interaction）")
        need(ch.side is None or ch.side in faction_ids, f"{where}：side {ch.side} 不是劇本的陣營")


def check_figures(c: Content, need, known, front_ids: list[str]) -> None:
    """大勢人物（content/figures.json，計畫 T4）：對話人物、陣營、戰線（戰線 id，不是大區）、地點、代表本人的隊伍都存在，
    隊伍跟人物同一個陣營；一個對話人物只能是一位大勢人物，而且人物的 id 就是對話人物的 id（伏筆用對話人物的 id 讀人物的
    狀態）；接位的人存在、同一個陣營、接位鏈不繞回來；名字只用繁體中文。"""
    faction_ids = [f.id for f in c.scenario.factions]
    owner: dict[str, str] = {}  # 對話人物 → 第一個用它的大勢人物
    week7 = _week7(c)
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
        need(  # 21 天季照天數出兵（正式季整合設計 1.2 給開發 5）：第 1 週以後才出兵的人物要另寫天數
            not c.config.season21 or week7 or fig.active_from_week <= 1 or fig.active_from_day is not None,
            f"{where}：21 天季照天數出兵，第 {fig.active_from_week} 週起的人物要寫 active_from_day",
        )
        need(  # 7 天濃縮季同上，寫 7 天的那一份
            not week7 or fig.active_from_week <= 1 or fig.active_from_day7 is not None,
            f"{where}：7 天濃縮季照天數出兵，第 {fig.active_from_week} 週起的人物要寫 active_from_day7",
        )
        need(
            fig.active_from_day7 is None or fig.active_from_day7 < 7,
            f"{where}：active_from_day7（{fig.active_from_day7:g}）超出 7 天" if fig.active_from_day7 is not None else "",
        )
        need(to_traditional(fig.name) == fig.name, f"{where}：名字只能用繁體中文（{fig.name}）")
        check_stances(c, need, where, fig)
        check_errands(c, need, where, fig)
        if fig.out_flag is not None:  # 丙 (c)：退場時記的世界旗標要有人讀（劇本或事件的條件），打錯字才抓得到
            need(fig.out_flag in _condition_flags(c), f"{where}：out_flag {fig.out_flag} 沒有任何劇本或事件的條件讀它")
        meet = c.characters.get(fig.character) if fig.character is not None else None
        if meet is not None and fig.start_status == "active":  # 挑戰每季都有設計 3.3：14 天的季沒人退場時求見的地方跟現在一樣
            spot = meet.talk_at or meet.recruit_at
            need(spot == fig.location,
                 f"{where}：開季在場、有對話人物的人物，開季地點（{fig.location}）要等於 {fig.character} 的 talk_at（{spot}）")
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


STANCE_MAX = 3  # 一位人物最多幾個心意（整合設計 5.4「2～3 個」）


def check_stances(c: Content, need, where: str, fig) -> None:
    """人物心意（減法季批 6，整合設計 5.4）：要有對話人物（歸類在對話裡）、最多 STANCE_MAX 個、id 不重複、id 不是 stances.NONE；
    字只用繁體；改做的事裡痕跡的鍵是「地點 id:痕跡名」、地點存在、倍數至少 1。"""
    if not fig.stances:
        return
    need(fig.character is not None, f"{where}：有心意的人物要有對話人物（心意在跟他說話時歸類）")
    need(len(fig.stances) <= STANCE_MAX, f"{where}：心意最多 {STANCE_MAX} 個（現在 {len(fig.stances)} 個）")
    ids = [x.id for x in fig.stances]
    need(len(set(ids)) == len(ids), f"{where}：心意的 id 重複了（{ids}）")
    for x in fig.stances:
        at = f"{where} 的心意 {x.id}"
        need(x.id != "none", f"{at}：id 不能是 none（模型歸不進任何一種時填的）")
        for text in (x.name, x.hint, x.rumor, x.chronicle):
            need(to_traditional(text) == text, f"{at}：字只能用繁體中文（{text}）")
        for key, times in x.action.marks.items():
            loc, sep, name = key.partition(":")
            need(bool(sep and name) and loc in c.locations, f"{at}：痕跡要寫成「地點 id:痕跡名」、地點存在（{key}）")
            need(times >= 1, f"{at}：痕跡 {key} 的倍數至少 1")
        if x.action.event_daily is not None:  # 生效時開的人物事件（批 6 修正輪）：從探索的池子抽、可重複（每人每天一則由 stances 管）
            ev = c.events.get(x.action.event_daily)
            need(ev is not None, f"{at}：event_daily 的事件 {x.action.event_daily} 不存在")
            if ev is not None:
                need("explore" in ev.actions and not ev.once and not ev.qiyu and not ev.fortune and ev.free_text is None,
                     f"{at}：event_daily 的事件 {ev.id} 要是探索抽得到、可重複、沒有隨口應對的事件")


ERRAND_SLOTS = ("{place}", "{hero}")  # 託付的字認得的插槽（errands.give、task_text 填）


def check_errands(c: Content, need, where: str, fig) -> None:
    """託付的池子（減法季批 6，整合設計 5.5、5.9）：要有對話人物（信是他寫的）、id 不重複、地點存在；勸降要寫 persuade（勸不成打的隊伍存在、
    痕跡是「地點 id:痕跡名」、推的線是 front 或戰線 id），其他兩種不寫；寫了 stance 要是他自己的心意；字只用繁體、只用認得的插槽。"""
    if not fig.errands:
        return
    need(fig.character is not None, f"{where}：有託付的人物要有對話人物（託付以他的信送到）")
    ids = [d.id for d in fig.errands]
    need(len(set(ids)) == len(ids), f"{where}：託付的 id 重複了（{ids}）")
    stance_ids = {x.id for x in fig.stances}
    lines = {t.id for t in c.scenario.trends} | {"front"}
    for d in fig.errands:
        at = f"{where} 的託付 {d.id}"
        need(d.target in c.locations, f"{at}：地點 {d.target} 不存在")
        need(d.stance is None or d.stance in stance_ids, f"{at}：心意 {d.stance} 不是他的心意（{sorted(stance_ids)}）")
        need((d.kind == "persuade") == (d.persuade is not None), f"{at}：勸降才寫 persuade、勸降一定要寫")
        for text in (d.task, d.text, d.to):
            need(to_traditional(text) == text, f"{at}：字只能用繁體中文（{text}）")
            need(not [s for s in re.findall(r"\{[^}]*\}", text) if s not in ERRAND_SLOTS], f"{at}：只認得 {ERRAND_SLOTS}（{text}）")
        if d.persuade is not None:
            need(d.persuade.foe in c.squads, f"{at}：勸不成打的隊伍 {d.persuade.foe} 不存在")
            for key in d.persuade.marks:
                loc, sep, name = key.partition(":")
                need(bool(sep and name) and loc in c.locations, f"{at}：痕跡要寫成「地點 id:痕跡名」、地點存在（{key}）")
            need(set(d.persuade.trend) <= lines, f"{at}：推的線只能是 front 或戰線 id（{sorted(d.persuade.trend)}）")


RECRUITER_SLOTS = ("{本週}", "{每週}")  # 入伍段引薦人的話裡照軍令多久一道換的字（enlist.SLOTS，FB-502）


def check_promotions(c: Content, need, known) -> None:
    """晉升（content/promotions.json、followers.json，計畫 T5）：陣營在劇本裡、每陣營每階一筆；人物在人物表；地點存在
    （或 nearest_base）；奇遇存在；有接手的人就要有接手版的奇遇與召見；部下的陣營存在、武學在 skills.json；
    promote／followers 只寫在晉升奇遇的選項上，給的部下是那個陣營的。
    第 2 階寫 location／event_main／summons_text，第 3、4 階寫 legs（正式版丙一）：每段有版本、版本的人物與地點存在、
    before_event 在時刻表；各段的版本事件都算晉升奇遇。選項效果的 summons_next（只有最後一段以前的奇遇、寫自己的 id）、
    patron（只有晉升奇遇）、event_mods（只有擲骰的時刻表大事）在這裡查。
    奇遇的選項要跟它在 legs 裡的位置對得上（最終審查 m3）：promote 只能是 2～4、而且等於那一則所屬的那一階；
    非最後一段的每個選項（檢定、戰鬥的輸贏兩邊也一樣）要往下一段（summons_next）或結束召見（promote），最後一段的每個選項要
    promote——不然召見留在原地，「應召」（不花體力）又能重演同一幕、獎勵白拿。"""
    factions = {f.id for f in c.scenario.factions}
    seen: set[tuple[str, int]] = set()
    promo_events: dict[str, str] = {}
    unfinished: set[str] = set()  # 第 3、4 階奇遇的各段裡，不是最後一段的版本事件：只有它們的選項可以寫 summons_next
    last_events: set[str] = set()  # 最後一段的版本事件：每個選項都要晉升
    leg_ranks: dict[str, set[int]] = {}  # 各段的版本事件 → 它在哪幾階的 legs 裡（promote 要等於那一階）
    for promo in c.promotions:
        where = f"promotions.json 的 {promo.faction}／第 {promo.rank} 階"
        need(promo.faction in factions, f"{where}：陣營不在劇本裡")
        need((promo.faction, promo.rank) not in seen, f"{where}：同一個陣營的同一階寫了兩筆")
        seen.add((promo.faction, promo.rank))
        known(where, [x for x in (promo.figure, promo.successor) if x is not None], c.figures, "人物")
        if promo.location and promo.location != "nearest_base":  # 第 3、4 階的 location 空著（地點寫在各段），空的不查
            known(where, [promo.location], c.locations, "地點")
        need(
            (promo.successor is None) == (promo.event_handoff is None) == (promo.summons_handoff is None),
            f"{where}：有接手的人就要有接手版的奇遇與召見，沒有就都不寫",
        )
        for event_id in filter(None, (promo.event_main, promo.event_handoff)):
            known(where, [event_id], c.events, "事件")
            promo_events[event_id] = promo.faction
        if promo.rank == 2:
            need(bool(promo.location and promo.event_main and promo.summons_text),
                 f"{where}：第 2 階要寫 location、event_main、summons_text")
        else:
            need(bool(promo.legs), f"{where}：第 {promo.rank} 階要寫 legs")
        for i, leg in enumerate(promo.legs):
            need(bool(leg.casts), f"{where}：第 {i + 1} 段沒有版本")
            if leg.location and leg.location != "nearest_base":  # 段的地點有寫才查
                known(where, [leg.location], c.locations, "地點")
            for cast in leg.casts:
                known(where, [cast.event], c.events, "事件")
                promo_events[cast.event] = promo.faction  # 各段的奇遇都算晉升奇遇：最後一段的選項才寫 promote、followers，下面那條檢查要認得它
                leg_ranks.setdefault(cast.event, set()).add(promo.rank)
                if i < len(promo.legs) - 1:
                    unfinished.add(cast.event)
                else:
                    last_events.add(cast.event)
                known(where, [cast.figure] if cast.figure else [], c.figures, "人物")
                known(where, [cast.at] if cast.at else [], c.locations, "地點")
                need(cast.figure is not None or cast.at is not None or leg.location is not None,
                     f"{where}：第 {i + 1} 段的 {cast.event} 不知道在哪裡演")
                need(cast.before_event is None or any(e.id == cast.before_event for e in c.timetable),
                     f"{where}：before_event {cast.before_event} 不在時刻表")
        for line in promo.patron_lines.values():
            known(where, list(line.affinity), c.characters, "人物")
    rolled = {e.id for e in c.timetable if e.roll_side is not None}  # event_mods 只對擲骰的大事有意義（timetable.add_mod）
    timetable_ids = {e.id for e in c.timetable}
    for fid, follower in c.followers.items():
        where = f"followers.json 的 {fid}"
        need(follower.faction in factions, f"{where}：陣營不在劇本裡")
        known(where, [follower.wugong], c.skills, "武學")
    for event in c.events.values():
        for choice in event.choices:
            for effect in (choice.effect, choice.fail_effect):  # 檢定輸的那一邊也一樣（promo_hao_4 的摔角是第一則在 fail_effect 晉升的）
                if effect.promote is None and not effect.followers:
                    continue
                where = f"事件 {event.id}"
                need(event.id in promo_events, f"{where}：promote／followers 只能寫在晉升奇遇（promotions.json 的事件）")
                known(where, effect.followers, c.followers, "部下")
                side = promo_events.get(event.id)
                need(all(c.followers[f].faction == side for f in effect.followers if f in c.followers),
                     f"{where}：給的部下要是 {side} 的")
    # 第 3、4 階的三種新效果（正式版丙一）：選項的 effect 與 fail_effect 都查
    for event in c.events.values():
        for choice in event.choices:
            where = f"事件 {event.id}"
            # 這個選項會走到的效果：檢定、戰鬥有輸贏兩邊；沒有的話 fail_effect 不會被用到
            sides = (choice.effect, choice.fail_effect) if choice.check is not None or choice.combat else (choice.effect,)
            if event.id in unfinished:
                need(all(e.summons_next is not None or e.promote is not None for e in sides),
                     f"{where}：非最後一段的選項每一邊（檢定、戰鬥的輸贏也一樣）都要寫 summons_next（往下一段）或 promote（結束召見），"
                     "不然召見留在原地，「應召」又能重演同一幕")
            if event.id in last_events:
                need(all(e.promote is not None for e in sides),
                     f"{where}：最後一段的選項每一邊（檢定、戰鬥的輸贏也一樣）都要寫 promote，不然召見留在原地，「應召」又能重演同一幕")
            for effect in (choice.effect, choice.fail_effect):
                if effect.donate_grain or effect.runic:
                    # 捐糧（記貢獻）與符文殘片自己不看陣營：只准寫在晉升奇遇（召見只發給自己陣營的人），或事件／選項的條件寫了
                    # factions 的地方，沒投靠的人、別的陣營的人才領不到（丙二審查）
                    reachable = event.id in promo_events or bool(event.condition.factions) or bool(choice.condition.factions)
                    need(reachable, f"{where}：donate_grain／runic 只能寫在晉升奇遇，或條件寫了 factions 的事件、選項"
                                    "（不然散人與別的陣營的人也領得到貢獻與殘片）")
                if effect.promote is not None:
                    need(2 <= effect.promote <= 4, f"{where}：promote 要在 2～4 之間（第 2 到 4 階），寫了 {effect.promote}")
                    ranks_here = leg_ranks.get(event.id)
                    need(not ranks_here or effect.promote in ranks_here,
                         f"{where}：promote 要寫 {'、'.join(str(r) for r in sorted(ranks_here or ()))}"
                         f"（這一則在那一階的 legs 裡），寫了 {effect.promote}")
                if effect.summons_next is not None:
                    if effect.summons_next != event.id:
                        need(False, f"{where}：summons_next 要寫這一則自己的 id")
                    else:
                        need(event.id in unfinished, f"{where}：summons_next 只能寫在晉升奇遇的最後一段以前（最後一段演完就是晉升）")
                if effect.patron is not None:
                    need(event.id in promo_events, f"{where}：patron 只能寫在晉升奇遇（promotions.json 的事件）")
                for mod in effect.event_mods:
                    need(mod.event in timetable_ids, f"{where}：event_mods 的 {mod.event} 不在時刻表")
                    need(mod.event not in timetable_ids or mod.event in rolled,
                         f"{where}：event_mods 的 {mod.event} 不是擲骰的大事（固定、決戰、季末沒有成功率可改）")


def check_opportunities(c: Content, need, known, front_ids: list[str]) -> None:
    """機緣（content/opportunities.json、orders.json 的 rank2，正式版乙一）：id 不重複；陣營存在；kind 對應的那一塊要寫、
    別的不能寫；人物、地點、大區、戰線存在；累積型的來源行動（第 2 階行動、守勢行動）自己陣營要有；有東西要送的天時地利型
    要寫送的選項與送到的那一句；文字只能繁體。front_ids 是 validate 的那一份戰線清單。
    乙二：拼圖型（拿法寫全、東西與處的 key 不重複、官軍交給誰與豪強的靠山）、推理型（天機存在、嫌疑人剛好是那個天機的候選、
    每個嫌疑人的特徵都有片段）、集體密謀型（每一處寫 front 或 at、跟 how 一致、need_parts 不超過處數）；請命的陣營與人物存在。"""
    from .core import omen_base  # noqa: PLC0415  軍情第 34 批：天機表在核心的 omen_base（原本延後 import foreshadow）

    ids = [o.id for o in c.opportunities]
    need(len(set(ids)) == len(ids), "opportunities.json：機緣 id 重複")
    factions = {f.id for f in c.scenario.factions}
    regions = {r.id for r in c.map.regions}
    trend_ids = {t.id for t in c.scenario.trends}
    derived_ids = {t.id for t in c.scenario.trends if t.derived}  # 衍生線（開關開著時由戰線合成的黃巾聲勢）
    for o in c.opportunities:
        where = f"機緣 {o.id}"
        need(o.faction in factions, f"{where}：沒有陣營 {o.faction}")
        blocks = {"bond": o.bond, "accumulate": o.accumulate, "timing": o.timing,
                  "puzzle": o.puzzle, "deduce": o.deduce, "plot": o.plot}
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
        if o.puzzle is not None:
            keys = [piece.key for piece in o.puzzle.pieces]
            need(bool(keys), f"{where}：拼圖至少要有一樣東西")
            need(len(set(keys)) == len(keys), f"{where}：東西 key 重複")
            for piece in o.puzzle.pieces:
                need(piece.how != "ask" or (piece.front is not None and piece.figure is not None and piece.topic),
                     f"{where}：{piece.key} 是 ask，要寫 front、figure、topic")
                need(piece.how != "ask" or "*" in piece.lines, f"{where}：{piece.key} 的 lines 要有 \"*\"（沒列到的人說的那一句）")
                need(piece.how == "ask" or piece.at is not None, f"{where}：{piece.key} 要寫 at")
                need(piece.how != "check" or piece.check is not None, f"{where}：{piece.key} 是 check，要寫 check")
                known(where, [piece.front] if piece.front else [], front_ids, "戰線")
                known(where, [piece.at] if piece.at else [], c.locations, "地點")
                known(where, [k for k in piece.lines if k != "*"] + ([piece.figure] if piece.figure else []), c.figures, "人物")
                texts += [piece.name, piece.topic, piece.label, piece.ok, piece.fail] + list(piece.lines.values())
            pr = o.puzzle.present
            need(pr.at is not None or bool(pr.patrons), f"{where}：交給誰要寫 at 或 patrons")
            need(pr.at is None or pr.figure is not None, f"{where}：官軍的交付要寫 figure")
            known(where, [pr.at] if pr.at else [], c.locations, "地點")
            known(where, [pr.figure] if pr.figure else [], c.figures, "人物")
            known(where, [x.character for x in pr.patrons.values()], c.characters, "人物")
            known(where, [x.at for x in pr.patrons.values()], c.locations, "地點")
            texts += [pr.stand_in, pr.label, pr.done] + [x.done for x in pr.patrons.values()]
        if o.deduce is not None:
            d = o.deduce
            need(d.tianji in omen_base.TIANJI, f"{where}：天機 {d.tianji} 不存在")
            need({s.id for s in d.suspects} == set(omen_base.TIANJI.get(d.tianji, ())),
                 f"{where}：嫌疑人要跟天機 {d.tianji} 的候選一樣")
            keys = {t.key for t in d.traits}
            need(all(set(s.traits) <= keys for s in d.suspects), f"{where}：嫌疑人有沒寫片段的特徵")
            need(all(t.region in regions for t in d.traits), f"{where}：特徵有不存在的大區")
            need(bool(d.askers), f"{where}：至少要有一位指認的人")
            known(where, [h.figure for h in d.askers], c.figures, "人物")
            known(where, [h.at for h in d.askers], c.locations, "地點")
            known(where, list(d.trend), trend_ids, "大勢線")  # 指對了推哪條線（戰線；衍生線不能直接推）
            need(not set(d.trend) & derived_ids, f"{where}：trend 不能推衍生線（要推就推它的來源線）")
            texts += [d.label, d.right, d.wrong] + [s.name for s in d.suspects] + [t.text for t in d.traits]
        if o.plot is not None:
            pl = o.plot
            keys = [x.key for x in pl.parts]
            need(bool(keys), f"{where}：集體密謀至少要有一處")
            need(len(set(keys)) == len(keys), f"{where}：各處的 key 重複")
            need(pl.how != "check" or pl.check is not None, f"{where}：check 類要寫 check")
            need(all((x.front is None) != (x.at is None) for x in pl.parts), f"{where}：每一處寫 front 或 at 其中一個")
            need(pl.how != "win" or all(x.front is not None for x in pl.parts), f"{where}：win 類每一處都要寫 front")
            need(pl.how != "check" or all(x.at is not None for x in pl.parts), f"{where}：check 類每一處都要寫 at")
            known(where, [x.front for x in pl.parts if x.front], front_ids, "戰線")
            need(pl.need_parts is None or 0 < pl.need_parts <= len(pl.parts), f"{where}：need_parts 超出處數")
            known(where, [x.at for x in pl.parts if x.at], c.locations, "地點")
            texts += [pl.part_label, pl.part_ok, pl.part_fail, pl.start_text, pl.done_text, pl.helper_text,
                      pl.fail_text] + [x.name for x in pl.parts]
        for text in texts:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    for faction_id, action in c.orders.rank2.items():
        need(faction_id in factions, f"orders.json rank2：沒有陣營 {faction_id}")
        for text in (action.name, action.ok, action.fail):
            need(to_traditional(text) == text, f"orders.json rank2.{faction_id}：文字只能用繁體中文（「{text[:12]}」）")
    # 第 3、4 階的行動（正式版戊一）：id 不重複、陣營存在、標籤是某個地點真的帶的（拼錯的那個行動哪裡都不會出現）、檢定的屬性認得、
    # 有檢定就要寫沒過的那一句。標籤不看地點在不在戰線上：validate 遇到壞掉的大區多邊形還會繼續跑，atlas.region_of 會丟 ValueError
    rank_action_ids = [a.id for a in c.orders.rank_actions]
    need(len(set(rank_action_ids)) == len(rank_action_ids), "orders.json rank_actions：id 重複")
    place_tags = {t for loc in c.locations.values() for t in loc.tags}
    for a in c.orders.rank_actions:
        where = f"orders.json rank_actions.{a.id}"
        need(a.faction in factions, f"{where}：沒有陣營 {a.faction}")
        need(bool(a.id) and ":" not in a.id, f"{where}：id 不能是空的、也不能有冒號（選項是 act:rank:<id>，軍令記功的 kind 也是它）")
        need(set(a.tags) <= place_tags, f"{where}：tags 裡有的標籤，沒有任何地點帶：{sorted(set(a.tags) - place_tags)}")
        need("{地點}" in a.ok, f"{where}：ok 要寫 {{地點}}（成功的那一句要說在哪裡）")
        if a.check is not None:
            known(where, [a.check.stat], STATS, "屬性")
        need(a.check is None or bool(a.fail.strip()), f"{where}：有檢定就要寫 fail（沒過的那一句）")
        for text in (a.name, a.ok, a.fail):
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}」）")
    for faction_id, petition in c.orders.petition.items():
        need(faction_id in factions, f"orders.json petition：沒有陣營 {faction_id}")
        known(f"orders.json petition.{faction_id}", petition.characters, c.characters, "人物")
        need(to_traditional(petition.label) == petition.label, f"orders.json petition.{faction_id}：文字只能用繁體中文（「{petition.label[:12]}」）")


def check_foreshadows(
    c: Content, need, known, region_ids: list[str], front_ids: list[str], counters_written: dict[str, str],
) -> None:
    """伏筆（content/foreshadows.json，計畫 T7）：鏈的大事在時刻表上、陣營在劇本裡；片段的大區是大區、事件與人物存在；
    最後一步的地點、物品、人物存在，答案是選項之一或 tianji:<天機>（天機的選項要剛好是候選）；文字只用繁體中文。
    伏筆計數：效果寫的要有鏈讀，鏈讀的要有效果寫（官銀由 guanyin 的規則寫）。"""
    from .core.omen_base import FIGURE_SLOT, GUANYIN, TIANJI, TIANJI_ANSWER, asks_of, trips  # noqa: PLC0415  軍情第 34 批：核心的 omen_base

    fs = c.foreshadows
    faction_ids = [f.id for f in c.scenario.factions]
    item_ids = [item.id for item in fs.items]
    chain_ids = [ch.id for ch in fs.chains]
    for label, ids in (("伏筆物品", item_ids), ("伏筆", chain_ids)):
        duplicated = sorted({x for x in ids if ids.count(x) > 1})
        need(not duplicated, f"{label} id 重複：{'、'.join(duplicated)}")
    events = {e.id: e for e in c.timetable}

    check_text = functools.partial(_check_traditional, need)

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
        # 豪強第三方的鏈 2026-10-31 拿掉（T-05）：鏈只能是會鎖定大事的兩方
        need(ch.side in TIMETABLE_SIDES, f"{where}：side 只能是 guan 或 huang（寫的是 {ch.side}；豪強第三方的鏈已經拿掉）")
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


def check_bounties(c: Content, need) -> None:
    """懸賞榜的設定（Config.bounties，懸賞榜設計 4.1 末段）：種類只能是認得的（不認得的 bounties.issue 會默默跳過）；求兵挑屬性的
    範圍至少一個、而且是認得的屬性；求兵的價錢剛好寫三個品質與四個階（1～4 階，四階 ×6；少一個，交那種兵器時會 KeyError）。
    give_kinds 只能是 arms（求藝企劃者 2026-10-21 拿掉，寫 art 直接報錯，不默默跳過）。
    give_kinds、give_attributes 不能重複：kinds 寫兩次 strike 是「掛兩張」，give_kinds 寫兩次 arms 卻只會掛一張（issue 照種類各掛一張），
    照 kinds 的習慣寫會被默默吃掉；give_attributes 重複會讓三方抽到同一個屬性。
    賞的字典（silver、exp、deeds、xinde）：設定覆寫檔寫了就是整張換掉，少寫 give_kinds 裡某一種的那一項，掛得出來、交得了，領到的卻默默是 0
    （bounties.py 都是 .get(種類, 0)）。所以預設有寫的項目，掛出去的每一種都要留著（預設 silver 沒有 arms：求兵的銀兩走 arms_silver × arms_tier）。"""
    cfg = c.config.bounties
    need(set(cfg.kinds) <= {"strike", "scout", "escort"}, f"Config.bounties.kinds 只能有 strike、scout、escort：{cfg.kinds}")
    need(
        set(cfg.give_kinds) <= {"arms"} and len(set(cfg.give_kinds)) == len(cfg.give_kinds),
        f"Config.bounties.give_kinds 只能有 arms（求藝 2026-10-21 拿掉），最多寫一次：{cfg.give_kinds}",
    )
    need(
        bool(cfg.give_attributes) and set(cfg.give_attributes) <= set(ATTRIBUTES)
        and len(set(cfg.give_attributes)) == len(cfg.give_attributes),
        f"Config.bounties.give_attributes 至少一個、不重複，而且只能是 {'、'.join(ATTRIBUTES)}：{cfg.give_attributes}",
    )
    need(set(cfg.arms_silver) == {"下品", "中品", "上品"}, f"Config.bounties.arms_silver 要剛好寫下品、中品、上品：{sorted(cfg.arms_silver)}")
    need(set(cfg.arms_tier) == {"1", "2", "3", "4"}, f"Config.bounties.arms_tier 要剛好寫 1、2、3、4：{sorted(cfg.arms_tier)}")
    defaults = type(cfg)()  # 預設長什麼樣，就是「該寫哪幾項」的依據
    for field in ("silver", "exp", "deeds", "xinde"):
        given = getattr(cfg, field)
        missing = [kind for kind in cfg.give_kinds if kind in getattr(defaults, field) and kind not in given]
        need(
            not missing,
            f"Config.bounties.{field} 少了 {'、'.join(missing)} 的賞（整張字典換掉時，give_kinds 裡每一種都要寫，少了會默默給 0）：{sorted(given)}",
        )


def check_duels(c: Content, need, known) -> None:
    """單人頭目戰（content/duels.json）：地點、素材認得；每個陣營都挑得到一個不是自己人的面貌（散人挑第一個）；
    面貌的陣營認得；出招偏好只寫三招、權重不是負的、加起來大於 0。"""
    from .models import MOVES  # noqa: PLC0415

    factions = {f.id for f in c.scenario.factions}
    for boss in c.duels.values():
        where = f"頭目 {boss.id}"
        need(bool(boss.locations), f"{where}：至少要有一個地點")
        known(where, boss.locations, c.locations, "地點")
        known(where, boss.drops, c.materials, "素材")
        for i, foe in enumerate(boss.foes):
            if foe.side is not None:
                need(foe.side in factions, f"{where} 的第 {i + 1} 個面貌：未知的陣營 {foe.side}")
            need(set(foe.moves) <= set(MOVES), f"{where} 的第 {i + 1} 個面貌：moves 只能寫{'、'.join(MOVES)}")
            need(all(w >= 0 for w in foe.moves.values()) and (not foe.moves or sum(foe.moves.values()) > 0),
                 f"{where} 的第 {i + 1} 個面貌：moves 的權重不能是負的、也不能全是 0")
        for faction in sorted(factions):
            need(any(foe.side != faction for foe in boss.foes), f"{where}：{faction} 的人挑不到一個不是自己人的面貌")


def check_gear(c: Content, need, known) -> None:
    """寶物表、名駒、名將贈禮（content/gear.json，裝備四欄 6.3、5.7）與 Config.treasures：效果的數字剛好八種；良駒的品質權重只寫
    三個品質、不是負的、加起來大於 0。有表時：掉落池至少一件；名字不重複、過得了命名過濾、id 不叫 good_horse、寶物與名駒的 id 不重複；
    贈禮的人物存在、一位只寫一次、送的是名駒或 pool 為 false 的寶物，送禮那一句是繁體、只用 {general}、{gift}；
    pool 為 false 的寶物與名駒都要有人送（不然永遠拿不到）。沒有 gear.json（測試內容）就只查設定。"""
    cfg, book = c.config.treasures, c.gear
    need(set(cfg.effects) == set(TREASURE_EFFECTS), f"Config.treasures.effects 要剛好寫八種效果：{sorted(cfg.effects)}")
    need(
        set(cfg.horse_quality) <= {"下品", "中品", "上品"} and all(v >= 0 for v in cfg.horse_quality.values())
        and sum(cfg.horse_quality.values()) > 0,
        f"Config.treasures.horse_quality 只能寫下品、中品、上品，權重不能是負的、加起來要大於 0：{cfg.horse_quality}",
    )
    if not (book.treasures or book.steeds or book.gifts):
        return
    need(any(t.pool for t in book.treasures.values()), "content/gear.json：掉落池（pool 為 true 的寶物）至少要一件")
    clash = sorted(set(book.treasures) & set(book.steeds))
    need(not clash, f"content/gear.json：寶物與名駒的 id 重複：{clash}")
    names: set[str] = set()
    for item in [*book.treasures.values(), *book.steeds.values()]:
        where = f"裝備表 {item.id}"
        need(item.id != GOOD_HORSE, f"{where}：id 不能叫 {GOOD_HORSE}（事件給良駒用的字）")
        need(item.name not in names, f"{where}：名字 {item.name} 重複")
        names.add(item.name)
        problem = name_problem(item.name, c)
        need(problem in (None, GEAR_CLASH), f"{where}：名字 {item.name} 過不了命名過濾（{problem}）")  # 寶物自己的名字現在會撞到自己
    given: set[str] = set()
    for gift in book.gifts:
        where = f"名將贈禮 {gift.character}"
        known(where, [gift.character], c.characters, "人物")
        need(gift.character not in given, f"{where}：同一位人物寫了兩次")
        given.add(gift.character)
        tdef = book.treasures.get(gift.gear)
        need(gift.gear in book.steeds or (tdef is not None and not tdef.pool), f"{where}：贈禮 {gift.gear} 要是名駒或 pool 為 false 的寶物")
        if gift.line:
            need(to_traditional(gift.line) == gift.line, f"{where}：送禮那一句只能用繁體中文")
            try:
                gift.line.format(general="甲", gift="乙")
            except (KeyError, IndexError, ValueError):
                need(False, f"{where}：送禮那一句只能用 {{general}}、{{gift}}")
    sent = {gift.gear for gift in book.gifts}
    for item_id in [t.id for t in book.treasures.values() if not t.pool] + list(book.steeds):
        need(item_id in sent, f"裝備表 {item_id}：沒有人送（pool 為 false 的寶物與名駒只從名將贈禮來）")


def check_signature_arms(c: Content, need, known) -> None:
    """名將本命兵器（content/gear.json 的 signature_arms，兵器設計 4.10）：人物存在、一位只寫一把；種類、屬性合法；名字跟寶物、名駒、
    隱藏配方的名器、別把本命兵器不重複（name_problem 對寶物表與本命兵器回同一句 GEAR_CLASH，蓋過 FORGE_CLASH，所以這裡另查），
    過得了命名過濾（自己的名字收 GEAR_CLASH），不能帶別種兵器的字、不能跟架上的現成兵器同名（一般組合字表組得出它的話，驗字表那一段
    的 name_problem 會擋下來，不必另查）；figure 是人物表上的大勢人物、而且就是這一位；兩句話是繁體、只用 {general}、{arm}。"""
    book = c.gear
    names = {item.name for item in [*book.treasures.values(), *book.steeds.values(), *c.forge_secrets.values()]}
    shop = {weapon_shop_name(k, a) for k in WEAPON_KINDS for a in WEAPON_ATTR_WORDS}
    seen: set[str] = set()
    for arm in book.signature_arms:
        where = f"本命兵器 {arm.character}"
        known(where, [arm.character], c.characters, "人物")
        need(arm.character not in seen, f"{where}：同一位人物寫了兩次")
        seen.add(arm.character)
        need(arm.kind in WEAPON_KINDS, f"{where}：種類 {arm.kind} 不是兵器種類")
        need(arm.attribute in ATTRIBUTES, f"{where}：屬性 {arm.attribute} 不認得")
        need(arm.name not in names, f"{where}：名字 {arm.name} 重複")
        names.add(arm.name)
        problem = name_problem(arm.name, c)
        need(problem in (None, GEAR_CLASH), f"{where}：名字 {arm.name} 過不了命名過濾（{problem}）")
        others = [word for kind, words in WEAPON_WORDS.items() if kind != arm.kind for word in words]
        need(not any(word in arm.name for word in others), f"{where}：名字 {arm.name} 帶了別種兵器的字")
        need(arm.name not in shop, f"{where}：名字 {arm.name} 跟架上的現成兵器同名")
        if arm.figure is not None:
            known(where, [arm.figure], c.figures, "大勢人物")
            fig = c.figures.get(arm.figure)
            need(fig is None or fig.character == arm.character, f"{where}：大勢人物 {arm.figure} 不是這一位")
        for label, line in (("送兵器那一句", arm.gift_line), ("奪兵器那一句", arm.seize_line)):
            if not line:
                continue
            need(to_traditional(line) == line, f"{where}：{label}只能用繁體中文")
            try:
                line.format(general="甲", arm="乙")
            except (KeyError, IndexError, ValueError):
                need(False, f"{where}：{label}只能用 {{general}}、{{arm}}")


def check_attributes(c: Content, need) -> None:
    """屬性定義、效果表、難度等級與獎勵等級（屬性與跨季架構 v2 第二、五節）寫得對。第 ① 階段屬性的鍵與順序跟 team.COMBAT_STATS 一樣。"""
    from .team import ATTR_HOOKS, COMBAT_STATS, RATE_KEYS  # noqa: PLC0415  team 一路 import 很多模組，content 不在模組層依賴它

    keys = [a.key for a in c.attributes] or list(COMBAT_STATS)
    if c.attributes:
        need(tuple(keys) == COMBAT_STATS, f"attributes.json：鍵與順序要是 {'、'.join(COMBAT_STATS)}（寫了 {'、'.join(keys)}）")
        need(all(a.name for a in c.attributes), "attributes.json：每一項都要有顯示名")
    for i, row in enumerate(c.config.attributes.effects):
        at = f"attributes.effects[{i}]（{row.attr}→{row.hook}）"
        need(row.attr in keys, f"{at}：沒有 {row.attr} 這一項屬性")
        need(row.hook in ATTR_HOOKS, f"{at}：沒有 {row.hook} 這個鉤子（team.ATTR_HOOKS）")
        if row.curve == "linear" and isinstance(row.per, str):
            need(row.per in RATE_KEYS, f"{at}：per 寫字的話要是 {'、'.join(RATE_KEYS)} 其中一個")
        if row.curve == "tiers":
            need(bool(row.steps) and [t for t, _ in row.steps] == sorted(t for t, _ in row.steps), f"{at}：steps 要照門檻由小到大")
    v2 = c.config.attributes.v2
    if c.attributes_v2:
        need([a.key for a in c.attributes_v2] == v2.keys, f"attributes_v2.json：鍵與順序要是 {'、'.join(v2.keys)}")
    for i, row in enumerate(v2.effects):
        need(row.attr in v2.keys and row.hook in ATTR_HOOKS, f"attributes.v2.effects[{i}]：{row.attr}→{row.hook} 不認得")
    need(all(t in v2.keys for t in v2.legacy.values()), "attributes.v2.legacy：只能對到新的五項")
    grades = [g.key for g in c.config.checks.grades]
    need(len(set(grades)) == len(grades) and bool(grades), "checks.grades：等級的 key 不能重複、至少一級")
    need([g.dc for g in c.config.checks.grades] == sorted(g.dc for g in c.config.checks.grades), "checks.grades：照難度由易到難排")
    rewards = [g.key for g in c.config.rewards.grades]
    need(len(set(rewards)) == len(rewards), "rewards.grades：等級的 key 不能重複")


def validate(c: Content) -> None:
    if c._only_pack is not None:  # core_content（第 63 批）。不能用 ContentError：只載一包一定驗不過，沒寫 match 的 pytest.raises(ContentError) 會假綠
        raise RuntimeError(f"這份內容只載了 {c._only_pack} 這一包，不能拿來驗內容：測試標 @pytest.mark.whole_content 拿整份")
    errors: list[str] = []
    from .atlas import region_of  # noqa: PLC0415  延後 import：atlas → world → rules 一路載入，content 不必一開始就依賴它們
    # core_content（第二輪第 96 批）：timetable、conquest 這幾支頂層 import 多，函式內 import
    from .relations import check_relations  # noqa: PLC0415
    from .plans import check_itineraries  # noqa: PLC0415
    from .siege import check_siege_templates  # noqa: PLC0415
    from .push import check_core_loop  # noqa: PLC0415
    from .terrain import check_terrain_arts  # noqa: PLC0415
    from .battlelog import check_combat_lines  # noqa: PLC0415
    from .signature import check_signature_arts  # noqa: PLC0415
    from .secret_recipes import validate_secrets  # noqa: PLC0415
    from .orders import check_orders  # noqa: PLC0415
    from .traits import check_traits  # noqa: PLC0415
    from .timetable import check_timetable  # noqa: PLC0415
    from .territory import check_territory  # noqa: PLC0415
    from .conquest import check_conquest_blocks  # noqa: PLC0415
    from .forge_secrets import validate_forge_secrets, validate_named_clash, validate_tier4_named  # noqa: PLC0415
    from .core.features import check_at  # noqa: PLC0415

    trend_ids = {t.id for t in c.scenario.trends}
    hidden = {t.id for t in c.scenario.trends if t.hidden}
    derived = {t.id for t in c.scenario.trends if t.derived}  # 衍生線（第一季濃縮版的黃巾聲勢）
    season_one_trends = {t.id for t in c.scenario.trends if t.season_one}  # 第一季才有的線（三條戰線）
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

    need(  # 療傷只在醫館（clinic.py）：開著時至少要有一家，不然內傷一輩子治不好
        not c.config.heal_at_clinic or any("醫館" in (loc.tags or []) for loc in c.locations.values()),
        "config.heal_at_clinic 開著，可是沒有地點帶「醫館」標籤：內傷治不好",
    )
    odds = c.config.fuse_quality_odds  # 合成擲品質：只擲得到下品～上品（絕學要修練），權重不能是負的、也不能全是 0
    need(
        set(odds) <= {"下品", "中品", "上品"} and all(w >= 0 for w in odds.values()) and sum(odds.values()) > 0,
        "config.fuse_quality_odds 只能寫下品、中品、上品，權重不能是負的、也不能全是 0",
    )
    fq = c.config.fuse_quality  # 照搭配推機率：上品、下品的範圍要排得下中品（兩頭都推到底時中品也不會是負的）
    need(
        0 <= fq.up_range[0] <= fq.up_range[1] and 0 <= fq.low_range[0] <= fq.low_range[1]
        and fq.up_range[1] + fq.low_range[0] <= 100 and fq.up_range[0] + fq.low_range[1] <= 100
        and all(len(pair) == 2 for pair in fq.lines.values()),
        "config.fuse_quality 的上品、下品範圍排不下中品（或說明那一句不是「加分、扣分」兩種寫法）",
    )
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
    taught: dict[str, str] = {}  # 事件 learn_skills 給得到的武學 → 第一個給它的地方（品質要明寫，見最後）
    marks_read: dict[str, str] = {}  # 痕跡 → 第一個讀它的地方（條件或文字裡的模糊人數）
    outcome_marks: dict[str, str] = {}  # 隨口應對分岔的後果寫的痕跡 → 第一個寫它的後果（減法季批 4）

    def check_mark_key(where: str, key: str) -> None:
        loc, sep, name = key.partition(":")
        need(bool(sep and name.strip()), f"{where}：痕跡 {key!r} 要寫成「地點 id:痕跡名」")
        need(loc in c.locations, f"{where}：痕跡 {key!r} 的地點 {loc} 不存在")

    def read_marks_in(where: str, text: str) -> None:
        for key in MARKS_TOKEN.findall(text):
            check_mark_key(where, key)
            marks_read.setdefault(key, where)

    def check_condition(where: str, cond: Condition, after_fight: bool = False) -> None:
        """after_fight：這個條件掛在只有遊歷會抽的事件上（actions 剛好是 ["train"]，打完才抽），fight_tiers 只有這裡有意義：
        別的行動抽到它時沒有「剛打完的那一場」（探索三選一是互斥的支線、交友沒有戰鬥、只靠串接來的更沒有），寫了永遠不成立。"""
        known(where, cond.fight_tiers, FIGHT_TIERS, "戰鬥結果")
        need(
            after_fight or not cond.fight_tiers,
            f"{where}：fight_tiers 只能寫在遊歷會抽的事件（actions 剛好是 [\"train\"]）的條件上，別處沒有「剛打完的那一場」，永遠不成立",
        )
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
                f"{where}：條件不能讀第一季的線 {key}（條件讀的是大勢的原數字：開關關著時戰線沒有值、"
                "季中才開季的那一季讀不到起始值；要讀就讀黃巾聲勢這種衍生線或一般的線）",
            )
        known(where, [*cond.revealed_all, *cond.revealed_none], trend_ids, "大勢線")
        known(where, cond.members_none, c.characters, "人物")
        known(where, cond.factions, faction_ids, "陣營")
        known(where, cond.factions_none, faction_ids, "陣營")
        known(where, cond.controlled_by, faction_ids, "陣營")
        known(where, [*cond.place_state, *cond.place_state_none], PLACE_KINDS, "地點的樣子")
        known(where, cond.clue_items, item_ids, "伏筆物品")
        weekly = cond.week_min is not None or cond.week_max is not None
        if _week7(c) and weekly:  # 7 天濃縮季同 21 天季照天數，寫 7 天的那一份（cal_day_*7，1～7 在模型裡驗）
            need(cond.week_min is None or cond.cal_day_min7 is not None, f"{where}：7 天濃縮季照天數，寫了 week_min 也要寫 cal_day_min7")
            need(cond.week_max is None or cond.cal_day_max7 is not None, f"{where}：7 天濃縮季照天數，寫了 week_max 也要寫 cal_day_max7")
        elif c.config.season21 and weekly:  # 21 天季不看週、只看天（正式季整合設計 1.2 給開發 6）：寫了哪一頭的週就要寫那一頭的天
            need(cond.week_min is None or cond.cal_day_min is not None, f"{where}：21 天季照天數，寫了 week_min 也要寫 cal_day_min")
            need(cond.week_max is None or cond.cal_day_max is not None, f"{where}：21 天季照天數，寫了 week_max 也要寫 cal_day_max")
        else:
            for week in (cond.week_min, cond.week_max):
                need(week is None or 1 <= week <= c.config.season_weeks, f"{where}：週次 {week} 不在 1～{c.config.season_weeks} 之間")
        for day in (cond.cal_day_min, cond.cal_day_max):
            need(day is None or day <= c.config.season_weeks * 7, f"{where}：第 {day} 天超出季曆的 {c.config.season_weeks * 7} 天")
        for sub in cond.any_of:
            check_condition(where, sub, after_fight)

    def no_lore(where: str, eff: Effect) -> None:
        """博聞只靠升級的點數增加（設計 6.3；PM 2026-10-05）：任何效果的 stats 都不能有 lore，給、扣、寫 0 都不行。
        檢定（Check／隨口應對的 stat）可以照樣考博聞，那不是獎勵。"""
        need(LORE not in eff.stats, f"{where}：stats 不能有 {LORE}（博聞只能靠升級的點數增加，事件、奇遇、隨口應對的獎勵都不能給、也不能扣）")

    def check_effect(where: str, eff: Effect, outcome: bool = False) -> None:
        """outcome：這是隨口應對分岔的一種後果（減法季批 4）——只有它准寫 contribution（rules.apply_effect 不讀，接線之前寫在別處
        會靜靜沒作用）；它寫的痕跡另記一筆（check_outcomes）。"""
        no_lore(where, eff)
        need(outcome or eff.contribution == 0,
             f"{where}：contribution 只能寫在隨口應對分岔的後果上（接線之前 rules.apply_effect 不讀它，寫在這裡不會有作用）")
        for key, n in eff.marks.items():
            check_mark_key(where, key)
            need(1 <= n <= 3, f"{where}：痕跡 {key} 一次只能加 1～3（不能減）")
            marks_written.setdefault(key, where)
            if outcome:
                outcome_marks.setdefault(key, where)
        read_marks_in(where, eff.text)
        known(where, eff.stats, STATS, "屬性")
        known(where, eff.learn_skills, c.skills, "武學")
        for skill_id in eff.learn_skills:
            taught.setdefault(skill_id, where)
        known(where, eff.materials, c.materials, "素材")
        known(where, eff.insights, c.insights, "意境")
        for insight_id in eff.insights:
            if insight_id in c.insights and c.insights[insight_id].grant is not None:
                need(False, f"{where}：{c.insights[insight_id].name}只能靠名聲悟得，事件不能給")
        known(where, eff.affinity, c.characters, "人物")
        # 黃巾的第 3、4 階奇遇（正式版丙二）：捐糧的據點存在、份量大於 0（0 份換算出 0、不拿糧也記一筆貢獻）；給的片段存在
        known(where, list(eff.donate_grain), c.locations, "地點")
        need(all(n > 0 for n in eff.donate_grain.values()), f"{where}：donate_grain 的份量要大於 0")
        for ref in eff.fs_fragments:
            chain_id, _, index = ref.rpartition(":")
            found = next((ch for ch in c.foreshadows.chains if ch.id == chain_id), None)
            need(found is not None and index.isdecimal() and int(index) < len(found.fragments),
                 f"{where}：fs_fragments 的 {ref} 不存在（要寫「鏈 id:片段序號」，序號從 0 起）")
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
        if eff.gear is not None:  # 奇遇給的寶物或良駒（裝備四欄 6.4）：掉落池的寶物、或一匹良駒；名將贈禮與名駒不能從事件給
            tdef = c.gear.treasures.get(eff.gear)
            need(eff.gear == GOOD_HORSE or (tdef is not None and tdef.pool),
                 f"{where}：gear {eff.gear} 要是 content/gear.json 掉落池的寶物或 {GOOD_HORSE}（名將贈禮、名駒不能從事件給）")

    def check_free_text(where: str, ev: Event) -> None:
        """隨口應對（§8.1）：賣的是好玩不是划算，獎勵不能比同一則事件裡最好的檢定選項高；
        也不能串到下一則事件、結識人物、拜師、改旗標或晉升（那些都要靠手寫的選項）。"""
        ft, fw = ev.free_text, f"{where} 隨口應對"
        check_effect(fw, ft.effect)
        check_effect(fw, ft.fail_effect)
        # 只跟人人按得到的選項比（名聲 5.3：俠寇選項要稱號才按得到，獎勵本來就高一點，不拿來放寬隨口應對的上限）
        open_choices = [ch for ch in ev.choices if ch.needs is None]
        rivals = [ch.effect for ch in open_choices if ch.check is not None] or [ch.effect for ch in open_choices]
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
                    # 晉升奇遇的效果（只能寫在手寫的晉升選項上）：summons_next、event_mods、patron 是正式版丙一的
                    ("promote", eff.promote), ("followers", eff.followers), ("summons_next", eff.summons_next),
                    ("event_mods", eff.event_mods), ("patron", eff.patron),
                    # 黃巾奇遇的捐糧、給片段、記殘片（正式版丙二）：同樣只准寫在手寫的選項上，不是隨口一句話換得到的
                    ("donate_grain", eff.donate_grain), ("fs_fragments", eff.fs_fragments), ("runic", eff.runic),
                    # 寶物、良駒（裝備四欄 6.4）：隨口一句就換一件寶物，等於繞過稀有
                    ("gear", eff.gear),
                ) if used
            ]
            need(not banned, f"{fw} {label}：不能有 {'、'.join(banned)}")

    def check_outcomes(where: str, ev: Event) -> None:
        """隨口應對分岔（減法季整合設計 5.1、5.9；主機側計畫 Task 4-1，規則從 scripts/check_outcomes.py 搬來）：
        2～4 種後果（作惡那一種另算、最多一種、原事件要有作惡的固定選項），最後一種是 fallback（只有一句結果）；其餘每一種判法寫一種
        ——check（屬性是看得了的那幾項或 best_of、難度在這則固定選項的帶子裡）、combat（這則固定選項裡打的那一路）、cost（正的銀兩、
        必成，沒有失手，企劃者第 8 件 c）——都留一個這則事件地點上的痕跡、記貢獻（作惡的不記）。效果只准寫結果、獎勵、體力、痕跡、
        貢獻（公開的只有後果與痕跡：不寫傳聞、江湖史、推線）；獎勵只給不扣，不准比這則「有檢定或打仗的開放選項」多（俠寇選項不算，
        同 check_free_text），作惡那一種不准比原事件的作惡選項多（俠寇選項也算）、扣的是善名（第 8 件 a）。敘事不寫阿拉伯數字。"""
        outs = ev.free_text.outcomes
        fw = f"{where} 隨口應對分岔"
        # 只在分岔開著時才有的那一顆（人拉犁，PM 2026-10-25 第 7 件）：要寫後果；關著的季沒有這一顆，effect／fail_effect 沒人用、不准寫
        need(not ev.free_text.outcomes_only or bool(outs), f"{fw}：outcomes_only 要寫 outcomes")
        need(not ev.free_text.outcomes_only or (ev.free_text.effect == Effect() and ev.free_text.fail_effect == Effect()),
             f"{fw}：outcomes_only 的隨口應對只在分岔開著時才有，effect／fail_effect 不寫")
        if not outs:
            return
        evil = [o for o in outs if o.evil]
        plain = len(outs) - len(evil)
        need(OUTCOMES_MIN <= plain <= OUTCOMES_MAX, f"{fw}：後果要 {OUTCOMES_MIN}～{OUTCOMES_MAX} 種（作惡那一種另算），有 {plain} 種")
        need(len(evil) <= 1, f"{fw}：作惡的後果最多一種，有 {len(evil)} 種")
        ids = [o.id for o in outs]
        need(all(ids) and len(set(ids)) == len(ids), f"{fw}：後果的 id 是空的或重複（{ids}）")
        evil_choices = [ch for ch in ev.choices if ch.effect.stats.get("evil", 0) > 0]
        need(not evil or bool(evil_choices), f"{fw}：原事件沒有作惡的固定選項，不能有作惡的後果")
        open_choices = [ch for ch in ev.choices if ch.needs is None]
        graded = [ch for ch in open_choices if ch.check is not None or ch.combat] or open_choices
        diffs = [ch.check.difficulty for ch in ev.choices if ch.check is not None]
        band = (min(diffs), max(diffs)) if diffs else (3, 8)
        squads = {ch.combat for ch in ev.choices if ch.combat}
        for i, o in enumerate(outs):
            ow = f"{fw} {o.id}"
            head, _, how = o.tag.partition("：")
            need(bool(head.strip() and how.strip()), f"{ow}：tag 要寫成「類名：怎麼做」（{o.tag!r}）")
            need(not OUTCOME_DIGITS.search(o.tag), f"{ow}：tag 不寫阿拉伯數字")
            for label, eff in (("effect", o.effect), ("fail_effect", o.fail_effect)):
                check_effect(f"{ow} {label}", eff, outcome=True)
                known(f"{ow} {label}", eff.stats, FREE_TEXT_REWARDS, "隨口應對的獎勵屬性")
                extra = [
                    name for name, info in Effect.model_fields.items()
                    if name not in OUTCOME_EFFECT_FIELDS and getattr(eff, name) != info.get_default(call_default_factory=True)
                ]
                need(not extra, f"{ow} {label}：後果的效果只准寫 {'、'.join(sorted(OUTCOME_EFFECT_FIELDS))}"
                                f"（公開的只有後果與痕跡），不能有 {'、'.join(extra)}")
                need(not OUTCOME_DIGITS.search(eff.text), f"{ow} {label}：敘事裡不寫阿拉伯數字（數字只能是引擎的）")
            need(not o.fail_effect.marks and not o.fail_effect.contribution, f"{ow} fail_effect：失手不留痕跡、不記貢獻")
            if i == len(outs) - 1:
                need(
                    o.kind == "fallback" and bool(o.effect.text) and not o.effect.stats and not o.effect.marks
                    and not o.effect.contribution and not o.effect.stamina and o.fail_effect == Effect(),
                    f"{ow}：最後一種要是對不上時的 fallback（只寫結果那一句：不寫判法、獎勵、體力、痕跡、貢獻、失手）",
                )
                continue
            need(o.kind != "fallback", f"{ow}：判法要寫一種（check／combat／cost）；只有最後一種是 fallback")
            if o.check is not None:
                known(ow, o.check.stats if o.check.stat == BEST_OF else [o.check.stat], OUTCOME_CHECK_STATS, "檢定屬性")
                need(band[0] <= o.check.difficulty <= band[1],
                     f"{ow}：難度 {o.check.difficulty} 要在這則固定選項的帶子 {band[0]}～{band[1]} 裡")
                if o.check.practice:
                    known(ow, [o.check.practice], c.config.practice_bonus, "熟練（config.practice_bonus）")
            if o.combat is not None:
                known(ow, [o.combat], c.squads, "敵方隊伍")
                need(o.combat in squads, f"{ow}：combat {o.combat} 要是這則事件固定選項裡打的隊伍（{sorted(squads)}）")
            if o.cost is not None:
                need(set(o.cost) == {"silver"} and o.cost["silver"] > 0, f"{ow}：cost 只能是正的 silver（{o.cost}）")
                need(o.fail_effect == Effect(), f"{ow}：掏錢的後果必成（企劃者第 8 件 c），不寫 fail_effect")
            else:
                need(bool(o.fail_effect.text), f"{ow}：check／combat 要寫 fail_effect 的那一句")
            need(bool(o.effect.text), f"{ow}：effect 要寫結果那一句")
            need(bool(o.effect.marks), f"{ow}：每一種後果都要留一個痕跡")
            for key in o.effect.marks:
                need(key.partition(":")[0] in ev.locations, f"{ow}：痕跡 {key} 要留在這則事件的地點（{'、'.join(ev.locations)}）")
            for key, delta in o.effect.stats.items():
                need(delta > 0 or (key == "good" and delta < 0),
                     f"{ow}：effect 的 {key} {delta:+d}：後果的效果只給不扣（掏錢寫 cost，扣善名的是作惡那一種）")
            rivals, rival_word = (evil_choices, "原事件的作惡選項") if o.evil else (graded, "有檢定或打仗的開放選項")
            for key in FREE_TEXT_REWARDS:
                got = o.effect.stats.get(key, 0)
                best = max((ch.effect.stats.get(key, 0) for ch in rivals), default=0)
                need(got <= max(best, 0), f"{ow}：{key} +{got} 比{rival_word}最多的 +{best} 還多")
            if o.evil:
                need(o.effect.contribution == 0, f"{ow}：作惡的後果不記貢獻")
            else:
                need(o.effect.contribution >= 1, f"{ow}：每一種後果都記貢獻（1～6）")

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
        f"config.chaos_low 不能大於 chaos_high（{cfg.chaos_low} > {cfg.chaos_high}：亂局的區間是空的）",
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
    unreachable = set(c.materials) - _material_sources(c)
    if not (c.config.four_tiers.enabled and (c.config.economy.upgrade or c.config.checkin.enabled)):
        # FB-340：素材四階或升階關著時四階料拿不到是預期的（四階料是內容收不回的，設計 10.1：關著時九件神器實際上打不出來），不擋載入
        unreachable = {mid for mid in unreachable if c.materials[mid].tier < 4}
    unreachable = sorted(unreachable)
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
    need(bool(names.weapon), "craft_names.weapon 不能是空的")
    need(bool(names.armor), "craft_names.armor 不能是空的")
    count = len(c.materials)  # 一般組合的名字照素材的位置取字（打造隱藏配方設計 4.1）：前 count 個字要夠、不能重複，名字才不會撞
    for field in ("prefixes", "weapon", "armor"):
        chars = getattr(names, field)[:count]
        need(len(chars) == count and len(set(chars)) == count,
             f"craft_names.{field} 至少要 {count} 個不重複的字（一般組合的名字照素材的位置取字；新素材加在 materials.json 最後）")
    for prefix in names.prefixes:
        for middle in names.weapon:
            for kind, noun in WEAPON_NOUNS.items():
                weapon_name = prefix + middle + noun
                reason = name_problem(weapon_name, c) or weapon_kind_problem(kind, weapon_name)
                need(reason is None, f"craft_names.weapon 組出的兵器名「{weapon_name}」過不了命名過濾：{reason}")
    for prefix in names.prefixes:
        for middle in names.armor:
            for noun in sorted(set(ARMOR_FORGE_NOUNS.values())):
                armor_name = prefix + middle + noun
                reason = name_problem(armor_name, c) or armor_word_problem(armor_name)
                need(reason is None, f"craft_names.armor 組出的防具名「{armor_name}」過不了命名過濾：{reason}")
    for word in c.banned_names:
        need(bool(word.strip()), "banned_names 裡有空字串")
    check_check_voice(c, need)
    check_insight_scenes(c, need)
    check_insight_strong(c, need)
    check_terrain_arts(c, need)
    check_faction_choices(c, need)
    check_front_lines(c, need)
    check_combat_lines(c, need)
    check_shop_lines(c, need)
    # 功能包自己的內容（商城的商品，原本的 check_mall；擂台的場邊事件，原本在 check_art 下一行的 check_arena_crowd，全部拆包第 12 批）
    check_features(c, need)
    check_art(c, need)
    check_attributes(c, need)
    check_traits(c, need)
    check_signature_arts(c, need)
    # 沒寫 drops 的對手走 materials.py 依難度的預設掉落表，所以每一階都得有素材可挑。
    # 只看預設表會掉的階（一到三階）：四階是神器的料，掉落表不給（正式季整合 4.5），測試內容也沒有
    for tier in sorted({t for _, rolls in DEFAULT_DROPS for t, _ in rolls}):
        need(
            any(m.tier == tier for m in c.materials.values()),
            f"content/materials.json 沒有任何第 {tier} 階（{TIER_NAMES[tier]}）的素材，預設掉落表會挑不到東西",
        )

    for ev in c.events.values():
        where = f"事件 {ev.id}"
        known(where, ev.locations, c.locations, "地點")
        check_condition(where, ev.condition, after_fight=ev.actions == ["train"])
        need(
            any(ch.condition == Condition() for ch in ev.choices),
            f"{where}：至少要有一個沒有條件的選項，否則玩家可能卡住",
        )
        for i, ch in enumerate(ev.choices):
            cw = f"{where} 選項{i}"
            check_condition(cw, ch.condition)
            check_effect(cw, ch.effect)
            check_effect(cw, ch.fail_effect)
            # 奇遇給寶物、良駒（裝備四欄 6.4）只准一次性的事件：可以重複遇到的事件寫了，等於每遇一次送一件、或每遇一次換 dup_silver 兩
            # （涿郡「馬市試騎」sc_zhuo_horse 就是這種；沒標 once 的奇遇看過也照樣留著，所以看 once、不看 qiyu）。計畫「要 PM 定的」第 5 條
            need(ev.once or (ch.effect.gear is None and ch.fail_effect.gear is None),
                 f"{cw}：gear 只能寫在一次性的事件（once: true）——可以重複遇到的事件寫了，等於每遇一次送一件")
            if ch.combat:
                known(cw, [ch.combat], c.squads, "敵方隊伍")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")
                if ch.check.practice:
                    known(cw, [ch.check.practice], c.config.practice_bonus, "熟練（config.practice_bonus）")
        read_marks_in(where, ev.text)
        if ev.free_text is not None:
            check_free_text(where, ev)
            check_outcomes(where, ev)
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
    # 串接（next_event）不看 once：Game._present 照樣叫出看過的事件（只標 is_repeat），所以一次性的事件只要從可以重複遇到的事件
    # 串得到（中間隔幾層都算），寫了 gear 一樣每遇一次送一件、或換一次 dup_silver 兩（裝備三終審）
    chains = {
        ev.id: [eff.next_event for ch in ev.choices for eff in (ch.effect, ch.fail_effect) if eff.next_event]
        for ev in c.events.values()
    }
    reach = [target for ev in c.events.values() if not ev.once for target in chains[ev.id]]
    chained: set[str] = set()
    while reach:
        eid = reach.pop()
        if eid in chained or eid not in c.events:
            continue
        chained.add(eid)
        reach += chains[eid]
    for eid in sorted(chained):
        need(all(ch.effect.gear is None and ch.fail_effect.gear is None for ch in c.events[eid].choices),
             f"事件 {eid}：gear 不能寫在從可以重複遇到的事件用 next_event 串得到的事件（串接不看 once，每遇一次照樣送一件）")

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
            f"{where}：不能掛在第一季的線 {th.trend}（門檻看的是原數字：開關關著時戰線沒有值；要掛就掛衍生線或一般的線）",
        )
        if th.location:
            known(where, [th.location], c.locations, "地點")
        if th.starts_battle:
            known(where, [th.starts_battle], c.battles, "戰鬥")
            need(th.starts_battle not in c.battles or not c.battles[th.starts_battle].siege, f"{where}：攻城範本不能從門檻開")
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
            need(event.starts_battle not in c.battles or not c.battles[event.starts_battle].siege,
                 f"世界事件 {event.id}：攻城範本不能從世界事件開")
    # 第一季不觸發的 beta 內容（計畫 T8、與 T4 說好的格式）：照種類各自檢查 id 存在，不跨種類比對
    off = c.scenario.season_one_off
    for kind, ids, valid, label in (
        ("thresholds", off.thresholds, {t.id for t in c.scenario.thresholds}, "門檻"),
        ("storylines", off.storylines, line_ids, "主線"),
        ("battles", off.battles, c.battles, "戰鬥"),
        ("events", off.events, c.events, "事件"),
        ("milestones", off.milestones, {m.id for m in c.scenario.milestones}, "個人目標"),
        ("world_events", off.world_events, {e.id for e in c.scenario.world_events}, "世界事件"),
        ("unlocks", off.unlocks, c.locations, "地點"),
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
        # 豪強分屬兩軍（allied）：可以依附的是劇本裡別的陣營，而且那幾軍自己不能再要依附別人
        need(all(a in scenario_faction_ids and a != faction.id for a in faction.allies),
             f"陣營 {faction.id}：allies 只能寫劇本裡別的陣營（{faction.allies}）")
        need(not any(c.scenario.find_faction(a) is not None and c.scenario.find_faction(a).allies for a in faction.allies),
             f"陣營 {faction.id}：allies 寫的陣營自己不能再有 allies")
    jf = c.config.jianfa  # 三陣營四勝利（減法季批 3c）：「此刻幫誰」就是 ally；投靠點的預設對得上劇本
    if jf.enabled:
        if any(f.allies for f in c.scenario.factions):
            from .wins import check as wins_check  # noqa: PLC0415  延後 import：wins → allied → calendar，content 不必一開始就依賴

            errors.extend(f"config.jianfa.{line}" for line in wins_check(c, jf))
    # 列傳為終點（減法季批 7b-2）：寫評曰的人物要在 characters 裡；評曰的固定句在列傳包的 check_content 驗（理由、長度、沒有數字）
    for faction in c.scenario.factions:
        need(all(cid in c.characters for cid in faction.verdict_by), f"陣營 {faction.id}：verdict_by 寫的人物不在 characters 裡（{faction.verdict_by}）")
    # 輿圖上的一個字（輿圖第三版第 3 批，FactionInk.short）：天下圖大區名底下「官 N・巾 N」照它認是哪一方，兩方同一個字就分不出來
    shorts = [f.ink.short for f in c.scenario.factions if f.ink is not None and f.ink.short]
    need(len(shorts) == len(set(shorts)), f"劇本：陣營在輿圖上的一個字（ink.short）重複了：{'、'.join(shorts)}")
    need(all(len(s) == 1 for s in shorts), f"劇本：陣營在輿圖上的一個字（ink.short）只能是一個字：{'、'.join(shorts)}")

    showdown_events ={e.id: e for e in [*c.timetable, *c.mandate_timetable] if e.kind == "showdown"}  # 含天命之爭（玉璽二）
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

    for attribute in c.config.battle.affinity:  # 三招的適性對應表（Config.battle）：打錯字的屬性名永遠用不到，載入時就報
        need(attribute in ATTRIBUTES, f"config.battle.affinity：未知的屬性 {attribute}（武學的屬性是 {'、'.join(ATTRIBUTES)}）")
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
            for key in act.text_by_lead:  # 幕文字照誰佔上風換版本（戰鬥系統 3.2）：鍵要是這場的陣營
                need(key in battle_sides, f"{aw}：text_by_lead 的鍵 {key} 不是這場的陣營")
            for option in act.options:
                if not option.free_text:  # 固定選項走三招（戰鬥系統 3.4）：要寫 move 與自己這一邊；放手一搏（free_text）不填 move
                    need(option.move is not None and option.faction in battle_sides,
                         f"{aw} 選項「{option.text}」：固定選項要寫 move 與陣營")
                if option.faction is not None:
                    known(f"{aw} 選項「{option.text}」", [option.faction], battle_sides, "陣營")
            for side in battle_sides:  # 每一幕、每一邊剛好強攻、固守、奇襲各一個固定選項（沒寫 move 的已經在上面報了）
                moves = [o.move for o in act.options if not o.free_text and o.faction == side]
                need(sorted(map(str, moves)) == sorted(MOVES), f"{aw}：{side} 要剛好有三招（強攻、固守、奇襲）各一個固定選項")
                tags = [o.tag for o in act.options if o.faction == side]
                dup = next((t for t in tags if tags.count(t) > 1), None)
                need(dup is None, f"{aw}：{side} 的選項 tag {dup} 重複（tag 是這一邊在這一幕的選項名，不能同名）")
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
        endings = [e for e in c.scenario.endings if e.season_one == season_one and not e.mandate]  # 天命結局不當保底（玉璽二）
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
    enlist = c.tutorial.enlist  # 入伍段（新手引導計畫二）：引薦人要對得上劇本的陣營、每位每一步都有收起來那一行
    if enlist is not None:
        for step in enlist.steps:
            where = f"入伍段 {step.id}"
            known(where, step.done_when.locations, c.locations, "地點")
            check_condition(where, step.done_when.condition)
        for faction_id, who in enlist.recruiters.items():
            need(faction_id in faction_ids, f"入伍段：引薦人 {who.name} 的陣營 {faction_id} 不是劇本的陣營")
            need(
                len(who.lines) == len(enlist.steps),
                f"入伍段：引薦人 {who.name}（{faction_id}）的 lines 要有 {len(enlist.steps)} 行（每一步一行），現在是 {len(who.lines)} 行",
            )
            for field, text in who.allied.items():  # 豪強分屬兩軍的季換的那幾句（Recruiter.allied）
                need(field in RECRUITER_ALLIED_FIELDS, f"入伍段：引薦人 {who.name} 的 allied 不認得 {field}（只認 {RECRUITER_ALLIED_FIELDS}）")
                need(bool(text.strip()) and to_traditional(text) == text, f"入伍段：引薦人 {who.name} 的 allied.{field} 要是繁體、不能是空的")
            texts = [who.intro, who.briefing, who.order_hint, who.done, who.rejoin, *who.lines, *who.allied.values()]
            for slot in sorted({s for text in texts for s in re.findall(r"\{[^{}]*\}", text)}):  # enlist.fill 只換這兩個（FB-502）
                need(slot in RECRUITER_SLOTS, f"入伍段：引薦人 {who.name} 的話裡 {slot} 不認得（只認 {RECRUITER_SLOTS}）")

    # ── 開局第一分鐘（減法季批 7，content/opening.json；tianxia/opening.py）──
    o = c.opening
    if o is not None:
        need(o.event in c.events, f"opening.json：事件 {o.event} 不存在")
        need(o.end in c.locations, f"opening.json：送信的終點 {o.end} 不存在")
        flags = {x.flag for x in o.senders}
        need(len(flags) == len(o.senders), "opening.json：senders 的 flag 不能重複")
        for x in o.senders:
            ch = c.characters.get(x.figure)
            need(ch is not None and ch.deep_interaction, f"opening.json：{x.figure} 要是 characters.json 裡能深交的人物")
            need(any(fig.character == x.figure for fig in c.figures.values()), f"opening.json：{x.figure} 要是大勢人物（信才寫得出他在哪）")
        if o.event in c.events:
            ev = c.events[o.event]
            need(bool(ev.choices), f"opening.json：事件 {o.event} 要有選項")
            for ch in ev.choices:
                need(any(f in flags for f in ch.effect.flags_add), f"opening.json：事件 {o.event} 的選項「{ch.text}」要帶 senders 其中一個 flag")
                need(ch.effect.next_event is None, f"opening.json：事件 {o.event} 的選項「{ch.text}」不能接 next_event（人物開口是信）")

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
            # 略過序章的人體力補滿（prologue.finish）；走出草廬的人只有這一步的獎勵補得到，補不滿兩種人離開時的體力就不一樣
            need(
                last.reward.stamina >= c.config.stamina_max,
                f"新手引導 {last.id}：出師的獎勵要把體力補滿（reward.stamina 至少 stamina_max {c.config.stamina_max}），跟略過序章一樣",
            )
    for i, step in enumerate(t.steps):
        where = f"新手引導 {step.id}"
        special = (step.explore_event or step.enemies
                   or step.force_tier or step.deepen or step.instant_rest or step.fuse_base or step.melt_only
                   or step.give_art or step.give_piece or step.paged or step.after)
        need(not special or i < t.prologue_steps, f"{where}：序章才有的欄位只能寫在前 {t.prologue_steps} 步")
        # 畫面的那幾樣（旁白、收起來那一行、亮、發光、選單）序章與初入江湖（序章之後、不分季的步驟，新手引導第四段）都可以寫
        screen = step.scene or step.line or step.reveal or step.glow or step.allow
        need(not screen or t.location is not None and (i < t.prologue_steps or not step.season_one),
             f"{where}：scene、line、reveal、glow、allow 只能寫在序章與初入江湖的步驟（第一季才有的步驟不行）")
        need(not step.paged or "\n\n" in step.text, f"{where}：paged 的話要有兩段以上（照空一行切頁）")
        # 要換掉的字只認這幾個（打錯了會原樣出現在畫面上）：話、旁白、收起來那一行是 {武學}；結果那一句（after）是 {意境}、{武學}、{心得}
        for field, allowed in (("text", {"武學"}), ("scene", {"武學"}), ("line", {"武學"}), ("after", {"意境", "武學", "心得"})):
            unknown = sorted({w for w in STEP_PLACEHOLDER.findall(getattr(step, field))} - allowed)
            need(not unknown, f"{where}：{field} 裡有不認得的要換掉的字 {unknown}（只認 {sorted(allowed)}）")
        bad = [k for k in step.reveal if k not in REVEAL_KEYS]
        need(not bad, f"{where}：reveal 不認得 {bad}")
        # 初入江湖的步驟還可以讓選單上的一顆發光（寫它的 id，同 allow 認得的；prologue.onboard_glow）
        bad = [k for k in step.glow if k not in GLOW_KEYS and (i < t.prologue_steps or not allow_known(k))]
        need(not bad, f"{where}：glow 不認得 {bad}（要是 models.GLOW_KEYS 裡的鍵；初入江湖的步驟也可以是選單 id）")
        unknown = [entry for entry in step.allow if not allow_known(entry)]
        need(
            not unknown,
            f"{where}：allow 不是選單上的行動 {unknown}（閒著的選單做得出來的 id 列在 models.ALLOW_FIXED／ALLOW_FAMILIES；"
            "引擎新加的行動要先補進那裡）",
        )
        need(step.explore_event is None or step.explore_event in c.events, f"{where}：explore_event {step.explore_event} 不存在")
        if step.explore_scene is not None:
            scene = c.insight_scenes.get(step.explore_scene)
            need(scene is not None and scene.prologue, f"{where}：explore_scene {step.explore_scene} 要是 insight_scenes.json 裡 prologue 的場景")
            need(step.explore_event is None, f"{where}：explore_event 與 explore_scene 只能寫一個")
            hut_loc = c.locations.get(t.location) if t.location else None
            if scene is not None and hut_loc is not None:
                from .insights import pool_attributes  # noqa: PLC0415
                wrong = sorted({m.attribute for m in scene.methods} - pool_attributes(hut_loc, c))
                need(not wrong, f"{where}：序章的有所感每個做法都要選得對，{wrong} 在草廬悟不到")
        known(where, step.enemies, c.squads, "對手")
        need(step.force_tier is None or step.force_tier in encounter.TIERS, f"{where}：force_tier {step.force_tier} 不是判定結果")
        for art in (step.fuse_base, step.melt_only, step.give_art.id if step.give_art else None):
            need(art is None or art in c.skills, f"{where}：武學 {art} 不存在")
    # 武學重構：序章裝意境那一步點名的那一門要收得下草廬悟得到的每個意境（相容屬性），不然新人照師父的話做會被擋
    sights: set[str] = set()
    for step in t.steps[: t.prologue_steps]:
        sights.update(step.reward.insights)
    hut_place = c.locations.get(t.location) if t.location else None
    for step in t.steps[: t.prologue_steps]:  # 有所感的草廬：每個做法悟到的就是草廬裡那個屬性的基本意境
        scene = c.insight_scenes.get(step.explore_scene or "")
        if scene is not None and hut_place is not None:
            from .insights import base_of  # noqa: PLC0415
            sights.update(i for i in (base_of(m.attribute, hut_place, c) for m in scene.methods) if i)
    todo = ([t.start_event] if t.start_event else []) + [s.explore_event for s in t.steps[: t.prologue_steps] if s.explore_event]
    seen_events: set[str] = set()
    while todo:
        event_id = todo.pop()
        if event_id in seen_events or event_id not in c.events:
            continue
        seen_events.add(event_id)
        for choice in c.events[event_id].choices:
            for effect in (choice.effect, choice.fail_effect):
                sights.update(effect.insights)
                if effect.next_event:
                    todo.append(effect.next_event)
    for step in t.steps[: t.prologue_steps]:
        base_def = c.skills.get(step.fuse_base) if step.fuse_base else None
        if base_def is not None and base_def.affinity:
            wrong = sorted(i for i in sights if i in c.insights and c.insights[i].attribute not in base_def.affinity)
            need(not wrong, f"新手引導 {step.id}：{step.fuse_base} 的相容屬性 {base_def.affinity} 收不下草廬悟得到的意境 {wrong}")
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
        # 師門教的那一門換上身，不能跟開局送的另一種相剋（FB-092：選火的新人照師父的話做就 −20%）
        attribute = recipe.attribute or (recipe_insight.attribute if recipe_insight is not None else None)
        need(recipe.attribute is None or recipe.attribute in ATTRIBUTES, f"{where}：屬性 {recipe.attribute} 不是陰陽剛柔快慢虛實之一")
        base_skill = c.skills.get(recipe.base)
        for other_id in c.config.starter_skills:
            other = c.skills.get(other_id)
            if base_skill is None or other is None or other.kind == base_skill.kind:
                continue
            need(ATTRIBUTE_COUNTERS.get(attribute) != other.attribute,
                 f"{where}：合出來屬{attribute}，跟開局送的【{other.name}】（屬{other.attribute}）相剋；師門配方寫 attribute 改掉")

    validate_secrets(c, need)
    validate_forge_secrets(c, need)
    validate_tier4_named(c, need)
    validate_named_clash(c, need)
    _validate_seal(c, need)

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
            ch.kind is not None or ch.hire_type is not None or ch.starting_wugong is None,
            f"{where}：敵人（kind 沒填）不需要 starting_wugong，那是同伴才有的欄位",
        )
        if ch.hire_type is not None or ch.hire_at is not None:  # 一般 NPC 同伴（features/hire；content/hire.json）
            need(ch.kind is None and not ch.recruitable, f"{where}：一般 NPC 同伴不寫 kind、recruitable（只在酒肆花銀兩招）")
            need(ch.hire_type in {t.key for t in c.config.hire.types}, f"{where}：hire_type {ch.hire_type} 不是 Config.hire.types 的任何一型")
            need(ch.hire_at is not None, f"{where}：一般 NPC 同伴要寫 hire_at（在哪間酒肆招）")
            known(where, [ch.hire_at] if ch.hire_at else [], c.locations, "地點")
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
        if ch.haunts:  # 人物活起來：走動範圍的第一個就是他平常在的地方（開季、退回原處都照它）
            known(where, ch.haunts, c.locations, "地點")
            need(ch.haunts[0] == (ch.talk_at or ch.recruit_at), f"{where}：haunts 的第一個要是 talk_at／recruit_at")
            need(ch.follows is None, f"{where}：跟著別人走（follows）的人物不寫自己的 haunts")
        if ch.follows is not None:
            known(where, [ch.follows], c.characters, "人物")
            leader = c.characters.get(ch.follows)
            need(leader is None or leader.follows is None, f"{where}：follows 的 {ch.follows} 自己也在跟著別人走")
        if ch.side is not None:
            known(where, [ch.side], [f.id for f in c.scenario.factions], "陣營")
    for squad in c.squads.values():
        where = f"敵方隊伍 {squad.id}"
        need(squad.difficulty >= 0, f"{where}：difficulty 不能是負的")

    front_ids = sorted(region_fronts)  # 戰線 id 照 T1 的大區 front，不另寫一份清單
    check_timetable(c, need, known, front_ids, trend_ids)
    check_figures(c, need, known, front_ids)
    stance_events: dict[str, str] = {}  # 人物心意開的事件 → 開它的心意（一則事件只掛一個心意）
    for fid, fig in c.figures.items():  # 勸降成了立的痕跡（減法季批 6，FB-827）也算「有效果寫它」：痕跡規則讀它
        for d in fig.errands:
            for key in (d.persuade.marks if d.persuade is not None else {}):
                marks_written.setdefault(key, f"大勢人物 {fid} 的託付 {d.id}")
        for x in fig.stances:
            if x.action.event_daily is not None:
                first = stance_events.setdefault(x.action.event_daily, f"{fid}:{x.id}")
                need(first == f"{fid}:{x.id}", f"大勢人物 {fid} 的心意 {x.id}：事件 {x.action.event_daily} 已經掛在 {first}")
    check_relations(c, need, known)
    check_itineraries(c, need, known)
    check_companions(c, need)
    check_foreshadows(c, need, known, region_ids, front_ids, counters_written)
    check_orders(c, need, known, front_ids)
    check_promotions(c, need, known)
    check_opportunities(c, need, known, front_ids)
    check_duels(c, need, known)
    check_gear(c, need, known)
    check_signature_arms(c, need, known)
    check_bounties(c, need)
    check_core_loop(c, need)
    check_territory(c, need, known, front_ids)
    check_conquest_blocks(c, need, known, front_ids)
    check_siege_templates(c, need)
    check_storylines(c, need)
    for ev in c.events.values():  # 事件分級：第二、三階要寫從哪一道門進來，第一階不寫門；第二、三階的難度帶（事件分級設計稿）
        need((ev.tier == 1) == (ev.door is None), f"事件 {ev.id}：第二、三階要寫 door，第一階不寫（tier {ev.tier}、door {ev.door}）")
        low, high = TIER_BANDS.get(ev.tier, (None, None))
        checks = [ch.check for ch in ev.choices] + ([o.check for o in ev.free_text.outcomes] if ev.free_text else [])
        for check in checks:
            if check is not None and low is not None:
                need(low <= check.difficulty <= high, f"事件 {ev.id}：第 {ev.tier} 階的難度要在 {low}～{high}（寫了 {check.difficulty}）")

    # 地方痕跡過門檻（減法季整合設計 5.2；主機側計畫 Task 4-3，content/mark_rules.json）：一個痕跡一條規則，算「有人讀」；
    # 過門檻那一刻的傳聞、之後地點描寫多接的那一段都要寫（〈天下形勢〉與江湖史沒寫就照傳聞那一句）；推的線同事件效果的規矩
    rule_marks: dict[str, str] = {}
    for rule in c.mark_rules:
        rw = f"痕跡規則 {rule.mark}"
        check_mark_key(rw, rule.mark)
        need(rule.mark not in rule_marks, f"{rw}：重複（一個痕跡只寫一條規則）")
        rule_marks.setdefault(rule.mark, rw)
        marks_read.setdefault(rule.mark, rw)
        for name in ("describe", "rumor"):
            need(bool(getattr(rule, name).strip()), f"{rw}：{name} 要寫（過門檻那一刻的地方傳聞、之後地點描寫多接的那一段）")
        for name in ("describe", "rumor", "xingshi", "chronicle"):
            need(not OUTCOME_DIGITS.search(getattr(rule, name)), f"{rw}：{name} 不寫阿拉伯數字（數字只能是引擎的）")
        known(rw, rule.trend, trend_ids | {FRONT_KEY}, "大勢線")
        front_needs_total(rw, rule.trend)
        not_derived(rw, rule.trend)
        need(all(rule.trend.values()), f"{rw}：trend 的量不能是 0")
    for key, where in sorted(outcome_marks.items()):
        need(key in rule_marks,
             f"{where}：痕跡 {key} 是分岔的後果寫的，要有一條痕跡規則讀它（content/mark_rules.json：過門檻換地點描寫、發傳聞）")
    for loc in c.locations.values():
        for text in loc.desc_marks:
            lw = f"地點 {loc.id} 的 desc_marks"
            check_mark_key(lw, text.mark)
            need(text.mark.partition(":")[0] == loc.id, f"{lw}：痕跡 {text.mark} 要是這個地點（{loc.id}）的")
            need(bool(text.text.strip()) and not OUTCOME_DIGITS.search(text.text), f"{lw}：{text.mark} 那一段是空的或寫了阿拉伯數字")
            marks_read.setdefault(text.mark, lw)

    for key, where in sorted(marks_written.items()):
        need(key in marks_read, f"{where}：痕跡 {key} 寫了卻沒有任何條件或文字讀它")
    for key, where in sorted(marks_read.items()):
        need(key in marks_written, f"{where}：痕跡 {key} 沒有任何效果寫它，條件永遠不會成立")

    # 玩家拿得到的內容武學品質要明寫（PM 2026-10-14：追風步沒寫 quality，照 SkillDef 的預設成了絕學，
    # 付四十兩就學得到）：事件 learn_skills 給的、各地教的（learn）、開局送的（starter_skills）
    for skill_id in sorted(set(taught) | {s.id for s in c.skills.values() if s.learn is not None} | set(c.config.starter_skills)):
        skill = c.skills.get(skill_id)
        if skill is not None:
            need("quality" in skill.model_fields_set,
                 f"{taught.get(skill_id, '教得到的武學')}：【{skill.name}】（{skill_id}）沒寫 quality，會照預設成了絕學——玩家拿得到的武學品質要明寫")

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))


def _validate_seal(c: Content, need) -> None:
    """玉璽碎片（玉璽碎片設計 13.4、8.5）：係數都不超過 1（一場最多 cap）；沒有 content/seal.json 可以（碎片關著：時刻表的標記與
    emerge_skill 都不檢查——測試內容沒有混元一氣，預設的 emerge_skill 不能讓它載入失敗）；有就 emerge_skill 認得、剛好七片、名字不重複、
    效果鍵在 Config.seal.effects（改版的 effects 在 Config.seal.revamp.effects）、名字過命名過濾；時刻表不是空的時標 emerge 的剛好一件、標了 seal 的都是決戰。
    天命之爭（玉璽二）：最多一件、是決戰、沒標 seal、有它的戰鬥、mandate_endings 指到交戰兩軍與標了 mandate 的結局；標了 mandate 的結局都有人指。"""
    cfg = c.config.seal
    for label, table in (("side_factor", cfg.side_factor), ("take_share", cfg.take_share)):
        need(all(0 <= v <= 1 for v in table.values()), f"Config.seal.{label}：係數不能超過 1（一場被奪最多 cap）")
    if not c.seal:
        return
    need(cfg.emerge_skill is None or cfg.emerge_skill in c.skills, f"Config.seal.emerge_skill：{cfg.emerge_skill} 不是內容裡的武學")
    need(len(c.seal) == 7, f"content/seal.json：要剛好七片，現在 {len(c.seal)} 片")
    need(len({s.name for s in c.seal.values()}) == len(c.seal), "content/seal.json：七片的名字要不重複")
    for shard in c.seal.values():
        need(shard.effect in cfg.effects, f"content/seal.json：{shard.id} 的效果 {shard.effect} 不在 Config.seal.effects")
        for key in shard.effects:  # 改版的常駐效果（玉璽碎片改版第三章）：開關關著也檢查，打開那一刻不會才發現內容寫錯
            need(key in cfg.revamp.effects, f"content/seal.json：{shard.id} 的改版效果 {key} 不在 Config.seal.revamp.effects")
        problem = name_problem(shard.name, c)
        need(problem in (None, SEAL_CLASH), f"content/seal.json：{shard.id} 的名字「{shard.name}」{problem}")
    acts = [shard.act for shard in c.seal.values() if shard.act is not None]  # 獨門行動（改版第 2 批）：一種只給一片
    need(len(acts) == len(set(acts)), f"content/seal.json：同一種獨門行動只能給一片（{acts}）")
    mandates = c.mandate_timetable  # 天命之爭（玉璽二；8.3、8.5）
    need(len(mandates) <= 1, "時刻表：標 mandate_only 的天命之爭最多一件")
    endings = {e.id: e for e in c.scenario.endings}
    for event in mandates:
        where = f"時刻表 {event.id}（天命之爭）"
        need(event.kind == "showdown" and event.seal is None, f"{where}：天命之爭要是決戰、不能標 seal（它本身不璽動）")
        battle = next((b for b in c.battles.values() if b.timetable_event == event.id), None)
        need(battle is not None, f"{where}：battles.json 要有一筆 timetable_event 是 {event.id} 的戰鬥")
        armies = {f.id for f in battle.factions} if battle is not None else set()
        need(bool(event.mandate_endings) and set(event.mandate_endings) <= armies, f"{where}：mandate_endings 的鍵要是交戰兩軍")
        for side, ending_id in event.mandate_endings.items():
            ending = endings.get(ending_id)
            need(ending is not None and ending.mandate and ending.season_one,
                 f"{where}：{side} 的結局 {ending_id} 要是劇本裡標了 mandate 的第一季結局")
    for ending in c.scenario.endings:
        if ending.mandate:
            need(any(ending.id in e.mandate_endings.values() for e in mandates), f"結局 {ending.id}：標了 mandate 卻沒有天命之爭指到它")
            need(ending.condition == Condition() and not (ending.stance_min or ending.stance_max or ending.stance_top),
                 f"結局 {ending.id}：天命結局不寫條件與態勢（照天命之爭的結果挑）")
    if not c.timetable:
        return
    marked = [e for e in c.timetable if e.seal is not None]
    need(all(e.kind == "showdown" for e in marked), "時刻表：seal 只能標在決戰（kind 是 showdown）")
    need(sum(1 for e in marked if e.seal == "emerge") == 1, "時刻表：標 seal: emerge 的決戰要剛好一件")
