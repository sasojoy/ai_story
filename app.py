"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。
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
from tianxia.save import load_game, save_game

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
# game_state、任務區塊、狀態文字、場景文字、紀錄、地圖、大勢、傳聞、江湖史、選項 id 清單、匿名勾選框、
# 左欄「場景／地圖」分頁、門下文字、武學表、戰報、人物下拉、武學下拉、心得下拉，再加上按鈕（MAX_BUTTONS）。
MAIN_TABS_INDEX = 11
TEAM_INDEX = 12
REPORT_INDEX = 14
N_OUTPUTS = 18 + MAX_BUTTONS

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
        game.team_text(),
        game.skills_text(),
        game.report_text(),
        gr.update(choices=game.team_members()),
        gr.update(choices=[("（空）", "")] + game.loadout_choices()),
        gr.update(choices=game.upgrade_options()),
        *buttons,
    ]


def _scene_key(game: Game) -> str | None:
    """目前需要玩家讀場景的東西：待處理事件。"""
    return game.state.pending_event


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
        return render(game, focus_scene=after is not None and after != before)


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


def loadout_handler(game, member, slot, skill_id):
    if not member:  # game 為 None 時 act() 會自己略過
        return [gr.skip()] * N_OUTPUTS
    return act(game, lambda g: g.set_loadout(member, int(slot) - 1, skill_id or None))


def upgrade_handler(game, target):
    if not target:
        return [gr.skip()] * N_OUTPUTS
    return act(game, lambda g: g.upgrade(target))


def dispel_handler(game, target):
    if not target:
        return [gr.skip()] * N_OUTPUTS
    return act(game, lambda g: g.dispel(target))


def anonymous_handler(game, value):
    return act(game, lambda g: g.set_anonymous(value))


def map_view_handler(game):
    return act(game, lambda g: g.view_map())


def skip_tutorial_handler(game):
    return act(game, lambda g: g.skip_tutorial())


def tick_handler(game):
    return act(game, lambda g: None)


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
        game.notice(f"（舊存檔的格式已不相容，已備份到 saves/backup/{backup.name}；這是新的開始。）")
        return game


def start(name):
    name = (name or "").strip()
    if not name:
        raise gr.Error("請先輸入你的名號。")
    return act(open_game(name), lambda g: None) + [gr.update(visible=False), gr.update(visible=True)]


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
                    with gr.Tab("門下"):
                        team_md = gr.Markdown()
                        gr.Markdown("**配置武學**（同一隊裡同一門武學只能出現一次）")
                        with gr.Row():
                            member_dd = gr.Dropdown(label="人物", choices=[], interactive=True)
                            slot_radio = gr.Radio(["1", "2"], value="1", label="自選欄")
                            skill_dd = gr.Dropdown(label="武學", choices=[], interactive=True)
                        loadout_btn = gr.Button("配置")
                        gr.Markdown("**心得修練**（第 n 成升一成需要心得 20×n；散功返還八成）")
                        upgrade_dd = gr.Dropdown(label="武學", choices=[], interactive=True)
                        with gr.Row():
                            upgrade_btn = gr.Button("升一成")
                            dispel_btn = gr.Button("散功")
                        skills_md = gr.Markdown()
                    with gr.Tab("戰報"):
                        report_md = gr.Markdown()
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

        outputs = [
            game_state, quest_md, status_md, scene_md, log_md, map_html, trends_md, rumors_md, chronicle_md,
            ids_state, anon_cb, main_tabs, team_md, skills_md, report_md, member_dd, skill_dd, upgrade_dd,
            *option_btns,
        ]
        assert len(outputs) == N_OUTPUTS

        start_btn.click(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        name_box.submit(start, inputs=[name_box], outputs=outputs + [start_col, game_row])
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, hours_sl], outputs=outputs)
        loadout_btn.click(loadout_handler, inputs=[game_state, member_dd, slot_radio, skill_dd], outputs=outputs)
        upgrade_btn.click(upgrade_handler, inputs=[game_state, upgrade_dd], outputs=outputs)
        dispel_btn.click(dispel_handler, inputs=[game_state, upgrade_dd], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        skip_tutorial_btn.click(skip_tutorial_handler, inputs=[game_state], outputs=outputs)
        map_tab.select(map_view_handler, inputs=[game_state], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)
        gr.Timer(10).tick(tick_handler, inputs=[game_state], outputs=outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
