# 手機通知（`tianxia/features/notify/`）

玩家在設定頁自己打開的手機通知（減法季整合設計第十章「回來的理由」，批 9）：分頁關著、手機鎖著也跳得出來——來信、約戰、決戰集結、被截殺、被〈天下形勢〉提到五種事。送的是一句話，只給那個人自己的裝置。包名不叫 `push`：`tianxia/push.py` 是推力規則（共用規則層）。

- 導覽：`docs/guide/核心與存檔.md`（「手機通知」那一條）。
- 設計稿：減法季整合設計第十章；計畫 `docs/superpowers/plans/2026-11-06-手機通知包-第1批.md`（全部拆包第 53 批）。
- 開關：`Config.web_push.enabled`（`content/config.json` 打開；測試內容關著）加上主機裝了 `cryptography`（`server_push.AVAILABLE`）。關著 `WEB_PUSH` 是 `None`、設定頁不畫、`/api/push*` 回 404。
- 內容：沒有內容檔。訂閱記在資料庫旁邊的小檔 `<db>-push.sqlite`（`PushStore`），不動 `SCHEMA_VERSION`。VAPID 金鑰在 `.local/webpush_vapid.pem`（第一次開時產生，不進版控）。

## 補充說明（這一包的東西在哪）

- `notices.py`（原 `tianxia/notices.py`）：五種事，純函式，只讀存檔與決戰。送信日走 `ctx.mail_day_at`（人物情誼包的服務），不再經殼碰 `letters`（第二輪第 102 批）。
- **「客服」種類**（J 波第 211 批）：`Kind` 多 `"support"`，`notices.kinds(config)` 在客服包開著（`Config.support.enabled`）時才多這一種，關著等於 `KINDS`（`KINDS` 本身不動，關著時 `/api/push` 的回應不變）；`routes.py` 三處改叫 `kinds(shell.CONTENT.config)`，`web/notify.js` 的 `PUSH_KIND_NAMES` 多 `["support","客服"]`、只在伺服器的 kinds 有這個鍵才畫。推播的字在客服包的 `routes.py`（`PUSH_TEXT`，包不 import 別包），推是客服包經 `WEB_PUSH` 送的；玩家關掉「客服」的設定留在 push 小檔。
- `webpush.py`（原 `server_push.py` 下半段，連同 `cryptography` 的 try-import）：RFC 8291 加密、RFC 8292 VAPID 簽名、`PushStore`、`WebPush`。沒有 tianxia 的 import。`server_push.py` 檔尾把十四個名字原樣再匯出（`server.py`、測試、`same_behavior` 讀 `server_push.<名字>`）。
- `routes.py`：看守一輪 `notice_round`、`_notice_keys`、開看守 `start_web_push`、`web_push_line`，加上五條 `/api/push*` 與 `/sw.js`（路由搬、`web/sw.js` 檔留在 `web/` 原位）。
- 掛鉤只接 `routes`、`threads`。`threads` 叫殼的 `start_web_push`；`main()` 原本在 `print(web_push_line(...))` 下一行直接叫它，現在經 `start_threads`（晚幾行、在 `start_narration` 之後，都在 `uvicorn.run` 之前，沒有輸出、沒有順序依賴；退版：把那一行放回去、`threads` 改回 `None`）。`enabled` 回 `True`。
- 選項前綴：沒有。`choose`、`bot_policy.py`、`bot.py`、`bot_runner.py` 都沒有手機通知。假人沒有帳號，進不了訂閱名單。
- 核心要用的：`tianxia/core/services_list.md` 的 `# notify`：看守在行動鎖內叫 `game.morning_mail(now)`（主人人物情誼包，名字掛在那一包的 `game_api.py`；這一包自己沒有表）。
- SSE 那一半（`server_push.py` 的 `PushHub`、`watch_world`、`sse_stream`，`server.py` 的 `HUB`、`/api/events`）是殼，沒搬。

## 認領的欄位（手冊 3.5）

`player_fields = ()`、`carried = ()`：不是 `PlayerState` 欄位，訂閱存在旁邊的小檔。

## 還留在原位的接縫

- 殼 `server.py` 留 **state 的宣告**（測試與 `tests/conftest.py` 認這幾個名字，包一律 `shell.<名字>` 當下讀、當下寫，不快取）：`WEB_PUSH`、`NOTICE_STOP`、`NOTICE_THREAD`、`NOTICE_SENT`、`MAIL_DONE`、`VAPID_FILE`，與測試讀的字串 `NOTICE_TITLE`、`PUSH_WELCOME`、`PUSH_TEST`、`PUSH_NOT_HERE`。
- 殼留 **4 個一行薄包裝**：`start_web_push`、`notice_round`（預設參數 `clock=time.time` 寫在包裝上）、`_notice_keys`、`web_push_line`（`main()` 印、`same_behavior` 與測試從 `server.` 叫）。
- 手機通知的畫面（設定頁、`pushAskHtml`）在 `web/notify.js`（第 66 批）、`web/notify.css`（第 67 批）；`web/sw.js`、`manifest.webmanifest` 留 `web/` 原位、不進 `Feature.web`（`web_scripts` 會把 `.js` 排成 script）。

## 測試

整檔搬進 `tests/`：`test_web_push.py`（加密與簽名、五種事、09:00 來信、訂閱 API 與看守；原 `tianxia/features/notify/tests/test_web_push.py`，只改說明字；有一條 `@pytest.mark.smoke`）、`test_notify_package.py`（有登記、五條路由與 `/sw.js`、`main()` 經掛鉤開看守）。`pytest tianxia/features/notify/tests -n 4`。

**另外要跑的混合檔**（含手機通知的測試，但檔案不屬於這一包，不拆；`test_for` 改這一包挑不到）：

- `tests/server/test_server.py -k "main or users or push or fingerprint"`（`_users_in_server` 掃 `server.py` 與各包 `routes.py`、`test_main_starts…`；推送指紋那幾條第二輪第 102 批搬回來）
- `tianxia/features/companions/tests/test_relations_letters.py`（`Game.morning_mail`）

注意：`tests/server/test_push.py` 測的是推力規則（`tianxia/push.py`），不是這一包的（總表附錄丙把它歸手機通知是誤判）。

前後比對：`same_behavior` 的 `beacon` 一軌（三種設定、整段與半舊半新）；`companions`（叫 `server._notice_keys`）、`duel`（叫 `notices.current`）。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`main` 表 `web_push`（`frame.shell.WEB_PUSH` 是殼的 state）。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_push_how_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。
