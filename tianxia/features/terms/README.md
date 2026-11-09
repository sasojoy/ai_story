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
| `tests/` | `test_terms.py`（規則、小檔、API）、煙霧 |

**給註冊那一邊**（設計稿「請註冊那邊接的一個勾選」）：註冊表單兩個勾選（滿 18 歲或法定代理人同意、同意兩份條款），表單帶 `terms_version`（`/api/terms` 沒登入是 401，版本號在 `rules.load()["version"]`），帳號建好之後叫 `routes.record_consent(shell, key, version)`；版本不是現行版丟 `ValueError(STALE)`。還沒接之前，登入後的同意層會補問，不會漏。

**網頁**：`web/terms.js` 不改 `app.js`，用 MutationObserver 看 `#app`：登入頁（`.gate`）與設定頁（`.sheet[aria-label="設定"]`）底下補連結；進了遊戲問一次 `/api/terms`。網頁測試的 node 沒有 DOM，整段跳過。
