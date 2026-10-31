"""酒肆（tianxia/tavern.py；企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」）第一批：進門、聽消息、查人、交情、素材、題壁、請酒、
藏行跡、反查、風聲。正式內容、週末設定；宛城、潁川郡帶「酒肆」標籤，黃巾大營沒有。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import tavern, tavern_ask
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

NOW = 16 * 3600 + 3600


def _content():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    return c


def _game(name="沈浪", at="wan_city", silver=500, world=None, content=None, faction=None):
    c = content or _content()
    game = Game.new(c, name, rng=random.Random(0), world=world or open_world())
    game.client = None
    p = game.state.player
    p.location, p.faction = at, faction
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    game.now = NOW
    p.seen_real = NOW
    CharacterStore(game.world.db).save(game.state)
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def test_only_towns_with_a_tavern_have_one():
    assert "act:tavern" in _ids(_game())
    assert "act:tavern" in _ids(_game(at="yingchuan"))
    assert "act:tavern" not in _ids(_game(at="runan_academy"))  # 汝南學宮是城鎮，沒有酒肆
    assert "act:tavern" not in _ids(_game(at="huangjin_camp"))


def test_entering_opens_the_tavern_page_and_blocks_travel():
    game = _game()
    msgs = game.choose("act:tavern")
    assert msgs and "宛城・酒肆" in msgs[0]
    ids = _ids(game)
    assert tavern.BACK_ID in ids and tavern.NEWS_ID in ids
    view = game.shop_view()
    assert view["shop"] == "tavern" and view["sign"] == "宛城・酒肆" and view["line"]
    assert len(view["chatter"]) == 2 and all(row["who"] and row["said"] for row in view["chatter"])
    assert "act:explore" not in ids  # 坐在酒肆裡：選單卡在酒肆那一串
    game.choose(tavern.BACK_ID)
    assert not game.state.player.picking_tavern
    assert "act:explore" in _ids(game)


def test_prices_follow_the_season_length():
    game = _game()
    full = game.content.config.tavern.news_price
    assert game._tavern_price(full) <= full
    assert game._tavern_price(0) == 0


@pytest.mark.smoke
def test_news_charges_once_and_does_not_repeat():
    game = _game()
    w = game.state.world
    from tianxia.rules import add_rumor
    add_rumor(game.state, "皇甫嵩移往長社，黃巾聲勢稍退。", "changshe", content=game.content, layer="world")
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    msgs = game.tavern_do("news")
    price = game._tavern_price(game.content.config.tavern.news_price)
    assert game.state.player.stats["silver"] == before - price
    assert any("皇甫嵩移往長社" in m for m in msgs)
    assert game.state.journal[0].title == "宛城・酒肆"
    assert game.state.player.tavern_notes[-1].kind == "news"
    assert w.rumors  # 傳聞還在季上
    again = game.tavern_do("news")
    assert not any("皇甫嵩移往長社" in m for m in again)  # 聽過的不再說


def test_seeking_a_famous_player_names_the_place_and_whispers_to_him():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    other = _game("李尋歡", at="wan_city", world=world, content=c)
    other.state.player.stats["fame"] = 10_000  # 名望頂段
    other.state.player.seen_real = NOW
    CharacterStore(world.db).save(other.state)
    me.choose("act:tavern")
    msgs = me.tavern_do("seek", "李尋歡")
    assert any("宛城" in m for m in msgs)
    assert "李尋歡" in me.state.player.tavern_known
    me._save_season()
    other.sync(NOW + 10)
    assert other.state.player.whispers and other.state.player.whispers[-1].kind == "seek"
    assert any(e.title == tavern.WHISPER_TITLE for e in other.state.journal)


def test_an_unknown_name_and_an_obscure_player_read_the_same_and_refund_half():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    far = _game("無名氏", at="xiaquyang", world=world, content=c)  # 默默無名、離得遠
    far.state.player.stats["fame"] = 0
    CharacterStore(world.db).save(far.state)
    me.choose("act:tavern")
    price = me._tavern_price(c.config.tavern.seek_price)
    back = int(price * c.config.tavern.refund_share)
    before = me.state.player.stats["silver"]
    a = me.tavern_do("seek", "查無此人")
    assert me.state.player.stats["silver"] == before - price + back
    b = me.tavern_do("seek", "無名氏")
    assert a[0].split("（")[0] in (tavern.NOBODY.split("（")[0], tavern.HALF_MISS.split("（")[0])
    assert b[0].split("（")[0] in (tavern.NOBODY.split("（")[0], tavern.HALF_MISS.split("（")[0])


def test_seeking_a_figure_and_a_material():
    game = _game()
    game.choose("act:tavern")
    figure = next(iter(game.content.figures.values()))
    name = game.content.characters[figure.character].name
    msgs = game.tavern_do("seek", name)
    assert msgs and name in msgs[0]
    one = next(m for m in game.content.materials.values() if m.tier == 1)
    msgs = game.tavern_do("material", one.id)
    assert msgs and one.name in msgs[0]
    three = next(m for m in game.content.materials.values() if m.tier == 3)
    msgs = game.tavern_do("material", three.id)
    assert "傳說" in msgs[0]


def test_material_answers_name_real_places_and_differ_by_material():
    """Joy 2026-10-19「酒館打聽素材消息他全部都回一樣的話」：地點的 materials 寫的是素材 id，以前拿屬性去比、一處都對不上，
    一階二階全回「傳說裡的東西」。"""
    c = _content()
    for m in c.materials.values():
        places = tavern.material_places(c, m)
        assert bool(places) == (m.tier <= 2), m.id
        assert all(m.id in c.locations[loc].materials for loc in places)
    game = _game(silver=5000)
    game.choose("act:tavern")
    answers = {}
    for m in c.materials.values():
        if m.tier > 2:
            continue
        line = game.tavern_do("material", m.id)[0]
        assert "傳說" not in line, line
        answers[m.id] = line
    assert len(set(answers.values())) == len(answers)
    assert "沉淵石" in tavern.material_lines(game.state, c, c.materials["man_1"])[0][0]


def test_wall_treat_hide_and_their_limits():
    game = _game()
    c = game.content
    game.choose("act:tavern")
    assert game.tavern_do("wall", text="") == [tavern.WALL_EMPTY]
    assert game.tavern_do("wall", text="字" * (c.config.tavern.wall_chars + 1))[0].startswith("一句最多")
    game.tavern_do("wall", text="南市一壺濁酒，換得潁川三夜風。")
    view = game.shop_view()
    assert view["walls"][0]["text"] == "南市一壺濁酒，換得潁川三夜風。" and view["walls"][0]["who"] == "沈浪"
    fame = game.state.player.stats.get("fame", 0)
    game.tavern_do("treat")
    assert game.state.player.stats.get("fame", 0) == fame + c.config.tavern.treat_fame
    assert game.shop_view()["treat"]
    assert game.tavern_do("treat") == [tavern.TREAT_FULL]
    game.tavern_do("hide")
    assert game.state.player.hidden_until > game.state.world.time
    assert game.tavern_do("hide")[0].startswith("已經打點過了")


def test_hiding_makes_you_harder_to_find():
    world = open_world()
    c = _content()
    me = _game(world=world, content=c)
    other = _game("李尋歡", at="wan_city", world=world, content=c)
    base = tavern.person_reach(me.state, c, other.state)
    other.state.player.hidden_until = other.state.world.time + 1000
    assert tavern.person_reach(me.state, c, other.state) == base - c.config.tavern.hide_reach


def test_trace_with_nothing_to_trace_is_free():
    game = _game()
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    assert game.tavern_do("trace") == [tavern.TRACE_NONE]
    assert game.state.player.stats["silver"] == before


def test_cannot_act_outside_the_tavern():
    game = _game()
    before = game.state.player.stats["silver"]
    game.tavern_do("news")
    assert game.state.player.stats["silver"] == before


def test_a_bot_drops_in_asks_one_thing_and_leaves():
    from tianxia import bot_policy
    game = _game(silver=500)
    game.state.player.newbie_done.add("tavern")  # 新手目標「在酒肆打聽一件事」的 20 兩另外驗（tests/test_training.py）
    rng = random.Random(1)
    old = bot_policy.TAVERN_CHANCE
    bot_policy.TAVERN_CHANCE = 1.0
    try:
        msgs = bot_policy._tavern(game, rng)
    finally:
        bot_policy.TAVERN_CHANCE = old
    assert msgs
    assert not game.state.player.picking_tavern
    assert game.state.player.stats["silver"] < 500


def test_a_bot_short_of_silver_stays_out():
    from tianxia import bot_policy
    game = _game(silver=5)
    old = bot_policy.TAVERN_CHANCE
    bot_policy.TAVERN_CHANCE = 1.0
    try:
        assert bot_policy._tavern(game, random.Random(1)) is None
    finally:
        bot_policy.TAVERN_CHANCE = old


def _feud(world, c, *, target_fame=10_000, target_at="wan_city"):
    me = _game(world=world, content=c, faction="guanjun")
    them = _game("李尋歡", at=target_at, world=world, content=c, faction="huangjin")
    them.state.player.stats["fame"] = target_fame
    for g in (me, them):
        g.state.player.joined_at = -10 ** 9
    CharacterStore(world.db).save(them.state)
    CharacterStore(world.db).save(me.state)
    return me, them


def test_hiring_needs_a_name_you_found():
    world = open_world()
    c = _content()
    me, them = _feud(world, c)
    me.choose("act:tavern")
    assert me.tavern_do("hit", "李尋歡", "0") == [tavern.HIT_NEED_KNOWN]
    assert me.tavern_do("hit", "查無此人", "0") == [tavern.HIT_NEED_KNOWN]  # 跟沒查過的人同一句
    me.tavern_do("seek", "李尋歡")
    before = me.state.player.stats["silver"]
    msgs = me.tavern_do("hit", "李尋歡", "0:hush")
    price = me._tavern_price(c.config.tavern.hit_prices[0] + c.config.tavern.hush_price)
    assert me.state.player.stats["silver"] == before - price, msgs
    hit = me.state.world.tavern_hits[-1]
    assert hit.target == "李尋歡" and hit.hushed and not hit.done
    assert me.tavern_do("hit", "李尋歡", "1")[0].startswith("酒家搖頭：「已經有人出了價")
    assert me.shop_view()["hits"]["mine"]


def test_the_killer_waits_in_town_and_strikes_outside():
    world = open_world()
    c = _content()
    me, them = _feud(world, c)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "2")
    me._save_season()
    them.sync(NOW + 5)
    assert them._tavern_hit_check() == []  # 宛城是城鎮：殺手等著
    out = next(lid for lid in c.locations if not tavern.town(c, lid) and tavern.near(c, "wan_city", lid) >= 1
               and not c.locations[lid].tags.count("序章"))
    them.state.player.location = out
    msgs = them._tavern_hit_check()
    hit = them.state.world.tavern_hits[-1]
    assert hit.done and hit.outcome in ("殺手贏", "對方贏", "對方贏・供出", "平手")
    assert any(e.title == tavern.HIT_STRUCK for e in them.state.journal) and msgs
    them._save_season()
    me.sync(NOW + 20)
    assert hit.outcome and any(e.title == tavern.HIT_TITLE for e in me.state.journal)


def test_an_unfound_target_refunds_half_when_the_order_lapses():
    world = open_world()
    c = _content()
    me, them = _feud(world, c)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "0")
    hit = me.state.world.tavern_hits[-1]
    before = me.state.player.stats["silver"]
    me.now = hit.until_real + 1
    me._deliver_hits()
    assert hit.done and hit.outcome == "過期" and hit.refunded
    assert me.state.player.stats["silver"] == before + int(hit.price * c.config.tavern.refund_share)


def test_a_guard_once_until_it_lapses():
    game = _game()
    game.choose("act:tavern")
    game.tavern_do("guard")
    assert game.state.player.tavern_guard_until > game.now
    assert game.tavern_do("guard")[0].startswith("保鏢還跟著")


def test_asking_the_keeper_three_steps():
    game = _game()
    c = game.content
    game.choose("act:tavern")
    req = game.tavern_ask_request("最近哪裡最亂？")
    assert isinstance(req, tavern.AskRequest) and req.facts and not req.secret
    before = game.state.player.stats["silver"]
    msgs = game.tavern_ask(req.question, "客官，這兩日南陽一帶最不太平，聽說黃巾又有動靜。", request=req)
    assert game.state.player.stats["silver"] == before - game._tavern_price(c.config.tavern.ask_price)
    assert msgs[1].startswith("酒家：「客官")
    assert game.state.player.tavern_notes[-1].kind == "ask"


def test_the_keeper_does_not_answer_secrets_and_is_free_when_silent():
    game = _game()
    c = game.content
    game.choose("act:tavern")
    req = game.tavern_ask_request("神器配方怎麼湊？")
    assert req.secret and tavern.ask_write(object(), req) is None  # 秘密不叫模型
    before = game.state.player.stats["silver"]
    assert game.tavern_ask(req.question, None, request=req)[1] == tavern.ASK_SECRET
    assert game.state.player.stats["silver"] == before - game._tavern_price(c.config.tavern.ask_price // 2)
    before = game.state.player.stats["silver"]
    req = game.tavern_ask_request("曹操好不好說話？")
    assert game.tavern_ask(req.question, None, request=req) == [tavern.ASK_BUSY]
    assert game.state.player.stats["silver"] == before


def test_a_reply_with_made_up_numbers_is_thrown_away():
    req = tavern.AskRequest(name="甲", place="wan_city", sign="宛城・酒肆", question="多少人？", facts=("宛城一帶採得到屬剛的素材。",))
    assert tavern.ask_clean("客官，城外聚了三千人。", req) == "客官，城外聚了三千人。"
    assert tavern.ask_clean("客官，城外聚了3000人。", req) is None
    assert tavern.ask_clean("字" * 200, req) is None


def test_neighbours_chatter_is_written_once_per_while_and_falls_back():
    """酒客閒談：開著的酒肆該換一段時開單（A）、寫好的記進這一季（C），這一陣子都用它；寫不出來記空的、照固定句、不再開單。"""
    game = _game()
    c = game.content
    game.choose("act:tavern")
    req = game.tavern_chatter_request()
    assert isinstance(req, tavern.ChatterRequest) and req.place == "wan_city"
    lines = tavern.chatter_clean(["靠窗的腳夫：「今兒這酒倒是沒摻水。」", "老卒:城外又不太平了", "說了一大堆" * 10], req)
    assert lines == ["靠窗的腳夫：「今兒這酒倒是沒摻水。」", "老卒：「城外又不太平了」"]
    assert game.apply_tavern_chatter(req, lines)
    assert game.tavern_chatter_request() is None  # 這一陣子不再寫
    assert game.shop_view()["chatter"][0] == {"who": "靠窗的腳夫", "said": "「今兒這酒倒是沒摻水。」"}
    assert not game.apply_tavern_chatter(req, ["甲：「乙」", "丙：「丁」"])  # 別人先寫好了：不蓋
    game.state.world.time += c.config.tavern.chatter_hours * 3600
    req = game.tavern_chatter_request()
    assert req is not None and not game.apply_tavern_chatter(req, [])  # 寫不出來：記空的，照固定句
    assert game.tavern_chatter_request() is None
    assert len(game.shop_view()["chatter"]) == 2


def test_chatter_lines_with_made_up_numbers_or_one_line_are_dropped():
    req = tavern.ChatterRequest(place="wan_city", sign="宛城・酒肆", asked_at=0.0, facts=())
    assert tavern.chatter_clean(["腳夫：「城外聚了3000人」", "老卒：「唉」"], req) == []  # 剩一句：整段不用
    assert tavern.chatter_write(None, req) == []


def test_the_server_writes_the_chatter_outside_the_lock(monkeypatch):
    import server
    from tianxia.characters import open_characters

    content = server.CONTENT
    game = Game.new(content, "閒客")
    game.world.open_season(content, 0.0)
    game.client = None
    p = game.state.player
    p.tutorial_step = len(content.tutorial.steps)
    p.location = "wan_city"
    game.now = 0.0
    game.sync(0.0)
    game.choose("act:tavern")
    open_characters().save(game.state)
    game.client = object()  # 只要「叫得到模型」：B 段換成下面的 write
    seen = []

    def write(client, req):
        seen.append(open_world().db.writing())
        return ["靠窗的腳夫：「酒錢又漲了。」", "喝悶酒的老卒：「仗打不完囉。」"]

    monkeypatch.setattr(tavern, "chatter_write", write)
    monkeypatch.setattr(server, "within_budget", lambda client, budget: client)
    assert server.chatter_once(game)
    assert seen == [False]  # 模型在鎖外
    assert game.shop_view()["chatter"][1]["who"] == "喝悶酒的老卒"
    assert not server.chatter_once(game)  # 這一陣子不再寫


def test_asking_the_keeper_to_keep_watch_sends_word_later():
    """託酒家留意：查不清楚時多付一半，那個人打聽得到確切地點時（託的那一間算）捎信進江湖紀錄；問清楚了不收、到期捎一句沒消息。"""
    world = open_world()
    c = _content()
    far = _game("無名客", at="zhuo_commandery", world=world, content=c)
    game = _game(world=world, content=c)
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    msgs = game._tavern_run("seek", target="無名客", text="watch")
    watch_price = game._tavern_price(round(c.config.tavern.seek_price * c.config.tavern.watch_share))
    assert tavern.WATCH_PLACED.format(name="無名客") in msgs
    assert len(game.state.player.tavern_watches) == 1
    assert before - game.state.player.stats["silver"] >= watch_price
    assert tavern.WATCH_SAME.format(name="無名客") in game._tavern_run("seek", target="無名客", text="watch")
    game._deliver_watches()
    assert len(game.state.player.tavern_watches) == 1  # 還在遠方：沒消息
    far.state.player.location = "wan_city"  # 走進宛城、又有了點名氣：從這一間打聽得到確切地點
    far.state.player.stats["fame"] = 100000
    CharacterStore(world.db).save(far.state)
    game._deliver_watches()
    assert game.state.player.tavern_watches == []
    entry = game.state.journal[0]
    assert entry.title == tavern.WATCH_TITLE
    assert tavern.WATCH_FOUND.format(name="無名客", place="宛城") in entry.lines
    assert "無名客" in game.state.player.tavern_known
    assert tavern.WATCH_CLEAR in game._tavern_run("seek", target="曹操", text="watch")  # 人物一問就清楚：不託、不多收
    assert game.state.player.tavern_watches == []
    game._tavern_run("seek", target="查無此人", text="watch")  # 查無此人也照收，到期捎一句
    assert len(game.state.player.tavern_watches) == 1
    game.now += c.config.tavern.watch_hours * 3600 + 1
    game._deliver_watches()
    assert tavern.WATCH_LAPSED.format(name="查無此人") in game.state.journal[0].lines  # 江湖紀錄新的在前


def test_leaving_the_tavern_keeps_the_save_readable():
    """收起酒肆以前把 shop_hold 寫成 None，存下的角色整個讀不進來（characters.all 跳過、載入時搬去備份）：現在寫空字串，
    那一版存下的 None 也照讀。"""
    from tianxia.state import GameState

    game = _game()
    tavern.close(game.state)
    assert game.state.player.shop_hold == ""
    data = game.state.model_dump(mode="json")
    data["player"]["shop_hold"] = None
    assert GameState.model_validate(data).player.shop_hold == ""


def _outside(c):
    return next(lid for lid in c.locations if not tavern.town(c, lid) and tavern.near(c, "wan_city", lid) >= 1
                and not c.locations[lid].tags.count("序章"))


def _rig(monkeypatch, tier):
    """殺手那一場的結果定死（tier 是本人這一邊的結果）；回傳記下殺手威力的清單。"""
    from tianxia import encounter

    seen = []

    def fake(mine, killer, rng, *a, **k):
        seen.append(killer / mine)
        return encounter.EncounterResult(tier=tier, margin=0.0, our_power=mine, difficulty=killer)

    monkeypatch.setattr("tianxia.engine.encounter.resolve_encounter", fake)
    monkeypatch.setattr(tavern, "find_chance", lambda c, reach: 1.0)
    return seen


def test_same_side_can_hire_and_a_kill_leaves_one_hp_and_a_shield(monkeypatch):
    """企劃者 2026-10-27：同陣營也能雇；得手了對方氣血只剩 1（不是扣上限的一成半），銀兩照丟，之後 hit_shield_hours 殺手找不上。"""
    world = open_world()
    c = _content()
    me = _game(world=world, content=c, faction="guanjun")
    them = _game("李尋歡", world=world, content=c, faction="guanjun")
    for g in (me, them):
        g.state.player.joined_at = -10 ** 9
        CharacterStore(world.db).save(g.state)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    assert me._tavern_hit_problem("李尋歡", 0)[0] is None
    me.tavern_do("hit", "李尋歡", "1")
    me._save_season()
    _rig(monkeypatch, "落敗")
    them.sync(NOW + 5)
    them.state.player.location = _outside(c)
    purse = them.state.player.stats["silver"]
    msgs = them._tavern_hit_check()
    assert msgs and them.state.player.member.neili == 1.0
    assert them.state.player.stats["silver"] < purse
    assert them.state.player.tavern_shield_until == them.now + c.config.tavern.hit_shield_hours * 3600
    them.state.world.raided.clear()
    them.state.world.tavern_hits[-1].done = False  # 再來一次：護身期間殺手找不上
    assert them._tavern_hit_check() == []


def test_a_target_who_logs_off_outside_town_is_found_while_away(monkeypatch):
    """下線那一段：站在城外下線、單子期限跟這一段重疊，回來同步時擲一次，紀錄裡有遭殺手找上；城鎮裡下線照舊安全。"""
    world = open_world()
    c = _content()
    me, them = _feud(world, c)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "0")
    me._save_season()
    _rig(monkeypatch, "落敗")
    them.sync(NOW + 5)  # 宛城：城裡下線
    them.sync(NOW + 3600)
    assert not them.state.world.tavern_hits[-1].done
    them.state.player.location = _outside(c)
    them.sync(NOW + 3700)  # 才隔不到 hit_offline_minutes：不算下線
    assert not them.state.world.tavern_hits[-1].done
    them.sync(NOW + 3700 + c.config.tavern.hit_offline_minutes * 60 + 1)
    hit = them.state.world.tavern_hits[-1]
    assert hit.done and hit.outcome == "殺手贏"
    struck = [e for e in them.state.journal if e.title == tavern.HIT_STRUCK]
    assert struck and any("下線歇在" in line for line in struck[-1].lines)
    assert them.state.player.member.neili == 1.0


def test_an_order_that_lapsed_while_away_still_gets_its_roll(monkeypatch):
    world = open_world()
    c = _content()
    me, them = _feud(world, c)
    them.state.player.location = _outside(c)
    CharacterStore(world.db).save(them.state)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    me.tavern_do("hit", "李尋歡", "0")
    me._save_season()
    _rig(monkeypatch, "落敗")
    them.state.last_real = NOW + 1
    them.sync(NOW + c.config.tavern.hit_hours * 3600 + 3600)  # 整張單子都在下線那一段裡過期
    hit = them.state.world.tavern_hits[-1]
    assert hit.outcome == "殺手贏"


def test_each_miss_raises_the_next_price_and_the_killer_up_to_three(monkeypatch):
    """同一個雇主找同一個人：每失手一次（打退、平手），下一張 +50% 價錢、威力 +0.1，最多疊 3 次；得手歸零。"""
    world = open_world()
    c = _content()
    cfg = c.config.tavern
    me, them = _feud(world, c)
    me.choose("act:tavern")
    me.tavern_do("seek", "李尋歡")
    seen = _rig(monkeypatch, "僵持")
    them.state.player.location = _outside(c)
    for n in range(5):
        k = min(n, cfg.hit_fail_max)
        assert tavern.hit_streak(me.state.world, me.state.player.name, "李尋歡", cfg.hit_fail_max) == k
        before = me.state.player.stats["silver"]
        me.tavern_do("hit", "李尋歡", "0")
        hit = me.state.world.tavern_hits[-1]
        assert hit.streak == k
        assert before - me.state.player.stats["silver"] == me._tavern_price(round(cfg.hit_prices[0] * (1 + 0.5 * k)))
        me._save_season()
        them.sync(them.now + 1)
        them.state.player.location = _outside(c)
        them.state.world.raided.clear()  # 截殺那一道一小時的護身不在這裡量
        them._tavern_hit_check()
        assert len(seen) == n + 1 and abs(seen[-1] - (cfg.hit_power[0] + 0.1 * k)) < 1e-6
        them._save_season()
        me.sync(me.now + 1)
        hit = next(h for h in me.state.world.tavern_hits if h.id == hit.id)
        assert hit.outcome == "平手"
        for h in me.state.world.tavern_hits:  # 跳過同一對人 24 小時一次的限制
            h.placed_real -= cfg.hit_pair_hours * 3600 + 10
        them.state.player.tavern_shield_until = 0
        me.state.player.stats["silver"] = 500
    assert me.shop_view()["hits"]["streaks"]
    me.state.world.tavern_hits[-1].outcome = "殺手贏"
    assert tavern.hit_streak(me.state.world, me.state.player.name, "李尋歡", cfg.hit_fail_max) == 0


def test_the_keeper_finds_facts_for_whatever_you_ask():
    """問酒家照問句找事實（企劃者 2026-10-27「大大小小的東西都可以問」）：人物、地名、素材、武學、店面、玩法各自帶得出那一樣，
    什麼都沒點到時給附近城鎮與野外；改版前清單裡只有這一區的局勢與傳聞。"""
    world = open_world()
    c = _content()
    game = _game(world=world, content=c)
    them = _game("李尋歡", at="songshan_foot", world=world, content=c)
    them.state.player.stats["fame"] = 400
    CharacterStore(world.db).save(them.state)
    game.choose("act:tavern")
    cases = {
        "波才現在在哪？": ("figure", "波才"),
        "嵩山腳危險嗎？": ("place", "嵩山腳"),
        "精鐵砂哪裡採得到？": ("material", "精鐵砂"),
        "青龍刀法是什麼？": ("skill", "青龍刀法"),
        "鐵匠鋪在哪裡？": ("shop", "鐵匠鋪"),
        "體力不夠怎麼辦？": ("guide", "體力"),
        "李尋歡是誰？": ("player", "李尋歡"),
    }
    for q, (kind, word) in cases.items():
        facts, kinds = game._tavern_ask_facts(q)
        assert kind in kinds and word in facts[0], (q, facts[:3])
    facts, kinds = game._tavern_ask_facts("李尋歡是誰？")
    assert not any("嵩山腳" in f for f in facts)  # 玩家只說到大區，確切地點是「查人」的事
    facts, kinds = game._tavern_ask_facts("我該先做什麼？")
    assert kinds == () and facts[0].startswith("附近的城鎮")
    req = game.tavern_ask_request("鐵匠鋪在哪裡？")
    assert req.kinds == ("shop",) and req.facts == game._tavern_ask_facts("鐵匠鋪在哪裡？")[0]


def test_a_keeper_who_cannot_say_refunds_half_and_points_the_way():
    game = _game()
    c = game.content
    game.choose("act:tavern")
    before = game.state.player.stats["silver"]
    req = game.tavern_ask_request("精鐵砂好不好用？")
    msgs = game.tavern_ask(req.question, "客官，這事我不清楚。", request=req)
    price = game._tavern_price(c.config.tavern.ask_price)
    assert game.state.player.stats["silver"] == before - price + price // 2
    assert tavern.ASK_UNSURE.format(refund=price // 2, tip=tavern_ask.POINTERS["material"]) in msgs
    assert c.config.tavern.ask_chars == 40
