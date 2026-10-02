"""江湖紀錄：每次行動寫成一則 JournalEntry（engine），舊存檔的 log 轉成紀錄，以及「剛剛」卡片與紀錄列的 HTML。"""
import json

from conftest import FixedRandom

from tianxia import journal
from tianxia.engine import LOG_BREAK, Game
from tianxia.save import load_game, save_game
from tianxia.state import JournalEntry

HOUR = 3600


def latest(game):
    return game.state.journal[0]


# ── 每種行動寫成的紀錄 ─────────────────────────────────


def test_new_game_opens_with_the_season_intro(game):
    assert len(game.state.journal) == 1
    entry = latest(game)
    assert (entry.title, entry.tag) == ("測試劇本", "賽季開始")
    assert entry.lines == ["測試開始。", "【說書人】先探索一下。"]  # 地點描述留給場景，不寫進紀錄
    assert (entry.changes, entry.battle_id, entry.time) == ([], None, 0.0)


def test_move_entry_drops_the_location_description(game):
    game.choose("move:lake")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("前往 湖邊", "", [], [])
    assert game.location_text() in game.state.log  # 原始訊息照舊留在 log
    assert len(game.state.journal) == 2


def test_move_entry_keeps_guide_messages(game):
    game.choose("act:explore")
    game.choose("choice:1")  # 把醉漢打發掉
    game.choose("move:lake")
    entry = latest(game)
    assert entry.title == "前往 湖邊"
    assert entry.lines == ["✔ 引導完成", "【說書人】看看地圖。"]


def test_explore_that_meets_an_event_tags_it_and_drops_the_intro(game):
    game.choose("act:explore")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("探索小鎮", "遇上【醉漢】")
    assert "一名醉漢撞上了你。" not in entry.lines and "【醉漢】" not in entry.lines
    assert entry.lines == ["✔ 引導完成", "【說書人】去湖邊。"]
    assert entry.changes == ["銀兩 +5"]  # 引導獎勵是數值變化


def test_explore_that_finds_nothing(game):
    game.state.player.tutorial_step = 3  # 引導已走完，不會多出引導的訊息
    game.choose("move:lake")
    game.state.player.seen_events.add("scroll")  # 湖邊唯一的探索事件只出現一次
    game.choose("act:explore")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("探索湖邊", "", ["你四處走走，一無所獲。"])


def test_qiyu_is_tagged_as_such(game):
    game.choose("move:lake")
    game.choose("act:explore")
    assert latest(game).tag == "遇上奇遇【殘卷】"


def test_socialize_entry(game):
    game.choose("act:socialize")
    assert (latest(game).title, latest(game).tag) == ("交遊・小鎮", "遇上【拜師】")


def _give_player_a_winning_wugong(game):
    """讓玩家確定打得過 thug（難度 5）：自創一門威力夠高的武學。"""
    game.create_skill("測試長拳", "武學")


def test_train_entry_carries_the_battle_summary_and_gains(game):
    from conftest import FixedRandom

    game.choose("move:lake")
    _give_player_a_winning_wugong(game)
    game.rng = FixedRandom(0.99)  # 好運氣，確保是大勝或險勝（算進 WIN_TIERS）
    game._draft = journal.Draft("歷練・湖邊")
    msgs = game._squad_encounter("thug")
    journal.add_entry(game.state, game._draft.entry(game.state.world.time, msgs))
    game._log(msgs)
    game._draft = None
    record = game.state.battles[0]
    entry = latest(game)
    assert entry.title == "歷練・湖邊"
    assert entry.tag == f"{record.tier}水寇小隊"
    assert entry.battle_id == record.id == 1
    assert entry.changes == [
        "經驗 +20（每人）", "銀兩 +5", "心得 +10", "氣血 -16", "內傷 +3",
    ]  # 經驗的寫法和戰鬥卡片一致；氣血與內傷是打完的代價（氣血設計 §1.3）
    assert entry.lines == ["（寇亂 -1）"]  # 湖邊 train_trend kou:-1
    assert f"⚔ 湖邊：{record.tier}水寇小隊" in game.state.log


def test_choice_entry_names_the_event_and_the_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("醉漢・逼問", "本人出手・成功")  # 空隊伍時只有本人
    assert entry.lines == ["他全招了。", "（寇亂 -5）"]
    assert entry.changes == ["善名 +2"]
    assert "▸ 逼問" in game.state.log and "（本人出手——成功）" in game.state.log


def test_self_check_choice_entry(game):
    game.state.pending_event = "insight"
    game.rng = FixedRandom(0.99)
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("調息・運氣衝關", "本人・失敗", ["氣息一亂，只得作罷。"])


def test_choice_entry_with_a_battle(game):
    game.choose("move:lake")
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
    「歷練」這個分類，chain_a 原本標的 actions=["train"] 在新制度下不會被任何行動觸發，
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
    assert entry.lines == ["你閉關靜修，預計 4 小時後出關；閉關期間氣血回復加倍。"]
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


def test_menxia_changes_are_written_but_failures_are_not(game):
    assert game.create_skill("", "武學") == ["得先取個名字。"]
    assert len(game.state.journal) == 1
    game.create_skill("測試長拳", "武學")
    entry = latest(game)
    assert entry.title == "門下"
    assert "自創了一門武學" in entry.tag
    assert game.create_skill("另一門", "武學") == ["你已經有一門武學了，同時只能練一門。"]
    assert len(game.state.journal) == 2  # 失敗不會再寫一則新紀錄
    assert any("你已經有一門武學了" in line for line in game.state.log)  # 失敗訊息仍留在 log


def test_menxia_entries_merge_only_when_nothing_else_happened_in_between(game):
    game.create_skill("測試長拳", "武學")
    game.state.world.time = 600
    game.choose("move:lake")
    game.practice("武學")
    game.state.world.time = 1200
    game.practice("武學")
    assert [e.title for e in game.state.journal] == ["門下", "前往 湖邊", "門下", "測試劇本"]
    assert latest(game).time == 1200


def test_view_map_writes_an_entry_only_when_it_finishes_a_guide_step(game):
    game.view_map()
    assert len(game.state.journal) == 1  # 引導還沒走到「看地圖」：只記下看過地圖
    game.state.player.flags.discard("看過地圖")
    game.state.player.tutorial_step = 2  # 下一步就是看地圖
    game.view_map()
    entry = latest(game)
    assert (entry.title, entry.lines) == ("翻看地圖", ["✔ 引導完成", "【說書人】去闖吧。"])


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
    """湖邊探索剛好遇上遭遇戰、順便完成一步新手引導（獎勵銀兩 5）：把唯一的湖邊探索事件
    標成已經看過，逼 explore 落到隨機遭遇戰那條路（見 engine.py::_encounter），
    train_event_chance=1.0 保證真的觸發。"""
    game.content.tutorial.steps[0].done_when.action = "explore"
    game.content.config.train_event_chance = 1.0
    game.state.player.seen_events.add("scroll")
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    game.choose("move:lake")
    game.choose("act:explore")


def test_changes_with_the_same_label_are_added_up(game):
    guided_train(game)
    entry = latest(game)
    assert entry.changes == [
        "經驗 +20（每人）", "銀兩 +10", "心得 +10", "氣血 -16", "內傷 +3",
    ]  # 對手的 5 兩＋引導獎勵 5 兩（同標籤相加）
    assert entry.lines == ["（寇亂 -1）", "✔ 引導完成", "【說書人】去湖邊。"]  # 湖邊 train_trend kou:-1


def test_battle_card_extra_shows_what_the_card_does_not(game):
    guided_train(game)
    assert game.shows_battle_card()
    extra = game.battle_extra_html()
    assert "✔ 引導完成" in extra and "【說書人】去湖邊。" in extra
    assert '<span class="tx-chg tx-up">銀兩 +5</span>' in extra  # 卡片上只有對手給的 5 兩
    assert "經驗" not in extra and "心得" not in extra  # 卡片上已經有了


def test_battle_card_extra_skips_card_notes_and_event_markers(game):
    game.state.player.tutorial_step = 1  # 跳過第一步，這次遭遇戰不該混進引導訊息
    game.content.config.train_event_chance = 1.0
    game.state.player.seen_events.add("scroll")
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    game.state.player.member.exp = 90
    game.choose("move:lake")
    game.choose("act:explore")
    assert "沈浪升到第 2 級！" in latest(game).lines and "沈浪升到第 2 級！" in game.state.battles[0].notes
    assert game.battle_extra_html() == ""  # 升級已經寫在卡片的「結果」裡
    game.choose("move:town")
    assert game.battle_extra_html() == ""  # 沒有顯示戰鬥卡片時沒有補充


def test_new_season_starts_a_fresh_journal(game):
    game.choose("move:lake")
    game.advance(2 * 24 * HOUR)
    game.choose("season:new")
    assert [e.title for e in game.state.journal] == ["測試劇本"]


def test_journal_keeps_the_newest_thirty(game):
    for i in range(40):
        game.state.player.stamina = 150
        game.choose("move:lake" if i % 2 == 0 else "move:town")
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


def test_old_save_file_without_a_journal_loads_and_converts(tmp_path, content, game):
    game.choose("move:lake")
    dump = game.state.model_dump(mode="json")
    del dump["journal"]
    path = tmp_path / "old.json"
    path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    state = load_game(path)
    assert state.journal == []
    entries = Game(content, state).state.journal
    assert [e.title for e in entries] == ["【湖邊】危險 ★★", "══ 測試劇本 ══"]


def test_journal_survives_a_save_round_trip(tmp_path, game):
    game.content.config.train_event_chance = 1.0
    game.state.player.seen_events.add("scroll")
    _give_player_a_winning_wugong(game)
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    game.choose("move:lake")
    game.choose("act:explore")
    path = tmp_path / "沈浪.json"
    save_game(game.state, path)
    loaded = load_game(path)
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
    game.content.config.train_event_chance = 1.0
    game.state.player.seen_events.add("scroll")
    from conftest import FixedRandom

    game.rng = FixedRandom(0.99)
    game.choose("move:lake")
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
