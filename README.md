# 天下大勢（原型）

一個由玩家寫下結局的文字武俠江湖。設計文件見 `docs/superpowers/specs/2026-09-27-天下大勢-design.md`。

## 安裝與執行

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app.py
```

打開 http://127.0.0.1:7861 ，輸入名號即可開始；同一個名號會自動讀取存檔（`saves/`）。

## 測試與平衡

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/simulate.py 30
```

## 修改內容

所有地點、事件、武學、敵人、大勢線都在 `content/` 的 JSON 裡，改完重啟 `app.py` 即可。內容寫錯時，啟動會直接列出是哪個 id 出錯。
試玩時可以在「設定」分頁快轉時間，或把 `content/config.json` 的 `time_scale` 調大。
