"""論武（玩家互動第二層，企劃者 2026-10-08）：同一地點的兩個人各出一個意境合成一個新的，兩人都拿到；
第一次合出來的首創算兩人共有，價錢各付一半；持有上限照舊擋。答應的那一方開爐（首創取名在鎖外）。
煉製只剩意境＋意境（Joy 2026-10-21）：論武跟著只剩意境，武學不再拿出來論。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去（同 test_spar）。"""
from __future__ import annotations

import random

import pytest

from conftest import FixedRandom, install_season_one
from tianxia import bot_policy, engine, fusion, invites, library, naming, social
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.martial_arts import Insight
import json
from test_prologue_web import DRIVER as BASE_DRIVER
import server
import webharness
from tianxia import discuss, engine, social

NOW = 1000.0
NAME = ("烈焰境", "風助火勢。")


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


@pytest.fixture(autouse=True)
def _fist_is_plain(content):
    """武學重構：寫死的武學（內容寫死、不是下品）不能當合成的料；測試內容的長拳沒寫品級（預設絕學），
    這裡改成下品，讓它照舊當論武的那一門。"""
    content.skills["fist"].quality = "下品"


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


def _invite(content, world, item="insight:feng"):
    return _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", {"arg": f"invite:{item}"}))[0]


def _accept(content, world, item, proposed=NAME):
    return _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": f"yes:{item}", "proposed": proposed}))[0]


def test_both_get_the_new_insight_and_share_the_first_creation(pair):
    content, world = pair
    assert "等他回覆" in _invite(content, world)[-1]
    msgs = _accept(content, world, "insight:huo")
    assert "烈焰境" in msgs[0]
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    assert (made.name, made.creator, made.co_creator, made.creator_shown) == ("烈焰境", "乙", "甲", "乙、甲")
    cfg = content.config
    xinde, stamina = fusion.half_price(cfg.merge_xinde, cfg.merge_stamina)  # 一爐的一半，各自進位
    for name in ("甲", "乙"):
        p = _load(world, name).player
        assert made.id in p.insights
        assert p.stats["xinde"] == 100 - xinde and p.stamina == pytest.approx(100 - stamina, abs=0.5)
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


def test_arts_are_not_put_in_any_more(pair):
    """武學不再拿來合：論武的清單裡沒有武學，拿武學邀、拿武學答都不成，誰都不收錢。"""
    content, world = pair
    items = dict(_do(content, world, "甲", lambda g: g.discuss_items())[0])
    assert list(items) == ["insight:feng"]
    assert _invite(content, world, "art:basic_fist") == ["你身上沒有這一樣。"] and world.get_season().invites == []
    _invite(content, world)
    msgs = _accept(content, world, "art:fist")
    assert msgs == ["你身上沒有這一樣。"] and len(world.get_season().invites) == 1
    assert _load(world, "甲").player.stats["xinde"] == 100 and _load(world, "乙").player.stats["xinde"] == 100


def test_an_old_invitation_with_an_art_is_refused(pair):
    """這一版之前發出的邀請上寫的是武學：發邀請的那一方已經出不了它，邀請作廢，誰都不收錢。"""
    content, world = pair
    _invite(content, world)
    world.mutate_season(lambda season: season.invites[0].payload.update(item="art:basic_fist"))
    msgs = _accept(content, world, "insight:huo")
    assert msgs == ["甲身上已經沒有他要出的那一樣了。"] and world.get_season().invites == []
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None
    assert _load(world, "甲").player.stats["xinde"] == 100 and _load(world, "乙").player.stats["xinde"] == 100


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

    assert buttons("甲", "乙") == [("論武・以「風」", "invite:insight:feng")]
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    picks = [(b["group"], b["pick"]) for b in card["actions"] if b["action"] == "discuss"]
    assert picks == [("論武", "「風」")]  # 網頁照 group 收成一個下拉清單
    _invite(content, world)
    assert buttons("甲", "乙") == [("收回論武邀請", "cancel")]
    assert buttons("乙", "甲") == [("以「火」應之", "yes:insight:huo"), ("婉拒論武", "no")]
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "no"}))
    assert world.get_season().invites == [] and any("婉拒" in e.title for e in _load(world, "甲").journal)


def test_the_menu_only_lets_you_decline(pair):
    content, world = pair
    _invite(content, world)
    iid = world.get_season().invites[0].id
    options = {o.id: o for o in _do(content, world, "乙", lambda g: g.options(odds=False))[0]}
    assert not options[f"invite:yes:{iid}"].enabled and options[f"invite:no:{iid}"].enabled


def test_the_first_creation_echo_pays_both(pair):
    """別人照著論武合出來的那一個意境合：兩個首創者各自同步時都拿名望。"""
    content, world = pair
    _invite(content, world)
    _accept(content, world, "insight:huo")
    third = _make(content, world, "丙", insights=("feng", "huo"))
    third.forge(None, ["feng", "huo"], proposed=(None, ""))
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
    assert slot.job.item == "insight:huo"
    _do(content, world, "乙", lambda g: bot_policy.apply_job(g, slot.job, ("風火境", "風助火勢。")))
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    assert made.name == "風火境" and made.id in _owned(world, "甲")


def test_a_bot_without_a_name_does_not_take_the_first_creation(pair):
    content, world = pair
    _invite(content, world)
    slot = bot_policy.NamingSlot(open=True)
    _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.0), slot))
    _do(content, world, "乙", lambda g: bot_policy.apply_job(g, slot.job, (None, "")))
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None
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
    _invite(content, world)  # 甲出「風」，乙出「火」：新配方，要取名
    request = _do(content, world, "乙", lambda g: g.peer_request("甲", "discuss", {"arg": "yes:insight:huo"}))[0]
    assert isinstance(request, naming.NamingRequest)
    msgs, calls = _answer_like_the_server(content, world, monkeypatch)
    assert calls == 1 and "烈焰境" in msgs[0] and world.get_season().invites == []


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
        _change(world, "甲", lambda p: setattr(p, "insights", []))
        mine, theirs = "甲身上已經沒有他要出的那一樣了。", "你身上已經沒有要出的那一樣了。"
    assert _do(content, world, "乙", lambda g: g.peer_request("甲", "discuss", {"arg": "yes:insight:huo"}))[0] is None
    msgs, calls = _answer_like_the_server(content, world, monkeypatch)
    assert calls == 0 and msgs == [mine]
    assert world.get_season().invites == []
    head = _load(world, "甲").journal[0]
    assert (head.title, head.lines) == ("論武不成・乙", [engine.INVITE_LAPSED.format(who="乙", what="論武"), theirs])
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None


@pytest.mark.parametrize("why", ["same_insight", "their_side"])
def test_fb245_a_pick_that_cannot_fit_is_refused_without_the_model(content, world, no_ollama, monkeypatch, why):
    """你挑的那一樣合不成（跟他出的是同一樣、他那邊合不成）：一樣不開單、不叫模型，回原本那一句，邀請留著換一樣再答。
    同一個意境兩邊各出一個：一個人合併同一個意境是可以的（fusion.merge_problem 不擋），以前會先開單取名才回「同一樣」。"""
    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", insights=("huo", "feng"))  # 兩個人都有「風」
    _invite(content, world)
    if why == "same_insight":
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


# ── 原 test_fb117.py（整檔搬進來） ──
# FB-117 玩家互動的畫面與文字（企劃者 2026-10-14 在遊戲裡碰到第一件）：
# - 場景底下論武那一列的「答應」以前是一顆沒說為什麼的灰鈕：現在是「挑一樣答應」，按了打開邀你的人的玩家卡、捲到答應那一格；
# - 答應的下拉清單預設第一樣合得成的，合不成的灰掉寫原因；挑的那一樣不行時邀請留著，真的作廢時發邀請的人收到一句；
# - 其餘各件見各段。
#
# 兩個角色開在同一個資料庫，每一個動作照伺服器的做法先從資料庫重讀自己（同 test_discuss、test_spar）。網頁的部分照
# test_prologue_web 的做法把整支 app.js 放進 node 的假瀏覽器（沒有 node 就略過）。

NOW_fb117 = 1000.0  # 同 test_discuss


needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# test_prologue_web 的假瀏覽器，多交出這一份要測的名字
DRIVER = BASE_DRIVER.replace(
    '"bookHtml", "peerHtml"]',
    '"bookHtml", "peerHtml", "socialHtml", "peerActsHtml", "openPeer", "callPeers", "peerAct", "refreshPeer", "openCalls"]',
)


assert DRIVER != BASE_DRIVER


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _main(content, world, name):
    return _do(content, world, name, server.main_view)[0]


def _card(content, world, name, other):
    return _do(content, world, name, lambda g: g.peer_card(other))[0]


def _answers(card):
    return [b for b in card["actions"] if b["action"] == "discuss"]


def _two_picks(world):
    """乙手上兩個都跟「風」合得成的意境（火、水）：答應那一格才是下拉清單（論武只合意境）。"""
    state = _load(world, "乙")
    state.player.insights = ["huo", "shui"]
    CharacterStore(world.db).save(state)


def _give(world, name, **fields):
    """改一個人的存檔（測試用）：fields 是 player 上的欄位。"""
    state = _load(world, name)
    for key, value in fields.items():
        setattr(state.player, key, value)
    CharacterStore(world.db).save(state)


# ── 第一件：場景底下論武那一列的答應 ──


def test_the_scene_row_for_a_discussion_opens_his_card(pair):
    content, world = pair
    _invite(content, world)
    [call] = _do(content, world, "乙", lambda g: g.calls_here())[0]
    yes, no = call["options"]
    assert call["text"] == "甲邀你論武。"
    assert yes["label"] == social.PICK_TO_ANSWER and yes["enabled"] and yes["peer"] == "甲" and yes["id"].startswith("invite:yes:")
    assert no["label"] == "婉拒" and no["enabled"] and "peer" not in no
    # 選單上那一顆照舊是灰的（引擎不收，整季機器人與假人不會按到），字寫去哪裡答
    options = {o.id: o for o in _do(content, world, "乙", lambda g: g.options(odds=False))[0]}
    assert not options[yes["id"]].enabled and "玩家卡" in options[yes["id"]].label


def test_other_invitations_keep_their_plain_buttons(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    [call] = _do(content, world, "乙", lambda g: g.calls_here())[0]
    assert [o["label"] for o in call["options"]] == ["答應", "婉拒"] and all("peer" not in o for o in call["options"])


@needs_node
def test_the_scene_and_the_fold_draw_it_as_a_button_that_opens_the_card(pair):
    content, world = pair
    _invite(content, world)
    m = _main(content, world, "乙")
    out = run(m, "return { scene: H.socialHtml(m), peers: H.callPeers(m), bar: H.actionBar(m) };")
    yes_id = next(o["id"] for c in m["calls"] for o in c["options"] if o.get("peer"))
    assert f'<button class="btn small" data-act="peer-answer" data-name="甲">{social.PICK_TO_ANSWER}</button>' in out["scene"]
    assert out["peers"] == {yes_id: "甲"}
    # 「此地還能做」裡同一顆（選單上的全名）也畫成打開玩家卡，按得下去
    assert '<button class="btn" data-act="peer-answer" data-name="甲"><span>答應甲的論武（在對方的玩家卡上挑你要出的）</span></button>' in out["bar"]
    assert f'data-id="{yes_id}"' not in out["bar"]


@needs_node
def test_opening_the_card_from_the_scene_scrolls_to_the_answer(pair):
    content, world = pair
    _two_picks(world)
    _invite(content, world)
    card = _card(content, world, "乙", "甲")
    script = """
      const seen = [];
      T.qs['.peer-card [data-answer="discuss"]'] = {
        classList: { add: (c) => seen.push(["class", c]) },
        scrollIntoView: (o) => seen.push(["scroll", o.block]),
      };
      return (async () => {
        await H.openPeer("甲", "discuss");
        return { seen, html: H.peerHtml(), asked: T.calls.map((c) => c[0]) };
      })();"""
    out = run(_main(content, world, "乙"), script, responses={"/api/peer": {"card": card, "gone": social.GONE}})
    assert out["asked"] == ["/api/peer?name=%E7%94%B2"]  # 只問卡，不送任何動作
    assert out["seen"] == [["class", "peer-focus"], ["scroll", "nearest"]]
    assert 'class="peer-pick" data-answer="discuss"' in out["html"]


@needs_node
def test_when_he_is_gone_the_card_says_why_and_what_to_do(pair):
    content, world = pair
    _invite(content, world)
    out = run(_main(content, world, "乙"), "return (async () => { await H.openPeer('甲', 'discuss'); return H.peerHtml(); })();",
              responses={"/api/peer": {"card": None, "gone": social.GONE}})
    assert social.GONE in out and "這份邀請答不成了" in out


# ── 第二件：答應的下拉清單與邀請作廢 ──


@pytest.fixture
def twins(content, world):
    """兩個人都有「風」：甲出它，乙清單上第一項就是它（同一樣），第二項「火」合得成（論武只合意境）。"""
    from conftest import install_season_one

    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", insights=("feng", "huo"))
    return content, world


def test_the_list_starts_at_the_first_one_that_fits(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」
    rows = _answers(_card(content, world, "乙", "甲"))
    assert [(b["arg"], b["enabled"], b["pick"]) for b in rows] == [
        ("yes:insight:feng", False, "「風」（同一樣）"),
        ("yes:insight:huo", True, "「火」"),
        ("no", True, ""),
    ]
    assert {b["group"] for b in rows[:2]} == {discuss.ANSWER_GROUP}


@needs_node
def test_the_web_list_disables_what_cannot_fit_and_selects_the_first_that_can(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」，乙的「火」合得成
    rows = _answers(_card(content, world, "乙", "甲"))  # 只畫論武那幾顆：索引從 0 起
    html = run(_main(content, world, "乙"), f"return H.peerActsHtml({json.dumps(rows, ensure_ascii=False)});")
    assert '<option value="0" disabled>「風」（同一樣）</option>' in html
    assert '<option value="1" selected>「火」</option>' in html
    assert '<button class="btn" data-act="peer-pick"><span class="pa-name">以此應之</span>' in html


@needs_node
def test_a_group_with_nothing_to_pick_is_grayed(content):
    from test_social import _player

    actions = [
        {"action": "discuss", "arg": "yes:a", "label": "以甲應之", "group": "以此應之", "pick": "甲（同一樣）", "enabled": False},
        {"action": "discuss", "arg": "yes:b", "label": "以乙應之", "group": "以此應之", "pick": "乙（已經有了）", "enabled": False},
    ]
    html = run(server.main_view(_player(content, "丙")), f"return H.peerActsHtml({json.dumps(actions, ensure_ascii=False)});")
    assert 'data-act="peer-pick" disabled>' in html and " selected" not in html


def test_nothing_fits_one_gray_button_says_why(twins):
    content, world = twins
    _give(world, "乙", insights=["feng"])  # 乙身上只剩「風」，跟甲出的同一樣
    _invite(content, world)
    rows = _answers(_card(content, world, "乙", "甲"))
    assert [(b["label"], b["enabled"], b["note"]) for b in rows] == [
        (discuss.ANSWER_NONE, False, engine.DISCUSS_SAME), ("婉拒論武", True, ""),
    ]


def test_different_reasons_are_listed_short(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」
    _give(world, "乙", stats={**_load(world, "乙").player.stats, "xinde": 0})
    rows = _answers(_card(content, world, "乙", "甲"))
    # 「風」＋「風」：同一樣；「火」＋「風」：心得不足
    assert rows[0]["enabled"] is False and rows[0]["note"] == discuss.NONE_FITS.format(
        theirs="「風」", why="「風」同一樣、「火」心得不足")


def test_a_pick_that_does_not_fit_keeps_the_invitation(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」；乙的「風」是同一樣，「火」＋風才合得成
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:feng", "proposed": (None, "")}))[0]
    assert msgs == [engine.DISCUSS_SAME]
    assert len(world.get_season().invites) == 1  # 換一樣再答
    assert not any(e.title.startswith("論武不成") for e in _load(world, "甲").journal)
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("烈焰境", "")}))[0]
    assert "烈焰境" in msgs[0] and world.get_season().invites == []


def test_a_lapsed_discussion_tells_the_sender(twins):
    content, world = twins
    _invite(content, world)
    _give(world, "甲", insights=[])  # 甲要出的那一樣沒了
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": (None, "")}))[0]
    assert msgs == ["甲身上已經沒有他要出的那一樣了。"]
    assert world.get_season().invites == []
    head = _load(world, "甲").journal[0]
    assert head.title == "論武不成・乙"
    assert head.lines == [engine.INVITE_LAPSED.format(who="乙", what="論武"), "你身上已經沒有要出的那一樣了。"]


def test_a_lapsed_spar_tells_the_sender(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    _give(world, "甲", stamina=0.0)
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "yes"}))[0]
    cost = content.config.action_cost["train"]
    assert msgs == [f"甲體力不夠（切磋要 {cost} 點）。"]
    head = _load(world, "甲").journal[0]
    assert head.title == "切磋不成・乙" and head.lines[1] == f"你體力不夠（切磋要 {cost} 點）。"


def test_an_answer_after_he_left_tells_him_later(pair):
    """答應的那一刻他不在這裡了（走了、下線）：照舊收掉邀請、說他不在了；他的江湖紀錄裡補一句。"""
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    iid = world.get_season().invites[0].id
    _give(world, "甲", location="lake")
    _do(content, world, "乙", lambda g: g.answer_invite(g.state.world.invites[0], None, "yes"))
    assert not any(i.id == iid for i in world.get_season().invites)
    head = _load(world, "甲").journal[0]
    assert head.title == "切磋不成・乙" and head.lines == [engine.INVITE_LAPSED.format(who="乙", what="切磋"), engine.INVITE_LAPSED_AWAY]


def test_a_bot_answers_with_one_that_fits(twins):
    """假人照同一張卡挑：按得下去的第一樣（同一樣的那一項灰著，不會挑到）。"""
    from conftest import FixedRandom

    from tianxia import bot_policy

    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」，乙按得下去的是「火」（「風」同一樣）
    slot = bot_policy.NamingSlot(open=True)
    _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.0), slot))
    assert slot.job is not None and slot.job.item == "insight:huo"


# ── 第三件：他發給你的打招呼、結伴，在他的卡上寫你這邊該做什麼 ──


def _row(card, action):
    return [(b["label"], b["arg"], b["note"], b["enabled"]) for b in card["actions"] if b["action"] == action]


def test_his_taunt_shows_the_replies_on_his_card(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "greet", {"arg": "taunt"}))
    assert _row(_card(content, world, "乙", "甲"), "greet") == [
        ("冷眼以對", "reply:cold", social.GREET_BACK.format(him="他"), True), ("出言回敬", "reply:retort", "", True),
        (social.MUTE_LABEL.format(him="他"), "mute", "", True),
    ]
    assert all(note == "等回應" for _, _, note, _ in _row(_card(content, world, "甲", "乙"), "greet"))  # 發的那一方照舊
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "greet", {"arg": "reply:cold"}))[0]
    assert msgs == ["甲斜眼打量你，出言挑釁。", "你冷眼以對。"] and world.get_season().invites == []
    head = _load(world, "乙").journal[0]
    assert (head.title, head.lines) == ("與甲", msgs)  # 跟場景底下那一顆同一則
    assert "你向乙斜眼打量，出言挑釁，乙冷眼以對。" in _load(world, "甲").journal[0].lines


def _card_for(content, world, name):
    _do(content, world, name, lambda g: g.make_mingtie([[0, 0, 10, 10, 60, 60]], [], ""))


def test_his_mingtie_shows_answer_and_decline_on_his_card(pair):
    content, world = pair
    _card_for(content, world, "甲")
    _do(content, world, "甲", lambda g: g.peer_act("乙", "mingtie", {"arg": "send"}))
    from tianxia import mingtie
    assert _row(_card(content, world, "乙", "甲"), "mingtie") == [("回帖", "yes", mingtie.NO_CARD, False), ("婉拒", "no", "", True)]
    assert _row(_card(content, world, "甲", "乙"), "mingtie")[0][2] == "等他回帖"  # 發的那一方
    _card_for(content, world, "乙")
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "mingtie", {"arg": "yes"}))[0]
    assert msgs == ["你回了帖，與甲互換了名帖。"]
    assert [x.name for x in _load(world, "乙").player.mingtie_box] == ["甲"]
    assert [x.name for x in _load(world, "甲").player.mingtie_box] == ["乙"]
    assert _row(_card(content, world, "甲", "乙"), "mingtie")[0][:2] == ("換新帖", "send")


def test_declining_his_mingtie_on_the_card(pair):
    content, world = pair
    _card_for(content, world, "甲")
    _do(content, world, "甲", lambda g: g.peer_act("乙", "mingtie", {"arg": "send"}))
    _do(content, world, "乙", lambda g: g.peer_act("甲", "mingtie", {"arg": "no"}))
    assert world.get_season().invites == [] and _load(world, "乙").player.mingtie_box == []
    assert "乙拱手婉拒了你的邀請。" in _load(world, "甲").journal[0].lines


# ── 第四件：論武取名等模型時的等候話；等的時候關了卡、換了人，回應回來不把舊卡彈出來 ──

HOLD = """
  // fetch 拿住不回，等 release()；setTimeout 只讓「等候的話」那一個（1500 毫秒）馬上跑
  let release;
  T.ctx.fetch = (url, opts) => { T.calls.push([url, opts && opts.body ? JSON.parse(opts.body) : null]);
    return new Promise((res) => { release = (data) => res({ ok: true, status: 200, json: () => Promise.resolve(data) }); }); };
  const real = T.ctx.setTimeout;
  T.ctx.setTimeout = (fn, ms) => (ms === 1500 ? (fn(), 0) : real(fn, ms));
"""


@needs_node
def test_answering_a_discussion_shows_its_own_waiting_line(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 武學重構：甲出「風」，乙以「火」應之
    card = _card(content, world, "乙", "甲")
    i = next(n for n, b in enumerate(card["actions"]) if b["arg"] == "yes:insight:huo")
    script = HOLD + f"""
      H.S.peer = {{ name: "甲", card: {json.dumps(card, ensure_ascii=False)} }};
      const p = H.peerAct({i});
      const waiting = T.bodyHtml.join("");
      release({{ card: null, gone: "", main: null, message: "<p>好了</p>" }});
      return p.then(() => ({{ waiting, sent: T.calls[0] }}));"""
    out = run(_main(content, world, "乙"), script)
    assert "兩人各陳所學，推敲新招……" in out["waiting"]
    assert out["sent"][1]["arg"] == "yes:insight:huo"


@needs_node
def test_a_reply_after_the_card_was_closed_does_not_reopen_it(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 武學重構：甲出「風」，乙以「火」應之
    card = _card(content, world, "乙", "甲")
    i = next(n for n, b in enumerate(card["actions"]) if b["arg"] == "yes:insight:huo")
    script = HOLD + f"""
      H.S.peer = {{ name: "甲", card: {json.dumps(card, ensure_ascii=False)} }};
      const p = H.peerAct({i});
      H.S.peer = {{ name: "丙", card: null, gone: "x" }};  // 等的時候關了卡、點開了丙
      release({{ card: {json.dumps(card, ensure_ascii=False)}, gone: "", main: null, message: "<p>「火」與「風」在你心中交融……很長的一段</p>",
                 brief: "論武有結果了：合出「烈焰境」。詳見江湖紀錄。" }});
      return p.then(() => ({{ peer: H.S.peer.name, toast: T.els.toast.textContent }}));"""
    out = run(_main(content, world, "乙"), script)
    assert out == {"peer": "丙", "toast": "論武有結果了：合出「烈焰境」。詳見江湖紀錄。"}  # 只講一句（FB-242）


# ── 第五件：玩家卡跟著輪詢更新 ──

FAKE_CARD = """
  // 畫面上那一張卡（假的）：換卡時記下做了什麼；新的那一張有一個下拉清單
  const log = [];
  const nowSel = { options: [{ value: "0" }, { value: "1" }], value: "0" };
  const now = { scrollTop: 0, querySelectorAll: (sel) => (sel === ".peer-pick select" ? [nowSel] : []) };
  const old = {
    scrollTop: 40, previousElementSibling: { classList: { contains: (c) => c === "sheet-bg" }, remove: () => log.push("bg") },
    querySelectorAll: () => [], remove: () => log.push("old"),
    insertAdjacentHTML: (pos, html) => { log.push(pos); T.qs[".peer-card"] = now; log.push(html.includes("以此應之") ? "answer" : "plain");
      log.push(html.includes('class="sheet peer-card still"') ? "still" : "moving"); },
  };
  T.qs[".peer-card"] = old;
"""


def _refresh_script(before, after, extra=""):
    return FAKE_CARD + f"""
      H.S.peer = {{ name: "甲", card: {json.dumps(before, ensure_ascii=False)} }};
      {extra}
      return (async () => {{
        await H.refreshPeer();
        await new Promise((r) => setTimeout(r, 0));
        return {{ log, card: H.S.peer.card && H.S.peer.card.actions.length, top: now.scrollTop, asked: T.calls.map((c) => c[0]) }};
      }})();"""


@needs_node
def test_an_open_card_follows_the_poll(twins):
    content, world = twins
    before = _card(content, world, "乙", "甲")
    _invite(content, world, "insight:feng")  # 甲出「風」，乙有合得成的（「火」），卡上是那一格下拉清單
    after = _card(content, world, "乙", "甲")
    out = run(_main(content, world, "乙"), _refresh_script(before, after), responses={"/api/peer": {"card": after, "gone": social.GONE}})
    assert out["asked"] == ["/api/peer?name=%E7%94%B2"]
    assert out["log"] == ["afterend", "answer", "still", "old", "bg"] and out["card"] == len(after["actions"]) and out["top"] == 40


@needs_node
def test_an_unchanged_card_is_left_alone(twins):
    content, world = twins
    card = _card(content, world, "乙", "甲")
    out = run(_main(content, world, "乙"), _refresh_script(card, card), responses={"/api/peer": {"card": card, "gone": social.GONE}})
    assert out["log"] == []


@needs_node
def test_a_held_finger_waits_for_release(twins):
    content, world = twins
    before = _card(content, world, "乙", "甲")
    _invite(content, world)
    after = _card(content, world, "乙", "甲")
    held = "T.docListeners.pointerdown.forEach((f) => f());"
    script = FAKE_CARD + f"""
      H.S.peer = {{ name: "甲", card: {json.dumps(before, ensure_ascii=False)} }};
      {held}
      return (async () => {{
        await H.refreshPeer();
        const during = [log.length, H.S.peer.card.actions.length];
        T.docListeners.pointerup.filter((f) => f.name === "releasePointer").forEach((f) => f());
        await new Promise((r) => setTimeout(r, 5));
        return {{ during, after: [log.length, H.S.peer.card.actions.length] }};
      }})();"""
    out = run(_main(content, world, "乙"), script, responses={"/api/peer": {"card": after, "gone": social.GONE}})
    assert out["during"] == [0, len(before["actions"])]
    assert out["after"] == [5, len(after["actions"])]


@needs_node
def test_no_swap_while_a_confirm_or_amount_is_open(twins):
    content, world = twins
    before = _card(content, world, "乙", "甲")
    _invite(content, world)
    after = _card(content, world, "乙", "甲")
    out = run(_main(content, world, "乙"), _refresh_script(before, after, "H.S.peer.amountFor = 5;"),
              responses={"/api/peer": {"card": after, "gone": social.GONE}})
    assert out["log"] == [] and out["card"] == len(before["actions"])


# ── 第六件：場景底下最多畫兩份邀請，其餘收成一行 ──


@needs_node
def test_at_most_two_invitations_under_the_scene(pair):
    content, world = pair
    _card_for(content, world, "甲")
    for kind, arg in (("greet", "taunt"), ("mingtie", "send"), ("spar", "invite"), ("discuss", "invite:insight:feng")):
        _do(content, world, "甲", lambda g, k=kind, a=arg: g.peer_act("乙", k, {"arg": a}))
    m = _main(content, world, "乙")
    assert len(m["calls"]) == 4
    out = run(m, "const shut = H.socialHtml(m); H.S.main = m; H.openCalls(); const open = H.socialHtml(m);"
                 "m.calls = m.calls.slice(0, 2); const few = H.socialHtml(m); return { shut, open, few, after: H.S.callsOpen };")
    assert out["shut"].count('<div class="call">') == 2 and "還有 2 份邀請 ▾" in out["shut"]
    assert out["shut"].index("甲斜眼打量你，出言挑釁。") < out["shut"].index("還有 2 份邀請")  # 舊的在前
    assert out["open"].count('<div class="call">') == 4 and "還有" not in out["open"]
    # 回掉兩份：剩下的兩份照樣攤著（FB-241：以前回到兩份以內就收回去）
    assert out["few"].count('<div class="call">') == 2 and "還有" not in out["few"] and len(out["after"]) == 4


# 第一屏還放不下（例：師父的框在）：FB-107 的收法多一步（6b），從最後一份往前收、併進「還有 N 份邀請」那一行
CALLS = {"bottom": 830, "actbar": True, "scene": True, "calls": 2, "callsTotal": 4, "callsMore": "還有 2 份邀請 ▾"}


@needs_node
def test_the_fit_folds_invitations_from_the_last_one():
    from test_jianghu_page_web import run as fit_run

    out = fit_run(CALLS)  # 830 − 間距 30 = 800，還差 60：收掉第二份（70）就夠
    assert out["fitted"] == ["space", "calls"] and out["calls"] == [False, True] and out["more"] == ["還有 3 份邀請 ▾", ""]
    out = fit_run({**CALLS, "bottom": 900})  # 兩份都收掉
    assert out["calls"] == [True, True] and out["more"] == ["有 4 份邀請等你回應 ▾", ""]


@needs_node
def test_the_fit_adds_the_line_when_there_was_none_and_takes_it_back():
    from test_jianghu_page_web import run as fit_run

    layout = {**CALLS, "callsTotal": 2, "callsMore": ""}
    out = fit_run(layout)
    assert out["calls"] == [False, True] and out["more"] == ["還有 1 份邀請 ▾", "1"]
    script = "H.fitFirstScreen(); L.bottom = 700; H.fitFirstScreen(); return snap();"  # 放得下了：攤回來、補的那一行拿掉
    out = fit_run(layout, script)
    assert out["fitted"] == [] and out["calls"] == [False, False] and out["more"] is None
    script = "H.fitFirstScreen(); L.bottom = 700; H.fitFirstScreen(); return snap();"
    out = fit_run(CALLS, script)  # 原本就有的那一行：字換回來
    assert out["more"] == ["還有 2 份邀請 ▾", ""]


@needs_node
def _calls_main(*ids):
    """第一屏收法的假頁面用的 S.main：邀請那幾份（回應鈕的 id 最後一段是編號）。"""
    return {"card_id": 7, "scene": "<p>x</p>", "on_road": False,
            "calls": [{"text": f"{i}邀你切磋。", "options": [{"id": f"invite:yes:{i}"}, {"id": f"invite:no:{i}"}]} for i in ids]}


def test_opened_invitations_are_not_folded_again():
    from test_jianghu_page_web import run as fit_run

    out = fit_run(CALLS, S={"callsOpen": ["a", "b"], "main": _calls_main("a", "b")})
    assert "calls" not in out["fitted"] and out["calls"] == [False, False]
    out = fit_run(CALLS, S={"callsOpen": ["a"], "main": _calls_main("a", "b")})  # 點開之後來了新的一份：照常收
    assert "calls" in out["fitted"]


@needs_node
def test_the_fit_counts_the_line_it_adds():
    """6b 補上的「還有 N 份邀請」那一行也佔高度：先放好那一行再量。以前收完才補，收一份就停，補上之後行動列又掉回分頁列底下
    （實機 375×812、兩份、師父的框在：行動列 679～777）。"""
    from test_jianghu_page_web import run as fit_run

    # 830 − 間距 30 = 800；收一份（−70）＋那一行（+35）是 765，還差，再收一份
    out = fit_run({**CALLS, "callsTotal": 2, "callsMore": ""}, save={"moreLine": 35})
    assert out["calls"] == [True, True] and out["more"] == ["有 2 份邀請等你回應 ▾", "1"] and out["bottom"] <= 740


# ── FB-241：只有一、兩份邀請被第一屏收成一行時，點了攤不開 ──


@needs_node
def test_fb241_one_folded_invitation_opens_when_tapped():
    """一份邀請、師父的框在：6b 收成「有 1 份邀請等你回應 ▾」；點了（openCalls 記下那一份）之後重量，不再收。"""
    from test_jianghu_page_web import run as fit_run

    one = {**CALLS, "bottom": 820, "calls": 1, "callsTotal": 1, "callsMore": ""}
    out = fit_run(one, S={"main": _calls_main("a")})
    assert out["calls"] == [True] and out["more"] == ["有 1 份邀請等你回應 ▾", "1"]
    out = fit_run(one, S={"callsOpen": ["a"], "main": _calls_main("a")})
    assert "calls" not in out["fitted"] and out["calls"] == [False]


@needs_node
def test_fb241_tapping_keeps_one_or_two_invitations_open(pair):
    """以前 socialHtml 看到邀請沒超過兩份就把 S.callsOpen 改回假，點了等於沒點。現在點開那時的那幾份還在就一直攤著，
    回掉一份照樣攤著，來了新的一份才照常收。"""
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "greet", {"arg": "taunt"}))
    m = _main(content, world, "乙")
    script = """
      const key = (c) => c.options[0].id.split(":").pop();
      H.S.main = m; H.openCalls();
      const first = H.socialHtml(m);
      const kept = Array.isArray(H.S.callsOpen) && H.S.callsOpen.length === 1;
      const newer = { text: "丙邀你切磋。", options: [{ id: "invite:yes:zz", label: "答應", enabled: true }] };
      const more = H.socialHtml({ ...m, calls: [...m.calls, newer] });
      return { kept, first, opened: H.S.callsOpen };"""
    out = run(m, script)
    assert out["kept"] is True and out["first"].count('<div class="call">') == 1
    assert out["opened"] is False  # 來了點開時沒有的那一份：照常收


# ── 第七件：決戰輪到你出招時，「此地還有」排在三招後面 ──


@needs_node
def test_on_your_battle_turn_the_people_here_come_after_the_three_moves(pair):
    content, world = pair
    m = _main(content, world, "乙")
    m["here"] = [{"name": f"路人{i}", "side": "散人"} for i in range(8)]
    plain = run(m, "return H.pageJianghu();")
    scene = plain.index('<section class="card scene">')
    assert scene < plain.index('<div class="here">') < plain.index("</section>", scene)  # 平常：在場景卡裡
    moves = [{"id": f"battle:act:guan_{k}", "label": k, "enabled": True, "wait": "", "confirm": "", "confirm_yes": ""}
             for k in ("strong", "hold", "raid")]
    turn = run({**m, "options": moves}, "return H.pageJianghu();")
    scene_end = turn.index("</section>", turn.index('<section class="card scene">'))
    assert '<div class="here">' not in turn[:scene_end]
    assert turn.index('data-id="battle:act:guan_raid"') < turn.index('<section class="card people-after"><div class="here">')


# ── 第八件：論武共同首創的那一方 ──


def test_the_inviter_is_told_they_co_founded_the_insight(pair):
    from tianxia import fusion

    content, world = pair
    _invite(content, world, "insight:feng")
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("風火境", "")}))
    theirs = " ".join(_load(world, "甲").journal[0].lines)
    assert fusion.CO_FIRST_INSIGHT.format(other="乙").strip() in theirs and "首悟。" not in theirs


def test_someone_else_following_the_recipe_still_reads_who_founded_it(pair):
    content, world = pair
    _invite(content, world)  # 甲出「風」，乙出「火」
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("風火境", "")}))
    third = _make(content, world, "丙", insights=("feng", "huo"))  # 照著合同一爐
    lines = " ".join(third.forge(None, ["feng", "huo"], proposed=(None, "")))
    assert "這個意境由乙、甲首悟。" in lines


# ── 第九件：同一對人每個遊戲日的上限寫換日的那一刻，三本帳一個寫法 ──


@pytest.mark.parametrize("kind, head, verb", [
    ("gift", "你們已經互贈過 5 回了", "送"), ("discuss", "你們已經論武過 2 回了", "論武"), ("spar", "你們已經切磋過 2 場了", "切磋"),
])
def test_a_full_pair_names_when_the_day_turns(pair, kind, head, verb):
    from tianxia import calendar, rules

    content, world = pair
    line, game = _do(content, world, "甲", lambda g: social.pair_full(g, kind))
    moment = calendar.stamp_text(rules.day_ends(content, game.state.world), content, game.state.world)
    assert line == f"{head}，{moment} 之後再{verb}。" and "今天" not in line


def test_a_full_pair_on_the_last_game_day_says_not_this_season(pair, monkeypatch):
    content, world = pair
    monkeypatch.setattr(social, "day_turn", lambda c, w: ("season", None))
    assert _do(content, world, "甲", lambda g: social.pair_full(g, "spar"))[0] == "你們已經切磋過 2 場了，這一季之內不能再切磋了。"
    monkeypatch.setattr(social, "day_turn", lambda c, w: ("later", None))
    assert _do(content, world, "甲", lambda g: social.pair_full(g, "gift"))[0] == "你們已經互贈過 5 回了，過一陣子再送。"


# ── 第十件：答應切磋的那一方紀錄也有內文 ──


def test_both_sides_of_a_spar_get_the_result_line(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    iid = world.get_season().invites[0].id
    _do(content, world, "乙", lambda g: g.choose(f"invite:yes:{iid}"))  # 場景底下那一顆（選單的 invite:yes）
    for name, rival in (("甲", "乙"), ("乙", "甲")):
        head = _load(world, name).journal[0]
        assert head.title == f"切磋・{rival}" and head.lines and head.lines[0].startswith("⚔") and rival in head.lines[0]


# ── FB-242：論武等候中換了卡，提示泡泡只講一句 ──


def test_fb242_the_server_gives_a_brief_line_for_the_toast(pair, monkeypatch):
    """/api/peer/act 多回 brief：論武合成了是「論武有結果了：合出【某某】。詳見江湖紀錄。」，其餘是回話的第一句。"""
    from fastapi.testclient import TestClient

    content, world = pair
    _invite(content, world)
    state = CharacterStore(world.db).load("乙")
    game = engine.Game(content, state, __import__("random").Random(0), world)
    game.client = None
    game.sync(NOW_fb117)
    # 只驗這個端點怎麼組回應：拿鎖、同步、存檔那一套（act、look）換成直接做，不碰伺服器的資料庫
    monkeypatch.setattr(server, "_game", lambda request: game)
    monkeypatch.setattr(server, "act", lambda g, action, **k: action(g))
    monkeypatch.setattr(server, "look", lambda g, view: view(g) if view is not server.main_view else None)
    monkeypatch.setattr(server, "prepare_peer", lambda *a, **k: ("烈焰境", "風助火勢。"))
    monkeypatch.setattr(server, "_tell_tabs", lambda g: None)
    client = TestClient(server.app)
    r = client.post("/api/peer/act", json={"name": "甲", "action": "discuss", "arg": "yes:insight:huo"}).json()
    assert r["brief"] == "論武有結果了：合出「烈焰境」。詳見江湖紀錄。" and len(r["message"]) > len(r["brief"])
    monkeypatch.setattr(server, "screen_peer", lambda *a, **k: "")
    r = client.post("/api/peer/act", json={"name": "甲", "action": "greet", "arg": "taunt"}).json()
    assert r["brief"] == "你向甲斜眼打量，出言挑釁。"


def test_fb242_brief_is_the_first_sentence_cut_short():
    assert social.brief(["甲身上已經沒有他要出的那一樣了。後面還有。", "第二則"]) == "甲身上已經沒有他要出的那一樣了。"
    assert social.brief(["一" * 60]) == "一" * social.BRIEF_MAX + "……"
    assert social.brief([]) == "" and social.brief(None) == ""
    from tianxia.martial_arts import Insight

    assert social.thing_label(Insight(id="x", name="風火境", attribute="快")) == "「風火境」"


# ── FB-243：論武的兩句字 ──


def test_fb243_a_co_founder_merging_again_is_not_told_it_is_the_first_time(pair):
    """共同首創的人熔掉之後自己再合一次：寫「這個意境是你與某某首悟的」，不寫「江湖上第一次」。"""
    from tianxia import fusion

    content, world = pair
    _invite(content, world)  # 甲出「風」，乙出「火」
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("風火境", "")}))
    state = _load(world, "甲")
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    _melt(state, made.id)
    state.player.insights.append("huo")  # 自己也悟了「火」，自己合一次
    CharacterStore(world.db).save(state)
    msgs = _do(content, world, "甲", lambda g: g.forge(None, ["feng", "huo"], proposed=(None, "")))[0]
    text = " ".join(msgs)
    assert fusion.CO_OWN_INSIGHT.format(other="乙").strip() in text and "江湖上第一次" not in text


def _melt(state, insight_id):
    """熔掉（只拿掉這一份意境，不必算心得）。"""
    from tianxia import insight_fx

    state.player.insights.remove(insight_id)
    insight_fx.drop(state, insight_id)


def test_fb243_discussing_the_same_recipe_again_is_not_the_first_time(pair):
    """同一對人之後再論出同一個意境（兩人都熔掉了）：發邀請的那一方也不寫「江湖上第一次」。"""
    from tianxia import fusion

    content, world = pair
    _invite(content, world)
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("風火境", "")}))
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    for name in ("甲", "乙"):
        state = _load(world, name)
        _melt(state, made.id)
        state.player.stamina = 100.0
        CharacterStore(world.db).save(state)
    key = "|".join(sorted(("甲", "乙")))
    world.mutate_season(lambda s: s.discuss_tally.pop(key, None))  # 今天的帳清掉，再論一回
    _invite(content, world)
    _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": (None, "")}))
    theirs = " ".join(_load(world, "甲").journal[0].lines)
    assert fusion.CO_OWN_INSIGHT.format(other="乙").strip() in theirs and "江湖上第一次" not in theirs


def test_fb243_their_side_refusal_is_written_from_your_side(twins):
    """答應時對方那邊合不成：不貼他那一句原話（「你已經悟得了」的你是他），照那兩三個字寫成從你這邊看的話。"""
    from types import SimpleNamespace

    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」，乙出「火」
    own_words = engine._refusal("這兩個合起來還是「風火境」，你已經悟得了。", "已經有了")  # 寫給甲看的那一句
    game = _do(content, world, "乙", lambda g: g)[1]
    peer = SimpleNamespace(state=_load(world, "甲"), discuss_problem=lambda *args: own_words)
    line = game.discuss_item_problem(world.get_season().invites[0], peer, "insight:huo")
    assert line == "甲那邊合不成：合出來的那一樣他已經有了。" and line.short == "他那邊已經有了"
    unknown = SimpleNamespace(state=peer.state, discuss_problem=lambda *args: "找不到它的資料。")  # 沒有兩三個字的那幾句
    assert game.discuss_item_problem(world.get_season().invites[0], unknown, "insight:huo") == "甲那邊合不成。"


# ── FB-244：切磋兩邊的江湖紀錄對稱 ──


@pytest.mark.parametrize("via", ["scene", "card"])
def test_fb244_both_spar_entries_show_their_exp_and_link_their_report(pair, via):
    """發邀請的那一方以前只寫「心得 +N」、沒連戰報；答應的那一方寫「經驗 +N（每人）」。現在兩邊各寫各自拿到的經驗與心得、
    各連自己那一份戰報，不寫「（每人）」。從場景底下答應（選單）、從玩家卡答應都一樣。"""
    content, world = pair
    exp = content.config.spar.exp
    before = {n: _load(world, n).player.member.exp for n in ("甲", "乙")}
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    if via == "scene":
        iid = world.get_season().invites[0].id
        _do(content, world, "乙", lambda g: g.choose(f"invite:yes:{iid}"))
    else:
        _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "yes"}))
    for name in ("甲", "乙"):
        state = _load(world, name)
        head = state.journal[0]
        assert f"經驗 +{exp}" in head.changes and not any("每人" in c for c in head.changes), head.changes
        assert any(c.startswith("心得 +") for c in head.changes)
        assert head.battle_id is not None and head.battle_id == state.battles[-1].id
        assert state.player.member.exp != before[name] or state.player.member.level > 1  # 經驗真的加了
