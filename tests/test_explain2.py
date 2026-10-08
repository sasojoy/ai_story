"""玩法說明二（explain-2，FB-100：QA 用完全不懂的新玩家角度玩 20 分鐘，說明告訴了「這一下會怎樣」，還沒告訴「為什麼要這樣做、目標是什麼」）。

一、點戰況圖卡、態勢、大事、主線看的說明（status.war_help，句子在 tianxia/howto.py）：這一季在打什麼、亂局與割據、大事怎麼定、
    你能怎麼出力。門檻讀設定、此刻在亂局的讀 rules.chaos_fronts、大事的件數讀時刻表、擲骰的上下限讀 timetable 的常數。
二、設定抽屜的玩法說明多五節（這一季在打什麼、名望、投靠與軍令、三方有什麼不同、修練與煉製）；新手期江湖頁有入口；
    狀態列的心得提示改成「付得起、做得了」就提示。
句子待 joy 潤；這裡驗的是「說的跟規則一樣」：設定改了、時刻表改了、內容改了，字跟著變。"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest
from conftest import real_content

from tianxia import howto, rules, timetable
from tianxia.engine import Game

ROOT = Path(__file__).parent.parent


def _war(content, name="甲"):
    return Game.new(content, name, rng=random.Random(0))


# ── 一、點戰況、態勢、大事、主線 ─────────────────────────────────────


def test_each_war_element_has_its_explanation_in_season_one(on):
    help_ = _war(on).status_data()["war_help"]
    assert set(help_) == {"stance", "fronts", "board", "quest"}
    assert all(help_[k] and all(isinstance(line, str) and line for line in help_[k]) for k in help_)
    stance = "".join(help_["stance"])
    assert f"這一季是{on.scenario.name}" in stance and "潁川汝南、南陽、冀州" in stance and "割據" in stance  # 在打什麼、割據
    assert "亂局" in "".join(help_["fronts"]) and "0 是官軍穩控、100 是黃巾控制" in help_["fronts"][0]  # 三條戰線與亂局帶
    board = "".join(help_["board"])
    assert "擲骰" in board and "看戰況" in board and "史書寫定" in board and "決戰" in board and "關鍵伏筆" in board  # 大事怎麼定：戰況、伏筆、寫定的
    quest = "".join(help_["quest"])
    assert "遊歷" in quest and "軍令" in quest and "伏筆" in quest  # 你能怎麼出力


def test_no_war_explanations_outside_season_one(real):
    """開關關著（beta 那一季）：沒有戰況、態勢，也沒有它們的說明，畫面照舊。"""
    data = _war(real).status_data()
    assert "war_help" not in data and "fronts" not in data


def test_the_chaos_band_in_the_explanations_follows_the_config(on):
    game = _war(on)
    assert "戰況 35～65" in game.status_data()["war_help"]["stance"][1]
    on.config.chaos_low, on.config.chaos_high = 30, 70
    help_ = game.status_data()["war_help"]
    assert "戰況 30～70" in help_["stance"][1] and "落在 30～70 是亂局" in help_["fronts"][0]
    assert "35" not in "".join(help_["stance"] + help_["fronts"])


def test_the_fronts_explanation_names_the_fronts_in_chaos_from_the_rule(on):
    """此刻哪幾條在亂局讀 rules.chaos_fronts（圖卡上的「亂局」標、割據的漲落讀的也是它）；門檻一改，名單跟著變。"""
    game = _war(on)
    s = game.state
    names = [rules.trend_name(on, f) for f in rules.chaos_fronts(s, on)]
    line = game.status_data()["war_help"]["fronts"][0]
    assert names and f"現在{'、'.join(names)}在亂局。" in line  # 開季的起始值 40／35／55：三條都在 35～65
    on.config.chaos_low, on.config.chaos_high = 36, 54  # 起始值 40 在、35 與 55 都不在
    assert rules.chaos_fronts(s, on) == ["yingru"]
    assert "現在潁川汝南在亂局。" in game.status_data()["war_help"]["fronts"][0]
    on.config.chaos_low, on.config.chaos_high = 90, 95
    assert rules.chaos_fronts(s, on) == [] and "現在沒有戰線在亂局。" in game.status_data()["war_help"]["fronts"][0]


def _rolls(content):
    rolls = [e for e in content.timetable if e.kind == "roll"]
    return len(rolls), sum(e.front is not None for e in rolls)


def test_the_big_event_counts_follow_the_timetable(on):
    kinds = [e.kind for e in on.timetable]
    roll, fronted = _rolls(on)
    line = howto.board_help(on)[0]
    assert f"這一季有 {len(kinds)} 件大事" in line
    assert f"{kinds.count('fixed')} 件史書寫定" in line
    assert f"{roll} 件擲骰（{fronted} 件看戰況" in line and f"{roll - fronted} 件不在戰線上" in line  # 審查 Minor 5：盧植下獄沒有戰線
    assert f"{kinds.count('showdown')} 場決戰" in line and "季末收場" in line
    first_roll = next(e for e in on.timetable if e.kind == "roll" and e.front is not None)
    first_roll.kind = "fixed"  # 時刻表改了：件數跟著變
    line = howto.board_help(on)[0]
    assert f"{kinds.count('fixed') + 1} 件史書寫定" in line and f"{roll - 1} 件擲骰（{fronted - 1} 件看戰況" in line
    for e in on.timetable:
        e.front = e.front or "yingru"  # 每一件都在戰線上：不寫「不在戰線上」那一段
    assert "不在戰線上" not in howto.board_help(on)[0]


def test_the_events_that_can_be_skipped_are_named_as_such(on):
    """審查 Minor 5：寫好的大事不一定發生——skip_if_out 的人物先退場了就跳過（timetable.resolve）。件數照時刻表。"""
    skips = sum(e.skip_if_out is not None for e in on.timetable)
    assert skips and f"有 {skips} 件要看那位人物還在不在：他先退場了，那件就不發生。" in howto.board_help(on)
    for e in on.timetable:
        e.skip_if_out = None
    assert not any("退場" in line for line in howto.board_help(on))


def test_orders_push_only_when_the_quota_is_met(on):
    """審查 Minor 5：一個人照做軍令不推戰線，全陣營湊滿額度那一刻才推一把（orders.credit）。"""
    line = howto.fronts_help(_war(on).state, on)[1]
    assert "做軍令，會" not in line and "軍令湊滿額度" in line


def test_the_roll_limits_come_from_the_timetable_rule(on, monkeypatch):
    assert "最多給到九成、最少也有一成" in howto.board_help(on)[0]  # timetable.CHANCE_CEIL／CHANCE_FLOOR
    monkeypatch.setattr(timetable, "CHANCE_CEIL", 0.8)
    monkeypatch.setattr(timetable, "CHANCE_FLOOR", 0.2)
    assert "最多給到八成、最少也有二成" in howto.board_help(on)[0]


def test_every_number_in_the_war_explanations_comes_from_the_config_or_the_rules(on):
    """審查 Minor 3（照 explain-1 的 numbers <= allowed）：戰況、態勢、大事、主線的說明與玩法說明「這一季在打什麼」那一節，
    每一個阿拉伯數字都要是設定、時刻表、伏筆鏈、結局算出來的數（設定換成不常見的值，句子裡不能寫死別的數）。"""
    on.config.chaos_low, on.config.chaos_high, on.config.decisive_from_week = 33, 67, 9
    game = _war(on)
    kinds = [e.kind for e in on.timetable]
    locks = {c.event for c in on.foreshadows.chains if c.side in ("guan", "huang")}
    bars = {v for e in on.scenario.endings if e.season_one for v in (*e.stance_min.values(), *(100 - x for x in e.stance_max.values()))}
    roll, fronted = _rolls(on)
    skips = sum(e.skip_if_out is not None for e in on.timetable)
    allowed = {"0", "100", "33", "67", "9", str(len(kinds)), str(len(locks)), *(str(kinds.count(k)) for k in ("fixed", "roll", "showdown")),
               str(fronted), str(roll - fronted), str(skips), *(str(b) for b in bars)}
    help_ = game.status_data()["war_help"]
    section = re.search(r"#### 這一季在打什麼\n((?:- .*\n)+)", game.howto_text()).group(1)
    for text in [*(line for lines in help_.values() for line in lines), section]:
        numbers = set(re.findall(r"\d+", text))
        assert numbers <= allowed, (numbers - allowed, text)


def test_the_rewritable_events_are_the_ones_guan_and_huang_chains_point_at(on):
    """關鍵伏筆改寫得了的大事：官軍、黃巾的鏈指著的那幾件（豪強的鏈是第三方，不改寫結果）；伏筆拿掉就不提。"""
    events = {c.event for c in on.foreshadows.chains if c.side in ("guan", "huang")}
    assert f"其中 {len(events)} 件可以被關鍵伏筆改寫" in howto.board_help(on)[-1]
    lines = len(howto.board_help(on))
    on.foreshadows.chains = [c for c in on.foreshadows.chains if c.side == "haoqiang"]
    assert len(howto.board_help(on)) == lines - 1 and "伏筆改寫" not in "".join(howto.board_help(on))


# ── 二、玩法說明多五節、新手期的入口、心得提示 ─────────────────────────────


def _titles(text):
    return re.findall(r"^#### (.+)$", text, re.M)


def test_the_howto_page_has_the_new_sections_in_season_one(on):
    titles = _titles(_war(on).howto_text())
    assert titles[0] == "這一季在打什麼"  # 為什麼要做這些：排在最前面
    for title in ("名望", "投靠與軍令", "三方有什麼不同", "修練與煉製"):
        assert title in titles
    assert titles.index("名望") < titles.index("投靠與軍令") < titles.index("三方有什麼不同") < titles.index("情誼")
    assert titles.index("心得") < titles.index("修練與煉製") < titles.index("意境")


def test_the_beta_page_leaves_out_what_only_season_one_has(real):
    """開關關著（beta）：沒有戰線、軍令、晉升、三方的不同；名望、投靠、修練與煉製照寫。"""
    text = _war(real).howto_text()
    titles = _titles(text)
    assert "這一季在打什麼" not in titles and "三方有什麼不同" not in titles
    assert {"名望", "投靠與軍令", "修練與煉製"} <= set(titles)
    assert "**投靠**" in text and "**軍令**" not in text and "**晉升**" not in text and "首創的武學或意境" not in text


def test_the_season_section_is_the_war_explanations_and_the_closing_rule(on):
    game = _war(on)
    section = re.search(r"#### 這一季在打什麼\n((?:- .*\n)+)", game.howto_text()).group(1)
    assert howto.season_line(on) in section and "35～65 是亂局" in section
    for line in howto.board_help(on) + howto.quest_help(on):
        assert line in section
    assert f"收季：{rules.stance_rule_note(game.state, on)}" in section  # 收季規則讀 stance_rule_note（第 N 週起、幾分）
    on.config.chaos_low, on.config.chaos_high = 30, 70
    assert "30～70 是亂局" in game.howto_text()


def _fame_spans(content, off=()):
    """名望的三堆，在測試裡另外照內容算一次（不靠 howto）：可重複事件裡不動手的、動手或一次性與奇遇的、扣的。"""
    piles = {"common": [], "big": [], "loss": []}
    for event in content.events.values():
        if event.id in off:
            continue
        rare = event.once or event.qiyu or event.fortune
        effects = [(c.effect, c.combat) for c in event.choices] + [(c.fail_effect, c.combat) for c in event.choices]
        if event.free_text is not None:
            effects += [(event.free_text.effect, None), (event.free_text.fail_effect, None)]
        for effect, combat in effects:
            fame = effect.stats.get("fame", 0)
            if fame < 0:
                piles["loss"].append(fame)
            elif fame > 0:
                piles["big" if rare or combat else "common"].append(fame)
    return {k: (min(v), max(v)) for k, v in piles.items() if v}


def _fame_section(game):
    return re.search(r"#### 名望\n((?:- .*\n)+)", game.howto_text()).group(1)


def test_the_fame_amounts_are_the_ones_the_content_gives(on):
    game = _war(on)
    spans = _fame_spans(on, set(on.scenario.season_one_off.events))
    section = _fame_section(game)
    low, high = spans["common"]
    assert f"（探索、交友、遊歷之後碰上的事）：一次 +{low}～+{high}。" in section
    low, high = spans["big"]
    assert f"劇情裡打贏強敵、奇遇與一次性的大事：一次 +{low}～+{high}。" in section
    most, least = spans["loss"]
    assert f"做了丟臉的事會掉：{-least}～{-most}。" in section


def test_the_fame_amounts_follow_the_content_when_it_changes(on):
    game = _war(on)
    common = next(e for e in on.events.values() if not (e.once or e.qiyu or e.fortune) and "explore" in e.actions
                  and any(c.combat is None and c.effect.stats.get("fame", 0) > 0 for c in e.choices))
    choice = next(c for c in common.choices if c.combat is None and c.effect.stats.get("fame", 0) > 0)
    choice.effect.stats["fame"] = 9
    assert "碰上的事）：一次 +1～+9。" in _fame_section(game)
    # 這一季關掉的 beta 事件（season_one_off）不算：開關開著時改了它也不影響
    for c in on.events["kou_boss"].choices:
        if c.effect.stats.get("fame", 0) > 0:
            c.effect.stats["fame"] = 77
    assert "+77" not in _fame_section(game)


def test_only_events_and_the_first_echo_give_fame_in_the_code():
    """名望的來源只有兩條：事件的效果（rules.apply_effect 照內容的 stats 加減）與第一季的首創回饋（Game._deliver_echoes）。
    程式裡直接寫名望的只有首創回饋那一行；內容裡給名望的效果只在 content/events。多了一條來源，玩法說明「名望」那一節要跟著寫。"""
    writes = []
    for path in sorted((ROOT / "tianxia").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"""stats\[\s*["']fame["']\s*\]\s*[+-]?=""", line):
                writes.append((path.name, line.strip()))
    assert writes == [("engine.py", 'p.stats["fame"] = p.stats.get("fame", 0) + gained')]
    givers = []

    def scan(node, where):
        if isinstance(node, dict):
            if isinstance(node.get("stats"), dict) and node["stats"].get("fame", 0) > 0:
                givers.append(where)
            for value in node.values():
                scan(value, where)
        elif isinstance(node, list):
            for value in node:
                scan(value, where)

    for path in sorted((ROOT / "content").rglob("*.json")):
        scan(json.loads(path.read_text(encoding="utf-8")), path.relative_to(ROOT / "content").as_posix())
    assert givers and all(where.startswith("events/") for where in givers), sorted(set(givers))


def test_the_first_echo_line_follows_the_config_and_only_in_season_one(on):
    on.config.first_echo.fame_per, on.config.first_echo.cap = 2, 7
    assert "別人照著合出同一門：每多一個人 +2，一門最多算 7 個人。" in _fame_section(_war(on))
    on.config.first_echo.fame_per = 0
    assert "首創的武學或意境" not in _fame_section(_war(on, "乙"))
    beta = real_content()  # 另一份（on 與 real 是同一份，開關已經打開）：開關關著、回饋照預設
    beta.config.auto_open_first_season = True
    assert beta.config.first_echo.fame_per > 0
    assert "首創的武學或意境" not in _fame_section(_war(beta))  # beta 沒有首創回饋（fusion.echo 只在第一季記）


def test_what_fame_is_for_follows_the_content(on):
    game = _war(on)
    bars = sorted(ch.audience_fame for ch in on.characters.values() if ch.deep_interaction and ch.audience_fame > 0)
    lessons = sorted(s.learn.fame for s in on.skills.values() if s.learn is not None and s.learn.fame > 0)
    line = _fame_section(game).splitlines()[-1]
    assert f"門檻最低 {bars[0]}、最高 {bars[-1]}" in line and f"名望到 {on.config.vision_fame}，輿圖多看一站" in line
    assert f"有些師父要名望 {lessons[0]} 以上才肯教" in line
    on.config.vision_fame = 12
    assert "名望到 12，輿圖多看一站" in _fame_section(game)


def test_joining_and_orders_read_the_config(on):
    on.config.contrib_per_push, on.config.rank2_contrib, on.config.audience_rank_discount = 7, 210, 4
    text = _war(on).howto_text()
    assert "推 1 點戰況記 7）" in text and "到 210 會有人召見" in text and "求見他的門檻就低 4" in text
    assert "攻城、守城、截糧、護糧、打擊" in text


def test_the_three_sides_are_read_from_the_scenario_and_the_rank_content(on):
    from tianxia import ranks

    section = re.search(r"#### 三方有什麼不同\n((?:- .*\n)+)", _war(on).howto_text()).group(1)
    rows = section.splitlines()
    assert len(rows) == len(on.scenario.factions)
    for faction, row in zip(on.scenario.factions, rows):
        assert row.startswith(f"- **{faction.name}**（在{'、'.join(on.locations[i].name for i in faction.join_at)}投靠）")
        titles = [t for t in ranks.TITLES[faction.id] if t]
        assert f"頭銜從{titles[0]}做到{titles[-1]}" in row
        assert f"「{on.orders.duties[faction.id].name}」" in row
        for action in on.orders.rank_actions:
            assert (f"第 {action.rank} 階起多「{action.name}」" in row) == (action.faction == faction.id)
    guan, huang, hao = rows
    assert "往官軍那一邊推" in guan and "往黃巾那一邊推" in huang and "不推戰線，戰線在亂局時遊歷、操練推割據" in hao
    assert "軍令只有打擊" in hao and "軍令有攻城、守城、截糧、護糧、打擊" in guan
    on.orders.templates = [t for t in on.orders.templates if not (t.side == "guan" and t.kind != "strike")]
    assert "軍令只有打擊" in re.search(r"- \*\*官軍\*\*.*", _war(on, "乙").howto_text()).group(0)


def _fresh(content, name="甲"):
    """新角色、略過序章（站在起點、拿了盤纏）。"""
    from tianxia.sqlite_world import open_world

    game = Game.new(content, name, rng=random.Random(0), world=open_world(), prologue=True)
    game.client = None
    game.skip_tutorial()
    return game


def test_the_howto_entry_is_there_only_in_the_newbie_window(on):
    from tianxia import calendar

    on.config.newbie_days = 1  # 氣血加倍那一段（newbie_days）跟體力那一段分開：入口跟的是體力那一段（審查 Minor 3）
    on.config.newbie_stamina_days = 18
    game = _fresh(on)
    assert game.status_data()["howto_entry"] is True
    s = game.state
    window = on.config.newbie_stamina_days * calendar.DAY / calendar.cal_scale(on, s.world)  # 跟體力回復加快同一段（roster.newbie）
    s.player.joined_at = s.world.time - window + 1
    assert game.status_data()["howto_entry"] is True
    s.player.joined_at = s.world.time - window - 1
    assert game.status_data()["howto_entry"] is False


def test_no_howto_entry_in_the_prologue(prologue_content, world):
    hut = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    assert hut.status_data()["howto_entry"] is False  # 序章裡師父會說


def test_the_xinde_hint_shows_once_the_next_level_is_affordable(on):
    """FB-100：剛出師、心得 34 的人看不到提示（以前要攢到 50）。現在只看「付得起、做得了」：心得夠練下一成就提示去「修練」。"""
    from tianxia import team

    game = _fresh(on)
    s = game.state
    member = s.player.member
    price = min(team.practice_price(on, member.wugong_level), team.practice_price(on, member.neigong_level))
    s.player.stats["xinde"] = price - 1
    assert game.status_data()["hint"] is None
    s.player.stats["xinde"] = price
    hint = game.status_data()["hint"]
    assert hint and "去「修練」練成" in hint and f"你已攢下 {price} 點心得" in hint
    s.player.stats["xinde"] = 34  # QA 那一輪的心得
    assert "去「修練」" in game.status_data()["hint"]


def test_no_xinde_hint_while_the_season_is_being_prepared(content, world):
    """審查 Minor 1：籌備中練成、合成都被擋（「賽季籌備中，等待管理者開季」），提示不能叫人去按。開了季就回來。"""
    from tianxia import team

    content.config.auto_open_first_season = False
    content.config.admins = ["管理者"]
    game = Game.new(content, "甲", rng=random.Random(1), world=world)
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.stats["xinde"] = team.practice_price(content, 1) + 10
    assert world.season_phase() == "preparing"
    assert game.practice("武學") == ["（賽季籌備中，等待管理者開季。）"]
    assert game.status_data()["hint"] is None
    Game.new(content, "管理者", rng=random.Random(2), world=world).admin_open_season(now=0.0)
    game.sync(10.0)
    assert game.status_data()["hint"]


def test_the_xinde_hint_points_to_the_forge_when_only_a_forge_is_doable(on):
    game = _fresh(on)
    s, cfg = game.state, on.config
    s.player.member.wugong_level = s.player.member.neigong_level = 10  # 兩門都練滿了：沒得練成
    s.player.stats["xinde"] = max(cfg.fuse_xinde, cfg.merge_xinde)
    s.player.insights = []
    assert game.status_data()["hint"] is None  # 沒有意境：合不了
    s.player.insights = ["feng"]
    hint = game.status_data()["hint"]
    assert hint and "去「煉製」" in hint and "修練" not in hint
    s.player.stamina = 0
    assert game.status_data()["hint"] is None  # 付不起體力：做不了


# ── 三、有所感的卡：意境是什麼、做法跟此地的關係，不洩漏哪一個是對的 ─────────────────────


METHODS = (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))


def _feeling(game, methods=METHODS, prologue=False, seed=0):
    from tianxia import sensing
    from tianxia.models import InsightScene, SenseMethod

    scene = InsightScene(
        id="lake_view", title="湖光", text="湖水拍岸。", locations=["lake"], prologue=prologue,
        methods=[SenseMethod(attribute=a, text=t) for a, t in methods],
    )
    game.content.insight_scenes = {scene.id: scene}
    game.state.player.location = "lake"
    game.state.player.sensing = None
    sensing.start(game.state, game.content, scene, random.Random(seed))
    return scene


def insights_pool(game):
    """這一處悟得到的意境的屬性（判斷做法對錯的那一份）。"""
    from tianxia import insights

    return insights.pool_attributes(game.content.locations[game.state.player.location], game.content)


def _card(game):
    ids = [o.id for o in game.options(odds=False)]
    return game.scene_text(), game.method_help(ids), [(o.id, o.label) for o in game.options(odds=False)]


def test_the_feeling_card_says_what_an_insight_is_and_frames_the_methods(game):
    from tianxia import sensing

    scene = _feeling(game)
    text, help_, _ = _card(game)
    assert "**有所感・湖光**（湖畔）" in text  # 地形寫在標題同一行
    assert help_["lines"] == [sensing.FRAMING.format(kinds="剛、柔、快、慢"), sensing.INSIGHT_LINE]
    # 審查 Minor 5：一處悟得到兩種（湖邊：水、風）的時候，對的做法有兩個：不能說「那一種」
    assert len(insights_pool(game)) == 2 and "那一種" not in sensing.FRAMING and "合得上的" in sensing.FRAMING
    assert "意境" in help_["lines"][1] and "合成" in help_["lines"][1] and "修練" in help_["lines"][1]
    # 審查 I1：每個做法不標心意（輿圖「這裡能悟」加上鈕上的心意，卡就成了查表）；鈕上照舊 1～4，卡上的字也不寫哪一個做法是哪一種
    assert "tags" not in help_
    for method in scene.methods:
        assert f"{method.attribute}・{method.text}" not in text and f"（{method.attribute}）{method.text}" not in text


def test_the_kind_labels_come_back_with_one_switch(game, monkeypatch):
    """企劃者要恢復鈕上的心意：sensing.SHOW_KINDS 改 True（一行），伺服器就照做法給 tags，網頁照它畫。"""
    from tianxia import sensing

    monkeypatch.setattr(sensing, "SHOW_KINDS", True)
    scene = _feeling(game)
    _, help_, _ = _card(game)
    order = game.state.player.sensing.order
    assert help_["tags"] == {f"sense:{i}": scene.methods[j].attribute for i, j in enumerate(order)}


def test_the_feeling_hint_is_the_same_whichever_method_is_right(game):
    """選對選錯只看這一處悟得到什麼（insights.pool_attributes）：換成別的做法才是對的，卡上的字、鈕上的心意、做法底下的小字一個都不變。
    做法照內容寫的順序常把對的那一個寫在最前面：心意照固定的順序列，內容換了順序也一樣。"""
    from tianxia import insights

    lake = game.content.locations["lake"]
    lake.insights = ["shui"]  # 只有柔是對的
    _feeling(game)
    soft = _card(game)
    assert insights.pool_attributes(lake, game.content) == {"柔"}
    lake.insights = ["huo"]  # 換成只有剛是對的
    _feeling(game)
    assert insights.pool_attributes(lake, game.content) == {"剛"} and _card(game) == soft
    _feeling(game, methods=METHODS[1:] + METHODS[:1])  # 內容把剛寫在最前面（同一副洗牌）
    text, help_, _ = _card(game)
    assert text == soft[0] and help_["lines"] == soft[1]["lines"]


def test_no_method_help_in_the_hut_or_while_drawing(game):
    from tianxia import sensing

    _feeling(game)
    game.state.player.sensing.stage, game.state.player.sensing.method = "draw", "柔"
    text, help_, _ = _card(game)
    assert help_ is None and "（湖畔）" in text  # 畫的那一步：做法已經選了，不再畫提示（地形照寫）
    assert sensing.method_help(game.state, game.content) is None  # 不只是選單上沒有做法：規則本身就只在選做法那一步給
    _feeling(game, prologue=True)  # 序章草廬：四個做法都對，卡照舊
    text, help_, _ = _card(game)
    assert help_ is None and "（湖畔）" not in text


def test_no_method_help_when_the_methods_are_not_on_the_menu(game):
    """戰場蓋過了畫面（選單是戰鬥選項）：做法不在選單上，就不給提示。"""
    _feeling(game)
    assert game.method_help(["battle:act:0"]) is None


# ── 四、潁川附近打得贏的遊歷（內容）：潁水河畔的河灘潑皮、偷網賊 ─────────────────────────────

RIVER = "yingshui"
NEW_SQUADS = ("hetan_popi", "touwang_zei")
WINNABLE = ("穩勝", "有把握")  # 「有勝算」：team.ODDS 沒有這個詞，取有把握（勝率 65% 以上）或更好


def _graduate(content, seed):
    """走完序章的新角色（假人、整季機器人走的同一條路：Game.new(graduated=True)），站在起點。"""
    from tianxia.sqlite_world import open_world

    world = open_world()
    if not world.get_season().storyline:
        world.seed_first_season(content)
    world.open_season(content, now=0.0)
    game = Game.new(content, f"出師{seed}", rng=random.Random(seed), world=world, graduated=True)
    game.client = None
    return game


@pytest.mark.parametrize("profile", ["weekend", None])
def test_a_fresh_character_can_win_by_the_yingshui(profile):
    """FB-100：剛出師的人在潁川一帶找不到打得贏的仗（長社、黃巾別部營寨都是必敗，潁川郊野難分勝負）。
    潁水河畔的兩路對手：略過序章與走完序章的新角色，勝算都是有把握以上，遊歷鈕上寫的也是。"""
    content = real_content(profile)
    content.config.auto_open_first_season = True
    for game in [_fresh(content), *(_graduate(content, seed) for seed in (1, 2, 3))]:
        game.state.player.location = RIVER
        for sid in NEW_SQUADS:
            assert game.odds(sid) in WINNABLE, (game.state.player.name, sid, game.odds(sid))
        train = next(o for o in game.options() if o.id == "act:train")
        assert train.enabled and train.label.split("・")[-1].rstrip("）") in WINNABLE, train.label


def test_the_river_squads_sit_within_two_stops_of_the_start(on):
    from collections import deque

    start = on.scenario.start_location
    assert start == "yingchuan"
    dist, todo = {start: 0}, deque([start])
    while todo:
        here = todo.popleft()
        for there in on.locations[here].connections:
            if str(there) not in dist:
                dist[str(there)] = dist[here] + 1
                todo.append(str(there))
    assert dist[RIVER] <= 2
    assert set(NEW_SQUADS) <= set(on.locations[RIVER].enemies)


def test_every_side_fights_the_river_squads(on):
    """不屬於任何陣營：誰遇上都是真的打（不會變成某一邊的零風險操練），散人與三邊的人一樣是勝算有把握的仗。"""
    game = _war(on)
    for faction in [None, *(f.id for f in on.scenario.factions)]:
        game.state.player.faction = faction
        assert not any(game._drills_with(on.squads[sid]) for sid in NEW_SQUADS)
    for sid in NEW_SQUADS:
        assert on.squads[sid].faction is None and on.squads[sid].desc


def test_the_river_squad_names_pass_the_name_rules(on):
    from tianxia import naming

    for sid in NEW_SQUADS:
        assert naming.name_problem(on.squads[sid].name, on) is None


def test_the_big_camp_opponents_stay_as_they_were(on):
    """給有經驗的人打的營寨對手不動（brief）：黃巾別部營寨、長社照舊。"""
    assert on.locations["huangjin_camp"].enemies == ["shuikou", "toumu"]
    assert on.locations["changshe"].enemies == ["louluo", "shuikou"]
    assert (on.squads["shuikou"].difficulty, on.squads["toumu"].difficulty, on.squads["louluo"].difficulty) == (35, 70, 15)


# ── 五、FB-101：行動列底下兩處小字 ─────────────────────────────


def _notes(game):
    return game.action_notes([o.id for o in game.options(odds=False)])


def test_the_drill_line_does_not_say_drill_again(on):
    """投靠黃巾之後在黃巾別部營寨：遊歷那一格本身寫「操練」，底下那一行不再開頭寫一次（以前是「操練　操練不冒險：…」）。"""
    game = _war(on)
    game.state.player.faction = "huang"
    game.state.player.location = "huangjin_camp"
    train = next(o for o in game.options(odds=False) if o.id == "act:train")
    assert train.label.startswith("操練（")
    line = _notes(game)["act:train"]
    assert line.startswith("不冒險：") and "操練" not in line


def test_one_branch_left_is_not_mostly(on):
    """只剩一支走得了（例：潁川選錯了做法，悟意境那一支到換日都沒了）：不寫「多半」，寫「會」。正式內容每一處都照這條。"""
    from tianxia.rules import game_day

    game = _war(on)
    s = game.state
    s.player.sense_misses[s.player.location] = game_day(on, s.world)
    line = _notes(game)["act:explore"]
    assert line.startswith("這裡會碰上事件") and "多半" not in line
    for loc in on.locations.values():
        s.player.location = loc.id
        weights = [w for w in game._explore_weights(loc) if w[1] > 0]
        note = _notes(game).get("act:explore")
        if note is not None and len(weights) == 1:
            assert "多半" not in note and note.startswith("這裡會"), (loc.id, note)
        if note is not None and len(weights) > 1:
            assert "這裡會" not in note, (loc.id, note)
