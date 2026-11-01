"""自建形象的訂單（功能包 looks 第二批）：下單扣元寶、一次一張、名字與樣子過字表；圖十張齊了變待審（假的生圖器當場抄好）；
管理者上傳、上架（從此是買到的一套，換季也在）、退回（元寶全退）；上傳的圖驗格式與大小；萬寶閣的一般購買不賣它。"""
from __future__ import annotations

import base64
import random
from pathlib import Path

import pytest
from conftest import next_season
from test_looks import T0, _game

from tianxia.engine import Game
from tianxia.features.looks import actions, orders
from tianxia.models import Look, MallItem
from tianxia.wallet import Wallet

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / "web/img/looks/moying"


@pytest.fixture
def on(content):
    content.config.mall.enabled, content.config.mall.beta_grant = True, 5000
    content.looks = {"moying": Look(id="moying", name="墨影", bots=True)}
    content.mall = {i.id: i for i in (
        MallItem(id="look_moying", name="墨影形象", price=600, kind="look", look="moying", effects={"look": 1}),
        MallItem(id="look_order", name="自建形象", price=900, kind="look", effects={"look_order": 1}),
    )}
    content.config.admins = ["管理者"]
    return content


def _admin(content, world) -> Game:
    admin = Game.new(content, "管理者", rng=random.Random(1), world=world)
    admin.sync(T0)
    return admin


def _upload_all(admin, pid):
    out = []
    for sheet in orders.SHEETS:
        out += actions.admin_upload(admin, pid, sheet, (ART / f"{sheet}.webp").read_bytes())
    return out


@pytest.mark.smoke
def test_order_upload_release_and_wear(on):
    game = _game(on)
    msgs = actions.order(game, "白衣書生", "白衣書生，背著竹簍", "order-ref-001")
    assert "下單了「白衣書生」" in msgs[-1] and Wallet(game.world.db).balance("沈浪") == 4100
    view = actions.view(game)
    assert view["order"]["open"] and view["order"]["list"][0]["status"] == orders.PENDING
    assert actions.order(game, "第二套", "黑衣", "order-ref-002")[-1] == orders.OPEN_ORDER  # 一次一張
    admin = _admin(on, game.world)
    pid = view["order"]["list"][0]["id"]
    row = actions.admin_view(admin)["open"][0]
    assert row["owner"] == "沈浪" and row["prompts"]["hero_bare_idle"].count("白衣書生，背著竹簍") == 1
    out = _upload_all(admin, pid)
    assert "十張齊了" in out[-1]
    assert "上架了" in actions.admin_release(admin, pid)[-1]
    look = orders.look_id(pid)
    assert look in [lk["id"] for lk in actions.view(game)["looks"] if lk["mine"]]
    assert "白衣書生" in actions.wear(game, look)[-1] and game.arena_look() == look


def test_fake_generator_makes_it_ready_for_review(on, monkeypatch):
    monkeypatch.setenv(actions.GEN_ENV, "fake")
    game = _game(on)
    actions.order(game, "白衣書生", "白衣書生", "order-ref-003")
    o = actions.view(game)["order"]["list"][0]
    assert o["status"] == orders.REVIEW
    assert len(orders.present(actions.image_root(game), orders.look_id(o["id"]))) == len(orders.SHEETS)


def test_reject_refunds_and_closes_the_order(on):
    game = _game(on)
    actions.order(game, "白衣書生", "白衣書生", "order-ref-004")
    pid = actions.view(game)["order"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert actions.admin_reject(admin, pid, "")[-1].startswith("（要寫原因")
    assert "退回了" in actions.admin_reject(admin, pid, "畫面不雅")[-1]
    assert Wallet(game.world.db).balance("沈浪") == 5000
    o = actions.view(game)["order"]["list"][0]
    assert (o["status"], o["reason"], actions.view(game)["order"]["open"]) == (orders.REJECTED, "畫面不雅", False)
    assert "已經退回" in actions.admin_release(admin, pid)[-1]


def test_made_look_survives_a_new_season(on, world):
    game = _game(on, world=world)
    actions.order(game, "白衣書生", "白衣書生", "order-ref-005")
    pid = actions.view(game)["order"]["list"][0]["id"]
    admin = _admin(on, world)
    _upload_all(admin, pid)
    actions.admin_release(admin, pid)
    actions.wear(game, orders.look_id(pid))
    next_season(on, world, game)
    assert game.arena_look() == orders.look_id(pid)


def test_bad_uploads_are_refused(on):
    game = _game(on)
    actions.order(game, "白衣書生", "白衣書生", "order-ref-006")
    pid = actions.view(game)["order"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert "要 880×220" in actions.admin_upload(admin, pid, "hero_bare_idle", (ART / "hero_bare_hit.webp").read_bytes())[-1]
    assert "PNG 或 WebP" in actions.admin_upload(admin, pid, "hero_bare_idle", b"GIF89a....")[-1]
    assert "沒有「cape」" in actions.admin_upload(admin, pid, "cape", b"")[-1]
    assert "還缺 10 張" in actions.admin_release(admin, pid)[-1]
    assert actions.admin_upload(game, pid, "hero_bare_idle", b"")[-1] == "（此刻無法這麼做。）"  # 不是管理者


def test_names_and_prompts_are_checked(on):
    game = _game(on)
    assert actions.order(game, "", "白衣", "order-ref-007")[-1] == orders.NO_NAME
    assert actions.order(game, "墨影", "白衣", "order-ref-008")[-1] == orders.NAME_TAKEN.format(name="墨影")
    assert actions.order(game, "白衣書生", "", "order-ref-009")[-1] == orders.NO_PROMPT
    assert actions.order(game, "白衣書生", "看 http://x.example", "order-ref-010")[-1] != ""
    assert Wallet(game.world.db).balance("沈浪") == 5000


def test_the_shelf_never_sells_the_order_item(on):
    game = _game(on)
    assert "look_order" not in [i["id"] for i in game.mall_view()["items"]]
    assert game.mall_buy("look_order", "buy-ref-0011")[-1] == "沒有這件商品。"


def test_png_and_webp_headers():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (880).to_bytes(4, "big") + (220).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"
    assert orders.image_size(png) == ("png", 880, 220)
    assert orders.sheet_problem("hero_bare_idle", png) is None
    data = (ART / "hero_bare_fall.webp").read_bytes()
    assert orders.image_size(data) == ("webp", 1320, 220)
    assert base64.b64encode(data)  # 網頁照 base64 送
