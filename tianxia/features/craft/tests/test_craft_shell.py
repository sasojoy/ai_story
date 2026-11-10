"""craft 這一包的測試，從 tests/server/test_server.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import json
import re
import threading
import time
import pytest
import llm_queue
import server
import webharness
from tianxia import fusion, naming
from tianxia.features.craft import forge_view
from tianxia.characters import open_characters
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
# autouse 的 fixture 要明列：少一個，這個檔就會在沒有關排程、沒換雜湊參數之下跑（第 61 批）
from server_kit import (  # noqa: F401
    FENG_HUO, _ScriptedQueue, _a_player_with_insights, _forger, _js_function, _model, _no_landing, _no_preset_recipes,
    _nobody_holds_the_lock, _player, breaker_clock, cheap_password_hashing, client, fresh_server_memory, game,
    lock_events, model_breaker_closed, save_dir, scheduler_off, season_already_open,
)

pytestmark = pytest.mark.whole_content


def test_forge_line_endpoint_says_what_one_lone_item_is_missing(client):
    """W4：煉製頁放了一樣東西就問一次 /api/forge_line，字的唯一出處是 forge_view.forge_line。"""
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng"]
    open_characters().save(game.state)
    insight = client.post("/api/forge_line", json={"insights": ["feng"]}).json()["line"]
    assert forge_view.FORGE_ONE_INSIGHT in insight


def test_forge_line_previews_without_forging(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stats["xinde"] = 100
    open_characters().save(game.state)  # 資料庫是唯一的真實來源：進鎖先重讀，只改記憶體的話下一個請求就看不到
    out = client.post("/api/forge_line", json={"insights": ["feng", "huo"]}).json()
    assert "合併" in out["line"] and "「風」＋「火」→ 一個新的意境" in out["line"]
    out = client.post("/api/forge_line", json={}).json()  # 什麼都沒放：只說怎麼放
    assert "放兩個意境" in out["line"]
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng", "huo"] and saved.stats["xinde"] == 100
    assert open_world().lookup_insight_recipe(FENG_HUO) is None  # 只是預覽：沒登記
    view = client.get("/api/menxia").json()
    assert "放兩個意境" in view["forge_line"] and "craft_line" not in view and "per_craft" not in view


def test_the_furnace_page_sends_only_insights():
    """爐裡只合意境（Joy 2026-10-21）：網頁沒有測試框架，這裡擋住「伺服器只收意境、網頁卻還送武學」。"""
    js = webharness.app_source()
    body = _js_function(js, "function forgeBody(")
    assert "insights:" in body and "other_art" not in body and "art:" not in body.replace("insights:", "")
    ready = _js_function(js, "function forgeReady(")
    assert "insights.length === 2" in ready  # 兩個意境才放得滿
    pick = _js_function(js, "function pick(")
    assert "已經放滿了" in pick and 'type !== "ins"' in pick  # 放滿了不再收；武學放不進爐
    assert "/api/forge_line" in js and "/api/menxia/forge" in js and js.count("forgeBody()") >= 2  # 預覽與開爐送同一份 body


def test_the_pages_trim_the_furnace_whenever_the_menxia_data_is_replaced():
    """修練頁熔掉爐裡放著的東西、再回煉製頁：S.forgeSel 還留著那個 id，爐子看起來是空的、開爐卻亮著（forgeReady 照 id 數）。
    只有輪詢的 refreshPage 會補，所以每個換掉 S.menxia 的地方都要自己修剪（mx、loadMenxia）。網頁沒有測試框架，這裡擋住漏改。"""
    js = webharness.app_source()
    for header in ("async function mx(", "async function loadMenxia("):
        body = _js_function(js, header)
        assert "S.menxia = " in body and "trimPot()" in body, header
        assert body.index("trimPot()") > body.index("S.menxia = "), header  # 換上新資料之後才修剪
    trim = _js_function(js, "function trimPot(")
    assert "trimForgeSel()" in trim and 'S.forgeLine = ""' in trim and "updateForgeLine()" in trim


def test_the_forge_refuses_an_art_and_points_to_the_practice_page(client):
    """爐裡只合意境（Joy 2026-10-21）：放一門武學＋一個意境不再是裝槽（裝槽在修練頁，MENXIA_ACTIONS 的 slot），
    開爐回 fusion.ART_IN_FURNACE 那一句，什麼都不動。"""
    _a_player_with_insights(client)
    out = client.post("/api/menxia/forge", json={"art": "jichu_quanjiao", "insights": ["feng"]})
    assert out.status_code == 200 and fusion.ART_IN_FURNACE in out.json()["message"]
    assert out.json()["made"] is False  # 沒做成：煉製頁把東西留在爐裡
    saved = open_characters().load("沈青衫").player
    assert all(x is None for slots in saved.art_slots.values() for x in slots) and saved.arts == []
    assert saved.stats["xinde"] == 100 and saved.insights == ["feng", "huo"]


def test_the_forge_merges_two_insights(client):
    _a_player_with_insights(client)
    out = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert out.status_code == 200 and "交融" in out.json()["message"]
    saved = open_characters().load("沈青衫").player
    merged = open_world().lookup_insight_recipe(fusion.merge_key("feng", "huo"))
    assert merged is not None and merged.attribute == "陽" and saved.insights == ["feng", "huo", merged.id]
    assert saved.stats["xinde"] == 95


def test_the_forge_refuses_what_it_cannot_do_and_charges_nothing(client):
    _a_player_with_insights(client, insights=("feng",), xinde=2)
    # 爐裡只合意境（Joy 2026-10-21）：放了武學一律被拒絕（舊網頁送來的 other_art 也一樣）；同一個意境放兩次是揣摩，要兩份、5 點心得
    for body in ({"art": "jichu_quanjiao", "other_art": "jichu_tuna"}, {"insights": ["feng", "feng"]},
                 {"art": "jichu_quanjiao", "insights": ["huo"]}, {"art": "jichu_quanjiao", "insights": []}):
        out = client.post("/api/menxia/forge", json=body)
        assert out.status_code == 200 and out.json()["message"], body
        assert out.json()["made"] is False, body  # 沒合成：煉製頁把東西留在爐裡
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng"] and saved.stats["xinde"] == 2
    assert all(x is None for slots in saved.art_slots.values() for x in slots) and saved.insight_strength.get("feng", 1) == 1  # 沒裝、沒加深
    other = client.post("/api/menxia/heal", json={})
    assert "made" not in other.json()  # 只有開爐帶這個鍵


def test_the_forge_endpoints_survive_oddly_shaped_bodies(client):
    """body 是玩家（或亂送的客戶端）寫的：art 不是字串、insights 不是清單都不能打出 500，也不能動到任何東西。"""
    _a_player_with_insights(client)
    bodies = (
        {"art": ["jichu_quanjiao"], "insights": ["feng"]},
        {"art": {"id": "jichu_quanjiao"}, "insights": ["feng"]},
        {"art": 5, "insights": ["feng"]},
        {"art": "jichu_quanjiao", "insights": "feng"},
        {"art": "jichu_quanjiao", "insights": {"feng": 1}},
        {"art": None, "insights": 7},
        {"insights": [["feng"], {"x": 1}]},
        {"art": "jichu_quanjiao", "other_art": ["jichu_tuna"], "insights": []},
        {"art": "jichu_quanjiao", "other_art": {"id": 1}},
        {"other_art": "jichu_tuna", "insights": ["feng"]},
        {},
    )
    for body in bodies:
        line = client.post("/api/forge_line", json=body)
        assert line.status_code == 200 and isinstance(line.json()["line"], str), body
        out = client.post("/api/menxia/forge", json=body)
        assert out.status_code == 200 and out.json()["message"], body
    saved = open_characters().load("沈青衫").player
    assert saved.arts == [] and saved.insights == ["feng", "huo"] and saved.stats["xinde"] == 100
    assert all(x is None for slots in saved.art_slots.values() for x in slots)  # 武學重構：形狀不對也不會把意境裝進槽


def test_forge_line_warns_about_an_insight_you_have_not_learned(client):
    _player(client)
    line = client.post("/api/forge_line", json={"insights": ["feng", "huo"]}).json()["line"]
    assert line.startswith("<p>⚠") and "兩個意境都要是你悟得的" in line


def test_forge_line_does_not_leak_an_art_the_player_does_not_have(client):
    """預覽不能拿來探：別人的本命武學（龍頭人物的）不在你身上，不管放在哪一格，都不寫名字與屬性（爐裡只合意境：武學根本不讀）。"""
    _a_player_with_insights(client)
    assert "caocao_wugong" in server.CONTENT.skills  # 真的有這一門（挾風槍法・屬快），探得到才算數
    for body in (
        {"art": "caocao_wugong", "insights": ["feng"]},
        {"art": "caocao_wugong", "insights": ["feng", "huo"]},
        {"art": "jichu_quanjiao", "other_art": "caocao_wugong", "insights": []},
        {"art": "caocao_wugong", "other_art": "jichu_quanjiao", "insights": []},
    ):
        line = client.post("/api/forge_line", json=body).json()["line"]
        assert "挾風槍法" not in line and "屬快" not in line, (body, line)
SHAN_SHUI = fusion.merge_key("shan", "shui")  # 要第二個新配方時用的


def _crafts(name):
    """這個角色江湖紀錄裡「煉製」的那幾則（同一種連續的會併成一則，所以比內容，不只比則數）。"""
    return [e.model_dump() for e in open_characters().load(name).journal if e.title == "煉製"]


def test_the_forge_endpoint_never_asks_the_model_while_holding_the_lock(client):
    _a_player_with_insights(client)
    game = server.game_for("沈青衫")
    asked = []

    def reply(model, messages):
        _nobody_holds_the_lock(game)
        asked.append(model.timeout)
        return "旋風腿"

    with _model(reply):
        out = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert out.status_code == 200 and "旋風腿" in out.json()["message"]
    # 預算 60 秒（扣掉 A 段等鎖的時間）；chat_structured 一次最多送兩趟，所以一趟最多一半。原本那個 client 不動
    assert len(asked) == 1 and 25 < asked[0] <= server.CONTENT.config.naming_budget_seconds / 2
    assert game.client.timeout == server.CONTENT.config.ollama_timeout


def test_a_forge_in_the_lock_respects_the_model_breaker(monkeypatch, breaker_clock):
    """沒給 proposed 直接在鎖內開爐（整季機器人那條路）：斷路器開著時鎖內不叫模型，名字走退路字表。"""
    game = _forger(insights=("feng", "huo", "shan", "shui"))
    server.act(game, lambda g: g.forge(None, ["feng", "huo"]))  # 鎖內取名失敗（conftest 假成連不上）→ 斷路器打開
    asked = []
    with _model(lambda model, messages: asked.append(1) or "山水清音"):
        msgs = server.act(game, lambda g: g.forge(None, ["shan", "shui"]))  # 另一個新配方
    assert asked == [] and any("交融" in m for m in msgs)
    assert open_world().lookup_insight_recipe(SHAN_SHUI).name != "山水清音"


def test_while_it_is_open_another_players_hold_starts_spent_and_asks_nothing(monkeypatch, breaker_clock):
    """甲在鎖內替首次出現的配方取名（沒給 proposed），模型連不上（conftest）：斷路器打開。乙接著也在鎖內開一爐新配方：
    這次拿鎖一開始額度就用完，不叫模型（假的模型一次都沒被叫到），照樣合成、名字走退路字表。"""
    jia, yi = _forger("甲", insights=("shan", "shui")), _forger("乙")
    server.act(jia, lambda g: g.forge(None, ["shan", "shui"]))
    asked, spent = [], []
    with _model(lambda model, messages: asked.append(1) or "旋風腿"):
        msgs = server.act(yi, lambda g: spent.append(g._model_budget.gave_up) or g.forge(None, ["feng", "huo"]))  # 乙合另一爐
    assert spent == [True] and asked == []
    assert any("交融" in m for m in msgs)
    assert open_world().lookup_insight_recipe(fusion.merge_key("feng", "huo")).name != "旋風腿"


def test_a_recipe_registered_between_the_two_trips_gives_the_registered_art():
    """乙備料、取名的時候，甲把同一個配方合出來登記了：乙進鎖時拿到的是甲登記的那一個意境（照常付心得），
    乙的模型取的名字不登記，全服只有一筆。"""
    first, second = _forger("甲"), _forger("乙")
    with _model(lambda model, messages: "疾風腿"):
        proposed = server.prepare_forge(second, None, ["feng", "huo"])  # 乙的 A、B
    assert proposed == ("疾風腿", "一句話。")
    with _model(lambda model, messages: "旋風腿"):
        server.forge(first, None, ["feng", "huo"])  # 甲從頭到尾
    msgs = server.act(second, lambda g: g.forge(None, ["feng", "huo"], proposed=proposed))  # 乙的 C
    world = open_world()
    made = world.lookup_insight_recipe(FENG_HUO)
    assert made.name == "旋風腿" and not world.is_skill_name_taken("疾風腿")
    saved = open_characters().load("乙").player
    assert made.id in saved.insights and saved.stats["xinde"] == 95
    assert any("由甲首悟" in m for m in msgs)


def test_a_second_tab_that_spends_the_xinde_while_naming_leaves_the_first_forge_refused_and_free():
    """Infra 第 2 點：B 段在鎖外等模型的時候，同一個角色在另一個分頁把同一份心得花在另一爐；C 段進鎖重驗，
    心得不夠了就整個不做：不登記配方、不扣東西、不寫紀錄，告訴玩家變了什麼。"""
    game = _forger(insights=("feng", "huo", "shan", "shui"), xinde=5)
    depth = []

    def reply(model, messages):
        if not depth:
            depth.append(1)
            server.forge(game, None, ["feng", "huo"])  # 另一個分頁：完整的一爐合併（它自己的取名是下面那一句）
            return "旋風腿"
        return "燎原"

    with _model(reply):
        msgs = server.forge(game, None, ["shan", "shui"])
    saved = open_characters().load("沈青衫").player
    fire = open_world().lookup_insight_recipe(FENG_HUO)
    assert fire.name == "燎原" and fire.id in saved.insights and saved.stats["xinde"] == 0
    assert any("心得不足" in m for m in msgs)
    assert open_world().lookup_insight_recipe(SHAN_SHUI) is None and not open_world().is_skill_name_taken("旋風腿")
    assert len(_crafts("沈青衫")) == 1 and "燎原" in _crafts("沈青衫")[0]["tag"]


def test_fb069_the_forge_never_names_a_recipe_after_a_character(lock_events):
    """FB-069：鎖外取名（B 段）拿到別的角色的名號不算取到名字（60 秒的預算只夠問一次，所以直接走退路字表）；
    C 段進鎖再擋一次。不會登記成角色的名號。"""
    _forger("驗收新武")
    game = _forger()
    asked = []
    with _model(lambda client, messages: asked.append(1) or "驗收新武"):
        assert server.prepare_forge(game, None, ["feng", "huo"]) == server.NO_NAME
        server.forge(game, None, ["feng", "huo"])
    assert asked == [1, 1]  # 兩次 prepare 各問一次，都被擋下來
    name = open_world().lookup_insight_recipe(FENG_HUO).name
    assert name != "驗收新武" and naming.name_problem(name, server.CONTENT) is None
    assert server.forge(game, None, ["feng", "huo"]) is not None  # 一般的名字照常（武學重構：另一爐換成合併意境）


def test_the_refusals_reach_the_page_as_a_short_message(client, monkeypatch):
    """被擋下來的請求回 400 與那一句話（前端的 api() 會把 error 跳成提示），不是 500。"""
    monkeypatch.setattr(server, "QUEUE", _ScriptedQueue("busy", "busy"))
    _a_player_with_insights(client)
    forged = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert forged.status_code == 400 and forged.json() == {"error": "上一爐還沒出爐。"}
    assert open_world().lookup_insight_recipe(FENG_HUO) is None
    game = server.game_for("沈青衫")
    from tianxia.models import Effect, FreeTextChoice

    event = next(iter(server.CONTENT.events.values()))
    monkeypatch.setattr(event, "free_text", FreeTextChoice(prompt="自己想辦法……", stat="str", effect=Effect(text="成了。")))
    server.act(game, lambda g: setattr(g.state, "pending_event", event.id))
    answered = client.post("/api/answer", json={"text": "大喊官兵來了"})
    assert answered.status_code == 400 and answered.json() == {"error": "上一句還在掂量，稍等。"}
    assert client.get("/api/main").json()["event_free_text"] == "自己想辦法……"  # 眼前的事還在原地


def test_a_queue_timeout_reaches_the_page_as_the_same_kind_of_short_message(client, monkeypatch):
    """排太久的拒絕跟重複的那一件走同一條路：400 與那一句話（前端的 api() 會跳成提示），什麼都沒登記、沒收、沒擲骰。"""
    monkeypatch.setattr(server, "QUEUE", _ScriptedQueue("timeout", "timeout"))
    _a_player_with_insights(client)
    forged = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert forged.status_code == 400 and forged.json() == {"error": server.BUSY_QUEUE_TIMEOUT}
    assert open_world().lookup_insight_recipe(FENG_HUO) is None and open_characters().load("沈青衫").player.stats["xinde"] == 100
    game = server.game_for("沈青衫")
    from tianxia.models import Effect, FreeTextChoice

    event = next(iter(server.CONTENT.events.values()))
    monkeypatch.setattr(event, "free_text", FreeTextChoice(prompt="自己想辦法……", stat="str", effect=Effect(text="成了。")))
    server.act(game, lambda g: setattr(g.state, "pending_event", event.id))
    answered = client.post("/api/answer", json={"text": "大喊官兵來了"})
    assert answered.status_code == 400 and answered.json() == {"error": server.BUSY_QUEUE_TIMEOUT}
    assert not any(e.title.endswith("隨口應對") for e in open_characters().load("沈青衫").journal)
    assert client.get("/api/main").json()["event_free_text"] == "自己想辦法……"  # 眼前的事還在原地


def test_the_forge_endpoint_goes_through_a_real_queue(client, monkeypatch):
    """佇列開著、端對端（HTTP → 開爐 → 排隊 → 模型取名 → 登記）：名字是模型取的，做完佇列是空的。"""
    queue = llm_queue.LlmQueue(slots=1, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    _a_player_with_insights(client)
    asked = []
    with _model(lambda model, messages: asked.append(queue.snapshot()) or "旋風腿"):
        out = client.post("/api/menxia/forge", json={"insights": ["feng", "huo"]})
    assert out.status_code == 200 and "旋風腿" in out.json()["message"]
    assert asked == [{"running": 1, "waiting": 0}]  # 模型叫的時候，這一件正在佇列裡跑
    assert queue.snapshot() == {"running": 0, "waiting": 0}


def test_a_duplicate_forge_is_refused_and_the_first_one_registers_the_models_name(monkeypatch):
    """同一個玩家兩個分頁同時開同一爐（審查 M2、控制者裁示，取代原本「重複的那一件拿退路」）：第二件被擋下來，不走 C 段，
    什麼都不登記、什麼都不收，回一句「上一爐還沒出爐。」；模型只叫一次，第一件登記的是模型取的名字、心得只扣一次。
    以前第二件拿 NO_NAME 先進鎖，這個配方這一季就用退路字表的名字登記，第一件模型取的名字被丟掉。"""
    queue = llm_queue.LlmQueue(slots=2, bot_cap=1)
    monkeypatch.setattr(server, "QUEUE", queue)
    game = _forger()
    started, release = threading.Event(), threading.Event()
    asked, first = [], {}

    def reply(model, messages):
        asked.append(1)
        started.set()
        release.wait(5)
        return "旋風腿"

    with _model(reply):
        thread = threading.Thread(target=lambda: first.update(msgs=server.forge(game, None, ["feng", "huo"])))
        thread.start()
        assert started.wait(2)
        with pytest.raises(server.GameError, match="上一爐還沒出爐"):
            server.forge(game, None, ["feng", "huo"])  # 第一件還在模型那邊的時候，第二件被擋下來
        assert open_world().lookup_insight_recipe(FENG_HUO) is None  # 第二件什麼都沒登記
        assert open_characters().load("沈青衫").player.stats["xinde"] == 100  # 也什麼都沒收
        release.set()
        thread.join(5)
    assert asked == [1]  # 模型只被叫一次（第一件的）
    assert open_world().lookup_insight_recipe(FENG_HUO).name == "旋風腿"  # 登記的是模型取的名字，不是退路字表的
    assert first["msgs"] is not None
    assert open_characters().load("沈青衫").player.stats["xinde"] == 95  # 只收一次
    assert queue.snapshot() == {"running": 0, "waiting": 0}


def test_a_refused_forge_does_not_leave_the_waiting_message_on_the_craft_page():
    """審查 M-2：開爐被擋下來（另一個分頁的上一爐還沒出爐，伺服器回 400）之後，煉製頁上方不能還寫著「爐火正旺。……請稍候」：
    重畫之前結果那一格（S.forgeResult，2026-10-10 起寫在開爐旁邊）要換成那一句拒絕（api() 丟的 Error 帶著伺服器的話），
    爐裡放的東西留著；成功的路訊息換成結果、爐子清空（Joy 2026-10-12），伺服器回「沒合成」的拒絕話時東西留著。頁面不捲到最上面。在 node 裡真的跑 forge()（假的 DOM、api 與 renderPage）。"""
    import json

    if webharness.NODE is None:
        pytest.skip("沒有裝 node")
    js = webharness.app_source()
    parts = [
        re.search(r"(?m)^  const esc = .*;$", js).group(0),
        re.search(r"(?m)^  const FORGE_WAIT = .*;$", js).group(0),
        re.search(r"(?ms)^  const failText = .*?\);$", js).group(0),
        _js_function(js, "function watchQueue(") + "\n  }",
        js[js.index("\n  // ── 送出指令的回饋 ──"):js.index("\n  // ── 送出指令的回饋（完）──")],
        _js_function(js, "async function forge(") + "\n  }",
        _js_function(js, "function trimForgeSel(") + "\n  }",
    ]
    script = "\n".join(parts) + """
    globalThis.setTimeout = () => 0;  // watchQueue 的計時器不真的跑
    let S, seen, button, bar, api;
    const document = { getElementById: (id) => (id === "forge" ? button : bar), querySelector: () => null };
    let scrolled = 0;
    const window = { scrollTo() { scrolled += 1; } };
    const forgeBody = () => ({});
    const renderPage = () => seen.push(S.forgeResult && S.forgeResult.html);
    const guideKey = () => null, updateForgeLine = () => {}, keepPlace = (draw) => draw(), showMadeCard = () => {}, kilnBurst = () => {}, secretPop = () => {};
    const renderTop = () => {};
    const setMain = () => {};
    const run = async (answer) => {
      S = { busy: false, message: "", offline: false, forgeSel: [{ type: "art", id: "a" }, { type: "ins", id: "i" }], forgeLine: "舊說明", menxia: null };
      seen = [];
      button = { disabled: false, textContent: "開爐", classList: { add() {} } };
      bar = { textContent: "" };
      api = answer;
      await forge();
      return { renderedWith: seen, message: S.forgeResult.html, waiting: button.textContent, sel: S.forgeSel.length, line: S.forgeLine, busy: S.busy, scrolled };
    };
    (async () => {
      const refused = await run(async () => { throw new Error("上一爐還沒出爐。"); });
      const done = await run(async () => ({ menxia: { owned_arts: [{ id: "a" }], insights: [{ id: "i" }] }, message: "<p>煉成了。</p>", main: {}, made: true }));
      const declined = await run(async () => ({ menxia: { owned_arts: [{ id: "a" }], insights: [{ id: "i" }] }, message: "<p>你已經有了。</p>", main: {}, made: false }));
      const offline = await run(async () => { S.offline = true; throw new Error("fetch failed"); });
      console.log(JSON.stringify({ refused, done, declined, offline }));
    })();
    """
    done = webharness.node(script)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    refused = out["refused"]
    assert refused["waiting"].startswith("爐火正旺")  # 等的時候寫的字
    assert refused["renderedWith"] == ["上一爐還沒出爐。"] and refused["message"] == "上一爐還沒出爐。"  # 重畫的時候已經換成那一句
    assert refused["sel"] == 2 and refused["line"] == "舊說明" and refused["busy"] is False  # 爐裡的東西留著、可以再按
    assert out["done"]["renderedWith"] == ["<p>煉成了。</p>"] and out["done"]["sel"] == 0 and out["done"]["line"] == ""  # 合成了：爐子清空（Joy 2026-10-12）
    assert out["declined"]["renderedWith"] == ["<p>你已經有了。</p>"] and out["declined"]["sel"] == 2  # 被拒絕、沒合成：東西留在爐裡
    assert "爐火正旺" not in out["offline"]["message"]  # 別的錯（例如斷線）也不再停在「爐火正旺」
    assert out["done"]["scrolled"] == 0  # 開爐之後不捲到最上面（企劃者 2026-10-10「點完又會跳到畫面最上面」）


def test_a_paused_season_never_asks_the_model(client, monkeypatch):
    """暫停中，鎖外三段（對話、大場面、開爐、隨口應對）在第一段就擋，送模型的單子連問都不問引擎要
    （只看回的 400 分不出第一段有沒有擋：第三段進鎖後會回同一句，白叫一次模型）。"""
    _player(client)
    assert server.game_for("沈青衫").world.pause_clock(time.time())
    asked = []
    for name in ("dialogue_request", "fight_request", "forge_request", "free_text_request"):
        monkeypatch.setattr(Game, name, lambda self, *a, _name=name, **k: asked.append(_name))
    for path, body in (
        ("/api/choose", {"id": "act:socialize"}), ("/api/choose", {"id": "act:train"}),
        ("/api/menxia/forge", {"art": "x", "insights": ["y"]}), ("/api/answer", {"text": "上前勸架"}),
    ):
        assert client.post(path, json=body).status_code == 400, path
    assert asked == []


def _craft_v2_on(monkeypatch):
    """意境合成改版：主機的開關＋這一季的章（開季時蓋，這裡直接寫進資料庫）。"""
    monkeypatch.setattr(server.CONTENT.config.craft, "enabled", True)
    monkeypatch.setattr(server.CONTENT.config.craft, "near_chance", 0.0)
    monkeypatch.setattr(server.CONTENT.config.craft, "bonus_chance", 0.0)
    open_world().mutate_season(lambda season: setattr(season, "craft_v2", True))


def test_the_preview_has_no_he_block_while_the_overhaul_is_off(client):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng", "huo"]
    open_characters().save(game.state)
    out = client.post("/api/forge_line", json={"insights": ["huo", "feng"], "pour": True}).json()
    assert out["preview"] is not None and "he" not in out["preview"]
    assert "fusion" not in client.get("/api/main").json()["status"]


def test_the_preview_carries_heat_the_four_conditions_and_the_pour_toggle(client, monkeypatch):
    _craft_v2_on(monkeypatch)
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng", "huo"]
    open_characters().save(game.state)
    he = client.post("/api/forge_line", json={"insights": ["huo", "feng"]}).json()["preview"]["he"]
    assert he["kind"] == "合併" and he["form"] == "變" and he["aux"] and he["grand"] == fusion.UNSEEN and he["can_pour"]
    assert [c["key"] for c in he["conds"]] == ["layers", "pour", "place", "secret"]
    assert next(c for c in he["conds"] if c["key"] == "pour")["ok"] is False
    poured = client.post("/api/forge_line", json={"insights": ["huo", "feng"], "pour": True}).json()["preview"]["he"]
    assert next(c for c in poured["conds"] if c["key"] == "pour")["ok"] is True
    assert client.post("/api/forge_line", json={"insights": ["huo", "feng"], "pour": "yes"}).json()["preview"]["he"]["conds"][1]["ok"] is False  # 只認 true


def test_forging_writes_the_aux_form_into_the_furnace_book(client, monkeypatch):
    _craft_v2_on(monkeypatch)
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng", "huo"]
    game.state.player.stats["xinde"] = 500
    open_characters().save(game.state)
    out = client.post("/api/menxia/forge", json={"insights": ["huo", "feng"], "intent": "守住不退"})  # 舊網頁多送的立意不理
    assert out.status_code == 200, out.text
    book = open_characters().load("沈青衫").player.fusion_book
    assert book[fusion.merge_key("huo", "feng")].form == "變" and book[fusion.merge_key("huo", "feng")].uses == 1


def test_infuse_goes_through_the_menxia_table_and_refuses_when_off(client, monkeypatch):
    _player(client)
    game = server.game_for("沈青衫")
    game.state.player.insights = ["feng", "feng~2"]
    open_characters().save(game.state)
    off = client.post("/api/menxia/infuse", json={"body": "feng", "others": ["feng~2"]}).json()
    assert "還不能化入" in off["message"] and open_characters().load("沈青衫").player.insights == ["feng", "feng~2"]
    _craft_v2_on(monkeypatch)
    status = client.get("/api/main").json()["status"]
    assert status["fusion"]["per_layer"] == server.CONTENT.config.craft.yun_per_layer
    on = client.post("/api/menxia/infuse", json={"body": "feng", "others": ["feng~2", 5, ["x"]]}).json()
    saved = open_characters().load("沈青衫").player
    assert saved.insights == ["feng"] and "化進" in on["message"]


def test_the_he_block_draws_what_the_server_said_and_nothing_when_absent():
    """預覽卡的改版那一塊（craft.js heHtml）：沒有 v.he 一個字都不畫；有的話火候、型（看輔料）、未看破、傾注、成神墨點照伺服器給的畫。"""
    js = (server.ROOT / "web" / "craft.js").read_text(encoding="utf-8")
    script = "\n".join([
        'const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", \'"\': "&quot;"}[c]));',
        _js_function(js, "function heHtml(") + "\n  }",
    ]) + """
    let S = { forgePour: true, heRoad: true };
    const he = { kind: "合併", heat: 5, need: 6, near: true, general: "乘勝", form: "變", aux: "先<手>", grand: "未看破", grand_desc: null, uses: 0,
      conds: [{ key: "layers", label: "兩份都三重", ok: false, miss: "再深一點" }, { key: "pour", label: "傾注", ok: true, miss: null }],
      god: false, hint: null, can_pour: true };
    console.log(JSON.stringify({ none: heHtml(undefined), html: heHtml(he) }));
    """
    done = webharness.node(script)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["none"] == ""
    html = out["html"]
    assert "he-heat near" in html and "差一點" in html and "未看破" in html and "unseen" in html
    assert "先&lt;手&gt;" in html and "變型" in html and "he-intent" not in html
    assert 'data-act="he-pour"' in html and 'aria-pressed="true"' in html
    assert html.count('<i class="on">') == 1 and "再深一點" in html
