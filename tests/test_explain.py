"""玩法說明（explain-1，試玩回饋 Gary：「很多東西要一句說明，不然體力用完了還不知道在玩什麼」）。

一、行動列底下那幾行：探索、遊歷、交友這一下會怎樣（Game.action_notes，句子在 tianxia/howto.py）；有所感選做法之前先說選錯的代價。
二、情誼：看得到（談話畫面、求見名單、輿圖的人物），玩家看到的一律叫「情誼」，第一次交友或談話時師父說它有什麼用（h_bond）。
句子待 joy 潤；這裡驗的是「說的跟規則一樣」：探索照探索真的擲骰用的那一份比重、遊歷照對手與操練的規則、數字照設定。"""
from __future__ import annotations

import ast
import random
import re
from pathlib import Path
from unittest import mock

import pytest
from conftest import real_content
from test_explore import _lake

from tianxia import atlas, companion_agent, hints, howto, sensing
from tianxia.engine import Game
from tianxia.models import ExploreMix, HintDef, InsightScene, SenseMethod
from tianxia.rules import current_day

ROOT = Path(__file__).parent.parent


def _notes(game):
    return game.action_notes([o.id for o in game.options(odds=False)])


# ── 探索：照這個地點那一類的比例（Config.explore_mix），跟擲骰同一份 ─────────────────────


@pytest.mark.parametrize("tags, line", [
    (["營寨"], "這裡多半碰上事件，也可能遇野怪、悟意境"),  # 營寨 15／35／50
    (["城鎮"], "這裡多半碰上事件，也可能悟意境"),  # 城鎮 15／0／85：野怪那一支是 0，不提
    (["湖畔"], "這裡多半悟意境，也可能遇野怪、碰上事件"),  # 其餘 40／35／25
])
def test_the_explore_line_follows_the_mix_of_each_place_kind(game, tags, line):
    _lake(game, tags=tags)
    assert _notes(game)["act:explore"] == line


def test_the_explore_line_follows_the_config_when_it_changes(game):
    _lake(game, tags=["城鎮"])
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 60, "wild": 0, "event": 40})
    assert _notes(game)["act:explore"] == "這裡多半悟意境，也可能碰上事件"
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 50, "wild": 0, "event": 50})
    assert _notes(game)["act:explore"] == "這裡可能悟意境、碰上事件"  # 並列最大：不說「多半」


def test_the_explore_line_drops_what_cannot_happen_here_like_the_roll_does(game):
    """做不了的那一支擲骰時拿掉、比例分給另外兩支（Game._explore_can）：說明也不提。"""
    _lake(game, tags=["營寨"], enemies=())  # 沒有會打的對手：營寨也遇不到野怪
    assert _notes(game)["act:explore"] == "這裡多半碰上事件，也可能悟意境"
    game.state.player.sense_misses["lake"] = current_day(game.state)  # 今天在這裡選錯過做法：悟意境那一支沒了
    assert _notes(game)["act:explore"] == "這裡多半碰上事件"


def test_the_explore_line_and_the_roll_read_the_same_weights(game, monkeypatch):
    """說明與擲骰都讀 Game._explore_weights：換掉它，兩邊一起變（說的跟擲的不會各寫一份）。"""
    _lake(game)
    monkeypatch.setattr(Game, "_explore_weights", lambda self, loc: [("wild", 1.0)])
    assert _notes(game)["act:explore"] == "這裡多半遇野怪"
    seq = game.state.battle_seq
    game._explore()
    assert game.state.battle_seq == seq + 1  # 真的打了一場野怪


def test_the_explore_line_follows_wisdom_like_the_roll(game):
    """悟意境那一支乘悟性（武學與成長設計 6.1），擲骰跟說明都一樣：悟性夠高，城裡也會「多半悟意境」。"""
    _lake(game, tags=["城鎮"])
    game.content.config.explore_mix[1] = ExploreMix(kind="town", tags=["城鎮"], weights={"insight": 45, "wild": 0, "event": 55})
    assert _notes(game)["act:explore"].startswith("這裡多半碰上事件")
    game.state.player.stats["wis"] = 15  # ×1.3：58.5 比 55
    assert _notes(game)["act:explore"].startswith("這裡多半悟意境")


def test_the_explore_line_mentions_the_breakthrough_pill_only_when_it_can_drop(game):
    _lake(game)
    assert "破境丹" not in _notes(game)["act:explore"]  # 測試內容把機率設成 0
    game.content.config.explore_legend_chance = 0.02
    assert _notes(game)["act:explore"].endswith("；偶得破境丹")


def test_explore_line_words():
    assert howto.explore_line([]) == "這裡多半一無所獲"
    assert howto.explore_line([("insight", 0.0), ("event", 3.0)]) == "這裡多半碰上事件"  # 比重 0 的不提
    assert howto.explore_line([("insight", 2.0), ("wild", 2.0), ("event", 1.0)], "破境丹") == "這裡可能悟意境、遇野怪、碰上事件；偶得破境丹"


# ── 遊歷：打贏得什麼；自己人的地盤是操練 ─────────────────────────────────


def test_the_train_line_says_what_winning_gives_on_enemy_ground(game):
    _lake(game)
    line = _notes(game)["act:train"]
    assert line == "打贏得銀兩、心得、經驗，可能掉素材，推動戰局"  # 水寇小隊：銀兩 5、心得 10、經驗 20；湖邊推大勢


def test_the_train_line_is_a_drill_on_your_own_ground(game):
    """自己陣營的隊伍不打、改操練（Game._drill）：不冒險，只給心得與經驗（對手的 drill_reward_share），不給銀兩、素材。"""
    _lake(game)
    game.state.player.faction = "guan"
    game.content.squads["thug"].faction = "guan"
    line = _notes(game)["act:train"]
    assert line == "操練不冒險：得心得、經驗，推動戰局；不給銀兩、素材"
    game.content.config.drill_reward_share = 0.0  # 操練什麼都不給的話，就不說給
    assert _notes(game)["act:train"] == "操練不冒險：沒什麼賞，推動戰局；不給銀兩、素材"


def test_the_train_line_mentions_the_drill_where_both_sides_are(game):
    _lake(game, enemies=("thug", "boss"))
    game.state.player.faction = "guan"
    game.content.squads["thug"].faction = "guan"
    boss = game.content.squads["boss"]
    boss.reward_xinde, boss.exp = 50, 30
    # 會打的只剩翻江龍：他給心得、經驗，不給銀兩（水寇小隊的銀兩是自己人的，操練不給）
    assert _notes(game)["act:train"] == "打贏得心得、經驗，可能掉素材，推動戰局；遇上自己人是操練"


def test_the_train_line_leaves_out_the_push_where_the_place_pushes_nothing(game):
    _lake(game)
    game.content.locations["lake"].train_trend = {}
    assert _notes(game)["act:train"] == "打贏得銀兩、心得、經驗，可能掉素材"


# ── 交友：會遇上誰 ──────────────────────────────────────────


def test_the_socialize_line_says_what_you_meet(game):
    game.state.player.location = "town"
    assert _notes(game)["act:socialize"] == "結識這裡的人，碰上交友的事"


def test_the_socialize_line_names_the_figure_you_will_talk_to(game, monkeypatch):
    monkeypatch.setattr(Game, "_socialize_figure", lambda self: "sage")
    game.state.player.location = "town"
    assert _notes(game)["act:socialize"] == "和隱士談話，聊得投機情誼會漲"


def test_no_notes_in_the_prologue(prologue_content, world):
    hut = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    assert hut.action_notes(["act:explore", "act:train", "act:socialize"]) == {}


def test_notes_only_for_what_is_on_the_menu(game):
    game.state.player.location = "town"  # 小鎮沒有對手：沒有遊歷
    assert set(_notes(game)) == {"act:explore", "act:socialize"}


# ── 有所感：選做法之前先說選錯的代價（sensing.choose：選錯了這一處今天不再悟）─────────────────


def _feeling(game, prologue=False):
    scene = InsightScene(
        id="lake_view", title="湖光", text="湖水拍岸。", locations=["lake"], prologue=prologue,
        methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
    )
    game.content.insight_scenes = {scene.id: scene}
    game.state.player.location = "lake"
    sensing.start(game.state, game.content, scene, random.Random(0))
    return scene


def test_the_feeling_card_warns_before_a_method_is_chosen(game):
    _feeling(game)
    text = game.scene_text()
    assert sensing.MISS_WARNING in text and text.index("湖水拍岸") < text.index(sensing.MISS_WARNING)
    assert sensing.MISS_WARNING == "選錯了做法，今天在這裡就悟不出了。"


def test_the_warning_matches_the_rule(game):
    """說的是真的：選錯了，這一處今天不再落在悟意境那一支（Game._explore_can 看 sensing.missed_today）。"""
    scene = _feeling(game)
    wrong = [scene.methods[j].attribute for j in game.state.player.sensing.order].index("剛")  # 湖邊悟得到水、風：剛是錯的
    game.choose(f"sense:{wrong}")
    assert sensing.missed_today(game.state, game.content.locations["lake"])
    assert not game._explore_can("insight", game.content.locations["lake"])


def test_no_warning_once_drawing_or_in_the_hut(game):
    _feeling(game)
    game.state.player.sensing.stage, game.state.player.sensing.method = "draw", "柔"
    assert "有所感・湖光" in game.scene_text() and sensing.MISS_WARNING not in game.scene_text()
    game.state.player.sensing = None
    _feeling(game, prologue=True)  # 序章草廬的四景：四個做法都對，不嚇人
    assert "有所感・湖光" in game.scene_text() and sensing.MISS_WARNING not in game.scene_text()


# ── 二、情誼：看得到、只叫「情誼」、第一次交友或談話時說它有什麼用 ─────────────────────────────


def _talking(content, game, affinity=12):
    """小鎮只有韓鐵一位人物（測試內容）：交友直接開口談話，模型換成固定的一輪（不叫模型）。"""
    from test_engine import FAKE_TURN

    content.characters["mate"].deep_interaction = True
    game.state.player.affinities["mate"] = affinity
    return mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN)


def test_the_dialogue_shows_the_bond_next_to_the_name(content, game):
    with _talking(content, game):
        game.choose("act:socialize")
        assert game.scene_text().startswith("**韓鐵**（情誼 12）\n\n")
        msgs = game.choose("talk:0")
    assert "（情誼 +1）" in msgs  # 談完那一輪的漲跌也叫情誼（以前寫「好感度」）
    assert game.scene_text().startswith("**韓鐵**（情誼 13）")


def test_the_audience_list_shows_the_bond_of_each_figure(game, monkeypatch):
    monkeypatch.setattr(Game, "_figures_here", lambda self: ["mate", "sage"])
    game.state.player.affinities["mate"] = 5
    game.state.player.picking_audience = True
    assert game.scene_text().endswith("你跟他們的情誼：韓鐵 5、隱士 0。")


def test_the_map_figure_card_shows_the_bond(on):
    game = Game.new(on, "甲", rng=random.Random(0))
    fig = next(f for f in on.figures.values() if f.character is not None)
    game.state.player.affinities[fig.character] = 33
    assert "- 你跟他的情誼 33（" in atlas.leader_text(game.state, on, fig.name)
    nobody = next(f for f in on.figures.values() if f.character is None)  # 彭脫這類沒有對話人物的：沒有情誼
    assert "情誼" not in atlas.leader_text(game.state, on, nobody.name)


OLD_WORDS = re.compile("好感|交情")
# 不是寫給玩家看的字串：交給模型的提示（companion_agent.build_system_prompt；裡面的「好感度」是程式的名字，模型照它理解數字）
MODEL_PROMPTS = {("companion_agent.py", "build_system_prompt")}


def _docstring_ids(tree):
    """模組、類別、函式的說明字串（不是玩家看的）。"""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _code_strings(path):
    """一個 .py 檔裡的字串常數（含 f 字串裡的字）：（行號, 字）。說明字串與交給模型的提示（MODEL_PROMPTS）不算。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstring_ids(tree)
    skip = [(f.lineno, f.end_lineno) for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and (path.name, f.name) in MODEL_PROMPTS]
    return [
        (node.lineno, node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
        and not any(a <= node.lineno <= b for a, b in skip)
    ]


def test_no_player_visible_old_words_in_code():
    """玩家看得到的一律叫「情誼」（explain-1）：tianxia/、server.py 的字串（說明字串與交給模型的提示不算）、web/ 的字串（註解不算）
    都不再寫「好感度」「交情」。content/ 不在這裡（事件文字歸 joy，見下一條）。"""
    found = [
        (path.name, line, text[:30])
        for path in [*sorted((ROOT / "tianxia").glob("*.py")), ROOT / "server.py"]
        for line, text in _code_strings(path) if OLD_WORDS.search(text)
    ]
    for path in sorted((ROOT / "web").iterdir()):
        source = path.read_text(encoding="utf-8")
        source = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), source, flags=re.S)  # 區塊註解（css、js）
        source = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), source, flags=re.S)  # html 註解
        for n, line in enumerate(source.splitlines(), 1):
            code = re.sub(r"(^|\s)//.*$", "", line)  # js 的行尾註解
            if OLD_WORDS.search(code):
                found.append((path.name, n, code.strip()[:30]))
    assert found == []


def test_the_old_word_finder_sees_strings_but_not_docstrings_or_prompts(tmp_path):
    """上一條的掃描本身：字串（含 f 字串）抓得到，說明字串與模型提示略過（不然上一條永遠通過）。"""
    path = tmp_path / "companion_agent.py"
    path.write_text(
        '"""模組說明：好感度。"""\n'
        'def build_system_prompt():\n    return "目前好感度 3"\n'
        'def turn(delta):\n    """好感度。"""\n    return f"（好感度 {delta}）"\n',
        encoding="utf-8",
    )
    assert [line for line, text in _code_strings(path) if OLD_WORDS.search(text)] == [6]


# content/ 裡還寫著舊說法的地方（joy 的字，這一版不改、列給 joy；見 docs/superpowers/specs/2026-10-06-新手引導-待joy潤的句子.md）
CONTENT_OLD_WORDS = {("hints.json", "h_recruit")}


def _old_words_in(node, where, file, out):
    if isinstance(node, dict):
        where = node.get("id", where)
        for value in node.values():
            _old_words_in(value, where, file, out)
    elif isinstance(node, list):
        for value in node:
            _old_words_in(value, where, file, out)
    elif isinstance(node, str) and OLD_WORDS.search(node):
        out.add((file, where))


def test_the_old_words_left_in_content_are_the_listed_ones():
    import json

    out = set()
    for path in sorted((ROOT / "content").rglob("*.json")):
        _old_words_in(json.loads(path.read_text(encoding="utf-8")), None, path.name, out)
    assert out == CONTENT_OLD_WORDS


def _with_bond(content):
    content.hints.hints.append(HintDef(id="h_bond", by="mentor", text="情誼到 {signature}，他會教你。"))


def _box_key(game):
    box = game.guide_box()
    return None if box is None else box["key"]


def test_the_bond_hint_fires_once_on_the_first_socialize(hints_content, world, monkeypatch):
    _with_bond(hints_content)
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    monkeypatch.setattr(Game, "_socialize", lambda self, prepared=None: ["你四處結交了一番。"])
    game.state.player.location = "town"
    game.choose("act:socialize")
    assert _box_key(game) == "h_bond" and "h_bond" in game.state.player.hints_seen
    assert game.guide_box()["text"] == "情誼到 70，他會教你。"  # 數字照設定（signature_affinity）
    assert "【想起師父說過】情誼到 70，他會教你。" in game.state.journal[0].guide  # 記進這一則江湖紀錄
    game.guide_ack()
    game.choose("act:socialize")
    assert _box_key(game) is None and [n.id for n in game.state.player.hint_queue] == []  # 說過就不再說


def test_the_bond_hint_waits_out_the_first_talk(hints_content, world):
    """第一次跟人物談話（求見也算）：對話開著時框不出（不把「告辭」擠出第一屏），告辭之後上框。"""
    _with_bond(hints_content)
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    game.state.player.location = "town"
    with _talking(hints_content, game):
        game.choose("call:mate")
        assert game.state.player.pending_companion == "mate"
        assert _box_key(game) is None and [n.id for n in game.state.player.hint_queue] == ["h_bond"]
        game.choose("talk:leave")
    assert _box_key(game) == "h_bond"


def _state(content):
    from tianxia.state import new_game_state

    return new_game_state(content, "甲")


def test_the_bond_hint_numbers_come_from_the_config():
    content = real_content()
    note = hints.note_for(_state(content), content, "h_bond")
    assert f"情誼到 {content.config.signature_affinity}，" in note.text and "{" not in note.text
    content.config.signature_affinity = 55
    assert "情誼到 55，" in hints.note_for(_state(content), content, "h_bond").text


@pytest.mark.parametrize("change, message", [
    (lambda d: d["hints"][0].update(text="到 {nope} 再說。"), "不認得的 {nope}"),  # 寫錯名字：框上會留著大括號
    (lambda d: d["hints"][0].update(season_one="第一季到 {oops} 再說。"), "不認得的 {oops}"),
    (lambda d: d["hints"][3].update(season_one="引薦人不寫這一句。"), "不寫 season_one"),
])
def test_a_bad_placeholder_or_season_line_is_refused_at_load(hints_root, change, message):
    from test_hints import _reload

    from tianxia.content import ContentError

    with pytest.raises(ContentError, match=re.escape(message)):
        _reload(hints_root, change)


def test_the_bond_hint_mentions_the_news_only_in_season_one(on):
    """「情誼夠深，還會透露些風聲」（伏筆的對話片段、機緣的話題）只有第一季的規則開著才是真的（HintDef.season_one）。"""
    first = Game.new(on, "乙", rng=random.Random(0))  # 這一季照週末設定開：蓋了第一季的章
    assert "風聲" in hints.note_for(first.state, on, "h_bond").text
    plain = real_content()  # 同一季，但設定的開關關著：beta 的規則
    beta = Game.new(plain, "甲", rng=random.Random(0))
    assert "風聲" not in hints.note_for(beta.state, plain, "h_bond").text


def test_the_signature_art_threshold_is_the_config(content, game):
    """本命武學的門檻跟提示寫的是同一個數（Config.signature_affinity，以前是 companion_agent 裡的常數）。"""
    content.config.signature_affinity = 10
    ch = content.characters["mate"]
    game.state.player.affinities["mate"] = 9
    assert companion_agent._maybe_grant_signature_skill(game.state, content, ch, "mate") == []
    game.state.player.affinities["mate"] = 10
    assert companion_agent._maybe_grant_signature_skill(game.state, content, ch, "mate")[0].startswith("你與韓鐵情誼深厚")


# ── 三、體力：點體力條看怎麼回；建角色送回體丹記一行；快滿時說為什麼 ─────────────────────────────


def _help(game):
    return game.status_data()["stamina_help"]


def test_the_stamina_help_reads_the_config(game):
    cfg = game.content.config
    cfg.time_scale, cfg.stamina_regen_seconds, cfg.stamina_max = 1.0, 180, 150
    cfg.newbie_stamina_multiplier, cfg.rest_regen_multiplier = 1, 2
    cfg.beta_free_refill, cfg.stamina_pill_restore = False, 100
    assert _help(game) == [
        "體力每 3 分鐘回 1 點，滿 150 就不再回。",
        "打坐時體力回復 ×2；坐著不能做別的，隨時可以起身。",
        f"回體丹一顆回 100 點（還有 {game.state.player.stamina_pills} 顆），按體力條右端的「丹」服下。",
    ]
    cfg.stamina_regen_seconds, cfg.stamina_max, cfg.rest_regen_multiplier, cfg.stamina_pill_restore = 120, 250, 3, 150
    cfg.newbie_stamina_multiplier = 3
    help_now = _help(game)
    assert help_now[0] == "體力每 2 分鐘回 1 點，滿 250 就不再回。"
    assert help_now[1].startswith("新手期：開季後的") and help_now[1].endswith("內，體力回復 ×3（你還在新手期）。")
    assert help_now[2].startswith("打坐時體力回復 ×3，跟新手期疊乘")
    assert "一顆回 150 點" in help_now[3]
    cfg.time_scale = 2.0  # 遊戲時間跑得比現實快：現實裡每 1 分鐘就回 1 點
    assert _help(game)[0].startswith("體力每 1 分鐘回 1 點")
    cfg.beta_free_refill, cfg.beta_free_refill_label = True, "補滿"
    assert _help(game)[-1] == "測試期間按體力條上的「補滿」直接補滿，不花回體丹。"


def test_the_newbie_window_is_written_in_real_time_for_this_season(on, tmp_path):
    """新手期 18 個季曆天：週末設定（2.5 天的季）是現實約 13 個小時；14 天的季（beta）是 3 天（roster.newbie 的同一個比例）。
    季長照這一季開季時蓋的章（同一個世界裡換了設定也一樣）。"""
    from tianxia.sqlite_world import open_world

    game = Game.new(on, "乙", rng=random.Random(0))
    assert "新手期：加入這一季後的約 13 個小時內，體力回復 ×3（你還在新手期）。" in _help(game)
    plain = real_content()
    plain.config.auto_open_first_season = True
    beta = Game.new(plain, "甲", rng=random.Random(0), world=open_world(tmp_path / "beta.db"))
    assert "新手期：開季後的 3 天內，體力回復 ×3（你還在新手期）。" in _help(beta)
    beta.state.world.time = 4 * 86400  # 開季四天：過了
    assert "新手期：開季後的 3 天內，體力回復 ×3（你的新手期已經過了）。" in _help(beta)


def test_the_stamina_help_leaves_out_the_pill_button_when_there_is_none(prologue_content, world):
    """序章裡體力條上沒有丹的鈕（status 的 pills 是 None）：說明也不提它。"""
    hut = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    assert hut.status_data()["pills"] is None
    assert not any("丹" in line for line in _help(hut))


def test_a_new_character_gets_a_journal_line_for_the_gift(content):
    game = Game.new(content, "沈浪", rng=random.Random(0))
    head = game.state.journal[0]
    assert head.tag == "賽季開始" and head.lines[-1] == howto.gift_line(content)
    assert head.lines[-1] == f"內測贈禮：回體丹 {content.config.beta_gift_stamina_pills} 顆，一顆回 {content.config.stamina_pill_restore} 點體力，按體力條右端的「丹」服下。"
    assert sum(1 for e in game.state.journal if e.tag == "賽季開始") == 1  # 接在開場那一則裡，不另起一則


def test_no_gift_no_line_and_the_refill_wording(content):
    content.config.beta_gift = False
    game = Game.new(content, "沈浪", rng=random.Random(0))
    assert not any("內測贈禮" in line for e in game.state.journal for line in e.lines)
    content.config.beta_gift, content.config.beta_free_refill = True, True
    other = Game.new(content, "柳青", rng=random.Random(0), world=game.world)
    assert other.state.journal[0].lines[-1].endswith("測試期間體力條上的「補滿」不花丹，丹先留著。")


def test_the_gift_line_does_not_show_on_the_first_screen_of_the_hut(prologue_content, world):
    """序章第一屏的「剛剛」照舊什麼都不放（開場那一則是江湖上的事，T7 審查 I2）：贈禮那一行接在開場那一則裡，江湖紀錄看得到。"""
    hut = Game.new(prologue_content, "沈浪", rng=random.Random(0), world=world, prologue=True)
    assert hut.now_entry_html() == ""
    assert any(line.startswith("內測贈禮") for line in hut.state.journal[0].lines)


def test_the_full_stamina_note_says_why():
    from tianxia import guide

    assert guide.FULL_STAMINA_NOTE == "體力將滿：滿了就不再回，別讓它浪費。"


def test_the_full_stamina_note_shows_when_nearly_full(game):
    from tianxia import guide

    game.skip_tutorial()
    game.state.player.stamina = game.content.config.stamina_max
    assert guide.FULL_STAMINA_NOTE in guide.next_hint(game.state, game.content, game.world)
