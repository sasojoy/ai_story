export const meta = {
  name: 'merge-smithing-flow',
  description: 'Merge the smithing flow (host batches B and D, web batches A, C, E with the planner picks) into develop: QA branch into feature/smithing-flow, latest develop in, gate (four-profile boot, full suite without slow, related slow), push feature and develop, merge record; then a read-only verifier',
  phases: [
    { title: 'Merge', detail: 'merge helper: merge, gate, push, docs' },
    { title: 'Verify', detail: 'read-only checker' },
  ],
}

const ARGS = { qa_branch: 'origin/qa/smithing-web', qa_head: 'FILL', qa_notes: 'FILL', ports: '8191～8194' }
const ROOT = 'C:\\Ray\\專案\\天下大勢'
const SP = 'C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray----ai--\\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\\scratchpad'
const PY = 'C:/Ray/專案/天下大勢/.venv/Scripts/python.exe'
const DIR = 'mergesmith'
const FEAT = 'feature/smithing-flow'
const QA = ARGS.qa_branch
const QAHEAD = ARGS.qa_head
const PORTS = ARGS.ports

const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、qa/*、develop：一律明確 fetch。推完明確 fetch 再 \`git merge-base --is-ancestor HEAD origin/<分支>\` 確認，也看 \`git ls-remote\`。
- 在 Git Bash 裡給 git 的路徑寫 Windows 格式（\`C:/Users/...\`）。python 用 PowerShell 跑 ${PY}（含中文路徑的指令直接寫在指令裡）。改檔用 Edit，或用 Write 寫成 .py 再跑（Bash heredoc 會吃反斜線）。工作樹是 CRLF、git 裡存 LF：Write 寫出 LF，寫完自己轉；提交前 \`git ls-files --eol <檔>\` 確認 \`i/lf\`。commit 訊息英文寫成檔案用 \`git commit -F\`，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 測試一律 \`-n 4\`、\`TIANXIA_DB\` 指到 ${SP}\\${DIR}\\ 底下的暫存檔。本機伺服器只用埠 ${PORTS}、\`-u\` 分離啟動、記 PID、模型網址指到 127.0.0.1:9（絕不打 11434）、收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（develop 第 9 版）不改，要改就停下來回報。不要動 ${ROOT}\\.claude\\worktrees\\ 底下別人的工作樹。
- 主機也是企劃者的遊戲電腦：跑完伺服器與測試都收乾淨，暫存大檔刪掉（企劃者 11/01：磁碟被用光過）。
- 也可能有別的合併在排隊、Joy 也會在 GitHub 合雲端的 PR：推 develop 前一定先明確 fetch、確認 ancestor；develop 動了就再合一次、重跑不含 slow 的整套才推。
- 不開子代理、不開工作流程。回報用繁體中文。
`

const MERGE_SCHEMA = {
  type: 'object',
  properties: {
    develop_head: { type: 'string' }, feature_head: { type: 'string' }, gate_commit: { type: 'string' },
    conflicts: { type: 'string' }, gate: { type: 'string' }, docs: { type: 'string' },
    problems: { type: 'array', items: { type: 'string' } }, report: { type: 'string' },
  },
  required: ['develop_head', 'feature_head', 'gate_commit', 'conflicts', 'gate', 'docs', 'problems', 'report'],
}

phase('Merge')
const m = await agent(`你是《天下大勢》PM 派的合併助手：把**鐵匠鋪與合成流程**合進 develop。內容有主機側 B、D 兩批（smith_furnace、修淬拆解與批量拆解、品質有實質、淬煉吃一階料、神器頁資料、頭目戰擂台奪璽單挑也磨防具），加上網頁 A、C、E 三批與企劃者 11/03 挑的四處（丙、乙、乙、乙）。
${COMMON}
**狀態**：
- 要合的是 \`${QA}\` \`${QAHEAD}\`：QA 分支，從 \`origin/dev/smithing-web\` 8785cab6 開，上面多了 QA 報告與回饋單。開發、審查、修正、完整實機 QA 都過了。QA 的結論：${ARGS.qa_notes}
- 功能分支 \`${FEAT}\` 在 0c63b327，跟 develop 的 merge-base 是 a540a388（11/01），落後 develop 一百五十多筆：這段時間 develop 合了拆包第 2～7、10、11、15、16 批，還有雲端的 PR #128～#142。
- 計畫：\`docs/superpowers/plans/2026-10-29-鐵匠鋪與合成-B批.md\`、\`2026-10-29-鐵匠鋪與合成-D批.md\`、\`2026-11-01-鐵匠鋪網頁ACE.md\`；設計稿 \`docs/superpowers/specs/2026-10-29-鐵匠鋪與合成流程-design.md\`。

**PM 先量過的**（照程式再核一次）：
- 兩邊都改過的檔：\`server.py\`、\`tianxia/arena.py\`、\`battle_instance.py\`、\`engine.py\`、\`models.py\`、\`shopview.py\`、\`skillview.py\`、\`state.py\`、\`web/app.js\`、\`web/style.css\`、\`docs/superpowers/feedback/試玩回饋.md\`。
- smithing 那邊改 engine 的方法，除了新加的 \`smith_furnace\`，在 develop 上都還在 \`engine.py\`：\`shop_view\`、\`dismantle_weapon\`、\`_battle_gear\`、\`_seal_spectators\`、\`_seal_side_of\`、\`_duel_start\`、\`_duel_act\`、\`_arena_side\`、\`_arena_join\`、\`_arena_start\`、\`_fill\`。所以多半是同一段兩邊都改的行衝突，不是搬家。
- 真的碰到 develop 已經搬進包的程式（\`features/battle\`、\`sortie\`、\`explore\`、\`tavern\`、\`looks\`、\`tianxia/core/event_check.py\`）：把那幾行移植進包，\`Game\` 上的一行委派不加邏輯，寫進紀錄。
- \`models.py\`、\`state.py\`、\`world_state.py\` 新加的 \`cut\` 是存檔裡的欄位（預設 0），兩邊的欄位都留，資料庫結構不變（仍是第 9 版）。

步驟：
1. 明確 fetch develop、${FEAT}、${QA.replace(/^origin\//, '')}、dev/smithing-web。\`git worktree add --detach ${SP.replace(/\\/g, '/')}/${DIR}/wt origin/${FEAT}\`，\`git switch -c pm/merge-smith\`（本地用，不推這個名字）。
2. \`merge --no-ff ${QA}\`（應該不撞：dev/smithing-web 本來就從 0c63b327 開）→ \`merge --no-ff origin/develop\`。衝突照「程式為準」：
   - 兩邊的行都留。
   - 共用登記檔各段都留、照順序接：邊界清單、\`services.py\`、\`registry.py\` 與 \`registry.SHARED\`、\`FEATURES\`、\`aliases()\`、\`same_behavior.py\`。
   - smithing 新加的 import 或直連照邊界測試的要求登記；邊界與導覽的處數照合好之後 \`python tests/core/test_feature_boundaries.py\` 重印的寫。
   - \`server.py\` 兩邊的路由都留；\`試玩回饋.md\` 兩邊的單都留、照編號排。
   - **git 自己合好的也逐檔看**：兩邊各自的增刪行，合好的那一筆都要在。
3. **閘門**（動到 tianxia/、content/、server.py）：
   - 四種設定（season21、week7、weekend、不帶）各載一次內容、各起一次伺服器（GET / 200，起完關掉、確認埠空了）。
   - 不含 slow 的整套：\`python -m pytest -q -n 4\`。
   - 相關的 slow：\`python scripts/test_for.py --base origin/develop --slow\`，加 \`tests/gear tests/bots\` 用 \`-m "slow or not slow" -n 4\`。
   - 紅了：判斷是鐵匠鋪、develop 還是合起來才壞；合起來才壞的修（一個 commit，寫進紀錄），再跑那幾條加不含 slow 的整套。
   - 網頁那一半：\`app.js\`、\`style.css\` 兩邊都改過，test_for 會挑到網頁測試；另外 \`node --check web/app.js\`。合衝突時改到鐵匠鋪畫面的行，寫進紀錄給 PM 看。
4. 計畫 \`2026-11-01-鐵匠鋪網頁ACE.md\` 最後加一節「合併進 develop」，commit。閘門跑的那一筆的樹，除了 docs/ 以外要跟推上去的一樣。這一節寫：
   - 合併紀錄：哪一筆、撞了什麼怎麼解、閘門數字、移植了什麼。
   - **PM 11/03 定的**：開發留的三張新對比圖（挑定/對比-小籤看不了、對比-裝備庫320、對比-長名字）都照甲（已做進程式）；爐火看不了時用 aria-disabled 加提示泡泡（跟灰格同一套）照准；「淬煉 N/M」照半形。
   - QA 開的回饋單。
5. 推 \`HEAD:${FEAT}\`（快轉；不是快轉就停下回報）。再明確 fetch develop：動了就再合一次、重跑不含 slow 的整套。然後：
   - 在 detached 工作樹 checkout \`origin/develop\`，\`merge --no-ff origin/${FEAT}\`；
   - \`git diff <合好的> origin/${FEAT}\` 要是空的；
   - 確認 ancestor 再推 \`HEAD:develop\`；
   - \`${FEAT}\` 快轉到 develop 那一筆。
6. develop 上的文件（同一串，推前確認 ancestor）：
   - 全部拆包總表 \`docs/superpowers/plans/2026-10-31-全部拆包-總表.md\` 3.2 第 12 列「等什麼」：「鐵匠鋪那條線落地」改成已落地（develop 那一筆），只剩第 11 批（已合）。
   - 六包批次表 \`2026-10-31-主動搬六包-批次.md\` 第 12 列同樣改。
   - 交接 \`docs/superpowers/handoff/2026-10-30-主機側交接.md\`：**只改**第〇節表裡「鐵匠鋪網頁」那一列（改成已合、develop 那一筆、閘門數字）。交接第一節的功能分支表裡有 ${FEAT} 的話，寫已合進 develop。其餘段落 PM 自己改。
7. 收：
   - 工作樹 \`git worktree remove\`、本地分支 \`pm/merge-smith\` 刪掉（已含在 develop）；
   - 伺服器與測試都關、暫存大檔刪掉；
   - QA 留下的工作樹 \`${ROOT}\\.claude\\worktrees\\wf_b66bf522-e1d-1\`（dev/smithing-web-picks）、\`-2\`（qa/smithing-web-r2）：乾淨而且已經含在 develop 的話 \`git worktree remove\`，本地分支一起刪；不乾淨就留著寫進回報。
回報：develop 與 ${FEAT} 的 HEAD、閘門跑的那一筆、撞了什麼怎麼解、移植了什麼、閘門數字、改了哪些文件、有問題的。`, { label: 'merge:smithing', phase: 'Merge', schema: MERGE_SCHEMA })

phase('Verify')
const v = await agent(`你是《天下大勢》的唯讀檢查員（不改檔、不提交、不推），檢查鐵匠鋪與合成流程（${FEAT}）合進 develop 合得對不對。
${COMMON}
合併助手的回報：${m ? JSON.stringify(m) : '（合併助手失敗；只查清楚 origin 上 develop、' + FEAT + ' 現在的狀態，寫出停在哪）'}
查：
1. 明確 fetch。
   - \`origin/develop\` 有沒有含 \`${QA}\` \`${QAHEAD}\` 與 0c63b327；
   - \`origin/${FEAT}\` 是不是 develop 的祖先或等於；
   - develop 上那一筆合併的樹，跟閘門跑的那一筆除了 docs/ 以外一樣。
2. 兩邊各自的改動都在：
   - smithing 那邊：\`smith_furnace\`、\`dismantle_many\`、品質淬煉上限、\`cut\` 欄位、\`/api\` 新路由、網頁的爐火小籤、熬的小單、裝備庫二乘二、收藏冊圓印；
   - develop 那邊：拆包第 16 批的 \`tianxia/core/event_check.py\`、決戰包、形象包的回合 MVP、PR #136～#142。
   用 grep 與 \`git diff\` 抽查，列證據。
3. 在 ${SP}\\${DIR}-verify\\ 開一個 detached 工作樹（origin/develop），跑：
   - \`python tests/core/test_feature_boundaries.py\`，看處數跟合併紀錄寫的一樣；
   - 邊界、契約兩個測試檔、\`tests/gear\` 與 \`-m smoke\`（\`-n 4\`）。
   用完 \`git worktree remove\`、刪暫存。
4. 文件：計畫最後那一節、總表與批次表第 12 列、交接第〇節鐵匠鋪那一列都改了，數字跟回報一致。
5. 機器乾淨：沒有留下的 python、伺服器、無頭瀏覽器（只看命令列含 ${DIR} 或埠 ${PORTS} 的），那幾個埠沒人聽。
回報：每一項過／不過、證據、要 PM 處理的。`, { label: 'verify:smithing', phase: 'Verify', schema: {
  type: 'object', properties: { ok: { type: 'boolean' }, items: { type: 'array', items: { type: 'object', properties: { item: { type: 'string' }, pass: { type: 'boolean' }, note: { type: 'string' } }, required: ['item', 'pass', 'note'] } }, todo: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['ok', 'items', 'todo', 'summary'] } })

return { merge: m, verify: v }
