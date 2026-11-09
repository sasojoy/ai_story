# 帖友書信（`tianxia/features/mail/`）

- 做什麼：交換過名帖的兩個人互相寄信（見聞 → 紀錄 → 信匣）。
- 導覽：`docs/guide/散人與玩家互動.md` 的「帖友書信」那一節
- 設計稿：https://claude.ai/artifact/FhMZSwH6aqNsrnNAwHBznn（Joy 2026-11-07「信能寫聯絡方式、網址嗎？不擋，其他按照建議」）
- 開關：`Config.mail.enabled`（`core/tuning/mail.py`，預設關；正式設定還沒打開，Joy 說開才在 `season21`、`week7` 加 `"mail": {"enabled": true}`）。緊急關：關掉就沒有信匣、沒有「寫信」，信照留在小檔裡。

| 檔 | 是什麼 |
|---|---|
| `__init__.py` | 登記：status（`main.mail.unread`，見聞的紅點）、status_slots（管理頁 admin 表的 `mail` 格，表外接尾）、admin_tools、routes；載入時把易名帖換名登記到 `core/renames` |
| `store.py` | 小檔 `<db>-mail.sqlite`（letters、blocks、mutes、reports）；兩季以前搬去 `<db>-mail-archive.sqlite`；一對帖友主檔留最近 `keep_per_pair` 封 |
| `actions.py` | 信匣、往來、寄（A 段 `screen`、C 段 `send`）、不收、檢舉、管理者看檢舉、撤下、停寄 |
| `routes.py` | `GET /api/mail`、`GET /api/mail/thread?name=&before=`、`POST /api/mail/{send,block,report}`；管理者工具 `mail_remove`、`mail_keep`、`mail_mute` |
| `tests/` | `test_mail.py`（10 條，1 條 smoke）、`test_mail_smoke.py`（1 條 smoke）、`mail_stage.py` |

**規則**：兩邊的名帖匣都收著對方那一張才寫得了（名帖跨季，帖友也跨季）。一封最多 `max_chars`（200）字；一天 `per_day`（10）封（回體丹那一套的 00:00 換日）；對方沒回之前同一個人最多連寄 `unanswered`（3）封。內容過 `speech` 的 LETTER（字表＋鎖外模型；聯絡方式與網址不擋）。
**沒有已讀**：寄的人只看得到自己寫的時刻與地點（假人永遠不讀信，有已讀就看得出來）。假人不寄信、照樣收信，寄給假人與寄給真人回的話、畫面一樣。
**不收他的信**：他照常寄、照常看到寄出去了，信記成 dropped、收件人永遠看不到（解開也不補）。**檢舉**：那一封從收件人的信匣收起來，管理頁「書信檢舉」看得到那一封（只看得到被檢舉的）；撤下（兩邊都看不到）、沒事（清掉檢舉）、停寄 1／3／7 天（`mute_days`）。
**換季**：信不清，往來照季分段。**易名帖**：`sqlite_world.rename_character` 那一筆交易 COMMIT 之後叫 `core/renames`，這一包把小檔裡的名號 key 換掉。
**不認領 PlayerState 欄位**、資料庫不升版：換回舊程式只是看不到信。
**網頁**：`web/mail.js`、`web/mail.css`；`web/app.js` 見聞的「紀錄」多一格「信匣」（`main.mail` 有才畫）、見聞分頁紅點看 `mailUnread()`；`web/peers.js` 名帖放大那一張底下多「寫信」；`web/admin.js` 多一塊「書信檢舉」（畫法 `mailAdminHtml` 在 mail.js）。
**還沒做**：手機通知「帖友來信」、玩家卡上的「寫信」鈕（第二批）。
