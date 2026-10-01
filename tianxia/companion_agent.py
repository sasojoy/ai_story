"""深度對話（設計文件四.3）：LLM 即時生成跟歷史人物的交遊對話，好感度變化查表決定
（不信任 LLM 自報數字），從 ai_story（征服路線引擎）的 src/npc_agent.py 移植並大幅簡化：
拿掉性愛/黑化/終極結局相關的一切，好感度改成 0~100 單向，玩家最多同時帶一段對話。

對話狀態存在 `PlayerState`（這個玩家跟這位人物的私有對話紀錄、上次選項），跟同伴本身
「全服共用」的等級/武學/招募狀態（world_state.py::CompanionProgress）完全分開——
兩者混在一起會讓「唯一同伴」的設計失去意義（不能每個玩家看到的對話歷史都互相污染）。
性格漂移（同一位人物在所有玩家眼中是同一個、被集體形塑的性情）走 world_state.py 的
companion_tag_counts/companion_drift_note，這個模組只負責累積 tag、不負責把 tag 轉成
漂移後的性情描述（那是留給後續獨立任務做的語意判斷，這裡先只做資料累積）。
"""
from __future__ import annotations

import logging
from random import Random

from pydantic import BaseModel, Field

from .models import CharacterDef, Content
from .ollama_client import OllamaClient
from .state import GameState
from .world_state import WorldStateStore

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40
MEMORY_CONSOLIDATION_INTERVAL = 20
MAX_RETRIES = 3
SIGNATURE_SKILL_AFFINITY_THRESHOLD = 70  # 情誼達到這個門檻，才能向對方習得本命武學（設計文件七.1）
DRIFT_SYNTHESIS_INTERVAL = 15  # 全服玩家對這位人物又新累積了幾次交遊 tag，就該重新語意化一次性情漂移

# 好感度 tag 查表（設計文件七.1／五.1 一貫原則：好感度變化只信任封閉分類查表，
# 不信任 LLM 自報數字）。目前是全部人物共用同一張表，之後如果要每位歷史人物有不同的
# 個性化反應強度，可以在 CharacterDef 加一個對應欄位覆寫，這裡先給一個通用版本。
AFFINITY_TAG_DELTAS: dict[str, int] = {
    "雪中送炭": 8,
    "坦誠相待": 7,
    "真誠請教": 6,
    "由衷讚賞": 5,
    "尋常寒暄": 1,
    "冷漠敷衍": -2,
    "言語冒犯": -6,
    "強人所難": -5,
}
DIALOGUE_TAGS = list(AFFINITY_TAG_DELTAS.keys())

GENERIC_OPENING = "上前攀談，試著攀談幾句"


class CompanionTurn(BaseModel):
    """交遊一回合的 LLM 輸出：敘事 + 3 個帶 tag 的選項，好感度查表覆寫，不信任這裡任何數字。"""

    narrative: str = ""
    options: list[str] = Field(default_factory=list)
    option_tags: list[str] = Field(default_factory=list)
    relationship_note_update: str | None = None


class MemoryConsolidation(BaseModel):
    relationship_summary: str = ""
    new_milestones: list[str] = Field(default_factory=list)


class DriftSynthesis(BaseModel):
    drift_note: str = ""


def resolve_tag_delta(tag: str | None, character: CharacterDef | None = None) -> int:
    """查表決定好感度變化：先看這位人物有沒有覆寫這個 tag（CharacterDef.affinity_tag_deltas，
    見「還要改進」第 6 點——15 位人物性格差異很大，同一句話對曹操跟劉備的效果不該一樣），
    沒覆寫才退回全人物共用的預設值。"""
    overrides = character.affinity_tag_deltas if character else None
    if overrides and tag in overrides:
        return overrides[tag]
    return AFFINITY_TAG_DELTAS.get(tag or "", 0)


def _fallback_relationship_note(delta: int, disp_name: str) -> str:
    if delta >= 6:
        trend = "明顯對你升溫，談興更濃了"
    elif delta > 0:
        trend = "對你的態度稍微軟化了一些"
    elif delta == 0:
        trend = "對你維持著一貫的態度，沒有明顯變化"
    elif delta > -5:
        trend = "因為你剛才的話而略顯不悅"
    else:
        trend = "因為你剛才的話而明顯不快"
    return f"{disp_name}{trend}。"


def _fallback_turn(character: CharacterDef, exclude: list[str]) -> CompanionTurn:
    """Ollama 連線失敗/解析失敗時的保底：通用但貼合角色個性的反應，3 個通用選項。"""
    disp_name = character.name
    narrative = f"{disp_name}只是淡淡應了一聲，似乎心思不在此處，並未多說什麼。"
    pool = [
        (f"請教{disp_name}對眼下局勢的看法", "真誠請教"),
        (f"與{disp_name}閒話幾句家常", "尋常寒暄"),
        (f"向{disp_name}坦言自己的來歷與打算", "坦誠相待"),
    ]
    options, tags = [], []
    for text, tag in pool:
        if text not in exclude:
            options.append(text)
            tags.append(tag)
    while len(options) < 3:
        options.append(f"（沉默地陪{disp_name}站一會兒）")
        tags.append("尋常寒暄")
    return CompanionTurn(narrative=narrative, options=options[:3], option_tags=tags[:3])


def build_system_prompt(
    character: CharacterDef, state: GameState, content: Content, world: WorldStateStore, companion_id: str,
) -> str:
    p = state.player
    affinity = p.affinities.get(companion_id, 0)
    my_note = p.relationship_notes.get(companion_id, "尚無記錄")
    drift = world.get_companion_drift_note(companion_id)
    drift_str = f"\n【{character.name}近來因眾人互動而顯露的性情變化】: {drift}" if drift else ""
    used = p.used_dialogue_options.get(companion_id, [])
    used_str = "、".join(f"「{o}」" for o in used[-8:]) if used else "無"
    tags_str = "、".join(DIALOGUE_TAGS)

    return (
        f"你是文字角色扮演遊戲的敘事引擎，正在扮演三國時代真實歷史人物「{character.name}」，"
        f"跟玩家進行一段交遊對話。\n"
        f"【{character.name}的出身】{character.background}\n"
        f"【{character.name}此時的處境】{character.situation}\n"
        f"【{character.name}的性格】{character.personality}{drift_str}\n"
        f"【玩家】{p.name}，目前好感度 {affinity}（範圍 0~100，只會照玩家選的話變化，"
        f"不是你決定的）。你與玩家目前的關係現況：{my_note}\n"
        f"【已經說過的話（避免重複）】{used_str}\n\n"
        "【寫作要求】\n"
        "0. 全程使用繁體中文書寫（包含人名、選項文字），不可出現簡體字。\n"
        "1. 以貼合三國時代語境的口吻描寫這一回合的互動與對白，控制在 100~200 字，"
        "要有畫面感（神情、語氣、周遭環境），不要寫成流水帳，同一句話不要連用超過 3 個「的」字。\n"
        f"2. 必須在 options 欄位生成 3 個具體的玩家發言/行動選項，圍繞與{character.name}的"
        "交流展開，每個選項只能描述玩家打算說/做的事本身，不能預先寫死對方會怎麼回應。\n"
        "3. 同時在 option_tags 欄位依序附上這 3 個選項各自最貼近的分類，只能從這個固定清單"
        f"裡選一個：[{tags_str}]，嚴禁自創清單外的分類——好感度變化由系統查表決定，不是你的"
        "工作。\n"
        "4. relationship_note_update 欄位請用一句話描述這回合結束後你們的關係現況，"
        "盡量包含一個具體細節，不要只寫抽象形容詞。\n"
        "5. 必須且僅能輸出符合下列範例的合法 JSON 物件：\n"
        '{"narrative": "...", "options": ["選項一", "選項二", "選項三"], '
        f'"option_tags": ["{DIALOGUE_TAGS[0]}", "{DIALOGUE_TAGS[1]}", "{DIALOGUE_TAGS[2]}"], '
        '"relationship_note_update": "..."}'
    )


def _build_messages(
    character: CharacterDef, state: GameState, content: Content, world: WorldStateStore, companion_id: str,
    player_action: str,
) -> list[dict[str, str]]:
    system_prompt = build_system_prompt(character, state, content, world, companion_id)
    history = state.player.dialogue_history.get(companion_id, [])[-4:]
    messages = [{"role": "system", "content": system_prompt}] + list(history)
    messages.append({"role": "user", "content": f"玩家的行動：「{player_action}」\n請描寫{character.name}的反應，並提供 3 個新選項。"})
    return messages


def _record_turn(state: GameState, companion_id: str, player_action: str, turn: CompanionTurn) -> None:
    p = state.player
    history = p.dialogue_history.setdefault(companion_id, [])
    history.append({"role": "user", "content": player_action})
    history.append({"role": "assistant", "content": turn.narrative})
    if len(history) > MAX_HISTORY_MESSAGES:
        p.dialogue_history[companion_id] = history[-MAX_HISTORY_MESSAGES:]
    used = p.used_dialogue_options.setdefault(companion_id, [])
    used.append(player_action.strip())
    p.turns_since_consolidation[companion_id] = p.turns_since_consolidation.get(companion_id, 0) + 1


def _apply_turn(
    state: GameState, character: CharacterDef, companion_id: str, player_action: str, turn: CompanionTurn,
    tag: str | None,
) -> list[str]:
    """回合收尾共用邏輯：查表覆寫好感度、記錄對話、更新關係現況，回傳要顯示的訊息。"""
    p = state.player
    delta = resolve_tag_delta(tag, character)
    before = p.affinities.get(companion_id, 0)
    after = max(0, min(100, before + delta))
    p.affinities[companion_id] = after

    note = turn.relationship_note_update
    if not (note and note.strip()):
        note = _fallback_relationship_note(delta, character.name)
    p.relationship_notes[companion_id] = note

    _record_turn(state, companion_id, player_action, turn)
    p.last_offered_dialogue[companion_id] = [list(turn.options), list(turn.option_tags)]

    msgs = [turn.narrative]
    if delta:
        msgs.append(f"（好感度 {'+' if delta >= 0 else ''}{delta}）")
    return msgs


def start_dialogue(
    client: OllamaClient | None, state: GameState, content: Content, world: WorldStateStore, companion_id: str,
    rng: Random,
) -> list[str]:
    """交遊觸發深度對話的第一回合：用一句通用的「上前攀談」當隱含的玩家行動。"""
    character = content.characters[companion_id]
    state.player.pending_companion = companion_id
    exclude = state.player.used_dialogue_options.get(companion_id, [])
    turn = _generate(client, character, state, content, world, companion_id, GENERIC_OPENING, exclude)
    return _apply_turn(state, character, companion_id, GENERIC_OPENING, turn, tag=None)


def continue_dialogue(
    client: OllamaClient | None, state: GameState, content: Content, world: WorldStateStore, companion_id: str,
    choice_index: int, rng: Random,
) -> list[str]:
    """玩家選了上一回合的第 choice_index 個選項：查表套用好感度、繼續生成下一回合。"""
    character = content.characters[companion_id]
    options, tags = state.player.last_offered_dialogue.get(companion_id, [[], []])
    if not (0 <= choice_index < len(options)):
        return ["（此刻無法這麼做。）"]
    player_action, tag = options[choice_index], tags[choice_index] if choice_index < len(tags) else None

    world.record_companion_tag(companion_id, tag or "尋常寒暄")
    exclude = state.player.used_dialogue_options.get(companion_id, [])
    turn = _generate(client, character, state, content, world, companion_id, player_action, exclude)
    msgs = _apply_turn(state, character, companion_id, player_action, turn, tag)
    msgs += _maybe_grant_signature_skill(state, content, character, companion_id)
    msgs += _maybe_consolidate_memory(client, state, character, companion_id)
    _maybe_synthesize_drift(client, character, companion_id, world)
    return msgs


def _maybe_consolidate_memory(client: OllamaClient | None, state: GameState, character: CharacterDef, companion_id: str) -> list[str]:
    """每隔 MEMORY_CONSOLIDATION_INTERVAL 輪，獨立呼叫一次濃縮關係現況、補上漏記的細節——
    不是每輪順便問 LLM「這輪值不值得記住」（那個做法實測填寫率極低，見 CLAUDE.md
    第三輪教訓），是把這個判斷切成一個獨立、不受敘事生成時間壓力干擾的定期任務。"""
    p = state.player
    if client is None or p.turns_since_consolidation.get(companion_id, 0) < MEMORY_CONSOLIDATION_INTERVAL:
        return []
    history = p.dialogue_history.get(companion_id, [])
    if not history:
        return []
    history_text = "\n".join(f"{'玩家' if m.get('role') == 'user' else character.name}：{m.get('content', '')}" for m in history)
    messages = [
        {"role": "system", "content": (
            f"你是遊戲的記憶整理系統，負責替角色「{character.name}」回顧近期發生的事，不負責寫新劇情。"
            "這是一段累積了好幾輪互動的對話紀錄，這段期間一定發生過值得記錄的事——"
            "relationship_summary 請用一到兩句話重新濃縮這段期間累積下來的關係現況；"
            "new_milestones 請列出這段對話裡出現過、值得永久記住的具體事件（不分大小）。"
            "兩個欄位都不可以留空，務必從對話紀錄裡找出至少一件具體的事寫下來。"
        )},
        {"role": "user", "content": f"近期對話紀錄：\n{history_text}"},
    ]
    result = None
    for _ in range(MAX_RETRIES):
        try:
            candidate = client.chat_structured(messages, MemoryConsolidation, temperature=0.6)
        except Exception:
            continue
        if candidate.relationship_summary.strip() or candidate.new_milestones:
            result = candidate
            break
    if result is None:
        return []
    p.turns_since_consolidation[companion_id] = 0
    p.relationship_notes[companion_id] = result.relationship_summary.strip() or p.relationship_notes.get(companion_id, "")
    return [f"📖 【記憶梳理】{character.name} 這段時光的點滴，已在心底沉澱。"]


def _maybe_synthesize_drift(client: OllamaClient | None, character: CharacterDef, companion_id: str, world: WorldStateStore) -> None:
    """性情漂移語意化（設計文件四.3，先前只累積原始 tag 計數、沒有語意判斷的部分）：
    每當全服玩家對這位人物又新累積了 DRIFT_SYNTHESIS_INTERVAL 次交遊 tag，獨立呼叫一次
    LLM，把「大家最近對他做了什麼」的分佈濃縮成一句漂移後的性情描述，寫回共用世界狀態
    （build_system_prompt 已經會讀取並顯示給下一輪對話參考）。這是全服共用的判斷，不是
    某個玩家專屬的，所以不回傳訊息給玩家看——純粹背景更新，失敗就跳過，下次互動再試。"""
    if client is None or world.tag_counts_since_last_drift(companion_id) < DRIFT_SYNTHESIS_INTERVAL:
        return
    counts = world.read().companion_tag_counts.get(companion_id, {})
    if not counts:
        return
    distribution = "、".join(f"{tag} {n} 次" for tag, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    baseline_note = world.get_companion_drift_note(companion_id)
    baseline_str = f"\n他目前已經漂移到的性情：{baseline_note}" if baseline_note else ""
    messages = [
        {"role": "system", "content": (
            f"你是遊戲的性情演化系統，負責判斷歷史人物「{character.name}」在許多玩家的集體互動下，"
            "性情是否該有細微的變化——這是全服共用的判斷，不是針對單一玩家。\n"
            f"【{character.name}的性格基礎模板（不可違背，只能在這個基礎上微調）】{character.personality}"
            f"{baseline_str}\n"
            f"【眾玩家累積至今、對他的言行傾向統計】{distribution}\n"
            "請用一句話描述他現在的性情，應該要反映統計裡占比最高的傾向，但措辭要貼合他的基礎性格，"
            "不能整個變成另一個人；如果統計分佈很平均、看不出明顯傾向，就寫他維持基礎性格、"
            "只是更加篤定或更加圓融這類細微描述，不要憑空編造劇情事件。"
        )},
        {"role": "user", "content": "請給出 drift_note。"},
    ]
    for _ in range(MAX_RETRIES):
        try:
            result = client.chat_structured(messages, DriftSynthesis, temperature=0.6, required_fields=["drift_note"])
        except Exception:
            continue
        if result.drift_note.strip():
            world.record_drift_synthesis(companion_id, result.drift_note.strip())
            return


def leave_dialogue(state: GameState) -> list[str]:
    if state.player.pending_companion is None:
        return []
    state.player.pending_companion = None
    return ["你結束了這段交談，先行告辭。"]


def _generate(
    client: OllamaClient | None, character: CharacterDef, state: GameState, content: Content, world: WorldStateStore,
    companion_id: str, player_action: str, exclude: list[str],
) -> CompanionTurn:
    if client is None:
        return _fallback_turn(character, exclude)
    messages = _build_messages(character, state, content, world, companion_id, player_action)
    try:
        return client.chat_structured(messages, CompanionTurn, required_fields=["options"])
    except Exception as e:
        logger.warning(f"companion_agent 生成失敗 ({companion_id}): {e}，改用保底反應")
        return _fallback_turn(character, exclude)


def _maybe_grant_signature_skill(state: GameState, content: Content, character: CharacterDef, companion_id: str) -> list[str]:
    """設計文件七.1：情誼滿門檻才能習得對方的本命武學。系統決定性判斷，不靠 LLM——
    跟里程碑/天機記事橫幅同一套「系統偵測狀態轉換」精神，只在真的跨過門檻那一刻觸發一次
    （用 flags 記錄過，之後即使好感度掉回門檻以下再升上來也不會重複觸發/重複學習）。
    learn_skill() 本身已經有「欄位已經有人就跳過」的保護，這裡只需要負責「這是不是
    第一次跨過門檻」。"""
    from .rules import learn_skill

    p = state.player
    if p.affinities.get(companion_id, 0) < SIGNATURE_SKILL_AFFINITY_THRESHOLD:
        return []
    flag = f"學會本命:{companion_id}"
    if flag in p.flags:
        return []
    p.flags.add(flag)
    msgs: list[str] = [f"你與{character.name}情誼深厚，他願意將本命武學傾囊相授！"]
    for skill_id in (character.starting_wugong, character.starting_neigong):
        if skill_id:
            msgs += learn_skill(state, content, skill_id)
    return msgs
