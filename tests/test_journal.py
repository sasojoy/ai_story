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


def test_train_entry_carries_the_battle_summary_and_gains(game):
    game.choose("move:lake")
    game.choose("act:train")
    record = game.state.battles[0]
    entry = latest(game)
    assert entry.title == "歷練・湖邊"
    assert entry.tag == f"擊退水寇小隊（{record.rounds} 回合）"
    assert entry.battle_id == record.id == 1
    assert entry.changes == ["經驗 +20", "銀兩 +5", "心得 +10"]
    assert entry.lines == []
    assert f"⚔ 湖邊：擊退水寇小隊（{record.rounds} 回合）" in game.state.log


def test_train_that_meets_an_event_lists_it_as_a_line(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    entry = latest(game)
    assert entry.tag.startswith("擊退水寇小隊")
    assert entry.lines == ["遇上【跟蹤】"]
    assert "你跟了上去。" not in entry.lines


def test_choice_entry_names_the_event_and_the_check(game):
    game.rng = FixedRandom(0.0)  # 檢定必定成功
    game.choose("act:explore")
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag) == ("醉漢・逼問", "韓鐵出手・成功")
    assert entry.lines == ["他全招了。"]
    assert entry.changes == ["善名 +2"]
    assert "▸ 逼問" in game.state.log and "（韓鐵出手——成功）" in game.state.log


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
    assert entry.tag == f"不敵翻江龍，敗退（{record.rounds} 回合）"
    assert entry.battle_id == record.id
    assert (entry.lines, entry.changes) == (["你敗了。"], ["銀兩 -10"])


def test_choice_that_leads_to_another_event(game):
    game.content.config.train_event_chance = 1.0
    game.choose("move:lake")
    game.choose("act:train")
    game.choose("choice:0")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines) == ("跟蹤・繼續", "遇上【倉庫】", [])
    assert entry.battle_id is None


def test_seclusion_start_and_finish(game):
    game.seclude(4)
    entry = latest(game)
    assert (entry.title, entry.tag) == ("閉關", "4 小時")
    assert entry.lines == ["你閉關靜修，預計 4 小時後出關；閉關期間內力回復加倍。"]
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


def test_invalid_option_writes_no_entry(game):
    game.choose("move:cave")
    assert len(game.state.journal) == 1


def test_menxia_changes_are_written_but_failures_are_not(game):
    p = game.state.player
    assert "心得不足" in game.upgrade("skill:fist")[0]
    assert game.dispel("skill:family") == ["本命武學不能散功。"]
    assert game.set_loadout("player", 0, "sword") == ["你尚未習得這門武學。"]
    game.set_loadout("player", 0, "fist")  # 原本就配著：什麼都沒變
    assert len(game.state.journal) == 1
    assert any("心得不足" in line for line in game.state.log)  # 失敗訊息仍留在 log
    p.stats["xinde"] = 100
    game.upgrade("skill:fist")
    entry = latest(game)
    assert (entry.title, entry.tag, entry.lines, entry.changes) == ("門下", "【長拳】精進至第2成", [], ["心得 -20"])
    game.dispel("skill:fist")
    assert (latest(game).tag, latest(game).changes) == ("【長拳】散功，退回第一成", ["心得 +16"])
    game.upgrade("innate:mate")
    assert latest(game).tag == "【驚濤掌】精進至第2成"
    game.set_loadout("player", 0, None)
    assert (latest(game).title, latest(game).tag) == ("門下", "沈浪的第1個武學欄：（空）")
    assert len(game.state.journal) == 5


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
        "銀兩 +5", LOG_BREAK,  # 只有數字的一組
        "長" * 60,  # 沒有結尾分隔標記、而且很長
    ]
    fresh = Game(content, game.state)
    entries = fresh.state.journal
    assert [e.title for e in entries] == ["長" * 40 + "…", "銀兩 +5", "▸ 上前勸架", "心得不足：【吐納法】升到第2成需要 20。", "【小鎮】危險 ★"]
    assert entries[0].lines == ["長" * 60]  # 標題截斷時，完整的一行留在敘事裡
    assert (entries[2].lines, entries[2].changes) == (["（韓鐵出手——失敗）", "你被一張飛來的板凳砸中。"], ["銀兩 -5"])
    assert entries[4].lines == ["一個小鎮。"]
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
    game.choose("move:lake")
    game.choose("act:train")
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
    assert [journal.change_class(c) for c in ("銀兩 +10", "心得 -20", "名望 +0", "奇怪的一行")] == [
        "tx-up", "tx-down", "", ""
    ]


def test_card_html_shows_time_title_tag_lines_and_coloured_changes():
    html = journal.card_html(entry())
    for part in ('剛剛　第1天 04:20', '探索揚州城', '遇上【酒樓鬥毆】', '✔ 引導完成',
                 '<span class="tx-chg tx-up">銀兩 +10</span>', '<span class="tx-chg tx-down">體力 -3</span>'):
        assert part in html
    assert html.index("剛剛") < html.index("探索揚州城") < html.index("✔ 引導完成") < html.index("銀兩 +10")


def test_card_html_escapes_text():
    html = journal.card_html(entry(title="<b>x</b>", lines=["a & b", "{name}"], changes=[]))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html and "a &amp; b" in html
    assert "{" not in html  # 大括號也轉成實體，不會被 Gradio 的樣板誤讀
    assert "tx-chgs" not in html  # 沒有數值變化時不畫那一排


def test_rows_html_one_line_per_entry():
    html = journal.rows_html([entry(), entry(title="拔出兵器迎戰", tag="擊退狼群（3 回合）", time=-1.0)])
    assert html.count('class="tx-row"') == 2
    assert "第1天 04:20" in html and "舊紀錄" in html  # 舊存檔轉來的紀錄沒有時間
    assert html.index("探索揚州城") < html.index("拔出兵器迎戰")
    assert "✔ 引導完成" not in html.replace('title="✔ 引導完成"', "")  # 敘事只放在滑鼠提示裡
    assert journal.rows_html([], heading="江湖紀錄", empty="（沒有了。）").count("（沒有了。）") == 1
    assert journal.rows_html([], heading="江湖紀錄").startswith('<div class="tx-journal"><div class="tx-heading">江湖紀錄')


def test_game_html_helpers(game):
    game.choose("move:lake")
    assert "前往 湖邊" in game.latest_entry_html()
    rows = game.journal_html(1, 5)
    assert rows.count('class="tx-row"') == 1 and "測試劇本" in rows
    assert game.journal_html(6, 30) == ""
    assert not game.shows_battle_card()
    game.choose("act:train")
    assert game.shows_battle_card()  # 最新一則就是卡片上那一場
    game.state.player.stats["xinde"] = 100
    game.upgrade("skill:fist")
    assert not game.shows_battle_card()  # 之後在門下做了事：「剛剛」改顯示那一則
    assert game.battle_card() is not None
