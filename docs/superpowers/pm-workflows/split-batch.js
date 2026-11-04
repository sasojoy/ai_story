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

const A = args || {}
const need = k => { if (A[k] === undefined || A[k] === null || A[k] === '') throw new Error('pass args.' + k); return A[k] }
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
- **不准改共用 clone 的 git 設定**：中文路徑印成八進位時，用單次的 \`git -c core.quotepath=off ...\`，不要 \`git config\`。
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
- **拆分在 \`split/trunk\` 上做**（企劃者 11/04：錨點 tag \`split-anchor-20261104\`）。\`develop\` 是別人在開發的線，它後來的提交不管、不要合進來，雲端的線也不用查；全面分拆完 PM 才追。
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
分支：明確 fetch ${FEAT}（PM 已開在 split/trunk ${BASE}；不是的話停下來回報）；\`git switch -c ${DEV} origin/${FEAT}\`（同名已存在就加 -work），推 \`git push origin HEAD:${DEV}\`。不碰 ${FEAT}、develop、main，PM 合。埠 ${P.dev}、${HOST}.localhost；暫存 ${SP}\\${SCRATCH}\\。

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

const CHECKP = (head) => (WEB || A.full_qa) ? `你是《天下大勢》的 QA 子代理，驗**全部拆包第 ${N} 批：${TITLE}**（${DEV} ${head}）。${WEB ? '這一批動到 web/' : '這一批動到 server 的路由分派（web/ 沒動）'}，照 .claude/skills/tianxia-qa/SKILL.md 做**完整實機 QA**：HEAD 對 BASE（origin/${FEAT} ${BASE}）同一個局面並排截圖（375 淺、375 深、1280）、逐像素比、主控台 0 錯誤、網路沒有 4xx／5xx、資料庫逐表比。
${COMMON}
做法照 ${SP}\\b12-chk\\s\\ 的 serve.py、drive.py（第 12 批那一版，最新）（時鐘凍住、固定亂數、排程不開），複製到 ${SP}\\${SCRATCH}-qa\\ 改著用；兩份 worktree 的 .local/webpush_vapid.pem 用同一把。埠 ${P.head}（HEAD，${HOST}qa.localhost）、${P.base}（BASE，127.0.0.1）。要點的：${STEPS}
有問題寫成回饋單 ${FB}（docs/superpowers/feedback/試玩回饋.md）；報告、回饋單、挑過的並排圖推到 ${QA}（從 origin/${DEV} ${head} 開）。沒有問題就寫「沒有問題」。收的時候伺服器 taskkill /T、刪暫存大檔。
回報：same、走了哪些步驟、差異、FB、截圖路徑、qa 分支 head。` : `你是《天下大勢》的驗收子代理，驗**全部拆包第 ${N} 批：${TITLE}**（${DEV} ${head}）。純搬、web/ 一個字沒動的批，實機 QA 照總表 5.0 做「兩台真伺服器逐位元組比」：網頁檔沒變、伺服器回的位元組一樣，畫面就一定一樣；只拍三張圖做 sanity。
${COMMON}
開發與審查已經跑過測試與 same_behavior：**不要重跑**。
做法：照 ${SP}\\b12-chk\\s\\ 的 serve.py、drive.py（第 12 批那一版，最新）（時鐘凍住只在 /__qa/clock 往前推、每次進行動鎖重設 game.rng 與 random、沒給種子的 Random 用固定種子、世界排程執行緒不開、/__qa/edit 擺位），複製到 ${SP}\\${SCRATCH}-chk\\ 改著用。明確 fetch ${DEV}、${FEAT}；開兩份 detached worktree：HEAD＝${head}、BASE＝origin/${FEAT}（${BASE}）；兩份的 .local/webpush_vapid.pem 用同一把。兩台伺服器開在埠 ${P.head}（HEAD，${HOST}chk.localhost）與 ${P.base}（BASE，127.0.0.1），season21（再加 week7 走一遍主要的幾步）：用真的 HTTP（帶 cookie）照同一串步驟打兩台——${STEPS}——**每一個回應的狀態碼與內容逐位元組比**（凍住時鐘之後帶時間戳的欄位應該一樣；真的不一樣的列出來分清楚是雜訊還是程式）；收場後兩個資料庫逐表比。再用 headless 瀏覽器各拍 375×812 淺色的三張相關畫面並排。收的時候 taskkill /T、刪兩份 worktree 與暫存大檔。
回報：same（全部一樣才是 true）、走了哪些步驟、差異清單、截圖路徑。有問題寫成回饋單 ${FB}（docs/superpowers/feedback/試玩回饋.md）並推到 ${QA}（從 origin/${DEV} 開；只放報告、回饋單、圖）；沒有問題就不必開 qa 分支。`

phase('Build')
const dev = await agent(DEVP, { label: `dev:b${N}`, phase: 'Build', schema: DEV_SCHEMA, isolation: 'worktree' })
if (!dev) return { dev: null }
if (dev.stopped) return { dev, stopped: dev.stopped }
phase('Review')
const devText = `開發回報：\n${dev.report}\nsame_behavior：${dev.same_behavior}\n驗收：${dev.acceptance}`
const reviews = await parallel(LENSES.map(l => () => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推）。\n${COMMON}\n審 ${DEV} 的 ${dev.head}（明確 fetch），base 是 ${FEAT} ${BASE}。這一批：${TITLE}。\n${devText}\n你的鏡頭：${l.text}\n每一條發現寫 severity（blocker＝合了會壞、或行為變了、或違反手冊／批次表／總表／PM 定的；should；nit）、在哪裡、證據（指令與輸出）。沒有就回空陣列，不要湊。`, { label: `review:b${N}-${l.key}`, phase: 'Review', schema: REVIEW_SCHEMA })))
const findings = reviews.filter(Boolean).flatMap(r => r.findings || [])
let head = dev.head, fix = null
if (findings.some(f => f.severity !== 'nit')) {
  phase('Fix')
  fix = await agent(`你是《天下大勢》的開發子代理，修 ${DEV}（現在 ${dev.head}）上審查員的發現。\n${COMMON}\n分支：明確 fetch，\`git switch -c ${DEV}-fix origin/${DEV}\`（同名已存在就加 -work），推回 origin/${DEV}（快轉）。每修一條一個 commit、修一條推一次；先寫會紅的測試（或讓 same_behavior 先抓到）再修；屬實的才修，不屬實的寫進 rejected 附證據；**nit 不修**，寫進計畫的審查那一節就好（PM 11/04：額度是拆完的瓶頸）。修完重跑 same_behavior 的 base 對 head（所有軌、五種）與相關測試。要開伺服器用埠 ${P.fix}、${HOST}fix.localhost。暫存 ${SP}\\${SCRATCH}-fix\\，做完刪大檔。\n開發回報（摘要）：${dev.report.slice(0, 5000)}\n發現：\n${JSON.stringify(findings, null, 1)}\n審查摘要：${reviews.filter(Boolean).map(r => r.summary).join('\n---\n')}\n回報 head、修了哪些、駁回哪些、測試、學到的。`, { label: `fix:b${N}`, phase: 'Fix', schema: FIX_SCHEMA })
  if (fix && fix.head) head = fix.head
}
phase('Check')
const check = await agent(CHECKP(head), { label: `check:b${N}`, phase: 'Check', schema: CHECK_SCHEMA })
return { n: N, dev, reviews, fix, head, check }
