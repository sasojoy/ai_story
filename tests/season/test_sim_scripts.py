"""量測腳本（scripts/fun_run.py 好玩度、scripts/sim_server_bots.py 伺服器假人整季）裡的模擬玩家也要配點：
升級給的屬性點（武學與成長設計 6.2）不分掉的話，整季五項都停在 5，量出來的平衡描述的是「不會配點的玩家」
（CLAUDE.md「第三層」的教訓：量平衡之前先確認機器人會用到那個機制）。伺服器假人本來就在 bot_policy.look_after 裡配點。

兩支腳本都只跑幾步，用測試內容，不驗平衡、只驗「點數有分掉」。"""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from conftest import FixedRandom
from tianxia import team
from tianxia.engine import Game

pytestmark = pytest.mark.slow  # 跑整個腳本：合併前的整套才跑（pytest -m "slow or not slow"）

ROOT = Path(__file__).parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # fun_run 有 dataclass：建類別時要在 sys.modules 查得到自己的模組
    # fun_run 匯入時把 sys.stdout 換成 UTF-8 的包裝：先換成一個用完就丟的，匯入完原樣換回來（不碰 pytest 的擷取）
    with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")):
        spec.loader.exec_module(module)
    return module


def _spent(game: Game) -> bool:
    p = game.state.player
    return p.stat_points == 0 and max(p.stats[k] for k in team.COMBAT_STATS) > team.BASE_STAT


def test_the_fun_run_player_spends_its_stat_points(content, tmp_path, monkeypatch):
    fun_run = _load("fun_run")
    real_new, games = Game.new, []

    def new(*args, **kwargs):  # 開局就給 3 點：等於已經升了幾級
        game = real_new(*args, **kwargs)
        game.state.player.stat_points = 3
        games.append(game)
        return game

    monkeypatch.setattr(Game, "new", new)
    monkeypatch.setattr(fun_run, "MAX_STEPS", fun_run.SPEND_XINDE_EVERY + 1)  # 第 0 步與第 5 步各輪到一次花用
    fun_run.play(content, 1, tmp_path)
    assert len(games) == 1 and _spent(games[0])


def test_the_server_bot_simulation_humans_spend_their_stat_points(game):
    sim = _load("sim_server_bots")
    game.state.player.stat_points = 3
    sim.human_turn(game, FixedRandom(0.1))  # random() < 0.2：這一輪輪到花用（練成、配點）
    assert _spent(game)


def test_the_server_bot_simulation_reports_forging(monkeypatch):
    sim = _load("sim_server_bots")
    tally = sim.ForgeTally()
    tally.forged["武學＋意境"] += 1
    tally.new += 1
    report = tally.report(libraries=[3, 30])
    assert report["開爐"] == {"武學＋意境": 1} and report["首創"] == 1
    assert report["庫存最多"] == 30 and report["最多可配對"] == 435


def test_the_forge_tally_reports_the_share_that_landed_on_old_recipes_and_the_blend_share():
    sim = _load("sim_server_bots")
    tally = sim.ForgeTally()
    assert tally.report(libraries=[])["合到舊的比例"] == 0.0 and tally.report(libraries=[])["庫存最多"] == 0
    tally.new, tally.landed = 3, 1
    tally.forged.update({"武學＋武學": 3, "武學＋意境": 1})
    report = tally.report(libraries=[2])
    assert report["合到舊的比例"] == 0.25 and report["武學＋武學佔"] == 0.75


def test_the_server_bot_simulation_counts_its_forging_in_a_short_season(tmp_path, monkeypatch):
    """整條接線：假人程式用假的取名（不叫模型），一小段時間內 forge 那一欄有東西、各項數字對得上。
    不驗平衡，只驗量測有接上（開爐的種類、首創、模型呼叫數、輪不到取名都記得到）。"""
    from tianxia import database
    from tianxia.content import load_content

    sim = _load("sim_server_bots")
    monkeypatch.setattr(sim, "MAX_REAL_DAYS", 1)
    content = load_content(ROOT / "content")
    content.config.time_scale, content.config.bot_tick_seconds = 6.0, 60.0
    try:
        result = sim.run_season(content, tmp_path, seed=1, tick=60.0)
    finally:
        database.close_all()
    forge = result["forge"]
    assert set(forge["開爐"]) <= set(sim.FORGE_KINDS.values())
    assert sum(forge["開爐"].values()) > 0 and forge["首創"] > 0
    assert forge["取名呼叫"] + forge["挑選呼叫"] + forge["定名呼叫"] > 0
    assert forge["庫存最多"] >= 2 and forge["最多可配對"] == forge["庫存最多"] * (forge["庫存最多"] - 1) // 2
    posted = result["bounties"]["掛出"]  # 預設設定（第一季規則關著）也每週初掛一批，求兵三方各一張（懸賞榜設計 11.2；求藝 2026-10-21 拿掉）
    assert "art" not in posted and posted.get("arms", 0) >= 3 and result["bounties"]["每週最多幾批"] == 1


def test_a_week7_server_bot_season_splits_the_gentry_between_the_armies(tmp_path, monkeypatch):
    """第一季豪強分屬兩軍（7 天季預設開）：假人整季跑一段，投靠豪強的假人都挑了依附哪一軍、名冊沒有不帶依附的豪強，
    大勢沒有割據那條線，名冊照那一方數只剩官軍、黃巾。只跑 0.4 個現實日（×6 約 2.4 個世界日，跟以前跑完 2.5 天的週末季一樣長；
    依附在投靠那一刻就挑好）。"""
    from tianxia import database
    from tianxia.characters import open_characters
    from tianxia.content import load_content

    sim = _load("sim_server_bots")
    monkeypatch.setattr(sim, "MAX_REAL_DAYS", 0.4)
    content = load_content(ROOT / "content", profile="week7")
    content.config.time_scale, content.config.bot_tick_seconds = 6.0, 60.0
    try:
        result = sim.run_season(content, tmp_path, seed=1, tick=60.0)
        gentry = [s.player for s in open_characters(tmp_path / "tianxia.db").all() if s.player.faction == "haoqiang"]
    finally:
        database.close_all()
    assert gentry and all(p.ally in ("guan", "huang") for p in gentry)
    assert "geju" not in result["trends"]
    assert set(result["sides"]) <= {"guan", "huang"} and result["factions"].get("haoqiang") == len(gentry)


def test_the_server_bot_simulation_can_ask_a_real_model(monkeypatch):
    """--real-model 傳給 run_season（預設是假的取名：只數次數、不連模型）。"""
    sim = _load("sim_server_bots")
    seen = []
    monkeypatch.setattr(
        sim, "run_season", lambda content, workdir, seed, tick, real_model=False, pause=None: seen.append(real_model) or {},
    )
    for flags in ([], ["--real-model"]):
        monkeypatch.setattr(sys, "argv", ["sim_server_bots.py", "--seasons", "1", *flags])
        sim.main()
    assert seen == [False, True]


def test_the_companion_measure_script_removes_its_temp_folder(tmp_path):
    """最終審查 M4：量測腳本在暫存目錄開一堆資料庫檔，結束時要清掉，不能每跑一次留一個 measure_companions_* 資料夾。
    只匯入、開一個資料庫就結束（不跑整個量測，太慢），然後看暫存目錄還在不在。"""
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'scripts')!r}); import measure_companions as m; "
        "m.open_world(m.TMP / 'x.db')"
    )
    env = {**os.environ, "TEMP": str(tmp_path), "TMP": str(tmp_path), "TMPDIR": str(tmp_path)}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=ROOT)
    assert list(tmp_path.glob("measure_companions_*")) == []


def test_the_server_bot_simulation_can_pause_the_season_clock(content, tmp_path, monkeypatch):
    """--pause-at：模擬中途讓賽季時鐘停一段——停著的時候「真人」照樣刷新（同步）、假人程式照樣巡，季的時間一秒都不動、
    假人一個動作都沒做；繼續之後照常跑到收季。測試內容的季壓到幾分鐘（time_scale 400），「真人」整天在線。"""
    sim = _load("sim_server_bots")
    monkeypatch.setattr(sim, "HUMAN_HOURS", range(24))
    content.config.time_scale = 400.0
    resumed, real = [], sim.resume_season_clock  # 「繼續」走 world.resume_season_clock（三步的順序只寫在那一個地方）
    # 跟正式的一樣在行動鎖裡做（伺服器的 act、主機端腳本都是）：記下呼叫的當下有沒有拿著寫入權
    monkeypatch.setattr(
        sim, "resume_season_clock", lambda world, *a, **k: resumed.append(world.db.writing()) or real(world, *a, **k),
    )
    result = sim.run_season(content, tmp_path, seed=0, tick=60.0, pause=(0.05, 0.1))
    assert resumed == [True]
    assert result["pause"]["at_day"] is not None
    assert result["pause"]["season_moved"] == 0.0 and result["pause"]["bot_moves"] == 0
    assert result["ended"] and isinstance(result["late_joiners"], int)


def test_the_exp_pace_measure_prints_one_line_per_side_and_rule(capsys, monkeypatch, tmp_path):
    """經驗節奏量表（正式季整合 8.2）：短短跑一段，每一方、每一種規則各印一行等級與經驗來源（只量不改，不驗數字）。"""
    monkeypatch.setenv("TIANXIA_DB", str(tmp_path / "pace.db"))
    measure = _load("measure_exp_pace")
    measure.main(["--profile", "week7", "--rules", "old", "new", "--sides", "官軍", "散人", "--days", "0.2", "--step", "120"])
    out = capsys.readouterr().out
    assert out.count("[舊規則") == 2 and out.count("[新規則") == 2 and out.count("經驗來源") == 4
    assert "練功" in out  # 新規則照練功拿經驗


def test_the_weapons_measure_script_prints_one_line_with_and_one_without_weapons(capsys, monkeypatch):
    """兵器量表：--seeds 1 跑一次，兵器開、兵器關各印一行（只量不改，不驗數字）。"""
    measure = _load("measure_weapons")
    monkeypatch.setattr(sys, "argv", ["measure_weapons.py", "--seeds", "1", "--profile", "week7"])
    measure.main()
    out = capsys.readouterr().out
    assert "種子 1 兵器開：" in out and "種子 1 兵器關：" in out
    assert out.count("遊歷勝率") == 2
    assert out.count("小時（世界時間）") == 2 and out.count("結局 ") == 2 and out.count("每遊戲日") == 2  # 季長、結局、每日場數
    assert out.count("、打造 ") == 2 and out.count("淬煉 ") == 2 and out.count("摸出隱藏配方 ") == 2 and out.count("、名器 ") == 2  # 打造第一批：一般組合不登記，數摸出的隱藏配方與名器
    assert out.count("鐵匠鋪花掉 ") == 2 and out.count("全季收入 ") == 2  # 設計第七節第 5 項：銀兩花在鐵匠鋪的比例


def test_the_gear_measure_script_prints_one_line_with_and_one_without_armor(capsys, monkeypatch):
    """裝備量表（防具那一項，裝備四欄設計第十節）：--seeds 1 跑一次週末設定、照手上的事走，防具開、關各印一行（只量不改，不驗數字）。"""
    measure = _load("measure_gear")
    monkeypatch.setattr(sys, "argv", ["measure_gear.py", "--seeds", "1", "--profile", "week7", "--steer"])
    measure.main()
    out = capsys.readouterr().out
    assert "種子 1 防具開：" in out and "種子 1 防具關：" in out and out.count("對照（") == 1
    assert out.count("掉氣血 ") == 2 and out.count("內傷 ") == 2 and out.count("療傷 ") == 2
    assert out.count("穿著防具 ") == 2  # 防具開那一行的硬仗與勝率只算穿著防具的仗，要看得出算了幾場
    assert out.count("一條氣血撐 ") == 2 and out.count("硬仗之後再打的勝率 ") == 2 and out.count("修防具 ") == 2
    assert out.count("一階素材 ") == 2 and out.count("結局 ") == 2
    assert out.count("打造防具 ") == 2 and out.count("淬防具 ") == 2 and out.count("防具名器 ") == 2  # 打造第一批：防具打造


def test_the_mounts_measure_script_prints_one_line_with_and_one_without_mounts(capsys, monkeypatch):
    """坐騎量表（裝備四欄設計第十節第 2 項）：--seeds 1 跑一次週末設定、照手上的事走、走法混著用，坐騎開、關各印一行（只量不改，不驗數字）。"""
    measure = _load("measure_mounts")
    monkeypatch.setattr(sys, "argv", ["measure_mounts.py", "--seeds", "1", "--profile", "week7", "--steer", "--gait", "mix"])
    measure.main()
    out = capsys.readouterr().out
    assert "種子 1 坐騎開：" in out and "種子 1 坐騎關：" in out
    assert out.count("走了 ") == 2 and out.count("走路花 ") == 2 and out.count("疾行體力 ") == 2
    assert out.count("買馬 ") == 2 and out.count("、餵 ") == 2 and out.count("策馬脫身 ") == 2
    assert out.count("決戰騎著馬 ") == 2 and out.count("一階素材 ") == 2 and out.count("結局 ") == 2


def test_the_treasures_measure_script_prints_one_line_with_and_one_without_treasures(capsys, monkeypatch):
    """寶物量表（裝備四欄設計第十節第 3 項）：--seeds 1 跑一次週末設定、照手上的事走，寶物開、關各印一行（只量不改，不驗數字）。"""
    measure = _load("measure_treasures")
    monkeypatch.setattr(sys, "argv", ["measure_treasures.py", "--seeds", "1", "--profile", "week7", "--steer"])
    measure.main()
    out = capsys.readouterr().out
    assert "種子 1 寶物開：" in out and "種子 1 寶物關：" in out
    assert out.count("件（懸賞 ") == 2 and out.count("良駒 ") == 2 and out.count("名駒 ") == 2 and out.count("換成銀兩 ") == 2
    assert out.count("寄放 ") == 2 and out.count("補發 ") == 2 and out.count("換寶物 ") == 2
    assert out.count("升品 ") == 2 and out.count("多掉素材 ") == 2 and out.count("破境丹 ") == 2
    assert out.count("勝場心得 ") == 2 and out.count("勝場經驗 ") == 2 and out.count("結局 ") == 2


def test_the_sanren_measure_script_can_measure_a_season_with_the_season_one_rules_off(capsys, monkeypatch):
    """散人量表（懸賞榜設計 11.1）：--profile none 不套設定覆寫檔，量的是預設設定（14 天、第一季規則關著）的季；
    開頭印一行設定，散人、陣營各一行，再各一行中位數（只量不改，不驗數字）。"""
    measure = _load("measure_sanren")
    monkeypatch.setattr(sys, "argv", ["measure_sanren.py", "--seeds", "1", "--profile", "none"])
    measure.main()
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "設定：預設"
    assert "種子 1 散人：" in out and "種子 1 陣營：" in out
    assert "散人中位數：" in out and "陣營中位數：" in out
    assert out.count("　交差：討伐 ") == 2 and out.count("　求兵：交 ") == 2 and "求藝" not in out  # 懸賞榜設計 11.1 第 3 點


def test_the_sanren_measure_script_can_send_the_faction_side_to_the_local_gentry(capsys, monkeypatch):
    """--faction（懸賞榜設計 11.1 第 3 點）：陣營那一邊一路走到地方豪強的投靠點投它（以前投選單上第一個出現的，量不到豪強）；
    劇本沒有的陣營直接報錯。--no-give 只清 give_kinds（豪強的基準：有懸賞榜第一批、沒有求兵），--bare 連 kinds、名號的經驗加成一起清。"""
    measure = _load("measure_sanren")
    content = measure.load_content(ROOT / "content")
    measure._strip(content, bare=False, no_give=True)
    assert content.config.bounties.give_kinds == [] and content.config.bounties.kinds and content.config.ranger.exp_per_tier > 0
    measure._strip(content, bare=True, no_give=False)
    assert content.config.bounties.kinds == [] and content.config.ranger.exp_per_tier == 0.0
    monkeypatch.setattr(sys, "argv", ["measure_sanren.py", "--seeds", "1", "--profile", "none", "--faction", "haoqiang"])
    measure.main()
    side = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("種子 1 陣營："))
    assert "haoqiang 第" in side
    monkeypatch.setattr(sys, "argv", ["measure_sanren.py", "--seeds", "1", "--faction", "nobody"])
    with pytest.raises(SystemExit):
        measure.main()


def test_the_server_bot_simulation_tallies_bounties_and_raids():
    """懸賞榜設計 11.2：每一種掛出幾張（第一次看到才算）、每一週最多冒出幾批（通緝不算），被截殺最多的那個人被截幾次、
    被截時丟了多少（只算他當守方輸掉的；他自己去截別人輸了不算，反殺、平手不丟）。"""
    from tianxia.engine import RaidSpoils
    from tianxia.state import Bounty

    sim = _load("sim_server_bots")
    tally = sim.BountyTally()

    def b(bounty_id, kind, week):
        return Bounty(id=bounty_id, kind=kind, faction="guan", week=week, expires=1.0, silver=0, deeds=0)

    tally.see(1, [b("b1", "scout", 1), b("b2", "arms", 1)])
    tally.see(2, [b("b1", "scout", 1), b("b2", "arms", 1), b("b3", "strike", 2), b("b4", "wanted", 1)])
    for winner, lost, hp in (("乙", 5, 20), ("丙", 7, 20)):
        tally.defended("甲", RaidSpoils(winner=winner, lost=lost, taken=0, hp=hp, contrib=0))
    tally.defended("甲", RaidSpoils(winner="甲", lost=9, taken=5, hp=30, contrib=0))  # 反殺：被截一次、輸的是對方
    tally.defended("甲", None)  # 平手
    tally.defended("乙", RaidSpoils(winner="丁", lost=9, taken=5, hp=30, contrib=0))
    report = tally.report()
    assert report["掛出"] == {"scout": 1, "arms": 1, "strike": 1, "wanted": 1} and report["每週最多幾批"] == 1
    assert report["被截最多"] == {"次數": 4, "銀兩": 12, "氣血": 40}
    tally.see(3, [b("b5", "arms", 2)])  # 第 2 週的單分兩輪冒出來：兩批
    assert tally.report()["每週最多幾批"] == 2


def test_the_server_bot_simulation_reports_smithing():
    """打造第二批：假人整季打了幾爐、幾個假人打過、手上的名器、原品、仿品各幾件（smith_report）。"""
    from types import SimpleNamespace as NS
    from tianxia.state import Weapon
    sim = _load("sim_server_bots")
    smith = NS(player=NS(
        forge_counts={"兵|劍|gang_1+gang_1": 2, "鎧|gang_1+gang_1": 1},
        weapon=Weapon(id="兵:1", name="甲", kind="劍", secret="t", original=True), armor=None,
        rack=[Weapon(id="兵:2", name="乙", kind="劍", secret="t", copy_of="鑄|t"), Weapon(id="兵:3", name="丙", kind="劍", secret="u")],
    ))
    idle = NS(player=NS(forge_counts={}, weapon=None, armor=None, rack=[]))
    assert sim.smith_report([smith, idle]) == {"打造": 3, "打過的假人": 1, "名器": 1, "原品": 1, "仿品": 1, "本命": 0}


def test_the_server_bot_simulation_reports_signature_arms():
    """打造第三批：這一季哪幾位名將的本命兵器被拿走了、怎麼拿的，假人裡打贏孫堅本人最多幾次（signature_report）。
    本命兵器是神器原品的一種，但「原品」只數打出來的，本命兵器另外數（smith_report 的「本命」）。"""
    from types import SimpleNamespace as NS
    from tianxia.state import SignatureClaim, Weapon
    sim = _load("sim_server_bots")
    season = NS(signature_arms={"sunjian": SignatureClaim(owner="甲", via="seized")})
    bots = [NS(player=NS(figure_wins={"sunjian": 3})), NS(player=NS(figure_wins={}))]
    assert sim.signature_report(season, bots) == {"拿走": {"sunjian": "seized"}, "打贏孫堅最多": 3}
    assert sim.signature_report(NS(signature_arms={}), []) == {"拿走": {}, "打贏孫堅最多": 0}
    holder = NS(player=NS(
        forge_counts={}, weapon=Weapon(id="兵:1", name="江潮槍", kind="槍", original=True, signature="sunjian"), armor=None, rack=[],
    ))
    assert sim.smith_report([holder]) == {"打造": 0, "打過的假人": 0, "名器": 0, "原品": 0, "仿品": 0, "本命": 1}


def test_the_secrets_measure_script_also_prints_the_forge_part(capsys, monkeypatch):
    """口訣與秘方量表多一段鑄器（打造隱藏配方設計第十二節第 1、2、4 項）：--seeds 1 跑一次週末設定，三種機器人各一行鑄器、
    三邊合起來一行、三行平均（只量不改，不驗數字）。"""
    measure = _load("measure_secrets")
    monkeypatch.setattr(sys, "argv", ["measure_secrets.py", "--seeds", "1"])
    measure.main()
    out = capsys.readouterr().out
    lines = out.splitlines()
    # 平均那三行（「隨機平均 鑄器：摸到 …」）也含「鑄器：摸到 」，所以每個種子的那三行照開頭數
    assert sum(line.startswith("種子 1 ") and "鑄器：摸到 " in line for line in lines) == 3
    assert out.count("種子 1 三邊合起來：鑄器摸到 ") == 1
    # FB-270：照季的章數配方，也數片子。神器輪替（正式季第 10 批）：伺服器的第一季九件神器全開（兵器六、防具三），
    # 加上名器兵器一階 2、二階 2、三階 2，防具一階 1、二階 1、三階 1（三階那一組是第 4 批補的），共 18 條
    forge_rows = [line for line in lines if line.startswith("種子 1 ") and "鑄器：摸到 " in line]
    assert all("/18（" in line and "神器片子 " in line for line in forge_rows), forge_rows
    assert out.count("爐、名器 ") == 6 and out.count("平均 鑄器：摸到 ") == 3  # 三邊各一行、三行平均
    assert out.count("神器 原品 ") >= 1 and out.count("三階 ") >= 1  # 打造第二批：神器一季幾把、三階一季幾個


def test_the_seal_measure_script_runs_its_duel_monte_carlo(capsys):
    """玉璽碎片 15.2：--duel-mc 只跑單挑，掃份量比、在場與代打、放手一搏（不搏、每回合搏、最多兩次），報單挑係數的期望 E[g]。"""
    measure = _load("measure_seal")
    rows = measure.duel_mc(measure.load_content(ROOT / "content"), ratios=[1.0, 3.0], trials=40, rates=[50], modes=["none", "cap2"])
    assert len(rows) == 2 * 4 * 2 and all(0.0 <= row["eg"] <= 1.0 for row in rows)
    assert rows == measure.duel_mc(measure.load_content(ROOT / "content"), ratios=[1.0, 3.0], trials=40, rates=[50], modes=["none", "cap2"])
    measure.print_mc(rows)
    assert "E[g]" in capsys.readouterr().out


def test_the_seal_measure_script_summarises_a_season():
    measure = _load("measure_seal")
    line = measure.summary(1, {
        "emerged": "雲篆", "emerge_rank": 2, "stirs": [{"tier": "大敗", "eligible": 3}], "duels": [
            {"verdict": "險勝", "share": 0.6, "taken": False, "edges": [50, 58, 61]}], "takes": 0, "sunk": 0,
        "holders": {"真人": 1, "假人": 0}, "fresh_ratio": [3.1], "holder_big_wins": [0, 1],
    })
    assert "現世 雲篆（戰功第 2）" in line and "璽動 1" in line and "易手 0" in line


def test_the_seal_measure_script_counts_seasons_to_the_mandate(capsys):
    """玉璽二：--mandate-mc 數七片湊齊要幾季（每季最多現世一片、機率 emerge_rate）；同樣的參數結果一樣。"""
    measure = _load("measure_seal")
    row = measure.mandate_mc(0.35, trials=2000, seed=1)
    assert 17 < row["mean"] < 23 and row["p10"] <= row["p50"] <= row["p90"] and row["cycle"] == round(row["mean"] + 1, 1)
    assert row == measure.mandate_mc(0.35, trials=2000, seed=1)
    measure.print_mandate_mc([row])
    assert "天命之季" in capsys.readouterr().out


def test_the_seal_measure_script_summarises_a_mandate_season():
    measure = _load("measure_seal")
    line = measure.summary(2, {
        "emerged": None, "stirs": [{"tier": "險敗", "eligible": 2}] * 3, "duels": [], "takes": 0, "sunk": 0,
        "holders": {"真人": 0, "假人": 5}, "fresh_ratio": [], "holder_big_wins": [0, 0, 0],
        "mandate": {"result": "官軍大勝", "shift": 6, "lean": "官軍握著3片、黃巾軍握著1片", "recalls": 2, "ending": "漢室重光"},
    })
    assert "天命之爭 官軍大勝（起點偏 +6" in line and "喚回 2" in line and "結局 漢室重光" in line
    lines = measure.mandate_lines([{"mandate": {"result": "官軍大勝", "ending": "漢室重光", "recalls": 2}, "stirs": [{}] * 3,
                                    "duels": [{}], "takes": 0}])
    assert any("官軍大勝 1" in x for x in lines)


def test_the_challenge_measure_script_summarises_a_season():
    """挑戰每季都有設計第十一節的量表：一季的紀錄照陣營分（打贏、心得經驗、三階照來源、寶物）、退場第幾天、聲威最低、挑戰佔打仗收入、
    強弱人物場數、頓悟。"""
    from conftest import real_content
    mc = _load("measure_challenge")
    content = real_content()
    t = mc.ChallengeTally()
    t.fight(1.0, "bocai", "guan", "大勝", 80, 80, True)
    t.fight(2.0, "bocai", "haoqiang", "僵持", 0, 0, False)
    t.tier3[("guan", "guaranteed")] += 1
    t.treasures["guan"] += 1
    t.retired["bocai"] = 9.5
    t.prestige = {0: {"bocai": 60}, 1: {"bocai": 55}}
    t.seizes.append((3.0, "挑戰本人"))
    t.battle_income[("guan", "xinde")] += 160
    t.battle_income[("guan", "exp")] += 160
    r = t.report(content)
    assert (r["挑戰"], r["打贏"], r["僵持"]) == (2, 1, 1)
    guan = r["分陣營"]["官軍"]
    assert (guan["打贏"], guan["心得"], guan["三階・保證"], guan["寶物"]) == (1, 80, 1, 1)
    assert r["退場"] == {"波才": 9.5} and r["聲威最低"] == {"波才": 55}
    assert r["挑戰佔打仗收入"] == {"心得": 0.5, "經驗": 0.5} and r["強弱人物場數"] == {"強": 1, "弱": 1}
    assert r["頓悟"] == [(3.0, "挑戰本人")]


def test_the_challenge_measure_script_prints_each_seed_and_the_switches(capsys, monkeypatch):
    mc = _load("measure_challenge")
    row = {"挑戰": 3, "打贏": 2, "僵持": 1, "退場": {"波才": 9.0}, "頓悟": []}
    monkeypatch.setattr(mc, "run_server", lambda args, seed: row)
    mc.main(["--seeds", "1", "2", "--regen", "0", "--cap", "0", "--outcome", "a", "--no-huangjin-end"])
    out = capsys.readouterr().out
    assert "regen 0" in out and "cap 0" in out and "丙 (a)" in out and "拿掉了黃巾聲勢 80 收季" in out
    assert out.count("種子 ") == 2 and "平均：挑戰 3.0" in out
