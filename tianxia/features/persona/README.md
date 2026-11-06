# 人物性子（`tianxia/features/persona/`）

- **做什麼**：全服的人跟人物說話，會一點一點把他的性子往某一頭推；推夠了他換一段，說話的樣子跟著變，簡介寫「如今」與變化紀錄。
- **導覽**：`docs/guide/大勢人物與賽季.md` 的「人物性子」那一節。
- **設計稿**：https://claude.ai/artifact/R8w6aMxgeH89djeKYC7n5U（Joy 2026-11-06「可以」；換季選「全部歸回本性」）。
- **開關**：`Config.persona_shift.enabled`（預設關；`season21`、`week7` 設定打開，Joy 11/6）。關著一個位元組都不變：舊的性情漂移照舊。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：`enabled`＝開關開著而且 `content/personas.json` 有人；`on_sync`（結算、行狀）；`check_content` |
| `rules.py` | re-export 共用規則層 `tianxia/persona_rules.py` 的同一批物件（合回第 4 段搬的，理由見下）。本體是純規則：值與段、記一筆（`record`／`hear`）、每天結算（`settle`，懶結算）、換段、行狀、對話提示（`prompt_lines`）、簡介（`view`） |
| `actions.py` | 同步時替全服結算到今天（結算了就 `_save_season`）、記勸成的行狀（`annals.STANCE`） |
| `checks.py` | `content/personas.json` 的檢查 |
| `tests/` | `test_persona.py`、`test_persona_smoke.py`、`persona_stage.py` |

**接在別處的**：人物情誼包的 `companion_agent` 叫 `ends_for`（schema 多一個 enum 的 `persona`）、`prompt_lines`（提示多一段）、`hear`（記一筆、多一句）、
`covers`（他歸這一包管時舊的性情漂移不讀也不寫）、`NONE`；包不准 import 包，這幾個呼叫手上又沒有 `ctx`，所以純規則放共用規則層（`registry.SHARED` 的 `persona_rules`；它只 import 核心的 `calendar`、`rules`、`models`、`state`）。
`actions.py` 留包裡（要記行狀；行狀經核心 `core/annal_base`）。`server.figure_intro(cid, game)` 讀 `persona_rules.view`， 把如今與變化紀錄接進簡介（`figure_intro` 留在殼）。
**認領的欄位**：`PlayerState.persona_notes`（換季不帶）；季上 `WorldState.persona*`（換季整個重來＝全部歸回本性）。
**數字**（`PersonaShiftRules`，全是【草】）：情誼 30／60／80 算 1／2／3 份；一天淨推力不到 3 份不動；一份 2 點、一天最多 8 點、一段 40 點；沒人推回 2 點；最多離起點 2 段。

## 程式在哪、另外要跑的

規則本體在共用層 `tianxia/persona_rules.py`（人物情誼包的 `companion_agent` 要叫，包不准讀包；手冊第十五節「波次 A 的 PM 認定」第 8 條），這裡的 `rules.py` re-export 同一批物件。改 `persona_rules.py` 時 `test_for` 挑不到下面這些，自己跑：`tianxia/features/persona/tests`，`tianxia/features/companions/tests` 裡寫到 `companion_agent` 的檔。
