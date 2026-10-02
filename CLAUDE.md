# CLAUDE.md

《天下大勢》文字武俠原型。權威文件：`docs/superpowers/specs/2026-09-27-天下大勢-design.md`（設計）、`docs/superpowers/plans/`（實作計畫）。

## 架構
- `tianxia/`：純 Python 規則引擎，**不得 import gradio**。`engine.Game` 是唯一對外門面。
- `content/`：所有遊戲內容（JSON），載入時由 `tianxia/content.py::validate` 交叉檢查。
- `app.py`：Gradio 介面，只負責顯示與接線。
- `tianxia/encounter.py`：單次判定的遭遇戰（`sanguo-companions` 合併後取代了舊的 `battle.py` 三對三全自動戰鬥，那個檔案已經不存在了）；只處理數字，不 import 內容模型。
- `tianxia/battle_instance.py`：全服即時多人戰鬥（黃巾決戰）的純邏輯——集結選陣營、逐幕逐回合鎖步、回合結算、機器人補位。資料存在共用世界狀態的 `active_battle`。
- `tianxia/team.py`：門下、內力、心得升級與散功、武學配置；把人物與武學轉成戰鬥單位；檢定由誰出手；戰前勝算（固定種子模擬 40 場，依完整陣容快取）。
- `tianxia/battlelog.py`：戰鬥紀錄（`GameState.battles`，最近 20 場）、關鍵時刻、場景戰鬥卡片與戰報分頁的文字。
- `tianxia/skillview.py`：「門下」頁面的說明文字（武學白話說明、人物卡、武學欄、武學庫）；只讀狀態、不改數值，說法以 `battle.py` 的實際規則為準。
- `tianxia/atlas.py`：大地圖的資料（純資料與文字）：視野、大區歸屬（地點座標落在哪個大區多邊形，區外歸最近的大區）、最省體力的路線、四個圖層要標的東西、地點詳情與「安排前往」的條件；勝算只在敵情層與詳情欄才算。
- `tianxia/mapview.py`：把 atlas 的資料畫成 SVG：大地圖（江湖輿圖）與場景旁以你為中心的小地圖（從大地圖截一塊，畫法與視野同大地圖，視窗外兩站以內的摸清地點在邊緣標方向）。
- `tianxia/server_bots.py`：伺服器假人的名號、個性、作息（純函式，不碰檔案也不 import 引擎）。
- `tianxia/bot_policy.py`：假人照陣營目標做一個動作，只走 `Game` 的公開行動，不呼叫 LLM。
- `tianxia/bot_runner.py`：假人程式的核心，每一輪補人（先叫醒退隱的、沒有才新建）、叫醒、讓在線的假人做事。
- `tianxia/fileio.py`：Windows 檔案被占用時的重試（存檔、全服紀錄共用）。
- `run_bots.py`：假人程式的入口，每隔 `bot_tick_seconds` 呼叫一次 `BotRunner.tick()`，跟 `app.py` 同時開著。

## 原則
- 數值全部由規則引擎決定，執行時不接 LLM。
- 武學、人物名稱必須原創，不用金庸等作品的專有名詞。
- 檢定分兩種：`Check.by` 為 `"team"`（預設，派出戰隊伍中該屬性最高的人）或 `"self"`（修行類，只看本人）。
- 改內容後跑 `pytest`：`tests/test_real_content.py` 會讓機器人玩完整季，抓出內容錯誤。
- 賽季由管理者開：全服第一次開局停在「籌備中」，管理者（`content/config.json` 的 `admins`，暫時用名號認人）在設定頁按「開季」；季結束進入「休季」，管理者按「開啟下一季」。換季時同伴全部重獲自由、自創武學名字全部釋出、天機 +1（同名長出不同武學）。測試內容用 `auto_open_first_season: true` 直接開季。升級前就存在的 `saves/world/state.json` 沒有「已開季」的紀錄，升級後會停在籌備中，管理者按一次「開季」即可；如果那一季在升級前就已經結束，管理者先按「開季」、再按「開啟下一季」。管理者名號要專用、難猜，而且不要拿來平常遊玩——任何人打出這個名號就有管理者權限，用 gradio.live 公開連結分享時尤其危險。
- 陣營（`content/scenario.json` 的 `factions`）：玩家開局是散人，在陣營的 `join_at` 地點按「投靠」，或拜入陣營名下的門派；劇本有分陣營時，全服決戰只能站自己陣營那邊，散人與不在交戰雙方的陣營不能參戰，只在一旁觀戰、照常遊玩。狀態列的名號後面顯示門派、陣營（兩者都有時寫成「門派・陣營」），都沒有才是散人。
- 伺服器假人（`docs/superpowers/specs/2026-10-02-伺服器假人-design.md`）跟真人完全一樣、看不出來：「是假人」只記在存檔的 `PlayerState.bot`，任何畫面、榜單、戰鬥名單、主控台輸出都不能顯示或透露；假人只透過 `Game` 的公開行動做事，不呼叫 LLM。
- `app.py` 與 `run_bots.py` 是兩個程式、共用同一份全服紀錄與存檔：每次「補算時間＋做動作＋存檔」都要包在 `WorldStateStore.action_lock()` 裡（伺服器等到拿到為止，假人等不到就跳過）。
- 投靠要確認一次（先按 `faction:<id>`，再按 `faction:confirm`）；陣營人數看全服投靠名冊（`WorldStateStore.faction_counts()`）。
- 管理者（試玩期是 `Rayal`）在設定頁可以立刻開戰、觸發大勢門檻或世界事件、推動大勢線；效果跟自然發生一樣（`Game.admin_start_battle`／`admin_fire`／`admin_push_trend`）。

## 指令
- 執行：`.venv/Scripts/python.exe app.py`（http://127.0.0.1:7861）
- 測試：`.venv/Scripts/python.exe -m pytest -q`
- 平衡模擬：`.venv/Scripts/python.exe scripts/simulate.py 30`
- 伺服器假人：`.venv/Scripts/python.exe run_bots.py`（跟 `app.py` 同時開著）
- 假人整季模擬：`.venv/Scripts/python.exe scripts/sim_server_bots.py --seasons 2`

### 開發伺服器的啟動方式（這台機器上的慣例）
不要用 Bash 工具背景執行 `app.py`（會被背景任務追蹤器砍掉）。用 PowerShell `Start-Process`
完全分離啟動，輸出導到 `server_out.log`/`server_err.log`，再輪詢 log 等 `*.gradio.live`
公開連結出現。要重啟時先 `netstat -ano | grep ":7861"` 找出真正在聽那個 port 的 PID
（`Start-Process` 回傳的 PID 常常跟實際佔用 port 的不同），`taskkill //PID <pid> //F` 關掉
再重新啟動。

## 全服即時多人戰鬥（黃巾決戰）

好感度/聲勢推到門檻（`content/scenario.json` 的 `huangjin_60` 門檻，`starts_battle`）會開啟一場
全服共享的決戰：集結期選陣營（逾時系統自動分配、優先補人數少的一邊）→ 逐幕逐回合鎖步
（所有在場者都送出行動、或回合逾時代選保守行動，才結算這一回合）→ 結算結果寫回共用賽季。
劇本有分陣營（`scenario.json` 的 `factions`）時，上面「自動分配、補人數少的一邊」不適用：
玩家只能替自己的陣營出戰（集結時只看得到自己那一邊，晚到的人也只會補進自己那一邊）；打不了
這場仗的人（散人、不在交戰雙方的陣營）在戰鬥進行中照常遊玩，場景上仍看得到戰場、標明在一旁
觀戰。場上沒有任何人能打（沒人參戰或全都倒下）時，回合一逾時就用 `outcomes` 最後那個無條件的
保底結果收場（`battle_instance.end_without_fighters`），不會把全服卡住；換季
（`WorldStateStore.next_season`）也會清掉沒打完的戰鬥。
機器人是一等公民（測試湊人數用，正式營運也要用來增加活躍感）。設計上**不是全程 LLM 自由
發展**，而是有一份人工寫好的框架（`content/battles.json` 的 `acts`/`outcomes`），玩家只能在
框架內影響要素。

### 自訂行動的「賭局」機制（使用者明確要求的核心樂趣）
固定選項（穩守/猛攻）走查表：`BattleDef.action_tags` 決定推動戰局與扣氣血的固定數字。
但「放手一搏」是一個 20 字內的**自由文字輸入框**，機制效果必須真的隨玩家寫的內容變化——
使用者明確否決過「不管打什麼結果都一樣、文字只當敘事素材」那一版（原話：「意思是不管打
什麼都是一樣的結果是嗎」「我就是希望看到玩家的奇葩操作對戰局產生影響」）。

最終設計把責任切開，既讓文字真的有影響、又沒有破壞「不信任 LLM 算數字」這個專案慣例：
**LLM 只評估一個 `success_rate`（0~100 成功率），真正的擲骰與傷害/推進幅度公式完全由系統
決定**（`FreeTextGamble`，`models.py`）。定案前有實測過真實本機模型（`qwen2.5:14b`）：
同一組測試行動各跑 3 次，成功率的排序穩定且合理（例如「獨自殺入敵陣，直取波才首級」三次
都落在 ~25%/高風險區間），所以模型可以信任來做機率估計，但不能信任它直接給機制數字。

實作要點：
- `assess_action_success_rate`（`battle_instance.py`）在**送出的當下**呼叫（還沒進檔案鎖），
  結果存進 `BattleRound.success_rates`，`resolve_round` 本身維持純同步函式、只消費算好的
  資料，不在鎖裡面呼叫 LLM。失敗（連不上、解析失敗）一律退回 `DEFAULT_FREE_TEXT_SUCCESS_RATE
  = 40`（刻意低於五成，「評估失敗就當它比較冒險」）。
- 推動方向的正負靠 `BattleDef.factions[0]` 是「正向」這個約定（`resolve_round` 的 `sign`）。
- 機器人不選 `free_text` 選項（它寫不出有意義的描述）。

## 實機試玩（以新玩家視角）找出並修掉的卡關點

使用者反映「遊玩體驗很差甚至沒辦法玩下去」，要求以新玩家視角實際玩、逐一修掉卡住的地方。
做法是寫一個腳本，用**真實 `content/`（不是 tests/fixtures）**跑真正的 `Game`，每步印出
所有選項、隨機選一個、偵測「全部 disabled」或「選項組合連續多輪不變」就停下來。這個方法
抓到的問題是單元測試完全看不到的（測試都是直接設好狀態驗證單一行為，不會發現「玩下去會
走進死路」）。四個修好的問題（commit `0cc6cfd`、`13d7a82`、`f8ff25a`）：

1. **體力歸零是真正的死路**：所有選項（連移動都）會變 disabled，完全無事可做。體力只靠
   現實時間每 5 分鐘回 1 點（等一次行動要 ~50 分鐘），唯一出路是去翻「門下」頁的閉關分頁
   （而且 `seclude()` 根本不回體力）或設定頁裡標著「測試用」的時間快轉鈕——新玩家不可能
   知道。修法：新增**永遠 enabled** 的 `act:rest`（打坐歇息），直接呼叫
   `_advance_player_local(HOUR)` 只推進玩家自己的進度。**刻意不用 `advance()`**：那個會連
   共用賽季時鐘一起快轉，一個人想歇息不該把全服的大勢/倒數也推走。
2. **8 位 `kind=locked` 龍頭人物有 7 位完全碰不到**：`options()` 判斷要不要顯示「交遊」時
   只看 `has_events_here(loc, "socialize")`（有沒有人工寫的劇情事件），從來沒問過
   `_deep_interaction_target()`（真正按 `talk_at` 找龍頭人物的那個函式）。八個 `talk_at`
   地點裡只有盧植那個剛好有一個**無關的**劇情事件，所以只有他能對話，其餘七位（張角/張寶/
   張梁/何進/皇甫嵩/朱儁/董卓）人設/好感度 tag 都寫好了卻永遠觸發不到。修法：條件加上
   `or self._deep_interaction_target() is not None`。
3. **主畫面「練功」按鈕是裝飾品**：`_act()` 在扣體力那行**之前**就回傳一句「請去門下頁」的
   提示，所以雖然標籤寫著「（體力 10）」其實不扣也不做事。已整個從 `options()` 移除（門下
   導覽鈕本來就在，而 `t4_practice` 引導步驟實測也會由真正的練功路徑完成，沒有東西依賴它）。
4. **`change_trend` 從頭到尾是靜音的**：只有一條大勢線「第一次浮現」那一刻會回傳訊息，
   之後每一次變動都只是悄悄改數字。而黃巾聲勢開局就已浮現，所以玩家做的每個相關行動都
   看不到任何回饋，只能自己開「江湖大勢」分頁比對數字。修法：真的有變動時回傳一句
   「（黃巾聲勢 -2）」，風格跟既有的「銀兩 -5」「善名 +3」一致，會自動接在既有的
   `apply_effect`/`_squad_encounter` 訊息串裡。`sim_tick`（背景虛擬玩家）本來就丟掉
   `change_trend` 的回傳值，所以背景每小時的微幅推動依然安靜，不會洗版。
5. **招募沒有反饋**：`recruit_chance` 其實一直是跟好感度掛鉤的（基礎 35%，好感度 100 時
   到 85%），但畫面上沒顯示、失敗訊息也沒講好感度才是槓桿。修法：招募按鈕標籤顯示即時算出
   的成功率（沿用 `_cost_option` 既有但沒人用過的 `note` 參數，跟 `_choice_label` 顯示戰鬥
   勝算是同一套慣例），失敗訊息改成明講「先多來幾趟交遊」。順手修掉一個真 bug：
   `attempt_recruit` 的 `duel_chance_on_fail` 分支印「你惹上了一場決鬥」卻完全沒有任何機制
   效果，跟它自己 docstring 寫的「失敗有代價」矛盾——現在會真的賠銀兩
   （`duel_fail_silver_loss`，會夾到 0 不會倒扣）。

### 踩過的坑（記下來避免重踩）
- **新增「永遠 enabled」的選項會打壞 `bot.py` 的整季模擬**：`play_season()` 用「沒有任何
  enabled 選項」當作「該呼叫 `game.advance()` 推進遊戲時間」的訊號。`act:rest` 永遠 enabled
  之後這個訊號永遠不成立，遊戲時間推進大幅變少，`test_bot_plays_a_full_season` 要跑到接近
  20000 步上限才結束，整個測試套件時間翻倍。修法：`bot.py::pick()` 把 `act:rest` 排除在
  候選之外（跟 `bot_choose_action` 排除 `free_text` 選項是同一個模式——機器人不需要給真人
  用的保底）。**以後再加這類「無條件可選」的選項，記得一併檢查 `bot.py`。**
- **不要憑有限的試玩就斷言某個機制「不存在」**：我一度跟使用者說「聲勢幾乎沒有推動管道」，
  後來實際翻 `content/events/*.json` 才發現有 20 個事件選項會推動 `huangjin`（包含黃巾別部
  營寨一個 -25 的波才任務線），每個有 `enemies` 的地點打贏遭遇戰也會按 `train_trend` 推。
  機制一直都很完整，真正的問題只是它對玩家隱形（見上面第 4 點）。**下結論前先查 content。**
- **`tests/test_app.py::test_create_skill_practice_and_heal_handlers` 是既有的 flaky 測試**，
  單獨跑會過、在特定執行順序下會失敗（練功受傷機率用到沒固定種子的亂數）。跟這次的改動
  無關，不要誤以為是自己改壞的。
- 在這台機器上寫一次性的 Python 驗證腳本時，記得先把 stdout 包成 UTF-8
  （`sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")`），
  否則印中文會噴 `UnicodeEncodeError: 'cp950' codec can't encode...`。

### LLM 對話的繁體中文問題（未解決）
`companion_agent.py` 的 system prompt 已經加了「全程使用繁體中文」的指令，但實測只是**部分
改善**，生成內容裡還是會夾雜簡體字（實際看到過「孙坚」「这」「说」「话题」「闻言」）。
這是模型行為的限制，不是 prompt 寫法問題。如果要真的解決，應該在輸出端做確定性的轉換
（例如 OpenCC），而不是繼續加指令。目前維持現狀、記錄為已知問題。

## 「心得」沒有用途：已決定維持免費、只加提示（附帶推翻了原本的前提）

原本的問題陳述：`team.py::practice()`/`create_skill()` 兩條路徑都是完全免費、無限次、沒有
任何心得門檻的——玩家在劇情裡打仗、閉關攢的「心得」從來不需要花掉，想練到滿等直接一路點
到底就好。`Config.xinde_cost_factor`（第 n 成升到 n+1 成需要 `factor × n`）這個欄位還在
`models.py` 裡，但**整個程式碼裡沒有任何地方真的讀它**（只有舊的設計文件
`docs/superpowers/plans/2026-09-29-第一階段1a-戰鬥核心.md` 寫過 `upgrade_cost()` 的構想，
從來沒實作）。（順帶確認過：門下的練功操作**本來就會**寫進同一份江湖紀錄 journal，回到
江湖畫面看得到，所以「UI 完全切開」不是問題所在。）

**使用者決定選項 (2)：維持練功免費，只在心得擱著沒用時加個提示。**（另兩個被否決的選項是
(1) 比照設計文件讓練功真的消耗心得、(3) 先不動留為已知問題。）

**動手前的實測推翻了「心得會累積到一大堆」這個前提，記錄下來避免以後又照這個錯誤印象做
設計**。用 `bot.play_season` 跑真實 `content/`、三個 seed 量心得餘額（練功免費，所以餘額
就等於整季總收入，沒有任何東西會扣）：

- **隨機玩完一整季（14 天）的心得總收入只有 20~96**。所以「累積到 300/500 才提示」這種
  門檻在正常遊玩下**永遠不會觸發**。心得的問題不是「攢成一大堆沒處花」，是**收入本身就
  很少**；要賺多得刻意閉關（`seclusion_xinde_per_hour = 15` × 悟性加成），隨機機器人幾乎
  不選閉關。
- **兩門武學在第 0.2~0.3 天就全部練到第十成**，整季剩下的 13.8 天練功系統完全失效。這比
  原本寫的「想練到滿等直接一路點到底」更嚴重：它不是「可以很快練滿」，是**開局幾分鐘內
  必定練滿**。
- 順帶證明選項 (1) 照現有數值做會完全不能玩：`xinde_cost_factor = 20` 代表單門 1→10 成要
  20×(1+…+9) = **900**、兩門 1800，而整季只賺到 ~50，**差了 20 倍以上**。以後若真的要回來
  做消耗制，`xinde_cost_factor` 必須連同心得收入一起重新校準，不能只實作 `upgrade_cost()`。

**實作**：因為前提被推翻，提示的觸發條件不能用「心得很多」，改成「心得擱著沒用、而且確實
還有功夫可以練」。`skillview.py::practice_hint(state, content)` 在心得 ≥
`Config.xinde_hint_threshold`（新增欄位，預設 50，刻意訂得低才可能觸發）**且**內功或武學
還沒到第十成時，回傳一句「💡 你已攢下 N 點心得。去「門下」自創或鍛鍊{內功/武學}不花一分
一毫，別讓它擱著。」，由 `engine.py::status_text()` 接在數值列後面。重點：
- 放在**主畫面**狀態欄而不是門下頁，因為真正需要這句話的就是「從來沒進過門下、心得一路
  擱著而武學還停在第一成」的玩家，提示只出現在他不會去的那一頁等於沒做。
- 兩門都練到第十成就不再提示（`todo` 清單為空回傳 `None`），免得變成嘮叨；文字也只列出
  真正還能練的那一門。
- 放進 `skillview.py` 是因為那個模組的定位就是「只讀狀態與內容、只產生文字，不改任何
  東西」，這句提示完全符合；不是選項、不影響 `bot.py`（CLAUDE.md 上面那條「新增永遠
  enabled 的選項會打壞整季模擬」的坑不適用，這只是一行文字）。
- 測試：`tests/test_skillview.py` 四個（低於門檻安靜、兩門都沒學時兩個都列、只列還沒練滿
  的那一門、全滿就閉嘴）、`tests/test_engine.py` 一個（`status_text()` 三種狀態）。588 個
  測試通過，並用真實 `Game` 實例印出四種狀態的實際畫面驗證過。

### 連帶發現：`scripts/simulate.py` 整個是死的（還沒修）

查心得收入時發現 `scripts/simulate.py` **在 import 階段就炸掉**：
`ModuleNotFoundError: No module named 'tianxia.battle'`——`battle.py` 在 sanguo-companions
合併時就被 `encounter.py` 取代了，這支腳本沒跟著更新。它還呼叫了兩個同樣不存在的東西：
`team.upgrade_cost()`（從來沒實作，見上面）、`team.battle_rules()`/`team.team_units()`。

所以 CLAUDE.md「指令」那節寫的 `平衡模擬：.venv/Scripts/python.exe scripts/simulate.py 30`
目前是一條跑不動的指令。**這次刻意沒修**：要復活它得把「付費方 vs 免費方本隊交手勝率」
那整套重寫到 `encounter.py` 的單次判定模型上，那是獨立的一件事，不屬於「心得提示」的範圍。
這次量心得收入是改用 `bot.play_season` + `observe` callback 直接測（照
`tests/test_real_content.py` 的方式 mock 掉 `OllamaClient.chat_structured`/`chat_text`），
沒有依賴 simulate.py。

## 下一個 session 的待辦（2026-10-01 交接）

**先確認工作目錄**：這些待辦全部屬於 `C:\Users\User\Documents\ai_story-tianxia`
（分支 `feature/sanguo-companions`）。上一次交接就是因為在 `C:\Users\User\Documents\ai_story`
（分支 `feature/conquest-route-redesign`，另一個完全不同的遊戲）開 session，載入到錯的
CLAUDE.md，白繞了一圈才找到正確的 worktree。**開工前先 `git worktree list` 核對一次。**

### 1. 把「心得提示」那組改動提交掉（已完成、只差 commit）
工作區目前有 6 個檔案未提交，588 個測試已經全部通過、也用真實 `Game` 實例驗證過四種狀態的
畫面輸出：`tianxia/skillview.py`（新增 `practice_hint`）、`tianxia/engine.py`
（`status_text()` 接上）、`tianxia/models.py`（新增 `xinde_hint_threshold`，預設 50）、
`tests/test_skillview.py`（4 個）、`tests/test_engine.py`（1 個）、`CLAUDE.md`（上面那節）。
要決定的只有 commit 訊息，以及要不要順便 push。

### 2. 無限煉製方向：先寫 spec，還是直接做最小一刀？（最大的一件，等決定）
使用者提的新方向：武功/武器玩法比照 [Infinite Alchemy](https://infinialchemy.com/)——元素
素材合成功法、功法與功法再合成，素材從地圖探索／戰鬥獲勝獎勵／奇遇取得；另外要玩家之間的
互動（偷竊、仇殺、決鬥、結義、同盟）。使用者的話：「從蒐集材料到應用 LLM 特色變強，然後跟
歷史人物 NPC 互動，推動大勢」。

已經查證並討論定案的部分，**下個 session 不用重新推導**：
- **現成可當地基的三樣東西**：`martial_arts.generate_from_name()`（名字即配方的純函式，
  文字→雜湊→屬性/品質/威力，同名同結果）、`SharedWorldState.created_skills`（**全服配方
  登記表**，`claim_skill_name()` 在檔案鎖內原子判斷，正好等於無限煉製「第一個發現者定義
  配方、之後所有人看到同一結果」的快取）、`ATTRIBUTES` 八元素（陰陽剛柔快慢虛實）+
  `ATTRIBUTE_COUNTERS` 相剋表。
- **與原則「數值全部由規則引擎決定，執行時不接 LLM」的衝突，解法已定**：照專案已有的兩個
  先例（`generate_from_name` 人給語意/引擎給數值、`FreeTextGamble` LLM 只估 success_rate）
  切開——合成時先查配方登記表，命中就直接回傳同一結果（**零 LLM 呼叫、全服一致**）；沒命中
  才呼叫 LLM 一次，而且**只要它產生名字（+一句說明），一個數字都不準碰**，再把名字丟進
  既有的 `generate_from_name()` 得到所有數值，最後用 `claim_skill_name()` 原子登記。這樣
  「LLM 不決定數值」字面上仍然成立，無限可能來自命名空間而不是數值自由度，而且 6~8 秒的
  LLM 成本只在首次發現時付一次。
- **唯一還需要設計的公式**：品質若純由名字雜湊決定，兩個頂級素材可能合出下品，「蒐集材料
  變強」就斷了。解法方向是讓**輸入的稀有度位移品質機率分佈**（`CREATED_QUALITY_WEIGHTS`
  現成），雜湊只在位移後的分佈內抽。這是整個系統的平衡核心。
- **規模誠實**：**目前完全沒有道具/素材/背包系統**（`PlayerState` 只有 `stats`/`flags`，
  戰鬥獎勵只有 exp/心得/銀兩，沒有掉落），素材是全新一套：資料模型＋`content/` 掉落表＋
  背包欄位＋存讀檔＋UI，約等於同伴系統那個量級，不是一個增量。
- **兩個有證據的風險**：(a) 煉製出的名字會**永久登記進 `created_skills`**，不是轉瞬即逝的
  對話句，所以已知未解的簡體字洩漏會變成永久污染——這是終於該上 OpenCC 的具體理由；
  (b) 原則第二條要求武學名稱原創、不用金庸專有名詞，但隔壁 conquest 分支實測生成時直接
  跑題到小龍女/楊過/趙敏/李莫愁，LLM 來命名功法必定產出九陰真經之類的東西，**過濾必須
  在 `claim_skill_name()` 之前執行**（登記是永久的，事後補救不了）。
- **玩家互動建議晚一步**，而且有個前置問題要先回答：目前玩家彼此**根本不會相遇**（決鬥只是
  招募失敗的罰款 `duel_fail_silver_loss`，唯一同場是全服決戰），偷竊/仇殺要能非同步改動
  離線玩家的狀態，`mutate()`＋檔案鎖解決了原子性，但沒有通知管道、沒有離線保護、沒有同意
  模型。「玩家在哪裡遇到彼此」要先有答案（大地圖可能是）。
- **順帶的好處**：這個方向直接修掉上面量到的「練功免費導致第 0.2 天就滿等、整季剩 13.8 天
  沒有成長曲線」，而且**心得終於有用途**（拿來當煉製消耗，比「練功要花心得」自然得多；
  被否決的選項 (1) 可以用這個形式正當地回來，但係數要照實際收入重新校準）。

**建議的最小第一刀**（照專案慣例，這種規模該先寫 spec 到 `docs/superpowers/specs/`）：
素材模型＋探索/戰鬥掉素材＋門下「煉製」（素材→功法，走上面那條快取鏈），**先不做
功法+功法、先不做 PvP**。

### 3. `scripts/simulate.py` 是死的：要修還是刪？（等決定）
詳見上一節。目前 import 階段就炸（`tianxia.battle` 已不存在），還呼叫
`team.upgrade_cost()`/`battle_rules()`/`team_units()` 三個不存在的函式，所以 CLAUDE.md
「指令」那節的 `平衡模擬` 是一條跑不動的命令。要復活得把「付費方 vs 免費方本隊交手勝率」
整套重寫到 `encounter.py` 上。

### 4. `mapping-architecture-flow` skill 缺 `example.html`
已安裝到 `C:\Users\User\.claude\skills\mapping-architecture-flow\SKILL.md`（裝在個人層
而不是專案層，因為有兩個 worktree，裝進其中一個另一邊吃不到）。但使用者只上傳了 SKILL.md，
沒有它依賴的 `example.html`——SKILL.md 的「做法」第 2 步是「複製 `example.html`、CSS 與
渲染函式不動」，少了模板會卡住。本機兩個 worktree、`~/.claude`、Downloads/桌面都找過沒有，
使用者發佈過的 Artifact 也只有四個（Momentum Ledger、提早進場調查、動能加倉回測、
訊號還是雜訊），沒有架構圖那一份。兩條路：使用者補上原檔，或第一次執行時照 SKILL.md 已經
寫得很具體的規格（流程圖座標、四種狀態、`NODES`/`EDGES`/`TREE` 結構）重建一份《天下大勢》
架構圖，再存成 `example.html` 當以後的模板（那份 example 本來就是這個 skill 的產物）。
