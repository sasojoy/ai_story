# CLAUDE.md 待修清單

CLAUDE.md 裡跟現況對不上的地方。PM 收集，**企劃者同意後**才改（規矩：不經企劃者同意不改 CLAUDE.md）。改的時候以程式為準；改完一項就從這裡刪掉。

最後整理：2026-10-04，主線 987a996（路上三塊與 FB-020 之後）。

| # | 在哪 | 現在寫的 | 實際情況 | 誰提的 |
|---|---|---|---|---|
| 1 | 「自訂行動的賭局機制」實作要點 | 放手一搏的成功率「在送出的當下呼叫（還沒進檔案鎖）」 | 舊 app.py 是先拿鎖才評成功率；換成 server.py 後要重查一次。煉製取名、決戰敘事、性情漂移與記憶梳理也都在鎖裡 | PM 對程式時發現 |
| 2 | 「LLM 對話的繁體中文問題（未解決）」整節 | 未解決、記為已知問題 | 已解決：`zh.to_traditional` 會把敘事、選項、分類標籤都轉成繁體（無限煉製設計 §5.7 也這樣寫）。另外地圖擴充開發正把轉換從 s2twp 改成 s2tw，不再把「的士卒」轉成「計程車卒」 | PM |
| 3 | 賭局機制、無限煉製「真實模型實測」 | 只記 qwen2.5:14b 的實測 | 對話模型已換成 gemma4:26b（`content/config.json` 的 `ollama_model`）；煉製取名 27~83 秒是 qwen2.5:14b 量的，換模型後沒重量 | PM |
| 4 | 無限煉製那節 | 「一次煉製 16~51」，沒寫凡品配方 | 凡品配方不花心得；成本算例已改（兩個天品 ＝ 28） | PM |
| 5 | 架構 `team.py` 那行 | 戰前勝算「依完整陣容快取」 | 沒有快取，每次重算 40 場 | PM |
| 6 | 「下一個 session 的待辦」開頭 | 工作目錄 `C:\Users\User\Documents\ai_story-tianxia`；架構圖 artifact `c63483c5…` | PM 在 `C:\Ray\專案\天下大勢`，開發在 `C:\Ray\專案\ai遊戲`；架構圖改成 `docs/superpowers/architecture/三國篇架構.html` 發佈的 artifact | PM |
| 7 | 「新方向：自創武功要限次數」那節 | 要限次數，五件事還沒決定 | 方向已經改了兩次：10/3 改定成「自創與融合」設計；2026-10-05 企劃者在「武學與成長」設計定了**取消自創**，改成「武學＋意境 → 衍生新武學」，《自創與融合》整份作廢。這節整段可以刪掉，改成一行指向 `specs/2026-10-05-武學與成長-design.md`。程式改完之前，現有的自創仍照舊運作 | 武學與成長設計 session |
| 8 | 第 138–140 行 | `tests/test_app.py` 的 flaky 測試（現在式） | `test_app.py` 已刪掉（flaky 的原因後面第三刀也寫了已修） | Infra |
| 9 | 第 262–264 行 | 門下頁的輸出數量改成 `app.MENXIA_OUTPUTS`（現在式） | `app.py` 已刪掉，那個常數不存在了 | Infra |
| 13 | 「下一個 session 的待辦」開頭與其他寫到分支名稱的地方 | 分支 `feature/sanguo-companions` | 2026-10-03 起主線改成 `main`（之後直接在 main 上開發；舊遊戲在 `legacy/ai-story-main`，feature/sanguo-companions 不再更新） | PM |
| 12 | 「全服即時多人戰鬥（黃巾決戰）」第 57～68 行，以及「架構」的 `battle_instance.py` 那行 | 只寫「逐幕逐回合鎖步」、框架是 `acts`/`outcomes`；沒寫回合上限 | 規則沒寫錯，是漏了 FB-016 的新規則。建議補：每幕固定 `rounds_per_act` 回合（黃巾決戰 3 幕 × 3 ＝ 9 回合，約 45 分鐘），換幕只看回合數、不看戰局；打完最後一回合，或某回合戰局偏離起點達 `decisive_margin`（到 90／10），由 `battle_instance.decide_outcome` 看戰局決定結果。「不會把全服卡住」現在主要靠回合上限（以前推力抵銷時戰局停在 50，要等氣血磨光）。框架改寫成 `acts`/`outcomes`/`rounds_per_act`/`decisive_margin`；`battle_instance.py` 的說明可補「回合上限與收場判定」 | Infra |
| 11 | 約 270 行、298～299 行（無限煉製「拍板的四件事」與真實模型實測） | 繁簡轉換用 OpenCC 的 `s2twp` | FB-014 起改用 `s2tw`：只轉字、不換台灣用語（以前會把「的士卒」轉成「計程車卒」），異體字表照留。本清單第 2 筆的說法也一併以此為準 | Infra |
| 10 | 「指令」的執行那一行 | 只寫 `server.py` 與 `--share` | Infra 的 W5 起伺服器預設只綁 127.0.0.1，要開放區網加 `--lan`（會多印一行提醒）；`--share` 不受影響。W5 進主線後才成立 | Infra |
| 14 | 「原則」第 3 條 | 「武學、人物名稱必須原創，不用金庸等作品的專有名詞」（沒說適用範圍） | 企劃者 2026-10-04 定（FB-022）：玩家自創功法可以自由取名，不擋；這條原則管的是我們寫的內容與 AI 取的名字（煉製取名照舊套 `content/banned_names.json`）。建議補一句適用範圍，免得之後有人把擋名單套到 `team.create_skill` | PM |
| 16 | 「架構」清單，`tianxia/mapview.py` 那行後面 | 沒有 `mapart.py` | 輿圖美術（10/4）新增模組，建議補一行：「`tianxia/mapart.py`：輿圖的畫法零件（設色山水）：配色、座標寫法、路的二次曲線、河與山脊的平滑線、大區削角、照標籤的地點圖示、紅旗、外框與指北針，以及地形（山頭與樹讓開地點、路與河；只跟內容有關，每份內容算一次快取）。只 import `models`、不看視野；mapview 只管組合、視野狀態與名字避讓。」 | 地圖擴充開發 |
| 15 | 「開發伺服器的啟動方式」那段 | 「要重啟時先 netstat 找出真正在聽那個 port 的 PID，taskkill 關掉」 | 用 `--share` 時只關聽埠的 python 會留下 cloudflared，舊網址還會通到新伺服器（FB-021）。要用 `taskkill /T` 關 `Start-Process` 回傳的整棵，或在主控台 Ctrl+C；見 `feedback/beta-主機端操作.md`。另外裝 cloudflared 之前就開著的終端機 PATH 是舊的，啟動前補 `$env:Path += ";C:\Program Files (x86)\cloudflared"` | QA |
| 17 | 「心得沒有用途」那節（約第 162 行起）、無限煉製「拍板的四件事」第 2 條（約第 221 行）、平衡討論第三層「結案」（約第 348、408～430 行，含「不要再提第三次練功收費」） | 練功維持免費（10/1、10/2 兩次決定），第三層還寫了不要再提收費 | 2026-10-05 企劃者在「武學與成長」設計推翻了：心得管學、體力管練。練成、合成、合併花心得；修練花體力（每次 10）；熔武學退回八成心得。理由在 `specs/2026-10-05-武學與成長-design.md` 4.7。程式改完之前現有的免費練功照舊；改程式時跟第 7 筆（自創）一起改 | 武學與成長設計 session |
| 18 | 「架構」清單 | 沒有 `figures.py` | 濃縮版 T4（10/5）新增模組，建議補一行：「`tianxia/figures.py`：第一季的大勢人物：讀（state_of、主將、難度、此刻站在哪）、推（tick，季的事每曆時一次）、改（apply 是時刻表的人物結局與接位鏈，defeat 是挑戰打贏）；人物表在 content/figures.json，開季蓋章時種進 WorldState.figures；讀的函式不看開關，呼叫端要用 rules.season_one 擋。」 | 地圖擴充開發 |
| 19 | 「架構」清單 | 有 `craft.py`（煉製），沒有武學與成長的新模組 | 武學與成長計畫一（`plans/2026-10-05-武學與成長-1-武學核心.md`）實作後：拿掉 `craft.py`、補上計畫一新增的模組各一行。**等計畫一做完才改**，現在 craft.py 還在 | 武學與成長設計 session |
| 20 | 「無限煉製（Infinite Alchemy 方向）」整節與它底下的第一～三刀、平衡討論各層 | 煉製是武功的主要來源，素材＋素材合成 | 武學與成長（2026-10-05 企劃者審閱通過）取代：武學＋意境合成、取消自創與素材合成。這節整段可以縮成一段歷史紀錄，指向 `specs/2026-10-05-武學與成長-design.md`。**等計畫一做完才改** | 武學與成長設計 session |
| 21 | 「架構」清單（`battlelog.py` 那行附近沒有 `front_lines.py`）；也沒提 `content/front_lines.json`、`content/check_lines.json` 的內容 | 沒有這些 | FB-064（分支 fb-064）新增：`tianxia/front_lines.py`（戰況變化的說法：機器可讀的寫法 `大勢@<線> ±N`、三段變動大小 `BANDS`、雜湊挑句；純文字、不看內容模型）與 `content/front_lines.json`（`sides`／`generic`／`by_side`／`geju`，照 `check_lines.json` 的模型、載入、驗證、挑句）。第一季規則開著時 `rules.change_trend` 對三條戰線與豪強割據回機器可讀的寫法，江湖紀錄照舊加總，畫的那一刻由 `rules.front_chip` 換成一句話、照看的人的陣營上色（`journal.ChipFn`、`Game._chip`）；`Game._log` 用 `rules.humanize` 把回給呼叫端與存進 log 的話也換成一句話；戰報（`BattleRecord`）不收這種變化（`battlelog.split_changes(for_record=True)`）。`check_lines.json` 也換成 S1 的 45 句（四項屬性各五段、每段兩句，加通用五句）。建議架構清單補一行 `front_lines.py`，原則補一句「戰況變化不對玩家露數字」 | FB-064 開發 |
| 22 | 「原則」的伺服器假人那條（「假人只透過 `Game` 的公開行動做事，不呼叫 LLM」），以及 `bot_policy.py`、`run_bots.py` 的說明 | 假人不呼叫 LLM | 企劃者 2026-10-05 定：**假人合成出全服第一次出現的配方時，也叫 AI 取名**（跟真人走同一條三段式：鎖內準備 → 鎖外取名 → 鎖內確認套用），免得「首創者是假人的配方名字都是字表風格」被看出來。其餘照舊不叫 LLM（不對話、不放手一搏）。假人目前還不會合成，這條等假人學會合成時才生效；建議原則改寫成「假人除了合成首創的取名，不呼叫 LLM」 | PM |
| 23 | 「架構」清單（`rules` 沒有單獨一行，可補在 `engine.Game` 那段）；「原則」的第一季規則 | 沒有寫戰況圖卡與態勢那一行的資料從哪來 | FB-065（分支 fb-065）：`rules.chaos_fronts`（在亂局的戰線，含兩端 `chaos_low`～`chaos_high`）是 `geju_tick` 的漲落、江湖頁圖卡的「亂局」標與亂局帶、態勢那一行、見聞→大勢的割據說明共用的同一份；`rules.chaos_note` 是那句話（「N 條戰線在亂局，割據漸長」／「沒有戰線在亂局，割據漸消」，N 寫阿拉伯數字），`rules.stance_sum_note` 是「三條戰線合計」。第一季規則開著時 `Game.status_data()` 多送 `fronts[].chaos`、`chaos_band`（{low, high}，前端不寫死 35／65）、`stance_notes`（{sum, haoqiang}）；關著時這幾個鍵都沒有。建議原則補一句：「畫面上寫的亂局條數與割據漲落方向必須讀 `rules.chaos_fronts`，不要另寫一份判斷」 | FB-065 開發 |
