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
    assert "全套齊了" in out[-1]
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
    assert f"還缺 {len(orders.SHEETS)} 張" in actions.admin_release(admin, pid)[-1]
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


def test_every_sheet_prompt_tells_the_generator_to_keep_the_whole_character_in_frame():
    """審圖的清單要求「每一格一個完整的人、不能被切半」（studio.CHECK_SHEET），所以生圖的提示詞一定要講明留白與不准殘影：
    2026-11-02 第一張自建形象連七張都被擋下，理由全是頭頂被上緣裁掉、有一格模糊成殘影、臉與下襬褪色（要求跟指示對不上）。"""
    from tianxia.features.looks import studio

    order = orders.Order(pid=1, owner="甲", name="試", prompt="紅衣少女", status=orders.PENDING,
                         reason="", look="u1", time=0.0)
    prompts = orders.gen_prompts(order)
    assert set(prompts) == set(orders.SHEETS)
    for sheet, prompt in prompts.items():
        assert "must not touch or cross the frame edge" in prompt, sheet
        assert "margin" in prompt and "no motion blur" in prompt, sheet
    # 定裝照那一張也要（清單寫 full body, nothing cut off）
    assert "whole character must be inside the frame" in studio.PORTRAIT_PROMPT


def test_the_hand_table_follows_each_looks_own_body():
    """兵器掛在哪：web/arena_anim.js 的 RING_HAND 是照斗笠小子量的，換一套形象手就不在同一個地方
    （2026-11-02 量新收的四套，49 格裡各有 7～11 格落在身體以外，兵器懸在空中）。
    cutting.hand_row 照每一套自己的身體算，算完每一格都要落在人身上；倒地那幾格兵器本來就在地上，不動。"""
    pytest.importorskip("scipy")
    import io

    import numpy as np
    from PIL import Image

    from tianxia.features.looks import cutting

    for look in ("moying", "xianv"):
        folder = ROOT / "web/img/looks" / look
        if not folder.is_dir():
            continue
        for sheet in orders.ARENA:  # 走一趟那六張不掛兵器
            path = orders.sheet_file(ROOT / "web/img/looks", look, sheet)
            if path is None:
                continue
            data = path.read_bytes()
            row = cutting.hand_row(data, sheet)
            assert len(row) == orders.ARENA[sheet]
            a = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))[..., 3] > 32
            for k, (x, y) in enumerate(row):
                if cutting.HAND[sheet][k][3] == cutting.GROUND_LAYER:  # 掉在地上那幾格照舊
                    assert [x, y] == list(cutting.HAND[sheet][k][:2])
                    continue
                cell = a[:, k * cutting.CELL:(k + 1) * cutting.CELL]
                assert cell[max(0, y - 2):y + 3, max(0, x - 2):x + 3].any(), f"{look} {sheet}#{k + 1} 手位落空"


def test_the_python_hand_table_is_the_same_as_the_one_the_page_draws_with():
    """cutting.HAND 與 web/arena_anim.js 的 RING_HAND 是同一張表（兩邊各留一份，這一條盯著不要走掉）。"""
    import re

    from tianxia.features.looks import cutting

    js = (ROOT / "web/arena_anim.js").read_text(encoding="utf-8")
    block = js.split("const RING_HAND = {", 1)[1].split("};", 1)[0]
    table = {}
    for line in block.strip().splitlines():
        m = re.match(r"\s*(\w+):\s*\[(.*?)\],?\s*(//.*)?$", line.strip())
        if m:
            table[m.group(1)] = tuple(tuple(int(x) for x in g.split(",")) for g in re.findall(r"\[([^\]]+)\]", m.group(2)))
    assert table == {k: tuple(v) for k, v in cutting.HAND.items()}


def test_saving_a_sheet_writes_that_looks_hand_table(tmp_path):
    """存一張圖就順手更新 hands.json（網頁照它掛兵器；自建形象不必另外跑腳本）。"""
    pytest.importorskip("scipy")
    import json

    data = (ART / "hero_bare_idle.webp").read_bytes()
    orders.save_sheet(tmp_path, "u9", "hero_bare_idle", data)
    table = json.loads(orders.hands_file(tmp_path, "u9").read_text(encoding="utf-8"))
    assert list(table) == ["hero_bare_idle"] and len(table["hero_bare_idle"]) == 4
    orders.save_sheet(tmp_path, "u9", "hero_bare_hit", (ART / "hero_bare_hit.webp").read_bytes())
    table = json.loads(orders.hands_file(tmp_path, "u9").read_text(encoding="utf-8"))
    assert sorted(table) == ["hero_bare_hit", "hero_bare_idle"]  # 併進去，不是蓋掉


def test_only_the_owner_withdraws_and_not_after_release(on):
    """撤回只認自己的單；審核中也能撤；上架了的撤不回來（照商城退款）。"""
    game = _game(on)
    actions.order(game, "白衣書生", "白衣書生", "order-ref-021")
    pid = actions.view(game)["order"]["list"][0]["id"]
    admin = _admin(on, game.world)
    assert actions.withdraw(admin, pid, "look")[-1] == f"（沒有第 {pid} 號訂單。）"
    _upload_all(admin, pid)
    assert actions.view(game)["order"]["list"][0]["status"] == orders.REVIEW
    assert "撤回了" in actions.withdraw(game, pid, "look")[-1] and Wallet(game.world.db).balance("沈浪") == 5000
    assert any("撤回了" in e.lines[0] for e in game.state.journal if e.title == "形象")
    actions.order(game, "第二套", "黑衣", "order-ref-022")
    pid2 = actions.view(game)["order"]["list"][0]["id"]
    _upload_all(admin, pid2)
    actions.admin_release(admin, pid2)
    assert "撤不回來" in actions.withdraw(game, pid2, "look")[-1]


def test_a_white_hole_in_the_body_is_dropped_but_a_white_robe_is_not():
    """本機生圖常把手臂與身體圍住的那一塊白底留下來，疊在擂台背景上就是一塊白斑（Joy 2026-11-02 的本機評估）。
    挖掉它，但角色本來就穿白衣的不能挖——照定裝照上「封閉白塊佔身體幾 %」判（量到的：白衣書生 17.6%、
    其他三套 0.4～2.2%、斗笠小子 0.0%，所以門檻 5% 兩邊都離八倍遠）。"""
    pytest.importorskip("scipy")
    import io

    import numpy as np
    from PIL import Image

    from tianxia.features.looks import cutting

    # 斗笠小子自己：身上沒有封閉白塊，判定不是白衣，挖不挖都一樣
    hat = (ROOT / "web/img/arena/hero_bare_idle.webp").read_bytes()
    assert cutting.white_share(Image.open(io.BytesIO(hat)).convert("RGBA")) < 1.0
    assert not cutting.wears_white(hat)

    # 在他身上戳一塊 20×20 的不透明白：挖得掉
    im = Image.open(io.BytesIO(hat)).convert("RGBA")
    a = np.asarray(im).copy()
    ys, xs = np.nonzero(a[..., 3] > 32)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    a[cy:cy + 20, cx:cx + 20] = (255, 255, 255, 255)
    holed = Image.fromarray(a, "RGBA")
    assert cutting.white_share(holed) > 1.0
    after = np.asarray(cutting.drop_white_holes(holed))
    assert after[cy + 5, cx + 5, 3] == 0  # 白斑變透明了
    assert after[..., 3].sum() < np.asarray(holed)[..., 3].sum()

    # 穿白衣的那一套（本機產的白衣書生）：判成白衣，sheet_bytes 的 keep_white 會留著它
    white = ROOT / "web/img/looks/shusheng/hero_bare_idle.webp"
    if white.is_file():
        share = cutting.white_share(Image.open(white).convert("RGBA"))
        assert share > cutting.WHITE_SHARE, f"白衣書生量到 {share:.1f}%，應該高過門檻 {cutting.WHITE_SHARE}%"
