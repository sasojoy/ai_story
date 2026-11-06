# 列傳（`tianxia/features/zhuan/`）

一季的終點是一篇列傳：寫傳（鎖內開單、鎖外叫模型、鎖內重驗再存的三段式）、休季三顆（用列傳插畫、蓋紀念印、請人物親筆評曰）、行狀頁與分享。全部拆包第 29 批搬進來（計畫 `docs/superpowers/plans/2026-11-04-列傳包-第1批.md`）。

- 導覽：`docs/guide/核心與存檔.md`（行狀 `annals`、寫傳 `biography`）、`docs/guide/商城.md`（「列傳為終點的四件」與重修列傳）。`大勢人物與賽季.md` 沒有列傳這一節。
- 設計稿：減法季整合設計第九章（列傳為終點）；玩家傳第一、二批沒有獨立的設計稿檔，規則寫在上面兩份導覽那兩節。
- 開關：`Config.jianfa.zhuan_end` 加開季的章（`zhuan_end.on`）。關著什麼都不做、商城不上架三張票；行狀本身看 `Config.biography` 與核心的 `annal_base.on`（`tianxia/core/annal_base.py`）。
- 內容：`content/verdicts.json`（人物評曰的固定句，包宣告 `content = ("verdicts.json",)`，驗證在 `ZhuanFeature.check_content`）。

## 補充說明（這一包的東西在哪）

- `actions.py`：原本 `Game` 上的 20 個方法的本體（換季補論功 `past`、同步記行狀 `tick`、行狀頁 `annals_view`、休季入口 `entry`、休季三顆 `options`／`act`、寫傳 A `request`、C `write`、讀傳 `view`、分享 `share`……），加上 `choose_unlisted`（休季用票的 choose）與 `profile`（第 29 批之二：換季存行狀時的身家，轉 `standing.profile`）。
- `standing.py`（第 29 批之二，原 `tianxia/annals.py` 的查詢與行狀頁那一半）：`profile`、`standing`、`tier_text`／`tier_note`、`xingshi_notes`、`rows`；用 `import *` 加 `_gear`、`_notable` re-export 核心 `annal_base` 的名字，舊名 `tianxia/annals.py` 是指到它的 `sys.modules` 別名。
- `biography.py`（原 `tianxia/biography.py`）、`zhuan_end.py`（原 `tianxia/zhuan_end.py`）、`zhuan_html.py`（原根目錄 `zhuan_html.py`）：舊名都留成指到同一個模組的別名。
- `routes.py`：`/api/annals`、`/api/zhuan`、`/api/zhuan/write`、`/api/zhuan/share`、`/zhuan/{code}`；殼（`server.py`）照 `FEATURES` 掛，殼的東西一律照 `shell.<名字>` 當下讀。
- 掛鉤：`choose_unlisted`（`zhuan:` 前綴，先看前綴再叫選單，原本在 `Game.choose` 的 `choose_unlisted` 之後、查選單之前）、`routes`、`check_content`、`enabled`（沒有任何掛鉤吃它）。沒有 `options`／`menu`：休季用票的鈕是 `Game._everyday_options` 休季那一支叫 `_zhuan_options` 一行委派。
- 前綴 `zhuan:`（`zhuan:pick_art`、`zhuan:seal`、`zhuan:quote:<人物 id>`）。沒有假人分數、沒有 `bots.py`：假人在休季整個不動，碰不到 `zhuan:`（`bot_policy`、`bot.py`、`bot_runner` 都沒有寫 `zhuan`）。
- 核心要用的那一段在 `tianxia/core/services.py`（`# zhuan`）：`illustration_for`、`writers`、`Writer`、`art_problem`、`ART`、`ART_NO_SIDE`、`ART_FREE`、`AFFINITY／TIER／BOUGHT／REASONS`（行狀 `standing.py` 的 `standing` 與商城插畫票用），`zhuan_end` re-export。

## 認領的欄位（手冊 3.5）

`player_fields = ()`、`carried = ()`：`annals`、`annals_mark`、`xingshi_seen` 是行狀，核心 `core/annal_base.py` 管，這一包不認領；列傳存在資料庫的 `biographies` 表，票在錢包（商城）裡，都不是 `PlayerState` 欄位。

## 還留在原位的接縫

- `Game` 上 9 個一行委派：`_zhuan_past`（換季：`_reset_player_for_new_season` 最前面）、`_zhuan_profile`（第 29 批之二；換季存行狀：`save_annals` 的第四個引數）、`_zhuan_options`（`_everyday_options` 休季那一支）、`annals_view`、`biography_entry`（server `main_view`）、`biography_request`、`write_biography`、`biography_view`、`share_biography`。紀錄先後算行為，前三個不是掛鉤的位置，記在邊界測試的 `GAME_DELEGATE_CALLERS`。
- B 段（鎖外叫模型）留在 `server.py`：`write_zhuan`、`verdict_text`、`ZHUAN_JOBS`、`ZHUAN_LOCK`，加上 `zhuan_view`、`zhuan_extras`、`zhuan_art_src`、`public_base`、`_season_arg`、`_zhuan_key`。`tests/server/test_server.py` 掃「鎖外叫模型的函式」認 `zhuan_job`、`verdict_text` 這幾個名字；鎖外工作的掛鉤是總表第 69 批，到時候再搬。
- 根目錄 `zhuan_html.py` 是別名檔（`server.py` 舊的 import、`tests/core/test_desktop_type.py` 讀的路徑）；`tests/core/test_shop_width.py` 讀這個檔斷言「不含 zhuan-layer」，別名檔也成立，但斷言的實質變弱了（真正的內容在包裡）。
- 行狀拆兩半（全部拆包第 29 批之二）：記一筆的那一半（`note`、`entry`、`watch`、種類常數）在核心 `tianxia/core/annal_base.py`，`biography.py`、`actions.py` 與各包記行狀都 import 它（不算過渡）；查詢與行狀頁那一半（`profile`、`standing`、`tier_*`、`xingshi_notes`、`rows`）在 `standing.py`。舊名 `tianxia/annals.py` 是指到 `standing.py` 的 `sys.modules` 別名（`standing` re-export 核心那一半，兩半的名字都拿得到、同一批物件；從這一批起舊名 `annals` 算列傳包，包要記一筆一律 `from tianxia.core import annal_base as annals`，不准再 `from tianxia import annals`）。換季存行狀時的身家 `profile` 核心不能 import 包，經 `Game._zhuan_profile` 一行委派（Game 上列傳的委派成了 10 個）。

## 測試

整檔搬進 `tests/`：`test_biography.py`（85，含網頁路由與公開頁；有一條 `@pytest.mark.smoke`）、`test_biography_ties.py`（21）、`test_verdicts.py`（7，slow）、`test_annals_jianfa.py`（10），共用的 `zhuan_fix_kit.py`（商城的 `test_mall_zhuan_items.py` 也 import 它，`tests/conftest.py` 把每個測試資料夾放上 `sys.path`），擺局面檔 `zhuan_stage.py`（只有「平常」：休季用票的鈕不是 `options` 掛鉤給的，契約測試問不到）。整包含 slow：`pytest tianxia/features/zhuan/tests -m "slow or not slow" -n 4`，123 條約 7 秒。

**另外要跑的混合檔**（含列傳的測試，但檔案不屬於這一包，不拆）：

- `tests/core/test_annals.py`（19 條，行狀記一筆那一半，核心；其中一條讀本包的 `routes.py` 看 `/api/annals` 有沒有掛）、`tests/core/test_annals_alias.py`（1 條，第 29 批之二：舊名 `annals` 上兩半的名字都是同一個物件）
- `tianxia/features/mall/tests/test_mall_zhuan_items.py`（45 條，商城的三張票；import 本包的 `zhuan_fix_kit`）、`test_mall_card_daily.py`（17 條，重修列傳票）
- `tests/core/test_desktop_type.py`（11 條）、`test_shop_width.py`（15 條）：讀根目錄別名 `zhuan_html` 與 `zhuan.css`
- `tests/core/test_jianfa_switch.py`（9 條）、`tests/core/test_gender.py`（9 條）、`tests/bots/test_zh.py`（25 條）：各有一兩條碰 `zhuan_end`／`biography` 的字

改這一包時連它們一起跑：`python scripts/test_for.py --base HEAD tianxia/features/zhuan/actions.py`，再視需要加上面幾個檔。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`sync.deliver` 的 `zhuan`（`actions.tick`）。換季最前面那幾行（`_zhuan_past`、`_story_close_season`、`_zhuan_profile`）留在原位：`past` 這個值要從第一行傳到第三行，掛鉤沒有傳值的位置。
