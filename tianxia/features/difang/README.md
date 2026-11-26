# 地方大事（`tianxia/features/difang/`）

- 做什麼：全服一週一件大事、輪著換大區（潁水決堤、宛城時疫……），人到了那一區用平常的探索、出陣出力，再挑做法、輪流上前，三幕湊滿了江湖史刻名字、出過力的人挑一份四階謝禮，沒湊滿此地鬧饑荒。
- 導覽：`docs/guide/散人與玩家互動.md` 的「地方大事」那一節（規則、欄位、畫面、還沒做的都寫在那裡）
- 設計稿：玩家一起玩設計稿第一節（https://claude.ai/artifact/J2hWqymn9SXRgw1qashgKb；Joy 2026-11-26「做」）
- 開關：`Config.difang.enabled`（預設關）。欄位：`WorldState.difang`（QUIET）。內容：`content/difang.json`（包自己讀，`rules.FILE`）。
- 測試：`tests/`（煙霧、三幕與收場、畫面）；另外動到的：`tests/core/test_contract_core.py`（`BUS_ORDER` 兩格）、`tests/server/test_server.py`（推送指紋的分類）、
  `tianxia/features/guide/tests/test_explain2.py`（名望來源兩行）、`scripts/webqa/gate.py` 的 `NOT_ON_TABLE`（開關關著，沒有回合走得到）。
