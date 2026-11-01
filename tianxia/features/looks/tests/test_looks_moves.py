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


@pytest.fixture
def on(content):
    content.config.mall.enabled, content.config.mall.beta_grant = True, 5000
    content.looks = {"moying": Look(id="moying", name="墨影", bots=True)}
    content.mall = {i.id: i for i in (
        MallItem(id="look_order", name="自建形象", price=900, kind="look", effects={"look_order": 1}),
        MallItem(id="move_order", name="招式動畫", price=300, kind="look", effects={"move_order": 1}),
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
    actions.order_move(game, "一道青色劍氣橫掃", ref)
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "可以審核" in actions.admin_move_upload(admin, pid, FX.read_bytes())[-1]
    assert "上架了" in actions.admin_move_release(admin, pid)[-1]
    return pid


@pytest.mark.smoke
def test_order_upload_release_and_the_arena_draws_it(on):
    game = _game(on)
    art = _art(game)
    msgs = actions.order_move(game, "一道青色劍氣橫掃", "move-ref-001")
    assert f"替「{art.name}」下單了招式動畫（拳腳）" in msgs[-1] and Wallet(game.world.db).balance("沈浪") == 4700
    view = actions.view(game)["moves"]
    assert view["open"] and view["art"] == art.name and view["list"][0]["status"] == orders.PENDING
    assert actions.order_move(game, "第二招", "move-ref-002")[-1] == moves.OPEN_ORDER  # 一次一張
    assert game.arena_move() == ""  # 還沒上架
    pid = view["list"][0]["id"]
    admin = _admin(on, game.world)
    row = actions.admin_view(admin)["moves"]["open"][0]
    assert row["owner"] == "沈浪" and "一道青色劍氣橫掃" in row["gen_prompt"]
    actions.admin_move_upload(admin, pid, FX.read_bytes())
    actions.admin_move_release(admin, pid)
    assert game.arena_move() == moves.move_id(pid)
    lib = actions.view(game)["moves"]["library"]
    assert [(x["move"], x["bound"], x["on_art"]) for x in lib] == [(moves.move_id(pid), art.name, True)]
    assert actions.order_move(game, "再一招", "move-ref-003")[-1] == moves.ALREADY.format(art=art.name)  # 這一門已經綁了


def test_only_your_own_art_and_a_matching_style(on, monkeypatch):
    game = _game(on)
    assert actions.order_move(game, "劍氣", "move-ref-004")[-1] == moves.NO_ART  # 內容裡的武功、或沒練
    _art(game)
    pid = _made(on, game, "move-ref-005")
    monkeypatch.setattr(actions, "current_style", lambda ctx: "slash")
    assert game.arena_move() == ""  # 換了兵器、打法對不上：不疊
    assert actions.bind_move(game, pid)[-1] == moves.WRONG_STYLE.format(want="拳腳", have="揮砍")


def test_a_new_season_keeps_the_move_and_rebinds_for_free(on, world):
    game = _game(on, world=world)
    _art(game)
    pid = _made(on, game, "move-ref-006")
    next_season(on, world, game)
    assert game.arena_move() == ""  # 武功歸零了、這一季還沒綁
    art = _art(game, "流雲掌")
    view = actions.view(game)["moves"]
    assert view["library"][0]["bindable"] and view["library"][0]["bound"] == ""
    before = Wallet(world.db).balance("沈浪")
    assert actions.bind_move(game, pid)[-1] == moves.BOUND.format(art=art.name)
    assert game.arena_move() == moves.move_id(pid) and Wallet(world.db).balance("沈浪") == before


def test_reject_refunds(on):
    game = _game(on)
    _art(game)
    actions.order_move(game, "劍氣", "move-ref-007")
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "（要寫原因" in actions.admin_move_reject(admin, pid, "")[-1]
    assert "元寶 +300" in actions.admin_move_reject(admin, pid, "看不出是招式")[-1]
    row = actions.view(game)["moves"]["list"][0]
    assert (row["status"], row["reason"]) == (orders.REJECTED, "看不出是招式") and Wallet(game.world.db).balance("沈浪") == 5000


def test_bad_uploads_and_the_shelf(on):
    game = _game(on)
    _art(game)
    actions.order_move(game, "劍氣", "move-ref-008")
    pid = actions.view(game)["moves"]["list"][0]["id"]
    admin = _admin(on, game.world)
    hit = (actions.WEB_IMG / "arena" / "hero_bare_hit.webp").read_bytes()
    assert "要 1320×220" in actions.admin_move_upload(admin, pid, hit)[-1]
    assert "還沒有光效圖" in actions.admin_move_release(admin, pid)[-1]
    assert actions.admin_move_upload(game, pid, b"")[-1] == "（此刻無法這麼做。）"  # 不是管理者
    assert "move_order" not in [i["id"] for i in game.mall_view()["items"]]
    assert game.mall_buy("move_order", "buy-ref-0012")[-1] == "沒有這件商品。"


def test_the_fake_generator_copies_the_sample(on, monkeypatch):
    monkeypatch.setenv(actions.GEN_ENV, "fake")
    game = _game(on)
    _art(game)
    actions.order_move(game, "劍氣", "move-ref-009")
    row = actions.view(game)["moves"]["list"][0]
    assert row["status"] == orders.REVIEW
    assert orders.sheet_file(actions.image_root(game), moves.move_id(row["id"]), moves.SHEET) is not None


def test_bots_never_carry_a_move(on):
    game = _game(on, name="假人甲")
    game.state.player.bot = True
    assert game.arena_move() == ""
