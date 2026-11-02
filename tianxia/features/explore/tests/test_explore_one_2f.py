"""減法季 2f：輿圖名字旁的兩個字也照這一處自己的比重寫（2e 驗收開的 FB-886；PM 2026-10-26）。

2e 讓鈕上、四格、行動列那一行都照「這一處此刻擲骰用的比重」寫（explore_one.hint_of）；輿圖第一層名字旁的兩個字還讀地點種類的表本身
（沒有危險度、不看誰在看），所以渡口 2★（白馬津、拒馬河畔、孟津渡）名字旁寫「參半」、鈕上寫「渡口多敵」，山 2★（北邙山、嵩山深處、綠林山寨、燕山腳）
名字旁寫「多料」、鈕上寫「山裡參半」。現在名字旁＝這個人站過去之後，鈕上小字的最後兩個字（Game.map_mostly 走 _outing_plan，跟鈕同一個函式）。
名字旁在底圖的地點清單裡（網頁讀 /api/map/base 的 places[].mostly，沒有改），所以底圖與疊層的 key 都帶著這一串字：字變了網頁才會重抓。
用正式內容（week7、season21）（以前整個檔標 slow，2026-10-31 起只有超過一秒的那幾條標）。"""
from __future__ import annotations

import re
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, plain_game, ready

import server
from tianxia import events as event_rules
from tianxia import explore_one, mapdata
from tianxia.state import Bounty

SIDES = ["guan", "huang", "haoqiang", None]
# 2★ 的渡與山（每星遭遇 +10、事件 −10；企劃者 2026-10-30 細分成十八張表之後各照自己的表）：
# 渡口 45／30／15／10 → 35／40／15／10 多敵；河畔 20／25／45／10 → 10／35／45／10 多料；
# 山林 10／30／45／15 → 5／40／45／15 多料；山寨 10／60／20／10 → 5／70／20／10 多敵
DANGEROUS_FORDS = ["baima_ford", "juma_river", "mengjin_ford"]
DANGEROUS_HILLS = ["beimang_hill", "deep_mountain", "lulin_zhai", "yanshan_foot"]
DANGEROUS_WORDS = {"baima_ford": "多敵", "mengjin_ford": "多敵", "juma_river": "多料",
                   "beimang_hill": "多料", "deep_mountain": "多料", "yanshan_foot": "多料", "lulin_zhai": "多敵"}


def _game(side, profile="week7", loc="yingshui"):
    game = ready(jianfa_game(profile), side=side, loc=loc)
    if side == "haoqiang":  # 地方豪強先挑依附哪一軍，選單才是平常的樣子
        game.choose("faction:ally:guan")
    return game


def _names(game) -> dict[str, str]:
    return {p["id"]: p["mostly"] for p in game.map_base()["places"]}


def _reset(game) -> None:
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def _strike(game, loc_id="yingchuan_wilds", squad="shanzei") -> Bounty:
    b = Bounty(id="s1", kind="strike", faction="guan", week=1, expires=1e12, silver=10, deeds=1, location=loc_id, squad=squad,
               takers=[game.state.player.name])
    game.state.world.bounties.append(b)
    return b


# ── 1. 名字旁＝站過去之後鈕上小字的最後兩個字 ──


def _every_place_agrees(game, names: dict[str, str] | None = None) -> int:
    """名字旁（底圖地點清單的 mostly，站在原處時給的）＝站過去之後探索鈕括號裡最後一段的最後兩個字，每一處都對；回有幾處。"""
    names = _names(game) if names is None else names
    checked = 0
    for loc_id, loc in game.content.locations.items():
        if loc.prologue_only:
            continue
        assert loc_id in names, loc_id
        ready(game, loc=loc_id)
        _reset(game)
        plan = game.outing_plan()
        assert plan is not None
        label = next(o for o in game.options(odds=False) if o.id == "act:explore").label
        assert label.endswith(f"・{plan.hint}）"), (loc_id, label)
        assert names[loc_id] == plan.hint[-2:], (loc_id, loc.danger, names[loc_id], plan.hint)
        checked += 1
    return checked


@pytest.mark.parametrize("profile", ["week7", "season21"])
@pytest.mark.parametrize("side", SIDES)
def test_the_name_beside_every_place_is_the_last_two_characters_of_its_button(side, profile):
    """每一處、每一種身分：名字旁（底圖地點清單的 mostly）＝這個人站過去之後，探索鈕括號裡最後一段的最後兩個字。"""
    assert _every_place_agrees(_game(side, profile)) >= 40


def test_the_names_follow_when_no_event_can_be_drawn_or_the_insight_is_missed():
    """抽不到事件（事件那一格歸 0，分給其餘的）、這個遊戲日在這裡悟錯過（感悟歸 0）：名字旁一樣跟鈕上走，寺變「多悟」。"""
    game = _game("guan")
    game.content.events.clear()  # 一則事件都沒有
    names = _names(game)
    assert names["baima_temple"] == "多悟" and _every_place_agrees(game, names) >= 40
    ready(game, loc="baima_temple")
    assert game.outing_plan().hint == "寺裡多悟"
    game = _game("guan")
    with mock.patch("tianxia.engine.sensing.missed_today", return_value=True):  # 每一處都悟錯過：感悟那一格是 0
        names = _names(game)
        assert _every_place_agrees(game, names) >= 40


def _only_events(game, *event_ids: str) -> None:
    keep = {event_id: game.content.events[event_id] for event_id in event_ids}
    game.content.events.clear()
    game.content.events.update(keep)


def test_whether_an_event_can_be_drawn_is_asked_at_the_place_not_where_the_viewer_stands():
    """事件池照地點挑（有的事件掛在特定地點）：只剩下邑縣一則地方事件時，只有下曲陽有事件可抽、名字旁寫「多事」，別的城是「參半」；
    看的人站在潁水（渡口）也一樣——名字旁要替每一處假裝站過去才問得對。"""
    game = _game("guan")
    _only_events(game, "jz_xqy_cellar")
    names = _names(game)
    assert names["xiaquyang"] == "多事" and names["yingchuan"] != "多事" and names["runan"] != "多事"
    assert _every_place_agrees(game, names) >= 40


def test_the_event_pool_questions_agree_with_the_full_list():
    """has_event_candidates（找到一則就停）、帶著算好的 hidden 問，都跟列出整份清單（event_candidates）說同一件事：每一處、每一種池子。"""
    game = _game("guan")
    for loc_id, loc in game.content.locations.items():
        if loc.prologue_only:
            continue
        ready(game, loc=loc_id)
        s, c = game.state, game.content
        hidden = event_rules.hidden_events(s, c)
        for pool in (None, "rare", "common"):
            listed = event_rules.event_candidates(s, c, "explore", pool)
            assert [e.id for e in event_rules.event_candidates(s, c, "explore", pool, hidden=hidden)] == [e.id for e in listed]
            assert event_rules.has_event_candidates(s, c, "explore", pool) == bool(listed) == event_rules.has_event_candidates(s, c, "explore", pool, hidden=hidden)
        # 一次性與奇遇加可重複的就是全部：_outing_weights 一趟只問一次（pool=None）跟以前問兩次是同一個答案
        assert bool(event_rules.event_candidates(s, c, "explore")) == bool(event_rules.event_candidates(s, c, "explore", "rare") or event_rules.event_candidates(s, c, "explore", "common"))


def test_events_that_are_hidden_from_this_viewer_do_not_count():
    """心意沒生效的人物事件、第三方的伏筆事件這些藏起來的事件，名字旁不能把它們算成「抽得到」：只剩一則藏起來的事件時，那一處的事件格是 0。"""
    game = _game("guan")
    _only_events(game, "stance_luzhi_refugees")  # 盧植的心意沒生效：藏起來，下曲陽、豪族塢堡、白馬津、鉅鹿大營才有它
    assert "stance_luzhi_refugees" in event_rules.hidden_events(game.state, game.content)
    names = _names(game)
    assert names["xiaquyang"] != "多事" and names["haozu_fort"] != "多事"
    assert _every_place_agrees(game, names) >= 40


@pytest.mark.parametrize("side", SIDES)
def test_where_the_viewer_stands_does_not_change_the_names(side):
    """名字旁是「他站過去之後」的字，不是「他現在站的地方」的字：站在別處、站在路上算出來都一樣。"""
    game = _game(side)
    names = _names(game)
    for loc_id in ("baima_temple", "changshe", "mengjin_ford", "lulin_zhai", "guan_camp"):
        ready(game, loc=loc_id)
        assert _names(game) == names, loc_id


@pytest.mark.parametrize("side", SIDES)
def test_dangerous_fords_and_hills_read_like_their_buttons(side):
    """FB-886 原例：危險的渡口、山，名字旁跟鈕上一樣照危險度加減過的比重寫（不是種類的表本身）。"""
    game = _game(side)
    names = _names(game)
    for loc_id in DANGEROUS_FORDS + DANGEROUS_HILLS:
        assert game.content.locations[loc_id].danger == 2 and names[loc_id] == DANGEROUS_WORDS[loc_id], (side, loc_id, names[loc_id])
    ready(game, loc="mengjin_ford")
    assert game.outing_plan().hint == "渡口多敵"
    ready(game, loc="lulin_zhai")
    assert game.outing_plan().hint == "山裡多敵"
    ready(game, loc="juma_river")
    assert game.outing_plan().hint == "渡口多料"


def test_the_easy_places_keep_the_words_of_their_kind():
    """危險度 1 的地方沒有修正，字跟地點種類的表一樣（城多事、寺多事、野多敵、山多料）。"""
    game = _game("guan")
    names = _names(game)
    for loc_id, loc in game.content.locations.items():
        if loc.prologue_only or loc.danger != 1 or loc_id not in names:
            continue
        table = explore_one.kind_of(game.content.config.jianfa, loc)
        if loc_id in ("changshe", "luoyang_road") or table.kind == explore_one.CAMP:
            continue  # 沒有對手（或自家營寨）的幾處下面另測
        assert names[loc_id] == explore_one.mostly_in(table), (loc_id, table.kind)


# ── 2. 看的人是誰，字就不同 ──


def test_a_place_without_foes_reads_by_what_is_left_for_the_one_looking():
    """官軍在長社沒有一般對手（只有頭目），遭遇那一格是 0：名字旁跟鈕一樣寫「多料」；黃巾站長社有對手，寫「多敵」。
    反過來黃巾在洛陽官道沒有對手：官道的表事件比素材多（25／0／15／10），寫「多事」。"""
    guan, huang = _names(_game("guan")), _names(_game("huang"))
    assert guan["changshe"] == "多料" and huang["changshe"] == "多敵"
    assert huang["luoyang_road"] == "多事" and guan["luoyang_road"] == "多敵"


def test_your_own_camp_reads_as_a_friendly_bout_and_the_other_sides_as_enemies():
    """自家營寨遇敵是跟同袍比劃，鈕上寫「同袍比劃」，名字旁最後兩個字「比劃」；別人的營寨是敵人，照比重寫「多敵」。"""
    guan, huang, drifter = _names(_game("guan")), _names(_game("huang")), _names(_game(None))
    for loc_id in ("guan_camp", "luzhi_camp"):
        assert guan[loc_id] == "比劃" and huang[loc_id] == "多敵" and drifter[loc_id] == "多敵", loc_id
    for loc_id in ("huangjin_camp", "nanyang_huangjin_camp", "julu_altar"):
        assert huang[loc_id] == "比劃" and guan[loc_id] == "多敵", loc_id
    game = _game("guan")
    ready(game, loc="guan_camp")
    assert game.outing_plan().hint == "同袍比劃"


def test_a_bounty_you_hold_here_reads_as_has_reward_unless_it_is_hopeless():
    """接了這裡的討伐懸賞，鈕上「野外有賞」，名字旁「有賞」；對那一路必敗時不強制（2e FB-880），鈕上照表「野外多敵」，名字旁跟著照表。"""
    game = _game("guan")
    game.state.player.member.wugong_id = "jichu_quanjiao"  # 對黃巾散兵「難分勝負」
    _strike(game)
    assert _names(game)["yingchuan_wilds"] == "有賞"
    ready(game, loc="yingchuan_wilds")
    assert game.outing_plan().hint == "野外有賞"
    ready(game, loc="yingshui")
    game.state.player.member.wugong_id = None  # 沒裝武學：威力 0，對誰都是必敗
    assert game.odds("shanzei", at="yingchuan_wilds") == "必敗"
    assert _names(game)["yingchuan_wilds"] == "多敵"
    ready(game, loc="yingchuan_wilds")
    assert game.outing_plan().hint == "野外多敵"


def test_asking_for_the_names_leaves_the_game_exactly_as_it_was():
    """名字旁是替每一處「假裝站過去」算的：不動存檔（連記憶體裡的位置都還在原處）、不碰 Game.rng、丟例外也要站回原處。"""
    game = _game("guan")
    state, before, rng = game.state, game.state.model_dump_json(), game.rng.getstate()
    game.map_mostly()
    game.map_base()
    game.map_state()
    assert game.state is state and game.state.model_dump_json() == before and game.rng.getstate() == rng
    with mock.patch.object(type(game), "_outing_plan", side_effect=RuntimeError("boom")), pytest.raises(RuntimeError):
        game.map_mostly()
    assert game.state is state and game.state.player.location == "yingshui" and game.state.model_dump_json() == before


def test_in_the_prologue_the_names_stay_by_the_table():
    """序章裡探索鈕是寫好的那幾步，沒有「出門一趟」的比重可看：名字旁照地點種類的表（跟鈕沒有可比的），也不算每一處。"""
    prologue = jianfa_game("week7")
    prologue.state.player.location, prologue.state.player.tutorial_step = prologue.content.tutorial.location, 0  # 站在草廬、序章第一步
    assert not prologue._outing_on() and prologue.map_mostly() is None
    cfg = prologue.content.config.jianfa
    assert all(p["mostly"] == explore_one.mostly_in(explore_one.kind_of(cfg, prologue.content.locations[p["id"]]))
               for p in prologue.map_base()["places"])
    assert prologue.map_base()["key"] == prologue.map_state()["key"] and mapdata.VIEWER_MOSTLY not in prologue.map_base()


# ── 3. 底圖與疊層的 key：字變了網頁才會重抓 ──


def test_base_and_state_carry_the_same_key_and_it_follows_the_words():
    server.MAP_BASE.clear()
    guan, huang = _game("guan"), _game("huang")
    one, two = server.map_base_view(guan), server.map_base_view(huang)
    assert one["key"] == guan.map_state()["key"] and two["key"] == huang.map_state()["key"]
    assert one["key"] != two["key"]  # 兩軍看到的字不一樣（長社、洛陽官道、自家營寨）
    assert {p["id"]: p["mostly"] for p in one["places"]} == _names(guan) and {p["id"]: p["mostly"] for p in two["places"]} == _names(huang)
    assert server.map_base_view(guan)["key"] == one["key"]  # 同一個人再問：同一把鍵
    assert one["svg"] is two["svg"] and one["regions"] is two["regions"]  # 重的那一份（山河的圖）照開放的地點只畫一次，不隨人


def test_the_base_and_the_overlay_differ_from_the_old_ones_only_by_the_words_and_the_key():
    """名字旁的字與兩邊的 key 以外，底圖與疊層一個字都沒動（跟 2e 的樣子比：map_mostly 回 None 就是 2e 的底圖與疊層）。"""
    game = _game("guan")
    base, state = game.map_base(), game.map_state()
    with mock.patch.object(type(game), "map_mostly", return_value=None):
        old_base, old_state = game.map_base(), game.map_state()
    assert base["key"] != old_base["key"] and state["key"] != old_state["key"] and base["key"] == state["key"]
    changed = {p["id"] for p, q in zip(base["places"], old_base["places"], strict=True) if p["mostly"] != q["mostly"]}
    assert {"changshe", "guan_camp", "luzhi_camp", "baima_ford", "mengjin_ford"} <= changed  # 危險的河畔、山林照比重也是「多料」，跟舊字一樣
    for p, q in zip(base["places"], old_base["places"], strict=True):
        assert {k: v for k, v in p.items() if k != "mostly"} == {k: v for k, v in q.items() if k != "mostly"}
    assert base[mapdata.VIEWER_MOSTLY] is True and mapdata.VIEWER_MOSTLY not in old_base  # 旗子：網頁看到它，名字旁整個照底圖（含「有賞」）
    assert server.map_base_view(game)[mapdata.VIEWER_MOSTLY] is True
    skip = ("key", "places", mapdata.VIEWER_MOSTLY)
    assert {k: v for k, v in base.items() if k not in skip} == {k: v for k, v in old_base.items() if k not in skip}
    assert {k: v for k, v in state.items() if k != "key"} == {k: v for k, v in old_state.items() if k != "key"}


def test_taking_a_bounty_changes_the_key_so_the_page_refetches_the_base():
    game = _game("guan")
    game.state.player.member.wugong_id = "jichu_quanjiao"
    before = game.map_state()["key"]
    _strike(game)
    after = game.map_state()["key"]
    assert after != before and server.map_base_view(game)["key"] == after
    assert {p["id"]: p["mostly"] for p in server.map_base_view(game)["places"]}["yingchuan_wilds"] == "有賞"


def test_a_word_that_did_not_change_leaves_the_key_alone():
    """換到一個字沒變的狀態（只換了站的地方）鍵不動，網頁就不會白白整頁重畫。"""
    game = _game("huang")
    key = game.map_state()["key"]
    ready(game, loc="baima_temple")
    assert game.map_state()["key"] == key


# ── 4. 關著的季一個字不變 ──


@pytest.mark.parametrize("make", [
    lambda: jianfa_game("week7", explore_one=False),
    lambda: plain_game("week7"),
    lambda: plain_game("season21"),
])
def test_when_the_small_words_are_off_the_names_and_keys_are_the_old_ones(make):
    game = ready(make(), side="guan", loc="yingshui")
    server.MAP_BASE.clear()
    assert game.map_mostly() is None
    base = game.map_base()
    assert all(p["mostly"] == mapdata.MOSTLY[p["glyph"]] for p in base["places"])
    assert mapdata.VIEWER_MOSTLY not in base and mapdata.VIEWER_MOSTLY not in server.map_base_view(game)  # 關著的季底圖沒有旗子，網頁照舊
    assert base["key"] == mapdata.base_key(game.state, game.content) == game.map_state()["key"]
    assert server.map_base_view(game) is server.map_base_view(game)  # 同一把鍵：同一份物件，不重畫（沒有人別的版本）


# ── 5. 玩法說明列十八張表：危險度的交代在表後面 ──


def test_the_howto_says_dangerous_places_give_more_fights_right_after_the_tables():
    game = _game("guan")
    text = game.howto_text().split("**探索**")[1].split("\n")[0]
    assert "官署多事" in text and "河畔多料" in text and "寺觀多悟" in text and "山林多料" in text  # 十八張表照名字列
    assert text.count("危險的地方") == 1
    tail = text.split("野外多敵", 1)[1]
    assert tail.startswith("），危險的地方遇敵多些"), tail[:30]
    assert re.search(r"自家營寨遇敵是跟同袍比劃", text)
