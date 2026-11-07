"""管理頁的 API（功能包 tianxia/features/admin/；原本寫在 server.py，第二輪第 90 批搬進來）：殼（server 模組，參數 shell）照 FEATURES 掛（server 的 features_core.routers 那一行；
路徑與別的路由不重疊，先後不影響）。這個檔只在殼掛路由、建動作表時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
權限一個字沒動：/api/admin、/api/admin/player、/api/admin/accounts 不是管理者 403；/api/admin/reset_password 回「（只有管理者能重設密碼。）」；
13 個工具走 /api/do/{op}，殼的 api_do 擋；/admin 不擋（同一張 PAGE，資料都在 /api/admin* 那幾條）。"""
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from tianxia import calendar, divine, rules, timetable
from tianxia.core.features import AdminTool, no_gate
from tianxia.world_state import season_length_days
from tianxia.features.territory_acts import xingshi  # 下一步改走 STATUS_ORDER["admin"] 就拿掉


def admin_choices(shell, game) -> dict:
    """管理者觸發區的三個下拉選單（戰鬥、大事、大勢線）與模型佇列的總數。戰鬥與大事照引擎給的（Game.admin_battles／admin_fires：
    內容的順序，第一季不觸發的 beta 決戰與門檻不列；已經發生過的大事按下去會被引擎拒絕）；
    大勢線照這一季的規則（第一季濃縮版要開關開著、而且這一季蓋了「開」的章）。呼叫端要拿著行動鎖（look）。"""
    world = game.state.world
    return {
        # 賽季在哪個階段（籌備中 preparing／進行中 running／休季 resting）：開季、立刻收季、開啟下一季只在對的階段按得下去（U-19）
        "phase": game.world.season_phase(),
        "battles": [{"label": b.name, "id": b.id} for b in game.admin_battles()],
        "events": [{"label": f"{x.text[:30]}（{x.id}）", "id": x.id} for x in game.admin_fires()],
        # 照開關：關著時不列第一季才有的線；開著時不列黃巾聲勢（由三條戰線合成，不能直接推）
        "trends": [{"label": t.name, "id": t.id} for t in shell.CONTENT.scenario.trends if rules.pushable(shell.CONTENT, world, t.id)],
        **timetable_choices(shell, game),
        # 這一季照第一季的規則（開關開著、開季時蓋了章）：管理者區多「每週的事」（立刻發本週軍令、立刻輪替第 4 階席次）
        "season_one": rules.season_one(shell.CONTENT, world),
        # 21 天季（季曆就是現實的週）：暫停、繼續的問句多說一句季曆會對回現實的星期（PM 2026-10-19）
        "season21": calendar.season21_on(world, shell.CONTENT),
        # 那一句照季寫（FB-501）：「21 天的季…對回現實的星期」「7 天的季…對回現實的日子」（同 world.realign_line）
        "realign": {"days": f"{season_length_days(world, shell.CONTENT):g}", "unit": calendar.week_word("realign", shell.CONTENT, world)}
        if calendar.season21_on(world, shell.CONTENT) else None,
        # 開季、開下一季的問句括號裡那一句：7 天濃縮季照時刻表寫（timetable.default_dates_note）；其他季 None，網頁照原本的字
        "default_dates": timetable.default_dates_note(shell.CONTENT),
        # 「這一季立刻蓋天命之季的章」問句裡天命之爭的時刻：7 天濃縮季照時刻表寫（timetable.mandate_note，FB-503）；其他季 None，網頁照原本的字
        "mandate_at": timetable.mandate_note(shell.CONTENT, world),
        # 三場大戲各一顆「立刻開這一場」（Game.admin_showdowns）：開不了的灰掉、寫為什麼（開過了、結算了、宛城要等第 3 週……）
        "showdowns": [
            {"id": event.id, "label": event.title, "enabled": why is None, "note": why or ""}
            for event, why in game.admin_showdowns()
        ],
        # 下一季會照第一季的規則開（開關開著）：「開啟下一季」的問句也提醒排三場大戲與季末的時間（FB-050）
        "next_has_timetable": bool(shell.CONTENT.config.season_one),
        # 救場「叫回人物」：這一季退場、重創的大勢人物（沒有就不畫那一列）
        "fallen": [{"label": shell.CONTENT.figures[fid].name, "id": fid} for fid in game.admin_fallen()],
        "seal": game.admin_seal_choices(),  # 玉璽一組（碎片關著是 None，不畫）
        "xingshi": xingshi.on(shell.CONTENT, world),  # 〈天下形勢〉開著的季：管理者區多一顆「現在就開一篇天下形勢」（領地爭奪第三批 A）
        # 領地爭奪開著的季：救場一組（定一塊歸誰、定進度、立刻下戰書、取消一場攻城）的下拉選單；關著、季收了是 None（不畫）
        "conquest": game.admin_conquest_choices(),
        "mingtie": game.admin_mingtie_reports(),  # 被檢舉的名帖（撤下、放回）；沒有是空的
        # 新神器用完了（正式季整合 5.6，FB-400）：主控台啟動時印、換季的回話寫，管理者那一塊也寫一行；沒用完是空字串
        "divine_out": divine.EXHAUSTED if divine.exhausted_now(game.world.divine_state(), game.world.get_season_number()) else "",
        # 模型佇列的總數（正在跑幾件、在排幾件，真人與假人算在一起，不分開數）；不列名號，也看不出有沒有假人（審查 M4）。開關關著是 None
        "llm_queue": None if shell.QUEUE is None else shell.QUEUE.snapshot(),
        # 管理頁頂上「現在」那一塊（管理頁獨立，Joy 2026-11-01）：第幾季、季曆此刻、在打的決戰、各條大勢線此刻的值
        "now": admin_now(shell, game),
    }


PHASE_WORDS = {"preparing": "籌備中", "running": "進行中", "resting": "休季"}
BATTLE_PHASE_WORDS = {"muster": "集結中", "active": "開打了"}


def _online_count(shell, seconds: float | None = None) -> int:
    """這 seconds 秒（預設 shell.ONLINE_SECONDS）之內同步過的真人有幾個；只給管理頁看。讀不到就是 0。"""
    since = shell.time.time() - (shell.ONLINE_SECONDS if seconds is None else seconds)
    try:
        with shell.open_characters().db.snapshot() as conn:
            row = conn.execute("SELECT COUNT(*) FROM characters WHERE is_bot = 0 AND json_extract(data, '$.last_real') >= ?", (since,)).fetchone()
        return int(row[0] or 0)
    except Exception:  # noqa: BLE001  管理頁的一格數字，讀不到不擋整頁
        return 0


def admin_now(shell, game) -> dict:
    """管理頁頂上的現況：按鈕按下去之前先看得到此刻的樣子（定戰況、推大勢、救場之前知道現在是多少）。呼叫端拿著行動鎖。"""
    world = game.state.world
    battle = game.world.get_battle()
    fight = None
    if battle is not None and battle.phase != "ended":
        definition = shell.CONTENT.battles.get(battle.battle_id)
        fight = {
            "name": definition.name if definition is not None else battle.battle_id,
            "phase": BATTLE_PHASE_WORDS.get(battle.phase, battle.phase),
            "people": len(battle.participants), "round": battle.round_number, "trend": battle.trend,
        }
    return {
        "season": game.world.get_season_number(),
        "phase_text": PHASE_WORDS.get(game.world.season_phase(), ""),
        "when": game.stamp(world.time),
        "battle": fight,
        "online": _online_count(shell),  # 管理頁四格的「在線」：shell.ONLINE_SECONDS（10 分鐘）內來過的真人（介面重整 2026-11-05）
        "trends": [{"id": t.id, "label": t.name, "value": rules.world_trend_value(world, shell.CONTENT, t.id)}
                   for t in shell.CONTENT.scenario.trends],
    }


RESULT_WORDS = (("guan:", "官軍"), ("huang:", "黃巾"))  # 結果鍵的白話（定結果的下拉選單）
# cancelled：開打後被取消、還沒有結果（FB-099）：要收尾用「定結果」（只有管理者看得到）
TIMETABLE_STATES = {"done": "已結算", "running": "開打了", "cancelled": "開打後取消・待定結果", "due": "時間到了", "later": "還沒到"}


def _result_label(key: str) -> str:
    if key == "fixed":
        return "照史書"
    for prefix, side in RESULT_WORDS:
        if key.startswith(prefix):
            return side + key[len(prefix):]
    return key


def _ending_title(shell, ending_id: str) -> str:
    """季末那一列的結果：時間軸記的是結局 id（world._finale），寫結局的標題（FB-051）。"""
    return next((e.title for e in shell.CONTENT.scenario.endings if e.id == ending_id), ending_id)


def _done_label(key: str) -> str:
    """時刻表上已結算那一件的結果：拿掉版本（宛城、秦頡的「甲:」「乙:」），跳過的寫「跳過」。"""
    if key == timetable.SKIPPED:
        return "跳過"
    head, _, rest = key.partition(":")
    return _result_label(rest if rest and head not in ("guan", "huang") else key)


def timetable_choices(shell, game) -> dict:
    """設定頁的「時刻表」與「救場」（計畫 T10）：這一季有時刻表（第一季）才有東西，beta 那一季全是空的。
    時刻表每件一列，可排的（三場決戰與季末）附現實時間 at_real（照此刻的季時間換算，time_scale 照設定）；
    定結果的下拉選單列還沒結算、此刻知道是哪一版的大事的每一個結果；鎖定列有人鎖定的大事。"""
    state = game.state
    world = state.world
    if not rules.season_one(shell.CONTENT, world):
        return {"timetable": [], "results": [], "locks": []}
    now = shell.time.time()
    rows = []
    for row in timetable.status_rows(state, shell.CONTENT, cancelled=game.cancelled_showdowns()):
        rows.append({
            # 7 天濃縮季寫「第 1 段（第 1～2 天）」（calendar.week_label，FB-501）；其他季「第1週」
            "id": row["id"], "label": f"{calendar.week_label(row['week'], shell.CONTENT, world, form='tight')}　{row['title']}",
            "state": row["state"], "state_text": TIMETABLE_STATES[row["state"]],
            "result": (_ending_title(shell, row["result"]) if row["kind"] == "finale" else _done_label(row["result"]))
            if row["result"] else None,
            "schedulable": row["schedulable"],
            "at_real": now + (row["when"] - world.time) / shell.CONTENT.config.time_scale if row["schedulable"] else None,
        })
    results = [
        {"value": f"{e.id}|{key}", "label": f"{e.title}：{_result_label(key)}"}
        for e in timetable.events(world, shell.CONTENT) if e.id not in world.timeline
        for key in timetable.result_keys(state, shell.CONTENT, e)
    ]
    locks = [
        {"id": event_id, "label": f"{e.title}（{lock.name}）"}
        for event_id, lock in world.locks.items() if (e := timetable.find(shell.CONTENT, event_id))
    ]
    return {"timetable": rows, "results": results, "locks": locks}


def reset_password(shell, game, target: str, temp: str) -> str:
    """管理者幫人重設密碼（先照帳號找，再照名號找）；臨時密碼由管理者私下告訴對方。"""
    if not game.is_admin():
        return "（只有管理者能重設密碼。）"
    store = shell.account_store()
    try:
        with shell.open_database().transaction():
            key = store.find(target)
            if key is None:
                return "找不到這個帳號或名號。"
            store.set_password(key, temp)
    except shell.AccountError as exc:
        return str(exc)
    return f"已重設 {store.get(key).login} 的密碼。"



def admin_tools(shell) -> dict[str, AdminTool]:
    """季、時間、大勢與時刻表的 13 個工具（原本殼的 ADMIN_ACTIONS，先後照原表）。暫停中照做（paused_ok 預設 True：暫停中要按得到「繼續」；其他的引擎自己擋）。
    現實時間由殼給（shell.time，引擎不讀時鐘）。"""
    return {
        "open_season": AdminTool(no_gate, lambda g, b: g.admin_open_season(shell.time.time())),
        "end_season": AdminTool(no_gate, lambda g, b: g.admin_end_season(shell.time.time())),
        "next_season": AdminTool(no_gate, lambda g, b: g.admin_next_season(shell.time.time())),
        # 公告停機時賽季時鐘暫停（線上架構第四節、8.3）；主機端另有 scripts/season_clock.py
        "pause_clock": AdminTool(no_gate, lambda g, b: g.admin_pause_clock(shell.time.time())),
        "resume_clock": AdminTool(no_gate, lambda g, b: g.admin_resume_clock(shell.time.time())),
        "fast_forward": AdminTool(no_gate, lambda g, b: g.advance(shell._int(b.get("hours"), 1) * 3600)),
        "fire": AdminTool(no_gate, lambda g, b: g.admin_fire(str(b.get("id", "")))),
        "push_trend": AdminTool(no_gate, lambda g, b: g.admin_push_trend(str(b.get("id", "")), shell._int(b.get("amount"), 0))),
        # 時刻表與救場（計畫 T10）：現實時間由伺服器給，引擎不讀時鐘
        "schedule": AdminTool(no_gate, lambda g, b: g.admin_schedule(str(b.get("id", "")), shell._float(b.get("at"), 0.0), shell.time.time())),
        "jump_next": AdminTool(no_gate, lambda g, b: g.admin_jump_next(shell.time.time())),
        "set_trend": AdminTool(no_gate, lambda g, b: g.admin_set_trend(str(b.get("id", "")), shell._int(b.get("value"), 0))),
        "resolve_event": AdminTool(no_gate, lambda g, b: g.admin_resolve_event(str(b.get("id", "")), str(b.get("key", "")))),
        "clear_lock": AdminTool(no_gate, lambda g, b: g.admin_clear_lock(str(b.get("id", "")))),
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/admin")
    def admin_page():
        """管理頁自己的網址（Joy 2026-11-01「把管理員工具獨立一個網址」）：同一支網頁，網頁看網址畫管理頁；不是管理者的人打開，
        網頁照常回到江湖（資料都在 /api/admin* 那幾條，那邊才擋人）。"""
        return HTMLResponse(shell.PAGE, headers=shell.NO_CACHE)

    @r.get("/api/admin")
    def api_admin(request: Request):
        game = shell._game(request)
        if not game.is_admin():
            raise HTTPException(403)
        return shell.look(game, lambda g: admin_choices(shell, g))

    @r.post("/api/admin/player")
    def api_admin_player(request: Request, body: dict = Body(...)):
        """管理者區「玩家個人劇情」查一個名號（Game.admin_player_choices）：他是誰、能不能發召見、能給的機緣與伏筆片段。只讀。
        名號放在 POST 的內容裡、不放在網址上。查不到回 200 加 {"refusal": …}（原因寫在表單那一行）。"""
        game = shell._game(request)
        if not game.is_admin():
            raise HTTPException(403)
        name = str(body.get("name", ""))
        return shell.look(game, lambda g: g.admin_player_choices(name))

    @r.post("/api/admin/accounts")
    def api_admin_accounts(request: Request, body: dict = Body(...)):
        """管理頁「重設密碼」的帳號搜尋（管理頁獨立，Joy 2026-11-01）：帳號或名號含這幾個字的，最多 10 筆 {login, character}。只讀、管理者以外 403。"""
        game = shell._game(request)
        if not game.is_admin():
            raise HTTPException(403)
        return {"rows": shell.account_store().search(str(body.get("q", "")))}

    @r.post("/api/admin/reset_password")
    def api_reset_password(request: Request, body: dict = Body(...)):
        return {"message": reset_password(shell, shell._game(request), str(body.get("target", "")), str(body.get("temp", "")))}

    return r
