"""過渡（開發規範手冊 3.11）：名將本命兵器的規則搬進功能包 tianxia/features/gear/signature_arms.py（全部拆包第 42 批）。這個名字留成指到同一個模組的
別名：`from tianxia import signature_arms`（engine 的 _drop_stale_references 讀 refresh_names、leaderboard.gear_card、測試）照舊拿到那一份。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.gear import signature_arms as _signature_arms

sys.modules[__name__] = _signature_arms
