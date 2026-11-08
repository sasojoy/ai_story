# 客服（`tianxia/features/support/`）

- 做什麼：玩家在設定抽屜送客服單、看自己的單與回覆、再回一句；名單上的客服在管理頁（`/admin`）看單、回覆、結單、請管理者處理；客服回覆了寫一則「客服」紀錄、推一則手機通知。查帳號、帳號卡的元寶帳本是客服二（下一批），這一包還沒有。
- 導覽：`docs/guide/商城.md` 的「客服」那一節（這一批不寫導覽，句子交給波末的文件代理）
- 設計稿：`docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md` 第 2 版（企劃者 2026-11-08 點頭）第六節；計畫 `docs/superpowers/plans/2026-11-08-帳號與客服-第211批.md`

## 開關

`Config.support.enabled`（`tianxia/core/tuning/support.py`，預設關；緊急開關也是它）。關著時：

- `/api/support/*` 七條：沒登入 401（開著關著一樣，所以 `NO_LOGIN_ROUTES` 不加），登入了 404；
- `/api/main` 不多任何鍵、`/api/push` 的 `kinds` 逐字不變、設定抽屜與管理頁的 HTML 一個位元組不變；
- 不建旁檔。

## 旁檔

`<db stem>-support.sqlite`（遊戲資料庫旁邊，跟著 `TIANXIA_DB`；`scripts/sb/harness.py` 的 `_wipe_db` 認得它）。不進資料庫第 9 版、沒有存檔欄位（`player_fields` 空的，不必 QUIET）。

- `tickets`：一張單。帳號 id、建帳號的時間（`accounts.created`）、登入名、名號、版本（`content/patch_notes.json` 最新一筆的日期）由伺服器填，不收客戶端的。看單、回單一律同時比單號、帳號 id、建帳號的時間（主檔退回舊時間點後 id 會被新帳號拿到）。
- `replies`：單上的每一則；`internal` 是「請管理者處理」的內部註記（玩家看不到、不推播），`seen` 是玩家看過了沒（紅點），`journaled` 是寫過「客服」紀錄沒。
- 開著之後才有人建這個檔（第一張單送出的那一下）。備份與還原這個檔是帳號一（`scripts/backup_db.py`）的事，開線上前要先合帳號一。

## 客服名單（認帳號，不認名號）

三個來源合起來（`staff.py`）：`Config.support.staff`、`.local/support.txt`（一行一個、`#` 開頭是註解，照修改時間重讀）、`TIANXIA_SUPPORT`（逗號分開）。每一筆是 `accounts.id` 的數字或登入名（不分大小寫）。不是名單上的人打客服那四條一律 404（跟沒有這條路同一句）。客服不走 `AdminTool`、`/api/admin*` 一條都打不過（`tests/test_support_staff.py::test_staff_rejected_by_every_admin_api` 守），`is_admin` 不動。

## 掛鉤與檔

- `routes`：`routes.py`，七條 `/api/support/*`；第一行 `_gate`（先登入、再看開關）。客服回覆（不是內部註記）經 `shell.WEB_PUSH` 推一則，`WEB_PUSH` 是 None、帳號關掉「客服」那一種都不送。
- `on_own_turn`：第一行先看假人（假人沒有帳號、不開旁檔），再看開關、旁檔在不在；有還沒寫過的客服回覆就一張單寫一則「客服」紀錄。**已知**：旁檔先把 `journaled` 標成 1、紀錄才寫進存檔，兩邊不是同一筆交易；那一輪存檔沒成功（例外、Game 物件被丟掉），那一則「客服」紀錄就不會再寫（未讀紅點照舊在）。要補就改成存檔成功後再標（留給下一波，第 J 波審查）。
- `status_slots`：main 表的表外格 `support`（接在 `STATUS_ORDER` 尾）：開著回 `support_unread`（沒有帳號是 0：真人假人同一個樣子），客服再加 `support_staff: true`。
- `rules.py` 純規則（不讀時鐘）；`store.py` 旁檔；`staff.py` 名單；`accounts_view.py` 唯讀查主檔的 `accounts`、`logins`（帳號一的 `accounts.account_id` 合進來後換過去）；`notes.py` 紀錄與 main 那一格。
- `gate_slot(config)` 與 `GATE_LINE`：登入頁客服信箱那一行的字（`Config.support.mailbox`），帳號一的 `registerGateSlot` 合進來後由 PM 接，這一批沒人叫。
- 畫面：`web/support.js`（`supportRow`、`supportPageHtml`、`supportDeskLink`、`renderSupportDesk`、`supportDeskHtml`；換版只換 `supportPageHtml`、`supportDeskHtml`）、`web/support.css`（前綴 `.sup-`：`.sp-` 是修練的）。殼那邊的接縫：`web/app.js` 三處（管理頁的條件、`sheetHtml` 的客服頁分派、抽屜的兩格）、`web/admin.js` 的 `renderAdmin` 開頭分流、`web/notify.js` 的「客服」種類、`web/index.html` 的 css link、`tests/kit/webharness.APP_FILES`。
- 手機通知包多一種「客服」：`notify/notices.kinds(config)`（客服關著等於 `KINDS`）、`notify/routes.py` 三處照它。

## 另外要跑的

- `test_for` 挑不到的：`tianxia/features/notify/tests/`（改了 notify 的 `kinds` 那三處）、`tests/web/test_shell_web.py`（表單框、點擊清單照字面）、`tests/bots/test_server_bots.py`（`web/support.js` 不准寫假人相關字）。
- 情境：`scripts/same_behavior.py` 的 `petition` 軌（客服關著時登入的人打七條、`/api/main`、`/api/push`）；比對帶 `--new support`。
- `test_for` 自己會帶、不用另外跑（PM J 波核對）：`tests/core/test_contract_features.py`（改包的檔帶核心契約 `[support]`）、`tests/core/test_shell_stays_thin.py`（改 `web/` 帶）。
