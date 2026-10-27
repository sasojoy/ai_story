"""正式季整合第 8 批：各陣營最好的練功點一樣好（設計 3.6、12.1 第 16 條）。官軍大營站的是北軍五校與涼州鐵騎（同廣宗的黃巾死士與渠帥；地盤易手的 garrison），
黃巾在那裡練功打的跟官軍在廣宗打的黃巾死士同一檔：對手經驗差不到一成（勝率照難度，難度也只差一截）。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from jianfa_kit import no_jianfa
from tianxia import atlas, bot, explore_modes, howto
from tianxia import duel as duel_rules
from tianxia import explore_modes, howto


def _practice_foe(faction, at):
    c = real_content("season21")
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    game.state.player.faction, game.state.player.location = faction, at
    return game._gather_foe(c.locations[at])


@pytest.mark.slow
def test_the_yellow_turbans_best_practice_spot_is_as_good_as_the_imperials():
    huang = _practice_foe("huang", "guan_camp")
    guan = _practice_foe("guan", "guangzong")
    assert huang.id == "beijun_wuzu" and guan.id == "huangjin_sishi"
    assert huang.exp >= 0.9 * guan.exp and abs(huang.difficulty - guan.difficulty) <= 10


# ── 原 test_fb670_practice_cell.py（整檔搬進來） ──
# FB-670（企劃者 2026-10-22 選練功入口「丙」，PM 給號）：練功從探索卡最下面搬到行動列自己一格。這一份是伺服器那一半：
# 行動列底下練功那一行（Game.action_notes 的 explore:practice，句子在 howto）。跟練功鈕（Game._practice_option）同一個判斷、同一個次序：
# 有對手寫打誰；這裡只有頭目寫頭目；城鎮與沒有對手的地方寫最近的在哪、步行多久（Game._nearest_practice，時間走 atlas.route_text
# 的步行，跟移動那張卡同一個算法）；頭目冷卻中、次數用完寫鈕上同一句。網頁只照這一句畫（tests/test_jianghu_page_web.py），
# 不另寫一份判斷。選項 id 照舊 explore:practice（假人、整季機器人、bot.pick 不受影響）。

HOUR = 3600


MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


NOW = MON + 10 * HOUR


PRACTICE = "explore:practice"


# 城裡操練（新手引導重做，Config.training）開著時城裡那一格是操練、城外練功寫級數（tests/test_training.py）；
# 這一份測的是練功一格本身（操練關著），內容一律把它關掉

def _content(profile):
    c = real_content(profile)
    c.config.training.enabled = False
    no_jianfa(c)  # 減法季探索一顆開著時沒有練功這一格（行動列只剩一顆「探索」，tests/test_explore_one.py）：這一份測的是舊的練功格
    return c


def _game(at, faction=None, profile="week7"):
    c = _content(profile)
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _option(game):
    return next(o for o in game.options() if o.id == PRACTICE)


def _note(game):
    return game.action_notes([o.id for o in game.options()]).get(PRACTICE)


def _reason(option):
    """灰掉的鈕括號裡那一句。"""
    return option.label.split("（", 1)[1].removesuffix("）")


@pytest.mark.slow
def test_in_town_the_note_says_outside_the_walls_and_how_far_the_nearest_is():
    game = _game("yingchuan")
    option = _option(game)
    route = game._nearest_practice()
    place = game.content.locations[route.path[-1]].name
    walk = atlas.route_text(game.state, game.content, route, "walk")
    assert not option.enabled and _reason(option) == f"{explore_modes.NO_FOE}，最近的在{place}"  # 前提：鈕上灰著、同一個地方
    assert place == "潁水河畔" and walk.startswith("步行約 ") and walk.endswith(" 分鐘")
    assert _note(game) == f"城外才有對手，最近的在{place}（{walk}）"
    # 時間跟移動那張卡上「前往 潁水河畔（步行約 N 分鐘）」一樣（潁水河畔就在隔壁）
    assert f"前往 {place}（{walk}）" in [o.label for o in game.options()]


@pytest.mark.slow
def test_a_place_out_of_town_without_foes_keeps_the_buttons_words():
    """官軍站在自己的大營：不是城鎮，可是一路對手都沒有（自己人不練手）。不說「城外才有」，照鈕上那一句再補步行多久。"""
    game = _game("guan_camp", faction="guan")
    option = _option(game)
    assert not explore_modes.is_town(game.content, game.content.locations["guan_camp"]) and not option.enabled
    route = game._nearest_practice()
    walk = atlas.route_text(game.state, game.content, route, "walk")
    assert _note(game) == f"{_reason(option)}（{walk}）"


@pytest.mark.slow
def test_a_grey_button_without_foes_carries_the_cells_word():
    """PM 2026-10-22（FB-670 回覆第 1 條）：沒有對手而灰著的練功鈕帶一個格子的字（Option.note，行動列格子的小字）：城鎮「城外才有」，
    城外（自家大營、營寨、玉洞、草廬）「這裡沒有」；是不是城鎮照 explore_modes.is_town。散人與兩軍各站遍每個地點；亮著的、頭目的不帶。"""
    game = _game("yingchuan")
    c, p = game.content, game.state.player
    seen = {}
    for faction in (None, "guan", "huang"):
        for loc_id, loc in c.locations.items():
            p.location, p.faction = loc_id, faction
            option = _option(game)
            if option.enabled or not _reason(option).startswith(explore_modes.NO_FOE):
                assert option.note == "", (faction, loc_id)
                continue
            word = explore_modes.NO_FOE_CELL_TOWN if explore_modes.is_town(c, loc) else explore_modes.NO_FOE_CELL
            assert option.note == word, (faction, loc_id)
            seen.setdefault(word, []).append(loc_id)
    assert explore_modes.NO_FOE_CELL_TOWN == "城外才有" and explore_modes.NO_FOE_CELL == "這裡沒有"
    assert "yingchuan" in seen["城外才有"] and {"guan_camp", "huangjin_camp", "jade_cave"} <= set(seen["這裡沒有"])


@pytest.mark.slow
def test_a_lit_practice_note_names_the_foe_the_button_names():
    game = _game("yingshui")
    option = _option(game)
    foe = game._gather_foe(game.content.locations["yingshui"]).name
    assert option.enabled and f"・{foe}・" in option.label
    assert _note(game) == howto.PRACTICE_NOTE.format(foe=foe)


@pytest.mark.slow
def test_a_boss_only_place_names_the_boss_then_says_why_he_is_away():
    game = _game("julu_altar", faction="huang")
    s, c = game.state, game.content
    option = _option(game)
    boss_face = option.label.split("・")[1]
    assert option.enabled and option.label.endswith(f"・{explore_modes.BOSS_NOTE}）")
    assert _note(game) == howto.PRACTICE_BOSS_NOTE.format(foe=boss_face)
    s.player.duel_last = [float(s.player.season_number), s.world.time]  # 冷卻中
    option = _option(game)
    assert not option.enabled and _note(game) == _reason(option) and "後才會再現身" in _note(game)
    s.player.duel_last = []
    boss = duel_rules.here(s, c)[0]
    s.player.duel_tally[duel_rules.week_key(s, c, boss.id)] = c.config.duel.per_boss_week  # 這一段的次數用完（7 天季）
    option = _option(game)
    assert not option.enabled and _note(game) == _reason(option) and "不再現身" in _note(game)


@pytest.mark.slow
def test_a_tired_player_still_reads_what_practice_would_be():
    """體力不夠時鈕灰著（格子寫「體力不夠」），底下那一行照亮著時那一句，跟別的格子一樣。"""
    game = _game("yingshui")
    game.state.player.stamina = 0.0
    assert not _option(game).enabled
    assert _note(game) == howto.PRACTICE_NOTE.format(foe=game._gather_foe(game.content.locations["yingshui"]).name)


@pytest.mark.slow
def test_no_practice_no_note():
    """一類一顆沒蓋章的舊季：沒有練功鈕，也沒有這一行。"""
    game = _game("yingshui")
    game.state.world.precise_actions = False
    ids = [o.id for o in game.options()]
    assert PRACTICE not in ids and PRACTICE not in game.action_notes(ids)


@pytest.mark.slow
def test_the_option_id_is_still_the_one_the_bots_press():
    """選項 id 照舊（explore_modes.option_id(PRACTICE)）：整季機器人要經驗時照舊按得到它。"""
    game = _game("yingshui")
    ids = [o.id for o in game.options() if o.enabled]
    assert PRACTICE == explore_modes.option_id(explore_modes.PRACTICE)
    assert bot.explore_choice(ids, want="exp") == PRACTICE


# ── 原 test_fb672_boss_away_name.py（整檔搬進來） ──
# FB-672：頭目的次數用完時，練功那一行（與練功鈕括號裡同一句）要說出「誰」不再現身。
#
# 以前寫「這一段他不再現身，第 3 天 00:00 再來」，行動列底下獨立成一行之後（FB-670）「他」要回頭猜；頭目還在時那一行寫
# 「這裡只有頭目段鐵頭」有名字。現在 Game._boss_away 把頭目的名字帶進 explore_modes.boss_gone：
# 「這一段頭目段鐵頭不再現身，第 3 天 00:00 再來」（7 天濃縮季）、「這一週頭目…不再現身」（21 天季）、「這一季頭目…不再現身」。
# 名字是這一隻頭目對你露的那一面（Game._boss_face：照陣營），跟「這裡只有頭目某某」、練功鈕上的名字同一個。新字待 joy 潤。
# 冷卻中那一句（頭目約 N 後才會再現身）本來就有「頭目」兩字，這一張不動。

def _game_fb672(at, faction, profile="week7"):
    c = no_jianfa(real_content(profile))  # 減法季探索一顆開著時沒有練功鈕（頭目改掛在出門一趟的遭遇拍）：這一份測的是舊的練功鈕
    store = open_world()
    store.seed_first_season(c)
    store.open_season(c, NOW)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=store)
    game.client = None
    game.sync(NOW)
    p = game.state.player
    p.location, p.faction, p.stamina = at, faction, 250.0
    p.tutorial_step = len(c.tutorial.steps)
    return game


def _reason_fb672(option):
    return option.label.split("（", 1)[1].removesuffix("）")


def _use_up(game):
    s, c = game.state, game.content
    boss = duel_rules.here(s, c)[0]
    key = duel_rules.week_key(s, c, boss.id) if c.config.duel.per_boss_week else duel_rules.season_key(s, boss.id)
    s.player.duel_tally[key] = c.config.duel.per_boss_week or c.config.duel.per_boss_season
    return boss


def _face_before(game):
    """頭目還在時，練功那一行寫的名字（「這裡只有頭目某某…」）。"""
    option = _option(game)
    assert option.enabled
    face = option.label.split("・")[1]
    assert _note(game) == howto.PRACTICE_BOSS_NOTE.format(foe=face)
    return face


# 只有頭目的地方（沒有一路是他的對手以外的隊伍）：官軍站長社、黃巾站鉅鹿道壇；反過來站的那一方有尋常對手，練功那一行寫打誰，不走這一句
@pytest.mark.slow
@pytest.mark.parametrize("faction,place", [("guan", "changshe"), ("huang", "julu_altar")])
def test_week7_names_the_boss_and_the_day_he_comes_back(faction, place):
    game = _game_fb672(place, faction)
    face = _face_before(game)
    _use_up(game)
    option = _option(game)
    assert not option.enabled and option.note == ""
    day = game.content.config.season_segments  # 前提：第 1 段兩天，下一段從第 3 天開始
    assert day[0] == 2
    assert _note(game) == _reason_fb672(option) == f"這一段頭目{face}不再現身，第 3 天 00:00 再來"
    assert "他不再現身" not in _note(game)


@pytest.mark.slow
def test_the_last_segment_says_this_season():
    game = _game_fb672("changshe", "guan")
    face = _face_before(game)
    _use_up(game)
    game.sync(NOW + 5 * 24 * HOUR)  # 第 6 天：最後一段（第 5～7 天）沒有下一段
    # 換了段，這一段的次數是新的一筆帳：再用完一次
    _use_up(game)
    assert _note(game) == f"這一季頭目{face}不再現身"


@pytest.mark.slow
def test_season21_says_this_week():
    game = _game_fb672("changshe", "guan", "season21")
    face = _face_before(game)
    _use_up(game)
    assert _note(game) == _reason_fb672(_option(game)) == f"這一週頭目{face}不再現身"


@pytest.mark.slow
@pytest.mark.parametrize("faction,place,seen,other", [("guan", "changshe", "段鐵頭", "韓稜"), ("huang", "julu_altar", "衛重", "梁鶴")])
def test_the_name_is_the_face_he_shows_that_side(faction, place, seen, other):
    """同一隻頭目有兩個面貌（官軍遇上黃巾那一面、黃巾遇上官軍那一面），寫的是你看到的那一個。"""
    game = _game_fb672(place, faction)
    _use_up(game)
    assert f"頭目{seen}不再現身" in _note(game) and other not in _note(game)


@pytest.mark.slow
def test_cooling_keeps_its_own_sentence():
    game = _game_fb672("changshe", "guan")
    s = game.state
    s.player.duel_last = [float(s.player.season_number), s.world.time]
    option = _option(game)
    assert not option.enabled and "後才會再現身" in _note(game) and _note(game) == _reason_fb672(option)
    assert explore_modes.BOSS_COOLING.split("{")[0] in _note(game)


@pytest.mark.slow
def test_boss_gone_needs_the_boss_name():
    c = real_content("week7")
    game = _game_fb672("changshe", "guan")
    assert explore_modes.boss_gone(game.state, c, "某某").startswith("這一段頭目某某不再現身")
