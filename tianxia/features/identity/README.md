# 帳號綁定（`tianxia/features/identity/`）

帳號可以不靠密碼：第三方（LINE、Google）、Email 與手機驗證碼登入、綁定與解綁、忘記密碼、綁手機才能用的功能。第 201 批（帳號一）只打底：沒有密碼的帳號與 `id:<n>` 鍵、登入頁的格與 `/api/identity/gate`、旁檔與備份還原；**第三方、驗證碼、綁定頁都還沒有**（第 202～205 批）。

- 導覽：`docs/guide/核心與存檔.md`（還沒寫那一節；句子在第 201 批回報的 docs，波末文件代理寫）。
- 設計稿：`docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md` 第 2 版（企劃者 2026-11-08 點頭）4.1、4.4、第七、八節；計畫 `docs/superpowers/plans/2026-11-08-帳號與客服-計畫.md`、`docs/superpowers/plans/2026-11-08-帳號與客服-第201批.md`。
- 開關：`Config.identity.enabled`（`tianxia/core/tuning/identity.py`，預設關）**加上** `.local/identity.json` 的金鑰讀得到（`{"key": "<至少 16 字>"}`，不進版控）；兩樣都在才算開著（`core/identity_base.on`）。關著：`/api/identity/gate` 404、登入頁一個字都不變（`web/identity.js` 問到 404 就不動）、`blocked_name` 一律回假、`phone_ok` 一律回真。
- 設定：`ways`（登入頁畫哪幾條路：`line`、`google`、`email`、`phone`）、`support_mail`（登入頁「登不進去？」那一行）、`turnstile_site_key`（第 203 批用）、`phone_gate`、`phone_required`（第 205 批才有人讀）。
- 內容：沒有內容檔。

## 這一包的東西在哪

- 核心 `tianxia/core/identity_base.py`（純規則，不 import 包）：手機與 Email 的正規化、遮罩、讀金鑰、`subject_hmac`、`on`、`phone_ok(ctx, feature_key)`（關著、`phone_gate` 關、不在名單、假人、沒有帳號都回真：看不出誰是假人）、`blocked_name`（開著才擋 `id:` 開頭與 `name_base.STAFF_NAMES`）。
- 核心 `tianxia/accounts.py`：`Account` 多 `key`、`id`；`id:<n>` 只認沒有 `password` 列的帳號；`create_without_password`、`add_login`、`remove_login`、`account_id`；管理者對沒有密碼的帳號重設回 `NO_PASSWORD`。有 `password` 列的帳號鍵照舊是小寫帳號（終身不變）。
- `store.py`：旁檔 `<db>-identity.sqlite`（跟著 `TIANXIA_DB`，同 `-push.sqlite`）：`bindings_meta`、`unbound`、`challenges`、`counters`、`session_auth` 五張表，WAL、寫一律 `BEGIN IMMEDIATE`，`count_and_record` 是「檢查並記一筆」。只有有人叫到 `IdentityStore` 才建（這一批沒有路由叫它）。時間一律傳入。
- `routes.py`：`GET /api/identity/gate`：不用登入（`tests/core/shell_tables.NO_LOGIN_ROUTES` 寫了理由）、不拿行動鎖、不看 cookie，只回設定裡公開的三樣。
- 畫面：`web/identity.js` 經殼的 `registerGateSlot` 掛在登入頁（`renderGate` 畫完叫 `drawGateSlots`）；開著時照企劃者 11/08 挑的 C 版（分段「快速登入｜帳號登入｜註冊」、上次選的格記在瀏覽器）；畫法全在 `identityGateHtml`。這一批四條路按了只說「尚未開放」。樣式 `web/identity.css`（選擇器都帶 `.gate`）。
- 掛鉤只接 `routes`。`enabled` 回 `identity_base.on`。選項前綴：沒有。假人沒有帳號，碰不到這一包。
- 殼：`web/shell.js` 三行（`GATE_SLOTS`、`registerGateSlot`、`drawGateSlots`）、`web/app.js` `renderGate` 一行，`scripts/sb/tracks/facade.py` 的 `FACADE_SHELL_LINES` 照字面放行；`server.name_taken` 與商城易名帖後備併 `blocked_name`。
- 旁檔 `-identity.sqlite`、`-support.sqlite`（客服包的，這一批只進清單）在 `scripts/sb/harness.py` 的 `_wipe_db`、`scripts/backup_db.py`（`SIDE_FILES`，跟主檔同一個時間戳）、`scripts/restore_db.py`。

## 認領的欄位（手冊 3.5）

`player_fields = ()`、`carried = ()`：沒有 `PlayerState` 欄位，資料在主資料庫的 `logins` 表（照現表多出 `provider` 不是 `password` 的列）與旁檔。主資料庫第 9 版不動。

## 退版

換回舊程式：沒有密碼的帳號 `_get` 查不到、進不來（第 201 批正式資料庫不會有這種帳號）；旁檔沒人讀；季中能換、不必休季。緊急開關 `Config.identity.enabled`。

## 測試

- 這一包：`tianxia/features/identity/tests/`（煙霧、旁檔、伺服器、網頁、`_wipe_db`）。
- 核心：`tests/core/test_identity_base.py`、`tests/core/test_accounts.py`（沒有密碼的帳號那一段）。
- 另外要跑的（`scripts/test_for.py` 照這一包挑不到）：`tests/core/test_accounts.py`、`tests/server/test_backup_db.py`、`tests/server/test_set_password.py`、`tests/web/test_webharness.py`、`tianxia/features/mall/tests/test_mall_card_daily.py`（易名帖擋名號）、`tests/server/test_server.py`（註冊撞保留名號）、`tests/core/test_shell_stays_thin.py`、`tests/web/test_shell_web.py`、`tests/bots/test_server_bots.py`（`web/identity.js` 不准寫假人字樣）。
