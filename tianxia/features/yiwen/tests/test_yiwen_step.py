"""異聞二（第 252 批）：/api/do/yiwen_step 的三段式（假的模型、server_kit 的殼）。A 鎖內開單 → B 鎖外 writer.write_scene → C 鎖內重驗再寫。
模型一律是假的：換 writer.write_scene（或給 game.client 一個假的 client、within_budget 原樣交回）；佇列用 server_kit._ScriptedQueue。"""
import dataclasses

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


def test_no_model_screens_through_and_writes_the_stand_in(on):
    """先對程式確認的第 2、4 條：沒有 client 時 screen_text 回空字串（照送）、佇列關著 model_call 直接叫 job；
    write_scene 拿不到 client 回 None，C 存替身（自己說的那一句照樣記成 typed 的節點）。"""
    assert server.QUEUE is None and on.client is None
    got = _step(on, "typed", "一隻會背兵法的鵝")
    n = _nodes(on)[0]
    assert n["typed"] == 1 and n["fallback"] == 1 and n["pick"] == "一隻會背兵法的鵝" and n["text"][0] in got
    assert actions.card(on)["scenes"][0]["zhupi_text"] == actions.SAID.format(words="一隻會背兵法的鵝")


def test_off_op_answers_empty_without_touching_anything(on, monkeypatch):
    calls = _writes(monkeypatch, lambda: pytest.fail("關著不該叫"))
    monkeypatch.setattr(server.CONTENT.config.yiwen, "enabled", False)
    monkeypatch.setattr(server, "_open_request", lambda *a, **k: pytest.fail("關著不進鎖"))
    assert _step(on, 0) == [] and calls == []


# ── 第 253 批：C 段（apply_step）每一項重驗各一條「拿掉就紅」（AI 波審查：拿掉 node、tale、key、valid、自己說的鎖、_writable 那六項，
# 舊的測試照綠——舊案例用 drop 清掉眼前那一則，server.act 一進鎖 on_sync 就先回 gone，走不到後面的比對）。
# 能走路由就走路由：假的 write_scene 第一次被叫時先做「B 段中間插進來的事」，再回草稿。路由走不到的直接叫 apply_step，說明寫為什麼。


def _stats(name=NAME):
    st = open_characters().load(name).player.stats
    return st.get("silver", 0), st.get("xinde", 0)


def _meanwhile(monkeypatch, first_time):
    """writer.write_scene 換成：第一次叫時先跑 first_time()（B 段中間插進來的事），之後每一次都回 _good()。"""
    calls = []

    def fake(client_for, request, tuning, left, content):
        calls.append(request)
        if len(calls) == 1:
            first_time()
        return _good()

    monkeypatch.setattr(writer, "write_scene", fake)
    return calls


def _first_scene_then_trail(on, client):
    """發掘者寫成第一幕後放下（則照逾時提早公開），兩個後來的人站在那一幕底下（還沒人接著寫）。"""
    server.act(on, lambda g: actions.step(g, {"tale": 0, "opening": OPENING, "node": 0, "pick": 0}))
    tale, first = _walk().tale, _walk().node
    server.act(on, actions.drop)
    return tale, first, _trail_player(client, "liu_02", "柳岸生", tale, first), _trail_player(client, "wu_03", "吳江月", tale, first)


def test_c_same_node_sent_twice_keeps_one_scene(on, monkeypatch):
    """守 C 的 w.node != req.node：同一個人在第二步送了兩次（兩張 A 開的單）。第一張寫進去、眼前前進到下一幕之後，
    第二張進 C：不重寫、不多給獎勵，回空清單（現行行為：不是重放、也不是 taken）。
    要在第二步造：第一步兩張單時 req.tale 是 0、眼前已經開則，會被 tale 那一項先擋住，拿掉 node 那一項照樣綠。"""
    monkeypatch.setattr(server.CONTENT.config.yiwen, "luck_good", 0.0)
    _writes(monkeypatch, _good)
    _step(on, 0)
    w = _walk()
    tale, first = w.tale, w.node
    body = {"tale": tale, "opening": OPENING, "node": first, "pick": 0}
    seen = {}

    def second_ticket():
        seen["inner"] = server.OUTLOCK_OPS["yiwen_step"](on, dict(body))
        seen["node"], seen["stats"] = _walk().node, _stats()

    calls = _meanwhile(monkeypatch, second_ticket)
    got = server.OUTLOCK_OPS["yiwen_step"](on, dict(body))
    assert len(calls) == 2 and A in seen["inner"]  # 內層那一張寫成了第二幕
    assert got == []
    nodes = store_of(on).nodes(tale)
    assert len(nodes) == 2 and [n["depth"] for n in nodes] == [1, 2] and nodes[1]["parent"] == first
    w = _walk()
    assert w.tale == tale and w.node == seen["node"] == nodes[1]["id"] and tale not in w.done
    assert _stats() == seen["stats"]  # 外層那一張一兩銀子都沒多給


def test_c_reattached_to_other_tale_writes_nothing(on, monkeypatch):
    """守 C 的 w.tale != req.tale：發掘者第一步送了「按第二顆」（A 看到旁檔沒有則→單上 tale 是 0）。B 中間同一個人又送了「按第一顆」
    寫成第一幕（開則 T），接著主交易撤回、玩家那一格回到 B 之前（tale 0）、世界那一格與旁檔留著。C 段接回 T（該變的），
    跟單上的 0 不一樣：不在 T 的第一層多寫一幕。「放下再撞見另一則」同一句開場時單上也是 0、對不出不同的則，可造的只有撤回後接回。"""
    monkeypatch.setattr(server.CONTENT.config.yiwen, "luck_good", 0.0)
    seen = {}

    def write_then_roll_back():
        before = _walk().model_copy(deep=True)
        server.OUTLOCK_OPS["yiwen_step"](on, {"tale": 0, "opening": OPENING, "node": 0, "pick": 0})
        seen["tale"] = _walk().tale
        server.act(on, lambda g: setattr(g.state.player, "yiwen", before))
        seen["stats"] = _stats()

    calls = _meanwhile(monkeypatch, write_then_roll_back)
    got = _step(on, 1)
    assert len(calls) == 2 and got == []
    tale = seen["tale"]
    nodes = store_of(on).nodes(tale)
    assert tale > 0 and len(nodes) == 1 and nodes[0]["pick"] == rules.openings()[OPENING]["guesses"][0]
    w = _walk()
    assert w.tale == tale and w.node == 0
    assert _stats() == seen["stats"]


@pytest.mark.parametrize("at", ["first", "second"])
def test_c_ticket_of_another_key_writes_nothing(on, monkeypatch, at):
    """守 C 的 key != req.key：單上的鍵跟進 C 的人不一樣（別人的單）。直接叫 apply_step：鍵是名號的 casefold（_mall_owner），
    路由的 A、C 用同一個 game；唯一換得了鍵的是易名帖，那走帳號交易、殼照名號重讀，這一批不造。
    兩格：第一步（拿掉會開則）、第二步（拿掉會在既有的則上寫幕）。"""
    monkeypatch.setattr(server.CONTENT.config.yiwen, "luck_good", 0.0)
    if at == "second":
        _writes(monkeypatch, _good)
        _step(on, 0)
    w = _walk()
    body = {"tale": w.tale, "opening": OPENING, "node": w.node, "pick": 0}
    req = server.act(on, lambda g: actions.step_request(g, body))
    assert isinstance(req, rules.YiwenRequest)
    before, stats = _walk().model_dump(), _stats()
    other = dataclasses.replace(req, key="別人的鍵")
    got = server.act(on, lambda g: actions.apply_step(g, other, _good(), ""))
    assert got == []
    season = open_characters().load(NAME).player.season_number
    row = store_of(on).tale_by_opening(season, OPENING)
    if at == "first":
        assert row is None
    else:
        assert len(store_of(on).nodes(row["id"])) == 1
    assert _walk().model_dump() == before and _stats() == stats


@pytest.mark.parametrize("how", ["claim_released", "claim_other", "removed", "opening_gone"])
def test_c_invalid_tale_inside_lock(on, monkeypatch, client, how):
    """守 C 的 not valid(ctx) 那一支。直接叫 apply_step，在同一個 server.act 裡先把則弄無效、再叫：路由的 C 一進鎖 game.sync 就跑 on_sync，
    眼前那一則無效就清掉、回 gone，走不到 C 的那一行。照 valid 的實際條件造：名額被放回、名額變成別人的（發掘者還沒寫第一幕）、
    則被拿掉（後來的人）、開場不在內容檔（發掘者第二步）。「逾時公開」只把狀態從 walking 改成 open，valid 照樣為真，不列。"""
    monkeypatch.setattr(server.CONTENT.config.yiwen, "luck_good", 0.0)
    me, name = on, NAME
    if how == "removed":
        tale, first, me, _ = _first_scene_then_trail(on, client)
        name = "柳岸生"
    elif how == "opening_gone":
        _writes(monkeypatch, _good)
        _step(on, 0)
    w = open_characters().load(name).player.yiwen
    tale = w.tale
    count = len(store_of(on).nodes(tale)) if tale else 0
    body = {"tale": tale, "opening": OPENING, "node": w.node, "pick": 0}
    req = server.act(me, lambda g: actions.step_request(g, body))
    assert isinstance(req, rules.YiwenRequest)
    stats = _stats(name)
    real = rules.openings

    def spoil_then_apply(g):
        if how == "claim_released":
            del g.state.world.yiwen.taken[OPENING]
        elif how == "claim_other":
            g.state.world.yiwen.taken[OPENING].by = "別人的鍵"
        elif how == "removed":
            store_of(g).set_status(tale, rules.REMOVED)
        else:
            monkeypatch.setattr(rules, "openings", lambda: {k: v for k, v in real().items() if k != OPENING})
        g._save_season()
        return actions.apply_step(g, req, _good(), "")

    got = server.act(me, spoil_then_apply)
    monkeypatch.setattr(rules, "openings", real)
    season = open_characters().load(name).player.season_number
    if how in ("claim_released", "claim_other"):  # 發掘者一幕都還沒寫：清眼前、回 gone、不開則
        assert len(got) == 1 and got[0] in rules.lines()["gone"]
        w = open_characters().load(name).player.yiwen
        assert w.opening == "" and store_of(on).tale_by_opening(season, OPENING) is None
    else:
        assert got == []
        assert len(store_of(on).nodes(tale)) == count
    assert _stats(name) == stats


@pytest.mark.parametrize("how", ["tries", "muted"])
def test_c_typed_locked_mid_b(on, monkeypatch, how):
    """守 C 的「自己說：w.tries >= typed_tries 或被禁寫」：A 開單時還寫得下去，B 中間這個人另外連送 typed_tries 次被審字擋掉的自己說
    （次數到了上限），或被禁寫（旁檔沒有寫 mute 的方法，異聞四才寫，這裡直接 INSERT）。C 回 locked、不寫、不給。站在第一步即可：
    發掘者走自己的路，_writable 永遠為真，不會被它先擋。"""
    t = server.CONTENT.config.yiwen
    monkeypatch.setattr(t, "luck_good", 0.0)
    inner = ["一隻會唱曲的貓", "一頭會寫字的牛", "一條會算命的狗", "一匹會作揖的馬"][:t.typed_tries]
    monkeypatch.setattr(server, "screen_text", lambda game, text, kind: "bad" if text in inner else "ok")
    seen = {}

    def meanwhile():
        if how == "tries":
            for text in inner:
                server.OUTLOCK_OPS["yiwen_step"](on, {"tale": 0, "opening": OPENING, "node": 0, "pick": "typed", "text": text})
        else:
            store_of(on)._write("INSERT INTO mutes (account, until, by, at) VALUES (?, ?, ?, ?)", (on._mall_owner(), 1e15, "管理者", 0.0))
        seen["tries"], seen["stats"] = _walk().tries, _stats()

    calls = _meanwhile(monkeypatch, meanwhile)
    got = _step(on, "typed", "一隻會背兵法的鵝")
    assert len(calls) == 1  # 內層的自己說都被審字擋下、不叫模型
    assert got == [rules.lines()["locked"][0]]
    assert seen["tries"] == (t.typed_tries if how == "tries" else 0)
    w = _walk()
    assert w.tries == seen["tries"] and w.tale == 0 and w.node == 0
    season = open_characters().load(NAME).player.season_number
    assert store_of(on).tale_by_opening(season, OPENING) is None and _stats() == seen["stats"]


def test_c_other_pick_written_mid_b_locks(on, monkeypatch, client):
    """守 C 的 not _writable：兩個後來的人站在發掘者停下的那一幕底下；柳岸生按第一顆，B 中間吳江月按了**第二顆**、寫成一幕。
    別人的則、這一個節點底下已經有人走過別的做法（開岔路是異聞三）：C 回 locked、不多開一條、不給。同一顆的情形由
    test_c_revalidates_season_switch_node[taken] 守（當重放、多回 taken）。"""
    monkeypatch.setattr(server.CONTENT.config.yiwen, "luck_good", 0.0)
    tale, first, me, rival = _first_scene_then_trail(on, client)
    stats = _stats("柳岸生")
    calls = _meanwhile(monkeypatch, lambda: server.act(rival, lambda g: actions.step(g, {"tale": tale, "opening": OPENING, "node": first, "pick": 1})))
    got = server.OUTLOCK_OPS["yiwen_step"](me, {"tale": tale, "opening": OPENING, "node": first, "pick": 0})
    assert len(calls) == 1 and got == [rules.lines()["locked"][0]]
    kids = store_of(on).children(tale, first)
    assert len(kids) == 1 and kids[0]["by_shown"] == "吳江月"
    w = open_characters().load("柳岸生").player.yiwen
    assert w.node == first and w.own_from == -1 and w.tale == tale
    assert _stats("柳岸生") == stats


# ── 第 253 批：writer._check 猜法那一步回 improper（當成檢查沒過：重問一次、還是 improper 存替身，不加 tries）──


def test_improper_on_a_guess_counts_as_failed_check(on, monkeypatch):
    t = server.CONTENT.config.yiwen
    improper = {"verdict": "improper", "reason": "換一句", "text": [A, B], "options": GOOD["options"], "ledger": GOOD["ledger"]}
    req = actions.step_request(on, {"tale": 0, "opening": OPENING, "node": 0, "pick": 0})
    assert isinstance(req, rules.YiwenRequest) and not req.typed
    fake = _Fake(improper, improper)
    draft = writer.write_scene(lambda: fake, req, t, lambda: 60.0, on.content)
    assert fake.calls == 2 and draft.problems == ["improper"]
    fake = _fake_model(on, monkeypatch, improper, improper)
    got = _step(on, 0)
    assert fake.calls == 2
    n = _nodes(on)[0]
    assert n["fallback"] == 1 and A not in n["text"] and A not in got and _walk().tries == 0


# ── 第 261 批：收尾卡「名望 +5」少了差距那半句（第 256 批網頁走查拍到）。差距由共用層 renown.after_action 接，它只在 Game._log 裡被叫；
# C 段回話不經 _log 的話，這一下沒人接，之後的同步只接「最新一則的時間＝此刻」的那一則——時鐘一走就永遠接不到。
# 測試內容的 renown.titles 關著（關著差距永遠不接、修前修後都綠），這裡打開；時鐘每讀一次往後 1 秒，照真的玩家。


@pytest.fixture
def ticking(on, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config.renown, "titles", True)
    clock = [server.time.time()]

    def tick():
        clock[0] += 1.0
        return clock[0]

    monkeypatch.setattr(server.time, "time", tick)
    return clock


def _walk_to_the_end(game):
    """走到收場（替身即可：client 是 None）。回最後一步的回話。"""
    got = []
    for _ in range(10):
        w = _walk()
        if w.tale and w.tale in w.done:
            break
        got = _step(game, 0)
    w = _walk()
    assert w.tale and w.tale in w.done, "十步內沒走完"
    return got


def _finish_entry():
    entry = open_characters().load(NAME).journal[0]
    assert entry.title.startswith("異聞")
    return entry


def test_finish_fame_gets_the_gap_on_the_spot(on, ticking):
    _walk_to_the_end(on)
    assert any(c.startswith("名望 +") and "（離「" in c for c in _finish_entry().changes)


def test_finish_fame_gap_survives_a_later_sync(on, ticking):
    _walk_to_the_end(on)
    ticking[0] += 30
    server.act(on, lambda g: [])
    assert any(c.startswith("名望 +") and "（離「" in c for c in _finish_entry().changes)


def test_finish_lines_go_into_the_game_log(on, ticking):
    got = _walk_to_the_end(on)
    assert got
    log = open_characters().load(NAME).log
    assert all(line in log for line in got if line)
