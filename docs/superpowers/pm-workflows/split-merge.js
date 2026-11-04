export const meta = {
  name: 'split-merge',
  description: 'Merge one finished split batch into split/trunk: dev branch into its feature branch, latest trunk in; the gate only checks what merging can break (profile boot, boundaries, contracts, smoke); push, write the merge record and PM decisions',
  phases: [
    { title: 'Merge', detail: 'merge helper: merge, gate, push, docs' },
  ],
}

const A = args || {}
const TRUNK = A.trunk || 'split/trunk'  // 拆分的主幹（企劃者 11/04：develop 訂錨點，全面分拆完才追）
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
const DECISIONS = A.decisions || ''
const NOTES = A.notes || ''
const DIR = 'merge' + N

const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、qa/*、${TRUNK}：一律明確 fetch。推完明確 fetch 再 \`git merge-base --is-ancestor HEAD origin/<分支>\` 確認，也看 \`git ls-remote\`。
- **不准改共用 clone 的 git 設定**：中文路徑印成八進位時，用單次的 \`git -c core.quotepath=off ...\`，不要 \`git config\`。
- 在 Git Bash 裡給 git 的路徑寫 Windows 格式（\`C:/Users/...\`）。python 用 PowerShell 跑 ${PY}（含中文路徑的指令直接寫在指令裡）。改檔用 Edit，或用 Write 寫成 .py 再跑（Bash heredoc 會吃反斜線）。工作樹是 CRLF、git 裡存 LF：Write 寫出 LF，寫完自己轉；提交前 \`git ls-files --eol <檔>\` 確認 \`i/lf\`。commit 訊息英文寫成檔案用 \`git commit -F\`，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 測試一律 \`-n 4\`、\`TIANXIA_DB\` 指到 ${SP}\\${DIR}\\ 底下的暫存檔。本機伺服器只用埠 ${PORTS}、\`-u\` 分離啟動、記 PID、模型網址指到 127.0.0.1:9（絕不打 11434）、收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（第 9 版）不改。不要動 ${ROOT}\\.claude\\worktrees\\ 底下別人的工作樹。
- 主機也是企劃者的遊戲電腦：跑完伺服器與測試都收乾淨，解出來的 base／head 與暫存大檔刪掉（企劃者 11/01：磁碟被用光過）。
- **這裡只合進 \`${TRUNK}\`，不碰 \`develop\`**：develop 是別人在開發的線，全面分拆完 PM 才追，這一次不要合它、不要推它。
- 同時有別的拆包線在跑、也可能有別的合併在排隊：推 ${TRUNK} 前一定先明確 fetch、確認 ancestor；${TRUNK} 動了就再合一次，重跑邊界與契約就好；多出來的提交只動 \`docs/\` 或 \`.claude/\`（\`git diff --stat <上次合的> origin/${TRUNK}\` 看得出來）時連這個也不用，紀錄寫一句。
- 不開子代理、不開工作流程。回報用繁體中文。
`

const MERGE_SCHEMA = {
  type: 'object',
  properties: {
    develop_head: { type: 'string' }, feature_head: { type: 'string' }, gate_commit: { type: 'string' },
    conflicts: { type: 'string' }, gate: { type: 'string' }, same_behavior: { type: 'string' },
    docs: { type: 'string' }, problems: { type: 'array', items: { type: 'string' } }, report: { type: 'string' },
  },
  required: ['develop_head', 'feature_head', 'gate_commit', 'conflicts', 'gate', 'docs', 'problems', 'report'],
}

phase('Merge')
const m = await agent(`你是《天下大勢》PM 派的合併助手：把**全部拆包第 ${N} 批：${TITLE}**合進 ${TRUNK}。
${COMMON}
**狀態**：要合的是 \`${SRC}\` \`${SRCHEAD}\`（開發、審查、修正、驗收都過了）；功能分支 \`${FEAT}\`。計畫 ${PLAN}（在 ${SRC} 上；第五節「交 PM 定的」、第六節修正、最後有驗收）。上一次同樣的合併怎麼做：${TRUNK} 上 \`docs/superpowers/plans/2026-11-01-核心收接縫.md\` 第七節與 \`2026-11-01-決戰包-第2批.md\` 第七節（照它們的格式寫這一批的第七節）。
${NOTES ? '**要特別處理的**：\n' + NOTES + '\n' : ''}
步驟：
1. 明確 fetch ${TRUNK}、${FEAT}、${SRC.replace(/^origin\//, '')}。\`git worktree add --detach ${SP.replace(/\\/g, '/')}/${DIR}/wt origin/${FEAT}\`，\`git switch -c pm/merge-b${N}\`（本地用，不推這個名字）。
2. \`merge --no-ff ${SRC}\` → \`merge --no-ff origin/${TRUNK}\`。衝突照「程式為準」：兩邊的行都留；共用登記檔（邊界清單、services.py、registry.py、FEATURES、same_behavior、\`aliases()\`）各包的段都留、照順序接；導覽的過渡處數照合好之後 \`python tests/core/test_feature_boundaries.py\` 重印的寫。**git 自己合好的也逐檔看**：兩邊各自的增刪行，合好的那一筆都要在。
3. **閘門只驗「合起來」才會壞的**（企劃者 11/04「不要一直測試變成高度重複測試，這就是拆分的精神」）。這一批的行為不變開發證明過了，這裡**不跑整套、不跑相關的 slow、不跑 same_behavior**；跨包的問題由主幹每天一次的全面檢查抓（PM 跑）：
   - 三種設定（season21、week7、不帶）各載一次內容、各起一次伺服器（GET / 200，起完關掉、確認埠空了）。
   - 邊界、契約、煙霧各一次：\`python -m pytest -q -n 4 tests/core/test_feature_boundaries.py tests/core/test_contract_core.py tests/core/test_contract_features.py\`、\`python -m pytest -q -n 4 -m smoke\`。${FULL ? '**核心批**另外跑一次 `scripts/test_for.py --base origin/' + TRUNK + '`（核心測試）。' : ''}
   - **只有合併時撞到程式**（共用登記檔以外的 \`tianxia/\`、\`server.py\`）才多跑：撞到的那幾個檔 \`scripts/test_for.py <檔>\`，加這一包那一軌的 \`same_behavior\`（base＝\`git archive origin/${TRUNK}\`，三種設定）。
   - 紅了：判斷是這一批、${TRUNK} 還是合起來才壞；合起來才壞的修（一個 commit，寫進紀錄），再跑那幾條。
4. 計畫第七節「合併紀錄」寫好、commit。閘門跑的那一筆的樹，除了 docs/ 以外要跟推上去的一樣。
5. 推 \`HEAD:${FEAT}\`（快轉；不是快轉就停下回報）。再明確 fetch ${TRUNK}（動了照上面「共通的規矩」再合一次）。在 detached 工作樹 checkout \`origin/${TRUNK}\`、\`merge --no-ff origin/${FEAT}\`，\`git diff <合好的> origin/${FEAT}\` 要是空的，確認 ancestor 再推 \`HEAD:${TRUNK}\`；\`${FEAT}\` 快轉到 ${TRUNK} 那一筆。
6. ${TRUNK} 上的文件（同一串，推前確認 ancestor）：
   - 全部拆包總表 \`docs/superpowers/plans/2026-10-31-全部拆包-總表.md\` 第 ${N} 列標「已合進 ${TRUNK}」（${TRUNK} 那一筆）；批次表 \`2026-10-31-主動搬六包-批次.md\` 若有這一批也改；「搬包中」有這一包就拿掉。
   - 手冊 \`docs/superpowers/specs/2026-10-30-開發模式-design.md\` 第十五節加「第 ${N} 批的 PM 認定」：${DECISIONS || '（照計畫第五節「交 PM 定的」，PM 沒另外寫的就寫「照開發的做法，認」）'}
   - 交接 \`docs/superpowers/handoff/2026-10-30-主機側交接.md\`：**只改**第〇節裡這一批那一句（改成已合、${TRUNK} 那一筆、閘門數字）。其餘段落 PM 自己改。
7. 收：工作樹 \`git worktree remove\`、本地分支 \`pm/merge-b${N}\` 刪掉（已含在 ${TRUNK}）、伺服器與測試都關、暫存大檔刪掉。
回報：${TRUNK} 與 ${FEAT} 的 HEAD、閘門跑的那一筆、撞了什麼怎麼解、閘門數字、改了哪些文件、有問題的。`, { label: `merge:b${N}`, phase: 'Merge', schema: MERGE_SCHEMA })

return { n: N, merge: m }
