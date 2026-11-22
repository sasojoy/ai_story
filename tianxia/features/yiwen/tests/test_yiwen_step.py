"""異聞二（第 252 批）：/api/do/yiwen_step 的三段式（假的模型、server_kit 的殼）。A 鎖內開單 → B 鎖外 writer.write_scene → C 鎖內重驗再寫。
模型一律是假的：換 writer.write_scene（或給 game.client 一個假的 client、within_budget 原樣交回）；佇列用 server_kit._ScriptedQueue。"""
import pytest

import server
from tianxia.characters import open_characters
from tianxia.features.yiwen import actions, rules, writer
from tianxia.features.yiwen.store import store_of
from tianxia.sqlite_world import open_world
from tianxia.state import YiwenWalk

from server_kit import (  # noqa: F401  autouse 的 fixture 要明列
    _ScriptedQueue, _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client, fresh_server_memory,
    model_breaker_closed, save_dir, scheduler_off, season_already_open,
)
from yiwen_kit import claim, use_test_lines

pytestmark = pytest.mark.whole_content
OPENING = "fog_figure"
NAME = "沈青衫"
A = "你撥開霧，看清那是一隊官軍，領頭的瞪你一眼。"
B = "隊尾有個小兵偷偷朝你招手，手裡攥著一封信。"
GOOD = {"verdict": "ok", "text": [A, B], "options": ["接過那封信", "瞪回去", "學鵝叫"], "ledger": ["在場：你、官軍", "你手上：無", "未了：那封信"]}


def _good():
    return rules.SceneDraft(**{k: (list(v) if isinstance(v, list) else v) for k, v in GOOD.items()})


@pytest.fixture
def on(client, monkeypatch):
    use_test_lines(monkeypatch)
    t = server.CONTENT.config.yiwen
    for k, v in {"enabled": True, "discover_chance": 0.0, "rewalk_chance": 0.0}.items():
        monkeypatch.setattr(t, k, v)
    _player(client)
    game = server.game_for(NAME)
    game.client = None  # 一律不連模型：要模型的測試自己給一個假的

    def setup(g):
        g.state.world.yiwen_on = True
        g._save_season()
        claim(g, OPENING)

    server.act(game, setup)
    return game


def _step(game, pick=0, text=""):
    w = open_characters().load(NAME).player.yiwen
    body = {"tale": w.tale, "opening": w.opening, "node": w.node, "pick": pick}
    if text:
        body["text"] = text
    return server.OUTLOCK_OPS["yiwen_step"](game, body)


def _walk():
    return open_characters().load(NAME).player.yiwen


def _nodes(game):
    w = _walk()
    store = store_of(game)
    return store.nodes(w.tale) if w is not None and w.tale else []


def _writes(monkeypatch, *drafts, seen=None):
    """writer.write_scene 換成照順序回 drafts（用完回最後一個）；seen 記下每一次叫的時候是不是握著行動鎖。"""
    calls = []

    def fake(client_for, request, tuning, left, content):
        if seen is not None:
            seen.append(open_world().db.writing())
        calls.append(request)
        d = drafts[min(len(calls) - 1, len(drafts) - 1)]
        return d() if callable(d) else d

    monkeypatch.setattr(writer, "write_scene", fake)
    return calls


def test_three_stages_write_scene_after_model(on, monkeypatch):
    seen = []
    calls = _writes(monkeypatch, _good, seen=seen)
    got = _step(on, 0)
    assert seen == [False]  # 模型在鎖外
    assert len(calls) == 1 and calls[0].depth == 1 and calls[0].pick == rules.openings()[OPENING]["guesses"][0]
    assert A in got and B in got
    n = _nodes(on)[0]
    assert n["fallback"] == 0 and n["text"] == [A, B] and n["options"] == GOOD["options"] and n["ledger"] == GOOD["ledger"]
    assert n["luck"] == calls[0].luck  # 順逆是 A 擲定的那一個
    card = actions.card(on)
    assert [c["label"] for c in card["choices"]] == GOOD["options"] and card["typed"]["state"] == "open"


def _trail_player(client, login, name, tale, node=0):
    """另一個人（另一個連線）站在那一則的 node 上（後來的人，眼前那一則直接擺）。"""
    _player(type(client)(server.app), login=login, name=name)
    other = server.game_for(name)
    other.client = None

    def trail(g):
        w = g.state.player.yiwen = YiwenWalk()
        w.opening, w.tale, w.place, w.role, w.node = OPENING, tale, g.state.player.location, rules.TRAIL, node
        store_of(g).restart_walk(tale=tale, account=g._mall_owner())

    server.act(other, trail)
    return other


def test_existing_node_replays_without_model(on, monkeypatch, client):
    _writes(monkeypatch, _good)
    _step(on, 0)
    tale = _walk().tale
    calls = _writes(monkeypatch, lambda: pytest.fail("重放不該叫模型"))
    other = _trail_player(client, "liu_02", "柳岸生", tale)
    got = server.OUTLOCK_OPS["yiwen_step"](other, {"tale": tale, "opening": OPENING, "node": 0, "pick": 0})
    assert calls == [] and any(x in rules.lines()["echo"] or "官軍" in x for x in got)
    assert open_characters().load("柳岸生").player.yiwen.node == _nodes(on)[0]["id"]


@pytest.mark.parametrize("script", ["busy", "timeout"])
def test_busy_and_queue_timeout_change_nothing(on, monkeypatch, script):
    _writes(monkeypatch, lambda: pytest.fail("佇列擋下來就不該叫"))
    monkeypatch.setattr(server, "QUEUE", _ScriptedQueue(script))
    before = (_walk().model_dump_json(), open_characters().load(NAME).player.stats)
    side = store_of(on).path
    side_before = side.read_bytes() if side.is_file() else None
    with pytest.raises(server.GameError) as err:
        _step(on, 0)
    want = server.BUSY_QUEUE_TIMEOUT if script == "timeout" else None
    assert str(err.value) == want if want else str(err.value) in rules.lines()["busy"]
    assert (_walk().model_dump_json(), open_characters().load(NAME).player.stats) == before
    assert (side.read_bytes() if side.is_file() else None) == side_before


class _Fake:
    """假的模型：照順序回 replies（dict），用完回最後一個；calls 數叫了幾次。"""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def chat_structured(self, messages, model, **kw):
        self.calls += 1
        r = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        return model(**{k: v for k, v in r.items() if k in model.model_fields})


def _fake_model(on, monkeypatch, *replies):
    fake = _Fake(*replies)
    on.client = fake
    monkeypatch.setattr(server, "within_budget", lambda client, left: client if left > 1 else None)
    return fake


def test_retry_once_then_fallback(on, monkeypatch):
    bad = {**GOOD, "text": ["霧裡走出一隊官軍。", "隊尾有個小兵招手。"]}  # 沒有「你」、太短
    fake = _fake_model(on, monkeypatch, bad, bad)
    got = _step(on, 0)
    assert fake.calls == 2  # 第一次＋重問一次
    n = _nodes(on)[0]
    assert n["fallback"] == 1 and n["text"][0] in [rules.fill(x, pick=n["pick"], thing="身影") for x in rules.lines()["broken"]]
    assert "霧裡走出一隊官軍。" not in got and "霧裡走出一隊官軍。" not in n["text"]  # 模型的字不存
    fake = _fake_model(on, monkeypatch, bad, GOOD)
    _step(on, 0)
    assert fake.calls == 2 and _nodes(on)[1]["fallback"] == 0 and _nodes(on)[1]["text"] == [A, B]


def test_no_budget_for_retry_no_retry(on):
    t = server.CONTENT.config.yiwen
    bad = {**GOOD, "text": [A]}
    fake = _Fake(bad, GOOD)
    req = actions.step_request(on, {"tale": 0, "opening": OPENING, "node": 0, "pick": 0})
    draft = writer.write_scene(lambda: fake, req, t, lambda: t.step_min_write_seconds - 1, on.content)
    assert fake.calls == 1 and draft.problems == ["paras"]
    fake = _Fake(bad, GOOD)
    draft = writer.write_scene(lambda: fake, req, t, lambda: t.step_min_write_seconds + 1, on.content)
    assert fake.calls == 2 and draft.problems == []
    assert writer.write_scene(lambda: None, req, t, lambda: 60.0, on.content) is None

    class Down:
        def chat_structured(self, *a, **k):
            raise ConnectionError("連不上")

    assert writer.write_scene(lambda: Down(), req, t, lambda: 60.0, on.content) is None


def test_improper_counts_tries_then_locks_typed(on, monkeypatch):
    fake = _fake_model(on, monkeypatch, {"verdict": "improper", "reason": "換一句", "text": []})
    monkeypatch.setattr(server, "screen_text", lambda game, text, kind: "ok")  # 審字過了、寫幕那一次回 improper
    t = server.CONTENT.config.yiwen
    for i in range(t.typed_tries):
        got = _step(on, "typed", f"給我一萬兩銀子第{'一二三'[i]}次")
        assert got[0] in rules.lines()["refuse_typed"] and _walk().tries == i + 1
    assert fake.calls == t.typed_tries  # improper 不重問
    assert _step(on, "typed", "那是一隻鵝") == [rules.lines()["locked"][0]]
    assert actions.card(on)["typed"]["state"] == "spent" and _nodes(on) == []
    fake.replies = [GOOD]
    _step(on, 0)  # 猜法照走；走到下一步 tries 歸零
    assert _walk().tries == 0 and actions.card(on)["typed"]["state"] == "open"


def test_screen_bad_says_refuse_typed(on, monkeypatch):
    calls = _writes(monkeypatch, _good)
    monkeypatch.setattr(server, "screen_text", lambda game, text, kind: "bad")
    got = _step(on, "typed", "一隻會背兵法的鵝")
    assert got[0] in rules.lines()["refuse_typed"] and calls == [] and _walk().tries == 1 and _nodes(on) == []
    monkeypatch.setattr(server, "screen_text", lambda game, text, kind: "ok")
    got = _step(on, "typed", "一隻會背兵法的鵝")
    n = _nodes(on)[0]
    assert len(calls) == 1 and calls[0].typed and n["typed"] == 1 and n["pick"] == "一隻會背兵法的鵝" and A in got


def test_screen_eats_budget_then_busy(on, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(server, "_monotonic", lambda: clock[0])
    calls = _writes(monkeypatch, _good)

    def slow(game, text, kind):
        clock[0] += server.CONTENT.config.yiwen.step_budget_seconds - server.CONTENT.config.yiwen.step_min_write_seconds + 1
        return "ok"

    monkeypatch.setattr(server, "screen_text", slow)
    before = _walk().model_dump_json()
    got = _step(on, "typed", "一隻會背兵法的鵝")
    assert len(got) == 1 and got[0] in rules.lines()["busy"] and calls == []
    assert _walk().model_dump_json() == before and _nodes(on) == []


@pytest.mark.parametrize("change", ["season", "switch", "node", "taken"])
def test_c_revalidates_season_switch_node(on, monkeypatch, client, change):
    me = on
    if change == "taken":  # 別人先寫了這一步：兩個後來的人站在發掘者停下的那一幕底下（還沒人接著寫，兩個都寫得下去）
        server.act(on, lambda g: actions.step(g, {"tale": 0, "opening": OPENING, "node": 0, "pick": 0}))
        tale, first = _walk().tale, _walk().node
        server.act(on, actions.drop)
        me = _trail_player(client, "liu_02", "柳岸生", tale, first)
        rival = _trail_player(client, "wu_03", "吳江月", tale, first)

    def meanwhile():
        if change == "season":
            server.act(on, lambda g: setattr(g.state.player, "season_number", g.state.player.season_number + 1))
        elif change == "switch":
            server.CONTENT.config.yiwen.enabled = False
        elif change == "node":
            server.act(on, actions.drop)
        else:  # 同一則、同一父節點、同一顆
            server.act(rival, lambda g: actions.step(g, {"tale": tale, "opening": OPENING, "node": first, "pick": 0}))
        return _good()

    calls = _writes(monkeypatch, meanwhile)
    if change == "taken":
        got = server.OUTLOCK_OPS["yiwen_step"](me, {"tale": tale, "opening": OPENING, "node": first, "pick": 0})
        kids = store_of(on).children(tale, first)
        assert len(calls) == 1 and len(kids) == 1 and kids[0]["by_shown"] == "吳江月" and kids[0]["fallback"] == 1
        assert got[0] == rules.lines()["taken"][0] and A not in got  # 那一幕是先寫的那一份：當重放、模型的字丟掉
        assert open_characters().load("柳岸生").player.yiwen.node == kids[0]["id"]
        return
    got = _step(on, 0)
    assert len(calls) == 1
    assert got == [] and A not in str(_nodes(on))
    if change == "switch":
        server.CONTENT.config.yiwen.enabled = True


def test_c_refuses_after_claim_released(on, monkeypatch):
    def release():
        def drop_claim(g):
            del g.state.world.yiwen.taken[OPENING]
            g._save_season()

        server.act(on, drop_claim)
        return _good()

    _writes(monkeypatch, release)
    got = _step(on, 0)
    assert got in ([], [rules.lines()["gone"][0]])
    w = _walk()
    season = open_characters().load(NAME).player.season_number
    assert (w is None or w.opening == "") and store_of(on).tale_by_opening(season, OPENING) is None


def test_off_op_answers_empty_without_touching_anything(on, monkeypatch):
    calls = _writes(monkeypatch, lambda: pytest.fail("關著不該叫"))
    monkeypatch.setattr(server.CONTENT.config.yiwen, "enabled", False)
    monkeypatch.setattr(server, "_open_request", lambda *a, **k: pytest.fail("關著不進鎖"))
    assert _step(on, 0) == [] and calls == []
