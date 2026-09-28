"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import gradio as gr

from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.save import load_game, save_game
from tianxia.state import EQUIP_SLOTS

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
# game_state、任務區塊、狀態文字、場景文字、紀錄、地圖、大勢、傳聞、江湖史、選項 id 清單、匿名勾選框、
# 左欄「場景／地圖」分頁，再加上按鈕（MAX_BUTTONS）、武學欄位下拉（EQUIP_SLOTS）、閉關武學下拉。
MAIN_TABS_INDEX = 11
N_OUTPUTS = 12 + MAX_BUTTONS + len(EQUIP_SLOTS) + 1

ACT_LOCK = threading.Lock()


def equip_slot_label(index: int) -> str:
    """把 EQUIP_SLOTS 的重複欄位（外功×2）編號，避免兩個欄位撞名。"""
    slot = EQUIP_SLOTS[index]
    dupes = [i for i, s in enumerate(EQUIP_SLOTS) if s == slot]
    if len(dupes) == 1:
        return f"{slot}欄位"
    return f"{slot}{'一二三四五'[dupes.index(index)]}"


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
    equips = [
        gr.update(choices=[("（空）", "")] + game.skill_choices(slot), value=skill_id or "")
        for slot, skill_id in zip(EQUIP_SLOTS, p.equipped)
    ]
    learned = [choice for slot in ("內功", "外功", "輕功") for choice in game.skill_choices(slot)]
    return [
        game,
        game.quest_text(),
        game.status_text(),
        game.scene_text(),
        game.log_text(),
        game.map_svg(),
        game.trends_text(),
        game.rumors_text(),
        game.chronicle_text(),
        [o.id for o in options],
        p.anonymous,
        gr.update(selected="scene") if focus_scene else gr.update(),
        *buttons,
        *equips,
        gr.update(choices=learned),
    ]


def _scene_key(game: Game) -> tuple:
    """目前需要玩家讀場景的東西：待處理事件或進行中的戰鬥。"""
    s = game.state
    return (s.pending_event, s.battle.enemy_id if s.battle else None)


def act(game: Game | None, action) -> list:
    """同步時間 → 執行動作 → 存檔 → 重畫。上鎖避免計時器與按鈕點擊同時操作同一存檔。"""
    if game is None:
        return [gr.skip()] * N_OUTPUTS
    with ACT_LOCK:
        game.sync(time.time())
        before = _scene_key(game)
        action(game)
        save_game(game.state, save_path(game.state.player.name))
        after = _scene_key(game)
        return render(game, focus_scene=after != (None, None) and after != before)


def make_option_handler(index: int):
    def handler(game, ids):
        if game is None or index >= len(ids):
            return [gr.skip()] * N_OUTPUTS
        return act(game, lambda g: g.choose(ids[index]))

    return handler


def make_equip_handler(slot: int):
    def handler(game, skill_id):
        return act(game, lambda g: g.equip(slot, skill_id or None))

    return handler


def make_fast_forward_handler(hours: int):
    def handler(game):
        return act(game, lambda g: g.advance(hours * 3600))

    return handler


def seclude_handler(game, skill_id, hours):
    if not skill_id:
        return [gr.skip()] * N_OUTPUTS
    return act(game, lambda g: g.seclude(int(hours), skill_id))


def anonymous_handler(game, value):
    return act(game, lambda g: g.set_anonymous(value))


def map_view_handler(game):
    return act(game, lambda g: g.view_map())


def skip_tutorial_handler(game):
    return act(game, lambda g: g.skip_tutorial())


def tick_handler(game):
    return act(game, lambda g: None)


def start(name):
    name = (name or "").strip()
    if not name:
        raise gr.Error("請先輸入你的名號。")
    path = save_path(name)
    game = Game(CONTENT, load_game(path)) if path.exists() else Game.new(CONTENT, name)
    return act(game, lambda g: None) + [gr.update(visible=False), gr.update(visible=True)]


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="天下大勢") as demo:
        game_state = gr.State(None)
        ids_state = gr.State([])
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
                gr.Markdown("---")
                log_md = gr.Markdown()
            with gr.Column(scale=2):
                with gr.Accordion("主線與目標", open=True):
                    quest_md = gr.Markdown()
                status_md = gr.Markdown()
                with gr.Tabs():
                    with gr.Tab("江湖大勢"):
                        trends_md = gr.Markdown()
                    with gr.Tab("江湖傳聞"):
                        rumors_md = gr.Markdown()
                    with gr.Tab("江湖史"):
                        chronicle_md = gr.Markdown()
                    with gr.Tab("武學"):
                        equip_dds = [
                            gr.Dropdown(label=equip_slot_label(i), choices=[], interactive=True)
                            for i in range(len(EQUIP_SLOTS))
                        ]
                        seclude_dd = gr.Dropdown(label="閉關修練的武學", choices=[], interactive=True)
                        hours_sl = gr.Slider(1, 12, value=8, step=1, label="閉關時數（小時）")
                        seclude_btn = gr.Button("開始閉關")
                    with gr.Tab("設定"):
                        anon_cb = gr.Checkbox(label="匿名行走（江湖傳聞中不顯示名號）")
                        skip_tutorial_btn = gr.Button("略過新手引導")
                        gr.Markdown("**測試用：時間快轉**")
                        with gr.Row():
                            ff_btns = {h: gr.Button(f"+{h} 小時") for h in (1, 8, 24)}

        outputs = [
            game_state, quest_md, status_md, scene_md, log_md, map_html, trends_md, rumors_md, chronicle_md,
            ids_state, anon_cb, main_tabs, *option_btns, *equip_dds, seclude_dd,
        ]
        assert len(outputs) == N_OUTPUTS

        start_btn.click(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        name_box.submit(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        for slot, dd in enumerate(equip_dds):
            dd.input(make_equip_handler(slot), inputs=[game_state, dd], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, seclude_dd, hours_sl], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        skip_tutorial_btn.click(skip_tutorial_handler, inputs=[game_state], outputs=outputs)
        map_tab.select(map_view_handler, inputs=[game_state], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)
        gr.Timer(10).tick(tick_handler, inputs=[game_state], outputs=outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
