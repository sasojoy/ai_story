# CLAUDE.md

《天下大勢》文字武俠原型。權威文件：`docs/superpowers/specs/2026-09-27-天下大勢-design.md`（設計）、`docs/superpowers/plans/`（實作計畫）。

## 架構
- `tianxia/`：純 Python 規則引擎，**不得 import gradio**。`engine.Game` 是唯一對外門面。
- `content/`：所有遊戲內容（JSON），載入時由 `tianxia/content.py::validate` 交叉檢查。
- `app.py`：Gradio 介面，只負責顯示與接線。

## 原則
- 數值全部由規則引擎決定，執行時不接 LLM。
- 武學、人物名稱必須原創，不用金庸等作品的專有名詞。
- 改內容後跑 `pytest`：`tests/test_real_content.py` 會讓機器人玩完整季，抓出內容錯誤。

## 指令
- 執行：`.venv/Scripts/python.exe app.py`（http://127.0.0.1:7861）
- 測試：`.venv/Scripts/python.exe -m pytest -q`
- 平衡模擬：`.venv/Scripts/python.exe scripts/simulate.py 30`
