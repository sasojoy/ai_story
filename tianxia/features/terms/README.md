# 條款 `tianxia/features/terms/`

- **做什麼**：使用條款與隱私權條款兩頁（`/terms`、`/privacy`，不用登入、開關關著也看得到）；登入後沒同意過現行版的帳號疊一層請他按同意；條款大改（換 `version`）之後，同意過舊版的人在考慮期內看到改版頁（可以稍後再看、過了視為接受；使用條款第九條）；`update_must` 開著（第 243 批的開關，第 246 批起預設關）才是按過新版的同意才關得掉那一層。登入頁與設定頁底下各兩個連結。
- **導覽**：`docs/guide/核心與存檔.md` 的「條款」一節。
- **設計稿**：https://claude.ai/artifact/BxXB4qnXvtDfCKUjmwuDj4（使用條款與隱私權 設計稿 v2，Joy 2026-11-07 給公司名義）。帳號註冊與綁定、客服系統 11/7 起交給另一位。條款 2026-11-v2（第 241 批，企劃者 11/20「現在就出新版條款」）第十條改字，寫明客服管道是遊戲內「設定」裡的「客服」頁；真人客服 AA 波（11/20）在 week7、season21 打開。第 244 批（企劃者 11/21「這一版一起補」）隱私權條款第二條把「客服往來內容」寫成客服單存什麼（類別、內容與往來、處理註記、截圖照原檔保存、送單時的帳號、名號、帳號建立時間與遊戲版本）、第三條加一段客服人員看得到哪些帳號資料（照 `features/support/lookup.py` 的帳號卡）與查帳號留紀錄，還在 `2026-11-v2`、版號不換。第 250 批（企劃者 11/22「要，上線時一起開橋」）第三條再加一段（插在 AI 那一句前面）：客服單轉送內部 Discord 客服頻道的內容（單號、類別、名號、遊戲版本、送單時間、內文與再回〔一則約 1,900 字截斷〕、找真人的通知、截圖原檔）、不送的（帳號、Email、手機、客服的回覆與註記）、只有指定客服看得到、Discord Inc. 境外、保存期限同客服單（照 `scripts/support_bridge.py` 實際送的寫）；還在 `2026-11-v2`、版號不換。`docs.privacy.updated` 跟 `published` 同一天，Joy 部署當天一起改。條文都是草案，上線前請企劃者與 Joy 找法律專業看過。
- **開關**：`Config.terms.enabled`（預設關）、`grace_days`（15，使用條款第九條、定型化契約應記載事項十七；`update_must` 關著〔預設〕才用）、`update_must`（預設關；第 243 批開的開關：開著時換版號之後同意過舊版的人要按過同意才能進。企劃者 2026-11-21 凌晨選過「改成強制按同意」、下午改選「這次用 15 天考慮期」，第 246 批把預設改回關；強制留給以後大改的版，先問法律專業）。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`TermsFeature`）：沒有選項前綴、沒有 PlayerState 欄位；`routes`、`check_content`；`web`＝`terms.js`、`terms.css`；`content`＝`terms.json` |
| `content/terms.json` | 條款全文、公司名義、版本（`version`、`published`）、同意頁的重點（`change_summary`，`web/terms.js` 全列）。**大改**換 `version` 與 `published`；**小改**只改字與 `updated`。大改時 `published` 填上線那一天：它是頁上印的生效日，也是考慮期的起點（`update_must` 關著〔預設〕：臺灣 0 點加 `grace_days` 天；填早了期限縮短，上線比它晚超過 `grace_days` 天就沒有人會被問）；`update_must` 開著時期限用不到它 |
| `rules.py` | 純規則：讀內容檔（改了就重讀）、`need`（`must`／`ask`／空字串；第五個參數 `update_must` 預設 False＝考慮期，只有 `routes.status` 明傳設定：開著時同意過別版的也回 `must`，`status` 這時多帶 `update: true`）、`check` |
| `store.py` | 同意紀錄的小檔 `<db>-terms.sqlite`（只加不刪；同手機通知的 `<db>-push.sqlite`，不進遊戲資料庫、資料庫不升版） |
| `pages.py` | 兩頁的 HTML |
| `routes.py` | `/terms`、`/privacy`、`/api/terms`、`/api/terms/agree`；`record_consent(shell, account_key, version, source="register")` 給註冊那一邊叫 |
| `tests/` | `test_terms.py`（規則、小檔、API）、`test_terms_register.py`（第 206 批：殼的註冊兩個勾選、記 `register`、`/api/terms/version`）、`test_terms_web.py`（第 206 批：`terms.js` 插勾選與擋送出，node 假 DOM）、煙霧；same_behavior 兩軌 charter（`scripts/sb/tracks/charter.py`）、amend（第 243 批開、第 246 批改：同意過舊版的人預設讀到 `ask`＋期限、考慮期內按同意記 `update`，最後打開 `update_must` 那一下讀到 `must`＋`update`；`scripts/sb/tracks/amend.py`） |

**給註冊那一邊（第 206 批接好了）**：註冊有兩條路——殼的 `/api/register`（`server.register`）與 identity 包建角色那一步（`/api/identity/character`，第三方、驗證碼第一次進來才開帳號）。包不准互相 import，所以經核心接縫 `tianxia/core/terms_base.py`：`router(shell)` 開頭 `terms_base.set_hook(_Hook(shell))`（`version()` 讀 `rules.load()["version"]`、`record` 叫 `record_consent`）。開新帳號之前 `terms_base.register_problem(CONTENT, body)`：開著時 `age_ok`、`terms_agree` 都要勾（認 `true`、`"on"`）、`terms_version` 要等於現行版，不然回同一句 `REGISTER_NEED`（不透露版本、不透露帳號在不在），殼與 identity 自己丟 `GameError`；被擋下的不算一次註冊。帳號建好之後 `terms_base.record(CONTENT, key, 表單帶的版號)` 記一筆 `source=register`（記玩家勾過的那一版；剛好改版丟的 `ValueError(STALE)` 吞掉，登入後同意層補問）。所以註冊時勾過的人進遊戲 `/api/terms` 的 `need` 是空字串、不跳層。關著（或包沒掛）兩個函式直接 return，註冊與建角色跟沒有這一包一樣。
- `GET /api/terms/version`（第 206 批）：不用登入（`NO_LOGIN_ROUTES` 寫了理由：還沒有帳號的人要拿得到）、第一行 gate、關著 404，只回 `{version}`。

**網頁**：`web/terms.js` 不改 `app.js`，用 MutationObserver 看 `#app`：登入頁（`.gate`）與設定頁（`.sheet[aria-label="設定"]`）底下補連結；進了遊戲問一次 `/api/terms`。網頁測試的 node 沒有 DOM，整段跳過。
第 206 批：同一個 MutationObserver 裡 `termsInsertChecks`——註冊模式的 `#gate-form`（有 `name="again"` 那一格才算註冊）與 identity 建角色那一張 `#idp-create-form` 的 `.form-msg` 前面插兩個勾選與 hidden `terms_version`（畫法集中在 `termsChecksHtml`，樣式 `terms.css` 的 `.terms-check`）；登入模式與殼自己的 `#create-form`（帳號已經開了）不插。版號第一次要用才問 `/api/terms/version`，非 200（關著 404）這一頁不再問、不插；斷線下一次再問。`document` 上 capture 的 submit（先於 `app.js` 的 submit 鏈）：表單裡有勾選而沒全勾就擋下、表單下面寫 `TERMS_SAY.need`。送出照殼與 identity 原本的整張表單序列化，三欄自然帶上。
第 210 批：兩格都勾了的那一次送出先攔下（`termsResend`）、不經快取重問 `/api/terms/version`（問到的寫回快取）、換掉 hidden `terms_version`，再 `form.requestSubmit()` 送一次（`termsFresh` 記著，那一次放行、不無窮攔）；問不到（斷線、非 200）照舊版號送，讓伺服器 `REGISTER_NEED` 那一句擋。條款改版後沒重新整理的註冊頁不再卡住。關著（版號 404）沒插勾選，照舊不攔。關著時同一頁只打一次 404（快取的是那一次請求），要連這一次都省得改殼，不做。

**2026-11-v2 上線時會怎樣**（第 241 批寫、第 243 批改、第 246 批改回；照 `rules.need`，`Config.terms.update_must` 預設關＝**15 天考慮期**，企劃者 2026-11-21 下午「這次用 15 天考慮期」，跟使用條款第九條一致）：`published` 是頁上印的生效日，也是期限的起點（先填預定日 2026-11-21，**Joy 部署當天一定要改成真的上線那一天**，`docs.terms.updated`、`docs.privacy.updated` 一起改；內容檔照修改時間重讀，改了不用重開伺服器）。
- 同意過 v1 的人：`need` 是 `ask`、帶 `deadline`（`published` 臺灣 0 點加 `grace_days`〔15〕天）、不帶 `update`。期限以前每次登入進遊戲跳一次改版頁：開頭寫「…{deadline} 以前沒有表示反對，就視為接受新版」（`TERMS_SAY.ask`）加 `change_summary` 的重點，三顆鈕：同意、稍後再看、我不同意（我不同意寫 `noAsk` 那一句：寫信終止並退費，不出登出鈕）。按同意記 `source=update`（`termsSource`），之後 `need` 回空字串；按稍後再看只關掉這一次，下次登入再跳。過了期限 `need` 回空字串、視為接受，旁檔不寫紀錄。
- 從沒同意過任何一版的人：照舊 `must`、不帶 `update`、那一層一個字不變，按同意記 `gate`。
- 擋法只是網頁上蓋一層：伺服器沒有路由看同意紀錄（新玩家第一次也一樣），不加伺服器端的擋法。
- 強制是開關：設定覆寫檔（`content/profiles/season21.json` 或 `week7.json`）的 `terms` 寫成 `{"enabled": true, "update_must": true}`、兩個程式重開生效。開著時同意過 v1 的人 `need` 是 `must`、回應多帶 `update: true`（`deadline` 是 `None`）：開頭換成改版那一句（`TERMS_SAY.update`），兩顆鈕：同意、我不同意（沒有「稍後再看」；我不同意照 `must` 寫那一句、出登出鈕），按同意記 `source=update`。這是給以後大改的版用的，開之前先問法律專業（第九條寫的是 15 天內沒反對視為接受）。換回第 243 批以前的程式跟預設一樣是考慮期，已記的 v2 同意紀錄留著。
- 註冊頁的勾選帶的版號是現問的（`/api/terms/version`，第 210 批送出前不經快取再問），改版前打開的註冊頁不會卡住。

**條文有承諾、程式還沒做的**（第 244 批）：隱私權第二條客服單「結案後 1 年」——support 包現在不刪單、不刪截圖夾（`<db stem>-support-files/`）、不刪查帳紀錄（`lookups`），每日備份（`scripts/backup_db.py`）照輪替整夾複製；最早的客服單 2026-11-20 起，2027-11 以前要有到期刪除的批（含還原舊備份後再掃一次）。客服的橋（`scripts/support_bridge.py`，貼 Discord）第 250 批已經寫進 `2026-11-v2` 第三條，v2 上線之前不要開橋；到期刪除因此多管一樣——轉貼到 Discord 的舊訊息（橋不記 Discord 訊息 id、刪不了，現在只能人工清頻道；要程式刪得另開一批改成 `wait=true` 記 id）。之後開客服官（外部模型讀單）仍要再改第三條（「不送到外部 AI 服務」那一句）並換 `version`。

**另外要跑的**（`scripts/test_for.py` 照這一包挑不到；第 206 批）：`tests/core/test_terms_base.py`、`tianxia/features/identity/tests/test_identity_terms.py`、`tianxia/features/identity/tests/test_identity_web.py -k privacy`、`tests/server/test_server.py -k register`（`server.register` 多一個參數）、`tests/core/test_shell_stays_thin.py`（`NO_LOGIN_ROUTES` 那一列）、`tests/bots/test_server_bots.py`（`web/terms.js` 不准寫假人字樣）、`tests/core/test_feature_boundaries.py`。第 210 批：`tianxia/features/identity/tests/test_identity_web.py`（同一張登入頁的 js）。
