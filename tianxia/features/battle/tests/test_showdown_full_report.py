"""決戰的完整戰報（Joy 2026-10-14「大決戰能不能把完整戰報在戰報那邊可以展開，而且這種大事件的決戰不應該跟一般的放在一起被洗掉」）。

收場時 Game._file_showdown 把整場一回合一段的戰況快照進自己的戰報（BattleRecord.log，照先後；每一段最後一條是自己出了什麼，
BattleParticipant.moves），戰報頁最後一段「完整戰況」；網頁（app.js 的 roundBlocks 帶 report）每一回合收成一行、點了展開。
決戰與奪璽單挑（battlelog.BIG_KINDS）不佔一般那 MAX_RECORDS 場，戰報列表另外一組排在最上面。"""
from __future__ import annotations

import re

from test_jianghu_page_web import battle, node, run_prologue_web as run  # noqa: F401（battle 是 fixture）

import server
from tianxia import battlelog, engine
from tianxia.state import BattleRecord


def _finish(fighter):
    """場上只有他：一直強攻到收場，再同步一次補戰報。"""
    for _ in range(20):
        if fighter.world.get_battle() is None or fighter.world.get_battle().phase == "ended":
            break
        move = next((o.id for o in fighter.options(odds=False) if o.enabled and o.id.startswith("battle:act:")), None)
        if move is None:
            break
        fighter.choose(move)
    fighter.sync(fighter.now)
    record = next(r for r in fighter.state.battles if r.kind == "showdown")
    return record


def test_the_showdown_report_keeps_every_round_in_order_with_my_move(battle):
    _, fighter = battle
    record = _finish(fighter)
    assert "集結完畢" in record.log[0]  # 開打那一句照舊一段話、在最前面
    rounds = record.log[1:]
    heads = [int(re.match(r"##### 第 (\d+) 回合", block).group(1)) for block in rounds]
    assert heads == list(range(1, len(heads) + 1)) and len(heads) >= 2  # 整場、照先後
    assert all(block.rstrip().split("\n")[-1].startswith("- **你**　強攻") for block in rounds)  # 每一回合最後一條是自己出了什麼（開局的小戰法發動了，後面接那一句）
    detail = fighter.battle_detail(record.id)
    assert battlelog.FULL_LOG_HEAD in detail and detail.index(battlelog.FULL_LOG_HEAD) < detail.index("##### 第 1 回合")


def test_big_battles_are_not_washed_out_by_ordinary_ones():
    from types import SimpleNamespace

    s = SimpleNamespace(battles=[], battle_seq=0)  # add_record 只碰這兩欄

    def rec(i, kind):
        return BattleRecord(id=i, time=0, location="某地", kind=kind, opponent="敵", ours=[], tier="大勝", our_power=0, difficulty=0)
    battlelog.add_record(s, rec(1, "showdown"))
    battlelog.add_record(s, rec(2, "seal"))
    for i in range(3, 3 + battlelog.MAX_RECORDS + 5):
        battlelog.add_record(s, rec(i, "train"))
    kinds = [r.kind for r in s.battles]
    assert kinds.count("train") == battlelog.MAX_RECORDS and {1, 2} <= {r.id for r in s.battles}
    for i in range(100, 100 + battlelog.BIG_KEEP + 3):
        battlelog.add_record(s, rec(i, "showdown"))
    assert sum(r.kind in battlelog.BIG_KINDS for r in s.battles) == battlelog.BIG_KEEP
    assert sum(r.kind == "train" for r in s.battles) == battlelog.MAX_RECORDS


def test_the_report_list_marks_the_big_battles(battle):
    _, fighter = battle
    record = _finish(fighter)
    view = server.reports_view(fighter, None)
    assert next(x for x in view["list"] if x["id"] == record.id)["big"] is True
    # 戰記（Joy 2026-10-29）：決戰的戰報帶著那一場的流水號，網頁拿它問 /api/tale
    assert server.reports_view(fighter, record.id)["tale_id"] == record.battle_ref is not None


@node
def test_the_report_page_puts_big_battles_first_and_folds_every_round(battle):
    _, fighter = battle
    record = _finish(fighter)
    m = server.main_view(fighter)
    reports = server.reports_view(fighter, record.id)
    reports["list"].append({"label": "大勝　第99場　遊歷", "id": 99, "big": False})
    listing = run(m, 'H.S.tab = "news"; H.S.news = "reports"; H.S.reports = R; H.S.reportOpen = false; H.renderPage(); return T.els.page.innerHTML;'.replace("R", repr_js(reports)))
    assert listing.index("大戰") < listing.index(f'data-id="{record.id}"') < listing.index("最近的仗") < listing.index('data-id="99"')
    out = run(m, 'H.S.tab = "news"; H.S.news = "reports"; H.S.reports = R; H.S.reportOpen = true; H.S.roundsOpen = new Set(["rID:2"]); H.renderPage(); return T.els.page.innerHTML;'
              .replace("R", repr_js(reports)).replace("ID", str(record.id)))
    keys = re.findall(r'<details class="b-round" data-round="([^"]+)"', out)
    assert keys and keys[0] == f"r{record.id}:1" and "b-round latest" not in out  # 照先後、全部收成一行
    assert f'data-round="r{record.id}:2" open>' in out  # 攤開了哪幾回合跟場景分開記
    assert "完整戰況" in out and "<h5>" not in out


def repr_js(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def test_a_washed_out_showdown_report_comes_back_once(battle):
    """以前決戰跟遊歷共用 20 場、被洗掉的（PM 2026-10-14，那一場 14 位真人有 6 位被洗掉）：同步時照 battles 表補回來，只補一次。"""
    _, fighter = battle
    record = _finish(fighter)
    silver = fighter.state.player.stats.get("silver", 0)
    fighter.state.battles = [r for r in fighter.state.battles if r.kind != "showdown"]
    fighter.state.player.showdowns_restored = 0
    fighter.sync(fighter.now)
    back = [r for r in fighter.state.battles if r.kind == "showdown"]
    assert len(back) == 1 and back[0].battle_ref == record.battle_ref and back[0].log
    assert engine.RESTORED_NOTE in back[0].notes and back[0].tier == record.tier
    assert fighter.state.player.stats.get("silver", 0) == silver  # 軍餉不再發
    fighter.state.player.showdowns_restored = 0
    fighter.sync(fighter.now)
    assert len([r for r in fighter.state.battles if r.kind == "showdown"]) == 1


def test_an_old_report_without_a_ref_is_not_doubled(battle):
    _, fighter = battle
    record = _finish(fighter)
    record.battle_ref, record.log = None, []  # 這一版以前收到的：照戰名與收場時刻認
    fighter.state.player.showdowns_restored = 0
    fighter.sync(fighter.now)
    assert len([r for r in fighter.state.battles if r.kind == "showdown"]) == 1
    assert record.battle_ref is not None and "完整戰況" in fighter.battle_detail(record.id)  # 還留著的舊戰報也補上完整戰況


def test_the_report_rereads_the_battle_for_tales_written_later(battle):
    _, fighter = battle
    record = _finish(fighter)
    store = fighter.world
    battle_now = store.ended_battle(record.battle_ref)
    battle_now.narrative_log[-1] += "\n參戰乙這一搏後來補上的劇情。"
    with store.db.transaction() as conn:
        conn.execute("UPDATE battles SET data = ? WHERE id = ?", (battle_now.model_dump_json(exclude={"record_id", "rounds"}), record.battle_ref))
    assert "後來補上的劇情" in fighter.battle_detail(record.id)
