# 商城（萬寶閣）`tianxia/features/mall/`

- **做什麼**：元寶的賣與記帳——商品上架與購買、發貨、月卡（每日領）、易名帖、封測發放、管理者的補發扣回退款與查帳；錢包（`tianxia/wallet.py`）與票的庫存、消耗（`ctx.wallet`）是核心的服務，別的功能用票叫核心、不叫這一包。
- **導覽**：`docs/guide/商城.md`（模組、規則速查、畫面、資料庫第 6 版、部署與對帳、販賣清單、列傳為終點的四件）；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：`docs/superpowers/specs/2026-10-20-商城架構-design.md` 第 1 版（手冊之前的稿，文內沒有版本號；企劃者 2026-10-20 核准）；第 1 階搬包照 `docs/superpowers/specs/2026-10-30-開發模式-design.md` 3.10。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`MallFeature`）：`enabled`＝`Config.mall.enabled`、`status`（江湖畫面的 `mall`）、`admin_tools`、`routes`、`check_content`、`on_own_turn`（封測發放，全部拆包第 11 批的接縫掛鉤）；`web`＝`mall.js`、`mall.css`（在 `web/`，第 3 階才搬進包）、`content`＝`mall.json`（在 `content/`） |
| `rules.py` | 純規則（原 `tianxia/mall.py`；那個名字留成別名給測試） |
| `rename.py` | 易名帖換名號的規矩（`clash`；`swap` 在核心 `tianxia/core/swap.py`） |
| `actions.py` | 原本 `Game` 上的 `mall_*`、`admin_mall_*`（全部拆包第 58 批委派全拿掉，路由與測試直接叫這裡）；`purchase` 回 `Receipt`（`lines`、`bought`、`already`，路由從回傳值拿），`buy` 只要句子 |
| `routes.py` | `/api/mall`、`/api/mall/records`、`/api/mall/buy`、`/api/mall/claim`、`/api/mall/rename`、`/api/admin/mall`；`/api/do/mall_reissue|revoke|refund` |
| `tests/` | 原 `tests/mall/`（`test_wallet.py` 測核心的錢包，搬到 `tests/core/`）與 `tests/web/test_mall_web.py` |

**認領的欄位**（3.5，留在原地）：`PlayerState.holding_bonus`（只這一季）、`create_rerolls`、`legend_items`（換季帶著走，核心的換季照抄）。原本寄放在 `Game` 上的 `mall_bought`、`mall_already` 第 58 批收回包（`actions.Receipt`）。資料庫第 6 版的三張表 `mall_purchases`、`mall_ledger`、`mall_entitlements`（`database.py`，核心）。
**過渡**：沒有了（保留的名號第 58 批搬進核心 `core/name_base.py`，`actions.py` 不再 import `server_bots`；插畫票用不上不賣的 `art_problem`、`ART` 全部拆包第 29 批進核心服務 `core/services.py`，不再 import `zhuan_end`；`journal` 江湖紀錄 PM 10/31 定算核心，不再是過渡；`rules.py` import 的 `tianxia.library`〔功法庫上限〕全部拆包第 15 批登記進共用規則層，行尾改註「共用規則層」，不算過渡）；`howto.py`（玩法說明「商城」一節）、`scripts/mall_ledger.py` import 這一包。封測發放原本是 `own_turn_checks` 叫 `Game._mall_grant`，全部拆包第 11 批（核心收接縫）換成 `on_own_turn` 接縫掛鉤（`own_turn_checks` 最前面、暫停的檢查之前，不問 `enabled`），委派拿掉。`tianxia/mall.py` 舊名別名還在（`from tianxia import mall` 的測試沒改），`howto.py` 的 import 是第 59 批的事。

**另外要跑的**（`test_for` 挑不到；改這幾處開發與修正另跑，`-n 4`，不含 slow）：

- 改 `core/name_base.py`：`tianxia/features/mall/tests/test_mall_card_daily.py`（易名帖撞保留的名號）、`tests/server/test_server.py`（註冊撞保留的名號）、`tests/bots/test_bot_runner.py`（假人取名）。核心的檔不往上走，`test_for` 只挑核心測試、煙霧與寫到這兩個名字的 `test_server_bots`、`test_figures`（第 58 批量過）。
- 改 `actions.py` 的 `buy`、`purchase`、`view`：`tianxia/features/looks/tests/`、`tianxia/features/zhuan/tests/` 與 `tianxia/features/explore/tests/test_outing.py` 也叫它們（形象、列傳、走一趟的票）。`test_for` 挑這一包的 `tests/` 與契約、邊界，不會挑到別包的測試（第 58 批量過）。
