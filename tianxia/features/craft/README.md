# 煉製與自創 `tianxia/features/craft/`

- **做什麼**：煉製頁的意境開爐——兩個不同的意境合成、同一種的兩份揣摩（取名的三段式：A 開單、B 鎖外請模型取名或挑名、C 整個重驗；預覽卡、爐裡放一個時另一格放得進來的提示）；自創武學五步（執器、擺式、立意、成形、立名）與作罷；重悟帖（成形後重骰形、重讀這句意）。全部拆包第 44 批搬進來（計畫 `docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md`）。**這一包的 `forge*` 是煉製頁的意境開爐；鐵匠鋪的打造（`smith_forge`、`smithing.forge_plan`、`bot.forge_step`、`forge_secrets`）不在這裡。**
- **導覽**：`docs/guide/武學與成長.md`（「模組」那一節的 `create.py`、`fusion.py`；兩種合成、自創）；籌備中的裝飾器與服務清單在 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：`docs/superpowers/specs/`：`2026-10-05-武學與成長-design.md`（合成）；武學重構（Joy 2026-10-20～22：先選兵器、擺姿勢當圖示、寫一句意、槽分顏色，自創保底上品，重悟帖）；招式與絕學稿案（以意成招）。`create.py` 檔頭寫五步的規則。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`CraftFeature`）：`enabled` 一直是 True（自創有沒有開看 `Config.arts.create_xinde`，由 `create.allowed` 擋）；`prefix` 是 None——**沒有選項前綴、沒有 `choose`**：煉製頁全是網頁按鈕打 `/api/menxia/<op>`、`/api/do/<op>`。掛鉤只有 `routes`、`content`（`create_forms.json`；`preset_recipes.json` 是序章、命名、引導共用的，不歸這一包）、`on_drop_stale`（`create.prune`：舊三步單子收掉）、`player_fields` |
| `create.py` | 自創的規則（原 `tianxia/create.py`，906 行；那個名字留成 `sys.modules` 別名，同一個模組物件）。擺式的幾何（`POSE_KEYS`、`stance_of`、`pose_read`、`preset`、`icon_pose`……）抽到共用規則層 `tianxia/pose.py`（`moves.stance_of_art` 認勢要用），`create` 照名字 re-export，`create.stance_of`、`create.preset` 照舊拿得到 |
| `actions.py` | 原本 `Game` 上的 16 個方法：開爐 `forge_request`（A）、`forge`（C）、`forge_line`、`forge_preview`、`forge_picks`；自創 `begin`、`pose`、`intent_request`（A）、`intent`（C）、`reread_request`（A）、`reread`（C）、`reroll`、`back`、`name`、`cancel`、`view`。九個動作掛核心的 `@not_while_preparing`；三個 A 段自己問 `ctx._preparing()` |
| `routes.py` | `/api/forge_line`（原本寫在 `server.py`；殼照 `FEATURES` 掛）、動作表、鎖外工作（見最後一段） |
| `tests/` | `test_craft_smoke.py`（煙霧一條：week7 合一爐、自創一門）、`test_create_ritual.py`（原 `tests/arts/`：五步、擺式、成形、立名、招式）、`test_create_reread.py`（原 `tests/arts/`：重悟帖的重讀）、`test_create_stance_hints.py`（原 `tests/arts/`：擺式提示，連網頁的幾何讀法，要 node）。整檔搬過來，三個的 `Path(__file__).parents[2]` 改成 `[4]` |

**認領的欄位**（3.5，留在原地）：`PlayerState.creating`（自創走到一半的單子）、`created_count`（這一季自創付了幾次心得）；換季跟著新角色重來（`carried` 空的）。**不認領**：`create_rerolls`（重悟帖張數，商城包 `player_fields`／`carried` 認領，換季帶著；這一包只讀寫它）、`insights`／`own_insights`／`own_serial`（共用規則層 `insights`、`insight_fx` 與有所感包）、`stats["xinde"]`（核心）。

**Game 上留的一行委派**（19 個）：16 個搬進 `actions.py` 的（`forge_request`、`forge`、`forge_line`、`forge_preview`、`forge_picks`、`create_begin`、`create_pose`、`create_request`、`create_intent`、`create_reread_request`、`create_reread`、`create_reroll`、`create_back`、`create_name`、`create_cancel`、`create_view`；這一包 `routes.py` 的 `menxia_actions`、`prepare_forge`、`create_intent`、`create_reread`（A、C 段照舊經 `Game`），假人 `bot_policy.tend_arts`、`bot.create_art`，引導包 `ctx.forge`，測試在叫），加三個查詢服務 `_create_on`、`_create_allowed`、`_create_price`（引導包碰到才說的 `h_create` 問：原本引導包直接 import `create`；服務清單二、查詢服務 `# craft`）。包裡互相叫直接叫函式；經 `ctx` 的是服務清單上的共用服務（`_log`、`_xinde`、`_menxia_entry`、`_save_season`、`_quick_client`、`_preparing`、`_solved_secrets`、`_note_solved`、`forged`、`forged_thing`、`secret_solved`、`client`）。規則照模組屬性叫（`create.set_intent`……：測試換掉模組上的，這裡照樣打得到）。

**接到掛鉤的**：`_drop_stale_references` 的 `create.prune(s, c)` → `on_drop_stale`（原本接在 `arts_mod.prune` 之後、`p.naming` 之前，現在接在最後；`create.prune` 只動 `p.creating`，中間到 `features_core.on_drop_stale` 沒有任何一行讀 `creating`，結果不變）；`/api/forge_line` → `routes`。

**還留在原位的**（`tests/core/test_feature_boundaries.py` 的 `GAME_DELEGATE_CALLERS` 逐條寫理由）：
- `status_data` 的 `create` 鍵叫 `create_view`（狀態列的鍵順序，總表第 66 批）。
- 留在殼的：`api_menxia_do` 的 `forge` 分支、`menxia_view` 的 `forge_line` 與 `create`。鎖外三段式的 B 段第 69 批進 `routes.py`：`prepare_forge`（`naming.generate`）、`create_intent`（`create.read`）、`create_reread`（`create.read_or_none`）、`forge`／`_forge_without_naming`，`MENXIA_ACTIONS` 的 `forge`／`create_*` 在 `menxia_actions`。
- 假人三支（`bot.py`：`pick_forge`、`forge_and_cultivate`、`create_art`；`bot_policy.py`：`tend_arts`、`_forge`、`apply_job`；`bot_runner.py`：`_name_and_apply`）照舊直接叫 `Game` 的公開方法與 `create.allowed/price/forms_of/preset`（走別名），沒有 `bots.py`（手冊 3.8 之後才拆）。
- `skillview`（`create_mod.icon_pose`、`marks_of`、`look_text`、`tier_of`）與 `fusion`（合成與揣摩，`SHARED_LATER`）照舊；包的 `actions.py` import 它們，行尾註「過渡：待搬」。

**改這一包時 `test_for` 挑不到、要另外跑的**（混在別人檔裡的測試，批次表第二節不拆）：
- `tests/arts/test_forge_picks.py`（3 條）：只測 `skillview.forge_picks`（不經 `Game`），歸 skillview／fusion，留原位。
- `tests/arts/test_fusion.py`、`test_fusion_design.py`（合成與揣摩，`fusion` 不搬）、`tests/arts/test_skillview.py`、`tests/arts/test_arts_pages_two.py`（煉製頁；連網頁）。
- 直接 `import create`、走別名的混合檔：`tests/core/test_journal.py`、`tests/figures/test_week_unlock.py`、`tests/seal/test_seal.py`、`test_seal_revamp.py`、`tianxia/features/cultivation/tests/test_ascend.py`。
- 網頁：`tests/web/test_craft_web.py`（這一批不切網頁）。
- 一起跑：`scripts/test_for.py --base <分支> <改的包檔> tests/arts/test_fusion.py tests/arts/test_skillview.py tests/web/test_craft_web.py`。

**過渡 import**（註「過渡：待搬」）：`actions.py` 2 行（`fusion`、`skillview`，共用規則層 `SHARED_LATER`）、`create.py` 1 行（`annals`，行狀第 29 批）。核心本體與共用規則層（含新的 `pose`）不算過渡。舊模組 → 包多 1 個別名（`tianxia/create.py`）與 engine 委派的兩行 import（`craft_actions`、`create`），另有 `bot.py`、`skillview.py`、`server.py`、`scripts/` 走別名（舊模組 → 包 224 → 239）。共用規則層 64 → 65 個模組（新增 `pose`）；`SHARED_PENDING` 14 → 13 條。

**行狀記一筆改 import 核心**（全部拆包第 29 批之二）：本包原本「包 → `tianxia.annals`」的過渡 import 改成 `from tianxia.core import annal_base as annals`（核心本體，不算過渡，行尾註拿掉「過渡：待搬」）；上面各處寫到 `annals` 的過渡句（含處數）是這一批之前的舊寫法，現在那幾處不算過渡，數字一律以 `python tests/core/test_feature_boundaries.py` 重印為準（舊名 `tianxia/annals.py` 是指到列傳包 `standing.py` 的別名，那一份 re-export 核心那一半）。

**動作表**（全部拆包第 68 批；原本寫在 `server.py`）：`routes.py` 的 `menxia_actions`：`create_begin`、`create_pose`、`create_back`、`create_name`、`create_cancel`、`create_reroll`。開爐（`MENXIA_ACTIONS["forge"]`）與立意的三段式第 69 批也搬進來（見下一段）。 殼的 `MAIN_ACTION_ORDER`、`MENXIA_ACTION_ORDER` 寫死表的先後（`action_table`；少一個開機就丟例外），暫停中照做的名單 `PAUSE_OK_ACTIONS` 留在殼。`scripts/same_behavior.py` 的 `switchboard` 一軌逐字記包裡的函式收到什麼。`Game` 的委派一個沒拿（假人、測試還在叫）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：`routes.py` 的 `prepare_forge`、`forge`、`forge_args`、`_forge_without_naming`（`MENXIA_ACTIONS["forge"]`）、`create_intent`、`create_reread`（`/api/do/create_*`，`outlock` 掛鉤）。殼留一行包裝：`prepare_forge`、`forge`、`forge_args`、`create_reread`；`api_menxia_do` 的 `forge` 分支留殼。`naming` 經 `shell.naming`（寫 import 會多一條包 → 舊模組）。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tests/server/test_server.py`、`tests/arts/test_in_lock_model_timeout.py`、`tests/server/test_outlock.py`。
