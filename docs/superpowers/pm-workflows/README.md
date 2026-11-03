# PM 的工作流程腳本（拆包用）

主機側 PM 派拆包用的 Workflow 腳本，原本放在 PM 對話的 scratchpad，11/01 晚收一份進 repo，免得 scratchpad 被清掉。

- `split-batch.js`：通用的一批（開發 → 審查 → 修 → 兩台真伺服器逐位元組比，`web: true` 時改完整實機 QA）。`args`：`base`、`n`、`title`、`pkg`、`feature`、`dev`、`plan`、`prev_plan`、`ports`（`dev`、`rev`、`fix`、`head`、`base`）、`host`、`fb`、`body`、`check_steps`、`reviewers`（2 或 3）、`parallel`、`dont_touch`、`after15`。
- `split-merge.js`：通用合併（合功能分支與 develop → 四種設定開機、測試閘門、same_behavior → 推功能分支與 develop → 計畫第七節、總表、手冊第十五節、交接一句 → 唯讀檢查員）。`args`：`n`、`title`、`feature`、`source`、`source_head`、`plan`、`ports`、`full_suite`、`related_slow`、`decisions`、`notes`。
- `next_batches.json`：第 8、17、22、23、24 批已經寫好的 `args`（`base`、`ports`、`fb`、`parallel` 派的時候補）。
- `battle-3.js`、`core-15.js`：第 7、15 批實際派的那兩支（第 7 批的驗收段可以單獨照抄重派）。

腳本裡寫死的路徑（`SP`）是 PM 對話 `86ac9c59` 的 scratchpad；換了對話要改成新的 scratchpad。
