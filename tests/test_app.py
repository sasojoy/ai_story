import random

import gradio as gr

import app
from tianxia.engine import Game


def column(page, i):
    """門下頁面第 i 位隊員那一組輸出：欄、人物卡、本命、自選1、自選2。"""
    start = app.MX_COLUMNS_INDEX + i * app.MX_COLUMN_SIZE
    return page[start:start + app.MX_COLUMN_SIZE]


def test_render_matches_outputs():
    game = Game.new(app.CONTENT, "測試")
    assert len(app.render(game)) == app.N_OUTPUTS
    assert len(app.render_menxia(game, None, None)) == app.MENXIA_OUTPUTS
    assert len(app.render_map_page(game, "situation", None)) == app.MAP_OUTPUTS


def test_option_handler_acts_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    ids = [o.id for o in game.options()]
    out = app.make_option_handler(ids.index("act:explore"))(game, ids)
    assert len(out) == app.N_OUTPUTS
    assert (tmp_path / "測試.json").exists()
    assert game.state.player.stamina < 150


def test_save_path_strips_unsafe_characters(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    assert app.save_path("沈/浪?").name == "沈_浪_.json"


def test_build_demo():
    assert app.build_demo() is not None


def test_render_includes_quest_and_minimap():
    game = Game.new(app.CONTENT, "測試")
    out = app.render(game)
    assert any(isinstance(x, str) and x.startswith("### 主線") for x in out)
    minimap = out[app.MINIMAP_INDEX]
    assert minimap == game.minimap_svg() and ">揚州城（你）<" in minimap and ">↓ 鎮江渡口<" in minimap


def test_skip_tutorial_handler_finishes_tutorial(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.skip_tutorial_handler(game)
    assert len(out) == app.N_OUTPUTS
    assert game.state.player.tutorial_step == len(app.CONTENT.tutorial.steps)


def test_left_column_has_no_tabs_and_puts_the_minimap_beside_the_scene():
    demo = app.build_demo()
    tabs = [block.label for block in demo.blocks.values() if isinstance(block, gr.Tab)]
    assert "場景" not in tabs and "地圖" not in tabs  # 右欄的分頁照舊
    outputs = next(f for f in demo.fns.values() if f.fn is app.start).outputs
    scene, minimap = outputs[3], outputs[app.MINIMAP_INDEX]
    assert isinstance(scene, gr.Markdown) and isinstance(minimap, gr.HTML)
    assert isinstance(scene.parent, gr.Row) and minimap.parent.parent is scene.parent  # 場景列：左文字、右小地圖


def test_minimap_follows_an_event(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    ids = [o.id for o in game.options()]
    out = app.make_option_handler(ids.index("act:explore"))(game, ids)
    assert game.state.pending_event is not None  # 揚州城探索必定遇到城鎮事件
    assert ">揚州城（你）<" in out[app.MINIMAP_INDEX]  # 事件進行中也照常標出所在地


def test_render_includes_the_card_placeholders():
    game = Game.new(app.CONTENT, "測試")
    out = app.render(game)
    assert out[app.CARD_INDEX] == gr.update(value="", visible=False)
    assert out[app.CARD_BUTTON_INDEX] == gr.update(visible=False)


# ── 「剛剛」卡片與江湖紀錄 ─────────────────────────────


def test_latest_card_shows_the_newest_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    latest = app.render(game)[app.LATEST_INDEX]
    assert latest["visible"] is True
    assert "剛剛　第1天 00:00" in latest["value"] and "江南風雨" in latest["value"] and "賽季開始" in latest["value"]
    out = click(game, "move:yangzhou_jiao")
    latest = out[app.LATEST_INDEX]["value"]
    assert "前往 揚州城郊" in latest
    assert app.CONTENT.locations["yangzhou_jiao"].description not in latest  # 地點描述只在場景裡


def test_journal_rows_show_five_and_fold_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.render(game)
    assert "江湖紀錄" in out[app.JOURNAL_INDEX] and 'class="tx-row"' not in out[app.JOURNAL_INDEX]
    assert out[app.OLDER_INDEX] == "" and out[app.OLDER_ACCORDION_INDEX] == gr.update(visible=False)
    for i in range(8):
        game.state.player.stamina = 150
        out = click(game, "move:yangzhou_jiao" if i % 2 == 0 else "move:yangzhou")
    assert len(game.state.journal) == 9
    assert out[app.JOURNAL_INDEX].count('class="tx-row"') == 5  # 「剛剛」之後的 5 則
    assert "江湖紀錄" in out[app.JOURNAL_INDEX]
    assert out[app.OLDER_INDEX].count('class="tx-row"') == 3  # 更早的收進摺疊區
    assert "江南風雨" in out[app.OLDER_INDEX]
    assert out[app.OLDER_ACCORDION_INDEX] == gr.update(visible=True)


def test_change_tags_are_coloured_by_sign(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    click(game, "act:train")
    game.state.pending_event = None
    out = click(game, "move:yangzhou")
    assert '<span class="tx-chg tx-up">經驗 +' in out[app.JOURNAL_INDEX]  # 歷練那一則成了紀錄的一列
    game.state.player.stats["xinde"] = 100
    out = app.upgrade_handler(game, None, "skill:tuna")
    assert '<span class="tx-chg tx-down">心得 -20</span>' in out[app.LATEST_INDEX]["value"]


def test_journal_outputs_are_their_own_components():
    demo = app.build_demo()
    fns = list(demo.fns.values())
    outputs = next(f for f in fns if f.fn is app.start).outputs
    menxia_fn = next(f for f in fns if f.fn is app.open_menxia)
    html = [outputs[i] for i in (app.LATEST_INDEX, app.JOURNAL_INDEX, app.OLDER_INDEX)]
    assert all(isinstance(c, gr.HTML) for c in html) and len(set(html)) == 3
    assert isinstance(outputs[app.OLDER_ACCORDION_INDEX], gr.Accordion)
    assert not set(html) & set(menxia_fn.outputs)


# ── 戰鬥卡片與戰報 ─────────────────────────────────────


def battle_game(tmp_path, monkeypatch) -> Game:
    """一局站在揚州城郊（可以歷練）的新遊戲，存檔寫到 tmp_path。"""
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試", rng=random.Random(0))
    game.state.player.location = "yangzhou_jiao"
    return game


def click(game: Game, option_id: str) -> list:
    ids = [o.id for o in game.options()]
    return app.make_option_handler(ids.index(option_id))(game, ids)


def test_battle_shows_a_card_until_the_next_action(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    monkeypatch.setattr(app.CONTENT.config, "train_event_chance", 0.0)  # 這裡只看卡片，不要遇上事件
    out = click(game, "act:train")
    card = out[app.CARD_INDEX]
    assert card["visible"] is True and card["value"].startswith("### ⚔ 揚州城郊・對陣 ")
    assert out[app.CARD_BUTTON_INDEX] == gr.update(visible=True)
    assert out[app.LATEST_INDEX] == gr.update(value="", visible=False)  # 只顯示戰鬥卡片，不同時放「剛剛」卡片
    out = click(game, "move:yangzhou")
    assert out[app.CARD_INDEX] == gr.update(value="", visible=False)
    assert out[app.CARD_BUTTON_INDEX] == gr.update(visible=False)
    assert out[app.LATEST_INDEX]["visible"] is True and "前往 揚州城" in out[app.LATEST_INDEX]["value"]


def test_battle_card_carries_what_else_happened_in_that_action(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    game.state.player.tutorial_step = 3  # 下一步引導就是「在城郊歷練一回」，獎勵銀兩 10
    out = click(game, "act:train")
    assert out[app.CARD_INDEX]["visible"] is True
    extra = out[app.LATEST_INDEX]
    assert extra["visible"] is True and 'class="tx-extra"' in extra["value"]
    assert "✔ 引導完成" in extra["value"] and "【老說書人】" in extra["value"]
    assert '<span class="tx-chg tx-up">銀兩 +10</span>' in extra["value"]  # 引導獎勵；對手給的銀兩在卡片上
    assert "剛剛" not in extra["value"]  # 不是第二張卡片


def test_menxia_action_after_a_battle_replaces_the_battle_card(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    click(game, "act:train")
    game.state.player.stats["xinde"] = 100
    out = app.upgrade_handler(game, None, "skill:tuna")
    assert out[app.CARD_INDEX] == gr.update(value="", visible=False)  # 兩張卡片不同時出現
    assert "【吐納法】精進至第2成" in out[app.LATEST_INDEX]["value"]


def test_tick_keeps_the_card(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    click(game, "act:train")
    out = app.tick_handler(game, None, None)
    assert out[app.CARD_INDEX]["visible"] is True


def test_battle_card_output_is_not_a_menxia_component():
    """CARD_INDEX 要接到場景戰鬥卡片，不能誤用門下頁面的元件（例如命名衝突誤用了迴圈變數 card_md）。"""
    demo = app.build_demo()
    fns = list(demo.fns.values())
    start_fn = next(f for f in fns if f.fn is app.start)
    menxia_fn = next(f for f in fns if f.fn is app.open_menxia)
    assert start_fn.outputs[app.CARD_INDEX] not in menxia_fn.outputs


# ── 戰報頁面 ───────────────────────────────────────────


def test_report_page_starts_empty():
    game = Game.new(app.CONTENT, "測試")
    out = app.open_report_page(game)
    assert len(out) == 4
    assert out[:2] == [gr.update(visible=False), gr.update(visible=True)]  # 江湖畫面、戰報頁面
    assert out[2] == gr.update(choices=[], value=None)
    assert out[3] == app.REPORT_EMPTY_TEXT
    assert app.open_report_page(None) == [gr.skip()] * 4


def test_report_btn_opens_the_page_with_the_newest_selected(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    for _ in range(2):
        game.state.pending_event = None
        click(game, "act:train")
    newest, older = [rid for _, rid in game.battle_list()]
    out = app.open_report_page(game)
    assert out[:2] == [gr.update(visible=False), gr.update(visible=True)]
    listing = out[2]
    assert listing["value"] == newest and listing["choices"] == game.battle_list()
    assert out[3] == game.battle_detail(newest)


def test_report_back_btn_returns_to_the_main_view():
    assert app.close_report() == [gr.update(visible=True), gr.update(visible=False)]


def test_card_btn_opens_the_report_page_with_that_record(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    for _ in range(2):
        game.state.pending_event = None
        click(game, "act:train")
    newest, older = [rid for _, rid in game.battle_list()]
    out = app.open_report_handler(game)  # 卡片上的「看完整戰報」
    assert len(out) == 4
    assert out[:2] == [gr.update(visible=False), gr.update(visible=True)]
    listing = out[2]
    assert listing["value"] == newest == game.battle_card_id()
    assert out[3] == game.battle_detail(newest)
    assert app.open_report_handler(None) == [gr.skip()] * 4


def test_report_list_pick_shows_that_record(tmp_path, monkeypatch):
    game = battle_game(tmp_path, monkeypatch)
    for _ in range(2):
        game.state.pending_event = None
        click(game, "act:train")
    newest, older = [rid for _, rid in game.battle_list()]
    assert app.report_pick_handler(game, older) == game.battle_detail(older) != game.battle_detail(newest)
    assert app.report_pick_handler(None, older) == gr.skip()


def test_tick_does_not_touch_the_report_page(tmp_path, monkeypatch):
    """計時器只重畫江湖畫面／門下頁面，不該碰戰報頁面的元件（戰報頁面開著時，行動的按鈕本來就看不到）。"""
    game = battle_game(tmp_path, monkeypatch)
    click(game, "act:train")
    out = app.tick_handler(game, None, None)
    assert len(out) == app.N_OUTPUTS + app.MENXIA_OUTPUTS  # 沒有多出戰報頁面的欄位


def test_report_page_outputs_are_not_menxia_or_main_components():
    """戰報頁面自己的列表／詳情元件不能誤用門下頁面或其他頁面既有的元件
    （game_row／report_col 本來就是好幾個處理函式都要切換顯示與否的容器，共用不算誤用）。"""
    demo = app.build_demo()
    fns = list(demo.fns.values())
    report_fn = next(f for f in fns if f.fn is app.open_report_page)
    card_fn = next(f for f in fns if f.fn is app.open_report_handler)
    menxia_fn = next(f for f in fns if f.fn is app.open_menxia)
    start_fn = next(f for f in fns if f.fn is app.start)
    assert report_fn.outputs[2:] == card_fn.outputs[2:]  # 戰報按鈕與看完整戰報共用同一組列表／詳情元件
    assert not set(report_fn.outputs[2:]) & set(menxia_fn.outputs)
    assert not set(report_fn.outputs[2:]) & set(start_fn.outputs)


# ── 門下頁面 ──────────────────────────────────────────


def test_menxia_page_shows_cards_slots_and_library():
    game = Game.new(app.CONTENT, "測試")
    out = app.render_menxia(game, None, None)
    assert out[:2] == [None, None]
    assert "**心得** 0" in out[app.MX_HEAD_INDEX] and "本命不能散功" in out[app.MX_HEAD_INDEX]
    shown, card, innate, free1, free2 = column(out, 0)
    assert shown == gr.update(visible=True)
    assert card.startswith("### 測試（隊長）") and "內力" in card
    assert innate["value"] == "本命　家傳劍法（絕招）第1成"
    assert free1["value"] == "自選1　吐納法（心法）第1成" and free1["variant"] == "secondary"
    assert free2["value"] == "自選2　長拳（連招）第1成"
    assert column(out, 1)[1].startswith("### 韓鐵") and column(out, 2)[1].startswith("### 小墨")
    library = out[app.MX_LIBRARY_INDEX]
    assert [t for _, t in library["choices"]] == [
        "skill:tuna", "skill:changquan", "skill:jiachuan", "innate:hantie", "innate:xiaomo"
    ]
    assert library["value"] is None
    assert "點選" in out[app.MX_DETAIL_INDEX]
    for index in (app.MX_EQUIP_INDEX, app.MX_UNEQUIP_INDEX, app.MX_UPGRADE_INDEX, app.MX_DISPEL_INDEX):
        assert out[index]["visible"] is False


def test_library_labels_stay_short_with_real_content():
    game = Game.new(app.CONTENT, "沈青衫")
    for skill_id in app.CONTENT.skills:  # 全部武學都學會、都練到第十成：最長的情形
        game.state.player.skills[skill_id] = 10
    labels = [label for label, _ in game.skill_library()]
    assert max(len(label) for label in labels) <= 42, max(labels, key=len)


def test_menxia_hides_columns_beyond_the_team():
    game = Game.new(app.CONTENT, "測試")
    game.state.player.teams[0].members = ["player", "hantie"]
    out = app.render_menxia(game, None, None)
    assert column(out, 1)[0] == gr.update(visible=True)
    assert column(out, 2)[0] == gr.update(visible=False)


def test_menxia_drops_stale_selection():
    game = Game.new(app.CONTENT, "測試")
    out = app.render_menxia(game, ("ghost", 0), "skill:nothing")
    assert out[:2] == [None, None]


def test_open_and_close_menxia_flip_visibility():
    game = Game.new(app.CONTENT, "測試")
    out = app.open_menxia(game, None, None)
    assert len(out) == 2 + app.MENXIA_OUTPUTS
    assert out[:2] == [gr.update(visible=False), gr.update(visible=True)]  # 江湖畫面、門下頁面
    assert out[2 + app.MX_MESSAGE_INDEX] == ""
    assert app.close_menxia() == [gr.update(visible=True), gr.update(visible=False)]


def test_start_leaves_menxia_report_and_map_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    out = app.start("測試")
    assert len(out) == app.N_OUTPUTS + 1 + len(app.PAGES)
    assert out[-5:] == [gr.update(visible=False), gr.update(visible=True)] + [gr.update(visible=False)] * 3


def test_free_slot_click_selects_the_slot_and_its_art():
    game = Game.new(app.CONTENT, "測試")
    out = app.make_free_slot_handler(0, 0)(game, None, None)
    assert len(out) == app.MENXIA_OUTPUTS
    assert out[:2] == [("player", 0), "skill:tuna"]
    assert column(out, 0)[3]["variant"] == "primary" and column(out, 0)[4]["variant"] == "secondary"
    assert out[app.MX_LIBRARY_INDEX]["value"] == "skill:tuna"
    assert out[app.MX_DETAIL_INDEX].startswith("### 吐納法")
    unequip = out[app.MX_UNEQUIP_INDEX]
    assert unequip["visible"] is True and unequip["value"] == "卸下〔測試・自選1〕"
    assert out[app.MX_EQUIP_INDEX]["visible"] is False  # 已經配在這一欄


def test_empty_free_slot_keeps_the_chosen_art():
    game = Game.new(app.CONTENT, "測試")
    out = app.make_free_slot_handler(1, 0)(game, None, "skill:changquan")
    assert out[:2] == [("hantie", 0), "skill:changquan"]
    equip = out[app.MX_EQUIP_INDEX]
    assert equip["visible"] is True and equip["value"] == "配置到〔韓鐵・自選1〕"
    assert out[app.MX_UNEQUIP_INDEX]["visible"] is False


def test_equip_through_the_page_moves_the_art(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    slot = app.make_free_slot_handler(1, 0)(game, None, None)[0]
    chosen = app.library_handler(game, slot, "skill:tuna")
    assert chosen[:2] == [("hantie", 0), "skill:tuna"]
    assert chosen[app.MX_EQUIP_INDEX]["visible"] is True
    out = app.equip_handler(game, slot, "skill:tuna")
    assert len(out) == app.N_OUTPUTS + app.MENXIA_OUTPUTS
    p = game.state.player
    assert p.loadouts["hantie"][0] == "tuna"
    assert p.loadouts["player"] == [None, "changquan"]  # 一門武學同時只配給一個人
    page = out[app.N_OUTPUTS:]
    assert column(page, 1)[3]["value"] == "自選1　吐納法（心法）第1成"
    assert column(page, 0)[3]["value"] == "自選1　（空）"
    assert "韓鐵的第1個武學欄：吐納法" in page[app.MX_MESSAGE_INDEX]
    assert game.state.journal[0].tag == "韓鐵的第1個武學欄：吐納法"
    assert "韓鐵的第1個武學欄：吐納法" in out[app.LATEST_INDEX]["value"]
    assert (tmp_path / "測試.json").exists()


def test_innate_slot_selects_the_innate_and_hides_equip_and_dispel():
    game = Game.new(app.CONTENT, "測試")
    out = app.make_innate_slot_handler(0)(game, ("hantie", 0), "skill:tuna")
    assert out[:2] == [None, "skill:jiachuan"]
    assert out[app.MX_EQUIP_INDEX]["visible"] is False
    assert out[app.MX_DISPEL_INDEX]["visible"] is False
    upgrade = out[app.MX_UPGRADE_INDEX]
    assert upgrade["visible"] is True and upgrade["value"] == "升一成（心得 20）"
    assert all(button["variant"] == "secondary" for button in column(out, 1)[2:])
    out = app.make_innate_slot_handler(2)(game, None, None)
    assert out[:2] == [None, "innate:xiaomo"]
    assert out[app.MX_DETAIL_INDEX].startswith("### 亂針")


def test_player_innate_cannot_be_equipped_into_a_free_slot():
    game = Game.new(app.CONTENT, "測試")
    out = app.library_handler(game, ("hantie", 0), "skill:jiachuan")
    assert out[:2] == [("hantie", 0), "skill:jiachuan"]
    assert out[app.MX_EQUIP_INDEX]["visible"] is False


def test_unequip_empties_the_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.unequip_handler(game, ("player", 0), "skill:tuna")
    assert game.state.player.loadouts["player"] == [None, "changquan"]
    page = out[app.N_OUTPUTS:]
    assert page[app.MX_UNEQUIP_INDEX]["visible"] is False
    assert page[app.MX_EQUIP_INDEX]["visible"] is True  # 還選著吐納法，可以再配回去


def test_upgrade_and_dispel_through_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    p = game.state.player
    p.stats["xinde"] = 100
    page = app.upgrade_handler(game, None, "skill:tuna")[app.N_OUTPUTS:]
    assert p.skills["tuna"] == 2 and p.stats["xinde"] == 80
    assert "精進至第2成" in page[app.MX_MESSAGE_INDEX]
    assert "**心得** 80" in page[app.MX_HEAD_INDEX]
    assert page[app.MX_UPGRADE_INDEX]["value"] == "升一成（心得 40）"
    assert page[app.MX_DISPEL_INDEX]["value"] == "散功（返還心得 16）"
    assert page[app.MX_DISPEL_INDEX]["interactive"] is True
    page = app.dispel_handler(game, None, "skill:tuna")[app.N_OUTPUTS:]
    assert p.skills["tuna"] == 1 and p.stats["xinde"] == 96
    assert page[app.MX_DISPEL_INDEX]["interactive"] is False  # 第一成無功可散


def test_upgrade_without_xinde_shows_the_message_on_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.upgrade_handler(game, None, "skill:tuna")
    assert "心得不足" in out[app.N_OUTPUTS + app.MX_MESSAGE_INDEX]
    assert game.state.player.skills["tuna"] == 1
    assert len(game.state.journal) == 1 and "心得不足" not in out[app.LATEST_INDEX]["value"]  # 失敗不進江湖紀錄


def test_upgrade_button_at_the_tenth_level():
    game = Game.new(app.CONTENT, "測試")
    game.state.player.skills["tuna"] = 10
    out = app.render_menxia(game, None, "skill:tuna")
    assert out[app.MX_UPGRADE_INDEX]["value"] == "已達第十成"
    assert out[app.MX_UPGRADE_INDEX]["interactive"] is False


def test_page_actions_skip_without_a_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    skip = [gr.skip()] * (app.N_OUTPUTS + app.MENXIA_OUTPUTS)
    assert app.equip_handler(game, None, "skill:tuna") == skip
    assert app.equip_handler(game, ("hantie", 0), None) == skip
    assert app.unequip_handler(game, None, "skill:tuna") == skip
    assert app.upgrade_handler(game, None, None) == skip
    assert app.dispel_handler(game, None, None) == skip
    assert app.equip_handler(None, ("hantie", 0), "skill:tuna") == skip
    assert app.tick_handler(None, None, None) == skip
    assert game.state.player.loadouts["player"] == ["tuna", "changquan"]
    assert not (tmp_path / "測試.json").exists()


def test_tick_refreshes_the_page_and_keeps_the_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.state.player.members["hantie"].neili = 100.0
    out = app.tick_handler(game, ("player", 1), "skill:changquan")
    assert len(out) == app.N_OUTPUTS + app.MENXIA_OUTPUTS
    page = out[app.N_OUTPUTS:]
    assert page[:2] == [("player", 1), "skill:changquan"]
    assert "內力 100 / " in column(page, 1)[1]
    assert page[app.MX_MESSAGE_INDEX] == gr.update()  # 不清掉上一則訊息


def test_incompatible_old_save_is_backed_up(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    (tmp_path / "測試.json").write_text("{}", encoding="utf-8")
    out = app.start("測試")
    game = out[0]
    assert game.state.player.name == "測試"
    backups = list((tmp_path / "backup").glob("測試-*.json"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "{}"
    assert any("已備份" in line for line in game.state.log)
    assert game.state.journal[0].title == "舊存檔已備份" and "已備份到 saves/backup/" in game.state.journal[0].lines[0]


# ── 大地圖頁面 ─────────────────────────────────────────


def map_page(out: list) -> list:
    """open_world_map 輸出裡大地圖頁面的那一段（順序見 MAP_*_INDEX）。"""
    return out[app.N_OUTPUTS + len(app.PAGES):]


def test_open_world_map_shows_the_page_and_finishes_the_guide_step(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.state.player.tutorial_step = 1  # 第二步是「按『大地圖』看看」
    out = app.open_world_map(game)
    assert len(out) == app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS
    assert out[app.N_OUTPUTS:app.N_OUTPUTS + len(app.PAGES)] == app.show_page("map")
    assert game.state.player.tutorial_step == 2
    assert "✔ 引導完成" in out[app.LATEST_INDEX]["value"]  # 江湖畫面也跟著重畫
    assert (tmp_path / "測試.json").exists()
    page = map_page(out)
    assert page[app.MAP_HEAD_INDEX] == "⏳ 第1天 00:00　**體力** 150 / 150"  # 引導獎勵的體力超過上限不算
    assert page[app.MAP_LAYER_INDEX] == gr.update(value="situation")  # 預設「局勢」
    assert page[app.MAP_SVG_INDEX].startswith("<svg") and ">太湖寇亂 30<" in page[app.MAP_SVG_INDEX]
    places = page[app.MAP_PLACE_INDEX]
    assert places["value"] == "yangzhou" and ("揚州城（所在地）", "yangzhou") in places["choices"]  # 預設選中所在地
    assert page[app.MAP_DETAIL_INDEX].startswith("### 揚州城（所在地）")
    assert page[app.MAP_TRAVEL_INDEX] == gr.update(visible=False)  # 所在地不顯示「安排前往」
    assert app.open_world_map(None) == [gr.skip()] * (app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS)


def test_the_four_pages_are_mutually_exclusive():
    assert app.show_page("map") == [gr.update(visible=False)] * 3 + [gr.update(visible=True)]
    assert app.close_world_map() == [gr.update(visible=True)] + [gr.update(visible=False)] * 3
    demo = app.build_demo()
    fns = list(demo.fns.values())
    pages = next(f for f in fns if f.fn is app.start).outputs[-len(app.PAGES):]
    game_row = pages[0]
    assert [f.outputs[-len(app.PAGES) - app.MAP_OUTPUTS:][:len(app.PAGES)] for f in fns if f.fn is app.open_world_map] == [
        pages
    ] * 3  # 右欄按鈕、小地圖、小地圖下方的按鈕
    assert next(f for f in fns if f.fn is app.close_world_map).outputs == pages

    def inside(block, container) -> bool:
        while block is not None:
            if block is container:
                return True
            block = block.parent
        return False

    # 打開整頁的按鈕全都在江湖畫面裡：一頁開著時按不到另一頁，門下、戰報、大地圖不會同時出現。
    openers = (app.open_menxia, app.open_report_page, app.open_report_handler, app.open_world_map)
    for fn in (f for f in fns if f.fn in openers):
        assert all(inside(demo.blocks[block_id], game_row) for block_id, _ in fn.targets)


def test_switching_layers_redraws_only_the_map_page(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    page = app.map_page_handler(game, "routes", "gaoyou")
    assert len(page) == app.MAP_OUTPUTS
    assert page[app.MAP_LAYER_INDEX] == gr.update(value="routes")
    assert ">10 體力<" in page[app.MAP_SVG_INDEX] and "數字：走過去最省的體力" in page[app.MAP_SVG_INDEX]
    assert page[app.MAP_PLACE_INDEX]["value"] == "gaoyou"
    assert page[app.MAP_TRAVEL_INDEX] == gr.update(visible=True, value="安排前往（約 10 體力）", interactive=True)
    page = app.map_page_handler(game, "enemies", "gaoyou")
    assert "最險：水寇嘍囉 穩勝" in page[app.MAP_SVG_INDEX]
    assert "**敵情**　水寇嘍囉 穩勝、太湖水寇 穩勝" in page[app.MAP_DETAIL_INDEX]
    assert app.map_page_handler(game, "nonsense", "nowhere")[app.MAP_PLACE_INDEX]["value"] == "yangzhou"
    assert app.map_page_handler(None, "routes", "gaoyou") == [gr.skip()] * app.MAP_OUTPUTS
    assert not (tmp_path / "測試.json").exists()  # 看地圖不算行動，不存檔


def test_clicking_a_place_on_the_map_selects_it():
    game = Game.new(app.CONTENT, "測試")
    page = app.map_click_handler(game, "story", gr.EventData(None, {"loc": "gaoyou"}))
    assert page[app.MAP_PLACE_INDEX]["value"] == "gaoyou"
    assert page[app.MAP_DETAIL_INDEX].startswith("### 高郵湖")
    assert 'r="18" fill="none" stroke="#2C2C2A"' in page[app.MAP_SVG_INDEX]  # 被選的地點加粗標示
    skip = [gr.skip()] * app.MAP_OUTPUTS
    assert app.map_click_handler(game, "story", gr.EventData(None, {"loc": "hanshan"})) == skip  # 沒名字的淡點
    assert app.map_click_handler(game, "story", gr.EventData(None, {})) == skip
    assert app.map_click_handler(None, "story", gr.EventData(None, {"loc": "gaoyou"})) == skip


def test_clicking_the_map_ignores_malformed_event_data():
    game = Game.new(app.CONTENT, "測試")
    skip = [gr.skip()] * app.MAP_OUTPUTS
    for data in (None, [], ["gaoyou"], "loc", 3, {"loc": None}, {"loc": ["gaoyou"]}, {"loc": {"id": "gaoyou"}}, {"loc": 3}):
        assert app.map_click_handler(game, "story", gr.EventData(None, data)) == skip, data
    assert app.map_click_handler(game, "story", None) == skip


def test_unknown_place_shows_only_that_it_is_unknown():
    game = Game.new(app.CONTENT, "測試")
    page = app.map_page_handler(game, "situation", "suzhou")
    assert page[app.MAP_DETAIL_INDEX] == "### 蘇州城？\n\n尚未摸清"
    assert page[app.MAP_TRAVEL_INDEX] == gr.update(visible=False)


def test_travel_button_explains_why_it_cannot_go():
    game = Game.new(app.CONTENT, "測試")
    game.state.pending_event = "tavern_brawl"
    page = app.map_page_handler(game, "situation", "gaoyou")
    assert page[app.MAP_TRAVEL_INDEX] == gr.update(visible=True, value="有事件待處理，不能安排前往", interactive=False)


TRAVEL_OUTPUTS = app.N_OUTPUTS + len(app.PAGES) + app.MAP_OUTPUTS  # 江湖畫面、四個整頁、大地圖頁面


def test_travel_returns_to_the_main_view_at_the_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    out = app.travel_handler(game, "situation", "gaoyou")
    assert len(out) == TRAVEL_OUTPUTS
    assert out[app.N_OUTPUTS:app.N_OUTPUTS + len(app.PAGES)] == app.show_page("main")
    assert map_page(out) == [gr.skip()] * app.MAP_OUTPUTS  # 大地圖頁面藏起來了，不用重畫
    assert game.state.player.location == "gaoyou"
    assert out[3].startswith("【高郵湖】")  # 場景顯示抵達的地點
    assert "前往 高郵湖（途經 揚州城郊）" in out[app.LATEST_INDEX]["value"]
    assert (tmp_path / "測試.json").exists()
    assert app.travel_handler(None, "situation", "gaoyou") == [gr.skip()] * TRAVEL_OUTPUTS


def test_refused_trip_stays_on_the_map_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    game.state.pending_event = "tavern_brawl"  # 按鈕是舊的：打開大地圖之後才冒出事件
    out = app.travel_handler(game, "story", "gaoyou")
    assert len(out) == TRAVEL_OUTPUTS
    assert out[app.N_OUTPUTS:app.N_OUTPUTS + len(app.PAGES)] == app.show_page("map")  # 留在大地圖
    page = map_page(out)
    assert page[app.MAP_LAYER_INDEX] == gr.update(value="story") and page[app.MAP_PLACE_INDEX]["value"] == "gaoyou"
    assert page[app.MAP_DETAIL_INDEX].startswith("**沒能出發**：有事件待處理，不能安排前往。\n\n### 高郵湖")
    assert page[app.MAP_TRAVEL_INDEX] == gr.update(visible=True, value="有事件待處理，不能安排前往", interactive=False)
    assert game.state.player.location == "yangzhou"
    demo = app.build_demo()
    wired = next(f for f in demo.fns.values() if f.fn is app.travel_handler)
    assert len(wired.outputs) == TRAVEL_OUTPUTS and len(wired.inputs) == 3


def test_normal_redraws_never_simulate_odds(tmp_path, monkeypatch):
    from tianxia import team

    monkeypatch.setattr(app, "SAVE_DIR", tmp_path)
    game = Game.new(app.CONTENT, "測試")
    calls = []
    real = team.run_battle
    monkeypatch.setattr(team, "run_battle", lambda *args: calls.append(1) or real(*args))
    app.tick_handler(game, None, None)
    app.open_world_map(game)  # 預設局勢層；所在地沒有敵人
    assert calls == []
