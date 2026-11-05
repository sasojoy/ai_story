# 軍情（`tianxia/features/military/`）

- 做什麼：軍令卡（江湖頁「本週軍令」）與押糧（接下糧車、走到終點交軍令）、第 2 階行動、第 3／4 階行動（黃巾煽動起事、豪強修築塢堡與趁亂占據郡縣）、第 4 階席次的抄帳、
  管理者重發軍令／輪替席次／替人發召見。全部拆包第 33 批從 `Game` 搬來（17 個方法）；包名不叫 `orders`：`tianxia/orders.py`（軍令的規則）留在原位。
- 導覽：`docs/guide/大勢人物與賽季.md` 的軍令與晉升那幾節
- 設計稿：`docs/superpowers/specs/2026-10-04-第一季陣營內容-軍令.md`、第一季正式版計畫戊（第 3、4 階行動）、丁（第 4 階席次）

## 檔案

| 檔 | 內容 |
|---|---|
| `__init__.py` | 登記：沒有前綴，只認領三個欄位（行動列的 `act:` 前綴是核心的）；掛鉤只有叛投那一刻的格 `defection()`（`clear` 位置的 `convoy`，第 32 批） |
| `order_actions.py` | 軍令卡與記功 4 個：`order_options`（守勢與接糧車的選單）、`order_credit`（替自己記一次軍令）、`convoy_line`、`orders_view`（江湖頁「本週軍令」卡） |
| `convoy_actions.py` | 押糧 2 個：`take_convoy`、`convoy_arrives`（走到終點：可能撞上截糧隊、記捐獻與貢獻、軍令記功）；叛投 `clear` 位置的 `convoy` 那一格 `defect_clear`（第 32 批） |
| `step_actions.py` | 第 2 階與第 3、4 階行動 6 個：`rank2_options`、`check_cost_note`、`rank2`、`rank_action_options`、`rank_action_line`、`rank_action` |
| `seat_actions.py` | 第四階席次抄帳：`report_seat`（賽季時鐘暫停中什麼都不做） |
| `admin_actions.py` | 管理者的軍令與召見：`issue_orders`、`rotate_seats`、`summons_plan`、`summon`，與回話用的五個常數 |
| `rank_rules.py` | 第 3、4 階行動的規則（原 `tianxia/rank_actions.py`，舊名留成指到同一個模組的別名） |

`Game` 留 15 個一行委派：`_order_options`、`_rank2_options`、`_rank_action_options`、`_rank2`、`_rank_action`、`_take_convoy`、`_convoy_arrives`、`_order_credit`、
`_report_seat`、`_summons_plan`、`orders_view`、`convoy_line`、`admin_issue_orders`、`admin_rotate_seats`、`admin_summon`；`_check_cost_note`、`_rank_action_line` 只有包裡自己叫，沒有委派。

## 認領的欄位（`PlayerState`，換季全部跟著新角色重來，沒有帶走的）

`convoy`（押著的糧車；這一包寫，叛投那一刻也由這一包清成 None）、`rank2_days`（第 2 階行動今天做了幾次）、`rank_action_weeks`（第 3、4 階行動這週做了幾次；`rank_rules.count` 寫）。
`donations`（押糧與捐糧效果都寫）、`summons`、`qualified`、`rank`、`contrib_weeks`、`rank_hinted` 是共用或階級、席次規則層的，不認領。

## 還留在核心原位的接縫（理由在 `tests/core/test_feature_boundaries.py` 的 `# military` 那一段）

- `act:rank2`、`act:convoy`、`act:rank:<行動>`：核心 `_act` 的 act 子動詞（總表第 57 批才擴 `Verb`），選單三段（`_everyday_options`，順序算行為）和按下去（`_act`）留在核心原位叫 Game 的委派。
- `act:summons`（人已在召見地點時按的應召）、`_summons_hop`（往召見地點）、`bot_policy.score` 的 `rank2`、`convoy`、`summons` 分數、`_summons_hop`：假人行動列的分數，留原位。
- `_report_seat`：`sync`、`choose`、`travel` 與事件檢定的兩處（`answer_event`、`answer_branch`）叫，位置固定（回話與紀錄的先後算行為），沒有掛鉤可接。
- `_convoy_arrives`：`_arrive` 走到地點那一刻先交糧車、再接懸賞榜護送交差。`_order_credit`：核心的單打服務（`_squad_encounter`）打贏之後記功；出陣、決戰、大勢人物也經 `ctx._order_credit` 叫。
- `server.py` 的 `orders`、`convoy` 兩個鍵（`/api/main`）與管理者三顆鈕（`/api/do` 的路由留原位，批次表第二節；`ADMIN_ACTIONS` 只是查表用的 dict，照包分是第 68 批）照舊叫 Game 的委派。
- `orders.py`（軍令規則）、`ranks.py`、`seats.py`、`opportunities.py`、`foreshadow.py` 不在這一包（共用規則層，總表第 40 批；機緣、伏筆第 34 批）。

## 過渡（手冊 3.11）

過渡 import 共 8 處（`test_feature_boundaries.py` 數）：`admin_actions`→`orders`、`ranks`；`convoy_actions`→`orders`；`order_actions`→`atlas`、`orders`；`rank_rules`→`ranks`；`step_actions`→`events`、`opportunities`。
`orders`、`ranks` 是共用規則層（第 40 批收進 `SHARED`），`atlas`、`events`、`opportunities` 等後面的批。
服務清單（`tianxia/core/services.py`）這一包加的：`_order_credit`（共用服務，出陣、決戰、大勢人物也經 `ctx` 叫）、`RANK_ACTION_PREFIX`、`_duty_option`（出陣包的委派，`order_options` 叫它）。
叛投那一刻經核心的叛投掛鉤（`core/features.py` 的 `DEFECT_ORDER`）`clear` 位置的 `convoy` 那一格清（`convoy_actions.defect_clear`：`p.convoy = None`，押著的糧車留給舊陣營；全部拆包第 32 批，原本 `defection.clear_progress` 直接寫）。軍令記下的貢獻（`contrib`、`contrib_weeks`）照舊由叛投自己的 `progress` 那一格清。

## 內容歸屬

`content/promotions.json`、`content/events/promotion.json`（第 2 階晉升奇遇）歸這一包，`__init__.py` 的 `content` 宣告；`opportunities.json`、`foreshadows.json` 是第 34 批的。

## 測試

- 這一包的 `tests/`：`test_rank_actions.py`（第 3、4 階行動：內容表、選單、做一次、做滿、推滿，67 個函式，原 `tests/core/`，整檔搬）、
  `test_military_smoke.py`（煙霧一條：黃巾第 3 階煽動起事）。沒有 `military_stage.py`：這一包沒有掛鉤給選項，契約測試擺「平常」就夠（`STAGE_PACKAGES` 只列有擺局面檔的包）。
- `test_admin_triggers.py`（31 個函式）**留在 `tests/figures/`**：14 個是管理者的軍令、席次、召見（這一包），其餘是開戰、機緣、碎片，混合檔不拆。

## 另外要跑的混合檔

混著別的功能、留在原處的（`條數＝碰到這一包的／全檔`，用語法樹數過，函式為單位，數字是粗的）；改這一包時連它們一起跑：

- 軍令卡、記功、押糧、席次抄帳：`tests/figures/test_orders.py`（20／85，`orders_view`、`_order_credit`、糧車）、`tests/figures/test_seats.py`（`_report_seat`）、
  `tests/figures/test_defection.py`（2／41）、`tests/figures/test_gentry_allied.py`（`_summons_plan`）、`tests/ranger/test_season21_daily.py`（2／29）、`tests/figures/test_week7_season.py`
- 第 2 階行動與召見：`tests/figures/test_opportunities.py`（18／93，`act:rank2`、`_rank2`）、`tests/figures/test_admin_triggers.py`（14／31）
- 引導與網頁：`tianxia/features/guide/tests/test_opening.py`（2／9，`orders_view`）、`tests/map/test_weekcard.py`、`tests/core/test_prologue.py`（2／101）、`tests/web/test_prologue_web.py`（3／81）、`tests/web/test_jianghu_page_web.py`（1／134）
- 別包叫進來的：`tianxia/features/sortie/tests/test_sortie.py`（出陣不花出陣次數）、`tests/server/test_server.py`（2／385）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/military/order_actions.py`
