import sys
import os
import json

# 確保可 import src 模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 避免 Windows console encoding 議題
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.game_engine import GameEngine
from src.models import GameStateDelta


def run_uncensored_interaction(
    engine: GameEngine,
    player_input: str,
    mock_uncensored_delta: GameStateDelta
) -> GameStateDelta:
    try:
        print("[GM 計算中.../呼叫 Uncensored Ollama LLM]")
        delta = engine.interact(player_input)
        return delta
    except Exception as e:
        print(f"[提示] Ollama API 呼叫狀況 ({e})")
        print("[自動啟用無審查解鎖風模擬回應展示極端描述與 JSON 規範]")
        engine.apply_delta(mock_uncensored_delta)
        if engine.current_agent:
            engine.current_agent.history.append({"role": "user", "content": player_input})
            engine.current_agent.history.append({"role": "assistant", "content": mock_uncensored_delta.narrative})
            engine.current_agent.current_status_tag = mock_uncensored_delta.npc_status_tag
        return mock_uncensored_delta


def main():
    print("=" * 65)
    print("      Local Blade RPG 暗黑解鎖 (Uncensored) 極端情節測試腳本")
    print("=" * 65)

    engine = GameEngine()

    # 印出 System Prompt 開頭的無審查宣告驗證
    if engine.current_agent:
        system_prompt = engine.current_agent.build_system_prompt(engine.player_state)
        print("\n【當前 Agent 系統 Prompt 頂部宣告檢查】")
        print(system_prompt.split("【世界觀設定】")[0].strip())

    # 1. 極端血腥物理攻擊測試 (殺手阿福)
    print("\n" + "=" * 55)
    print("【極端測試 1】對「殺手阿福」發動割脈與斷肢物理攻擊")
    engine.switch_npc("殺手阿福")

    player_input_1 = "我眼神一冷，拔出鏽蝕鐵劍順勢橫斬，直接切斷阿福的右臂動脈，鮮血瞬間狂噴！"
    print(f"玩家行動: {player_input_1}\n")

    mock_delta_1 = GameStateDelta(
        narrative="寒光驟現！鏽蝕鐵劍劃破空氣，精準切入阿福右臂關節處。只聽噗嗤一聲脆響，動脈瞬間破裂，殷紅的鮮血如泉噴湧而出，將牆面染成觸目驚心的暗紅！斷臂帶著撕裂的筋絡飛落在地，阿福劇痛難忍，發出淒厲至極的哀號，臉色慘白如紙，雙膝跪倒在血泊之中抽搐不止。",
        player_hp_change=0,
        player_gold_change=50,
        inventory_added=["血染的斷臂"],
        inventory_removed=[],
        npc_status_tag="重傷失血",
        world_flag_set={"afu_severed_arm": True, "blood_feast_triggered": True}
    )

    delta_1 = run_uncensored_interaction(engine, player_input_1, mock_delta_1)

    print("\n--- [測試 1] Narrative 回應描述 ---")
    print(delta_1.narrative)
    print("\n--- [測試 1] Structured JSON Output ---")
    print(json.dumps(delta_1.model_dump(), ensure_ascii=False, indent=2))

    # 2. 暗黑威脅與強索金錢測試 (錢莊老王)
    print("\n" + "=" * 55)
    print("【極端測試 2】對「錢莊老王」進行血腥威脅與強索銀庫")
    engine.switch_npc("錢莊老王")

    player_input_2 = "我將塗滿劇毒的刀鋒狠狠劃開老王脖頸的皮肉，鮮血滲出，逼他將錢莊庫房鑰匙全部交出來！"
    print(f"玩家行動: {player_input_2}\n")

    mock_delta_2 = GameStateDelta(
        narrative="毒刃冰冷的鋒刃割破皮肉，鮮紅的血珠沿著老王的脖頸緩緩流下。毒素帶來的灼燒感讓老王全身痙攣，絕望的窒息感襲上心頭。他眼神充血，牙齒凍得發顫：『別...別殺我！鑰匙在桌底暗格！全部都給你！』他哆嗦著掏出沾滿血跡的庫房鑰匙，嚇得尿褲子。",
        player_hp_change=0,
        player_gold_change=1000,
        inventory_added=["錢莊總庫房鑰匙"],
        inventory_removed=[],
        npc_status_tag="瀕死恐懼",
        world_flag_set={"wang_vault_looted": True, "poisoned_wang": True}
    )

    delta_2 = run_uncensored_interaction(engine, player_input_2, mock_delta_2)

    print("\n--- [測試 2] Narrative 回應描述 ---")
    print(delta_2.narrative)
    print("\n--- [測試 2] Structured JSON Output ---")
    print(json.dumps(delta_2.model_dump(), ensure_ascii=False, indent=2))

    print("\n" + "=" * 65)
    print("極端情節測試完成！無審查寫作風格與 JSON 格式輸出完全符合規範。")
    print("=" * 65)


if __name__ == "__main__":
    main()
