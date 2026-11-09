# 條款 `tianxia/features/terms/`

- **做什麼**：使用條款與隱私權條款兩頁（`/terms`、`/privacy`，不用登入、開關關著也看得到）；登入後沒同意過現行版的帳號疊一層請他按同意；條款大改時，考慮期內上線的人看到改版頁（可以先關掉，過了考慮期視為接受）。登入頁與設定頁底下各兩個連結。
- **導覽**：`docs/guide/核心與存檔.md` 的「條款」一節。
- **設計稿**：https://claude.ai/artifact/BxXB4qnXvtDfCKUjmwuDj4（使用條款與隱私權 設計稿 v2，Joy 2026-11-07 給公司名義）。帳號註冊與綁定、客服系統 11/7 起交給另一位（條款裡寫「客服管道（另案建置）」）。
- **開關**：`Config.terms.enabled`（預設關）、`grace_days`（15，定型化契約應記載事項十七）。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`TermsFeature`）：沒有選項前綴、沒有 PlayerState 欄位；`routes`、`check_content`；`web`＝`terms.js`、`terms.css`；`content`＝`terms.json` |
| `content/terms.json` | 條款全文、公司名義、版本（`version`、`published`）、同意頁的三句重點。**大改**換 `version` 與 `published`；**小改**只改字與 `updated` |
| `rules.py` | 純規則：讀內容檔（改了就重讀）、`need`（`must`／`ask`／空字串）、`check` |
| `store.py` | 同意紀錄的小檔 `<db>-terms.sqlite`（只加不刪；同手機通知的 `<db>-push.sqlite`，不進遊戲資料庫、資料庫不升版） |
| `pages.py` | 兩頁的 HTML |
| `routes.py` | `/terms`、`/privacy`、`/api/terms`、`/api/terms/agree`；`record_consent(shell, account_key, version, source="register")` 給註冊那一邊叫 |
| `tests/` | `test_terms.py`（規則、小檔、API）、`test_terms_register.py`（第 206 批：殼的註冊兩個勾選、記 `register`、`/api/terms/version`）、`test_terms_web.py`（第 206 批：`terms.js` 插勾選與擋送出，node 假 DOM）、煙霧 |

**給註冊那一邊（第 206 批接好了）**：註冊有兩條路——殼的 `/api/register`（`server.register`）與 identity 包建角色那一步（`/api/identity/character`，第三方、驗證碼第一次進來才開帳號）。包不准互相 import，所以經核心接縫 `tianxia/core/terms_base.py`：`router(shell)` 開頭 `terms_base.set_hook(_Hook(shell))`（`version()` 讀 `rules.load()["version"]`、`record` 叫 `record_consent`）。開新帳號之前 `terms_base.register_problem(CONTENT, body)`：開著時 `age_ok`、`terms_agree` 都要勾（認 `true`、`"on"`）、`terms_version` 要等於現行版，不然回同一句 `REGISTER_NEED`（不透露版本、不透露帳號在不在），殼與 identity 自己丟 `GameError`；被擋下的不算一次註冊。帳號建好之後 `terms_base.record(CONTENT, key, 表單帶的版號)` 記一筆 `source=register`（記玩家勾過的那一版；剛好改版丟的 `ValueError(STALE)` 吞掉，登入後同意層補問）。所以註冊時勾過的人進遊戲 `/api/terms` 的 `need` 是空字串、不跳層。關著（或包沒掛）兩個函式直接 return，註冊與建角色跟沒有這一包一樣。
- `GET /api/terms/version`（第 206 批）：不用登入（`NO_LOGIN_ROUTES` 寫了理由：還沒有帳號的人要拿得到）、第一行 gate、關著 404，只回 `{version}`。

**網頁**：`web/terms.js` 不改 `app.js`，用 MutationObserver 看 `#app`：登入頁（`.gate`）與設定頁（`.sheet[aria-label="設定"]`）底下補連結；進了遊戲問一次 `/api/terms`。網頁測試的 node 沒有 DOM，整段跳過。
第 206 批：同一個 MutationObserver 裡 `termsInsertChecks`——註冊模式的 `#gate-form`（有 `name="again"` 那一格才算註冊）與 identity 建角色那一張 `#idp-create-form` 的 `.form-msg` 前面插兩個勾選與 hidden `terms_version`（畫法集中在 `termsChecksHtml`，樣式 `terms.css` 的 `.terms-check`）；登入模式與殼自己的 `#create-form`（帳號已經開了）不插。版號第一次要用才問 `/api/terms/version`，非 200（關著 404）這一頁不再問、不插；斷線下一次再問。`document` 上 capture 的 submit（先於 `app.js` 的 submit 鏈）：表單裡有勾選而沒全勾就擋下、表單下面寫 `TERMS_SAY.need`。送出照殼與 identity 原本的整張表單序列化，三欄自然帶上。
第 210 批：兩格都勾了的那一次送出先攔下（`termsResend`）、不經快取重問 `/api/terms/version`（問到的寫回快取）、換掉 hidden `terms_version`，再 `form.requestSubmit()` 送一次（`termsFresh` 記著，那一次放行、不無窮攔）；問不到（斷線、非 200）照舊版號送，讓伺服器 `REGISTER_NEED` 那一句擋。條款改版後沒重新整理的註冊頁不再卡住。關著（版號 404）沒插勾選，照舊不攔。關著時同一頁只打一次 404（快取的是那一次請求），要連這一次都省得改殼，不做。

**另外要跑的**（`scripts/test_for.py` 照這一包挑不到；第 206 批）：`tests/core/test_terms_base.py`、`tianxia/features/identity/tests/test_identity_terms.py`、`tianxia/features/identity/tests/test_identity_web.py -k privacy`、`tests/server/test_server.py -k register`（`server.register` 多一個參數）、`tests/core/test_shell_stays_thin.py`（`NO_LOGIN_ROUTES` 那一列）、`tests/bots/test_server_bots.py`（`web/terms.js` 不准寫假人字樣）、`tests/core/test_feature_boundaries.py`。第 210 批：`tianxia/features/identity/tests/test_identity_web.py`（同一張登入頁的 js）。
