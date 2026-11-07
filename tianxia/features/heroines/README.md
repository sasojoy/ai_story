# 女子與隱線（`tianxia/features/heroines/`）

- 做什麼：幾位女子透過一條奇事出場，走完留在當地可以交談，說話跟著結局走；設定頁開了成人內容（預設關、確認年滿十八歲）的人另有一條隱線（兩段固定文字，尺度甲：寫到熄燈）。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「女子與隱線」那一節
- 設計稿：https://claude.ai/artifact/UBuM248hcNqTV9JWQsfUNb（Joy 2026-11-06「開工」；尺度「那先甲就好」；阿蘭「先把她這條整個拿掉」）
- 開關：沒有 Config 開關。`content/heroines.json` 有人就開（測試內容沒有這個檔＝關著，一個選項都不給）。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：options（「此地還能做」的那一顆）、menu（端在眼前時只剩應下、婉拒）、choose、status（設定頁那一格）、on_season_start、routes、check_content |
| `rules.py` | 純規則：她出不出現（`present`、`placed`）、隱線端不端得出來（`next_scene`）、給模型的那幾行（`prompt_lines`、`role`）、過濾（`clean`）、隱線的交談（`hidden_talk`，給交談點數那一份用） |
| `actions.py` | 選項、選單、端出與收、成人內容開關（`set_adult`，假人不准）、換季 |
| `routes.py` | `POST /api/heroines/adult` {value} |
| `checks.py` | `content/heroines.json` 的檢查（人物、奇事、結局、兩段、固定文字不准有的字） |
| `tests/` | `test_heroines.py`（10 條，1 條 slow）、`test_heroines_smoke.py`（2 條 smoke）、`heroines_stage.py` |

**接在別處的**：`figures.placed_characters` 問共用規則層的 `figures.heroine_ending`（`rules.ending_of` 也走它）（`heroines.json` 的 `stay` 寫了結局之後換去的地點；還不出現的女子不在任何地方：求見、交友、地圖都沒有她）；`companion_agent` 叫 `role`（提示開頭扮演誰）、`prompt_lines`（故事之後、你們之間、分寸）、`clean`（`_apply_turn` 開頭：寫回來的與玩家打的過一次）。網頁：設定抽屜的 `adultRow`（`web/app.js`，打開先跳確認卡）。
**認領的欄位**：`PlayerState.heroines`（`HeroineNotes`：steps、scene、declined；換季重來）、`PlayerState.heroines_adult`（成人內容的開關；`carried`，換季在 on_season_start 照帶）。
**不寫進**：傳聞、江湖史、行狀、列傳。隱線兩段只寫一則自己的江湖紀錄（標題是她的名字）。
**緊急關**：拿掉 `content/heroines.json` 某一位的 `scenes` 就沒有隱線（她照舊出場、照舊交談，提示照「只寫交情」）。整個檔拿掉她會一直站在 talk_at（沒有出場條件了），要連人物表那一位一起拿掉。
