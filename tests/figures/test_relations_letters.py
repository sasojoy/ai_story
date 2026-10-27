"""大勢人物擴充第二批「人與人」（Joy 2026-10-18「做」）：關係表（relations）、倒下時的反應與復仇懸賞（figure_life.on_fall）、
書信與委託（letters）。用真實內容（content/，figure_life 預設開著）；每個測試拿自己的一份複本。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import bounties, calendar, figure_life, figures, letters, relations
from tianxia.content import ContentError, validate
from tianxia.models import RelationDef
from tianxia.state import GameState, PlayerState
from tianxia.world_state import fresh_season


@pytest.fixture
def c():
    return real_content()


def _season(content) -> GameState:
    player = PlayerState(name="甲", location=content.scenario.start_location, stats={}, stamina=0)
    return GameState(player=player, world=fresh_season(content))


def _fell(s: GameState, c, fid: str) -> list[str]:
    return figures.defeat(s, c, fid, 1000)


def test_the_relations_table_reads_both_ways(c):
    assert relations.link(c, "zhangbao", "zhangliang") == "brother"
    assert relations.link(c, "liubei", "luzhi") == relations.link(c, "luzhi", "liubei") == "mentor"
    assert relations.link(c, "fuxie", "huangfusong") == "chief"
    assert relations.link(c, "qinjie", "zhangmancheng") == "foe"
    assert relations.link(c, "tangzhou", "zhangjiao") == "foe"  # 唐周與黃巾
    assert relations.link(c, "liubei", "gongsunzan") is None  # 同門不算（只寫師生）
    assert set(relations.allies(c, "zhangbao")) == {"zhangjiao", "zhangliang"}


def test_a_brother_falls_and_the_others_grieve_and_post_a_revenge_bounty(c):
    s = _season(c)
    lines = _fell(s, c, "zhangbao")
    text = "".join(lines)
    assert "張寶倒下的消息" in text and "張梁" in text and "張角" in text
    assert figures.mood_of(s, c, "zhangliang") == "悲憤"
    assert figure_life.mood_any(s, c, "tangzhou") == "得意"
    revenge = [b for b in s.world.bounties if b.motive == "復仇"]
    assert len(revenge) == 1  # 一方最多一張
    b = revenge[0]
    assert b.faction == "huang" and b.kind == "strike" and b.figure in ("zhangjiao", "zhangliang")
    assert b.silver == round(c.config.bounties.silver["strike"] * c.config.figure_life.revenge_silver_scale)
    assert bounties.title(c, b).startswith("復仇・") and bounties.issuer(c, b) == c.characters[b.figure].name
    assert any(r.text.find("張寶") >= 0 for r in s.world.rumors)


def test_the_grief_wears_off(c):
    s = _season(c)
    _fell(s, c, "zhangbao")
    s.world.time += figures.mood_span(c, s.world) + 1
    assert figures.mood_of(s, c, "zhangliang") != "悲憤"


def test_qin_jie_gloats_and_doubles_the_bounty_when_zhang_mancheng_falls(c):
    s = _season(c)
    lines = _fell(s, c, "zhangmancheng")
    assert any("秦頡聽說張曼成倒了" in x for x in lines)
    assert figures.mood_of(s, c, "qinjie") == "得意"
    hunt = [b for b in s.world.bounties if b.motive == "追剿"]
    assert hunt and hunt[0].faction == "guan" and hunt[0].figure == "qinjie"


def test_a_non_figure_disciple_rushes_to_the_fallen_teachers_region(c):
    s = _season(c)
    _fell(s, c, "luzhi")
    assert figure_life.mood_any(s, c, "liubei") == "悲憤"
    assert figure_life.mood_any(s, c, "gongsunzan") == "悲憤"


def test_season_one_figures_do_not_rush_off(c):
    c.config.season_one = True
    s = _season(c)
    before = figures.state_of(s, c, "zhangjiao").location
    _fell(s, c, "zhangbao")
    assert figures.state_of(s, c, "zhangjiao").location == before


def test_reactions_off_means_nothing_happens(c):
    c.config.figure_life.reactions = False
    s = _season(c)
    _fell(s, c, "zhangbao")
    assert not [b for b in s.world.bounties if b.motive]


def test_handing_in_a_revenge_bounty_warms_the_poster(c):
    s = _season(c)
    _fell(s, c, "zhangbao")
    b = next(b for b in s.world.bounties if b.motive == "復仇")
    s.player.faction = "huang"
    bounties.take(s, c, b.id)
    msgs = bounties.on_win(s, c, None, b.location, b.squad)
    assert s.player.affinities.get(b.figure) == c.config.figure_life.revenge_affinity
    assert any("情誼 +" in m for m in msgs)


def _anxious(s, c, fid: str) -> None:
    figures._ensure(s, c, fid).prestige = 1  # 聲威不到開季的一半：焦慮


def test_an_anxious_friend_writes_for_help_once_a_day(c):
    s = _season(c)
    s.world.time = calendar.DAY / 2  # 中午收到：委託撐過午夜
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    msgs = letters.deliver(s, c)
    assert msgs and "秦頡" in msgs[-1]
    letter = s.player.letters[-1]
    assert letter.kind == "求援" and letter.sender == "qinjie" and letter.task is not None
    assert letter.task.motive == "委託" and letter.task.figure == "qinjie"
    assert letters.deliver(s, c) == []  # 一天最多一封
    s.world.time = (s.world.time // calendar.DAY + 1) * calendar.DAY + 1  # 換日了，委託還沒到期
    assert s.player.letters[-1].task.expires > s.world.time
    assert letters.deliver(s, c) == []  # 委託還沒辦完，他不再寫


def test_below_the_affinity_line_nobody_writes(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 39
    assert letters.deliver(s, c) == [] and s.player.letters == []


def test_finishing_a_commission_pays_and_warms(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    letters.deliver(s, c)
    t = s.player.letters[-1].task
    silver = s.player.stats.get("silver", 0)
    if t.kind == "strike":
        msgs = bounties.on_win(s, c, None, t.location, t.squad)
    elif t.kind == "scout":
        msgs = bounties.on_explore(s, c, None, t.location)
    else:
        msgs = bounties.on_arrive(s, c, None, t.end)
    assert any("託你的事辦成了" in m for m in msgs)
    assert s.player.stats["silver"] == silver + c.config.figure_life.commission_silver
    assert s.player.affinities["qinjie"] == 40 + c.config.figure_life.commission_affinity
    assert bounties.open_commissions(s, c) == []


def test_a_commission_lapses_after_its_days(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    letters.deliver(s, c)
    s.world.time = s.player.letters[-1].task.expires + 1
    msgs = letters.deliver(s, c)
    assert any("作罷" in m for m in msgs) and s.player.letters[0].lapsed


def test_declining_drops_the_commission(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    letters.deliver(s, c)
    letter = s.player.letters[-1]
    assert letters.decline(s, c, letter.id)
    assert letter.lapsed and bounties.open_commissions(s, c) == []
    assert s.player.affinities["qinjie"] == 40  # 婉拒不扣情誼


def test_hearsay_that_pleases_a_friend_brings_a_congratulation(c):
    s = _season(c)
    s.player.location = c.figures["zhangmancheng"].location
    s.player.affinities["qinjie"] = 45
    figure_life.spread(s, c, "beat", "zhangmancheng", at=s.player.location, side="huang", text="在宛城打退了張曼成")
    assert any(x.startswith("qinjie|") for x in s.player.cheers)
    letters.deliver(s, c)
    letter = s.player.letters[-1]
    assert letter.kind == "道賀" and "打退了張曼成" in letter.text and letter.task is None


def test_the_card_shows_the_newest_unread_letter(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    letters.deliver(s, c)
    view = letters.view(s, c)
    assert view["sender"] == "秦頡" and view["task"]["live"]
    letters.read(s, view["id"])
    assert letters.view(s, c) is None
    assert any(row.get("commission") for row in bounties.status(s, c, None))  # 委託留在懸賞卡上


def test_the_model_rewrite_only_lands_on_the_same_letter(c):
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    letters.deliver(s, c)
    note = letters.request(s, c)
    assert note is not None and note.sender_name == "秦頡"
    assert letters.clean("**少俠**見字如面") == "少俠見字如面"
    assert letters.clean("借兵3000") == ""  # 數字不收
    assert letters.apply(s, note, "少俠台鑒：南陽吃緊，望速來援。")
    assert s.player.letters[-1].text.startswith("少俠台鑒") and letters.request(s, c) is None
    assert not letters.apply(s, note, "又一封")


def test_no_letters_when_switched_off(c):
    c.config.figure_life.letters = False
    s = _season(c)
    _anxious(s, c, "qinjie")
    s.player.affinities["qinjie"] = 40
    assert letters.deliver(s, c) == []


def test_the_content_check_catches_a_bad_relation(c):
    c.relations.append(RelationDef(kind="mentor", members=["liubei"]))
    with pytest.raises(ContentError):
        validate(c)
    c.relations[-1] = RelationDef(kind="brother", members=["liubei", "nobody"])
    with pytest.raises(ContentError):
        validate(c)


def test_the_server_shows_the_card_and_rewrites_the_letter_outside_the_lock(monkeypatch):
    import server
    from tianxia.characters import open_characters
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import Letter

    content = server.CONTENT
    monkeypatch.setattr(content.config.figure_life, "enabled", True)
    game = Game.new(content, "測試")
    game.world.open_season(content, 0.0)
    game.client = type("Fake", (), {})()
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.now = 0.0
    cid = next(iter(content.characters))
    game.state.player.letters.append(Letter(id=1, kind="道賀", sender=cid, at=0.0, about="打贏了", text="固定句"))
    open_characters().save(game.state)
    view = server.main_view(game)
    assert view["letter"]["id"] == 1 and view["letter"]["text"] == "固定句"
    seen = []

    def write(client, note):
        seen.append(open_world().db.writing())
        return "少俠台鑒：聞君大捷，喜不自勝。"

    monkeypatch.setattr(letters, "write", write)
    assert server.letter_once(game)
    assert seen == [False]  # 模型在鎖外寫
    assert game.state.player.letters[-1].text.startswith("少俠台鑒")
    assert not server.letter_once(game)  # 寫過了
    server.MAIN_ACTIONS["letter_read"](game, {"id": 1})
    assert "letter" not in server.main_view(game)


def test_the_letter_card_sits_above_just_now(monkeypatch):
    import server
    import webharness
    from test_prologue_web import run
    from tianxia.engine import Game
    from tianxia.state import Letter

    if webharness.NODE is None:
        pytest.skip("沒有 node")
    content = server.CONTENT
    monkeypatch.setattr(content.config.figure_life, "enabled", True)
    game = Game.new(content, "測試")
    game.world.open_season(content, 0.0)
    game.state.player.tutorial_step = len(content.tutorial.steps)
    game.now = 0.0
    game.sync(0.0)
    cid = next(iter(content.characters))
    game.state.player.letters.append(Letter(id=3, kind="道賀", sender=cid, at=0.0, about="打贏了", text="少俠台鑒：聞君大捷。"))
    m = server.main_view(game)
    page = run(m, "return H.pageJianghu();")
    assert 'data-act="letter-open" data-id="3"' in page and "少俠台鑒" in page
    assert "letter-body" not in page  # 收著只有一行
    opened = run(m, "return H.pageJianghu();", S={"letterOpen": 3})
    assert 'data-act="letter-read" data-id="3"' in opened and "letter-decline" not in opened  # 道賀沒有委託可婉拒
    if m.get("now"):
        assert opened.index("card letter") < opened.index('class="now')
