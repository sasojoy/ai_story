import sys
import os
import json

# 設置 Windows 控制台輸出為 UTF-8 避免 CP950 編碼崩潰
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

# 確保可 import src 模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from src.game_engine import GameEngine
from src.models import GameStateDelta, is_placeholder_option
from src.save_manager import list_saves

# 初始化全局遊戲引擎
engine = GameEngine()


def generate_dynamic_options(npc_name: str, location_name: str, intimacy: int, turn: int) -> list:
    if npc_name == "合歡宗聖女":
        if intimacy >= 40 or turn >= 3:
            return [
                f"A) 眼神深情凝視聖女柳如煙，詢問合歡宗雙修功法的絕密心法",
                f"B) 提議與柳如煙聯手對付前來追殺的正派武林盟聯軍",
                f"C) 溫柔地將柳如煙攬入懷中，在耳畔低語運轉雙修靈氣"
            ]
        else:
            return [
                f"A) 抱拳拱手向聖女柳如煙詢問懷中血秘卷與解毒線索",
                f"B) 掏出《勞動基準法》質疑合歡宗深夜出診違規要求補償",
                f"C) 湊近柳如煙身旁，眼神挑逗並嘗試進行身體接觸試探"
            ]
    elif npc_name == "風騷老闆娘":
        if intimacy >= 40 or turn >= 3:
            return [
                f"A) 詢問老闆娘賽金花龍門客棧密道與各方勢力的核心情報",
                f"B) 提議將龍門客棧打包上市進行資本股權劃轉",
                f"C) 伸手環住賽金花豐滿的細腰，低聲討要天字房鑰匙"
            ]
        else:
            return [
                f"A) 點一壺上等竹葉青向老闆娘賽金花打聽龍門關最新消息",
                f"B) 拿出客棧餐飲評鑑表要求賽金花打八折",
                f"C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背"
            ]
    elif npc_name == "殺手阿福":
        if turn % 2 == 0:
            return [
                f"A) 詢問阿福血衣樓黑榜殺手最新的懸賞名單",
                f"B) 開出《一例一休超時加班理賠單》逼阿福簽字",
                f"C) 將劇毒匕首架在阿福脖子上逼他透露分舵地圖"
            ]
        else:
            return [
                f"A) 亮出武器防備阿福突襲，詢問血衣樓的接單規則",
                f"B) 提醒阿福現在已過下班時間，打卡下班可避免工傷",
                f"C) 拔出利刃冷不防割向阿福右手動脈進行強襲"
            ]
    elif npc_name == "錢莊老王":
        if turn % 2 == 0:
            return [
                f"A) 詢問老王少林與武當鎮派武學的拍賣行情",
                f"B) 提議成立『龍門對沖基金』進行高槓桿做空",
                f"C) 捏住老王手腕將劇毒滲入其脈搏脅迫劃轉銀票"
            ]
        else:
            return [
                f"A) 詢問老王錢莊當前存款與借貸年化利率",
                f"B) 拿出不良資產包證券化 (MBS) 方案要求槓桿加碼",
                f"C) 亮出沾血匕首逼老王交出總庫房鑰匙"
            ]
    return [
        f"A) 在當前地區 [{location_name}] 仔細搜尋蛛絲馬跡",
        f"B) 掏出《勞動基準法》與理賠條款進行談判拉扯",
        f"C) 上前進行身體接觸與耳邊輕語誘惑條款"
    ]


def get_npc_initial_options(npc_name: str) -> list:
    loc = engine.current_location
    agent = engine.agents.get(npc_name)
    intimacy = agent.profile.intimacy if agent else 0
    return generate_dynamic_options(npc_name, loc, intimacy, engine.game_turn)


initial_npc_name = engine.current_agent.profile.name if engine.current_agent else ""
DEFAULT_OPTIONS = get_npc_initial_options(initial_npc_name)


def get_status_markdown() -> str:
    p = engine.player_state
    inv_str = ", ".join(p.inventory) if p.inventory else "無"
    arts_str = ", ".join(p.cultivation_arts) if p.cultivation_arts else "無"

    current_npc_info = "無"
    intimacy_info = "0/100"
    if engine.current_agent:
        profile = engine.current_agent.profile
        tag = engine.current_agent.current_status_tag
        current_npc_info = f"**{profile.name}** ({profile.identity}) | 位置: {profile.location} | 狀態: `[{tag}]`"
        intimacy_info = f"`{profile.intimacy}/100`"

    factions_str = " | ".join([f"{k}: `{v}`" for k, v in engine.factions.items()]) if engine.factions else "無"

    md = f"""### 🗺️ [當前世界動態與主線看板]
- **當前回合**: `第 {engine.game_turn} 回合`
- **主線任務狀態**: `{engine.main_quest_summary}`
- **勢力聲望**: {factions_str}

---
### 🗡️ [{p.name} 狀態板]
- **生命 (HP)**: `{p.hp}/{p.max_hp}` | **體力**: `{p.stamina}/{p.max_stamina}`
- **魅力/吸引力**: `{p.charm}` | **金幣**: `{p.gold}` 兩
- **修為等級**: `Level {p.cultivation_level}` (經驗: `{p.cultivation_exp}`)
- **功法武學**: `{arts_str}`
- **當前互動 NPC**: {current_npc_info}
- **NPC 親密度/好感度**: {intimacy_info}
- **背包**: `{inv_str}`
"""
    return md


def get_map_markdown() -> str:
    reg = engine.get_current_region()
    exits = engine.get_available_exits()
    unlocked = list(engine.unlocked_locations)

    exits_str = ", ".join([f"`{e}`" for e in exits]) if exits else "無"
    unlocked_str = ", ".join([f"`{u}`" for u in unlocked]) if unlocked else "無"

    md = f"""### 🧭 [網狀地圖與探索看板]
- **當前所在地**: **{engine.current_location}** (危險度: `{reg.get('danger_level', '低')}`)
- **地區環境描寫**: {reg.get('description', '')}
- **鄰近可連通區域**: {exits_str}
- **已解鎖探索地圖點**: {unlocked_str}
"""
    return md


def get_saves_markdown() -> str:
    saves = list_saves()
    md_lines = ["### 💾 [存檔槽位狀態一覽]"]
    for s in saves:
        status_tag = "✅ 已存檔" if s["exists"] else "⚪ 空槽位"
        md_lines.append(f"- **Slot {s['slot_id']}**: `{status_tag}` | {s['timestamp']} | `{s['summary']}`")
    return "\n".join(md_lines)


def parse_history(history) -> list:
    clean_history = []
    if not history:
        return clean_history

    for item in history:
        if isinstance(item, dict) and "role" in item and "content" in item:
            role = item["role"]
            content = item["content"]
            text_str = ""
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        text_str += str(part["text"])
                    elif isinstance(part, str):
                        text_str += part
            else:
                text_str = str(content)
            clean_history.append({
                "role": role,
                "content": [{"type": "text", "text": text_str}]
            })
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            clean_history.append({
                "role": "user",
                "content": [{"type": "text", "text": str(item[0])}]
            })
            clean_history.append({
                "role": "assistant",
                "content": [{"type": "text", "text": str(item[1])}]
            })
    return clean_history


def restore_web_state_after_load(msg_text: str):
    clean_history = []
    if engine.current_agent and engine.current_agent.history:
        for item in engine.current_agent.history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role == "user":
                clean_history.append({"role": "user", "content": [{"type": "text", "text": str(content)}]})
            else:
                clean_history.append({"role": "assistant", "content": [{"type": "text", "text": str(content)}]})

    opts = get_npc_initial_options(engine.current_agent.profile.name if engine.current_agent else "")
    return (
        clean_history,
        get_status_markdown(),
        get_map_markdown(),
        msg_text,
        engine.current_location,
        engine.current_agent.profile.name if engine.current_agent else None,
        get_saves_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2]
    )


def on_save_click(slot_str: str):
    slot_id = int(slot_str.split()[-1])
    msg = engine.save_slot(slot_id)
    return msg, get_saves_markdown()


def on_load_click(slot_str: str):
    slot_id = int(slot_str.split()[-1])
    success = engine.load_slot(slot_id)
    if success:
        msg = f"成功讀取 Slot {slot_id} 存檔！"
    else:
        msg = f"讀取 Slot {slot_id} 失敗 (找不到存檔)"
    return restore_web_state_after_load(msg)


def continue_game():
    success = engine.load_latest_slot()
    if success:
        res = restore_web_state_after_load("已成功載入最新存檔！")
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            res[0], res[1], res[2], res[3], res[4], res[5], res[6], res[7], res[8], res[9], res[10], res[11], res[12]
        )
    else:
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            [],
            get_status_markdown(),
            get_map_markdown(),
            "未檢測到可用的歷史存檔，請開始全新冒險！",
            engine.current_location,
            engine.current_agent.profile.name if engine.current_agent else None,
            get_saves_markdown(),
            gr.update(), gr.update(), gr.update(),
            DEFAULT_OPTIONS[0], DEFAULT_OPTIONS[1], DEFAULT_OPTIONS[2]
        )


def on_select_npc(npc_name: str):
    if npc_name and engine.switch_npc(npc_name):
        msg = f"已切換互動對象至 [{npc_name}]"
    else:
        msg = "切換失敗"
    opts = get_npc_initial_options(npc_name)
    return (
        get_status_markdown(),
        msg,
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2]
    )


def on_select_location(location_name: str, history: list):
    clean_history = parse_history(history)
    if location_name and engine.move_to_location(location_name):
        reg = engine.get_current_region()
        msg = f"【轉移陣地】已抵達 [{location_name}]"

        clean_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": f"🧭 **[地圖移動]** 大俠移步至 **{location_name}**！\n\n{reg.get('description', '')}\n危險度: `{reg.get('danger_level', '未知')}` | 駐留 NPC: `{reg.get('bound_npc', '無')}`"}]
        })

        opts = get_npc_initial_options(engine.current_agent.profile.name if engine.current_agent else "")
        return (
            clean_history,
            get_status_markdown(),
            get_map_markdown(),
            msg,
            engine.current_agent.profile.name if engine.current_agent else None,
            gr.update(value=opts[0]),
            gr.update(value=opts[1]),
            gr.update(value=opts[2]),
            opts[0],
            opts[1],
            opts[2]
        )
    return (
        clean_history,
        get_status_markdown(),
        get_map_markdown(),
        "移動失敗",
        engine.current_agent.profile.name if engine.current_agent else None,
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update()
    )


def enter_jianghu(custom_name: str):
    if custom_name and custom_name.strip():
        engine.set_player_name(custom_name.strip())

    p_name = engine.player_state.name
    intro = engine.world_intro
    opening_text = f"【血夜序幕故事】\n{intro.get('opening_narrative', '')}\n\n【大背景局勢衝突】\n{intro.get('background_conflict', '')}\n\n大俠 [{p_name}] 身處龍門客棧風暴中心，眼前四大勢力盤根錯節，你準備如何踏出江湖第一步？"

    initial_history = [{
        "role": "assistant",
        "content": [{"type": "text", "text": opening_text}]
    }]

    opts = get_npc_initial_options(engine.current_agent.profile.name if engine.current_agent else "")
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        initial_history,
        get_status_markdown(),
        get_map_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2]
    )


def process_player_choice(user_input: str, history: list, prev_opt_a: str = "", prev_opt_b: str = "", prev_opt_c: str = ""):
    clean_history = parse_history(history)

    if not user_input or not user_input.strip():
        return (
            "",
            clean_history,
            get_status_markdown(),
            get_map_markdown(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update()
        )

    # 與 NPC 互動
    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    intimacy = engine.current_agent.profile.intimacy if engine.current_agent else 0
    fallback_opts = generate_dynamic_options(npc_name, engine.current_location, intimacy, engine.game_turn + 1)

    try:
        delta = engine.interact(user_input)
    except Exception as e:
        delta = GameStateDelta(
            narrative=f"[{npc_name}] 默默地看著你... (提示: Ollama LLM 連線訊息: {e})",
            player_hp_change=0,
            player_gold_change=0,
            inventory_added=[],
            inventory_removed=[],
            npc_status_tag="靜默",
            world_flag_set={},
            options=fallback_opts
        )
        engine.apply_delta(delta)

    # 檢查 LLM 回傳的故事短句，若過短或僅重複玩家行動，進行小說文風擴充與情節描繪
    narrative_text = delta.narrative.strip()
    if len(narrative_text) < 35 or narrative_text in [user_input.strip(), f"{engine.player_state.name}對{npc_name}說：{user_input}"]:
        p_name = engine.player_state.name
        if npc_name == "風騷老闆娘":
            narrative_text = f"{p_name}身形前傾，靠近風騷老闆娘賽金花。賽金花眼波盈盈，嬌笑了一聲，冰涼的手指順勢挑起{p_name}的下巴，吐息如蘭道：『大俠這般勾人，莫不是真當老娘這龍門客棧是吃素的地方？』燭光搖曳下，她的嬌軀微顫，眼神中透著幾分性感與深層試探。"
        elif npc_name == "合歡宗聖女":
            narrative_text = f"{p_name}步步逼近合歡宗聖女柳如煙。柳如煙修長的雙眸微眯，薄紗下的肌膚在暗光中泛著迷人的乳白光澤。她並未退縮，反倒輕輕呼出一口帶有淡香的溫熱輕氣：『少俠心跳得這般急，難不成合歡宗的雙修媚術，已經勾動了少俠的心神？』"
        elif npc_name == "殺手阿福":
            narrative_text = f"{p_name}眼神冷冽，直視著面前的殺手阿福。阿福握緊了手中冰冷的鐵劍，雙眼銳利如鷹，冷哼一聲：『少廢話！過了下班時辰，多待一刻鐘便是一刻鐘的工資。你要麼掏錢理賠，要麼亮招！』空氣中頓時瀰漫開一股肅殺之氣。"
        elif npc_name == "錢莊老王":
            narrative_text = f"{p_name}大步踏前，逼視著錢莊老王。老王算盤撥得飛快，金光熠熠的雙眼射出精光：『客官此言差矣！在龍門錢莊，只要資本與槓桿足夠，連天上的月亮老夫也能幫你打包證券化！』"
        delta.narrative = narrative_text

    # 組合顯示內容
    changes = []
    if delta.player_hp_change != 0:
        sign = "+" if delta.player_hp_change > 0 else ""
        changes.append(f"HP {sign}{delta.player_hp_change}")
    if delta.player_stamina_change != 0:
        sign = "+" if delta.player_stamina_change > 0 else ""
        changes.append(f"體力 {sign}{delta.player_stamina_change}")
    if delta.player_gold_change != 0:
        sign = "+" if delta.player_gold_change > 0 else ""
        changes.append(f"金幣 {sign}{delta.player_gold_change}")
    if delta.intimacy_change != 0:
        sign = "+" if delta.intimacy_change > 0 else ""
        changes.append(f"親密度 {sign}{delta.intimacy_change}")
    if delta.cultivation_exp_gained > 0:
        changes.append(f"修為經驗 +{delta.cultivation_exp_gained}")
    if delta.cultivation_art_learned:
        changes.append(f"領悟雙修功法: 【{delta.cultivation_art_learned}】")
    if delta.inventory_added:
        changes.append(f"獲得: {', '.join(delta.inventory_added)}")
    if delta.inventory_removed:
        changes.append(f"失去: {', '.join(delta.inventory_removed)}")

    status_str = f"\n\n*(⚡ 變更: {' | '.join(changes)})*" if changes else ""
    quest_str = f"\n*(📖 主線動態更新: {delta.main_quest_summary_update})*" if delta.main_quest_summary_update else ""
    tag_str = f" `[狀態: {delta.npc_status_tag}]`" if delta.npc_status_tag else ""

    bot_msg = f"{delta.narrative}{status_str}{quest_str}{tag_str}"

    clean_history.append({
        "role": "user",
        "content": [{"type": "text", "text": str(user_input)}]
    })
    clean_history.append({
        "role": "assistant",
        "content": [{"type": "text", "text": str(bot_msg)}]
    })

    # 校驗選項是否重複，若重複或包含佔位符則自動刷新動態選項
    raw_opts = delta.options if (delta.options and len(delta.options) >= 3) else fallback_opts
    is_repeated = any(opt == prev_opt_a or opt == prev_opt_b for opt in raw_opts) or any(is_placeholder_option(opt) for opt in raw_opts)

    if is_repeated:
        opts = generate_dynamic_options(npc_name, engine.current_location, intimacy, engine.game_turn)
    else:
        opts = raw_opts

    opt_a = opts[0]
    opt_b = opts[1]
    opt_c = opts[2]

    return (
        "",
        clean_history,
        get_status_markdown(),
        get_map_markdown(),
        gr.update(value=opt_a),
        gr.update(value=opt_b),
        gr.update(value=opt_c),
        opt_a,
        opt_b,
        opt_c
    )


def reset_chat():
    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    opts = get_npc_initial_options(npc_name)
    if engine.current_agent:
        engine.current_agent.reset_history()
    return (
        [],
        "對話歷史已重置",
        get_status_markdown(),
        get_map_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2],
        gr.update(visible=False)
    )


def toggle_custom_input():
    return gr.update(visible=True)


# 建立 Gradio Web UI 介面
with gr.Blocks(title="Local Blade RPG Engine") as demo:
    gr.Markdown("# 🗡️ Local Blade RPG Engine - 暗黑武俠動態沙盒")
    gr.Markdown("使用 Ollama 本地端 LLM 驅動的高自由度文字 RPG 遊戲引擎 (v1.0.0)")
    gr.Markdown("📱 **[手機與跨裝置連線網址]**: 請確保手機與電腦連接同一個 Wi-Fi 網路，於手機瀏覽器輸入 `http://192.168.1.123:7860` 即可跨裝置遊玩！")

    state_opt_a = gr.State(DEFAULT_OPTIONS[0])
    state_opt_b = gr.State(DEFAULT_OPTIONS[1])
    state_opt_c = gr.State(DEFAULT_OPTIONS[2])

    # 1. 序幕的故事、自由取名與背景衝突展示區
    with gr.Column(visible=True) as prologue_group:
        intro_data = engine.world_intro
        gr.Markdown(f"## 📜 {intro_data.get('title', '血夜龍門')}")

        player_name_input = gr.Textbox(
            label="👤 請問大俠尊姓大名？(玩家自訂姓名)",
            value="楚留香",
            placeholder="請輸入你的大俠姓名...",
            interactive=True
        )

        gr.Markdown(f"**【序幕故事】**\n\n{intro_data.get('opening_narrative', '')}")
        gr.Markdown(f"**【江湖衝突局勢】**\n\n{intro_data.get('background_conflict', '')}")
        gr.Markdown(f"**【初始主線任務】**\n\n`{engine.main_quest_summary}`")

        with gr.Row():
            btn_enter_game = gr.Button("🗡️ [踏入江湖] 開啟冒險", variant="primary", size="lg")
            btn_continue_game = gr.Button("📂 [繼續遊戲] 載入最新進度", variant="secondary", size="lg")

    # 2. 正式遊戲主介面
    with gr.Column(visible=False) as main_game_group:
        with gr.Row():
            with gr.Column(scale=1):
                status_box = gr.Markdown(value=get_status_markdown)
                map_box = gr.Markdown(value=get_map_markdown)

                location_dropdown = gr.Dropdown(
                    choices=list(engine.world_map.get("regions", {}).keys()),
                    value=engine.current_location,
                    label="🧭 移動前往周邊地點 (點擊切換區域)",
                    interactive=True
                )

                npc_dropdown = gr.Dropdown(
                    choices=list(engine.agents.keys()),
                    value=engine.current_agent.profile.name if engine.current_agent else None,
                    label="選擇互動 NPC",
                    interactive=True
                )

                gr.Markdown("### 💾 [存檔與載入控制]")
                with gr.Row():
                    slot_dropdown = gr.Dropdown(
                        choices=["Slot 1", "Slot 2", "Slot 3", "Slot 4", "Slot 5"],
                        value="Slot 1",
                        label="選擇存檔槽位",
                        scale=2
                    )
                    btn_save_slot = gr.Button("💾 快速存檔", variant="primary", scale=1)
                    btn_load_slot = gr.Button("📂 讀取存檔", variant="secondary", scale=1)

                save_list_box = gr.Markdown(value=get_saves_markdown)
                system_msg = gr.Textbox(label="系統訊息", value="準備就緒", interactive=False)
                reset_btn = gr.Button("重置與當前 NPC 對話", variant="secondary")

            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="遊戲對話紀錄", height=450)

                gr.Markdown("### 🎯 劇情動態選項")
                with gr.Row():
                    btn_opt_a = gr.Button(DEFAULT_OPTIONS[0], variant="primary")
                    btn_opt_b = gr.Button(DEFAULT_OPTIONS[1], variant="secondary")
                    btn_opt_c = gr.Button(DEFAULT_OPTIONS[2], variant="stop")

                with gr.Row():
                    btn_other = gr.Button("✏️ [其它/自由打字]", variant="secondary")

                with gr.Row(visible=False) as custom_input_row:
                    input_box = gr.Textbox(
                        show_label=False,
                        placeholder="輸入自訂行動或對話...",
                        lines=2,
                        scale=4
                    )
                    submit_btn = gr.Button("發送自訂行動", variant="primary", scale=1)

    # 踏入江湖點擊事件
    btn_enter_game.click(
        fn=enter_jianghu,
        inputs=[player_name_input],
        outputs=[prologue_group, main_game_group, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    # 繼續遊戲點擊事件
    btn_continue_game.click(
        fn=continue_game,
        inputs=[],
        outputs=[
            prologue_group, main_game_group, chatbot, status_box, map_box,
            system_msg, location_dropdown, npc_dropdown, save_list_box,
            btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 存檔與讀檔事件
    btn_save_slot.click(
        fn=on_save_click,
        inputs=[slot_dropdown],
        outputs=[system_msg, save_list_box]
    )

    btn_load_slot.click(
        fn=on_load_click,
        inputs=[slot_dropdown],
        outputs=[
            chatbot, status_box, map_box, system_msg, location_dropdown,
            npc_dropdown, save_list_box, btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 地圖移動事件
    location_dropdown.change(
        fn=on_select_location,
        inputs=[location_dropdown, chatbot],
        outputs=[chatbot, status_box, map_box, system_msg, npc_dropdown, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    # 事件繫結
    npc_dropdown.change(
        fn=on_select_npc,
        inputs=[npc_dropdown],
        outputs=[status_box, system_msg, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    # 點擊選項 A / B / C 直接推進劇情
    btn_opt_a.click(
        fn=process_player_choice,
        inputs=[state_opt_a, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[input_box, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    btn_opt_b.click(
        fn=process_player_choice,
        inputs=[state_opt_b, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[input_box, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    btn_opt_c.click(
        fn=process_player_choice,
        inputs=[state_opt_c, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[input_box, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    # 點擊 [其他] 展開自由輸入框
    btn_other.click(
        fn=toggle_custom_input,
        inputs=[],
        outputs=[custom_input_row]
    )

    # 發送自訂行動
    submit_btn.click(
        fn=process_player_choice,
        inputs=[input_box, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[input_box, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    input_box.submit(
        fn=process_player_choice,
        inputs=[input_box, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[input_box, chatbot, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c]
    )

    reset_btn.click(
        fn=reset_chat,
        inputs=[],
        outputs=[chatbot, system_msg, status_box, map_box, btn_opt_a, btn_opt_b, btn_opt_c, state_opt_a, state_opt_b, state_opt_c, custom_input_row]
    )


if __name__ == "__main__":
    print("正在啟動 Local Blade RPG Web UI (0.0.0.0:7860)...")
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)
