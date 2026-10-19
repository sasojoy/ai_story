"""論武（玩家互動第二層，企劃者 2026-10-08）：同一地點的兩個人各出一樣（武學或意境）合成一樣新的，兩人都拿到；
第一次合出來的首創算兩人共有，價錢各付一半；血統、持有上限、「已經有了」照舊擋。答應的那一方開爐（首創取名在鎖外）。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去（同 test_spar）。"""
from __future__ import annotations

import random

import pytest

from conftest import FixedRandom, install_season_one
from tianxia import bot_policy, engine, fusion, invites, library, naming, social
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.martial_arts import Insight

NOW = 1000.0
NAME = ("烈焰拳", "拳勢裹著火氣。")


def _make(content, world, name, wugong="basic_fist", insights=("feng",)):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.member.wugong_id = wugong
    p.insights = list(insights)
    p.stats["xinde"] = 100
    p.stamina = 100.0
    game.sync(NOW)
    CharacterStore(world.db).save(game.state)
    return game


@pytest.fixture
def pair(content, world):
    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", wugong="fist", insights=("huo",))
    return content, world


def _do(content, world, name, act):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _load(world, name):
    return CharacterStore(world.db).load(name)


def _owned(world, name):
    s = _load(world, name)
    return set(library.owned_arts(s)) | set(s.player.insights)


def _invite(content, world, item="art:basic_fist"):
    return _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", {"arg": f"invite:{item}"}))[0]


def _accept(content, world, item, proposed=NAME):
    return _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": f"yes:{item}", "proposed": proposed}))[0]


def test_both_get_the_new_art_and_share_the_first_creation(pair):
    content, world = pair
    assert "等他回覆" in _invite(content, world)[-1]
    msgs = _accept(content, world, "insight:huo")
    assert "烈焰拳" in msgs[0]
    art = world.lookup_recipe(fusion.fuse_key("basic_fist", "huo", "剛"))
    assert (art.name, art.creator, art.co_creator, art.creator_shown) == ("烈焰拳", "乙", "甲", "乙、甲")
    for name in ("甲", "乙"):
        p = _load(world, name).player
        assert "烈焰拳" in library.owned_arts(_load(world, name))
        assert p.stats["xinde"] == 100 - 3 and p.stamina == pytest.approx(100 - 3, abs=0.5)  # 一爐 5 的一半，進位
        assert any(e.title.startswith("論武") for e in _load(world, name).journal)
    assert "huo" not in _load(world, "甲").player.insights  # 借來的意境不會留在你身上
    assert world.get_season().invites == []


def test_two_insights_merge_into_one_both_hold(pair):
    content, world = pair
    _invite(content, world, "insight:feng")
    _accept(content, world, "insight:huo", ("風火境", "風助火勢。"))
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    assert made.name == "風火境" and made.creator_shown == "乙、甲"
    assert made.id in _load(world, "甲").player.insights and made.id in _load(world, "乙").player.insights


def test_two_arts_blend(pair):
    content, world = pair
    _invite(content, world, "art:basic_fist")
    _accept(content, world, "art:fist", ("兩儀拳", "剛實並濟。"))
    made = world.lookup_recipe(fusion.blend_key("basic_fist", "fist"))
    assert made is not None and made.co_creator == "甲"
    assert made.id in _owned(world, "甲") and made.id in _owned(world, "乙")


def test_one_side_already_has_it_so_nothing_happens(pair):
    """一邊已經有了：整爐不開、誰都不收錢（說是哪一邊合不成）。"""
    content, world = pair
    _invite(content, world)
    _accept(content, world, "insight:huo")
    for name in ("甲", "乙"):  # 再論一次同一組
        state = _load(world, name)
        state.player.stamina = 100.0
        CharacterStore(world.db).save(state)
    _invite(content, world)
    msgs = _accept(content, world, "insight:huo")
    assert "已經有了" in msgs[0]
    assert _load(world, "甲").player.stats["xinde"] == 97 and _load(world, "乙").player.stats["xinde"] == 97


def test_lineage_still_blocks(pair):
    """血統裡融過的意境照樣擋：乙出火、甲出一門融過火的武學。"""
    content, world = pair
    _invite(content, world)
    _accept(content, world, "insight:huo")  # 兩人都有了 烈焰拳（粗淺拳腳＋火）
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.stamina = 100.0
        CharacterStore(world.db).save(state)
    _invite(content, world, "art:烈焰拳")
    msgs = _accept(content, world, "insight:huo")
    assert "早已融過" in msgs[0]


def test_private_insights_cannot_be_put_in(pair):
    content, world = pair
    state = _load(world, "甲")
    state.player.own_insights["悟:1"] = Insight(id="悟:1", name="一筆", attribute="快")
    state.player.insights.append("悟:1")
    CharacterStore(world.db).save(state)
    items = dict(_do(content, world, "甲", lambda g: g.discuss_items())[0])
    assert "insight:悟:1" not in items and "insight:feng" in items
    msgs = _invite(content, world, "insight:悟:1")
    assert msgs == ["你身上沒有這一樣。"] and world.get_season().invites == []


def test_the_card_buttons(pair):
    content, world = pair

    def buttons(name, other):
        card = _do(content, world, name, lambda g: g.peer_card(other))[0]
        return [(b["label"], b["arg"]) for b in card["actions"] if b["action"] == "discuss"]

    assert buttons("甲", "乙") == [("論武・以【粗淺拳腳】", "invite:art:basic_fist"), ("論武・以「風」", "invite:insight:feng")]
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    picks = [(b["group"], b["pick"]) for b in card["actions"] if b["action"] == "discuss"]
    assert picks == [("論武", "【粗淺拳腳】"), ("論武", "「風」")]  # 網頁照 group 收成一個下拉清單
    _invite(content, world)
    assert buttons("甲", "乙") == [("收回論武邀請", "cancel")]
    assert buttons("乙", "甲") == [("以【長拳】應之", "yes:art:fist"), ("以「火」應之", "yes:insight:huo"), ("婉拒論武", "no")]
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "no"}))
    assert world.get_season().invites == [] and any("婉拒" in e.title for e in _load(world, "甲").journal)


def test_the_menu_only_lets_you_decline(pair):
    content, world = pair
    _invite(content, world)
    iid = world.get_season().invites[0].id
    options = {o.id: o for o in _do(content, world, "乙", lambda g: g.options(odds=False))[0]}
    assert not options[f"invite:yes:{iid}"].enabled and options[f"invite:no:{iid}"].enabled


def test_the_first_creation_echo_pays_both(pair):
    """別人照著論武合出來的那一門合：兩個首創者各自同步時都拿名望。"""
    content, world = pair
    _invite(content, world)
    _accept(content, world, "insight:huo")
    third = _make(content, world, "丙", insights=("huo",))
    third.forge("basic_fist", ["huo"], proposed=(None, ""))
    third._save_season()
    CharacterStore(world.db).save(third.state)
    for name in ("甲", "乙"):
        fame = _load(world, name).player.stats.get("fame", 0)
        _, game = _do(content, world, name, lambda g: None)
        assert game.state.player.stats.get("fame", 0) == fame + content.config.first_echo.fame_per


def test_a_bot_asks_the_model_for_the_first_name(pair):
    """假人答論武：要首創取名就開單（DiscussJob），bot_runner 在鎖外取名、C 段交回 peer_act。"""
    content, world = pair
    _invite(content, world)
    slot = bot_policy.NamingSlot(open=True)
    _, bot = _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.0), slot))
    assert isinstance(slot.job, bot_policy.DiscussJob) and not slot.job.request.choices
    assert slot.job.item == "art:fist"  # 身上的先出（長拳＋粗淺拳腳）
    _do(content, world, "乙", lambda g: bot_policy.apply_job(g, slot.job, ("剛實拳", "兩拳合一。")))
    made = world.lookup_recipe(fusion.blend_key("basic_fist", "fist"))
    assert made.name == "剛實拳" and made.id in _owned(world, "甲")


def test_a_bot_without_a_name_does_not_take_the_first_creation(pair):
    content, world = pair
    _invite(content, world)
    slot = bot_policy.NamingSlot(open=True)
    _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.0), slot))
    _do(content, world, "乙", lambda g: bot_policy.apply_job(g, slot.job, (None, "")))
    assert world.lookup_recipe(fusion.blend_key("basic_fist", "fist")) is None
    assert len(world.get_season().invites) == 1  # 邀請還在，之後再答


def test_a_bot_declines_sometimes(pair):
    content, world = pair
    _invite(content, world)
    _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.99), bot_policy.NamingSlot(open=True)))
    assert world.get_season().invites == []


def test_the_server_names_it_outside_the_lock(pair, monkeypatch):
    """伺服器：答應論武先在鎖外取名（prepare_peer），取好的放進 params 交給 peer_act。"""
    import server

    content, world = pair
    _invite(content, world)
    state = CharacterStore(world.db).load("乙")
    game = Game(content, state, random.Random(0), world)
    game.sync(NOW)
    monkeypatch.setattr(server, "_open_request", lambda g, open_it: (0.0, open_it()))
    monkeypatch.setattr(naming, "generate", lambda *a, **k: NAME)
    params = {"arg": "yes:insight:huo"}
    assert server.prepare_peer(game, "甲", "discuss", params) == NAME
    assert server.prepare_peer(game, "甲", "spar", {"arg": "invite"}) is None  # 切磋不用模型
    assert server.prepare_peer(game, "甲", "discuss", {"arg": "no"}) == server.NO_NAME


# ── FB-245：答應論武時這一張邀請已經成不了，不開取名單子、不叫模型，直接回原本那一句 ──


class CountingClient:
    """假模型：每叫一次記一筆，回一個取得到的名字（真的被叫到就看得出來）。naming 用 copy.copy 複本，calls 是同一個串列。"""

    timeout = 30.0
    retry = True

    def __init__(self):
        self.calls = []

    def chat_structured(self, messages, schema, required_fields=None, **kw):
        # **kw：真的 client 收 temperature、num_predict 這些；替身把簽名寫死的話，
        # 呼叫端多給一個參數就變成 TypeError，被 except 吞掉之後看起來像「模型叫不動」
        # （2026-10-19 給每個呼叫點加 num_predict 時踩到）
        self.calls.append(messages)
        return schema(name=NAME[0], description=NAME[1])


@pytest.fixture
def no_ollama(monkeypatch):
    """不准碰模型的 port：Game 建 client 一律是 None（各測試自己給假 client）。"""
    from tianxia.ollama_client import OllamaClient

    monkeypatch.setattr(OllamaClient, "from_config", classmethod(lambda cls, cfg: None))


def _answer_like_the_server(content, world, monkeypatch, item="insight:huo"):
    """照伺服器答應論武的三段走一次：A、B 是 server.prepare_peer（A 段鎖內開單、B 段鎖外取名），C 是 peer_act。
    模型換成數次數的假 client。回傳（回話, 模型被叫了幾次）。"""
    import server

    monkeypatch.setattr(server, "_open_request", lambda g, open_it: (server._monotonic(), open_it()))
    fake = CountingClient()

    def answer(game):
        game.client = fake
        params = {"arg": f"yes:{item}"}
        proposed = server.prepare_peer(game, "甲", "discuss", params)
        return game.peer_act("甲", "discuss", {**params, "proposed": proposed})

    return _do(content, world, "乙", answer)[0], len(fake.calls)


def _change(world, name, edit):
    state = _load(world, name)
    edit(state.player)
    CharacterStore(world.db).save(state)


def test_fb245_a_discussion_that_can_go_ahead_still_asks_the_model_once(pair, no_ollama, monkeypatch):
    content, world = pair
    _invite(content, world)  # 甲出【粗淺拳腳】，乙出「火」：新配方，要取名
    request = _do(content, world, "乙", lambda g: g.peer_request("甲", "discuss", {"arg": "yes:insight:huo"}))[0]
    assert isinstance(request, naming.NamingRequest)
    msgs, calls = _answer_like_the_server(content, world, monkeypatch)
    assert calls == 1 and "烈焰拳" in msgs[0] and world.get_season().invites == []


@pytest.mark.parametrize("why", ["busy", "tired", "full", "item_gone"])
def test_fb245_a_lapsed_invitation_is_refused_without_the_model(pair, no_ollama, monkeypatch, why):
    """邀請本身成不了（他正忙、體力不夠、這一對今天論滿了、他要出的那一樣沒了）：A 段不開單（回 None），模型一次都不叫；
    回給你的那一句、邀請作廢、他江湖紀錄裡那一句都跟以前一樣（C 段照舊擋）。"""
    content, world = pair
    _invite(content, world)
    cost = _do(content, world, "甲", lambda g: g._discuss_cost())[0][1]
    if why == "busy":
        _change(world, "甲", lambda p: setattr(p, "busy_until", 1e9))  # 閉關中，同「進了鐵匠鋪」：選單上沒有探索
        mine, theirs = "甲此刻正忙，騰不出手來論武。", "你此刻正忙，騰不出手來論武。"
    elif why == "tired":
        _change(world, "甲", lambda p: setattr(p, "stamina", 0.0))
        mine, theirs = f"甲體力不夠（論武要 {cost} 點）。", f"你體力不夠（論武要 {cost} 點）。"
    elif why == "full":
        cap = content.config.discuss_per_pair_day
        _do(content, world, "乙", lambda g: [g._pair_tick(g.state.world.discuss_tally, "甲") for _ in range(cap)])
        mine = theirs = _do(content, world, "乙", lambda g: social.pair_full(g, "discuss"))[0]
    else:
        _change(world, "甲", lambda p: setattr(p, "member", p.member.model_copy(update={"wugong_id": None})))
        mine, theirs = "甲身上已經沒有他要出的那一樣了。", "你身上已經沒有要出的那一樣了。"
    assert _do(content, world, "乙", lambda g: g.peer_request("甲", "discuss", {"arg": "yes:insight:huo"}))[0] is None
    msgs, calls = _answer_like_the_server(content, world, monkeypatch)
    assert calls == 0 and msgs == [mine]
    assert world.get_season().invites == []
    head = _load(world, "甲").journal[0]
    assert (head.title, head.lines) == ("論武不成・乙", [engine.INVITE_LAPSED.format(who="乙", what="論武"), theirs])
    assert world.lookup_recipe(fusion.fuse_key("basic_fist", "huo", "剛")) is None


@pytest.mark.parametrize("why", ["same", "same_insight", "their_side"])
def test_fb245_a_pick_that_cannot_fit_is_refused_without_the_model(content, world, no_ollama, monkeypatch, why):
    """你挑的那一樣合不成（跟他出的是同一樣、他那邊合不成）：一樣不開單、不叫模型，回原本那一句，邀請留著換一樣再答。
    同一個意境兩邊各出一個：一個人合併同一個意境是可以的（fusion.merge_problem 不擋），以前會先開單取名才回「同一樣」。"""
    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", insights=("huo", "feng"))  # 兩個人都有【粗淺拳腳】、「風」
    _invite(content, world, "insight:feng" if why == "same_insight" else "art:basic_fist")
    if why == "same":
        item, line = "art:basic_fist", engine.DISCUSS_SAME
    elif why == "same_insight":
        item, line = "insight:feng", engine.DISCUSS_SAME
    else:
        _change(world, "甲", lambda p: p.stats.__setitem__("xinde", 0))
        item, line = "insight:huo", "甲那邊合不成：他的心得不夠。"
    assert _do(content, world, "乙", lambda g: g.peer_request("甲", "discuss", {"arg": f"yes:{item}"}))[0] is None
    msgs, calls = _answer_like_the_server(content, world, monkeypatch, item)
    assert calls == 0 and msgs == [line]
    assert len(world.get_season().invites) == 1  # 換一樣再答
    assert not any(e.title.startswith("論武不成") for e in _load(world, "甲").journal)


def test_nothing_while_the_switch_is_off(content, world):
    content.config.auto_open_first_season = True
    _make(content, world, "甲")
    _make(content, world, "乙")
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    assert not any(b["action"] == "discuss" for b in card["actions"])
    assert invites.KINDS["discuss"] == "論武" and social.ACTIONS["discuss"].order == 55
