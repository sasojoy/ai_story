# 商城（萬寶閣）`tianxia/features/mall/`

- **做什麼**：元寶的賣與記帳——商品上架與購買、發貨、月卡（每日領）、易名帖、封測發放、管理者的補發扣回退款與查帳；錢包（`tianxia/wallet.py`）與票的庫存、消耗（`ctx.wallet`）是核心的服務，別的功能用票叫核心、不叫這一包。
- **導覽**：`docs/guide/商城.md`（模組、規則速查、畫面、資料庫第 6 版、部署與對帳、販賣清單、列傳為終點的四件）；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：`docs/superpowers/specs/2026-10-20-商城架構-design.md` 第 1 版（手冊之前的稿，文內沒有版本號；企劃者 2026-10-20 核准）；第 1 階搬包照 `docs/superpowers/specs/2026-10-30-開發模式-design.md` 3.10。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`MallFeature`）：`enabled`＝`Config.mall.enabled`、`status`（江湖畫面的 `mall`）、`admin_tools`、`routes`、`check_content`；`web`＝`mall.js`、`mall.css`（在 `web/`，第 3 階才搬進包）、`content`＝`mall.json`（在 `content/`） |
| `rules.py` | 純規則（原 `tianxia/mall.py`；那個名字留成別名給測試） |
| `rename.py` | 易名帖換名號的規矩（`clash`；`swap` 在核心 `tianxia/core/swap.py`） |
| `actions.py` | 原本 `Game` 上的 `mall_*`、`admin_mall_*`；`Game` 留一行委派 |
| `routes.py` | `/api/mall`、`/api/mall/records`、`/api/mall/buy`、`/api/mall/claim`、`/api/mall/rename`、`/api/admin/mall`；`/api/do/mall_reissue|revoke|refund` |
| `tests/` | 原 `tests/mall/`（`test_wallet.py` 測核心的錢包，搬到 `tests/core/`）與 `tests/web/test_mall_web.py` |

**認領的欄位**（3.5，留在原地）：`PlayerState.holding_bonus`（只這一季）、`create_rerolls`、`legend_items`（換季帶著走，核心的換季照抄）；`Game.mall_bought`、`Game.mall_already`（伺服器在鎖裡讀）。資料庫第 6 版的三張表 `mall_purchases`、`mall_ledger`、`mall_entitlements`（`database.py`，核心）。
**過渡**：`rules.py` import `tianxia.library`（功法庫上限）、`actions.py` import `server_bots`（保留的名號）、`zhuan_end`（插畫票用不上不賣），都註「過渡：待搬」（`journal` 江湖紀錄 PM 10/31 定算核心，不再是過渡）；`howto.py`（玩法說明「商城」一節）、`scripts/mall_ledger.py` import 這一包；`Game._mall_grant` 在 `own_turn_checks` 裡（封測發放）。
