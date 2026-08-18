import sys
import os
import json
from typing import Set, Optional

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
from src.save_manager import list_account_saves, has_account_save, load_account_game, save_account_game

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


engine = get_engine_for_user("楚留香")


def generate_single_option(
    idx: int,
    npc_name: str,
    location_name: str,
    intimacy: int,
    turn: int,
    exclude_opts: Optional[Set[str]] = None
) -> str:
    exclude = exclude_opts or set()

    pools = {
        "合歡宗聖女": [
            [  # A) 正派/常規
                "A) 抱拳拱手向聖女柳如煙詢問懷中血秘卷與解毒線索",
                "A) 眼神深情凝視聖女柳如煙，詢問合歡宗雙修心法的絕密要訣",
                "A) 向柳如煙打聽少林與武當鎮派武學的江湖陰謀",
                "A) 與柳如煙密謀龍門之巔最終反殺正派盟主與朝廷禁衛計畫",
                f"A) 向柳如煙打聽當前地點 [{location_name}] 的暗道與周邊形勢"
            ],
            [  # B) 謀略/智取談判
                "B) 分析四大勢力利害關係向柳如煙提出籌碼交換",
                "B) 抓出柳如煙言語中的試探破綻，開出黑市情報做交易",
                "B) 提議與柳如煙聯手抗衡正派武林盟與朝廷追兵",
                "B) 以血秘卷第一層密碼為條件籌劃雙方共同退路",
                f"B) 冷靜剖析[{location_name}]局勢，向柳如煙開出合作盟約"
            ],
            [  # C) 情慾/色誘/親密
                "C) 湊近柳如煙身旁，眼神挑逗並嘗試進行身體接觸試探",
                "C) 溫柔地將柳如煙攬入懷中，在耳畔低語運轉雙修靈氣試探心意",
                "C) 順勢牽起柳如煙冰涼柔嫩的纖手，運轉雙修心法導入靈氣驅解詛咒",
                "C) 與柳如煙緊緊相擁，深度運轉太上陰陽心法突破修為至頂峰大成",
                f"C) 凝視柳如煙美眸，輕撫其腰肢運轉太上陰陽心法合練"
            ],
            [  # D) 混亂邪惡/背叛/暗黑
                "D) 眼神一冷搜刮柳如煙隨身攜帶的合歡宗毒藥令牌",
                "D) 亮出冷刃逼問柳如煙是否有意背叛正派武林盟",
                "D) 邀請柳如煙一同解開血秘卷上的雙修陣法封印",
                "D) 亮出毒刃威脅周邊埋伏的正派刺客保護柳如煙",
                f"D) 眼神冷冽拔出暗器戒備，逼問柳如煙隨身密卷真相"
            ],
            [  # E) 地圖探索/轉移
                "E) 移動前往亂葬崗搜尋古老功法殘頁",
                "E) 轉移陣地前往少林寺下鎮避開風頭",
                "E) 移動前往血衣樓分舵探索情報",
                f"E) 轉移陣地前往 [{location_name}] 核心密室籌劃大局",
                f"E) 在當前區域 [{location_name}] 仔細搜尋蛛絲馬跡與秘密通道"
            ]
        ],
        "風騷老闆娘": [
            [  # A
                "A) 點一壺上等竹葉青向老闆娘賽金花打聽龍門關最新消息",
                "A) 詢問老闆娘賽金花龍門客棧密道與各方勢力的核心情報",
                "A) 要求賽金花引薦黑市兵器商購買上等寶劍",
                "A) 與賽金花密謀掌控龍門關黑市情報網發起反擊",
                f"A) 探聽關於 [{location_name}] 黑市傳聞與血秘卷第一層真相"
            ],
            [  # B
                "B) 以龍門客棧密道情報與賽金花進行籌碼劃分",
                "B) 分析血衣樓黑榜賞金，提議與賽金花二八分帳",
                "B) 拿出黑市情報做交換，說服賽金花提供庇護",
                "B) 洞察賽金花的商賈企圖，提出合開情報網的謀略",
                f"B) 冷靜與賽金花交涉關於[{location_name}]的黑市收益分成"
            ],
            [  # C
                "C) 湊近賽金花耳畔輕吟調情話語並撫摸其手背",
                "C) 伸手環住賽金花豐滿的細腰，低聲討要天字房鑰匙",
                "C) 隨賽金花進入天字房秘室，共飲合歡美酒傾聽其紅塵身世心聲",
                "C) 攬住賽金花嬌軀在紅燭下雙宿雙飛共定生死誓言",
                f"C) 溫柔握住賽金花手心，在紅燭下雙修合練運轉靈氣"
            ],
            [  # D
                "D) 亮出血滴子逼問賽金花關於血衣樓黑榜的幕後主使",
                "D) 冷聲逼問賽金花龍門客棧地下庫房位置",
                "D) 掏出暗器威脅客棧酒保搜刮當日營業銀票",
                "D) 拔劍除掉暗中監視客棧的正派武林盟眼線",
                f"D) 眼神一冷亮出武器搜刮周邊密卷與隨身銀票"
            ],
            [  # E
                "E) 移動前往龍門錢莊查詢存款行情",
                "E) 移動前往黑風寨山腳避開風頭",
                "E) 移動前往少林寺下鎮避開朝廷搜捕",
                f"E) 移動前往區域 [{location_name}] 核心避難暗道",
                f"E) 在當前區域 [{location_name}] 仔細搜尋隱蔽出口"
            ]
        ],
        "殺手阿福": [
            [  # A
                "A) 亮出武器防備阿福突襲，詢問血衣樓的接單規則",
                "A) 詢問阿福血衣樓黑榜殺手最新的懸賞名單",
                "A) 重金雇傭阿福作為個人私人金牌護衛",
                "A) 詢問阿福關於血衣樓樓主與朝廷禁衛的秘密交易",
                f"A) 向阿福打聽 [{location_name}] 周邊殺手伏擊點"
            ],
            [  # B
                "B) 以黑市定金與情報做籌碼說服阿福暫緩刺殺",
                "B) 指出血衣樓懸賞令的條款漏洞，開出翻倍重金",
                "B) 提議協助阿福反殺血衣樓執法隊，劃分戰利品",
                "B) 分析朝廷禁衛軍的動向，向阿福提供逃生避難路線",
                f"B) 與阿福進行江湖籌碼談判，開出讓其無法拒絕的代價"
            ],
            [  # C
                "C) 湊近阿福耳邊輕語利益交換誘惑條款",
                "C) 掏出合歡宗雙修秘笈試圖與阿福私下交易",
                "C) 向阿福展露魅力邀請其退出血衣樓共闖江湖",
                "C) 湊近阿福身旁掏出美酒與雙修秘笈進行深層拉扯",
                f"C) 展示高超魅力與阿福分享秘寶並輕撫其手背"
            ],
            [  # D
                "D) 拔出利刃冷不防割向阿福右手動脈進行強襲",
                "D) 將劇毒匕首架在阿福脖子上逼他透露分舵地圖",
                "D) 聯手阿福發動伏擊殺死血衣樓前來督戰的執法長老",
                "D) 亮出冷刃逼問阿福血衣樓最新黑榜刺殺目標",
                f"D) 眼神一冷亮出匕首逼問阿福分舵地圖與藏寶"
            ],
            [  # E
                "E) 移動前往亂葬崗搜尋避難點",
                "E) 移動前往黑風寨山腳察看埋伏陷阱",
                f"E) 移動前往地點 [{location_name}] 探索暗道",
                f"E) 在當前區域 [{location_name}] 搜尋埋伏陷阱與出路",
                f"E) 移動前往周邊安全地點避開血衣樓追殺"
            ]
        ],
        "錢莊老王": [
            [  # A
                "A) 詢問老王錢莊當前存款與黑市金庫行情",
                "A) 詢問老王少林與武當鎮派武學的抵押拍賣行情",
                "A) 與老王商討收購少林武當地產股權計劃",
                "A) 向老王探聽四大勢力最新資金流向與黃金庫存",
                f"A) 詢問老王關於地點 [{location_name}] 的土地抵押行情"
            ],
            [  # B
                "B) 拿出黑市黃金密藏庫存地圖向老王進行高額借貸談判",
                "B) 以四大勢力的地下債務清單為籌碼逼老王劃轉銀票",
                "B) 提議與老王聯手做空正派武林盟與朝廷軍費資金鏈",
                "B) 剖析江湖局勢向老王提出龍門錢莊資本擴張合約",
                f"B) 出示黑市籌碼說服老王開具無限額度信用憑證"
            ],
            [  # C
                "C) 湊近老王耳邊低語財色交易條款",
                "C) 捏住老王手腕將劇毒滲入其脈搏脅迫劃轉銀票",
                "C) 展示高超魅力說服老王為自己開立無限額度金卡",
                "C) 上前對老王展露美色與魅力試圖減免貸款利息",
                f"C) 展露高超魅力試圖說服老王開立免息貸款合同"
            ],
            [  # D
                "D) 亮出沾血匕首逼老王交出總庫房鑰匙",
                "D) 強行搶走錢莊櫃檯上的最新銀票票據",
                "D) 威脅老王將朝廷懸賞金暗中劃入自己帳戶",
                "D) 亮出利刃逼問老王關於血衣樓與錢莊的密約",
                f"D) 眼神一冷掏出匕首逼問老王核心庫房與地圖"
            ],
            [  # E
                "E) 在錢莊櫃檯周邊仔細搜尋帳簿與地圖",
                "E) 移動前往少林寺下鎮聽取梵音淨化心神",
                f"E) 移動前往區域 [{location_name}] 尋找投資標的",
                f"E) 在當前區域 [{location_name}] 搜尋密藏銀票",
                f"E) 移動前往龍門客棧尋求保護與情報交易"
            ]
        ]
    }

    npc_pools = pools.get(npc_name)
    if not npc_pools:
        default_candidates = [
            [f"A) 抱拳向{npc_name}詢問當前地區 [{location_name}] 的傳聞", f"A) 探聽關於{npc_name}的出身來歷與背後勢力", f"A) 誠懇向{npc_name}討教當前局勢與解毒線索"],
            [f"B) 冷靜分析四大勢力利害關係與{npc_name}進行談判", f"B) 拿出黑市情報籌碼提議與{npc_name}利益均沾", f"B) 運用江湖談判與利益交換試圖說服{npc_name}"],
            [f"C) 湊近{npc_name}耳邊輕語並進行身體接觸試探", f"C) 牽起{npc_name}的手指展露魅力拉近情感距離", f"C) 上前擁住{npc_name}運轉靈氣進行雙修親密試探"],
            [f"D) 眼神一冷搜刮{npc_name}隨身帶有的密卷與銀票", f"D) 亮出利刃冷聲威脅{npc_name}透露秘密", f"D) 出其不意亮出暗器強襲{npc_name}索要情報"],
            [f"E) 在當前區域 [{location_name}] 仔細搜尋蛛絲馬跡", f"E) 移動前往周邊安全區域避開風頭", f"E) 移動前往鄰近地點尋找避難所"]
        ]
        category_candidates = default_candidates[idx % 5]
    else:
        category_candidates = npc_pools[idx % 5]

    for cand in category_candidates:
        cand_clean = cand.strip()
        if cand_clean not in exclude:
            return cand_clean

    prefixes = ["A", "B", "C", "D", "E"]
    prefix = prefixes[idx % 5]
    descriptions = [
        f"向{npc_name}打聽關於[{location_name}]的最新情報",
        f"與{npc_name}進行冷靜利害分析與利益交涉",
        f"上前對{npc_name}展露美色與魅力進行深層拉扯",
        f"亮出冷刃戒備並強行搜刮{npc_name}身上的秘卷",
        f"在[{location_name}]區域搜尋周邊秘密出口"
    ]
    desc = descriptions[idx % 5]
    dynamic_opt = f"{prefix}) {desc} (第{turn}回合)"
    if dynamic_opt in exclude:
        dynamic_opt = f"{prefix}) {desc} (第{turn}回合-{len(exclude)+1})"
    return dynamic_opt


def generate_dynamic_options(
    npc_name: str,
    location_name: str,
    intimacy: int,
    turn: int,
    exclude_opts: Optional[Set[str]] = None
) -> list:
    exclude = set(exclude_opts) if exclude_opts else set()
    result = []
    for idx in range(5):
        opt = generate_single_option(idx, npc_name, location_name, intimacy, turn, exclude)
        result.append(opt)
        exclude.add(opt)
    return result


def get_npc_initial_options(engine: GameEngine, npc_name: str) -> list:
    loc = engine.current_location
    agent = engine.agents.get(npc_name)
    intimacy = agent.profile.intimacy if agent else 0
    used_history = set(agent.used_options_history) if agent else set()
    return generate_dynamic_options(npc_name, loc, intimacy, engine.game_turn, used_history)


DEFAULT_OPTIONS = generate_dynamic_options("風騷老闆娘", "龍門客棧", 0, 1)


def get_status_markdown(engine: GameEngine) -> str:
    p = engine.player_state
    inv_str = ", ".join(p.inventory) if p.inventory else "無"
    arts_str = ", ".join(p.cultivation_arts) if p.cultivation_arts else "無"

    ch_info = engine.get_current_chapter_info()
    ch_title = ch_info.get("title", "第一章：血夜甦醒與龍門破局")
    ch_goal = ch_info.get("goal", "尋求療傷與避難，查明懷中血秘卷真相")

    current_npc_info = "無"
    intimacy_info = "0/100"
    if engine.current_agent:
        profile = engine.current_agent.profile
        tag = engine.current_agent.current_status_tag
        current_npc_info = f"**{profile.name}** ({profile.identity}) | 位置: {profile.location} | 狀態: `[{tag}]`"
        intimacy_info = f"`{profile.intimacy}/100`"

    factions_str = " | ".join([f"{k}: `{v}`" for k, v in engine.factions.items()]) if engine.factions else "無"

    ending_info = engine.evaluate_ending()
    ending_md = f"\n\n🏆 **[觸發終局結局]**: **{ending_info['name']}**\n*{ending_info['description']}*" if ending_info else ""

    md = f"""### 📜 [{ch_title}] (第 {engine.game_turn} 回合)
- **本章目標**: `{ch_goal}`
- **動態主線摘要**: `{engine.main_quest_summary}`
- **勢力聲望**: {factions_str}{ending_md}

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


def get_map_markdown(engine: GameEngine) -> str:
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


def get_npc_dossier_markdown(engine: GameEngine) -> str:
    if not engine.current_agent:
        return "### 📜 [NPC 機密檔案]\n目前無互動對象。"

    p = engine.current_agent.profile
    tag = engine.current_agent.current_status_tag

    md = f"""### 📜 [{p.name} 機密檔案]
- **角色身份**: `{p.identity}` | **所在地點**: `{p.location}`
- **性格特質**: {p.personality}
- **對話狀態**: `[{tag}]` | **親密度**: `{p.intimacy}/100`
"""
    return md


def get_world_news_markdown(engine: GameEngine) -> str:
    events = engine.recent_world_events[-3:] if engine.recent_world_events else ["龍門關外夜雨傾盆，風平浪靜。"]
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

    opts = get_npc_initial_options(engine, engine.current_agent.profile.name if engine.current_agent else "")
    return (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        msg_text,
        engine.current_location,
        engine.current_agent.profile.name if engine.current_agent else None,
        get_saves_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        gr.update(value=opts[3]),
        gr.update(value=opts[4]),
        opts[0],
        opts[1],
        opts[2],
        opts[3],
        opts[4]
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
            res[9], res[10], res[11], res[12], res[13],
            res[14], res[15], res[16], res[17], res[18]
        )
    else:
        opts = DEFAULT_OPTIONS
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
            engine.current_agent.profile.name if engine.current_agent else None,
            get_saves_markdown(),
            gr.update(value=opts[0]), gr.update(value=opts[1]), gr.update(value=opts[2]), gr.update(value=opts[3]), gr.update(value=opts[4]),
            opts[0], opts[1], opts[2], opts[3], opts[4]
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
        gr.update(value=opts[3]),
        gr.update(value=opts[4]),
        opts[0],
        opts[1],
        opts[2],
        opts[3],
        opts[4]
    )


def on_select_location(custom_name: str, location_name: str, history: list):
    engine = get_engine_for_user(custom_name)
    clean_history = parse_history(history)
    if location_name and engine.move_to_location(location_name):
        reg = engine.get_current_region()
        msg = f"【轉移陣地】已抵達 [{location_name}]"

        clean_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": f"🧭 **[地圖移動]** 大俠移步至 **{location_name}**！\n\n{reg.get('description', '')}\n危險度: `{reg.get('danger_level', '未知')}` | 駐留 NPC: `{reg.get('bound_npc', '無')}`"}]
        })

        opts = get_npc_initial_options(engine, engine.current_agent.profile.name if engine.current_agent else "")
        engine.auto_save()
        return (
            clean_history,
            get_status_markdown(engine),
            get_map_markdown(engine),
            get_npc_dossier_markdown(engine),
            get_world_news_markdown(engine),
            msg,
            engine.current_agent.profile.name if engine.current_agent else None,
            gr.update(value=opts[0]),
            gr.update(value=opts[1]),
            gr.update(value=opts[2]),
            gr.update(value=opts[3]),
            gr.update(value=opts[4]),
            opts[0],
            opts[1],
            opts[2],
            opts[3],
            opts[4]
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
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update()
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
            res[9], res[10], res[11], res[12], res[13],
            res[14], res[15], res[16], res[17], res[18]
        )

    engine.set_player_name(clean_name)
    intro = engine.world_intro
    opening_text = f"【血夜序幕故事】\n{intro.get('opening_narrative', '')}\n\n【大背景局勢衝突】\n{intro.get('background_conflict', '')}\n\n大俠 [{clean_name}] 身處龍門客棧風暴中心，眼前四大勢力盤根錯節，你準備如何踏出江湖第一步？"

    initial_history = [{
        "role": "assistant",
        "content": [{"type": "text", "text": opening_text}]
    }]

    opts = get_npc_initial_options(engine, engine.current_agent.profile.name if engine.current_agent else "")
    engine.auto_save()

    return (
        gr.update(visible=False),
        gr.update(visible=True),
        initial_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        f"歡迎大俠 [{clean_name}] 踏入江湖！",
        engine.current_location,
        engine.current_agent.profile.name if engine.current_agent else None,
        get_saves_markdown(),
        gr.update(value=opts[0]),
        gr.update(value=opts[1]),
        gr.update(value=opts[2]),
        gr.update(value=opts[3]),
        gr.update(value=opts[4]),
        opts[0],
        opts[1],
        opts[2],
        opts[3],
        opts[4]
    )


def process_player_choice(custom_name: str, user_input: str, history: list, prev_opt_a: str = "", prev_opt_b: str = "", prev_opt_c: str = "", prev_opt_d: str = "", prev_opt_e: str = ""):
    engine = get_engine_for_user(custom_name)
    clean_history = parse_history(history)

    if not user_input or not user_input.strip():
        return (
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
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update()
        )

    # 與 NPC 互動
    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    intimacy = engine.current_agent.profile.intimacy if engine.current_agent else 0
    used_history = set(engine.current_agent.used_options_history) if engine.current_agent else set()
    prev_opts = {
        prev_opt_a.strip(), prev_opt_b.strip(), prev_opt_c.strip(),
        prev_opt_d.strip(), prev_opt_e.strip()
    }
    fallback_opts = generate_dynamic_options(
        npc_name, engine.current_location, intimacy, engine.game_turn + 1, used_history | prev_opts
    )

    try:
        delta = engine.interact(user_input)
    except Exception as e:
        if engine.current_agent:
            delta = engine.current_agent._generate_fallback_delta(
                player_action=user_input,
                player_state=engine.player_state,
                current_location=engine.current_location,
                err_msg=str(e)
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
                options=fallback_opts
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

    # 檢查歷史使用過的選項與上一輪選項，進行嚴格去重與動態補齊
    used_history = set(engine.current_agent.used_options_history) if engine.current_agent else set()
    exclude_opts = used_history | prev_opts

    raw_opts = delta.options if (delta.options and len(delta.options) >= 5) else fallback_opts

    final_opts = []
    for idx in range(5):
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
            new_opt = generate_single_option(
                idx, npc_name, engine.current_location, intimacy, engine.game_turn, exclude_opts
            )
            final_opts.append(new_opt)
            exclude_opts.add(new_opt)

    if engine.current_agent:
        for opt in final_opts:
            engine.current_agent.used_options_history.add(opt)

    opt_a, opt_b, opt_c, opt_d, opt_e = final_opts

    engine.auto_save()

    return (
        clean_history,
        get_status_markdown(engine),
        get_map_markdown(engine),
        get_npc_dossier_markdown(engine),
        get_world_news_markdown(engine),
        gr.update(value=opt_a),
        gr.update(value=opt_b),
        gr.update(value=opt_c),
        gr.update(value=opt_d),
        gr.update(value=opt_e),
        opt_a,
        opt_b,
        opt_c,
        opt_d,
        opt_e
    )


def reset_chat(custom_name: str):
    engine = get_engine_for_user(custom_name)
    npc_name = engine.current_agent.profile.name if engine.current_agent else ""
    opts = get_npc_initial_options(engine, npc_name)
    if engine.current_agent:
        engine.current_agent.reset_history()
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
        gr.update(value=opts[3]),
        gr.update(value=opts[4]),
        opts[0],
        opts[1],
        opts[2],
        opts[3],
        opts[4]
    )


# 建立 Gradio Web UI 介面
with gr.Blocks(title="Local Blade RPG Engine") as demo:
    gr.Markdown("# 🗡️ Local Blade RPG Engine - 暗黑武俠動態沙盒")
    gr.Markdown("使用 Ollama 本地端 LLM 驅動的高自由度文字 RPG 遊戲引擎 (v1.0.0)")
    gr.Markdown("📱 **[手機與跨裝置連線網址]**: 請確保手機與電腦連接同一個 Wi-Fi 網路，於手機瀏覽器輸入 `http://192.168.1.123:7860` 即可跨裝置遊玩！")

    state_opt_a = gr.State(DEFAULT_OPTIONS[0])
    state_opt_b = gr.State(DEFAULT_OPTIONS[1])
    state_opt_c = gr.State(DEFAULT_OPTIONS[2])
    state_opt_d = gr.State(DEFAULT_OPTIONS[3])
    state_opt_e = gr.State(DEFAULT_OPTIONS[4])

    # 1. 序幕的故事、自由取名與背景衝突展示區
    with gr.Column(visible=True) as prologue_group:
        intro_data = engine.world_intro
        gr.Markdown(f"## 📜 {intro_data.get('title', '血夜龍門')}")

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
                status_box = gr.Markdown(value=lambda: get_status_markdown(engine))
                map_box = gr.Markdown(value=lambda: get_map_markdown(engine))
                dossier_box = gr.Markdown(value=lambda: get_npc_dossier_markdown(engine))
                news_box = gr.Markdown(value=lambda: get_world_news_markdown(engine))

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

                gr.Markdown("### 💾 [帳號存檔與載入控制]")
                with gr.Row():
                    btn_save_account = gr.Button("💾 立即存檔", variant="primary", scale=1)
                    btn_load_account = gr.Button("📂 重新載入我的存檔", variant="secondary", scale=1)

                save_list_box = gr.Markdown(value=get_saves_markdown)
                system_msg = gr.Textbox(label="系統訊息", value="準備就緒", interactive=False)
                reset_btn = gr.Button("重置與當前 NPC 對話", variant="secondary")

            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="遊戲對話紀錄", height=450)

                gr.Markdown("### 🎯 劇情動態選項 (請選擇要發動的行動)")
                with gr.Column():
                    btn_opt_a = gr.Button(DEFAULT_OPTIONS[0], variant="primary")
                    btn_opt_b = gr.Button(DEFAULT_OPTIONS[1], variant="secondary")
                    btn_opt_c = gr.Button(DEFAULT_OPTIONS[2], variant="stop")
                    btn_opt_d = gr.Button(DEFAULT_OPTIONS[3], variant="secondary")
                    btn_opt_e = gr.Button(DEFAULT_OPTIONS[4], variant="secondary")

    # 踏入江湖點擊事件
    btn_enter_game.click(
        fn=enter_jianghu,
        inputs=[player_name_input],
        outputs=[
            prologue_group, main_game_group, chatbot, status_box, map_box, dossier_box, news_box,
            system_msg, location_dropdown, npc_dropdown, save_list_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    # 繼續遊戲點擊事件
    btn_continue_game.click(
        fn=continue_game,
        inputs=[player_name_input],
        outputs=[
            prologue_group, main_game_group, chatbot, status_box, map_box, dossier_box, news_box,
            system_msg, location_dropdown, npc_dropdown, save_list_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
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
            npc_dropdown, save_list_box, btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    # 地圖移動事件
    location_dropdown.change(
        fn=on_select_location,
        inputs=[player_name_input, location_dropdown, chatbot],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box, system_msg, npc_dropdown,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    # 事件繫結
    npc_dropdown.change(
        fn=on_select_npc,
        inputs=[player_name_input, npc_dropdown],
        outputs=[
            status_box, dossier_box, system_msg,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    # 點擊選項 A / B / C / D / E 直接推進劇情
    btn_opt_a.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_a, chatbot, state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    btn_opt_b.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_b, chatbot, state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    btn_opt_c.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_c, chatbot, state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    btn_opt_d.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_d, chatbot, state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    btn_opt_e.click(
        fn=process_player_choice,
        inputs=[player_name_input, state_opt_e, chatbot, state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e],
        outputs=[
            chatbot, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )

    reset_btn.click(
        fn=reset_chat,
        inputs=[player_name_input],
        outputs=[
            chatbot, system_msg, status_box, map_box, dossier_box, news_box,
            btn_opt_a, btn_opt_b, btn_opt_c, btn_opt_d, btn_opt_e,
            state_opt_a, state_opt_b, state_opt_c, state_opt_d, state_opt_e
        ]
    )


if __name__ == "__main__":
    print("正在啟動 Local Blade RPG Web UI (0.0.0.0:7860，已開啟公共分享網址 share=True)...")
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)
