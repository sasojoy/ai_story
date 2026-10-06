"""伺服器主動通知（線上架構設計 5.3）：只送「哪一種變了」；指紋只看公開的東西。"""
import asyncio
import threading

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import server_push
from tianxia.battle_instance import BattleInstance, BattleParticipant
from tianxia.state import FigureState, Lock, Order, Rumor, TimelineResult, WorldState


def _listen(hub, name):
    """開一個事件迴圈、訂閱 name；回傳 (收到的清單, 執行緒, 迴圈)。收到 None（hub.close）就退訂、結束。"""
    got, ready = [], threading.Event()
    loop = asyncio.new_event_loop()

    async def main():
        queue: asyncio.Queue = asyncio.Queue()
        hub.subscribe(name, loop, queue)
        ready.set()
        while True:
            item = await queue.get()
            if item is None:
                break
            got.append(item)
        hub.unsubscribe(name, loop, queue)

    thread = threading.Thread(target=lambda: loop.run_until_complete(main()))
    thread.start()
    assert ready.wait(2)
    return got, thread, loop


def _finish(thread, loop):
    thread.join(2)
    loop.close()


def test_notify_reaches_only_that_character_and_broadcast_reaches_all():
    hub = server_push.PushHub()
    a, ta, la = _listen(hub, "甲")
    b, tb, lb = _listen(hub, "乙")
    assert hub.count() == 2
    assert hub.notify("甲") == 1
    assert hub.broadcast() == 2
    hub.close()
    _finish(ta, la)
    _finish(tb, lb)
    assert a == ["self", "world"] and b == ["world"]
    assert hub.count() == 0  # 斷了就退訂，不會越積越多（Review Focus 4）


def test_notify_nobody_listening_is_fine():
    assert server_push.PushHub().notify("沒人") == 0


def test_a_closed_loop_does_not_raise():
    """分頁關了、它的事件迴圈也關了，還沒來得及退訂：送過去不丟例外（Review Focus 4）。"""
    hub = server_push.PushHub()
    loop = asyncio.new_event_loop()
    hub.subscribe("甲", loop, asyncio.Queue())
    loop.close()
    assert hub.notify("甲") == 0


def _season():
    s = WorldState(storyline="main")
    s.trends = {"yingru": 40, "hidden": 5}
    s.revealed = {"yingru"}
    return s


def _fp(season, battle=None):
    return server_push.world_fingerprint(2, "running", season, battle)


def _order(**kw):
    return Order(id="o1", template="raid", faction="guan", week=1, quota=3, text="軍令", **kw)


def test_fingerprint_ignores_time_locks_and_hidden_things():
    """時間、鎖定、搶輸、豪強、隱藏的大勢線、陣營軍情都不算（伏筆鎖定看不出來，Review Focus 1）。"""
    s = _season()
    base = _fp(s)
    s.time += 3600
    s.locks["changshe_fire"] = Lock(side="guan", name="甲", time=1.0)
    s.lock_losers["changshe_fire"] = [Lock(side="huang", name="乙", time=2.0)]
    s.third_party["changshe_fire"] = ["丙"]
    s.third_party_shown["changshe_fire"] = {"丙": "某位少俠"}
    s.trends["hidden"] = 9
    s.rumors.append(Rumor(time=1.0, text="陣營的事", id=5, layer="faction", faction="guan"))
    assert _fp(s) == base


def test_fingerprint_ignores_what_only_some_players_can_see_or_nobody_can():
    """軍令、地方傳聞、個人線索、一般伏筆的修正、世界旗標、地方痕跡、推力的累積都不算（預檢 F4）：
    它們改了，沒有哪個人的畫面看得出全服的變化，卻會讓每個分頁多一次刷新，洩漏「有人做了看不見的事」。"""
    s = _season()
    base = _fp(s)
    s.orders.append(_order())
    s.orders[0].progress["甲"] = 2
    s.orders[0].done = True
    s.rumors.append(Rumor(time=1.0, text="某地的事", id=6, layer="local", region="yingchuan"))
    s.rumors.append(Rumor(time=1.0, text="只有甲聽到", id=7, layer="personal", character="甲"))
    s.event_mods["changshe_fire"] = 0.1
    s.event_bonus["changshe_fire"] = 0.05
    s.flags.add("某旗標")
    s.flag_times["某旗標"] = 3.0
    s.fired_thresholds.add("huangjin_60")
    s.marks["yingchuan:火光"] = 2
    s.trend_accum["yingru"] = 0.4
    s.active_pushers["guan"] = {"甲": 9.0}
    s.promoted_today["guan:3"] = ["甲"]
    s.schedule["changshe_fire"] = 12345.0
    s.showdowns_waiting.append("changshe_fire")
    s.sim_accum = 120.0
    assert _fp(s) == base


def test_fingerprint_ignores_who_has_joined_a_battle_and_who_has_acted():
    """決戰的人數、這一回合出手了幾個，畫面上哪裡都看不到，而且跟著假人的節奏變（預檢 F2）：不算。
    算了的話，每個人加入、每個人送出行動都讓全服刷新一次，看得出假人在做什麼。"""
    battle = BattleInstance(battle_id="changshe_fire")
    base = _fp(_season(), battle)
    battle.participants["甲"] = BattleParticipant(name="甲", faction="guan", neili=100, neili_cap=100)
    battle.participants["乙"] = BattleParticipant(name="乙", faction="huang", neili=100, neili_cap=100)
    assert _fp(_season(), battle) == base
    battle.round.pending_actions["甲"] = "safe"
    battle.round.custom_texts["乙"] = "直取首級"
    battle.round.success_rates["乙"] = 20
    battle.muster_deadline_real += 5
    battle.narrative_log.append("暗處的一句")
    assert _fp(_season(), battle) == base


def test_fingerprint_sees_public_changes():
    base = _fp(_season())
    s = _season()
    s.trends["yingru"] = 41
    assert _fp(s) != base
    s = _season()
    s.chronicle.append(Rumor(time=1.0, text="江湖史一筆"))
    assert _fp(s) != base
    s = _season()
    s.timeline["uprising"] = TimelineResult(key="fixed", time=0.0)
    assert _fp(s) != base
    s = _season()
    s.rumors.append(Rumor(time=1.0, text="天下大事", id=9, layer="world"))
    assert _fp(s) != base
    assert _fp(_season(), BattleInstance(battle_id="changshe_fire")) != base


def test_fingerprint_takes_the_rumor_and_chronicle_counts_instead_of_the_rows():
    """看守不把每一則傳聞與江湖史讀回來（m2）：資料庫算好最大的天下大事傳聞編號與江湖史則數，直接給；給了的跟從資料列算出來的是同一個指紋。"""
    s = _season()
    s.rumors.append(Rumor(time=1.0, text="天下大事", id=9, layer="world"))
    s.rumors.append(Rumor(time=1.0, text="地方", id=12, layer="local", region="yingchuan"))
    s.chronicle.append(Rumor(time=1.0, text="江湖史一筆", id=3))
    from_rows = _fp(s)
    bare = _season()  # 一列都沒有，只給數字
    assert server_push.world_fingerprint(2, "running", bare, None, rumor_id=9, chronicle_count=1) == from_rows
    assert server_push.world_fingerprint(2, "running", bare, None, rumor_id=10, chronicle_count=1) != from_rows
    assert server_push.world_fingerprint(2, "running", bare, None, rumor_id=9, chronicle_count=2) != from_rows
    assert server_push.world_fingerprint(2, "running", bare, None, rumor_id=0, chronicle_count=0) == _fp(_season())


def test_fingerprint_sees_the_other_public_parts_of_the_world():
    base = _fp(_season())
    s = _season()
    s.trends["hidden"] = 9
    s.revealed.add("hidden")  # 大勢線浮現了：現在大家看得到它
    assert _fp(s) != base
    s = _season()
    s.act = 1
    assert _fp(s) != base
    s = _season()
    s.ending_title = "天下大亂"
    assert _fp(s) != base
    s = _season()
    s.showdowns_opened["changshe_fire"] = "changshe_fire"
    assert _fp(s) != base
    s = _season()
    s.figures["lu_zhi"] = FigureState(prestige=70)
    assert _fp(s) != base
    assert server_push.world_fingerprint(3, "running", _season(), None) != base  # 換季
    assert server_push.world_fingerprint(2, "resting", _season(), None) != base  # 休季


def test_fingerprint_sees_the_season_clock_pause():
    """暫停賽季時鐘，每個人的選單都變成一顆灰的：算（有沒有暫停；停了幾分鐘不算，見 server 的 paused_at 測試）。"""
    base = _fp(_season())
    assert server_push.world_fingerprint(2, "running", _season(), None, paused=True) != base
    assert server_push.world_fingerprint(2, "running", _season(), None, paused=False) == base


def test_fingerprint_sees_a_battle_move_on_visibly():
    """決戰的階段、回合、戰局變了，每個人的畫面都不一樣：要算。"""
    base = _fp(_season(), BattleInstance(battle_id="changshe_fire"))
    for change in ({"phase": "active"}, {"round_number": 1}, {"trend": 55}, {"battle_id": "wancheng"}):
        assert _fp(_season(), BattleInstance(**{"battle_id": "changshe_fire", **change})) != base, change


def test_watch_world_debounces_and_skips_errors():
    """世界一直在變：兩次 world 至少隔 min_interval，被壓下來的變化時間到了照發（Review Focus 3）；讀不到就跳過。"""
    hub = server_push.PushHub()
    sent = []
    hub.broadcast = lambda kind="world": sent.append(kind) or 1
    readings = iter(["a", "a", "b", RuntimeError("讀不到"), "c", "d"])
    # 第一筆 a 只當起點、不讀時鐘；之後每讀到一筆就讀一次時鐘：a（0）沒變；b（100）發；讀不到跳過；
    # c（105）離上次不到 10 秒不發；d（120）發
    times = iter([0.0, 100.0, 105.0, 120.0])
    stop = threading.Event()

    def fp():
        v = next(readings, None)
        if v is None:
            stop.set()
            return "d"
        if isinstance(v, Exception):
            raise v
        return v

    server_push.watch_world(hub, fp, stop, interval=0.0, min_interval=10.0, clock=lambda: next(times, 999.0))
    assert sent == ["world", "world"]


def _watch(readings, **kw):
    """跑看守：照 readings 一輪一筆（Exception 就丟），用完就停；回傳 (發出去的 world 清單, 看守輪數)。"""
    hub = server_push.PushHub()
    sent = []
    hub.broadcast = lambda kind="world": sent.append(kind) or 1
    queue = iter(readings)
    stop = threading.Event()
    latest = ["start"]

    def fp():
        v = next(queue, None)
        if v is None:
            stop.set()
            return latest[0]  # 用完就停；停之前那一輪讀到的跟上一次一樣，不算變化
        if isinstance(v, Exception):
            raise v
        latest[0] = v
        return v

    server_push.watch_world(hub, fp, stop, interval=0.0, min_interval=0.0, clock=lambda: 0.0, **kw)
    return sent


def test_watch_world_reports_a_failed_round_without_printing_it(capsys):
    """讀不到世界：把例外交給 on_error（伺服器那邊只寫例外的類別、同一個錯只數次數），看守自己什麼都不印
    （例外的訊息常夾著名號，預檢 F5）；每一輪不論成敗都叫一次 on_round（那邊用它定時印累計）。"""
    failed, rounds = [], []
    _watch(["a", KeyError("某某人的名號"), "a", ValueError("又一個"), "b"], on_error=failed.append, on_round=lambda: rounds.append(1))
    assert [type(e) for e in failed] == [KeyError, ValueError]
    assert len(rounds) == 6  # 五筆讀數加上最後那一輪（停之前）
    shown = capsys.readouterr()
    assert shown.out == "" and shown.err == ""


def test_watch_world_keeps_going_when_the_error_callback_itself_fails():
    """記錄不能讓看守停下來：on_error、on_round 自己丟例外也照樣下一輪。"""
    def bad(*args):
        raise OSError("主控台不見了")

    sent = _watch(["a", RuntimeError("x"), "b", "c"], on_error=bad, on_round=bad)
    assert sent == ["world", "world"]


def test_watch_world_without_callbacks_stays_silent(capsys):
    assert _watch(["a", RuntimeError("夾著名號"), "b"]) == ["world"]
    shown = capsys.readouterr()
    assert shown.out == "" and shown.err == ""


def test_watch_world_keeps_a_suppressed_change_for_later():
    """壓下來的變化不能丟：離上次發出去不到 min_interval 的變化不記下來，下一輪照樣看得出來，時間到了就發（只發一次）。"""
    hub = server_push.PushHub()
    sent = []
    hub.broadcast = lambda kind="world": sent.append(kind) or 1
    readings = iter(["a", "b", "c", "c", "c"])
    # a 是起點；b（100）發；c（105）離上次 5 秒不發；c（112）離上次 12 秒、還是跟發出去的 b 不同：發；c（113）已經發過：不再發
    times = iter([100.0, 105.0, 112.0, 113.0])
    stop = threading.Event()

    def fp():
        v = next(readings, None)
        if v is None:
            stop.set()
            return "c"
        return v

    server_push.watch_world(hub, fp, stop, interval=0.0, min_interval=10.0, clock=lambda: next(times, 999.0))
    assert sent == ["world", "world"]


def test_sse_stream_heartbeat_events_and_end():
    hub = server_push.PushHub()

    async def run():
        gen = server_push.sse_stream(hub, "甲", heartbeat=0.05)
        out = [await gen.__anext__()]  # retry
        out.append(await gen.__anext__())  # 沒事：心跳
        hub.notify("甲")
        out.append(await gen.__anext__())
        hub.close()
        rest = [chunk async for chunk in gen]
        return out, rest

    out, rest = asyncio.run(run())
    # 心跳是一個叫 ping 的事件、不是註解：註解到不了頁面的 JS，頁面就分不出「連線還活著」與「半開的死連線」（預檢 F6）
    assert out == ["retry: 5000\n\n", "event: ping\ndata: {}\n\n", "event: self\ndata: {}\n\n"] and rest == []
    assert hub.count() == 0


def test_sse_stream_unsubscribes_when_the_client_goes_away():
    """連線被切（Starlette 取消這個串流）：照樣退訂，不會越積越多（Review Focus 4）。"""
    hub = server_push.PushHub()

    async def run():
        gen = server_push.sse_stream(hub, "甲", heartbeat=60)
        await gen.__anext__()
        assert hub.count() == 1
        await gen.aclose()

    asyncio.run(run())
    assert hub.count() == 0


class _OneShot(server_push.PushHub):
    """一訂閱就送一則再收尾：TestClient 要等整份回應收完才回來，不會結束的串流測不了（Task 2 也用它）。"""

    def subscribe(self, name, loop, queue):
        super().subscribe(name, loop, queue)
        self.notify(name)
        self.close()


def test_sse_stream_through_an_endpoint():
    hub = _OneShot()
    app = FastAPI()

    @app.get("/api/events")
    async def events():
        return StreamingResponse(server_push.sse_stream(hub, "甲"), media_type="text/event-stream")

    r = TestClient(app).get("/api/events")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text == "retry: 5000\n\nevent: self\ndata: {}\n\n"
