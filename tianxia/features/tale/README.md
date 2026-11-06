# 戰記（`tianxia/features/tale/`）

決戰收場之後，說書人把那一場寫成一篇話本，全服一份（Joy 2026-10-29，原稱「戰役話本」）：戰報頁的「戰記 ›」、公開的分享頁 `/zhanji/<代碼>`（Joy 2026-11-04）都讀它。引擎給料、模型只寫字，模型叫不動就存引擎自己拼的那一版。全部拆包第 52 批搬進來（計畫 `docs/superpowers/plans/2026-11-06-戰記包-第1批.md`）。

- 導覽：`docs/guide/戰鬥.md`（「戰記」那一節）。
- 設計稿：沒有獨立的設計稿；計畫 `docs/superpowers/plans/2026-10-30-戰記-引擎-plan.md`，規則寫在導覽那一節。
- 開關：沒有（`start_tales` 一定開，叫不動模型就寫模板版）。江湖史的目錄看殼的 `TALES_IN_CHRONICLE`（等 Joy 定，先關著）。
- 內容：沒有內容檔。戰記存在資料庫旁邊的小檔 `<db>-tale.sqlite`（`TaleStore`），不動 `SCHEMA_VERSION`。

## 補充說明（這一包的東西在哪）

- `tale.py`（原 `tianxia/tale.py`，舊名留成 `sys.modules` 別名）：備料（`gather`）、請模型寫（`write`）、組成整篇（`compose`／`plain`）、存放（`TaleStore`）。不讀時鐘、不碰狀態。讀 `battle_instance` 五個名字（共用層，不算過渡）：`CENTER`、`BattleInstance`、`BattleRoundRecord`、`GambleMoment`、`claims_a_kill`；`claims_a_kill` 是規則，第 54 批拆 `battle_instance` 的時候這一行要接核心小模組或查詢服務，不能變成包對包。
- `tale_html.py`（原根目錄 `tale_html.py`，舊名留成別名）：戰記頁的標記，只 import 標準庫；樣子在 `web/tale.css`（`index.html` 不載入，只有戰記頁自己連）。
- `routes.py`：路由 `/api/tale/{battle_id}`、`/zhanji/{code}`，加上 `server.py` 原本的戰記那一段（`tale_view`、`tale_cover`、`tale_page_view`、`_tale_due`、`tale_index`、`tale_store_path`、`start_tales`、`tale_material`、`tale_round`）與決戰放手一搏補劇情（`_tales_waiting`、`narrate_battle`、`narrate_once`；它們不是戰記本體，是派工單一起點名的同一段）。第一個參數都是 `shell`（server 模組）。
- 掛鉤只接 `routes`、`threads`（全部拆包第 52 批開的，殼開、測試停；`threads` 叫殼的 `start_tales`）。`enabled` 回 `True`（同輿圖包，這一包沒有遊戲當下的掛鉤，沒有誰問它）。
- 選項前綴：沒有。`choose`、`bot_policy.py`、`bot.py`、`bot_runner.py` 都沒有戰記（`_tale_clue`、`outing_tale`、`Config.secrets.tale_*` 是同名別的事）。假人只會進名錄。沒有 `bots.py`、沒有 `<包名>_stage.py`。
- 核心要用的：`tianxia/core/services.py` 的 `# tale`。`routes.py` 叫 `game.battle_tale_request()`、`game.apply_battle_tales(...)`、`game._tale_battles()` 是決戰包的委派（查詢服務，主人決戰包）。

## 認領的欄位（手冊 3.5）

`player_fields = ()`、`carried = ()`：戰記不是 `PlayerState` 欄位，存在旁邊的小檔。

## 還留在原位的接縫

- 殼 `server.py` 留 **state 的宣告**（測試與 `tests/conftest.py` 認這幾個名字，包一律 `shell.<名字>` 當下讀、當下寫，不快取）：`TALES`、`TALES_CLIENT`、`TALES_STOP`、`TALES_THREAD`、`TALES_IN_CHRONICLE`、`TALE_COVER_DIR`、`TALE_LOCK`、`TALE_RUNNING`、`TALE_OWNER`、`TALE_THREADS`（`TALE_THREADS` 另外六處也看：潤色、書信、月旦、形勢、擂台場邊、酒肆閒談；`main()` 開它的那一行不動）。第 53 批照同一個形狀（包的 `threads` 叫殼的 `start_*`，STOP、THREAD 留殼）。
- 殼留 **8 個一行薄包裝**：`_tales_waiting`、`narrate_battle`、`narrate_once`、`tale_view`、`tale_cover`、`tale_index`、`start_tales`、`tale_round`。`act`、`look`、`main_view` 原位叫，先後算行為；`test_server`、`test_battle_tales`、`same_behavior` 從 `server.` 叫。`tale_round` 的預設參數 `clock=time.time` 寫在包裝上（`same_behavior` 先換 `time.time` 才 import server）。包裡互叫也經 `shell.<名字>`，測試換掉的看得到。
- `_tale_ref`（`server.py`，`reports_view` 旁邊，只讀 `battlelog`）沒搬：派工單沒點名。
- 戰記的畫面（`taleLink`／`taleHtml`／`taleIndexHtml`）在 `web/tale.js`（第 66 批從 `app.js` 切出來）；`tale.css` 只有戰記頁自己連，不進 `Feature.web`。`tests/web/test_tale_web.py` 用假的 `/api/tale`，留 `tests/web/`。

## 測試

整檔搬進 `tests/`：`test_tale.py`（寫法與存放；有一條 `@pytest.mark.smoke`，手冊 4.1 第三級每一包至少一條，`tests/core/test_test_for.py` 守）、`test_tale_page.py`（戰記頁的標記）、`test_tale_package.py`（有登記、兩條路由、殼啟動時經掛鉤開執行緒）。`pytest tianxia/features/tale/tests -n 4`。

**另外要跑的混合檔**（含戰記的測試，但檔案不屬於這一包，不拆；`test_for` 改這一包挑不到）：

- `tianxia/features/battle/tests/test_battle_tales.py`（放手一搏補劇情，換 `battle_instance.write_tales`）
- `tests/web/test_tale_web.py`（畫面；用假的 `/api/tale`，測不到路由，路由靠 `same_behavior` 的 `scribe` 與 `test_server`）
- `tests/server/test_server.py -k "tale or queue or scheduler"`（`_users_in_server("QUEUE")` 掃本包 `routes.py` 看 `narrate_once`、`tale_round`）

前後比對：`same_behavior` 的 `scribe` 一軌（三種設定、整段與半舊半新）。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`main` 表 `tales`（經 `frame.shell.tale_index`，殼的薄包裝）。
