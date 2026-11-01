# 擂台形象（`tianxia/features/looks/`）

- **做什麼**：玩家在萬寶閣用元寶買一套擂台形象，在「形象」那一頁換上；擂台動畫照兩邊穿的那一套畫。預設是斗笠小子。買到的形象綁帳號，換季也帶著走；退款的形象收回。假人不買，照名號挑一套 `bots` 開著的。
- **導覽**：`docs/guide/商城.md` 的「擂台形象」那一節
- **設計稿**：擂台動畫＋付費自建形象 v3（https://claude.ai/artifact/5NMJiMhXFPYwdnMA2TQi3U；Joy 2026-10-31「都按照建議」），第二期的基礎版

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`LooksFeature`）：`enabled`＝商城開著＋`content/looks.json` 有東西、`routes`、`check_content`（id 當資料夾名、名字過命名過濾） |
| `rules.py` | 純規則：買到哪幾套（`owned`，照核心 `core.services.look_ids`）、穿哪一套（`worn`／`wear`，記在 `mall_entitlements` 的 `look`／`wear`）、假人挑哪一套（`bot_look`）、畫面資料（`view`） |
| `actions.py` | `look_of`（`Game.arena_look` 的一行委派叫它）、`view`、`wear`；第二批 `order`、`admin_view`／`admin_upload`／`admin_release`／`admin_reject`、`gen_mode`（`TIANXIA_LOOK_GEN`） |
| `orders.py` | 自建形象的訂單（第二批）：下單、狀態、圖的檔頭驗證與存放（資料庫旁邊的 `looks/u<id>/`）、假的生圖器、上架與退回、給生圖工具的提示詞 |
| `routes.py` | `GET /api/looks`、`POST /api/looks/wear {look}`、`POST /api/looks/order`、`GET /api/looks/img/<u數字>/<張>`、`GET /api/admin/looks`、管理者工具 `looks_upload`／`looks_release`／`looks_reject`；關著 404 |
| `moves.py` | 招式動畫（第三批）：替自己的武功下單一張六格光效、招式庫、每季綁到一門武功（同打法免費）、擂台記哪一招 |
| `market.py` | 形象市集（第四批）：自建形象定價上架、撤下、別人買一份、分成五五押七天才入帳、儲值限定的開關 |
| `tests/` | `test_looks.py`（買、換上、換季、退款、假人、關著）、`test_looks_orders.py`（自建形象）、`test_looks_moves.py`（招式動畫）、`test_looks_market.py`（市集）、`test_looks_server.py`、`test_looks_web.py`（萬寶閣「形象」那一頁、管理者區）、`looks_stage.py` |

切圖：`scripts/cut_look.py`（開發機或主機；Pillow、numpy、scipy）。

**賣是商城包的事**：商品 `kind` 寫 `look`、`look` 寫哪一套、效果只寫 `{"look": 1}`（`mall.item_problems` 驗）；購買那一列 `data` 多記 `look_id`（商品下架了也認得）；同一套買過了不再賣（`LOOK_OWNED`）。
**認領的欄位**：沒有角色上的欄位；`ArenaEntry.look`、`ArenaFight.skins`、`ArenaResult.skins` 是擂台的（`tianxia/state.py`），網頁的 `looks.me_look`／`foe_look`。
