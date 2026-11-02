export const meta = {
  name: 'split-batch15-shared-rules',
  description: 'Split batch 15: register the shared rule layer (registry.SHARED) and the shared services, no code moved, behaviour proven unchanged on every track; three review lenses, one fix round, then a two-server byte check',
  phases: [
    { title: 'Build', detail: 'plan, rerun every track, register, prove' },
    { title: 'Review', detail: 'proof honesty; registration correctness; regressions and test_for' },
    { title: 'Fix', detail: 'one round on findings' },
    { title: 'Check', detail: 'two real servers, every package touched, HTTP bytes and screenshots' },
  ],
}

const ROOT = 'C:\\Ray\\專案\\天下大勢'
const SP = 'C:\\Users\\ray61\\AppData\\Local\\Temp\\claude\\C--Ray--------\\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\\scratchpad'
const PY = 'C:/Ray/專案/天下大勢/.venv/Scripts/python.exe'
const BOOK = 'docs/superpowers/specs/2026-10-30-開發模式-design.md'
const BATCH = 'docs/superpowers/plans/2026-10-31-主動搬六包-批次.md'
const SURVEY = 'docs/superpowers/plans/2026-10-31-主動搬六包-調查'
const PLAN1 = 'docs/superpowers/plans/2026-10-31-出陣包-第1批.md'
const MASTER = SP + '\\split\\全部拆包-總表.md'
const BASE = args && args.base ? args.base : (() => { throw new Error('pass args.base') })()

const COMMON = `
共通的規矩（這台機器）：
- repo ${ROOT}。這份 clone 的 \`git fetch origin\` 不更新 dev/*、feature/*、qa/*、develop：一律明確 fetch（例 \`git fetch origin +refs/heads/feature/battle:refs/remotes/origin/feature/battle\`）。推完明確 fetch 再 \`git merge-base --is-ancestor HEAD origin/<分支>\` 確認，也看 \`git ls-remote\`。**每做完一個 Task 就推一次**。
- **在 Git Bash 裡給 git 的路徑寫 Windows 格式**（\`C:/Users/...\`），不要寫 \`/c/Users/...\`。scratch 資料夾裡的 .py 不要取標準函式庫的名字。隔離工作樹裡 Bash 可能擋 venv 的 python、含變數的 cp/tar、cd 再接 git：python 用 PowerShell 跑 ${PY}（PowerShell 5.1 會把沒有 BOM 的 UTF-8 .ps1 當 ANSI 讀，含中文路徑的指令直接寫在指令裡）；改檔腳本用 Write 工具寫成 .py 再跑或直接用 Edit（Bash heredoc 會吃掉反斜線；Git Bash 的 \`python - <<EOF\` 會卡住）；Write 寫出 LF，工作樹是 CRLF，寫完自己轉，提交前 \`git cat-file blob\` 確認 git 裡是 LF。PowerShell 5.1 傳含雙引號的 commit 訊息會壞：訊息寫成檔案用 \`git commit -F\`。commit 訊息英文，結尾一行 \`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\`。
- 規矩：開發規範手冊 ${BOOK}（第三節是包的規矩，**第十五節是落地補註、跟原文不同時照它**）；批次表 ${BATCH}（**第二節「每一批都照這些做」逐條照做**；第一節開頭「10/31 晚起改成並行」那一條也照做）；全部拆完的總表 docs/superpowers/plans/2026-10-31-全部拆包-總表.md（以 repo 裡的為準）。技能用 Read 直接讀 .claude/skills/<名字>/SKILL.md（開發看 tianxia-dev）。**技能檔、CLAUDE.md、手冊、批次表只有 PM 改**——學到的寫在回報。
- 暫存檔放 ${SP} 底下你自己的子資料夾（下面寫明），TIANXIA_DB 也指到那裡；不碰這份 clone 的 saves/；不要刪 .local/nightly/checkout。
- 測試：pytest 一律 \`-n 4\`；\`scripts/test_for.py --base origin/feature/core-shared\`。slow 不自動跟，要跑加 \`--slow\` 或 \`-m "slow or not slow"\`。不跑整套。
- 本機伺服器：只用給你的埠與 <名字>.localhost；\`-u\` 分離啟動、記 PID；模型網址指到 127.0.0.1:9，絕不打 11434；跑模擬前 patch \`ollama_client.from_config\`；收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（develop 現在第 9 版）不改。
- 不開子代理、不開工作流程。任何畫面、輸出不能透露誰是假人；這一批不該有新字。做完就停；回報用繁體中文。
- **核心批，但這一次跟第 7 批並行**（PM 11/01 定：這一批只登記、不搬程式）：改的是名單、服務清單，每一包都踩得到，所以每一包的情境都要重比。
- **同時跑的線**（PM 11/01 接手後定）：第 7 批（決戰「打」b，\`dev/battle-3\`）與第 15 批（共用規則層登記，\`dev/core-shared-1\`）並行——第 15 批只登記、不搬程式，衝突是增量的；共用登記檔（邊界清單、\`services.py\`、\`registry.py\`、FEATURES、same_behavior、\`aliases()\`）你加的每一筆都集中在自己那一段（\`# battle\`／\`# shared\`）後面，不穿插在別人的行之間。後合的那一條，PM 會先合 develop 再重比。
- **第 11 批（核心收接縫）已合進 develop**：\`tianxia/core/features.py\` 多了接縫掛鉤與兩個宣告（\`Shop\`、\`Verb\`）；手冊第十五節「第 11 批的 PM 認定」：接縫掛鉤不看包的 \`enabled\`、給選項的照問。**原位該接的照第 11 批的寫法接上掛鉤，不要再新增 \`GAME_DIRECT\`**（真的接不了寫理由）。
- 不要碰：web/、輿圖（feature/map-view）、鐵匠鋪（feature/smithing-flow）、戰記（tale.py、server 的 TALES 與 narrate_*）、資料庫結構（第 9 版）、技能檔、CLAUDE.md、手冊、批次表（只有 PM 改；學到的寫在回報）。
`

const DEV_SCHEMA = {
  type: 'object',
  properties: {
    branch: { type: 'string' }, head: { type: 'string' }, stopped: { type: 'string', description: '若因雲端戰記線停下，寫原因；否則空字串' },
    commits: { type: 'array', items: { type: 'string' } },
    same_behavior: { type: 'string' },
    acceptance: { type: 'string' },
    tests: { type: 'string' },
    learned: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
    report: { type: 'string' },
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
  properties: {
    same: { type: 'boolean' }, steps: { type: 'string' }, diffs: { type: 'array', items: { type: 'string' } },
    screenshots: { type: 'string' }, report: { type: 'string' },
  },
  required: ['same', 'steps', 'diffs', 'report'],
}

const DEV = `你是《天下大勢》的開發子代理，做**全部拆包的第 15 批：共用規則層登記**（總表 ${MASTER} 第 3.3 節甲表第 15 列）。第 17 批起每一包都等這一批：各包 import 的對象從一開始就合法，不必每批記一堆過渡。這一批**只登記、不搬程式**，承諾是行為一個字不變。
${COMMON}
先讀：
- 手冊 ${BOOK} 第三節與第十五節，含第 11 批 PM 加的兩條：接縫掛鉤；\`registry.SHARED\` 的格式是模組名 → 一句理由。
- 總表（repo 裡的 \`docs/superpowers/plans/2026-10-31-全部拆包-總表.md\`）第 3.3 節甲表第 15 列（整格）、第六節第 4、5 條、附錄甲（歸屬裁定）、附錄丙（補裁定，機器可讀）。
- 第 11 批的計畫 \`docs/superpowers/plans/2026-11-01-核心收接縫.md\`：照它的格式寫，第五、六、七節是它量到的與合併紀錄。
- \`tianxia/core/registry.py\`、\`services.py\`、\`tests/core/test_feature_boundaries.py\`、契約測試。
用 \`grep -n '^#'\` 看大綱，只讀相關的節。
分支：明確 fetch develop（現在是 ${BASE}）。PM 開了 \`feature/core-shared\`，跟 develop 同一筆；沒有的話你開：\`git push origin ${BASE}:refs/heads/feature/core-shared\`。然後 \`git switch -c dev/core-shared-1 origin/feature/core-shared\`（同名已存在就加 -work），推 \`git push origin HEAD:dev/core-shared-1\`。不碰 develop、main，PM 合。埠 8195、shared1.localhost（審查重跑用 8196）；暫存 ${SP}\\shared1\\。

**要做的**（照總表第 15 列）：
- **\`registry.SHARED\` 登記共用規則層**：總表列了 67 個。
  - 戰鬥引擎 9 個。
  - 武學與裝備的規則 25 個，含 economy、skillview、shopview。
  - 世界模型第一批 11 個：timetable、front_lines、push、allied、wins、relations、deeds、seats、factions、week_unlock、roster。
  - 地盤與攻城：territory、conquest、siege。
  - 其餘：clinic、ranger、precise、renown、speech、jianfa_numbers、events、outcomes、marks、tiers、模型服務 6 個（ollama_client、power_save、zh、event_llm、narration、flavor）、playlog、leaderboard、rumor_view、prologue。
  - 開工時照現行程式重數；總表之後有模組改名或拿掉的，照現行程式。
  - 每一個寫一句理由：誰在用、為什麼在共用層。
- **\`world.py\` 不收**：它 import 宴客、擂台、懸賞、月旦評，第 25 批改成世界層掛鉤之後才收。
- **模組 import 了包的**（例：leaderboard、tiers 讀擂台的稱號）：先改成查詢服務，或者先不收；寫明是哪一種。
- **邊界測試補上第 11 批沒守到的那一條**：SHARED 裡的模組只 import 核心本體與同一層，不 import 包。
- **\`services.py\` 補上五區量好的共用服務**：地盤、回體丹、醫館、本人對本人、操練的得、名聲、店面殼、修練頁紀錄、線索服務，約 90 個方法。每一個標主人；格式照第 11 批之後的樣子；第 6 批 siege 那三個名字的寫法也一起定。
- **\`test_for\`**：改 SHARED 裡的模組，挑法照手冊 4.3。共用規則層算哪一種、挑哪些，寫進計畫，前後各挑到幾條。

做法：
- 先照 superpowers:writing-plans 寫計畫 \`docs/superpowers/plans/2026-11-01-共用規則層登記.md\`。第一節「現行程式對照」：每一個要登記的模組，誰 import 它、它 import 誰、會不會碰到包。
- 再一個 Task 一個 commit 做（superpowers:executing-plans，不開子代理）：
  - **Task 1**：same_behavior 在 base 上跑一次全部（四軌加 explore），記雜湊。這一批原則上不加情境；改成查詢服務的那幾處要有情境看得出來。commit、推。
  - **Task 2～**：登記與服務清單，一區一個 Task；邊界與契約測試跟著改。commit、推。
  - **最後一個 Task**：證明與驗收。
    - same_behavior base（${BASE}）對 head：四軌加 explore，五種設定，整段、半舊半新、假人全部逐位元組一樣。
    - 量：SHARED 幾個；包 → 舊模組的過渡處數從幾處降到幾處，因為 import 共用層不再算過渡；services 幾個名字；改一個 SHARED 模組 test_for 挑到幾條。
    - 寫進計畫第五節；導覽 \`docs/guide/核心與存檔.md\` 跟著改。commit、推。
- 測試：核心測試＋煙霧每個 Task 一次；每一包的 tests 含 slow，最後一次；契約與邊界；相關的 slow 加 \`-m "slow or not slow" -n 4\`。不跑整套。
回報：head、commits、same_behavior、驗收數字、測試、學到的、要 PM 定的。碰到只有企劃者能定的，stopped 寫原因、停下來。`

const LENSES = [
  { key: 'proof', text: `**行為不變的證明誠不誠實**：
- 這一批只登記，加上幾處改成查詢服務。改成查詢服務的那幾處，有沒有情境看得出來？做一個單點突變（例：擂台稱號的查詢服務回空的），看 compare 抓不抓得到。
- **自己重跑一次**：在 ${SP}\\shared1-rev-proof\\ 開兩份 detached worktree，一份 ${BASE}、一份開發的 head（Windows 路徑）。season21 與 week7 各比一次 base 對 head，四軌加 explore-compare。
- 用完 \`git worktree remove\`。` },
  { key: 'boundary', text: `**登記得對不對**：
- SHARED 裡每一個模組自己查一次：
  - 它真的不 import 任何包。
  - 理由那一句對得上誰在用。
  - 總表列了、卻沒登記的，寫明為什麼。
- \`world.py\` 沒收。
- import 了包的那幾個，是改成查詢服務，還是先不收，寫得清不清楚。
- 邊界測試守住「SHARED 只 import 核心本體與同一層」。
- services 裡每一個名字都標了主人。
- 有沒有碰到 web/、戰記、輿圖、鐵匠鋪、資料庫結構、技能檔、CLAUDE.md、手冊、批次表。` },
  { key: 'regress', text: `**回歸與測試**：自己在 ${SP}\\shared1-rev-reg\\ 的 detached worktree 跑。
- 測試：每一包的 tests 含 slow；核心、契約、邊界；相關的 slow，\`-m "slow or not slow" -n 4\`。記時間。
- \`test_for\`：
  - 改一個 SHARED 模組、改一包任一檔、改 engine 一個委派，各挑到幾條？該挑的有沒有挑到？
  - 跟 develop 現在的挑法比，有沒有哪一種變成挑不到。
- 有沒有測試被改了斷言：只准改路徑與 import。` },
]

const CHECK = (head) => `你是《天下大勢》的驗收子代理，驗**全部拆包第 15 批：共用規則層登記**（dev/core-shared-1 ${head}）。**PM 10/31 晚為了趕進度，純搬、web/ 一個字沒動的批，實機 QA 改成這一個「兩台真伺服器逐位元組比」**：網頁檔沒變、伺服器回的位元組一樣，畫面就一定一樣；你只拍三張圖做 sanity。
${COMMON}
開發與審查已經跑過測試與 same_behavior：**不要重跑**。
做法：照 ${SP}\\qa-sortie1\\s\\ 的 serve.py（時鐘凍住只在 /__qa/clock 往前推、每次進行動鎖重設 game.rng 與 random、沒給種子的 Random 用固定種子、世界排程執行緒不開、/__qa/edit 擺位），複製到 ${SP}\\chk-shared1\\ 改著用。明確 fetch dev/core-shared-1、feature/core-shared；開兩份 detached worktree：HEAD＝${head}、BASE＝origin/feature/core-shared（${BASE}）；兩份的 .local/webpush_vapid.pem 用同一把。兩台伺服器分別開在埠 8197（HEAD，shared1chk.localhost）與 8198（BASE，127.0.0.1），season21：用真的 HTTP（requests 或 curl，帶 cookie）照同一串步驟打兩台（核心批：四種人各做幾樣每一包的事，出陣、探索一趟、酒肆、決戰與攻城、商城、宴客，讓每一個掛鉤都走到）——註冊四個帳號（官軍、黃巾、散人、豪強各一）、管理者開季、開決戰、集結、出招、放手一搏（模型擋著，走退回）、推時鐘到收場、每個人 /api/main、/api/reports、/api/reports?id=——**每一個回應的狀態碼與內容逐位元組比**（帶時間戳的欄位凍住時鐘之後應該一樣；真的不一樣的列出來分清楚是雜訊還是程式）；收場後兩個資料庫逐表比。再用 headless 瀏覽器各拍 375×812 淺色的江湖頁、決戰頁、戰報頁三張並排。收的時候 taskkill /T。
回報：same（全部一樣才是 true）、走了哪些步驟、差異清單、截圖路徑。有問題寫成回饋單 FB-9180～FB-9189（docs/superpowers/feedback/試玩回饋.md）並推到 qa/core-shared-1（從 origin/dev/core-shared-1 開；只放報告、回饋單、圖）；沒有問題就不必開 qa 分支。`

phase('Build')
const dev = await agent(DEV, { label: 'dev:core-shared-1', phase: 'Build', schema: DEV_SCHEMA, isolation: 'worktree' })
if (!dev) return { dev: null }
if (dev.stopped) return { dev, stopped: dev.stopped }
phase('Review')
const devText = `開發回報：\n${dev.report}\nsame_behavior：${dev.same_behavior}\n驗收：${dev.acceptance}`
const reviews = await parallel(LENSES.map(l => () => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推）。\n${COMMON}\n審 dev/core-shared-1 的 ${dev.head}（明確 fetch），base 是 feature/core-shared ${BASE}。\n${devText}\n你的鏡頭：${l.text}\n每一條發現寫 severity（blocker＝合了會壞、或行為變了、或違反手冊／批次表／PM 定的；should；nit）、在哪裡、證據（指令與輸出）。沒有就回空陣列，不要湊。`, { label: `review:core-shared-1-${l.key}`, phase: 'Review', schema: REVIEW_SCHEMA })))
const findings = reviews.filter(Boolean).flatMap(r => r.findings || [])
let head = dev.head, fix = null
if (findings.length) {
  phase('Fix')
  fix = await agent(`你是《天下大勢》的開發子代理，修 dev/core-shared-1（現在 ${dev.head}）上三位審查員的發現。\n${COMMON}\n分支：明確 fetch，\`git switch -c dev/core-shared-1-fix origin/dev/core-shared-1\`（同名已存在就加 -work），推回 origin/dev/core-shared-1（快轉）。每修一條一個 commit、修一條推一次；先寫會紅的測試（或讓 same_behavior 先抓到）再修；屬實的才修，不屬實的寫進 rejected 附證據；nit 能順手就修。修完重跑 same_behavior 的 base 對 head（五種）與相關測試。要開伺服器用埠 8196、shared1fix.localhost（審查已經收了）。暫存 ${SP}\\shared1-fix\\。\n開發回報（摘要）：${dev.report.slice(0, 5000)}\n發現：\n${JSON.stringify(findings, null, 1)}\n審查摘要：${reviews.filter(Boolean).map(r => r.summary).join('\n---\n')}\n回報 head、修了哪些、駁回哪些、測試、學到的。`, { label: 'fix:core-shared-1', phase: 'Fix', schema: FIX_SCHEMA })
  if (fix && fix.head) head = fix.head
}
phase('Check')
const check = await agent(CHECK(head), { label: 'check:core-shared-1', phase: 'Check', schema: CHECK_SCHEMA })
return { dev, reviews, fix, head, check }
