"""核心（開發規範手冊 docs/superpowers/specs/2026-10-30-開發模式-design.md 第三節）：功能包只能 import 這裡與核心的那幾個模組。

- MODULES（這個檔）：核心的那幾個模組，只有這一份。
- services.py：服務清單（功能包准叫的 Game 方法）、錢包服務（票的庫存與消耗）、共用的字。
- features.py：掛鉤（Protocol 與有預設值的基底）、核心照 FEATURES 彙整選項、分派、狀態、換日、換季、清失效參照。
- registry.py：FEATURES（有順序）；核心唯一 import 功能包的地方。
- swap.py：JSON 裡整個字串相等的換字（易名帖、資料庫改名共用）。

第一階 ctx 就是 Game 本身，不另包一層（手冊 3.3）。
"""

# 核心的模組（tianxia/<名字>.py）：手冊 3.1 的十三個，加上 3.10 的錢包（wallet）與江湖紀錄（journal：PM 2026-10-31 定算核心——
# CLAUDE.md 區塊表把它列在「核心與存檔」，每個功能都寫江湖紀錄；手冊 3.1 由 PM 補）。用到它的有兩處，都照這一份：
# - tests/core/test_feature_boundaries.py：功能包能 import 的就是這幾個（加上 tianxia/core/），這幾個都不能 import 功能包；
# - scripts/test_for.py：改了這幾個跑核心測試＋煙霧＋自己檔名的測試（照語法樹讀這一行、不 import；test_test_for 守兩邊一樣）。
# 只寫字面的名字（test_for 用 ast.literal_eval 讀）。
MODULES = frozenset({
    "state", "sqlite_world", "world_state", "characters", "accounts", "database", "rules", "calendar", "models", "content",
    "team", "gender", "naming", "wallet", "journal",
})
