"""招式動畫（功能包 looks 第三批）：替自己合成或自創的武功下單（內容裡的武功不行）、一次一張、扣元寶；管理者上傳一張六格的光效、
上架放進招式庫；擂台記綁在現在練的那一門、打法對得上的那一招；換季武功歸零，招式還在，綁到新的一門（同打法免費）；退回元寶全退；
萬寶閣的一般購買不賣它。"""
from __future__ import annotations

import random

import pytest
from conftest import next_season
from test_looks import T0, _game

from tianxia.engine import Game
from tianxia.features.looks import actions, moves, orders
from tianxia.martial_arts import generate_from_name
from tianxia.models import Look, MallItem
from tianxia.wallet import Wallet

FX = actions.FX_SAMPLE
ART = (actions.WEB_IMG / "arena" / "weapon_sword.webp").read_bytes()  # 一張小的去背圖，當法相、巨物那一張
BUDDHA = "背後出現一座大佛擊出一掌"  # 要畫兩樣：大佛、佛掌


@pytest.fixture
def on(content):
    content.config.mall.enabled, content.config.mall.beta_grant = True, 5000
    content.looks = {"moying": Look(id="moying", name="墨影", bots=True)}
    content.mall = {i.id: i for i in (
        MallItem(id="look_order", name="自建形象", price=900, kind="look", effects={"look_order": 1}),
        MallItem(id="move_order", name="獨門絕招", price=300, kind="look", effects={"move_order": 1}),
        MallItem(id="move_basic", name="通用絕招", price=60, kind="look", effects={"move_basic": 1}),
    )}
    content.config.admins = ["管理者"]
    return content


def _art(game, name="旋風腿"):
    """替他練一門合成出來的武功（全服登記的、不在內容裡）。"""
    art = generate_from_name(name, "武學", name, weights={"下品": 100.0, "中品": 0.0, "上品": 0.0, "絕學": 0.0})
    game.world.claim_skill_name(art)
    game.state.player.arts.append(art.id)
    game.state.player.member.wugong_id = art.id
    return art


def _admin(content, world) -> Game:
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.sync(T0)
    return admin


def _made(on, game, ref="move-ref-001") -> int:
    """一句話自創、有要畫的那一種：下單、管理者上傳兩張、上架。"""
    actions.order_move(game, BUDDHA, ref)
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "還缺 art2" in actions.admin_move_upload(admin, pid, ART, "art1")[-1]
    assert "可以審核" in actions.admin_move_upload(admin, pid, ART, "art2")[-1]
    assert "上架了" in actions.admin_move_release(admin, pid)[-1]
    return pid


@pytest.mark.smoke
def test_order_upload_release_and_the_arena_draws_it(on):
    game = _game(on)
    art = _art(game)
    msgs = actions.order_move(game, BUDDHA, "move-ref-001")
    assert f"替「{art.name}」下單了絕招（拳腳）" in msgs[-1] and "「大佛」「佛掌」" in msgs[-1]
    assert Wallet(game.world.db).balance("沈浪") == 4700
    view = actions.view(game)["moves"]
    assert view["open"] and view["art"] == art.name and view["list"][0]["status"] == orders.PENDING
    assert view["list"][0]["arts"] == ["大佛", "佛掌"]
    assert actions.order_move(game, "一劍寒光", "move-ref-002")[-1] == moves.OPEN_ORDER  # 一次一張
    assert game.arena_move() == ""  # 還沒上架
    pid = view["list"][0]["id"]
    admin = _admin(on, game.world)
    row = actions.admin_view(admin)["moves"]["open"][0]
    assert row["owner"] == "沈浪" and row["missing"] == ["art1", "art2"] and row["gen_prompt"] == ""
    assert [a["label"] for a in row["arts"]] == ["大佛", "佛掌"] and BUDDHA in row["arts"][0]["prompt"]
    assert "還沒有圖" in actions.admin_move_release(admin, pid)[-1]
    actions.admin_move_upload(admin, pid, ART, "art1")
    actions.admin_move_upload(admin, pid, ART, "art2")
    actions.admin_move_release(admin, pid)
    assert game.arena_move() == moves.move_id(pid)
    assert actions.scene_of(game, moves.move_id(pid))["arts"][1]["label"] == "佛掌"
    lib = actions.view(game)["moves"]["library"]
    assert [(x["move"], x["worn"], x["plays"]) for x in lib] == [(moves.move_id(pid), True, True)]  # 做好了就穿在身上
    # 這一門已經有一招上場了，但照樣可以再創（企劃者 2026-11-02）：新的先進招式庫、不自動換上去
    again = actions.order_move(game, "背後一尊金剛砸下巨拳", "move-ref-003")[-1]
    assert "先放進招式庫" in again and game.arena_move() == moves.move_id(pid)


def test_a_line_with_nothing_to_draw_is_learned_on_the_spot(on):
    """通用絕招（60，企劃者 2026-11-02 分兩種）：用現成的光效演，當場學成、上身，不用審核。
    同一句買獨門（300）會被退回來——沒有東西可畫，不收錢（見下一條）。"""
    game = _game(on)
    art = _art(game)
    msgs = actions.order_move(game, "一劍寒光九萬里", "move-ref-010", basic=True)
    assert msgs[-1].startswith(f"「{art.name}」的通用絕招學成了") and Wallet(game.world.db).balance("沈浪") == 4940
    mid = game.arena_move()
    assert mid.startswith("m")
    scene = actions.scene_of(game, mid)
    assert [b["op"] for b in scene["beats"]] == ["暗場", "蓄勢", "落款", "飄落", "光束", "異狀", "白光"] and scene["arts"] == []
    assert scene["name"] == art.name  # 沒有長出招名時落款寫武功的名字


def test_the_line_is_checked_before_charging(on):
    game = _game(on)
    _art(game)
    assert actions.order_move(game, "a sword", "move-ref-011")[-1] == "只能寫中文。"
    assert "最多" in actions.order_move(game, "劍" * 31, "move-ref-012")[-1]
    assert actions.preview_scene(game, "一劍寒光")["scene"]["beats"]
    assert actions.preview_scene(game, "")["problem"] == "寫一句這一招長什麼樣子。"
    assert Wallet(game.world.db).balance("沈浪") == 5000


def test_only_your_own_art_and_a_matching_style(on, monkeypatch):
    game = _game(on)
    assert actions.order_move(game, "劍氣", "move-ref-004")[-1] == moves.NO_ART  # 下單要自己合成或自創的武功
    _art(game)
    pid = _made(on, game, "move-ref-005")
    assert game.arena_move() == moves.move_id(pid)  # 買第一招：身上空著，順手穿上
    monkeypatch.setattr(actions, "current_style", lambda ctx: "slash")
    assert game.arena_move() == ""  # 換了兵器、打法對不上：不疊（穿著照舊，只是不演）
    assert moves.worn(Wallet(game.world.db), "沈浪") == pid


def test_a_worn_move_that_cannot_play_says_so(on, monkeypatch):
    """穿著、但手上的兵器換了打法：擂台上不會演（出招的身體圖四種打法各一套），畫面要講明白，不能讓人以為壞了。
    Joy 2026-11-02：「我那個絕招寒霜雪怎麼都還沒施放過」——當時是空手下的單（拳腳），後來拿了劍。"""
    game = _game(on)
    _art(game)
    pid = _made(on, game, "move-ref-020")
    view = actions.view(game)["moves"]
    row = view["library"][0]
    assert row["worn"] and row["plays"] and not row["asleep"] and view["asleep_text"] == ""  # 空手：演得出來
    monkeypatch.setattr(actions, "current_style", lambda ctx: "slash")  # 拿起劍
    view = actions.view(game)["moves"]
    row = view["library"][0]
    assert game.arena_move() == ""  # 真的不會演
    assert row["asleep"] and not row["plays"] and row["worn"]  # 還穿在身上，只是不演
    assert row["asleep_text"] == moves.ASLEEP.format(want="拳腳", have="揮砍") == view["asleep_text"]
    assert "揮砍" in view["order_style_note"]  # 下單那一塊也先講明打法會鎖住


def test_another_style_for_the_same_art_can_be_ordered(on, monkeypatch):
    """換了兵器，身上那一招不會演——再創一招對得上的，換穿過去就好（企劃者 2026-11-02 配套）。"""
    game = _game(on)
    _art(game)
    first = _made(on, game, "move-ref-021")
    second = actions.order_move(game, "再一拳", "move-ref-022", basic=True)[-1]  # 幾招都可以創
    assert "學成了" in second and "身上已經穿著一招，這一招先放進招式庫" in second
    monkeypatch.setattr(actions, "current_style", lambda ctx: "slash")  # 拿起劍
    second = _made(on, game, "move-ref-023")  # 揮砍那一招
    rows = {r["id"]: r for r in actions.view(game)["moves"]["library"]}
    assert rows[first]["asleep"] and not rows[second]["worn"]  # 身上還是第一招，而且睡著了
    assert "換上" in actions.wear_move(game, second)[-1]
    rows = {r["id"]: r for r in actions.view(game)["moves"]["library"]}
    assert rows[second]["plays"] and not rows[first]["worn"]  # 換穿過去，揮砍那一招上場


def test_a_new_season_keeps_the_move_on(on, world):
    """換季：穿在身上的那一招照穿（企劃者 2026-11-02「這應該跟穿衣服一樣」——跟練哪一門武功無關，不必重綁）。"""
    game = _game(on, world=world)
    _art(game)
    pid = _made(on, game, "move-ref-006")
    assert game.arena_move() == moves.move_id(pid)
    next_season(on, world, game)
    before = Wallet(world.db).balance("沈浪")
    assert game.arena_move() == moves.move_id(pid)  # 武功歸零了，招照樣穿在身上
    row = actions.view(game)["moves"]["library"][0]
    assert row["worn"] and row["plays"] and Wallet(world.db).balance("沈浪") == before


def test_reject_refunds(on):
    game = _game(on)
    _art(game)
    actions.order_move(game, BUDDHA, "move-ref-007")
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "（要寫原因" in actions.admin_move_reject(admin, pid, "")[-1]
    assert "元寶 +300" in actions.admin_move_reject(admin, pid, "看不出是招式")[-1]
    row = actions.view(game)["moves"]["list"][0]
    assert (row["status"], row["reason"]) == (orders.REJECTED, "看不出是招式") and Wallet(game.world.db).balance("沈浪") == 5000


def test_bad_uploads_and_the_shelf(on):
    game = _game(on)
    _art(game)
    actions.order_move(game, BUDDHA, "move-ref-008")
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "這一招只要art1（大佛）、art2（佛掌）" in actions.admin_move_upload(admin, pid, ART, "fx")[-1]
    assert "要是 PNG 或 WebP" in actions.admin_move_upload(admin, pid, b"not an image", "art1")[-1]
    assert "還沒有圖" in actions.admin_move_release(admin, pid)[-1]
    assert actions.admin_move_upload(game, pid, b"")[-1] == "（此刻無法這麼做。）"  # 不是管理者
    assert "move_order" not in [i["id"] for i in game.mall_view()["items"]]
    assert game.mall_buy("move_order", "buy-ref-0012")[-1] == "沒有這件商品。"


def test_the_fake_generator_leaves_drawings_to_the_admin(on, monkeypatch):
    """假的生圖器只抄舊的光效單；一句話自創要畫的（大佛、佛掌）照樣等管理者上傳。"""
    monkeypatch.setenv(actions.GEN_ENV, "fake")
    game = _game(on)
    _art(game)
    actions.order_move(game, BUDDHA, "move-ref-009")
    row = actions.view(game)["moves"]["list"][0]
    assert row["status"] == orders.PENDING
    assert orders.sheet_file(actions.image_root(game), moves.move_id(row["id"]), moves.SHEET) is None


def test_bots_never_carry_a_move(on):
    game = _game(on, name="假人甲")
    game.state.player.bot = True
    assert game.arena_move() == ""


def test_the_two_kinds_of_move(on):
    """企劃者 2026-11-02：通用 60 不另外畫圖、當場學成；獨門 300 一定畫圖、送出等審核。
    那一句導不出看得出形狀的東西就不准買獨門（也不收錢）；導得出來的買通用則把那一樣換成一道光。"""
    game = _game(on)
    _art(game)
    wallet = Wallet(game.world.db)
    # 沒東西可畫 → 獨門退回、一塊錢都不扣
    msgs = actions.order_move(game, "一劍寒光九萬里", "move-ref-040")
    assert "獨門絕招要畫一樣看得出形狀的東西" in msgs[-1] and "60" in msgs[-1]
    assert wallet.balance("沈浪") == 5000
    # 有東西可畫 → 買通用：那一樣換成一道光，當場學成、只扣 60
    msgs = actions.order_move(game, "背後出現一座大佛擊出一掌", "move-ref-041", basic=True)
    assert "通用絕招學成了" in msgs[-1] and wallet.balance("沈浪") == 4940
    scene = actions.scene_of(game, game.arena_move())
    assert scene["arts"] == [] and "光束" in [b["op"] for b in scene["beats"]] and "法相" not in [b["op"] for b in scene["beats"]]


def test_you_can_keep_creating_and_only_one_plays_at_a_time(on):
    """企劃者 2026-11-02「不應該有這種限制，應該可以一直創」：同一門武功同一種打法想買幾招就買幾招，
    上場的只有一招——後買的先進招式庫，要換上去自己按（獨門還要等畫好審過，不能當場把能用的那一招鬆開）。"""
    game = _game(on)
    _art(game)
    wallet = Wallet(game.world.db)
    first = actions.order_move(game, "一劍寒光九萬里", "move-ref-050", basic=True)
    assert "學成了" in first[-1] and "先放進招式庫" not in first[-1]  # 第一招：當場上場
    playing = game.arena_move()
    for n, line in enumerate(("風捲殘雲", "月落星沉"), start=51):
        msgs = actions.order_move(game, line, f"move-ref-0{n}", basic=True)
        assert "學成了" in msgs[-1] and "先放進招式庫" in msgs[-1]
    view = actions.view(game)["moves"]
    assert len(view["library"]) == 3 and sum(1 for r in view["library"] if r["plays"]) == 1  # 三招都在，只有一招上場
    assert game.arena_move() == playing  # 上場的還是第一招
    assert wallet.balance("沈浪") == 5000 - 60 * 3
    newer = next(r["id"] for r in view["library"] if not r["plays"])
    assert "換上" in actions.wear_move(game, newer)[-1]
    assert game.arena_move() != playing  # 換上去了
    assert sum(1 for r in actions.view(game)["moves"]["library"] if r["plays"]) == 1  # 還是只有一招上場
