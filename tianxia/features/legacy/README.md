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
**旗標**：門路是玩家旗標 `legacy_<zheng|xie|luck>_<n>`（`LegacyRules.tiers`），每次換季照新的值重立（掉下去的拿掉）；內容用條件的 `flags_all` 讀。每一道開什麼見下面「九道門路」。
**量表**：`scripts/measure_legacy.py`（只算真人；讀一份資料庫裡每個角色「此刻換季的話」會拿到多少、九成位對齊的建議權重；`--demo` 看三種人連玩幾季的走向）。
**畫面**（企劃者 2026-11-04「要有真的傳承、識海的感覺」）：狀態列展開名號時一行入口（`web/app.js` 的 `legacyHtml`），按了打開整頁的傳承（`legacyPageHtml`，`S.legacy = "main"`：月夜山影、三卷墨水到門就蓋朱印、每項三片竹簡＝門路，按一片看長句）與識海（`S.legacy = "shihai"`：深海、封印符紙、時境悟三道封印、破封、這一季要沉下去的那一份）。讀 `main.legacy`（`actions.status`：values、gains、tracks、shihai）；還沒結算過、身上也沒有神品的人不畫。樣子在 `web/legacy.css`，測試 `tests/test_legacy_web.py`。圖（水墨背景、符紙、卷軸、竹簡）等企劃者給，放 `web/img/legacy/`。
**九道門路**（Joy 11/4「照建議」；門檻 5、10、20【草】；`Config.legacy.doors` 寫哪一樣看哪一個旗標，判斷一律走 `renown.legacy_door`，開關關著一律是假）：
- 正氣：① 潁川書院不看惡名（`content/events/sects.json` 的 `yingchuan_join` 條件 `any_of` 讀 `legacy_zheng_1`）、正派武學第一段肯教（`library.learn_problem` 走 `renown.open_to("lessons")`）；② 第一段的俠選項不看路與段（`Game.options` 走 `renown.open_to("choices")`）；③ 敬俠的人物換季那一刻起始好感 +`regard_bonus`（10）。
- 邪氣：① 寇一路第一段的武學肯教（綠林門路）；② 第一段的寇選項；③ 喜狠的人物起始好感 +10。
- 機緣：① 頓悟沒中再擲一次（`epiphany.roll`）；② 奇遇的比重再乘 1 + `qiyu_boost`（0.5；`events.qiyu_multiplier`）；③ 長篇奇事沒中再擲一次（`storyline.roll_start`）。
- 門路只開到 `door_tier`（1）段；官府通緝、黑市、醫館打折照舊只看名聲（`renown.meets`）。
**權重**（Joy 11/4）：tasks 40、merit 0.1、fame 1、relations 1（正式站 60 個真人的九成位對齊），good、evil 1。
