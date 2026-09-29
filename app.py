"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。「門下」（隊伍與武學配置）與「戰報」（歷次戰鬥的列表與完整內容）
都是另外的整頁，分別由 render_menxia() 與戰報頁面自己的處理函式重畫。
左欄由上而下是場景（地點或事件）與選項按鈕、「剛剛」卡片（最新一則江湖紀錄；打完仗時換成戰鬥卡片，
卡片沒寫到的補充放在卡片底下）、「江湖紀錄」（再來的 5 則，一則一列、可點開看敘事，更早的收在摺疊區裡）。
按戰鬥卡片的「看完整戰報」或右欄的「戰報」按鈕都能打開戰報頁面。
"""
from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path

import gradio as gr

from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.save import load_game, save_game

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
# game_state、任務區塊、狀態文字、場景文字、「剛剛」卡片（打完仗時是戰鬥卡片底下的補充）、地圖、大勢、傳聞、江湖史、選項 id 清單、匿名勾選框、
# 左欄「場景／地圖」分頁、戰鬥卡片、「看完整戰報」按鈕、江湖紀錄、更早的紀錄、「展開更早的紀錄」摺疊區，
# 再加上按鈕（MAX_BUTTONS）。
LATEST_INDEX = 4
MAIN_TABS_INDEX = 11
CARD_INDEX = 12
CARD_BUTTON_INDEX = 13
JOURNAL_INDEX = 14
OLDER_INDEX = 15
OLDER_ACCORDION_INDEX = 16
N_OUTPUTS = 17 + MAX_BUTTONS
RECENT_ROWS = 5  # 「剛剛」之後直接列出幾則
OLDER_ROWS = 30  # 摺疊區裡最多幾則（存檔本來就只留 30 則）

# 戰報頁面的輸出順序（見 open_report_page／open_report_handler）：
# 江湖畫面顯示與否、戰報頁面顯示與否、戰鬥列表、選定那一場的完整內容。
REPORT_EMPTY_TEXT = "（還沒有戰報。打一場歷練或劇情戰之後，這裡會列出每一場。）"

# 門下頁面（render_menxia）的輸出順序：選取的自選欄、選取的武學、心得與規則、
# 每位隊員一組（欄、人物卡、本命、自選1、自選2）、武學庫、武學詳情、配置到、卸下、升一成、散功、訊息。
MAX_MEMBERS = 3  # 出戰隊伍最多三人
MX_COLUMN_SIZE = 3 + Game.FREE_SLOTS
MX_HEAD_INDEX = 2
MX_COLUMNS_INDEX = 3
MX_LIBRARY_INDEX = MX_COLUMNS_INDEX + MAX_MEMBERS * MX_COLUMN_SIZE
MX_DETAIL_INDEX = MX_LIBRARY_INDEX + 1
MX_EQUIP_INDEX = MX_LIBRARY_INDEX + 2
MX_UNEQUIP_INDEX = MX_LIBRARY_INDEX + 3
MX_UPGRADE_INDEX = MX_LIBRARY_INDEX + 4
MX_DISPEL_INDEX = MX_LIBRARY_INDEX + 5
MX_MESSAGE_INDEX = MX_LIBRARY_INDEX + 6
MENXIA_OUTPUTS = MX_MESSAGE_INDEX + 1

Slot = tuple[str, int]  # 選中的自選欄：(人物 key, 第幾欄，從 0 起算)

ACT_LOCK = threading.Lock()


def save_path(name: str) -> Path:
    return SAVE_DIR / (re.sub(r'[\\/:*?"<>|]', "_", name) + ".json")


def render(game: Game, focus_scene: bool = False) -> list:
    """回傳順序必須和 build_demo() 裡的 outputs 一致。"""
    options = game.options()[:MAX_BUTTONS]
    buttons = []
    for i in range(MAX_BUTTONS):
        if i < len(options):
            buttons.append(gr.update(value=options[i].label, visible=True, interactive=options[i].enabled))
        else:
            buttons.append(gr.update(visible=False))
    p = game.state.player
    # 「剛剛」那一格：這次行動打了仗就放戰鬥卡片（結果與獲得損失都在上面），卡片沒寫到的
    # （例如同時完成的新手引導與獎勵）放在卡片底下；沒打仗時放最新一則紀錄的卡片。
    card = game.battle_card() if game.shows_battle_card() else None
    latest = game.battle_extra_html() if card is not None else game.latest_entry_html()
    older = game.journal_html(1 + RECENT_ROWS, OLDER_ROWS)
    return [
        game,
        game.quest_text(),
        game.status_text(),
        game.scene_text(),
        gr.update(value=latest, visible=bool(latest)),
        game.world_map_svg(),
        game.trends_text(),
        game.rumors_text(),
        game.chronicle_text(),
        [o.id for o in options],
        p.anonymous,
        gr.update(selected="scene") if focus_scene else gr.update(),
        gr.update(value=card or "", visible=card is not None),
        gr.update(visible=card is not None),
        game.journal_html(1, RECENT_ROWS, heading="江湖紀錄", empty="（還沒有更早的紀錄。）"),
        older,
        gr.update(visible=bool(older)),
        *buttons,
    ]


# ── 門下頁面 ──────────────────────────────────────────


def menxia_selection(game: Game, slot: Slot | None, target: str | None) -> tuple[Slot | None, str | None]:
    """丟掉已經不成立的選取（例如換了新賽季）：自選欄要屬於隊中的人，武學要在武學庫裡。"""
    if slot is not None:
        key, index = slot
        slot = (key, index) if key in game.state.player.team and 0 <= index < Game.FREE_SLOTS else None
    if target not in {t for _, t in game.upgrade_options()}:
        target = None
    return slot, target


def render_menxia(game: Game, slot: Slot | None, target: str | None, message: str | None = None) -> list:
    """門下頁面的全部輸出，順序見 MX_*_INDEX；message 為 None 時保留頁面上原本的訊息。"""
    slot, target = menxia_selection(game, slot, target)
    team = game.state.player.team
    out: list = [slot, target, f"**心得** {game.state.player.stats.get('xinde', 0)}　｜　{game.menxia_rules()}"]
    for col in range(MAX_MEMBERS):
        if col >= len(team):
            out += [gr.update(visible=False)] + [gr.update()] * (MX_COLUMN_SIZE - 1)
            continue
        key = team[col]
        out += [
            gr.update(visible=True),
            game.member_card(key),
            gr.update(value=game.slot_label(key, None), variant="secondary"),
        ]
        out += [
            gr.update(value=game.slot_label(key, i), variant="primary" if slot == (key, i) else "secondary")
            for i in range(Game.FREE_SLOTS)
        ]
    out += [gr.update(choices=game.skill_library(), value=target), game.skill_detail(target)]
    out += _menxia_buttons(game, slot, target)
    out.append(gr.update() if message is None else message)
    assert len(out) == MENXIA_OUTPUTS
    return out


def _menxia_buttons(game: Game, slot: Slot | None, target: str | None) -> list:
    """「配置到」、「卸下」、「升一成」、「散功」四個按鈕：看選取決定顯示與否，文字寫明是哪一欄、多少心得。"""
    where = ""
    held = None
    if slot is not None:
        names = {key: name for name, key in game.team_members()}
        where = f"〔{names[slot[0]]}・自選{slot[1] + 1}〕"
        held = game.slot_skill(*slot)
    can_equip = (
        slot is not None and target is not None and target.startswith("skill:")
        and not game.is_innate(target) and (held is None or target != f"skill:{held}")
    )
    cost = game.upgrade_cost(target) if target else None
    refund = game.dispel_refund(target) if target else None
    return [
        gr.update(visible=can_equip, value=f"配置到{where}"),
        gr.update(visible=held is not None, value=f"卸下{where}"),
        gr.update(
            visible=target is not None, interactive=cost is not None,
            value="已達第十成" if cost is None else f"升一成（心得 {cost}）",
        ),
        gr.update(
            visible=target is not None and not game.is_innate(target), interactive=refund is not None,
            value="散功（第一成無功可散）" if refund is None else f"散功（返還心得 {refund}）",
        ),
    ]


def _scene_event(game: Game) -> str | None:
    """需要玩家到「場景」分頁讀的東西：待處理的事件（戰鬥卡片在按鈕底下、不在分頁裡，不必切換）。"""
    return game.state.pending_event


def act(game: Game | None, action, menxia: tuple[Slot | None, str | None] | None = None) -> list:
    """同步時間 → 執行動作 → 存檔 → 重畫。上鎖避免計時器與按鈕點擊同時操作同一存檔。

    menxia＝(選取的自選欄, 選取的武學) 時連門下頁面一起重畫；動作回傳的訊息（None 表示沒有）顯示在頁面上。
    戰報頁面是獨立的一整頁，不在這裡重畫（見 open_report_page／open_report_handler）。
    """
    n = N_OUTPUTS if menxia is None else N_OUTPUTS + MENXIA_OUTPUTS
    if game is None:
        return [gr.skip()] * n
    with ACT_LOCK:
        game.sync(time.time())
        before = _scene_event(game)
        msgs = action(game)
        save_game(game.state, save_path(game.state.player.name))
        after = _scene_event(game)
        out = render(game, focus_scene=after is not None and after != before)
        if menxia is not None:
            out += render_menxia(game, *menxia, None if msgs is None else "\n\n".join(msgs))
        return out


def make_option_handler(index: int):
    def handler(game, ids):
        if game is None or index >= len(ids):
            return [gr.skip()] * N_OUTPUTS
        return act(game, lambda g: g.choose(ids[index]))

    return handler


def make_fast_forward_handler(hours: int):
    def handler(game):
        return act(game, lambda g: g.advance(hours * 3600))

    return handler


def seclude_handler(game, hours):
    return act(game, lambda g: g.seclude(int(hours)))


def open_menxia(game, slot, target):
    """「門下」：藏起江湖畫面、打開門下頁面並重畫。"""
    if game is None:
        return [gr.skip()] * (2 + MENXIA_OUTPUTS)
    with ACT_LOCK:
        return [gr.update(visible=False), gr.update(visible=True)] + render_menxia(game, slot, target, "")


def close_menxia():
    """「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def make_innate_slot_handler(col: int):
    """點某人的本命欄：在武學庫與詳情選中他的本命，並取消自選欄的選取。"""

    def handler(game, slot, target):
        if game is None or col >= len(game.state.player.team):
            return [gr.skip()] * MENXIA_OUTPUTS
        with ACT_LOCK:
            key = game.state.player.team[col]
            return render_menxia(game, None, game.innate_target(key) or target, "")

    return handler


def make_free_slot_handler(col: int, index: int):
    """點某人的自選欄：選取這一欄；欄裡有武學時，也一併選中那門武學。"""

    def handler(game, slot, target):
        if game is None or col >= len(game.state.player.team):
            return [gr.skip()] * MENXIA_OUTPUTS
        with ACT_LOCK:
            key = game.state.player.team[col]
            held = game.slot_skill(key, index)
            return render_menxia(game, (key, index), f"skill:{held}" if held else target, "")

    return handler


def library_handler(game, slot, target):
    """在武學庫選一門武學：顯示它的詳情，自選欄的選取不變。"""
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    with ACT_LOCK:
        return render_menxia(game, slot, target, "")


def _page_skip() -> list:
    return [gr.skip()] * (N_OUTPUTS + MENXIA_OUTPUTS)


def equip_handler(game, slot, target):
    """把選中的武學配到選中的自選欄；原本配在別人身上的會移過來（同一隊同一門只能配一次）。"""
    if game is None:
        return _page_skip()
    slot, target = menxia_selection(game, slot, target)
    if slot is None or target is None or not target.startswith("skill:"):
        return _page_skip()
    key, index = slot
    skill_id = target.removeprefix("skill:")
    return act(game, lambda g: g.set_loadout(key, index, skill_id), menxia=(slot, target))


def unequip_handler(game, slot, target):
    if game is None:
        return _page_skip()
    slot, target = menxia_selection(game, slot, target)
    if slot is None:
        return _page_skip()
    key, index = slot
    return act(game, lambda g: g.set_loadout(key, index, None), menxia=(slot, target))


def upgrade_handler(game, slot, target):
    if game is None:
        return _page_skip()
    slot, target = menxia_selection(game, slot, target)
    if target is None:
        return _page_skip()
    return act(game, lambda g: g.upgrade(target), menxia=(slot, target))


def dispel_handler(game, slot, target):
    if game is None:
        return _page_skip()
    slot, target = menxia_selection(game, slot, target)
    if target is None:
        return _page_skip()
    return act(game, lambda g: g.dispel(target), menxia=(slot, target))


def _report_page(record_id: int | None, game: Game) -> list:
    """戰報頁面的四項輸出：藏起江湖畫面、顯示戰報頁面、戰鬥列表、選定那一場的完整內容
    （沒有任何戰報時顯示 REPORT_EMPTY_TEXT）。"""
    detail = game.battle_detail(record_id) if record_id is not None else REPORT_EMPTY_TEXT
    return [
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(choices=game.battle_list(), value=record_id),
        detail,
    ]


def open_report_page(game):
    """右欄「戰報」按鈕：打開戰報頁面，選好最新一場。"""
    if game is None:
        return [gr.skip()] * 4
    with ACT_LOCK:
        return _report_page(game.latest_battle_id(), game)


def open_report_handler(game):
    """場景卡片上的「看完整戰報」：打開戰報頁面，並選好卡片上的這一場。"""
    if game is None:
        return [gr.skip()] * 4
    with ACT_LOCK:
        return _report_page(game.battle_card_id(), game)


def close_report():
    """戰報頁面的「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def report_pick_handler(game, record_id):
    """在戰報列表點選一場：右邊顯示這一場的完整內容。"""
    if game is None:
        return gr.skip()
    with ACT_LOCK:
        return game.battle_detail(record_id)


def anonymous_handler(game, value):
    return act(game, lambda g: g.set_anonymous(value))


def map_view_handler(game):
    return act(game, lambda g: g.view_map())


def skip_tutorial_handler(game):
    return act(game, lambda g: g.skip_tutorial())


def tick_handler(game, slot, target):
    """計時器：同步時間，連同門下頁面一起重畫（保留目前的選取與訊息），內力等數字才會跟著走。"""
    return act(game, lambda g: None, menxia=(slot, target))


def open_game(name: str) -> Game:
    """讀取存檔；舊格式讀不進來時，先把原檔備份到 saves/backup/ 再開新角色，不刪除任何東西。"""
    path = save_path(name)
    if not path.exists():
        return Game.new(CONTENT, name)
    try:
        return Game(CONTENT, load_game(path))
    except ValueError:  # pydantic 的 ValidationError 屬於 ValueError
        backup = SAVE_DIR / "backup" / f"{path.stem}-{int(time.time())}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        game = Game.new(CONTENT, name)
        game.notice(f"（舊存檔的格式已不相容，已備份到 saves/backup/{backup.name}；這是新的開始。）", "舊存檔已備份")
        return game


def start(name):
    """踏入江湖：藏起開始畫面、顯示江湖畫面，門下頁面與戰報頁面維持隱藏。"""
    name = (name or "").strip()
    if not name:
        raise gr.Error("請先輸入你的名號。")
    shown = [
        gr.update(visible=False), gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
    ]  # start_col、game_row、menxia_col、report_col
    return act(open_game(name), lambda g: None) + shown


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="天下大勢") as demo:
        game_state = gr.State(None)
        ids_state = gr.State([])
        mx_slot = gr.State(None)  # 門下頁面選中的自選欄（Slot）
        mx_target = gr.State(None)  # 門下頁面選中的武學：skill:<id> 或 innate:<key>
        gr.Markdown("# 天下大勢 · 原型")
        with gr.Column(visible=True) as start_col:
            name_box = gr.Textbox(label="你的名號", placeholder="例如：沈青衫（輸入舊名號會讀取存檔）")
            start_btn = gr.Button("踏入江湖", variant="primary")
        with gr.Row(visible=False) as game_row:
            with gr.Column(scale=3):
                with gr.Tabs(selected="scene") as main_tabs:
                    with gr.Tab("場景", id="scene"):
                        scene_md = gr.Markdown()
                    with gr.Tab("地圖", id="map") as map_tab:
                        map_html = gr.HTML()
                option_btns = [gr.Button(visible=False) for _ in range(MAX_BUTTONS)]
                # 「剛剛」：最新一則江湖紀錄的卡片；這次行動打了仗時改放戰鬥卡片，latest_html 則放卡片沒寫到的補充。
                battle_card_md = gr.Markdown(visible=False, container=True)
                latest_html = gr.HTML(css_template=JOURNAL_CSS)
                card_btn = gr.Button("看完整戰報", visible=False)
                journal_html = gr.HTML(css_template=JOURNAL_CSS)
                with gr.Accordion("展開更早的紀錄", open=False, visible=False) as older_acc:
                    older_html = gr.HTML(css_template=JOURNAL_CSS)
            with gr.Column(scale=2):
                with gr.Accordion("主線與目標", open=True):
                    quest_md = gr.Markdown()
                status_md = gr.Markdown()
                with gr.Row():
                    menxia_btn = gr.Button("門下")
                    report_btn = gr.Button("戰報")
                with gr.Tabs():
                    with gr.Tab("江湖大勢"):
                        trends_md = gr.Markdown()
                    with gr.Tab("江湖傳聞"):
                        rumors_md = gr.Markdown()
                    with gr.Tab("江湖史"):
                        chronicle_md = gr.Markdown()
                    with gr.Tab("閉關"):
                        gr.Markdown("閉關可以得到心得，期間內力回復加倍。")
                        hours_sl = gr.Slider(1, 12, value=8, step=1, label="閉關時數（小時）")
                        seclude_btn = gr.Button("開始閉關")
                    with gr.Tab("設定"):
                        anon_cb = gr.Checkbox(label="匿名行走（江湖傳聞中不顯示名號）")
                        skip_tutorial_btn = gr.Button("略過新手引導")
                        gr.Markdown("**測試用：時間快轉**")
                        with gr.Row():
                            ff_btns = {h: gr.Button(f"+{h} 小時") for h in (1, 8, 24)}
        with gr.Column(visible=False) as menxia_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 門下", scale=1)
                mx_head_md = gr.Markdown(scale=6)
                back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            members = []
            with gr.Row():
                for _ in range(MAX_MEMBERS):
                    with gr.Column(visible=False, min_width=240) as member_col:
                        card_md = gr.Markdown()
                        slot_btns = [gr.Button("（空）") for _ in range(1 + Game.FREE_SLOTS)]  # 本命、自選…
                    members.append((member_col, card_md, slot_btns))
            with gr.Row():
                with gr.Column(scale=1):
                    library_radio = gr.Radio(label="武學庫", choices=[], interactive=True)
                with gr.Column(scale=1):
                    gr.Markdown("**武學詳情**")
                    detail_md = gr.Markdown()
                    with gr.Row():
                        equip_btn = gr.Button("配置到", variant="primary", visible=False)
                        unequip_btn = gr.Button("卸下", visible=False)
                        upgrade_btn = gr.Button("升一成", visible=False)
                        dispel_btn = gr.Button("散功", variant="stop", visible=False)
                    mx_message_md = gr.Markdown()
        with gr.Column(visible=False) as report_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 戰報", scale=1)
                gr.Markdown(scale=6)
                report_back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            with gr.Row():
                with gr.Column(scale=1):
                    report_list_radio = gr.Radio(label="歷次戰鬥（最新在前）", choices=[], interactive=True)
                with gr.Column(scale=2):
                    report_detail_md = gr.Markdown()

        outputs = [
            game_state, quest_md, status_md, scene_md, latest_html, map_html, trends_md, rumors_md, chronicle_md,
            ids_state, anon_cb, main_tabs, battle_card_md, card_btn, journal_html, older_html, older_acc,
            *option_btns,
        ]
        assert len(outputs) == N_OUTPUTS
        menxia_outputs = [mx_slot, mx_target, mx_head_md]
        for member_col, card_md, slot_btns in members:
            menxia_outputs += [member_col, card_md, *slot_btns]
        menxia_outputs += [library_radio, detail_md, equip_btn, unequip_btn, upgrade_btn, dispel_btn, mx_message_md]
        assert len(menxia_outputs) == MENXIA_OUTPUTS
        selection = [game_state, mx_slot, mx_target]

        start_btn.click(start, inputs=[name_box], outputs=outputs + [start_col, game_row, menxia_col, report_col])
        name_box.submit(start, inputs=[name_box], outputs=outputs + [start_col, game_row, menxia_col, report_col])
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, hours_sl], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        skip_tutorial_btn.click(skip_tutorial_handler, inputs=[game_state], outputs=outputs)
        map_tab.select(map_view_handler, inputs=[game_state], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)

        menxia_btn.click(open_menxia, inputs=selection, outputs=[game_row, menxia_col] + menxia_outputs)
        back_btn.click(close_menxia, outputs=[game_row, menxia_col])
        report_outputs = [game_row, report_col, report_list_radio, report_detail_md]
        report_btn.click(open_report_page, inputs=[game_state], outputs=report_outputs)
        card_btn.click(open_report_handler, inputs=[game_state], outputs=report_outputs)
        report_back_btn.click(close_report, outputs=[game_row, report_col])
        report_list_radio.input(
            report_pick_handler, inputs=[game_state, report_list_radio], outputs=[report_detail_md]
        )
        for col, (_, _, (innate_btn, *free_btns)) in enumerate(members):
            innate_btn.click(make_innate_slot_handler(col), inputs=selection, outputs=menxia_outputs)
            for index, btn in enumerate(free_btns):
                btn.click(make_free_slot_handler(col, index), inputs=selection, outputs=menxia_outputs)
        library_radio.input(library_handler, inputs=[game_state, mx_slot, library_radio], outputs=menxia_outputs)
        for btn, handler in (
            (equip_btn, equip_handler), (unequip_btn, unequip_handler),
            (upgrade_btn, upgrade_handler), (dispel_btn, dispel_handler),
        ):
            btn.click(handler, inputs=selection, outputs=outputs + menxia_outputs)
        gr.Timer(10).tick(tick_handler, inputs=selection, outputs=outputs + menxia_outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
