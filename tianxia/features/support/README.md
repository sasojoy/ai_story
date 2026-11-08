# 客服（`tianxia/features/support/`）

- 做什麼：玩家在設定抽屜送客服單、看自己的單與回覆、再回一句；名單上的客服在管理頁（`/admin`）看單、回覆、結單、請管理者處理、查帳號（客服二，第 212 批）；客服回覆了寫一則「客服」紀錄、推一則手機通知。
- 導覽：`docs/guide/商城.md` 的「客服」那一節（這兩批不寫導覽，句子交給波末的文件代理）
- 設計稿：`docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md` 第 2 版（企劃者 2026-11-08 點頭）第六節；計畫 `docs/superpowers/plans/2026-11-08-帳號與客服-第211批.md`、`2026-11-08-帳號與客服-第212批.md`

## 開關

`Config.support.enabled`（`tianxia/core/tuning/support.py`，預設關；緊急開關也是它）。關著時：

- `/api/support/*` 八條一律 404 `{"detail":"Not Found"}`，跟沒有這條路逐位元組一樣（第 212 批起 gate 先於登入、先於參數解析：沒登入、壞 JSON、單號不是數字都一樣；`NO_LOGIN_ROUTES` 不加）；
- `/api/me`、`/api/main` 不多任何鍵、`/api/push` 的 `kinds` 逐字不變、設定抽屜與管理頁的 HTML 一個位元組不變；
- 易名帖不多擋客服（`core/identity_base.support_staff_name` 關著回假）；
- 不建旁檔。

開著時：沒登入 401；壞 JSON、內文不是物件 422；客服看單的單號不是數字 404「找不到這張單。」（認過客服之後才轉）。

## 數字（`Config.support`）

`body_max` 1000、`open_max` 3、`daily_max` 5、`mailbox`；第 212 批加 `lookup_hourly` 20（每位客服每小時查帳號幾次）、`ledger_rows` 50（帳號卡的帳本列幾筆）。

## 旁檔

`<db stem>-support.sqlite`（遊戲資料庫旁邊，跟著 `TIANXIA_DB`；`scripts/sb/harness.py` 的 `_wipe_db` 認得它）。不進資料庫第 9 版、沒有存檔欄位（`player_fields` 空的，不必 QUIET）。表都是 `CREATE TABLE IF NOT EXISTS`：第 211 批建的舊檔打開時補上新的兩張，舊的兩張不 ALTER。

- `tickets`：一張單。帳號 id、建帳號的時間（`accounts.created`）、登入名、名號、版本（`content/patch_notes.json` 最新一筆的日期）由伺服器填，不收客戶端的。看單、回單一律同時比單號、帳號 id、建帳號的時間（主檔退回舊時間點後 id 會被新帳號拿到）。
- `replies`：單上的每一則；`internal` 是「請管理者處理」的內部註記（玩家看不到、不推播），`seen` 是玩家看過了沒（紅點），`journaled` 是「客服」紀錄確定存進存檔了沒。
- `lookups`（第 212 批）：查帳號與看單帶出帳號卡，每一次一列：客服的帳號 id、單號、種類（`login`、`email`、`phone`、`card`）、`shown`（帳號存正規化後的，Email、手機只存 `mask_*` 遮好的字，不存明碼、不存雜湊）、查到的帳號 id、結果（`found`、`none`、`limit`、`card`、`gone`）、`counted`、時間。**只有 INSERT**（`store._log` 一處），沒有任何路由改或刪（客服改不到）。
- `pending_notes`（第 212 批）：寫進存檔、還沒確定存成的「客服」紀錄（`reply_id`、`ticket_id`、`at`＝寫進去那一下的遊戲時間）。
- 開著之後才有人建這個檔（第一張單送出的那一下）。備份與還原照 `scripts/backup_db.py`（帳號一已接 `-support.sqlite`）。

## 客服名單（認帳號，不認名號）

三個來源合起來：`Config.support.staff`、`.local/support.txt`（一行一個、`#` 開頭是註解，照修改時間重讀）、`TIANXIA_SUPPORT`（逗號分開）。每一筆是 `accounts.id` 的數字或登入名（不分大小寫；全是數字的一筆只當 id）。第 212 批起本體在核心 `tianxia/core/identity_base.py`（`support_names`、`support_staff`、`support_staff_name`：商城的易名帖也要問，包不能 import 別包）；`staff.py` 留同名轉手（`_cache` 是同一個 dict）。不是名單上的人打客服那五條一律 404（跟沒有這條路同一句）。客服不走 `AdminTool`、`/api/admin*` 一條都打不過（`tests/test_support_staff.py::test_staff_rejected_by_every_admin_api` 守），`is_admin` 不動。**客服本人不能用易名帖改名**（同管理者；客服開著才擋，帖不用掉）。

## 查帳號（第 212 批；設計 6.3）

- `POST /api/support/lookup` `{id, kind, text}`：只收完整帳號（`AccountStore.account_id`；`id:<n>` 不收）、完整 Email、完整手機（`identity_base` 正規化後算 HMAC，`account_key_for` 找帳號；identity 關著或金鑰讀不到就查無）。不收名號、不做模糊搜尋。
- 要帶單號：單不存在 404（不算次數、不留紀錄）；寫法不對回那一句（不算、不留）。
- 每位客服每小時 `lookup_hourly` 次（`now-3600` 起 `counted=1` 的數），數與記在同一筆 `BEGIN IMMEDIATE`；滿了記一筆 `limit`（不算）、回「這一小時查帳號的次數用完了」。查無也算一次、也留紀錄。
- 看單（`GET /api/support/ticket/{tid}`）時單上的帳號直接帶出帳號卡 `card`（帳號 id 與建帳號的時間對得上才給，不對給 `{gone: true}`）：**不算查帳次數，照樣記一筆** `card`／`gone`（企劃者 11/08 挑 B 版）。`answer`、`close` 的回應不帶卡，畫面沿用看單時的。
- 帳號卡（`lookup.card`）：帳號、名號、建帳號日、綁了哪幾種（只有 Email、手機帶遮好的顯示字；LINE、Google 的暱稱不給）、餘額與 `Wallet.ledger` 最近 `ledger_rows` 筆（還沒有角色就是空的）。帳本的原因字是 `rules.LEDGER_REASONS`（同商城 `REASONS`；月卡那幾份照原因字寫，不照編號細分）。
- `GET /api/support/queue` 多 `lookups_left`（這位客服這一小時還剩幾次）。
- 假人沒有帳號：拿假人的名號當帳號查，回應跟亂打的字一樣（查無），卡永遠不會是假人。
- 要補發、退款、重設密碼、解綁、刪帳號：在單上註記，請管理者做（這一包不做）。

## 掛鉤與檔

- `routes`：`routes.py`，八條 `/api/support/*`，全是 `async def`、第一行 `_gate_off`（關著 404），再自己解 JSON，同步的本體丟執行緒池（sqlite 與 `shell._account` 都在那裡）。客服回覆（不是內部註記）經 `shell.WEB_PUSH` 推一則，`WEB_PUSH` 是 None、帳號關掉「客服」那一種都不送。
- `on_own_turn`：第一行先看假人（假人沒有帳號、不開旁檔），再看開關、旁檔在不在。「客服」紀錄**先存檔成功再標**（第 212 批）：①上一輪寫進去、記在 `pending_notes` 的，到這一份存檔（伺服器每次進鎖從資料庫重讀）找那一則（標題、時間、那一句都對）：找到就標 `journaled`，找不到（上一輪沒存成）拿掉 pending、這一輪補寫；②沒寫、也不在 pending 的，一張單寫一則、記進 pending。極端情況：兩輪之間那一則被擠出 `journal.MAX_ENTRIES`（30 則）的話會補寫一次。
- `status_slots`：main 表的表外格 `support`（接在 `STATUS_ORDER` 尾）：開著回 `support_unread`（沒有帳號是 0：真人假人同一個樣子），客服再加 `support_staff: true`。
- `rules.py` 純規則（不讀時鐘；查帳號的種類、輸入檢查、正規化與遮好的字、這一小時、綁定與帳本的字）；`store.py` 旁檔；`staff.py` 名單的轉手；`accounts_view.py` 唯讀查主檔的 `accounts`、`logins`（帳號鍵照 `AccountStore.account_id`：`id:<n>` 的帳號也送得了單）；`lookup.py` 查帳號與帳號卡（唯讀）；`notes.py` 紀錄與 main 那一格。
- `gate_slot(config)` 與 `GATE_LINE`：登入頁客服信箱那一行的字（`Config.support.mailbox`），帳號一的 `registerGateSlot` 合進來後由 PM 接，還沒人叫。
- 畫面：`web/support.js`（`supportRow`、`supportPageHtml`、`supportDeskLink`、`renderSupportDesk`、`supportDeskHtml`、`supportCardHtml`；換版只換 `supportPageHtml`、`supportDeskHtml`，帳號卡只換 `supportCardHtml`）、`web/support.css`（前綴 `.sup-`：`.sp-` 是修練的）。管理頁客服 B 版：四格（沒回的、等玩家、今天新單、查帳剩）、左清單＋「查別的帳號」表單 `support-lookup-form`（查到的卡放 `S.supportDeskCard`，回單後保留）、右單＋帳號卡。殼那邊的接縫：`web/app.js` 三處（管理頁的條件、`sheetHtml` 的客服頁分派、抽屜的兩格）、`web/admin.js` 的 `renderAdmin` 開頭分流、`web/notify.js` 的「客服」種類、`web/index.html` 的 css link、`tests/kit/webharness.APP_FILES`（第 212 批一處都沒動）。
- 手機通知包多一種「客服」：`notify/notices.kinds(config)`（客服關著等於 `KINDS`）、`notify/routes.py` 三處照它。
- 核心：`tianxia/core/identity_base.py` 的客服名單（上面）；商城 `features/mall/actions.py` 的 `rename_self` 問它（`RENAME_STAFF`）。

## 退版

資料庫第 9 版不動；沒有存檔欄位。旁檔多 `lookups`、`pending_notes` 兩張表（舊程式不讀，檔留著）。換回第 211 批：還在 pending 的回覆舊程式當沒寫過，最多各補寫一則「客服」紀錄；查帳紀錄留著沒人讀；`id:<n>` 的帳號又送不了單（401）；易名帖不再擋客服。季中能換、不必休季。緊急開關 `Config.support.enabled`。

## 另外要跑的

- `test_for` 挑不到的：`tianxia/features/notify/tests/`（改了 notify 的 `kinds` 那三處）、`tests/web/test_shell_web.py`（表單框、點擊清單照字面）、`tests/bots/test_server_bots.py`（`web/support.js` 不准寫假人相關字）、`tianxia/features/mall/tests/test_mall_rename_staff.py` 與 `tests/core/test_identity_base.py`（改了核心 `identity_base` 的客服名單時：易名帖擋客服）。
- 情境：`scripts/same_behavior.py` 的 `petition` 軌（客服關著時登入的人打八條、`/api/main`、`/api/push`）；比對帶 `--new support`；第 212 批起 base 已經有這一包，要再加 `--also-existing`（K 波，PM 核對）。
- `test_for` 自己會帶、不用另外跑（PM J 波核對）：`tests/core/test_contract_features.py`（改包的檔帶核心契約 `[support]`）、`tests/core/test_shell_stays_thin.py`（改 `web/` 帶）。
