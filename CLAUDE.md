# CLAUDE.md

《天下大勢》文字武俠原型。權威文件：`docs/superpowers/specs/2026-09-27-天下大勢-design.md`（設計）、`docs/superpowers/plans/`（實作計畫）。

## 架構
- `tianxia/`：純 Python 規則引擎，**不得 import gradio**。`engine.Game` 是唯一對外門面。
- `content/`：所有遊戲內容（JSON），載入時由 `tianxia/content.py::validate` 交叉檢查。
- `app.py`：Gradio 介面，只負責顯示與接線。
- `tianxia/battle.py`：三對三全自動戰鬥引擎，只處理數字（不 import 內容模型）；除了戰報文字，也回傳結構化的戰鬥事件（絕招、控制、倒下）與我方每人的傷害、控制次數。
- `tianxia/team.py`：門下、內力、心得升級與散功、武學配置；把人物與武學轉成戰鬥單位；檢定由誰出手；戰前勝算（固定種子模擬 40 場，依完整陣容快取）。
- `tianxia/battlelog.py`：戰鬥紀錄（`GameState.battles`，最近 20 場）、關鍵時刻、場景戰鬥卡片與戰報分頁的文字。
- `tianxia/skillview.py`：「門下」頁面的說明文字（武學白話說明、人物卡、武學欄、武學庫）；只讀狀態、不改數值，說法以 `battle.py` 的實際規則為準。
- `tianxia/atlas.py`：大地圖的資料（純資料與文字）：視野、大區歸屬（地點座標落在哪個大區多邊形，區外歸最近的大區）、最省體力的路線、四個圖層要標的東西、地點詳情與「安排前往」的條件；勝算只在敵情層與詳情欄才算。
- `tianxia/mapview.py`：把 atlas 的資料畫成 SVG：大地圖（江湖輿圖）與場景旁的大區小地圖。

## 原則
- 數值全部由規則引擎決定，執行時不接 LLM。
- 武學、人物名稱必須原創，不用金庸等作品的專有名詞。
- 檢定分兩種：`Check.by` 為 `"team"`（預設，派出戰隊伍中該屬性最高的人）或 `"self"`（修行類，只看本人）。
- 改內容後跑 `pytest`：`tests/test_real_content.py` 會讓機器人玩完整季，抓出內容錯誤。

## 指令
- 執行：`.venv/Scripts/python.exe app.py`（http://127.0.0.1:7861）
- 測試：`.venv/Scripts/python.exe -m pytest -q`
- 平衡模擬：`.venv/Scripts/python.exe scripts/simulate.py 30`
