# 傳承 `tianxia/features/legacy/`

- **做什麼**：正氣、邪氣、機緣三項只在換季那一刻照上一季的傳結算一次（季中不動）；識海——這一季自己選一份神品意境，下一季帶著、封著，解封才回到身上。
- **導覽**：`docs/guide/大勢人物與賽季.md` 的「傳承（功能包）」那一節。
- **設計稿**：`docs/superpowers/specs/2026-11-04-屬性與跨季-架構方向v2.md` 第六、七節（實作順序第十節的第 ③ 階段）；數字在 `Config.legacy`（`LegacyRules`），全是【草】。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`LegacyFeature`）：`enabled`＝`Config.legacy.enabled`（預設關）、`options`（識海三顆）、`choose`（`legacy:`）、`status`（`main.legacy`）、`on_season_start`（結算）、`bot_pick`、`bot_always`＝`legacy:drop` |
| `rules.py` | 純規則：評比的六樣（`inputs`）、增量（`gains`：平方根或 log）、結算（`settle`：舊的留七成再加）、門路（`reached`）、季初那一則的字 |
| `actions.py` | 換季結算、識海的選項與動作（放進、不留、解封、撞名改名）、江湖畫面的狀態 |
| `bots.py` | 假人的分數：放進識海 30、解封 40、撞名挑第一個候選 50；不留了不按 |
| `tests/` | `test_legacy.py`、`test_legacy_smoke.py`、`legacy_kit.py`（有神品的局面）、`legacy_stage.py`（契約測試擺局面） |

**認領的欄位**（3.5）：`PlayerState.legacy`（`LegacyBook`、`ShihaiSeal`；`None` 不寫進存檔，在 `state.QUIET_DEFAULTS`）。換季照帶（`carried`）：照帶本身寫在 `Game._reset_player_for_new_season`、不看開關（同出陣那兩格）；結算在 `on_season_start`，只在開關開著時。`Config.legacy`。
**旗標**：門路是玩家旗標 `legacy_<zheng|xie|luck>_<n>`（`LegacyRules.tiers`），每次換季照新的值重立（掉下去的拿掉）；內容用條件的 `flags_all` 讀。現在還沒有內容讀它：每一道門路開什麼，第 ③ 階段量完給 Joy 挑（設計稿第十三節第 6 題）。
**量表**：`scripts/measure_legacy.py`（讀一份資料庫裡每個角色「此刻換季的話」會拿到多少；`--demo` 看三種人連玩幾季的走向）。
**畫面**：狀態列展開名號時多一行「傳承　正氣 N（+n）　邪氣 N　機緣 N」，底下寫開了的門路與識海封著的那一份（`web/app.js` 的 `legacyHtml`，讀 `main.legacy`；還沒結算過的人不畫）。
**機緣多擲一次**：立了 `Config.legacy.luck_reroll_flag`（預設 `legacy_luck_1`）的人，頓悟（`epiphany.roll`）沒中再擲一次；開關關著不多擲、不動亂數。
