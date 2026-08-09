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


def run_interaction(engine: GameEngine, player_input: str, mock_fallback_delta: GameStateDelta) -> GameStateDelta:
    try:
        print("[GM 計算中.../呼叫 Ollama LLM API]")
        delta = engine.interact(player_input)
        return delta
    except Exception as e:
        print(f"[提示] Ollama API 呼叫未成功 ({e})")
        print("[自動啟用模擬 LLM 回應引擎展示 Pydantic Schema / JSON 輸出規格]")
        # 手動套用 delta 至引擎
        engine.apply_delta(mock_fallback_delta)
        if engine.current_agent:
            engine.current_agent.history.append({"role": "user", "content": player_input})
            engine.current_agent.history.append({"role": "assistant", "content": mock_fallback_delta.narrative})
            engine.current_agent.current_status_tag = mock_fallback_delta.npc_status_tag
        return mock_fallback_delta


def run_verification():
    print("=" * 60)
    print("      Local Blade RPG 遊戲邏輯與 LLM JSON 輸出驗證腳本")
    print("=" * 60)

    engine = GameEngine()

    # 1. 測試殺手阿福
    print("\n" + "=" * 50)
    print("【情境 1】切換 NPC -> 殺手阿福")
    engine.switch_npc("殺手阿福")
    print(f"目前 NPC: {engine.current_agent.profile.name} ({engine.current_agent.profile.identity})")

    player_input_afu = "現在已經下午 6 點 01 分了，如果你不收刀下班，我就要向勞工局檢舉你違法加班！"
    print(f"玩家輸入: {player_input_afu}\n")

    mock_delta_afu = GameStateDelta(
        narrative="殺手阿福聽到『勞工局』三個字頓時臉色大變，慌忙將血滴子塞進公務包，掏出一張打卡單：『誤會！都是誤會！我阿福向來嚴格遵守一例一休，絕無超時加班之事！這 100 兩算是我給您的精神損失補償，請萬萬不可通報勞動檢查！』說完一溜煙消失在暗巷中。",
        player_hp_change=0,
        player_gold_change=100,
        inventory_added=["阿福的打卡紀錄表"],
        inventory_removed=[],
        npc_status_tag="驚慌下班",
        world_flag_set={"afu_off_duty": True, "labor_bureau_reported": False}
    )

    delta_afu = run_interaction(engine, player_input_afu, mock_delta_afu)

    print("\n--- 殺手阿福 回應結果 (GameStateDelta Model) ---")
    print(f"故事劇情 Narrative:\n{delta_afu.narrative}\n")
    print(f"玩家 HP 變更: {delta_afu.player_hp_change}")
    print(f"玩家金幣變更: {delta_afu.player_gold_change}")
    print(f"獲得物品: {delta_afu.inventory_added}")
    print(f"失去物品: {delta_afu.inventory_removed}")
    print(f"NPC 狀態標籤: {delta_afu.npc_status_tag}")
    print(f"世界 Flag 標記: {delta_afu.world_flag_set}")

    print("\n--- Raw / Formatted JSON Output (Pydantic Dump) ---")
    print(json.dumps(delta_afu.model_dump(), ensure_ascii=False, indent=2))

    # 2. 測試錢莊老王
    print("\n" + "=" * 50)
    print("【情境 2】切換 NPC -> 錢莊老王")
    engine.switch_npc("錢莊老王")
    print(f"目前 NPC: {engine.current_agent.profile.name} ({engine.current_agent.profile.identity})")

    player_input_wang = "掌櫃的，我這裡有一套龍門客棧不良資產包打包證券化 (MBS) 方案，年化報酬 18%，你要不要槓桿開滿加碼？"
    print(f"玩家輸入: {player_input_wang}\n")

    mock_delta_wang = GameStateDelta(
        narrative="錢莊老王眼睛射出金光，算盤撥得飛快：『年化 18%？！這簡直是天才的金融創新！拿著！這 300 兩當做首期次級債券認購金，你快把這套 Asset-Backed Securities 說明書給我畫出來！』老王激動得雙手發抖，甚至塞給你一把錢莊貴賓鑰匙。",
        player_hp_change=0,
        player_gold_change=300,
        inventory_added=["龍門錢莊貴賓鑰匙"],
        inventory_removed=[],
        npc_status_tag="極度亢奮",
        world_flag_set={"wang_mbs_purchased": True, "financial_leverage_max": True}
    )

    delta_wang = run_interaction(engine, player_input_wang, mock_delta_wang)

    print("\n--- 錢莊老王 回應結果 (GameStateDelta Model) ---")
    print(f"故事劇情 Narrative:\n{delta_wang.narrative}\n")
    print(f"玩家 HP 變更: {delta_wang.player_hp_change}")
    print(f"玩家金幣變更: {delta_wang.player_gold_change}")
    print(f"獲得物品: {delta_wang.inventory_added}")
    print(f"失去物品: {delta_wang.inventory_removed}")
    print(f"NPC 狀態標籤: {delta_wang.npc_status_tag}")
    print(f"世界 Flag 標記: {delta_wang.world_flag_set}")

    print("\n--- Raw / Formatted JSON Output (Pydantic Dump) ---")
    print(json.dumps(delta_wang.model_dump(), ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("驗證完成！當前玩家狀態彙總：")
    print(f"HP: {engine.player_state.hp}/{engine.player_state.max_hp}")
    print(f"Gold: {engine.player_state.gold}")
    print(f"Inventory: {engine.player_state.inventory}")
    print(f"World Flags: {engine.world_flags}")
    print("=" * 60)


if __name__ == "__main__":
    run_verification()
