# 移動 `tianxia/features/travel/`

- **做什麼**：移動（全部拆包第 47 批「移動一」）的一半：**選單**（站著的「前往 相鄰地點」，照主畫面選的走法〔步行、疾行；舊的趕路只認得、不再給〕寫時間與體力、體力不夠灰掉）、**路上那串**（折返、路上小事三樣：邊走邊想、沿途打聽、路邊採集；做過的灰掉、收穫每個遊戲日有上限）、**路上見聞**（抵達一站時抽一則）、**喊停**、**安排前往**（大地圖的按鈕，`Game.travel`／`travel_refusal`）、`POST /api/travel`。**出發（`_depart`）與抵達（`_arrive`、`_arrivals`）、結伴同行、前往的補算是第 48 批（移動二），還在 `Game`**，這一包經 `ctx` 叫、位置一個都不動。
- **導覽**：`docs/guide/行動與地盤.md` 的「移動」那一條。
- **設計稿**：都沒有版本號（手冊之前的稿）——地圖擴充設計 `docs/superpowers/specs/2026-10-03-地圖擴充與移動-design.md` 3.2、3.3（出發、喊停）；路上設計 `docs/superpowers/specs/2026-10-03-路上-design.md` 第三～五節（折返、路上小事、路上見聞；企劃者 2026-10-03 同一天拍板）、第四節的每天收穫上限（企劃者 2026-10-03）；計畫 `docs/superpowers/plans/2026-11-06-移動包-第1批.md`；搬包照手冊 `docs/superpowers/specs/2026-10-30-開發模式-design.md` 3.1～3.11、第十五節與總表 `docs/superpowers/plans/2026-10-31-全部拆包-總表.md` 第 47 列。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`TravelFeature`）：`enabled`＝一律開著（`choose`、`bot_pick` 原位本來就不看開關）、`prefix`＝`move`、`road`（`choose` 回 `Outcome`：標題先算，前往寫「前往 <地點>」、折返跟前往同一個標題、路上小事寫它自己的名字）、`bot_always`＝`road:`、`verbs()`＝`halt`（`run`＝`go_actions.halt`、`title`＝「喊停」）、`routes` |
| `menu.py` | 原本 `Game._move_option`、`_back_way`、`_back_option`、`_road_task_options`、`set_move_mode`；`Game` 留 4 個一行委派（`_back_way` 只有包自己叫，沒有委派） |
| `road_actions.py` | 原本 `Game._move`、`_road`、`_road_ends`、`_road_rewards_used`、`_road_reward_due`、`_count_road_reward`、`_road_reopen`、`_road_think`、`_road_ask`、`_road_gather`、`_road_sight`；`Game` 留 3 個一行委派（`_road_reward_due`、`_count_road_reward` 給第 48 批的 `_share_road`，`_road_sight` 給 `_arrivals`） |
| `go_actions.py` | 原本 `Game._halt`、`travel`、`travel_refusal`；`Game` 留 `travel`、`travel_refusal` 兩個一行委派 |
| `bots.py` | 假人的分數（原 `bot_policy.score` 的 `move:` 那一段）：要 `profile` 與 `bot_policy` 的七個私有函式，經 `from tianxia import bot_policy` 延後 import（過渡） |
| `routes.py` | `POST /api/travel`（原 `server.py` 的 `api_travel`；回的鍵與順序不變：`main`、`arrived`，走不成時再加 `reason`、`map`） |
| `tests/` | `test_travel_smoke.py`、`test_travel_bots.py`、`test_travel_routes.py`（新寫的；移動的規則測試散在混合檔，見下） |

**認領的欄位**（3.5，留在原地）：`PlayerState.leg_actions`（這一段做過的路上小事）、`recent_sights`（最近看過的見聞）、`road_rewards_today`（今天路上小事／見聞各拿過幾次收穫）；換季照 `_reset_player_for_new_season` 重來，`carried = ()`。`journey` 每一包都讀，不認領；`tagalong` 是第 48 批。
**共用的字**：`ROAD_TASKS`、`ROAD_REWARD_TASKS` 在核心 `core/services.py`（`# travel`；`_share_road`、換季重設也讀），`engine` 照舊 import。
**選單順序（不能改成 `Feature.options`）**：站著的時候「前往」夾在求見、招募之後、拜師之前（`_everyday_options`）；路上那串是「在路上（`act:on_road`）→ 分道揚鑣〔結伴時，其餘只剩小事〕→ 折返 → 帶路的路上一句 → 喊停 → 路上小事 → 擂台」（`_options`）。`Game` 原位那幾行只叫委派（`GAME_DELEGATE_CALLERS` 寫理由），選單的順序算行為。
**接縫在原位的位置不能動**（位置就是行為）：`sync`、`advance` 的 `_arrivals()`；`_arrivals` 迴圈中途的 `_ambush_check` → `_arrive`〔`publish("arrive")`，糧車先於懸賞護送，由 `BUS_ORDER` 鎖住〕→ 騎乘飽足 → `_road_sight`（`Game._road_sight` 一行委派，第 48 批才拿掉）。
**舊的趕路**照舊認得：`atlas.MODE_NAMES`、`TIME_SHARE`、`TravelMode` 不動；`go_actions.halt` 的 `if j.mode == "hurry"` 那一句、`menu.road_task_options` 的 `j.mode == "dash"` 都逐字搬；`travel_refusal` 對 `hurry` 回「無法安排前往這裡」（`mode not in atlas.MODES`）。
**經 Game 的委派叫自己**：`go_actions.travel` 開頭問 `ctx.travel_refusal(...)`（不是直接叫同檔的函式），因為 `tests/gear/test_weapons.py`、`test_armor.py`、`test_mounts.py` 換掉 `game.travel_refusal` 來繞過檢查、直接測 `_depart` 的防線。
**過渡**（全部拆包第 40 批合完重印 6 處，原本 7 處）：`atlas`（輿圖：路程、走法、折返的路、所在大區，第 50 批前後）、`bots.py` 延後 import `bot`、`bot_policy`（假人的挑法還在舊模組）。`ranks`（疾行送到糧車記貢獻；`go_actions.py` 跟 `atlas` 同一行）第 40 批收進共用規則層，不算過渡。`bot_policy.score` 在 `features_core.bot_pick` 之前直接問 `bots.score(game, option, profile)`（測試傳的 `profile` 不一定是 `game.state.player.bot`，掛鉤沒有 `profile`），這是「舊模組 → 包」一處。
**審查守的**：`bot.py` 的 `bot_always` 只拿掉 `road:` 一個字面（改由包宣告）；`bot_policy.take_turn` 的 `("road:", "defect:", …)` 字面不動（同層的 `invite:`、`errand:` 也是字面）。`tests/gear/test_weapons.py` 的 `game._move("lake")` 改成 `road_actions.move(game, "lake")`（`_move` 沒有委派；只改叫法，斷言不動）。`tests/core/test_contract_features.py` 的 `CORE_IDS` 換掉兩個 id、加 `MENU_BY_CORE`（選單由核心原位排、包一律開著，「關著的包選單上沒有它的前綴」那一行對這一包不查）。
**另外要跑的混合檔**（移動的用法散在別人的檔裡，這一輪不拆〔抽函式要動 fixture，行為風險大於好處〕；改包任一檔時 `test_for` 只挑到包的 tests 與核心契約，要靠這一張清單）：
- `tests/core/test_engine.py`（約 155 處，有 106 條帶路上、喊停、折返等字眼）、`tests/server/test_server.py`（39 處，含 `/api/travel`）、`tests/gear/test_mounts.py`（27）、`tests/figures/test_day_scale.py`（23，收穫上限）、`tests/core/test_prologue.py`（13）、`tests/gear/test_weapons.py`、`tests/gear/test_armor.py`、`tests/bots/test_bot_policy.py`。
- 一起跑：`pytest tianxia/features/travel/tests tests/core/test_engine.py tests/server/test_server.py tests/gear/test_mounts.py tests/figures/test_day_scale.py tests/core/test_prologue.py tests/gear/test_weapons.py tests/gear/test_armor.py tests/bots/test_bot_policy.py -n 4`；證明一個字不變：`python scripts/same_behavior.py compare --tracks travel,herald,stamina`。
