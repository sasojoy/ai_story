export const meta = {
  name: 'split-batch7-battle-fight-b',
  description: 'Split batch 7: move the showdown muster, enlist and escort picking (fight half, part b) into tianxia/features/battle and take the battle prefix, behaviour proven unchanged; three review lenses, one fix round, then a two-server byte check',
  phases: [
    { title: 'Build', detail: 'plan, core prep, move, prove' },
    { title: 'Review', detail: 'proof honesty; prefix and bots; boundary and regressions' },
    { title: 'Fix', detail: 'one round on findings' },
    { title: 'Check', detail: 'two real servers, same seeded scenario, HTTP bytes and three screenshots' },
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
- 規矩：開發規範手冊 ${BOOK}（第三節是包的規矩，**第十五節是落地補註、跟原文不同時照它**）；批次表 ${BATCH}（**第二節「每一批都照這些做」逐條照做**；第一節開頭「10/31 晚起改成並行」那一條也照做）；全部拆完的總表草稿 ${MASTER}（第 3.2 節第 5 列、第六節）。技能用 Read 直接讀 .claude/skills/<名字>/SKILL.md（開發看 tianxia-dev）。**技能檔、CLAUDE.md、手冊、批次表只有 PM 改**——學到的寫在回報。
- 暫存檔放 ${SP} 底下你自己的子資料夾（下面寫明），TIANXIA_DB 也指到那裡；不碰這份 clone 的 saves/；不要刪 .local/nightly/checkout。
- 測試：pytest 一律 \`-n 4\`；\`scripts/test_for.py --base origin/feature/battle\`。slow 不自動跟，要跑加 \`--slow\` 或 \`-m "slow or not slow"\`。不跑整套。
- 本機伺服器：只用給你的埠與 <名字>.localhost；\`-u\` 分離啟動、記 PID；模型網址指到 127.0.0.1:9，絕不打 11434；跑模擬前 patch \`ollama_client.from_config\`；收的時候 \`taskkill /PID <pid> /T /F\`。
- **不下載、不安裝任何東西**。絕不碰 7861、C:\\Ray\\tianxia-play、線上資料庫、Tunnel、server_push.py；資料庫結構（develop 現在第 9 版）不改。
- 不要碰：web/（這一批不切網頁；main.js 決戰那一段照舊）、輿圖、鐵匠鋪（feature/smithing-flow）、**戰記**（tale.py、server 的 TALES、narrate_battle、narrate_once、_tales_waiting，以及 battle_tale_request／apply_battle_tales 的鎖外三段式：這一批只把 Game 上那兩個方法的本體搬進包、server 照舊叫委派，**行為與位置一個字不動**；雲端近期要讓奪璽單挑、攻城也寫戰記、每一幕寫時辰）、頭目戰、擂台、玉璽、別的包（mall、feast、sortie、explore、tavern）的行為。
- 不開子代理、不開工作流程。任何畫面、輸出不能透露誰是假人；這一批不該有新字。做完就停；回報用繁體中文。
- **同時跑的線**（PM 11/01 接手後定）：第 7 批（決戰「打」b，\`dev/battle-3\`）與第 15 批（共用規則層登記，\`dev/core-shared-1\`）並行——第 15 批只登記、不搬程式，衝突是增量的；共用登記檔（邊界清單、\`services.py\`、\`registry.py\`、FEATURES、same_behavior、\`aliases()\`）你加的每一筆都集中在自己那一段（\`# battle\`／\`# shared\`）後面，不穿插在別人的行之間。後合的那一條，PM 會先合 develop 再重比。
- **第 11 批（核心收接縫）已合進 develop**：\`tianxia/core/features.py\` 多了接縫掛鉤與兩個宣告（\`Shop\`、\`Verb\`）；手冊第十五節「第 11 批的 PM 認定」：接縫掛鉤不看包的 \`enabled\`、給選項的照問。**原位該接的照第 11 批的寫法接上掛鉤，不要再新增 \`GAME_DIRECT\`**（真的接不了寫理由）。
- **開工第一步先查雲端那兩條線**：明確 fetch origin 的 \`claude/*\`（\`git ls-remote origin 'refs/heads/claude/*'\`），看最近兩天有提交、還沒合進 develop 的，有沒有改到這一批要搬的集結、投效、挑同伴的方法（名字照你在計畫第一節量出來的清單）、\`escorts.py\`、\`generals.py\`，或 tale.py、server 的戰記那一段。企劃者 10/31：雲端近期要讓攻城、奪璽單挑也寫戰記。**動到了就停**，stopped 寫哪一條、哪幾個方法，不要開工。
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

const DEV = `你是《天下大勢》的開發子代理，做**全部拆包的第 7 批：決戰「打」b——集結、投效、挑同伴，搬進 \`tianxia/features/battle/\`**（總表 ${MASTER} 第 3.2 節第 7 列：約 29 個方法、466 行；接在第 5、6 批後面，兩批都已合進 feature/battle 與 develop）。這一批要**拿 \`battle\` 前綴**。承諾是**行為一個字不變**。
${COMMON}
先讀：
- 手冊 ${BOOK} 3.1～3.11 與第十五節（含「第 11 批的 PM 認定」）。
- 批次表 ${BATCH}，整份，很短（第二節假人那一條：拿了前綴就把 \`bot_policy.score\` 那一段搬進包的 \`bots.py\`，照宴客；測試直接換的名字要照舊生效）。
- **第 6 批的計畫 \`docs/superpowers/plans/2026-11-01-決戰包-第2批.md\`**：照它的格式寫這一批；第五、六、七節是它量到的、修正與合併紀錄；第五節「交 PM 定的」裡 \`cancel_siege\` 那一條 PM 定了：**這一批 Task 1 先補 \`cancel_siege\` 收起來之後讀回季那一行的測試**。
- 第 11 批的計畫 \`docs/superpowers/plans/2026-11-01-核心收接縫.md\`：新的接縫掛鉤怎麼接、\`Verb\`、\`Shop\`。
- \`tianxia/features/battle/\` 整包與 README；\`escorts.py\`、\`generals.py\`。
- ${SURVEY}/survey_battle.json，以及 ${SURVEY}/plan.json 裡決戰第二段那一筆。
- 總表第 3.2 節第 7 列：\`_mandate_weight\` 裁定歸玉璽，這一批留原位當過渡（主人玉璽）。第 8 批（推進與結算、收季的收兵）接在這一批後面，不要先做。
- docs/guide/戰鬥.md 全服決戰那幾段；\`scripts/same_behavior.py\` 決戰那一軌。
用 \`grep -n '^#'\` 看大綱，只讀相關的節。調查的行號是舊的，一律照現行程式重量。
分支：明確 fetch feature/battle（PM 會先把它快轉到 develop ${BASE}；不是的話停下來回報）；\`git switch -c dev/battle-3 origin/feature/battle\`（同名已存在就加 -work），推 \`git push origin HEAD:dev/battle-3\`。不碰 feature/battle、develop、main，PM 合。埠 8191、battle3.localhost；暫存 ${SP}\\battle3\\。

**PM 定的（照做）**：
- **拿 \`battle\` 前綴**：\`battle:\` 選項的分派進包（照第 11 批之後的寫法；\`choose\` 前段已經有掛鉤的就接掛鉤）；\`bot_policy.score\` 的 \`battle:\` 那一段搬進 \`features/battle/bots.py\`（照宴客）。測試直接換或直接叫的名字（bot_policy、Game 上的）照舊生效、斷言一個字不改；做不到就留在原位、寫明理由，並用 BotRunner 雜湊證明假人一樣。
- \`escorts.py\` 進包（舊名留 \`sys.modules\` 別名，同一個模組物件）；\`generals.py\` 是第 8 批的，這一批不搬。
- 留在原位、叫委派的照第 5、6 批的寫法；**第 11 批已經有掛鉤的位置改接掛鉤**，記進邊界清單、寫理由。
- 測試直接叫或 patch 的 Game 方法一律留委派；被 monkeypatch 的包裡經 \`ctx.<名>\`。
- 這一批不該有新字，也不改 web/。

做法：先照 superpowers:writing-plans 寫計畫 docs/superpowers/plans/2026-11-01-決戰包-第3批.md。第一節「現行程式對照」照現行程式重量：要搬的方法、要留的委派、留在原位的、核心直接碰包的各幾處、\`battle:\` 前綴在 choose／bot_policy／bot.py／bot_runner 的每一處。然後一個 Task 一個 commit 做（superpowers:executing-plans，不開子代理）：
- **Task 1：測試與 same_behavior**：先補 \`cancel_siege\` 收起來之後讀回季那一行的測試（PM 定）。決戰那一軌加這一批的情境：開集結、各陣營加入、散人與豪強臨時投效（集結時、開打後晚到）、改投、挑同伴出戰、集結被拒的路各一次；**半舊半新切在集結中**（base 開集結、幾人加入後停，head 接著投效、開打、收場）；假人照第 5 批的寫法，BotRunner 要碰得到 \`battle:\` 那一段。先在 base 上跑兩次證明穩、改一個字抓得到，commit、推。
- **Task 2：核心那一側**：services.py、FEATURES（prefix）、邊界清單（集中在 \`# battle\`）。跑核心測試＋煙霧一次。commit、推。
- **Task 3：搬**：方法進 \`features/battle/\`（照前兩批的命名習慣）、\`escorts.py\` 進包、\`bots.py\`。委派一行、不加邏輯。commit、推。
- **Task 4：測試整檔搬**：整檔屬於這一批的才搬；跟第 8 批共用的不拆、留原位、記數字。README。commit、推。
- **Task 5：證明與驗收**：same_behavior base（${BASE}）對 head：
  - 四軌（出陣、約戰、決戰、酒肆）加 explore-compare，五種設定，整段、半舊半新、假人全部逐位元組一樣。
  - 量：包的測試時間、改 features/battle/ 任一檔挑到幾條（≤ 300）、過渡處數、委派數、GAME_DIRECT 與 GAME_DELEGATE_CALLERS 各幾處、engine.py 行數。
  - 寫進計畫第五節，導覽跟著改。commit、推。
測試：
- 包的 tests（\`-m "slow or not slow"\`）。
- 核心測試＋煙霧：Task 2、Task 5 各一次。
- 相關的 slow：git grep 找叫這一批方法的測試檔與 bots 測試（例：決戰整場那幾支、\`test_bot_policy*\`、投效與同伴的），\`-m "slow or not slow" -n 4\`。
- 不跑整套。
回報：head、commits、same_behavior、驗收數字、測試、學到的、要 PM 定的；因雲端的線停下就在 stopped 寫原因。`

const LENSES = [
  { key: 'proof', text: `**行為不變的證明誠不誠實**：讀 \`scripts/same_behavior.py\` 這一批加的情境。開集結、各陣營加入、散人與豪強投效（集結時與晚到）、改投、挑同伴、被拒的路，是不是都真的走到了？看回應與資料庫裡有沒有那幾句、那幾筆。半舊半新的切點是不是在集結中？假人那一段碰不碰得到 \`battle:\` 前綴（BotRunner）？**自己重跑一次**：在 ${SP}\\battle3-rev-proof\\ 開兩份 detached worktree，一份 ${BASE}、一份開發的 head（Windows 路徑）。season21 與 week7 各比一次 base 對 head，再做一個單點突變（例：投效時少記一筆、或假人少按一次投效），看 compare 抓不抓得到；用完 \`git worktree remove\`。` },
  { key: 'bots', text: `**前綴與假人**：拿了 \`battle\` 前綴之後，\`bot_policy.score\` 那一段是不是搬進了 \`features/battle/bots.py\`、原位沒有變死碼；測試直接換的 bot_policy 名字照舊生效、斷言沒改；\`choose\` 前段走第 11 批的掛鉤還是留原位、寫了理由；\`bot.py\`、\`bot_runner\` 叫的名字還在。自己在 ${SP}\\battle3-rev-bots\\ 的 detached worktree 跑 bots 相關測試（含 slow）。` },
  { key: 'boundary', text: `**照不照手冊、批次表，有沒有回歸**：
- 包只 import 核心＋標了「# 過渡：待搬」的舊模組（數一數）。
- 委派都是一行。
- 這一批加的是不是集中在 \`# battle\` 那一段。
- 拿了 \`battle\` 前綴（假人那一段由另一位看）；\`escorts.py\` 的別名是同一個模組物件；\`generals.py\`、\`_mandate_weight\` 沒搬。
- 第 11 批有掛鉤的位置接了掛鉤，沒有新增 \`GAME_DIRECT\`（有的話理由站不站得住）。
- 沒碰 web/、戰記、輿圖、鐵匠鋪、別的包、資料庫結構、技能檔、CLAUDE.md、手冊、批次表。
再自己在 ${SP}\\battle3-rev-reg\\ 的 detached worktree 跑：
- 包的測試（含 slow，記時間）、相關的 slow，\`-m "slow or not slow" -n 4\`。
- 變異：包裡改壞一個搬過去的方法，看哪些測試紅、test_for 挑不挑得到。
- 有沒有測試被改了斷言：只准改路徑深度與 import。` },
]

const CHECK = (head) => `你是《天下大勢》的驗收子代理，驗**全部拆包第 7 批：決戰「打」b（集結、投效、挑同伴）搬進 \`tianxia/features/battle/\`**（dev/battle-3 ${head}）。**PM 10/31 晚為了趕進度，純搬、web/ 一個字沒動的批，實機 QA 改成這一個「兩台真伺服器逐位元組比」**：網頁檔沒變、伺服器回的位元組一樣，畫面就一定一樣；你只拍三張圖做 sanity。
${COMMON}
開發與審查已經跑過測試與 same_behavior：**不要重跑**。
做法：照 ${SP}\\qa-sortie1\\s\\ 的 serve.py（時鐘凍住只在 /__qa/clock 往前推、每次進行動鎖重設 game.rng 與 random、沒給種子的 Random 用固定種子、世界排程執行緒不開、/__qa/edit 擺位），複製到 ${SP}\\chk-battle3\\ 改著用。明確 fetch dev/battle-3、feature/battle；開兩份 detached worktree：HEAD＝${head}、BASE＝origin/feature/battle（${BASE}）；兩份的 .local/webpush_vapid.pem 用同一把。兩台伺服器分別開在埠 8193（HEAD，battle3chk.localhost）與 8194（BASE，127.0.0.1），season21：用真的 HTTP（requests 或 curl，帶 cookie）照同一串步驟打兩台——註冊六個帳號（官軍、黃巾各二，散人、豪強各一）、管理者開季、開決戰、集結（各陣營加入、散人與豪強投效、一人改投、挑同伴）、出招、放手一搏（模型擋著，走退回）、推時鐘到收場、每個人 /api/main、/api/reports、/api/reports?id=——**每一個回應的狀態碼與內容逐位元組比**（帶時間戳的欄位凍住時鐘之後應該一樣；真的不一樣的列出來分清楚是雜訊還是程式）；收場後兩個資料庫逐表比。再用 headless 瀏覽器各拍 375×812 淺色的江湖頁、決戰頁、戰報頁三張並排。收的時候 taskkill /T。
回報：same（全部一樣才是 true）、走了哪些步驟、差異清單、截圖路徑。有問題寫成回饋單 FB-9190～FB-9199（docs/superpowers/feedback/試玩回饋.md）並推到 qa/battle-3（從 origin/dev/battle-3 開；只放報告、回饋單、圖）；沒有問題就不必開 qa 分支。`

phase('Build')
const dev = await agent(DEV, { label: 'dev:battle-3', phase: 'Build', schema: DEV_SCHEMA, isolation: 'worktree' })
if (!dev) return { dev: null }
if (dev.stopped) return { dev, stopped: dev.stopped }
phase('Review')
const devText = `開發回報：\n${dev.report}\nsame_behavior：${dev.same_behavior}\n驗收：${dev.acceptance}`
const reviews = await parallel(LENSES.map(l => () => agent(`你是《天下大勢》的唯讀審查員（不改檔、不提交、不推）。\n${COMMON}\n審 dev/battle-3 的 ${dev.head}（明確 fetch），base 是 feature/battle ${BASE}。\n${devText}\n你的鏡頭：${l.text}\n每一條發現寫 severity（blocker＝合了會壞、或行為變了、或違反手冊／批次表／PM 定的；should；nit）、在哪裡、證據（指令與輸出）。沒有就回空陣列，不要湊。`, { label: `review:battle-3-${l.key}`, phase: 'Review', schema: REVIEW_SCHEMA })))
const findings = reviews.filter(Boolean).flatMap(r => r.findings || [])
let head = dev.head, fix = null
if (findings.length) {
  phase('Fix')
  fix = await agent(`你是《天下大勢》的開發子代理，修 dev/battle-3（現在 ${dev.head}）上三位審查員的發現。\n${COMMON}\n分支：明確 fetch，\`git switch -c dev/battle-3-fix origin/dev/battle-3\`（同名已存在就加 -work），推回 origin/dev/battle-3（快轉）。每修一條一個 commit、修一條推一次；先寫會紅的測試（或讓 same_behavior 先抓到）再修；屬實的才修，不屬實的寫進 rejected 附證據；nit 能順手就修。修完重跑 same_behavior 的 base 對 head（五種）與相關測試。要開伺服器用埠 8192、battle3fix.localhost（審查已經收了）。暫存 ${SP}\\battle3-fix\\。\n開發回報（摘要）：${dev.report.slice(0, 5000)}\n發現：\n${JSON.stringify(findings, null, 1)}\n審查摘要：${reviews.filter(Boolean).map(r => r.summary).join('\n---\n')}\n回報 head、修了哪些、駁回哪些、測試、學到的。`, { label: 'fix:battle-3', phase: 'Fix', schema: FIX_SCHEMA })
  if (fix && fix.head) head = fix.head
}
phase('Check')
const check = await agent(CHECK(head), { label: 'check:battle-3', phase: 'Check', schema: CHECK_SCHEMA })
return { dev, reviews, fix, head, check }
