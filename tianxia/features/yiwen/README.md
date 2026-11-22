# 異聞（`tianxia/features/yiwen/`）

- 做什麼：探索時極低機率撞見一則怪事（三十句開場之一，一句一季一則），發掘者說那是什麼、一步一步寫出三幕；後來在同一處探索的人踩著舊腳印重走、看到發掘者的朱批與同一個順逆圓章。這一包的數值全由引擎決定（順逆、獎勵、足跡）。
- 導覽：`docs/guide/大勢人物與賽季.md` 的「異聞」那一節（第 247 批的句子在回報裡，波末文件代理寫）
- 設計稿：`docs/superpowers/specs/2026-11-20-異聞-design.md` 第 2 版（企劃者 2026-11-21「看過了，十題都照建議做」）；做法照總計畫 `docs/superpowers/plans/2026-11-21-異聞-計畫.md`（計畫與設計稿對不上的照計畫）。
- 開關：`Config.yiwen.enabled`（`tianxia/core/tuning/yiwen.py`，預設關，數字全是草案）＋開季蓋章 `WorldState.yiwen_on`；一律問 `rules.on(content, world)`。季中打開下一季才有；季中關掉撞見停、眼前那一則的選單接管放手（`PlayerState.yiwen` 留著）。

## 第 247 批（異聞一之一）做到哪

- 撞見（`BUS_ORDER["outing"]` 尾端那一格 `actions.on_explore`）：先擲重走（`rewalk_chance`，此地公開的、自己這一季還沒走完的則），沒中再擲發掘（季鐘 ≤ `discover_until_day` 天、全季 `season_cap`、一人一季 `free_per_player`、全服每天 `free_daily_cap`〔台灣日〕、地點類型對得上還沒被佔的開場）。假人、序章、籌備中、休季、別的事已經接管這一段（探索不在選單上）都不撞。種子是 sha256（`rules.roll`），不碰 `Game.rng`。
- 選單接管：眼前有一則就只剩「〈標題〉」（`yiwen:open`）與「放下」（`yiwen:drop`），走一趟停在這一段；走完之後只剩「收起」。撞見卡上的鈕走 `/api/do/yiwen_step`（鎖外工作的 op；這一批平鋪、不叫模型）。
- 每一幕一律寫替身（`broken` 那一句＋第一、二步的退路做法 `fallback_options`），走通三幕；有人走過的那一顆重放（回聲句；第一步多一行朱批）、同一個圓章。別人的則上沒人走過的那一顆鎖著（「這條路還沒開」；開岔路是異聞三）；這一個節點底下還沒有任何一幕的（逾時或放下公開後沒寫完的那一步）照設計 2.2.8 接著寫，不算岔路。
- 獎勵（核心 `apply_effect`）：寫成一幕 `per_scene`（順的那一幕多一個 `luck_material_tier` 階的此地素材，屬性取地點素材的第一個，共用層 `materials.tier_pick`）、重放一幕 `per_replay`、走完 `finish_first`（發掘者，加名望 `discover_fame`〔共用層 `renown.gain`〕、行狀「首見異聞」、江湖史具名一行）／`finish`；一則一人一季只算第一趟（`paid_scenes`、`done`）。
- 放下：發掘者一幕都沒寫→開場放回（`free_found`、`free_today` 不退）；已有幾幕→提早公開；後來的人→只清眼前。眼前那一則不見了（旁檔不在、旁檔少了那一列、開場改版拿掉、名額被收回）：選單不接管，下一次同步清掉、寫一則「那件怪事已經散了」。
- 易名帖：旁檔的鍵（`tales.discoverer`、`nodes.by`、`walks.account`、`reports.by`、`mutes.account`）由 `core/renames` 換，`*_shown` 不動；旁檔不在不建。

## 畫面（第 248 批：企劃者 2026-11-21 挑的乙版「頁邊朱批」，原始檔 `docs/superpowers/specs/2026-11-21-異聞-畫面/card-b.html`）

- 只在 `web/yiwen.js`、`web/yiwen.css`（class 一律 `yw-`，色只用 `style.css` 的變數）；資料全是 `main.yiwen.card`，伺服器、欄位、路由一個字沒動。
- 整頁的紙 `#yw-pop`（`MutationObserver` 照 `main.yiwen.card` 補上或拿掉）：頂上一行標題、「地點・異聞」、右邊「收起」。收起時頁上留一條「進行中」`.yw-track`（「異聞・〈標題〉（第幾幕／收尾）」，江湖錄 `.cx-track` 後面，沒有就 `#page` 最上面），點了叫回來；選單上的「〈標題〉」（`yiwen:open`）也叫回來（捕獲階段的 click 只清旗子）。
- 撞見卡（`yiwenCard`，還沒有幕）：頁首圖（此地有圖用它、沒有是墨暈底）、朱印「異聞」（實心，發掘者）／「舊腳印」（後來的人）、懸念楷書大字、框、地點與「已有 N 人走過」；段標「你看那是什麼」；路牌 `ywSigns`；灰著的「自己說」；「？ 異聞的規矩」；「放下」問一次。
- 每一幕（`yiwenScene`）：一頁書——左直條「第一幕」、中正文（順逆章蓋在末尾）、右頁邊朱批直書＋名號小印（只放前兩字，全名小字橫排在印下）；朱批照字數 `yw-zp-2`／`yw-zp-3` 折兩行、再縮字。回聲句畫在書上面，**發掘者那一步不畫回聲句**（PM 定）。較早的幕收成一行 `.yw-prev`，點了原地攤開。
- 路牌：有人走過的照足跡多到少排前面，再沒人走過的（「免費開」，發掘者寫「寫下這一步」）、要香的（「問路香 1」，異聞三才會給）、鎖著的（灰、按不下去、籤寫伺服器的 `note`）；`state: "full"` 併成一列「a・b ｜開完了」＋頁下灰字；別人自己說開的路（`typed: true`、`i: "zhupi"`）朱色帶「某某說的」——這三種鍵伺服器什麼時候給是異聞二、三的事。
- 等說書人寫（`yiwenWait`）：按了沒人走過的那一顆、請求 250ms 還沒回才畫；格線頁、三顆墨點（`prefers-reduced-motion` 不動）、「開路」小印。這一波替身當場就有，所以平常看不到；「停」不畫（異聞二）。
- 收尾卡（`yiwenClose`）：收場句、朱印「完」、一路的做法（自己寫的朱字；有自己寫的幕才多一句灰字「朱字是你開的路……踩得到你的腳印」，只重放別人的路沒有這一句；「記進異聞錄」那半句異聞四加回，第 251 批）、得失一行（剛按完那一下的回話扣掉收場句、回聲與正文；重新整理後沒有就不畫）、主鈕「回江湖」。「看這一則的全圖 ›」不放（異聞三）。
- 窄機：寬 <380 頁邊 58→46px、直條 30→24px（360 寬正文一行 14 字）；<340 朱批改成頁頂橫排。
- 還沒放的：「這一段讀不通」（會加在書下面一行）與檢舉（`.yw-leaf` 頂右「⋯」），都是異聞四。
- 新按鈕走 `registerClicks`：`yw-step`、`yw-hide`、`yw-show`、`yw-help`、`yw-open`、`yw-drop`。

## 欄位與旁檔

- `PlayerState.yiwen: YiwenWalk | None`（QUIET、None 起家、第一次撞見才建；不在 `carried`，換季清掉；回到「眼前沒有」只清眼前那幾格，季內的帳留著）。
- `WorldState.yiwen_on: bool`（QUIET）、`WorldState.yiwen: YiwenWorld | None`（QUIET、None 起家、第一次要寫才建：名額 `taken`、每天的數 `free_day`／`free_today`、定論記號 `settled`〔異聞四〕）。關著的季、沒人撞見的季存檔一個鍵都不多。
- 旁檔 `<db stem>-yiwen.sqlite`（`store.py`；表 tales、nodes、walks，reports、mutes 這一批只建表）：第一次真的要寫才建（第 251 批：發掘者說了第一步、開則那一下；沒人撞見過、撞見了還沒走第一步都沒有這個檔，關著一個檔都不建）；讀的時候檔不在當成空、不建；寫過之後檔被刪，下一次寫重建表。`scripts/backup_db.py` 的 `SIDE_FILES`、`scripts/sb/harness.py::_wipe_db` 都帶它。記憶體世界（沒有資料庫）異聞不開。
- 撤回後接回（第 251 批）：旁檔不跟主交易同一筆。發掘者第一步寫進旁檔（開則＋第一幕）之後主交易撤回（存檔失敗、行程被砍），存檔的 `w.tale` 回到 0、旁檔卻留著那一則 `walking`：再按時 `actions._reattach` 照旁檔那一列（同季、同開場、發掘者是自己的鍵、沒被拿掉）接回——`w.tale` 指回去，已在旁檔的幕走重放（不重寫、不另開一則，獎勵照 `paid_scenes` 一幕一次、給重放的量），世界名額那一格有就補上 `tale`、沒有就補記一格，不重複記；之後照常走完、那一列補上 `finished_at`。那一則是別人的，照舊「有人比你先一步」。
- 內容檔包自己讀（`rules.FILES`）：`content/yiwen_openings.json`（設計 3.1 五句樣例；正式三十句等 Joy 與企劃者交）、`content/yiwen_lines.json`（3.3 的模板句，加 `gone`、`drop`、`locked`）。測試內容十八句在 `tests/data/yiwen_openings.json`（不放 `tests/content/`），`yiwen_kit.use_test_lines` 換。

## 讀別包的欄位

- 撞見的種子讀探索包的 `PlayerState.explore_seq`（只讀不寫）：照玉璽包 `actions.seal_find` 的前例寫明在這裡，不加查詢服務（總計畫「對不上的」第 11 條）。

## 假人

- 不撞見、不走、不開路、足跡不算（設計 6.6）：撞見那一格看 `PlayerState.bot` 直接回空；選單上沒有異聞的鈕，`bots.py` 不寫 `bot_pick`。`web/yiwen.js` 不寫那三個詞（`tests/bots/test_server_bots.py` 掃）。

## 測試

- 包的 `tests/`：`test_yiwen_smoke`（關著不出聲、op 關著不動、新欄位不寫鍵）、`test_yiwen_content`、`test_yiwen_store`、`test_yiwen_discover`、`test_yiwen_walk`、`test_yiwen_rename`、`test_yiwen_frames`、`test_yiwen_web`（node；第 251 批多收尾卡腳印那一句一條；第 248 批十一條：撞見卡兩種身分、每一幕、發掘者那一步不重複回聲句、朱批超長的 class、路牌排序與開滿、等待頁、進行中那一行、跳脫）。經過探索的用正式內容 season21（`yiwen_kit.season21_game`；測試內容走舊探索，撞不到異聞），只測規則的直接叫 `actions.on_explore`。
- 另外要跑的（`test_for` 挑不到）：`tests/core/test_contract_core.py`（`BUS_ORDER` 三處）、`tests/server/test_outlock.py`（`OP_OWNERS`）、`tests/core/test_same_behavior_wipe.py`、`tests/server/test_backup_db.py`、`tests/core/test_content_packs.py`、`tests/web/test_shell_web.py`、`tests/bots/test_server_bots.py`。
- 比對軌 `scripts/sb/tracks/yiwen.py`（season21：甲撞見、三幕替身走完；乙同處重走三步重放）。

## 還沒做（後三批）

- 異聞二：說書人（三段式、程式檢查、自己說）；`yiwen_step` 換成 A／B／C，請求與回應的鍵不變。
- 異聞三：岔路、問路香、尋異符。
- 異聞四：定論、兆頭、逾時收回（世界那一格 `WORLD_ORDER`）、回報、管理、異聞錄、`/api/yiwen/*` 路由。
