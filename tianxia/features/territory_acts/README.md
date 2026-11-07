# 地盤的行動與畫面（`tianxia/features/territory_acts/`）

- 做什麼：領地爭奪（翻地與爭搶）裡「玩家碰到的行動與畫面」——下戰書與攻城時段、每天 22:00 換天（前一天沒開成的攻城作罷）、〈天下形勢〉每天一篇（三段式的 A、C 兩段）、翻地分紅與守城功送到、地盤畫面的資料（時程表、每一塊的翻地資料、能不能下戰書）、管理者五個救場工具。全部拆包第 46 批從 `Game` 搬來（27 個方法、431 行，加 `conquest_day.py` 240 行、`xingshi.py` 314 行兩個模組）。
- **包名叫 `territory_acts`，不叫 `territory`**：`tianxia/territory.py`（誰控制、駐軍、大本營）是共用規則層，這一批不搬，同名不准（第 23 批的教訓）。`tianxia/conquest.py`（進度、易手、分紅的規則）也在共用規則層。
- 導覽：`docs/guide/行動與地盤.md` 的地盤易手那一節、`docs/guide/大勢人物與賽季.md`（戰線推力與軍令）
- 設計稿：`docs/superpowers/specs/2026-10-20-輿圖簡化-design.md`（開頭寫「三版」，翻地與爭搶）、`docs/superpowers/specs/2026-10-20-領地爭奪-design.md`（沒有版本號；〈天下形勢〉是第三批 A）；搬家計畫 `docs/superpowers/plans/2026-11-06-地盤包-第1批.md`

## 檔案

| 檔 | 內容 |
|---|---|
| `__init__.py` | 登記：沒有前綴、沒有選項；`admin_tools`、`routes`、`check_content` 三個掛鉤；`enabled` 一直是 True（戰書看 `conquest.on`、〈天下形勢〉看 `xingshi.on`，各在動作裡驗） |
| `letter_actions.py` | 戰書：`letter_key`（今天是第幾天）、`letter_problem`、`conquest_letter`；`LETTER_*`、`CONQUEST_OFF`、`CONQUEST_ENDED` |
| `day_actions.py` | 22:00 換天與分紅補送：`conquest_tick`（換天的掛鉤）、`deliver_conquest`（分紅與守城功送到，結尾把最新一則紀錄的出陣回報接著畫同一塊） |
| `xingshi_actions.py` | 〈天下形勢〉：`start`、`open_ticket`、`finish`、`grace`（寬限到了照固定段收）、`waiting`、`release`、`request`（A 段）、`settle`（C 段）、`view`、`mark`、`admin_now` |
| `view.py` | 地盤畫面：`conquest_view`、`siege_you`、`region_name`、`siege_live`、`siege_join`、`siege_margin`、`admin_choices`（管理者頁的下拉選單）；`SIEGE_STATUS`、`siege_status_text` |
| `admin_actions.py` | 管理者救場：`conquest_set`、`conquest_progress`、`conquest_letter`、`conquest_cancel` |
| `routes.py` | `GET /api/xingshi`；`admin_tools`：`conquest_set`、`conquest_progress`、`admin_conquest_letter`、`conquest_cancel`、`xingshi_now` |
| `conquest_day.py`、`xingshi.py` | 規則模組（舊名 `tianxia/conquest_day.py`、`tianxia/xingshi.py` 留成指到同一個模組的別名）；`xingshi.check_lines` 驗 這一包的 `content/xingshi_lines.json` 的句型（原本在 `content.py`） |

`conquest_day` 的 `void`、`note_void`、`today`（連 `_rumor`）先搬進了共用規則層 `conquest`（`siege`、`orders` 就不必 import 包），`conquest_day` 裡留同名的 import。

## 認領的欄位

**沒有 `PlayerState` 欄位**（`player_fields = ()`、`carried = ()`）。全服的帳 `WorldState.conquest`（時程表、進度、分紅、`letter_days`、`day_log`、`settled_key`）、`xingshi`、`xingshi_ticket`、`xingshi_mark` 留在 `state.py`。

## 還留在原位的接縫（理由在 `tests/core/boundary_tables.py` 的 `# territory_acts` 那一組）

- **22:00 換天不接世界層**：世界層的 `day` 格是 21 天季的曆日，不是現實 22:00 的換天；換天與分紅在 `world_tick`、`sync`、`advance` 三處（五格，第 55 批換成 `SEAM_ORDER` 的 `tick`、`sync.deliver`、`advance.turn`）排在別的結算之間，順序就是行為（`_xingshi_grace` 在「季收了、日子沒往前」之前，`late` 的存季只在那一條路上存）。`Game` 上那兩個委派留給測試，`WORLD_ORDER` 不動。
- **〈天下形勢〉的 B 段與背景執行緒**（`write_xingshi`、`xingshi_once`、`XINGSHI_RUNNING`）：第 69 批進了 `routes.py`（同月旦評 `write_yuedan`，見最後一段），照舊用殼的佇列、預算、`TALE_THREADS`。
- `admin_choices` 的 `xingshi`、`conquest` 兩格第二輪第 90 批改走 `status_slots`（`admin` 表）（`/api/main` 的 `conquest`、`xingshi`、`xingshi_mark` 第 66 批改走 `status_slots`，`Game.xingshi_mark` 拿掉）。
- `MAIN_ACTIONS["conquest_letter"]`（玩家下戰書）第 68 批搬進 `routes.py` 的 `main_actions`。**管理者那一個叫 `admin_conquest_letter`，不叫 `conquest_letter`**：`api_do` 先查功能包的管理者工具，同名會把玩家的下戰書整個蓋掉（FB-609）。
- `Game._conquest_side`（陣營是哪一軍）、`_sieges`、`_joinable`、`_cancel_siege`、`_flavor_sink`：包經 `ctx` 叫（服務清單）。
- 沒有選項前綴：戰書走 `/api/do/conquest_letter`，不在選單上；假人不下戰書（`bot_policy` 只讀 `conquest` 規則）。

## 過渡（手冊 3.11）

過渡 import 共 1 處（包到舊模組，標了「# 過渡：待搬」；全部拆包第 40 批合完重印）：`view`→`atlas`。原本還有 `day_actions`→`annals`（第 29 批之二改 import 核心）、`letter_actions`→`ranks`、`view`→`ranks`（第 40 批 `ranks` 收進共用規則層，行尾註改寫成「共用規則層」），不算過渡。舊模組到包有 `engine.py` 的 GAME_IMPORTS 五行與 `conquest_day`、`xingshi` 兩個別名（理由在邊界測試的 `# territory_acts` 段）。
第 50 批合完重印 **0 處**：`view`→`atlas` 收進共用規則層（`atlas` 第 50 批進 `registry.SHARED`），行尾註改「共用規則層」。

## 測試

- 這一包的 `tests/`：`test_xingshi.py`（〈天下形勢〉，37 條，原 `tests/acts/`，整檔搬）、`test_marks_xingshi_once.py`（痕跡與〈天下形勢〉，6 條，原 `tests/core/`，整檔搬）、`test_territory_acts_smoke.py`（煙霧）、`territory_acts_stage.py`（契約測試擺局面）。
- 整檔搬時改的只有 `tianxia/features/territory_acts/tests/test_xingshi.py` 的兩處斷言字串（路由搬進包之後 `include_router` 掛的不在 `server.app.routes` 上，改查 `app.openapi()["paths"]`；管理者工具不在 `server.ADMIN_ACTIONS`，改查 `server.FEATURE_ADMIN_ACTIONS`）。
- 留在原處的混合檔（`test_conquest_rules.py`、`test_conquest_siege.py`）也因為管理者五個工具搬進 `admin_tools`，把 `server.ADMIN_ACTIONS[op](game, …)` 改成 `server.FEATURE_ADMIN_ACTIONS[op].run(game, …)`，`SIEGE_STATUS` 改從 `view` import。
- 調查點名的 `test_xingshi_fb610_order.py`、`test_xingshi_fb646_mend.py`、`test_fb883_admin_letter_ids.py` 現行程式裡沒有這三個檔（已併進 `test_xingshi.py` 或 `test_conquest_siege.py`）。

## 另外要跑的混合檔

- `tests/acts/test_conquest_rules.py`（領地爭奪規則＋戰書換天救場）、`tests/acts/test_conquest_siege.py`（攻城戰本身在決戰包，戰書、換天、救場在這一包）、`tests/acts/test_conquest_flip.py`
- `tests/core/test_marks_visible.py`、`tianxia/features/map/tests/test_world_map.py`、`tianxia/features/seal/tests/test_seal_acts3.py`、`tests/kit/conquest_kit.py`（共用建局）
- 別包的：`tianxia/features/battle/tests/test_siege_cancel.py`（叫 `admin_conquest_cancel`）、`tianxia/features/sortie/tests/test_sortie_report.py`（叫 `_deliver_conquest`）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/territory_acts/day_actions.py`

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `conquest`（`day_actions.conquest_tick(ctx, True)`，回傳不接）、`conquest.deliver`；`advance.turn` 的 `conquest`（`conquest_tick(ctx, False)`，回話接進 `msgs`）、`conquest.deliver`；`tick` 的 `conquest`（`conquest_tick(ctx, True)`，回話接進 `msgs`）。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（「地盤」那一節（碎片的來源那一句問玉璽包，插句 `land_seal`）），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

## 畫面與狀態列（全部拆包第 66 批）

- 畫面：`web/territory_acts.js`（見聞的〈天下形勢〉）、`web/territory_acts.css`（第 67 批）。
- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`main` 表 `conquest`、`xingshi`（`xingshi`、`xingshi_mark`）。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`conquest_letter`（玩家下戰書；管理者的 `admin_conquest_letter` 第 46 批就在 `admin_tools`，不同名）。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：`routes.py` 的〈天下形勢〉`_xingshi_waiting`、`write_xingshi`、`xingshi_once`、`XINGSHI_RUNNING`、`XINGSHI_OWNER`、`XINGSHI_SKIPPED`（`outlock` 掛鉤那一格 `xingshi`；殼留一行包裝 `_xingshi_waiting`、`xingshi_once`）。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tests/server/test_outlock.py`。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_conquest_bots.py`（原 `tests/acts/`）、`test_conquest_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。
