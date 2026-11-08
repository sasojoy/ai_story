export const meta = {
  name: 'split-wave',
  description: 'One wave of the full split (planner 11/06: full speed, one check per wave): several lines of batches built in parallel with no per-batch review, compare or merge; then one merge, one zero-token gate (all tracks, full suite with slow, three profile boots), one read-only review per line, one fix round',
  phases: [
    { title: 'Build', detail: 'each line builds its batches in order, two fresh agents per batch' },
    { title: 'Merge', detail: 'all lines merged into the wave branch' },
    { title: 'Gate', detail: 'wave_gate.py once, no tokens: all tracks, explore, full suite with slow, three boots' },
    { title: 'Review', detail: 'one read-only review per line, working from the mechanical moved report' },
    { title: 'Check', detail: 'real-browser QA once, only when the wave touched web/' },
    { title: 'Fix', detail: 'one round on red and findings; only what was fixed is rerun' },
  ],
}

const A = args || {}
const need = k => { if (A[k] === undefined || A[k] === null || A[k] === '') throw new Error('pass args.' + k); return A[k] }
const ROOT = 'C:\\Ray\\專案\\天下大勢'
const SP = need('scratch')
const PY = 'C:/Ray/專案/天下大勢/.venv/Scripts/python.exe'
const BOOK = 'docs/superpowers/specs/2026-10-30-開發模式-design.md'
const BATCH = 'docs/superpowers/plans/2026-10-31-主動搬六包-批次.md'
const ROUND2 = !!A.round2  // 第二輪：總表換一份、各包 README 與 docs/guide 線上不動（PM 11/07）
const MASTER = A.master || 'docs/superpowers/plans/2026-10-31-全部拆包-總表.md'
const SURVEYDIR = 'docs/superpowers/plans/2026-10-31-全部拆包-調查'
const TOOLS = 'docs/superpowers/pm-workflows'
const WAVE = need('wave')             // 這一波的名字，例 "A"
const WAVE_BRANCH = A.branch || ''    // 合起來的分支，例 wave/A
const MERGE_BASE = A.merge_base || '' // 合併與閘門的基準；先開發、之後才合的波在第二次叫的時候給
const LINES = A.lines || []           // [{ name, base, batches: [{ n, title, pkg, dev, plan, ports, model?, custom?, body }] }]；只合不開發時傳 built
const MERGE_PORT = A.merge_port || 0
const FIX_PORT = A.fix_port || 0
const MERGE_INTO = A.merge_extra || '' // 合併時要多合的東西（PM 寫）

const halted_word = (x) => { const s = String(x || '').trim(); return !!s && !/^(無|沒有|none|no|n\/a)?[。.]?$/i.test(s) && !/^沒有?停/.test(s) }  // 子代理回「無」「沒有停，全部合完」都不算停下來（A、D 波合併踩過）
const sha_of = (x) => (String(x || '').match(/[0-9a-f]{40}/) || [''])[0] || String(x || '').trim()  // head 欄位子代理可能帶字（D 波踩過）
const GATE_BASE = A.gate_base || MERGE_BASE  // 閘門比對的基準；合併之後基準又有新提交時另外給
const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、wave/*：一律明確 fetch（\`git fetch origin +refs/heads/<分支>:refs/remotes/origin/<分支>\`）。推完 \`git ls-remote\` 確認。**每做完一個 Task 就推一次**。
- 不准改共用 clone 的 git 設定；中文路徑用單次的 \`git -c core.quotepath=off ...\`。在 Git Bash 裡給 git 的路徑寫 Windows 格式。python 用 PowerShell 跑 ${PY}（含中文路徑的指令直接寫在指令裡）。改檔用 Edit，或用 Write 寫成 .py 再跑；Write 寫出 LF，工作樹是 CRLF，寫完自己轉，提交前 \`git ls-files --eol <檔>\` 確認 \`i/lf\`。commit 訊息英文、寫成檔案用 \`git commit -F\`，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 暫存放 ${SP}\\wave${WAVE}\\ 底下，TIANXIA_DB 也指到那裡；不碰這份 clone 的 saves/；做完把解出來的 base／head、資料庫這些大檔刪掉（企劃者 11/01：磁碟被用光過）。
- 伺服器：只用給你的埠、\`-u\` 分離啟動、記 PID；模型網址指到 127.0.0.1:9，絕不打 11434；跑模擬前 patch \`ollama_client.from_config\`；收的時候 \`taskkill /PID <pid> /T /F\`。
- 不下載、不安裝任何東西。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel；資料庫結構（第 9 版）不改。任何畫面、輸出不能透露誰是假人；這一波不該有新字。不開子代理、不開工作流程。回報用繁體中文。
- **context 就是額度**：大檔用 grep 加行號範圍讀，不整份讀、不重讀同一段；指令輸出先截短。
`

const DEV_SCHEMA = {
  type: 'object',
  properties: {
    branch: { type: 'string' }, head: { type: 'string' }, stopped: { type: 'string', description: '只有企劃者能定的事才停，寫原因；否則空字串' },
    commits: { type: 'array', items: { type: 'string' } },
    tests: { type: 'string' },
    decided: { type: 'array', items: { type: 'string' }, description: '你選了保守做法的判斷，一條一句' },
    leftovers: { type: 'array', items: { type: 'string' }, description: '留給後面哪一批的東西' },
    docs: { type: 'array', items: { type: 'string' }, description: '第二輪：要寫進各包 README、docs/guide 的句子，一條一句，寫明哪個檔、改哪裡；波末文件代理統一寫' },
    report: { type: 'string' },
  },
  required: ['branch', 'head', 'stopped', 'commits', 'tests', 'decided', 'leftovers', 'report'],
}
const MERGE_SCHEMA = {
  type: 'object',
  properties: { head: { type: 'string', description: '只寫 40 碼 SHA' }, conflicts: { type: 'string' }, checks: { type: 'string' }, stopped: { type: 'string', description: '解不了才寫原因；否則空字串' }, report: { type: 'string' } },
  required: ['head', 'conflicts', 'checks', 'stopped', 'report'],
}
const GATE_SCHEMA = {
  type: 'object',
  properties: { green: { type: 'boolean' }, result: { type: 'string', description: 'result.json 的全文' } },
  required: ['green', 'result'],
}
const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      title: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'should', 'nit'] }, where: { type: 'string' }, evidence: { type: 'string' } },
      required: ['title', 'severity', 'where', 'evidence'] } },
    summary: { type: 'string' },
  },
  required: ['findings', 'summary'],
}
const FIX_SCHEMA = {
  type: 'object',
  properties: { head: { type: 'string', description: '只寫 40 碼 SHA' }, fixed: { type: 'array', items: { type: 'string' } }, rejected: { type: 'array', items: { type: 'string' } }, tests: { type: 'string' }, stopped: { type: 'string', description: '只有企劃者能定的事才寫原因；否則空字串' }, report: { type: 'string' } },
  required: ['head', 'fixed', 'rejected', 'tests', 'stopped', 'report'],
}

const WAVE_RULE = `**波次模式**（企劃者 11/06「火力全開」「減少測試驗收的頻率」「一次性多改幾個功能再一起全部合併測試」）：這一批**沒有逐批審查、沒有逐批比對、沒有逐批合併**。一波的每條線做完，PM 合起來一次跑所有軌、整套含 slow、三種設定起伺服器，再一人一條線唯讀審查。所以：
- **你不跑** same_behavior compare、整套、slow、別包的測試，也不跑 test_for 全挑。承諾照舊：**行為一個字不變**，閘門會逐位元組比。
- 拿不準的判斷**選最保守的、照現在的先後與位置留著**，寫進回報的 decided；不等 PM。只有企劃者才能定的事才停。
- 派工單的字跟現行程式對不上時，以現行程式為準，寫進 decided。
- 不碰的：\`develop\`、\`main\`、\`split/trunk\`、技能檔、CLAUDE.md、手冊、批次表、總表（學到的寫回報）。${'`'}web/${'`'} 只有派工單明寫才碰。`

const devHead = (b) => `你是《天下大勢》的開發子代理，做${b.custom ? `**${b.title}**` : `**全部拆包第 ${b.n} 批：${b.title}**（總表 ${MASTER} 第三節第 ${b.n} 列）`}。
${COMMON}
${WAVE_RULE}
規矩：手冊 ${BOOK} 第三節（包的規矩）用 grep 看標題、只讀要用的那幾節；第十五節只 grep 這一包、相關批號的 PM 認定，不整節讀。${b.custom ? '' : `總表第 ${b.n} 列整格、第二節這一包、附錄甲丙這一包的裁定；${SURVEYDIR}/ 裡歸這一包的 \`area_*.json\`（行號是舊的，一律照現行程式重量）。`}已成包的範本看 \`tianxia/features/\`。
共用登記檔（services_list.md、registry.py、FEATURES、\`aliases()\`）你加的每一筆集中在 \`# ${b.pkg}\` 那一段，不穿插在別人的行之間；同一波別條線也在加，PM 合的時候接好。邊界名單（\`tests/core/boundary_tables.py\`）不一樣：加列加在那一包的組，搬走直接刪那一行，不寫 \`del\`、\`-=\`。
**這一批要做的（PM 定，照做）**：
${b.body}`

const P1 = (b, base) => `${devHead(b)}

**這一批分兩段，每段一個新的子代理。你只做第一段：量與計畫，做完推上去、回報、就停。**
分支：\`git switch -c ${b.dev} ${base}\`（先明確 fetch 拿到這一筆；同名已存在就加 -work），推 \`git push origin HEAD:${b.dev}\`。暫存 ${SP}\\wave${WAVE}\\b${b.n}\\，埠 ${b.ports}。
1. 寫計畫 ${b.plan}，**短，不超過 120 行**，只寫下一段要用的（下一段看不到你讀過的東西，也不該再重量）：要搬的方法與模組（行號範圍）；留下的委派怎麼寫；留在原位的與理由；接哪個掛鉤；核心直接碰包的各幾處；選項前綴在 choose／bot_policy／bot.py／bot_runner 的每一處；被 patch 的名字怎麼保證打得到；順序與坑。不要寫逐行程式碼。
2. **情境**：先查 \`scripts/sb/tracks/\` 現有的軌有沒有走到這一批搬的東西（grep 按鈕 id、路由）。**走到了就不加**，計畫寫哪一軌走到什麼。走不到的才加：原創名字、新開一檔 \`scripts/sb/tracks/<軌>.py\`，檔尾 \`register_track\`、三種設定、整段、半舊半新（切在這一包「寫到一半」的那一刻）、假人碰得到；跑那一軌 selftest 一次（穩、改一字抓得到）。情境的說明字寫「走到」的要在輸出看過才寫。
commit、推。回報 head、計畫重點、加了哪一軌（或現有哪一軌走到）。`

const P2 = (b, prev) => `${devHead(b)}

**這一批分兩段，第一段做完了，你做第二段：搬。做完推上去、回報、就停。**
先讀計畫 \`${b.plan}\`（在 \`origin/${b.dev}\` 上）。分支：明確 fetch ${b.dev}；\`git switch -c ${b.dev}-move origin/${b.dev}\`（同名已存在就加 -work），做完快轉推回 \`${b.dev}\`。暫存 ${SP}\\wave${WAVE}\\b${b.n}\\，埠 ${b.ports}。
上一段的回報：
${String(prev.report || '').slice(0, 3000)}

${ROUND2 ? `一個 Task 一個 commit，照第二輪總表那一節與你的計畫分。順序就是行為。**各包 README、\`docs/guide\` 不動**：要寫的句子放回報的 docs。` : `一個 Task 一個 commit：
- **Task 2 核心那一側**：services.py、FEATURES、邊界清單（集中在 \`# ${b.pkg}\`）。
- **Task 3 搬**：方法與模組進 \`tianxia/features/${b.pkg}/\`（舊模組名留 \`sys.modules\` 別名，同一個模組物件）；委派一行、不加邏輯；前綴的 \`bot_policy.score\` 那一段搬進包的 \`bots.py\`。核心批照派工單改掛鉤，順序就是行為。
- **Task 4 測試與文件**：整檔屬於這一包的測試才搬（只改路徑與 import，不改斷言），混合檔不拆；包的 README（含「另外要跑的」）；\`docs/guide\` 那一塊補程式的位置。`}
**交出去之前自己對一次**（以前審查最常抓到的，現在沒有逐批審查，漏了要等波末才發現）：
- ${ROUND2 ? '第二輪總表這一節點名' : '總表附錄甲點名'}這一批的方法與測試檔有沒有漏；這一批的 \`PlayerState\` 欄位 \`player_fields\` 與 README 有沒有認領；列舉每一包的表（\`STAGE_PACKAGES\`、\`aliases()\`）；拿掉委派後 engine 頂端沒人用的 import 拿掉、在自己的段 \`GAME_IMPORTS -=\`。
- 寫死 \`"engine.py"\` 的測試（\`git grep -n '"engine.py"' -- tests tianxia/features\`）；\`renown.gain(..., "fame", ...)\` 那張清單（\`tianxia/features/guide/tests/test_explain2.py\`）；被 patch 的舊路徑打不打得到（\`git grep\` 測試與 \`scripts/\`）；selftest 的目標句（各軌檔 \`register_track\` 的第三個參數，\`sortie\`、\`duel\` 在 \`scripts/sb/base.py\` 檔尾，\`EXPLORE_MUTATIONS\` 在 \`scripts/sb/tracks/explore.py\`）搬了要補檔清單。
**只跑這些，各一次**（跑在最後的程式上）：\`python ${TOOLS}/undef_scan.py tianxia server.py\`；\`python -m pytest -q -n 4 tianxia/features/${b.pkg}/tests\`（有這個資料夾才跑）加計畫列的幾個最直接的檔；\`python -m pytest -q -n 4 tests/core/test_feature_boundaries.py tests/core/test_contract_core.py tests/core/test_contract_features.py\`。base 上就紅的（這條分支可能還在修合併的紅）在 base 上跑同一條確認，寫進回報、不用修。
回報 head、commits、tests、decided（你選保守做法的判斷）、leftovers（留給哪一批）${ROUND2 ? '、docs（要寫進 README、導覽的句子）' : ''}。`

const devOpts = (b, key) => ({ label: `dev:b${b.n}-${key}`, phase: 'Build', schema: DEV_SCHEMA, isolation: 'worktree', model: b.model || 'opus' })  // 企劃者 11/08：開發派 Opus

async function buildLine(line) {
  let base = line.base
  const done = []
  for (const b of line.batches) {
    const p1 = await agent(P1(b, base), devOpts(b, 'plan'))
    if (!p1) return { line: line.name, done, stopped: `第 ${b.n} 批第一段沒有結果` }
    if (halted_word(p1.stopped)) return { line: line.name, done, stopped: `第 ${b.n} 批：${p1.stopped}`, partial: p1 }
    const p2 = await agent(P2(b, p1), devOpts(b, 'move'))
    if (!p2) return { line: line.name, done, stopped: `第 ${b.n} 批第二段沒有結果`, partial: p1 }
    if (halted_word(p2.stopped)) return { line: line.name, done, stopped: `第 ${b.n} 批：${p2.stopped}`, partial: p2 }
    done.push({ n: b.n, title: b.title, dev: b.dev, head: p2.head, base, tests: p2.tests, decided: [...(p1.decided || []), ...(p2.decided || [])], leftovers: [...(p1.leftovers || []), ...(p2.leftovers || [])], docs: [...(p1.docs || []), ...(p2.docs || [])], report: p2.report })
    base = p2.head
  }
  return { line: line.name, base: line.base, head: base, branch: line.batches[line.batches.length - 1].dev, done, stopped: '' }
}

let built = A.built
if (!built) {
  phase('Build')
  built = (await parallel(LINES.map(l => () => buildLine(l)))).filter(Boolean)
  const halted = built.filter(l => l.stopped)
  if (A.stop_after_build || halted.length || built.length !== LINES.length) return { wave: WAVE, built, stopped: halted.map(l => l.stopped).join('；') || (A.stop_after_build ? '' : '有一條線沒有結果') }
}

const lineList = built.map(l => `- 線 ${l.line}：\`${l.branch}\` ${l.head}（從 ${l.base} 開；批：${l.done.map(d => d.n).join('、')}）`).join('\n')

phase('Merge')
const merged = A.merged_head ? { head: A.merged_head, conflicts: '', checks: '', stopped: '', report: 'PM：合併在上一段做完，下一波已從這一筆開工' } : await agent(`你是《天下大勢》PM 派的合併助手：把**第 ${WAVE} 波**每條線合起來。
${COMMON}
**要合的**：
${lineList}
${MERGE_INTO ? '**另外要合的（PM 寫）**：\n' + MERGE_INTO + '\n' : ''}
分支：明確 fetch 上面每一條。\`git switch -c ${WAVE_BRANCH} ${MERGE_BASE}\`（同名已存在就加 -work 重開），一條一條 \`merge --no-ff\`。埠 ${MERGE_PORT}，暫存 ${SP}\\wave${WAVE}\\merge\\。
衝突照「程式為準」：兩邊的行都留；共用登記檔（邊界清單、services_list.md、registry.py、FEATURES、\`aliases()\`、\`bot_policy\`）各包的段都留、照 FEATURES 的順序接。**git 自己合好的也逐檔看**：兩邊各自的增刪行，合好的那一筆都要在。一條線把舊模組搬走、另一條線還在改舊位置的，改動照新位置寫回去。
合完**只跑**：\`python ${TOOLS}/undef_scan.py tianxia server.py\` 0 個；\`python -m pytest -q -n 4 tests/core/test_feature_boundaries.py tests/core/test_contract_core.py tests/core/test_contract_features.py\` 過。紅了修（合起來才壞的一個 commit）。**整套、比對不跑**：下一關一次跑。
推 \`git push origin HEAD:${WAVE_BRANCH}\`。回報 head、撞了什麼怎麼解、跑的結果。解不了才寫 stopped。`, { label: `merge:wave${WAVE}`, phase: 'Merge', schema: MERGE_SCHEMA, isolation: 'worktree', model: 'opus' })
if (!merged || halted_word(merged.stopped)) return { wave: WAVE, built, merged, stopped: merged ? merged.stopped : '合併沒有結果' }
if (A.stop_after_merge) return { wave: WAVE, built, merged, head: sha_of(merged.head), stopped: '' }  // 企劃者 11/07「不要卡著」：合好就開下一波，閘門疊著跑

let gateHead = sha_of(merged.head), docsPass = null
const docsRun = () => agent(`你是《天下大勢》PM 派的文件子代理，第 ${WAVE} 波合好之後、閘門之前做一輪文件。
${COMMON}
分支：明確 fetch ${WAVE_BRANCH}；\`git switch -c ${WAVE_BRANCH}-docs origin/${WAVE_BRANCH}\`（同名已存在就加 -work），做完快轉推回 \`${WAVE_BRANCH}\`。暫存 ${SP}\\wave${WAVE}\\docs\\。
${A.after_merge}
回報 head、做了哪些（fixed）、發現不該做或對不上的（rejected）、跑的結果（tests）。只有企劃者能定的才寫 stopped。`, { label: `docs:wave${WAVE}`, phase: 'Merge', schema: FIX_SCHEMA, isolation: 'worktree', model: 'opus' })
const docsPromise = (A.after_merge && A.docs_alongside) ? docsRun() : null  // 只動文件，跟閘門同時跑，閘門不驗它（企劃者 11/07）
if (A.after_merge && !A.docs_alongside) {  // 合完、閘門之前的文件輪（PM 寫；閘門要驗到它）
  docsPass = await docsRun()
  if (!docsPass || halted_word(docsPass.stopped)) return { wave: WAVE, built, merged, docsPass, stopped: docsPass ? docsPass.stopped : '文件輪沒有結果' }
  if (docsPass.head) gateHead = sha_of(docsPass.head)
}

const PM_TOOLS = A.pm_tools || 'C:/Ray/專案/天下大勢/.claude/worktrees/pm-1103/docs/superpowers/pm-workflows'  // 主要 clone 在 main 上，工具在 PM 的工作樹
const runGate = (head, label) => agent(`你只做一件事：跑一次閘門腳本，等它跑完，回報結果。不改任何檔、不推任何東西、不修任何東西。
1. 用 PowerShell 分離啟動（不要 tee、不要前景跑，它要 15～30 分鐘；先建 ${SP}\\wave${WAVE}\\ 這個資料夾）：
\`Start-Process -WindowStyle Hidden -FilePath "${PY}" -ArgumentList '${PM_TOOLS}/wave_gate.py','--base','${GATE_BASE}','--head','${head}','--name','wave${WAVE}' -WorkingDirectory "${ROOT}" -RedirectStandardOutput "${SP}\\wave${WAVE}\\gate.out" -RedirectStandardError "${SP}\\wave${WAVE}\\gate.err"\`
2. 重複跑 \`& "${PY}" "${PM_TOOLS}/wait_file.py" "${ROOT}\\.local\\wave_gate\\${head.slice(0, 8)}\\done" 570\`（工具逾時設 600000），直到印出 done。不要做別的事，也不要讀別的檔。超過 90 分鐘還沒好，看 gate.out 與 gate.err 的最後 20 行，當成紅回報。
3. 讀 \`${ROOT}\\.local\\wave_gate\\${head.slice(0, 8)}\\result.json\`，全文放進 result，green 照裡面的 green。`, { label, phase: 'Gate', schema: GATE_SCHEMA, model: 'sonnet' })

phase('Gate')
const gatePromise = runGate(gateHead, `gate:wave${WAVE}`)

phase('Review')
const reviewOf = (l) => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推）。審**第 ${WAVE} 波的線 ${l.line}**：\`${l.branch}\` ${l.head}，base ${l.base}。批：
${l.done.map(d => `- 第 ${d.n} 批：${d.title}\n  開發回報：${String(d.report).slice(0, 1800)}\n  開發自己定的：${(d.decided || []).join('；').slice(0, 1200)}`).join('\n')}
${COMMON}
**這一關不跑測試、不跑比對、不做突變**：閘門同時在跑所有軌與整套。你看閘門看不到的。
1. 先跑機械報告（明確 fetch 這條分支）：\`& "${PY}" "${PM_TOOLS}/moved_report.py" ${l.base} ${l.head}\`（用 PowerShell）。語法樹一樣的不必再看；**有差的每一行都看**：是機械改寫（self 換 ctx、經服務叫、換 import 路徑）還是行為改了。
2. 對${ROUND2 ? `第二輪總表 ${MASTER} 第 ${l.done.map(d => d.n).join('、')} 批那幾節（數字會過時，以現行程式為準）` : `總表 ${MASTER} 第 ${l.done.map(d => d.n).join('、')} 列與附錄甲丙`}：有沒有漏搬、搬錯包；委派都是一行；別名是同一個模組物件；包只 import 核心、共用規則層與標過渡的舊模組；核心批的順序表跟原本的呼叫順序一樣（順序就是行為）；\`PlayerState\` 欄位認領；前綴與 \`bots.py\`；有沒有測試被改了斷言（只准改路徑與 import）；有沒有碰到派工單沒寫的 \`web/\`、資料庫結構、CLAUDE.md、手冊、總表。
3. 這條線新加的情境真的走到了嗎（讀程式）；monkeypatch 敏感的路照舊打得到嗎。
每一條發現寫 severity（blocker＝合了會壞、或行為變了、或違反規矩；should；nit）、在哪裡、證據。沒有就回空陣列，不要湊。`, { label: `review:${l.line}`, phase: 'Review', schema: REVIEW_SCHEMA, model: 'sonnet' })  // 企劃者 11/08：測試與審查派 Sonnet
const lensOf = (x) => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推），**專門挑錯**：預設這一波在你這個鏡頭下有問題，你的工作是找出來或親手證明沒有。審第 ${WAVE} 波合好的結果 \`${WAVE_BRANCH}\` ${gateHead}，對 base ${MERGE_BASE}（明確 fetch）。
${COMMON}
**這一關不跑整套、不跑 same_behavior compare**：閘門同時在跑。可以跑小腳本、讀語法樹、用 \`& "${PY}" "${PM_TOOLS}/moved_report.py" ${MERGE_BASE} ${gateHead}\` 看機械報告；要跑程式就解到 ${SP}\\wave${WAVE}\\lens-${x.key}\\，用完刪。
**你的鏡頭**：${x.text}
每一條發現寫 severity（blocker＝合了會壞、或行為變了；should；nit）、在哪裡、證據（指令與輸出，或兩份程式並排的行）。**沒有證據不要寫**；沒有就回空陣列，summary 寫你實際驗了哪些、怎麼驗的。`, { label: `lens:${x.key}`, phase: 'Review', schema: REVIEW_SCHEMA, model: 'sonnet' })
const checkPromise = !A.web_check ? null : agent(`你是《天下大勢》的 QA 子代理，驗**第 ${WAVE} 波動到的畫面**（波次模式：一波一次，企劃者 11/06）。照 .claude/skills/tianxia-qa/SKILL.md 在實機看：head ${gateHead} 對 base ${GATE_BASE}，同一個局面並排截圖（375 淺、375 深、1280）、逐像素比、主控台 0 錯誤、網路沒有 4xx／5xx。**不重跑測試、不比資料庫。**
${COMMON}
埠 ${A.web_check.ports}，分主機名（127.0.0.1 對 localhost）。要看的：${A.web_check.steps}
回報 same、走了哪些步驟、差異、截圖路徑。收的時候伺服器 taskkill /T、刪暫存大檔。`, { label: `check:wave${WAVE}`, phase: 'Check', schema: { type: 'object', properties: { same: { type: 'boolean' }, steps: { type: 'string' }, diffs: { type: 'array', items: { type: 'string' } }, report: { type: 'string' } }, required: ['same', 'steps', 'diffs', 'report'] }, model: 'sonnet' })
const reviewsRaw = await parallel([...built.map(l => () => reviewOf(l)), ...(A.extra_lenses || []).map(x => () => lensOf(x))])
const reviews = reviewsRaw.filter(Boolean)
const gate = await gatePromise
const check = checkPromise ? await checkPromise : null
if (docsPromise) docsPass = await docsPromise
const findings = [...reviews.flatMap(r => r.findings || []).filter(f => f.severity !== 'nit'), ...(check && !check.same ? (check.diffs || []).map(d => ({ title: '實機畫面有差', severity: 'blocker', where: '', evidence: d })) : [])]

let head = (docsPass && docsPass.head) ? sha_of(docsPass.head) : gateHead, fix = null
if (!gate || !gate.green || findings.length) {
  phase('Fix')
  fix = await agent(`你是《天下大勢》的開發子代理，修第 ${WAVE} 波合起來之後的問題。
${COMMON}
${WAVE_RULE}
分支：明確 fetch ${WAVE_BRANCH}；\`git switch -c ${WAVE_BRANCH}-fix origin/${WAVE_BRANCH}\`（同名已存在就加 -work），修完快轉推回 \`${WAVE_BRANCH}\`。埠 ${FIX_PORT}，暫存 ${SP}\\wave${WAVE}\\fix\\。
這一波的線：
${lineList}
**閘門**（base ${GATE_BASE}、head ${gateHead}；完整輸出在 ${ROOT}\\.local\\wave_gate\\${gateHead.slice(0, 8)}\\）：
${gate ? gate.result : '閘門沒有結果：先用同樣的參數跑一次 wave_gate.py'}
**審查的發現**：
${JSON.stringify(findings, null, 1)}
**企劃者 11/07「加快分拆，不要卡著」：這一關不超過 60 分鐘，到了就把修好的推上去、交。** 順序：閘門紅的 → blocker → 一兩行能修好的 should；其餘 should 不修，寫進 rejected，開頭寫「留給下一波：」。**工具（scripts/webqa、scripts/sb、wave_gate）的誤報不修工具**，寫進 rejected；工具整個跑不起來（結束碼 2）才修。不重跑全量網頁比對、不跑 selftest。
做法：一條一個 commit、修一條推一次。比對紅了先用那一軌（\`same_behavior compare --tracks <軌>\`）對每條線的 head 比，找到是哪一條線、哪一批；是腳本的問題（情境走的路兩邊不同）就修腳本、兩邊重比。測試紅了照「合併丟東西」「只是路徑」「真的行為變了」分類：**不要為了綠改行為，也不要改斷言的意思**。修完**只重跑修到的**：那幾條測試、那幾軌，改了 \`tianxia/\` 再跑 \`python ${TOOLS}/undef_scan.py tianxia server.py\` 與邊界、契約。不跑整套（PM 最後再跑一次）。屬實的才修，不屬實的寫進 rejected 附證據。nit 不修。只有企劃者能定的才寫 stopped。
回報 head、修了哪些、駁回哪些、重跑的結果。`, { label: `fix:wave${WAVE}`, phase: 'Fix', schema: FIX_SCHEMA, isolation: 'worktree', model: 'opus' })
  if (fix && fix.head) head = sha_of(fix.head)
}

return { wave: WAVE, branch: WAVE_BRANCH, merge_base: MERGE_BASE, head, merged, docsPass, gate, reviews, check, fix, nits: reviews.flatMap(r => (r.findings || []).filter(f => f.severity === 'nit')),
  batches: built.flatMap(l => l.done.map(d => ({ n: d.n, title: d.title, line: l.line, head: d.head, decided: d.decided, leftovers: d.leftovers, docs: d.docs, tests: d.tests }))) }
