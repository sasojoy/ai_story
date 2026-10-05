# CLAUDE.md 待修清單

CLAUDE.md 裡跟現況對不上的地方。PM 收集，**企劃者同意後**才改（規矩：不經企劃者同意不改 CLAUDE.md）。改的時候以程式為準；改完一項就從這裡刪掉。

最後整理：2026-10-06。企劃者 10/6 同意「一次改好」，PM 把專職開發的改版草稿（`CLAUDE-md-改版草稿.md`）換上 CLAUDE.md：原本 1～45 列照草稿附錄一處理完（第 14 列企劃者定絕學定名照程式擋禁用名單；第 40 列照程式寫博聞不能被獎勵動；第 4 列不適用），第 46 列（叛投）、第 47 列（輿圖圖例浮層）也一起寫進去了。清單清空，之後有新的對不上再往下加。

| # | 在哪 | 現在寫的 | 實際情況 | 誰提的 |
|---|---|---|---|---|
| 1 | `CLAUDE.md`「第一季濃縮版」那一節的「叛投」一條；同一節也沒有「第 2 階行動」與「機緣」兩條；「架構」清單沒有 `tianxia/opportunities.py`（併入時可能要重編） | 叛投「身份歸零：晉升、召見、部下、本季貢獻、押著的糧車作廢……屬性、武學、同伴、銀兩、素材、紀錄都不動」，只列這幾樣 | 乙一做完後，叛投還會清掉機緣的完成、計數、拿著的東西與聽過的線索（`defection.clear_progress` 呼叫 `opportunities.clear`；每人每曆日第 2 階行動限次 `rank2_days` 不清）。另外多了：第 2 階行動 `act:rank2`（`Config.rank2_stamina`／`rank2_daily`／`rank2_push`）；機緣九種（`content/opportunities.json`，`tianxia/opportunities.py`，選項 `opp:deliver:`／`opp:try:`、對話話題 `talk:opp:`）；假人與整季機器人不做機緣（`bot.FORESHADOW_OPTIONS`、`bot_policy.score`），第 2 階行動假人照守勢行動的分數做 | 乙一 Task 2～5 |
