# 親衛隊長（`tianxia/features/guard/`）

- 做什麼：取代酒肆招募的同伴系統（Joy 2026-11-09）。10 級那一路撞見一個快死的孩子，救下、收養，之後一件一件的事由玩家決定怎麼待他；情分（善待往上、虐待往下）與性向兩條帳，紀事是他的記憶。最後他一定成為你的親衛隊長，被虐待大的帶著恨追隨（第二批起）。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「親衛隊長」那一節
- 設計稿：https://claude.ai/artifact/7Sra7sBo7njyH34B2Nr7Su（源檔在專案資料夾 `design/親衛隊長/設計稿v1.html`；Joy 2026-11-09「其他都按照建議」）
- 開關：`Config.guard.enabled`（預設關；數字在 `tianxia/core/tuning/guard.py`，全是【草】）

## 第一批：遇見與成長

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：options、menu、choose（`guard:`）、status（`main.guard`）、on_sync、after_action（自己問 enabled）、on_season_start、bot_pick、main_actions、outlock、scratch（`_guard_stamina`） |
| `rules.py` | 純規則：心性五檔（`band`）、夾法（`clamp_choice`：情分 ±step_cap、模型的 ±2、性向只留清單上的）、固定事件（`fixed_event`）、記帳（`apply`）、給模型的提示（`write_event` 生一件事＋溫嚴狠三個做法、`judge_say` 評自己寫的那一句） |
| `texts.py` | 固定的字：六種開場、男女名字表、八件家裡的事、四件路上的事（模型壞了與假人用；全部待 joy 潤） |
| `actions.py` | 「此地還能做」那幾顆、接管的選單、每天保底的家裡的事（on_sync）、帶他出門花了體力那一下冒出的路上的事（after_action）、三段式的 A、C 段、改名、出門帶不帶、養成冊那一份、換季照帶 |
| `routes.py` | `/api/do/guard_rename`、`guard_along`、`guard_say`（鎖外三段式）；背景寫字 `guard`（OutlockJob，表外的格接在表尾） |
| `bots.py` | 假人也養一個（別人之後看得到他）：只走固定事件、不叫模型；每個假人一種待人的路數（七成溫、兩成嚴、一成狠） |
| `web/guard.js`、`web/guard.css` | 俠客頁「同伴」最上面的養成冊（`cultivation.js` 的同伴那一頁叫 `guardHtml`） |

- 流程：`met`（眼前有個孩子：救／不管）→ `saved`（收養少年、少女，或救了不帶走）→ `grow`。不管、不帶走都是 `left`：他留在那裡，回到那個地點「回去看看那個孩子」。
- 事件從哪來：模型叫得到時 on_sync／after_action 只記 `want`，放鎖之後背景寫字生（`write_event`），回來 C 段重驗同一張單子才收；寫不出來、等過 `wait_seconds`、假人、伺服器沒模型，一律換固定事件。
- 自己寫的那一句：A `say_request` → B `judge_say`（跟這件事無關的回 relevant=false，C 段回「沒聽懂」不算這一次）→ C `apply_say` 重驗同一件。
- 數字由引擎定：模型評的情分夾到 ±2，固定事件寫死的最多 ±`step_cap`，總帳夾在 ±`qing_cap`；畫面不露數字（心性一檔、墨線位置）。

**認領的欄位**：`PlayerState.guard`（`GuardBook`、`GuardEvent`、`GuardChoice`、`GuardEntry`；`None` 不寫進存檔，在 `state.QUIET_DEFAULTS`）。換季照帶（`carried`）：第一批在 `on_season_start`（開關開著時）；開關關著的換季帶不過去，第四批補 `season.carry` 那一格（核心表，要點頭）。資料庫不升版。

## 還沒做（設計稿第十節）

第二批求學、出師結算、投效；第三批投效之後；第四批同服互動、跨季那一格、列傳、名帖、關酒肆招募；第五批圖。江湖頁有事時要一條提示列（`main.js` 的 `jhHintsHtml`，殼）要 Joy 點頭才加，現在是「此地還能做」裡那一顆。

## 測試

- `tests/test_guard.py`（14 條）、`tests/test_guard_smoke.py`（1 條 smoke）。
