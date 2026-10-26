"""減法季主機側批 2 的小修（PM 2026-10-26；試玩回饋 FB-830～832、hints.json 的「尋敵」）：只改顯示的字，實際入帳不動。
（2d，企劃者 2026-10-26：一趟只抽一件事；原本「其他拍的素材照舊列在帳上」那一條沒有其他拍了，拿掉。）
1. FB-830：自家營寨比劃那一趟，段落最後「得：」那一行心得照實際入帳寫一次（以前寫兩倍），後面不再多一則單獨的「心得 +N」；
2. FB-831：撞到破境丹、回體丹時，「得：」那一行只列「破境丹 +1」「回體丹 +1」，不把整句說明當成一樣東西列進去（說明那一句照舊留在訊息裡）；
3. FB-832：鈕上與四格那一格的小字以地點種類的字為主，只有那一種的招牌類在這一處此刻的比重是 0 才改寫比重最高的那一類（PM 2026-10-26）；
4. hints.json 的 h_drill_done 在探索一顆開著時不再說「尋敵」。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

import re
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, plain_game, ready

from tianxia import explore_one, hints, journal, team
from tianxia.encounter import EncounterResult

pytestmark = pytest.mark.slow

NUMERIC = re.compile(r"^\S+ [+-]\d+(\.\d+)?")  # 例如「銀兩 +5」「經驗 +10（每人）」


def _beat(beat: str):
    """這一趟抽到的那一件事照給的（2d，企劃者 2026-10-26：一趟只抽一件事）。"""
    return mock.patch.object(explore_one, "draw", return_value=beat)


def _fight(tier: str = "大勝"):
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def _reset(game) -> None:
    game.state.player.stamina = 250.0
    game.state.pending_event = None
    game.state.player.sensing = None


def _ledger_parts(msgs: list[str]) -> tuple[list[str], list[str]]:
    """段落後面那一行「得：…　失：…」拆成（得的幾項, 失的幾項）；沒有那一行是（[], []）。"""
    line = msgs[1] if len(msgs) > 1 and msgs[1][:2] in ("得：", "失：") else ""
    gains, losses = [], []
    for part in line.split("　") if line else []:
        (gains if part.startswith("得：") else losses).extend(part[2:].split("、"))
    return gains, losses


# ── 1. FB-830：營寨比劃的帳 ──


@pytest.mark.parametrize("side, loc", [("guan", "guan_camp"), ("huang", "huangjin_camp")])
def test_the_camp_spar_ledger_writes_the_xinde_once(side, loc):
    game = ready(jianfa_game(), side=side, loc=loc, level=20)
    p = game.state.player
    xinde0, exp0 = p.stats.get("xinde", 0), p.member.exp
    with _beat("encounter"):
        msgs = game.choose("act:explore")
    xinde, exp = p.stats.get("xinde", 0) - xinde0, p.member.exp - exp0
    assert xinde > 0 and exp > 0  # 實際入帳不動（兩倍的只是字）
    gains, losses = _ledger_parts(msgs)
    assert [g for g in gains if g.startswith("心得")] == [f"心得 +{xinde}"], gains
    assert f"經驗 +{exp}（每人）" in gains and not losses
    assert not [m for m in msgs if m.startswith("心得 ")], msgs  # 後面不再多一則單獨的「心得 +N」
    assert game.state.journal[0].changes.count(f"心得 +{xinde}") == 1  # 江湖紀錄的標籤本來就只有一顆


def test_the_camp_spar_called_without_a_journal_draft_still_reports_the_xinde():
    """沒有江湖紀錄草稿（直接叫引擎函式，例如別的測試、腳本）時，心得那一行照樣在回傳的訊息裡，不會悄悄不見。"""
    game = ready(jianfa_game(), side="guan", loc="guan_camp", level=20)
    plan = game.outing_plan()
    assert game._draft is None and plan.how == "spar"
    msgs = game._outing_fight(game.content.locations["guan_camp"], plan)[0]
    assert any(m.startswith("心得 +") for m in msgs)


@pytest.mark.parametrize("loc", ["guan_camp", "yingchuan_wilds", "yingchuan", "yingshui"])  # 比劃、野外的仗、城裡的地痞、只有素材
def test_the_ledger_numbers_are_the_numbers_the_journal_chips_show(loc):
    """「得：」「失：」那一行的數值跟江湖紀錄的標籤同一份（實際入帳寫一次）：每一種拍都一樣。"""
    game = ready(jianfa_game(), side="guan", loc=loc, level=20)
    game.content.config.training.goals = False  # 新手目標的獎勵會在這一則多記一顆標籤，跟這一行的帳無關
    with _beat("material" if loc == "yingshui" else "encounter"), _fight("大勝"):
        msgs = game.choose("act:explore")
    gains, losses = _ledger_parts(msgs)
    shown = sorted(x for x in gains + losses if NUMERIC.match(x))
    assert shown == sorted(game.state.journal[0].changes), (shown, game.state.journal[0].changes)


def test_the_other_drills_still_report_the_xinde_line_and_hide_it_from_the_journal_text():
    """操練、出陣的守與攪局共用的 _drill_gains：訊息照舊有「心得 +N」、草稿另記一筆標籤、敘事裡不重複（只有出門一趟的比劃不回那一行）。"""
    game = ready(jianfa_game(explore_one=False), side="guan", loc="guan_camp", level=20)
    foe = game.content.squads["liangzhou_cavalry"]
    game._draft = journal.Draft("操練")
    msgs = game._drill_gains(foe, 0.3)
    xinde = [m for m in msgs if m.startswith("心得 +")]
    assert len(xinde) == 1 and game._draft.changes[0] == xinde[0] and (xinde[0], None) in game._draft.rewrites
    assert not [line for line in game._draft.entry(0.0, msgs).lines if line.startswith("心得 ")]
    game._draft = None


# ── 2. FB-831：破境丹、回體丹 ──


def test_a_legend_pill_find_lists_only_the_count_in_the_ledger():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    game.content.config.explore_legend_chance = 1.0  # 一定撿到
    name, note = game.content.config.legend_item_name, game.content.config.legend_item_note
    with _beat("material"):
        msgs = game.choose("act:explore")
    gains, _ = _ledger_parts(msgs)
    assert f"{name} +1" in gains
    assert not [g for g in gains if note in g or "一枚" in g or g.startswith("【")], gains  # 整句說明不當成一樣東西列
    assert any(" ×" in g for g in gains)  # 素材照舊列
    assert any(m.startswith("獲得 【") and note in m for m in msgs)  # 說明那一句照舊在訊息裡
    assert any(note in line for line in game.state.journal[0].lines)  # 也在江湖紀錄的敘事裡


def test_a_stamina_pill_find_lists_only_the_count_in_the_ledger():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    game.content.config.checkin.pill_drop = 1.0
    game.content.config.training.goals = False
    name = game.content.config.stamina_pill_name
    with _beat("material"):
        msgs = game.choose("act:explore")
    gains, _ = _ledger_parts(msgs)
    assert gains.count(f"{name} +1") == 1
    assert not [g for g in gains if "一顆" in g or g.startswith("【")], gains
    assert any(m.startswith("獲得 【") and "一顆" in m for m in msgs)


def test_both_pills_in_one_outing_each_show_once():
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    cfg = game.content.config
    cfg.explore_legend_chance = 1.0
    cfg.checkin.pill_drop = 1.0
    cfg.training.goals = False
    with _beat("material"):
        msgs = game.choose("act:explore")
    gains, _ = _ledger_parts(msgs)
    assert gains.count(f"{cfg.legend_item_name} +1") == 1 and gains.count(f"{cfg.stamina_pill_name} +1") == 1
    assert not [g for g in gains if not NUMERIC.match(g) and " ×" not in g], gains  # 帳上不是「名 +N」的只有「名 ×N」


def test_is_item_tells_a_material_from_a_description():
    assert explore_one.is_item("精鐵砂 ×2") and explore_one.is_item("驚羽 ×1（拾遺囊）")
    assert not explore_one.is_item("【破境丹】一枚——衝擊絕學時可以服下，那一次的機會多幾分。")
    assert not explore_one.is_item("【回體丹】一顆——不知誰落下的，正好收著。") and not explore_one.is_item("")


# ── 3. FB-832：小字以地點種類的字為主，招牌類此刻是 0 才照比重 ──

WORDS = {explore_one.EVENT: "多事", explore_one.ENCOUNTER: "多敵", explore_one.MATERIAL: "多料", explore_one.INSIGHT: "多悟"}


def _w(event: int, encounter: int, material: int, insight: int) -> dict[str, int]:
    return {explore_one.EVENT: event, explore_one.ENCOUNTER: encounter, explore_one.MATERIAL: material, explore_one.INSIGHT: insight}


def test_the_hint_keeps_the_place_word_while_its_signature_beat_is_alive():
    """PM 2026-10-26：以地點種類的字為主（跟輿圖名字旁的 MOSTLY、玩法說明的 HINTS 一致）；比重怎麼排，只要招牌類還抽得到就不改字。"""
    h = explore_one.hint_of
    assert h(explore_one.TEMPLE, None, _w(50, 0, 15, 30)) == "寺裡多悟" and h(explore_one.TEMPLE, "foe", _w(50, 5, 15, 30)) == "寺裡多悟"  # 事件比感悟重也寫多悟
    assert h(explore_one.HILL, "foe", _w(5, 40, 40, 20)) == "山裡多料" and h(explore_one.HILL, "foe", _w(10, 30, 40, 20)) == "山裡多料"  # 危險的山：遭遇＝素材
    assert h(explore_one.FORD, "foe", _w(20, 40, 30, 10)) == "渡口參半" and h(explore_one.FORD, "foe", _w(30, 30, 30, 10)) == "渡口參半"  # 危險的渡口：遭遇最重
    assert h(explore_one.FORD, None, _w(30, 0, 30, 10)) == "渡口參半"  # 沒有對手：事件、素材還在，三樣裡兩樣抽得到
    assert h(explore_one.TOWN, "town", _w(60, 15, 15, 10)) == "城裡多事"
    assert h(explore_one.WILD, "foe", _w(15, 55, 20, 10)) == "野外多敵" and h(explore_one.WILD, "foe", _w(5, 20, 55, 10)) == "野外多敵"  # 遭遇不是最重也照字
    assert h(explore_one.CAMP, None, _w(15, 60, 15, 10)) == "營裡多敵"
    assert h(explore_one.WILD, None, None) == "野外多敵"  # 沒有比重可看：照地點種類


def test_the_hint_is_rewritten_only_when_the_signature_beat_is_zero():
    h = explore_one.hint_of
    assert h(explore_one.WILD, None, _w(15, 0, 20, 10)) == "野外多料"  # 遭遇是 0 的野外（長社官軍、洛陽官道黃巾）
    assert h(explore_one.WILD, None, _w(15, 0, 15, 10)) == "野外參半"  # 並列最高
    assert h(explore_one.WILD, None, _w(0, 0, 0, 0)) == "野外多料"  # 全是 0：補的是素材
    assert h(explore_one.TOWN, "town", _w(0, 15, 15, 10)) == "城裡參半"  # 城裡抽不到事件
    assert h(explore_one.TEMPLE, None, _w(50, 0, 15, 0)) == "寺裡多事"  # 悟不出感悟
    assert h(explore_one.FORD, None, _w(0, 0, 30, 10)) == "渡口多料"  # 渡口三樣只剩一樣抽得到，不再寫參半
    assert h(explore_one.CAMP, None, _w(15, 0, 15, 10)) == "營裡參半"


def test_each_kind_signature_beat_is_the_one_its_word_names():
    assert set(explore_one.SIGNATURE) == set(explore_one.MOSTLY)
    for kind, beats in explore_one.SIGNATURE.items():
        if kind == explore_one.FORD:
            assert explore_one.MOSTLY[kind] == explore_one.BALANCED and len(beats) == 3
        else:
            assert len(beats) == 1 and WORDS[beats[0]] == explore_one.MOSTLY[kind], kind


def test_a_bounty_and_the_camp_keep_their_own_words():
    w = _w(15, 0, 20, 10)
    assert explore_one.hint_of(explore_one.WILD, "bounty", w) == "野外有賞" and explore_one.hint_of(explore_one.CAMP, "spar", w) == "同袍比劃"


@pytest.mark.parametrize("side, loc", [("guan", "changshe"), ("huang", "luoyang_road")])
def test_a_place_with_only_a_boss_no_longer_says_many_enemies(side, loc):
    """官軍在長社、黃巾在洛陽官道：遭遇的比重是 0（頭目另外擲、不算一般對手），鈕與四格那一格寫「野外多料」，兩處一樣。"""
    import server

    game = ready(jianfa_game(), side=side, loc=loc)
    plan = game.outing_plan()
    assert plan.weights[explore_one.ENCOUNTER] == 0 and plan.hint == "野外多料"
    assert plan.hint == explore_one.hint_of(plan.kind, plan.how, plan.weights)
    label = next(o for o in game.options(odds=False) if o.id == "act:explore").label
    assert label.endswith("・野外多料）") and server.main_view(game)["mostly"] == "野外多料" and game.mostly_here() == "野外多料"


CHANGED_WORDS = {"guan": {"changshe"}, "huang": {"luoyang_road"}, "haoqiang": set(), None: set()}  # 哪個身分在哪幾處不寫地點種類的字


@pytest.mark.parametrize("side", ["guan", "huang", "haoqiang", None])
def test_only_the_two_boss_only_places_change_their_word(side):
    """每一處、每一種身分：鈕上的字＝四格那一格的字；除了長社（官軍）與洛陽官道（黃巾），都是地點種類的字（寺、山、渡口也是，
    比重怎麼排都一樣）；改寫的那兩處，招牌類（遭遇）真的是 0。"""
    import server

    game = ready(jianfa_game(), side=side, loc="yingshui")
    if side == "haoqiang":  # 地方豪強先挑依附哪一軍，選單才是平常的樣子
        game.choose("faction:ally:guan")
    checked, changed = 0, set()
    for loc_id, loc in game.content.locations.items():
        if loc.prologue_only:
            continue
        ready(game, loc=loc_id)
        _reset(game)
        options = {o.id: o for o in game.options(odds=False)}
        if "act:explore" not in options:
            continue
        plan = game.outing_plan()
        assert plan is not None
        assert options["act:explore"].label.endswith(f"・{plan.hint}）"), (loc_id, plan.hint)
        assert server.main_view(game)["mostly"] == plan.hint, loc_id
        if plan.how in ("bounty", "spar"):
            continue
        if plan.hint != explore_one.HINTS[plan.kind]:
            changed.add(loc_id)
            assert not explore_one.signature_holds(plan.kind, plan.weights), (loc_id, plan.weights)
        checked += 1
    assert checked > 20 and changed == CHANGED_WORDS[side], (side, changed)


def test_the_map_names_keep_the_place_kind_words():
    """輿圖名字旁的兩個字照地點種類（表，是地點自己的事、不看誰站在那裡）：這一格不隨此刻的比重變。"""
    game = ready(jianfa_game(), side="guan", loc="changshe")
    places = {p["id"]: p["mostly"] for p in game.map_base()["places"]}
    kind = explore_one.kind_of(game.content.config.jianfa, game.content.locations["changshe"]).kind
    assert places["changshe"] == explore_one.MOSTLY[kind]


# ── 4. hints.json 的「尋敵」 ──


def _drill_done(game) -> str:
    return hints.note_for(game.state, game.content, "h_drill_done").text


def test_the_drill_done_hint_names_the_outing_when_explore_one_is_on():
    on = jianfa_game()
    assert "尋敵" not in _drill_done(on) and "出門探索" in _drill_done(on)
    assert "尋敵" in _drill_done(jianfa_game(explore_one=False))  # 子開關關著照舊
    assert "尋敵" in _drill_done(plain_game())  # 減法季關著照舊


def test_a_hint_line_for_the_outing_is_checked_when_loaded(hints_root):
    import json

    from tianxia.content import ContentError, load_content

    path = hints_root / "hints.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["hints"][3]["explore_one"] = "引薦人不寫這一句。"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ContentError, match="不寫 explore_one"):
        load_content(hints_root)
    data["hints"][3].pop("explore_one")
    data["hints"][0]["explore_one"] = "到 {oops} 再說。"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ContentError, match=re.escape("不認得的 {oops}")):
        load_content(hints_root)
