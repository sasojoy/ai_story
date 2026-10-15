# 名聲畫面草圖

第 3 塊「名聲」（`docs/superpowers/specs/2026-10-15-名聲-design.md` 2.5、3.3、5.3、第六節）的畫面對照：五處（第五處分成事件選項與江湖紀錄兩段），每一處兩三種，說明卡多畫一種，標一個推薦。

- `renown-sketch.html`：發佈成 artifact 的那一頁（企劃者帳號下、私人的）。上面可以切跟系統／淺色／深色。
- `產生器/`：怎麼畫出來的。只做草圖，不是遊戲程式。

## 怎麼畫的

1. `build.py`：正式內容、週末設定，用 `Game` 建兩個示範角色（顧長風：官軍・屯長、名望 27、善名 18、惡名 3；韓七：散人、名望 12、善名 4、惡名 22）與一場宛城之戰（六個人打到第三回合），拿 `server.main_view` 與玩家卡（`social.card`）的資料。不連模型、資料庫開在暫存資料夾。
2. `gen.py`：名聲的資料照設計第二、四、五節的表算好，加在 `status.renown`、玩家卡與本場戰功那幾列上（引擎還沒有這些欄位）。拿真的 `web/app.js` 複製一份，只改草圖要的幾個地方（名號那一塊、玩家卡、本場戰功、選項、說明卡；改法寫在 gen.py，新加的函式在 `mock.js`），在 `tests/webharness.py` 的假瀏覽器裡跑 `render()` 畫出每一種。
3. `page.py`：把每一種放進 375 寬的 iframe 並排，遊戲的樣式是真的 `web/style.css` 加 journal 的 CSS，新加的樣子在 `mock.css`；紅色虛線框是新加的那一塊。

重畫（三步，依序）：

```bash
.venv/Scripts/python.exe docs/superpowers/specs/2026-10-15-名聲-草圖/產生器/build.py
.venv/Scripts/python.exe docs/superpowers/specs/2026-10-15-名聲-草圖/產生器/gen.py
.venv/Scripts/python.exe docs/superpowers/specs/2026-10-15-名聲-草圖/產生器/page.py
```

中間檔寫在系統暫存資料夾的 `renown-sketch/`。app.js 或 style.css 改了，重畫出來的就是改過之後的樣子；gen.py 的字串替換對不上會直接停下來。

## 量到的

- 收起時（第一處）：顧長風「官軍・屯長・名動一方・一方豪俠・第14級」在 375 寬要 287px，名號那一格只有 267px，所以 1A 收掉名望稱號；縮到 10.5px 是 254px（1C）。韓七「散人・小有名氣・江湖巨寇・第12級」剛好 234px 放得下。假瀏覽器量不到字寬，產生器用字數估，這幾個數字是在瀏覽器裡量的。
- 本場戰功（第四處）：B 比 A 高 41px、C 高 76px，三招跟著往下推。
