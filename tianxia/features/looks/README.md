# 擂台形象（`tianxia/features/looks/`）

- **做什麼**：玩家在萬寶閣用元寶買一套擂台形象，在「形象」那一頁換上；擂台動畫照兩邊穿的那一套畫。預設是斗笠小子。買到的形象綁帳號，換季也帶著走；退款的形象收回。假人不買，照名號挑一套 `bots` 開著的。
- **導覽**：`docs/guide/商城.md` 的「擂台形象」那一節
- **設計稿**：擂台動畫＋付費自建形象 v3（https://claude.ai/artifact/5NMJiMhXFPYwdnMA2TQi3U；Joy 2026-10-31「都按照建議」），第二期的基礎版

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`LooksFeature`）：`enabled`＝商城開著＋`content/looks.json` 有東西、`routes`、`check_content`（id 當資料夾名、名字過命名過濾） |
| `rules.py` | 純規則：買到哪幾套（`owned`，照核心 `core.services.look_ids`）、穿哪一套（`worn`／`wear`，記在 `mall_entitlements` 的 `look`／`wear`）、假人挑哪一套（`bot_look`）、畫面資料（`view`） |
| `actions.py` | `look_of`（`Game.arena_look` 的一行委派叫它）、`view`、`wear` |
| `routes.py` | `GET /api/looks`、`POST /api/looks/wear {look}`；關著 404 |
| `tests/` | `test_looks.py`（買、換上、換季、退款、假人、關著）、`test_looks_web.py`（萬寶閣「形象」那一頁）、`looks_stage.py` |

**賣是商城包的事**：商品 `kind` 寫 `look`、`look` 寫哪一套、效果只寫 `{"look": 1}`（`mall.item_problems` 驗）；購買那一列 `data` 多記 `look_id`（商品下架了也認得）；同一套買過了不再賣（`LOOK_OWNED`）。
**認領的欄位**：沒有角色上的欄位；`ArenaEntry.look`、`ArenaFight.skins`、`ArenaResult.skins` 是擂台的（`tianxia/state.py`），網頁的 `looks.me_look`／`foe_look`。
