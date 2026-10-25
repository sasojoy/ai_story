"""時刻表決戰的起點照哪一條戰線（企劃者 2026-10-22 選計畫 2026-10-22-長社火攻主場 第七節第 4 條：不另加主場偏移，照現在的規則補一句說明）。

領地爭奪開著的季，時刻表決戰（寫了戰線的：長社火攻、宛城、廣宗、天命之爭）的起點照那條線的戰況算（start_from_front），戰況又照佔領算；
開集結那一刻把「那條線上的區塊誰佔幾處、照戰況換算的起點」快照進 BattleInstance.front_note，之後不重算：
- 天下大事一則：先寫起點照戰況偏幾點，另一句寫那條線上的地盤（FB-686：不能讀成「佔得多就往那邊偏」）；
- 決戰畫面標題底下一行短句：只寫偏幾點與哪一條線（FB-685：375／360／320 都本來就一行、數字不在句尾）；
- 天命之爭的碎片那一句改寫成「再」偏的那一份（FB-687）。
領地爭奪關著、沒寫戰線、舊資料：什麼都不寫（存檔連鍵都沒有）。"""
from __future__ import annotations

import json
import re
import unicodedata

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import battle_instance as bi
from tianxia import conquest, seal, territory
from tianxia import world as world_mod

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

CHANGSHE = "changshe_fire"
WHY = "（戰況從開季的態勢算起，之後的易手與各路推動都算在裡面）"


def _hold(game, given: dict[str, str]) -> None:
    c = game.content

    def _set(season):
        for loc, side in given.items():
            assert conquest.set_control(season, c, loc, side)
        territory.update(season, c)

    game.world.mutate_season(_set)


def _muster(game, battle_id: str = CHANGSHE, given: dict[str, str] | None = None):
    """開集結（時刻表與管理者「立刻開這一場」走的 world._open_claimed），起點照戰況（showdown_start）。"""
    c, world = game.content, game.world
    if given:
        _hold(game, given)
    d = c.battles[battle_id]
    msgs = world_mod._open_claimed(world, c, 0.0, lambda vehicle: (d, world_mod.showdown_start(vehicle, c, d)))  # noqa: SLF001
    return d, msgs, world.get_battle(), world.get_season()


def test_changshe_at_season_open_says_who_holds_the_line():
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game)
    assert battle.trend_start == battle.trend == 55  # 起點照舊（不另加偏移）
    assert battle.front_note == bi.FrontNote(line="yingru", start=55, held={"guan": 8, "huang": 5}, open=2)
    line = f"長社火攻開集結：戰局起點照潁川汝南此刻的戰況往官軍偏了 5 點{WHY}。潁川汝南一帶的地盤此刻官軍佔 8 處、黃巾軍佔 5 處、2 處還沒人佔。"
    assert f"🗺️ 【天下大事】{line}" in msgs
    assert any(r.text == line and r.layer == "world" for r in season.rumors)
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "\n\n起點偏官軍 5 點：潁川汝南戰況\n\n" in scene
    assert "處" not in conquest.front_scene(game.content, d, battle.front_note)  # 佔幾處只寫在天下大事那一則（FB-685）


def test_yellow_turbans_took_the_two_neutral_blocks():
    """開著的季，佔領一：黃巾拿下潁川汝南兩塊中立地，起點往黃巾偏，沒人佔的那一段不寫。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "huang", "hilltop_wilds": "huang"})
    assert battle.trend_start == 38
    assert battle.front_note == bi.FrontNote(line="yingru", start=38, held={"guan": 8, "huang": 7}, open=0)
    line = f"長社火攻開集結：戰局起點照潁川汝南此刻的戰況往黃巾軍偏了 12 點{WHY}。潁川汝南一帶的地盤此刻官軍佔 8 處、黃巾軍佔 7 處。"
    assert any(r.text == line for r in season.rumors)
    assert "\n\n起點偏黃巾軍 12 點：潁川汝南戰況\n\n" in game._battle_scene_text(battle, d)  # noqa: SLF001


def test_han_army_took_runan_wilds_on_the_weekend():
    """開著的季，佔領二（週末）：官軍拿下汝南荒野。"""
    game = conquest_game("week7")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "guan"})
    assert battle.front_note == bi.FrontNote(line="yingru", start=64, held={"guan": 9, "huang": 5}, open=1)
    assert (f"🗺️ 【天下大事】長社火攻開集結：戰局起點照潁川汝南此刻的戰況往官軍偏了 14 點{WHY}。"
            "潁川汝南一帶的地盤此刻官軍佔 9 處、黃巾軍佔 5 處、1 處還沒人佔。") in msgs
    assert "\n\n起點偏官軍 14 點：潁川汝南戰況\n\n" in game._battle_scene_text(battle, d)  # noqa: SLF001


def test_the_screen_keeps_the_muster_snapshot():
    """數字是開集結那一刻的：之後易手了（戰況變了），決戰畫面照舊寫開集結那一刻的，資料庫讀回來也是同一份。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    _hold(game, {"runan_wilds": "huang", "hilltop_wilds": "huang", "yingchuan_wilds": "huang"})
    now = bi.start_from_front(game.world.get_season().trends["yingru"])
    assert now != 55  # 戰況真的變了：重算的話畫面會不一樣
    again = game.world.get_battle()
    assert again.front_note == battle.front_note
    assert "起點偏官軍 5 點：潁川汝南戰況" in game._battle_scene_text(again, d)  # noqa: SLF001
    assert '"front_note":{"line":"yingru","start":55' in again.model_dump_json(exclude={"record_id", "rounds"})


def test_every_timetable_showdown_with_a_front_gets_it():
    """宛城（南陽）、廣宗（冀州）一樣照自己那條線寫；沒寫戰線的（beta 的黃巾決戰）不寫。"""
    for battle_id, line, name in (("wancheng_jia", "nanyang", "南陽"), ("guangzong", "jizhou", "冀州")):
        game = conquest_game("season21")
        d, msgs, battle, season = _muster(game, battle_id)
        note = battle.front_note
        assert note is not None and note.line == line and note.start == battle.trend_start
        held, unheld = conquest.line_holdings(season, game.content, line)
        assert sum(note.held.values()) + note.open == sum(held.values()) + unheld
        assert any(m.startswith("🗺️ 【天下大事】") and f"{name}一帶的地盤此刻" in m for m in msgs)
        assert f"：{name}戰況" in game._battle_scene_text(battle, d)  # noqa: SLF001
        if battle_id == "guangzong":  # 大本營與廣宗也算（同輿圖）：開季的冀州不寫成「黃巾軍佔 0 處」
            assert note.held == {"guan": 5, "huang": 2} and note.open == 3
            assert any("冀州一帶的地盤此刻官軍佔 5 處、黃巾軍佔 2 處、3 處還沒人佔" in m for m in msgs)
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "huangjin_showdown")
    assert d.front is None and battle.front_note is None
    assert not any("🗺️" in m for m in msgs)
    assert "戰況" not in game._battle_scene_text(battle, d).split("\n\n")[1]  # 標題底下沒有那一行  # noqa: SLF001


def _width(text: str) -> float:
    """排出來大約幾個字寬：全形（中文、全形標點）一個，半形（數字、空格）半個。"""
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.5 for ch in text)


def test_fb685_the_battle_screen_line_is_one_short_line():
    """FB-685（PM 2026-10-22）：決戰畫面那一句只留一行短句——320 寬那一段約 16.6 個字寬（15.5px 的字、258px），最長的局面
    （黃巾軍、兩位數、潁川汝南）也要在 16 個字寬以內；數字不在句尾（收成一行時句尾的數字會被「…」吃掉，fitDigitsShown 就不收）；
    不寫佔幾處。三條線、起點 25～75 每一種都量。"""
    c = conquest_game("season21").content
    for battle_id in ("changshe_fire", "wancheng_jia", "wancheng_yi", "guangzong", "tianming"):
        d = c.battles[battle_id]
        for start in range(25, 76):
            line = conquest.front_scene(c, d, bi.FrontNote(line=d.front, start=start, held={"guan": 9, "huang": 9}, open=9))
            assert _width(line) <= 16, (battle_id, start, line, _width(line))
            assert not re.search(r"[0-9０-９][^0-9０-９]{0,2}$", line), line
            assert "處" not in line and "\n" not in line
    d = c.battles[CHANGSHE]
    assert conquest.front_scene(c, d, bi.FrontNote(line="yingru", start=50)) == "起點不偏：潁川汝南戰況"
    assert conquest.front_scene(c, d, None) == ""


def test_fb686_the_lean_and_the_holdings_are_two_sentences():
    """FB-686（PM 2026-10-22）：冀州開季官軍佔 5 處、黃巾軍佔 2 處，起點卻往黃巾軍偏 2 點（開季的態勢本來就偏黃巾）。天下大事把
    「起點照戰況偏幾點」與「地盤此刻誰佔幾處」寫成兩句：前一句不提處數、後一句不提偏，中間不用因果連起來。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "guangzong")
    assert battle.trend_start == 48
    line = next(r.text for r in season.rumors if r.text.startswith("廣宗決戰開集結："))
    assert line == (f"廣宗決戰開集結：戰局起點照冀州此刻的戰況往黃巾軍偏了 2 點{WHY}。"
                    "冀州一帶的地盤此刻官軍佔 5 處、黃巾軍佔 2 處、3 處還沒人佔。")
    first, second, rest = line.split("。")
    assert "處" not in first and "偏" in first and rest == ""
    assert "偏" not in second and "處" in second
    assert not re.search(r"所以|因此|因為|於是|故", line)


def test_fb687_the_mandate_line_says_the_shards_add_nothing_more():
    """FB-687（PM 2026-10-22）：天命之爭在領地爭奪開著的季，前一句寫起點照冀州戰況偏 2 點，碎片那一句不再寫「戰局起點不偏」
    （講的是碎片另加的那一份），改成「起點不再另偏」／「起點再往某軍偏 N 點」。畫面與天下大事都是。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "tianming")
    assert seal.on(game.content) and seal.is_mandate_battle(game.content, d)
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "\n\n起點偏黃巾軍 2 點：冀州戰況\n\n天命之爭：玉璽碎片不在交戰的任何一方手上，起點不再另偏。" in scene
    assert "戰局起點不偏" not in scene
    rumors = [r.text for r in season.rumors]
    assert "天命之爭集結：玉璽碎片不在交戰的任何一方手上，起點不再另偏。" in rumors
    assert not any("戰局起點不偏" in t for t in rumors)
    two = {"guan": 2, "huang": 1}
    assert seal.shift_text(3, two, d, extra=True) == "起點再往官軍偏 3 點"
    assert seal.shift_text(-6, {"huang": 2}, d, extra=True) == "起點再往黃巾軍偏 6 點"
    assert seal.shift_text(0, {"guan": 1, "huang": 1}, d, extra=True) == "兩軍持璽相當，起點不再另偏"
    assert seal.shift_text(0, {}, d, extra=True) == "起點不再另偏"


@pytest.mark.parametrize("profile", ["week7", "season21"])
def test_fb687_conquest_off_the_mandate_line_is_unchanged(profile):
    """領地爭奪關著（沒有起點照戰況那一句）：天命之爭碎片那一句照舊「戰局起點不偏」，畫面上也沒有新的那一行。"""
    game = plain_game(profile)
    d, msgs, battle, season = _muster(game, "tianming")
    assert battle.front_note is None
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "天命之爭：玉璽碎片不在交戰的任何一方手上，戰局起點不偏。" in scene and "戰況" not in scene.split("\n\n")[1]
    assert "天命之爭集結：玉璽碎片不在交戰的任何一方手上，戰局起點不偏。" in [r.text for r in season.rumors]


@pytest.mark.parametrize("profile", ["week7", None, "season21"])
def test_conquest_off_not_a_byte_changes(profile, monkeypatch):
    """領地爭奪關著（正式內容的預設）：開集結的訊息、決戰那一列的 JSON、季（含天下大事）、決戰畫面，跟拿掉這個掛點時一模一樣，
    決戰那一列連 front_note 這個鍵都沒有。"""
    def run(hooked: bool):
        game = plain_game(profile)
        if not hooked:
            monkeypatch.setattr(world_mod, "_front_muster", lambda *a, **k: [])
        d, msgs, battle, season = _muster(game)
        out = (msgs, battle.model_dump_json(exclude={"record_id", "rounds"}), season.model_dump_json(),
               game._battle_scene_text(battle, d))  # noqa: SLF001
        monkeypatch.undo()
        return out

    with_hook, without = run(True), run(False)
    assert with_hook == without
    assert '"front_note"' not in with_hook[1]
    assert "戰況" not in with_hook[3].split("\n\n")[1]


def test_old_rows_without_the_snapshot_still_render():
    """舊資料（這一版以前開的決戰，那一列沒有 front_note）：讀得進來、是 None，畫面不多寫、不炸。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    data = json.loads(battle.model_dump_json())
    assert data.pop("front_note")["line"] == "yingru"
    old = bi.BattleInstance.model_validate_json(json.dumps(data, ensure_ascii=False))
    assert old.front_note is None and old.battle_id == battle.battle_id
    assert "戰況" not in game._battle_scene_text(old, d).split("\n\n")[1]  # noqa: SLF001
    game.world.mutate_battle(lambda b: setattr(b, "front_note", None))
    stored = game.world.get_battle()
    assert stored.front_note is None
    assert "起點偏" not in game._battle_scene_text(stored, d)  # noqa: SLF001
    assert conquest.front_scene(game.content, d, None) == ""
