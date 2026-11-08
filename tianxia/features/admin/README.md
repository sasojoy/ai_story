# 管理者包 `features/admin`

第二輪第 90 批開的包（計畫 `docs/superpowers/plans/2026-11-07-第二輪-第90批.md`）。管理頁 `/admin` 與它的資料、重設密碼、季與時刻表的工具都在這裡；改管理頁只讀這一包與 `web/admin.js`。

| 檔 | 做什麼 |
|---|---|
| `actions.py` | Game 上原本的 17 個方法：開季、收季、開下一季、暫停與繼續賽季時鐘、觸發大事、推動大勢、排時間、跳到下一件、定戰況、定結果、清鎖定 |
| `game_api.py` | Game 上掛的 15 個名字（`_settle_season_start`、`_showdown_mark` 只有這一包叫，不掛） |
| `routes.py` | `/admin`、`/api/admin`、`/api/admin/player`、`/api/admin/accounts`、`/api/admin/reset_password`；管理頁的選單 `admin_choices`、`timetable_choices`、`admin_now`；13 個管理者工具（`admin_tools`） |
| `web/admin.js`（檔照手冊 G9 在 `web/`，`web = ("admin.js",)`） | 管理頁的畫法與表單；排在 `WEB_ORDER` 裡，`/` 的 script 先後不變 |

**沒有**：選項前綴、`PlayerState` 欄位（`player_fields` 空的）、內容檔、`Config`、開關（`enabled` 回真）。假人不碰管理者。

## 留在別處的

- `Game` 留 `is_admin`、`_admin_refusal`、`_admin_target`、`_save_target`（管理者外殼，手冊第十五節波次 B、C 第 14 條）；`paused_minutes` 留（`main` 表 `admin` 那一格每個人都讀）。
- 殼留 `/`、`main` 表的 `admin` 格、`api_do` 的先後（管理者工具 gate → 登入 → `is_admin` → `identity_base.admin_session_ok` → `act`）、`PLAYER_ADMIN_ACTIONS`。`admin` 格與 `api_do` 在 `is_admin` 之後多問 `admin_session_ok`（帳號與客服第 207 批；identity 關著一律回真）。
- `routes.admin_ok(shell, request, game)`（第 207 批）：`is_admin` 加 `identity_base.admin_session_ok`（identity 開著時名單上的人要這次是密碼登入、`staff_hours` 內驗過）；四條 `/api/admin*` 都走它，不夠的回 403／「（只有管理者能重設密碼。）」跟不是管理者一樣。`reset_password` 多一個 `request`（直接叫的不帶，只看名號）；identity 開著時目標是名單上的帳號（`identity_base.listed`），臨時密碼也要 12 字。另外要跑：`tianxia/features/identity/tests/test_identity_admin_session.py`。
- 玩家個人劇情那張選單 `admin_player_choices` 在軍情包（`features/military/admin_actions.py` 的 `player_choices`）。
- `PAUSED_REFUSAL` 在 `core/services.py`（`Game._admin_refusal` 也用）。

## `admin_choices` 的格

`/api/admin` 那一份的鍵照 `core/features.py` 的 `STATUS_ORDER["admin"]` 一格一格叫，**鍵的先後與叫的先後都算行為**（假鐘同一個請求每叫一次走一步）。`battles`、`showdowns` 是決戰包的格，`fallen` 是大勢人物的行動，`seal` 是玉璽，`xingshi`、`conquest` 是地盤，`mingtie` 是玩家互動；其餘是 `admin_choices` 裡的閉包。別的包要多給管理頁一樣東西，在自己的 `status_slots` 登記 `StatusHook("admin", …)`。

## 權限

- `/api/admin`、`/api/admin/player`、`/api/admin/accounts`：不是管理者 403。
- `/api/admin/reset_password`：回「（只有管理者能重設密碼。）」。
- 13 個工具走 `/api/do/{op}`：殼的 `api_do` 擋，回「只有管理者能這麼做。」。
- `/admin` 不擋（同一張 `PAGE`，資料都在 `/api/admin*`）。

## 測試

`tests/`：`test_admin_timetable.py`、`test_season_pause.py`、`test_admin_routes.py`（每條路由、每個工具各打一條「不是管理者」）。
別處要一起看的：`tianxia/features/military/tests/test_admin_triggers.py`、`tests/server/test_action_tables.py`、`tianxia/features/smithy/tests/test_divine_rotation.py`、`tests/acts/test_conquest_rules.py`，還有直接叫 `admin_routes` 的 `tests/figures/test_week7_season.py`、`tests/server/test_server.py`、`tests/web/test_revamp_web.py`（改 `routes.py` 時 `test_for` 挑不到）。same_behavior 的軌：`switchboard`、`gavel`。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- `admin_choices` 走 `STATUS_ORDER["admin"]`，20 格。`web/admin.js` 由這一包宣告，`test_for.WEB_SCRIPTS` 拿掉它，改管理頁照這一包挑（第 90 批）；submit、change 分支第 85 批搬進 `admin.js`。
- 走不到的（`gavel` 軌的說明寫了）：跳到季末「時刻表上沒有下一件大事了」、神器用完那一句（`test_divine_rotation` 守）、第一季規則的季 `fire` 只回「沒有這件大事」。

## 重設密碼之後的扣押（帳號與客服第 208 批；設計 6.4）

`routes.reset_password` 成功之後，identity 開著（`core/identity_base.on`）才經核心 `identity_base.record_admin_reset` 寫旁檔：`reset_holds` 扣押 `Config.identity.reset_hold_hours`（72）小時
（不能花元寶、贈物、上架市集、綁定新的登入方式），一則「帳號」紀錄（`identity_base.NOTE_ADMIN_RESET`，identity 包下一輪寫進存檔）。回給管理者的字不變；identity 關著不碰旁檔。
這一包不 import identity 包，全經核心。測試 `tests/test_admin_reset_hold.py`。另外要跑的：改 `core/identity_base.py` 時跑 `tests/core/test_identity_base.py`、四包的 `test_*_phone_gate.py` 與 mall、peers、looks 的 `test_*_hold.py`、admin 的 `test_admin_reset_hold.py`。
