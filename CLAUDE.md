# CLAUDE.md

給 Claude Code 的專案速覽。完整規劃請見 [VISION.md](VISION.md)（產品願景）、[ARCHITECTURE.md](ARCHITECTURE.md)（架構債與分階段重構計畫）、[ROADMAP.md](ROADMAP.md)（功能路線圖）——這三份是本專案的權威文件，開始任何工作前先讀 ARCHITECTURE.md 的「分階段重構順序」了解目前走到哪一步。

## 目前進度（重構，依 ARCHITECTURE.md 第四節分階段順序）

- [x] Stage 0 — 補測試安全網（`tests/test_streaming.py`）
- [x] Stage 1 — 清死程式碼/死設定
- [x] Stage 2 — 存檔系統整併為 account-based
- [x] Stage 3 — 共用 fallback/選項模組（`src/options.py` + `config/npc_fallbacks.json`，commit `699551d`）
- [ ] Stage 4 — 親密度分級 SSOT（接上 `config/npc_stages.json`）**← 下一步**
- [ ] Stage 5～8 — 尚未開始

## 近期修復：LLM 輸出截斷導致選項跑進劇情文字

**症狀**：實際試玩（本機 `qwen2.5:1.5b`）時，新選項文字有時會出現在 narrative 段落裡（例如「選項 A) ... 選項 B) ...」被寫進故事內容），且下方按鈕偶爾顯示跟上一輪一樣的舊選項。

**根因**：`src/ollama_client.py` 的 `num_predict` 原本是 512，但這個遊戲要求「150~300 字中文敘事 + 完整 5 個選項 + 其他狀態欄位」，換算下來常超過 512 tokens，回應被硬生生截斷，模型就把選項清單寫進 narrative 裡湊字數，或截斷修復出來的 `options` 陣列不完整而觸發保底機制。

**修復**：
- `num_predict` 512 → 1024（`chat_structured` 兩處呼叫 + `chat_structured_stream` 預設值）
- `src/models.py::normalize_llm_dict` 新增防線：偵測「選項 A)」/「选项A)」這類清單開頭標記並自動從 narrative 截斷（`tests/test_engine.py` 有覆蓋，含「一般語句提到『選項』兩字不應誤刪」的邊界測試）

**已知但刻意不採用的方案**：把 `context_length`（`num_ctx`）從 4096 提高到 8192，理論上能讓長對話歷史不被截斷，但實測在這台機器上會讓單次回應從 ~60 秒暴增到 180 秒逾時失敗，得不償失，所以維持 4096。如果之後在效能更好的機器上開發，可以重新評估調高。

## 執行與測試

```bash
# 需先啟動 Ollama 並確認 config/game_config.json 的 model_name 已下載
python web_ui.py     # Gradio Web UI，預設 http://0.0.0.0:7860
python main.py        # CLI 介面
pytest                 # 全部離線可跑，不需要真的連線 Ollama
```

`config/game_config.json` 目前設定 `model_name: qwen2.5:1.5b`（本機已安裝，`context_length: 4096`）。這台機器上也裝了 `qwen2.5-coder:7b-instruct-q4_K_M`，如果要換更大的模型做品質比較，記得同步評估推論速度，不要只看輸出品質。

## 個人 hobby 專案的設計原則（ARCHITECTURE.md 已明訂，維持一致）

不引入 DI container、抽象介面（ABC）或企業級分層；`GameEngine` 維持作為 `main.py`/`web_ui.py` 唯一對外入口。重構時對外方法簽章盡量不變，讓呼叫端不用跟著改。
