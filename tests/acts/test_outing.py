"""走一趟（tianxia/outing.py；企劃者 2026-10-29～30）：探索一次走一、三、五段，每一段是現行的一次探索；
要選的事停下、選完接著走；打輸、氣血見底回頭，沒走的段不扣體力；段數越多稀有的越容易來（倍數 1／1.2／1.5，畫面不寫）。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

import random
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import explore_modes, explore_one, outing, social, speech, team
from tianxia.encounter import EncounterResult
from tianxia.state import Inscription

pytestmark = pytest.mark.slow

MAT, EVT, ENC = explore_one.MATERIAL, explore_one.EVENT, explore_one.ENCOUNTER


@contextmanager
def _draws(*kinds: str, tier: str = "大勝"):
    """每一段抽到什麼照 kinds 的順序；遭遇照 tier 打。"""
    seq = iter(kinds)
    with mock.patch.object(explore_one, "draw", side_effect=lambda *a, **k: next(seq)), \
         mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40)):
        yield


def _game(**flags):
    game = ready(jianfa_game(**flags), side="guan", loc="yingshui")
    game.state.player.stamina = 100.0
    return game


def _settle_event(game) -> None:
    option = next(o for o in game.options(odds=False) if o.id.startswith("choice:") and o.enabled)
    game.choose(option.id)


def test_three_segments_walk_three_explores():
    game = _game()
    p = game.state.player
    journal = len(game.state.journal)
    with _draws(MAT, MAT, MAT):
        assert game.outing_go(3) == []
    trip = p.outing
    assert (trip.total, trip.done, trip.end) == (3, 3, outing.DONE)
    assert [b.kind for b in trip.beats] == [MAT] * 3
    assert all(b.text and not b.stop for b in trip.beats)
    assert p.stamina == 100 - 3 * game.content.config.jianfa.explore_stamina  # 一段一次探索的體力
    assert len(game.state.journal) - journal == 4  # 每一段各寫一則江湖紀錄，收尾再一則整趟的
    head = game.state.journal[0]
    assert head.title == outing.TRIP_TITLE.format(place="潁水河畔")
    assert f"體力 -{3 * game.content.config.jianfa.explore_stamina}" in head.changes


def test_an_event_stops_the_walk_until_it_is_settled():
    game = _game()
    p = game.state.player
    with _draws(MAT, EVT, MAT):
        game.outing_go(3)
        trip = p.outing
        assert (trip.done, trip.end) == (2, "")
        assert trip.beats[-1].stop and game.state.pending_event is not None
        assert game.outing_view()["trip"]["can_go"] is False  # 事情還沒選
        _settle_event(game)
        assert game.outing_view()["trip"]["can_go"] is True
        game.outing_go()
    assert (trip.done, trip.end) == (3, outing.DONE)


def test_the_last_segment_stopping_closes_after_the_choice():
    game = _game()
    with _draws(EVT):
        game.outing_go(1)
    trip = game.state.player.outing
    assert (trip.done, trip.end) == (1, "")
    _settle_event(game)
    game.outing_go()
    assert trip.end == outing.DONE


def _bag_of_money(game, silver: int = 30, stamina: int = 5):
    """把選事件的那一下換成「塞給你一袋錢」：銀兩 +silver、另外扣 stamina 體力、事件了結。"""
    p = game.state.player

    def settle(_i):
        p.stamina -= stamina
        game.state.pending_event = None
        return ["你咬牙扛住，對方塞給你一袋錢。", f"銀兩 +{silver}"]
    return mock.patch.object(game, "_choose", side_effect=settle)


def test_a_settled_event_keeps_its_numbers_on_the_beat():
    """Joy 10/31「你咬住了牙⋯獲得一袋錢（多少）（有額外扣體力？）」：選完的得失（含另外扣的體力）記在那一段。"""
    game = _game()
    with _draws(MAT, EVT, MAT):
        game.outing_go(3)
        with _bag_of_money(game):
            _settle_event(game)
        trip = game.state.player.outing
        assert trip.beats[-1].after == "得：銀兩 +30　失：體力 -5"
        game.outing_go()
    assert trip.end == outing.DONE
    assert trip.beats[1].after == "得：銀兩 +30　失：體力 -5"  # 接著走的那幾段不算進去
    items, totals = outing.trip_totals(trip)
    step = game.content.config.jianfa.explore_stamina
    assert "銀兩 +30" in totals and f"體力 -{3 * step + 5}" in totals
    assert items and all(" ×" in x for x in items)


def test_leaving_a_line_keeps_the_trip_on_top():
    """留一句併進「走一趟」那一則：「剛剛」照舊看得到整趟的得失（Joy 10/31）。"""
    game = _game()
    with _draws(EVT):
        game.outing_go(1)
    with _bag_of_money(game):
        _settle_event(game)
    game.outing_go()
    count = len(game.state.journal)
    game.outing_say(preset=0)
    head = game.state.journal[0]
    assert len(game.state.journal) == count
    assert head.title == outing.TRIP_TITLE.format(place="潁水河畔")
    assert "銀兩 +30" in head.changes and any("蒼天已死" in line for line in head.lines)


def test_losing_a_fight_turns_back_and_saves_the_stamina():
    game = _game()
    p = game.state.player
    with _draws(ENC, MAT, MAT, tier="落敗"):
        game.outing_go(3)
    trip = p.outing
    assert (trip.done, trip.end) == (1, outing.LOST)
    assert trip.beats[0].kind == ENC and trip.beats[0].won is False
    assert p.stamina == 100 - game.content.config.jianfa.explore_stamina  # 只扣走了的那一段


def test_low_hp_turns_back():
    game = _game()
    with _draws(MAT, MAT, MAT), mock.patch.object(team, "member_neili", return_value=(10.0, 100.0)):
        game.outing_go(3)
    trip = game.state.player.outing
    assert (trip.done, trip.end) == (1, outing.HURT)


def test_refusals():
    game = _game()
    p = game.state.player
    assert game.outing_go(2) == ["（此刻無法這麼做。）"]  # 不是一、三、五段
    p.stamina = 10.0
    assert game.outing_go(5) == ["（體力不夠走這麼多段。）"]
    assert p.outing is None
    assert game.outing_go() == ["（此刻無法這麼做。）"]  # 沒有在路上的那一趟


def test_rare_boost_follows_the_trip_length():
    game = _game()
    s, c = game.state, game.content
    assert outing.rare_boost(s, c) == 1.0
    seen = []
    with _draws(MAT, MAT, MAT, MAT, MAT), mock.patch.object(
            explore_modes, "gather_finds", side_effect=lambda *a, boost=1.0, **k: seen.append(boost) or []):
        game.outing_go(5)
    assert seen == [1.5] * 5
    assert outing.rare_boost(s, c) == 1.0  # 走完了，不在路上
    assert c.config.jianfa.outing_rare == {"1": 1.0, "3": 1.2, "5": 1.5}


def test_gather_boost_raises_only_the_second_tier():
    game = _game()
    c = game.content
    loc = next(l for l in c.locations.values()
               if l.danger >= 2 and l.materials and not explore_modes.is_town(c, l))  # 城外、危險度二以上才擲二階
    chance = c.config.explore_modes.second_tier[loc.danger]

    class Fixed(random.Random):
        def random(self):
            return chance * 1.2  # 不加成擲不中，乘 1.5 擲得中

    plain = explore_modes.gather_finds(c, loc, Fixed(), sure=True)
    boosted = explore_modes.gather_finds(c, loc, Fixed(), sure=True, boost=1.5)
    assert len(boosted) == len(plain) + 1


def test_view_and_switch():
    game = _game()
    view = game.outing_view()
    assert [x["n"] for x in view["picker"]] == [1, 3, 5]
    assert view["note"] == outing.MORE_IS_RARER and "倍" not in view["note"]
    assert view["trip"] is None
    off = _game(outing=False)
    assert off.outing_view() is None
    assert off.outing_go(3) == ["（此刻無法這麼做。）"]


def test_bots_walk_the_same_trip():
    """伺服器假人：挑到探索就挑段數走一趟；停在要選的事上、選完了就接著走（bot_policy.take_turn）。"""
    from tianxia import bot
    game = _game()
    rng = random.Random(1)
    assert bot.outing_segments(game, rng) in (1, 3, 5)
    game.state.player.stamina = 5.0
    assert bot.outing_segments(game, rng) == 0


# ── 留言（題壁墨）、路上看到的那幾行（企劃者 2026-10-29～30）──

def _walked(game, n: int = 1):
    with _draws(*([MAT] * n)):
        game.outing_go(n)
    return game.state.player.outing


def _with_ink(game, n: int = 1) -> None:
    from tianxia.characters import name_key
    from tianxia.wallet import Wallet
    game.now = game.now or 1_800_000_000.0  # 用掉的那一張記用掉的時刻（0 會被當成沒用）
    Wallet(game.world.db).post(name_key(game.state.player.name), 1000, "grant", "test:ink", time=game.now)
    for i in range(n):
        assert game.mall_buy("inscribe_ink", f"ink-{i}") and game.mall_bought == "inscribe_ink"


def test_a_preset_line_is_free_and_one_per_trip():
    game = _game()
    assert game.outing_say(0) == [outing.SAY_NOT_HERE]  # 還沒走
    trip = _walked(game)
    assert game.outing_view()["trip"]["can_say"] is True
    game.outing_say(1)
    w = game.state.world
    assert trip.said == outing.PRESETS[1] and [(i.text, i.preset, i.author) for i in w.inscriptions] == [
        (outing.PRESETS[1], True, game.state.player.name)]
    assert game.outing_say(2) == [outing.SAY_AGAIN]
    assert game.outing_view()["trip"]["can_say"] is False


def test_own_words_need_ink_and_pass_the_word_list():
    game = _game()
    _walked(game)
    assert game.outing_say(text="此處風大") == [outing.NO_INK]
    _with_ink(game)
    assert game.outing_view()["trip"]["ink"] == 1
    game.content.banned_words = ["王八"]
    assert game.outing_say(text="你個王八") == [speech.BLOCKED]
    assert game.outing_say(text="字" * 21) == [speech.TOO_LONG.format(n=20)]
    assert game.outing_say(text="此處風大", verdict="bad") == [speech.BLOCKED]  # 模型擋下
    assert game.outing_view()["trip"]["ink"] == 1  # 擋下的不用墨
    game.outing_say(text="此處風大")
    assert game.state.world.inscriptions[-1].text == "此處風大" and not game.state.world.inscriptions[-1].preset
    assert game.outing_ink_left() == 0


def test_a_place_keeps_the_latest_lines():
    game = _game()
    keep = game.content.config.jianfa.outing_keep
    for _ in range(keep + 3):
        game.state.player.stamina = 100.0
        _walked(game)
        game.outing_say(0)
    here = [i for i in game.state.world.inscriptions if i.place == "yingshui"]
    assert len(here) == keep and here[0].id == 4  # 最舊的三則丟了


def test_others_lines_show_on_the_road_without_taking_a_segment():
    game = _game()
    w = game.state.world
    w.inscription_seq = 2
    w.inscriptions = [Inscription(id=1, place="yingshui", text="溪水可飲。", author="別人", preset=True),
                      Inscription(id=2, place="yingshui", text="自己的", author=game.state.player.name)]
    game.content.config.jianfa.outing_trace_chance = 1.0
    trip = _walked(game, 3)
    traces = [b for b in trip.beats if b.kind == outing.TRACE]
    assert trip.done == 3 and trip.end == outing.DONE
    assert len(traces) == 1 and "溪水可飲。" in traces[0].text and "別人" in traces[0].text and traces[0].ref == 1  # 自己的不看、同一則不看兩次
    assert len([b for b in trip.beats if b.kind != outing.TRACE]) == 3


def test_someone_here_waves_once():
    game = _game()
    game.content.config.jianfa.outing_trace_chance = 1.0
    other = SimpleNamespace(player=SimpleNamespace(name="遠方客"))
    with mock.patch.object(social, "here", return_value=[other]):
        trip = _walked(game, 5)
        assert game.outing_view()["trip"]["people"] == ["遠方客"]
    waves = [b for b in trip.beats if b.kind == outing.TRACE]
    assert [b.text for b in waves] == [outing.WAVE_LINE.format(name="遠方客")]  # 一趟揮一次，沒有留言就只有這一行


def test_admin_erases_a_line():
    game = _game()
    _walked(game)
    game.outing_say(0)
    ins = game.state.world.inscriptions[0].id
    assert game.admin_erase_inscription(ins) == ["（此刻無法這麼做。）"]  # 不是管理者
    game.content.config.admins = [game.state.player.name]
    assert game.admin_erase_inscription(ins) == [outing.ERASED] and game.state.world.inscriptions == []


def test_bots_leave_only_preset_lines():
    from tianxia import bot
    game = _game()
    _walked(game)

    class Always(random.Random):
        def random(self):
            return 0.0
    bot.outing_say(game, Always(3))
    assert game.state.world.inscriptions[0].preset and game.state.world.inscriptions[0].text in outing.PRESETS


# ── 遊記、世界記事 ──

def test_the_tale_falls_back_to_a_template_without_digits():
    game = _game()
    with _draws(MAT, ENC, MAT):
        game.outing_go(3)
    view = game.outing_view()["trip"]
    assert view["diary"].startswith("這一趟在") and "兩樣東西" in view["diary"] and not any(ch.isdigit() for ch in view["diary"])
    assert view["diary_done"] is False


def test_the_model_tale_is_checked_and_kept_for_the_same_trip():
    game = _game()
    _walked(game)
    req = game.outing_tale_request()
    assert isinstance(req, outing.TaleRequest) and req.facts
    assert outing.tale_clean("你走了3段路。", req) is None  # 有數字
    assert outing.tale_clean("你跟人過了兩場招。", req) is None  # 數量
    assert outing.tale_clean("這遊戲真好玩。", req) is None
    assert outing.tale_clean("你在溪邊拾得一根羽毛，風很涼", req) == "你在溪邊拾得一根羽毛，風很涼。"
    game.outing_set_tale("你在溪邊拾得一根羽毛。", req)
    trip = game.state.player.outing
    assert trip.tale == "你在溪邊拾得一根羽毛。" and trip.tale_done
    assert game.outing_tale_request() == ["（此刻無法這麼做。）"]  # 請過了不再請
    _walked(game)
    game.outing_set_tale("舊的那一趟", req)  # 不是同一趟：不收
    assert game.state.player.outing.tale == ""


def _outing_annals(game):
    from tianxia import annals
    return [a for a in game.state.player.annals if a.kind == annals.DEED and ("走了一趟" in a.text or "必輸的一仗" in a.text)]


def test_only_a_rare_treasure_or_an_upset_goes_into_the_annals():
    """Joy 10/30：每一趟都收進行狀太多、沒價值；「真的出現超級稀有的物品或是奇蹟逆轉的戰役這種類型的才有價值被記錄」。
    結算卡的「收進行狀」鈕拿掉；撿到四階素材、勝算凶險以下打贏才自動記一則行狀（世界記事一筆）。"""
    from tianxia import deeds
    game = _game()
    c = game.content
    low = next(m.id for m in c.materials.values() if m.tier == 1)
    top = next(m for m in c.materials.values() if m.tier >= outing.FEAT_TIER)
    with _draws(MAT, ENC, MAT), mock.patch.object(explore_modes, "gather_finds", return_value=[low]), \
         mock.patch.object(team, "odds_word", return_value="有把握"):
        game.outing_go(3)
    assert _outing_annals(game) == [] and game.outing_view()["trip"]["feat_note"] == ""
    assert "outing_keep" not in dir(game)
    with _draws(MAT), mock.patch.object(explore_modes, "gather_finds", return_value=[top.id]):
        game.outing_go(1)
    got = _outing_annals(game)
    assert len(got) == 1 and top.name in got[0].text and game.outing_view()["trip"]["feat_note"] == outing.FEAT_NOTE
    with _draws(ENC), mock.patch.object(team, "odds_word", return_value="凶險"):
        game.outing_go(1)
    got = _outing_annals(game)
    assert len(got) == 2 and "必輸的一仗" in got[-1].text
    if deeds.on(c):
        assert sum(1 for d in game.state.world.deeds if d.kind == outing.DEED_KIND) == 2


def test_the_stele_shows_the_last_ink_or_the_most_left_preset():
    """畫面上方的路碑（Joy 10/30）：最後一則題壁墨寫的；沒有就是最多人留的預設句；點開看全部，新的在前。"""
    game = _game()
    w = game.state.world
    here = game.state.player.location
    assert outing.stele(game.state, here) is None
    w.inscriptions = [Inscription(id=1, place=here, text="溪水可飲。", author="甲", preset=True, time=0),
                      Inscription(id=2, place=here, text="後來者保重。", author="乙", preset=True, time=0),
                      Inscription(id=3, place=here, text="溪水可飲。", author="丙", preset=True, time=0),
                      Inscription(id=4, place="elsewhere", text="別處", author="丁", preset=False, time=0)]
    st = outing.stele(game.state, here)
    assert (st["text"], st["author"], st["n"]) == ("溪水可飲。", "", 2) and [x["author"] for x in st["all"]] == ["丙", "乙", "甲"]
    w.inscriptions.append(Inscription(id=5, place=here, text="橋下有魚", author="戊", preset=False, time=0))
    st = outing.stele(game.state, here)
    assert (st["text"], st["author"]) == ("橋下有魚", "戊") and st["all"][0]["ink"] and st["ink"]


def test_my_own_line_shows_on_the_stele_right_after_i_leave_it():
    """Joy 10/30「自己留的路牌看不到嗎」→「要」：這一趟自己留了一句，碑上先是自己那一句（題壁墨、預設句都算）。"""
    game = _game()
    w = game.state.world
    w.inscription_seq = 1
    w.inscriptions = [Inscription(id=1, place="yingshui", text="橋下有魚", author="戊", preset=False, time=0)]
    _walked(game)
    assert game.outing_view()["trip"]["stele"]["text"] == "橋下有魚"
    game.outing_say(0)
    st = game.outing_view()["trip"]["stele"]
    assert st["mine"] and (st["text"], st["author"]) == (outing.PRESETS[0], game.state.player.name)
    assert not outing.stele(game.state, "yingshui").get("mine")  # 別的時候照舊是最後一則題壁墨


def test_a_line_and_its_erasing_are_saved_to_the_season():
    """留言刻在全服這一季：伺服器每一步都從資料庫重讀，沒寫回共用賽季的話，留下的那一句下一步就不見了（路牌上看不到自己那一句）。"""
    game = _game()
    _walked(game)
    game.outing_say(0)
    assert [i.text for i in game.world.get_season().inscriptions if i.place == "yingshui"] == [outing.PRESETS[0]]
    game.content.config.admins = [game.state.player.name]
    game.admin_erase_inscription(game.state.world.inscriptions[0].id)
    assert not [i for i in game.world.get_season().inscriptions if i.place == "yingshui"]


def test_the_scene_follows_the_place_kind():
    """背景照這一處的地點種類畫（Joy 10/30 六套背景）：潁水河畔是渡。"""
    game = _game()
    _walked(game)
    assert game.outing_view()["trip"]["scene"] == "ford"
    assert game.outing_view()["trip"]["n"] == game.state.player.outing.n  # 畫面認「同一趟」（重新整理接回結算卡、畫布，U-13）


def test_road_lines_are_rare():
    """Joy 10/30「（見）不用（拿掉），但是不用出現太頻繁」：一趟最多一行，每段兩成。"""
    cfg = _game().content.config.jianfa
    assert (cfg.outing_trace_cap, cfg.outing_trace_chance) == (1, 0.2)


def test_a_foe_is_drawn_as_its_own_side():
    """Joy 10/30「現在敵人只有黃巾軍，如果我本身就是黃巾不是很奇怪嗎」：遭遇那一段帶對手的樣子，畫面照它挑圖。"""
    sq = lambda name, faction=None: SimpleNamespace(name=name, faction=faction)
    assert outing.foe_look(sq("郡國兵", "guan")) == outing.LOOK_GUAN
    assert outing.foe_look(sq("黃巾散兵")) == outing.LOOK_HUANG
    assert outing.foe_look(sq("蘇家家丁")) == outing.LOOK_RETAINER
    assert outing.foe_look(sq("吊睛白額虎")) == outing.LOOK_BEAST
    assert outing.foe_look(sq("流寇散兵")) == outing.LOOK_BANDIT
    game = _game()
    with _draws(ENC):
        game.outing_go(1)
    beat = game.state.player.outing.beats[0]
    assert beat.kind == ENC and beat.foe in {outing.LOOK_HUANG, outing.LOOK_GUAN, outing.LOOK_RETAINER, outing.LOOK_BANDIT, outing.LOOK_BEAST}
