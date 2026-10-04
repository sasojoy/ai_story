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
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .companion_agent import DIALOGUE_TAGS
from .materials import TIER_NAMES
from .models import (
    ROADS, STATS, BattleDef, CharacterDef, Condition, Config, Content, CraftNames, Effect, Event, Location,
    MapLayout, Material, RoadSight, Scenario, Sect, SimRumor, SkillDef, Squad, TimetableEvent, Tutorial,
)
from .zh import to_traditional

ROAD_SIGHTS_PER_SPOT = 2  # 路上見聞：每一種路、每一個大區的組合至少要有幾則可挑（路上設計第五節）
ROAD_SIGHT_CAPS = {"silver": 10, "xinde": 5}  # 路上見聞的小收穫上限
TERRAIN_SIZE = (8, 40)  # 山脈、丘陵的山頭高度範圍（輿圖美術設計第四節）
# 時刻表的戰況鍵先也認這幾條：三條戰線與豪強割據由 T1（地圖擴充開發）加進 scenario 的 trends，T2 跟它平行開發。
# T1 併進來之後拿掉，只認劇本裡的大勢線（時刻表推一條劇本沒有的線時 timetable 直接略過）。
SEASON_ONE_TRENDS = {"yingru", "nanyang", "jizhou", "geju"}
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
        materials=_index(Material, _read(root / "materials.json")),
        craft_names=CraftNames(**_read(root / "craft_names.json")),
        banned_names=_read(root / "banned_names.json"),
        sects=_index(Sect, _read(root / "sects.json")),
        characters=_index(CharacterDef, _read(root / "characters.json")),
        squads=_index(Squad, _read(root / "squads.json")),
        battles=_index(BattleDef, _read(root / "battles.json")) if (root / "battles.json").exists() else {},
        road_sights=_index(RoadSight, _read(root / "road_sights.json")),
        timetable=[_build(TimetableEvent, raw) for raw in _read(root / "timetable.json")]
        if (root / "timetable.json").exists() else [],
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
FREE_TEXT_REWARDS = ("silver", "fame", "good", "xinde", "str", "agi", "con", "wis")  # 隨口應對的獎勵不能超過檢定選項的這幾項


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
    """所有拿得到的素材 id：地點撿、對手掉（含依難度的預設表）、事件給。"""
    from .materials import _default_rolls, by_tier  # noqa: PLC0415  延後 import，避免循環依賴

    reachable: set[str] = set()
    for loc in c.locations.values():
        reachable |= set(loc.materials)
        if not loc.materials and loc.tags:
            reachable |= {m.id for m in by_tier(c, 1)}  # 沒填 materials 的地點給隨機一階素材
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


def check_timetable(c: Content, need, known, region_ids: list[str], trend_ids: set[str]) -> None:
    """時刻表（content/timetable.json，計畫 T2）：戰線是大區 id（不檢查是不是大勢線，三條戰線是 T1 加的）、
    結果鍵照種類齊全、鎖定對得到結果、人物與修正的對象存在、文字只用繁體中文。人物先認 characters.json 的 id，
    T4 的人物表進來後改認它。"""
    ids = [e.id for e in c.timetable]
    duplicated = sorted({eid for eid in ids if ids.count(eid) > 1})
    need(not duplicated, f"時刻表 id 重複：{'、'.join(duplicated)}")
    trends = trend_ids | SEASON_ONE_TRENDS
    earlier: dict[str, TimetableEvent] = {}
    order = {e.id: i for i, e in enumerate(c.timetable)}
    rolled = {e.id for e in c.timetable if e.roll_side is not None}

    def check_text(where: str, text: str | None) -> None:
        if text:
            need(to_traditional(text) == text, f"{where}：文字只能用繁體中文（「{text[:12]}…」）")

    def check_figure(where: str, key: str, change) -> None:
        if key.startswith("@commander:"):
            front, _, side = key.removeprefix("@commander:").partition(":")
            known(where, [front], region_ids, "大區")
            need(side in TIMETABLE_SIDES, f"{where}：{key} 的那一方只能是 guan 或 huang")
        else:
            known(where, [key], c.characters, "人物")
        if change.front is not None:
            known(where, [change.front], region_ids, "大區")
        if change.location is not None:
            known(where, [change.location], c.locations, "地點")
        if change.fate == "到任":
            need(change.front is not None and change.location is not None, f"{where}：{key} 到任要寫 front 與 location")
        known(where, change.only_if, c.characters, "人物")
        known(where, change.only_if.values(), region_ids, "大區")
        check_text(where, change.note)

    for ev in c.timetable:
        where = f"時刻表 {ev.id}"
        need(ev.week <= c.config.season_weeks, f"{where}：第 {ev.week} 週超出季曆的 {c.config.season_weeks} 週")
        if ev.front is not None:
            known(where, [ev.front], region_ids, "大區")
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
            known(where, [ev.skip_if_out], c.characters, "人物")
        versions = list(dict.fromkeys(ev.versions.values()))
        base = TIMETABLE_KEYS.get(ev.kind)
        if base is not None:  # 季末的結局句由 T9 寫在劇本的結局裡
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
        check_text(where, ev.third_party_text)
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
            for text in (outcome.text, outcome.note, outcome.chronicle, outcome.third_party_text,
                         *outcome.locked_text.values(), *outcome.loser_text.values()):
                check_text(ow, text)
        earlier[ev.id] = ev


def validate(c: Content) -> None:
    errors: list[str] = []
    trend_ids = {t.id for t in c.scenario.trends}
    hidden = {t.id for t in c.scenario.trends if t.hidden}

    def need(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    def known(where: str, keys, valid, kind: str) -> None:
        for key in keys:
            need(key in valid, f"{where}：未知的{kind} {key}")

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
        known(where, [*cond.revealed_all, *cond.revealed_none], trend_ids, "大勢線")
        known(where, cond.members_none, c.characters, "人物")
        for sub in cond.any_of:
            check_condition(where, sub)

    def check_effect(where: str, eff: Effect) -> None:
        for key, n in eff.marks.items():
            check_mark_key(where, key)
            need(1 <= n <= 3, f"{where}：痕跡 {key} 一次只能加 1～3（不能減）")
            marks_written.setdefault(key, where)
        read_marks_in(where, eff.text)
        known(where, eff.stats, STATS, "屬性")
        known(where, eff.learn_skills, c.skills, "武學")
        known(where, eff.materials, c.materials, "素材")
        known(where, eff.trend, trend_ids, "大勢線")
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
        known(where, loc.enemies, c.squads, "敵方隊伍")
        known(where, loc.train_trend, trend_ids, "大勢線")
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

    # 煉製的決定性組名字表（LLM 不可用時的退路）：不能是空的，而且組出來的每一個名字都得
    # 通過命名過濾——這條退路一定會被走到（整季模擬把 LLM mock 掉），組出壞名字會永久登記。
    from .craft import name_problem  # noqa: PLC0415  延後 import，避免 content <-> craft 互相依賴

    names = c.craft_names
    need(bool(names.prefixes), "craft_names.prefixes 不能是空的")
    need(bool(names.wugong), "craft_names.wugong 不能是空的")
    need(bool(names.neigong), "craft_names.neigong 不能是空的")
    for prefix in names.prefixes:
        for suffix in [*names.wugong, *names.neigong]:
            reason = name_problem(prefix + suffix, c)
            need(reason is None, f"craft_names 組出的名字「{prefix + suffix}」過不了命名過濾：{reason}")
    for word in c.banned_names:
        need(bool(word.strip()), "banned_names 裡有空字串")
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

    region_ids = [region.id for region in c.map.regions]
    duplicated = sorted({rid for rid in region_ids if region_ids.count(rid) > 1})
    need(not duplicated, f"大區 id 重複：{'、'.join(duplicated)}")
    for region in c.map.regions:
        where = f"大區 {region.id}"
        known(where, region.trends, trend_ids, "大勢線")
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
        for stat, amount in eff.stats.items():
            cap = ROAD_SIGHT_CAPS.get(stat)
            need(cap is not None and 0 < amount <= cap, f"{where}：stats 只能是銀兩 1～10 或心得 1～5（寫的是 {stat} {amount}）")
        known(where, eff.materials, c.materials, "素材")
        for mid, count in eff.materials.items():
            if mid in c.materials:
                need(count == 1 and c.materials[mid].tier == 1, f"{where}：素材只能是一階 1 個（寫的是 {mid} ×{count}）")

    for th in c.scenario.thresholds:
        where = f"門檻 {th.id}"
        known(where, [th.trend], trend_ids, "大勢線")
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
        if sim.requires_revealed:
            known(where, [sim.requires_revealed], trend_ids, "大勢線")
        known(where, sim.haunts, c.locations, "地點")
        for rumor in sim.rumors:
            if isinstance(rumor, SimRumor):
                known(f"{where} 的傳聞「{rumor.text}」", [rumor.location], c.locations, "地點")
        check_condition(where, sim.condition)
    for ending in c.scenario.endings:
        check_condition(f"結局 {ending.id}", ending.condition)

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

    scenario_faction_ids = [f.id for f in c.scenario.factions]
    need(len(set(scenario_faction_ids)) == len(scenario_faction_ids), "劇本：陣營 id 重複")
    for faction in c.scenario.factions:
        known(f"陣營 {faction.id}", faction.join_at, c.locations, "地點")
        known(f"陣營 {faction.id}", faction.sects, c.sects, "門派")
        known(f"陣營 {faction.id}", faction.goals, trend_ids, "大勢線")
        need(all(d in (-1, 1) for d in faction.goals.values()), f"陣營 {faction.id}：goals 的方向只能是 1 或 -1")

    for battle in c.battles.values():
        where = f"戰鬥 {battle.id}"
        faction_ids = [f.id for f in battle.factions]
        need(len(set(faction_ids)) == len(faction_ids), f"{where}：陣營 id 重複")
        if scenario_faction_ids:
            known(where, faction_ids, scenario_faction_ids, "陣營")
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
                    known(f"{aw} 選項「{option.text}」", [option.faction], faction_ids, "陣營")
        need(
            battle.free_text_gamble is not None or not any(o.free_text for a in battle.acts for o in a.options),
            f"{where}：有 free_text 選項，必須設定 free_text_gamble",
        )
        for outcome in battle.outcomes:
            known(f"{where} 結果「{outcome.title}」", [outcome.faction], faction_ids, "陣營")
            known(f"{where} 結果「{outcome.title}」", outcome.trend_delta, trend_ids, "大勢線")
        need(
            battle.outcomes[-1].trend_min is None and battle.outcomes[-1].trend_max is None,
            f"{where}：最後一個結果必須沒有數值門檻（作為保底結果，一定要能命中）",
        )

    last = c.scenario.endings[-1] if c.scenario.endings else None
    need(
        last is not None and last.condition == Condition() and last.storyline is None,
        "劇本的最後一個結局必須沒有條件、也不限主線（作為保底結局）",
    )

    for milestone in c.scenario.milestones:
        check_condition(f"個人目標 {milestone.id}", milestone.condition)
    for step in c.tutorial.steps:
        where = f"新手引導 {step.id}"
        known(where, step.done_when.locations, c.locations, "地點")
        check_condition(where, step.done_when.condition)
        check_effect(where, step.reward)

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
    for squad in c.squads.values():
        where = f"敵方隊伍 {squad.id}"
        need(squad.difficulty >= 0, f"{where}：difficulty 不能是負的")

    check_timetable(c, need, known, region_ids, trend_ids)

    for key, where in sorted(marks_written.items()):
        need(key in marks_read, f"{where}：痕跡 {key} 寫了卻沒有任何條件或文字讀它")
    for key, where in sorted(marks_read.items()):
        need(key in marks_written, f"{where}：痕跡 {key} 沒有任何效果寫它，條件永遠不會成立")

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
