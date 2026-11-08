# 帳號綁定（`tianxia/features/identity/`）

帳號可以不靠密碼：第三方（LINE、Google）、Email 與手機驗證碼登入、綁定與解綁、忘記密碼、綁手機才能用的功能。第 201 批（帳號一）打底：沒有密碼的帳號與 `id:<n>` 鍵、登入頁的格與 `/api/identity/gate`、旁檔與備份還原。第 202 批（帳號二）：**LINE、Google 登入**；驗過、查無對應的身分不開帳號，到建角色成功才在同一筆交易開帳號。第 203 批（帳號三）加了 Email、手機驗證碼登入的兩條路由、防刷與寄送介面（見「驗證碼登入」；畫面還沒有），查無帳號一樣寫 `pending`、建角色走第 202 批那一條。**綁定頁、忘記密碼都還沒有**（第 204～205 批）。

- 導覽：`docs/guide/核心與存檔.md`（還沒寫那一節；句子在第 201、202 批回報的 docs，波末文件代理寫）。
- 設計稿：`docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md` 第 2 版（企劃者 2026-11-08 點頭）4.1、4.2、4.4、第七、八節；計畫 `docs/superpowers/plans/2026-11-08-帳號與客服-計畫.md`、`…-第201批.md`、`…-第202批.md`。
- 開關：`Config.identity.enabled`（`tianxia/core/tuning/identity.py`，預設關）**加上** `.local/identity.json` 的 `key` 讀得到（`{"key": "<至少 16 字>", "line": {"client_id", "client_secret"}, "google": {...}}`，不進版控）才算開著（`core/identity_base.on`）；LINE、Google 各自還要 `oauth.ready`（在 `ways` 裡、那一家兩欄都有、`redirect_base` 不空）。關著：四條路由 404、`/api/me` 不帶 `identity` 旗標、登入頁一個字都不變（`web/identity.js` 沒旗標連 gate 都不問）、`blocked_name` 一律回假、`phone_ok` 一律回真。只關第三方：`ways` 拿掉 line、google。
- 設定：`ways`（登入頁畫哪幾條路：`line`、`google`、`email`、`phone`）、`redirect_base`（回呼網址的前半，寫死設定值，例 `https://tianxiadashi.com`；回呼是 `<redirect_base>/auth/<provider>/callback`）、`ticket_seconds`（一次性單，600）、`pending_seconds`（還沒建角色的身分，1800）、`start_per_hour`（同一個來源 IP 一小時按幾次第三方登入，30）、`turnstile_site_key`（第 203 批用）、`phone_gate`、`phone_required`（第 205 批才有人讀）。客服信箱 `support_mail` 第 202 批拿掉（登入頁那一行歸客服包）。
- 內容：沒有內容檔。

## 這一包的東西在哪

- 核心 `tianxia/core/identity_base.py`（純規則，不 import 包）：手機與 Email 的正規化、遮罩、讀金鑰、`subject_hmac`、`on`、`phone_ok(ctx, feature_key)`（關著、`phone_gate` 關、不在名單、假人、沒有帳號都回真：看不出誰是假人）、`blocked_name`（開著才擋 `id:` 開頭與 `name_base.STAFF_NAMES`）。
- 核心 `tianxia/accounts.py`：`Account` 多 `key`、`id`；`id:<n>` 只認沒有 `password` 列的帳號；`create_without_password`、`login_key`（第 202 批：第三方身分查帳號鍵，subject 原樣比對；有密碼的帳號回小寫帳號）、`add_login`、`remove_login`、`account_id`；管理者對沒有密碼的帳號重設回 `NO_PASSWORD`。有 `password` 列的帳號鍵照舊是小寫帳號（終身不變）。
- `store.py`：旁檔 `<db>-identity.sqlite`（跟著 `TIANXIA_DB`，同 `-push.sqlite`）：`bindings_meta`、`unbound`、`challenges`、`counters`、`session_auth`，第 202 批加 `oauth_tickets`（一次性單：`take_ticket` 讀完就刪、過期當沒有）與 `pending`（驗過、還沒建角色的身分）；都是 `CREATE TABLE IF NOT EXISTS`，舊旁檔開的時候補建。WAL、寫一律 `BEGIN IMMEDIATE`，`count_and_record` 是「檢查並記一筆」。只有有人叫到 `IdentityStore` 才建（開著時的 start、callback、character 才叫）。時間一律傳入。
- `oauth.py`（第 202 批）：兩家的設定表（授權、token 網址、可接受的 `iss`；scope 只 `openid`，不要 Email 與個人資料）、`secrets`、`ready`、`authorize_url`（state、nonce、PKCE S256）、`exchange`（經模組層 `HTTP`，測試換成假的登入服務；逾時 10 秒，出錯當沒換到）、`claims`、`check`（`iss`、`aud`、`exp`、`nonce`、`sub`）。不驗簽章：`id_token` 是伺服器自己經 TLS 向 token 端點拿的（OIDC Core 3.1.3.7 第 6 項）。不讀時鐘。
- `routes.py`（都不拿行動鎖、不叫模型；現在時間照 `shell.time.time()`）：
  - `GET /api/identity/gate`：不用登入、不看 cookie，只回 `ways`（line、google 要 `ready` 才列）與 `turnstile`。
  - `POST /api/identity/start` `{provider, purpose: "login"}`：不用登入；provider 沒備好或 purpose 不是 login 404；已登入回 400「你已經登入了，要換帳號請先登出」；按來源 IP 節流（`counters` 的 `oauth:<ip>`）；寫票、發 `tx_oauth`（HttpOnly、Lax、`ticket_seconds`、path `/auth/`；票上存它的雜湊，擋登入 CSRF），回 `{"url": 授權網址}`。
  - `GET /auth/{provider}/callback`：不用登入；不認得的 provider 404；票一律作廢；`error` → 302 `/?auth=cancel`；票、`tx_oauth`、id_token 有一樣不對 → `/?auth=fail`；查得到帳號 → 開 session、`/?auth=ok`；查不到 → 寫 `pending`、發 `tx_pending`（path `/api/identity/`、`pending_seconds`）、`/?auth=new&via=<provider>`，**不開帳號**。一律刪 `tx_oauth`。
  - `POST /api/identity/character` `{name, gender}`：先看 cookie（`tx_pending`、`tx_session` 都沒有 401「請先登入。」）再過 gate；pending 拿不到 401 同一句；共用殼的註冊限制（`server._register_allowed`、`_registered`：跟密碼註冊一起算）；`create_without_password` 與 `server.create_character` 併進同一筆交易，名號不合格整筆退、帳號不留；成功寫 `bindings_meta`、刪 pending 與 cookie、開 session，回 `server._entry`。連按兩次：交易裡再查一次身分，查得到就直接登入、不再開。
- 畫面：`web/identity.js` 經殼的 `registerGateSlot` 掛在登入頁（`renderGate` 畫完叫 `drawGateSlots`）；`/api/me` 沒帶 `identity` 旗標（`app.js` `enter` 開頭那一行設 `S.identity`）就整支不動、不問 gate。開著時照企劃者 11/08 挑的 C 版（分段「快速登入｜帳號登入｜註冊」、上次選的格記在瀏覽器）。LINE、Google 鈕 POST start、整頁去授權網址；Email、手機按了只說「尚未開放」。LINE 與別的 App 內建網頁（`identityEnv`：`Line/`、FBAN、FBAV、Instagram、`; wv)`）藏 Google 鈕、多一行改用瀏覽器開的提示；從主畫面開的多一行提示。載入時讀 `?auth=`（ok、new、fail、cancel 才認）並 `replaceState` 拿掉 `auth`、`via`；fail、cancel 在登入頁說一句；new 下一拍切到殼的建角色頁，表單改名 `idp-create-form`（`identityForm` 認，送 `/api/identity/character`；殼的 submit 鏈不認它），底下多「已經有帳號？」一行與回帳號登入的鈕。畫法在 `identityGateHtml`、`identityCreateHtml`。樣式 `web/identity.css`（選擇器都帶 `.gate`、class 都是 `idp` 開頭）。
- 掛鉤只接 `routes`。`enabled` 回 `identity_base.on`。選項前綴：沒有。假人沒有帳號，碰不到這一包。
- 殼：`web/shell.js` 三行（`GATE_SLOTS`、`registerGateSlot`、`drawGateSlots`）、`web/app.js` `renderGate` 一行與 `enter` 開頭一行（第 202 批），`scripts/sb/tracks/facade.py` 的 `FACADE_SHELL_LINES` 照字面放行；`server.name_taken` 與商城易名帖後備併 `blocked_name`；`server.me` 開著才帶 `identity: True`（第 202 批）。`tests/core/shell_tables.NO_LOGIN_ROUTES` 列 gate、start、callback 三條（寫了理由）。
- cookie：`tx_oauth`、`tx_pending`（第 202 批，見上）；`secure` 照 `server.cookie_secure`。
- 旁檔 `-identity.sqlite`、`-support.sqlite`（客服包的）在 `scripts/sb/harness.py` 的 `_wipe_db`、`scripts/backup_db.py`（`SIDE_FILES`，跟主檔同一個時間戳）、`scripts/restore_db.py`。

## 驗證碼登入（第 203 批，帳號三；設計 4.2、4.6、4.7、第五節）

- 路由（不用登入，`tests/core/shell_tables.NO_LOGIN_ROUTES` 寫了理由；第一行 gate：關著、金鑰讀不到、這條路不在 `ways` 一律 404）：
  - `POST /api/identity/code/send` `{channel: "phone"|"email", to, turnstile}`：正規化（只收台灣手機門號）→ 伺服器端 Turnstile（沒過不碰計數）→ 查有沒有綁（決定池）→ 旁檔 `check_all_and_record` 一筆記完所有格 → 產碼、寄 → 開單、設 `tx_code`。寄出與額度滿了回同一份 `{message, notice, privacy}`（個資告知短文與隱私權連結），不透露有沒有帳號；滿了不寄、不開新單、舊單不動。只有寄送服務本身出錯才回「現在無法寄送」（計數不退）。
  - `POST /api/identity/code/verify` `{code}`：單從 `tx_code` 取（別的瀏覽器拿不到你的單）。沒單、過期、錯碼回同一句；錯碼算在單上，錯 5 次刪單；對了刪單。有帳號：開 session（`shell._start_session`）、`session_auth` 記這次是 `phone`／`email`、`bindings_meta.verified_at` 更新、這個瀏覽器記進 `trusted_devices`（`tx_dev`）、回 `shell._entry`。查無帳號：只寫 `pending`、設 `tx_pending`、回 `{stage: "create", pending: true}`，**不開帳號**（建角色那一步開帳號是第 202 批的待處理流程）。
- 規則 `codes.py`（純規則，不讀時鐘、不讀環境）：一號 `resend_seconds`（60）秒一次；每日兩格擇一（沒用這個身分登入過的瀏覽器共用 `daily_shared` 5 次；曾成功登入的瀏覽器另有 `daily_trusted` 5 次，偽造的 `tx_dev` 查不到＝共用格）；來源一小時 `source_hour` 10 次（IPv4 一格；IPv6 以 /64 一格、再加 /48 一格）；全服分池 `sms_caps`／`mail_caps`（`login` 已綁、`bind` 第 204 批、`anon` 沒綁；[每天, 每小時]）。桶名 `resend:`、`day:`、`src:`、`pool:`，身分一律是 `subject_hmac`。碼 6 位（`secrets`），只存 `HMAC(金鑰, challenge_id|碼)`；同一個身分同一種用途開新單時舊單作廢；`code_ttl` 300 秒過期。玩家看的字全在這一檔最上面。
- 寄送 `senders.py`：`SmsSender`、`MailSender`、`TurnstileVerifier` 三個介面；`fake_services` 開著用 `FAKES`（`FakeSms`、`FakeMail` 只記 `outbox`，`FakeTurnstile` 只認 `"ok"`）；關著（正式機）簡訊與信是 `NoSender`（服務商接上之前一寄就「現在無法寄送」）、Turnstile 是 `CloudflareTurnstile`（siteverify，驗 `success`、`hostname`、`action`＝`turnstile_action`，逾時 5 秒，出錯當沒過；secret 在 `.local/identity.json` 的 `turnstile_secret`）。
- 旁檔多的：`challenges` 三欄 `channel`、`subject_hmac`、`display`（第 201 批開的舊旁檔開檔時補）、`trusted_devices` 一表；`pending` 跟第 202 批共用一張（多 `display` 欄）。主資料庫只讀 `logins`（`core/identity_base.account_key_for`），不寫。
- cookie（HttpOnly、SameSite=Lax、`secure` 照 `shell.cookie_secure`）：`tx_code`（單的 id，`code_ttl`）、`tx_dev`（長效隨機，成功登入才發；旁檔只存 sha256）、`tx_pending`（同第 202 批：`pending_seconds`、path `/api/identity/`；合 K 波時從 10 分鐘併成同一個設定）。
- 設定（`tianxia/core/tuning/identity.py`）：`code_ttl`、`code_tries`、`resend_seconds`、`daily_shared`、`daily_trusted`、`source_hour`、`sms_caps`、`mail_caps`、`fake_services`（**正式機必須 false**：假的不會真的寄、假的 Turnstile 會放行）、`turnstile_action`、`privacy_url`（條款包的隱私權頁）。
- 畫面：這一批不畫（派工單不准碰 `web/`）。登入頁 C 版的手機驗證碼流程、Turnstile 元件、個資告知短文與隱私權連結留給准碰 `web/identity.js` 的那一批（畫法集中在一個 `drawCodeForm()`）。
- 情境軌 `scripts/sb/tracks/missive.py`：三種設定關著，沒登入（含偽造 `tx_code`）與登入的人打兩條路由都是 404。
- 還沒做：綁定用途的碼（`bind` 池，第 204 批）、門號回收、到池上限通知管理者。建角色時把 `pending` 開成帳號：合 K 波時接上第 202 批的 `/api/identity/character`（`logins.display` 寫 `pending.display` 遮罩過的號碼）。

## 認領的欄位（手冊 3.5）

`player_fields = ()`、`carried = ()`：沒有 `PlayerState` 欄位，資料在主資料庫的 `logins` 表（照現表多出 `provider` 不是 `password` 的列：第 202 批起有 `line`、`google`，`subject` 是對方的使用者編號原樣、`display` 是「LINE」「Google」）與旁檔。主資料庫第 9 版不動。

## 退版

換回舊程式：沒有密碼的帳號（第 202 批起 LINE、Google 開的，第 203 批起驗證碼開的）`_get` 查不到、進不來（角色在、資料不丟，再換回來照登），密碼帳號不受影響；旁檔（多出的兩張表）沒人讀；`tx_oauth`、`tx_pending` cookie 舊程式不認、自己過期；資料庫第 9 版不動、沒有遷移；季中能換、不必休季。備份照舊 `scripts/backup_db.py --dest <資料夾> --tag manual`。緊急開關 `Config.identity.enabled`（關著四條路由 404、`/api/me` 不帶旗標、登入頁不變），或 `ways` 拿掉 line、google 只關第三方。
第 203 批：資料庫第 9 版不動、主資料庫不寫、沒有新存檔欄位；旁檔只在開著且有人送碼才多一表三欄，舊程式不讀、留著無害；`tx_code`、`tx_dev`、`tx_pending` 舊程式不認。驗證碼另一個緊急開關：從 `ways` 拿掉 `email`、`phone`（兩條路由 404）。

## 測試

- 這一包：`tianxia/features/identity/tests/`（煙霧、旁檔、伺服器、網頁、`_wipe_db`；第 202 批加 `test_identity_oauth.py`、`test_identity_login.py`：假的登入服務換 `oauth.HTTP`；第 203 批 `test_identity_codes.py` 純規則與寄送、`test_identity_code_routes.py` 兩條路由）。
- 情境：`scripts/sb/tracks/wicket.py`（`--track wicket`：關著時四條路由與 `/api/me`）；`scripts/sb/tracks/missive.py`（`--track missive`：第 203 批兩條路由）。
- 核心：`tests/core/test_identity_base.py`、`tests/core/test_accounts.py`（沒有密碼的帳號那一段）。
- 另外要跑的（`scripts/test_for.py` 照這一包挑不到）：`tests/core/test_accounts.py`、`tests/server/test_backup_db.py`、`tests/server/test_set_password.py`、`tests/web/test_webharness.py`、`tianxia/features/mall/tests/test_mall_card_daily.py`（易名帖擋名號）、`tests/server/test_server.py`（註冊撞保留名號；第 202 批再加 `-k "register or login or me"`：`/api/me` 與共用的註冊限制）、`tests/core/test_shell_stays_thin.py`、`tests/web/test_shell_web.py`、`tests/bots/test_server_bots.py`（`web/identity.js` 不准寫假人字樣）、`tests/core/test_contract_features.py -k identity`、`tests/core/test_feature_boundaries.py`；第 203 批：驗證碼路由的回應由這一包的 `test_bots_cannot_be_told_apart` 用同一個 `leaks` 掃、`tests/core/test_identity_base.py`（`account_key_for`）。
