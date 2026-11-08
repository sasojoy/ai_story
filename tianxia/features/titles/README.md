# 稱號與官職（`tianxia/features/titles/`）

- 做什麼：頭銜分三等（尋常不能配戴、不印名帖；官職第 2 階起墨印；名號金印或朱印），一次戴一個。名次型的名號每週結算一次（季曆換週之後第一個同步的人替全服頒），整週有效；一季的名號拿到就整季有效；拿過的名號收進名號簿（`PlayerState.title_book`）往後都能印名帖。**不加任何屬性**（Joy 2026-11-08「不加屬性，靠稀有和顯示」）。開關 `Config.titles.enabled`（`tianxia/core/tuning/titles.py`）預設關。
- 導覽：`docs/guide/散人與玩家互動.md` 的「稱號與官職」那一節
- 設計稿：稱號與官職重做 v5（Artifact https://claude.ai/artifact/1rXqs2bYVD9EKmu7w67nj4，2026-11-08）
- 檔：`rules.py`（名號清單 DEFS、三檔印色、誰拿得到、結算頒給誰、傳聞與紀錄的字）、`actions.py`（同步時的結算與配戴、換戴、狀態列資料）、`routes.py`（`/api/titles/wear {id}`，關著 404）、`web/titles.js`、`web/titles.css`
- 認領的欄位：`PlayerState.titles_pin`（自己挑的；"" 自動）、`titles_worn`（此刻戴的 `{"id","name","grade"}`，別處只讀這一格）；`WorldState.titles_week`（結算到第幾週）、`titles_holders`（這一週每個週名號頒給誰）。都標 QUIET，關著存檔一個鍵都不多。
- 別處讀 `titles_worn` 的接縫（都先問 `Config.titles.enabled`，關著一個字都不變）：核心 `presence.affiliation`（拿掉擂台稱號與論功稱號）、`combat.battle_marks`（`title` 快照進 `BattleParticipant.title`，空的不寫鍵）；決戰包 `instance.merit_board`／`title_flags`（戰功榜第二行、將旗）、`_title_entrance`（戴名號的人加入時一句戰報）、`progress` 首功那一句；玩家互動包 `mingtie.earned`／`season_book`／`seal_of`（名帖只印官職、親傳、本命兵器、神器、名號簿；大印是戴的那一個）、`social.card`（玩家卡）；共用層 `leaderboard`（`WORN` 那一格，榜單名字後面的小印）。
