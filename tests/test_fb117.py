"""FB-117 玩家互動的畫面與文字（企劃者 2026-10-14 在遊戲裡碰到第一件）：
- 場景底下論武那一列的「答應」以前是一顆沒說為什麼的灰鈕：現在是「挑一樣答應」，按了打開邀你的人的玩家卡、捲到答應那一格；
- 答應的下拉清單預設第一樣合得成的，合不成的灰掉寫原因；挑的那一樣不行時邀請留著，真的作廢時發邀請的人收到一句；
- 其餘各件見各段。

兩個角色開在同一個資料庫，每一個動作照伺服器的做法先從資料庫重讀自己（同 test_discuss、test_spar）。網頁的部分照
test_prologue_web 的做法把整支 app.js 放進 node 的假瀏覽器（沒有 node 就略過）。"""
from __future__ import annotations

import json

import pytest
from test_discuss import _do, _invite, _load, _make, pair  # noqa: F401（pair 是 fixture）
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia import discuss, engine, social
from tianxia.characters import CharacterStore

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

# test_prologue_web 的假瀏覽器，多交出這一份要測的名字
DRIVER = BASE_DRIVER.replace(
    '"bookHtml", "peerHtml"]',
    '"bookHtml", "peerHtml", "socialHtml", "peerActsHtml", "openPeer", "callPeers", "peerAct"]',
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
    """兩個人都有【粗淺拳腳】：甲出它，乙清單上第一項就是它（同一樣），第二項「火」才合得成。"""
    from conftest import install_season_one

    install_season_one(content)
    content.config.auto_open_first_season = True
    _make(content, world, "甲", insights=("feng",))
    _make(content, world, "乙", insights=("huo",))
    return content, world


def test_the_list_starts_at_the_first_one_that_fits(twins):
    content, world = twins
    _invite(content, world)  # 甲出【粗淺拳腳】
    rows = _answers(_card(content, world, "乙", "甲"))
    assert [(b["arg"], b["enabled"], b["pick"]) for b in rows] == [
        ("yes:art:basic_fist", False, "【粗淺拳腳】（同一樣）"),
        ("yes:insight:huo", True, "「火」"),
        ("no", True, ""),
    ]
    assert {b["group"] for b in rows[:2]} == {discuss.ANSWER_GROUP}


@needs_node
def test_the_web_list_disables_what_cannot_fit_and_selects_the_first_that_can(twins):
    content, world = twins
    _invite(content, world)
    rows = _answers(_card(content, world, "乙", "甲"))  # 只畫論武那幾顆：索引從 0 起
    html = run(_main(content, world, "乙"), f"return H.peerActsHtml({json.dumps(rows, ensure_ascii=False)});")
    assert '<option value="0" disabled>【粗淺拳腳】（同一樣）</option>' in html
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
    _give(world, "乙", insights=[])  # 乙身上只剩【粗淺拳腳】，跟甲出的同一樣
    _invite(content, world)
    rows = _answers(_card(content, world, "乙", "甲"))
    assert [(b["label"], b["enabled"], b["note"]) for b in rows] == [
        (discuss.ANSWER_NONE, False, engine.DISCUSS_SAME), ("婉拒論武", True, ""),
    ]


def test_different_reasons_are_listed_short(twins):
    content, world = twins
    _invite(content, world, "insight:feng")  # 甲出「風」
    _give(world, "乙", insights=["feng"], stats={**_load(world, "乙").player.stats, "xinde": 0})
    rows = _answers(_card(content, world, "乙", "甲"))
    # 【粗淺拳腳】＋風：心得不夠；「風」＋「風」：同一樣
    assert rows[0]["enabled"] is False and rows[0]["note"] == discuss.NONE_FITS.format(
        theirs="「風」", why="【粗淺拳腳】心得不足、「風」同一樣")


def test_a_pick_that_does_not_fit_keeps_the_invitation(twins):
    content, world = twins
    _invite(content, world)
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:art:basic_fist", "proposed": (None, "")}))[0]
    assert msgs == [engine.DISCUSS_SAME]
    assert len(world.get_season().invites) == 1  # 換一樣再答
    assert not any(e.title.startswith("論武不成") for e in _load(world, "甲").journal)
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "discuss", {"arg": "yes:insight:huo", "proposed": ("烈焰拳", "")}))[0]
    assert "烈焰拳" in msgs[0] and world.get_season().invites == []


def test_a_lapsed_discussion_tells_the_sender(twins):
    content, world = twins
    _invite(content, world)
    _give(world, "甲", member=_load(world, "甲").player.member.model_copy(update={"wugong_id": None}))  # 甲要出的那一樣沒了
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
    _invite(content, world)
    slot = bot_policy.NamingSlot(open=True)
    _do(content, world, "乙", lambda g: bot_policy._answer_discuss(g, FixedRandom(0.0), slot))
    assert slot.job is not None and slot.job.item == "insight:huo"


# ── 第三件：他發給你的打招呼、結伴，在他的卡上寫你這邊該做什麼 ──


def _row(card, action):
    return [(b["label"], b["arg"], b["note"], b["enabled"]) for b in card["actions"] if b["action"] == action]


def test_his_greeting_shows_the_replies_on_his_card(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "greet", {"arg": "bow"}))
    assert _row(_card(content, world, "乙", "甲"), "greet") == [
        ("抱拳還禮", "reply:bow", social.GREET_BACK.format(him="他"), True), ("點頭致意", "reply:nod", "", True),
    ]
    assert all(note == "等回禮" for _, _, note, _ in _row(_card(content, world, "甲", "乙"), "greet"))  # 發的那一方照舊
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "greet", {"arg": "reply:bow"}))[0]
    assert msgs == ["你抱拳還禮。"] and world.get_season().invites == []
    head = _load(world, "乙").journal[0]
    assert (head.title, head.lines) == ("與甲", ["你抱拳還禮。"])  # 跟場景底下那一顆同一則
    assert "你向乙抱拳見禮，乙抱拳還禮。" in _load(world, "甲").journal[0].lines


def test_his_travel_invite_shows_answer_and_decline_on_his_card(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "travel"))
    assert _row(_card(content, world, "乙", "甲"), "travel") == [
        ("答應結伴同行", "yes", social.TRAVEL_ASKED.format(him="他"), True), ("婉拒同行", "no", "", True),
    ]
    assert _row(_card(content, world, "甲", "乙"), "travel")[0][2] == "等他回應"  # 發的那一方照舊
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", "travel", {"arg": "yes"}))[0]
    assert msgs == ["你答應與甲結伴同行，等他動身。"]
    assert _load(world, "乙").player.tagalong.leader == "甲" and _load(world, "乙").journal[0].title == "結伴同行・甲"


def test_declining_his_travel_invite_on_the_card(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "travel"))
    _do(content, world, "乙", lambda g: g.peer_act("甲", "travel", {"arg": "no"}))
    assert world.get_season().invites == [] and _load(world, "乙").player.tagalong is None
    assert "乙拱手婉拒了你的邀請。" in _load(world, "甲").journal[0].lines
    assert _load(world, "乙").journal[0].title == "婉拒結伴同行"


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
    _invite(content, world)
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
    _invite(content, world)
    card = _card(content, world, "乙", "甲")
    i = next(n for n, b in enumerate(card["actions"]) if b["arg"] == "yes:insight:huo")
    script = HOLD + f"""
      H.S.peer = {{ name: "甲", card: {json.dumps(card, ensure_ascii=False)} }};
      const p = H.peerAct({i});
      H.S.peer = {{ name: "丙", card: null, gone: "x" }};  // 等的時候關了卡、點開了丙
      release({{ card: {json.dumps(card, ensure_ascii=False)}, gone: "", main: null, message: "<p>你以【粗淺拳腳】融入「火」</p>" }});
      return p.then(() => ({{ peer: H.S.peer.name, toast: T.els.toast.textContent }}));"""
    out = run(_main(content, world, "乙"), script)
    assert out == {"peer": "丙", "toast": "你以【粗淺拳腳】融入「火」"}
