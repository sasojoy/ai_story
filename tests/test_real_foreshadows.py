"""關鍵伏筆的真實內容（計畫 T7b；濃縮版內容表第四節）：11 條鏈、9 樣物品、13 則事件，以及一條從頭到尾的實測。

引擎本身（片段、最後一步、鎖定、天機、官銀、開關）是 T7a 用 fixture 驗的（tests/test_foreshadow.py）；這裡驗的是
content/foreshadows.json 與 content/events/foreshadow_*.json 照內容表轉對了、每一條都做得完。

下面的表是照內容表 4.1～4.5 逐項抄的（不是從 content 反推）。數字都是 1000 人以上那一檔的基準量；
用週末設定（2 人，係數 0.2）跑，所以物品、情誼、糧草的量要過 foreshadow.need 換算。
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from conftest import FixedRandom
from tianxia import calendar, foreshadow, team, timetable
from tianxia.content import load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.events import event_candidates
from tianxia.journal import WORLD_NEWS
from tianxia.state import FigureState, GameState

CONTENT_DIR = Path(__file__).parent.parent / "content"
PLACEHOLDER_TAG = "待joy寫"  # 13 則事件的文字是占位（內容表 4.5：事件文字歸 joy）；事件模型不收多的欄位，所以記在 tags 上

FS_CHAINS = {  # chain: (大事, 陣營, 類型, 戰況看哪條, 片段的大區（4.2）, 片段的來源（4.2）)
    "fs_changshe_guan": ("changshe_fire", "guan", "天時地利", "yingru",
                         ["yingru", "yingru", "luoyang", "yingru"], ["action", "event", "action", "talk"]),
    "fs_changshe_huang": ("changshe_fire", "huang", "推理", "yingru",
                          ["yingru", "yingru", "yingru", "jizhou"], ["action", "action", "event", "talk"]),
    "fs_changshe_haoqiang": ("changshe_fire", "haoqiang", "反直覺抉擇", "yingru",
                             ["yingru", "yingru", "luoyang", "yingru"], ["action", "action", "action", "talk"]),
    "fs_luzhi_guan": ("luzhi_jailed", "guan", "拼圖", "jizhou",
                      ["jizhou", "jizhou", "luoyang", "luoyang"], ["action", "talk", "action", "action"]),
    "fs_luzhi_huang": ("luzhi_jailed", "huang", "累積", "jizhou",
                       ["jizhou", "jizhou", "luoyang", "luoyang"], ["action", "talk", "action", "action"]),
    "fs_luzhi_haoqiang": ("luzhi_jailed", "haoqiang", "情誼", "jizhou",
                          ["luoyang", "yingru", "luoyang", "luoyang"], ["action", "action", "action", "talk"]),
    "fs_wancheng_guan": ("wancheng", "guan", "情誼", "nanyang",
                         ["nanyang", "nanyang", "yingru", "yingru"], ["action", "talk", "talk", "action"]),
    "fs_wancheng_huang": ("wancheng", "huang", "累積", "nanyang",
                          ["nanyang", "nanyang", "yingru", "nanyang"], ["action", "talk", "action", "action"]),
    "fs_wancheng_haoqiang": ("wancheng", "haoqiang", "天時地利", "nanyang",
                             ["nanyang", "nanyang", "luoyang", "nanyang"], ["action", "action", "action", "event"]),
    "fs_zhangjiao_guan": ("zhangjiao_dies", "guan", "推理", "jizhou",
                          ["jizhou", "jizhou", "yingru", "jizhou"], ["action", "talk", "action", "action"]),
    "fs_zhangjiao_huang": ("zhangjiao_dies", "huang", "拼圖", "jizhou",
                           ["jizhou", "jizhou", "nanyang", "nanyang"], ["action", "talk", "action", "event"]),
}
FS_INVALID_IF = {  # 4.1 的 invalid_if；沒列的沒有
    "fs_changshe_huang": "bocai", "fs_luzhi_guan": "luzhi", "fs_luzhi_huang": "luzhi",
    "fs_wancheng_guan": "sunjian", "fs_wancheng_huang": "zhaohong", "fs_zhangjiao_huang": "zhangjiao",
}
FS_TALKS = {  # (chain, 片段序號 0 起): (人物, 接手的人, 話題標籤, 情誼門檻的基準量)（4.2）
    ("fs_changshe_guan", 3): ("huangfusong", "zhujun", "問起破敵之策", 20),
    ("fs_changshe_huang", 3): ("zhangliang", None, "問起兵法", 0),
    ("fs_changshe_haoqiang", 3): ("caocao", None, "談起糧草", 0),
    ("fs_luzhi_guan", 1): ("luzhi", None, "問起監軍", 0),
    ("fs_luzhi_huang", 1): ("zhangbao", None, "問起洛陽", 0),
    ("fs_luzhi_haoqiang", 3): ("yuanshao", None, "談起時局", 0),
    ("fs_wancheng_guan", 1): ("sunjian", None, "問起江東", 0),
    ("fs_wancheng_guan", 2): ("zhujun", None, "問起南陽", 0),
    ("fs_wancheng_huang", 1): ("zhaohong", None, "問起糧", 0),
    ("fs_zhangjiao_guan", 1): ("luzhi", "dongzhuo", "問起廣宗", 0),
    ("fs_zhangjiao_huang", 1): ("zhangliang", None, "問起大哥", 0),
}
FS_ITEMS = {
    "fs_reeds": "葦束", "fs_oil": "膏油", "fs_dry_reeds": "長社的乾葦", "fs_blood_letter": "郡守的血書",
    "fs_ledger": "渡口的貨帳", "fs_witness": "宮中的證人", "fs_herb": "嵩陰草", "fs_ash": "丹爐灰", "fs_fungus": "淯水白苓",
}
FS_EVENTS = {  # 4.5：事件 id → (地點, 只對誰出現；空的是不分陣營)
    "fs_ev_boatman": (["yingshui"], []),
    "fs_ev_xinye_doctor": (["xinye"], ["huang"]),
    "fs_ev_xinye_clerk": (["xinye"], ["haoqiang"]),
    "fs_ev_two_buyers": (["runan_market"], ["haoqiang"]),
    "fs_prep_reeds": (["yingshui", "yingchuan_wilds"], ["guan"]),
    "fs_prep_oil": (["runan_market"], ["guan"]),
    "fs_prep_dry_reeds": (["changshe"], ["huang"]),
    "fs_prep_blood_letter": (["haozu_fort"], ["guan"]),
    "fs_prep_ledger": (["mengjin_ford"], ["guan"]),
    "fs_prep_witness": (["luoyang_palace"], ["guan"]),
    "fs_prep_herb": (["deep_mountain"], ["huang"]),
    "fs_prep_ash": (["jade_cave"], ["huang"]),
    "fs_prep_fungus": (["yu_river"], ["huang"]),
}
WIND, DISGUISE = "wind", "disguise"  # 答案寫天機的 key；執行時換成這一季的答案
FS_ANSWERS = {  # 單趟的鏈：答對的選項 id（依序，每一題一個）
    "fs_changshe_guan": [WIND], "fs_changshe_huang": [WIND], "fs_luzhi_guan": ["2"], "fs_luzhi_huang": ["1"],
    "fs_luzhi_haoqiang": ["1"], "fs_wancheng_guan": ["1", "東北角"], "fs_wancheng_huang": [], "fs_wancheng_haoqiang": ["1"],
    "fs_zhangjiao_guan": [DISGUISE], "fs_zhangjiao_huang": ["2"],
}


ALL_EVENTS: dict = {}  # meet 會把 content.events 換成只剩一則（測完還原）；全部的事件留在這裡，同一個測試裡可以連著遇上不同的事件


@pytest.fixture(scope="module")
def fs_content():
    c = load_content(CONTENT_DIR, profile="weekend")
    c.config.auto_open_first_season = True  # 這一組測的是開打後的內容
    ALL_EVENTS.update(c.events)
    return c


@pytest.fixture(scope="module")
def off_content():
    c = load_content(CONTENT_DIR)  # 正式設定：第一季開關是關的
    c.config.auto_open_first_season = True
    return c


def fs_chain(c, chain_id: str):
    return next(ch for ch in c.foreshadows.chains if ch.id == chain_id)


def cal(c, week: int, weekday: int = 0, hour: int = 0, minute: int = 0) -> float:
    """季曆第 week 週、週 weekday（0＝週一）的 hour:minute 是第幾個世界秒。"""
    return calendar.week_start(week, c) + ((weekday * 24 + hour) * 60 + minute) * 60 / calendar.cal_scale(c)


def fs_game(c, world, name: str, faction: str | None, at: str, *, rng=None, time: float | None = None) -> Game:
    game = Game.new(c, name, rng=rng or random.Random(0), world=world)
    p = game.state.player
    p.faction, p.location = faction, at
    p.visited.add(at)
    if time is not None:
        game.state.world.time = time
    return game


def fs_option(game: Game, option_id: str):
    return next((o for o in game.options() if o.id == option_id), None)


def fs_window_time(c, game: Game, chain) -> float:
    """這條鏈最後一步做得了的一刻：大事前 7 天的時間窗裡（夜裡的鏈在夜裡）；新野那條是決戰集結開始之後。"""
    event = next(e for e in c.timetable if e.id == chain.event)
    at = timetable.when(game.state, c, event)
    if chain.final.window == "during_muster":
        return at + 1
    day = calendar.point(at - 3 * 86400 / calendar.cal_scale(c), c, game.state.world)  # 大事前三個曆日那一天
    return cal(c, day.week, day.weekday, 0 if chain.final.night else 12, 30)


def fs_prepare(c, game: Game, chain) -> None:
    """給足這條鏈要的東西（照換算後的量）：伏筆物品、糧草（一階慢屬性素材，一份一個）、捐獻、情誼、計數；any_of 取第一組。"""
    p = game.state.player
    for req in [chain.final.requires, *(t.requires for t in chain.final.steps)]:
        for r in [req, *req.any_of[:1]]:
            for item, n in r.clue_items.items():
                p.clue_items[item] = p.clue_items.get(item, 0) + foreshadow.need(c, n)
            if r.grain:
                p.materials["man_1"] = p.materials.get("man_1", 0) + foreshadow.need(c, r.grain)
            for key, n in r.donations.items():
                p.donations[key] = max(p.donations.get(key, 0), foreshadow.need(c, n))
            for key, n in r.affinity.items():
                p.affinities[key] = max(p.affinities.get(key, 0), foreshadow.need(c, n))
            for key, n in r.counters.items():
                p.fs_counters[key] = max(p.fs_counters.get(key, 0), foreshadow.need(c, n))


def fs_ready(c, world, chain_id: str, name: str = "甲", *, give: bool = True, rng=None) -> Game:
    """站在那條鏈最後一步的地點、陣營對、時間窗裡，手上有（give）這條鏈要的東西的玩家。"""
    chain = fs_chain(c, chain_id)
    trip = foreshadow.trips(chain.final)[0]
    game = fs_game(c, world, name, chain.side, trip.location, rng=rng)
    game.state.world.time = fs_window_time(c, game, chain)
    if give:
        fs_prepare(c, game, chain)
    return game


def fs_answer(world, answer: str) -> str:
    """天機的 key 換成這一季的答案，選項 id 照舊。"""
    return foreshadow.tianji_answer(world.read().tianji, answer) if answer in (WIND, DISGUISE) else answer


def fs_run(world, game: Game, chain_id: str, answers: list[str]) -> list[str]:
    """按下 fs:<鏈> 看題，依序答 answers（沒有題的鏈按一下就做完）；回傳最後一下的訊息。"""
    msgs = game.choose(f"fs:{chain_id}")
    for answer in answers:
        msgs = game.choose(f"fs:{chain_id}:{fs_answer(world, answer)}")
    return msgs


def candidates(c, game: Game) -> list:
    return event_candidates(game.state, c, "explore", "common")


def meet(c, game: Game, event_id: str, monkeypatch) -> None:
    """讓這個角色在腳下的地點探索時，一定遇上指定的事件（只留那一則、事件那一支必中、不抽奇遇）。"""
    monkeypatch.setattr(c, "events", {event_id: ALL_EVENTS[event_id]})
    monkeypatch.setattr(c.config, "rare_explore_chance", 0.0)
    for mix in c.config.explore_mix:
        monkeypatch.setattr(mix, "weights", {"event": 1})
    game.state.player.stamina = 150
    game.choose("act:explore")
    assert game.state.pending_event == event_id


# ── 內容對得上表 ─────────────────────────────────────────


def test_real_foreshadows_valid(fs_content):
    """11 條的地點、人物、物品、事件都存在（content.validate 載入時已經查過）；每條 4 片；片段的大區與來源照 4.2；
    13 則事件與 9 樣物品都在；天機的兩個 key 都有人用。"""
    c, fs = fs_content, fs_content.foreshadows
    assert [ch.id for ch in fs.chains] == list(FS_CHAINS) and len(fs.chains) == 11
    timetable_ids = {e.id for e in c.timetable}
    for ch in fs.chains:
        event, side, kind, front, regions, sources = FS_CHAINS[ch.id]
        assert (ch.event, ch.side, ch.kind, ch.front) == (event, side, kind, front), ch.id
        assert event in timetable_ids
        assert len(ch.fragments) == 4, ch.id
        assert [f.region for f in ch.fragments] == regions, ch.id
        assert [f.source for f in ch.fragments] == sources, ch.id
        assert ch.invalid_if.figure_out == FS_INVALID_IF.get(ch.id), ch.id
        for trip in foreshadow.trips(ch.final):
            assert trip.location in c.locations
    assert {i.id: i.name for i in fs.items} == FS_ITEMS and len(fs.items) == 9
    assert foreshadow.event_ids(c) == set(FS_EVENTS)  # 13 則事件，而且每一則開關關著時都被藏起來（不多也不少）
    for event_id, (locations, sides) in FS_EVENTS.items():
        event = c.events[event_id]
        assert (event.locations, event.condition.factions, event.actions) == (locations, sides, ["explore"]), event_id
    answers = {ask.answer for ch in fs.chains for _, ask in foreshadow.asks_of(ch)}
    assert {"tianji:wind", "tianji:disguise"} <= answers  # 風向、藥車偽裝都有人考
    texts = [f.text for ch in fs.chains for f in ch.fragments]
    assert any("{風向}" in t for t in texts) and any("{偽裝}" in t for t in texts)
    assert fs.guanyin is not None and (fs.guanyin.side, fs.guanyin.squad_faction) == ("huang", "guan")
    assert fs.guanyin.regions == ["jizhou", "yingru"] and fs.guanyin.text


def test_real_talk_and_event_fragments_follow_table_4_2(fs_content):
    """11 則對話片段：誰說、誰接手、話題標籤、情誼門檻（基準量）；4 則事件片段：來自哪一則事件。"""
    chains = fs_content.foreshadows.chains
    talks = {
        (ch.id, i): (f.character, f.stand_in, f.topic, f.affinity_min)
        for ch in chains for i, f in enumerate(ch.fragments) if f.source == "talk"
    }
    assert talks == FS_TALKS
    events = {(ch.id, i): f.event for ch in chains for i, f in enumerate(ch.fragments) if f.source == "event"}
    assert events == {
        ("fs_changshe_guan", 1): "fs_ev_boatman", ("fs_changshe_huang", 2): "fs_ev_boatman",
        ("fs_wancheng_haoqiang", 3): "fs_ev_xinye_clerk", ("fs_zhangjiao_huang", 3): "fs_ev_xinye_doctor",
    }


def test_real_final_steps_follow_table_4_3(fs_content):
    """11 條最後一步的地點、夜裡、需要的東西、正解、懲罰（內容表 4.3；數字是基準量）。"""
    f = {ch.id: ch.final for ch in fs_content.foreshadows.chains}
    assert all(x.window_days == 7 and x.window == "before_event" and x.front_rule == "side"
               for cid, x in f.items() if cid != "fs_wancheng_haoqiang")
    g = f["fs_changshe_guan"]
    assert (g.location, g.night, g.requires.clue_items, g.answer) == ("changshe", True, {"fs_reeds": 3, "fs_oil": 2}, "tianji:wind")
    assert [o.id for o in g.options] == list("東南西北") and g.wrong.lose_items == ["fs_reeds", "fs_oil"]
    assert (g.figure, g.stand_in) == ("huangfusong", "zhujun") and "{人物}" in g.success_text
    h = f["fs_changshe_huang"]
    assert (h.location, h.night, h.answer) == ("huangjin_camp", False, "tianji:wind")
    assert [(r.clue_items, r.affinity) for r in h.requires.any_of] == [({"fs_dry_reeds": 1}, {}), ({}, {"bocai": 30})]
    assert h.unready == "官軍縮在城裡，我還怕他放火？" and h.wrong.affinity == {"bocai": -5}
    b = f["fs_changshe_haoqiang"]
    assert b.requires.counters == {"two_buyers": 1} and b.location is None
    assert [(t.location, t.requires.grain, t.requires.check.stat, t.requires.check.dc, t.wrong.lose_grain) for t in b.steps] == [
        ("changshe", 4, "wis", 6, True), ("huangjin_camp", 4, "agi", 6, True),
    ]
    lg = f["fs_luzhi_guan"]
    assert (lg.location, lg.requires.clue_items, lg.answer) == (
        "dajiangjun_fu", {"fs_blood_letter": 1, "fs_ledger": 1, "fs_witness": 1}, "2")
    assert [o.wrong.lose_items if o.wrong else None for o in lg.options] == [[], None, ["fs_witness"]]
    lh = f["fs_luzhi_huang"]
    assert (lh.location, lh.requires.counters, lh.answer) == ("baima_temple", {"guanyin": 5}, "1")
    assert [o.wrong.cooldown_days if o.wrong else None for o in lh.options] == [None, 0, 1]
    lq = f["fs_luzhi_haoqiang"]
    assert (lq.location, lq.requires.affinity, lq.answer) == ("dajiangjun_fu", {"yuanshao": 40}, "1")
    assert [o.wrong.affinity if o.wrong else None for o in lq.options] == [None, {"yuanshao": -5}, {"yuanshao": -5}]
    wg = f["fs_wancheng_guan"]
    assert (wg.location, wg.requires.affinity, wg.answer) == ("wan_city", {"sunjian": 50}, "1")
    assert [o.wrong.affinity if o.wrong else None for o in wg.options] == [None, {"sunjian": -5}, {"sunjian": -5}]
    assert [(a.answer, [o.id for o in a.options]) for a in wg.then] == [("東北角", ["東北角", "正門", "西牆"])]
    assert wg.wrong.affinity == {"sunjian": -5} and set(wg.success_versions) == {"甲", "乙"}
    wh = f["fs_wancheng_huang"]
    assert (wh.location, wh.requires.donations, wh.question) == ("nanyang_huangjin_camp", {"nanyang_huangjin_camp:糧草": 24}, "")
    wq = f["fs_wancheng_haoqiang"]
    assert (wq.location, wq.window, wq.requires.grain, wq.answer) == ("xinye", "during_muster", 4, "1")
    zg = f["fs_zhangjiao_guan"]
    assert (zg.location, zg.answer, zg.wrong.cooldown_days) == ("baima_ford", "tianji:disguise", 1)
    assert [o.id for o in zg.options] == ["鹽車", "棺木", "香客", "商隊"] and "{偽裝}" in zg.success_text
    zh = f["fs_zhangjiao_huang"]
    assert (zh.location, zh.requires.clue_items, zh.answer, zh.wrong.lose_all) == (
        "guangzong", {"fs_herb": 1, "fs_ash": 1, "fs_fungus": 1}, "2", True)


def test_tianji_slots_are_filled_in_every_fragment_and_final_text(fs_content, world):
    """{風向}、{偽裝}、{人物} 在片段與最後一步的文字裡都填好，不留大括號。"""
    c = fs_content
    game = fs_game(c, world, "甲", "guan", "changshe")
    for ch in c.foreshadows.chains:
        texts = [f.text for f in ch.fragments] + [t for f in ch.fragments for t in f.versions.values()]
        for trip in foreshadow.trips(ch.final):
            texts += [trip.question, trip.success_text, trip.wrong.text, trip.unready, trip.label]
            texts += [o.text for o in trip.options] + [o.wrong.text for o in trip.options if o.wrong]
            texts += [t for ask in trip.then for t in (ask.question, *(o.text for o in ask.options))]
        texts += [ch.final.success_text, *ch.final.success_versions.values()]
        for text in texts:
            filled = foreshadow.fill(game.state, c, ch, text, world)
            assert "{" not in filled and "}" not in filled, (ch.id, text)
    tianji = world.read().tianji
    boatman, ferry = fs_chain(c, "fs_changshe_guan"), fs_chain(c, "fs_zhangjiao_guan")
    assert foreshadow.tianji_answer(tianji, "wind") in foreshadow.fill(game.state, c, boatman, boatman.fragments[1].text, world)
    assert foreshadow.tianji_answer(tianji, "disguise") in foreshadow.fill(game.state, c, ferry, ferry.fragments[3].text, world)


# ── 片段從哪裡聽到 ───────────────────────────────────────


def test_every_action_fragment_is_heard_by_its_own_side_in_its_own_region(fs_content, world):
    """行動來源的片段：那一陣營的人在那個大區花體力之後聽得到（其他大區聽不到）；寫成「你聽到一件事：…」。"""
    c = fs_content
    assert len(c.foreshadows.chains) == 11
    for ch in c.foreshadows.chains:
        for i, f in enumerate(ch.fragments):
            if f.source != "action":
                continue
            game = fs_game(c, world, f"{ch.id}{i}", ch.side, "yingchuan")
            game.state.player.fragments = {  # 這一陣營其他的片段都聽過了：只剩這一則
                other.id: [j for j in range(4) if (other.id, j) != (ch.id, i)]
                for other in c.foreshadows.chains if other.side == ch.side
            }
            heard = foreshadow.hear_after_action(game.state, c, f.region, FixedRandom(0.0), world)
            assert heard == [f"你聽到一件事：{foreshadow.fill(game.state, c, ch, f.text, world)}"], (ch.id, i)
            assert foreshadow.hear_after_action(game.state, c, "youzhou", FixedRandom(0.0), world) == []  # 幽州一則片段也沒有
    stranger = fs_game(c, world, "路人", None, "yingchuan")
    assert foreshadow.hear_after_action(stranger.state, c, "yingru", FixedRandom(0.0), world) == []  # 散人什麼都聽不到


def test_event_fragments_go_to_the_sides_that_can_use_them(fs_content, world):
    """老船夫對官軍、黃巾各說一則（同一則事件）；新野老醫只對黃巾、老縣吏只對豪強；其他人什麼都沒有。"""
    c = fs_content
    guan, huang, hao, loner = (
        fs_game(c, world, n, f, "yingshui") for n, f in (("甲", "guan"), ("乙", "huang"), ("丙", "haoqiang"), ("丁", None))
    )
    wind = foreshadow.tianji_answer(world.read().tianji, "wind")
    assert foreshadow.hear_from_event(guan.state, c, "fs_ev_boatman", world) == [
        f"你聽到一件事：「這時節的大風，都是半夜從{wind}邊刮過來的，刮起來連船都拴不住。」"]
    assert foreshadow.hear_from_event(huang.state, c, "fs_ev_boatman", world) == [
        f"你聽到一件事：「前兩天官軍把我叫去，問的全是颳風的事。這時節夜裡的風都從{wind}邊來。」"]
    assert foreshadow.hear_from_event(hao.state, c, "fs_ev_boatman", world) == []
    assert foreshadow.hear_from_event(loner.state, c, "fs_ev_boatman", world) == []
    assert foreshadow.hear_from_event(huang.state, c, "fs_ev_xinye_doctor", world) == [
        "你聽到一件事：「這方子要三味：嵩山背陰崖下的草、南華觀丹爐裡的灰、淯水的白苓。先煎苓，後下草，灰化在符水裡。順序錯了就是毒。」"]
    assert foreshadow.hear_from_event(hao.state, c, "fs_ev_xinye_clerk", world) == [
        "你聽到一件事：「誰能讓縣裡的人吃上飯，冊子就交給誰。」"]
    assert foreshadow.hear_from_event(guan.state, c, "fs_ev_xinye_doctor", world) == []
    assert foreshadow.hear_from_event(guan.state, c, "fs_ev_xinye_clerk", world) == []


def test_talk_fragments_are_offered_by_the_right_person_at_the_right_affinity(fs_content, world):
    """每一則對話片段：那位人物在對話裡多一個固定選項，標籤是話題；情誼照換算（皇甫嵩 20 → 4，其餘不設門檻）；只說一次。"""
    c = fs_content
    for (chain_id, i), (speaker, _stand_in, topic, base) in FS_TALKS.items():
        ch = fs_chain(c, chain_id)
        game = fs_game(c, world, f"{chain_id}{i}", ch.side, c.characters[speaker].talk_at)
        p = game.state.player
        p.affinities[speaker] = foreshadow.need(c, base) - 1 if base else 0
        offered = {o.id: o.label for o in foreshadow.talk_options(game.state, c, speaker)}
        if base:
            assert f"talk:clue:{chain_id}:{i}" not in offered  # 情誼還差一點
            p.affinities[speaker] = foreshadow.need(c, base)
            offered = {o.id: o.label for o in foreshadow.talk_options(game.state, c, speaker)}
        assert offered[f"talk:clue:{chain_id}:{i}"] == topic, (chain_id, i)
        said = foreshadow.hear_talk(game.state, c, speaker, chain_id, i, world)
        assert said == [f"{c.characters[speaker].name}說：{foreshadow.fill(game.state, c, ch, ch.fragments[i].text, world)}"]
        assert foreshadow.hear_talk(game.state, c, speaker, chain_id, i, world) == []  # 只說一次
    other_side = fs_game(c, world, "路人", "huang", "changshe")
    other_side.state.player.affinities["huangfusong"] = 50
    assert foreshadow.talk_options(other_side.state, c, "huangfusong") == []  # 不是官軍：皇甫嵩不對他說


def test_zhangjiao_guan_talk_goes_to_dongzhuo_once_luzhi_is_jailed(fs_content, world):
    """冀州官軍主將的片段：盧植在時盧植說；盧植下獄後改由董卓說（T7a 的裁定 6，內容表 4.2）。"""
    c = fs_content
    game = fs_game(c, world, "甲", "guan", "mengjin_ford")
    assert foreshadow.talk_options(game.state, c, "dongzhuo") == []
    assert [o.id for o in foreshadow.talk_options(game.state, c, "luzhi")] == [
        "talk:clue:fs_luzhi_guan:1", "talk:clue:fs_zhangjiao_guan:1",  # 盧植自己的「問起監軍」也在
    ]
    game.state.world.figures["luzhi"] = FigureState(status="jailed")
    assert [o.id for o in foreshadow.talk_options(game.state, c, "dongzhuo")] == ["talk:clue:fs_zhangjiao_guan:1"]
    assert foreshadow.talk_options(game.state, c, "luzhi") == []
    assert foreshadow.hear_talk(game.state, c, "dongzhuo", "fs_zhangjiao_guan", 1, world) == ["董卓說：「張角的藥要是斷了，廣宗不攻自破。」"]
    assert foreshadow.talk_options(game.state, c, "dongzhuo") == []


# ── 最後一步：每一條都做得完 ─────────────────────────────


@pytest.mark.parametrize("chain_id", list(FS_ANSWERS))
def test_every_single_trip_chain_completes_with_the_right_answer(fs_content, world, chain_id):
    """十條單趟的鏈（天時地利、推理、拼圖、累積、情誼各種）：備齊東西、在時間窗裡、答對 → 完成、記做完、記貢獻、鎖定或寫第三方。
    官軍與黃巾寫 locks（鎖那件大事），豪強寫 third_party、不碰 locks。"""
    c = fs_content
    chain = fs_chain(c, chain_id)
    game = fs_ready(c, world, chain_id)
    opt = fs_option(game, f"fs:{chain_id}")
    assert opt is not None and opt.enabled and opt.label == chain.final.label
    msgs = fs_run(world, game, chain_id, FS_ANSWERS[chain_id])
    done = chain.final.success_versions.get("甲", chain.final.success_text)  # 張曼成的那件還沒結算：宛城用史書那一版（甲）
    assert foreshadow.fill(game.state, c, chain, done, world) in msgs
    assert chain_id in game.state.player.fs_done and game.state.player.contrib == c.config.foreshadow_contrib
    season = world.get_season()
    if chain.side == "haoqiang":
        assert season.third_party[chain.event] == ["甲"] and chain.event not in season.locks
    else:
        assert (season.locks[chain.event].side, season.locks[chain.event].name) == (chain.side, "甲")


def test_changshe_guan_hands_over_the_scaled_amounts_and_names_the_commander(fs_content, world):
    """葦束 3、膏油 2 在週末設定是各 1；{人物} 在皇甫嵩還在潁川時是皇甫嵩，重挫轉往冀州後是朱儁。"""
    c = fs_content
    assert (foreshadow.need(c, 3), foreshadow.need(c, 2)) == (1, 1)
    game = fs_ready(c, world, "fs_changshe_guan", give=False)
    p = game.state.player
    assert fs_option(game, "fs:fs_changshe_guan").label == "束苣乘城（東西還沒備齊）"
    p.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    wind = fs_answer(world, WIND)
    assert fs_run(world, game, "fs_changshe_guan", [WIND]) == [
        f"▸ {wind}", "你把葦束膏油交進營中，又在沙盤上畫了風向。皇甫嵩看了很久，只說：「就等那一夜。」", "葦束 -1", "膏油 -1",
    ]
    other = fs_ready(c, world, "fs_changshe_guan", "乙")
    other.state.world.figures["huangfusong"] = FigureState(status="active", front="jizhou")
    assert fs_run(world, other, "fs_changshe_guan", [WIND])[1] == (
        "你把葦束膏油交進營中，又在沙盤上畫了風向。朱儁看了很久，只說：「就等那一夜。」"
    )


def test_changshe_guan_is_only_at_night(fs_content, world):
    c = fs_content
    game = fs_ready(c, world, "fs_changshe_guan")
    game.state.world.time = cal(c, 5, 4, 12)  # 時間窗裡、白天
    assert fs_option(game, "fs:fs_changshe_guan").label == "束苣乘城（時候未到）"
    game.state.world.time = fs_window_time(c, game, fs_chain(c, "fs_changshe_guan"))
    assert fs_option(game, "fs:fs_changshe_guan").enabled


def test_changshe_haoqiang_two_trips_and_two_checks(fs_content, world):
    """反直覺抉擇：起點「兩邊都賣」寫了計數才能做；長社智力檢定、黃巾別部營寨敏捷檢定，兩趟都成才完成（寫第三方）；
    檢定失敗沒收那一趟的糧草、可以再來。"""
    c = fs_content
    chain = fs_chain(c, "fs_changshe_haoqiang")
    game = fs_ready(c, world, "fs_changshe_haoqiang", give=False, rng=FixedRandom(0.99))
    p = game.state.player
    p.materials = {"man_1": 2}
    assert fs_option(game, "fs:fs_changshe_haoqiang").label == "交糧（東西還沒備齊）"  # 沒有「兩邊都賣」的起點
    p.fs_counters = {"two_buyers": 1}
    assert game.choose("fs:fs_changshe_haoqiang") == ["（本人——失敗）", chain.final.steps[0].wrong.text, "沉淵石 -1"]
    assert p.materials == {"man_1": 1} and p.fs_done == []
    p.materials = {"man_1": 2}
    game.rng = FixedRandom(0.0)
    assert game.choose("fs:fs_changshe_haoqiang") == ["（本人——成功）", chain.final.steps[0].success_text, "沉淵石 -1"]
    assert p.fs_done == ["fs_changshe_haoqiang:0"] and fs_option(game, "fs:fs_changshe_haoqiang") is None
    p.location = "huangjin_camp"
    assert game.choose("fs:fs_changshe_haoqiang") == ["（本人——成功）", chain.final.success_text, "沉淵石 -1"]
    assert "fs_changshe_haoqiang" in p.fs_done and world.get_season().third_party["changshe_fire"] == ["甲"]


def test_two_buyers_event_only_the_last_choice_opens_the_chain(fs_content, world, monkeypatch):
    """汝南集市的「兩路買家」：第 4～6 週只對豪強出現；四個選項只有「兩邊都賣」寫 two_buyers。"""
    c = fs_content
    event = c.events["fs_ev_two_buyers"]
    assert event.choices[-1].text == "兩邊都賣，誰也別讓誰知道" and len(event.choices) == 4
    assert [bool(ch.effect.fs_counters) for ch in event.choices] == [False, False, False, True]
    assert event.choices[-1].effect.fs_counters == {"two_buyers": 1}
    assert (event.condition.week_min, event.condition.week_max) == (4, 6)
    for i in range(4):
        game = fs_game(c, world, f"豪{i}", "haoqiang", "runan_market", time=cal(c, 5))
        meet(c, game, "fs_ev_two_buyers", monkeypatch)
        game.choose(f"choice:{i}")
        assert game.state.player.fs_counters == ({"two_buyers": 1} if i == 3 else {})
    assert event not in candidates(c, fs_game(c, world, "豪早", "haoqiang", "runan_market", time=cal(c, 3)))  # 第 3 週還不出現
    assert event not in candidates(c, fs_game(c, world, "豪晚", "haoqiang", "runan_market", time=cal(c, 7)))
    assert event not in candidates(c, fs_game(c, world, "官", "guan", "runan_market", time=cal(c, 5)))


# ── 答錯的代價 ───────────────────────────────────────────


def test_wrong_answers_cost_what_the_table_says(fs_content, world):
    """4.3 最後一欄：長社官軍收走物品、黃巾 −5 情誼、盧植官軍③收走證人、盧植黃巾③ 要等一天、袁紹 −5、孫堅 −5（兩問都算）、
    新野糧草留著、張角官軍等一天、南華良藥三味作廢。"""
    c = fs_content

    def attempt(chain_id, answers, *, tweak=None, give=True):
        game = fs_ready(c, world, chain_id, give=give)
        if tweak:
            tweak(game.state.player)
        return game, fs_run(world, game, chain_id, answers)

    wind = fs_answer(world, WIND)
    wrong_wind = next(d for d in "東南西北" if d != wind)
    game, msgs = attempt("fs_changshe_guan", [wrong_wind])
    assert msgs == [f"▸ {wrong_wind}", "軍司馬搖頭：「這一面放火，燒的是我們自己。」", "葦束 -1", "膏油 -1"]
    assert game.state.player.clue_items == {} and game.state.player.fs_done == []

    game, msgs = attempt("fs_changshe_huang", [wrong_wind], give=False, tweak=lambda p: p.affinities.update(bocai=10))
    assert msgs == [f"▸ {wrong_wind}", "「挪到那邊？官軍做夢都要笑醒。」", "波才情誼 -5"] and game.state.player.affinities["bocai"] == 5
    bare = fs_ready(c, world, "fs_changshe_huang", "乙", give=False)
    assert fs_option(bare, "fs:fs_changshe_huang").label == "勸營（官軍縮在城裡，我還怕他放火？）"
    assert not fs_option(bare, "fs:fs_changshe_huang").enabled  # 乾葦與波才的情誼兩樣都沒有

    items = {"fs_blood_letter": 1, "fs_ledger": 1, "fs_witness": 1}
    game, msgs = attempt("fs_luzhi_guan", ["1"])
    assert msgs[1] == "何進聳聳肩，把證物退還給你。" and game.state.player.clue_items == items
    game, msgs = attempt("fs_luzhi_guan", ["3"])
    assert msgs[-1] == "宮中的證人 -1" and game.state.player.clue_items == {"fs_blood_letter": 1, "fs_ledger": 1}

    game, msgs = attempt("fs_luzhi_huang", ["2"])
    assert msgs == ["▸ 直接把包袱塞給他", "他裝作不認識你。"] and fs_option(game, "fs:fs_luzhi_huang").enabled
    game, msgs = attempt("fs_luzhi_huang", ["3"])
    assert msgs[1] == "他嚇得跑了，一個遊戲日內不會再出現。"
    assert fs_option(game, "fs:fs_luzhi_huang").label == "黃圈（時候未到）"
    game.state.world.time += 86400 / calendar.cal_scale(c)  # 過一個曆日
    assert fs_option(game, "fs:fs_luzhi_huang").enabled

    for answer in ("2", "3"):
        game, msgs = attempt("fs_luzhi_haoqiang", [answer], tweak=lambda p: p.affinities.update(yuanshao=20))
        assert msgs[-1] == "袁紹情誼 -5" and game.state.player.affinities["yuanshao"] == 15 and game.state.player.fs_done == []

    for answers in (["2"], ["3"], ["1", "正門"], ["1", "西牆"]):
        game, msgs = attempt("fs_wancheng_guan", answers, tweak=lambda p: p.affinities.update(sunjian=20))
        assert msgs[-1] == "孫堅情誼 -5" and game.state.player.affinities["sunjian"] == 15 and game.state.player.fs_done == []
        assert fs_option(game, "fs:fs_wancheng_guan").enabled  # 可以再來

    game, msgs = attempt("fs_wancheng_haoqiang", ["2"])
    assert msgs == ["▸ 帶人進縣衙直接拿冊子", "老吏把冊子扔進火盆，這次不算。"] and game.state.player.materials == {"man_1": 1}

    wrong_disguise = next(d for d in ("鹽車", "棺木", "香客", "商隊") if d != fs_answer(world, DISGUISE))
    game, msgs = attempt("fs_zhangjiao_guan", [wrong_disguise])
    assert msgs[1] == "什麼都沒搜到。" and fs_option(game, "fs:fs_zhangjiao_guan").label == "盤查（時候未到）"

    for answer in ("1", "3"):
        game, msgs = attempt("fs_zhangjiao_huang", [answer])
        assert msgs[-3:] == ["嵩陰草 -1", "丹爐灰 -1", "淯水白苓 -1"] and game.state.player.clue_items == {}


def test_wancheng_guan_reads_the_version_the_week_three_roll_picked(fs_content, world):
    """宛城官軍的完成敘事分甲、乙兩版（看第 3 週張曼成那一擲）；第 3 週還沒結算時用史書那一版（甲）。"""
    c = fs_content
    chain = fs_chain(c, "fs_wancheng_guan")
    assert chain.final.success_versions["甲"].startswith("孫堅大笑，拍著你的肩：「好！東北角，雞鳴時分，你帶人跟緊了。」")
    assert chain.final.success_versions["乙"].startswith("孫堅把繩子在手上繞了兩圈：「下雨那夜，東北角，你帶人跟緊了。」")
    game = fs_ready(c, world, "fs_wancheng_guan", "官未")  # 先做：之後的角色把第 3 週的結果存進了共用的賽季
    assert chain.final.success_versions["甲"] in fs_run(world, game, "fs_wancheng_guan", ["1", "東北角"])
    for key, version in (("成", "甲"), ("不成", "乙")):
        game = fs_ready(c, world, "fs_wancheng_guan", f"官{version}")
        game.state.world.timeline["zhangmancheng_wan"] = timetable.TimelineResult(key=key, time=0.0)
        assert chain.final.success_versions[version] in fs_run(world, game, "fs_wancheng_guan", ["1", "東北角"])
    huang = fs_chain(c, "fs_wancheng_huang").fragments[3]
    assert huang.versions["甲"].startswith("城裡的人說，官軍圍城最怕拖") and huang.text == huang.versions["甲"]
    assert huang.versions["乙"].startswith("圍城的弟兄說，城裡的糧比我們少")


def test_wancheng_huang_counts_only_donations_to_the_huang_camp(fs_content, world):
    """替趙弘囤糧：只讀 donations["nanyang_huangjin_camp:糧草"]（24 → 週末 5 份），不夠按不下去；達到門檻按一下就點糧。"""
    c = fs_content
    game = fs_ready(c, world, "fs_wancheng_huang", give=False)
    p = game.state.player
    assert foreshadow.need(c, 24) == 5
    p.donations = {"nanyang_huangjin_camp:糧草": 4}
    assert not fs_option(game, "fs:fs_wancheng_huang").enabled
    p.donations = {"nanyang_huangjin_camp:糧草": 5}
    assert fs_option(game, "fs:fs_wancheng_huang").enabled
    assert game.choose("fs:fs_wancheng_huang") == [fs_chain(c, "fs_wancheng_huang").final.success_text]
    assert p.donations == {"nanyang_huangjin_camp:糧草": 5}  # 捐獻不扣


def test_wancheng_haoqiang_only_opens_once_the_showdown_musters(fs_content, world):
    """新野的冊子：決戰排定的時間到了（集結中或開打後）才做得了，不是大事前 7 天；糧草 4（週末 1）交出去。"""
    c = fs_content
    chain = fs_chain(c, "fs_wancheng_haoqiang")
    game = fs_ready(c, world, "fs_wancheng_haoqiang")
    at = timetable.when(game.state, c, next(e for e in c.timetable if e.id == "wancheng"))
    game.state.world.time = at - 5
    assert fs_option(game, "fs:fs_wancheng_haoqiang").label == "接冊（時候未到）"
    game.state.world.time = at + 5
    assert game.choose("fs:fs_wancheng_haoqiang") == [chain.final.question]
    assert game.choose("fs:fs_wancheng_haoqiang:1") == ["▸ 開倉放糧，讓縣裡的人自己推你", chain.final.success_text, "沉淵石 -1"]
    assert game.state.player.materials == {}


# ── 官銀 ─────────────────────────────────────────────────


def test_guanyin_on_a_real_win_against_the_guan_squad(fs_content, world, monkeypatch):
    """黃巾在冀州（盧植營，那裡的對手是官軍）遊歷打贏，30% 得 1 官銀；落敗不算。"""
    c = fs_content
    monkeypatch.setattr(c.config, "train_event_chance", 0.0)
    monkeypatch.setattr(c.config, "train_stat_chance", 0.0)
    monkeypatch.setattr(team, "fight", lambda *a, **k: EncounterResult(tier="大勝", margin=50, our_power=60, difficulty=1))
    huang = fs_game(c, world, "乙", "huang", "luzhi_camp", rng=FixedRandom(0.0), time=cal(c, 7))  # 盧植那件大事還沒到
    huang.choose("act:train")
    assert huang.state.player.fs_counters == {"guanyin": 1}
    assert c.foreshadows.guanyin.text in huang.state.journal[0].lines
    huang.rng = FixedRandom(c.config.guanyin_chance + 0.01)
    huang.state.player.stamina = 150
    huang.choose("act:train")
    assert huang.state.player.fs_counters == {"guanyin": 1}  # 沒擲中
    monkeypatch.setattr(team, "fight", lambda *a, **k: EncounterResult(tier="落敗", margin=-50, our_power=1, difficulty=60))
    loser = fs_game(c, world, "丙", "huang", "luzhi_camp", rng=FixedRandom(0.0), time=cal(c, 7))
    loser.choose("act:train")
    assert loser.state.player.fs_counters == {}


# ── 豪強的效果與江湖史 ───────────────────────────────────


def test_haoqiang_effects_are_in_the_timetable(fs_content):
    """豪強三條完成時，大事當天不論誰贏：長社割據 +10、盧植割據 +8、宛城割據 +10 並記「{name} 取得新野」。
    （袁紹聲威 +10、完成者與袁紹的情誼 +10：模型表達不了，先不做，見 T7b 回報。）"""
    events = {e.id: e for e in fs_content.timetable}
    assert [events[e].third_party_trends for e in ("changshe_fire", "luzhi_jailed", "wancheng")] == [
        {"geju": 10}, {"geju": 8}, {"geju": 10},
    ]
    assert events["wancheng"].third_party_chronicle == "{name} 取得新野"
    assert events["changshe_fire"].third_party_chronicle is None and events["luzhi_jailed"].third_party_chronicle is None
    assert all(not e.locked_chronicle for e in events.values())  # 內容表沒寫具名江湖史：走「（{name}改寫）」的退路


def test_wancheng_haoqiang_names_the_new_owner_of_xinye_in_the_chronicle(fs_content, world):
    c = fs_content
    state = GameState(player=fs_game(c, world, "甲", None, "xinye").state.player, world=world.get_season())
    state.world.third_party["wancheng"] = ["豪甲", "豪乙"]
    state.world.timeline["zhangmancheng_wan"] = timetable.TimelineResult(key="成", time=0.0)
    event = next(e for e in c.timetable if e.id == "wancheng")
    msgs = timetable.resolve(state, c, event, random.Random(0), key="guan:大勝")
    assert msgs[0].endswith("宛城殺聲震天的時候，新野縣衙的冊子換了主人：豪甲、豪乙 開倉放糧，縣裡的人自己把冊子捧了出來。")
    assert [r.text for r in state.world.chronicle][-1] == "豪甲、豪乙 取得新野"


# ── 準備事件 ─────────────────────────────────────────────


def test_foreshadow_events_are_hidden_when_the_switch_is_off(off_content, world):
    """正式設定的開關是關的：13 則事件在哪個地點都不出現（包括不分陣營的老船夫），beta 那一季一個字都不變。"""
    c = off_content
    assert c.config.season_one is False
    for event_id, (locations, _sides) in FS_EVENTS.items():
        for loc in locations:
            assert event_id in c.events, event_id
            game = Game.new(c, f"關{event_id}{loc}", world=world)
            game.state.player.location = loc
            assert event_id not in {e.id for e in event_candidates(game.state, c, "explore")}, (event_id, loc)


@pytest.mark.parametrize("event_id, item, silver", [
    ("fs_prep_reeds", "fs_reeds", 0), ("fs_prep_oil", "fs_oil", -10), ("fs_prep_witness", "fs_witness", -30),
    ("fs_prep_herb", "fs_herb", 0), ("fs_prep_fungus", "fs_fungus", 0),
])
def test_prep_events_hand_over_one_item_to_their_own_side_only(fs_content, world, monkeypatch, event_id, item, silver):
    """不用檢定的準備事件（葦束、膏油、證人、嵩陰草、白苓）：只對自己的陣營出現；選了那一項給 1 個伏筆物品（銀兩照價錢扣、
    價錢不換算），另一個選項什麼都不拿。"""
    c = fs_content
    event = c.events[event_id]
    side, loc = event.condition.factions[0], event.locations[0]
    mine = fs_game(c, world, "我", side, loc, time=cal(c, 2))
    assert event in candidates(c, mine)
    for other in {"guan", "huang", "haoqiang", None} - {side}:
        assert event not in candidates(c, fs_game(c, world, f"外{other}", other, loc, time=cal(c, 2)))
    meet(c, mine, event_id, monkeypatch)
    mine.state.player.stats["silver"] = 100  # 新手引導在第一次探索後會給一點銀兩：遇上事件之後才設
    msgs = mine.choose("choice:0")
    assert mine.state.player.clue_items == {item: 1} and any(f"獲得 {FS_ITEMS[item]} ×1" in m for m in msgs)
    assert mine.state.player.stats["silver"] == 100 + silver
    walker = fs_game(c, world, "走開", side, loc, time=cal(c, 2))
    meet(c, walker, event_id, monkeypatch)
    walker.state.player.stats["silver"] = 100
    walker.choose(f"choice:{len(event.choices) - 1}")
    assert walker.state.player.clue_items == {} and walker.state.player.stats["silver"] == 100


def test_paid_prep_events_need_the_silver(fs_content, world, monkeypatch):
    """膏油 10 兩、宮中的證人 30 兩（價錢不換算）：銀兩不夠時看不到那個選項。"""
    c = fs_content
    for event_id, price in (("fs_prep_oil", 10), ("fs_prep_witness", 30)):
        event = ALL_EVENTS[event_id]
        game = fs_game(c, world, f"窮{event_id}", "guan", event.locations[0], time=cal(c, 2))
        meet(c, game, event_id, monkeypatch)
        game.state.player.stats["silver"] = price - 1
        assert [o.id for o in game.options()] == [f"choice:{len(event.choices) - 1}"]  # 只剩「不買」


@pytest.mark.parametrize("event_id, item, stat, dc, night", [
    ("fs_prep_dry_reeds", "fs_dry_reeds", "agi", 6, None), ("fs_prep_blood_letter", "fs_blood_letter", "wis", 6, None),
    ("fs_prep_ledger", "fs_ledger", "agi", 6, True), ("fs_prep_ash", "fs_ash", "wis", 7, None),
])
def test_checked_prep_events_roll_the_table_stat(fs_content, world, monkeypatch, event_id, item, stat, dc, night):
    """檢定的準備事件：長社乾葦（敏捷 6）、血書（智力 6）、貨帳（夜裡、敏捷 6）、丹爐灰（智力 7）；失敗沒有損失、可以再來。"""
    c = fs_content
    event = c.events[event_id]
    first = event.choices[0]
    assert (first.check.stat, first.check.difficulty, event.condition.night) == (stat, dc, night)
    assert first.effect.clue_items == {item: 1} and not first.fail_effect.clue_items
    assert "這次沒成，可以再來" in first.fail_effect.text and first.fail_effect.stats == {}
    side, loc = event.condition.factions[0], event.locations[0]
    t = cal(c, 2, 0, 0, 30) if night else cal(c, 2, 0, 12)
    won = fs_game(c, world, "成", side, loc, rng=FixedRandom(0.0), time=t)
    meet(c, won, event_id, monkeypatch)
    won.choose("choice:0")
    assert won.state.player.clue_items == {item: 1}
    lost = fs_game(c, world, "敗", side, loc, rng=FixedRandom(0.99), time=t)
    meet(c, lost, event_id, monkeypatch)
    msgs = lost.choose("choice:0")
    assert lost.state.player.clue_items == {} and "這次沒成，可以再來" in "".join(msgs)
    if night:
        assert event not in candidates(c, fs_game(c, world, "白", side, loc, time=cal(c, 2, 0, 12)))  # 貨帳只在夜裡出現


def test_all_thirteen_events_still_carry_the_joy_placeholder_tag(fs_content):
    """13 則事件的文字是占位（內容表 4.5：事件文字歸 joy），每一則都帶「待joy寫」的標記。
    joy 換完文字、把標記拿掉的時候，這個測試跟著刪；標記只准出現在這 13 則上。"""
    marked = {eid for eid, e in fs_content.events.items() if PLACEHOLDER_TAG in e.tags}
    assert marked == set(FS_EVENTS)


# ── 一條伏筆從頭到尾（版本目標第四節第 3 條）────────────────


def test_end_to_end_one_chain(world):
    """真實內容、週末設定：官軍、黃巾、管理者各一個角色。管理者快轉到長社決戰前一週的夜裡；官軍備齊長社的條件、答對風向，
    黃巾也答對他那條 → 官軍鎖定、黃巾搶輸，鎖定那一刻不發傳聞。管理者再快轉到決戰排定的時間，第 6 週長社決戰收場（官軍大勝）：
    公告寫出官軍的名字與黃巾搶輸的一筆，江湖史有一筆「（名號改寫）」，之後每個人同步都收到那則公告。"""
    c = load_content(CONTENT_DIR, profile="weekend")
    c.config.auto_open_first_season = True
    jia = Game.new(c, "趙甲", rng=random.Random(1), world=world)
    yi = Game.new(c, "錢乙", rng=random.Random(2), world=world)
    admin = Game.new(c, "Rayal", rng=random.Random(3), world=world)
    assert admin.is_admin() and calendar.season_one_on(world.get_season(), c)
    for game, faction, at in ((jia, "guan", "changshe"), (yi, "huang", "huangjin_camp")):
        game.state.player.faction, game.state.player.location = faction, at
        game.state.player.visited.add(at)

    guan_chain, huang_chain = fs_chain(c, "fs_changshe_guan"), fs_chain(c, "fs_changshe_huang")
    # 管理者快轉：第 5 週週五 00:30（長社排在第 6 週週四 20:00：前 7 天的時間窗裡、子時以後）
    admin.advance(fs_window_time(c, jia, guan_chain) - world.get_season().time)
    for game in (jia, yi):
        game.state.world = world.get_season()
    assert calendar.is_night(jia.state.world.time, c, jia.state.world) and "changshe_fire" not in jia.state.world.timeline

    # 官軍：葦束 3、膏油 2（週末各 1）備齊，夜裡在長社答對風向
    assert (foreshadow.need(c, 3), foreshadow.need(c, 2)) == (1, 1)
    jia.state.player.clue_items = {"fs_reeds": 1, "fs_oil": 1}
    rumors = list(world.get_season().rumors)
    msgs = fs_run(world, jia, guan_chain.id, [WIND])
    assert guan_chain.final.success_text.replace("{人物}", "皇甫嵩") in msgs
    assert f"▸ {fs_answer(world, WIND)}" in msgs
    assert world.get_season().rumors == rumors  # 鎖定的那一刻不發任何傳聞
    assert world.get_season().locks["changshe_fire"].name == "趙甲"

    # 黃巾：晚了一步，照做照完成、看到的是自己那條鏈的敘事
    yi.state.world = world.get_season()
    yi.state.player.clue_items = {"fs_dry_reeds": 1}
    assert huang_chain.final.success_text in fs_run(world, yi, huang_chain.id, [WIND])
    season = world.get_season()
    assert [(x.side, x.name) for x in season.lock_losers["changshe_fire"]] == [("huang", "錢乙")]
    assert "趙甲" not in str(season.rumors) and not any("趙甲" in r.text for r in season.chronicle)

    # 管理者快轉到決戰排定的時間；全服決戰（T8）還沒進 main，照 T2 的做法直接給結果：官軍大勝
    event = next(e for e in c.timetable if e.id == "changshe_fire")
    admin.state.world = world.get_season()
    admin.advance(timetable.when(admin.state, c, event) + 1 - world.get_season().time)
    season = world.get_season()
    msgs = timetable.resolve(GameState(player=admin.state.player, world=season), c, event, random.Random(0), key="guan:大勝")
    world.save_season(season)
    named = "史書上，皇甫嵩趁夜縱火，大破波才於長社。這一次，趙甲 讓史書沒有落空：葦束膏油早已備下，風起之時火光燭天。"
    assert msgs[0].startswith("【江湖大事】" + named)
    assert "騎都尉曹操的援兵恰好趕到，黃巾的草營燒成一片火海。" in msgs[0]
    assert "黃巾的 錢乙 曾看破火攻、勸波才移營，可惜晚了一步。" in msgs[0]
    result = season.timeline["changshe_fire"]
    assert (result.key, result.locked_by, result.losers) == ("guan:大勝", "趙甲", ["錢乙"])
    assert [r.text for r in season.chronicle][-1] == "皇甫嵩火攻長社，大破波才。（趙甲改寫）"

    # 每個人同步時都收到那則公告（FB-038），名字寫在裡面
    for game in (jia, yi, admin):
        game.state.world = world.get_season()
        game.advance(1)
        news = [e for e in game.state.journal if e.title == WORLD_NEWS and "趙甲 讓史書沒有落空" in e.tag + "".join(e.lines)]
        assert news, game.state.player.name
