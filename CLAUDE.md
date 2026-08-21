# CLAUDE.md

給 Claude Code 的專案速覽。完整規劃請見 [VISION.md](VISION.md)（產品願景）、[ARCHITECTURE.md](ARCHITECTURE.md)（架構債與分階段重構計畫）、[ROADMAP.md](ROADMAP.md)（功能路線圖）——這三份是本專案的權威文件，開始任何工作前先讀 ARCHITECTURE.md 的「分階段重構順序」了解目前走到哪一步。

**注意**：以上三份文件與下面「目前進度」段落，描述的是 `main` 分支上「多軸線沙盒」那套舊方向。
目前還有一條**方向完全不同、平行進行**的重構在 `feature/conquest-route-redesign` 分支上，
收斂成單一情慾/征服路線＋四位獨立女主角，完整規劃與工作日誌見該分支的
[REDESIGN_PLAN.md](REDESIGN_PLAN.md)。下面這節是那條分支的工作日誌摘要。

## 征服路線重構工作日誌（`feature/conquest-route-redesign` 分支）

**已完成的部分**（詳細設計討論與確認過程見 `REDESIGN_PLAN.md`）：
- 四位女主角人設（沈青鋒/慕容茵/卓芷若/阿罌）與世界觀（群芳會／棲霜山莊）逐項跟使用者
  確認定案。
- 核心機制重構：好感度區間改成 -50~80；選項從「LLM 每回合自由創作 5 個＋自報好感度變化」
  改成「LLM 每回合寫 3 個選項文字＋標記固定分類 (tag)，系統依分類查表覆寫好感度變化，
  不信任 LLM 自報數字」；好感度接近終極/黑化門檻時系統決定性插入關鍵臨界選項；
  `evaluate_ending` 改成對稱規則逐一檢查四位角色；`src/thread_state.py` 主題線鎖定
  狀態機整個移除（單一路線不再需要）。五份主要設定檔全面替換成新角色/新世界觀內容。
  `pytest` 63 個測試全數通過（測試套件已同步更新）。
- **結局劇情生成管線**（`src/ending_writer.py` + `config/ending_writer_config.json` +
  Web UI 的「🔞 結局劇情檢視器」面板）：獨立於一般回合制劇情之外，用專門的模型把角色人設
  與黑化流程大綱擴寫成長篇結局內文。實測過 `huihui_ai/qwen3.5-abliterated:4b`
  （完全不夠露骨，且發現這是「思考型」模型，`message.content` 有時是空的，實際內容跑進
  `message.thinking`，已在 `src/ollama_client.py::chat_text()` 加了 fallback 讀取）與
  `hf.co/bartowski/EVA-Qwen2.5-7B-v0.1-GGUF:Q4_K_M`（篇幅夠但角色名字會飄掉、劇情跟給定
  大綱前後不連貫，推測是 7B 模型在 Q4 量化下擕不住一次 2048 tokens 長篇生成的連貫性）。
  當時使用者決定先停在這裡、等機器升級後再回來處理；機器升級後已接續處理，見下方
  「機器升級後的模型/可靠度修復」一節（多步驟接龍生成、few-shot 風格範例、崩壞偵測重試
  等），目前結論是露骨程度與穩定性仍有明顯隨機波動，下一步方向是 LoRA 微調。

**背景執行的坑（這台機器上踩過，記錄起來避免重踩）**：長時間生成任務（例如結局劇情這種
2048 tokens 的單次呼叫）如果直接用 Claude Code 的 Bash 工具背景執行，曾經被 Claude Code
自己的背景任務追蹤器在毫無预警的情況下砍掉（跟 `web_ui.py` 一直以來用 `Start-Process`
完全分離啟動是同一類問題，見下方「手機/外部網路連線」段落）。修法：比照
`scripts/start_server.ps1` 的模式，寫一個小腳本用 PowerShell `Start-Process` 完全分離啟動，
執行完把結果寫進一個標記檔案，再輪詢標記檔案是否出現，而不是依賴 Bash 工具自己的背景任務
追蹤機制。

## 機器升級後的模型/可靠度修復（新 session，硬體從純 CPU 換成 RTX 5070 12GB + 60GB RAM 之後）

機器升級後 Ollama 跟 Python 套件整個要重裝（原本裝的東西都不見了），順便把停在
「等機器升級」的結局生成管線與主線引擎都往前推進了一大步。

**主線引擎模型與 `context_length`**：`config/game_config.json` 的 `model_name` 從
`qwen2.5:1.5b` 換成 `qwen2.5:14b`（GPU 加速後速度足夠，Q4_K_M 約 9GB 完整塞進 12GB
VRAM），`context_length` 從 4096 拉高到 8192（原本 4096 是純 CPU 時代怕拉高會讓單次回應
從 60 秒暴增到 180 秒才定的限制，GPU 加速後這個顧慮不再成立）。

**主線引擎 JSON 輸出可靠度問題（重大發現與修法）**：換上 14b 之後第一次實機測試才發現
`GameStateDelta`（19 個欄位）用 Ollama 通用 `format:"json"` 模式時，成功率低到接近
0%——小模型透過這個只保證「語法合法」不保證「欄位齊全」的模式，常常寫了 6~7 個欄位後就
自己判斷「這樣算寫完了」提前補上 `}`，`options` 欄位從沒被寫到，觸發保底。（用真實
存檔重現、隔離變因後確認：跟同一個 session 稍早加的 `story_milestones`/摘要機制無關，
也不是 14b 特有——1.5b 換上同一套 prompt 一樣是這個成功率；這是換模型後第一次真的做
端到端實機測試才浮現的既有問題，過去可能一直存在只是沒被系統性測過。）

修法分兩步，最終**單次 API 呼叫、完全不加延遲**達到 30 次跨 4 位角色測試 100% 成功
（樣本數不大，但比對照組的 0~50% 是質的差異）：
1. `src/ollama_client.py::_build_payload` 新增 `json_schema` 參數，傳完整 Pydantic
   JSON Schema 給 Ollama 的 `format` 欄位（而不是字串 `"json"`），啟用文法約束
   (grammar-constrained) 解碼。**單獨這步只把成功率從約 0% 拉到約 50%**，因為
   `GameStateDelta` 每個欄位都有 `default` 值，Pydantic 生成的 schema 因此完全沒有
   `"required"` 清單，文法約束依然允許模型在任何時候合法收尾。
   **試過手動在 schema 裡補 `"required": [...]` 清單想強制填滿關鍵欄位，結果讓成功率
   降到 0/8，比不加還糟——已回退，不要重踩這個方向。**
2. 查程式碼確認 `player_hp_change`/`player_stamina_change`/`player_gold_change`/
   `player_charm_change`/`cultivation_art_learned`/`cultivation_exp_gained`/
   `inventory_added`/`inventory_removed`/`world_flag_set`/`current_location`/
   `unlocked_locations`/`faction_reputation_changes` 這 12 個欄位在**目前**的征服路線
   遊戲規則裡完全沒有機制效果（HP 歸零不會怎樣、`world_flags` 只寫不讀、
   `cultivation_level` 只影響自己的升級公式不影響任何判定），純粹是裝飾性數值，缺席時
   套用 default 值（0/不變）完全安全。於是把每回合要求 LLM 主動產生的欄位從 19 個縮小成
   7 個核心欄位（`src/npc_agent.py::_CORE_TURN_SCHEMA_FIELDS`：`narrative`、
   `npc_status_tag`、`options`、`option_tags`、`main_quest_summary_update`、
   `npc_relationship_note_update`、`milestone_unlocked`），透過
   `OllamaClient.chat_structured/chat_structured_stream` 新增的 `schema_fields`
   參數（`_trim_schema_properties` 只保留指定欄位）送出縮小過的 schema。
   **`GameStateDelta` 資料模型本身完全沒有刪欄位**，那 12 個欄位還在、還能正常存讀檔，
   只是不再放進每回合送給 LLM 的 schema／prompt 範例裡。
   **使用者明確交代**：金錢/體力/修為這幾個欄位目前劇情用不到，但之後的劇情內容有可能會
   用到——**之後如果真的要恢復，只要把對應欄位名稱加回 `_CORE_TURN_SCHEMA_FIELDS`
   （`src/npc_agent.py`），`build_schema_example()` 的範例跟 `build_system_prompt()`
   「核心原則」編號指令都會跟著自動涵蓋，不需要重新設計**；加回去後很可能又要重新測一次
   成功率有沒有掉回去，必要時可能得同時精簡其他欄位來平衡 schema 大小。

**結局劇情生成管線**（`src/ending_writer.py`，接續之前「等機器升級」停下的地方）：
- 改成多步驟接龍生成：大綱每一步驟分開呼叫模型、用多輪對話歷史串接前文，取代單次要模型
  寫完整段 2048 tokens；最後兩步（親密場景本身）額外加碼 token 預算＋明確指令要求直接
  進入具體描寫，不要一直鋪陳氣氛。
- 新增 `strip_meta_leakage()` 過濾模型偶爾破格輸出的「自我規劃/創作提示」文字（markdown
  標題、code fence、提到「用戶」的整段、`1. **標題** - ` 這種條列格式），以及
  `is_step_output_broken()` 崩壞偵測（過濾後內容太短，或 emoji/符號密度過高）搭配最多
  3 次自動重試。
- 新增 `config/style_reference.txt`（真人撰寫的露骨風格範例，人名已替換成通用代詞，
  當 few-shot 錨點用——因為光靠抽象指令「請直接描寫」對 abliterated 模型沒什麼約束力，
  abliteration 只移除拒答，不會移除模型從 RLHF 學來的「含蓄比較有品味」傾向）。這個檔案
  跟 `saves/endings/` 一樣**刻意不進版本控制**（`.gitignore` 已加），內容本身很露骨、
  只留在本機；`novels/` 整個資料夾（使用者放的原始參考小說）也一併加進 `.gitignore`。
- 換模型測過 `TheDrummer/Cydonia-24B-v4.3`（Q4_K_M，中文明顯不行，大量夾雜英文、
  最終崩潰成同義詞洗版）、`huihui_ai/qwen3-abliterated:30b-a3b`（MoE，仍不夠露骨，
  且混進緬甸文/阿拉伯文標點符號等量化錯亂），最後採用 `huihui_ai/qwen3-abliterated:14b`
  （`config/ending_writer_config.json`，`context_length` 也拉高到 8192）。
  **實測結論：不管哪個模型，露骨程度跟穩定性都有明顯隨機波動**（同樣輸入，這次寫得很
  好、下次可能整段崩潰成 emoji/符號亂碼），這比較像是這個尺寸/量化組合的固有限制，不是
  prompt 調整能穩定解決的天花板。這個結論後來被下面「RWKV 續寫模型」的實驗部分推翻——
  不是「這個任務本身就做不到穩定」，是「abliterated instruct 模型不適合這個任務」。

**結局劇情生成管線的後續：RWKV 續寫模型是重大突破（同一個 session 後段接續處理）**

使用者提出一個關鍵洞察：跟其一直在「泛用 instruct 模型 + abliteration + prompt 工程」
這條路線裡打轉，不如換個方向找**專門用中文情色小說語料直接訓練**的模型——這類模型不需要
「移除拒答」，因為它訓練時看過的資料本身就是這種文字。找到
`a686d380/rwkv-5-h-world`（HuggingFace，Apache 2.0），實測結果證實這個方向完全正確：

- **架構跟這個專案原本假設的完全不同**：這是 RWKV（RNN 類架構，不是 transformer），
  不能直接被 Ollama 讀取，需要另外裝
  [RWKV Runner](https://github.com/josStorer/RWKV-Runner) 的 `backend-python`
  跑一個獨立的 OpenAI 相容 API server（預設 port 8000，`/v1/completions`）。
  設定步驟：`git clone` RWKV-Runner 原始碼到 `tools/rwkv-runner-src/`、在
  `backend-python/` 底下建 venv 裝 `requirements.txt`（**torch 那一行改用
  `pip install torch --index-url https://download.pytorch.org/whl/cu128` 另外裝**，
  requirements.txt 裡沒指定 index 的 torch 版本太舊，這台機器的 RTX 5070 是 Blackwell
  架構 (compute capability 12.0)，舊版 torch 會報
  `CUDA error: no kernel image is available for execution on the device`，要 cu128
  以上的 wheel 才有 sm_120 kernel）。模型權重（1.5B/3B/7B 三種尺寸的 `.pth` 檔）另外從
  HuggingFace 下載到 `tools/rwkv-models/`。`tools/` 整個資料夾已加進 `.gitignore`
  （裡面是外部原始碼、執行檔、GB 級模型權重，不該進版本控制），啟動流程寫成
  `scripts/start_rwkv_server.ps1`/`stop_rwkv_server.ps1`（跟 `start_server.ps1` 同一
  套模式：`Start-Process` 完全分離啟動，啟動後自動呼叫 `/switch-model` 載入 3B 模型，
  策略用 `cuda fp16i8`）。**寫這兩個新腳本時踩到一個坑**：用 Write 工具新建的 `.ps1`
  檔沒有 UTF-8 BOM，Windows PowerShell 5.1 沒有 BOM 就會用系統 ANSI 編碼讀檔，把檔案裡
  的中文字元讀壞導致字串常值解析失敗（`TerminatorExpectedAtEndOfString`）——舊的
  `start_server.ps1` 之所以能正常運作是因為它本來就有 BOM。修法：寫完新的 `.ps1` 檔後
  用 `Get-Content -Encoding UTF8 | Set-Content -Encoding UTF8` 補上 BOM（Windows
  PowerShell 5.1 的 `-Encoding UTF8` 預設就會寫入 BOM）。
- **比較過 3B 跟 7B**：兩者品質沒有壓倒性差異（都會隨機波動），但 7B 用掉
  10.9GB/12GB VRAM（幾乎吃滿），3B 只需要一小部分、速度也快，最後採用 3B。
- **這是純續寫 (completion) 模型，不是指令遵循 (chat) 模型**：不能像 qwen 那樣下指令
  「請描寫...」，只能給一段前綴讓它自然接下去，所以 `src/ending_writer.py` 新增
  `backend: "ollama" | "rwkv"` 分流：`_generate_steps_ollama`（原本的多輪對話+指令）
  跟 `_generate_steps_rwkv`（前綴接龍，`build_ending_prefix`/
  `build_combined_outline_cue` 全部寫成第三人稱敘事散文，不能有指令式用語）。新增
  `src/rwkv_client.py::RWKVClient` 這個獨立的輕量 client，故意不跟 `OllamaClient`
  共用（呼叫的 API 形狀跟使用情境都不同，硬共用只會兩邊都變得不乾淨）。
- **重大的架構教訓：接龍多步驟生成（今天稍早才確立的模式）反而是 RWKV 的天敵**。
  一開始比照 ollama 路線也做成多步驟接龍（`build_step_continuation_cue`，累積前綴
  越滾越長），結果實測發現 RWKV 這類 RNN 類架構比 transformer 更容易被累積前綴裡
  剛出現過的句子「黏住」，反覆複誦自己剛寫過的內容——縮小上下文視窗、拉高
  `frequency_penalty`/`presence_penalty`、拉嚴重複偵測門檻（3 次降到 2 次）都只能
  緩解、無法根治，這幾個嘗試已經全部刪除，`build_step_continuation_cue` 這個函式也已
  移除。**最終解法是徹底放棄接龍，改成單次生成**：把整份大綱濃縮成一句劇情走向提示
  (`build_combined_outline_cue`)接在角色前綴後面，只呼叫模型一次。改成單次生成後
  品質大幅提升且穩定很多（30 次跨角色測試裡大多數品質很好、速度也快很多，
  99~150 秒對比接龍版本的 260~400+ 秒），這是全部測試過的方案裡最好的結果。
- **仍未解決的新問題**：單次生成偶爾會**跑題到其他武俠作品的角色宇宙**（例如某次
  「卓芷若」的結局生成混入了小龍女、楊過、趙敏、李莫愁等金庸小說角色）——這是訓練語料
  包含大量武俠小說（可能含金庸原作或同人）造成的角色名字聯想污染，不是崩潰/亂碼類型
  的失敗，現有的 `is_step_output_broken()` 偵測不到。使用者已決定**先在這裡打住，之後
  再考慮要不要加「偵測到知名武俠角色名字就重試」這類規則**。
- **新增機制（跟 ollama 路線共用）**：`_has_repeated_sentence_loop()`/
  `_truncate_before_repeat_loop()`——偵測「同一句子逐字重複 2 次以上」直接判定崩壞，
  重試 `MAX_STEP_RETRIES` 次後仍然崩壞就砍掉復讀迴圈開始的地方、只保留前面正常的內容
  （而不是把整段複誦文字塞進最終結局文字），這是 CLAUDE.md 更早之前就記錄過但沒真的
  做的防線，這次借助 RWKV 暴露出的復讀問題順手補上，ollama 路線也一併受惠。
- **使用者提出但尚未實作的下一個方向**：角色標籤（例如「巨乳」）觸發對應的**人工預先
  寫好的劇情模板庫**，模型只需要做「把選中的模板套進當前情境、調整人稱/銜接語氣」這種
  輕量編輯工作，而不是從零生成整段露骨內容——把 LLM 的任務從「創作」降級成「改寫」，
  對應到 `NPCProfile.body` 可以加 `body_tags: List[str]`、`config/scene_templates.json`
  存模板庫、依標籤篩選模板。這個方向使用者認為可行且評價正面，但決定先確認 RWKV
  這條路線後再回頭做。

**主線敘事連貫性補強**：
- `story_milestones`（原本只有存讀檔，從未被塞進 LLM prompt，形同虛設）現在會實際注入
  system prompt 當「不可遺忘或改寫」的精確錨點，跟會被逐輪覆寫的 `main_quest_summary`
  互補。
- 新增 `GameState.npc_relationship_notes`（`Dict[角色名, 一句話關係現況]`）取代「要求
  LLM 每回合把四位角色的關係現況都重寫一遍」的最初設計——**那個設計已經試過，結果跟
  `OllamaClient` 為了防止敘事復讀而開的 `presence_penalty`/`frequency_penalty` 互相
  打架**：模型為了「避免重複」這幾位角色名字與慣用句式，開始亂編欄位名稱、夾雜英文，
  JSON 格式整個崩潰。改成系統端逐一角色更新（`src/rules.py::apply_delta` 只更新
  `state.current_agent` 那一位角色的記錄）、其他角色的現況只用唯讀方式顯示給模型參考，
  LLM 只需要回報眼前這一位角色的更新即可，從根本避開這個衝突。
- `NPCAgent.history` 加了上限（`_MAX_HISTORY_MESSAGES = 40`），純粹是存檔衛生／效能考量
  （反正 `_build_messages` 本來就只取最後 4 則送進 LLM），不是連貫性修復。

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

## 主題線鎖定（選項連貫性）

**動機**：實測發現每回合的 5 個選項 (A~E) 各自獨立生成，即使玩家上一輪選了情慾線，下一輪 5 個選項也可能完全不相關（正派/謀略/情慾/混亂/探索各一個），玩家反饋「選項不連貫」。

**設計**（完整討論見對話紀錄，這裡只記結論）：`src/thread_state.py::update_thread_state` 是一個獨立於 `src/rules.py` 的狀態機（獨立成一個檔案是因為 `rules.py` 會 import `src/state.py`，而 `state.py` 又 import `src/npc_agent.py`，如果狀態機放進 `rules.py`，`npc_agent.py` 要用就會循環 import）：

- `NPCAgent` 新增 `active_thread`（"B"/"C"/"D" 或 `None`）、`thread_intensity`（0~100）、`thread_climax_pending` 三個欄位，已同步進 `save_manager.py` 存讀檔（讀舊存檔時用 `.get()` 給預設值向後相容）。
- 玩家從中立狀態（`active_thread is None`）選了 B(謀略)/C(情慾)/D(混亂) 才會進入鎖定；選 A/E 維持中立。
- 鎖定後 `A~D` 四個選項全部延續同一主題發想 4 個不同切入角度的變體，**E 永遠維持原本「地圖探索/轉移」語意不變**，作為玩家隨時可以脫離主題線的逃生口（選 E 立刻重置回中立，不用等強度累積）。
- `thread_intensity` 累積量借用既有 `GameStateDelta` 欄位當訊號，**沒有新增任何 LLM 輸出欄位**（避免加重小模型的 JSON 負擔）：C 用 `intimacy_change`、D 用 `faction_reputation_changes` 變動幅度、B 用 `milestone_unlocked`/`main_quest_summary_update` 是否有更新，外加每回合固定基礎值。
- 累積到門檻 (`THREAD_INTENSITY_THRESHOLD = 100`) 不會立刻重置：因為要偵測「這回合是否跨過門檻」得先看這回合的 delta，但那時候這回合的劇情文字已經生成完了，沒辦法讓 LLM 現場照著收尾寫。所以改成「延後一回合」：跨過門檻的那一刻只設 `thread_climax_pending = True`，**下一回合**才是真正的收尾回合（system prompt 會加一段依主題類型客製化的收尾指令，例如 D 線是「讓這段背叛或混亂局勢迎來一次爆發性轉折」），收尾回合結束後才真正重置回中立、選項恢復五種類型都開放。
- 選項對應到哪個類別不靠解析 LLM 輸出文字裡的「A)」前綴：Gradio 的五個按鈕各自綁一個固定的 `gr.State("A"~"E")` 常數，透過 `process_player_choice(..., chosen_category=...)` → `GameEngine.interact_stream(chosen_category=...)` → `NPCAgent.process_action_stream(chosen_category=...)` 一路往下傳，100% 準確。CLI (`main.py`) 沒有固定按鈕對應類別，`chosen_category` 預設 `None`，行為不受影響。

測試見 `tests/test_engine.py` 裡「主題線鎖定狀態機」那一段（純函式單元測試涵蓋所有分支 + 一個驗證按鈕→engine→NPCAgent 整條路徑真的有接上的整合測試）。

### 上線後發現的嚴重 bug：解析失敗時靜默套用 GameStateDelta 寫死的預設選項

主題線鎖定上線後，玩家實測反饋「劇情顯示不完、選項好像是寫死的，永遠都是那幾個」。用玩家真實存檔重現後找到根因，**跟主題線鎖定本身無關，是更早就存在的潛藏 bug，只是被放大凸顯出來**：

- `qwen2.5:1.5b` 敘事有時會陷入逐句復讀迴圈（跟更早之前修過的柳如煙復讀是同一類問題），把 `num_predict=1024` 的 token 預算整個耗在重複同一句話上，導致 JSON 還沒寫到 `options` 欄位就被截斷。
- `src/ollama_client.py::parse_json_robustly` 的截斷修復機制會把不完整 JSON 修到語法合法（補上缺的引號/括號），但如果 `options` 這個 key 整個沒出現，修復後的 dict 就是**沒有這個 key**，而 `GameStateDelta.options` 有 `default_factory` 給的一份寫死的 5 個範例選項（在 `src/models.py`，本來是給「完全沒資料」時的最後防線）。Pydantic 驗證這種情況**不會報錯**，會靜默套用那份寫死清單——這就是玩家看到「選項永遠是那幾個」的真正原因，不是任何程式碼真的寫死選項，是解析失敗後悄悄接受了 schema 內建的預設值。
- **修復**：`src/ollama_client.py` 新增 `_ensure_options_present()`，在 `chat_structured`（含首次與 re-prompt 重試兩次）與 `chat_structured_stream` 解析出 dict 後、丟進 Pydantic 驗證前，明確檢查 `options` 是否存在且非空，沒有就 raise `ValueError`。首次失敗會觸發既有的 re-prompt 重試機制；如果重試後依然缺 `options`，例外會往上傳到 `NPCAgent.process_action`/`process_action_stream` 的既有 exception handling，改用設計完整、跟當下 NPC 個性/地點貼合的 `generate_fallback_delta`（`src/options.py`），而不是悄悄回傳那份完全通用、跟劇情脫節的 schema 預設值。用玩家的真實存檔重現過（見 git log），確認修復後行為符合預期：re-prompt 失敗兩次後正確走到 NPC 專屬 fallback，不再是寫死的通用選項。
- **仍未解決的根本問題**：模型本身陷入復讀迴圈這件事目前只是「處理得比較體面」（fallback 到位），沒有真正被防止。主題線鎖定會讓對話連續好幾輪停留在同一種語氣情境，可能會提高復讀迴圈發生的機率——如果之後復讀還是頻繁發生，下一步可以考慮：提高 `repeat_penalty`、明確設定 Ollama 的 `repeat_last_n`、或在 narrative 裡偵測「同一句子重複 3 次以上」就主動截斷重新請求。

### 上線後續發現：復讀迴圈幾乎每回合都在發生 + 保底選項的兩個連帶 bug

用玩家真實存檔（帳號「楚留香3」，鎖定情慾主題線）比對後發現：玩了 4 回合，`used_options_history` 卻累積了 22 筆——等於幾乎每回合的每個選項都在用保底模板，真正 LLM 輸出成功率接近 0。對話歷史裡還直接看到 4 次幾乎相同的殘句「你若不嫌弃，在下有一句古韻呢...」，證實小模型在連續鎖定同一主題後很容易崩進復讀迴圈（**不是快取或程式重用了舊回應，是模型自己每次都真的重新呼叫，但傾向收斂到同一句話**）。這代表主題線鎖定對這個 1.5B 模型可能是負向放大：連續同質語境讓模型更容易復讀。

被這個高頻 fallback 意外凸顯出兩個原本沒發現的連帶 bug，都已修復：

1. **保底選項沒有尊重主題線鎖定狀態**：`src/options.py::generate_single_fallback_option` 原本永遠依插槽位置 (`CATEGORIES[idx % 5]`) 決定要抓哪個類別的候選池，鎖定在 C（情慾）時，A/B/D 插槽的保底內容卻還是抓各自原本位置對應的正派/謀略/混亂候選池，跟當下劇情完全脫節。修復：新增 `active_thread` 參數，鎖定中時 A~D 四個插槽的內容改抓鎖定主題的候選池（前綴字母仍對應插槽位置），E 不受影響。`generate_fallback_options`/`generate_fallback_delta`/`NPCAgent._generate_fallback_delta`/`web_ui.py` 的兩個呼叫點都已同步更新。
2. **選項把行動的「結果」也寫進去了**：`config/npc_fallbacks.json` 的「風騷老闆娘」C/B/D 類別有幾條模板預先寫死了結果（例如「...傾聽其紅塵身世心聲」預設對方一定會敞開心房、「...共定生死誓言」預設對方一定同意），跟 `src/options.py::_generic_option_pools` 原本「只寫行動、用『試探』這類詞保持結果開放」的慣例不一致。已改寫成動作導向、不預設結果的措辭；同時在 `npc_agent.py::_OPTION_OUTCOME_NEUTRALITY_RULE` 新增一條明確的 prompt 規則（中立/鎖定/收尾三種選項生成指令都共用），要求 LLM 生成選項時也只能寫行動意圖、不能預先寫結果。

測試見 `tests/test_options.py` 的 `test_fallback_options_respect_active_thread_for_abd_slots` 等。

**門檻調整**：使用者確認後把 `THREAD_INTENSITY_THRESHOLD` 從 100 調降為 60（`src/thread_state.py`），讓鎖定通常 1~2 回合就自然收尾，縮短連續同質語境的時間、降低復讀崩潰機率，同時保留「延續同一主題」的連貫性效果。如果之後還是常復讀，可以再往下調；如果收尾太快、連貫性效果不明顯，可以往上調。

### 收尾回合的 fallback 也要知道自己在收尾

門檻調降後實測發現：收尾回合如果 LLM 又失敗、觸發了保底機制，保底邏輯完全不知道現在是收尾回合，於是（1）保底選項還是照 `active_thread` 鎖定的舊主題生成，收尾等於沒發生，選項一直輪迴；（2）保底劇情只是通用的 NPC 罐頭開場白，讀起來不像收尾。

修復：`generate_fallback_narrative`/`generate_fallback_delta`（`src/options.py`）新增 `climax_pending` 參數。`climax_pending=True` 時：選項改用 `active_thread=None` 生成（視同已回到中立狀態，五種類型都開放）；劇情會在保底文字後面補一句跟鎖定主題呼應的收尾散文（`src/thread_state.py::THREAD_FALLBACK_RESOLUTION_TEXT`，跟寫給 LLM 看的 `THREAD_RESOLVE_HINTS` 分開維護，因為前者要是能直接顯示給玩家看的敘事散文、後者是指令語氣，文體不同硬共用會很怪）。`NPCAgent._generate_fallback_delta` 與 `web_ui.py` 的 `fallback_opts` 呼叫點都已同步帶入 `self.thread_climax_pending`。

**沒有加長收尾回合的敘事字數**：使用者原本期待收尾回合的劇情篇幅應該比較長，但目前敘事長度要求（150~300 字）維持不變、沒有為收尾回合加碼——因為這台機器上模型截斷/保底觸發率已經偏高，要求更長的文字只會讓截斷更容易發生，跟「降低復讀機率」的目標互相矛盾。如果之後 fallback 觸發率明顯下降、模型比較穩定了，可以重新評估要不要讓收尾回合要求更多字數。

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

`web_ui.py` 最下面的啟動訊息一直宣稱「已開啟公共分享網址 share=True」，但實際的 `demo.launch(...)` 呼叫從來沒有真的傳 `share=True`——這是既有程式碼裡訊息跟行為對不上的舊 bug，只是之前沒人需要外部連線所以沒發現。已修正為 `demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True, share=True)`，這樣啟動時終端機會印出一個 `https://xxxxx.gradio.live` 的公開連結（Gradio 官方 tunnel，有效期最長約 1 週），手機用行動網路（不需要跟主機同一個 Wi-Fi）也能連進來玩。

**注意**：這個連結雖然不會被公開索引，但只要有連結的人都能打開遊戲，不要隨便外流。

### 啟動/停止腳本（`scripts/start_server.ps1` 等）

不要再直接 `python web_ui.py` 手動啟動。改用：

```powershell
scripts/start_server.ps1     # 啟動：檢查 Ollama 是否活著、模型是否已下載（只警告不阻擋），
                              # 完全分離啟動 web_ui.py，等公開連結出現後印出來
scripts/stop_server.ps1      # 停止：找出誰在聽 port 7860 直接關閉，PID 檔只是輔助
scripts/status_server.ps1    # 查詢目前是否在跑、公開連結是什麼、Ollama 連線狀態
scripts/restart_server.ps1   # 停止 + 啟動（改完程式碼要讓修改生效時用這個）
```

**為什麼要用分離啟動**：早期直接在 Claude Code 的 Bash 工具裡背景執行 `web_ui.py`，曾經被 Claude Code 自己的背景任務追蹤器在毫無预警的情況下砍掉（跟 auto mode classifier 擋 `share=True` 是兩回事），導致伺服器和外網連結無預警失效。`start_server.ps1` 用 `Start-Process` 啟動，完全不掛在呼叫者的程序樹或任何工具追蹤器上，關掉終端機、結束 Claude Code session 都不會連帶關閉伺服器。

**PID 陷阱**：`Start-Process` 回傳的 PID 觀察到常常跟實際佔用 port 7860 的 PID 不同（venv 的 `python.exe` 啟動器 exec 出真正的直譯器子程序），所以 `stop_server.ps1` 是優先用「誰在聽 7860」(`Get-NetTCPConnection -LocalPort 7860 -State Listen`) 去關，PID 檔只是備援，不能只信任 PID 檔。

**已知限制**：以上腳本目前是手動執行、沒有崩潰自動重啟（例如 Ollama 掛掉導致 `web_ui.py` 拋未捕捉例外整個程序死掉），使用者已明確表示現階段先不要用 Windows 排程工作（Task Scheduler）做自動重啟，之後有需要再加。

## 執行與測試

```bash
# 需先啟動 Ollama 並確認 config/game_config.json 的 model_name 已下載
python web_ui.py     # Gradio Web UI，預設 http://0.0.0.0:7860
python main.py        # CLI 介面
pytest                 # 全部離線可跑，不需要真的連線 Ollama
```

`config/game_config.json` 目前設定 `model_name: qwen2.5:14b`（`context_length: 8192`）。

**以下是機器升級（純 CPU → RTX 5070 12GB + 60GB RAM）前的舊結論，只留當歷史紀錄，已不適用**：
當時實測過 `qwen2.5:7b`（非 coder 版）純 CPU 推論吞吐量約 4.8 tokens/秒，單回合要 3~4
分鐘，比 `qwen2.5:1.5b`（約 60 秒/回合）慢 3~4 倍，所以選擇留在 `qwen2.5:1.5b`。機器升級
後這個限制已不成立，GPU 加速下 `qwen2.5:14b` 单回合速度良好（見上方「機器升級後的模型/
可靠度修復」一節），已正式換上；`OllamaClient()` 直接建構子的 `timeout` 預設只有 60 秒，
跟 `game_config.json` 的 `timeout: 120` 不同步，拿 `OllamaClient()` 單獨做基準測試時記得
手動帶入 `timeout=` 参數，這一點在 GPU 環境下依然適用，不受機器升級影響。

## 個人 hobby 專案的設計原則（ARCHITECTURE.md 已明訂，維持一致）

不引入 DI container、抽象介面（ABC）或企業級分層；`GameEngine` 維持作為 `main.py`/`web_ui.py` 唯一對外入口。重構時對外方法簽章盡量不變，讓呼叫端不用跟著改。
