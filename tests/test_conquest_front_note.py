"""時刻表決戰的起點照哪一條戰線（企劃者 2026-10-22 選計畫 2026-10-22-長社火攻主場 第七節第 4 條：不另加主場偏移，照現在的規則補一句說明）。

領地爭奪開著的季，時刻表決戰（寫了戰線的：長社火攻、宛城、廣宗、天命之爭）的起點照那條線的戰況算（start_from_front），戰況又照佔領算；
開集結那一刻把「那條線上搶得下來的區塊誰佔幾處、起點往哪邊偏幾點」快照進 BattleInstance.front_note，天下大事一句、決戰畫面一句，
之後不重算。領地爭奪關著、沒寫戰線、舊資料：什麼都不寫（存檔連鍵都沒有）。"""
from __future__ import annotations

import json

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import battle_instance as bi
from tianxia import conquest, territory
from tianxia import world as world_mod

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

CHANGSHE = "changshe_fire"


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
    line = "長社火攻開集結：潁川汝南一帶官軍佔 8 處、黃巾軍佔 5 處、2 處還沒人佔，戰局起點照這一帶的戰況往官軍偏了 5 點。"
    assert f"🗺️ 【天下大事】{line}" in msgs
    assert any(r.text == line and r.layer == "world" for r in season.rumors)
    scene = game._battle_scene_text(battle, d)  # noqa: SLF001
    assert "戰局起點照潁川汝南的戰況往官軍偏了 5 點（開集結那一刻潁川汝南一帶官軍佔 8 處、黃巾軍佔 5 處、2 處還沒人佔）。" in scene


def test_yellow_turbans_took_the_two_neutral_blocks():
    """開著的季，佔領一：黃巾拿下潁川汝南兩塊中立地，起點往黃巾偏，沒人佔的那一段不寫。"""
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "huang", "hilltop_wilds": "huang"})
    assert battle.trend_start == 38
    assert battle.front_note == bi.FrontNote(line="yingru", start=38, held={"guan": 8, "huang": 7}, open=0)
    line = "長社火攻開集結：潁川汝南一帶官軍佔 8 處、黃巾軍佔 7 處，戰局起點照這一帶的戰況往黃巾軍偏了 12 點。"
    assert any(r.text == line for r in season.rumors)
    assert "戰局起點照潁川汝南的戰況往黃巾軍偏了 12 點（開集結那一刻潁川汝南一帶官軍佔 8 處、黃巾軍佔 7 處）。" in game._battle_scene_text(battle, d)  # noqa: SLF001


def test_han_army_took_runan_wilds_on_the_weekend():
    """開著的季，佔領二（週末）：官軍拿下汝南荒野。"""
    game = conquest_game("weekend")
    d, msgs, battle, season = _muster(game, given={"runan_wilds": "guan"})
    assert battle.front_note == bi.FrontNote(line="yingru", start=64, held={"guan": 9, "huang": 5}, open=1)
    assert "🗺️ 【天下大事】長社火攻開集結：潁川汝南一帶官軍佔 9 處、黃巾軍佔 5 處、1 處還沒人佔，戰局起點照這一帶的戰況往官軍偏了 14 點。" in msgs


def test_the_screen_keeps_the_muster_snapshot():
    """數字是開集結那一刻的：之後易手了，決戰畫面照舊寫開集結那一刻的，資料庫讀回來也是同一份。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    _hold(game, {"runan_wilds": "huang", "hilltop_wilds": "huang", "yingchuan_wilds": "huang"})
    again = game.world.get_battle()
    assert again.front_note == battle.front_note
    assert "官軍佔 8 處、黃巾軍佔 5 處、2 處還沒人佔" in game._battle_scene_text(again, d)  # noqa: SLF001
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
        assert any(m.startswith("🗺️ 【天下大事】") and f"{name}一帶" in m for m in msgs)
        assert f"戰局起點照{name}的戰況" in game._battle_scene_text(battle, d)  # noqa: SLF001
        if battle_id == "guangzong":  # 大本營與廣宗也算（同輿圖）：開季的冀州不寫成「黃巾軍佔 0 處」
            assert note.held == {"guan": 5, "huang": 2} and note.open == 3
            assert any("冀州一帶官軍佔 5 處、黃巾軍佔 2 處、3 處還沒人佔" in m for m in msgs)
    game = conquest_game("season21")
    d, msgs, battle, season = _muster(game, "huangjin_showdown")
    assert d.front is None and battle.front_note is None
    assert not any("🗺️" in m for m in msgs)
    assert "戰局起點照" not in game._battle_scene_text(battle, d)  # noqa: SLF001


@pytest.mark.parametrize("profile", ["weekend", None, "season21"])
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
    assert "戰局起點照" not in with_hook[3]


def test_old_rows_without_the_snapshot_still_render():
    """舊資料（這一版以前開的決戰，那一列沒有 front_note）：讀得進來、是 None，畫面不多寫、不炸。"""
    game = conquest_game("season21")
    d, _, battle, _ = _muster(game)
    data = json.loads(battle.model_dump_json())
    assert data.pop("front_note")["line"] == "yingru"
    old = bi.BattleInstance.model_validate_json(json.dumps(data, ensure_ascii=False))
    assert old.front_note is None and old.battle_id == battle.battle_id
    assert "戰局起點照" not in game._battle_scene_text(old, d)  # noqa: SLF001
    game.world.mutate_battle(lambda b: setattr(b, "front_note", None))
    stored = game.world.get_battle()
    assert stored.front_note is None
    assert "戰局起點照" not in game._battle_scene_text(stored, d)  # noqa: SLF001
    assert conquest.front_scene(game.content, d, None) == ""
