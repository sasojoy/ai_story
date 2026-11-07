"""battle 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
from unittest import mock
import pytest
import server
import server_push
from conftest import at
from tianxia import battle_instance
from tianxia.characters import open_characters
from tianxia.sqlite_world import open_world
from tianxia.state import FigureState, Lock, Rumor, TimelineResult, WorldState
from tianxia.world_state import SharedWorldState
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _a_showdown_fighter, _journal_titles, _no_landing, _no_preset_recipes, _player, _seal_duel, cheap_password_hashing,
    client, fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


# ── 全服即時戰鬥：自訂行動 ────────────────────────────────


def test_battle_free_text_shows_and_submits(game):
    definition = server.CONTENT.battles["huangjin_showdown"]
    game.state.player.faction = "guan"  # 劇本分陣營：散人只能觀戰，要先投靠才有得加入
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=320.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        assert server.look(game, server.main_view)["free_text"] == game.battle_free_text_prompt()
        with mock.patch("server.time.time", return_value=after_muster):
            server.battle_text(game, "直取波才首級")
    assert any("直取波才首級" in line for line in game.world.get_battle().narrative_log)


def test_joining_the_muster_tells_the_page_and_is_journaled(client):
    _a_showdown_fighter(client)
    before = _journal_titles()
    out = client.post("/api/choose", json={"id": "battle:join:guan"}).json()
    assert "你加入了這場戰局。" in out["message"]
    assert "黃巾決戰・加入官軍" in out["main"]["latest"]
    assert _journal_titles() == ["黃巾決戰・加入官軍"] + before


def test_joining_late_shows_the_line_on_the_page_data_and_journals_it(client):
    """FB-028 的驗收：「你趕到了戰場，這一回合就能出手。」要在畫面資料裡找得到（回話與江湖紀錄兩處）。"""
    _a_showdown_fighter(client, started=True)
    before = _journal_titles()
    out = client.post("/api/choose", json={"id": "battle:join_late"}).json()
    line = "你趕到了戰場，這一回合就能出手。"
    assert line in out["message"]
    main = client.get("/api/main").json()
    assert line in main["latest"] and line in out["main"]["latest"]
    assert _journal_titles() == ["黃巾決戰・趕到戰場"] + before


def test_a_rounds_action_replies_but_is_not_journaled(client):
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    before = _journal_titles()
    options = client.get("/api/main").json()["options"]
    act_id = next(o["id"] for o in options if o["id"].startswith("battle:act:"))
    out = client.post("/api/choose", json={"id": act_id}).json()
    assert "等待其他人" in out["message"]
    assert _journal_titles() == before


def test_the_free_text_action_already_replies_and_is_not_journaled(client):
    """放手一搏走 /api/do/battle_text，回話本來就從 api_do 的 message 回來、前端的 doMain 也會跳出來；不寫江湖紀錄。"""
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    before = _journal_titles()
    assert client.get("/api/main").json()["free_text"]
    assert "重傷的是你自己" in client.get("/api/main").json()["free_text_note"]
    out = client.post("/api/do/battle_text", json={"text": "直取波才首級"}).json()
    assert "等待其他人" in out["message"]
    assert _journal_titles() == before


def test_the_free_text_action_is_rated_outside_the_action_lock(client, monkeypatch):
    """試玩回饋 2026-10-08：放手一搏的成功率以前在行動鎖裡評，最多等 in_lock_model_timeout 秒，全服跟著等。現在鎖外評，
    評好的分照樣送進這一回合。"""
    _a_showdown_fighter(client, started=True)
    client.post("/api/choose", json={"id": "battle:join_late"})
    seen = []

    def rate(c, act, faction_name, text, name, target="", sex="男"):
        seen.append((open_world().db.writing(), faction_name, text, name))
        return 73

    monkeypatch.setattr(battle_instance, "score_gamble", rate)
    client.post("/api/do/battle_text", json={"text": "火燒糧草"})
    assert seen == [(False, "官軍", "火燒糧草", "沈青衫")]
    battle = open_world().get_battle()
    assert battle.round.success_rates == {"沈青衫": 73}
    # 只評成功率（Joy 2026-10-13）：劇情等回合結算後一整批寫（narrate_battle），送出時沒有劇情
    assert battle.round.stories == {} and battle.round.sexes == {"沈青衫": "男"}


def test_a_showdown_option_that_is_no_longer_there_still_says_so(client):
    _a_showdown_fighter(client)
    out = client.post("/api/choose", json={"id": "battle:act:safe"}).json()
    assert "此刻無法" in out["message"]


def test_a_fighter_sees_the_finished_showdown_on_the_main_page(client):
    """FB-027：決戰在這個帳號沒連線時收場（只動了資料庫裡的戰鬥），下一次打 /api/main 就補進江湖紀錄與戰報、
    「剛剛」放這一場的卡片，而且存進了角色。"""
    _player(client)
    definition = server.CONTENT.battles["huangjin_showdown"]
    world = open_world()
    world.start_battle(definition, now=0.0)

    def fight(b):
        battle_instance.join_faction(b, "沈青衫", "guan", neili_cap=320.0)
        battle_instance.close_muster(b, definition, random.Random(0))
        while b.phase == "active":
            battle_instance.submit_action(b, "沈青衫", battle_instance.safest_option_tag(b, definition, "沈青衫"))
            battle_instance.resolve_round(b, definition, random.Random(0))

    world.mutate_battle(fight)
    main = client.get("/api/main").json()
    assert main["card"] is not None and "決戰：黃巾決戰" in main["card"] and "你站在官軍" in main["card"]
    assert main["card_id"] is not None
    saved = open_characters().load("沈青衫")
    assert saved.journal[0].title.startswith("黃巾決戰・") and saved.journal[0].battle_id == main["card_id"]
    report = client.get(f"/api/reports?id={main['card_id']}").json()
    assert report["list"][0]["id"] == main["card_id"] and "你站在官軍" in report["detail"]


def test_the_fingerprint_ignores_the_clock_the_schedule_and_who_acts(client):
    """預檢 F4：世界時間與 season_last_real 每一次同步、每一下排程都在動，不能算進指紋，不然每個分頁每幾秒就被叫醒；
    決戰裡誰加入、這一回合出手了幾個（預檢 F2）畫面上看不到，也不算。"""
    open_world().mutate(lambda st: None)
    before = server.current_fingerprint()
    open_world().mutate(lambda st: (setattr(st, "season_last_real", 9e9), setattr(st.season, "time", st.season.time + 3600)))
    assert server.current_fingerprint() == before
    _a_showdown_fighter(client)
    with_battle = server.current_fingerprint()
    assert with_battle != before  # 決戰開了：大家都看得到
    client.post("/api/choose", json={"id": "battle:join:guan"})  # 又一個人加入：看不到
    open_world().mutate_battle(lambda b: b.round.pending_actions.__setitem__("沈青衫", "safe"))
    assert server.current_fingerprint() == with_battle
    open_world().mutate_battle(lambda b: setattr(b, "trend", b.trend + 1))  # 戰局動了：看得到
    assert server.current_fingerprint() != with_battle


# 推送指紋的欄位分類（最終審查 m5）：全服共用的世界狀態（SharedWorldState、它的賽季 WorldState、進行中的決戰 BattleInstance）
# 每一個欄位，不是「算進指紋」（底下的改法真的讓指紋變，下面的測試會試）、就是「不算」（寫一句為什麼）。以後誰加了新欄位，
# 兩邊都沒有就紅——到時候要決定：它改了，全服每個人的畫面看得出來嗎？看得出來就要算進去（不然開著的分頁最久 60 秒才知道），
# 看不出來（或不能讓人看出來）就寫進「不算」。暫停（paused_at）就是這樣漏過一次。
_SEASON = "season"  # 容器欄位：它自己不算，裡面的欄位各自分類（WorldState 的欄位在 "WorldState" 那一組）
FINGERPRINTED = {
    "SharedWorldState": {
        "season_number": lambda st: setattr(st, "season_number", st.season_number + 1),
        "season_opened": lambda st: setattr(st, "season_opened", False),  # 籌備中：階段變了
        "paused_at": lambda st: setattr(st, "paused_at", 1000.0),
        "season": _SEASON,
        "active_battle": lambda st: setattr(st, "active_battle", None),  # 決戰收掉
        # 奪璽單挑（玉璽碎片設計 5.10、13.3）：全服觀戰，回合推進、出招，開著的分頁要更新
        "seal_duels": lambda st: st.seal_duels.append(_seal_duel()),
        # 攻城戰（領地爭奪第二批）：每一場同決戰，開集結、回合推進、收場，開著的分頁要更新
        "sieges": lambda st: st.sieges.append(battle_instance.BattleInstance(battle_id="changshe_fire")),
    },
    "WorldState": {
        "trends": lambda st: st.season.trends.__setitem__("t", st.season.trends["t"] + 1),  # 浮現的那一條
        "revealed": lambda st: st.season.revealed.add("h"),  # 隱藏的那一條浮現了
        "rumors": lambda st: st.season.rumors.append(Rumor(time=0.0, text="天下大事", layer="world")),
        "chronicle": lambda st: st.season.chronicle.append(Rumor(time=0.0, text="江湖史一筆")),
        "ended": lambda st: setattr(st.season, "ended", True),  # 休季：階段變了
        "ending_title": lambda st: setattr(st.season, "ending_title", "天下大亂"),
        "storyline": lambda st: setattr(st.season, "storyline", "另一條主線"),
        "act": lambda st: setattr(st.season, "act", st.season.act + 1),
        "timeline": lambda st: st.season.timeline.__setitem__("uprising", TimelineResult(key="fixed", time=0.0)),
        "showdowns_opened": lambda st: st.season.showdowns_opened.__setitem__("changshe_fire", "changshe_fire"),
        "figures": lambda st: st.season.figures.__setitem__("lu_zhi", FigureState(prestige=70)),
    },
    "BattleInstance": {
        "battle_id": lambda st: setattr(st.active_battle, "battle_id", "wancheng"),
        "phase": lambda st: setattr(st.active_battle, "phase", "active"),
        "round_number": lambda st: setattr(st.active_battle, "round_number", 1),
        "trend": lambda st: setattr(st.active_battle, "trend", 55),
        # 「已送出 X／在場 Y」（試玩回饋 2026-10-08）：兩軍有人出手，開著的分頁要更新那個數
        "round": lambda st: (
            setattr(st.active_battle, "phase", "active"),
            st.active_battle.participants.__setitem__("甲", battle_instance.BattleParticipant(name="甲", faction="guan", neili=1, neili_cap=1)),
            st.active_battle.round.pending_actions.__setitem__("甲", "guan_hold"),
        ),
        # 放手一搏的劇情回合結算後才補上（Joy 2026-10-13）：補上的那一下場景的字變了
        "tales": lambda st: st.active_battle.tales.append(battle_instance.GambleTale(
            round=1, act_index=0, name="甲", faction="guan", text="火攻", won=True, fixed="x", numbers="y",
        )),
    },
}
NOT_IN_THE_FINGERPRINT = {
    "SharedWorldState": {
        "companion_tag_counts": "跟人物對話才用的記數，不在共用的畫面上",
        "companion_drift_note": "同伴的性情句，只在跟他對話時用",
        "companion_drift_synthesized_at": "性情語意化的記數，不在畫面上",
        "companions": "同伴被招走、升級只影響門下頁與招募鈕，那是各人自己的畫面（自己的動作走 self 通知），別人下次輪詢才補也不礙事",
        "event_flavor": "事件的潤色句，一次寫好之後不變，跟著事件的公告出現",
        "jade_seal_fragments": "玉璽碎片的歸屬，只在持有者的畫面",
        "season_last_real": "賽季時鐘的對時點：每次同步、每一下排程都在動，算進去每幾秒就叫醒全服（推送計畫 F4）",
        "tianji": "換季才加一，同時 season_number 也變了",
        "seal": "碎片的歸屬：現世、易手、隱沒都寫天下大事（傳聞流水號已在指紋裡）；密鹽不能讓人看出來（13.3）",
        "mingtie_reports": "名帖的檢舉：誰檢舉了誰不能讓人看出來；藏起來的那一張別人下次打開才補",
        "mingtie_removed": "管理者撤下的名帖：被撤的人江湖紀錄一句（自己的動作走 self 通知），收過的人下次打開才補",
        "mingtie_cleared": "管理者放回的名帖，同上",
        "divine": "神器輪替的全服登記：開季換季時才挑；原品與仿品數在打造、定名那一下改，傳聞與江湖史已在指紋裡",
        "siege_records": "攻城戰的流水號（存檔時照 sieges 寫）；sieges 本身算進指紋",
        # 3b-2 接線了（main.sortie_card、main.sorties）；搬進指紋要在 server_push.world_fingerprint 加一格、server.current_fingerprint 傳
        # shared.sorties——server_push 是雲端側的檔，交雲端側改（計畫 4.0 之三第 5 條）
        "sorties": "出陣約戰（減法季批 3b）：接線了，但推送指紋的那一格在雲端側的 server_push，等他們改；之前開著的分頁照輪詢看到別人貼的約戰",
    },
    "WorldState": {
        "time": "時鐘一直在走，靠慢速輪詢更新（排程每 10 秒推一次，算進去會一直叫醒全服）",
        "flags": "世界旗標只是條件，不直接畫在共用畫面上（推送計畫 F4）",
        "flag_times": "旗標第一次成立的時間，同上",
        "chapter_weights": "章回主線做成的份量：畫面上只有章回卡那一行（各人自己的卡，下次輪詢才補也不礙事），改歷史在大事結算那一刻才看得出來",
        "chapter_done": "章回做成的人數：同上，只寫在各人自己的章回卡上",
        "fired_thresholds": "門檻觸發過的記號；畫面看的是它帶來的傳聞與大勢",
        "sim_accum": "不滿一小時的時間累積器",
        "life_turn": "人物每日行事做到第幾輪的記號；畫面看的是它帶來的傳聞（傳聞流水號已在指紋裡）",
        "whereabouts": "人物走動時一定同時寫一則傳聞（傳聞流水號已在指紋裡），誰在這裡下次輪詢就補",
        "feasts": "開席、散席都寫天下大事（傳聞流水號已在指紋裡）；席上別人敬的那一句只畫在入席的人的場景，下次輪詢才補也不礙事",
        "feast_seq": "宴席的流水號，跟 feasts 一起寫",
        "plans": "盤算公告、結算都寫天下大事（傳聞流水號已在指紋裡）；兩邊各幾人只畫在江湖頁的盤算卡，下次輪詢才補也不礙事",
        "stops_done": "行程每一站做完了沒，做的那一下都寫天下大事",
        "deeds": "世界記事：人物對話與此地舊事才讀，寫的那一下都有天下大事或江湖紀錄",
        "deed_seq": "世界記事的流水號，跟 deeds 一起寫",
        "places": "地點的樣子（地點會變樣）：變樣那一下都有天下大事或世界記事一起寫；照時間轉重建、回太平不寫存檔，畫面下次輪詢自己現算",
        "inscriptions": "走一趟的留言：只在別人下一次走一趟、路上抽到才看得到，不在共用的畫面上",
        "inscription_seq": "留言的流水號，跟 inscriptions 一起寫",
        "yuedan": "月旦評發出去那一刻寫天下大事與江湖史（都在指紋裡）；還沒發的那一批誰都看不到",
        "yuedan_week": "評到第幾週的記號，跟 yuedan 一起寫",
        "rallies": "求援委託只在那一方的人的懸賞卡（各人自己的畫面），掛單時寫一則陣營傳聞",
        "ending_text": "收季那一刻跟 ended、ending_title 一起寫入",
        "ending_id": "同上",
        "final_trends": "同上（結算卡的資料）",
        "final_rankings": "同上（結算卡的資料）",
        "final_tiers": "同上（結局卡的資料：收季那一刻跟 ended 一起寫，減法季批 3c）",
        "act_reached": "隊伍數與統御上限的內部計數，不畫在共用畫面上",
        "marks": "地方痕跡只畫成模糊人數，改了讓每個分頁多刷新一次會洩漏有人做了看不見的事（推送計畫 F4）",
        "marks_fired": "痕跡過門檻那一刻寫一則地方傳聞（傳聞流水號在指紋裡；世界層那一句 2026-10-25 拿掉）；江湖史在季末",
        "mark_helpers": "誰替痕跡出過力只用來記本人的行狀，不畫在共用畫面上（改了讓每個分頁刷新會洩漏有人做了看不見的事，同 marks）",
        "stance_counts": "人物心意的全服計數（減法季批 6）：只畫在跟他談的人自己的人物頁（自己的動作走 self 通知）；算進去會洩漏有人跟他說了話（同 marks）",
        "stance_week": "心意計數是哪一週的記號，玩家看不到",
        "persona": "人物性子此刻的值（功能包 persona）：只畫在點人物那一層的簡介；換段那一刻另寫傳聞（傳聞流水號已在指紋裡）",
        "persona_day": "人物性子結算到第幾天的記號，玩家看不到",
        "persona_push": "人物性子今天的淨推力：玩家看不到；算進去會洩漏有人跟他說了話（同 stance_counts）",
        "persona_tug": "同上（今天的總份數）",
        "persona_torn": "拉鋸只在結算那一刻變（每天一次），畫在簡介上；簡介跟著人物那一層重讀",
        "persona_log": "換段紀錄：換的那一刻另寫傳聞（傳聞流水號已在指紋裡）",
        "god_names": "特殊頓悟全服神品意境的名字（只拿來擋重名），不畫在共用畫面上；首悟上江湖史走傳聞流水號",
        "god_firsts": "特殊頓悟每個模板這一季第一個悟出的人（江湖史那一句走傳聞流水號），不畫在共用畫面上",
        "stance_active": "人物此刻照哪一個心意做事：換的那一刻另寫天下大事（傳聞流水號已在指紋裡）；週初歸零跟著週初的掛鉤",
        "pending_battle": "背景推進記下要開的戰鬥，開成集結之後 active_battle 的指紋就變了",
        "season_one": "開季時蓋的章，開季之後不變",
        "season21": "開季時蓋的章（21 天季），開季之後不變",
        "precise_actions": "開季時蓋的章（一類一顆），開季之後不變",
        "cal_offset": "開季時蓋的章（21 天季季曆的偏移），開季之後不變",
        "cal_offset_history": "21 天季暫停再繼續時才多一筆（FB-332）：繼續那一下季的時間與排定本來就跟著變",
        "length_days": "同上",
        "locks": "伏筆鎖定不能露出來（推送計畫 Review Focus 1）",
        "lock_losers": "同上",
        "event_mods": "一般伏筆的修正，畫面上看不到（推送計畫 F4）",
        "event_bonus": "時刻表結果帶來的修正，同上",
        "schedule": "只畫成『下一件大事』的倒數；時鐘本來就靠慢速輪詢，管理者改排定很少見（推送計畫沒納入）",
        "hooked_week": "週初掛鉤的內部記號",
        "hooked_day": "21 天季每天掛鉤的內部記號",
        "showdowns_waiting": "排隊等著開的決戰記號，開成集結之後 active_battle 的指紋就變了",
        "showdown_opened_at": "開集結那一刻（輿圖歸週用），跟 showdowns_opened 一起寫，那一下指紋已經變了（FB-563）",
        "showdowns_cancelled": "管理者取消的決戰：取消那一下另寫天下大事（傳聞流水號已在指紋裡），輿圖不列它下次輪詢才補（FB-563）",
        "orders": "陣營軍令只有那個陣營看得到（推送計畫 F4）",
        "plots": "集體密謀只有自己陣營的人看得到（發起的軍情是陣營軍情，不進天下大事的流水號）；算進去，別的陣營會從『又被叫醒了』看出對方有動靜（乙二）",
        "promoted_today": "晉升的每日彙整，進陣營軍情，不是共用畫面",
        "trend_accum": "不足一點的推力累積器（推送計畫 F4）",
        "active_pushers": "人數緩衝的記錄，畫面上看不到（推送計畫 F4）",
        "invites": "玩家之間的邀請只有發的人與收的人看得到，伺服器做完動作直接叫醒他們兩個的分頁（Game.touched）；算進去會叫醒全服",
        "spar_tally": "切磋的每日次數，畫面上看不到",
        "gift_tally": "贈物的每日次數（FB-116），只在玩家卡上那一顆鈕灰不灰，打開卡才重問",
        "discuss_tally": "論武的每日次數（FB-116），只在玩家卡上那一顆鈕灰不灰，打開卡才重問",
        "raids": "截殺的冷卻，只在打開玩家卡時看得到（截殺當下 touched 叫醒被截殺的人）",
        "ambushes": "埋伏是看不見的（設伏劫道）：中伏的那一下 touched 叫醒伏兵",
        "figure_guards": "護衛的崗只寫在挑戰鈕的「身邊有 N 人護衛」與自家人的按鈕上；站崗、擋下都是某個人自己的動作，別人下次輪詢才補也不礙事",
        "aid_tally": "犒軍、探望、聲威回復的每日記數，畫面上看不到",
        "guard_credits": "護衛擋下挑戰、等著補給護衛的那幾句，只在護衛自己同步時領",
        "supply": "屯糧練兵的量只在自家人的按鈕上（自己的動作走 self 通知），開集結那一刻寫天下大事",
        "bounties": "懸賞榜只在城裡打開第二層選單時看得到，揭、交差都是自己的動作（通緝當下 touched 叫醒被通緝的人）",
        "bounty_seq": "懸賞的流水號，玩家看不到",
        "armaments": "陣營的軍備存量（素材與經濟）：捐的人自己那一下的畫面就更新；同陣營其他人的存量等下一次輪詢，不必為它叫醒全服的分頁",
        "bounty_week": "懸賞自動掛單掛到第幾週，玩家看不到",
        "bounty_day": "21 天季懸賞每天掛單掛到第幾天，玩家看不到",
        "raided": "被截殺過的冷卻，只在打開玩家卡時看得到",
        "clashes": "混戰寫進截殺冷卻的那幾筆（FB-607：拒絕話照實寫），跟 raids 一起寫、一樣只在打開玩家卡時看得到",
        "clashed": "混戰被撞的護身是混戰寫的（FB-607），跟 raided 一起寫、一樣只在打開玩家卡時看得到",
        "arena": "擂台的分身與名次只在打開擂台、看擂台榜時看得到；稱號在狀態列，守擂的人的戰報與俸在他自己同步時補",
        "arena_pairs": "挑擂的同一對冷卻，只在打開擂台時看得到",
        "arena_seq": "擂台的流水號，玩家看不到",
        "arena_closed": "擂台這一季收了沒（季末排名寫進江湖史與傳聞，那一下指紋就變了）",
        "arena_day": "擂台的俸記到哪一天，玩家看不到（俸在本人同步時補）",
        "tavern_walls": "酒肆的題壁只在坐進那一間酒肆時看得到；坐在裡面的人照輪詢每十秒重抓",
        "tavern_whispers": "酒肆的風聲在被打聽的人自己同步時補（寫風聲的人另外叫醒他的分頁，Game.touched）",
        "tavern_treats": "請全店喝酒只在坐進那一間酒肆時看得到；請的那一下另有地方傳聞",
        "tavern_hits": "雇殺手（第三批）只在本人同步時結算與補",
        "tavern_hit_seq": "雇殺手的流水號，玩家看不到",
        "tavern_chatter": "酒客閒談（第四批）只在坐進那一間酒肆時看得到",
        "echoes": "首創名望回饋的帳，只在首創者自己同步時補一則紀錄；湊滿時那一句傳聞進 rumors，那一下指紋就變了",
        "seat_ledger": "第四階席次的貢獻帳，畫面上看不到；陣營私有，跟 orders、plots 一樣（正式版丁）",
        "seats": "在任名單只改那個陣營的人自己的頭銜，上任的消息是陣營軍情；算進去，別的陣營會從『又被叫醒了』看出對方有人上任（同 orders、plots，正式版丁）",
        "general_gifts": "名將贈禮給了誰，只寫在拿到的人自己的江湖紀錄裡（裝備四欄 6.4）",
        "secret_sets": "「裝滿」秘方這一季誰先暗合；傳聞與江湖史另有自己的欄位，這裡只記先後",
        "signature_arms": "名將本命兵器給了誰，只寫在拿到的人自己的江湖紀錄裡；江湖史與天下大事傳聞進 chronicle、rumors，那一下指紋就變了（兵器設計 4.10）",
        "tianji": "開季時蓋進季裡的天機，開季之後不變（週初掛單的重賞亂數用）",
        "forge_divine_per_kind": "開季時蓋的章（素材與經濟），開季之後不變",
        "forge_split_clues": "開季時蓋的章（素材與經濟），開季之後不變",
        "divine_lineup": "開季時蓋的章（神器輪替），開季之後不變",
        "renown_scale": "開季時蓋的章（名聲的門檻倍數），開季之後不變",
        "mandate": "天命之季的章：蓋章時另寫天下大事（傳聞流水號已在指紋裡）",
        "mandate_result": "天命之爭定下來時跟時間軸、天下大事一起寫入",
        "territory": "地盤的控制方只跟著戰線、割據（trends）與大事（timeline）改；易手的那一下另寫天下大事（傳聞流水號已在指紋裡），第一次算不發也不必叫醒誰",
        "conquest_on": "開季時蓋的章（領地爭奪），開季之後不變",
        "jianfa_on": "開季時蓋的章（減法季），開季之後不變",
        "attrs_v2": "開季時蓋的章（五項屬性），開季之後不變",
        "conquest": "領地爭奪的開季種類、偏移與進度：易手另寫天下大事（傳聞流水號已在指紋裡），偏移跟著 trends 一起改；"
                    "進度不露數字、只回推的人自己那一句話",
        "xingshi": "〈天下形勢〉收下的文章：收下那一刻另寫天下大事與江湖史（都在指紋裡）；見聞「形勢」頁自己去讀，不叫醒全服",
        "xingshi_ticket": "還在等模型寫的那一張單，誰都看不到",
        "xingshi_mark": "上一篇讀到哪裡的記號，玩家看不到",
        "seal_acts": "玉璽碎片的獨門行動（改版第 2 批）：起用那一下另寫天下大事與江湖史（都在指紋裡）；引將期滿回原處改的是 figures（算進指紋）",
    },
    "BattleInstance": {
        "muster_deadline_real": "現實時間的期限，畫面上的倒數靠輪詢（推送計畫 F4）",
        "participants": "誰加入、誰出手了，畫面上看不到；這一回合送出幾個的人數算在 round 那一格（推送計畫 F2）",
        "act_index": "換幕只在 round_number 加一的那一下發生",
        "narrative_log": "戰報的敘事一回合結算才加一行，那一下 round_number 也變了",
        "tactic_kinds": "戰法名 → kind 只在回合結算時跟著 narrative_log 一起加，那一下 round_number 也變了",
        "last_mix": "上一回合兩邊的出招比例，一回合結算才改，那一下 round_number 也變了（每個人的份量與上一回合的結果在 participants 裡，同它）",
        "outcome_title": "收場時跟 phase 一起寫入",
        "outcome_text": "同上",
        "outcome_world_flags": "同上",
        "outcome_trend_delta": "同上",
        "end_time": "同上",
        "unfinished_text": "同上",
        "unfinished": "同上",
        "record_id": "資料庫裡的流水號，不是畫面",
        "rounds": "還沒寫進資料庫的回合緩衝，不是畫面",
        "trend_start": "開打時就定了，跟 phase 一起寫入",
        "swings": "每回合戰局怎麼走，一回合結算才加一筆，那一下 round_number 也變了",
        "mvps": "每回合的 MVP（looks 的 mvp.crown），一回合結算才加一筆，那一下 round_number 也變了",
        "marked": "誰在這一幕顯眼，只在回合結算時改，那一下 round_number 也變了",
        "last_targets": "上一回合誰被點名，只在回合結算時改，那一下 round_number 也變了",
        "outcome_reason": "收場時跟 phase 一起寫入",
        "outcome_side": "收場時跟 phase 一起寫入（軍餉看誰贏）",
        "outcome_margin": "收場時跟 phase 一起寫入",
        "highlight": "最有戲的放手一搏：跟著回合結算變（回合已經算進指紋），收場時寫進傳聞",
        "seal_emerge": "現世擲中了：集結那一刻另寫天下大事（3.4），指紋本來就變了",
        "seal_shard": "璽動牽動哪一片：另寫天下大事（4.3）",
        "seal_holder": "同上",
        "seal_holder_faction": "同上（快照，畫面上看不到）",
        "seal_holder_side": "同上",
        "seal_notes": "收場時跟 phase 一起寫入（戰報那一行）",
        "seal_lean": "天命之爭開集結那一刻快照（集結公告另寫天下大事，指紋本來就變了）",
        "supply_lean": "屯糧練兵開集結那一刻快照（集結公告另寫天下大事，指紋本來就變了）",
        "front_note": "起點照哪一條戰線：開集結那一刻快照（另寫天下大事，指紋本來就變了），之後不再改",
        "commanders": "上陣的大勢人物：開集結那一刻派上來（另寫天下大事），氣血與敗走只在回合結算時改，那一下 round_number 也變了",
        "orders": "主將令：回合結算那一下換，round_number 也變了",
        "siege": "攻城戰打哪一塊、誰攻：開集結那一刻就定了（跟 phase 一起寫入）；收場的易手另寫天下大事（傳聞流水號已在指紋裡）",
    },
}


WORLD_MODELS = {"SharedWorldState": SharedWorldState, "WorldState": WorldState, "BattleInstance": battle_instance.BattleInstance}


def test_every_shared_world_field_is_classified_for_the_push_fingerprint():
    """新欄位兩邊都沒寫就紅：逼加欄位的人當場決定它算不算進推送的指紋。"""
    for name, model in WORLD_MODELS.items():
        counted, ignored = set(FINGERPRINTED[name]), set(NOT_IN_THE_FINGERPRINT[name])
        assert not counted & ignored, f"{name} 同時在兩邊：{sorted(counted & ignored)}"
        assert set(model.model_fields) == counted | ignored, (
            f"{name} 的欄位沒分類或寫錯了：沒分類 {sorted(set(model.model_fields) - counted - ignored)}，"
            f"不存在 {sorted((counted | ignored) - set(model.model_fields))}——見 FINGERPRINTED／NOT_IN_THE_FINGERPRINT 上面的說明"
        )
        assert all(reason.strip() for reason in NOT_IN_THE_FINGERPRINT[name].values()), name


@pytest.mark.parametrize(
    ("name", "field"),
    [(name, field) for name, fields in FINGERPRINTED.items() for field, change in fields.items() if change != _SEASON],
)
def test_every_field_counted_in_the_push_fingerprint_really_changes_it(name, field):
    """上面說「算進指紋」的欄位，真的改了就讓 server.current_fingerprint() 變（不是只寫在清單上）。每個欄位自己一個資料庫。"""
    world = open_world()
    world.seed_first_season(server.CONTENT)
    if world.season_phase() == "preparing":
        world.open_season(server.CONTENT, 1000.0)

    def setup(st):
        st.season.trends, st.season.revealed = {"t": 10, "h": 5}, {"t"}  # 一條浮現的、一條隱藏的
        st.active_battle = battle_instance.BattleInstance(battle_id="changshe_fire")

    world.mutate(setup)
    before = server.current_fingerprint()
    world.mutate(FINGERPRINTED[name][field])
    assert server.current_fingerprint() != before, f"{name}.{field} 改了，指紋沒變"


def _three_read_fingerprint() -> str:
    """推送看守原本的讀法：三次各自的快照，還把這一季每一則傳聞與江湖史讀回來數。新的讀法（一次快照加 MAX／COUNT）要跟它一樣。"""
    world = open_world()
    shared = world.read()
    return server_push.world_fingerprint(
        shared.season_number, shared.season_phase(), world.get_season(), world.get_battle(),
        paused=shared.paused_at is not None,
    )


def test_the_one_snapshot_fingerprint_is_the_old_three_read_one_on_every_state():
    """m2：同樣的東西算進去、同樣的東西不算（F2 的決戰、F4 的排除項），在一連串不同的狀態裡每一步都跟舊的算法一樣，
    該變的變、不該變的不變。"""
    world = open_world()
    content = server.CONTENT
    revealed = []

    def trend_up(season):
        key = revealed[0]
        season.trends[key] += 1

    def nudge_trend():
        world.mutate_season(trend_up)

    def pick_revealed():
        revealed.append(next(iter(world.get_season().revealed)))

    def rumors(*items):
        return lambda: world.mutate_season(lambda s: s.rumors.extend(items))

    steps = [  # (這一步, 指紋會不會變)
        (lambda: world.seed_first_season(content), True),
        (pick_revealed, False),
        (rumors(Rumor(time=1.0, text="天下大事", layer="world")), True),
        (rumors(Rumor(time=1.0, text="軍情", layer="faction", faction="guan"),
                Rumor(time=1.0, text="地方", layer="local", region="yingchuan"),
                Rumor(time=1.0, text="只有你", layer="personal", character="甲")), False),
        (rumors(Rumor(time=3.0, text="又一則天下大事", layer="world")), True),
        (lambda: world.mutate_season(lambda s: s.chronicle.append(Rumor(time=2.0, text="江湖史一筆"))), True),
        (nudge_trend, True),
        (lambda: world.mutate_season(lambda s: s.locks.__setitem__("changshe_fire", Lock(side="guan", name="甲", time=1.0))), False),
        (lambda: world.start_battle(content.battles["huangjin_showdown"], now=0.0), True),
        (lambda: world.mutate_battle(lambda b: battle_instance.join_faction(b, "乙玩家", "huang", neili_cap=320.0)), False),
        (lambda: world.mutate_battle(lambda b: setattr(b, "trend", b.trend + 3)), True),
        (lambda: world.mutate_season(lambda s: s.timeline.__setitem__("uprising", TimelineResult(key="fixed", time=0.0))), True),
        (lambda: world.mutate_season(lambda s: setattr(s, "ended", True)), True),
        (lambda: world.next_season(content, now=1.0), True),
    ]
    assert server.current_fingerprint() == _three_read_fingerprint()  # 還沒有賽季的空資料庫
    for number, (step, changes) in enumerate(steps):
        before = server.current_fingerprint()
        step()
        now = server.current_fingerprint()
        assert now == _three_read_fingerprint(), number
        assert (now != before) is changes, number


def test_main_view_drops_the_battle_scene_when_its_own_poll_settles_the_battle():
    """U-06（手機介面自檢 2026-10-31）：場景先讀、選單才把決戰推到收場——以前「剛剛」已經寫了結果，場景還停在最後一回合
    「已送出 0／在場 0」。現在同一次回的場景就回到地點；U-08：上過陣的人全倒下了，這一下就收場，不等回合逾時。"""
    from jianfa_kit import jianfa_game, ready

    game = ready(jianfa_game("week7", name="Rayal"), side="guan", loc="changshe", level=20)
    game.now = 1000.0
    game.admin_start_showdown("changshe_fire", game.now)
    game.choose("battle:join:guan")
    game.now = game.world.get_battle().muster_deadline_real + 1
    game.options()
    assert game.world.get_battle().phase == "active"

    def fall(battle):
        for p in battle.participants.values():
            p.eliminated = True
    game.world.mutate_battle(fall)
    game.now += 5  # 遠不到回合逾時
    view = server.main_view(game)
    assert game.world.get_battle().phase == "ended"
    assert "回合" not in view["scene"] and "在場" not in view["scene"]
    assert "長社" in view["scene"]  # 回到地點描述；結果在「剛剛」與戰報
