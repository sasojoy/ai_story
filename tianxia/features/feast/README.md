# 宴客 `tianxia/features/feast/`

- **做什麼**：大勢人物設宴（季的事）、玩家入席敬酒（固定的三句或自己寫一句、模型鎖外評分）、情誼照分數漲、散席時席間最佳那一句上天下大事、那個人補名望。第 1 階多搬的「有按鈕的小包」（開發規範手冊 3.10），驗 `options`、接管選單（`menu`）、`choose`、`on_sync`、`bot_pick` 這幾個商城用不到的掛鉤。
- **導覽**：`docs/guide/大勢人物與賽季.md` 的「宴客（功能包）」那一節；核心與功能包的關係見 `docs/guide/核心與存檔.md` 的「核心、功能包、FEATURES、掛鉤、服務清單」。
- **設計稿**：大勢人物擴充第三批「多人同服的玩法」（https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2）第 1 版（手冊之前的稿，沒有版本號），數字在 `Config.figure_life` 的 `feast_*`。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記（`FeastFeature`）：`enabled`＝宴客開著或這一季還有擺過的宴、`options`（入席）、`menu`（坐在席上）、`choose`（`feast:`，標題先算）、`on_sync`、`bot_pick`、`bot_always`＝`feast:` |
| `rules.py` | 純規則（原 `tianxia/feasts.py`；那個名字留成別名給測試） |
| `actions.py` | 原本 `Game` 上的 `_feast_seat`、`_feast_options`、`_feast_menu`、`_feast_act`、`feast_*`；`Game.feast_free_text_prompt`、`feast_text_request`、`feast_toast` 留一行委派 |
| `bots.py` | 假人的分數（原 `bot_policy.score` 的 feast 那一段）：入席 8、敬酒 50、離席不按 |
| `tests/` | `test_feast.py`（原 `tests/figures/test_figure_life_batch3.py` 的「宴客」那一段）、`feast_stage.py`（契約測試擺局面） |

**認領的欄位**（3.5，留在原地）：`PlayerState.feasting`、`feasts_paid`（換季跟著新角色重來）；`WorldState.feasts`、`feast_seq`（這一季的宴席）；`Config.figure_life.feasts`、`feast_*`。`models.py` 序章不出現的前綴 `feast:join:`。
**還沒接掛鉤的（過渡）**：`world.py` 散席（季的推進）、`figure_life.py` 設宴、`letters.py` 邀宴，都 import 這一包；`server.feast_text`（三段式、鎖外評分）與 `main_view` 的 `free_text`／`free_op` 叫 `Game.feast_*`；`Game.scene_text` 坐在席上的場景卡叫 `actions.scene`。`rules.py` import `figure_life`、`seal_acts`、`renown`（註「過渡：待搬」）。
