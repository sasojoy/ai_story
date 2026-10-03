# CLAUDE.md 待修清單

CLAUDE.md 裡跟現況對不上的地方。PM 收集，**企劃者同意後**才改（規矩：不經企劃者同意不改 CLAUDE.md）。改的時候以程式為準；改完一項就從這裡刪掉。

最後整理：2026-10-03，主線 56c0eeb（新網頁接上主線之後）。

| # | 在哪 | 現在寫的 | 實際情況 | 誰提的 |
|---|---|---|---|---|
| 1 | 「自訂行動的賭局機制」實作要點 | 放手一搏的成功率「在送出的當下呼叫（還沒進檔案鎖）」 | 舊 app.py 是先拿鎖才評成功率；換成 server.py 後要重查一次。煉製取名、決戰敘事、性情漂移與記憶梳理也都在鎖裡 | PM 對程式時發現 |
| 2 | 「LLM 對話的繁體中文問題（未解決）」整節 | 未解決、記為已知問題 | 已解決：`zh.to_traditional` 會把敘事、選項、分類標籤都轉成繁體（無限煉製設計 §5.7 也這樣寫）。另外地圖擴充開發正把轉換從 s2twp 改成 s2tw，不再把「的士卒」轉成「計程車卒」 | PM |
| 3 | 賭局機制、無限煉製「真實模型實測」 | 只記 qwen2.5:14b 的實測 | 對話模型已換成 gemma4:26b（`content/config.json` 的 `ollama_model`）；煉製取名 27~83 秒是 qwen2.5:14b 量的，換模型後沒重量 | PM |
| 4 | 無限煉製那節 | 「一次煉製 16~51」，沒寫凡品配方 | 凡品配方不花心得；成本算例已改（兩個天品 ＝ 28） | PM |
| 5 | 架構 `team.py` 那行 | 戰前勝算「依完整陣容快取」 | 沒有快取，每次重算 40 場 | PM |
| 6 | 「下一個 session 的待辦」開頭 | 工作目錄 `C:\Users\User\Documents\ai_story-tianxia`；架構圖 artifact `c63483c5…` | PM 在 `C:\Ray\專案\天下大勢`，開發在 `C:\Ray\專案\ai遊戲`；架構圖改成 `docs/superpowers/architecture/三國篇架構.html` 發佈的 artifact | PM |
| 7 | 「新方向：自創武功要限次數」那節 | 要限次數，五件事還沒決定 | 已改定成「自創與融合」設計（先不限次數、跟融合一起開，放開觀察），不進第一次 beta | 軍備物資設計 session |
| 8 | 第 138–140 行 | `tests/test_app.py` 的 flaky 測試（現在式） | `test_app.py` 已刪掉（flaky 的原因後面第三刀也寫了已修） | Infra |
| 9 | 第 262–264 行 | 門下頁的輸出數量改成 `app.MENXIA_OUTPUTS`（現在式） | `app.py` 已刪掉，那個常數不存在了 | Infra |
| 13 | 「下一個 session 的待辦」開頭與其他寫到分支名稱的地方 | 分支 `feature/sanguo-companions` | 2026-10-03 起主線改成 `main`（之後直接在 main 上開發；舊遊戲在 `legacy/ai-story-main`，feature/sanguo-companions 不再更新） | PM |
| 12 | 「全服即時多人戰鬥（黃巾決戰）」第 57～68 行，以及「架構」的 `battle_instance.py` 那行 | 只寫「逐幕逐回合鎖步」、框架是 `acts`/`outcomes`；沒寫回合上限 | 規則沒寫錯，是漏了 FB-016 的新規則。建議補：每幕固定 `rounds_per_act` 回合（黃巾決戰 3 幕 × 3 ＝ 9 回合，約 45 分鐘），換幕只看回合數、不看戰局；打完最後一回合，或某回合戰局偏離起點達 `decisive_margin`（到 90／10），由 `battle_instance.decide_outcome` 看戰局決定結果。「不會把全服卡住」現在主要靠回合上限（以前推力抵銷時戰局停在 50，要等氣血磨光）。框架改寫成 `acts`/`outcomes`/`rounds_per_act`/`decisive_margin`；`battle_instance.py` 的說明可補「回合上限與收場判定」 | Infra |
| 11 | 約 270 行、298～299 行（無限煉製「拍板的四件事」與真實模型實測） | 繁簡轉換用 OpenCC 的 `s2twp` | FB-014 起改用 `s2tw`：只轉字、不換台灣用語（以前會把「的士卒」轉成「計程車卒」），異體字表照留。本清單第 2 筆的說法也一併以此為準 | Infra |
| 10 | 「指令」的執行那一行 | 只寫 `server.py` 與 `--share` | Infra 的 W5 起伺服器預設只綁 127.0.0.1，要開放區網加 `--lan`（會多印一行提醒）；`--share` 不受影響。W5 進主線後才成立 | Infra |
