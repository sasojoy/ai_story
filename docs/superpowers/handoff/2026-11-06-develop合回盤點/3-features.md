# develop 合回主幹盤點 3：develop 新功能的落點

> 11/06 唯讀盤點（工作流程 `wf_4c64148d-820`），量的時候主幹 `0176753d`（檢查者另對 `3e2271a4`）、develop `99f6a79b`。第 27、50 批之後主幹是 `f7b17ed7`，行號開工前重量。

# develop 新功能拆進主幹的地圖（11/06）

基準：`origin/split/trunk` 0176753d、`origin/develop` 99f6a79b、錨點 17c5199d。全程只讀，沒有改檔、沒跑測試、沒碰分支。行號是那一版的行號，標「推測」的是沒驗過的。

## 〇、結論

- **要「拆進包」的實際量不大。** 9 個新 `Game` 方法共約 107 行。其中只有 6 個（約 80 行）該離開 `Game`，另外 3 個本來就屬於核心彙整。
- **工作量在合併本身。** develop 的屬性 v2 散在約 60 個檔，其中 9 個方法、8 個舊模組、11 個測試檔在主幹上已經換了位置。
- **建議分段：第 0 段合併並照新位置搬（單獨、最先做），之後 A～D 四段可以並行，E 可選。** 細節在第六節。

## 一、先要知道的四件事（影響整個拆法）

**1. 舊軌在 week7、season21 會卡在開季準備卡，比對等於空驗。**
- develop 6cb80d62 在 `content/profiles/week7.json`、`season21.json` 打開了 `attributes.v2` 和 `legacy`。`same_behavior` 每一軌照設定跑 season21、week7、test 三種（same_behavior.py:49、:107-126），所以合併之後每一軌在 week7、season21 都是五項屬性的季。
- 情境的玩家是 `/api/register` 加 `skip_tutorial`（same_behavior.py:546-550、:714-716）。伺服器建角色時走序章（`prologue=True`，develop server.py:2584）。只有不走序章的建角才會補預設配比（develop engine.py:520-522），`skip_tutorial` 不補（develop guide/actions.py:506）。
- 結果 `growth_preset` 是 `None`，`_season_prep`（develop engine.py:8835）會接管整個選單。之後每一步都會被擋，兩邊一樣擋，比對永遠「一樣」，等於空驗。
- 第 0 段要先在 `Scenario` 補一步：開季準備卡出現時照預設配比按 `/api/do/growth`，識海按 `legacy:skip`。這一步兩個根都會跑，不影響比對公平。

**2. 拿 develop 當 base 跑，至少有一軌起不來。**
- `RoadmateScenario.invite` 寫死 `from tianxia.features.peers import invites`（same_behavior.py:17432），develop 上沒有這一包。
- 推測還有別的軌只在主幹上起得來。第 0 段第一步先拿 develop 根跑一次 selftest，看每一軌起不起得來。

**3. 第 27 批（玉璽）要先落地。**
develop 改了 `_seal_challenge`、`_seal_spectators`、`_seal_side_of`、`seal_gamble`、`admin_seal_duel`（約 8 行），還有 `seal_duel.py`（+15/-3）。這些都是 27 要搬的，合併時改寫進玉璽包。第 50 批（輿圖）跟 develop 沒有交集（develop 沒動 atlas、mapview 這一類）。

**4. 主幹完全沒動 `web/`。**
develop 的網頁改動（app.js +373、main.js +252、admin.js、style.css、mall.js）照貼不會撞。要搬的只有規矩要求切檔的那幾塊（傳承、招募的畫面）。

## 二、逐項地圖

### 2.1 `tianxia/attrset.py`（250 行，新的頂層模組）
- **做什麼**：五項屬性的季。開關與季章（`on`）、配比、送點、舊鍵對應（`v1_value`、`legacy`）、魅力、對手照等級長屬性、歷練（`grant_event`）。
- **落點**：核心本體，照 develop 加進 `tianxia/core/__init__.py` 的 `MODULES`。
  - 理由：它只 import `models`、`state`，而核心的 `team.py`、`rules.py` 在模組層 import 它。
  - 共用規則層也合規矩，但它的測試已經放在 `tests/core`。
  - 主幹的 `MODULES` 多了 `world`、`log_archive`、`step`、`weekcard`，會撞，解法是加上 `"attrset"`。
  - 稽核寫查不到 PM 認定，要補。
- **欄位**：`growth_preset`、`growth_custom`、`attr_event`、`attr_alloc`（develop state.py:828-831）、`WorldState.attrs_v2`。**建議不給任何包認領**：
  - 核心的 `rules.apply_effect` 經 `grant_event` 寫 `attr_event`；
  - 如果修練包認領它，主幹邊界測試 `test_the_effect_slots_and_the_defection_clearing_touch_no_package_field` 推測會紅。
- **讀它的包**：修練、有所感、鐵匠鋪、單挑、決戰、新手引導、招募、出陣；共用層的 `insight_fx`、`library`、`rise`、`roster`、`renown`。都合規矩。
- **測試**：`tests/core/test_attrset.py`（467 行）、`tests/core/test_attributes.py`（136 行）、`tests/kit/grade_kit.py`。
- **same_behavior**：沒有軌點名它。第一節第 1 點補好之後，week7、season21 的每一軌都會順帶走到 `team.v1_stat` 這一類路徑。

### 2.2 屬性 v2 的 `Game` 方法

| 方法（develop engine.py） | 做什麼 | 落點 |
|---|---|---|
| `_allocate_v2`（:8820，14 行） | 五項屬性的季的配點 | 修練包 `actions.py`，接在 `allocate_stat`（主幹 cultivation/actions.py:285）最前面。`Game` 不留它（只有 `allocate_stat` 叫），develop 邊界測試新加的那條 `("_allocate_v2","_note_action")` 拿掉 |
| `pick_growth`（:8857，18 行） | 挑這一季的成長配比 | 修練包 `actions.pick_growth`（配點在那一包，總表第二節）。`Game` 留一行委派：server 的 `/api/do/growth`（develop server.py:2875）、bot.py、新手引導 `ctx.pick_growth`、核心 `choose` 都在叫 |
| `_season_prep`（:8835，11 行） | 開季準備卡（`options()` 彙整的一段） | 核心 |
| `season_prep_view`（:8847，9 行） | 給 `main.prep` 的那一份 | 核心 |
| `_attr_rows`（:12065，7 行） | `status_data` 的屬性列 | 核心。`status_data` 鍵的順序算行為，不能改成包的 `status` |

- **核心那三個不拆的理由**：
  - 如果配比那一步改成修練包的 `prep` 掛鉤，`season_prep_view` 的 `steps`（"feature" 那一格看 `features_core.prep` 是不是 None）會變，`main.prep` 的輸出就跟 develop 不一樣。
- **`growth:` 前綴**：留在核心原位，就是 develop engine.py:2499 那 3 行，叫 `pick_growth` 委派。
  - 它在建紀錄（Draft）之前分派，`pick_growth` 自己寫一則紀錄。
  - 改走包的 `choose` 掛鉤會多一則紀錄、標題也不同，行為就變了。
  - 前綴不給任何包，契約測試才不會紅。
  - 邊界測試要加 `("choose","pick_growth")`；`GROWTH_PREFIX`、`GROWTH_LOCKED`、`GROWTH_CUSTOM_ASK` 留在 engine（bot.py 從 engine import）。
- **假人碰得到**：
  - bot.py 的 `growth_key`、`allocate_points` 的 v2 那一支、`pick()` 的 `GROWTH_PREFIX`；
  - bot_policy 的 `kind == "growth"`（`GROWTH_SCORE` 100）；
  - 換季之後 `growth_preset` 歸零，假人也會碰到開季準備卡。
- **測試**：`tests/core/test_attrset.py`（`pick_growth`、`_season_prep`、`season_prep_view`）、`tests/web/test_season_prep_web.py`、`features/legacy/tests/test_legacy.py:223`、`features/guide/tests/test_guide_smoke.py`、`tests/figures/test_checkin.py`（`growth:`）。
- **same_behavior**：`allocate_stat` 只有 arts 軌碰一次（same_behavior.py:9166）；`pick_growth`、`growth:`、`status_data` 的 `growth`／`lilian` 沒有軌點名。
  - **新軌 `growth`** 要走：v2 的季、序章外建的真人 → 開季準備卡 → `growth:<預設>` → `growth:custom`（只回一句）→ `/api/do/growth` 自己配（合計對、不對、每項超過 `custom_max`）→ 已鎖再挑（`GROWTH_LOCKED`）→ 升到 `bonus_every` 拿點 → `allocate_stat` 走 v2 → 換季後準備卡再出現 → 假人照名號挑。

### 2.3 事件歷練（2812e126、f8173840）
- **做什麼**：五項屬性的季，事件給的屬性記成歷練，每季上限 60，滿了化成心得；戰報附註「（歷練 N／M）」。
- **落點**：全在核心與共用層，不必拆。`attrset.grant_event`（核心）、`rules.py` 的效果（核心）、`battlelog.py`（共用層）、`models` 的 `event_cap`、新手引導的 `h_lilian`（包裡，原位改）、網頁的 `lilianHtml`（狀態列，殼）。
- **欄位**：`attr_event`（不認領，見 2.1）。
- **假人**：碰得到（假人也做事件）。
- **same_behavior**：events 軌在 week7、season21 會順帶走到（推測，前提是第一節第 1 點補好）。新軌 `growth` 可以加一段把歷練推到上限。

### 2.4 屬性 v2 散在已搬模組裡的改動（對抗式、魅力、內功、擂台閃避、歷史武將不同行）
全是第 0 段照新位置改，不新開包。對照表在第三、四節。

### 2.5 `place_state.py`（186 行）＋ `place_state_view` ＋ 上線邸報
- **做什麼**：地點會變樣（太平、戰火、淪陷、饑荒、重建），影響店價、馬市、事件條件、人物行程。上線邸報把「你不在的時候」改寫成三段。
- **落點**：
  - `place_state.py`：共用規則層，照 develop core/registry.py:105 的 `SHARED` 那一條。它只 import `calendar`、`deeds`、`models`、`state`、`world_state`，邊界測試綠。讀它的 `rules`（核心，函式裡 import）、`conquest`、`territory`、`timetable`、`plans`、`figure_life`、`mounts`（都是共用層）、新手引導包，都合規矩。缺 PM 認定（稽核 3.7）。
  - `place_state_view`（develop engine.py:3385，6 行）：**建議留核心**，跟同樣直接讀 `place_state.view` 的 `location_text`、`scene_art`（主幹 engine.py:6334、:6340，核心）放一起。另一個選擇是照稽核放大勢人物包 `plan_actions.py`，跟 `place_deeds_view`（主幹 :2205 的委派、plan_actions.py:46）並排，要多一個委派。
  - 上線邸報：`rumor_view.gazette_lines`（共用層）、`journal.GAZETTE`（核心）、`_deliver_away`（主幹 engine.py:935，核心）。原位改。
- **欄位**：`WorldState.places`、`PlaceMark`（核心 state.py），`Condition.place_state`／`place_state_none`、`PlanTuning` 九欄、`TimetableOutcome.places`（models）。
- **前綴與路由**：沒有；server 的 `main.place_state`（develop server.py:2205）。
- **假人**：間接碰到（盤算、時刻表、地盤易手會改地點的樣子）。
- **測試**：`tests/figures/test_place_state.py`、`tests/figures/test_rumor_layers.py`、`tests/arts/test_hints.py:1461`。稽核 3.12 指出它們用了不帶設定的 `real_content()`。
- **same_behavior**：沒有點名。world、landturn、figact 這幾軌經 `/api/main` 整份 emit，推測會順帶看到 `place_state` 鍵與地名底下那一句。
  - **新軌 `places`** 要走：盤算結果讓一處變戰火 → 到那裡看 `location_text`、`scene_art`、`/api/main` → 馬市不開、店價、`h_place` 提示 → 時刻表的 `places` 推成饑荒、淪陷 → 收復變重建 → 時間過了回太平 → 離線超過 `away_hours` 再上線看邸報。

### 2.6 `figures_here_view`、`_figure_side_name`、`talk_view`（介面重整，4de6fb28）

| 方法（develop engine.py） | 做什麼 | 落點 |
|---|---|---|
| `figures_here_view`（:2780，29 行） | 江湖頁「此地人物」那一排 | 交友求見包 `view.py`。它叫的 `_talkable`、`_why_not_talk`、`_social_plan`、`_audience_options` 在主幹上本體都在這一包（socialize/view.py:25、:30、:53，menus），`_figures_here` 在服務清單上。`Game` 留委派給 server |
| `talk_view`（:2816，8 行） | 對話框頂上那一份 | 人物情誼包 `talk_actions.py`（`affinity_text` 在 :243）。它讀的 `pending_companion` 是人物情誼包認領的欄位。`Game` 留委派 |
| `_figure_side_name`（:2810，5 行） | 人物站哪一邊（純查內容） | 共用層 `figures.py`，例如 `side_name(content, fid)`。上面兩包都要用；放在任一包裡另一包就得 import 它，違規 |

- `figures_here_view` 只產出大勢人物包的 id 字串（`aid:guard`、`aid:rally`、`act:challenge`），不 import 那一包。
- **欄位**：讀 `affinities`（核心）、`pending_companion`（人物情誼）、`journey`、`pending_event`。不寫。
- **路由**：server 的 `main.figures_here`、`main.talk`（develop server.py:2166-2167；`figure_face` :134 留殼）。
- **假人**：碰不到（只有畫面讀）。
- **測試**：只有 `tests/web/test_revamp_web.py:44-67`，沒有引擎層的測試。
- **same_behavior**：沒有點名；經 `/api/main` 整份 emit 會順帶看到（推測）。
  - **新軌 `here`** 要走：一位人物、兩位以上（求見名單）、`precise` 開與關、閉門不見、名聲不夠、序章中、在路上、事件中、對話中（`talk_view`）、季收了。

### 2.7 `talk_log.py`（119 行，往來紀錄）
- **做什麼**：跟大勢人物說過的每一句，存在資料庫旁邊的小檔 `<db>-talk.sqlite`，兩季以前的封存。
- **落點**：人物情誼包 `features/companions/talk_log.py`，舊名 `tianxia/talk_log.py` 留成別名（測試照舊 import）。
  - 理由：它讀 `used_dialogue_options`、`dialogue_history`，這兩欄是人物情誼包認領的。
  - `/api/talk_log`（develop server.py:3136，19 行）搬進 `companions/routes.py`，跟 `/api/figure` 放一起。
  - 動作前後的記錄（server.py:479-481 的 `act`、`_log_talk` :863、`talk_store` :853）是殼的鎖外包裝，沒有對應的掛鉤（`after_action` 拿不到動作前的那一份），留在 server，改 import 包。
- **欄位**：不進存檔。
- **假人**：碰不到。
- **測試**：`tests/server/test_talk_log.py`，跟著搬進 `features/companions/tests/`。
- **same_behavior**：引擎層看不到（小檔不在角色存檔裡）。要照純搬批的做法，兩台真伺服器跑同一串 HTTP（談兩輪、翻頁、上一季），逐位元組比回應與 `-talk.sqlite`。

### 2.8 傳承包 `features/legacy/`（已經是包；對主幹規矩）
- **做什麼**：正氣、邪氣、機緣換季時結算一次；九道門路；識海帶一份神品意境到下一季。
- **邊界測試會不會紅**：
  - import：`insight_fx`、`insights`、`renown`（主幹都在共用層）、`naming`、`state`、`models`、`core.*`。綠。
  - 叫 `Game`：只碰 `ctx.state`、`content`、`world`、`_write`，都在服務清單上。綠。
  - 舊模組 → 包：沒有。門路是旗標（核心），共用層的 `renown.legacy_door` 只讀旗標和 `Config.legacy`（develop renown.py:114）。乾淨。
- **要補的**：
  1. 主幹 `core/features.py` 要加 `prep` 掛鉤。develop 的寫法是表一行、Protocol、`Feature` 預設、彙整，共 13 行。這是改核心，稽核查不到 PM 同意的紀錄，要補一筆認定。
  2. `FEATURES` 接在 `gear` 後面。
     - 主幹上實作 `options` 的只有宴客，實作 `status` 的只有商城和形象，所以排最後跟 develop 的相對順序一樣。
     - `on_season_start` 主幹多了玩家互動包排在前面。推測順序一樣，因為原本那一段就寫在 `features_core.on_season_start` 之前，要驗。
  3. 網頁違反 G9（稽核 3.10）：
     - 傳承頁在 develop app.js:824-947，約 124 行，含 `legacyHtml`、`lgScrollSvg`、`legacyMainHtml`、`legacyShihaiHtml`、`legacyOfferOpen`、`legacyPageHtml`；
     - 另有四條按鈕處理在 :6315-6318，識海的開季那一步 `prepShihaiHtml` 在 :1058；
     - 切成 `web/legacy.js`，`web` 宣告改成 `("legacy.js","legacy.css")`，`index.html` 在 `app.js` 之前加 script，`webharness.APP_FILES` 也加。
  4. README 寫 `bot_always＝legacy:drop`，程式是 `("legacy:skip",)`（legacy/__init__.py:18）。照程式改。
  5. `legacy_stage.py` 只給了神品，選項要換季才有，契約測試等於空驗（稽核 3.12）。要擺出「換季後有 offers」「封著、條件到了」兩種局面。
  6. 契約測試沒驗 `prep`：
     - develop test_contract_features.py:67 只收 `options`、`menu`、店面；
     - 要加：`prep` 的 id 帶前綴、包關著時 `prep` 回 None。
  7. 主幹的 `test_a_new_season_keeps_only_what_the_package_carries` 要帶上 develop 加的 `c.config.legacy.enabled = False`（develop :288）。`test_test_for` 的 `STAGE_PACKAGES` 加 `legacy`、`hire`。
  8. `rules.inputs(old)` 讀了別包認領的欄位：`errands`（人物情誼）、`showdowns`、`top_merits`（決戰）、`bounties_done`（懸賞，第 45 批才成包）。邊界測試不掃這個方向，不會紅；照 3.4 應該經核心查。這一次記成過渡，還是開查詢服務，請 PM 定。
- **門路散在別處的改動**（第 0 段照新位置改）：
  - `epiphany._luck_reroll` → 有所感包 `sense/epiphany.py:161` 的 `roll`；
  - `storyline.roll_start` → 共用層 `story_base.py:160`；
  - `library.learn_problem` → 共用層 `library.py:101`；
  - `events.qiyu_multiplier` → `events.py:144`、:155，舊模組原位；
  - `renown.open_to`（共用層）、核心 `_everyday_options` 那一行；
  - `content/events/sects.json` 的 `yingchuan_join` → 陣營包宣告的內容檔，原位改。
- **欄位**：`PlayerState.legacy`，有 `QUIET_DEFAULTS`，換季帶走。`_reset_player_for_new_season` 那一行照帶（develop engine.py:674）。
- **前綴**：`legacy:seal:<i>`、`legacy:skip`、`legacy:open`、`legacy:name:<i>`。
- **假人**：碰得到（`bots.py`：封第一份 60、解封 40、撞名 50；`skip` 是 `bot_always`）。
- **測試**：`test_legacy.py`（353 行）、`test_legacy_smoke.py`、`test_legacy_web.py`。
- **same_behavior**：沒有點名。換季的軌（`next_season` 出現 42 處）在 week7、season21 會跑到結算，有神品的才出識海（推測）。
  - **新軌 `legacy`** 要走：第一季累積俠寇、名望、情誼、任務 → 換季結算 → 門路旗標 → 潁川書院條件、俠寇第一段選項、正邪武學、頓悟、奇遇、長篇奇事重擲、敬俠起始好感 → 開季準備卡封一份或不帶 → 時間、等級、心得都到了解封 → 撞名改名 → 再換季，舊的留七成。

### 2.9 招募包 `features/hire/`（已經是包；對主幹規矩）
- **做什麼**：五項屬性的季，在酒肆花銀兩招五型一般 NPC 同伴。
- **邊界測試**：
  - import `attrset`（要先進核心，見 2.1）、`roster`（主幹共用層）、`team`、`core.option`；
  - 只碰 `ctx.state`、`content`、`world`。
  - `attrset` 進了 `MODULES` 就綠。
- **要補的**：
  1. 內容檔違反 G8（稽核 3.8）：
     - 現況：`content/hirelings.json` 被併進人物表（develop content.py:190-191），驗證寫在核心的 `content.validate`（:3301）。
     - **改檔名、把驗證搬進包的 `check_content`**：行為不變（只有內容寫錯時錯誤訊息的先後不同），可以做。
     - **拆成獨立的內容欄位、不再併進人物表**：行為會變。酒肆打聽、`roster`、`try_recruit`、`world.get_companion`、`team` 都靠人物表認人；稽核 3.1 的「酒肆打聽答出一般 NPC」就是從這裡來的。這一步不能算在純搬裡，要企劃者定是不是要這樣改。
  2. `hire_stage.py` 只 yield「平常」。契約用的是真實內容 week7，擺得出酒肆的局面，要改。
  3. tests/season/test_real_content.py:532-541 用子程序跑 `make_hirelings.py`，沒標 slow（稽核 3.12）。
  4. `status` 讀酒肆包認領的 `picking_tavern`（hire/__init__.py 的 `status`），跨包讀欄位，不會紅，記成過渡。
  5. 網頁：酒肆裡的招募那幾顆在 develop main.js:2102 一帶，照 G9 應該切成 `web/hire.js`（推測約 20 行）。
- **獨立一包還是併進人物情誼包**：總表把「同伴招募」寫在人物情誼包。**建議照舊獨立**：
  - 它有自己的開關（`Config.hire` 加 `attrset.on`），不碰人物情誼包的欄位；
  - 併進去的話，選單與 `status` 鍵的位置要另外驗，而且會跟 D 段撞同一包。
- **欄位**：沒有 `player_fields`。寫 `stats["silver"]`、`team`（核心）、world 的同伴名冊。
- **前綴**：`hire:<人物 id>`。選項經 `options` 掛鉤（主幹 engine.py:5036：護衛之後、盤算之前）。
- **假人**：碰得到（`BOT_SCORE` 6）。
- **測試**：`test_hire_smoke.py`（3 條）、tests/season/test_real_content.py:523-541。
- **same_behavior**：develop 只改了一行讓 `pick_mate` 跳過一般 NPC（develop same_behavior.py:3327），主幹沒有。酒肆那一軌在 week7 推測會順帶列出招募鈕。
  - **新軌 `hire`** 要走：v2 的季到有酒肆的城 → 列出招募鈕 → 銀兩不夠、名下滿了灰掉 → 招一位（扣銀兩、配武學、入隊）→ 兩人搶同一位（`GONE`）→ 坐進酒肆看 `main.hires` → 魅力打折 → 換季重獲自由 → 假人招。

### 2.10 戰記分享頁（177b2e70、e9f351a7 等 8 筆）
- **做什麼**：戰記一幕一趟；公開頁 `/zhanji/<代碼>` 帶分享預覽；遊戲裡用 iframe 開同一頁。
- **現況**：`tianxia/tale.py`（develop 596 行，+209/-55）、根目錄新檔 `tale_html.py`（156 行；稽核寫成 tianxia 底下，實際在根目錄）、server 的戰記那一段約 170 行（`tale_cover`、`tale_page_view`、`tale_page`，加上原有的 `tale_view`、`tale_round`、`start_tales`……）、`web/tale.css`、決戰包 `rules.py`、`view.py`、`battle_instance`（誰死誰活）。
- **落點**：總表第 52 批的戰記（`tale`）包。
  - `tianxia/tale.py` 搬進包、舊名留別名，名字的衝突就解了。
  - `tale_html.py` 照列傳包放 `zhuan_html.py` 的做法進包。
  - 兩條路由（`/zhanji/{code}`、`/api/tale/{id}`）進 `routes.py`。
- **可以延後**：`tale.py` 在主幹上還是舊模組，develop 的改動第 0 段原位套得上。企劃者要「這一次一併拆」才提前做（E 段）。
- **假人**：碰不到。
- **測試**：`tests/server/test_tale_page.py`、`features/battle/tests/test_battle_tales.py`。
- **same_behavior**：要模型，沒有軌走到。照純搬批做兩台伺服器比 `/zhanji/<code>`、`/api/tale` 的位元組。

### 2.11 已經在包裡的，合併時原包改
- 形象包：絕招示範例句（6320c69d、cc04a404 內容相同）、畫坊十幾筆。主幹沒動形象包。
- 新手引導包：FB-9110 的 11 條提示、v2 序章那一步、`h_place`。主幹 guide/actions.py 也改了 +24/-9，會撞。
- 單挑包：擂台身法閃避 8fbd6500、`pvp_card`。主幹 arena_rules.py +14、duel_actions.py -17，會撞。
- 決戰包：`muster` 的魅力、放手一搏不寫死人。
- 出陣包：`duel_actions` 的 `v1_stat`。
- 走一趟（`web/outing.js`）。

## 三、engine.py 改動對照主幹位置

**主幹上已經是一行委派（9 個，develop 改了約 13 行，要寫進包）：**
- `_recruit_targets` → companions/actions.py:43（`roster.on` 加 world）
- `_explore_weights` → explore/explore_base `explore_weights`
- `challenge_odds`、`_figure_squad`、`_challenge` → figure_acts/challenge.py:73-138（`rise` 加 world、`attrset.figure_squad`、`_take_toll(squad=)`）
- `_finish_seclusion` → seclusion 的 `actions.finish`
- `allocate_stat` → cultivation/actions.py:285（接 v2 那一支）
- `_raid_spoils` → peers 的 `raid_actions.take_spoils`
- `_ambush_spoils` → stamina_plays 的 `ambush_actions.spoils`

**主幹上還是核心本體（15 個，原位套）：**
`new`、`_reset_player_for_new_season`、`_deliver_away`、`_everyday_options`、`choose`、`_battle_role`、`_battle_marks`、`_squad_encounter`、`_take_toll`、`_play_rounds`、`_story_squad`、`_spar_power`、`location_text`、`scene_art`、`status_data`。

**第 27 批會搬的（5 個，約 8 行，27 合完之後寫進玉璽包）：**
`_seal_challenge`、`_seal_spectators`、`_seal_side_of`、`seal_gamble`、`admin_seal_duel`。另有 `seal_duel.py`。

**新方法 9 個：** 見 2.2、2.5、2.6。

## 四、舊模組與測試的新家

**develop 改了、主幹已搬的舊模組（8 個，約 55 行）：**
- `cultivation.py` → features/cultivation/cultivation.py
- `epiphany.py`、`sensing.py` → features/sense/
- `smithing.py` → features/smithy/smithing.py
- `storyline.py` → features/story/storyline.py（`roll_start` 在共用層 `story_base.py`）
- `companion_agent.py` → features/companions/
- `foreshadow.py` → features/military/fs_rules.py
- 根目錄 `zhuan_html.py`（+20）→ features/zhuan/zhuan_html.py

**develop 改了、主幹已搬或已刪的測試檔（11 個）：**
- 搬了 9 個：
  - `test_epiphany` → sense
  - `test_silver_gates` → outlets
  - `test_biography` → zhuan
  - `test_explore_variety` → explore
  - `test_socialize_variety` → socialize
  - `test_story_wangyue`、`test_story_wolong` → story
  - `test_checkin` → checkin
  - `test_real_map` → map
- 主幹已刪 2 個：`tests/acts/test_explore_modes.py`、`tests/web/test_gather_branches_web.py`（第 13、14 批拿掉的功能），develop 對它們的改動丟掉。

**server.py：** develop 改到的函式在主幹 server 都還在，或是新加的。撞的是主幹 -285 行留下的上下文，照字面解。

## 五、same_behavior 現有的軌

- 主幹現有 41 軌，加上 explore 那一套：battle、muster、progress、tavern、events、train、guide、bout、ring、companions、sense、arts、talk、socialize、strip、story、roam、shut、figact、zhuan、military、outlets、craft、world、effects、stamina、landturn、peers、omen、herald、travel、roadmate、map、smithy、allegiance、compass、loom、gear、crossblade，加上 sortie、duel。
- 新東西沒有一軌點名：`pick_growth`、`growth:`、`legacy`、`hire:`、`place_state`、`figures_here`、`talk_view`、`status_data`、`seal_gamble` 在腳本裡的出現次數都是 0。
- 會順帶走到的：
  - 經 `/api/main` 整份 emit 的軌（`Scenario.call` 每一個回應都 emit，same_behavior.py:388-399），在 week7、season21 會順帶看到新的鍵；
  - test 那一份設定（測試內容）v2 和傳承都關著，走舊路。
  - 前提是第一節第 1 點補好。
- 要新開的軌：`growth`（2.2）、`places`（2.5）、`here`（2.6）、`legacy`（2.8）、`hire`（2.9）。推測每軌 300～600 行（照 gear、smithy 那幾軌的長度）。往來紀錄、戰記頁不在引擎層，用兩台伺服器的 HTTP 比對。

## 六、分段與並行（對照 11/05 稽核第 6 節）

**第 0 段：合併本身，照新位置搬，不拆新功能。單獨做、最先做，在 27、50 合進主幹之後。**
- 量：
  - 撞檔 29 個（試合）；
  - engine 15 個核心方法原位套，9 個委派方法改寫進 8 個包檔，5 個玉璽方法進玉璽包；
  - 8 個舊模組約 55 行、11 個測試檔；
  - 核心四個檔：`MODULES` 加 `attrset`、`features.py` 加 `prep`、`registry` 加兩包和 `place_state`、`services` 加 `ctx.pick_growth`；
  - 邊界、契約、`test_for` 三個核心測試檔；
  - same_behavior 補開季準備卡的那一步，修 roadmate 那一行 import。
- 證明：develop 對合好的主幹，所有軌 × 三種設定加假人；整套含 slow 全綠。
- PM 要先認定：`attrset` 進核心、`prep` 掛鉤、`place_state` 進共用層（都是稽核查不到的那幾條）。

**A 段：屬性 v2 的動作進修練包。小。**
- 搬 2 個方法、32 行（`_allocate_v2`、`pick_growth`）；留 1 個委派；邊界測試動 3 條；新軌 `growth`。
- 核心留 `_season_prep`、`season_prep_view`、`_attr_rows`、`growth:` 那 3 行。

**B 段：傳承包補規矩。中。**
- 0 個方法。網頁約 130 行從 app.js 切到 `web/legacy.js`，`index.html`、`webharness`；README；局面檔；契約的 `prep` 兩條（改核心測試，回報寫明）；新軌 `legacy`。

**C 段：招募包補規矩。小。**
- 0 個方法。內容檔改名、驗證搬進包（約 10 行；碰 `content.py` 算改核心，這一段不能當純包批並行，要 PM 點頭）；局面檔；slow 標記；可選切 `web/hire.js`；新軌 `hire`。

**D 段：人物與地點畫面＋往來紀錄。中。**
- 4 個方法、48 行：`figures_here_view` 進交友求見包，`talk_view` 進人物情誼包，`_figure_side_name` 進共用層 `figures.py`，`place_state_view` 留核心或進大勢人物包。
- `talk_log` 119 行加路由 19 行進人物情誼包；新軌 `here` 加 HTTP 比對。

**E 段（可選，等於總表第 52 批提前）：戰記包。大。**
- 0 個方法。模組約 750 行（`tale.py` 596 加 `tale_html.py` 156）、server 約 170 行、2 條路由、`web/tale.css`。可以照原排程留給第 52 批。

**並行：**
- 第 0 段完成後，A、B、D（加 E）是不同的包、彼此不等，照總表 5.0 可以三到四條同時跑。C 碰核心的 `content.py`，不並行，或者把那 10 行併進第 0 段。
- 會撞的熱點：
  - `tests/core/test_feature_boundaries.py` 的 `GAME_DELEGATES`、`GAME_DELEGATE_CALLERS`（A、D 都改）；
  - `scripts/same_behavior.py`（每段都在檔尾加一軌）；
  - `engine.py`（A、D，不同區段）；
  - `server.py`（D、E）。
- 照順序合進主幹，後合的照字面解。
- 如果 PM 改成「配比那一步做成修練包的 `prep` 掛鉤」，A 跟 B 都會碰開季準備卡的先後，要排成先後做。

**跟稽核第 6 節的四批比：**
- (a) 屬性 v2「兩三倍大」：那是把 v2 整套搬上主幹的量。現在大部分（`team` +303、`rules`、`models`、`content`、`attrset`，加上 15 個以上的檔要照新位置改）落在第 0 段。真正拆進包的 A 段很小。
- (b) 傳承：等於 B。(c) 招募：等於 C。
- (d) 世界活起來二＋戰記列傳＋main 同步：
  - 世界活起來那一半只剩 `place_state_view` 要拆，併進 D；
  - 戰記那一半是 E；
  - main 的同步已經在 develop 的歷史裡，第 0 段一起進來。
- 稽核之後 develop 新加的：事件歷練 #167 進第 0 段（核心）；介面重整與往來紀錄 #171～175 是新的 D 段；絕招例句 #166 進第 0 段（形象包原位）。

**結果：** 稽核估 4 批，現在是第 0 段加 A～D 四段，E 可選。

## 七、要 PM 定的

1. `attrset` 算核心本體還是共用層（建議核心，照 develop）。
2. `growth:` 留核心前綴、本體進修練包（建議），還是新開一包。新開的話不能叫 `growth`，`tianxia/growth.py` 在共用層，可以叫 `attrs`。
3. `prep` 掛鉤留不留，要補認定。
4. `place_state` 進共用層，要補認定；`place_state_view` 留核心（建議）還是進大勢人物包（稽核的寫法）。
5. 招募獨立一包（建議）還是併進人物情誼包；內容檔只改名、搬驗證（行為不變），還是拆出人物表（行為會變，要企劃者定）。
6. 傳承讀別包欄位：記成過渡，還是開查詢服務。
7. 戰記頁現在拆（E），還是照第 52 批。
8. same_behavior 補「開季準備卡照預設配比、識海不帶」那一步：week7、season21 每一軌的輸出會跟合併前的主幹不同，這是預期的，比對對象改成 develop。

## 本報告用的暫存腳本與量表輸出
- C:/Users/ray61/AppData/Local/Temp/claude/4d5f79bfb143ac0b/86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444/scratchpad/map/hunks.py：engine 改動對照主幹位置
- C:/Users/ray61/AppData/Local/Temp/claude/4d5f79bfb143ac0b/86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444/scratchpad/map/server_hunks.py：server 改動對照主幹位置
- C:/Users/ray61/AppData/Local/Temp/claude/4d5f79bfb143ac0b/86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444/scratchpad/map/server_fn.py：server 戰記與往來紀錄函式的行數
