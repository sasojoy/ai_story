# 三國同伴好感度整合 — 設計

- 日期：2026-09-30
- 狀態：企劃階段，待確認三個開放決策後開工
- 分支：`feature/sanguo-companions`（base：`tianxia`，獨立於 `feature/conquest-route-redesign`）
- 背景：把 `ai_story`（原本的征服路線引擎）與 `ai_story-tianxia`（天下大勢原型）合併成同一個專案。
  兩邊是同工作室、同一個起點分出去的專案，不是外部依賴，可以自由重組。

---

## 一、範圍

**保留 tianxia 的部分**：體力／行動經濟、地圖（`atlas.py`/`mapview.py`）、事件骨架
（`content/events/*.json`）、大勢線與賽季結構、門下名冊與隊伍、招賢抽卡。

**不保留 tianxia 的部分**：`battle.py` 三對三全自動戰鬥系統（本次明確排除）。

**從 ai_story 移植的部分**：`src/npc_agent.py` 的「LLM 每回合生成對話 + tag 查表決定
好感度變化（不信任 LLM 自報數字）+ 關係現況記憶」核心機制，**不含**
`intimate_mode.py`/`scene_templates.py`/`ending_writer.py`/`rwkv_client.py`（性愛模式與
結局劇情相關的東西全部不搬）。

**世界觀**：改成三國（史書公版，人物/地名/事件可以直接用真實名字，不用擔心版權——這點
跟 tianxia 原本「金庸人名一律原創」的規則不同，是這次明確的方向調整）。

---

## 二、現況盤點（讀過雙邊程式碼後的結論）

- tianxia 的 `Member`（`tianxia/state.py`）目前只有 `level`/`exp`/`neili`/`innate_level`，
  **沒有好感度欄位**，需要新增。
- tianxia 的同伴目前是純資料（`content/characters.json`：品階/統御/流派/武學/取得管道），
  沒有個性化對話、沒有記憶——這正是要從 ai_story 補進去的部分。
- ai_story 的好感度機制（`src/rules.py`／`src/npc_agent.py`）是圍繞「單一路線走向終局
  （好結局 80 / 黑化 -50）」設計的，多人賽季制沒有這種終局概念，直接照搬會不合邏輯。
- ai_story 的 `NPCAgent` 呼叫 Ollama 是**每回合都要**（游戲核心玩法依賴即時 LLM）；
  tianxia 的既有原則是「規則引擎決定一切數值，AI 選用、逾時直接退回原始文字」——這條
  原則本身是好的工程實踐（多人賽季遊戲不能讓單次 LLM 逾時卡住一個行動），不是「因為
  是 Ray 的規則所以要遵守」，是獨立於歸屬的正確設計，這次移植會延續。

---

## 三、整合設計

### 3.1 新模組：`tianxia/companion_agent.py`
從 `src/npc_agent.py` 移植並精簡：
- 保留：`_build_messages`/`_record_turn` 對話歷史管理、schema-constrained JSON 輸出、
  tag 查表決定數值變化（不信任 LLM 自報）、`npc_relationship_note` 保底機制、記憶梳理
  （`consolidate_memory`，20 回合一次）、連線失敗/解析失敗時的 fallback（改用 tianxia
  已有的事件骨架當保底，不用另外設計一套 fallback 文案庫）。
- 移除：`intimacy_tags` 裡黑化方向的用語、`bad_ending_flow`、`character_tags` 那一整套
  情慾向標籤。

### 3.2 `Member` 新增欄位（`tianxia/state.py`）
```python
affinity: int = 0            # 0~100，見四.2 的開放決策
relationship_note: str = ""  # 沿用 ai_story 的「一句話關係現況」保底機制
```
舊存檔沒有這兩個欄位時預設 0/空字串，不用遷移腳本。

### 3.3 觸發點：交遊
`tianxia/roster.py`/事件骨架目前的「交遊」是純事件骨架驅動。這次改成：同伴的
`content/characters.json` 標記 `deep_interaction: true` 的人，交遊時改走
`companion_agent.py` 的即時對話（一段個性化敘事 + 2~3 個帶 tag 的選項），系統照 tag
查表更新 `affinity`；沒標記的同伴維持原本的事件骨架/範本文字，兩條路徑並存，不用把
全部 14 位同伴都換成 LLM 對話（見四.3 的開放決策）。

### 3.4 好感度門檻的效果
不做「終局」，改成解鎖：對話話題深度（比照 ai_story 已經閒置在 `npc_stages.json` 的
`unlocked_topics` 概念）、小額屬性加成、專屬奇遇事件——具體門檻數字與效果留給實作階段
用模擬器（`scripts/simulate.py`）調。

---

## 四、開放決策（需要確認才能開工）

### 4.1 拿掉戰鬥後，「歷練」「劇情戰」這類原本靠 `battle.py` 解決的行動怎麼處理？
tianxia 其實已經有一套獨立於戰鬥的「檢定」機制（`Check.by` = `"team"`/`"self"`，辦事類
由隊伍該屬性最高者出手、修行類只看本人），目前只用在非戰鬥事件的選項判定。
**建議**：歷練與劇情戰也改用這套檢定機制解決（抽象化成「隊伍屬性 vs 難度」的判定 +
文字結果），不重新做一套簡化戰鬥。好處是重用既有系統、不用再造一次戰鬥的輪子；壞處是
會失去 tianxia 原本戰鬥系統裡「陣容搭配」的策略深度，練功/收同伴的意義會變弱一些。

### 4.2 好感度數值範圍
ai_story 用 -50~80（因為要對稱處理「好結局／黑化」兩個方向）。**建議**：多人賽季制沒有
終局，改成單純 0~100「情誼」，只有一個方向，門檻只解鎖內容不觸發黑化。

### 4.3 深度 LLM 對話要開放給全部同伴，還是先選幾位試點？
tianxia 設計文件裡本來就有「重要地點手寫、一般地點範本」的分級投入原則
（design.md §5.4）。**建議**：套用同樣邏輯，先選 3~5 位「看板角色」標
`deep_interaction: true` 做完整驗證（含實測 LLM 可靠度、速度、內容品質），其餘同伴維持
純資料+事件骨架，之後好玩再擴大範圍，不要一次對 14 位同伴都接 LLM。

---

## 五、三國重皮範圍（原型階段，1 大區）

比照 tianxia 原型範圍（1 大區、20~30 地點、14 位同伴、30~50 事件），這次重皮只需要
在**既有內容量**上改名字/背景，不用新增內容量：
- `content/characters.json`：14 位同伴的姓名/背景改成三國人物或原創武將，統御/品階/武學
  數值不動。
- `content/locations.json`/`content/map.json`：地點改真實三國地名（先鎖同一大區規模，
  例如「中原」或「江東」）。
- `content/sects.json`：門派概念在三國語境下改成「勢力／陣營」（例如曹營、劉備陣營），
  或保留「武學傳承」意義上的門派（例如黃巾餘部、某位名師的兵法傳人）——具體怎麼對應
  留給實作階段，先不在這份文件定案。
- `content/scenario.json`：大勢線劇本改三國史事骨架（例如「黃巾之亂」「群雄割據」），
  走向仍由玩家推動，不是照抄史書結局。
- `content/skills.json`：武學名稱改用三國背景合理的兵法/武藝名稱。
