# 閉關 `tianxia/features/seclusion/`

- **做什麼**：修練頁按「閉關」鈕：1～12 個世界小時不動（`busy_until`），氣血回復加倍；滿時自然出關或按 `act:break` 提早出關，照小時數給心得（`Config.seclusion_xinde_per_hour` × (1＋悟性／20) × 寶物「閉關心得」）。出關那一刻記 `seclusion_done`（天時地利的「心靜」：出關之後一陣子開爐，`fusion.setting_points`）。序章裡不閉關（`prologue.seclude_problem`）。
- **導覽**：`docs/guide/行動與地盤.md` 的「閉關」那一段（PM 補導覽的標題，這一批沒動 `docs/guide/`）。
- **設計稿**：武學與成長設計（`docs/superpowers/specs/2026-10-05-武學與成長-design.md` 心得的來源，沒有版本號）；數字在 `Config.seclusion_xinde_per_hour`。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`SeclusionFeature`）：沒有前綴、沒有選項；`verbs()`＝`Verb("break")`（按下去回 `actions.finish` 的句子；標題不給，`Game._action_title` 走預設的「提前出關」；不問 `enabled`） |
| `actions.py` | 原本 `Game` 上的 `seclusion_refusal`、`seclude`、`_finish_seclusion`；`Game` 留三個一行委派（server 的修練頁、`_advance_player_local` 的自然出關、測試叫） |
| `tests/` | `test_seclusion_smoke.py` |

**認領的欄位**（3.5，留在原地）：`PlayerState.seclusion_start`、`seclusion_done`（換季照 `_reset_player_for_new_season` 重來）；`Config.seclusion_xinde_per_hour`。`busy_until` 是核心的（遊歷、出陣也用），不認領。`fusion.py` 讀 `seclusion_done`（只讀狀態）。
**接縫**：`local` 的 `seclusion` 那一格（第 55 批；體力回復之後、福緣之前，位置就是行為）；閉關中的選單（`_everyday_options`：`act:break` 與擂台入口併成一串）留在核心，總表第 57 批才碰。假人不閉關，沒有 `bots.py`。
**另外要跑的混合檔**（閉關散在這些檔裡，這一輪不拆；數字是 `seclude`／`_finish_seclusion`／`seclusion_refusal` 出現的次數）：`tests/core/test_engine.py`（7）、`tests/core/test_prologue.py`（5）、`tests/core/test_journal.py`（3）、`tests/ranger/test_bounties.py`（3）、`tests/gear/test_treasures.py`（2）、`tests/figures/test_foreshadow.py`（2）、`tests/gear/test_mounts.py`（1）、`tests/bots/test_stamina_refill.py`（1）；網頁那一頭 `tests/web/test_prologue_web.py` 等（打 `/api/do/seclude`，這一批沒動 `web/`）。改閉關任一檔時另外跑它們。

**補算與換季的格**（core_seams，全部拆包第 55 批；順序在 `core/features.py` 的 `SEAM_ORDER`，都不問 `enabled`，叫到才照模組屬性或 `ctx` 找）：`local` 的 `seclusion`（`actions.finish_due`，原位的判斷搬過來；`Game._finish_seclusion` 留給測試）。

**第 56 批（選單收接縫，核心批）**：`busy/seclusion`（`act:break` 那一顆）是這一包登記的格；先後在 `core/features.py` 的 `MENU_ORDER`；上面寫「留委派」「原位」的以這一句為準。
