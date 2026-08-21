"""
用本機 RWKV 續寫模型重新生成「圓滿收場」（性愛模式收尾動作）的實際敘事內文，
取代目前手寫的含蓄留白版本。跟 scripts/bootstrap_scene_templates.py 共用同一套
生成/破格過濾/崩壞重試/插槽佔位邏輯，只是這裡只處理這一個 act、用的前綴是專門
導向「即將迎來高潮/內射收尾」情境的版本。

前綴刻意只用「她」/「你」泛用代詞、不帶任何具體角色姓名或設定，讓生成結果保持
角色中立，可以被四位角色共用（這個動作 required_tags 是空的，任何角色都適用）。

用法（需先用 scripts/start_rwkv_server.ps1 啟動 RWKV backend-python）：
    python scripts/regenerate_finisher_scene.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ending_writer import load_ending_writer_config
from src.rwkv_client import RWKVClient
from scripts.bootstrap_scene_templates import _generate_raw, _insert_placeholders

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "scene_templates.json")
ACT_NAME = "圓滿收場"
PREFIX = "他悶哼一聲，加快了抽送的速度，她的嬌喘一聲比一聲急促，兩人的身軀緊緊相貼，"


def main():
    config = load_ending_writer_config()
    client = RWKVClient(base_url=config.rwkv_url, timeout=config.timeout)
    if not client.check_health():
        print(f"連不上 RWKV backend ({config.rwkv_url})，請先執行 scripts/start_rwkv_server.ps1")
        sys.exit(1)

    if not os.path.exists(OUTPUT_PATH):
        print(f"找不到 {OUTPUT_PATH}，請先確認模板庫已建立。")
        sys.exit(1)
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)
    if ACT_NAME not in existing:
        print(f"{OUTPUT_PATH} 裡沒有 [{ACT_NAME}] 這個 act，無法就地更新。")
        sys.exit(1)

    print(f"[生成中] {ACT_NAME} ...")
    # 前幾次用 500 tokens 生成，實測不管怎麼調前綴都會在中段開始跑題（混入第一人稱
    # 偷窺視角、姓名漂移、甚至整段換成不相干的劇情），縮短成 120 tokens 讓生成
    # 停在「即將高潮/內射」這個瞬間本身，減少有機會跑題的篇幅。
    raw = _generate_raw(client, PREFIX, config, max_tokens=120)
    text = _insert_placeholders(PREFIX, raw)
    print(f"[完成]（{len(text)} 字）")

    existing[ACT_NAME]["variants"] = [{"text": text}]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"已更新 {OUTPUT_PATH} 的 [{ACT_NAME}]")


if __name__ == "__main__":
    main()
