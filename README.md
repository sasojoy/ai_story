# Local Blade RPG CLI Engine

Local Blade RPG 是一個本地運行的文字 RPG 遊戲引擎，使用 Ollama 本地 LLM (如 Qwen2.5 / Llama-3.1) 驅動 NPC AI。

## 安裝與執行

1. 安裝套件依賴：
   ```bash
   pip install -r requirements.txt
   ```

2. 啟動 Ollama 服務並下載模型 (預設 `qwen2.5:7b`)：
   ```bash
   ollama run qwen2.5:7b
   ```

3. 執行遊戲：
   ```bash
   python main.py
   ```

4. 執行測試：
   ```bash
   pytest
   ```
