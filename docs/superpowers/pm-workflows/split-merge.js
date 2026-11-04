export const meta = {
  name: 'split-merge',
  description: 'Merge one finished split batch into develop: dev/qa branch into its feature branch, latest develop in, gate (four-profile boot, test suite, related slow), same_behavior against the new develop, push feature and develop, write the merge record and PM decisions; then a read-only verifier',
  phases: [
    { title: 'Merge', detail: 'merge helper: merge, gate, push, docs' },
    { title: 'Verify', detail: 'read-only checker' },
  ],
}

const A = args || {}
const need = k => { if (A[k] === undefined || A[k] === null || A[k] === '') throw new Error('pass args.' + k); return A[k] }
const ROOT = 'C:\\Ray\\專案\\天下大勢'
const SP = 'C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray--------\\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\\scratchpad'
const PY = 'C:/Ray/專案/天下大勢/.venv/Scripts/python.exe'
const N = need('n')
const TITLE = need('title')
const FEAT = need('feature')
const SRC = need('source')          // e.g. origin/dev/core-shared-1 or origin/qa/xxx
const SRCHEAD = need('source_head')
const PLAN = need('plan')
const PORTS = need('ports')        // e.g. "8179～8182"
const FULL = !!A.full_suite
const SLOW = A.related_slow || '這一批計畫第五節與包的 README「另外要跑的混合檔」列的 slow 測試檔，加包的 tests/'
const DECISIONS = A.decisions || ''
const NOTES = A.notes || ''
const DIR = 'merge' + N

const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、qa/*、develop：一律明確 fetch。推完明確 fetch 再 \`git merge-base --is-ancestor HEAD origin/<分支>\` 確認，也看 \`git ls-remote\`。
- **不准改共用 clone 的 git 設定**：中文路徑印成八進位時，用單次的 \`git -c core.quotepath=off ...\`，不要 \`git config\`。
- 在 Git Bash 裡給 git 的路徑寫 Windows 格式（\`C:/Users/...\`）。python 用 PowerShell 跑 ${PY}（含中文路徑的指令直接寫在指令裡）。改檔用 Edit，或用 Write 寫成 .py 再跑（Bash heredoc 會吃反斜線）。工作樹是 CRLF、git 裡存 LF：Write 寫出 LF，寫完自己轉；提交前 \`git ls-files --eol <檔>\` 確認 \`i/lf\`。commit 訊息英文寫成檔案用 \`git commit -F\`，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 測試一律 \`-n 4\`、\`TIANXIA_DB\` 指到 ${SP}\\${DIR}\\ 底下的暫存檔。本機伺服器只用埠 ${PORTS}、\`-u\` 分離啟動、記 PID、模型網址指到 127.0.0.1:9（絕不打 11434）、收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（develop 第 9 版）不改。不要動 ${ROOT}\\.claude\\worktrees\\ 底下別人的工作樹。
- 主機也是企劃者的遊戲電腦：跑完伺服器與測試都收乾淨，解出來的 base／head 與暫存大檔刪掉（企劃者 11/01：磁碟被用光過）。
- 同時有別的拆包線在跑、也可能有別的合併在排隊：推 develop 前一定先明確 fetch、確認 ancestor；develop 動了就再合一次、重跑不含 slow 的整套與 same_behavior 才推。**例外**（PM 11/04，第 17 批合併的教訓）：develop 多出來的提交只動 \`docs/\` 或 \`.claude/\`（\`git diff --stat <上次合的> origin/develop\` 看得出來；全 repo 沒有程式或測試讀它們）時，再合一次、確認沒撞就好，不必重跑，紀錄寫一句。
- 不開子代理、不開工作流程。回報用繁體中文。
`

const MERGE_SCHEMA = {
  type: 'object',
  properties: {
    develop_head: { type: 'string' }, feature_head: { type: 'string' }, gate_commit: { type: 'string' },
    conflicts: { type: 'string' }, gate: { type: 'string' }, same_behavior: { type: 'string' },
    docs: { type: 'string' }, problems: { type: 'array', items: { type: 'string' } }, report: { type: 'string' },
  },
  required: ['develop_head', 'feature_head', 'gate_commit', 'conflicts', 'gate', 'same_behavior', 'docs', 'problems', 'report'],
}

phase('Merge')
const m = await agent(`你是《天下大勢》PM 派的合併助手：把**全部拆包第 ${N} 批：${TITLE}**合進 develop。
${COMMON}
**狀態**：要合的是 \`${SRC}\` \`${SRCHEAD}\`（開發、審查、修正、驗收都過了）；功能分支 \`${FEAT}\`。計畫 ${PLAN}（在 ${SRC} 上；第五節「交 PM 定的」、第六節修正、最後有驗收）。上一次同樣的合併怎麼做：develop 上 \`docs/superpowers/plans/2026-11-01-核心收接縫.md\` 第七節與 \`2026-11-01-決戰包-第2批.md\` 第七節（照它們的格式寫這一批的第七節）。
${NOTES ? '**要特別處理的**：\n' + NOTES + '\n' : ''}
步驟：
1. 明確 fetch develop、${FEAT}、${SRC.replace(/^origin\//, '')}。\`git worktree add --detach ${SP.replace(/\\/g, '/')}/${DIR}/wt origin/${FEAT}\`，\`git switch -c pm/merge-b${N}\`（本地用，不推這個名字）。
2. \`merge --no-ff ${SRC}\` → \`merge --no-ff origin/develop\`。衝突照「程式為準」：兩邊的行都留；共用登記檔（邊界清單、services.py、registry.py、FEATURES、same_behavior、\`aliases()\`）各包的段都留、照順序接；導覽的過渡處數照合好之後 \`python tests/core/test_feature_boundaries.py\` 重印的寫。**git 自己合好的也逐檔看**：兩邊各自的增刪行，合好的那一筆都要在。
3. **閘門**：
   - 四種設定（season21、week7、weekend、不帶）各載一次內容、各起一次伺服器（GET / 200，起完關掉、確認埠空了）。
   - ${FULL ? '**整套含 slow**：`python -m pytest -q -n 4 -m "slow or not slow"`（核心批）。' : '**不含 slow 的整套**：`python -m pytest -q -n 4`；**加相關的 slow**：' + SLOW + '，`-m "slow or not slow" -n 4`。'}
   - 紅了：判斷是這一批、develop 還是合起來才壞；合起來才壞的修（一個 commit，寫進紀錄），再跑那幾條加不含 slow 的整套。
   - \`same_behavior\` 對新的 develop：base＝\`git archive origin/develop\`、head＝合好的這一份（兩份都不含 docs/），\`compare\`（所有軌：\`--tracks\` 照 \`--help\` 列的全部）與 \`explore-compare\`，五種設定、整段與半舊半新、假人，全部一樣；記每一軌每一種的雜湊與行數。比完刪 base、head、暫存。
4. 計畫第七節「合併紀錄」寫好、commit。閘門跑的那一筆的樹，除了 docs/ 以外要跟推上去的一樣。
5. 推 \`HEAD:${FEAT}\`（快轉；不是快轉就停下回報）。再明確 fetch develop（動了就再合一次、重跑不含 slow 的整套與 same_behavior）。在 detached 工作樹 checkout \`origin/develop\`、\`merge --no-ff origin/${FEAT}\`，\`git diff <合好的> origin/${FEAT}\` 要是空的，確認 ancestor 再推 \`HEAD:develop\`；\`${FEAT}\` 快轉到 develop 那一筆。
6. develop 上的文件（同一串，推前確認 ancestor）：
   - 全部拆包總表 \`docs/superpowers/plans/2026-10-31-全部拆包-總表.md\` 第 ${N} 列標「已合進 develop」（develop 那一筆）；批次表 \`2026-10-31-主動搬六包-批次.md\` 若有這一批也改；「搬包中」有這一包就拿掉。
   - 手冊 \`docs/superpowers/specs/2026-10-30-開發模式-design.md\` 第十五節加「第 ${N} 批的 PM 認定」：${DECISIONS || '（照計畫第五節「交 PM 定的」，PM 沒另外寫的就寫「照開發的做法，認」）'}
   - 交接 \`docs/superpowers/handoff/2026-10-30-主機側交接.md\`：**只改**第〇節裡這一批那一句（改成已合、develop 那一筆、閘門數字）。其餘段落 PM 自己改。
7. 收：工作樹 \`git worktree remove\`、本地分支 \`pm/merge-b${N}\` 刪掉（已含在 develop）、伺服器與測試都關、暫存大檔刪掉。
回報：develop 與 ${FEAT} 的 HEAD、閘門跑的那一筆、撞了什麼怎麼解、閘門數字、same_behavior 每一軌結果、改了哪些文件、有問題的。`, { label: `merge:b${N}`, phase: 'Merge', schema: MERGE_SCHEMA })

phase('Verify')
const v = await agent(`你是《天下大勢》的唯讀檢查員（不改檔、不提交、不推），檢查全部拆包第 ${N} 批（${TITLE}）合進 develop 合得對不對。
${COMMON}
合併助手的回報：${m ? JSON.stringify(m) : '（合併助手失敗；只查清楚 origin 上 develop、' + FEAT + ' 現在的狀態，寫出停在哪）'}
查：
1. 明確 fetch。\`origin/develop\` 有沒有含 \`${SRC}\` \`${SRCHEAD}\`；\`origin/${FEAT}\` 是不是 develop 的祖先或等於；develop 上那一筆合併的樹，跟閘門跑的那一筆除了 docs/ 以外一樣。
2. 在 ${SP}\\${DIR}-verify\\ 開一個 detached 工作樹（origin/develop），跑 \`python tests/core/test_feature_boundaries.py\` 看處數跟合併紀錄寫的一樣；跑邊界、契約兩個測試檔與 \`-m smoke\`（\`-n 4\`）。用完 \`git worktree remove\`、刪暫存。
3. 文件：計畫第七節、總表、手冊第十五節、交接第〇節那一句都改了，數字跟回報一致。
4. 機器乾淨：沒有留下的 python／伺服器／無頭瀏覽器（只看命令列含 ${DIR} 或埠 ${PORTS} 的），那幾個埠沒人聽。
回報：每一項過／不過、證據、要 PM 處理的。`, { label: `verify:b${N}`, phase: 'Verify', schema: {
  type: 'object', properties: { ok: { type: 'boolean' }, items: { type: 'array', items: { type: 'object', properties: { item: { type: 'string' }, pass: { type: 'boolean' }, note: { type: 'string' } }, required: ['item', 'pass', 'note'] } }, todo: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['ok', 'items', 'todo', 'summary'] } })

return { n: N, merge: m, verify: v }
