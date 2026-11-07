"""過渡（開發規範手冊 3.11）：擂台賽的規則搬進功能包 tianxia/features/bout/arena_rules.py（全部拆包第 12 批）。這個名字留成指到同一個
模組的別名：`from tianxia import arena`（還沒搬的舊模組 bot_policy、scripts 與測試）
照舊拿到那一份（換掉的屬性兩邊都看得到）。擂台的名次與稱號是核心的查詢服務
（tianxia/core/arena_ranks.py，那一份 re-export 它；只讀這幾樣的名帖、玩家卡、榜單直接讀核心）。程式裡新寫的一律 import 包或核心；
呼叫端改完就拿掉。"""
import sys

from tianxia.features.bout import arena_rules as _rules

sys.modules[__name__] = _rules
