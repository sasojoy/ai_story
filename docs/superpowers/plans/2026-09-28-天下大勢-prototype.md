# 《天下大勢》原型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出一個可在瀏覽器遊玩的純文字武俠原型：江南一個大區、體力制行動、文字事件選擇、自動與關鍵戰鬥、兩條大勢線（一公開一隱藏）與虛擬玩家，用來驗證設計文件第十三節的三個核心問題。

**Architecture:** `tianxia/` 是不依賴任何 UI 的純 Python 規則引擎（Pydantic 模型 + 小模組），`content/` 是 JSON 內容檔，`app.py` 是 Gradio 介面，只負責顯示與接線。引擎的時間由呼叫端推進（`advance(seconds)` / `sync(now)`），所以測試與「時間快轉」都不必真的等待。

**Tech Stack:** Python 3.14、Pydantic 2、Gradio 5 以上、pytest。

**Spec:** `docs/superpowers/specs/2026-09-27-天下大勢-design.md`

## Global Constraints

- 所有玩家看得到的文字一律使用**繁體中文**。
- 武學、人物、秘笈名稱**全部原創**，不得使用金庸等作品的專有名詞（設計文件第二節）。
- 遊戲執行時**不接 LLM**；所有數值由規則引擎決定（設計文件第十一節）。
- `tianxia/` 底下的任何模組都**不得 import gradio**。規則引擎必須能單獨測試與重用。
- 內容檔是 UTF-8 JSON；內容檔有誤時，載入就要報錯並指出是哪個檔案的哪個 id。
- 虛擬環境：`.venv`；在 Git Bash 執行指令時使用 `.venv/Scripts/python.exe`。
- 原型**不做**：幫派、地盤、PK、陣法、流派套裝、同伴、門派晉升、跨季傳承、多大區、真正的多人連線（設計文件 13.5）。
- 參考專案 `C:\Ray\專案\ai遊戲` 的教訓：狀態、規則、內容載入從一開始就分模組，不要做出上帝物件。

## File Structure

```
天下大勢/
├── app.py                    # Gradio 介面（Task 11）
├── requirements.txt          # 依賴（Task 1）
├── pyproject.toml            # pytest 設定（Task 1）
├── README.md / CLAUDE.md     # 說明（Task 11）
├── .claude/launch.json       # 預覽設定（Task 11）
├── tianxia/
│   ├── __init__.py
│   ├── models.py             # 內容資料模型（Task 1）
│   ├── content.py            # 載入與交叉驗證內容檔（Task 2）
│   ├── state.py              # 執行期狀態模型（Task 3）
│   ├── rules.py              # 條件、效果、檢定、武學經驗（Task 3）
│   ├── events.py             # 事件抽選與選項標籤（Task 4）
│   ├── combat.py             # 相剋、自動戰鬥、關鍵戰鬥（Task 5）
│   ├── world.py              # 大勢門檻、虛擬玩家、結局（Task 6）
│   ├── engine.py             # Game 門面：行動、選項、時間、畫面文字（Task 7、8）
│   ├── save.py               # 存讀檔（Task 8）
│   └── bot.py                # 亂數機器人，用於整季測試與平衡模擬（Task 10）
├── content/                  # 正式內容（Task 9、10）
│   ├── config.json  scenario.json  locations.json
│   ├── skills.json  sects.json  enemies.json
│   └── events/ general.json  kou.json  treasure.json  sects.json
├── scripts/simulate.py       # 平衡模擬（Task 10）
└── tests/
    ├── conftest.py
    ├── fixtures/content/     # 測試用的迷你內容（Task 2）
    └── test_*.py
```

---

### Task 1: 專案骨架與內容資料模型

**Files:**
- Create: `requirements.txt`, `pyproject.toml`, `.gitignore`, `tianxia/__init__.py`, `tianxia/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `tianxia.models` 中的 `STATS`、`Condition`、`Effect`、`Check`、`Choice`、`Event`、`Location`、`Skill`、`Sect`、`Enemy`、`Trend`、`Threshold`、`SimPlayer`、`Ending`、`Scenario`、`Config`、`Content`（欄位如下方程式碼）。

- [ ] **Step 1: 建立專案檔與虛擬環境**

`requirements.txt`:
```
pydantic>=2.6
gradio>=5.0
pytest>=8.0
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
saves/
```

`tianxia/__init__.py`:
```python
"""《天下大勢》規則引擎。不依賴任何介面，可單獨測試與重用。"""
```

Run:
```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: 安裝成功，無錯誤。

- [ ] **Step 2: Write the failing test**

`tests/test_models.py`:
```python
import pytest
from pydantic import ValidationError

from tianxia.models import Choice, Config, Event, Location


def test_event_requires_at_least_one_choice():
    with pytest.raises(ValidationError):
        Event(id="e", title="t", text="x", choices=[])


def test_event_defaults():
    ev = Event(id="e", title="t", text="x", choices=[Choice(text="走")])
    assert ev.actions == ["explore"]
    assert ev.weight == 1.0 and not ev.once and not ev.qiyu
    assert ev.choices[0].effect.stats == {}


def test_location_danger_range():
    with pytest.raises(ValidationError):
        Location(id="a", name="A", description="d", connections=[], danger=4)


def test_config_defaults():
    cfg = Config()
    assert cfg.stamina_max == 150
    assert cfg.action_cost == {"explore": 10, "train": 10, "socialize": 5}
    assert cfg.stat_names["str"] == "臂力"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.models'`

- [ ] **Step 4: Write implementation**

`tianxia/models.py`:
```python
"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

STATS = ("str", "agi", "con", "wis", "silver", "good", "evil", "fame")
Style = Literal["剛", "柔", "快", "巧", "無"]
Slot = Literal["內功", "外功", "輕功"]
ActionKind = Literal["explore", "train", "socialize"]


class Condition(BaseModel):
    """所有欄位都是「且」的關係；空的欄位不檢查。"""

    min_stats: dict[str, int] = Field(default_factory=dict)
    max_stats: dict[str, int] = Field(default_factory=dict)
    flags_all: list[str] = Field(default_factory=list)
    flags_none: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    no_sect: bool = False
    skills_all: list[str] = Field(default_factory=list)
    skills_none: list[str] = Field(default_factory=list)
    trend_min: dict[str, int] = Field(default_factory=dict)
    trend_max: dict[str, int] = Field(default_factory=dict)
    world_flags_all: list[str] = Field(default_factory=list)
    world_flags_none: list[str] = Field(default_factory=list)


class Effect(BaseModel):
    text: str = ""
    stats: dict[str, int] = Field(default_factory=dict)
    stamina: int = 0
    flags_add: list[str] = Field(default_factory=list)
    flags_remove: list[str] = Field(default_factory=list)
    learn_skills: list[str] = Field(default_factory=list)
    trend: dict[str, int] = Field(default_factory=dict)
    world_flags_add: list[str] = Field(default_factory=list)
    rumor: str = ""  # {name} 會換成玩家名號（匿名時為「某位少俠」）
    chronicle: str = ""  # 寫入江湖史，同樣支援 {name}
    join_sect: str | None = None
    leave_sect: bool = False
    next_event: str | None = None


class Check(BaseModel):
    stat: str
    difficulty: int


class Choice(BaseModel):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵人 id：選了就進入關鍵戰鬥
    effect: Effect = Field(default_factory=Effect)  # 檢定成功／戰鬥勝利（或無檢定時）
    fail_effect: Effect = Field(default_factory=Effect)  # 檢定失敗／戰鬥落敗


class Event(BaseModel):
    id: str
    title: str
    text: str
    actions: list[ActionKind] = Field(default_factory=lambda: ["explore"])  # 空清單＝只能由 next_event 串接
    locations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    once: bool = False
    qiyu: bool = False
    condition: Condition = Field(default_factory=Condition)
    choices: list[Choice] = Field(min_length=1)


class Location(BaseModel):
    id: str
    name: str
    description: str
    connections: list[str]
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    move_cost: int = 5
    important: bool = False
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往


class Skill(BaseModel):
    id: str
    name: str
    slot: Slot
    style: Style = "無"
    power: int
    sect: str | None = None
    desc: str = ""


class Sect(BaseModel):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""
    starter_skills: list[str] = Field(default_factory=list)


class Enemy(BaseModel):
    id: str
    name: str
    desc: str = ""
    hp: int
    atk: int
    dfn: int
    spd: int
    style: Style = "無"
    reward_silver: int = 0


class Trend(BaseModel):
    id: str
    name: str
    desc: str = ""
    start: int = Field(default=0, ge=0, le=100)
    hidden: bool = False


class Threshold(BaseModel):
    id: str
    trend: str
    op: Literal[">=", "<="]
    value: int
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False


class SimPlayer(BaseModel):
    name: str
    actions_per_day: float
    trend: dict[str, int] = Field(default_factory=dict)
    requires_revealed: str | None = None  # 這條隱藏線浮現之前不會行動
    rumors: list[str] = Field(default_factory=list)
    rumor_chance: float = 0.3


class Ending(BaseModel):
    id: str
    title: str
    text: str
    condition: Condition = Field(default_factory=Condition)


class Scenario(BaseModel):
    id: str
    name: str
    intro: str
    start_location: str
    trends: list[Trend]
    thresholds: list[Threshold] = Field(default_factory=list)
    sim_players: list[SimPlayer] = Field(default_factory=list)
    endings: list[Ending]


class Config(BaseModel):
    stamina_max: int = 150
    stamina_regen_seconds: float = 300
    action_cost: dict[str, int] = Field(
        default_factory=lambda: {"explore": 10, "train": 10, "socialize": 5}
    )
    time_scale: float = 1.0
    season_days: float = 14
    seclusion_exp_per_hour: int = 20
    skill_exp_per_level: int = 100
    train_skill_exp: int = 10
    train_stat_chance: float = 0.3
    train_event_chance: float = 0.3
    qiyu_weight_multiplier: float = 1.5
    starter_skills: list[str] = Field(default_factory=list)
    start_stats: dict[str, int] = Field(
        default_factory=lambda: {
            "str": 5, "agi": 5, "con": 5, "wis": 5,
            "silver": 50, "good": 0, "evil": 0, "fame": 0,
        }
    )
    stat_names: dict[str, str] = Field(
        default_factory=lambda: {
            "str": "臂力", "agi": "身法", "con": "根骨", "wis": "悟性",
            "silver": "銀兩", "good": "善名", "evil": "惡名", "fame": "名望",
        }
    )
    max_log: int = 200


class Content(BaseModel):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, Skill]
    sects: dict[str, Sect]
    enemies: dict[str, Enemy]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pyproject.toml .gitignore tianxia/__init__.py tianxia/models.py tests/test_models.py
git commit -m "feat: add project scaffold and content data models"
```

---

### Task 2: 內容載入與交叉驗證

**Files:**
- Create: `tianxia/content.py`, `tests/conftest.py`, `tests/fixtures/content/`（config.json、scenario.json、locations.json、skills.json、sects.json、enemies.json、events/test.json）
- Test: `tests/test_content.py`

**Interfaces:**
- Consumes: Task 1 的所有模型與 `STATS`。
- Produces:
  - `load_content(root: Path) -> Content`：讀取 `root` 下的所有 JSON 並驗證；錯誤時丟 `ContentError`（訊息列出所有問題）。
  - `class ContentError(Exception)`
  - `tests/conftest.py`：`FIXTURE` 路徑、`FixedRandom(value)`（`random()` 永遠回傳固定值）、`content` fixture。
  - 測試用迷你內容（後續任務的測試都依賴這份內容的具體數值，**不要改動**）。

- [ ] **Step 1: 建立測試用迷你內容**

`tests/fixtures/content/config.json`:
```json
{"starter_skills": ["fist"], "season_days": 2}
```

`tests/fixtures/content/scenario.json`:
```json
{
  "id": "test",
  "name": "測試劇本",
  "intro": "測試開始。",
  "start_location": "town",
  "trends": [
    {"id": "kou", "name": "寇亂", "desc": "水寇勢力", "start": 30},
    {"id": "bao", "name": "寶藏", "desc": "前朝寶藏", "hidden": true}
  ],
  "thresholds": [
    {"id": "kou50", "trend": "kou", "op": ">=", "value": 50, "text": "水寇封江！", "world_flags_add": ["blocked"]},
    {"id": "kou80", "trend": "kou", "op": ">=", "value": 80, "text": "水寇稱霸！", "world_flags_add": ["kou_win"], "ends_season": true},
    {"id": "bao100", "trend": "bao", "op": ">=", "value": 100, "text": "寶洞現世！", "world_flags_add": ["cave_open"]}
  ],
  "sim_players": [
    {"name": "翻江龍", "actions_per_day": 24, "trend": {"kou": 1}, "rumors": ["{name}又劫了一艘船。"], "rumor_chance": 1.0},
    {"name": "鬼手", "actions_per_day": 24, "trend": {"bao": 1}, "requires_revealed": "bao", "rumors": ["{name}在挖土。"], "rumor_chance": 0.0}
  ],
  "endings": [
    {"id": "kou_win", "title": "水寇稱霸", "text": "江南落入水寇之手。", "condition": {"world_flags_all": ["kou_win"]}},
    {"id": "default", "title": "風雨飄搖", "text": "江南依舊動盪。"}
  ]
}
```

`tests/fixtures/content/locations.json`:
```json
[
  {"id": "town", "name": "小鎮", "description": "一個小鎮。", "connections": ["lake"], "tags": ["城鎮"]},
  {"id": "lake", "name": "湖邊", "description": "湖水茫茫。", "connections": ["town", "cave"], "tags": ["湖畔"], "danger": 2, "enemies": ["thug"], "train_trend": {"kou": -1}},
  {"id": "cave", "name": "寶洞", "description": "幽深的山洞。", "connections": ["lake"], "unlock_flag": "cave_open", "danger": 3}
]
```

`tests/fixtures/content/skills.json`:
```json
[
  {"id": "fist", "name": "長拳", "slot": "外功", "style": "剛", "power": 10},
  {"id": "breath", "name": "吐納法", "slot": "內功", "power": 8},
  {"id": "sword", "name": "流雲劍", "slot": "外功", "style": "柔", "power": 16, "sect": "cloud"},
  {"id": "step", "name": "追風步", "slot": "輕功", "style": "快", "power": 12}
]
```

`tests/fixtures/content/sects.json`:
```json
[
  {"id": "cloud", "name": "流雲派", "location": "town", "alignment": "正", "desc": "以劍法聞名。", "starter_skills": ["sword"]}
]
```

`tests/fixtures/content/enemies.json`:
```json
[
  {"id": "thug", "name": "小嘍囉", "desc": "拿著魚叉的水寇。", "hp": 30, "atk": 8, "dfn": 2, "spd": 5, "style": "剛", "reward_silver": 5},
  {"id": "boss", "name": "翻江龍", "desc": "水寨大當家。", "hp": 500, "atk": 60, "dfn": 30, "spd": 30, "style": "剛"}
]
```

`tests/fixtures/content/events/test.json`:
```json
[
  {"id": "drunk", "title": "醉漢", "text": "一名醉漢撞上了你。", "locations": ["town"], "choices": [
    {"text": "逼問", "check": {"stat": "str", "difficulty": 5},
     "effect": {"text": "他全招了。", "stats": {"good": 2}, "trend": {"kou": -5}},
     "fail_effect": {"text": "被他溜了。"}},
    {"text": "摸走鐵牌", "effect": {"stats": {"evil": 1}, "flags_add": ["token"]}},
    {"text": "入夥", "condition": {"min_stats": {"evil": 5}}, "effect": {"flags_add": ["kou_member"]}}
  ]},
  {"id": "scroll", "title": "殘卷", "text": "你撿到一片殘卷。", "locations": ["lake"], "qiyu": true, "once": true, "choices": [
    {"text": "收下", "effect": {"trend": {"bao": 20}, "rumor": "{name}撿到了殘卷！", "chronicle": "{name}發現殘卷。"}}
  ]},
  {"id": "join", "title": "拜師", "text": "流雲派收徒。", "actions": ["socialize"], "locations": ["town"], "condition": {"no_sect": true}, "choices": [
    {"text": "拜入", "effect": {"join_sect": "cloud"}},
    {"text": "婉拒"}
  ]},
  {"id": "duel", "title": "挑戰", "text": "翻江龍攔住去路。", "actions": ["socialize"], "locations": ["lake"], "choices": [
    {"text": "應戰", "combat": "boss",
     "effect": {"text": "你擊敗了翻江龍！", "trend": {"kou": -20}},
     "fail_effect": {"text": "你敗了。", "stats": {"silver": -10}}},
    {"text": "迴避"}
  ]},
  {"id": "chain_a", "title": "跟蹤", "text": "你跟了上去。", "actions": ["train"], "locations": ["lake"], "choices": [
    {"text": "繼續", "effect": {"next_event": "chain_b"}}
  ]},
  {"id": "chain_b", "title": "倉庫", "text": "你發現一座倉庫。", "actions": [], "choices": [
    {"text": "離開"}
  ]}
]
```

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:
```python
import random
from pathlib import Path

import pytest

from tianxia.content import load_content

FIXTURE = Path(__file__).parent / "fixtures" / "content"


class FixedRandom(random.Random):
    """random() 永遠回傳固定值，讓檢定與機率判定可以預測。"""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.fixture
def content():
    return load_content(FIXTURE)
```

`tests/test_content.py`:
```python
import json
import shutil

import pytest

from conftest import FIXTURE
from tianxia.content import ContentError, load_content


def copy_fixture(tmp_path):
    dest = tmp_path / "content"
    shutil.copytree(FIXTURE, dest)
    return dest


def edit_json(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_fixture(content):
    assert set(content.locations) == {"town", "lake", "cave"}
    assert "drunk" in content.events and "chain_b" in content.events
    assert content.scenario.start_location == "town"
    assert content.config.starter_skills == ["fist"]


def test_one_way_connection_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "locations.json", lambda d: d[0]["connections"].append("cave"))
    with pytest.raises(ContentError, match="town.*cave"):
        load_content(root)


def test_unknown_enemy_in_choice_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][0].update(combat="ghost"))
    with pytest.raises(ContentError, match="ghost"):
        load_content(root)


def test_event_needs_unconditional_choice(tmp_path):
    root = copy_fixture(tmp_path)

    def make_all_conditional(d):
        for choice in d[0]["choices"]:
            choice["condition"] = {"min_stats": {"str": 1}}

    edit_json(root / "events" / "test.json", make_all_conditional)
    with pytest.raises(ContentError, match="drunk"):
        load_content(root)


def test_unknown_stat_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d[0]["choices"][1]["effect"]["stats"].update(luck=1))
    with pytest.raises(ContentError, match="luck"):
        load_content(root)


def test_last_ending_must_be_unconditional(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["endings"].pop())
    with pytest.raises(ContentError, match="結局"):
        load_content(root)


def test_duplicate_event_id_rejected(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "events" / "test.json", lambda d: d.append(dict(d[0])))
    with pytest.raises(ContentError, match="drunk"):
        load_content(root)


def test_hidden_trend_cannot_use_lte_threshold(tmp_path):
    root = copy_fixture(tmp_path)
    edit_json(root / "scenario.json", lambda d: d["thresholds"][2].update(op="<=", value=0))
    with pytest.raises(ContentError, match="bao100"):
        load_content(root)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_content.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.content'`

- [ ] **Step 4: Write implementation**

`tianxia/content.py`:
```python
"""載入 content/ 底下的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。"""
from __future__ import annotations

import json
from pathlib import Path

from .models import (
    STATS, Condition, Config, Content, Effect, Enemy, Event, Location, Scenario, Sect, Skill,
)


class ContentError(Exception):
    pass


def load_content(root: Path) -> Content:
    root = Path(root)
    events: dict[str, Event] = {}
    for path in sorted((root / "events").glob("*.json")):
        for raw in _read(path):
            event = Event(**raw)
            if event.id in events:
                raise ContentError(f"事件 id 重複：{event.id}（{path.name}）")
            events[event.id] = event
    content = Content(
        config=Config(**_read(root / "config.json")),
        scenario=Scenario(**_read(root / "scenario.json")),
        locations=_index(Location, _read(root / "locations.json")),
        skills=_index(Skill, _read(root / "skills.json")),
        sects=_index(Sect, _read(root / "sects.json")),
        enemies=_index(Enemy, _read(root / "enemies.json")),
        events=events,
    )
    validate(content)
    return content


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _index(model, items: list[dict]) -> dict:
    result = {}
    for raw in items:
        obj = model(**raw)
        if obj.id in result:
            raise ContentError(f"{model.__name__} id 重複：{obj.id}")
        result[obj.id] = obj
    return result


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

    def check_condition(where: str, cond: Condition) -> None:
        known(where, [*cond.min_stats, *cond.max_stats], STATS, "屬性")
        known(where, cond.sects, c.sects, "門派")
        known(where, [*cond.skills_all, *cond.skills_none], c.skills, "武學")
        known(where, [*cond.trend_min, *cond.trend_max], trend_ids, "大勢線")

    def check_effect(where: str, eff: Effect) -> None:
        known(where, eff.stats, STATS, "屬性")
        known(where, eff.learn_skills, c.skills, "武學")
        known(where, eff.trend, trend_ids, "大勢線")
        if eff.join_sect:
            known(where, [eff.join_sect], c.sects, "門派")
        if eff.next_event:
            known(where, [eff.next_event], c.events, "事件")

    cfg = c.config
    for action in ("explore", "train", "socialize"):
        need(action in cfg.action_cost, f"config.action_cost 缺少 {action}")
    for stat in STATS:
        need(stat in cfg.start_stats, f"config.start_stats 缺少 {stat}")
    known("config.starter_skills", cfg.starter_skills, c.skills, "武學")

    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        for dest in loc.connections:
            if dest not in c.locations:
                errors.append(f"{where}：連到不存在的地點 {dest}")
            elif loc.id not in c.locations[dest].connections:
                errors.append(f"地點 {loc.id} 連到 {dest}，但 {dest} 沒有連回來")
        known(where, loc.enemies, c.enemies, "敵人")
        known(where, loc.train_trend, trend_ids, "大勢線")
    need(c.scenario.start_location in c.locations, f"劇本起點 {c.scenario.start_location} 不存在")

    for skill in c.skills.values():
        if skill.sect:
            known(f"武學 {skill.id}", [skill.sect], c.sects, "門派")
    for sect in c.sects.values():
        known(f"門派 {sect.id}", [sect.location], c.locations, "地點")
        known(f"門派 {sect.id}", sect.starter_skills, c.skills, "武學")

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
                known(cw, [ch.combat], c.enemies, "敵人")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")

    for th in c.scenario.thresholds:
        where = f"門檻 {th.id}"
        known(where, [th.trend], trend_ids, "大勢線")
        need(
            not (th.trend in hidden and th.op == "<="),
            f"{where}：隱藏大勢線不能用 <= 門檻（未浮現時數值為 0，會立刻觸發）",
        )
    for sim in c.scenario.sim_players:
        where = f"虛擬玩家 {sim.name}"
        known(where, sim.trend, trend_ids, "大勢線")
        if sim.requires_revealed:
            known(where, [sim.requires_revealed], trend_ids, "大勢線")
    for ending in c.scenario.endings:
        check_condition(f"結局 {ending.id}", ending.condition)
    need(
        bool(c.scenario.endings) and c.scenario.endings[-1].condition == Condition(),
        "劇本的最後一個結局必須沒有條件（作為保底結局）",
    )

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_content.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add tianxia/content.py tests/conftest.py tests/fixtures tests/test_content.py
git commit -m "feat: load and cross-validate JSON content files"
```

---
### Task 3: 執行期狀態與數值規則

**Files:**
- Create: `tianxia/state.py`, `tianxia/rules.py`
- Modify: `tests/conftest.py`（新增 `state` fixture）
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: Task 1 的模型、Task 2 的 `content` fixture。
- Produces:
  - `state.EQUIP_SLOTS = ("內功", "外功", "外功", "輕功")`
  - `state.SkillProgress(level=1, exp=0)`、`PlayerState`、`Rumor(time, text)`、`WorldState`、`BattleState`、`GameState`（欄位如下）
  - `state.new_game_state(content, name) -> GameState`（不含起始武學，由 Task 7 的 `Game.new` 負責）
  - `rules.display_name(state) -> str`
  - `rules.check_condition(cond, state) -> bool`
  - `rules.check_chance(check, state) -> float`、`rules.roll_check(check, state, rng) -> bool`
  - `rules.add_rumor(state, text)`、`rules.add_chronicle(state, text)`
  - `rules.trend_name(content, trend_id) -> str`
  - `rules.change_trend(state, content, trend_id, delta, reveal=True) -> list[str]`
  - `rules.learn_skill(state, content, skill_id) -> list[str]`
  - `rules.add_skill_exp(state, content, skill_id, amount) -> list[str]`
  - `rules.apply_effect(effect, state, content) -> list[str]`（不處理 `next_event`，由 Task 7 的引擎處理）

- [ ] **Step 1: Write the failing test**

在 `tests/conftest.py` 最後加上：
```python
@pytest.fixture
def state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "沈浪")
```

`tests/test_rules.py`:
```python
import pytest

from tianxia.models import Check, Condition, Effect
from tianxia.rules import add_skill_exp, apply_effect, check_chance, check_condition, learn_skill


def test_new_state(state):
    assert state.player.location == "town"
    assert state.player.stamina == 150
    assert state.world.trends == {"kou": 30, "bao": 0}
    assert state.world.revealed == {"kou"}


def test_empty_condition_passes(state):
    assert check_condition(Condition(), state)


def test_condition_stats_and_flags(state):
    state.player.flags.add("token")
    assert check_condition(Condition(min_stats={"str": 5}, flags_all=["token"]), state)
    assert not check_condition(Condition(min_stats={"str": 6}), state)
    assert not check_condition(Condition(flags_none=["token"]), state)


def test_condition_sect_and_skills(state):
    assert check_condition(Condition(no_sect=True), state)
    assert not check_condition(Condition(sects=["cloud"]), state)
    state.player.sect = "cloud"
    assert check_condition(Condition(sects=["cloud"]), state)
    assert not check_condition(Condition(no_sect=True), state)
    assert check_condition(Condition(skills_none=["fist"]), state)


def test_condition_world(state):
    assert check_condition(Condition(trend_min={"kou": 30}, trend_max={"kou": 30}), state)
    assert not check_condition(Condition(trend_min={"kou": 31}), state)
    state.world.flags.add("blocked")
    assert check_condition(Condition(world_flags_all=["blocked"]), state)
    assert not check_condition(Condition(world_flags_none=["blocked"]), state)


def test_check_chance_scales_and_clamps(state):
    assert check_chance(Check(stat="str", difficulty=5), state) == 0.5
    assert check_chance(Check(stat="str", difficulty=7), state) == pytest.approx(0.3)
    assert check_chance(Check(stat="str", difficulty=50), state) == 0.05
    assert check_chance(Check(stat="str", difficulty=-50), state) == 0.95


def test_apply_stats_clamps_at_zero(state, content):
    msgs = apply_effect(Effect(text="你撿到錢。", stats={"silver": 10, "evil": -3}), state, content)
    assert state.player.stats["silver"] == 60
    assert state.player.stats["evil"] == 0
    assert msgs[0] == "你撿到錢。"
    assert "銀兩 +10" in msgs


def test_apply_stamina_clamps(state, content):
    apply_effect(Effect(stamina=50), state, content)
    assert state.player.stamina == 150
    apply_effect(Effect(stamina=-500), state, content)
    assert state.player.stamina == 0


def test_hidden_trend_revealed_by_positive_push(state, content):
    msgs = apply_effect(Effect(trend={"bao": 20}), state, content)
    assert "bao" in state.world.revealed
    assert state.world.trends["bao"] == 20
    assert any("寶藏" in m for m in msgs)


def test_hidden_trend_ignores_negative_push(state, content):
    apply_effect(Effect(trend={"bao": -5}), state, content)
    assert "bao" not in state.world.revealed
    assert state.world.trends["bao"] == 0


def test_trend_clamped(state, content):
    apply_effect(Effect(trend={"kou": 500}), state, content)
    assert state.world.trends["kou"] == 100
    apply_effect(Effect(trend={"kou": -500}), state, content)
    assert state.world.trends["kou"] == 0


def test_rumor_respects_anonymity(state, content):
    apply_effect(Effect(rumor="{name}撿到了殘卷！", chronicle="{name}發現殘卷。"), state, content)
    state.player.anonymous = True
    apply_effect(Effect(rumor="{name}又出手了！"), state, content)
    assert [r.text for r in state.world.rumors] == ["沈浪撿到了殘卷！", "某位少俠又出手了！"]
    assert state.world.chronicle[0].text == "沈浪發現殘卷。"


def test_join_sect_learns_and_equips(state, content):
    msgs = apply_effect(Effect(join_sect="cloud"), state, content)
    assert state.player.sect == "cloud"
    assert "sword" in state.player.skills
    assert state.player.equipped[1] == "sword"
    assert any("流雲派" in m for m in msgs)


def test_leave_sect_sets_flag(state, content):
    state.player.sect = "cloud"
    apply_effect(Effect(leave_sect=True), state, content)
    assert state.player.sect is None
    assert "叛出:cloud" in state.player.flags


def test_learn_skill_fills_first_matching_empty_slot(state, content):
    learn_skill(state, content, "fist")
    learn_skill(state, content, "sword")
    assert state.player.equipped == [None, "fist", "sword", None]
    assert learn_skill(state, content, "fist") == []


def test_skill_exp_levels_up_and_caps(state, content):
    learn_skill(state, content, "fist")
    msgs = add_skill_exp(state, content, "fist", 250)
    prog = state.player.skills["fist"]
    assert (prog.level, prog.exp) == (3, 50)
    assert len(msgs) == 2
    add_skill_exp(state, content, "fist", 10_000)
    assert (prog.level, prog.exp) == (10, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.state'`

- [ ] **Step 3: Write implementation**

`tianxia/state.py`:
```python
"""執行期狀態：玩家、世界、戰鬥。全部是可直接序列化成 JSON 的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import Content

EQUIP_SLOTS = ("內功", "外功", "外功", "輕功")


class SkillProgress(BaseModel):
    level: int = 1
    exp: int = 0


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    skills: dict[str, SkillProgress] = Field(default_factory=dict)
    equipped: list[str | None] = Field(default_factory=lambda: [None] * len(EQUIP_SLOTS))
    seen_events: set[str] = Field(default_factory=set)
    anonymous: bool = False
    busy_until: float | None = None  # 閉關結束的遊戲時間
    seclusion_start: float = 0.0
    seclusion_skill: str | None = None


class Rumor(BaseModel):
    time: float
    text: str


class WorldState(BaseModel):
    time: float = 0.0  # 賽季開始後經過的遊戲秒數
    trends: dict[str, int] = Field(default_factory=dict)
    revealed: set[str] = Field(default_factory=set)
    flags: set[str] = Field(default_factory=set)
    fired_thresholds: set[str] = Field(default_factory=set)
    rumors: list[Rumor] = Field(default_factory=list)
    chronicle: list[Rumor] = Field(default_factory=list)
    sim_accum: float = 0.0  # 累積但還不滿一小時的時間，給虛擬玩家用
    ended: bool = False
    ending_title: str = ""
    ending_text: str = ""


class BattleState(BaseModel):
    enemy_id: str
    event_id: str
    choice_index: int
    player_hp: int
    player_hp_max: int
    enemy_hp: int
    round: int = 0
    ultimate_used: bool = False


class GameState(BaseModel):
    player: PlayerState
    world: WorldState
    pending_event: str | None = None
    battle: BattleState | None = None
    log: list[str] = Field(default_factory=list)
    last_real: float | None = None  # 上次同步的現實時間（time.time()）


def new_game_state(content: Content, name: str) -> GameState:
    cfg = content.config
    trends = content.scenario.trends
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
    )
    world = WorldState(
        trends={t.id: t.start for t in trends},
        revealed={t.id for t in trends if not t.hidden},
    )
    return GameState(player=player, world=world)
```

`tianxia/rules.py`:
```python
"""數值規則的核心：條件判定、效果套用、屬性檢定、大勢推進、武學經驗。"""
from __future__ import annotations

import random

from .models import Check, Condition, Content, Effect
from .state import EQUIP_SLOTS, GameState, Rumor, SkillProgress

MAX_SKILL_LEVEL = 10


def display_name(state: GameState) -> str:
    return "某位少俠" if state.player.anonymous else state.player.name


def check_condition(cond: Condition, state: GameState) -> bool:
    p, w = state.player, state.world
    if any(p.stats.get(k, 0) < v for k, v in cond.min_stats.items()):
        return False
    if any(p.stats.get(k, 0) > v for k, v in cond.max_stats.items()):
        return False
    if not set(cond.flags_all) <= p.flags or set(cond.flags_none) & p.flags:
        return False
    if cond.sects and p.sect not in cond.sects:
        return False
    if cond.no_sect and p.sect is not None:
        return False
    if any(s not in p.skills for s in cond.skills_all):
        return False
    if any(s in p.skills for s in cond.skills_none):
        return False
    if any(w.trends.get(t, 0) < v for t, v in cond.trend_min.items()):
        return False
    if any(w.trends.get(t, 0) > v for t, v in cond.trend_max.items()):
        return False
    if not set(cond.world_flags_all) <= w.flags or set(cond.world_flags_none) & w.flags:
        return False
    return True


def check_chance(check: Check, state: GameState) -> float:
    """屬性每高於難度 1 點，成功率 +10%；範圍 5%～95%。"""
    value = state.player.stats.get(check.stat, 0)
    return min(0.95, max(0.05, 0.5 + (value - check.difficulty) * 0.1))


def roll_check(check: Check, state: GameState, rng: random.Random) -> bool:
    return rng.random() < check_chance(check, state)


def add_rumor(state: GameState, text: str) -> None:
    state.world.rumors.append(Rumor(time=state.world.time, text=text))


def add_chronicle(state: GameState, text: str) -> None:
    state.world.chronicle.append(Rumor(time=state.world.time, text=text))


def trend_name(content: Content, trend_id: str) -> str:
    return next(t.name for t in content.scenario.trends if t.id == trend_id)


def change_trend(
    state: GameState, content: Content, trend_id: str, delta: int, reveal: bool = True
) -> list[str]:
    """推動大勢線。隱藏線只有在 reveal=True 且正向推進時才會浮現；未浮現前其他推動一律無效。"""
    w = state.world
    msgs: list[str] = []
    if trend_id not in w.revealed:
        if not reveal or delta <= 0:
            return msgs
        w.revealed.add(trend_id)
        msgs.append(f"（江湖暗流湧動——「{trend_name(content, trend_id)}」浮上檯面。）")
    w.trends[trend_id] = min(100, max(0, w.trends.get(trend_id, 0) + delta))
    return msgs


def learn_skill(state: GameState, content: Content, skill_id: str) -> list[str]:
    p = state.player
    if skill_id in p.skills:
        return []
    p.skills[skill_id] = SkillProgress()
    skill = content.skills[skill_id]
    msgs = [f"你習得了【{skill.name}】！"]
    for i, slot in enumerate(EQUIP_SLOTS):
        if slot == skill.slot and p.equipped[i] is None:
            p.equipped[i] = skill_id
            msgs.append(f"已將【{skill.name}】配置於{slot}欄位。")
            break
    return msgs


def add_skill_exp(state: GameState, content: Content, skill_id: str, amount: int) -> list[str]:
    prog = state.player.skills[skill_id]
    if prog.level >= MAX_SKILL_LEVEL:
        return []
    prog.exp += amount
    per_level = content.config.skill_exp_per_level
    msgs = []
    while prog.exp >= per_level and prog.level < MAX_SKILL_LEVEL:
        prog.exp -= per_level
        prog.level += 1
        msgs.append(f"【{content.skills[skill_id].name}】精進至第{prog.level}成！")
    if prog.level >= MAX_SKILL_LEVEL:
        prog.exp = 0
    return msgs


def apply_effect(effect: Effect, state: GameState, content: Content) -> list[str]:
    p = state.player
    names = content.config.stat_names
    msgs: list[str] = []
    if effect.text:
        msgs.append(effect.text)
    for key, delta in effect.stats.items():
        p.stats[key] = max(0, p.stats.get(key, 0) + delta)
        msgs.append(f"{names.get(key, key)} {'+' if delta >= 0 else ''}{delta}")
    if effect.stamina:
        p.stamina = min(content.config.stamina_max, max(0.0, p.stamina + effect.stamina))
        msgs.append(f"體力 {'+' if effect.stamina > 0 else ''}{effect.stamina}")
    p.flags |= set(effect.flags_add)
    p.flags -= set(effect.flags_remove)
    for skill_id in effect.learn_skills:
        msgs += learn_skill(state, content, skill_id)
    if effect.join_sect:
        sect = content.sects[effect.join_sect]
        p.sect = sect.id
        msgs.append(f"你拜入了{sect.name}！")
        for skill_id in sect.starter_skills:
            msgs += learn_skill(state, content, skill_id)
    if effect.leave_sect and p.sect:
        msgs.append(f"你叛出了{content.sects[p.sect].name}。")
        p.flags.add(f"叛出:{p.sect}")
        p.sect = None
    for trend_id, delta in effect.trend.items():
        msgs += change_trend(state, content, trend_id, delta)
    state.world.flags |= set(effect.world_flags_add)
    name = display_name(state)
    if effect.rumor:
        text = effect.rumor.format(name=name)
        add_rumor(state, text)
        msgs.append(f"【江湖傳聞】{text}")
    if effect.chronicle:
        add_chronicle(state, effect.chronicle.format(name=name))
    return msgs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rules.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add tianxia/state.py tianxia/rules.py tests/conftest.py tests/test_rules.py
git commit -m "feat: add runtime state and core rules (conditions, effects, checks, skills)"
```

---

### Task 4: 事件抽選與選項

**Files:**
- Create: `tianxia/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: `rules.check_condition`、`rules.check_chance`。
- Produces:
  - `event_matches_location(event, location) -> bool`：`locations` 與 `tags` 都空＝任何地點；否則地點 id 在 `locations` 內**或** tags 有交集即可。
  - `pick_event(state, content, action, rng) -> Event | None`：依 action、地點、`once`、條件篩選後按權重抽選；奇遇權重乘上 `config.qiyu_weight_multiplier`。
  - `visible_choices(event, state) -> list[tuple[int, Choice]]`：保留原始索引。
  - `choice_label(choice, state) -> str`：有檢定時附上「（成功率 N%）」。

- [ ] **Step 1: Write the failing test**

`tests/test_events.py`:
```python
import random

from tianxia.events import choice_label, event_matches_location, pick_event, visible_choices


def test_location_matching(content):
    town, lake = content.locations["town"], content.locations["lake"]
    assert event_matches_location(content.events["drunk"], town)
    assert not event_matches_location(content.events["drunk"], lake)


def test_pick_event_filters_by_action_and_location(state, content):
    rng = random.Random(0)
    assert {pick_event(state, content, "explore", rng).id for _ in range(20)} == {"drunk"}
    assert pick_event(state, content, "socialize", rng).id == "join"
    assert pick_event(state, content, "train", rng) is None


def test_pick_event_skips_seen_once_events(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    assert pick_event(state, content, "explore", rng).id == "scroll"
    state.player.seen_events.add("scroll")
    assert pick_event(state, content, "explore", rng) is None


def test_pick_event_respects_condition(state, content):
    state.player.sect = "cloud"
    assert pick_event(state, content, "socialize", random.Random(0)) is None


def test_chain_only_events_never_picked(state, content):
    state.player.location = "lake"
    rng = random.Random(0)
    picks = {pick_event(state, content, "train", rng).id for _ in range(20)}
    assert picks == {"chain_a"}


def test_visible_choices_hide_conditional(state, content):
    ev = content.events["drunk"]
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1]
    state.player.stats["evil"] = 5
    assert [i for i, _ in visible_choices(ev, state)] == [0, 1, 2]


def test_choice_label_shows_success_rate(state, content):
    ev = content.events["drunk"]
    assert choice_label(ev.choices[0], state) == "逼問（成功率 50%）"
    assert choice_label(ev.choices[1], state) == "摸走鐵牌"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.events'`

- [ ] **Step 3: Write implementation**

`tianxia/events.py`:
```python
"""事件抽選與選項顯示。選項的效果處理在 engine.py（因為可能牽涉戰鬥與事件串接）。"""
from __future__ import annotations

import random

from .models import Choice, Content, Event, Location
from .rules import check_chance, check_condition
from .state import GameState


def event_matches_location(event: Event, location: Location) -> bool:
    if not event.locations and not event.tags:
        return True
    return location.id in event.locations or bool(set(event.tags) & set(location.tags))


def pick_event(
    state: GameState, content: Content, action: str, rng: random.Random
) -> Event | None:
    location = content.locations[state.player.location]
    candidates: list[Event] = []
    weights: list[float] = []
    for event in content.events.values():
        if action not in event.actions:
            continue
        if not event_matches_location(event, location):
            continue
        if event.once and event.id in state.player.seen_events:
            continue
        if not check_condition(event.condition, state):
            continue
        candidates.append(event)
        bonus = content.config.qiyu_weight_multiplier if event.qiyu else 1.0
        weights.append(event.weight * bonus)
    if not candidates:
        return None
    return rng.choices(candidates, weights=weights)[0]


def visible_choices(event: Event, state: GameState) -> list[tuple[int, Choice]]:
    return [(i, c) for i, c in enumerate(event.choices) if check_condition(c.condition, state)]


def choice_label(choice: Choice, state: GameState) -> str:
    if choice.check:
        return f"{choice.text}（成功率 {round(check_chance(choice.check, state) * 100)}%）"
    return choice.text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_events.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add tianxia/events.py tests/test_events.py
git commit -m "feat: add weighted event picking and choice labels"
```

---
### Task 5: 戰鬥（相剋、自動結算、關鍵戰鬥）

**Files:**
- Create: `tianxia/combat.py`
- Test: `tests/test_combat.py`

**Interfaces:**
- Consumes: `state.BattleState`、`GameState`；`Content`。
- Produces:
  - `BEATS`（剛克巧、巧克快、快克柔、柔克剛）、`ADVANTAGE = 1.25`、`TACTICS = ("強攻", "巧取", "固守", "絕招", "撤退")`
  - `@dataclass Fighter(name, hp, atk, dfn, spd, style)`
  - `player_fighter(state, content) -> Fighter`：攻＝臂力×2＋外功加成；防＝根骨×2＋內功加成；速＝身法×2＋輕功加成；氣血＝80＋根骨×5；流派＝第一個裝備外功的屬性。武學加成＝`power * (10 + 成數) // 20`。
  - `enemy_fighter(enemy) -> Fighter`
  - `style_multiplier(attacker_style, defender_style) -> float`
  - `damage(attacker, defender, rng, mult=1.0) -> int`（至少 1）
  - `auto_battle(player, enemy, rng) -> tuple[bool, int]`（是否勝利、回合數）
  - `start_battle(state, content, enemy_id, event_id, choice_index) -> list[str]`
  - `battle_status(state, content) -> str`
  - `battle_round(state, content, tactic, rng) -> tuple[str | None, list[str]]`：結果為 `"win"`／`"lose"`／`"flee"`；戰鬥結束時把 `state.battle` 設為 `None`。第二次使用絕招丟 `ValueError`。

- [ ] **Step 1: Write the failing test**

`tests/test_combat.py`:
```python
import random

import pytest

from conftest import FixedRandom
from tianxia.combat import (
    ADVANTAGE, Fighter, auto_battle, battle_round, damage, player_fighter, start_battle,
    style_multiplier,
)
from tianxia.rules import learn_skill


def test_style_cycle():
    assert style_multiplier("柔", "剛") == ADVANTAGE
    assert style_multiplier("剛", "柔") == pytest.approx(1 / ADVANTAGE)
    assert style_multiplier("剛", "剛") == 1.0
    assert style_multiplier("無", "快") == 1.0


def test_player_fighter_uses_equipped_skills(state, content):
    base = player_fighter(state, content)
    assert (base.hp, base.atk, base.dfn, base.spd, base.style) == (105, 10, 10, 10, "無")
    learn_skill(state, content, "fist")  # power 10，第1成：10 * 11 // 20 = 5
    fighter = player_fighter(state, content)
    assert (fighter.atk, fighter.style) == (15, "剛")


def test_damage_minimum_one():
    weak = Fighter("弱", 10, 1, 0, 1, "無")
    tank = Fighter("硬", 10, 1, 100, 1, "無")
    assert damage(weak, tank, random.Random(0)) == 1


def test_auto_battle_strong_beats_weak():
    strong = Fighter("強", 200, 50, 20, 20, "無")
    weak = Fighter("弱", 30, 5, 2, 5, "無")
    assert auto_battle(strong, weak, random.Random(0)) == (True, 1)
    won, _ = auto_battle(weak, strong, random.Random(0))
    assert not won


def test_key_battle_flee(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "撤退", FixedRandom(0.0))
    assert outcome == "flee" and state.battle is None


def test_key_battle_win_with_huge_strength(state, content):
    state.player.stats["str"] = 300
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "強攻", random.Random(0))
    assert outcome == "win" and state.battle is None


def test_key_battle_ultimate_only_once(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome, _ = battle_round(state, content, "絕招", random.Random(0))
    assert outcome is None and state.battle.ultimate_used
    with pytest.raises(ValueError):
        battle_round(state, content, "絕招", random.Random(0))


def test_key_battle_lose(state, content):
    start_battle(state, content, "boss", "duel", 0)
    outcome = None
    for _ in range(5):
        outcome, _ = battle_round(state, content, "強攻", random.Random(0))
        if outcome:
            break
    assert outcome == "lose" and state.battle is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_combat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.combat'`

- [ ] **Step 3: Write implementation**

`tianxia/combat.py`:
```python
"""戰鬥：武學相剋、一般遭遇的自動結算、關鍵戰鬥的回合選擇。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Content, Enemy
from .state import BattleState, GameState

BEATS = {"剛": "巧", "巧": "快", "快": "柔", "柔": "剛"}  # key 克制 value
ADVANTAGE = 1.25
MAX_AUTO_ROUNDS = 10
MAX_KEY_ROUNDS = 12
TACTICS = ("強攻", "巧取", "固守", "絕招", "撤退")


@dataclass
class Fighter:
    name: str
    hp: int
    atk: int
    dfn: int
    spd: int
    style: str


def player_fighter(state: GameState, content: Content) -> Fighter:
    p = state.player
    atk, dfn, spd = p.stats["str"] * 2, p.stats["con"] * 2, p.stats["agi"] * 2
    style = "無"
    for skill_id in p.equipped:
        if skill_id is None:
            continue
        skill = content.skills[skill_id]
        bonus = skill.power * (10 + p.skills[skill_id].level) // 20
        if skill.slot == "外功":
            atk += bonus
            if style == "無":
                style = skill.style
        elif skill.slot == "內功":
            dfn += bonus
        else:
            spd += bonus
    return Fighter(p.name, 80 + p.stats["con"] * 5, atk, dfn, spd, style)


def enemy_fighter(enemy: Enemy) -> Fighter:
    return Fighter(enemy.name, enemy.hp, enemy.atk, enemy.dfn, enemy.spd, enemy.style)


def style_multiplier(attacker: str, defender: str) -> float:
    if BEATS.get(attacker) == defender:
        return ADVANTAGE
    if BEATS.get(defender) == attacker:
        return 1 / ADVANTAGE
    return 1.0


def damage(attacker: Fighter, defender: Fighter, rng: random.Random, mult: float = 1.0) -> int:
    base = attacker.atk * style_multiplier(attacker.style, defender.style) * mult - defender.dfn * 0.5
    return max(1, round(base * rng.uniform(0.85, 1.15)))


def auto_battle(player: Fighter, enemy: Fighter, rng: random.Random) -> tuple[bool, int]:
    """回傳（是否勝利, 交手回合數）。回合打完仍未分勝負時，比較剩餘氣血比例。"""
    fighters = {"p": player, "e": enemy}
    hp = {"p": player.hp, "e": enemy.hp}
    order = ["p", "e"] if player.spd >= enemy.spd else ["e", "p"]
    for rnd in range(1, MAX_AUTO_ROUNDS + 1):
        for side in order:
            other = "e" if side == "p" else "p"
            hp[other] -= damage(fighters[side], fighters[other], rng)
            if hp[other] <= 0:
                return side == "p", rnd
    return hp["p"] / player.hp >= hp["e"] / enemy.hp, MAX_AUTO_ROUNDS


def start_battle(
    state: GameState, content: Content, enemy_id: str, event_id: str, choice_index: int
) -> list[str]:
    pf = player_fighter(state, content)
    enemy = content.enemies[enemy_id]
    state.battle = BattleState(
        enemy_id=enemy_id, event_id=event_id, choice_index=choice_index,
        player_hp=pf.hp, player_hp_max=pf.hp, enemy_hp=enemy.hp,
    )
    return [f"⚔ 對手：{enemy.name}——{enemy.desc}", "生死一線，你要如何應對？"]


def battle_status(state: GameState, content: Content) -> str:
    b = state.battle
    enemy = content.enemies[b.enemy_id]
    return (
        f"第{b.round}回合｜你 {max(0, b.player_hp)}/{b.player_hp_max}　"
        f"{enemy.name} {max(0, b.enemy_hp)}/{enemy.hp}"
    )


def battle_round(
    state: GameState, content: Content, tactic: str, rng: random.Random
) -> tuple[str | None, list[str]]:
    b = state.battle
    pf = player_fighter(state, content)
    ef = enemy_fighter(content.enemies[b.enemy_id])
    deal, take, heal = 1.0, 1.0, 0
    msgs: list[str] = []
    if tactic == "強攻":
        deal, take = 1.4, 1.2
        msgs.append("你搶身而上，招招搶攻！")
    elif tactic == "巧取":
        chance = min(0.9, max(0.1, 0.5 + (state.player.stats["wis"] * 2 - ef.spd) * 0.03))
        if rng.random() < chance:
            deal, take = 1.8, 0.5
            msgs.append("你看準破綻，以巧破力！")
        else:
            deal, take = 0.5, 1.0
            msgs.append("你想以巧取勝，卻被對方識破。")
    elif tactic == "固守":
        deal, take, heal = 0.5, 0.4, b.player_hp_max // 10
        msgs.append("你守住門戶，調勻氣息。")
    elif tactic == "絕招":
        if b.ultimate_used:
            raise ValueError("絕招每場只能施展一次")
        b.ultimate_used = True
        deal = 2.2
        msgs.append("你運起全身功力，施展壓箱絕技！")
    elif tactic == "撤退":
        chance = min(0.9, max(0.1, 0.4 + (pf.spd - ef.spd) * 0.02))
        if rng.random() < chance:
            state.battle = None
            return "flee", msgs + ["你虛晃一招，全身而退。"]
        deal = 0.0
        msgs.append("你想抽身而退，卻被對方纏住！")
    else:
        raise ValueError(f"未知的戰術：{tactic}")
    b.round += 1

    def player_hits() -> None:
        if deal > 0:
            dmg = damage(pf, ef, rng, deal)
            b.enemy_hp -= dmg
            msgs.append(f"你對{ef.name}造成 {dmg} 點傷害。")

    def enemy_hits() -> None:
        dmg = damage(ef, pf, rng, take)
        b.player_hp -= dmg
        msgs.append(f"{ef.name}對你造成 {dmg} 點傷害。")

    for step in ([enemy_hits, player_hits] if ef.spd > pf.spd else [player_hits, enemy_hits]):
        step()
        if b.enemy_hp <= 0:
            state.battle = None
            return "win", msgs + [f"{ef.name}倒地不起，你贏了！"]
        if b.player_hp <= 0:
            state.battle = None
            return "lose", msgs + ["你眼前一黑，敗下陣來……"]
    if heal:
        b.player_hp = min(b.player_hp_max, b.player_hp + heal)
    if b.round >= MAX_KEY_ROUNDS:
        won = b.player_hp / b.player_hp_max >= b.enemy_hp / ef.hp
        state.battle = None
        return ("win" if won else "lose"), msgs + ["雙方力竭，勝負已分。"]
    msgs.append(battle_status(state, content))
    return None, msgs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_combat.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add tianxia/combat.py tests/test_combat.py
git commit -m "feat: add style counters, auto battle and round-based key battles"
```

---

### Task 6: 江湖大勢（門檻、虛擬玩家、結局）

**Files:**
- Create: `tianxia/world.py`
- Test: `tests/test_world.py`

**Interfaces:**
- Consumes: `rules.add_rumor`、`add_chronicle`、`change_trend`、`check_condition`。
- Produces:
  - `check_thresholds(state, content) -> list[str]`：每個門檻只觸發一次；觸發時加世界旗標、寫入傳聞與江湖史；`ends_season` 門檻會呼叫 `end_season`。
  - `sim_tick(state, content, hours, rng) -> list[str]`：每小時、每位虛擬玩家以 `actions_per_day / 24` 的機率行動；`requires_revealed` 的線未浮現前不行動；虛擬玩家不能揭露隱藏線。每小時結束都檢查門檻。
  - `evaluate_ending(state, content) -> Ending`：第一個條件成立的結局。
  - `end_season(state, content) -> list[str]`：重複呼叫回傳 `[]`。

- [ ] **Step 1: Write the failing test**

`tests/test_world.py`:
```python
import random

from tianxia.world import check_thresholds, end_season, evaluate_ending, sim_tick


def test_threshold_fires_once_and_sets_flag(state, content):
    state.world.trends["kou"] = 50
    msgs = check_thresholds(state, content)
    assert "blocked" in state.world.flags
    assert msgs == ["【江湖大事】水寇封江！"]
    assert state.world.rumors[-1].text == "水寇封江！"
    assert state.world.chronicle[-1].text == "水寇封江！"
    assert check_thresholds(state, content) == []


def test_ending_threshold_ends_season(state, content):
    state.world.trends["kou"] = 80
    msgs = check_thresholds(state, content)
    assert state.world.ended
    assert state.world.ending_title == "水寇稱霸"
    assert any("賽季落幕" in m for m in msgs)


def test_evaluate_ending_falls_back(state, content):
    assert evaluate_ending(state, content).id == "default"


def test_end_season_is_idempotent(state, content):
    assert end_season(state, content)
    assert end_season(state, content) == []


def test_sim_players_push_trends_and_spread_rumors(state, content):
    msgs = sim_tick(state, content, 3, random.Random(0))
    assert state.world.trends["kou"] == 33
    assert msgs.count("【江湖傳聞】翻江龍又劫了一艘船。") == 3
    assert state.world.trends["bao"] == 0  # 鬼手要等寶藏線浮現


def test_sim_player_waits_for_revealed_trend(state, content):
    state.world.revealed.add("bao")
    sim_tick(state, content, 2, random.Random(0))
    assert state.world.trends["bao"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_world.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.world'`

- [ ] **Step 3: Write implementation**

`tianxia/world.py`:
```python
"""江湖大勢：大勢線門檻、虛擬玩家、賽季結局。"""
from __future__ import annotations

import random

from .models import Content, Ending
from .rules import add_chronicle, add_rumor, change_trend, check_condition
from .state import GameState


def check_thresholds(state: GameState, content: Content) -> list[str]:
    w = state.world
    msgs: list[str] = []
    if w.ended:
        return msgs
    for th in content.scenario.thresholds:
        if th.id in w.fired_thresholds:
            continue
        value = w.trends.get(th.trend, 0)
        if not (value >= th.value if th.op == ">=" else value <= th.value):
            continue
        w.fired_thresholds.add(th.id)
        w.flags |= set(th.world_flags_add)
        add_rumor(state, th.text)
        add_chronicle(state, th.text)
        msgs.append(f"【江湖大事】{th.text}")
        if th.ends_season:
            msgs += end_season(state, content)
            break
    return msgs


def sim_tick(state: GameState, content: Content, hours: int, rng: random.Random) -> list[str]:
    msgs: list[str] = []
    for _ in range(hours):
        for sim in content.scenario.sim_players:
            if sim.requires_revealed and sim.requires_revealed not in state.world.revealed:
                continue
            if rng.random() >= sim.actions_per_day / 24:
                continue
            for trend_id, delta in sim.trend.items():
                change_trend(state, content, trend_id, delta, reveal=False)
            if sim.rumors and rng.random() < sim.rumor_chance:
                text = rng.choice(sim.rumors).format(name=sim.name)
                add_rumor(state, text)
                msgs.append(f"【江湖傳聞】{text}")
        msgs += check_thresholds(state, content)
        if state.world.ended:
            break
    return msgs


def evaluate_ending(state: GameState, content: Content) -> Ending:
    for ending in content.scenario.endings:
        if check_condition(ending.condition, state):
            return ending
    return content.scenario.endings[-1]


def end_season(state: GameState, content: Content) -> list[str]:
    w = state.world
    if w.ended:
        return []
    ending = evaluate_ending(state, content)
    w.ended = True
    w.ending_title = ending.title
    w.ending_text = ending.text
    add_chronicle(state, f"賽季落幕：{ending.title}")
    return [f"══ 賽季落幕：{ending.title} ══", ending.text]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_world.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tianxia/world.py tests/test_world.py
git commit -m "feat: add world trend thresholds, simulated players and season endings"
```

---
### Task 7: 遊戲門面 `Game`（行動、選項、時間、畫面文字）

**Files:**
- Create: `tianxia/engine.py`
- Modify: `tests/conftest.py`（新增 `game` fixture）
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: Task 3～6 的所有公開函式。
- Produces（介面層與機器人只使用這些）：
  - `class Option(BaseModel)`: `id: str`, `label: str`, `enabled: bool = True`
  - 選項 id 格式：`act:train`、`act:explore`、`act:socialize`、`act:break`、`move:<地點id>`、`choice:<原始索引>`、`tactic:<戰術>`、`season:new`
  - `Game(content, state, rng=None)`、`Game.new(content, name, rng=None) -> Game`
  - `game.options() -> list[Option]`
  - `game.choose(option_id) -> list[str]`：不合法或停用的選項回傳 `["（此刻無法這麼做。）"]` 且不改變狀態。
  - `game.advance(seconds) -> list[str]`、`game.sync(now: float) -> list[str]`
  - `game.seclude(hours, skill_id) -> list[str]`、`game.equip(slot, skill_id | None) -> list[str]`、`game.set_anonymous(value)`、`game.new_season() -> list[str]`
  - `game.status_text()`、`scene_text()`、`location_text()`、`trends_text()`、`rumors_text()`、`chronicle_text()` → `str`（Markdown）
  - `game.skill_choices(slot_type) -> list[tuple[str, str]]`（顯示名稱, 武學 id）
  - 所有對外方法都會把訊息寫入 `state.log`（上限 `config.max_log` 行）。

- [ ] **Step 1: Write the failing test**

在 `tests/conftest.py` 最後加上：
```python
@pytest.fixture
def game(content):
    from tianxia.engine import Game

    content.config.train_event_chance = 0.0
    content.config.train_stat_chance = 0.0
    return Game.new(content, "沈浪", rng=random.Random(0))
```

`tests/test_engine.py`:
```python
import pytest

from conftest import FixedRandom

HOUR = 3600


def ids(game):
    return [o.id for o in game.options()]


def test_new_game(game):
    p = game.state.player
    assert p.location == "town" and p.stamina == 150
    assert p.equipped[1] == "fist"
    assert "測試開始。" in game.state.log


def test_town_options(game):
    assert ids(game) == ["act:explore", "act:socialize", "move:lake"]  # 城鎮沒有敵人，不能歷練


def test_locked_location_hidden_until_flag(game):
    game.choose("move:lake")
    assert "move:cave" not in ids(game)
    game.state.world.flags.add("cave_open")
    assert "move:cave" in ids(game)


def test_move_costs_stamina(game):
    game.choose("move:lake")
    assert game.state.player.location == "lake"
    assert game.state.player.stamina == 145


def test_invalid_option_rejected(game):
    assert game.choose("move:cave") == ["（此刻無法這麼做。）"]
    assert game.state.player.location == "town"


def test_insufficient_stamina_disables_actions(game):
    game.state.player.stamina = 4
    assert all(not o.enabled for o in game.options())
    game.choose("act:explore")
    assert game.state.player.stamina == 4


def test_explore_presents_event_and_resolves_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    assert game.state.pending_event == "drunk"
    assert ids(game) == ["choice:0", "choice:1"]
    game.choose("choice:0")
    assert game.state.pending_event is None
    assert game.state.player.stats["good"] == 2
    assert game.state.world.trends["kou"] == 25
    assert "（檢定成功）" in game.state.log


def test_join_sect_via_socialize(game):
    game.choose("act:socialize")
    game.choose("choice:0")
    assert game.state.player.sect == "cloud"
    assert game.state.player.equipped[1:3] == ["fist", "sword"]


def test_key_battle_flow_lose(game):
    game.choose("move:lake")
    game.choose("act:socialize")
    assert game.state.pending_event == "duel"
    game.choose("choice:0")
    assert ids(game) == ["tactic:強攻", "tactic:巧取", "tactic:固守", "tactic:絕招", "tactic:撤退"]
    for _ in range(10):
        if game.state.battle is None:
            break
        game.choose("tactic:強攻")
    assert game.state.battle is None
    assert game.state.player.stats["silver"] == 40
    assert "你敗了。" in game.state.log


def test_train_wins_and_pushes_trend(game):
    game.choose("move:lake")
    game.choose("act:train")
    p = game.state.player
    assert p.stamina == 135
    assert p.stats["silver"] == 55
    assert p.skills["fist"].exp == 10
    assert game.state.world.trends["kou"] == 29


def test_train_event_chain(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    assert game.state.pending_event == "chain_a"
    game.choose("choice:0")
    assert game.state.pending_event == "chain_b"


def test_stamina_regenerates_with_time(game):
    game.state.player.stamina = 0
    game.advance(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_sync_uses_real_clock_and_time_scale(game):
    game.content.config.time_scale = 60
    game.state.player.stamina = 0
    game.sync(1000.0)  # 第一次只記下現實時間
    game.sync(1010.0)  # 10 秒 × 60 倍 = 600 秒
    assert game.state.world.time == pytest.approx(600)
    assert game.state.player.stamina == pytest.approx(2)


def test_seclusion_completes_and_grants_exp(game):
    game.seclude(4, "fist")
    assert ids(game) == ["act:break"]
    game.advance(4 * HOUR)
    assert game.state.player.busy_until is None
    assert game.state.player.skills["fist"].level == 2  # 4 小時 × 20 × (1 + 5/20) = 100


def test_break_seclusion_early(game):
    game.seclude(4, "fist")
    game.advance(HOUR)
    game.choose("act:break")
    assert game.state.player.busy_until is None
    assert game.state.player.skills["fist"].exp == 25


def test_season_ends_by_time(game):
    game.advance(2 * 24 * HOUR)
    w = game.state.world
    assert w.ended and w.ending_title == "風雨飄搖"
    assert "blocked" in w.flags  # 翻江龍 48 小時把寇亂推到 78
    assert ids(game) == ["season:new"]


def test_new_season_resets(game):
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert not game.state.world.ended
    assert game.state.world.trends["kou"] == 30
    assert game.state.player.name == "沈浪"


def test_equip_rules(game):
    game.choose("act:socialize")
    game.choose("choice:0")  # 學到 sword，放進第二個外功欄
    game.equip(1, "sword")
    assert game.state.player.equipped[1:3] == ["sword", None]
    game.equip(0, "sword")  # 欄位不符，不變
    assert game.state.player.equipped[0] is None
    game.equip(1, None)
    assert game.state.player.equipped[1] is None


def test_texts_render(game):
    assert "沈浪" in game.status_text()
    assert "小鎮" in game.scene_text()
    assert "寇亂" in game.trends_text() and "寶藏" not in game.trends_text()
    assert game.rumors_text() == "（尚無傳聞。）"
    game.choose("act:explore")
    assert "醉漢" in game.scene_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.engine'`

- [ ] **Step 3: Write implementation**

`tianxia/engine.py`:
```python
"""遊戲門面：介面層唯一需要呼叫的類別。負責行動、選項、時間流逝與畫面文字。"""
from __future__ import annotations

import random

from pydantic import BaseModel

from .combat import (
    TACTICS, auto_battle, battle_round, battle_status, enemy_fighter, player_fighter, start_battle,
)
from .events import choice_label, pick_event, visible_choices
from .models import Content, Effect, Event
from .rules import add_skill_exp, apply_effect, change_trend, learn_skill, roll_check
from .state import EQUIP_SLOTS, GameState, Rumor, new_game_state
from .world import check_thresholds, end_season, sim_tick

HOUR = 3600
DAY = 86400


class Option(BaseModel):
    id: str
    label: str
    enabled: bool = True


class Game:
    def __init__(self, content: Content, state: GameState, rng: random.Random | None = None):
        self.content = content
        self.state = state
        self.rng = rng or random.Random()

    @classmethod
    def new(cls, content: Content, name: str, rng: random.Random | None = None) -> Game:
        game = cls(content, new_game_state(content, name), rng)
        for skill_id in content.config.starter_skills:
            learn_skill(game.state, content, skill_id)
        game._log([f"══ {content.scenario.name} ══", content.scenario.intro, game.location_text()])
        return game

    # ── 時間 ──────────────────────────────────────────────

    def sync(self, now: float) -> list[str]:
        """把現實經過的時間（乘上 time_scale）推進到遊戲裡。第一次呼叫只記錄時間點。"""
        if self.state.last_real is None:
            self.state.last_real = now
            return []
        elapsed = max(0.0, now - self.state.last_real) * self.content.config.time_scale
        self.state.last_real = now
        return self.advance(elapsed)

    def advance(self, seconds: float) -> list[str]:
        msgs: list[str] = []
        remaining = seconds
        while remaining > 0 and not self.state.world.ended:
            step = min(remaining, HOUR)
            remaining -= step
            msgs += self._advance_step(step)
        return self._log(msgs)

    def _advance_step(self, seconds: float) -> list[str]:
        cfg, p, w = self.content.config, self.state.player, self.state.world
        w.time += seconds
        p.stamina = min(cfg.stamina_max, p.stamina + seconds / cfg.stamina_regen_seconds)
        msgs: list[str] = []
        if p.busy_until is not None and w.time >= p.busy_until:
            msgs += self._finish_seclusion(p.busy_until)
        w.sim_accum += seconds
        hours = int(w.sim_accum // HOUR)
        if hours:
            w.sim_accum -= hours * HOUR
            msgs += sim_tick(self.state, self.content, hours, self.rng)
        if not w.ended and w.time >= cfg.season_days * DAY:
            msgs += end_season(self.state, self.content)
        return msgs

    # ── 選項 ──────────────────────────────────────────────

    def options(self) -> list[Option]:
        s, c = self.state, self.content
        if s.world.ended:
            return [Option(id="season:new", label="開啟新的賽季")]
        if s.battle:
            return [
                Option(id=f"tactic:{t}", label=t, enabled=not (t == "絕招" and s.battle.ultimate_used))
                for t in TACTICS
            ]
        if s.pending_event:
            event = c.events[s.pending_event]
            return [Option(id=f"choice:{i}", label=choice_label(ch, s)) for i, ch in visible_choices(event, s)]
        if s.player.busy_until is not None:
            return [Option(id="act:break", label="提前出關")]
        loc = c.locations[s.player.location]
        cost = c.config.action_cost
        opts = []
        if loc.enemies:
            opts.append(self._cost_option("act:train", "歷練", cost["train"]))
        opts.append(self._cost_option("act:explore", "探索", cost["explore"]))
        opts.append(self._cost_option("act:socialize", "交遊", cost["socialize"]))
        for dest_id in loc.connections:
            dest = c.locations[dest_id]
            if dest.unlock_flag and dest.unlock_flag not in s.world.flags:
                continue
            opts.append(self._cost_option(f"move:{dest_id}", f"前往 {dest.name}", dest.move_cost))
        return opts

    def _cost_option(self, option_id: str, label: str, cost: int) -> Option:
        return Option(
            id=option_id, label=f"{label}（體力 {cost}）", enabled=self.state.player.stamina >= cost
        )

    def choose(self, option_id: str) -> list[str]:
        option = {o.id: o for o in self.options()}.get(option_id)
        if option is None or not option.enabled:
            return self._log(["（此刻無法這麼做。）"])
        kind, _, arg = option_id.partition(":")
        if kind == "act":
            msgs = self._act(arg)
        elif kind == "move":
            msgs = self._move(arg)
        elif kind == "choice":
            msgs = self._choose(int(arg))
        elif kind == "tactic":
            msgs = self._tactic(arg)
        else:
            msgs = self.new_season()
        msgs += check_thresholds(self.state, self.content)
        return self._log(msgs)

    # ── 行動 ──────────────────────────────────────────────

    def _act(self, what: str) -> list[str]:
        cost = self.content.config.action_cost
        if what == "break":
            return self._finish_seclusion(self.state.world.time)
        self.state.player.stamina -= cost[what]
        if what == "train":
            return self._train()
        if what == "explore":
            return self._encounter("explore", "你四處走走，一無所獲。")
        return self._encounter("socialize", "此地無人可訪，你只好悻悻離去。")

    def _encounter(self, action: str, nothing: str) -> list[str]:
        event = pick_event(self.state, self.content, action, self.rng)
        return self._present(event) if event else [nothing]

    def _present(self, event: Event) -> list[str]:
        self.state.pending_event = event.id
        self.state.player.seen_events.add(event.id)
        head = f"✦ 奇遇：{event.title}" if event.qiyu else f"【{event.title}】"
        return [head, event.text]

    def _train(self) -> list[str]:
        s, c = self.state, self.content
        p = s.player
        loc = c.locations[p.location]
        enemy = c.enemies[self.rng.choice(loc.enemies)]
        won, rounds = auto_battle(player_fighter(s, c), enemy_fighter(enemy), self.rng)
        if won:
            msgs = [f"你在{loc.name}與{enemy.name}交手 {rounds} 回合，將其擊退。"]
            if enemy.reward_silver:
                p.stats["silver"] += enemy.reward_silver
                msgs.append(f"銀兩 +{enemy.reward_silver}")
            if self.rng.random() < c.config.train_stat_chance:
                key = self.rng.choice(["str", "agi", "con"])
                p.stats[key] += 1
                msgs.append(f"{c.config.stat_names[key]} +1")
            for skill_id in p.equipped:
                if skill_id and c.skills[skill_id].slot == "外功":
                    msgs += add_skill_exp(s, c, skill_id, c.config.train_skill_exp)
            for trend_id, delta in loc.train_trend.items():
                msgs += change_trend(s, c, trend_id, delta)
        else:
            loss = p.stats["silver"] // 10
            p.stats["silver"] -= loss
            msgs = [f"你在{loc.name}與{enemy.name}交手 {rounds} 回合，不敵敗走，失落銀兩 {loss}。"]
        if self.rng.random() < c.config.train_event_chance:
            event = pick_event(s, c, "train", self.rng)
            if event:
                msgs += self._present(event)
        return msgs

    def _move(self, dest_id: str) -> list[str]:
        dest = self.content.locations[dest_id]
        self.state.player.stamina -= dest.move_cost
        self.state.player.location = dest_id
        return [self.location_text()]

    def _choose(self, index: int) -> list[str]:
        s, c = self.state, self.content
        event = c.events[s.pending_event]
        choice = event.choices[index]
        s.pending_event = None
        msgs = [f"▸ {choice.text}"]
        if choice.combat:
            return msgs + start_battle(s, c, choice.combat, event.id, index)
        if choice.check:
            success = roll_check(choice.check, s, self.rng)
            msgs.append("（檢定成功）" if success else "（檢定失敗）")
            return msgs + self._apply(choice.effect if success else choice.fail_effect)
        return msgs + self._apply(choice.effect)

    def _tactic(self, tactic: str) -> list[str]:
        s, c = self.state, self.content
        event_id, index = s.battle.event_id, s.battle.choice_index
        outcome, msgs = battle_round(s, c, tactic, self.rng)
        if outcome is None or outcome == "flee":
            return msgs
        choice = c.events[event_id].choices[index]
        return msgs + self._apply(choice.effect if outcome == "win" else choice.fail_effect)

    def _apply(self, effect: Effect) -> list[str]:
        msgs = apply_effect(effect, self.state, self.content)
        if effect.next_event:
            msgs += self._present(self.content.events[effect.next_event])
        return msgs

    # ── 閉關、武學、設定 ─────────────────────────────────

    def _idle(self) -> bool:
        s = self.state
        return (
            not s.world.ended and s.battle is None and s.pending_event is None
            and s.player.busy_until is None
        )

    def seclude(self, hours: int, skill_id: str) -> list[str]:
        p = self.state.player
        if not self._idle():
            return self._log(["你現在無法閉關。"])
        if skill_id not in p.skills:
            return self._log(["你尚未習得這門武學。"])
        hours = max(1, min(12, int(hours)))
        p.busy_until = self.state.world.time + hours * HOUR
        p.seclusion_start = self.state.world.time
        p.seclusion_skill = skill_id
        return self._log([f"你閉關苦修【{self.content.skills[skill_id].name}】，預計 {hours} 小時後出關。"])

    def _finish_seclusion(self, end_time: float) -> list[str]:
        p, cfg = self.state.player, self.content.config
        hours = (end_time - p.seclusion_start) / HOUR
        amount = round(hours * cfg.seclusion_exp_per_hour * (1 + p.stats["wis"] / 20))
        skill_id = p.seclusion_skill
        p.busy_until = None
        p.seclusion_skill = None
        msgs = [f"你結束閉關（{hours:.1f} 小時），【{self.content.skills[skill_id].name}】修為 +{amount}。"]
        return msgs + add_skill_exp(self.state, self.content, skill_id, amount)

    def equip(self, slot: int, skill_id: str | None) -> list[str]:
        p, c = self.state.player, self.content
        if self.state.battle is not None:
            return self._log(["戰鬥中無法更換武學。"])
        if skill_id:
            if skill_id not in p.skills:
                return self._log(["你尚未習得這門武學。"])
            if c.skills[skill_id].slot != EQUIP_SLOTS[slot]:
                return self._log([f"【{c.skills[skill_id].name}】不能放在{EQUIP_SLOTS[slot]}欄位。"])
            for i, other in enumerate(p.equipped):
                if other == skill_id and i != slot:
                    p.equipped[i] = None
        p.equipped[slot] = skill_id or None
        label = c.skills[skill_id].name if skill_id else "（空）"
        return self._log([f"{EQUIP_SLOTS[slot]}欄位：{label}"])

    def set_anonymous(self, value: bool) -> None:
        self.state.player.anonymous = bool(value)

    def new_season(self) -> list[str]:
        self.state = Game.new(self.content, self.state.player.name, self.rng).state
        return []

    def skill_choices(self, slot_type: str) -> list[tuple[str, str]]:
        return [
            (f"{self.content.skills[sid].name} 第{prog.level}成", sid)
            for sid, prog in self.state.player.skills.items()
            if self.content.skills[sid].slot == slot_type
        ]

    # ── 畫面文字 ──────────────────────────────────────────

    def location_text(self) -> str:
        loc = self.content.locations[self.state.player.location]
        return f"【{loc.name}】危險 {'★' * loc.danger}\n\n{loc.description}"

    def scene_text(self) -> str:
        s, c = self.state, self.content
        if s.world.ended:
            return f"## {s.world.ending_title}\n\n{s.world.ending_text}"
        if s.battle:
            return f"⚔ {battle_status(s, c)}"
        if s.pending_event:
            event = c.events[s.pending_event]
            return f"**{event.title}**\n\n{event.text}"
        return self.location_text()

    def status_text(self) -> str:
        s, c = self.state, self.content
        p, w = s.player, s.world
        names = c.config.stat_names
        sect = c.sects[p.sect].name if p.sect else "散人"
        day = int(w.time // DAY) + 1
        clock = f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}"
        lines = [
            f"### {p.name}　·　{sect}" + ("（匿名行走）" if p.anonymous else ""),
            f"📍 {c.locations[p.location].name}　⏳ 第 {day} 天 {clock}（本季共 {c.config.season_days:g} 天）",
            f"**體力** {int(p.stamina)} / {c.config.stamina_max}",
            "　".join(f"{names[k]} {p.stats[k]}" for k in ("str", "agi", "con", "wis")),
            "　".join(f"{names[k]} {p.stats[k]}" for k in ("silver", "good", "evil", "fame")),
            "**武學**",
        ]
        for slot, skill_id in zip(EQUIP_SLOTS, p.equipped):
            if skill_id:
                skill = c.skills[skill_id]
                lines.append(f"- {slot}：{skill.name}（{skill.style}）第{p.skills[skill_id].level}成")
            else:
                lines.append(f"- {slot}：（空）")
        if p.busy_until is not None:
            lines.append(f"🧘 閉關中，約 {(p.busy_until - w.time) / HOUR:.1f} 小時後出關")
        return "\n\n".join(lines)

    def trends_text(self) -> str:
        w = self.state.world
        parts = []
        for trend in self.content.scenario.trends:
            if trend.id not in w.revealed:
                continue
            value = w.trends[trend.id]
            bar = "█" * (value // 5) + "░" * (20 - value // 5)
            parts.append(f"**{trend.name}** {value}/100\n\n`{bar}`\n\n{trend.desc}")
        if w.ended:
            parts.append(f"## 結局：{w.ending_title}\n\n{w.ending_text}")
        return "\n\n".join(parts) or "（江湖暫時風平浪靜。）"

    def rumors_text(self, limit: int = 30) -> str:
        return _timeline(self.state.world.rumors[-limit:][::-1]) or "（尚無傳聞。）"

    def chronicle_text(self) -> str:
        return _timeline(self.state.world.chronicle) or "（江湖史尚無記載。）"

    def _log(self, msgs: list[str]) -> list[str]:
        log = self.state.log
        log.extend(msgs)
        overflow = len(log) - self.content.config.max_log
        if overflow > 0:
            del log[:overflow]
        return msgs


def _timeline(entries: list[Rumor]) -> str:
    return "\n\n".join(f"第{int(e.time // DAY) + 1}天　{e.text}" for e in entries)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`
Expected: 19 passed

- [ ] **Step 5: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add tianxia/engine.py tests/conftest.py tests/test_engine.py
git commit -m "feat: add Game facade with actions, options, time flow and text views"
```

---

### Task 8: 存讀檔與舊存檔相容

**Files:**
- Create: `tianxia/save.py`
- Modify: `tianxia/engine.py`（`Game.__init__` 呼叫新的 `_drop_stale_references()`）
- Test: `tests/test_save.py`

**Interfaces:**
- Consumes: `GameState`、`Game`。
- Produces:
  - `save_game(state, path: Path) -> None`（先寫暫存檔再取代，避免寫到一半損毀）
  - `load_game(path: Path) -> GameState`
  - `Game.__init__` 會丟棄已不存在於內容檔的事件、戰鬥、地點、武學引用。原因：原型期會一直修改內容檔，舊存檔不能因此當機。

- [ ] **Step 1: Write the failing test**

`tests/test_save.py`:
```python
from tianxia.engine import Game
from tianxia.save import load_game, save_game
from tianxia.state import SkillProgress


def test_roundtrip(tmp_path, game):
    game.choose("act:socialize")
    game.choose("choice:0")
    game.state.world.flags.add("blocked")
    path = tmp_path / "saves" / "沈浪.json"
    save_game(game.state, path)
    assert load_game(path) == game.state


def test_stale_references_are_dropped(content, game):
    s = game.state
    s.pending_event = "removed_event"
    s.player.location = "removed_place"
    s.player.skills["removed_skill"] = SkillProgress()
    s.player.equipped[1] = "removed_skill"
    fresh = Game(content, s)
    assert fresh.state.pending_event is None
    assert fresh.state.player.location == "town"
    assert fresh.state.player.equipped[1] is None
    assert "removed_skill" not in fresh.state.player.skills
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_save.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.save'`

- [ ] **Step 3: Write implementation**

`tianxia/save.py`:
```python
"""存讀檔：整個 GameState 直接序列化成 JSON。"""
from __future__ import annotations

from pathlib import Path

from .state import GameState


def save_game(state: GameState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
    tmp.replace(path)


def load_game(path: Path) -> GameState:
    return GameState.model_validate_json(Path(path).read_text(encoding="utf-8"))
```

在 `tianxia/engine.py` 的 `Game.__init__` 最後加一行：
```python
        self._drop_stale_references()
```

並在 `Game` 類別中（`new` 方法之後）加上：
```python
    def _drop_stale_references(self) -> None:
        """內容檔改版後，舊存檔可能引用已刪除的事件、地點或武學；丟掉這些引用以免當機。"""
        s, c = self.state, self.content
        p = s.player
        if s.pending_event and s.pending_event not in c.events:
            s.pending_event = None
        if s.battle and (s.battle.enemy_id not in c.enemies or s.battle.event_id not in c.events):
            s.battle = None
        if p.location not in c.locations:
            p.location = c.scenario.start_location
        p.skills = {k: v for k, v in p.skills.items() if k in c.skills}
        p.equipped = [sid if sid in p.skills else None for sid in p.equipped]
        if p.seclusion_skill and p.seclusion_skill not in p.skills:
            p.busy_until = None
            p.seclusion_skill = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通過（包含 `tests/test_save.py` 的 2 個測試）

- [ ] **Step 5: Commit**

```bash
git add tianxia/save.py tianxia/engine.py tests/test_save.py
git commit -m "feat: add save/load and tolerate stale references in old saves"
```

---
### Task 9: 正式內容（一）：設定、劇本、地圖、武學、門派、敵人

**Files:**
- Create: `content/config.json`, `content/scenario.json`, `content/locations.json`, `content/skills.json`, `content/sects.json`, `content/enemies.json`, `content/events/.gitkeep`
- Test: `tests/test_real_content.py`

**Interfaces:**
- Consumes: `load_content`。
- Produces: 劇本「江南風雨」。後續事件檔會引用的 id：
  - 地點：`yangzhou` `shouxihu` `yangzhou_jiao` `gaoyou` `guazhou` `zhenjiang` `jinshan` `jiangning_road` `jinling` `qinhuai` `yuhuatai` `qixia_foot` `qixia_sect` `qixia_back` `canglong` `changzhou` `wuxi` `xuantie` `taihu_north` `taihu_isle` `suzhou` `hanshan`
  - 地點 tags：`城鎮` `湖畔` `野外` `水路` `渡口` `寺院` `官道` `山林` `門派` `洞窟` `水寨`
  - 大勢線：`kou`（公開）、`bao`（隱藏）；世界旗標：`canal_blocked` `kou_win` `kou_crushed` `bao_half` `cave_open` `treasure_taken` `fjl_defeated`
  - 門派：`qixia`、`xuantie`
  - 武學：`tuna` `changquan` `qixia_xinjue` `liuyun` `luoying` `yanhui` `xuantie_gong` `tiesha` `lieshi` `zhuifeng` `feihua` `hunyuan`
  - 敵人：`dipi` `shanzei` `yelang` `heixiong` `louluo` `shuikou` `toumu` `fanjianglong` `guishou` `shoumu` `xuantie_dizi`

**平衡說明（寫給之後調數值的人）**：翻江龍每天約推寇亂 +8、沈青約 −3，玩家什麼都不做的話，寇亂約第 4 天到 50（封鎖運河）、第 10 天到 80（水寇稱霸，賽季提早結束）。玩家在高郵湖、瓜洲渡、太湖一帶歷練或處理水寇事件可以壓低它。寶藏線浮現後，鬼手劉三每天約 +6。

- [ ] **Step 1: Write the failing test**

`tests/test_real_content.py`:
```python
from collections import deque
from pathlib import Path

from tianxia.content import load_content

CONTENT_DIR = Path(__file__).parent.parent / "content"


def test_real_content_loads():
    c = load_content(CONTENT_DIR)
    assert 20 <= len(c.locations) <= 30
    assert sum(loc.important for loc in c.locations.values()) >= 5
    assert {t.id for t in c.scenario.trends} == {"kou", "bao"}


def test_all_locations_reachable_from_start():
    c = load_content(CONTENT_DIR)
    start = c.scenario.start_location
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in c.locations[queue.popleft()].connections:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(c.locations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_real_content.py -v`
Expected: FAIL with `FileNotFoundError`（content/config.json 不存在）

- [ ] **Step 3: Write the content files**

`content/events/.gitkeep`：空檔案。

`content/config.json`:
```json
{
  "stamina_max": 150,
  "stamina_regen_seconds": 300,
  "action_cost": {"explore": 10, "train": 10, "socialize": 5},
  "time_scale": 1.0,
  "season_days": 14,
  "seclusion_exp_per_hour": 20,
  "skill_exp_per_level": 100,
  "train_skill_exp": 10,
  "train_stat_chance": 0.3,
  "train_event_chance": 0.3,
  "qiyu_weight_multiplier": 1.5,
  "starter_skills": ["tuna", "changquan"],
  "start_stats": {"str": 5, "agi": 5, "con": 5, "wis": 5, "silver": 50, "good": 0, "evil": 0, "fame": 0},
  "max_log": 200
}
```

`content/scenario.json`:
```json
{
  "id": "jiangnan_storm",
  "name": "江南風雨",
  "intro": "大胤末年，朝廷無力南顧。太湖水寨大當家「翻江龍」聚眾數千，劫掠運河商船；又有流言說，前朝覆滅時，有一批寶藏藏在江南某處山中。你背著一個包袱，站在揚州城門口——江湖，就從這裡開始。",
  "start_location": "yangzhou",
  "trends": [
    {"id": "kou", "name": "太湖寇亂", "desc": "水寇勢力越大，江南越亂。到 50 會封鎖運河，到 80 水寇將攻陷鎮江。剿寇能讓它下降。", "start": 30},
    {"id": "bao", "name": "前朝寶藏", "desc": "藏寶圖的拼湊進度。湊齊時，寶藏所在將會現世。", "start": 0, "hidden": true}
  ],
  "thresholds": [
    {"id": "kou_50", "trend": "kou", "op": ">=", "value": 50, "text": "太湖水寇封鎖運河，揚州至鎮江的商路斷絕，沿岸人心惶惶！", "world_flags_add": ["canal_blocked"]},
    {"id": "kou_80", "trend": "kou", "op": ">=", "value": 80, "text": "翻江龍率水寨大軍攻破鎮江渡口，江南從此落入水寇之手！", "world_flags_add": ["kou_win"], "ends_season": true},
    {"id": "kou_10", "trend": "kou", "op": "<=", "value": 10, "text": "太湖水寨被各路俠客踏平，翻江龍下落不明，運河重歸太平。", "world_flags_add": ["kou_crushed"]},
    {"id": "bao_50", "trend": "bao", "op": ">=", "value": 50, "text": "江湖傳言：前朝藏寶圖已拼出大半，各路人馬湧向棲霞山。", "world_flags_add": ["bao_half"]},
    {"id": "bao_100", "trend": "bao", "op": ">=", "value": 100, "text": "藏寶圖終於湊齊！棲霞後山的「藏龍洞」現世，洞口有人把守。", "world_flags_add": ["cave_open"]}
  ],
  "sim_players": [
    {"name": "翻江龍", "actions_per_day": 8, "trend": {"kou": 1}, "rumor_chance": 0.25, "rumors": [
      "太湖水寇又劫了一艘官船，據說是{name}親自帶的人。",
      "{name}在太湖放話：「江南的水路，從今往後姓翻！」",
      "運河上又有商船失蹤，人人都說是{name}的手筆。"
    ]},
    {"name": "白衣劍客沈青", "actions_per_day": 3, "trend": {"kou": -1}, "rumor_chance": 0.3, "rumors": [
      "{name}在太湖邊獨挑水寇十七人，劍不染塵。",
      "有人看見{name}在鎮江渡口護送難民過江。"
    ]},
    {"name": "鬼手劉三", "actions_per_day": 3, "trend": {"bao": 2}, "requires_revealed": "bao", "rumor_chance": 0.3, "rumors": [
      "有人看見{name}在棲霞山一帶鬼鬼祟祟地挖土。",
      "{name}在金陵黑市高價收購前朝古物。"
    ]}
  ],
  "endings": [
    {"id": "kou_win", "title": "水寇稱霸", "text": "鎮江陷落，翻江龍坐擁運河。江南的商旅從此要向水寨納貢，而這一季的俠客們，只能在酒館裡嘆息。", "condition": {"world_flags_all": ["kou_win"]}},
    {"id": "peace_treasure", "title": "江南太平，寶藏重光", "text": "水寨覆滅，前朝寶藏也重見天日。這一季的江南，是俠客的江南。", "condition": {"world_flags_all": ["kou_crushed", "treasure_taken"]}},
    {"id": "treasure", "title": "寶藏現世，亂局未平", "text": "寶藏被人取走，江湖為之震動；然而太湖水寇仍在，江南的風雨還遠未停歇。", "condition": {"world_flags_all": ["treasure_taken"]}},
    {"id": "peace", "title": "寇平而寶藏成謎", "text": "運河重歸太平，但那批前朝寶藏，依舊是酒館裡說不完的傳說。", "condition": {"world_flags_all": ["kou_crushed"]}},
    {"id": "default", "title": "江南依舊風雨飄搖", "text": "這一季，沒有人能徹底改變江南。水寇與俠客互有勝負，寶藏的傳說仍在流傳。"}
  ]
}
```

`content/locations.json`:
```json
[
  {"id": "yangzhou", "name": "揚州城", "important": true, "tags": ["城鎮"], "connections": ["shouxihu", "yangzhou_jiao", "guazhou"],
   "description": "運河與長江交匯的繁華大城，鹽商雲集，酒樓林立。南來北往的江湖人，大多會在這裡歇腳。"},
  {"id": "shouxihu", "name": "瘦西湖", "tags": ["湖畔"], "connections": ["yangzhou"],
   "description": "湖面狹長如帶，兩岸垂柳拂水，畫舫往來。遊人如織，也是三教九流混雜之地。"},
  {"id": "yangzhou_jiao", "name": "揚州城郊", "tags": ["野外"], "connections": ["yangzhou", "gaoyou"], "enemies": ["dipi", "shanzei"],
   "description": "出了城便是一片荒野，官道兩旁雜草叢生，常有地痞與山賊出沒。"},
  {"id": "gaoyou", "name": "高郵湖", "tags": ["湖畔", "水路"], "danger": 2, "connections": ["yangzhou_jiao"], "enemies": ["louluo", "shuikou"], "train_trend": {"kou": -1},
   "description": "煙波浩渺的大湖，蘆葦深處藏著水寇的小船。漁民們已經很久不敢夜裡下湖了。"},
  {"id": "guazhou", "name": "瓜洲渡", "important": true, "tags": ["渡口", "水路"], "connections": ["yangzhou", "zhenjiang"], "enemies": ["louluo"], "train_trend": {"kou": -1},
   "description": "揚州南面的古渡口，隔江與鎮江相望。渡船上擠滿了商旅，水寇的探子也混在其中。"},
  {"id": "zhenjiang", "name": "鎮江渡口", "important": true, "tags": ["渡口", "城鎮"], "connections": ["guazhou", "jinshan", "jiangning_road", "changzhou"],
   "description": "扼守長江與運河的咽喉，城牆高厚，是江南的門戶。若鎮江失守，整條運河都將落入他人之手。"},
  {"id": "jinshan", "name": "金山寺", "tags": ["寺院"], "connections": ["zhenjiang"],
   "description": "建在江心小山上的古寺，鐘聲可傳數里。寺中老方丈據說年輕時也是江湖中人。"},
  {"id": "jiangning_road", "name": "江寧官道", "tags": ["官道", "野外"], "connections": ["zhenjiang", "jinling"], "enemies": ["shanzei"],
   "description": "通往金陵的官道，路旁不時可見被劫掠後丟棄的車駕。"},
  {"id": "jinling", "name": "金陵城", "important": true, "tags": ["城鎮"], "connections": ["jiangning_road", "qinhuai", "yuhuatai", "qixia_foot"],
   "description": "六朝古都，龍蟠虎踞。城中國子監、古董鋪、黑市應有盡有，各路消息在這裡交匯。"},
  {"id": "qinhuai", "name": "秦淮河畔", "tags": ["城鎮", "湖畔"], "connections": ["jinling"],
   "description": "槳聲燈影，畫舫笙歌。這裡是金陵最熱鬧的銷金窟，也是打聽消息的好地方。"},
  {"id": "yuhuatai", "name": "雨花台", "tags": ["野外"], "connections": ["jinling"], "enemies": ["dipi"],
   "description": "城南的小山崗，遍地是五色的雨花石。近來常有人在這一帶挖土，不知在找什麼。"},
  {"id": "qixia_foot", "name": "棲霞山腳", "tags": ["山林"], "connections": ["jinling", "qixia_sect", "qixia_back"], "enemies": ["yelang"],
   "description": "楓林如火的山腳，山道蜿蜒而上。林中偶有狼嚎。"},
  {"id": "qixia_sect", "name": "棲霞劍派", "important": true, "tags": ["門派"], "connections": ["qixia_foot"],
   "description": "山腰上的劍派，白牆青瓦，演武場上劍光閃爍。門規森嚴，弟子們個個行止端正。"},
  {"id": "qixia_back", "name": "棲霞後山", "tags": ["山林"], "danger": 2, "move_cost": 8, "connections": ["qixia_foot", "canglong"], "enemies": ["yelang", "heixiong"],
   "description": "人跡罕至的深山，古木參天，岩壁陡峭。傳說前朝曾在這裡開鑿過什麼。"},
  {"id": "canglong", "name": "藏龍洞", "important": true, "tags": ["洞窟"], "danger": 3, "move_cost": 8, "unlock_flag": "cave_open", "connections": ["qixia_back"],
   "description": "藏在後山峭壁間的石洞，洞口被藤蔓遮掩。洞內寒氣逼人，深處隱約有火光。"},
  {"id": "changzhou", "name": "常州府", "tags": ["城鎮"], "connections": ["zhenjiang", "wuxi"],
   "description": "運河邊的府城，米行、布莊一家挨著一家，是江南的糧倉之一。"},
  {"id": "wuxi", "name": "無錫", "tags": ["城鎮"], "connections": ["changzhou", "xuantie", "taihu_north"],
   "description": "太湖北岸的城鎮，碼頭上停滿漁船。城外不遠便是玄鐵門的山門。"},
  {"id": "xuantie", "name": "玄鐵門", "important": true, "tags": ["門派"], "connections": ["wuxi"],
   "description": "無錫城外的武館式門派，演武場上盡是赤膊練功的漢子，呼喝聲震天。"},
  {"id": "taihu_north", "name": "太湖北岸", "tags": ["湖畔", "水路"], "danger": 2, "connections": ["wuxi", "suzhou", "taihu_isle"], "enemies": ["louluo", "shuikou"], "train_trend": {"kou": -1},
   "description": "太湖的北岸，湖面一望無際。水寇的快船時常出沒，岸邊的漁村十室九空。"},
  {"id": "taihu_isle", "name": "太湖水寨", "tags": ["水寨"], "danger": 3, "move_cost": 10, "connections": ["taihu_north"], "enemies": ["shuikou", "toumu"], "train_trend": {"kou": -2},
   "description": "湖心島上的水寨，木柵高聳，旌旗獵獵。這是翻江龍的老巢，擅闖者九死一生。"},
  {"id": "suzhou", "name": "蘇州城", "important": true, "tags": ["城鎮"], "connections": ["taihu_north", "hanshan"],
   "description": "園林精巧、水巷縱橫的富庶之城。知府衙門就設在這裡，官府平寇的告示貼滿了城門。"},
  {"id": "hanshan", "name": "寒山寺", "tags": ["寺院"], "connections": ["suzhou"],
   "description": "蘇州城外的古寺，楓橋夜泊，鐘聲悠遠。"}
]
```

`content/skills.json`:
```json
[
  {"id": "tuna", "name": "吐納法", "slot": "內功", "style": "無", "power": 8, "desc": "最粗淺的調息法門，人人都會。"},
  {"id": "changquan", "name": "長拳", "slot": "外功", "style": "剛", "power": 10, "desc": "街頭巷尾都有人練的拳法。"},
  {"id": "qixia_xinjue", "name": "棲霞心訣", "slot": "內功", "style": "柔", "power": 16, "sect": "qixia", "desc": "棲霞劍派的入門內功，綿長不絕。"},
  {"id": "liuyun", "name": "流雲劍法", "slot": "外功", "style": "柔", "power": 16, "sect": "qixia", "desc": "劍勢如流雲舒卷，以柔化剛。"},
  {"id": "luoying", "name": "落英劍式", "slot": "外功", "style": "快", "power": 22, "sect": "qixia", "desc": "棲霞劍派的進階劍法，劍光如落英繽紛。"},
  {"id": "yanhui", "name": "燕回翔", "slot": "輕功", "style": "快", "power": 18, "sect": "qixia", "desc": "棲霞劍派的輕功，身法輕盈如燕。"},
  {"id": "xuantie_gong", "name": "玄鐵功", "slot": "內功", "style": "剛", "power": 18, "sect": "xuantie", "desc": "玄鐵門的護體內功，練到深處刀槍難入。"},
  {"id": "tiesha", "name": "鐵砂掌", "slot": "外功", "style": "剛", "power": 18, "sect": "xuantie", "desc": "玄鐵門的看家掌法，一掌下去碑裂石碎。"},
  {"id": "lieshi", "name": "裂石拳", "slot": "外功", "style": "剛", "power": 24, "sect": "xuantie", "desc": "玄鐵門的進階拳法，剛猛無儔。"},
  {"id": "zhuifeng", "name": "追風步", "slot": "輕功", "style": "快", "power": 12, "desc": "鏢局裡流傳的輕功，講究腳下快。"},
  {"id": "feihua", "name": "飛花摘葉", "slot": "外功", "style": "巧", "power": 22, "desc": "摘葉飛花皆可傷人的奇門手法，只傳無門無派之人。"},
  {"id": "hunyuan", "name": "混元一氣", "slot": "內功", "style": "無", "power": 26, "desc": "前朝秘藏的內功心法，渾厚無比。"}
]
```

`content/sects.json`:
```json
[
  {"id": "qixia", "name": "棲霞劍派", "location": "qixia_sect", "alignment": "正", "starter_skills": ["qixia_xinjue", "liuyun"],
   "desc": "棲霞山上的劍派，劍法以柔克剛，門規嚴明，不容門下作惡。"},
  {"id": "xuantie", "name": "玄鐵門", "location": "xuantie", "alignment": "中", "starter_skills": ["xuantie_gong", "tiesha"],
   "desc": "無錫城外的外家門派，以剛猛拳掌見長，只問強弱，不問出身。"}
]
```

`content/enemies.json`:
```json
[
  {"id": "dipi", "name": "地痞無賴", "desc": "遊手好閒的地痞，專挑外地人下手。", "hp": 45, "atk": 9, "dfn": 4, "spd": 8, "style": "無", "reward_silver": 5},
  {"id": "shanzei", "name": "劫道山賊", "desc": "蒙著臉的山賊，手持鬼頭刀。", "hp": 70, "atk": 14, "dfn": 8, "spd": 10, "style": "剛", "reward_silver": 10},
  {"id": "yelang", "name": "野狼", "desc": "餓得眼睛發綠的野狼。", "hp": 50, "atk": 13, "dfn": 4, "spd": 18, "style": "快"},
  {"id": "heixiong", "name": "黑熊", "desc": "一人多高的黑熊，一掌能拍碎石頭。", "hp": 120, "atk": 22, "dfn": 12, "spd": 8, "style": "剛"},
  {"id": "louluo", "name": "水寇嘍囉", "desc": "拿著魚叉的水寇小卒。", "hp": 60, "atk": 12, "dfn": 6, "spd": 10, "style": "剛", "reward_silver": 8},
  {"id": "shuikou", "name": "太湖水寇", "desc": "水性精熟、刀法狠辣的水寇。", "hp": 90, "atk": 18, "dfn": 10, "spd": 14, "style": "剛", "reward_silver": 15},
  {"id": "toumu", "name": "水寨頭目", "desc": "水寨的小頭目，一對分水刺使得虎虎生風。", "hp": 140, "atk": 26, "dfn": 16, "spd": 16, "style": "快", "reward_silver": 40},
  {"id": "fanjianglong", "name": "翻江龍", "desc": "太湖水寨大當家，一柄九環刀橫行江南二十年。", "hp": 260, "atk": 34, "dfn": 22, "spd": 20, "style": "剛"},
  {"id": "guishou", "name": "鬼手劉三", "desc": "江南有名的盜墓賊，一雙手快得看不清。", "hp": 110, "atk": 22, "dfn": 12, "spd": 26, "style": "巧"},
  {"id": "shoumu", "name": "藏龍洞守墓人", "desc": "守了寶藏四十年的老人，眼中沒有一絲活人的溫度。", "hp": 240, "atk": 30, "dfn": 24, "spd": 24, "style": "柔"},
  {"id": "xuantie_dizi", "name": "玄鐵門師兄", "desc": "玄鐵門負責試煉新人的師兄，一身橫練功夫。", "hp": 90, "atk": 15, "dfn": 14, "spd": 10, "style": "剛"}
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_real_content.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add content tests/test_real_content.py
git commit -m "content: add 江南風雨 scenario, map, skills, sects and enemies"
```

---
### Task 10: 正式內容（二）：事件、機器人整季測試、平衡模擬

**Files:**
- Create: `content/events/general.json`, `content/events/kou.json`, `content/events/treasure.json`, `content/events/sects.json`, `tianxia/bot.py`, `scripts/simulate.py`
- Delete: `content/events/.gitkeep`
- Modify: `tests/test_real_content.py`（新增測試）

**Interfaces:**
- Consumes: Task 9 列出的所有 id；`Game`。
- Produces:
  - `tianxia/bot.py`：`play_season(content, seed, max_steps=20000) -> Game`（亂數選擇可用選項，每 4 步推進 30 分鐘；沒有可用選項時也推進 30 分鐘）。
  - `scripts/simulate.py`：`python scripts/simulate.py [場數]` 印出結局分布、門檻觸發次數、平均季長與平均遇到的事件數。

- [ ] **Step 1: Write the failing test**

在 `tests/test_real_content.py` 加上（檔案開頭的 import 一併補上 `import pytest` 與 `from tianxia.bot import play_season`）：
```python
def test_real_content_has_enough_events():
    c = load_content(CONTENT_DIR)
    assert len(c.events) >= 30
    assert sum(e.qiyu for e in c.events.values()) >= 3


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_bot_plays_full_season(seed):
    game = play_season(load_content(CONTENT_DIR), seed)
    assert game.state.world.ended
    assert game.state.world.ending_title
    assert len(game.state.player.seen_events) >= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_real_content.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tianxia.bot'`

- [ ] **Step 3: Write the bot and the simulate script**

`tianxia/bot.py`:
```python
"""亂數機器人：隨機選擇可用選項玩完一整季。用於整季測試與平衡模擬。"""
from __future__ import annotations

import random

from .engine import Game
from .models import Content

HALF_HOUR = 1800


def play_season(content: Content, seed: int, max_steps: int = 20000) -> Game:
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed))
    rng = random.Random(seed)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options() if o.enabled]
        if options:
            game.choose(rng.choice(options).id)
        if not options or step % 4 == 0:
            game.advance(HALF_HOUR)
    return game
```

`scripts/simulate.py`:
```python
"""平衡模擬：讓亂數機器人玩完整季，統計結局與大勢發展。

用法：.venv/Scripts/python.exe scripts/simulate.py 50
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.bot import play_season  # noqa: E402
from tianxia.content import load_content  # noqa: E402


def main(runs: int) -> None:
    content = load_content(ROOT / "content")
    endings, thresholds = Counter(), Counter()
    days, events = [], []
    for seed in range(runs):
        world = (game := play_season(content, seed)).state.world
        endings[world.ending_title] += 1
        thresholds.update(world.fired_thresholds)
        days.append(world.time / 86400)
        events.append(len(game.state.player.seen_events))
    print(f"模擬 {runs} 季")
    print("結局：", dict(endings))
    print("門檻觸發次數：", dict(thresholds))
    print(f"平均季長 {sum(days) / runs:.1f} 天；平均遇到 {sum(events) / runs:.1f} 種事件")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
```

- [ ] **Step 4: Write the event files**

刪除 `content/events/.gitkeep`。

`content/events/general.json`:
```json
[
  {"id": "drunk_token", "title": "狼頭鐵牌", "locations": ["shouxihu", "qinhuai"],
   "text": "一名醉漢跌跌撞撞撞上了你，懷中掉出一塊刻著狼頭的鐵牌。他慌忙撿起，眼神閃過一絲驚恐。",
   "choices": [
    {"text": "一把扣住他的手腕，逼問鐵牌來歷", "check": {"stat": "str", "difficulty": 6},
     "effect": {"text": "醉漢疼得齜牙咧嘴，全招了：狼頭牌是太湖水寨的暗記，他是水寨安插在城裡的眼線。你將他扭送官府。", "stats": {"good": 2, "fame": 1}, "trend": {"kou": -2}},
     "fail_effect": {"text": "醉漢身子一扭，竟像泥鰍般滑脫，轉眼消失在人群裡。"}},
    {"text": "裝作沒看見，暗中跟蹤", "check": {"stat": "agi", "difficulty": 6},
     "effect": {"text": "你遠遠吊在他身後，一路跟到運河邊一座破倉庫。", "stamina": -10, "next_event": "drunk_warehouse"},
     "fail_effect": {"text": "拐過兩條巷子，人就不見了。", "stamina": -10}},
    {"text": "扶他起身，順手摸走鐵牌", "check": {"stat": "agi", "difficulty": 5},
     "effect": {"text": "你扶起醉漢，鐵牌已悄悄落入你袖中。", "stats": {"evil": 1}, "flags_add": ["wolf_token"]},
     "fail_effect": {"text": "醉漢猛然抓住你的手：「小賊！」四周的人都朝你看過來。", "stats": {"fame": -1}}},
    {"text": "不予理會，繼續賞景", "effect": {"text": "你轉過身，湖上的畫舫正緩緩駛過。"}}
  ]},
  {"id": "drunk_warehouse", "title": "運河倉庫", "actions": [],
   "text": "倉庫裡燈火昏暗，十幾名水寇正在搬運私鹽，那醉漢正向一名頭目低聲稟報。",
   "choices": [
    {"text": "悄悄退出，回報官府", "effect": {"text": "官兵連夜查抄倉庫，水寇在城裡的據點被拔了一個。", "stats": {"good": 3, "silver": 20}, "trend": {"kou": -3}}},
    {"text": "等他們走後，向醉漢敲一筆封口費", "effect": {"text": "醉漢哭喪著臉，把一袋碎銀塞給你。", "stats": {"silver": 40, "evil": 2}}},
    {"text": "拔劍闖進去", "combat": "shuikou",
     "effect": {"text": "你一人一劍，殺得水寇四散奔逃！", "stats": {"fame": 3, "good": 2}, "trend": {"kou": -5}, "rumor": "{name}單槍匹馬挑了水寇在城裡的私鹽倉。"},
     "fail_effect": {"text": "寡不敵眾，你帶傷殺出重圍。", "stamina": -20}}
  ]},
  {"id": "herb", "title": "紫靈芝", "tags": ["山林"],
   "text": "石縫間長著一株紫色的靈芝，傘蓋上泛著微光。",
   "choices": [
    {"text": "採下來拿去藥鋪賣", "effect": {"text": "藥鋪掌櫃出了個好價錢。", "stats": {"silver": 15}}},
    {"text": "當場服下", "check": {"stat": "wis", "difficulty": 6},
     "effect": {"text": "一股暖流自丹田升起，你只覺筋骨舒展。", "stats": {"con": 1}},
     "fail_effect": {"text": "你腹痛如絞，在草叢裡躺了半天。", "stamina": -15}},
    {"text": "留在原地，讓它繼續長", "effect": {"text": "你記下了位置，心想也許有一天用得上。", "stats": {"good": 1}}}
  ]},
  {"id": "beggar", "title": "路邊乞丐", "tags": ["官道", "野外"],
   "text": "路邊一個老乞丐捧著破碗，眼巴巴地望著你。",
   "choices": [
    {"text": "施捨幾兩銀子", "effect": {"text": "老乞丐咧開缺牙的嘴笑了，多看了你兩眼。", "stats": {"silver": -5, "good": 1}, "flags_add": ["helped_beggar"]}},
    {"text": "視而不見", "effect": {"text": "你快步走過。"}},
    {"text": "一腳踢翻他的碗", "effect": {"text": "銅板滾了一地，老乞丐一聲不吭地撿著。", "stats": {"evil": 2}}}
  ]},
  {"id": "temple_zen", "title": "禪房聽經", "tags": ["寺院"],
   "text": "禪房裡傳出老僧講經的聲音，香客們席地而坐。",
   "choices": [
    {"text": "坐下靜聽", "check": {"stat": "wis", "difficulty": 6},
     "effect": {"text": "你似有所悟，心境一片澄明。", "stamina": -5, "stats": {"wis": 1}},
     "fail_effect": {"text": "聽著聽著，你竟睡著了。", "stamina": -5}},
    {"text": "捐些香油錢", "effect": {"text": "知客僧雙手合十：「施主善心。」", "stats": {"silver": -10, "good": 2}}},
    {"text": "悄悄退出去", "effect": {"text": "你輕輕帶上了禪房的門。"}}
  ]},
  {"id": "tavern_brawl", "title": "酒樓鬥毆", "tags": ["城鎮"],
   "text": "酒樓裡兩幫人一言不合，桌椅橫飛，眼看要出人命。",
   "choices": [
    {"text": "上前勸架", "check": {"stat": "str", "difficulty": 6},
     "effect": {"text": "你一手一個把人分開，眾人見你手勁驚人，都不敢再鬧。", "stats": {"good": 1, "fame": 1}},
     "fail_effect": {"text": "你被一張飛來的板凳砸中，還賠了掌櫃桌椅錢。", "stats": {"silver": -5}}},
    {"text": "趁亂撿走地上的錢袋", "effect": {"text": "錢袋沉甸甸的，沒人注意到你。", "stats": {"silver": 12, "evil": 1}}},
    {"text": "找個角落看熱鬧", "effect": {"text": "你喝完一壺酒，看完了一場好戲。"}}
  ]},
  {"id": "teahouse", "title": "茶館說書", "actions": ["socialize"], "tags": ["城鎮"],
   "text": "茶館裡說書先生正講到精彩處，醒木一拍，滿堂喝采。",
   "choices": [
    {"text": "花幾個錢向茶客打聽消息", "effect": {"text": "茶客壓低聲音：「太湖那邊不太平，翻江龍又在招兵買馬。還有人說，棲霞山裡挖出過前朝的古錢……」", "stats": {"silver": -5}}},
    {"text": "上台和說書先生對幾句", "check": {"stat": "wis", "difficulty": 7},
     "effect": {"text": "你一番妙語，說書先生拱手稱服，茶客們記住了你的名號。", "stats": {"fame": 1}},
     "fail_effect": {"text": "你張口結舌，惹得哄堂大笑。"}},
    {"text": "喝完茶就走", "effect": {"text": "茶香猶在舌尖。"}}
  ]},
  {"id": "fisherman", "title": "補網的漁翁", "tags": ["湖畔", "水路"],
   "text": "湖邊一位老漁翁正在補網，嘴裡念叨著今年的魚不好打。",
   "choices": [
    {"text": "幫他補網", "effect": {"text": "漁翁嘆道：「水寇到處抓壯丁，年輕人都不敢下湖了。」", "stamina": -5, "stats": {"good": 1}}},
    {"text": "買一碗魚湯", "effect": {"text": "一碗熱騰騰的魚湯下肚，渾身都是力氣。", "stamina": 15, "stats": {"silver": -3}}},
    {"text": "向他打聽水寇的動靜", "check": {"stat": "wis", "difficulty": 5},
     "effect": {"text": "漁翁指了指湖心：「水寨的船，每逢初一十五就出來。」你暗暗記下。", "flags_add": ["kou_intel"]},
     "fail_effect": {"text": "漁翁搖搖頭，不肯多說。"}}
  ]},
  {"id": "wolves", "title": "狼群", "tags": ["山林", "野外"],
   "text": "林中傳來一聲狼嚎，幾雙綠油油的眼睛從四面圍了過來。",
   "choices": [
    {"text": "拔出兵器迎戰", "combat": "yelang",
     "effect": {"text": "你殺退狼群，身法越發靈活了。", "stats": {"agi": 1}},
     "fail_effect": {"text": "你被咬了幾口，狼狽地逃出樹林。", "stamina": -15}},
    {"text": "爬上大樹躲避", "check": {"stat": "agi", "difficulty": 5},
     "effect": {"text": "你攀上高枝，狼群轉了幾圈悻悻而去。"},
     "fail_effect": {"text": "你爬到一半滑了下來，被追得滿山跑。", "stamina": -15}}
  ]},
  {"id": "hanshan_bell", "title": "夜半鐘聲", "locations": ["hanshan"], "once": true,
   "text": "夜半鐘聲悠悠傳來，寺外江楓漁火，客船靜泊。",
   "choices": [
    {"text": "閉目靜聽", "effect": {"text": "鐘聲一聲聲敲進心裡，你的思緒清明了許多。", "stats": {"wis": 1}}},
    {"text": "回客棧歇息", "effect": {"text": "你睡了一個好覺。", "stamina": 10}}
  ]},
  {"id": "train_insight", "title": "拆招頓悟", "actions": ["train"],
   "text": "一番苦戰之後，方才對手的一招在你腦海中反覆浮現。",
   "choices": [
    {"text": "趁熱再練幾遍", "effect": {"text": "你反覆演練，拳腳更有力了。", "stamina": -10, "stats": {"str": 1}}},
    {"text": "靜下心來細想", "check": {"stat": "wis", "difficulty": 6},
     "effect": {"text": "你想通了其中關竅。", "stats": {"wis": 1}},
     "fail_effect": {"text": "想了半天，還是沒想明白。"}}
  ]},
  {"id": "train_onlooker", "title": "錦衣少年", "actions": ["train"],
   "text": "打鬥剛歇，一個錦衣少年跑過來，一臉崇拜地看著你。",
   "choices": [
    {"text": "收下他送的見面禮", "effect": {"text": "少年說回去要跟人講講你的威風。", "stats": {"silver": 15, "fame": 1}}},
    {"text": "教他兩招防身", "effect": {"text": "少年學得有模有樣，千恩萬謝地走了。", "stamina": -5, "stats": {"good": 1, "fame": 1}}},
    {"text": "擺擺手離開", "effect": {"text": "你不喜歡被人盯著看。"}}
  ]},
  {"id": "escort_teacher", "title": "威遠鏢局", "actions": ["socialize"], "locations": ["yangzhou"], "condition": {"skills_none": ["zhuifeng"]},
   "text": "威遠鏢局的老鏢頭正在院子裡教新進的趟子手練腳力。",
   "choices": [
    {"text": "付四十兩學費，跟著練追風步", "condition": {"min_stats": {"silver": 40}},
     "effect": {"text": "老鏢頭收了錢，教得倒是實在。", "stats": {"silver": -40}, "learn_skills": ["zhuifeng"]}},
    {"text": "替鏢局跑一趟腿", "effect": {"text": "你幫鏢局送了封信，拿到一份工錢。", "stamina": -15, "stats": {"silver": 15}}},
    {"text": "告辭", "effect": {"text": "老鏢頭點點頭，繼續吆喝。"}}
  ]},
  {"id": "monk_jinshan", "title": "金山寺方丈", "actions": ["socialize"], "locations": ["jinshan"],
   "text": "金山寺的老方丈正在寺後菜園澆水。",
   "choices": [
    {"text": "請教調息之法", "check": {"stat": "wis", "difficulty": 6},
     "effect": {"text": "老方丈隨口點撥幾句，你的氣息順暢了許多。", "stamina": -5, "stats": {"con": 1}},
     "fail_effect": {"text": "老方丈笑而不語，繼續澆他的菜。", "stamina": -5}},
    {"text": "幫忙挑水", "effect": {"text": "老方丈道了聲善哉。", "stamina": -10, "stats": {"good": 1}}}
  ]},
  {"id": "qinhuai_song", "title": "畫舫歌聲", "actions": ["socialize"], "locations": ["qinhuai"],
   "text": "秦淮河的畫舫上傳來琵琶聲，一位歌女倚窗而歌。",
   "choices": [
    {"text": "上船聽曲", "condition": {"min_stats": {"silver": 20}},
     "effect": {"text": "一曲終了，你一身疲憊都散了。", "stamina": 20, "stats": {"silver": -20}}},
    {"text": "在岸邊聽一會兒就走", "effect": {"text": "曲子隨水聲漸遠。"}}
  ]},
  {"id": "waterfall", "title": "瀑布怪客", "tags": ["山林"], "qiyu": true, "weight": 0.2, "once": true,
   "text": "山澗瀑布下，一個赤足怪客正在急流中來回縱躍，身形快得只剩一道影子。",
   "choices": [
    {"text": "躲在石後偷學", "check": {"stat": "wis", "difficulty": 7},
     "effect": {"text": "你把怪客的步法默記在心，竟學到了七八成。", "stats": {"agi": 1}, "learn_skills": ["zhuifeng"]},
     "fail_effect": {"text": "你看得眼花撩亂，什麼也沒記住。"}},
    {"text": "上前拜見", "effect": {"text": "怪客瞥了你一眼，一個起落就不見了。"}}
  ]}
]
```

`content/events/kou.json`:
```json
[
  {"id": "kou_escort", "title": "布商求援", "locations": ["guazhou", "zhenjiang"],
   "text": "一位滿頭大汗的布商拉住你：「少俠！我這船貨要過江，最近水寇猖獗，能不能護送一程？酬金好說！」",
   "choices": [
    {"text": "答應護送", "combat": "shuikou",
     "effect": {"text": "水寇果然來劫，被你殺退，布商千恩萬謝。", "stats": {"silver": 35, "good": 1}, "trend": {"kou": -3}},
     "fail_effect": {"text": "你寡不敵眾，貨被劫走一半，布商哭天搶地。", "trend": {"kou": 1}}},
    {"text": "收了訂金，半路溜走", "effect": {"text": "布商在渡口等了一整天，也沒等到你。", "stats": {"silver": 20, "evil": 3, "fame": -2}}},
    {"text": "婉拒", "effect": {"text": "布商嘆了口氣，另找他人去了。"}}
  ]},
  {"id": "kou_recruit", "title": "水寇拉人", "locations": ["gaoyou", "taihu_north"], "condition": {"flags_none": ["kou_member", "kou_spy", "kou_traitor"]},
   "text": "幾名水寇攔住你，為首的咧嘴一笑：「看你身手不錯，跟著翻江龍大當家混，吃香的喝辣的，怎樣？」",
   "choices": [
    {"text": "入夥", "effect": {"text": "你接過水寨的狼頭牌，從此是道上的人了。", "stats": {"silver": 30, "evil": 3}, "trend": {"kou": 3}, "flags_add": ["kou_member"], "rumor": "有人說{name}投了太湖水寨。"}},
    {"text": "假意入夥，伺機探聽", "check": {"stat": "wis", "difficulty": 7},
     "effect": {"text": "你混進了水寇的隊伍，對方還沒起疑。", "flags_add": ["kou_spy"]},
     "fail_effect": {"text": "你眼神一閃被看穿，挨了一刀才逃出來。", "stamina": -15, "stats": {"evil": 1}}},
    {"text": "拔劍", "combat": "shuikou",
     "effect": {"text": "你一劍逼退為首的水寇，其餘的四散而逃。", "stats": {"fame": 1}, "trend": {"kou": -2}},
     "fail_effect": {"text": "你被水寇打翻在地，身上的銀子也被搜走了。", "stamina": -15, "stats": {"silver": -10}}}
  ]},
  {"id": "kou_spy_report", "title": "巡江校尉", "actions": ["socialize"], "locations": ["zhenjiang", "suzhou"], "condition": {"flags_all": ["kou_spy"]}, "once": true,
   "text": "你找到官府的巡江校尉，他正為水寇的布防發愁。",
   "choices": [
    {"text": "獻上水寨布防", "effect": {"text": "校尉大喜，當夜便調兵突襲。", "stats": {"good": 3, "fame": 3, "silver": 50}, "trend": {"kou": -10}, "flags_remove": ["kou_spy"],
     "rumor": "{name}潛入水寨，探得布防交給官府，水寇折損慘重！", "chronicle": "{name}潛入太湖水寨，探得布防，重挫水寇。"}},
    {"text": "暫不透露，繼續潛伏", "effect": {"text": "你決定再等等，也許能探到更大的消息。"}}
  ]},
  {"id": "kou_member_raid", "title": "水寨的命令", "tags": ["水路"], "condition": {"flags_all": ["kou_member"]},
   "text": "水寨傳來命令：今晚劫一艘運糧船，你也得上。",
   "choices": [
    {"text": "動手", "effect": {"text": "糧船上的人跪了一地，你分到了一份。", "stats": {"silver": 40, "evil": 3}, "trend": {"kou": 3}}},
    {"text": "放走糧船，從此與水寨一刀兩斷", "effect": {"text": "你悄悄解開纜繩，看著糧船消失在夜色裡。", "stats": {"good": 2}, "trend": {"kou": -2},
     "flags_remove": ["kou_member"], "flags_add": ["kou_traitor"], "rumor": "{name}在劫船時倒戈，放走了一整船糧食，水寨揚言要他的命。"}}
  ]},
  {"id": "kou_blockade", "title": "運河封鎖", "tags": ["水路", "渡口"], "weight": 2, "condition": {"world_flags_all": ["canal_blocked"], "world_flags_none": ["kou_crushed"]},
   "text": "運河被水寇封鎖，渡口擠滿了過不了江的百姓，米價一天漲三次。",
   "choices": [
    {"text": "夜襲水寇的哨船", "combat": "shuikou",
     "effect": {"text": "你摸上哨船，一把火燒了個乾淨。", "stats": {"fame": 2, "good": 1}, "trend": {"kou": -4}},
     "fail_effect": {"text": "哨船上早有埋伏，你跳江才逃過一劫。", "stamina": -20}},
    {"text": "囤米高價賣出", "effect": {"text": "你賺了一大筆，也挨了不少白眼。", "stats": {"silver": 40, "evil": 3}}},
    {"text": "幫忙維持秩序", "effect": {"text": "百姓們漸漸安定下來。", "stamina": -10, "stats": {"good": 2}}}
  ]},
  {"id": "kou_captives", "title": "蘆葦盪", "locations": ["taihu_north", "taihu_isle"],
   "text": "蘆葦盪裡綁著幾個被擄來的漁民，看守的水寇正在打瞌睡。",
   "choices": [
    {"text": "悄悄救人", "check": {"stat": "agi", "difficulty": 6},
     "effect": {"text": "你割斷繩子，帶著漁民從蘆葦盪摸了出去。", "stats": {"good": 3}, "trend": {"kou": -2}},
     "fail_effect": {"text": "看守驚醒大叫，你只好丟下漁民逃走。", "stamina": -15}},
    {"text": "裝作沒看見", "effect": {"text": "你繞開了蘆葦盪。"}}
  ]},
  {"id": "kou_boss", "title": "翻江龍", "locations": ["taihu_isle"], "weight": 0.6,
   "condition": {"min_stats": {"fame": 3}, "world_flags_none": ["kou_crushed", "fjl_defeated"]},
   "text": "聚義廳前，一個鐵塔般的大漢拄著九環刀，冷冷地看著你：「就是你，最近專跟我水寨作對？」——正是翻江龍。",
   "choices": [
    {"text": "拔劍：「正是在下。」", "combat": "fanjianglong",
     "effect": {"text": "九環刀脫手飛出，翻江龍踉蹌後退，水寇們面面相覷。", "stats": {"fame": 10, "good": 3}, "trend": {"kou": -25}, "world_flags_add": ["fjl_defeated"],
      "rumor": "{name}在太湖水寨當眾擊敗翻江龍！", "chronicle": "{name}於太湖水寨擊敗水寇大當家翻江龍。"},
     "fail_effect": {"text": "九環刀勢大力沉，你被震得虎口迸裂，狼狽逃出水寨。", "stamina": -30, "stats": {"silver": -20}}},
    {"text": "轉身就走", "effect": {"text": "翻江龍的笑聲在身後迴盪。"}}
  ]},
  {"id": "kou_reward", "title": "知府設宴", "actions": ["socialize"], "locations": ["suzhou"], "condition": {"world_flags_all": ["kou_crushed"]}, "once": true,
   "text": "蘇州知府設宴答謝平定太湖的俠客，席間有人提起你的名字。",
   "choices": [
    {"text": "赴宴領賞", "effect": {"text": "知府親手把一盤銀錠推到你面前。", "stats": {"silver": 100, "fame": 5}}},
    {"text": "婉拒", "effect": {"text": "你說，平寇是分內之事。", "stats": {"good": 3}}}
  ]}
]
```

`content/events/treasure.json`:
```json
[
  {"id": "bao_scroll", "title": "白骨與殘卷", "locations": ["qixia_foot", "qixia_back", "yuhuatai"], "qiyu": true, "weight": 0.15, "once": true, "condition": {"trend_max": {"bao": 0}},
   "text": "你一腳踩空，跌進一個被雨水沖開的土坑。坑底有具白骨，懷裡緊緊抱著一個油布包——裡面是半張泛黃的地圖，角落蓋著前朝的官印。",
   "choices": [
    {"text": "收起殘卷，把消息傳出去", "effect": {"text": "消息傳開，江湖上的眼睛都轉向了金陵。", "stats": {"fame": 2}, "trend": {"bao": 20}, "flags_add": ["bao_piece"],
     "rumor": "江湖傳聞：{name}在金陵一帶掘出一片前朝藏寶圖殘卷！", "chronicle": "{name}發現第一片前朝藏寶圖殘卷，寶藏之謎浮上檯面。"}},
    {"text": "收起殘卷，秘而不宣", "effect": {"text": "你把殘卷貼身收好，誰也沒告訴。", "trend": {"bao": 20}, "flags_add": ["bao_piece"]}}
  ]},
  {"id": "bao_antique", "title": "古董鋪的舊圖", "actions": ["socialize"], "locations": ["suzhou", "jinling"], "weight": 0.5, "once": true,
   "condition": {"trend_max": {"bao": 0}, "min_stats": {"silver": 150}},
   "text": "古董鋪的掌櫃神神秘秘地拉你到後堂：「客官，這半張舊圖是前朝的東西，一百五十兩，不二價。」",
   "choices": [
    {"text": "買下", "effect": {"text": "你展開舊圖，上面畫著一座山，山勢像極了棲霞山。", "stats": {"silver": -150}, "trend": {"bao": 20}, "flags_add": ["bao_piece"]}},
    {"text": "不買", "effect": {"text": "掌櫃聳聳肩，把舊圖收了回去。"}}
  ]},
  {"id": "bao_dig", "title": "循圖挖掘", "tags": ["山林"], "condition": {"trend_min": {"bao": 1}, "world_flags_none": ["cave_open"]},
   "text": "你對照殘卷上的山形，找到一處可疑的土坡。",
   "choices": [
    {"text": "動手挖掘", "check": {"stat": "wis", "difficulty": 6},
     "effect": {"text": "鏟子碰到一個鐵盒，裡面又是一片殘卷！", "stamina": -15, "trend": {"bao": 10}},
     "fail_effect": {"text": "挖了半天，只挖出一窩螞蟻。", "stamina": -15}},
    {"text": "做個記號，改天再來", "effect": {"text": "你在樹上刻了個記號。"}}
  ]},
  {"id": "bao_rival", "title": "鬼手劉三", "tags": ["山林"], "weight": 0.7, "condition": {"trend_min": {"bao": 20}, "world_flags_none": ["cave_open"]},
   "text": "土坡後面有人在挖土，那人猛一回頭——是江南有名的盜墓賊，鬼手劉三。",
   "choices": [
    {"text": "動手搶他的殘卷", "combat": "guishou",
     "effect": {"text": "鬼手劉三丟下殘卷，一溜煙跑了。", "stats": {"fame": 2}, "trend": {"bao": 15}},
     "fail_effect": {"text": "等你回過神來，身上的殘卷已經被他摸走了。", "trend": {"bao": -5}}},
    {"text": "談合作：「一起找，平分。」", "condition": {"min_stats": {"silver": 20}},
     "effect": {"text": "劉三眼珠一轉，收了你二十兩「定金」，給了你一條線索。", "stats": {"silver": -20}, "trend": {"bao": 8}}},
    {"text": "悄悄走開", "effect": {"text": "你不想惹這個麻煩。"}}
  ]},
  {"id": "bao_scholar", "title": "老學究", "actions": ["socialize"], "locations": ["jinling"], "once": true, "condition": {"trend_min": {"bao": 1}, "world_flags_none": ["cave_open"]},
   "text": "國子監旁住著一位老學究，據說對前朝典故無所不知。",
   "choices": [
    {"text": "帶上謝禮請教", "condition": {"min_stats": {"silver": 20}},
     "effect": {"text": "老學究指著殘卷上的小字：「這不是地名，是前朝工部的營造編號……」", "stats": {"silver": -20, "wis": 1}, "trend": {"bao": 15}}},
    {"text": "自己拿著殘卷琢磨", "check": {"stat": "wis", "difficulty": 8},
     "effect": {"text": "你熬了一夜，終於看出殘卷上的暗記。", "trend": {"bao": 15}},
     "fail_effect": {"text": "你盯著殘卷看了一夜，只看得眼花。"}}
  ]},
  {"id": "bao_guardian", "title": "藏龍洞守墓人", "locations": ["canglong"], "condition": {"world_flags_none": ["treasure_taken"]},
   "text": "藏龍洞深處，一位白髮老人盤坐在石門前，緩緩睜開眼：「四十年了，終於有人找到這裡。想要寶藏，先過我這一關。」",
   "choices": [
    {"text": "出手", "combat": "shoumu",
     "effect": {"text": "老人長嘆一聲，讓開了石門。門後金光耀眼，還有一卷寫著「混元一氣」的絹冊。", "stats": {"silver": 500, "fame": 15}, "learn_skills": ["hunyuan"], "world_flags_add": ["treasure_taken"],
      "rumor": "藏龍洞中傳出巨響，前朝寶藏被{name}取走了！", "chronicle": "{name}擊敗藏龍洞守墓人，取得前朝寶藏與失傳內功「混元一氣」。"},
     "fail_effect": {"text": "老人一掌將你推出洞外：「再練十年吧。」", "stamina": -30}},
    {"text": "退出洞外", "effect": {"text": "你決定先回去準備。"}}
  ]}
]
```

`content/events/sects.json`:
```json
[
  {"id": "qixia_join", "title": "棲霞收徒", "actions": ["socialize"], "locations": ["qixia_sect"],
   "condition": {"no_sect": true, "flags_none": ["叛出:qixia"], "max_stats": {"evil": 9}},
   "text": "棲霞劍派的知客弟子迎上來：「掌門有令，近來江南不寧，本派廣開山門，收錄品行端正的弟子。」",
   "choices": [
    {"text": "拜入棲霞劍派", "effect": {"text": "你在祖師像前叩了三個頭，從此是棲霞弟子。門規第一條：不得恃武作惡。", "join_sect": "qixia"}},
    {"text": "婉拒，當個散人", "effect": {"text": "知客弟子也不勉強，送你下山。"}}
  ]},
  {"id": "xuantie_join", "title": "玄鐵試煉", "actions": ["socialize"], "locations": ["xuantie"],
   "condition": {"no_sect": true, "flags_none": ["叛出:xuantie"]},
   "text": "玄鐵門的演武場上，一個赤膊大漢攔住你：「想入我玄鐵門？先接我三拳！」",
   "choices": [
    {"text": "接招", "combat": "xuantie_dizi",
     "effect": {"text": "大漢揉著胳膊哈哈大笑：「好！從今天起你就是玄鐵門的人了！」", "join_sect": "xuantie"},
     "fail_effect": {"text": "你被一拳打出演武場，大漢喊道：「練結實了再來！」", "stamina": -10}},
    {"text": "告辭", "effect": {"text": "你轉身離開了演武場。"}}
  ]},
  {"id": "qixia_teach", "title": "師父傳劍", "actions": ["socialize"], "locations": ["qixia_sect"],
   "condition": {"sects": ["qixia"], "min_stats": {"fame": 5}, "skills_none": ["luoying"]},
   "text": "師父把你叫到後山：「你在江湖上的事，為師都聽說了。今天傳你本門的『落英劍式』與『燕回翔』。」",
   "choices": [
    {"text": "恭敬受教", "effect": {"text": "劍光如落英繽紛，你練到日落才停手。", "learn_skills": ["luoying", "yanhui"]}},
    {"text": "自覺火候未到，改日再來", "effect": {"text": "師父點點頭：「也好。」"}}
  ]},
  {"id": "xuantie_teach", "title": "門主傳拳", "actions": ["socialize"], "locations": ["xuantie"],
   "condition": {"sects": ["xuantie"], "min_stats": {"fame": 5}, "skills_none": ["lieshi"]},
   "text": "門主拍拍你的肩膀：「小子，你在外面沒給玄鐵門丟臉。這套『裂石拳』，今天傳給你。」",
   "choices": [
    {"text": "抱拳受教", "effect": {"text": "一拳下去，演武場邊的石墩裂成兩半。", "learn_skills": ["lieshi"]}},
    {"text": "自覺火候未到，改日再來", "effect": {"text": "門主哈哈一笑：「有自知之明，不錯。」"}}
  ]},
  {"id": "qixia_rule", "title": "清理門戶", "weight": 5, "condition": {"sects": ["qixia"], "min_stats": {"evil": 10}},
   "text": "一名棲霞劍派的師兄攔在路中，面色鐵青：「師弟，你在外面做的事，掌門都知道了。跟我回山領罰！」",
   "choices": [
    {"text": "回山領罰", "effect": {"text": "你在思過崖面壁三天，腿都跪麻了。", "stamina": -30, "stats": {"evil": -5}}},
    {"text": "叛出師門", "effect": {"text": "你折斷了棲霞弟子的腰牌，擲在師兄腳下。", "leave_sect": true, "stats": {"evil": 3},
     "rumor": "{name}叛出棲霞劍派！棲霞弟子揚言要清理門戶。", "chronicle": "{name}叛出棲霞劍派。"}}
  ]},
  {"id": "beggar_master", "title": "乞丐高人", "tags": ["官道", "野外"], "qiyu": true, "weight": 0.4, "once": true,
   "condition": {"no_sect": true, "flags_all": ["helped_beggar"]},
   "text": "又是那個老乞丐。他朝你擠擠眼，隨手摘下一片樹葉一彈——葉子竟釘進了三丈外的樹幹。「小子，心腸不錯，又沒門沒派，這手『飛花摘葉』要不要學？」",
   "choices": [
    {"text": "拜謝學藝", "effect": {"text": "老乞丐教完就走，連名字都沒留下。", "stats": {"fame": 1}, "learn_skills": ["feihua"]}},
    {"text": "婉拒", "effect": {"text": "老乞丐哈哈一笑，消失在官道盡頭。"}}
  ]}
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通過。若 `test_bot_plays_full_season` 失敗，先看錯誤訊息是哪個事件或地點出錯，修正內容檔，**不要**放寬測試。

- [ ] **Step 6: Run the balance simulation**

Run: `.venv/Scripts/python.exe scripts/simulate.py 30`
Expected: 印出結局分布等統計，沒有例外。亂數機器人不會刻意剿寇，所以「水寇稱霸」佔多數是正常的；把輸出貼進 commit 訊息或回報給使用者作為平衡的起點。

- [ ] **Step 7: Commit**

```bash
git add content tianxia/bot.py scripts/simulate.py tests/test_real_content.py
git commit -m "content: add 36 events, a random bot and a balance simulation script"
```

---
### Task 11: Gradio 網頁介面與專案說明

**Files:**
- Create: `app.py`, `.claude/launch.json`, `README.md`, `CLAUDE.md`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `Game` 的所有公開方法、`save_game`、`load_game`、`EQUIP_SLOTS`。
- Produces:
  - `app.CONTENT`、`app.SAVE_DIR`、`app.MAX_BUTTONS = 10`、`app.N_OUTPUTS`
  - `app.save_path(name) -> Path`、`app.render(game) -> list`、`app.make_option_handler(index)`、`app.build_demo() -> gr.Blocks`
  - 介面：左欄是場景文字、最多 10 個動態選項按鈕、最近 40 行紀錄；右欄是角色狀態與分頁（江湖大勢、江湖傳聞、江湖史、武學、設定）。每 10 秒自動同步時間；每次操作後自動存檔到 `saves/<名號>.json`。

- [ ] **Step 1: Write the failing test**

`tests/test_app.py`:
```python
import app
from tianxia.engine import Game


def test_render_matches_outputs():
    game = Game.new(app.CONTENT, "測試")
    assert len(app.render(game)) == app.N_OUTPUTS


def test_option_handler_acts_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    ids = [o.id for o in game.options()]
    out = app.make_option_handler(ids.index("act:explore"))(game, ids)
    assert len(out) == app.N_OUTPUTS
    assert (tmp_path / "測試.json").exists()
    assert game.state.player.stamina < 150


def test_save_path_strips_unsafe_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    assert app.save_path("沈/浪?").name == "沈_浪_.json"


def test_build_demo():
    assert app.build_demo() is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write implementation**

`app.py`:
```python
"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import gradio as gr

from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.save import load_game, save_game
from tianxia.state import EQUIP_SLOTS

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
LOG_LINES = 40
N_OUTPUTS = 8 + MAX_BUTTONS + len(EQUIP_SLOTS) + 1


def save_path(name: str) -> Path:
    return SAVE_DIR / (re.sub(r'[\\/:*?"<>|]', "_", name) + ".json")


def render(game: Game) -> list:
    """回傳順序必須和 build_demo() 裡的 outputs 一致。"""
    options = game.options()[:MAX_BUTTONS]
    buttons = []
    for i in range(MAX_BUTTONS):
        if i < len(options):
            buttons.append(gr.update(value=options[i].label, visible=True, interactive=options[i].enabled))
        else:
            buttons.append(gr.update(visible=False))
    p = game.state.player
    equips = [
        gr.update(choices=[("（空）", "")] + game.skill_choices(slot), value=skill_id or "")
        for slot, skill_id in zip(EQUIP_SLOTS, p.equipped)
    ]
    learned = [choice for slot in ("內功", "外功", "輕功") for choice in game.skill_choices(slot)]
    return [
        game,
        game.status_text(),
        game.scene_text(),
        "\n\n".join(game.state.log[-LOG_LINES:]),
        game.trends_text(),
        game.rumors_text(),
        game.chronicle_text(),
        [o.id for o in options],
        *buttons,
        *equips,
        gr.update(choices=learned),
    ]


def act(game: Game | None, action) -> list:
    """同步時間 → 執行動作 → 存檔 → 重畫。"""
    if game is None:
        return [gr.skip()] * N_OUTPUTS
    game.sync(time.time())
    action(game)
    save_game(game.state, save_path(game.state.player.name))
    return render(game)


def make_option_handler(index: int):
    def handler(game, ids):
        if game is None or index >= len(ids):
            return [gr.skip()] * N_OUTPUTS
        return act(game, lambda g: g.choose(ids[index]))

    return handler


def make_equip_handler(slot: int):
    def handler(game, skill_id):
        return act(game, lambda g: g.equip(slot, skill_id or None))

    return handler


def make_fast_forward_handler(hours: int):
    def handler(game):
        return act(game, lambda g: g.advance(hours * 3600))

    return handler


def seclude_handler(game, skill_id, hours):
    if not skill_id:
        return [gr.skip()] * N_OUTPUTS
    return act(game, lambda g: g.seclude(int(hours), skill_id))


def anonymous_handler(game, value):
    return act(game, lambda g: g.set_anonymous(value))


def tick_handler(game):
    return act(game, lambda g: None)


def start(name):
    name = (name or "").strip()
    if not name:
        raise gr.Error("請先輸入你的名號。")
    path = save_path(name)
    game = Game(CONTENT, load_game(path)) if path.exists() else Game.new(CONTENT, name)
    return act(game, lambda g: None) + [gr.update(visible=False), gr.update(visible=True)]


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="天下大勢") as demo:
        game_state = gr.State(None)
        ids_state = gr.State([])
        gr.Markdown("# 天下大勢 · 原型")
        with gr.Column(visible=True) as start_col:
            name_box = gr.Textbox(label="你的名號", placeholder="例如：沈青衫（輸入舊名號會讀取存檔）")
            start_btn = gr.Button("踏入江湖", variant="primary")
        with gr.Row(visible=False) as game_row:
            with gr.Column(scale=3):
                scene_md = gr.Markdown()
                option_btns = [gr.Button(visible=False) for _ in range(MAX_BUTTONS)]
                gr.Markdown("---")
                log_md = gr.Markdown()
            with gr.Column(scale=2):
                status_md = gr.Markdown()
                with gr.Tabs():
                    with gr.Tab("江湖大勢"):
                        trends_md = gr.Markdown()
                    with gr.Tab("江湖傳聞"):
                        rumors_md = gr.Markdown()
                    with gr.Tab("江湖史"):
                        chronicle_md = gr.Markdown()
                    with gr.Tab("武學"):
                        equip_dds = [
                            gr.Dropdown(label=f"{slot}欄位", choices=[], interactive=True)
                            for slot in EQUIP_SLOTS
                        ]
                        seclude_dd = gr.Dropdown(label="閉關修練的武學", choices=[], interactive=True)
                        hours_sl = gr.Slider(1, 12, value=8, step=1, label="閉關時數（小時）")
                        seclude_btn = gr.Button("開始閉關")
                    with gr.Tab("設定"):
                        anon_cb = gr.Checkbox(label="匿名行走（江湖傳聞中不顯示名號）")
                        gr.Markdown("**測試用：時間快轉**")
                        with gr.Row():
                            ff_btns = {h: gr.Button(f"+{h} 小時") for h in (1, 8, 24)}

        outputs = [
            game_state, status_md, scene_md, log_md, trends_md, rumors_md, chronicle_md, ids_state,
            *option_btns, *equip_dds, seclude_dd,
        ]
        assert len(outputs) == N_OUTPUTS

        start_btn.click(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        name_box.submit(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        for slot, dd in enumerate(equip_dds):
            dd.input(make_equip_handler(slot), inputs=[game_state, dd], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, seclude_dd, hours_sl], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)
        gr.Timer(10).tick(tick_handler, inputs=[game_state], outputs=outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
```

`.claude/launch.json`:
```json
{
  "version": "0.0.1",
  "configurations": [
    {"name": "天下大勢", "runtimeExecutable": ".venv/Scripts/python.exe", "runtimeArgs": ["app.py"], "port": 7861}
  ]
}
```

`README.md`:
````markdown
# 天下大勢（原型）

一個由玩家寫下結局的文字武俠江湖。設計文件見 `docs/superpowers/specs/2026-09-27-天下大勢-design.md`。

## 安裝與執行

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app.py
```

打開 http://127.0.0.1:7861 ，輸入名號即可開始；同一個名號會自動讀取存檔（`saves/`）。

## 測試與平衡

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/simulate.py 30
```

## 修改內容

所有地點、事件、武學、敵人、大勢線都在 `content/` 的 JSON 裡，改完重啟 `app.py` 即可。內容寫錯時，啟動會直接列出是哪個 id 出錯。
試玩時可以在「設定」分頁快轉時間，或把 `content/config.json` 的 `time_scale` 調大。
````

`CLAUDE.md`:
```markdown
# CLAUDE.md

《天下大勢》文字武俠原型。權威文件：`docs/superpowers/specs/2026-09-27-天下大勢-design.md`（設計）、`docs/superpowers/plans/`（實作計畫）。

## 架構
- `tianxia/`：純 Python 規則引擎，**不得 import gradio**。`engine.Game` 是唯一對外門面。
- `content/`：所有遊戲內容（JSON），載入時由 `tianxia/content.py::validate` 交叉檢查。
- `app.py`：Gradio 介面，只負責顯示與接線。

## 原則
- 數值全部由規則引擎決定，執行時不接 LLM。
- 武學、人物名稱必須原創，不用金庸等作品的專有名詞。
- 改內容後跑 `pytest`：`tests/test_real_content.py` 會讓機器人玩完整季，抓出內容錯誤。

## 指令
- 執行：`.venv/Scripts/python.exe app.py`（http://127.0.0.1:7861）
- 測試：`.venv/Scripts/python.exe -m pytest -q`
- 平衡模擬：`.venv/Scripts/python.exe scripts/simulate.py 30`
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通過

- [ ] **Step 5: Manual smoke test in the browser**

用 `preview_start`（名稱「天下大勢」）啟動，依序確認：
1. 輸入名號、按「踏入江湖」後，出現場景文字與「探索／交遊／前往」按鈕。
2. 按「探索」會出現事件與選項，選一個之後，紀錄區顯示結果。
3. 在「設定」按「+24 小時」，江湖傳聞分頁出現翻江龍的傳聞，大勢條上升。
4. 在「武學」分頁選一門武學開始閉關，選項變成「提前出關」。
5. 重新整理頁面、輸入同一名號，狀態與先前一致（讀檔成功）。

若 Gradio 版本不支援 `gr.update` 或 `gr.skip`，改用回傳元件實例（例如 `gr.Button(visible=False)`）的寫法，並在 commit 訊息中註明。

- [ ] **Step 6: Commit**

```bash
git add app.py .claude/launch.json README.md CLAUDE.md tests/test_app.py
git commit -m "feat: add Gradio web UI, launch config and project docs"
```
