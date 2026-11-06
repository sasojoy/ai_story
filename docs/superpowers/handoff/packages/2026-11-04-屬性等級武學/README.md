# 工作包：屬性、等級、武學（新功能）

> **2026-11-04 暫停，先不要開工**：Joy 改了方向，見 `docs/superpowers/specs/2026-11-04-屬性與跨季-架構方向v2.md`。這份工作包的第 1 批（亂數配比、洗點、每點 0.2%、轉接值）跟 v2 的骨架相衝；新的計畫照 v2 第十節的階段另寫。

《天下大勢》要把四屬性、等級等差、武學品級重做一輪。企劃者把這一塊交給你開發，PM 專心做架構拆分。

**你要做的**：照設計與計畫把四批做完。每一批開關關著、驗過，就開 PR 合進 `develop`。上線是換季的事，由企劃者決定。

整理時間：2026-11-04（`develop` 當時的狀態）。

## 現況

| 項目 | 狀態 |
|---|---|
| 設計 | **定案**（企劃者 2026-11-01～11-03 一題一題談定） |
| 第 1 批計畫 | **寫好了**，一步一步可以照做（759 行） |
| 第 2～4 批計畫 | 只有粗分（第 1 批計畫第六節），要你寫 |
| 程式 | **一行都還沒動** |
| 內容 | 季初對話、洗點商品、傳奇事件、中品武學、人物等級都還沒有，要企劃者或 Joy 填（見「要別人定的」） |

## 四批

| 批 | 範圍 |
|---|---|
| 1 屬性尺度與來源 | 存檔新欄位、季初對話（新包 `features/aptitude`）、洗點商品、傳奇成長、事件檢定值 |
| 2 四項分工進戰鬥 | `player_boost`、`tactics.Ctx` 七個新數、`_apply_toll`、練成折扣、對手身法 |
| 3 等差與人物等級 | 傷害係數、人物表欄位、世界進程與活動升級、隊伍 `level` |
| 4 武學 | 中品、槽數、發動率上限、相剋雙向、兼容並蓄、真意機率 |

## 要讀的（照這個順序）

都在 `develop` 上；壓縮檔裡也附了一份（`文件/`）。

1. `docs/superpowers/handoff/2026-11-03-屬性等級武學-設計交接.md`：定案一覽與企劃者原話，先看這份。
2. `docs/superpowers/specs/2026-11-01-四屬性與等差-方向定案.md`：**定案在這裡**，第八節是總表。
3. `docs/superpowers/plans/2026-11-03-屬性等級武學-第1批.md`：第 1 批怎麼做。
4. `docs/superpowers/specs/2026-11-01-屬性等級武學連動-盤點.md`：照程式現況抄的連動，改程式前看。
5. 要查才看：`2026-11-01-武學特性全表.md`、`2026-11-01-屬性進戰鬥與等級等差-討論稿.md`（大半被定案取代）。

專案規矩：`CLAUDE.md`、開發規範手冊 `docs/superpowers/specs/2026-10-30-開發模式-design.md`（3.1～3.11、第十五節）、技能 `.claude/skills/tianxia-dev/SKILL.md`、`tianxia-flow/SKILL.md`。

## 企劃者 11/04 改了什麼（跟計畫不同時照這裡）

計畫是 11/03 寫的，有幾處過時了：

1. **開工時機改了**：計畫第七節寫「拆包全部做完再開」，**作廢，現在就開工**。同一節另外兩條照舊：舊存檔不換算；做完驗過、開關關著先合進 `develop`。
2. **計畫第二節「跟拆包撞到哪裡」不用管了**：拆分搬到別條分支（下一節），`develop` 上的程式不會被搬。Task 0 不用查那幾條分支，也不用看「搬包中」。第 7、8、12、15、16、17、22 批與鐵匠鋪都已經在 `develop` 裡。

## 跟拆分的關係

**你在 `develop` 上做，拆分不會干擾你。** PM 的拆分從錨點 tag `split-anchor-20261104` 開到 `split/trunk` 上做，全面分拆完才把 `develop` 的提交一筆一筆追過去。所以 `develop` 上的 `engine.py` 不會被搬，計畫寫的 `Game.allocate_stat` 這些都還在原位。

**為了之後追得動，請照這幾條：**

- **新邏輯放核心或你的新包**：`team.py`、`state.py`、`models.py`、`rules.py`、`world_state.py` 是核心，季初對話放 `features/aptitude`，用 `scripts/new_feature.py` 開包。
- **`engine.py` 裡只改必要的行**，不要順手整理、不要搬方法。那些方法在 `split/trunk` 上已經或將要搬進包，你改的每一行之後都要人工搬過去。
- **一筆 commit 做一件事**，訊息寫清楚改了哪個方法。之後是一筆一筆追的。
- **已經成包的改包裡的檔**（`features/mall` 等），`Game` 上的一行委派不加邏輯。
- **批要小、要快合**：開關關著的東西一批一批合。計畫第 1 批有 14 個 Task，可以再切幾次 PR。

## 不能破的

- **開關關著一個位元組都不變**：`aptitude.enabled` 照開季蓋章。每批都要用 `scripts/same_behavior.py compare`（所有軌、五種設定）對 `develop` 證明。這是合進 `develop` 的條件。
- **數值全部由規則引擎決定**，模型只寫文字。
- **不升資料庫結構**（第 9 版）。計畫第三節寫了新欄位怎麼放。
- **舊存檔不換算**：這是換季才上的改動。
- **任何畫面、輸出都不能透露誰是假人**。`web/` 底下的檔連註解都不准寫假人、機器人、bot。
- **新寫的字**標 `# 待 joy 潤`（js 寫 `// 待 joy 潤`），先做、之後再潤。名字用原創的，不用金庸等作品的專有名詞。
- **不碰** `main`、線上資料庫、`https://tianxiadashi.com`。模型網址指到 `127.0.0.1:9`，測試不打真的模型。
- **部下不碰**：部下乙（部下＝兵）還沒談完；NPC 強弱由等級算（定案 4.3 乙）也是另外談。

## 環境

```bash
git clone https://github.com/sasojoy/ai_story.git && cd ai_story
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt    # 別的系統是 .venv/bin/python
git switch -c feature/aptitude origin/develop                      # 雲端 session 只能推 claude/<名字> 的話就用那個
```

- 主機用的版本：Python 3.14.3、Node 22（網頁測試要 node）。
- Windows 工作樹是 CRLF、git 裡存 LF，用腳本改檔要先轉 `\n` 再比對、寫回時轉回去。
- 測試一律 `-n 4`，`TIANXIA_DB` 指到 repo 外的暫存檔。
- 開發中只跑相關的：`python scripts/test_for.py --base origin/develop`。合併前跑不含 slow 的整套：`python -m pytest -q -n 4`。
- 量表與模擬腳本看 `docs/guide/量表與教訓.md`。定案第五節列了進 Config 之前要量的表。

前後對照：

```bash
mkdir ../base && git archive origin/develop | tar -x -C ../base
python scripts/same_behavior.py compare --base ../base --head . --tmp ../sb --jobs 4        # 最後一行要是「全部一樣」，約 15 分鐘
python scripts/same_behavior.py explore-compare --base ../base --head . --tmp ../sb2
```

## 怎麼交付

每一批（或切得更小的一段）：

1. 合最新的 `develop`，衝突兩邊都留。
2. 閘門：四種設定（season21、week7、weekend、不帶）各載一次內容、各起一次伺服器，GET / 200；不含 slow 的整套；相關的 slow；same_behavior 全部一樣。
3. 開 PR 到 `develop`，由 Joy 在 GitHub 合。

```markdown
## 改了什麼
屬性等級武學第 N 批（Task x～y）：……。開關 `aptitude.enabled` 關著。

## 測過什麼（對 <SHA>）
- 四種設定載內容、起伺服器：GET / 都是 200
- 不含 slow 的整套：N passed、N skipped
- 相關的 slow：N passed（列檔）
- same_behavior 對 develop <SHA>：所有軌、五種設定、整段與半舊半新、假人，全部一樣

## 退版風險
（逐條寫。第 1 批計畫 3.5 有五條範本）

## 給企劃者
還沒定的題目、等人填的內容
```

**四批做完不等於上線**：企劃者說可以，才在休季打開開關、換程式、開下一季。

## 要別人定的

**不擋開工**，程式先照計畫的預設做，測試用測試裡建的內容。這些定了才寫進 `content/`、才能打開開關：

1. **季初對話的字**：幾題、答案、各偏哪一項、誰在問；開局三選一要併進來還是照舊。
2. **洗點商品**：名字（暫名「洗髓帖」）、價錢、限購、什麼時候上架。
3. **傳奇事件**：哪幾則、各給哪一項、每級多長多少。
4. 第 3、4 批：中品武學的內容（現在 0 門）、人物表的起始與季末等級、隊伍與頭目的 `level`。

畫面的決定（狀態列屬性那一塊、對話卡、用帖那一格）給企劃者 2～3 個對比圖挑，不要用文字問。

**怎麼問**：開一個 draft PR 到 `develop`，把問題寫在說明的「給企劃者」，同時告訴把這包交給你的人。

## 詞彙

| 詞 | 意思 |
|---|---|
| 企劃者 | 這個專案的負責人，定玩法與規矩。 |
| Joy | 在 GitHub 審與合 PR 的人。 |
| PM | 企劃者的專案管理 session，正在 `split/trunk` 上做架構拆分。 |
| 批（拆分的） | 拆包的一個工作單位，路線在 `docs/superpowers/plans/2026-10-31-全部拆包-總表.md`。跟這裡的「第 1～4 批」是兩回事。 |
| 包 | `tianxia/features/<包>/`，一個功能一包。 |
| same_behavior | `scripts/same_behavior.py`，同一串操作在新舊程式各跑一次，逐位元組比。 |
