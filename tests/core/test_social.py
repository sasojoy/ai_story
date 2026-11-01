"""玩家之間的互動（social.py）：第一層「此地還有誰」與玩家卡、卡上動作的登記表。"""
from __future__ import annotations

import random

import pytest

from tianxia import social
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import BotProfile
import re
from tianxia import howto, rules
from tianxia.engine import SNUB_NOTE, Game
from test_discuss import pair  # noqa: F401（fixture）
from tianxia import atlas, fusion, seal, social
from tianxia.rules import game_day
import server
import webharness

NOW = 1_000_000.0


def _player(content, name, *, at="town", now=NOW, bot=False, save=True):
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(now)
    game.state.player.location = at
    if bot:
        game.state.player.bot = BotProfile(personality="普通", seed=1)
    if save:
        CharacterStore(game.world.db).save(game.state)
    return game


@pytest.mark.smoke
def test_people_in_the_same_place_see_each_other(content):
    a = _player(content, "甲")
    _player(content, "乙")
    _player(content, "丙", at="lake")  # 別的地方
    assert a.peers_here() == [{"name": "乙", "side": "散人"}]


def test_only_recently_seen_people_are_listed(content):
    gap = content.config.presence_seconds
    a = _player(content, "甲", now=NOW + gap + 10)
    _player(content, "乙", now=NOW)  # 上次同步是 presence_seconds 以前：下線了
    _player(content, "丙", now=NOW + 20)
    assert [p["name"] for p in a.peers_here()] == ["丙"]


def test_people_on_the_road_are_not_listed_and_see_nobody(content):
    a = _player(content, "甲")
    b = _player(content, "乙", save=False)
    b.state.player.journey = _journey(b)
    CharacterStore(b.world.db).save(b.state)
    assert a.peers_here() == []
    assert b.peers_here() == []


def _journey(game):
    from tianxia.state import Journey

    return Journey(mode="walk", path=["lake"], arrive_at=[game.state.world.time + 3600])


def test_bots_are_listed_the_same_way_as_people(content):
    a = _player(content, "甲")
    _player(content, "乙", bot=True)
    _player(content, "丙")
    here = a.peers_here()
    assert sorted(p["name"] for p in here) == ["丙", "乙"] and all(p == {"name": p["name"], "side": "散人"} for p in here)
    assert a.peer_card("乙").keys() == a.peer_card("丙").keys()


def test_the_card_shows_title_level_and_worn_arts(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    card = a.peer_card("乙")
    assert card["name"] == "乙" and card["affiliation"] == "散人" and card["level"] == b.state.player.member.level
    kinds = [row["kind"] for row in card["arts"]]
    assert set(kinds) <= {"內功", "武學"} and all(row["name"] and row["quality"] for row in card["arts"])
    assert card["actions"] == [] or all("action" in x for x in card["actions"])


def test_someone_who_left_has_no_card(content):
    a = _player(content, "甲")
    _player(content, "乙", at="lake")
    assert a.peer_card("乙") is None and a.peer_card("沒這個人") is None
    assert a.peer_act("乙", "anything") == [social.GONE]


@pytest.fixture
def poke():
    """測試用的一種互動：卡上一顆鈕，按了在對方的銀兩上加 1。測完拿掉。"""
    def run(game, other, params):
        other.state.player.stats["silver"] = other.state.player.stats.get("silver", 0) + 1
        return [f"你戳了{other.state.player.name}一下（{params.get('arg')}）。"]

    action = social.register(social.CardAction(
        id="poke", buttons=lambda game, other: [social.CardButton(action="poke", label="戳一下", arg="x")], run=run,
    ))
    yield action
    social.ACTIONS.pop("poke", None)


def test_registered_actions_show_on_every_card_and_change_the_other_save(content, poke):
    a = _player(content, "甲")
    b = _player(content, "乙")
    silver = b.state.player.stats.get("silver", 0)
    card = a.peer_card("乙")
    assert {"action": "poke", "label": "戳一下", "arg": "x"}.items() <= card["actions"][-1].items()  # order 100：排在內建的幾種後面
    assert a.peer_act("乙", "poke", {"arg": "x"}) == ["你戳了乙一下（x）。"]
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.stats["silver"] == silver + 1
    assert stored.last_real == b.state.last_real  # 替他寫東西不替他補算時間：下了線的人不會因此一直掛在名單上
    assert a.peer_act("乙", "no-such") == ["（沒有這個動作。）"]


# ── 第二層：贈物、打招呼、結伴同行 ──


def _as(content, world, name, now):
    """伺服器那樣：讀他的存檔、補算到 now。做完要 _done 存回去。"""
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    game.sync(now)
    return game


def _done(game):
    CharacterStore(game.world.db).save(game.state)


def _titles(game):
    return [e.title for e in game.state.journal]


def _lines(game):
    return [line for e in game.state.journal for line in e.lines + e.changes]


def _calls(game):
    return game.calls_here()


def test_only_low_tier_materials_can_be_given(content):
    """贈物只剩素材（Joy 2026-10-19 拿掉銀兩、PM 建議拿掉回體丹，Joy「照建議」），而且只送得出 gift_max_tier 階以下的。"""
    a = _player(content, "甲")
    _player(content, "乙")
    a.state.player.stats["silver"] = 50
    a.state.player.materials = {"gang_1": 3, "gang_3": 2}
    card = a.peer_card("乙")
    gifts = [b for b in card["actions"] if b["action"] == "gift"]
    assert [b["arg"] for b in gifts] == ["material"]
    assert gifts[0]["choices"] == [{"id": "gang_1", "label": content.materials["gang_1"].name, "max": 3}]
    assert a.peer_act("乙", "gift", {"arg": "silver", "amount": 20}) == ["（要送多少？）"]
    assert a.peer_act("乙", "gift", {"arg": "pill", "amount": 1}) == ["（要送多少？）"]
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_3", "amount": 1}) == ["（這一樣送不出去。）"]
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 4}) == ["（身上沒有那麼多。）"]
    a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 2})
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    assert b.state.player.materials == {"gang_1": 2} and a.state.player.materials == {"gang_1": 1, "gang_3": 2}
    assert "收禮・甲" in _titles(b) and "贈物・乙" in _titles(a)
    assert a.state.player.stats["silver"] == 50


def test_one_person_can_give_only_so_many_times_a_day(content):
    """一個人一天總共送 gift_per_day 次（不分送誰；照回體丹的換日）。"""
    content.config.gift_per_day = 2
    content.config.gift_per_pair_day = 9
    a = _player(content, "甲")
    for name in ("乙", "丙"):
        _player(content, name)
    a.state.player.materials = {"gang_1": 9}
    a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})
    a.peer_act("丙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})
    full = social.GIFT_DAY_FULL.format(n=2)
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1}) == [full]
    button = next(b for b in a.peer_card("丙")["actions"] if b["action"] == "gift")
    assert button["enabled"] is False and button["note"] == full
    a.sync(NOW + 24 * 3600)
    assert a.gift_day_left() == 2


def test_card_has_only_taunt_gift_and_mingtie_of_the_old_second_layer(content):
    """拿掉抱拳、請教、敬酒、結伴同行（Joy 2026-10-19；抱拳換成遞名帖）。"""
    a = _player(content, "甲")
    _player(content, "乙")
    card = a.peer_card("乙")
    acts = {(b["action"], b["arg"]) for b in card["actions"]}
    assert ("greet", "taunt") in acts and ("mingtie", "send") in acts
    assert not {("greet", "bow"), ("greet", "ask"), ("greet", "toast")} & acts
    assert not any(b["action"] == "travel" for b in card["actions"])
    assert a.peer_act("乙", "greet", {"arg": "bow"}) == ["（沒有這種禮數。）"]
    assert a.peer_act("乙", "travel") == ["（沒有這個動作。）"]


def test_a_taunt_can_carry_a_line_and_both_sides_remember_it(content):
    a = _player(content, "甲")
    _player(content, "乙")
    taunt = next(b for b in a.peer_card("乙")["actions"] if b["arg"] == "taunt")
    assert taunt["text"] == content.config.mingtie.taunt_max
    assert a.peer_act("乙", "greet", {"arg": "taunt", "text": "你這三腳貓也敢來"}) == ["你向乙斜眼打量，出言挑釁：「你這三腳貓也敢來」"]
    assert a.peer_act("乙", "greet", {"arg": "taunt"}) == ["（乙還沒回應。）"]
    assert not any(o.id.startswith("invite:") for o in a.options())  # 挑釁不用收回
    _done(a)
    b = _as(content, a.world, "乙", NOW + 10)
    [call] = _calls(b)
    assert call["text"] == "甲斜眼打量你，出言挑釁：「你這三腳貓也敢來」"
    assert [o["label"] for o in call["options"]] == ["冷眼以對", "出言回敬"]
    assert b.choose(call["options"][1]["id"])[-1] == "你出言回敬。"
    _done(b)
    a = _as(content, a.world, "甲", NOW + 20)
    assert "你向乙斜眼打量，出言挑釁：「你這三腳貓也敢來」，乙出言回敬。" in _lines(a)


def test_a_dirty_or_too_long_taunt_is_not_sent(content):
    from tianxia import speech

    content.banned_words = ["王八蛋"]
    a = _player(content, "甲")
    _player(content, "乙")
    assert a.peer_act("乙", "greet", {"arg": "taunt", "text": "你這王 八．蛋"}) == [speech.BLOCKED]
    assert a.peer_act("乙", "greet", {"arg": "taunt", "text": "字" * 21}) == [speech.TOO_LONG.format(n=20)]
    assert a.peer_act("乙", "greet", {"arg": "taunt", "text": "你算哪根蔥", "verdict": "bad"}) == [speech.BLOCKED]
    assert a.state.world.invites == []


def test_you_can_stop_reading_his_taunt_lines(content):
    a = _player(content, "甲")
    _player(content, "乙")
    a.peer_act("乙", "greet", {"arg": "taunt", "text": "改天讓你見識見識"})
    _done(a)
    b = _as(content, a.world, "乙", NOW + 10)
    mute = next(x for x in b.peer_card("甲")["actions"] if x["arg"] == "mute")
    assert mute["label"] == "不再接他的挑釁話"
    b.peer_act("甲", "greet", {"arg": "mute"})
    assert _calls(b)[0]["text"] == "甲斜眼打量你，出言挑釁。"
    assert any(x["arg"] == "unmute" for x in b.peer_card("甲")["actions"])


def test_an_unanswered_greeting_runs_out(content):
    a = _player(content, "甲")
    _player(content, "乙")
    a.peer_act("乙", "greet", {"arg": "taunt"})
    _done(a)
    later = NOW + content.config.invite_ttl_seconds / content.config.time_scale + 1
    b = _as(content, a.world, "乙", later)
    assert _calls(b) == [] and not any(o.id.startswith("invite:") for o in b.options())


def _walk_to_lake(game):
    return game.choose("move:lake")


def test_a_follower_who_cannot_keep_up_is_left_behind(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    from tianxia.state import Tagalong

    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    b.state.player.stamina = 0
    _done(b)
    a.set_move_mode("dash")
    msgs = a.choose("move:lake:dash")
    assert "乙沒能跟上，你們就此分開。" in msgs
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.tagalong is None and stored.player.journey is None


def test_the_leader_halting_halts_the_follower_and_parting_frees_him(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    from tianxia.state import Tagalong

    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    _done(b)
    a.state.world.flags.add("cave_open")
    a.state.player.surveyed |= {"lake", "cave"}  # 乙不認得寶洞也跟得去：路是帶頭的人認得的
    assert a.travel("cave")[-1] == "乙跟著你。"
    a.choose("act:halt")
    _done(a)
    b = _as(content, a.world, "乙", NOW + 1)
    assert b.state.player.journey.stop_at == 0 == a.state.player.journey.stop_at
    assert b.choose("act:part")[-1] == "你與甲分道揚鑣。"
    assert b.state.player.tagalong is None and any(o.id.startswith("road:back") for o in b.options())
    _done(b)
    assert a.party_view() is None


@pytest.mark.parametrize("kind, arg, want", [
    ("greet", "taunt", {"cold", "retort", None}),
    ("mingtie", "send", {"yes", "no", None}),
])
def test_bots_answer_at_a_human_pace(content, kind, arg, want):
    """假人回打招呼、結伴邀請：剛收到不回；過了一陣子，各種假人（seed 不同）有回有拒有不理（None）。"""
    from tianxia import bot_policy

    a = _player(content, "甲")
    b = _player(content, "乙", bot=True)
    for g in (a, b):
        g.make_mingtie([[0, 0, 10, 10, 50, 50]], [], "")
        _done(g)
    a.peer_act("乙", kind, {"arg": arg})
    _done(a)
    b = _as(content, a.world, "乙", NOW + 1)
    assert bot_policy.answer_call(b, b.state.player.bot) is None
    later = NOW + (bot_policy.REPLY_MIN_SECONDS + bot_policy.REPLY_SPREAD_SECONDS + 1) * content.config.time_scale
    b = _as(content, a.world, "乙", later)
    seen = set()
    for seed in range(60):
        b.state.player.bot.seed = seed
        option = bot_policy.answer_call(b, b.state.player.bot)
        seen.add(option.split(":")[1] if option else None)
    assert seen == want
    b.state.player.bot.seed = next(n for n in range(60) if (lambda o: o and o.split(":")[1] in ("cold", "yes"))(
        bot_policy.answer_call(b, b.state.player.bot.model_copy(update={"seed": n}))))
    bot_policy.take_turn(b, b.state.player.bot, random.Random(0))  # 照選單那一顆按下去
    assert _calls(b) == []


def test_a_bot_waiting_for_its_leader_stays_put(content):
    from tianxia import bot_policy
    from tianxia.state import Tagalong

    _player(content, "甲")
    b = _player(content, "乙", bot=True)
    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    before = b.state.player.location
    for _ in range(5):
        bot_policy.take_turn(b, b.state.player.bot, random.Random(0))
    assert b.state.player.location == before and b.state.player.journey is None


# ── 原 test_fb103_call_note.py（整檔搬進來） ──
# FB-103（QA 7cc1fd7，2026-10-08）：只有一位人物的地點，行動列交友那一格放「求見某某」，底下那一行（Game.action_notes）要跟格子說的是同一回事。
#
# 以前談滿的情形已經對了（day-scale 審查 I1）；閉門不見（挑戰本人打贏之後）時格子寫「求見／閉門不見」、那一行卻寫「和董卓談話，聊得投機情誼會漲」；
# 名望不夠時格子是「求見董卓」（選單上寫「名望還差 N」），那一行寫「名望不夠，董卓會打發你」。現在那一行照選項括號裡的話寫：
# 閉門不見寫整句「剛吃了敗仗，閉門不見」，名望不夠寫「名望還差 N」與會被打發，談滿照舊，見得到照舊。
#
# 用真實內容（週末設定）：官軍站在黃巾別部營寨，那裡只站著波才。句子待 joy 潤：這裡比的是選項括號裡的話有沒有出現在那一行，不鎖死字句。

CALL = "call:bocai"


@pytest.fixture
def guan(on, world):
    on.config.precise_actions = False  # 一類一顆之前的交友、求見（新規則在 tests/test_precise_actions.py，設計 8.4）
    game = Game.new(on, "官甲", rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "huangjin_camp"
    p.tutorial_step = len(on.tutorial.steps)
    game.now = 1000.0
    return game


def _cell_and_note(game):
    option = next(o for o in game.options() if o.id == CALL)
    return option, game.action_notes([o.id for o in game.options()])[CALL]


def _detail(label):
    return re.fullmatch(r"求見.+?（(.*)）", label).group(1)


def test_a_snubbed_audience_says_the_door_is_shut(guan):
    guan.state.player.stats["fame"] = 100
    guan.state.player.snubbed_until["bocai"] = guan.now + 3600
    option, note = _cell_and_note(guan)
    assert not option.enabled and _detail(option.label) == SNUB_NOTE
    assert note == SNUB_NOTE and "談話" not in note  # 跟格子同一句（格子只放得下最後一小句「閉門不見」）


def test_a_fame_short_audience_names_the_gap_like_the_menu(guan):
    guan.state.player.stats["fame"] = 0
    option, note = _cell_and_note(guan)
    gap = _detail(option.label)
    assert option.enabled and gap.startswith("名望還差 ")
    assert note.startswith(gap) and "打發" in note and "不花體力" in note and "談話" not in note


def test_the_talked_out_and_the_open_audience_keep_their_lines(guan, on):
    guan.state.player.stats["fame"] = 100
    option, note = _cell_and_note(guan)
    assert option.enabled and note == howto.call_line("波才", True)
    guan.state.player.talks_today["bocai"] = [rules.game_day(on, guan.state.world), on.config.talk_turns_per_day]
    option, note = _cell_and_note(guan)
    assert not option.enabled and note == _detail(option.label) == guan._talked_out_note()  # noqa: SLF001


@pytest.mark.parametrize("fame, snubbed, talked", [(100, True, False), (0, False, False), (100, False, True), (0, True, False)])
def test_whenever_the_cell_gives_a_reason_the_line_repeats_it(guan, on, fame, snubbed, talked):
    """格子（選項）括號裡寫了原因（不是體力），那一行就從那一句開頭：兩邊說的永遠是同一件事。"""
    p = guan.state.player
    p.stats["fame"] = fame
    if snubbed:
        p.snubbed_until["bocai"] = guan.now + 3600
    if talked:
        p.talks_today["bocai"] = [rules.game_day(on, guan.state.world), on.config.talk_turns_per_day]
    option, note = _cell_and_note(guan)
    reason = _detail(option.label)
    assert not reason.startswith("體力") and note.startswith(reason)


# ── 原 test_fb_batch_b.py ──

# ── FB-116：玩家互動的漏洞 → 贈物同一個人連送併成一則、同一對人每個遊戲日有上限；論武同一對人每個遊戲日有上限 ──


def test_fb116_gifts_fold_into_one_entry_and_stop_at_the_daily_cap(content):
    from test_social import NOW, _as, _done, _player

    from tianxia import materials

    cap = content.config.gift_per_pair_day
    assert cap == 5
    a = _player(content, "甲")
    _player(content, "乙")
    a.state.player.materials = {"gang_1": 50}
    one = f"你把{materials.item_text(content, 'gang_1', 1)}送給了乙。"
    for _ in range(cap):
        assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})[0] == one
    full = social.pair_full(a, "gift")
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1}) == [full]  # 第六次：照樣不收、不寫紀錄
    assert a.state.player.materials["gang_1"] == 50 - cap
    gifts = [b for b in a.peer_card("乙")["actions"] if b["action"] == "gift"]
    assert gifts and not any(b["enabled"] for b in gifts) and all(b["note"] == full for b in gifts)
    sent = [e for e in a.state.journal if e.title == "贈物・乙"]
    assert len(sent) == 1 and len(sent[0].lines) == cap
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    got = [e for e in b.state.journal if e.title == "收禮・甲"]
    assert len(got) == 1 and len(got[0].lines) == cap  # 連送五次：收禮併成一則
    assert b.peer_act("甲", "gift", {"arg": "material", "choice": "gang_1", "amount": 1}) == [full]  # 同一對人：反過來送也算在同一本帳
    key = b._spar_pair("甲")
    b.state.world.gift_tally[key][0] -= 1  # 帳記的是昨天：今天重算
    assert b.peer_act("甲", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})[0].startswith("你把")


def test_fb116_gifts_from_someone_else_in_between_start_a_new_entry(content):
    from test_social import NOW, _as, _done, _player

    give = {"arg": "material", "choice": "gang_1", "amount": 1}
    a = _player(content, "甲")
    c = _player(content, "丙")
    _player(content, "乙")
    a.state.player.materials = {"gang_1": 5}
    c.state.player.materials = {"gang_1": 5}
    _done(c)
    a.peer_act("乙", "gift", give)
    _done(a)
    c = _as(content, a.world, "丙", NOW + 1)
    c.peer_act("乙", "gift", give)
    _done(c)
    a = _as(content, a.world, "甲", NOW + 2)
    a.peer_act("乙", "gift", give)
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    assert [e.title for e in b.state.journal[:3]] == ["收禮・甲", "收禮・丙", "收禮・甲"]  # 只併「連著」同一個人送的


def test_fb116_a_pair_discusses_at_most_twice_a_game_day(pair):
    from test_discuss import _accept, _do, _invite

    content, world = pair
    cap = content.config.discuss_per_pair_day
    assert cap == 2
    _invite(content, world, "insight:feng")
    assert "烈焰境" in _accept(content, world, "insight:huo")[0]  # 武學重構（10/21）：論武只合意境
    made = world.lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    _invite(content, world, f"insight:{made.id}")
    # 第二張邀請還在等的時候，這一對人今天的帳被別處用滿了（另一個分頁、假人）：答應那一下重驗，不開爐
    key = "|".join(sorted(("甲", "乙")))
    world.mutate_season(lambda s: s.discuss_tally.update({key: [game_day(content, s), cap]}))
    full = _do(content, world, "乙", lambda g: social.pair_full(g, "discuss"))[0]
    assert _accept(content, world, "insight:huo", ("風火境", "風助火勢。")) == [full]
    assert world.lookup_insight_recipe(fusion.merge_key(made.id, "huo")) is None
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", {"arg": "invite:insight:feng"}))
    assert msgs == [full]  # 卡上那一顆也按不下去


# ── 原 test_fb_batch_c.py ──

needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


# ── FB-220：贈物送滿之後，卡上灰掉的「贈銀兩」「贈回體丹」被右邊那句原因擠成一字一行（鈕高 103px）──
# 名字包一格不折行（.pa-name）；說明放得下就跟名字並排，放不下換到名字底下一行、照空白與標點折（375 寬實機：103px → 75px，
# 同一張卡上的「邀他結伴同行」63px → 75px，名字不再被折成兩行；「身上 50 兩」這種短的照舊並排，48px）。原因那一句字不改。


@needs_node
def test_fb220_a_full_gift_button_keeps_its_name_on_one_line(content):
    import json

    from test_prologue_web import run
    from test_shop2_web import _css, _rule
    from test_social import _player

    from tianxia import social

    cap = content.config.gift_per_pair_day
    a = _player(content, "甲")
    b = _player(content, "乙")
    a.state.player.materials = {"gang_1": 50}
    for _ in range(cap):
        a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 1})
    card = social.card(a, b)
    full = social.pair_full(a, "gift")
    assert [x["note"] for x in card["actions"] if x["action"] == "gift"] == [full]  # 原因那一句字不改
    out = run(server.main_view(a), "H.S.peer = { name: '乙', card: CARD }; return H.peerHtml();".replace("CARD", json.dumps(card, ensure_ascii=False)))
    assert f'disabled><span class="pa-name">贈素材</span><small>{full}</small></button>' in out
    css = _css()
    assert "white-space: nowrap" in _rule(css, ".peer-acts .btn .pa-name") and "flex: none" in _rule(css, ".peer-acts .btn .pa-name")
    assert "flex-wrap: wrap" in _rule(css, ".peer-acts .btn")  # 說明放不下就換到名字底下一行
    note = _rule(css, ".peer-acts .btn small")
    assert "min-width: 0" in note and "word-break: keep-all" in note and "overflow-wrap: anywhere" in note  # 照空白、標點折，太長才硬折


@needs_node
def test_fb220_every_card_button_wraps_its_name(content):
    """卡上每一顆鈕（論武出哪一樣收成下拉清單那一顆也是）名字都包一格，沒有說明的照樣包。"""
    import json

    from test_prologue_web import run
    from test_social import _player

    actions = [
        {"action": "greet", "label": "抱拳", "enabled": True},
        {"action": "spar", "label": "切磋", "enabled": True, "note": "體力 6・勝算 五五波"},
        {"action": "discuss", "label": "出流雲劍", "group": "論武", "pick": "流雲劍", "enabled": True},
        {"action": "discuss", "label": "出風", "group": "論武", "pick": "風", "enabled": True},
    ]
    card = {"name": "乙", "affiliation": "散人", "level": 1, "record": "", "arts": [], "actions": actions}
    script = "H.S.peer = { name: '乙', card: CARD }; return H.peerHtml();".replace("CARD", json.dumps(card, ensure_ascii=False))
    out = run(server.main_view(_player(content, "甲")), script)
    assert '<span class="pa-name">抱拳</span></button>' in out and '<span class="pa-name">切磋</span><small>體力 6・勝算 五五波</small>' in out
    assert 'data-act="peer-pick"><span class="pa-name">論武</span></button>' in out
