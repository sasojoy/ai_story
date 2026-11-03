# PM 的工作流程腳本（拆包用）

主機側 PM 派拆包用的 Workflow 腳本，原本放在 PM 對話的 scratchpad，11/01 晚收一份進 repo，免得 scratchpad 被清掉。

- `split-batch.js`：通用的一批（開發 → 審查 → 修 → 兩台真伺服器逐位元組比，`web: true` 時改完整實機 QA）。`args`：`base`、`n`、`title`、`pkg`、`feature`、`dev`、`plan`、`prev_plan`、`ports`（`dev`、`rev`、`fix`、`head`、`base`）、`host`、`fb`、`body`、`check_steps`、`reviewers`（2 或 3）、`parallel`、`dont_touch`、`after15`。
- `split-merge.js`：通用合併（合功能分支與 develop → 四種設定開機、測試閘門、same_behavior → 推功能分支與 develop → 計畫第七節、總表、手冊第十五節、交接一句 → 唯讀檢查員）。`args`：`n`、`title`、`feature`、`source`、`source_head`、`plan`、`ports`、`full_suite`、`related_slow`、`decisions`、`notes`。
- `next_batches.json`：第 8、17、22、23、24 批已經寫好的 `args`（`base`、`ports`、`fb`、`parallel` 派的時候補）。
- `battle-3.js`、`core-15.js`：第 7、15 批實際派的那兩支（第 7 批的驗收段可以單獨照抄重派）。

腳本裡寫死的路徑（`SP`）是 PM 對話 `86ac9c59` 的 scratchpad；換了對話要改成新的 scratchpad。

## 11/03 暫停：第 8、17 批派工時補的參數

企劃者 11/03「剩下先暫停，先整理整合」。下面是兩批派工時在 `next_batches.json` 之外補的參數，接回來照這個補（`base` 換成當時的 develop）：

| 批 | `base`（當時） | `ports` | `fb` | 其他 |
|---|---|---|---|---|
| 8 | `9cd4ddde` | dev 8163、rev／fix 8164、head 8165、base 8166 | FB-9240～FB-9249 | `after15: true`；`parallel` 照當時在跑的寫。iv1gio 已合進 develop（#137），派工單裡「iv1gio 還沒合就照常搬」那一段改成「`_advance_battle_round` 外面那一層 `_round_mvp` 一起搬」。另加兩件第 16 批留下的小事：`services.py` 戰力快照 7 個名字去重、engine 三個沒人用的 import（`AccountStore`、`Feast`、`FrontReport`） |
| 17 | `746bd932` | dev 8159、rev／fix 8160、head 8161、base 8162 | FB-9230～FB-9239 | `after15: true`。第 1、2 項已在 `dev/sortie-3` `6cab584a`；第 3 項 WIP 在 `dev/sortie-3b` `ca5e4a17`：開發那一步改成「從 `dev/sortie-3b` 接著做第 3 項起，做完快轉推進 `dev/sortie-3`」，不要從頭開 |

- `merge-smith.js`：鐵匠鋪與合成流程（`feature/smithing-flow`）合進 develop 用的那一支。它不是拆包批，行為本來就會變，所以沒有 same_behavior。
- 停在半路的 run 換了對話接不回來（`resumeFromRunId` 只認同一個對話）。接法：讀舊對話的 `subagents/workflows/<run>/journal.jsonl`，把做完的 agent 結果填回腳本，只重跑沒做完的那一步；或者在派工單裡寫明前一位做到哪。
