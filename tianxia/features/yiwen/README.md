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

## 欄位與旁檔

- `PlayerState.yiwen: YiwenWalk | None`（QUIET、None 起家、第一次撞見才建；不在 `carried`，換季清掉；回到「眼前沒有」只清眼前那幾格，季內的帳留著）。
- `WorldState.yiwen_on: bool`（QUIET）、`WorldState.yiwen: YiwenWorld | None`（QUIET、None 起家、第一次要寫才建：名額 `taken`、每天的數 `free_day`／`free_today`、定論記號 `settled`〔異聞四〕）。關著的季、沒人撞見的季存檔一個鍵都不多。
- 旁檔 `<db stem>-yiwen.sqlite`（`store.py`；表 tales、nodes、walks，reports、mutes 這一批只建表）：開關開著、有人探索到撞見那一格才建（關著一個檔都不建）；`scripts/backup_db.py` 的 `SIDE_FILES`、`scripts/sb/harness.py::_wipe_db` 都帶它。記憶體世界（沒有資料庫）異聞不開。
- 內容檔包自己讀（`rules.FILES`）：`content/yiwen_openings.json`（設計 3.1 五句樣例；正式三十句等 Joy 與企劃者交）、`content/yiwen_lines.json`（3.3 的模板句，加 `gone`、`drop`、`locked`）。測試內容十八句在 `tests/data/yiwen_openings.json`（不放 `tests/content/`），`yiwen_kit.use_test_lines` 換。

## 讀別包的欄位

- 撞見的種子讀探索包的 `PlayerState.explore_seq`（只讀不寫）：照玉璽包 `actions.seal_find` 的前例寫明在這裡，不加查詢服務（總計畫「對不上的」第 11 條）。

## 假人

- 不撞見、不走、不開路、足跡不算（設計 6.6）：撞見那一格看 `PlayerState.bot` 直接回空；選單上沒有異聞的鈕，`bots.py` 不寫 `bot_pick`。`web/yiwen.js` 不寫那三個詞（`tests/bots/test_server_bots.py` 掃）。

## 測試

- 包的 `tests/`：`test_yiwen_smoke`（關著不出聲、op 關著不動、新欄位不寫鍵）、`test_yiwen_content`、`test_yiwen_store`、`test_yiwen_discover`、`test_yiwen_walk`、`test_yiwen_rename`、`test_yiwen_frames`、`test_yiwen_web`（node）。經過探索的用正式內容 season21（`yiwen_kit.season21_game`；測試內容走舊探索，撞不到異聞），只測規則的直接叫 `actions.on_explore`。
- 另外要跑的（`test_for` 挑不到）：`tests/core/test_contract_core.py`（`BUS_ORDER` 三處）、`tests/server/test_outlock.py`（`OP_OWNERS`）、`tests/core/test_same_behavior_wipe.py`、`tests/server/test_backup_db.py`、`tests/core/test_content_packs.py`、`tests/web/test_shell_web.py`、`tests/bots/test_server_bots.py`。
- 比對軌 `scripts/sb/tracks/yiwen.py`（season21：甲撞見、三幕替身走完；乙同處重走三步重放）。

## 還沒做（後三批）

- 異聞二：說書人（三段式、程式檢查、自己說）；`yiwen_step` 換成 A／B／C，請求與回應的鍵不變。
- 異聞三：岔路、問路香、尋異符。
- 異聞四：定論、兆頭、逾時收回（世界那一格 `WORLD_ORDER`）、回報、管理、異聞錄、`/api/yiwen/*` 路由。
