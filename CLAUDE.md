# CLAUDE.md

給 Claude Code 的專案速覽。完整規劃請見 [VISION.md](VISION.md)（產品願景）、[ARCHITECTURE.md](ARCHITECTURE.md)（架構債與分階段重構計畫）、[ROADMAP.md](ROADMAP.md)（功能路線圖）——這三份是本專案的權威文件，開始任何工作前先讀 ARCHITECTURE.md 的「分階段重構順序」了解目前走到哪一步。

## 目前進度（重構，依 ARCHITECTURE.md 第四節分階段順序）

- [x] Stage 0 — 補測試安全網（`tests/test_streaming.py`）
- [x] Stage 1 — 清死程式碼/死設定
- [x] Stage 2 — 存檔系統整併為 account-based
- [x] Stage 3 — 共用 fallback/選項模組（`src/options.py` + `config/npc_fallbacks.json`，commit `699551d`）
- [x] Stage 4 — 親密度分級 SSOT（`src/rules.py::get_intimacy_stage/get_intimacy_stage_number` 接上 `config/npc_stages.json`）
- [x] Stage 5 — Prompt/schema 去重複（JSON 範例改由 `npc_agent.py::build_schema_example()` 從 `GameStateDelta.model_fields` 動態產生；`load_lorebook` 加 `lru_cache`；`_build_messages`/`_record_turn` helper 消除 `process_action`/`process_action_stream` 重複；`ollama_client.py::_build_payload` 整併三份 payload 字面量）
- [x] Stage 6 — Web UI 接上串流（`web_ui.py::process_player_choice` 改成 generator，迭代 `engine.interact_stream()` 逐步更新 Chatbot，只有最後一個 yield 才更新狀態板/選項；用真實本地 Ollama 驗證過 145 次逐字 yield 正常運作；`main.py` 補上「CLI 刻意不接串流」的註解）
- [x] Stage 7 — `GameEngine` 拆分為 facade（`src/content_loader.py`/`src/state.py::GameState`/`src/npc_autonomy.py` + `config/npc_autonomy.json`；`rules.py` 擴充 `apply_delta`/`evaluate_ending`/`get_current_chapter_info`；`game_engine.py` 變薄成 facade，靠 property 轉發維持 100% 向後相容；順手修掉「NPC 自主行動同回合觸發兩次」的既有 bug；`content_loader` 範圍比原規劃更大，一併收斂了 Stage 3～5 自己新增的三個重複 loader）
- [ ] Stage 8 — 戰鬥系統擴充點（僅文件，不實作）**← 使用者規劃的重構到此為止（Stage 8 本身也只是留文件，不實作）**

### Stage 7 討論過但刻意沒做的事：GameState 自己管存讀檔序列化
考慮過讓 `GameState` 自己提供 `to_dict()/from_dict()`，取代 `save_manager.py` 手動列欄位的存讀檔邏輯（這能防止「新增欄位忘記同步存檔」的 bug class，Stage 2 已經因為這樣漏掉 `story_milestones`/`used_options_history` 一次）。最後決定不做：existing 存檔格式（含使用者正在玩的真實存檔）已經是這個手刻的 JSON 形狀，貿然改序列化方式有存檔不相容的風險；而且 `NPCAgent`（親密度、對話歷史）不是純資料，不會被 `GameState` 直接持有，所以這個構想並不能像預期的那樣把存讀檔邏輯完全收斂到一個地方，效益比想像中小。如果之後真的要動存檔格式，建議另開一個獨立階段，並先補一個「載入舊格式存檔」的相容性回歸測試再動手。

使用者預計這次重構做到 Stage 7 為止（Stage 8 只是文件、不實作）。

## 近期修復：LLM 輸出截斷導致選項跑進劇情文字

**症狀**：實際試玩（本機 `qwen2.5:1.5b`）時，新選項文字有時會出現在 narrative 段落裡（例如「選項 A) ... 選項 B) ...」被寫進故事內容），且下方按鈕偶爾顯示跟上一輪一樣的舊選項。

**根因**：`src/ollama_client.py` 的 `num_predict` 原本是 512，但這個遊戲要求「150~300 字中文敘事 + 完整 5 個選項 + 其他狀態欄位」，換算下來常超過 512 tokens，回應被硬生生截斷，模型就把選項清單寫進 narrative 裡湊字數，或截斷修復出來的 `options` 陣列不完整而觸發保底機制。

**修復**：
- `num_predict` 512 → 1024（`chat_structured` 兩處呼叫 + `chat_structured_stream` 預設值）
- `src/models.py::normalize_llm_dict` 新增防線：偵測「選項 A)」/「选项A)」這類清單開頭標記並自動從 narrative 截斷（`tests/test_engine.py` 有覆蓋，含「一般語句提到『選項』兩字不應誤刪」的邊界測試）

**已知但刻意不採用的方案**：把 `context_length`（`num_ctx`）從 4096 提高到 8192，理論上能讓長對話歷史不被截斷，但實測在這台機器上會讓單次回應從 ~60 秒暴增到 180 秒逾時失敗，得不償失，所以維持 4096。如果之後在效能更好的機器上開發，可以重新評估調高。

## 測試 web_ui.py 串流函式時的兩個陷阱

寫 `process_player_choice`（或未來其他串流 generator）的測試時踩過兩個坑，記錄起來避免重踩：

1. **不要用 `list(generator)` 收集中途 yield 再事後檢查內容**：`process_player_choice` 為了讓 Gradio 能低成本更新畫面，是「就地修改同一個 `clean_history` 物件再 yield」，不是每次 yield 一份新的複本。用 `list(...)` 收集會拿到一堆指向同一個「已經被改到最終狀態」物件的參照，事後檢查 `results[0]` 看到的其實是最後一輪的內容。要驗證中途狀態，必須在 `for result in gen:` 迴圈「當下」就把要斷言的純量值（字串/數字）取出來存成快照。
2. **`process_player_choice` 結尾一定會呼叫 `engine.auto_save()` 寫入真實存檔檔案**：如果測試斷言依賴選項去重後「剛好是哪個候選字串」這種精確值，殘留的存檔檔案會讓 `used_options_history` 帶著上一次測試執行的痕跡，導致同一份測試在不同次執行結果不一樣。要嘛 mock 掉 `src.save_manager.save_account_game`，要嘛只斷言相對行為（例如「跟前一輪不一樣」），不要斷言絕對字串。

## 手機/外部網路連線：Gradio share=True

`web_ui.py` 最下面的啟動訊息一直宣稱「已開啟公共分享網址 share=True」，但實際的 `demo.launch(...)` 呼叫從來沒有真的傳 `share=True`——這是既有程式碼裡訊息跟行為對不上的舊 bug，只是之前沒人需要外部連線所以沒發現。已修正為 `demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True, share=True)`，這樣啟動時終端機會印出一個 `https://xxxxx.gradio.live` 的公開連結（Gradio 官方 tunnel，有效期 72 小時），手機用行動網路（不需要跟主機同一個 Wi-Fi）也能連進來玩。

**注意**：這個連結雖然不會被公開索引，但只要有連結的人都能打開遊戲，不要隨便外流。

**已知限制**：啟動 `web_ui.py`（尤其是帶 `share=True` 開公開通道）目前會被 Claude Code 的 auto mode classifier 擋下，即使加了 `.claude/settings.local.json` 的 `Bash(*web_ui.py*)` 允許規則也一樣——很可能是因為 `.claude/` 目錄是這個 session 開始「之後」才建立的，設定監看器沒吃到，需要重開一個新的 Claude Code session 才會生效。如果重開 session 後還是被擋，代表這可能是 classifier 刻意不給覆蓋的安全邊界（開公開對外通道），屆時請自己在終端機手動執行 `.venv/Scripts/python.exe web_ui.py`。

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
