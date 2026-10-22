"""榜單點開看卡（Joy 2026-10-22「上榜的武學其他玩家應該要可以點的開來看卡，才知道有多強，也讓知識流通」）：
武學榜、內功榜那一列點開是主人身上那一門的唯讀功法卡（skillview.shown_art，跟主人修練頁那張同一份料、沒有任何按主人才按得到的東西）；
神器譜那一筆點開是那一把的裝備卡（skillview.shown_gear）。只開得了榜上看得到的那幾列（leaderboard.art_card、gear_card）。
伺服器 /api/board_card 只讀、不拿行動鎖；網頁的列變成鈕、卡疊在抽屜裡，卡上沒有 data-act。"""
from __future__ import annotations

import random
import re

import pytest
from test_forge_divine import _forger, divine_content  # noqa: F401（fixture）
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia import forge_secrets, leaderboard, smithing
from tianxia.characters import open_characters
from tianxia.state import GearFind, new_game_state

PRIVATE = {"melt", "cultivate", "might", "compare", "relearn", "judge", "glow", "worn"}  # 只有主人自己按得到、比得了的


def _ranked(content, n: int) -> list[str]:
    """n 個人身上都練著 fist（成數越前面越高），存進角色表；回名號，照榜上的順序。"""
    names = [f"甲{i:02d}" for i in range(n)]
    for i, name in enumerate(names):
        state = new_game_state(content, name)
        state.player.member.wugong_id = "fist"
        state.player.member.wugong_level = 10 - i if i < 10 else 1
        state.player.art_levels["fist"] = state.player.member.wugong_level
        open_characters().save(state)
    return names


def test_a_listed_art_opens_with_the_owners_card_and_nothing_private(content, world):
    names = _ranked(content, 1)
    board = leaderboard.compute_boards(content, world, top=None)
    card = leaderboard.art_card(content, world, board, "武學", names[0])
    assert card["owner"] == names[0] and card["kind"] == "武學" and card["id"] == "fist"
    assert card["level"] == 10 and "【" in card["card"] and isinstance(card["score"], int)
    assert not PRIVATE & card.keys()
    assert leaderboard.art_card(content, world, board, "內功", names[0]) is None  # 那一欄空著
    assert leaderboard.art_card(content, world, board, "善人", names[0]) is None  # 不是功法的榜
    assert leaderboard.art_card(content, world, board, "武學", "沒這個人") is None


def test_only_rows_you_can_see_open(content, world):
    """前 TOP_N 名人人點得開；第 TOP_N 名以後只有自己點得開自己（榜單底下那一行「你：第 N 名」）。"""
    names = _ranked(content, leaderboard.TOP_N + 1)
    board = leaderboard.compute_boards(content, world, top=None)
    assert [row[0] for row in board["武學"]][-1] == names[-1]
    assert leaderboard.art_card(content, world, board, "武學", names[leaderboard.TOP_N - 1]) is not None
    assert leaderboard.art_card(content, world, board, "武學", names[-1]) is None
    assert leaderboard.art_card(content, world, board, "武學", names[-1], me=names[-1]) is not None
    assert leaderboard.art_card(content, world, board, "武學", names[-1], me=names[0]) is None


def test_the_owner_moving_to_a_new_season_closes_the_card(content, world):
    names = _ranked(content, 1)
    board = leaderboard.compute_boards(content, world, top=None)
    state = open_characters().load(names[0])
    state.player.season_number += 1  # 快取的榜還寫著他，存檔已經不是這一季的了
    open_characters().save(state)
    assert leaderboard.art_card(content, world, board, "武學", names[0]) is None


def test_a_divine_original_opens_from_the_book(divine_content, world):  # noqa: F811
    owner = _forger(divine_content, world, name="甲")
    original, _ = smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    smithing.name_divine(owner.state, divine_content, world, original.id, "斬月")
    original.tempers = 2
    open_characters().save(owner.state)
    row = next(r for r in owner.divine_book_view() if "斬月" in r["name"])
    card = leaderboard.gear_card(divine_content, world, row["season"], row["ref"])
    assert card["name"] == "【斬月】" and card["owner"] == "甲" and card["what"] == "劍" and "神器" in card["grade"]
    assert card["tempers"] == 2 and card["edge"] == original.edge and card["season"] == row["season"]
    assert leaderboard.gear_card(divine_content, world, row["season"] + 1, row["ref"]) is None  # 季對不上
    assert leaderboard.gear_card(divine_content, world, row["season"], "鑄|沒這條") is None


def test_an_original_no_longer_on_hand_is_drawn_from_the_book(divine_content, world):  # noqa: F811
    """上一季的原品、主人已經不在角色表上：照譜上記的種類、屬性、階畫，淬煉與磨損不寫（不編）。"""
    season = world.get_season_number()
    old = GearFind(secret="t_old", slot="armor", attribute="剛", tier=3, title="舊甲", creator="丙", creator_shown="丙",
                   divine=True, owner="丙", master_shown="丙", divine_name="鎮岳甲", copies=3)
    with world.db.transaction() as conn:
        conn.execute("INSERT INTO gear_recipes (season, key, name, creator, data) VALUES (?, ?, ?, ?, ?)",
                     (season - 1, "鑄|t_old", "鎮岳甲", "丙", old.model_dump_json()))
    card = leaderboard.gear_card(divine_content, world, season - 1, "鑄|t_old")
    assert card["name"] == "【鎮岳甲】" and card["owner"] == "丙" and card["attribute"] == "剛"
    assert card["tempers"] is None and card["edge"] is None


def test_every_book_entry_carries_a_ref(divine_content, world):  # noqa: F811
    owner = _forger(divine_content, world, name="甲")
    smithing.forge(owner.state, divine_content, world, "劍", "gang_3", "gang_3")
    rows = owner.divine_book_view()
    assert rows and all(r["ref"].startswith(forge_secrets.PREFIX) for r in rows)


# ── 伺服器 ──


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(server.app)


def test_the_endpoint_reads_without_the_action_lock(client, monkeypatch):
    from test_server import _player

    monkeypatch.setattr(server, "BOARDS_CACHE", {})
    _player(client)
    state = open_characters().load("沈青衫")
    state.player.member.wugong_id = next(k for k, a in server.CONTENT.skills.items() if a.kind == "武學")
    open_characters().save(state)
    monkeypatch.setattr(server, "_locked", lambda game: (_ for _ in ()).throw(AssertionError("不該拿行動鎖")))
    out = client.get("/api/board_card", params={"board": "武學", "name": "沈青衫"}).json()["card"]
    assert out["owner"] == "沈青衫" and out["card"].startswith("<")  # 功法卡的字轉成 HTML（同修練頁）
    assert client.get("/api/board_card", params={"board": "武學", "name": "沒這個人"}).json() == {"card": None}
    assert client.get("/api/board_card", params={"board": "神器", "season": 1, "ref": "鑄|x"}).json() == {"card": None}


def test_the_endpoint_needs_a_login():
    from fastapi.testclient import TestClient

    assert TestClient(server.app).get("/api/board_card", params={"board": "武學", "name": "x"}).status_code == 401


# ── 網頁 ──

NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "boardsHtml", "boardCardHtml", ')
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

BOARDS = {"boards": [
    {"id": "善人", "title": "善人榜", "note": "", "rows": [{"rank": 1, "name": "甲", "text": "善名 3", "you": False}]},
    {"id": "武學", "title": "天下武學榜", "note": "", "rows": [{"rank": 1, "name": "甲", "text": "【拳】", "sub": "上品・評 9・威力 3.0", "you": False}]},
    {"id": "神器", "title": "神器譜", "note": "", "book": [{"season": 1, "name": "【斬月】", "text": "劍・屬剛", "ref": "鑄|t_star"}]},
]}
ART = {"id": "fist", "name": "拳", "kind": "武學", "quality": "上品", "attribute": "剛", "level": 7, "card": "<p>【拳】</p>",
       "affinity": "剛", "slots": [{"id": "i1", "name": "斷金", "attribute": "剛", "skill": "破甲", "strength": 2, "desc": "", "look": "佳", "fx": []}, None],
       "colors": [["剛"], []], "pose": None, "weapon": None, "score": 9, "tactic": "", "fifth": None, "look": "", "tier": None, "owner": "甲"}


def _run(script, S=None):
    return webharness.run(DRIVER, {"m": {}, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


@needs_node
def test_art_and_book_rows_open_but_other_boards_do_not():
    html = _run("H.S.board = '武學'; const a = H.boardsHtml(H.S.boards); H.S.board = '善人'; const b = H.boardsHtml(H.S.boards);"
                " H.S.board = '神器'; return [a, b, H.boardsHtml(H.S.boards)];", {"boards": BOARDS})
    assert 'data-act="board-card" data-board="武學" data-name="甲"' in html[0]
    assert "board-card" not in html[1]
    assert 'data-board="神器" data-season="1" data-ref="鑄|t_star"' in html[2]


@needs_node
def test_the_card_has_no_buttons_but_the_close():
    html = _run("return H.boardCardHtml();", {"boardCard": {"loading": False, "board": "武學", "card": ART}})
    assert "甲身上的武學" in html and "第7成" in html and "評 9" in html and "斷金" in html
    assert set(re.findall(r'data-act="([^"]+)"', html)) == {"board-card-close"}
    gear = {"name": "【斬月】", "what": "劍", "attribute": "剛", "grade": "三階上品・神器", "tempers": None, "edge": None,
            "wear_word": "鋒利度", "tactic": [], "owner": "甲", "season": 1}
    html = _run("return H.boardCardHtml();", {"boardCard": {"loading": False, "board": "神器", "card": gear}})
    assert "【斬月】" in html and "在甲手上" in html and "鋒利度" not in html
    html = _run("return H.boardCardHtml();", {"boardCard": {"loading": False, "board": "武學", "card": None}})
    assert "看不到了" in html
