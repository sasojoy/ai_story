"""跨段那一刻（名聲設計 3.3、十一之二第 6 條）與得失後面的差距（6.4）。"""
import random

from conftest import real_content, renown_unscaled

from tianxia import journal, renown
from tianxia.engine import Game
from tianxia.journal import Draft
from tianxia.state import new_game_state


def test_annotate_merges_and_appends_the_gap():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats.update({"fame": 25, "good": 18, "evil": 3})
    out = renown.annotate(["名望 +1", "銀兩 +5", "名望 +1", "善名 +2", "惡名 +1"], s, c)
    assert out == ["名望 +2（離「威震州郡」還差 25）", "銀兩 +5", "善名 +2（離「州郡大俠」還差 12）",
                   "惡名 +1（善名還比惡名高，稱號照善名算）"]
    s.player.stats.update({"good": 6, "evil": 6})
    assert renown.annotate(["惡名 +1"], s, c) == ["惡名 +1（稱號照善名算，惡名要比善名高才換路）"]
    s.player.stats["fame"] = 95
    assert renown.annotate(["名望 +1"], s, c) == ["名望 +1（已是天下聞名）"]
    assert renown.annotate(["名望 -1"], s, c) == ["名望 -1"]  # 扣的不接
    assert renown.annotate(["名望 +1", "名望 -1"], s, c) == []  # 一加一扣：沒動就不寫
    once = renown.annotate(["名望 +1"], s, c)
    assert renown.annotate(once, s, c) == once  # 接過差距的不再動


def test_first_look_only_records_then_up_writes_once():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats["fame"] = 24
    first = renown.watch(s, c, day=1)
    assert first.first and first.lines == [] and s.player.renown_seen.fame == 1
    s.player.stats["fame"] = 25
    up = renown.watch(s, c, day=1)
    assert up.up == ["名動一方"] and up.lines[0] == "你的名號傳開了，江湖上漸漸有人稱你「名動一方」。"
    assert up.lines[1].startswith("這一段多了：九四折")
    s.player.stats["fame"] = 24
    down = renown.watch(s, c, day=1)
    assert down.lines == ["江湖上漸漸不再提你「名動一方」的名號。"]
    s.player.stats["fame"] = 25
    assert renown.watch(s, c, day=1).lines == []  # 沒超過這一季到過的最高段：不再寫
    s.player.stats["fame"] = 24
    assert renown.watch(s, c, day=1).lines == []  # 掉段一個遊戲日最多一次
    s.player.stats["fame"] = 25
    renown.watch(s, c, day=2)
    s.player.stats["fame"] = 24
    assert renown.watch(s, c, day=2).lines == ["江湖上漸漸不再提你「名動一方」的名號。"]  # 換了一天


def test_switching_path_is_said():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats.update({"good": 6, "evil": 0})
    renown.watch(s, c, day=1)
    s.player.stats["evil"] = 8
    crossed = renown.watch(s, c, day=1)
    assert crossed.lines[0] == "江湖上不再叫你「江湖遊俠」，改叫你「綠林好漢」。"


def test_virtue_up_is_said():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.stats["good"] = 3
    renown.watch(s, c, day=1)
    s.player.stats["good"] = 15
    assert renown.watch(s, c, day=1).lines[0] == "江湖上開始有人叫你「一方豪俠」。"


def _game(c):
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    return g


def test_an_action_appends_the_crossing_and_the_gold_tag():
    c = renown_unscaled(real_content("week7"))
    g = _game(c)
    g.state.player.stats["fame"] = 24
    g._log(["（看一眼）"])  # 第一次看（新角色在建立時就看過了）：只記段、寫一則說明，開場那一則照舊在最上面
    assert g.state.player.renown_told and any(e.title == renown.TOLD_TITLE for e in g.state.journal)
    assert g.state.journal[0].title != renown.TOLD_TITLE
    g._write("測試", ["名望 +1"])
    g.state.player.stats["fame"] = 25
    g._log(["名望 +1"])
    entry = g.state.journal[0]
    assert entry.title == "測試"
    assert entry.changes[0] == "名望 +1（離「威震州郡」還差 25）"
    assert journal.renown_mark("名動一方") in entry.changes
    assert "你的名號傳開了，江湖上漸漸有人稱你「名動一方」。" in entry.lines
    html = journal.card_html(entry)
    assert 'class="tx-chg tx-renown"' in html and 'data-act="renown-open"' in html and "名號傳開・名動一方 ›" in html


def test_a_crossing_found_while_syncing_gets_its_own_entry():
    c = renown_unscaled(real_content("week7"))
    g = _game(c)
    g._log(["（看一眼）"])
    g.state.player.stats["fame"] = 30
    g._renown_after(synced=True)
    entry = g.state.journal[0]
    assert entry.title == renown.TOLD_TITLE and entry.lines[0].startswith("你的名號傳開了")


def test_entries_written_while_syncing_merge_their_fame_and_show_the_gap(monkeypatch):
    """FB-292：同步時補進來的那一則（決戰收場後回來補的「長社火攻・官軍大勝」：時間是收場那一刻、比此刻早；軍餉那一份名望與立功
    那一份名望各一行），也合成一行、接差距，跟同一場的戰報一樣；跨段那一則「名聲」照舊另起。同步之前就在的那幾則不動。"""
    c = renown_unscaled(real_content("week7"))
    g = _game(c)
    g.state.player.stats["fame"] = 46
    g._log(["（看一眼）"])
    older = Draft("舊的一則").entry(g.state.world.time, ["之前的事"])
    older.changes = ["名望 +1"]
    journal.add_entry(g.state, older)

    def deliver(self):  # 照 _deliver_battle_results → _file_showdown 補進來的那一則
        entry = Draft("長社火攻・官軍大勝").entry(self.state.world.time - 600, ["軍餉發下來了。"])
        entry.changes = ["銀兩 +40", "名望 +4", "名望 +2"]
        journal.add_entry(self.state, entry)
        self.state.player.stats["fame"] = 52

    monkeypatch.setattr(Game, "_deliver_battle_results", deliver)
    g.sync(1_000_000.0)
    delivered = next(e for e in g.state.journal if e.title == "長社火攻・官軍大勝")
    assert delivered.changes == ["銀兩 +40", "名望 +6（離「天下聞名」還差 38）"]
    assert older.changes == ["名望 +1"]
    told = next(e for e in g.state.journal if e.title == renown.TOLD_TITLE and journal.renown_mark("威震州郡") in e.changes)
    assert "名望" not in "".join(told.changes).replace(journal.renown_mark("威震州郡"), "")


def test_told_once_across_seasons():
    c = renown_unscaled(real_content("week7"))
    g = _game(c)
    g._log(["（看一眼）"])
    g.state.player.renown_seen = None  # 換季：角色重來、段清掉，說明過了照記
    g._log(["（再看一眼）"])
    assert sum(1 for e in g.state.journal if e.title == renown.TOLD_TITLE) == 1


def test_switch_off_writes_nothing():
    c = renown_unscaled(real_content("week7"))
    c.config.renown.titles = False
    s = new_game_state(c, "甲")
    s.player.stats["fame"] = 99
    assert renown.watch(s, c, day=1).lines == [] and renown.annotate(["名望 +1"], s, c) == ["名望 +1"]
    g = _game(c)
    g._log(["（看一眼）"])
    assert all(e.title != renown.TOLD_TITLE for e in g.state.journal) and g.state.player.renown_seen is None
