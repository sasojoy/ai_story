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
from src.options import generate_fallback_options, generate_single_fallback_option, generate_fallback_delta
from src.save_manager import list_account_saves, has_account_save, load_account_game, save_account_game
from src.ending_writer import DEFAULT_OUTPUT_DIR, load_ending_writer_config, make_ollama_beat_generator, make_rwkv_beat_generator
from src.intimate_mode import list_intimate_actions, attempt_intimate_action
from src.scene_templates import load_scene_templates, get_action_label

# 獨立帳號 Session 引擎註冊表
session_engines: dict = {}


def get_engine_for_user(username: str = "楚留香") -> GameEngine:
    clean_name = username.strip() if (username and username.strip()) else "楚留香"
    if clean_name not in session_engines:
        eng = GameEngine()
        if has_account_save(clean_name):
            load_account_game(clean_name, eng)
        else:
            eng.set_player_name(clean_name)
        session_engines[clean_name] = eng
    return session_engines[clean_name]


def _pick_intimate_menu(matches: list) -> list:
    """從 list_intimate_actions() 回傳的 (act_name, entry) 清單裡挑出最多 3 個放進選單。
    優先保留最多 2 個非收尾動作 + 1 個收尾動作，確保只要有任何 is_finisher=True 的
    動作符合資格，玩家就一定有辦法結束性愛模式，不會卡在只能選非收尾動作的死路。
    不足 3 個時重複最後一個湊滿，配合既有 UI 固定 3 顆按鈕的限制（見 btn_opt_a/b/c）。"""
    finishers = [m for m in matches if m[1].is_finisher]
    others = [m for m in matches if not m[1].is_finisher]
    menu = others[:2] + finishers[:1]
    if len(menu) < 3:
        rest = [m for m in matches if m not in menu]
        menu += rest[: 3 - len(menu)]
    while menu and len(menu) < 3:
        menu.append(menu[-1])
    return menu[:3]


def get_intimate_menu_options(engine: GameEngine, npc_name: str) -> list:
    """性愛模式的動作選單標籤：優先顯示 entry.label（玩家導向的動作描述，例如
    「撫弄她的胸乳」），沒填才 fallback 用 act_name 本身（見 get_action_label）。
    沿用一般回合制既有的 3 顆按鈕 UI，不另外開新元件。刻意不寫回
    agent.last_offered_options/tags——性愛模式的選項比對改成直接拿按鈕文字對照
    scene_templates.json 算出來的 label，跟一般回合制的 tag 比對系統是兩套獨立機制，
    見 process_intimate_choice。"""
    agent = engine.agents.get(npc_name)
    if not agent:
        return ["A) ...", "B) ...", "C) ..."]
    templates = load_scene_templates()
    matches = list_intimate_actions(agent.profile, templates, engine.intimate_mode_ending_type or "good")
    menu = _pick_intimate_menu(matches)
    labels = [get_action_label(name, entry) for name, entry in menu]
    return labels if labels else ["（靜靜地靠近她）"]


def get_npc_initial_options(engine: GameEngine, npc_name: str) -> list:
    """生成一組全新的保底選項給指定 NPC，並同步寫回 agent.last_offered_options/tags，
    確保玩家下一次點擊按鈕時 NPCAgent 能正確比對出這次行動屬於哪個分類。

    每次呼叫都先確認一次是否該進入性愛模式（check_and_enter_intimate_mode 本身有
    triggered_endings/intimate_mode_npc 保護，重複呼叫是安全的）——這是所有選項產生
    路徑的共同起點 (on_select_npc/on_select_location/enter_jianghu 都會經過這裡)，
    在這裡集中判斷，其餘呼叫端不用各自處理。"""
    engine.check_and_enter_intimate_mode()
    if engine.intimate_mode_npc == npc_name:
        return get_intimate_menu_options(engine, npc_name)

    loc = engine.current_location
    agent = engine.agents.get(npc_name)
    disp_name = agent.profile.display_name if agent else None
    used_history = set(agent.used_options_history) if agent else set()
    options, tags = generate_fallback_options(npc_name, loc, engine.game_turn, used_history, disp_name=disp_name)
    if agent:
        agent.last_offered_options = list(options)
        agent.last_offered_tags = list(tags)
    return options


def get_display_options(engine: GameEngine, npc_name: str) -> list:
    """回傳目前應該顯示給玩家的選項：優先沿用 agent 已記錄的 last_offered_options
    (例如剛讀檔還原、延續存檔當下的選項)，查無才生成新的保底選項。"""
    engine.check_and_enter_intimate_mode()
    if engine.intimate_mode_npc == npc_name:
        return get_intimate_menu_options(engine, npc_name)
    agent = engine.agents.get(npc_name)
    if agent and agent.last_offered_options and len(agent.last_offered_options) >= 3:
        return agent.last_offered_options[:3]
    return get_npc_initial_options(engine, npc_name)


DEFAULT_NPC_NAME = None
engine = get_engine_for_user("楚留香")
if engine.current_agent:
    DEFAULT_NPC_NAME = engine.current_agent.profile.name
DEFAULT_OPTIONS = get_display_options(engine, DEFAULT_NPC_NAME) if DEFAULT_NPC_NAME else ["A) ...", "B) ...", "C) ..."]


def get_status_markdown(engine: GameEngine) -> str:
    p = engine.player_state
    inv_str = ", ".join(p.inventory) if p.inventory else "無"
    arts_str = ", ".join(p.cultivation_arts) if p.cultivation_arts else "無"

    ch_info = engine.get_current_chapter_info()
    ch_title = ch_info.get("title", "")
    ch_goal = ch_info.get("goal", "")

    factions_str = " | ".join([f"{k}: `{v}`" for k, v in engine.factions.items()]) if engine.factions else "無"

    ending_info = engine.evaluate_ending()
    ending_md = f"\n\n🏆 **[觸發結局]**: **{ending_info['name']}**\n*{ending_info['description']}*" if ending_info else ""
    if engine.all_endings_triggered():
        ending_md += "\n\n🎉 **四人皆已觸發過結局，全破關！**"

    # 當前互動對象/好感度不在這裡重複顯示——NPC 檔案面板 (get_npc_dossier_markdown)
    # 已經是同一個資訊唯一該出現的地方，這裡只留玩家自身數值與世界局勢。
    #
    # 玩家最常瞄一眼的三個數字（金錢/體力/境界）直接放在最前面、永遠可見；其餘細節
    # （HP/魅力/修為經驗/功法/背包/章節主線/勢力聲望/結局橫幅）收進 <details> 摺疊區塊
    # 預設收起。用 <details> 而不是另外拉一個 Gradio 元件，是因為 get_status_markdown()
    # 的回傳值被十幾個呼叫端當同一個 status_box 輸出在用，拆成兩個元件要同步改掉每一處
    # 輸出 tuple 的形狀，風險跟改動範圍都遠大於在同一個 Markdown 字串裡包一層可摺疊 HTML。
    #
    # 境界 (cultivation realm) 目前 PlayerState 還沒有對應欄位（只有 cultivation_level
    # 這個數字等級），先留一個佔位文字，之後真的實裝了直接把這行換成真實資料即可。
    md = f"""### 🗡️ [{p.name}]（第 {engine.game_turn} 回合）
- **金幣**: `{p.gold}` 兩 | **體力**: `{p.stamina}/{p.max_stamina}` | **境界**: `尚未實裝`

<details>
<summary>📜 詳細狀態（點擊展開）</summary>

### 📜 [{ch_title}] (第 {engine.game_turn} 回合)
- **本章氛圍**: `{ch_goal}`
- **動態主線摘要**: `{engine.main_quest_summary}`
- **勢力聲望**: {factions_str}{ending_md}

---
- **生命 (HP)**: `{p.hp}/{p.max_hp}`
- **魅力/吸引力**: `{p.charm}`
- **修為等級**: `Level {p.cultivation_level}` (經驗: `{p.cultivation_exp}`)
- **功法武學**: `{arts_str}`
- **背包**: `{inv_str}`

</details>
"""
    return md


def get_map_markdown(engine: GameEngine) -> str:
    reg = engine.get_current_region()
    exits = engine.get_available_exits()
    unlocked = list(engine.unlocked_locations)

    exits_str = ", ".join([f"`{e}`" for e in exits]) if exits else "無"
    unlocked_str = ", ".join([f"`{u}`" for u in unlocked]) if unlocked else "無"

    md = f"""### 🧭 [棲霜山莊探索看板]
- **當前所在地**: **{engine.current_location}** (危險度: `{reg.get('danger_level', '低')}`)
- **地區環境描寫**: {reg.get('description', '')}
- **鄰近可連通區域**: {exits_str}
- **已解鎖探索地圖點**: {unlocked_str}
"""
    return md


def get_npc_dossier_markdown(engine: GameEngine) -> str:
    """整塊都收在 <details> 裡預設摺疊（理由跟 get_status_markdown 的說明一樣：這個
    函式的回傳值被同一個 dossier_box 元件在十幾個呼叫端共用，用 <details> 而不是拆
    元件才不用同步改掉每一處輸出 tuple）。"""
    if not engine.current_agent:
        return "<details>\n<summary>📜 機密檔案（點擊展開）</summary>\n\n目前無互動對象。\n\n</details>"

    p = engine.current_agent.profile
    tag = engine.current_agent.current_status_tag

    md = f"""<details>
<summary>📜 [{p.name}] 機密檔案（點擊展開）</summary>

- **角色身份**: `{p.identity}` | **所在地點**: `{p.location}`
- **性格特質**: {p.personality}
- **對話狀態**: `[{tag}]` | **好感度**: `{p.intimacy}` (範圍 -50~80)

</details>
"""
    return md


def get_world_news_markdown(engine: GameEngine) -> str:
    events = engine.recent_world_events[-3:] if engine.recent_world_events else ["棲霜山莊夜色沉靜，群芳會尚未真正開始。"]
    events_md = "\n".join([f"- {ev}" for ev in events])
    return f"""### 📰 [江湖動態新聞連線]
{events_md}
"""


def get_saves_markdown() -> str:
    saves = list_account_saves()
    md_lines = ["### 💾 [帳號自動存檔狀態一覽]"]
    if not saves:
        md_lines.append("- 尚無任何帳號存檔")
        return "\n".join(md_lines)
    for s in saves[:5]:
        md_lines.append(f"- **{s['account_name']}**: {s['timestamp']} | `{s['summary']}`")
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


def restore_web_state_after_load(engine: GameEngine, msg_text: str):
    clean_history = []
    if engine.current_agent and engine.current_agent.history:
        for item in engine.current_agent.history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role == "user":
                clean_history.append({"role": "user", "content": [{"type": "text", "text": str(content)}]})
            else:
                clean_history.append({"role": "assistant", "content": [{"type": "text", "text": str(content)}]})

    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    opts = get_display_options(engine, npc_name)
    return (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        msg_text,
        engine.current_location,
        npc_name if npc_name else None,
        get_saves_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2],
    )


def on_save_click(custom_name: str):
    engine = get_engine_for_user(custom_name)
    msg = engine.auto_save(custom_name)
    return msg, get_saves_markdown()


def on_load_click(custom_name: str):
    engine = get_engine_for_user(custom_name)
    success = engine.load_account(custom_name)
    if success:
        msg = f"成功讀取帳號 [{custom_name}] 的存檔！"
    else:
        msg = f"讀取帳號 [{custom_name}] 失敗 (找不到存檔)"
    return restore_web_state_after_load(engine, msg)


def continue_game(custom_name: str):
    clean_name = custom_name.strip() if custom_name else "楚留香"
    engine = get_engine_for_user(clean_name)

    success = has_account_save(clean_name) and engine.load_account(clean_name)

    if success:
        res = restore_web_state_after_load(engine, f"帳號 [{clean_name}] 已成功讀取歷史自動存檔進度！")
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            res[0], res[1], res[2], res[3], res[4], res[5], res[6], res[7], res[8],
            res[9], res[10], res[11], res[12], res[13], res[14]
        )
    else:
        npc_name = engine.current_agent.profile.name if engine.current_agent else ""
        opts = get_display_options(engine, npc_name) if npc_name else DEFAULT_OPTIONS
        return (
            gr.update(visible=True),
            gr.update(visible=False),
            [],
            get_status_markdown(engine),
            get_map_markdown(engine),
            get_npc_dossier_markdown(engine),
            get_world_news_markdown(engine),
            f"未檢測到帳號 [{clean_name}] 的歷史存檔，請開始全新冒險！",
            engine.current_location,
            npc_name if npc_name else None,
            get_saves_markdown(),
            gr.update(value=opts[0]), gr.update(value=opts[1]), gr.update(value=opts[2]),
            opts[0], opts[1], opts[2]
        )


def on_select_npc(custom_name: str, npc_name: str):
    engine = get_engine_for_user(custom_name)
    if npc_name and engine.switch_npc(npc_name):
        msg = f"已切換互動對象至 [{npc_name}]"
    else:
        msg = "切換失敗"
    opts = get_npc_initial_options(engine, npc_name)
    return (
        get_status_markdown(engine),
        get_npc_dossier_markdown(engine),
        msg,
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2],
    )


def on_select_location(custom_name: str, location_name: str, history: list):
    engine = get_engine_for_user(custom_name)
    clean_history = parse_history(history)
    if location_name and engine.move_to_location(location_name):
        # move_to_location 本身不觸發 NPC 自主行動 (見 ARCHITECTURE.md Stage 7)，
        # 這裡是唯一的直接地點移動入口 (不經過 interact)，所以要自己觸發恰好一次
        engine.simulate_npc_autonomous_actions()
        reg = engine.get_current_region()
        msg = f"【轉移陣地】已抵達 [{location_name}]"

        clean_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": f"🧭 **[地圖移動]** 大俠移步至 **{location_name}**！\n\n{reg.get('description', '')}\n危險度: `{reg.get('danger_level', '未知')}` | 駐留對象: `{reg.get('bound_npc', '無')}`"}]
        })

        npc_name = engine.current_agent.profile.name if engine.current_agent else ""
        opts = get_npc_initial_options(engine, npc_name) if npc_name else ["A) ...", "B) ...", "C) ..."]
        engine.auto_save()
        return (
            clean_history,
            get_status_markdown(engine),
            get_map_markdown(engine),
            get_npc_dossier_markdown(engine),
            get_world_news_markdown(engine),
            msg,
            npc_name if npc_name else None,
            gr.update(value=opts[0]),
            gr.update(value=opts[1]),
            gr.update(value=opts[2]),
            opts[0],
            opts[1],
            opts[2],
        )
    return (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        "移動失敗",
        engine.current_agent.profile.name if engine.current_agent else None,
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
    )


def enter_jianghu(custom_name: str):
    clean_name = custom_name.strip() if custom_name else "楚留香"
    engine = get_engine_for_user(clean_name)

    if has_account_save(clean_name):
        engine.load_account(clean_name)
        res = restore_web_state_after_load(engine, f"帳號 [{clean_name}] 已成功連線載入上次進度！")
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            res[0], res[1], res[2], res[3], res[4], res[5], res[6], res[7], res[8],
            res[9], res[10], res[11], res[12], res[13], res[14]
        )

    engine.set_player_name(clean_name)
    intro = engine.world_intro
    opening_text = f"【群芳會序幕】\n{intro.get('opening_narrative', '')}\n\n【江湖局勢】\n{intro.get('background_conflict', '')}\n\n大俠 [{clean_name}] 已抵達棲霜山莊，四大勢力代表齊聚一堂，你準備如何踏出第一步？"

    initial_history = [{
        "role": "assistant",
        "content": [{"type": "text", "text": opening_text}]
    }]

    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    opts = get_npc_initial_options(engine, npc_name) if npc_name else ["A) ...", "B) ...", "C) ..."]
    engine.auto_save()

    return (
        gr.update(visible=False),
        gr.update(visible=True),
        initial_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        f"歡迎大俠 [{clean_name}] 踏入群芳會！",
        engine.current_location,
        npc_name if npc_name else None,
        get_saves_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2],
    )


def process_intimate_choice(engine: GameEngine, npc_name: str, user_input: str, clean_history: list):
    """性愛模式的單一回合：比對玩家點擊的動作標籤（label 字串，見 get_action_label）、
    呼叫 attempt_intimate_action 判定成功/失敗並生成敘事，選到 is_finisher 動作就把
    engine.intimate_mode_npc 清空、退回一般回合制。跟一般回合制共用同一組 UI 元件
    (3 個選項按鈕)，最後一個 yield 的格式必須跟 process_player_choice 完全一致，這樣
    Gradio 端的 wiring 不用另外新增元件。

    是個 generator：{beat:xxx} 插槽要即時呼叫本機 Ollama/RWKV 模型，這一步可能要等
    幾秒鐘，先 yield 一個「她似乎正在回應」的暫時訊息讓畫面立刻有反應，而不是整段
    卡住不動，跟一般回合制 process_player_choice 用 interact_stream 逐字更新畫面是
    同一個「讓玩家知道系統還活著」的用意，只是這裡沒有真的逐字串流、只有頭尾兩個
    yield（beat 生成本身不是串流 API）。"""
    agent = engine.agents.get(npc_name)
    profile = agent.profile
    ending_type = engine.intimate_mode_ending_type or "good"
    disp_name = profile.display_name or profile.name

    templates = load_scene_templates()
    matches = list_intimate_actions(profile, templates, ending_type)
    match_by_label = {get_action_label(name, entry): entry for name, entry in matches}
    entry = match_by_label.get(user_input.strip())

    clean_history.append({"role": "user", "content": [{"type": "text", "text": str(user_input)}]})
    clean_history.append({"role": "assistant", "content": [{"type": "text", "text": f"（{disp_name}似乎正在回應……）"}]})
    yield (
        clean_history,
        gr.update(), gr.update(), gr.update(), gr.update(),
        gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
    )

    if entry is None:
        clean_history[-1]["content"][0]["text"] = f"（{disp_name}似乎沒聽懂你的意思……）"
    else:
        config = load_ending_writer_config()
        if config.backend == "rwkv":
            beat_generator = make_rwkv_beat_generator(config)
        else:
            beat_generator = make_ollama_beat_generator(profile, config)

        result = attempt_intimate_action(profile, entry, engine.player_state.name, beat_generator)

        status_note = "" if result.success else "（她拒絕了……）"
        tag_note = (
            f"\n\n*（{disp_name}似乎漸漸習得了「{result.tag_granted}」……）*"
            if result.tag_granted else ""
        )
        bot_text = f"{status_note}{result.narrative}{tag_note}"

        if result.is_finisher:
            engine.intimate_mode_npc = None
            engine.intimate_mode_ending_type = None
            bot_text += "\n\n---\n🌙 **【性愛模式結束】** 這段親密的糾葛，暫時告一段落。"

        clean_history[-1]["content"][0]["text"] = bot_text

    engine.auto_save()

    if engine.intimate_mode_npc == npc_name:
        opt_a, opt_b, opt_c = get_intimate_menu_options(engine, npc_name)[:3]
    else:
        opt_a, opt_b, opt_c = get_npc_initial_options(engine, npc_name)[:3]

    yield (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        gr.update(value=opt_a),
        gr.update(value=opt_b),
        gr.update(value=opt_c),
        opt_a,
        opt_b,
        opt_c,
    )


def process_player_choice(custom_name: str, user_input: str, history: list, prev_opt_a: str = "", prev_opt_b: str = "", prev_opt_c: str = ""):
    """以串流方式推進劇情：過程持續 yield 逐步填入的敘事文字，只有最後一個 yield 才更新狀態板與選項按鈕"""
    engine = get_engine_for_user(custom_name)
    clean_history = parse_history(history)

    if not user_input or not user_input.strip():
        yield (
            clean_history,
            get_status_markdown(engine),
            get_map_markdown(engine),
            get_npc_dossier_markdown(engine),
            get_world_news_markdown(engine),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )
        return

    npc_name = engine.current_agent.profile.name if engine.current_agent else ""

    if npc_name and engine.intimate_mode_npc == npc_name:
        yield from process_intimate_choice(engine, npc_name, user_input, clean_history)
        return

    # 與 NPC 互動
    used_history = set(engine.current_agent.used_options_history) if engine.current_agent else set()
    prev_opts = {prev_opt_a.strip(), prev_opt_b.strip(), prev_opt_c.strip()}
    disp_name = engine.current_agent.profile.display_name if engine.current_agent else None
    fallback_opts, _fallback_tags = generate_fallback_options(
        npc_name, engine.current_location, engine.game_turn + 1, used_history | prev_opts, disp_name=disp_name
    )

    clean_history.append({"role": "user", "content": [{"type": "text", "text": str(user_input)}]})
    clean_history.append({"role": "assistant", "content": [{"type": "text", "text": ""}]})

    delta = None
    try:
        if not engine.current_agent:
            raise ValueError("目前沒有選擇任何 NPC 進行互動！")
        for partial_narrative, streamed_delta in engine.interact_stream(user_input):
            clean_history[-1]["content"][0]["text"] = partial_narrative
            if streamed_delta is not None:
                delta = streamed_delta
                break
            yield (
                clean_history,
                gr.update(), gr.update(), gr.update(), gr.update(),
                gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            )
    except Exception as e:
        if engine.current_agent:
            delta = generate_fallback_delta(
                npc_name=npc_name,
                player_state=engine.player_state,
                location=engine.current_location,
                turn=engine.game_turn,
                exclude_opts=used_history | prev_opts,
                disp_name=disp_name,
                identity=engine.current_agent.profile.identity,
            )
        else:
            delta = GameStateDelta(
                narrative=f"[{npc_name}] 默默地思索著眼前的情勢...",
                player_hp_change=0,
                player_gold_change=0,
                inventory_added=[],
                inventory_removed=[],
                npc_status_tag="凝視",
                world_flag_set={},
                options=fallback_opts,
                option_tags=_fallback_tags,
            )
        engine.apply_delta(delta)

    if delta is None:
        # 理論上不會發生：interact_stream 保證最後一定會 yield 出非 None 的 delta，
        # 這裡是防禦性保底，避免真的發生時整個 handler 直接崩潰
        delta = GameStateDelta(
            narrative=f"[{npc_name}] 陷入了短暫的沉默...",
            npc_status_tag="沉默",
            options=fallback_opts,
            option_tags=_fallback_tags,
        )
        engine.apply_delta(delta)

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
        changes.append(f"好感度 {sign}{delta.intimacy_change}")
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
    clean_history[-1]["content"][0]["text"] = bot_msg

    # 這一回合的好感度變化有沒有剛好跨過終極/黑化門檻，馬上切進性愛模式——不用等玩家
    # 之後重新切換 NPC 或移動地點才會被 get_npc_initial_options 那條路徑偵測到。
    # apply_delta 在 interact_stream/exception fallback 兩條路徑都已經跑過，這裡讀到的
    # profile.intimacy 一定是這回合結束後的最終值。
    intimate_trigger = engine.check_and_enter_intimate_mode()
    if intimate_trigger and engine.intimate_mode_npc == npc_name:
        clean_history[-1]["content"][0]["text"] += (
            f"\n\n---\n🏆 **【觸發結局】{intimate_trigger['name']}**\n*{intimate_trigger['description']}*"
            "\n\n💋 進入性愛模式，請從下方動作選單選擇下一步。"
        )
        opt_a, opt_b, opt_c = get_intimate_menu_options(engine, npc_name)[:3]
        engine.auto_save()
        yield (
            clean_history,
            get_status_markdown(engine),
            get_map_markdown(engine),
            get_npc_dossier_markdown(engine),
            get_world_news_markdown(engine),
            gr.update(value=opt_a),
            gr.update(value=opt_b),
            gr.update(value=opt_c),
            opt_a,
            opt_b,
            opt_c,
        )
        return

    # 檢查歷史使用過的選項與上一輪選項，進行嚴格去重與動態補齊
    used_history = set(engine.current_agent.used_options_history) if engine.current_agent else set()
    exclude_opts = used_history | prev_opts

    # 只要 LLM 有回傳任何選項就沿用（就算不到 3 個）：下面逐格迴圈本來就會對缺的格位
    # 個別補生成，用完整 fallback_opts 整批取代會把模型辛苦生出的其餘幾個貼合劇情的
    # 選項也一起丟掉，換成完全通用、跟當下劇情無關的罐頭選項，是玩家覺得「選項不連貫」的主因之一。
    raw_opts = delta.options if delta.options else fallback_opts
    raw_tags = delta.option_tags if delta.option_tags else _fallback_tags

    final_opts = []
    for idx in range(3):
        raw_opt = raw_opts[idx].strip() if idx < len(raw_opts) else ""
        is_dup = (
            not raw_opt or
            raw_opt in exclude_opts or
            is_placeholder_option(raw_opt)
        )
        if not is_dup:
            final_opts.append(raw_opt)
            exclude_opts.add(raw_opt)
        else:
            new_opt, new_tag = generate_single_fallback_option(
                idx, npc_name, engine.current_location, engine.game_turn, exclude_opts, disp_name=disp_name
            )
            final_opts.append(new_opt)
            exclude_opts.add(new_opt)
            if idx < len(raw_tags):
                raw_tags[idx] = new_tag

    if engine.current_agent:
        for opt in final_opts:
            engine.current_agent.used_options_history.add(opt)
        # 若選項因去重被替換，agent 記錄的 last_offered_options 要跟著更新，
        # 否則下一輪玩家點擊按鈕時比對的會是被替換前的舊文字，查不到分類
        engine.current_agent.last_offered_options = list(final_opts)
        engine.current_agent.last_offered_tags = list(raw_tags[:3]) if len(raw_tags) >= 3 else list(_fallback_tags)

    opt_a, opt_b, opt_c = final_opts

    engine.auto_save()

    yield (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        gr.update(value=opt_a),
        gr.update(value=opt_b),
        gr.update(value=opt_c),
        opt_a,
        opt_b,
        opt_c,
    )


def list_ending_files() -> list:
    """列出 saves/endings/ 底下已生成的結局劇情檔案；查無目錄時回傳空清單。"""
    if not os.path.isdir(DEFAULT_OUTPUT_DIR):
        return []
    return sorted(f for f in os.listdir(DEFAULT_OUTPUT_DIR) if f.endswith(".txt"))


def load_ending_content(filename: str) -> str:
    """讀取指定結局檔案內容顯示給玩家——由 Gradio 自己的伺服器端讀檔直接渲染到瀏覽器，
    內容全程只在使用者自己的裝置與自己的伺服器之間傳輸。"""
    if not filename:
        return "請先從上方選擇一份結局檔案。"
    path = os.path.join(DEFAULT_OUTPUT_DIR, filename)
    if not os.path.isfile(path):
        return f"找不到檔案：{filename}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def refresh_ending_list():
    files = list_ending_files()
    return gr.update(choices=files, value=files[0] if files else None)


def reset_chat(custom_name: str):
    engine = get_engine_for_user(custom_name)
    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    if engine.current_agent:
        engine.current_agent.reset_history()
    opts = get_npc_initial_options(engine, npc_name) if npc_name else ["A) ...", "B) ...", "C) ..."]
    engine.auto_save()
    return (
        [],
        "對話歷史已重置",
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        opts[0],
        opts[1],
        opts[2],
    )


# 建立 Gradio Web UI 介面
with gr.Blocks(title="Local Blade RPG Engine") as demo:
    gr.Markdown("# 🗡️ Local Blade RPG Engine - 群芳會・棲霜山莊")
    gr.Markdown("使用 Ollama 本地端 LLM 驅動的暗黑武俠情慾/征服路線文字 RPG 遊戲引擎")
    gr.Markdown("📱 **[手機與跨裝置連線網址]**: 請確保手機與電腦連接同一個 Wi-Fi 網路，於手機瀏覽器輸入 `http://192.168.1.123:7860` 即可跨裝置遊玩！")

    state_opt_a = gr.State(DEFAULT_OPTIONS[0])
    state_opt_b = gr.State(DEFAULT_OPTIONS[1])
    state_opt_c = gr.State(DEFAULT_OPTIONS[2])

    # 1. 序幕的故事、自由取名與背景衝突展示區
    with gr.Column(visible=True) as prologue_group:
        intro_data = engine.world_intro
        gr.Markdown(f"## 📜 {intro_data.get('title', '群芳會')}")

        player_name_input = gr.Textbox(
            label="👤 帳號 / 大俠姓名 (登入與自動紀錄)",
            value="楚留香",
            placeholder="請輸入帳號 / 大俠姓名...",
            interactive=True
        )
        gr.Markdown("💡 *提示：輸入您先前使用的帳號名稱並點擊 [踏入江湖/登入進度]，即可自動恢復所有歷史對話與遊戲進度！*")

        gr.Markdown(f"**【序幕故事】**\n\n{intro_data.get('opening_narrative', '')}")
        gr.Markdown(f"**【江湖衝突局勢】**\n\n{intro_data.get('background_conflict', '')}")
        gr.Markdown(f"**【初始主線任務】**\n\n`{engine.main_quest_summary}`")

        with gr.Row():
            btn_enter_game = gr.Button("🗡️ [踏入江湖 / 登入進度] 開始/繼續冒險", variant="primary", size="lg")
            btn_continue_game = gr.Button("📂 [載入最新全域存檔]", variant="secondary", size="lg")

    # 2. 正式遊戲主介面
    with gr.Column(visible=False) as main_game_group:
        with gr.Row():
            with gr.Column(scale=1):
                # 狀態板/NPC 檔案是每回合都要看的核心資訊，維持一直展開。地圖/新聞、
                # 存檔控制、結局檢視器都是「偶爾才需要點開看一眼」的次要資訊，收進
                # Accordion 預設折疊，避免左欄一開場就是一長串文字牆（尤其手機上）。
                status_box = gr.Markdown(value=lambda: get_status_markdown(engine))
                dossier_box = gr.Markdown(value=lambda: get_npc_dossier_markdown(engine))

                location_dropdown = gr.Dropdown(
                    choices=list(engine.world_map.get("regions", {}).keys()),
                    value=engine.current_location,
                    label="🧭 移動前往周邊地點 (點擊切換區域)",
                    interactive=True
                )

                npc_dropdown = gr.Dropdown(
                    choices=list(engine.agents.keys()),
                    value=engine.current_agent.profile.name if engine.current_agent else None,
                    label="選擇互動對象",
                    interactive=True
                )

                with gr.Accordion("🗺️ 地圖與江湖動態", open=False):
                    map_box = gr.Markdown(value=lambda: get_map_markdown(engine))
                    news_box = gr.Markdown(value=lambda: get_world_news_markdown(engine))

                with gr.Accordion("💾 存檔與系統控制", open=False):
                    gr.Markdown("### 💾 [帳號存檔與載入控制]")
                    with gr.Row():
                        btn_save_account = gr.Button("💾 立即存檔", variant="primary", scale=1)
                        btn_load_account = gr.Button("📂 重新載入我的存檔", variant="secondary", scale=1)

                    save_list_box = gr.Markdown(value=get_saves_markdown)
                    system_msg = gr.Textbox(label="系統訊息", value="準備就緒", interactive=False)
                    reset_btn = gr.Button("重置與當前對象對話", variant="secondary")

                with gr.Accordion("🔞 結局劇情檢視器", open=False):
                    gr.Markdown("由伺服器端直接讀取 `saves/endings/` 底下已生成的結局檔案顯示，內容不經過任何第三方。")
                    ending_file_dropdown = gr.Dropdown(
                        choices=list_ending_files(),
                        label="選擇已生成的結局檔案",
                        interactive=True
                    )
                    with gr.Row():
                        btn_refresh_endings = gr.Button("🔄 重新整理清單", variant="secondary")
                        btn_show_ending = gr.Button("📖 顯示內容", variant="primary")
                    ending_content_box = gr.Textbox(
                        value="請先選擇一份結局檔案，再按「顯示內容」。",
                        label="結局內文",
                        lines=15,
                        interactive=False
                    )

            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="遊戲對話紀錄", height=450)

                gr.Markdown("### 🎯 劇情動態選項 (請選擇要發動的行動)")
                with gr.Column():
                    btn_opt_a = gr.Button(DEFAULT_OPTIONS[0], variant="primary")
                    btn_opt_b = gr.Button(DEFAULT_OPTIONS[1], variant="secondary")
                    btn_opt_c = gr.Button(DEFAULT_OPTIONS[2], variant="stop")

    # 踏入江湖點擊事件
    btn_enter_game.click(
        fn=enter_jianghu,
        inputs=[player_name_input],
        outputs=[
            prologue_group, main_game_group, chatbot, status_box, map_box, dossier_box, news_box,
            system_msg, location_dropdown, npc_dropdown, save_list_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 繼續遊戲點擊事件
    btn_continue_game.click(
        fn=continue_game,
        inputs=[player_name_input],
        outputs=[
            prologue_group, main_game_group, chatbot, status_box, map_box, dossier_box, news_box,
            system_msg, location_dropdown, npc_dropdown, save_list_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 存檔與讀檔事件
    btn_save_account.click(
        fn=on_save_click,
        inputs=[player_name_input],
        outputs=[system_msg, save_list_box]
    )

    btn_load_account.click(
        fn=on_load_click,
        inputs=[player_name_input],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box, system_msg, location_dropdown,
            npc_dropdown, save_list_box, btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 地圖移動事件
    location_dropdown.change(
        fn=on_select_location,
        inputs=[player_name_input, location_dropdown, chatbot],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box, system_msg, npc_dropdown,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 事件繫結
    npc_dropdown.change(
        fn=on_select_npc,
        inputs=[player_name_input, npc_dropdown],
        outputs=[
            status_box, dossier_box, system_msg,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 點擊選項 A / B / C 直接推進劇情
    btn_opt_a.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_a, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    btn_opt_b.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_b, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    btn_opt_c.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_c, chatbot, state_opt_a, state_opt_b, state_opt_c],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    reset_btn.click(
        fn=reset_chat,
        inputs=[player_name_input],
        outputs=[
            chatbot, system_msg, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c,
            state_opt_a, state_opt_b, state_opt_c
        ]
    )

    # 結局劇情檢視器事件：change/select 兩種事件都綁，外加一個明確的「顯示內容」按鈕
    # 當保底，避免手機瀏覽器上 Dropdown 的 change 事件沒有確實觸發時完全沒有反應
    btn_refresh_endings.click(fn=refresh_ending_list, outputs=[ending_file_dropdown])
    btn_show_ending.click(fn=load_ending_content, inputs=[ending_file_dropdown], outputs=[ending_content_box])
    ending_file_dropdown.change(fn=load_ending_content, inputs=[ending_file_dropdown], outputs=[ending_content_box])
    ending_file_dropdown.select(fn=load_ending_content, inputs=[ending_file_dropdown], outputs=[ending_content_box])


if __name__ == "__main__":
    print("正在啟動 Local Blade RPG Web UI (0.0.0.0:7860，已開啟公共分享網址 share=True)...")
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True, share=True)
