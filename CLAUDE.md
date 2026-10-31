# CLAUDE.md

《天下大勢》文字武俠原型（三國篇，第一季黃巾之亂）。

權威文件（**計畫寫的是當時的打算，跟程式對不上時以程式為準**）：
- 設計：`docs/superpowers/specs/`。總設計 `2026-09-27-天下大勢-design.md`；武學、屬性、戰鬥過程、人物資質以 `2026-10-05-武學與成長-design.md` 為準（第十四節是人物資質）；第一季 `2026-10-02-第一季黃巾之亂-design.md`、`2026-10-04-第一季濃縮版-版本目標.md`；線上架構 `2026-10-02-線上架構-design.md`；伺服器假人 `2026-10-02-伺服器假人-design.md`。
- 實作計畫：`docs/superpowers/plans/`。
- **開發規範手冊**（分層與功能包、測試分級、派工、合併、交接；企劃者 2026-10-30「寫成開發規範手冊，讓其他人遵守」）：`docs/superpowers/specs/2026-10-30-開發模式-design.md`。技能檔照它改，對不上時照手冊；手冊跟程式對不上時照程式（手冊最後一節是落地補註）。
- 試玩回饋（FB-編號）：`docs/superpowers/feedback/試玩回饋.md`；裁決：`docs/superpowers/rulings/`；主機端怎麼開伺服器、給網址、備份、換季：`docs/superpowers/feedback/beta-主機端操作.md`。
- 架構流程圖：`docs/superpowers/architecture/三國篇架構.html`（PM 發佈成 artifact，隨進度更新）。

## 工作目錄與分支

- GitHub `sasojoy/ai_story`，`main` 是線上正式版。**2026-10-18 起新功能不在 `main` 上做**（企劃者）：功能分支（現在是 `feature/formal-season`，正式季整合）從 `develop` 開，分批的工作樹從功能分支開；QA 過了合進功能分支、功能做完合進 `develop`（之後可能另外部署 `develop` 做內測），企劃者說可以上線才合回 `main`。分支、測試與合併的規矩全寫在專案技能 `.claude/skills/tianxia-flow/SKILL.md`，開工、派工、合併前先看。（2026-10-03～10-18 直接在 main 上開發；`feature/sanguo-companions` 不再更新；舊遊戲在 `legacy/ai-story-main`。）
- 這台機器有兩份 clone：`C:\Ray\專案\天下大勢` 是主要的那份（main 在這裡合併、推上 GitHub；專職開發的工作樹在它的 `.claude/worktrees/`）；`C:\Ray\專案\ai遊戲` 是另一份 clone，地圖擴充開發在它的 `.worktrees/` 裡做。**開工前先 `git worktree list`、`git remote -v` 核對一次**：曾經在另一個遊戲的目錄開 session，讀到錯的 CLAUDE.md，白繞一圈。
- `.claude/worktrees/` 底下的工作樹沒有 `.venv`：下面指令裡的 `.venv/Scripts/python.exe` 換成那份 clone 的絕對路徑（例：`C:/Ray/專案/天下大勢/.venv/Scripts/python.exe`）。
- 工作樹的檔案是 CRLF（`core.autocrlf=true`，git 裡存 LF）：用腳本改檔時先把 `\r\n` 轉成 `\n` 再比對，寫回時轉回去。

## 功能區塊（先看這張表，再讀要改的那一塊）

模組說明、規則速查、量表以前都寫在這份檔裡（約 10 萬 token，每個對話每一回合都要重讀）；2026-10-19 起按功能區塊切到 `docs/guide/`（企劃者「CLAUDE.md 請按照功能區塊切割開來」）。
- **開工前只讀這一次要碰的那一兩塊**，不要整批讀。派工的人在派工單上寫明要讀哪幾塊。
- 新規則、新模組寫進那一塊的導覽檔；這份檔只留跨區塊的原則、分支、指令與這張表（上限約 1 萬 token）。
- 模組沒列在表上的，照它做的事歸到最近的那一塊，順手補進表與導覽檔。
- 規則速查的寫法：數字都在 `Config`（`tianxia/models.py`，正式值以 `content/config.json` 與設定覆寫檔為準）；這裡只寫結構與現在的值，改數字不必改這一節的結構。

| 區塊 | 管什麼 | 模組（`tianxia/`） | 原本「規則速查」的節 |
|---|---|---|---|
| [核心與存檔](docs/guide/核心與存檔.md) | 門面、存檔與全服狀態、規則核心（條件與效果、事件、世界、性別、行狀與傳）、事件檢定、減法季的開關、真人量表 | database、world_state、characters、accounts、playlog、models、rules、gender、events、tiers、world、annals、biography、journal、guide、newbie、prologue、opening、storyline | 事件檢定 |
| [行動與地盤](docs/guide/行動與地盤.md) | 體力與行動、探索三選一、出陣、交友求見、閉關、移動、醫館、地盤易手、設伏與工事 | territory、sortie、explore_modes、training、gather_llm、clinic、ambush、works | 行動、屬性、威力與氣血、地盤易手（每季都有，`Config.territory`；`tianxia/territory.py`）、後期體力玩法（第一批，Joy 2026-10-16；2026-10-16 合進 main〔ff60ed83〕，正式內容三個開關都關著，數字等 21 天的季一起定） |
| [戰鬥](docs/guide/戰鬥.md) | 屬性與威力、單次判定、回合與戰法、大場面、頭目戰、擂台、全服決戰、江湖水漲 | encounter、team、rounds、tactics、battlelog、styles、fight_llm、duel、arena、arena_crowd、escorts、generals、battle_instance、tale、rise、terrain | 屬性、威力與氣血、戰鬥的演出與大場面、第一季濃縮版（`rules.season_one` 開著時才有）、江湖水漲（大場面、頭目、事件跟得上變強的人）、擂台賽（每季都有，`Config.arena`；設計 `docs/superpowers/specs/2026-10-14-擂台賽-design.md`）、全服決戰 |
| [武學與成長](docs/guide/武學與成長.md) | 等級、武學、意境槽、兩種合成、自創、絕學、口訣秘方、熔煉、傳功 | martial_arts、arts、insight_fx、insights、epiphany、fusion、create、secret_recipes、naming、signature、cultivation、library、chuangong、skillview | 行動、屬性、威力與氣血、武學與成長（武學與成長設計；計畫一～三、二之二、二之三、四、五都已在 main）、第一季濃縮版（`rules.season_one` 開著時才有） |
| [裝備與店面](docs/guide/裝備與店面.md) | 兵器、防具、坐騎、寶物、素材與四階、神器、鐵匠鋪、馬市、酒肆、打點與銀兩出口 | weapons、smithing、signature_arms、forge_secrets、divine、equipment、armor、mounts、treasures、materials、shopview、tavern | 武學與成長（武學與成長設計；計畫一～三、二之二、二之三、四、五都已在 main） |
| [大勢人物與賽季](docs/guide/大勢人物與賽季.md) | 季曆與時刻表、21 天季、7 天濃縮季、戰線推力與軍令、晉升、叛投、伏筆、大勢人物、人物活起來、同伴、章回主線 | calendar、checkin、timetable、figures、figure_life、relations、letters、orders、defection、foreshadow、front_lines、figure_aid、roster、chapters | 第一季濃縮版（`rules.season_one` 開著時才有）、挑戰大勢人物（每季都有）、人物活起來（每季都有，`Config.figure_life`；`tianxia/figure_life.py`） |
| [散人與玩家互動](docs/guide/散人與玩家互動.md) | 遊俠名號、懸賞榜、求兵、截殺、玩家卡、切磋、論武 | ranger、bounties、raid | 第一季濃縮版（`rules.season_one` 開著時才有）、散人、懸賞與截殺（每季都有） |
| [玉璽碎片](docs/guide/玉璽碎片.md) | 七片碎片、璽動與奪璽單挑、天命之季與天命之爭、碎片的獨門行動 | seal、seal_duel、seal_acts | 玉璽碎片（玉璽一；天命之爭是玉璽二） |
| [商城](docs/guide/商城.md) | 元寶錢包與帳本、商品表與允許的效果、購買發貨、月卡（每日領）、重修列傳、易名帖（改名當場生效）、封測發放、管理者工具、資料庫第 6 版 | mall、wallet、rename | —（2026-10-20 新開） |
| [地圖與介面](docs/guide/地圖與介面.md) | 輿圖資料與畫法、網頁各分頁與店面的畫面、江湖頁的本週卡與三方卡 | atlas、mapview、mapart、weekcard | 介面（`web/`） |
| [模型與假人](docs/guide/模型與假人.md) | Ollama 與三段式、繁體、省電與維修頁、伺服器假人、整季機器人 | ollama_client、power_save、zh、event_llm、server_bots、bot_policy、bot_runner、bot | 模型呼叫 |
| [量表與教訓](docs/guide/量表與教訓.md) | 量表與模擬腳本、好玩度量表、量平衡的教訓、歷史 | — | 量表與教訓、歷史（已完成或已取代，細節看原文件） |

## 原則

- **行動名稱**（企劃者 2026-10-04 定）：「遊歷」（舊稱歷練，`act:train`）、「交友」（舊稱交遊，`act:socialize`）；移動只剩步行、疾行兩種（企劃者 2026-10-12 拿掉趕路：「毫無存在的意義」；拿掉之前以趕路出發、還在路上的那一趟照原本的步調走完，`atlas.MODE_NAMES`、`TIME_SHARE`、`TravelMode` 還認得它）。舊文件寫舊名的，指的是同一個行動。有地盤的季（`territory.on`）遊歷（`act:train`）就是「出陣」（企劃者 2026-10-14）；探索三選一開著時（`Config.explore_modes`）「探索」是展開三顆的入口。
- **數值全部由規則引擎決定。** 模型只寫文字、評一個機率（放手一搏、隨口應對的成功率）、給一個夾過的優勢（大場面判讀，最多 ±`big_fight_swing` 個百分點），或從清單裡挑一個名字；擲骰、換算、損耗、獎勵都是引擎的事，引擎拿到模型的數字一律再夾一次。
- **引擎不讀電腦時鐘**：現在時間一律由 `Game.sync(now)`（設定 `Game.now`）或明確的 `now` 參數傳入。`tianxia/` 裡只有 `database.py`（等寫入權的期限）、`accounts.py` 與 `bot_runner.py`（注入的 `clock`）碰時間；模型呼叫的時間預算靠 HTTP 逾時扣，由 `server.py` 量好傳進來。
- **玩家看得到的時刻只有一個寫法**：第一季一律走 `calendar.point_text`（「第 N 週・週X HH:MM」，N 前後有空格）；寫時間的地方都經過 `calendar.stamp_text`／`Game.stamp`（狀態列第二行、下一件、軍令截止、江湖史、傳聞、戰報都是），不要在別處自己拼。開關關著時照舊「第2天 14:05」。
- **名字原創**：我們寫的內容（武學、人物、意境）不用金庸等作品的專有名詞。模型取的名字與玩家替絕學定的名字都過 `naming.name_problem`（禁用名單 `content/banned_names.json`、只能是中文、不能跟素材、人物、內容武學、意境、江湖上任何角色的名號同名），全服重名在登記時原子判斷。
- **改名之後 id 跟顯示的名字不同**（絕學定名只改顯示的名字）：寫給玩家看的一律用 `team.resolve_art(...).name`，認東西的一律用 id。
- **改內容後跑 `scripts/test_for.py`**（會挑到 `tests/season/test_real_content.py` 不含 slow 的那些，抓出內容錯誤、鎖住事件難度帶 `DIFFICULTY_BANDS`）；機器人用真實內容玩完整季的那幾條是 slow，要看就加 `--slow`。
- **賽季由管理者開**：全服第一次開局停在「籌備中」，管理者（`content/config.json` 的 `admins`，加上 `.local/admins.txt` 與 `TIANXIA_ADMINS`）在設定頁按「開季」；季結束（或管理者「立刻收季」）進入「休季」，管理者按「開啟下一季」。換季時：同伴全部重獲自由、等級武學歸零；全服登記的武學、配方、改過的名字、意境、第一個練成絕學的人都照季分開存，新的一季自然是空的；上一季的首創（合成、意境、絕學）寫進那一季的江湖史；天機 +1（同一個配方長出不同的東西）；沒打完的決戰清掉；跟人物的好感度只帶一成。測試內容用 `auto_open_first_season: true` 直接開季。資料都在資料庫；舊的 `saves/*.json`、`saves/world/state.json`、`saves/accounts/accounts.json` 不再讀取（企劃者 2026-10-03 決定不搬）。管理者的角色用 `scripts/set_password.py <帳號> --character <名號>` 建立並綁到帳號上，只有登入那個帳號的人進得了；玩家不能取管理者的名號。
- **第一季濃縮版的規則掛在開關後面**：`Config.season_one`（`config.json` 預設關，`weekend` 設定打開）加上這一季開季時蓋的章（`rules.season_one`）。開關打開時正在跑的那一季照舊用 beta 的規則；開關關著時 beta 一個字都不變，新功能一律先問 `rules.season_one`。**例外**（不看這個開關，企劃者 2026-10-08～10）：兵器（`Config.weapons`）、防具（`Config.armor`）、坐騎（`Config.mounts`）與寶物（`Config.treasures`）只看各自的 `enabled`（兵器第一批計畫自己的判斷；企劃者 2026-10-10 在裝備四欄設計 2.6 定四欄跟兵器一樣不掛：beta 那一季、上線那一刻正在跑的那一季也有；挑戰本人掉寶物寫在 `_challenge` 打贏那一支、不看第一季開關；挑戰本人已經每季都有，這條來源也每季都有）、懸賞榜（`Config.bounties.enabled`＋劇本有陣營）、遊俠名號與截殺（劇本有陣營；截殺的貢獻只在第一季記，`Config.raid.enabled` 是主機的緊急開關）、叛投、單人頭目戰、口訣與秘方、挑戰大勢人物本人（`figures.challenge_on`：人物表有人＋劇本有陣營；第一季以外另看 `Config.figure_challenge_every_season`；閉門不見、人物此刻站在哪跟著它；見「挑戰大勢人物（每季都有）」），還有操練推大勢照季長縮放（每一季都算；週末設定倍數 1、一個字都不變，FB-165）；地盤、出陣與領地爭奪是同一件事、沒有開關（`territory.on`＝`sortie.on`＝`conquest.on`：`Config.season_one` 開著、劇本寫了 `territory` 區塊、官軍黃巾兩軍都在、豪強分屬兩軍；2026-10-27 舊出陣拔河、割據佔地、攪局、修築工事拿掉，不看季上的章），探索三選一（`Config.explore_modes`）、盡頭阻力與季長縮放（`Config.push_resistance`）各看自己的 `enabled`（企劃者 2026-10-14；盡頭阻力與事件五折兩種季都有，PM 2026-10-14），全圖開放沒有開關（2026-10-27）。反過來，規則關著的季事件的大勢效果也照季長縮放（一季只會發生一次的不縮放：事件標了 `once`、或這一則效果這一下新立世界旗標〔例：擊敗波才立 `bocai_defeated`〕，`rules.apply_effect` 帶 `source="event_once"`，照原本的量推；FB-166），而且大勢門檻觸發的提前收季（黃巾稱霸）照第一季決定性勝利同一條：季曆第 `decisive_from_week`（10）週以前先不觸發、大勢照推、決戰照開照打，到了那一週還在門檻上才收季（`world.early_end_held`；「可能的結局」那一條補寫最早什麼時候會收季）（FB-165，PM 2026-10-12；第一季一個字都不變）。開決戰的大勢門檻（`starts_battle`，例 huangjin_60）也一樣：季曆第 `battle_from_week`（5）週以前推過了不開集結、不記成觸發過，到了那一週還在門檻上就開（`world.battle_held`；企劃者 2026-10-13「季中，第 5 週起才開」，FB-168；測試內容寫 1）。玉璽碎片的效果（傳承那一格）不看第一季開關，現世與璽動本來就只在有時刻表決戰的季；天命之季要第一季規則的章（新的一季沒有就延後到下一個有章的季，玉璽二）。
- **陣營**（`content/scenario.json` 的 `factions`）：玩家開局是散人，在陣營的 `join_at` 地點按「投靠」（要確認一次：先按 `faction:<id>`，再按 `faction:confirm`），或拜入陣營名下的門派；陣營人數看全服投靠名冊（`WorldStateStore.faction_counts()`）。全服決戰只有官軍、黃巾兩軍（沒有第三方：Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」），兩軍的人只能站自己陣營那邊；散人與不是交戰兩軍的陣營（地方豪強）可以在決戰的大區「臨時投效」交戰兩軍之一（`battle:enlist:<id>`，`Game._free_agent(definition)`；集結時能改投、開打了也能晚到），只算這一場：不改自己的陣營、不進投靠名冊、不算叛投、不記貢獻，戰功與論功算在投效的那一軍。散人的假人不投效、也不趕來；豪強的假人照兩軍的假人一樣擲「趕來參戰」（`bot_runner._battle_sides`、`Game.rally_region`），到了投人少的那一軍、一樣多照名號＋這一場的雜湊挑（`bot.enlist_pick`，整季機器人同一個）。狀態列的名號後面寫「門派・陣營・頭銜」（有哪幾樣寫哪幾樣），都沒有才是散人。
- **「此地還有」的窗口是 24 小時**（`Config.presence_seconds` 86400；Joy 2026-10-19「能真的碰到面的只有 10 分鐘內在線的人 這不好吧 至少拉長」→「就是要可以殺得到啊 延長到24小時怕被殺去城鎮」；以前 600）：同一地點、這麼久之內同步過、不在路上的人才列得出來、才互動得了（打招呼、贈物、結伴、切磋、論武、**截殺、通緝**都看它），酒肆查人的「此刻就在…」也不准比它寬（`tavern.seek_lines`，`tests/gear/test_tavern_seek_presence.py` 守這條不變量）。**下線也殺得到是刻意的**，代價由「城鎮類地點不能動手」擋（`Game.raid_refusal`）——不想被殺就在城鎮下線；另外還有新手期、同一對 3 小時冷卻、被截過 1 小時護身。邀請**不**跟著拉長（`invite_ttl_seconds` 1800）：切磋、論武要兩個人都在，隔一天才被接受的邀請只會變成一堆作廢訊息。**主機端那兩支刻意不讀這個數字**（拿 24 小時當「在線」的話，省電模式永遠不卸模型、監控頁永遠寫著幾十人在線）：`scripts/warm_keeper.py` 自己一個 `ONLINE_SECONDS`（600），`scripts/monitor.py` 的「在線」也是 600、另一行才寫「互動得到（24 小時內）」照設定讀。
- **伺服器假人跟真人完全一樣、看不出來**（`docs/superpowers/specs/2026-10-02-伺服器假人-design.md`）：「是假人」只記在存檔的 `PlayerState.bot`，任何畫面、榜單、戰鬥名單、主控台輸出都不能顯示或透露；隨檔送到每個玩家瀏覽器的 `web/` 檔連註解都不准寫「假人」「機器人」「bot」（`tests/bots/test_server_bots.py` 掃，FB-673）（回給玩家的拒絕話也一樣：名號被假人用掉、模型取到假人的名號，都回跟真人同一句）。假人只透過 `Game` 的公開行動做事；現在 `client=None`，一個模型都不叫，也不寫自由文字（放手一搏、隨口應對都排除）。**企劃者 2026-10-05 定：假人之後學會合成時，首創配方也要叫模型取名**（走同一條三段式，A、C 在 `action_lock` 裡，`bot_runner` 到時候要補 `reset_model_budget()`），不然「首創者是假人的配方名字都是字表風格」會被看出來。**已知看得出來的地方**（打造第二批）：假人打出神器原品一律「沿用譜名」，神器譜上名字等於譜名的原品比較可能是假人；要補就是假人也叫模型取名（三段式，同絕學定名的 `MasterJob`）。
- **兩個程式、一個資料庫、一把行動鎖**：`server.py` 與 `run_bots.py` 共用同一個資料庫，每次「補算時間＋做動作＋存檔」都包在 `WorldStateStore.action_lock()` 裡（一筆 SQLite 寫入交易；伺服器等到拿到為止，假人等不到就跳過）。伺服器每次進鎖先從資料庫重讀角色（`server._locked`）：資料庫是唯一的真實來源，`server.GAMES` 只是每個角色那份 `Game` 物件放的地方，拿來做決定的讀取都在鎖裡。**慢的模型呼叫不在鎖裡**：人物對話、開爐取名、大場面判讀、隨口應對都是三段式（見「模型呼叫」）；還留在鎖裡的模型呼叫一律用 `Game._quick_client()`，一步最多 `in_lock_model_timeout`（15）秒、一次拿鎖只容忍一次失敗，失敗一次全服 180 秒內鎖內都不叫模型（`server.MODEL_BREAKER_SECONDS`）。
- **管理者**（試玩期是 `Rayal`）在設定頁可以開季、收季、開下一季、立刻開戰、觸發大勢門檻或世界事件、推動大勢線、時間快轉，第一季還有時刻表與救場工具（排時間、跳到下一件、定戰況、定結果、清鎖定、取消決戰）；效果跟自然發生一樣（`Game.admin_*`），也可以幫玩家重設密碼。管理者目前認角色名號（`Game.is_admin()`），之後換成帳號權限。
- **登入**用帳號密碼（`tianxia/accounts.py`；設計見 `docs/superpowers/specs/2026-10-03-帳號密碼登入-design.md`）：線上版現在就是帳號密碼登入（伺服器只有 `/api/register`、`/api/login`，有網址的人都能註冊；線上架構設計原本定封測只開 LINE／Google、帳號密碼只留在開發與測試環境，那一條沒有做）。帳號和名號分開，一個帳號一個角色；帳號不存在與密碼錯、名號被真人或假人用掉，各自回同一句話，避免試出誰是假人。會改帳號或建立角色的動作都包在同一筆交易裡。
- **屬性只靠升級給的點**（武學與成長設計 6.2、6.3）：每升一級給 `stat_points_per_level`（1）點（30 級以後兩級一點，見「等級」），自己分配到臂力、身法、根骨、悟性、博聞（每項最高 `stat_cap` 15）；戰鬥不再隨機加屬性。前四項事件可以加（夾在 `stat_cap`，訊息照實際動了多少寫，被夾掉時多一句「已到頂」）；**博聞只能靠配點，任何獎勵都不能給、不能扣**（載入時檢查，企劃者 2026-10-05）。
- **根骨只從 `team.con_of(state, content, world, key)` 讀**：本人照存檔、同伴照他自己的；氣血上限、回血、損耗、氣血係數、狀態列與角色卡都走它。
- **身法讓落敗有機會閃成僵持**（`team.dodge_chance`），劇情戰除外；勝算不含閃避（勝算是贏的機會）。
- **戰況變化不對玩家露數字**：第一季開著時，推動戰線、割據的那一行是機器可讀的 `大勢@<線> ±N`，畫出來的那一刻才換成一句話、照看的人的陣營上色（`rules.front_chip`、`rules.humanize`）；戰報不收這種變化。畫面上寫的亂局條數與割據漲落方向**必須讀 `rules.chaos_fronts` 與 `rules.geju_per_day`**，不要另寫一份判斷。
- **新增「永遠按得下去」的選項要一併改 `bot.py::pick()`**：整季模擬用「沒有任何可按的選項」當推進時間的訊號（`act:rest`〔現在只剩序章的調息〕、喊停、路上的選項、會被打發的求見都已經排除）。
- **臨時腳本**：會開世界（`Game.new`、`open_world`）的一次性腳本先把 `TIANXIA_DB` 設到 repo 外的暫存檔，不然會開到這份 clone 的 `saves/tianxia.db`；印中文前先把 stdout 包成 UTF-8（`sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`），不然 cp950 會噴錯。**不要寫「多處替換、最後統一寫檔」的腳本**：中間一個 assert 失敗就整批回滾，印出來的訊息會讓人以為改好了。

## 指令

- 執行：`.venv/Scripts/python.exe server.py`（http://127.0.0.1:7861，預設只聽這台電腦；`--port` 換埠）。要給外面的手機：**固定網域 https://tianxiadashi.com**（2026-10-13 起，Cloudflare 具名 Tunnel `tianxia`，隧道是獨立行程、伺服器重開網址不變；做法與驗法在 `docs/superpowers/feedback/beta-主機端操作.md` 的「固定網域」，啟動時一併設 `TIANXIA_PUBLIC_URL=https://tianxiadashi.com`）——**所以不要再加 `--share`**，那是 trycloudflare 的臨時網址、每次重開都換。要讓同一個區網的裝置直接連：加 `--lan`（綁在所有網卡上、多印一行提醒；有網址的人都進得來）。
- 週末設定（第一季濃縮版）：兩個程式啟動前都設 `$env:TIANXIA_PROFILE = "weekend"`；啟動時印「設定：…」，兩邊要一樣。
- 測試（2026-10-07）：開發用的依賴在 `requirements-dev.txt`（`-r requirements.txt` 加 `pytest-xdist`；伺服器不用裝），裝好之後加 `-n auto`（或 `-n 8`）平行跑；這台 16 核整套約 1 分鐘，單一行程約 3 分 40 秒。venv 路徑有中文時 worker 要 `PYTHONIOENCODING=utf-8`，`tests/conftest.py` 在開 worker 前已經補上。網頁測試預設每個行程一個常駐 node，`TIANXIA_WEB_HARNESS=process` 改回每次各開一個。三種跑法：
  - **開發中與 QA**（企劃者 2026-10-18：平常只跑最小量；挑法照開發規範手冊 4.3，2026-10-31 起）：`.venv/Scripts/python.exe scripts/test_for.py`——跟 origin/develop 比（預設；功能分支的工作樹加 `--base origin/feature/<名字>` 或設 `TIANXIA_TEST_BASE`；base 沒 fetch 過會停下、結束碼 2）、加上還沒提交的改動，照功能群挑：`engine.py` 看改到 Game 的哪個方法、`models.py`／`state.py` 與核心模組跑核心測試（核心模組自己的測試＋`test_engine`＋契約與邊界）加 `-m smoke`、`server.py` 看路由、`web/` 跑寫到那個檔名的、內容改了跑 `test_content` 與真實內容不含 slow 的、`tianxia/features/<包>/` 跑那一包的 `tests/` 加核心契約；「import 了 engine」不再算相關。**slow 不自動跟，`--slow` 才加**（改到的測試檔本身照舊連 slow）；預設 `-n 4`；`--list` 只列不跑、寫每一段為什麼挑，`--count` 數條數，也可以直接給檔名（`scripts/test_for.py tianxia/fusion.py`），`--` 之後的參數原樣交給 pytest。改 `tests/conftest.py` 照改到的 fixture 挑、太廣就跑煙霧。develop 每天 03:30 在這台跑一次整套含 slow（`scripts/nightly.ps1`，結果在 `.local/nightly/latest.txt`）。
  - **平常的整套**：`.venv/Scripts/python.exe -m pytest -q -n auto`，不跑標了 `@pytest.mark.slow` 的（整季模擬、真實內容跑整季、量表與模擬腳本）。
  - **分支合併的那一刻**（Joy 2026-10-26：只有上 main 跑整套含 slow）：批合進功能分支、功能分支合進 develop、main 合回 develop／功能分支，只動 `web/`、文件、測試的只跑 `scripts/test_for.py --base origin/<要合進去的分支>` 挑的相關測試；動到 `tianxia/`、`content/` 的再加不含 slow 的整套 `.venv/Scripts/python.exe -m pytest -q -n auto`（Joy 2026-10-27）。**develop 合進 main 之前一定跑整套含 slow**：`.venv/Scripts/python.exe -m pytest -q -n auto -m "slow or not slow"`（或 `scripts/test_for.py --all`）。不寫 `-m ""`：PowerShell 5.1 會把空字串參數吞掉。
  - 新寫的測試要跑整季、整個腳本、或單一個超過一秒的，標 `@pytest.mark.slow`（整個檔都是就寫 `pytestmark = pytest.mark.slow`）。
  - **測試照區塊分資料夾**（2026-10-27 測試整理 2）：`tests/` 底下 `core/`（核心與存檔）、`acts/`（行動與地盤）、`battle/`、`arts/`、`gear/`、`figures/`（大勢人物與賽季）、`ranger/`、`seal/`、`mall/`、`map/`（地圖資料）、`web/`（整檔跑 node 的網頁測試）、`bots/`、`server/`、`season/`（整季、量表、真實內容），共用工具在 `tests/kit/`（webharness、conquest_kit……）；`tests/conftest.py` 把每個資料夾放上 `sys.path`，所以測試檔照舊用檔名互相 import，**檔名全 `tests/` 不能重複**。新測試放它測的模組那一塊；改哪一塊可以只跑那個資料夾（`pytest tests/arts`）。
  - **回饋單的測試寫進那個模組的測試檔，不開 `test_fb…` 新檔**（測試名可以帶 FB 編號；2026-10-27 測試整理 1b 把 53 個 `test_fb…` 檔併掉了，江湖頁第一屏、行動列、摺疊的網頁測試在 `tests/web/test_jianghu_page_web.py`）。搬進別的檔時，原本整檔的 `pytestmark` 改成每條測試自己的標記，不要讓 slow 的套到不 slow 的、反過來也不行。
  - 探索三選一、盡頭阻力兩個開關在測試內容（`tests/fixtures/content/config.json`）關著（舊的照地點比例自動抽還是序章的探索）；用正式內容、測舊探索／舊推力本身的舊測試叫 `tests/conftest.py::classic_rules(content)`（兩個一起關；共用的內容用 `monkeypatch.setattr(content.config.explore_modes, "enabled", False)` 這種只關一個），新規則的測試在 `test_explore_modes.py`、`test_push_resistance.py`。測試內容沒有陣營、沒有區塊：沒有地盤與出陣，是舊的遊歷與操練。
  - 全圖開放沒有開關了（2026-10-27 企劃者選「拿掉舊玩法和它的測試」，舊的摸清、視野、留意地形連 `Config.open_map`、`closed_map` 一起拿掉）；全圖開放的規則在 `tests/map/test_open_map.py`。
  - 領地爭奪沒有開關了（2026-10-27 企劃者選「拿掉舊玩法和它的測試」，舊的地盤拔河、出陣推線、攪局、修築工事連 `Config.conquest/sortie/territory/fortify` 的開關、`no_conquest` 一起拿掉）：用正式內容 week7、season21 就是領地爭奪，測試用 `conquest_kit.conquest_game`（出陣約戰關掉、攻一下就打一場）；出陣本身（獎勵、滿級心得）的測試在中立地（汝南荒野）出陣。
  - **「開關關著一個字都不變」每個開關只留一條**（2026-10-27 測試整理 3，照 Joy 10/25「不用測的要拿掉」）：兩個舊規則開關是 `test_explore_modes.py::test_the_old_explore_with_the_switch_off`、`test_push_resistance.py::test_the_switches_off_keep_the_old_push`（地盤、出陣、領地爭奪、全圖開放 2026-10-27 起沒有開關）。新功能不再另寫「關著照舊」的測試；墊片 `classic_rules` 只在測試真的靠舊規則時才叫。
- 伺服器假人：`.venv/Scripts/python.exe run_bots.py`（跟 `server.py` 同時開著）
- 幫帳號設密碼（主機端）：`.venv/Scripts/python.exe scripts/set_password.py <帳號> [--character <名號>] [--db <資料庫檔>]`（角色不存在時直接建立；密碼寫到 `.local/`，不印在畫面上）
- **把自己設成管理者（這台機器）**：在 `.local/admins.txt` 一行寫一個名號（`#` 開頭是註解）。`.local/` 在 `.gitignore` 裡，不會進版控、pull 下來也不會被蓋掉；臨時用也可以設 `TIANXIA_ADMINS=甲,乙`。兩者都**附加**在 `config.json` 的名單（`Rayal`）之上。
- 量表、整季模擬、真模型實測的指令都在 [量表與教訓](docs/guide/量表與教訓.md)。

### 開發伺服器的啟動方式（這台機器上的慣例）

完整步驟（含給網址、換季、備份、具名 Tunnel）見 `docs/superpowers/feedback/beta-主機端操作.md`。要點：
- 不要用 Bash 工具背景執行 `server.py`（會被背景任務追蹤器砍掉）。用 PowerShell `Start-Process`（或 `Invoke-CimMethod` 建 Win32_Process，工作階段結束也不會被收掉）完全分離啟動，輸出導到 `server_out.log`／`server_err.log`，**記下回傳的 PID**。網址是固定網域、不必等 log 印網址；驗證改成 `curl http://tianxiadashi.com/`（伺服器開著 200、沒開 502），隧道沒在跑就照「固定網域」那一節開起來。
- **引數一定要加 `-u`**（`python.exe -u server.py`）：stdout 導到檔案時 Python 會緩衝，沒有 `-u` 的話服務其實已經在聽 port、log 卻一直是空的。
- cloudflared（具名 Tunnel 與 `--share` 都要）裝在 `C:\Program Files (x86)\cloudflared`（`winget install Cloudflare.cloudflared`）；裝之前就開著的終端機找不到它，啟動前補 `$env:Path += ";C:\Program Files (x86)\cloudflared"`。
- **停的時候用 `/T` 關整棵**：`taskkill /PID <Start-Process 回傳的 PID> /T /F`（或在主控台 Ctrl+C）。只關「正在聽 7861 的那個 PID」會留下 cloudflared，重開後舊網址照樣進得到新伺服器（FB-021）。不確定有沒有殘留時，先停伺服器，再清掉連到 7861 的 cloudflared，最後才重開（指令在主機端操作文件）。
- `server.py` 與 `run_bots.py` 要開同一個資料庫、同一份設定：要用 `saves/tianxia.db` 以外的檔，兩個程式啟動前設同一個 `TIANXIA_DB`（兩個程式啟動時都會印出資料庫路徑與設定，設錯一眼看得出來）。
