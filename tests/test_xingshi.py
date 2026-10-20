"""領地爭奪第三批 A：〈天下形勢〉（設計 3.10；計畫第五章 Task 16、17，第六章 6.3、6.4）。

每天 22:00 結算那一刻（Game._conquest_tick）開一張單：事實是上一篇以來的 day_log（易手、守住、作罷、主將為什麼挑那一塊）、三條線比前一篇
往哪一邊動、天下大事（不帶數字的那幾則）。伺服器鎖外請模型寫一篇（server.write_xingshi → xingshi_once，三段式），寫不出來、過
grace_seconds 沒交回，照固定段收（下一個同步的人、或伺服器排程）。收下那一刻天下大事一則、江湖史一筆、見聞「形勢」頁多一篇。
模型不給任何數字；假人程式的 Game 沒有 client，不叫模型。"""
from __future__ import annotations

import calendar as pycal
import re
from datetime import datetime

import pytest

import server
from conquest_kit import announce, conquest_game, go, join
from tianxia import conquest, rules, siege, xingshi
from tianxia.engine import Game

DIGITS = re.compile(r"[0-9０-９]")
ESSAY = "　　是日也，" + "南陽一帶兵戈不息，黃巾漸佔上風，官軍據城自守，未敢輕出。" * 6  # 一篇寫得好好的（一百二十字以上）


def _tw(y, mo, d, h, mi=0) -> float:
    """台灣時間 → 現實 epoch 秒（同 test_conquest_settle._tw）。"""
    return float(pycal.timegm(datetime(y, mo, d, h, mi).timetuple())) - 8 * 3600


def _game(now: float, name: str = "沈浪", side: str = "huang", on: bool = True, world=None) -> Game:
    game = join(conquest_game("season21", name=name, world=world, xingshi=on), side)
    game.now = now
    return game


def _tick(game: Game, now: float):
    game.now = now
    game._conquest_tick()
    game.state.world = game.world.get_season()
    return game.state.world


def _world_rumors(game: Game) -> list[str]:
    return [r.text for r in game.world.get_season().rumors if r.layer == "world"]


DAY0 = _tw(2026, 10, 20, 10)  # 這一季第一次同步：只記下今天
SETTLE = _tw(2026, 10, 20, 22, 1)  # 換天：結算、開一張單


# ── 純規則（不建 Game）──


def test_clean_rejects_digits_kana_and_length():
    assert xingshi.clean(ESSAY) == ESSAY.strip()
    assert xingshi.clean("天下未定。") is None  # 太短
    assert xingshi.clean(ESSAY + "官軍一連拿下3處") is None  # 阿拉伯數字（全形也算）
    assert xingshi.clean(ESSAY + "拿下３處") is None
    assert xingshi.clean(ESSAY + "ひらがな") is None  # 假名
    assert xingshi.clean("天下" * 450) is None  # 太長
    assert xingshi.clean("## 天下形勢\n" + ESSAY).startswith("天下形勢")  # 去 markdown 的標記
    assert xingshi.clean(ESSAY + "天下大势未定。").endswith("天下大勢未定。")  # 轉繁體


@pytest.mark.slow
def test_switch_off_no_ticket():
    """〈天下形勢〉關著（Config.xingshi.enabled，conquest_kit 的預設）：結算照舊，季上的形勢欄位一個都不動。"""
    game = _game(DAY0, on=False)
    _tick(game, DAY0)
    w = _tick(game, SETTLE)
    assert w.conquest.schedule  # 結算照舊排了明天的攻城
    assert w.xingshi_ticket is None and w.xingshi == [] and w.xingshi_mark is None
    assert game.xingshi_view() == {"on": False}


@pytest.mark.slow
def test_ticket_opens_with_the_daily_settle():
    game = _game(DAY0)
    w = _tick(game, DAY0)
    assert w.xingshi_ticket is None and w.xingshi_mark is not None  # 第一次只記下起點（三條線此刻的值）
    assert set(w.xingshi_mark.lines) == set(rules.front_ids(game.content))
    w = _tick(game, SETTLE)
    t = w.xingshi_ticket
    assert t is not None and t.n == 1 and t.key == w.conquest.settled_key and not t.taken
    assert t.line.startswith(xingshi.SUMMARY_HEAD)
    assert t.facts and not [f for f in t.facts if DIGITS.search(f)]  # 事實不帶數字（文章也不准有）
    places = {game.content.locations[s.loc].name for s in w.conquest.schedule}
    assert any(p in f for p in places for f in t.facts)  # 明天打哪裡、主將為什麼挑那裡
    lines = {tr.name for tr in game.content.scenario.trends if tr.id in rules.front_ids(game.content)}
    assert all(any(name in f for f in t.facts) for name in lines)  # 三條線各一句
    again = _tick(game, _tw(2026, 10, 20, 22, 10))  # 同一天再同步（還沒過 grace）：不重開
    assert again.xingshi_ticket.n == 1 and again.xingshi == []


@pytest.mark.slow
def test_outcomes_are_noted_in_the_day_log_and_summed_up():
    """易手、守住寫進 day_log（DayNote.result），〈天下形勢〉照它寫「是日：…」與事實。"""
    game = go(_game(DAY0), "nanyang_road")
    _tick(game, DAY0)
    slot = announce(game, "nanyang_road", "huang")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, game.now)
    game.state.world = game.world.get_season()
    battle = game.world.get_sieges()[0]

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", 10, game.state.world.time  # 黃巾大勝

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, _close))
    game.state.world = game.world.get_season()
    notes = [n for n in game.state.world.conquest.day_log if n.result]
    assert len(notes) == 1
    note = notes[0]
    assert (note.result, note.taken, note.loc, note.attackers) == ("taken", "huang", "nanyang_road", ["huang"])
    assert note.margin == "大勝" and note.keeper == "guard"
    huang = game.content.scenario.faction_name("huang", "huang")
    t = _tick(game, SETTLE).xingshi_ticket
    assert f"{huang}拿下南陽官道" in t.line
    assert any("南陽官道" in f and huang in f and "大勝" in f for f in t.facts)


@pytest.mark.slow
def test_held_and_void_are_noted():
    game = go(_game(DAY0), "nanyang_road")
    _tick(game, DAY0)
    slot = announce(game, "nanyang_road", "huang")
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, game.now)
    game.state.world = game.world.get_season()
    battle = game.world.get_sieges()[0]

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", 60, game.state.world.time  # 守將守住（戰局往官軍那一格偏）

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, _close))
    game.state.world = game.world.get_season()
    note = next(n for n in game.state.world.conquest.day_log if n.result)
    assert (note.result, note.taken, note.keeper) == ("held", "", "guard")
    t = _tick(game, SETTLE).xingshi_ticket
    assert "守住南陽官道" in t.line


@pytest.mark.slow
def test_grace_falls_back_to_rule_text():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    before = _world_rumors(game)
    w = _tick(game, SETTLE + 899)  # 還在等模型
    assert w.xingshi_ticket is not None and w.xingshi == []
    w = _tick(game, SETTLE + 901)  # 過了 grace_seconds：下一個同步的人照固定段收
    assert w.xingshi_ticket is None and len(w.xingshi) == 1
    essay = w.xingshi[0]
    assert essay.by_rule and essay.n == 1 and essay.essay and not DIGITS.search(essay.essay)
    news = _world_rumors(game)[len(before):]
    assert len(news) == 1 and news[0].startswith(xingshi.RUMOR_HEAD)
    assert [c.text for c in w.chronicle if c.text.startswith(xingshi.RUMOR_HEAD)] == news  # 江湖史一筆，同一句


@pytest.mark.slow
def test_grace_also_runs_on_the_server_schedule():
    """沒人上線：伺服器排程（Game.for_world 的 world_tick）照樣收得掉。"""
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    ticker = Game.for_world(game.content, game.world)
    ticker.world_tick(SETTLE + 901)
    w = game.world.get_season()
    assert w.xingshi_ticket is None and len(w.xingshi) == 1 and w.xingshi[0].by_rule


@pytest.mark.slow
def test_model_essay_is_kept_and_stale_request_is_dropped():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    req = game.xingshi_request()
    assert req is not None and req.n == 1 and req.facts and req.line
    assert game.state.world.xingshi_ticket.taken  # 拿走了
    assert game.xingshi_request() is None  # 不會再拿一次
    assert game.settle_xingshi(req, ESSAY)
    w = game.world.get_season()
    assert w.xingshi_ticket is None and w.xingshi[0].essay == ESSAY.strip() and not w.xingshi[0].by_rule
    assert not game.settle_xingshi(req, ESSAY)  # 收過了：同一張單再來一次不收
    assert len(game.world.get_season().xingshi) == 1


@pytest.mark.slow
def test_a_new_day_settles_the_pending_one_by_rule_and_old_requests_are_stale():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    old = game.xingshi_request()
    w = _tick(game, SETTLE + 86400)  # 一天過去（中間沒人收）：舊的照固定段收、開新的
    assert [e.n for e in w.xingshi] == [1] and w.xingshi[0].by_rule
    assert w.xingshi_ticket.n == 2
    game.state.world = w
    assert not game.settle_xingshi(old, ESSAY)  # 舊單：丟掉
    w = game.world.get_season()
    assert w.xingshi_ticket.n == 2 and len(w.xingshi) == 1


@pytest.mark.slow
def test_a_bad_essay_falls_back_to_the_rule_text():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    req = game.xingshi_request()
    assert game.settle_xingshi(req, ESSAY + "共3處")
    essay = game.world.get_season().xingshi[0]
    assert essay.by_rule and not DIGITS.search(essay.essay)


@pytest.mark.slow
def test_lines_compare_with_the_last_essay():
    game = _game(DAY0)
    _tick(game, DAY0)
    rules.change_trend(game.state, game.content, "nanyang", 10)  # 南陽往黃巾推了一截
    game._save_season()
    t = _tick(game, SETTLE).xingshi_ticket
    huang = game.content.scenario.faction_name("huang", "huang")
    nanyang = next(tr.name for tr in game.content.scenario.trends if tr.id == "nanyang")
    fact = next(f for f in t.facts if f.startswith(nanyang))
    assert huang in fact and xingshi.lines(game.content)["move"]["toward"].format(side=huang) in fact


@pytest.mark.slow
def test_view_lists_newest_first():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    _tick(game, SETTLE + 901)
    _tick(game, SETTLE + 86400)  # 第二篇開單
    view = game.xingshi_view()
    assert view["on"] and view["pending"]  # 今天這一篇還在寫
    assert [e["n"] for e in view["essays"]] == [1]
    e = view["essays"][0]
    assert e["title"] == xingshi.HEAD.format(n=1) and e["line"].startswith(xingshi.SUMMARY_HEAD) and e["essay"] and e["time"]
    assert "by_rule" not in e  # 看不出是不是模型寫的
    _tick(game, SETTLE + 86400 + 901)
    assert [e["n"] for e in game.xingshi_view()["essays"]] == [2, 1]


@pytest.mark.slow
def test_admin_opens_one_now():
    game = _game(DAY0, name="Rayal")
    _tick(game, DAY0)
    msgs = game.admin_xingshi_now()
    assert msgs and game.world.get_season().xingshi_ticket is not None
    other = _game(DAY0, name="乙某", world=game.world)
    assert other.admin_xingshi_now() and game.world.get_season().xingshi_ticket.n == 1  # 不是管理者：被擋（沒有多開一張）


# ── 伺服器：鎖外寫文章（三段式）──


class _Fake:
    """假 client：chat_structured 回一篇，或丟例外。"""

    def __init__(self, essay: str | None = None, fail: bool = False):
        self.essay, self.fail, self.calls = essay, fail, []

    def chat_structured(self, messages, model, **kwargs):
        self.calls.append((messages, kwargs))
        if self.fail:
            raise RuntimeError("模型叫不動")
        return model(essay=self.essay or "")

    def with_timeout(self, seconds):
        return self


@pytest.mark.slow
def test_server_writes_with_the_model():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    game.client = _Fake(ESSAY)
    assert server.xingshi_once(game)
    w = game.world.get_season()
    assert w.xingshi[0].essay == ESSAY.strip() and not w.xingshi[0].by_rule
    messages, kwargs = game.client.calls[0]
    assert kwargs.get("required_fields") == ["essay"] and kwargs.get("require_in_schema") is True
    text = "\n".join(m["content"] for m in messages)
    assert w.xingshi[0].line in text  # 「是日：…」與事實都在提示裡
    assert not server.xingshi_once(game)  # 沒有單子了


@pytest.mark.slow
def test_server_falls_back_when_the_model_fails():
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    game.client = _Fake(fail=True)
    assert server.xingshi_once(game)
    assert game.world.get_season().xingshi[0].by_rule


@pytest.mark.slow
def test_no_thread_without_tale_threads(monkeypatch):
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    game.client = _Fake(ESSAY)
    monkeypatch.setattr(server, "TALE_THREADS", False)
    assert not server._xingshi_waiting(game)  # 測試與腳本：不開背景執行緒
    monkeypatch.setattr(server, "TALE_THREADS", True)
    assert server._xingshi_waiting(game)
    game.client = None  # 假人程式的 Game：不叫模型
    assert not server._xingshi_waiting(game)


class _FullQueue:
    """假的模型佇列：前 full 次假人的名額被佔（照 llm_queue 的規矩回 fallback、不跑），之後照跑。"""

    def __init__(self, full: int):
        self.full, self.calls = full, 0

    def run(self, owner, job, *, fallback, bot=False, wait=30.0):
        self.calls += 1
        if self.full > 0:
            self.full -= 1
            return fallback
        return job()


@pytest.mark.slow
def test_bot_slot_taken_retries_within_grace(monkeypatch):
    """PM（第三批 A 回報之後）：被假人的名額擋住時不要馬上照固定段，寬限之內下一輪再試；名額被佔一次、下一輪空了，寫得出模型那一篇。"""
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    game.client = _Fake(ESSAY)
    queue = _FullQueue(1)
    monkeypatch.setattr(server, "QUEUE", queue)
    monkeypatch.setattr(server, "TALE_THREADS", True)
    assert not server.xingshi_once(game)  # 名額被佔：這一次不收（修前照固定段收了）
    w = game.world.get_season()
    assert w.xingshi == [] and w.xingshi_ticket is not None and not w.xingshi_ticket.taken  # 單子放回去
    assert not server._xingshi_waiting(game)  # 隔一下（retry_seconds）才再試，不每一次輪詢都撞一次
    game.now = SETTLE + game.content.config.xingshi.retry_seconds + 1
    assert server._xingshi_waiting(game)
    assert server.xingshi_once(game)  # 下一輪空了
    essay = game.world.get_season().xingshi[0]
    assert not essay.by_rule and essay.essay == ESSAY.strip() and queue.calls == 2


@pytest.mark.slow
def test_bot_slot_never_frees_falls_back_after_grace(monkeypatch):
    """名額一直被佔：寬限（grace_seconds）到了照固定段收，一天一篇照樣有。"""
    game = _game(DAY0)
    _tick(game, DAY0)
    _tick(game, SETTLE)
    game.client = _Fake(ESSAY)
    monkeypatch.setattr(server, "QUEUE", _FullQueue(99))
    assert not server.xingshi_once(game)
    w = _tick(game, SETTLE + 901)
    assert w.xingshi_ticket is None and len(w.xingshi) == 1 and w.xingshi[0].by_rule


def test_server_serves_the_page():
    assert any(getattr(r, "path", "") == "/api/xingshi" for r in server.app.routes)
    assert "xingshi_now" in server.ADMIN_ACTIONS


def test_lines_file_has_every_key(tmp_path):
    from conftest import real_content

    lines = xingshi.lines(real_content("season21"))
    for key in xingshi.FACT_KEYS:
        assert lines["fact"][key]
    for key in xingshi.SUMMARY_KEYS:
        assert lines["summary"][key]
    assert lines["open"] and lines["close"]
