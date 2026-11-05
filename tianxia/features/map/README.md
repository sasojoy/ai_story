# 輿圖（`tianxia/features/map/`）

- 做什麼：天下圖、各區圖、小地圖、地點詳情，以及每一種疊層（局勢、敵情、傳聞、意境提示、出陣、軍令、懸賞……）的資料與畫法。全部從存檔現算、只讀，自己沒有寫到一半的東西。
- 導覽：`docs/guide/地圖與介面.md`
- 設計稿：`docs/superpowers/specs/2026-10-30-輿圖表現-design.md`（輿圖表現第二版）、`docs/superpowers/specs/2026-10-15-輿圖升級-design.md`
- 搬家計畫：`docs/superpowers/plans/2026-11-06-輿圖包-第1批.md`（全部拆包第 49 批）。`web/map.js` 照手冊 G9 留在 `web/`、由這一包的 `web` 宣告（第 49 批 PM 認定第 1 條：計畫 Task 5 不做，第 64～67 批殼化時再看）；`atlas` 拆兩半（計畫 Task 6）留給總表第 50 批（PM 認定第 2 條）。

## 檔案

| 檔 | 內容 |
|---|---|
| `__init__.py` | 登記：沒有前綴、沒有選項、沒有狀態鍵；`routes` 一個掛鉤；`web = ("map.js",)`（檔照手冊 G9 留在 `web/`，第 64～67 批殼化時再看）；`enabled` 一直是 True（輿圖沒有開關） |
| `actions.py` | 原本 `Game` 上輿圖的 11 個方法（`self`→`ctx`）：`map_base`、`map_state`、`map_foes`（`_map_foes`）、`fierce_line`（`_fierce_line`）、`world_map_svg`、`minimap_svg`、`map_legend`、`map_header`、`map_places`、`place_detail`、`travel_options`；另有探索包問的兩個查詢 `open_places`、`mostly_here`（Game 上的 `_map_open_places`、`_map_mostly_here`） |
| `views.py` | `/api/map` 的資料：`map_base_view`（底圖，照 `mapdata.base_key` 快取）、`map_view`（舊輿圖；殼的 `md` 當參數傳進來）、`MAP_BASE`／`MAP_BASE_KEEP`（快取字典，`server.MAP_BASE` 是同一個物件）、`DEFAULT_LAYER`；不碰 fastapi |
| `routes.py` | `GET /api/map`、`GET /api/map/base`、`GET /api/map/state`（殼照 `FEATURES` 掛；一律照 `shell.<名字>` 當下讀，測試換掉 `server.map_view` 也看得到） |
| `mapview.py` | 畫法：四層 SVG、小地圖、圖例（`legend_data`）、`open_places`、`render_base`（原 `tianxia/mapview.py`，舊名留成別名） |
| `mapart.py` | 設色山水：地形、河、區塊的畫法（原 `tianxia/mapart.py`，舊名別名） |
| `mapdata.py` | 底圖資料與疊層：`base`、`state`、`base_key`、`with_mostly`、`mostly_here`、`place_mostly`（原 `tianxia/mapdata.py`，舊名別名） |
| `worldgeo.py` | 天下圖的純幾何（原 `tianxia/worldgeo.py`，舊名別名） |

## 認領的欄位

**沒有 `PlayerState` 欄位**（`player_fields = ()`、`carried = ()`）。`content/map.json` 是核心 `models.Content.map` 的，不歸這一包。

## 這一批做的設計（包→包三條，不用過渡）

搬到 `core/services.py` 的純函式與字表是**寄放**：`services.py` 是 ctx 服務清單，第 50 批（`atlas` 拆兩半）把它們移到核心小模組（照 `omen_base`、`annal_base`、`convoy_base` 前例），原模組照舊 re-export（第 49 批 PM 認定第 3 條）。

- **探索包讀輿圖**：原本 `explore_actions` import `mapdata`（`LOSE_WORD`、`mostly_here`）與 `mapview`（`open_places`）。`LOSE_WORD` 搬到 `core/services.py`（`mapdata.LOSE_WORD` 是同一個字串）；`mostly_here`、`open_places` 改經 `Game` 的一行委派 `_map_mostly_here`、`_map_open_places` 問這一包。
- **輿圖讀探索包**：`mapdata` 讀探索表的 `kind_of`、`hint_in`、`mostly_in`。這幾個純函式（連同六種地點、四類事、「多半」兩個字的字表與算法）搬到 `core/services.py`，`explore_rules` re-export（`explore_rules.kind_of is services.kind_of`）。
- **輿圖讀有所感包**：`sensing.terrain_tags` 搬到 `core/services.py`，`sensing` re-export。
- **輿圖讀出陣包**：`mapview` 的 `sortie.on` 就是 `territory.on`（共用規則層）；`map_state` 的 `sortie.mode` 改問 `ctx._sortie_mode(loc)`（服務清單二、查詢服務 `# map`）。

## 還留在原位的接縫（理由在 `tests/core/test_feature_boundaries.py` 的 `# map` 那一段）

- **`/api/travel` 帶的 `map`**（走不成時回 `{arrived: false, map, reason}`）：`/api/travel` 是移動包的路由（第 47 批搬進 `tianxia/features/travel/routes.py`），經 `shell.map_view` 帶 `map`；`server.map_view` 是一層薄薄的包裝（把殼的 `md` 帶進 `views.map_view`；`server.py` 直接 import 這一包的 `views`，第 49 批 PM 認定第 10 條）。
- **`bot_policy` 的 `travel_options`**（假人的移動選項）：叫 `Game.travel_options` 的一行委派。假人不看地圖。
- **`view_map`**（新手引導包的）、**`tab:map`**（揭曉鍵）：不是這一包的；輿圖沒有選項前綴。
- **`app.js` 的 `loadMap`**：殼呼叫的入口，留在 `app.js`。
- **`Game.MAP_LAYERS`**（`atlas.LAYERS`）：類別屬性，`views.map_view` 與 `test_atlas` 讀它。

## 過渡（手冊 3.11）

過渡 import 共 4 行（包到舊模組，都標了「# 過渡：待搬」）：`actions`→`atlas`、`orders`；`mapdata`→`atlas`、`bounties`、`figures`、`orders`；`mapview`→`atlas`、`orders`（兩行，一行是 `atlas.KNOWN`、`atlas.Odds`）。`atlas` 拆兩半（圖層那一半進包）留給總表第 50 批（計畫 Task 6，第 49 批 PM 認定第 2 條；這幾行的註寫「atlas 第 50 批拆兩半」），做完 `actions`、`mapview`、`mapdata` 對 `atlas` 的過渡會少一部分（留在 `atlas` 的是地點與路的資料，移動、地盤、設伏都在讀，不進包）。舊模組到包有 `engine.py` 的 `GAME_IMPORTS` 一行（`tianxia.features.map.actions`）與四個別名（`mapview`、`mapart`、`mapdata`、`worldgeo`）。

## 測試

- 這一包的 `tests/`（全部拆包第 49 批從 `tests/` 整檔搬來，含 slow）：`test_mapview.py`（畫法）、`test_mapart.py`、`test_mapdata.py`（底圖、疊層、推薦）、`test_mapdata_layers.py`、`test_mapdata_suggest_cooling.py`、`test_map_base.py`、`test_open_map.py`、`test_worldgeo.py`、`test_world_map.py`、`test_real_map.py`（正式內容的地圖）、`test_map_perf.py`、`test_map_history.py`、`test_jianfa_3d_map_foes.py`（地點卡的對手與勝算）；另加 `test_map_package.py`（接縫：舊名別名、殼留的是同一個物件、三條路由、搬到核心服務檔的函式是同一個物件）。搬的時候改的只有 `test_mapview.py`、`test_real_map.py` 讀 `content/` 的路徑（`parents[2]` 換成 `parents[4]`）。
- 混合檔的一處改動：`tests/core/test_test_for.py` 的 `test_a_module_also_picks_the_tests_of_the_modules_that_import_it` 原本拿 `mapview` 當「還是舊模組」的例子，`mapview` 成了包的模組，換成本週卡 `step`（經 `weekcard` 挑到 `test_weekcard`）。
- 跑：`pytest tianxia/features/map/tests -m "slow or not slow" -n 4`。

## 另外要跑的混合檔

- `tests/map/test_atlas.py`（測 `atlas` 的核心那一半，圖層那幾條跟著第 50 批 `atlas` 拆兩半改 import）、`tests/map/test_weekcard.py`、`tests/map/test_four_wins_lean_anytime.py`（不是輿圖的，留）
- `tests/web/test_map_web.py`（網頁；留在 `tests/web`，歸總表第 61 批〔混合測試檔歸位〕一起搬，第 49 批 PM 認定第 9 條）、`tests/web/test_conquest_web.py`、`tests/core/test_prologue.py`（讀 `mapart._terrain_key`、`_obstacles`）、`tests/core/test_models.py`
- `tests/server/test_server.py -k map`（`map_view`、`map_base_view`、`/api/travel` 的 `map`）、`tests/seal/test_seal_acts3.py`、`tests/seal/test_seal_acts_hidden.py`（用 `server.map_view`）、`tests/figures/test_week_unlock.py`（`mapdata.mostly_here`）
- 別包的：`tianxia/features/explore/tests/test_explore_one*.py`（用 `mapdata.mostly_here`、`MOSTLY`、`VIEWER_MOSTLY`、`base_key`、`server.MAP_BASE`）、`tianxia/features/sortie/tests/test_sortie_duel_map.py`（`mapdata.state`、`Game.map_state`）
- 改這一包時：`python scripts/test_for.py --base HEAD tianxia/features/map/mapdata.py`
