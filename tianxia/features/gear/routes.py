"""裝備的動作表（功能包 tianxia/features/gear/；原本寫在 server.py 的 MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（menxia_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
_id_list 留在殼（修練包也用）。"""
from . import bench_actions


def menxia_actions(shell) -> dict:
    return {
        "wield": lambda g, b: bench_actions.wield_weapon(g, str(b.get("weapon") or "")),  # 裝備庫上那一件換到身上它那一欄（兵器設計 2.2、裝備四欄 2.3）：武器、防具、坐騎、寶物都走這裡，網頁照舊送 weapon 這個鍵
        "dismantle": lambda g, b: bench_actions.dismantle_weapon(g, str(b.get("weapon") or "")),  # 裝備庫上那一件拆成一個素材（兵器設計 4.7.1、裝備四欄 4.8）：坐騎、寶物不能拆
        "feed": lambda g, b: bench_actions.feed_mount(g),  # 身上那匹餵一個一階素材（裝備四欄 5.4）：閒著時哪裡都能餵
        # 裝備庫勾好的一次拆完（鐵匠鋪與合成流程 3.4）：items 是 id 的串列（不是串列的當沒勾）；不擋地點、拆不了的跳過寫原因、一則修練紀錄
        "dismantle_many": lambda g, b: bench_actions.dismantle_many(g, shell._id_list(b.get("items"))),
    }
