export const meta = {
  name: 'split-batch',
  description: 'One split batch from the full-split table: move a group of Game methods and modules into a feature package (or a core step) with behaviour proven byte-identical; review lenses, one fix round, then a two-server byte check (or full browser QA when web/ changes)',
  phases: [
    { title: 'Build', detail: 'plan, Task 1 proof scenarios, core side, move, tests, proof' },
    { title: 'Review', detail: 'proof honesty; boundary and handbook; regressions' },
    { title: 'Fix', detail: 'one round on findings' },
    { title: 'Check', detail: 'two real servers byte check, or real-browser QA' },
  ],
}

const ARGS = {"n": 23, "title": "修練——改練、練成、意境裝卸、熔煉、絕學與破境丹、破境卡三段式、傳功、配點（`cultivation`、`chuangong`、`ascend` 進新包 `arts`）", "pkg": "arts", "feature": "feature/arts", "dev": "dev/arts-1", "plan": "docs/superpowers/plans/2026-11-01-修練包-第1批.md", "host": "arts1", "reviewers": 3, "body": "- **接手（PM 11/04 清晨）**：上一個子代理做到 Task 1 一半撞到額度停下，什麼都還沒提交。**不要照下面「分支」那一句從 feature 開新的**：\n  - `git switch -c dev/arts-1 origin/dev/arts-1b`（`751ad824`，PM 收的 WIP 一筆：計畫 `2026-11-01-修練包-第1批.md` 寫好了〔230 行〕、same_behavior 的 arts 一軌寫到一半〔+567 行，還沒跑過〕）。本地若已有 `dev/arts-1` 就用 `dev/arts-1-work`。\n  - 先讀計畫和 `git show 751ad824 --stat`，看 arts 一軌寫到哪，接著寫完、在 base 上跑兩次證明穩、改一個字抓得到，再提交（WIP 那一筆留著）。\n  - 推到 **`dev/arts-1`**（`git push origin HEAD:dev/arts-1`；遠端還沒有這條）。`dev/arts-1b` 留著不動。上一位的暫存在 `C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray--------\\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\\scratchpad\\b23\\`，有用就用。\n  - 接著做 Task 2～5。Task 5 的 base 照舊用 `85c3f682`。\n- 範圍照總表第 3.3 節乙表第 23 列（約 32 個方法、294 行）：改練、練成、意境裝卸、熔煉（含批量）、絕學與破境丹、破境卡三段式、傳功、配點；`cultivation`、`chuangong`、`ascend` 進新包 `tianxia/features/arts/`（舊名留別名）；`learn:` 前綴。\n- **先做**：裝飾器 `_not_while_preparing`（22 個方法掛著）搬進核心。\n- 32 個方法裡約 31 個要留委派（測試、server、別包在叫）；驗收看「改 engine 挑到幾條」。\n- 武學、意境、合成的**規則模組**（martial_arts、arts、insight_fx、fusion……）照總表歸共用規則層，不搬；煉製與自創（`create`）是第 44 批、等鐵匠鋪那條線，不搬。\n- Task 1 的情境：改練、練成一成（成與受傷）、裝一個意境進槽再拆、熔煉一門與批量熔煉、破境丹衝絕學（成與敗）、破境卡三段式（模型擋著走退回）、傳功給同伴與部下、配一點屬性；半舊半新切在破境卡送出、還沒寫回的時候。\n- 第 15 批已合：武學、裝備的規則模組在 `registry.SHARED`，包直接 import 不算過渡。\n- develop 的 `Game._preparing` 在 PR #145（`01f90863`）多了一層 `with atlas.route_memo(), renown.needs_memo()`：搬 `_not_while_preparing` 時照現行程式量，不要照調查的行號。\n- **same_behavior 新開的軌一律用原創名字**（PM 11/04，第 22 批認定第 3 條）：不要用金庸、古龍等作品的人物名。", "check_steps": "註冊一個帳號、管理者開季；練成一成、裝卸意境、熔煉一門、批量熔煉兩門、配一點、用破境丹衝一次、傳功一次（給它同伴或部下）", "base": "85c3f682", "ports": {"dev": 8159, "rev": 8160, "fix": 8160, "head": 8161, "base": 8162}, "fb": "FB-9270～FB-9279", "parallel": "第 24 批（新包 `sense`，`dev/sense-1`）可能同時有人在做；第 12 批（新包 `bout`）由 PM 合。開工前 fetch develop，看哪些批已經合了。共用登記檔各寫各的那一段。", "after15": true}

// 工作包 docs/superpowers/handoff/packages/2026-11-04-第23-24批/第23批-工作單.md：開發已經做完（wf_9b08e317-075 的結果照抄），不重跑。
// 不換包名的話把 RENAME 改成 false。
const RENAME = true
const DEV_RESULT = {"branch": "dev/arts-1", "head": "674ee394f4882ece1b00972ec58c03e4591040e7", "stopped": "", "commits": ["751ad824 WIP split batch 23 Task 1（PM 收的上一位的 WIP，照留）", "2c3c88c3 Task 1：same_behavior 的 arts 一軌寫完、在 base 上證明穩", "c504d892 Task 2：核心那一側（籌備中的裝飾器進核心、修練包接走 learn:）", "a2365300 Task 3：修練頁搬進 features/arts（三個模組＋33 個委派）", "2bbcba01 Task 4：整檔屬於這一包的 2 個測試檔搬進包、README", "674ee394 Task 5：證明與驗收（arts 一軌補兩段、計畫第五節、導覽）"], "same_behavior": "base 85c3f682（git archive 解出來的）對 head 工作樹，--jobs 4：\n- 所有軌（--help 列的 8 軌：sortie、duel、battle、muster、tavern、events、train、arts）× 五種設定（none、weekend、season21、week7、test）× 整段與「base 前半＋head 後半」，加四軌的假人（出陣 2 種、約戰 2、出陣三 3、修練 3）：全部逐位元組一樣，922 秒。\n- explore-compare（五種 × 整段與半舊半新，加探索假人 2 種）：全部一樣，268 秒。\n- Task 5 在 arts 一軌補了兩段之後，arts 一軌重比一次（五種＋假人）：一樣。雜湊是 none f9380213、weekend 0f66d664、season21 765c703f、week7 d58258e7、test d1352747。\n- 半舊半新的切點：寒江服丹衝開、破境卡寫好、卡上那一句還沒寫回的那一刻（week7 前半 126 步）。同一刻還有三種寫到一半的狀態：舊存檔等著定名、境界卡沒配完、序章新人停在裝意境那一步。後半第一件事是新程式走破境卡三段式（模型擋著，走套句）。\n- 假人：整季機器人加 BotRunner 四個。假人程式照 run_bots 帶一個叫不動的 client，所以絕學定名也走到 A、B、C 三段（named 2、2、6 次）。\n- 比對本身穩不穩：base 上 selftest --tracks arts 跑了兩次（Task 5 改完情境之後又兩次）。每一種跑兩次一樣、前半＋後半＝整段、改一個字抓得到，兩次的雜湊也一樣。\n- 單點突變 20 種（腳本 scratchpad b23/mutants.py，不進版控）：第一次抓到 16 種。補兩段情境之後抓到 18 種：雲岫打完幾場再配點，配點那一句才寫「此刻全隊」；墨池手上要真的有追風步。剩下 2 種在 API 上看不出差別，是等價突變：被拒的改練只回一句，標記取第幾句都一樣；forged 只在 op=forge 時才讀。", "acceptance": "- 包的測試單獨跑（-n 4，含 slow）：20 條，約 9 秒。\n- 改 features/arts 任一檔（test_for --count，不含／含 slow）：actions.py、cultivation.py、__init__.py 都挑到 140／141 條，≤ 300。\n- 改 engine.py（臨時改方法最後一行再還原；base→head，不含／含 slow）：\n  - `_tavern_price` 164/169 → 169/174\n  - `chuangong` 130/131 → 240/243\n  - `_seize` 204/205 → 209/210\n  - `status_data` 1605/1610 → 1611/1616\n  - 變多的四個：`practice` 654/684 → 2995/3127、`cultivate` 288/289 → 1696/1744、`allocate_stat` 115/126 → 1391/1421、`art_rows` 473/490 → 1830/1857。原因是第 11 批定的規矩：一行委派還要並上「內文寫到那個方法名」的測試檔，而這四個是常見字。\n- 過渡處數：包 → 舊模組 57 → 62（修練 6 處；決戰包少 1）；舊模組 → 包 66 → 77。\n- 委派 126 → 159（修練 33：動作 22、唯讀資料 11）。\n- 直連 59 → 68：GAME_DIRECT 7 不變（這一批 0 個）；GAME_DELEGATE_CALLERS 52 → 61，多的 9 對是 `_drop_stale_references`、`sync`、`_seize`、`status_data` 各 1 對，`_graduate_pass` 5 對。\n- GAME_IMPORTS 19 → 21；共用規則層 60 個不變。\n- engine.py 14,018 → 13,812 行（−206）。", "tests": "- Task 2：test_for --base origin/feature/arts（核心測試＋煙霧＋契約與邊界），2006＋43 passed。\n- Task 3：同一個 test_for，5241 passed、1 failed，另外連 slow 的那批 123 passed。紅的是 tests/seal/test_seal_acts.py 掃 tianxia/*.py 找頒詔呼叫端的那一條（路徑變了），改成連包一起掃之後，那兩個檔 96 passed。\n- Task 4：包的 tests 連 slow 20 passed（約 9 秒）；另外跑 test_seal_revamp、test_cultivation、test_practice_hardening，113 passed。\n- Task 5：\n  - test_for --base origin/feature/arts 再跑一次：5207＋204 passed。\n  - 相關的 slow，-m \"slow or not slow\" -n 4：1908 passed。範圍是叫到這一批方法、模組、learn:、/api/menxia 而且有 slow 的 13 個檔，加 README 列的混合檔、test_figures、test_hints、修練與決戰兩包、契約與邊界。\n- 沒跑整套；沒開伺服器。", "learned": ["包名 arts 跟共用規則層的 tianxia/arts.py 同名，會讓 test_feature_boundaries 的「共用規則層的模組不是包」那條斷言紅；new_feature.py 本來就不准這種撞名。包裡要拿共用層那一個，一律寫 `from tianxia import arts as arts_mod`，因為 `from . import arts` 在包裡指到包自己。", "舊模組搬進包、改成別名之後，tests 裡用 `glob('tianxia/*.py')` 掃原始碼的（例 test_seal_acts 的頒詔呼叫端），以及 test_test_for 拿那個模組當例子的（T-02 的 ascend→cultivation），都會紅。開工時先 grep 這兩種。", "改成一行委派之後，test_for 照「內文寫到方法名」挑測試；方法名是常見字（practice、cultivate、allocate、art_rows）時，挑到的條數會比搬之前多好幾倍。", "same_behavior 有兩種寫法會讓路徑看起來有走到、其實沒走到，用單點突變才量得出來：追風步的舊品質要角色手上真的有那一門，因為讀檔時不在手上的品質本來就照「手上有的」清掉；配點那一句的「此刻全隊」要威力夠大，一級的人配一點不會出現那一段。", "破境丹衝關的「敗」、絕學契機的「成」、練成的「受傷」：在記憶體裡把機率擺成 1% 或必中（兩份程式同一套，做完擺回來）是穩的作法，不必靠種子碰運氣。", "/api/main 回的是 main_view 本身：境界卡在頂層的 milestone（WIP 寫成 .get('main') 讀不到）；破境卡在 status.ascension。", "BotRunner 不帶 client 時，假人的絕學定名一次都不走（named 0）。要比對假人那一段，照 run_bots 帶一個叫不動的 client。", "develop 在這一批開工之後合了第 22 批（151d9fc7）：allocate_stat 的 note_action 改成 self._note_action，_graduate_pass 搬進了引導包。後合的人要照這兩處改，細節寫在計畫第五節「合併時要對上的」。"], "open_questions": ["1. 包名 arts 跟共用規則層 tianxia/arts.py 同名（總表定的）。Task 2 改了邊界測試的斷言：同名的要列在 SHARED_NAMED_LIKE_A_PACKAGE 才放行，這是改核心測試斷言的例外。認這個改法，還是包要換名？換名的話總表與 final_owner.json 要跟著改。", "2. tests/core/test_test_for.py 的 T-02 例子換成 mapview→mapdata（原本的 ascend、cultivation 成了別名）；tests/seal/test_seal_acts.py 那一條改成連包一起掃。兩處都是改斷言的例外，請認。", "3. 總表歸修練的 13 個測試檔只搬了 test_chuangong、test_legend_xinde 兩個；其餘 11 個也測別人的規則（README 一個一個寫了理由），照「混合檔不拆」留在原處。test_cultivation 70 條裡只有最後三條 FB-069 與換季首創那一條不是這一包的，要不要在第 61 批拆出來？", "4. 改 engine 上修練的一行委派挑到的條數變多（practice 2995、cultivate 1696、allocate_stat 1391、art_rows 1830；搬之前 115～684）：一行委派要並上「內文寫到方法名」的測試檔，這四個名字是常見字。要不要讓 test_for 對委派只認 `.<名>(` 這種呼叫寫法？", "5. 合併：develop 已經有第 22 批。後合的人要做三件事：features/arts/actions.py 的 allocate_stat 改成 ctx._guide(ctx._note_action(\"allocate\"))，並拿掉 `from tianxia.guide import note_action`（不改的話包會經別名 import 包，邊界測試紅）；GAME_DELEGATE_CALLERS 的 _graduate_pass 5 對拿掉；服務清單 # arts 那一行的 _check_hints 跟第 22 批的去重。細節在計畫第五節。"], "report": "第 23 批（修練）五個 Task 都做完了，推上 dev/arts-1（674ee394），行為一個字不變。有一題要 PM 先定：包名 arts 跟共用規則層的 tianxia/arts.py 同名，我改了一條核心測試的斷言才過（下面第 1 條）。\n\n**接手**：從 dev/arts-1b 的 WIP（751ad824）開 dev/arts-1，WIP 那一筆留著，dev/arts-1b 沒動。開工前查了雲端的線：最近兩天還沒合進 develop 的只有 admin-gallery（形象包與 web）和 sleepy-shannon（只有 docs），都沒碰這一批要搬的方法與模組。\n\n**各 Task**：\n- **Task 1**：WIP 的 arts 一軌補完。學藝改到散人真的學得了的地方；破境丹衝絕學的「敗」與絕學契機的「成」改成在記憶體裡定機率；境界卡改讀 /api/main 的頂層；假人程式帶一個叫不動的 client，讓絕學定名走得到。在 base 上 selftest 兩次都穩，改一個字抓得到。\n- **Task 2**：籌備中的那兩句和裝飾器 not_while_preparing 搬進 tianxia/core/services.py，engine 照舊 import 回去用。新包 features/arts 一直開著，接走 learn: 的 choose，標題在動作之前先拿；認領 naming、renames_told、ascension、legend_fails、milestone_due 五個欄位。engine 原本 learn 的兩支拿掉。\n- **Task 3**：cultivation、chuangong、ascend 三個模組整個搬進包，舊名留成別名（同一個模組物件，monkeypatch 照樣打得到）。修練頁的動作進 actions.py、唯讀資料進 view.py，Game 留 33 個一行委派，_allocate_line 拿掉。\n  - 核心的單打服務 _seize 改叫新的查詢服務 _seize_chance，行尾標「過渡：第 26 批」；status_data 改叫 ascend_view。\n  - 決戰包 view.py 收場的絕學契機改成 ctx._seize_chance。\n  - 邊界清單加在 # arts 那一段；GAME_DIRECT 一個沒加。\n- **Task 4**：test_chuangong、test_legend_xinde 整檔搬進包，其餘 11 個是混合檔、留在原處，README 列了理由、條數和一行指令。\n- **Task 5**：\n  - 數字：改包任一檔挑到 140／141 條；包的測試 20 條約 9 秒；engine.py 14,018 → 13,812 行（−206）；完整數字在計畫第五節。\n  - 單點突變 20 種：第一次抓到 16 種；arts 一軌補兩段情境之後抓到 18 種，剩下 2 種在 API 上看不出差別。\n  - 導覽 武學與成長.md、核心與存檔.md 跟著改了。\n\n**PM 要定的**：\n1. **包名同名**：tianxia/arts.py 跟包名 arts 撞名，原本「共用規則層的模組不是包」那條斷言會紅。我改成同名的要列在 SHARED_NAMED_LIKE_A_PACKAGE 並寫理由才放行。認這個改法，還是包換名？換名的話總表與 final_owner.json 要跟著改。\n2. **另外兩處改了測試斷言**：test_test_for 的 T-02 例子換成 mapview→mapdata（原本的 ascend、cultivation 成了別名）；test_seal_acts 找頒詔呼叫端的那一條改成連包一起掃。\n3. **改 engine 挑到的條數變多**：practice、cultivate、allocate_stat、art_rows 是常見字，一行委派依規矩要並上寫到這個字的測試檔，現在挑到 1,400～3,100 條（搬之前 115～684）。要不要讓 test_for 對委派只認 `.<名>(` 的呼叫寫法？\n4. **test_cultivation 要不要拆**：70 條裡只有最後幾條不是這一包的，要不要在第 61 批拆出來？\n5. **合併時要對上的**：develop 已經合了第 22 批。後合的人要做三件事：\n   - allocate_stat 改用 ctx._note_action，並拿掉對 tianxia.guide 的 import（不改的話包會經別名 import 包，邊界測試紅）；\n   - GAME_DELEGATE_CALLERS 裡 _graduate_pass 的 5 對拿掉；\n   - 服務清單的 _check_hints 跟第 22 批的去重。\n   細節在計畫第五節「合併時要對上的」。\n\n**收尾**：暫存的大檔（解出來的 base、資料庫、比對輸出）都刪了，scratchpad b23 只留小腳本和紀錄。沒開伺服器，背景的比對與測試都跑完了。"}
const A = ARGS || {}
const need = k => { if (A[k] === undefined || A[k] === null || A[k] === '') throw new Error('pass ARGS.' + k); return A[k] }
// 換到別台機器要改這三行（ROOT：repo；SP：暫存資料夾；PY：有裝 requirements-dev 的 python）。下面 COMMON 寫的是 Windows 主機的坑，別的系統照實調整。
const ROOT = 'C:\\Ray\\專案\\天下大勢'
const SP = 'C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray--------\\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\\scratchpad'
const PY = 'C:/Ray/專案/天下大勢/.venv/Scripts/python.exe'
const BOOK = 'docs/superpowers/specs/2026-10-30-開發模式-design.md'
const BATCH = 'docs/superpowers/plans/2026-10-31-主動搬六包-批次.md'
const MASTER = 'docs/superpowers/plans/2026-10-31-全部拆包-總表.md'
const SURVEYDIR = 'docs/superpowers/plans/2026-10-31-全部拆包-調查'
const BASE = need('base')
const N = need('n')
const TITLE = need('title')
const PKG = need('pkg')
const FEAT = need('feature')
const DEV = need('dev')
const QA = A.qa || DEV.replace(/^dev\//, 'qa/')
const PLAN = need('plan')
const PREV = A.prev_plan || 'docs/superpowers/plans/2026-11-01-決戰包-第2批.md'
const P = need('ports')
const HOST = need('host')
const FB = need('fb')
const BODY = need('body')
const STEPS = need('check_steps')
const WEB = !!A.web
const LENSES_N = A.reviewers === 2 ? 2 : 3
const SCRATCH = 'b' + N

const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、qa/*、develop：一律明確 fetch（例 \`git fetch origin +refs/heads/${FEAT}:refs/remotes/origin/${FEAT}\`）。推完明確 fetch 再 \`git merge-base --is-ancestor HEAD origin/<分支>\` 確認，也看 \`git ls-remote\`。**每做完一個 Task 就推一次**。
- **在 Git Bash 裡給 git 的路徑寫 Windows 格式**（\`C:/Users/...\`），不要寫 \`/c/Users/...\`。scratch 資料夾裡的 .py 不要取標準函式庫的名字。隔離工作樹裡 Bash 可能擋 venv 的 python、含變數的 cp/tar、cd 再接 git：python 用 PowerShell 跑 ${PY}（PowerShell 5.1 會把沒有 BOM 的 UTF-8 .ps1 當 ANSI 讀，含中文路徑的指令直接寫在指令裡）；改檔腳本用 Write 工具寫成 .py 再跑或直接用 Edit（Bash heredoc 會吃掉反斜線）；Write 寫出 LF，工作樹是 CRLF，寫完自己轉，提交前 \`git cat-file blob\` 確認 git 裡是 LF。PowerShell 5.1 傳含雙引號的 commit 訊息會壞：訊息寫成檔案用 \`git commit -F\`。commit 訊息英文，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 規矩：開發規範手冊 ${BOOK}（第三節是包的規矩，**第十五節是落地補註與各批的 PM 認定，跟原文不同時照它**）；批次表 ${BATCH}（**第二節「每一批都照這些做」逐條照做**；第一節「並行」那一條也照做）；全部拆包總表 ${MASTER}（第三節這一批那一列、第六節、附錄甲與丙的歸屬裁定）；分區調查 ${SURVEYDIR}/（\`area_*.json\` 是每一個方法、模組歸誰）。技能用 Read 直接讀 .claude/skills/<名字>/SKILL.md（開發看 tianxia-dev）。**技能檔、CLAUDE.md、手冊、批次表、總表只有 PM 改**——學到的寫在回報。
- 暫存檔放 ${SP}\\${SCRATCH}* 底下（下面寫明），TIANXIA_DB 也指到那裡；不碰這份 clone 的 saves/；不要刪 .local/nightly/checkout；**做完把自己的暫存大檔（解出來的 base/head、資料庫、截圖以外的副本）刪掉**——企劃者 11/01：磁碟被用光過。
- 測試：pytest 一律 \`-n 4\`；\`scripts/test_for.py --base origin/${FEAT}\`。slow 不自動跟，要跑加 \`--slow\` 或 \`-m "slow or not slow"\`。不跑整套。
- 本機伺服器：只用給你的埠與 <名字>.localhost；\`-u\` 分離啟動、記 PID；模型網址指到 127.0.0.1:9，絕不打 11434；跑模擬前 patch \`ollama_client.from_config\`；收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（develop 第 9 版）不改。
- 主機也是企劃者的遊戲電腦：測試一律 \`-n 4\`，跑完伺服器與測試都收乾淨。
- 不要碰：${WEB ? '' : 'web/（這一批不切網頁）、'}輿圖（feature/map-view）、鐵匠鋪（feature/smithing-flow）、戰記（tale.py、server 的 TALES 與 narrate_*）、別的包的行為${A.dont_touch ? '、' + A.dont_touch : ''}。
- **第 11 批已經合了**：\`tianxia/core/features.py\` 有接縫掛鉤與兩個宣告（\`Shop\`、\`Verb\`）；手冊第十五節「第 11 批的 PM 認定」。**原位該接的照第 11 批的寫法接上掛鉤，不要再新增 \`GAME_DIRECT\`**（真的接不了寫理由）。${A.after15 ? '**第 15 批（共用規則層登記）也合了**：`registry.SHARED` 裡的模組包可以直接 import，不算過渡。' : ''}
- **並行**：${A.parallel || '同時還有別的拆包線在跑'}。共用登記檔（邊界清單、services.py、registry.py、FEATURES、same_behavior、\`aliases()\`）你加的每一筆都集中在 \`# ${PKG}\` 那一段後面，不穿插在別人的行之間；後合的那一條 PM 會先合 develop 再重比。
- **開工第一步先查雲端的線**：明確 fetch origin 的 \`claude/*\`（\`git ls-remote origin 'refs/heads/claude/*'\`），看最近兩天有提交、還沒合進 develop 的，有沒有改到這一批要搬的方法或模組（名字照你在計畫第一節量出來的清單）。**動到了就停**，stopped 寫哪一條、哪幾個方法，不要開工。
- 不開子代理、不開工作流程。任何畫面、輸出不能透露誰是假人；這一批不該有新字。做完就停；回報用繁體中文。
`

const DEV_SCHEMA = {
  type: 'object',
  properties: {
    branch: { type: 'string' }, head: { type: 'string' }, stopped: { type: 'string', description: '若因雲端的線或要企劃者定的事停下，寫原因；否則空字串' },
    commits: { type: 'array', items: { type: 'string' } },
    same_behavior: { type: 'string' }, acceptance: { type: 'string' }, tests: { type: 'string' },
    learned: { type: 'array', items: { type: 'string' } }, open_questions: { type: 'array', items: { type: 'string' } }, report: { type: 'string' },
  },
  required: ['branch', 'head', 'stopped', 'commits', 'same_behavior', 'acceptance', 'tests', 'learned', 'open_questions', 'report'],
}
const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      title: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'should', 'nit'] }, where: { type: 'string' }, evidence: { type: 'string' } },
      required: ['title', 'severity', 'where', 'evidence'] } },
    remeasured: { type: 'string' }, summary: { type: 'string' },
  },
  required: ['findings', 'summary'],
}
const FIX_SCHEMA = {
  type: 'object',
  properties: { head: { type: 'string' }, fixed: { type: 'array', items: { type: 'string' } }, rejected: { type: 'array', items: { type: 'string' } }, tests: { type: 'string' }, learned: { type: 'array', items: { type: 'string' } }, report: { type: 'string' } },
  required: ['head', 'fixed', 'rejected', 'tests', 'report'],
}
const CHECK_SCHEMA = {
  type: 'object',
  properties: { same: { type: 'boolean' }, steps: { type: 'string' }, diffs: { type: 'array', items: { type: 'string' } }, fbs: { type: 'array', items: { type: 'string' } }, screenshots: { type: 'string' }, qa_head: { type: 'string' }, report: { type: 'string' } },
  required: ['same', 'steps', 'diffs', 'report'],
}

const DEVP = `你是《天下大勢》的開發子代理，做**全部拆包的第 ${N} 批：${TITLE}**（總表 ${MASTER} 第三節第 ${N} 列）。承諾是**行為一個字不變**。
${COMMON}
先讀：
- 手冊 ${BOOK} 3.1～3.11 與第十五節（含各批的 PM 認定）。
- 批次表 ${BATCH}（整份，短）；總表第 ${N} 列整格與第六節、附錄甲與丙裡這一包的裁定；${SURVEYDIR}/ 裡歸這一包的 \`area_*.json\` 條目。
- **上一批的計畫 \`${PREV}\`**：照它的格式寫這一批（第一節現行程式對照、Task、第五節量到的、第六節修正、第七節合併紀錄）。
- 已成包的範本：\`tianxia/features/\`（sortie、explore、tavern、battle、feast、mall）與它們的 README、\`bots.py\`。
- \`scripts/same_behavior.py\`（各軌與 \`--help\`）。
用 \`grep -n '^#'\` 看大綱，只讀相關的節。調查的行號是 develop \`5fccb11a\` 量的，一律照現行程式重量。
分支：明確 fetch ${FEAT}（PM 已開在 develop ${BASE}；不是的話停下來回報）；\`git switch -c ${DEV} origin/${FEAT}\`（同名已存在就加 -work），推 \`git push origin HEAD:${DEV}\`。不碰 ${FEAT}、develop、main，PM 合。埠 ${P.dev}、${HOST}.localhost；暫存 ${SP}\\${SCRATCH}\\。

**這一批要做的（PM 定，照做）**：
${BODY}

做法：先照 superpowers:writing-plans 寫計畫 ${PLAN}（第一節「現行程式對照」照現行程式重量：要搬的方法與模組、要留的委派、留在原位的、接到第 11 批掛鉤的、核心直接碰包的各幾處、選項前綴在 choose／bot_policy／bot.py／bot_runner 的每一處）。然後一個 Task 一個 commit 做（superpowers:executing-plans，不開子代理）：
- **Task 1：證明的情境**：same_behavior 加這一包的一軌或在相關那一軌加情境（上面寫的情境；五種設定 none、weekend、season21、week7、test；整段、半舊半新〔切在這一包有「寫到一半」狀態的那一刻〕、假人〔BotRunner 碰得到這一包的選項〕）。先在 base 上跑兩次證明穩、改一個字抓得到，commit、推。
- **Task 2：核心那一側**：services.py、FEATURES、邊界清單（集中在 \`# ${PKG}\`）。跑核心測試＋煙霧一次。commit、推。
- **Task 3：搬**：方法與模組進 \`tianxia/features/${PKG}/\`（舊模組名留 \`sys.modules\` 別名，同一個模組物件）；委派一行、不加邏輯；拿了前綴就把 \`bot_policy.score\` 那一段搬進包的 \`bots.py\`（測試直接換的名字照舊生效）。commit、推。
- **Task 4：測試整檔搬**：整檔屬於這一包的才搬；混合檔不拆、記數字；README（含「另外要跑的混合檔」）。commit、推。
- **Task 5：證明與驗收**：same_behavior base（${BASE}）對 head：**所有軌**（出陣、約戰、決戰、酒肆、探索與這一批加的）、五種設定、整段、半舊半新、假人全部逐位元組一樣。量：包的測試時間、改包任一檔挑到幾條（≤ 300）、過渡處數、委派數、GAME_DIRECT 與 GAME_DELEGATE_CALLERS、engine.py 行數。寫進計畫第五節，導覽跟著改。commit、推。
測試：包的 tests（\`-m "slow or not slow"\`）；核心測試＋煙霧（Task 2、Task 5）；相關的 slow（git grep 找叫這一批方法、模組的測試檔），\`-m "slow or not slow" -n 4\`。不跑整套。
回報：head、commits、same_behavior、驗收數字、測試、學到的、要 PM 定的。碰到只有企劃者能定的，stopped 寫原因、停下來。`

const LENSES_ALL = [
  { key: 'proof', text: `**行為不變的證明誠不誠實**：讀 \`scripts/same_behavior.py\` 這一批加的情境，每一個都真的走到了嗎（看回應與資料庫裡有沒有那幾句、那幾筆，不是被擋在前面）？半舊半新的切點是不是在這一包「寫到一半」的那一刻？假人碰不碰得到這一包的選項？**自己重跑一次**：在 ${SP}\\${SCRATCH}-rev-proof\\ 開兩份 detached worktree（${BASE} 與開發的 head；Windows 路徑），season21 與 week7 各比一次所有軌，再做一個單點突變看 compare 抓不抓得到；用完 \`git worktree remove\`、刪暫存。要開伺服器用埠 ${P.rev}。` },
  { key: 'boundary', text: `**照不照手冊、批次表、總表**：包只 import 核心、共用規則層與標了「# 過渡：待搬」的舊模組（數一數，跟開發報的對）；委派都是一行；別名是同一個模組物件；這一批加的是不是集中在 \`# ${PKG}\`；第 11 批有掛鉤的位置接了掛鉤、沒有新增 \`GAME_DIRECT\`；前綴與 \`bots.py\`；歸屬照總表附錄甲／丙（有沒有搬了別包的、漏了這一包的）；README；有沒有碰到不准碰的（web/、輿圖、鐵匠鋪、戰記、資料庫結構、技能檔、CLAUDE.md、手冊、批次表、總表）。` + (LENSES_N === 2 ? `\n**再兼回歸**：自己在 ${SP}\\${SCRATCH}-rev-reg\\ 的 detached worktree 跑包的測試（含 slow，記時間）與相關的 slow；變異：包裡改壞一個搬過去的方法，看哪些測試紅、test_for 挑不挑得到；有沒有測試被改了斷言（只准改路徑與 import）。` : '') },
  { key: 'regress', text: `**回歸與測試**：自己在 ${SP}\\${SCRATCH}-rev-reg\\ 的 detached worktree 跑：包的測試（含 slow，記時間）、相關的 slow，\`-m "slow or not slow" -n 4\`；變異：在包裡改壞一個搬過去的方法，看哪些測試紅、test_for 挑不挑得到；monkeypatch 敏感的路照舊有效；改包任一檔 test_for 挑到幾條（≤ 300）；有沒有測試被改了斷言（只准改路徑深度與 import）。用完刪暫存。` },
]
const LENSES = LENSES_ALL.slice(0, LENSES_N)

const CHECKP = (head) => WEB ? `你是《天下大勢》的 QA 子代理，驗**全部拆包第 ${N} 批：${TITLE}**（${DEV} ${head}）。這一批動到 web/，照 .claude/skills/tianxia-qa/SKILL.md 做**完整實機 QA**：HEAD 對 BASE（origin/${FEAT} ${BASE}）同一個局面並排截圖（375 淺、375 深、1280）、逐像素比、主控台 0 錯誤、網路沒有 4xx／5xx、資料庫逐表比。
${COMMON}
做法照 docs/superpowers/handoff/packages/2026-11-04-第23-24批/tools/qa/ 的 serve.py、drive.py（用法看工作包「共用-環境與做法.md」第六節）（時鐘凍住、固定亂數、排程不開），複製到 ${SP}\\${SCRATCH}-qa\\ 改著用；兩份 worktree 的 .local/webpush_vapid.pem 用同一把。埠 ${P.head}（HEAD，${HOST}qa.localhost）、${P.base}（BASE，127.0.0.1）。要點的：${STEPS}
有問題寫成回饋單 ${FB}（docs/superpowers/feedback/試玩回饋.md）；報告、回饋單、挑過的並排圖推到 ${QA}（從 origin/${DEV} ${head} 開）。沒有問題就寫「沒有問題」。收的時候伺服器 taskkill /T、刪暫存大檔。
回報：same、走了哪些步驟、差異、FB、截圖路徑、qa 分支 head。` : `你是《天下大勢》的驗收子代理，驗**全部拆包第 ${N} 批：${TITLE}**（${DEV} ${head}）。純搬、web/ 一個字沒動的批，實機 QA 照總表 5.0 做「兩台真伺服器逐位元組比」：網頁檔沒變、伺服器回的位元組一樣，畫面就一定一樣；只拍三張圖做 sanity。
${COMMON}
開發與審查已經跑過測試與 same_behavior：**不要重跑**。
做法：照 docs/superpowers/handoff/packages/2026-11-04-第23-24批/tools/qa/ 的 serve.py、drive.py（用法看工作包「共用-環境與做法.md」第六節）（時鐘凍住只在 /__qa/clock 往前推、每次進行動鎖重設 game.rng 與 random、沒給種子的 Random 用固定種子、世界排程執行緒不開、/__qa/edit 擺位），複製到 ${SP}\\${SCRATCH}-chk\\ 改著用。明確 fetch ${DEV}、${FEAT}；開兩份 detached worktree：HEAD＝${head}、BASE＝origin/${FEAT}（${BASE}）；兩份的 .local/webpush_vapid.pem 用同一把。兩台伺服器開在埠 ${P.head}（HEAD，${HOST}chk.localhost）與 ${P.base}（BASE，127.0.0.1），season21（再加 week7 走一遍主要的幾步）：用真的 HTTP（帶 cookie）照同一串步驟打兩台——${STEPS}——**每一個回應的狀態碼與內容逐位元組比**（凍住時鐘之後帶時間戳的欄位應該一樣；真的不一樣的列出來分清楚是雜訊還是程式）；收場後兩個資料庫逐表比。再用 headless 瀏覽器各拍 375×812 淺色的三張相關畫面並排。收的時候 taskkill /T、刪兩份 worktree 與暫存大檔。
回報：same（全部一樣才是 true）、走了哪些步驟、差異清單、截圖路徑。有問題寫成回饋單 ${FB}（docs/superpowers/feedback/試玩回饋.md）並推到 ${QA}（從 origin/${DEV} 開；只放報告、回饋單、圖）；沒有問題就不必開 qa 分支。`

phase('Build')
const dev = DEV_RESULT
if (RENAME) {
  const r = await agent(`你是《天下大勢》的開發子代理。全部拆包第 23 批（修練包，${DEV} ${dev.head}）開發做完了，審查之前先做一件事：**把包名 \`arts\` 換成 \`cultivation\`**（PM 11/04 定，工作包 docs/superpowers/handoff/packages/2026-11-04-第23-24批/第23批-工作單.md 第三節）。
理由：\`arts\` 跟共用規則層的 \`tianxia/arts.py\` 同名，開發時為了放行改了邊界測試的斷言（\`SHARED_NAMED_LIKE_A_PACKAGE\`），而 \`scripts/new_feature.py\` 本來就不准撞名。\`tianxia/cultivation.py\` 是這一包的別名，同第 22 批 \`tianxia/guide.py\` 的做法，不算撞名。
${COMMON}
做法：明確 fetch，\`git switch -c ${DEV}-rename origin/${DEV}\`（同名已存在就加 -work）。
- \`git mv tianxia/features/arts tianxia/features/cultivation\`，改所有 \`features.arts\`、\`features/arts\`（約 11 個檔 27 行：\`git grep\` 量）、\`FEATURES\` 登記、\`# arts\` 段的標記。包裡 \`from tianxia import arts as arts_mod\` 照留（那是共用層的）。
- 邊界測試拿掉 \`SHARED_NAMED_LIKE_A_PACKAGE\` 與它放行的寫法，那條斷言還原成 base 的樣子。
- same_behavior 的軌名 \`arts\` 不改（改了雜湊對不起來）。
- 查：包的 id 有沒有寫進存檔或回應（\`Feature.id\`、認領的欄位）。**有的話停下來**，stopped 寫哪裡，不要改；行為必須一個字不變。
- 導覽、README、計畫裡寫 \`features/arts\` 的跟著改。總表與 \`final_owner.json\` 只有 PM 改，列在回報裡。
驗：邊界、兩個契約、\`test_test_for\`、包的 tests（\`-m "slow or not slow" -n 4\`）；\`same_behavior compare --base <85c3f682 解出來的> --head <工作樹> --tracks arts --profiles season21,week7\` 一樣。一個 commit，快轉推回 \`${DEV}\`，推完確認。埠 ${P.dev}。
回報 head、改了幾個檔幾行、驗的結果。`, { label: `rename:b${N}`, phase: 'Build', schema: { type: 'object', properties: { head: { type: 'string' }, stopped: { type: 'string' }, report: { type: 'string' } }, required: ['head', 'stopped', 'report'] } })
  if (!r) return { dev, rename: null }
  if (r.stopped) return { dev, rename: r, stopped: r.stopped }
  dev.head = r.head
  dev.report += '\n\n審查之前改了包名（arts → cultivation）：' + r.report
}
if (!dev) return { dev: null }
if (dev.stopped) return { dev, stopped: dev.stopped }
phase('Review')
const devText = `開發回報：\n${dev.report}\nsame_behavior：${dev.same_behavior}\n驗收：${dev.acceptance}`
const reviews = await parallel(LENSES.map(l => () => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推）。\n${COMMON}\n審 ${DEV} 的 ${dev.head}（明確 fetch），base 是 ${FEAT} ${BASE}。這一批：${TITLE}。\n${devText}\n你的鏡頭：${l.text}\n每一條發現寫 severity（blocker＝合了會壞、或行為變了、或違反手冊／批次表／總表／PM 定的；should；nit）、在哪裡、證據（指令與輸出）。沒有就回空陣列，不要湊。`, { label: `review:b${N}-${l.key}`, phase: 'Review', schema: REVIEW_SCHEMA })))
const findings = reviews.filter(Boolean).flatMap(r => r.findings || [])
let head = dev.head, fix = null
if (findings.some(f => f.severity !== 'nit') || findings.length > 2) {
  phase('Fix')
  fix = await agent(`你是《天下大勢》的開發子代理，修 ${DEV}（現在 ${dev.head}）上審查員的發現。\n${COMMON}\n分支：明確 fetch，\`git switch -c ${DEV}-fix origin/${DEV}\`（同名已存在就加 -work），推回 origin/${DEV}（快轉）。每修一條一個 commit、修一條推一次；先寫會紅的測試（或讓 same_behavior 先抓到）再修；屬實的才修，不屬實的寫進 rejected 附證據；nit 能順手就修。修完重跑 same_behavior 的 base 對 head（所有軌、五種）與相關測試。要開伺服器用埠 ${P.fix}、${HOST}fix.localhost。暫存 ${SP}\\${SCRATCH}-fix\\，做完刪大檔。\n開發回報（摘要）：${dev.report.slice(0, 5000)}\n發現：\n${JSON.stringify(findings, null, 1)}\n審查摘要：${reviews.filter(Boolean).map(r => r.summary).join('\n---\n')}\n回報 head、修了哪些、駁回哪些、測試、學到的。`, { label: `fix:b${N}`, phase: 'Fix', schema: FIX_SCHEMA })
  if (fix && fix.head) head = fix.head
}
phase('Check')
const check = await agent(CHECKP(head), { label: `check:b${N}`, phase: 'Check', schema: CHECK_SCHEMA })
return { n: N, dev, reviews, fix, head, check }
