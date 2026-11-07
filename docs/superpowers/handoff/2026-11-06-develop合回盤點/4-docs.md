# develop 合回主幹盤點 4：文件、規矩與 CLAUDE.md

> 11/06 唯讀盤點（工作流程 `wf_4c64148d-820`），量的時候主幹 `0176753d`（檢查者另對 `3e2271a4`）、develop `99f6a79b`。第 27、50 批之後主幹是 `f7b17ed7`，行號開工前重量。

**主幹合回 develop：文件、規矩與 CLAUDE.md 的合併地圖**

先講三件要緊的：
- 7 個撞檔的文件，每個只撞一塊，取捨都很直接（第 1 節）。
- 自動合好的部分會出矛盾的句子：主幹的「架構拆分在 `split/trunk` 上做…不合、不推 develop」，緊接著 develop 的「活的那一份在 `split/trunk`」。合回之後兩句都不對，要重寫，而且得先定「之後拆分怎麼跟 develop 同步」（第 2 節 L19）。
- 主幹自己的 CLAUDE.md 也過時：包清單少 9 包，`test_open_map` 的路徑還是舊的。

**前提（查到的數字）**
- fetch 之後：`split/trunk` 是 `0176753d`，develop 是 `99f6a79b`，兩邊共同的祖先是 `17c5199d`（錨點）。
- `git merge-tree --write-tree` 試合得到樹 `882cd7d6`，下面「試合」的行號都是這棵樹的。
- 撞檔共 31 個（交接寫 29 個，是 11/06 量的，那時的 develop 比現在舊）。其中文件 7 個：
  - `.claude/skills/tianxia-flow/SKILL.md`
  - `CLAUDE.md`
  - `docs/guide/地圖與介面.md`
  - `docs/guide/大勢人物與賽季.md`
  - `docs/guide/核心與存檔.md`
  - `docs/superpowers/feedback/試玩回饋.md`
  - `docs/superpowers/handoff/2026-10-30-主機側交接.md`
- 沒撞、自動合好的文件：`量表與教訓.md`、`beta-主機端操作.md`、`2026-10-30-開發模式-design.md`。

---

## 1. 撞檔文件：兩邊各改了什麼、怎麼取

**CLAUDE.md（試合 :59-65，一塊）**
- 撞的是 develop 第 58、59 兩行：
  - develop 改 L58「賽季由管理者開」，加了傳承那一句（`2f4ae10d` 系列）。
  - 主幹改 L59「第一季濃縮版」：設定打開的換成 `season21`、`week7`；拿掉探索三選一；操練倍數改寫成「季長 2.5 天以內倍數是 1」。
  - 取法：L58 用 develop 的，L59 用主幹的。
- 自動合好但互相矛盾的：主幹新加的「架構拆分在 split/trunk 上做」（主幹 :15），跟 develop 的 L18 句尾、L19 放在一起，三句都要重寫（見第 2 節）。
- 規矩照 tianxia-flow:120「CLAUDE.md 一律留瘦身版」。

**tianxia-flow SKILL.md（試合 :150-154，一塊）**
- 撞在「週末、14 天季、三選一」這一條。
  - 取法：用主幹的寫法，句尾接 develop 那一句「雲端掛開關的新功能 PR 附的那一份也比這三種（企劃者 2026-11-05）」。主幹本來就寫三種，develop 那句只剩點出「雲端」。
- 自動合好、兩邊都要留的：
  - develop 11/05 的規矩（`f7dfe8cb`、`b0538bde`）：分支表 main 那一列、「誰合進 develop、main」、雲端那一條（:27）、上 main（:28）、「Joy 那一側自己合 main」與「開了 PR 之後再推」（:126-127）。
  - 主幹的 :58「拆分主幹不照下面這一條」、:123「不帶設定各載一次」。
- 合完還是錯的：
  - :27 develop 自己的「批次表『搬包中』的那幾包不改」，跟 develop CLAUDE.md L19「不用避開」互相打架。主幹 tianxia-dev:23 也寫「搬包中不改」。
  - :28「追進拆分主幹（split/trunk）」、:58 主幹那一條：要看合回之後拆分還在不在 `split/trunk`。

**docs/guide/地圖與介面.md（試合 :22-35）**
- develop：在「江湖頁」那一條前面插了「介面重整」一整段（PR #173，8 個子項，develop 在這個檔只有加行）。
- 主幹：改寫「江湖頁」那一條（第 13 批拿掉練功格與三選一展開）。
- 取法：develop 那一整段放前面，接主幹的「江湖頁」。
- develop 那段裡的 `tianxia/talk_log.py`，等它的位置定了再改路徑。

**docs/guide/大勢人物與賽季.md（試合 :160-200）**
- 主幹：改了宴客「還沒接掛鉤的」那一行（`letters.py` 邀宴，改成 `figure_life.py` 設宴與書信邀宴問的 `feast_invites`），後面新加「一條線」「簽到」「大勢人物的行動」三節。
- develop：在檔尾加了「傳承」「招募同伴」兩節。
- 取法：主幹那一行與三節在前，develop 兩節接在後面。
- develop 在 :16-17 加的 `place_state.py`、`rumor_view.gazette_lines` 兩行，自動合進「## 模組」了。
- 合完要改的：
  - 傳承那節的 `epiphany.roll`：現在在 `features/sense/epiphany.py`。
  - `storyline.roll_start`：現在在 `story_base`（稽核第 6 節）。
  - `web/app.js` 的 `legacyHtml`：稽核 3.10 要切到 `web/legacy.js`。
  - 招募的 `content/hirelings.json`：稽核 3.8 要改成 `hire.json`。

**docs/guide/核心與存檔.md（試合 :36-41）**
- 主幹：改了「新手引導重做」（老周七步，第 13、14 批之後）。
- develop：在它後面加了「補新手教學的十一條碰到才說」。
- 取法：兩行都留，主幹的在前。
- develop 的「難度等級…」「五項屬性」兩小節自動合在「## 事件檢定」底下（試合 :93-108）。合完要補：
  - 試合 :108「還沒做（第 2～4 批）」：稽核 3.6 說跟程式相反，要改。
  - 試合 :58 的掛鉤清單：加上 `prep`（develop 的 `core/features.py` 開的）。
  - 試合 :52 的 FEATURES 清單：加上 legacy、hire。
  - 如果 attrset 進核心 `MODULES`，「十七個」那個數字跟著改。

**試玩回饋.md（試合 :529-533）**
- 兩邊都在表尾加了一列：主幹 FB-9310、develop FB-9430。
- 兩列都留，照編號排（tianxia-flow:119）。develop 改 FB-9110 那一列（:514）已經自動合好。

**主機側交接（試合 :7-13）**
- 主幹把整份重寫成 148 行，舊的流水帳搬到 `2026-11-05-主機側交接-封存.md`。
- develop 只加了兩行「這一份停在錨點…活的在 split/trunk」（`54d8f7d5`）。
- 取法：整份用主幹的，develop 那兩行丟掉。
- 合完要改：
  - 第一節：主幹、現在在跑、下一步。
  - 第六節的分支表：寫的是 main `a208ea99`、develop `6907ae7d`、split/trunk `e3cd42ff`，都過時了。
  - 第二節 11/04「不合、不推 develop」那一列。
  - 第十節「改之前 checkout origin/split/trunk」。

**自動合好、但合完要再改的文件**
- 手冊（開發模式-design.md）：
  - develop 的 11/05 改動（第五節、第六節 Joy 那一列、十一節第 2 題、G19、3.3 `prep`、「11/05 企劃者答」）都合進來了，主幹的各批認定也在。
  - G19（主幹 :808）兩邊都還寫「第 13、14 批落地以前…照舊比四種設定」，要照主幹 tianxia-flow 的寫法改。
  - develop 那行「3.3 多開一個掛鉤 `prep`（PM 同意）」：稽核 3.7、4.6 查不到這份同意；11/05 的規矩又是「沒有紀錄不准寫 PM 同意」。要補上真正點頭的人，或標待補。
  - :172「拆分主幹」、:781「正在搬的那一包不改」：要看之後怎麼拆。
- `beta-主機端操作.md`：develop 加的往來紀錄小檔備份兩行，和主幹的 23 行都留。
- `量表與教訓.md`：develop :157 的「量平衡一律照這份清單」，和主幹的都留。
- 只有 develop 有、合完就過時的：工作包 `packages/2026-11-04-屬性等級武學/README.md` :47、:51、:56、:141（「develop 上的程式不會被搬」「PM 在 split/trunk 上拆」）。

---

## 2. develop 的 CLAUDE.md 要改的清單（原文行號是 origin/develop:CLAUDE.md）

先查證的開關：
- 主幹的 `tianxia/models.py`：`Config` 沒有 `explore_modes`，也沒有 `open_map`。
- `SortieRules`、`TerritoryRules`、`ConquestRules` 都沒有 `enabled`；還留著的只有 `PushResistance.enabled`、`Training.enabled`。
- 主幹的 `content/config.json`：`sortie`、`territory` 底下沒有 `enabled`。
- 主幹沒有 `profiles/weekend.json`，develop 還有。develop 的 `models.py:4198` 也還有 `explore_modes`。

**工作目錄與分支**
- **L14**　原文「現況看交接〔`docs/superpowers/handoff/` 最新那一份〕第一節」
  → 改成主幹 :14 的寫法：「交接〔`docs/superpowers/handoff/2026-10-30-主機側交接.md`〕第六節」。交接資料夾現在有 11/05 的稽核與封存，「最新那一份」會指錯。
- **主幹 :15（develop 沒有這一行）**　「架構拆分在 split/trunk 上做…不合、不推 develop…」
  → 改寫成：錨點 tag `split-anchor-20261104`；企劃者 11/06「已經拆的都可以回develop了」；拆到第 N 批的主幹 `<SHA>` 已在 `<合併 SHA>` 合回 develop；從這一筆起 develop 上的總表、交接、手冊是活的那一份；剩下的批之後怎麼跟 develop 同步，合回之後再定。SHA 合的時候填。
- **L15**　照留；「路線與進度看總表」改成「路線看總表、進度看交接第一、三節」。
- **L16-18**　**照留原文**（企劃者 11/05 的話：PR 範本、退版五件、誰點頭、`same_behavior`、Joy 本人可直推）。
  - 只有 L18 句尾「PM 照舊把 main 合回 develop、追進 `split/trunk`」：拆分還在主幹就留，直接在 develop 拆就刪「追進 split/trunk」。待定。
- **L19**　原文「不用避開搬包中的包…develop 上看到的『搬包中』、總表、交接停在錨點那一刻，活的那一份在 split/trunk」
  - 合回之後這句是錯的。
  - 改成：「還沒搬的批看交接第三節，正在搬的看第一節『現在在跑』」，再加二選一（待企劃者定）：
    - (甲) 照舊不用避開，PM 合的時候照新位置搬；
    - (乙) 照手冊十五節「改哪裡」：正在搬的那一包不改，非改不可推自己的分支、告訴 PM。
  - 「搬包中」那張表（`2026-10-31-主動搬六包-批次.md`:7-10）在主幹是空的，不要再指到它。
  - 同一件事要一起改：tianxia-flow :27、tianxia-dev :23。
- **L20**　原文照留，後面補：
  - 舊名 `tianxia/<模組>.py` 檔裡只有 `sys.modules[__name__] = …` 的是別名（主幹 59 個，develop 18 個），要改它指到的包裡那一份。
  - 全新的玩法（新的選項前綴、新的開關、新的畫面）一律用 `scripts/new_feature.py` 生一包，不加進 `engine.py`（手冊 :782）。
  - 包只准 import 三樣：核心（`tianxia/core/__init__.py` 的 `MODULES` 與 `tianxia/core/`）、共用規則層（`tianxia/core/registry.py` 的 `SHARED`）、自己這一包；不 import 別包（`tests/core/test_feature_boundaries.py` 守）。
  - 新包的畫面寫在 `web/<包>.js`、`.css`（G9，稽核 3.10）。
  - 新包的內容檔叫 `content/<包>.json`，驗證寫在包的 `check_content`（G8，稽核 3.8）。
  - 可選、企劃者沒答過：「一筆提交一件事，訊息寫改了 Game 的哪幾個方法」（稽核 4.8）。

**功能區塊**
- **L31「已經搬成功能包的」**
  - 換成合回那一刻的全名單：主幹 :32 的 20 包，加上主幹已經成包、但 CLAUDE.md 沒列的 9 包：陣營 `faction`、裝備 `gear`、輿圖 `map`、玩家互動 `peers`、閉關 `seclusion`、鐵匠鋪 `smithy`、體力玩法 `stamina_plays`、地盤 `territory_acts`、移動 `travel`。
  - 再加 develop 的傳承 `legacy`、招募 `hire`；第 27 批合了加玉璽 `seal`；develop 新的 9 個 `Game` 方法拆進去的包也要寫上。
  - 「2026-11-04 照 develop」改成「照合回那一筆」。
  - 「正在搬的看批次表『搬包中』」改成「看交接第一節」。
  - 推測：這份檔約 38,000 字，已經超過「上限約 1 萬 token」。建議把這張長名單移到〈核心與存檔〉的「核心、功能包…」那一節，這裡留一句指過去。
- **L36 核心與存檔**
  - 標出別名：`annals`、`biography` 是列傳包 zhuan 的（記一筆用 `core/annal_base`）；`guide`、`newbie`、`opening` 是引導包的；`storyline` 是一條線包的（底座在 `story_base`）。
  - `prologue`、`playlog` 在共用層。
  - 補：`step`（核心 `MODULES`）；`tianxia/core/` 的 annal_base、presence、omen_base、convoy_base、feast_base、smith_base、event_check、duel_base、arena_ranks、option、swap、services、features、registry。
  - develop 的 `attrset`：develop 把它放進核心 `MODULES`，主幹沒有這個檔；算不算核心，稽核第 6 節列為 PM 要定。
- **L37 行動與地盤**
  - 「管什麼」的「探索三選一」改成「探索」（主幹 :38）。
  - 拿掉 `explore_modes`、`gather_llm`（主幹沒有這兩個檔）。
  - `sortie` 是出陣包的別名；`ambush`、`works` 是 stamina_plays 的別名；`territory`、`training`、`clinic`、`conquest` 在共用層。
  - 補包：explore（`outing`、`explore_one` 是別名）、travel、seclusion、socialize、territory_acts（`conquest_day`、`xingshi` 是別名）。
  - 第 4 欄「正式內容三個開關都關著」跟 config.json 對不上：config.json 是 `ambush.enabled: true`、`stockpile.enabled: false`。推測後來打開過設伏；導覽 行動與地盤.md:131 一起改。
- **L38 戰鬥**　用主幹 :39，補 `sortie_duel` 是出陣包的別名。
- **L39 武學與成長**　用主幹 :40（`pose` 在共用層；`create`、`cultivation`、`chuangong`、`ascend`、`sensing`、`epiphany`、`glyph`、`insight_llm` 是別名）。
  - develop 的 `_allocate_v2`、`pick_growth` 放哪：推測歸修練包，因為稽核第 6 節把「配點兩個」歸 cultivation。
- **L40 裝備與店面**　`smithing` 是 smithy 的別名、`signature_arms` 是 gear 的別名、`tavern`（連 `tavern_ask`）是酒肆包的別名；補包 outlets、gear（馬市）。
- **L41 大勢人物與賽季**
  - 用主幹 :42，再補別名：`checkin`→簽到包、`defection`→faction、`foreshadow`、`opportunities`、`rank_actions`→military、`figure_aid`、`yuedan`→figure_acts。
  - `figures`、`figure_life`、`plans`、`orders`、`ranks`、`chapters`、`timetable`、`front_lines`、`relations`、`roster` 在共用層。
  - develop 的：`place_state`（develop 登記進了 `SHARED`）、hire 與 legacy 兩包。
- **L42 散人與玩家互動**　`raid` 是 peers 的別名；補 peers 包（`social`、`invites`、`mingtie`、`mingtie_card`、`spar`、`discuss` 是別名）；`ranger` 在共用層；`bounties` 還在原位（第 45 批）。
- **L43 玉璽碎片**　第 27 批合了，照它實際搬的寫（PM 認定：核心讀的抽到 `core/seal_base.py`）。
- **L44 商城**　兩邊都沒有 `tianxia/rename.py`，它在 `features/mall/rename.py`；`mall` 是別名；`wallet` 是核心。「資料庫第 6 版」改成第 9 版（手冊 :788）。
- **L45 地圖與介面**
  - `mapview`、`mapart`（連 `mapdata`、`worldgeo`）是輿圖包 map 的別名。
  - `weekcard` 是核心 `MODULES`（第 36 批）。
  - `atlas` 照第 50 批的結果寫。
  - develop 的 `talk_log` 只有 server.py 用，位置待定。
- **L46 模型與假人**　`ollama_client`、`power_save`、`zh`、`event_llm` 在共用層。

**原則**
- **L51** → 用主幹 :52（「探索三選一第 13 批拿掉了…」）。
- **L58** → 用 develop 的版本（傳承那一句，見第 1 節）。照「對方新加的搬進 docs/guide」，也可以縮成一句指到〈大勢人物與賽季〉的「傳承」。
- **L59** → 用主幹 :60。已查證：`season21`、`week7` 兩份設定都是 `season_one: true`。
- **L66、L67**（建議，推測要改）：補一句「五項屬性的季（`attrset.on`，`Config.attributes.v2` 預設關）另見〈核心與存檔〉『五項屬性』：配比一季挑一次、博聞拔掉、con→lead」。

**指令**
- **L76** → 用主幹 :77（不帶設定套 season21；`weekend` 起不來）。合的時候 develop 的 `profiles/weekend.json` 跟著主幹拿掉。
- **L78** 照留（test_for 預設跟 origin/develop 比）。
- 主幹 :81「拆分主幹 split/trunk…同一件事只驗一次」：拆分還在主幹就留；直接在 develop 拆，就改成那一條線的規矩。待定。
- **L82** 拿掉 `mall/`（兩邊都沒有 `tests/mall/`），補一句「已成包的測試在包的 `tests/` 裡」。
- **L84** → 用主幹 :86（`old_explore`、`classic_rules`，主幹 conftest :91、:99）。
- **L85**　原文 `tests/map/test_open_map.py` → `tianxia/features/map/tests/test_open_map.py`（主幹 :87 也還是舊路徑）。
- **L86** 照留（`Config.conquest/sortie/territory/fortify` 的開關拿掉了，跟 models 對得上）。
- **L87** → 用主幹 :89（舊規則開關只剩盡頭阻力，`tests/server/test_push_resistance.py:117`）。

---

## 3. docs/guide：兩邊都改過的段落怎麼合

- develop 只改了 4 份：地圖與介面、大勢人物與賽季、核心與存檔、量表與教訓。前三份各撞一塊，取法見第 1 節；量表與教訓自動合好，兩邊都留。
- 合的原則照 tianxia-flow:24：共用登記檔（含 `docs/guide`）每條線把自己加的集中成一段、前面寫 `# <包>`。所以 develop 新的「傳承」「招募同伴」「介面重整」都整段留，只改裡面的路徑。
- 稽核 3.6 列的、develop 沒跟上的導覽，合的時候一起補：
  - 核心與存檔（試合 :108）「還沒做（第 2～4 批）」
  - 戰鬥.md:149「丟了只是那幾場沒有戰記」，與 :134
  - 商城.md:104 畫坊的流程
  - #157 的對打照對手重算、統御、魅力，導覽裡完全沒寫
- 主幹自己的舊路徑（現在是別名，沒標「舊名」）：
  - 大勢人物與賽季.md:8 `figure_aid`、:21 `checkin`
  - 行動與地盤.md:10 `xingshi`、:18-19 `ambush`、`works`
  - 戰鬥.md:16 `sortie_duel`、:22 `escorts`
  - 核心與存檔.md:35 `guide`
  - 交接 :19 記的「〈散人與玩家互動〉還寫著 `Game.spar_invite` 等名字，拆完一起改」

---

## 4. PR 範本與技能檔

**`.github/pull_request_template.md`（只有 develop 有，合過來就在）**：要改，但改得不多。
- 「改了哪一包」的說明補兩句：
  - 舊名是別名的，寫包名；全新的玩法用 `new_feature.py` 生一包。
  - 改了 `SHARED`、核心 `MODULES`、`core/*_base.py` 也列出來，寫進「誰點頭」那一格。
- 「關著不變的證明」：主幹 `same_behavior.py:49` 的預設就是 `season21`、`week7`、`test` 三種，可以寫「不帶 `--profiles` 就是三種」；照留也沒錯。
- 如果第 2 節 L19 選了 (乙)，補一格「動到還沒搬完的批的那幾包嗎（交接第三節）」。

**tianxia-flow**：除了解撞，:27、:28、:58 要跟 CLAUDE.md L18、L19 和主幹 :81 同一個說法。

**tianxia-dev、tianxia-qa**：develop 沒改過，自動用主幹的版本。只有 tianxia-dev:23「搬包中不改」要跟 L19 一起定。

**tianxia-map-remake**：有 1 處寫舊的 `tianxia/map*.py` 路徑，等第 50 批合了看要不要改。

**另一份 clone**：推上 develop 之後，`C:\Ray\專案\ai遊戲` 那份的 CLAUDE.md 與技能還是舊的，照手冊 G17 在它乾淨時 `pull --ff-only`。

**這次要 PM 或企劃者先定、文件才寫得下去的**：
1. 合回之後拆分還在不在 `split/trunk`（影響 CLAUDE.md L18 句尾、主幹 :15、:81，tianxia-flow :28、:58，手冊 :172）。
2. 「搬包中」的規矩選 (甲) 還是 (乙)（影響 L19、tianxia-flow:27、tianxia-dev:23）。
3. `attrset`、`place_state`、`talk_log`、`growth:` 歸哪裡，`prep` 掛鉤留不留（稽核第 6 節）。
4. `prep` 那一條真正點頭的是誰。
