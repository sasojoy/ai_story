# CLAUDE.md

《天下大勢》文字武俠原型（三國篇，第一季黃巾之亂）。

權威文件（**計畫寫的是當時的打算，跟程式對不上時以程式為準**）：
- 設計：`docs/superpowers/specs/`。總設計 `2026-09-27-天下大勢-design.md`；武學、屬性、戰鬥過程、人物資質以 `2026-10-05-武學與成長-design.md` 為準（第十四節是人物資質）；第一季 `2026-10-02-第一季黃巾之亂-design.md`、`2026-10-04-第一季濃縮版-版本目標.md`；線上架構 `2026-10-02-線上架構-design.md`；伺服器假人 `2026-10-02-伺服器假人-design.md`。
- 實作計畫：`docs/superpowers/plans/`。
- 試玩回饋（FB-編號）：`docs/superpowers/feedback/試玩回饋.md`；裁決：`docs/superpowers/rulings/`；主機端怎麼開伺服器、給網址、備份、換季：`docs/superpowers/feedback/beta-主機端操作.md`。
- 架構流程圖：`docs/superpowers/architecture/三國篇架構.html`（PM 發佈成 artifact，隨進度更新）。

## 工作目錄與分支

- GitHub `sasojoy/ai_story`，主線是 `main`（2026-10-03 起直接在 main 上開發；`feature/sanguo-companions` 不再更新；舊遊戲在 `legacy/ai-story-main`）。
- 這台機器有兩份 clone：`C:\Ray\專案\天下大勢` 是主要的那份（main 在這裡合併、推上 GitHub；專職開發的工作樹在它的 `.claude/worktrees/`）；`C:\Ray\專案\ai遊戲` 是另一份 clone，地圖擴充開發在它的 `.worktrees/` 裡做。**開工前先 `git worktree list`、`git remote -v` 核對一次**：曾經在另一個遊戲的目錄開 session，讀到錯的 CLAUDE.md，白繞一圈。
- `.claude/worktrees/` 底下的工作樹沒有 `.venv`：下面指令裡的 `.venv/Scripts/python.exe` 換成那份 clone 的絕對路徑（例：`C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`）。
- 工作樹的檔案是 CRLF（`core.autocrlf=true`，git 裡存 LF）：用腳本改檔時先把 `\r\n` 轉成 `\n` 再比對，寫回時轉回去。

## 架構

**門面與程式**
- `tianxia/`：純 Python 規則引擎，**不得 import 任何網頁框架**（fastapi 等）。`engine.Game` 是唯一對外門面。
- `content/`：所有遊戲內容（JSON），載入時由 `tianxia/content.py::validate` 交叉檢查（id、連通、素材拿不拿得到、退路字表組出的每個名字都過得了命名過濾、獎勵不能給或扣博聞、隨口應對的獎勵不能高過檢定選項……）。`content/profiles/<名字>.json` 是設定覆寫檔，由環境變數 `TIANXIA_PROFILE` 選（`weekend`：第一季規則開、季長 2.5 天、人數上限 2），只能寫 `Config` 有的欄位。
- `server.py`：網頁伺服器（FastAPI），只負責登入、行動鎖、鎖外的模型呼叫與把畫面要的東西整理成 JSON；引擎的 Markdown 在這裡轉成 HTML（原始 HTML 一律跳脫）。鎖內模型呼叫的全服斷路器也在這裡（見「模型呼叫」）。
- `web/`：手機優先的單頁網頁（`index.html`／`style.css`／`app.js`，沒有建置步驟、不靠外部函式庫，見「介面」）。
- `run_bots.py`：伺服器假人程式的入口，每隔 `bot_tick_seconds` 呼叫一次 `BotRunner.tick()`，跟 `server.py` 同時開著、開同一個資料庫與同一份設定。

**存檔與全服狀態**
- `tianxia/database.py`：SQLite（預設 `saves/tianxia.db`，環境變數 `TIANXIA_DB` 可改；線上版與開發版各用各的）：連線、資料表、交易。一個動作＝一筆交易（`BEGIN IMMEDIATE`，出錯整個撤回），同一個執行緒可以巢狀（交易可以巢狀；`WorldStateStore.mutate` 不行，內層寫的會被外層蓋掉，直接丟 `RuntimeError`）。結構版本記在 `PRAGMA user_version`（目前第 3 版）；改結構時新增一組句子、接進 `SCHEMA`、`MIGRATIONS[舊版]` 指向它、`SCHEMA_VERSION` 加一，舊檔打開時在同一筆交易裡一版一版就地升級（中途出錯整個撤回、檔還是舊版；沒有遷移路徑就丟 `RuntimeError`）。**改結構前先跟 PM 對版本號。**
- `tianxia/world_state.py`：全服狀態的資料模型與存取介面 `WorldStateStore`（Protocol）；實作是 `tianxia/sqlite_world.py::SqliteWorldStore`（`open_world()`）。小的整份覆寫，會長大的（傳聞、江湖史、全服登記的武學、配方、改過的名字、合併出來的意境、第一個練成絕學的人、投靠名冊、決戰回合）一筆一筆加、照季分；換季不刪資料，江湖史跨季保留。武學、改過的名字、意境共用一個名字空間（`sqlite_world._name_taken`）；登記都是鎖內原子（`claim_recipe`、`claim_insight_recipe`、`link_recipe`、`link_insight_recipe`、`rename_skill`、`claim_master`）；`fused_arts`／`merged_insights` 是合到舊的找候選用的。
- `tianxia/characters.py`：角色存檔（`CharacterStore`、`open_characters()`），一個角色一列，**不含賽季**（`GameState.world` 只在記憶體）；名號比對不分大小寫。
- `tianxia/accounts.py`：帳號與密碼（`accounts`、`logins` 表），見「原則」的登入那條。

**規則核心**
- `tianxia/models.py`：內容的資料模型（`Config` 的每個數字與它的理由都寫在欄位註解裡）。`tianxia/state.py`：執行期狀態（玩家、門下、世界）。
- `tianxia/rules.py`：條件、效果（`apply_effect`）、事件檢定（`check_outlook`）、大勢推動（`change_trend`）、第一季的亂局與割據（`chaos_fronts`、`geju_per_day`、`chaos_note`）、戰況變化換成一句話（`front_chip`、`humanize`）、求見門檻（`audience_bar`、`can_meet`）。
- `tianxia/events.py`：事件抽選（同一個池子看過的先不抽，`rotation_pool`）與選項那一行的寫法（`choice_label`）。
- `tianxia/world.py`：大勢門檻、世界事件、分幕主線、虛擬玩家、賽季結局、每週掛勾（`WEEK_HOOKS`）。
- `tianxia/journal.py`：江湖紀錄（一次行動一則）與「剛剛」卡片、紀錄列的 HTML；拿到新東西那一行會掃光（`_NEW_THING`，照訊息原文錨在開頭）。
- `tianxia/guide.py`：新手引導、個人目標與任務區塊。`tianxia/leaderboard.py`：天下武學榜／內功榜。
- `tianxia/roster.py`：同伴招募（每位歷史人物全服唯一）。`tianxia/companion_agent.py`：跟歷史人物的對話（模型生成，好感度照 tag 查表）。

**戰鬥**
- `tianxia/encounter.py`：單次判定的遭遇戰（遊歷、探索野怪、劇情戰、挑戰大勢人物本人都走它）；只處理數字，不 import 內容模型。威力、運氣、結果門檻、加成（`Boost`）、大場面優勢的平移（`advantage_shift`）、身法閃避（`dodge`）。
- `tianxia/team.py`：隊伍與門下：本人、同伴、部下的屬性與加成（`player_boost`／`mate_boost`／`follower_boost`、`pairing`、`resonance`）、氣血與內傷（`neili_cap`、`take_encounter_toll`、`heal`）、經驗與配點、練成與改練（`practice`、`switch_art`）、打一場（`fight`）、戰前勝算（`estimate`：固定種子模擬 40 場，**每次重算、沒有快取**；不含閃避）。根骨一律從 `con_of(state, content, world, key)` 讀。
- `tianxia/rounds.py`：勝負算好之後照結果拆成 3～5 回合的數字（誰出手、對手氣勢、你掉多少氣血），中途不翻盤。
- `tianxia/battlelog.py`：戰報（`GameState.battles`，最近 20 場）、回合的句子（`round_lines`，句型在 `content/combat_lines.json`）、場景戰鬥卡片與戰報分頁的文字。
- `tianxia/styles.py`：一門打不遍：大場面對手的路數（怕哪一路、最會對付哪一路，照天機＋隊伍 id 雜湊、每季不同）、對威力的倍數、戰報那一句、給模型的打法描述；只在第一季開著時有。
- `tianxia/fight_llm.py`：大場面在行動鎖外請模型判讀（優勢＋佔上風、落下風兩版過程）；只問模型、不碰狀態。
- `tianxia/battle_instance.py`：全服即時多人戰鬥（決戰）的純邏輯——集結、逐幕逐回合鎖步、回合結算、回合上限與收場判定（`decide_outcome`、時刻表決戰的 `decide_result`）、機器人補位。資料存在共用世界狀態的 `active_battle`。

**武學與成長**
- `tianxia/martial_arts.py`：武學的品質、熟練度（成）、威力、屬性與相剋；內容武學與全服登記武學的資料形狀。
- `tianxia/insights.py`：意境的查（`resolve`）、悟（`learn`：新的記進 `PlayerState.insights`、已經會的化成心得）、探索悟哪一個（`explore_pool`／`roll_explore`）、合併的配方鍵、屬性與正邪（`merge_key`／`merged_attribute`／`merged_lean`）；善名、惡名到門檻悟浩然、血煞（`grant_by_name`）。只讀寫 `PlayerState.insights`。
- `tianxia/fusion.py`：三種合成——武學＋意境 → 新武學（`fuse`）、意境＋意境 → 新意境（`merge`）、武學＋武學 → 第三門新武學（`blend`，`MartialArt.parents` 記兩個來源）；配方全服共享、首創者等模型取名；`forge_request` 是取名三段式的 A 段；`can_forge` 是狀態列提示用的便宜檢查。
- `tianxia/landing.py`：合到舊的（設計 12.2）：候選、機會、決定性的擲骰（天機＋配方鍵的雜湊）、規則挑（`rule_pick`）、模型挑的名字對得上候選才用（`choose`）。
- `tianxia/naming.py`：玩家看得到的名字的把關與取名（`clean_name`、`name_problem`、`propose`、`pick`、`generate`、`recheck`、`fallback_name`）；模型只給名字與一句說明，過不了走決定性的退路字表（`content/craft_names.json`）。
- `tianxia/cultivation.py`：修練（衝品質）與絕學定名（`cultivate`、`odds_for`、`boost_for`、`name_mastered`）；只改狀態與回傳訊息。
- `tianxia/library.py`：功法庫：持有上限（`holding_cap`、`cap_of`、`full`）、新武學放哪（`store_art`）、各地學基礎武學（`lessons_here`、`learn`）、熔煉（`melt_art`、`melt_insight`、`melt_value`）。
- `tianxia/materials.py`：素材的掉落與背包。素材**不再拿去煉製**，現在的用途是糧草（押糧車）與伏筆。
- `tianxia/skillview.py`：修練、煉製頁與狀態列提示的說明文字（人物卡、功法卡、武學列、煉製那一行、背包、`practice_hint`、`boost_line`）；只讀狀態、不改數值，說法以 `team.py`、`encounter.py`、`fusion.py` 的實際規則為準。

**第一季濃縮版**（全部掛在 `rules.season_one` 後面，見「第一季濃縮版」）
- `tianxia/calendar.py`：季曆（一季壓成 `season_weeks` 週）、夜裡、週次；玩家看得到的時刻只有一個寫法 `point_text`（「第 3 週・週二 21:40」）。
- `tianxia/timetable.py`：時刻表（第一季 12 件大事）：什麼時候、怎麼結算、公告怎麼寫。
- `tianxia/figures.py`：大勢人物：讀（`state_of`、主將、難度、此刻站在哪、`can_challenge`）、推（`tick`，季的事每曆時一次）、改（`apply` 是時刻表的人物結局與接位鏈，`defeat` 是挑戰打贏）；人物表在 `content/figures.json`，開季蓋章時種進 `WorldState.figures`；讀的函式不看開關，呼叫端要用 `rules.season_one` 擋。
- `tianxia/orders.py`：陣營軍令（每週一發令、個人記功、陣營湊滿額度套效果）。`tianxia/ranks.py`：陣營裡的階級（頭銜、召見、晉升、部下）。`tianxia/push.py`：推力規則（人數緩衝、每人每曆日上限、貢獻）。`tianxia/factions.py`：陣營規模照伺服器人數上限換算。
- `tianxia/defection.py`：叛投（第一季正式版甲）：能不能叛投（`can_defect`）、確認畫面只列真的會失去的東西、`clear_progress` 是之後幾份計畫加「個人進度清除項目」的唯一地方；世界那邊的清理（軍情、地方傳聞）寫在 `Game.defect()`。
- `tianxia/foreshadow.py`：關鍵伏筆（片段、最後一步、暗中鎖定、豪強第三方、官銀），鎖定不能露出來。
- `tianxia/front_lines.py`：戰況變化的說法：機器可讀的寫法 `大勢@<線> ±N`、三段變動大小 `BANDS`、雜湊挑句（句子在 `content/front_lines.json`）；純文字、不看內容模型。

**地圖**
- `tianxia/atlas.py`：大地圖的資料（純資料與文字）：視野、大區歸屬（地點座標落在哪個大區多邊形，區外歸最近的大區）、最省體力的路線與三種走法的時間與體力、四個圖層要標的東西（含局勢層的打擊記號 `strike_marks`）、地點詳情與「安排前往」的條件；勝算只在敵情層與詳情欄才算。
- `tianxia/mapview.py`：把 atlas 的資料畫成 SVG：大地圖（江湖輿圖，四個圖層）與場景旁以你為中心的小地圖（從大地圖截一塊，畫法與視野同大地圖，視窗外兩站以內的摸清地點在邊緣標方向）；地點包在 `<g data-loc>` 裡給網頁認點擊。圖例不畫進 SVG：`legend_data()` 把圖例當資料（六個圖示的小 SVG 與幾行說明，字全在 `LEGEND_*` 常數）交給網頁，網頁在地圖框左下角疊一層半透明、可收合、不跟著平移縮放的圖例（`web/app.js` 的 `legendHtml`，收合記在這個瀏覽器的 localStorage）；小地圖沒有圖例。
- `tianxia/mapart.py`：輿圖的畫法零件（設色山水）：配色、座標寫法、路的二次曲線、河與山脊的平滑線、大區削角、照標籤的地點圖示、紅旗、外框與指北針，以及地形（山頭與樹讓開地點、路與河；只跟內容有關，每份內容算一次快取）。只 import `models`、不看視野；mapview 只管組合、視野狀態與名字避讓。

**模型與文字**
- `tianxia/ollama_client.py`：本機 Ollama 的 client（JSON schema 約束、截斷修復、必填欄位缺了才重問——`0` 與 `False` 不算缺）；`quick_client` 是行動鎖內用的短逾時、不重問的複本。
- `tianxia/zh.py`：模型產出的文字轉成繁體（`to_traditional`，見「模型呼叫」）。
- `tianxia/event_llm.py`：事件的隨口應對（評成功率、擲骰後潤色）。`tianxia/flavor.py`：重複事件與重遊的點綴句、世界事件傳聞的全服潤色。

**假人與機器人**
- `tianxia/server_bots.py`：伺服器假人的名號、個性、作息（純函式，不碰檔案也不 import 引擎）。
- `tianxia/bot_policy.py`：假人照陣營目標做一個動作，只走 `Game` 的公開行動（含配點 `Game.allocate_stat`）。
- `tianxia/bot_runner.py`：假人程式的核心，每一輪補人（先叫醒退隱的、沒有才新建）、叫醒、讓在線的假人做事；`game.client` 設成 None。
- `tianxia/bot.py`：整季測試與量表用的亂數機器人（`play_season`）：隨機挑選項，每隔幾步配點、練成、合成、修練（`allocate_points`、`spend_xinde`、`forge_and_cultivate`）。

## 原則

- **行動名稱**（企劃者 2026-10-04 定）：「遊歷」（舊稱歷練，`act:train`）、「交友」（舊稱交遊，`act:socialize`）；移動維持步行／趕路／疾行三種。舊文件寫舊名的，指的是同一個行動。
- **數值全部由規則引擎決定。** 模型只寫文字、評一個機率（放手一搏、隨口應對的成功率）、給一個夾過的優勢（大場面判讀，最多 ±`big_fight_swing` 個百分點），或從清單裡挑一個名字；擲骰、換算、損耗、獎勵都是引擎的事，引擎拿到模型的數字一律再夾一次。
- **引擎不讀電腦時鐘**：現在時間一律由 `Game.sync(now)`（設定 `Game.now`）或明確的 `now` 參數傳入。`tianxia/` 裡只有 `database.py`（等寫入權的期限）、`accounts.py` 與 `bot_runner.py`（注入的 `clock`）碰時間；模型呼叫的時間預算靠 HTTP 逾時扣，由 `server.py` 量好傳進來。
- **玩家看得到的時刻只有一個寫法**：第一季一律走 `calendar.point_text`（「第 N 週・週X HH:MM」，N 前後有空格）；寫時間的地方都經過 `calendar.stamp_text`／`Game.stamp`（狀態列第二行、下一件、軍令截止、江湖史、傳聞、戰報都是），不要在別處自己拼。開關關著時照舊「第2天 14:05」。
- **名字原創**：我們寫的內容（武學、人物、意境）不用金庸等作品的專有名詞。模型取的名字與玩家替絕學定的名字都過 `naming.name_problem`（禁用名單 `content/banned_names.json`、只能是中文、不能跟素材、人物、內容武學、意境、江湖上任何角色的名號同名），全服重名在登記時原子判斷。
- **改名之後 id 跟顯示的名字不同**（絕學定名只改顯示的名字）：寫給玩家看的一律用 `team.resolve_art(...).name`，認東西的一律用 id。
- **改內容後跑 `scripts/test_for.py`**（會挑到 `tests/test_real_content.py`，連 slow 一起跑）：它讓機器人用真實內容玩完整季，抓出內容錯誤（也鎖住事件難度帶 `DIFFICULTY_BANDS`）。
- **賽季由管理者開**：全服第一次開局停在「籌備中」，管理者（`content/config.json` 的 `admins`，加上 `.local/admins.txt` 與 `TIANXIA_ADMINS`）在設定頁按「開季」；季結束（或管理者「立刻收季」）進入「休季」，管理者按「開啟下一季」。換季時：同伴全部重獲自由、等級武學歸零；全服登記的武學、配方、改過的名字、意境、第一個練成絕學的人都照季分開存，新的一季自然是空的；上一季的首創（合成、意境、絕學）寫進那一季的江湖史；天機 +1（同一個配方長出不同的東西）；沒打完的決戰清掉；跟人物的好感度只帶一成。測試內容用 `auto_open_first_season: true` 直接開季。資料都在資料庫；舊的 `saves/*.json`、`saves/world/state.json`、`saves/accounts/accounts.json` 不再讀取（企劃者 2026-10-03 決定不搬）。管理者的角色用 `scripts/set_password.py <帳號> --character <名號>` 建立並綁到帳號上，只有登入那個帳號的人進得了；玩家不能取管理者的名號。
- **第一季濃縮版的規則掛在開關後面**：`Config.season_one`（`config.json` 預設關，`weekend` 設定打開）加上這一季開季時蓋的章（`rules.season_one`）。開關打開時正在跑的那一季照舊用 beta 的規則；開關關著時 beta 一個字都不變，新功能一律先問 `rules.season_one`。
- **陣營**（`content/scenario.json` 的 `factions`）：玩家開局是散人，在陣營的 `join_at` 地點按「投靠」（要確認一次：先按 `faction:<id>`，再按 `faction:confirm`），或拜入陣營名下的門派；陣營人數看全服投靠名冊（`WorldStateStore.faction_counts()`）。全服決戰只能站自己陣營那邊；散人可以在決戰的大區「臨時投效」交戰兩軍之一（`battle:enlist:<id>`，集結時能改投、開打了也能晚到），只算這一場：不改自己的陣營、不進投靠名冊、不算叛投、不能投第三方（散人的假人不投效）。不在交戰雙方的陣營只在一旁觀戰、照常遊玩。狀態列的名號後面寫「門派・陣營・頭銜」（有哪幾樣寫哪幾樣），都沒有才是散人。
- **伺服器假人跟真人完全一樣、看不出來**（`docs/superpowers/specs/2026-10-02-伺服器假人-design.md`）：「是假人」只記在存檔的 `PlayerState.bot`，任何畫面、榜單、戰鬥名單、主控台輸出都不能顯示或透露（回給玩家的拒絕話也一樣：名號被假人用掉、模型取到假人的名號，都回跟真人同一句）。假人只透過 `Game` 的公開行動做事；現在 `client=None`，一個模型都不叫，也不寫自由文字（放手一搏、隨口應對都排除）。**企劃者 2026-10-05 定：假人之後學會合成時，首創配方也要叫模型取名**（走同一條三段式，A、C 在 `action_lock` 裡，`bot_runner` 到時候要補 `reset_model_budget()`），不然「首創者是假人的配方名字都是字表風格」會被看出來。
- **兩個程式、一個資料庫、一把行動鎖**：`server.py` 與 `run_bots.py` 共用同一個資料庫，每次「補算時間＋做動作＋存檔」都包在 `WorldStateStore.action_lock()` 裡（一筆 SQLite 寫入交易；伺服器等到拿到為止，假人等不到就跳過）。伺服器每次進鎖先從資料庫重讀角色（`server._locked`）：資料庫是唯一的真實來源，`server.GAMES` 只是每個角色那份 `Game` 物件放的地方，拿來做決定的讀取都在鎖裡。**慢的模型呼叫不在鎖裡**：人物對話、開爐取名、大場面判讀、隨口應對都是三段式（見「模型呼叫」）；還留在鎖裡的模型呼叫一律用 `Game._quick_client()`，一步最多 `in_lock_model_timeout`（15）秒、一次拿鎖只容忍一次失敗，失敗一次全服 180 秒內鎖內都不叫模型（`server.MODEL_BREAKER_SECONDS`）。
- **管理者**（試玩期是 `Rayal`）在設定頁可以開季、收季、開下一季、立刻開戰、觸發大勢門檻或世界事件、推動大勢線、時間快轉，第一季還有時刻表與救場工具（排時間、跳到下一件、定戰況、定結果、清鎖定、取消決戰）；效果跟自然發生一樣（`Game.admin_*`），也可以幫玩家重設密碼。管理者目前認角色名號（`Game.is_admin()`），之後換成帳號權限。
- **登入**用帳號密碼（`tianxia/accounts.py`；設計見 `docs/superpowers/specs/2026-10-03-帳號密碼登入-design.md`；帳號密碼是一種登入方式，封測的線上版不開、只留在開發與測試環境）：帳號和名號分開，一個帳號一個角色；帳號不存在與密碼錯、名號被真人或假人用掉，各自回同一句話，避免試出誰是假人。會改帳號或建立角色的動作都包在同一筆交易裡。
- **屬性只靠升級給的點**（武學與成長設計 6.2、6.3）：每升一級給 `stat_points_per_level`（1）點，自己分配到臂力、身法、根骨、悟性、博聞（每項最高 `stat_cap` 15）；戰鬥不再隨機加屬性。前四項事件可以加（夾在 `stat_cap`，訊息照實際動了多少寫，被夾掉時多一句「已到頂」）；**博聞只能靠配點，任何獎勵都不能給、不能扣**（載入時檢查，企劃者 2026-10-05）。
- **根骨只從 `team.con_of(state, content, world, key)` 讀**：本人照存檔、同伴照他自己的；氣血上限、回血、損耗、氣血係數、狀態列與角色卡都走它。
- **身法讓落敗有機會閃成僵持**（`team.dodge_chance`），劇情戰除外；勝算不含閃避（勝算是贏的機會）。
- **戰況變化不對玩家露數字**：第一季開著時，推動戰線、割據的那一行是機器可讀的 `大勢@<線> ±N`，畫出來的那一刻才換成一句話、照看的人的陣營上色（`rules.front_chip`、`rules.humanize`）；戰報不收這種變化。畫面上寫的亂局條數與割據漲落方向**必須讀 `rules.chaos_fronts` 與 `rules.geju_per_day`**，不要另寫一份判斷。
- **新增「永遠按得下去」的選項要一併改 `bot.py::pick()`**：整季模擬用「沒有任何可按的選項」當推進時間的訊號（`act:rest`、喊停、路上的選項、會被打發的求見都已經排除）。
- **臨時腳本**：會開世界（`Game.new`、`open_world`）的一次性腳本先把 `TIANXIA_DB` 設到 repo 外的暫存檔，不然會開到這份 clone 的 `saves/tianxia.db`；印中文前先把 stdout 包成 UTF-8（`sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`），不然 cp950 會噴錯。**不要寫「多處替換、最後統一寫檔」的腳本**：中間一個 assert 失敗就整批回滾，印出來的訊息會讓人以為改好了。

## 指令

- 執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861，預設只聽這台電腦；`--port` 換埠）。要給外面的手機：加 `--share`（cloudflared 開 trycloudflare 臨時公開網址，每次重開都換）；要讓同一個區網的裝置直接連：加 `--lan`（綁在所有網卡上、多印一行提醒；有網址的人都進得來）。
- 週末設定（第一季濃縮版）：兩個程式啟動前都設 `$env:TIANXIA_PROFILE = "weekend"`；啟動時印「設定：…」，兩邊要一樣。
- 測試（2026-10-07）：開發用的依賴在 `requirements-dev.txt`（`-r requirements.txt` 加 `pytest-xdist`；伺服器不用裝），裝好之後加 `-n auto`（或 `-n 8`）平行跑；這台 16 核整套約 1 分鐘，單一行程約 3 分 40 秒。venv 路徑有中文時 worker 要 `PYTHONIOENCODING=utf-8`，`tests/conftest.py` 在開 worker 前已經補上。網頁測試預設每個行程一個常駐 node，`TIANXIA_WEB_HARNESS=process` 改回每次各開一個。三種跑法：
  - **開發中**：`.venv/Scripts/python.exe scripts/test_for.py`——跟 origin/main 比、加上還沒提交的改動，只跑直接相關的測試檔（直接 import 改到的模組的、內容改了跑內容與真實內容、`web/` 改了跑寫到那個檔名的），連 slow 一起跑，挑到三個檔以上自動 `-n auto`；`--list` 只列不跑，也可以直接給檔名（`scripts/test_for.py tianxia/fusion.py`），`--` 之後的參數原樣交給 pytest。改 `tests/conftest.py`、`tests/fixtures/`、`pyproject.toml` 時跑整套。
  - **平常的整套**：`.venv/Scripts/python.exe -m pytest -q -n auto`，不跑標了 `@pytest.mark.slow` 的（整季模擬、真實內容跑整季、量表與模擬腳本）。
  - **合併前**：`.venv/Scripts/python.exe -m pytest -q -n auto -m "slow or not slow"`（或 `scripts/test_for.py --all`），含 slow。不寫 `-m ""`：PowerShell 5.1 會把空字串參數吞掉。
  - 新寫的測試要跑整季、整個腳本、或單一個超過一秒的，標 `@pytest.mark.slow`（整個檔都是就寫 `pytestmark = pytest.mark.slow`）。
- 伺服器假人：`.venv/Scripts/python.exe run_bots.py`（跟 `server.py` 同時開著）
- 假人整季模擬：`.venv/Scripts/python.exe scripts/sim_server_bots.py --seasons 2 [--profile weekend]`
- 第一季整季模擬與驗收：`.venv/Scripts/python.exe scripts/sim_season_one.py --seeds 1 2 3 --factions 5 5 5 --hours 60`（預設 `--profile weekend`；數字照實報，不為了驗收調參數）
- 合成量表：`.venv/Scripts/python.exe scripts/measure_forge.py --seeds 1 2 3 4 5 [--profile weekend] [--reserve N]`——一季裡三種合成第一次的組合數、合到舊的比例、模型呼叫數、`bot.FORGE_RESERVE` 夠不夠；只量不改。一個機器人獨佔一個資料庫，合到舊的一定合到它自己已經有的，所以那個比例是全服的下限。
- 同伴加成量表：`.venv/Scripts/python.exe scripts/measure_companions.py`（只量不改）
- **好玩度量表**：`.venv/Scripts/python.exe scripts/fun_run.py --seeds 1 2 3`／`--calibrate`（見「量表與教訓」）
- 隨口應對的真模型實測：`.venv/Scripts/python.exe scripts/try_event_llm.py`（要先開 Ollama；會印出保底警告）
- 黃巾聲勢來源分析：`.venv/Scripts/python.exe scripts/sim_trend_sources.py --seasons 4 [--variant zero|half] [--cap N]`
- 幫帳號設密碼（主機端）：`.venv/Scripts/python.exe scripts/set_password.py <帳號> [--character <名號>] [--db <資料庫檔>]`（角色不存在時直接建立；密碼寫到 `.local/`，不印在畫面上）
- **把自己設成管理者（這台機器）**：在 `.local/admins.txt` 一行寫一個名號（`#` 開頭是註解）。`.local/` 在 `.gitignore` 裡，不會進版控、pull 下來也不會被蓋掉；臨時用也可以設 `TIANXIA_ADMINS=甲,乙`。兩者都**附加**在 `config.json` 的名單（`Rayal`）之上。

### 開發伺服器的啟動方式（這台機器上的慣例）

完整步驟（含給網址、換季、備份、具名 Tunnel）見 `docs/superpowers/feedback/beta-主機端操作.md`。要點：
- 不要用 Bash 工具背景執行 `server.py`（會被背景任務追蹤器砍掉）。用 PowerShell `Start-Process` 完全分離啟動，輸出導到 `server_out.log`／`server_err.log`，**記下回傳的 PID**，再輪詢 log 等 `公開網址：https://…trycloudflare.com`（約 7 秒；讀 log 要 `Get-Content server_out.log -Encoding UTF8`）。
- **引數一定要加 `-u`**（`python.exe -u server.py --share`）：stdout 導到檔案時 Python 會緩衝，沒有 `-u` 的話服務其實已經在聽 port、log 卻一直是空的。
- `--share` 要先 `winget install Cloudflare.cloudflared`（裝在 `C:\Program Files (x86)\cloudflared`）；裝之前就開著的終端機找不到它，啟動前補 `$env:Path += ";C:\Program Files (x86)\cloudflared"`。
- **停的時候用 `/T` 關整棵**：`taskkill /PID <Start-Process 回傳的 PID> /T /F`（或在主控台 Ctrl+C）。只關「正在聽 7861 的那個 PID」會留下 cloudflared，重開後舊網址照樣進得到新伺服器（FB-021）。不確定有沒有殘留時，先停伺服器，再清掉連到 7861 的 cloudflared，最後才重開（指令在主機端操作文件）。
- `server.py` 與 `run_bots.py` 要開同一個資料庫、同一份設定：要用 `saves/tianxia.db` 以外的檔，兩個程式啟動前設同一個 `TIANXIA_DB`（兩個程式啟動時都會印出資料庫路徑與設定，設錯一眼看得出來）。

## 規則速查（現在怎麼玩）

數字都在 `Config`（`tianxia/models.py`，正式值以 `content/config.json` 與設定覆寫檔為準）；這裡只寫結構與現在的值，改數字不必改這一節的結構。

### 行動
- **體力**（體力平衡提案第〇節，企劃者 2026-10-07 定案）：上限 250，每 3 分鐘回 1 點（`stamina_regen_seconds`）；新手期（加入起 `newbie_stamina_days` 18 季曆天，週末約 13 小時、14 天的季 3 天）回復 ×`newbie_stamina_multiplier`（3），跟打坐疊乘；氣血加倍的 `newbie_days` 也是 18。探索、遊歷各 6，交友 3，招募 15。事件檢定、隨口應對失敗另扣的體力乘 `event_fail_stamina_scale`（0.5，四捨五入，`rules.failed`），選項上寫「（體力 -N）」「（失手多耗體力 N）」（`events.stamina_note`）。回體丹一顆回 150（內測新角色送 20 顆，`beta_gift`）。
- **探索**（探索三選一設計）：這裡有還能遇上的一次性或奇遇事件時先滾 `rare_explore_chance`（2.5%）；沒中就照地點類型（`explore_mix`：營寨類、城鎮類、其餘）抽「悟意境／野怪／事件」三支之一（悟意境那一支的比重乘悟性的加成；做不了的那一支拿掉重抽）；不論走哪一支，最後再擲 `explore_legend_chance`（2%）撿一枚破境丹。**探索不撿素材。** 野怪扣的氣血打五折、打贏不推大勢。
- **遊歷**（`act:train`）：只在這裡有敵人（或軍令帶來的運糧隊）時出現，**必定開打**；遇上自己陣營的隊伍是操練（零風險：給經驗與心得、推大勢，不給銀兩、不掉素材）。打完有 `train_event_chance`（30%）接一則 `actions: ["train"]` 的戰後事件。按鈕寫勝算，多路對手時取**最強的**那個算（標籤是警告，寧可低估）。
- **交友與求見**：見不見得到看求見門檻（`rules.audience_bar`：人物的 `audience_fame`，投靠他那個陣營的人每晉升一次抵 `audience_rank_discount`），或結識過；門檻不夠的求見一直按得下去，但只會被打發（他自己口吻的一句、寫還差多少名望；不花體力、不叫模型）。只有一位人物的地點直接列「求見某某」，兩位以上打開求見名單（不花體力）。對話每輪 `talk_stamina`（2），同一位人物每個遊戲日最多 `talk_turns_per_day`（3）輪。
- **招募**：成功率 35%＋50%×情誼／100，夾在 5%～95%（按鈕上寫）；失敗有 40% 被要求決鬥、賠 15 兩。
- **打坐**（`act:rest`）：永遠按得下去；坐下之後體力回復是平常的 `rest_regen_multiplier`（2）倍，期間不能做別的，隨時「起身」，回滿自己起身。只推玩家自己的時間，不碰共用賽季時鐘。
- **閉關**：1～12 小時，出關得心得 小時 × `seclusion_xinde_per_hour` ×（1＋悟性／20），期間氣血回復加倍。
- **移動**：步行不花體力只花時間、趕路快一倍、疾行立刻到（後兩種花體力）。步行、趕路時路上有四樣小事，每一段路各做一次（疾行沒有）：邊走邊想（心得）、沿途打聽（傳聞）、留意地形（摸清地點）、路邊採集（一階素材，屬性看這段路兩頭的 `Location.materials`），收穫每個遊戲日有上限；每抵達一站有機會看見一則路上見聞。可以折返、喊停。
- **拜師學藝**（`learn:<id>`）：各地教基礎武學（武學與成長設計附錄 B），開局送的兩門（基礎吐納、基礎拳腳）熔掉之後在任何城鎮免費重學；持有滿了不能學。

### 事件檢定
- **每一個事件檢定都只看本人的屬性**（企劃者 2026-10-05）：檢定值＝本人這項屬性（配的點與事件加成）＋熟練加成。`Check.by`、`FreeTextChoice.by` 照樣讀得進來、不再有作用。成功率 50%＋差值×10%，夾在 5%～95%（`rules.check_outlook`；擲骰與選項上寫的都出自它）。
- **選項只寫一行**：「{選項}（{屬性名} {數值}：{心裡話}）」，不寫成算、百分比、誰出手。心裡話出自 joy 的 `content/check_voice.json`（照差值分檔）。結果只寫「（成功）」「（失敗）」（`rules.check_result_line`）。動手的選項寫對手與勝算。
- **難度帶**（2026-10-05，企劃者「成功率毫無道理可言」）：難度跟著事件所在地點的 `danger` 走（出現在好幾處時取最危險的）：危險度 1 是 3～6、2 是 4～7、3 是 6～8。`tests/test_real_content.py::DIFFICULTY_BANDS` 鎖住；**新寫事件照地點的危險度挑難度**。伏筆準備事件（`foreshadow_prep.json`）的難度照伏筆設計表，不在帶裡。
- **惡名的熟練加成**（2026-10-05，企劃者「你常常做壞事（惡名高）因為很熟練所以也增加成功率」）：檢定寫 `"practice": "evil"` 時，檢定值再加 `min(cap, 惡名 // per)`（`Config.practice_bonus`，現在每 10 點 +1、最多 +3）。選項上寫成「身法 5＋2」，熟練那一句（`rules.practice_line`，「這種事你幹得多了」）併進同一個括號。依據：機器人整季隨機玩惡名 9～22（多半 +1），每次挑做壞事的選項 28～47（+2～+3）。**哪些事件帶 `practice` 由劇情填**。
- **隨口應對**：事件有 `free_text` 時選單最後多一顆 `choice:free`，按了才出現 20 字輸入框，送出走 `/api/answer`（三段式）。成功率＝模型分數＋（屬性−5）×4，夾在 5～85（`rules.free_text_rate`；模型失敗一律 40）；江湖紀錄寫「你：「…」（成算 N 成）」。獎勵不能高過同一則事件最好的檢定選項，也不能有 `next_event`／`recruit`／`join_sect`／`flags_add`／`world_flags_add`（載入時檢查）。
- **地方痕跡**：`Effect.marks`（1～3，只能加）、`Condition.marks_min/max`、`WorldState.marks`（換季自然清空），一人一天一次；門檻在載入時乘 `mark_threshold_scale`；文字裡的 `{marks:地點:痕跡}` 換成模糊人數，不列名字。

### 屬性、威力與氣血
- **五屬性**（`team.COMBAT_STATS`，順序就是狀態列與＋鈕的順序）：臂力、身法、根骨、悟性、博聞（鍵 `lore`；「博聞」是暫名，顯示名只寫在 `Config.stat_names`），開局都是 5。比基準 5 每多一點 `stat_bonus_per_point`（3%），比 5 少是負的；乘上去的量最低夾在 `encounter.BOOST_FLOOR`（0.1）。
  - 臂力：乘武學（外功）威力。根骨：乘內功威力、乘氣血上限、減一場損耗裡變成內傷的比例。身法：減一場的氣血損耗；落敗時有（身法−5）×`dodge_per_point`（2%）的機會閃成僵持（劇情戰不擲）；回合演出裡不低於對手就先出手（對手身法＝5＋難度÷20）。悟性：乘修練升品的機率（在 `cultivate_cap` 之內）與探索落在悟意境的比重、閉關心得。博聞：持有上限，**不進戰力**。
  - 狀態列點名號展開，「可配 N 點」與五顆＋鈕（`Game.allocate_stat`）；底下一行寫五項各管什麼（`skillview.STAT_USES`）。
- **整個人的乘數**（`Boost.factor`）：本人＝內外搭配（`team.pairing`：同屬性 +20%、相剋的一對 −20%、少一門或其他是 1）× 兩門各自的正邪共鳴（`team.resonance`：正派功法吃善名、邪派吃惡名，每點 0.5%、最多 +20%，反了不反噬）；同伴只乘他自己的內外搭配。本人的角色卡多一行「威力加成」（`skillview.boost_line`；同伴的卡這一版不寫）。
- **同伴與部下吃自己的屬性**（人物資質設計 14.3）：同伴＝他自己的臂力乘他的武學、根骨乘他的內功與氣血、再乘他自己那兩門的內外搭配（屬性是內容的起始值＋每級成長，博聞沒寫當 5）；部下＝模板的臂力乘他那一門武學。**都不吃正邪共鳴**（看的是你的善名惡名）。部下上陣只算威力：不擋檢定、不扣氣血、不吃經驗。同伴不進全服決戰。
- **威力**（`encounter.member_power`）：武學威力（品質與成）×（1＋臂力加成）×（1＋內功威力×（1＋根骨加成）／100）× 整個人的乘數 ×（屬性克對手時 1.3）× 氣血係數（0.5＋0.5×剩餘／上限）。沒有武學就是 0。**等級不進威力**：等級買的是氣血上限（撐得住幾場）與屬性點。
- **單次判定**（`encounter.resolve_encounter`）：差距＝我方威力−難度＋運氣（±難度的 30%，至少 ±5）＋大場面優勢的平移；差距 ≥ 難度的 50% 大勝、≥15% 險勝、≥−50% 僵持，其餘落敗。比例而不是固定點數，所以打大對手是一場賭、打散兵幾乎沒有變數（2026-10-02 校準：武學高 3 成勝率 79%）。
- **氣血與內傷**（氣血門戶名冊設計 §1、A1）：氣血上限＝（300＋20×等級）×根骨的倍數。一場打完按結果扣上限的 5%／15%／20%／30%（大勝／險勝／僵持／落敗；探索野怪再打五折），其中 `injury_share`（兩成）變成內傷；氣血只回到「上限−內傷」（不低於上限的一成），內傷要療傷（每 2 點 1 兩）。落敗另失一成銀兩。練成有 15% 機會受傷、累積內傷。**劇情戰不扣氣血**。
- **等級**：第 n 級升 n+1 級要 `level_exp`×n（10×n）經驗，最高 30 級；同伴跟著拿經驗（存在全服共用的 `CompanionProgress`）。

### 戰鬥的演出與大場面
- **回合演出**（武學與成長設計 8.2）：遊歷、探索野怪、劇情戰、挑戰大勢人物本人打完都演出 3～5 回合（大勝 3、險勝 4、僵持 5、落敗 3～4）。勝負照單次判定一次算好，`rounds.py` 只照結果拆數字（中途不翻盤；回合裡「你氣血 -N」加起來等於戰報那一筆，劇情戰不帶數字），句子照出手那門武學的屬性從 `content/combat_lines.json` 挑（`battlelog.round_lines`；句子由內容方手改，載入時檢查）。**演出用自己的亂數**（`random.Random("名號｜戰報流水號")`），不碰 `Game.rng`：接下來的擲骰不會位移，同一筆戰報每次演出來都一樣。
- **大場面**（設計 8.3）：挑戰大勢人物本人、標了 `Squad.boss` 的對手、難度 ≥ `big_fight_difficulty`（100）的對手（`Game.is_big`；自己陣營的操練、探索野怪不算）。伺服器在行動鎖外請模型判讀（`server.prepare_fight` → `fight_llm.judge`，預算 `big_fight_budget_seconds` 60 秒扣掉等鎖的時間）：模型回優勢（夾在 ±15 個百分點）與佔上風、落下風兩版過程；引擎換成判定差距的平移（`encounter.advantage_shift`），大勝、險勝播佔上風那一版，僵持、落敗播落下風那一版（取代範本回合，寫在 `BattleRecord.narration`）。C 段重驗**整張單子一模一樣**才採用（選項、對手、地點、事件、戰報流水號、雙方陣容），對不上照平常打；等判讀時人走了或事件被了結就不打，回一句「你離開了，這一仗沒打成。」或「情勢變了……」。**一般的仗不問模型，備料與動作在同一次拿鎖裡做完**。按下去要等模型的選項帶 `Option.wait`（「兩人對峙……」），網頁照它換字。池子裡有大場面對手的地點，遊歷挑對手照 `Game._train_pick`（雜湊），其餘照 `Game.rng`（正式內容目前每一處都是後者）。
- **戰鬥卡片**（「剛剛」那張，`battlelog.card_text`）：標題、時間與類型、結果三行同一塊；「過程」（回合一行一行，或大場面模型的一段話）；結果敘事與得失併成一段（「**結果**　…　**得失**　…」）；不重複掉落物、不寫「氣血 -0」，身法閃過多一句「身法一閃，躲過了這一敗。」。網頁上只露第一回合（太高時換成只有數字的短句，`compactRound`），按「展開過程」才攤開，「看完整戰報 ›」放在「過程」那一行（沒有過程的卡片放在最後一段句尾）——目的是 375×812 上不用捲就看得到結果。戰報頁（`detail_text`）照舊整段列出、陣容與「獲得與損失」各一段。

### 武學與成長（武學與成長設計；計畫一～三、二之二、二之三、四、五都已在 main）
- **身上一門內功、一門武學**，開局送基礎吐納與基礎拳腳。**取消自創**（設計 3.8）：玩家不能自己取名造武學，新武學靠合成。
- **心得管學、體力管練**（設計 4.7，推翻了「練功免費」的兩次舊決定）：
  - 練成（成）：第 N 成升 N+1 成花 N×`practice_xinde_per_level`（2）點心得（練滿十成 90），只看第幾成、不看品質；有 15% 機會受傷。
  - 修練（品）：融過意境的武學，用它融的那個意境反覆修練衝品質，一次花 `cultivate_stamina`（10）體力。**衝哪一品之前先要練到幾成**（`cultivate_min_level`：中品 4、上品 7、絕學 10；序章一定升品的那一步不看）。中品 40%、+20%、第三次必成（`cultivate_sure_by`）；上品 6%、+3，乘悟性，**再乘這一回的搭配**（`cultivation.fit`／`Config.cultivate_fit`：成數 ×（0.5＋成×0.05）、拿同屬性的別的意境代用 ×0.7、所在地點探索悟得到同屬性的意境 ×1.5；修練頁與結果只寫一句含蓄的話，不寫倍數）。品質每人各練各的（`PlayerState.art_quality`），熟練度記在 `art_mastery`，升品時成不變。
  - **絕學要契機**（`Config.breakthrough`，企劃者 2026-10-07 選 PR #28 的 A＋B＋C）：上品往絕學的修練不擲骰，只添火候（`art_mastery`，滿 8）；火候滿了、身上那一門十成，打贏一場難度比（對手難度 ÷ 我方威力）≥ 0.3 的仗、或在決戰裡出手滿 3 回合（當難度比 1.0），擲一次頓悟（`cultivation.seize`，從 `Game._seize` 與 `_file_showdown` 呼叫）：25% ×（難度比 ÷ 0.5）× 搭配 × 悟性，夾在 1～60%；沒成留一句「摸到了又滑走」。火候滿了在練功房裡只能勾破境丹強行衝關（`force_odds`：15% × 搭配 × 悟性），成不成都用掉一枚。整季機器人修練先挑身上那兩門（`bot.worn_first`），火候滿了有挑戰本人就去打（`bot.awaits_chance`）。
  - 破境丹（`legend_items`）：探索偶爾撿到；修練頁每一門武學勾「服下破境丹」（預設不勾，伺服器只認布林 `true` 的 `use_legend`）。方案 C 開著時只在火候滿了的那一門出現（強行衝關）；被拒絕的修練不擲骰、丹也不動。測試內容（`tests/fixtures/content/config.json`）把三樣都關著，舊的修練測試照舊量階梯；新規則的測試在 `tests/test_practice_hardening.py`。
  - 絕學定名：全服第一個練成的人拿到取名權（`world.claim_master`，一人一次只留一門；還有一門沒定名時不能衝第二門），名字過 `naming.name_problem`、`world.rename_skill`（原子），id 不變只改顯示的名字（沿用原名也算定名），江湖史記一行；等著定名的那門不能熔。
- **意境**（設計 3.2、附錄 A）：基本意境 風（快）、火（剛）、水（柔）、山（慢）靠探索悟（照地點地形，附錄 C）；浩然（正）、血煞（邪）靠善名、惡名到門檻；奇遇可以直接給（`Effect.insights`，只能是靠探索悟的基本意境）。悟到已經會的化成 10 心得。意境永久學會，合成、修練、合併都不會用掉。
- **三種合成**（煉製頁的太極火爐，`Game.forge(art_id, insight_ids, proposed=None, other_art=None)`）：
  - 武學＋意境 → 新武學（`fuse`，配方鍵 `融|底+意境`）：底留著；種類跟底、屬性與正邪跟意境。
  - 意境＋意境（可以是同一個）→ 新意境（`merge`，`合|甲+乙`）：兩個都留著；屬性的種子是「天機｜配方鍵」。
  - 武學＋武學 → 第三門新武學（`blend`，`兼|甲+乙`，兩個 id 排序後接起來）：兩門都留著；種類、屬性、正邪由 `blend_shape` 照配方種子決定。
  - **三種一樣價錢**：`fuse_xinde`／`merge_xinde`（5）心得＋`fuse_stamina`／`merge_stamina`（5）體力，真的合成了才收（被拒絕不扣）。合併收體力的起因：「合併 → 熔掉 → 再合併」每一圈淨賺心得，企劃者決定不擋、讓每一圈都付一次體力（2026-10-05；FB-067 從 10 降到 5）。
  - 合成出來的武學從第一成起修，不繼承底的品質（擋「絕學的底合出絕學的複本、熔掉就賺」的迴圈）。全服登記的那一筆是下品；**自己那一份的品質照這一爐的搭配算機率再擲**（企劃者 2026-10-06「不要套死固數值」；`fusion.fuse_odds`／`blend_odds`）：底自己那一份的品質與成數（兩門時平均）、意境的來歷（合併出來的、有正邪的、自己首悟的加分）、兩者同屬性加分相剋扣分、悟性（同修練的 `stat_factor`）加成一個造化分，從 `Config.fuse_quality_odds`（普通搭配的平均，下品 50、中品 30、上品 20）往上下推，上品夾在 5～45%、下品 15～80%，權重全在 `Config.fuse_quality`；首創、照著合、合到舊的都照自己這一爐算。週末設定整季平均剛好落在 50／30／20，十四天設定隨角色變強上移到約 34／38／28，記在 `art_quality` 也記在 `art_rolled`，修練從擲到的那一品接著往上。合成前的說明寫這一爐的三個機率與最多兩句原因（「火候還淺、底子尚淺」，`FuseQuality.lines`），不寫品級；結果句寫擲到的。序章那一爐固定下品。
  - **配方全服共享**：第一個合出來的人等模型取名（叫不動走退路字表），之後查表、不用等；別人首創、你還沒有的照樣能合。
  - **合到舊的**（設計 12.2）：一個組合這一季第一次被合時，規則先判會不會合到這一季已經合出來的同類（`landing`：每個候選 +`land_chance_per_candidate` 5%、最多 90%，擲骰是天機＋配方鍵的雜湊）；候選兩個以上由模型從清單挑一個（挑到清單外的當沒挑、改由規則挑）；合到的那一門登記成這個配方，合到你已經有的不收錢。基礎武學、名將武學、內容寫好的意境不在候選裡。
  - **血統裡融過的意境不能再融**（企劃者 2026-10-06 回報「同一種意境合成後的產物無限合成上去」）：意境不會用掉，不擋就能「武學＋風 → 乙、乙＋風 → 丙……」一代一代疊、每代都把風推到功效第一位。`fusion.lineage_has` 沿底（`base`）與武學＋武學的兩門來源（`parents`）一路往上查：全服的意境照 id 認，私有意境照屬性認（跟配方鍵認私有意境同一套）；輪流融兩個意境也擋（甲＋風→乙、乙＋火→丙、丙＋風 擋）。擋在 `fuse_problem` 最前面（「…的來歷裡早已融過「風」——同一股意，再融也只是舊路重走。」），卷軸卡的機率條也不拿這種意境算。
  - **合成的意義是拿到你還沒有的**：配方已經登記、合出來的那一門你已經有了，就不准合（「…你已經有了——換一組試試吧」，排在花費與持有上限之前，同一爐連按兩下也只扣一次）。「已經有了」一律照功法的 id 認。合出來的對應欄位空著就直接配上身，否則進功法庫。
- **持有上限**（武學與意境合計，`library.cap_of`）：50＋（等級 // 5）×3＋max(0, 博聞−5)×2（一季最多 88 格）。滿了不能合成、合併、學新的；悟意境照收（博聞被扣下來而超過上限時，熔回上限以內之前不能合成）。
- **熔煉**：功法庫裡的武學熔成心得＝max(基本值, 練成花的八成)＋品質加給（只算自己修練上去的那幾階：中品 5、上品 15、絕學 40，減去登記時的那一階；合成擲到的品質也算登記時就有，`art_rolled`）；全服登記的武學基本值 `melt_min_refund`（4），內容裡的武學沒有基本值（不然「學、熔、再學」就是無本迴圈）。意境熔成 10 心得。身上正在練的不能熔（先改練）。
- **改練**（`team.switch_art`）：把庫裡的換上身、換下來的回庫，熟練度各自保留（`PlayerState.art_levels` 只在換下來時寫、換上去時取）。
- **素材**：只剩打贏掉（`Squad.drops` 或依難度的預設表）、路邊採集、事件與路上見聞給；用途是糧草與伏筆。`content.py` 載入時檢查每一種素材都拿得到。
- **狀態列提示**（`skillview.practice_hint`）：心得 ≥ `xinde_hint_threshold`（50）而且真的有事可做（還能練成、或付得起一次合成）時，提示去「修練」或「煉製」；休季不提示。

### 第一季濃縮版（`rules.season_one` 開著時才有）
- **季曆**：一季壓成 `season_weeks`（12）週，季曆秒＝世界秒×`cal_scale`；週末設定 2.5 天時一週是現實 5 小時。季長照開季時蓋的章，設定中途換了也不影響正在跑的這一季。
- **時刻表**（`content/timetable.json`，12 件大事）：一般大事看季曆；決戰與季末看 `WorldState.schedule`（管理者可排）。結算：給了結果鍵照它 → 有人鎖定關鍵伏筆照鎖定 → 寫死的照 fixed → 其餘照戰況擲骰。公告卡（江湖頁最上面）、天下大事傳聞、江湖史各一筆；每個人的江湖紀錄在他下次同步時補（`Game._deliver_big_events`）。
- **三條戰線**：潁川汝南、南陽、冀州（0 官軍穩控、100 黃巾控制）；黃巾聲勢由三條加權而來；豪強割據：有戰線在亂局（35～65，`chaos_low`～`chaos_high`）時每條每曆日漲 `geju_chaos_per_day`×min(1, 投靠名冊人數÷`geju_full_players` 15)，三條都穩時每曆日落 `geju_calm_per_day`。決定性勝利（聲勢 ≥85 或 ≤15、割據 ≥85）第 `decisive_from_week`（10）週起才提前收季。江湖頁有戰況圖卡（亂局帶、亂局標）與三方態勢那一行（`status_data` 的 `fronts`、`chaos_band`、`stances`、`stance_notes`，開關關著時這幾個鍵都沒有）。
- **推力**（`Game.push_trend`）：陣營人數緩衝、每人每曆日每條線上限 `daily_push_cap`、貢獻記帳（推 1 點記 `contrib_per_push`）。
- **軍令**（`content/orders.json`）：每週一發令，五種：攻城、守城、截糧、護糧、打擊大勢人物；個人照做一次記一次，全陣營湊滿額度那一刻套一次效果。打擊軍令的卡寫怎麼打、在哪（所在沒摸清只寫大區），輿圖局勢層在目標標 ◎（沒摸清標大區）；「他現在挑戰得了嗎」只問 `figures.can_challenge`（挑戰鈕、軍令卡、輿圖共用）。
- **晉升**：貢獻到 `rank2_contrib` 發召見 → 在召見的地點應召走晉升奇遇；頭銜寫在狀態列；部下見上面。
- **大勢人物**：選單上「挑戰本人」（`act:challenge:<id>`，難度跟著聲威）；打贏扣他的聲威與情誼，`snub_hours` 現實小時內閉門不見。
- **伏筆**：片段（行動後偷聽、對話裡的片段選項）、準備事件、最後一步；鎖定只在大事揭曉時露出來，先完成與搶輸的敘事一模一樣。
- **叛投**：一季一次，在別陣營的投靠點（「此地還能做」裡的「叛投X」，要再按一次確認，可以「再想想」）。身份歸零：晉升、召見、部下、本季貢獻、押著的糧車作廢，舊陣營的門派一起離開、這一季拜不回去；屬性、武學、同伴、銀兩、素材、紀錄都不動。新舊陣營各一則軍情（寫本名），當地一則地方傳聞（照匿名規則）。名字還在沒打完的決戰陣上不能叛投；假人與整季機器人不叛投。
- **一門打不遍**（企劃者 2026-10-07 選甲，`styles.py`、`Config.styles`）：大場面對手（同 `Game.is_big`）每季各有路數：上陣的人身上武學屬性落在他怕的那一路威力 ×1.25、落在他最會對付的那一路 ×0.75（乘在 `Boost.factor`，跟相剋的 ×1.3 疊；`team.fight` 與 `estimate` 都走 `_styled_fighters`）。提示含蓄：戰報裡打贏且用了軟處、或沒打贏且用了硬處各一句；大場面判讀的對手那一行多寫打法（`styles.fight_line`）；大勢人物好感到 `talk_affinity`（20）時對話提示裡多一段他的武藝習慣（`styles.talk_line`），只能不經意流露。決戰裡同一邊出固定招的人武學屬性每多一路，力量 ×（1＋`diversity_per` 0.05），最多 `diversity_cap` 0.15（屬性在加入時快照進 `BattleParticipant.attribute`）。
- **首創名望回饋**（`Config.first_echo`）：別人照著你首創的武學或意境合出同一門（照著合、合到舊的都算），`fusion.echo` 記在這一季的 `WorldState.echoes`；你下次同步時每人名望 +1（`Game._deliver_echoes`，一門最多 5 人），湊滿 5 人時江湖上傳一句。
- **切磋**（玩家互動第二層，企劃者 2026-10-08；`tianxia/spar.py` 登記進玩家卡 `social.ACTIONS`，規則在 `Game.spar_invite`／`answer_invite`／`_spar`）：同一地點的人發邀請（`WorldState.invites`，`tianxia/invites.py`，`invite_ttl_seconds` 600 秒逾時），對方答應才打；收到的邀請也進閒著的選單（`invite:yes|no|cancel:<id>`，假人照它答，`bot_policy._answer_invite`）。本人對本人單次判定（不帶同伴部下，從發邀請的一方算、另一方照鏡像），不扣氣血、不掉銀兩，雙方各花一次遊歷的體力、各一份戰報（`kind="spar"`），經驗與心得照 `Config.spar`，同一對人每個遊戲日最多 `per_pair_day` 場（`WorldState.spar_tally`）。動到別人時 `Game.touched` 記名號，`server._tell_tabs` 一起叫醒他們的分頁。
- **玩家之間的互動**（企劃者 2026-10-08；`tianxia/social.py`）：場景底下「此地還有」列 `presence_seconds`（600）現實秒內同步過、不在路上也不在序章的人（真人假人一樣），點名字開玩家卡；卡上的鈕是登記表 `social.ACTIONS`（打招呼、贈物、結伴同行、切磋）。**贈物**（銀兩、素材、回體丹）不必對方同意，兩邊江湖紀錄各一則。**打招呼**（抱拳、請教、挑釁、敬酒，`social.GESTURES`）與**結伴同行**走跟切磋同一套邀請（`invites.py`，kind `greet`／`travel`），收到的列在閒著的選單（`invite:<回應>:<id>`）與場景底下（`Game.calls_here`）；打招呼只有固定的回禮、沒有自由文字。結伴同行答應之後記在跟著的人身上（`PlayerState.tagalong`，帶頭的人照它從資料庫查，`CharacterStore.tagging`）：帶頭的人出發、改道、喊停時跟著的人照抄那一趟（`Game._lead`，體力各付各的，跟不上就散），跟著的人路上只能「分道揚鑣」（`act:part`），路上小事的收穫兩人都有（`_share_road`），到終點就散；答應了 `party_wait_seconds` 沒動身也散。假人照人的步調回打招呼與結伴（`bot_policy.answer_call`：先等一段、有回有拒有不理），答應了結伴就在原地等。
- 結局與休季的結算卡（江湖頁最上面）。beta 的黃巾決戰門檻、主線、`kou_boss` 等由 `scenario.json` 的 `season_one_off` 關掉。

### 全服決戰
- **兩種開法**：beta 那一季是大勢推到門檻（`scenario.json` 的 `huangjin_60`，`starts_battle`）開「黃巾決戰」；第一季是時刻表上的三場（長社火攻、宛城之戰、廣宗決戰），起點照戰況。
- **流程**：集結（人要在決戰所在的大區、不在路上；劇本有陣營時只能替自己的陣營出戰，晚到的人補進自己那一邊）→ 逐幕逐回合鎖步（所有在場者都送出行動、或回合逾時代選保守行動，才結算；誰送出最後一個就由誰的這次呼叫觸發結算，不需要背景程式）→ 收場。**每幕固定 `rounds_per_act`（3）回合**（黃巾決戰 3 幕 × 3 ＝ 9 回合），換幕只看回合數、不看戰局；打完最後一回合，或某回合戰局偏離中線 50 達 `decisive_margin`（40，即到 90／10）就收場，由 `battle_instance.decide_outcome` 照 `outcomes` 決定結果。時刻表決戰的結果由 `decide_result` 判：有人鎖定伏筆的一方一定贏，否則看戰局偏向哪邊，偏離 ≥15 大勝、否則險勝。場上沒有任何人能打時，回合一逾時就用 `outcomes` 最後那個無條件的保底收場（`end_without_fighters`）；換季也會清掉沒打完的戰鬥。「不會把全服卡住」主要靠回合上限。
- 決戰的氣血池是加入時抓的快照，不回頭傷到角色；威力也是加入時快照。參戰者打完各自補一則紀錄與一場戰報（站哪邊、出手幾回合、第幾回合倒下、大勢），下線的人回來補。
- **輸贏要看得懂**（試玩回饋 2026-10-08）：每回合場景的第一句是「這一回合X佔了上風（戰局 a→b）：原因」（`round_line`／`round_causes`：哪招剋住哪招、人多、武藝或氣血、對面沒人正面出陣、放手一搏的淨推動、幾個人逾時被代為固守），每回合記一筆 `BattleInstance.swings`；收場時 `outcome_reason` 挑往贏家推得最多的兩回合（起點偏向贏家也寫）寫成「勝負的關鍵：…」，進收場訊息與每個參戰者的戰報。伏筆鎖定的一方贏了、戰場上卻是另一方佔上風時改寫 `overruled_reason`。放手一搏的結果寫出推進或倒退多少、氣血扣多少。**回合不叫模型潤色**（以前在鎖內等模型，全服跟著等）。
- **越強越有份量、進場給職位**（試玩回饋 2026-10-08，Joy：「玩家越強應該越有份量，而不是一視同仁……進場時可以根據屬性給大家職位」）：實力＝20＋0.5×min(威力, 400)（`battle_instance.strength`；舊的 40＋0.4×min(威力,150)、最多 100 只差兩倍）。整季機器人季末威力 14 天 195～397、週末 91～262，新手約 25：份量比新手 32.5 對練上去的 120～220，週末 2～4.6 倍、14 天約 5 倍。放手一搏成功的推進乘實力÷100（夾在 0.5～2）；失敗不乘。職位照本人五屬性最高的那一項（`role_for`，同分照臂力、身法、根骨、悟性、博聞的順序，五項一樣高沒有職位），加入時快照進 `BattleParticipant.role`：先鋒（臂力）強攻份量 +15%、斥候（身法）奇襲 +15%、盾陣（根骨）固守 +15%（算進份量快照，按鈕上的分數就看得到）、軍師（悟性）放手一搏成功率模型評完再 +10、參謀（博聞）被剋時剋制係數低於 1 的那一截減半。數字在 `BattleTuning`（`roles`、`role_*`、`gamble_strength_*`）。決戰畫面寫「你的職位：…」，戰報寫「你以…出陣」。真人、臨時投效的散人、假人都走 `Game._battle_role`。
- **等待看得出在等人**：場景的回合那一格與「已選擇」按鈕寫「已送出 X／在場 Y，最遲 M 分 S 秒後結算」（`round_progress`；兩軍的人不算豪強）。推送指紋也算這個數（`server_push.world_fingerprint(progress=…)`），有人出手開著的分頁就更新。
- 框架是人寫好的（`content/battles.json` 的 `acts`／`outcomes`／`rounds_per_act`／`decisive_margin`），玩家只能在框架內影響要素；機器人是一等公民（補位湊人數，`bot_choose_action` 照風險反向加權，不選自由文字）。
- **放手一搏（使用者明確要求的核心樂趣）**：固定選項（穩守／猛攻）走查表（`BattleDef.action_tags`）。「放手一搏」是 20 字內的自由文字，機制效果必須真的隨玩家寫的內容變化——使用者明確否決過「不管打什麼結果都一樣」那一版（「我就是希望看到玩家的奇葩操作對戰局產生影響」）。做法：**模型只評一個成功率（0～100），擲骰與推進、損耗公式全由引擎**（`FreeTextGamble`，風險＝100−成功率）。**對戰局只有小影響，主要的代價是自己的氣血池**（試玩回饋 2026-10-08，Joy：「個別玩家如果失敗除了稍微影響大局比較嚴重的懲罰是扣自己的氣血，自己的扣到0就自己先出局」；舊值讓五個人亂寫就把全官軍推到 50→5）：成功推進 2＋風險×0.06（最多 8）、扣氣血池上限的 5%；失敗最多倒退 1（風險 25 以上），扣氣血池上限的（0.1＋風險×0.004），成功率 0 失手扣五成、兩次就倒下出局；同一邊一回合放手一搏合起來最多 ±5（`side_trend_cap`，超過時多一句「各路奇招互相牽扯」）。輸入框旁邊寫「寫得越險……重傷的是你自己」（`Game.battle_free_text_note`），成功率照舊不事前顯示。重演（12 官軍、五次 45／5／0／0／0 全失手、其餘固守）：舊值 50→1 黃巾得勢，現在 50→39 兩軍膠著（`test_the_playtest_battle_replayed_is_no_longer_a_rout_for_the_yellow_turbans`）。評估在**行動鎖外**做（`server.battle_text` 三段：`Game.battle_text_request` → `model_call` 評分 → `Game.submit_battle_custom_action(text, rate)`；直接呼叫沒給分數才在鎖內用 `_quick_client()` 評），存進 `BattleRound.success_rates`；`resolve_round` 本身是純同步函式、不叫模型。評不到一律 `DEFAULT_FREE_TEXT_SUCCESS_RATE = 40`（刻意低於五成）。推動方向靠 `BattleDef.factions[0]` 是正向的約定。

### 模型呼叫
- 本機 Ollama，模型 `gemma4:26b`（`content/config.json` 的 `ollama_model`；`ollama_think: false`、`ollama_keep_alive: 12h`）。實測（模型已常駐）：隨口應對評分 4～5 秒、人物對話一輪約 9～13 秒、合成取名約 4 秒；冷啟動第一次載入約 32 秒。trycloudflare 約 100 秒就切斷一個請求。
- **三段式**（照人物對話 `server.prepare_dialogue` 的做法）：A 鎖內很快地開單（`Game.dialogue_request`、`Game.forge_request`、`Game.fight_request`、`Game.free_text_request`，只讀）→ B 鎖外叫模型（`companion_agent.prepare_turn`、`naming.generate`、`fight_llm.judge`、`event_llm.assess_event_success_rate`；不碰狀態、不拿鎖）→ C 鎖內整個重驗再套用（`Game.choose(prepared=…)`、`Game.forge(…, proposed=…)`、`Game.choose(fight=…)`、`Game.answer_event`），對不上就丟掉、照沒有模型的路走。開爐取名的 B 段預算是 `naming_budget_seconds`（60）扣掉 A 段等鎖的時間，`naming.propose(…, budget=)` 照給出去的逾時扣、用 client 的複本；伺服器的開爐一律給 `proposed`（不必叫模型時是 `NO_NAME`），所以鎖裡從不取名。C 段的名字再過 `naming.recheck`，重名在登記時原子判斷，過不了走退路字表（種子是配方鍵＋這一季的天機，不看誰先到）。之後的模型佇列只會換掉 B 段。
- **還留在鎖內的模型呼叫**：大事潤色（`world.check_thresholds`／`fire_by_id`）、重複事件與重遊的點綴句（`flavor`）、沒給分數的放手一搏（腳本、測試）、鎖內才備料的對話與每隔一陣子的記憶整理／性情漂移、沒給 `proposed` 的開爐與沒給分數的隨口應對（整季機器人、腳本、測試）。**一律拿 `Game._quick_client()`，不要直接用 `self.client`**：逾時 `in_lock_model_timeout`（15 秒，這是每一步的上限）、不重問；一次拿鎖期間第一次失敗之後，後面的鎖內呼叫都不叫（`_model_budget`；`server._locked` 每次拿到鎖先 `reset_model_budget()`）。**全服斷路器**：任何一次拿鎖裡鎖內的模型呼叫失敗或逾時，`server.py` 打開 `MODEL_BREAKER_SECONDS`（180 秒），這段時間每一次拿鎖一開始額度就用完、直接用固定文字；時間到之後的第一次照常叫，又失敗再打開；開、關各印一行（不寫是誰）。鎖外的路徑不歸它管。
- **繁體**：模型產出的文字（對話、敘事、選項、標籤、名字、點綴）一律過 `zh.to_traditional`：純 Python 的 `opencc-python-reimplemented`、`s2tw` 模式（只轉字、不換詞——`s2twp` 會把「的士卒」換成「計程車卒」，FB-014），繁體輸入原樣通過（FB-018，「里、斗、了」不會被改錯），之後再套一張異體字表 `VARIANTS`（OpenCC 放過日式新字體「鉄」）；import 失敗退回手寫對照表。**要「保證繁體」只靠 OpenCC 不夠。**
- **保底值會把「模型壞了」偽裝成「模型給了中庸的答案」**：成功率評不到退回 40，可是模型對爛寫法正常會評 0～5；曾經因為 `ollama_client` 把 `0` 當成缺值，所有灌水的寫法都被抬到 40（2026-10-05 已修，`tests/test_ollama_client.py`）。驗模型的機率評估要先看有沒有保底警告（`scripts/try_event_llm.py` 會印）。LLM 相關的東西定案前要用真模型跑一次。
- **匿名**：首創者、第一個練成絕學的人寫給別人看的名號在登記當下記下（`MartialArt.creator_shown`／`master_shown`、`Insight.creator_shown`；匿名是「某位少俠」），之後照它寫；名號本身照舊存著當身分。

### 介面（`web/`）
- 伺服器只給資料、畫面自己做：沒有建置步驟的原生 JavaScript（`web/app.js` 一個檔）。底部五個分頁 **江湖／修練／煉製／輿圖／見聞**（見聞＝戰報、大勢、傳聞、江湖史、紀錄），設定與管理者工具收在右上角齒輪。頂上狀態列（體力、氣血兩條＋銀兩、心得；點名號展開：名號獨佔一行、頭銜第二行〔一段一個 `.who-seg`，不能叫 `seg`〕、屬性、「可配 N 點」與五顆＋鈕、隊伍）。
- 登入狀態是 cookie（`tx_session`），伺服器記憶體裡對應帳號；**重開伺服器要重新登入**。前端每 10 秒打 `/api/main`，分頁在背景時不打、上一次還沒回來不打、內容沒變不重畫。
- **江湖頁**：劇情文字在上、行動在下；375×812 上「剛剛」、場景與整排行動都在第一屏（企劃者要的是按完不用捲就看得到結果）。平常閒著時（選單上有「打坐」）行動是一排五顆「水墨氣勁」按鈕：探索、遊歷、打坐、交友（沒有時是求見）、移動（點了在下面展開走法與「前往」）；其他只在此地才有的行動收在「此地還能做 N 件事」。事件、對話、路上、決戰的選單照舊是一排按鈕。第一季另有公告卡、本週軍令卡、戰況圖卡。
- **修練頁**（`pagePractice`）：身上的功法卡、練成鈕（寫價錢）；每一門武學一列（`owned_arts`：品質、熟練度、融的意境）可修練（含「服下破境丹」）、改練、熔煉；意境可化成心得；等著取名的絕學多一張定名表單；名冊與人物卡。
- **煉製頁**（`pageCraft`）：太極火爐左右兩格放「一門武學＋一個意境」、「兩門武學」（第二門當 `other_art` 送出）或「兩個意境」，點有東西的那一格拿出來；挑東西在爐子下面的武學與意境清單；說明那一行即時更新（`/api/forge_line`），「開爐」緊接在它下面；等結果時整座爐子晃動；第一季手上有伏筆物品時多一列「伏筆物品」；最底下摺疊「背包」（素材，有破境丹時另起「傳奇道具」小標題）。
- **輿圖**：四個圖層，可拖、可縮放；點地點看詳情，「安排前往」是步行／趕路／疾行三顆（`/api/travel` 帶 `mode`，照 `Game.travel_options()` 畫）。

## 量表與教訓

### 好玩度量表（企劃者 2026-10-03 提的方法，`scripts/fun_run.py`）
企劃者的話：「你要假裝自己是一個新玩家，甚麼都不知道，然後有新東西……你的好玩度會上升，反之如果你的行動看到重複出現過的，那你的好玩度會下降，重複越多次下降越多」。
- **定案的算法**：每條管道（事件、意境、合成出來的功法〔配方首創／查表〕、對手、地點）各自算「每次碰到它，有幾成給了你新東西」（−100～+100）再平均（`FunLog.balanced`）；整季沒出現的管道算 −100。單一總分（`FunLog.score`，每百行動的密度）只留著對照，**不要拿它下結論**——總分會隨「玩了多久」無上限累積，被觸發頻率高的管道支配。
- 實作上刻意處理：新而沒有收穫的首見只拿一半分；**機制動作的重複（移動、遊歷、練功、療傷）不扣**，只扣敘事內容的重複；遞增懲罰夾上限；輸出分項、每日淨值的時間軸、最後一次看到新東西是第幾天。
- **校準先於結論**：`--calibrate` 用行為重現造出已知比較無聊的歷史狀態（`--no-craft --no-train`、`--no-train`、現在），指標排不對就是指標錯了。計畫一拿掉素材煉製之後校準剩這三個狀態；10/3 四個狀態時量到種子落差 36 分 < 狀態差距 93 分，現在的數字沒重量。當時最大的問題是事件管道（茶館說書一季 27～37 次），之後有了防重複輪替（`events.rotation_pool`）。
- **量不到的事**：挫折（連續失敗、不可預期的損失）。新角色連輸三場、氣血見底這種坑，這個指標看不出來，要另外量或實機試玩。

### 量平衡與試玩的教訓（還在用的）
- **量平衡之前先確認機器人會用到那個機制**（舊稱「第三層」的教訓）：`bot.py` 不會煉製的那段時間，所有平衡數字描述的都是「忽略新玩法的玩家」。`bot.forge_and_cultivate`、`allocate_points` 就是為此存在。
- **以後要在「什麼都沒發生」的分支上掛東西，先確認那個分支真的會被走到**：舊版探索 100 次有 100 次撞到事件，掛在「一無所獲」後面的素材與遭遇戰一次都沒執行過。
- **不要憑有限的試玩就斷言某個機制「不存在」**，下結論前先查 content。
- **實機試玩**（用真實 `content/` 跑真正的 `Game`，每步印出所有選項、偵測「全部 disabled」或「選項組合連續多輪不變」）抓得到單元測試看不到的死路：體力歸零全部 disabled、龍頭人物碰不到、裝飾用的按鈕、對玩家隱形的數值變化、新角色照著引導走把自己打死。資訊透明（勝算、成功率、還差多少）是這類坑最常見的解法。
- **重現歷史缺陷要連同期的程式行為一起退回**：缺陷常常是「檢查沒有」加上「當時的策略比較笨」兩件事一起造成的。
- 判準只寫有依據的那一條；判準不通過時先確認是重現不夠真、還是指標看不見，不要急著調參數迎合直覺。
- **任何「用 Game 跑整季」的腳本都要先開季**（`store.open_season(now)`；`bot.play_season` 自己會開），不然停在籌備中、什麼都不會發生。

## 歷史（已完成或已取代，細節看原文件）

- **Gradio 介面**（`app.py`，至 2026-10-03）：已換成 `server.py`＋`web/`；`requirements.txt` 不再裝 gradio／pandas／numpy（這台機器封鎖過 pandas 帶進來的 DLL）。舊計畫寫 `app.py` 的地方讀成 `server.py`。
- **三對三戰鬥** `battle.py`：sanguo-companions 合併時換成 `encounter.py` 的單次判定；`scripts/simulate.py` 因此死掉，2026-10-03 刪除（替代品：`fun_run.py`、`sim_server_bots.py`、`bot.play_season`＋observe）。
- **無限煉製**（素材＋素材 → 功法，`craft.py`，2026-10-01～10-04，`specs/2026-10-01-無限煉製-design.md`）：由武學與成長取代（武學＋意境、取消素材合成）；`craft.py`、`tests/test_craft.py`、`Config.xinde_cost_factor`／`craft_xinde_*` 已刪。留下來的有：配方全服共享、首創者取名、每季清空、`zh.py`、退路字表、禁用名單、`MartialArt.note`、功法庫與改練。
- **自創武功**（`team.create_skill`）與 10/2「限次數」、10/3「自創與融合」設計：企劃者 2026-10-05 在武學與成長設計取消自創，程式已拿掉；《自創與融合》整份作廢。
- **「練功免費」**（10/1、10/2 兩次決定，與第三層「不要再提收費」）：2026-10-05 由武學與成長設計 4.7 推翻（心得管學、體力管練）。當時量到的事實（隨機一季心得收入很少、兩門開局幾分鐘就練滿）是推翻的依據之一。
- **平衡五層**（2026-10-02）：三階素材沒有來源（補了鎮山塔奇遇與素材可得性檢查）、遭遇戰機制上不會發生（遊歷做回真正的行動）、白燒的爐子（擋重煉；現在是「結果你已經有了就不准合」與「合到你已經有的不收錢」）、等級無用（補上氣血門戶名冊設計 §1 的內傷與氣血係數，方案 A1；運氣與門檻改成難度的比例；§1.4 第 1 條的「高 10 級勝率 60～70%」已在設計裡改寫掉）。現在的規則見上面「屬性、威力與氣血」。
- **引導順序**：練功排到出城之前（t4 在 t3 前面）；開局就送兩門基礎武學。
- **flaky 測試** `test_create_skill_practice_and_heal_handlers`：原因是練功受傷的機率沒固定種子，已修（測試裡把 `practice_injury_chance` 設 0）；連同 `tests/test_app.py` 一起不在了。
- **LLM 對話夾簡體字**：已由 `zh.py` 解決。
- **舊模型** `qwen2.5:14b`：放手一搏的成功率排序是用它實測定案的；煉製取名 27～83 秒也是它的數字，換 `gemma4:26b` 後約 4 秒。
