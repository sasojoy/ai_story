# 開局前導（`tianxia/features/intro/`）

- 做什麼：新角色取完名號、站到潁川城門口之前，演一段 55 秒的水墨畫本（時空背景，張角、皇甫嵩、朱儁、波才）。可以跳過，看過不再自動播，設定裡能重看。開關 `Config.intro.enabled` 預設關，week7、season21 設定覆寫檔打開（Joy 2026-11-11 PR #225，已上線）。網頁比對起的伺服器（`scripts/webqa/serve.py`）把它關掉（比對的帳號都是新角色，開場那一層會蓋住要按的鈕），`web/intro.js` 因此在 `scripts/webqa/gate.py` 的 `NOT_ON_TABLE`：改這一包的網頁靠包自己的測試。
- 導覽：`docs/guide/核心與存檔.md` 的「開局前導」那一節
- 設計稿：評估與示意 https://claude.ai/artifact/X6yiopXuXDk8gAwaNX5WVq（Joy 2026-11-10「這種形式可以 想壓在60秒內」）
- 認領的欄位：沒有（看過記在 `PlayerState.flags` 的 `看過:開場`）
- 相關的 slow：沒有
