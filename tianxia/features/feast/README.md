# 宴客 `tianxia/features/feast/`

- **做什麼**：大勢人物設宴（季的事）、玩家入席敬酒（固定的三句或自己寫一句、模型鎖外評分）、情誼照分數漲、散席時席間最佳那一句上天下大事、那個人補名望。第 1 階多搬的「有按鈕的小包」（開發規範手冊 3.10），驗 `options`、接管選單（`menu`）、`choose`、`on_sync`、`bot_pick` 這幾個商城用不到的掛鉤。
- **導覽**：`docs/guide/大勢人物與賽季.md` 的「宴客（功能包）」那一節；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：大勢人物擴充第三批「多人同服的玩法」（https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2）第 1 版（手冊之前的稿，沒有版本號），數字在 `Config.figure_life` 的 `feast_*`。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`FeastFeature`）：`enabled`＝宴客開著或這一季還有擺過的宴、`options`（入席）、`menu`（坐在席上）、`choose`（`feast:`，標題先算）、`on_sync`、`bot_pick`、`bot_always`＝`feast:` |
| `rules.py` | 純規則（原 `tianxia/feasts.py`；那個名字留成別名給測試） |
| `actions.py` | 原本 `Game` 上的 `_feast_seat`、`_feast_options`、`_feast_menu`、`_feast_act`、`feast_*`；`Game.feast_free_text_prompt`、`feast_text_request`、`feast_toast` 留一行委派 |
| `bots.py` | 假人的分數（原 `bot_policy.score` 的 feast 那一段）：入席 8、敬酒 50、離席不按 |
| `tests/` | `test_feast.py`（原 `tests/figures/test_figure_life_batch3.py` 的「宴客」那一段）、`feast_stage.py`（契約測試擺局面） |

**認領的欄位**（3.5，留在原地）：`PlayerState.feasting`、`feasts_paid`（換季跟著新角色重來）；`WorldState.feasts`、`feast_seq`（這一季的宴席）；`Config.figure_life.feasts`、`feast_*`。`models.py` 序章不出現的前綴 `feast:join:`。
**世界層的格**（core_world：全部拆包第 25 批）：散席（季的推進；原本 `world.py` 直接叫 `feasts.settle`）是世界層 `step` 的 `feast` 那一格（`__init__.py` 的 `world()` → `rules.world_step`；夾在人物行事與盤算之間，先後在核心的 `WORLD_ORDER`；不問 `enabled`，同原位「開關關著也照散」）。
**世界層 `life` 那一格**（core_world2：全部拆包第 40 批）：設宴（原本 `figure_life.tick` 每一輪每一位對話人物直接叫 `feasts.maybe_open`）是世界層 `life` 的 `feast` 那一格（`__init__.py` 的 `world()` → `rules.maybe_open`；`figure_life.tick` 一輪取一次掛鉤，每一位對話人物先設宴、再求援，一位一位穿插，先後在核心的 `WORLD_ORDER`；包沒登記時不跑）。宴席「讀」的那一半（`on`、`find`、`is_open`、`open_feasts`、`hosting`、`toasted`、`_key`）搬到核心的 `tianxia/core/feast_base.py`，`rules.py` 照原名 re-export 同一個物件；`figure_life`（共用規則層）與 `letters.py` 邀宴（經 `figure_life.feast_invites`）改讀它，不再 import 這一包。
**還沒接掛鉤的（過渡）**：`main_view` 的 `free_text`／`free_op` 叫 `Game.feast_*`（三段式 `feast_text` 第 69 批進了 `routes.py`，見最後一段）；`Game.scene_text` 坐在席上的場景卡全部拆包第 11 批（核心收接縫）換成 `scene` 接縫掛鉤（`_own_scene_text` 擂台之後那一行，不問 `enabled`；`__init__.py` 的 `scene` 叫 `actions.scene`）。`rules.py` import `seal_acts`（第 51 批留原名收進共用規則層，行尾改註「共用規則層」，不算過渡；全部拆包第 51 批合完重印 0 處，第 40 批合完 1 處，原本 2 處：`figure_life` 第 40 批、`renown` 全部拆包第 15 批登記進共用規則層）。

**鎖外工作**（全部拆包第 69 批；原本寫在 `server.py`，計畫 `docs/superpowers/plans/2026-11-06-伺服器分包-第69批.md`）：新開的 `routes.py`（沒有路由，`routes` 掛鉤照舊回 None）：`feast_text`（`/api/do/feast_text`，`outlock` 掛鉤；殼留一行包裝）。`same_behavior` 的 `relay` 軌 selftest 改 `fallback=feasts.DEFAULT_SCORE` 那一句（全檔要剛好一處），不要拆行或改名。A、C 段照舊經 `Game` 的委派（假人走同一批、測試換 `Game.xxx` 打得到），模型呼叫絕不進鎖；殼的東西一律 `shell.<名字>` 當下讀，函式名不改（`tests/server/test_server.py` 的 `_users_in_server` 掃各包 `routes.py` 認這些名字，參數要叫 `shell`、不要先存成變數）；開執行緒寫 `shell.threading.Thread`、`shell.traceback`，不在包裡 `import threading`（`zhuan` 軌換的是殼上那個）。另外要跑的（`test_for` 挑不到）：`tests/server/test_server.py`、`tests/arts/test_in_lock_model_timeout.py`、`tests/server/test_outlock.py`。
