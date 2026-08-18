# Blade RPG — 架構規劃文件 (Architecture Spec)

> 本文件記錄專案目前的實際架構、已知的架構債，以及後續開發要走向的目標架構與分階段重構順序。
> 產品願景（這款遊戲最終要是什麼樣子）請見 [VISION.md](VISION.md)；產品層的功能規劃請見 [ROADMAP.md](ROADMAP.md)；本文件只談「程式碼怎麼組織」，不重複列功能清單。

---

## 一、現況架構總覽

### 1.1 `src/game_engine.py` — `GameEngine`（上帝物件）

`GameEngine.__init__`（12–70 行）同時持有：

- 設定物件：`game_config`（`GameConfig`）、`client`（`OllamaClient`）
- 玩家狀態：`player_state: PlayerState`（單一全域玩家，引擎本身不支援多 session）
- 世界資料：`world_flags`、`world_intro`、`world_map`（原始 dict，非 Pydantic model）、`story_outline`（同樣是原始 dict）
- 位置/導航狀態：`current_location`、`unlocked_locations: Set[str]`
- 劇情/進度狀態：`game_turn`、`main_quest_summary`、`story_milestones`、`recent_world_events`（上限 5）、`world_news`（上限 10，初始化時塞了 4 條寫死的風味文字，45–50 行）
- 勢力聲望：`factions: Dict[str, int]`
- NPC 狀態：`agents: Dict[str, NPCAgent]`（用內部 `name` 當 key，不是 `display_name`）、`current_agent`

**這是典型的上帝物件**：設定載入、世界/劇情資料、玩家狀態、NPC 註冊表、勢力聲望帳本、存檔委派、回合/章節邏輯全部塞在同一個 class，資料與行為完全沒有分層。

**關鍵方法：**

| 方法 | 位置 | 問題 |
|---|---|---|
| `_load_game_config/_load_world_intro/_load_world_map/_load_story_outline/_load_npcs` | 72–168 | 5 份幾乎一樣的「讀 JSON，失敗就用寫死的 Python fallback」邏輯，JSON 檔跟 Python fallback 是兩份平行的資料來源，會互相漂移 |
| `evaluate_ending()` | 182 | 寫死的 4 結局判斷邏輯；只有 `web_ui.py:287` 會呼叫，**CLI 完全沒有結局畫面** |
| `move_to_location()` | 228 | 更新位置後**內部又呼叫一次** `simulate_npc_autonomous_actions()`（副作用） |
| `save_slot/auto_save/load_slot/load_account/load_latest_slot` | 250–277 | 對 `save_manager` 的薄包裝，每個方法都在方法體內做 local import（避免循環引用） |
| `apply_delta(delta)` | 279–358 | 回合結算的真正核心邏輯，~80 行混雜位置/HP/背包/勢力/敘事紀錄的變更 |
| `simulate_npc_autonomous_actions()` | 360–415 | 用**寫死的 dict**（364–389 行，NPC 名稱字串必須跟 `config/npcs.json` 完全一致）隨機挑選 NPC 背景活動 |
| `interact()` / `interact_stream()` | 417 / 444 | 兩個回合執行入口，見下方「已知問題」 |

**`apply_delta` 細節：**
- 每次呼叫一定 `game_turn += 1`，即使是 fallback delta 也照樣推進世界時鐘
- `delta.unlocked_locations` 直接合併進 `unlocked_locations`，**繞過** `move_to_location` 對 `world_map["regions"]` 的驗證 —— LLM 可以「解鎖」一個根本不存在的地點
- 直接改 `current_agent.profile.intimacy`（伸手進 `NPCAgent` 內部狀態，而不是透過 `NPCAgent` 的方法）
- 升級判定（`required_exp = level * 100`）、升級獎勵（+2 魅力、+20 最大體力並回滿）等遊戲平衡數值直接寫在這裡
- `faction_reputation_changes` 是無上限疊加（跟 HP/親密度有 clamp 不同）

**已確認的死欄位：** `GameStateDelta.available_exits`（全 repo 沒有任何地方讀取）、`world_map.json` 的 `region_events`（同樣沒人讀）。

**兩個沒對齊的「已解鎖地點」概念：** `world_map.json` 每個 region 自己的 `is_unlocked`（靜態，只在 init 讀一次）vs. 執行期的 `unlocked_locations: Set[str]`（動態，被 `move_to_location`/`apply_delta` 修改）——這兩者從未互相同步。

**回合流程中的重複呼叫 bug：** `interact()` 呼叫 `apply_delta(delta)` 後，**又額外呼叫一次** `simulate_npc_autonomous_actions()`；但如果 delta 內含換地點，`apply_delta` 內部的 `move_to_location` 早就已經觸發過一次了——同一回合 NPC 自主行動可能跑兩次。

### 1.2 `src/models.py` — Pydantic Models

- **`GameStateDelta`**（17–211）：LLM 每回合輸出的結構化契約，約 20 個欄位。有一個很大的 `model_validator(mode="before")`（56–211 行）做 LLM 輸出的修復/正規化：數字欄位的字串轉型、list 欄位從 dict/字串強制轉換、~10 種欄位別名解析（`content/story/description` → `narrative` 等）、`is_placeholder_option()`/`sanitize_option_text()` 過濾佔位字串。**這是跟 `ollama_client.py` 平行、獨立的第二層 JSON 修復邏輯。**
- **`NPCProfile`**（214–280）：`get_unlocked_biography()`/`get_unlocked_stats()` 都各自寫死 25/50/75 門檻（同一組數字在同一個 class 出現兩次，用不同機制），**又跟** `config/npc_stages.json` 裡設計的親密度分級（有 stage_title/behavior/unlocked_topics）**是第三份重複**，而 `npc_stages.json` 從未被任何 Python 程式碼讀取。
- **`PlayerState`**（283–298）：純資料，沒有方法（跟 `NPCProfile` 相反，「狀態變更邏輯放哪」這件事在兩個 model 間不一致——全部集中在 `GameEngine.apply_delta`）。
- **`GameConfig`**（301–305）：`context_length` 欄位宣告了但**從未被讀取**——`OllamaClient` 自己在兩個方法裡各硬編碼一次 `num_ctx: 4096`。

**重複/死欄位總結：** 親密度門檻 25/50/75 出現 3 處（`models.py` 兩處 + `npc_stages.json` 一處死資料）；5 選項的預設 fallback list 出現 3 處（`GameStateDelta` 的 default_factory、`npc_agent.py` 每個 NPC 各自的 fallback、`main.py` 的 CLI 種子值）；JSON 修復邏輯分裂在 `models.py`／`ollama_client.py` 兩處。

### 1.3 `config/` 設定檔

| 檔案 | 用途 | 讀取者 |
|---|---|---|
| `game_config.json` | Ollama URL/模型名/`context_length`（死）/timeout | `GameEngine._load_game_config` |
| `npcs.json` | 每個 NPC 的靜態種子資料（身份、個性、初始關係、屬性、傳記、可選的 `system_prompt_override`） | `GameEngine._load_npcs` → `NPCProfile` |
| `world_intro.json` | 開場敘事、初始勢力聲望 | `GameEngine._load_world_intro` |
| `world_map.json` | 地區圖：description/connections/is_unlocked/danger_level/bound_npc/`region_events`（死） | `GameEngine._load_world_map` |
| `story_outline.json` | 章節（turns_range+goal+`key_event`死欄位）+ 4 個結局 | `GameEngine._load_story_outline`；`evaluate_ending()` |
| `lorebook.json` | 世界觀 + 親密文風寫作範例 | `npc_agent.py::load_lorebook()`，**每回合都重新讀檔+parse，沒有快取** |
| `npc_stages.json` | 每 NPC 4 段親密度分級設計（stage_title/behavior/unlocked_topics） | **完全沒有任何 Python 檔案讀取**——死設定 |

所有 `_load_*` loader 都是同一個 pattern：`os.path.exists` → `json.load` → `except` 印警告 + 回傳寫死的 Python fallback，這個 pattern 在 `game_engine.py` 重複 5 次、`npc_agent.py::load_lorebook` 再重複一次。

### 1.4 `src/npc_agent.py` — `NPCAgent`

- `build_system_prompt()`（38–158）：組出整個 system prompt，包含玩家狀態、已用過選項、章節脈絡、世界觀/文風範例，以及一段**手打的 JSON schema 範例字串**（131–156 行）——不是從 `GameStateDelta` 的 Pydantic schema 動態產生，可能跟真正的 model 漂移。有 `system_prompt_override` 分支（目前只有柳如煙/合歡宗聖女使用）會用完全自訂的 prompt。
- `process_action()`（276–351，非串流）與 `process_action_stream()`（353–433，串流）**幾乎整段複製**：system prompt 組裝、history 去重/切片、`context_bridge` 建構、`action_prompt` 文字，四塊邏輯逐字重複；成功/fallback 路徑的 history/`used_options_history`/`current_status_tag` 記帳邏輯更是重複了 3 次（兩個方法的成功路徑各一次，`process_action_stream` 的例外路徑再一次）。
- `_generate_fallback_delta()`（160–253）：用 **NPC 名稱字串的 if/elif 鏈**寫死每個角色 LLM 失敗時的劇情與選項——新增一個 NPC 到 `config/npcs.json` 卻忘了改這裡，就會靜默掉進通用 fallback。
- `get_deduplicated_history()`（255–274）：只用「前 40 字重複」的簡單啟發式抓重複，不是真正的迴圈偵測。

### 1.5 `src/ollama_client.py` — `OllamaClient`

- 打的是舊版 `/api/chat`（不是 `/v1/chat/completions`），固定送 `"format": "json"` + 一組寫死的取樣參數。
- 4 個手刻的 JSON 修復函式：`clean_json_text`、`repair_truncated_json`、`extract_partial_narrative`、`parse_json_robustly`——都是手寫字元掃描，不是用容錯 JSON 函式庫；`parse_json_robustly` 最後一次嘗試沒有防護，失敗會直接丟出未捕捉的例外。
- `chat_structured()`：失敗時**只重試一次**（附加一句「請輸出合法 JSON」），第二次還失敗就讓例外往外傳（交給 `NPCAgent.process_action` 的外層 try/except 接住並換成 fallback）。
- `chat_structured_stream()`：整個 try 區塊被外層 except 包住，**串流失敗會靜默退化成呼叫非串流的 `chat_structured()`**，呼叫端完全不知道這次其實沒有串流。
- `chat_structured`（含重試）與 `chat_structured_stream` 各自組了一份幾乎一樣的 request payload dict，三份重複字面量。

### 1.6 `src/save_manager.py` — 存檔系統

**兩套並存的存檔機制：**
- Slot-based：`save_slot_N.json`（1–5 號槽位）
- Account-based：`account_<sanitized_name>.json`

`save_game()` 和 `save_account_game()` 幾乎是複製貼上（只有路徑產生函式跟一個 dict key 不同）。**確認硬碟上 `saves/` 目錄目前只有 `account_*.json` 檔案，一個 `save_slot_*.json` 都沒有**——slot 機制在實務上是死的。更嚴重的是 `list_saves()`/`get_latest_save_slot_id()` **只支援 slot 機制**，所以「載入最新存檔」這個功能對現有的 account 存檔完全找不到東西。

另外，`story_milestones` 和每個 NPC 的 `used_options_history` **從未被存進存檔**——讀檔後這兩樣會靜默重置，但 `game_turn` 和對話 history 不會，造成一個不一致的存檔快照。

### 1.7 `web_ui.py`（995 行）— Gradio Web UI

- 全域 `session_engines: dict`（27 行），用**玩家自己打的名字字串**當 key 對應一個 `GameEngine` 實例——不是 Gradio 真正的 per-session 機制，兩個瀏覽器分頁打同一個名字會共用同一個活的 `GameEngine`，沒有任何鎖。模組載入時就即時建立一個預設引擎（43 行）並可能觸發磁碟 I/O，是 Gradio 的反模式。
- `generate_dynamic_options`/`generate_single_option`/`get_npc_initial_options`（46–263 行，約 220 行）：**第三份**per-NPC fallback 選項內容，跟 `npc_agent.py::_generate_fallback_delta` 是各自獨立寫的兩套系統，而不是同一份重複兩次。
- `process_player_choice()`（612 行）呼叫 `engine.interact(user_input)`（**648 行，確認是非串流版本**），從未呼叫 `interact_stream`——串流功能雖然引擎端已經寫完，UI 端完全沒接。它自己的 except 區塊還會伸手呼叫 `engine.current_agent._generate_fallback_delta()`（私有方法），跟 `NPCAgent.process_action()` 內部本來就有的 fallback 處理重複。
- 所有事件處理函式回傳長串「位置對應」的 tuple 給 Gradio `outputs=[...]`（例如一次回傳 19 個值），測試裡甚至用 `res1[12]` 這種魔法索引去驗證——順序一換就悄悄壞掉。

### 1.8 `server/` 目錄

**完全是空的**——沒有任何檔案，git 歷史上也從未有過任何被追蹤的檔案。不是另一個 HTTP server，沒有跟 `web_ui.py` 有任何關係，只是一個沒人用的空目錄。

### 1.9 `main.py`（CLI）vs. `web_ui.py`

兩者共用同一套 `GameEngine`/`NPCAgent`/`OllamaClient` 核心（沒有分岔），但呈現層已經分岔：

- CLI 的 `/status` 指令**寫在說明文字裡，但指令分派的 if/elif 鏈根本沒有這個分支**——打 `/status` 會被當成一般玩家行動送給 LLM。
- `GameStateDelta.options` 永遠有 5 個選項，但 CLI 只把 A/B/C 三個做成 hotkey，D/E 要手打。
- CLI 從未呼叫 `auto_save()`，只有 `/save N`/`/load N` 的 slot 指令——這代表 CLI 的進度完全不會出現在 Web UI 的「帳號繼續遊戲」流程裡，兩端進度互不相通。
- CLI 的選項 fallback 種子文字（`main.py` 99–103 行）還停留在舊的「勞基法/現代法律梗」風格，跟最新一次 commit 已經從 NPC prompt 移除的搞笑風格不一致——呈現層沒有跟著同步更新。

### 1.10 測試現況

`tests/test_engine.py`、`test_ollama.py`、`test_save_manager.py` 涵蓋核心邏輯，且**全部離線可跑**（所有 Ollama 呼叫都用 `unittest.mock.patch` 掉，沒有測試需要真的連線到 Ollama）。已知覆蓋率缺口：

- `GameEngine.interact_stream` / `NPCAgent.process_action_stream`：**零測試覆蓋**（只有 `OllamaClient.chat_structured_stream` 這個最底層有測到）
- `main.py`（CLI）：完全沒有測試檔
- `web_ui.py` 的大部分 handler（存讀檔按鈕、`on_select_location`、`enter_jianghu`、`continue_game`、`reset_chat`）：沒有測試

---

## 二、目標模組地圖

```
src/
  models.py          # 純 Pydantic schema（GameStateDelta, NPCProfile, PlayerState, GameConfig）
  content_loader.py  # 統一設定檔載入 + 快取（取代 5 份重複的 _load_* fallback 邏輯）
  state.py           # GameState：純資料容器（取代 GameEngine 身上散落的欄位）
  rules.py           # apply_delta / evaluate_ending / get_current_chapter_info / 親密度分級查詢
  npc_autonomy.py    # simulate_npc_autonomous_actions，資料驅動化
  options.py         # CLI 與 Web UI 共用的選項/fallback 產生邏輯（收斂現有 3 份重複實作為 1 份）
  npc_agent.py        # 精簡：只保留 prompt 組裝 + LLM 呼叫協調，消除 stream/non-stream 重複
  ollama_client.py    # 精簡：payload 建構統一為一個 helper，JSON 修復邏輯保留但職責註記清楚
  save_manager.py     # 只留 account-based 存檔，修正 list/latest 查詢
  game_engine.py       # 變薄成 facade，組合以上模組，對外方法簽章維持不變（main.py/web_ui.py 呼叫端不用改）
config/
  npc_stages.json     # 成為親密度分級的唯一真實來源（目前是死設定，將被接上）
  npc_fallbacks.json  # 新增：每個 NPC 的 fallback 劇情/選項內容（資料化，取代 if/elif 與硬編碼表）
  npc_autonomy.json   # 新增：目前寫死在 game_engine.py 的 activities_pool
```

`GameEngine` 維持作為 `main.py`/`web_ui.py` 唯一的對外入口（不引入第二個 facade 或 repository/service 分層），只是從「什麼都自己做」變成「組合以上模組」。這是個人 hobby 專案，設計上刻意不引入 DI container、抽象介面（ABC）或企業級分層——維持現有「Pydantic model + 一堆職責單一的檔案」風格。

### 職責對照表（舊 → 新）

| 現有位置 | 職責 | 新位置 |
|---|---|---|
| `game_engine.py` 5 個 `_load_*` 方法 | 設定檔載入 + 重複的 fallback | `content_loader.py`：一個 `load_json_or_default(path, default)` |
| `GameEngine` 身上的散落欄位 | 執行期狀態 | `state.py::GameState` |
| `GameEngine.apply_delta` | 回合結算規則 | `rules.py::apply_delta(state, delta)` |
| `GameEngine.evaluate_ending`、`get_current_chapter_info` | 規則查詢 | `rules.py` |
| `GameEngine.simulate_npc_autonomous_actions` + `activities_pool` | NPC 自主行為 | `npc_autonomy.py`，資料移到 `config/npc_autonomy.json` |
| `NPCProfile.get_unlocked_biography/get_unlocked_stats` 寫死 25/50/75 | 親密度分級 | `rules.py::get_intimacy_stage(profile, stages_data)`，讀 `config/npc_stages.json` |
| `web_ui.py::generate_dynamic_options`（~220 行）+ `npc_agent.py::_generate_fallback_delta` if/elif | fallback 內容 | `options.py` + `config/npc_fallbacks.json`，CLI/Web UI/NPCAgent 三方共用 |
| `npc_agent.py` 手打的 JSON 範例字串 | LLM schema 範例 | 從 `GameStateDelta.model_fields` 動態產生 |
| `ollama_client.py` 3 份重複的 payload dict | request 建構 | 一個 `_build_payload(...)` helper |
| `save_manager.py` slot 相關函式 | 死機制 | 移除 |

---

## 三、關鍵設計決策

**串流：接上 Web UI，CLI 明確不接。** Gradio 原生支援 generator 更新 UI，改動小；純文字終端機逐字重寫游標的 UX 效益低於實作複雜度。在 `main.py` 留一行註解記錄這個決定，避免日後看起來像遺漏或忘記做。

**存檔：只保留 account-based。** 硬碟上實際存檔只有這種格式，slot 機制在現實中沒被使用；移除 `save_slot`/`load_slot`/`load_latest_slot` 與 `save_manager.py` 對應函式，`list_saves()`/最新存檔偵測改成掃描 `account_*.json` 並依內嵌時間戳排序。同時補回目前會被存檔遺失的 `story_milestones`、`used_options_history`。

**親密度分級：`config/npc_stages.json` 成為 SSOT。** `NPCProfile` 的解鎖方法改成查表；查無資料的 NPC（或設定檔被改壞）才 fallback 回目前的 25/50/75 寫死值，確保向後相容。額外機會（非必要）：把 `npc_stages.json` 裡的 `behavior`/`unlocked_topics` 文字餵進系統 prompt，讓這份設定從「死資料」變成真正影響劇情的功能。

**LLM JSON schema 範例：從 `GameStateDelta.model_fields` 動態產生。** 不再手打字串；加一個「產生的欄位集合 == `model_fields.keys()`」的回歸測試，防止未來新增/改動欄位又忘記同步 prompt——這正是目前這個 bug class 的成因。

**Fallback 內容：收斂進 `config/npc_fallbacks.json`。** 用 `{player_name}`/`{disp_name}`/`{location}` 佔位符；查無資料的新 NPC 用 `profile.identity`/`profile.personality` 動態生成通用 fallback，而不是掉進沒有角色特色的通用文字，也不需要每新增一個 NPC 就強制手寫一份 fallback 劇情。

**JSON 修復分層：保留兩層，但把界線寫清楚。** `ollama_client.py` 修的是「文字」層（去除 code fence、修補截斷、修多餘逗號），`models.py` 的 validator 修的是「已解析 dict」層（型別強制轉換、欄位別名）——兩者其實不是完全重工，只是沒有講清楚各自負責什麼。把 `normalize_llm_dict` 拆成 4–5 個具名 private helper（純重構、不改行為），並在兩個檔案開頭各寫一行註解說明自己是哪一層。

**`server/` 目錄：直接移除。** 確認為空、從未被使用；未來若真的要做 HTTP API 層（例如支援 ROADMAP 階段四的 Mod 工具），屆時再有意識地重新建立並附上說明，而不是留一個沒人解釋的空資料夾。

**LLM 連線層維持隔離，為未來網頁化鋪路。** 依 VISION.md 六，網頁化＋伺服器端 LLM 是明確的後期目標，但近期只做本機版。因此在拆分 `GameEngine` 時（Stage 7）要刻意保持一個不變式：「怎麼連到 LLM」這件事只集中在 `ollama_client.py`，`rules.py`/`state.py`/`npc_agent.py` 的其他部分不應該知道底層是本機 Ollama 還是未來的遠端伺服器。這不需要額外的抽象層或介面設計，現有結構本來就大致如此，只是要在後續每個 Stage 的 PR 裡守住這條界線，別讓 Ollama 特定的細節（例如 `/api/chat` 的請求格式）滲透到 `ollama_client.py` 以外的地方。

**`GameConfig.context_length`：接上而不是刪除。** 把 `ollama_client.py` 三處硬編碼的 `"num_ctx": 4096` 換成從 `GameConfig` 傳入的 `self.context_length`，同時解決「死欄位」跟「三份重複字面量」兩個問題。

---

## 四、分階段重構順序

每階段獨立可交付、可測試，由低風險排到高風險；後面階段依賴前面階段完成。目前進度見 [CLAUDE.md](CLAUDE.md)。

**Stage 0 — 補測試安全網（不改行為）✅ 已完成**
`interact_stream`/`process_action_stream` 目前零覆蓋率，先補上 mock 測試（成功路徑 + fallback 路徑），再動大範圍重構才安全。
檔案：`tests/test_engine.py`、`tests/test_save_manager.py`、新增 `tests/test_streaming.py`

**Stage 1 — 清死程式碼/死設定 ✅ 已完成**
移除 `available_exits`、`region_events`、`key_event`；把 `GameConfig.context_length` 接進 `ollama_client.py`（取代 3 處硬編碼）；移除 `server/`；刪除/重建過時的 `scripts/test_prompt.py`。
檔案：`src/models.py`、`config/world_map.json`、`config/story_outline.json`、`src/ollama_client.py`、`server/`、`scripts/test_prompt.py`

**Stage 2 — 存檔系統整併 ✅ 已完成**
移除 `save_manager.py`/`GameEngine` 的 slot 機制；修正 `list_saves`/最新存檔偵測改用 account 機制；補回 `story_milestones`/`used_options_history` 的存讀；`main.py` 改用 account 存讀 + 補上 `/status` + 5 個選項全部 hotkey。
檔案：`src/save_manager.py`、`src/game_engine.py`、`main.py`、`tests/test_save_manager.py`（改寫成針對 account 機制）

**Stage 3 — 共用 fallback/選項模組 ✅ 已完成（commit `699551d`）**
建立 `config/npc_fallbacks.json` + 通用 fallback 生成；建立 `src/options.py`；`npc_agent.py::_generate_fallback_delta` 與 `web_ui.py::generate_dynamic_options` 都改呼叫它，刪掉兩份寫死的內容。
檔案：`config/npc_fallbacks.json`（新）、`src/options.py`（新）、`src/npc_agent.py`、`web_ui.py`、新增 `tests/test_options.py`

**Stage 4 — 親密度分級 SSOT ✅ 已完成**
接上 `config/npc_stages.json`，新增 `rules.get_intimacy_stage()`（此時可先建立最小版的 `rules.py`，或延後到 Stage 7 一起做——排程上兩種順序都可以）。
檔案：`src/rules.py`（新，最小版）或 `src/models.py`、新增 `tests/test_models.py`（涵蓋邊界值 24/25/49/50/74/75 與未知 NPC 的 fallback）

**Stage 5 — Prompt/schema 去重複**
JSON 範例改成從 `GameStateDelta.model_fields` 動態產生 + 加回歸測試；`load_lorebook` 改成 process 內快取而非每回合讀檔；抽出 `process_action`/`process_action_stream` 共用的 `_build_messages`/`_record_turn` helper；`ollama_client.py` 的 payload 建構整併成一個 helper。
檔案：`src/npc_agent.py`、`src/ollama_client.py`、`tests/test_ollama.py`、`tests/test_engine.py`

**Stage 6 — Web UI 接上串流**
`process_player_choice` 改成迭代 `engine.interact_stream(user_input)`，逐步更新敘事文字框/Chatbot，只在最後一個 yield（`delta is not None`）才更新狀態與選項；移除多餘的私有方法 `_generate_fallback_delta` 呼叫（改用 Stage 3 的共用模組）；`main.py` 留註解記錄「CLI 刻意不接串流」的決定。
檔案：`web_ui.py`、`main.py`（僅註解）

**Stage 7 — `GameEngine` 拆分為 facade（風險最高，排最後）**
抽出 `content_loader.py`（收斂 5 個 `_load_*` 成一個 helper）、`state.py::GameState`、`rules.py::apply_delta/evaluate_ending/get_current_chapter_info`（若 Stage 4 還沒做就一併納入）、`npc_autonomy.py` + `config/npc_autonomy.json`（把寫死的 `activities_pool` 資料化）。`game_engine.py` 變薄成 facade，對外方法簽章維持不變，`main.py`/`web_ui.py` 呼叫端不用改。順手修掉「同一回合 NPC 自主行動可能觸發兩次」的 bug，讓它每回合只跑一次。
檔案：`src/content_loader.py`、`src/state.py`、`src/rules.py`、`src/npc_autonomy.py`、`config/npc_autonomy.json`（皆為新增）、`src/game_engine.py`（改寫為 facade）、`tests/test_engine.py`（拆分/擴充）

**Stage 8 — 戰鬥系統擴充點（僅文件，不實作）**
為 ROADMAP 階段二的**輕量戰鬥**預留位置——依 VISION.md 三，戰鬥不做獨立畫面/模式切換，而是跟一般 NPC 互動走同一套「選項 → LLM 敘事回合」流程。判定邏輯（用敏捷/戰力/勢力等數值算出成功率或傷害區間）放在新的 `src/combat.py`，是一個純函式：輸入雙方相關屬性，輸出一個結構化結果，交給 `rules.py` 折算進 `GameState`（跟今天 `apply_delta` 的模式一樣），這個結果會被當成額外上下文餵進 `npc_agent.py` 的 prompt，讓 LLM 生成對應的敘事描寫，而不是另外做一個戰鬥狀態機或獨立 UI。`NPCProfile.stats`（attack/defense/agility/weapon）已經存在不用改；`PlayerState.inventory` 目前是 `List[str]`，等真的要做裝備欄位時才需要升級成 `Item`/`Equipment` model，這部分明確排除在本次重構範圍外。

---

## 五、與 ROADMAP.md 的關係

本文件的模組拆分刻意讓 Stage 7 之後的 `rules.py`/`state.py`/`game_engine.py` facade 能乾淨地接上 ROADMAP 八個階段的功能，特別是：

- **階段一（新手引導與建角系統）**：不在本次重構範圍內，屬於新功能。等 Stage 7 完成、`PlayerState` 仍是乾淨的 Pydantic model 之後，加背景/出身/初始屬性欄位跟一個建角流程，改動會侷限在 `models.py` 加欄位 + `main.py`/`web_ui.py` 各自加一個開局前的新畫面/新問答，不需要動 `rules.py`/`content_loader.py`。內容分級開關同理，是 `GameConfig`/`GameState` 上加一個布林旗標，讀取點集中在 `npc_agent.py::build_system_prompt`（決定要不要把成人向 lorebook 段落餵給 LLM）。
- **階段二（輕量戰鬥）**：見上方 Stage 8，`src/combat.py` 是獨立模組，跟現有 `apply_delta` 同一種介面模式，不是另一套戰鬥引擎。
- **階段三（長期記憶/串流）**：串流部分本文件 Stage 6 已經處理；長期記憶（摘要/RAG）屬於全新功能，等 Stage 7 完成後，`state.py`/`content_loader.py` 的拆分會讓「查詢歷史摘要」有清楚的落腳點，而不是又塞進 `GameEngine`。
- **階段四（地圖視覺化/隨機事件）**：`world_map.json` 的 `region_events` 目前是死欄位（Stage 1 會先移除），若階段四要做隨機遭遇，屆時應該重新設計這個欄位的 schema，而不是復用已經被清除的舊設計。
- **階段五（勢力與門派系統）**：延伸 Stage 7 拆出的 `npc_autonomy.py`/`config/npc_autonomy.json`——勢力消長模擬跟現有的 NPC 自主行動是同一種「背景模擬」模式，資料驅動的設計讓兩者可以共用同一套機制，不需要另起一個系統。
- **階段六（Mod/自訂 NPC 編輯器）**：Stage 3 的 `config/npc_fallbacks.json`、Stage 4 的 `config/npc_stages.json` 接上，都是讓 NPC 資料更「資料驅動」，直接降低未來做 Mod 編輯器的門檻；`server/` 目錄若這個階段真的需要 HTTP API，屆時再重新建立。
- **階段七（UI/UX 升級）**：不影響本文件範圍，屬於純呈現層工作。
- **階段八（網頁化與雲端部署）**：見上方「LLM 連線層維持隔離」設計決策——這是這個階段能不能低成本執行的關鍵前提。
