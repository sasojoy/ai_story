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
| `moves.py` | 招式動畫（第三批）：替自己的武功下單、招式庫、每季綁到一門武功（同打法免費）、擂台記哪一招；2026-11-01 起下單是一句話自創（`scenes.py`） |
| `scenes.py` | 一句話自創絕招：一句話 → 導演稿（動作表、夾參數、時間照表排）、要畫的法相巨物、給生圖工具的提示詞 |
| `studio.py` | 畫坊的流程（2026-11-01）：抓等圖的單（絕招的法相巨物、自建形象的定裝照與十張）、畫、切、審、不過照意見改最多三張、收或停手、管理者「再畫一次」 |
| `studio_api.py` | 畫坊真的去叫的：Nano Banana（Gemini 生圖，`GEMINI_API_KEY`）、Claude 審圖（`ANTHROPIC_API_KEY`）；只有 `run_studio.py` 用 |
| `cutting.py` | 去背、切格（畫坊與 `scripts/cut_look.py` 共用；Pillow、numpy、scipy，伺服器不 import） |
| `market.py` | 形象市集（第四批）：自建形象定價上架、撤下、別人買一份、分成五五押七天才入帳、儲值限定的開關 |
| `tests/` | `test_looks.py`（買、換上、換季、退款、假人、關著）、`test_looks_orders.py`（自建形象）、`test_looks_moves.py`（招式動畫）、`test_looks_scenes.py`（導演稿）、`test_looks_studio.py`（畫坊，生圖審圖都是假的）、`test_looks_market.py`（市集）、`test_looks_server.py`、`test_looks_web.py`（萬寶閣「形象」那一頁、管理者區）、`looks_stage.py` |

兵器掛在哪：`web/arena_anim.js` 的 `RING_HAND` 是照斗笠小子量的，共用會讓別套形象的兵器懸在空中（Joy 2026-11-02 看出來的，量四套新形象，49 格裡各有 7～11 格落在身體以外）。每一套自己的手位表存在圖旁邊的 `hands.json`（`cutting.hand_row` 算：從斗笠小子那一點往外找最近的身體像素；官方形象跑 `scripts/look_hands.py`，自建的在 `orders.save_sheet` 存圖時順手算），網頁抓得到就用它的位置、角度與層次照舊讀 `RING_HAND`，抓不到整個照 `RING_HAND`。

切圖：`scripts/cut_look.py`（開發機或主機；Pillow、numpy、scipy）。畫坊：根目錄 `run_studio.py`（主機，跟 `server.py`、`run_bots.py` 一起開；裝 `requirements-studio.txt`）。

**賣是商城包的事**：商品 `kind` 寫 `look`、`look` 寫哪一套、效果只寫 `{"look": 1}`（`mall.item_problems` 驗）；購買那一列 `data` 多記 `look_id`（商品下架了也認得）；同一套買過了不再賣（`LOOK_OWNED`）。
**認領的欄位**：沒有角色上的欄位；`ArenaEntry.look`、`ArenaFight.skins`、`ArenaResult.skins` 是擂台的（`tianxia/state.py`），網頁的 `looks.me_look`／`foe_look`。
