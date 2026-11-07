# 商城（萬寶閣）`tianxia/features/mall/`

- **做什麼**：元寶的賣與記帳——商品上架與購買、發貨、月卡（每日領）、易名帖、封測發放、管理者的補發扣回退款與查帳；錢包（`tianxia/wallet.py`）與票的庫存、消耗（`ctx.wallet`）是核心的服務，別的功能用票叫核心、不叫這一包。
- **導覽**：`docs/guide/商城.md`（模組、規則速查、畫面、資料庫第 6 版、部署與對帳、販賣清單、列傳為終點的四件）；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：`docs/superpowers/specs/2026-10-20-商城架構-design.md` 第 1 版（手冊之前的稿，文內沒有版本號；企劃者 2026-10-20 核准）；第 1 階搬包照 `docs/superpowers/specs/2026-10-30-開發模式-design.md` 3.10。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`MallFeature`）：`enabled`＝`Config.mall.enabled`、`status`（江湖畫面的 `mall`）、`admin_tools`、`routes`、`check_content`、`on_own_turn`（封測發放，全部拆包第 11 批的接縫掛鉤）；`web`＝`mall.js`、`mall.css`（在 `web/`，第 3 階才搬進包；形象段沒寫字級的規則第 104 批搬到 `web/looks.css`，字級與電腦寬留 `mall.css`）、`content`＝`mall.json`（在 `content/`） |
| `rules.py` | 純規則（原 `tianxia/mall.py`） |
| `rename.py` | 易名帖換名號的規矩（`clash`；`swap` 在核心 `tianxia/core/swap.py`） |
| `actions.py` | 原本 `Game` 上的 `mall_*`、`admin_mall_*`（全部拆包第 58 批委派全拿掉，路由與測試直接叫這裡）；`purchase` 回 `Receipt`（`lines`、`bought`、`already`，路由從回傳值拿），`buy` 只要句子 |
| `routes.py` | `/api/mall`、`/api/mall/records`、`/api/mall/buy`、`/api/mall/claim`、`/api/mall/rename`、`/api/admin/mall`；`/api/do/mall_reissue|revoke|refund` |
| `tests/` | 原 `tests/mall/`（`test_wallet.py` 測核心的錢包，搬到 `tests/core/`）與 `tianxia/features/mall/tests/test_mall_web.py` |

**認領的欄位**（3.5，留在原地）：`PlayerState.holding_bonus`（只這一季）、`create_rerolls`、`legend_items`（換季帶著走，核心的換季照抄）。原本寄放在 `Game` 上的 `mall_bought`、`mall_already` 第 58 批收回包（`actions.Receipt`）。資料庫第 6 版的三張表 `mall_purchases`、`mall_ledger`、`mall_entitlements`（`database.py`，核心）。
**import**：包只 import 核心、共用層、自己這一包（第二輪第 102 批硬規矩，手冊 3.11，寫註也放行不了），沒有過渡 import。保留的名號在核心 `core/name_base.py`，插畫票用不上不賣的 `art_problem`、`ART` 在核心服務 `core/services.py`，`rules.py` 讀共用層 `library`（功法庫上限）。`scripts/mall_ledger.py` import 這一包。封測發放原本是 `own_turn_checks` 叫 `Game._mall_grant`，全部拆包第 11 批（核心收接縫）換成 `on_own_turn` 接縫掛鉤（`own_turn_checks` 最前面、暫停的檢查之前，不問 `enabled`），委派拿掉。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`season.carry` 的 `mall`（破境丹、重悟帖照帶，不看開關）。

**另外要跑的**（`test_for` 挑不到；改這幾處開發與修正另跑，`-n 4`，不含 slow）：

- 改 `core/name_base.py`：`tianxia/features/mall/tests/test_mall_card_daily.py`（易名帖撞保留的名號）、`tests/server/test_server.py`（註冊撞保留的名號）、`tests/bots/test_bot_runner.py`（假人取名）。核心的檔不往上走，`test_for` 只挑核心測試、煙霧與寫到這兩個名字的 `test_server_bots`、`test_figures`（第 58 批量過）。
- 改 `actions.py` 的 `buy`、`purchase`、`view`：`tianxia/features/looks/tests/`、`tianxia/features/zhuan/tests/` 與 `tianxia/features/explore/tests/test_outing.py` 也叫它們（形象、列傳、走一趟的票）。`test_for` 挑這一包的 `tests/` 與契約、邊界，不會挑到別包的測試（第 58 批量過）。

`howto.py`（全部拆包第 59 批「引導二」）：玩法說明自己那一節（「商城」那一節），順序在核心 `HOWTO_ORDER`，掛鉤見新手引導包的 README。

**第二輪 E 波補註**（上面對不上的以這裡為準）：
- 畫面只剩貨架、紀錄、購買確認、易名帖、管理者查帳（`web/mall.js` 505 行，`mallClick` 13 個 case）；形象那一頁在 `web/looks.js`（第 94 批）。
