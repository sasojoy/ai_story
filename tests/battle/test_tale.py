"""戰記（tianxia/tale.py；Joy 2026-10-29，原稱戰役話本）：收場的決戰整理成料 → 模型寫字 → 組成一篇 → 存進旁邊的小檔。

守三件事：**玩家原話一字不改**（不經過模型）、**模型寫壞或叫不動照樣有一篇可看**（模板版）、
**模型寫的字不准夾阿拉伯數字或「假人」那幾個字**。畫面那一半在 tests/web/test_tale_web.py。
"""
from __future__ import annotations

from conftest import real_content

from tianxia import tale
from tianxia.battle_instance import BattleInstance, BattleParticipant, BattleRoundRecord, GambleMoment

SIDES = {"guan": "官軍", "huang": "黃巾軍"}


def _fighter(name: str, faction: str, **kw) -> BattleParticipant:
    return BattleParticipant(name=name, faction=faction, neili=100.0, neili_cap=100.0, **kw)


def _battle(**kw) -> BattleInstance:
    """收場的一場黃巾決戰：兩個人，黃巾那邊的霜刃第二回合放手一搏成了，官軍的鐵鍋第三回合倒下。"""
    shuang = _fighter("霜刃", "huang", gambles_won=1, gambles=[
        GambleMoment(name="霜刃", faction="huang", text="包圍城頭那一隊", rate=55, won=True, round=2),
    ])
    tiehuo = _fighter("鐵鍋", "guan", fell_round=3, led_rounds=2)
    base = dict(
        battle_id="huangjin_showdown", phase="ended", record_id=41, trend=28,
        participants={"霜刃": shuang, "鐵鍋": tiehuo},
        outcome_title="黃巾大勝", outcome_reason="黃巾在第二回合壓上去", outcome_side="huang",
        highlight=shuang.gambles[0],
    )
    return BattleInstance(**{**base, **kw})


def _rounds() -> list[BattleRoundRecord]:
    """三回合：第一幕兩回合、第二幕一回合（rounds_per_act 不重算，照回合自己記的 act_index）。
    戰局往下＝往 factions[1]（黃巾）那一邊走：BattleDef 的第一個陣營才是 trend 的正向方。"""
    return [
        BattleRoundRecord(id=1, act_index=0, round_number=1, resolved_real=1000.0, trend_after=45),
        BattleRoundRecord(id=2, act_index=0, round_number=2, resolved_real=1100.0, trend_after=36),
        BattleRoundRecord(id=3, act_index=1, round_number=3, resolved_real=1200.0, trend_after=28),
    ]


def _material(**kw):
    content = real_content()
    definition = content.battles["huangjin_showdown"]
    return tale.gather(definition, _battle(**kw), _rounds(), season=8, side_names=SIDES)


# ── 引擎備的料 ──


def test_the_material_follows_the_rounds_not_the_whole_script():
    """只寫打到的幕（第三幕沒結算過就不寫），幕的標題照內容，結果與勝負的關鍵照收場的那一場。"""
    m = _material()
    assert m.battle_name == "黃巾決戰" and m.title == "黃巾決戰戰記" and m.season == 8
    assert m.result == "黃巾大勝" and m.reason == "黃巾在第二回合壓上去"
    assert [a.title for a in m.acts] == ["兩軍對陣", "鏖戰正酣"]  # 第三幕「決勝時刻」沒打到


def test_the_player_line_is_copied_word_for_word():
    """玩家原話一字不改，而且掛在他那一幕、記著他站哪一邊。"""
    said = [b.said for a in _material().acts for b in a.beats if b.said is not None]
    assert len(said) == 1
    assert said[0].line == "包圍城頭那一隊" and said[0].who == "霜刃" and said[0].side == "黃巾軍"


def test_who_fell_and_which_side_pushed_come_from_the_engine():
    first, second = _material().acts
    assert any("霜刃放手一搏，成了。" == b.fact for b in first.beats)
    assert any("鐵鍋倒在這一幕。" == b.fact for b in second.beats)  # 第三回合在第二幕
    assert second.beats[-1].fact == "黃巾軍壓了上去。"  # 戰局偏黃巾（不露數字）


def test_an_even_act_says_so_instead_of_naming_a_side():
    rounds = _rounds()
    rounds[-1] = rounds[-1].model_copy(update={"trend_after": tale.CENTER})
    content = real_content()
    m = tale.gather(content.battles["huangjin_showdown"], _battle(), rounds, season=8, side_names=SIDES)
    assert m.acts[-1].beats[-1].fact == tale.EVEN_LINE


def test_the_cast_puts_the_most_dramatic_first_and_writes_a_fact_for_each():
    cast = _material().cast
    assert [c.name for c in cast] == ["霜刃", "鐵鍋"] and cast[0].side == "黃巾軍"
    assert cast[0].fact == "放手一搏成了一次。"
    assert "倒在第三回合。" in cast[1].fact  # 數字寫中文（引擎自己那幾句）


# ── 組成整篇（模型寫的字只是填空）──


def test_without_a_model_every_beat_still_has_the_engine_line():
    page = tale.plain(_material())
    assert page.status == "ready" and page.title == "黃巾決戰戰記" and page.result == "黃巾大勝"
    assert all(scene.text for act in page.acts for scene in act.scenes)
    assert [c.line for c in page.cast] == [c.fact for c in _material().cast]
    assert page.acts[-1].no == tale.CLOSE_NO and page.acts[0].no == ""  # 收場那一幕寫「收場」，其餘讓網頁寫「第N回」


def test_the_model_text_fills_the_beats_and_the_player_line_survives():
    m = _material()
    beat = m.acts[0].beats[1].id  # 放手一搏那一拍
    page = tale.compose(m, {beat: ("暮色", "霜刃立於陣前。\n她看著城頭。")}, {"霜刃": "全場最敢的一個。"})
    scene = next(s for a in page.acts for s in a.scenes if s.said is not None)
    assert scene.head == "暮色" and scene.text == "霜刃立於陣前。\n她看著城頭。"
    assert scene.said.line == "包圍城頭那一隊"  # 模型碰不到玩家原話
    assert page.cast[0].line == "全場最敢的一個。"
    assert page.acts[0].scenes[0].text == m.acts[0].beats[0].fact  # 模型沒寫到的那一拍照引擎那一句


# ── 請模型寫（B 段）──


class _Client:
    """假的 client：回一份寫好的 TaleReply。"""

    def __init__(self, reply: dict):
        self.reply, self.kwargs = reply, {}

    def chat_structured(self, messages, model, **kwargs):
        self.kwargs = kwargs
        return model.model_validate(self.reply)


def test_no_client_means_the_template_version():
    assert tale.write(None, _material()) == ({}, {})


def test_the_required_fields_are_forced_into_the_schema():
    """scenes、cast 都有預設值：沒寫進 required（而且語法強制）的話模型回 {} 也合法，整篇靜靜變成模板版。"""
    client = _Client({"scenes": [], "cast": []})
    tale.write(client, _material())
    assert client.kwargs["required_fields"] == ["scenes", "cast"] and client.kwargs["require_in_schema"] is True


def test_what_the_model_writes_is_screened():
    m = _material()
    ids = [b.id for a in m.acts for b in a.beats]
    client = _Client({"scenes": [
        {"id": ids[0], "head": "開場", "text": "兩軍在城下列開。"},
        {"id": ids[1], "head": "", "text": "霜刃一聲喝，帶著 3 個人撲上去。"},  # 阿拉伯數字：丟掉
        {"id": "9-9", "head": "", "text": "這一拍不存在。"},  # 名單外：丟掉
    ], "cast": [
        {"name": "霜刃", "line": "全場最敢。"},
        {"name": "鐵鍋", "line": "這個假人倒得很快。"},  # 不准出現的字：丟掉
        {"name": "沒這個人", "line": "插進來的。"},
    ]})
    scenes, cast = tale.write(client, m)
    assert list(scenes) == [ids[0]] and scenes[ids[0]] == ("開場", "兩軍在城下列開。")
    assert cast == {"霜刃": "全場最敢。"}
    page = tale.compose(m, scenes, cast)
    assert page.cast[1].line == m.cast[1].fact  # 被丟掉的照引擎那一句


def test_the_output_budget_grows_with_the_tale():
    """2026-10-31 線上：3 幕 12 拍＋6 人的名錄 1400 寫不完，cast 被截掉、整篇變模板句。預算照拍數與名錄加，小場面不低於原本的下限。"""
    m = _material()
    client = _Client({"scenes": [], "cast": []})
    tale.write(client, m)
    assert client.kwargs["num_predict"] == tale.predict_budget(m) >= tale.NUM_PREDICT
    beats = sum(len(a.beats) for a in m.acts)
    big = tale.Material(record_id=1, season=8, battle_name="長社", result="官軍勝", reason="",
                        acts=m.acts * 3, cast=m.cast * 3)
    assert tale.predict_budget(big) >= tale.PREDICT_PER_SCENE * beats * 3 + tale.PREDICT_PER_CAST * len(m.cast) * 3


def test_a_scene_that_copies_the_player_line_or_names_someone_else_is_dropped():
    """2026-10-31 線上那一篇：原話在散文裡又抄一次（底下金線引言又一次），還有一拍寫成另一拍的人。都照引擎那一句。"""
    m = _material()
    beat = m.acts[0].beats[1]  # 霜刃放手一搏那一拍
    assert beat.said is not None
    for text in ("霜刃大喝：包圍城頭那一隊！", "鐵鍋提刀衝上城頭。", "霜刃與鐵鍋同時撲上城頭。"):
        scenes, _ = tale.write(_Client({"scenes": [{"id": beat.id, "text": text}], "cast": []}), m)
        assert beat.id not in scenes, text
    scenes, _ = tale.write(_Client({"scenes": [{"id": beat.id, "text": "霜刃一聲斷喝，帶人撲上城頭。"}], "cast": []}), m)
    assert scenes[beat.id][1] == "霜刃一聲斷喝，帶人撲上城頭。"
    assert "不要引" in tale.messages(m)[1]["content"]


def test_the_same_text_on_two_beats_falls_back_on_both():
    m = _material()
    ids = [b.id for a in m.acts for b in a.beats if b.said is None][:2]
    same = "城下塵土飛揚。"
    scenes, _ = tale.write(_Client({"scenes": [{"id": i, "text": same} for i in ids], "cast": []}), m)
    assert not set(ids) & set(scenes)


def test_a_model_that_blows_up_falls_back_to_the_template():
    class _Boom:
        def chat_structured(self, *a, **k):
            raise RuntimeError("模型掛了")

    assert tale.write(_Boom(), _material()) == ({}, {})


# ── 存放 ──


def test_the_store_keeps_one_tale_per_battle_and_lists_the_newest_first(tmp_path):
    store = tale.TaleStore(tmp_path / "x-tale.sqlite")
    assert store.get(41) is None and store.done(8) == set() and store.listing(8) == []
    first = tale.plain(_material())
    store.put(41, first)
    store.put(42, tale.plain(_material(record_id=42)))
    assert store.get(41).title == "黃巾決戰戰記" and store.done(8) == {41, 42}
    assert [record_id for record_id, _ in store.listing(8)] == [42, 41]  # 新的在前
    assert store.listing(9) == []


def test_writing_the_same_battle_twice_keeps_the_first(tmp_path):
    """全服看同一篇：同一場寫兩次以先寫的為準。"""
    store = tale.TaleStore(tmp_path / "x-tale.sqlite")
    store.put(41, tale.compose(_material(), {}, {"霜刃": "先寫的。"}))
    store.put(41, tale.compose(_material(), {}, {"霜刃": "後寫的。"}))
    assert store.get(41).cast[0].line == "先寫的。"


def test_a_broken_row_reads_as_missing(tmp_path):
    """讀不懂的舊格式當作沒有（背景會重寫），不是整頁爆掉。"""
    import sqlite3

    path = tmp_path / "x-tale.sqlite"
    tale.TaleStore(path).put(41, tale.plain(_material()))
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE tales SET data = ? WHERE record_id = ?", ("{壞掉的", 41))
    assert tale.TaleStore(path).get(41) is None and tale.TaleStore(path).listing(8) == []
