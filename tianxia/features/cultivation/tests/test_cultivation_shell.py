"""cultivation 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import pytest
import server
from tianxia.features.cultivation import cultivation
from tianxia import team
from tianxia.characters import open_characters
from tianxia.martial_arts import generate_from_name
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    _a_player_with_insights, _no_landing, _no_preset_recipes, _player, cheap_password_hashing, client,
    fresh_server_memory, game, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_menxia_practice_and_heal(client, monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert "基礎拳腳" in out["message"] and "第2成" in out["message"]  # 開局送的那一門
    assert "基礎拳腳" in out["menxia"]["player_card"]
    out = client.post("/api/menxia/heal", json={}).json()
    assert out["message"]
    assert out["main"]["status"]["name"] == "沈青衫"


def test_menxia_practice_costs_xinde_and_says_how_much_is_missing(client, monkeypatch):
    """練成花心得（每成 2N，企劃者 2026-10-07 方案 A）：第 1 成升第 2 成 2 點、第 2 成升第 3 成 4 點；不夠時直接說還差多少，
    等級與心得都不動。"""
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.stats["xinde"] = 2
    open_characters().save(game.state)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert "第2成" in out["message"]
    assert open_characters().load("沈青衫").player.stats["xinde"] == 0
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()  # 第 2 成升第 3 成要 4 點，只剩 0 點
    assert "要 4 點心得，你只有 0 點" in out["message"] and "還差 4 點" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.member.wugong_level == 2 and saved.stats["xinde"] == 0


def test_allocate_through_the_main_actions(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.stat_points = 1
    open_characters().save(game.state)
    r = client.post("/api/do/allocate", json={"stat": "con"}).json()
    assert r["main"]["status"]["stat_points"] == 0
    assert open_characters().load("沈青衫").player.stats["con"] == 6
    stat_names = server.CONTENT.config.stat_names
    assert [(name, key) for name, _, key in r["main"]["status"]["attrs"]] == [
        (stat_names[key], key) for key in ("str", "agi", "con", "wis", "lore")
    ]  # 網頁的配點鈕送的鍵就是這個鍵，要跟 Config.stat_names 對得上


def test_an_old_save_stored_without_lore_reads_as_five_through_the_server(client):
    """舊存檔（博聞加進來之前存的）：_reload 讀回來的是資料庫裡原樣的那一列、沒經過 Game 的建構，所以進鎖重讀之後也要
    照開局的 5 補上（計畫 2-2 Review Focus 1）：唯讀的 look、會存檔的 act（/api/main）、＋博聞都照常，不是 KeyError。"""
    _player(client)
    game = server.game_for("沈青衫")
    del game.state.player.stats["lore"]
    game.state.player.stat_points = 1
    open_characters().save(game.state)
    assert "lore" not in open_characters().load("沈青衫").player.stats  # 資料庫裡那一列確實沒有博聞
    game.state.player.stats["lore"] = 9  # 記憶體裡那份是別的數字：重讀要換成資料庫裡的（補成 5），不能沿用它
    assert server.look(game, lambda g: g.state.player.stats["lore"]) == server.CONTENT.config.start_stats["lore"] == 5
    status = client.get("/api/main").json()["status"]
    assert status["attrs"][-1][1:] == [5, "lore"]
    r = client.post("/api/do/allocate", json={"stat": "lore"}).json()
    assert r["main"]["status"]["stat_points"] == 0
    assert r["main"]["status"]["attrs"][-1][1:] == [6, "lore"]
    assert open_characters().load("沈青衫").player.stats["lore"] == 6


def test_a_refused_allocation_through_the_server_only_says_why(client):
    _player(client)
    r = client.post("/api/do/allocate", json={"stat": "con"}).json()
    assert "沒有可以分配" in r["message"]
    r = client.post("/api/do/allocate", json={}).json()  # 客戶端沒帶 stat：也只是一句話，不是 500
    assert "沒有這項" in r["message"]


def _an_old_blended_art(name="沈青衫") -> str:
    """以前武學＋武學合出來的那一門（煉製只剩意境＋意境，Joy 2026-10-21；登記過的照舊讀得到）：直接登記一門下品、兼容並蓄、
    由基礎拳腳與基礎吐納衍生的武學，放進這個角色的功法庫。回傳 id。"""
    art = generate_from_name("拳息合一", "武學", "拳息合一", weights={"下品": 100, "中品": 0, "上品": 0, "絕學": 0}).model_copy(
        update={"origin": "fused", "parents": ["jichu_quanjiao", "jichu_tuna"], "affinity": [], "creator": name},
    )
    assert open_world().claim_skill_name(art)
    game = server.game_for(name)
    game.state.player.arts.append(art.id)
    open_characters().save(game.state)
    return art.id


def test_a_blended_art_that_is_worn_names_its_parents_on_the_slot_card(client):
    """身上兩欄的功法卡也寫「由…衍生」（不只清單裡的卡）：改練上身，再看修練頁。"""
    _a_player_with_insights(client)
    art = team.resolve_art(_an_old_blended_art(), server.CONTENT, open_world())
    out = client.post("/api/menxia/switch", json={"art": art.id})
    assert out.status_code == 200
    view = client.get("/api/menxia").json()
    worn = next(c for c in view["slot_cards"] if c["kind"] == art.kind)
    assert "由【基礎拳腳】與【基礎吐納】衍生" in worn["card"]
    plain = next(c for c in view["slot_cards"] if c["kind"] != art.kind)
    assert "衍生" not in plain["card"]


def test_menxia_view_rows_carry_what_the_pages_need(client):
    """每門武學一列：身上的在前、功法卡已轉成 HTML、修練與熔煉按不按得下去與為什麼；意境一列一個。"""
    _a_player_with_insights(client)
    view = client.get("/api/menxia").json()
    breath, fist = view["owned_arts"]
    assert (breath["worn"], fist["worn"], breath["kind"], fist["kind"]) == (True, True, "內功", "武學")
    assert breath["level"] == 1 and breath["insight"] is None and breath["card"].startswith("<")
    # 武學重構：下品不靠修練衝品，修練那一格灰掉寫 NO_RANK_LINE；意境槽一列一格（基礎武學下品 2 格、兼容並蓄）
    assert breath["cultivate"]["ok"] is False and breath["cultivate"]["note"] == cultivation.NO_RANK_LINE
    assert breath["affinity"] == "兼容並蓄" and len(breath["slots"]) == 2 and breath["cultivate"]["xinde"] is None
    assert breath["melt"]["ok"] is False
    assert [(i["id"], i["name"], i["melt"]) for i in view["insights"]] == [("feng", "風", 10), ("huo", "火", 10)]


def test_forge_cultivate_and_melt_through_the_endpoints(client):
    # 合成（意境＋意境）、修練（只剩上品到了極處衝絕學，沒到灰掉）、熔煉三個端點接不接得上
    _a_player_with_insights(client)
    r = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]}).json()
    assert "交融" in r["message"] and r["made"] is True
    art_id = _an_old_blended_art()
    new = next(a for a in client.get("/api/menxia").json()["owned_arts"] if a["id"] == art_id)
    assert not new["worn"] and new["cultivate"]["ok"] is False and new["cultivate"]["note"] == cultivation.NO_RANK_LINE  # 下品
    stamina = open_characters().load("沈青衫").player.stamina
    r = client.post("/api/menxia/cultivate", json={"art": new["id"]}).json()
    assert r["message"] == f"<p>{cultivation.NO_RANK_LINE}</p>\n"  # 被拒絕只回一句：不花體力
    assert open_characters().load("沈青衫").player.stamina >= stamina
    r = client.post("/api/menxia/melt", json={"art": new["id"]}).json()
    assert "熔成了心得" in r["message"]
    assert all(row["id"] != new["id"] for row in r["menxia"]["owned_arts"])


def test_slotting_and_unslotting_through_the_endpoints(client):
    """武學重構：修練頁的意境槽（MENXIA_ACTIONS 的 slot／unslot）：裝上去那一列的 slots 跟著變，拆下來回到空格；不花心得。"""
    _a_player_with_insights(client)
    r = client.post("/api/menxia/slot", json={"art": "jichu_quanjiao", "insight": "feng"}).json()
    assert "裝進了【基礎拳腳】第 1 格" in r["message"]
    fist = next(a for a in r["menxia"]["owned_arts"] if a["id"] == "jichu_quanjiao")
    assert fist["slots"][0] is not None and fist["slots"][1] is None
    saved = open_characters().load("沈青衫").player
    assert saved.art_slots["jichu_quanjiao"] == ["feng", None] and saved.stats["xinde"] == 100
    r = client.post("/api/menxia/unslot", json={"art": "jichu_quanjiao", "insight": "feng"}).json()
    assert "拆了下來" in r["message"]
    assert open_characters().load("沈青衫").player.art_slots["jichu_quanjiao"] == [None, None]


def _a_peerless_candidate(client, pills=2):
    """一門（以前）合成出來、已經是上品、練到第十成、意境槽都裝滿的武學（下一步是絕學）、手上有 pills 枚破境丹、體力夠。
    回傳（功法 id，Game）。武學重構：沒有火候了，到了極處（cultivation.ready）就只等契機或服丹。"""
    from tianxia import arts

    _a_player_with_insights(client, insights=("feng", "huo", "shui", "shan"))
    art_id = _an_old_blended_art()
    game = server.game_for("沈青衫")
    game.state.player.art_quality[art_id] = "上品"
    game.state.player.art_levels[art_id] = 10
    art = team.resolve_art(art_id, server.CONTENT, game.world)
    n = len(arts.slots_of(game.state, server.CONTENT, art))
    game.state.player.art_slots[art_id] = ["feng", "huo", "shui", "shan"][:n]  # 兩門基礎武學合出來兼容並蓄：什麼都收
    from test_cultivation import STRONG  # 槽裡放效果夠濃的意境（評分不是門檻，只是讓卡上有東西）
    from tianxia.state import InsightFx

    for ins in game.state.player.art_slots[art_id]:
        game.state.player.insight_fx[ins] = InsightFx(quality="上品", general=dict(STRONG[ins]))
    game.state.player.legend_items = pills
    game.state.player.stamina = server.CONTENT.config.stamina_max
    open_characters().save(game.state)
    assert cultivation.ready(game.state, server.CONTENT, game.world, art_id)[0]
    return art_id, game


def test_the_pill_is_taken_only_when_the_request_ticks_it_with_a_real_true(client):
    """勾了才服：use_legend 只認布林 true。到了極處的那一門，沒勾就修不下去（等契機），勾了是服丹強行衝關：
    成不成都用掉一枚。"""
    from conftest import FixedRandom

    art_id, game = _a_peerless_candidate(client)
    game.rng = FixedRandom(0.99)
    for odd in (False, None, "true", 1, "yes", [True], {"a": 1}):  # 沒勾，或不是真正的 true：丹留著、什麼都不動
        body = {"art": art_id} if odd is None else {"art": art_id, "use_legend": odd}
        out = client.post("/api/menxia/cultivate", json=body).json()
        assert "不在練功房裡" in out["message"] and "你服下" not in out["message"], odd
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 2 and saved.stamina == server.CONTENT.config.stamina_max
    out = client.post("/api/menxia/cultivate", json={"art": art_id, "use_legend": True}).json()  # 擲 99：沒衝開
    assert "強行衝關" in out["message"] and "彈了回來" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 1 and saved.art_quality[art_id] == "上品"
    game.rng = FixedRandom(0.0)
    out = client.post("/api/menxia/cultivate", json={"art": art_id, "use_legend": True}).json()
    assert "強行衝關" in out["message"] and "晉為絕學" in out["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 0 and saved.art_quality[art_id] == "絕學"


def test_a_stale_page_ticking_a_pill_you_no_longer_hold_changes_nothing(client):
    """頁面過期、手上已經沒有丹，卻勾了丹送來：只回「等契機或服丹」那一句（CHANCE_LINE），什麼都不扣。
    （武學重構：沒有火候了，原本「勾了丹也照樣添火候」那一條跟著拿掉。）"""
    art_id, game = _a_peerless_candidate(client, pills=0)
    out = client.post("/api/menxia/cultivate", json={"art": art_id, "use_legend": True})
    assert out.status_code == 200 and "不在練功房裡" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    assert saved.legend_items == 0 and saved.art_quality[art_id] == "上品" and saved.stamina == server.CONTENT.config.stamina_max


def test_the_practice_page_offers_the_pill_for_the_peerless_step(client):
    """到了極處的那一門：修練那一格寫等契機或服丹，破境丹那一格是強行衝關，寫的機會跟實際擲的一樣（cultivation.force_odds）。"""
    art_id, game = _a_peerless_candidate(client)
    row = next(r for r in client.get("/api/menxia").json()["owned_arts"] if r["id"] == art_id)
    odds = cultivation.force_odds(game.state, server.CONTENT, game.world, art_id)
    stamina = server.CONTENT.config.cultivate_stamina
    assert row["cultivate"]["ok"] and row["cultivate"]["note"] == f"上品已到極處：等一場硬仗的契機，或服丹強行衝關・體力 {stamina}"
    assert row["cultivate"]["legend"]["label"] == "服下破境丹強行衝關（剩 2 枚）"
    assert row["cultivate"]["legend"]["note"] == f"約 {odds}% 衝開・體力 {stamina}"
    breath = client.get("/api/menxia").json()["owned_arts"][0]
    assert breath["cultivate"]["ok"] is False and breath["cultivate"]["legend"] is None


def test_melting_an_insight_through_the_endpoint(client):
    _a_player_with_insights(client, xinde=0)
    r = client.post("/api/menxia/melt_insight", json={"insight": "feng"}).json()
    assert "化成了心得" in r["message"] and [i["id"] for i in r["menxia"]["insights"]] == ["huo"]
    saved = open_characters().load("沈青衫").player
    assert saved.insights == ["huo"] and saved.stats["xinde"] == 10
    r = client.post("/api/menxia/melt_insight", json={"insight": "feng"}).json()  # 已經沒有了
    assert "沒有這個意境" in r["message"]


def test_melting_many_through_the_endpoint(client):
    """批量熔煉：勾的武學與意境一次熔完、寫一則江湖紀錄；不是串列的當沒勾。art_rows 帶每一門熔了退多少（網頁合計用）。"""
    _a_player_with_insights(client, xinde=100)
    _an_old_blended_art()
    fused = next(a for a in client.get("/api/menxia").json()["owned_arts"] if not a["worn"])
    assert fused["melt"]["value"] == server.CONTENT.config.melt_min_refund
    before = open_characters().load("沈青衫").player.stats["xinde"]
    assert "沒有勾選" in client.post("/api/menxia/melt_many", json={"arts": "x", "insights": 3}).json()["message"]
    r = client.post("/api/menxia/melt_many", json={"arts": [fused["id"]], "insights": ["feng", "huo"]}).json()
    assert "一口氣熔掉了 1 門武學、2 個意境" in r["message"]
    saved = open_characters().load("沈青衫")
    assert fused["id"] not in saved.player.arts and saved.player.insights == []
    assert saved.player.stats["xinde"] == before + fused["melt"]["value"] + 2 * server.CONTENT.config.melt_insight_xinde
    assert "一口氣熔掉了" in saved.journal[0].tag


def test_the_naming_row_and_the_name_action(client):
    """練成絕學的第一人：修練頁有等著取名的一列；定了名，那一列消失、武學的名字全服一起改。"""
    _a_player_with_insights(client)
    art_id = _an_old_blended_art()
    game = server.game_for("沈青衫")
    game.state.player.naming = art_id
    game.state.player.art_quality[art_id] = "絕學"
    open_characters().save(game.state)
    assert open_world().claim_master(art_id, "沈青衫")
    view = client.get("/api/menxia").json()
    assert view["naming"] == {"id": art_id, "name": view["owned_arts"][-1]["name"]}
    assert view["owned_arts"][-1]["melt"]["ok"] is False and "先替它定名" in view["owned_arts"][-1]["melt"]["note"]
    r = client.post("/api/menxia/name", json={"name": "旋風不歸腿"}).json()
    assert "旋風不歸腿" in r["message"] and r["menxia"]["naming"] is None
    assert r["menxia"]["owned_arts"][-1]["name"] == "旋風不歸腿"
    assert open_characters().load("沈青衫").player.naming is None


def test_a_bad_name_leaves_the_naming_right_in_place(client):
    _a_player_with_insights(client)
    art_id = _an_old_blended_art()
    game = server.game_for("沈青衫")
    game.state.player.naming = art_id
    open_characters().save(game.state)
    assert open_world().claim_master(art_id, "沈青衫")
    r = client.post("/api/menxia/name", json={"name": "a"}).json()
    assert "不行" in r["message"] and r["menxia"]["naming"]["id"] == art_id


def test_the_slot_cards_say_whether_each_slot_holds_an_art_and_its_level(client, monkeypatch):
    """C5：修練頁照目前那一門有沒有功法、練到第幾成，決定鍛鍊鈕亮不亮。
    全程走 API：動作端點會存檔，每次進鎖都從資料庫重讀角色，所以讀到的是存好的那一份。"""
    monkeypatch.setattr(server.CONTENT.config, "practice_injury_chance", 0.0)

    def slots(cards):
        return [(c["kind"], c["learned"], c["level"], c["maxed"]) for c in cards]

    _player(client)
    assert slots(client.get("/api/menxia").json()["slot_cards"]) == [("武學", True, 1, False), ("內功", True, 1, False)]
    game = server.game_for("沈青衫")
    monkeypatch.setattr(server.CONTENT.config, "starter_skills", [])  # 沒有開局送的武學：讀檔才不會把空著的欄位補回來
    game.state.player.member.neigong_id = None  # 欄位空著（內容改版之後的舊角色）：沒學過、第 0 成
    game.state.player.stats["xinde"] = 100  # 練成花心得：第 1 成升到第十成共 45 點，開局的 20 點不夠
    open_characters().save(game.state)
    out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert slots(out["menxia"]["slot_cards"]) == [("武學", True, 2, False), ("內功", False, 0, False)]
    assert slots(client.get("/api/menxia").json()["slot_cards"]) == [("武學", True, 2, False), ("內功", False, 0, False)]
    for _ in range(8):  # 練到第十成：練滿了沒由伺服器照 team.MAX_LEVEL 說，前端不另外記上限
        out = client.post("/api/menxia/practice", json={"kind": "武學"}).json()
    assert slots(out["menxia"]["slot_cards"]) == [("武學", True, 10, True), ("內功", False, 0, False)]
