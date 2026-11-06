# 簽到（`tianxia/features/checkin/`）

21 天季每天簽一次（第 N 天照開季那一天起算，那天沒上線就錯過）：丹的日子給回體丹，第 6、13、20 天給一個自己挑屬性（剛柔快慢）的四階料（第 6 天連丹兩樣都給），其餘的日子照先後輪流 30 兩銀子與一個一階素材；找素材、練功另有機會掉一顆回體丹。每天第一次同步時今天不必挑的份自動領（江湖頁沒有簽到鈕，只有一張小標；要挑四階的日子冒一張挑屬性的小卡）。全部拆包第 30 批搬進來（計畫 `docs/superpowers/plans/2026-11-04-一條線簽到-第30批.md`，和一條線小包併批）。

- 導覽：`docs/guide/大勢人物與賽季.md` 的「簽到（功能包 `tianxia/features/checkin/`）」那一節。
- 設計稿：`docs/superpowers/specs/2026-10-17-正式季整合-design.md` 6.2～6.4（每日簽到與回體丹）、8.1（假人）；減法季批 1（Joy 2026-10-24 挑江湖頁乙案：簽到不放鈕）。都沒有版本號。數字在 `Config.checkin`（只有 season21 設定打開，另照開季的章）。

## 裡面有什麼

- `checkin.py`（原 `tianxia/checkin.py`，舊名留成 `sys.modules` 別名，同一個模組物件）：第幾天、給什麼、能不能領、領了改背包與銀兩、畫面要的資料、假人挑哪一種（`bot_attribute`）。`on`、`PILL_FOUND` 是**核心** `tianxia/core/services.py` 的 `checkin_on`、`PILL_FOUND`（回體丹那一套歸核心，總表附錄甲：`Game._pill_find` 掉回體丹也問「簽到開著沒」），這裡 re-export（`checkin.on is services.checkin_on`）。
- `actions.py`：原本 `Game` 上的 3 個方法（`check_in`、`auto_checkin`、`checkin_view`；`Game` 留 3 個一行委派，`check_in` 的裝飾器 `@_not_while_preparing` 留在委派上）。序章（草廬）裡不簽，開局第一分鐘〔城門口三選一還沒選〕回引導包那一句（經 `ctx._opening_pending()`、`ctx._opening_gate()`，服務清單二、查詢服務 `# checkin`）。
- 掛鉤：`enabled` 回 `checkin_on`（沒有任何掛鉤吃這個開關，委派自己各問 `checkin.on`）；`prefix = None`（沒有選項 id）。**沒有 `APIRouter`、沒有 `bots.py`**：`/api/do/checkin` 在 `routes.py` 的 `main_actions`（第 68 批）；假人叫的是 `Game.checkin_view`／`check_in`（`bot.check_in`、`bot_policy.take_turn`），不是選項。

## 認領的欄位（手冊 3.5：留在原地）

- `player_fields`：`checkin_days`（這一季簽過的是第幾天）、`checkin_picks`（四階的日子挑到哪一樣：第幾天 → 素材 id）；`carried` 空的，換季全部跟著新角色重來。（契約測試的換季那一條：新季第一次同步會自動簽第 1 天，所以那條測試擺局面時先關掉簽到，斷言不動。）
- 內容：沒有自己的檔（簽到的數字在 `content/config.json` 的 `checkin`）。

## 委派與留在原位的接縫

核心原位碰簽到的兩處沒有第 11 批掛鉤可接，改叫 `Game` 上一行的委派，記進邊界測試 `GAME_DELEGATE_CALLERS` 的 `# checkin` 那一段，**沒有新增 `GAME_DIRECT`**：

- `sync.deliver` 的 `checkin` 那一格（第 55 批）：在補送裝備（`held_gear`）之後；`on_sync` 掛鉤在它前面，江湖紀錄的先後算行為。
- 狀態列的 `checkin` 那一格（`status_slots`，第 66 批；位置在 `STATUS_ORDER`：`howto_entry` 之後、`fronts` 之前）；`feature_status` 是 `main` 的頂層。
- `Game._pill_find`：直接叫核心的 `checkin_on`、`PILL_FOUND`。

## 過渡（手冊 3.11）

- 包 → 還沒搬的舊模組：**沒有**（`checkin.py` 只 import 核心與共用規則層 `four_tiers`、`materials`、`prologue`）。
- 舊模組 → 包：`engine` 1 行（`checkin_actions`）、別名檔 `tianxia/checkin.py`；還沒搬的 `bot`（`bot_attribute`）與測試、腳本。
- 服務清單（`tianxia/core/services.py`）這一包加的：一、共用 `PILL_FOUND`、`checkin_on`；二、查詢 `# checkin` 一段（`_opening_pending`、`_opening_gate`：這一包問引導包）。

## 測試

`tests/` 底下：`test_checkin.py`（24 條：表、領、斷簽、序章與開局第一分鐘、回體丹掉落、假人，從 `tests/figures/` 整檔搬來）、煙霧 `test_checkin_smoke.py`（正式內容 season21：第 1 天自動領、同一天被擋、第 6 天等挑）與契約測試擺局面用的 `checkin_stage.py`。全部不含 slow，共 25 條。

網頁測試：`test_checkin_web.py`（江湖頁的簽到小標；整檔跑 node，沒有 node 就略過）第 61 批搬進這一包的 `tests/`，`test_for` 挑得到。

```
python scripts/test_for.py --base HEAD tianxia/features/checkin/actions.py
```

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `checkin`（`actions.auto_checkin`；`Game._auto_checkin` 留給測試）。

## 畫面與狀態列（全部拆包第 66 批）

- 狀態列與江湖畫面的格 `status_slots()`（順序在核心的 `STATUS_ORDER`；不問 `enabled`）：`status` 表 `checkin`（None 沒有鍵）。
- 畫面：`web/checkin.js`（`checkinPeek`、`checkinPickHtml`）、`web/checkin.css`（全部拆包第 67 批從 `main.js`、`style.css` 切出來，一個字不改）；`web/main.js` 的本週卡叫它們。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `main_actions`：`checkin`。 `checkin` 的 `Game` 的委派上掛著 `@_not_while_preparing`、包裡的函式沒有，所以表上那一條包 `not_while_preparing(lambda g, b: …)`（同一支裝飾器），籌備中的擋法不丟。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

## 第 61 批搬進來的測試（混合測試檔歸位）

整檔搬進 `tests/`（只搬位置、不改斷言；模組層標 `whole_content`，內容照舊是整份）：`test_checkin_web.py`（原 `tests/web/`）。

這些檔改這一包時 `test_for` 挑得到（整檔 slow 的要加 `--slow` 或直接給檔名）；上面寫「另外要跑」而路徑在這一包 `tests/` 底下的不用另外跑。上面寫 `tests/core/test_engine.py`、`tests/server/test_server.py`、`tests/web/test_jianghu_page_web.py` 找不到的那一條，條名不變，搬到各包的 `test_<包>_facade.py`、`test_<包>_shell.py`、`test_<包>_page_web.py` 了。
