# 客服（`tianxia/features/support/`）

- 做什麼：玩家在設定抽屜送客服單、看自己的單與回覆、再回一句；名單上的客服在管理頁（`/admin`）看單、回覆、結單、請管理者處理、查帳號（客服二，第 212 批）；客服回覆了寫一則「客服」紀錄、推一則手機通知。
- 導覽：`docs/guide/商城.md` 的「客服」那一節（這兩批不寫導覽，句子交給波末的文件代理）
- 設計稿：`docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md` 第 2 版（企劃者 2026-11-08 點頭）第六節；計畫 `docs/superpowers/plans/2026-11-08-帳號與客服-第211批.md`、`2026-11-08-帳號與客服-第212批.md`、`2026-11-08-帳號與客服-第214批.md`（登入頁的客服信箱）；截圖是客服自動受理（設計 `2026-11-09-客服自動受理-design.md` 5.1、5.5，計畫 `2026-11-10-客服自動受理-計畫.md` 與 `2026-11-10-客服自動受理-第215批.md`）；客服官的 token、自動回覆標示、找真人、自動結單是第 216 批（設計 5.2～5.4、5.6②、七、八，計畫 `2026-11-10-客服自動受理-第216批.md`）

## 開關

`Config.support.enabled`（`tianxia/core/tuning/support.py`，預設關；緊急開關也是它）。關著時：

- `/api/support/*` 十三條（第 215 批加截圖的上傳與看圖兩條，第 216 批加找真人與自動結單兩條）一律 404 `{"detail":"Not Found"}`，跟沒有這條路逐位元組一樣（第 212 批起 gate 先於登入、先於參數解析：沒登入、壞 JSON、單號不是數字都一樣；十三條都在 `NO_LOGIN_ROUTES`，因為關著的 404 不是 401）；
- 登入頁沒有客服信箱那一行、不多問一次（`web/support.js` 只在 `S.identity` 設了才問 `/api/support/mailbox`，第 214 批）；
- `/api/me`、`/api/main` 不多任何鍵、`/api/push` 的 `kinds` 逐字不變、設定抽屜與管理頁的 HTML 一個位元組不變；
- 易名帖不多擋客服（`core/identity_base.support_staff_name` 關著回假）；
- 不建旁檔、不建截圖的資料夾。

開著時：沒登入 401（`GET /api/support/mailbox` 除外：不用登入，回 `{mailbox, line}`，不看 cookie、不開旁檔、對誰都同一份）；壞 JSON、內文不是物件 422；客服看單的單號不是數字 404「找不到這張單。」（認過客服之後才轉）。

## 數字（`Config.support`）

`body_max` 1000、`open_max` 3、`daily_max` 5、`mailbox`；第 212 批加 `lookup_hourly` 20（每位客服每小時查帳號幾次）、`ledger_rows` 50（帳號卡的帳本列幾筆）；第 215 批加 `files_max` 3（一張單最多幾張截圖，0＝主機把截圖關掉）、`file_bytes_max` 3,000,000（一張最多幾個位元組）；第 216 批加 `bot_account`（客服官用哪一個帳號：`accounts.id` 的數字或登入名，空的＝token 路一律 404）、`auto_close_days` 3（已回覆幾天沒動就自動結單）。

## 旁檔

`<db stem>-support.sqlite`（遊戲資料庫旁邊，跟著 `TIANXIA_DB`；`scripts/sb/harness.py` 的 `_wipe_db` 認得它）。不進資料庫第 9 版、沒有存檔欄位（`player_fields` 空的，不必 QUIET）。表都是 `CREATE TABLE IF NOT EXISTS`：第 211 批建的舊檔打開時補上新的兩張，舊的兩張不 ALTER。

- `tickets`：一張單。帳號 id、建帳號的時間（`accounts.created`）、登入名、名號、版本（`content/patch_notes.json` 最新一筆的日期）由伺服器填，不收客戶端的。看單、回單一律同時比單號、帳號 id、建帳號的時間（主檔退回舊時間點後 id 會被新帳號拿到）。
- `replies`：單上的每一則；`internal` 是「請管理者處理」的內部註記（玩家看不到、不推播），`seen` 是玩家看過了沒（紅點），`journaled` 是「客服」紀錄確定存進存檔了沒。
- `lookups`（第 212 批）：查帳號與看單帶出帳號卡，每一次一列：客服的帳號 id、單號、種類（`login`、`email`、`phone`、`card`）、`shown`（帳號存正規化後的，Email、手機只存 `mask_*` 遮好的字，不存明碼、不存雜湊）、查到的帳號 id、結果（`found`、`none`、`limit`、`card`、`gone`）、`counted`、時間。**只有 INSERT**（`store._log` 一處），沒有任何路由改或刪（客服改不到）。
- `pending_notes`（第 212 批）：寫進存檔、還沒確定存成的「客服」紀錄（`reply_id`、`ticket_id`、`at`＝寫進去那一下的遊戲時間）。
- `files`（第 215 批）：單上的截圖，一張一列（`seq` 從 1 起、`kind`＝副檔名 `png`／`jpg`／`webp`、`bytes`、`sha256`、時間；`UNIQUE (ticket_id, seq)`）。第 214 批的舊檔打開時補上這張表，舊的四張不 ALTER。
- `flags`（第 216 批）：單上的記號，`kind='human'`（玩家按了找真人，`ref` NULL，一張單最多一列）、`kind='relay'`（客服官轉達真人的那一則，`ref`＝`replies.id`）。第 215 批的舊檔打開時補上，舊的五張不 ALTER。
- 系統回覆（第 216 批，自動結單那一則）：`replies.by_account_id = 0`（`rules.SYSTEM_ACCOUNT`）、`staff=1`、`internal=0`、`seen=0`（紅點有）、`journaled=1`（不寫「客服」紀錄、不推播）。
- 截圖的資料夾 `<db stem>-support-files/<單號>/<seq>.<png|jpg|webp>`（`store.files_dir`，跟著 `TIANXIA_DB`）：只有上傳那一支建它。上傳先寫同一個資料夾裡的 `.upload-<uuid>.part`，`add_file` 在 `BEGIN IMMEDIATE` 裡查主人、沒結、張數、算 `seq`、記一列、`os.replace` 成正式檔名（先檔後列；換名失敗整筆 rollback、`.part` 刪掉）。有列無檔時看圖回 404。`scripts/sb/harness.py` 的 `_wipe_db` 只清 `.sqlite`：所有軌開關關著不會建這個資料夾，這一批不動它。
- 開著之後才有人建這個檔（第一張單送出的那一下）。備份與還原照 `scripts/backup_db.py`（帳號一已接 `-support.sqlite`；第 215 批起截圖的資料夾也整夾備份、還原、輪替：`SIDE_DIRS`）。

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

## 截圖（客服自動受理第 215 批；設計 5.1、5.5）

- `POST /api/support/file?id=<單號>`：內文就是圖的位元組（不解 JSON）。gate 之後先認登入（`shell._account` 只查記憶體的 SESSIONS，在讀內文之前；沒登入 401），`Content-Length` 說超過 `file_bytes_max` 的不讀就拒、說不超過的不信：`request.stream()` 串流累計，超過就停止讀、回「圖太大了：一張最多 3 MB。」。讀完丟執行緒池：單號不是數字 404、檔頭不是 PNG／JPEG／WebP 回「只收 PNG、JPEG、WebP 的圖。」（**只看前 12 位元組**，不信 `Content-Type`、不驗整張圖；內容不是圖的照檔頭存、照檔頭回，瀏覽器在 `nosniff` 下只畫成破圖）、別人的單與不存在的單 404「找不到這張單。」同一句（同再回一句）、結了回「這張單已經結了。」、滿了回「一張單最多附 3 張圖。」。回 `{id, seq, kind, bytes, files}`。不壓縮、不縮圖、不清 EXIF；回覆表單不附圖（圖掛單）。
- `GET /api/support/file/{tid}/{seq}`：沒登入 401；單的主人給，不是主人再看是不是客服（照 `_staff` 的兩個條件：名單上、這次是密碼登入且 6 小時內）；其他人、單或序號不存在、不是數字、列在而檔不見了一律 404「找不到這張單。」。`Content-Type` 照存的種類、`Content-Disposition: inline`。第 216 批起也認客服官的 Bearer。
- 看單（玩家 `mine`、客服 `ticket/{tid}`、`answer`、`close` 的回應）每張單多 `files: [{seq, kind, bytes}]`；`queue` 每一列多 `file_count`（`store.queue_extras` 一次查齊）。
- 畫面（A 版）：寫單多一格「附截圖」（`web/support.js` 的 `supportPickHtml`；挑的檔記在 `S.supportPicks`，重畫會清掉 file input；第 4 張起不收、單張超過 3 MB 當場擋），單送出之後逐張上傳，一張失敗就停、單留著、寫「單送出了，第 N 張圖沒傳上，可以在單上補。」；看單在內文下面一列縮圖（新分頁、`rel="noopener"`、`loading="lazy"`），沒結又不滿 3 張多一個「補一張圖」表單（一次一張）；客服頁的單同一列縮圖。前端的 3 張、3 MB 是寫死的（同設定預設值），伺服器照設定另外再擋。

## 客服官、找真人、自動結單（客服自動受理第 216 批；設計 5.2～5.4、第八節）

- **token 身分**：客服的路由帶 `Authorization: Bearer <token>` 就以它為準（`routes._staff`，不看 cookie、不看 6 小時的 session）：核心 `identity_base.support_bot_token()` 讀 `.local/support.json` 的 `bot_token`（只讀這一鍵；少於 32 字、壞 json、不是字串一律當沒設；照修改時間重讀），`hmac.compare_digest` 兩邊轉 bytes 比；`Config.support.bot_account` 的帳號在（`staff.bot_account_id`：全是數字只當 id，否則當登入名；名號不認）才回那個帳號。token 沒設、不對、非 ASCII、帳號不在一律 404 Not Found（跟不是客服同一句、不 500）。客服帶了錯的 token 也是 404（Bearer 贏）。`request.state.support_desk` 記這一次是不是 token 身分。
- token 打得到：清單、看單（含帳號卡）、看圖、回覆（`answer`）、結單、自動結單；**打不到查帳號**（`_lookup` 用 `allow_bot=False`，404、不留紀錄）。別的路由（`/api/do`、`/api/main`、`/api/me`、`/api/admin*`）根本不讀 Bearer（`test_support_bot.py::test_bot_token_rejected_by_every_admin_api_and_the_shell` 守）。
- **自動回覆的標示**：`rules.reply_auto`：系統回覆一律是；客服官的帳號回的、又不是轉達真人的才是。玩家的單每則多 `auto`、單多 `human`；客服的單每則多 `auto`、`system`，單多 `human`、`last_by`（最後一則看得到的回覆是誰：`player`／`staff`／`desk`／`system`／null；內部註記不算）；`queue` 每列多 `human`、`last_by`（`store.queue_extras` 一次查齊）。回應裡不出現 bot 這個字。沒設 `bot_account` 時只剩系統回覆認得出來。
- **轉達**：`answer` 在 token 身分收 `relay_from`（轉字串、去空白，空的當沒有；cookie 身分帶了不看；`then=admin` 不收）：那一則不算自動，同一筆交易多一列 `flags(relay)` 與一則內部註記「轉達自 <ID>」（不經 `then=admin`）。
- **admin_flag**：第 216 批起每次回覆設值（請管理者 1、其他 0），結單也清（以前只設不清，自動結單會永遠跳過它）。
- **找真人** `POST /api/support/human {id}`：主人才行（別人的、不存在 404「找不到這張單。」），結了回「這張單已經結了。」，按過再按照舊（冪等）；第一次按記一列 `flags(human)`、已回覆的單回到處理中。伺服器不要求單上已有自動回覆（畫面才看）。回這一張單（玩家看的）。
- **自動結單** `POST /api/support/sweep {}`：客服（cookie）或 token 叫，玩家 404 同一句；旁檔不在回 `{"closed": []}`、不建檔。`store.sweep` 在 `BEGIN IMMEDIATE` 裡才讀：已回覆、`admin_flag = 0`、最後一則（含內部註記）早於 `auto_close_days` 天的單，各記一則系統回覆「N 天沒再回，單自動結了。」並結掉；不推播。客服頁每次重讀清單前先打一次（失敗不擋）。
- 畫面（A 版）：玩家看單時自動回覆署名「客服（自動回覆）・回覆」；單沒結、有自動回覆、還沒按過，對話最下面、回覆表單上方一顆「找真人」（44px）；按過畫膠囊籤「已請真人處理」。客服頁：「系統」「客服官・自動回覆」兩種署名，單的標題旁與清單列有同一個籤。
- 這一批不做：橋、CLI、Discord（第 217 批）；真人客服頁的轉達鈕；客服官的動作上限（伺服器既有的字數、單數、狀態就是上限）。

## 主機端（客服自動受理第 217 批；設計 6.1、6.2、第七節）

兩支主機上的腳本，**都不 import `tianxia`**、不在遊戲的程式路徑上；預設路徑一律從腳本所在的 repo 根算（從 `C:\Ray\tianxia-support\` 啟動也一樣）。

- **橋** `scripts/support_bridge.py`：唯讀開旁檔（`mode=ro`，不建表、不寫），每 15 秒看 `tickets`、`replies`（只看玩家的）、`flags`（只看 `human`）、`files`，有新的就貼到 Discord 的 #客服（webhook，圖一起上），並在 `--log` 檔記一行（只有 `NEW 12`、`REPLY 12`、`HUMAN 12`、`FILE 12` 四種；`ALIVE` 每 5 分鐘印到 stdout，不進 log）。新單等 60 秒（`--grace`）或已有一張圖才貼，之後補的圖另貼 `FILE`；還在等的單，它的再回、找真人也先停著。貼的字不帶帳號（login）、Email、手機；`payload_json` 一律帶 `allowed_mentions`（找真人只點 `mention` 那兩個 ID，單裡寫 `@everyone` 點不到人）。進度逐張記在 `--state`（預設 `.local/support_bridge.json`）；逾時、429、5xx、旁檔被鎖這一輪不前進、下一輪再試（連續 10 輪印一行警告、不停）；400、401、403、404 等其他 4xx 印警告並前進。參數：`--db`（預設 `TIANXIA_DB`，再 `saves/tianxia.db`）、`--config`、`--state`、`--log`（必填）、`--interval 15`、`--grace 60`、`--once`、`--dry-run`。金鑰檔沒有 `discord_webhook` 等同 `--dry-run`：只記 log、進度照前進（之後補上 webhook 不補貼舊的）。
- **客服官的手** `scripts/support_cli.py`：只打 HTTP（`Authorization: Bearer <bot_token>`）。`queue`（先 `POST sweep` 再看清單；標籤 請管理者／等真人／等玩家／待客服官，最後一行四個數）、`ticket <n>`（單、每一則誰回的、帳號卡只印綁了哪幾種、截圖存到 `--inbox\<n>\<seq>.<副檔名>` 並印路徑）、`answer <n> [--close] [--human <Discord ID>]`、`note <n>`（請管理者處理的內部註記）、`close <n>`。**回覆與註記的字從 stdin 讀**，沒有 `--file`；stdin 空的不送（結束碼 1）。伺服器拒絕的句子原樣印（結束碼 1）；token 沒設、不對、或客服關著（404）印 token 那一句（結束碼 2）。**鎖定模式**：環境變數 `TIANXIA_SUPPORT_LOCKED=1` 時 `--config`、`--url`、`--inbox` 只照 `TIANXIA_SUPPORT_CONFIG`、`TIANXIA_SUPPORT_URL`、`TIANXIA_SUPPORT_INBOX`，命令列上帶了一律拒絕（結束碼 2）。永遠不印 token、帳號、Email、手機。
- **`.local/support.json` 的四個鍵**（不進版控，值不寫在任何文件裡）：`bot_token`（核心 `identity_base.support_bot_token()` 也讀這一個）、`discord_webhook`（可省：省了橋只記不貼）、`server_url`（CLI 用，預設 `http://127.0.0.1:7861`）、`mention`（找真人要點的 Discord ID，字串陣列）。
- 怎麼開、停：主機端操作文件「帳號綁定與客服」的「客服的橋（第 217 批）」。客服官 session 與 `cli.cmd` 是第 218 批。
- **客服官 session**（第 218 批；設計 6.3、6.4）：範本在 `docs/support/session/`（`CLAUDE.md` 七條規矩與醒來先 queue、`settings.local.json`、`cli.sh`、`cli.cmd`、`start.cmd`、`stop.cmd`），`scripts/support_session_init.py <工作夾> [--url] [--config] [--python]` 冪等抄過去（已經在的不蓋、`.cmd` 寫 CRLF、`cli.sh` 寫 LF；金鑰檔在工作夾裡就拒絕、結束碼 2）。客服官的許可白名單是 `mcp__plugin_discord_discord__reply`、`Bash(./cli.sh *)`、`Read(//<工作夾>/**)`、`Monitor(tail -n 0 -f bridge.log)`；**`cli.cmd` 不進白名單**：Git Bash 叫 `.cmd` 時參數不加引號交給 cmd，`"R&D"` 的 `&` 被 cmd 當成下一個指令（排練實跑），`cli.sh` 直接 exec python。兩支都設 `TIANXIA_SUPPORT_LOCKED=1` 與 `TIANXIA_SUPPORT_CONFIG`／`URL`／`INBOX`，參數含 `& | < > ^ !` 就結束碼 2。`scripts/support_knowledge.py <工作夾> [--profile] [--content]` 把 `content/patch_notes.json`、`docs/support/FAQ.md` 抄進 `knowledge\`、開一個暫存的世界（自己的 `TIANXIA_DB`，用完刪、還原）寫 `howto.md`（`Game.howto_text()`；新世界停在籌備中），三個檔過 `test_server_bots.FORBIDDEN` 同一張字表，命中就一個都不寫、結束碼 1。設定與企劃者要做的五樣：`docs/superpowers/discord/客服官-設定.md`；排練：`docs/support/排練.md`。

## 掛鉤與檔

- `routes`：`routes.py`，十三條 `/api/support/*`，全是 `async def`、第一行 `_gate_off`（關著 404）；`mailbox`（第 214 批）不用登入、直接回設定裡的字，其餘再自己解 JSON（截圖上傳除外），同步的本體丟執行緒池（sqlite 與 `shell._account` 都在那裡）。客服回覆（不是內部註記）經 `shell.WEB_PUSH` 推一則，`WEB_PUSH` 是 None、帳號關掉「客服」那一種都不送；自動結單不推。
- `on_own_turn`：第一行先看假人（假人沒有帳號、不開旁檔），再看開關、旁檔在不在。「客服」紀錄**先存檔成功再標**（第 212 批）：①上一輪寫進去、記在 `pending_notes` 的，到這一份存檔（伺服器每次進鎖從資料庫重讀）找那一則（標題、時間、那一句都對）：找到就標 `journaled`，找不到（上一輪沒存成）拿掉 pending、這一輪補寫；②沒寫、也不在 pending 的，一張單寫一則、記進 pending。極端情況：兩輪之間那一則被擠出 `journal.MAX_ENTRIES`（30 則）的話會補寫一次。
- `status_slots`：main 表的表外格 `support`（接在 `STATUS_ORDER` 尾）：開著回 `support_unread`（沒有帳號是 0：真人假人同一個樣子），客服再加 `support_staff: true`。
- `rules.py` 純規則（不讀時鐘；查帳號的種類、輸入檢查、正規化與遮好的字、這一小時、綁定與帳本的字）；`store.py` 旁檔；`staff.py` 名單的轉手；`accounts_view.py` 唯讀查主檔的 `accounts`、`logins`（帳號鍵照 `AccountStore.account_id`：`id:<n>` 的帳號也送得了單）；`lookup.py` 查帳號與帳號卡（唯讀）；`notes.py` 紀錄與 main 那一格。
- `gate_slot(config)` 與 `GATE_LINE`：登入頁客服信箱那一行的字（`Config.support.mailbox`）；第 214 批起 `GET /api/support/mailbox` 回、`web/support.js` 的 `supportGate`（`registerGateSlot`）畫在 `#gate-patch` 前面，信箱包在 `.sup-mail`（整段可選取）。只在 `/api/me` 帶 identity 旗標（`S.identity`）時才問：support 開、identity 關的那一種登入頁沒有這一行（殼在登入頁沒有 support 的旗標）。
- 畫面：`web/support.js`（`supportRow`、`supportPageHtml`、`supportDeskLink`、`renderSupportDesk`、`supportDeskHtml`、`supportCardHtml`；換版只換 `supportPageHtml`、`supportDeskHtml`，帳號卡只換 `supportCardHtml`）、`web/support.css`（前綴 `.sup-`：`.sp-` 是修練的）。管理頁客服 B 版：四格（沒回的、等玩家、今天新單、查帳剩）、左清單＋「查別的帳號」表單 `support-lookup-form`（查到的卡放 `S.supportDeskCard`，回單後保留）、右單＋帳號卡。殼那邊的接縫：`web/app.js` 三處（管理頁的條件、`sheetHtml` 的客服頁分派、抽屜的兩格）、`web/admin.js` 的 `renderAdmin` 開頭分流、`web/notify.js` 的「客服」種類、`web/index.html` 的 css link、`tests/kit/webharness.APP_FILES`（第 212 批一處都沒動）。
- 手機通知包多一種「客服」：`notify/notices.kinds(config)`（客服關著等於 `KINDS`）、`notify/routes.py` 三處照它。
- 核心：`tianxia/core/identity_base.py` 的客服名單（上面）；商城 `features/mall/actions.py` 的 `rename_self` 問它（`RENAME_STAFF`）。第 216 批起還有客服官的金鑰檔（`SUPPORT_BOT_FILE`、`support_bot_file`、`support_bot_token`）。

## 退版

資料庫第 9 版不動；沒有存檔欄位。旁檔多 `lookups`、`pending_notes` 兩張表（舊程式不讀，檔留著）；第 215 批再多 `files` 表與 `<db stem>-support-files/` 資料夾。換回第 214 批：`files` 表沒人讀、截圖的資料夾留著沒人看、兩條新路由不在（看單的回應少 `files`）；只停截圖不停客服：`files_max` 設 0。換回第 211 批：還在 pending 的回覆舊程式當沒寫過，最多各補寫一則「客服」紀錄；查帳紀錄留著沒人讀；`id:<n>` 的帳號又送不了單（401）；易名帖不再擋客服。季中能換、不必休季。緊急開關 `Config.support.enabled`。
第 216 批：旁檔多 `flags` 表（換回第 215 批沒人讀，單與回覆照讀）；換回後 token 路 404、`auto` 看不出來（自動回覆與系統回覆都顯示成「客服・回覆」）、`admin_flag` 又只設不清、兩條新路由不在。季中能換、不必休季。只停客服官：拿掉 `.local/support.json` 的 `bot_token`（或清 `bot_account`），再不行關 `Config.support.enabled`。
第 217 批：只多兩支主機腳本（`scripts/support_bridge.py`、`scripts/support_cli.py`）與主機上的 `.local/support_bridge.json`（橋的進度）、`.local/support-inbox/`（CLI 存的截圖）；資料庫、存檔、旁檔都不動，刪掉兩支腳本就沒了，季中能換、不必休季。只停貼 Discord：停橋（`taskkill /PID <pid> /T /F`）或拿掉 `discord_webhook`（只記不貼）；只停 CLI：拿掉 `bot_token`（全部 404）。
第 218 批：只多文件、範本（`docs/support/`）與兩支主機腳本（`scripts/support_session_init.py`、`scripts/support_knowledge.py`）；遊戲程式、資料庫、存檔、旁檔、`web/` 都不動，季中能換、不必休季。主機上多一個客服官的工作夾（`C:\Ray\tianxia-support\`，抄過去的檔留著）。只停客服官：關掉它的終端機、`stop.cmd` 停橋。

## 另外要跑的

- `test_for` 挑不到的：`tianxia/features/notify/tests/`（改了 notify 的 `kinds` 那三處）、`tests/web/test_shell_web.py`（表單框、點擊清單照字面）、`tests/bots/test_server_bots.py`（`web/support.js` 不准寫假人相關字）、`tianxia/features/mall/tests/test_mall_rename_staff.py` 與 `tests/core/test_identity_base.py`（改了核心 `identity_base` 的客服名單時：易名帖擋客服）。
- 第 215 批：`tests/server/test_backup_db.py`（截圖的資料夾跟著備份、還原、輪替）、`tests/web/test_shell_web.py`（`supportChange` 的框照字面）。
- 第 216 批：`tests/core/test_identity_base.py`（`support_bot_token`）、`tests/core/test_shell_stays_thin.py`（`NO_LOGIN_ROUTES` 兩條）、`tests/bots/test_server_bots.py`（`web/support.js` 新字）、`tests/web/test_shell_web.py`（`support-human` 的點擊清單照字面）。
- 情境：`scripts/same_behavior.py` 的 `petition` 軌（客服關著時登入的人打十三條、沒登入的人打 `mailbox`、`/api/main`、`/api/push`）；比對帶 `--new support`；第 212 批起 base 已經有這一包，要再加 `--also-existing`（K 波，PM 核對）。
- 第 217 批：改 `scripts/support_bridge.py`、`scripts/support_cli.py` 時 `test_for` 只帶邊界，另跑 `tianxia/features/support/tests/test_support_bridge.py`、`test_support_cli.py`；改了旁檔的表或欄位（`store.py` 的 `SCHEMA`）、`rules.CATEGORIES`、`/api/support/*` 的回應長相時，這兩個檔也要跑（兩支腳本自己照欄位與鍵讀，不 import 包）。
- 第 218 批：改 `docs/support/session/` 的範本、`docs/support/FAQ.md`、`scripts/support_session_init.py`、`scripts/support_knowledge.py` 時 `test_for` 只帶邊界（範本與 FAQ 是文件，挑不到），另跑 `tianxia/features/support/tests/test_support_session.py`；改 `content/patch_notes.json`、玩法說明（guide 包的 `howto`）時也跑它（匯出過 leaks 字表）。
- `test_for` 自己會帶、不用另外跑（PM J 波核對）：`tests/core/test_contract_features.py`（改包的檔帶核心契約 `[support]`）、`tests/core/test_shell_stays_thin.py`（改 `web/` 帶）。
