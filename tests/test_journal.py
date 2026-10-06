"""江湖紀錄：每次行動寫成一則 JournalEntry（engine），舊存檔的 log 轉成紀錄，以及「剛剛」卡片與紀錄列的 HTML。"""
import json
import re
from html import escape

from conftest import FixedRandom, walk_to

from tianxia import journal
from tianxia.engine import LOG_BREAK, Game
from tianxia.characters import name_key, open_characters
from tianxia.models import ExploreMix
from tianxia.state import JournalEntry

HOUR = 3600


def latest(game):
    return game.state.journal[0]


def _train(game, kind="武學"):
    """在修練頁鍛鍊一成：先把內容裡的一門功夫配到身上（第一成），再按「鍛鍊」——江湖紀錄多一則「修練」。
    自創已經作廢，開局送的功夫也不在 fixture 的設定裡，所以測試直接配一門。"""
    member = game.state.player.member
    if kind == "內功":
        if member.neigong_id is None:
            member.neigong_id, member.neigong_level = "breath", 1
    elif member.wugong_id is None:
        member.wugong_id, member.wugong_level = "fist", 1
    game.state.player.stats["xinde"] = max(game.state.player.stats.get("xinde", 0), 100)  # 練成要花心得
    return game.practice(kind)


def _explore_only(game, branch):
    """探索三選一：讓探索一定走某一支（"event"／"wild"／"insight"）。這些測試看的是事件或戰鬥寫成的紀錄，
    不是探索抽到哪一支；不指定的話就要靠亂數剛好落在那一支的比例裡。"""
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={branch: 1})]


# ── 每種行動寫成的紀錄 ─────────────────────────────────


def test_new_game_opens_with_the_season_intro(game):
    assert len(game.state.journal) == 1
    entry = latest(game)
    assert (entry.title, entry.tag) == ("測試劇本", "賽季開始")
    assert entry.lines == ["測試開始。"]  # 地點描述留給場景，不寫進紀錄
    assert entry.guide == ["【說書人】先探索一下。"]  # 說書人的第一句在對話框；江湖紀錄記在 guide（引導重做設計 8.1）
    assert (entry.changes, entry.battle_id, entry.time) == ([], None, 0.0)


def test_move_entry_drops_the_location_description(game):
    walk_to(game, "lake")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("前往 湖邊", "步行約 3 分鐘", [], [])
    assert game.location_text() in game.state.log  # 原始訊息照舊留在 log
    assert len(game.state.journal) == 2  # 出發那則，抵達時併進同一則
    assert entry.time == 180.0  # 時間換成抵達的時間


def test_an_arrival_after_other_entries_gets_its_own_entry(game):
    game.choose("move:lake")
    _train(game)  # 路上在門下練功：紀錄多了一則
    game.advance(game.state.player.journey.arrive_at[-1] - game.state.world.time)
    assert [(e.title, e.tag) for e in game.state.journal[:3]] == [
        ("前往 湖邊", "抵達"), ("修練", game.state.journal[1].tag), ("前往 湖邊", "步行約 3 分鐘"),
    ]


def test_a_trip_finished_after_a_station_entry_is_tagged_as_arrived(game):
    game.state.world.flags.add("cave_open")
    game.state.player.tutorial_step = 1  # 「去湖邊」：中途抵達湖邊時有引導訊息
    game.travel("cave", "walk")
    _train(game)  # 路上在門下練功：出發那則不再是最新的
    journey = game.state.player.journey
    game.advance(journey.arrive_at[0] - game.state.world.time)  # 走到湖邊：另起一則「途中」
    assert (latest(game).title, latest(game).tag) == ("前往 寶洞（途經 湖邊）", "途中")
    game.advance(journey.arrive_at[1] - game.state.world.time)  # 走到寶洞：併進那一則，已經走完了
    entry = latest(game)
    assert game.state.player.journey is None
    assert (entry.title, entry.tag) == ("前往 寶洞（途經 湖邊）", "抵達")
    assert entry.guide[0] == "✔ 引導完成"


def test_move_entry_keeps_guide_messages(game):
    _explore_only(game, "event")
    game.choose("act:explore")
    game.choose("choice:1")  # 把醉漢打發掉
    walk_to(game, "lake")
    entry = latest(game)
    assert entry.title == "前往 湖邊"
    assert (entry.lines, entry.guide) == ([], ["✔ 引導完成", "【說書人】看看地圖。"])


def test_a_new_insight_or_art_line_gets_the_shine():
    """「拿到新東西」那一行掃過一道光：悟得意境、學會基礎武學、合成出新武學、修練晉品都算；重複悟到只是化成心得，不算。"""
    for line in (
        "你悟得了「風」的意境（屬快）！",
        "你學會了【長拳】（武學・下品・屬剛）。",
        "你以【長拳】融入「風」，衍生出一門武學【追風拳】（下品・屬快）！\n一句話說明。\n這是江湖上第一次有人合出這一門——從此它就叫這個名字。",
        "「風」與「火」在你心中交融，化成「燎原」（屬陽）！\n這是江湖上第一次有人悟出這個意境。",
        "【長拳】修練有成，從下品晉為中品！",
        # 武學＋武學：新衍生出的一門、與三種「合到舊的」（拿到的是別人首創的那一門，對這個玩家一樣是新東西）
        "你把【長拳】與【腿法】合而為一，衍生出一門武學【追風拳】（下品・屬快）！\n這是江湖上第一次有人合出這一門——從此它就叫這個名字。",
        "你把【長拳】與【腿法】合而為一，合出來的竟是一門已有的武學【追風拳】（下品・屬快）！\n這一門由甲首創。",
        "你以【長拳】融入「風」，合出來的竟是一門已有的武學【追風拳】（下品・屬快）！\n這一門由甲首創。",
        "「風」與「火」在你心中交融，化成的竟是已有的「燎原」（屬陽）！\n這個意境由甲首悟。",
    ):
        assert journal._line_class(line) == "tx-line tx-new", line
    for line in (
        "你又悟到一次「風」，這份體會化成了心得。",
        "你在湖邊靜下心來，看了好一陣。",
        "路邊有獵戶設的套索，套住的山雞早被什麼東西叼走了，只剩一地毛。你學會了那個結的打法。",  # 路上見聞，不是新功法
        "老獵戶說他悟得了一個道理。",
        "心得 -5",
        # 合出來的是自己已經有的：什麼也沒拿到，不亮
        "這兩門合出來還是【追風拳】，你已經有了——換一門吧。",
        "這一爐合出來還是【追風拳】，你已經有了——換一組試試吧。",
        "這兩個合起來還是「燎原」，你已經悟得了。",
        # 這一爐才摸清的新配方、合到的還是自己已經有的（FB-078）：也什麼都沒拿到，不亮
        "這一爐的路數，竟又歸到【追風拳】——你多摸清了一條練法（【長拳】＋「風」）。不收心得、體力。",
        "這一爐的路數，竟又歸到「燎原」——你多摸清了一條悟法（「風」＋「火」）。不收心得、體力。",
        "兩門都要是你會的武學。",
    ):
        assert journal._line_class(line) == "tx-line", line


def test_explore_that_meets_an_event_tags_it_and_drops_the_intro(game):
    _explore_only(game, "event")
    game.choose("act:explore")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("探索小鎮", "遇上【醉漢】")
    assert "一名醉漢撞上了你。" not in entry.lines and "【醉漢】" not in entry.lines
    assert (entry.lines, entry.changes) == ([], [])  # 「剛剛」只放這次行動的結果（引導重做設計 8.1.3）
    assert entry.guide == ["✔ 引導完成", "銀兩 +5", "【說書人】去湖邊。"]  # 引導與獎勵記在 guide


def test_explore_that_finds_nothing(game):
    game.state.player.tutorial_step = 3  # 引導已走完，不會多出引導的訊息
    walk_to(game, "lake")
    game.state.player.seen_events.add("scroll")  # 湖邊唯一的探索事件只出現一次
    game.content.locations["lake"].enemies = []  # 探索三選一：三支都做不了才是一無所獲
    game.content.config.explore_mix = [ExploreMix(kind="wild", tags=[], weights={"insight": 0, "wild": 35, "event": 25})]
    game.choose("act:explore")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("探索湖邊", "", ["你四處走走，一無所獲。"])


def test_qiyu_is_tagged_as_such(game):
    walk_to(game, "lake")
    game.content.config.rare_explore_chance = 1.0  # 探索三選一：奇遇判定最優先
    game.choose("act:explore")
    assert latest(game).tag == "遇上奇遇【殘卷】"


def test_socialize_entry(game):
    game.choose("act:socialize")
    assert (latest(game).title, latest(game).tag) == ("交友・小鎮", "遇上【拜師】")


def _give_player_a_winning_wugong(game):
    """讓玩家確定打得過 thug（難度 5）：配上一門內容裡的武學。"""
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 1


def test_train_entry_carries_the_battle_summary_and_gains(game):
    from conftest import FixedRandom

    walk_to(game, "lake")
    _give_player_a_winning_wugong(game)
    game.rng = FixedRandom(0.99)  # 好運氣，確保是大勝或險勝（算進 WIN_TIERS）
    game._draft = journal.Draft("遊歷・湖邊")
    msgs = game._squad_encounter("thug")
    journal.add_entry(game.state, game._draft.entry(game.state.world.time, msgs))
    game._log(msgs)
    game._draft = None
    record = game.state.battles[0]
    entry = latest(game)
    assert entry.title == "遊歷・湖邊"
    assert entry.tag == f"{record.tier}水寇小隊"
    assert entry.battle_id == record.id == 1
    assert entry.changes == [
        "經驗 +20（每人）", "銀兩 +5", "心得 +10", "氣血 -16", "內傷 +3",
    ]  # 經驗的寫法和戰鬥卡片一致；氣血與內傷是打完的代價（氣血設計 §1.3）
    assert entry.lines == ["（寇亂 -1）"]  # 湖邊 train_trend kou:-1
    assert f"⚔ 湖邊：{record.tier}水寇小隊" in game.state.log


def test_choice_entry_names_the_event_and_the_check(game):
    _explore_only(game, "event")
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("醉漢・逼問", "成功")  # 結果不寫誰出手（企劃者 2026-10-05：一律是本人）
    assert entry.lines == ["他全招了。", "（寇亂 -5）"]
    assert entry.changes == ["善名 +2"]
    assert "▸ 逼問" in game.state.log and "（成功）" in game.state.log


def test_self_check_choice_entry(game):
    game.state.pending_event = "insight"
    game.rng = FixedRandom(0.99)
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("調息・運氣衝關", "失敗", ["氣息一亂，只得作罷。"])


def test_choice_entry_with_a_battle(game):
    walk_to(game, "lake")
    game.choose("act:socialize")
    game.choose("choice:0")
    record = game.state.battles[0]
    entry = latest(game)
    assert entry.title == "挑戰・應戰"
    assert entry.tag == f"{record.tier}翻江龍"  # 難度 200，新手打不過
    assert entry.battle_id == record.id
    assert (entry.lines, entry.changes) == (["你敗了。"], ["銀兩 -10"])


def test_choice_that_leads_to_another_event(game):
    """chain_a/chain_b 事件鏈：直接把 chain_a 設成待處理事件，不依賴哪個行動觸發它
    （新制度下 explore/socialize 才會隨機遇上事件，跟事件骨架裡的 actions 標記已經沒有
    「遊歷」這個分類，chain_a 原本標的 actions=["train"] 在新制度下不會被任何行動觸發，
    這裡只測「選項串接下一個事件」本身這件事，跳過「怎麼遇到 chain_a」）。"""
    game.state.pending_event = "chain_a"
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("跟蹤・繼續", "遇上【倉庫】", [])
    assert entry.battle_id is None


def test_seclusion_start_and_finish(game):
    game.seclude(4)
    entry = latest(game)
    assert (entry.title, entry.tag) == ("閉關", "4 小時")
    assert entry.lines == ["你閉關靜修，預計現實 4 小時後出關；閉關期間氣血回復加倍。"]
    game.advance(4 * HOUR)
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("出關", "4.0 小時", [], ["心得 +75"])
    assert entry.time == 4 * HOUR
    assert len(game.state.journal) == 3  # 期間的江湖傳聞不另外寫紀錄


def test_breaking_seclusion_early(game):
    game.seclude(4)
    game.advance(HOUR)
    game.choose("act:break")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("提前出關", "1.0 小時", [], ["心得 +19"])


def test_seclusion_refused_is_still_written(game):
    _explore_only(game, "event")
    game.choose("act:explore")  # 有事件待處理，不能閉關
    game.seclude(4)
    assert (latest(game).title, latest(game).lines) == ("閉關", ["你現在無法閉關。"])


def test_time_passing_writes_no_entry(game):
    before = list(game.state.journal)
    game.advance(3 * HOUR)  # 虛擬玩家每小時都在放傳聞
    assert any(line.startswith("【江湖傳聞】") for line in game.state.log)
    assert game.state.journal == before


def test_world_news_while_time_passes_is_written_and_merged(game):
    game.advance(20 * HOUR)  # 翻江龍每小時把寇亂推高 1：到 50 時水寇封江
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("江湖大事", "水寇封江！", [])
    assert entry.time == 20 * HOUR
    game.advance(10 * HOUR)  # 到 60 時主線進入第二幕：接在同一則裡
    entry = latest(game)
    assert entry.title == "江湖大事" and entry.time == 30 * HOUR
    assert entry.lines == ["水寇封江！", "【主線】第2幕「運河封鎖」：運河被封了。"]  # 一般的傳聞不寫進來
    assert entry.tag == "【主線】第2幕「運河封鎖」：運河被封了。"
    assert len(game.state.journal) == 2
    game.choose("move:lake")
    game.state.world.trends["kou"] = 79
    game.advance(HOUR)  # 前一則不是江湖大事：另起一則
    assert [e.title for e in game.state.journal[:3]] == ["江湖大事", "前往 湖邊", "江湖大事"]
    assert latest(game).tag == "水寇稱霸！"


def test_invalid_option_writes_no_entry(game):
    game.choose("move:cave")
    assert len(game.state.journal) == 1


# FB-024：在修練頁完成新手引導的那一步，「✔ 引導完成」、獎勵與說書人的下一步也要進江湖紀錄，
# 跟在江湖頁（choose()）完成時一樣；沒完成引導的門下動作，紀錄跟以前一模一樣。

GUIDE_REWARD = 7
GUIDE_XINDE = 5  # 獎勵也給心得：紀錄裡的心得變化只能算一次（門下紀錄自己也會算心得的增減）


def _guide_waits_for(game, goal):
    """把引導換成「第一步＝goal（獎勵銀兩 7、心得 5）、第二步＝出城」，停在第一步。"""
    from tianxia.models import Effect, TutorialGoal, TutorialStep

    game.content.tutorial.steps = [
        TutorialStep(
            id="t4", text="先修練。", done_when=goal,
            reward=Effect(stats={"silver": GUIDE_REWARD, "xinde": GUIDE_XINDE}),
        ),
        TutorialStep(id="t5", text="出城。", done_when=TutorialGoal(action="move")),
    ]
    game.state.player.tutorial_step = 0


def _speaker(game):
    return game.content.tutorial.speaker


def test_a_first_practice_that_finishes_a_has_wugong_step_writes_it_into_the_journal(game):
    from tianxia.models import TutorialGoal

    _guide_waits_for(game, TutorialGoal(has_wugong=True))
    msgs = _train(game)
    assert "✔ 引導完成" not in msgs and "✔ 引導完成" in game.state.player.guide_done  # 走對話框（引導重做設計 8.1.3）
    entry = latest(game)
    assert entry.title == "修練" and "精進至第2成" in entry.tag
    assert entry.guide == [  # 跟 choose() 那條路同一種寫法
        "✔ 引導完成", f"銀兩 +{GUIDE_REWARD}", f"心得 +{GUIDE_XINDE}", f"【{_speaker(game)}】出城。"]
    assert entry.changes == ["心得 -1"]  # 練成花的 1 點心得記在 changes；引導的獎勵只在 guide，沒有算兩次
    assert game.state.player.tutorial_step == 1


def test_practicing_that_finishes_a_guide_step_writes_it_into_the_journal(game):
    from tianxia.models import TutorialGoal

    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 3
    game.state.player.stats["xinde"] = 10  # 第 3 成升第 4 成花 3 點
    _guide_waits_for(game, TutorialGoal(action="practice"))
    game.practice("武學")
    entry = latest(game)
    assert entry.title == "修練"
    assert entry.guide[0] == "✔ 引導完成" and entry.guide[-1] == f"【{_speaker(game)}】出城。"
    assert f"銀兩 +{GUIDE_REWARD}" in entry.guide and f"銀兩 +{GUIDE_REWARD}" not in entry.changes


def test_forging_that_finishes_a_guide_step_writes_it_into_the_journal(game):
    from unittest import mock

    from tianxia import naming
    from tianxia.models import TutorialGoal

    game.state.player.member.wugong_id = "fist"
    game.state.player.insights = ["feng"]
    game.state.player.stats["xinde"] = 100
    _guide_waits_for(game, TutorialGoal(action="practice"))
    reply = naming.NameReply(name="鐵腕勁", description="一句話。")
    with mock.patch.object(game.client, "chat_structured", return_value=reply):
        msgs = game.forge("fist", ["feng"])
    assert "✔ 引導完成" not in msgs and "✔ 引導完成" in game.state.player.guide_done  # 合成結果也不夾引導（8.1.3）
    entry = latest(game)
    assert entry.title == "煉製" and entry.tag == "合成【鐵腕勁】"
    assert entry.guide[0] == "✔ 引導完成" and entry.guide[-1] == f"【{_speaker(game)}】出城。"
    assert f"銀兩 +{GUIDE_REWARD}" in entry.guide and f"銀兩 +{GUIDE_REWARD}" not in entry.changes


def test_practice_and_forging_are_titled_after_their_tabs(game):
    """FB-047：江湖紀錄照動作寫「修練」（鍛鍊、療傷、改練）與「煉製」（合成、合併），不再寫「門下」；
    煉製不併進前面那則鍛鍊。"""
    from unittest import mock

    from tianxia import naming

    _train(game)
    game.practice("武學")
    assert latest(game).title == "修練" and len([e for e in game.state.journal if e.title == "修練"]) == 1
    game.state.player.insights = ["feng", "huo"]
    reply = naming.NameReply(name="鐵腕勁", description="一句話。")
    with mock.patch.object(game.client, "chat_structured", return_value=reply):
        game.forge("fist", ["feng"])
    assert [e.title for e in game.state.journal[:2]] == ["煉製", "修練"]
    assert "合成【鐵腕勁】" == latest(game).tag
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge(None, ["feng", "huo"])
    assert [e.title for e in game.state.journal[:2]] == ["煉製", "修練"]  # 合併也標「煉製」，併進同一則
    assert latest(game).tag.startswith("合併「")
    assert not any(e.title == "門下" for e in game.state.journal)


# ── FB-073：煉製的結果那一句寫進江湖紀錄，拿到新東西的那幾行才亮 ────────────────────────────
# 以前紀錄裡只有結果標記（「合成【X】」「合併「X」」），完整的那一句只在煉製頁的回話裡，journal._NEW_THING 的句型
# （衍生出一門／合出來的竟是一門已有的／在你心中交融……）一次都配不到。現在那一句寫進這一則的敘事。


def _forger(game, arts=()):
    """身上一門武學（粗淺拳腳）、兩個意境（風、火）、心得夠；arts 是功法庫裡另外給的功法。"""
    p = game.state.player
    p.member.wugong_id, p.arts, p.insights, p.stats["xinde"] = "basic_fist", list(arts), ["feng", "huo"], 100


def _forge(game, art, insight_ids, name, other_art=None):
    from unittest import mock

    from tianxia import naming

    reply = naming.NameReply(name=name, description="一句話。")
    with mock.patch.object(game.client, "chat_structured", return_value=reply):
        return game.forge(art, insight_ids, other_art=other_art)


def shines(card: str) -> list[str]:
    """畫出來的 HTML 裡會亮的那幾行（掃光的那一行）。"""
    return re.findall(r'<div class="tx-line tx-new">(.*?)</div>', card)


def test_a_fuse_writes_its_result_sentence_into_the_journal_and_it_shines(game):
    _forger(game)
    msgs = _forge(game, "basic_fist", ["feng"], "旋風腿")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("煉製", "合成【旋風腿】")  # 結果標記照舊
    assert entry.lines == [msgs[0]] and msgs[0].startswith("你以【粗淺拳腳】融入「風」，衍生出一門武學【旋風腿】")
    assert journal._line_class(entry.lines[0]) == "tx-line tx-new"
    assert shines(game.now_entry_html()) == [escape(msgs[0]).replace("\n", "<br>")]  # 「剛剛」卡片
    assert shines(journal.rows_html([entry])) == shines(game.now_entry_html())  # 江湖紀錄那一列點開也亮
    assert entry.changes == ["心得 -5", "體力 -5"]  # 數值變化沒有多一份、也沒有少


def test_a_merge_writes_its_result_sentence_into_the_journal_and_it_shines(game):
    _forger(game)
    msgs = _forge(game, None, ["feng", "huo"], "燎原")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("煉製", "合併「燎原」")
    assert entry.lines == [msgs[0]] and msgs[0].startswith("「風」與「火」在你心中交融，化成「燎原」")
    assert shines(game.now_entry_html()) == [escape(msgs[0]).replace("\n", "<br>")]
    assert entry.changes == ["心得 -5", "體力 -5"]


def test_a_blend_writes_its_result_sentence_into_the_journal_and_it_shines(game):
    _forger(game, arts=["lake_kick"])
    msgs = _forge(game, "basic_fist", [], "踏浪拳", other_art="lake_kick")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("煉製", "合成【踏浪拳】")
    assert entry.lines == [msgs[0]] and "合而為一，衍生出一門武學【踏浪拳】" in msgs[0]
    assert shines(game.now_entry_html()) == [escape(msgs[0]).replace("\n", "<br>")]
    assert entry.changes == ["心得 -5", "體力 -5"]


def test_landing_on_an_art_someone_else_made_shines_too(game):
    """合到舊的（別人首創的那一門）對這個玩家一樣是新東西：那一句寫進紀錄、也亮。"""
    from unittest import mock

    from tianxia import fusion, naming
    from tianxia.state import new_game_state

    content = game.content
    other = new_game_state(content, "乙")
    other.player.member.wugong_id, other.player.insights, other.player.stats["xinde"] = "basic_fist", ["feng"], 100
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name="旋風腿", description="一句話。")
    fusion.fuse(other, content, game.world, client, "basic_fist", "feng")
    content.config.land_chance_per_candidate, content.config.land_chance_cap = 1.0, 1.0  # 有候選就一定合到舊的
    _forger(game, arts=["lake_kick"])
    msgs = _forge(game, "lake_kick", ["feng"], "不會用到的名字")
    assert "合出來的竟是一門已有的武學【旋風腿】" in msgs[0]
    entry = latest(game)
    assert entry.tag == "合成【旋風腿】" and entry.lines == [msgs[0]]
    assert shines(game.now_entry_html()) == [escape(msgs[0]).replace("\n", "<br>")]


def test_landing_on_what_you_already_own_writes_nothing_and_does_not_shine(game):
    """合出來的是你已經有的：被拒絕、不收錢、不寫紀錄；那句拒絕的話也不亮。三種合成都一樣。"""
    _forger(game, arts=["lake_kick"])
    _forge(game, "basic_fist", ["feng"], "旋風腿")
    _forge(game, "basic_fist", [], "踏浪拳", other_art="lake_kick")
    _forge(game, None, ["feng", "huo"], "燎原")
    before = list(game.state.journal)
    for refused in (
        _forge(game, "basic_fist", ["feng"], "旋風腿"),
        _forge(game, "lake_kick", [], "踏浪拳", other_art="basic_fist"),  # 反過來放也是同一個配方
        _forge(game, None, ["huo", "feng"], "燎原"),
    ):
        assert len(refused) == 1 and "已經" in refused[0]
        assert journal._line_class(refused[0]) == "tx-line"
    assert game.state.journal == before and len(shines(game.now_entry_html())) == 3  # 前三爐的那三行照舊亮、沒多一行


def test_two_forges_in_a_row_keep_both_sentences_and_both_shine(game):
    """連做幾爐併成一則（同一種連續的門下動作）：每一爐的那一句都在、照順序、各一次，每一句都亮；數值變化加總。"""
    _forger(game)
    first = _forge(game, "basic_fist", ["feng"], "旋風腿")[0]
    second = _forge(game, None, ["feng", "huo"], "燎原")[0]
    crafts = [e for e in game.state.journal if e.title == "煉製"]
    assert len(crafts) == 1
    entry = crafts[0]
    assert entry.lines == [first, second] and entry.tag == "合併「燎原」"
    cfg = game.content.config
    assert entry.changes == [f"心得 -{cfg.fuse_xinde + cfg.merge_xinde}", f"體力 -{cfg.fuse_stamina + cfg.merge_stamina}"]
    card, row = game.now_entry_html(), journal.rows_html([entry])
    wanted = [escape(s).replace("\n", "<br>") for s in (first, second)]
    assert shines(card) == wanted and shines(row) == wanted
    for sentence in wanted:
        assert card.count(sentence) == 1 and row.count(sentence) == 1  # 每一句只畫一次（FB-070）


def test_three_different_forges_in_a_row_all_shine(game):
    """合成、武學＋武學、合併接著做：三種句型各自亮、各一行。"""
    _forger(game)
    said = [
        _forge(game, "basic_fist", ["feng"], "旋風腿")[0],
        _forge(game, "basic_fist", [], "烈風拳", other_art="旋風腿")[0],
        _forge(game, None, ["feng", "huo"], "燎原")[0],
    ]
    (entry,) = [e for e in game.state.journal if e.title == "煉製"]
    assert entry.lines == said and entry.tag == "合併「燎原」"
    assert shines(game.now_entry_html()) == [escape(s).replace("\n", "<br>") for s in said]


def test_an_old_forge_entry_without_a_sentence_still_merges_with_a_new_one(game):
    """舊存檔裡的煉製只有結果標記、沒有敘事：新的一爐併進去時，舊的那一爐用它的標記當那一行（journal._story），照舊能畫。"""
    _forger(game)
    journal.add_entry(game.state, JournalEntry(
        time=game.state.world.time, title="煉製", tag="合成【舊的一爐】", changes=["心得 -5", "體力 -5"]), merge=True)
    sentence = _forge(game, None, ["feng", "huo"], "燎原")[0]
    entry = latest(game)
    assert entry.lines == ["合成【舊的一爐】", sentence] and entry.changes == ["心得 -10", "體力 -10"]
    assert shines(game.now_entry_html()) == [escape(sentence).replace("\n", "<br>")]


def test_the_guide_lines_do_not_swallow_the_menxia_story_when_entries_merge(game):
    """連續的門下動作併成一則：每次動作的那句話都還在、照順序；引導的那幾行併在 guide。"""
    from tianxia.models import TutorialGoal

    _train(game, "內功")
    first_tag = latest(game).tag
    _guide_waits_for(game, TutorialGoal(has_wugong=True))
    _train(game)
    second_tag = latest(game).tag
    game.practice("武學")
    entries = [e for e in game.state.journal if e.title == "修練"]
    assert len(entries) == 1  # 還是併成一則
    lines = entries[0].lines
    assert lines.index(first_tag) < lines.index(second_tag) and "✔ 引導完成" not in lines
    assert entries[0].guide[0] == "✔ 引導完成" and entries[0].guide[-1] == f"【{_speaker(game)}】出城。"


def test_menxia_without_finishing_a_guide_step_writes_exactly_what_it_used_to(game):
    from tianxia.models import TutorialGoal

    _guide_waits_for(game, TutorialGoal(action="view_map"))  # 修練頁做的事不會完成這一步
    _train(game)
    entry = latest(game)
    assert entry.title == "修練" and "精進至第2成" in entry.tag
    assert entry.lines == [] and entry.changes == ["心得 -1"]  # 沒有引導、也沒有別的敘事，只有練成花掉的心得
    assert game.state.player.tutorial_step == 0
    game.state.player.tutorial_step = len(game.content.tutorial.steps)  # 引導已走完：同一回事
    game.practice("武學")
    assert latest(game).lines == [entry.tag, latest(game).tag]  # 兩次練功併成一則，敘事只有兩次動作自己


# FB-029：完成引導的門下動作，那次動作自己的那句話也放在 lines 第一行（之後併進來的門下動作才擠不掉它），
# 「剛剛」與紀錄列畫這一則時，那句話只出現一次。


def test_a_menxia_action_that_finishes_a_guide_step_shows_its_sentence_once(game):
    import html

    from tianxia.models import TutorialGoal

    _guide_waits_for(game, TutorialGoal(has_wugong=True))
    _train(game)
    said = latest(game).tag
    assert game.latest_entry_html().count(html.escape(said)) == 1
    assert "✔ 引導完成" not in game.latest_entry_html()  # 「剛剛」不夾引導（引導重做設計 8.1.3）
    assert journal.rows_html([latest(game)]).count(html.escape(said)) == 1
    assert "✔ 引導完成" in journal.rows_html([latest(game)])  # 江湖紀錄照舊看得到

    game.practice("武學")  # 接著再做一個門下動作：併進同一則，那句話還在、仍只一次
    entries = [e for e in game.state.journal if e.title == "修練"]
    assert len(entries) == 1 and said in entries[0].lines
    assert game.latest_entry_html().count(html.escape(said)) == 1
    assert journal.rows_html(entries).count(html.escape(said)) == 1


def test_menxia_entries_that_finish_no_guide_step_render_as_before(game):
    from tianxia.models import TutorialGoal

    _guide_waits_for(game, TutorialGoal(action="view_map"))
    _train(game)
    assert 'class="tx-line' not in game.latest_entry_html()  # 只有結果標記，沒有敘事
    game.practice("武學")
    entry = latest(game)
    assert entry.lines[0] != entry.tag
    assert journal._lines(entry.lines) in game.latest_entry_html()  # 兩次動作的敘事照舊一行一行畫出來


# FB-070 (c)：同一種連續的門下動作併成一則時，結果標記是最新那次的那句話、敘事是每一次照順序（journal._story），
# 所以標記又是敘事的最後一行。「剛剛」卡片以前標記畫一次、敘事再畫一次：做了兩次看起來像三次。


def shown(card: str) -> list[str]:
    """「剛剛」卡片上畫出來的每一句，照畫的順序：標題旁的結果標記（有的話），再來是底下的敘事。"""
    return re.findall(r'<span class="tx-tag">(.*?)</span>', card) + re.findall(r'<div class="tx-line[^"]*">(.*?)</div>', card)


def test_twice_practising_reads_as_two_lines_on_the_just_now_card(game):
    _train(game)
    first = latest(game).tag
    game.practice("武學")
    second = latest(game).tag
    assert first != second
    assert shown(game.now_entry_html()) == [escape(first), escape(second)]
    assert "心得 -3" in game.now_entry_html()  # 第 1 成升第 2 成 1 點、第 2 成升第 3 成 2 點：加總照舊


def test_twice_forging_reads_as_two_lines_on_the_just_now_card(game):
    """合成接著合併（同一則「煉製」）：標題旁是最新那一爐的結果標記、底下是每一爐的那一句（FB-073 起煉製的結果那一句也寫進紀錄，
    見上面那一段），照順序、各一次，沒有哪一句重複畫；心得、體力照舊加總。"""
    from unittest import mock

    from tianxia import naming

    game.state.player.member.wugong_id = "fist"
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stats["xinde"] = 100
    with mock.patch.object(game.client, "chat_structured", return_value=naming.NameReply(name="鐵腕勁", description="一句話。")):
        fused_said = game.forge("fist", ["feng"])[0]
    fused = latest(game).tag
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        merged_said = game.forge(None, ["feng", "huo"])[0]
    merged = latest(game).tag
    assert (fused, latest(game).title) == ("合成【鐵腕勁】", "煉製") and merged.startswith("合併「")
    assert latest(game).lines == [fused_said, merged_said]
    assert shown(game.now_entry_html()) == [
        escape(merged), escape(fused_said).replace("\n", "<br>"), escape(merged_said).replace("\n", "<br>")]
    cfg = game.content.config
    assert f"體力 -{cfg.fuse_stamina + cfg.merge_stamina}" in game.now_entry_html()  # 設計 12.1：合成與合併各收一次，加總


def test_twice_melting_reads_as_two_lines_on_the_just_now_card(game):
    game.state.player.insights = ["feng", "huo"]
    first = game.melt_insight("feng")[0]
    second = game.melt_insight("huo")[0]
    assert latest(game).title == "修練" and latest(game).tag == second
    assert shown(game.now_entry_html()) == [escape(first), escape(second)]


def test_a_single_menxia_action_still_reads_as_one_tag(game):
    """只做一次：照舊只有標題旁的結果標記（沒有敘事），跟以前一樣。"""
    _train(game)
    assert shown(game.now_entry_html()) == [escape(latest(game).tag)]
    assert 'class="tx-tag"' in game.now_entry_html()


def test_menxia_changes_are_written_but_failures_are_not(game):
    assert game.forge("fist", ["feng"])  # 沒有武學也沒有意境：被擋下
    assert len(game.state.journal) == 1
    _train(game)
    entry = latest(game)
    assert entry.title == "修練"
    assert "精進至第2成" in entry.tag
    msgs = game.forge("fist", ["feng"])  # 身上有武學了，可是還沒悟到這個意境：還是被擋下
    assert msgs and len(game.state.journal) == 2  # 失敗不會再寫一則新紀錄
    assert any(msgs[0] in line for line in game.state.log)  # 失敗訊息仍留在 log


def test_menxia_entries_merge_only_when_nothing_else_happened_in_between(game):
    _train(game)
    game.state.world.time = 600
    walk_to(game, "lake")
    game.practice("武學")
    game.state.world.time = 1200
    game.practice("武學")
    assert [e.title for e in game.state.journal] == ["修練", "前往 湖邊", "修練", "測試劇本"]
    assert latest(game).time == 1200


def test_view_map_adds_the_guide_to_the_latest_entry_without_a_new_one(game):
    """打開輿圖不是一次行動：完成「看地圖」那一步時，引導接在最新一則的 guide，「剛剛」不換成一則空的「翻看地圖」。"""
    game.view_map()
    assert len(game.state.journal) == 1  # 引導還沒走到「看地圖」：只記下看過地圖
    game.state.player.flags.discard("看過地圖")
    game.state.player.tutorial_step = 2  # 下一步就是看地圖
    game.view_map()
    assert len(game.state.journal) == 1
    assert latest(game).guide[-2:] == ["✔ 引導完成", "【說書人】去闖吧。"]


def test_notice_and_skip_tutorial(game):
    game.notice("（舊存檔已備份。）", title="舊存檔已備份")
    assert (latest(game).title, latest(game).lines) == ("舊存檔已備份", ["（舊存檔已備份。）"])
    game.skip_tutorial()
    assert (latest(game).title, latest(game).tag, latest(game).lines) == ("新手引導", "已略過", [])
    log_size = len(game.state.log)
    assert game.skip_tutorial() == []  # 引導早就結束了：什麼都不做
    assert len(game.state.journal) == 3 and len(game.state.log) == log_size


# ── 戰鬥卡片底下的補充 ─────────────────────────────────


def guided_train(game):
    """湖邊遊歷打一場、順便完成一步新手引導（獎勵銀兩 5）：把引導第一步改成「遊歷」。
    （以前是逼探索落到隨機遭遇戰那條路；探索三選一之後那條路沒了，打仗就是遊歷。）"""
    game.content.tutorial.steps[0].done_when.action = "train"
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    walk_to(game, "lake")
    game.choose("act:train")


def test_a_fight_that_finishes_a_guide_step_keeps_the_reward_out_of_its_changes(game):
    """遊歷打一場、順便完成一步引導：這一則的數值變化只有這一場的（對手的 5 兩），引導的 5 兩記在 guide、走對話框。"""
    guided_train(game)
    entry = latest(game)
    assert entry.changes == ["經驗 +20（每人）", "銀兩 +5", "心得 +10", "氣血 -16", "內傷 +3"]
    assert entry.lines == ["（寇亂 -1）"]  # 湖邊 train_trend kou:-1
    assert entry.guide == ["✔ 引導完成", "銀兩 +5", "【說書人】去湖邊。"]


def test_battle_card_extra_shows_what_the_card_does_not(game):
    guided_train(game)
    assert game.shows_battle_card()
    extra = game.battle_extra_html()
    assert "✔ 引導完成" not in extra and "【說書人】" not in extra  # 引導走對話框，卡片底下不補（引導重做設計 8.1.3）
    assert "經驗" not in extra and "心得" not in extra and "銀兩" not in extra  # 卡片上已經有了


def test_battle_card_extra_does_not_repeat_a_material_the_card_already_lists(game):
    """打贏掉了素材：卡片的獲得與損失寫「精鐵砂 ×1」，那一則裡的訊息寫「獲得 精鐵砂 ×1」，是同一件事，卡片底下不再補一次。
    江湖紀錄那一則本身照舊留著那句話（紀錄頁看得到掉了什麼）。"""
    game.state.player.tutorial_step = 1  # 跳過第一步，不混進引導
    _give_player_a_winning_wugong(game)
    game.rng = FixedRandom(0.3)  # 水寇小隊難度 5：預設掉落表 50% 掉一個一階素材
    walk_to(game, "lake")
    game.choose("act:train")
    assert game.state.battles[0].materials == ["精鐵砂 ×1"] and "精鐵砂 ×1" in game.battle_card()
    assert "獲得 精鐵砂 ×1" in latest(game).lines
    assert "精鐵砂" not in game.battle_extra_html()


def test_card_leftovers_drop_what_the_card_tells_but_keep_what_it_does_not():
    """卡片講過的（結果裡的敘事、獲得與損失裡的素材與數值）不再補；卡片沒寫到的照舊補（例如別的獎勵、世界大事）。"""
    from tianxia import battlelog
    from tianxia.state import BattleRecord, Fighter

    record = BattleRecord(
        id=1, time=0, location="湖邊", kind="train", opponent="水寇", ours=[Fighter(name="沈浪", level=1)], tier="大勝",
        our_power=50, difficulty=10, exp=10, materials=["精鐵砂 ×1"], notes=["沈浪升到第 2 級！"], changes=["氣血 -17"],
    )
    entry = JournalEntry(
        time=0, title="遊歷・湖邊", tag="大勝水寇", battle_id=1,
        lines=["獲得 精鐵砂 ×1", "沈浪升到第 2 級！", "遇上【水寇】", "獲得 【破境丹】一枚——衝擊絕學時可以服下。", "【江湖大事】潁川重歸平靜。"],
        changes=["經驗 +10（每人）", "氣血 -17", "破境丹 +1"],
    )
    lines, changes = journal.card_leftovers(entry, battlelog.told_lines(record), battlelog.gains_list(record))
    assert lines == ["獲得 【破境丹】一枚——衝擊絕學時可以服下。", "【江湖大事】潁川重歸平靜。"]
    assert changes == ["破境丹 +1"]


def test_battle_card_extra_skips_card_notes_and_event_markers(game):
    game.state.player.tutorial_step = 1  # 跳過第一步，這次遭遇戰不該混進引導訊息
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    game.state.player.member.exp = 90
    walk_to(game, "lake")
    game.choose("act:train")
    assert "沈浪升到第 2 級！" in latest(game).lines and "沈浪升到第 2 級！" in game.state.battles[0].notes
    assert game.battle_extra_html() == ""  # 升級已經寫在卡片的「結果」裡
    walk_to(game, "town")
    assert game.battle_extra_html() == ""  # 沒有顯示戰鬥卡片時沒有補充


# ── 配點不換「剛剛」（計畫二最終審查 M1）──────────────────────


def _level_up_fight(game) -> int:
    """湖邊遊歷打贏一場、升到第 2 級（多 1 點屬性）：「剛剛」放這一場的戰鬥卡片。回傳那一場戰報的 id。"""
    game.state.player.tutorial_step = 1  # 跳過第一步，不混進引導
    _give_player_a_winning_wugong(game)
    game.rng = FixedRandom(0.99)
    game.state.player.member.exp = 90
    walk_to(game, "lake")
    game.choose("act:train")
    assert game.state.player.stat_points == 1 and game.shows_battle_card()
    return game.state.battles[0].id


def test_spending_a_point_keeps_the_level_up_fight_in_now(game):
    """升級那一仗打完，照著「你有 N 點屬性可以分配（點名號展開）」去配點：配點是狀態列上的動作，跟 journal.add_guide
    一樣不換「剛剛」——那一場的戰鬥卡片與卡片底下的補充照舊；「配點」那一則照樣寫進江湖紀錄、從最新一則列起。"""
    fight = _level_up_fight(game)
    fought, extra = latest(game).title, game.battle_extra_html()
    game.allocate_stat("str")
    assert latest(game).title == journal.ALLOCATE and "臂力 +1" in game.latest_entry_html()
    assert game.shows_battle_card() and game.battle_card_id() == fight
    assert game.battle_extra_html() == extra  # 補充看的是那一場那一則，不是配點那一則
    now = game.now_entry_html()
    assert fought in now and "臂力 +1" not in now


def test_the_home_page_keeps_the_fight_card_after_a_point_is_spent(game):
    """伺服器送給江湖頁的那一份：「剛剛」（card／now）照舊是那一場；江湖紀錄頁（latest＋journal）配點在最前面、那一場接在後面。"""
    import server

    fight = _level_up_fight(game)
    fought = latest(game).title
    game.allocate_stat("agi")
    view = server.main_view(game)
    assert view["card"] is not None and view["card_id"] == fight
    assert "身法 +1" not in view["now"]
    assert "身法 +1" in view["latest"] and fought in view["journal"]


def test_a_point_spent_after_a_quiet_action_leaves_that_action_in_now(game):
    """前面沒有打仗：「剛剛」放配點之前的那一則（不是空的），江湖紀錄照舊從配點列起。"""
    walk_to(game, "lake")
    before = latest(game).title
    game.state.player.stat_points = 1
    game.allocate_stat("con")
    assert not game.shows_battle_card() and game.battle_extra_html() == ""
    now = game.now_entry_html()
    assert before in now and "根骨 +1" not in now
    assert "根骨 +1" in game.latest_entry_html()


def test_now_is_not_empty_when_the_journal_holds_only_points(game):
    game.state.journal.clear()
    game.state.player.stat_points = 1
    game.allocate_stat("wis")
    assert [e.title for e in game.state.journal] == [journal.ALLOCATE]
    assert "悟性 +1" in game.now_entry_html()  # 只有配點那一則時就放它，「剛剛」不空著


def test_new_season_starts_a_fresh_journal(game):
    game.content.config.admins = [game.state.player.name]
    walk_to(game, "lake")
    game.advance(2 * 24 * HOUR)
    game.admin_next_season(now=0.0)
    assert [e.title for e in game.state.journal] == ["測試劇本"]


def test_journal_keeps_the_newest_thirty(game):
    for i in range(40):
        game.state.player.stamina = 150
        walk_to(game, "lake" if i % 2 == 0 else "town")
    entries = game.state.journal
    assert len(entries) == journal.MAX_ENTRIES == 30
    assert entries[0].title == "前往 小鎮" and entries[1].title == "前往 湖邊"  # 最新的在前


# ── 舊存檔 ─────────────────────────────────────────────


def test_legacy_log_is_converted_once(content, game):
    game.state.journal = []
    game.state.log = [
        "【小鎮】危險 ★\n\n一個小鎮。", LOG_BREAK,
        "心得不足：【吐納法】升到第2成需要 20。", LOG_BREAK, LOG_BREAK,  # 連續的分隔標記
        "▸ 上前勸架", "（韓鐵出手——失敗）", "你被一張飛來的板凳砸中。", "銀兩 -5", "", "  ", LOG_BREAK,
        "本命武學不能散功。", "【長拳】已經練到第十成。", LOG_BREAK,  # 只有失敗訊息的一組：不轉
        "銀兩 +5", LOG_BREAK,  # 只有數字的一組
        "長" * 60,  # 沒有結尾分隔標記、而且很長
    ]
    fresh = Game(content, game.state)
    entries = fresh.state.journal
    assert [e.title for e in entries] == ["長" * 40 + "…", "銀兩 +5", "▸ 上前勸架", "【小鎮】危險 ★"]
    assert entries[0].lines == ["長" * 60]  # 標題截斷時，完整的一行留在敘事裡
    assert (entries[2].lines, entries[2].changes) == (["（韓鐵出手——失敗）", "你被一張飛來的板凳砸中。"], ["銀兩 -5"])
    assert entries[3].lines == ["一個小鎮。"]
    assert all(e.time == journal.LEGACY_TIME and e.tag == "" and e.battle_id is None for e in entries)
    again = Game(content, fresh.state)
    assert again.state.journal == entries  # 只轉一次


def test_legacy_log_without_breaks_and_the_cap(content, game):
    game.state.journal = []
    game.state.log = ["舊紀錄一", "舊紀錄二"]  # 最早的存檔沒有分隔標記：整段當成一組
    assert [(e.title, e.lines) for e in Game(content, game.state).state.journal] == [("舊紀錄一", ["舊紀錄二"])]
    game.state.journal = []
    game.state.log = [x for i in range(45) for x in (f"第{i}組", LOG_BREAK)]
    entries = Game(content, game.state).state.journal
    assert len(entries) == 30 and entries[0].title == "第44組" and entries[-1].title == "第15組"
    assert journal.from_legacy_log([]) == [] and journal.from_legacy_log([LOG_BREAK, "", LOG_BREAK]) == []
    failures = [
        "心得不足：【吐納法】升到第2成需要 20。", "沒有這門武學。", "【長拳】尚在第一成，無功可散。", "沒有這個武學欄。",
        "你尚未習得這門武學。", "【吐納法】是隊中某人的本命武學，不能重複配置。", "（此刻無法這麼做。）", "你現在無法閉關。",
    ]
    assert journal.from_legacy_log([x for f in failures for x in (f, LOG_BREAK)]) == []
    kept = journal.from_legacy_log(["心得不足：【吐納法】升到第2成需要 20。", "你閉關靜修。"])
    assert [e.title for e in kept] == ["心得不足：【吐納法】升到第2成需要 20。"]  # 同一組裡還有別的事：照常轉


def test_old_save_file_without_a_journal_loads_and_converts(content, game):
    walk_to(game, "lake")
    dump = game.state.model_dump(mode="json")
    del dump["journal"]
    characters = open_characters()
    with characters.db.transaction() as conn:
        conn.execute(
            "INSERT INTO characters (key, name, is_bot, faction, data) VALUES (?, '沈浪', 0, NULL, ?)",
            (name_key("沈浪"), json.dumps(dump, ensure_ascii=False)),
        )
    state = characters.load("沈浪")
    assert state.journal == []
    entries = Game(content, state).state.journal
    assert entries[0].title == "【湖邊】危險 ★★" and entries[-1].title == "══ 測試劇本 ══"


def test_journal_survives_a_save_round_trip(game):
    _explore_only(game, "wild")  # 在湖邊探索撞上野怪，打一場
    game.state.player.seen_events.add("scroll")
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    walk_to(game, "lake")
    game.choose("act:explore")
    open_characters().save(game.state)
    loaded = open_characters().load("沈浪")
    assert loaded.journal == game.state.journal and loaded.journal[0].battle_id == 1


# ── 顯示 ──────────────────────────────────────────────


def entry(**kw):
    base = dict(time=4 * HOUR + 20 * 60, title="探索揚州城", tag="遇上【酒樓鬥毆】", lines=["✔ 引導完成"],
                changes=["銀兩 +10", "體力 -3"])
    return JournalEntry(**(base | kw))


def test_change_signs():
    assert [journal.change_class(c) for c in ("銀兩 +10", "心得 -20", "名望 +0", "奇怪的一行", "經驗 +15（每人）")] == [
        "tx-up", "tx-down", "", "", "tx-up"
    ]


def test_more_internal_injury_is_coloured_as_a_loss():
    """FB-049：內傷多了是損失（紅，跟「氣血 -17」一樣），療傷讓內傷少了是收穫（綠）；其他照正負。"""
    assert journal.change_class("內傷 +3") == "tx-down"
    assert journal.change_class("內傷 -10") == "tx-up"
    assert journal.change_class("氣血 -17") == "tx-down" and journal.change_class("銀兩 +5") == "tx-up"


def test_combine_and_subtract_changes():
    assert journal.combine_changes(["銀兩 +10", "心得 +8", "銀兩 +10", "經驗 +5（每人）", "經驗 +5（每人）"]) == [
        "銀兩 +20", "心得 +8", "經驗 +10（每人）"
    ]
    assert journal.combine_changes(["銀兩 +5", "銀兩 -5", "體力 +10.0", "奇怪的一行"]) == ["體力 +10", "奇怪的一行"]
    shown = ["心得 +10", "銀兩 +5", "經驗 +20（每人）"]
    assert journal.subtract_changes(["經驗 +20（每人）", "銀兩 +10", "心得 +10"], shown) == ["銀兩 +5"]
    assert journal.subtract_changes(["奇怪的一行", "名望 +1"], ["奇怪的一行"]) == ["名望 +1"]


def test_card_html_shows_time_title_tag_lines_and_coloured_changes():
    html = journal.card_html(entry())
    for part in ('剛剛　第1天 04:20', '探索揚州城', '遇上【酒樓鬥毆】', '✔ 引導完成',
                 '<span class="tx-chg tx-up">銀兩 +10</span>', '<span class="tx-chg tx-down">體力 -3</span>'):
        assert part in html
    assert html.index("剛剛") < html.index("探索揚州城") < html.index("✔ 引導完成") < html.index("銀兩 +10")


def test_card_html_draws_a_merged_entry_once_per_action_in_order():
    """FB-070 (c)：標記是敘事的最後一行（併成一則的門下動作）時，標記不另寫在標題旁、敘事照順序畫：N 次就是 N 行。
    一樣的一句話做了兩次（例如兩次療傷）也還是兩行；只有一行、或標記不在敘事最後的，照舊（FB-029 只看第一行）。"""
    first, second = "【鎮風手】修練有成，從下品晉為中品！", "【鎮風手】修練了一回，還差一點火候（熟練度 1）。"
    html = journal.card_html(entry(title="修練", tag=second, lines=[first, second], changes=["體力 -20"]))
    assert shown(html) == [first, second] and '<span class="tx-chg tx-down">體力 -20</span>' in html
    assert shown(journal.card_html(entry(title="修練", tag=first, lines=[first, first], changes=[]))) == [first, first]
    assert shown(journal.card_html(entry(title="修練", tag=first, lines=[first], changes=[]))) == [first]  # FB-029
    assert shown(journal.card_html(entry())) == ["遇上【酒樓鬥毆】", "✔ 引導完成"]  # 標記不在敘事裡：照舊


def test_card_html_for_a_legacy_entry_does_not_claim_just_now():
    html = journal.card_html(entry(time=journal.LEGACY_TIME))
    assert "舊紀錄" in html and "剛剛" not in html


def test_card_html_escapes_text():
    html = journal.card_html(entry(title="<b>x</b>", lines=["a & b", "{name} ${x}"], changes=[]))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "a &amp; b" in html
    assert "{name} ${x}" in html  # gr.HTML 把值原樣插進樣板、不再解讀：大括號不必處理
    assert "tx-chgs" not in html  # 沒有數值變化時不畫那一排


def test_extra_html():
    html = journal.extra_html(["✔ 引導完成"], ["銀兩 +10"])
    assert html.startswith('<div class="tx-extra">') and "✔ 引導完成" in html
    assert '<span class="tx-chg tx-up">銀兩 +10</span>' in html
    assert journal.extra_html([], []) == ""


def test_a_heard_fragment_line_is_marked_so_the_card_can_fold_it_to_one_line():
    """FB-074：「你聽到一件事：聽說皇甫嵩說過：…」常有兩三行高，卡片收成一行、點了看全文。標記由伺服器畫（class tx-hearsay，
    認的是引擎自己的 FRAGMENT_PREFIX），網頁不必去讀句子的字；其他的行不帶這個標記，「拿到新東西」的掃光照舊。"""
    heard = journal.fragment_line("聽說皇甫嵩說過：「兵有奇變，不在眾寡。」")
    for html in (journal.extra_html([heard, "✔ 引導完成"], []), journal.card_html(entry(lines=[heard, "✔ 引導完成"]))):
        classes = re.findall(r'<div class="([^"]*)">([^<]*)</div>', html)
        marked = [text for cls, text in classes if "tx-hearsay" in cls]
        assert marked == [escape(heard)] and html.count("tx-hearsay") == 1
        assert next(cls for cls, text in classes if text == escape(heard)) == "tx-line tx-new tx-hearsay"
        assert next(cls for cls, text in classes if "引導完成" in text) == "tx-line"
    assert "tx-hearsay" not in journal.extra_html(["傳言說：你聽到一件事：不是開頭就不算"], [])  # 只認開頭的標記，不是句子裡出現這幾個字


def test_the_fight_card_extra_carries_the_hearsay_marker(game):
    fight = _level_up_fight(game)
    heard = journal.fragment_line("聽說皇甫嵩說過：「兵有奇變，不在眾寡。」")
    game.state.journal[0].lines.append(heard)  # 打完仗順便聽到一件事
    extra = game.battle_extra_html()
    assert game.battle_card_id() == fight and 'class="tx-line tx-new tx-hearsay">' + escape(heard) in extra


def test_rows_html_one_line_per_entry_with_the_story_folded_inside():
    html = journal.rows_html([entry(), entry(title="拔出兵器迎戰", tag="擊退狼群（3 回合）", time=-1.0, lines=[])])
    assert html.count('class="tx-row"') == 2
    assert "第1天 04:20" in html and "舊紀錄" in html  # 舊存檔轉來的紀錄沒有時間
    assert html.index("探索揚州城") < html.index("拔出兵器迎戰")
    # 有敘事的一列可以點開：摘要就是那一列，敘事在裡面；沒有敘事的一列就是一般的一列
    assert html.count("<details") == 1 and html.count("<summary") == 1 and "title=" not in html
    summary = html[html.index("<summary"):html.index("</summary>")]
    assert "探索揚州城" in summary and "銀兩 +10" in summary and "✔ 引導完成" not in summary
    assert html.index("</summary>") < html.index("✔ 引導完成") < html.index("</details>")
    assert journal.rows_html([], heading="江湖紀錄", empty="（沒有了。）").count("（沒有了。）") == 1
    assert journal.rows_html([], heading="江湖紀錄").startswith('<div class="tx-journal"><div class="tx-heading">江湖紀錄')


def test_game_html_helpers(game):
    _explore_only(game, "wild")  # 在湖邊探索撞上野怪，打一場
    game.state.player.seen_events.add("scroll")
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    walk_to(game, "lake")
    assert "前往 湖邊" in game.latest_entry_html()
    rows = game.journal_html(1, 5)
    assert rows.count('class="tx-row"') == 1 and "測試劇本" in rows
    assert game.journal_html(6, 30) == ""
    assert not game.shows_battle_card()
    _give_player_a_winning_wugong(game)
    game.choose("act:explore")
    assert game.shows_battle_card()  # 最新一則就是卡片上那一場
    game.practice("武學")
    assert not game.shows_battle_card()  # 之後在門下做了事：「剛剛」改顯示那一則
    assert game.battle_card() is not None
